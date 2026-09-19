#pragma once

#include <cstdint>
#include <optional>
#include <string>

namespace astu::core {

enum class SignalAction {
    Buy,
    Sell,
    ScaleIn,
    ScaleOut,
};

enum class PositionSide {
    Long,
    Short,
};

enum class RiskState {
    Normal,
    Warning,
    Restricted,
    BlockNewEntries,
    Emergency,
};

struct SignalIntent {
    std::uint32_t schema_version{1};
    std::string signal_id;
    std::string analysis_run_id;
    std::string strategy_id;
    std::string strategy_version;
    std::string universe_id;
    std::uint64_t universe_version{0};
    std::string symbol;
    SignalAction action{SignalAction::Buy};
    PositionSide side{PositionSide::Long};
    std::string source_periodicity;
    std::int64_t source_bar_time_utc_ms{0};
    std::int64_t signal_time_utc_ms{0};
    double trigger_price{0.0};
    std::int64_t valid_from_utc_ms{0};
    std::int64_t expires_utc_ms{0};
    std::string quantity_model;
    double priority_score{0.0};
    std::uint64_t data_generation{0};
};

struct DataStatus {
    std::uint32_t schema_version{1};
    std::string source{"WSRTD"};
    std::string symbol;
    bool live{false};
    bool fresh{false};
    bool cache_ready{false};
    bool identity_ready{false};
    std::optional<std::uint64_t> universe_version;
    std::optional<std::uint64_t> data_generation;
    std::optional<std::uint32_t> cache_eod;
    std::optional<std::uint32_t> cache_intraday;
    std::string detail;
};

struct AccountRiskSnapshot {
    bool reconciled{false};
    RiskState risk_state{RiskState::Emergency};
    double risk_capital{0.0};
    double available_balance{0.0};
    double gross_notional{0.0};
    double max_gross_notional{0.0};
    std::uint32_t open_positions{0};
    std::uint32_t max_open_positions{0};
};

enum class DecisionCode {
    SimulatedAccepted,
    InvalidIntent,
    DataNotReady,
    IdentityUnavailable,
    UniverseMismatch,
    DataGenerationMismatch,
    NotYetValid,
    Expired,
    AccountNotReconciled,
    RiskBlocked,
    OrderRoutingDisabled,
};

struct SimulationDecision {
    DecisionCode code{DecisionCode::InvalidIntent};
    bool accepted_for_simulation{false};
    bool would_increase_exposure{false};
    double simulated_quantity{0.0};
    std::string reason;
};

inline bool increases_exposure(SignalAction action) noexcept {
    return action == SignalAction::Buy || action == SignalAction::ScaleIn;
}

}  // namespace astu::core
