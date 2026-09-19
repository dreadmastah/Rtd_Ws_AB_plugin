#include <chrono>
#include <cstdint>
#include <iostream>
#include <string>

#include "astu/ipc/simulation_protocol.hpp"
#include "astu/trade/execution_pipe_client.hpp"

int main() {
#ifdef _WIN32
    const auto now = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();

    astu::ipc::SimulationRequest request;
    request.request_id = "PIPE-SMOKE-REQ-1";
    request.idempotency_key = "PIPE-SMOKE-IDEMPOTENCY-1";

    auto& intent = request.intent;
    intent.signal_id = "PIPE-SMOKE-SIGNAL-1";
    intent.analysis_run_id = "PIPE-SMOKE-AA-1";
    intent.strategy_id = "pipe-smoke";
    intent.strategy_version = "1";
    intent.universe_id = "wsrtd-r2-bootstrap";
    intent.universe_version = 1;
    intent.symbol = "BTCUSDT";
    intent.action = astu::core::SignalAction::Buy;
    intent.side = astu::core::PositionSide::Long;
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
        std::cout << "decision=" << astu::ipc::decision_to_string(response.decision_code) << "\n";
        std::cout << "acceptedForSimulation="
                  << (response.accepted_for_simulation ? "true" : "false") << "\n";
        std::cout << "orderRoutingEnabled="
                  << (response.order_routing_enabled ? "true" : "false") << "\n";
        std::cout << "simulatedQuantity=" << response.simulated_quantity << "\n";
        std::cout << "reason=" << response.reason << "\n";
        return response.decision_code == astu::core::DecisionCode::OrderRoutingDisabled ? 0 : 1;
    } catch (const std::exception& exc) {
        std::cerr << "pipe smoke failed: " << exc.what() << "\n";
        return 2;
    }
#else
    std::cerr << "Execution Named Pipe smoke client requires Windows.\n";
    return 2;
#endif
}
