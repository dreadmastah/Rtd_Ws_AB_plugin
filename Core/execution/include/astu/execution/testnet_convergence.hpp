#pragma once

#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>

#include "astu/ipc/flat_json.hpp"

namespace astu::execution {

struct TestnetConvergenceState {
    bool ready{false};
    bool stream_alive{false};
    bool ordering_ok{false};
    bool expired{false};
    bool account_converged{false};
    bool positions_converged{false};
    bool orders_converged{false};
    bool rest_fallback_required{true};
    std::uint64_t generated_unix_ms{0};
    std::uint64_t last_frame_unix_ms{0};
    std::uint64_t unresolved_orders{0};
    std::string detail;
};

class FileBackedTestnetConvergenceProvider {
public:
    explicit FileBackedTestnetConvergenceProvider(
        std::filesystem::path path,
        std::uint64_t max_age_ms = 7'000)
        : path_(std::move(path)),
          max_age_ms_(max_age_ms) {
        if (max_age_ms_ == 0) {
            throw std::invalid_argument(
                "Testnet convergence max age must be positive");
        }
    }

    TestnetConvergenceState operator()() const {
        TestnetConvergenceState out;
        try {
            std::ifstream in(path_, std::ios::binary);
            if (!in) {
                out.detail =
                    "Testnet user-data convergence state unavailable";
                return out;
            }
            std::ostringstream text;
            text << in.rdbuf();
            const auto obj =
                astu::ipc::FlatJsonParser(text.str()).parse();

            if (astu::ipc::require_u64(obj, "schemaVersion") != 1 ||
                astu::ipc::require_string(obj, "messageType") !=
                    "TestnetUserDataState.v1" ||
                astu::ipc::require_string(obj, "source") !=
                    "BINANCE_USDM_TESTNET_USER_DATA") {
                out.detail =
                    "Testnet user-data convergence schema/source mismatch";
                return out;
            }

            out.generated_unix_ms =
                astu::ipc::require_u64(obj, "generatedUnixMs");
            out.last_frame_unix_ms =
                astu::ipc::require_u64(obj, "lastFrameUnixMs");
            out.stream_alive =
                astu::ipc::require_bool(obj, "streamAlive");
            out.ordering_ok =
                astu::ipc::require_bool(obj, "orderingOk");
            out.expired =
                astu::ipc::require_bool(obj, "expired");
            out.account_converged =
                astu::ipc::require_bool(obj, "accountConverged");
            out.positions_converged =
                astu::ipc::require_bool(obj, "positionsConverged");
            out.orders_converged =
                astu::ipc::require_bool(obj, "ordersConverged");
            out.rest_fallback_required =
                astu::ipc::require_bool(
                    obj, "restFallbackRequired");
            out.unresolved_orders =
                astu::ipc::require_u64(obj, "unresolvedAstuOrders");
            out.detail =
                astu::ipc::require_string(obj, "detail");

            const auto now = utc_now_ms();
            const bool clock_rollback =
                out.generated_unix_ms > now + 5'000;
            const bool stale =
                out.generated_unix_ms <= now &&
                now - out.generated_unix_ms > max_age_ms_;
            if (clock_rollback || stale) {
                out.detail =
                    clock_rollback
                        ? "Testnet convergence clock rollback"
                        : "Testnet convergence state stale";
                return out;
            }

            const bool source_ready =
                astu::ipc::require_bool(obj, "ready");
            out.ready =
                source_ready &&
                out.stream_alive &&
                out.ordering_ok &&
                !out.expired &&
                out.account_converged &&
                out.positions_converged &&
                out.orders_converged &&
                !out.rest_fallback_required &&
                out.unresolved_orders == 0;
            if (!out.ready && out.detail.empty()) {
                out.detail =
                    "Testnet account/position/order convergence incomplete";
            }
        } catch (const std::exception& exc) {
            out.ready = false;
            out.detail =
                std::string("Testnet convergence parse failure: ") +
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

    std::filesystem::path path_;
    std::uint64_t max_age_ms_{7'000};
};

}  // namespace astu::execution
