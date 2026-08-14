# Reviewed FotMob data-matches terminal-state schema extension implementation

## Purpose

PR #87 implements the additive structural layer pre-registered by PR #86 while
keeping the frozen PR #39 implementation unchanged.

The implementation accepts only the exact optional terminal/live fields frozen in
PR #86, validates their structural domains, projects those extension fields away,
and re-runs the remaining payload through the unchanged PR #39 assessment.

Implementation state:

```text
IMPLEMENTED_STRUCTURAL_EXTENSION_NO_FINAL_RESULT_SEMANTICS
```

A successful assessment may report only:

```text
QUALIFIED_STRUCTURAL_TERMINAL_STATE_SCHEMA_EXTENSION
```

That status means only that a payload conforms to the additive structural layer
and the frozen PR #39 base contract. It is not final-result or settlement
qualification.

## Exact ancestry

PR #87 starts from merged PR #86 main:

```text
11f34a1856d0cbb4b5f7a0b6b8c757fa8c07bbc9
```

It binds merged PR #86:

```text
protocol blob  71b2f1a8add05929835d469df94396375a115391
SHA-256        6e2e0936023531ad9c0a87cde68eb0cf4c8753b27aaa8c001bcbd3fcb5daa225
size           5639 bytes
```

and the unchanged PR #39 implementation:

```text
schema blob    4dfff0eb05335895c3ee0fcaa7b8da1299ea692f
```

Before an assessment runs, the implementation also rechecks the reviewed source
capability premise:

```text
source                    fotmob_data_matches_reviewed_catalog
reliable_fixture_identity CONFIRMED
full_time_score           NOT_CAPTURED
historical_coverage       UNKNOWN
```

## PR #86 structural extension

Only these optional team keys are admitted:

```text
penScore
redCards
```

Only these optional status keys are admitted:

```text
awarded
liveTime
numberOfAwayRedCards
numberOfHomeRedCards
ongoing
scoreStr
```

Only this optional `status.halfs` key is admitted:

```text
secondHalfStarted
```

The implementation enforces the exact PR #86 domains: non-negative exact
integers for `penScore`, `redCards` and both status red-card counts; exact bools
for `awarded` and `ongoing`; exact strings for `scoreStr` and
`secondHalfStarted`; and an exact seven-key `liveTime` object with non-negative
integer `addedTime`, `basePeriod`, `maxTime` and exact-string `long`, `longKey`,
`short`, `shortKey`. Null and coercion are rejected.

Unknown extension keys fail closed.

## Keeping PR #39 authoritative

PR #87 validates the original PR #38 raw byte lineage first. It uses PR #39's
strict JSON parser, validates only the additive PR #86 fields, then creates an
in-memory projection containing only the frozen PR #39 key shape.

The projection receives a derived verification manifest with its own size and
SHA-256 and with `network_acquisition_performed=False`. It is not represented as
a new provider capture. The resulting PR #87 assessment retains the original
source manifest SHA, raw SHA, size, observation time and request identity.

The unchanged PR #39 assessment therefore remains the final base structural gate
for league/match identity, duplicate IDs, kickoff/timeTS consistency, base team
and status fields, reason shape, and every other PR #39 invariant.

## Adversarial execution against the exact PR #85 pair

The first implementation attempt exposed a second, independent structural issue
that had not been part of PR #86's pre-registration.

After the registered terminal/live extra keys are removed, both preserved PR #85
captures still fail the frozen PR #39 base contract because at least one match has
a **non-null `eliminatedTeamId`**. PR #39 already includes this key but freezes its
V1 value domain to null only.

This is not another unknown key and it is not covered by the PR #86 terminal-key
extension. It is a **base-field value-domain change**. ATHENA therefore does not
silently broaden PR #39 after seeing it.

The implementation reports this as:

```text
BLOCKED_BASE_PR39_CONTRACT_DRIFT
```

with an explicit count of non-null `eliminatedTeamId` values in the projected
capture.

The exact committed PR #85 captures remain:

```text
20260814/a18e843fabe5aca74846b160
20260814/e28d9ce746c1ef9102995517
```

Both retain their original source raw and manifest lineage. The test suite proves
that each reaches this fail-closed base-domain blocker rather than being promoted
through it.

## Positive implementation seam

The implementation is also exercised on a deterministic PR #39-compatible
synthetic fixture where `eliminatedTeamId=None` and all pre-registered PR #86
extension fields are present with valid types.

That seam reaches:

```text
QUALIFIED_STRUCTURAL_TERMINAL_STATE_SCHEMA_EXTENSION
```

while keeping `reason_semantics_qualified=False`,
`final_result_semantics_qualified=False`, and every authority/safety value exact
false. This distinguishes a functioning structural extension from the separate
real-evidence base-domain blocker.

## Frozen failure vocabulary

PR #87 uses only the PR #86 status vocabulary:

```text
QUALIFIED_STRUCTURAL_TERMINAL_STATE_SCHEMA_EXTENSION
BLOCKED_BASE_PR39_CONTRACT_DRIFT
BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT
BLOCKED_EXTRA_KEY_OUTSIDE_PRE_REGISTERED_SET
BLOCKED_EXTENSION_TYPE_OR_NULLABILITY_MISMATCH
BLOCKED_LIVE_TIME_SHAPE_MISMATCH
```

No new permissive status is invented to bypass the unexpected
`eliminatedTeamId` evidence.

## Semantic boundary

PR #87 does not interpret any terminal/live field name and does not qualify:

- `status.reason`;
- `FT` or penalties reason labels;
- `eliminatedTeamId` meaning;
- regulation-time, extra-time or penalty-shootout result;
- awarded-match meaning;
- red-card or live-time meaning;
- bookmaker settlement;
- final-result semantics.

The independent PR #83 `status.reason` gate is therefore still unresolved, but it
is **not yet the immediate next boundary**. The newly observed PR #39 base-domain
issue must be reviewed first.

`full_time_score` remains `NOT_CAPTURED` and `historical_coverage` remains
`UNKNOWN`.

## Next required boundary

```text
PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_ELIMINATED_TEAM_ID_VALUE_DOMAIN_EXTENSION
```

That next PR must freeze exactly which non-null `eliminatedTeamId` values are
structurally admissible, their type/nullability rules, evidence basis, fail-closed
outcomes and semantic exclusions before any implementation may broaden the
frozen null-only PR #39 V1 domain.

Only after that separate boundary is implemented and the PR #85 pair can pass the
complete structural chain should ATHENA proceed to the independent
`status.reason` semantics gate.

## Safety

PR #87 performs no network acquisition and changes no PR #39, source-capability,
model, probability, pricing, selection, production or betting file.

Structural success creates no authority for source capability promotion,
source-history completeness, PR #80 input, successor execution, expected goals,
score matrix, probability/calibration, pricing, market activation, selection,
production or betting. All such values remain exact `false`.
