#include "owned_reader.h"
#include <sqlite3.h>
#include <algorithm>
#include <cmath>
#include <limits>
#include <memory>
#include <stdexcept>
#include <regex>
#include <ctime>
#include <chrono>
namespace wsrtd {
namespace {
using DB=std::unique_ptr<sqlite3,decltype(&sqlite3_close)>;
using Statement=std::unique_ptr<sqlite3_stmt,decltype(&sqlite3_finalize)>;
using Clock=std::chrono::steady_clock;
thread_local Clock::time_point deadline;
void checkpoint(){if(Clock::now()>deadline)throw std::runtime_error("Cooperative read deadline");}
int progress(void*){return Clock::now()>deadline?1:0;}
DB open(const std::string& path) {
  deadline=Clock::now()+std::chrono::milliseconds(100);
  sqlite3* raw=nullptr;
  int rc=sqlite3_open_v2(path.c_str(),&raw,SQLITE_OPEN_READONLY|SQLITE_OPEN_NOMUTEX,nullptr);
  DB db(raw,sqlite3_close);
  if(rc!=SQLITE_OK) throw std::runtime_error("SQLite open failed");
  sqlite3_busy_timeout(db.get(),0);
  sqlite3_progress_handler(db.get(),1000,progress,nullptr);
  for(const auto& check:std::vector<std::pair<const char*,int>>{{"PRAGMA application_id",1465074229},{"PRAGMA user_version",2}}) {
    sqlite3_stmt* s=nullptr;int result=sqlite3_prepare_v2(db.get(),check.first,-1,&s,nullptr);Statement stmt(s,sqlite3_finalize);
    if(result!=SQLITE_OK||sqlite3_step(stmt.get())!=SQLITE_ROW||sqlite3_column_int(stmt.get(),0)!=check.second)throw std::runtime_error("Not an owned N1 database");
  }
  return db;
}
Statement prepare(sqlite3* db,const char* sql) {
  sqlite3_stmt* raw=nullptr;int rc=sqlite3_prepare_v2(db,sql,-1,&raw,nullptr);
  Statement stmt(raw,sqlite3_finalize);
  if(rc!=SQLITE_OK)throw std::runtime_error("SQLite prepare failed");return stmt;
}
float number(sqlite3_stmt* st,int col) {
  int type=sqlite3_column_type(st,col);double n=sqlite3_column_double(st,col);
  if((type!=SQLITE_FLOAT&&type!=SQLITE_INTEGER)||!std::isfinite(n)||std::abs(n)>std::numeric_limits<float>::max())throw std::runtime_error("Invalid numeric candle");
  return static_cast<float>(n);
}
void check_date(int d,int t,const std::string& interval) {
  int y=d/10000,m=d/100%100,day=d%100;
  int days[]={0,31,28,31,30,31,30,31,31,30,31,30,31};
  if(y%4==0&&(y%100!=0||y%400==0))days[2]=29;
  if(y<1970||y>4095||m<1||m>12||day<1||day>days[m]||t<0||t/10000>23||t/100%100>59||t%100!=0||(interval=="1d"&&t!=0))throw std::runtime_error("Invalid candle date");
}
}
std::vector<std::string> registry(const std::string& path,const std::string& database_id) {
  if(database_id.empty())throw std::runtime_error("No database scope");
  auto db=open(path);auto context=prepare(db.get(),"SELECT database_id FROM database_context WHERE database_id=?");
  if(sqlite3_bind_text(context.get(),1,database_id.c_str(),-1,SQLITE_TRANSIENT)!=SQLITE_OK||sqlite3_step(context.get())!=SQLITE_ROW)throw std::runtime_error("unknown database scope");
  auto st=prepare(db.get(),"SELECT symbol FROM symbol_registry WHERE database_id=? ORDER BY symbol");
  if(sqlite3_bind_text(st.get(),1,database_id.c_str(),-1,SQLITE_TRANSIENT)!=SQLITE_OK)throw std::runtime_error("scope bind failed");
  std::vector<std::string> out;int rc;
  while((rc=sqlite3_step(st.get()))==SQLITE_ROW) {
    checkpoint();
    const auto* s=sqlite3_column_text(st.get(),0);if(!s)throw std::runtime_error("Invalid registry symbol");
    std::string symbol(reinterpret_cast<const char*>(s));
    if(!std::regex_match(symbol,std::regex("[A-Z0-9]{3,30}")))throw std::runtime_error("Invalid registry symbol");out.push_back(symbol);
  }
  if(rc!=SQLITE_DONE)throw std::runtime_error("Registry read incomplete");return out;
}
std::vector<Candle> read_recent(const std::string& path,const std::string& database_id,const std::string& symbol,const std::string& interval,int max_bars) {
  if(database_id.empty()||path.empty()||max_bars<=0||max_bars>200000||(interval!="1m"&&interval!="1d")||!std::regex_match(symbol,std::regex("[A-Z0-9]{3,30}")))throw std::invalid_argument("Invalid read request");
  auto db=open(path);
  auto st=prepare(db.get(),"SELECT date_num,time_num,o,h,l,c,v,oi,aux1,aux2,ts_ms FROM bars WHERE symbol=? AND interval=? AND database_id=? AND finalized=1 ORDER BY ts_ms DESC LIMIT ?");
  if(sqlite3_bind_text(st.get(),1,symbol.c_str(),-1,SQLITE_TRANSIENT)!=SQLITE_OK||sqlite3_bind_text(st.get(),2,interval.c_str(),-1,SQLITE_TRANSIENT)!=SQLITE_OK||sqlite3_bind_text(st.get(),3,database_id.c_str(),-1,SQLITE_TRANSIENT)!=SQLITE_OK||sqlite3_bind_int(st.get(),4,max_bars)!=SQLITE_OK)throw std::runtime_error("SQLite bind failed");
  std::vector<Candle> items;int rc;
  while((rc=sqlite3_step(st.get()))==SQLITE_ROW) {
    checkpoint();
    Candle c{};
    if(sqlite3_column_type(st.get(),0)!=SQLITE_INTEGER||sqlite3_column_type(st.get(),1)!=SQLITE_INTEGER||sqlite3_column_type(st.get(),10)!=SQLITE_INTEGER)throw std::runtime_error("Invalid date type");
    auto date64=sqlite3_column_int64(st.get(),0),time64=sqlite3_column_int64(st.get(),1),stamp=sqlite3_column_int64(st.get(),10);
    if(date64<19700101||date64>40951231||time64<0||time64>235959||stamp<0||stamp%60000)throw std::runtime_error("Timestamp out of range");
    __time64_t sec=stamp/1000;tm utc{};
    if(_gmtime64_s(&utc,&sec)||utc.tm_year+1900>4095||date64!=(utc.tm_year+1900)*10000+(utc.tm_mon+1)*100+utc.tm_mday||time64!=utc.tm_hour*10000+utc.tm_min*100+utc.tm_sec)throw std::runtime_error("Timestamp fields inconsistent");
    c.date_num=sqlite3_column_int(st.get(),0);c.time_num=sqlite3_column_int(st.get(),1);check_date(c.date_num,c.time_num,interval);
    c.open=number(st.get(),2);c.high=number(st.get(),3);c.low=number(st.get(),4);c.close=number(st.get(),5);c.volume=number(st.get(),6);c.open_interest=number(st.get(),7);c.aux1=number(st.get(),8);c.aux2=number(st.get(),9);
    if(c.low<=0||c.high<c.low||c.open<c.low||c.open>c.high||c.close<c.low||c.close>c.high||c.volume<0)throw std::runtime_error("Invalid OHLCV");items.push_back(c);
  }
  if(rc!=SQLITE_DONE)throw std::runtime_error("SQLite read incomplete");
  std::reverse(items.begin(),items.end());return items;
}
}
