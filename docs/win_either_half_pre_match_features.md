# Win Either Half pre-match feature dataset

This Stage 3 tool converts the frozen Win Either Half label dataset into a
deterministic pre-match feature table. It does not train or evaluate a model,
estimate probabilities, use bookmaker odds, or enable a betting market.

## Frozen inputs and verification

The exporter verifies the Stage 2 evidence baseline, the Stage 3 label
manifest, and the local `labels-v1.csv`. The labels file must match the
manifest's SHA-256, byte size, row count, season assignments, and split counts.
SQLite is opened read-only, and no network request is made.

The Stage 3 label manifest is fingerprinted as canonical logical JSON: parsed
JSON is serialized as compact, sorted-key UTF-8 before hashing. Its identity is
therefore independent of LF versus CRLF checkout newlines, indentation, and
object-key order. The labels CSV deliberately retains its exact raw-byte
SHA-256 and byte-size contract.

## Temporal cutoff

For a target fixture at time `T`, historical state contains only allowed-split
fixtures with kickoff strictly less than `T`. Every fixture sharing `T` is
calculated against the same earlier state; same-timestamp fixtures are added
only after the entire timestamp group has been calculated. Their file order or
fixture identity can therefore never create artificial history.

TRAIN rows can use only earlier TRAIN rows. VALIDATION rows can use earlier
TRAIN and VALIDATION rows. TEST rows can use earlier TRAIN, VALIDATION, and
TEST rows. Random splitting is forbidden, and the exporter preserves the
frozen label manifest's season-to-split assignment.

The target labels are attached after all pre-match columns are calculated.
The target fixture's FT score, HT score, half outcomes, and labels never enter
its own feature state.

## Columns and formulas

The manifest assigns every column one machine-readable role:

- `IDENTIFIER`: fixture identity and home/away team identity.
- `SPLIT_METADATA`: UTC kickoff, league, season, and frozen split.
- `PRE_MATCH_FEATURE`: values derived only from permitted earlier fixtures.
- `TARGET_ONLY`: the three frozen Win Either Half research labels.

For both target teams the dataset records:

- `prior_overall_matches`: count of all permitted earlier fixtures involving
  the team.
- `prior_relevant_venue_matches`: prior home fixtures for the target home team,
  or prior away fixtures for the target away team.
- `days_since_previous_fixture`: `(target kickoff - latest permitted earlier
  team kickoff) / 86400`; blank without prior history.
- `no_prior_history` and `days_since_previous_missing`: explicit 0/1
  availability indicators.

For the last 5 and last 10 permitted earlier fixtures, both overall and at the
relevant venue, the exporter calculates:

- `observation_count`: actual contributing rows, from 0 up to the window size.
- `goals_for_per_match`: sum of team-perspective FT goals for divided by the
  actual count.
- `goals_against_per_match`: sum of opponent FT goals divided by the count.
- `first_half_goals_for_per_match`: sum of team-perspective HT goals for
  divided by the count.
- `first_half_goals_against_per_match`: sum of opponent HT goals divided by the
  count.
- `first_half_win_rate`: first-half wins divided by the count.
- `second_half_win_rate`: second-half wins divided by the count, where each
  second-half score is FT minus HT.
- `win_either_half_yes_rate`: historical team-perspective YES labels divided by
  the count.

Incomplete windows use only actual earlier observations. A zero-observation
window records count `0` and leaves every mean/rate blank. No future-aware,
full-dataset, season-end, or silent zero imputation is used.

## Generate and verify locally

After this tooling PR is merged, generate the ignored row-level CSV and future
manifest from a clean worktree:

```powershell
python -m scripts.export_win_either_half_feature_dataset --database database/athena.db --baseline artifacts/evidence-baselines/half-time-ready-for-research.json --label-manifest artifacts/research-manifests/win-either-half-labels-v1.json --labels-input .cache/athena-research/win-either-half/labels-v1.csv --features-output .cache/athena-research/win-either-half/features-v1.csv --manifest-output artifacts/research-manifests/win-either-half-features-v1.json --expect-rows 21791
```

Verify a later committed manifest with:

```powershell
python -m scripts.export_win_either_half_feature_dataset --database database/athena.db --baseline artifacts/evidence-baselines/half-time-ready-for-research.json --label-manifest artifacts/research-manifests/win-either-half-labels-v1.json --labels-input .cache/athena-research/win-either-half/labels-v1.csv --check artifacts/research-manifests/win-either-half-features-v1.json
```

The future manifest fingerprints frozen evidence and label identities, the
input label CSV, output feature CSV, schema, split counts, generator revision,
and market safety. It proves deterministic reproduction of those inputs, not
provider correctness, feature usefulness, predictive performance,
calibration, or betting value. Simple historical form features omit many
pre-match factors and are not evidence that a deployable model exists.

Both Home and Away Win Either Half markets remain `DISABLED`.
