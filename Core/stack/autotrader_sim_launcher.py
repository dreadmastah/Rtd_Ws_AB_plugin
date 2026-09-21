#!/usr/bin/env python3
"""Simulation-only supervisor for the auto-trader runtime."""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
RUNTIME = ROOT / "runtime"
LOGS = RUNTIME / "logs"
PID_FILE = RUNTIME / "autotrader_sim_pids.json"
LOCK_FILE = RUNTIME / "autotrader_sim_launcher.lock.json"
CLAIM_FILE = RUNTIME / "autotrader_sim_launcher.claim.json"
RISK_FILE = RUNTIME / "account_risk_status.v1.json"
REALIZED_PNL_FILE = RUNTIME / "realized_pnl_status.v1.json"
REALIZED_PNL_STATE = RUNTIME / "realized_pnl_accumulator.v1.json"
POSITION_DIR = RUNTIME / "position_status"
EXECUTION_STATUS_FILE = RUNTIME / "execution_status.v1.json"
SYMBOL_RISK_STATUS_FILE = RUNTIME / "symbol_risk_status.v1.json"
SYMBOL_RISK_UNIVERSE_FILE = REPO / "CleanRoomR2" / "stack" / "bootstrap_symbols.tls"
DEFAULT_STATUS_DIR = REPO / "CleanRoomR2" / "stack" / "runtime" / "autotrader_status"
DEFAULT_HOST = REPO / "build" / "core" / "Release" / "astu_execution_pipe_host.exe"
GATEWAY = ROOT / "account" / "binance_usdm_readonly_gateway.py"
FIXTURE = ROOT / "account" / "tests" / "fixtures" / "binance_usdm_account_v3.json"
INCOME_RECONCILER = ROOT / "account" / "binance_usdm_income_reconciler.py"
INCOME_FIXTURE = ROOT / "account" / "tests" / "fixtures" / "binance_usdm_income_v1.json"
INSTRUMENT_PUBLISHER = ROOT / "instrument" / "binance_usdm_instrument_rules.py"
INSTRUMENT_FIXTURE = ROOT / "instrument" / "tests" / "fixtures" / "binance_usdm_exchange_info_bootstrap12.json"
INSTRUMENT_DIR = RUNTIME / "instrument_constraints"
ORDER_SNAPSHOT_DIR = RUNTIME / "authoritative_order_snapshots"
ACCOUNT_RISK_VIEW = ROOT / "operator" / "account_risk_view.py"
ACCOUNT_RISK_VIEW_JSON = RUNTIME / "account_risk_view.v1.json"
ACCOUNT_RISK_VIEW_HTML = RUNTIME / "account_risk_view.html"
TESTNET_USER_DATA = ROOT / "account" / "binance_usdm_testnet_user_data.py"
TESTNET_USER_DATA_STATUS = RUNTIME / "testnet_user_data_status.v1.json"
TESTNET_ORDER_AUTHORITY_DIR = RUNTIME / "testnet_order_authority"

PID_SCHEMA_VERSION = 2
PROCESS_OWNER_MATCH = "MATCH"
PROCESS_OWNER_STALE = "STALE"
PROCESS_OWNER_DEAD = "DEAD"
PROCESS_OWNER_AMBIGUOUS = "AMBIGUOUS"
LAUNCH_OWNERSHIP_ACQUIRED = "ACQUIRED"
LAUNCH_OWNERSHIP_ALREADY_RUNNING = "ALREADY_RUNNING"
LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS = "LIVE_OWNER_AMBIGUOUS"
SENSITIVE_ENV_NAMES = frozenset({
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "ASTU_BINANCE_TESTNET_API_KEY",
    "ASTU_BINANCE_TESTNET_API_SECRET",
    "ASTU_PRIVATE_TOKEN",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "OPENAI_API_KEY",
    "AWS_SECRET_ACCESS_KEY",
})
SENSITIVE_ENV_SUFFIXES = (
    "_API_KEY",
    "_API_SECRET",
    "_ACCESS_TOKEN",
    "_AUTH_TOKEN",
    "_CLIENT_SECRET",
    "_PASSWORD",
    "_PRIVATE_KEY",
    "_TOKEN",
)
BENIGN_ENV_NAMES = frozenset({"TOKENIZERS_PARALLELISM"})
CREDENTIAL_PROFILE_NONE = "NONE"
CREDENTIAL_PROFILE_BINANCE_READONLY = "BINANCE_READONLY"
CREDENTIAL_PROFILE_BINANCE_DEMO_SIGNED = "BINANCE_DEMO_SIGNED"
CREDENTIAL_PROFILE_TESTNET_USER_DATA = "TESTNET_USER_DATA"

RUNTIME.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        return process_identity(pid) is not None
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _normalize_executable(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def process_identity(pid: int) -> dict[str, object] | None:
    """Return stable process identity fields, or None when PID is unavailable."""
    if pid <= 0:
        return None
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(
            process_query_limited_information,
            False,
            pid,
        )
        if not handle:
            return None
        try:
            size = wintypes.DWORD(32768)
            image = ctypes.create_unicode_buffer(size.value)
            if not kernel32.QueryFullProcessImageNameW(
                handle,
                0,
                image,
                ctypes.byref(size),
            ):
                return None
            created = wintypes.FILETIME()
            exited = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(created),
                ctypes.byref(exited),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                return None
            creation_time_100ns = (
                int(created.dwHighDateTime) << 32
            ) | int(created.dwLowDateTime)
            return {
                "pid": pid,
                "creationTime100ns": creation_time_100ns,
                "executable": _normalize_executable(image.value),
            }
        finally:
            kernel32.CloseHandle(handle)

    proc_dir = Path("/proc") / str(pid)
    try:
        stat_text = (proc_dir / "stat").read_text(encoding="utf-8")
        stat_fields = stat_text[stat_text.rfind(")") + 2 :].split()
        executable = os.readlink(proc_dir / "exe")
        return {
            "pid": pid,
            "creationTime100ns": int(stat_fields[19]),
            "executable": _normalize_executable(executable),
        }
    except (OSError, ValueError, IndexError):
        return None


def pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        cp = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = (cp.stdout or "").strip()
        return bool(out) and not out.upper().startswith("INFO:")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def process_record_status(record: object) -> str:
    if not isinstance(record, dict):
        return PROCESS_OWNER_AMBIGUOUS
    try:
        pid = int(record["pid"])
        created = int(record["creationTime100ns"])
        executable = _normalize_executable(str(record["executable"]))
    except (KeyError, TypeError, ValueError):
        return PROCESS_OWNER_AMBIGUOUS
    actual = process_identity(pid)
    if actual is None:
        return PROCESS_OWNER_AMBIGUOUS if pid_exists(pid) else PROCESS_OWNER_DEAD
    if (
        int(actual["creationTime100ns"]) == created
        and _normalize_executable(str(actual["executable"])) == executable
    ):
        return PROCESS_OWNER_MATCH
    return PROCESS_OWNER_STALE


def process_record_matches(record: object) -> bool:
    return process_record_status(record) == PROCESS_OWNER_MATCH


def load_json_object(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except (OSError, ValueError):
        return {}


def load_pid_state() -> dict[str, object]:
    return load_json_object(PID_FILE)


def _atomic_create_json(path: Path, obj: Mapping[str, object]) -> bool:
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
        fh.write("\n")
    return True


def lock_is_owned(lock: object) -> bool:
    return bool(
        isinstance(lock, dict)
        and isinstance(lock.get("launchNonce"), str)
        and lock.get("launchNonce")
        and process_record_matches(lock.get("launcher"))
    )


def acquire_launch_lock(
    launch_nonce: str,
    launcher_record: Mapping[str, object],
) -> bool:
    payload = {
        "schemaVersion": PID_SCHEMA_VERSION,
        "launchNonce": launch_nonce,
        "launcher": dict(launcher_record),
    }
    for _ in range(3):
        if _atomic_create_json(LOCK_FILE, payload):
            return True
        if lock_is_owned(load_json_object(LOCK_FILE)):
            return False
        with contextlib.suppress(OSError):
            LOCK_FILE.unlink()
    return False


def acquire_claim_guard(
    launch_nonce: str,
    launcher_record: Mapping[str, object],
) -> bool:
    payload = {
        "schemaVersion": PID_SCHEMA_VERSION,
        "launchNonce": launch_nonce,
        "launcher": dict(launcher_record),
    }
    for _ in range(3):
        if _atomic_create_json(CLAIM_FILE, payload):
            return True
        guard = load_json_object(CLAIM_FILE)
        for _wait in range(10):
            if guard or not CLAIM_FILE.exists():
                break
            time.sleep(0.01)
            guard = load_json_object(CLAIM_FILE)
        if guard and process_record_matches(guard.get("launcher")):
            return False
        with contextlib.suppress(OSError):
            CLAIM_FILE.unlink()
    return False


def release_claim_guard(launch_nonce: str) -> None:
    guard = load_json_object(CLAIM_FILE)
    if guard.get("launchNonce") == launch_nonce:
        with contextlib.suppress(OSError):
            CLAIM_FILE.unlink()


def _claim_launcher_ownership_guarded(
    launch_nonce: str,
    launcher_record: Mapping[str, object],
) -> str:
    """Adjudicate existing state before attempting atomic lock ownership."""
    state_file_exists = PID_FILE.exists()
    state = load_pid_state()
    if state_file_exists and not state:
        return LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS
    if state:
        processes = state.get("processes")
        recorded_nonce = state.get("launchNonce")
        if (
            state.get("schemaVersion") != PID_SCHEMA_VERSION
            or not isinstance(recorded_nonce, str)
            or not recorded_nonce
            or not isinstance(processes, dict)
            or "launcher" not in processes
        ):
            return LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS

        recorded_launcher = processes["launcher"]
        owner_status = process_record_status(recorded_launcher)
        if owner_status == PROCESS_OWNER_MATCH:
            return (
                LAUNCH_OWNERSHIP_ALREADY_RUNNING
                if state_has_valid_lock(state)
                else LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS
            )
        if owner_status == PROCESS_OWNER_AMBIGUOUS:
            return LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS

        child_statuses = {
            name: process_record_status(record)
            for name, record in processes.items()
            if name != "launcher"
        }
        if any(
            status in (PROCESS_OWNER_MATCH, PROCESS_OWNER_AMBIGUOUS)
            for status in child_statuses.values()
        ):
            return LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS

        existing_lock = load_json_object(LOCK_FILE)
        if existing_lock and lock_is_owned(existing_lock):
            return LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS
        with contextlib.suppress(OSError):
            PID_FILE.unlink()
        with contextlib.suppress(OSError):
            LOCK_FILE.unlink()

    if acquire_launch_lock(launch_nonce, launcher_record):
        return LAUNCH_OWNERSHIP_ACQUIRED
    if lock_is_owned(load_json_object(LOCK_FILE)):
        return LAUNCH_OWNERSHIP_ALREADY_RUNNING
    return LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS


def claim_launcher_ownership(
    launch_nonce: str,
    launcher_record: Mapping[str, object],
) -> str:
    if not acquire_claim_guard(launch_nonce, launcher_record):
        return LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS
    try:
        return _claim_launcher_ownership_guarded(
            launch_nonce,
            launcher_record,
        )
    finally:
        release_claim_guard(launch_nonce)


def release_launch_lock(launch_nonce: str) -> None:
    lock = load_json_object(LOCK_FILE)
    if lock.get("launchNonce") == launch_nonce:
        with contextlib.suppress(OSError):
            LOCK_FILE.unlink()


def state_has_valid_lock(state: Mapping[str, object]) -> bool:
    lock = load_json_object(LOCK_FILE)
    processes = state.get("processes")
    return bool(
        state.get("schemaVersion") == PID_SCHEMA_VERSION
        and isinstance(state.get("launchNonce"), str)
        and state.get("launchNonce") == lock.get("launchNonce")
        and lock_is_owned(lock)
        and isinstance(processes, dict)
        and lock.get("launcher") == processes.get("launcher")
    )


def save_pids(
    process_records: Mapping[str, Mapping[str, object]],
    launch_nonce: str,
    *,
    startup_complete: bool = False,
) -> None:
    obj = {
        "schemaVersion": PID_SCHEMA_VERSION,
        "launchNonce": launch_nonce,
        "startupComplete": startup_complete,
        "processes": {
            name: dict(record) for name, record in process_records.items()
        },
    }
    tmp = PID_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, PID_FILE)


def persist_owned_child(
    process_records: dict[str, dict[str, object]],
    name: str,
    pid: int,
    launch_nonce: str,
) -> dict[str, object]:
    """Record a newly spawned child before startup advances to another child."""
    record = process_identity(pid)
    if record is None:
        raise RuntimeError(f"cannot establish ownership identity for child {name}")
    process_records[name] = record
    save_pids(process_records, launch_nonce)
    return record


def status() -> int:
    state = load_pid_state()
    processes = state.get("processes")
    if not isinstance(processes, dict) or not processes:
        print("ASTU_SIM_STACK_STATUS=STOPPED")
        return 1
    lock_valid = state_has_valid_lock(state)
    all_owned = lock_valid and state.get("startupComplete") is True
    for name, record in processes.items():
        owned = process_record_matches(record)
        pid = record.get("pid", 0) if isinstance(record, dict) else 0
        print(f"{name.upper()}_PID={pid} OWNED={owned}")
        all_owned = all_owned and owned
    print(f"LAUNCH_LOCK_OWNED={lock_valid}")
    print(f"ASTU_SIM_STACK_STATUS={'RUNNING' if all_owned else 'DEGRADED'}")

    routing_enabled = False
    execution_environment = "UNKNOWN"
    try:
        obj = json.loads(
            EXECUTION_STATUS_FILE.read_text(encoding="utf-8")
        )
        routing_enabled = obj.get("orderRoutingEnabled") is True
        execution_environment = str(
            obj.get("executionEnvironment", "UNKNOWN")
        )
    except Exception:
        pass
    print(
        "ORDER_ROUTING_ENABLED="
        f"{str(routing_enabled).lower()}"
    )
    print(f"EXECUTION_ENVIRONMENT={execution_environment}")
    return 0 if all_owned else 1


def stop() -> int:
    state = load_pid_state()
    processes = state.get("processes")
    launcher_record = (
        processes.get("launcher") if isinstance(processes, dict) else None
    )
    nonce = str(state.get("launchNonce", ""))
    if not state_has_valid_lock(state) or not process_record_matches(launcher_record):
        print("ASTU_SIM_STACK_STOP_REFUSED=OWNERSHIP_NOT_PROVEN")
        return 2
    launcher = int(launcher_record["pid"])
    if launcher != os.getpid():
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(launcher), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            with contextlib.suppress(OSError):
                os.kill(launcher, signal.SIGTERM)
    deadline = time.monotonic() + 5.0
    while process_record_matches(launcher_record) and time.monotonic() < deadline:
        time.sleep(0.05)
    if process_record_matches(launcher_record):
        print("ASTU_SIM_STACK_STOP_REFUSED=OWNED_PROCESS_DID_NOT_EXIT")
        return 3
    with contextlib.suppress(OSError):
        PID_FILE.unlink()
    release_launch_lock(nonce)
    print("ASTU_SIM_STACK_STOP_REQUESTED=YES")
    return 0


def is_sensitive_environment_name(name: str) -> bool:
    upper = name.upper()
    if upper in BENIGN_ENV_NAMES:
        return False
    return upper in SENSITIVE_ENV_NAMES or upper.endswith(SENSITIVE_ENV_SUFFIXES)


def sanitized_child_environment(
    overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not is_sensitive_environment_name(key)
    }
    env["PYTHONUNBUFFERED"] = "1"
    if overrides:
        env.update({str(key): str(value) for key, value in overrides.items()})
    return env


def selected_parent_environment(names: tuple[str, ...]) -> dict[str, str]:
    return {
        name: os.environ[name]
        for name in names
        if os.environ.get(name, "")
    }


def child_environment(credential_profile: str) -> dict[str, str]:
    overrides: dict[str, str] = {}
    if credential_profile == CREDENTIAL_PROFILE_BINANCE_READONLY:
        overrides = selected_parent_environment((
            "ASTU_BINANCE_PRIVATE_READONLY_ENABLED",
            "BINANCE_API_KEY",
            "BINANCE_API_SECRET",
            "BINANCE_USDM_BASE_URL",
        ))
    elif credential_profile == CREDENTIAL_PROFILE_BINANCE_DEMO_SIGNED:
        overrides = {
            "ASTU_BINANCE_PRIVATE_READONLY_ENABLED": "1",
            "BINANCE_API_KEY": os.environ["ASTU_BINANCE_TESTNET_API_KEY"],
            "BINANCE_API_SECRET": os.environ["ASTU_BINANCE_TESTNET_API_SECRET"],
        }
    elif credential_profile == CREDENTIAL_PROFILE_TESTNET_USER_DATA:
        overrides = selected_parent_environment((
            "ASTU_BINANCE_TESTNET_USER_DATA_ENABLED",
            "ASTU_BINANCE_TESTNET_API_KEY",
            "ASTU_BINANCE_TESTNET_USER_STREAM_URL_TEMPLATE",
        ))
    elif credential_profile != CREDENTIAL_PROFILE_NONE:
        raise ValueError(f"unknown child credential profile: {credential_profile}")
    return sanitized_child_environment(overrides)


def popen_child_process(
    command: list[str],
    *,
    stdout: object,
    credential_profile: str,
) -> subprocess.Popen:
    return subprocess.Popen(
        command,
        cwd=REPO,
        stdout=stdout,
        stderr=subprocess.STDOUT,
        env=child_environment(credential_profile),
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )


def wait_for_demo_convergence(
    path: Path,
    *,
    max_age_ms: int,
    timeout_seconds: float,
) -> tuple[bool, str]:
    deadline = time.monotonic() + timeout_seconds
    last_detail = "status unavailable"
    while time.monotonic() < deadline:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            generated = int(obj.get("generatedUnixMs", 0) or 0)
            age_ms = int(time.time() * 1000) - generated
            ready = obj.get("ready") is True
            stream_alive = obj.get("streamAlive") is True
            account_ok = obj.get("accountConverged") is True
            positions_ok = obj.get("positionsConverged") is True
            orders_ok = obj.get("ordersConverged") is True
            unresolved = int(obj.get("unresolvedAstuOrders", -1))
            fallback = obj.get("restFallbackRequired") is True
            fresh = generated > 0 and 0 <= age_ms <= max_age_ms
            if (
                ready
                and stream_alive
                and account_ok
                and positions_ok
                and orders_ok
                and unresolved == 0
                and not fallback
                and fresh
            ):
                return True, "Demo user-data convergence ready"
            last_detail = (
                f"ready={ready} streamAlive={stream_alive} "
                f"account={account_ok} positions={positions_ok} "
                f"orders={orders_ok} unresolved={unresolved} "
                f"fallback={fallback} ageMs={age_ms}"
            )
        except Exception as exc:
            last_detail = str(exc)
        time.sleep(0.25)
    return False, last_detail


def run(args: argparse.Namespace) -> int:
    if os.name != "nt":
        print("ASTU_SIM_STACK_FATAL=Windows Named Pipe host requires Windows")
        return 2

    host = Path(args.host).resolve()
    status_dir = Path(args.status_dir).resolve()
    risk_file = Path(args.risk_file).resolve()
    realized_pnl_file = Path(args.realized_pnl_file).resolve()
    realized_pnl_state = Path(args.realized_pnl_state).resolve()
    position_dir = Path(args.position_dir).resolve()
    journal = Path(args.journal).resolve()
    execution_status_file = Path(args.execution_status_file).resolve()
    symbol_risk_status_file = Path(args.symbol_risk_status_file).resolve()
    symbol_risk_universe_file = Path(args.symbol_risk_universe_file).resolve()
    account_risk_view_json = Path(args.account_risk_view_json).resolve()
    account_risk_view_html = Path(args.account_risk_view_html).resolve()
    testnet_user_data_status = Path(args.testnet_user_data_status).resolve()
    testnet_order_authority_dir = Path(args.testnet_order_authority_dir).resolve()
    instrument_dir = Path(args.instrument_dir).resolve()
    order_snapshot_dir = (
        Path(args.order_snapshot_dir).resolve()
        if args.order_snapshot_dir
        else None
    )

    if (
        args.minimum_available_balance_reserve < 0
        or args.simulation_margin_reservation_rate < 0
        or args.max_effective_leverage < 0
        or args.max_margin_utilization < 0
        or args.max_margin_utilization > 1
        or args.max_net_directional_notional < 0
        or args.max_daily_risk_capital_loss < 0
        or args.max_weekly_risk_capital_loss < 0
        or args.max_daily_total_pnl_loss < 0
        or args.max_weekly_total_pnl_loss < 0
        or args.max_account_drawdown < 0
        or args.max_daily_realized_trade_loss < 0
        or args.max_weekly_realized_trade_loss < 0
        or args.account_risk_view_max_source_age_ms <= 0
        or args.account_risk_view_poll_seconds <= 0
        or args.testnet_user_data_max_liveness_ms <= 0
        or args.testnet_user_data_max_state_age_ms <= 0
        or args.testnet_user_data_keepalive_seconds <= 0
        or args.testnet_user_data_reconnect_seconds <= 0
        or args.testnet_convergence_wait_seconds <= 0
        or (
            (
                args.minimum_available_balance_reserve > 0
                or args.max_margin_utilization > 0
            )
            and args.simulation_margin_reservation_rate <= 0
        )
    ):
        print(
            "ASTU_SIM_STACK_FATAL=projected margin settings must be valid; "
            "free-balance or margin-utilization limits require a positive "
            "simulation margin reservation rate"
        )
        return 2

    demo_authority_active = args.testnet_user_data_mode == "live"
    demo_authority_only = args.demo_authority_only

    if demo_authority_only:
        if not demo_authority_active:
            print(
                "ASTU_SIM_STACK_FATAL=--demo-authority-only requires "
                "--testnet-user-data-mode live"
            )
            return 2
    if demo_authority_active:
        if args.risk_mode != "readonly":
            print(
                "ASTU_SIM_STACK_FATAL=Demo authority requires --risk-mode readonly"
            )
            return 2
        if args.instrument_mode != "public":
            print(
                "ASTU_SIM_STACK_FATAL=Demo authority requires --instrument-mode public"
            )
            return 2
        if args.testnet_rest_base_url.rstrip("/") != "https://demo-fapi.binance.com":
            print(
                "ASTU_SIM_STACK_FATAL=Demo authority requires "
                "https://demo-fapi.binance.com"
            )
            return 2
        if not args.testnet_user_data_ws_url_template.strip():
            print(
                "ASTU_SIM_STACK_FATAL=Demo authority requires explicit "
                "user-stream WebSocket template"
            )
            return 2
        if (
            not os.getenv("ASTU_BINANCE_TESTNET_API_KEY", "").strip()
            or not os.getenv("ASTU_BINANCE_TESTNET_API_SECRET", "").strip()
        ):
            print(
                "ASTU_SIM_STACK_FATAL=Demo authority credentials unavailable"
            )
            return 2
        if os.getenv("ASTU_BINANCE_TESTNET_USER_DATA_ENABLED", "").strip() != "1":
            print(
                "ASTU_SIM_STACK_FATAL=Demo authority requires "
                "ASTU_BINANCE_TESTNET_USER_DATA_ENABLED=1"
            )
            return 2

    if not args.realized_pnl_settlement_asset.strip():
        print(
            "ASTU_SIM_STACK_FATAL=realized PnL settlement asset must not be empty"
        )
        return 2

    if (
        (
            args.max_daily_realized_trade_loss > 0
            or args.max_weekly_realized_trade_loss > 0
        )
        and args.realized_pnl_mode == "disabled"
    ):
        print(
            "ASTU_SIM_STACK_FATAL=realized-trade loss limits require "
            "--realized-pnl-mode fixture or readonly"
        )
        return 2

    if not demo_authority_only:
        if not host.exists():
            print(f"ASTU_SIM_STACK_FATAL=missing execution host {host}")
            return 2
        if not status_dir.exists():
            print(
                f"ASTU_SIM_STACK_FATAL=missing WSRTD status directory {status_dir}"
            )
            return 3

    existing_state = load_pid_state()
    if existing_state and existing_state.get("schemaVersion") != PID_SCHEMA_VERSION:
        legacy_pids = [
            int(value)
            for value in existing_state.values()
            if isinstance(value, int) and value > 0
        ]
        if any(pid_alive(pid) for pid in legacy_pids):
            print(
                "ASTU_SIM_STACK_FATAL=legacy PID ownership cannot be proven; "
                "stop the existing stack before upgrading"
            )
            return 5
        with contextlib.suppress(OSError):
            PID_FILE.unlink()

    launch_nonce = uuid.uuid4().hex
    launcher_record = process_identity(os.getpid())
    if launcher_record is None:
        print("ASTU_SIM_STACK_FATAL=launcher process identity unavailable")
        return 5

    stop_requested = False
    children: dict[str, subprocess.Popen] = {}
    process_records: dict[str, dict[str, object]] = {
        "launcher": launcher_record,
    }
    logs: dict[str, object] = {}

    def on_signal(_sig, _frame):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, on_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, on_signal)

    child_credential_profiles: dict[str, str] = {}

    def start_child(
        name: str,
        command: list[str],
        credential_profile: str = CREDENTIAL_PROFILE_NONE,
    ) -> subprocess.Popen:
        log_path = LOGS / f"{name}.log"
        fh = open(log_path, "a", encoding="utf-8", buffering=1)
        logs[name] = fh
        proc = popen_child_process(
            command,
            stdout=fh,
            credential_profile=credential_profile,
        )
        try:
            persist_owned_child(process_records, name, proc.pid, launch_nonce)
        except RuntimeError:
            with contextlib.suppress(Exception):
                proc.terminate()
            raise
        child_credential_profiles[name] = credential_profile
        print(f"STARTED_{name.upper()}_PID={proc.pid}")
        return proc

    risk_command: list[str] | None = None
    if args.risk_mode == "fixture":
        risk_command = [
            sys.executable,
            "-u",
            str(GATEWAY),
            "--fixture",
            str(FIXTURE),
            "--output",
            str(risk_file),
            "--positions-output-dir",
            str(position_dir),
            "--symbols-file",
            str(REPO / "CleanRoomR2" / "stack" / "bootstrap_symbols.tls"),
            "--poll-seconds",
            str(args.risk_poll_seconds),
        ]
    elif args.risk_mode == "readonly":
        risk_command = [
            sys.executable,
            "-u",
            str(GATEWAY),
            "--output",
            str(risk_file),
            "--positions-output-dir",
            str(position_dir),
            "--symbols-file",
            str(REPO / "CleanRoomR2" / "stack" / "bootstrap_symbols.tls"),
            "--poll-seconds",
            str(args.risk_poll_seconds),
        ]
        if demo_authority_active:
            risk_command.extend([
                "--base-url",
                str(args.testnet_rest_base_url),
            ])

    realized_pnl_command: list[str] | None = None
    if args.realized_pnl_mode == "fixture":
        realized_pnl_command = [
            sys.executable,
            "-u",
            str(INCOME_RECONCILER),
            "--fixture",
            str(INCOME_FIXTURE),
            "--output",
            str(realized_pnl_file),
            "--state",
            str(realized_pnl_state),
            "--settlement-asset",
            str(args.realized_pnl_settlement_asset),
            "--poll-seconds",
            str(args.realized_pnl_poll_seconds),
        ]
    elif args.realized_pnl_mode == "readonly":
        realized_pnl_command = [
            sys.executable,
            "-u",
            str(INCOME_RECONCILER),
            "--output",
            str(realized_pnl_file),
            "--state",
            str(realized_pnl_state),
            "--settlement-asset",
            str(args.realized_pnl_settlement_asset),
            "--poll-seconds",
            str(args.realized_pnl_poll_seconds),
        ]

    testnet_user_data_command: list[str] | None = None
    if args.testnet_user_data_mode == "live":
        testnet_user_data_command = [
            sys.executable,
            "-u",
            str(TESTNET_USER_DATA),
            "--status",
            str(testnet_user_data_status),
            "--order-output-dir",
            str(testnet_order_authority_dir),
            "--journal",
            str(journal),
            "--account-snapshot",
            str(risk_file),
            "--position-dir",
            str(position_dir),
            "--max-liveness-ms",
            str(args.testnet_user_data_max_liveness_ms),
            "--rest-base-url",
            str(args.testnet_rest_base_url),
            "--ws-url-template",
            str(args.testnet_user_data_ws_url_template),
            "--keepalive-seconds",
            str(args.testnet_user_data_keepalive_seconds),
            "--reconnect-seconds",
            str(args.testnet_user_data_reconnect_seconds),
        ]

    instrument_command: list[str] | None = None
    if args.instrument_mode == "fixture":
        instrument_command = [
            sys.executable,
            "-u",
            str(INSTRUMENT_PUBLISHER),
            "--fixture",
            str(INSTRUMENT_FIXTURE),
            "--output-dir",
            str(instrument_dir),
            "--symbols-file",
            str(REPO / "CleanRoomR2" / "stack" / "bootstrap_symbols.tls"),
            "--poll-seconds",
            str(args.instrument_poll_seconds),
        ]
    elif args.instrument_mode == "public":
        instrument_command = [
            sys.executable,
            "-u",
            str(INSTRUMENT_PUBLISHER),
            "--output-dir",
            str(instrument_dir),
            "--poll-seconds",
            str(args.instrument_poll_seconds),
        ]
        if demo_authority_active:
            instrument_command.extend([
                "--rest-base",
                str(args.testnet_rest_base_url),
            ])

    ownership = claim_launcher_ownership(launch_nonce, launcher_record)
    if ownership == LAUNCH_OWNERSHIP_ALREADY_RUNNING:
        print("ASTU_SIM_STACK_STATUS=ALREADY_RUNNING")
        return 0
    if ownership != LAUNCH_OWNERSHIP_ACQUIRED:
        print("ASTU_LAUNCH_REFUSED_LIVE_OWNER_AMBIGUOUS")
        return 5

    try:
        save_pids(process_records, launch_nonce)
        if risk_command is not None:
            risk_profile = CREDENTIAL_PROFILE_NONE
            if args.risk_mode == "readonly":
                risk_profile = CREDENTIAL_PROFILE_BINANCE_READONLY
            if demo_authority_active and args.risk_mode == "readonly":
                risk_profile = CREDENTIAL_PROFILE_BINANCE_DEMO_SIGNED
            children["risk"] = start_child(
                "risk",
                risk_command,
                risk_profile,
            )
            time.sleep(0.5)
        if realized_pnl_command is not None:
            realized_pnl_profile = (
                CREDENTIAL_PROFILE_BINANCE_READONLY
                if args.realized_pnl_mode == "readonly"
                else CREDENTIAL_PROFILE_NONE
            )
            children["realized_pnl"] = start_child(
                "realized_pnl",
                realized_pnl_command,
                realized_pnl_profile,
            )
            time.sleep(0.5)
        if instrument_command is not None:
            children["instrument"] = start_child("instrument", instrument_command)
            time.sleep(0.5)
        if testnet_user_data_command is not None:
            children["testnet_user_data"] = start_child(
                "testnet_user_data",
                testnet_user_data_command,
                CREDENTIAL_PROFILE_TESTNET_USER_DATA,
            )
            time.sleep(0.5)

        if demo_authority_only:
            converged, detail = wait_for_demo_convergence(
                testnet_user_data_status,
                max_age_ms=args.testnet_user_data_max_state_age_ms,
                timeout_seconds=args.testnet_convergence_wait_seconds,
            )
            if not converged:
                print(
                    "ASTU_SIM_STACK_FATAL=Demo authority convergence timeout: "
                    f"{detail}"
                )
                return 4
            print("DEMO_AUTHORITY_CONVERGENCE=READY")

        host_command: list[str] | None = None
        if not demo_authority_only:
            host_command = [
            str(host),
            "--status-dir",
            str(status_dir),
            "--risk-status-file",
            str(risk_file),
            "--journal",
            str(journal),
            "--max-status-age-ms",
            str(args.max_status_age_ms),
            "--max-risk-status-age-ms",
            str(args.max_risk_status_age_ms),
            "--execution-status-file",
            str(execution_status_file),
            "--symbol-risk-status-file",
            str(symbol_risk_status_file),
            "--symbol-risk-universe-file",
            str(symbol_risk_universe_file),
            "--max-pending-entry-scale-in-reservations",
            str(args.max_pending_entry_scale_in_reservations),
            "--max-symbol-notional",
            str(args.max_symbol_notional),
            "--minimum-available-balance-reserve",
            str(args.minimum_available_balance_reserve),
            "--simulation-margin-reservation-rate",
            str(args.simulation_margin_reservation_rate),
            "--max-effective-leverage",
            str(args.max_effective_leverage),
            "--max-margin-utilization",
            str(args.max_margin_utilization),
            "--max-net-directional-notional",
            str(args.max_net_directional_notional),
            "--max-daily-risk-capital-loss",
            str(args.max_daily_risk_capital_loss),
            "--max-weekly-risk-capital-loss",
            str(args.max_weekly_risk_capital_loss),
            "--max-daily-total-pnl-loss",
            str(args.max_daily_total_pnl_loss),
            "--max-weekly-total-pnl-loss",
            str(args.max_weekly_total_pnl_loss),
            "--max-account-drawdown",
            str(args.max_account_drawdown),
            "--account-loss-baseline-file",
            str(args.account_loss_baseline_file),
            "--realized-pnl-status-file",
            str(realized_pnl_file),
            "--max-realized-pnl-status-age-ms",
            str(args.max_realized_pnl_status_age_ms),
            "--max-daily-realized-trade-loss",
            str(args.max_daily_realized_trade_loss),
            "--max-weekly-realized-trade-loss",
            str(args.max_weekly_realized_trade_loss),
            ]
        if host_command is not None and instrument_command is not None:
            host_command.extend([
                "--instrument-status-dir",
                str(instrument_dir),
                "--max-instrument-status-age-ms",
                str(args.max_instrument_status_age_ms),
            ])
        if host_command is not None and risk_command is not None:
            host_command.extend([
                "--position-status-dir",
                str(position_dir),
                "--max-position-status-age-ms",
                str(args.max_position_status_age_ms),
            ])
        if host_command is not None and order_snapshot_dir is not None:
            host_command.extend([
                "--order-snapshot-dir",
                str(order_snapshot_dir),
                "--max-order-snapshot-age-ms",
                str(args.max_order_snapshot_age_ms),
                "--order-reconcile-interval-ms",
                str(args.order_reconcile_interval_ms),
            ])
        if host_command is not None:
            children["execution"] = start_child("execution", host_command)

        account_risk_view_command: list[str] | None = None
        if (
            not demo_authority_only
            and args.account_risk_view_mode == "local"
        ):
            account_risk_view_command = [
                sys.executable,
                "-u",
                str(ACCOUNT_RISK_VIEW),
                "--execution-status-file",
                str(execution_status_file),
                "--output-json",
                str(account_risk_view_json),
                "--output-html",
                str(account_risk_view_html),
                "--symbol-risk-status-file",
                str(symbol_risk_status_file),
                "--max-source-age-ms",
                str(args.account_risk_view_max_source_age_ms),
                "--max-symbol-risk-age-ms",
                str(args.account_risk_view_max_source_age_ms),
                "--poll-seconds",
                str(args.account_risk_view_poll_seconds),
                "--watch",
            ]
            children["account_risk_view"] = start_child(
                "account_risk_view",
                account_risk_view_command,
            )

        save_pids(process_records, launch_nonce, startup_complete=True)

        print("ASTU_SIM_STACK_STATUS=RUNNING")
        print(f"RISK_MODE={args.risk_mode}")
        print(f"STATUS_DIR={status_dir}")
        print(f"RISK_STATUS_FILE={risk_file}")
        print(f"REALIZED_PNL_MODE={args.realized_pnl_mode}")
        print(f"REALIZED_PNL_STATUS_FILE={realized_pnl_file}")
        print(f"REALIZED_PNL_STATE={realized_pnl_state}")
        print(f"REALIZED_PNL_SETTLEMENT_ASSET={args.realized_pnl_settlement_asset}")
        if risk_command is not None:
            print(f"POSITION_STATUS_DIR={position_dir}")
        print(f"EXECUTION_JOURNAL={journal}")
        print(f"EXECUTION_STATUS_FILE={execution_status_file}")
        print(f"SYMBOL_RISK_STATUS_FILE={symbol_risk_status_file}")
        print(f"SYMBOL_RISK_UNIVERSE_FILE={symbol_risk_universe_file}")
        print(f"ACCOUNT_RISK_VIEW_MODE={args.account_risk_view_mode}")
        print(f"TESTNET_USER_DATA_MODE={args.testnet_user_data_mode}")
        print(
            "DEMO_AUTHORITY_ACTIVE="
            f"{str(demo_authority_active).lower()}"
        )
        print(f"TESTNET_USER_DATA_STATUS={testnet_user_data_status}")
        print(f"TESTNET_ORDER_AUTHORITY_DIR={testnet_order_authority_dir}")
        if args.account_risk_view_mode == "local":
            print(f"ACCOUNT_RISK_VIEW_JSON={account_risk_view_json}")
            print(f"ACCOUNT_RISK_VIEW_HTML={account_risk_view_html}")
        print(f"MAX_PENDING_ENTRY_SCALE_IN_RESERVATIONS={args.max_pending_entry_scale_in_reservations}")
        print(f"MAX_SYMBOL_NOTIONAL={args.max_symbol_notional}")
        print(f"MINIMUM_AVAILABLE_BALANCE_RESERVE={args.minimum_available_balance_reserve}")
        print(f"SIMULATION_MARGIN_RESERVATION_RATE={args.simulation_margin_reservation_rate}")
        print(f"MAX_EFFECTIVE_LEVERAGE={args.max_effective_leverage}")
        print(f"MAX_MARGIN_UTILIZATION={args.max_margin_utilization}")
        print(f"MAX_NET_DIRECTIONAL_NOTIONAL={args.max_net_directional_notional}")
        print(f"MAX_DAILY_RISK_CAPITAL_LOSS={args.max_daily_risk_capital_loss}")
        print(f"MAX_WEEKLY_RISK_CAPITAL_LOSS={args.max_weekly_risk_capital_loss}")
        print(f"MAX_DAILY_TOTAL_PNL_LOSS={args.max_daily_total_pnl_loss}")
        print(f"MAX_WEEKLY_TOTAL_PNL_LOSS={args.max_weekly_total_pnl_loss}")
        print(f"MAX_ACCOUNT_DRAWDOWN={args.max_account_drawdown}")
        print(f"ACCOUNT_LOSS_BASELINE_FILE={args.account_loss_baseline_file}")
        print(f"MAX_DAILY_REALIZED_TRADE_LOSS={args.max_daily_realized_trade_loss}")
        print(f"MAX_WEEKLY_REALIZED_TRADE_LOSS={args.max_weekly_realized_trade_loss}")
        print(f"INSTRUMENT_MODE={args.instrument_mode}")
        if instrument_command is not None:
            print(f"INSTRUMENT_STATUS_DIR={instrument_dir}")
        if demo_authority_only:
            print("EXECUTION_HOST=DISABLED_AUTHORITY_ONLY")
            print("ORDER_SNAPSHOT_PROVIDER=DISABLED")
        elif order_snapshot_dir is not None:
            print(f"ORDER_SNAPSHOT_DIR={order_snapshot_dir}")
            print(
                "ORDER_SNAPSHOT_PROVIDER="
                "FILE_BACKED_AUTHORITATIVE_SIMULATION_ORDER_STATE"
            )
        else:
            print("ORDER_SNAPSHOT_PROVIDER=DISABLED")
        print("ORDER_ROUTING_ENABLED=false")

        while not stop_requested:
            time.sleep(1.0)
            for name, proc in list(children.items()):
                if proc.poll() is None:
                    continue
                if stop_requested:
                    break
                print(
                    f"{name.upper()}_EXITED={proc.returncode} "
                    f"RESTARTING_IN={args.restart_delay_seconds}s"
                )
                time.sleep(args.restart_delay_seconds)
                try:
                    logs[name].close()
                except Exception:
                    pass
                if name == "risk":
                    command = risk_command
                elif name == "realized_pnl":
                    command = realized_pnl_command
                elif name == "instrument":
                    command = instrument_command
                elif name == "testnet_user_data":
                    command = testnet_user_data_command
                elif name == "account_risk_view":
                    command = account_risk_view_command
                else:
                    command = host_command
                if command is None:
                    continue
                children[name] = start_child(
                    name,
                    command,
                    child_credential_profiles.get(
                        name,
                        CREDENTIAL_PROFILE_NONE,
                    ),
                )
                save_pids(process_records, launch_nonce, startup_complete=True)
    finally:
        for proc in reversed(list(children.values())):
            if proc.poll() is None:
                with contextlib.suppress(Exception):
                    proc.terminate()
        deadline = time.time() + 5.0
        for proc in reversed(list(children.values())):
            while proc.poll() is None and time.time() < deadline:
                time.sleep(0.1)
            if proc.poll() is None:
                with contextlib.suppress(Exception):
                    proc.kill()
        for fh in logs.values():
            with contextlib.suppress(Exception):
                fh.close()
        state = load_pid_state()
        if state.get("launchNonce") == launch_nonce:
            with contextlib.suppress(OSError):
                PID_FILE.unlink()
        release_launch_lock(launch_nonce)
        print("ASTU_SIM_STACK_STATUS=STOPPED")

    return 0


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--stop", action="store_true")
    ap.add_argument("--host", default=str(DEFAULT_HOST))
    ap.add_argument("--status-dir", default=str(DEFAULT_STATUS_DIR))
    ap.add_argument("--risk-file", default=str(RISK_FILE))
    ap.add_argument(
        "--journal",
        default=str(RUNTIME / "execution_journal.v1.jsonl"),
    )
    ap.add_argument(
        "--execution-status-file",
        default=str(EXECUTION_STATUS_FILE),
    )
    ap.add_argument(
        "--symbol-risk-status-file",
        default=str(SYMBOL_RISK_STATUS_FILE),
    )
    ap.add_argument(
        "--symbol-risk-universe-file",
        default=str(SYMBOL_RISK_UNIVERSE_FILE),
    )
    ap.add_argument(
        "--account-risk-view-mode",
        choices=("disabled", "local"),
        default="local",
        help=(
            "Generate a read-only local Account Risk JSON/HTML projection from "
            "ExecutionStatus.v1; this never opens a trading endpoint."
        ),
    )
    ap.add_argument(
        "--account-risk-view-json",
        default=str(ACCOUNT_RISK_VIEW_JSON),
    )
    ap.add_argument(
        "--account-risk-view-html",
        default=str(ACCOUNT_RISK_VIEW_HTML),
    )
    ap.add_argument(
        "--account-risk-view-max-source-age-ms",
        type=int,
        default=5000,
    )
    ap.add_argument(
        "--account-risk-view-poll-seconds",
        type=float,
        default=1.0,
    )
    ap.add_argument(
        "--demo-authority-only",
        action="store_true",
        help=(
            "Run only the Binance USD-M Demo account/instrument/user-data "
            "authority sidecars. The simulation execution host is not started."
        ),
    )
    ap.add_argument(
        "--testnet-user-data-mode",
        choices=("disabled", "live"),
        default="disabled",
        help=(
            "Supervise the read-only Binance USD-M Demo user-data authority sidecar."
        ),
    )
    ap.add_argument(
        "--testnet-user-data-status",
        default=str(TESTNET_USER_DATA_STATUS),
    )
    ap.add_argument(
        "--testnet-order-authority-dir",
        default=str(TESTNET_ORDER_AUTHORITY_DIR),
    )
    ap.add_argument(
        "--testnet-user-data-max-liveness-ms",
        type=int,
        default=15000,
    )
    ap.add_argument(
        "--testnet-user-data-max-state-age-ms",
        type=int,
        default=7000,
    )
    ap.add_argument(
        "--testnet-convergence-wait-seconds",
        type=float,
        default=30.0,
        help=(
            "Maximum startup wait for a fresh fully-converged Demo "
            "user-data authority-only process."
        ),
    )
    ap.add_argument(
        "--testnet-user-data-keepalive-seconds",
        type=float,
        default=1800.0,
    )
    ap.add_argument(
        "--testnet-user-data-reconnect-seconds",
        type=float,
        default=2.0,
    )
    ap.add_argument(
        "--testnet-rest-base-url",
        default="https://demo-fapi.binance.com",
    )
    ap.add_argument(
        "--testnet-user-data-ws-url-template",
        default=os.getenv(
            "ASTU_BINANCE_TESTNET_USER_STREAM_URL_TEMPLATE",
            "",
        ),
    )
    ap.add_argument(
        "--risk-mode",
        choices=("disabled", "fixture", "readonly"),
        default="disabled",
    )
    ap.add_argument("--risk-poll-seconds", type=float, default=5.0)
    ap.add_argument(
        "--realized-pnl-mode",
        choices=("disabled", "fixture", "readonly"),
        default="disabled",
    )
    ap.add_argument(
        "--realized-pnl-file",
        default=str(REALIZED_PNL_FILE),
    )
    ap.add_argument(
        "--realized-pnl-state",
        default=str(REALIZED_PNL_STATE),
    )
    ap.add_argument(
        "--realized-pnl-poll-seconds",
        type=float,
        default=30.0,
    )
    ap.add_argument(
        "--realized-pnl-settlement-asset",
        default="USDT",
    )
    ap.add_argument(
        "--max-realized-pnl-status-age-ms",
        type=int,
        default=90000,
    )
    ap.add_argument("--position-dir", default=str(POSITION_DIR))
    ap.add_argument("--max-position-status-age-ms", type=int, default=7000)
    ap.add_argument(
        "--instrument-mode",
        choices=("disabled", "fixture", "public"),
        default="disabled",
    )
    ap.add_argument("--instrument-dir", default=str(INSTRUMENT_DIR))
    ap.add_argument("--instrument-poll-seconds", type=float, default=3600.0)
    ap.add_argument("--max-instrument-status-age-ms", type=int, default=86400000)
    ap.add_argument(
        "--order-snapshot-dir",
        default="",
        help=(
            "Optional directory containing AuthoritativeSimulationOrderSnapshot.v1 "
            "files used only for startup reconciliation."
        ),
    )
    ap.add_argument("--max-order-snapshot-age-ms", type=int, default=7000)
    ap.add_argument("--order-reconcile-interval-ms", type=int, default=2000)
    ap.add_argument("--max-status-age-ms", type=int, default=5000)
    ap.add_argument("--max-risk-status-age-ms", type=int, default=7000)
    ap.add_argument(
        "--max-pending-entry-scale-in-reservations",
        type=int,
        default=0,
        help="0 disables the simulation projected pending-reservation count limit.",
    )
    ap.add_argument(
        "--max-symbol-notional",
        type=float,
        default=0.0,
        help="0 disables the simulation per-symbol projected-notional limit.",
    )
    ap.add_argument(
        "--minimum-available-balance-reserve",
        type=float,
        default=0.0,
        help="Minimum projected available balance to keep free for safety.",
    )
    ap.add_argument(
        "--simulation-margin-reservation-rate",
        type=float,
        default=0.0,
        help=(
            "Execution-local simulation margin reserved per unit of accepted "
            "notional; 0 disables projected margin reservation."
        ),
    )
    ap.add_argument(
        "--max-effective-leverage",
        type=float,
        default=0.0,
        help="0 disables projected effective-leverage enforcement.",
    )
    ap.add_argument(
        "--max-margin-utilization",
        type=float,
        default=0.0,
        help="0 disables projected margin-utilization enforcement; otherwise use 0..1.",
    )
    ap.add_argument(
        "--max-net-directional-notional",
        type=float,
        default=0.0,
        help="0 disables the symmetric absolute signed-net-notional limit.",
    )
    ap.add_argument(
        "--max-daily-risk-capital-loss",
        type=float,
        default=0.0,
        help="0 disables the persisted UTC-day Risk Capital loss budget.",
    )
    ap.add_argument(
        "--max-weekly-risk-capital-loss",
        type=float,
        default=0.0,
        help="0 disables the persisted UTC-week Risk Capital loss budget.",
    )
    ap.add_argument(
        "--max-daily-total-pnl-loss",
        type=float,
        default=0.0,
        help="0 disables the UTC-day margin-balance total-PnL loss budget.",
    )
    ap.add_argument(
        "--max-weekly-total-pnl-loss",
        type=float,
        default=0.0,
        help="0 disables the UTC-week margin-balance total-PnL loss budget.",
    )
    ap.add_argument(
        "--max-account-drawdown",
        type=float,
        default=0.0,
        help="0 disables margin-balance high-water drawdown enforcement.",
    )
    ap.add_argument(
        "--account-loss-baseline-file",
        default=str(RUNTIME / "account_loss_baseline.v1.json"),
    )
    ap.add_argument(
        "--max-daily-realized-trade-loss",
        type=float,
        default=0.0,
        help="0 disables exact UTC-day realized-trade loss enforcement.",
    )
    ap.add_argument(
        "--max-weekly-realized-trade-loss",
        type=float,
        default=0.0,
        help="0 disables exact UTC-week realized-trade loss enforcement.",
    )
    ap.add_argument("--restart-delay-seconds", type=float, default=2.0)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    if args.status:
        return status()
    if args.stop:
        return stop()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
