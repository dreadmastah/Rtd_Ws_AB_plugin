#pragma once
#include <windows.h>
#include <string>
#include <vector>
#include <filesystem>
#include <stdexcept>
#include <cstdio>
#include <algorithm>
namespace n1 {
struct Binding {
 std::string key;
 std::vector<HANDLE> handles;
 Binding()=default;
 Binding(const Binding&)=delete;
 Binding& operator=(const Binding&)=delete;
 Binding(Binding&& b) noexcept:key(std::move(b.key)),handles(std::move(b.handles)){b.handles.clear();}
 Binding& operator=(Binding&& b) noexcept {clear();key=std::move(b.key);handles=std::move(b.handles);b.handles.clear();return *this;}
 ~Binding(){clear();}
 void clear(){for(auto h:handles)CloseHandle(h);handles.clear();key.clear();}
};
inline Binding bind_directory(const char* input) {
 if(!input||!*input)throw std::runtime_error("missing database path");
 // Deliberately bounded ANSI ADK subset: local absolute drive paths only.
 std::string s(input);
 if(s.size()>240||s.size()<3||s[1]!=':'||(s[2]!='\\'&&s[2]!='/')||s.find("..")!=std::string::npos)throw std::runtime_error("ambiguous database path");
 for(unsigned char ch:s)if(ch<32||ch>126)throw std::runtime_error("unsupported ANSI path");
 if(GetDriveTypeA(s.substr(0,3).c_str())!=DRIVE_FIXED)throw std::runtime_error("nonlocal database");
 std::filesystem::path p(s);p=p.lexically_normal();Binding out;
 std::vector<std::filesystem::path> ancestors;
 for(auto at=p;!at.empty();){ancestors.push_back(at);auto parent=at.parent_path();if(parent==at)break;at=parent;}
 std::reverse(ancestors.begin(),ancestors.end());
 for(const auto& at:ancestors){
  auto str=at.string();DWORD a=GetFileAttributesA(str.c_str());
  if(a==INVALID_FILE_ATTRIBUTES||!(a&FILE_ATTRIBUTE_DIRECTORY)||(a&FILE_ATTRIBUTE_REPARSE_POINT))throw std::runtime_error("invalid database ancestor");
  HANDLE h=CreateFileA(str.c_str(),FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
  if(h==INVALID_HANDLE_VALUE)throw std::runtime_error("database directory pin failed");
  out.handles.push_back(h);BY_HANDLE_FILE_INFORMATION info{};
  if(!GetFileInformationByHandle(h,&info)||(info.dwFileAttributes&FILE_ATTRIBUTE_REPARSE_POINT))throw std::runtime_error("database identity failed");
  if(at==p){char key[80];sprintf_s(key,"%08lx:%08lx%08lx",info.dwVolumeSerialNumber,info.nFileIndexHigh,info.nFileIndexLow);out.key=key;}
 }
 if(out.key.empty())throw std::runtime_error("empty identity");return out;
}
}
