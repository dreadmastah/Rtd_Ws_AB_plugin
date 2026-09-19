#pragma once

#include <stdexcept>
#include <string>
#include <utility>

#include "astu/core/contracts.hpp"

namespace astu::trade {

class SignalIntentBuilder {
public:
    explicit SignalIntentBuilder(astu::core::SignalIntent intent)
        : intent_(std::move(intent)) {}

    astu::core::SignalIntent build() const {
        if (intent_.schema_version != 1) {
            throw std::invalid_argument("SignalIntent schema_version must be 1");
        }
        if (intent_.signal_id.empty() || intent_.analysis_run_id.empty() ||
            intent_.strategy_id.empty() || intent_.strategy_version.empty() ||
            intent_.universe_id.empty() || intent_.symbol.empty()) {
            throw std::invalid_argument("SignalIntent required identity field is empty");
        }
        if (intent_.universe_version == 0 || intent_.data_generation == 0) {
            throw std::invalid_argument("SignalIntent identity versions must be non-zero");
        }
        if (intent_.source_periodicity.empty() || intent_.quantity_model.empty()) {
            throw std::invalid_argument("SignalIntent source_periodicity/quantity_model required");
        }
        if (intent_.trigger_price <= 0.0) {
            throw std::invalid_argument("SignalIntent trigger_price must be positive");
        }
        if (intent_.expires_utc_ms <= intent_.valid_from_utc_ms) {
            throw std::invalid_argument("SignalIntent expiry must follow valid_from");
        }
        return intent_;
    }

private:
    astu::core::SignalIntent intent_;
};

}  // namespace astu::trade
