#include <array>
#include <cstddef>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <string>

#include "astu/account/live_risk_provider.hpp"
#include "astu/core/contracts.hpp"
#include "astu/execution/execution_journal.hpp"
#include "astu/execution/simulation_engine.hpp"
#include "astu/ipc/frame.hpp"
#include "astu/ipc/idempotency_cache.hpp"
#include "astu/ipc/simulation_protocol.hpp"
#include "astu/trade/signal_intent_builder.hpp"
#include "astu/wsrtd/data_status_adapter.hpp"
#include "astu/wsrtd/live_status_provider.hpp"

#define REQUIRE(...) do { \
    if (!(__VA_ARGS__)) { \
        std::cerr << "REQUIRE_FAILED line=" << __LINE__ << " expr=" << #__VA_ARGS__ << "\n"; \
        return 99; \
    } \
} while (0)

#define TRACE(name) do { std::cout << "TEST_TRACE=" << name << "\n" << std::flush; } while (0)

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
        REQUIRE(result.accepted_for_simulation);
        REQUIRE(result.code == DecisionCode::OrderRoutingDisabled);
        REQUIRE(result.simulated_quantity > 0.0);
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
        REQUIRE(!result.accepted_for_simulation);
        REQUIRE(result.code == DecisionCode::IdentityUnavailable);
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
        REQUIRE(result.accepted_for_simulation);
        REQUIRE(result.code == DecisionCode::OrderRoutingDisabled);
    }

    {
        auto data = ready_data();
        auto intent = astu::trade::SignalIntentBuilder(base_intent())
                          .bind_data_identity(data)
                          .build();
        intent.universe_id = "OTHER";
        auto result = astu::execution::SimulationEngine::run(
            intent, data, ready_risk(), 2'000);
        REQUIRE(!result.accepted_for_simulation);
        REQUIRE(result.code == DecisionCode::UniverseMismatch);
    }

    {
        auto data = ready_data();
        auto intent = astu::trade::SignalIntentBuilder(base_intent())
                          .bind_data_identity(data)
                          .build();
        intent.data_generation += 1;
        auto result = astu::execution::SimulationEngine::run(
            intent, data, ready_risk(), 2'000);
        REQUIRE(!result.accepted_for_simulation);
        REQUIRE(result.code == DecisionCode::DataGenerationMismatch);
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
        REQUIRE(!result.accepted_for_simulation);
        REQUIRE(result.code == DecisionCode::RiskBlocked);
    }

    {
        const std::string text = "{\"requestId\":\"REQ-1\",\"schemaVersion\":1}";
        const auto* raw = reinterpret_cast<const std::byte*>(text.data());
        auto encoded = astu::ipc::encode_frame(
            std::span<const std::byte>(raw, text.size()));
        auto decoded = astu::ipc::decode_frame(encoded);
        const std::string roundtrip(
            reinterpret_cast<const char*>(decoded.data()), decoded.size());
        REQUIRE(roundtrip == text);

        encoded.back() ^= std::byte{0x01};
        bool rejected = false;
        try {
            (void)astu::ipc::decode_frame(encoded);
        } catch (const std::invalid_argument&) {
            rejected = true;
        }
        REQUIRE(rejected);
    }

    {
        astu::ipc::IdempotencyCache cache(2);
        REQUIRE(cache.accept_once("REQ-1"));
        REQUIRE(!cache.accept_once("REQ-1"));
        REQUIRE(cache.accept_once("REQ-2"));
        REQUIRE(cache.accept_once("REQ-3"));
        REQUIRE(cache.size() == 2);
        REQUIRE(cache.accept_once("REQ-1"));
    }

    {
        auto data = ready_data();
        auto intent = astu::trade::SignalIntentBuilder(base_intent())
                          .bind_data_identity(data)
                          .build();

        astu::ipc::SimulationRequest request;
        request.request_id = "REQ-PROTOCOL-1";
        request.idempotency_key = "IDEMP-PROTOCOL-1";
        request.intent = intent;

        const std::string encoded = astu::ipc::encode_request_json(request);
        const auto decoded = astu::ipc::decode_request_json(encoded);
        REQUIRE(decoded.request_id == request.request_id);
        REQUIRE(decoded.idempotency_key == request.idempotency_key);
        REQUIRE(decoded.intent.signal_id == request.intent.signal_id);
        REQUIRE(decoded.intent.universe_id == request.intent.universe_id);
        REQUIRE(decoded.intent.universe_version == request.intent.universe_version);
        REQUIRE(decoded.intent.data_generation == request.intent.data_generation);

        astu::ipc::SimulationDispatcher dispatcher(
            [data](const astu::core::SignalIntent&) { return data; },
            [](const astu::core::SignalIntent&) { return ready_risk(); },
            4);

        const auto response1 = dispatcher.dispatch(request, 2'000);
        REQUIRE(response1.decision_code == DecisionCode::OrderRoutingDisabled);
        REQUIRE(response1.accepted_for_simulation);
        REQUIRE(!response1.simulation_order_id.empty());
        REQUIRE(response1.simulation_order_id.rfind("SIMORD-", 0) == 0);
        REQUIRE(!response1.order_routing_enabled);

        const std::string response_json = astu::ipc::encode_response_json(response1);
        const auto response_roundtrip = astu::ipc::decode_response_json(response_json);
        REQUIRE(response_roundtrip.request_id == request.request_id);
        REQUIRE(response_roundtrip.signal_id == request.intent.signal_id);
        REQUIRE(response_roundtrip.simulation_order_id ==
                response1.simulation_order_id);
        REQUIRE(response_roundtrip.decision_code == DecisionCode::OrderRoutingDisabled);
        REQUIRE(!response_roundtrip.order_routing_enabled);

        const auto response2 = dispatcher.dispatch(request, 2'000);
        REQUIRE(response2.decision_code == DecisionCode::DuplicateRequest);
        REQUIRE(!response2.accepted_for_simulation);
    }

    {
        astu::ipc::SimulationDispatcher dispatcher(
            [](const astu::core::SignalIntent&) { return ready_data(); },
            [](const astu::core::SignalIntent&) { return ready_risk(); });
        const auto response = dispatcher.dispatch_json("not-json", 2'000);
        REQUIRE(response.decision_code == DecisionCode::FrameInvalid);
        REQUIRE(!response.order_routing_enabled);
    }

    {
        TRACE("live_status_provider");
        const auto now_ms = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now().time_since_epoch()).count());
        const auto dir = std::filesystem::temp_directory_path() /
            "astu_live_status_provider_test";
        std::filesystem::create_directories(dir);
        const auto path = dir / "BTCUSDT.json";
        std::ofstream out(path, std::ios::binary | std::ios::trunc);
        out
            << "{"
            << "\"schemaVersion\":1,"
            << "\"source\":\"WSRTD-CleanRoomR2\","
            << "\"symbol\":\"BTCUSDT\","
            << "\"generatedUnixMs\":" << now_ms << ","
            << "\"live\":true,"
            << "\"fresh\":true,"
            << "\"cacheReady\":true,"
            << "\"identityReady\":true,"
            << "\"universeId\":\"wsrtd-r2-bootstrap\","
            << "\"universeVersion\":1,"
            << "\"universeHash\":\"d31527c87e0aa41edc0fe81c7c16aafcdadaec976bf0455ad886cf4b81c502e0\","
            << "\"dataGeneration\":1789824780000,"
            << "\"generationKind\":\"WSRTD_R2_COMPLETED_M1_OPEN_MS\","
            << "\"cacheEod\":300,"
            << "\"cacheIntraday\":1500,"
            << "\"quoteAgeMs\":100,"
            << "\"detail\":\"WSRTD runtime data/identity ready\""
            << "}";
        out.close();

        astu::wsrtd::LiveStatusProvider provider(dir, 5'000);
        auto seed = base_intent();
        auto data = provider(seed);
        REQUIRE(data.live);
        REQUIRE(data.fresh);
        REQUIRE(data.cache_ready);
        REQUIRE(data.identity_ready);
        REQUIRE(data.universe_id.has_value());
        REQUIRE(*data.universe_id == "wsrtd-r2-bootstrap");
        REQUIRE(data.universe_version.has_value() && *data.universe_version == 1);
        REQUIRE(data.data_generation.has_value() &&
               *data.data_generation == 1'789'824'780'000ULL);

        auto intent = astu::trade::SignalIntentBuilder(seed)
                          .bind_data_identity(data)
                          .build();
        auto result = astu::execution::SimulationEngine::run(
            intent, data, ready_risk(), 2'000);
        REQUIRE(result.code == DecisionCode::OrderRoutingDisabled);

        std::filesystem::remove_all(dir);
    }

    {
        TRACE("live_status_provider_stale");
        const auto now_ms = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now().time_since_epoch()).count());
        const auto dir = std::filesystem::temp_directory_path() /
            "astu_live_status_provider_stale_test";
        std::filesystem::remove_all(dir);
        std::filesystem::create_directories(dir);
        const auto path = dir / "BTCUSDT.json";

        std::ofstream out(path, std::ios::binary | std::ios::trunc);
        out
            << "{"
            << "\"schemaVersion\":1,"
            << "\"source\":\"WSRTD-CleanRoomR2\","
            << "\"symbol\":\"BTCUSDT\","
            << "\"generatedUnixMs\":" << (now_ms - 60'000) << ","
            << "\"live\":true,"
            << "\"fresh\":true,"
            << "\"cacheReady\":true,"
            << "\"identityReady\":true,"
            << "\"universeId\":\"wsrtd-r2-bootstrap\","
            << "\"universeVersion\":1,"
            << "\"universeHash\":\"d31527c87e0aa41edc0fe81c7c16aafcdadaec976bf0455ad886cf4b81c502e0\","
            << "\"dataGeneration\":1789824780000,"
            << "\"generationKind\":\"WSRTD_R2_COMPLETED_M1_OPEN_MS\","
            << "\"cacheEod\":300,"
            << "\"cacheIntraday\":1500,"
            << "\"quoteAgeMs\":100,"
            << "\"detail\":\"fixture claims ready but snapshot is stale\""
            << "}";
        out.close();

        astu::wsrtd::LiveStatusProvider provider(dir, 5'000);
        const auto data = provider(base_intent());
        REQUIRE(!data.live);
        REQUIRE(!data.fresh);
        REQUIRE(!data.cache_ready);
        REQUIRE(!data.identity_ready);
        REQUIRE(data.detail == "runtime DataStatus snapshot stale");

        std::filesystem::remove_all(dir);
    }

    {
        const auto dir = std::filesystem::temp_directory_path() /
            "astu_live_status_provider_missing_test";
        std::filesystem::remove_all(dir);
        astu::wsrtd::LiveStatusProvider provider(dir, 5'000);
        auto data = provider(base_intent());
        REQUIRE(!data.live);
        REQUIRE(!data.fresh);
        REQUIRE(!data.cache_ready);
        REQUIRE(!data.identity_ready);
    }

    {
        TRACE("live_risk_provider");
        const auto now_ms = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now().time_since_epoch()).count());
        const auto dir = std::filesystem::temp_directory_path() /
            "astu_live_risk_provider_test";
        std::filesystem::remove_all(dir);
        std::filesystem::create_directories(dir);
        const auto path = dir / "account_risk_status.v1.json";

        std::ofstream out(path, std::ios::binary | std::ios::trunc);
        out
            << "{"
            << "\"schemaVersion\":1,"
            << "\"messageType\":\"AccountRiskSnapshot.v1\","
            << "\"generatedUnixMs\":" << now_ms << ","
            << "\"source\":\"TEST_RECONCILER\","
            << "\"reconciled\":true,"
            << "\"riskState\":\"NORMAL\","
            << "\"riskCapital\":10000,"
            << "\"availableBalance\":9000,"
            << "\"marginBalance\":10250,"
            << "\"initialMargin\":100,"
            << "\"grossNotional\":1000,"
            << "\"netDirectionalNotional\":1000,"
            << "\"maxGrossNotional\":50000,"
            << "\"openPositions\":1,"
            << "\"maxOpenPositions\":10,"
            << "\"detail\":\"reconciled test snapshot\""
            << "}";
        out.close();

        astu::account::LiveRiskProvider provider(path, 5'000);
        const auto risk = provider(base_intent());
        REQUIRE(risk.reconciled);
        REQUIRE(risk.risk_state == astu::core::RiskState::Normal);
        REQUIRE(risk.risk_capital == 10'000.0);
        REQUIRE(risk.available_balance == 9'000.0);
        REQUIRE(risk.margin_metrics_reconciled);
        REQUIRE(risk.margin_balance == 10'250.0);
        REQUIRE(risk.initial_margin == 100.0);
        REQUIRE(risk.gross_notional == 1'000.0);
        REQUIRE(risk.net_directional_reconciled);
        REQUIRE(risk.net_directional_notional == 1'000.0);
        REQUIRE(risk.max_gross_notional == 50'000.0);
        REQUIRE(risk.open_positions == 1);
        REQUIRE(risk.max_open_positions == 10);

        std::filesystem::remove_all(dir);
    }

    {
        const auto path = std::filesystem::temp_directory_path() /
            "astu_missing_account_risk_status.v1.json";
        std::filesystem::remove(path);
        astu::account::LiveRiskProvider provider(path, 5'000);
        const auto risk = provider(base_intent());
        REQUIRE(!risk.reconciled);
        REQUIRE(risk.risk_state == astu::core::RiskState::Emergency);

        auto data = ready_data();
        auto intent = astu::trade::SignalIntentBuilder(base_intent())
                          .bind_data_identity(data)
                          .build();
        const auto result = astu::execution::SimulationEngine::run(
            intent, data, risk, 2'000);
        REQUIRE(result.code == DecisionCode::AccountNotReconciled);
        REQUIRE(!result.accepted_for_simulation);
    }

    {
        TRACE("execution_journal");
        const auto dir = std::filesystem::temp_directory_path() /
            "astu_execution_journal_test";
        std::filesystem::remove_all(dir);
        std::filesystem::create_directories(dir);
        const auto journal_path = dir / "execution_journal.v1.jsonl";

        auto data = ready_data();
        auto intent = astu::trade::SignalIntentBuilder(base_intent())
                          .bind_data_identity(data)
                          .build();

        astu::ipc::SimulationRequest request;
        request.request_id = "REQ-JOURNAL-1";
        request.idempotency_key = "IDEMP-JOURNAL-1";
        request.intent = intent;

        {
            TRACE("execution_journal_create_1");
            auto journal = std::make_shared<astu::execution::ExecutionJournal>(
                journal_path, 100);
            TRACE("execution_journal_created_1");
            astu::ipc::SimulationDispatcher dispatcher(
                [data](const astu::core::SignalIntent&) { return data; },
                [](const astu::core::SignalIntent&) { return ready_risk(); },
                4,
                [journal](const std::string& key) {
                    return journal->accept_idempotency_key(key);
                },
                [journal](
                    const astu::ipc::SimulationRequest& req,
                    const astu::ipc::SimulationResponse& response,
                    std::int64_t utc_ms) {
                    journal->append(req, response, utc_ms);
                });

            TRACE("execution_journal_dispatch_1");
            const auto response = dispatcher.dispatch(request, 2'000);
            TRACE("execution_journal_dispatched_1");
            REQUIRE(response.decision_code == DecisionCode::OrderRoutingDisabled);
            REQUIRE(journal->replay_size() == 1);
        }

        {
            TRACE("execution_journal_create_2");
            auto journal = std::make_shared<astu::execution::ExecutionJournal>(
                journal_path, 100);
            TRACE("execution_journal_created_2");
            REQUIRE(journal->replay_size() == 1);

            astu::ipc::SimulationDispatcher dispatcher(
                [data](const astu::core::SignalIntent&) { return data; },
                [](const astu::core::SignalIntent&) { return ready_risk(); },
                4,
                [journal](const std::string& key) {
                    return journal->accept_idempotency_key(key);
                },
                [journal](
                    const astu::ipc::SimulationRequest& req,
                    const astu::ipc::SimulationResponse& response,
                    std::int64_t utc_ms) {
                    journal->append(req, response, utc_ms);
                });

            TRACE("execution_journal_dispatch_2");
            const auto replay = dispatcher.dispatch(request, 2'100);
            TRACE("execution_journal_dispatched_2");
            REQUIRE(replay.decision_code == DecisionCode::DuplicateRequest);
            REQUIRE(!replay.accepted_for_simulation);
        }

        TRACE("execution_journal_readback");
        std::ifstream journal_in(journal_path, std::ios::binary);
        const std::string journal_text(
            (std::istreambuf_iterator<char>(journal_in)),
            std::istreambuf_iterator<char>());
        REQUIRE(journal_text.find("IDEMPOTENCY_RESERVATION") != std::string::npos);
        REQUIRE(journal_text.find("SIMULATION_DECISION") != std::string::npos);
        REQUIRE(journal_text.find("ORDER_ROUTING_DISABLED") != std::string::npos);
        REQUIRE(journal_text.find("DUPLICATE_REQUEST") != std::string::npos);
        journal_in.close();

        TRACE("execution_journal_remove");
        std::filesystem::remove_all(dir);
        TRACE("execution_journal_done");
    }

    TRACE("complete");
    std::cout << "astu_core_tests PASS\n";
    return 0;
}
