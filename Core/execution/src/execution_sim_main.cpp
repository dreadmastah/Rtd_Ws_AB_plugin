#include <iostream>

#include "astu/core/contracts.hpp"
#include "astu/execution/simulation_engine.hpp"

int main() {
    astu::core::SignalIntent intent;
    intent.signal_id = "SIM-001";
    intent.analysis_run_id = "AA-001";
    intent.strategy_id = "example";
    intent.strategy_version = "1";
    intent.universe_id = "U-SIM";
    intent.universe_version = 1;
    intent.symbol = "BTCUSDT";
    intent.action = astu::core::SignalAction::Buy;
    intent.side = astu::core::PositionSide::Long;
    intent.source_periodicity = "M1";
    intent.source_bar_time_utc_ms = 1'000;
    intent.signal_time_utc_ms = 1'100;
    intent.trigger_price = 100'000.0;
    intent.valid_from_utc_ms = 1'000;
    intent.expires_utc_ms = 10'000;
    intent.quantity_model = "SYNTHETIC_TEST_ONLY";
    intent.priority_score = 0.0;
    intent.data_generation = 7;

    astu::core::DataStatus data;
    data.symbol = "BTCUSDT";
    data.live = true;
    data.fresh = true;
    data.cache_ready = true;
    data.identity_ready = true;
    data.universe_version = 1;
    data.data_generation = 7;

    astu::core::AccountRiskSnapshot risk;
    risk.reconciled = true;
    risk.risk_state = astu::core::RiskState::Normal;
    risk.risk_capital = 10'000.0;
    risk.available_balance = 10'000.0;
    risk.max_gross_notional = 50'000.0;
    risk.max_open_positions = 10;

    const auto result = astu::execution::SimulationEngine::run(intent, data, risk, 2'000);
    std::cout << result.reason << "\n";
    std::cout << "simulated_quantity=" << result.simulated_quantity << "\n";
    return result.accepted_for_simulation ? 0 : 1;
}
