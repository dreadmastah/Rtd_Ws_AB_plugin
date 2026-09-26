#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>

#include "astu/core/contracts.hpp"
#include "astu/trade/amibroker_abi_min.hpp"

int main(int argc, char** argv) {
#ifdef _WIN32
    if (argc != 3) {
        std::cerr
            << "usage: astu_trade_amibroker_call_smoke <AstuTrade.dll> <status-dir>\n";
        return 2;
    }

    if (_putenv_s("ASTU_STATUS_DIR", argv[2]) != 0 ||
        !SetEnvironmentVariableA("ASTU_STATUS_DIR", argv[2])) {
        std::cerr << "setting ASTU_STATUS_DIR failed\n";
        return 3;
    }

    HMODULE dll = LoadLibraryA(argv[1]);
    if (!dll) {
        std::cerr << "LoadLibrary failed\n";
        return 4;
    }

    using namespace astu::trade::amibroker;
    using GetTableFn = int (*)(FunctionTag**);
    using SimpleFn = int (*)();

    const auto get_table = reinterpret_cast<GetTableFn>(
        GetProcAddress(dll, "GetFunctionTable"));
    const auto init = reinterpret_cast<SimpleFn>(
        GetProcAddress(dll, "Init"));
    const auto release = reinterpret_cast<SimpleFn>(
        GetProcAddress(dll, "Release"));

    if (!get_table || !init || !release || init() != 1) {
        std::cerr << "AstuTrade initialization failed\n";
        FreeLibrary(dll);
        return 5;
    }

    FunctionTag* table = nullptr;
    const int count = get_table(&table);
    if (count < 3 || !table) {
        std::cerr << "AstuTrade function table unavailable\n";
        release();
        FreeLibrary(dll);
        return 6;
    }

    AflFunction simulate = nullptr;
    AflFunction last_decision = nullptr;
    for (int i = 0; i < count; ++i) {
        if (std::strcmp(table[i].Name, "AstuSimulate") == 0) {
            simulate = table[i].Descript.Function;
        } else if (std::strcmp(table[i].Name, "AstuLastDecision") == 0) {
            last_decision = table[i].Descript.Function;
        }
    }

    if (!simulate || !last_decision) {
        std::cerr << "AstuTrade required AFL functions unavailable\n";
        release();
        FreeLibrary(dll);
        return 7;
    }

    char symbol[] = "BTCUSDT";
    char action[] = "BUY";
    char side[] = "LONG";
    char strategy[] = "abi-e2e-smoke";
    char strategy_version[] = "1";
    char periodicity[] = "M1";

    AmiVar args[8]{};
    char* strings[6] = {
        symbol,
        action,
        side,
        strategy,
        strategy_version,
        periodicity,
    };
    for (int i = 0; i < 6; ++i) {
        args[i].type = VarString;
        args[i].string = strings[i];
    }
    args[6].type = VarFloat;
    args[6].val = 100000.0f;
    args[7].type = VarFloat;
    args[7].val = 30.0f;

    const AmiVar result = simulate(8, args);
    const AmiVar last = last_decision(0, nullptr);

    const int expected =
        static_cast<int>(astu::core::DecisionCode::OrderRoutingDisabled);
    const bool ok =
        result.type == VarFloat &&
        last.type == VarFloat &&
        static_cast<int>(result.val) == expected &&
        static_cast<int>(last.val) == expected;

    std::cout << "ASTU_TRADE_AFL_RESULT="
              << static_cast<int>(result.val) << "\n";
    std::cout << "ASTU_TRADE_LAST_DECISION="
              << static_cast<int>(last.val) << "\n";

    release();
    FreeLibrary(dll);

    if (!ok) {
        std::cerr << "AstuTrade AFL end-to-end simulation did not reach code "
                  << expected << "\n";
        return 8;
    }

    std::cout << "ASTU_TRADE_AFL_E2E=PASS\n";
    return 0;
#else
    (void)argc;
    (void)argv;
    std::cerr << "AstuTrade AFL call smoke requires Windows\n";
    return 2;
#endif
}
