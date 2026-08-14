# Reviewed FotMob data-matches terminal-state schema extension implementation

## Purpose

PR #87 implements the additive structural layer pre-registered by PR #86.

The frozen PR #39 schema is not edited. Instead, PR #87 accepts only the exact
optional terminal/live fields registered in PR #86, validates their exact types,
projects those fields away, and then re-runs the remaining payload through the
unchanged PR #39 structural assessment. This keeps the original PR #39 contract
as an independent base gate rather than silently widening it.

Implementation state:

```text
IMPLEMENTED_STRUCTURAL_EXTENSION_NO_FINAL_RESULT_SEMANTICS
```

A successful assessment may report only:

```text
QUALIFIED_STRUCTURAL_TERMINAL_STATE_SCHEMA_EXTENSION
```

That status means only that the source capture conforms to the reviewed additive
structural layer. It is not a football-semantic or betting-semantic qualification.

## Exact ancestry

PR #87 starts from merged PR #86 main:

```text
11f34a1856d0cbb4b5f7a0b6b8c757fa8c07bbc9
```

It binds the merged PR #86 protocol:

```text
blob       71b2f1a8add05929835d469df94396375a115391
SHA-256    6e2e0936023531ad9c0a87cde68eb0cf4c8753b27aaa8c001bcbd3fcb5daa225
size       5639 bytes
```

and the unchanged PR #39 schema implementation:

```text
blob       4dfff0eb05335895c3ee0fcaa7b8da1299ea692f
```

The source capability premise is also rechecked before every assessment:

```text
source                    fotmob_data_matches_reviewed_catalog
reliable_fixture_identity CONFIRMED
full_time_score           NOT_CAPTURED
historical_coverage       UNKNOWN
```

## Structural extension

The implementation admits only these optional team fields:

```text
penScore
redCards
```

only these optional status fields:

```text
awarded
liveTime
numberOfAwayRedCards
numberOfHomeRedCards
ongoing
scoreStr
```

and only this optional `status.halfs` field:

```text
secondHalfStarted
```

No extra key is admitted at top-level, league, match, team, status, halfs, or
inside `liveTime`.

The exact PR #86 typing rules are enforced:

- `penScore`, `redCards`, and both status red-card counts: exact non-negative
  integers, with bool rejected as an integer;
- `awarded` and `ongoing`: exact bool;
- `scoreStr` and `secondHalfStarted`: exact strings;
- `liveTime`: exact object with exactly seven keys;
- `liveTime.addedTime`, `basePeriod`, `maxTime`: exact non-negative integers;
- `liveTime.long`, `longKey`, `short`, `shortKey`: exact strings;
- null is rejected for every extension field.

No coercion is performed.

## How PR #39 remains authoritative

PR #87 first validates the original PR #38 raw-byte lineage and strict JSON
parsing. It then validates the extension fields and builds a deterministic
in-memory projection containing only the frozen PR #39 key shape.

The projection is paired with an internal derived manifest containing the
projection's own byte size and SHA-256. That internal object is used only to run
the unchanged `assess_fotmob_data_matches_schema` function.

The final PR #87 assessment continues to record the **original source capture**
manifest SHA, raw SHA, raw size, request identity, and observation time. The
derived projection is not represented as a new source capture and creates no new
source lineage.

This means PR #87 still inherits PR #39 checks for:

- exact top-level `date` / `leagues`;
- league required/allowed keys and field types;
- exact match keys;
- duplicate match IDs;
- league linkage;
- status ID, time, timeTS, tournament-stage and eliminated-team constraints;
- base home/away team identity and score scalar types;
- base status shape and reason shape;
- source kickoff UTC parsing;
- `timeTS` / kickoff agreement;
- kickoff UTC date / request-date agreement.

A base failure is surfaced as:

```text
BLOCKED_BASE_PR39_CONTRACT_DRIFT
```

The implementation does not hide a PR #39 failure merely because the additive
terminal schema is valid.

## Frozen failure vocabulary

PR #87 uses only the status vocabulary pre-registered in PR #86:

```text
QUALIFIED_STRUCTURAL_TERMINAL_STATE_SCHEMA_EXTENSION
BLOCKED_BASE_PR39_CONTRACT_DRIFT
BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT
BLOCKED_EXTRA_KEY_OUTSIDE_PRE_REGISTERED_SET
BLOCKED_EXTENSION_TYPE_OR_NULLABILITY_MISMATCH
BLOCKED_LIVE_TIME_SHAPE_MISMATCH
```

Unknown extension keys, null/type mismatch, live-time shape mismatch, frozen-base
drift, and upstream ancestry drift therefore remain explicit fail-closed outcomes.

## Revalidation of the PR #85 evidence pair

The tests execute the implementation against both exact committed PR #85
captures:

```text
20260814/a18e843fabe5aca74846b160
20260814/e28d9ce746c1ef9102995517
```

Each capture contains 183 match records and each now passes the additive
structural extension layer.

The test suite separately confirms that the unchanged PR #39 implementation still
rejects those raw terminal snapshots directly. This is intentional: PR #87 is a
separate additive layer, not a mutation of PR #39.

Structural qualification does **not** clear the PR #83 reason gate.

## Semantic boundary

PR #87 does not interpret any of the newly admitted field names.

It does not qualify:

- `status.reason`;
- `FT` or penalties reason labels;
- regulation-time result;
- extra-time result;
- penalty-shootout result;
- awarded-match meaning;
- red-card meaning;
- live-time meaning;
- score-string meaning;
- bookmaker settlement;
- final-result semantics.

Therefore the reviewed source capability remains:

```text
full_time_score = NOT_CAPTURED
historical_coverage = UNKNOWN
```

and the next boundary is:

```text
PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_STATUS_REASON_SEMANTICS
```

That next step must freeze the exact evidence and interpretation rules for
`status.reason` before the preserved PR #85 pair can be reconsidered under the
PR #83 final-result semantics protocol.

## Safety

The implementation performs no network acquisition. It imports no network
client, provider/worker path, score matrix, probability, pricing, selection,
SportyBet, production, or betting module.

A structural success does not authorize:

- PR #39 mutation;
- source capability promotion;
- final-result semantics;
- source-history completeness;
- PR #80 constructor input;
- successor-model execution;
- expected-goals production use;
- score-matrix or probability inference;
- calibration for production;
- pricing;
- market activation;
- selection;
- production;
- betting.

All safety/authority values remain exact `false`.
