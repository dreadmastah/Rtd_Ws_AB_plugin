#pragma once

#include <chrono>
#include <cstdint>
#include <deque>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>

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
            << ",\"orderRoutingEnabled\":false"
            << ",\"reason\":\"" << astu::ipc::json_escape(response.reason) << "\""
            << "}\n";

        append_durable(out.str());
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
};

}  // namespace astu::execution
