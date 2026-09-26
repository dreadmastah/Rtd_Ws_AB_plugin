#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>

#include "astu/account/live_realized_pnl_provider.hpp"
#include "astu/core/contracts.hpp"
#include "astu/execution/simulation_engine.hpp"

#define REQUIRE(...) do { \
    if (!(__VA_ARGS__)) { \
        std::cerr << "REQUIRE_FAILED line=" << __LINE__ \
                  << " expr=" << #__VA_ARGS__ << "\n"; \
        return 99; \
    } \
} while (0)

namespace {

std::uint64_t now_ms() {
    const auto now =
        std::chrono::system_clock::now().time_since_epoch();
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<
            std::chrono::milliseconds>(now).count());
}

std::uint64_t day_start(std::uint64_t unix_ms) {
    constexpr std::uint64_t kDayMs = 86'400'000ULL;
    return (unix_ms / kDayMs) * kDayMs;
}

std::uint64_t week_start(std::uint64_t unix_ms) {
    constexpr std::uint64_t kDayMs = 86'400'000ULL;
    const auto day = unix_ms / kDayMs;
    const auto offset = (day + 3ULL) % 7ULL;
    return (day >= offset ? day - offset : 0ULL) * kDayMs;
}

void write_snapshot(
    const std::filesystem::path& path,
    std::uint64_t generated,
    std::uint64_t day,
    std::uint64_t week,
    bool reconciled = true) {
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    out
        << "{"
        << "\"schemaVersion\":1"
        << ",\"messageType\":\"RealizedPnlSnapshot.v1\""
        << ",\"generatedUnixMs\":" << generated
        << ",\"source\":\"CPP_TEST\""
        << ",\"reconciled\":" << (reconciled ? "true" : "false")
        << ",\"settlementAsset\":\"USDT\""
        << ",\"utcDayStartUnixMs\":" << day
        << ",\"utcWeekStartUnixMs\":" << week
        << ",\"dailyRealizedTradePnl\":-20"
        << ",\"weeklyRealizedTradePnl\":-50"
        << ",\"dailyRealizedTradeLoss\":20"
        << ",\"weeklyRealizedTradeLoss\":50"
        << ",\"dailyFundingFee\":-2"
        << ",\"weeklyFundingFee\":0"
        << ",\"dailyCommission\":-1.5"
        << ",\"weeklyCommission\":-2.5"
        << ",\"dailyNetTradingIncome\":-23.5"
        << ",\"weeklyNetTradingIncome\":-52.5"
        << ",\"recordsInCurrentWeek\":8"
        << ",\"ignoredIncomeRecords\":1"
        << ",\"detail\":\"test\""
        << "}\n";
}

astu::core::AccountRiskSnapshot base_risk() {
    astu::core::AccountRiskSnapshot risk;
    risk.reconciled = true;
    risk.risk_state = astu::core::RiskState::Normal;
    risk.risk_capital = 10'000.0;
    risk.available_balance = 10'000.0;
    risk.max_gross_notional = 100'000.0;
    risk.max_open_positions = 10;
    return risk;
}

astu::core::SignalIntent buy_intent() {
    astu::core::SignalIntent intent;
    intent.symbol = "BTCUSDT";
    intent.action = astu::core::SignalAction::Buy;
    intent.side = astu::core::PositionSide::Long;
    intent.trigger_price = 100.0;
    return intent;
}

}  // namespace

int main() {
    using astu::core::DecisionCode;

    const auto root =
        std::filesystem::temp_directory_path() /
        "astu_realized_pnl_provider_tests";
    std::filesystem::remove_all(root);
    std::filesystem::create_directories(root);
    const auto path = root / "realized.json";

    const auto now = now_ms();
    const auto day = day_start(now);
    const auto week = week_start(now);

    write_snapshot(path, now, day, week);
    {
        astu::account::LiveRealizedPnlProvider provider(path, 5'000);
        const auto pnl = provider();
        REQUIRE(pnl.reconciled);
        REQUIRE(pnl.settlement_asset == "USDT");
        REQUIRE(pnl.daily_realized_trade_pnl == -20.0);
        REQUIRE(pnl.weekly_realized_trade_pnl == -50.0);
        REQUIRE(pnl.daily_realized_trade_loss == 20.0);
        REQUIRE(pnl.weekly_realized_trade_loss == 50.0);
        REQUIRE(pnl.daily_funding_fee == -2.0);
        REQUIRE(pnl.weekly_commission == -2.5);
        REQUIRE(pnl.records_in_current_week == 8);
        REQUIRE(pnl.ignored_income_records == 1);
    }

    write_snapshot(path, now, day - 86'400'000ULL, week);
    {
        astu::account::LiveRealizedPnlProvider provider(path, 5'000);
        REQUIRE(!provider().reconciled);
    }

    write_snapshot(path, now - 10'000, day, week);
    {
        astu::account::LiveRealizedPnlProvider provider(path, 500);
        REQUIRE(!provider().reconciled);
    }

    {
        auto risk = base_risk();
        risk.max_daily_realized_trade_loss = 10.0;
        const auto decision =
            astu::execution::AccountRiskEngine::evaluate(
                buy_intent(),
                risk);
        REQUIRE(decision.code ==
                DecisionCode::AccountNotReconciled);
    }

    {
        auto risk = base_risk();
        risk.realized_pnl_evidence_reconciled = true;
        risk.daily_realized_trade_loss = 20.0;
        risk.max_daily_realized_trade_loss = 20.0;
        const auto decision =
            astu::execution::AccountRiskEngine::evaluate(
                buy_intent(),
                risk);
        REQUIRE(decision.code ==
                DecisionCode::RiskBlocked);
        REQUIRE(decision.reason.find("daily realized-trade") !=
                std::string::npos);
    }

    {
        auto risk = base_risk();
        risk.realized_pnl_evidence_reconciled = true;
        risk.weekly_realized_trade_loss = 50.0;
        risk.max_weekly_realized_trade_loss = 40.0;
        const auto decision =
            astu::execution::AccountRiskEngine::evaluate(
                buy_intent(),
                risk);
        REQUIRE(decision.code ==
                DecisionCode::RiskBlocked);
        REQUIRE(decision.reason.find("weekly realized-trade") !=
                std::string::npos);
    }

    std::filesystem::remove_all(root);
    std::cout << "astu_realized_pnl_provider_tests PASS\n";
    return 0;
}
