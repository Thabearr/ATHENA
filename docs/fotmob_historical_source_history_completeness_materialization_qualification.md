# FotMob historical source-history completeness and materialization qualification

## Purpose

PR #119 executes the PR #118 preregistered boundary against the exact preserved FotMob campaign. It answers one narrow question: can ATHENA prove a complete reviewed historical source-history envelope for the frozen eleven-family campaign through `2026-08-14` and deterministically materialize the ordinary-FT rows that are on or after the PR #114 Elo initialization floors?

The answer is **yes for that exact frozen scope only**.

The qualification state is:

`EXECUTED_SCOPED_HISTORICAL_COMPLETENESS_QUALIFIED_ROWS_MATERIALIZED_PR80_USE_UNREVIEWED`

The admitted PR #118 result status is:

`QUALIFIED_COMPLETE_FROZEN_HISTORICAL_HISTORY_THROUGH_2026_08_14`

This resolves the historical-coverage blocker only for the exact frozen campaign scope. It does not promote the global FotMob source capability, authorize PR #80 target use, train a model, infer probabilities, price a market, select a bet, or authorize BET.

## Exact ancestry

Execution is anchored to repository `main`:

`2b2f6390f077b562c185768db030c7c4e61a06de`

The exact PR #118 protocol is:

- protocol ID `REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_COMPLETENESS_AND_MATERIALIZATION_PROTOCOL_V1`;
- implementation blob `be7119f06804093959b6730c2fe8ac05ea4d2f05`;
- canonical SHA-256 `1917db656004305df9ce56dfdf049347733a591bde08d465c105bb7d98d1e6de`;
- canonical size `9,962` bytes.

The execution also revalidates the frozen PR #81 and PR #99 completeness contracts plus the PR #110 special-result, PR #112 chronology, PR #114 Elo initialization, and PR #117 historical-adapter qualifications.

## Frozen source evidence

The exact source artifact remains:

- artifact ID `9249856559`;
- artifact name `fotmob-ordinary-ft-source-history-campaign-31887523012`;
- artifact SHA-256 `7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f`;
- artifact size `61,886,753` bytes;
- embedded research-cache SHA-256 `cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6`;
- embedded cache size `61,881,610` bytes;
- request dates `2020-08-01` through `2026-08-14`;
- request timezone `UTC`;
- `ccode3=NGA`.

No network reacquisition is part of PR #119.

## Completeness result

The exact preserved campaign was re-executed through the already-qualified PR #117 historical adapter. The following accounting closes exactly:

- `2,205` required calendar request dates;
- `4,410` capture manifests;
- `21,640` target-family fixture/date occurrences;
- `21,336` qualified ordinary-FT occurrences;
- `304` reviewed special-state occurrences;
- `10` ordinary-FT occurrences before their PR #114 family floor;
- `21,326` ordinary-FT materialization candidates on or after the floors;
- `21,336` unique ordinary-FT source fixture IDs;
- zero duplicate ordinary-FT source fixture IDs.

All required dates are present. There are zero capture-pair cardinality failures, request-identity mismatches, manifest/raw lineage mismatches, unreviewed target states, materializable duplicate fixture IDs, same-team/same-kickoff conflicts, request-date/kickoff-date mismatches, source display-time mismatches, source-display-local/UTC ordering disagreements, or post-kickoff observation failures.

The frozen eleven-family materialization counts remain:

| Family | Rows |
|---|---:|
| B1 | 1,933 |
| D1 | 1,835 |
| E0 | 2,280 |
| F1 | 2,056 |
| G1 | 1,431 |
| I1 | 2,280 |
| N1 | 1,865 |
| P1 | 1,846 |
| SC0 | 1,380 |
| SP1 | 2,280 |
| T1 | 2,140 |

These eleven families remain ATHENA's currently validated historical/model universe, not the complete ATHENA competition universe.

## Special states remain excluded

The `304` reviewed non-ordinary occurrences remain evidence/disposition only:

| State | Occurrences |
|---|---:|
| ABANDONED | 20 |
| AFTER_EXTRA_TIME | 3 |
| AFTER_PENALTIES | 3 |
| AWARDED_WIN | 26 |
| CANCELLED | 11 |
| POSTPONED | 241 |

They are not converted into ordinary regulation-time history. The ten pre-floor ordinary-FT observations are also preserved as evidence only and do not enter the materialized history corpus.

## Deterministic historical materialization

PR #119 materializes exactly `21,326` rows in memory and can reproduce the canonical JSON-lines projection with the execution script.

Each row binds:

- the reviewed derived FotMob source namespace;
- exact FotMob fixture and team IDs as decimal strings;
- canonical kickoff UTC;
- an `Europe/Oslo` display-time candidate derived from kickoff UTC and made naive for structural PR #80 representation;
- exact non-negative final home and away goals;
- the earlier of the two PR #117-qualified manifest observation times;
- SHA-256 of the exact canonical PR #117 projection record as row evidence lineage;
- a deterministic frozen-campaign/request-date/source-fixture evidence reference.

Every row structurally satisfies the unchanged PR #80 `ProspectiveMatchEvidence` invariants. Final-result evidence is strictly after kickoff for all `21,326` rows.

The deterministic materialization projection is:

- row count `21,326`;
- SHA-256 `e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2`;
- size `10,545,099` bytes;
- ordering `source_local_kickoff`, then `fixture_identifier`.

The large projection is reproducible from the exact preserved artifact and is not required to be checked into the repository.

## Important source-local boundary

PR #118 deliberately corrected an earlier over-strong interpretation. PR #119 preserves that correction.

`Europe/Oslo` is a qualified FotMob display-time basis for this frozen campaign. It is **not yet proven semantically equivalent** to the unresolved source-local time semantics inherited from PR #69 / PR #80.

PR #119 proves that the derived display-local ordering and UTC ordering agree for this materialized corpus. That is not the same claim as proving that FotMob's wall-clock basis is the exact historical source-local basis used by the PR #69 replay.

Therefore:

- `pr80_source_local_semantic_equivalence_proven = false`;
- `pr80_constructor_input_authorized = false`.

## Scoped authority versus global authority

PR #119 may now say, for this exact frozen campaign only:

- scoped historical source-history completeness is proven through `2026-08-14`;
- the PR #117 historical adapter is approved for this frozen campaign scope;
- the exact `21,326` ordinary-FT rows are materialized and their scoped materialization is authorized.

It still may **not** say:

- global FotMob historical coverage is confirmed;
- the source capability registry should be mutated;
- PR #80 constructor input is authorized;
- successor live inputs or the successor model are approved;
- model training, expected-goals production, probability inference, pricing, market activation, selection, production, or BET are authorized.

The global source capability therefore remains `historical_coverage=UNKNOWN`.

## Historical ceiling

The frozen historical campaign ends on `2026-08-14`.

Any target requiring later dates remains outside this historical completeness envelope until ATHENA separately qualifies a contiguous prospective extension beginning after that ceiling. No later date may be silently inferred from the frozen historical adapter.

## Durable receipt

The canonical PR #119 receipt is:

- SHA-256 `da8037cd9b4a4f91be942a4052e76134b66cc94221ed66e624c14008c9e562a0`;
- size `6,810` bytes.

## Next boundary

The next narrow boundary is:

`PRE_REGISTER_REVIEWED_FOTMOB_PR80_SOURCE_LOCAL_TIME_SEMANTIC_EQUIVALENCE_PROTOCOL`

This keeps the source-local semantic question separate from the already-qualified frozen historical completeness/materialization result and separate again from future prospective extension and target-specific PR #80 use.
