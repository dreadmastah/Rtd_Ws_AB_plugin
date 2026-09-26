#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

ALLOWED_STATES = {
    "INTENT_RECEIVED",
    "VALIDATING",
    "RISK_APPROVED",
    "SIZING",
    "SUBMITTING",
    "ACKNOWLEDGED",
    "WORKING",
    "PARTIAL",
    "FILLED",
    "CANCELED",
    "REJECTED",
    "UNKNOWN_RECONCILE_REQUIRED",
}


def write_atomic(path: Path, obj: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(obj, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def publish(
    *,
    output_dir: Path,
    order_id: str,
    state: str,
    cumulative_filled: float,
    source: str,
    detail: str,
    ready: bool,
    generated_unix_ms: int | None = None,
) -> Path:
    order_id = order_id.strip()
    state = state.strip().upper()
    if not order_id:
        raise ValueError("simulation order id is required")
    if state not in ALLOWED_STATES:
        raise ValueError(f"unsupported order state: {state}")
    if cumulative_filled < 0:
        raise ValueError("cumulative fill must be non-negative")
    if not source.strip():
        raise ValueError("source is required")

    snapshot = {
        "schemaVersion": 1,
        "messageType": "AuthoritativeSimulationOrderSnapshot.v1",
        "generatedUnixMs": generated_unix_ms or int(time.time() * 1000),
        "ready": bool(ready),
        "source": source.strip(),
        "simulationOrderId": order_id,
        "state": state,
        "cumulativeFilledQuantity": float(cumulative_filled),
        "detail": detail[:512],
    }
    path = output_dir / f"{order_id}.json"
    write_atomic(path, snapshot)
    print(
        "AUTHORITATIVE_SIM_ORDER_SNAPSHOT=published "
        f"orderId={order_id} state={state} "
        f"cumulativeFilled={cumulative_filled} ready={str(ready).lower()} "
        f"path={path}"
    )
    print("EXCHANGE_SUBMISSION_ATTEMPTED=false")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Publish a local authoritative SIMULATION order-state snapshot. "
            "This utility has no exchange/network/order-submission behavior."
        )
    )
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--order-id", required=True)
    ap.add_argument("--state", required=True, choices=sorted(ALLOWED_STATES))
    ap.add_argument("--cumulative-filled", type=float, default=0.0)
    ap.add_argument(
        "--source",
        default="SIMULATED_AUTHORITATIVE_ORDER_STATE",
    )
    ap.add_argument("--detail", default="simulation order-state fixture")
    ap.add_argument("--not-ready", action="store_true")
    ap.add_argument("--generated-unix-ms", type=int)
    args = ap.parse_args()

    publish(
        output_dir=args.output_dir,
        order_id=args.order_id,
        state=args.state,
        cumulative_filled=args.cumulative_filled,
        source=args.source,
        detail=args.detail,
        ready=not args.not_ready,
        generated_unix_ms=args.generated_unix_ms,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
