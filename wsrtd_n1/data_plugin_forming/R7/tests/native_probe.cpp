#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <tchar.h>
#include "Plugin.h"
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <string>
#include <chrono>
#include <psapi.h>
static unsigned notices=0;
LRESULT CALLBACK window(HWND h,UINT m,WPARAM w,LPARAM l){if(m==WM_USER+13000){++notices;return 0;}return DefWindowProcA(h,m,w,l);}
int main(int argc,char** argv){
 if(argc!=5)return 2;
 auto dll=LoadLibraryA(argv[1]);if(!dll)return 3;
 auto init=(decltype(&Init))GetProcAddress(dll,"Init");auto release=(decltype(&Release))GetProcAddress(dll,"Release");auto notify=(decltype(&Notify))GetProcAddress(dll,"Notify");auto quotes=(decltype(&GetQuotesEx))GetProcAddress(dll,"GetQuotesEx");
 if(!init||!release||!notify||!quotes||!init())return 4;
 WNDCLASSA wc{};wc.lpfnWndProc=window;wc.hInstance=GetModuleHandleA(nullptr);wc.lpszClassName="R2_FIXTURE_HOST";RegisterClassA(&wc);
 HWND h=CreateWindowExA(0,wc.lpszClassName,"",0,0,0,0,0,HWND_MESSAGE,nullptr,wc.hInstance,nullptr);
 _Workspace ws{};ws.DataSource=PIDCODE('W','F','R','7');PluginNotification n{};n.nStructSize=sizeof(n);n.nReason=REASON_DATABASE_LOADED;n.pszDatabasePath=argv[2];n.hMainWnd=h;n.pWorkspace=&ws;
 if(!notify(&n)){printf("notify_failed\n");release();return 5;}
 auto start=GetTickCount64();while(GetTickCount64()-start<800){MSG m;while(PeekMessageA(&m,nullptr,0,0,PM_REMOVE)){TranslateMessage(&m);DispatchMessageA(&m);}Sleep(5);}
 FILE* f=nullptr;fopen_s(&f,argv[4],"w");if(!f){release();return 6;}
 int count=atoi(argv[3]);std::vector<Quotation> q(128);double maxus=0,total=0;
 fprintf(f,"{\"rows\":[");int valid=0;
 for(int i=0;i<count;++i){std::string s=i==0?"BTCUSDT":i==1?"ETHUSDT":"SYN"+std::to_string(10000+i)+"USDT";
 auto a=std::chrono::steady_clock::now();int z=quotes(s.c_str(),60,-1,(int)q.size(),q.data(),nullptr);auto b=std::chrono::steady_clock::now();double us=std::chrono::duration<double,std::micro>(b-a).count();total+=us;if(us>maxus)maxus=us;
 if(z>0)++valid;
 fprintf(f,"%s{\"symbol\":\"%s\",\"bars\":%d,\"close\":%.9g,\"volume\":%.9g,\"open\":%.9g,\"high\":%.9g,\"low\":%.9g,\"minute\":%u}",i?",":"",s.c_str(),z,z?q[z-1].Price:0,z?q[z-1].Volume:0,z?q[z-1].Open:0,z?q[z-1].High:0,z?q[z-1].Low:0,z?(unsigned)q[z-1].DateTime.PackDate.Minute:0);
 }
 PROCESS_MEMORY_COUNTERS mem{};mem.cb=sizeof(mem);GetProcessMemoryInfo(GetCurrentProcess(),&mem,sizeof(mem));
 fprintf(f,"],\"symbols_returned\":%d,\"notifications\":%u,\"callback_mean_us\":%.3f,\"callback_max_us\":%.3f,\"native_peak_working_set_bytes\":%llu}",valid,notices,total/count,maxus,(unsigned long long)mem.PeakWorkingSetSize);fclose(f);
 n.nReason=REASON_DATABASE_UNLOADED;if(!notify(&n)||!release())return 7;
 DestroyWindow(h);UnregisterClassA(wc.lpszClassName,wc.hInstance);FreeLibrary(dll);return valid==count?0:8;
}
