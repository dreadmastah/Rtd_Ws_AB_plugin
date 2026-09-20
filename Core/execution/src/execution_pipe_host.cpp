#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <memory>
#include <limits>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "astu/account/live_position_provider.hpp"
#include "astu/account/live_realized_pnl_provider.hpp"
#include "astu/account/live_risk_provider.hpp"
#include "astu/core/contracts.hpp"
#include "astu/execution/account_loss_baseline.hpp"
#include "astu/execution/authoritative_order_snapshot.hpp"
#include "astu/execution/execution_journal.hpp"
#include "astu/execution/execution_pipe_server.hpp"
#include "astu/execution/execution_status.hpp"
#include "astu/execution/exposure_reservation.hpp"
#include "astu/execution/reconciliation_pipe_server.hpp"
#include "astu/execution/runtime_order_reconciler.hpp"
#include "astu/execution/simulation_order_lifecycle.hpp"
#include "astu/execution/startup_order_reconciler.hpp"
#include "astu/execution/symbol_risk_status.hpp"
#include "astu/execution/binance_usdm_testnet_order_gateway.hpp"
#include "astu/execution/testnet_order_router.hpp"
#include "astu/execution/testnet_convergence.hpp"
#include "astu/ipc/simulation_protocol.hpp"
#include "astu/instrument/live_instrument_provider.hpp"
#include "astu/wsrtd/live_status_provider.hpp"

namespace {

astu::core::AccountRiskSnapshot synthetic_risk(
    const astu::core::SignalIntent&,
    double risk_capital,
    double available_balance,
    double margin_balance,
    double initial_margin,
    double net_directional_notional,
    double max_gross_notional,
    std::uint32_t max_open_positions) {
    astu::core::AccountRiskSnapshot risk;
    risk.reconciled = true;
    risk.risk_state = astu::core::RiskState::Normal;
    risk.risk_capital = risk_capital;
    risk.available_balance = available_balance;
    risk.gross_notional = 0.0;
    risk.max_gross_notional = max_gross_notional;
    risk.open_positions = 0;
    risk.max_open_positions = max_open_positions;
    risk.margin_metrics_reconciled = true;
    risk.margin_balance = margin_balance;
    risk.initial_margin = initial_margin;
    risk.net_directional_reconciled = true;
    risk.net_directional_notional = net_directional_notional;
    return risk;
}

std::int64_t utc_now_ms() {
    const auto now = std::chrono::system_clock::now().time_since_epoch();
    return std::chrono::duration_cast<std::chrono::milliseconds>(now).count();
}

std::string position_mode_to_string(
    astu::core::PositionMode mode) {
    using astu::core::PositionMode;
    switch (mode) {
    case PositionMode::Flat:
        return "FLAT";
    case PositionMode::Long:
        return "LONG";
    case PositionMode::Short:
        return "SHORT";
    case PositionMode::Hedged:
        return "HEDGED";
    case PositionMode::Unknown:
        return "UNKNOWN";
    }
    return "UNKNOWN";
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
    double synthetic_risk_capital = 10'000.0;
    double synthetic_available_balance = 10'000.0;
    double synthetic_margin_balance = 10'000.0;
    double synthetic_initial_margin = 0.0;
    double synthetic_net_directional_notional = 0.0;
    double synthetic_max_gross_notional = 100'000.0;
    std::uint32_t synthetic_max_open_positions = 10;
    std::uint64_t max_pending_entry_scale_in_reservations = 0;
    double max_symbol_notional = 0.0;
    double minimum_available_balance_reserve = 0.0;
    double margin_reservation_rate = 0.0;
    double max_effective_leverage = 0.0;
    double max_margin_utilization = 0.0;
    double max_net_directional_notional = 0.0;
    double max_daily_risk_capital_loss = 0.0;
    double max_weekly_risk_capital_loss = 0.0;
    double max_daily_total_pnl_loss = 0.0;
    double max_weekly_total_pnl_loss = 0.0;
    double max_account_drawdown = 0.0;
    std::filesystem::path account_loss_baseline_file =
        "Core/runtime/account_loss_baseline.v1.json";
    double max_daily_realized_trade_loss = 0.0;
    double max_weekly_realized_trade_loss = 0.0;
    std::filesystem::path realized_pnl_status_file =
        "Core/runtime/realized_pnl_status.v1.json";
    std::uint64_t max_realized_pnl_status_age_ms = 90'000;
    std::uint64_t max_status_age_ms = 5'000;
    std::filesystem::path journal_path =
        "Core/runtime/execution_journal.v1.jsonl";
    std::filesystem::path risk_status_file =
        "Core/runtime/account_risk_status.v1.json";
    std::uint64_t max_risk_status_age_ms = 5'000;
    std::filesystem::path execution_status_file =
        "Core/runtime/execution_status.v1.json";
    std::filesystem::path symbol_risk_status_file =
        "Core/runtime/symbol_risk_status.v1.json";
    std::filesystem::path symbol_risk_universe_file =
        "CleanRoomR2/stack/bootstrap_symbols.tls";
    bool testnet_order_routing_enabled = false;
    bool testnet_order_routing_armed = false;
    std::filesystem::path testnet_convergence_status_file =
        "Core/runtime/testnet_user_data_status.v1.json";
    std::uint64_t max_testnet_convergence_age_ms = 7'000;
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
    if (const char* env = std::getenv("ASTU_SYMBOL_RISK_STATUS_FILE");
        env && *env) {
        symbol_risk_status_file = env;
    }
    if (const char* env = std::getenv("ASTU_SYMBOL_RISK_UNIVERSE_FILE");
        env && *env) {
        symbol_risk_universe_file = env;
    }
    if (const char* env = std::getenv("ASTU_TESTNET_ORDER_ROUTING_ENABLED");
        env && std::string(env) == "1") {
        testnet_order_routing_enabled = true;
    }
    if (const char* env = std::getenv("ASTU_TESTNET_ORDER_ROUTING_ARMED");
        env && std::string(env) == "1") {
        testnet_order_routing_armed = true;
    }
    if (const char* env =
            std::getenv("ASTU_TESTNET_CONVERGENCE_STATUS_FILE");
        env && *env) {
        testnet_convergence_status_file = env;
    }
    if (const char* env =
            std::getenv("ASTU_MAX_TESTNET_CONVERGENCE_AGE_MS");
        env && *env) {
        max_testnet_convergence_age_ms =
            static_cast<std::uint64_t>(std::stoull(env));
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
    if (const char* env = std::getenv(
            "ASTU_MAX_PENDING_ENTRY_SCALE_IN_RESERVATIONS");
        env && *env) {
        max_pending_entry_scale_in_reservations =
            std::stoull(env);
    }
    if (const char* env = std::getenv("ASTU_MAX_SYMBOL_NOTIONAL");
        env && *env) {
        max_symbol_notional = std::stod(env);
    }
    if (const char* env = std::getenv(
            "ASTU_MINIMUM_AVAILABLE_BALANCE_RESERVE");
        env && *env) {
        minimum_available_balance_reserve =
            std::stod(env);
    }
    if (const char* env = std::getenv(
            "ASTU_SIMULATION_MARGIN_RESERVATION_RATE");
        env && *env) {
        margin_reservation_rate = std::stod(env);
    }
    if (const char* env = std::getenv("ASTU_MAX_EFFECTIVE_LEVERAGE");
        env && *env) {
        max_effective_leverage = std::stod(env);
    }
    if (const char* env = std::getenv("ASTU_MAX_MARGIN_UTILIZATION");
        env && *env) {
        max_margin_utilization = std::stod(env);
    }
    if (const char* env = std::getenv("ASTU_MAX_NET_DIRECTIONAL_NOTIONAL");
        env && *env) {
        max_net_directional_notional = std::stod(env);
    }
    if (const char* env = std::getenv("ASTU_MAX_DAILY_RISK_CAPITAL_LOSS");
        env && *env) {
        max_daily_risk_capital_loss = std::stod(env);
    }
    if (const char* env = std::getenv("ASTU_MAX_WEEKLY_RISK_CAPITAL_LOSS");
        env && *env) {
        max_weekly_risk_capital_loss = std::stod(env);
    }
    if (const char* env = std::getenv("ASTU_MAX_DAILY_TOTAL_PNL_LOSS");
        env && *env) {
        max_daily_total_pnl_loss = std::stod(env);
    }
    if (const char* env = std::getenv("ASTU_MAX_WEEKLY_TOTAL_PNL_LOSS");
        env && *env) {
        max_weekly_total_pnl_loss = std::stod(env);
    }
    if (const char* env = std::getenv("ASTU_MAX_ACCOUNT_DRAWDOWN");
        env && *env) {
        max_account_drawdown = std::stod(env);
    }
    if (const char* env = std::getenv("ASTU_ACCOUNT_LOSS_BASELINE_FILE");
        env && *env) {
        account_loss_baseline_file = env;
    }
    if (const char* env = std::getenv("ASTU_MAX_DAILY_REALIZED_TRADE_LOSS");
        env && *env) {
        max_daily_realized_trade_loss = std::stod(env);
    }
    if (const char* env = std::getenv("ASTU_MAX_WEEKLY_REALIZED_TRADE_LOSS");
        env && *env) {
        max_weekly_realized_trade_loss = std::stod(env);
    }
    if (const char* env = std::getenv("ASTU_REALIZED_PNL_STATUS_FILE");
        env && *env) {
        realized_pnl_status_file = env;
    }
    if (const char* env = std::getenv(
            "ASTU_MAX_REALIZED_PNL_STATUS_AGE_MS");
        env && *env) {
        max_realized_pnl_status_age_ms = std::stoull(env);
    }

    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--synthetic") {
            synthetic = true;
        } else if (arg == "--synthetic-risk-capital" && i + 1 < argc) {
            synthetic_risk_capital = std::stod(argv[++i]);
        } else if (arg == "--synthetic-available-balance" && i + 1 < argc) {
            synthetic_available_balance = std::stod(argv[++i]);
        } else if (arg == "--synthetic-margin-balance" && i + 1 < argc) {
            synthetic_margin_balance = std::stod(argv[++i]);
        } else if (arg == "--synthetic-initial-margin" && i + 1 < argc) {
            synthetic_initial_margin = std::stod(argv[++i]);
        } else if (arg == "--synthetic-net-directional-notional" &&
                   i + 1 < argc) {
            synthetic_net_directional_notional = std::stod(argv[++i]);
        } else if (arg == "--synthetic-max-gross-notional" && i + 1 < argc) {
            synthetic_max_gross_notional = std::stod(argv[++i]);
        } else if (arg == "--synthetic-max-open-positions" && i + 1 < argc) {
            synthetic_max_open_positions = static_cast<std::uint32_t>(
                std::stoul(argv[++i]));
        } else if (arg == "--max-pending-entry-scale-in-reservations" &&
                   i + 1 < argc) {
            max_pending_entry_scale_in_reservations =
                std::stoull(argv[++i]);
        } else if (arg == "--max-symbol-notional" && i + 1 < argc) {
            max_symbol_notional = std::stod(argv[++i]);
        } else if (arg == "--minimum-available-balance-reserve" &&
                   i + 1 < argc) {
            minimum_available_balance_reserve =
                std::stod(argv[++i]);
        } else if (arg == "--simulation-margin-reservation-rate" &&
                   i + 1 < argc) {
            margin_reservation_rate = std::stod(argv[++i]);
        } else if (arg == "--max-effective-leverage" && i + 1 < argc) {
            max_effective_leverage = std::stod(argv[++i]);
        } else if (arg == "--max-margin-utilization" && i + 1 < argc) {
            max_margin_utilization = std::stod(argv[++i]);
        } else if (arg == "--max-net-directional-notional" && i + 1 < argc) {
            max_net_directional_notional = std::stod(argv[++i]);
        } else if (arg == "--max-daily-risk-capital-loss" &&
                   i + 1 < argc) {
            max_daily_risk_capital_loss = std::stod(argv[++i]);
        } else if (arg == "--max-weekly-risk-capital-loss" &&
                   i + 1 < argc) {
            max_weekly_risk_capital_loss = std::stod(argv[++i]);
        } else if (arg == "--max-daily-total-pnl-loss" &&
                   i + 1 < argc) {
            max_daily_total_pnl_loss = std::stod(argv[++i]);
        } else if (arg == "--max-weekly-total-pnl-loss" &&
                   i + 1 < argc) {
            max_weekly_total_pnl_loss = std::stod(argv[++i]);
        } else if (arg == "--max-account-drawdown" &&
                   i + 1 < argc) {
            max_account_drawdown = std::stod(argv[++i]);
        } else if (arg == "--account-loss-baseline-file" &&
                   i + 1 < argc) {
            account_loss_baseline_file = argv[++i];
        } else if (arg == "--max-daily-realized-trade-loss" &&
                   i + 1 < argc) {
            max_daily_realized_trade_loss = std::stod(argv[++i]);
        } else if (arg == "--max-weekly-realized-trade-loss" &&
                   i + 1 < argc) {
            max_weekly_realized_trade_loss = std::stod(argv[++i]);
        } else if (arg == "--realized-pnl-status-file" &&
                   i + 1 < argc) {
            realized_pnl_status_file = argv[++i];
        } else if (arg == "--max-realized-pnl-status-age-ms" &&
                   i + 1 < argc) {
            max_realized_pnl_status_age_ms = std::stoull(argv[++i]);
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
        } else if (arg == "--symbol-risk-status-file" && i + 1 < argc) {
            symbol_risk_status_file = argv[++i];
        } else if (arg == "--symbol-risk-universe-file" && i + 1 < argc) {
            symbol_risk_universe_file = argv[++i];
        } else if (arg == "--enable-testnet-order-routing") {
            testnet_order_routing_enabled = true;
        } else if (arg == "--arm-testnet-order-routing") {
            testnet_order_routing_armed = true;
        } else if (arg == "--testnet-convergence-status-file" &&
                   i + 1 < argc) {
            testnet_convergence_status_file = argv[++i];
        } else if (arg == "--max-testnet-convergence-age-ms" &&
                   i + 1 < argc) {
            max_testnet_convergence_age_ms =
                static_cast<std::uint64_t>(
                    std::stoull(argv[++i]));
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

    if (!std::isfinite(synthetic_risk_capital) ||
        synthetic_risk_capital < 0.0 ||
        !std::isfinite(synthetic_available_balance) ||
        synthetic_available_balance < 0.0 ||
        !std::isfinite(synthetic_margin_balance) ||
        synthetic_margin_balance < 0.0 ||
        !std::isfinite(synthetic_initial_margin) ||
        synthetic_initial_margin < 0.0 ||
        !std::isfinite(synthetic_net_directional_notional) ||
        !std::isfinite(max_symbol_notional) ||
        max_symbol_notional < 0.0 ||
        !std::isfinite(minimum_available_balance_reserve) ||
        minimum_available_balance_reserve < 0.0 ||
        !std::isfinite(margin_reservation_rate) ||
        margin_reservation_rate < 0.0 ||
        !std::isfinite(max_effective_leverage) ||
        max_effective_leverage < 0.0 ||
        !std::isfinite(max_margin_utilization) ||
        max_margin_utilization < 0.0 ||
        max_margin_utilization > 1.0 ||
        !std::isfinite(max_net_directional_notional) ||
        max_net_directional_notional < 0.0 ||
        !std::isfinite(max_daily_risk_capital_loss) ||
        max_daily_risk_capital_loss < 0.0 ||
        !std::isfinite(max_weekly_risk_capital_loss) ||
        max_weekly_risk_capital_loss < 0.0 ||
        !std::isfinite(max_daily_total_pnl_loss) ||
        max_daily_total_pnl_loss < 0.0 ||
        !std::isfinite(max_weekly_total_pnl_loss) ||
        max_weekly_total_pnl_loss < 0.0 ||
        !std::isfinite(max_account_drawdown) ||
        max_account_drawdown < 0.0 ||
        !std::isfinite(max_daily_realized_trade_loss) ||
        max_daily_realized_trade_loss < 0.0 ||
        !std::isfinite(max_weekly_realized_trade_loss) ||
        max_weekly_realized_trade_loss < 0.0) {
        std::cerr
            << "projected risk numeric settings must be finite and non-negative\n";
        return 2;
    }
    if ((minimum_available_balance_reserve > 0.0 ||
         max_margin_utilization > 0.0) &&
        margin_reservation_rate <= 0.0) {
        std::cerr
            << "free-balance or margin-utilization limits require a positive simulation margin reservation rate\n";
        return 2;
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
        risk_provider =
            [synthetic_risk_capital,
             synthetic_available_balance,
             synthetic_margin_balance,
             synthetic_initial_margin,
             synthetic_net_directional_notional,
             synthetic_max_gross_notional,
             synthetic_max_open_positions](
                const astu::core::SignalIntent& intent) {
                return synthetic_risk(
                    intent,
                    synthetic_risk_capital,
                    synthetic_available_balance,
                    synthetic_margin_balance,
                    synthetic_initial_margin,
                    synthetic_net_directional_notional,
                    synthetic_max_gross_notional,
                    synthetic_max_open_positions);
            };
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

    const auto symbol_risk_symbols =
        astu::execution::load_symbol_risk_universe(
            symbol_risk_universe_file,
            64);

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
        100'000,
        margin_reservation_rate);
    const auto recovered_orders_at_startup =
        journal->recovered_order_count();
    const auto recovered_reconciliation_events_at_startup =
        journal->reconciliation_event_count();
    const auto recovered_reservation_summary =
        journal->exposure_reservation_summary();

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

    const bool realized_pnl_required =
        max_daily_realized_trade_loss > 0.0 ||
        max_weekly_realized_trade_loss > 0.0;
    std::shared_ptr<astu::account::LiveRealizedPnlProvider>
        realized_pnl_provider;
    if (realized_pnl_required) {
        realized_pnl_provider = std::make_shared<
            astu::account::LiveRealizedPnlProvider>(
                realized_pnl_status_file,
                max_realized_pnl_status_age_ms);
    }

    if (testnet_order_routing_armed &&
        !testnet_order_routing_enabled) {
        throw std::invalid_argument(
            "--arm-testnet-order-routing requires --enable-testnet-order-routing");
    }
    if (testnet_order_routing_enabled && synthetic) {
        throw std::invalid_argument(
            "Testnet order routing refuses synthetic account/data mode");
    }
    if (testnet_order_routing_enabled &&
        (risk_status_file.empty() ||
         position_status_dir.empty() ||
         instrument_status_dir.empty() ||
         order_snapshot_dir.empty())) {
        throw std::invalid_argument(
            "Testnet order routing requires account, position, instrument and authoritative order evidence");
    }

    if (testnet_order_routing_enabled) {
        if (max_testnet_convergence_age_ms == 0) {
            throw std::invalid_argument(
                "Testnet convergence age must be positive");
        }
        const astu::execution::FileBackedTestnetConvergenceProvider
            convergence_provider(
                testnet_convergence_status_file,
                max_testnet_convergence_age_ms);
        const auto convergence = convergence_provider();
        if (!convergence.ready) {
            throw std::runtime_error(
                "Binance Testnet routing fail-closed: account/position/order user-data convergence unavailable: " +
                convergence.detail);
        }
        throw std::runtime_error(
            "Binance Testnet routing convergence is ready, but activation remains administratively locked until live Testnet user-data transport/recovery acceptance is completed");
    }

    const bool account_loss_limits_enabled =
        max_daily_risk_capital_loss > 0.0 ||
        max_weekly_risk_capital_loss > 0.0 ||
        max_daily_total_pnl_loss > 0.0 ||
        max_weekly_total_pnl_loss > 0.0 ||
        max_account_drawdown > 0.0;
    const bool account_loss_requires_margin =
        max_daily_total_pnl_loss > 0.0 ||
        max_weekly_total_pnl_loss > 0.0 ||
        max_account_drawdown > 0.0;

    std::shared_ptr<astu::execution::AccountLossBaselineTracker>
        account_loss_tracker;
    if (account_loss_limits_enabled) {
        account_loss_tracker = std::make_shared<
            astu::execution::AccountLossBaselineTracker>(
                account_loss_baseline_file);
    }

    auto base_risk_provider = std::make_shared<
        astu::ipc::SimulationDispatcher::RiskProvider>(
            std::move(risk_provider));
    const auto projected_position_provider = position_provider;
    risk_provider =
        [base_risk_provider,
         account_loss_tracker,
         account_loss_requires_margin,
         realized_pnl_provider,
         journal,
         projected_position_provider,
         synthetic,
         max_pending_entry_scale_in_reservations,
         max_symbol_notional,
         minimum_available_balance_reserve,
         margin_reservation_rate,
         max_effective_leverage,
         max_margin_utilization,
         max_net_directional_notional,
         max_daily_risk_capital_loss,
         max_weekly_risk_capital_loss,
         max_daily_total_pnl_loss,
         max_weekly_total_pnl_loss,
         max_account_drawdown,
         max_daily_realized_trade_loss,
         max_weekly_realized_trade_loss](
            const astu::core::SignalIntent& intent) mutable {
            auto risk = (*base_risk_provider)(intent);

            risk.max_daily_risk_capital_loss =
                max_daily_risk_capital_loss;
            risk.max_weekly_risk_capital_loss =
                max_weekly_risk_capital_loss;
            risk.max_daily_total_pnl_loss =
                max_daily_total_pnl_loss;
            risk.max_weekly_total_pnl_loss =
                max_weekly_total_pnl_loss;
            risk.max_account_drawdown =
                max_account_drawdown;
            risk.max_daily_realized_trade_loss =
                max_daily_realized_trade_loss;
            risk.max_weekly_realized_trade_loss =
                max_weekly_realized_trade_loss;

            if (realized_pnl_provider) {
                const auto realized = (*realized_pnl_provider)();
                risk.realized_pnl_evidence_reconciled =
                    realized.reconciled;
                risk.daily_realized_trade_loss =
                    realized.daily_realized_trade_loss;
                risk.weekly_realized_trade_loss =
                    realized.weekly_realized_trade_loss;
            }

            if (account_loss_tracker) {
                const auto metrics =
                    account_loss_tracker->evaluate(
                        risk,
                        static_cast<std::uint64_t>(utc_now_ms()),
                        account_loss_requires_margin);
                risk.account_loss_metrics_reconciled =
                    metrics.ready;
                risk.daily_risk_capital_loss =
                    metrics.daily_risk_capital_loss;
                risk.weekly_risk_capital_loss =
                    metrics.weekly_risk_capital_loss;
                risk.daily_total_pnl_loss =
                    metrics.daily_total_pnl_loss;
                risk.weekly_total_pnl_loss =
                    metrics.weekly_total_pnl_loss;
                risk.account_drawdown =
                    metrics.account_drawdown;
            }

            bool symbol_exposure_reconciled = false;
            double reconciled_symbol_notional = 0.0;
            if (max_symbol_notional > 0.0) {
                if (synthetic) {
                    symbol_exposure_reconciled = true;
                } else if (projected_position_provider) {
                    const auto position =
                        projected_position_provider(intent);
                    if (position.reconciled &&
                        position.schema_version == 1 &&
                        position.symbol == intent.symbol &&
                        std::isfinite(position.notional) &&
                        position.notional >= 0.0) {
                        symbol_exposure_reconciled = true;
                        reconciled_symbol_notional =
                            position.notional;
                    }
                }
            }

            return astu::execution::ExposureReservationRiskOverlay::apply(
                risk,
                journal->exposure_reservation_summary(
                    intent.symbol),
                max_pending_entry_scale_in_reservations,
                symbol_exposure_reconciled,
                reconciled_symbol_notional,
                max_symbol_notional,
                minimum_available_balance_reserve,
                margin_reservation_rate,
                max_effective_leverage,
                max_margin_utilization,
                max_net_directional_notional);
        };

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
    execution_status->set_exposure_reservation_metrics(
        recovered_reservation_summary.active_reservations,
        recovered_reservation_summary.active_reservations,
        recovered_reservation_summary.reserved_gross_notional,
        recovered_reservation_summary.reserved_available_balance,
        recovered_reservation_summary.reserved_net_directional_notional,
        recovered_reservation_summary.reserved_position_slots,
        journal->exposure_reservation_create_count(),
        journal->exposure_reservation_release_count(),
        journal->exposure_reservation_implicit_release_count(),
        journal->exposure_reservation_reconstructed_count());
    execution_status->set_projected_risk_limits(
        max_pending_entry_scale_in_reservations,
        max_symbol_notional,
        minimum_available_balance_reserve,
        margin_reservation_rate,
        max_effective_leverage,
        max_margin_utilization,
        max_net_directional_notional);
    execution_status->set_account_loss_policy(
        account_loss_limits_enabled,
        account_loss_baseline_file.string(),
        max_daily_risk_capital_loss,
        max_weekly_risk_capital_loss,
        max_daily_total_pnl_loss,
        max_weekly_total_pnl_loss,
        max_account_drawdown);
    execution_status->set_realized_pnl_status(
        realized_pnl_required
            ? "FILE_BACKED_BINANCE_INCOME_V1"
            : "DISABLED",
        realized_pnl_required,
        realized_pnl_status_file.string(),
        false,
        "UNKNOWN",
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0,
        0,
        max_daily_realized_trade_loss,
        max_weekly_realized_trade_loss);
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

    auto symbol_risk_status =
        std::make_shared<astu::execution::SymbolRiskStatusPublisher>(
            symbol_risk_status_file);

    std::jthread symbol_risk_status_thread(
        [symbol_risk_status,
         symbol_risk_symbols,
         projected_position_provider,
         journal,
         synthetic,
         max_symbol_notional](
            std::stop_token stop) {
            while (!stop.stop_requested()) {
                try {
                    std::vector<astu::execution::SymbolRiskStatusEntry>
                        entries;
                    entries.reserve(symbol_risk_symbols.size());

                    for (const auto& symbol : symbol_risk_symbols) {
                        astu::execution::SymbolRiskStatusEntry entry;
                        entry.symbol = symbol;
                        entry.max_symbol_notional =
                            std::max(0.0, max_symbol_notional);
                        entry.limit_enabled =
                            max_symbol_notional > 0.0;

                        if (synthetic) {
                            entry.position_ready = true;
                            entry.position_mode = "FLAT";
                            entry.current_notional = 0.0;
                            entry.detail =
                                "synthetic position exposure";
                        } else if (projected_position_provider) {
                            astu::core::SignalIntent intent;
                            intent.symbol = symbol;
                            const auto position =
                                projected_position_provider(intent);
                            entry.position_ready =
                                position.reconciled &&
                                position.schema_version == 1 &&
                                position.symbol == symbol &&
                                std::isfinite(position.notional) &&
                                position.notional >= 0.0;
                            entry.position_mode =
                                position_mode_to_string(
                                    position.mode);
                            entry.current_notional =
                                entry.position_ready
                                    ? position.notional
                                    : 0.0;
                            entry.detail = position.detail;
                        } else {
                            entry.position_ready = false;
                            entry.position_mode = "UNKNOWN";
                            entry.detail =
                                "position provider unavailable";
                        }

                        const auto reservations =
                            journal->exposure_reservation_summary(
                                symbol);
                        entry.active_reservations =
                            reservations.symbol_active_reservations;
                        entry.reserved_gross_notional =
                            std::max(
                                0.0,
                                reservations
                                    .symbol_reserved_gross_notional);
                        entry.projected_notional =
                            std::max(
                                0.0,
                                entry.current_notional +
                                    entry.reserved_gross_notional);

                        if (!entry.limit_enabled) {
                            entry.status = "DISABLED";
                            entry.headroom = 0.0;
                        } else if (!entry.position_ready) {
                            entry.status = "UNAVAILABLE";
                            entry.headroom = 0.0;
                        } else {
                            entry.headroom =
                                std::max(
                                    0.0,
                                    max_symbol_notional -
                                        entry.projected_notional);
                            entry.status =
                                entry.projected_notional >=
                                        max_symbol_notional
                                    ? "BLOCKED"
                                    : "HEADROOM";
                        }

                        entries.push_back(std::move(entry));
                    }

                    symbol_risk_status->publish(entries);
                } catch (const std::exception& exc) {
                    std::cerr
                        << "symbol-risk status publish failed: "
                        << exc.what() << "\n";
                }

                for (int i = 0;
                     i < 10 && !stop.stop_requested();
                     ++i) {
                    std::this_thread::sleep_for(
                        std::chrono::milliseconds(100));
                }
            }
        });

    std::jthread account_risk_observation_thread(
        [base_risk_provider,
         journal,
         execution_status](
            std::stop_token stop) {
            astu::core::SignalIntent monitor_intent;
            monitor_intent.symbol = "ACCOUNT";
            while (!stop.stop_requested()) {
                try {
                    const auto risk =
                        (*base_risk_provider)(monitor_intent);
                    const auto reservations =
                        journal->exposure_reservation_summary();

                    const auto projected_available_balance =
                        std::max(
                            0.0,
                            risk.available_balance -
                                std::max(
                                    0.0,
                                    reservations.reserved_available_balance));
                    const auto projected_gross_notional =
                        std::max(
                            0.0,
                            risk.gross_notional +
                                std::max(
                                    0.0,
                                    reservations.reserved_gross_notional));
                    const auto projected_open_positions =
                        static_cast<std::uint32_t>(
                            std::min<std::uint64_t>(
                                static_cast<std::uint64_t>(
                                    risk.open_positions) +
                                    static_cast<std::uint64_t>(
                                        reservations.reserved_position_slots),
                                std::numeric_limits<std::uint32_t>::max()));

                    const auto projected_initial_margin =
                        risk.margin_metrics_reconciled
                            ? std::max(
                                  0.0,
                                  risk.initial_margin +
                                      std::max(
                                          0.0,
                                          reservations
                                              .reserved_available_balance))
                            : 0.0;
                    const auto projected_effective_leverage =
                        risk.margin_metrics_reconciled &&
                                risk.margin_balance > 0.0
                            ? projected_gross_notional /
                                  risk.margin_balance
                            : 0.0;
                    const auto projected_margin_utilization =
                        risk.margin_metrics_reconciled &&
                                risk.margin_balance > 0.0
                            ? projected_initial_margin /
                                  risk.margin_balance
                            : 0.0;
                    const auto projected_net_directional_notional =
                        risk.net_directional_reconciled
                            ? risk.net_directional_notional +
                                  reservations
                                      .reserved_net_directional_notional
                            : 0.0;

                    std::string risk_state = "EMERGENCY";
                    switch (risk.risk_state) {
                    case astu::core::RiskState::Normal:
                        risk_state = "NORMAL";
                        break;
                    case astu::core::RiskState::Warning:
                        risk_state = "WARNING";
                        break;
                    case astu::core::RiskState::Restricted:
                        risk_state = "RESTRICTED";
                        break;
                    case astu::core::RiskState::BlockNewEntries:
                        risk_state = "BLOCK_NEW_ENTRIES";
                        break;
                    case astu::core::RiskState::Emergency:
                        risk_state = "EMERGENCY";
                        break;
                    }

                    execution_status->set_account_risk_observation(
                        risk.reconciled,
                        static_cast<std::uint64_t>(utc_now_ms()),
                        std::move(risk_state),
                        risk.risk_capital,
                        risk.available_balance,
                        projected_available_balance,
                        risk.gross_notional,
                        projected_gross_notional,
                        risk.max_gross_notional,
                        risk.open_positions,
                        projected_open_positions,
                        risk.max_open_positions,
                        risk.margin_metrics_reconciled,
                        risk.margin_balance,
                        risk.initial_margin,
                        projected_initial_margin,
                        projected_effective_leverage,
                        projected_margin_utilization,
                        risk.net_directional_reconciled,
                        risk.net_directional_notional,
                        projected_net_directional_notional);
                    execution_status->publish();
                } catch (const std::exception& exc) {
                    execution_status->set_account_risk_observation(
                        false,
                        static_cast<std::uint64_t>(utc_now_ms()),
                        "EMERGENCY",
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0,
                        0,
                        0,
                        false,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        false,
                        0.0,
                        0.0);
                    try {
                        execution_status->publish();
                    } catch (...) {
                    }
                    std::cerr
                        << "account-risk observation failed: "
                        << exc.what() << "\n";
                }

                for (int i = 0;
                     i < 10 && !stop.stop_requested();
                     ++i) {
                    std::this_thread::sleep_for(
                        std::chrono::milliseconds(100));
                }
            }
        });

    std::jthread realized_pnl_monitor_thread;
    if (realized_pnl_provider) {
        realized_pnl_monitor_thread = std::jthread(
            [realized_pnl_provider,
             execution_status,
             realized_pnl_status_file,
             max_daily_realized_trade_loss,
             max_weekly_realized_trade_loss](
                std::stop_token stop) {
                while (!stop.stop_requested()) {
                    const auto realized =
                        (*realized_pnl_provider)();
                    execution_status->set_realized_pnl_status(
                        "FILE_BACKED_BINANCE_INCOME_V1",
                        true,
                        realized_pnl_status_file.string(),
                        realized.reconciled,
                        realized.settlement_asset.empty()
                            ? "UNKNOWN"
                            : realized.settlement_asset,
                        realized.daily_realized_trade_pnl,
                        realized.weekly_realized_trade_pnl,
                        realized.daily_realized_trade_loss,
                        realized.weekly_realized_trade_loss,
                        realized.daily_funding_fee,
                        realized.weekly_funding_fee,
                        realized.daily_commission,
                        realized.weekly_commission,
                        realized.daily_net_trading_income,
                        realized.weekly_net_trading_income,
                        realized.records_in_current_week,
                        realized.ignored_income_records,
                        max_daily_realized_trade_loss,
                        max_weekly_realized_trade_loss);
                    try {
                        execution_status->publish();
                    } catch (...) {
                    }
                    for (int i = 0;
                         i < 10 && !stop.stop_requested();
                         ++i) {
                        std::this_thread::sleep_for(
                            std::chrono::milliseconds(100));
                    }
                }
            });
    }

    std::jthread account_loss_monitor_thread;
    if (account_loss_tracker) {
        account_loss_monitor_thread = std::jthread(
            [base_risk_provider,
             account_loss_tracker,
             account_loss_requires_margin,
             execution_status](
                std::stop_token stop) {
                astu::core::SignalIntent monitor_intent;
                monitor_intent.symbol = "ACCOUNT";
                while (!stop.stop_requested()) {
                    try {
                        const auto risk =
                            (*base_risk_provider)(monitor_intent);
                        const auto metrics =
                            account_loss_tracker->evaluate(
                                risk,
                                static_cast<std::uint64_t>(
                                    utc_now_ms()),
                                account_loss_requires_margin);
                        execution_status->set_account_loss_metrics(
                            metrics.ready,
                            metrics.utc_day_index,
                            metrics.utc_week_start_day_index,
                            metrics.daily_start_risk_capital,
                            metrics.weekly_start_risk_capital,
                            metrics.daily_start_margin_balance,
                            metrics.weekly_start_margin_balance,
                            metrics.high_water_margin_balance,
                            metrics.daily_risk_capital_loss,
                            metrics.weekly_risk_capital_loss,
                            metrics.daily_total_pnl_loss,
                            metrics.weekly_total_pnl_loss,
                            metrics.account_drawdown);
                        execution_status->publish();
                    } catch (const std::exception& exc) {
                        execution_status->set_degraded(
                            std::string(
                                "account loss baseline monitor failed: ") +
                            exc.what());
                        try {
                            execution_status->publish();
                        } catch (...) {
                        }
                    }

                    for (int i = 0;
                         i < 10 && !stop.stop_requested();
                         ++i) {
                        std::this_thread::sleep_for(
                            std::chrono::milliseconds(100));
                    }
                }
            });
    }

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
         recovered_reconciliation_events_at_startup,
         recovered_reservation_summary](
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
                    const auto reservations =
                        journal->exposure_reservation_summary();
                    execution_status->set_exposure_reservation_metrics(
                        recovered_reservation_summary.active_reservations,
                        reservations.active_reservations,
                        reservations.reserved_gross_notional,
                        reservations.reserved_available_balance,
                        reservations.reserved_net_directional_notional,
                        reservations.reserved_position_slots,
                        journal->exposure_reservation_create_count(),
                        journal->exposure_reservation_release_count(),
                        journal->exposure_reservation_implicit_release_count(),
                        journal->exposure_reservation_reconstructed_count());
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

    std::shared_ptr<astu::execution::TestnetOrderRouter>
        testnet_order_router;
    if (testnet_order_routing_enabled &&
        testnet_order_routing_armed) {
        const char* api_key =
            std::getenv("ASTU_BINANCE_TESTNET_API_KEY");
        const char* api_secret =
            std::getenv("ASTU_BINANCE_TESTNET_API_SECRET");
        if (api_key == nullptr || *api_key == '\0' ||
            api_secret == nullptr || *api_secret == '\0') {
            throw std::runtime_error(
                "armed Testnet routing requires ASTU_BINANCE_TESTNET_API_KEY and ASTU_BINANCE_TESTNET_API_SECRET");
        }
        auto gateway =
            std::make_shared<
                astu::execution::BinanceUsdmTestnetOrderGateway>(
                    api_key,
                    api_secret);
        testnet_order_router =
            std::make_shared<astu::execution::TestnetOrderRouter>(
                journal,
                [gateway](
                    const astu::execution::TestnetOrderRequest& order,
                    std::uint64_t timestamp_ms) {
                    return gateway->submit_market(
                        order,
                        timestamp_ms);
                });
    }

    astu::ipc::SimulationDispatcher dispatcher(
        std::move(data_provider),
        std::move(risk_provider),
        4096,
        [journal](const std::string& key) {
            return journal->accept_idempotency_key(key);
        },
        [journal, order_lifecycle, execution_status, recovered_orders_at_startup,
         recovered_reconciliation_events_at_startup,
         recovered_reservation_summary,
         testnet_order_router](
            const astu::ipc::SimulationRequest& request,
            astu::ipc::SimulationResponse& response,
            std::int64_t utc_ms) {
            order_lifecycle->observe(request, response, utc_ms);
            if (response.decision_code ==
                    astu::core::DecisionCode::OrderRoutingDisabled &&
                response.accepted_for_simulation) {
                journal->append_simulation_order_intent(
                    request,
                    response,
                    utc_ms);
                journal->append_exposure_reservation(
                    request,
                    response,
                    utc_ms);
                if (testnet_order_router) {
                    testnet_order_router->route(
                        request,
                        response,
                        utc_ms);
                }
            }
            journal->append(request, response, utc_ms);
            execution_status->record_response(response);
            execution_status->set_order_state_metrics(
                recovered_orders_at_startup,
                journal->recovered_order_count(),
                journal->order_transition_count(),
                recovered_reconciliation_events_at_startup,
                journal->reconciliation_event_count());
            const auto reservations =
                journal->exposure_reservation_summary();
            execution_status->set_exposure_reservation_metrics(
                recovered_reservation_summary.active_reservations,
                reservations.active_reservations,
                reservations.reserved_gross_notional,
                reservations.reserved_available_balance,
                reservations.reserved_net_directional_notional,
                reservations.reserved_position_slots,
                journal->exposure_reservation_create_count(),
                journal->exposure_reservation_release_count(),
                journal->exposure_reservation_implicit_release_count(),
                journal->exposure_reservation_reconstructed_count());
        },
        std::move(instrument_provider),
        std::move(position_provider));

    execution_status->set_execution_environment(
        (testnet_order_routing_enabled &&
         testnet_order_routing_armed)
            ? "BINANCE_USDM_TESTNET"
            : "SIMULATION_ONLY",
        testnet_order_routing_enabled &&
            testnet_order_routing_armed);
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
    std::cout << "ORDER_ROUTING_ENABLED="
              << ((testnet_order_routing_enabled &&
                   testnet_order_routing_armed)
                      ? "true"
                      : "false")
              << "\n";
    std::cout << "EXECUTION_ENVIRONMENT="
              << ((testnet_order_routing_enabled &&
                   testnet_order_routing_armed)
                      ? "BINANCE_USDM_TESTNET"
                      : "SIMULATION_ONLY")
              << "\n";
    std::cout << "TESTNET_ORDER_ROUTING_ENABLED="
              << (testnet_order_routing_enabled ? "true" : "false")
              << "\n";
    std::cout << "TESTNET_ORDER_ROUTING_ARMED="
              << (testnet_order_routing_armed ? "true" : "false")
              << "\n";
    std::cout << "TESTNET_CONVERGENCE_STATUS_FILE="
              << testnet_convergence_status_file.string()
              << "\n";
    std::cout << "MAX_TESTNET_CONVERGENCE_AGE_MS="
              << max_testnet_convergence_age_ms
              << "\n";
    std::cout << "DATA_PROVIDER=" << data_provider_name << "\n";
    if (!synthetic) {
        std::cout << "STATUS_DIR=" << status_dir.string() << "\n";
        std::cout << "MAX_STATUS_AGE_MS=" << max_status_age_ms << "\n";
    }
    std::cout << "RISK_PROVIDER=" << risk_provider_name << "\n";
    if (!synthetic) {
        std::cout << "RISK_STATUS_FILE=" << risk_status_file.string() << "\n";
        std::cout << "MAX_RISK_STATUS_AGE_MS=" << max_risk_status_age_ms << "\n";
    } else {
        std::cout << "SYNTHETIC_RISK_CAPITAL="
                  << synthetic_risk_capital << "\n";
        std::cout << "SYNTHETIC_AVAILABLE_BALANCE="
                  << synthetic_available_balance << "\n";
        std::cout << "SYNTHETIC_MARGIN_BALANCE="
                  << synthetic_margin_balance << "\n";
        std::cout << "SYNTHETIC_INITIAL_MARGIN="
                  << synthetic_initial_margin << "\n";
        std::cout << "SYNTHETIC_NET_DIRECTIONAL_NOTIONAL="
                  << synthetic_net_directional_notional << "\n";
        std::cout << "SYNTHETIC_MAX_GROSS_NOTIONAL="
                  << synthetic_max_gross_notional << "\n";
        std::cout << "SYNTHETIC_MAX_OPEN_POSITIONS="
                  << synthetic_max_open_positions << "\n";
    }
    std::cout << "MAX_PENDING_ENTRY_SCALE_IN_RESERVATIONS="
              << max_pending_entry_scale_in_reservations << "\n";
    std::cout << "MAX_SYMBOL_NOTIONAL="
              << max_symbol_notional << "\n";
    std::cout << "MINIMUM_AVAILABLE_BALANCE_RESERVE="
              << minimum_available_balance_reserve << "\n";
    std::cout << "SIMULATION_MARGIN_RESERVATION_RATE="
              << margin_reservation_rate << "\n";
    std::cout << "MAX_EFFECTIVE_LEVERAGE="
              << max_effective_leverage << "\n";
    std::cout << "MAX_MARGIN_UTILIZATION="
              << max_margin_utilization << "\n";
    std::cout << "MAX_NET_DIRECTIONAL_NOTIONAL="
              << max_net_directional_notional << "\n";
    std::cout << "ACCOUNT_LOSS_BASELINE_ENABLED="
              << (account_loss_limits_enabled ? "true" : "false")
              << "\n";
    std::cout << "ACCOUNT_LOSS_BASELINE_FILE="
              << account_loss_baseline_file.string() << "\n";
    std::cout << "MAX_DAILY_RISK_CAPITAL_LOSS="
              << max_daily_risk_capital_loss << "\n";
    std::cout << "MAX_WEEKLY_RISK_CAPITAL_LOSS="
              << max_weekly_risk_capital_loss << "\n";
    std::cout << "MAX_DAILY_TOTAL_PNL_LOSS="
              << max_daily_total_pnl_loss << "\n";
    std::cout << "MAX_WEEKLY_TOTAL_PNL_LOSS="
              << max_weekly_total_pnl_loss << "\n";
    std::cout << "MAX_ACCOUNT_DRAWDOWN="
              << max_account_drawdown << "\n";
    std::cout << "REALIZED_PNL_PROVIDER="
              << (realized_pnl_required
                      ? "FILE_BACKED_BINANCE_INCOME_V1"
                      : "DISABLED")
              << "\n";
    std::cout << "REALIZED_PNL_STATUS_FILE="
              << realized_pnl_status_file.string() << "\n";
    std::cout << "MAX_REALIZED_PNL_STATUS_AGE_MS="
              << max_realized_pnl_status_age_ms << "\n";
    std::cout << "MAX_DAILY_REALIZED_TRADE_LOSS="
              << max_daily_realized_trade_loss << "\n";
    std::cout << "MAX_WEEKLY_REALIZED_TRADE_LOSS="
              << max_weekly_realized_trade_loss << "\n";
    std::cout << "EXECUTION_JOURNAL=" << journal_path.string() << "\n";
    std::cout << "EXECUTION_STATUS_FILE=" << execution_status_file.string() << "\n";
    std::cout << "SYMBOL_RISK_STATUS_FILE="
              << symbol_risk_status_file.string() << "\n";
    std::cout << "SYMBOL_RISK_UNIVERSE_FILE="
              << symbol_risk_universe_file.string() << "\n";
    std::cout << "SYMBOL_RISK_UNIVERSE_COUNT="
              << symbol_risk_symbols.size() << "\n";
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
    std::cout << "RECOVERED_ACTIVE_EXPOSURE_RESERVATIONS_AT_STARTUP="
              << recovered_reservation_summary.active_reservations << "\n";
    std::cout << "RECOVERED_RESERVED_GROSS_NOTIONAL_AT_STARTUP="
              << recovered_reservation_summary.reserved_gross_notional << "\n";
    std::cout << "RECOVERED_RESERVED_POSITION_SLOTS_AT_STARTUP="
              << recovered_reservation_summary.reserved_position_slots << "\n";
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
