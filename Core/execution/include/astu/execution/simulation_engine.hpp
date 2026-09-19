#pragma once

#include <algorithm>
#include <cmath>
#include <string>

#include "astu/core/contracts.hpp"

namespace astu::execution {

class IntentValidator {
public:
    static astu::core::SimulationDecision validate(
        const astu::core::SignalIntent& intent,
        const astu::core::DataStatus& data,
        std::int64_t now_utc_ms) {
        using astu::core::DecisionCode;
        using astu::core::SimulationDecision;

        if (intent.schema_version != 1 || intent.signal_id.empty() ||
            intent.symbol.empty() || intent.universe_id.empty() ||
            intent.universe_version == 0 || intent.data_generation == 0 ||
            intent.trigger_price <= 0.0) {
            return {DecisionCode::InvalidIntent, false,
                    astu::core::increases_exposure(intent.action), 0.0,
                    "invalid SignalIntent"};
        }
        if (now_utc_ms < intent.valid_from_utc_ms) {
            return {DecisionCode::NotYetValid, false,
                    astu::core::increases_exposure(intent.action), 0.0,
                    "signal validity window has not opened"};
        }
        if (now_utc_ms >= intent.expires_utc_ms) {
            return {DecisionCode::Expired, false,
                    astu::core::increases_exposure(intent.action), 0.0,
                    "signal expired"};
        }
        if (!data.live || !data.fresh || !data.cache_ready || data.symbol != intent.symbol) {
            return {DecisionCode::DataNotReady, false,
                    astu::core::increases_exposure(intent.action), 0.0,
                    "WSRTD data is not live/fresh/cache-ready for symbol"};
        }
        if (!data.identity_ready || !data.universe_id.has_value() ||
            !data.universe_version.has_value() || !data.data_generation.has_value()) {
            return {DecisionCode::IdentityUnavailable, false,
                    astu::core::increases_exposure(intent.action), 0.0,
                    "universe/data identity unavailable; fail closed"};
        }
        if (*data.universe_id != intent.universe_id ||
            *data.universe_version != intent.universe_version) {
            return {DecisionCode::UniverseMismatch, false,
                    astu::core::increases_exposure(intent.action), 0.0,
                    "universe identity/version mismatch"};
        }
        if (*data.data_generation != intent.data_generation) {
            return {DecisionCode::DataGenerationMismatch, false,
                    astu::core::increases_exposure(intent.action), 0.0,
                    "dataGeneration mismatch"};
        }
        return {DecisionCode::SimulatedAccepted, true,
                astu::core::increases_exposure(intent.action), 0.0,
                "intent/data validation passed for simulation"};
    }
};

class AccountRiskEngine {
public:
    static astu::core::SimulationDecision evaluate(
        const astu::core::SignalIntent& intent,
        const astu::core::AccountRiskSnapshot& risk) {
        using astu::core::DecisionCode;
        using astu::core::RiskState;

        const bool exposure = astu::core::increases_exposure(intent.action);
        if (!risk.reconciled) {
            return {DecisionCode::AccountNotReconciled, false, exposure, 0.0,
                    "account snapshot is not reconciled"};
        }
        if (exposure && (risk.risk_state == RiskState::BlockNewEntries ||
                         risk.risk_state == RiskState::Emergency)) {
            return {DecisionCode::RiskBlocked, false, exposure, 0.0,
                    "risk state blocks new exposure"};
        }
        if (exposure && risk.max_open_positions > 0 &&
            risk.open_positions >= risk.max_open_positions) {
            return {DecisionCode::RiskBlocked, false, exposure, 0.0,
                    "max open positions reached"};
        }
        if (exposure && risk.max_gross_notional > 0.0 &&
            risk.gross_notional >= risk.max_gross_notional) {
            return {DecisionCode::RiskBlocked, false, exposure, 0.0,
                    "max gross notional reached"};
        }
        return {DecisionCode::SimulatedAccepted, true, exposure, 0.0,
                "risk gate passed for simulation"};
    }
};

class PositionSizer {
public:
    static double simulate_quantity(
        const astu::core::SignalIntent& intent,
        const astu::core::AccountRiskSnapshot& risk) {
        if (intent.trigger_price <= 0.0 || risk.risk_capital <= 0.0) {
            return 0.0;
        }
        constexpr double kSyntheticRiskFraction = 0.001;
        return (risk.risk_capital * kSyntheticRiskFraction) / intent.trigger_price;
    }
};

class OrderManager {
public:
    static astu::core::SimulationDecision simulate_only(
        const astu::core::SignalIntent& intent,
        double quantity) {
        return {
            astu::core::DecisionCode::OrderRoutingDisabled,
            true,
            astu::core::increases_exposure(intent.action),
            std::max(0.0, quantity),
            "SIMULATION_ONLY: order routing, credentials and private APIs are disabled",
        };
    }
};

class SimulationEngine {
public:
    static astu::core::SimulationDecision run(
        const astu::core::SignalIntent& intent,
        const astu::core::DataStatus& data,
        const astu::core::AccountRiskSnapshot& risk,
        std::int64_t now_utc_ms) {
        auto validation = IntentValidator::validate(intent, data, now_utc_ms);
        if (!validation.accepted_for_simulation) {
            return validation;
        }
        auto risk_result = AccountRiskEngine::evaluate(intent, risk);
        if (!risk_result.accepted_for_simulation) {
            return risk_result;
        }
        const double quantity = PositionSizer::simulate_quantity(intent, risk);
        return OrderManager::simulate_only(intent, quantity);
    }
};

}  // namespace astu::execution
