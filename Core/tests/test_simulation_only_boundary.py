from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "Core"


forbidden_order_path = "/fapi/" + "v1/order"
forbidden_activation_flag = "--enable-testnet-" + "order-routing"
forbidden_arm_flag = "--arm-testnet-" + "order-routing"

scanned = sorted(
    path
    for path in CORE.rglob("*")
    if path.is_file() and path.suffix.lower() in {".cpp", ".hpp", ".py", ".cmd"}
)
for path in scanned:
    text = path.read_text(encoding="utf-8")
    assert forbidden_order_path not in text, path
    assert forbidden_activation_flag not in text, path
    assert forbidden_arm_flag not in text, path

removed_submission_files = [
    CORE / "execution" / "include" / "astu" / "execution" /
    "binance_usdm_testnet_order_gateway.hpp",
    CORE / "execution" / "include" / "astu" / "execution" /
    "testnet_order_router.hpp",
    CORE / "tools" / "testnet_acceptance.py",
]
assert all(not path.exists() for path in removed_submission_files)

host = (
    CORE / "execution" / "src" / "execution_pipe_host.cpp"
).read_text(encoding="utf-8")
assert "ORDER_ROUTING_ENABLED=false" in host
assert "EXECUTION_ENVIRONMENT=SIMULATION_ONLY" in host

print("SIMULATION_ONLY_BOUNDARY=PASS")
