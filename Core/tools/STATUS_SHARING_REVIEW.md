# ExecutionStatus Windows sharing fix — local review

Baseline: `e067cbd0205468a537fc8a0deffe0a5ef47b4f3f`, branch
`chatgpt/core-autotrader-scaffold-sim-only`. Worktree was clean before edits.
No commit or remote write is part of this change.

## Diagnosis

**Exact CI operation: READ/OPEN.** Push run 35700912218, Windows job
106658444820, step 33 (`Windows periodic runtime order reconciliation smoke`)
failed in `json.load(open(...))` at 2026-09-22T07:45:38Z. It did not reach the
MISMATCH_TO_UNKNOWN assertions. The emitted RC=8 labels the failed checkpoint,
not a demonstrated reconciliation-state defect. The earlier report describing
that traceback as a write failure was incorrect.

**Classification: HIGH_CONFIDENCE for the historical race; PROVEN sharing
mechanism on this Windows host.** Controlled native-handle tests show that a
handle with DELETE access (needed for replacement) conflicts with the ordinary
Python/CRT reader's sharing mode. The reader raises PermissionError. Conversely,
holding a normal reader open makes replacement fail and leaves the previous
destination intact. A concurrent publication/read loop also reproduced access
denial locally. No historical handle trace identifies the exact CI holder.

The PR run 35700916685 passed while the push run failed at the same head SHA.
The publisher and smoke reader overlap without synchronization, so different
runner scheduling can make one run hit the conflicting open window and another
miss it. This is consistent with the deterministic sharing demonstration and
CI traceback; it does not prove an exact runner/antivirus timing explanation.

### Producer and consumer audit

- `Core/execution/include/astu/execution/execution_status.hpp` is the
  ExecutionStatus publisher. Its per-object `publish_mu_` serializes threads
  sharing one object, but does not protect separate processes/objects using the
  original fixed `.tmp` path. Separate-instance staging collision is a real
  design risk, not a demonstrated duplicate producer in the failed CI run.
- `Core/execution/src/execution_pipe_host.cpp` publishes at startup, heartbeat,
  reconciliation and state updates. The failed smoke sets reconciliation to
  250 ms. Persistent publication failure remains an exception; existing host
  handling logs/marks degraded as appropriate. The heartbeat logs
  `execution-status publish failed`.
- The four edited reconciliation/startup smoke scripts open the actively
  published ExecutionStatus directly. Their original assertions are preserved.
- Other direct status readers remain in `run_available_balance_reservation_smoke.cmd`,
  `run_execution_restart_smoke.cmd`, `run_exposure_reservation_smoke.cmd`,
  `run_loss_drawdown_risk_smoke.cmd`, `run_net_directional_risk_smoke.cmd`,
  `run_order_fsm_restart_smoke.cmd`, and `run_realized_pnl_risk_smoke.cmd`.
  These are outside this focused reconciliation fix and remain candidates for
  separately migrating to the helper if needed.
- `Core/tools/wait_json_status.py` already polls, but retries parse and
  expectation failures too; using it here would change checkpoint semantics.
  It is used by the leverage/margin smoke. It is intentionally unchanged.
- `Core/operator/account_risk_view.py::publish_once` reads ExecutionStatus,
  catches failures, and emits a fail-closed error view; its next refresh can
  recover. `Core/stack/autotrader_sim_launcher.py::status` also reads it and can
  report UNKNOWN on failure. Neither production consumer is rewritten here.
- `Core/tests/execution_status_tests.cpp` reads after synchronous publication;
  account-risk tests use fixtures. `verify_account_risk_view_smoke.py` reads
  derived view/symbol files, not this publisher's destination. C++ live market
  providers read derived WSRTD symbol status, not ExecutionStatus.

This is a general Windows file-sharing interaction, not intrinsically a CI-only
problem. The harness exposed it by treating any single failed open as a failed
semantic assertion checkpoint.

## Changes

- `Core/tools/status_json_reader.py`: read/close a complete snapshot, then parse
  JSON. Only Windows access/sharing PermissionErrors are retried: five attempts,
  10/20/40/80 ms delays (150 ms scheduled backoff total). Normal reads do not
  sleep. Missing files, malformed JSON, unrelated errors and caller assertions
  propagate. Persistent denial names the path and attempts and retains the cause.
- Four smoke scripts use this helper through script-local PYTHONPATH. No
  checkpoint delays, assertions, journal checks, or reconciliation logic changed.
- ExecutionStatus publisher: Windows same-directory uniquely reserved staging
  via GetTempFileName; bounded MoveFileEx retries for error 5/32/33 only; preserve
  GetLastError before cleanup; remove owned staging on failure and rethrow.
  Destination is never removed first. Non-Windows rename behavior is unchanged.
- `Core/tests/test_status_json_reader.py`: 10 tests including injected transient
  and persistent reader denial, no-delay normal read, malformed/missing/error
  propagation, wrong semantic assertion, native Windows sharing demonstrations,
  and 1,000 actual C++ publications with concurrent Python JSON reads.
- `Core/tests/status_sharing_tests.cpp`: production publisher tests for held
  readers, bounded exhaustion, old-file preservation, transient release,
  overlapping publisher instances, staging cleanup; also drives the Python
  concurrent-read test.
- `Core/CMakeLists.txt`: registers the publisher test in CTest.
- `.github/workflows/core-sim.yml`: runs the Python sharing regressions after
  build/CTest on each matrix platform. This is a local workflow-file edit only.

Producer hardening is justified by the independently reproduced reverse
sharing conflict, not just by the CI reader failure. Routing, execution
decisions, schema and reconciliation assertions are unchanged.

## Validation and limitations

The no-delay maximum-throughput experimental loop exhausted the deliberately
short retry budget. The retained regression uses 1 ms requested publisher and
reader pacing, with a 45-second test deadline to accommodate Windows timer
granularity. It performs 1,000 real publications (about 18 seconds here), much
faster than the smoke's 250 ms reconciliation interval. Bounded retries cannot
guarantee success under indefinitely held locks or continuous contention.

Assertions compared against HEAD: 26 runtime-reconciliation, 36 startup,
15 reconciliation-FSM, 14 reconciliation-pipe expressions unchanged.

Local results:

- CMake configure and Release build: PASS.
- CTest: 16/16 PASS, including the new production publisher tests.
- Python reader regression suite: 10/10 PASS in 17.760 seconds.
- Existing Core launcher suite: 32/32 PASS in 2.458 seconds.
- Simulation-only boundary, account-risk view, account-risk/execution/symbol
  schema checks, and Testnet user-data authority scripts: PASS.
- `python -m compileall -q Core`: PASS.
- `git diff --check`: PASS; new source files checked separately too.
- Exact runtime-order-reconciliation smoke: **20 consecutive PASS, 0 FAIL**;
  all MISMATCH_TO_UNKNOWN checkpoints passed, no PermissionError or smoke
  failure in the saved output/error logs. Minimum requested stress count used.
- Startup-order-snapshot, reconciliation-FSM, reconciliation-pipe smokes: PASS.
- Reconciliation-restart smoke: PASS in the isolated fixture copy.

Evidence directory (relative to repository root):
`build/core/ci_sharing_cbb947a460064bbe9913dde2a48c689f`.
Files `1.out`/`1.err` through `20.out`/`20.err` are the exact smoke iterations;
21 is startup snapshot, 22 is reconciliation FSM, 23 is reconciliation pipe.
The isolated restart log is
`build/core/restart_isolated_ad338465a37440de80b612e24eeface2/evidence.log`.
Validation-only orchestration scripts are `build/core/ci_sharing_stress.ps1`
and `build/core/run_isolated_restart.py`; these ignored build artifacts are
not proposed source changes.

The exact smoke
uses disposable `build/core` output. The restart smoke needs an isolated copy:
the original calls `identity_bridge.py --once` against the live directory.
The validation copy retains the script, bridge and assertions while redirecting
all files through its copied directory layout. It reads copied market/recovery
snapshots and never writes to the production-like WSRTD runtime.

The existing smoke scripts use image-wide cleanup. Local runs check that no
execution host already exists before launching each smoke and run serially.
They do not target Broker or WSRTD Python processes.

Live WSRTD PID-file baseline SHA256:
`6CD4C5879A4C145188BA71730839EAD16A63231B19A7714A148719D2A8EAA86F`.
Final hash is identical. Launcher 30156, relay 31344, server 27872, identity
29148 and Broker 4424 remain alive. Maintenance pause remains absent. No
execution test host remains. Local HEAD remains the baseline; working-tree
changes consist solely of the source/test/workflow/report files listed below.

## Files proposed for a future commit

All paths relative to `D:\wsrtd_binance_usdm_stack\autotrader`:

1. `.github/workflows/core-sim.yml`
2. `Core/CMakeLists.txt`
3. `Core/execution/include/astu/execution/execution_status.hpp`
4. `Core/tools/run_runtime_order_reconciliation_smoke.cmd`
5. `Core/tools/run_startup_order_snapshot_smoke.cmd`
6. `Core/tools/run_reconciliation_fsm_smoke.cmd`
7. `Core/tools/run_reconciliation_pipe_smoke.cmd`
8. `Core/tools/status_json_reader.py`
9. `Core/tests/test_status_json_reader.py`
10. `Core/tests/status_sharing_tests.cpp`
11. `Core/tools/STATUS_SHARING_REVIEW.md`

LIVE_DATA_10101_TOUCHED=NO

SOURCE_COMMITTED=NO

REMOTE_GITHUB_CHANGED=NO

## CI plan after review

After explicit approval: create one dedicated commit, push normally to the
existing branch, and require both newly triggered push and PR Windows CI jobs
to pass. Rerunning the old failed workflow is not validation of this change.
Network/crash/reboot acceptance remains deferred.
