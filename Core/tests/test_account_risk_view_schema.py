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
assert "accountRiskObservation" in schema["required"]
assert "symbolRisk" in schema["required"]
symbol_risk = schema["properties"]["symbolRisk"]
assert symbol_risk["additionalProperties"] is False
assert symbol_risk["properties"]["symbols"]["maxItems"] == 64
account = schema["properties"]["accountRiskObservation"]
assert account["additionalProperties"] is False
assert "projectedEffectiveLeverage" in account["required"]
assert "longDirectionalHeadroom" in account["required"]

execution_schema = json.loads(
    (ROOT / "schemas" / "ExecutionStatus.v1.schema.json").read_text(encoding="utf-8")
)
for key in (
    "accountRiskObservationReady",
    "currentRiskCapital",
    "projectedAvailableBalance",
    "projectedGrossNotional",
    "projectedEffectiveLeverage",
    "projectedMarginUtilization",
    "projectedNetDirectionalNotional",
):
    assert key in execution_schema["required"]
    assert key in execution_schema["properties"]
assert execution_schema["properties"]["orderRoutingEnabled"]["const"] is False

symbol_schema = json.loads(
    (ROOT / "schemas" / "SymbolRiskStatus.v1.schema.json").read_text(encoding="utf-8")
)
assert symbol_schema["properties"]["orderRoutingEnabled"]["const"] is False
assert symbol_schema["properties"]["symbols"]["maxItems"] == 64
print("ACCOUNT_RISK_VIEW_SCHEMA=PASS")
print("EXECUTION_STATUS_ACCOUNT_RISK_OBSERVABILITY_SCHEMA=PASS")
print("SYMBOL_RISK_STATUS_SCHEMA=PASS")
