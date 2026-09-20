#!/usr/bin/env python3
"""Credentialed Binance USD-M Demo Trading acceptance harness.

Default behavior is preflight only. A Demo Trading MARKET order can be submitted only when:
1) --execute-market-order is supplied,
2) ASTU_TESTNET_ACCEPTANCE_ARM=I_UNDERSTAND_TESTNET_ORDER,
3) the REST host is an approved Demo Trading host,
4) the requested notional is below the configured hard cap,
5) an explicit user-stream URL template is supplied and successfully upgrades.

No production/mainnet host is accepted. Internal TESTNET identifiers are retained for compatibility.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
USER_DATA = ROOT / "account" / "binance_usdm_testnet_user_data.py"
DEFAULT_REPORT = ROOT / "runtime" / "testnet_acceptance_report.v1.json"
ALLOWED_REST_HOSTS = {
    "testnet.binancefuture.com",
    "demo-fapi.binance.com",
}
HARD_MAX_NOTIONAL = 50.0


class AcceptanceError(RuntimeError):
    pass


def load_user_data_module():
    spec = importlib.util.spec_from_file_location(
        "astu_testnet_user_data_acceptance",
        USER_DATA,
    )
    if spec is None or spec.loader is None:
        raise AcceptanceError("cannot load Demo Trading user-data module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def atomic_write(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def require_testnet_rest_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_REST_HOSTS:
        raise AcceptanceError(
            "REST base URL must be HTTPS and one of: "
            + ", ".join(sorted(ALLOWED_REST_HOSTS))
        )
    if parsed.path not in ("", "/") or parsed.params or parsed.query or parsed.fragment:
        raise AcceptanceError("REST base URL must not contain path/query/fragment")
    return base_url.rstrip("/")


def request_json(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        method=method,
        headers=headers or {},
        data=body,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise AcceptanceError(f"HTTP {exc.code} for {method} request") from exc
    except urllib.error.URLError as exc:
        raise AcceptanceError(f"network request failed: {exc}") from exc
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise AcceptanceError("response was not valid JSON") from exc
    if not isinstance(obj, dict):
        raise AcceptanceError("response root was not an object")
    return obj


def signed_request(
    *,
    method: str,
    base_url: str,
    path: str,
    api_key: str,
    api_secret: str,
    params: list[tuple[str, str]],
    timeout_seconds: float,
) -> dict[str, Any]:
    signed_params = list(params)
    signed_params.extend([
        ("recvWindow", "5000"),
        ("timestamp", str(int(time.time() * 1000))),
    ])
    query = urllib.parse.urlencode(signed_params)
    signature = hmac.new(
        api_secret.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    url = (
        base_url
        + path
        + "?"
        + query
        + "&signature="
        + urllib.parse.quote(signature)
    )
    return request_json(
        method=method,
        url=url,
        headers={
            "X-MBX-APIKEY": api_key,
            "User-Agent": "ASTU-Testnet-Acceptance/1.0",
        },
        timeout_seconds=timeout_seconds,
    )


def ticker_price(base_url: str, symbol: str, timeout_seconds: float) -> float:
    obj = request_json(
        method="GET",
        url=(
            base_url
            + "/fapi/v1/ticker/price?"
            + urllib.parse.urlencode({"symbol": symbol})
        ),
        timeout_seconds=timeout_seconds,
    )
    try:
        price = float(obj["price"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AcceptanceError("ticker price response invalid") from exc
    if not (0.0 < price < float("inf")):
        raise AcceptanceError("ticker price must be positive and finite")
    return price


def deterministic_acceptance_client_id() -> str:
    return (
        "ASTU-ACC-"
        + str(int(time.time() * 1000))[-13:]
        + "-"
        + os.urandom(4).hex()
    )[:36]


def validate_execution(
    *,
    execute: bool,
    quantity: float,
    price: float,
    max_notional: float,
) -> float:
    if quantity <= 0:
        raise AcceptanceError("--quantity must be positive")
    if max_notional <= 0 or max_notional > HARD_MAX_NOTIONAL:
        raise AcceptanceError(
            f"--max-test-notional must be in (0, {HARD_MAX_NOTIONAL}]"
        )
    notional = quantity * price
    if notional > max_notional + 1e-9:
        raise AcceptanceError(
            f"requested Demo Trading notional {notional:.8f} exceeds "
            f"configured Demo Trading acceptance cap {max_notional:.8f}"
        )
    if execute and os.getenv("ASTU_TESTNET_ACCEPTANCE_ARM", "") != (
        "I_UNDERSTAND_TESTNET_ORDER"
    ):
        raise AcceptanceError(
            "execution requires "
            "ASTU_TESTNET_ACCEPTANCE_ARM=I_UNDERSTAND_TESTNET_ORDER"
        )
    return notional


def probe_user_stream(
    *,
    module,
    rest_base_url: str,
    api_key: str,
    ws_url_template: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    if not ws_url_template.strip():
        return {
            "attempted": False,
            "connected": False,
            "detail": "explicit user-stream URL template not supplied",
        }
    listen_key = module.start_listen_key(
        rest_base_url,
        api_key,
        timeout_seconds,
    )
    url = ws_url_template.format(listenKey=listen_key)
    parsed = urlparse(url)
    if parsed.scheme != "wss" or not parsed.hostname:
        raise AcceptanceError("user-stream URL template must produce wss:// URL")
    ws = module.WebSocket(url, timeout_seconds)
    try:
        ws.connect()
        module.keepalive_listen_key(
            rest_base_url,
            api_key,
            listen_key,
            timeout_seconds,
        )
        return {
            "attempted": True,
            "connected": True,
            "host": parsed.hostname,
            "detail": "WebSocket upgrade and listen-key keepalive succeeded",
        }
    finally:
        ws.close()


def submit_market_order(
    *,
    base_url: str,
    api_key: str,
    api_secret: str,
    symbol: str,
    side: str,
    quantity: float,
    client_order_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    return signed_request(
        method="POST",
        base_url=base_url,
        path="/fapi/v1/order",
        api_key=api_key,
        api_secret=api_secret,
        params=[
            ("symbol", symbol),
            ("side", side),
            ("type", "MARKET"),
            ("quantity", f"{quantity:.15f}".rstrip("0").rstrip(".")),
            ("newClientOrderId", client_order_id),
            ("newOrderRespType", "ACK"),
        ],
        timeout_seconds=timeout_seconds,
    )


def query_order(
    *,
    base_url: str,
    api_key: str,
    api_secret: str,
    symbol: str,
    client_order_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    return signed_request(
        method="GET",
        base_url=base_url,
        path="/fapi/v1/order",
        api_key=api_key,
        api_secret=api_secret,
        params=[
            ("symbol", symbol),
            ("origClientOrderId", client_order_id),
        ],
        timeout_seconds=timeout_seconds,
    )


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rest-base-url", default="https://demo-fapi.binance.com")
    ap.add_argument("--ws-url-template", default=os.getenv(
        "ASTU_BINANCE_TESTNET_USER_STREAM_URL_TEMPLATE", ""
    ))
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--side", choices=("BUY", "SELL"), default="BUY")
    ap.add_argument("--quantity", type=float, default=0.0)
    ap.add_argument("--max-test-notional", type=float, default=25.0)
    ap.add_argument("--timeout-seconds", type=float, default=10.0)
    ap.add_argument("--execute-market-order", action="store_true")
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    started = int(time.time() * 1000)
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "messageType": "TestnetAcceptanceReport.v1",
        "generatedUnixMs": started,
        "mode": "EXECUTE" if args.execute_market_order else "PREFLIGHT",
        "passed": False,
        "restBaseUrl": args.rest_base_url,
        "symbol": args.symbol.upper(),
        "side": args.side,
        "streamProbe": {
            "attempted": False,
            "connected": False,
            "detail": "not attempted",
        },
        "orderSubmitted": False,
        "clientOrderId": "",
        "exchangeOrderId": "",
        "exchangeOrderStatus": "",
        "detail": "",
    }

    try:
        base_url = require_testnet_rest_url(args.rest_base_url)
        if args.timeout_seconds <= 0:
            raise AcceptanceError("--timeout-seconds must be positive")

        api_key = os.getenv("ASTU_BINANCE_TESTNET_API_KEY", "")
        api_secret = os.getenv("ASTU_BINANCE_TESTNET_API_SECRET", "")
        if not api_key or not api_secret:
            raise AcceptanceError(
                "ASTU_BINANCE_TESTNET_API_KEY and "
                "ASTU_BINANCE_TESTNET_API_SECRET are required"
            )

        account = signed_request(
            method="GET",
            base_url=base_url,
            path="/fapi/v3/account",
            api_key=api_key,
            api_secret=api_secret,
            params=[],
            timeout_seconds=args.timeout_seconds,
        )
        report["accountProbe"] = {
            "passed": True,
            "canTrade": account.get("canTrade"),
        }

        price = ticker_price(
            base_url,
            args.symbol.upper(),
            args.timeout_seconds,
        )
        report["markReferencePrice"] = price

        module = load_user_data_module()
        report["streamProbe"] = probe_user_stream(
            module=module,
            rest_base_url=base_url,
            api_key=api_key,
            ws_url_template=args.ws_url_template,
            timeout_seconds=args.timeout_seconds,
        )

        if not args.execute_market_order:
            report["passed"] = bool(
                report["accountProbe"]["passed"]
                and (
                    not report["streamProbe"]["attempted"]
                    or report["streamProbe"]["connected"]
                )
            )
            report["detail"] = (
                "credentialed Demo Trading preflight completed; no order submitted"
            )
            atomic_write(args.report, report)
            print("TESTNET_ACCEPTANCE=PREFLIGHT_PASS")
            print(f"REPORT={args.report}")
            return 0

        if not report["streamProbe"]["connected"]:
            raise AcceptanceError(
                "Demo Trading order execution requires a successful explicit user-stream probe"
            )

        notional = validate_execution(
            execute=True,
            quantity=args.quantity,
            price=price,
            max_notional=args.max_test_notional,
        )
        report["requestedQuantity"] = args.quantity
        report["requestedNotional"] = notional
        report["maxTestNotional"] = args.max_test_notional

        client_order_id = deterministic_acceptance_client_id()
        result = submit_market_order(
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret,
            symbol=args.symbol.upper(),
            side=args.side,
            quantity=args.quantity,
            client_order_id=client_order_id,
            timeout_seconds=args.timeout_seconds,
        )
        report["orderSubmitted"] = True
        report["clientOrderId"] = client_order_id
        report["exchangeOrderId"] = str(result.get("orderId", ""))
        report["exchangeOrderStatus"] = str(result.get("status", ""))

        lookup = query_order(
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret,
            symbol=args.symbol.upper(),
            client_order_id=client_order_id,
            timeout_seconds=args.timeout_seconds,
        )
        if str(lookup.get("clientOrderId", "")) != client_order_id:
            raise AcceptanceError("order lookup clientOrderId mismatch")
        report["lookupStatus"] = str(lookup.get("status", ""))
        report["executedQty"] = str(lookup.get("executedQty", ""))
        report["passed"] = True
        report["detail"] = (
            "Demo Trading MARKET order acknowledged and recovered by origClientOrderId; "
            "inspect user-data authority artifacts for ORDER_TRADE_UPDATE convergence"
        )
        atomic_write(args.report, report)
        print("TESTNET_ACCEPTANCE=ORDER_PASS")
        print(f"CLIENT_ORDER_ID={client_order_id}")
        print(f"REPORT={args.report}")
        return 0
    except Exception as exc:
        report["passed"] = False
        report["detail"] = str(exc)[:512]
        atomic_write(args.report, report)
        print(f"TESTNET_ACCEPTANCE=FAIL detail={exc}")
        print(f"REPORT={args.report}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
