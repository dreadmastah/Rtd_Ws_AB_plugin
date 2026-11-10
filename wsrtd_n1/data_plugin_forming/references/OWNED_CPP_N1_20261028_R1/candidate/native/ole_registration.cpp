#include "ole_registration.h"
#include <utility>
namespace owned {
namespace {
struct Value {
  VARIANT value;Value(){VariantInit(&value);}~Value(){VariantClear(&value);}
  Value(const Value&)=delete;Value& operator=(const Value&)=delete;
};
void invoke(IDispatch* object,const wchar_t* member,WORD flags,Value& output,VARIANT* arg=nullptr){
  if(!object)throw std::runtime_error("Null automation object");
  LPOLESTR name=const_cast<LPOLESTR>(member);DISPID id;
  if(FAILED(object->GetIDsOfNames(IID_NULL,&name,1,LOCALE_USER_DEFAULT,&id)))throw std::runtime_error("Unknown documented member");
  DISPPARAMS params{};params.rgvarg=arg;params.cArgs=arg?1:0;EXCEPINFO ex{};UINT index=0;
  HRESULT hr=object->Invoke(id,IID_NULL,LOCALE_USER_DEFAULT,flags,&params,&output.value,&ex,&index);
  if(ex.bstrSource)SysFreeString(ex.bstrSource);if(ex.bstrDescription)SysFreeString(ex.bstrDescription);if(ex.bstrHelpFile)SysFreeString(ex.bstrHelpFile);
  if(FAILED(hr))throw std::runtime_error("Automation call failed; never interpreted as missing");
}
void string_arg(Value& v,const std::string& s){
  std::wstring w(s.begin(),s.end());v.value.vt=VT_BSTR;v.value.bstrVal=SysAllocStringLen(w.data(),static_cast<UINT>(w.size()));
  if(!v.value.bstrVal)throw std::bad_alloc();
}
}
OleHost::OleHost(IDispatch* supplied,TargetIdentity identity,std::function<bool(IDispatch*,const TargetIdentity&)> binding):app(supplied),target(std::move(identity)),thread(GetCurrentThreadId()),attest(std::move(binding)){
  if(!app||!attest||!target.pid||!target.creation_time||target.executable.empty()||target.database.empty())throw std::runtime_error("UNBOUND_TARGET");
  // Verify before AddRef or any automation call. Attestation is a separate gate.
  if(!attest(app,target))throw std::runtime_error("BLOCKED_SAFE_AUTOMATION_BINDING");app->AddRef();
}
OleHost::~OleHost(){app->Release();}
void OleHost::verify_target(){
  if(GetCurrentThreadId()!=thread||!attest(app,target))throw std::runtime_error("TARGET_OR_THREAD_CHANGED");
  Value path;invoke(app,L"DatabasePath",DISPATCH_PROPERTYGET,path);
  if(path.value.vt!=VT_BSTR||!path.value.bstrVal||target.database!=path.value.bstrVal)throw std::runtime_error("DATABASE_PATH_MISMATCH");
}
bool OleHost::exists(const std::string& symbol){
  verify_target();Value stocks,item,arg;invoke(app,L"Stocks",DISPATCH_PROPERTYGET,stocks);
  if(stocks.value.vt!=VT_DISPATCH)throw std::runtime_error("Stocks is not IDispatch");string_arg(arg,symbol);
  invoke(stocks.value.pdispVal,L"Item",DISPATCH_PROPERTYGET,item,&arg.value);
  if(item.value.vt==VT_EMPTY||item.value.vt==VT_NULL||(item.value.vt==VT_DISPATCH&&!item.value.pdispVal))return false;
  if(item.value.vt!=VT_DISPATCH)throw std::runtime_error("Unexpected stock object");
  Value ticker;invoke(item.value.pdispVal,L"Ticker",DISPATCH_PROPERTYGET,ticker);
  std::wstring expected(symbol.begin(),symbol.end());
  if(ticker.value.vt!=VT_BSTR||!ticker.value.bstrVal||expected!=ticker.value.bstrVal)throw std::runtime_error("Wrong stock identity");return true;
}
void OleHost::add(const std::string& symbol){
  verify_target();Value stocks,added,arg;invoke(app,L"Stocks",DISPATCH_PROPERTYGET,stocks);
  if(stocks.value.vt!=VT_DISPATCH)throw std::runtime_error("Stocks is not IDispatch");string_arg(arg,symbol);
  invoke(stocks.value.pdispVal,L"Add",DISPATCH_METHOD,added,&arg.value);
  if(added.value.vt!=VT_DISPATCH||!added.value.pdispVal)throw std::runtime_error("Stocks.Add failed");
}
void OleHost::save(){verify_target();Value result;invoke(app,L"SaveDatabase",DISPATCH_METHOD,result);}
void OleHost::refresh(){verify_target();Value result;invoke(app,L"RefreshAll",DISPATCH_METHOD,result);}
}
