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

    void set_exposure_reservation_metrics(
        std::uint64_t recovered_active_at_startup,
        std::uint64_t active_reservations,
        double reserved_gross_notional,
        std::uint32_t reserved_position_slots,
        std::uint64_t create_count,
        std::uint64_t release_count,
        std::uint64_t implicit_release_count) {
        std::lock_guard<std::mutex> lock(mu_);
        recovered_active_exposure_reservations_at_startup_ =
            recovered_active_at_startup;
        active_exposure_reservations_ = active_reservations;
        reserved_gross_notional_ = reserved_gross_notional;
        reserved_position_slots_ = reserved_position_slots;
        exposure_reservation_create_count_ = create_count;
        exposure_reservation_release_count_ = release_count;
        exposure_reservation_implicit_release_count_ =
            implicit_release_count;
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
        std::uint32_t reserved_position_slots = 0;
        std::uint64_t exposure_reservation_create_count = 0;
        std::uint64_t exposure_reservation_release_count = 0;
        std::uint64_t exposure_reservation_implicit_release_count = 0;
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
            reserved_position_slots =
                reserved_position_slots_;
            exposure_reservation_create_count =
                exposure_reservation_create_count_;
            exposure_reservation_release_count =
                exposure_reservation_release_count_;
            exposure_reservation_implicit_release_count =
                exposure_reservation_implicit_release_count_;
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
            << ",\"reservedPositionSlots\":"
            << reserved_position_slots
            << ",\"exposureReservationCreateCount\":"
            << exposure_reservation_create_count
            << ",\"exposureReservationReleaseCount\":"
            << exposure_reservation_release_count
            << ",\"exposureReservationImplicitReleaseCount\":"
            << exposure_reservation_implicit_release_count
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
    std::uint32_t reserved_position_slots_{0};
    std::uint64_t exposure_reservation_create_count_{0};
    std::uint64_t exposure_reservation_release_count_{0};
    std::uint64_t exposure_reservation_implicit_release_count_{0};
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
