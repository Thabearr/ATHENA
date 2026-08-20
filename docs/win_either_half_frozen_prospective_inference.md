# Frozen Win Either Half prospective analytical inference

## Boundary

This boundary makes `HOME_WIN_EITHER_HALF` and `AWAY_WIN_EITHER_HALF`
analytically callable for a future fixture. It packages the model decisions
already reviewed in Stage 4A/4B; it does not select another model, tune a
coefficient, or use full-time win probability as a proxy.

The exact execution chain is:

```text
qualified completed fixtures strictly before target kickoff
  -> frozen 74-feature prospective builder
  -> TRAIN medians, means, and scales
  -> TRAIN-fitted logistic_l2_c0.1_v1 Home/Away models
  -> Home isotonic_calibration_v1 / Away identity_calibration_v1
  -> canonical Home/Away YES and NO analytical probabilities
```

The public predictor accepts only the exact 74-feature mapping. It loads the
exact committed model state internally and accepts no state, coefficient,
calibrator, price, or authority override. Runtime inference uses only the
Python standard library and performs no fitting.

## Exact reviewed ancestry

The deterministic exporter verifies the ignored frozen research files before
constructing state:

| Evidence | SHA-256 | Rows |
| --- | --- | ---: |
| Stage 3 feature CSV | `68547ae9670703c59d68367d8fa1ef067e7410d8beb842ad0aec2151f0777e7b` | 21,791 |
| Stage 4 benchmark summary | `e6c2157f137a7d243f38d3a55a087e9b2ab9cb2536ab2a1544e1125362c9253f` | — |
| Stage 4 predictions | `02790fdb2c4549adb27d3a086d522491215ac7a2b9889375208cae96f32873a1` | 43,582 |
| Stage 4B calibration summary | `957ffb850354173f84f1f3b44e8e5bff83c74357bdebc90c091c1f5ca997dfda` | — |
| Stage 4B calibrated predictions | `6e931ae156f7319bc9cba2647e746471422adafad8e431981bdb573ca64c44d4` | 36,318 |

Reconstruction refits the two frozen base configurations on exactly 14,267
TRAIN rows, reproduces every recorded Stage 4A probability, reconstructs the
10,635-row expanding-temporal OOF calibration fit for each target, and
reproduces every recorded Stage 4B OOF, validation, and independent final-test
base/calibrated probability. VALIDATION and FINAL_TEST labels are never used to
fit the deployed base state.

After serialization, the exporter also runs the deployed stdlib calculation,
not the sklearn objects, across the frozen rows. It requires exact 12-decimal
parity for the final TRAIN-state base probability on all 21,791 rows and for
the selected calibrated probability on every validation/final-test row. For
the 10,635 OOF rows per target, which necessarily came from fold-specific base
models, it applies the deployed calibration primitive to the recorded OOF base
probability and requires exact calibrated parity. This keeps the OOF ancestry
honest while proving the serialized preprocessor, dot-product association,
sigmoid, and isotonic/identity runtime state.

The stdlib numerical path deliberately reproduces two Stage 4 implementation
details that can affect the twelfth decimal: the single-threaded BLAS
five-term dot-product association and the frozen array-rounding/expit policy.
Algebraically equivalent `fsum`, negative-logit sigmoid, or direct Python
`round(value, 12)` implementations are rejected when they drift from the
recorded canonical probability.

The committed state is
`artifacts/model-states/win-either-half-analytical-inference-v1.json`:

- canonical byte size: 23,968;
- artifact SHA-256: `2b2490f7270b6e69646bba59c4979cc6f2cc462b3e9ef2a745583d9fa00a4cd2`;
- internal state fingerprint: `7604203a4273e0428190ce37447437016c7a081d14e4fba8b7d16f44ec590d5b`.

It contains only ordered model/preprocessor/calibrator state and provenance,
not row-level historical training data. `scripts/export_win_either_half_inference_state.py
--check` reconstructs the state from the exact ignored evidence and requires
byte equality.

## Prospective feature semantics

`build_prospective_win_either_half_features` is separate from the reviewed
research-row builder. The research path and its target/split columns are not
weakened. The prospective path accepts an upstream-qualified target identity
and completed HT/FT fixtures, then:

- includes only fixtures with `history.kickoff_utc < target.kickoff_utc`;
- never requires or accepts a target result or target label;
- derives first-half, second-half, and either-half indicators from historical
  HT/FT scores;
- uses the same overall and relevant-venue windows of 5 and 10;
- retains the same no-history and days-since missing indicators;
- preserves `None` for the fields the TRAIN median imputer owns;
- emits exactly the manifest-frozen 74 predictors in manifest order.

Fixtures at the target kickoff or later cannot leak. Duplicate identities and
ambiguous same-team/same-kickoff history fail closed.

## Specialized capability namespace

WEH does not consume the generic six `ModelFeatureId` inputs used by
ScoreMatrix markets. The model registry therefore declares
`SPECIALIZED_WEH_PRE_MATCH_FEATURES` with the exact 74-feature tuple.

The older reviewed-match-details readiness boundary owns only
`GENERIC_FIXTURE_MODEL_FEATURES`. It reports the specialized namespace as
`BLOCKED_INPUT_NAMESPACE_NOT_OWNED`; it does not pretend six generic features
establish WEH readiness. The ScoreMatrix projector likewise does not project
WEH.

Both WEH markets are `EXPERIMENTAL` analytical capabilities with ordinary
YES/NO event settlement. Stage 4B calibration is frozen research evidence, not
fresh bookmaker/value confirmation.

New half-time evidence baselines use schema v2. They record the truthful
current `EXPERIMENTAL` maturity and independently record pricing and selection
authority as `NOT_AUTHORIZED`. The already-committed schema-v1 baseline and
its descendant research receipts retain their historical `DISABLED` bytes;
those bytes are reconstructed only by the explicit version-aware verification
path. New baseline generation cannot emit the legacy projection.

## Authority

This change authorizes analytical prediction only. The artifact, prediction,
registry, old runtime, and documentation all keep these authorities false:

- pricing;
- value;
- selection;
- production approval;
- BET.

No bookmaker odds are accepted. No SportyBet freshness, de-vig, edge, Kelly,
or bet construction is added. The final 15-market orchestrator remains a
separate boundary.
