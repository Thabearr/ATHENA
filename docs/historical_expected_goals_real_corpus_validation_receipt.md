# Historical expected-goals real-corpus validation receipt

This document records the first exact real-corpus execution of the deterministic
PR #70 historical expected-goals component evaluator.

It is a **research execution receipt**, not a production-model approval and not
a replacement for the PR #69 raw source evidence. The full PR #69 and PR #70
revalidators were executed against official football-data.co.uk bytes on an
ephemeral GitHub-hosted runner. The resulting source and validation hashes are
committed so later work cannot silently change the evidence that motivated the
next modelling step.

## Exact execution ancestry

The execution checked out repository main at:

`d507c0ca6515cfa5ffbda6c26f388ec64e5c2f5f`

A disposable branch-only Actions workflow ran as:

- workflow run: `31683073429`
- job: `94392777855`
- research branch head: `04b7a3443bf4d5b43dc47b3f3afe333e15c51fb2`

The official source download reproduced the reviewed PR #69 source receipt
exactly:

- 66 CSV files
- 10,006,877 source bytes
- 21,226 parsed fixtures
- source-corpus SHA-256:
  `c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0`
- PR #69 canonical replay SHA-256:
  `b44166b9543a8f436e62a644efc5316ad12fcc260a4c2c5908ad112928bedfe3`
- PR #69 canonical replay size: 39,952,730 bytes

Both the PR #69 full source replay revalidator and PR #70 full validation
revalidator succeeded before the metrics were recorded.

The resulting PR #70 validation artifact is anchored as:

- SHA-256:
  `c13287a28ac1ffc1bfc02b1ea283c34840a7a00eb14ec13cac39ca67c14ab5e5`
- canonical size: 20,902 bytes
- target transform:
  `LEGACY_MATCH_ANALYST_POISSON_RATE_HEURISTIC_V1`
- target transform-spec SHA-256:
  `e7a5959eef21be51a45e79da1aa174b164504223ed45774d32b23eb073b3716c`
- validation specification:
  `HISTORICAL_EXPECTED_GOALS_COMPONENT_VALIDATION_SPEC_V1`
- validation-spec SHA-256:
  `3e4380fa5456e212bbdc422d0b1310ba8a8daf792a38666796f349e096378ce1`

Historical `live_data_freshness` remains unreconstructed. The FORM and ELO
branches are still counterfactual component evaluations, not reconstructed
historical switch states.

## Result

Both frozen PR #68 formula components contain broad retrospective predictive
signal on the 21,033 fixtures eligible for each branch.

### FORM component

Mean joint Poisson NLL: `2.994657343211276`.

Against the frozen PR #68 constant baseline (`3.0478626092896053`), FORM
improves NLL by `-0.053205266078329316`.

Against the strict pre-match rolling league baseline (`3.0425180023049267`),
FORM improves NLL by `-0.04786065909365078`.

FORM beats both baselines in every one of the six recorded seasons and all
11 identity leagues.

### ELO fallback component

Mean joint Poisson NLL: `2.9782107989272695`.

Against the frozen constant baseline, ELO improves NLL by
`-0.06965181036233581`.

Against the rolling league baseline, ELO improves NLL by
`-0.06430720337765727`.

ELO also beats both baselines in all six seasons and all 11 identity leagues.
Its aggregate mean NLL is lower than FORM by `0.016446544284006492` when
reported as FORM minus ELO. This is descriptive evidence only; the receipt does
not convert that difference into a formal superiority claim.

## Calibration warning

The predictive signal is not sufficient for production use.

The ELO branch materially underpredicts high-scoring states. In the populated
home predicted-rate bucket `[1.5, 2.0)`, 6,533 fixtures average approximately
`1.611` predicted home goals versus `2.060` observed, an error of
`-0.4490093372110824` goals. In the analogous away bucket, 1,770 fixtures
average approximately `1.583` predicted versus `2.080` observed, an error of
`-0.4963830508474576`.

FORM also has systematic home underprediction, including `-0.3335` goals in
its populated `[2.0, 2.5)` home bucket.

Therefore the correct conclusion is:

- FORM shows strong signal for further research;
- ELO shows stronger broad signal and is the preferred legacy component for
  the next modelling investigation;
- neither branch is calibrated well enough to approve the legacy PR #68
  transform as a production goal model;
- the historical freshness switch remains unavailable and cannot be inferred
  from these results;
- no score matrix, market probability, price, value, selection, or bet is
  authorized by this receipt.

## Why the receipt is committed

PR #70 deliberately did not persist a real-data output. Once the exact
real-corpus execution became available, this small canonical receipt was added
to preserve the evidence that will guide subsequent model research without
checking 40 MB of replay JSON or 10 MB of raw source CSV into the repository.

The receipt itself does **not** prove the underlying raw bytes. Its trust anchor
is the exact PR #69 source-corpus SHA and the exact PR #70 validation SHA. Full
reproduction still requires the 66 raw source files and the merged PR #69/#70
revalidators.

All safety flags in the committed receipt are exact `false`.
