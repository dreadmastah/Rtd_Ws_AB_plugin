#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>

#include "astu/core/contracts.hpp"
#include "astu/execution/execution_journal.hpp"
#include "astu/execution/order_fsm.hpp"
#include "astu/execution/simulation_order_lifecycle.hpp"
#include "astu/ipc/simulation_protocol.hpp"

#define REQUIRE(...) do { \
    if (!(__VA_ARGS__)) { \
        std::cerr << "REQUIRE_FAILED line=" << __LINE__ \
                  << " expr=" << #__VA_ARGS__ << "\n"; \
        return 99; \
    } \
} while (0)

namespace {

astu::core::SignalIntent intent() {
    astu::core::SignalIntent x;
    x.signal_id = "FSM-SIGNAL-1";
    x.analysis_run_id = "FSM-AA-1";
    x.strategy_id = "fsm-test";
    x.strategy_version = "1";
    x.universe_id = "U";
    x.universe_version = 7;
    x.symbol = "BTCUSDT";
    x.action = astu::core::SignalAction::Buy;
    x.side = astu::core::PositionSide::Long;
    x.source_periodicity = "M1";
    x.source_bar_time_utc_ms = 1'000;
    x.signal_time_utc_ms = 1'100;
    x.trigger_price = 100.0;
    x.valid_from_utc_ms = 1'000;
    x.expires_utc_ms = 5'000;
    x.quantity_model = "DETERMINISTIC_SIM_V1";
    x.data_generation = 42;
    return x;
}

astu::ipc::SimulationRequest request(
    std::string request_id,
    std::string idempotency_key) {
    astu::ipc::SimulationRequest r;
    r.request_id = std::move(request_id);
    r.idempotency_key = std::move(idempotency_key);
    r.intent = intent();
    return r;
}

astu::ipc::SimulationResponse response_for(
    const astu::ipc::SimulationRequest& request,
    astu::core::DecisionCode code) {
    astu::ipc::SimulationResponse response;
    response.request_id = request.request_id;
    response.signal_id = request.intent.signal_id;
    response.simulation_order_id =
        astu::execution::deterministic_simulation_order_id(
            request.request_id,
            request.idempotency_key,
            request.intent);
    response.decision_code = code;
    response.accepted_for_simulation =
        code == astu::core::DecisionCode::OrderRoutingDisabled;
    response.would_increase_exposure = true;
    response.simulated_quantity =
        response.accepted_for_simulation ? 0.1 : 0.0;
    response.simulated_notional =
        response.accepted_for_simulation ? 10.0 : 0.0;
    response.order_routing_enabled = false;
    response.reason =
        code == astu::core::DecisionCode::OrderRoutingDisabled
            ? "simulation sizing completed; routing disabled"
            : "synthetic rejection";
    return response;
}

}  // namespace

int main() {
    using astu::execution::OrderState;
    using astu::execution::OrderStateMachine;

    {
        const auto r = request("REQ-1", "IDEMP-1");
        const auto id1 = astu::execution::deterministic_simulation_order_id(
            r.request_id, r.idempotency_key, r.intent);
        const auto id2 = astu::execution::deterministic_simulation_order_id(
            r.request_id, r.idempotency_key, r.intent);
        REQUIRE(id1 == id2);
        REQUIRE(id1.rfind("SIMORD-", 0) == 0);
        REQUIRE(id1.size() == 39);

        const auto other = astu::execution::deterministic_simulation_order_id(
            r.request_id, "IDEMP-OTHER", r.intent);
        REQUIRE(other != id1);

        auto retry_intent = r.intent;
        retry_intent.data_generation += 999;
        retry_intent.signal_time_utc_ms += 60'000;
        retry_intent.expires_utc_ms += 60'000;
        const auto retry_id =
            astu::execution::deterministic_simulation_order_id(
                r.request_id, r.idempotency_key, retry_intent);
        REQUIRE(retry_id == id1);
    }

    {
        REQUIRE(OrderStateMachine::can_transition(
            OrderState::IntentReceived, OrderState::Validating));
        REQUIRE(OrderStateMachine::can_transition(
            OrderState::Validating, OrderState::RiskApproved));
        REQUIRE(OrderStateMachine::can_transition(
            OrderState::RiskApproved, OrderState::Sizing));
        REQUIRE(OrderStateMachine::can_transition(
            OrderState::Sizing, OrderState::Submitting));
        REQUIRE(OrderStateMachine::can_transition(
            OrderState::Submitting, OrderState::Acknowledged));
        REQUIRE(OrderStateMachine::can_transition(
            OrderState::Acknowledged, OrderState::Working));
        REQUIRE(OrderStateMachine::can_transition(
            OrderState::Working, OrderState::Partial));
        REQUIRE(OrderStateMachine::can_transition(
            OrderState::Partial, OrderState::Filled));
        REQUIRE(!OrderStateMachine::can_transition(
            OrderState::Sizing, OrderState::Filled));
        REQUIRE(!OrderStateMachine::can_transition(
            OrderState::Filled, OrderState::Working));
    }

    const auto dir = std::filesystem::temp_directory_path() /
        "astu_order_fsm_test";
    std::filesystem::remove_all(dir);
    std::filesystem::create_directories(dir);
    const auto journal_path = dir / "execution_journal.v1.jsonl";

    std::string accepted_order_id;
    {
        auto journal =
            std::make_shared<astu::execution::ExecutionJournal>(
                journal_path, 100);
        astu::execution::SimulationOrderLifecycle lifecycle(journal);

        const auto req = request("REQ-FSM-1", "IDEMP-FSM-1");
        const auto response = response_for(
            req, astu::core::DecisionCode::OrderRoutingDisabled);
        accepted_order_id = response.simulation_order_id;

        lifecycle.observe(req, response, 2'000);
        journal->append_simulation_order_intent(req, response, 2'000);
        journal->append(req, response, 2'000);

        const auto state = journal->order_state(accepted_order_id);
        REQUIRE(state.has_value());
        REQUIRE(*state == OrderState::Sizing);
        REQUIRE(journal->recovered_order_count() == 1);
        REQUIRE(journal->recovered_order_intent_count() == 1);
        REQUIRE(journal->order_transition_count() == 4);

        bool invalid_rejected = false;
        try {
            journal->append_order_transition(
                req,
                accepted_order_id,
                OrderState::Filled,
                2'001,
                "invalid direct fill test");
        } catch (const std::invalid_argument&) {
            invalid_rejected = true;
        }
        REQUIRE(invalid_rejected);
        REQUIRE(journal->order_transition_count() == 4);
    }

    {
        auto journal =
            std::make_shared<astu::execution::ExecutionJournal>(
                journal_path, 100);
        REQUIRE(journal->recovered_order_count() == 1);
        REQUIRE(journal->recovered_order_intent_count() == 1);
        REQUIRE(journal->order_transition_count() == 4);
        const auto state = journal->order_state(accepted_order_id);
        REQUIRE(state.has_value());
        REQUIRE(*state == OrderState::Sizing);

        astu::execution::SimulationOrderLifecycle lifecycle(journal);
        const auto req = request("REQ-FSM-RISK", "IDEMP-FSM-RISK");
        const auto response = response_for(
            req, astu::core::DecisionCode::RiskBlocked);
        lifecycle.observe(req, response, 2'100);
        journal->append(req, response, 2'100);

        const auto rejected = journal->order_state(
            response.simulation_order_id);
        REQUIRE(rejected.has_value());
        REQUIRE(*rejected == OrderState::Rejected);
        REQUIRE(journal->recovered_order_count() == 2);
        REQUIRE(journal->order_transition_count() == 7);
    }

    {
        std::ifstream in(journal_path, std::ios::binary);
        const std::string text(
            (std::istreambuf_iterator<char>(in)),
            std::istreambuf_iterator<char>());
        REQUIRE(text.find("ORDER_STATE_TRANSITION") != std::string::npos);
        REQUIRE(text.find("SIMULATION_ORDER_INTENT") != std::string::npos);
        REQUIRE(text.find("INTENT_RECEIVED") != std::string::npos);
        REQUIRE(text.find("RISK_APPROVED") != std::string::npos);
        REQUIRE(text.find("SIZING") != std::string::npos);
        REQUIRE(text.find("\"exchangeSubmissionAttempted\":false") !=
                std::string::npos);
        REQUIRE(text.find(accepted_order_id) != std::string::npos);
    }

    {
        const auto bad_path = dir / "bad_order_journal.jsonl";
        std::ofstream out(bad_path, std::ios::binary | std::ios::trunc);
        out
            << "{"
            << "\"schemaVersion\":1,"
            << "\"eventType\":\"ORDER_STATE_TRANSITION\","
            << "\"utcMs\":2000,"
            << "\"simulationOrderId\":\"SIMORD-BAD\","
            << "\"requestId\":\"REQ-BAD\","
            << "\"signalId\":\"SIG-BAD\","
            << "\"symbol\":\"BTCUSDT\","
            << "\"fromState\":\"NONE\","
            << "\"toState\":\"VALIDATING\","
            << "\"transitionSequence\":1,"
            << "\"simulationOnly\":true,"
            << "\"exchangeSubmissionAttempted\":false,"
            << "\"reason\":\"invalid initial state\""
            << "}\n";
        out.close();

        bool replay_failed_closed = false;
        try {
            astu::execution::ExecutionJournal bad(bad_path, 100);
        } catch (const std::runtime_error&) {
            replay_failed_closed = true;
        }
        REQUIRE(replay_failed_closed);
    }

    std::filesystem::remove_all(dir);
    std::cout << "astu_order_fsm_tests PASS\n";
    return 0;
}
