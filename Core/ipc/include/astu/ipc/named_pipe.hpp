#pragma once

#include <cstddef>
#include <cstdint>
#include <span>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "astu/ipc/frame.hpp"

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <sddl.h>
#endif

namespace astu::ipc {

inline constexpr wchar_t kExecutionPipeName[] = L"\\\\.\\pipe\\AstuExecutionSim.v1";
inline constexpr wchar_t kReconciliationPipeName[] =
    L"\\\\.\\pipe\\AstuExecutionReconcileSim.v1";
inline constexpr wchar_t kDemoExecutionPipeName[] =
    L"\\\\.\\pipe\\AstuExecutionDemo.v1";

#ifdef _WIN32

class WinHandle {
public:
    explicit WinHandle(HANDLE handle = INVALID_HANDLE_VALUE) : handle_(handle) {}
    ~WinHandle() {
        if (valid()) {
            CloseHandle(handle_);
        }
    }
    WinHandle(const WinHandle&) = delete;
    WinHandle& operator=(const WinHandle&) = delete;
    WinHandle(WinHandle&& other) noexcept : handle_(other.handle_) {
        other.handle_ = INVALID_HANDLE_VALUE;
    }
    WinHandle& operator=(WinHandle&& other) noexcept {
        if (this != &other) {
            if (valid()) CloseHandle(handle_);
            handle_ = other.handle_;
            other.handle_ = INVALID_HANDLE_VALUE;
        }
        return *this;
    }
    bool valid() const noexcept {
        return handle_ != nullptr && handle_ != INVALID_HANDLE_VALUE;
    }
    HANDLE get() const noexcept { return handle_; }

private:
    HANDLE handle_;
};

inline std::wstring sid_to_string(PSID sid) {
    LPWSTR raw = nullptr;
    if (!ConvertSidToStringSidW(sid, &raw)) {
        throw std::runtime_error(
            "ConvertSidToStringSidW failed error=" +
            std::to_string(GetLastError()));
    }

    std::wstring value;
    try {
        value.assign(raw);
    } catch (...) {
        LocalFree(raw);
        throw;
    }
    LocalFree(raw);
    return value;
}

inline std::wstring current_process_user_sid_string() {
    HANDLE raw_token = INVALID_HANDLE_VALUE;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &raw_token)) {
        throw std::runtime_error(
            "OpenProcessToken failed error=" +
            std::to_string(GetLastError()));
    }
    WinHandle token(raw_token);

    DWORD bytes = 0;
    (void)GetTokenInformation(token.get(), TokenUser, nullptr, 0, &bytes);
    const DWORD size_error = GetLastError();
    if (bytes == 0 || size_error != ERROR_INSUFFICIENT_BUFFER) {
        throw std::runtime_error(
            "GetTokenInformation size query failed error=" +
            std::to_string(size_error));
    }

    std::vector<std::byte> buffer(bytes);
    if (!GetTokenInformation(
            token.get(),
            TokenUser,
            buffer.data(),
            bytes,
            &bytes)) {
        throw std::runtime_error(
            "GetTokenInformation failed error=" +
            std::to_string(GetLastError()));
    }

    const auto* token_user =
        reinterpret_cast<const TOKEN_USER*>(buffer.data());
    return sid_to_string(token_user->User.Sid);
}

class PipeSecurityAttributes {
public:
    PipeSecurityAttributes() {
        const std::wstring sddl =
            L"D:P(A;;GA;;;" + current_process_user_sid_string() + L")";
        if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(
                sddl.c_str(),
                SDDL_REVISION_1,
                &descriptor_,
                nullptr)) {
            throw std::runtime_error(
                "ConvertStringSecurityDescriptorToSecurityDescriptorW failed error=" +
                std::to_string(GetLastError()));
        }

        attributes_.nLength = sizeof(attributes_);
        attributes_.lpSecurityDescriptor = descriptor_;
        attributes_.bInheritHandle = FALSE;
    }

    ~PipeSecurityAttributes() {
        if (descriptor_ != nullptr) {
            LocalFree(descriptor_);
        }
    }

    PipeSecurityAttributes(const PipeSecurityAttributes&) = delete;
    PipeSecurityAttributes& operator=(const PipeSecurityAttributes&) = delete;

    SECURITY_ATTRIBUTES* get() noexcept { return &attributes_; }
    PSECURITY_DESCRIPTOR descriptor() const noexcept { return descriptor_; }

private:
    PSECURITY_DESCRIPTOR descriptor_{nullptr};
    SECURITY_ATTRIBUTES attributes_{};
};

inline constexpr DWORD kNamedPipeOpenMode =
    PIPE_ACCESS_DUPLEX | FILE_FLAG_FIRST_PIPE_INSTANCE;
inline constexpr DWORD kNamedPipeMode =
    PIPE_TYPE_BYTE |
    PIPE_READMODE_BYTE |
    PIPE_WAIT |
    PIPE_REJECT_REMOTE_CLIENTS;

inline WinHandle create_secure_named_pipe(const std::wstring& pipe_name) {
    PipeSecurityAttributes security;
    WinHandle pipe(CreateNamedPipeW(
        pipe_name.c_str(),
        kNamedPipeOpenMode,
        kNamedPipeMode,
        1,
        static_cast<DWORD>(kFrameHeaderBytes + kMaxPayloadBytes),
        static_cast<DWORD>(kFrameHeaderBytes + kMaxPayloadBytes),
        5000,
        security.get()));
    if (!pipe.valid()) {
        throw std::runtime_error(
            "CreateNamedPipeW failed error=" +
            std::to_string(GetLastError()));
    }
    return pipe;
}

inline void write_all(HANDLE handle, std::span<const std::byte> bytes) {
    std::size_t offset = 0;
    while (offset < bytes.size()) {
        const DWORD chunk = static_cast<DWORD>(
            (bytes.size() - offset) > 0x7fffffffU ? 0x7fffffffU : (bytes.size() - offset));
        DWORD written = 0;
        if (!WriteFile(handle, bytes.data() + offset, chunk, &written, nullptr) || written == 0) {
            throw std::runtime_error("Named Pipe WriteFile failed");
        }
        offset += written;
    }
}

inline void read_exact(HANDLE handle, std::span<std::byte> bytes) {
    std::size_t offset = 0;
    while (offset < bytes.size()) {
        const DWORD chunk = static_cast<DWORD>(
            (bytes.size() - offset) > 0x7fffffffU ? 0x7fffffffU : (bytes.size() - offset));
        DWORD read = 0;
        if (!ReadFile(handle, bytes.data() + offset, chunk, &read, nullptr) || read == 0) {
            throw std::runtime_error("Named Pipe ReadFile failed");
        }
        offset += read;
    }
}

inline std::vector<std::byte> read_one_frame(HANDLE handle) {
    std::vector<std::byte> frame(kFrameHeaderBytes);
    read_exact(handle, frame);
    const std::uint32_t payload_length = get_u32(frame, 8);
    if (payload_length > kMaxPayloadBytes) {
        throw std::length_error("Named Pipe frame payload exceeds maximum");
    }
    frame.resize(kFrameHeaderBytes + payload_length);
    if (payload_length > 0) {
        read_exact(
            handle,
            std::span<std::byte>(frame.data() + kFrameHeaderBytes, payload_length));
    }
    return frame;
}

class NamedPipeClient {
public:
    explicit NamedPipeClient(std::wstring pipe_name = kExecutionPipeName)
        : pipe_name_(std::move(pipe_name)) {}

    std::vector<std::byte> request(
        std::span<const std::byte> frame,
        DWORD timeout_ms = 5000) const {
        const ULONGLONG deadline = GetTickCount64() + timeout_ms;
        WinHandle handle;

        for (;;) {
            HANDLE raw = CreateFileW(
                pipe_name_.c_str(),
                GENERIC_READ | GENERIC_WRITE,
                0,
                nullptr,
                OPEN_EXISTING,
                FILE_ATTRIBUTE_NORMAL,
                nullptr);
            if (raw != INVALID_HANDLE_VALUE) {
                handle = WinHandle(raw);
                break;
            }

            const DWORD error = GetLastError();
            if (error != ERROR_PIPE_BUSY && error != ERROR_FILE_NOT_FOUND) {
                throw std::runtime_error(
                    "CreateFileW for Named Pipe failed error=" +
                    std::to_string(error));
            }

            const ULONGLONG now = GetTickCount64();
            if (now >= deadline) {
                throw std::runtime_error(
                    "Named Pipe unavailable before timeout");
            }

            const DWORD remaining = static_cast<DWORD>(
                (deadline - now) > 250ULL ? 250ULL : (deadline - now));
            if (error == ERROR_PIPE_BUSY) {
                (void)WaitNamedPipeW(pipe_name_.c_str(), remaining);
            } else {
                Sleep(remaining > 25U ? 25U : remaining);
            }
        }
        DWORD mode = PIPE_READMODE_BYTE;
        if (!SetNamedPipeHandleState(handle.get(), &mode, nullptr, nullptr)) {
            throw std::runtime_error(
                "SetNamedPipeHandleState failed error=" +
                std::to_string(GetLastError()));
        }
        write_all(handle.get(), frame);
        return read_one_frame(handle.get());
    }

private:
    std::wstring pipe_name_;
};

class NamedPipeServer {
public:
    explicit NamedPipeServer(std::wstring pipe_name = kExecutionPipeName)
        : pipe_name_(std::move(pipe_name)) {}

    template <typename Handler>
    void serve_once(Handler&& handler) const {
        WinHandle pipe = create_secure_named_pipe(pipe_name_);

        const BOOL connected =
            ConnectNamedPipe(pipe.get(), nullptr) ? TRUE :
            (GetLastError() == ERROR_PIPE_CONNECTED ? TRUE : FALSE);
        if (!connected) {
            throw std::runtime_error("ConnectNamedPipe failed");
        }

        const auto request_frame = read_one_frame(pipe.get());
        const auto response_frame = handler(request_frame);
        write_all(pipe.get(), response_frame);
        FlushFileBuffers(pipe.get());
        DisconnectNamedPipe(pipe.get());
    }

private:
    std::wstring pipe_name_;
};

#else

class NamedPipeClient {
public:
    explicit NamedPipeClient(std::wstring = kExecutionPipeName) {}
    std::vector<std::byte> request(
        std::span<const std::byte>,
        std::uint32_t = 5000) const {
        throw std::runtime_error("Windows Named Pipe transport requires _WIN32");
    }
};

class NamedPipeServer {
public:
    explicit NamedPipeServer(std::wstring = kExecutionPipeName) {}
    template <typename Handler>
    void serve_once(Handler&&) const {
        throw std::runtime_error("Windows Named Pipe transport requires _WIN32");
    }
};

#endif

}  // namespace astu::ipc
