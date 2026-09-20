#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <stdexcept>
#include <string>

#include "astu/core/contracts.hpp"
#include "astu/execution/execution_journal.hpp"
#include "astu/execution/order_fsm.hpp"
#include "astu/execution/simulation_order_lifecycle.hpp"
#include "astu/execution/simulation_reconciliation.hpp"
#include "astu/ipc/simulation_protocol.hpp"

#define REQUIRE(...) do { \
    if (!(__VA_ARGS__)) { \
        std::cerr << "REQUIRE_FAILED line=" << __LINE__ \
                  << " expr=" << #__VA_ARGS__ << "\n"; \
        return 99; \
    } \
} while (0)

namespace {

astu::ipc::SimulationRequest request() {
    astu::ipc::SimulationRequest request;
    request.request_id = "RECON-REQ-1";
    request.idempotency_key = "RECON-IDEMP-1";
    auto& i = request.intent;
    i.signal_id = "RECON-SIGNAL-1";
    i.analysis_run_id = "RECON-AA-1";
    i.strategy_id = "reconciliation-test";
    i.strategy_version = "1";
    i.universe_id = "U";
    i.universe_version = 1;
    i.symbol = "BTCUSDT";
    i.action = astu::core::SignalAction::Buy;
    i.side = astu::core::PositionSide::Long;
    i.source_periodicity = "M1";
    i.source_bar_time_utc_ms = 1'000;
    i.signal_time_utc_ms = 1'100;
    i.trigger_price = 100.0;
    i.valid_from_utc_ms = 1'000;
    i.expires_utc_ms = 5'000;
    i.quantity_model = "DETERMINISTIC_SIM_V1";
    i.data_generation = 1;
    return request;
}

astu::ipc::SimulationResponse accepted_response(
    const astu::ipc::SimulationRequest& request) {
    astu::ipc::SimulationResponse response;
    response.request_id = request.request_id;
    response.signal_id = request.intent.signal_id;
    response.simulation_order_id =
        astu::execution::deterministic_simulation_order_id(
            request.request_id,
            request.idempotency_key,
            request.intent);
    response.decision_code =
        astu::core::DecisionCode::OrderRoutingDisabled;
    response.accepted_for_simulation = true;
    response.would_increase_exposure = true;
    response.simulated_quantity = 1.0;
    response.simulated_notional = 100.0;
    response.order_routing_enabled = false;
    response.reason = "simulation accepted; routing disabled";
    return response;
}

}  // namespace

int main() {
    using astu::execution::OrderState;
    using astu::execution::SimulationReconciliationType;

    const auto dir = std::filesystem::temp_directory_path() /
        "astu_sim_reconciliation_test";
    std::filesystem::remove_all(dir);
    std::filesystem::create_directories(dir);
    const auto journal_path = dir / "execution_journal.v1.jsonl";

    const auto req = request();
    const auto response = accepted_response(req);
    const auto order_id = response.simulation_order_id;

    {
        auto journal =
            std::make_shared<astu::execution::ExecutionJournal>(
                journal_path, 100);
        astu::execution::SimulationOrderLifecycle lifecycle(journal);
        lifecycle.observe(req, response, 2'000);
        journal->append_simulation_order_intent(req, response, 2'000);
        journal->append(req, response, 2'000);

        REQUIRE(journal->order_state(order_id).has_value());
        REQUIRE(*journal->order_state(order_id) == OrderState::Sizing);
        REQUIRE(journal->order_transition_count() == 4);

        astu::execution::SimulationReconciliationService reconciliation(
            journal);

        REQUIRE(reconciliation.apply(
                    "EV-UNKNOWN",
                    order_id,
                    SimulationReconciliationType::MarkUnknown,
                    0.0,
                    2'100,
                    "simulated acknowledgement state uncertain") ==
                OrderState::UnknownReconcileRequired);

        REQUIRE(reconciliation.apply(
                    "EV-ACK",
                    order_id,
                    SimulationReconciliationType::Acknowledged,
                    0.0,
                    2'200,
                    "simulated authoritative acknowledgement") ==
                OrderState::Acknowledged);

        REQUIRE(reconciliation.apply(
                    "EV-WORKING",
                    order_id,
                    SimulationReconciliationType::Working,
                    0.0,
                    2'300,
                    "simulated authoritative working state") ==
                OrderState::Working);

        REQUIRE(reconciliation.apply(
                    "EV-PARTIAL",
                    order_id,
                    SimulationReconciliationType::PartialFill,
                    0.4,
                    2'400,
                    "simulated authoritative partial fill") ==
                OrderState::Partial);
        REQUIRE(journal->reconciled_filled_quantity(order_id) == 0.4);

        bool decreasing_fill_rejected = false;
        try {
            reconciliation.apply(
                "EV-DECREASE",
                order_id,
                SimulationReconciliationType::PartialFill,
                0.3,
                2'450,
                "invalid decreasing fill");
        } catch (const std::invalid_argument&) {
            decreasing_fill_rejected = true;
        }
        REQUIRE(decreasing_fill_rejected);

        bool duplicate_event_rejected = false;
        try {
            reconciliation.apply(
                "EV-PARTIAL",
                order_id,
                SimulationReconciliationType::PartialFill,
                0.6,
                2'460,
                "duplicate event id");
        } catch (const std::invalid_argument&) {
            duplicate_event_rejected = true;
        }
        REQUIRE(duplicate_event_rejected);

        REQUIRE(reconciliation.apply(
                    "EV-FILLED",
                    order_id,
                    SimulationReconciliationType::Filled,
                    1.0,
                    2'500,
                    "simulated authoritative full fill") ==
                OrderState::Filled);
        REQUIRE(journal->reconciled_filled_quantity(order_id) == 1.0);
        REQUIRE(journal->reconciliation_event_count() == 5);
        REQUIRE(journal->order_transition_count() == 9);

        bool terminal_mutation_rejected = false;
        try {
            reconciliation.apply(
                "EV-CANCEL-AFTER-FILL",
                order_id,
                SimulationReconciliationType::Canceled,
                1.0,
                2'600,
                "invalid terminal mutation");
        } catch (const std::invalid_argument&) {
            terminal_mutation_rejected = true;
        }
        REQUIRE(terminal_mutation_rejected);
    }

    {
        auto journal =
            std::make_shared<astu::execution::ExecutionJournal>(
                journal_path, 100);
        const auto state = journal->order_state(order_id);
        REQUIRE(state.has_value());
        REQUIRE(*state == OrderState::Filled);
        REQUIRE(journal->recovered_order_count() == 1);
        REQUIRE(journal->recovered_order_intent_count() == 1);
        REQUIRE(journal->reconciliation_event_count() == 5);
        REQUIRE(journal->order_transition_count() == 9);
        REQUIRE(journal->reconciled_filled_quantity(order_id) == 1.0);

        const auto intent = journal->simulation_order_intent(order_id);
        REQUIRE(intent.has_value());
        REQUIRE(intent->symbol == "BTCUSDT");
        REQUIRE(intent->quantity == 1.0);
        REQUIRE(intent->notional == 100.0);
    }

    {
        std::ifstream in(journal_path, std::ios::binary);
        const std::string text(
            (std::istreambuf_iterator<char>(in)),
            std::istreambuf_iterator<char>());
        REQUIRE(
            text.find("SIMULATION_RECONCILIATION_EVENT") !=
            std::string::npos);
        REQUIRE(
            text.find("UNKNOWN_RECONCILE_REQUIRED") !=
            std::string::npos);
        REQUIRE(text.find("\"toState\":\"FILLED\"") !=
                std::string::npos);
        REQUIRE(
            text.find("\"exchangeSubmissionAttempted\":false") !=
            std::string::npos);
        REQUIRE(
            text.find("\"exchangeSubmissionAttempted\":true") ==
            std::string::npos);
    }

    {
        const auto bad_path = dir / "bad_reconciliation_journal.jsonl";
        std::filesystem::copy_file(
            journal_path,
            bad_path,
            std::filesystem::copy_options::overwrite_existing);
        std::ofstream out(bad_path, std::ios::binary | std::ios::app);
        out
            << "{"
            << "\"schemaVersion\":1,"
            << "\"eventType\":\"SIMULATION_RECONCILIATION_EVENT\","
            << "\"utcMs\":3000,"
            << "\"eventId\":\"EV-BAD\","
            << "\"simulationOrderId\":\"" << order_id << "\","
            << "\"reconciliationType\":\"CANCELED\","
            << "\"fromState\":\"FILLED\","
            << "\"toState\":\"CANCELED\","
            << "\"transitionSequence\":10,"
            << "\"reconciliationSequence\":6,"
            << "\"orderQuantity\":1,"
            << "\"cumulativeFilledQuantity\":1,"
            << "\"simulationOnly\":true,"
            << "\"exchangeSubmissionAttempted\":false,"
            << "\"detail\":\"invalid terminal transition\""
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
    std::cout << "astu_reconciliation_tests PASS\n";
    return 0;
}
