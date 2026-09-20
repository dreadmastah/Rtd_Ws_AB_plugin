#pragma once

#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>

#include "astu/execution/execution_journal.hpp"
#include "astu/execution/order_fsm.hpp"

namespace astu::execution {

enum class SimulationReconciliationType {
    MarkUnknown,
    Acknowledged,
    Working,
    PartialFill,
    Filled,
    Canceled,
    Rejected,
};

inline std::string reconciliation_type_to_string(
    SimulationReconciliationType type) {
    switch (type) {
    case SimulationReconciliationType::MarkUnknown:
        return "MARK_UNKNOWN";
    case SimulationReconciliationType::Acknowledged:
        return "ACKNOWLEDGED";
    case SimulationReconciliationType::Working:
        return "WORKING";
    case SimulationReconciliationType::PartialFill:
        return "PARTIAL_FILL";
    case SimulationReconciliationType::Filled:
        return "FILLED";
    case SimulationReconciliationType::Canceled:
        return "CANCELED";
    case SimulationReconciliationType::Rejected:
        return "REJECTED";
    }
    throw std::invalid_argument("unsupported reconciliation type");
}

inline SimulationReconciliationType reconciliation_type_from_string(
    const std::string& value) {
    if (value == "MARK_UNKNOWN") {
        return SimulationReconciliationType::MarkUnknown;
    }
    if (value == "ACKNOWLEDGED") {
        return SimulationReconciliationType::Acknowledged;
    }
    if (value == "WORKING") {
        return SimulationReconciliationType::Working;
    }
    if (value == "PARTIAL_FILL") {
        return SimulationReconciliationType::PartialFill;
    }
    if (value == "FILLED") {
        return SimulationReconciliationType::Filled;
    }
    if (value == "CANCELED") {
        return SimulationReconciliationType::Canceled;
    }
    if (value == "REJECTED") {
        return SimulationReconciliationType::Rejected;
    }
    throw std::invalid_argument("unknown reconciliation type");
}

inline OrderState reconciliation_target_state(
    SimulationReconciliationType type) {
    switch (type) {
    case SimulationReconciliationType::MarkUnknown:
        return OrderState::UnknownReconcileRequired;
    case SimulationReconciliationType::Acknowledged:
        return OrderState::Acknowledged;
    case SimulationReconciliationType::Working:
        return OrderState::Working;
    case SimulationReconciliationType::PartialFill:
        return OrderState::Partial;
    case SimulationReconciliationType::Filled:
        return OrderState::Filled;
    case SimulationReconciliationType::Canceled:
        return OrderState::Canceled;
    case SimulationReconciliationType::Rejected:
        return OrderState::Rejected;
    }
    throw std::invalid_argument("unsupported reconciliation type");
}

class SimulationReconciliationService {
public:
    explicit SimulationReconciliationService(
        std::shared_ptr<ExecutionJournal> journal)
        : journal_(std::move(journal)) {
        if (!journal_) {
            throw std::invalid_argument(
                "SimulationReconciliationService requires journal");
        }
    }

    OrderState apply(
        const std::string& event_id,
        const std::string& simulation_order_id,
        SimulationReconciliationType type,
        double cumulative_filled_quantity,
        std::int64_t utc_ms,
        std::string detail) {
        const auto target = reconciliation_target_state(type);
        journal_->append_reconciliation_event(
            event_id,
            simulation_order_id,
            reconciliation_type_to_string(type),
            target,
            cumulative_filled_quantity,
            utc_ms,
            std::move(detail));
        return target;
    }

private:
    std::shared_ptr<ExecutionJournal> journal_;
};

}  // namespace astu::execution
