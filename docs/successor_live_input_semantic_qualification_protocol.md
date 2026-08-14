# Successor live-input semantic qualification protocol

## Purpose

This change pre-registers, before observing any live qualification result, the exact rules ATHENA must use to decide whether current/live PR31 model-feature values mean the same thing as the historical raw predictors used to train the successor expected-goals model.

The successor's source-bound historical evidence is strong enough to justify continuing the research chain, but a shared field name is not proof of shared semantics. PR31 `AVAILABLE` means the reviewed feature boundary has a usable supported numeric value. It does **not** by itself prove that the value was constructed using the same chronology, scale, initialization, update rule, or missing-data behavior as the historical predictor.

PR #78 is therefore a protocol only. It executes no semantic qualification, qualifies no feature, produces no expected goals, builds no score matrix, infers no probabilities, prices no market, selects no bet, and creates no production or betting authority.

## Exact ancestry

The protocol is anchored to the reviewed repository state at PR #77 main `0bca6d1bc5f156079ecdcea696a7035dc7f4fb0e` and freezes these source identities:

- PR31 fixture-model-feature contract blob: `e8d9ebf04676b54826b71752eae5aa5d23cb6caa`
- PR66 reviewed FotMob model-feature handoff blob: `e7b9adccdde32555ff1f70f1dfa37409165255f8`
- PR69 historical replay blob: `b67a7e52954f47cc90c578ad193545c541984964`
- PR72 successor protocol blob: `f0b3a070bcf235a097dd737d715f9d6162505509`
- frozen successor candidate SHA-256: `1fe9ff5f0963355bb98ae93d205a5ea3cb9aa53592601a7b06ff4000f6091660`
- PR77 robustness receipt SHA-256: `db90e0cbb1452a3267c346a190d5936d3576f20a935798e7a2b66e6c5f5c5b14`

The focused tests independently recompute the Git blob identities for the four source modules and the SHA-256 of the committed PR77 receipt, then verify that the receipt preserves the frozen successor candidate and semantic caveats.

## Successor inputs and transforms

PR31 exposes six feature IDs, but the validated successor uses only five raw inputs. `live_data_freshness` is explicitly **not** a successor predictor and is not a semantic-qualification condition for this model.

The successor predictor vector remains exactly:

1. constant intercept `1`;
2. `(home_elo - 1500.0) / 400.0`;
3. `(away_elo - 1500.0) / 400.0`;
4. `home_form - 0.5`;
5. `away_form - 0.5`;
6. raw `fatigue` with the identity transform.

Qualification applies to the meaning of the raw live feature **before** these transforms. A numerically similar value is insufficient.

## Historical form meaning

For each team at the target kickoff, historical form was built only from strictly prior source fixtures. Prior fixtures were ordered by kickoff descending and at most the most recent five were used. A win contributes 3 points, a draw 1, and a loss 0.

With `n` qualifying fixtures and `points` earned, the exact value is:

`round(0.10 + ((points / (n * 3)) * 0.85), 3)`

If no strictly prior fixture exists, form is `MISSING_PRIOR_HISTORY`; there is no default. A future live qualification therefore has to prove the same chronology, window, W/D/L weighting, scaling, rounding, and missing-history behavior.

## Historical fatigue meaning

Historical fatigue uses each team's most recent strictly prior fixture. If either team lacks prior history, fatigue is missing rather than defaulted.

The replay measures rest with the integer `.days` component of the Python `datetime` difference for each team. It then computes:

`difference_days = (target - home_last).days - (target - away_last).days`

and maps it exactly as follows:

- `difference_days < -2` -> `0.30`
- otherwise `difference_days < 0` -> `0.10`
- otherwise -> `0.0`

The orientation is home-relative. Matching one of the values `0.0`, `0.10`, or `0.30` is not enough to qualify a live fatigue feature. The future evaluator must prove the last-fixture identity, chronology/date semantics, integer-day measurement, missing-data behavior, orientation, and thresholds through reviewed replayable evidence or an exact reviewed implementation contract.

The existing factual caveat remains unchanged:

`fatigue_pr31_semantic_equivalence = UNPROVEN`

PR #78 defines what later evidence would have to prove; it does not claim that proof already exists.

## Historical Elo meaning

The historical replay uses a source-scoped chronological overall Elo state. Safe fixtures are ordered exactly by source-local kickoff ascending with fixture identifier as the deterministic tiebreak. Each unseen team starts at 1500, and the raw home/away Elo feature is the current overall rating **before** the target fixture is used to update ratings.

The exact expected-score formulas are:

`expected_home = 1 / (1 + 10 ** ((away_rating - (home_rating + 50)) / 400))`

`expected_away = 1 / (1 + 10 ** ((home_rating - away_rating) / 400))`

The home calculation therefore carries the exact +50 home adjustment while both use the 400-point logistic divisor. Observed result scores are win `1.0`, draw `0.5`, loss `0.0`.

The K schedule is exact:

- fewer than 20 prior matches -> 32;
- fewer than 50 -> 24;
- otherwise -> 16.

After a fixture the rating update is converted with Python `int(old_overall + K * (actual_score - expected_score))`. Temporal or identity ambiguity fails closed and taints dependent replay state instead of guessing an ordering or identity.

The 1500 initial state is still an assumption, not observed evidence:

`1500_REPLAY_INITIAL_STATE_ASSUMPTION_NOT_OBSERVED_EVIDENCE`

A provider value merely labelled "Elo", or one with a similar scale, is therefore not equivalent unless its derivation is proven to match this exact construction.

## Qualification vocabulary

The frozen vocabulary distinguishes four states:

- `QUALIFIED_EXACT_SEMANTIC_EQUIVALENCE`
- `UNQUALIFIED_INSUFFICIENT_PROVENANCE`
- `UNQUALIFIED_DEFINITION_MISMATCH`
- `BLOCKED_SOURCE_FEATURE_UNAVAILABLE`

This distinction prevents `AVAILABLE` from being conflated with `QUALIFIED`. It also distinguishes a known semantic mismatch from a value for which the derivation simply has not been proven.

Any future aggregate statement can mean only that all five raw successor inputs have individually proven exact semantic equivalence. It can never mean model-ready, production-ready, approved, or betting-ready.

## Evidence standard

Exact semantic equivalence requires both value-level compatibility and derivation/provenance compatibility. The protocol explicitly records the following as insufficient proof on their own:

- same field name;
- same numeric range;
- same current value;
- same source category;
- PR31 `AVAILABLE` status;
- one hand-checked fixture;
- a documentation claim without executable lineage;
- a provider calling a number "Elo";
- a fatigue value matching `0.0`, `0.10`, or `0.30` without derivation proof.

A later evaluator must use reviewed replayable evidence or an exact reviewed implementation contract. Equal values are not equal semantics.

## Deterministic artifact

Protocol identity:

`SUCCESSOR_LIVE_INPUT_SEMANTIC_QUALIFICATION_PROTOCOL_V1`

Scope:

`PRE_REGISTERED_LIVE_TO_HISTORICAL_SUCCESSOR_SEMANTIC_QUALIFICATION_ONLY`

The protocol canonicalizes as UTF-8 JSON using `ensure_ascii=False`, `allow_nan=False`, sorted keys, compact separators, and exactly one trailing newline. Its frozen canonical SHA-256 is:

`97a47d431ce57468598b17fcb24e9e0e9a41fa26c80ff1f4df9e2e611107ed7c`

Canonical size: `4,904` bytes.

The strict revalidator rebuilds the protocol and requires both the supplied object and supplied bytes to match that exact frozen contract.

## Safety

This PR is pre-registration only. Its state is exactly `PRE_REGISTERED_NOT_EXECUTED_NO_FEATURE_QUALIFIED`.

Every downstream safety flag remains exact `false`, including semantic qualification execution, all-five-input qualification, successor approval, expected-goals approval/production use, score matrix, probability inference/adjustment, production calibration, pricing, market activation, selection, production approval, and betting.

The module is inert and standard-library-only. It imports no acquisition, browser/network, score-matrix, probability/model runtime, pricing, selection, bookmaker, or betting implementation.
