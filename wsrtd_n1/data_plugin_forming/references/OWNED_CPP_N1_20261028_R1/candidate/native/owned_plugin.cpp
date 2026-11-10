// Owned SAFE_CODE_ONLY adapter. ANSI LPCTSTR ABI matches official ADK samples.
// No network, registry, DB writes, worker threads, or retained host pointers.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <tchar.h>
#include "Plugin.h"
#include "owned_reader.h"
#include <atomic>
#include <cstring>
#include <cstdlib>
#include <shared_mutex>
#include <mutex>
#include <string>
#include <vector>
#include <map>
#include <cstddef>
#include <chrono>
#include <stdexcept>
#include <set>
#include "database_binding.h"
#ifdef UNICODE
#error This target requires the documented ANSI ADK ABI
#endif
static_assert(sizeof(void*)==8 && sizeof(Quotation)==40 && alignof(Quotation)==8);
static_assert(sizeof(PluginInfo)==152 && sizeof(AmiDate)==8);
static_assert(offsetof(Quotation,Price)==8 && offsetof(Quotation,AuxData2)==36);
namespace {
std::recursive_mutex lifecycle;
n1::Binding binding;
unsigned long long generation=0;
std::atomic<unsigned long long> invalidation{0};
unsigned long long bound_epoch=0;
bool configuring=false;
std::set<std::string> registered;
std::string path;
bool ready=false;
thread_local int last_error=0;
int saved_count(int last,int size){return last>=0&&last<size?last+1:0;}
}
PLUGINAPI int GetPluginInfo(PluginInfo* info) {
  if(!info)return 0;
  PluginInfo p{};p.nStructSize=sizeof(p);p.nType=PLUGIN_TYPE_DATA;p.nVersion=50100;p.nIDCode=PIDCODE('W','N','1','T');p.nMinAmiVersion=700000;
  strcpy_s(p.szName,"WSRTD Owned N1 Database Bound");strcpy_s(p.szVendor,"WSRTD Private Development");*info=p;return 1;
}
PLUGINAPI int Init(void) {
  try {std::unique_lock lock(lifecycle);if(ready)return 1;
    const char* p=std::getenv("WSRTD_N1_SQLITE_PATH");
    if(!p||!*p){last_error=1;return 0;}
    std::string next(p);if(!std::filesystem::path(next).is_absolute())return 0;path=next;binding.clear();registered.clear();++generation;ready=true;last_error=0;return 1;
  }catch(...){last_error=2;return 0;}
}
PLUGINAPI int Release(void) {
  ++invalidation;
  try {std::unique_lock lock(lifecycle);ready=false;path.clear();binding.clear();registered.clear();++generation;return 1;}catch(...){last_error=2;return 0;}
}
// Host-owned callback executed only synchronously in Configure; no pointer cached.
// DO NOT EXECUTE until separate isolated AmiBroker native acceptance authority.
PLUGINAPI int Configure(LPCTSTR database,InfoSite* site) {
  try {std::unique_lock lock(lifecycle,std::try_to_lock);
    if(!lock.owns_lock()){last_error=7;return 0;}
    if(configuring){last_error=7;return 0;}
    if(!ready||bound_epoch!=invalidation.load()||!site||site->nStructSize<sizeof(InfoSite)||!site->AddStockNew){binding.clear();registered.clear();++generation;last_error=3;return 0;}
    auto supplied=n1::bind_directory(database);
    if(binding.key.empty()||supplied.key!=binding.key)throw std::runtime_error("Configure differs from Notify database");
    auto symbols=wsrtd::registry(path,binding.key);const auto epoch=generation;
    bool failed=false;configuring=true;
    struct Reset{~Reset(){configuring=false;}} reset;
    // Recursive nonblocking gate serializes concurrent database changes. Host
    // callback is synchronous; same-thread Notify may invalidate epoch.
    for(const auto& symbol:symbols){
      if(generation!=epoch||bound_epoch!=invalidation.load()||binding.key.empty()){last_error=7;return 0;}
      if(registered.count(symbol))continue;
      auto result=site->AddStockNew(symbol.c_str());
      if(generation!=epoch||bound_epoch!=invalidation.load()){last_error=7;return 0;}
      if(result)registered.insert(symbol);else failed=true;
    }
    last_error=failed?4:0;return failed?0:1;
  }catch(...){std::unique_lock lock(lifecycle);binding.clear();registered.clear();++generation;last_error=2;return 0;}
}
PLUGINAPI int GetQuotesEx(LPCTSTR ticker,int periodicity,int last,int size,Quotation* quotes,GQEContext*) {
  const int kept=saved_count(last,size);
  try {std::unique_lock lock(lifecycle,std::try_to_lock);
    if(!lock.owns_lock()){last_error=7;return 0;}
    const auto deadline=std::chrono::steady_clock::now()+std::chrono::milliseconds(150);
    const auto checkpoint=[&](){if(std::chrono::steady_clock::now()>deadline)throw std::runtime_error("Callback cooperative deadline");};
    if(!ready||bound_epoch!=invalidation.load()||binding.key.empty()||!ticker||!quotes||size<=0||size>200000){last_error=1;return 0;}
    const std::string interval=periodicity==60?"1m":periodicity==86400?"1d":"";
    if(interval.empty()){last_error=5;return 0;}
    const auto bars=wsrtd::read_recent(path,binding.key,ticker,interval,size);
    // Build the entire response before touching caller memory; failures preserve prior quotes.
    std::vector<Quotation> out;out.reserve(bars.size());
    for(const auto& b:bars){checkpoint();Quotation q{};
      q.DateTime.PackDate.Year=b.date_num/10000;q.DateTime.PackDate.Month=b.date_num/100%100;q.DateTime.PackDate.Day=b.date_num%100;
      if(interval=="1d")q.DateTime.Date|=DAILY_MASK;
      else {q.DateTime.PackDate.Hour=b.time_num/10000;q.DateTime.PackDate.Minute=b.time_num/100%100;q.DateTime.PackDate.Second=b.time_num%100;}
      q.Open=b.open;q.High=b.high;q.Low=b.low;q.Price=b.close;q.Volume=b.volume;q.OpenInterest=b.open_interest;q.AuxData1=b.aux1;q.AuxData2=b.aux2;out.push_back(q);
    }
    // Caller buffers have no database provenance in the ADK. Never merge an
    // untagged prior buffer into a different scoped store. Store is read-only.
    if(bound_epoch!=invalidation.load()){last_error=7;return 0;}
    for(size_t i=0;i<out.size();++i)quotes[i]=out[i];last_error=0;return static_cast<int>(out.size());
  }catch(...){last_error=2;return 0;}
}
PLUGINAPI int GetQuotes(LPCTSTR,int,int,int,QuotationFormat4*) {last_error=5;return 0;}
// Diagnostic code only: 0 OK;1 lifecycle/input;2 storage;3 callback ABI;4 add failure;
// 5 unsupported;6 historical coverage incomplete. No capacity claim.
PLUGINAPI int OwnedLastError(void){return last_error;}
// Notify never retains HWND, workspace or host stock pointers. The external
// controller uses documented RefreshAll; no unbound Windows messages are sent.
PLUGINAPI int Notify(PluginNotification* notice){
  if(notice&&notice->nStructSize>=sizeof(PluginNotification)&&notice->nReason==REASON_STATUS_RMBCLICK)return 1;
  const auto attempt=++invalidation;
  std::unique_lock lock(lifecycle,std::try_to_lock);
  if(!lock.owns_lock()){last_error=7;return 0;}
  binding.clear();registered.clear();++generation;
  if(!notice||notice->nStructSize<sizeof(PluginNotification)){last_error=3;return 0;}
  if(notice->nReason==REASON_DATABASE_UNLOADED){last_error=0;return 1;}
  if(notice->nReason!=REASON_DATABASE_LOADED&&notice->nReason!=REASON_SETTINGS_CHANGE){last_error=3;return 0;}
  try {if(!ready)throw std::runtime_error("not initialized");auto next=n1::bind_directory(notice->pszDatabasePath);
    wsrtd::registry(path,next.key);if(invalidation.load()!=attempt)throw std::runtime_error("concurrent notification");binding=std::move(next);bound_epoch=attempt;last_error=0;return 1;
  }catch(...){last_error=2;return 0;}
}
PLUGINAPI int SetTimeBase(int seconds){return seconds==60||seconds==86400;}
// Offline diagnostic: copies current opaque file-identity key, never a host pointer.
PLUGINAPI int OwnedDatabaseKey(char* output,int size){std::unique_lock lock(lifecycle,std::try_to_lock);if(!lock.owns_lock()||bound_epoch!=invalidation.load()||binding.key.empty()||!output||size<=static_cast<int>(binding.key.size()))return 0;strcpy_s(output,size,binding.key.c_str());return 1;}
