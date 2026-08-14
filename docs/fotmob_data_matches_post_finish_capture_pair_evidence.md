# Reviewed FotMob PR83 post-finish capture-pair evidence

## Purpose

PR #85 performs the first genuinely new-evidence step after PR #84. It uses the
already reviewed PR #38 transparent `/api/data/matches` transport to acquire and
preserve two exact source snapshots for the same request identity, more than 300
seconds apart.

The acquisition boundary succeeds: ATHENA now has two distinct raw responses and
two distinct canonical PR #38 manifests. The result does **not**, however,
qualify final-result semantics. The new terminal snapshots expose structural
fields outside the frozen PR #39 schema, so PR #83's first qualification gate
fails closed before finished-score semantics can be promoted.

```text
ACQUIRED_DISTINCT_CAPTURE_PAIR_BLOCKED_BY_PR39_TERMINAL_SCHEMA_DRIFT
```

No source capability, source-history completeness, successor-model, probability,
pricing, selection, production, or betting authority is created.

## Exact ancestry

PR #85 starts from merged PR #84 main:

```text
3ec2b2f415d483da6412fedb857c23642ee3b08b
```

It binds the frozen PR #83 protocol:

```text
blob       25f8045524badcb90239df59ac9c47f36fcffe34
SHA-256    572dde2f5ba8e68c96188ec2df3cc1fdcfa554aa1023aa56e8b8f8b225d7194b
size       3995 bytes
```

and the merged PR #84 validation receipt:

```text
blob       93a74ff60b3af7549f06d8b37b3323a07f7404c4
SHA-256    b8ac94402677c8d539ac365e348fd8415d3963b6511a0db5d0564f38737f1b9a
size       2490 bytes
```

PR #84 froze the next boundary as acquisition and preservation of two reviewed
post-finish data-matches captures for one finished fixture. PR #85 does not
weaken the PR #83 evidence rules after observing the source.

## Acquisition method

The successful acquisition used the exact reviewed PR #38 transparent request
profile:

```text
GET /api/data/matches?date=20260814&timezone=UTC&ccode3=NGA HTTP/1.1
Host: www.fotmob.com
Accept: application/json
User-Agent: ATHENA/1.0
```

No `x-mas`, Cookie, Authorization, browser impersonation, proxy, alternate
source, redirect, or fallback was introduced. Two requests were made in the
one-shot evidence run with a 310-second wait between them.

Authoritative acquisition provenance:

```text
workflow run       31822859656
job                94840009083
artifact           9227788141
artifact ZIP SHA   9dac79f90dad5c447eccf8fd6874f464f7e69437c979d82baaed633334cf3996
```

The temporary acquisition/materialization workflow was removed before final
review. The raw evidence is now committed under
`evidence/fotmob_data_matches/pr83_post_finish_pair/20260814/`.

## Exact capture pair

First observation:

```text
capture id       a18e843fabe5aca74846b160
observed_at      2026-08-14T17:12:02.437509Z
raw size         114920 bytes
raw SHA-256      fbcf24729973dbe7153c87fe9f37bd988aaca14ad10cce6b260ac7df650ff80f
manifest SHA     27bfb5dc90c67a305bdb045a7ff33010d87c4109925384d3e6d2a6e058d7b302
```

Second observation:

```text
capture id       e28d9ce746c1ef9102995517
observed_at      2026-08-14T17:17:13.043248Z
raw size         114964 bytes
raw SHA-256      175c6f94788fbf676e08a288ff0c46a995cd8798d60e4bc5044076e3c9713f8d
manifest SHA     d60501a5b7b1b4e5c810a0a0463bdcecb3a0b806110ad4542c314f8fe536824e
```

The observation separation is exactly `310.605739` seconds. Both raw SHA-256
values differ and both manifest SHA-256 values differ. Each raw payload contains
183 match records.

An earlier attempt using historical request date `20260813` is deliberately not
used as qualifying evidence. Its two requests were independently observed, but
the raw response body was byte-identical across the two observations. PR #83
requires distinct raw SHA-256 lineage, so that attempt correctly failed closed.

## What the new snapshots contain

A deterministic comparison of the two successful current-day snapshots finds 29
same-fixture observations that, before applying the PR #39 and status-reason
gates, have all of the following properties:

- exact source match, league, home-team, away-team, and kickoff identity is
  unchanged;
- both observations occur strictly after kickoff;
- `finished=True`, `started=True`, and `cancelled=False` in both snapshots;
- home and away score values are exact non-negative integers and the score pair
  is identical across both observations.

Twenty-eight of those carry a source reason with short value `FT`; one carries a
penalties reason. This count is evidence description only. It is not semantic
qualification.

A simple ordinary selected fixture is frozen for reproducible review:

```text
fixture id       5186581
league           920266 / Super League
home             8623 / Shandong Taishan
away             4183 / Qingdao Hainiu
kickoff UTC      2026-08-14T11:35:00.000Z
score            3-1 in both captures
statusId         6 in both captures
reason.short     FT
reason.shortKey  fulltime_short
reason.long      Full-Time
reason.longKey   finished
```

Its canonical `{league metadata without matches, match}` projection is 788 bytes
with SHA-256:

```text
46cab2b5138a620995fd093946f556dc3c5233a50c212c46253c5f8dd9184d1b
```

PR #83 explicitly says `statusId` cannot be the sole finality signal and any
status `reason` requires explicit review. The selected fixture therefore remains
reason-blocked even apart from the primary schema blocker below.

## Primary blocker: frozen PR #39 terminal-schema drift

PR #83's first qualification requirement is to revalidate every capture under
the reviewed PR #38 capture contract **and the frozen PR #39 strict schema**.
Both PR #85 raw responses fail that PR #39 structural revalidation because
terminal/live snapshots contain additional fields that were absent from the
single PR #39 review capture.

The exact extra keys observed in both new captures are:

```text
team:
  penScore
  redCards

status:
  awarded
  liveTime
  numberOfAwayRedCards
  numberOfHomeRedCards
  ongoing
  scoreStr

halfs:
  secondHalfStarted
```

The existing PR #39 contract permits team keys only `id`, `longName`, `name`,
and `score`; status permits the required status fields plus only `aggregatedStr`
and `reason`; `halfs` permits only `firstHalfStarted`.

ATHENA does not silently expand those sets after seeing the new data. Doing so
inside this acquisition PR would change the qualification rule after observing
the evidence.

The primary blocker is therefore:

```text
PR39_STRICT_SCHEMA_REVALIDATION_FAILED_TERMINAL_SNAPSHOT_EXTRA_KEYS
```

and PR #83 eligibility remains false.

## Secondary blocker: status reason requires review

Every one of the 29 stable finished identity/score candidates carries a status
`reason`. The ordinary example carries:

```json
{"long":"Full-Time","longKey":"finished","short":"FT","shortKey":"fulltime_short"}
```

PR #83 freezes the rule that any such reason requires separate explicit review
and cannot auto-qualify. This is recorded as the secondary blocker:

```text
PR83_STATUS_REASON_REQUIRES_EXPLICIT_REVIEW
```

The source wording is preserved as evidence only; this PR does not yet assert
that `Full-Time` has a particular regulation-time, extra-time, penalty, or
bookmaker-settlement meaning.

## Capability consequence

The reviewed source capability remains unchanged:

```text
full_time_score     = NOT_CAPTURED
historical_coverage = UNKNOWN
```

The capture pair does not authorize PR #80 constructor input, successor live
inputs, expected goals, score matrices, probability inference or adjustment,
calibration for production, prices, market activation, selection, production,
or betting.

## Canonical receipt

The compact sorted UTF-8 JSON receipt plus final LF has identity:

```text
SHA-256  a181e40c1264eecf6c9da897d826131c48177168e5592a64caa211ce64dacf02
size     3921 bytes
```

Tests independently re-hash the committed raw responses and manifests, re-run
frozen PR #39 schema assessment expecting failure, derive the exact added key
sets, recompute the 29 stable candidates, reproduce the selected fixture
projection, and enforce all safety flags as exact `false`.

## Next required boundary

The smallest truthful next step is now frozen as:

```text
PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_TERMINAL_STATE_SCHEMA_EXTENSION
```

That future protocol must decide, before implementation, exactly which newly
observed terminal/live keys may be structurally admitted and what their type and
nullability domains are. It must not infer semantics merely from field names.
Only after that separately reviewed structural boundary can these two captures
be reconsidered under PR #83; the status-reason semantic gate would still need
to be satisfied independently.
