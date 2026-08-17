# FotMob UTC-Native Successor Feature Construction Qualification Runner

## Boundary

This PR implements the offline execution boundary pre-registered by PR #134.

It does **not** execute the preserved campaign during review and does not check in a result receipt or feature projection. It adds the deterministic runner that can later consume the exact preserved FotMob GitHub Actions artifact ZIP, re-execute the already-qualified PR #119 historical materialization, and build a new UTC-native pre-match feature projection.

The implementation stops at feature materialization. It cannot train or tune expected goals, produce a score matrix, calculate market probabilities, inspect SportyBet prices, select a market, size a stake, or authorize BET.

## Exact ancestry

The runner is stacked on the exact reviewed PR #134 head:

`fdd85d391ae0995e883e9510564a27d876d63a28`

It pins and revalidates:

- PR #134 canonical protocol SHA-256 `b3cc9a8e5ca05f199b7e404fa8288074e77d76fa5f21224c5bddb48ca1aac411` / `5,809` bytes;
- PR #134 protocol implementation Git blob `57cc133a7fb9daa76c5d5d8e9156903e583c6575`;
- PR #119 executor Git blob `2409676b4993a25024e2e8554e84e3525e7c5e6e`.

The PR #119 executor already reopens the exact preserved campaign, verifies the outer artifact and research-cache identities, revalidates the reviewed historical adapter lineage, re-derives canonical `kickoff_utc` from preserved raw FotMob evidence, checks the exact 21,326 admitted ordinary-FT rows, and emits the frozen PR #119 materialization projection.

PR #136 reuses that executor rather than creating a second 2,205-date provenance implementation.

## Input

The CLI accepts the exact preserved GitHub Actions artifact ZIP as a positional argument.

Frozen artifact identity:

- artifact ID `9249856559`;
- SHA-256 `7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f`;
- size `61,886,753` bytes.

The runner performs no network download. A wrong, truncated or replaced artifact fails inside the existing PR #119/PR #117 revalidation chain before feature construction.

## Revalidated intermediate projection

Before constructing any new features, execution must reproduce the exact PR #119 materialization projection:

- SHA-256 `e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2`;
- size `10,545,099` bytes;
- row count `21,326`.

Each line is required to be canonical JSON. The UTC-native constructor consumes only:

- source namespace;
- fixture identifier;
- canonical `kickoff_utc`;
- source-scoped home and away team identifiers;
- regulation-time home and away goals;
- evidence SHA-256;
- evidence reference.

The old PR #119 `source_local_kickoff` field is deliberately ignored and is never emitted by the new feature projection.

## UTC-native construction

Rows are sorted by timezone-aware UTC kickoff and deterministic fixture identity.

Strict prior history means exactly:

`history_kickoff_utc < target_kickoff_utc`

Fixtures sharing one exact UTC kickoff form one batch. All features for the batch are computed from the state that existed before that kickoff; result-driven state changes are applied only after every fixture in the batch has been constructed.

The exact PR #119 corpus is also required not to contain one source-scoped team in two fixtures at the same UTC kickoff. Such a collision fails closed rather than inventing an order.

## Form

For each side:

- keep source-scoped ordinary-FT history only;
- use the last five strictly prior fixtures;
- win = 3, draw = 1, loss = 0;
- `round(0.10 + ((points / (n * 3)) * 0.85), 3)`;
- no prior history → `MISSING` with value `null`;
- no default value.

## Elo

Only the **overall** pre-match rating is exported as `home_elo` / `away_elo`, matching the reviewed mathematical reference.

Unseen source-scoped teams begin at `1500` with zero matches. This remains explicitly a frozen source-native replay assumption, not observed evidence.

Expected scores are asymmetric exactly as frozen by PR #134:

- home: `1/(1+10**((away_rating-(home_rating+50))/400))`;
- away: `1/(1+10**((home_rating-away_rating)/400))`.

The +50 adjustment applies only to the home expected-score calculation.

K-factor:

- 32 before 20 matches;
- 24 before 50 matches;
- 16 thereafter.

Update:

`int(old_rating + K * (score - expected))`

There is no season reset. Same-kickoff results are batch-applied only after feature construction for the whole kickoff group.

## Fatigue

The constructor keeps each team's most recent strictly prior UTC kickoff.

When both sides have prior history:

- home rest = `(target_utc - home_last_prior_utc).days`;
- away rest = `(target_utc - away_last_prior_utc).days`;
- differential = home rest − away rest;
- fatigue = `0.30` when differential < −2, `0.10` when differential < 0, otherwise `0.0`.

If either required prior fixture is absent, fatigue is `MISSING` with no numeric value.

No local-time conversion occurs before subtraction.

## Historical freshness

Every projected row records:

`NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE`

for historical `live_data_freshness`, with numeric value `null`.

This field is not silently reconstructed and is not authorized as a historical training feature. Prospective freshness remains a separate live-input qualification/gating problem.

## Deterministic output

The feature projection is canonical newline-delimited JSON. Execution returns a receipt containing:

- exact protocol identity;
- exact PR #119/artifact lineage;
- UTC-only time-basis declaration;
- projection SHA-256 and byte size;
- row, fixture and team counts;
- same-kickoff group count;
- deterministic per-feature status counts;
- unresolved historical-freshness state;
- all downstream safety flags false.

Optional `--projection-output` writes the canonical NDJSON projection. `--output` writes the canonical qualification receipt.

## CLI

```text
python scripts/qualify_fotmob_utc_native_successor_feature_construction.py \
  /path/to/fotmob-history-campaign.zip \
  --projection-output /path/to/utc-native-features.ndjson \
  --output /path/to/qualification.json
```

No network is performed by this command.

## Qualification result vocabulary

A successful future execution returns:

`QUALIFIED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION`

with state:

`EXECUTED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION_MODEL_USE_UNREVIEWED`

That wording is deliberate: successful feature materialization is **not model approval**.

The next reviewed boundary after a successful exact execution is:

`PRE_REGISTER_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_PROTOCOL`

## Safety

Every downstream authority remains false:

- successor candidate approval;
- model training;
- expected-goals approval or production;
- score matrix;
- probability inference/adjustment;
- calibration for production;
- bookmaker pricing;
- market activation;
- selection;
- production approval;
- BET;
- successor live-input qualification.

## Review state

This PR contains the implementation runner only. No 21,326-row execution result is claimed until the exact reviewed runner is separately executed against the preserved artifact after merge/authorization.
