#pragma once

#include <cstddef>
#include <deque>
#include <string>
#include <unordered_set>

namespace astu::ipc {

class IdempotencyCache {
public:
    explicit IdempotencyCache(std::size_t capacity)
        : capacity_(capacity) {}

    bool accept_once(const std::string& key) {
        if (key.empty() || capacity_ == 0) {
            return false;
        }
        if (seen_.contains(key)) {
            return false;
        }
        if (order_.size() >= capacity_) {
            seen_.erase(order_.front());
            order_.pop_front();
        }
        order_.push_back(key);
        seen_.insert(key);
        return true;
    }

    std::size_t size() const noexcept {
        return order_.size();
    }

private:
    std::size_t capacity_{0};
    std::deque<std::string> order_;
    std::unordered_set<std::string> seen_;
};

}  // namespace astu::ipc
