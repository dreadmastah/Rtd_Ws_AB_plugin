# Exact protocol gap

Source: D:\WSRTD_PR3_Test_20261010\releases\a2401ca\Binance\sender.py. record() emits n,d,t,o,h,l,c,v. CandleBuffer.ingest retains E and x in its local seen version but forwards record() without E/x. That per-symbol high-water also rejects older-minute late finals after a newer minute. Historical frames have a separate hist/format/bars envelope. Legacy records cannot be upgraded to V2 by guessing missing E/x.

Relay source: releases\a2401ca\Relay\Server\Python\relay.py, configured path protocol. /sender broadcasts bytes to /receiver or /; receiver messages flow upstream. No authentication is supplied by that relay framing. Existing receiver compatibility with new envelopes has not been demonstrated. Do not emit V2 blindly into the shared relay.

Minimum versioned correction: create V2 alongside the exact original Binance event, before legacy record() discards metadata; retain separate per-bucket finality and receipt times. Add authenticated custody/session framing and a separately routed versioned receiver channel, while preserving legacy output. transport.envelope() implements the isolated transformation; it is not deployed into sender.py. No running sender with a compatible alternate output has been verified.

The snapshot records process creation identities, executable/source hashes and sockets. It is point-in-time evidence, not proof of current Binance subscriptions, subscription universe or event freshness. No genuine payload was received. Existing18101 producer remains UNVERIFIED, not automatically INACTIVE.

## Refreshed configured-chain evidence

Bounded existing status/log/source inspection corroborates the configured18101 sender is INACTIVE at observation: status sender_pid=null and sender_running=false, supervisor PID26188 creation matches process census. The supervisor detects only Broker.exe at the installed path with an established18101 socket. A helper receiver does not satisfy this rule. A Broker connection can launch the sender with --native-history --quotes and cause REST rehydration. Do not treat either connection type as a qualified passive path.

Historical sender-log tail records strict pinned-universe rejection of EPICUSDT, MITOUSDT, PTBUSDT and VELODROMEUSDT. This identifies the old failure, not current eligible membership. Do not delete those symbols/history or silently replace the pinned configuration. Output metadata correction, receiver-gating compatibility and separately authorized restoration remain required.
