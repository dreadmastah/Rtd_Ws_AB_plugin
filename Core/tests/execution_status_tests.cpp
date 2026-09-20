#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>

#include "astu/execution/execution_status.hpp"

namespace {

std::string read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        throw std::runtime_error("cannot read execution status test output");
    }
    std::ostringstream out;
    out << in.rdbuf();
    return out.str();
}

bool contains(
    const std::string& text,
    const std::string& expected) {
    if (text.find(expected) != std::string::npos) {
        return true;
    }
    std::cerr << "missing expected fragment: " << expected << "\n";
    return false;
}

double json_number(
    const std::string& text,
    const std::string& key) {
    const std::string marker = "\"" + key + "\":";
    const auto pos = text.find(marker);
    if (pos == std::string::npos) {
        throw std::runtime_error("missing numeric JSON key: " + key);
    }
    return std::stod(text.substr(pos + marker.size()));
}

bool same_number(
    const std::string& text,
    const std::string& key,
    double expected) {
    try {
        const auto actual = json_number(text, key);
        if (actual == expected) {
            return true;
        }
        std::cerr
            << "numeric mismatch for " << key
            << " actual=" << actual
            << " expected=" << expected << "\n";
        return false;
    } catch (const std::exception& exc) {
        std::cerr << exc.what() << "\n";
        return false;
    }
}

}  // namespace

int main() {
    const auto path =
        std::filesystem::temp_directory_path() /
        "astu_execution_status_account_risk_test.json";
    std::error_code ec;
    std::filesystem::remove(path, ec);

    astu::execution::ExecutionStatusPublisher status(
        path,
        "TEST_DATA",
        "TEST_RISK",
        "TEST_INSTRUMENT",
        false,
        "TEST_POSITION",
        "test_journal.jsonl");

    status.set_projected_risk_limits(
        4,
        2500.0,
        100.0,
        0.10,
        3.0,
        0.60,
        5000.0);
    status.set_account_risk_observation(
        true,
        123456789,
        "NORMAL",
        10250.0,
        9150.0,
        9120.0,
        1000.0,
        1300.0,
        100000.0,
        1,
        2,
        10,
        true,
        10250.0,
        100.0,
        130.0,
        1300.0 / 10250.0,
        130.0 / 10250.0,
        true,
        1000.0,
        1100.0);
    status.set_ready(true, true);
    status.publish();

    const auto text = read_all(path);
    bool ok = true;
    ok = contains(text, "\"accountRiskObservationReady\":true") && ok;
    ok = contains(text, "\"accountRiskObservedUnixMs\":123456789") && ok;
    ok = contains(text, "\"accountRiskState\":\"NORMAL\"") && ok;
    ok = contains(text, "\"currentRiskCapital\":10250") && ok;
    ok = contains(text, "\"currentAvailableBalance\":9150") && ok;
    ok = contains(text, "\"projectedAvailableBalance\":9120") && ok;
    ok = contains(text, "\"currentGrossNotional\":1000") && ok;
    ok = contains(text, "\"projectedGrossNotional\":1300") && ok;
    ok = contains(text, "\"currentMaxGrossNotional\":100000") && ok;
    ok = contains(text, "\"currentOpenPositions\":1") && ok;
    ok = contains(text, "\"projectedOpenPositions\":2") && ok;
    ok = contains(text, "\"currentMaxOpenPositions\":10") && ok;
    ok = contains(text, "\"accountMarginMetricsReady\":true") && ok;
    ok = contains(text, "\"currentMarginBalance\":10250") && ok;
    ok = contains(text, "\"currentInitialMargin\":100") && ok;
    ok = contains(text, "\"projectedInitialMargin\":130") && ok;
    ok = same_number(
             text,
             "projectedEffectiveLeverage",
             1300.0 / 10250.0) &&
         ok;
    ok = same_number(
             text,
             "projectedMarginUtilization",
             130.0 / 10250.0) &&
         ok;
    ok = contains(text, "\"accountNetDirectionalReady\":true") && ok;
    ok = contains(text, "\"currentNetDirectionalNotional\":1000") && ok;
    ok = contains(text, "\"projectedNetDirectionalNotional\":1100") && ok;
    ok = contains(text, "\"orderRoutingEnabled\":false") && ok;

    std::filesystem::remove(path, ec);
    if (!ok) {
        return 1;
    }
    std::cout << "EXECUTION_STATUS_ACCOUNT_RISK_OBSERVABILITY=PASS\n";
    return 0;
}
