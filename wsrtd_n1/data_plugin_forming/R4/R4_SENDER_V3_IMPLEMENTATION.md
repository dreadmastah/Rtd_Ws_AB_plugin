# Sender-to-receiver V3 metadata

src/sender.py validates subscribedsymbol and pipeline producer/session/universe/symbolset, rejects duplicateJSONkeys and nonobjectroot, and passes complete supplied sourceevent into unchanged R3 Pipeline.encode. It retains raw x/E/t/T/OHLCV/volume/count and optionalraw fields. No nextminute or wallclock finalization inference. IsolatedRelay validates exact declared custody plus receiverpipeline before exact-byte handoff. R3validates reconstructedcandle/rawlinkage and atomically persists receipt with finalrow.

V3 sourceevent encoding remains SYNTHETIC_FIXTURE through the unchanged R3 receiver. This cannot accept or attest genuine Binance custody. No localHMAC or newproducer label promotes trust. Missingevent fields reject. RESTmetadata fixture does not produce a verified universe; allowlist is an explicit testinput. A real networkadapter, TLSprovenance and OSprocess custody verifier are not supplied and remain required.

No running sender changed. src/admission.py and sender.py are versioned Python source, not standalone compiledbinaries. Exact Python executable hash is recorded in the sourceinventory; no senderbinary is invented. R3nativeDLL unchanged.
