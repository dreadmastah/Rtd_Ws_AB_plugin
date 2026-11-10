#pragma once
#include <string>
#include <vector>
#include <set>
#include <atomic>
#include <thread>
#include <stdexcept>
namespace owned {
struct Symbol {std::string name;bool eligible;};
struct Outcome {std::string symbol,event,detail;};
// No stored InfoSite. Host port belongs to one initialized COM/controller thread.
struct Host {
  virtual ~Host()=default;
  virtual void verify_target()=0;
  virtual bool exists(const std::string&)=0;
  virtual void add(const std::string&)=0;
  virtual void save()=0;
  virtual void refresh()=0;
};
class Registration {
  Host& host;std::thread::id owner=std::this_thread::get_id();
  std::atomic<bool> cancelled{false},refresh_pending{false};
  std::set<std::string> seen;
  size_t cursor=0;
  void check(){if(std::this_thread::get_id()!=owner)throw std::runtime_error("WRONG_THREAD");if(cancelled)throw std::runtime_error("CANCELLED");host.verify_target();}
public:
  explicit Registration(Host& h):host(h){}
  void cancel(){cancelled=true;refresh_pending=false;}
  // Producer operation: no host/SQLite work, one coalesced pending bit.
  void request_refresh(){if(!cancelled)refresh_pending=true;}
  std::vector<Outcome> tick(const std::vector<Symbol>& symbols,size_t max_batch=100);
  Outcome drain_refresh();
};
}
