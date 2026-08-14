# Reviewed FotMob data-matches terminal-state schema-extension protocol

## Purpose

PR #86 pre-registers the **structural** extension required after PR #85 exposed
terminal/live `/api/data/matches` fields that were absent from the frozen PR #39
review capture.

This PR does not implement the extension and does not reinterpret the new field
names. It freezes the exact allowed key sets, type/nullability domains,
fail-closed outcomes, ancestry, and safety boundaries **before** an
implementation is allowed to accept those fields.

Protocol state:

```text
PRE_REGISTERED_NOT_IMPLEMENTED_NO_TERMINAL_STATE_SCHEMA_EXTENSION_QUALIFIED
```

No final-result semantics, source-capability promotion, source-history approval,
successor-model authority, probability inference, pricing, selection,
production, or betting authority is created.

## Exact ancestry

PR #86 starts from merged PR #85 main:

```text
4dc04a8856a01d5756bf992887df2553928c48a4
```

It binds the exact PR #85 evidence module:

```text
blob       7b74e9893071ef47ea425b4f106d92b0c5e1ddc2
SHA-256    a181e40c1264eecf6c9da897d826131c48177168e5592a64caa211ce64dacf02
size       3921 bytes
```

and the frozen PR #39 schema implementation:

```text
blob       4dfff0eb05335895c3ee0fcaa7b8da1299ea692f
```

PR #85 froze the next boundary as:

```text
PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_TERMINAL_STATE_SCHEMA_EXTENSION
```

PR #86 performs only that pre-registration.

## Why this extension is separate from PR #39

PR #39 is deliberately kept immutable. Its v1 schema was reviewed against a
different evidence shape and remains an important frozen ancestry boundary.

PR #86 therefore requires the future implementation to be a **separate additive
reviewed layer**. It must not silently enlarge the PR #39 v1 allowed-key sets.

The existing PR #39 base contract remains:

```text
team:
  id
  longName
  name
  score

status required:
  cancelled
  finished
  halfs
  periodLength
  started
  utcTime

status optional:
  aggregatedStr
  reason

status.halfs:
  firstHalfStarted
```

All existing PR #39 top-level, league, match, identity, kickoff, strict-JSON,
duplicate-key, and capture-lineage validation remains in force.

## Pre-registered optional extension keys

The only team-level additions permitted by this protocol are:

```text
penScore
redCards
```

The only status-level additions are:

```text
awarded
liveTime
numberOfAwayRedCards
numberOfHomeRedCards
ongoing
scoreStr
```

The only `status.halfs` addition is:

```text
secondHalfStarted
```

Every extension key is **optional**. None may become a new PR #39-style base
required field merely because it appeared in the PR #85 terminal snapshots.

Any key outside the frozen PR #39 base sets plus these exact extension sets must
fail closed.

## Exact type and nullability domains

This is structural validation only. Names do not authorize football meaning.

```text
team.penScore
  optional exact non-negative integer
  null forbidden

team.redCards
  optional exact non-negative integer
  null forbidden

status.awarded
  optional exact bool
  null forbidden

status.ongoing
  optional exact bool
  null forbidden

status.numberOfAwayRedCards
  optional exact non-negative integer
  null forbidden

status.numberOfHomeRedCards
  optional exact non-negative integer
  null forbidden

status.scoreStr
  optional exact string
  null forbidden
  empty string structurally allowed

status.halfs.secondHalfStarted
  optional exact string
  null forbidden
  empty string structurally allowed
```

`status.liveTime`, when absent, is valid. When present it must be an exact object,
must not be null, and must contain **exactly**:

```text
addedTime
basePeriod
long
longKey
maxTime
short
shortKey
```

with these structural domains:

```text
addedTime   exact non-negative integer
basePeriod  exact non-negative integer
maxTime     exact non-negative integer

long        exact string, empty allowed
longKey     exact string, empty allowed
short       exact string, empty allowed
shortKey    exact string, empty allowed
```

No extra `liveTime` key is allowed in this protocol.

Exact typing means there is no coercion. In particular, a bool does not satisfy
an integer field merely because Python treats `bool` as an `int` subclass.

## Semantic exclusions

The extension fields remain opaque structural evidence.

PR #86 does **not** infer or qualify:

- whether `penScore` means a particular penalty-shootout result;
- whether `redCards` or either red-card count has any specific disciplinary
  settlement meaning;
- what `awarded` means operationally;
- what `ongoing`, `scoreStr`, `liveTime`, or the half-start strings mean beyond
  their reviewed structural types;
- regulation-time score semantics;
- extra-time score semantics;
- penalty-shootout score semantics;
- bookmaker settlement semantics;
- final-result semantics.

The PR #83 rule that any `status.reason` requires explicit review remains a
separate, unchanged blocker. Structural admission of a `reason`-bearing fixture
does not make its reason semantically trusted.

## Future implementation outcomes

The implementation step must use only this frozen vocabulary:

```text
QUALIFIED_STRUCTURAL_TERMINAL_STATE_SCHEMA_EXTENSION
BLOCKED_BASE_PR39_CONTRACT_DRIFT
BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT
BLOCKED_EXTRA_KEY_OUTSIDE_PRE_REGISTERED_SET
BLOCKED_EXTENSION_TYPE_OR_NULLABILITY_MISMATCH
BLOCKED_LIVE_TIME_SHAPE_MISMATCH
```

A structural qualification is only permission to say that a capture conforms to
this additive reviewed schema layer. It is not permission to interpret any new
field as football truth.

## Implementation requirements

The next implementation must:

1. verify exact PR #85 receipt and PR #39 ancestry;
2. leave PR #39 v1 unchanged;
3. admit only the exact pre-registered optional extension keys;
4. enforce exact bool/int/string/object types without coercion;
5. require extension integers to be non-negative;
6. forbid null for every extension field in this protocol;
7. require exactly seven keys inside `status.liveTime` when it exists;
8. fail on any unknown `liveTime` key;
9. keep extension strings opaque rather than parsing meaning from them;
10. preserve all existing PR #39 top-level, league, match, identity and kickoff
    validation;
11. not use the extension to qualify final-result semantics or the PR #83
    `status.reason` gate;
12. keep source capabilities and every downstream authorization unchanged.

## Canonical protocol identity

Compact sorted UTF-8 JSON plus one final LF:

```text
SHA-256  6e2e0936023531ad9c0a87cde68eb0cf4c8753b27aaa8c001bcbd3fcb5daa225
size     5639 bytes
```

## Safety

Every protocol safety value is exact `false`, including:

- network acquisition;
- extension implementation/qualification;
- PR #39 mutation;
- final-result semantics;
- source-capability update;
- source-history completeness;
- PR #80 constructor input;
- successor model;
- expected goals;
- score matrix;
- probability/calibration;
- pricing;
- market activation;
- selection;
- production;
- betting.

## Next required boundary

```text
IMPLEMENT_REVIEWED_FOTMOB_DATA_MATCHES_TERMINAL_STATE_SCHEMA_EXTENSION
```

Only after that implementation is independently reviewed may the preserved PR
#85 pair be structurally reconsidered. Even then, the independent PR #83
`status.reason` semantic gate remains unresolved.
