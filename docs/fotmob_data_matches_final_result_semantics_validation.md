# Reviewed FotMob data-matches final-result semantics validation

## Purpose

PR #84 executes the frozen PR #83 final-result semantics protocol against the
**currently reviewed evidence inventory only**.

It does not perform a new FotMob request and does not reinterpret old fixture
values that were deliberately left out of committed reviewed artifacts. The
result is therefore fail-closed:

```text
EXECUTED_FAIL_CLOSED_INSUFFICIENT_POST_FINISH_OBSERVATIONS
```

with protocol status:

```text
BLOCKED_INSUFFICIENT_POST_FINISH_OBSERVATIONS
```

No final-result semantics are qualified.

## Exact ancestry

PR #84 starts from merged PR #83 main:

```text
5cba22dfa480f66cf7fde22e31c730fb0848bcce
```

The exact merged PR #83 protocol blob is:

```text
25f8045524badcb90239df59ac9c47f36fcffe34
```

and its canonical protocol identity remains:

```text
SHA-256  572dde2f5ba8e68c96188ec2df3cc1fdcfa554aa1023aa56e8b8f8b225d7194b
size     3995 bytes
```

PR #83 froze the next boundary as:

```text
EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_FINAL_RESULT_SEMANTICS_VALIDATION
```

PR #84 does exactly that without weakening the protocol after seeing the
available evidence.

## Reviewed evidence inventory

The committed PR #39 schema-review documentation identifies one reviewed PR #38
raw capture:

```text
.cache/athena-research/fotmob-data-matches-captures/
    20260815/76d18629482ffda786e6b58e/
```

Its reviewed metadata is:

```text
request date          20260815
raw size              314098 bytes
raw SHA-256           6eabfb341d29f3b5db0833972a9aaf7dbd97df150ccecde09f6f67396bc73b27
manifest SHA-256      3fe1d24a0738114c46114a815eca44c4221b53fe8da2476d5a487153ce72d145
```

PR #39 intentionally committed only metadata-level schema assessment. It did
not emit fixture IDs, teams, scores, or status values. Its review states that
the capture contained no reviewed started/finished evidence that established
the football meaning of the score integers.

The raw capture itself remains under the repository's ignored research cache,
which is an intentional evidence boundary rather than a missing-data problem to
paper over.

## Why PR #83 cannot qualify yet

PR #83 requires **at least two distinct reviewed post-kickoff captures** for the
same fixture. Those observations must have distinct manifest/raw lineage, be at
least 300 seconds apart, preserve exact fixture/team/league/kickoff identity,
carry `finished=True`, `started=True`, `cancelled=False`, have no unreviewed
status reason, and report the same exact non-negative integer score pair.

The current committed/reviewed inventory cannot prove such a pair. Importantly,
PR #84 does **not** claim that the single documented capture is or is not a
post-finish capture at fixture level, because those fixture-level values were not
committed by PR #39. That count stays unknown:

```text
reviewed capture count                 1
post-finish capture count              UNKNOWN_FROM_COMMITTED_METADATA_ONLY
PR83-eligible two-capture pair count   0
required distinct captures per pair    2
```

The zero applies only to a **provable PR83-eligible pair**. It is not a claim
that zero finished fixtures existed in the ignored raw response.

PR #84 therefore does **not** choose an old fixture, reconstruct a score from
legacy code, infer a terminal state, use a website display, use search results,
or treat a plausible numeric pair as proof.

It also does not downgrade the requirement to one capture simply because only
one reviewed capture is currently documented.

## Exact receipt

The canonical PR #84 receipt is compact sorted UTF-8 JSON plus one final LF:

```text
SHA-256  b8ac94402677c8d539ac365e348fd8415d3963b6511a0db5d0564f38737f1b9a
size     2490 bytes
```

The receipt records the reviewed inventory metadata, preserves the unknown
post-finish count explicitly, and records the exact fail-closed status. It
contains no fabricated fixture identifier or score.

## Capability consequence

The reviewed source capability must remain:

```text
full_time_score     = NOT_CAPTURED
historical_coverage = UNKNOWN
```

PR #84 does not modify `domain/source_capabilities.py` and creates no capability
promotion.

Even a later successful finished-score semantics result would still not by
itself prove historical coverage, the PR #69-equivalent Elo initialization
boundary, eleven-league mapping, cross-season identity continuity, date-gap
absence, complete result coverage, PR #80 constructor eligibility, or successor
production authority.

## Safety

Every network, source-capability, source-history, successor, expected-goals,
score-matrix, probability, calibration, pricing, market-activation, selection,
production, and betting authorization remains exact `false`.

This PR is an evidence receipt, not a source adapter or model activation.

## Next required boundary

The smallest truthful next step is now frozen as:

```text
ACQUIRE_AND_PRESERVE_TWO_REVIEWED_POST_FINISH_DATA_MATCHES_CAPTURES_FOR_ONE_FINISHED_FIXTURE
```

That future acquisition must use the already-reviewed PR #38 transparent
`/api/data/matches` capture contract. It must preserve both raw bodies and both
canonical manifests, retain exact request identity, and leave the two-capture
and 300-second rules unchanged. Only after those captures exist may a later
execution determine whether PR #83's positive semantic status is earned.
