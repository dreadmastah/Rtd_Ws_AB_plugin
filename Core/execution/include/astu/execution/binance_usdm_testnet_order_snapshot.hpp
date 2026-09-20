#pragma once

#include <cmath>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <utility>

#include "astu/execution/authoritative_order_snapshot.hpp"
#include "astu/execution/binance_usdm_testnet_order_gateway.hpp"
#include "astu/execution/execution_journal.hpp"

namespace astu::execution {

inline OrderState binance_testnet_status_to_order_state(
    const std::string& status,
    double cumulative_filled_quantity,
    double order_quantity) {
    if (!std::isfinite(cumulative_filled_quantity) ||
        !std::isfinite(order_quantity) ||
        cumulative_filled_quantity < 0.0 ||
        order_quantity <= 0.0 ||
        cumulative_filled_quantity > order_quantity + 1e-12) {
        return OrderState::UnknownReconcileRequired;
    }

    if (status == "FILLED") {
        return std::fabs(
                   cumulative_filled_quantity - order_quantity) <=
                1e-12
            ? OrderState::Filled
            : OrderState::UnknownReconcileRequired;
    }
    if (status == "PARTIALLY_FILLED") {
        return cumulative_filled_quantity > 1e-12 &&
                       cumulative_filled_quantity <
                           order_quantity - 1e-12
            ? OrderState::Partial
            : OrderState::UnknownReconcileRequired;
    }
    if (status == "NEW") {
        return cumulative_filled_quantity <= 1e-12
            ? OrderState::Working
            : OrderState::UnknownReconcileRequired;
    }
    if (status == "CANCELED" ||
        status == "EXPIRED" ||
        status == "EXPIRED_IN_MATCH") {
        return OrderState::Canceled;
    }
    if (status == "REJECTED") {
        return OrderState::Rejected;
    }
    return OrderState::UnknownReconcileRequired;
}

class BinanceUsdmTestnetOrderSnapshotProvider {
public:
    using Query = std::function<TestnetOrderQueryResult(
        const std::string&,
        const std::string&,
        std::uint64_t)>;

    BinanceUsdmTestnetOrderSnapshotProvider(
        std::shared_ptr<ExecutionJournal> journal,
        Query query)
        : journal_(std::move(journal)),
          query_(std::move(query)) {
        if (!journal_ || !query_) {
            throw std::invalid_argument(
                "Testnet snapshot provider requires journal/query");
        }
    }

    AuthoritativeSimulationOrderSnapshot operator()(
        const std::string& simulation_order_id) const {
        AuthoritativeSimulationOrderSnapshot out;
        out.source = "BINANCE_USDM_TESTNET_REST_ORDER_QUERY";
        out.simulation_order_id = simulation_order_id;
        out.generated_unix_ms = utc_now_ms();

        const auto intent =
            journal_->simulation_order_intent(simulation_order_id);
        if (!intent.has_value()) {
            out.detail =
                "persistent normalized order intent unavailable";
            return out;
        }

        const auto client_order_id =
            deterministic_testnet_client_order_id(
                simulation_order_id);
        const auto result = query_(
            intent->symbol,
            client_order_id,
            out.generated_unix_ms);

        if (!result.ready) {
            out.detail = result.detail;
            return out;
        }
        if (!result.found) {
            out.detail =
                "Binance Testnet order identity not found; absence does not resolve ambiguous submission: " +
                result.detail;
            return out;
        }
        if (result.client_order_id != client_order_id ||
            result.symbol != intent->symbol ||
            std::fabs(
                result.original_quantity -
                intent->quantity) > 1e-12) {
            out.detail =
                "Binance Testnet order identity/quantity mismatch";
            return out;
        }

        out.ready = true;
        out.state = binance_testnet_status_to_order_state(
            result.exchange_status,
            result.cumulative_filled_quantity,
            intent->quantity);
        out.cumulative_filled_quantity =
            result.cumulative_filled_quantity;
        out.detail =
            result.detail +
            "; exchangeOrderId=" +
            result.exchange_order_id +
            "; clientOrderId=" +
            result.client_order_id +
            "; exchangeStatus=" +
            result.exchange_status;
        if (out.state == OrderState::UnknownReconcileRequired) {
            out.ready = false;
            out.detail =
                "unsupported/inconsistent Binance Testnet order state: " +
                out.detail;
        }
        return out;
    }

private:
    static std::uint64_t utc_now_ms() {
        const auto now =
            std::chrono::system_clock::now().time_since_epoch();
        return static_cast<std::uint64_t>(
            std::chrono::duration_cast<
                std::chrono::milliseconds>(now).count());
    }

    std::shared_ptr<ExecutionJournal> journal_;
    Query query_;
};

}  // namespace astu::execution
