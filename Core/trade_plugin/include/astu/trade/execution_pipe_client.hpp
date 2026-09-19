#pragma once

#include <cstddef>
#include <span>
#include <string>
#include <utility>

#include "astu/ipc/frame.hpp"
#include "astu/ipc/named_pipe.hpp"
#include "astu/ipc/simulation_protocol.hpp"

namespace astu::trade {

class ExecutionPipeClient {
public:
    explicit ExecutionPipeClient(
        astu::ipc::NamedPipeClient transport = astu::ipc::NamedPipeClient{})
        : transport_(std::move(transport)) {}

    astu::ipc::SimulationResponse send(
        const astu::ipc::SimulationRequest& request) const {
        const std::string json = astu::ipc::encode_request_json(request);
        const auto* raw = reinterpret_cast<const std::byte*>(json.data());
        const auto frame = astu::ipc::encode_frame(
            std::span<const std::byte>(raw, json.size()));
        const auto response_frame = transport_.request(frame);
        const auto response_payload = astu::ipc::decode_frame(response_frame);
        const std::string response_json(
            reinterpret_cast<const char*>(response_payload.data()),
            response_payload.size());
        auto response = astu::ipc::decode_response_json(response_json);
        if (response.request_id != request.request_id) {
            throw std::runtime_error("Execution response requestId mismatch");
        }
        if (!response.signal_id.empty() && response.signal_id != request.intent.signal_id) {
            throw std::runtime_error("Execution response signalId mismatch");
        }
        return response;
    }

private:
    astu::ipc::NamedPipeClient transport_;
};

}  // namespace astu::trade
