#pragma once

#include <cmath>
#include <cstdint>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

#include "astu/execution/testnet_convergence.hpp"
#include "astu/ipc/flat_json.hpp"

namespace astu::ipc {

enum class DemoAdmissionCode {
    Authorized,
    InvalidRequest,
    CapabilityRejected,
    RequestStale,
    RequestFromFuture,
    ConvergenceRejected,
    RoutingNotImplemented,
};

inline std::string demo_admission_code_to_string(DemoAdmissionCode code) {
    switch (code) {
    case DemoAdmissionCode::Authorized: return "AUTHORIZED";
    case DemoAdmissionCode::InvalidRequest: return "INVALID_REQUEST";
    case DemoAdmissionCode::CapabilityRejected: return "CAPABILITY_REJECTED";
    case DemoAdmissionCode::RequestStale: return "REQUEST_STALE";
    case DemoAdmissionCode::RequestFromFuture: return "REQUEST_FROM_FUTURE";
    case DemoAdmissionCode::ConvergenceRejected: return "CONVERGENCE_REJECTED";
    case DemoAdmissionCode::RoutingNotImplemented: return "ROUTING_NOT_IMPLEMENTED";
    }
    return "INVALID_REQUEST";
}

inline DemoAdmissionCode demo_admission_code_from_string(
    const std::string& value) {
    if (value == "AUTHORIZED") return DemoAdmissionCode::Authorized;
    if (value == "INVALID_REQUEST") return DemoAdmissionCode::InvalidRequest;
    if (value == "CAPABILITY_REJECTED") return DemoAdmissionCode::CapabilityRejected;
    if (value == "REQUEST_STALE") return DemoAdmissionCode::RequestStale;
    if (value == "REQUEST_FROM_FUTURE") return DemoAdmissionCode::RequestFromFuture;
    if (value == "CONVERGENCE_REJECTED") return DemoAdmissionCode::ConvergenceRejected;
    if (value == "ROUTING_NOT_IMPLEMENTED") return DemoAdmissionCode::RoutingNotImplemented;
    throw std::invalid_argument("unknown Demo admission code");
}

struct DemoExecutionRequest {
    std::uint32_t schema_version{1};
    std::string request_id;
    std::string idempotency_key;
    std::string source_simulation_order_id;
    std::string signal_id;
    std::string symbol;
    std::string side;
    double quantity{0.0};
    bool reduce_only{false};
    std::uint64_t created_unix_ms{0};
    std::uint64_t expires_unix_ms{0};
    std::string capability_id;
    std::string capability_token;
    std::string execution_environment{"BINANCE_USDM_DEMO"};
};

struct DemoExecutionResponse {
    std::uint32_t schema_version{1};
    std::string request_id;
    std::string source_simulation_order_id;
    DemoAdmissionCode decision_code{DemoAdmissionCode::RoutingNotImplemented};
    bool accepted_for_execution{false};
    bool order_submission_attempted{false};
    std::string execution_environment{"BINANCE_USDM_DEMO"};
    std::string exchange_client_order_id;
    std::string exchange_order_id;
    std::string exchange_order_status;
    std::string reason;
};

inline bool constant_time_equal(
    const std::string& left,
    const std::string& right) noexcept {
    if (left.size() != right.size()) {
        return false;
    }
    unsigned char diff = 0;
    for (std::size_t i = 0; i < left.size(); ++i) {
        diff |= static_cast<unsigned char>(
            static_cast<unsigned char>(left[i]) ^
            static_cast<unsigned char>(right[i]));
    }
    return diff == 0;
}

inline std::string encode_demo_execution_request_json(
    const DemoExecutionRequest& request) {
    std::ostringstream out;
    out << std::setprecision(17);
    out
        << "{"
        << "\"schemaVersion\":" << request.schema_version
        << ",\"messageType\":\"DemoExecutionRequest.v1\""
        << ",\"requestId\":\"" << json_escape(request.request_id) << "\""
        << ",\"idempotencyKey\":\"" << json_escape(request.idempotency_key) << "\""
        << ",\"sourceSimulationOrderId\":\""
        << json_escape(request.source_simulation_order_id) << "\""
        << ",\"signalId\":\"" << json_escape(request.signal_id) << "\""
        << ",\"symbol\":\"" << json_escape(request.symbol) << "\""
        << ",\"side\":\"" << json_escape(request.side) << "\""
        << ",\"quantity\":" << request.quantity
        << ",\"reduceOnly\":" << (request.reduce_only ? "true" : "false")
        << ",\"createdUnixMs\":" << request.created_unix_ms
        << ",\"expiresUnixMs\":" << request.expires_unix_ms
        << ",\"capabilityId\":\"" << json_escape(request.capability_id) << "\""
        << ",\"capabilityToken\":\"" << json_escape(request.capability_token) << "\""
        << ",\"executionEnvironment\":\""
        << json_escape(request.execution_environment) << "\""
        << "}";
    return out.str();
}

inline DemoExecutionRequest decode_demo_execution_request_json(
    const std::string& json) {
    const auto obj = FlatJsonParser(json).parse();
    if (require_u64(obj, "schemaVersion") != 1 ||
        require_string(obj, "messageType") != "DemoExecutionRequest.v1") {
        throw std::invalid_argument("unsupported Demo execution request schema");
    }

    DemoExecutionRequest request;
    request.request_id = require_string(obj, "requestId");
    request.idempotency_key = require_string(obj, "idempotencyKey");
    request.source_simulation_order_id =
        require_string(obj, "sourceSimulationOrderId");
    request.signal_id = require_string(obj, "signalId");
    request.symbol = require_string(obj, "symbol");
    request.side = require_string(obj, "side");
    request.quantity = require_double(obj, "quantity");
    request.reduce_only = require_bool(obj, "reduceOnly");
    request.created_unix_ms = require_u64(obj, "createdUnixMs");
    request.expires_unix_ms = require_u64(obj, "expiresUnixMs");
    request.capability_id = require_string(obj, "capabilityId");
    request.capability_token = require_string(obj, "capabilityToken");
    request.execution_environment =
        require_string(obj, "executionEnvironment");
    return request;
}

inline std::string encode_demo_execution_response_json(
    const DemoExecutionResponse& response) {
    std::ostringstream out;
    out
        << "{"
        << "\"schemaVersion\":" << response.schema_version
        << ",\"messageType\":\"DemoExecutionResult.v1\""
        << ",\"requestId\":\"" << json_escape(response.request_id) << "\""
        << ",\"sourceSimulationOrderId\":\""
        << json_escape(response.source_simulation_order_id) << "\""
        << ",\"decisionCode\":\""
        << demo_admission_code_to_string(response.decision_code) << "\""
        << ",\"acceptedForExecution\":"
        << (response.accepted_for_execution ? "true" : "false")
        << ",\"orderSubmissionAttempted\":"
        << (response.order_submission_attempted ? "true" : "false")
        << ",\"executionEnvironment\":\""
        << json_escape(response.execution_environment) << "\""
        << ",\"exchangeClientOrderId\":\""
        << json_escape(response.exchange_client_order_id) << "\""
        << ",\"exchangeOrderId\":\""
        << json_escape(response.exchange_order_id) << "\""
        << ",\"exchangeOrderStatus\":\""
        << json_escape(response.exchange_order_status) << "\""
        << ",\"reason\":\"" << json_escape(response.reason) << "\""
        << "}";
    return out.str();
}

inline DemoExecutionResponse decode_demo_execution_response_json(
    const std::string& json) {
    const auto obj = FlatJsonParser(json).parse();
    if (require_u64(obj, "schemaVersion") != 1 ||
        require_string(obj, "messageType") != "DemoExecutionResult.v1") {
        throw std::invalid_argument("unsupported Demo execution response schema");
    }

    DemoExecutionResponse response;
    response.request_id = require_string(obj, "requestId");
    response.source_simulation_order_id =
        require_string(obj, "sourceSimulationOrderId");
    response.decision_code = demo_admission_code_from_string(
        require_string(obj, "decisionCode"));
    response.accepted_for_execution =
        require_bool(obj, "acceptedForExecution");
    response.order_submission_attempted =
        require_bool(obj, "orderSubmissionAttempted");
    response.execution_environment =
        require_string(obj, "executionEnvironment");
    response.exchange_client_order_id =
        require_string(obj, "exchangeClientOrderId");
    response.exchange_order_id = require_string(obj, "exchangeOrderId");
    response.exchange_order_status =
        require_string(obj, "exchangeOrderStatus");
    response.reason = require_string(obj, "reason");
    return response;
}

struct DemoAdmissionResult {
    DemoAdmissionCode code{DemoAdmissionCode::InvalidRequest};
    bool authorized{false};
    std::string reason;
};

class DemoExecutionAdmissionPolicy {
public:
    DemoExecutionAdmissionPolicy(
        std::string capability_id,
        std::string capability_token,
        std::uint64_t max_request_age_ms = 5'000,
        std::uint64_t max_future_skew_ms = 1'000,
        std::uint64_t max_convergence_age_ms = 5'000)
        : capability_id_(std::move(capability_id)),
          capability_token_(std::move(capability_token)),
          max_request_age_ms_(max_request_age_ms),
          max_future_skew_ms_(max_future_skew_ms),
          max_convergence_age_ms_(max_convergence_age_ms) {
        if (capability_id_.empty() || capability_id_.size() > 128) {
            throw std::invalid_argument("Demo capability id is invalid");
        }
        if (capability_token_.size() < 32 || capability_token_.size() > 256) {
            throw std::invalid_argument(
                "Demo capability token must contain 32..256 bytes");
        }
        if (max_request_age_ms_ == 0 || max_convergence_age_ms_ == 0) {
            throw std::invalid_argument(
                "Demo admission freshness windows must be positive");
        }
    }

    DemoAdmissionResult evaluate(
        const DemoExecutionRequest& request,
        const astu::execution::TestnetConvergenceState& convergence,
        std::uint64_t now_unix_ms) const {
        if (!valid_request_shape(request)) {
            return {
                DemoAdmissionCode::InvalidRequest,
                false,
                "Demo execution request shape invalid",
            };
        }

        if (!constant_time_equal(request.capability_id, capability_id_) ||
            !constant_time_equal(
                request.capability_token,
                capability_token_)) {
            return {
                DemoAdmissionCode::CapabilityRejected,
                false,
                "Demo execution capability rejected",
            };
        }

        if (request.created_unix_ms >
            now_unix_ms + max_future_skew_ms_) {
            return {
                DemoAdmissionCode::RequestFromFuture,
                false,
                "Demo execution request timestamp is in the future",
            };
        }

        if (now_unix_ms > request.expires_unix_ms ||
            (request.created_unix_ms <= now_unix_ms &&
             now_unix_ms - request.created_unix_ms >
                 max_request_age_ms_)) {
            return {
                DemoAdmissionCode::RequestStale,
                false,
                "Demo execution request is stale or expired",
            };
        }

        if (!convergence_ready(convergence, now_unix_ms)) {
            return {
                DemoAdmissionCode::ConvergenceRejected,
                false,
                "Demo account/position/order convergence is not fresh and ready",
            };
        }

        return {
            DemoAdmissionCode::Authorized,
            true,
            "Demo execution admission authorized",
        };
    }

private:
    bool valid_request_shape(
        const DemoExecutionRequest& request) const noexcept {
        return
            request.schema_version == 1 &&
            !request.request_id.empty() &&
            request.request_id.size() <= 128 &&
            !request.idempotency_key.empty() &&
            request.idempotency_key.size() <= 128 &&
            !request.source_simulation_order_id.empty() &&
            request.source_simulation_order_id.size() <= 64 &&
            !request.signal_id.empty() &&
            request.signal_id.size() <= 128 &&
            !request.symbol.empty() &&
            request.symbol.size() <= 32 &&
            (request.side == "LONG" || request.side == "SHORT") &&
            std::isfinite(request.quantity) &&
            request.quantity > 0.0 &&
            request.created_unix_ms > 0 &&
            request.expires_unix_ms > request.created_unix_ms &&
            !request.capability_id.empty() &&
            request.capability_id.size() <= 128 &&
            request.capability_token.size() >= 32 &&
            request.capability_token.size() <= 256 &&
            request.execution_environment == "BINANCE_USDM_DEMO";
    }

    bool convergence_ready(
        const astu::execution::TestnetConvergenceState& state,
        std::uint64_t now_unix_ms) const noexcept {
        if (!state.ready ||
            !state.stream_alive ||
            !state.ordering_ok ||
            state.expired ||
            !state.account_converged ||
            !state.positions_converged ||
            !state.orders_converged ||
            state.rest_fallback_required ||
            state.unresolved_orders != 0 ||
            state.generated_unix_ms == 0 ||
            state.last_frame_unix_ms == 0) {
            return false;
        }

        if (state.generated_unix_ms >
                now_unix_ms + max_future_skew_ms_ ||
            state.last_frame_unix_ms >
                now_unix_ms + max_future_skew_ms_) {
            return false;
        }

        const auto generated_age =
            now_unix_ms >= state.generated_unix_ms
                ? now_unix_ms - state.generated_unix_ms
                : 0;
        const auto frame_age =
            now_unix_ms >= state.last_frame_unix_ms
                ? now_unix_ms - state.last_frame_unix_ms
                : 0;
        return generated_age <= max_convergence_age_ms_ &&
               frame_age <= max_convergence_age_ms_;
    }

    std::string capability_id_;
    std::string capability_token_;
    std::uint64_t max_request_age_ms_{5'000};
    std::uint64_t max_future_skew_ms_{1'000};
    std::uint64_t max_convergence_age_ms_{5'000};
};

}  // namespace astu::ipc
