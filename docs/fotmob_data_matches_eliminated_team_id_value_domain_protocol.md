# Reviewed FotMob `eliminatedTeamId` value-domain extension protocol

## Purpose

PR #88 pre-registers the smallest structural boundary exposed by PR #87.

The frozen PR #39 schema already contains the match-level key:

```text
eliminatedTeamId
```

but PR #39 V1 permits only `null`. The exact PR #85 post-finish evidence pair
contains one stable non-null occurrence, so the terminal-state structural chain
cannot yet revalidate those real captures.

This PR does **not** implement the broader value domain. It freezes what a later
implementation is allowed to accept and, equally importantly, what it is not
allowed to infer.

Protocol state:

```text
PRE_REGISTERED_NOT_IMPLEMENTED_NO_SEMANTIC_PROMOTION
```

## Exact ancestry

PR #88 starts from merged PR #87 main:

```text
f72ac2210945e35f04b7413e2c31480f027addf0
```

It binds:

```text
PR39 schema blob          4dfff0eb05335895c3ee0fcaa7b8da1299ea692f
PR85 evidence blob        7b74e9893071ef47ea425b4f106d92b0c5e1ddc2
PR85 canonical SHA-256    a181e40c1264eecf6c9da897d826131c48177168e5592a64caa211ce64dacf02
PR85 canonical size       3921 bytes
PR86 protocol blob        71b2f1a8add05929835d469df94396375a115391
PR86 canonical SHA-256    6e2e0936023531ad9c0a87cde68eb0cf4c8753b27aaa8c001bcbd3fcb5daa225
PR86 canonical size       5639 bytes
PR87 implementation blob  fc120476739293abbb5db4374a0b4d7cfe8a1fc3
```

The two exact raw captures remain the PR #85 evidence:

```text
a18e843fabe5aca74846b160
raw Git blob  ea60c0cac4b3081c3180e00c8bfdcdbdc218915f
raw SHA-256   fbcf24729973dbe7153c87fe9f37bd988aaca14ad10cce6b260ac7df650ff80f

e28d9ce746c1ef9102995517
raw Git blob  2b73b50bfa3f4ab2b49b7a8faf68d3434792ad59
raw SHA-256   175c6f94788fbf676e08a288ff0c46a995cd8798d60e4bc5044076e3c9713f8d
```

No new network acquisition is performed.

## Exact observed evidence

Each of the two captures contains exactly one non-null `eliminatedTeamId`.
The observation is stable across both captures:

```text
fixture id             5844873
league id              938331
home team id           6576
away team id           1218886
eliminatedTeamId       6576
status id              13
reason.short           Pen
reason.shortKey        penalties_short
reason.long            After penalties
reason.longKey         afterpenalties
```

The observed non-null value equals the home-team identifier in this one fixture.
That is recorded as an evidence fact only. One observation is not used to create
a universal referential or football-semantic rule.

## Frozen structural domain

The later implementation may broaden only the `eliminatedTeamId` value domain:

```text
null
OR
exact Python integer, excluding bool, with value >= 1
```

`null` remains valid because it is the overwhelmingly observed PR #85 form and
is already the frozen PR #39 V1 domain.

When the field is non-null, coercion is forbidden. Booleans, floats, strings,
containers, zero and negative integers must fail closed.

PR #88 deliberately does **not** require a non-null value to equal `home.id` or
`away.id`. The exact pair provides only one non-null fixture, so universalizing
that observed coincidence would exceed the reviewed evidence.

## Frozen status vocabulary

A later implementation may use only:

```text
QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN
BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT
BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT
BLOCKED_ELIMINATED_TEAM_ID_TYPE_OR_NULLABILITY_MISMATCH
BLOCKED_ELIMINATED_TEAM_ID_NONPOSITIVE_INTEGER
```

A qualified structural status will mean only that the field satisfies the frozen
null-or-positive-exact-integer domain. It will not establish what the identifier
means.

## Semantic exclusions

PR #88 does not infer or qualify any of the following:

- that `eliminatedTeamId` names an eliminated team;
- that it identifies a winner or loser;
- that it must equal either endpoint team identifier;
- that its observed presence is caused by penalties;
- `status.reason` meaning;
- `FT`, penalties, regulation-time or extra-time semantics;
- bookmaker settlement;
- final-result semantics.

The reason fields above are preserved as opaque context from the exact source
evidence. Their football meaning remains behind the independent `status.reason`
semantic gate.

## Safety consequence

The reviewed source capability remains unchanged:

```text
source                    fotmob_data_matches_reviewed_catalog
reliable_fixture_identity CONFIRMED
full_time_score           NOT_CAPTURED
historical_coverage       UNKNOWN
```

PR #88 changes no PR #39, PR #87, acquisition, source-capability, model,
probability, pricing, selection, production or betting code. Every authority flag
remains exact `false`.

## Canonical protocol

```text
protocol id     FOTMOB_DATA_MATCHES_ELIMINATED_TEAM_ID_VALUE_DOMAIN_EXTENSION_PROTOCOL_V1
scope           PRE_REGISTERED_REVIEWED_ELIMINATED_TEAM_ID_STRUCTURAL_VALUE_DOMAIN_ONLY
SHA-256         e1b435e8ed833518f9c4a6c5ba89b3c22773c6e3c30e9a50bb85b708b9ff77da
size            4276 bytes
```

## Next required boundary

```text
IMPLEMENT_REVIEWED_FOTMOB_DATA_MATCHES_ELIMINATED_TEAM_ID_VALUE_DOMAIN_EXTENSION
```

That implementation must leave PR #39 and PR #87 immutable, apply only the
pre-registered value-domain widening, and then re-run the exact PR #85 pair
through the structural chain. Only after the full structural chain passes may
ATHENA return to the independent `status.reason` semantics boundary.
