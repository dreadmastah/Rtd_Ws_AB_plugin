# RC2 source provenance and reproduction

PR baseline: `ea79ae6df50ed419564813d2402fed0c6d29df87`.
Main baseline: `662ada11e335d236ba48a8846ec6d45b371754d4`.

RC2 is an independent source copy, not a linked checkout. No local or remote
commits are created. `inputs/pr3-base.tar` contains the original Git archive.
`05_ISOLATED_SOURCE_DIFF.patch` records the candidate delta. The final source
manifest identifies every candidate file; an archive provides a direct
reproducible source artifact without installed-runtime dependencies.

R6A source inventory is authenticated through its operator-bound evidence seal
`20febc17c070d6550302999e184e21ac911e930386f8d0e9afa172112deda2b0`.
The sender hash is
`042ee153dcb459b58712357ac7193c451abf2651ceea7a0dd725ff52bb23b2f6`.
R15B source manifest is
`911a37d2f7313e324682e75475b8f4e4dccbd33ca89069a4a0ea8c48b62fdfbf`.
R15C source manifest is
`7391e911fd1180dc454f2b1cbdc03b68a2dc047ba339bf4912be424b9da34cb0`.
R15D source manifest is
`99fd9ca26e13bfb3a3a0f6fdb1c32f8dec77b3851b34bf8495d5410af6ccbd65`.
R15F's sealed receipt binds source manifest
`a4efd3aa720bbd4798f240e7f67e713fbf39361fae60ebcfbb63773460ab43cb`.

Each source manifest and its entries was verified. R15D/F sender and telemetry
modules are the same as R15C; their Windows maintenance implementation has no
import dependency from the selected sender/telemetry modules and is excluded.
Fairness authority comes from explicit R5/R6A operator specifications, not from
R15B/C's narrower authorization. The method-level matrix records every compared
method and residual module declaration, with line ranges and source identities.

Two main-only commits, `b7235cfe07b248aa14fa7889a03676a7ce9dacd0` and
`662ada11e335d236ba48a8846ec6d45b371754d4`, affect only
`Docs/WSRTD_PROJECT_CONTEXT_2026-10-13.md`. Its exact Git blob is preserved.
Existing historical paths and identities in that repository document are
historical context, not new installation instructions or current identity claims.

The local evidence contains private host paths and inventory and must not be
uploaded wholesale. Publication assets require a separate review. No plugin
DLL, AmiBroker database, license key or Windows installation package is included.
