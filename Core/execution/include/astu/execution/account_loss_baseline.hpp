#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

#include "astu/core/contracts.hpp"
#include "astu/ipc/flat_json.hpp"

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace astu::execution {

struct AccountLossBaselineMetrics {
    bool ready{false};
    std::uint64_t utc_day_index{0};
    std::uint64_t utc_week_start_day_index{0};
    double daily_start_risk_capital{0.0};
    double weekly_start_risk_capital{0.0};
    double daily_start_margin_balance{0.0};
    double weekly_start_margin_balance{0.0};
    double high_water_margin_balance{0.0};
    double daily_risk_capital_loss{0.0};
    double weekly_risk_capital_loss{0.0};
    double daily_total_pnl_loss{0.0};
    double weekly_total_pnl_loss{0.0};
    double account_drawdown{0.0};
    std::uint64_t last_observed_unix_ms{0};
};

class AccountLossBaselineTracker {
public:
    explicit AccountLossBaselineTracker(std::filesystem::path path)
        : path_(std::move(path)) {
        load_if_present();
    }

    AccountLossBaselineMetrics evaluate(
        const astu::core::AccountRiskSnapshot& risk,
        std::uint64_t now_ms,
        bool require_margin_metrics) {
        std::lock_guard<std::mutex> lock(mu_);

        if (!risk.reconciled ||
            !std::isfinite(risk.risk_capital) ||
            risk.risk_capital < 0.0) {
            return {};
        }
        if (require_margin_metrics &&
            (!risk.margin_metrics_reconciled ||
             !std::isfinite(risk.margin_balance) ||
             risk.margin_balance < 0.0)) {
            return {};
        }
        if (loaded_ && now_ms < state_.last_observed_unix_ms) {
            return {};
        }

        const auto day = utc_day_index(now_ms);
        const auto week = utc_week_start_day_index(day);
        const bool margin_ready =
            risk.margin_metrics_reconciled &&
            std::isfinite(risk.margin_balance) &&
            risk.margin_balance >= 0.0;

        bool changed = false;
        if (!loaded_) {
            state_.utc_day_index = day;
            state_.utc_week_start_day_index = week;
            state_.daily_start_risk_capital = risk.risk_capital;
            state_.weekly_start_risk_capital = risk.risk_capital;
            if (margin_ready) {
                state_.daily_start_margin_balance = risk.margin_balance;
                state_.weekly_start_margin_balance = risk.margin_balance;
                state_.high_water_margin_balance = risk.margin_balance;
            }
            state_.last_observed_unix_ms = now_ms;
            loaded_ = true;
            changed = true;
        } else {
            if (state_.utc_day_index != day) {
                state_.utc_day_index = day;
                state_.daily_start_risk_capital = risk.risk_capital;
                state_.daily_start_margin_balance =
                    margin_ready ? risk.margin_balance : 0.0;
                changed = true;
            }
            if (state_.utc_week_start_day_index != week) {
                state_.utc_week_start_day_index = week;
                state_.weekly_start_risk_capital = risk.risk_capital;
                state_.weekly_start_margin_balance =
                    margin_ready ? risk.margin_balance : 0.0;
                changed = true;
            }
            if (margin_ready &&
                (state_.high_water_margin_balance <= 0.0 ||
                 risk.margin_balance > state_.high_water_margin_balance)) {
                state_.high_water_margin_balance = risk.margin_balance;
                changed = true;
            }
            if (state_.last_observed_unix_ms != now_ms) {
                state_.last_observed_unix_ms = now_ms;
                changed = true;
            }
        }

        if (margin_ready) {
            if (state_.daily_start_margin_balance <= 0.0) {
                state_.daily_start_margin_balance = risk.margin_balance;
                changed = true;
            }
            if (state_.weekly_start_margin_balance <= 0.0) {
                state_.weekly_start_margin_balance = risk.margin_balance;
                changed = true;
            }
            if (state_.high_water_margin_balance <= 0.0) {
                state_.high_water_margin_balance = risk.margin_balance;
                changed = true;
            }
        }

        if (changed) {
            persist_unlocked();
        }

        AccountLossBaselineMetrics out = state_;
        out.ready = true;
        out.daily_risk_capital_loss = std::max(
            0.0,
            out.daily_start_risk_capital - risk.risk_capital);
        out.weekly_risk_capital_loss = std::max(
            0.0,
            out.weekly_start_risk_capital - risk.risk_capital);
        if (margin_ready) {
            out.daily_total_pnl_loss = std::max(
                0.0,
                out.daily_start_margin_balance - risk.margin_balance);
            out.weekly_total_pnl_loss = std::max(
                0.0,
                out.weekly_start_margin_balance - risk.margin_balance);
            out.account_drawdown = std::max(
                0.0,
                out.high_water_margin_balance - risk.margin_balance);
        }
        last_metrics_ = out;
        return out;
    }

    AccountLossBaselineMetrics snapshot() const {
        std::lock_guard<std::mutex> lock(mu_);
        return last_metrics_;
    }

    const std::filesystem::path& path() const noexcept {
        return path_;
    }

    static std::uint64_t utc_day_index(std::uint64_t unix_ms) noexcept {
        constexpr std::uint64_t kDayMs = 86'400'000ULL;
        return unix_ms / kDayMs;
    }

    static std::uint64_t utc_week_start_day_index(
        std::uint64_t day_index) noexcept {
        // Unix epoch day 0 was Thursday. Monday-aligned week start:
        // Thursday => offset 3 from Monday.
        const auto days_since_monday =
            (day_index + 3ULL) % 7ULL;
        return day_index - days_since_monday;
    }

private:
    void load_if_present() {
        std::lock_guard<std::mutex> lock(mu_);
        if (!std::filesystem::exists(path_)) {
            return;
        }

        std::ifstream in(path_, std::ios::binary);
        if (!in) {
            throw std::runtime_error(
                "cannot open account loss baseline state");
        }
        std::ostringstream buffer;
        buffer << in.rdbuf();
        const auto obj =
            astu::ipc::FlatJsonParser(buffer.str()).parse();

        if (astu::ipc::require_u64(obj, "schemaVersion") != 1 ||
            astu::ipc::require_string(obj, "messageType") !=
                "AccountLossBaselineState.v1") {
            throw std::runtime_error(
                "account loss baseline schema mismatch");
        }

        state_.utc_day_index =
            astu::ipc::require_u64(obj, "utcDayIndex");
        state_.utc_week_start_day_index =
            astu::ipc::require_u64(obj, "utcWeekStartDayIndex");
        state_.daily_start_risk_capital =
            astu::ipc::require_double(
                obj,
                "dailyStartRiskCapital");
        state_.weekly_start_risk_capital =
            astu::ipc::require_double(
                obj,
                "weeklyStartRiskCapital");
        state_.daily_start_margin_balance =
            astu::ipc::require_double(
                obj,
                "dailyStartMarginBalance");
        state_.weekly_start_margin_balance =
            astu::ipc::require_double(
                obj,
                "weeklyStartMarginBalance");
        state_.high_water_margin_balance =
            astu::ipc::require_double(
                obj,
                "highWaterMarginBalance");
        state_.last_observed_unix_ms =
            astu::ipc::require_u64(
                obj,
                "lastObservedUnixMs");

        const double values[] = {
            state_.daily_start_risk_capital,
            state_.weekly_start_risk_capital,
            state_.daily_start_margin_balance,
            state_.weekly_start_margin_balance,
            state_.high_water_margin_balance,
        };
        for (double value : values) {
            if (!std::isfinite(value) || value < 0.0) {
                throw std::runtime_error(
                    "account loss baseline contains invalid metric");
            }
        }
        loaded_ = true;
    }

    void persist_unlocked() const {
        if (!path_.parent_path().empty()) {
            std::filesystem::create_directories(
                path_.parent_path());
        }

        std::ostringstream out;
        out << std::setprecision(17);
        out
            << "{"
            << "\"schemaVersion\":1"
            << ",\"messageType\":\"AccountLossBaselineState.v1\""
            << ",\"utcDayIndex\":" << state_.utc_day_index
            << ",\"utcWeekStartDayIndex\":"
            << state_.utc_week_start_day_index
            << ",\"dailyStartRiskCapital\":"
            << state_.daily_start_risk_capital
            << ",\"weeklyStartRiskCapital\":"
            << state_.weekly_start_risk_capital
            << ",\"dailyStartMarginBalance\":"
            << state_.daily_start_margin_balance
            << ",\"weeklyStartMarginBalance\":"
            << state_.weekly_start_margin_balance
            << ",\"highWaterMarginBalance\":"
            << state_.high_water_margin_balance
            << ",\"lastObservedUnixMs\":"
            << state_.last_observed_unix_ms
            << "}\n";

        const auto tmp = path_.string() + ".tmp";
        {
            std::ofstream file(
                tmp,
                std::ios::binary | std::ios::trunc);
            if (!file) {
                throw std::runtime_error(
                    "cannot open account loss baseline temp file");
            }
            const auto text = out.str();
            file.write(
                text.data(),
                static_cast<std::streamsize>(text.size()));
            file.flush();
            if (!file) {
                throw std::runtime_error(
                    "cannot write account loss baseline temp file");
            }
        }

#ifdef _WIN32
        if (!MoveFileExA(
                tmp.c_str(),
                path_.string().c_str(),
                MOVEFILE_REPLACE_EXISTING |
                    MOVEFILE_WRITE_THROUGH)) {
            std::filesystem::remove(tmp);
            throw std::runtime_error(
                "cannot publish account loss baseline error=" +
                std::to_string(GetLastError()));
        }
#else
        std::filesystem::rename(tmp, path_);
#endif
    }

    std::filesystem::path path_;
    mutable std::mutex mu_;
    AccountLossBaselineMetrics state_;
    AccountLossBaselineMetrics last_metrics_;
    bool loaded_{false};
};

}  // namespace astu::execution
