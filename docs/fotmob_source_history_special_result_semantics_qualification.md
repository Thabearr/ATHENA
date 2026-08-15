# FotMob source-history special-result semantics qualification

## Purpose

This boundary executes the PR #109 special-result semantics contract against the exact preserved PR #105 FotMob campaign artifact. It performs no new FotMob request and does not materialize or extend model history.

The result is narrow: the six reviewed non-ordinary source states are now qualified as **source-state semantics and dispositions**. They remain excluded from ordinary regulation-time model history. Rearrangement chronology, initialization equivalence, and overall historical completeness remain fail-closed.

## Exact ancestry

- base/main: `2d66af0d176828e1a4efbea2abef6385b694330f`
- PR #109 protocol SHA-256: `5fc2d1c089ecea5fd3ab4b9920f578ac25b555c0d89bebad4eedbfcd80c3cf87`
- PR #109 protocol size: `7,040` bytes
- PR #108 mapping receipt SHA-256: `fdb55feef9585fe0aa2668ddb9ac9a6eb8e63ac8870c06cdb7917d1f996e7bc9`
- PR #105 completeness receipt SHA-256: `a8c5a704e06853d6debfc029653132ca201b98c1fc8a32b3e3095db18f8e1363`
- preserved campaign artifact ID: `9249856559`
- artifact SHA-256: `7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f`
- artifact size: `61,886,753` bytes

The reproduction script refuses any artifact or embedded research-cache hash/size drift.

## What the preserved campaign actually contains

Across the initial eleven qualified competition families, the exact six reviewed special-state signatures occur on **295 unique fixture IDs** and **304 fixture/request-date observations**. Each observation has two same-date campaign captures, for **608 raw capture observations**. The A/B copies agree exactly on the reviewed identity, kickoff, status/reason and relevant score fields; conflict count is zero.

The special-state projection is:

- SHA-256: `ad2881eb67bec1988462953acc8d55d59366667b47f3b7c55e026d644b85c990`
- size: `211,526` bytes

The wider history projection for those 295 fixture IDs, including later ordinary-FT observations needed only to preserve chronology, is:

- SHA-256: `459c94fd53430663562d9ce614ca2b52b518b6a8f06f6661b27b555c567c281d`
- size: `380,539` bytes
- fixture/request-date rows: `547`

## Qualified state semantics

| Source state | Unique fixture IDs observed | Fixture/date observations | Raw A/B observations | Status IDs | Disposition |
|---|---:|---:|---:|---|---|
| Awarded win | 25 | 26 | 52 | 190 | administrative source result; exclude from ordinary model history |
| After extra time | 3 | 3 | 6 | 11 | score includes extra-time scope; exclude |
| After penalties | 3 | 3 | 6 | 13 | base score and `penScore` stay separate; exclude |
| Abandoned | 20 | 20 | 40 | 17 | partial source state; exclude |
| Cancelled | 11 | 11 | 22 | 106 | non-result state; exclude |
| Postponed | 239 | 241 | 482 | 5 | non-result state; exclude |

Every row remains preserved as source evidence under `PRESERVE_AS_SOURCE_EVIDENCE_NO_SILENT_DROP_OR_COERCION`.

The three penalty observations all preserve both teams' `penScore` fields separately from the base score and preserve `eliminatedTeamId`. The campaign also contains 15 abandoned observations and 9 cancelled observations with at least one non-zero team score scalar. Those values are explicitly **not** promoted to played final results.

## Frozen PR #105 blocker membership remains intact

The PR #105 terminal special-result sets are accounted for exactly: 25 awarded wins, 3 AET fixtures and 3 penalty fixtures. Its unresolved sets are also accounted for exactly: 13 abandoned, 6 cancelled and 2 postponed fixtures.

The larger observed abandoned/cancelled/postponed counts are not a contradiction. They include earlier source states for fixtures that later reappear under another kickoff/state. Those transitions are evidence for the chronology boundary, not a reason to rewrite the frozen unresolved sets.

## Chronology remains unresolved

The same **250** rearranged/kickoff-changing fixture IDs remain blocked. Their preserved transition summary is unchanged:

- 234 `POSTPONED -> ORDINARY_FT`
- 7 `ABANDONED -> ORDINARY_FT`
- 5 `CANCELLED -> AWARDED_WIN`
- 2 `POSTPONED -> POSTPONED -> ORDINARY_FT`
- 1 `POSTPONED -> AWARDED_WIN`
- 1 `AWARDED_WIN -> AWARDED_WIN`

No convenient final observation is chosen. Fixture `3932603` remains two awarded source occurrences on request dates `20230220` and `20230305` until chronology is reviewed explicitly.

## What changed

`BLOCKED_NON_ORDINARY_FT_RESULT_REQUIRES_SEPARATE_REVIEW` is resolved **only as a semantics/disposition blocker**: all six reviewed classes have an exact source-state meaning and are excluded from ordinary regulation-time model history.

The following remain blocked:

- `BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT`
- `BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN`
- `BLOCKED_HISTORICAL_COVERAGE_UNPROVEN`

Historical completeness is therefore still false.

## Safety

No source-history adapter is approved. No special-result rows are authorized for model history. No ordinary-FT history extension occurs. No source or competition registry is mutated. Expected-goals, score-matrix, probabilities, calibration, pricing, market activation, selection, production and BET authority all remain false.

## Canonical receipt

- SHA-256: `7d6bb5c86391c45abdbb588a27325c99ebf88c4753f75c108387e2c4d3dbb99d`
- size: `8,558` bytes

## Next reviewed boundary

`PRE_REGISTER_REVIEWED_FOTMOB_SOURCE_HISTORY_REARRANGEMENT_CHRONOLOGY_SEMANTICS_PROTOCOL`
