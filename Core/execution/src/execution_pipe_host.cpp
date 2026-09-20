#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <memory>
#include <string>
#include <thread>
#include <utility>

#include "astu/account/live_position_provider.hpp"
#include "astu/account/live_risk_provider.hpp"
#include "astu/core/contracts.hpp"
#include "astu/execution/authoritative_order_snapshot.hpp"
#include "astu/execution/execution_journal.hpp"
#include "astu/execution/execution_pipe_server.hpp"
#include "astu/execution/execution_status.hpp"
#include "astu/execution/reconciliation_pipe_server.hpp"
#include "astu/execution/runtime_order_reconciler.hpp"
#include "astu/execution/simulation_order_lifecycle.hpp"
#include "astu/execution/startup_order_reconciler.hpp"
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

std::int64_t utc_now_ms() {
    const auto now = std::chrono::system_clock::now().time_since_epoch();
    return std::chrono::duration_cast<std::chrono::milliseconds>(now).count();
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
    std::filesystem::path position_status_dir;
    std::uint64_t max_position_status_age_ms = 7'000;
    std::filesystem::path order_snapshot_dir;
    std::uint64_t max_order_snapshot_age_ms = 7'000;
    std::uint64_t order_reconcile_interval_ms = 2'000;

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
    if (const char* env = std::getenv("ASTU_POSITION_STATUS_DIR"); env && *env) {
        position_status_dir = env;
    }
    if (const char* env = std::getenv("ASTU_ORDER_SNAPSHOT_DIR"); env && *env) {
        order_snapshot_dir = env;
    }
    if (const char* env = std::getenv("ASTU_ORDER_RECONCILE_INTERVAL_MS");
        env && *env) {
        order_reconcile_interval_ms = std::stoull(env);
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
        } else if (arg == "--position-status-dir" && i + 1 < argc) {
            position_status_dir = argv[++i];
        } else if (arg == "--max-position-status-age-ms" && i + 1 < argc) {
            max_position_status_age_ms = std::stoull(argv[++i]);
        } else if (arg == "--order-snapshot-dir" && i + 1 < argc) {
            order_snapshot_dir = argv[++i];
        } else if (arg == "--max-order-snapshot-age-ms" && i + 1 < argc) {
            max_order_snapshot_age_ms = std::stoull(argv[++i]);
        } else if (arg == "--order-reconcile-interval-ms" && i + 1 < argc) {
            order_reconcile_interval_ms = std::stoull(argv[++i]);
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

    astu::ipc::SimulationDispatcher::PositionProvider position_provider;
    if (!position_status_dir.empty()) {
        astu::account::LivePositionProvider provider(
            position_status_dir,
            max_position_status_age_ms);
        position_provider =
            [provider](const astu::core::SignalIntent& intent) {
                return provider(intent);
            };
    }

    auto journal = std::make_shared<astu::execution::ExecutionJournal>(
        journal_path,
        100'000);
    const auto recovered_orders_at_startup =
        journal->recovered_order_count();
    const auto recovered_reconciliation_events_at_startup =
        journal->reconciliation_event_count();

    astu::execution::StartupOrderReconciliationReport
        startup_order_report;
    std::shared_ptr<
        astu::execution::FileBackedSimulationOrderSnapshotProvider>
        order_snapshot_provider;
    const bool startup_order_snapshot_required =
        !order_snapshot_dir.empty();
    const std::string startup_order_snapshot_provider_name =
        startup_order_snapshot_required
            ? "FILE_BACKED_AUTHORITATIVE_SIMULATION_ORDER_STATE"
            : "DISABLED";
    if (startup_order_snapshot_required) {
        order_snapshot_provider = std::make_shared<
            astu::execution::FileBackedSimulationOrderSnapshotProvider>(
                order_snapshot_dir,
                max_order_snapshot_age_ms);
        startup_order_report =
            astu::execution::StartupOrderReconciler::reconcile(
                journal,
                *order_snapshot_provider,
                utc_now_ms());
    } else {
        startup_order_report.tracked_orders =
            static_cast<std::uint64_t>(
                journal->recovered_order_count());
    }

    auto order_lifecycle =
        std::make_shared<astu::execution::SimulationOrderLifecycle>(journal);

    const std::string data_provider_name =
        synthetic ? "SYNTHETIC" : "WSRTD_LIVE_STATUS";
    const std::string risk_provider_name =
        synthetic ? "SYNTHETIC" : "FILE_BACKED_RECONCILED_STATUS";
    const std::string instrument_provider_name =
        instrument_status_dir.empty()
            ? "LEGACY_SIMULATION_SIZING"
            : "FILE_BACKED_PUBLIC_FILTERS";
    const bool instrument_rules_required = !instrument_status_dir.empty();
    const std::string position_provider_name =
        position_status_dir.empty()
            ? "NONE"
            : "FILE_BACKED_RECONCILED_POSITIONS";

    auto execution_status =
        std::make_shared<astu::execution::ExecutionStatusPublisher>(
            execution_status_file,
            data_provider_name,
            risk_provider_name,
            instrument_provider_name,
            instrument_rules_required,
            position_provider_name,
            journal_path.string());
    execution_status->set_order_state_metrics(
        recovered_orders_at_startup,
        journal->recovered_order_count(),
        journal->order_transition_count(),
        recovered_reconciliation_events_at_startup,
        journal->reconciliation_event_count());
    execution_status->set_startup_order_reconciliation(
        startup_order_snapshot_provider_name,
        startup_order_snapshot_required,
        startup_order_report.tracked_orders,
        startup_order_report.matched_orders,
        startup_order_report.marked_unknown,
        startup_order_report.unresolved_orders);
    execution_status->set_runtime_order_reconciliation(
        startup_order_snapshot_required,
        0,
        0,
        0,
        0,
        0,
        startup_order_report.unresolved_orders,
        0,
        0,
        0,
        0);
    execution_status->publish();

    std::jthread runtime_order_reconciliation_thread;
    if (order_snapshot_provider) {
        runtime_order_reconciliation_thread = std::jthread(
            [journal,
             execution_status,
             order_snapshot_provider,
             order_reconcile_interval_ms,
             recovered_orders_at_startup,
             recovered_reconciliation_events_at_startup](
                std::stop_token stop) {
                std::uint64_t sweep_count = 0;
                std::uint64_t sweep_errors = 0;
                astu::execution::RuntimeOrderReconciliationReport
                    last_report;

                while (!stop.stop_requested()) {
                    const auto sweep_utc_ms =
                        static_cast<std::uint64_t>(utc_now_ms());
                    try {
                        last_report =
                            astu::execution::RuntimeOrderReconciler::sweep(
                                journal,
                                *order_snapshot_provider,
                                static_cast<std::int64_t>(
                                    sweep_utc_ms));
                        ++sweep_count;
                        execution_status->set_runtime_order_reconciliation(
                            true,
                            sweep_utc_ms,
                            sweep_count,
                            last_report.tracked_nonterminal_orders,
                            last_report.matched_orders,
                            last_report.marked_unknown,
                            last_report.unresolved_orders,
                            last_report.source_unavailable_orders,
                            last_report.terminal_orders_skipped,
                            last_report.concurrent_state_changes,
                            sweep_errors);
                        execution_status->set_order_state_metrics(
                            recovered_orders_at_startup,
                            journal->recovered_order_count(),
                            journal->order_transition_count(),
                            recovered_reconciliation_events_at_startup,
                            journal->reconciliation_event_count());
                        execution_status->publish();
                    } catch (const std::exception& exc) {
                        ++sweep_errors;
                        execution_status->set_runtime_order_reconciliation(
                            true,
                            sweep_utc_ms,
                            sweep_count,
                            last_report.tracked_nonterminal_orders,
                            last_report.matched_orders,
                            last_report.marked_unknown,
                            last_report.unresolved_orders,
                            last_report.source_unavailable_orders,
                            last_report.terminal_orders_skipped,
                            last_report.concurrent_state_changes,
                            sweep_errors);
                        execution_status->set_degraded(
                            std::string(
                                "runtime order reconciliation sweep failed: ") +
                            exc.what());
                        try {
                            execution_status->publish();
                        } catch (...) {
                        }
                        std::cerr
                            << "runtime order reconciliation sweep failed: "
                            << exc.what() << "\n";
                    }

                    const auto interval =
                        std::max<std::uint64_t>(
                            100,
                            order_reconcile_interval_ms);
                    std::uint64_t slept = 0;
                    while (slept < interval &&
                           !stop.stop_requested()) {
                        const auto chunk =
                            std::min<std::uint64_t>(
                                100,
                                interval - slept);
                        std::this_thread::sleep_for(
                            std::chrono::milliseconds(chunk));
                        slept += chunk;
                    }
                }
            });
    }

    auto reconciliation_server =
        std::make_shared<astu::execution::ReconciliationPipeServer>(
            astu::ipc::SimulationReconciliationDispatcher{journal});

    std::jthread reconciliation_thread(
        [reconciliation_server,
         journal,
         execution_status,
         recovered_orders_at_startup,
         recovered_reconciliation_events_at_startup](
            std::stop_token stop) {
            while (!stop.stop_requested()) {
                try {
                    reconciliation_server->serve_once();
                    execution_status->set_order_state_metrics(
                        recovered_orders_at_startup,
                        journal->recovered_order_count(),
                        journal->order_transition_count(),
                        recovered_reconciliation_events_at_startup,
                        journal->reconciliation_event_count());
                    execution_status->publish();
                } catch (const std::exception& exc) {
                    execution_status->set_degraded(
                        std::string(
                            "reconciliation pipe request failed: ") +
                        exc.what());
                    try {
                        execution_status->publish();
                    } catch (...) {
                    }
                    std::cerr
                        << "reconciliation pipe request failed: "
                        << exc.what() << "\n";
                    execution_status->set_ready(true, true);
                }
            }
        });

    astu::ipc::SimulationDispatcher dispatcher(
        std::move(data_provider),
        std::move(risk_provider),
        4096,
        [journal](const std::string& key) {
            return journal->accept_idempotency_key(key);
        },
        [journal, order_lifecycle, execution_status, recovered_orders_at_startup,
         recovered_reconciliation_events_at_startup](
            const astu::ipc::SimulationRequest& request,
            const astu::ipc::SimulationResponse& response,
            std::int64_t utc_ms) {
            order_lifecycle->observe(request, response, utc_ms);
            if (response.decision_code ==
                    astu::core::DecisionCode::OrderRoutingDisabled &&
                response.accepted_for_simulation) {
                journal->append_simulation_order_intent(
                    request,
                    response,
                    utc_ms);
            }
            journal->append(request, response, utc_ms);
            execution_status->record_response(response);
            execution_status->set_order_state_metrics(
                recovered_orders_at_startup,
                journal->recovered_order_count(),
                journal->order_transition_count(),
                recovered_reconciliation_events_at_startup,
                journal->reconciliation_event_count());
        },
        std::move(instrument_provider),
        std::move(position_provider));

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
    std::wcout << L"Simulation reconciliation pipe listening on "
               << astu::ipc::kReconciliationPipeName << L"\n";
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
        std::cout << "INSTRUMENT_PROVIDER=" << instrument_provider_name << "\n";
        std::cout << "INSTRUMENT_STATUS_DIR=" << instrument_status_dir.string() << "\n";
        std::cout << "MAX_INSTRUMENT_STATUS_AGE_MS="
                  << max_instrument_status_age_ms << "\n";
    } else {
        std::cout << "INSTRUMENT_PROVIDER=" << instrument_provider_name << "\n";
    }
    if (!position_status_dir.empty()) {
        std::cout << "POSITION_PROVIDER=" << position_provider_name << "\n";
        std::cout << "POSITION_STATUS_DIR=" << position_status_dir.string() << "\n";
        std::cout << "MAX_POSITION_STATUS_AGE_MS="
                  << max_position_status_age_ms << "\n";
    } else {
        std::cout << "POSITION_PROVIDER=" << position_provider_name << "\n";
    }
    std::cout << "REPLAY_KEYS_LOADED=" << journal->replay_size() << "\n";
    std::cout << "RECOVERED_SIMULATION_ORDERS_AT_STARTUP="
              << recovered_orders_at_startup << "\n";
    std::cout << "TRACKED_SIMULATION_ORDERS="
              << journal->recovered_order_count() << "\n";
    std::cout << "ORDER_TRANSITIONS_REPLAYED="
              << journal->order_transition_count() << "\n";
    std::cout << "RECOVERED_SIMULATION_ORDER_INTENTS_AT_STARTUP="
              << journal->recovered_order_intent_count() << "\n";
    std::cout << "RECOVERED_RECONCILIATION_EVENTS_AT_STARTUP="
              << recovered_reconciliation_events_at_startup << "\n";
    std::cout << "STARTUP_ORDER_SNAPSHOT_PROVIDER="
              << startup_order_snapshot_provider_name << "\n";
    if (startup_order_snapshot_required) {
        std::cout << "ORDER_SNAPSHOT_DIR="
                  << order_snapshot_dir.string() << "\n";
        std::cout << "MAX_ORDER_SNAPSHOT_AGE_MS="
                  << max_order_snapshot_age_ms << "\n";
        std::cout << "ORDER_RECONCILE_INTERVAL_MS="
                  << order_reconcile_interval_ms << "\n";
        std::cout << "RUNTIME_ORDER_RECONCILIATION=ENABLED\n";
    }
    std::cout << "STARTUP_ORDER_TRACKED="
              << startup_order_report.tracked_orders << "\n";
    std::cout << "STARTUP_ORDER_MATCHED="
              << startup_order_report.matched_orders << "\n";
    std::cout << "STARTUP_ORDER_MARKED_UNKNOWN="
              << startup_order_report.marked_unknown << "\n";
    std::cout << "STARTUP_ORDER_UNRESOLVED="
              << startup_order_report.unresolved_orders << "\n";
    if (!startup_order_snapshot_required) {
        std::cout << "RUNTIME_ORDER_RECONCILIATION=DISABLED\n";
    }

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
