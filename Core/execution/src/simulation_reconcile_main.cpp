#include <chrono>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

#include "astu/execution/execution_journal.hpp"
#include "astu/execution/simulation_reconciliation.hpp"

namespace {

std::int64_t utc_now_ms() {
    const auto now = std::chrono::system_clock::now().time_since_epoch();
    return std::chrono::duration_cast<std::chrono::milliseconds>(now).count();
}

}  // namespace

int main(int argc, char** argv) {
    std::filesystem::path journal_path;
    std::string order_id;
    std::string event_id;
    std::string type_text;
    std::string detail{"simulation reconciliation event"};
    double cumulative_filled = 0.0;
    bool have_fill = false;

    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--journal" && i + 1 < argc) {
            journal_path = argv[++i];
        } else if (arg == "--order-id" && i + 1 < argc) {
            order_id = argv[++i];
        } else if (arg == "--event-id" && i + 1 < argc) {
            event_id = argv[++i];
        } else if (arg == "--event" && i + 1 < argc) {
            type_text = argv[++i];
        } else if (arg == "--cumulative-filled" && i + 1 < argc) {
            cumulative_filled = std::stod(argv[++i]);
            have_fill = true;
        } else if (arg == "--detail" && i + 1 < argc) {
            detail = argv[++i];
        } else {
            std::cerr << "unknown/incomplete argument: " << arg << "\n";
            return 2;
        }
    }

    if (journal_path.empty() || order_id.empty() ||
        event_id.empty() || type_text.empty()) {
        std::cerr
            << "required: --journal PATH --order-id ID --event-id ID "
            << "--event TYPE [--cumulative-filled QTY] [--detail TEXT]\n";
        return 2;
    }

    try {
        auto journal =
            std::make_shared<astu::execution::ExecutionJournal>(
                journal_path,
                100'000);
        const auto type =
            astu::execution::reconciliation_type_from_string(type_text);

        if (!have_fill) {
            cumulative_filled =
                journal->reconciled_filled_quantity(order_id);
        }

        astu::execution::SimulationReconciliationService service(journal);
        const auto state = service.apply(
            event_id,
            order_id,
            type,
            cumulative_filled,
            utc_now_ms(),
            detail);

        const auto intent = journal->simulation_order_intent(order_id);
        std::cout << "SIMULATION_RECONCILIATION=APPLIED\n";
        std::cout << "simulationOrderId=" << order_id << "\n";
        std::cout << "eventId=" << event_id << "\n";
        std::cout << "event=" << type_text << "\n";
        std::cout << "state="
                  << astu::execution::order_state_to_string(state)
                  << "\n";
        std::cout << "cumulativeFilled="
                  << journal->reconciled_filled_quantity(order_id)
                  << "\n";
        if (intent.has_value()) {
            std::cout << "orderQuantity=" << intent->quantity << "\n";
        }
        std::cout << "reconciliationEvents="
                  << journal->reconciliation_event_count() << "\n";
        std::cout << "orderTransitions="
                  << journal->order_transition_count() << "\n";
        std::cout << "exchangeSubmissionAttempted=false\n";
        std::cout << "orderRoutingEnabled=false\n";
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << "SIMULATION_RECONCILIATION=REJECTED\n";
        std::cerr << "reason=" << exc.what() << "\n";
        std::cerr << "exchangeSubmissionAttempted=false\n";
        return 3;
    }
}
