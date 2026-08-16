# PR69 source-local time basis resolution protocol

## Purpose

PR #122 pre-registers the exact evidence boundary needed to resolve the remaining
`BLOCKED_PR69_REFERENCE_TIME_BASIS_UNRESOLVED` result from PR #121.

It is intentionally **result-free**. It does not pick a timezone, does not assert
that football-data.co.uk used UTC or any named civil timezone, and does not compare
FotMob `Europe/Oslo` timestamps to PR #69 as reference evidence.

## Frozen ancestry

The protocol anchors to repository `main`:

`06ae83b0305f2080be5a875987f8a77e2a8b31dc`

It revalidates:

- PR #121 receipt SHA-256 `8d057e96504a83237b719b3a465e29b7df74e2b6c3630fc1d97e8a2a7bdfb5fb`,
  size `3,599` bytes;
- PR #121 qualification implementation blob
  `98c53095f56515975ae4b07194ffbe27749a7f53`;
- PR #120 protocol canonical SHA-256
  `a938ee4ea45c427c5396fe063af4efd2341a9c8e8ffccc1105aa7bdffdbb2918`,
  size `5,242` bytes;
- exact PR #69 replay implementation blob
  `b67a7e52954f47cc90c578ad193545c541984964`;
- PR #114 receipt SHA-256
  `fbbec0b858c3e9630d9f4c7dec630012f57811de52d300db3a11b781a719e110`,
  size `24,428` bytes;
- PR #69 exact source corpus SHA-256
  `c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0`;
- PR #69 canonical replay SHA-256
  `b44166b9543a8f436e62a644efc5316ad12fcc260a4c2c5908ad112928bedfe3`,
  size `39,952,730` bytes.

## Frozen PR69 scope

The reference corpus remains exactly:

- source namespace `football_data_uk_csv`;
- `66` source CSV files;
- `10,006,877` raw source bytes;
- `21,226` source fixtures;
- seasons `2020-21` through `2025-26`;
- the currently validated historical/model codes
  `B1`, `D1`, `E0`, `F1`, `G1`, `I1`, `N1`, `P1`, `SC0`, `SP1`, `T1`.

These eleven codes are not ATHENA's full competition universe.

The frozen PR #69 meaning of `Time` remains only:

`NAIVE_DATETIME_COMBINED_FROM_SOURCE_DATE_AND_SOURCE_TIME`

and its timezone state remains:

`SOURCE_LOCAL_TIMEZONE_UNRESOLVED`

## Direct resolution route

A positive direct resolution must come from provenanced primary
football-data.co.uk semantics and produce a deterministic rule that covers every
relevant PR #69 row.

The protocol admits several *shapes* of direct rule without claiming any of them
is true:

- explicit UTC;
- explicit fixed offset;
- explicit named IANA timezone;
- explicit source-defined competition/local civil-time rule with a deterministic
  mapping.

If DST or offset transitions can occur, their semantics must be explicit. The
evidence must also state the effective period/version to which the rule applies.

A named timezone is not mandatory if the primary source defines a different but
fully deterministic local-time rule.

## Evidence rules

Admissible evidence is limited to:

- the exact frozen PR #69 raw bytes and PR #114 hashed rebuild evidence;
- preserved primary football-data.co.uk documentation/data dictionaries with
  URL, capture time, raw bytes hash and effective scope;
- archived copies of primary football-data.co.uk content only when the original
  provenance and captured bytes are preserved;
- source-file metadata or embedded semantics that actually exist in the exact
  preserved bytes;
- a formal operational-invariance proof whose assumptions are machine-checkable
  and proven for the frozen scope.

Search snippets, blogs, mirrors, forum posts and secondary interpretations cannot
establish the reference basis.

Country, league, team, venue or normal football scheduling practice cannot be
used to guess a timezone.

## Conflict handling

Primary evidence is not combined by majority vote.

If two primary statements conflict, the execution must determine whether they
refer to different effective periods or versions. If that cannot be proven, the
qualification fails closed with a conflict or scope-ambiguity status.

Every relevant PR #69 row must be covered by the resulting rule. Unmapped rows
block a positive direct qualification.

## Formal invariance route

If direct primary semantics cannot be recovered, a positive result is possible
only through a formal operational-invariance proof.

That proof must enumerate every admissible reference transformation and prove
invariance for all PR #80 time-sensitive operations:

- strict-prior membership;
- form ordering and tie-break behavior;
- Elo ordering and tie-break behavior;
- most-recent prior fixture selection;
- integer `datetime.timedelta.days` rest components;
- home-minus-away rest-day difference;
- fatigue bucket.

Equal observed feature values or zero observed disagreements are not enough by
themselves.

## What remains closed

This pre-registration does not:

- resolve the PR #69 time basis;
- prove FotMob `Europe/Oslo` equivalent or non-equivalent;
- perform the PR #120 FotMob equivalence assessment;
- authorize PR #80 constructor input;
- authorize model training;
- authorize expected-goals production;
- authorize probabilities, pricing, market activation, selection, production or
  BET.

All safety flags remain exact `false`.

## Canonical protocol identity

Canonical SHA-256:

`d3bf061ade81bb1b60f38e98f5fa3c8c21ba5bf6652879f2cc19e151b53aee4a`

Canonical size:

`6,983` bytes.

## Next boundary

`EXECUTE_REVIEWED_PR69_SOURCE_LOCAL_TIME_BASIS_RESOLUTION_QUALIFICATION`

That execution may resolve the reference only under the evidence/proof rules
frozen here. It must not change the rules after observing the evidence.
