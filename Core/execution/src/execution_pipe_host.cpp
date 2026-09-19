#include <iostream>

#include "astu/core/contracts.hpp"
#include "astu/execution/execution_pipe_server.hpp"
#include "astu/ipc/simulation_protocol.hpp"

int main() {
#ifdef _WIN32
    astu::ipc::SimulationDispatcher dispatcher(
        [](const astu::core::SignalIntent& intent) {
            astu::core::DataStatus data;
            data.source = "PIPE_SIM_PROVIDER";
            data.symbol = intent.symbol;
            data.live = true;
            data.fresh = true;
            data.cache_ready = true;
            data.identity_ready = true;
            data.universe_id = intent.universe_id;
            data.universe_version = intent.universe_version;
            data.universe_hash = "simulation-provider";
            data.data_generation = intent.data_generation;
            data.generation_kind = "PIPE_SIM_GENERATION";
            data.detail = "deterministic pipe-host simulation provider";
            return data;
        },
        [](const astu::core::SignalIntent&) {
            astu::core::AccountRiskSnapshot risk;
            risk.reconciled = true;
            risk.risk_state = astu::core::RiskState::Normal;
            risk.risk_capital = 10'000.0;
            risk.available_balance = 10'000.0;
            risk.gross_notional = 0.0;
            risk.max_gross_notional = 100'000.0;
            risk.open_positions = 0;
            risk.max_open_positions = 10;
            return risk;
        });

    astu::execution::ExecutionPipeServer server(std::move(dispatcher));
    std::cout << "Execution simulation pipe host listening on "
              << "\\.\pipe\AstuExecutionSim.v1" << "\n";
    std::cout << "ORDER_ROUTING_ENABLED=false\n";

    for (;;) {
        try {
            server.serve_once();
        } catch (const std::exception& exc) {
            std::cerr << "pipe-host request failed: " << exc.what() << "\n";
        }
    }
#else
    std::cerr << "Execution Named Pipe host requires Windows.\n";
    return 2;
#endif
}
