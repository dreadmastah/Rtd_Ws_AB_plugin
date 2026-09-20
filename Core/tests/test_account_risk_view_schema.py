#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
schema = json.loads(
    (ROOT / "schemas" / "AccountRiskView.v1.schema.json").read_text(encoding="utf-8")
)
assert schema["properties"]["orderRoutingEnabled"]["const"] is False
assert set(schema["properties"]["gateState"]["enum"]) == {
    "CLEAR",
    "ACCOUNT_NOT_RECONCILED",
    "RISK_BLOCKED",
}
print("ACCOUNT_RISK_VIEW_SCHEMA=PASS")
