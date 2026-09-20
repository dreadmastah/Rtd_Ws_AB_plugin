#pragma once

#include <algorithm>
#include <cstdint>
#include <limits>

#include "astu/core/contracts.hpp"

namespace astu::execution {

struct ExposureReservationSummary {
    std::uint64_t active_reservations{0};
    double reserved_gross_notional{0.0};
    std::uint32_t reserved_position_slots{0};
    std::uint64_t symbol_active_reservations{0};
    double symbol_reserved_gross_notional{0.0};
    double reserved_available_balance{0.0};
};

class ExposureReservationRiskOverlay {
public:
    static astu::core::AccountRiskSnapshot apply(
        astu::core::AccountRiskSnapshot risk,
        const ExposureReservationSummary& reservations,
        std::uint64_t max_pending_entry_scale_in_reservations = 0,
        bool symbol_exposure_reconciled = false,
        double reconciled_symbol_notional = 0.0,
        double max_symbol_notional = 0.0,
        double minimum_available_balance_reserve = 0.0,
        double margin_reservation_rate = 0.0) noexcept {
        risk.gross_notional = std::max(
            0.0,
            risk.gross_notional +
                std::max(0.0, reservations.reserved_gross_notional));

        const auto projected_positions =
            static_cast<std::uint64_t>(risk.open_positions) +
            static_cast<std::uint64_t>(
                reservations.reserved_position_slots);
        risk.open_positions = static_cast<std::uint32_t>(
            std::min<std::uint64_t>(
                projected_positions,
                std::numeric_limits<std::uint32_t>::max()));

        risk.pending_entry_scale_in_reservations =
            reservations.active_reservations;
        risk.max_pending_entry_scale_in_reservations =
            max_pending_entry_scale_in_reservations;
        risk.symbol_exposure_reconciled =
            symbol_exposure_reconciled;
        risk.symbol_notional = std::max(
            0.0,
            reconciled_symbol_notional +
                std::max(
                    0.0,
                    reservations.symbol_reserved_gross_notional));
        risk.max_symbol_notional =
            std::max(0.0, max_symbol_notional);
        risk.available_balance = std::max(
            0.0,
            risk.available_balance -
                std::max(
                    0.0,
                    reservations.reserved_available_balance));
        risk.minimum_available_balance_reserve =
            std::max(0.0, minimum_available_balance_reserve);
        risk.margin_reservation_rate =
            std::max(0.0, margin_reservation_rate);
        return risk;
    }
};

inline bool reserves_new_position_slot(
    astu::core::SignalAction action) noexcept {
    return action == astu::core::SignalAction::Buy;
}

}  // namespace astu::execution
