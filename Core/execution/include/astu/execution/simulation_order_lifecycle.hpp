#pragma once

#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>

#include "astu/execution/execution_journal.hpp"
#include "astu/execution/order_fsm.hpp"
#include "astu/ipc/simulation_protocol.hpp"

namespace astu::execution {

class SimulationOrderLifecycle {
public:
    explicit SimulationOrderLifecycle(
        std::shared_ptr<ExecutionJournal> journal)
        : journal_(std::move(journal)) {
        if (!journal_) {
            throw std::invalid_argument("SimulationOrderLifecycle requires journal");
        }
    }

    void observe(
        const astu::ipc::SimulationRequest& request,
        const astu::ipc::SimulationResponse& response,
        std::int64_t utc_ms) {
        using astu::core::DecisionCode;

        if (response.simulation_order_id.empty() ||
            response.decision_code == DecisionCode::DuplicateRequest ||
            response.decision_code == DecisionCode::FrameInvalid) {
            return;
        }

        ensure_state(
            request,
            response.simulation_order_id,
            OrderState::IntentReceived,
            utc_ms,
            "SignalIntent accepted into simulation order lifecycle");
        ensure_state(
            request,
            response.simulation_order_id,
            OrderState::Validating,
            utc_ms,
            "simulation order validation started");

        switch (response.decision_code) {
        case DecisionCode::InvalidIntent:
        case DecisionCode::DataNotReady:
        case DecisionCode::IdentityUnavailable:
        case DecisionCode::UniverseMismatch:
        case DecisionCode::DataGenerationMismatch:
        case DecisionCode::NotYetValid:
        case DecisionCode::Expired:
        case DecisionCode::AccountNotReconciled:
        case DecisionCode::RiskBlocked:
            reject(
                request,
                response.simulation_order_id,
                utc_ms,
                response.reason);
            return;

        case DecisionCode::PositionUnavailable:
        case DecisionCode::PositionConflict:
            ensure_state(
                request,
                response.simulation_order_id,
                OrderState::RiskApproved,
                utc_ms,
                "account risk gate passed before position-state rejection");
            reject(
                request,
                response.simulation_order_id,
                utc_ms,
                response.reason);
            return;

        case DecisionCode::InstrumentUnavailable:
        case DecisionCode::FilterRejected:
        case DecisionCode::SizingRejected:
            ensure_state(
                request,
                response.simulation_order_id,
                OrderState::RiskApproved,
                utc_ms,
                "account risk and position-state gates passed");
            ensure_state(
                request,
                response.simulation_order_id,
                OrderState::Sizing,
                utc_ms,
                "deterministic simulation sizing/filter stage");
            reject(
                request,
                response.simulation_order_id,
                utc_ms,
                response.reason);
            return;

        case DecisionCode::SimulatedAccepted:
        case DecisionCode::OrderRoutingDisabled:
            ensure_state(
                request,
                response.simulation_order_id,
                OrderState::RiskApproved,
                utc_ms,
                "account risk and required position-state gates passed");
            ensure_state(
                request,
                response.simulation_order_id,
                OrderState::Sizing,
                utc_ms,
                "deterministic quantity/filter simulation completed");
            return;

        case DecisionCode::DuplicateRequest:
        case DecisionCode::FrameInvalid:
            return;
        }
    }

private:
    void ensure_state(
        const astu::ipc::SimulationRequest& request,
        const std::string& order_id,
        OrderState target,
        std::int64_t utc_ms,
        const std::string& reason) {
        const auto current = journal_->order_state(order_id);
        if (current.has_value() && *current == target) {
            return;
        }
        if (current.has_value() && is_terminal_order_state(*current)) {
            throw std::runtime_error(
                "cannot advance terminal recovered simulation order");
        }
        journal_->append_order_transition(
            request,
            order_id,
            target,
            utc_ms,
            reason);
    }

    void reject(
        const astu::ipc::SimulationRequest& request,
        const std::string& order_id,
        std::int64_t utc_ms,
        const std::string& reason) {
        ensure_state(
            request,
            order_id,
            OrderState::Rejected,
            utc_ms,
            reason);
    }

    std::shared_ptr<ExecutionJournal> journal_;
};

}  // namespace astu::execution
