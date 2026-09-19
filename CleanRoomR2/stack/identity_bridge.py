#!/usr/bin/env python3
"""WSRTD R2 -> auto-trader identity compatibility bridge.

This process is read-only with respect to market/exchange state. It converts the
existing R2 bootstrap universe plus recovery watermarks into a versioned local
identity snapshot for the simulation-only auto-trader core.

Compatibility definition for this bridge:
- universeVersion is taken only from the tracked universe_identity.v1.json.
- dataGeneration is the exact completed 1-minute open timestamp in milliseconds
  from recovery_state.json for each symbol.
- generationKind is WSRTD_R2_COMPLETED_M1_OPEN_MS.

No exchange credentials, private API access, or order-routing functionality is
present here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
RECOV_CFG = CFG.get("recovery", {})
IDENTITY_CFG = CFG.get("identity_bridge", {})

RECOVERY_FILE_CFG = Path(str(RECOV_CFG.get("state_file", "runtime/recovery_state.json")))
RECOVERY_PATH = RECOVERY_FILE_CFG if RECOVERY_FILE_CFG.is_absolute() else BASE / RECOVERY_FILE_CFG
MANIFEST_FILE_CFG = Path(str(IDENTITY_CFG.get("manifest_file", "universe_identity.v1.json")))
MANIFEST_PATH = MANIFEST_FILE_CFG if MANIFEST_FILE_CFG.is_absolute() else BASE / MANIFEST_FILE_CFG
OUTPUT_FILE_CFG = Path(str(IDENTITY_CFG.get("output_file", "runtime/data_identity.v1.json")))
OUTPUT_PATH = OUTPUT_FILE_CFG if OUTPUT_FILE_CFG.is_absolute() else BASE / OUTPUT_FILE_CFG
STATUS_DIR_CFG = Path(str(IDENTITY_CFG.get("status_dir", "runtime/autotrader_status")))
STATUS_DIR = STATUS_DIR_CFG if STATUS_DIR_CFG.is_absolute() else BASE / STATUS_DIR_CFG
MARKET_STATUS_CFG = CFG.get("autotrader_status", {})
MARKET_STATUS_FILE_CFG = Path(
    str(MARKET_STATUS_CFG.get("output_file", "runtime/market_status.v1.json"))
)
MARKET_STATUS_PATH = (
    MARKET_STATUS_FILE_CFG
    if MARKET_STATUS_FILE_CFG.is_absolute()
    else BASE / MARKET_STATUS_FILE_CFG
)
POLL_SECONDS = max(0.25, float(IDENTITY_CFG.get("poll_seconds", 1.0)))
ENABLED = bool(IDENTITY_CFG.get("enabled", True))
GENERATION_KIND = "WSRTD_R2_COMPLETED_M1_OPEN_MS"

(BASE / "logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BASE / "logs" / "identity_bridge.log", encoding="utf-8"),
    ],
)
LOG = logging.getLogger("wsrtd-identity-bridge")


def load_bootstrap() -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for line in (BASE / "bootstrap_symbols.tls").read_text(encoding="utf-8-sig").splitlines():
        symbol = line.strip().upper()
        if not symbol or symbol.startswith("#") or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
    if not symbols:
        raise RuntimeError("bootstrap_symbols.tls contains no symbols")
    return symbols


def canonical_universe_hash(symbols: list[str]) -> str:
    body = ("\n".join(symbols) + "\n").encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def load_and_verify_manifest() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if int(manifest.get("schemaVersion", 0) or 0) != 1:
        raise RuntimeError("identity manifest schemaVersion must be 1")
    universe_id = str(manifest.get("universeId", "")).strip()
    universe_version = int(manifest.get("universeVersion", 0) or 0)
    symbols = [str(x).strip().upper() for x in manifest.get("symbols", [])]
    expected_hash = str(manifest.get("universeHash", "")).strip().lower()
    bootstrap = load_bootstrap()
    actual_hash = canonical_universe_hash(bootstrap)
    if not universe_id or universe_version <= 0:
        raise RuntimeError("identity manifest universeId/universeVersion invalid")
    if symbols != bootstrap:
        raise RuntimeError("identity manifest symbols do not exactly match bootstrap_symbols.tls")
    if expected_hash != actual_hash:
        raise RuntimeError(
            f"identity manifest hash mismatch expected={expected_hash} actual={actual_hash}"
        )
    return {
        "universeId": universe_id,
        "universeVersion": universe_version,
        "universeHash": actual_hash,
        "symbols": bootstrap,
    }


def load_recovery_state() -> dict[str, Any]:
    if not RECOVERY_PATH.exists():
        return {"version": 1, "symbols": {}}
    try:
        obj = json.loads(RECOVERY_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        LOG.warning("recovery state unreadable: %s", exc)
        return {"version": 1, "symbols": {}}
    if not isinstance(obj, dict) or not isinstance(obj.get("symbols"), dict):
        LOG.warning("recovery state structure invalid")
        return {"version": 1, "symbols": {}}
    return obj


def load_market_status() -> dict[str, Any]:
    if not MARKET_STATUS_PATH.exists():
        return {"schemaVersion": 1, "symbols": {}}
    try:
        obj = json.loads(MARKET_STATUS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        LOG.warning("market status unreadable: %s", exc)
        return {"schemaVersion": 1, "symbols": {}}
    if not isinstance(obj, dict) or not isinstance(obj.get("symbols"), dict):
        LOG.warning("market status structure invalid")
        return {"schemaVersion": 1, "symbols": {}}
    return obj


def build_snapshot(manifest: dict[str, Any], recovery: dict[str, Any]) -> dict[str, Any]:
    recovery_symbols = recovery.get("symbols", {})
    output_symbols: dict[str, Any] = {}
    all_ready = True
    for symbol in manifest["symbols"]:
        item = recovery_symbols.get(symbol, {})
        if not isinstance(item, dict):
            item = {}
        completed_m1 = int(item.get("last_completed_1m_open_ms", 0) or 0)
        last_eod = int(item.get("last_completed_eod_date", 0) or 0)
        ready = completed_m1 > 0
        all_ready = all_ready and ready
        output_symbols[symbol] = {
            "identityReady": ready,
            "dataGeneration": completed_m1 if ready else None,
            "generationKind": GENERATION_KIND,
            "lastCompleted1mOpenMs": completed_m1 if ready else None,
            "lastCompletedEodDate": last_eod if last_eod > 0 else None,
            "recoveryUpdatedUtc": item.get("updated_utc"),
        }
    return {
        "schemaVersion": 1,
        "source": "WSRTD-CleanRoomR2",
        "universeId": manifest["universeId"],
        "universeVersion": manifest["universeVersion"],
        "universeHash": manifest["universeHash"],
        "generationKind": GENERATION_KIND,
        "identityReady": all_ready,
        "generatedUtc": datetime.now(timezone.utc).isoformat(),
        "recoveryStateSavedUtc": recovery.get("saved_utc"),
        "symbols": output_symbols,
    }


def write_atomic(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def build_runtime_status_files(
    manifest: dict[str, Any],
    recovery: dict[str, Any],
    market: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    recovery_symbols = recovery.get("symbols", {})
    market_symbols = market.get("symbols", {})
    generated_ms = int(time.time() * 1000)
    files: dict[str, dict[str, Any]] = {}

    for symbol in manifest["symbols"]:
        rec = recovery_symbols.get(symbol, {})
        if not isinstance(rec, dict):
            rec = {}
        mk = market_symbols.get(symbol, {})
        if not isinstance(mk, dict):
            mk = {}

        generation = int(rec.get("last_completed_1m_open_ms", 0) or 0)
        last_eod = int(rec.get("last_completed_eod_date", 0) or 0)
        live = bool(mk.get("live", False))
        fresh = bool(mk.get("fresh", False))
        history_hydrated = bool(mk.get("historyHydrated", False))
        quote_age_raw = mk.get("quoteAgeMs")
        quote_age = int(quote_age_raw) if isinstance(quote_age_raw, (int, float)) else 0

        identity_ready = generation > 0
        cache_ready = history_hydrated
        detail_parts: list[str] = []
        if not live:
            detail_parts.append("market sockets/data not live")
        if not fresh:
            detail_parts.append("quote freshness not ready")
        if not cache_ready:
            detail_parts.append("full bounded receiver hydration not confirmed")
        if not identity_ready:
            detail_parts.append("completed-1m identity watermark unavailable")
        if not detail_parts:
            detail_parts.append("WSRTD runtime data/identity ready")

        files[symbol] = {
            "schemaVersion": 1,
            "source": "WSRTD-CleanRoomR2",
            "symbol": symbol,
            "generatedUnixMs": generated_ms,
            "live": live,
            "fresh": fresh,
            "cacheReady": cache_ready,
            "identityReady": identity_ready,
            "universeId": manifest["universeId"] if identity_ready else "",
            "universeVersion": manifest["universeVersion"] if identity_ready else 0,
            "universeHash": manifest["universeHash"] if identity_ready else "",
            "dataGeneration": generation if identity_ready else 0,
            "generationKind": GENERATION_KIND if identity_ready else "",
            "cacheEod": 300 if cache_ready and last_eod > 0 else 0,
            "cacheIntraday": 1500 if cache_ready else 0,
            "quoteAgeMs": max(0, quote_age),
            "detail": "; ".join(detail_parts),
        }

    return files


def write_runtime_status_files(files: dict[str, dict[str, Any]]) -> None:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    for symbol, obj in files.items():
        write_atomic(STATUS_DIR / f"{symbol}.json", obj)


def write_once(manifest: dict[str, Any]) -> dict[str, Any]:
    recovery = load_recovery_state()
    market = load_market_status()
    snapshot = build_snapshot(manifest, recovery)
    write_atomic(OUTPUT_PATH, snapshot)
    write_runtime_status_files(build_runtime_status_files(manifest, recovery, market))
    return snapshot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    if not ENABLED:
        LOG.info("identity bridge disabled")
        return 0
    manifest = load_and_verify_manifest()
    LOG.info(
        "identity manifest verified universe=%s version=%d hash=%s symbols=%d",
        manifest["universeId"], manifest["universeVersion"],
        manifest["universeHash"], len(manifest["symbols"]),
    )
    if args.once:
        snapshot = write_once(manifest)
        LOG.info(
            "identity snapshot written once ready=%s path=%s status_dir=%s",
            snapshot["identityReady"], OUTPUT_PATH, STATUS_DIR,
        )
        return 0
    while True:
        snapshot = write_once(manifest)
        LOG.debug(
            "identity snapshot refreshed ready=%s status_dir=%s",
            snapshot["identityReady"], STATUS_DIR,
        )
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
