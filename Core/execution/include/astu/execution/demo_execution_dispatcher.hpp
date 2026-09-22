#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <functional>
#include <string>
#include <utility>

#include "astu/execution/execution_journal.hpp"
#include "astu/ipc/demo_execution_protocol.hpp"
#include "astu/ipc/simulation_protocol.hpp"

namespace astu::execution {

struct DemoSourceVerificationResult {
    bool verified{false};
    std::string reason;
};

class DemoSourceJournalVerifier {
public:
    explicit DemoSourceJournalVerifier(std::filesystem::path journal_path)
        : journal_path_(std::move(journal_path)) {}

    DemoSourceVerificationResult verify(
        const astu::ipc::DemoExecutionRequest& request) const {
        try {
            if (journal_path_.empty() ||
                !std::filesystem::exists(journal_path_) ||
                !std::filesystem::is_regular_file(journal_path_)) {
                return {
                    false,
                    "source execution journal unavailable",
                };
            }

            ExecutionJournal journal(journal_path_);
            const auto intent =
                journal.simulation_order_intent(
                    request.source_simulation_order_id);
            if (!intent.has_value()) {
                return {
                    false,
                    "source simulation order intent unavailable",
                };
            }

            const auto state =
                journal.order_state(
                    request.source_simulation_order_id);
            if (!state.has_value() ||
                *state != OrderState::Sizing) {
                return {
                    false,
                    "source simulation order is not in SIZING state",
                };
            }

            if (intent->signal_id != request.signal_id ||
                intent->symbol != request.symbol ||
                astu::ipc::side_to_string(intent->side) !=
                    request.side) {
                return {
                    false,
                    "source simulation identity mismatch",
                };
            }

            const double tolerance =
                std::max(
                    1e-12,
                    std::abs(intent->quantity) * 1e-9);
            if (!std::isfinite(intent->quantity) ||
                intent->quantity <= 0.0 ||
                !std::isfinite(request.quantity) ||
                std::abs(intent->quantity - request.quantity) >
                    tolerance) {
                return {
                    false,
                    "source simulation quantity mismatch",
                };
            }

            return {
                true,
                "source simulation journal identity verified",
            };
        } catch (const std::exception& exc) {
            return {
                false,
                std::string(
                    "source execution journal rejected: ") +
                    exc.what(),
            };
        }
    }

private:
    std::filesystem::path journal_path_;
};

class DemoExecutionDispatcher {
public:
    using ConvergenceProvider =
        std::function<TestnetConvergenceState()>;

    DemoExecutionDispatcher(
        astu::ipc::DemoExecutionAdmissionPolicy admission_policy,
        ConvergenceProvider convergence_provider,
        DemoSourceJournalVerifier source_verifier)
        : admission_policy_(std::move(admission_policy)),
          convergence_provider_(std::move(convergence_provider)),
          source_verifier_(std::move(source_verifier)) {
        if (!convergence_provider_) {
            throw std::invalid_argument(
                "Demo convergence provider is required");
        }
    }

    astu::ipc::DemoExecutionResponse dispatch(
        const astu::ipc::DemoExecutionRequest& request,
        std::uint64_t now_unix_ms) const {
        astu::ipc::DemoExecutionResponse response;
        response.request_id = request.request_id;
        response.source_simulation_order_id =
            request.source_simulation_order_id;

        TestnetConvergenceState convergence;
        try {
            convergence = convergence_provider_();
        } catch (const std::exception& exc) {
            response.decision_code =
                astu::ipc::DemoAdmissionCode::ConvergenceRejected;
            response.reason =
                std::string(
                    "Demo convergence provider failed: ") +
                exc.what();
            return response;
        }

        const auto admission =
            admission_policy_.evaluate(
                request,
                convergence,
                now_unix_ms);
        if (!admission.authorized) {
            response.decision_code = admission.code;
            response.reason = admission.reason;
            return response;
        }

        const auto source = source_verifier_.verify(request);
        if (!source.verified) {
            response.decision_code =
                astu::ipc::DemoAdmissionCode::SourceRejected;
            response.reason = source.reason;
            return response;
        }

        response.decision_code =
            astu::ipc::DemoAdmissionCode::RoutingNotImplemented;
        response.accepted_for_execution = false;
        response.order_submission_attempted = false;
        response.reason =
            "Demo admission and source identity verified; "
            "order router is not implemented";
        return response;
    }

    astu::ipc::DemoExecutionResponse dispatch_json(
        const std::string& json,
        std::uint64_t now_unix_ms) const {
        return dispatch(
            astu::ipc::decode_demo_execution_request_json(json),
            now_unix_ms);
    }

private:
    astu::ipc::DemoExecutionAdmissionPolicy admission_policy_;
    ConvergenceProvider convergence_provider_;
    DemoSourceJournalVerifier source_verifier_;
};

}  // namespace astu::execution
