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

namespace astu::account {

class LivePositionProvider {
public:
    explicit LivePositionProvider(
        std::filesystem::path status_dir,
        std::uint64_t max_snapshot_age_ms = 7'000)
        : status_dir_(std::move(status_dir)),
          max_snapshot_age_ms_(max_snapshot_age_ms) {}

    astu::core::PositionSnapshot operator()(
        const astu::core::SignalIntent& intent) const {
        astu::core::PositionSnapshot out;
        out.symbol = intent.symbol;

        try {
            const auto path = status_dir_ / (intent.symbol + ".json");
            const auto json = read_all(path);
            const auto obj = astu::ipc::FlatJsonParser(json).parse();

            if (astu::ipc::require_u64(obj, "schemaVersion") != 1 ||
                astu::ipc::require_string(obj, "messageType") != "PositionSnapshot.v1") {
                out.detail = "position snapshot schema mismatch";
                return out;
            }

            const auto symbol = astu::ipc::require_string(obj, "symbol");
            if (symbol != intent.symbol) {
                out.detail = "position snapshot symbol mismatch";
                return out;
            }

            const auto generated_ms = astu::ipc::require_u64(obj, "generatedUnixMs");
            const auto now_ms = utc_now_ms();
            const bool too_far_future =
                generated_ms > now_ms && generated_ms - now_ms > 5'000;
            const bool too_old =
                generated_ms <= now_ms &&
                now_ms - generated_ms > max_snapshot_age_ms_;
            if (too_far_future || too_old) {
                out.detail = "position snapshot stale";
                return out;
            }

            out.schema_version = 1;
            out.reconciled = astu::ipc::require_bool(obj, "reconciled");
            out.source = astu::ipc::require_string(obj, "source");
            out.symbol = symbol;
            out.mode = mode_from_string(astu::ipc::require_string(obj, "mode"));
            out.quantity = astu::ipc::require_double(obj, "quantity");
            out.notional = astu::ipc::require_double(obj, "notional");
            out.detail = astu::ipc::require_string(obj, "detail");

            if (out.quantity < 0.0 || out.notional < 0.0) {
                out.reconciled = false;
                out.mode = astu::core::PositionMode::Unknown;
                out.detail = "position snapshot contains negative absolute quantity/notional";
            }
        } catch (const std::exception& exc) {
            out.reconciled = false;
            out.mode = astu::core::PositionMode::Unknown;
            out.detail = std::string("position snapshot unavailable: ") + exc.what();
        }
        return out;
    }

private:
    static astu::core::PositionMode mode_from_string(const std::string& value) {
        if (value == "FLAT") return astu::core::PositionMode::Flat;
        if (value == "LONG") return astu::core::PositionMode::Long;
        if (value == "SHORT") return astu::core::PositionMode::Short;
        if (value == "HEDGED") return astu::core::PositionMode::Hedged;
        return astu::core::PositionMode::Unknown;
    }

    static std::uint64_t utc_now_ms() {
        const auto now = std::chrono::system_clock::now().time_since_epoch();
        return static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::milliseconds>(now).count());
    }

    static std::string read_all(const std::filesystem::path& path) {
        std::ifstream in(path, std::ios::binary);
        if (!in) {
            throw std::runtime_error("cannot open position snapshot " + path.string());
        }
        std::ostringstream out;
        out << in.rdbuf();
        return out.str();
    }

    std::filesystem::path status_dir_;
    std::uint64_t max_snapshot_age_ms_{7'000};
};

}  // namespace astu::account
