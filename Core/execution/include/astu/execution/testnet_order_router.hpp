#pragma once

#include <cstdint>
#include <functional>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>

#include "astu/execution/binance_usdm_testnet_order_gateway.hpp"
#include "astu/execution/execution_journal.hpp"
#include "astu/ipc/simulation_protocol.hpp"

namespace astu::execution {

class TestnetOrderRouter {
public:
    using Submitter = std::function<TestnetOrderResult(
        const TestnetOrderRequest&,
        std::uint64_t)>;

    TestnetOrderRouter(
        std::shared_ptr<ExecutionJournal> journal,
        Submitter submitter)
        : journal_(std::move(journal)),
          submitter_(std::move(submitter)) {
        if (!journal_ || !submitter_) {
            throw std::invalid_argument(
                "TestnetOrderRouter requires journal and submitter");
        }
    }

    void route(
        const astu::ipc::SimulationRequest& request,
        astu::ipc::SimulationResponse& response,
        std::int64_t utc_ms) const {
        using astu::core::DecisionCode;
        using astu::execution::OrderState;

        if (response.decision_code !=
                DecisionCode::OrderRoutingDisabled ||
            !response.accepted_for_simulation ||
            response.simulated_quantity <= 0.0) {
            return;
        }

        const auto state =
            journal_->order_state(response.simulation_order_id);
        if (!state.has_value() || *state != OrderState::Sizing) {
            throw std::runtime_error(
                "Testnet routing requires persistent SIZING state");
        }

        TestnetOrderRequest order;
        order.symbol = request.intent.symbol;
        order.exchange_side =
            testnet_exchange_side(request.intent);
        order.quantity = response.simulated_quantity;
        order.client_order_id =
            deterministic_testnet_client_order_id(
                response.simulation_order_id);
        order.reduce_only =
            testnet_reduce_only(request.intent);

        journal_->append_order_transition(
            request,
            response.simulation_order_id,
            OrderState::Submitting,
            utc_ms,
            "Binance USD-M Testnet MARKET submission starting",
            false,
            true,
            std::string(kBinanceUsdmTestnetEnvironment));
        journal_->append_testnet_submission_attempt(
            request,
            response.simulation_order_id,
            order.client_order_id,
            order.exchange_side,
            order.quantity,
            order.reduce_only,
            utc_ms);

        const auto result = submitter_(
            order,
            static_cast<std::uint64_t>(utc_ms));

        response.order_routing_enabled = true;
        response.execution_environment =
            std::string(kBinanceUsdmTestnetEnvironment);
        response.exchange_client_order_id =
            result.client_order_id.empty()
                ? order.client_order_id
                : result.client_order_id;
        response.exchange_order_id = result.exchange_order_id;
        response.exchange_order_status = result.exchange_status;

        switch (result.outcome) {
        case TestnetSubmitOutcome::Acknowledged:
            journal_->append_order_transition(
                request,
                response.simulation_order_id,
                OrderState::Acknowledged,
                utc_ms,
                result.detail,
                false,
                true,
                std::string(kBinanceUsdmTestnetEnvironment));
            response.decision_code =
                DecisionCode::TestnetSubmitted;
            response.reason = result.detail;
            return;

        case TestnetSubmitOutcome::Rejected:
            journal_->append_order_transition(
                request,
                response.simulation_order_id,
                OrderState::Rejected,
                utc_ms,
                result.detail,
                false,
                true,
                std::string(kBinanceUsdmTestnetEnvironment));
            response.decision_code =
                DecisionCode::TestnetRejected;
            response.reason = result.detail;
            return;

        case TestnetSubmitOutcome::Unknown:
            journal_->append_order_transition(
                request,
                response.simulation_order_id,
                OrderState::UnknownReconcileRequired,
                utc_ms,
                result.detail,
                false,
                true,
                std::string(kBinanceUsdmTestnetEnvironment));
            response.decision_code =
                DecisionCode::TestnetUnknown;
            response.reason = result.detail;
            return;
        }
    }

private:
    std::shared_ptr<ExecutionJournal> journal_;
    Submitter submitter_;
};

}  // namespace astu::execution
