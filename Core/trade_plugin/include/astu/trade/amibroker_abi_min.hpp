#pragma once

// Minimal AmiBroker AFL plug-in ABI declarations used by AstuTrade.
//
// The ABI layout and export signatures are based on AmiBroker Development Kit
// Plugin.h (ADK 2.1a). AmiBroker's published header grants a royalty-free
// license for individual and commercial software, subject to retaining its
// copyright notice in user documentation/internal comments.
//
// Copyright (c) 2001-2010 AmiBroker.com. All rights reserved.
// AmiBroker.com provides the original ADK source "AS IS" without warranty.
//
// This file intentionally restates only the small ABI subset needed by the
// simulation-only AFL plug-in; it is not a copy of the full ADK header.

#include <cstdint>

namespace astu::trade::amibroker {

inline constexpr int kPluginTypeAfl = 1;

struct PluginInfo {
    int nStructSize;
    int nType;
    int nVersion;
    int nIDCode;
    char szName[64];
    char szVendor[64];
    int nCertificate;
    int nMinAmiVersion;
};

enum : int {
    VarNone = 0,
    VarFloat = 1,
    VarArray = 2,
    VarString = 3,
    VarDisp = 4,
};

#pragma pack(push, 2)
struct AmiVar {
    int type;
    union {
        float val;
        float* array;
        char* string;
        void* disp;
    };
};
#pragma pack(pop)

using DateTimeInt = unsigned long long;

struct SiteInterface {
    int nStructSize;
    int (*GetArraySize)();
    float* (*GetStockArray)(int);
    AmiVar (*GetVariable)(const char*);
    void (*SetVariable)(const char*, AmiVar);
    AmiVar (*CallFunction)(const char*, int, AmiVar*);
    AmiVar (*AllocArrayResult)();
    void* (*Alloc)(unsigned int);
    void (*Free)(void*);
    DateTimeInt* (*GetDateTimeArray)();
};

using AflFunction = AmiVar (*)(int, AmiVar*);

struct FunDesc {
    AflFunction Function;
    unsigned char ArrayQty;
    unsigned char StringQty;
    signed char FloatQty;
    unsigned char DefaultQty;
    float* DefaultValues;
};

struct FunctionTag {
    char* Name;
    FunDesc Descript;
};

static_assert(sizeof(AmiVar) == (sizeof(void*) == 8 ? 12 : 8));

}  // namespace astu::trade::amibroker

#ifdef _WIN32
#define ASTU_AMIBROKER_EXPORT extern "C" __declspec(dllexport)
#else
#define ASTU_AMIBROKER_EXPORT extern "C"
#endif
