#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

#include "astu/core/contracts.hpp"
#include "astu/execution/authoritative_order_snapshot.hpp"
#include "astu/execution/execution_journal.hpp"
#include "astu/execution/order_fsm.hpp"
#include "astu/execution/simulation_order_lifecycle.hpp"
#include "astu/execution/simulation_reconciliation.hpp"
#include "astu/execution/startup_order_reconciler.hpp"
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

astu::ipc::SimulationRequest request(
    const std::string& suffix) {
    astu::ipc::SimulationRequest request;
    request.request_id = "STARTUP-REQ-" + suffix;
    request.idempotency_key = "STARTUP-IDEMP-" + suffix;
    auto& i = request.intent;
    i.signal_id = "STARTUP-SIGNAL-" + suffix;
    i.analysis_run_id = "STARTUP-AA-" + suffix;
    i.strategy_id = "startup-reconcile-test";
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
        << "\"source\":\"STARTUP_TEST_SOURCE\","
        << "\"simulationOrderId\":\"" << order_id << "\","
        << "\"state\":\""
        << astu::execution::order_state_to_string(state) << "\","
        << "\"cumulativeFilledQuantity\":" << cumulative_filled << ","
        << "\"detail\":\"startup reconciliation fixture\""
        << "}";
}

}  // namespace

int main() {
    using astu::execution::FileBackedSimulationOrderSnapshotProvider;
    using astu::execution::OrderState;
    using astu::execution::SimulationReconciliationService;
    using astu::execution::SimulationReconciliationType;
    using astu::execution::StartupOrderReconciler;

    const auto root =
        std::filesystem::temp_directory_path() /
        "astu_startup_order_reconciliation_test";
    std::filesystem::remove_all(root);
    std::filesystem::create_directories(root);

    const auto journal_path = root / "execution_journal.v1.jsonl";
    const auto snapshot_dir = root / "snapshots";
    const auto req = request("1");
    const auto response = accepted(req);
    const auto order_id = response.simulation_order_id;

    {
        auto journal =
            std::make_shared<astu::execution::ExecutionJournal>(
                journal_path,
                100);
        seed_order(journal, req, response);
        REQUIRE(*journal->order_state(order_id) ==
                OrderState::Sizing);

        write_snapshot(
            snapshot_dir,
            order_id,
            OrderState::Sizing,
            0.0,
            now_ms());

        FileBackedSimulationOrderSnapshotProvider provider(
            snapshot_dir,
            5'000);
        const auto report = StartupOrderReconciler::reconcile(
            journal,
            provider,
            static_cast<std::int64_t>(now_ms()));
        REQUIRE(report.tracked_orders == 1);
        REQUIRE(report.matched_orders == 1);
        REQUIRE(report.marked_unknown == 0);
        REQUIRE(report.unresolved_orders == 0);
        REQUIRE(journal->reconciliation_event_count() == 0);
        REQUIRE(*journal->order_state(order_id) ==
                OrderState::Sizing);

        write_snapshot(
            snapshot_dir,
            order_id,
            OrderState::Working,
            0.0,
            now_ms());
        const auto mismatch = StartupOrderReconciler::reconcile(
            journal,
            provider,
            static_cast<std::int64_t>(now_ms() + 1));
        REQUIRE(mismatch.matched_orders == 0);
        REQUIRE(mismatch.marked_unknown == 1);
        REQUIRE(mismatch.unresolved_orders == 1);
        REQUIRE(*journal->order_state(order_id) ==
                OrderState::UnknownReconcileRequired);
        REQUIRE(journal->reconciliation_event_count() == 1);

        const auto still_unknown = StartupOrderReconciler::reconcile(
            journal,
            provider,
            static_cast<std::int64_t>(now_ms() + 2));
        REQUIRE(still_unknown.marked_unknown == 0);
        REQUIRE(still_unknown.unresolved_orders == 1);
        REQUIRE(journal->reconciliation_event_count() == 1);

        SimulationReconciliationService reconciliation(journal);
        REQUIRE(
            reconciliation.apply(
                "STARTUP-EVIDENCE-WORKING",
                order_id,
                SimulationReconciliationType::Working,
                0.0,
                static_cast<std::int64_t>(now_ms() + 3),
                "authoritative simulated working evidence") ==
            OrderState::Working);

        write_snapshot(
            snapshot_dir,
            order_id,
            OrderState::Working,
            0.0,
            now_ms());
        const auto resolved = StartupOrderReconciler::reconcile(
            journal,
            provider,
            static_cast<std::int64_t>(now_ms() + 4));
        REQUIRE(resolved.matched_orders == 1);
        REQUIRE(resolved.unresolved_orders == 0);

        write_snapshot(
            snapshot_dir,
            order_id,
            OrderState::Working,
            0.0,
            now_ms() - 60'000);
        const auto stale = StartupOrderReconciler::reconcile(
            journal,
            provider,
            static_cast<std::int64_t>(now_ms() + 5));
        REQUIRE(stale.marked_unknown == 1);
        REQUIRE(stale.unresolved_orders == 1);
        REQUIRE(*journal->order_state(order_id) ==
                OrderState::UnknownReconcileRequired);
    }

    {
        const auto missing_journal_path =
            root / "missing_journal.v1.jsonl";
        const auto missing_snapshot_dir =
            root / "missing_snapshots";
        const auto missing_req = request("missing");
        const auto missing_response = accepted(missing_req);
        const auto missing_id =
            missing_response.simulation_order_id;

        auto journal =
            std::make_shared<astu::execution::ExecutionJournal>(
                missing_journal_path,
                100);
        seed_order(journal, missing_req, missing_response);
        FileBackedSimulationOrderSnapshotProvider provider(
            missing_snapshot_dir,
            5'000);

        const auto report = StartupOrderReconciler::reconcile(
            journal,
            provider,
            static_cast<std::int64_t>(now_ms()));
        REQUIRE(report.tracked_orders == 1);
        REQUIRE(report.matched_orders == 0);
        REQUIRE(report.marked_unknown == 1);
        REQUIRE(report.unresolved_orders == 1);
        REQUIRE(*journal->order_state(missing_id) ==
                OrderState::UnknownReconcileRequired);
        REQUIRE(journal->reconciliation_event_count() == 1);
    }

    {
        const auto terminal_journal_path =
            root / "terminal_journal.v1.jsonl";
        const auto terminal_snapshot_dir =
            root / "terminal_snapshots";
        const auto terminal_req = request("terminal");
        const auto terminal_response = accepted(terminal_req);
        const auto terminal_id =
            terminal_response.simulation_order_id;

        auto journal =
            std::make_shared<astu::execution::ExecutionJournal>(
                terminal_journal_path,
                100);
        seed_order(journal, terminal_req, terminal_response);
        SimulationReconciliationService reconciliation(journal);
        reconciliation.apply(
            "TERM-UNKNOWN",
            terminal_id,
            SimulationReconciliationType::MarkUnknown,
            0.0,
            3'000,
            "unknown");
        reconciliation.apply(
            "TERM-WORKING",
            terminal_id,
            SimulationReconciliationType::Working,
            0.0,
            3'100,
            "working");
        reconciliation.apply(
            "TERM-FILLED",
            terminal_id,
            SimulationReconciliationType::Filled,
            1.0,
            3'200,
            "filled");
        REQUIRE(*journal->order_state(terminal_id) ==
                OrderState::Filled);

        write_snapshot(
            terminal_snapshot_dir,
            terminal_id,
            OrderState::Canceled,
            1.0,
            now_ms());
        FileBackedSimulationOrderSnapshotProvider provider(
            terminal_snapshot_dir,
            5'000);

        bool terminal_conflict_failed_closed = false;
        try {
            (void)StartupOrderReconciler::reconcile(
                journal,
                provider,
                static_cast<std::int64_t>(now_ms()));
        } catch (const std::runtime_error&) {
            terminal_conflict_failed_closed = true;
        }
        REQUIRE(terminal_conflict_failed_closed);
        REQUIRE(*journal->order_state(terminal_id) ==
                OrderState::Filled);
    }

    std::filesystem::remove_all(root);
    std::cout << "astu_startup_order_reconciliation_tests PASS\n";
    return 0;
}
