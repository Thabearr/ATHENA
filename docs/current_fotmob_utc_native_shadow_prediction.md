# Current FotMob → UTC-native shadow replay bridge

## Purpose

PR #244 composes the reviewed current fixture bootstrap introduced by PR #243
with ATHENA's already-reviewed UTC-native successor/fresh-holdout machinery.
It deliberately does **not** create a second feature model or reinterpret live
provider scalar fields as successor inputs.

The exact replay path is:

`PR243 reviewed current /api/data/matches bootstrap`
→ exact raw/manifest replay
→ exact PR243 policy replay at the original review time
→ PR149 provider-native fixture qualification
→ exact PR119 historical bootstrap replay
→ supplied reviewed fresh settlements
→ existing PR149 UTC-native form/Elo/fatigue construction
→ existing PR149 frozen native/Elo/calibrated xG-rate seal
→ PR244 research/shadow replay handoff.

## What a replay does and does not prove

A returned PR149 `SEALED_COMPLETE_CASE` means the **supplied reviewed history
inputs** contain every feature required by the frozen PR149 constructor and that
the resulting seal reconstructs exactly.

It does **not** mean that those supplied inputs are the complete current PR151
campaign history.

The active PR151 collection runner rebuilds its model history on every tick from
the complete cumulative `settlement-journal.ndjson`. PR #244 currently accepts a
tuple of reviewed `SettledFreshPrediction` objects and can validate every member,
but it has no proof that the caller supplied every committed legacy settlement
from the active durable campaign prefix.

For that reason every PR #244 handoff fixes:

`current_fresh_history_prefix_complete = false`

and research evidence fixes:

`complete_current_fresh_history_prefix = false`.

Neither claim can be relabelled to true through `dataclasses.replace`.

## Why provider scalar fields are not used

Matching names such as `home_form`, `away_form`, `home_elo`, `away_elo`, and
`fatigue` do not prove mathematical equivalence to the reviewed UTC-native
successor feature construction. PR #244 therefore never treats
`fixture_extended`, legacy runtime form fields, or the PR66 provider-scalar
handoff as UTC-native successor feature authority.

Every feature value emitted by a PR #244 replay is reconstructed by the existing
PR149 fresh-holdout core from the exact reviewed history inputs supplied to the
replay.

## Exact current-source ancestry

The bridge accepts an exact `ReviewedFixtureIntelligenceBootstrap`, exact raw
`/api/data/matches` bytes, and the exact reviewed capture manifest.

Before any shadow feature work it:

1. proves the raw SHA against the manifest;
2. rebuilds the reviewed fixture candidate bundle from those exact bytes;
3. requires that candidate-bundle SHA to equal the current bootstrap ancestry;
4. re-runs the frozen PR243 fixture policy at the bootstrap's exact review time;
5. requires the resulting review-bundle SHA and approval count to equal the
   bootstrap ancestry; and
6. re-runs PR149 provider-native identity qualification from the same raw bytes.

A bootstrap cannot therefore be relabelled onto a different current capture.
The handoff also retains its exact supplied source bundle in memory and
reconstructs detached digests and rows during validation.

## Supplied history ancestry

Historical state starts only from the exact PR119 projection bytes accepted by
`build_fresh_history_ledger`.

Post-PR119 history can enter only as exact reviewed `SettledFreshPrediction`
objects. Legacy-primary settlements are replayed through
`append_fresh_legacy_history_update`; non-legacy settlements do not mutate the
legacy feature state. Duplicate sealed-prediction identities fail closed.

This establishes integrity of the **supplied** history inputs, not completeness
of the active PR151 durable prefix.

## Fresh seal window

PR149's existing prospective seal rule remains unchanged:

`kickoff - 24h <= capture_observed_at <= kickoff - 60m`

with the reviewed fresh-holdout start also enforced.

A PR243 fixture whose current capture is outside this window is emitted as
`OUTSIDE_REVIEWED_SEAL_WINDOW`. It is not retrofilled from a later capture.

If supplied reviewed UTC-native form/fatigue history is incomplete, the row
remains `MISSING_REVIEWED_FEATURES`; no default or provider scalar is
substituted.

## Research evidence and authority

The handoff may record factual research evidence that:

- reviewed current fixture identity was replayed;
- supplied reviewed history inputs were replayed;
- the existing UTC-native research feature constructor ran; and
- the existing frozen shadow xG-rate constructor ran.

It simultaneously records that complete current fresh-history prefix evidence
has **not** yet been proven.

Every downstream authority remains exact `false` for:

- production model;
- ScoreMatrix;
- football market probability;
- Phase 6;
- pricing;
- selection;
- SportyBet execution; and
- BET/wager placement.

`wager_placed=false` throughout.

## Next boundary

`CURRENT_DURABLE_FRESH_HISTORY_PREFIX_BINDING_REQUIRED`

The next reviewed PR should consume an exact cumulative PR151 **success** archive
plus its canonical tick receipt, revalidate the active committed journal prefix,
prove schedule/checkpoint/settlement completeness up to the applicable current
source observation, and derive every reviewed legacy history update from that
verified durable prefix.

It must reuse the existing PR151 journal semantics and PR168 archive/receipt
transport commitments rather than inventing another history authority.

Only after that boundary can ATHENA claim a complete-current-history shadow
replay. Even then, production model/ScoreMatrix/Phase-6 authority remains
separately time-gated by the reviewed fresh-holdout confirmation process.
