# Reviewed FotMob `status.reason` semantics protocol

## Purpose

PR #90 pre-registers the independent `status.reason` review required by the frozen PR #83 final-result semantics protocol.

PR #89 has now cleared the structural blockers for the exact PR #85 capture pair. That does **not** make the source scores semantically final. PR #83 explicitly says that any present `status.reason` must undergo a separate explicit review before a finished-score candidate can qualify.

This PR therefore answers only one narrow question:

> When a PR83 candidate is already structurally valid, stable across the required post-finish capture pair, and otherwise satisfies PR83, which exact `status.reason` tuple may clear the reason gate?

Protocol state:

```text
PRE_REGISTERED_NOT_EXECUTED_STATUS_REASON_GATE_UNQUALIFIED
```

No source capability or downstream authority changes in PR #90.

## Frozen ancestry

PR #90 starts from merged PR #89 main:

```text
812e9f36bcffabf5c583ea1af1dd138acf23240a
```

It freezes these upstream identities:

```text
PR83 protocol blob       25f8045524badcb90239df59ac9c47f36fcffe34
PR83 canonical SHA-256   572dde2f5ba8e68c96188ec2df3cc1fdcfa554aa1023aa56e8b8f8b225d7194b
PR83 canonical size      3995 bytes

PR85 evidence blob       7b74e9893071ef47ea425b4f106d92b0c5e1ddc2
PR85 canonical SHA-256   a181e40c1264eecf6c9da897d826131c48177168e5592a64caa211ce64dacf02
PR85 canonical size      3921 bytes

PR89 implementation blob f33dd31aedcd92b5691a3503914ed184d601b493
source capabilities blob ffd9730d6675a7dbcc9e8622d6e9844b772b6f96
```

The exact PR #85 source pair remains:

```text
a18e843fabe5aca74846b160
raw SHA-256      fbcf24729973dbe7153c87fe9f37bd988aaca14ad10cce6b260ac7df650ff80f
manifest SHA-256 27bfb5dc90c67a305bdb045a7ff33010d87c4109925384d3e6d2a6e058d7b302

e28d9ce746c1ef9102995517
raw SHA-256      175c6f94788fbf676e08a288ff0c46a995cd8798d60e4bc5044076e3c9713f8d
manifest SHA-256 d60501a5b7b1b4e5c810a0a0463bdcecb3a0b806110ad4542c314f8fe536824e
```

Request identity remains `20260814 / UTC / NGA`.

## Reviewed evidence distribution

PR #85 froze 29 stable finished identity-and-score pairs across the two post-finish observations:

```text
29 total stable finished score pairs
28 ordinary FT reason pairs
 1 penalty reason pair
```

PR #90 does not broaden this evidence set.

## Exact ordinary reason tuple

The only ordinary tuple pre-registered to clear the PR83 reason gate is:

```text
short     FT
shortKey  fulltime_short
long      Full-Time
longKey   finished
```

All four fields must match exactly. No case folding, aliasing, normalization, partial matching or inference from `statusId` is allowed.

A successful future reason assessment for this tuple means only:

```text
SOURCE LABEL IS COMPATIBLE WITH PR83 SOURCE-REPORTED FINISHED-SCORE SEMANTICS
```

It does **not** prove regulation-time settlement, extra-time treatment, bookmaker rules, or any broader football result semantics.

### Additional guards for ordinary FT

Even an exact FT tuple cannot clear the reason gate unless:

```text
status.awarded is absent or exact false
home.penScore is absent
away.penScore is absent
```

These guards stop an administrative or penalty-bearing terminal state from being silently treated as an ordinary finished-score observation.

`status.scoreStr` remains opaque and is not parsed by this protocol.

## Exact penalty reason tuple

The evidence pair contains one stable penalty-state fixture:

```text
fixture id        5844873
home.score        1
away.score        1
home.penScore     5
away.penScore     6
eliminatedTeamId  6576
```

Its reason tuple is:

```text
short     Pen
shortKey  penalties_short
long      After penalties
longKey   afterpenalties
```

PR #90 explicitly does **not** allow this tuple to qualify plain home/away score semantics. The source exposes a tied ordinary score pair together with separate penalty-score fields and a terminal reason labelled after penalties. That requires its own future penalty-score semantics review.

The protocol does not infer that `eliminatedTeamId` means loser, winner, eliminated side, or any other football concept. It merely preserves the exact source evidence.

## Unknown or changed reasons

Any other present reason tuple remains blocked pending explicit review.

A near-match also remains blocked. For example, changing only `FT` to `ft`, changing one key, omitting one field, or adding an alias is not accepted.

This is deliberate fail-closed behavior: provider vocabulary drift must create a new reviewed boundary rather than silently inheriting old semantics.

## Future status vocabulary

Execution may use only:

```text
QUALIFIED_PR83_REASON_GATE_ORDINARY_FT_SOURCE_LABEL
BLOCKED_PR83_OR_PR85_ANCESTRY_DRIFT
BLOCKED_PR89_STRUCTURAL_ANCESTRY_DRIFT
BLOCKED_REASON_TUPLE_UNREVIEWED
BLOCKED_REASON_TUPLE_MISMATCH_OR_PARTIAL
BLOCKED_AWARDED_RESULT_REQUIRES_SEPARATE_REVIEW
BLOCKED_PEN_SCORE_PRESENT_REQUIRES_SEPARATE_REVIEW
BLOCKED_PENALTY_REASON_REQUIRES_SEPARATE_SCORE_SEMANTICS
```

A qualified reason-gate status is not a final-result semantic qualification by itself.

## Safety consequence

The reviewed source capability remains:

```text
source                    fotmob_data_matches_reviewed_catalog
reliable_fixture_identity CONFIRMED
full_time_score           NOT_CAPTURED
historical_coverage       UNKNOWN
```

PR #90 performs no network acquisition and changes no PR83, PR85, PR89, acquisition, source-capability, model, probability, pricing, selection, production or betting code.

Every authority flag remains exact `false`, including status-reason execution, status-reason qualification, final-result execution, final-result qualification, source-capability update and betting authorization.

## Canonical protocol

```text
protocol id  FOTMOB_DATA_MATCHES_STATUS_REASON_SEMANTICS_PROTOCOL_V1
scope        PRE_REGISTERED_REVIEWED_PR83_STATUS_REASON_GATE_ONLY
SHA-256      08bbc2d1e53cfb1268ba71745ae80d9bc32f4bfad0f02d52225df936c7634f23
size         5602 bytes
```

## Next required boundary

```text
EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_STATUS_REASON_SEMANTICS_VALIDATION
```

That execution must revalidate the two exact PR #85 captures and PR #89 structural qualification, enumerate the stable PR83 finished-score candidates, apply the exact tuple and guard rules above, and produce a deterministic evidence receipt. It must not update `full_time_score` or authorize downstream use.
