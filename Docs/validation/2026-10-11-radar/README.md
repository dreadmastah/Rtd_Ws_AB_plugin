# Native RADAR smoke results — 2026-10-11

**Disposition: visible 13-row and 500-row live RADAR smoke demonstrated;
full native acceptance remains incomplete.** PR #3 remains draft and unmerged.
This note adds evidence; it does not supersede the existing failure records or
the pending actual-rollover acceptance in [Binance-500.md](../../Binance-500.md).

## Test binding

- Database: `D:\WSRTD_PR3_Test_20261010`, 1-minute, local storage enabled.
- AmiBroker PID 85728, creation epoch `1791663354.916726`; test socket 18101,
  with no production-port 10101 connection at either end of each process sample.
- Isolated sender release: `a2401ca`; 500-symbol live feed remained running.
- Formula fix: `a89a1faa0d13401e3446644a45fb691424d1ebc8` replaces undefined
  `formatTime` with `formatDateTimeISO` and uses `Now(5)`.
- Evaluation local is a local wall-clock timestamp, not quote receipt latency.
  Bar UTC is a minute-open timestamp, not a delivery timestamp.

## Observed results

| Observation | 13 rows | 500 rows |
| --- | ---: | ---: |
| Native GUI result count | 13 | 500 |
| GUI completion display | 0.17 seconds, one-shot exploration | 0.10 seconds, RADAR screenshot |
| Passive process sample duration | 30.010508 seconds | 30.007803 seconds |
| Process CPU consumed | 0.703125 seconds | 0.531250 seconds |
| CPU, one logical core = 100% | 2.342929% | 1.770373% |
| CPU, all 12 logical CPUs = 100% | 0.195244% | 0.147531% |
| RSS minimum / maximum, bytes | 224792576 / 224989184 | 224501760 / 224501760 |

The user first ran the explicit 13-symbol watchlist, then manually selected
**All symbols** and demonstrated 500 result rows. The 500-row count is not an
exported exact-set comparison against the saved selected universe. Visible
rows show interval 60; the full 500-row interval column was not exported.
The 13-row RADAR screenshot showed advancing values after the one-shot run.
The 500-row screenshot showed RADAR active and populated, not a recorded
multi-cycle timing trace. The 0.10-second GUI display is not a latency percentile
or independently measured end-to-end throughput.

The process samples cover all of AmiBroker, including charts and native DLL
ingestion, with the same 500-symbol live feed active for both samples. CPU is
`100 * process CPU delta / elapsed seconds`; machine-normalized CPU divides
that value by 12. RSS is sampled once per second for 30 samples. These short,
non-synchronized windows do not establish a scaling improvement, isolate RADAR
cost, or certify absence of memory leaks. No new native command was sent by
the passive sampler.

## Evidence and provenance

The committed [13-row metrics](radar-13-metrics.json) and
[500-row metrics](radar-500-metrics.json) include all 30 process samples and UTC
start/end times. Their original local files remain under the test database in
`radar-13-passive-20261011-r1/metrics.json` and
`radar-500-passive-20261011-r1/metrics.json`.

| Original local evidence | SHA-256 |
| --- | --- |
| 13-row process metrics | `f2adcc0312c6aaabb1556d9103f0d43dc7b13aeb254cd7a006cc92bef1f98ed0` |
| 500-row process metrics | `131464bdb57bd42ca2b20454627d4d0d5ab3d7b1908727265950cbb5da9d17d9` |
| Native readback audit summary | `bc9a676bda93d336f817bd07d4b8a74f72d10fc8a1ce0ba39e622bba1dd900e2` |
| 13-row exploration screenshot, `codex-clipboard-f7d57af9-bae5-4db0-b0f8-e3fe2ba7ebc6.png` | `60717f9b98743eec41a0b706fc85ef10123f0785941d2788223d0c45bacae0cc` |
| 500-row RADAR screenshot, `codex-clipboard-546d205c-d1c6-4936-ae44-70564e70cbca.png` | `c763d8074ac3e02f79ecb255eadfeaef9d15625f57607448dc95a8a7f5336bfb` |

Screenshots were supplied by the operator in the task and are not published
here. The native audit remains local at
`native-ipc-audit-20261011-r1/summary.json`: 500 selected symbols, four recent
closed BTC-axis minutes each, 2000 non-null bars, and 56 sampled closed bars
across 14 symbols matching REST within one float32 ULP plus a 1e-12
serialization floor. It used `SetForeign` with fixup disabled; this is neither
independent per-symbol retention verification nor a full-history comparison.

Earlier Python transport, unit-test and REST audit evidence is separate from
native DLL and RADAR acceptance; this note does not relabel those tests.

## Failed attempts and remaining coverage

- The original formula failed native compilation because `formatTime` was
  undefined. The corrected formula passed native execution and the visible
  exploration/RADAR checks above.
- Initial generated APX strings were not escaped correctly. The path-error run
  returned zero rows and failed. After escaping the path and embedded formula,
  the start client timed out at 45 seconds, but the later operator screenshot
  showed the completed 13-row exploration. Do not treat that timeout as a
  throughput result or blindly replay a request with unknown server outcome.
  These local artifacts remain in `native-explore-13-20261011-r1` through `r4`.
- Native 100/250-row RADAR stages were skipped when the operator advanced to
  500. They are not marked passed.
- Exact 500-row exported membership, per-symbol freshness, cumulative-volume
  replacement across updates, minute boundaries, and native reconnect/backfill
  acceptance need dedicated evidence; a populated screenshot alone is insufficient.
- Synthetic native DLL/RADAR load, sustained update latency and long-duration
  CPU/memory acceptance remain unperformed. Synthetic prices must use a separate
  synthetic-only database and relay, never this live or the production database.
- Actual UTC-rollover acceptance for the revised sender remains separately
  pending as documented in the parent guide.

No production database, production service, network setting or scheduled task
was changed for these RADAR samples or this documentation publication.
