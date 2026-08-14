# Prospective successor source-history adapter and completeness protocol

## Purpose

PR #81 freezes the next boundary after PR #80 before ATHENA adapts or judges any
real prospective result-history corpus.

PR #80 proved that the five raw successor inputs can be reconstructed with the
same mathematics used by the historical successor path **if** an adequate
source-scoped prior-result history is supplied. PR #81 pre-registers what
"adequate" must mean before any execution result is seen.

The frozen state is:

```text
PRE_REGISTERED_NOT_EXECUTED_NO_SOURCE_HISTORY_QUALIFIED
```

The next boundary is:

```text
EXECUTE_REVIEWED_SOURCE_HISTORY_ADAPTER_AND_COMPLETENESS_ASSESSMENT
```

PR #81 does not execute an adapter and grants no positive qualification.

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
  `9d16fcc79e9809a82ef154c75b8e263f782a4e1d4723b57cc216d893c88780ec`;
- size: `4,223` bytes.

## Why a completeness proof is required

The successor Elo predictor is not a target-team-only statistic. A target team's
rating depends on opponent ratings, and those opponent ratings depend on earlier
opponents. A partial history that contains only the two teams in the target
fixture can therefore produce plausible numbers while using the wrong Elo state.

PR #81 also forbids choosing a convenient recent date and resetting all ratings
to `1500`. The initialization boundary must be proven equivalent to the frozen
PR #69 replay-start semantics.

## Candidate reviewed source

The protocol selects only:

```text
fotmob_data_matches_reviewed_catalog
```

It does **not** substitute the legacy `fotmob_historical` loader or another old
FotMob worker merely because legacy code once parsed scores.

The exact current reviewed capability facts are:

```text
reliable_fixture_identity = CONFIRMED
full_time_score           = NOT_CAPTURED
historical_coverage       = UNKNOWN
```

The reviewed `/api/data/matches` schema structurally contains home/away `score`
scalars, but their full-time meaning remains explicitly `AMBIGUOUS`. The reviewed
catalog path therefore does not promote them into final-result semantics.

The currently reviewed match-details raw-capture path is also strictly
pre-kickoff: its manifest rejects captures observed at or after kickoff. It cannot
be silently repurposed as post-match result evidence.

## Required history-row semantics

Any later adapter claiming to produce PR #80 history rows must prove:

1. one FotMob source namespace with exact source fixture and team identities;
2. exact kickoff UTC and an explicit source-local time basis;
3. one exact request timezone and `ccode3` across the required daily capture
   interval, so date coverage cannot change meaning from day to day;
4. explicit non-negative final home and away goals;
5. final-result evidence observed after the source fixture kickoff and by the
   target analysis `as_of`;
6. canonical capture and row lineage for every admitted result;
7. no target fixture inside its own prior-result history;
8. no cross-source identity inference.

Numeric score coincidence is not enough. The score source must have reviewed
finished/settlement meaning.

## Completeness proof

A positive result requires all of the following.

### Initialization

The exact Elo replay initialization boundary must be proven against the frozen
PR #69 semantics. Moving the `1500` reset point changes the predictor scale and
therefore changes what the fitted successor receives.

### Competition universe

All eleven frozen model leagues require explicit reviewed mapping to exact FotMob
competition identities. PR #81 does not pre-register guessed FotMob league IDs;
that mapping must be an evidence result of the execution boundary.

### Daily coverage

The required source interval must cover **every calendar date from the proven
initialization boundary through the target fixture's source-local calendar
 date**.

Including the target date matters because the adapter must prove there is no
strictly-prior same-day source result or conflicting target-team fixture hidden by
stopping one day early. The later constructor may still admit only rows strictly
prior to the target kickoff.

A missing, failed, malformed, or unreviewed daily capture is a completeness gap.
A failed request may not be interpreted as a day containing zero fixtures.

### Finished-result coverage

Every in-scope finished fixture discovered in the required interval must have
reviewed final-result evidence. A fixture with identity but no reviewed final
result becomes a result-evidence gap; it is not silently dropped.

### Identity and chronology

Execution must fail closed for duplicate fixture identity, same-team
same-kickoff ambiguity, incompatible source-local/UTC ordering, or unresolved
source-scoped team identity continuity.

Postponed, cancelled, abandoned, or rearranged fixtures require explicit reviewed
disposition. They cannot disappear because their status is inconvenient.

## Frozen result vocabulary

A later execution may emit only:

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

## Safety boundary

Every downstream safety flag remains exact `false`.

PR #81 does not authorize a source-history adapter, source-history completeness,
PR #80 constructor input, successor live-input qualification, successor model
approval, expected-goals execution, score matrices, probability inference or
adjustment, production calibration, pricing, market activation, selection,
production approval, or betting.

## Next implementation boundary

PR #82 should execute this frozen contract rather than weaken it.

The first execution question is intentionally strict: can ATHENA's **currently
reviewed** FotMob chain prove final-result semantics and the required historical
coverage? If not, PR #82 must return the corresponding blocked status and identify
the smallest missing reviewed boundary.

A blocked result is useful evidence. It is preferable to an arbitrary `1500`
reset, guessed competition mapping, or partial history that happens to produce
reasonable-looking numbers.
