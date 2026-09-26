#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <stdexcept>
#include <vector>

namespace astu::ipc {

constexpr std::uint32_t kFrameMagic = 0x55545341U;  // "ASTU" little-endian
constexpr std::uint16_t kFrameVersion = 1;
constexpr std::size_t kFrameHeaderBytes = 16;
constexpr std::size_t kMaxPayloadBytes = 64 * 1024;

struct FrameHeader {
    std::uint32_t magic{kFrameMagic};
    std::uint16_t version{kFrameVersion};
    std::uint16_t flags{0};
    std::uint32_t payload_length{0};
    std::uint32_t crc32c{0};
};

inline std::uint32_t crc32c(std::span<const std::byte> bytes) noexcept {
    std::uint32_t crc = 0xffffffffU;
    for (const std::byte b : bytes) {
        crc ^= static_cast<std::uint8_t>(b);
        for (int bit = 0; bit < 8; ++bit) {
            const std::uint32_t mask = 0U - (crc & 1U);
            crc = (crc >> 1U) ^ (0x82f63b78U & mask);
        }
    }
    return ~crc;
}

inline void put_u16(std::vector<std::byte>& out, std::uint16_t value) {
    out.push_back(static_cast<std::byte>(value & 0xffU));
    out.push_back(static_cast<std::byte>((value >> 8U) & 0xffU));
}

inline void put_u32(std::vector<std::byte>& out, std::uint32_t value) {
    for (int shift = 0; shift < 32; shift += 8) {
        out.push_back(static_cast<std::byte>((value >> shift) & 0xffU));
    }
}

inline std::uint16_t get_u16(std::span<const std::byte> in, std::size_t offset) {
    return static_cast<std::uint16_t>(
        static_cast<std::uint8_t>(in[offset]) |
        (static_cast<std::uint16_t>(static_cast<std::uint8_t>(in[offset + 1])) << 8U));
}

inline std::uint32_t get_u32(std::span<const std::byte> in, std::size_t offset) {
    std::uint32_t value = 0;
    for (int shift = 0; shift < 32; shift += 8) {
        value |= static_cast<std::uint32_t>(
            static_cast<std::uint8_t>(in[offset + static_cast<std::size_t>(shift / 8)]))
            << shift;
    }
    return value;
}

inline std::vector<std::byte> encode_frame(std::span<const std::byte> payload) {
    if (payload.size() > kMaxPayloadBytes) {
        throw std::length_error("IPC payload exceeds bounded maximum");
    }
    std::vector<std::byte> out;
    out.reserve(kFrameHeaderBytes + payload.size());
    put_u32(out, kFrameMagic);
    put_u16(out, kFrameVersion);
    put_u16(out, 0);
    put_u32(out, static_cast<std::uint32_t>(payload.size()));
    put_u32(out, crc32c(payload));
    out.insert(out.end(), payload.begin(), payload.end());
    return out;
}

inline std::vector<std::byte> decode_frame(std::span<const std::byte> frame) {
    if (frame.size() < kFrameHeaderBytes) {
        throw std::invalid_argument("IPC frame truncated");
    }
    const auto magic = get_u32(frame, 0);
    const auto version = get_u16(frame, 4);
    const auto payload_length = get_u32(frame, 8);
    const auto expected_crc = get_u32(frame, 12);
    if (magic != kFrameMagic) {
        throw std::invalid_argument("IPC frame magic mismatch");
    }
    if (version != kFrameVersion) {
        throw std::invalid_argument("IPC frame version unsupported");
    }
    if (payload_length > kMaxPayloadBytes) {
        throw std::length_error("IPC frame declares oversized payload");
    }
    if (frame.size() != kFrameHeaderBytes + payload_length) {
        throw std::invalid_argument("IPC frame length mismatch");
    }
    const auto payload = frame.subspan(kFrameHeaderBytes, payload_length);
    if (crc32c(payload) != expected_crc) {
        throw std::invalid_argument("IPC frame CRC32C mismatch");
    }
    return std::vector<std::byte>(payload.begin(), payload.end());
}

}  // namespace astu::ipc
