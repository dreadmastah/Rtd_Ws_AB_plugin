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
};

class ExposureReservationRiskOverlay {
public:
    static astu::core::AccountRiskSnapshot apply(
        astu::core::AccountRiskSnapshot risk,
        const ExposureReservationSummary& reservations) noexcept {
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
        return risk;
    }
};

inline bool reserves_new_position_slot(
    astu::core::SignalAction action) noexcept {
    return action == astu::core::SignalAction::Buy;
}

}  // namespace astu::execution
