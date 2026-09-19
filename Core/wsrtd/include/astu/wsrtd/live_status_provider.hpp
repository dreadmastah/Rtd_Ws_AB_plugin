#pragma once

#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>

#include "astu/core/contracts.hpp"
#include "astu/ipc/flat_json.hpp"

namespace astu::wsrtd {

class LiveStatusProvider {
public:
    explicit LiveStatusProvider(
        std::filesystem::path status_dir,
        std::uint64_t max_snapshot_age_ms = 5'000)
        : status_dir_(std::move(status_dir)),
          max_snapshot_age_ms_(max_snapshot_age_ms) {}

    astu::core::DataStatus operator()(const astu::core::SignalIntent& intent) const {
        astu::core::DataStatus out;
        out.source = "WSRTD-CleanRoomR2";
        out.symbol = intent.symbol;

        try {
            const auto path = status_dir_ / (intent.symbol + ".json");
            const std::string json = read_all(path);
            const auto obj = astu::ipc::FlatJsonParser(json).parse();

            const auto schema = astu::ipc::require_u64(obj, "schemaVersion");
            const auto source = astu::ipc::require_string(obj, "source");
            const auto symbol = astu::ipc::require_string(obj, "symbol");
            const auto generated_ms = astu::ipc::require_u64(obj, "generatedUnixMs");

            if (schema != 1 || source != "WSRTD-CleanRoomR2" || symbol != intent.symbol) {
                out.detail = "runtime DataStatus identity/header mismatch";
                return out;
            }

            const auto now_ms = utc_now_ms();
            const bool too_far_future =
                generated_ms > now_ms && generated_ms - now_ms > 5'000;
            const bool too_old =
                generated_ms <= now_ms && now_ms - generated_ms > max_snapshot_age_ms_;
            if (too_far_future || too_old) {
                out.detail = "runtime DataStatus snapshot stale";
                return out;
            }

            out.live = astu::ipc::require_bool(obj, "live");
            out.fresh = astu::ipc::require_bool(obj, "fresh");
            out.cache_ready = astu::ipc::require_bool(obj, "cacheReady");
            out.identity_ready = astu::ipc::require_bool(obj, "identityReady");

            const auto universe_id = astu::ipc::require_string(obj, "universeId");
            const auto universe_version = astu::ipc::require_u64(obj, "universeVersion");
            const auto universe_hash = astu::ipc::require_string(obj, "universeHash");
            const auto data_generation = astu::ipc::require_u64(obj, "dataGeneration");
            const auto generation_kind = astu::ipc::require_string(obj, "generationKind");

            if (out.identity_ready && !universe_id.empty() && universe_version > 0 &&
                !universe_hash.empty() && data_generation > 0 &&
                !generation_kind.empty()) {
                out.universe_id = universe_id;
                out.universe_version = universe_version;
                out.universe_hash = universe_hash;
                out.data_generation = data_generation;
                out.generation_kind = generation_kind;
            } else {
                out.identity_ready = false;
            }

            const auto cache_eod = astu::ipc::require_u64(obj, "cacheEod");
            const auto cache_intraday = astu::ipc::require_u64(obj, "cacheIntraday");
            if (cache_eod > 0) {
                out.cache_eod = static_cast<std::uint32_t>(cache_eod);
            }
            if (cache_intraday > 0) {
                out.cache_intraday = static_cast<std::uint32_t>(cache_intraday);
            }

            out.detail = astu::ipc::require_string(obj, "detail");
        } catch (const std::exception& exc) {
            out.live = false;
            out.fresh = false;
            out.cache_ready = false;
            out.identity_ready = false;
            out.detail = std::string("runtime DataStatus unavailable: ") + exc.what();
        }
        return out;
    }

private:
    static std::uint64_t utc_now_ms() {
        const auto now = std::chrono::system_clock::now().time_since_epoch();
        return static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::milliseconds>(now).count());
    }

    static std::string read_all(const std::filesystem::path& path) {
        std::ifstream in(path, std::ios::binary);
        if (!in) {
            throw std::runtime_error("cannot open " + path.string());
        }
        std::ostringstream out;
        out << in.rdbuf();
        return out.str();
    }

    std::filesystem::path status_dir_;
    std::uint64_t max_snapshot_age_ms_{5'000};
};

}  // namespace astu::wsrtd
