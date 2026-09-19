#pragma once

#include <atomic>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

#include "astu/ipc/flat_json.hpp"
#include "astu/ipc/simulation_protocol.hpp"

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace astu::execution {

class ExecutionStatusPublisher {
public:
    ExecutionStatusPublisher(
        std::filesystem::path path,
        std::string data_provider,
        std::string risk_provider,
        std::string instrument_provider,
        bool instrument_rules_required,
        std::string journal_path)
        : path_(std::move(path)),
          data_provider_(std::move(data_provider)),
          risk_provider_(std::move(risk_provider)),
          instrument_provider_(std::move(instrument_provider)),
          instrument_rules_required_(instrument_rules_required),
          journal_path_(std::move(journal_path)) {}

    void set_ready(bool journal_ready, bool pipe_ready) {
        std::lock_guard<std::mutex> lock(mu_);
        lifecycle_state_ = "READY";
        journal_ready_ = journal_ready;
        pipe_ready_ = pipe_ready;
        detail_ = "simulation execution host ready";
    }

    void set_degraded(std::string detail) {
        std::lock_guard<std::mutex> lock(mu_);
        lifecycle_state_ = "DEGRADED";
        detail_ = std::move(detail);
    }

    void record_response(const astu::ipc::SimulationResponse& response) {
        requests_seen_.fetch_add(1, std::memory_order_relaxed);
        std::lock_guard<std::mutex> lock(mu_);
        last_decision_code_ = astu::ipc::decision_to_string(response.decision_code);
        detail_ = response.reason;
    }

    void publish() const {
        const auto generated_ms = utc_now_ms();

        std::string lifecycle;
        std::string detail;
        std::string last_decision;
        bool journal_ready = false;
        bool pipe_ready = false;
        {
            std::lock_guard<std::mutex> lock(mu_);
            lifecycle = lifecycle_state_;
            detail = detail_;
            last_decision = last_decision_code_;
            journal_ready = journal_ready_;
            pipe_ready = pipe_ready_;
        }

        std::ostringstream out;
        out
            << "{"
            << "\"schemaVersion\":1"
            << ",\"messageType\":\"ExecutionStatus.v1\""
            << ",\"generatedUnixMs\":" << generated_ms
            << ",\"processId\":" << process_id()
            << ",\"lifecycleState\":\"" << astu::ipc::json_escape(lifecycle) << "\""
            << ",\"dataProvider\":\"" << astu::ipc::json_escape(data_provider_) << "\""
            << ",\"riskProvider\":\"" << astu::ipc::json_escape(risk_provider_) << "\""
            << ",\"instrumentProvider\":\"" << astu::ipc::json_escape(instrument_provider_) << "\""
            << ",\"instrumentRulesRequired\":" << (instrument_rules_required_ ? "true" : "false")
            << ",\"journalPath\":\"" << astu::ipc::json_escape(journal_path_) << "\""
            << ",\"journalReady\":" << (journal_ready ? "true" : "false")
            << ",\"pipeReady\":" << (pipe_ready ? "true" : "false")
            << ",\"orderRoutingEnabled\":false"
            << ",\"requestsSeen\":" << requests_seen_.load(std::memory_order_relaxed)
            << ",\"lastDecisionCode\":";
        if (last_decision.empty()) {
            out << "null";
        } else {
            out << "\"" << astu::ipc::json_escape(last_decision) << "\"";
        }
        out
            << ",\"detail\":\"" << astu::ipc::json_escape(detail) << "\""
            << "}\n";

        write_atomic(out.str());
    }

    const std::filesystem::path& path() const noexcept {
        return path_;
    }

private:
    static std::uint64_t utc_now_ms() {
        const auto now = std::chrono::system_clock::now().time_since_epoch();
        return static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::milliseconds>(now).count());
    }

    static std::uint64_t process_id() noexcept {
#ifdef _WIN32
        return static_cast<std::uint64_t>(GetCurrentProcessId());
#else
        return 0;
#endif
    }

    void write_atomic(const std::string& text) const {
        if (!path_.parent_path().empty()) {
            std::filesystem::create_directories(path_.parent_path());
        }
        const auto tmp = path_.string() + ".tmp";
        {
            std::ofstream out(tmp, std::ios::binary | std::ios::trunc);
            if (!out) {
                throw std::runtime_error("cannot open execution status temp file");
            }
            out.write(text.data(), static_cast<std::streamsize>(text.size()));
            out.flush();
            if (!out) {
                throw std::runtime_error("cannot write execution status temp file");
            }
        }
#ifdef _WIN32
        if (!MoveFileExA(
                tmp.c_str(),
                path_.string().c_str(),
                MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
            std::filesystem::remove(tmp);
            throw std::runtime_error(
                "cannot publish execution status error=" +
                std::to_string(GetLastError()));
        }
#else
        std::filesystem::rename(tmp, path_);
#endif
    }

    std::filesystem::path path_;
    std::string data_provider_;
    std::string risk_provider_;
    std::string instrument_provider_;
    bool instrument_rules_required_{false};
    std::string journal_path_;
    mutable std::mutex mu_;
    std::string lifecycle_state_{"STARTING"};
    std::string detail_{"simulation execution host starting"};
    std::string last_decision_code_;
    bool journal_ready_{false};
    bool pipe_ready_{false};
    std::atomic<std::uint64_t> requests_seen_{0};
};

}  // namespace astu::execution
