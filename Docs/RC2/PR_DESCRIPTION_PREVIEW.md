# Reconcile approved WSRTD 500-symbol source corrections

Draft only; PR #3 has not been edited or marked ready for review.

The published PR3 sender and later offline sender packages followed different
source lines. This candidate preserves the explicitly approved R5/R6A repair
fairness and history semantics, combines the R15B actual-attempt pacing and
cooldown guards, and integrates R15C default-disabled telemetry. It also includes
the two main-branch context-document commits without changing their contents.

The exact dependency resolution and standalone offline test references are
included. The original supervisor remains byte-identical; Windows maintenance,
recovery provisioning and native DLL changes are excluded.

Validation must be read from the final RC2 receipt. Development failures are
retained, superseded test assertions are explained, and the final uninterrupted
suite is bound to its source hash. An incomplete independent review prevents
publication readiness even if tests pass.

Live freshness remains failed/unaccepted. Native storage, actual UTC rollover,
aggregate IP headroom and installed watchdog dispatch fencing remain unproven.
Publication, merge and deployment require separate operator decisions.
