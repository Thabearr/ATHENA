# Reviewed FotMob full-time-score capability promotion protocol

## Purpose

PR #93 pre-registers the next boundary after merged PR #92.

PR #92 proved a narrow semantic fact: 28 ordinary `FT` fixtures in the exact
preserved PR #85 capture pair carry stable source-reported finished-score
semantics under the frozen PR #83 contract. The one penalties fixture remains
excluded.

That is enough to design a reviewed score-capability surface, but not enough to
claim that ATHENA already has a reusable score adapter. PR #92 is an evidence
execution bound to the exact preserved pair; source capabilities describe what a
current adapter can reproducibly capture, not merely what one receipt proved.

PR #93 therefore freezes two protections before any capability registration:

```text
REGISTER_NEW_DERIVED_ADAPTER_SCOPED_SOURCE_KEY_DO_NOT_MUTATE_PARENT
SOURCE_CAPABILITY_PROMOTION_REQUIRES_REUSABLE_REVIEWED_PROSPECTIVE_ORDINARY_FT_FINISHED_SCORE_ADAPTER_NOT_ONE_OFF_EVIDENCE_RECEIPT
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

## Why a reusable adapter is mandatory

The existing PR #92 executor proves the exact preserved evidence pair. It is not
a prospective source adapter that can take a new reviewed capture and expose a
qualified ordinary-FT finished score under the same contract.

A source-capability registry entry would therefore be premature unless a
reusable reviewed adapter exists first. PR #93 freezes the future module path:

```text
domain/fotmob_data_matches_ordinary_ft_finished_score_adapter.py
```

and records the current pre-registration state as:

```text
ABSENT_NOT_IMPLEMENTED_AT_PR93_PRE_REGISTRATION
```

The future execution assessment must fail closed with
`BLOCKED_REUSABLE_REVIEWED_SCORE_ADAPTER_NOT_IMPLEMENTED` while that prerequisite
is missing. A one-off evidence receipt is never sufficient by itself to promote
a reusable source capability.

## Why the parent source key stays unchanged

The current parent capability key is:

```text
fotmob_data_matches_reviewed_catalog
```

It was deliberately created as an adapter-scoped identity capability. Its
current contract remains:

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
semantics and would blur the older identity-only catalog contract.

PR #93 therefore freezes a future derived source key instead:

```text
fotmob_data_matches_reviewed_ordinary_ft_finished_score
```

The parent entry remains unchanged.

## Proposed derived capability

Only after a reusable prospective adapter exists and a separate execution
assessment qualifies the registration may the derived key be considered for
these exact values:

```text
full_time_score           CONFIRMED
half_time_score           NOT_CAPTURED
event_timestamps          NOT_CAPTURED
reliable_fixture_identity CONFIRMED
historical_coverage       UNKNOWN
freshness_metadata        NOT_CAPTURED
```

For this derived adapter only, `CONFIRMED full_time_score` has the deliberately
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
reinterpreted by this layer.

Any future terminal reason outside the exact reviewed ordinary `FT` gate must
also remain excluded until separately reviewed.

## Frozen proposed registry evidence

The final derived capability, if separately authorized after the reusable adapter
exists, must carry the complete evidence set frozen here:

```text
domain/fotmob_data_matches_final_result_semantics_validation_with_reason_gate.py: exact PR92 28 ordinary-FT source-reported finished-score semantics
domain/fotmob_data_matches_status_reason_semantics_validation.py: exact reviewed ordinary-FT reason gate and penalty exclusion
domain/fotmob_data_matches_eliminated_team_id_value_domain_extension.py: reviewed structural chain over preserved PR85 captures
domain/fotmob_data_matches_capture.py: provenance-bound reviewed capture manifests
domain/fotmob_data_matches_ordinary_ft_finished_score_adapter.py: reusable reviewed prospective ordinary-FT finished-score gate
```

The first four evidence paths already exist on the PR #93 base. The final adapter
path is intentionally absent at pre-registration time and is frozen as required
future evidence. This prevents a later registry implementation from citing only
the one-off receipt while omitting the reusable adapter that makes the capability
real.

The registered notes are also pre-frozen to state that the score capability is
reachable only through a reusable reviewed prospective adapter and that broader
semantics and downstream authority remain excluded.

## Qualification requirements

The future assessment must verify all of the following before it may return a
qualified registration outcome:

- exact PR #92 validation blob and canonical receipt identity;
- exact PR #91 reason-gate and PR #83 semantic-scope ancestry;
- the parent reviewed-catalog entry still has `full_time_score = NOT_CAPTURED`
  and remains identity-only;
- the proposed derived source key does not already exist;
- a reusable reviewed prospective ordinary-FT finished-score adapter exists;
- that adapter is included in the proposed registry evidence;
- only the exact PR #92 ordinary-FT gate is admitted by that adapter;
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
BLOCKED_REUSABLE_REVIEWED_SCORE_ADAPTER_NOT_IMPLEMENTED
BLOCKED_PROPOSED_CAPABILITY_SCOPE_OVERCLAIM
BLOCKED_PENALTY_OR_UNREVIEWED_REASON_INCLUDED
```

A future `QUALIFIED_...REGISTRATION` status means only that the exact proposed
derived capability is safe to register. It does not itself mutate the registry
or authorize downstream use.

## Safety boundary

PR #93 performs no network acquisition and no source-capability registry update.
It does not mutate the parent source key or create the prospective score adapter.
It does not qualify penalties, regulation-time, extra-time, settlement, global
reason semantics, historical coverage, source history, successor inputs,
modelling, probabilities, calibration, pricing, market activation, selection,
production or betting.

Every authority flag remains exact `false`.

## Canonical protocol

```text
protocol id FOTMOB_DATA_MATCHES_FULL_TIME_SCORE_CAPABILITY_PROMOTION_PROTOCOL_V1
scope       PRE_REGISTERED_REVIEWED_SCOPED_FULL_TIME_SCORE_CAPABILITY_PROMOTION_ONLY
state       PRE_REGISTERED_NOT_EXECUTED_NO_SOURCE_CAPABILITY_CHANGE
SHA-256     8606367857915046eb27b9f2bf751514e52e266966b23caf598d1fedbf6b4009
size        6458 bytes
```

## Next required boundary

```text
EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_FULL_TIME_SCORE_CAPABILITY_PROMOTION_ASSESSMENT
```

Given the frozen current state, that execution is expected to fail closed on the
missing reusable adapter unless repository authority changes before execution.
The assessment must report that blocker rather than weaken the protocol. The
smallest following engineering boundary would then be the separately reviewed
prospective ordinary-FT score adapter; registry registration remains a later
step.
