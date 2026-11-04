#!/usr/bin/env python3
"""Local WSRTD relay with receiver-presence status for R2.1 recovery.

Root / and /receiver connections are treated as WSRTD/AmiBroker receivers.
/sender connections are treated as market-data senders.
Messages from receivers are forwarded to all senders; messages from senders
are forwarded to all receivers. Internal relay-status packets are sent only
to sender connections so the Binance bridge knows whether AmiBroker is ready
to receive automatic recovery history.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Iterable

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

BASE = Path(__file__).resolve().parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
RCFG = CFG["relay"]
HOST = os.getenv("WSRTD_RELAY_HOST", str(RCFG.get("host", "127.0.0.1")))
PORT = int(os.getenv("WSRTD_RELAY_PORT", str(RCFG.get("port", 10101))))
AUTH = os.getenv("WSRTD_RELAY_AUTH", str(RCFG.get("auth_code", "")))
MAX_SIZE = int(RCFG.get("max_message_bytes", 8 * 1024 * 1024))
SEND_TIMEOUT = float(RCFG.get("send_timeout_seconds", 5))

(BASE / "logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BASE / "logs" / "relay.log", encoding="utf-8"),
    ],
)
LOG = logging.getLogger("wsrtd-relay")

RECEIVERS: set[ServerConnection] = set()
SENDERS: set[ServerConnection] = set()


def _path(ws: ServerConnection) -> str:
    req = getattr(ws, "request", None)
    return getattr(req, "path", "/") or "/"


async def _safe_send(ws: ServerConnection, message: str) -> bool:
    try:
        async with asyncio.timeout(SEND_TIMEOUT):
            await ws.send(message)
        return True
    except Exception:
        return False


async def _fanout(peers: Iterable[ServerConnection], message: str) -> None:
    peers = list(peers)
    if not peers:
        return
    results = await asyncio.gather(*(_safe_send(p, message) for p in peers))
    for peer, ok in zip(peers, results):
        if not ok:
            RECEIVERS.discard(peer)
            SENDERS.discard(peer)
            try:
                await peer.close(code=1011, reason="relay send failure")
            except Exception:
                pass


def _status_message() -> str:
    return json.dumps(
        {
            "_relay": "status",
            "protocol": "wsrtd-relay-status-v1",
            "receivers": len(RECEIVERS),
            "senders": len(SENDERS),
            "unix_ms": int(time.time() * 1000),
        },
        separators=(",", ":"),
    )


async def _notify_senders_status() -> None:
    await _fanout(SENDERS, _status_message())


async def handler(ws: ServerConnection) -> None:
    path = _path(ws)
    role = "sender" if path.startswith("/sender") else "receiver"
    peers = SENDERS if role == "sender" else RECEIVERS
    peers.add(ws)
    authed = (role == "sender") or (AUTH == "")
    LOG.info("%s connected path=%s receivers=%d senders=%d", role, path, len(RECEIVERS), len(SENDERS))

    if role == "sender":
        await _safe_send(ws, _status_message())
    else:
        await _notify_senders_status()

    try:
        async for raw in ws:
            if not isinstance(raw, str):
                continue
            msg = raw.strip()
            if not msg:
                continue
            if msg in {"rolesend", "rolerecv"}:
                continue
            if role == "receiver" and not authed:
                if msg == AUTH:
                    authed = True
                    LOG.info("receiver authenticated")
                    continue
                LOG.warning("receiver auth rejected")
                await ws.close(code=1008, reason="authentication failed")
                return
            if role == "receiver" and not (msg.startswith("{") or msg.startswith("[")):
                LOG.info("ignored receiver non-JSON control string")
                continue
            if role == "sender":
                await _fanout(RECEIVERS, msg)
            else:
                await _fanout(SENDERS, msg)
    except ConnectionClosed:
        pass
    finally:
        peers.discard(ws)
        LOG.info("%s disconnected receivers=%d senders=%d", role, len(RECEIVERS), len(SENDERS))
        await _notify_senders_status()


async def main() -> None:
    LOG.info("WSRTD relay listening on ws://%s:%d (root=receiver, /sender=sender)", HOST, PORT)
    async with serve(
        handler,
        HOST,
        PORT,
        max_size=MAX_SIZE,
        ping_interval=20,
        ping_timeout=20,
        close_timeout=5,
        compression=None,
    ):
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
