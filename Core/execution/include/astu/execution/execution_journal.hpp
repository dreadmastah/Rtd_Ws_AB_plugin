#pragma once

#include <chrono>
#include <cmath>
#include <cstdint>
#include <deque>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <limits>
#include <mutex>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include "astu/execution/exposure_reservation.hpp"
#include "astu/execution/order_fsm.hpp"
#include "astu/ipc/flat_json.hpp"
#include "astu/ipc/simulation_protocol.hpp"

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#include <share.h>
#include <sys/stat.h>
#endif

namespace astu::execution {

class ExecutionJournal {
public:
    struct SimulationOrderIntentRecord {
        std::string request_id;
        std::string idempotency_key;
        std::string signal_id;
        std::string symbol;
        astu::core::SignalAction action{astu::core::SignalAction::Buy};
        astu::core::PositionSide side{astu::core::PositionSide::Long};
        double quantity{0.0};
        double reference_price{0.0};
        double notional{0.0};
    };

    explicit ExecutionJournal(
        std::filesystem::path path,
        std::size_t replay_capacity = 100'000,
        double default_margin_reservation_rate = 0.0)
        : path_(std::move(path)),
          replay_capacity_(replay_capacity),
          default_margin_reservation_rate_(
              default_margin_reservation_rate) {
        if (!std::isfinite(default_margin_reservation_rate_) ||
            default_margin_reservation_rate_ < 0.0) {
            throw std::invalid_argument(
                "default margin reservation rate must be finite and non-negative");
        }
        if (!path_.parent_path().empty()) {
            std::filesystem::create_directories(path_.parent_path());
        }
        load_existing();
    }

    bool accept_idempotency_key(const std::string& key) {
        std::lock_guard<std::mutex> lock(mu_);
        if (key.empty() || replay_capacity_ == 0) {
            return false;
        }
        if (seen_.contains(key)) {
            return false;
        }

        std::ostringstream reservation;
        reservation
            << "{"
            << "\"schemaVersion\":1"
            << ",\"eventType\":\"IDEMPOTENCY_RESERVATION\""
            << ",\"utcMs\":" << utc_now_ms()
            << ",\"idempotencyKey\":\"" << astu::ipc::json_escape(key) << "\""
            << "}\n";
        append_durable(reservation.str());
        remember_unlocked(key);
        return true;
    }

    void append(
        const astu::ipc::SimulationRequest& request,
        const astu::ipc::SimulationResponse& response,
        std::int64_t utc_ms) {
        std::lock_guard<std::mutex> lock(mu_);
        if (!path_.parent_path().empty()) {
            std::filesystem::create_directories(path_.parent_path());
        }

        std::ostringstream out;
        out << std::setprecision(17);
        out
            << "{"
            << "\"schemaVersion\":1"
            << ",\"eventType\":\"SIMULATION_DECISION\""
            << ",\"utcMs\":" << utc_ms
            << ",\"requestId\":\"" << astu::ipc::json_escape(request.request_id) << "\""
            << ",\"idempotencyKey\":\"" << astu::ipc::json_escape(request.idempotency_key) << "\""
            << ",\"signalId\":\"" << astu::ipc::json_escape(request.intent.signal_id) << "\""
            << ",\"simulationOrderId\":\"" << astu::ipc::json_escape(response.simulation_order_id) << "\""
            << ",\"symbol\":\"" << astu::ipc::json_escape(request.intent.symbol) << "\""
            << ",\"universeId\":\"" << astu::ipc::json_escape(request.intent.universe_id) << "\""
            << ",\"universeVersion\":" << request.intent.universe_version
            << ",\"dataGeneration\":" << request.intent.data_generation
            << ",\"decisionCode\":\""
            << astu::ipc::decision_to_string(response.decision_code) << "\""
            << ",\"acceptedForSimulation\":"
            << (response.accepted_for_simulation ? "true" : "false")
            << ",\"wouldIncreaseExposure\":"
            << (response.would_increase_exposure ? "true" : "false")
            << ",\"simulatedQuantity\":" << response.simulated_quantity
            << ",\"simulatedNotional\":" << response.simulated_notional
            << ",\"orderRoutingEnabled\":"
            << (response.order_routing_enabled ? "true" : "false")
            << ",\"executionEnvironment\":\""
            << astu::ipc::json_escape(
                   response.execution_environment)
            << "\""
            << ",\"exchangeClientOrderId\":\""
            << astu::ipc::json_escape(
                   response.exchange_client_order_id)
            << "\""
            << ",\"exchangeOrderId\":\""
            << astu::ipc::json_escape(
                   response.exchange_order_id)
            << "\""
            << ",\"exchangeOrderStatus\":\""
            << astu::ipc::json_escape(
                   response.exchange_order_status)
            << "\""
            << ",\"reason\":\"" << astu::ipc::json_escape(response.reason) << "\""
            << "}\n";

        append_durable(out.str());
    }

    void append_simulation_order_intent(
        const astu::ipc::SimulationRequest& request,
        const astu::ipc::SimulationResponse& response,
        std::int64_t utc_ms) {
        std::lock_guard<std::mutex> lock(mu_);
        if (response.simulation_order_id.empty() ||
            !response.accepted_for_simulation ||
            response.order_routing_enabled ||
            response.simulated_quantity <= 0.0 ||
            response.simulated_notional <= 0.0) {
            throw std::invalid_argument(
                "simulation order intent requires accepted non-routing sizing result");
        }
        if (order_intents_.contains(response.simulation_order_id)) {
            throw std::invalid_argument(
                "simulation order intent already journaled");
        }

        std::ostringstream out;
        out << std::setprecision(17);
        out
            << "{"
            << "\"schemaVersion\":1"
            << ",\"eventType\":\"SIMULATION_ORDER_INTENT\""
            << ",\"utcMs\":" << utc_ms
            << ",\"simulationOrderId\":\""
            << astu::ipc::json_escape(response.simulation_order_id) << "\""
            << ",\"requestId\":\"" << astu::ipc::json_escape(request.request_id) << "\""
            << ",\"idempotencyKey\":\"" << astu::ipc::json_escape(request.idempotency_key) << "\""
            << ",\"signalId\":\"" << astu::ipc::json_escape(request.intent.signal_id) << "\""
            << ",\"symbol\":\"" << astu::ipc::json_escape(request.intent.symbol) << "\""
            << ",\"action\":\"" << astu::ipc::action_to_string(request.intent.action) << "\""
            << ",\"side\":\"" << astu::ipc::side_to_string(request.intent.side) << "\""
            << ",\"quantity\":" << response.simulated_quantity
            << ",\"referencePrice\":" << request.intent.trigger_price
            << ",\"notional\":" << response.simulated_notional
            << ",\"simulationOnly\":true"
            << ",\"orderRoutingEnabled\":false"
            << ",\"exchangeSubmissionAttempted\":false"
            << "}\n";

        append_durable(out.str());
        order_intents_.emplace(
            response.simulation_order_id,
            SimulationOrderIntentRecord{
                request.request_id,
                request.idempotency_key,
                request.intent.signal_id,
                request.intent.symbol,
                request.intent.action,
                request.intent.side,
                response.simulated_quantity,
                request.intent.trigger_price,
                response.simulated_notional,
            });
    }

    std::optional<SimulationOrderIntentRecord> simulation_order_intent(
        const std::string& simulation_order_id) const {
        std::lock_guard<std::mutex> lock(mu_);
        const auto it = order_intents_.find(simulation_order_id);
        if (it == order_intents_.end()) {
            return std::nullopt;
        }
        return it->second;
    }

    std::size_t recovered_order_intent_count() const {
        std::lock_guard<std::mutex> lock(mu_);
        return order_intents_.size();
    }

    bool append_exposure_reservation(
        const astu::ipc::SimulationRequest& request,
        const astu::ipc::SimulationResponse& response,
        std::int64_t utc_ms) {
        std::lock_guard<std::mutex> lock(mu_);

        if (!astu::core::increases_exposure(request.intent.action)) {
            return false;
        }
        if (response.simulation_order_id.empty() ||
            !response.accepted_for_simulation ||
            response.order_routing_enabled ||
            !response.would_increase_exposure ||
            !std::isfinite(response.simulated_quantity) ||
            !std::isfinite(response.simulated_notional) ||
            response.simulated_quantity <= 0.0 ||
            response.simulated_notional <= 0.0) {
            throw std::invalid_argument(
                "exposure reservation requires accepted exposure-increasing simulation result");
        }

        const auto intent_it =
            order_intents_.find(response.simulation_order_id);
        if (intent_it == order_intents_.end()) {
            throw std::invalid_argument(
                "exposure reservation requires normalized simulation order intent");
        }
        const auto state_it =
            order_states_.find(response.simulation_order_id);
        if (state_it == order_states_.end() ||
            is_terminal_order_state(state_it->second.state)) {
            throw std::invalid_argument(
                "exposure reservation requires active simulation order state");
        }
        if (exposure_reservations_.contains(
                response.simulation_order_id)) {
            throw std::invalid_argument(
                "exposure reservation already exists");
        }

        const bool position_slot =
            reserves_new_position_slot(request.intent.action);
        const double margin_reservation_rate =
            default_margin_reservation_rate_;
        const double reserved_available_balance =
            response.simulated_notional *
            margin_reservation_rate;
        if (!std::isfinite(reserved_available_balance) ||
            reserved_available_balance < 0.0) {
            throw std::invalid_argument(
                "invalid available-balance reservation");
        }
        std::ostringstream out;
        out << std::setprecision(17);
        out
            << "{"
            << "\"schemaVersion\":1"
            << ",\"eventType\":\"EXPOSURE_RESERVATION_CREATED\""
            << ",\"utcMs\":" << utc_ms
            << ",\"simulationOrderId\":\""
            << astu::ipc::json_escape(response.simulation_order_id)
            << "\""
            << ",\"signalId\":\""
            << astu::ipc::json_escape(request.intent.signal_id)
            << "\""
            << ",\"symbol\":\""
            << astu::ipc::json_escape(request.intent.symbol)
            << "\""
            << ",\"action\":\""
            << astu::ipc::action_to_string(request.intent.action)
            << "\""
            << ",\"side\":\""
            << astu::ipc::side_to_string(request.intent.side)
            << "\""
            << ",\"reservedQuantity\":"
            << response.simulated_quantity
            << ",\"reservedGrossNotional\":"
            << response.simulated_notional
            << ",\"marginReservationRate\":"
            << margin_reservation_rate
            << ",\"reservedAvailableBalance\":"
            << reserved_available_balance
            << ",\"reservesPositionSlot\":"
            << (position_slot ? "true" : "false")
            << ",\"simulationOnly\":true"
            << ",\"exchangeSubmissionAttempted\":false"
            << "}\n";

        append_durable(out.str());
        exposure_reservations_.emplace(
            response.simulation_order_id,
            ExposureReservationRecord{
                request.intent.symbol,
                request.intent.action,
                request.intent.side,
                response.simulated_quantity,
                response.simulated_notional,
                reserved_available_balance,
                margin_reservation_rate,
                position_slot,
                true,
            });
        ++exposure_reservation_create_count_;
        return true;
    }

    ExposureReservationSummary exposure_reservation_summary(
        const std::string& symbol = {}) const {
        std::lock_guard<std::mutex> lock(mu_);
        ExposureReservationSummary summary;
        for (const auto& [order_id, reservation] :
             exposure_reservations_) {
            (void)order_id;
            if (!reservation.active) {
                continue;
            }
            ++summary.active_reservations;
            summary.reserved_gross_notional +=
                reservation.reserved_gross_notional;
            summary.reserved_available_balance +=
                reservation.reserved_available_balance;
            summary.reserved_net_directional_notional +=
                position_side_direction(reservation.side) *
                reservation.reserved_gross_notional;
            if (reservation.reserves_position_slot &&
                summary.reserved_position_slots <
                    std::numeric_limits<std::uint32_t>::max()) {
                ++summary.reserved_position_slots;
            }
            if (!symbol.empty() && reservation.symbol == symbol) {
                ++summary.symbol_active_reservations;
                summary.symbol_reserved_gross_notional +=
                    reservation.reserved_gross_notional;
            }
        }
        return summary;
    }

    std::uint64_t exposure_reservation_create_count() const {
        std::lock_guard<std::mutex> lock(mu_);
        return exposure_reservation_create_count_;
    }

    std::uint64_t exposure_reservation_release_count() const {
        std::lock_guard<std::mutex> lock(mu_);
        return exposure_reservation_release_count_;
    }

    std::uint64_t exposure_reservation_implicit_release_count() const {
        std::lock_guard<std::mutex> lock(mu_);
        return exposure_reservation_implicit_release_count_;
    }

    std::uint64_t exposure_reservation_reconstructed_count() const {
        std::lock_guard<std::mutex> lock(mu_);
        return exposure_reservation_reconstructed_count_;
    }

    void append_reconciliation_event(
        const std::string& event_id,
        const std::string& simulation_order_id,
        const std::string& reconciliation_type,
        astu::execution::OrderState to_state,
        double cumulative_filled_quantity,
        std::int64_t utc_ms,
        std::string detail) {
        std::lock_guard<std::mutex> lock(mu_);
        if (event_id.empty() || simulation_order_id.empty() ||
            reconciliation_type.empty()) {
            throw std::invalid_argument(
                "reconciliation event identity/type is required");
        }
        if (reconciliation_event_ids_.contains(event_id)) {
            throw std::invalid_argument(
                "duplicate reconciliation event id");
        }
        if (reconciliation_target_from_type_unlocked(
                reconciliation_type) != to_state) {
            throw std::invalid_argument(
                "reconciliation type/toState mismatch");
        }

        const auto intent_it = order_intents_.find(simulation_order_id);
        if (intent_it == order_intents_.end()) {
            throw std::invalid_argument(
                "simulation order intent unavailable for reconciliation");
        }
        const auto state_it = order_states_.find(simulation_order_id);
        if (state_it == order_states_.end()) {
            throw std::invalid_argument(
                "simulation order state unavailable for reconciliation");
        }

        const auto& intent = intent_it->second;
        const auto previous_progress =
            reconciliation_progress_.find(simulation_order_id);
        const double previous_filled =
            previous_progress == reconciliation_progress_.end()
                ? 0.0
                : previous_progress->second.cumulative_filled_quantity;
        const std::uint64_t reconciliation_sequence =
            previous_progress == reconciliation_progress_.end()
                ? 1
                : previous_progress->second.sequence + 1;

        validate_reconciliation_quantity_unlocked(
            intent.quantity,
            previous_filled,
            cumulative_filled_quantity,
            to_state);

        astu::execution::OrderStateMachine::require_transition(
            state_it->second.state,
            to_state);
        const auto transition_sequence = state_it->second.sequence + 1;

        std::ostringstream out;
        out << std::setprecision(17);
        out
            << "{"
            << "\"schemaVersion\":1"
            << ",\"eventType\":\"SIMULATION_RECONCILIATION_EVENT\""
            << ",\"utcMs\":" << utc_ms
            << ",\"eventId\":\"" << astu::ipc::json_escape(event_id) << "\""
            << ",\"simulationOrderId\":\""
            << astu::ipc::json_escape(simulation_order_id) << "\""
            << ",\"reconciliationType\":\""
            << astu::ipc::json_escape(reconciliation_type) << "\""
            << ",\"fromState\":\""
            << astu::execution::order_state_to_string(state_it->second.state)
            << "\""
            << ",\"toState\":\""
            << astu::execution::order_state_to_string(to_state) << "\""
            << ",\"transitionSequence\":" << transition_sequence
            << ",\"reconciliationSequence\":" << reconciliation_sequence
            << ",\"orderQuantity\":" << intent.quantity
            << ",\"cumulativeFilledQuantity\":" << cumulative_filled_quantity
            << ",\"simulationOnly\":true"
            << ",\"exchangeSubmissionAttempted\":false"
            << ",\"detail\":\"" << astu::ipc::json_escape(detail) << "\""
            << "}\n";

        append_durable(out.str());
        order_states_[simulation_order_id] =
            OrderRecoveryState{to_state, transition_sequence};
        reconciliation_progress_[simulation_order_id] =
            ReconciliationRecoveryState{
                reconciliation_sequence,
                cumulative_filled_quantity,
            };
        reconciliation_event_ids_.insert(event_id);
        ++order_transition_count_;
        ++reconciliation_event_count_;

        if (is_terminal_order_state(to_state)) {
            release_exposure_reservation_unlocked(
                simulation_order_id,
                utc_ms,
                to_state,
                "terminal reconciliation released projected exposure reservation");
        }
    }

    double reconciled_filled_quantity(
        const std::string& simulation_order_id) const {
        std::lock_guard<std::mutex> lock(mu_);
        const auto it = reconciliation_progress_.find(simulation_order_id);
        return it == reconciliation_progress_.end()
            ? 0.0
            : it->second.cumulative_filled_quantity;
    }

    std::uint64_t reconciliation_event_count() const {
        std::lock_guard<std::mutex> lock(mu_);
        return reconciliation_event_count_;
    }

    void append_order_transition(
        const astu::ipc::SimulationRequest& request,
        const std::string& simulation_order_id,
        astu::execution::OrderState to_state,
        std::int64_t utc_ms,
        std::string reason,
        bool simulation_only = true,
        bool exchange_submission_attempted = false,
        std::string execution_environment = "SIMULATION_ONLY") {
        std::lock_guard<std::mutex> lock(mu_);
        if (simulation_order_id.empty()) {
            throw std::invalid_argument("simulation order id is required");
        }

        std::string from_state = "NONE";
        std::uint64_t sequence = 1;
        const auto existing = order_states_.find(simulation_order_id);
        if (existing == order_states_.end()) {
            if (to_state != astu::execution::OrderState::IntentReceived) {
                throw std::invalid_argument(
                    "first order-state transition must be INTENT_RECEIVED");
            }
        } else {
            astu::execution::OrderStateMachine::require_transition(
                existing->second.state,
                to_state);
            from_state =
                astu::execution::order_state_to_string(existing->second.state);
            sequence = existing->second.sequence + 1;
        }

        std::ostringstream out;
        out << std::setprecision(17);
        out
            << "{"
            << "\"schemaVersion\":1"
            << ",\"eventType\":\"ORDER_STATE_TRANSITION\""
            << ",\"utcMs\":" << utc_ms
            << ",\"simulationOrderId\":\""
            << astu::ipc::json_escape(simulation_order_id) << "\""
            << ",\"requestId\":\"" << astu::ipc::json_escape(request.request_id) << "\""
            << ",\"signalId\":\"" << astu::ipc::json_escape(request.intent.signal_id) << "\""
            << ",\"symbol\":\"" << astu::ipc::json_escape(request.intent.symbol) << "\""
            << ",\"fromState\":\"" << from_state << "\""
            << ",\"toState\":\""
            << astu::execution::order_state_to_string(to_state) << "\""
            << ",\"transitionSequence\":" << sequence
            << ",\"simulationOnly\":"
            << (simulation_only ? "true" : "false")
            << ",\"exchangeSubmissionAttempted\":"
            << (exchange_submission_attempted ? "true" : "false")
            << ",\"executionEnvironment\":\""
            << astu::ipc::json_escape(execution_environment) << "\""
            << ",\"reason\":\"" << astu::ipc::json_escape(reason) << "\""
            << "}\n";

        append_durable(out.str());
        order_states_[simulation_order_id] = OrderRecoveryState{
            to_state,
            sequence,
        };
        ++order_transition_count_;
    }

    void append_testnet_submission_attempt(
        const astu::ipc::SimulationRequest& request,
        const std::string& simulation_order_id,
        const std::string& client_order_id,
        const std::string& exchange_side,
        double quantity,
        bool reduce_only,
        std::int64_t utc_ms) {
        std::lock_guard<std::mutex> lock(mu_);
        const auto state_it = order_states_.find(simulation_order_id);
        if (state_it == order_states_.end() ||
            state_it->second.state != OrderState::Submitting ||
            client_order_id.empty() ||
            (exchange_side != "BUY" && exchange_side != "SELL") ||
            !std::isfinite(quantity) || quantity <= 0.0) {
            throw std::invalid_argument(
                "invalid Binance Testnet submission attempt");
        }

        std::ostringstream out;
        out << std::setprecision(17);
        out
            << "{"
            << "\"schemaVersion\":1"
            << ",\"eventType\":\"TESTNET_ORDER_SUBMISSION_ATTEMPT\""
            << ",\"utcMs\":" << utc_ms
            << ",\"simulationOrderId\":\""
            << astu::ipc::json_escape(simulation_order_id) << "\""
            << ",\"requestId\":\""
            << astu::ipc::json_escape(request.request_id) << "\""
            << ",\"signalId\":\""
            << astu::ipc::json_escape(request.intent.signal_id) << "\""
            << ",\"symbol\":\""
            << astu::ipc::json_escape(request.intent.symbol) << "\""
            << ",\"exchangeSide\":\""
            << exchange_side << "\""
            << ",\"quantity\":" << quantity
            << ",\"reduceOnly\":"
            << (reduce_only ? "true" : "false")
            << ",\"clientOrderId\":\""
            << astu::ipc::json_escape(client_order_id) << "\""
            << ",\"executionEnvironment\":\"BINANCE_USDM_TESTNET\""
            << ",\"exchangeSubmissionAttempted\":true"
            << "}\n";
        append_durable(out.str());
        ++testnet_submission_attempt_count_;
    }

    std::uint64_t testnet_submission_attempt_count() const {
        std::lock_guard<std::mutex> lock(mu_);
        return testnet_submission_attempt_count_;
    }

    std::optional<astu::execution::OrderState> order_state(
        const std::string& simulation_order_id) const {
        std::lock_guard<std::mutex> lock(mu_);
        const auto it = order_states_.find(simulation_order_id);
        if (it == order_states_.end()) {
            return std::nullopt;
        }
        return it->second.state;
    }

    std::size_t recovered_order_count() const {
        std::lock_guard<std::mutex> lock(mu_);
        return order_states_.size();
    }

    std::uint64_t order_transition_count() const {
        std::lock_guard<std::mutex> lock(mu_);
        return order_transition_count_;
    }

    std::vector<std::string> tracked_order_ids() const {
        std::lock_guard<std::mutex> lock(mu_);
        std::vector<std::string> out;
        out.reserve(order_intents_.size());
        for (const auto& [order_id, intent] : order_intents_) {
            (void)intent;
            out.push_back(order_id);
        }
        return out;
    }

    std::size_t replay_size() const {
        std::lock_guard<std::mutex> lock(mu_);
        return order_.size();
    }

    const std::filesystem::path& path() const noexcept {
        return path_;
    }

private:
    void load_existing() {
        std::lock_guard<std::mutex> lock(mu_);
        if (!std::filesystem::exists(path_)) {
            return;
        }
        std::ifstream in(path_, std::ios::binary);
        if (!in) {
            throw std::runtime_error("cannot open execution journal: " + path_.string());
        }
        std::string line;
        while (std::getline(in, line)) {
            if (line.empty()) {
                continue;
            }
            try {
                const auto obj = astu::ipc::FlatJsonParser(line).parse();
                if (astu::ipc::require_u64(obj, "schemaVersion") != 1) {
                    continue;
                }
                const auto event_type = astu::ipc::require_string(obj, "eventType");
                if (event_type == "ORDER_STATE_TRANSITION") {
                    replay_order_transition_unlocked(obj);
                    continue;
                }
                if (event_type == "SIMULATION_ORDER_INTENT") {
                    replay_simulation_order_intent_unlocked(obj);
                    continue;
                }
                if (event_type == "SIMULATION_RECONCILIATION_EVENT") {
                    replay_reconciliation_event_unlocked(obj);
                    continue;
                }
                if (event_type == "EXPOSURE_RESERVATION_CREATED") {
                    replay_exposure_reservation_created_unlocked(obj);
                    continue;
                }
                if (event_type == "EXPOSURE_RESERVATION_RELEASED") {
                    replay_exposure_reservation_released_unlocked(obj);
                    continue;
                }
                if (event_type == "TESTNET_ORDER_SUBMISSION_ATTEMPT") {
                    replay_testnet_submission_attempt_unlocked(obj);
                    continue;
                }
                if (event_type != "IDEMPOTENCY_RESERVATION" &&
                    event_type != "SIMULATION_DECISION") {
                    continue;
                }
                const auto key = astu::ipc::require_string(obj, "idempotencyKey");
                if (!key.empty() && !seen_.contains(key)) {
                    remember_unlocked(key);
                }
            } catch (const std::exception& exc) {
                throw std::runtime_error(
                    "execution journal replay parse failure: " + std::string(exc.what()));
            }
        }
        finalize_exposure_reservations_after_replay_unlocked();
    }

    struct OrderRecoveryState {
        astu::execution::OrderState state{
            astu::execution::OrderState::IntentReceived};
        std::uint64_t sequence{0};
    };

    struct ReconciliationRecoveryState {
        std::uint64_t sequence{0};
        double cumulative_filled_quantity{0.0};
    };

    struct ExposureReservationRecord {
        std::string symbol;
        astu::core::SignalAction action{astu::core::SignalAction::Buy};
        astu::core::PositionSide side{astu::core::PositionSide::Long};
        double reserved_quantity{0.0};
        double reserved_gross_notional{0.0};
        double reserved_available_balance{0.0};
        double margin_reservation_rate{0.0};
        bool reserves_position_slot{false};
        bool active{false};
    };

    static astu::execution::OrderState
    reconciliation_target_from_type_unlocked(
        const std::string& value) {
        if (value == "MARK_UNKNOWN") {
            return astu::execution::OrderState::UnknownReconcileRequired;
        }
        if (value == "ACKNOWLEDGED") {
            return astu::execution::OrderState::Acknowledged;
        }
        if (value == "WORKING") {
            return astu::execution::OrderState::Working;
        }
        if (value == "PARTIAL_FILL") {
            return astu::execution::OrderState::Partial;
        }
        if (value == "FILLED") {
            return astu::execution::OrderState::Filled;
        }
        if (value == "CANCELED") {
            return astu::execution::OrderState::Canceled;
        }
        if (value == "REJECTED") {
            return astu::execution::OrderState::Rejected;
        }
        throw std::invalid_argument(
            "unknown reconciliation type");
    }

    static void validate_reconciliation_quantity_unlocked(
        double order_quantity,
        double previous_filled,
        double cumulative_filled,
        astu::execution::OrderState to_state) {
        constexpr double kEpsilon = 1e-12;
        if (!std::isfinite(order_quantity) || order_quantity <= 0.0 ||
            !std::isfinite(cumulative_filled) ||
            cumulative_filled < -kEpsilon ||
            cumulative_filled + kEpsilon < previous_filled ||
            cumulative_filled > order_quantity + kEpsilon) {
            throw std::invalid_argument(
                "invalid reconciliation cumulative fill quantity");
        }

        if (to_state == astu::execution::OrderState::Partial &&
            (cumulative_filled <= kEpsilon ||
             cumulative_filled >= order_quantity - kEpsilon)) {
            throw std::invalid_argument(
                "PARTIAL requires cumulative fill strictly between zero and order quantity");
        }
        if (to_state == astu::execution::OrderState::Filled &&
            std::fabs(cumulative_filled - order_quantity) > kEpsilon) {
            throw std::invalid_argument(
                "FILLED requires cumulative fill equal to order quantity");
        }
    }

    bool release_exposure_reservation_unlocked(
        const std::string& simulation_order_id,
        std::int64_t utc_ms,
        astu::execution::OrderState terminal_state,
        const std::string& reason) {
        const auto it =
            exposure_reservations_.find(simulation_order_id);
        if (it == exposure_reservations_.end() ||
            !it->second.active) {
            return false;
        }
        if (!is_terminal_order_state(terminal_state)) {
            throw std::invalid_argument(
                "exposure reservation release requires terminal order state");
        }

        std::ostringstream out;
        out << std::setprecision(17);
        out
            << "{"
            << "\"schemaVersion\":1"
            << ",\"eventType\":\"EXPOSURE_RESERVATION_RELEASED\""
            << ",\"utcMs\":" << utc_ms
            << ",\"simulationOrderId\":\""
            << astu::ipc::json_escape(simulation_order_id)
            << "\""
            << ",\"symbol\":\""
            << astu::ipc::json_escape(it->second.symbol)
            << "\""
            << ",\"releasedGrossNotional\":"
            << it->second.reserved_gross_notional
            << ",\"releasedAvailableBalance\":"
            << it->second.reserved_available_balance
            << ",\"releasedPositionSlot\":"
            << (it->second.reserves_position_slot ? "true" : "false")
            << ",\"terminalState\":\""
            << order_state_to_string(terminal_state)
            << "\""
            << ",\"simulationOnly\":true"
            << ",\"exchangeSubmissionAttempted\":false"
            << ",\"reason\":\""
            << astu::ipc::json_escape(reason)
            << "\""
            << "}\n";

        append_durable(out.str());
        it->second.active = false;
        ++exposure_reservation_release_count_;
        return true;
    }

    void replay_exposure_reservation_created_unlocked(
        const astu::ipc::JsonObject& obj) {
        const auto order_id =
            astu::ipc::require_string(obj, "simulationOrderId");
        const auto symbol =
            astu::ipc::require_string(obj, "symbol");
        const auto action = astu::ipc::action_from_string(
            astu::ipc::require_string(obj, "action"));
        const auto side = astu::ipc::side_from_string(
            astu::ipc::require_string(obj, "side"));
        const auto quantity =
            astu::ipc::require_double(obj, "reservedQuantity");
        const auto notional =
            astu::ipc::require_double(obj, "reservedGrossNotional");
        double margin_reservation_rate =
            default_margin_reservation_rate_;
        double reserved_available_balance =
            notional * margin_reservation_rate;
        const auto rate_it = obj.find("marginReservationRate");
        const auto balance_it =
            obj.find("reservedAvailableBalance");
        if ((rate_it == obj.end()) !=
            (balance_it == obj.end())) {
            throw std::runtime_error(
                "exposure reservation margin fields are incomplete");
        }
        if (rate_it != obj.end()) {
            margin_reservation_rate =
                astu::ipc::require_double(
                    obj,
                    "marginReservationRate");
            reserved_available_balance =
                astu::ipc::require_double(
                    obj,
                    "reservedAvailableBalance");
        }
        const bool position_slot =
            astu::ipc::require_bool(obj, "reservesPositionSlot");

        if (order_id.empty() || symbol.empty() ||
            !astu::core::increases_exposure(action) ||
            !std::isfinite(quantity) || quantity <= 0.0 ||
            !std::isfinite(notional) || notional <= 0.0 ||
            !std::isfinite(margin_reservation_rate) ||
            margin_reservation_rate < 0.0 ||
            !std::isfinite(reserved_available_balance) ||
            reserved_available_balance < 0.0 ||
            std::fabs(
                reserved_available_balance -
                notional * margin_reservation_rate) > 1e-9 ||
            position_slot != reserves_new_position_slot(action) ||
            !astu::ipc::require_bool(obj, "simulationOnly") ||
            astu::ipc::require_bool(
                obj,
                "exchangeSubmissionAttempted")) {
            throw std::runtime_error(
                "execution journal invalid exposure reservation creation");
        }

        const auto intent_it = order_intents_.find(order_id);
        if (intent_it == order_intents_.end()) {
            throw std::runtime_error(
                "exposure reservation missing simulation order intent");
        }
        const auto& intent = intent_it->second;
        if (intent.symbol != symbol ||
            intent.action != action ||
            intent.side != side ||
            std::fabs(intent.quantity - quantity) > 1e-12 ||
            std::fabs(intent.notional - notional) > 1e-9) {
            throw std::runtime_error(
                "exposure reservation does not match simulation order intent");
        }

        if (!exposure_reservations_.emplace(
                order_id,
                ExposureReservationRecord{
                    symbol,
                    action,
                    side,
                    quantity,
                    notional,
                    reserved_available_balance,
                    margin_reservation_rate,
                    position_slot,
                    true,
                }).second) {
            throw std::runtime_error(
                "duplicate exposure reservation creation");
        }
        ++exposure_reservation_create_count_;
    }

    void replay_exposure_reservation_released_unlocked(
        const astu::ipc::JsonObject& obj) {
        const auto order_id =
            astu::ipc::require_string(obj, "simulationOrderId");
        const auto symbol =
            astu::ipc::require_string(obj, "symbol");
        const auto terminal_state =
            order_state_from_string(
                astu::ipc::require_string(
                    obj,
                    "terminalState"));
        const auto released_notional =
            astu::ipc::require_double(
                obj,
                "releasedGrossNotional");
        std::optional<double> released_available_balance;
        if (obj.find("releasedAvailableBalance") != obj.end()) {
            released_available_balance =
                astu::ipc::require_double(
                    obj,
                    "releasedAvailableBalance");
        }
        const bool released_position_slot =
            astu::ipc::require_bool(
                obj,
                "releasedPositionSlot");

        if (order_id.empty() || symbol.empty() ||
            !is_terminal_order_state(terminal_state) ||
            !std::isfinite(released_notional) ||
            released_notional <= 0.0 ||
            (released_available_balance.has_value() &&
             (!std::isfinite(*released_available_balance) ||
              *released_available_balance < 0.0)) ||
            !astu::ipc::require_bool(obj, "simulationOnly") ||
            astu::ipc::require_bool(
                obj,
                "exchangeSubmissionAttempted")) {
            throw std::runtime_error(
                "execution journal invalid exposure reservation release");
        }

        auto reservation_it =
            exposure_reservations_.find(order_id);
        if (reservation_it == exposure_reservations_.end()) {
            const auto intent_it = order_intents_.find(order_id);
            if (intent_it == order_intents_.end() ||
                !astu::core::increases_exposure(
                    intent_it->second.action)) {
                throw std::runtime_error(
                    "exposure reservation release without reservable simulation order intent");
            }
            const auto& intent = intent_it->second;
            const double reconstructed_available_balance =
                intent.notional *
                default_margin_reservation_rate_;
            exposure_reservations_.emplace(
                order_id,
                ExposureReservationRecord{
                    intent.symbol,
                    intent.action,
                    intent.side,
                    intent.quantity,
                    intent.notional,
                    reconstructed_available_balance,
                    default_margin_reservation_rate_,
                    reserves_new_position_slot(intent.action),
                    true,
                });
            ++exposure_reservation_reconstructed_count_;
            reservation_it =
                exposure_reservations_.find(order_id);
        }
        if (!reservation_it->second.active) {
            throw std::runtime_error(
                "exposure reservation release without active reservation");
        }
        const auto state_it = order_states_.find(order_id);
        if (state_it == order_states_.end() ||
            state_it->second.state != terminal_state) {
            throw std::runtime_error(
                "exposure reservation terminal state mismatch");
        }
        if (reservation_it->second.symbol != symbol ||
            std::fabs(
                reservation_it->second.reserved_gross_notional -
                released_notional) > 1e-9 ||
            (released_available_balance.has_value() &&
             std::fabs(
                 reservation_it->second.reserved_available_balance -
                 *released_available_balance) > 1e-9) ||
            reservation_it->second.reserves_position_slot !=
                released_position_slot) {
            throw std::runtime_error(
                "exposure reservation release amount mismatch");
        }

        reservation_it->second.active = false;
        ++exposure_reservation_release_count_;
    }

    void finalize_exposure_reservations_after_replay_unlocked() {
        for (auto& [order_id, reservation] :
             exposure_reservations_) {
            if (!reservation.active) {
                continue;
            }
            const auto intent_it = order_intents_.find(order_id);
            const auto state_it = order_states_.find(order_id);
            if (intent_it == order_intents_.end() ||
                state_it == order_states_.end()) {
                throw std::runtime_error(
                    "active exposure reservation missing persistent order state/intent");
            }
            if (is_terminal_order_state(state_it->second.state)) {
                reservation.active = false;
                ++exposure_reservation_implicit_release_count_;
            }
        }

        for (const auto& [order_id, intent] : order_intents_) {
            if (!astu::core::increases_exposure(intent.action) ||
                exposure_reservations_.contains(order_id)) {
                continue;
            }
            const auto state_it = order_states_.find(order_id);
            if (state_it == order_states_.end()) {
                throw std::runtime_error(
                    "simulation order intent missing order state during reservation recovery");
            }
            if (is_terminal_order_state(state_it->second.state)) {
                continue;
            }
            exposure_reservations_.emplace(
                order_id,
                ExposureReservationRecord{
                    intent.symbol,
                    intent.action,
                    intent.side,
                    intent.quantity,
                    intent.notional,
                    intent.notional *
                        default_margin_reservation_rate_,
                    default_margin_reservation_rate_,
                    reserves_new_position_slot(intent.action),
                    true,
                });
            ++exposure_reservation_reconstructed_count_;
        }
    }

    void replay_simulation_order_intent_unlocked(
        const astu::ipc::JsonObject& obj) {
        const auto order_id =
            astu::ipc::require_string(obj, "simulationOrderId");
        if (order_id.empty() ||
            !astu::ipc::require_bool(obj, "simulationOnly") ||
            astu::ipc::require_bool(obj, "orderRoutingEnabled") ||
            astu::ipc::require_bool(obj, "exchangeSubmissionAttempted") ||
            astu::ipc::require_double(obj, "quantity") <= 0.0 ||
            astu::ipc::require_double(obj, "referencePrice") <= 0.0 ||
            astu::ipc::require_double(obj, "notional") <= 0.0) {
            throw std::runtime_error(
                "execution journal invalid simulation order intent");
        }
        const auto action = astu::ipc::action_from_string(
            astu::ipc::require_string(obj, "action"));
        const auto side = astu::ipc::side_from_string(
            astu::ipc::require_string(obj, "side"));
        const SimulationOrderIntentRecord record{
            astu::ipc::require_string(obj, "requestId"),
            astu::ipc::require_string(obj, "idempotencyKey"),
            astu::ipc::require_string(obj, "signalId"),
            astu::ipc::require_string(obj, "symbol"),
            action,
            side,
            astu::ipc::require_double(obj, "quantity"),
            astu::ipc::require_double(obj, "referencePrice"),
            astu::ipc::require_double(obj, "notional"),
        };
        if (!order_intents_.emplace(order_id, record).second) {
            throw std::runtime_error(
                "execution journal duplicate simulation order intent");
        }
    }

    void replay_reconciliation_event_unlocked(
        const astu::ipc::JsonObject& obj) {
        const auto event_id =
            astu::ipc::require_string(obj, "eventId");
        const auto order_id =
            astu::ipc::require_string(obj, "simulationOrderId");
        const auto from_state =
            astu::ipc::require_string(obj, "fromState");
        const auto reconciliation_type =
            astu::ipc::require_string(obj, "reconciliationType");
        const auto to_state = astu::execution::order_state_from_string(
            astu::ipc::require_string(obj, "toState"));
        const auto expected_state =
            reconciliation_target_from_type_unlocked(
                reconciliation_type);
        if (to_state != expected_state) {
            throw std::runtime_error(
                "reconciliation type/toState mismatch");
        }
        const auto transition_sequence =
            astu::ipc::require_u64(obj, "transitionSequence");
        const auto reconciliation_sequence =
            astu::ipc::require_u64(obj, "reconciliationSequence");
        const auto cumulative_filled =
            astu::ipc::require_double(obj, "cumulativeFilledQuantity");
        const auto recorded_order_quantity =
            astu::ipc::require_double(obj, "orderQuantity");

        if (event_id.empty() || order_id.empty() ||
            reconciliation_type.empty() ||
            !astu::ipc::require_bool(obj, "simulationOnly") ||
            astu::ipc::require_bool(obj, "exchangeSubmissionAttempted")) {
            throw std::runtime_error(
                "execution journal invalid reconciliation event");
        }
        if (!reconciliation_event_ids_.insert(event_id).second) {
            throw std::runtime_error(
                "execution journal duplicate reconciliation event id");
        }

        const auto intent_it = order_intents_.find(order_id);
        if (intent_it == order_intents_.end()) {
            throw std::runtime_error(
                "reconciliation event missing simulation order intent");
        }
        if (std::fabs(
                recorded_order_quantity - intent_it->second.quantity) >
            1e-12) {
            throw std::runtime_error(
                "reconciliation event order quantity mismatch");
        }

        const auto state_it = order_states_.find(order_id);
        if (state_it == order_states_.end()) {
            throw std::runtime_error(
                "reconciliation event missing order state");
        }
        if (transition_sequence != state_it->second.sequence + 1 ||
            from_state != astu::execution::order_state_to_string(
                state_it->second.state)) {
            throw std::runtime_error(
                "reconciliation transition sequence/from-state mismatch");
        }
        astu::execution::OrderStateMachine::require_transition(
            state_it->second.state,
            to_state);

        const auto previous_progress =
            reconciliation_progress_.find(order_id);
        const double previous_filled =
            previous_progress == reconciliation_progress_.end()
                ? 0.0
                : previous_progress->second.cumulative_filled_quantity;
        const std::uint64_t expected_reconciliation_sequence =
            previous_progress == reconciliation_progress_.end()
                ? 1
                : previous_progress->second.sequence + 1;
        if (reconciliation_sequence != expected_reconciliation_sequence) {
            throw std::runtime_error(
                "reconciliation event sequence gap");
        }

        try {
            validate_reconciliation_quantity_unlocked(
                intent_it->second.quantity,
                previous_filled,
                cumulative_filled,
                to_state);
        } catch (const std::exception& exc) {
            throw std::runtime_error(
                "invalid reconciliation event quantity: " +
                std::string(exc.what()));
        }

        order_states_[order_id] =
            OrderRecoveryState{to_state, transition_sequence};
        reconciliation_progress_[order_id] =
            ReconciliationRecoveryState{
                reconciliation_sequence,
                cumulative_filled,
            };
        ++order_transition_count_;
        ++reconciliation_event_count_;
    }

    void replay_testnet_submission_attempt_unlocked(
        const astu::ipc::JsonObject& obj) {
        const auto order_id =
            astu::ipc::require_string(obj, "simulationOrderId");
        const auto client_order_id =
            astu::ipc::require_string(obj, "clientOrderId");
        const auto exchange_side =
            astu::ipc::require_string(obj, "exchangeSide");
        const auto quantity =
            astu::ipc::require_double(obj, "quantity");
        if (order_id.empty() ||
            client_order_id.empty() ||
            (exchange_side != "BUY" && exchange_side != "SELL") ||
            !std::isfinite(quantity) || quantity <= 0.0 ||
            astu::ipc::require_string(
                obj, "executionEnvironment") !=
                "BINANCE_USDM_TESTNET" ||
            !astu::ipc::require_bool(
                obj, "exchangeSubmissionAttempted")) {
            throw std::runtime_error(
                "invalid Testnet submission attempt journal event");
        }
        const auto state_it = order_states_.find(order_id);
        if (state_it == order_states_.end() ||
            state_it->second.state != OrderState::Submitting) {
            throw std::runtime_error(
                "Testnet submission attempt missing SUBMITTING state");
        }
        ++testnet_submission_attempt_count_;
    }

    void replay_order_transition_unlocked(
        const astu::ipc::JsonObject& obj) {
        const auto order_id =
            astu::ipc::require_string(obj, "simulationOrderId");
        const auto from_state =
            astu::ipc::require_string(obj, "fromState");
        const auto to_state = astu::execution::order_state_from_string(
            astu::ipc::require_string(obj, "toState"));
        const auto sequence =
            astu::ipc::require_u64(obj, "transitionSequence");
        const bool simulation_only =
            astu::ipc::require_bool(obj, "simulationOnly");
        const bool exchange_submission_attempted =
            astu::ipc::require_bool(obj, "exchangeSubmissionAttempted");
        std::string execution_environment = "SIMULATION_ONLY";
        if (obj.find("executionEnvironment") != obj.end()) {
            execution_environment =
                astu::ipc::require_string(
                    obj, "executionEnvironment");
        }
        const bool testnet_transition =
            !simulation_only &&
            exchange_submission_attempted &&
            execution_environment == "BINANCE_USDM_TESTNET" &&
            (to_state == OrderState::Submitting ||
             to_state == OrderState::Acknowledged ||
             to_state == OrderState::Rejected ||
             to_state == OrderState::UnknownReconcileRequired);
        if ((!simulation_only || exchange_submission_attempted) &&
            !testnet_transition) {
            throw std::runtime_error(
                "execution journal contains unauthorized routed order transition");
        }
        if (order_id.empty()) {
            throw std::runtime_error(
                "execution journal order transition has empty order id");
        }

        const auto existing = order_states_.find(order_id);
        if (existing == order_states_.end()) {
            if (sequence != 1 || from_state != "NONE" ||
                to_state != astu::execution::OrderState::IntentReceived) {
                throw std::runtime_error(
                    "execution journal invalid initial order transition");
            }
        } else {
            if (sequence != existing->second.sequence + 1) {
                throw std::runtime_error(
                    "execution journal order transition sequence gap");
            }
            if (from_state !=
                astu::execution::order_state_to_string(
                    existing->second.state)) {
                throw std::runtime_error(
                    "execution journal order transition fromState mismatch");
            }
            astu::execution::OrderStateMachine::require_transition(
                existing->second.state,
                to_state);
        }

        order_states_[order_id] = OrderRecoveryState{to_state, sequence};
        ++order_transition_count_;
    }

    static std::int64_t utc_now_ms() {
        const auto now = std::chrono::system_clock::now().time_since_epoch();
        return std::chrono::duration_cast<std::chrono::milliseconds>(now).count();
    }

    void remember_unlocked(const std::string& key) {
        if (replay_capacity_ == 0) {
            return;
        }
        if (order_.size() >= replay_capacity_) {
            seen_.erase(order_.front());
            order_.pop_front();
        }
        order_.push_back(key);
        seen_.insert(key);
    }

    void append_durable(const std::string& line) {
#ifdef _WIN32
        int fd = -1;
        const std::wstring wide = path_.wstring();
        const errno_t open_error = _wsopen_s(
            &fd,
            wide.c_str(),
            _O_WRONLY | _O_CREAT | _O_APPEND | _O_BINARY,
            _SH_DENYWR,
            _S_IREAD | _S_IWRITE);
        if (open_error != 0 || fd < 0) {
            throw std::runtime_error("open execution journal failed");
        }

        const char* ptr = line.data();
        std::size_t remaining = line.size();
        bool ok = true;
        while (remaining > 0) {
            const unsigned int chunk = static_cast<unsigned int>(
                remaining > 0x7fffffffU ? 0x7fffffffU : remaining);
            const int written = _write(fd, ptr, chunk);
            if (written <= 0) {
                ok = false;
                break;
            }
            ptr += written;
            remaining -= static_cast<std::size_t>(written);
        }
        if (ok) {
            ok = _commit(fd) == 0;
        }
        _close(fd);
        if (!ok) {
            throw std::runtime_error("durable execution journal append failed");
        }
#else
        std::ofstream out(path_, std::ios::binary | std::ios::app);
        if (!out) {
            throw std::runtime_error("cannot append execution journal");
        }
        out.write(line.data(), static_cast<std::streamsize>(line.size()));
        out.flush();
        if (!out) {
            throw std::runtime_error("execution journal append failed");
        }
#endif
    }

    std::filesystem::path path_;
    std::size_t replay_capacity_{100'000};
    double default_margin_reservation_rate_{0.0};
    mutable std::mutex mu_;
    std::deque<std::string> order_;
    std::unordered_set<std::string> seen_;
    std::unordered_map<std::string, OrderRecoveryState> order_states_;
    std::unordered_map<std::string, SimulationOrderIntentRecord> order_intents_;
    std::unordered_map<std::string, ReconciliationRecoveryState>
        reconciliation_progress_;
    std::unordered_set<std::string> reconciliation_event_ids_;
    std::unordered_map<std::string, ExposureReservationRecord>
        exposure_reservations_;
    std::uint64_t order_transition_count_{0};
    std::uint64_t reconciliation_event_count_{0};
    std::uint64_t exposure_reservation_create_count_{0};
    std::uint64_t exposure_reservation_release_count_{0};
    std::uint64_t exposure_reservation_implicit_release_count_{0};
    std::uint64_t exposure_reservation_reconstructed_count_{0};
    std::uint64_t testnet_submission_attempt_count_{0};
};

}  // namespace astu::execution
