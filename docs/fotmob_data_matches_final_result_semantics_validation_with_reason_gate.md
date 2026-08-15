# FotMob final-result semantics validation with reviewed reason gate

PR #92 executes the frozen PR #83 final-result semantics contract only on the
ordinary `FT` subset cleared by merged PR #91.

It is evidence-only. It does not promote the source capability, does not infer
regulation-time or extra-time score meaning, does not interpret penalty scores,
and does not authorize modelling, pricing, selection, production, or betting.

## Exact ancestry

Execution starts from merged main:

```text
50025517298ff5a05fdb708396b12f216f2e7e1e
```

and binds:

```text
PR83 protocol blob        25f8045524badcb90239df59ac9c47f36fcffe34
PR89 implementation blob  f33dd31aedcd92b5691a3503914ed184d601b493
PR90 protocol blob        f9546ff05cddfe366d278d4dbdf1020bb7666951
PR91 validation blob      a663a2c2879cb70dbd1f31f0f8bbe4ff8f1034d6
source-capability blob    ffd9730d6675a7dbcc9e8622d6e9844b772b6f96
```

The frozen PR #83 protocol identity remains:

```text
SHA-256  572dde2f5ba8e68c96188ec2df3cc1fdcfa554aa1023aa56e8b8f8b225d7194b
size     3995 bytes
```

The exact merged PR #91 receipt remains:

```text
SHA-256  3e8537a4ddfd2d558a493ace74bd302a7d9f835c4768dc05049682e8ddf94abf
size     3307 bytes
```

## Exact evidence input

The preserved PR #85 pair remains:

```text
request identity  20260814 / UTC / NGA
capture A         a18e843fabe5aca74846b160
capture B         e28d9ce746c1ef9102995517
separation        310.605739 seconds
```

PR #91 already revalidates the complete structural chain and independently
reconstructs 29 stable finished identity-and-score pairs. Its reviewed reason
gate produces:

```text
28  QUALIFIED_PR83_REASON_GATE_ORDINARY_FT_SOURCE_LABEL
1   BLOCKED_PENALTY_REASON_REQUIRES_SEPARATE_SCORE_SEMANTICS
0   other reason blockers
```

PR #92 therefore admits exactly those 28 ordinary candidates into the frozen
PR #83 final-result semantics decision. The penalty fixture `5844873` remains
outside the execution input.

## Qualification result

All 28 execution inputs satisfy the remaining frozen PR #83 requirements and
receive:

```text
QUALIFIED_STABLE_SOURCE_FINISHED_SCORE_SEMANTICS
```

The exact execution summary is:

```text
stable finished identity/score pairs     29
PR91 ordinary-FT reason-qualified         28
PR91 penalty blocked                       1
PR92 final-result execution inputs        28
PR92 qualified source-finished scores     28
PR92 non-qualified execution inputs        0
```

This qualification has only the semantic scope frozen by PR #83:

```text
QUALIFICATION_MEANS_SOURCE_REPORTED_FINISHED_SCORE_ONLY_NOT_REGULATION_TIME_EXTRA_TIME_PENALTIES_OR_SETTLEMENT_SEMANTICS_BEYOND_THE_SOURCE_FIELDS
```

It therefore does **not** establish regulation-time score, extra-time score,
penalty score, winner/loser settlement, or bookmaker-settlement semantics.

## Capability remains unchanged

The reviewed source registry still says:

```text
source               fotmob_data_matches_reviewed_catalog
full_time_score      NOT_CAPTURED
historical_coverage  UNKNOWN
```

PR #83 explicitly did not authorize a source-capability update, so PR #92 does
not modify `domain/source_capabilities.py` or reinterpret `NOT_CAPTURED` as
`CONFIRMED` merely because a narrow evidence subset now has reviewed semantics.

A separate pre-registered promotion boundary is required.

## Canonical receipt

```text
dataset     athena-fotmob-data-matches-final-result-semantics-with-reviewed-reason-gate-v1
state       EXECUTED_28_ORDINARY_FT_SOURCE_FINISHED_SCORE_SEMANTICS_QUALIFIED
SHA-256     b821d5211de1e2a058b85ac1ca2ac50bdd0d3b577b54aa40c86ed6773bcb0c86
size        3561 bytes
```

All authority flags remain exact `false`.

## Next boundary

```text
PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_FULL_TIME_SCORE_CAPABILITY_PROMOTION_PROTOCOL
```

That later protocol must decide whether, and under exactly what restricted
conditions, the reviewed source registry may move `full_time_score` away from
`NOT_CAPTURED`. It must not silently absorb the blocked penalty fixture or claim
historical coverage.
