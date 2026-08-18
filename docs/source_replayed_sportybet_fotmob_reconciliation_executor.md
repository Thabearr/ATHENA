# Source-replayed SportyBet/FotMob reconciliation executor

## Purpose

This is the thin offline execution boundary after PR #165. It does not define new reconciliation semantics. It reconstructs the exact already-reviewed source chain and invokes the durable PR #164 receipt layer.

The operator consumes:

- one exact PR #153 user-controlled SportyBet event-detail evidence directory;
- one exact PR #157 user-controlled official SportyBet Terms evidence directory;
- one exact PR #161 user-controlled official Sportradar event-metadata evidence directory;
- one or more verified PR #38 FotMob `/api/data/matches` capture directories;
- the explicit FotMob fixture-review decision ledger;
- a checked reviewed Fixture Catalog JSON and manifest generated on the exact current clean Git state;
- one stored PR #165 source-replayed reviewed Fixture Catalog admission directory.

It then rebuilds, rather than trusts, the SportyBet native inventory, event-local GMT qualification, Sportradar event-ID bridge, Sportradar metadata lineage, confirmed kickoff promotion, and reviewed FotMob admission before PR #164 stores the exact PR #163 full-UTC reconciliation bytes.

## Important current-Git requirement

PR #165 deliberately binds checked Fixture Catalog evidence to the actual current clean Git HEAD. Therefore a checked catalog/manifest created on an older commit cannot be reused after this executor merges merely by changing its recorded SHA.

Before real execution, regenerate/check the reviewed Fixture Catalog and manifest on the exact clean merged code state, then replay/store the reviewed admission from those exact sources. The executor fails closed when the checked manifest `generator_commit` differs from actual current HEAD or the tracked worktree is dirty.

## No network acquisition

This command performs no SportyBet, Sportradar, or FotMob provider network request. It consumes only previously preserved local evidence.

The allowed evidence roots remain the existing reviewed roots:

- `.cache/athena-research/sportybet-user-controlled-evidence`
- `.cache/athena-research/sportybet-official-time-semantics`
- `.cache/athena-research/sportradar-user-controlled-event-metadata`
- `.cache/athena-research/fotmob-data-matches-captures`
- `.cache/athena-research/reviewed-fixture-catalog-admission-source-replay`

The resulting receipt remains under the existing PR #164 root:

- `.cache/athena-research/sportybet-fotmob-full-utc-reconciliation-receipts`

## Source-replay sequence

1. Verify the SportyBet event evidence directory before and after reading its exact HTML bytes.
2. Rebuild the provider-native SportyBet inventory from those same bytes.
3. Verify the official Terms evidence before and after reading its exact HTML bytes.
4. Rebuild the event-local GMT/year-unknown qualification from event + Terms evidence.
5. Rebuild the documented SportyBet `sr:match:<n>` -> Sportradar `sr:sport_event:<n>` bridge.
6. Verify the stored Sportradar evidence, reread the exact response bytes, and source-revalidate it against the rebuilt bridge and SportyBet source chain.
7. Rebuild the confirmed Sportradar kickoff-year/full-UTC promotion.
8. Replay PR #165 from the exact raw FotMob captures, fixture-review ledger, checked catalog/manifest, and actual clean Git state; require an exact `ADMITTED` reviewed catalog.
9. Independently re-read and verify every supplied FotMob raw capture into exact `(raw bytes, manifest)` pairs.
10. Build PR #164's complete `FullUtcReconciliationSourceBundle`.
11. Store the exact PR #163 reconciliation receipt using PR #164.
12. Source-verify the stored receipt again before reporting success.

## Invocation

Run only from a clean checkout containing the exact checked catalog/manifest used by the PR #165 replay:

```text
python -m scripts.execute_source_replayed_sportybet_fotmob_reconciliation \
  --event-evidence-directory <event-evidence-dir> \
  --terms-evidence-directory <terms-evidence-dir> \
  --sportradar-evidence-directory <sportradar-evidence-dir> \
  --fotmob-capture-directory <capture-dir-1> \
  --fotmob-capture-directory <capture-dir-2> \
  --fixture-review-decision-ledger <fixture-review-ledger> \
  --check-catalog <checked-catalog.json> \
  --check-manifest <checked-manifest.json> \
  --fotmob-admission-directory <source-replayed-admission-dir>
```

The command emits one JSON summary to stdout. Failure is non-zero and emits no successful summary.

## Meaning of the result

The underlying PR #163 disposition is preserved exactly:

- `UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED`: exactly one admitted FotMob fixture matches exact case-sensitive home, away, competition and provider-resolved full UTC. This authorizes fixture reconciliation only.
- `NO_EXACT_FULL_UTC_MATCH`: no exact match; no fixture authority.
- `AMBIGUOUS_EXACT_FULL_UTC_MATCH`: multiple exact matches; no fixture authority.

A unique exact fixture match does **not** authorize bookmaker equivalence, canonical SportyBet market/selection mapping, provider quote freshness, pricing/value, model integration, selection, ACCA/slip construction, booking code, SportyBet execution, or BET. Those remain later independent review boundaries.

If literal provider labels differ, the next step is a separately reviewed explicit alias contract. This executor never introduces fuzzy matching, case folding, participant reversal, kickoff rounding, or tolerance.

## Safety

The executor:

- adds no network client;
- does not modify provider evidence;
- rejects path traversal;
- rereads critical source bytes between source verification passes;
- requires exact source-manifest SHA-256/size equality;
- rejects duplicate FotMob capture directories;
- requires exact PR #165 `ADMITTED` disposition;
- relies on PR #164 for durable no-overwrite receipt persistence and source-aware receipt verification;
- keeps every non-fixture downstream authority false.
