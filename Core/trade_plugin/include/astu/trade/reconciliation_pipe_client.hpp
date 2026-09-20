#pragma once

#include <cstddef>
#include <span>
#include <string>
#include <utility>

#include "astu/ipc/frame.hpp"
#include "astu/ipc/named_pipe.hpp"
#include "astu/ipc/reconciliation_protocol.hpp"

namespace astu::trade {

class ReconciliationPipeClient {
public:
    explicit ReconciliationPipeClient(
        astu::ipc::NamedPipeClient transport =
            astu::ipc::NamedPipeClient{
                astu::ipc::kReconciliationPipeName})
        : transport_(std::move(transport)) {}

    astu::ipc::SimulationReconciliationResponse send(
        const astu::ipc::SimulationReconciliationRequest& request) const {
        const std::string json =
            astu::ipc::encode_reconciliation_request_json(request);
        const auto* raw =
            reinterpret_cast<const std::byte*>(json.data());
        const auto frame = astu::ipc::encode_frame(
            std::span<const std::byte>(raw, json.size()));
        const auto response_frame = transport_.request(frame);
        const auto payload =
            astu::ipc::decode_frame(response_frame);
        const std::string response_json(
            reinterpret_cast<const char*>(payload.data()),
            payload.size());
        return astu::ipc::decode_reconciliation_response_json(
            response_json);
    }

private:
    astu::ipc::NamedPipeClient transport_;
};

}  // namespace astu::trade
