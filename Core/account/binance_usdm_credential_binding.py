"""Offline, fail-closed environment/endpoint/credential binding for USD-M readers."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping
from urllib.parse import urlsplit


DEMO_REST_BASE = "https://demo-fapi.binance.com"
DEMO_PRIVATE_WS_BASE = "wss://fstream.binancefuture.com/private/ws"
DEMO_USER_STREAM_TEMPLATE = (
    "wss://fstream.binancefuture.com/private/ws?listenKey={listenKey}"
    "&events=ORDER_TRADE_UPDATE/ACCOUNT_UPDATE"
)
LIVE_REST_BASE = "https://fapi.binance.com"
LIVE_PRIVATE_WS_BASE = "wss://fstream.binance.com/private/ws"
LIVE_USER_STREAM_TEMPLATE = (
    "wss://fstream.binance.com/private/ws?listenKey={listenKey}"
    "&events=ORDER_TRADE_UPDATE/ACCOUNT_UPDATE"
)

DEMO_KEY = "ASTU_BINANCE_TESTNET_API_KEY"
DEMO_SECRET = "ASTU_BINANCE_TESTNET_API_SECRET"
LIVE_KEY = "ASTU_BINANCE_LIVE_API_KEY"
LIVE_SECRET = "ASTU_BINANCE_LIVE_API_SECRET"
GENERIC_NAMES = ("BINANCE_API_KEY", "BINANCE_API_SECRET")

_ENVIRONMENTS = {
    "DEMO": {
        "rest": DEMO_REST_BASE,
        "private_ws_base": DEMO_PRIVATE_WS_BASE,
        "template": DEMO_USER_STREAM_TEMPLATE,
    },
    "LIVE": {
        "rest": LIVE_REST_BASE,
        "private_ws_base": LIVE_PRIVATE_WS_BASE,
        "template": LIVE_USER_STREAM_TEMPLATE,
    },
}
_PROFILES = {
    ("DEMO", "TESTNET_SIGNED_READONLY"): (DEMO_KEY, DEMO_SECRET),
    ("DEMO", "TESTNET_USER_DATA"): (DEMO_KEY,),
    ("LIVE", "LIVE_SIGNED_READONLY"): (LIVE_KEY, LIVE_SECRET),
}


class CredentialBindingError(ValueError):
    """A safe binding failure; ``reason_code`` never embeds input values."""

    def __init__(self, reason_code: str):
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class CredentialBinding:
    environment: str
    profile: str
    rest_base_url: str
    private_ws_base: str
    private_ws_template: str
    credential_names: tuple[str, ...]


def _canonical_environment(environment: str | None) -> str:
    if not environment:
        raise CredentialBindingError("ENVIRONMENT_REQUIRED")
    selected = environment.strip().upper()
    if selected not in _ENVIRONMENTS:
        raise CredentialBindingError("ENVIRONMENT_UNSUPPORTED")
    return selected


def _canonical_rest_base(value: str) -> str:
    if not isinstance(value, str):
        return ""
    candidate = value.strip().rstrip("/")
    parsed = urlsplit(candidate)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return ""
    return candidate


def resolve_credential_binding(
    *,
    environment: str | None,
    profile: str,
    rest_base_url: str,
    private_ws_template: str | None = None,
) -> CredentialBinding:
    """Validate non-secret selectors/endpoints without reading values or I/O."""
    selected = _canonical_environment(environment)
    names = _PROFILES.get((selected, profile))
    if names is None:
        raise CredentialBindingError("PROFILE_ENVIRONMENT_MISMATCH")
    family = _ENVIRONMENTS[selected]
    if _canonical_rest_base(rest_base_url) != family["rest"]:
        raise CredentialBindingError("REST_ENDPOINT_MISMATCH")
    if private_ws_template is not None and private_ws_template != family["template"]:
        raise CredentialBindingError("PRIVATE_WS_ENDPOINT_MISMATCH")
    return CredentialBinding(
        environment=selected,
        profile=profile,
        rest_base_url=family["rest"],
        private_ws_base=family["private_ws_base"],
        private_ws_template=family["template"],
        credential_names=names,
    )


def read_bound_credentials(
    binding: CredentialBinding, environ: Mapping[str, str]
) -> tuple[str, ...]:
    """Read only the selected names; reject generic compatibility variables."""
    if any(environ.get(name, "") for name in GENERIC_NAMES):
        raise CredentialBindingError("GENERIC_CREDENTIAL_FORBIDDEN")
    values = tuple(environ.get(name, "") for name in binding.credential_names)
    if any(not value for value in values):
        raise CredentialBindingError("CREDENTIAL_REFERENCE_MISSING")
    return values


def safe_diagnostic(
    *, environment: str | None, profile: str | None, reason_code: str,
    exception: BaseException | None = None,
) -> str:
    """Render identifiers and exception class only, never exception text."""
    env_candidate = environment.strip().upper() if isinstance(environment, str) else ""
    env = env_candidate if env_candidate in _ENVIRONMENTS else "UNBOUND"
    valid_profiles = {name for _, name in _PROFILES}
    selected_profile = profile if profile in valid_profiles else "UNBOUND"
    safe_reason = (
        reason_code
        if isinstance(reason_code, str) and re.fullmatch(r"[A-Z0-9_]{1,64}", reason_code)
        else "REDACTED_FAILURE"
    )
    exception_class = type(exception).__name__ if exception is not None else "NONE"
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", exception_class):
        exception_class = "Exception"
    return (
        f"environment={env} profile={selected_profile} "
        f"reason={safe_reason} exception={exception_class}"
    )
