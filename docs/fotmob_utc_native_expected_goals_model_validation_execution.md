# FotMob UTC-native expected-goals model-validation execution

## Boundary

PR #145 installs the reviewed one-shot control plane for the source-bound model-validation implementation merged in PR #142 and pre-registered in PR #140.

**PR #145 review and merge do not execute the study.** The real fit/evaluation requires a later explicit owner comment on the already merged and closed PR #145. Merge authorization and execution authorization remain separate boundaries.

This lane is research-only. It does not invoke ScoreMatrix, derive market probabilities, inspect bookmaker prices, choose selections, write a production model artifact, or authorize production/BET use.

## Exact reviewed implementation

The execution workflow checks out the exact owner-authorized current `main` and fails closed unless these reviewed Git blobs are unchanged:

- projection evaluator: `0421506b9e6e398c3469bb69196ef8fcad04f2a5`
- source-bound evaluator: `89cbe2e948c4f69339c89df00db0282e14b955e8`
- CLI: `d3dddecbd66b79887aef547abcd048f40a57e2a8`
- PR #140 protocol: `1780330c4d0ab9140f0b2f6c776dfe79073ca7f8`
- reviewed deterministic historical fitter seam: `28e33a625c02c7f005232d6c5d05d6a0a52397b7`
- `requirements.txt`: `54d24a55dfa4c73ba3910d333257cfd2e68daf4b`

The workflow also requires the exact successful V2 feature-qualification result receipt on PR #139, comment `5311318782`, from run `31990121181`.

## Exact source evidence

The only accepted input is the preserved V2 feature-qualification artifact:

- artifact ID: `9275052993`
- name: `fotmob-utc-native-feature-qualification-v2-31990121181`
- size: `23,349,191` bytes
- SHA-256: `f69ffad8f47faadb3ec743c96efa35fb6f4b43776a7650cf0414fb40455d29eb`
- source run: `31990121181`
- source head: `cd67be14f6a4f09484d18a57de360b8a5d4c51d7`
- projection member: `utc-native-feature-projection-v2.ndjson`
- projection size: `23,342,076` bytes
- projection SHA-256: `5519ef40db3efc678c9eef73046c0e577e5f33a85f11b3fe043fc22bca2fcfed`
- projection rows / unique fixtures: `21,326 / 21,326`
- identity/lineage conflicts: `0`

Artifact metadata is re-read from GitHub immediately before download. The downloaded ZIP bytes are then rehashed before the source-bound validator is allowed to run.

## One-shot authorization

After PR #145 has been reviewed, explicitly merged, and verified, the owner command is exactly:

```text
/athena-run-fotmob-utc-native-expected-goals-validation
main-sha: <exact-current-main-sha>
confirm: EXECUTE_REVIEWED_21129_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION
```

The workflow requires:

- PR #145 already merged and closed;
- command author exactly `Thabearr`;
- exact three-line framing;
- exact lowercase 40-hex current `main` SHA;
- current default branch equal to that requested SHA;
- exact successful upstream V2 result receipt still present;
- no earlier model-validation attempt marker.

Before checkout or fitting, it creates:

`<!-- ATHENA_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_ATTEMPT -->`

Once the attempt marker exists, the attempt is spent. A failed, interrupted, or partially completed run must be reconciled from its preserved evidence before any new execution boundary is defined. It must not be replayed automatically.

## Exact offline execution

The reviewed command is:

```text
python -m scripts.validate_fotmob_utc_native_expected_goals_model \
  fotmob-utc-native-feature-qualification-v2.zip \
  --predictions-output fotmob-utc-native-xg-validation-predictions.ndjson \
  --receipt-output fotmob-utc-native-xg-validation-receipt.json
```

The validator itself performs no network acquisition. GitHub network access is used only by the execution control plane to retrieve the already-preserved exact Actions artifact.

The study keeps the frozen PR #140 population:

| Population | Rows | Membership SHA-256 |
|---|---:|---|
| Complete cases | 21,129 | `1374fd323bd5aa7e6da6cee23358621c26435297c2e195553e227373008fd8ed` |
| Train | 14,181 | `4c017b9e43ab9e2f231e88187339a3960c5fdfbd087f21ba92ca8855576219a9` |
| Evaluation A | 3,471 | `4361cd60976170bd14442502025160d9b3aa97717fb94afc1b68eee9b88c429f` |
| Evaluation B | 3,477 | `4910b5db577bd87fd4bed4e24f3b1e00dff85d58f23e7ea8558cfba0aa5efd59` |
| Pooled A+B | 6,948 | `f4d713a739feeac90c166f5125dd80ab7e3063598f9ad0187f07d10b88e5bcdc` |

Exactly 197 qualified projection rows remain excluded rather than imputed.

Exactly five reviewed arms are evaluated:

1. `FOTMOB_NATIVE_SAME_FAMILY_REFIT`
2. `HISTORICAL_FIXED_COEFFICIENT_TRANSFER`
3. `FOTMOB_NATIVE_ELO_ONLY_NESTED_GLM`
4. `FOTMOB_NATIVE_NO_FATIGUE_ABLATION`
5. `TRAIN_ONLY_GLOBAL_HOME_AWAY_MEAN_BASELINE`

## Result verification

A runner exit code of zero is not sufficient by itself. The workflow independently verifies the canonical source-bound receipt and prediction bytes.

It requires:

- source-bound ID `FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_SOURCE_BOUND_V1`;
- implementation state `IMPLEMENTED_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION`;
- `research_training_executed = true`;
- `automatic_model_approval = false`;
- validation state exactly one of the two reviewed `...REVIEW_REQUIRED` states;
- exact source artifact and projection ancestry;
- exact complete-case, train, Evaluation A, Evaluation B and pooled membership identities;
- every model arm evaluated on the same frozen evaluation membership;
- exactly 6,948 canonical prediction rows, with 3,471 A rows and 3,477 B rows;
- exact five-model prediction set on every prediction row;
- all required paired NLL deltas;
- strong/weak state consistent with the exact strong-signal boolean checks;
- nine UTC-quarter jackknife groups with frozen counts `626, 1017, 1073, 755, 599, 1020, 1097, 721, 40`;
- competition robustness still `BLOCKED_PROJECTION_DOES_NOT_CARRY_COMPETITION_IDENTITY`;
- `cross_runtime_bit_identity_claimed = false`;
- `known_pr77_machine_precision_canonicalization_gap_cleared = false`;
- every downstream authority flag exact `false`.

A strong study result is therefore still only evidence requiring review. It does not silently promote the model.

## Preserved evidence

The workflow packages evidence even when the validator fails where possible. The 30-day Actions artifact is named:

`fotmob-utc-native-expected-goals-validation-<run-id>`

It contains the execution metadata, runner log, canonical result receipt and predictions where produced, source-artifact digest/size proof, an all-false research execution envelope, and a SHA-256 file manifest.

The wrapper result states are:

- success: `EXECUTION_COMPLETED_REVIEWED_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_EVIDENCE_PRESERVED`
- incomplete/failure: `EXECUTION_NOT_QUALIFIED_REVIEW_MODEL_VALIDATION_ARTIFACT_BEFORE_ANY_RETRY`

A result comment is emitted only after an attempt marker exists. Failure means inspect the preserved artifact before defining any new attempt.

## Authority after execution

Even a fully verified successful run advances only to:

`REVIEW_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_RESULT`

No ScoreMatrix, probability, pricing, selection, production, or BET authority is granted by PR #145, by the execution wrapper, or by a strong validation state itself.
