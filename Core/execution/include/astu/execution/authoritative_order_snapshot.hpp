#pragma once

#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

#include "astu/execution/order_fsm.hpp"
#include "astu/ipc/flat_json.hpp"

namespace astu::execution {

struct AuthoritativeSimulationOrderSnapshot {
    std::uint32_t schema_version{1};
    bool ready{false};
    std::string source;
    std::string simulation_order_id;
    OrderState state{OrderState::UnknownReconcileRequired};
    double cumulative_filled_quantity{0.0};
    std::uint64_t generated_unix_ms{0};
    std::string detail;
};

class FileBackedSimulationOrderSnapshotProvider {
public:
    explicit FileBackedSimulationOrderSnapshotProvider(
        std::filesystem::path status_dir,
        std::uint64_t max_snapshot_age_ms = 7'000)
        : status_dir_(std::move(status_dir)),
          max_snapshot_age_ms_(max_snapshot_age_ms) {}

    AuthoritativeSimulationOrderSnapshot operator()(
        const std::string& simulation_order_id) const {
        AuthoritativeSimulationOrderSnapshot out;
        out.simulation_order_id = simulation_order_id;

        try {
            const auto path =
                status_dir_ / (simulation_order_id + ".json");
            const auto json = read_all(path);
            const auto obj =
                astu::ipc::FlatJsonParser(json).parse();

            if (astu::ipc::require_u64(obj, "schemaVersion") != 1 ||
                astu::ipc::require_string(obj, "messageType") !=
                    "AuthoritativeSimulationOrderSnapshot.v1") {
                out.detail =
                    "authoritative order snapshot schema mismatch";
                return out;
            }

            const auto order_id =
                astu::ipc::require_string(
                    obj,
                    "simulationOrderId");
            if (order_id != simulation_order_id) {
                out.detail =
                    "authoritative order snapshot identity mismatch";
                return out;
            }

            const auto generated_ms =
                astu::ipc::require_u64(obj, "generatedUnixMs");
            const auto now_ms = utc_now_ms();
            const bool too_far_future =
                generated_ms > now_ms &&
                generated_ms - now_ms > 5'000;
            const bool too_old =
                generated_ms <= now_ms &&
                now_ms - generated_ms >
                    max_snapshot_age_ms_;
            if (too_far_future || too_old) {
                out.detail =
                    "authoritative order snapshot stale";
                return out;
            }

            out.schema_version = 1;
            out.ready =
                astu::ipc::require_bool(obj, "ready");
            out.source =
                astu::ipc::require_string(obj, "source");
            out.simulation_order_id = order_id;
            out.state = order_state_from_string(
                astu::ipc::require_string(
                    obj,
                    "state"));
            out.cumulative_filled_quantity =
                astu::ipc::require_double(
                    obj,
                    "cumulativeFilledQuantity");
            out.generated_unix_ms = generated_ms;
            out.detail =
                astu::ipc::require_string(obj, "detail");

            if (out.cumulative_filled_quantity < 0.0) {
                out.ready = false;
                out.detail =
                    "authoritative order snapshot has negative cumulative fill";
            }
        } catch (const std::exception& exc) {
            out.ready = false;
            out.detail =
                std::string(
                    "authoritative order snapshot unavailable: ") +
                exc.what();
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

    static std::string read_all(
        const std::filesystem::path& path) {
        std::ifstream in(path, std::ios::binary);
        if (!in) {
            throw std::runtime_error(
                "cannot open authoritative order snapshot " +
                path.string());
        }
        std::ostringstream out;
        out << in.rdbuf();
        return out.str();
    }

    std::filesystem::path status_dir_;
    std::uint64_t max_snapshot_age_ms_{7'000};
};

}  // namespace astu::execution
