# Reviewed FotMob data-matches final-result semantics protocol

## Purpose

PR #83 pre-registers the exact evidence required before ATHENA may interpret the
reviewed FotMob `/api/data/matches` team `score` fields as a source-reported
finished score.

The protocol is intentionally result-free. It does not perform network
acquisition, does not inspect a new live response, does not update source
capabilities, does not create historical result rows, and does not authorize the
PR #80 successor feature constructor or any downstream expected-goals,
probability, pricing, selection, production, or betting path.

## Why this boundary exists

PR #82 executed the source-history completeness assessment and stopped at:

```text
BLOCKED_CURRENT_REVIEWED_SOURCE_NO_FINAL_SCORE_SEMANTICS
```

The currently reviewed data-matches chain already proves stable source-scoped
fixture identity, team identity, competition identity and kickoff structure.
Its strict schema also observes:

```text
match.home.score
match.away.score
match.status.started
match.status.cancelled
match.status.finished
match.status.utcTime
```

However, PR #39 deliberately leaves:

```text
full_time_score_candidate = AMBIGUOUS
```

and the reviewed source-capability registry still records:

```text
full_time_score     = NOT_CAPTURED
historical_coverage = UNKNOWN
```

PR #83 therefore freezes the evidence required to resolve that one ambiguity
without silently treating a numeric score as a settled result.

## Exact ancestry

The protocol is anchored to merged PR #82 main:

- repository main:
  `a82aa81412f45a04720687c930f36d16dbe39f67`;
- PR #82 assessment blob:
  `6a46f36d7070e6e62a1587906c2e642fbcfea052`;
- PR #82 canonical assessment SHA-256:
  `450031e15fbb5878ee87ff7def69e549d0ec47fa94fc80dcb56e0b005408e807`;
- PR #82 canonical assessment size: `3,766` bytes.

It also binds the exact reviewed implementation blobs:

- `fotmob_data_matches_capture.py`:
  `ca2149395de868104666620173b55a880b10c729`;
- `fotmob_data_matches_schema.py`:
  `4dfff0eb05335895c3ee0fcaa7b8da1299ea692f`;
- `source_capabilities.py`:
  `ffd9730d6675a7dbcc9e8622d6e9844b772b6f96`.

The canonical PR #83 protocol is sorted compact UTF-8 JSON plus one final
newline:

- SHA-256:
  `572dde2f5ba8e68c96188ec2df3cc1fdcfa554aa1023aa56e8b8f8b225d7194b`;
- size: `3,995` bytes.

## Candidate fields

Only the following existing reviewed fields are in scope:

```text
match.id
match.leagueId
match.home.id
match.home.score
match.away.id
match.away.score
match.status.utcTime
match.status.started
match.status.cancelled
match.status.finished
```

`statusId` may be preserved as evidence during a future execution but cannot be
used as the sole finality signal. Legacy `status.scoreStr` behavior is not part of
the current reviewed PR #38/39 schema and is not imported into this contract.

## Frozen terminal-state rule

A candidate finished observation must satisfy exactly:

```text
status.finished  is True
status.started   is True
status.cancelled is False
```

A fixture that is merely started, has a plausible-looking score, or carries a
numeric `statusId` does not qualify.

If `status.reason` is present, the observation cannot auto-qualify. That reason
must first receive explicit review because abandoned, rearranged or otherwise
exceptional fixtures must not be converted into ordinary finished results.

## Frozen score rule

Both team score fields must be exact non-negative integers:

```text
home.score >= 0
away.score >= 0
```

Boolean values, floating-point values, strings, missing values and negative
values fail closed.

This remains only a candidate source-finished score until the repeated-observation
requirements below are also satisfied.

## Repeated finished observations

One response is not sufficient for PR #83's future positive verdict.

A validating execution must produce at least two distinct reviewed raw captures
for the same source fixture. Each used observation must:

1. revalidate through the existing PR #38 raw-capture contract and PR #39 strict
   schema;
2. occur strictly after the source kickoff;
3. have a distinct capture manifest and distinct raw-response SHA-256;
4. be separated from the other required observation by at least `300` seconds;
5. preserve the same source match ID, team IDs, league ID and kickoff;
6. satisfy the exact finished/started/not-cancelled state; and
7. report the identical home/away score pair.

A duplicated file or duplicated manifest is not a second observation.

If the source fixture identity or score changes between the required finished
observations, the execution fails closed rather than choosing one value.

## What a positive result would mean

The only positive status is:

```text
QUALIFIED_STABLE_SOURCE_FINISHED_SCORE_SEMANTICS
```

That status means only:

> for the exact reviewed FotMob data-matches field family and evidence contract,
> the stable team score pair observed under the explicit source `finished` state
> can be interpreted as the source-reported finished score.

It does **not** automatically establish whether that score is regulation-time,
extra-time, penalty-shootout, competition-settlement or bookmaker-settlement
scoring in every possible competition.

That narrower semantic scope prevents a future source-history adapter from
quietly importing assumptions that were never reviewed.

## Negative statuses

PR #83 freezes the following fail-closed outcomes:

```text
BLOCKED_NOT_FINISHED
BLOCKED_CANCELLED_OR_CONFLICTING_STATUS
BLOCKED_SCORE_INVALID
BLOCKED_INSUFFICIENT_POST_FINISH_OBSERVATIONS
BLOCKED_POST_FINISH_SCORE_INSTABILITY
BLOCKED_FIXTURE_IDENTITY_DRIFT
BLOCKED_CAPTURE_LINEAGE_OR_TIME
BLOCKED_STATUS_REASON_REQUIRES_REVIEW
```

These are execution outcomes for a later boundary. PR #83 itself emits none of
them because it is pre-registration only.

## Legacy code is not semantic proof

ATHENA contains older FotMob workers that have historically parsed score-shaped
fields or `status.scoreStr`. Those paths are outside the reviewed data-matches
capture/schema lineage and therefore cannot retroactively prove PR #83.

Their existence may be useful engineering context, but it is not accepted as
evidence that the currently reviewed `home.score` and `away.score` fields have
the required final-result meaning.

## What remains blocked even after a future positive verdict

Even a successful PR #83 execution would resolve only the first blocker found by
PR #82.

It would **not** by itself prove:

- historical date coverage;
- the PR #69-equivalent Elo initialization boundary;
- mapping of all eleven frozen model leagues to reviewed FotMob competitions;
- cross-season source-team identity continuity;
- absence of required-date gaps;
- complete finished-result coverage;
- PR #80 constructor-input eligibility;
- successor model production approval.

Those remain separate gates.

## Safety

Every authorization remains exact `false`, including:

- network acquisition;
- execution or qualification of final-result semantics;
- source-capability updates;
- source-history adapter approval and completeness;
- PR #80 constructor-input authorization;
- successor live-input qualification;
- successor model approval;
- expected-goals transformation and production use;
- score matrices and probability inference/adjustment;
- calibration;
- pricing and market activation;
- selection;
- production approval;
- betting.

## Next boundary

The only next boundary frozen by PR #83 is:

```text
EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_FINAL_RESULT_SEMANTICS_VALIDATION
```

That execution must use the exact protocol above. It may not weaken the
two-capture requirement or change the semantic interpretation after seeing a
result.
