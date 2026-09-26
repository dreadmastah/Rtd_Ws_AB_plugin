#pragma once

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

#include "astu/ipc/flat_json.hpp"

#ifdef _WIN32
#include <windows.h>
#endif

namespace astu::execution {

struct SymbolRiskStatusEntry {
    std::string symbol;
    bool position_ready{false};
    std::string position_mode{"UNKNOWN"};
    double current_notional{0.0};
    std::uint64_t active_reservations{0};
    double reserved_gross_notional{0.0};
    double projected_notional{0.0};
    double max_symbol_notional{0.0};
    double headroom{0.0};
    bool limit_enabled{false};
    std::string status{"UNAVAILABLE"};
    std::string detail;
};

inline std::vector<std::string> load_symbol_risk_universe(
    const std::filesystem::path& path,
    std::size_t max_symbols = 64) {
    if (max_symbols == 0) {
        throw std::invalid_argument("max_symbols must be positive");
    }

    std::ifstream in(path);
    if (!in) {
        throw std::runtime_error(
            "cannot open symbol risk universe " + path.string());
    }

    std::vector<std::string> symbols;
    std::unordered_set<std::string> seen;
    std::string line;
    while (std::getline(in, line)) {
        while (!line.empty() &&
               (line.back() == '\r' ||
                line.back() == ' ' ||
                line.back() == '\t')) {
            line.pop_back();
        }
        std::size_t first = 0;
        while (first < line.size() &&
               (line[first] == ' ' || line[first] == '\t')) {
            ++first;
        }
        line.erase(0, first);
        if (line.empty() || line.front() == '#') {
            continue;
        }
        if (line.size() > 32) {
            throw std::runtime_error("symbol risk universe symbol too long");
        }
        for (const unsigned char ch : line) {
            if (!(std::isupper(ch) || std::isdigit(ch))) {
                throw std::runtime_error(
                    "symbol risk universe contains invalid symbol");
            }
        }
        if (!seen.insert(line).second) {
            throw std::runtime_error(
                "symbol risk universe contains duplicate symbol");
        }
        symbols.push_back(line);
        if (symbols.size() > max_symbols) {
            throw std::runtime_error(
                "symbol risk universe exceeds bounded symbol count");
        }
    }

    if (symbols.empty()) {
        throw std::runtime_error("symbol risk universe is empty");
    }
    return symbols;
}

class SymbolRiskStatusPublisher {
public:
    explicit SymbolRiskStatusPublisher(std::filesystem::path path)
        : path_(std::move(path)) {}

    void publish(
        const std::vector<SymbolRiskStatusEntry>& entries,
        std::uint64_t generated_unix_ms = 0) const {
        if (entries.empty() || entries.size() > 64) {
            throw std::invalid_argument(
                "symbol risk status requires 1..64 entries");
        }

        if (generated_unix_ms == 0) {
            generated_unix_ms = utc_now_ms();
        }

        std::ostringstream out;
        out << std::setprecision(17);
        out
            << "{"
            << "\"schemaVersion\":1"
            << ",\"messageType\":\"SymbolRiskStatus.v1\""
            << ",\"generatedUnixMs\":" << generated_unix_ms
            << ",\"orderRoutingEnabled\":false"
            << ",\"symbols\":[";

        for (std::size_t i = 0; i < entries.size(); ++i) {
            const auto& entry = entries[i];
            if (entry.symbol.empty() ||
                entry.current_notional < 0.0 ||
                entry.reserved_gross_notional < 0.0 ||
                entry.projected_notional < 0.0 ||
                entry.max_symbol_notional < 0.0 ||
                entry.headroom < 0.0) {
                throw std::invalid_argument(
                    "invalid symbol risk status entry");
            }
            if (i != 0) {
                out << ",";
            }
            out
                << "{"
                << "\"symbol\":\""
                << astu::ipc::json_escape(entry.symbol) << "\""
                << ",\"positionReady\":"
                << (entry.position_ready ? "true" : "false")
                << ",\"positionMode\":\""
                << astu::ipc::json_escape(entry.position_mode) << "\""
                << ",\"currentNotional\":" << entry.current_notional
                << ",\"activeReservations\":"
                << entry.active_reservations
                << ",\"reservedGrossNotional\":"
                << entry.reserved_gross_notional
                << ",\"projectedNotional\":"
                << entry.projected_notional
                << ",\"maxSymbolNotional\":"
                << entry.max_symbol_notional
                << ",\"headroom\":";
            if (entry.limit_enabled && entry.position_ready) {
                out << entry.headroom;
            } else {
                out << "null";
            }
            out
                << ",\"limitEnabled\":"
                << (entry.limit_enabled ? "true" : "false")
                << ",\"status\":\""
                << astu::ipc::json_escape(entry.status) << "\""
                << ",\"detail\":\""
                << astu::ipc::json_escape(entry.detail) << "\""
                << "}";
        }

        out << "]}\n";
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

    void write_atomic(const std::string& text) const {
        if (!path_.parent_path().empty()) {
            std::filesystem::create_directories(path_.parent_path());
        }
        const auto tmp = path_.string() + ".tmp";
        {
            std::ofstream out(tmp, std::ios::binary | std::ios::trunc);
            if (!out) {
                throw std::runtime_error(
                    "cannot open symbol risk status temp file");
            }
            out.write(text.data(), static_cast<std::streamsize>(text.size()));
            out.flush();
            if (!out) {
                throw std::runtime_error(
                    "cannot write symbol risk status temp file");
            }
        }
#ifdef _WIN32
        if (!MoveFileExA(
                tmp.c_str(),
                path_.string().c_str(),
                MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
            std::filesystem::remove(tmp);
            throw std::runtime_error(
                "cannot publish symbol risk status error=" +
                std::to_string(GetLastError()));
        }
#else
        std::filesystem::rename(tmp, path_);
#endif
    }

    std::filesystem::path path_;
};

}  // namespace astu::execution
