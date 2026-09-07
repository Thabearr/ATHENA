# Current-only non-legacy history issuance

Purpose: `CURRENT_SHADOW_RESEARCH_ONLY`. This is not PR119/PR149 history,
does not mutate `LEGACY_PRIMARY_IDS`, and cannot seal a holdout prediction.

## Source audit

The chosen source is the existing latest-applicable durable history handoff's
complete reviewed `SettledFreshPrediction` tuple. Its source is replayed through
the existing GitHub/Release/archive/checkpoint boundary before issuing features.
The new builder accepts no caller result rows, timestamps, SHA claims, odds or
feature values. Detached output receipts are diagnostic only; there is no
receipt-admission API. The independent version-1 contract SHA is
`a3c60b068e95946cdbf6c8b9715994ee04e26736474512fc01c76e979d804d10`.

Other sources investigated:

| Source | Identity / time / result | Current use |
|---|---|---|
| Frozen PR119 bootstrap | Exact FotMob IDs and observations; 21,326 reviewed rows | Unchanged frozen Elo inputs only |
| Legacy settlement updates | Exact IDs, oriented scores, observed UTC | Unchanged; never widened |
| Reviewed durable settlements | Exact FotMob fixture/team/primary IDs; kickoff and result observation; ordinary FT | Selected, same competition only |
| Raw capture archives | Exact bytes/manifest observation, but results require qualification | Never parse directly as feature evidence |
| Historical warehouse | Competition-scoped names, optional source IDs, mutable field precedence and ingestion timestamps | No proven current FotMob/as-of join |
| Historical As-Of | Date-prior warehouse features, not current provider identity or availability proof | Not consumed |
| Operational results DB | Mutable results without exact raw/manifest observation ancestry | Not consumed |
| Current identity registry | Exact reviewed fixture reconciliation, no result truth | Not a history source |

Existing-source inspection: Release W37 asset 548903884,
`success-20260907T140700Z-run-34131595760.tar.gz`, SHA-256
`3eb3d2876a88d4a4ccf8533ac15ed50067d3442355bd0936061abcd5b6acd4d9`.
Its journal contains 255 ordinary-FT settlements and one identity-drift exclusion.
Some settlements are non-legacy, but none involves the twelve teams in run214's
six Elo-only fixtures. This inventory is not a new historical replay attestation.
Those six therefore have no demonstrated new coverage; no changed prediction
or live operational success is claimed.

## Coverage and mathematics

Only the target's exact provider primary ID and oriented team IDs participate.
No cross-competition result borrowing or display-name matching occurs. Both
kickoff and settlement observation must precede current inference as appropriate:
prior kickoff < target kickoff and current capture time; observation <= capture.
Duplicates, conflicts, self-history and invalid evidence fail closed. No claim of
complete competition coverage or maximum-recency policy is invented.

The actual frozen form definition needs **one**, not five, prior results. It uses
up to five latest results: round(0.10 + 0.85 * points/(3*n), 3). Fatigue requires
one prior result for each side. It uses integer rest-day differential and the
existing 0.30/0.10/0.0 mapping. Functions are reused, not reimplemented.
Coverage records retain exact IDs, count, earliest/latest kickoff, as-of, status,
missing reason and an explicit false completeness claim.

All three newly issued features must exist before they can join the unchanged
frozen-ledger Elo inputs and frozen rate equations. No partial mixing with
legacy form is performed. Otherwise the reviewed Elo-only fallback remains.
Invalid source issuance cannot authorize full inference and is visible in the
existing durable per-fixture diagnostic. The original full-model path runs first.

No tactical context, prices, provider calls, email changes, scheduler changes,
production authority, wallet, stake, wager or historical backfill is introduced.
