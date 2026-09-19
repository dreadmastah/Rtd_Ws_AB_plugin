#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <memory>
#include <string>
#include <thread>
#include <utility>

#include "astu/account/live_risk_provider.hpp"
#include "astu/core/contracts.hpp"
#include "astu/execution/execution_journal.hpp"
#include "astu/execution/execution_pipe_server.hpp"
#include "astu/execution/execution_status.hpp"
#include "astu/ipc/simulation_protocol.hpp"
#include "astu/instrument/live_instrument_provider.hpp"
#include "astu/wsrtd/live_status_provider.hpp"

namespace {

astu::core::AccountRiskSnapshot synthetic_risk(
    const astu::core::SignalIntent&) {
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
}

astu::core::DataStatus synthetic_data(
    const astu::core::SignalIntent& intent) {
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
}

}  // namespace

int main(int argc, char** argv) {
#ifdef _WIN32
    bool synthetic = false;
    std::filesystem::path status_dir =
        "CleanRoomR2/stack/runtime/autotrader_status";
    std::uint64_t max_status_age_ms = 5'000;
    std::filesystem::path journal_path =
        "Core/runtime/execution_journal.v1.jsonl";
    std::filesystem::path risk_status_file =
        "Core/runtime/account_risk_status.v1.json";
    std::uint64_t max_risk_status_age_ms = 5'000;
    std::filesystem::path execution_status_file =
        "Core/runtime/execution_status.v1.json";
    std::filesystem::path instrument_status_dir;
    std::uint64_t max_instrument_status_age_ms = 86'400'000;

    if (const char* env = std::getenv("ASTU_STATUS_DIR"); env && *env) {
        status_dir = env;
    }
    if (const char* env = std::getenv("ASTU_EXECUTION_JOURNAL"); env && *env) {
        journal_path = env;
    }
    if (const char* env = std::getenv("ASTU_RISK_STATUS_FILE"); env && *env) {
        risk_status_file = env;
    }
    if (const char* env = std::getenv("ASTU_EXECUTION_STATUS_FILE"); env && *env) {
        execution_status_file = env;
    }
    if (const char* env = std::getenv("ASTU_INSTRUMENT_STATUS_DIR"); env && *env) {
        instrument_status_dir = env;
    }

    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--synthetic") {
            synthetic = true;
        } else if (arg == "--status-dir" && i + 1 < argc) {
            status_dir = argv[++i];
        } else if (arg == "--max-status-age-ms" && i + 1 < argc) {
            max_status_age_ms = std::stoull(argv[++i]);
        } else if (arg == "--journal" && i + 1 < argc) {
            journal_path = argv[++i];
        } else if (arg == "--risk-status-file" && i + 1 < argc) {
            risk_status_file = argv[++i];
        } else if (arg == "--max-risk-status-age-ms" && i + 1 < argc) {
            max_risk_status_age_ms = std::stoull(argv[++i]);
        } else if (arg == "--execution-status-file" && i + 1 < argc) {
            execution_status_file = argv[++i];
        } else if (arg == "--instrument-status-dir" && i + 1 < argc) {
            instrument_status_dir = argv[++i];
        } else if (arg == "--max-instrument-status-age-ms" && i + 1 < argc) {
            max_instrument_status_age_ms = std::stoull(argv[++i]);
        } else {
            std::cerr << "unknown/missing argument: " << arg << "\n";
            return 2;
        }
    }

    astu::ipc::SimulationDispatcher::DataProvider data_provider;
    if (synthetic) {
        data_provider = synthetic_data;
    } else {
        astu::wsrtd::LiveStatusProvider provider(status_dir, max_status_age_ms);
        data_provider = [provider](const astu::core::SignalIntent& intent) {
            return provider(intent);
        };
    }

    astu::ipc::SimulationDispatcher::RiskProvider risk_provider;
    if (synthetic) {
        risk_provider = synthetic_risk;
    } else {
        astu::account::LiveRiskProvider provider(
            risk_status_file,
            max_risk_status_age_ms);
        risk_provider = [provider](const astu::core::SignalIntent& intent) {
            return provider(intent);
        };
    }

    astu::ipc::SimulationDispatcher::InstrumentProvider instrument_provider;
    if (!instrument_status_dir.empty()) {
        astu::instrument::LiveInstrumentProvider provider(
            instrument_status_dir,
            max_instrument_status_age_ms);
        instrument_provider =
            [provider](const astu::core::SignalIntent& intent) {
                return provider(intent);
            };
    }

    auto journal = std::make_shared<astu::execution::ExecutionJournal>(
        journal_path,
        100'000);

    const std::string data_provider_name =
        synthetic ? "SYNTHETIC" : "WSRTD_LIVE_STATUS";
    const std::string risk_provider_name =
        synthetic ? "SYNTHETIC" : "FILE_BACKED_RECONCILED_STATUS";

    auto execution_status =
        std::make_shared<astu::execution::ExecutionStatusPublisher>(
            execution_status_file,
            data_provider_name,
            risk_provider_name,
            journal_path.string());
    execution_status->publish();

    astu::ipc::SimulationDispatcher dispatcher(
        std::move(data_provider),
        std::move(risk_provider),
        4096,
        [journal](const std::string& key) {
            return journal->accept_idempotency_key(key);
        },
        [journal, execution_status](
            const astu::ipc::SimulationRequest& request,
            const astu::ipc::SimulationResponse& response,
            std::int64_t utc_ms) {
            journal->append(request, response, utc_ms);
            execution_status->record_response(response);
        },
        std::move(instrument_provider));

    execution_status->set_ready(true, true);
    execution_status->publish();

    std::jthread heartbeat([execution_status](std::stop_token stop) {
        while (!stop.stop_requested()) {
            try {
                execution_status->publish();
            } catch (const std::exception& exc) {
                std::cerr << "execution-status publish failed: "
                          << exc.what() << "\n";
            }
            for (int i = 0; i < 10 && !stop.stop_requested(); ++i) {
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
            }
        }
    });

    astu::execution::ExecutionPipeServer server(std::move(dispatcher));
    std::wcout << L"Execution simulation pipe host listening on "
               << astu::ipc::kExecutionPipeName << L"\n";
    std::cout << "ORDER_ROUTING_ENABLED=false\n";
    std::cout << "DATA_PROVIDER=" << data_provider_name << "\n";
    if (!synthetic) {
        std::cout << "STATUS_DIR=" << status_dir.string() << "\n";
        std::cout << "MAX_STATUS_AGE_MS=" << max_status_age_ms << "\n";
    }
    std::cout << "RISK_PROVIDER=" << risk_provider_name << "\n";
    if (!synthetic) {
        std::cout << "RISK_STATUS_FILE=" << risk_status_file.string() << "\n";
        std::cout << "MAX_RISK_STATUS_AGE_MS=" << max_risk_status_age_ms << "\n";
    }
    std::cout << "EXECUTION_JOURNAL=" << journal_path.string() << "\n";
    std::cout << "EXECUTION_STATUS_FILE=" << execution_status_file.string() << "\n";
    if (!instrument_status_dir.empty()) {
        std::cout << "INSTRUMENT_PROVIDER=FILE_BACKED_PUBLIC_FILTERS\n";
        std::cout << "INSTRUMENT_STATUS_DIR=" << instrument_status_dir.string() << "\n";
        std::cout << "MAX_INSTRUMENT_STATUS_AGE_MS="
                  << max_instrument_status_age_ms << "\n";
    } else {
        std::cout << "INSTRUMENT_PROVIDER=LEGACY_SIMULATION_SIZING\n";
    }
    std::cout << "REPLAY_KEYS_LOADED=" << journal->replay_size() << "\n";

    for (;;) {
        try {
            server.serve_once();
        } catch (const std::exception& exc) {
            execution_status->set_degraded(
                std::string("pipe-host request failed: ") + exc.what());
            try {
                execution_status->publish();
            } catch (...) {
            }
            std::cerr << "pipe-host request failed: " << exc.what() << "\n";
            execution_status->set_ready(true, true);
        }
    }
#else
    (void)argc;
    (void)argv;
    std::cerr << "Execution Named Pipe host requires Windows.\n";
    return 2;
#endif
}
