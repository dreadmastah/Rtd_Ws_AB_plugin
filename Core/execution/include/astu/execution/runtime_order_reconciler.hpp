#pragma once

#include <cmath>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>

#include "astu/execution/authoritative_order_snapshot.hpp"
#include "astu/execution/execution_journal.hpp"
#include "astu/execution/order_fsm.hpp"

namespace astu::execution {

struct RuntimeOrderReconciliationReport {
    std::uint64_t tracked_nonterminal_orders{0};
    std::uint64_t matched_orders{0};
    std::uint64_t marked_unknown{0};
    std::uint64_t unresolved_orders{0};
    std::uint64_t source_unavailable_orders{0};
    std::uint64_t terminal_orders_skipped{0};
    std::uint64_t concurrent_state_changes{0};
};

class RuntimeOrderReconciler {
public:
    template <typename Provider>
    static RuntimeOrderReconciliationReport sweep(
        const std::shared_ptr<ExecutionJournal>& journal,
        const Provider& provider,
        std::int64_t utc_ms) {
        if (!journal) {
            throw std::invalid_argument(
                "RuntimeOrderReconciler requires journal");
        }

        RuntimeOrderReconciliationReport report;
        for (const auto& order_id : journal->tracked_order_ids()) {
            const auto state = journal->order_state(order_id);
            const auto intent =
                journal->simulation_order_intent(order_id);
            if (!state.has_value() || !intent.has_value()) {
                throw std::runtime_error(
                    "runtime reconciliation missing persistent order state/intent for " +
                    order_id);
            }

            if (is_terminal_order_state(*state)) {
                ++report.terminal_orders_skipped;
                continue;
            }

            ++report.tracked_nonterminal_orders;
            const auto snapshot = provider(order_id);
            const auto journal_filled =
                journal->reconciled_filled_quantity(order_id);
            const bool quantity_valid =
                snapshot.cumulative_filled_quantity >= -kEpsilon &&
                snapshot.cumulative_filled_quantity <=
                    intent->quantity + kEpsilon;
            const bool exact_match =
                snapshot.ready &&
                quantity_valid &&
                snapshot.state == *state &&
                std::fabs(
                    snapshot.cumulative_filled_quantity -
                    journal_filled) <= kEpsilon;

            if (exact_match) {
                ++report.matched_orders;
                continue;
            }

            if (!snapshot.ready) {
                ++report.source_unavailable_orders;
            }

            if (*state == OrderState::UnknownReconcileRequired) {
                ++report.unresolved_orders;
                continue;
            }

            if (!OrderStateMachine::can_transition(
                    *state,
                    OrderState::UnknownReconcileRequired)) {
                throw std::runtime_error(
                    "runtime order disagreement cannot enter UNKNOWN_RECONCILE_REQUIRED from " +
                    order_state_to_string(*state) +
                    " for " + order_id);
            }

            try {
                journal->append_reconciliation_event(
                    runtime_event_id(order_id, snapshot, utc_ms),
                    order_id,
                    "MARK_UNKNOWN",
                    OrderState::UnknownReconcileRequired,
                    journal_filled,
                    utc_ms,
                    mismatch_detail(
                        *state,
                        snapshot,
                        journal_filled));
                ++report.marked_unknown;
                ++report.unresolved_orders;
            } catch (const std::invalid_argument&) {
                const auto current = journal->order_state(order_id);
                if (!current.has_value()) {
                    throw;
                }
                if (*current == OrderState::UnknownReconcileRequired) {
                    ++report.concurrent_state_changes;
                    ++report.unresolved_orders;
                    continue;
                }
                if (is_terminal_order_state(*current)) {
                    ++report.concurrent_state_changes;
                    ++report.terminal_orders_skipped;
                    continue;
                }
                throw;
            }
        }

        return report;
    }

private:
    static constexpr double kEpsilon = 1e-12;

    static std::string runtime_event_id(
        const std::string& order_id,
        const AuthoritativeSimulationOrderSnapshot& snapshot,
        std::int64_t utc_ms) {
        return "RUNTIME-RECON-" + order_id + "-" +
            std::to_string(utc_ms) + "-" +
            std::to_string(snapshot.generated_unix_ms);
    }

    static std::string snapshot_state_text(
        const AuthoritativeSimulationOrderSnapshot& snapshot) {
        return snapshot.ready
            ? order_state_to_string(snapshot.state)
            : "UNAVAILABLE";
    }

    static std::string mismatch_detail(
        OrderState journal_state,
        const AuthoritativeSimulationOrderSnapshot& snapshot,
        double journal_filled) {
        return
            "runtime authoritative simulation order disagreement; journalState=" +
            order_state_to_string(journal_state) +
            "; snapshotState=" + snapshot_state_text(snapshot) +
            "; journalFilled=" + std::to_string(journal_filled) +
            "; snapshotFilled=" +
            std::to_string(snapshot.cumulative_filled_quantity) +
            "; snapshotReady=" +
            std::string(snapshot.ready ? "true" : "false") +
            "; snapshotDetail=" + snapshot.detail;
    }
};

}  // namespace astu::execution
