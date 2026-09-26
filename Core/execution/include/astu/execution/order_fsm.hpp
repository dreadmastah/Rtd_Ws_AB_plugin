#pragma once

#include <cstdint>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>

#include "astu/core/contracts.hpp"

namespace astu::execution {

enum class OrderState {
    IntentReceived,
    Validating,
    RiskApproved,
    Sizing,
    Submitting,
    Acknowledged,
    Working,
    Partial,
    Filled,
    Canceled,
    Rejected,
    UnknownReconcileRequired,
};

inline std::string order_state_to_string(OrderState state) {
    switch (state) {
    case OrderState::IntentReceived: return "INTENT_RECEIVED";
    case OrderState::Validating: return "VALIDATING";
    case OrderState::RiskApproved: return "RISK_APPROVED";
    case OrderState::Sizing: return "SIZING";
    case OrderState::Submitting: return "SUBMITTING";
    case OrderState::Acknowledged: return "ACKNOWLEDGED";
    case OrderState::Working: return "WORKING";
    case OrderState::Partial: return "PARTIAL";
    case OrderState::Filled: return "FILLED";
    case OrderState::Canceled: return "CANCELED";
    case OrderState::Rejected: return "REJECTED";
    case OrderState::UnknownReconcileRequired:
        return "UNKNOWN_RECONCILE_REQUIRED";
    }
    throw std::invalid_argument("unsupported OrderState");
}

inline OrderState order_state_from_string(const std::string& value) {
    if (value == "INTENT_RECEIVED") return OrderState::IntentReceived;
    if (value == "VALIDATING") return OrderState::Validating;
    if (value == "RISK_APPROVED") return OrderState::RiskApproved;
    if (value == "SIZING") return OrderState::Sizing;
    if (value == "SUBMITTING") return OrderState::Submitting;
    if (value == "ACKNOWLEDGED") return OrderState::Acknowledged;
    if (value == "WORKING") return OrderState::Working;
    if (value == "PARTIAL") return OrderState::Partial;
    if (value == "FILLED") return OrderState::Filled;
    if (value == "CANCELED") return OrderState::Canceled;
    if (value == "REJECTED") return OrderState::Rejected;
    if (value == "UNKNOWN_RECONCILE_REQUIRED") {
        return OrderState::UnknownReconcileRequired;
    }
    throw std::invalid_argument("unknown OrderState value");
}

inline bool is_terminal_order_state(OrderState state) noexcept {
    return state == OrderState::Filled ||
           state == OrderState::Canceled ||
           state == OrderState::Rejected;
}

class OrderStateMachine {
public:
    static bool can_transition(OrderState from, OrderState to) noexcept {
        if (from == to) {
            return from == OrderState::Partial;
        }

        switch (from) {
        case OrderState::IntentReceived:
            return to == OrderState::Validating ||
                   to == OrderState::Rejected;
        case OrderState::Validating:
            return to == OrderState::RiskApproved ||
                   to == OrderState::Rejected ||
                   to == OrderState::UnknownReconcileRequired;
        case OrderState::RiskApproved:
            return to == OrderState::Sizing ||
                   to == OrderState::Rejected ||
                   to == OrderState::UnknownReconcileRequired;
        case OrderState::Sizing:
            return to == OrderState::Submitting ||
                   to == OrderState::Rejected ||
                   to == OrderState::UnknownReconcileRequired;
        case OrderState::Submitting:
            return to == OrderState::Acknowledged ||
                   to == OrderState::Rejected ||
                   to == OrderState::UnknownReconcileRequired;
        case OrderState::Acknowledged:
            return to == OrderState::Working ||
                   to == OrderState::Rejected ||
                   to == OrderState::UnknownReconcileRequired;
        case OrderState::Working:
            return to == OrderState::Partial ||
                   to == OrderState::Filled ||
                   to == OrderState::Canceled ||
                   to == OrderState::Rejected ||
                   to == OrderState::UnknownReconcileRequired;
        case OrderState::Partial:
            return to == OrderState::Partial ||
                   to == OrderState::Filled ||
                   to == OrderState::Canceled ||
                   to == OrderState::Rejected ||
                   to == OrderState::UnknownReconcileRequired;
        case OrderState::UnknownReconcileRequired:
            return to == OrderState::Acknowledged ||
                   to == OrderState::Working ||
                   to == OrderState::Partial ||
                   to == OrderState::Filled ||
                   to == OrderState::Canceled ||
                   to == OrderState::Rejected;
        case OrderState::Filled:
        case OrderState::Canceled:
        case OrderState::Rejected:
            return false;
        }
        return false;
    }

    static void require_transition(OrderState from, OrderState to) {
        if (!can_transition(from, to)) {
            throw std::invalid_argument(
                "invalid order-state transition " +
                order_state_to_string(from) + " -> " +
                order_state_to_string(to));
        }
    }
};

namespace detail {

inline std::uint64_t fnv1a64(
    std::string_view text,
    std::uint64_t seed) noexcept {
    constexpr std::uint64_t kPrime = 1099511628211ULL;
    std::uint64_t hash = seed;
    for (const unsigned char ch : text) {
        hash ^= static_cast<std::uint64_t>(ch);
        hash *= kPrime;
    }
    return hash;
}

inline std::string fixed_hex(std::uint64_t value) {
    std::ostringstream out;
    out << std::hex << std::setfill('0') << std::setw(16) << value;
    return out.str();
}

}  // namespace detail

inline std::string deterministic_simulation_order_id(
    const std::string& request_id,
    const std::string& idempotency_key,
    const astu::core::SignalIntent& intent) {
    const std::string material =
        request_id + "|" +
        idempotency_key + "|" +
        intent.signal_id + "|" +
        intent.strategy_id + "|" +
        intent.strategy_version + "|" +
        intent.symbol + "|" +
        std::to_string(static_cast<int>(intent.action)) + "|" +
        std::to_string(static_cast<int>(intent.side));

    constexpr std::uint64_t kSeed1 = 14695981039346656037ULL;
    constexpr std::uint64_t kSeed2 = 7809847782465536322ULL;
    const auto h1 = detail::fnv1a64(material, kSeed1);
    const auto h2 = detail::fnv1a64(material, kSeed2);
    return "SIMORD-" + detail::fixed_hex(h1) + detail::fixed_hex(h2);
}

}  // namespace astu::execution
