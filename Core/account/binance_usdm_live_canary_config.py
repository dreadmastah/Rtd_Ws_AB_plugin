"""Pure structural validation for a future LIVE-canary configuration.

VALID means structurally valid only. It never approves values for A5,
enables LIVE, arms a process, or consumes a trading/runtime service.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re


_AUTHORITY_STATE = "STRUCTURAL_ONLY_NOT_A5_APPROVED"
_KIND = "LIVE_CANARY_CONFIGURATION"
_MAX_NOTIONAL = Decimal("999999999999999999")
_SYMBOL = re.compile(r"^[A-Z0-9]{2,20}USDT$", re.ASCII)
_STRATEGY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$", re.ASCII)
_CHECK_IDS = (
    "CONFIG_KIND",
    "LIVE_ENVIRONMENT",
    "RESTRICTED_UNIVERSE",
    "MAX_CONCURRENT_POSITIONS",
    "MAX_NOTIONAL_USDT",
    "STRATEGY_ID",
    "STRATEGY_VERSION",
)


@dataclass(frozen=True)
class LiveCanaryConfigInput:
    config_kind: str | None = None
    environment: str | None = None
    symbols: tuple[str, ...] | None = None
    max_concurrent_positions: int | None = None
    max_notional_usdt: Decimal | None = None
    strategy_id: str | None = None
    strategy_version: str | None = None


@dataclass(frozen=True)
class LiveCanaryCheckResult:
    check_id: str
    status: str
    reason_code: str


@dataclass(frozen=True)
class LiveCanaryConfigResult:
    status: str
    check_results: tuple[LiveCanaryCheckResult, ...]
    failed_check_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    normalized_config: tuple[object, ...] | None
    configuration_identity: tuple[object, ...] | None
    authority_state: str
    can_activate_live: bool


def _symbols(value: object) -> tuple[str, tuple[str, ...] | None]:
    if value is None:
        return "MISSING", None
    if type(value) is not tuple:
        return "INVALID_TYPE", None
    if not 1 <= len(value) <= 64:
        return "OUT_OF_RANGE", None
    if any(type(symbol) is not str or not _SYMBOL.fullmatch(symbol)
           for symbol in value):
        return "MALFORMED", None
    if len(set(value)) != len(value):
        return "DUPLICATE", None
    return "VALID", tuple(sorted(value))


def _positions(value: object) -> tuple[str, int | None]:
    if value is None:
        return "MISSING", None
    if type(value) is not int:
        return "INVALID_TYPE", None
    if not 1 <= value <= 64:
        return "OUT_OF_RANGE", None
    return "VALID", value


def _notional(value: object) -> tuple[str, str | None]:
    if value is None:
        return "MISSING", None
    if type(value) is not Decimal:
        return "INVALID_TYPE", None
    if not value.is_finite():
        return "NONFINITE", None
    if value <= 0 or value > _MAX_NOTIONAL:
        return "OUT_OF_RANGE", None
    parts = value.as_tuple()
    if len(parts.digits) > 18 or parts.exponent < -8:
        return "UNSUPPORTED_PRECISION", None
    plain = format(value, "f")
    if "." in plain:
        plain = plain.rstrip("0").rstrip(".")
    return "VALID", plain


def _strategy(value: object) -> tuple[str, str | None]:
    if value is None:
        return "MISSING", None
    if type(value) is not str:
        return "INVALID_TYPE", None
    if not _STRATEGY.fullmatch(value):
        return "MALFORMED", None
    return "VALID", value


def _invalid_all(reason: str) -> LiveCanaryConfigResult:
    checks = tuple(
        LiveCanaryCheckResult(check_id, "FAIL", reason)
        for check_id in _CHECK_IDS
    )
    return LiveCanaryConfigResult(
        status="INVALID",
        check_results=checks,
        failed_check_ids=_CHECK_IDS,
        reason_codes=tuple(reason for _ in _CHECK_IDS),
        normalized_config=None,
        configuration_identity=None,
        authority_state=_AUTHORITY_STATE,
        can_activate_live=False,
    )


def validate_live_canary_config(
    config: LiveCanaryConfigInput,
) -> LiveCanaryConfigResult:
    """Validate in memory without conferring any LIVE or A5 authority."""
    if type(config) is not LiveCanaryConfigInput:
        return _invalid_all("INVALID_INPUT")
    try:
        kind_reason = (
            "MISSING" if config.config_kind is None
            else "VALID" if type(config.config_kind) is str
            and config.config_kind == _KIND else "UNSUPPORTED"
        )
        environment_reason = (
            "MISSING" if config.environment is None
            else "VALID" if type(config.environment) is str
            and config.environment == "LIVE" else "UNSUPPORTED"
        )
        universe_reason, universe = _symbols(config.symbols)
        positions_reason, positions = _positions(config.max_concurrent_positions)
        notional_reason, notional = _notional(config.max_notional_usdt)
        strategy_reason, strategy = _strategy(config.strategy_id)
        version_reason, version = _strategy(config.strategy_version)
        reasons = (
            kind_reason,
            environment_reason,
            universe_reason,
            positions_reason,
            notional_reason,
            strategy_reason,
            version_reason,
        )
        checks = tuple(
            LiveCanaryCheckResult(
                check_id,
                "PASS" if reason == "VALID" else "FAIL",
                reason,
            )
            for check_id, reason in zip(_CHECK_IDS, reasons)
        )
        failed = tuple(c.check_id for c in checks if c.status == "FAIL")
        normalized = (
            (_KIND, "LIVE", universe, positions, notional, strategy, version)
            if not failed else None
        )
        return LiveCanaryConfigResult(
            status="INVALID" if failed else "VALID",
            check_results=checks,
            failed_check_ids=failed,
            reason_codes=tuple(
                c.reason_code for c in checks if c.status == "FAIL"
            ),
            normalized_config=normalized,
            configuration_identity=normalized,
            authority_state=_AUTHORITY_STATE,
            can_activate_live=False,
        )
    except Exception:
        # Never include exception text or input data in the result.
        return _invalid_all("EVALUATION_EXCEPTION")
