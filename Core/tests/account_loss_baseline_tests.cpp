#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <string>

#include "astu/core/contracts.hpp"
#include "astu/execution/account_loss_baseline.hpp"
#include "astu/execution/simulation_engine.hpp"

#define REQUIRE(...) do { \
    if (!(__VA_ARGS__)) { \
        std::cerr << "REQUIRE_FAILED line=" << __LINE__ \
                  << " expr=" << #__VA_ARGS__ << "\n"; \
        return 99; \
    } \
} while (0)

namespace {

astu::core::AccountRiskSnapshot risk_snapshot(
    double risk_capital,
    double margin_balance,
    bool margin_ready = true) {
    astu::core::AccountRiskSnapshot risk;
    risk.reconciled = true;
    risk.risk_state = astu::core::RiskState::Normal;
    risk.risk_capital = risk_capital;
    risk.available_balance = risk_capital;
    risk.gross_notional = 0.0;
    risk.max_gross_notional = 100'000.0;
    risk.open_positions = 0;
    risk.max_open_positions = 10;
    risk.margin_metrics_reconciled = margin_ready;
    risk.margin_balance = margin_balance;
    risk.initial_margin = 0.0;
    return risk;
}

astu::core::SignalIntent exposure_intent() {
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
    using astu::execution::AccountLossBaselineTracker;

    const auto root =
        std::filesystem::temp_directory_path() /
        "astu_account_loss_baseline_tests";
    std::filesystem::remove_all(root);
    std::filesystem::create_directories(root);
    const auto state_path = root / "loss_baseline.v1.json";

    constexpr std::uint64_t day_ms = 86'400'000ULL;
    // 2026-era synthetic timestamp, safely after Unix epoch.
    const std::uint64_t t0 = 1'800'000'000'000ULL;

    {
        AccountLossBaselineTracker tracker(state_path);

        auto m = tracker.evaluate(
            risk_snapshot(1'000.0, 1'000.0),
            t0,
            true);
        REQUIRE(m.ready);
        REQUIRE(std::fabs(m.daily_start_risk_capital - 1'000.0) < 1e-12);
        REQUIRE(std::fabs(m.weekly_start_risk_capital - 1'000.0) < 1e-12);
        REQUIRE(std::fabs(m.high_water_margin_balance - 1'000.0) < 1e-12);
        REQUIRE(std::fabs(m.daily_risk_capital_loss) < 1e-12);
        REQUIRE(std::fabs(m.daily_total_pnl_loss) < 1e-12);
        REQUIRE(std::fabs(m.account_drawdown) < 1e-12);

        m = tracker.evaluate(
            risk_snapshot(950.0, 970.0),
            t0 + 1'000,
            true);
        REQUIRE(m.ready);
        REQUIRE(std::fabs(m.daily_risk_capital_loss - 50.0) < 1e-12);
        REQUIRE(std::fabs(m.weekly_risk_capital_loss - 50.0) < 1e-12);
        REQUIRE(std::fabs(m.daily_total_pnl_loss - 30.0) < 1e-12);
        REQUIRE(std::fabs(m.weekly_total_pnl_loss - 30.0) < 1e-12);
        REQUIRE(std::fabs(m.account_drawdown - 30.0) < 1e-12);

        m = tracker.evaluate(
            risk_snapshot(1'050.0, 1'100.0),
            t0 + 2'000,
            true);
        REQUIRE(m.ready);
        REQUIRE(std::fabs(m.high_water_margin_balance - 1'100.0) < 1e-12);
        REQUIRE(std::fabs(m.account_drawdown) < 1e-12);

        m = tracker.evaluate(
            risk_snapshot(980.0, 1'000.0),
            t0 + 3'000,
            true);
        REQUIRE(std::fabs(m.daily_risk_capital_loss - 20.0) < 1e-12);
        REQUIRE(std::fabs(m.account_drawdown - 100.0) < 1e-12);
    }

    {
        AccountLossBaselineTracker replayed(state_path);
        auto m = replayed.evaluate(
            risk_snapshot(980.0, 1'000.0),
            t0 + 4'000,
            true);
        REQUIRE(m.ready);
        REQUIRE(std::fabs(m.daily_start_risk_capital - 1'000.0) < 1e-12);
        REQUIRE(std::fabs(m.weekly_start_risk_capital - 1'000.0) < 1e-12);
        REQUIRE(std::fabs(m.high_water_margin_balance - 1'100.0) < 1e-12);
        REQUIRE(std::fabs(m.account_drawdown - 100.0) < 1e-12);

        const auto next_day =
            (AccountLossBaselineTracker::utc_day_index(t0) + 1ULL) *
            day_ms + 1'000ULL;
        m = replayed.evaluate(
            risk_snapshot(900.0, 900.0),
            next_day,
            true);
        REQUIRE(m.ready);
        REQUIRE(std::fabs(m.daily_start_risk_capital - 900.0) < 1e-12);
        REQUIRE(std::fabs(m.daily_risk_capital_loss) < 1e-12);
        REQUIRE(std::fabs(m.weekly_start_risk_capital - 1'000.0) < 1e-12 ||
                std::fabs(m.weekly_start_risk_capital - 900.0) < 1e-12);
        REQUIRE(std::fabs(m.high_water_margin_balance - 1'100.0) < 1e-12);
        REQUIRE(std::fabs(m.account_drawdown - 200.0) < 1e-12);

        const auto rollback = replayed.evaluate(
            risk_snapshot(900.0, 900.0),
            t0,
            true);
        REQUIRE(!rollback.ready);
    }

    {
        const auto risk_only_path = root / "risk_only.v1.json";
        AccountLossBaselineTracker tracker(risk_only_path);
        const auto m = tracker.evaluate(
            risk_snapshot(1'000.0, 0.0, false),
            t0,
            false);
        REQUIRE(m.ready);
        REQUIRE(std::fabs(m.daily_start_risk_capital - 1'000.0) < 1e-12);
        REQUIRE(std::fabs(m.high_water_margin_balance) < 1e-12);

        const auto unavailable = tracker.evaluate(
            risk_snapshot(1'000.0, 0.0, false),
            t0 + 1'000,
            true);
        REQUIRE(!unavailable.ready);
    }

    {
        auto risk = risk_snapshot(900.0, 900.0);
        risk.account_loss_metrics_reconciled = true;
        risk.daily_risk_capital_loss = 60.0;
        risk.max_daily_risk_capital_loss = 50.0;
        const auto decision =
            astu::execution::AccountRiskEngine::evaluate(
                exposure_intent(),
                risk);
        REQUIRE(decision.decision_code == DecisionCode::RiskBlocked);
        REQUIRE(decision.reason.find("daily risk-capital") !=
                std::string::npos);
    }

    {
        auto risk = risk_snapshot(900.0, 900.0);
        risk.account_loss_metrics_reconciled = true;
        risk.weekly_total_pnl_loss = 101.0;
        risk.max_weekly_total_pnl_loss = 100.0;
        const auto decision =
            astu::execution::AccountRiskEngine::evaluate(
                exposure_intent(),
                risk);
        REQUIRE(decision.decision_code == DecisionCode::RiskBlocked);
        REQUIRE(decision.reason.find("weekly total-PnL") !=
                std::string::npos);
    }

    {
        auto risk = risk_snapshot(900.0, 900.0);
        risk.account_loss_metrics_reconciled = true;
        risk.account_drawdown = 150.0;
        risk.max_account_drawdown = 100.0;
        const auto decision =
            astu::execution::AccountRiskEngine::evaluate(
                exposure_intent(),
                risk);
        REQUIRE(decision.decision_code == DecisionCode::RiskBlocked);
        REQUIRE(decision.reason.find("drawdown") !=
                std::string::npos);
    }

    {
        auto risk = risk_snapshot(900.0, 900.0);
        risk.max_daily_risk_capital_loss = 50.0;
        const auto decision =
            astu::execution::AccountRiskEngine::evaluate(
                exposure_intent(),
                risk);
        REQUIRE(decision.decision_code ==
                DecisionCode::AccountNotReconciled);
    }

    {
        const auto corrupt = root / "corrupt.v1.json";
        std::ofstream out(corrupt);
        out << "{\"schemaVersion\":1,\"messageType\":"
               "\"AccountLossBaselineState.v1\"}\n";
        out.close();
        bool failed = false;
        try {
            AccountLossBaselineTracker tracker(corrupt);
            (void)tracker;
        } catch (const std::exception&) {
            failed = true;
        }
        REQUIRE(failed);
    }

    std::filesystem::remove_all(root);
    std::cout << "astu_account_loss_baseline_tests PASS\n";
    return 0;
}
