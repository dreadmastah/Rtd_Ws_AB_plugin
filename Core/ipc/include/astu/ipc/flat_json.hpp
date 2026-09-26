#pragma once

#include <cctype>
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <unordered_map>

namespace astu::ipc {

struct JsonScalar {
    enum class Kind { String, Number, Boolean, Null };
    Kind kind{Kind::Null};
    std::string text;
};

using JsonObject = std::unordered_map<std::string, JsonScalar>;

inline std::string json_escape(std::string_view value) {
    std::string out;
    out.reserve(value.size() + 8);
    for (const unsigned char c : value) {
        switch (c) {
        case '"': out += "\\\""; break;
        case '\\': out += "\\\\"; break;
        case '\b': out += "\\b"; break;
        case '\f': out += "\\f"; break;
        case '\n': out += "\\n"; break;
        case '\r': out += "\\r"; break;
        case '\t': out += "\\t"; break;
        default:
            if (c < 0x20U) {
                throw std::invalid_argument("JSON string contains unsupported control byte");
            }
            out.push_back(static_cast<char>(c));
        }
    }
    return out;
}

class FlatJsonParser {
public:
    explicit FlatJsonParser(std::string_view text) : text_(text) {}

    JsonObject parse() {
        JsonObject out;
        skip_ws();
        expect('{');
        skip_ws();
        if (peek('}')) {
            ++pos_;
            finish();
            return out;
        }
        while (true) {
            skip_ws();
            const std::string key = parse_string();
            skip_ws();
            expect(':');
            skip_ws();
            auto [it, inserted] = out.emplace(key, parse_scalar());
            if (!inserted) {
                throw std::invalid_argument("duplicate JSON key: " + key);
            }
            skip_ws();
            if (peek('}')) {
                ++pos_;
                break;
            }
            expect(',');
        }
        finish();
        return out;
    }

private:
    std::string_view text_;
    std::size_t pos_{0};

    void skip_ws() {
        while (pos_ < text_.size() &&
               std::isspace(static_cast<unsigned char>(text_[pos_]))) {
            ++pos_;
        }
    }

    bool peek(char c) const {
        return pos_ < text_.size() && text_[pos_] == c;
    }

    void expect(char c) {
        if (!peek(c)) {
            throw std::invalid_argument("invalid flat JSON syntax");
        }
        ++pos_;
    }

    void finish() {
        skip_ws();
        if (pos_ != text_.size()) {
            throw std::invalid_argument("trailing data after JSON object");
        }
    }

    std::string parse_string() {
        expect('"');
        std::string out;
        while (pos_ < text_.size()) {
            const char c = text_[pos_++];
            if (c == '"') {
                return out;
            }
            if (c != '\\') {
                if (static_cast<unsigned char>(c) < 0x20U) {
                    throw std::invalid_argument("JSON control byte in string");
                }
                out.push_back(c);
                continue;
            }
            if (pos_ >= text_.size()) {
                throw std::invalid_argument("truncated JSON escape");
            }
            const char e = text_[pos_++];
            switch (e) {
            case '"': out.push_back('"'); break;
            case '\\': out.push_back('\\'); break;
            case '/': out.push_back('/'); break;
            case 'b': out.push_back('\b'); break;
            case 'f': out.push_back('\f'); break;
            case 'n': out.push_back('\n'); break;
            case 'r': out.push_back('\r'); break;
            case 't': out.push_back('\t'); break;
            default:
                throw std::invalid_argument("unsupported JSON escape");
            }
        }
        throw std::invalid_argument("unterminated JSON string");
    }

    JsonScalar parse_scalar() {
        if (peek('"')) {
            return {JsonScalar::Kind::String, parse_string()};
        }
        if (text_.substr(pos_, 4) == "true") {
            pos_ += 4;
            return {JsonScalar::Kind::Boolean, "true"};
        }
        if (text_.substr(pos_, 5) == "false") {
            pos_ += 5;
            return {JsonScalar::Kind::Boolean, "false"};
        }
        if (text_.substr(pos_, 4) == "null") {
            pos_ += 4;
            return {JsonScalar::Kind::Null, ""};
        }

        const std::size_t start = pos_;
        while (pos_ < text_.size()) {
            const char c = text_[pos_];
            if (std::isdigit(static_cast<unsigned char>(c)) ||
                c == '-' || c == '+' || c == '.' || c == 'e' || c == 'E') {
                ++pos_;
            } else {
                break;
            }
        }
        if (pos_ == start) {
            throw std::invalid_argument("flat JSON supports only scalar values");
        }
        return {JsonScalar::Kind::Number, std::string(text_.substr(start, pos_ - start))};
    }
};

inline const JsonScalar& require_key(const JsonObject& obj, std::string_view key) {
    const auto it = obj.find(std::string(key));
    if (it == obj.end()) {
        throw std::invalid_argument("missing JSON key: " + std::string(key));
    }
    return it->second;
}

inline std::string require_string(const JsonObject& obj, std::string_view key) {
    const auto& v = require_key(obj, key);
    if (v.kind != JsonScalar::Kind::String) {
        throw std::invalid_argument("JSON key is not string: " + std::string(key));
    }
    return v.text;
}

inline bool require_bool(const JsonObject& obj, std::string_view key) {
    const auto& v = require_key(obj, key);
    if (v.kind != JsonScalar::Kind::Boolean) {
        throw std::invalid_argument("JSON key is not boolean: " + std::string(key));
    }
    return v.text == "true";
}

inline std::uint64_t require_u64(const JsonObject& obj, std::string_view key) {
    const auto& v = require_key(obj, key);
    if (v.kind != JsonScalar::Kind::Number || v.text.empty() || v.text.front() == '-') {
        throw std::invalid_argument("JSON key is not unsigned integer: " + std::string(key));
    }
    std::size_t used = 0;
    const unsigned long long value = std::stoull(v.text, &used, 10);
    if (used != v.text.size()) {
        throw std::invalid_argument("JSON unsigned integer invalid: " + std::string(key));
    }
    return static_cast<std::uint64_t>(value);
}

inline std::int64_t require_i64(const JsonObject& obj, std::string_view key) {
    const auto& v = require_key(obj, key);
    if (v.kind != JsonScalar::Kind::Number || v.text.empty()) {
        throw std::invalid_argument("JSON key is not integer: " + std::string(key));
    }
    std::size_t used = 0;
    const long long value = std::stoll(v.text, &used, 10);
    if (used != v.text.size()) {
        throw std::invalid_argument("JSON integer invalid: " + std::string(key));
    }
    return static_cast<std::int64_t>(value);
}

inline double require_double(const JsonObject& obj, std::string_view key) {
    const auto& v = require_key(obj, key);
    if (v.kind != JsonScalar::Kind::Number || v.text.empty()) {
        throw std::invalid_argument("JSON key is not number: " + std::string(key));
    }
    std::size_t used = 0;
    const double value = std::stod(v.text, &used);
    if (used != v.text.size()) {
        throw std::invalid_argument("JSON number invalid: " + std::string(key));
    }
    return value;
}

}  // namespace astu::ipc
