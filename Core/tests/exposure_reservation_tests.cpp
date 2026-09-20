#include <cmath>
#include <filesystem>
#include <iostream>
#include <memory>
#include <string>

#include "astu/core/contracts.hpp"
#include "astu/execution/execution_journal.hpp"
#include "astu/execution/exposure_reservation.hpp"
#include "astu/execution/order_fsm.hpp"
#include "astu/execution/simulation_engine.hpp"
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

astu::ipc::SimulationRequest request(
    std::string suffix,
    astu::core::SignalAction action = astu::core::SignalAction::Buy) {
    astu::ipc::SimulationRequest request;
    request.request_id = "RES-REQ-" + suffix;
    request.idempotency_key = "RES-IDEMP-" + suffix;
    auto& i = request.intent;
    i.signal_id = "RES-SIGNAL-" + suffix;
    i.analysis_run_id = "RES-AA-" + suffix;
    i.strategy_id = "reservation-test";
    i.strategy_version = "1";
    i.universe_id = "U";
    i.universe_version = 1;
    i.symbol = "BTCUSDT";
    i.action = action;
    i.side = astu::core::PositionSide::Long;
    i.source_periodicity = "M1";
    i.source_bar_time_utc_ms = 1'000;
    i.signal_time_utc_ms = 1'100;
    i.trigger_price = 100.0;
    i.valid_from_utc_ms = 1'000;
    i.expires_utc_ms = 10'000;
    i.quantity_model = "DETERMINISTIC_SIM_V1";
    i.data_generation = 1;
    return request;
}

astu::core::DataStatus ready_data(
    const astu::core::SignalIntent& intent) {
    astu::core::DataStatus data;
    data.source = "RESERVATION_TEST";
    data.symbol = intent.symbol;
    data.live = true;
    data.fresh = true;
    data.cache_ready = true;
    data.identity_ready = true;
    data.universe_id = intent.universe_id;
    data.universe_version = intent.universe_version;
    data.data_generation = intent.data_generation;
    data.detail = "ready";
    return data;
}

astu::core::AccountRiskSnapshot base_risk(
    double gross_notional,
    double max_gross_notional,
    std::uint32_t open_positions,
    std::uint32_t max_open_positions) {
    astu::core::AccountRiskSnapshot risk;
    risk.reconciled = true;
    risk.risk_state = astu::core::RiskState::Normal;
    risk.risk_capital = 10'000.0;
    risk.available_balance = 10'000.0;
    risk.gross_notional = gross_notional;
    risk.max_gross_notional = max_gross_notional;
    risk.open_positions = open_positions;
    risk.max_open_positions = max_open_positions;
    return risk;
}

astu::ipc::SimulationResponse accepted_response(
    const astu::ipc::SimulationRequest& request,
    double quantity = 0.1,
    double notional = 10.0) {
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
    response.would_increase_exposure =
        astu::core::increases_exposure(request.intent.action);
    response.simulated_quantity = quantity;
    response.simulated_notional = notional;
    response.order_routing_enabled = false;
    response.reason = "simulation accepted";
    return response;
}

void persist_accepted(
    const std::shared_ptr<astu::execution::ExecutionJournal>& journal,
    const astu::ipc::SimulationRequest& request,
    const astu::ipc::SimulationResponse& response,
    std::int64_t utc_ms) {
    astu::execution::SimulationOrderLifecycle lifecycle(journal);
    lifecycle.observe(request, response, utc_ms);
    journal->append_simulation_order_intent(
        request,
        response,
        utc_ms);
    journal->append_exposure_reservation(
        request,
        response,
        utc_ms);
    journal->append(request, response, utc_ms);
}

astu::ipc::SimulationDispatcher reservation_dispatcher(
    const std::shared_ptr<astu::execution::ExecutionJournal>& journal,
    astu::core::AccountRiskSnapshot base) {
    auto lifecycle =
        std::make_shared<astu::execution::SimulationOrderLifecycle>(
            journal);

    return astu::ipc::SimulationDispatcher(
        [](const astu::core::SignalIntent& intent) {
            return ready_data(intent);
        },
        [journal, base](const astu::core::SignalIntent&) {
            return astu::execution::ExposureReservationRiskOverlay::apply(
                base,
                journal->exposure_reservation_summary());
        },
        4096,
        [journal](const std::string& key) {
            return journal->accept_idempotency_key(key);
        },
        [journal, lifecycle](
            const astu::ipc::SimulationRequest& request,
            const astu::ipc::SimulationResponse& response,
            std::int64_t utc_ms) {
            lifecycle->observe(request, response, utc_ms);
            if (response.decision_code ==
                    astu::core::DecisionCode::OrderRoutingDisabled &&
                response.accepted_for_simulation) {
                journal->append_simulation_order_intent(
                    request,
                    response,
                    utc_ms);
                journal->append_exposure_reservation(
                    request,
                    response,
                    utc_ms);
            }
            journal->append(request, response, utc_ms);
        });
}

}  // namespace

int main() {
    using astu::core::DecisionCode;
    using astu::core::SignalAction;
    using astu::execution::OrderState;
    using astu::execution::SimulationReconciliationService;
    using astu::execution::SimulationReconciliationType;

    const auto root =
        std::filesystem::temp_directory_path() /
        "astu_exposure_reservation_test";
    std::filesystem::remove_all(root);
    std::filesystem::create_directories(root);

    {
        const auto journal_path = root / "gross.jsonl";
        auto journal =
            std::make_shared<astu::execution::ExecutionJournal>(
                journal_path,
                100);

        auto dispatcher = reservation_dispatcher(
            journal,
            base_risk(90.0, 100.0, 0, 10));

        const auto first = request("GROSS-1");
        const auto first_response =
            dispatcher.dispatch(first, 2'000);
        REQUIRE(first_response.decision_code ==
                DecisionCode::OrderRoutingDisabled);
        REQUIRE(first_response.accepted_for_simulation);
        REQUIRE(std::fabs(first_response.simulated_notional - 10.0) <
                1e-12);

        auto summary = journal->exposure_reservation_summary();
        REQUIRE(summary.active_reservations == 1);
        REQUIRE(std::fabs(summary.reserved_gross_notional - 10.0) <
                1e-12);
        REQUIRE(summary.reserved_position_slots == 1);

        const auto projected =
            astu::execution::ExposureReservationRiskOverlay::apply(
                base_risk(90.0, 100.0, 0, 10),
                summary);
        REQUIRE(std::fabs(projected.gross_notional - 100.0) <
                1e-12);
        REQUIRE(projected.open_positions == 1);

        const auto second = request("GROSS-2");
        const auto second_response =
            dispatcher.dispatch(second, 2'001);
        REQUIRE(second_response.decision_code ==
                DecisionCode::RiskBlocked);
        REQUIRE(!second_response.accepted_for_simulation);
        REQUIRE(journal->exposure_reservation_summary()
                    .active_reservations == 1);

        const auto order_id =
            first_response.simulation_order_id;
        SimulationReconciliationService reconciliation(journal);
        REQUIRE(
            reconciliation.apply(
                "RES-GROSS-UNKNOWN",
                order_id,
                SimulationReconciliationType::MarkUnknown,
                0.0,
                2'100,
                "unknown") ==
            OrderState::UnknownReconcileRequired);
        REQUIRE(
            reconciliation.apply(
                "RES-GROSS-WORKING",
                order_id,
                SimulationReconciliationType::Working,
                0.0,
                2'200,
                "working") ==
            OrderState::Working);
        REQUIRE(
            reconciliation.apply(
                "RES-GROSS-PARTIAL",
                order_id,
                SimulationReconciliationType::PartialFill,
                0.05,
                2'300,
                "partial") ==
            OrderState::Partial);

        summary = journal->exposure_reservation_summary();
        REQUIRE(summary.active_reservations == 1);
        REQUIRE(std::fabs(summary.reserved_gross_notional - 10.0) <
                1e-12);

        REQUIRE(
            reconciliation.apply(
                "RES-GROSS-FILLED",
                order_id,
                SimulationReconciliationType::Filled,
                0.1,
                2'400,
                "filled") ==
            OrderState::Filled);

        summary = journal->exposure_reservation_summary();
        REQUIRE(summary.active_reservations == 0);
        REQUIRE(std::fabs(summary.reserved_gross_notional) < 1e-12);
        REQUIRE(summary.reserved_position_slots == 0);
        REQUIRE(journal->exposure_reservation_release_count() == 1);

        auto replayed =
            std::make_shared<astu::execution::ExecutionJournal>(
                journal_path,
                100);
        const auto replayed_summary =
            replayed->exposure_reservation_summary();
        REQUIRE(replayed_summary.active_reservations == 0);
        REQUIRE(replayed->exposure_reservation_create_count() == 1);
        REQUIRE(replayed->exposure_reservation_release_count() == 1);
    }

    {
        const auto journal_path = root / "positions.jsonl";
        auto journal =
            std::make_shared<astu::execution::ExecutionJournal>(
                journal_path,
                100);
        auto dispatcher = reservation_dispatcher(
            journal,
            base_risk(0.0, 100'000.0, 0, 1));

        const auto first = request("POS-1");
        const auto first_response =
            dispatcher.dispatch(first, 3'000);
        REQUIRE(first_response.decision_code ==
                DecisionCode::OrderRoutingDisabled);
        REQUIRE(journal->exposure_reservation_summary()
                    .reserved_position_slots == 1);

        const auto second = request("POS-2");
        const auto second_response =
            dispatcher.dispatch(second, 3'001);
        REQUIRE(second_response.decision_code ==
                DecisionCode::RiskBlocked);
        REQUIRE(!second_response.accepted_for_simulation);
    }

    {
        const auto journal_path = root / "scale.jsonl";
        auto journal =
            std::make_shared<astu::execution::ExecutionJournal>(
                journal_path,
                100);

        const auto scale_request =
            request("SCALE-IN", SignalAction::ScaleIn);
        const auto scale_response =
            accepted_response(scale_request);
        persist_accepted(
            journal,
            scale_request,
            scale_response,
            4'000);

        const auto scale_summary =
            journal->exposure_reservation_summary();
        REQUIRE(scale_summary.active_reservations == 1);
        REQUIRE(scale_summary.reserved_position_slots == 0);
        REQUIRE(std::fabs(
                    scale_summary.reserved_gross_notional -
                    scale_response.simulated_notional) <
                1e-12);

        const auto sell_request =
            request("SELL", SignalAction::Sell);
        const auto sell_response =
            accepted_response(sell_request);
        astu::execution::SimulationOrderLifecycle lifecycle(journal);
        lifecycle.observe(
            sell_request,
            sell_response,
            4'100);
        journal->append_simulation_order_intent(
            sell_request,
            sell_response,
            4'100);
        REQUIRE(!journal->append_exposure_reservation(
            sell_request,
            sell_response,
            4'100));
        REQUIRE(journal->exposure_reservation_summary()
                    .active_reservations == 1);
    }

    {
        const auto journal_path = root / "reconstruct.jsonl";
        const auto req = request("RECONSTRUCT");
        const auto response = accepted_response(req);
        {
            auto journal =
                std::make_shared<astu::execution::ExecutionJournal>(
                    journal_path,
                    100);
            astu::execution::SimulationOrderLifecycle lifecycle(journal);
            lifecycle.observe(req, response, 5'000);
            journal->append_simulation_order_intent(
                req,
                response,
                5'000);
            journal->append(req, response, 5'000);
            REQUIRE(journal->exposure_reservation_summary()
                        .active_reservations == 0);
        }

        auto replayed =
            std::make_shared<astu::execution::ExecutionJournal>(
                journal_path,
                100);
        const auto summary =
            replayed->exposure_reservation_summary();
        REQUIRE(summary.active_reservations == 1);
        REQUIRE(std::fabs(
                    summary.reserved_gross_notional -
                    response.simulated_notional) <
                1e-12);
        REQUIRE(summary.reserved_position_slots == 1);
        REQUIRE(
            replayed->exposure_reservation_reconstructed_count() ==
            1);

        SimulationReconciliationService reconciliation(replayed);
        REQUIRE(
            reconciliation.apply(
                "RES-RECONSTRUCT-UNKNOWN",
                response.simulation_order_id,
                SimulationReconciliationType::MarkUnknown,
                0.0,
                5'100,
                "legacy reconstructed reservation unknown") ==
            OrderState::UnknownReconcileRequired);
        REQUIRE(
            reconciliation.apply(
                "RES-RECONSTRUCT-WORKING",
                response.simulation_order_id,
                SimulationReconciliationType::Working,
                0.0,
                5'200,
                "legacy reconstructed reservation working") ==
            OrderState::Working);
        REQUIRE(
            reconciliation.apply(
                "RES-RECONSTRUCT-FILLED",
                response.simulation_order_id,
                SimulationReconciliationType::Filled,
                response.simulated_quantity,
                5'300,
                "legacy reconstructed reservation filled") ==
            OrderState::Filled);
        REQUIRE(replayed->exposure_reservation_summary()
                    .active_reservations == 0);
        REQUIRE(replayed->exposure_reservation_release_count() == 1);

        auto replayed_again =
            std::make_shared<astu::execution::ExecutionJournal>(
                journal_path,
                100);
        REQUIRE(replayed_again->exposure_reservation_summary()
                    .active_reservations == 0);
        REQUIRE(
            replayed_again->exposure_reservation_reconstructed_count() ==
            1);
        REQUIRE(
            replayed_again->exposure_reservation_release_count() ==
            1);
    }

    std::filesystem::remove_all(root);
    std::cout << "astu_exposure_reservation_tests PASS\n";
    return 0;
}
