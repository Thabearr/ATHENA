# Reviewed legacy expected-goals transform candidate

PR #68 freezes a research-only representation of the legacy home/away
Poisson-rate heuristic in `intelligence.match_analyst`. It is not expected-
goals approval, probability inference, or a score-matrix handoff.

The only legal input is the complete replayable PR #52 through PR #67 chain.
PR #68 revalidates PR #67 and PR #66, then takes the rebuilt exact PR #31
feature resolutions. It does not accept a naked feature snapshot, feature
dictionary, coefficient override, expected-goals value, or model choice.

## Research-only status

The sole usable result status is `AVAILABLE_RESEARCH_CANDIDATE`. It means the
exact six reviewed PR #31 features were available and the historical
mathematics was reproduced mechanically. It does not mean approved, ready,
validated, production-authorized, statistically sound, or probability-ready.

When any required feature is `MISSING` or `BLOCKED`, the result is
`BLOCKED_FEATURE_INPUTS` and carries no home or away candidate rate.

PR #68 requires all six declared PR #31 features:

- `home_form`
- `away_form`
- `home_elo`
- `away_elo`
- `fatigue`
- `live_data_freshness`

It never restores legacy substitutions such as form `0.50`, Elo `1500`, or
fatigue `0.0`. Unknown remains unknown in the reviewed path.

## Frozen legacy behavior

The transform identity is
`LEGACY_MATCH_ANALYST_POISSON_RATE_HEURISTIC_V1`. Its canonical specification
records the exact current legacy behavior:

- use form values directly by default;
- when `live_data_freshness < 0.05`, derive raw values as
  `0.50 + ((elo - 1500) / 800.0)`;
- clamp those Elo-path raw values to `[0.1, 0.9]`;
- calculate home and away bases using `1.45`, `1.25`, and fatigue coefficient
  `0.5`;
- compute `max(0.05, round(base_rate, 3))` in that exact order.

`live_data_freshness` is used only as the exact reviewed PR #31 scalar for the
historical branch condition. PR #68 does not reevaluate timestamps or source
freshness.

The output names are deliberately
`home_expected_goals_candidate` and `away_expected_goals_candidate`. They are
not validated or approved xG values.

## Explicit boundaries

Candidate rates are not permission to run `domain.score_matrix`. PR #68 does
not construct a score matrix, probabilities, prices, selections, or bets.
Every downstream execution authority is exact `false`, including
`expected_goals_transform_approved`.

The trained goals regressor is a different model family: it predicts expected
total goals from Elo, rolling xG, possession, GF, and GA inputs. PR #68 does
not load, retrain, combine with, or derive a home/away split from that model.

A later PR must validate and explicitly admit a transform before PR #67's
`BLOCKED_UNREVIEWED_TRANSFORM` condition can be lifted.

## Integrity

The artifact anchors exact PR #67 and nested PR #31 canonical identities, the
fixture/source/time identity, the canonical transform specification, and exact
per-feature status, value, blockers, and evidence hashes. Its full revalidator
replays PR #52 through PR #67, reconstructs the candidate, recomputes rates,
and compares canonical bytes. Local mutation or recomputed local hashes are
not authority.
