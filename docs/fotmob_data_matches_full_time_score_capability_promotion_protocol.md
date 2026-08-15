# Reviewed FotMob full-time-score capability promotion protocol

## Purpose

PR #93 pre-registers the next boundary after merged PR #92.

PR #92 proved a narrow semantic fact: 28 ordinary `FT` fixtures in the exact
preserved PR #85 capture pair carry stable source-reported finished-score
semantics under the frozen PR #83 contract. The one penalties fixture remains
excluded.

That evidence is strong enough to consider a reviewed score-capability surface,
but it is **not** broad enough to rewrite the existing source-wide reviewed
catalog capability as though every terminal FotMob fixture were now understood.

For that reason, PR #93 freezes a safer promotion design:

```text
REGISTER_NEW_DERIVED_ADAPTER_SCOPED_SOURCE_KEY_DO_NOT_MUTATE_PARENT
```

No registry update is performed in this PR.

## Exact starting point

Merged PR #92 main:

```text
5e63aaa8d2c036b2af95d0f3a48bd78adb5cc02e
```

Frozen upstream identities:

```text
PR92 validation blob          0acd3cc554b927f0038bbaba122a54974e1c0829
PR92 receipt SHA-256          b821d5211de1e2a058b85ac1ca2ac50bdd0d3b577b54aa40c86ed6773bcb0c86
PR92 receipt size             3561 bytes
PR91 validation blob          a663a2c2879cb70dbd1f31f0f8bbe4ff8f1034d6
PR83 protocol blob            25f8045524badcb90239df59ac9c47f36fcffe34
source-capabilities blob      ffd9730d6675a7dbcc9e8622d6e9844b772b6f96
reviewed-capability test blob 8cf8837686aa8ebed0788676416b70ff3deffd4a
```

The reviewed evidence remains:

```text
ordinary FT source-finished-score qualified  28
penalty fixture excluded                       1
excluded penalty fixture id              5844873
```

## Why the parent source key stays unchanged

The current parent capability key is:

```text
fotmob_data_matches_reviewed_catalog
```

It was deliberately created as an adapter-scoped identity capability. Its
current contract is still:

```text
full_time_score           NOT_CAPTURED
half_time_score           NOT_CAPTURED
event_timestamps          NOT_CAPTURED
reliable_fixture_identity CONFIRMED
historical_coverage       UNKNOWN
freshness_metadata        NOT_CAPTURED
```

Mutating that parent entry to `full_time_score = CONFIRMED` would overstate the
reviewed evidence because the penalties case remains outside the qualified score
semantics. It would also blur the older identity-only catalog contract.

PR #93 therefore freezes a new derived source key instead:

```text
fotmob_data_matches_reviewed_ordinary_ft_finished_score
```

The parent entry must remain byte-for-byte governed by its existing source
capability contract until a separate future review explicitly changes it.

## Proposed derived capability

If the future execution assessment qualifies the registration, the derived key
may have exactly these capability values:

```text
full_time_score           CONFIRMED
half_time_score           NOT_CAPTURED
event_timestamps          NOT_CAPTURED
reliable_fixture_identity CONFIRMED
historical_coverage       UNKNOWN
freshness_metadata        NOT_CAPTURED
```

For this derived adapter only, `CONFIRMED full_time_score` has a deliberately
narrow definition:

```text
CONFIRMED_FULL_TIME_SCORE_MEANS_ONLY_PR92_QUALIFIED_SOURCE_REPORTED_FINISHED_SCORE_FOR_EXACT_ORDINARY_FT_GATE
```

It does **not** mean regulation-time score, extra-time score, penalty score,
bookmaker settlement, provider-wide score semantics, historical completeness,
or source freshness.

## Penalty and reason exclusion

The exact exclusion rule is:

```text
PENALTY_OR_OTHER_UNREVIEWED_REASON_FIXTURES_MUST_NOT_ENTER_DERIVED_CAPABILITY
```

Fixture `5844873` therefore remains outside the proposed derived capability.
Its ordinary score pair, penalty fields and `Pen` reason must not be silently
reinterpreted by this promotion layer.

Any future terminal reason not covered by the exact reviewed ordinary `FT` gate
must also remain outside the derived capability until separately reviewed.

## Frozen evidence strings

A later registry implementation, if separately authorized, must use only the
reviewed repository evidence frozen here:

```text
domain/fotmob_data_matches_final_result_semantics_validation_with_reason_gate.py: exact PR92 28 ordinary-FT source-reported finished-score semantics
domain/fotmob_data_matches_status_reason_semantics_validation.py: exact reviewed ordinary-FT reason gate and penalty exclusion
domain/fotmob_data_matches_eliminated_team_id_value_domain_extension.py: reviewed structural chain over preserved PR85 captures
domain/fotmob_data_matches_capture.py: provenance-bound reviewed capture manifests
```

The notes are also pre-registered and explicitly preserve the scope, penalty
exclusion, historical-coverage uncertainty, and downstream safety boundary.

## Qualification requirements

The future assessment must verify all of the following before it may return a
qualified registration outcome:

- exact PR #92 validation blob and canonical receipt identity;
- exact PR #91 reason-gate and PR #83 semantic-scope ancestry;
- the parent reviewed-catalog entry still has `full_time_score = NOT_CAPTURED`
  and remains identity-only;
- the proposed derived source key does not already exist;
- only the exact PR #92 ordinary-FT gate is admitted;
- the penalty fixture and any other unreviewed reason are excluded;
- promotion is expressed as a new derived adapter-scoped key, not a parent
  mutation;
- `historical_coverage` remains `UNKNOWN` and source freshness remains
  `NOT_CAPTURED`;
- regulation-time, extra-time, penalty-score, settlement and global reason
  semantics are not promoted;
- no source-history, model, probability, calibration, pricing, selection,
  production or betting authority is created.

## Frozen assessment status vocabulary

```text
QUALIFIED_SCOPED_ORDINARY_FT_FULL_TIME_SCORE_CAPABILITY_REGISTRATION
BLOCKED_PR92_EVIDENCE_ANCESTRY_DRIFT
BLOCKED_PARENT_SOURCE_CAPABILITY_DRIFT
BLOCKED_PROPOSED_SOURCE_KEY_ALREADY_EXISTS
BLOCKED_PROPOSED_CAPABILITY_SCOPE_OVERCLAIM
BLOCKED_PENALTY_OR_UNREVIEWED_REASON_INCLUDED
```

A future `QUALIFIED_...REGISTRATION` status will mean only that the exact
proposed derived capability is safe to register. It will not itself mutate the
registry or authorize any downstream use.

## Safety boundary

PR #93 performs no network acquisition and no source-capability registry update.
It does not mutate the parent source key. It does not qualify penalties,
regulation-time, extra-time, settlement, global reason semantics, historical
coverage, source history, successor inputs, modelling, probabilities,
calibration, pricing, market activation, selection, production or betting.

Every authority flag remains exact `false`.

## Canonical protocol

```text
protocol id FOTMOB_DATA_MATCHES_FULL_TIME_SCORE_CAPABILITY_PROMOTION_PROTOCOL_V1
scope       PRE_REGISTERED_REVIEWED_SCOPED_FULL_TIME_SCORE_CAPABILITY_PROMOTION_ONLY
state       PRE_REGISTERED_NOT_EXECUTED_NO_SOURCE_CAPABILITY_CHANGE
SHA-256     504287e45e614b6b47c5e730c3d50fd2a354be90863acc4b70025a7fd53d9549
size        5618 bytes
```

## Next required boundary

```text
EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_FULL_TIME_SCORE_CAPABILITY_PROMOTION_ASSESSMENT
```

That execution must determine whether the exact scoped registration pre-frozen
here is currently qualified. Even a qualified assessment must still leave the
actual registry unchanged until a separate implementation boundary is reviewed.
