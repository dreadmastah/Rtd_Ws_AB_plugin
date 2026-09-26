#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <utility>

#include "astu/core/contracts.hpp"
#include "astu/ipc/simulation_protocol.hpp"
#include "astu/trade/amibroker_abi_min.hpp"
#include "astu/trade/execution_pipe_client.hpp"
#include "astu/trade/signal_intent_builder.hpp"
#include "astu/wsrtd/live_status_provider.hpp"

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace {

using astu::trade::amibroker::AmiVar;
using astu::trade::amibroker::FunctionTag;
using astu::trade::amibroker::PluginInfo;
using astu::trade::amibroker::SiteInterface;

std::atomic<unsigned long long> gSequence{0};
std::atomic<int> gLastDecision{
    static_cast<int>(astu::core::DecisionCode::FrameInvalid)};
std::mutex gPipeMutex;
SiteInterface gSite{};

constexpr int kPluginVersion = 10000;
constexpr int kMinAmiBrokerVersion = 530000;

AmiVar float_result(float value) {
    AmiVar result{};
    result.type = astu::trade::amibroker::VarFloat;
    result.val = value;
    return result;
}

std::int64_t utc_now_ms() {
    const auto now = std::chrono::system_clock::now().time_since_epoch();
    return std::chrono::duration_cast<std::chrono::milliseconds>(now).count();
}

std::string bounded_string(const char* text, std::size_t max_len) {
    if (!text) {
        return {};
    }
    std::string out(text);
    if (out.size() > max_len) {
        out.resize(max_len);
    }
    return out;
}

std::string environment_value(const char* name) {
#ifdef _WIN32
    const DWORD required = GetEnvironmentVariableA(name, nullptr, 0);
    if (required == 0) {
        return {};
    }
    std::string value(static_cast<std::size_t>(required), '\0');
    const DWORD written = GetEnvironmentVariableA(
        name,
        value.data(),
        required);
    if (written == 0 || written >= required) {
        return {};
    }
    value.resize(written);
    return value;
#else
    const char* raw = std::getenv(name);
    return raw ? std::string(raw) : std::string{};
#endif
}

void write_diagnostic(const std::string& text) noexcept {
    try {
        const std::string raw = environment_value("ASTU_TRADE_DIAGNOSTIC_FILE");
        if (raw.empty()) {
            return;
        }
        const std::filesystem::path path(raw);
        if (!path.parent_path().empty()) {
            std::filesystem::create_directories(path.parent_path());
        }
        std::ofstream out(path, std::ios::binary | std::ios::app);
        if (out) {
            out << text.substr(0, 1024) << "\n";
        }
    } catch (...) {
    }
}

std::filesystem::path status_dir_from_environment() {
    const std::string raw = environment_value("ASTU_STATUS_DIR");
    if (raw.empty()) {
        throw std::runtime_error(
            "ASTU_STATUS_DIR is required for AstuTrade live DataStatus binding");
    }
    return std::filesystem::path(raw);
}

AmiVar astu_version(int, AmiVar*) {
    return float_result(static_cast<float>(kPluginVersion));
}

AmiVar astu_last_decision(int, AmiVar*) {
    return float_result(static_cast<float>(gLastDecision.load()));
}

AmiVar astu_simulate(int num_args, AmiVar* args) {
    using astu::core::DecisionCode;

    if (num_args != 8 || !args) {
        gLastDecision.store(static_cast<int>(DecisionCode::InvalidIntent));
        return float_result(static_cast<float>(
            static_cast<int>(DecisionCode::InvalidIntent)));
    }

    for (int i = 0; i < 6; ++i) {
        if (args[i].type != astu::trade::amibroker::VarString) {
            gLastDecision.store(static_cast<int>(DecisionCode::InvalidIntent));
            return float_result(static_cast<float>(
                static_cast<int>(DecisionCode::InvalidIntent)));
        }
    }
    if (args[6].type != astu::trade::amibroker::VarFloat ||
        args[7].type != astu::trade::amibroker::VarFloat) {
        gLastDecision.store(static_cast<int>(DecisionCode::InvalidIntent));
        return float_result(static_cast<float>(
            static_cast<int>(DecisionCode::InvalidIntent)));
    }

    try {
        const std::string symbol = bounded_string(args[0].string, 32);
        const std::string action_text = bounded_string(args[1].string, 16);
        const std::string side_text = bounded_string(args[2].string, 16);
        const std::string strategy_id = bounded_string(args[3].string, 128);
        const std::string strategy_version = bounded_string(args[4].string, 64);
        const std::string periodicity = bounded_string(args[5].string, 32);
        const double trigger_price = static_cast<double>(args[6].val);
        const double validity_seconds = static_cast<double>(args[7].val);

        if (symbol.empty() || strategy_id.empty() || strategy_version.empty() ||
            periodicity.empty() || !std::isfinite(trigger_price) ||
            trigger_price <= 0.0 || !std::isfinite(validity_seconds) ||
            validity_seconds < 1.0 || validity_seconds > 3600.0) {
            gLastDecision.store(static_cast<int>(DecisionCode::InvalidIntent));
            return float_result(static_cast<float>(
                static_cast<int>(DecisionCode::InvalidIntent)));
        }

        const auto action = astu::ipc::action_from_string(action_text);
        const auto side = astu::ipc::side_from_string(side_text);
        const auto now_ms = utc_now_ms();
        const auto sequence = ++gSequence;

        astu::core::SignalIntent seed;
        seed.signal_id =
            "AB-" + std::to_string(now_ms) + "-" + std::to_string(sequence);
        seed.analysis_run_id =
            "ABRUN-" + std::to_string(now_ms) + "-" + std::to_string(sequence);
        seed.strategy_id = strategy_id;
        seed.strategy_version = strategy_version;
        seed.symbol = symbol;
        seed.action = action;
        seed.side = side;
        seed.source_periodicity = periodicity;
        seed.signal_time_utc_ms = now_ms;
        seed.trigger_price = trigger_price;
        seed.valid_from_utc_ms = now_ms;
        seed.expires_utc_ms =
            now_ms + static_cast<std::int64_t>(validity_seconds * 1000.0);
        seed.quantity_model = "SYNTHETIC_TEST_ONLY";
        seed.priority_score = 0.0;

        astu::wsrtd::LiveStatusProvider status_provider(
            status_dir_from_environment(),
            5'000);
        const auto data = status_provider(seed);
        if (!data.identity_ready || !data.data_generation.has_value()) {
            gLastDecision.store(static_cast<int>(DecisionCode::IdentityUnavailable));
            return float_result(static_cast<float>(
                static_cast<int>(DecisionCode::IdentityUnavailable)));
        }

        seed.source_bar_time_utc_ms =
            static_cast<std::int64_t>(*data.data_generation);

        astu::ipc::SimulationRequest request;
        request.request_id = "REQ-" + seed.signal_id;
        request.idempotency_key = seed.signal_id;
        request.intent = astu::trade::SignalIntentBuilder(std::move(seed))
                             .bind_data_identity(data)
                             .build();

        astu::ipc::SimulationResponse response;
        {
            std::lock_guard<std::mutex> lock(gPipeMutex);
            astu::trade::ExecutionPipeClient client;
            response = client.send(request);
        }

        gLastDecision.store(static_cast<int>(response.decision_code));
        return float_result(
            static_cast<float>(static_cast<int>(response.decision_code)));
    } catch (const std::exception& exc) {
        write_diagnostic(std::string("AstuSimulate exception: ") + exc.what());
        gLastDecision.store(static_cast<int>(DecisionCode::FrameInvalid));
        return float_result(
            static_cast<float>(static_cast<int>(DecisionCode::FrameInvalid)));
    }
}

char kNameAstuSimulate[] = "AstuSimulate";
char kNameAstuVersion[] = "AstuVersion";
char kNameAstuLastDecision[] = "AstuLastDecision";

FunctionTag gFunctionTable[] = {
    {
        kNameAstuSimulate,
        {astu_simulate, 0, 6, 2, 0, nullptr},
    },
    {
        kNameAstuVersion,
        {astu_version, 0, 0, 0, 0, nullptr},
    },
    {
        kNameAstuLastDecision,
        {astu_last_decision, 0, 0, 0, 0, nullptr},
    },
};

constexpr int kFunctionTableSize =
    static_cast<int>(sizeof(gFunctionTable) / sizeof(gFunctionTable[0]));

}  // namespace

ASTU_AMIBROKER_EXPORT int GetPluginInfo(PluginInfo* info) {
    if (!info) {
        return 0;
    }
    *info = {};
    info->nStructSize = sizeof(PluginInfo);
    info->nType = astu::trade::amibroker::kPluginTypeAfl;
    info->nVersion = kPluginVersion;
    info->nIDCode = 0;
    info->nCertificate = 0;
    info->nMinAmiVersion = kMinAmiBrokerVersion;
#ifdef _WIN32
    strncpy_s(
        info->szName,
        sizeof(info->szName),
        "AstuTrade Simulation Bridge",
        _TRUNCATE);
    strncpy_s(
        info->szVendor,
        sizeof(info->szVendor),
        "dreadmastah",
        _TRUNCATE);
#else
    std::snprintf(
        info->szName,
        sizeof(info->szName),
        "%s",
        "AstuTrade Simulation Bridge");
    std::snprintf(
        info->szVendor,
        sizeof(info->szVendor),
        "%s",
        "dreadmastah");
#endif
    return 1;
}

ASTU_AMIBROKER_EXPORT int SetSiteInterface(SiteInterface* site) {
    if (!site || site->nStructSize < static_cast<int>(sizeof(SiteInterface))) {
        return 0;
    }
    gSite = *site;
    return 1;
}

ASTU_AMIBROKER_EXPORT int GetFunctionTable(FunctionTag** table) {
    if (!table) {
        return 0;
    }
    *table = gFunctionTable;
    return kFunctionTableSize;
}

ASTU_AMIBROKER_EXPORT int Init() {
    return 1;
}

ASTU_AMIBROKER_EXPORT int Release() {
    return 1;
}
