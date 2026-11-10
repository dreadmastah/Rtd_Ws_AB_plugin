# WSRTD N1 Data Plugin development archive

Development checkpoint only. No production release or activation authorization.

`R1` through `R8` map directly to `D:\WSRTD_N1_DATA_PLUGIN_FORMING_R1` through `R8`. Copied artifacts retain exact original bytes and relative paths. `references/OWNED_CPP_N1_20261028_R1` contains the original native implementation referenced by R1. R1 is a diagnostic milestone with no original SHA-256 manifest; it is not represented as a built release. No R9 was present.

Run `python verify_archive.py` from this directory for portable, read-only copied-byte verification. Original milestone verification/build scripts remain unchanged and may require their original Windows paths and dependencies. Original manifests are preserved even when they reference deliberately omitted artifacts; use ARCHIVE_INVENTORY.json for the complete inclusion/omission mapping. Do not regenerate old evidence to conceal omissions.

Build prerequisites: Windows x64, Python3.12, CMake and MSVC; use the relevant milestone's build.py/build_native.py/stage_native.py and native/CMakeLists.txt. Inspect hard-coded disposable/output guards before executing. R3 onward builds use the included ADK headers. The older reference additionally requires its separately supplied ADK and SQLite amalgamation3.54.1; these dependencies were not copied from that reference. R8 does not change native code and deliberately does not rebuild the R7 DLL. Builds were not rerun for this archive.

Excluded: disposable databases and WAL/SHM, private test keys/certificates, build outputs/caches, runtime/host snapshots, logs ignored by repository policy, environments and unrelated data. Exact per-file omissions are in ARCHIVE_INVENTORY.json. Source paths, test PID examples and historical engineering diagnostics remain evidence, not current runtime authority. No credentials/private keys were found in the staged allowlist.

Use STATUS.md for current limitations. Never install or run a candidate based on archive publication alone.
