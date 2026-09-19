#include <cassert>
#include <iostream>

#include "astu/core/contracts.hpp"
#include "astu/execution/simulation_engine.hpp"
#include "astu/trade/signal_intent_builder.hpp"
#include "astu/wsrtd/data_status_adapter.hpp"

namespace {

astu::core::SignalIntent base_intent() {
    astu::core::SignalIntent x;
    x.signal_id = "T-1";
    x.analysis_run_id = "AA-1";
    x.strategy_id = "S";
    x.strategy_version = "1";
    x.symbol = "BTCUSDT";
    x.action = astu::core::SignalAction::Buy;
    x.side = astu::core::PositionSide::Long;
    x.source_periodicity = "M1";
    x.source_bar_time_utc_ms = 1'000;
    x.signal_time_utc_ms = 1'100;
    x.trigger_price = 100.0;
    x.valid_from_utc_ms = 1'000;
    x.expires_utc_ms = 5'000;
    x.quantity_model = "TEST";
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
    d.universe_version = 3;
    d.universe_hash = "abc";
    d.data_generation = 9;
    d.generation_kind = "TEST";
    return d;
}

astu::core::AccountRiskSnapshot ready_risk() {
    astu::core::AccountRiskSnapshot r;
    r.reconciled = true;
    r.risk_state = astu::core::RiskState::Normal;
    r.risk_capital = 10'000.0;
    r.max_open_positions = 10;
    r.max_gross_notional = 100'000.0;
    return r;
}

}  // namespace

int main() {
    using astu::core::DecisionCode;

    {
        auto data = ready_data();
        auto intent = astu::trade::SignalIntentBuilder(base_intent())
                          .bind_data_identity(data)
                          .build();
        auto result = astu::execution::SimulationEngine::run(
            intent, data, ready_risk(), 2'000);
        assert(result.accepted_for_simulation);
        assert(result.code == DecisionCode::OrderRoutingDisabled);
        assert(result.simulated_quantity > 0.0);
    }

    {
        astu::wsrtd::WsrtdR2Snapshot snapshot;
        snapshot.symbol = "BTCUSDT";
        snapshot.cache_eod = 300;
        snapshot.cache_intraday = 1500;
        snapshot.quote_age_ms = 100;
        auto data = astu::wsrtd::DataStatusAdapter::from_r2(snapshot);
        auto intent = base_intent();
        intent.universe_id = "U";
        intent.universe_version = 3;
        intent.data_generation = 9;
        auto result = astu::execution::SimulationEngine::run(
            intent, data, ready_risk(), 2'000);
        assert(!result.accepted_for_simulation);
        assert(result.code == DecisionCode::IdentityUnavailable);
    }

    {
        astu::wsrtd::WsrtdR2Snapshot snapshot;
        snapshot.symbol = "BTCUSDT";
        snapshot.cache_eod = 300;
        snapshot.cache_intraday = 1500;
        snapshot.quote_age_ms = 100;
        astu::wsrtd::WsrtdR2IdentitySnapshot identity;
        identity.verified = true;
        identity.symbol = "BTCUSDT";
        identity.universe_id = "wsrtd-r2-bootstrap";
        identity.universe_version = 1;
        identity.universe_hash = "d31527c87e0aa41edc0fe81c7c16aafcdadaec976bf0455ad886cf4b81c502e0";
        identity.data_generation = 1'789'824'780'000ULL;
        auto data = astu::wsrtd::DataStatusAdapter::from_r2(snapshot, identity);
        auto intent = astu::trade::SignalIntentBuilder(base_intent())
                          .bind_data_identity(data)
                          .build();
        auto result = astu::execution::SimulationEngine::run(
            intent, data, ready_risk(), 2'000);
        assert(result.accepted_for_simulation);
        assert(result.code == DecisionCode::OrderRoutingDisabled);
    }

    {
        auto data = ready_data();
        auto intent = astu::trade::SignalIntentBuilder(base_intent())
                          .bind_data_identity(data)
                          .build();
        intent.universe_id = "OTHER";
        auto result = astu::execution::SimulationEngine::run(
            intent, data, ready_risk(), 2'000);
        assert(!result.accepted_for_simulation);
        assert(result.code == DecisionCode::UniverseMismatch);
    }

    {
        auto data = ready_data();
        auto intent = astu::trade::SignalIntentBuilder(base_intent())
                          .bind_data_identity(data)
                          .build();
        intent.data_generation += 1;
        auto result = astu::execution::SimulationEngine::run(
            intent, data, ready_risk(), 2'000);
        assert(!result.accepted_for_simulation);
        assert(result.code == DecisionCode::DataGenerationMismatch);
    }

    {
        auto risk = ready_risk();
        risk.risk_state = astu::core::RiskState::BlockNewEntries;
        auto data = ready_data();
        auto intent = astu::trade::SignalIntentBuilder(base_intent())
                          .bind_data_identity(data)
                          .build();
        auto result = astu::execution::SimulationEngine::run(
            intent, data, risk, 2'000);
        assert(!result.accepted_for_simulation);
        assert(result.code == DecisionCode::RiskBlocked);
    }

    std::cout << "astu_core_tests PASS\n";
    return 0;
}
