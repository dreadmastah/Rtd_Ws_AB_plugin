#include <filesystem>
#include <iostream>
#include <memory>

#include "astu/execution/authoritative_order_convergence.hpp"
#include "astu/execution/binance_usdm_testnet_order_snapshot.hpp"

namespace {

astu::ipc::SimulationRequest make_request() {
    astu::ipc::SimulationRequest req;
    req.request_id = "REQ-QRY-1";
    req.idempotency_key = "IDEMP-QRY-1";
    req.intent.signal_id = "SIG-QRY-1";
    req.intent.strategy_id = "test";
    req.intent.strategy_version = "1";
    req.intent.symbol = "BTCUSDT";
    req.intent.action = astu::core::SignalAction::Buy;
    req.intent.side = astu::core::PositionSide::Long;
    req.intent.trigger_price = 100.0;
    return req;
}

astu::ipc::SimulationResponse make_response() {
    astu::ipc::SimulationResponse out;
    out.request_id = "REQ-QRY-1";
    out.signal_id = "SIG-QRY-1";
    out.simulation_order_id =
        "SIMORD-0123456789abcdef0123456789abcdef";
    out.decision_code =
        astu::core::DecisionCode::OrderRoutingDisabled;
    out.accepted_for_simulation = true;
    out.would_increase_exposure = true;
    out.simulated_quantity = 0.102;
    out.simulated_notional = 10.2;
    return out;
}

}  // namespace

int main() {
    using namespace astu::execution;

    const auto query = build_testnet_order_query_params(
        "BTCUSDT", "ASTU-client-1", 123456789);
    if (query.find("symbol=BTCUSDT") == std::string::npos ||
        query.find("origClientOrderId=ASTU-client-1") ==
            std::string::npos ||
        query.find("timestamp=123456789") ==
            std::string::npos) {
        return 1;
    }

    if (binance_testnet_status_to_order_state(
            "NEW", 0.0, 1.0) != OrderState::Working ||
        binance_testnet_status_to_order_state(
            "PARTIALLY_FILLED", 0.4, 1.0) !=
            OrderState::Partial ||
        binance_testnet_status_to_order_state(
            "FILLED", 1.0, 1.0) != OrderState::Filled ||
        binance_testnet_status_to_order_state(
            "CANCELED", 0.4, 1.0) !=
            OrderState::Canceled ||
        binance_testnet_status_to_order_state(
            "REJECTED", 0.0, 1.0) !=
            OrderState::Rejected ||
        binance_testnet_status_to_order_state(
            "FILLED", 0.5, 1.0) !=
            OrderState::UnknownReconcileRequired) {
        return 2;
    }

    const auto root =
        std::filesystem::temp_directory_path() /
        "astu_testnet_order_snapshot_tests";
    std::filesystem::remove_all(root);
    std::filesystem::create_directories(root);
    auto journal = std::make_shared<ExecutionJournal>(
        root / "journal.jsonl");
    auto req = make_request();
    auto resp = make_response();
    journal->append_order_transition(
        req, resp.simulation_order_id,
        OrderState::IntentReceived, 1, "intent");
    journal->append_order_transition(
        req, resp.simulation_order_id,
        OrderState::Validating, 2, "validating");
    journal->append_order_transition(
        req, resp.simulation_order_id,
        OrderState::RiskApproved, 3, "risk");
    journal->append_order_transition(
        req, resp.simulation_order_id,
        OrderState::Sizing, 4, "sizing");
    journal->append_simulation_order_intent(req, resp, 5);

    const auto expected_client =
        deterministic_testnet_client_order_id(
            resp.simulation_order_id);

    BinanceUsdmTestnetOrderSnapshotProvider filled(
        journal,
        [expected_client](
            const std::string& symbol,
            const std::string& client,
            std::uint64_t) {
            TestnetOrderQueryResult result;
            result.ready = true;
            result.found = true;
            result.symbol = symbol;
            result.exchange_order_id = "123";
            result.client_order_id = client;
            result.exchange_status = "FILLED";
            result.original_quantity = 0.102;
            result.cumulative_filled_quantity = 0.102;
            result.detail = "fixture";
            if (client != expected_client) {
                result.ready = false;
            }
            return result;
        });
    const auto snapshot = filled(resp.simulation_order_id);
    if (!snapshot.ready ||
        snapshot.state != OrderState::Filled ||
        snapshot.cumulative_filled_quantity != 0.102 ||
        snapshot.source !=
            "BINANCE_USDM_TESTNET_REST_ORDER_QUERY") {
        return 3;
    }

    journal->append_order_transition(
        req,
        resp.simulation_order_id,
        OrderState::Submitting,
        6,
        "testnet submitting",
        false,
        true,
        "BINANCE_USDM_TESTNET");
    journal->append_order_transition(
        req,
        resp.simulation_order_id,
        OrderState::UnknownReconcileRequired,
        7,
        "ambiguous submission",
        false,
        true,
        "BINANCE_USDM_TESTNET");
    if (!AuthoritativeOrderConvergence::apply_testnet_snapshot(
            journal,
            resp.simulation_order_id,
            snapshot,
            8) ||
        journal->order_state(resp.simulation_order_id) !=
            OrderState::Filled ||
        std::fabs(
            journal->reconciled_filled_quantity(
                resp.simulation_order_id) -
            0.102) > 1e-12) {
        return 4;
    }

    auto replay = std::make_shared<ExecutionJournal>(
        root / "journal.jsonl");
    if (replay->order_state(resp.simulation_order_id) !=
            OrderState::Filled ||
        std::fabs(
            replay->reconciled_filled_quantity(
                resp.simulation_order_id) -
            0.102) > 1e-12) {
        return 5;
    }

    BinanceUsdmTestnetOrderSnapshotProvider absent(
        journal,
        [](const std::string& symbol,
           const std::string& client,
           std::uint64_t) {
            TestnetOrderQueryResult result;
            result.ready = true;
            result.found = false;
            result.symbol = symbol;
            result.client_order_id = client;
            result.exchange_code = -2013;
            result.detail = "Order does not exist.";
            return result;
        });
    const auto missing = absent(resp.simulation_order_id);
    if (missing.ready ||
        missing.state !=
            OrderState::UnknownReconcileRequired) {
        return 6;
    }

    BinanceUsdmTestnetOrderSnapshotProvider mismatch(
        journal,
        [](const std::string& symbol,
           const std::string& client,
           std::uint64_t) {
            TestnetOrderQueryResult result;
            result.ready = true;
            result.found = true;
            result.symbol = symbol;
            result.client_order_id = client;
            result.exchange_order_id = "124";
            result.exchange_status = "NEW";
            result.original_quantity = 99.0;
            result.cumulative_filled_quantity = 0.0;
            result.detail = "fixture";
            return result;
        });
    if (mismatch(resp.simulation_order_id).ready) {
        return 7;
    }

    std::error_code ec;
    std::filesystem::remove_all(root, ec);
    std::cout << "TESTNET_ORDER_SNAPSHOT_TESTS=PASS\n";
    return 0;
}
