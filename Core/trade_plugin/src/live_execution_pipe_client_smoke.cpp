#include <chrono>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <string>

#include "astu/core/contracts.hpp"
#include "astu/trade/execution_pipe_client.hpp"
#include "astu/trade/signal_intent_builder.hpp"
#include "astu/wsrtd/live_status_provider.hpp"

int main(int argc, char** argv) {
#ifdef _WIN32
    std::filesystem::path status_dir =
        "CleanRoomR2/stack/runtime/autotrader_status";
    std::string symbol = "BTCUSDT";

    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--status-dir" && i + 1 < argc) {
            status_dir = argv[++i];
        } else if (arg == "--symbol" && i + 1 < argc) {
            symbol = argv[++i];
        } else {
            std::cerr << "unknown/missing argument: " << arg << "\n";
            return 2;
        }
    }

    const auto now = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();

    astu::core::SignalIntent seed;
    seed.signal_id = "LIVE-PIPE-SMOKE-SIGNAL-1";
    seed.analysis_run_id = "LIVE-PIPE-SMOKE-AA-1";
    seed.strategy_id = "live-pipe-smoke";
    seed.strategy_version = "1";
    seed.symbol = symbol;
    seed.action = astu::core::SignalAction::Buy;
    seed.side = astu::core::PositionSide::Long;
    seed.source_periodicity = "M1";
    seed.source_bar_time_utc_ms = now - 60'000;
    seed.signal_time_utc_ms = now;
    seed.trigger_price = 100'000.0;
    seed.valid_from_utc_ms = now - 1'000;
    seed.expires_utc_ms = now + 30'000;
    seed.quantity_model = "SYNTHETIC_TEST_ONLY";
    seed.priority_score = 0.0;

    astu::wsrtd::LiveStatusProvider status_provider(status_dir, 5'000);
    const auto data = status_provider(seed);
    if (!data.live || !data.fresh || !data.cache_ready || !data.identity_ready) {
        std::cerr << "live DataStatus not ready: " << data.detail << "\n";
        return 3;
    }

    astu::ipc::SimulationRequest request;
    request.request_id = "LIVE-PIPE-SMOKE-REQ-1";
    request.idempotency_key = "LIVE-PIPE-SMOKE-IDEMPOTENCY-1";
    request.intent = astu::trade::SignalIntentBuilder(seed)
                         .bind_data_identity(data)
                         .build();

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
        std::cout << "reason=" << response.reason << "\n";
        return response.decision_code == astu::core::DecisionCode::OrderRoutingDisabled ? 0 : 1;
    } catch (const std::exception& exc) {
        std::cerr << "live pipe smoke failed: " << exc.what() << "\n";
        return 4;
    }
#else
    (void)argc;
    (void)argv;
    std::cerr << "Live Execution Named Pipe smoke client requires Windows.\n";
    return 2;
#endif
}
