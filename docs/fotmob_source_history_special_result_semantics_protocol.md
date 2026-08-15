# FotMob source-history special-result semantics protocol

## Purpose

This boundary pre-registers how ATHENA may classify the non-ordinary FotMob
result states preserved by the completed source-history campaign.

PR #108 qualified the initial eleven domestic-league `primaryId` families as
stable FotMob source-scoped competition identities. Historical coverage still
remains fail-closed because PR #105 also preserved special finished results,
unresolved non-results, cross-date rearrangements, and an initialization
boundary that have not yet been dispositioned.

This PR freezes the **special-result semantics before execution**. It performs no
new FotMob request, does not execute the campaign evidence pass, does not mutate
source or competition registries, and grants no model, pricing, selection,
production, or BET authority.

## Exact ancestry

The protocol starts from merged `main`:

`fa3aa9de0a679e6efebc1a53a245bd8b418f3839`

The PR #108 mapping qualification receipt remains:

- SHA-256: `fdb55feef9585fe0aa2668ddb9ac9a6eb8e63ac8870c06cdb7917d1f996e7bc9`
- size: `13,681` bytes
- mapping qualification: proven for the initial eleven source-scoped families
- historical coverage: still false

The underlying PR #105 completeness receipt remains:

- SHA-256: `a8c5a704e06853d6debfc029653132ca201b98c1fc8a32b3e3095db18f8e1363`
- size: `11,995` bytes

The preserved campaign artifact is unchanged: 4,410 successful captures over
2,205 UTC request dates from 2020-08-01 through 2026-08-14.

## Frozen evidence scope

PR #105 preserved 31 unique finished fixtures outside the reviewed ordinary-FT
semantic gate:

- 25 awarded wins;
- 3 after-extra-time results;
- 3 after-penalties results.

It also preserved 21 unresolved non-result fixture IDs:

- 13 abandoned;
- 6 cancelled;
- 2 postponed.

The protocol binds execution to the exact PR #105 special-result and unresolved-state
projection hashes, so the later evidence pass cannot quietly change its target
corpus after seeing results.

The awarded set contains 26 observations because fixture `3932603` appears as an
awarded terminal source state on request dates `20230220` and `20230305`. Those
two occurrences remain distinct evidence until the later chronology boundary.

## Exact semantic classes

### Awarded win

The reviewed source signature is `finished=true`, `started=true`,
`cancelled=false`, `awarded=true`, with
`AW / <empty shortKey> / Awarded win / awarded_win`.

An awarded score is an administrative source result. It is not evidence of goals
produced by normal played football and must not be used as an observed-goal
training target.

### After extra time

The reviewed source signature is `finished=true`, `started=true`,
`cancelled=false`, `awarded=false`, with
`AET / afterextratime_short / After extra time / afterextra`.

The source finished score includes extra-time scope. ATHENA must not reinterpret
that score as the 90-minute regulation score.

### After penalties

The reviewed source signature is `finished=true`, `started=true`,
`cancelled=false`, `awarded=false`, with
`Pen / penalties_short / After penalties / afterpenalties`.

The source `home.score` and `away.score` scalars remain distinct from the
separate `home.penScore` and `away.penScore` fields. The later qualification pass
must preserve those fields and `eliminatedTeamId` as evidence. It may not combine
shootout values with the base score or claim that either pair is a 90-minute
regulation score.

### Abandoned

The reviewed source signature is `finished=true`, `started=true`,
`cancelled=true`, awarded absent or false, with
`Ab / aborted_short / Abandoned / aborted`.

`finished=true` does not make an abandoned score a completed match result. Any
score represents a partial source state and must not be promoted to ordinary
regulation-time history.

### Cancelled

The reviewed source signature is `finished=false`, `started=false`,
`cancelled=true`, awarded absent or false, with
`Can / cancelled_short / Cancelled / cancelled`.

Some preserved cancelled records contain non-zero team score scalars. Under this
protocol those values are non-result metadata and cannot be treated as played
goals.

### Postponed

The reviewed source signature is `finished=false`, `started=false`,
`cancelled=true`, awarded absent or false, with
`PP / postponed_short / Postponed / postponed`.

Any score scalar on a postponed state is non-result metadata and cannot be
promoted to a played result.

## Model-history disposition

All six reviewed classes use:

`EXCLUDE_FROM_ORDINARY_REGULATION_TIME_MODEL_HISTORY`

Every observation remains preserved as source evidence under:

`PRESERVE_AS_SOURCE_EVIDENCE_NO_SILENT_DROP_OR_COERCION`

This is deliberate. Awarded scores are administrative, AET and penalty scores
exceed the ordinary 90-minute scope, and abandoned/cancelled/postponed states
are not completed ordinary results. None may silently enter the successor model
as an ordinary regulation-time target.

This does not prevent later separately reviewed knockout or special-result
models. It only prevents incompatible source states from masquerading as normal
league-history observations.

## Status ID is not semantics

`statusId` may be retained as supporting evidence, but it is never sufficient by
itself. Qualification requires the exact reviewed reason tuple and exact
finished/started/cancelled/awarded policy. A familiar-looking score can never
override the source state.

## Cross-date chronology remains separate

PR #105 found 250 source fixture IDs whose kickoff changes across request dates.
Some also transition between states, including postponed/cancelled to ordinary
FT and cancelled to awarded.

This protocol does not pick a convenient final observation or canonical kickoff.
The execution pass may classify each observed state, but cross-date transitions
remain blocked for the later rearrangement/chronology boundary.

Fixture `3932603`, which appears as an awarded terminal state on two request
dates, must remain two source occurrences until chronology is explicitly
resolved.

## Qualification requirements

The next execution boundary must use only the exact preserved PR #105 campaign
artifact with no network reacquisition, revalidate PR #108 competition mapping,
account for every fixture in the frozen special and unresolved projections,
preserve exact provenance and relevant status/score fields, fail closed on
unknown variants, keep shootout fields separate from base scores, produce a
deterministic canonical receipt, and mutate no source capability, competition,
model, pricing, selection, or betting registry.

## Deliberately unresolved

This protocol does not resolve the 250 rearranged/kickoff-changing fixture IDs,
canonical cross-date chronology, PR #69 initialization equivalence, overall
historical completeness, bookmaker settlement semantics, or broader competition
qualification beyond the already reviewed initial proof set.

## Canonical identity

- SHA-256: `5fc2d1c089ecea5fd3ab4b9920f578ac25b555c0d89bebad4eedbfcd80c3cf87`
- size: `7,040` bytes

## Next reviewed boundary

`EXECUTE_REVIEWED_FOTMOB_SOURCE_HISTORY_SPECIAL_RESULT_SEMANTICS_QUALIFICATION`

## Safety

Every authorization field remains exact `false`. No special result is admitted
to ordinary regulation-time model history. No source-history adapter is
promoted. Historical completeness remains unproven. Expected-goals,
score-matrix, probability, calibration, pricing, market activation, selection,
production, and BET authority all remain disabled.
