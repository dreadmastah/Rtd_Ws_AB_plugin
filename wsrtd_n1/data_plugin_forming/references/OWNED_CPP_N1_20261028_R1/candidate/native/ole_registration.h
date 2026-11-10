#pragma once
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <oaidl.h>
#include "registration_engine.h"
#include <functional>
namespace owned {
struct TargetIdentity {DWORD pid;unsigned long long creation_time;std::wstring executable,database;};
// Takes a caller-supplied object; does not select, activate, locate or attach COM.
// External binder must prove that this exact object belongs to TargetIdentity.
// No production binder is provided in SAFE_CODE_ONLY.
class OleHost final:public Host {
  IDispatch* app;TargetIdentity target;DWORD thread;
  std::function<bool(IDispatch*,const TargetIdentity&)> attest;
public:
  OleHost(IDispatch*,TargetIdentity,std::function<bool(IDispatch*,const TargetIdentity&)>);
  ~OleHost();
  OleHost(const OleHost&)=delete;OleHost& operator=(const OleHost&)=delete;
  void verify_target() override;
  bool exists(const std::string&) override;
  void add(const std::string&) override;
  void save() override;
  void refresh() override;
};
}
