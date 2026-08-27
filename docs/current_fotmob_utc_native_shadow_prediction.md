# Current FotMob → UTC-native shadow prediction bridge

## Purpose

PR #244 composes the reviewed current fixture bootstrap introduced by PR #243
with ATHENA's already-reviewed UTC-native successor/fresh-holdout machinery.
It deliberately does **not** create a second feature model or reinterpret live
provider scalar fields as successor inputs.

The exact path is:

`PR243 reviewed current /api/data/matches bootstrap`
→ exact raw/manifest replay
→ exact PR243 policy replay at the original review time
→ PR149 provider-native fixture qualification
→ exact PR119 historical bootstrap replay
→ reviewed fresh legacy settlements
→ existing PR149 UTC-native form/Elo/fatigue construction
→ existing PR149 frozen native/Elo/calibrated xG-rate seal
→ PR244 research/shadow handoff.

## Why provider scalar fields are not used

ATHENA's earlier semantic-equivalence review found that matching names such as
`home_form`, `away_form`, `home_elo`, `away_elo`, and `fatigue` do not prove
mathematical equivalence to the historical successor feature construction.
PR #244 therefore never treats `fixture_extended`, legacy runtime form fields,
or the PR66 provider-scalar handoff as UTC-native successor feature authority.

Every model input used by this bridge is reconstructed by the existing PR149
fresh-holdout core from strictly prior reviewed result history.

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

## History ancestry

The bridge does not accept caller-supplied feature values or a generic history
mapping. The historical state starts only from the exact PR119 projection bytes
accepted by `build_fresh_history_ledger`.

Optional post-PR119 history can enter only as exact reviewed
`SettledFreshPrediction` objects. Legacy-primary settlements are replayed
through `append_fresh_legacy_history_update`; non-legacy settlements remain
counted evidence but do not mutate the legacy feature state. Duplicate sealed
prediction identities fail closed.

## Fresh seal window

PR149's existing prospective seal rule remains unchanged:

`kickoff - 24h <= capture_observed_at <= kickoff - 60m`

with the reviewed fresh-holdout start also enforced.

A PR243 fixture whose current capture is outside this window is emitted as
`OUTSIDE_REVIEWED_SEAL_WINDOW`. It is not retrofilled from a later capture.

If reviewed UTC-native form/fatigue history is incomplete, the row remains
`MISSING_REVIEWED_FEATURES`; no default or provider scalar is substituted.

Complete cases carry the exact existing PR149 `SealedFreshPrediction` and its
canonical SHA-256.

## Authority

This bridge proves only:

- reviewed current fixture identity;
- reviewed UTC-native **research** feature construction; and
- reviewed frozen **shadow** expected-goals rate construction.

It does not authorize:

- the UTC-native successor for production use;
- ScoreMatrix;
- football market probabilities;
- Phase 6 calibrated value candidates;
- bookmaker pricing;
- market selection;
- SportyBet execution; or
- wagering.

The fresh holdout remains active. On 2026-08-27 its first count-only review
boundary has not yet occurred, so PR #244 must not manufacture production model
approval.

`wager_placed=false` throughout.

## Next boundary

`CURRENT_UTC_NATIVE_MODEL_PRODUCTION_AUTHORITY_REQUIRES_REVIEWED_FRESH_HOLDOUT_CONFIRMATION`

Once the pre-registered fresh holdout legitimately reaches and passes its
reviewed confirmation boundary, this shadow handoff is positioned to feed a
separate reviewed production-model/Phase-6 issuer without another current
fixture-identity integration rewrite.
