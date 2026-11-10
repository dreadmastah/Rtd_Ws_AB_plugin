# Installed N1 data-plugin forming-bar assessment

Task: WSRTD_N1_500PLUS_DATA_PLUGIN_NATIVE_FORMING_BARS_R1
Observation: 2026-11-04 local time. Radar work deferred. No network connections, process control, installed-file changes, or original SQLite SQL connections performed.

## Exact findings

Installed `C:\Program Files\AmiBroker\Plugins\WSRTD_Owned_N1_DATABASE_BOUND.dll` SHA256 `ae7f6bc4e9ec61c3103b48d8ee43769173b44ed1619aa61ffbcc15b513af4179` matches the candidate and independent review in `D:\WSRTD_OWNED_CPP_N1_20261028_R1\13_INDEPENDENT_REVIEW.json`. It is loaded in Broker PID 92688, creation 2026-11-04T05:57:49.00523+08:00, parent 62440. Operator identifies the selected source and N1 database; loaded-module inspection does not independently establish selection or successful Init.

Exact source: `D:\WSRTD_OWNED_CPP_N1_20261028_R1\candidate\native\owned_plugin.cpp`, SHA256 `73f7981797cb9cb60700579f1756b4182db8b3bf6de0677be7e864d15b5c58af`; reader `owned_reader.cpp`, SHA256 `78b89de0e92424922b6d6ce0166d6d06af417749fa5fbb0eaa2e7260f60189d6` in the same directory.

1. Init requires an absolute `WSRTD_N1_SQLITE_PATH`. Absent/empty returns 0; it does not discover the sidecar automatically. Prior absent-environment evidence belongs to an older Broker and is not proof of the current process's environment or Init outcome.
2. Notify binds physical database identity and requires its key in SQLite database_context. GetQuotesEx supports 60/86400 seconds, copies UTC-validated OHLCV into ADK Quotation, and reads **only finalized=1** rows. There is no network receiver or port18101 binding.
3. There is no transient forming-bar cache, forming replacement/finalized promotion pipeline, GetRecentInfo, or automatic refresh worker in this source. Notify handles lifecycle; it does not signal new quotes. The external RefreshAll comment is not evidence of a running refresh controller.
4. The reader is read-only; errors return zero. Returning fewer stored bars can shorten the returned host buffer; the predecessor review explicitly leaves native historical retention unverified. Do not repair this by merging unscoped host buffers.
5. `D:\Amibroker_myDATA\N1\.wsrtd-n1\feed.sqlite` has schema2/application_id1465074229. File SHA256 `cefea565ca4a869b434c8c94f6d51989c0dda9993562d2d0a1487ff63b6642bc`. Its memory-only image has two registered symbols, BTCUSDT and ETHUSDT, with one finalized minute each, timestamp1791650280000. This is neither complete-since-listing evidence nor live coverage. Original bytes were checked unchanged. No claim of source provenance follows from finalized=1 alone.
6. Directory file ID `09490000000be708` matches the file-index portion of stored context `303accbc:09490000000be708`. Volume identity and current host's bound key still require attestation; this partial match is not complete runtime binding proof.
7. Observed listener18101 is PID119852; listener10101 is PID116276. At this socket snapshot18101 has no established connections. 10101 has a connection from PID113576. No sender.py process was found in the bounded command-line query. A listener is not a working quote source.
8. Source for the observed18101 relay command is `D:\WSRTD_PR3_Test_20261010\releases\a2401ca\Relay\Server\Python\relay.py`, path protocol. Its sibling `Binance\sender.py` ingests nonfinal and final klines, but record() emits n,d,t,o,h,l,c,v without event E or final x. CandleBuffer uses x internally, then drops it from the forwarded record. It cannot independently establish authoritative finalization from those wire fields. No live payload observation was attempted and no source-on-disk claim implies that a sender is running.

## Required implementation boundary

A functional correction needs a separately versioned data-plugin receiver/adapter, a transient per-symbol current-minute cache, scoped finalized history, lifecycle-bound native refresh, and explicit provenance/finalization admission. Same-minute updates must replace cumulative OHLCV, never sum cumulative volume; previous-minute data must not be declared finalized merely because a later minute arrives. Missing/stale/replayed events must remain unready. A forming cache cannot waive complete-since-listing readiness.

No candidate DLL is built here: there is no qualified current upstream producer, the existing wire contract loses required finality/source metadata, and no activation/change authority covers the protected18101 producer. A DLL that exposes the two old rows or invents finality would not correct the requested system. A parallel Binance streamer is not implemented. Reusing the existing18101 architecture remains preferable to adding another upstream connection, but requires an explicitly approved adapter/protocol scope and a functioning sender.

## Smallest next authorization and verification

First designate the intended existing18101 producer/configuration and authorize, separately, its bounded restoration if it is offline. Include permission for an isolated receiver contract carrying symbol, minute-open UTC, exchange event time, finalized flag, OHLCV, source/session identity and replay ordering; preserve compatibility with existing receivers. No Broker restart is needed for that source-contract qualification. Do not authorize a parallel Binance subscription by implication.

After an offline versioned data-plugin candidate passes this contract, separately approve a supported plugin loading lifecycle and disposable native database. The current loaded v5.1.0 cannot acquire missing receiver/forming functionality through a path variable. Do not replace a loaded DLL or switch the current source in this task.

Native acceptance must correlate BTCUSDT and ETHUSDT received events, exact GetQuotesEx timestamps/OHLCV, repeated updates within one minute, one final promotion, and automatic chart refresh. Separately attest full-prefix history. Then expand through the explicitly identified Foundational13,100,500,eligible universe. The exact13-symbol membership is not established here; do not invent it. Verify native history preservation before using original history. No native PASS is claimed.

## CMD read-only verification

```cmd
certutil -hashfile "C:\Program Files\AmiBroker\Plugins\WSRTD_Owned_N1_DATABASE_BOUND.dll" SHA256
certutil -hashfile "D:\Amibroker_myDATA\N1\.wsrtd-n1\feed.sqlite" SHA256
fsutil file queryfileid "D:\Amibroker_myDATA\N1"
tasklist /m WSRTD_Owned_N1_DATABASE_BOUND.dll
netstat -ano -p tcp
```

Compare actual outputs to captured identities, not old PIDs. These commands do not establish native quotation delivery. No restart, source switch, environment edit, producer launch or relay connection is part of this procedure.

## Preservation limits

No production modifications made. SQLite bytes compared equal across inspection; other historical files were not written. This is not a full historical integrity audit or exclusive-writer assertion. Broker remains running, and no control operations targeted10101/18101. Existing R3/N1/Radar releases remain unchanged.
