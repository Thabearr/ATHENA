# FotMob historical source-history completeness and materialization protocol

## Purpose

PR #118 freezes the next evidence boundary after PR #117.

PR #117 qualified a **historical-only ordinary-FT adapter** for the exact preserved FotMob campaign. It did not prove historical completeness and it materialized zero history rows. PR #118 defines, before execution, what ATHENA must prove before the `21,326` on-or-after-floor ordinary-FT candidates can become a reviewed historical result corpus.

The frozen state is:

`PRE_REGISTERED_NOT_EXECUTED_HISTORICAL_COVERAGE_UNPROVEN`

The next boundary is:

`EXECUTE_REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_COMPLETENESS_AND_MATERIALIZATION_QUALIFICATION`

PR #118 executes nothing and authorizes nothing.

## Exact ancestry

The protocol binds current `main`:

`7e0e43852ff6527021de6ece52394b44bf222234`

It revalidates:

- PR #81 source-history completeness protocol: `9d16fcc79e9809a82ef154c75b8e263f782a4e1d4723b57cc216d893c88780ec`, `4,223` bytes;
- PR #99 derived ordinary-FT completeness protocol: `edddd7445bb9bb6ed2db4778b6ab48da9489ae6efac822b6e6c139992275bf87`, `5,741` bytes;
- PR #110 special-result receipt: `7d6bb5c86391c45abdbb588a27325c99ebf88c4753f75c108387e2c4d3dbb99d`;
- PR #112 rearrangement chronology receipt: `58c7a275580cc74489269a66de2836544e78ca232693d5283f1813ee817d3fc0`;
- PR #114 Elo-initialization receipt: `fbbec0b858c3e9630d9f4c7dec630012f57811de52d300db3a11b781a719e110`;
- PR #117 historical-adapter receipt: `a8f06a9d789b20b4ef49766bd771fb5c4d13c4be657ac6a5fc8f284701054020`, `5,081` bytes;
- PR #117 ordinary-FT projection: `eddb7f5b58eb3cb92087dc7bf57a45a270aebabce38641cd3b4ffc2277d67ed3`, `22,080,831` bytes;
- PR #80 construction specification: `75fe157d1b767cf374e5c2a27cc3d96434aa12f2214fc37d7c91b1e7127eb4b7`, `2,330` bytes.

## Contract reconciliation

PR #81 remains authoritative for source-history completeness: initialization, daily coverage, reviewed result evidence, source-scoped identity, chronology, source-local/UTC consistency, explicit special-state disposition, and no silent target-team filtering.

PR #99 remains unchanged for the **prospective** derived ordinary-FT path. Its prospective adapter is not weakened.

For the exact frozen PR #105 campaign only, the PR #117-qualified historical adapter is the reviewed historical result adapter. This is a campaign-specific reviewed bridge, not a global FotMob schema claim and not a mutation of the prospective adapter.

The eleven model families remain only ATHENA's currently validated historical/model universe, not ATHENA's full competition universe.

## Frozen source envelope

The evidence envelope remains:

- source namespace `fotmob_data_matches_reviewed_ordinary_ft_finished_score`;
- artifact ID `9249856559`;
- artifact SHA-256 `7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f`;
- artifact size `61,886,753` bytes;
- embedded cache SHA-256 `cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6`;
- embedded cache size `61,881,610` bytes;
- request dates `2020-08-01` through `2026-08-14`;
- request timezone `UTC`;
- `ccode3=NGA`;
- qualified corpus **display-time basis** `Europe/Oslo`;
- PR #80 source-local semantic equivalence remains `UNPROVEN`.

The `Europe/Oslo` result is deliberately described as a frozen-corpus display-time projection. It does **not** prove that FotMob's display time is semantically equivalent to the unresolved PR #69 football-data.co.uk source-local timestamp basis.

The global source-capability registry must continue to report historical coverage as `UNKNOWN`. Any future positive result here is scoped only to this exact eleven-family/date envelope.

## Frozen evidence accounting

Execution must reproduce exactly:

- `2,205` request dates and `4,410` capture manifests;
- `21,640` target-family fixture/date occurrences;
- `21,336` PR #117-qualified ordinary-FT occurrences;
- `304` reviewed special-state occurrences;
- `10` ordinary-FT occurrences before their PR #114 family floor;
- `21,326` on-or-after-floor materialization candidates;
- `21,336` unique ordinary-FT source fixture IDs and zero duplicate ordinary IDs.

The `21,326` candidate counts remain:

| Family | Count |
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

The `304` special-state occurrences remain: `20` abandoned, `3` after-extra-time, `3` after-penalties, `26` awarded wins, `11` cancelled, and `241` postponed.

## Completeness proof required

A positive execution must re-run the exact frozen evidence rather than trust summary counts. All `2,205` request dates must exist with exactly two canonical manifests per date using the same `timezone=UTC` and `ccode3=NGA`; a missing, failed, malformed, or unreviewed date cannot be interpreted as an empty football day.

The PR #114 family floors remain binding. Pre-floor observations stay evidence only. Every target-family fixture/date occurrence must close into either the PR #117 ordinary-FT class or a PR #110 reviewed special state, with PR #112 chronology still authoritative.

Every ordinary materialization candidate must prove final-result evidence observed strictly after canonical kickoff. Execution must fail closed for duplicate fixture identity, same-team/same-kickoff ambiguity, unresolved source-scoped team identity, request-date/kickoff-date conflict, special-state drift, display-time/UTC ordering conflict, or non-deterministic materialization.

## Historical row materialization

Only the `21,326` ordinary-FT occurrences on or after their PR #114 floor may become historical materialization rows after a positive completeness execution.

The `10` pre-floor ordinary observations remain evidence only and may not seed Elo, form, fatigue, or PR #80 history. The `304` special-state observations remain evidence/disposition only and may never be converted into ordinary regulation-time results.

For each eligible ordinary row:

- source namespace is the exact reviewed derived FotMob source key;
- fixture and team identifiers are exact decimal strings of positive FotMob source IDs;
- kickoff UTC is the PR #117 canonical `status.utcTime`;
- a **source-local kickoff candidate** is derived from canonical UTC through the frozen `Europe/Oslo` display basis and made naive only as a structural PR #80 representation; PR #69 source-local semantic equivalence remains unproven;
- goals are the exact PR #117 non-negative integer scores;
- `observed_at` is the earlier of the two qualified manifest observations and must be strictly after kickoff;
- `evidence_sha256` is the SHA-256 of the exact canonical PR #117 projection record binding both manifest lineages;
- `evidence_reference` deterministically binds the frozen campaign, request date, and source fixture ID.

Each row must **structurally** satisfy the unmodified PR #80 `ProspectiveMatchEvidence` invariants. Structural validation does not authorize PR #80 use and does not prove PR #69 source-local semantic equivalence.

The materialized history projection must be deterministic canonical evidence with count, size, and SHA-256 frozen in the execution receipt.

## Materialization is not PR #80 authorization

Even a positive execution remains narrower than using this corpus for a target prediction. A later target-specific boundary must still enforce target-fixture exclusion, strictly-prior local and UTC ordering, `observed_at <= target as_of`, no same-team/same-kickoff ambiguity, and a complete source-history envelope through the target's required date.

## Historical ceiling and future extension

The frozen campaign ends on `2026-08-14`. The historical adapter is not authorized to acquire or qualify later dates.

Any target requiring a later request date remains incomplete until a separately reviewed prospective extension is qualified. That extension must be calendar-date contiguous with `2026-08-14`, contain no missing/failed/unreviewed dates, and use separately reviewed prospective acquisition and adapter semantics. Any difference in historical versus prospective row-lineage semantics requires an explicit bridge review rather than silent concatenation.

## Positive-result authority boundary

A future positive execution may establish only scoped frozen historical completeness, authorization to materialize exactly `21,326` ordinary-FT history rows, and approval of the PR #117 historical adapter for this frozen campaign scope.

It must still leave false: global source-capability historical coverage confirmation, source-capability/competition-registry mutation, PR #80 constructor input, successor live-input qualification, successor-candidate approval, model training, expected-goals production, probability inference, pricing, market activation, selection, production approval, and BET authority.

## Frozen result vocabulary

The execution may emit only:

- `QUALIFIED_COMPLETE_FROZEN_HISTORICAL_HISTORY_THROUGH_2026_08_14`
- `BLOCKED_PR117_HISTORICAL_ADAPTER_QUALIFICATION_DRIFT`
- `BLOCKED_PR81_OR_PR99_COMPLETENESS_CONTRACT_DRIFT`
- `BLOCKED_INITIALIZATION_BOUNDARY_DRIFT`
- `BLOCKED_REQUIRED_DATE_GAP`
- `BLOCKED_RESULT_EVIDENCE_GAP`
- `BLOCKED_SPECIAL_RESULT_OR_CHRONOLOGY_DISPOSITION_DRIFT`
- `BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT`
- `BLOCKED_SOURCE_LOCAL_TIME_BASIS_CONFLICT`
- `BLOCKED_OBSERVATION_TIME_NOT_AFTER_KICKOFF`
- `BLOCKED_MATERIALIZATION_ROW_INVARIANT`
- `BLOCKED_MATERIALIZATION_PROJECTION_NONDETERMINISTIC`

Before execution, the disposition remains `BLOCKED_HISTORICAL_COVERAGE_UNPROVEN` and every PR #118 safety flag remains exact `false`.

## Canonical protocol identity

The protocol is canonical compact sorted UTF-8 JSON plus one final newline:

- SHA-256 `1917db656004305df9ce56dfdf049347733a591bde08d465c105bb7d98d1e6de`;
- size `9,962` bytes.
