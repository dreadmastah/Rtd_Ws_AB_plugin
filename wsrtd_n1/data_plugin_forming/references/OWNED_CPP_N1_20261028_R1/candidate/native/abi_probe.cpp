// Real Windows loader + official ADK types. NOT an AmiBroker host or acceptance.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <tchar.h>
#include "Plugin.h"
#include <iostream>
#include <stdexcept>
#include <vector>
#include <cstring>
#include <thread>
#include <atomic>
#include <cstddef>
void require(bool b,const char* msg){if(!b)throw std::runtime_error(msg);}
int main(int argc,char** argv) {
  HMODULE dll=nullptr;
  try {
    require(argc==3||argc==4,"usage: abi_probe dll scratch.sqlite [init-failure|read-failure]");
    _putenv_s("WSRTD_OWNED_SQLITE_PATH",argv[2]);
    dll=LoadLibraryExA(argv[1],nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);require(dll!=nullptr,"load failed");
    auto info=reinterpret_cast<decltype(&GetPluginInfo)>(GetProcAddress(dll,"GetPluginInfo"));
    auto init=reinterpret_cast<decltype(&Init)>(GetProcAddress(dll,"Init"));
    auto release=reinterpret_cast<decltype(&Release)>(GetProcAddress(dll,"Release"));
    auto get=reinterpret_cast<decltype(&GetQuotesEx)>(GetProcAddress(dll,"GetQuotesEx"));
    auto error=reinterpret_cast<int(*)()>(GetProcAddress(dll,"OwnedLastError"));
    require(info&&init&&release&&get&&error&&GetProcAddress(dll,"GetQuotes")&&GetProcAddress(dll,"Configure"),"exports missing");
    PluginInfo p{};require(info(&p)==1&&p.nStructSize==sizeof(p)&&p.nType==PLUGIN_TYPE_DATA,"plugin info");
    require(sizeof(Quotation)==40&&alignof(Quotation)==8&&offsetof(Quotation,Price)==8&&sizeof(PluginInfo)==152&&sizeof(InfoSite)==64,"ABI layout");
    if(argc==4){
      std::string mode(argv[3]);
      if(mode=="init-failure")require(init()==0&&error()==2,"unowned DB rejected");
      else {require(mode=="read-failure"&&init()==1,"failure fixture init");
        std::vector<Quotation> b(4);memset(b.data(),0x5a,b.size()*sizeof(Quotation));auto prior=b;
        require(get("BTCUSDT",86400,0,4,b.data(),nullptr)==1&&error()==2&&!memcmp(b.data(),prior.data(),b.size()*sizeof(Quotation)),"malformed storage must preserve caller bytes");}
      require(release()==1,"failure release");FreeLibrary(dll);dll=nullptr;std::cout<<"PASS_NATIVE_FAILURE_BOUNDARY "<<mode<<'\n';return 0;
    }
    require(init()==1&&init()==1,"idempotent init");
    std::vector<Quotation> q(1000);int n=get("BTCUSDT",86400,-1,1000,q.data(),nullptr);require(n>0&&error()==0,"recorded daily read");
    require(q[n-1].DateTime.PackDate.Year==2026&&q[n-1].DateTime.PackDate.Month==10&&q[n-1].DateTime.PackDate.Day==11,"date packing");
    require((q[n-1].DateTime.Date&DAILY_MASK)==DAILY_MASK,"daily mask");
    require(q[n-1].Price==static_cast<float>(83723.0)&&q[n-1].Volume==static_cast<float>(61419.685),"recorded values");
    // Exact first BTCUSDT record in recorded-prior-daily-frames.jsonl, 2026-10-10.
    // Copy genuine historical values into the host's prior buffer, not into SQLite.
    Quotation older{};older.DateTime.PackDate.Year=2026;older.DateTime.PackDate.Month=10;older.DateTime.PackDate.Day=10;older.DateTime.Date|=DAILY_MASK;
    older.Open=82578.5f;older.High=83137.2f;older.Low=82500.0f;older.Price=82941.0f;older.Volume=37032.69f;
    std::vector<Quotation> merged(1000);merged[0]=older;
    require(get("BTCUSDT",86400,0,1000,merged.data(),nullptr)==2&&!memcmp(&merged[0],&older,sizeof(older)),"genuine caller history survives short source");
    auto before=q;require(get("BTCUSDT",123,n-1,1000,q.data(),nullptr)==n&&error()==5&&!memcmp(q.data(),before.data(),q.size()*sizeof(Quotation)),"unsupported preserves buffer");
    require(get("BAD'",86400,n-1,1000,q.data(),nullptr)==n&&error()==2&&!memcmp(q.data(),before.data(),q.size()*sizeof(Quotation)),"exception boundary");
    std::atomic<bool> ok{true};std::atomic<int> completed{0},bounded{0};std::vector<std::thread> workers;
    for(int t=0;t<8;++t)workers.emplace_back([&](){std::vector<Quotation> b(1000);for(int i=0;i<30;++i){
      auto prior=b;int count=get("BTCUSDT",86400,-1,1000,b.data(),nullptr);int code=error();
      if(count==n&&code==0)++completed;
      else if(count==0&&(code==2||code==7)&&!memcmp(b.data(),prior.data(),b.size()*sizeof(Quotation)))++bounded;
      else ok=false;
    }});
    for(auto& t:workers)t.join();require(ok&&completed>0,"concurrent read/fail-closed boundary");
    std::cout<<"concurrent_completed="<<completed<<" cooperative_deferrals="<<bounded<<'\n';
    require(release()==1&&release()==1,"idempotent release");
    require(get("BTCUSDT",86400,n-1,1000,q.data(),nullptr)==n&&error()==1,"released read preserves buffer");
    require(init()==1&&release()==1,"restart");
    FreeLibrary(dll);dll=nullptr;
    std::cout<<"PASS_WINDOWS_X64_ADK_LOADER_ABI_AND_RECORDED_SQLITE_READ\nQuotation=40 align=8 PluginInfo=152 InfoSite=64\nConfigure/AddStockNew NOT EXECUTED; AmiBroker acceptance NOT RUN\n";return 0;
  }catch(const std::exception& e){std::cerr<<e.what()<<'\n';if(dll)FreeLibrary(dll);return 1;}
}
