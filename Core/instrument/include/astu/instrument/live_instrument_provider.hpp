#pragma once

#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

#include "astu/core/contracts.hpp"
#include "astu/ipc/flat_json.hpp"

namespace astu::instrument {

class LiveInstrumentProvider {
public:
    explicit LiveInstrumentProvider(
        std::filesystem::path status_dir,
        std::uint64_t max_snapshot_age_ms = 86'400'000)
        : status_dir_(std::move(status_dir)),
          max_snapshot_age_ms_(max_snapshot_age_ms) {}

    astu::core::InstrumentConstraints operator()(
        const astu::core::SignalIntent& intent) const {
        astu::core::InstrumentConstraints out;
        out.symbol = intent.symbol;

        try {
            const auto path = status_dir_ / (intent.symbol + ".json");
            const auto json = read_all(path);
            const auto obj = astu::ipc::FlatJsonParser(json).parse();

            if (astu::ipc::require_u64(obj, "schemaVersion") != 1 ||
                astu::ipc::require_string(obj, "messageType") !=
                    "InstrumentConstraints.v1") {
                out.detail = "instrument constraints schema mismatch";
                return out;
            }

            const auto symbol = astu::ipc::require_string(obj, "symbol");
            if (symbol != intent.symbol) {
                out.detail = "instrument constraints symbol mismatch";
                return out;
            }

            const auto generated_ms =
                astu::ipc::require_u64(obj, "generatedUnixMs");
            const auto now_ms = utc_now_ms();
            const bool too_far_future =
                generated_ms > now_ms && generated_ms - now_ms > 5'000;
            const bool too_old =
                generated_ms <= now_ms &&
                now_ms - generated_ms > max_snapshot_age_ms_;
            if (too_far_future || too_old) {
                out.detail = "instrument constraints snapshot stale";
                return out;
            }

            out.schema_version = 1;
            out.ready = astu::ipc::require_bool(obj, "ready");
            out.source = astu::ipc::require_string(obj, "source");
            out.symbol = symbol;
            out.price_tick = astu::ipc::require_double(obj, "priceTick");
            out.quantity_step =
                astu::ipc::require_double(obj, "quantityStep");
            out.min_quantity =
                astu::ipc::require_double(obj, "minQuantity");
            out.max_quantity =
                astu::ipc::require_double(obj, "maxQuantity");
            out.min_notional =
                astu::ipc::require_double(obj, "minNotional");
            out.max_notional =
                astu::ipc::require_double(obj, "maxNotional");
            out.detail = astu::ipc::require_string(obj, "detail");
        } catch (const std::exception& exc) {
            out.ready = false;
            out.detail =
                std::string("instrument constraints unavailable: ") + exc.what();
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
            throw std::runtime_error(
                "cannot open instrument constraints " + path.string());
        }
        std::ostringstream out;
        out << in.rdbuf();
        return out.str();
    }

    std::filesystem::path status_dir_;
    std::uint64_t max_snapshot_age_ms_{86'400'000};
};

}  // namespace astu::instrument
