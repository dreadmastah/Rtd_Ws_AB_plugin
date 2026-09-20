#pragma once

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "astu/core/contracts.hpp"
#include "astu/ipc/flat_json.hpp"

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <bcrypt.h>
#include <winhttp.h>
#endif

namespace astu::execution {

inline constexpr std::string_view kBinanceUsdmTestnetEnvironment =
    "BINANCE_USDM_TESTNET";
inline constexpr std::string_view kBinanceUsdmDemoRestHost =
    "demo-fapi.binance.com";
inline constexpr std::string_view kBinanceUsdmLegacyTestnetRestHost =
    "testnet.binancefuture.com";
inline constexpr std::string_view kBinanceUsdmTestnetOrderPath =
    "/fapi/v1/order";

inline std::string require_testnet_rest_host(std::string host) {
    if (host != kBinanceUsdmDemoRestHost &&
        host != kBinanceUsdmLegacyTestnetRestHost) {
        throw std::invalid_argument(
            "Demo Trading REST host must be demo-fapi.binance.com "
            "or legacy testnet.binancefuture.com");
    }
    return host;
}
inline constexpr std::uint64_t kBinanceTestnetRecvWindowMs = 5000;

enum class TestnetSubmitOutcome {
    Acknowledged,
    Rejected,
    Unknown,
};

struct TestnetOrderRequest {
    std::string symbol;
    std::string exchange_side;
    double quantity{0.0};
    std::string client_order_id;
    bool reduce_only{false};
};

struct TestnetOrderQueryResult {
    bool ready{false};
    bool found{false};
    std::uint32_t http_status{0};
    std::int64_t exchange_code{0};
    std::string symbol;
    std::string exchange_order_id;
    std::string client_order_id;
    std::string exchange_status;
    double original_quantity{0.0};
    double cumulative_filled_quantity{0.0};
    std::string detail;
};

struct TestnetOrderResult {
    TestnetSubmitOutcome outcome{TestnetSubmitOutcome::Unknown};
    std::uint32_t http_status{0};
    std::int64_t exchange_code{0};
    std::string exchange_order_id;
    std::string client_order_id;
    std::string exchange_status;
    std::string detail;
};

inline std::string testnet_exchange_side(
    const astu::core::SignalIntent& intent) {
    const bool add = astu::core::increases_exposure(intent.action);
    if (intent.side == astu::core::PositionSide::Long) {
        return add ? "BUY" : "SELL";
    }
    return add ? "SELL" : "BUY";
}

inline bool testnet_reduce_only(
    const astu::core::SignalIntent& intent) noexcept {
    return !astu::core::increases_exposure(intent.action);
}

inline std::string deterministic_testnet_client_order_id(
    const std::string& internal_order_id) {
    if (internal_order_id.empty()) {
        throw std::invalid_argument("internal order id is required");
    }
    constexpr std::size_t kSuffix = 31;
    const auto suffix =
        internal_order_id.size() > kSuffix
            ? internal_order_id.substr(internal_order_id.size() - kSuffix)
            : internal_order_id;
    std::string out = "ASTU-" + suffix;
    if (out.size() > 36) {
        out.resize(36);
    }
    for (const unsigned char ch : out) {
        if (!(std::isalnum(ch) || ch == '-' || ch == '_')) {
            throw std::invalid_argument(
                "internal order id cannot form Binance client order id");
        }
    }
    return out;
}

inline std::string decimal_text(double value) {
    if (!std::isfinite(value) || value <= 0.0) {
        throw std::invalid_argument(
            "order quantity must be finite and positive");
    }

    // Binance quantity parameters are decimal strings. Avoid emitting the
    // binary floating-point round-trip tail (for example,
    // 0.10199999999999999 for the logical step-rounded value 0.102).
    std::ostringstream out;
    out << std::fixed << std::setprecision(15) << value;
    auto text = out.str();
    while (!text.empty() && text.back() == '0') {
        text.pop_back();
    }
    if (!text.empty() && text.back() == '.') {
        text.pop_back();
    }
    if (text.empty() || text == "0") {
        throw std::invalid_argument(
            "order quantity rounds to zero decimal text");
    }
    return text;
}

inline std::string build_testnet_order_query_params(
    const std::string& symbol,
    const std::string& client_order_id,
    std::uint64_t timestamp_ms) {
    if (symbol.empty() || client_order_id.empty() ||
        client_order_id.size() > 36 || timestamp_ms == 0) {
        throw std::invalid_argument(
            "invalid Testnet order query identity");
    }
    std::ostringstream out;
    out
        << "symbol=" << symbol
        << "&origClientOrderId=" << client_order_id
        << "&recvWindow=" << kBinanceTestnetRecvWindowMs
        << "&timestamp=" << timestamp_ms;
    return out.str();
}

inline std::string build_testnet_order_params(
    const TestnetOrderRequest& request,
    std::uint64_t timestamp_ms) {
    if (request.symbol.empty() ||
        (request.exchange_side != "BUY" &&
         request.exchange_side != "SELL") ||
        request.client_order_id.empty() ||
        request.client_order_id.size() > 36 ||
        timestamp_ms == 0) {
        throw std::invalid_argument("invalid Testnet order request");
    }

    std::ostringstream out;
    out
        << "symbol=" << request.symbol
        << "&side=" << request.exchange_side
        << "&type=MARKET"
        << "&quantity=" << decimal_text(request.quantity)
        << "&newClientOrderId=" << request.client_order_id
        << "&newOrderRespType=ACK";
    if (request.reduce_only) {
        out << "&reduceOnly=true";
    }
    out
        << "&recvWindow=" << kBinanceTestnetRecvWindowMs
        << "&timestamp=" << timestamp_ms;
    return out.str();
}

#ifdef _WIN32

namespace detail {

class BCryptAlgorithm {
public:
    BCryptAlgorithm() {
        const auto status = BCryptOpenAlgorithmProvider(
            &handle_,
            BCRYPT_SHA256_ALGORITHM,
            nullptr,
            BCRYPT_ALG_HANDLE_HMAC_FLAG);
        if (status < 0) {
            throw std::runtime_error(
                "BCryptOpenAlgorithmProvider(SHA256/HMAC) failed");
        }
    }
    ~BCryptAlgorithm() {
        if (handle_ != nullptr) {
            BCryptCloseAlgorithmProvider(handle_, 0);
        }
    }
    BCryptAlgorithm(const BCryptAlgorithm&) = delete;
    BCryptAlgorithm& operator=(const BCryptAlgorithm&) = delete;
    BCRYPT_ALG_HANDLE get() const noexcept { return handle_; }

private:
    BCRYPT_ALG_HANDLE handle_{nullptr};
};

class BCryptHash {
public:
    BCryptHash(
        BCRYPT_ALG_HANDLE algorithm,
        const std::string& secret) {
        DWORD object_size = 0;
        DWORD result_size = 0;
        if (BCryptGetProperty(
                algorithm,
                BCRYPT_OBJECT_LENGTH,
                reinterpret_cast<PUCHAR>(&object_size),
                sizeof(object_size),
                &result_size,
                0) < 0 ||
            object_size == 0) {
            throw std::runtime_error(
                "BCryptGetProperty(BCRYPT_OBJECT_LENGTH) failed");
        }
        object_.resize(object_size);
        const auto status = BCryptCreateHash(
            algorithm,
            &handle_,
            object_.data(),
            static_cast<ULONG>(object_.size()),
            reinterpret_cast<PUCHAR>(
                const_cast<char*>(secret.data())),
            static_cast<ULONG>(secret.size()),
            0);
        if (status < 0) {
            throw std::runtime_error("BCryptCreateHash failed");
        }
    }
    ~BCryptHash() {
        if (handle_ != nullptr) {
            BCryptDestroyHash(handle_);
        }
    }
    BCryptHash(const BCryptHash&) = delete;
    BCryptHash& operator=(const BCryptHash&) = delete;
    BCRYPT_HASH_HANDLE get() const noexcept { return handle_; }

private:
    BCRYPT_HASH_HANDLE handle_{nullptr};
    std::vector<UCHAR> object_;
};

class WinHttpHandle {
public:
    explicit WinHttpHandle(HINTERNET handle = nullptr)
        : handle_(handle) {}
    ~WinHttpHandle() {
        if (handle_ != nullptr) {
            WinHttpCloseHandle(handle_);
        }
    }
    WinHttpHandle(const WinHttpHandle&) = delete;
    WinHttpHandle& operator=(const WinHttpHandle&) = delete;
    WinHttpHandle(WinHttpHandle&& other) noexcept
        : handle_(other.handle_) {
        other.handle_ = nullptr;
    }
    WinHttpHandle& operator=(WinHttpHandle&& other) noexcept {
        if (this != &other) {
            if (handle_ != nullptr) WinHttpCloseHandle(handle_);
            handle_ = other.handle_;
            other.handle_ = nullptr;
        }
        return *this;
    }
    bool valid() const noexcept { return handle_ != nullptr; }
    HINTERNET get() const noexcept { return handle_; }

private:
    HINTERNET handle_{nullptr};
};

inline std::string hmac_sha256_hex(
    const std::string& secret,
    const std::string& payload) {
    if (secret.empty()) {
        throw std::invalid_argument("Testnet API secret is required");
    }

    BCryptAlgorithm algorithm;
    BCryptHash hash(algorithm.get(), secret);

    if (BCryptHashData(
            hash.get(),
            reinterpret_cast<PUCHAR>(
                const_cast<char*>(payload.data())),
            static_cast<ULONG>(payload.size()),
            0) < 0) {
        throw std::runtime_error("BCryptHashData failed");
    }

    std::vector<UCHAR> digest(32);
    if (BCryptFinishHash(
            hash.get(),
            digest.data(),
            static_cast<ULONG>(digest.size()),
            0) < 0) {
        throw std::runtime_error("BCryptFinishHash failed");
    }

    static constexpr char kHex[] = "0123456789abcdef";
    std::string out;
    out.reserve(digest.size() * 2);
    for (const auto byte : digest) {
        out.push_back(kHex[(byte >> 4) & 0x0f]);
        out.push_back(kHex[byte & 0x0f]);
    }
    return out;
}

inline std::string read_response_body(HINTERNET request) {
    std::string body;
    for (;;) {
        DWORD available = 0;
        if (!WinHttpQueryDataAvailable(request, &available)) {
            throw std::runtime_error(
                "WinHttpQueryDataAvailable failed");
        }
        if (available == 0) {
            break;
        }
        const auto old_size = body.size();
        body.resize(old_size + available);
        DWORD read = 0;
        if (!WinHttpReadData(
                request,
                body.data() + old_size,
                available,
                &read)) {
            throw std::runtime_error("WinHttpReadData failed");
        }
        body.resize(old_size + read);
    }
    return body;
}

inline std::string optional_string(
    const astu::ipc::JsonObject& obj,
    const std::string& key) {
    return obj.find(key) == obj.end()
        ? std::string{}
        : astu::ipc::require_string(obj, key);
}

}  // namespace detail

inline std::string hmac_sha256_hex_for_test(
    const std::string& secret,
    const std::string& payload) {
    return detail::hmac_sha256_hex(secret, payload);
}

class BinanceUsdmTestnetOrderGateway {
public:
    BinanceUsdmTestnetOrderGateway(
        std::string api_key,
        std::string api_secret,
        std::string rest_host =
            std::string(kBinanceUsdmDemoRestHost))
        : api_key_(std::move(api_key)),
          api_secret_(std::move(api_secret)),
          rest_host_(require_testnet_rest_host(
              std::move(rest_host))) {
        if (api_key_.empty() || api_secret_.empty()) {
            throw std::invalid_argument(
                "Binance Testnet API credentials are required");
        }
    }

    TestnetOrderResult submit_market(
        const TestnetOrderRequest& order,
        std::uint64_t timestamp_ms) const noexcept {
        try {
            const auto params =
                build_testnet_order_params(order, timestamp_ms);
            const auto signature =
                detail::hmac_sha256_hex(api_secret_, params);
            const auto body =
                params + "&signature=" + signature;

            detail::WinHttpHandle session(WinHttpOpen(
                L"AstuExecution/1.0",
                WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY,
                WINHTTP_NO_PROXY_NAME,
                WINHTTP_NO_PROXY_BYPASS,
                0));
            if (!session.valid()) {
                throw std::runtime_error("WinHttpOpen failed");
            }

            detail::WinHttpHandle connection(WinHttpConnect(
                session.get(),
                std::wstring(
                    rest_host_.begin(),
                    rest_host_.end()).c_str(),
                INTERNET_DEFAULT_HTTPS_PORT,
                0));
            if (!connection.valid()) {
                throw std::runtime_error("WinHttpConnect failed");
            }

            detail::WinHttpHandle request(WinHttpOpenRequest(
                connection.get(),
                L"POST",
                L"/fapi/v1/order",
                nullptr,
                WINHTTP_NO_REFERER,
                WINHTTP_DEFAULT_ACCEPT_TYPES,
                WINHTTP_FLAG_SECURE));
            if (!request.valid()) {
                throw std::runtime_error("WinHttpOpenRequest failed");
            }

            const std::wstring headers =
                L"Content-Type: application/x-www-form-urlencoded\r\n"
                L"X-MBX-APIKEY: " +
                std::wstring(api_key_.begin(), api_key_.end()) +
                L"\r\n";

            if (!WinHttpSendRequest(
                    request.get(),
                    headers.c_str(),
                    static_cast<DWORD>(-1L),
                    const_cast<char*>(body.data()),
                    static_cast<DWORD>(body.size()),
                    static_cast<DWORD>(body.size()),
                    0) ||
                !WinHttpReceiveResponse(request.get(), nullptr)) {
                throw std::runtime_error(
                    "Binance Testnet order HTTP request failed");
            }

            DWORD status = 0;
            DWORD status_size = sizeof(status);
            if (!WinHttpQueryHeaders(
                    request.get(),
                    WINHTTP_QUERY_STATUS_CODE |
                        WINHTTP_QUERY_FLAG_NUMBER,
                    WINHTTP_HEADER_NAME_BY_INDEX,
                    &status,
                    &status_size,
                    WINHTTP_NO_HEADER_INDEX)) {
                throw std::runtime_error(
                    "WinHttpQueryHeaders(status) failed");
            }

            const auto response_body =
                detail::read_response_body(request.get());

            TestnetOrderResult result;
            result.http_status = status;
            result.client_order_id = order.client_order_id;

            if (status >= 200 && status < 300) {
                const auto obj =
                    astu::ipc::FlatJsonParser(response_body).parse();
                const auto order_id =
                    astu::ipc::require_u64(obj, "orderId");
                result.outcome = TestnetSubmitOutcome::Acknowledged;
                result.exchange_order_id = std::to_string(order_id);
                result.client_order_id =
                    detail::optional_string(obj, "clientOrderId");
                if (result.client_order_id.empty()) {
                    result.client_order_id =
                        order.client_order_id;
                }
                result.exchange_status =
                    detail::optional_string(obj, "status");
                result.detail =
                    "Binance USD-M Testnet acknowledged MARKET order";
                return result;
            }

            if (status >= 400 && status < 500) {
                result.outcome = TestnetSubmitOutcome::Rejected;
                try {
                    const auto obj =
                        astu::ipc::FlatJsonParser(response_body).parse();
                    result.exchange_code =
                        astu::ipc::require_i64(obj, "code");
                    result.detail =
                        detail::optional_string(obj, "msg");
                } catch (...) {
                    result.detail =
                        "Binance Testnet rejected order with HTTP " +
                        std::to_string(status);
                }
                return result;
            }

            result.outcome = TestnetSubmitOutcome::Unknown;
            result.detail =
                "Binance Testnet submission outcome ambiguous HTTP " +
                std::to_string(status);
            return result;
        } catch (const std::exception& exc) {
            TestnetOrderResult result;
            result.outcome = TestnetSubmitOutcome::Unknown;
            result.client_order_id = order.client_order_id;
            result.detail =
                std::string("Binance Testnet submission outcome unknown: ") +
                exc.what();
            return result;
        }
    }

    TestnetOrderQueryResult query_order(
        const std::string& symbol,
        const std::string& client_order_id,
        std::uint64_t timestamp_ms) const noexcept {
        try {
            const auto params =
                build_testnet_order_query_params(
                    symbol,
                    client_order_id,
                    timestamp_ms);
            const auto signature =
                detail::hmac_sha256_hex(api_secret_, params);
            const auto target =
                std::wstring(kBinanceUsdmTestnetOrderPath.begin(),
                             kBinanceUsdmTestnetOrderPath.end()) +
                L"?" +
                std::wstring(params.begin(), params.end()) +
                L"&signature=" +
                std::wstring(signature.begin(), signature.end());

            detail::WinHttpHandle session(WinHttpOpen(
                L"AstuExecution/1.0",
                WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY,
                WINHTTP_NO_PROXY_NAME,
                WINHTTP_NO_PROXY_BYPASS,
                0));
            if (!session.valid()) {
                throw std::runtime_error("WinHttpOpen failed");
            }
            detail::WinHttpHandle connection(WinHttpConnect(
                session.get(),
                std::wstring(
                    rest_host_.begin(),
                    rest_host_.end()).c_str(),
                INTERNET_DEFAULT_HTTPS_PORT,
                0));
            if (!connection.valid()) {
                throw std::runtime_error("WinHttpConnect failed");
            }
            detail::WinHttpHandle request(WinHttpOpenRequest(
                connection.get(),
                L"GET",
                target.c_str(),
                nullptr,
                WINHTTP_NO_REFERER,
                WINHTTP_DEFAULT_ACCEPT_TYPES,
                WINHTTP_FLAG_SECURE));
            if (!request.valid()) {
                throw std::runtime_error("WinHttpOpenRequest failed");
            }

            const std::wstring headers =
                L"X-MBX-APIKEY: " +
                std::wstring(api_key_.begin(), api_key_.end()) +
                L"\r\n";
            if (!WinHttpSendRequest(
                    request.get(),
                    headers.c_str(),
                    static_cast<DWORD>(-1L),
                    WINHTTP_NO_REQUEST_DATA,
                    0,
                    0,
                    0) ||
                !WinHttpReceiveResponse(request.get(), nullptr)) {
                throw std::runtime_error(
                    "Binance Testnet order query HTTP request failed");
            }

            DWORD status = 0;
            DWORD status_size = sizeof(status);
            if (!WinHttpQueryHeaders(
                    request.get(),
                    WINHTTP_QUERY_STATUS_CODE |
                        WINHTTP_QUERY_FLAG_NUMBER,
                    WINHTTP_HEADER_NAME_BY_INDEX,
                    &status,
                    &status_size,
                    WINHTTP_NO_HEADER_INDEX)) {
                throw std::runtime_error(
                    "WinHttpQueryHeaders(status) failed");
            }

            const auto body =
                detail::read_response_body(request.get());
            TestnetOrderQueryResult result;
            result.http_status = status;
            result.symbol = symbol;
            result.client_order_id = client_order_id;

            if (status >= 200 && status < 300) {
                const auto obj =
                    astu::ipc::FlatJsonParser(body).parse();
                result.ready = true;
                result.found = true;
                result.exchange_order_id =
                    std::to_string(
                        astu::ipc::require_u64(obj, "orderId"));
                result.client_order_id =
                    astu::ipc::require_string(
                        obj, "clientOrderId");
                result.exchange_status =
                    astu::ipc::require_string(obj, "status");
                result.original_quantity =
                    std::stod(
                        astu::ipc::require_string(
                            obj, "origQty"));
                result.cumulative_filled_quantity =
                    std::stod(
                        astu::ipc::require_string(
                            obj, "executedQty"));
                if (!std::isfinite(result.original_quantity) ||
                    result.original_quantity <= 0.0 ||
                    !std::isfinite(
                        result.cumulative_filled_quantity) ||
                    result.cumulative_filled_quantity < 0.0 ||
                    result.cumulative_filled_quantity >
                        result.original_quantity + 1e-12) {
                    throw std::runtime_error(
                        "Binance Testnet order query returned invalid quantities");
                }
                result.detail =
                    "authoritative Binance USD-M Testnet order query";
                return result;
            }

            if (status >= 400 && status < 500) {
                try {
                    const auto obj =
                        astu::ipc::FlatJsonParser(body).parse();
                    result.exchange_code =
                        astu::ipc::require_i64(obj, "code");
                    result.detail =
                        detail::optional_string(obj, "msg");
                } catch (...) {
                    result.detail =
                        "Binance Testnet order query rejected with HTTP " +
                        std::to_string(status);
                }
                // Binance -2013 means the queried order identity is not
                // currently known. This is authoritative absence, not proof
                // that a recently ambiguous submission never reached the
                // exchange, so callers keep the internal order UNKNOWN.
                result.ready = true;
                result.found = false;
                return result;
            }

            result.detail =
                "Binance Testnet order query ambiguous HTTP " +
                std::to_string(status);
            return result;
        } catch (const std::exception& exc) {
            TestnetOrderQueryResult result;
            result.symbol = symbol;
            result.client_order_id = client_order_id;
            result.detail =
                std::string(
                    "Binance Testnet order query unavailable: ") +
                exc.what();
            return result;
        }
    }

private:
    std::string api_key_;
    std::string api_secret_;
    std::string rest_host_;
};

#else

inline std::string hmac_sha256_hex_for_test(
    const std::string&,
    const std::string&) {
    throw std::runtime_error(
        "Binance Testnet HMAC gateway requires Windows");
}

class BinanceUsdmTestnetOrderGateway {
public:
    BinanceUsdmTestnetOrderGateway(
        std::string,
        std::string,
        std::string = std::string(kBinanceUsdmDemoRestHost)) {
        throw std::runtime_error(
            "Binance Testnet order gateway requires Windows");
    }
};

#endif

}  // namespace astu::execution
