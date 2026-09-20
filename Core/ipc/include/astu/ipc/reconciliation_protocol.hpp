#pragma once

#include <cstdint>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

#include "astu/execution/execution_journal.hpp"
#include "astu/execution/simulation_reconciliation.hpp"
#include "astu/ipc/flat_json.hpp"

namespace astu::ipc {

struct SimulationReconciliationRequest {
    std::uint32_t schema_version{1};
    std::string request_id;
    std::string event_id;
    std::string simulation_order_id;
    astu::execution::SimulationReconciliationType reconciliation_type{
        astu::execution::SimulationReconciliationType::MarkUnknown};
    double cumulative_filled_quantity{0.0};
    std::string detail;
};

struct SimulationReconciliationResponse {
    std::uint32_t schema_version{1};
    std::string request_id;
    std::string event_id;
    std::string simulation_order_id;
    bool accepted{false};
    std::string state{"UNKNOWN"};
    double cumulative_filled_quantity{0.0};
    std::uint64_t reconciliation_event_count{0};
    std::uint64_t order_transition_count{0};
    bool exchange_submission_attempted{false};
    std::string reason;
};

inline std::string encode_reconciliation_request_json(
    const SimulationReconciliationRequest& request) {
    std::ostringstream out;
    out
        << "{"
        << "\"schemaVersion\":" << request.schema_version
        << ",\"messageType\":\"SimulationReconciliationRequest.v1\""
        << ",\"requestId\":\"" << json_escape(request.request_id) << "\""
        << ",\"eventId\":\"" << json_escape(request.event_id) << "\""
        << ",\"simulationOrderId\":\""
        << json_escape(request.simulation_order_id) << "\""
        << ",\"reconciliationType\":\""
        << astu::execution::reconciliation_type_to_string(
               request.reconciliation_type)
        << "\""
        << ",\"cumulativeFilledQuantity\":"
        << request.cumulative_filled_quantity
        << ",\"detail\":\"" << json_escape(request.detail) << "\""
        << "}";
    return out.str();
}

inline SimulationReconciliationRequest decode_reconciliation_request_json(
    const std::string& json) {
    const auto obj = FlatJsonParser(json).parse();
    if (require_u64(obj, "schemaVersion") != 1 ||
        require_string(obj, "messageType") !=
            "SimulationReconciliationRequest.v1") {
        throw std::invalid_argument(
            "unsupported reconciliation request schema");
    }

    SimulationReconciliationRequest request;
    request.request_id = require_string(obj, "requestId");
    request.event_id = require_string(obj, "eventId");
    request.simulation_order_id =
        require_string(obj, "simulationOrderId");
    request.reconciliation_type =
        astu::execution::reconciliation_type_from_string(
            require_string(obj, "reconciliationType"));
    request.cumulative_filled_quantity =
        require_double(obj, "cumulativeFilledQuantity");
    request.detail = require_string(obj, "detail");
    if (request.request_id.empty() || request.event_id.empty() ||
        request.simulation_order_id.empty()) {
        throw std::invalid_argument(
            "reconciliation request identity is required");
    }
    return request;
}

inline std::string encode_reconciliation_response_json(
    const SimulationReconciliationResponse& response) {
    std::ostringstream out;
    out
        << "{"
        << "\"schemaVersion\":" << response.schema_version
        << ",\"messageType\":\"SimulationReconciliationResult.v1\""
        << ",\"requestId\":\"" << json_escape(response.request_id) << "\""
        << ",\"eventId\":\"" << json_escape(response.event_id) << "\""
        << ",\"simulationOrderId\":\""
        << json_escape(response.simulation_order_id) << "\""
        << ",\"accepted\":" << (response.accepted ? "true" : "false")
        << ",\"state\":\"" << json_escape(response.state) << "\""
        << ",\"cumulativeFilledQuantity\":"
        << response.cumulative_filled_quantity
        << ",\"reconciliationEventCount\":"
        << response.reconciliation_event_count
        << ",\"orderTransitionCount\":"
        << response.order_transition_count
        << ",\"exchangeSubmissionAttempted\":false"
        << ",\"reason\":\"" << json_escape(response.reason) << "\""
        << "}";
    return out.str();
}

inline SimulationReconciliationResponse decode_reconciliation_response_json(
    const std::string& json) {
    const auto obj = FlatJsonParser(json).parse();
    if (require_u64(obj, "schemaVersion") != 1 ||
        require_string(obj, "messageType") !=
            "SimulationReconciliationResult.v1") {
        throw std::invalid_argument(
            "unsupported reconciliation response schema");
    }

    SimulationReconciliationResponse response;
    response.request_id = require_string(obj, "requestId");
    response.event_id = require_string(obj, "eventId");
    response.simulation_order_id =
        require_string(obj, "simulationOrderId");
    response.accepted = require_bool(obj, "accepted");
    response.state = require_string(obj, "state");
    response.cumulative_filled_quantity =
        require_double(obj, "cumulativeFilledQuantity");
    response.reconciliation_event_count =
        require_u64(obj, "reconciliationEventCount");
    response.order_transition_count =
        require_u64(obj, "orderTransitionCount");
    response.exchange_submission_attempted =
        require_bool(obj, "exchangeSubmissionAttempted");
    response.reason = require_string(obj, "reason");
    if (response.exchange_submission_attempted) {
        throw std::invalid_argument(
            "simulation reconciliation protocol forbids exchange submission");
    }
    return response;
}

class SimulationReconciliationDispatcher {
public:
    explicit SimulationReconciliationDispatcher(
        std::shared_ptr<astu::execution::ExecutionJournal> journal)
        : journal_(std::move(journal)),
          service_(journal_) {
        if (!journal_) {
            throw std::invalid_argument(
                "reconciliation dispatcher requires journal");
        }
    }

    SimulationReconciliationResponse dispatch(
        const SimulationReconciliationRequest& request,
        std::int64_t utc_ms) {
        SimulationReconciliationResponse response;
        response.request_id = request.request_id;
        response.event_id = request.event_id;
        response.simulation_order_id =
            request.simulation_order_id;

        try {
            const auto target = service_.apply(
                request.event_id,
                request.simulation_order_id,
                request.reconciliation_type,
                request.cumulative_filled_quantity,
                utc_ms,
                request.detail);
            response.accepted = true;
            response.state =
                astu::execution::order_state_to_string(target);
            response.reason =
                "simulation reconciliation event applied";
        } catch (const std::exception& exc) {
            response.accepted = false;
            const auto state =
                journal_->order_state(request.simulation_order_id);
            response.state = state.has_value()
                ? astu::execution::order_state_to_string(*state)
                : "UNKNOWN";
            response.reason = exc.what();
        }

        response.cumulative_filled_quantity =
            journal_->reconciled_filled_quantity(
                request.simulation_order_id);
        response.reconciliation_event_count =
            journal_->reconciliation_event_count();
        response.order_transition_count =
            journal_->order_transition_count();
        response.exchange_submission_attempted = false;
        return response;
    }

    SimulationReconciliationResponse dispatch_json(
        const std::string& json,
        std::int64_t utc_ms) {
        try {
            return dispatch(
                decode_reconciliation_request_json(json),
                utc_ms);
        } catch (const std::exception& exc) {
            SimulationReconciliationResponse response;
            response.accepted = false;
            response.reason =
                std::string("reconciliation frame rejected: ") +
                exc.what();
            return response;
        }
    }

private:
    std::shared_ptr<astu::execution::ExecutionJournal> journal_;
    astu::execution::SimulationReconciliationService service_;
};

}  // namespace astu::ipc
