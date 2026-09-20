#pragma once

#include <atomic>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

#include "astu/ipc/flat_json.hpp"
#include "astu/ipc/simulation_protocol.hpp"

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace astu::execution {

class ExecutionStatusPublisher {
public:
    ExecutionStatusPublisher(
        std::filesystem::path path,
        std::string data_provider,
        std::string risk_provider,
        std::string instrument_provider,
        bool instrument_rules_required,
        std::string position_provider,
        std::string journal_path)
        : path_(std::move(path)),
          data_provider_(std::move(data_provider)),
          risk_provider_(std::move(risk_provider)),
          instrument_provider_(std::move(instrument_provider)),
          instrument_rules_required_(instrument_rules_required),
          position_provider_(std::move(position_provider)),
          journal_path_(std::move(journal_path)) {}

    void set_ready(bool journal_ready, bool pipe_ready) {
        std::lock_guard<std::mutex> lock(mu_);
        lifecycle_state_ = "READY";
        journal_ready_ = journal_ready;
        pipe_ready_ = pipe_ready;
        detail_ = "simulation execution host ready";
    }

    void set_degraded(std::string detail) {
        std::lock_guard<std::mutex> lock(mu_);
        lifecycle_state_ = "DEGRADED";
        detail_ = std::move(detail);
    }

    void set_order_state_metrics(
        std::size_t recovered_orders_at_startup,
        std::size_t tracked_orders,
        std::uint64_t order_transition_count,
        std::uint64_t recovered_reconciliation_events_at_startup,
        std::uint64_t reconciliation_event_count) noexcept {
        recovered_orders_at_startup_.store(
            static_cast<std::uint64_t>(recovered_orders_at_startup),
            std::memory_order_relaxed);
        tracked_orders_.store(
            static_cast<std::uint64_t>(tracked_orders),
            std::memory_order_relaxed);
        order_transition_count_.store(
            order_transition_count,
            std::memory_order_relaxed);
        recovered_reconciliation_events_at_startup_.store(
            recovered_reconciliation_events_at_startup,
            std::memory_order_relaxed);
        reconciliation_event_count_.store(
            reconciliation_event_count,
            std::memory_order_relaxed);
    }

    void set_startup_order_reconciliation(
        std::string provider,
        bool required,
        std::uint64_t tracked,
        std::uint64_t matched,
        std::uint64_t marked_unknown,
        std::uint64_t unresolved) {
        std::lock_guard<std::mutex> lock(mu_);
        startup_order_snapshot_provider_ = std::move(provider);
        startup_order_snapshot_required_ = required;
        startup_order_tracked_ = tracked;
        startup_order_matched_ = matched;
        startup_order_marked_unknown_ = marked_unknown;
        startup_order_unresolved_ = unresolved;
    }

    void set_runtime_order_reconciliation(
        bool enabled,
        std::uint64_t last_sweep_utc_ms,
        std::uint64_t sweep_count,
        std::uint64_t tracked_nonterminal,
        std::uint64_t matched,
        std::uint64_t marked_unknown,
        std::uint64_t unresolved,
        std::uint64_t source_unavailable,
        std::uint64_t terminal_skipped,
        std::uint64_t concurrent_state_changes,
        std::uint64_t sweep_errors) {
        std::lock_guard<std::mutex> lock(mu_);
        runtime_order_reconciliation_enabled_ = enabled;
        runtime_order_last_sweep_utc_ms_ = last_sweep_utc_ms;
        runtime_order_sweep_count_ = sweep_count;
        runtime_order_tracked_nonterminal_ = tracked_nonterminal;
        runtime_order_matched_ = matched;
        runtime_order_marked_unknown_ = marked_unknown;
        runtime_order_unresolved_ = unresolved;
        runtime_order_source_unavailable_ = source_unavailable;
        runtime_order_terminal_skipped_ = terminal_skipped;
        runtime_order_concurrent_state_changes_ =
            concurrent_state_changes;
        runtime_order_sweep_errors_ = sweep_errors;
    }

    void set_projected_risk_limits(
        std::uint64_t max_pending_entry_scale_in_reservations,
        double max_symbol_notional,
        double minimum_available_balance_reserve,
        double margin_reservation_rate,
        double max_effective_leverage,
        double max_margin_utilization,
        double max_net_directional_notional) {
        std::lock_guard<std::mutex> lock(mu_);
        max_pending_entry_scale_in_reservations_ =
            max_pending_entry_scale_in_reservations;
        max_symbol_notional_ = max_symbol_notional;
        minimum_available_balance_reserve_ =
            minimum_available_balance_reserve;
        margin_reservation_rate_ =
            margin_reservation_rate;
        max_effective_leverage_ =
            max_effective_leverage;
        max_margin_utilization_ =
            max_margin_utilization;
        max_net_directional_notional_ =
            max_net_directional_notional;
    }

    void set_account_loss_policy(
        bool enabled,
        std::string baseline_file,
        double max_daily_risk_capital_loss,
        double max_weekly_risk_capital_loss,
        double max_daily_total_pnl_loss,
        double max_weekly_total_pnl_loss,
        double max_account_drawdown) {
        std::lock_guard<std::mutex> lock(mu_);
        account_loss_baseline_enabled_ = enabled;
        account_loss_baseline_file_ = std::move(baseline_file);
        max_daily_risk_capital_loss_ =
            max_daily_risk_capital_loss;
        max_weekly_risk_capital_loss_ =
            max_weekly_risk_capital_loss;
        max_daily_total_pnl_loss_ =
            max_daily_total_pnl_loss;
        max_weekly_total_pnl_loss_ =
            max_weekly_total_pnl_loss;
        max_account_drawdown_ =
            max_account_drawdown;
    }

    void set_account_loss_metrics(
        bool ready,
        std::uint64_t utc_day_index,
        std::uint64_t utc_week_start_day_index,
        double daily_start_risk_capital,
        double weekly_start_risk_capital,
        double daily_start_margin_balance,
        double weekly_start_margin_balance,
        double high_water_margin_balance,
        double daily_risk_capital_loss,
        double weekly_risk_capital_loss,
        double daily_total_pnl_loss,
        double weekly_total_pnl_loss,
        double account_drawdown) {
        std::lock_guard<std::mutex> lock(mu_);
        account_loss_metrics_ready_ = ready;
        account_loss_utc_day_index_ = utc_day_index;
        account_loss_utc_week_start_day_index_ =
            utc_week_start_day_index;
        daily_start_risk_capital_ = daily_start_risk_capital;
        weekly_start_risk_capital_ = weekly_start_risk_capital;
        daily_start_margin_balance_ = daily_start_margin_balance;
        weekly_start_margin_balance_ = weekly_start_margin_balance;
        high_water_margin_balance_ = high_water_margin_balance;
        daily_risk_capital_loss_ = daily_risk_capital_loss;
        weekly_risk_capital_loss_ = weekly_risk_capital_loss;
        daily_total_pnl_loss_ = daily_total_pnl_loss;
        weekly_total_pnl_loss_ = weekly_total_pnl_loss;
        account_drawdown_ = account_drawdown;
    }

    void set_realized_pnl_status(
        std::string provider,
        bool required,
        std::string status_file,
        bool ready,
        std::string settlement_asset,
        double daily_realized_trade_pnl,
        double weekly_realized_trade_pnl,
        double daily_realized_trade_loss,
        double weekly_realized_trade_loss,
        double daily_funding_fee,
        double weekly_funding_fee,
        double daily_commission,
        double weekly_commission,
        double daily_net_trading_income,
        double weekly_net_trading_income,
        std::uint64_t records_in_current_week,
        std::uint64_t ignored_income_records,
        double max_daily_realized_trade_loss,
        double max_weekly_realized_trade_loss) {
        std::lock_guard<std::mutex> lock(mu_);
        realized_pnl_provider_ = std::move(provider);
        realized_pnl_required_ = required;
        realized_pnl_status_file_ = std::move(status_file);
        realized_pnl_ready_ = ready;
        realized_pnl_settlement_asset_ = std::move(settlement_asset);
        daily_realized_trade_pnl_ = daily_realized_trade_pnl;
        weekly_realized_trade_pnl_ = weekly_realized_trade_pnl;
        daily_realized_trade_loss_ = daily_realized_trade_loss;
        weekly_realized_trade_loss_ = weekly_realized_trade_loss;
        daily_funding_fee_ = daily_funding_fee;
        weekly_funding_fee_ = weekly_funding_fee;
        daily_commission_ = daily_commission;
        weekly_commission_ = weekly_commission;
        daily_net_trading_income_ = daily_net_trading_income;
        weekly_net_trading_income_ = weekly_net_trading_income;
        realized_pnl_records_in_current_week_ = records_in_current_week;
        realized_pnl_ignored_income_records_ = ignored_income_records;
        max_daily_realized_trade_loss_ = max_daily_realized_trade_loss;
        max_weekly_realized_trade_loss_ = max_weekly_realized_trade_loss;
    }

    void set_exposure_reservation_metrics(
        std::uint64_t recovered_active_at_startup,
        std::uint64_t active_reservations,
        double reserved_gross_notional,
        double reserved_available_balance,
        double reserved_net_directional_notional,
        std::uint32_t reserved_position_slots,
        std::uint64_t create_count,
        std::uint64_t release_count,
        std::uint64_t implicit_release_count,
        std::uint64_t reconstructed_count) {
        std::lock_guard<std::mutex> lock(mu_);
        recovered_active_exposure_reservations_at_startup_ =
            recovered_active_at_startup;
        active_exposure_reservations_ = active_reservations;
        reserved_gross_notional_ = reserved_gross_notional;
        reserved_available_balance_ = reserved_available_balance;
        reserved_net_directional_notional_ =
            reserved_net_directional_notional;
        reserved_position_slots_ = reserved_position_slots;
        exposure_reservation_create_count_ = create_count;
        exposure_reservation_release_count_ = release_count;
        exposure_reservation_implicit_release_count_ =
            implicit_release_count;
        exposure_reservation_reconstructed_count_ =
            reconstructed_count;
    }

    void set_account_risk_observation(
        bool ready,
        std::uint64_t observed_unix_ms,
        std::string risk_state,
        double current_risk_capital,
        double current_available_balance,
        double projected_available_balance,
        double current_gross_notional,
        double projected_gross_notional,
        double max_gross_notional,
        std::uint32_t current_open_positions,
        std::uint32_t projected_open_positions,
        std::uint32_t max_open_positions,
        bool margin_metrics_ready,
        double current_margin_balance,
        double current_initial_margin,
        double projected_initial_margin,
        double projected_effective_leverage,
        double projected_margin_utilization,
        bool net_directional_ready,
        double current_net_directional_notional,
        double projected_net_directional_notional) {
        std::lock_guard<std::mutex> lock(mu_);
        account_risk_observation_ready_ = ready;
        account_risk_observed_unix_ms_ = observed_unix_ms;
        account_risk_state_ = std::move(risk_state);
        current_risk_capital_ = current_risk_capital;
        current_available_balance_ = current_available_balance;
        projected_available_balance_ = projected_available_balance;
        current_gross_notional_ = current_gross_notional;
        projected_gross_notional_ = projected_gross_notional;
        current_max_gross_notional_ = max_gross_notional;
        current_open_positions_ = current_open_positions;
        projected_open_positions_ = projected_open_positions;
        current_max_open_positions_ = max_open_positions;
        account_margin_metrics_ready_ = margin_metrics_ready;
        current_margin_balance_ = current_margin_balance;
        current_initial_margin_ = current_initial_margin;
        projected_initial_margin_ = projected_initial_margin;
        projected_effective_leverage_ = projected_effective_leverage;
        projected_margin_utilization_ = projected_margin_utilization;
        account_net_directional_ready_ = net_directional_ready;
        current_net_directional_notional_ = current_net_directional_notional;
        projected_net_directional_notional_ = projected_net_directional_notional;
    }

    void record_response(const astu::ipc::SimulationResponse& response) {
        requests_seen_.fetch_add(1, std::memory_order_relaxed);
        std::lock_guard<std::mutex> lock(mu_);
        last_decision_code_ = astu::ipc::decision_to_string(response.decision_code);
        detail_ = response.reason;
    }

    void publish() const {
        std::lock_guard<std::mutex> publish_lock(publish_mu_);
        const auto generated_ms = utc_now_ms();

        std::string lifecycle;
        std::string detail;
        std::string last_decision;
        bool journal_ready = false;
        bool pipe_ready = false;
        std::string startup_order_snapshot_provider;
        bool startup_order_snapshot_required = false;
        std::uint64_t startup_order_tracked = 0;
        std::uint64_t startup_order_matched = 0;
        std::uint64_t startup_order_marked_unknown = 0;
        std::uint64_t startup_order_unresolved = 0;
        bool runtime_order_reconciliation_enabled = false;
        std::uint64_t runtime_order_last_sweep_utc_ms = 0;
        std::uint64_t runtime_order_sweep_count = 0;
        std::uint64_t runtime_order_tracked_nonterminal = 0;
        std::uint64_t runtime_order_matched = 0;
        std::uint64_t runtime_order_marked_unknown = 0;
        std::uint64_t runtime_order_unresolved = 0;
        std::uint64_t runtime_order_source_unavailable = 0;
        std::uint64_t runtime_order_terminal_skipped = 0;
        std::uint64_t runtime_order_concurrent_state_changes = 0;
        std::uint64_t runtime_order_sweep_errors = 0;
        std::uint64_t recovered_active_exposure_reservations_at_startup = 0;
        std::uint64_t active_exposure_reservations = 0;
        double reserved_gross_notional = 0.0;
        double reserved_available_balance = 0.0;
        double reserved_net_directional_notional = 0.0;
        std::uint32_t reserved_position_slots = 0;
        std::uint64_t exposure_reservation_create_count = 0;
        std::uint64_t exposure_reservation_release_count = 0;
        std::uint64_t exposure_reservation_implicit_release_count = 0;
        std::uint64_t exposure_reservation_reconstructed_count = 0;
        std::uint64_t max_pending_entry_scale_in_reservations = 0;
        double max_symbol_notional = 0.0;
        double minimum_available_balance_reserve = 0.0;
        double margin_reservation_rate = 0.0;
        double max_effective_leverage = 0.0;
        double max_margin_utilization = 0.0;
        double max_net_directional_notional = 0.0;
        bool account_risk_observation_ready = false;
        std::uint64_t account_risk_observed_unix_ms = 0;
        std::string account_risk_state;
        double current_risk_capital = 0.0;
        double current_available_balance = 0.0;
        double projected_available_balance = 0.0;
        double current_gross_notional = 0.0;
        double projected_gross_notional = 0.0;
        double current_max_gross_notional = 0.0;
        std::uint32_t current_open_positions = 0;
        std::uint32_t projected_open_positions = 0;
        std::uint32_t current_max_open_positions = 0;
        bool account_margin_metrics_ready = false;
        double current_margin_balance = 0.0;
        double current_initial_margin = 0.0;
        double projected_initial_margin = 0.0;
        double projected_effective_leverage = 0.0;
        double projected_margin_utilization = 0.0;
        bool account_net_directional_ready = false;
        double current_net_directional_notional = 0.0;
        double projected_net_directional_notional = 0.0;
        bool account_loss_baseline_enabled = false;
        std::string account_loss_baseline_file;
        bool account_loss_metrics_ready = false;
        std::uint64_t account_loss_utc_day_index = 0;
        std::uint64_t account_loss_utc_week_start_day_index = 0;
        double daily_start_risk_capital = 0.0;
        double weekly_start_risk_capital = 0.0;
        double daily_start_margin_balance = 0.0;
        double weekly_start_margin_balance = 0.0;
        double high_water_margin_balance = 0.0;
        double daily_risk_capital_loss = 0.0;
        double weekly_risk_capital_loss = 0.0;
        double daily_total_pnl_loss = 0.0;
        double weekly_total_pnl_loss = 0.0;
        double account_drawdown = 0.0;
        double max_daily_risk_capital_loss = 0.0;
        double max_weekly_risk_capital_loss = 0.0;
        double max_daily_total_pnl_loss = 0.0;
        double max_weekly_total_pnl_loss = 0.0;
        double max_account_drawdown = 0.0;
        std::string realized_pnl_provider;
        bool realized_pnl_required = false;
        std::string realized_pnl_status_file;
        bool realized_pnl_ready = false;
        std::string realized_pnl_settlement_asset;
        double daily_realized_trade_pnl = 0.0;
        double weekly_realized_trade_pnl = 0.0;
        double daily_realized_trade_loss = 0.0;
        double weekly_realized_trade_loss = 0.0;
        double daily_funding_fee = 0.0;
        double weekly_funding_fee = 0.0;
        double daily_commission = 0.0;
        double weekly_commission = 0.0;
        double daily_net_trading_income = 0.0;
        double weekly_net_trading_income = 0.0;
        std::uint64_t realized_pnl_records_in_current_week = 0;
        std::uint64_t realized_pnl_ignored_income_records = 0;
        double max_daily_realized_trade_loss = 0.0;
        double max_weekly_realized_trade_loss = 0.0;
        {
            std::lock_guard<std::mutex> lock(mu_);
            lifecycle = lifecycle_state_;
            detail = detail_;
            last_decision = last_decision_code_;
            journal_ready = journal_ready_;
            pipe_ready = pipe_ready_;
            startup_order_snapshot_provider =
                startup_order_snapshot_provider_;
            startup_order_snapshot_required =
                startup_order_snapshot_required_;
            startup_order_tracked = startup_order_tracked_;
            startup_order_matched = startup_order_matched_;
            startup_order_marked_unknown =
                startup_order_marked_unknown_;
            startup_order_unresolved =
                startup_order_unresolved_;
            runtime_order_reconciliation_enabled =
                runtime_order_reconciliation_enabled_;
            runtime_order_last_sweep_utc_ms =
                runtime_order_last_sweep_utc_ms_;
            runtime_order_sweep_count =
                runtime_order_sweep_count_;
            runtime_order_tracked_nonterminal =
                runtime_order_tracked_nonterminal_;
            runtime_order_matched =
                runtime_order_matched_;
            runtime_order_marked_unknown =
                runtime_order_marked_unknown_;
            runtime_order_unresolved =
                runtime_order_unresolved_;
            runtime_order_source_unavailable =
                runtime_order_source_unavailable_;
            runtime_order_terminal_skipped =
                runtime_order_terminal_skipped_;
            runtime_order_concurrent_state_changes =
                runtime_order_concurrent_state_changes_;
            runtime_order_sweep_errors =
                runtime_order_sweep_errors_;
            recovered_active_exposure_reservations_at_startup =
                recovered_active_exposure_reservations_at_startup_;
            active_exposure_reservations =
                active_exposure_reservations_;
            reserved_gross_notional =
                reserved_gross_notional_;
            reserved_available_balance =
                reserved_available_balance_;
            reserved_net_directional_notional =
                reserved_net_directional_notional_;
            reserved_position_slots =
                reserved_position_slots_;
            exposure_reservation_create_count =
                exposure_reservation_create_count_;
            exposure_reservation_release_count =
                exposure_reservation_release_count_;
            exposure_reservation_implicit_release_count =
                exposure_reservation_implicit_release_count_;
            exposure_reservation_reconstructed_count =
                exposure_reservation_reconstructed_count_;
            max_pending_entry_scale_in_reservations =
                max_pending_entry_scale_in_reservations_;
            max_symbol_notional =
                max_symbol_notional_;
            minimum_available_balance_reserve =
                minimum_available_balance_reserve_;
            margin_reservation_rate =
                margin_reservation_rate_;
            max_effective_leverage =
                max_effective_leverage_;
            max_margin_utilization =
                max_margin_utilization_;
            max_net_directional_notional =
                max_net_directional_notional_;
            account_risk_observation_ready =
                account_risk_observation_ready_;
            account_risk_observed_unix_ms =
                account_risk_observed_unix_ms_;
            account_risk_state = account_risk_state_;
            current_risk_capital = current_risk_capital_;
            current_available_balance = current_available_balance_;
            projected_available_balance =
                projected_available_balance_;
            current_gross_notional = current_gross_notional_;
            projected_gross_notional = projected_gross_notional_;
            current_max_gross_notional =
                current_max_gross_notional_;
            current_open_positions = current_open_positions_;
            projected_open_positions = projected_open_positions_;
            current_max_open_positions =
                current_max_open_positions_;
            account_margin_metrics_ready =
                account_margin_metrics_ready_;
            current_margin_balance = current_margin_balance_;
            current_initial_margin = current_initial_margin_;
            projected_initial_margin = projected_initial_margin_;
            projected_effective_leverage =
                projected_effective_leverage_;
            projected_margin_utilization =
                projected_margin_utilization_;
            account_net_directional_ready =
                account_net_directional_ready_;
            current_net_directional_notional =
                current_net_directional_notional_;
            projected_net_directional_notional =
                projected_net_directional_notional_;
            account_loss_baseline_enabled =
                account_loss_baseline_enabled_;
            account_loss_baseline_file =
                account_loss_baseline_file_;
            account_loss_metrics_ready =
                account_loss_metrics_ready_;
            account_loss_utc_day_index =
                account_loss_utc_day_index_;
            account_loss_utc_week_start_day_index =
                account_loss_utc_week_start_day_index_;
            daily_start_risk_capital =
                daily_start_risk_capital_;
            weekly_start_risk_capital =
                weekly_start_risk_capital_;
            daily_start_margin_balance =
                daily_start_margin_balance_;
            weekly_start_margin_balance =
                weekly_start_margin_balance_;
            high_water_margin_balance =
                high_water_margin_balance_;
            daily_risk_capital_loss =
                daily_risk_capital_loss_;
            weekly_risk_capital_loss =
                weekly_risk_capital_loss_;
            daily_total_pnl_loss =
                daily_total_pnl_loss_;
            weekly_total_pnl_loss =
                weekly_total_pnl_loss_;
            account_drawdown =
                account_drawdown_;
            max_daily_risk_capital_loss =
                max_daily_risk_capital_loss_;
            max_weekly_risk_capital_loss =
                max_weekly_risk_capital_loss_;
            max_daily_total_pnl_loss =
                max_daily_total_pnl_loss_;
            max_weekly_total_pnl_loss =
                max_weekly_total_pnl_loss_;
            max_account_drawdown =
                max_account_drawdown_;
            realized_pnl_provider = realized_pnl_provider_;
            realized_pnl_required = realized_pnl_required_;
            realized_pnl_status_file = realized_pnl_status_file_;
            realized_pnl_ready = realized_pnl_ready_;
            realized_pnl_settlement_asset =
                realized_pnl_settlement_asset_;
            daily_realized_trade_pnl = daily_realized_trade_pnl_;
            weekly_realized_trade_pnl = weekly_realized_trade_pnl_;
            daily_realized_trade_loss = daily_realized_trade_loss_;
            weekly_realized_trade_loss = weekly_realized_trade_loss_;
            daily_funding_fee = daily_funding_fee_;
            weekly_funding_fee = weekly_funding_fee_;
            daily_commission = daily_commission_;
            weekly_commission = weekly_commission_;
            daily_net_trading_income = daily_net_trading_income_;
            weekly_net_trading_income = weekly_net_trading_income_;
            realized_pnl_records_in_current_week =
                realized_pnl_records_in_current_week_;
            realized_pnl_ignored_income_records =
                realized_pnl_ignored_income_records_;
            max_daily_realized_trade_loss =
                max_daily_realized_trade_loss_;
            max_weekly_realized_trade_loss =
                max_weekly_realized_trade_loss_;
        }

        std::ostringstream out;
        out
            << "{"
            << "\"schemaVersion\":1"
            << ",\"messageType\":\"ExecutionStatus.v1\""
            << ",\"generatedUnixMs\":" << generated_ms
            << ",\"processId\":" << process_id()
            << ",\"lifecycleState\":\"" << astu::ipc::json_escape(lifecycle) << "\""
            << ",\"dataProvider\":\"" << astu::ipc::json_escape(data_provider_) << "\""
            << ",\"riskProvider\":\"" << astu::ipc::json_escape(risk_provider_) << "\""
            << ",\"instrumentProvider\":\"" << astu::ipc::json_escape(instrument_provider_) << "\""
            << ",\"instrumentRulesRequired\":" << (instrument_rules_required_ ? "true" : "false")
            << ",\"positionProvider\":\"" << astu::ipc::json_escape(position_provider_) << "\""
            << ",\"positionStateRequiredForScaleActions\":true"
            << ",\"startupOrderSnapshotProvider\":\""
            << astu::ipc::json_escape(startup_order_snapshot_provider)
            << "\""
            << ",\"startupOrderSnapshotRequired\":"
            << (startup_order_snapshot_required ? "true" : "false")
            << ",\"startupOrderTracked\":" << startup_order_tracked
            << ",\"startupOrderMatched\":" << startup_order_matched
            << ",\"startupOrderMarkedUnknown\":"
            << startup_order_marked_unknown
            << ",\"startupOrderUnresolved\":"
            << startup_order_unresolved
            << ",\"runtimeOrderReconciliationEnabled\":"
            << (runtime_order_reconciliation_enabled ? "true" : "false")
            << ",\"runtimeOrderLastSweepUtcMs\":"
            << runtime_order_last_sweep_utc_ms
            << ",\"runtimeOrderSweepCount\":"
            << runtime_order_sweep_count
            << ",\"runtimeOrderTrackedNonterminal\":"
            << runtime_order_tracked_nonterminal
            << ",\"runtimeOrderMatched\":"
            << runtime_order_matched
            << ",\"runtimeOrderMarkedUnknown\":"
            << runtime_order_marked_unknown
            << ",\"runtimeOrderUnresolved\":"
            << runtime_order_unresolved
            << ",\"runtimeOrderSourceUnavailable\":"
            << runtime_order_source_unavailable
            << ",\"runtimeOrderTerminalSkipped\":"
            << runtime_order_terminal_skipped
            << ",\"runtimeOrderConcurrentStateChanges\":"
            << runtime_order_concurrent_state_changes
            << ",\"runtimeOrderSweepErrors\":"
            << runtime_order_sweep_errors
            << ",\"recoveredActiveExposureReservationsAtStartup\":"
            << recovered_active_exposure_reservations_at_startup
            << ",\"activeExposureReservations\":"
            << active_exposure_reservations
            << ",\"reservedGrossNotional\":"
            << reserved_gross_notional
            << ",\"reservedAvailableBalance\":"
            << reserved_available_balance
            << ",\"reservedNetDirectionalNotional\":"
            << reserved_net_directional_notional
            << ",\"reservedPositionSlots\":"
            << reserved_position_slots
            << ",\"exposureReservationCreateCount\":"
            << exposure_reservation_create_count
            << ",\"exposureReservationReleaseCount\":"
            << exposure_reservation_release_count
            << ",\"exposureReservationImplicitReleaseCount\":"
            << exposure_reservation_implicit_release_count
            << ",\"exposureReservationReconstructedCount\":"
            << exposure_reservation_reconstructed_count
            << ",\"maxPendingEntryScaleInReservations\":"
            << max_pending_entry_scale_in_reservations
            << ",\"maxSymbolNotional\":"
            << max_symbol_notional
            << ",\"minimumAvailableBalanceReserve\":"
            << minimum_available_balance_reserve
            << ",\"simulationMarginReservationRate\":"
            << margin_reservation_rate
            << ",\"maxEffectiveLeverage\":"
            << max_effective_leverage
            << ",\"maxMarginUtilization\":"
            << max_margin_utilization
            << ",\"maxNetDirectionalNotional\":"
            << max_net_directional_notional
            << ",\"accountRiskObservationReady\":"
            << (account_risk_observation_ready ? "true" : "false")
            << ",\"accountRiskObservedUnixMs\":"
            << account_risk_observed_unix_ms
            << ",\"accountRiskState\":\""
            << astu::ipc::json_escape(account_risk_state) << "\""
            << ",\"currentRiskCapital\":"
            << current_risk_capital
            << ",\"currentAvailableBalance\":"
            << current_available_balance
            << ",\"projectedAvailableBalance\":"
            << projected_available_balance
            << ",\"currentGrossNotional\":"
            << current_gross_notional
            << ",\"projectedGrossNotional\":"
            << projected_gross_notional
            << ",\"currentMaxGrossNotional\":"
            << current_max_gross_notional
            << ",\"currentOpenPositions\":"
            << current_open_positions
            << ",\"projectedOpenPositions\":"
            << projected_open_positions
            << ",\"currentMaxOpenPositions\":"
            << current_max_open_positions
            << ",\"accountMarginMetricsReady\":"
            << (account_margin_metrics_ready ? "true" : "false")
            << ",\"currentMarginBalance\":"
            << current_margin_balance
            << ",\"currentInitialMargin\":"
            << current_initial_margin
            << ",\"projectedInitialMargin\":"
            << projected_initial_margin
            << ",\"projectedEffectiveLeverage\":"
            << projected_effective_leverage
            << ",\"projectedMarginUtilization\":"
            << projected_margin_utilization
            << ",\"accountNetDirectionalReady\":"
            << (account_net_directional_ready ? "true" : "false")
            << ",\"currentNetDirectionalNotional\":"
            << current_net_directional_notional
            << ",\"projectedNetDirectionalNotional\":"
            << projected_net_directional_notional
            << ",\"accountLossBaselineEnabled\":"
            << (account_loss_baseline_enabled ? "true" : "false")
            << ",\"accountLossBaselineFile\":\""
            << astu::ipc::json_escape(account_loss_baseline_file) << "\""
            << ",\"accountLossMetricsReady\":"
            << (account_loss_metrics_ready ? "true" : "false")
            << ",\"accountLossUtcDayIndex\":"
            << account_loss_utc_day_index
            << ",\"accountLossUtcWeekStartDayIndex\":"
            << account_loss_utc_week_start_day_index
            << ",\"dailyStartRiskCapital\":"
            << daily_start_risk_capital
            << ",\"weeklyStartRiskCapital\":"
            << weekly_start_risk_capital
            << ",\"dailyStartMarginBalance\":"
            << daily_start_margin_balance
            << ",\"weeklyStartMarginBalance\":"
            << weekly_start_margin_balance
            << ",\"highWaterMarginBalance\":"
            << high_water_margin_balance
            << ",\"dailyRiskCapitalLoss\":"
            << daily_risk_capital_loss
            << ",\"weeklyRiskCapitalLoss\":"
            << weekly_risk_capital_loss
            << ",\"dailyTotalPnlLoss\":"
            << daily_total_pnl_loss
            << ",\"weeklyTotalPnlLoss\":"
            << weekly_total_pnl_loss
            << ",\"accountDrawdown\":"
            << account_drawdown
            << ",\"maxDailyRiskCapitalLoss\":"
            << max_daily_risk_capital_loss
            << ",\"maxWeeklyRiskCapitalLoss\":"
            << max_weekly_risk_capital_loss
            << ",\"maxDailyTotalPnlLoss\":"
            << max_daily_total_pnl_loss
            << ",\"maxWeeklyTotalPnlLoss\":"
            << max_weekly_total_pnl_loss
            << ",\"maxAccountDrawdown\":"
            << max_account_drawdown
            << ",\"realizedPnlProvider\":\""
            << astu::ipc::json_escape(realized_pnl_provider) << "\""
            << ",\"realizedPnlRequired\":"
            << (realized_pnl_required ? "true" : "false")
            << ",\"realizedPnlStatusFile\":\""
            << astu::ipc::json_escape(realized_pnl_status_file) << "\""
            << ",\"realizedPnlReady\":"
            << (realized_pnl_ready ? "true" : "false")
            << ",\"realizedPnlSettlementAsset\":\""
            << astu::ipc::json_escape(realized_pnl_settlement_asset)
            << "\""
            << ",\"dailyRealizedTradePnl\":"
            << daily_realized_trade_pnl
            << ",\"weeklyRealizedTradePnl\":"
            << weekly_realized_trade_pnl
            << ",\"dailyRealizedTradeLoss\":"
            << daily_realized_trade_loss
            << ",\"weeklyRealizedTradeLoss\":"
            << weekly_realized_trade_loss
            << ",\"dailyFundingFee\":"
            << daily_funding_fee
            << ",\"weeklyFundingFee\":"
            << weekly_funding_fee
            << ",\"dailyCommission\":"
            << daily_commission
            << ",\"weeklyCommission\":"
            << weekly_commission
            << ",\"dailyNetTradingIncome\":"
            << daily_net_trading_income
            << ",\"weeklyNetTradingIncome\":"
            << weekly_net_trading_income
            << ",\"realizedPnlRecordsInCurrentWeek\":"
            << realized_pnl_records_in_current_week
            << ",\"realizedPnlIgnoredIncomeRecords\":"
            << realized_pnl_ignored_income_records
            << ",\"maxDailyRealizedTradeLoss\":"
            << max_daily_realized_trade_loss
            << ",\"maxWeeklyRealizedTradeLoss\":"
            << max_weekly_realized_trade_loss
            << ",\"journalPath\":\"" << astu::ipc::json_escape(journal_path_) << "\""
            << ",\"journalReady\":" << (journal_ready ? "true" : "false")
            << ",\"pipeReady\":" << (pipe_ready ? "true" : "false")
            << ",\"orderRoutingEnabled\":false"
            << ",\"requestsSeen\":" << requests_seen_.load(std::memory_order_relaxed)
            << ",\"recoveredOrdersAtStartup\":" << recovered_orders_at_startup_.load(std::memory_order_relaxed)
            << ",\"trackedOrders\":" << tracked_orders_.load(std::memory_order_relaxed)
            << ",\"orderTransitionCount\":" << order_transition_count_.load(std::memory_order_relaxed)
            << ",\"recoveredReconciliationEventsAtStartup\":" << recovered_reconciliation_events_at_startup_.load(std::memory_order_relaxed)
            << ",\"reconciliationEventCount\":" << reconciliation_event_count_.load(std::memory_order_relaxed)
            << ",\"lastDecisionCode\":";
        if (last_decision.empty()) {
            out << "null";
        } else {
            out << "\"" << astu::ipc::json_escape(last_decision) << "\"";
        }
        out
            << ",\"detail\":\"" << astu::ipc::json_escape(detail) << "\""
            << "}\n";

        write_atomic(out.str());
    }

    const std::filesystem::path& path() const noexcept {
        return path_;
    }

private:
    static std::uint64_t utc_now_ms() {
        const auto now = std::chrono::system_clock::now().time_since_epoch();
        return static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::milliseconds>(now).count());
    }

    static std::uint64_t process_id() noexcept {
#ifdef _WIN32
        return static_cast<std::uint64_t>(GetCurrentProcessId());
#else
        return 0;
#endif
    }

    void write_atomic(const std::string& text) const {
        if (!path_.parent_path().empty()) {
            std::filesystem::create_directories(path_.parent_path());
        }
        const auto tmp = path_.string() + ".tmp";
        {
            std::ofstream out(tmp, std::ios::binary | std::ios::trunc);
            if (!out) {
                throw std::runtime_error("cannot open execution status temp file");
            }
            out.write(text.data(), static_cast<std::streamsize>(text.size()));
            out.flush();
            if (!out) {
                throw std::runtime_error("cannot write execution status temp file");
            }
        }
#ifdef _WIN32
        if (!MoveFileExA(
                tmp.c_str(),
                path_.string().c_str(),
                MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
            std::filesystem::remove(tmp);
            throw std::runtime_error(
                "cannot publish execution status error=" +
                std::to_string(GetLastError()));
        }
#else
        std::filesystem::rename(tmp, path_);
#endif
    }

    std::filesystem::path path_;
    std::string data_provider_;
    std::string risk_provider_;
    std::string instrument_provider_;
    bool instrument_rules_required_{false};
    std::string position_provider_;
    std::string journal_path_;
    mutable std::mutex mu_;
    mutable std::mutex publish_mu_;
    std::string lifecycle_state_{"STARTING"};
    std::string detail_{"simulation execution host starting"};
    std::string last_decision_code_;
    std::string startup_order_snapshot_provider_{"DISABLED"};
    bool startup_order_snapshot_required_{false};
    std::uint64_t startup_order_tracked_{0};
    std::uint64_t startup_order_matched_{0};
    std::uint64_t startup_order_marked_unknown_{0};
    std::uint64_t startup_order_unresolved_{0};
    bool runtime_order_reconciliation_enabled_{false};
    std::uint64_t runtime_order_last_sweep_utc_ms_{0};
    std::uint64_t runtime_order_sweep_count_{0};
    std::uint64_t runtime_order_tracked_nonterminal_{0};
    std::uint64_t runtime_order_matched_{0};
    std::uint64_t runtime_order_marked_unknown_{0};
    std::uint64_t runtime_order_unresolved_{0};
    std::uint64_t runtime_order_source_unavailable_{0};
    std::uint64_t runtime_order_terminal_skipped_{0};
    std::uint64_t runtime_order_concurrent_state_changes_{0};
    std::uint64_t runtime_order_sweep_errors_{0};
    std::uint64_t recovered_active_exposure_reservations_at_startup_{0};
    std::uint64_t active_exposure_reservations_{0};
    double reserved_gross_notional_{0.0};
    double reserved_available_balance_{0.0};
    double reserved_net_directional_notional_{0.0};
    std::uint32_t reserved_position_slots_{0};
    std::uint64_t exposure_reservation_create_count_{0};
    std::uint64_t exposure_reservation_release_count_{0};
    std::uint64_t exposure_reservation_implicit_release_count_{0};
    std::uint64_t exposure_reservation_reconstructed_count_{0};
    std::uint64_t max_pending_entry_scale_in_reservations_{0};
    double max_symbol_notional_{0.0};
    double minimum_available_balance_reserve_{0.0};
    double margin_reservation_rate_{0.0};
    double max_effective_leverage_{0.0};
    double max_margin_utilization_{0.0};
    double max_net_directional_notional_{0.0};
    bool account_risk_observation_ready_{false};
    std::uint64_t account_risk_observed_unix_ms_{0};
    std::string account_risk_state_{"UNKNOWN"};
    double current_risk_capital_{0.0};
    double current_available_balance_{0.0};
    double projected_available_balance_{0.0};
    double current_gross_notional_{0.0};
    double projected_gross_notional_{0.0};
    double current_max_gross_notional_{0.0};
    std::uint32_t current_open_positions_{0};
    std::uint32_t projected_open_positions_{0};
    std::uint32_t current_max_open_positions_{0};
    bool account_margin_metrics_ready_{false};
    double current_margin_balance_{0.0};
    double current_initial_margin_{0.0};
    double projected_initial_margin_{0.0};
    double projected_effective_leverage_{0.0};
    double projected_margin_utilization_{0.0};
    bool account_net_directional_ready_{false};
    double current_net_directional_notional_{0.0};
    double projected_net_directional_notional_{0.0};
    bool account_loss_baseline_enabled_{false};
    std::string account_loss_baseline_file_;
    bool account_loss_metrics_ready_{false};
    std::uint64_t account_loss_utc_day_index_{0};
    std::uint64_t account_loss_utc_week_start_day_index_{0};
    double daily_start_risk_capital_{0.0};
    double weekly_start_risk_capital_{0.0};
    double daily_start_margin_balance_{0.0};
    double weekly_start_margin_balance_{0.0};
    double high_water_margin_balance_{0.0};
    double daily_risk_capital_loss_{0.0};
    double weekly_risk_capital_loss_{0.0};
    double daily_total_pnl_loss_{0.0};
    double weekly_total_pnl_loss_{0.0};
    double account_drawdown_{0.0};
    double max_daily_risk_capital_loss_{0.0};
    double max_weekly_risk_capital_loss_{0.0};
    double max_daily_total_pnl_loss_{0.0};
    double max_weekly_total_pnl_loss_{0.0};
    double max_account_drawdown_{0.0};
    std::string realized_pnl_provider_{"DISABLED"};
    bool realized_pnl_required_{false};
    std::string realized_pnl_status_file_;
    bool realized_pnl_ready_{false};
    std::string realized_pnl_settlement_asset_;
    double daily_realized_trade_pnl_{0.0};
    double weekly_realized_trade_pnl_{0.0};
    double daily_realized_trade_loss_{0.0};
    double weekly_realized_trade_loss_{0.0};
    double daily_funding_fee_{0.0};
    double weekly_funding_fee_{0.0};
    double daily_commission_{0.0};
    double weekly_commission_{0.0};
    double daily_net_trading_income_{0.0};
    double weekly_net_trading_income_{0.0};
    std::uint64_t realized_pnl_records_in_current_week_{0};
    std::uint64_t realized_pnl_ignored_income_records_{0};
    double max_daily_realized_trade_loss_{0.0};
    double max_weekly_realized_trade_loss_{0.0};
    bool journal_ready_{false};
    bool pipe_ready_{false};
    std::atomic<std::uint64_t> requests_seen_{0};
    std::atomic<std::uint64_t> recovered_orders_at_startup_{0};
    std::atomic<std::uint64_t> tracked_orders_{0};
    std::atomic<std::uint64_t> order_transition_count_{0};
    std::atomic<std::uint64_t> recovered_reconciliation_events_at_startup_{0};
    std::atomic<std::uint64_t> reconciliation_event_count_{0};
};

}  // namespace astu::execution
