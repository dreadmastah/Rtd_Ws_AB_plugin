# Versioned correction

src/pipeline.py encode/receive retains original source_event, universeversion, session and explicitV3 wrapper. Inner candle carries E,t,T,x,decimalOHLCV/basevolume,optionalquotevolume/tradecount and null eventID where absent. No timestamp or finality is inferred. Full wrapper is persisted atomically for newly committed finals. Receiver rejects corruptMAC/version/universe/raw linkage, invalidbody and stale sessions. No running sender source is edited.

This is a callable offline adapter, not a deployed WebSocket transport or Binance acquisition process. Existing18101 legacy fields cannot be converted losslessly after E/x discard. A versioned producer correction must occur before record() and must retain legacy receiver compatibility. Actual producer custody and complete current UM/CM metadata qualification remain blocked.
