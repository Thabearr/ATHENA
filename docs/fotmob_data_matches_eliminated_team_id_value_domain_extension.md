# Reviewed FotMob `eliminatedTeamId` structural value-domain implementation

## Purpose

PR #89 implements the exact structural widening pre-registered by PR #88.

The frozen PR #39 V1 schema already requires the match-level key
`eliminatedTeamId`, but accepts only `null`. PR #87 correctly preserves that
contract and therefore fails closed on the exact PR #85 terminal snapshots,
where one fixture carries a stable non-null integer in both captures.

PR #89 leaves PR #39 and PR #87 unchanged. It adds one outer structural layer
that accepts only the PR #88 domain:

```text
null
OR
exact Python integer, excluding bool, with value >= 1
```

No meaning is assigned to the field.

## Exact ancestry

PR #89 starts from merged PR #88 main:

```text
df6b782e0e1b36c46089333a893a12f44e40fa07
```

Frozen upstream identities:

```text
PR39 schema blob          4dfff0eb05335895c3ee0fcaa7b8da1299ea692f
PR85 evidence blob        7b74e9893071ef47ea425b4f106d92b0c5e1ddc2
PR87 implementation blob  fc120476739293abbb5db4374a0b4d7cfe8a1fc3
PR88 protocol blob        85414d1377b231e11ff302d0706ddcd42e41c984
PR88 canonical SHA-256    e1b435e8ed833518f9c4a6c5ba89b3c22773c6e3c30e9a50bb85b708b9ff77da
PR88 canonical size       4276 bytes
```

The implementation revalidates the frozen PR #88 protocol and source-capability
premises before assessing an input capture.

## Structural method

The source capture itself is never rewritten or re-labelled.

For a reviewed source capture, PR #89:

1. revalidates the original PR38 capture manifest against the exact raw bytes;
2. parses the original bytes through the frozen PR39 strict JSON parser;
3. inspects every required `eliminatedTeamId` occurrence;
4. accepts `null`, or a non-null exact integer `>= 1`;
5. rejects booleans, floats, strings, containers, zero, and negative integers;
6. creates an internal deep-copy projection in which accepted non-null values are
   replaced with `null`;
7. creates a non-network manifest for that internal projection;
8. runs the projected bytes through the unchanged PR #87 terminal-state
   structural implementation;
9. returns a new PR #89 assessment bound to the **original** source manifest and
   raw SHA, while recording the internal PR #87 assessment identity.

The projection exists only to let the frozen PR #87/PR39 chain validate every
other reviewed structural rule without changing those earlier contracts. It is
not a replacement source capture and does not erase the original value from
lineage.

## Exact PR #85 result

Both preserved PR #85 captures now pass the complete reviewed structural chain.
Each capture contains:

```text
match count                         183
eliminatedTeamId occurrences        183
null occurrences                    182
non-null occurrences                1
```

The same non-null evidence remains:

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

The positive structural result is:

```text
QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN
```

This means only that the field's source value satisfies the frozen
null-or-positive-exact-integer domain and that, after the one permitted internal
projection, the unchanged PR #87 structural chain passes.

PR #87 itself remains unchanged and still rejects the original captures directly,
as required by its frozen PR39 base contract.

## What is still unknown

The one observed non-null value happens to equal the home-team ID. PR #89 does
not turn that observation into a rule. A positive integer that does not equal
either endpoint team ID is still structurally valid under the frozen PR #88
domain.

PR #89 does not establish:

- that `eliminatedTeamId` necessarily identifies an eliminated team;
- that it identifies the winner or loser;
- that it must equal `home.id` or `away.id`;
- that its presence means penalties occurred;
- the meaning of `status.reason`;
- regulation-time, extra-time or penalties score semantics;
- bookmaker settlement semantics;
- final-result semantics.

The exact PR #85 reason tuple remains opaque evidence pending a separate semantic
review.

## Fail-closed behavior

PR #89 uses only the PR #88 status vocabulary:

```text
QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN
BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT
BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT
BLOCKED_ELIMINATED_TEAM_ID_TYPE_OR_NULLABILITY_MISMATCH
BLOCKED_ELIMINATED_TEAM_ID_NONPOSITIVE_INTEGER
```

If the internal null projection is rejected by the frozen PR #87 chain, PR #89
fails closed as `BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT` and preserves the
inner PR #87 status in the error message. The value-domain widening therefore
cannot hide another unreviewed key, type, chronology, or base-schema failure.

## Source capability and authority

The reviewed source capability remains unchanged:

```text
source                    fotmob_data_matches_reviewed_catalog
reliable_fixture_identity CONFIRMED
full_time_score           NOT_CAPTURED
historical_coverage       UNKNOWN
```

All PR #88/PR #89 safety and downstream-authority fields remain exact `false`.
No network acquisition, model execution, expected-goals transformation,
ScoreMatrix construction, probability inference, calibration, pricing, market
activation, selection, production approval, or betting is authorized.

## Next required boundary

The terminal structural chain is now complete for the exact PR #85 pair. The
remaining explicit blocker already frozen by PR #83 is the presence of
`status.reason`.

The next boundary is therefore:

```text
PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_STATUS_REASON_SEMANTICS_PROTOCOL
```

That future protocol must define exactly what reason evidence may be admitted and
what, if anything, it can prove before final-result semantics are re-executed. It
must not silently equate `FT`, penalty, status ID, score strings, or any other
source label with regulation-time or bookmaker-settlement meaning.
