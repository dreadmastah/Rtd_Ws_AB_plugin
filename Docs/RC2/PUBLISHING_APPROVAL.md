# Publication decision package — no action authorized

This package prepares a later source-publication decision. No commit, push,
merge, tag, release, ready-for-review update or deployment is authorized.

The operator should assess the final RC2 receipt, exact source manifest,
dependency artifact provenance, complete test run and final independent review.
Publication readiness requires zero unresolved blocking findings. A missing final
review or failed test means the candidate is not ready for publication approval.

If all gates later pass, the separate decision must name the exact reviewed
source hash, destination branch, intended commit/push operation, and any proposed
version/tag. No values are preselected here. Main or PR drift must be reconciled
again before any remote write. Do not force-push or merge by implication.

Only reviewed source and curated public documentation belong in publication.
Exclude private host inventories, runtime paths/logs, user identities, native
databases, DLLs, credentials and local dependency snapshots pending any required
distribution review. Preserve existing repository notices and context documents.

Publication of source does not authorize Windows activation. R15N-R2, recovery
changes, native acceptance, live freshness testing and R16 remain separate.
