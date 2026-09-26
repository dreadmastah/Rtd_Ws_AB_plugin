#pragma once

#include "astu/core/contracts.hpp"

namespace astu::account {

// Read-only boundary for private account state.
//
// Deliberately absent from this interface:
// - order submission
// - order cancellation
// - leverage/margin mutation
// - credential management
//
// A later Binance private implementation may populate account state through
// this boundary without changing the simulation/risk contract.
class PrivateAccountGateway {
public:
    virtual ~PrivateAccountGateway() = default;
    virtual astu::core::AccountRiskSnapshot read_account_risk() = 0;
};

}  // namespace astu::account
