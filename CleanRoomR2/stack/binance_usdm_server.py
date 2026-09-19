#!/usr/bin/env python3
"""Binance USD-M Futures -> WSRTD sender.

Public market data only. No API key, account access, private streams, orders,
or trading actions are implemented.

Live mapping:
  kline_1m   -> WSRTD d,t,o,h,l,c,v,x1,x2
  ticker     -> daily volume/open/high/low/previous close
  bookTicker -> bid/ask + sizes
  markPrice  -> ExtraData (mark/index/funding/next funding)
  REST openInterest -> WSRTD oi + ExtraData

Backfill commands from WSRTD are serviced from Binance public REST klines.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

BASE = Path(__file__).resolve().parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
BCFG = CFG["binance"]
RCFG = CFG["relay"]

REST_BASE = str(BCFG["rest_base"]).rstrip("/")
MARKET_WS = str(BCFG["market_ws"])
PUBLIC_WS = str(BCFG["public_ws"])
INTERVAL = str(BCFG.get("kline_interval", "1m"))
PUBLISH_SEC = max(0.05, int(BCFG.get("publish_interval_ms", 250)) / 1000.0)
OI_POLL_SEC = max(5.0, float(BCFG.get("open_interest_poll_seconds", 30)))
REQUEST_TIMEOUT = float(BCFG.get("request_timeout_seconds", 15))
FULL_BF_DAYS = max(1, int(BCFG.get("full_backfill_days", 2)))
MAX_BF_DAYS = max(FULL_BF_DAYS, int(BCFG.get("max_backfill_days", 2)))
EOD_BF_DAYS = max(2, int(BCFG.get("eod_backfill_days", 301)))
REST_LIMIT = min(1500, max(100, int(BCFG.get("rest_page_limit", 1500))))
FAIL_CLOSED_BOOTSTRAP = bool(BCFG.get("fail_closed_bootstrap", True))
RECOV_CFG = CFG.get("recovery", {})
RECOVERY_ENABLED = bool(RECOV_CFG.get("enabled", True))
RECOVERY_AUDIT_SEC = max(10.0, float(RECOV_CFG.get("audit_seconds", 60)))
RECOVERY_STATE_FLUSH_SEC = max(1.0, float(RECOV_CFG.get("state_flush_seconds", 5)))
RECOVERY_RECEIVER_FULL_REFRESH = bool(RECOV_CFG.get("receiver_full_refresh", True))
RECOVERY_1M_RECORDS = max(60, int(RECOV_CFG.get("intraday_target_records", 1500)))
RECOVERY_EOD_BARS = max(1, int(RECOV_CFG.get("eod_target_bars", 300)))
PREFLIGHT_RETRY_INITIAL = max(1.0, float(RECOV_CFG.get("preflight_retry_initial_seconds", 2)))
PREFLIGHT_RETRY_MAX = max(PREFLIGHT_RETRY_INITIAL, float(RECOV_CFG.get("preflight_retry_max_seconds", 60)))
STATE_FILE_CFG = Path(str(RECOV_CFG.get("state_file", "runtime/recovery_state.json")))
RECOVERY_STATE_PATH = STATE_FILE_CFG if STATE_FILE_CFG.is_absolute() else BASE / STATE_FILE_CFG
MINUTE_MS = 60_000
DAY_MS = 86_400_000
RELAY_URI = os.getenv(
    "WSRTD_RELAY_URI",
    f"ws://{RCFG.get('host', '127.0.0.1')}:{RCFG.get('port', 10101)}/sender",
)

(BASE / "logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BASE / "logs" / "binance_server.log", encoding="utf-8"),
    ],
)
LOG = logging.getLogger("binance-usdm-wsrtd")


class BootstrapValidationError(RuntimeError):
    """Fail-closed bootstrap universe validation failure."""


def load_bootstrap() -> list[str]:
    path = BASE / "bootstrap_symbols.tls"
    symbols: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        s = line.strip().upper()
        if not s or s.startswith("#") or s in seen:
            continue
        seen.add(s)
        symbols.append(s)
    if not symbols:
        raise RuntimeError("bootstrap_symbols.tls contains no symbols")
    return symbols


BOOTSTRAP = load_bootstrap()


@dataclass
class SymbolState:
    symbol: str
    k_open_ms: int = 0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    quote_volume: float = 0.0
    trades: int = 0
    daily_volume: float = 0.0
    prev_close: float = 0.0
    day_open: float = 0.0
    day_high: float = 0.0
    day_low: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    bid_size: float = 0.0
    ask_size: float = 0.0
    open_interest: float = 0.0
    mark_price: float = 0.0
    index_price: float = 0.0
    funding_rate: float = 0.0
    next_funding_time: int = 0
    have_kline: bool = False
    updated_monotonic: float = field(default_factory=time.monotonic)


class App:
    def __init__(self) -> None:
        self.bootstrap = list(BOOTSTRAP)
        self.active: set[str] = set(BOOTSTRAP)
        self.valid: dict[str, dict[str, Any]] = {}
        self.state: dict[str, SymbolState] = {s: SymbolState(s) for s in BOOTSTRAP}
        self.dirty: set[str] = set()
        self.dirty_event = asyncio.Event()
        self.stop = asyncio.Event()
        self.session: aiohttp.ClientSession | None = None
        self.relay_ws: ClientConnection | None = None
        self.market_ws: ClientConnection | None = None
        self.public_ws: ClientConnection | None = None
        self.relay_send_lock = asyncio.Lock()
        self.market_send_lock = asyncio.Lock()
        self.public_send_lock = asyncio.Lock()
        self.market_up = False
        self.public_up = False
        self.req_id = 100
        self.backfill_sem = asyncio.Semaphore(2)
        self.receiver_count = 0
        self.recovery_event = asyncio.Event()
        self.recovery_reasons: set[str] = set()
        self.recovery_full_requested = False
        self.recovery_lock = asyncio.Lock()
        self.recovery_state_dirty = False
        self.recovery_state = self.load_recovery_state()

    def next_id(self) -> int:
        self.req_id += 1
        return self.req_id

    @staticmethod
    def completed_1m_open_ms(now_ms: int | None = None) -> int:
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        return (now_ms // MINUTE_MS) * MINUTE_MS - MINUTE_MS

    @staticmethod
    def date_num_from_ms(open_ms: int) -> int:
        dt = datetime.fromtimestamp(open_ms / 1000.0, tz=timezone.utc)
        return dt.year * 10000 + dt.month * 100 + dt.day

    @staticmethod
    def yesterday_date_num(now_ms: int | None = None) -> int:
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        return App.date_num_from_ms(now_ms - DAY_MS)

    def load_recovery_state(self) -> dict[str, Any]:
        default = {"version": 1, "symbols": {}}
        if not RECOVERY_ENABLED or not RECOVERY_STATE_PATH.exists():
            return default
        try:
            obj = json.loads(RECOVERY_STATE_PATH.read_text(encoding="utf-8"))
            if not isinstance(obj, dict) or not isinstance(obj.get("symbols"), dict):
                raise ValueError("invalid recovery-state structure")
            obj["version"] = 1
            LOG.info("recovery state loaded path=%s symbols=%d", RECOVERY_STATE_PATH, len(obj["symbols"]))
            return obj
        except Exception as exc:
            LOG.warning("recovery state unreadable; starting conservatively: %s", exc)
            return default

    def recovery_symbol_state(self, symbol: str) -> dict[str, Any]:
        symbols = self.recovery_state.setdefault("symbols", {})
        item = symbols.setdefault(symbol.upper(), {})
        return item

    def update_1m_watermark(self, symbol: str, open_ms: int, *, allow_jump: bool = False) -> None:
        if open_ms <= 0:
            return
        item = self.recovery_symbol_state(symbol)
        old = int(item.get("last_completed_1m_open_ms", 0) or 0)
        if open_ms <= old:
            return
        if old > 0 and open_ms > old + MINUTE_MS and not allow_jump:
            observed = int(item.get("observed_completed_1m_open_ms", 0) or 0)
            if open_ms > observed:
                item["observed_completed_1m_open_ms"] = int(open_ms)
                self.recovery_state_dirty = True
            LOG.warning(
                "live 1m gap detected symbol=%s last=%d observed=%d missing_minutes=%d",
                symbol, old, open_ms, max(0, (open_ms - old) // MINUTE_MS - 1),
            )
            self.request_recovery(f"live-gap:{symbol}", full=False)
            return
        item["last_completed_1m_open_ms"] = int(open_ms)
        item.pop("observed_completed_1m_open_ms", None)
        item["updated_utc"] = datetime.now(timezone.utc).isoformat()
        self.recovery_state_dirty = True

    def update_eod_watermark(self, symbol: str, date_num: int) -> None:
        if date_num <= 0:
            return
        item = self.recovery_symbol_state(symbol)
        old = int(item.get("last_completed_eod_date", 0) or 0)
        if date_num > old:
            item["last_completed_eod_date"] = int(date_num)
            item["updated_utc"] = datetime.now(timezone.utc).isoformat()
            self.recovery_state_dirty = True

    def save_recovery_state(self) -> None:
        if not RECOVERY_ENABLED or not self.recovery_state_dirty:
            return
        RECOVERY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = RECOVERY_STATE_PATH.with_suffix(RECOVERY_STATE_PATH.suffix + ".tmp")
        body = dict(self.recovery_state)
        body["version"] = 1
        body["saved_utc"] = datetime.now(timezone.utc).isoformat()
        tmp.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, RECOVERY_STATE_PATH)
        self.recovery_state_dirty = False

    async def recovery_state_writer_loop(self) -> None:
        while not self.stop.is_set():
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=RECOVERY_STATE_FLUSH_SEC)
            except asyncio.TimeoutError:
                pass
            if self.recovery_state_dirty:
                try:
                    self.save_recovery_state()
                except Exception:
                    LOG.exception("recovery state save failed")

    def request_recovery(self, reason: str, *, full: bool = False) -> None:
        if not RECOVERY_ENABLED:
            return
        self.recovery_reasons.add(reason)
        if full:
            self.recovery_full_requested = True
        self.recovery_event.set()

    async def handle_relay_status(self, obj: dict[str, Any]) -> None:
        new_count = max(0, int(obj.get("receivers", 0) or 0))
        old_count = self.receiver_count
        self.receiver_count = new_count
        if new_count != old_count:
            LOG.info("relay receiver count changed old=%d new=%d", old_count, new_count)
        if new_count > 0 and old_count == 0:
            self.request_recovery("receiver-attached", full=RECOVERY_RECEIVER_FULL_REFRESH)

    async def rest_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        assert self.session is not None
        url = REST_BASE + path
        for attempt in range(5):
            try:
                async with self.session.get(url, params=params) as resp:
                    txt = await resp.text()
                    if resp.status == 200:
                        return json.loads(txt)
                    if resp.status in {418, 429}:
                        delay = min(30, 2 ** attempt)
                        LOG.warning("REST rate limited status=%d path=%s delay=%ss", resp.status, path, delay)
                        await asyncio.sleep(delay)
                        continue
                    raise RuntimeError(f"REST {resp.status} {path}: {txt[:300]}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt == 4:
                    raise
                await asyncio.sleep(min(10, 1.5 * (attempt + 1)))
                LOG.warning("REST retry path=%s error=%s", path, exc)
        raise RuntimeError("unreachable")

    async def preflight_exchange(self) -> None:
        info = await self.rest_json("/fapi/v1/exchangeInfo")
        self.valid = {x["symbol"].upper(): x for x in info.get("symbols", [])}
        bad: list[str] = []
        for s in self.bootstrap:
            x = self.valid.get(s)
            if not x:
                bad.append(f"{s}: missing")
                continue
            if x.get("quoteAsset") != "USDT" or x.get("contractType") != "PERPETUAL" or x.get("status") != "TRADING":
                bad.append(
                    f"{s}: quoteAsset={x.get('quoteAsset')} contractType={x.get('contractType')} status={x.get('status')}"
                )
        if bad:
            msg = "Bootstrap validation failed: " + "; ".join(bad)
            if FAIL_CLOSED_BOOTSTRAP:
                raise BootstrapValidationError(msg)
            LOG.warning(msg)
            for item in bad:
                self.active.discard(item.split(":", 1)[0])
        LOG.info("bootstrap validation PASS active=%d symbols=%s", len(self.active), ",".join(sorted(self.active)))

    async def wait_for_preflight(self) -> None:
        delay = PREFLIGHT_RETRY_INITIAL
        while not self.stop.is_set():
            try:
                await self.preflight_exchange()
                return
            except BootstrapValidationError:
                raise
            except Exception as exc:
                LOG.warning("Binance preflight unavailable; retrying in %.1fs: %s", delay, exc)
                try:
                    await asyncio.wait_for(self.stop.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                delay = min(PREFLIGHT_RETRY_MAX, delay * 1.8)
        raise asyncio.CancelledError

    def symbol_eligible(self, symbol: str) -> bool:
        x = self.valid.get(symbol.upper())
        return bool(
            x
            and x.get("quoteAsset") == "USDT"
            and x.get("contractType") == "PERPETUAL"
            and x.get("status") == "TRADING"
        )

    async def relay_send(self, obj: Any) -> bool:
        msg = obj if isinstance(obj, str) else json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
        ws = self.relay_ws
        if ws is None:
            return False
        try:
            async with self.relay_send_lock:
                await ws.send(msg)
            return True
        except Exception:
            return False

    async def relay_loop(self) -> None:
        backoff = 1.0
        while not self.stop.is_set():
            try:
                async with connect(
                    RELAY_URI,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                    max_size=8 * 1024 * 1024,
                    compression=None,
                ) as ws:
                    self.relay_ws = ws
                    backoff = 1.0
                    LOG.info("connected to relay %s", RELAY_URI)
                    await self.send_all_info()
                    async for raw in ws:
                        if isinstance(raw, str):
                            asyncio.create_task(self.handle_relay_message(raw))
            except (OSError, ConnectionClosed, asyncio.TimeoutError) as exc:
                LOG.warning("relay disconnected: %s", exc)
            except Exception:
                LOG.exception("relay loop failure")
            finally:
                self.relay_ws = None
                self.receiver_count = 0
            if not self.stop.is_set():
                await asyncio.sleep(backoff)
                backoff = min(15.0, backoff * 1.7)

    def market_streams(self, symbol: str) -> list[str]:
        s = symbol.lower()
        return [f"{s}@kline_{INTERVAL}", f"{s}@ticker", f"{s}@markPrice@1s"]

    def public_streams(self, symbol: str) -> list[str]:
        return [f"{symbol.lower()}@bookTicker"]

    async def send_sub(self, ws: ClientConnection | None, lock: asyncio.Lock, method: str, params: list[str]) -> None:
        if ws is None or not params:
            return
        payload = {"method": method, "params": params, "id": self.next_id()}
        async with lock:
            await ws.send(json.dumps(payload, separators=(",", ":")))

    async def subscribe_symbol(self, symbol: str) -> None:
        await self.send_sub(self.market_ws, self.market_send_lock, "SUBSCRIBE", self.market_streams(symbol))
        await self.send_sub(self.public_ws, self.public_send_lock, "SUBSCRIBE", self.public_streams(symbol))

    async def unsubscribe_symbol(self, symbol: str) -> None:
        await self.send_sub(self.market_ws, self.market_send_lock, "UNSUBSCRIBE", self.market_streams(symbol))
        await self.send_sub(self.public_ws, self.public_send_lock, "UNSUBSCRIBE", self.public_streams(symbol))

    async def market_loop(self) -> None:
        await self.binance_ws_loop("market")

    async def public_loop(self) -> None:
        await self.binance_ws_loop("public")

    async def binance_ws_loop(self, kind: str) -> None:
        uri = MARKET_WS if kind == "market" else PUBLIC_WS
        lock = self.market_send_lock if kind == "market" else self.public_send_lock
        backoff = 1.0
        connection_seq = 0
        while not self.stop.is_set():
            connected_monotonic: float | None = None
            message_count = 0
            connection_seq += 1
            try:
                async with connect(
                    uri,
                    ping_interval=None,
                    close_timeout=5,
                    open_timeout=15,
                    max_size=4 * 1024 * 1024,
                    compression=None,
                ) as ws:
                    connected_monotonic = time.monotonic()
                    if kind == "market":
                        self.market_ws = ws
                        self.market_up = True
                        params = [x for s in sorted(self.active) for x in self.market_streams(s)]
                    else:
                        self.public_ws = ws
                        self.public_up = True
                        params = [x for s in sorted(self.active) for x in self.public_streams(s)]
                    await self.send_sub(ws, lock, "SUBSCRIBE", params)
                    LOG.info(
                        "Binance %s websocket connected connection=%d streams=%d uri=%s",
                        kind, connection_seq, len(params), uri,
                    )
                    if kind == "market":
                        self.request_recovery("market-websocket-connected", full=False)
                    backoff = 1.0
                    async for raw in ws:
                        message_count += 1
                        if not isinstance(raw, str):
                            continue
                        try:
                            obj = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(obj, dict) and "data" in obj and "stream" in obj:
                            obj = obj["data"]
                        await self.handle_binance_event(obj)
                    duration = max(0.0, time.monotonic() - connected_monotonic)
                    LOG.warning(
                        "Binance %s websocket closed cleanly connection=%d duration_seconds=%.3f messages=%d uri=%s",
                        kind, connection_seq, duration, message_count, uri,
                    )
            except (OSError, ConnectionClosed, asyncio.TimeoutError) as exc:
                duration = 0.0 if connected_monotonic is None else max(0.0, time.monotonic() - connected_monotonic)
                close_code = getattr(exc, "code", None)
                close_reason = getattr(exc, "reason", None)
                if close_code is None:
                    rcvd = getattr(exc, "rcvd", None)
                    close_code = getattr(rcvd, "code", None)
                    close_reason = getattr(rcvd, "reason", close_reason)
                LOG.warning(
                    "Binance %s websocket disconnected connection=%d exception=%s duration_seconds=%.3f messages=%d close_code=%s close_reason=%r uri=%s detail=%s",
                    kind, connection_seq, type(exc).__name__, duration, message_count,
                    close_code, close_reason, uri, exc,
                )
            except Exception:
                duration = 0.0 if connected_monotonic is None else max(0.0, time.monotonic() - connected_monotonic)
                LOG.exception(
                    "Binance %s websocket loop failure connection=%d duration_seconds=%.3f messages=%d uri=%s",
                    kind, connection_seq, duration, message_count, uri,
                )
            finally:
                if kind == "market":
                    self.market_ws = None
                    self.market_up = False
                else:
                    self.public_ws = None
                    self.public_up = False
            if not self.stop.is_set():
                await asyncio.sleep(backoff)
                backoff = min(20.0, backoff * 1.7)

    async def handle_binance_event(self, obj: Any) -> None:
        if not isinstance(obj, dict):
            return
        if "result" in obj and "id" in obj:
            return
        et = obj.get("e")
        symbol = str(obj.get("s", "")).upper()
        if not symbol or symbol not in self.active:
            return
        st = self.state.setdefault(symbol, SymbolState(symbol))
        if et == "kline":
            k = obj.get("k") or {}
            st.k_open_ms = int(k.get("t", 0))
            st.open = float(k.get("o", 0) or 0)
            st.high = float(k.get("h", 0) or 0)
            st.low = float(k.get("l", 0) or 0)
            st.close = float(k.get("c", 0) or 0)
            st.volume = float(k.get("v", 0) or 0)
            st.quote_volume = float(k.get("q", 0) or 0)
            st.trades = int(k.get("n", 0) or 0)
            st.have_kline = True
            if bool(k.get("x", False)):
                self.update_1m_watermark(symbol, st.k_open_ms)
            self.mark_dirty(symbol)
        elif et == "24hrTicker":
            last = float(obj.get("c", 0) or 0)
            change = float(obj.get("p", 0) or 0)
            st.daily_volume = float(obj.get("v", 0) or 0)
            st.prev_close = last - change if last else 0.0
            st.day_open = float(obj.get("o", 0) or 0)
            st.day_high = float(obj.get("h", 0) or 0)
            st.day_low = float(obj.get("l", 0) or 0)
            self.mark_dirty(symbol)
        elif et == "bookTicker":
            st.bid = float(obj.get("b", 0) or 0)
            st.bid_size = float(obj.get("B", 0) or 0)
            st.ask = float(obj.get("a", 0) or 0)
            st.ask_size = float(obj.get("A", 0) or 0)
            self.mark_dirty(symbol)
        elif et == "markPriceUpdate":
            st.mark_price = float(obj.get("p", 0) or 0)
            st.index_price = float(obj.get("i", 0) or 0)
            st.funding_rate = float(obj.get("r", 0) or 0)
            st.next_funding_time = int(obj.get("T", 0) or 0)
        st.updated_monotonic = time.monotonic()

    def mark_dirty(self, symbol: str) -> None:
        self.dirty.add(symbol)
        self.dirty_event.set()

    def rtd_record(self, st: SymbolState) -> dict[str, Any] | None:
        if not st.have_kline or not st.k_open_ms:
            return None
        dt = datetime.fromtimestamp(st.k_open_ms / 1000.0, tz=timezone.utc)
        return {
            "n": st.symbol,
            "d": dt.year * 10000 + dt.month * 100 + dt.day,
            "t": dt.hour * 10000 + dt.minute * 100 + dt.second,
            "o": st.open,
            "h": st.high,
            "l": st.low,
            "c": st.close,
            "v": st.volume,
            "oi": st.open_interest,
            "x1": st.quote_volume,
            "x2": st.trades,
            "s": st.daily_volume,
            "pc": st.prev_close,
            "bs": st.bid_size,
            "bp": st.bid,
            "as": st.ask_size,
            "ap": st.ask,
            "do": st.day_open,
            "dh": st.day_high,
            "dl": st.day_low,
        }

    async def publish_loop(self) -> None:
        while not self.stop.is_set():
            try:
                await asyncio.wait_for(self.dirty_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            await asyncio.sleep(PUBLISH_SEC)
            names = sorted(self.dirty)
            self.dirty.clear()
            self.dirty_event.clear()
            payload = [r for s in names if s in self.active if (r := self.rtd_record(self.state[s])) is not None]
            if payload:
                await self.relay_send(payload)

    async def open_interest_loop(self) -> None:
        while not self.stop.is_set():
            started = time.monotonic()
            for symbol in sorted(self.active):
                if self.stop.is_set():
                    break
                try:
                    obj = await self.rest_json("/fapi/v1/openInterest", {"symbol": symbol})
                    self.state.setdefault(symbol, SymbolState(symbol)).open_interest = float(obj.get("openInterest", 0) or 0)
                    self.mark_dirty(symbol)
                except Exception as exc:
                    LOG.warning("openInterest %s failed: %s", symbol, exc)
                await asyncio.sleep(0.05)
            remaining = OI_POLL_SEC - (time.monotonic() - started)
            if remaining > 0:
                try:
                    await asyncio.wait_for(self.stop.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    pass

    def info_packet(self, symbol: str) -> dict[str, Any]:
        return {
            "info": symbol,
            "fn": f"Binance USD-M {symbol} Perpetual",
            "an": symbol,
            "ad": "Binance USD-M Futures",
            "co": "",
            "cy": "USDT",
            "wi": symbol,
            "im": 0,
            "ig": 0,
            "ii": 0,
            "gc": 0,
        }

    async def send_all_info(self) -> None:
        for symbol in sorted(self.active):
            await self.relay_send(self.info_packet(symbol))

    def extra_packet(self, symbol: str) -> dict[str, Any]:
        st = self.state.setdefault(symbol, SymbolState(symbol))
        rec = self.recovery_symbol_state(symbol)
        return {
            "ed": symbol,
            "MarkPrice": st.mark_price,
            "IndexPrice": st.index_price,
            "FundingRate": st.funding_rate,
            "NextFundingTime": float(st.next_funding_time),
            "OpenInterest": st.open_interest,
            "QuoteVolume1m": st.quote_volume,
            "TradeCount1m": float(st.trades),
            "Bootstrap": 1.0 if symbol in self.bootstrap else 0.0,
            "RecoveryEnabled": 1.0 if RECOVERY_ENABLED else 0.0,
            "RecoveryReceivers": float(self.receiver_count),
            "RecoveryLast1mOpenMs": float(rec.get("last_completed_1m_open_ms", 0) or 0),
            "RecoveryLastEODDate": float(rec.get("last_completed_eod_date", 0) or 0),
        }

    async def handle_relay_message(self, raw: str) -> None:
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return
        if not isinstance(obj, dict):
            return
        if obj.get("_relay") == "status":
            await self.handle_relay_status(obj)
            return
        if "cmd" not in obj:
            return
        cmd = str(obj.get("cmd", ""))
        arg = str(obj.get("arg", ""))
        LOG.info("WSRTD command cmd=%s arg=%s", cmd, arg[:160])

        if cmd == "cping":
            code = 200 if self.market_up and self.public_up else 400
            status = "Binance USD-M connected" if code == 200 else "Binance USD-M degraded/disconnected"
            await self.relay_send({"cmd": "cping", "code": code, "arg": status})
            return
        if cmd == "ed":
            symbol = arg.strip().upper()
            if symbol in self.state:
                await self.relay_send(self.extra_packet(symbol))
            return
        if cmd == "addsym":
            await self.cmd_add_symbol(arg)
            return
        if cmd == "remsym":
            await self.cmd_remove_symbol(arg)
            return
        if cmd == "newreq":
            await self.relay_send({"cmd": "newreq", "code": 200, "arg": f"received:{arg}"})
            return
        if cmd in {"bfauto", "bffull", "bfsym", "bfall", "bfsymeod", "bfeodall"}:
            asyncio.create_task(self.handle_backfill_command(cmd, arg))
            return

    async def cmd_add_symbol(self, arg: str) -> None:
        symbol = arg.strip().upper()
        if not self.symbol_eligible(symbol):
            await self.relay_send({"cmd": "addsym", "code": 400, "arg": f"{symbol} is not a TRADING USD-M USDT perpetual"})
            return
        if symbol not in self.active:
            self.active.add(symbol)
            self.state.setdefault(symbol, SymbolState(symbol))
            try:
                await self.subscribe_symbol(symbol)
            except Exception as exc:
                LOG.warning("subscribe %s failed; websocket reconnect will restore it: %s", symbol, exc)
            await self.relay_send(self.info_packet(symbol))
        await self.relay_send({"cmd": "addsym", "code": 200, "arg": f"{symbol} subscribed ok"})

    async def cmd_remove_symbol(self, arg: str) -> None:
        symbol = arg.strip().upper()
        if symbol in self.active:
            self.active.remove(symbol)
            try:
                await self.unsubscribe_symbol(symbol)
            except Exception as exc:
                LOG.warning("unsubscribe %s failed: %s", symbol, exc)
            await self.relay_send({"cmd": "remsym", "code": 200, "arg": f"{symbol} unsubscribed ok"})
        else:
            await self.relay_send({"cmd": "remsym", "code": 400, "arg": f"{symbol} not subscribed"})

    @staticmethod
    def parse_dt_utc(date_num: str, time_num: str) -> int:
        d = str(int(date_num)).zfill(8)
        t = str(int(time_num)).zfill(6)
        dt = datetime(
            int(d[0:4]), int(d[4:6]), int(d[6:8]),
            int(t[0:2]), int(t[2:4]), int(t[4:6]), tzinfo=timezone.utc,
        )
        return int(dt.timestamp() * 1000)

    async def handle_backfill_command(self, cmd: str, arg: str) -> None:
        async with self.backfill_sem:
            try:
                if cmd == "bfall":
                    for s in sorted(self.active):
                        await self.send_intraday_history(s, days=FULL_BF_DAYS)
                    await self.relay_send({"cmd": cmd, "code": 200, "arg": f"backfilled {len(self.active)} symbols"})
                elif cmd == "bfeodall":
                    for s in sorted(self.active):
                        await self.send_eod_history(s, days=EOD_BF_DAYS)
                    await self.relay_send({"cmd": cmd, "code": 200, "arg": f"EOD backfilled {len(self.active)} symbols"})
                elif cmd == "bffull":
                    s = arg.split()[0].upper()
                    await self.send_intraday_history(s, days=FULL_BF_DAYS)
                elif cmd == "bfauto":
                    parts = arg.split()
                    s = parts[0].upper()
                    start_ms = None
                    if len(parts) >= 3:
                        with contextlib.suppress(Exception):
                            start_ms = self.parse_dt_utc(parts[1], parts[2])
                    await self.send_intraday_history(s, start_ms=start_ms, days=FULL_BF_DAYS)
                elif cmd == "bfsym":
                    parts = arg.split()
                    if len(parts) < 2:
                        raise ValueError("bfsym arg requires reserved SYMBOL [days]")
                    s = parts[1].upper()
                    days = FULL_BF_DAYS
                    if len(parts) >= 3:
                        with contextlib.suppress(ValueError):
                            days = int(parts[2])
                    days = min(MAX_BF_DAYS, max(1, days))
                    await self.send_intraday_history(s, days=days)
                elif cmd == "bfsymeod":
                    parts = arg.split()
                    if len(parts) < 2:
                        raise ValueError("bfsymeod arg requires reserved SYMBOL [preset]")
                    s = parts[1].upper()
                    preset = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 1
                    days = 30 if preset <= 1 else min(EOD_BF_DAYS, 365)
                    await self.send_eod_history(s, days=days)
                await self.relay_send({"cmd": cmd, "code": 200, "arg": "backfill completed"})
            except Exception as exc:
                LOG.exception("backfill command failed cmd=%s arg=%s", cmd, arg)
                await self.relay_send({"cmd": cmd, "code": 400, "arg": f"backfill error: {exc}"})

    async def fetch_klines(self, symbol: str, interval: str, start_ms: int, end_ms: int) -> list[list[Any]]:
        rows: list[list[Any]] = []
        cursor = start_ms
        while cursor <= end_ms and not self.stop.is_set():
            params = {
                "symbol": symbol,
                "interval": interval,
                "startTime": cursor,
                "endTime": end_ms,
                "limit": REST_LIMIT,
            }
            page = await self.rest_json("/fapi/v1/klines", params)
            if not isinstance(page, list) or not page:
                break
            rows.extend(page)
            last_open = int(page[-1][0])
            nxt = last_open + 1
            if nxt <= cursor:
                break
            cursor = nxt
            if len(page) < REST_LIMIT:
                break
            await asyncio.sleep(0.08)
        return rows

    async def send_intraday_range(
        self,
        symbol: str,
        start_ms: int,
        end_open_ms: int,
        *,
        log_label: str = "intraday backfill",
    ) -> int:
        symbol = symbol.upper()
        if not self.symbol_eligible(symbol):
            raise ValueError(f"ineligible symbol {symbol}")
        if start_ms > end_open_ms:
            return 0
        query_end_ms = end_open_ms + MINUTE_MS - 1
        rows = await self.fetch_klines(symbol, INTERVAL, start_ms, query_end_ms)
        rows = [r for r in rows if start_ms <= int(r[0]) <= end_open_ms]
        if not rows:
            return 0
        for off in range(0, len(rows), 1200):
            chunk = rows[off: off + 1200]
            bars = []
            for r in chunk:
                open_s = int(r[0]) // 1000
                bars.append([
                    open_s,
                    float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]),
                    0.0, float(r[7]), float(r[8]),
                ])
            await self.relay_send({"hist": symbol, "format": "gohlcvixy", "bars": bars})
            await asyncio.sleep(0.02)
        self.update_1m_watermark(symbol, int(rows[-1][0]), allow_jump=True)
        LOG.info("sent %s symbol=%s bars=%d", log_label, symbol, len(rows))
        return len(rows)

    async def send_intraday_history(self, symbol: str, days: int = FULL_BF_DAYS, start_ms: int | None = None) -> int:
        symbol = symbol.upper()
        now_ms = int(time.time() * 1000)
        end_open_ms = self.completed_1m_open_ms(now_ms)
        floor_ms = end_open_ms - (MAX_BF_DAYS * 24 * 60 - 1) * MINUTE_MS
        if start_ms is None:
            minutes = min(MAX_BF_DAYS, max(1, days)) * 24 * 60
            start_ms = end_open_ms - (minutes - 1) * MINUTE_MS
        else:
            start_ms = max(int(start_ms), floor_ms)
        return await self.send_intraday_range(symbol, start_ms, end_open_ms, log_label="intraday backfill")

    async def send_intraday_target(self, symbol: str, records: int = RECOVERY_1M_RECORDS) -> int:
        end_open_ms = self.completed_1m_open_ms()
        records = max(1, int(records))
        start_ms = end_open_ms - (records - 1) * MINUTE_MS
        return await self.send_intraday_range(
            symbol,
            start_ms,
            end_open_ms,
            log_label="automatic full intraday recovery",
        )

    async def repair_intraday_gap(self, symbol: str) -> int:
        symbol = symbol.upper()
        end_open_ms = self.completed_1m_open_ms()
        floor_ms = end_open_ms - (RECOVERY_1M_RECORDS - 1) * MINUTE_MS
        item = self.recovery_symbol_state(symbol)
        last_ms = int(item.get("last_completed_1m_open_ms", 0) or 0)
        if last_ms <= 0:
            start_ms = floor_ms
            LOG.info("recovery watermark absent symbol=%s; using bounded %d-bar baseline", symbol, RECOVERY_1M_RECORDS)
        else:
            start_ms = last_ms + MINUTE_MS
            if start_ms < floor_ms:
                dropped = max(0, (floor_ms - start_ms) // MINUTE_MS)
                LOG.warning(
                    "recovery gap exceeds retention symbol=%s dropped_outside_cache=%d; clamping to newest %d bars",
                    symbol, dropped, RECOVERY_1M_RECORDS,
                )
                start_ms = floor_ms
        if start_ms > end_open_ms:
            return 0
        return await self.send_intraday_range(
            symbol,
            start_ms,
            end_open_ms,
            log_label="automatic gap repair",
        )

    async def send_eod_history(
        self,
        symbol: str,
        days: int = EOD_BF_DAYS,
        *,
        target_bars: int | None = None,
        log_label: str = "EOD backfill",
    ) -> int:
        symbol = symbol.upper()
        if not self.symbol_eligible(symbol):
            raise ValueError(f"ineligible symbol {symbol}")
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - max(1, days) * DAY_MS
        rows = await self.fetch_klines(symbol, "1d", start_ms, now_ms)
        if not rows:
            return 0
        bars = []
        today = datetime.now(timezone.utc).date()
        for r in rows:
            dt = datetime.fromtimestamp(int(r[0]) / 1000.0, tz=timezone.utc)
            if dt.date() >= today:
                continue
            dn = dt.year * 10000 + dt.month * 100 + dt.day
            bars.append([dn, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])])
        if target_bars is not None and len(bars) > target_bars:
            bars = bars[-target_bars:]
        if bars:
            await self.relay_send({"hist": symbol, "format": "dohlcv", "bars": bars})
            self.update_eod_watermark(symbol, int(bars[-1][0]))
            LOG.info("sent %s symbol=%s bars=%d", log_label, symbol, len(bars))
        return len(bars)

    async def send_eod_target(self, symbol: str) -> int:
        return await self.send_eod_history(
            symbol,
            days=max(EOD_BF_DAYS, RECOVERY_EOD_BARS + 1),
            target_bars=RECOVERY_EOD_BARS,
            log_label="automatic EOD recovery",
        )

    async def recovery_pass(self, *, full: bool, reasons: list[str]) -> None:
        if not RECOVERY_ENABLED or self.receiver_count <= 0:
            return
        async with self.recovery_lock:
            async with self.backfill_sem:
                LOG.info(
                    "automatic recovery start mode=%s receivers=%d reasons=%s",
                    "FULL" if full else "GAP",
                    self.receiver_count,
                    ",".join(reasons) if reasons else "audit",
                )
                total_1m = 0
                total_eod = 0
                yesterday = self.yesterday_date_num()
                for symbol in sorted(self.active):
                    if self.receiver_count <= 0 or self.stop.is_set():
                        LOG.warning("automatic recovery interrupted because receiver detached")
                        break
                    if full:
                        total_1m += await self.send_intraday_target(symbol)
                        total_eod += await self.send_eod_target(symbol)
                    else:
                        total_1m += await self.repair_intraday_gap(symbol)
                        item = self.recovery_symbol_state(symbol)
                        last_eod = int(item.get("last_completed_eod_date", 0) or 0)
                        if last_eod < yesterday:
                            total_eod += await self.send_eod_target(symbol)
                self.save_recovery_state()
                LOG.info(
                    "automatic recovery complete mode=%s intraday_bars=%d eod_bars=%d receivers=%d",
                    "FULL" if full else "GAP",
                    total_1m,
                    total_eod,
                    self.receiver_count,
                )

    async def recovery_loop(self) -> None:
        if not RECOVERY_ENABLED:
            return
        while not self.stop.is_set():
            timed_out = False
            try:
                await asyncio.wait_for(self.recovery_event.wait(), timeout=RECOVERY_AUDIT_SEC)
            except asyncio.TimeoutError:
                timed_out = True
            self.recovery_event.clear()
            if self.receiver_count <= 0:
                self.recovery_reasons.clear()
                self.recovery_full_requested = False
                continue
            full = self.recovery_full_requested
            self.recovery_full_requested = False
            reasons = sorted(self.recovery_reasons)
            self.recovery_reasons.clear()
            if timed_out and not reasons:
                reasons = ["periodic-audit"]
            try:
                await self.recovery_pass(full=full, reasons=reasons)
            except asyncio.CancelledError:
                raise
            except Exception:
                LOG.exception("automatic recovery pass failed")
                try:
                    await asyncio.wait_for(self.stop.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                self.request_recovery("retry-after-recovery-failure", full=full)

    async def run(self) -> None:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        headers = {"User-Agent": "WSRTD-Binance-USDM-Bridge/1.0"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            self.session = session
            await self.wait_for_preflight()
            tasks = [
                asyncio.create_task(self.relay_loop(), name="relay"),
                asyncio.create_task(self.market_loop(), name="market"),
                asyncio.create_task(self.public_loop(), name="public"),
                asyncio.create_task(self.publish_loop(), name="publisher"),
                asyncio.create_task(self.open_interest_loop(), name="open-interest"),
                asyncio.create_task(self.recovery_loop(), name="recovery"),
                asyncio.create_task(self.recovery_state_writer_loop(), name="recovery-state-writer"),
            ]
            try:
                await self.stop.wait()
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                try:
                    self.save_recovery_state()
                except Exception:
                    LOG.exception("final recovery state save failed")
                self.session = None


async def main() -> None:
    app = App()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, app.stop.set)
    LOG.info("bootstrap symbols (%d): %s", len(BOOTSTRAP), ",".join(BOOTSTRAP))
    LOG.info("Binance endpoints market=%s public=%s rest=%s", MARKET_WS, PUBLIC_WS, REST_BASE)
    LOG.info("backfill horizons intraday_full_days=%d intraday_max_days=%d eod_request_days=%d", FULL_BF_DAYS, MAX_BF_DAYS, EOD_BF_DAYS)
    LOG.info(
        "automatic recovery enabled=%s intraday_target=%d eod_target=%d audit_seconds=%.1f state=%s",
        RECOVERY_ENABLED, RECOVERY_1M_RECORDS, RECOVERY_EOD_BARS, RECOVERY_AUDIT_SEC, RECOVERY_STATE_PATH,
    )
    await app.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
