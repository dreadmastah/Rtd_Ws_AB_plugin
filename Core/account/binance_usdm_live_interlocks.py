"""Pure, offline authorization boundary for a future LIVE privilege transition.

An ALLOW result is a logical decision over caller-supplied readiness facts.
It does not arm a system, start execution, or perform an exchange operation.
"""
from __future__ import annotations

from dataclasses import dataclass

import binance_usdm_live_preflight as preflight


@dataclass(frozen=True)
class LiveInterlockInput:
    preflight_input: preflight.LivePreflightInput | None = None
    arm_state: str | None = None


@dataclass(frozen=True)
class LiveInterlockCheckResult:
    check_id: str
    status: str
    reason_code: str


@dataclass(frozen=True)
class LiveInterlockResult:
    decision: str
    environment: str
    arm_state: str
    preflight_overall_status: str
    check_results: tuple[LiveInterlockCheckResult, ...]
    failed_interlock_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    authorization_state: str


_PREFLIGHT_IDS = (
    "LIVE_ENVIRONMENT",
    "CONFIGURATION_VALID",
    "WORKFLOW_VALID",
    "REGISTRY_VALID",
    "LIVE_CREDENTIAL_BINDING",
    "LIVE_CREDENTIAL_PRESENT",
    "ENDPOINT_PROFILE_BINDING",
    "LIVE_ENABLED",
    "RECONCILIATION_READY",
    "RISK_LIMITS_READY",
    "PROCESS_INSTANCE_READY",
    "DATA_CONNECTIVITY_READY",
    "PERSISTENCE_READY",
)

_INTERLOCK_IDS = (
    "IL_LIVE_ENVIRONMENT",
    "IL_D1_LIVE_PROFILE",
    "IL_D2_PREFLIGHT_PASS",
    "IL_LIVE_ENABLED",
    "IL_EXPLICIT_ARM_LIVE",
    "IL_WORKFLOW_REGISTRY_READY",
    "IL_RECONCILIATION_READY",
    "IL_RISK_READY",
    "IL_PROCESS_DATA_PERSISTENCE_READY",
    "IL_FAIL_CLOSED_CONTEXT",
)

_DENIAL_REASONS = (
    "ENVIRONMENT_NOT_LIVE",
    "D1_BINDING_NOT_READY",
    "PREFLIGHT_NOT_READY",
    "LIVE_DISABLED",
    "NOT_ARMED_LIVE",
    "WORKFLOW_REGISTRY_NOT_READY",
    "RECONCILIATION_NOT_READY",
    "RISK_NOT_READY",
    "PROCESS_DATA_PERSISTENCE_NOT_READY",
    "INVALID_INTERLOCK_INPUT",
)


def _safe_environment(value: object) -> str:
    return value if type(value) is str and value in ("LIVE", "DEMO") else "UNBOUND"


def _safe_arm_state(value: object) -> str:
    return value if type(value) is str and value in ("DISARMED", "ARM_LIVE") else "UNBOUND"


def _valid_preflight(
    result: object, expected_environment: str
) -> bool:
    if type(result) is not preflight.LivePreflightResult:
        return False
    if (
        result.environment != expected_environment
        or result.overall_status not in ("PASS", "FAIL")
        or type(result.check_results) is not tuple
        or type(result.failed_check_ids) is not tuple
        or type(result.reason_summary) is not tuple
        or result.armed is not False
    ):
        return False
    if len(result.check_results) != len(_PREFLIGHT_IDS):
        return False
    for expected_id, check in zip(_PREFLIGHT_IDS, result.check_results):
        if (
            type(check) is not preflight.LivePreflightCheckResult
            or check.check_id != expected_id
            or check.required is not True
            or check.status not in ("PASS", "FAIL")
            or type(check.reason_code) is not str
            or not check.reason_code
        ):
            return False
        if (check.status == "PASS") != (check.reason_code == "READY"):
            return False
    failed = tuple(
        check.check_id for check in result.check_results if check.status == "FAIL"
    )
    if result.failed_check_ids != failed:
        return False
    if result.reason_summary != tuple(
        f"{check.check_id}:{check.reason_code}"
        for check in result.check_results if check.status == "FAIL"
    ):
        return False
    if result.overall_status != ("FAIL" if failed else "PASS"):
        return False
    return result.readiness_state == (
        "NOT_READY" if failed else "READY_FOR_OPERATOR_ARMING"
    )


def _build_result(
    snapshot: preflight.LivePreflightInput | None,
    arm_state: object,
    result: object,
    evaluation_exception: bool,
) -> LiveInterlockResult:
    environment = _safe_environment(
        snapshot.environment if type(snapshot) is preflight.LivePreflightInput
        else None
    )
    safe_arm = _safe_arm_state(arm_state)
    preflight_valid = (
        type(snapshot) is preflight.LivePreflightInput
        and not evaluation_exception
        and _valid_preflight(result, environment)
    )
    context_valid = preflight_valid and safe_arm != "UNBOUND"
    checks_by_id = (
        {check.check_id: check for check in result.check_results}
        if preflight_valid else {}
    )

    def ready(check_id: str) -> bool:
        check = checks_by_id.get(check_id)
        return check is not None and check.status == "PASS"

    conditions = (
        environment == "LIVE" and ready("LIVE_ENVIRONMENT"),
        all(ready(check_id) for check_id in (
            "LIVE_CREDENTIAL_BINDING",
            "LIVE_CREDENTIAL_PRESENT",
            "ENDPOINT_PROFILE_BINDING",
        )),
        preflight_valid and result.overall_status == "PASS",
        ready("LIVE_ENABLED"),
        safe_arm == "ARM_LIVE",
        all(ready(check_id) for check_id in (
            "CONFIGURATION_VALID", "WORKFLOW_VALID", "REGISTRY_VALID",
        )),
        ready("RECONCILIATION_READY"),
        ready("RISK_LIMITS_READY"),
        all(ready(check_id) for check_id in (
            "PROCESS_INSTANCE_READY",
            "DATA_CONNECTIVITY_READY",
            "PERSISTENCE_READY",
        )),
        context_valid,
    )
    checks = tuple(
        LiveInterlockCheckResult(
            check_id=check_id,
            status="PASS" if condition else "FAIL",
            reason_code=(
                "READY" if condition else
                "INTERLOCK_EVALUATION_EXCEPTION"
                if evaluation_exception and check_id == "IL_FAIL_CLOSED_CONTEXT"
                else _DENIAL_REASONS[index]
            ),
        )
        for index, (check_id, condition) in enumerate(zip(_INTERLOCK_IDS, conditions))
    )
    failed = tuple(check.check_id for check in checks if check.status == "FAIL")
    decision = "DENY" if failed else "ALLOW"
    return LiveInterlockResult(
        decision=decision,
        environment=environment,
        arm_state=safe_arm,
        preflight_overall_status=(
            result.overall_status if preflight_valid else "UNBOUND"
        ),
        check_results=checks,
        failed_interlock_ids=failed,
        reason_codes=tuple(
            check.reason_code for check in checks if check.status == "FAIL"
        ),
        authorization_state=(
            "LIVE_PRIVILEGE_AUTHORIZED" if decision == "ALLOW"
            else "NOT_AUTHORIZED"
        ),
    )


def evaluate_live_interlock(input: LiveInterlockInput) -> LiveInterlockResult:
    """Evaluate D2 synchronously and grant no privilege unless every gate passes."""
    snapshot = (
        input.preflight_input if type(input) is LiveInterlockInput else None
    )
    arm_state = input.arm_state if type(input) is LiveInterlockInput else None
    if type(snapshot) is not preflight.LivePreflightInput:
        return _build_result(None, arm_state, None, False)
    try:
        result = preflight.evaluate_live_preflight(snapshot)
        sanitized_exception = (
            type(result) is preflight.LivePreflightResult
            and result.failed_check_ids == ("EVALUATION_EXCEPTION",)
        )
        return _build_result(snapshot, arm_state, result, sanitized_exception)
    except Exception:
        # Never include exception text, input values, or credentials in a result.
        return _build_result(snapshot, arm_state, None, True)
