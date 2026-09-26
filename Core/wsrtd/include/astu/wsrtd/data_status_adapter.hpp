#pragma once

#include <cstdint>
#include <string>

#include "astu/core/contracts.hpp"

namespace astu::wsrtd {

struct WsrtdR2Snapshot {
    std::string symbol;
    std::uint32_t cache_eod{0};
    std::uint32_t cache_intraday{0};
    std::uint32_t eod_retention{300};
    std::uint32_t intraday_retention{1500};
    std::uint64_t quote_age_ms{0};
};

struct WsrtdR2IdentitySnapshot {
    bool verified{false};
    std::string symbol;
    std::string universe_id;
    std::uint64_t universe_version{0};
    std::string universe_hash;
    std::uint64_t data_generation{0};
    std::string generation_kind{"WSRTD_R2_COMPLETED_M1_OPEN_MS"};
};

class DataStatusAdapter {
public:
    static astu::core::DataStatus from_r2(
        const WsrtdR2Snapshot& snapshot,
        std::uint64_t max_quote_age_ms = 5'000) {
        WsrtdR2IdentitySnapshot missing;
        return from_r2(snapshot, missing, max_quote_age_ms);
    }

    static astu::core::DataStatus from_r2(
        const WsrtdR2Snapshot& snapshot,
        const WsrtdR2IdentitySnapshot& identity,
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

        const bool identity_valid =
            identity.verified &&
            identity.symbol == snapshot.symbol &&
            !identity.universe_id.empty() &&
            identity.universe_version > 0 &&
            !identity.universe_hash.empty() &&
            identity.data_generation > 0 &&
            !identity.generation_kind.empty();

        if (identity_valid) {
            out.identity_ready = true;
            out.universe_id = identity.universe_id;
            out.universe_version = identity.universe_version;
            out.universe_hash = identity.universe_hash;
            out.data_generation = identity.data_generation;
            out.generation_kind = identity.generation_kind;
            out.detail = out.cache_ready
                ? "R2 cache/freshness and compatibility identity ready"
                : "R2 compatibility identity ready; cache/freshness not ready";
        } else {
            out.identity_ready = false;
            out.universe_id = std::nullopt;
            out.universe_version = std::nullopt;
            out.universe_hash = std::nullopt;
            out.data_generation = std::nullopt;
            out.generation_kind = std::nullopt;
            out.detail = out.cache_ready
                ? "R2 cache/freshness observed; compatibility identity unavailable"
                : "R2 cache/freshness not ready; compatibility identity unavailable";
        }
        return out;
    }
};

}  // namespace astu::wsrtd
