#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "astu/execution/symbol_risk_status.hpp"

namespace {

std::string read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        throw std::runtime_error("cannot read symbol risk status output");
    }
    std::ostringstream out;
    out << in.rdbuf();
    return out.str();
}

bool contains(const std::string& text, const std::string& expected) {
    if (text.find(expected) != std::string::npos) {
        return true;
    }
    std::cerr << "missing expected fragment: " << expected << "\n";
    return false;
}

}  // namespace

int main() {
    const auto root =
        std::filesystem::temp_directory_path() /
        "astu_symbol_risk_status_test";
    std::filesystem::create_directories(root);

    const auto universe = root / "symbols.tls";
    {
        std::ofstream out(universe);
        out << "BTCUSDT\nETHUSDT\n";
    }

    const auto symbols =
        astu::execution::load_symbol_risk_universe(universe, 2);
    if (symbols.size() != 2 ||
        symbols[0] != "BTCUSDT" ||
        symbols[1] != "ETHUSDT") {
        std::cerr << "bounded universe load mismatch\n";
        return 1;
    }

    bool bounded = false;
    try {
        (void)astu::execution::load_symbol_risk_universe(universe, 1);
    } catch (const std::runtime_error&) {
        bounded = true;
    }
    if (!bounded) {
        std::cerr << "universe bound was not enforced\n";
        return 2;
    }

    const auto status_path = root / "symbol_risk_status.v1.json";
    astu::execution::SymbolRiskStatusPublisher publisher(status_path);

    std::vector<astu::execution::SymbolRiskStatusEntry> entries;

    astu::execution::SymbolRiskStatusEntry btc;
    btc.symbol = "BTCUSDT";
    btc.position_ready = true;
    btc.position_mode = "LONG";
    btc.current_notional = 1000.0;
    btc.active_reservations = 1;
    btc.reserved_gross_notional = 300.0;
    btc.projected_notional = 1300.0;
    btc.max_symbol_notional = 2500.0;
    btc.headroom = 1200.0;
    btc.limit_enabled = true;
    btc.status = "HEADROOM";
    btc.detail = "fixture";
    entries.push_back(btc);

    astu::execution::SymbolRiskStatusEntry eth;
    eth.symbol = "ETHUSDT";
    eth.position_ready = true;
    eth.position_mode = "FLAT";
    eth.current_notional = 0.0;
    eth.active_reservations = 0;
    eth.reserved_gross_notional = 0.0;
    eth.projected_notional = 0.0;
    eth.max_symbol_notional = 2500.0;
    eth.headroom = 2500.0;
    eth.limit_enabled = true;
    eth.status = "HEADROOM";
    eth.detail = "fixture";
    entries.push_back(eth);

    publisher.publish(entries, 123456789);

    const auto text = read_all(status_path);
    bool ok = true;
    ok = contains(text, "\"messageType\":\"SymbolRiskStatus.v1\"") && ok;
    ok = contains(text, "\"generatedUnixMs\":123456789") && ok;
    ok = contains(text, "\"orderRoutingEnabled\":false") && ok;
    ok = contains(text, "\"symbol\":\"BTCUSDT\"") && ok;
    ok = contains(text, "\"currentNotional\":1000") && ok;
    ok = contains(text, "\"reservedGrossNotional\":300") && ok;
    ok = contains(text, "\"projectedNotional\":1300") && ok;
    ok = contains(text, "\"headroom\":1200") && ok;
    ok = contains(text, "\"symbol\":\"ETHUSDT\"") && ok;

    std::error_code ec;
    std::filesystem::remove_all(root, ec);
    if (!ok) {
        return 3;
    }

    std::cout << "SYMBOL_RISK_STATUS_TESTS=PASS\n";
    return 0;
}
