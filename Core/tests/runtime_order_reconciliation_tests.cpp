#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <string>

#include "astu/core/contracts.hpp"
#include "astu/execution/authoritative_order_snapshot.hpp"
#include "astu/execution/execution_journal.hpp"
#include "astu/execution/order_fsm.hpp"
#include "astu/execution/runtime_order_reconciler.hpp"
#include "astu/execution/simulation_order_lifecycle.hpp"
#include "astu/execution/simulation_reconciliation.hpp"
#include "astu/ipc/simulation_protocol.hpp"

#define REQUIRE(...) do { \
    if (!(__VA_ARGS__)) { \
        std::cerr << "REQUIRE_FAILED line=" << __LINE__ \
                  << " expr=" << #__VA_ARGS__ << "\n"; \
        return 99; \
    } \
} while (0)

namespace {

std::uint64_t now_ms() {
    const auto now =
        std::chrono::system_clock::now().time_since_epoch();
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::milliseconds>(
            now).count());
}

astu::ipc::SimulationRequest request() {
    astu::ipc::SimulationRequest request;
    request.request_id = "RUNTIME-REQ-1";
    request.idempotency_key = "RUNTIME-IDEMP-1";
    auto& i = request.intent;
    i.signal_id = "RUNTIME-SIGNAL-1";
    i.analysis_run_id = "RUNTIME-AA-1";
    i.strategy_id = "runtime-reconcile-test";
    i.strategy_version = "1";
    i.universe_id = "U";
    i.universe_version = 1;
    i.symbol = "BTCUSDT";
    i.action = astu::core::SignalAction::Buy;
    i.side = astu::core::PositionSide::Long;
    i.source_periodicity = "M1";
    i.source_bar_time_utc_ms = 1'000;
    i.signal_time_utc_ms = 1'100;
    i.trigger_price = 100.0;
    i.valid_from_utc_ms = 1'000;
    i.expires_utc_ms = 5'000;
    i.quantity_model = "DETERMINISTIC_SIM_V1";
    i.data_generation = 1;
    return request;
}

astu::ipc::SimulationResponse accepted(
    const astu::ipc::SimulationRequest& request) {
    astu::ipc::SimulationResponse response;
    response.request_id = request.request_id;
    response.signal_id = request.intent.signal_id;
    response.simulation_order_id =
        astu::execution::deterministic_simulation_order_id(
            request.request_id,
            request.idempotency_key,
            request.intent);
    response.decision_code =
        astu::core::DecisionCode::OrderRoutingDisabled;
    response.accepted_for_simulation = true;
    response.would_increase_exposure = true;
    response.simulated_quantity = 1.0;
    response.simulated_notional = 100.0;
    response.order_routing_enabled = false;
    response.reason = "simulation accepted";
    return response;
}

void seed_order(
    const std::shared_ptr<astu::execution::ExecutionJournal>& journal,
    const astu::ipc::SimulationRequest& request,
    const astu::ipc::SimulationResponse& response) {
    astu::execution::SimulationOrderLifecycle lifecycle(journal);
    lifecycle.observe(request, response, 2'000);
    journal->append_simulation_order_intent(
        request,
        response,
        2'000);
    journal->append(request, response, 2'000);
}

void write_snapshot(
    const std::filesystem::path& dir,
    const std::string& order_id,
    astu::execution::OrderState state,
    double cumulative_filled,
    std::uint64_t generated_ms,
    bool ready = true) {
    std::filesystem::create_directories(dir);
    std::ofstream out(
        dir / (order_id + ".json"),
        std::ios::binary | std::ios::trunc);
    out
        << "{"
        << "\"schemaVersion\":1,"
        << "\"messageType\":\"AuthoritativeSimulationOrderSnapshot.v1\","
        << "\"generatedUnixMs\":" << generated_ms << ","
        << "\"ready\":" << (ready ? "true" : "false") << ","
        << "\"source\":\"RUNTIME_TEST_SOURCE\","
        << "\"simulationOrderId\":\"" << order_id << "\","
        << "\"state\":\""
        << astu::execution::order_state_to_string(state) << "\","
        << "\"cumulativeFilledQuantity\":" << cumulative_filled << ","
        << "\"detail\":\"runtime reconciliation fixture\""
        << "}";
}

}  // namespace

int main() {
    using astu::execution::FileBackedSimulationOrderSnapshotProvider;
    using astu::execution::OrderState;
    using astu::execution::RuntimeOrderReconciler;
    using astu::execution::SimulationReconciliationService;
    using astu::execution::SimulationReconciliationType;

    const auto root =
        std::filesystem::temp_directory_path() /
        "astu_runtime_order_reconciliation_test";
    std::filesystem::remove_all(root);
    std::filesystem::create_directories(root);

    const auto journal_path =
        root / "execution_journal.v1.jsonl";
    const auto snapshot_dir = root / "snapshots";
    const auto req = request();
    const auto response = accepted(req);
    const auto order_id = response.simulation_order_id;

    auto journal =
        std::make_shared<astu::execution::ExecutionJournal>(
            journal_path,
            100);
    seed_order(journal, req, response);
    REQUIRE(*journal->order_state(order_id) ==
            OrderState::Sizing);

    FileBackedSimulationOrderSnapshotProvider provider(
        snapshot_dir,
        5'000);

    write_snapshot(
        snapshot_dir,
        order_id,
        OrderState::Sizing,
        0.0,
        now_ms());
    auto report = RuntimeOrderReconciler::sweep(
        journal,
        provider,
        static_cast<std::int64_t>(now_ms()));
    REQUIRE(report.tracked_nonterminal_orders == 1);
    REQUIRE(report.matched_orders == 1);
    REQUIRE(report.marked_unknown == 0);
    REQUIRE(report.unresolved_orders == 0);
    REQUIRE(report.source_unavailable_orders == 0);
    REQUIRE(journal->reconciliation_event_count() == 0);

    write_snapshot(
        snapshot_dir,
        order_id,
        OrderState::Working,
        0.0,
        now_ms());
    report = RuntimeOrderReconciler::sweep(
        journal,
        provider,
        static_cast<std::int64_t>(now_ms() + 1));
    REQUIRE(report.matched_orders == 0);
    REQUIRE(report.marked_unknown == 1);
    REQUIRE(report.unresolved_orders == 1);
    REQUIRE(*journal->order_state(order_id) ==
            OrderState::UnknownReconcileRequired);
    REQUIRE(journal->reconciliation_event_count() == 1);

    report = RuntimeOrderReconciler::sweep(
        journal,
        provider,
        static_cast<std::int64_t>(now_ms() + 2));
    REQUIRE(report.marked_unknown == 0);
    REQUIRE(report.unresolved_orders == 1);
    REQUIRE(journal->reconciliation_event_count() == 1);

    SimulationReconciliationService reconciliation(journal);
    REQUIRE(
        reconciliation.apply(
            "RUNTIME-WORKING-EVIDENCE",
            order_id,
            SimulationReconciliationType::Working,
            0.0,
            static_cast<std::int64_t>(now_ms() + 3),
            "runtime authoritative working evidence") ==
        OrderState::Working);

    report = RuntimeOrderReconciler::sweep(
        journal,
        provider,
        static_cast<std::int64_t>(now_ms() + 4));
    REQUIRE(report.matched_orders == 1);
    REQUIRE(report.unresolved_orders == 0);

    std::filesystem::remove(
        snapshot_dir / (order_id + ".json"));
    report = RuntimeOrderReconciler::sweep(
        journal,
        provider,
        static_cast<std::int64_t>(now_ms() + 5));
    REQUIRE(report.source_unavailable_orders == 1);
    REQUIRE(report.marked_unknown == 1);
    REQUIRE(report.unresolved_orders == 1);
    REQUIRE(*journal->order_state(order_id) ==
            OrderState::UnknownReconcileRequired);

    write_snapshot(
        snapshot_dir,
        order_id,
        OrderState::Working,
        0.0,
        now_ms());
    report = RuntimeOrderReconciler::sweep(
        journal,
        provider,
        static_cast<std::int64_t>(now_ms() + 6));
    REQUIRE(report.matched_orders == 0);
    REQUIRE(report.marked_unknown == 0);
    REQUIRE(report.unresolved_orders == 1);

    REQUIRE(
        reconciliation.apply(
            "RUNTIME-RECOVERY-WORKING",
            order_id,
            SimulationReconciliationType::Working,
            0.0,
            static_cast<std::int64_t>(now_ms() + 7),
            "explicit evidence required after source recovery") ==
        OrderState::Working);
    report = RuntimeOrderReconciler::sweep(
        journal,
        provider,
        static_cast<std::int64_t>(now_ms() + 8));
    REQUIRE(report.matched_orders == 1);
    REQUIRE(report.unresolved_orders == 0);

    REQUIRE(
        reconciliation.apply(
            "RUNTIME-FILLED",
            order_id,
            SimulationReconciliationType::Filled,
            1.0,
            static_cast<std::int64_t>(now_ms() + 9),
            "simulation full fill") ==
        OrderState::Filled);

    write_snapshot(
        snapshot_dir,
        order_id,
        OrderState::Canceled,
        1.0,
        now_ms());
    report = RuntimeOrderReconciler::sweep(
        journal,
        provider,
        static_cast<std::int64_t>(now_ms() + 10));
    REQUIRE(report.tracked_nonterminal_orders == 0);
    REQUIRE(report.terminal_orders_skipped == 1);
    REQUIRE(report.marked_unknown == 0);
    REQUIRE(*journal->order_state(order_id) ==
            OrderState::Filled);

    std::filesystem::remove_all(root);
    std::cout << "astu_runtime_order_reconciliation_tests PASS\n";
    return 0;
}
