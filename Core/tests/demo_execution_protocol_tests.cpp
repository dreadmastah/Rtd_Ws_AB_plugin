#include <iostream>
#include <stdexcept>
#include <string>

#include "astu/ipc/demo_execution_protocol.hpp"

namespace {

astu::ipc::DemoExecutionRequest good_request(std::uint64_t now) {
    astu::ipc::DemoExecutionRequest request;
    request.request_id = "DEMO-REQ-1";
    request.idempotency_key = "DEMO-IDEM-1";
    request.source_simulation_order_id = "SIM-ORDER-1";
    request.signal_id = "SIGNAL-1";
    request.symbol = "BTCUSDT";
    request.side = "LONG";
    request.quantity = 0.001;
    request.reduce_only = false;
    request.created_unix_ms = now - 100;
    request.expires_unix_ms = now + 2'000;
    request.capability_id = "demo-execution-v1";
    request.capability_token =
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    return request;
}

astu::execution::TestnetConvergenceState good_convergence(
    std::uint64_t now) {
    astu::execution::TestnetConvergenceState state;
    state.ready = true;
    state.stream_alive = true;
    state.ordering_ok = true;
    state.expired = false;
    state.account_converged = true;
    state.positions_converged = true;
    state.orders_converged = true;
    state.rest_fallback_required = false;
    state.generated_unix_ms = now - 100;
    state.last_frame_unix_ms = now - 50;
    state.unresolved_orders = 0;
    state.detail = "fixture ready";
    return state;
}

}  // namespace

int main() {
    using astu::ipc::DemoAdmissionCode;
    using astu::ipc::DemoExecutionAdmissionPolicy;

    constexpr std::uint64_t now = 1'000'000;
    const std::string token =
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    DemoExecutionAdmissionPolicy policy(
        "demo-execution-v1",
        token,
        2'000,
        500,
        1'000);

    auto request = good_request(now);
    auto convergence = good_convergence(now);

    const auto encoded =
        astu::ipc::encode_demo_execution_request_json(request);
    const auto decoded =
        astu::ipc::decode_demo_execution_request_json(encoded);
    if (decoded.request_id != request.request_id ||
        decoded.source_simulation_order_id !=
            request.source_simulation_order_id ||
        decoded.capability_token != request.capability_token ||
        decoded.execution_environment != "BINANCE_USDM_DEMO") {
        return 1;
    }

    auto result = policy.evaluate(decoded, convergence, now);
    if (!result.authorized ||
        result.code != DemoAdmissionCode::Authorized) {
        std::cerr << result.reason << "\n";
        return 2;
    }

    auto bad_capability = request;
    bad_capability.capability_token =
        "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff";
    result = policy.evaluate(bad_capability, convergence, now);
    if (result.authorized ||
        result.code != DemoAdmissionCode::CapabilityRejected) {
        return 3;
    }

    auto stale = request;
    stale.created_unix_ms = now - 3'000;
    stale.expires_unix_ms = now + 1'000;
    result = policy.evaluate(stale, convergence, now);
    if (result.authorized ||
        result.code != DemoAdmissionCode::RequestStale) {
        return 4;
    }

    auto future = request;
    future.created_unix_ms = now + 1'000;
    future.expires_unix_ms = now + 2'000;
    result = policy.evaluate(future, convergence, now);
    if (result.authorized ||
        result.code != DemoAdmissionCode::RequestFromFuture) {
        return 5;
    }

    auto not_ready = convergence;
    not_ready.ready = false;
    result = policy.evaluate(request, not_ready, now);
    if (result.authorized ||
        result.code != DemoAdmissionCode::ConvergenceRejected) {
        return 6;
    }

    auto stale_stream = convergence;
    stale_stream.last_frame_unix_ms = now - 2'000;
    result = policy.evaluate(request, stale_stream, now);
    if (result.authorized ||
        result.code != DemoAdmissionCode::ConvergenceRejected) {
        return 7;
    }

    auto malformed = request;
    malformed.quantity = 0.0;
    result = policy.evaluate(malformed, convergence, now);
    if (result.authorized ||
        result.code != DemoAdmissionCode::InvalidRequest) {
        return 8;
    }

    astu::ipc::DemoExecutionResponse response;
    response.request_id = request.request_id;
    response.source_simulation_order_id =
        request.source_simulation_order_id;
    response.decision_code =
        DemoAdmissionCode::RoutingNotImplemented;
    response.accepted_for_execution = false;
    response.order_submission_attempted = false;
    response.reason =
        "Admission contract is present; Demo router is not wired";

    const auto response_json =
        astu::ipc::encode_demo_execution_response_json(response);
    if (response_json.find("capabilityToken") != std::string::npos ||
        response_json.find(token) != std::string::npos) {
        return 9;
    }
    const auto decoded_response =
        astu::ipc::decode_demo_execution_response_json(response_json);
    if (decoded_response.decision_code !=
            DemoAdmissionCode::RoutingNotImplemented ||
        decoded_response.accepted_for_execution ||
        decoded_response.order_submission_attempted) {
        return 10;
    }

    bool weak_token_rejected = false;
    try {
        DemoExecutionAdmissionPolicy weak(
            "demo-execution-v1",
            "short",
            2'000,
            500,
            1'000);
        (void)weak;
    } catch (const std::invalid_argument&) {
        weak_token_rejected = true;
    }
    if (!weak_token_rejected) {
        return 11;
    }

    std::cout << "DEMO_EXECUTION_PROTOCOL_TESTS=PASS\n";
    return 0;
}
