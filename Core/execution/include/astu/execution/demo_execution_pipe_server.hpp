#pragma once

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <span>
#include <string>
#include <utility>
#include <vector>

#include "astu/execution/demo_execution_dispatcher.hpp"
#include "astu/ipc/demo_execution_protocol.hpp"
#include "astu/ipc/frame.hpp"
#include "astu/ipc/named_pipe.hpp"

namespace astu::execution {

class DemoExecutionPipeServer {
public:
    DemoExecutionPipeServer(
        DemoExecutionDispatcher dispatcher,
        astu::ipc::NamedPipeServer transport =
            astu::ipc::NamedPipeServer(
                astu::ipc::kDemoExecutionPipeName))
        : dispatcher_(std::move(dispatcher)),
          transport_(std::move(transport)) {}

    void serve_once() {
        transport_.serve_once(
            [this](
                const std::vector<std::byte>& request_frame) {
                astu::ipc::DemoExecutionResponse response;
                try {
                    const auto payload =
                        astu::ipc::decode_frame(request_frame);
                    const std::string json(
                        reinterpret_cast<const char*>(
                            payload.data()),
                        payload.size());
                    response =
                        dispatcher_.dispatch_json(
                            json,
                            utc_now_ms());
                } catch (const std::exception& exc) {
                    response.decision_code =
                        astu::ipc::DemoAdmissionCode::InvalidRequest;
                    response.reason =
                        std::string("frame rejected: ") +
                        exc.what();
                }

                const auto response_json =
                    astu::ipc::encode_demo_execution_response_json(
                        response);
                const auto* raw =
                    reinterpret_cast<const std::byte*>(
                        response_json.data());
                return astu::ipc::encode_frame(
                    std::span<const std::byte>(
                        raw,
                        response_json.size()));
            });
    }

private:
    static std::uint64_t utc_now_ms() {
        const auto now =
            std::chrono::system_clock::now().time_since_epoch();
        return static_cast<std::uint64_t>(
            std::chrono::duration_cast<
                std::chrono::milliseconds>(now).count());
    }

    DemoExecutionDispatcher dispatcher_;
    astu::ipc::NamedPipeServer transport_;
};

}  // namespace astu::execution
