#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

#include <array>
#include <iostream>

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

    FreeLibrary(dll);
    if (rc == 0) {
        std::cout << "AMIBROKER_PLUGIN_EXPORTS=PASS\n";
    }
    return rc;
#else
    (void)argc;
    (void)argv;
    std::cerr << "AmiBroker export smoke requires Windows\n";
    return 2;
#endif
}
