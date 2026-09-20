#pragma once

#include <chrono>
#include <cmath>
#include <cstdint>
#include <deque>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>

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
        std::size_t replay_capacity = 100'000)
        : path_(std::move(path)),
          replay_capacity_(replay_capacity) {
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
            << ",\"orderRoutingEnabled\":false"
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
        std::string reason) {
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
            << ",\"simulationOnly\":true"
            << ",\"exchangeSubmissionAttempted\":false"
            << ",\"reason\":\"" << astu::ipc::json_escape(reason) << "\""
            << "}\n";

        append_durable(out.str());
        order_states_[simulation_order_id] = OrderRecoveryState{
            to_state,
            sequence,
        };
        ++order_transition_count_;
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
        if (!astu::ipc::require_bool(obj, "simulationOnly") ||
            astu::ipc::require_bool(obj, "exchangeSubmissionAttempted")) {
            throw std::runtime_error(
                "execution journal contains non-simulation order transition");
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
    mutable std::mutex mu_;
    std::deque<std::string> order_;
    std::unordered_set<std::string> seen_;
    std::unordered_map<std::string, OrderRecoveryState> order_states_;
    std::unordered_map<std::string, SimulationOrderIntentRecord> order_intents_;
    std::unordered_map<std::string, ReconciliationRecoveryState>
        reconciliation_progress_;
    std::unordered_set<std::string> reconciliation_event_ids_;
    std::uint64_t order_transition_count_{0};
    std::uint64_t reconciliation_event_count_{0};
};

}  // namespace astu::execution
