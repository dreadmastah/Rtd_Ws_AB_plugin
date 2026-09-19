#pragma once

#include <cstdint>
#include <string>

#include "astu/core/contracts.hpp"

namespace astu::wsrtd {

// Snapshot of fields the current CleanRoomR2 plugin can expose today.
// The current R2 ABI does not expose architecture-level universeVersion or
// dataGeneration, so this adapter deliberately leaves those values unknown.
struct WsrtdR2Snapshot {
    std::string symbol;
    std::uint32_t cache_eod{0};
    std::uint32_t cache_intraday{0};
    std::uint32_t eod_retention{300};
    std::uint32_t intraday_retention{1500};
    std::uint64_t quote_age_ms{0};
};

class DataStatusAdapter {
public:
    static astu::core::DataStatus from_r2(
        const WsrtdR2Snapshot& snapshot,
        std::uint64_t max_quote_age_ms = 5'000) {
        astu::core::DataStatus out;
        out.source = "WSRTD-CleanRoomR2";
        out.symbol = snapshot.symbol;
        out.live = snapshot.quote_age_ms <= max_quote_age_ms;
        out.fresh = out.live;
        out.cache_eod = snapshot.cache_eod;
        out.cache_intraday = snapshot.cache_intraday;
        out.cache_ready =
            snapshot.cache_eod >= snapshot.eod_retention &&
            snapshot.cache_intraday >= snapshot.intraday_retention;

        // Fail closed: R2 presently has no authoritative universe/data identity
        // fields matching Architecture R3.1 SignalIntent validation requirements.
        out.identity_ready = false;
        out.universe_version = std::nullopt;
        out.data_generation = std::nullopt;
        out.detail = out.cache_ready
            ? "R2 cache/freshness observed; architecture identity unavailable"
            : "R2 cache/freshness not ready; architecture identity unavailable";
        return out;
    }
};

}  // namespace astu::wsrtd
