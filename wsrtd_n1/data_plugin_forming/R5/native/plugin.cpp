#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <tchar.h>
#include "Plugin.h"
#include <atomic>
#include <thread>
#include <mutex>
#include <map>
#include <vector>
#include <string>
#include <algorithm>
#include <cmath>
#include <ctime>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <memory>
#include <set>
static_assert(sizeof(Quotation)==40 && alignof(Quotation)==8 && sizeof(void*)==8);
static_assert(sizeof(PluginInfo)==152 && sizeof(PluginStatus)==300);
#pragma pack(push,1)
struct Header {unsigned magic,version,count,connected;unsigned long long serial,now;char session[64],dbkey[80];};
struct Row {char symbol[32];unsigned long long stamp;double o,h,l,c,v;unsigned state,prefix;};
#pragma pack(pop)
static_assert(sizeof(Header)==176 && sizeof(Row)==88);
namespace {
constexpr unsigned ID=PIDCODE('W','F','R','5');
std::mutex guard;
std::recursive_mutex lifecycle;
struct PipeHandle {HANDLE h=INVALID_HANDLE_VALUE;explicit PipeHandle(HANDLE v):h(v){} ~PipeHandle(){if(h!=INVALID_HANDLE_VALUE)CloseHandle(h);} PipeHandle(const PipeHandle&)=delete;};
std::map<std::string,std::vector<Row>> cache;
std::thread worker;
std::atomic<bool> stopping{false}, healthy{false};
std::atomic<unsigned long long> revision{0}, callbacks{0}, notifications{0},acks{0};
std::atomic<unsigned long long> epoch{0};
std::atomic<ULONGLONG> received{0};
std::string pipeName,session,dbkey,dbpath;
DWORD ownerPID=0,uiThread=0;
unsigned long long ownerCreation=0;
HANDLE owner=nullptr,dbhandle=INVALID_HANDLE_VALUE;
HWND host=nullptr,timerWindow=nullptr;
HMODULE module=nullptr;
unsigned long long announced=0;
unsigned long long lastSerial=0,lastSnapshotTime=0;
bool lastFresh=false;
std::vector<Row> lastRows;
unsigned lastConnected=0;
unsigned attempts=0;
bool initialized=false,dispatching=false;
std::atomic<bool> bound{false};
const char* className="WSRTD_FORMING_R5_TIMER";
const char* property="WSRTD_FORMING_R5_AUTHORITY";
unsigned long long filetime(FILETIME x){return (static_cast<unsigned long long>(x.dwHighDateTime)<<32)|x.dwLowDateTime;}
unsigned long long utc(){FILETIME f{};GetSystemTimeAsFileTime(&f);return (filetime(f)-116444736000000000ULL)/10000;}
std::string env(const char* n){char b[1024]{};auto z=GetEnvironmentVariableA(n,b,sizeof(b));return z&&z<sizeof(b)?b:"";}
bool text(const char* p,size_t n){return memchr(p,0,n)!=nullptr;}
bool validSymbol(const char* p){size_t n=strlen(p);if(n<3||n>30)return false;for(size_t i=0;i<n;++i)if(!((p[i]>='A'&&p[i]<='Z')||(p[i]>='0'&&p[i]<='9')))return false;return true;}
// Every pending read has cancellation and completion before stack OVERLAPPED dies.
bool readExact(HANDLE p,void* dst,DWORD size){
 char* out=static_cast<char*>(dst);DWORD total=0;
 while(total<size&&!stopping){OVERLAPPED ov{};ov.hEvent=CreateEventA(nullptr,TRUE,FALSE,nullptr);if(!ov.hEvent)return false;
  DWORD got=0;BOOL ok=ReadFile(p,out+total,size-total,&got,&ov);
  if(!ok&&GetLastError()==ERROR_IO_PENDING){auto wait=WaitForSingleObject(ov.hEvent,200);if(wait!=WAIT_OBJECT_0){CancelIoEx(p,&ov);GetOverlappedResult(p,&ov,&got,TRUE);CloseHandle(ov.hEvent);return false;}ok=GetOverlappedResult(p,&ov,&got,FALSE);}
  CloseHandle(ov.hEvent);if(!ok||!got)return false;total+=got;
 }return total==size;
}
bool accept(const Header& h,const std::vector<Row>& rows){
 if(h.magic!=0x32434E57||h.version!=2||h.count!=rows.size()||h.connected>1||!text(h.session,64)||!text(h.dbkey,80)||session!=h.session||dbkey!=h.dbkey)return false;
 auto now=utc();if(h.now>now+2000||now>h.now+5000||h.serial<lastSerial||h.now<lastSnapshotTime)return false;
 if(lastSerial&&h.serial==lastSerial&&(h.connected!=lastConnected||rows.size()!=lastRows.size()||(!rows.empty()&&memcmp(rows.data(),lastRows.data(),rows.size()*sizeof(Row)))))return false;
 std::map<std::string,std::vector<Row>> next;
 for(const auto& r:rows){if(!text(r.symbol,32)||!validSymbol(r.symbol)||r.stamp%60000||r.stamp>=4102444800000ULL||r.state<1||r.state>3||r.prefix!=0)return false;
  if(!std::isfinite(r.o)||!std::isfinite(r.h)||!std::isfinite(r.l)||!std::isfinite(r.c)||!std::isfinite(r.v)||r.l<=0||r.h<std::max(r.o,r.c)||r.l>std::min(r.o,r.c)||r.v<0||r.h>1e30||r.v>1e30)return false;
  if(r.state==2&&(!h.connected||r.stamp!=now/60000*60000))return false;
  auto& v=next[r.symbol];if(!v.empty()&&v.back().stamp>=r.stamp)return false;v.push_back(r);
 }
 if(next.size()>1024)return false;
 std::lock_guard lock(guard);cache.swap(next);received=GetTickCount64();healthy=h.connected!=0;revision=h.serial;lastSerial=h.serial;lastSnapshotTime=h.now;lastRows=rows;lastConnected=h.connected;return true;
}
void run(){
 while(!stopping){
  try {
  PipeHandle pipe(CreateFileA(pipeName.c_str(),GENERIC_READ,0,nullptr,OPEN_EXISTING,FILE_FLAG_OVERLAPPED,nullptr));HANDLE p=pipe.h;
  bool ok=false;
  if(p!=INVALID_HANDLE_VALUE){ULONG pid=0;
   if(GetNamedPipeServerProcessId(p,&pid)&&pid==ownerPID&&WaitForSingleObject(owner,0)==WAIT_TIMEOUT){
    Header h{};if(readExact(p,&h,sizeof(h))&&h.count<=65536){std::vector<Row> rows(h.count);if(readExact(p,rows.data(),static_cast<DWORD>(rows.size()*sizeof(Row))))ok=accept(h,rows);}
   }
  }
  if(!ok)healthy=false;
  }catch(...){healthy=false;}
  for(int i=0;i<10&&!stopping;++i)Sleep(10);
 }
}
bool bindDatabase(const char* path){
 if(!path)return false;
 auto p=std::filesystem::absolute(path).lexically_normal();
 auto root=std::filesystem::path("D:/WSRTD_N1_DATA_PLUGIN_FORMING_R5/disposable");
 auto rel=p.lexically_relative(root).string();if(rel.empty()||rel.rfind("..",0)==0||rel.find(':')!=std::string::npos)return false;
 for(auto at=p;!at.empty();){auto a=GetFileAttributesA(at.string().c_str());if(a==INVALID_FILE_ATTRIBUTES||!(a&FILE_ATTRIBUTE_DIRECTORY)||(a&FILE_ATTRIBUTE_REPARSE_POINT))return false;auto parent=at.parent_path();if(parent==at)break;at=parent;}
 auto h=CreateFileA(p.string().c_str(),FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
 if(h==INVALID_HANDLE_VALUE)return false;BY_HANDLE_FILE_INFORMATION i{};if(!GetFileInformationByHandle(h,&i)){CloseHandle(h);return false;}
 char b[80]{};sprintf_s(b,"%08lx:%08lx%08lx",i.dwVolumeSerialNumber,i.nFileIndexHigh,i.nFileIndexLow);
 dbhandle=h;dbkey=b;dbpath=p.string();return true;
}
LRESULT CALLBACK proc(HWND w,UINT msg,WPARAM wp,LPARAM lp){
 if(msg!=WM_TIMER)return DefWindowProcA(w,msg,wp,lp);
 if(!bound||dispatching)return 0;
 DWORD pid=0;auto tid=GetWindowThreadProcessId(host,&pid);
 if(pid!=GetCurrentProcessId()||tid!=uiThread||GetPropA(host,property)!=timerWindow){healthy=false;return 0;}
 const bool fresh=healthy&&GetTickCount64()-received<=5000;
 auto r=revision.load();if(r!=announced||fresh!=lastFresh){announced=r;lastFresh=fresh;attempts=0;}
 if(attempts>=3)return 0;
 ++attempts;++notifications;dispatching=true;SendMessageA(host,WM_USER+13000,0,0);dispatching=false;return 0;
}
bool stop(){
 if(timerWindow&&(GetCurrentThreadId()!=uiThread||dispatching)){HMODULE pinned=nullptr;GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,reinterpret_cast<LPCSTR>(&proc),&pinned);return false;}
 ++epoch;bound=false;stopping=true;if(worker.joinable())worker.join();
 if(host&&GetPropA(host,property)==timerWindow)RemovePropA(host,property);
 if(timerWindow){KillTimer(timerWindow,1);DestroyWindow(timerWindow);timerWindow=nullptr;}
 if(module){UnregisterClassA(className,module);FreeLibrary(module);module=nullptr;}
 if(owner){CloseHandle(owner);owner=nullptr;}if(dbhandle!=INVALID_HANDLE_VALUE){CloseHandle(dbhandle);dbhandle=INVALID_HANDLE_VALUE;}
 host=nullptr;dbkey.clear();{std::lock_guard lock(guard);cache.clear();}healthy=false;return true;
}
bool start(PluginNotification* n){
 if(env("WFR5_FIXTURE_ONLY")!="1"||!bindDatabase(n->pszDatabasePath))return false;
 pipeName=env("WFR5_PIPE");session=env("WFR5_SESSION");
 if(pipeName.rfind("\\\\.\\pipe\\WSRTD_FORMING_R5_",0)!=0||pipeName.size()>180||session.size()!=32)return false;
 ownerPID=static_cast<DWORD>(std::stoul(env("WFR5_OWNER_PID")));ownerCreation=std::stoull(env("WFR5_OWNER_CREATION"));
 owner=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION|SYNCHRONIZE,FALSE,ownerPID);FILETIME c{},e{},k{},u{};
 if(!owner||!GetProcessTimes(owner,&c,&e,&k,&u)||filetime(c)!=ownerCreation)return false;
 if(n->hMainWnd){DWORD pid=0;uiThread=GetWindowThreadProcessId(n->hMainWnd,&pid);
  if(pid!=GetCurrentProcessId()||uiThread!=GetCurrentThreadId()||!n->pWorkspace||n->pWorkspace->DataSource!=ID||GetPropA(n->hMainWnd,property))return false;
  if(!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,reinterpret_cast<LPCSTR>(&proc),&module))return false;
  WNDCLASSA wc{};wc.lpfnWndProc=proc;wc.hInstance=module;wc.lpszClassName=className;if(!RegisterClassA(&wc))return false;
  timerWindow=CreateWindowExA(0,className,"",0,0,0,0,0,HWND_MESSAGE,nullptr,module,nullptr);host=n->hMainWnd;
  if(!timerWindow||!SetPropA(host,property,timerWindow)||!SetTimer(timerWindow,1,100,nullptr))return false;
 }
 stopping=false;bound=true;announced=0;lastSerial=0;lastSnapshotTime=0;lastRows.clear();lastFresh=false;attempts=0;worker=std::thread(run);return true;
}
}
PLUGINAPI int GetPluginInfo(PluginInfo* p){if(!p)return 0;PluginInfo i{};i.nStructSize=sizeof(i);i.nType=PLUGIN_TYPE_DATA;i.nVersion=50505;i.nIDCode=ID;i.nMinAmiVersion=700000;strcpy_s(i.szName,"WSRTD Forming R5 OFFLINE ONLY");strcpy_s(i.szVendor,"WSRTD");*p=i;return 1;}
PLUGINAPI int Init(){try{std::unique_lock lock(lifecycle,std::try_to_lock);if(!lock.owns_lock())return 0;initialized=true;return 1;}catch(...){return 0;}}
PLUGINAPI int Release(){try{std::unique_lock lock(lifecycle,std::try_to_lock);if(!lock.owns_lock())return 0;if(!stop())return 0;initialized=false;return 1;}catch(...){return 0;}}
PLUGINAPI int Notify(PluginNotification* n){try{
 std::unique_lock lock(lifecycle,std::try_to_lock);if(!lock.owns_lock())return 0;
 if(!n||n->nStructSize<sizeof(*n))return 0;
 if(n->nReason==REASON_STATUS_RMBCLICK)return 1;
 if(n->nReason!=REASON_DATABASE_LOADED&&n->nReason!=REASON_DATABASE_UNLOADED&&n->nReason!=REASON_SETTINGS_CHANGE)return 1;
 if(!stop())return 0;if(n->nReason==REASON_DATABASE_UNLOADED)return 1;
 if(!initialized||!start(n)){stop();return 0;}return 1;
 }catch(...){std::unique_lock lock(lifecycle,std::try_to_lock);if(lock.owns_lock())stop();return 0;}}
PLUGINAPI int GetQuotesEx(LPCTSTR ticker,int period,int,int capacity,Quotation* out,GQEContext*){try{
 const auto generation=epoch.load();++callbacks;if(!bound||!ticker||!out||(period!=60&&period!=86400)||capacity<=0||capacity>200000)return 0;
 std::unique_lock lock(guard,std::try_to_lock);if(!lock.owns_lock())return 0;
 auto it=cache.find(ticker);if(it==cache.end())return 0;
 std::vector<Quotation> response;response.reserve(std::min<size_t>(it->second.size(),capacity));
 const bool fresh=healthy&&GetTickCount64()-received<=5000;const auto minute=utc()/60000*60000;
 std::vector<Row> selected;
 if(period==60)selected=it->second;
 else {
  // UTC day aggregation requires all 1440 unique DURABLE minutes. Pending live
  // finals and forming data cannot complete a historical daily candle.
  std::map<unsigned long long,std::vector<Row>> days;
  for(const auto& r:it->second)if(r.state==1)days[r.stamp/86400000*86400000].push_back(r);
  for(const auto& item:days){const auto& v=item.second;if(v.size()!=1440)continue;
   bool complete=true;Row daily=v.front();daily.v=0;
   for(size_t i=0;i<v.size();++i){if(v[i].stamp!=item.first+i*60000){complete=false;break;}daily.h=std::max(daily.h,v[i].h);daily.l=std::min(daily.l,v[i].l);daily.v+=v[i].v;}
   if(complete&&std::isfinite(daily.v)){daily.c=v.back().c;selected.push_back(daily);}
  }
 }
 for(const auto& r:selected){if(r.state==2&&(!fresh||r.stamp!=minute))continue;
  __time64_t sec=r.stamp/1000;tm t{};if(_gmtime64_s(&t,&sec))return 0;Quotation q{};
  q.DateTime.PackDate.Year=t.tm_year+1900;q.DateTime.PackDate.Month=t.tm_mon+1;q.DateTime.PackDate.Day=t.tm_mday;q.DateTime.PackDate.Hour=t.tm_hour;q.DateTime.PackDate.Minute=t.tm_min;
  if(period==86400)q.DateTime.Date|=DAILY_MASK;
  q.Open=static_cast<float>(r.o);q.High=static_cast<float>(r.h);q.Low=static_cast<float>(r.l);q.Price=static_cast<float>(r.c);q.Volume=static_cast<float>(r.v);response.push_back(q);
 }
 if(response.size()>static_cast<size_t>(capacity))return 0; // Never silently truncate history.
 if(!bound||epoch.load()!=generation)return 0;
 std::copy(response.begin(),response.end(),out);++acks;return static_cast<int>(response.size());
 }catch(...){return 0;}}
PLUGINAPI int GetQuotes(LPCTSTR,int,int,int,QuotationFormat4*){return 0;}
PLUGINAPI int SetTimeBase(int p){return p==60||p==86400;}
PLUGINAPI int GetSymbolLimit(){return 1024;}
PLUGINAPI int Configure(LPCTSTR,InfoSite*){return 0;} // No database or registration writes.
PLUGINAPI BOOL IsBackfillComplete(LPCTSTR){return FALSE;} // No production prefix certificate exists.
PLUGINAPI RecentInfo* GetRecentInfo(LPCTSTR){return nullptr;}
PLUGINAPI int GetPluginStatus(PluginStatus* p){if(!p||p->nStructSize<sizeof(*p))return 0;PluginStatus s{};s.nStructSize=sizeof(s);s.nStatusCode=2<<28;s.clrStatusColor=RGB(220,0,0);strcpy_s(s.szShortMessage,"OFFLINE ONLY");strcpy_s(s.szLongMessage,"Synthetic receiver; full prefix and genuine producer custody NOT QUALIFIED");*p=s;return 1;}
PLUGINAPI int R5Metrics(unsigned long long* p,int n){if(!p||n!=5)return 0;p[0]=revision;p[1]=callbacks;p[2]=notifications;p[3]=acks;p[4]=healthy;return 1;}
