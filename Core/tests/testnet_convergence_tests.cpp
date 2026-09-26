#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>

#include "astu/execution/testnet_convergence.hpp"

namespace {

std::uint64_t now_ms() {
    const auto now =
        std::chrono::system_clock::now().time_since_epoch();
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<
            std::chrono::milliseconds>(now).count());
}

void write_state(
    const std::filesystem::path& path,
    std::uint64_t generated,
    bool ready,
    bool stream_alive,
    bool account,
    bool positions,
    bool orders,
    bool fallback,
    std::uint64_t unresolved) {
    std::ofstream out(path, std::ios::trunc);
    out
        << "{"
        << "\"schemaVersion\":1,"
        << "\"messageType\":\"TestnetUserDataState.v1\","
        << "\"generatedUnixMs\":" << generated << ","
        << "\"source\":\"BINANCE_USDM_TESTNET_USER_DATA\","
        << "\"ready\":" << (ready ? "true" : "false") << ","
        << "\"streamAlive\":" << (stream_alive ? "true" : "false") << ","
        << "\"streamEpoch\":1,"
        << "\"connectedUnixMs\":" << generated << ","
        << "\"lastFrameUnixMs\":" << generated << ","
        << "\"lastEventUnixMs\":" << generated << ","
        << "\"livenessAgeMs\":0,"
        << "\"maxLivenessAgeMs\":15000,"
        << "\"eventCount\":2,"
        << "\"orderEventCount\":1,"
        << "\"accountEventCount\":1,"
        << "\"ignoredOrderEventCount\":0,"
        << "\"listenKeyExpiredCount\":0,"
        << "\"expired\":false,"
        << "\"orderingOk\":true,"
        << "\"lastAccountEventTimeMs\":" << generated << ","
        << "\"lastAccountReason\":\"ORDER\","
        << "\"accountRestGeneratedUnixMs\":" << generated << ","
        << "\"accountConverged\":" << (account ? "true" : "false") << ","
        << "\"positionsConverged\":" << (positions ? "true" : "false") << ","
        << "\"ordersConverged\":" << (orders ? "true" : "false") << ","
        << "\"resolvedAstuOrders\":1,"
        << "\"unresolvedAstuOrders\":" << unresolved << ","
        << "\"restFallbackRequired\":" << (fallback ? "true" : "false") << ","
        << "\"lastOrderClientId\":\"ASTU-test\","
        << "\"lastOrderSymbol\":\"BTCUSDT\","
        << "\"lastOrderExchangeStatus\":\"FILLED\","
        << "\"lastOrderCumulativeFilledQuantity\":0.102,"
        << "\"detail\":\"fixture\""
        << "}\n";
}

}  // namespace

int main() {
    using astu::execution::FileBackedTestnetConvergenceProvider;

    const auto path =
        std::filesystem::temp_directory_path() /
        "astu_testnet_convergence_test.json";
    const auto now = now_ms();

    write_state(path, now, true, true, true, true, true, false, 0);
    auto state =
        FileBackedTestnetConvergenceProvider(path, 5'000)();
    if (!state.ready) {
        std::cerr << state.detail << "\n";
        return 1;
    }

    write_state(path, now, false, true, true, true, false, true, 1);
    state = FileBackedTestnetConvergenceProvider(path, 5'000)();
    if (state.ready || !state.rest_fallback_required ||
        state.unresolved_orders != 1) {
        return 2;
    }

    write_state(path, now - 10'000, true, true, true, true, true, false, 0);
    state = FileBackedTestnetConvergenceProvider(path, 5'000)();
    if (state.ready ||
        state.detail.find("stale") == std::string::npos) {
        return 3;
    }

    std::error_code ec;
    std::filesystem::remove(path, ec);
    std::cout << "TESTNET_CONVERGENCE_TESTS=PASS\n";
    return 0;
}
