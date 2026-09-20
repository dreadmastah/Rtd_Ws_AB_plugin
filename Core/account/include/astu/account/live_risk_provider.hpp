#pragma once

#include <chrono>
#include <cmath>
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

class LiveRiskProvider {
public:
    explicit LiveRiskProvider(
        std::filesystem::path status_file,
        std::uint64_t max_snapshot_age_ms = 5'000)
        : status_file_(std::move(status_file)),
          max_snapshot_age_ms_(max_snapshot_age_ms) {}

    astu::core::AccountRiskSnapshot operator()(
        const astu::core::SignalIntent&) const {
        astu::core::AccountRiskSnapshot risk;
        risk.reconciled = false;
        risk.risk_state = astu::core::RiskState::Emergency;

        try {
            const std::string json = read_all(status_file_);
            const auto obj = astu::ipc::FlatJsonParser(json).parse();

            if (astu::ipc::require_u64(obj, "schemaVersion") != 1 ||
                astu::ipc::require_string(obj, "messageType") !=
                    "AccountRiskSnapshot.v1") {
                return risk;
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
                return risk;
            }

            risk.reconciled = astu::ipc::require_bool(obj, "reconciled");
            risk.risk_state = risk_state_from_string(
                astu::ipc::require_string(obj, "riskState"));
            risk.risk_capital = astu::ipc::require_double(obj, "riskCapital");
            risk.available_balance =
                astu::ipc::require_double(obj, "availableBalance");
            risk.gross_notional =
                astu::ipc::require_double(obj, "grossNotional");
            risk.max_gross_notional =
                astu::ipc::require_double(obj, "maxGrossNotional");
            risk.open_positions = static_cast<std::uint32_t>(
                astu::ipc::require_u64(obj, "openPositions"));
            risk.max_open_positions = static_cast<std::uint32_t>(
                astu::ipc::require_u64(obj, "maxOpenPositions"));

            const auto margin_balance_it = obj.find("marginBalance");
            const auto initial_margin_it = obj.find("initialMargin");
            if ((margin_balance_it == obj.end()) !=
                (initial_margin_it == obj.end())) {
                return astu::core::AccountRiskSnapshot{};
            }
            if (margin_balance_it != obj.end()) {
                risk.margin_balance =
                    astu::ipc::require_double(obj, "marginBalance");
                risk.initial_margin =
                    astu::ipc::require_double(obj, "initialMargin");
                risk.margin_metrics_reconciled =
                    std::isfinite(risk.margin_balance) &&
                    std::isfinite(risk.initial_margin) &&
                    risk.margin_balance >= 0.0 &&
                    risk.initial_margin >= 0.0;
            }

            if (!risk.reconciled) {
                risk.risk_state = astu::core::RiskState::Emergency;
            }
        } catch (const std::exception&) {
            risk.reconciled = false;
            risk.risk_state = astu::core::RiskState::Emergency;
        }
        return risk;
    }

private:
    static astu::core::RiskState risk_state_from_string(
        const std::string& value) {
        using astu::core::RiskState;
        if (value == "NORMAL") return RiskState::Normal;
        if (value == "WARNING") return RiskState::Warning;
        if (value == "RESTRICTED") return RiskState::Restricted;
        if (value == "BLOCK_NEW_ENTRIES") return RiskState::BlockNewEntries;
        if (value == "EMERGENCY") return RiskState::Emergency;
        throw std::invalid_argument("unknown account risk state");
    }

    static std::uint64_t utc_now_ms() {
        const auto now = std::chrono::system_clock::now().time_since_epoch();
        return static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::milliseconds>(now).count());
    }

    static std::string read_all(const std::filesystem::path& path) {
        std::ifstream in(path, std::ios::binary);
        if (!in) {
            throw std::runtime_error("cannot open account risk snapshot");
        }
        std::ostringstream out;
        out << in.rdbuf();
        return out.str();
    }

    std::filesystem::path status_file_;
    std::uint64_t max_snapshot_age_ms_{5'000};
};

}  // namespace astu::account
