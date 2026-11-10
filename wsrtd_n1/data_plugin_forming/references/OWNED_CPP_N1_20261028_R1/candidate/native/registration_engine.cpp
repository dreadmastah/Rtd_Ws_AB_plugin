#include "registration_engine.h"
#include <regex>
namespace owned {
std::vector<Outcome> Registration::tick(const std::vector<Symbol>& input,size_t max_batch){
  check();if(max_batch==0||max_batch>1000)throw std::invalid_argument("Invalid batch bound");
  std::vector<Symbol> symbols;std::set<std::string> unique;
  for(const auto& s:input){if(!std::regex_match(s.name,std::regex("[A-Z0-9]{3,30}")))throw std::invalid_argument("Invalid symbol");if(unique.insert(s.name).second)symbols.push_back(s);}
  std::vector<Outcome> out;if(symbols.empty())return out;
  size_t start=cursor%symbols.size(),count=(std::min)(max_batch,symbols.size());
  for(size_t i=0;i<count;++i){
    const auto& s=symbols[(start+i)%symbols.size()];
    if(cancelled)break;
    if(!s.eligible){out.push_back({s.name,"SYMBOL_DELISTED_HISTORY_RETAINED","No deletion; no refresh request"});continue;}
    if(seen.insert(s.name).second)out.push_back({s.name,"NEW_SYMBOL_DETECTED","Eligibility supplied separately"});
    out.push_back({s.name,"SYMBOL_REGISTRATION_REQUESTED",""});
    try {
      check();bool existed=host.exists(s.name);
      if(!existed){check();host.add(s.name);}
      check();if(!host.exists(s.name))throw std::runtime_error("Add not visible");
      check();host.save();
      out.push_back({s.name,existed?"SYMBOL_ALREADY_EXISTS":"SYMBOL_REGISTRATION_CONFIRMED","Interface readback and SaveDatabase call succeeded; native reopen persistence unproven"});
      request_refresh();
    }catch(const std::exception& e){out.push_back({s.name,"SYMBOL_REGISTRATION_FAILED",e.what()});}
    catch(...){out.push_back({s.name,"SYMBOL_REGISTRATION_FAILED","Unknown callback failure"});}
  }
  cursor=(start+count)%symbols.size();return out;
}
Outcome Registration::drain_refresh(){
  check();if(!refresh_pending.exchange(false))return {"","REFRESH_IDLE",""};
  try{check();host.refresh();return {"","REFRESH_REQUESTED","RefreshAll call completed; actual host redraw unproven"};}
  catch(const std::exception& e){refresh_pending=true;return {"","REFRESH_FAILED",e.what()};}
  catch(...){refresh_pending=true;return {"","REFRESH_FAILED","Unknown callback failure"};}
}
}
