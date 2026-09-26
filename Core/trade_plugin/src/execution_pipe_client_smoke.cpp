#include <chrono>
#include <cstdint>
#include <iostream>
#include <string>

#include "astu/ipc/simulation_protocol.hpp"
#include "astu/trade/execution_pipe_client.hpp"

int main(int argc, char** argv) {
#ifdef _WIN32
    bool expect_duplicate = false;
    std::string case_id = "1";
    std::string symbol = "BTCUSDT";
    auto side = astu::core::PositionSide::Long;
    auto expected = astu::core::DecisionCode::OrderRoutingDisabled;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--expect-duplicate") {
            expect_duplicate = true;
        } else if (arg == "--case-id" && i + 1 < argc) {
            case_id = argv[++i];
        } else if (arg == "--expect" && i + 1 < argc) {
            expected = astu::ipc::decision_from_string(argv[++i]);
        } else if (arg == "--symbol" && i + 1 < argc) {
            symbol = argv[++i];
        } else if (arg == "--side" && i + 1 < argc) {
            side = astu::ipc::side_from_string(argv[++i]);
        } else {
            std::cerr << "unknown argument: " << arg << "\n";
            return 2;
        }
    }
    const auto now = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();

    astu::ipc::SimulationRequest request;
    request.request_id = "PIPE-SMOKE-REQ-" + case_id;
    request.idempotency_key = "PIPE-SMOKE-IDEMPOTENCY-" + case_id;

    auto& intent = request.intent;
    intent.signal_id = "PIPE-SMOKE-SIGNAL-" + case_id;
    intent.analysis_run_id = "PIPE-SMOKE-AA-" + case_id;
    intent.strategy_id = "pipe-smoke";
    intent.strategy_version = "1";
    intent.universe_id = "wsrtd-r2-bootstrap";
    intent.universe_version = 1;
    intent.symbol = symbol;
    intent.action = astu::core::SignalAction::Buy;
    intent.side = side;
    intent.source_periodicity = "M1";
    intent.source_bar_time_utc_ms = now - 60'000;
    intent.signal_time_utc_ms = now;
    intent.trigger_price = 100'000.0;
    intent.valid_from_utc_ms = now - 1'000;
    intent.expires_utc_ms = now + 30'000;
    intent.quantity_model = "SYNTHETIC_TEST_ONLY";
    intent.priority_score = 0.0;
    intent.data_generation = static_cast<std::uint64_t>(now - 60'000);

    try {
        astu::trade::ExecutionPipeClient client;
        const auto response = client.send(request);
        std::cout << "requestId=" << response.request_id << "\n";
        std::cout << "signalId=" << response.signal_id << "\n";
        std::cout << "simulationOrderId=" << response.simulation_order_id << "\n";
        std::cout << "decision=" << astu::ipc::decision_to_string(response.decision_code) << "\n";
        std::cout << "acceptedForSimulation="
                  << (response.accepted_for_simulation ? "true" : "false") << "\n";
        std::cout << "orderRoutingEnabled="
                  << (response.order_routing_enabled ? "true" : "false") << "\n";
        std::cout << "simulatedQuantity=" << response.simulated_quantity << "\n";
        std::cout << "simulatedNotional=" << response.simulated_notional << "\n";
        std::cout << "reason=" << response.reason << "\n";
        const auto effective_expected = expect_duplicate
            ? astu::core::DecisionCode::DuplicateRequest
            : expected;
        return response.decision_code == effective_expected ? 0 : 1;
    } catch (const std::exception& exc) {
        std::cerr << "pipe smoke failed: " << exc.what() << "\n";
        return 2;
    }
#else
    (void)argc;
    (void)argv;
    std::cerr << "Execution Named Pipe smoke client requires Windows.\n";
    return 2;
#endif
}
