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

enum class PositionMode {
    Flat,
    Long,
    Short,
    Hedged,
    Unknown,
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
    std::optional<std::string> universe_id;
    std::optional<std::uint64_t> universe_version;
    std::optional<std::string> universe_hash;
    std::optional<std::uint64_t> data_generation;
    std::optional<std::string> generation_kind;
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

    // Execution-local projected-risk context. These fields are populated
    // after reading the reconciled AccountRiskSnapshot.v1 and are not claims
    // that the account snapshot itself contains order-reservation state.
    std::uint64_t pending_entry_scale_in_reservations{0};
    std::uint64_t max_pending_entry_scale_in_reservations{0};
    bool symbol_exposure_reconciled{false};
    double symbol_notional{0.0};
    double max_symbol_notional{0.0};
    double minimum_available_balance_reserve{0.0};
    double margin_reservation_rate{0.0};

    // Margin-health metrics originate from the reconciled account snapshot.
    // Configured limits are execution-local policy layered on top.
    bool margin_metrics_reconciled{false};
    double margin_balance{0.0};
    double initial_margin{0.0};
    double max_effective_leverage{0.0};
    double max_margin_utilization{0.0};
};

struct PositionSnapshot {
    std::uint32_t schema_version{1};
    bool reconciled{false};
    std::string source;
    std::string symbol;
    PositionMode mode{PositionMode::Unknown};
    double quantity{0.0};
    double notional{0.0};
    std::string detail;
};

struct InstrumentConstraints {
    std::uint32_t schema_version{1};
    bool ready{false};
    std::string source;
    std::string symbol;
    double price_tick{0.0};
    double quantity_step{0.0};
    double min_quantity{0.0};
    double max_quantity{0.0};
    double min_notional{0.0};
    double max_notional{0.0};
    std::string detail;
};

enum class DecisionCode : int {
    SimulatedAccepted = 0,
    InvalidIntent = 10,
    DataNotReady = 20,
    IdentityUnavailable = 21,
    UniverseMismatch = 22,
    DataGenerationMismatch = 23,
    NotYetValid = 24,
    Expired = 25,
    AccountNotReconciled = 30,
    RiskBlocked = 31,
    InstrumentUnavailable = 32,
    FilterRejected = 33,
    SizingRejected = 34,
    PositionUnavailable = 35,
    PositionConflict = 36,
    OrderRoutingDisabled = 100,
    DuplicateRequest = 110,
    FrameInvalid = 120,
};

struct SimulationDecision {
    DecisionCode code{DecisionCode::InvalidIntent};
    bool accepted_for_simulation{false};
    bool would_increase_exposure{false};
    double simulated_quantity{0.0};
    double simulated_notional{0.0};
    std::string reason;
};

inline bool increases_exposure(SignalAction action) noexcept {
    return action == SignalAction::Buy || action == SignalAction::ScaleIn;
}

}  // namespace astu::core
