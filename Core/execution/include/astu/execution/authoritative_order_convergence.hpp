#pragma once

#include <cmath>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>

#include "astu/execution/authoritative_order_snapshot.hpp"
#include "astu/execution/execution_journal.hpp"

namespace astu::execution {

inline std::string reconciliation_type_for_state(
    OrderState state) {
    switch (state) {
    case OrderState::Acknowledged: return "ACKNOWLEDGED";
    case OrderState::Working: return "WORKING";
    case OrderState::Partial: return "PARTIAL_FILL";
    case OrderState::Filled: return "FILLED";
    case OrderState::Canceled: return "CANCELED";
    case OrderState::Rejected: return "REJECTED";
    case OrderState::UnknownReconcileRequired:
        return "MARK_UNKNOWN";
    default:
        throw std::invalid_argument(
            "state cannot be applied as authoritative reconciliation");
    }
}

class AuthoritativeOrderConvergence {
public:
    static bool apply_testnet_snapshot(
        const std::shared_ptr<ExecutionJournal>& journal,
        const std::string& order_id,
        const AuthoritativeSimulationOrderSnapshot& snapshot,
        std::int64_t utc_ms) {
        if (!journal || !snapshot.ready ||
            snapshot.simulation_order_id != order_id) {
            return false;
        }
        const auto current = journal->order_state(order_id);
        if (!current.has_value()) {
            throw std::runtime_error(
                "authoritative convergence missing local order state");
        }
        const auto current_filled =
            journal->reconciled_filled_quantity(order_id);

        if (*current == snapshot.state &&
            std::fabs(
                current_filled -
                snapshot.cumulative_filled_quantity) <= 1e-12) {
            return true;
        }

        if (!OrderStateMachine::can_transition(
                *current, snapshot.state)) {
            throw std::runtime_error(
                "authoritative Testnet state cannot converge from " +
                order_state_to_string(*current) + " to " +
                order_state_to_string(snapshot.state));
        }

        journal->append_reconciliation_event(
            "TESTNET-AUTH-" + order_id + "-" +
                std::to_string(utc_ms) + "-" +
                std::to_string(snapshot.generated_unix_ms),
            order_id,
            reconciliation_type_for_state(snapshot.state),
            snapshot.state,
            snapshot.cumulative_filled_quantity,
            utc_ms,
            snapshot.detail,
            false,
            true,
            "BINANCE_USDM_TESTNET");
        return true;
    }
};

}  // namespace astu::execution
