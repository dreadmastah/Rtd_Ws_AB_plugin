# Isolated dependency resolution

The candidate imports aiohttp, websockets and psutil in addition to Python's
standard library. Middleware integration requires a client version providing
per-request middleware; the exact tested resolution uses aiohttp 3.14.4.
`requirements-rc2.lock` lists all 12 resolved distributions.

No package downloads or system-wide installs were performed. A new RC2 virtual
environment uses CPython 3.12.0, Windows x64. Package files were copied from an
existing isolated validation environment only after verifying each hashed
distribution RECORD entry. A deterministic local artifact captures all required
package files. Its SHA-256 is
`5abaca01329e4c2def0c2e3021079291a15727c45b79101bcce79b7b5ba87af4`.

`inputs/dependencies-cp312-win_amd64.zip` and the machine-readable dependency
report permit offline reconstruction without a running WSRTD installation.
Create a fresh CPython 3.12 Windows x64 virtual environment, verify this artifact
hash, extract it into that environment's `Lib/site-packages`, then run `pip check`.
The artifact's identity establishes local consistency, not independent publisher
authenticity. A future public wheel-based installation needs separately verified
wheel artifacts for the exact lock; none were downloaded or invented here.

The final test suite requires `RC2_WORKSPACE` set to its isolated root,
`RC2_OUTPUT` set to a fresh directory under that root, and `PYTHONPATH` containing
the candidate's `Tests/guard` and candidate root. Run the isolated Python with
`-B -m Benchmarks.run_offline_tests` from the candidate directory. The guard
confines writes and permits connections only to test-owned ephemeral loopback
listeners. Original ports 10101, 18101 and 18102 are never used.

The test harness verifies exact package versions, generates fresh fairness
results, then runs the complete applicable regression suite in one process.
Disposable Python child processes inherit the guard. No test needs files from
the installed sender, relay, AmiBroker database or predecessor workspaces.
