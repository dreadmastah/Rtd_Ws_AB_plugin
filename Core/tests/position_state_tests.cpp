#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>

#include "astu/account/live_position_provider.hpp"
#include "astu/core/contracts.hpp"
#include "astu/execution/simulation_engine.hpp"

#define REQUIRE(...) do { \
    if (!(__VA_ARGS__)) { \
        std::cerr << "REQUIRE_FAILED line=" << __LINE__ << " expr=" << #__VA_ARGS__ << "\n"; \
        return 99; \
    } \
} while (0)

namespace {

bool near(double a, double b, double eps = 1e-9) {
    return std::fabs(a - b) <= eps;
}

astu::core::SignalIntent intent(
    astu::core::SignalAction action,
    astu::core::PositionSide side,
    double trigger_price = 1000.0) {
    astu::core::SignalIntent x;
    x.signal_id = "POS-1";
    x.analysis_run_id = "AA-POS-1";
    x.strategy_id = "position-state-test";
    x.strategy_version = "1";
    x.universe_id = "U";
    x.universe_version = 1;
    x.symbol = "BTCUSDT";
    x.action = action;
    x.side = side;
    x.source_periodicity = "M1";
    x.source_bar_time_utc_ms = 1'000;
    x.signal_time_utc_ms = 1'100;
    x.trigger_price = trigger_price;
    x.valid_from_utc_ms = 1'000;
    x.expires_utc_ms = 5'000;
    x.quantity_model = "DETERMINISTIC_SIM_V1";
    x.data_generation = 9;
    return x;
}

astu::core::DataStatus ready_data() {
    astu::core::DataStatus d;
    d.symbol = "BTCUSDT";
    d.live = true;
    d.fresh = true;
    d.cache_ready = true;
    d.identity_ready = true;
    d.universe_id = "U";
    d.universe_version = 1;
    d.data_generation = 9;
    return d;
}

astu::core::AccountRiskSnapshot ready_risk() {
    astu::core::AccountRiskSnapshot r;
    r.reconciled = true;
    r.risk_state = astu::core::RiskState::Normal;
    r.risk_capital = 10'000.0;
    r.available_balance = 9'000.0;
    r.gross_notional = 1'000.0;
    r.max_gross_notional = 100'000.0;
    r.open_positions = 1;
    r.max_open_positions = 10;
    return r;
}

astu::core::InstrumentConstraints rules() {
    astu::core::InstrumentConstraints x;
    x.ready = true;
    x.source = "TEST";
    x.symbol = "BTCUSDT";
    x.price_tick = 0.1;
    x.quantity_step = 0.001;
    x.min_quantity = 0.001;
    x.max_quantity = 1000.0;
    x.min_notional = 5.0;
    x.max_notional = 0.0;
    return x;
}

astu::core::PositionSnapshot long_position(double quantity = 0.010) {
    astu::core::PositionSnapshot p;
    p.reconciled = true;
    p.source = "TEST";
    p.symbol = "BTCUSDT";
    p.mode = astu::core::PositionMode::Long;
    p.quantity = quantity;
    p.notional = quantity * 1000.0;
    p.detail = "test long";
    return p;
}

}  // namespace

int main() {
    using astu::core::DecisionCode;
    using astu::core::PositionMode;
    using astu::core::PositionSide;
    using astu::core::SignalAction;

    {
        const auto result = astu::execution::SimulationEngine::run_with_instrument(
            intent(SignalAction::ScaleIn, PositionSide::Long),
            ready_data(), ready_risk(), rules(), 2'000);
        REQUIRE(result.code == DecisionCode::PositionUnavailable);
        REQUIRE(!result.accepted_for_simulation);
    }

    {
        const auto result =
            astu::execution::SimulationEngine::run_with_position_and_instrument(
                intent(SignalAction::ScaleIn, PositionSide::Long),
                ready_data(), ready_risk(), long_position(), rules(), 2'000);
        REQUIRE(result.code == DecisionCode::OrderRoutingDisabled);
        REQUIRE(result.accepted_for_simulation);
    }

    {
        auto flat = long_position();
        flat.mode = PositionMode::Flat;
        flat.quantity = 0.0;
        flat.notional = 0.0;
        const auto result =
            astu::execution::SimulationEngine::run_with_position_and_instrument(
                intent(SignalAction::ScaleIn, PositionSide::Long),
                ready_data(), ready_risk(), flat, rules(), 2'000);
        REQUIRE(result.code == DecisionCode::PositionConflict);
    }

    {
        const auto result =
            astu::execution::SimulationEngine::run_with_position_and_instrument(
                intent(SignalAction::ScaleIn, PositionSide::Short),
                ready_data(), ready_risk(), long_position(), rules(), 2'000);
        REQUIRE(result.code == DecisionCode::PositionConflict);
    }

    {
        auto hedged = long_position();
        hedged.mode = PositionMode::Hedged;
        hedged.quantity = 0.020;
        const auto result =
            astu::execution::SimulationEngine::run_with_position_and_instrument(
                intent(SignalAction::ScaleOut, PositionSide::Long),
                ready_data(), ready_risk(), hedged, rules(), 2'000);
        REQUIRE(result.code == DecisionCode::PositionConflict);
    }

    {
        const auto result =
            astu::execution::SimulationEngine::run_with_position_and_instrument(
                intent(SignalAction::ScaleOut, PositionSide::Long),
                ready_data(), ready_risk(), long_position(0.005), rules(), 2'000);
        REQUIRE(result.code == DecisionCode::OrderRoutingDisabled);
        REQUIRE(near(result.simulated_quantity, 0.005));
        REQUIRE(near(result.simulated_notional, 5.0));
    }

    {
        const auto now_ms = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now().time_since_epoch()).count());
        const auto dir = std::filesystem::temp_directory_path() /
            "astu_position_provider_test";
        std::filesystem::remove_all(dir);
        std::filesystem::create_directories(dir);

        std::ofstream out(dir / "BTCUSDT.json", std::ios::binary | std::ios::trunc);
        out
            << "{"
            << "\"schemaVersion\":1,"
            << "\"messageType\":\"PositionSnapshot.v1\","
            << "\"generatedUnixMs\":" << now_ms << ","
            << "\"source\":\"TEST\","
            << "\"reconciled\":true,"
            << "\"symbol\":\"BTCUSDT\","
            << "\"mode\":\"LONG\","
            << "\"quantity\":0.01,"
            << "\"notional\":10,"
            << "\"detail\":\"provider fixture\""
            << "}";
        out.close();

        astu::account::LivePositionProvider provider(dir, 5'000);
        const auto loaded = provider(intent(SignalAction::ScaleIn, PositionSide::Long));
        REQUIRE(loaded.reconciled);
        REQUIRE(loaded.mode == PositionMode::Long);
        REQUIRE(near(loaded.quantity, 0.01));

        std::ofstream stale(dir / "BTCUSDT.json", std::ios::binary | std::ios::trunc);
        stale
            << "{"
            << "\"schemaVersion\":1,"
            << "\"messageType\":\"PositionSnapshot.v1\","
            << "\"generatedUnixMs\":" << (now_ms - 60'000) << ","
            << "\"source\":\"TEST\","
            << "\"reconciled\":true,"
            << "\"symbol\":\"BTCUSDT\","
            << "\"mode\":\"LONG\","
            << "\"quantity\":0.01,"
            << "\"notional\":10,"
            << "\"detail\":\"stale provider fixture\""
            << "}";
        stale.close();

        const auto stale_loaded =
            provider(intent(SignalAction::ScaleIn, PositionSide::Long));
        REQUIRE(!stale_loaded.reconciled);
        REQUIRE(stale_loaded.mode == PositionMode::Unknown);
        REQUIRE(stale_loaded.detail == "position snapshot stale");

        std::filesystem::remove_all(dir);
    }

    std::cout << "astu_position_state_tests PASS\n";
    return 0;
}
