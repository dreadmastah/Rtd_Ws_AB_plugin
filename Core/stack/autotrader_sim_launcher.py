#!/usr/bin/env python3
"""Supervisor for the auto-trader runtime.

Default behavior is simulation-only. Binance USD-M Demo Trading routing can be
activated only with explicit dual arming plus live read-only account,
instrument, user-data, and authoritative order-state evidence. Mainnet routing
is not supported by this launcher.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
RUNTIME = ROOT / "runtime"
LOGS = RUNTIME / "logs"
PID_FILE = RUNTIME / "autotrader_sim_pids.json"
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

RUNTIME.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        cp = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        out = (cp.stdout or "").strip()
        return bool(out) and not out.upper().startswith("INFO:")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def load_pids() -> dict[str, int]:
    if not PID_FILE.exists():
        return {}
    try:
        obj = json.loads(PID_FILE.read_text(encoding="utf-8"))
        return {str(k): int(v) for k, v in obj.items() if int(v) > 0}
    except Exception:
        return {}


def save_pids(children: dict[str, subprocess.Popen]) -> None:
    obj = {
        "launcher": os.getpid(),
        **{name: proc.pid for name, proc in children.items() if proc is not None},
    }
    tmp = PID_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, PID_FILE)


def status() -> int:
    pids = load_pids()
    if not pids:
        print("ASTU_SIM_STACK_STATUS=STOPPED")
        return 1
    all_alive = True
    for name, pid in pids.items():
        alive = pid_alive(pid)
        print(f"{name.upper()}_PID={pid} ALIVE={alive}")
        all_alive = all_alive and alive
    print(f"ASTU_SIM_STACK_STATUS={'RUNNING' if all_alive else 'DEGRADED'}")
    print("ORDER_ROUTING_ENABLED=false")
    return 0 if all_alive else 1


def stop() -> int:
    pids = load_pids()
    launcher = int(pids.get("launcher", 0) or 0)
    if launcher and launcher != os.getpid() and pid_alive(launcher):
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
    try:
        PID_FILE.unlink()
    except OSError:
        pass
    print("ASTU_SIM_STACK_STOP_REQUESTED=YES")
    return 0


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

    if args.arm_testnet_order_routing and not args.enable_testnet_order_routing:
        print(
            "ASTU_SIM_STACK_FATAL=--arm-testnet-order-routing requires "
            "--enable-testnet-order-routing"
        )
        return 2

    routing_active = (
        args.enable_testnet_order_routing
        and args.arm_testnet_order_routing
    )
    if routing_active:
        if args.risk_mode != "readonly":
            print(
                "ASTU_SIM_STACK_FATAL=Demo routing requires --risk-mode readonly"
            )
            return 2
        if args.instrument_mode != "public":
            print(
                "ASTU_SIM_STACK_FATAL=Demo routing requires --instrument-mode public"
            )
            return 2
        if args.testnet_user_data_mode != "live":
            print(
                "ASTU_SIM_STACK_FATAL=Demo routing requires "
                "--testnet-user-data-mode live"
            )
            return 2
        if args.testnet_rest_base_url.rstrip("/") != "https://demo-fapi.binance.com":
            print(
                "ASTU_SIM_STACK_FATAL=Demo routing requires "
                "https://demo-fapi.binance.com"
            )
            return 2
        if not args.testnet_user_data_ws_url_template.strip():
            print(
                "ASTU_SIM_STACK_FATAL=Demo routing requires explicit "
                "user-stream WebSocket template"
            )
            return 2
        if (
            not os.getenv("ASTU_BINANCE_TESTNET_API_KEY", "").strip()
            or not os.getenv("ASTU_BINANCE_TESTNET_API_SECRET", "").strip()
        ):
            print(
                "ASTU_SIM_STACK_FATAL=Demo routing credentials unavailable"
            )
            return 2
        if os.getenv("ASTU_BINANCE_TESTNET_USER_DATA_ENABLED", "").strip() != "1":
            print(
                "ASTU_SIM_STACK_FATAL=Demo routing requires "
                "ASTU_BINANCE_TESTNET_USER_DATA_ENABLED=1"
            )
            return 2
        # In active Demo mode, authoritative order snapshots are produced by
        # the live user-data authority sidecar.
        order_snapshot_dir = testnet_order_authority_dir

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

    if not host.exists():
        print(f"ASTU_SIM_STACK_FATAL=missing execution host {host}")
        return 2
    if not status_dir.exists():
        print(f"ASTU_SIM_STACK_FATAL=missing WSRTD status directory {status_dir}")
        return 3

    old = load_pids()
    if old and int(old.get("launcher", 0) or 0) != os.getpid():
        if all(pid_alive(pid) for pid in old.values()):
            print("ASTU_SIM_STACK_STATUS=ALREADY_RUNNING")
            return 0
        try:
            PID_FILE.unlink()
        except OSError:
            pass

    stop_requested = False
    children: dict[str, subprocess.Popen] = {}
    logs: dict[str, object] = {}

    def on_signal(_sig, _frame):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, on_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, on_signal)

    child_env_overrides: dict[str, dict[str, str]] = {}

    def start_child(
        name: str,
        command: list[str],
        env_overrides: dict[str, str] | None = None,
    ) -> subprocess.Popen:
        log_path = LOGS / f"{name}.log"
        fh = open(log_path, "a", encoding="utf-8", buffering=1)
        logs[name] = fh
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        proc = subprocess.Popen(
            command,
            cwd=REPO,
            stdout=fh,
            stderr=subprocess.STDOUT,
            env={
                **os.environ,
                "PYTHONUNBUFFERED": "1",
                **(env_overrides or {}),
            },
            creationflags=flags,
        )
        if env_overrides:
            child_env_overrides[name] = dict(env_overrides)
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
        if routing_active:
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
        if args.risk_mode != "readonly":
            print(
                "ASTU_SIM_STACK_FATAL=live Testnet user-data authority "
                "requires --risk-mode readonly for REST account/position convergence"
            )
            return 2
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
        if routing_active:
            instrument_command.extend([
                "--rest-base",
                str(args.testnet_rest_base_url),
            ])

    try:
        if risk_command is not None:
            risk_env = None
            if routing_active and args.risk_mode == "readonly":
                risk_env = {
                    "ASTU_BINANCE_PRIVATE_READONLY_ENABLED": "1",
                    "BINANCE_API_KEY": os.environ[
                        "ASTU_BINANCE_TESTNET_API_KEY"
                    ],
                    "BINANCE_API_SECRET": os.environ[
                        "ASTU_BINANCE_TESTNET_API_SECRET"
                    ],
                }
            children["risk"] = start_child(
                "risk",
                risk_command,
                risk_env,
            )
            time.sleep(0.5)
        if realized_pnl_command is not None:
            children["realized_pnl"] = start_child(
                "realized_pnl",
                realized_pnl_command,
            )
            time.sleep(0.5)
        if instrument_command is not None:
            children["instrument"] = start_child("instrument", instrument_command)
            time.sleep(0.5)
        if testnet_user_data_command is not None:
            children["testnet_user_data"] = start_child(
                "testnet_user_data",
                testnet_user_data_command,
            )
            time.sleep(0.5)

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
            "--testnet-convergence-status-file",
            str(testnet_user_data_status),
            "--max-testnet-convergence-age-ms",
            str(args.testnet_user_data_max_state_age_ms),
            "--testnet-rest-host",
            "demo-fapi.binance.com",
        ]
        if args.enable_testnet_order_routing:
            host_command.append("--enable-testnet-order-routing")
        if args.arm_testnet_order_routing:
            host_command.append("--arm-testnet-order-routing")
        if instrument_command is not None:
            host_command.extend([
                "--instrument-status-dir",
                str(instrument_dir),
                "--max-instrument-status-age-ms",
                str(args.max_instrument_status_age_ms),
            ])
        if risk_command is not None:
            host_command.extend([
                "--position-status-dir",
                str(position_dir),
                "--max-position-status-age-ms",
                str(args.max_position_status_age_ms),
            ])
        if order_snapshot_dir is not None:
            host_command.extend([
                "--order-snapshot-dir",
                str(order_snapshot_dir),
                "--max-order-snapshot-age-ms",
                str(args.max_order_snapshot_age_ms),
                "--order-reconcile-interval-ms",
                str(args.order_reconcile_interval_ms),
            ])
        children["execution"] = start_child("execution", host_command)

        account_risk_view_command: list[str] | None = None
        if args.account_risk_view_mode == "local":
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

        save_pids(children)

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
        if order_snapshot_dir is not None:
            print(f"ORDER_SNAPSHOT_DIR={order_snapshot_dir}")
            print("ORDER_SNAPSHOT_PROVIDER=FILE_BACKED_AUTHORITATIVE_SIMULATION_ORDER_STATE")
        else:
            print("ORDER_SNAPSHOT_PROVIDER=DISABLED")
        print(
            "ORDER_ROUTING_ENABLED="
            f"{str(routing_active).lower()}"
        )

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
                    child_env_overrides.get(name),
                )
                save_pids(children)
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
        try:
            PID_FILE.unlink()
        except OSError:
            pass
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
        "--enable-testnet-order-routing",
        action="store_true",
        help=(
            "Stage Binance USD-M Demo Trading routing. No routing occurs "
            "unless --arm-testnet-order-routing is also supplied."
        ),
    )
    ap.add_argument(
        "--arm-testnet-order-routing",
        action="store_true",
        help=(
            "Second explicit activation gate for Demo Trading routing. "
            "Requires --enable-testnet-order-routing and live convergence."
        ),
    )
    ap.add_argument(
        "--testnet-user-data-mode",
        choices=("disabled", "live"),
        default="disabled",
        help=(
            "Supervise the Binance USD-M Demo Trading user-data authority sidecar. "
            "This alone does not enable order routing."
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
