#include <filesystem>
#include <iostream>
#include <memory>
#include <string>

#include "astu/execution/demo_execution_dispatcher.hpp"
#include "astu/execution/execution_journal.hpp"
#include "astu/execution/order_fsm.hpp"
#include "astu/ipc/demo_execution_protocol.hpp"
#include "astu/ipc/simulation_protocol.hpp"

namespace {

astu::execution::TestnetConvergenceState
ready_convergence(std::uint64_t now) {
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
    return state;
}

astu::ipc::SimulationRequest simulation_request() {
    astu::ipc::SimulationRequest request;
    request.request_id = "SIM-REQ-1";
    request.idempotency_key = "SIM-IDEM-1";
    request.intent.signal_id = "SIGNAL-1";
    request.intent.symbol = "BTCUSDT";
    request.intent.action =
        astu::core::SignalAction::Buy;
    request.intent.side =
        astu::core::PositionSide::Long;
    request.intent.trigger_price = 100.0;
    return request;
}

astu::ipc::DemoExecutionRequest demo_request(
    std::uint64_t now) {
    astu::ipc::DemoExecutionRequest request;
    request.request_id = "DEMO-REQ-1";
    request.idempotency_key = "DEMO-IDEM-1";
    request.source_simulation_order_id =
        "SIM-ORDER-1";
    request.signal_id = "SIGNAL-1";
    request.symbol = "BTCUSDT";
    request.side = "LONG";
    request.quantity = 0.1;
    request.created_unix_ms = now - 100;
    request.expires_unix_ms = now + 2'000;
    request.capability_id = "demo-execution-v1";
    request.capability_token =
        "0123456789abcdef0123456789abcdef"
        "0123456789abcdef0123456789abcdef";
    return request;
}

void seed_sizing_order(
    const std::filesystem::path& path) {
    astu::execution::ExecutionJournal journal(path);
    const auto request = simulation_request();

    astu::ipc::SimulationResponse response;
    response.request_id = request.request_id;
    response.signal_id = request.intent.signal_id;
    response.simulation_order_id = "SIM-ORDER-1";
    response.decision_code =
        astu::core::DecisionCode::OrderRoutingDisabled;
    response.accepted_for_simulation = true;
    response.would_increase_exposure = true;
    response.simulated_quantity = 0.1;
    response.simulated_notional = 10.0;
    response.order_routing_enabled = false;
    response.execution_environment = "SIMULATION_ONLY";

    journal.append_simulation_order_intent(
        request,
        response,
        1);
    journal.append_order_transition(
        request,
        response.simulation_order_id,
        astu::execution::OrderState::IntentReceived,
        2,
        "test");
    journal.append_order_transition(
        request,
        response.simulation_order_id,
        astu::execution::OrderState::Validating,
        3,
        "test");
    journal.append_order_transition(
        request,
        response.simulation_order_id,
        astu::execution::OrderState::RiskApproved,
        4,
        "test");
    journal.append_order_transition(
        request,
        response.simulation_order_id,
        astu::execution::OrderState::Sizing,
        5,
        "test");
}

}  // namespace

int main() {
    using astu::ipc::DemoAdmissionCode;
    constexpr std::uint64_t now = 1'000'000;

    const auto path =
        std::filesystem::temp_directory_path() /
        "astu_demo_execution_dispatch_test.jsonl";
    std::error_code ec;
    std::filesystem::remove(path, ec);
    seed_sizing_order(path);

    const std::string token =
        "0123456789abcdef0123456789abcdef"
        "0123456789abcdef0123456789abcdef";

    auto make_dispatcher = [&]() {
        return astu::execution::DemoExecutionDispatcher(
            astu::ipc::DemoExecutionAdmissionPolicy(
                "demo-execution-v1",
                token,
                2'000,
                500,
                1'000),
            [now]() {
                return ready_convergence(now);
            },
            astu::execution::DemoSourceJournalVerifier(
                path));
    };

    auto request = demo_request(now);
    auto response =
        make_dispatcher().dispatch(request, now);
    if (response.decision_code !=
            DemoAdmissionCode::RoutingNotImplemented ||
        response.accepted_for_execution ||
        response.order_submission_attempted) {
        std::cerr << response.reason << "\n";
        return 1;
    }

    auto missing = request;
    missing.source_simulation_order_id =
        "SIM-ORDER-MISSING";
    response = make_dispatcher().dispatch(missing, now);
    if (response.decision_code !=
        DemoAdmissionCode::SourceRejected) {
        return 2;
    }

    auto bad_signal = request;
    bad_signal.signal_id = "SIGNAL-OTHER";
    response =
        make_dispatcher().dispatch(bad_signal, now);
    if (response.decision_code !=
        DemoAdmissionCode::SourceRejected) {
        return 3;
    }

    auto bad_quantity = request;
    bad_quantity.quantity = 0.09;
    response =
        make_dispatcher().dispatch(
            bad_quantity,
            now);
    if (response.decision_code !=
        DemoAdmissionCode::SourceRejected) {
        return 4;
    }

    {
        astu::execution::ExecutionJournal journal(path);
        const auto source = simulation_request();
        journal.append_order_transition(
            source,
            request.source_simulation_order_id,
            astu::execution::OrderState::Rejected,
            6,
            "terminal test");
    }
    response =
        make_dispatcher().dispatch(request, now);
    if (response.decision_code !=
        DemoAdmissionCode::SourceRejected) {
        return 5;
    }

    auto bad_capability = request;
    bad_capability.capability_token =
        "ffffffffffffffffffffffffffffffff"
        "ffffffffffffffffffffffffffffffff";
    response =
        make_dispatcher().dispatch(
            bad_capability,
            now);
    if (response.decision_code !=
        DemoAdmissionCode::CapabilityRejected) {
        return 6;
    }

    std::filesystem::remove(path, ec);
    std::cout
        << "DEMO_EXECUTION_DISPATCH_TESTS=PASS\n";
    return 0;
}
