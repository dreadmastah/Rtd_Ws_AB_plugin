#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <string>

#include "astu/execution/binance_usdm_testnet_order_gateway.hpp"
#include "astu/execution/execution_journal.hpp"
#include "astu/execution/testnet_order_router.hpp"

namespace {

astu::ipc::SimulationRequest request() {
    astu::ipc::SimulationRequest req;
    req.request_id = "REQ-TESTNET-1";
    req.idempotency_key = "IDEMP-TESTNET-1";
    req.intent.signal_id = "SIG-TESTNET-1";
    req.intent.analysis_run_id = "AA-TESTNET-1";
    req.intent.strategy_id = "testnet-router";
    req.intent.strategy_version = "1";
    req.intent.universe_id = "wsrtd-r2-bootstrap";
    req.intent.universe_version = 1;
    req.intent.symbol = "BTCUSDT";
    req.intent.action = astu::core::SignalAction::Buy;
    req.intent.side = astu::core::PositionSide::Long;
    req.intent.source_periodicity = "M1";
    req.intent.source_bar_time_utc_ms = 1;
    req.intent.signal_time_utc_ms = 2;
    req.intent.trigger_price = 100.0;
    req.intent.valid_from_utc_ms = 1;
    req.intent.expires_utc_ms = 10'000;
    req.intent.quantity_model = "TEST";
    req.intent.data_generation = 1;
    return req;
}

astu::ipc::SimulationResponse response() {
    astu::ipc::SimulationResponse out;
    out.request_id = "REQ-TESTNET-1";
    out.signal_id = "SIG-TESTNET-1";
    out.simulation_order_id =
        "SIMORD-0123456789abcdef0123456789abcdef";
    out.decision_code =
        astu::core::DecisionCode::OrderRoutingDisabled;
    out.accepted_for_simulation = true;
    out.would_increase_exposure = true;
    out.simulated_quantity = 0.102;
    out.simulated_notional = 10.2;
    out.order_routing_enabled = false;
    out.execution_environment = "SIMULATION_ONLY";
    out.reason = "simulation passed";
    return out;
}

void seed_sizing(
    const std::shared_ptr<astu::execution::ExecutionJournal>& journal,
    const astu::ipc::SimulationRequest& req,
    const astu::ipc::SimulationResponse& resp) {
    journal->append_order_transition(
        req, resp.simulation_order_id,
        astu::execution::OrderState::IntentReceived, 1000, "intent");
    journal->append_order_transition(
        req, resp.simulation_order_id,
        astu::execution::OrderState::Validating, 1001, "validate");
    journal->append_order_transition(
        req, resp.simulation_order_id,
        astu::execution::OrderState::RiskApproved, 1002, "risk");
    journal->append_order_transition(
        req, resp.simulation_order_id,
        astu::execution::OrderState::Sizing, 1003, "sizing");
}

bool expect_state(
    const std::shared_ptr<astu::execution::ExecutionJournal>& journal,
    const std::string& order_id,
    astu::execution::OrderState expected) {
    const auto state = journal->order_state(order_id);
    if (!state.has_value() || *state != expected) {
        std::cerr << "unexpected order state\n";
        return false;
    }
    return true;
}

}  // namespace

int main() {
    using namespace astu::execution;

    auto long_buy = request().intent;
    long_buy.action = astu::core::SignalAction::Buy;
    long_buy.side = astu::core::PositionSide::Long;
    if (testnet_exchange_side(long_buy) != "BUY" ||
        testnet_reduce_only(long_buy)) {
        return 1;
    }
    long_buy.action = astu::core::SignalAction::ScaleOut;
    if (testnet_exchange_side(long_buy) != "SELL" ||
        !testnet_reduce_only(long_buy)) {
        return 2;
    }
    long_buy.side = astu::core::PositionSide::Short;
    long_buy.action = astu::core::SignalAction::ScaleIn;
    if (testnet_exchange_side(long_buy) != "SELL" ||
        testnet_reduce_only(long_buy)) {
        return 3;
    }
    long_buy.action = astu::core::SignalAction::ScaleOut;
    if (testnet_exchange_side(long_buy) != "BUY" ||
        !testnet_reduce_only(long_buy)) {
        return 4;
    }

    const auto client_id =
        deterministic_testnet_client_order_id(
            "SIMORD-0123456789abcdef0123456789abcdef");
    if (client_id.size() > 36 ||
        client_id.rfind("ASTU-", 0) != 0) {
        return 5;
    }

    const auto params = build_testnet_order_params(
        TestnetOrderRequest{
            "BTCUSDT", "BUY", 0.102, client_id, false},
        123456789);
    if (params.find("symbol=BTCUSDT") == std::string::npos ||
        params.find("type=MARKET") == std::string::npos ||
        params.find("quantity=0.102") == std::string::npos ||
        params.find("reduceOnly=true") != std::string::npos ||
        params.find("timestamp=123456789") == std::string::npos) {
        return 6;
    }

#ifdef _WIN32
    const auto digest = hmac_sha256_hex_for_test(
        "key",
        "The quick brown fox jumps over the lazy dog");
    if (digest !=
        "f7bc83f430538424b13298e6aa6fb143ef4d59a14946175997479dbc2d1a3cd8") {
        std::cerr << "HMAC-SHA256 mismatch\n";
        return 7;
    }
#endif

    const auto root =
        std::filesystem::temp_directory_path() /
        "astu_testnet_order_router_tests";
    std::filesystem::create_directories(root);

    {
        auto journal = std::make_shared<ExecutionJournal>(
            root / "ack.jsonl");
        auto req = request();
        auto resp = response();
        seed_sizing(journal, req, resp);

        TestnetOrderRouter router(
            journal,
            [](const TestnetOrderRequest& order, std::uint64_t) {
                TestnetOrderResult result;
                result.outcome = TestnetSubmitOutcome::Acknowledged;
                result.client_order_id = order.client_order_id;
                result.exchange_order_id = "987654321";
                result.exchange_status = "NEW";
                result.detail = "fixture acknowledged";
                return result;
            });
        router.route(req, resp, 2000);
        if (resp.decision_code !=
                astu::core::DecisionCode::TestnetSubmitted ||
            !resp.order_routing_enabled ||
            resp.execution_environment !=
                "BINANCE_USDM_TESTNET" ||
            resp.exchange_order_id != "987654321" ||
            journal->testnet_submission_attempt_count() != 1 ||
            !expect_state(
                journal,
                resp.simulation_order_id,
                OrderState::Acknowledged)) {
            return 8;
        }

        auto replay = std::make_shared<ExecutionJournal>(
            root / "ack.jsonl");
        if (replay->testnet_submission_attempt_count() != 1 ||
            !expect_state(
                replay,
                resp.simulation_order_id,
                OrderState::Acknowledged)) {
            return 9;
        }
    }

    {
        auto journal = std::make_shared<ExecutionJournal>(
            root / "unknown.jsonl");
        auto req = request();
        req.request_id = "REQ-TESTNET-UNKNOWN";
        req.idempotency_key = "IDEMP-TESTNET-UNKNOWN";
        req.intent.signal_id = "SIG-TESTNET-UNKNOWN";
        auto resp = response();
        resp.request_id = req.request_id;
        resp.signal_id = req.intent.signal_id;
        resp.simulation_order_id =
            "SIMORD-fedcba9876543210fedcba9876543210";
        seed_sizing(journal, req, resp);

        TestnetOrderRouter router(
            journal,
            [](const TestnetOrderRequest& order, std::uint64_t) {
                TestnetOrderResult result;
                result.outcome = TestnetSubmitOutcome::Unknown;
                result.client_order_id = order.client_order_id;
                result.detail = "fixture timeout";
                return result;
            });
        router.route(req, resp, 3000);
        if (resp.decision_code !=
                astu::core::DecisionCode::TestnetUnknown ||
            !expect_state(
                journal,
                resp.simulation_order_id,
                OrderState::UnknownReconcileRequired)) {
            return 10;
        }
    }

    std::error_code ec;
    std::filesystem::remove_all(root, ec);
    std::cout << "TESTNET_ORDER_ROUTER_TESTS=PASS\n";
    return 0;
}
