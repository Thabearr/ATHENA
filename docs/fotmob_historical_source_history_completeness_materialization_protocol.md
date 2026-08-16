# FotMob historical source-history completeness and materialization protocol

## Purpose

PR #118 freezes the next evidence boundary after PR #117.

PR #117 qualified a **historical-only ordinary-FT adapter** for the exact preserved FotMob campaign. It did not prove historical completeness and it materialized zero history rows. PR #118 therefore defines, before seeing the next execution result, what ATHENA must prove before any of the `21,326` on-or-after-floor ordinary-FT candidates may become a reviewed historical result corpus.

The frozen state is:

`PRE_REGISTERED_NOT_EXECUTED_HISTORICAL_COVERAGE_UNPROVEN`

The next boundary is:

`EXECUTE_REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_COMPLETENESS_AND_MATERIALIZATION_QUALIFICATION`

PR #118 executes nothing and authorizes nothing.

## Exact ancestry

The protocol binds current `main`:

`7e0e43852ff6527021de6ece52394b44bf222234`

It revalidates the exact frozen contracts and receipts that matter to this boundary:

- PR #81 source-history completeness protocol: `9d16fcc79e9809a82ef154c75b8e263f782a4e1d4723b57cc216d893c88780ec`, `4,223` bytes;
- PR #99 derived ordinary-FT source-history completeness protocol: `edddd7445bb9bb6ed2db4778b6ab48da9489ae6efac822b6e6c139992275bf87`, `5,741` bytes;
- PR #110 special-result receipt: `7d6bb5c86391c45abdbb588a27325c99ebf88c4753f75c108387e2c4d3dbb99d`;
- PR #112 rearrangement chronology receipt: `58c7a275580cc74489269a66de2836544e78ca232693d5283f1813ee817d3fc0`;
- PR #114 Elo-initialization receipt: `fbbec0b858c3e9630d9f4c7dec630012f57811de52d300db3a11b781a719e110`;
- PR #117 historical-adapter qualification receipt: `a8f06a9d789b20b4ef49766bd771fb5c4d13c4be657ac6a5fc8f284701054020`, `5,081` bytes;
- PR #117 ordinary-FT evidence projection: `eddb7f5b58eb3cb92087dc7bf57a45a270aebabce38641cd3b4ffc2277d67ed3`, `22,080,831` bytes;
- PR #80 construction specification: `75fe157d1b767cf374e5c2a27cc3d96434aa12f2214fc37d7c91b1e7127eb4b7`, `2,330` bytes.

## Contract reconciliation

PR #118 does not rewrite PR #81 or PR #99.

PR #81 remains the authority for what complete source history means: initialization, daily coverage, reviewed result evidence, source-scoped identity, chronology, source-local/UTC consistency, explicit special-state disposition, and no silent target-team filtering.

PR #99 remains unchanged for the **prospective** derived ordinary-FT source path. Its reusable prospective-adapter requirement is not weakened.

The new bridge is narrower: for the exact frozen PR #105 campaign only, the PR #117-qualified historical adapter is the reviewed historical result adapter. That is a campaign-specific exception created by prior review, not a redefinition of the prospective adapter and not a new global FotMob schema claim.

The eleven model families remain only ATHENA's currently validated historical/model universe. They are not the full competition universe.

## Frozen source envelope

The historical evidence envelope remains:

- source namespace `fotmob_data_matches_reviewed_ordinary_ft_finished_score`;
- artifact ID `9249856559`;
- artifact SHA-256 `7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f`;
- artifact size `61,886,753` bytes;
- embedded cache SHA-256 `cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6`;
- embedded cache size `61,881,610` bytes;
- request dates `2020-08-01` through `2026-08-14`;
- request timezone `UTC`;
- `ccode3=NGA`;
- qualified corpus-local display time basis `Europe/Oslo`.

The global source-capability registry must still report historical coverage as `UNKNOWN`. A future positive result here would be scoped to this exact eleven-family/date envelope and must not be advertised as global FotMob historical coverage.

## Evidence accounting frozen before execution

The next execution must reproduce exactly:

- `2,205` request dates;
- `4,410` capture manifests;
- `21,640` target-family fixture/date occurrences;
- `21,336` PR #117-qualified ordinary-FT occurrences;
- `304` reviewed special-state occurrences;
- `10` ordinary-FT occurrences before their PR #114 family floor;
- `21,326` on-or-after-floor materialization candidates;
- `21,336` unique ordinary-FT source fixture IDs;
- zero duplicate ordinary-FT fixture IDs.

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

The `304` special-state occurrences remain:

| State | Count |
|---|---:|
| ABANDONED | 20 |
| AFTER_EXTRA_TIME | 3 |
| AFTER_PENALTIES | 3 |
| AWARDED_WIN | 26 |
| CANCELLED | 11 |
| POSTPONED | 241 |

## Completeness proof required

A positive execution must re-run the exact frozen evidence rather than trust the summary counts.

All `2,205` calendar request dates must be present with exactly two canonical manifests per date, the same `timezone=UTC`, the same `ccode3=NGA`, and intact raw/manifest lineage. No missing, failed, malformed, or unreviewed date can be interpreted as an empty football day.

The PR #114 family floors remain binding. Pre-floor observations stay evidence only. Every target-family fixture/date occurrence must close into either the PR #117 ordinary-FT class or a PR #110 reviewed special state, with PR #112 chronology still authoritative.

Every ordinary-FT materialization candidate must also prove that its final-result evidence was observed strictly after its canonical kickoff.

Execution must fail closed for duplicate ordinary fixture identity, same-team/same-kickoff ambiguity, unresolved source-scoped team identity, source-local/UTC ordering disagreement, request-date/kickoff-date conflict, special-state drift, or non-deterministic materialization.

## Historical row materialization

PR #118 freezes the intended mapping but does not create rows.

Only the `21,326` ordinary-FT occurrences on or after their PR #114 floor can become materialized rows after a positive completeness execution.

The `10` pre-floor ordinary-FT observations remain evidence only. They may not seed Elo, form, fatigue, or PR #80 history.

The `304` special-state observations remain evidence/disposition only. They are never converted into ordinary regulation-time results.

For each eligible ordinary row:

- source namespace is the exact reviewed derived FotMob source key;
- fixture identifier is the exact decimal string of the positive FotMob fixture ID;
- home and away team identifiers are the exact decimal strings of the positive FotMob team IDs;
- kickoff UTC is the PR #117 canonical `status.utcTime`;
- source-local kickoff is derived from that UTC timestamp through `Europe/Oslo` and then made naive only to satisfy the frozen PR #80 source-local representation;
- home and away goals are the exact PR #117 non-negative integer scores;
- `observed_at` is the earlier of the two qualified manifest observation timestamps and must still be strictly after kickoff;
- `evidence_sha256` is the SHA-256 of the exact canonical PR #117 projection record, which binds both manifest lineages;
- `evidence_reference` deterministically binds the frozen campaign, request date, and source fixture ID.

Every materialized row must satisfy the unmodified PR #80 `ProspectiveMatchEvidence` invariants.

The resulting history projection must itself be canonical and deterministic, with count, size, and SHA-256 frozen in the execution receipt.

## Materialization is not PR #80 authorization

Even a positive execution would remain narrower than using the history in a target prediction.

Materialization may prove that the frozen historical corpus is complete and row-valid for its exact scope. It does **not** by itself authorize PR #80 constructor input.

A later target-specific boundary must still enforce target fixture exclusion, strictly-prior ordering in both source-local and UTC time, `observed_at <= target as_of`, no same-team/same-kickoff ambiguity, and that the target's required date lies inside a complete source-history envelope.

This keeps a corpus proof separate from a live target-use proof.

## Historical ceiling and future extension

The frozen historical campaign ends on `2026-08-14`.

The historical adapter is not authorized to acquire or qualify new dates beyond that ceiling.

A target that requires any later request date cannot claim complete source history from this campaign alone. A future extension must use separately reviewed prospective acquisition and adapter semantics, remain calendar-date contiguous with `2026-08-14`, and contain no missing, failed, or unreviewed dates.

If historical and prospective row-lineage semantics differ, ATHENA must review the bridge explicitly rather than silently concatenate them.

## Positive-result authority boundary

A future positive execution may establish only scoped frozen historical source-history completeness, authorization to materialize the exact `21,326` ordinary-FT history rows, and approval of the PR #117 historical adapter for this frozen campaign scope.

It must still leave false global source-capability historical coverage confirmation, source-capability or competition-registry mutation, PR #80 constructor input authorization, successor live-input qualification, successor-candidate approval, model training, expected-goals production, probability inference, pricing, market activation, selection, production approval, and BET authority.

## Frozen result vocabulary

The execution may return only one of the pre-registered statuses:

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

Before execution the disposition remains:

`BLOCKED_HISTORICAL_COVERAGE_UNPROVEN`

## Safety

Every PR #118 safety flag is exact `false`.

There is no source capability mutation, no competition registry mutation, no history materialization, no PR #80 input, no model training, no probability inference, no pricing, no market activation, no selection, no production approval, and no BET authorization.

## Canonical protocol identity

The canonical protocol is compact sorted UTF-8 JSON plus one final newline:

- SHA-256 `c4d9d019fa433677d82354570df1fe1c0e634c14b91c1f9ba0c3b47f91258209`;
- size `9,708` bytes.
