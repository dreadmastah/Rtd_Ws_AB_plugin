#include <iostream>
#include <string>

#include "astu/ipc/reconciliation_protocol.hpp"
#include "astu/trade/reconciliation_pipe_client.hpp"

int main(int argc, char** argv) {
#ifdef _WIN32
    std::string order_id;
    std::string event_id;
    std::string event;
    std::string detail{"simulation reconciliation smoke"};
    double cumulative_filled = 0.0;
    bool expect_accept = true;

    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--order-id" && i + 1 < argc) {
            order_id = argv[++i];
        } else if (arg == "--event-id" && i + 1 < argc) {
            event_id = argv[++i];
        } else if (arg == "--event" && i + 1 < argc) {
            event = argv[++i];
        } else if (arg == "--cumulative-filled" && i + 1 < argc) {
            cumulative_filled = std::stod(argv[++i]);
        } else if (arg == "--detail" && i + 1 < argc) {
            detail = argv[++i];
        } else if (arg == "--expect-rejected") {
            expect_accept = false;
        } else {
            std::cerr << "unknown/incomplete argument: " << arg << "\n";
            return 2;
        }
    }

    if (order_id.empty() || event_id.empty() || event.empty()) {
        std::cerr
            << "required: --order-id ID --event-id ID --event TYPE "
            << "[--cumulative-filled QTY] [--expect-rejected]\n";
        return 2;
    }

    try {
        astu::ipc::SimulationReconciliationRequest request;
        request.request_id = "RECON-PIPE-" + event_id;
        request.event_id = event_id;
        request.simulation_order_id = order_id;
        request.reconciliation_type =
            astu::execution::reconciliation_type_from_string(event);
        request.cumulative_filled_quantity = cumulative_filled;
        request.detail = detail;

        astu::trade::ReconciliationPipeClient client;
        const auto response = client.send(request);

        std::cout << "requestId=" << response.request_id << "\n";
        std::cout << "eventId=" << response.event_id << "\n";
        std::cout << "simulationOrderId="
                  << response.simulation_order_id << "\n";
        std::cout << "accepted="
                  << (response.accepted ? "true" : "false") << "\n";
        std::cout << "state=" << response.state << "\n";
        std::cout << "cumulativeFilled="
                  << response.cumulative_filled_quantity << "\n";
        std::cout << "reconciliationEventCount="
                  << response.reconciliation_event_count << "\n";
        std::cout << "orderTransitionCount="
                  << response.order_transition_count << "\n";
        std::cout << "exchangeSubmissionAttempted="
                  << (response.exchange_submission_attempted
                          ? "true"
                          : "false")
                  << "\n";
        std::cout << "reason=" << response.reason << "\n";

        if (response.exchange_submission_attempted) {
            return 3;
        }
        return response.accepted == expect_accept ? 0 : 1;
    } catch (const std::exception& exc) {
        std::cerr << "reconciliation pipe smoke failed: "
                  << exc.what() << "\n";
        return 2;
    }
#else
    (void)argc;
    (void)argv;
    std::cerr
        << "Simulation reconciliation Named Pipe smoke requires Windows.\n";
    return 2;
#endif
}
