#include "owned_reader.h"
#include <iostream>
int main(int argc,char** argv){
  if(argc!=4){ std::cerr<<"usage: reader_probe <db> <symbol> <1m|1d>\n"; return 2; }
  auto candles=wsrtd::read_recent(argv[1],argv[2],argv[3],200000);
  std::cout<<"CANDLES="<<candles.size()<<"\n";
  if(!candles.empty())std::cout<<"LAST_DATE="<<candles.back().date_num<<" LAST_CLOSE="<<candles.back().close<<"\n";
}
