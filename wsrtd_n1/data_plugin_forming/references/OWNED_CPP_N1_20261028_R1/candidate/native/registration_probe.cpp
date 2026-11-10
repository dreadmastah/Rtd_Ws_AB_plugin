// SYNTHETIC HOST PORT. Exercises real compiled registration code, not AmiBroker.
#include "registration_engine.h"
#include "ole_registration.h"
#include <iostream>
#include <map>
using namespace owned;
void require(bool value,const char* message){if(!value)throw std::runtime_error(message);}
struct Fake:Host {
  std::set<std::string> symbols;std::map<std::string,int> adds;bool bound=true,fail_save=false,fail_refresh=false;int saves=0,refreshes=0;
  void verify_target()override{if(!bound)throw std::runtime_error("SYNTHETIC target drift");}
  bool exists(const std::string& s)override{return symbols.count(s)!=0;}
  void add(const std::string& s)override{if(s=="FAILUSDT")throw std::runtime_error("SYNTHETIC add failure");++adds[s];symbols.insert(s);}
  void save()override{if(fail_save)throw std::runtime_error("SYNTHETIC save failure");++saves;}
  void refresh()override{if(fail_refresh)throw std::runtime_error("SYNTHETIC refresh failure");++refreshes;}
};
// Real IDispatch vtable fixture exercising the concrete OLE adapter's Invoke path.
// This object is local to the probe; no COM activation or AmiBroker instance.
struct DispatchFixture:IDispatch {
  ULONG refs=1;std::set<std::wstring> names;std::wstring ticker,path=L"D:\\isolated";int saves=0,refreshes=0;
  HRESULT STDMETHODCALLTYPE QueryInterface(REFIID id,void** out)override{if(!out)return E_POINTER;if(id==IID_IUnknown||id==IID_IDispatch){*out=this;AddRef();return S_OK;}*out=nullptr;return E_NOINTERFACE;}
  ULONG STDMETHODCALLTYPE AddRef()override{return ++refs;}
  ULONG STDMETHODCALLTYPE Release()override{return --refs;}
  HRESULT STDMETHODCALLTYPE GetTypeInfoCount(UINT* n)override{*n=0;return S_OK;}
  HRESULT STDMETHODCALLTYPE GetTypeInfo(UINT,LCID,ITypeInfo**)override{return E_NOTIMPL;}
  HRESULT STDMETHODCALLTYPE GetIDsOfNames(REFIID,LPOLESTR* names_,UINT count,LCID,DISPID* ids)override{
    const wchar_t* members[]={L"DatabasePath",L"Stocks",L"Item",L"Add",L"Ticker",L"SaveDatabase",L"RefreshAll"};
    if(count!=1)return DISP_E_UNKNOWNNAME;for(int i=0;i<7;++i)if(std::wstring(names_[0])==members[i]){ids[0]=i;return S_OK;}return DISP_E_UNKNOWNNAME;
  }
  HRESULT STDMETHODCALLTYPE Invoke(DISPID id,REFIID,LCID,WORD,DISPPARAMS* params,VARIANT* result,EXCEPINFO*,UINT*)override{
    VariantInit(result);
    if(id==0||id==4){result->vt=VT_BSTR;result->bstrVal=SysAllocString((id==0?path:ticker).c_str());return result->bstrVal?S_OK:E_OUTOFMEMORY;}
    if(id==1){result->vt=VT_DISPATCH;result->pdispVal=this;AddRef();return S_OK;}
    if(id==2||id==3){
      if(params->cArgs!=1||params->rgvarg[0].vt!=VT_BSTR)return DISP_E_TYPEMISMATCH;
      ticker=params->rgvarg[0].bstrVal;
      if(id==3){if(ticker==L"FAILUSDT")return E_FAIL;names.insert(ticker);}
      if(!names.count(ticker)){result->vt=VT_NULL;return S_OK;}
      result->vt=VT_DISPATCH;result->pdispVal=this;AddRef();return S_OK;
    }
    if(id==5){++saves;return S_OK;}if(id==6){++refreshes;return S_OK;}return DISP_E_MEMBERNOTFOUND;
  }
};
int main(){try{
  Fake f;Registration c(f);auto results=c.tick({{"FAILUSDT",true},{"BTCUSDT",true},{"BTCUSDT",true}});
  require(f.adds["BTCUSDT"]==1,"Failure must not stop next valid symbol");
  bool failed=false,confirmed=false;for(auto& r:results){failed|=r.event=="SYMBOL_REGISTRATION_FAILED";confirmed|=r.event=="SYMBOL_REGISTRATION_CONFIRMED";}
  require(failed&&confirmed,"Per symbol outcomes");
  c.tick({{"BTCUSDT",true}});require(f.adds["BTCUSDT"]==1,"Duplicate registration");
  require(c.drain_refresh().event=="REFRESH_REQUESTED"&&c.drain_refresh().event=="REFRESH_IDLE","Coalesced refresh");
  auto delisted=c.tick({{"BTCUSDT",false}});require(delisted[0].event=="SYMBOL_DELISTED_HISTORY_RETAINED"&&f.symbols.count("BTCUSDT"),"No auto delete");
  c.tick({{"BTCUSDT",true}});require(f.adds["BTCUSDT"]==1,"Relisting duplicate");
  f.fail_save=true;auto interrupted=c.tick({{"ETHUSDT",true}});require(interrupted.back().event=="SYMBOL_REGISTRATION_FAILED","Interrupted save");
  f.fail_save=false;c.tick({{"ETHUSDT",true}});require(f.adds["ETHUSDT"]==1,"Save retry must not duplicate");
  f.fail_refresh=true;require(c.drain_refresh().event=="REFRESH_FAILED","Observable refresh failure");
  f.fail_refresh=false;require(c.drain_refresh().event=="REFRESH_REQUESTED","Bounded refresh retry");
  std::thread producer([&](){for(int i=0;i<100000;++i)c.request_refresh();});producer.join();
  int before=f.refreshes;c.drain_refresh();c.drain_refresh();require(f.refreshes==before+1,"Bounded queue");
  bool thread_failed=false;std::thread wrong([&](){try{c.tick({{"XRPUSDT",true}});}catch(...){thread_failed=true;}});wrong.join();require(thread_failed,"Thread affinity");
  Registration restart(f);restart.tick({{"BTCUSDT",true}});require(f.adds["BTCUSDT"]==1,"Restart lookup");
  f.bound=false;bool drift=false;try{c.tick({{"BTCUSDT",true}});}catch(...){drift=true;}require(drift,"Identity failure");f.bound=true;
  c.cancel();bool stopped=false;try{c.tick({{"BTCUSDT",true}});}catch(...){stopped=true;}require(stopped,"Cancellation");
  bool unbound=false;try{OleHost denied(nullptr,TargetIdentity{},{});}catch(...){unbound=true;}require(unbound,"No implicit COM attach");
  DispatchFixture dispatch;
  {OleHost ole(&dispatch,{123,456,L"SYNTHETIC_PROBE",L"D:\\isolated"},[](IDispatch*,const TargetIdentity&){return true;});
   Registration actual_adapter(ole);auto events=actual_adapter.tick({{"FAILUSDT",true},{"BTCUSDT",true}});
   require(dispatch.names.size()==1&&dispatch.saves==1,"Concrete IDispatch add/readback/save");
   actual_adapter.tick({{"BTCUSDT",true}});require(dispatch.names.size()==1,"Concrete IDispatch duplicate");
   require(actual_adapter.drain_refresh().event=="REFRESH_REQUESTED"&&dispatch.refreshes==1,"Concrete RefreshAll");
   dispatch.path=L"D:\\wrong";bool wrongdb=false;try{actual_adapter.tick({{"ETHUSDT",true}});}catch(...){wrongdb=true;}require(wrongdb,"Concrete database drift");
  }
  require(dispatch.refs==1,"IDispatch resource ownership");
  std::cout<<"PASS_COMPILED_REGISTRATION_AND_REFRESH_CONTRACT\nHOST=SYNTHETIC_PORT NATIVE_AMIBROKER=NOT_RUN\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
