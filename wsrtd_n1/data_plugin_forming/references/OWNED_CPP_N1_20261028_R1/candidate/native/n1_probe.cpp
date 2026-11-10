#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <tchar.h>
#include "Plugin.h"
#include "database_binding.h"
#include <iostream>
#include <cstddef>
int main(int argc,char**argv){
 static_assert(sizeof(InfoSite)==64&&sizeof(PluginNotification)==48&&sizeof(Quotation)==40);
 static_assert(offsetof(InfoSite,AddStockNew)==56&&offsetof(PluginNotification,pszDatabasePath)==8);
 try{if(argc==2){auto b=n1::bind_directory(argv[1]);std::cout<<b.key;return 0;}
 std::cout<<"InfoSite=64 Notification=48 Quotation=40 AddStockNew=56 DatabasePath=8\n";return 0;
 }catch(const std::exception&e){std::cerr<<e.what();return 2;}
}
