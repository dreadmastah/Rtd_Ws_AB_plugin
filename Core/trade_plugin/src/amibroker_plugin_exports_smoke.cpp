#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

#include <array>
#include <cstring>
#include <iostream>

#include "astu/trade/amibroker_abi_min.hpp"

int main(int argc, char** argv) {
#ifdef _WIN32
    if (argc != 2) {
        std::cerr << "usage: astu_trade_amibroker_exports_smoke <dll>\n";
        return 2;
    }

    HMODULE dll = LoadLibraryA(argv[1]);
    if (!dll) {
        std::cerr << "LoadLibrary failed\n";
        return 3;
    }

    constexpr std::array<const char*, 5> required = {
        "GetPluginInfo",
        "Init",
        "Release",
        "GetFunctionTable",
        "SetSiteInterface",
    };

    int rc = 0;
    for (const char* name : required) {
        if (!GetProcAddress(dll, name)) {
            std::cerr << "missing export: " << name << "\n";
            rc = 4;
        }
    }

    using namespace astu::trade::amibroker;
    using GetInfoFn = int (*)(PluginInfo*);
    using GetTableFn = int (*)(FunctionTag**);
    using SimpleFn = int (*)();

    if (rc == 0) {
        const auto get_info = reinterpret_cast<GetInfoFn>(
            GetProcAddress(dll, "GetPluginInfo"));
        const auto get_table = reinterpret_cast<GetTableFn>(
            GetProcAddress(dll, "GetFunctionTable"));
        const auto init = reinterpret_cast<SimpleFn>(
            GetProcAddress(dll, "Init"));
        const auto release = reinterpret_cast<SimpleFn>(
            GetProcAddress(dll, "Release"));

        PluginInfo info{};
        if (!get_info || get_info(&info) != 1 ||
            info.nStructSize != sizeof(PluginInfo) ||
            info.nType != kPluginTypeAfl ||
            std::strcmp(info.szName, "AstuTrade Simulation Bridge") != 0) {
            std::cerr << "GetPluginInfo validation failed\n";
            rc = 5;
        }

        FunctionTag* table = nullptr;
        const int count = get_table ? get_table(&table) : 0;
        if (count != 3 || !table ||
            std::strcmp(table[0].Name, "AstuSimulate") != 0 ||
            std::strcmp(table[1].Name, "AstuVersion") != 0 ||
            std::strcmp(table[2].Name, "AstuLastDecision") != 0) {
            std::cerr << "GetFunctionTable validation failed\n";
            rc = 6;
        }

        if (!init || init() != 1 || !release || release() != 1) {
            std::cerr << "Init/Release validation failed\n";
            rc = 7;
        }
    }

    FreeLibrary(dll);
    if (rc == 0) {
        std::cout << "AMIBROKER_PLUGIN_EXPORTS=PASS\n";
        std::cout << "AMIBROKER_PLUGIN_FUNCTION_TABLE=PASS\n";
    }
    return rc;
#else
    (void)argc;
    (void)argv;
    std::cerr << "AmiBroker export smoke requires Windows\n";
    return 2;
#endif
}
