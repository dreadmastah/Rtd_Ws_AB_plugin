#pragma once

#include <cstdint>
#include <functional>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

#include "astu/core/contracts.hpp"
#include "astu/execution/simulation_engine.hpp"
#include "astu/ipc/flat_json.hpp"
#include "astu/ipc/idempotency_cache.hpp"

namespace astu::ipc {

struct SimulationRequest {
    std::uint32_t schema_version{1};
    std::string request_id;
    std::string idempotency_key;
    astu::core::SignalIntent intent;
};

struct SimulationResponse {
    std::uint32_t schema_version{1};
    std::string request_id;
    std::string signal_id;
    astu::core::DecisionCode decision_code{astu::core::DecisionCode::FrameInvalid};
    bool accepted_for_simulation{false};
    bool would_increase_exposure{false};
    double simulated_quantity{0.0};
    bool order_routing_enabled{false};
    std::string reason;
};

inline std::string action_to_string(astu::core::SignalAction action) {
    switch (action) {
    case astu::core::SignalAction::Buy: return "BUY";
    case astu::core::SignalAction::Sell: return "SELL";
    case astu::core::SignalAction::ScaleIn: return "SCALE_IN";
    case astu::core::SignalAction::ScaleOut: return "SCALE_OUT";
    }
    throw std::invalid_argument("unsupported SignalAction");
}

inline astu::core::SignalAction action_from_string(const std::string& value) {
    if (value == "BUY") return astu::core::SignalAction::Buy;
    if (value == "SELL") return astu::core::SignalAction::Sell;
    if (value == "SCALE_IN") return astu::core::SignalAction::ScaleIn;
    if (value == "SCALE_OUT") return astu::core::SignalAction::ScaleOut;
    throw std::invalid_argument("unsupported SignalAction value");
}

inline std::string side_to_string(astu::core::PositionSide side) {
    switch (side) {
    case astu::core::PositionSide::Long: return "LONG";
    case astu::core::PositionSide::Short: return "SHORT";
    }
    throw std::invalid_argument("unsupported PositionSide");
}

inline astu::core::PositionSide side_from_string(const std::string& value) {
    if (value == "LONG") return astu::core::PositionSide::Long;
    if (value == "SHORT") return astu::core::PositionSide::Short;
    throw std::invalid_argument("unsupported PositionSide value");
}

inline std::string decision_to_string(astu::core::DecisionCode code) {
    using astu::core::DecisionCode;
    switch (code) {
    case DecisionCode::SimulatedAccepted: return "SIMULATED_ACCEPTED";
    case DecisionCode::InvalidIntent: return "INVALID_INTENT";
    case DecisionCode::DataNotReady: return "DATA_NOT_READY";
    case DecisionCode::IdentityUnavailable: return "IDENTITY_UNAVAILABLE";
    case DecisionCode::UniverseMismatch: return "UNIVERSE_MISMATCH";
    case DecisionCode::DataGenerationMismatch: return "DATA_GENERATION_MISMATCH";
    case DecisionCode::NotYetValid: return "NOT_YET_VALID";
    case DecisionCode::Expired: return "EXPIRED";
    case DecisionCode::AccountNotReconciled: return "ACCOUNT_NOT_RECONCILED";
    case DecisionCode::RiskBlocked: return "RISK_BLOCKED";
    case DecisionCode::OrderRoutingDisabled: return "ORDER_ROUTING_DISABLED";
    case DecisionCode::DuplicateRequest: return "DUPLICATE_REQUEST";
    case DecisionCode::FrameInvalid: return "FRAME_INVALID";
    }
    return "FRAME_INVALID";
}

inline astu::core::DecisionCode decision_from_string(const std::string& value) {
    using astu::core::DecisionCode;
    if (value == "SIMULATED_ACCEPTED") return DecisionCode::SimulatedAccepted;
    if (value == "INVALID_INTENT") return DecisionCode::InvalidIntent;
    if (value == "DATA_NOT_READY") return DecisionCode::DataNotReady;
    if (value == "IDENTITY_UNAVAILABLE") return DecisionCode::IdentityUnavailable;
    if (value == "UNIVERSE_MISMATCH") return DecisionCode::UniverseMismatch;
    if (value == "DATA_GENERATION_MISMATCH") return DecisionCode::DataGenerationMismatch;
    if (value == "NOT_YET_VALID") return DecisionCode::NotYetValid;
    if (value == "EXPIRED") return DecisionCode::Expired;
    if (value == "ACCOUNT_NOT_RECONCILED") return DecisionCode::AccountNotReconciled;
    if (value == "RISK_BLOCKED") return DecisionCode::RiskBlocked;
    if (value == "ORDER_ROUTING_DISABLED") return DecisionCode::OrderRoutingDisabled;
    if (value == "DUPLICATE_REQUEST") return DecisionCode::DuplicateRequest;
    if (value == "FRAME_INVALID") return DecisionCode::FrameInvalid;
    throw std::invalid_argument("unknown decision code");
}

inline std::string encode_request_json(const SimulationRequest& request) {
    const auto& i = request.intent;
    std::ostringstream out;
    out << std::setprecision(17);
    out
        << "{"
        << "\"schemaVersion\":" << request.schema_version
        << ",\"messageType\":\"ExecutionSimulationRequest.v1\""
        << ",\"requestId\":\"" << json_escape(request.request_id) << "\""
        << ",\"idempotencyKey\":\"" << json_escape(request.idempotency_key) << "\""
        << ",\"signalId\":\"" << json_escape(i.signal_id) << "\""
        << ",\"analysisRunId\":\"" << json_escape(i.analysis_run_id) << "\""
        << ",\"strategyId\":\"" << json_escape(i.strategy_id) << "\""
        << ",\"strategyVersion\":\"" << json_escape(i.strategy_version) << "\""
        << ",\"universeId\":\"" << json_escape(i.universe_id) << "\""
        << ",\"universeVersion\":" << i.universe_version
        << ",\"symbol\":\"" << json_escape(i.symbol) << "\""
        << ",\"action\":\"" << action_to_string(i.action) << "\""
        << ",\"side\":\"" << side_to_string(i.side) << "\""
        << ",\"sourcePeriodicity\":\"" << json_escape(i.source_periodicity) << "\""
        << ",\"sourceBarTime\":" << i.source_bar_time_utc_ms
        << ",\"signalTime\":" << i.signal_time_utc_ms
        << ",\"triggerPrice\":" << i.trigger_price
        << ",\"validFromUtc\":" << i.valid_from_utc_ms
        << ",\"expiresUtc\":" << i.expires_utc_ms
        << ",\"quantityModel\":\"" << json_escape(i.quantity_model) << "\""
        << ",\"priorityScore\":" << i.priority_score
        << ",\"dataGeneration\":" << i.data_generation
        << "}";
    return out.str();
}

inline SimulationRequest decode_request_json(const std::string& json) {
    const auto obj = FlatJsonParser(json).parse();
    if (require_u64(obj, "schemaVersion") != 1 ||
        require_string(obj, "messageType") != "ExecutionSimulationRequest.v1") {
        throw std::invalid_argument("unsupported simulation request schema");
    }

    SimulationRequest request;
    request.schema_version = 1;
    request.request_id = require_string(obj, "requestId");
    request.idempotency_key = require_string(obj, "idempotencyKey");
    auto& i = request.intent;
    i.schema_version = 1;
    i.signal_id = require_string(obj, "signalId");
    i.analysis_run_id = require_string(obj, "analysisRunId");
    i.strategy_id = require_string(obj, "strategyId");
    i.strategy_version = require_string(obj, "strategyVersion");
    i.universe_id = require_string(obj, "universeId");
    i.universe_version = require_u64(obj, "universeVersion");
    i.symbol = require_string(obj, "symbol");
    i.action = action_from_string(require_string(obj, "action"));
    i.side = side_from_string(require_string(obj, "side"));
    i.source_periodicity = require_string(obj, "sourcePeriodicity");
    i.source_bar_time_utc_ms = require_i64(obj, "sourceBarTime");
    i.signal_time_utc_ms = require_i64(obj, "signalTime");
    i.trigger_price = require_double(obj, "triggerPrice");
    i.valid_from_utc_ms = require_i64(obj, "validFromUtc");
    i.expires_utc_ms = require_i64(obj, "expiresUtc");
    i.quantity_model = require_string(obj, "quantityModel");
    i.priority_score = require_double(obj, "priorityScore");
    i.data_generation = require_u64(obj, "dataGeneration");
    return request;
}

inline std::string encode_response_json(const SimulationResponse& response) {
    std::ostringstream out;
    out << std::setprecision(17);
    out
        << "{"
        << "\"schemaVersion\":" << response.schema_version
        << ",\"messageType\":\"ExecutionResult.v1\""
        << ",\"requestId\":\"" << json_escape(response.request_id) << "\""
        << ",\"signalId\":\"" << json_escape(response.signal_id) << "\""
        << ",\"decisionCode\":\"" << decision_to_string(response.decision_code) << "\""
        << ",\"acceptedForSimulation\":" << (response.accepted_for_simulation ? "true" : "false")
        << ",\"wouldIncreaseExposure\":" << (response.would_increase_exposure ? "true" : "false")
        << ",\"simulatedQuantity\":" << response.simulated_quantity
        << ",\"orderRoutingEnabled\":false"
        << ",\"reason\":\"" << json_escape(response.reason) << "\""
        << "}";
    return out.str();
}

inline SimulationResponse decode_response_json(const std::string& json) {
    const auto obj = FlatJsonParser(json).parse();
    if (require_u64(obj, "schemaVersion") != 1 ||
        require_string(obj, "messageType") != "ExecutionResult.v1") {
        throw std::invalid_argument("unsupported execution response schema");
    }
    SimulationResponse response;
    response.request_id = require_string(obj, "requestId");
    response.signal_id = require_string(obj, "signalId");
    response.decision_code = decision_from_string(require_string(obj, "decisionCode"));
    response.accepted_for_simulation = require_bool(obj, "acceptedForSimulation");
    response.would_increase_exposure = require_bool(obj, "wouldIncreaseExposure");
    response.simulated_quantity = require_double(obj, "simulatedQuantity");
    response.order_routing_enabled = require_bool(obj, "orderRoutingEnabled");
    response.reason = require_string(obj, "reason");
    if (response.order_routing_enabled) {
        throw std::invalid_argument("simulation protocol forbids orderRoutingEnabled=true");
    }
    return response;
}

class SimulationDispatcher {
public:
    using DataProvider = std::function<astu::core::DataStatus(const astu::core::SignalIntent&)>;
    using RiskProvider = std::function<astu::core::AccountRiskSnapshot(const astu::core::SignalIntent&)>;

    SimulationDispatcher(
        DataProvider data_provider,
        RiskProvider risk_provider,
        std::size_t idempotency_capacity = 4096)
        : data_provider_(std::move(data_provider)),
          risk_provider_(std::move(risk_provider)),
          idempotency_(idempotency_capacity) {}

    SimulationResponse dispatch(const SimulationRequest& request, std::int64_t now_utc_ms) {
        if (request.request_id.empty() || request.idempotency_key.empty()) {
            return error_response(request, astu::core::DecisionCode::InvalidIntent,
                                  "requestId/idempotencyKey required");
        }
        if (!idempotency_.accept_once(request.idempotency_key)) {
            return error_response(request, astu::core::DecisionCode::DuplicateRequest,
                                  "duplicate idempotency key");
        }

        const auto data = data_provider_(request.intent);
        const auto risk = risk_provider_(request.intent);
        const auto decision = astu::execution::SimulationEngine::run(
            request.intent, data, risk, now_utc_ms);

        SimulationResponse response;
        response.request_id = request.request_id;
        response.signal_id = request.intent.signal_id;
        response.decision_code = decision.code;
        response.accepted_for_simulation = decision.accepted_for_simulation;
        response.would_increase_exposure = decision.would_increase_exposure;
        response.simulated_quantity = decision.simulated_quantity;
        response.order_routing_enabled = false;
        response.reason = decision.reason;
        return response;
    }

    SimulationResponse dispatch_json(const std::string& json, std::int64_t now_utc_ms) {
        try {
            return dispatch(decode_request_json(json), now_utc_ms);
        } catch (const std::exception& exc) {
            SimulationResponse response;
            response.decision_code = astu::core::DecisionCode::FrameInvalid;
            response.reason = std::string("request decode failed: ") + exc.what();
            return response;
        }
    }

private:
    SimulationResponse error_response(
        const SimulationRequest& request,
        astu::core::DecisionCode code,
        std::string reason) const {
        SimulationResponse response;
        response.request_id = request.request_id;
        response.signal_id = request.intent.signal_id;
        response.decision_code = code;
        response.accepted_for_simulation = false;
        response.would_increase_exposure = astu::core::increases_exposure(request.intent.action);
        response.simulated_quantity = 0.0;
        response.order_routing_enabled = false;
        response.reason = std::move(reason);
        return response;
    }

    DataProvider data_provider_;
    RiskProvider risk_provider_;
    IdempotencyCache idempotency_;
};

}  // namespace astu::ipc
