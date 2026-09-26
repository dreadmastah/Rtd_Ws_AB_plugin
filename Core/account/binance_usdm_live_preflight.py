"""Pure, offline aggregation of USD-M LIVE readiness facts.

This module reports readiness only. It does not grant or exercise LIVE authority.
The caller supplies normalized facts; no credentials, network calls, or runtime
state are read here.
"""
from __future__ import annotations

from dataclasses import dataclass

import binance_usdm_credential_binding as binding


@dataclass(frozen=True)
class LivePreflightInput:
    environment: str | None = None
    credential_profile: str | None = None
    rest_base_url: str | None = None
    private_ws_template: str | None = None
    configuration_valid: str | None = None
    workflow_valid: str | None = None
    registry_valid: str | None = None
    credential_presence_valid: str | None = None
    live_enabled: str | None = None
    reconciliation_ready: str | None = None
    risk_limits_ready: str | None = None
    process_instance_ready: str | None = None
    data_connectivity_ready: str | None = None
    persistence_ready: str | None = None


@dataclass(frozen=True)
class LivePreflightCheckResult:
    check_id: str
    status: str
    reason_code: str
    required: bool
    source_class: str


@dataclass(frozen=True)
class LivePreflightResult:
    environment: str
    overall_status: str
    check_results: tuple[LivePreflightCheckResult, ...]
    failed_check_ids: tuple[str, ...]
    reason_summary: tuple[str, ...]
    readiness_state: str
    armed: bool


# Order and source classes are the frozen PF01-PF13 applicability contract.
_CHECKS = (
    ("LIVE_ENVIRONMENT", "REQUIRED_EXISTING_CHECK_REUSE"),
    ("CONFIGURATION_VALID", "REQUIRED_NEW_INPUT_CONTRACT"),
    ("WORKFLOW_VALID", "REQUIRED_NEW_INPUT_CONTRACT"),
    ("REGISTRY_VALID", "REQUIRED_NEW_INPUT_CONTRACT"),
    ("LIVE_CREDENTIAL_BINDING", "REQUIRED_EXISTING_CHECK_REUSE"),
    ("LIVE_CREDENTIAL_PRESENT", "REQUIRED_NEW_INPUT_CONTRACT"),
    ("ENDPOINT_PROFILE_BINDING", "REQUIRED_EXISTING_CHECK_REUSE"),
    ("LIVE_ENABLED", "REQUIRED_NEW_INPUT_CONTRACT"),
    ("RECONCILIATION_READY", "REQUIRED_EXISTING_CHECK_REUSE"),
    ("RISK_LIMITS_READY", "REQUIRED_NEW_INPUT_CONTRACT"),
    ("PROCESS_INSTANCE_READY", "REQUIRED_NEW_INPUT_CONTRACT"),
    ("DATA_CONNECTIVITY_READY", "REQUIRED_EXISTING_CHECK_REUSE"),
    ("PERSISTENCE_READY", "REQUIRED_NEW_INPUT_CONTRACT"),
)

_FACTS = (
    ("CONFIGURATION_VALID", "configuration_valid"),
    ("WORKFLOW_VALID", "workflow_valid"),
    ("REGISTRY_VALID", "registry_valid"),
    ("LIVE_CREDENTIAL_PRESENT", "credential_presence_valid"),
    ("LIVE_ENABLED", "live_enabled"),
    ("RECONCILIATION_READY", "reconciliation_ready"),
    ("RISK_LIMITS_READY", "risk_limits_ready"),
    ("PROCESS_INSTANCE_READY", "process_instance_ready"),
    ("DATA_CONNECTIVITY_READY", "data_connectivity_ready"),
    ("PERSISTENCE_READY", "persistence_ready"),
)


def _fact_reason(value: object) -> str:
    if type(value) is str and value == "PASS":
        return "READY"
    if type(value) is str and value == "FAIL":
        return "REPORTED_FAIL"
    if value is None or (type(value) is str and value == "UNKNOWN"):
        return "UNKNOWN"
    return "INVALID_STATE"


def _safe_environment(value: object) -> str:
    return value if type(value) is str and value in ("LIVE", "DEMO") else "UNBOUND"


def _result(environment: str, reasons: dict[str, str]) -> LivePreflightResult:
    checks = tuple(
        LivePreflightCheckResult(
            check_id=check_id,
            status="PASS" if reasons[check_id] == "READY" else "FAIL",
            reason_code=reasons[check_id],
            required=True,
            source_class=source_class,
        )
        for check_id, source_class in _CHECKS
    )
    failed = tuple(check.check_id for check in checks if check.status == "FAIL")
    return LivePreflightResult(
        environment=environment,
        overall_status="FAIL" if failed else "PASS",
        check_results=checks,
        failed_check_ids=failed,
        reason_summary=tuple(
            f"{check.check_id}:{check.reason_code}"
            for check in checks if check.status == "FAIL"
        ),
        readiness_state="NOT_READY" if failed else "READY_FOR_OPERATOR_ARMING",
        armed=False,
    )


def evaluate_live_preflight(input: LivePreflightInput) -> LivePreflightResult:
    """Evaluate all required LIVE checks without producing any side effect."""
    environment = "UNBOUND"
    try:
        environment = _safe_environment(input.environment)
        reasons = {
            check_id: _fact_reason(getattr(input, field))
            for check_id, field in _FACTS
        }
        reasons["LIVE_ENVIRONMENT"] = (
            "READY" if environment == "LIVE" else "NOT_LIVE"
            if environment == "DEMO" else "ENVIRONMENT_UNSUPPORTED"
        )

        if environment != "LIVE":
            reasons["LIVE_CREDENTIAL_BINDING"] = "ENVIRONMENT_NOT_LIVE"
            reasons["ENDPOINT_PROFILE_BINDING"] = "ENVIRONMENT_NOT_LIVE"
        else:
            try:
                # D1 validates the LIVE profile using its own canonical endpoints.
                # This call receives no credential values.
                binding.resolve_credential_binding(
                    environment="LIVE",
                    profile=input.credential_profile,
                    rest_base_url=binding.LIVE_REST_BASE,
                    private_ws_template=binding.LIVE_USER_STREAM_TEMPLATE,
                )
            except binding.CredentialBindingError:
                reasons["LIVE_CREDENTIAL_BINDING"] = "BINDING_REJECTED"
                reasons["ENDPOINT_PROFILE_BINDING"] = "BINDING_UNAVAILABLE"
            else:
                reasons["LIVE_CREDENTIAL_BINDING"] = "READY"
                if input.private_ws_template is None:
                    reasons["ENDPOINT_PROFILE_BINDING"] = "ENDPOINT_METADATA_MISSING"
                else:
                    try:
                        binding.resolve_credential_binding(
                            environment="LIVE",
                            profile=input.credential_profile,
                            rest_base_url=input.rest_base_url,
                            private_ws_template=input.private_ws_template,
                        )
                    except binding.CredentialBindingError:
                        reasons["ENDPOINT_PROFILE_BINDING"] = "ENDPOINT_MISMATCH"
                    else:
                        reasons["ENDPOINT_PROFILE_BINDING"] = "READY"
        return _result(environment, reasons)
    except Exception:
        # An unexpected failure is reported without exception text or input values.
        check = LivePreflightCheckResult(
            check_id="EVALUATION_EXCEPTION",
            status="FAIL",
            reason_code="EVALUATION_EXCEPTION",
            required=True,
            source_class="EVALUATOR",
        )
        return LivePreflightResult(
            environment=environment,
            overall_status="FAIL",
            check_results=(check,),
            failed_check_ids=(check.check_id,),
            reason_summary=("EVALUATION_EXCEPTION",),
            readiness_state="NOT_READY",
            armed=False,
        )
