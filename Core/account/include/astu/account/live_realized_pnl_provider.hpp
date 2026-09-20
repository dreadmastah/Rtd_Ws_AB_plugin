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

class LiveRealizedPnlProvider {
public:
    explicit LiveRealizedPnlProvider(
        std::filesystem::path status_file,
        std::uint64_t max_snapshot_age_ms = 60'000)
        : status_file_(std::move(status_file)),
          max_snapshot_age_ms_(max_snapshot_age_ms) {}

    astu::core::RealizedPnlSnapshot operator()() const {
        astu::core::RealizedPnlSnapshot out;
        try {
            const auto json = read_all(status_file_);
            const auto obj = astu::ipc::FlatJsonParser(json).parse();

            if (astu::ipc::require_u64(obj, "schemaVersion") != 1 ||
                astu::ipc::require_string(obj, "messageType") !=
                    "RealizedPnlSnapshot.v1") {
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
                now_ms - generated_ms > max_snapshot_age_ms_;
            if (too_far_future || too_old) {
                return out;
            }

            const auto day_start =
                astu::ipc::require_u64(
                    obj,
                    "utcDayStartUnixMs");
            const auto week_start =
                astu::ipc::require_u64(
                    obj,
                    "utcWeekStartUnixMs");
            if (day_start != utc_day_start_ms(now_ms) ||
                week_start != utc_week_start_ms(now_ms)) {
                return out;
            }

            out.reconciled =
                astu::ipc::require_bool(obj, "reconciled");
            out.source =
                astu::ipc::require_string(obj, "source");
            out.utc_day_start_unix_ms = day_start;
            out.utc_week_start_unix_ms = week_start;
            out.daily_realized_trade_pnl =
                astu::ipc::require_double(
                    obj,
                    "dailyRealizedTradePnl");
            out.weekly_realized_trade_pnl =
                astu::ipc::require_double(
                    obj,
                    "weeklyRealizedTradePnl");
            out.daily_realized_trade_loss =
                astu::ipc::require_double(
                    obj,
                    "dailyRealizedTradeLoss");
            out.weekly_realized_trade_loss =
                astu::ipc::require_double(
                    obj,
                    "weeklyRealizedTradeLoss");
            out.daily_funding_fee =
                astu::ipc::require_double(
                    obj,
                    "dailyFundingFee");
            out.weekly_funding_fee =
                astu::ipc::require_double(
                    obj,
                    "weeklyFundingFee");
            out.daily_commission =
                astu::ipc::require_double(
                    obj,
                    "dailyCommission");
            out.weekly_commission =
                astu::ipc::require_double(
                    obj,
                    "weeklyCommission");
            out.daily_net_trading_income =
                astu::ipc::require_double(
                    obj,
                    "dailyNetTradingIncome");
            out.weekly_net_trading_income =
                astu::ipc::require_double(
                    obj,
                    "weeklyNetTradingIncome");
            out.records_in_current_week =
                astu::ipc::require_u64(
                    obj,
                    "recordsInCurrentWeek");
            out.ignored_income_records =
                astu::ipc::require_u64(
                    obj,
                    "ignoredIncomeRecords");
            out.detail =
                astu::ipc::require_string(obj, "detail");

            const double finite_values[] = {
                out.daily_realized_trade_pnl,
                out.weekly_realized_trade_pnl,
                out.daily_realized_trade_loss,
                out.weekly_realized_trade_loss,
                out.daily_funding_fee,
                out.weekly_funding_fee,
                out.daily_commission,
                out.weekly_commission,
                out.daily_net_trading_income,
                out.weekly_net_trading_income,
            };
            for (const double value : finite_values) {
                if (!std::isfinite(value)) {
                    return astu::core::RealizedPnlSnapshot{};
                }
            }
            if (out.daily_realized_trade_loss < 0.0 ||
                out.weekly_realized_trade_loss < 0.0) {
                return astu::core::RealizedPnlSnapshot{};
            }
            if (!out.reconciled) {
                return astu::core::RealizedPnlSnapshot{};
            }
        } catch (const std::exception&) {
            return astu::core::RealizedPnlSnapshot{};
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

    static std::uint64_t utc_day_start_ms(
        std::uint64_t unix_ms) noexcept {
        constexpr std::uint64_t kDayMs = 86'400'000ULL;
        return (unix_ms / kDayMs) * kDayMs;
    }

    static std::uint64_t utc_week_start_ms(
        std::uint64_t unix_ms) noexcept {
        constexpr std::uint64_t kDayMs = 86'400'000ULL;
        const auto day_index = unix_ms / kDayMs;
        const auto days_since_monday =
            (day_index + 3ULL) % 7ULL;
        const auto week_start_day =
            day_index >= days_since_monday
                ? day_index - days_since_monday
                : 0ULL;
        return week_start_day * kDayMs;
    }

    static std::string read_all(
        const std::filesystem::path& path) {
        std::ifstream in(path, std::ios::binary);
        if (!in) {
            throw std::runtime_error(
                "cannot open realized PnL snapshot");
        }
        std::ostringstream out;
        out << in.rdbuf();
        return out.str();
    }

    std::filesystem::path status_file_;
    std::uint64_t max_snapshot_age_ms_{60'000};
};

}  // namespace astu::account
