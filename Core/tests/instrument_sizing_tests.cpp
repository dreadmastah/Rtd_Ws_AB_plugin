#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>

#include "astu/core/contracts.hpp"
#include "astu/execution/simulation_engine.hpp"
#include "astu/instrument/live_instrument_provider.hpp"
#include "astu/trade/signal_intent_builder.hpp"

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

astu::core::SignalIntent intent_at(double trigger_price) {
    astu::core::SignalIntent x;
    x.signal_id = "SIZE-1";
    x.analysis_run_id = "AA-SIZE-1";
    x.strategy_id = "sizing-test";
    x.strategy_version = "1";
    x.universe_id = "U";
    x.universe_version = 1;
    x.symbol = "BTCUSDT";
    x.action = astu::core::SignalAction::Buy;
    x.side = astu::core::PositionSide::Long;
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
    x.source = "TEST_FIXTURE";
    x.symbol = "BTCUSDT";
    x.price_tick = 0.10;
    x.quantity_step = 0.001;
    x.min_quantity = 0.001;
    x.max_quantity = 1'000.0;
    x.min_notional = 5.0;
    x.max_notional = 0.0;
    x.detail = "synthetic deterministic filter fixture";
    return x;
}

}  // namespace

int main() {
    using astu::core::DecisionCode;

    {
        const auto result = astu::execution::SimulationEngine::run_with_instrument(
            intent_at(333.0), ready_data(), ready_risk(), rules(), 2'000);
        REQUIRE(result.code == DecisionCode::OrderRoutingDisabled);
        REQUIRE(result.accepted_for_simulation);
        REQUIRE(near(result.simulated_quantity, 0.030));
        REQUIRE(near(result.simulated_notional, 9.99));
    }

    {
        auto strict = rules();
        strict.min_notional = 20.0;
        const auto result = astu::execution::SimulationEngine::run_with_instrument(
            intent_at(100.0), ready_data(), ready_risk(), strict, 2'000);
        REQUIRE(result.code == DecisionCode::FilterRejected);
        REQUIRE(!result.accepted_for_simulation);
        REQUIRE(near(result.simulated_quantity, 0.100));
        REQUIRE(near(result.simulated_notional, 10.0));
    }

    {
        auto strict = rules();
        strict.min_quantity = 0.200;
        const auto result = astu::execution::SimulationEngine::run_with_instrument(
            intent_at(100.0), ready_data(), ready_risk(), strict, 2'000);
        REQUIRE(result.code == DecisionCode::FilterRejected);
        REQUIRE(!result.accepted_for_simulation);
    }

    {
        auto risk = ready_risk();
        risk.gross_notional = 1'000.0;
        risk.max_gross_notional = 1'005.0;
        const auto result = astu::execution::SimulationEngine::run_with_instrument(
            intent_at(100.0), ready_data(), risk, rules(), 2'000);
        REQUIRE(result.code == DecisionCode::OrderRoutingDisabled);
        REQUIRE(near(result.simulated_quantity, 0.050));
        REQUIRE(near(result.simulated_notional, 5.0));
    }

    {
        auto demo_intent = intent_at(80'000.0);
        auto demo_risk = ready_risk();
        demo_risk.risk_capital = 5'000.0;
        demo_risk.gross_notional = 0.0;
        demo_risk.max_gross_notional = 100.0;
        demo_risk.symbol_exposure_reconciled = true;
        demo_risk.symbol_notional = 0.0;
        demo_risk.max_symbol_notional = 100.0;

        auto btc_demo = rules();
        btc_demo.quantity_step = 0.0001;
        btc_demo.min_quantity = 0.0001;
        btc_demo.min_notional = 50.0;

        const auto default_result =
            astu::execution::SimulationEngine::run_with_instrument(
                demo_intent, ready_data(), demo_risk, btc_demo, 2'000);
        REQUIRE(default_result.code == DecisionCode::SizingRejected);
        REQUIRE(!default_result.accepted_for_simulation);

        demo_intent.quantity_model = "DEMO_ACCEPTANCE_FIXED_60_USDT";
        const auto acceptance_result =
            astu::execution::SimulationEngine::run_with_instrument(
                demo_intent, ready_data(), demo_risk, btc_demo, 2'000);
        REQUIRE(acceptance_result.code == DecisionCode::OrderRoutingDisabled);
        REQUIRE(acceptance_result.accepted_for_simulation);
        REQUIRE(near(acceptance_result.simulated_quantity, 0.0007));
        REQUIRE(near(acceptance_result.simulated_notional, 56.0));
        REQUIRE(acceptance_result.simulated_notional <= 100.0);
    }

    {
        auto malformed = rules();
        malformed.quantity_step = 0.0;
        const auto result = astu::execution::SimulationEngine::run_with_instrument(
            intent_at(100.0), ready_data(), ready_risk(), malformed, 2'000);
        REQUIRE(result.code == DecisionCode::InstrumentUnavailable);
        REQUIRE(!result.accepted_for_simulation);
    }

    {
        const auto now_ms = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now().time_since_epoch()).count());
        const auto dir = std::filesystem::temp_directory_path() /
            "astu_instrument_constraints_test";
        std::filesystem::remove_all(dir);
        std::filesystem::create_directories(dir);

        std::ofstream out(dir / "BTCUSDT.json", std::ios::binary | std::ios::trunc);
        out
            << "{"
            << "\"schemaVersion\":1,"
            << "\"messageType\":\"InstrumentConstraints.v1\","
            << "\"generatedUnixMs\":" << now_ms << ","
            << "\"ready\":true,"
            << "\"source\":\"TEST_FIXTURE\","
            << "\"symbol\":\"BTCUSDT\","
            << "\"priceTick\":0.1,"
            << "\"quantityStep\":0.001,"
            << "\"minQuantity\":0.001,"
            << "\"maxQuantity\":1000,"
            << "\"minNotional\":5,"
            << "\"maxNotional\":0,"
            << "\"detail\":\"provider fixture\""
            << "}";
        out.close();

        astu::instrument::LiveInstrumentProvider provider(dir, 5'000);
        const auto loaded = provider(intent_at(100.0));
        REQUIRE(loaded.ready);
        REQUIRE(loaded.symbol == "BTCUSDT");
        REQUIRE(near(loaded.price_tick, 0.1));
        REQUIRE(near(loaded.quantity_step, 0.001));
        REQUIRE(near(loaded.min_notional, 5.0));

        const auto result = astu::execution::SimulationEngine::run_with_instrument(
            intent_at(100.0), ready_data(), ready_risk(), loaded, 2'000);
        REQUIRE(result.code == DecisionCode::OrderRoutingDisabled);
        REQUIRE(near(result.simulated_quantity, 0.100));
        REQUIRE(near(result.simulated_notional, 10.0));

        std::ofstream changed(
            dir / "BTCUSDT.json",
            std::ios::binary | std::ios::trunc);
        changed
            << "{"
            << "\"schemaVersion\":1,"
            << "\"messageType\":\"InstrumentConstraints.v1\","
            << "\"generatedUnixMs\":" << now_ms << ","
            << "\"ready\":true,"
            << "\"source\":\"TEST_FIXTURE_CHANGED\","
            << "\"symbol\":\"BTCUSDT\","
            << "\"priceTick\":0.1,"
            << "\"quantityStep\":0.01,"
            << "\"minQuantity\":0.01,"
            << "\"maxQuantity\":1000,"
            << "\"minNotional\":20,"
            << "\"maxNotional\":0,"
            << "\"detail\":\"changed provider fixture\""
            << "}";
        changed.close();

        const auto reloaded = provider(intent_at(100.0));
        REQUIRE(reloaded.ready);
        REQUIRE(near(reloaded.quantity_step, 0.01));
        REQUIRE(near(reloaded.min_notional, 20.0));
        const auto changed_result =
            astu::execution::SimulationEngine::run_with_instrument(
                intent_at(100.0),
                ready_data(),
                ready_risk(),
                reloaded,
                2'000);
        REQUIRE(changed_result.code == DecisionCode::FilterRejected);
        REQUIRE(!changed_result.accepted_for_simulation);

        std::ofstream stale(
            dir / "BTCUSDT.json",
            std::ios::binary | std::ios::trunc);
        stale
            << "{"
            << "\"schemaVersion\":1,"
            << "\"messageType\":\"InstrumentConstraints.v1\","
            << "\"generatedUnixMs\":" << (now_ms - 60'000) << ","
            << "\"ready\":true,"
            << "\"source\":\"TEST_FIXTURE_STALE\","
            << "\"symbol\":\"BTCUSDT\","
            << "\"priceTick\":0.1,"
            << "\"quantityStep\":0.001,"
            << "\"minQuantity\":0.001,"
            << "\"maxQuantity\":1000,"
            << "\"minNotional\":5,"
            << "\"maxNotional\":0,"
            << "\"detail\":\"stale provider fixture\""
            << "}";
        stale.close();

        const auto stale_rules = provider(intent_at(100.0));
        REQUIRE(!stale_rules.ready);
        REQUIRE(stale_rules.detail == "instrument constraints snapshot stale");
        const auto stale_result =
            astu::execution::SimulationEngine::run_with_instrument(
                intent_at(100.0),
                ready_data(),
                ready_risk(),
                stale_rules,
                2'000);
        REQUIRE(stale_result.code == DecisionCode::InstrumentUnavailable);

        std::filesystem::remove_all(dir);
    }

    {
        const auto missing_dir = std::filesystem::temp_directory_path() /
            "astu_instrument_constraints_missing";
        std::filesystem::remove_all(missing_dir);
        astu::instrument::LiveInstrumentProvider provider(missing_dir, 5'000);
        const auto missing = provider(intent_at(100.0));
        REQUIRE(!missing.ready);

        const auto result = astu::execution::SimulationEngine::run_with_instrument(
            intent_at(100.0), ready_data(), ready_risk(), missing, 2'000);
        REQUIRE(result.code == DecisionCode::InstrumentUnavailable);
    }

    std::cout << "astu_instrument_sizing_tests PASS\n";
    return 0;
}
