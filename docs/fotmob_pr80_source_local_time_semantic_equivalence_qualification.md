# FotMob → PR80 source-local time semantic-equivalence qualification

## Result

PR #121 executes the exact PR #120 protocol and **fails closed at the first semantic gate**.

Qualification state:

`EXECUTED_FAIL_CLOSED_PR69_REFERENCE_TIME_BASIS_UNRESOLVED`

Primary status:

`BLOCKED_PR69_REFERENCE_TIME_BASIS_UNRESOLVED`

This is an evidence result, not a football-result failure and not a claim that FotMob's `Europe/Oslo` representation is incorrect.

## Exact ancestry

Execution is anchored to `main`:

`cadd32bb3d5241afbbb0b9c36326b6ddad820400`

It revalidates the PR #120 protocol:

- protocol ID `REVIEWED_FOTMOB_PR80_SOURCE_LOCAL_TIME_SEMANTIC_EQUIVALENCE_PROTOCOL_V1`;
- implementation blob `e07616e99c0beaf2a95bcaec96d02616b21c378f`;
- canonical SHA-256 `a938ee4ea45c427c5396fe063af4efd2341a9c8e8ffccc1105aa7bdffdbb2918`;
- canonical size `5,242` bytes.

The canonical PR #121 receipt is:

- SHA-256 `8d057e96504a83237b719b3a465e29b7df74e2b6c3630fc1d97e8a2a7bdfb5fb`;
- size `3,599` bytes.

## Why execution stops here

PR #120 deliberately requires one of two things **before** row-level time semantics can be qualified:

1. resolve the PR #69 source-local time basis to a deterministic reviewed rule; or
2. provide a formal source-independent invariance proof whose assumptions are themselves proven for the frozen scope.

The frozen PR #69 reference remains:

`SOURCE_LOCAL_TIMEZONE_UNRESOLVED`

PR #80 still requires:

`SOURCE_LOCAL_NAIVE_DATETIME_REQUIRED_FOR_PR78_PARITY`

The frozen FotMob candidate remains `Europe/Oslo`, and PR #119 still says its PR #80 semantic equivalence is `UNPROVEN`.

This execution supplies the exact PR #120 protocol, but it supplies **no admissible reference-basis evidence bundle** and **no formal source-independent invariance proof bundle**. Therefore the protocol's first semantic gate cannot pass.

## Why the campaign is not re-executed in this PR

Re-running all `21,326` historical rows cannot resolve an unknown reference definition by itself. PR #120 explicitly forbids treating equal observed ordering or equal numeric feature output as sufficient semantic proof.

The row-level gates are therefore correctly marked `NOT_REACHED` rather than being evaluated against an unresolved reference:

- FotMob `Europe/Oslo` admissibility;
- strict-prior membership;
- form ordering;
- Elo ordering;
- most-recent prior fixture selection;
- integer `.days` rest components;
- home-minus-away rest difference and fatigue bucket;
- zero unresolved temporal ambiguity.

This prevents result-driven timezone inference.

## What this does **not** mean

PR #121 does **not** prove that `Europe/Oslo` differs from the old football-data.co.uk source-local wall clock. It also does not prove equivalence.

It makes the narrower statement that the exact positive proof required by PR #120 is not present in this execution.

No cross-source fixture or team identity inference is used to hide the missing time-basis evidence.

## Frozen scope

The blocked qualification remains limited to the PR #119 corpus:

- exactly `21,326` materialized ordinary-FT history rows;
- historical ceiling `2026-08-14`;
- exactly the currently validated eleven historical/model league codes `B1`, `D1`, `E0`, `F1`, `G1`, `I1`, `N1`, `P1`, `SC0`, `SP1`, `T1`.

Those eleven codes are **not** ATHENA's complete competition universe.

## Safety state

All downstream authority remains false, including:

- source-local time semantic equivalence qualified;
- PR #80 constructor input authorized;
- successor live inputs qualified;
- successor candidate approved;
- model training authorized;
- expected-goals production authorized;
- score matrix authorized;
- probability inference/adjustment authorized;
- calibration for production authorized;
- pricing authorized;
- market activation authorized;
- selection authorized;
- production approval authorized;
- BET authorized.

## Next boundary

The blocker is now isolated to the missing reference definition. The next exact boundary is:

`PRE_REGISTER_REVIEWED_PR69_SOURCE_LOCAL_TIME_BASIS_RESOLUTION_PROTOCOL`

That protocol should freeze, before acquiring or interpreting evidence, what can resolve the PR #69 wall-clock basis and what formal invariance route is admissible if a direct source definition cannot be recovered.
