#pragma once

#include <algorithm>
#include <cmath>
#include <limits>
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
                    astu::core::increases_exposure(intent.action), 0.0, 0.0,
                    "invalid SignalIntent"};
        }
        if (now_utc_ms < intent.valid_from_utc_ms) {
            return {DecisionCode::NotYetValid, false,
                    astu::core::increases_exposure(intent.action), 0.0, 0.0,
                    "signal validity window has not opened"};
        }
        if (now_utc_ms >= intent.expires_utc_ms) {
            return {DecisionCode::Expired, false,
                    astu::core::increases_exposure(intent.action), 0.0, 0.0,
                    "signal expired"};
        }
        if (!data.live || !data.fresh || !data.cache_ready || data.symbol != intent.symbol) {
            return {DecisionCode::DataNotReady, false,
                    astu::core::increases_exposure(intent.action), 0.0, 0.0,
                    "WSRTD data is not live/fresh/cache-ready for symbol"};
        }
        if (!data.identity_ready || !data.universe_id.has_value() ||
            !data.universe_version.has_value() || !data.data_generation.has_value()) {
            return {DecisionCode::IdentityUnavailable, false,
                    astu::core::increases_exposure(intent.action), 0.0, 0.0,
                    "universe/data identity unavailable; fail closed"};
        }
        if (*data.universe_id != intent.universe_id ||
            *data.universe_version != intent.universe_version) {
            return {DecisionCode::UniverseMismatch, false,
                    astu::core::increases_exposure(intent.action), 0.0, 0.0,
                    "universe identity/version mismatch"};
        }
        if (*data.data_generation != intent.data_generation) {
            return {DecisionCode::DataGenerationMismatch, false,
                    astu::core::increases_exposure(intent.action), 0.0, 0.0,
                    "dataGeneration mismatch"};
        }
        return {DecisionCode::SimulatedAccepted, true,
                astu::core::increases_exposure(intent.action), 0.0, 0.0,
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
            return {DecisionCode::AccountNotReconciled, false, exposure, 0.0, 0.0,
                    "account snapshot is not reconciled"};
        }
        if (exposure && (risk.risk_state == RiskState::BlockNewEntries ||
                         risk.risk_state == RiskState::Emergency)) {
            return {DecisionCode::RiskBlocked, false, exposure, 0.0, 0.0,
                    "risk state blocks new exposure"};
        }
        if (exposure && risk.max_open_positions > 0 &&
            risk.open_positions >= risk.max_open_positions) {
            return {DecisionCode::RiskBlocked, false, exposure, 0.0, 0.0,
                    "max open positions reached"};
        }
        if (exposure && risk.max_gross_notional > 0.0 &&
            risk.gross_notional >= risk.max_gross_notional) {
            return {DecisionCode::RiskBlocked, false, exposure, 0.0, 0.0,
                    "max gross notional reached"};
        }
        return {DecisionCode::SimulatedAccepted, true, exposure, 0.0, 0.0,
                "risk gate passed for simulation"};
    }
};

class InstrumentFilterEngine {
public:
    static astu::core::SimulationDecision validate_rules(
        const astu::core::SignalIntent& intent,
        const astu::core::InstrumentConstraints& rules) {
        const bool exposure = astu::core::increases_exposure(intent.action);
        if (!rules.ready || rules.schema_version != 1 ||
            rules.symbol != intent.symbol) {
            return {astu::core::DecisionCode::InstrumentUnavailable, false,
                    exposure, 0.0, 0.0,
                    "instrument constraints unavailable or symbol mismatch"};
        }
        if (!std::isfinite(rules.price_tick) || rules.price_tick <= 0.0 ||
            !std::isfinite(rules.quantity_step) || rules.quantity_step <= 0.0 ||
            rules.min_quantity < 0.0 || rules.max_quantity < 0.0 ||
            rules.min_notional < 0.0 || rules.max_notional < 0.0 ||
            (rules.max_quantity > 0.0 && rules.max_quantity < rules.min_quantity) ||
            (rules.max_notional > 0.0 && rules.max_notional < rules.min_notional)) {
            return {astu::core::DecisionCode::InstrumentUnavailable, false,
                    exposure, 0.0, 0.0,
                    "instrument constraints are malformed"};
        }
        return {astu::core::DecisionCode::SimulatedAccepted, true,
                exposure, 0.0, 0.0,
                "instrument constraints validated"};
    }

    static astu::core::SimulationDecision validate_sized_quantity(
        const astu::core::SignalIntent& intent,
        const astu::core::InstrumentConstraints& rules,
        double quantity,
        double notional) {
        const bool exposure = astu::core::increases_exposure(intent.action);
        constexpr double eps = 1e-12;

        if (!std::isfinite(quantity) || !std::isfinite(notional) ||
            quantity <= 0.0 || notional <= 0.0) {
            return {astu::core::DecisionCode::SizingRejected, false,
                    exposure, 0.0, 0.0,
                    "deterministic sizing produced no executable quantity"};
        }
        if (rules.min_quantity > 0.0 && quantity + eps < rules.min_quantity) {
            return {astu::core::DecisionCode::FilterRejected, false,
                    exposure, quantity, notional,
                    "quantity below instrument minimum"};
        }
        if (rules.max_quantity > 0.0 && quantity - eps > rules.max_quantity) {
            return {astu::core::DecisionCode::FilterRejected, false,
                    exposure, quantity, notional,
                    "quantity above instrument maximum"};
        }
        if (rules.min_notional > 0.0 && notional + eps < rules.min_notional) {
            return {astu::core::DecisionCode::FilterRejected, false,
                    exposure, quantity, notional,
                    "notional below instrument minimum"};
        }
        if (rules.max_notional > 0.0 && notional - eps > rules.max_notional) {
            return {astu::core::DecisionCode::FilterRejected, false,
                    exposure, quantity, notional,
                    "notional above instrument maximum"};
        }
        return {astu::core::DecisionCode::SimulatedAccepted, true,
                exposure, quantity, notional,
                "instrument filters passed for simulation"};
    }
};

class PositionSizer {
public:
    struct Result {
        double quantity{0.0};
        double notional{0.0};
        double budget_notional{0.0};
    };

    static double simulate_quantity(
        const astu::core::SignalIntent& intent,
        const astu::core::AccountRiskSnapshot& risk) {
        if (intent.trigger_price <= 0.0 || risk.risk_capital <= 0.0) {
            return 0.0;
        }
        constexpr double kSyntheticRiskFraction = 0.001;
        return (risk.risk_capital * kSyntheticRiskFraction) / intent.trigger_price;
    }

    static Result simulate_with_constraints(
        const astu::core::SignalIntent& intent,
        const astu::core::AccountRiskSnapshot& risk,
        const astu::core::InstrumentConstraints& rules) {
        Result out;
        if (intent.trigger_price <= 0.0 || risk.risk_capital <= 0.0 ||
            rules.quantity_step <= 0.0) {
            return out;
        }

        constexpr double kSyntheticRiskFraction = 0.001;
        double budget = risk.risk_capital * kSyntheticRiskFraction;

        if (astu::core::increases_exposure(intent.action) &&
            risk.max_gross_notional > 0.0) {
            const double headroom =
                std::max(0.0, risk.max_gross_notional - risk.gross_notional);
            budget = std::min(budget, headroom);
        }

        if (rules.max_notional > 0.0) {
            budget = std::min(budget, rules.max_notional);
        }
        if (budget <= 0.0 || !std::isfinite(budget)) {
            return out;
        }

        const double raw_quantity = budget / intent.trigger_price;
        const double steps = std::floor(
            (raw_quantity / rules.quantity_step) + 1e-12);
        const double quantity = steps * rules.quantity_step;
        if (quantity <= 0.0 || !std::isfinite(quantity)) {
            return out;
        }

        out.quantity = quantity;
        out.notional = quantity * intent.trigger_price;
        out.budget_notional = budget;
        return out;
    }
};

class OrderManager {
public:
    static astu::core::SimulationDecision simulate_only(
        const astu::core::SignalIntent& intent,
        double quantity,
        double notional = 0.0) {
        return {
            astu::core::DecisionCode::OrderRoutingDisabled,
            true,
            astu::core::increases_exposure(intent.action),
            std::max(0.0, quantity),
            std::max(0.0, notional),
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
        return OrderManager::simulate_only(
            intent, quantity, quantity * intent.trigger_price);
    }

    static astu::core::SimulationDecision run_with_instrument(
        const astu::core::SignalIntent& intent,
        const astu::core::DataStatus& data,
        const astu::core::AccountRiskSnapshot& risk,
        const astu::core::InstrumentConstraints& rules,
        std::int64_t now_utc_ms) {
        auto validation = IntentValidator::validate(intent, data, now_utc_ms);
        if (!validation.accepted_for_simulation) {
            return validation;
        }

        auto risk_result = AccountRiskEngine::evaluate(intent, risk);
        if (!risk_result.accepted_for_simulation) {
            return risk_result;
        }

        auto rules_result = InstrumentFilterEngine::validate_rules(intent, rules);
        if (!rules_result.accepted_for_simulation) {
            return rules_result;
        }

        const auto sized =
            PositionSizer::simulate_with_constraints(intent, risk, rules);
        auto filter_result = InstrumentFilterEngine::validate_sized_quantity(
            intent, rules, sized.quantity, sized.notional);
        if (!filter_result.accepted_for_simulation) {
            return filter_result;
        }

        return OrderManager::simulate_only(
            intent, sized.quantity, sized.notional);
    }
};

}  // namespace astu::execution
