
# Local status publication and stop-provenance review

Date: 2026-09-22 (Asia/Taipei). Local-only; not a deployed-runtime acceptance.

## Baseline and scope

- Repository: `D:\wsrtd_binance_usdm_stack\autotrader`.
- Branch: `chatgpt/core-autotrader-scaffold-sim-only`.
- Exact starting HEAD: `a5cf7511353d615a29a67f532cc8fd08cbb8314a`.
- `git status --porcelain=v1` was empty before edits. HEAD/branch remain unchanged.
- No commit, fetch, pull, merge, rebase, push, branch switch, or GitHub operation.
- No DLL, Core, execution, schema, retention, market-liveness, registry, autostart,
  power-plan or configuration edits. No full-stack stop, sleep, reboot or logoff.
- Supplied ZIP inventory: `wsrtd_market_status_winerror5.patch` (6606 bytes),
  `apply_local_fix.cmd` (1854 bytes). Neither was applied/executed.

## 1. WinError 5: proven mechanism; historical holder unresolved

The original publisher used one shared `.tmp`, followed by one `os.replace`.
Before changing that code, an isolated test held the destination open with
Python `Path.open('r')`, the same opening mechanism as the identity bridge's
`Path.read_text`. The original publication raised Windows `PermissionError`
and preserved the old file. Baseline reproduction: **1 test passed in 0.115s**.
This proves a normal Python reader can block atomic replacement on this host;
it does not prove which process held the real file at a past failure.

High-confidence diagnosis: transient Windows file-sharing contention, with
the once-per-second identity reader a concrete in-repository candidate.
Exact historical lock holder: **UNRESOLVED**. Antivirus/indexer involvement and
duplicate external publishers are neither proved nor ruled out. No handle trace
was captured at failure time. Handle/ProcMon were not found on PATH or in the
searched Downloads/repository locations; no software was installed.

Evidence: `CleanRoomR2/stack/logs/server_supervisor.log` records replacement
failure at 2026-09-22 14:43:53.022 (around lines 8802-8809), then accepted live
klines at 14:43:58.784; another failure at 14:45:04.022. Periodic GAP audit
completed at 14:43:44.432. This is not evidence of dead market streams.
Absence of the old fixed temporary file later is not proof that replacement
never failed: a later successful write reuses and consumes that filename.

### Reader/writer map (whole-repository search, including .github)

| Path / function | Access to market status | Scheduling / context |
| --- | --- | --- |
| `CleanRoomR2/stack/binance_usdm_server.py::save_autotrader_market_status` | Sole production writer found; original fixed temp + replace | One status task; final save only after task cancellation/gather |
| `App.autotrader_status_writer_loop`, `App.run` finalizer | Calls above writer | Every configured second; shutdown final save |
| `CleanRoomR2/stack/identity_bridge.py::load_market_status` | Reads destination using `Path.read_text`; no temp access | `write_once` called every second or explicit `--once` |
| `.github/workflows/core-sim.yml` identity fixture | Writes destination directly with fixture JSON | CI job in its workspace, not installed watchdog; must not replay against live runtime |
| `Core/wsrtd/include/astu/wsrtd/live_status_provider.hpp::read_all` | Reads derived `autotrader_status/<symbol>.json`, NOT market_status | Engine/runtime consumers |
| Core demo/execution/account/risk components | No direct market_status reader/writer found | Consume derived files through status providers/CLI-selected dirs |
| Core launchers/smoke tests | Pass derived status directory; no direct market_status temp writes found | Explicit tests/demo |
| PowerShell history / operator inspection | `Get-Content runtime/market_status.v1.json`, temp/attribute checks; attempted `handle.exe` | Manual diagnostics; history lacks reliable per-command timestamps |
| New publication tests | Read/write isolated TemporaryDirectory only | Explicit test execution |

Within one original App process the synchronous writer and finalizer cannot
race each other. The fixed staging name is nevertheless unsafe if a second
server is manually started or fixture code is run in the live directory.
Unique staging removes that collision, not logical ownership of multiple
independent server instances. No production duplicate was demonstrated.

### Process snapshot / limits

CIM at about 14:48 returned the following Python/Broker tree. For ALL rows,
`ExecutablePath` and full `CommandLine` were **null/unavailable** from CIM;
do not mistake a command-line-filtered empty result for zero servers.

| PID | Parent PID | Image | Attribution from PID file/logs (not CIM command line) |
| --- | --- | --- | --- |
| 26260 | 25204 | python.exe | launcher wrapper |
| 19840 | 26260 | python.exe | supervisor |
| 27708 | 19840 | python.exe | relay venv wrapper |
| 6116 | 27708 | python.exe | relay interpreter, listener 127.0.0.1:10101 |
| 25972 | 19840 | python.exe | server venv wrapper |
| 27716 | 25972 | python.exe | server interpreter |
| 23268 | 19840 | python.exe | identity venv wrapper |
| 26720 | 23268 | python.exe | identity interpreter |
| 27640 | 19840 | Broker.exe | AmiBroker before authorized forced-restart test |

`runtime/stack_pids.json` records `Data:10101`, launcher 19840, relay 27708,
server 25972, identity 23268. Log-recorded service executable is
`D:\wsrtd_binance_usdm_stack\autotrader\CleanRoomR2\stack\.venv\Scripts\python.exe`;
the launcher builds `python.exe -u <absolute service script>`. These are expected
commands, NOT independently recovered full CIM command lines. The observed
tree fits **one managed server**, but exact global server count is not proven
under the available process metadata. No `astu*` process appeared in the snapshot.

### Minimal publication change

`save_autotrader_market_status` is now async; both production callers await it.
Snapshot/serialization still happens on the event loop. A unique, closed,
same-directory temporary file is atomically replaced. PermissionError alone
gets four nonblocking sleeps (25, 50, 100, 200 ms), at most five attempts.
Persistent failures log attempt count and propagate to the existing exception
logger. Other I/O failures propagate immediately. Success/failure/cancellation
cleans staging; cleanup failure is logged. Old destination is never deleted.
No detached background writer can outlive cancellation and overwrite final state.
Small local file writes remain synchronous; there is no unbounded retry or sleep.

## 2. Historical stop: PROVEN Codex acceptance invocation

The prior Codex acceptance script explicitly issued:

```powershell
& 'C:\Users\dadhie\AppData\Local\Programs\Python\Python312\python.exe' CleanRoomR2/stack/stack_launcher.py --stop --dbname WSRTD --relay-port 10101
```

Durable execution evidence:
`C:\Users\dadhie\.codex\sessions\2026\09\21\rollout-2026-09-21T12-07-11-01a0c225-7a83-7b31-99b9-c03aaeca210d.jsonl`.
Line 3626 is a completed CommandExecution event at **2026-09-22T01:29:32.421Z**
(09:29:32 Taipei), exit 0, with `WSRTD_STACK_STOP_REQUESTED=YES` and
`FINAL_WSRtd_STOP=PASS`. The same script explicitly checked that PID state and
relay listeners were gone, preserving AmiBroker. This was Codex's acceptance
cleanup, not an automatic watchdog stop.

Earlier successful stop/restart acceptance commands are also recorded at lines
3601 (01:27:50.443Z) and 3617 (01:28:45.369Z). Line 3594 is a failed dependency
check that exited BEFORE its stop command; it must not be counted as a stop.

`logs/autostart_supervisor.log` matches the final tracked cohort: launcher
23936, relay 24784, server 25808, identity 24780; request token
`5b7b5f8213bd306b85460d7f`; STOPPING lines, STOPPED, lock release. The next
recorded cohort uses `Data` and launcher 19840. Supervisor lines themselves
lack timestamps; do not assign the file's last-write time to every old event.

The original `stop_from_pidfile` necessarily wrote `manual-stop` before the
request. `ensure_running` then correctly refused restart while that marker
existed. Thus this specific historical invoker is PROVEN. Attribution of
every older stop or any unrecorded later recreation is NOT recoverable from
these logs alone; the original transient request was deleted and pause content
had no provenance. Durable provenance was added to close that remaining gap.

Task Scheduler Operational history: disabled. Security log: access denied to
this session. PSReadLine history contains a Core `--stop`, not proof of this
WSRTD stop. Current scheduled task and HKCU Run command both explicitly use
`--ensure-running --dbname Data --relay-port 10101`, NOT `--stop`.

### Stop and pause call-path map

| Path / entrypoint | Condition / command | Creates pause / request? | Automatic / manual / tests / scheduler |
| --- | --- | --- | --- |
| `stack_launcher.py::main -> stop_from_pidfile` | Explicit `--stop`; matching recorded instance | Yes / yes when PID state exists; no state: pause only; mismatch: neither | Any CLI caller, including human/automation/tests; not current task/Run action |
| `stop_wsrtd_stack.cmd` | Calls Python `stack_launcher.py --stop` | Delegates both | Manual or external script invocation; not intrinsically human-only; no installed scheduler link |
| Previous Codex acceptance PowerShell | Exact command above | Delegates both | Explicit integration-test cleanup, proven execution |
| `run_supervisor_locked` stop-request branch | Existing instance request | Neither; consumes request then finally stops services | Automatic response to caller's request |
| `run_supervisor_locked::on_signal`, exception/finally | SIGINT/SIGTERM, relay readiness/startup/persistence failure | Neither | Manual OS signal or automatic fatal failure; service cleanup, preserves Broker |
| `run_supervisor_locked` child restart loop | Service exits / Broker missing | Neither | Automatic restart, NOT maintenance stop |
| `ensure_running`, status command | Watchdog/logon/status query | Neither | Automatic via installed Task Scheduler + Run key; pause respected |
| `launch_wsrtd_stack.cmd`, `main --resume` | Explicit launch/resume | Removes pause; no request creation | Human or scripted; not the configured scheduler entrypoint |
| `autostart_manager.py::install` / install recovery cmd | Explicit install | Removes pause; installs ensure-running commands; no stop | Human/script install; future triggers only ensure-running |
| `autostart_manager.py::uninstall` / uninstall cmd | Explicit uninstall | Neither; removes triggers only | Human/script; does not stop runtime |
| `install_wsrtd_stack.cmd` | Venv/dependency setup | Neither | Explicit installer or launch prerequisite |
| `test_stack_launcher_lifecycle.py` | Mocked process ownership/lifecycle tests | No production pause/request; temporary PID fixtures | Explicit tests; could run under CI, no installed schedule |
| `test_stop_provenance.py` | New stop/pause tests | Temporary-directory files only | Explicit tests with fake process state; never production stop |
| `Core/stack/autotrader_sim_launcher.py::stop`, `stop_child_confirmed` | Core `--stop`, startup rollback, shutdown | Neither WSRTD file | Core process tree only; manual/tests |
| `Core/tools/run_execution_restart_smoke.cmd`, `run_sim_stack_fixture_smoke.cmd` | `%LAUNCHER% --stop`; LAUNCHER resolves to Core launcher | Neither WSRTD file | Explicit smoke scripts, not current scheduler |
| Other Core smoke `taskkill` commands | Named `astu_*` service termination | Neither WSRTD file | Explicit tests; no Python/WSRTD kill path found |

Search included tracked/untracked/hidden code, .github, Core, CleanRoomR2 and
utility scripts, excluding Git internals, venv/build outputs and runtime logs.
External arbitrary scripts can still create a marker; application provenance
cannot audit writes made outside its own stop entrypoint.

### Provenance change

Before creating either stop artifact, append and fsync a JSONL intent record in
`runtime/stop_provenance.jsonl`; serialize concurrent appends with a bounded
Windows byte-range lock. Audit failure aborts before writing stop/pause state.
Pause and request contain the same structured record/eventId. Includes UTC,
reason, requester/parent PIDs, executable, username, DB/port/instance identity,
current launcher and child PIDs, intended artifacts and declared source.
Command text is an allowlisted effective invocation: raw argv, environment and
parent command lines are deliberately omitted to avoid recording credentials.
Source choices are direct-cli, cmd-wrapper, test-harness, installer, other;
they are caller-declared routing labels, not authenticated identities.
An intent proves a request attempt, not successful termination. The wrapper
now forwards explicit arguments and labels itself; its default DB is unchanged.

## DB default audit (unchanged)

| Script | Default |
| --- | --- |
| `launch_wsrtd_stack.cmd` | Data; port 10101 |
| `configure_plugin_registry.cmd` | Data; port 10101 |
| `stop_wsrtd_stack.cmd` | Inherits Python default WSRTD unless explicit arguments |
| `install_recovery_autostart.cmd` | WSRTD |
| `autostart_manager.py --dbname` | WSRTD; port from config (10101) |
| `stack_launcher.py --dbname`, blank InstanceLock fallback | WSRTD; port argument/environment/config |
| `status_wsrtd_stack.cmd`, `--resume`, uninstall wrappers | No DB selection needed for their existing global state operation |

Current actual configuration is Data:10101 in PID state, autostart_dbname.txt,
watchdog action and HKCU Run; Data registry reports Server=127.0.0.1, Port=10101.
Proposal for a separate change: align defaults deliberately or require explicit
DB selection. Do not run the no-argument stop/install wrappers on this host.

## Tests and observed runtime

Commands from repository root, using the existing WSRTD Python 3.12 venv:

```powershell
& .\CleanRoomR2\stack\.venv\Scripts\python.exe -B -m unittest discover -s CleanRoomR2/stack -p 'test_*.py' -v
& .\CleanRoomR2\stack\.venv\Scripts\python.exe -m compileall -q CleanRoomR2/stack
git diff --check
& .\CleanRoomR2\stack\.venv\Scripts\python.exe -B CleanRoomR2/stack/stack_launcher.py --status
& .\CleanRoomR2\stack\.venv\Scripts\python.exe -B CleanRoomR2/stack/stack_launcher.py --ensure-running --dbname Data --relay-port 10101
```

- PASS: 36 tests in 1.456s, exit 0: 20 existing lifecycle + 8 publication +
  8 provenance. Existing mocked-launch tests emit unclosed log ResourceWarnings;
  no assertion failures. Publication tests include real Windows held/released
  reader, old JSON preservation, retries/exhaustion, unique concurrent staging,
  cancellation cleanup, normal write, other I/O error, event-loop progress.
- PASS: provenance concurrency (9 intact append records), audit failure,
  explicit pause and recovery refusal, normal ensure no marker, source labeling,
  mismatched DB refusal, unknown secret args/environment omitted.
- PASS: compileall exit 0; diff check exit 0 (Git CRLF normalization warnings only).
- PASS: live status RUNNING; ensure ALREADY_RUNNING; maintenance_pause absent.
- PASS: forced Broker-only restart. Verified PID 27640, name Broker and creation
  FILETIME against PID ownership, then `Stop-Process -Id $brokerProc.Id -Force`.
  Supervisor created PID **24796**, start 2026-09-22 14:53:42.6901377 +08:00;
  PID state/log updated. Relay/server/identity/supervisor unchanged.
- PASS: at 14:54:10, market JSON parsed, marketUp/publicUp true, receiverCount 1;
  BTCUSDT live/fresh/cacheReady true, quoteAgeMs 8, caches 1500/300.
- NOT RUN: full-stack deployment restart, patched live long-duration publication,
  sleep/wake, reboot/logoff; require separate approval. Current server/supervisor
  were already running before these edits and have not reloaded patched modules.

## Local changed files and diff

All paths below are relative to `D:\wsrtd_binance_usdm_stack\autotrader`:

1. `CleanRoomR2/stack/binance_usdm_server.py` — atomic async retry publication.
2. `CleanRoomR2/stack/stack_launcher.py` — durable structured stop provenance.
3. `CleanRoomR2/stack/stop_wsrtd_stack.cmd` — explicit argument forwarding/source.
4. `CleanRoomR2/stack/test_market_status_publication.py` — new isolated tests.
5. `CleanRoomR2/stack/test_stop_provenance.py` — new isolated tests.
6. `CleanRoomR2/stack/LOCAL_STATUS_STOP_REVIEW.md` — this report.

Tracked diff: 3 files, 132 insertions / 15 deletions. Three new untracked files
(two tests + report) are additional and not included in ordinary git diff --stat.

## User-run deployment validation (after review)

The following deliberately stops the full stack. **Not executed by Codex.** Run
only when ready for a maintenance interruption, from a shell with the same rights
as the current runtime. Explicit Data prevents the default-DB mismatch.

```powershell
Set-Location 'D:\wsrtd_binance_usdm_stack\autotrader'
& .\CleanRoomR2\stack\.venv\Scripts\python.exe CleanRoomR2/stack/stack_launcher.py --stop --dbname Data --relay-port 10101
if ($LASTEXITCODE -ne 0) { throw 'Stop failed; do not continue' }
Get-Content CleanRoomR2/stack/runtime/maintenance_pause
Get-Content CleanRoomR2/stack/runtime/stop_provenance.jsonl -Tail 1
& .\CleanRoomR2\stack\.venv\Scripts\python.exe CleanRoomR2/stack/stack_launcher.py --ensure-running --dbname Data --relay-port 10101
# Expected MAINTENANCE_PAUSED; then launch explicitly clears the marker:
cmd.exe /d /c 'CleanRoomR2\stack\launch_wsrtd_stack.cmd Data 10101'
if ($LASTEXITCODE -ne 0) { throw 'Launch failed' }
& .\CleanRoomR2\stack\.venv\Scripts\python.exe CleanRoomR2/stack/stack_launcher.py --status
Get-NetTCPConnection -LocalPort 10101 -State Listen
1..10 | ForEach-Object {
    Get-Content CleanRoomR2/stack/runtime/market_status.v1.json -Raw | ConvertFrom-Json |
        Select-Object generatedUtc,marketUp,publicUp,receiverCount
    Start-Sleep -Seconds 1
}
Get-Content CleanRoomR2/stack/runtime/autotrader_status/BTCUSDT.json -Raw | ConvertFrom-Json
Get-Content CleanRoomR2/stack/logs/server_supervisor.log -Tail 80
Test-Path CleanRoomR2/stack/runtime/maintenance_pause # Expected False
```

Remaining risks: historical lock holder and global server count unresolved;
long-held readers still cause a clearly logged bounded publication failure;
concurrent independent servers can still publish semantically conflicting
snapshots; forced process termination can leave a unique staging file because
no finally block can run after hard kill; source labels are self-declared;
external file writes cannot be attributed by this application audit; legacy DB
defaults remain inconsistent. No claim of patched live acceptance is made.

REMOTE_GITHUB_CHANGED=NO

LOCAL_COMMIT_CREATED=NO
