#pragma once

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <span>
#include <string>
#include <utility>
#include <vector>

#include "astu/ipc/frame.hpp"
#include "astu/ipc/named_pipe.hpp"
#include "astu/ipc/simulation_protocol.hpp"

namespace astu::execution {

class ExecutionPipeServer {
public:
    ExecutionPipeServer(
        astu::ipc::SimulationDispatcher dispatcher,
        astu::ipc::NamedPipeServer transport = astu::ipc::NamedPipeServer{})
        : dispatcher_(std::move(dispatcher)),
          transport_(std::move(transport)) {}

    void serve_once() {
        transport_.serve_once([this](const std::vector<std::byte>& request_frame) {
            astu::ipc::SimulationResponse response;
            try {
                const auto payload = astu::ipc::decode_frame(request_frame);
                const std::string json(
                    reinterpret_cast<const char*>(payload.data()), payload.size());
                response = dispatcher_.dispatch_json(json, utc_now_ms());
            } catch (const std::exception& exc) {
                response.decision_code = astu::core::DecisionCode::FrameInvalid;
                response.reason = std::string("frame rejected: ") + exc.what();
            }

            const std::string response_json = astu::ipc::encode_response_json(response);
            const auto* raw = reinterpret_cast<const std::byte*>(response_json.data());
            return astu::ipc::encode_frame(
                std::span<const std::byte>(raw, response_json.size()));
        });
    }

private:
    static std::int64_t utc_now_ms() {
        const auto now = std::chrono::system_clock::now().time_since_epoch();
        return std::chrono::duration_cast<std::chrono::milliseconds>(now).count();
    }

    astu::ipc::SimulationDispatcher dispatcher_;
    astu::ipc::NamedPipeServer transport_;
};

}  // namespace astu::execution
