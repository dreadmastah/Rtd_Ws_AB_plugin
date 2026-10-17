# WSRTD 500-symbol Python source candidate — RC2 preview

Local publication draft. No version, tag, release or deployment is authorized.
Final test and independent-review status are recorded in the RC2 receipt; this
preview does not override a failed or incomplete gate.

The source combines previously approved 3:1 minute/daily repair arbitration and
page-level progress with guarded monotonic REST pacing and persistent cooldown
deadlines. Requests remain serialized with a minimum 250 ms spacing. Client
middleware covers retries and redirects without disabling the existing policy.

The pipeline supports a selected universe of up to 500 eligible Binance USD-M
USDT perpetual symbols, divided into five market-stream shards at 100 symbols
each. Optional quote subscriptions use their existing separate streams. Native
history and JSON wire formats are preserved. No trading functionality is added.

Telemetry stays disabled by default. When enabled explicitly at startup, bounded
recording and export run without extra market-data requests. Repair observations
now cover the page-level scheduler, including repairs between preload pages.
The inherited R15C observer does not infer reconnect causes from generic repair
execution or label 5xx backoff as an exchange cooldown observation.

The original supervisor is retained. Windows maintenance adapters, recovery-agent
provisioning and Task Scheduler experiments are excluded. The two existing
main-branch context-document commits are preserved byte-for-byte.

The dependency resolution is exact for CPython 3.12 on Windows x64: aiohttp
3.14.4, websockets 16.1.1 and psutil 7.2.2, with transitive versions recorded in
the candidate lock. These are tested-resolution pins, not a claim about newest
versions or other Python/platform combinations.

These acceptance gates remain separate:

| Gate | Status |
| --- | --- |
| GitHub source release candidate | Local source only; see final RC2 test/review receipt |
| Windows production deployment | Not authorized |
| Native DLL/storage acceptance | NOT_PROVEN |
| Live 500-symbol freshness | FAIL_PREVIOUS_R6 |
| Actual UTC rollover | NOT_PROVEN |
| Aggregate public-IP headroom | NOT_PROVEN |
| Installed watchdog dispatch fencing | NOT_PROVEN |
| R16 execution | Not authorized |

Offline fixtures cannot establish live freshness, native persistence or recovery
after host interruption. No production-ready claim is made. Earlier failed test
runs remain in the local evidence package.
