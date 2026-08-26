# Forward-chaining market-family calibration

## Status and roadmap boundary

Live Expansion PR **#234** implements ATHENA Phase 6 calibration on top of the
merged Goal/Score Dynamics v2 research boundary. The dated Master Expansion
Roadmap originally numbered calibration as #233, but the earlier infrastructure
hotfix shifted the live sequence by one: live #233 is Goal/Score Dynamics v2,
live #234 is forward-chaining calibration, and the Price-all Value Engine follows
as live #235.

The roadmap definition of done is explicit: calibration must be out-of-fold by
market family/regime, random-fold leakage is forbidden, and calibration identity
must be auditable. The Phase 6 exit gate is reliability + expected calibration
error (ECE), not betting ROI and not bookmaker value.

## Authority

This layer has **research calibration authority only**. It does not train or
promote a football model, ingest bookmaker prices, de-vig a market, activate a
market, route selections, build accumulators, approve production use, or grant
BET authority. Those boundaries remain downstream.

Bookmaker odds, implied probabilities, prices, offered lines, EV, Kelly, and
SportyBet popularity never enter calibrator fitting. For Total Goals and Asian
Handicap research, lines are caller-declared analytical lines only. Their
presence proves neither that a bookmaker offered the line nor that a quote
exists.

## Frozen dependencies

Calibration v1 binds the exact reviewed identities of:

- Goal/Score Dynamics evaluation contract;
- Goal/Score canonical training-view contract;
- canonical market-label registry;
- canonical market settlement semantics;
- historical label-generation contract.

The calibration contract v1 identity is:

`45c0c614ca8b26ee554cd80d94855227b9995f1b31b2a531dcd3262b667183d9`

Same-version semantic drift fails closed. Persisted calibrators are canonical
JSON, never opaque pickle/joblib estimators. The JSON payload carries all frozen
dependency identities plus its own SHA-256; load-time validation checks both the
self-hash and the currently reviewed dependency identities.

## Chronology: prediction first, calibration later

PR #234 reuses PR #233's complete-date chronological split and expanding
five-fold rolling-origin development policy. No random folds are introduced.
For each development fold:

1. fit the selected Goal/Score challenger only on rows strictly earlier than the
   validation date bucket;
2. generate validation probabilities out of sample;
3. project those probabilities into canonical market/settlement calibration
   vectors;
4. retain the fold number and the model-fit end date on every calibration row;
5. require `fit_end_date < target_match_date`.

Only those forward OOF rows may fit a calibrator.

The latest 20% complete-date terminal holdout defined by PR #233 is **never**
used to fit a calibrator. After all calibrators have been frozen from OOF
predictions, the Goal/Score model is fitted on the complete development period,
produces terminal-holdout probabilities, and the frozen calibrator is evaluated
there. A terminal-holdout row passed into calibrator fitting raises an error.

This keeps the terminal holdout as evaluation evidence rather than a hidden
calibration training set.

## Supported market families

Calibration is created only where Goal/Score Dynamics and the canonical
post-match labels support the settlement question:

- Match Result: HOME/DRAW/AWAY simplex;
- BTTS: YES/NO binary partition;
- Draw/Home/Away-or-Over-2.5: YES/NO binary partitions;
- Home/Away Win to Nil: YES/NO binary partitions;
- Double Chance: each overlapping selection is calibrated as its own YES/NO
  event, not falsely normalized against the other Double Chance selections;
- Draw No Bet: each side is a WIN/PUSH/LOSS settlement distribution;
- Total Goals: caller-declared non-negative half-goal lines, OVER/UNDER binary
  partitions;
- Asian Handicap: caller-declared quarter-goal lines, side-specific
  WIN/HALF_WIN/PUSH/HALF_LOSS/LOSS settlement distributions.

Win Either Half and Early Payout (1UP/2UP) remain blocked here. Their settlement
questions require validated Half Dynamics and Lead Path specialists respectively;
PR #234 does not manufacture those specialist probabilities from a full-time
score matrix.

## Calibration method and probability coherence

The v1 calibrator uses monotonic isotonic maps represented as explicit threshold
arrays. Sparse or degenerate components fall back to identity rather than
inventing a curve.

Binary partitions calibrate the primary event and construct the second outcome
as its exact complement. Multi-state/simplex and settlement distributions use
one-vs-rest component maps followed by deterministic renormalization, preserving
a total probability mass of one.

The output remains a correction of the supplied probability vector. It never
silently overwrites or discards the raw probability; evaluation reports RAW and
calibrated variants side by side.

## Global, competition and regime calibration

The architecture memo requires testing whether calibration should be global or
more local while avoiding tiny isolated samples. PR #234 therefore evaluates:

- `GLOBAL`;
- `COMPETITION`;
- `REGIME`;
- `HIERARCHICAL`.

Regime is the strictly pre-match Tactical Identity event environment:
LOW_EVENT, MID_EVENT, HIGH_EVENT, or UNKNOWN. Competition comes from the
canonical training row. No post-match richness class is used as a predictor of
calibration.

Global maps require at least 80 rows before an isotonic curve can replace the
identity map. Local competition/regime maps require at least 60 rows, at least
10 positive and 10 negative examples per fitted component, and at least eight
unique raw probability values. Otherwise they are absent or identity.

A local curve never stands alone. Its prediction is shrunk toward the global
parent with:

`weight = n / (n + 100)`

Hierarchical fallback order is competition+regime, competition, regime, then
global. Unknown or sparse groups therefore degrade safely to broader evidence.

## Reliability and gates

Evaluation uses fixed ten-bin classwise reliability diagnostics and reports:

- multiclass/binary log loss;
- Brier score;
- classwise expected calibration error;
- mean absolute reliability gap;
- explicit reliability bins.

The research gate compares the hierarchical calibration against the raw
probability on the untouched terminal holdout. For a family with enough data:

- classwise ECE must be non-worse than raw;
- log loss may not regress by more than 2%;
- Brier score may not regress by more than 2%.

An underpowered family is `INSUFFICIENT_SAMPLE`; it is not relabelled PASS. A
failed gate does not authorize a different downstream action or production use.

## Artifacts and offline runner

`scripts/evaluate_forward_calibration.py` consumes a canonical Goal/Score
training-view SQLite artifact and emits:

- `forward_calibration_artifact.json`;
- `forward_calibration_evaluation.json`.

Writes use an exclusive temporary file, fsync, and atomic replacement. Existing
outputs require explicit `--replace`. The runner can be restricted by
competition/date/limit for research, and those runs are marked as subsets.

The generated Goal/Score and historical source database artifacts are not stored
in Git. Consequently this PR does not claim real full-corpus calibration
performance inside hosted CI:

`FULL_CORPUS_CALIBRATION_STATUS = NOT_RUN_SOURCE_CORPORA_UNAVAILABLE`

Synthetic tests prove chronology, contracts, settlement topology, hierarchical
fallback, calibration mechanics, artifact integrity, and authority boundaries;
they are not football-performance evidence.

## Downstream boundary

The next live dependency is the Price-all / de-vig / settlement-aware Value
Engine. It may consume a valid calibrated research artifact only after the
artifact self-hash and every frozen upstream identity validate. Bookmaker quote
mapping, source age, de-vigging, fair-price comparison, and settlement-aware EV
belong there—not in calibration.
