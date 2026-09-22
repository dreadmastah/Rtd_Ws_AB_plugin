#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>

#include "astu/execution/demo_execution_dispatcher.hpp"
#include "astu/execution/demo_execution_pipe_server.hpp"
#include "astu/execution/testnet_convergence.hpp"
#include "astu/ipc/demo_execution_protocol.hpp"
#include "astu/ipc/named_pipe.hpp"

namespace {

struct Options {
    std::filesystem::path journal;
    std::filesystem::path convergence_state;
    std::string capability_id{"demo-execution-v1"};
    std::uint64_t request_max_age_ms{5'000};
    std::uint64_t future_skew_ms{1'000};
    std::uint64_t convergence_max_age_ms{5'000};
    bool once{false};
};

std::uint64_t parse_u64(
    const std::string& value,
    const char* name) {
    std::size_t used = 0;
    const auto parsed = std::stoull(value, &used);
    if (used != value.size() || parsed == 0) {
        throw std::invalid_argument(
            std::string(name) + " must be positive");
    }
    return parsed;
}

Options parse_args(int argc, char** argv) {
    Options options;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        auto require_value =
            [&](const char* name) -> std::string {
                if (i + 1 >= argc) {
                    throw std::invalid_argument(
                        std::string(name) +
                        " requires a value");
                }
                return argv[++i];
            };

        if (arg == "--journal") {
            options.journal =
                require_value("--journal");
        } else if (arg == "--convergence-state") {
            options.convergence_state =
                require_value("--convergence-state");
        } else if (arg == "--capability-id") {
            options.capability_id =
                require_value("--capability-id");
        } else if (arg == "--request-max-age-ms") {
            options.request_max_age_ms =
                parse_u64(
                    require_value("--request-max-age-ms"),
                    "--request-max-age-ms");
        } else if (arg == "--future-skew-ms") {
            options.future_skew_ms =
                parse_u64(
                    require_value("--future-skew-ms"),
                    "--future-skew-ms");
        } else if (arg == "--convergence-max-age-ms") {
            options.convergence_max_age_ms =
                parse_u64(
                    require_value(
                        "--convergence-max-age-ms"),
                    "--convergence-max-age-ms");
        } else if (arg == "--once") {
            options.once = true;
        } else {
            throw std::invalid_argument(
                "unknown argument: " + arg);
        }
    }

    if (options.journal.empty()) {
        throw std::invalid_argument(
            "--journal is required");
    }
    if (options.convergence_state.empty()) {
        throw std::invalid_argument(
            "--convergence-state is required");
    }
    if (!std::filesystem::exists(options.journal) ||
        !std::filesystem::is_regular_file(
            options.journal)) {
        throw std::invalid_argument(
            "execution journal does not exist");
    }
    return options;
}

std::string required_capability_token() {
    const char* raw =
        std::getenv(
            "ASTU_DEMO_EXECUTION_CAPABILITY_TOKEN");
    if (raw == nullptr) {
        throw std::invalid_argument(
            "ASTU_DEMO_EXECUTION_CAPABILITY_TOKEN "
            "is required");
    }
    return std::string(raw);
}

}  // namespace

int main(int argc, char** argv) {
#ifndef _WIN32
    (void)argc;
    (void)argv;
    std::cerr
        << "Demo execution pipe host requires Windows.\n";
    return 2;
#else
    try {
        const auto options =
            parse_args(argc, argv);
        auto capability_token =
            required_capability_token();

        astu::execution::
            FileBackedTestnetConvergenceProvider
                convergence_provider(
                    options.convergence_state,
                    options.convergence_max_age_ms);

        astu::execution::DemoExecutionDispatcher
            dispatcher(
                astu::ipc::
                    DemoExecutionAdmissionPolicy(
                        options.capability_id,
                        capability_token,
                        options.request_max_age_ms,
                        options.future_skew_ms,
                        options.convergence_max_age_ms),
                [convergence_provider]() mutable {
                    return convergence_provider();
                },
                astu::execution::
                    DemoSourceJournalVerifier(
                        options.journal));

        capability_token.assign(
            capability_token.size(),
            '\0');
        capability_token.clear();

        astu::execution::DemoExecutionPipeServer
            server(
                std::move(dispatcher),
                astu::ipc::NamedPipeServer(
                    astu::ipc::kDemoExecutionPipeName));

        std::cout
            << "ASTU_DEMO_EXECUTION_HOST=ADMISSION_ONLY\n"
            << "ASTU_DEMO_ORDER_ROUTER=NOT_IMPLEMENTED\n"
            << "ASTU_DEMO_PIPE="
            << "\\\\.\\pipe\\AstuExecutionDemo.v1\n";

        do {
            server.serve_once();
        } while (!options.once);

        return 0;
    } catch (const std::exception& exc) {
        std::cerr
            << "Demo execution host startup failed: "
            << exc.what() << "\n";
        return 1;
    }
#endif
}
