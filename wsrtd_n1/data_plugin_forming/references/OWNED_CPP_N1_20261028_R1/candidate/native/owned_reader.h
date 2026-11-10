#pragma once
#include <cstdint>
#include <string>
#include <vector>
namespace wsrtd {
std::vector<std::string> registry(const std::string& db_path, const std::string& database_id);
struct Candle {
  int date_num{};
  int time_num{};
  float open{}, high{}, low{}, close{}, volume{}, open_interest{}, aux1{}, aux2{};
};
// Reads persistent local history. No deleting, no network and no AmiBroker host calls.
std::vector<Candle> read_recent(const std::string& db_path,
                                const std::string& database_id, const std::string& symbol,
                                const std::string& interval,
                                int max_bars);
}
