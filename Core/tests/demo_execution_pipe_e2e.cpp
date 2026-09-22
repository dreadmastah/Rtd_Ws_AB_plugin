#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <span>
#include <sstream>
#include <string>

#include "astu/execution/execution_journal.hpp"
#include "astu/execution/order_fsm.hpp"
#include "astu/ipc/demo_execution_protocol.hpp"
#include "astu/ipc/frame.hpp"
#include "astu/ipc/named_pipe.hpp"
#include "astu/ipc/simulation_protocol.hpp"

namespace {

std::uint64_t now_ms() {
    const auto now =
        std::chrono::system_clock::now().time_since_epoch();
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<
            std::chrono::milliseconds>(now).count());
}

struct Options {
    bool prepare{false};
    bool stale{false};
    std::filesystem::path journal;
    std::filesystem::path convergence;
    std::string case_name{"valid"};
};

Options parse_args(int argc, char** argv) {
    Options out;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        auto value = [&](const char* name) -> std::string {
            if (i + 1 >= argc) {
                throw std::invalid_argument(
                    std::string(name) + " requires a value");
            }
            return argv[++i];
        };
        if (arg == "--prepare") {
            out.prepare = true;
        } else if (arg == "--stale") {
            out.stale = true;
        } else if (arg == "--journal") {
            out.journal = value("--journal");
        } else if (arg == "--convergence") {
            out.convergence = value("--convergence");
        } else if (arg == "--case") {
            out.case_name = value("--case");
        } else {
            throw std::invalid_argument(
                "unknown argument: " + arg);
        }
    }
    if (out.journal.empty() || out.convergence.empty()) {
        throw std::invalid_argument(
            "--journal and --convergence are required");
    }
    return out;
}

astu::ipc::SimulationRequest simulation_request() {
    astu::ipc::SimulationRequest request;
    request.request_id = "DEMO-E2E-SIM-REQ-1";
    request.idempotency_key = "DEMO-E2E-SIM-IDEM-1";
    request.intent.signal_id = "DEMO-E2E-SIGNAL-1";
    request.intent.analysis_run_id = "DEMO-E2E-AA-1";
    request.intent.strategy_id = "demo-e2e";
    request.intent.strategy_version = "1";
    request.intent.universe_id = "wsrtd-r2-bootstrap";
    request.intent.universe_version = 1;
    request.intent.symbol = "BTCUSDT";
    request.intent.action = astu::core::SignalAction::Buy;
    request.intent.side = astu::core::PositionSide::Long;
    request.intent.source_periodicity = "M1";
    request.intent.source_bar_time_utc_ms = 1;
    request.intent.signal_time_utc_ms = 2;
    request.intent.trigger_price = 100.0;
    request.intent.valid_from_utc_ms = 1;
    request.intent.expires_utc_ms = 9'999'999'999'999LL;
    request.intent.quantity_model = "DEMO_E2E_FIXTURE";
    request.intent.priority_score = 0.0;
    request.intent.data_generation = 1;
    return request;
}

void write_convergence(
    const std::filesystem::path& path,
    bool stale) {
    if (!path.parent_path().empty()) {
        std::filesystem::create_directories(
            path.parent_path());
    }
    const auto now = now_ms();
    const auto generated =
        stale && now > 30'000 ? now - 30'000 : now;
    std::ofstream out(path, std::ios::trunc);
    if (!out) {
        throw std::runtime_error(
            "cannot create convergence fixture");
    }
    out
        << "{"
        << "\"schemaVersion\":1,"
        << "\"messageType\":\"TestnetUserDataState.v1\","
        << "\"generatedUnixMs\":" << generated << ","
        << "\"source\":\"BINANCE_USDM_TESTNET_USER_DATA\","
        << "\"ready\":true,"
        << "\"streamAlive\":true,"
        << "\"streamEpoch\":1,"
        << "\"connectedUnixMs\":" << generated << ","
        << "\"lastFrameUnixMs\":" << generated << ","
        << "\"lastEventUnixMs\":" << generated << ","
        << "\"livenessAgeMs\":0,"
        << "\"maxLivenessAgeMs\":15000,"
        << "\"eventCount\":3,"
        << "\"orderEventCount\":1,"
        << "\"accountEventCount\":1,"
        << "\"ignoredOrderEventCount\":0,"
        << "\"listenKeyExpiredCount\":0,"
        << "\"expired\":false,"
        << "\"orderingOk\":true,"
        << "\"lastAccountEventTimeMs\":" << generated << ","
        << "\"lastAccountReason\":\"ORDER\","
        << "\"accountRestGeneratedUnixMs\":" << generated << ","
        << "\"accountConverged\":true,"
        << "\"positionsConverged\":true,"
        << "\"ordersConverged\":true,"
        << "\"resolvedAstuOrders\":0,"
        << "\"unresolvedAstuOrders\":0,"
        << "\"restFallbackRequired\":false,"
        << "\"lastOrderClientId\":\"\","
        << "\"lastOrderSymbol\":\"\","
        << "\"lastOrderExchangeStatus\":\"\","
        << "\"lastOrderCumulativeFilledQuantity\":0,"
        << "\"detail\":\"Demo E2E fixture\""
        << "}\n";
}

void prepare(
    const std::filesystem::path& journal_path,
    const std::filesystem::path& convergence_path,
    bool stale) {
    std::error_code ec;
    std::filesystem::remove(journal_path, ec);
    if (!journal_path.parent_path().empty()) {
        std::filesystem::create_directories(
            journal_path.parent_path());
    }

    astu::execution::ExecutionJournal journal(journal_path);
    const auto request = simulation_request();

    astu::ipc::SimulationResponse response;
    response.request_id = request.request_id;
    response.signal_id = request.intent.signal_id;
    response.simulation_order_id = "DEMO-E2E-SIM-ORDER-1";
    response.decision_code =
        astu::core::DecisionCode::OrderRoutingDisabled;
    response.accepted_for_simulation = true;
    response.would_increase_exposure = true;
    response.simulated_quantity = 0.1;
    response.simulated_notional = 10.0;
    response.order_routing_enabled = false;
    response.execution_environment = "SIMULATION_ONLY";

    journal.append_simulation_order_intent(
        request, response, 1);
    journal.append_order_transition(
        request,
        response.simulation_order_id,
        astu::execution::OrderState::IntentReceived,
        2,
        "Demo E2E seed");
    journal.append_order_transition(
        request,
        response.simulation_order_id,
        astu::execution::OrderState::Validating,
        3,
        "Demo E2E seed");
    journal.append_order_transition(
        request,
        response.simulation_order_id,
        astu::execution::OrderState::RiskApproved,
        4,
        "Demo E2E seed");
    journal.append_order_transition(
        request,
        response.simulation_order_id,
        astu::execution::OrderState::Sizing,
        5,
        "Demo E2E seed");

    write_convergence(convergence_path, stale);
}

std::string required_token() {
    const char* raw =
        std::getenv("ASTU_DEMO_EXECUTION_CAPABILITY_TOKEN");
    if (raw == nullptr) {
        throw std::runtime_error(
            "ASTU_DEMO_EXECUTION_CAPABILITY_TOKEN missing");
    }
    return raw;
}

bool journal_has_submission_attempt(
    const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    std::ostringstream text;
    text << in.rdbuf();
    const auto body = text.str();
    return
        body.find("TESTNET_ORDER_SUBMISSION_ATTEMPT") !=
            std::string::npos ||
        body.find("\"exchangeSubmissionAttempted\":true") !=
            std::string::npos;
}

int send_case(
    const Options& options) {
#ifndef _WIN32
    (void)options;
    std::cerr
        << "Demo Named Pipe E2E requires Windows.\n";
    return 2;
#else
    auto token = required_token();
    astu::ipc::DemoExecutionRequest request;
    request.request_id =
        "DEMO-E2E-REQ-" + options.case_name;
    request.idempotency_key =
        "DEMO-E2E-IDEM-" + options.case_name;
    request.source_simulation_order_id =
        "DEMO-E2E-SIM-ORDER-1";
    request.signal_id = "DEMO-E2E-SIGNAL-1";
    request.symbol = "BTCUSDT";
    request.side = "LONG";
    request.quantity = 0.1;
    request.reduce_only = false;
    request.created_unix_ms = now_ms();
    request.expires_unix_ms =
        request.created_unix_ms + 5'000;
    request.capability_id = "demo-execution-v1";
    request.capability_token = token;

    astu::ipc::DemoAdmissionCode expected =
        astu::ipc::DemoAdmissionCode::RoutingNotImplemented;

    if (options.case_name == "bad-source") {
        request.source_simulation_order_id =
            "DEMO-E2E-MISSING-ORDER";
        expected =
            astu::ipc::DemoAdmissionCode::SourceRejected;
    } else if (options.case_name == "bad-capability") {
        request.capability_token =
            "ffffffffffffffffffffffffffffffff"
            "ffffffffffffffffffffffffffffffff";
        expected =
            astu::ipc::DemoAdmissionCode::CapabilityRejected;
    } else if (options.case_name == "stale-convergence") {
        expected =
            astu::ipc::DemoAdmissionCode::ConvergenceRejected;
    } else if (options.case_name != "valid") {
        throw std::invalid_argument(
            "unsupported case: " + options.case_name);
    }

    const auto json =
        astu::ipc::encode_demo_execution_request_json(request);
    const auto* raw =
        reinterpret_cast<const std::byte*>(json.data());
    const auto frame =
        astu::ipc::encode_frame(
            std::span<const std::byte>(
                raw,
                json.size()));

    astu::ipc::NamedPipeClient client(
        astu::ipc::kDemoExecutionPipeName);
    const auto response_frame =
        client.request(frame, 10'000);
    const auto payload =
        astu::ipc::decode_frame(response_frame);
    const std::string response_json(
        reinterpret_cast<const char*>(payload.data()),
        payload.size());
    const auto response =
        astu::ipc::decode_demo_execution_response_json(
            response_json);

    token.assign(token.size(), '\0');
    token.clear();

    if (response.request_id != request.request_id ||
        response.source_simulation_order_id !=
            request.source_simulation_order_id) {
        std::cerr << "response correlation mismatch\n";
        return 10;
    }
    if (response.decision_code != expected) {
        std::cerr
            << "unexpected decision="
            << astu::ipc::demo_admission_code_to_string(
                   response.decision_code)
            << " expected="
            << astu::ipc::demo_admission_code_to_string(
                   expected)
            << " reason=" << response.reason << "\n";
        return 11;
    }
    if (response.accepted_for_execution ||
        response.order_submission_attempted ||
        !response.exchange_client_order_id.empty() ||
        !response.exchange_order_id.empty() ||
        !response.exchange_order_status.empty()) {
        std::cerr
            << "response indicates forbidden submission state\n";
        return 12;
    }
    if (response_json.find("capabilityToken") !=
            std::string::npos) {
        std::cerr
            << "capability token field leaked to response\n";
        return 13;
    }
    if (journal_has_submission_attempt(options.journal)) {
        std::cerr
            << "journal contains submission-attempt evidence\n";
        return 14;
    }

    std::cout
        << "DEMO_PIPE_CASE=" << options.case_name
        << " DECISION="
        << astu::ipc::demo_admission_code_to_string(
               response.decision_code)
        << " SUBMISSION_ATTEMPTED=false\n";
    return 0;
#endif
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const auto options = parse_args(argc, argv);
        if (options.prepare) {
            prepare(
                options.journal,
                options.convergence,
                options.stale);
            std::cout
                << "DEMO_PIPE_FIXTURE=READY stale="
                << (options.stale ? "true" : "false")
                << "\n";
            return 0;
        }
        return send_case(options);
    } catch (const std::exception& exc) {
        std::cerr
            << "Demo pipe E2E failed: "
            << exc.what() << "\n";
        return 2;
    }
}
