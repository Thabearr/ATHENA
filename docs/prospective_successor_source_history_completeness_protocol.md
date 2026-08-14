# Prospective successor source-history adapter and completeness protocol

## Purpose

PR #81 freezes the next boundary after PR #80 before ATHENA inspects or adapts a
real prospective result-history corpus.

PR #80 proved that the five raw successor inputs can be reconstructed with the
same mathematics used by the frozen historical research path **if** an adequate
source-scoped prior-result history is supplied. It intentionally left the hard
question unresolved: how do we prove that a prospective source history is
complete, correctly identified, chronologically safe, and based on reviewed
final-result semantics?

PR #81 answers that question as a pre-registered protocol. It does not execute
the source adapter and does not produce a positive qualification result.

The frozen state is:

```text
PRE_REGISTERED_NOT_EXECUTED_NO_SOURCE_HISTORY_QUALIFIED
```

The next boundary is:

```text
EXECUTE_REVIEWED_SOURCE_HISTORY_ADAPTER_AND_COMPLETENESS_ASSESSMENT
```

## Exact ancestry

PR #81 binds the exact merged PR #80 state:

- repository main: `271afbc2b22d39eb6e8cd13f49fd55c4f0c45ba2`;
- PR #80 constructor blob: `9135f056d036fd0207a3daead2599ac2520274be`;
- PR #80 construction specification SHA-256:
  `75fe157d1b767cf374e5c2a27cc3d96434aa12f2214fc37d7c91b1e7127eb4b7`;
- PR #80 construction specification size: `2,330` bytes.

It also binds the frozen successor research ancestry:

- PR #69 source corpus SHA-256:
  `c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0`;
- source files: `66`;
- source fixtures: `21,226`;
- training seasons: `2020-21` through `2023-24`;
- evaluation seasons: `2024-25` and `2025-26`;
- Elo initialization semantics:
  `1500_REPLAY_INITIAL_STATE_ASSUMPTION_NOT_OBSERVED_EVIDENCE`.

The exact frozen model league-code universe is:

```text
B1 D1 E0 F1 G1 I1 N1 P1 SC0 SP1 T1
```

That set is mechanically checked against the committed real successor receipt.

The PR #81 protocol is canonical sorted compact UTF-8 JSON plus a final newline:

- SHA-256:
  `b8da8a64b5b4c689eeed7fbacb9a093a5ba7409387b6bf61db6a54d9773b96bd`;
- size: `4,145` bytes.

## Why this boundary is necessary

The successor's Elo predictor is not a target-team-only statistic.

A target team's rating depends on its opponents' ratings. Those opponent ratings
in turn depend on their earlier opponents. Therefore a source-history adapter
cannot fetch only the two teams in the target fixture and call the result
complete.

The prospective replay requires a defensible source corpus and initialization
boundary.

PR #81 explicitly forbids choosing a convenient recent date and initializing all
teams at `1500` there. The initialization boundary must be proven equivalent to
the frozen PR #69 replay-start semantics rather than selected after seeing a
result.

## Candidate reviewed source

The protocol selects only the reviewed adapter-scoped source capability:

```text
fotmob_data_matches_reviewed_catalog
```

It does **not** silently substitute the legacy `fotmob_historical` loader or any
other older FotMob worker merely because those modules historically parsed
scores.

The exact current reviewed capability facts are:

```text
reliable_fixture_identity = CONFIRMED
full_time_score           = NOT_CAPTURED
historical_coverage       = UNKNOWN
```

These facts come from the repository-reviewed source-capability registry.

The reviewed `/api/data/matches` schema does expose home/away `score` scalar
fields structurally, but the reviewed schema assessment deliberately classifies
their full-time meaning as:

```text
AMBIGUOUS
```

The reviewed catalog chain consequently does not promote those scalars into
full-time result semantics.

The currently reviewed match-details raw-capture boundary is also explicitly a
**pre-kickoff** boundary. Its manifest rejects captures observed at or after
kickoff. It therefore cannot simply be repurposed as post-match final-result
evidence without a new reviewed boundary.

PR #81 records those limitations instead of routing around them.

## Required result-history row semantics

Any PR #82 adapter claiming to produce PR #80 history rows must prove all of the
following:

1. one FotMob source namespace with exact source fixture and team identities;
2. exact kickoff UTC plus an explicit source-local time basis;
3. explicit non-negative final home and away goals;
4. final-result evidence observed after the source fixture kickoff and by the
   target analysis `as_of`;
5. canonical capture and row lineage for every admitted result;
6. no target fixture inside its own prior-result history;
7. no cross-source identity inference.

Numeric score coincidence is not enough. The score source must have reviewed
finished/settlement meaning.

## Completeness proof

A positive completeness result requires **all** of the following.

### Initialization

The adapter must prove the exact Elo replay initialization boundary against the
frozen PR #69 semantics.

This is a model-scale requirement. Moving the `1500` initialization point changes
ratings and therefore changes the predictor distribution seen by the fitted
successor.

### Competition universe

All eleven frozen model leagues require an explicit reviewed mapping to exact
FotMob competition identities.

The protocol does not pre-register guessed FotMob league IDs. That mapping is an
evidence result for the execution boundary, not something to infer from league
names or legacy constants.

### Daily coverage

The required source interval must cover every calendar date from the proven
initialization boundary through the day before the target fixture.

A missing, failed, malformed, or unreviewed daily capture is a completeness gap.
The adapter cannot silently treat a failed request as a day with zero fixtures.

### Finished-result coverage

Every in-scope finished fixture discovered in the required source coverage must
have reviewed final-result evidence.

A fixture with identity but no reviewed final result is not silently dropped.
It produces a blocked result-evidence gap.

### Identity and chronology

The execution must fail closed for duplicate fixture identity, same-team
same-kickoff ambiguity, incompatible source-local/UTC ordering, or unresolved
team identity continuity.

Postponed, cancelled, abandoned, or rearranged fixtures require explicit
reviewed disposition. They cannot vanish because their status is inconvenient.

## Frozen result vocabulary

The later execution may emit only the pre-registered statuses:

```text
QUALIFIED_COMPLETE_REVIEWED_HISTORY
BLOCKED_CURRENT_REVIEWED_SOURCE_NO_FINAL_SCORE_SEMANTICS
BLOCKED_HISTORICAL_COVERAGE_UNPROVEN
BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN
BLOCKED_LEAGUE_MAPPING_UNPROVEN
BLOCKED_REQUIRED_DATE_GAP
BLOCKED_RESULT_EVIDENCE_GAP
BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT
```

The presence of a positive vocabulary value does not mean PR #81 grants it. PR
#81 is explicitly not executed.

## What PR #81 does not authorize

Every downstream safety flag remains exact `false`.

This protocol does not authorize:

- a source-history adapter;
- a source-history completeness proof;
- use of any history as PR #80 constructor input;
- successor live-input qualification;
- successor candidate approval;
- expected-goals execution or production use;
- score matrices;
- probability inference or adjustment;
- production calibration;
- pricing;
- market activation;
- selection;
- production approval;
- betting.

## Next implementation boundary

PR #82 should execute this frozen contract, not weaken it.

The first execution question is intentionally uncomfortable: can ATHENA's
**currently reviewed** FotMob source chain prove final-result semantics and the
required historical coverage? If not, PR #82 must return the appropriate blocked
status and identify the smallest missing reviewed source boundary.

A blocked result is useful evidence. It tells us exactly whether the next piece
is post-match result capture/review, competition mapping, initialization-boundary
proof, daily historical coverage, or another lineage issue. It is preferable to
a fabricated `1500` reset or a partial history that happens to produce plausible
numbers.
