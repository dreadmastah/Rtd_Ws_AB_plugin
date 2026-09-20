#!/usr/bin/env python3
"""Normalize Binance USD-M Demo Trading user-data events into fail-closed authority.

The process has no order/cancel/margin mutation methods. It consumes
ORDER_TRADE_UPDATE, ACCOUNT_UPDATE, listenKeyExpired, and transport liveness,
then publishes:
- TestnetUserDataState.v1
- AuthoritativeSimulationOrderSnapshot.v1 files for ASTU-owned orders

Fixture mode is deterministic and used by CI. Live mode uses only the Python
standard library: listen-key REST lifecycle plus a minimal RFC6455 TLS client.
The live stream URL template is configurable to survive Binance endpoint
migrations without changing authority semantics.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import socket
import ssl
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_STATUS = Path("Core/runtime/testnet_user_data_status.v1.json")
DEFAULT_ORDER_DIR = Path("Core/runtime/testnet_order_authority")
DEFAULT_JOURNAL = Path("Core/runtime/execution_journal.v1.jsonl")
DEFAULT_ACCOUNT = Path("Core/runtime/account_risk_status.v1.json")
DEFAULT_POSITIONS = Path("Core/runtime/position_status")
DEFAULT_REST_BASE = "https://testnet.binancefuture.com"
DEFAULT_WS_TEMPLATE = os.getenv(
    "ASTU_BINANCE_TESTNET_USER_STREAM_URL_TEMPLATE",
    "",
)


class UserDataError(RuntimeError):
    pass


def now_ms() -> int:
    return int(time.time() * 1000)


def atomic_write(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise UserDataError(f"{path} root must be object")
    return obj


def number(value: Any, name: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise UserDataError(f"invalid numeric field {name}") from exc
    if not (float("-inf") < out < float("inf")):
        raise UserDataError(f"non-finite numeric field {name}")
    return out


def integer(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise UserDataError(f"invalid integer field {name}")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise UserDataError(f"invalid integer field {name}") from exc


def order_state(status: str, cumulative: float, quantity: float) -> str:
    if cumulative < -1e-12 or quantity <= 0 or cumulative > quantity + 1e-12:
        return "UNKNOWN_RECONCILE_REQUIRED"
    if status == "NEW":
        return "WORKING" if cumulative <= 1e-12 else "UNKNOWN_RECONCILE_REQUIRED"
    if status == "PARTIALLY_FILLED":
        return (
            "PARTIAL"
            if cumulative > 1e-12 and cumulative < quantity - 1e-12
            else "UNKNOWN_RECONCILE_REQUIRED"
        )
    if status == "FILLED":
        return "FILLED" if abs(cumulative - quantity) <= 1e-12 else "UNKNOWN_RECONCILE_REQUIRED"
    if status in {"CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"}:
        return "CANCELED"
    if status == "REJECTED":
        return "REJECTED"
    return "UNKNOWN_RECONCILE_REQUIRED"


@dataclass
class Attempt:
    simulation_order_id: str
    client_order_id: str
    symbol: str
    quantity: float


def load_attempts(journal: Path) -> dict[str, Attempt]:
    attempts: dict[str, Attempt] = {}
    if not journal.exists():
        return attempts
    for line_no, raw in enumerate(journal.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise UserDataError(f"malformed journal line {line_no}") from exc
        if not isinstance(obj, dict):
            raise UserDataError(f"journal line {line_no} is not object")
        if obj.get("eventType") != "TESTNET_ORDER_SUBMISSION_ATTEMPT":
            continue
        if obj.get("executionEnvironment") != "BINANCE_USDM_TESTNET":
            raise UserDataError("testnet submission attempt has wrong environment")
        if obj.get("exchangeSubmissionAttempted") is not True:
            raise UserDataError("testnet submission attempt lacks exchange attempt marker")
        attempt = Attempt(
            simulation_order_id=str(obj.get("simulationOrderId", "")),
            client_order_id=str(obj.get("clientOrderId", "")),
            symbol=str(obj.get("symbol", "")).upper(),
            quantity=number(obj.get("quantity"), "quantity"),
        )
        if not attempt.simulation_order_id or not attempt.client_order_id or not attempt.symbol:
            raise UserDataError("testnet submission attempt identity incomplete")
        prior = attempts.get(attempt.client_order_id)
        if prior and prior != attempt:
            raise UserDataError("client order id maps to multiple persistent attempts")
        attempts[attempt.client_order_id] = attempt
    return attempts


@dataclass
class Authority:
    status_path: Path
    order_dir: Path
    journal: Path
    account_snapshot: Path
    position_dir: Path
    max_liveness_ms: int
    stream_epoch: int = 1
    connected_unix_ms: int = 0
    last_frame_unix_ms: int = 0
    last_event_unix_ms: int = 0
    event_count: int = 0
    order_event_count: int = 0
    account_event_count: int = 0
    ignored_order_event_count: int = 0
    expired_count: int = 0
    ordering_ok: bool = True
    expired: bool = False
    last_event_time_by_type: dict[str, int] = field(default_factory=dict)
    last_account_event_time_ms: int = 0
    last_account_reason: str = ""
    changed_position_event_time_ms: dict[str, int] = field(default_factory=dict)
    seen_order_clients: set[str] = field(default_factory=set)
    last_order_client_id: str = ""
    last_order_symbol: str = ""
    last_order_exchange_status: str = ""
    last_order_cumulative_fill: float = 0.0
    detail: str = "user-data authority initialized"

    def mark_connected(self, at_ms: int | None = None) -> None:
        when = at_ms or now_ms()
        self.connected_unix_ms = when
        self.last_frame_unix_ms = when
        self.expired = False
        self.detail = "user-data transport connected"
        self.publish(when)

    def mark_frame(self, at_ms: int | None = None) -> None:
        self.last_frame_unix_ms = at_ms or now_ms()

    def check_ordering(self, event_type: str, event_time: int) -> None:
        prior = self.last_event_time_by_type.get(event_type, 0)
        if prior and event_time < prior:
            self.ordering_ok = False
            raise UserDataError(
                f"{event_type} event time regressed: {event_time} < {prior}"
            )
        self.last_event_time_by_type[event_type] = event_time

    def process(self, event: dict[str, Any], received_ms: int | None = None) -> None:
        received = received_ms or now_ms()
        event_type = str(event.get("e", ""))
        event_time = integer(event.get("E", received), "E")
        if not event_type:
            raise UserDataError("user-data event missing e")
        self.mark_frame(received)
        self.check_ordering(event_type, event_time)
        self.last_event_unix_ms = received
        self.event_count += 1

        if event_type == "listenKeyExpired":
            self.expired = True
            self.expired_count += 1
            self.detail = "Binance listenKey expired"
            self.publish(received)
            return

        if event_type == "ORDER_TRADE_UPDATE":
            self.process_order(event, event_time)
        elif event_type == "ACCOUNT_UPDATE":
            self.process_account(event, event_time)
        else:
            self.detail = f"ignored user-data event type {event_type}"
        self.publish(received)

    def process_order(self, event: dict[str, Any], event_time: int) -> None:
        raw = event.get("o")
        if not isinstance(raw, dict):
            raise UserDataError("ORDER_TRADE_UPDATE missing o object")
        client_id = str(raw.get("c", ""))
        symbol = str(raw.get("s", "")).upper()
        status = str(raw.get("X", ""))
        quantity = number(raw.get("q"), "o.q")
        cumulative = number(raw.get("z"), "o.z")
        exchange_order_id = str(raw.get("i", ""))
        if not client_id or not symbol or not status or not exchange_order_id:
            raise UserDataError("ORDER_TRADE_UPDATE identity/status incomplete")

        attempts = load_attempts(self.journal)
        attempt = attempts.get(client_id)
        self.order_event_count += 1
        self.last_order_client_id = client_id
        self.last_order_symbol = symbol
        self.last_order_exchange_status = status
        self.last_order_cumulative_fill = cumulative
        if attempt is None:
            self.ignored_order_event_count += 1
            self.detail = "ignored non-ASTU order update"
            return
        if attempt.symbol != symbol or abs(attempt.quantity - quantity) > 1e-12:
            raise UserDataError("ORDER_TRADE_UPDATE does not match persistent ASTU attempt")

        state = order_state(status, cumulative, quantity)
        ready = state != "UNKNOWN_RECONCILE_REQUIRED"
        snapshot = {
            "schemaVersion": 1,
            "messageType": "AuthoritativeSimulationOrderSnapshot.v1",
            "generatedUnixMs": event_time,
            "source": "BINANCE_USDM_TESTNET_USER_DATA",
            "ready": ready,
            "simulationOrderId": attempt.simulation_order_id,
            "state": state,
            "cumulativeFilledQuantity": cumulative,
            "detail": (
                f"ORDER_TRADE_UPDATE exchangeOrderId={exchange_order_id}; "
                f"clientOrderId={client_id}; status={status}"
            ),
        }
        atomic_write(self.order_dir / f"{attempt.simulation_order_id}.json", snapshot)
        self.seen_order_clients.add(client_id)
        self.detail = "ASTU order authority updated from ORDER_TRADE_UPDATE"

    def process_account(self, event: dict[str, Any], event_time: int) -> None:
        raw = event.get("a")
        if not isinstance(raw, dict):
            raise UserDataError("ACCOUNT_UPDATE missing a object")
        reason = str(raw.get("m", ""))
        positions = raw.get("P", [])
        if not isinstance(positions, list):
            raise UserDataError("ACCOUNT_UPDATE P must be array")

        self.account_event_count += 1
        self.last_account_event_time_ms = event_time
        self.last_account_reason = reason
        for item in positions:
            if not isinstance(item, dict):
                raise UserDataError("ACCOUNT_UPDATE position must be object")
            symbol = str(item.get("s", "")).upper()
            if symbol:
                # Validate quantity is numeric but treat ACCOUNT_UPDATE as a delta.
                number(item.get("pa", 0), "a.P.pa")
                self.changed_position_event_time_ms[symbol] = event_time
        self.detail = "account/position delta observed; awaiting REST convergence"

    def rest_account_converged(self) -> tuple[bool, int]:
        try:
            obj = read_json(self.account_snapshot)
            generated = integer(obj.get("generatedUnixMs"), "generatedUnixMs")
            reconciled = obj.get("reconciled") is True
            if not reconciled:
                return False, generated
            if self.last_account_event_time_ms and generated < self.last_account_event_time_ms:
                return False, generated
            return True, generated
        except Exception:
            return False, 0

    def rest_positions_converged(self) -> bool:
        for symbol, event_time in self.changed_position_event_time_ms.items():
            try:
                obj = read_json(self.position_dir / f"{symbol}.json")
                if obj.get("reconciled") is not True:
                    return False
                if str(obj.get("symbol", "")).upper() != symbol:
                    return False
                if integer(obj.get("generatedUnixMs"), "generatedUnixMs") < event_time:
                    return False
            except Exception:
                return False
        return True

    def orders_converged(self) -> tuple[bool, int, int]:
        attempts = load_attempts(self.journal)
        unresolved = 0
        stream_resolved = 0
        for client_id, attempt in attempts.items():
            path = self.order_dir / f"{attempt.simulation_order_id}.json"
            try:
                obj = read_json(path)
                if (
                    obj.get("ready") is True
                    and obj.get("simulationOrderId") == attempt.simulation_order_id
                    and str(obj.get("source", "")).startswith("BINANCE_USDM_TESTNET_")
                ):
                    stream_resolved += 1
                    continue
            except Exception:
                pass
            unresolved += 1
        return unresolved == 0, stream_resolved, unresolved

    def snapshot(self, at_ms: int | None = None) -> dict[str, Any]:
        current = at_ms or now_ms()
        liveness_age = (
            current - self.last_frame_unix_ms if self.last_frame_unix_ms else 2**63 - 1
        )
        stream_alive = (
            not self.expired
            and self.ordering_ok
            and self.last_frame_unix_ms > 0
            and 0 <= liveness_age <= self.max_liveness_ms
        )
        account_ok, account_generated = self.rest_account_converged()
        positions_ok = self.rest_positions_converged()
        orders_ok, resolved, unresolved = self.orders_converged()
        ready = stream_alive and account_ok and positions_ok and orders_ok

        return {
            "schemaVersion": 1,
            "messageType": "TestnetUserDataState.v1",
            "generatedUnixMs": current,
            "source": "BINANCE_USDM_TESTNET_USER_DATA",
            "ready": ready,
            "streamAlive": stream_alive,
            "streamEpoch": self.stream_epoch,
            "connectedUnixMs": self.connected_unix_ms,
            "lastFrameUnixMs": self.last_frame_unix_ms,
            "lastEventUnixMs": self.last_event_unix_ms,
            "livenessAgeMs": max(0, liveness_age if liveness_age < 2**62 else 0),
            "maxLivenessAgeMs": self.max_liveness_ms,
            "eventCount": self.event_count,
            "orderEventCount": self.order_event_count,
            "accountEventCount": self.account_event_count,
            "ignoredOrderEventCount": self.ignored_order_event_count,
            "listenKeyExpiredCount": self.expired_count,
            "expired": self.expired,
            "orderingOk": self.ordering_ok,
            "lastAccountEventTimeMs": self.last_account_event_time_ms,
            "lastAccountReason": self.last_account_reason,
            "accountRestGeneratedUnixMs": account_generated,
            "accountConverged": account_ok,
            "positionsConverged": positions_ok,
            "ordersConverged": orders_ok,
            "resolvedAstuOrders": resolved,
            "unresolvedAstuOrders": unresolved,
            "restFallbackRequired": unresolved > 0,
            "lastOrderClientId": self.last_order_client_id,
            "lastOrderSymbol": self.last_order_symbol,
            "lastOrderExchangeStatus": self.last_order_exchange_status,
            "lastOrderCumulativeFilledQuantity": self.last_order_cumulative_fill,
            "detail": self.detail[:512],
        }

    def publish(self, at_ms: int | None = None) -> None:
        atomic_write(self.status_path, self.snapshot(at_ms))


def api_request(
    *,
    method: str,
    url: str,
    api_key: str,
    timeout_seconds: float,
) -> bytes:
    request = urllib.request.Request(
        url,
        method=method,
        headers={
            "X-MBX-APIKEY": api_key,
            "User-Agent": "ASTU-Testnet-UserData/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise UserDataError(f"Binance Demo Trading USER_STREAM HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise UserDataError(f"Binance Demo Trading USER_STREAM request failed: {exc}") from exc


def start_listen_key(base_url: str, api_key: str, timeout_seconds: float) -> str:
    body = api_request(
        method="POST",
        url=base_url.rstrip("/") + "/fapi/v1/listenKey",
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )
    obj = json.loads(body.decode("utf-8"))
    if not isinstance(obj, dict) or not obj.get("listenKey"):
        raise UserDataError("Binance Demo Trading listenKey response invalid")
    return str(obj["listenKey"])


def keepalive_listen_key(
    base_url: str,
    api_key: str,
    listen_key: str,
    timeout_seconds: float,
) -> None:
    query = urllib.parse.urlencode({"listenKey": listen_key})
    api_request(
        method="PUT",
        url=base_url.rstrip("/") + "/fapi/v1/listenKey?" + query,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )


class WebSocket:
    def __init__(self, url: str, timeout_seconds: float) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "wss" or not parsed.hostname:
            raise UserDataError("user-data websocket URL must be wss://")
        self.host = parsed.hostname
        self.port = parsed.port or 443
        self.path = parsed.path or "/"
        if parsed.query:
            self.path += "?" + parsed.query
        self.timeout_seconds = timeout_seconds
        self.sock: ssl.SSLSocket | None = None

    def connect(self) -> None:
        raw = socket.create_connection((self.host, self.port), timeout=self.timeout_seconds)
        context = ssl.create_default_context()
        self.sock = context.wrap_socket(raw, server_hostname=self.host)
        self.sock.settimeout(self.timeout_seconds)
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "User-Agent: ASTU-Testnet-UserData/1.0\r\n\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise UserDataError("websocket handshake closed")
            response += chunk
            if len(response) > 65536:
                raise UserDataError("websocket handshake too large")
        head = response.split(b"\r\n\r\n", 1)[0]
        if not head.startswith(b"HTTP/1.1 101"):
            raise UserDataError("websocket upgrade rejected")
        expected = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        )
        headers = {}
        for line in head.split(b"\r\n")[1:]:
            if b":" in line:
                k, v = line.split(b":", 1)
                headers[k.strip().lower()] = v.strip()
        if headers.get(b"sec-websocket-accept") != expected:
            raise UserDataError("websocket accept key mismatch")

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.send_frame(0x8, b"")
            except Exception:
                pass
            try:
                self.sock.close()
            finally:
                self.sock = None

    def recv_exact(self, size: int) -> bytes:
        if self.sock is None:
            raise UserDataError("websocket not connected")
        out = bytearray()
        while len(out) < size:
            chunk = self.sock.recv(size - len(out))
            if not chunk:
                raise UserDataError("websocket closed")
            out.extend(chunk)
        return bytes(out)

    def send_frame(self, opcode: int, payload: bytes) -> None:
        if self.sock is None:
            raise UserDataError("websocket not connected")
        mask = secrets.token_bytes(4)
        length = len(payload)
        first = bytes([0x80 | (opcode & 0x0F)])
        if length < 126:
            header = first + bytes([0x80 | length])
        elif length <= 0xFFFF:
            header = first + bytes([0x80 | 126]) + struct.pack("!H", length)
        else:
            header = first + bytes([0x80 | 127]) + struct.pack("!Q", length)
        masked = bytes(value ^ mask[i % 4] for i, value in enumerate(payload))
        self.sock.sendall(header + mask + masked)

    def recv_message(self) -> tuple[str, bytes]:
        fragments = bytearray()
        message_opcode = 0
        while True:
            b1, b2 = self.recv_exact(2)
            fin = bool(b1 & 0x80)
            opcode = b1 & 0x0F
            masked = bool(b2 & 0x80)
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack("!H", self.recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self.recv_exact(8))[0]
            if length > 2 * 1024 * 1024:
                raise UserDataError("user-data websocket frame too large")
            mask = self.recv_exact(4) if masked else b""
            payload = self.recv_exact(length)
            if masked:
                payload = bytes(value ^ mask[i % 4] for i, value in enumerate(payload))

            if opcode == 0x9:
                self.send_frame(0xA, payload)
                return "ping", payload
            if opcode == 0xA:
                return "pong", payload
            if opcode == 0x8:
                raise UserDataError("websocket close received")
            if opcode in (0x1, 0x2):
                message_opcode = opcode
                fragments = bytearray(payload)
            elif opcode == 0x0 and message_opcode:
                fragments.extend(payload)
            else:
                raise UserDataError(f"unsupported websocket opcode {opcode}")
            if fin:
                if message_opcode != 0x1:
                    raise UserDataError("user-data stream sent non-text message")
                return "text", bytes(fragments)


def run_fixture(args: argparse.Namespace, authority: Authority) -> int:
    authority.mark_connected(now_ms())
    for raw in args.fixture_jsonl.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            raise UserDataError("fixture event must be object")
        received = integer(obj.pop("_receivedUnixMs", now_ms()), "_receivedUnixMs")
        authority.process(obj, received)
    authority.publish(now_ms())
    return 0


def run_live(args: argparse.Namespace, authority: Authority) -> int:
    if os.getenv("ASTU_BINANCE_TESTNET_USER_DATA_ENABLED", "").strip() != "1":
        raise UserDataError(
            "live Demo Trading user-data stream requires ASTU_BINANCE_TESTNET_USER_DATA_ENABLED=1"
        )
    api_key = os.getenv("ASTU_BINANCE_TESTNET_API_KEY", "")
    if not api_key:
        raise UserDataError("ASTU_BINANCE_TESTNET_API_KEY is required")

    if not args.ws_url_template.strip():
        raise UserDataError(
            "live Demo Trading user-data stream requires an explicit "
            "ASTU_BINANCE_TESTNET_USER_STREAM_URL_TEMPLATE"
        )

    while True:
        listen_key = start_listen_key(args.rest_base_url, api_key, args.timeout_seconds)
        url = args.ws_url_template.format(listenKey=listen_key)
        ws = WebSocket(url, args.timeout_seconds)
        try:
            authority.stream_epoch += 1
            ws.connect()
            authority.mark_connected(now_ms())
            keepalive_due = time.monotonic() + args.keepalive_seconds
            while True:
                kind, payload = ws.recv_message()
                current = now_ms()
                authority.mark_frame(current)
                if kind == "text":
                    obj = json.loads(payload.decode("utf-8"))
                    if not isinstance(obj, dict):
                        raise UserDataError("user-data websocket message must be object")
                    authority.process(obj, current)
                else:
                    authority.publish(current)

                if time.monotonic() >= keepalive_due:
                    keepalive_listen_key(
                        args.rest_base_url,
                        api_key,
                        listen_key,
                        args.timeout_seconds,
                    )
                    keepalive_due = time.monotonic() + args.keepalive_seconds
        except Exception as exc:
            authority.detail = f"user-data transport reconnect required: {exc}"
            authority.last_frame_unix_ms = 0
            authority.publish(now_ms())
            time.sleep(args.reconnect_seconds)
        finally:
            ws.close()


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture-jsonl", type=Path)
    ap.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    ap.add_argument("--order-output-dir", type=Path, default=DEFAULT_ORDER_DIR)
    ap.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL)
    ap.add_argument("--account-snapshot", type=Path, default=DEFAULT_ACCOUNT)
    ap.add_argument("--position-dir", type=Path, default=DEFAULT_POSITIONS)
    ap.add_argument("--max-liveness-ms", type=int, default=15_000)
    ap.add_argument("--rest-base-url", default=DEFAULT_REST_BASE)
    ap.add_argument("--ws-url-template", default=DEFAULT_WS_TEMPLATE)
    ap.add_argument("--keepalive-seconds", type=float, default=30 * 60)
    ap.add_argument("--reconnect-seconds", type=float, default=2.0)
    ap.add_argument("--timeout-seconds", type=float, default=10.0)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_liveness_ms <= 0:
        raise SystemExit("max-liveness-ms must be positive")
    if args.keepalive_seconds <= 0 or args.reconnect_seconds <= 0 or args.timeout_seconds <= 0:
        raise SystemExit("timing values must be positive")

    authority = Authority(
        status_path=args.status,
        order_dir=args.order_output_dir,
        journal=args.journal,
        account_snapshot=args.account_snapshot,
        position_dir=args.position_dir,
        max_liveness_ms=args.max_liveness_ms,
    )
    try:
        if args.fixture_jsonl:
            return run_fixture(args, authority)
        return run_live(args, authority)
    except Exception as exc:
        authority.detail = f"user-data authority fail-closed: {exc}"
        authority.last_frame_unix_ms = 0
        authority.publish(now_ms())
        print(f"TESTNET_USER_DATA_FATAL={exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
