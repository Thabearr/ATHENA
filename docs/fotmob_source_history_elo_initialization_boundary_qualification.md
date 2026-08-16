# FotMob source-history Elo initialization boundary qualification

## Result

PR #114 executes the PR #113 initialization protocol and qualifies the narrow question it pre-registered:

```text
QUALIFIED_PR69_EQUIVALENT_EMPTY_1500_INITIALIZATION_BOUNDARY
```

The resolved blocker is:

```text
BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN
```

The remaining blocker is still:

```text
BLOCKED_HISTORICAL_COVERAGE_UNPROVEN
```

This result does **not** authorize a FotMob history row, source-history adapter, model training, probability, calibration, pricing, market activation, selection, production use, or BET.

## Exact execution evidence

The execution was performed in a controlled GitHub Actions lane against two independent evidence families:

- the exact preserved FotMob campaign artifact `9249856559`, SHA-256 `7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f`, `61,886,753` bytes;
- a fresh acquisition of all 66 official football-data.co.uk CSVs used by PR #69, rebuilt through the unchanged PR #69 replay implementation.

The exact PR #69 rebuild reproduced all frozen identities:

- 66 source files;
- `10,006,877` raw bytes;
- 21,226 fixtures;
- source-corpus SHA-256 `c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0`;
- canonical replay SHA-256 `b44166b9543a8f436e62a644efc5316ad12fcc260a4c2c5908ad112928bedfe3`;
- canonical replay size `39,952,730` bytes.

That independent reproduction matters: the initialization date was not selected from FotMob after seeing its data.

## Independently derived PR #69 replay floors

The earliest source-local calendar date in each exact 2020-21 PR #69 source file became that league family's reference floor:

| Model family | FotMob `primaryId` | PR #69 reference floor |
|---|---:|---|
| B1 | 40 | 2020-08-08 |
| D1 | 54 | 2020-09-18 |
| E0 | 47 | 2020-09-12 |
| F1 | 53 | 2020-08-21 |
| G1 | 135 | 2020-09-11 |
| I1 | 55 | 2020-09-19 |
| N1 | 57 | 2020-09-12 |
| P1 | 61 | 2020-09-18 |
| SC0 | 64 | 2020-08-01 |
| SP1 | 87 | 2020-09-12 |
| T1 | 71 | 2020-09-11 |

The comparison is intentionally only at source calendar-date granularity. PR #69 source times retain unresolved source-local timezone semantics, so PR #114 does not invent cross-provider clock equality.

## Why the campaign start is not the Elo reset

The FotMob campaign begins on `2020-08-01`, but only Scotland's PR #69 replay floor is `2020-08-01`. The other ten families begin later according to their independent PR #69 source evidence.

The campaign contains ten Italy fixture/date observations before Italy's `2020-09-19` PR #69 floor, representing twenty exact A/B capture rows and ten unique fixture IDs. PR #114 preserves those observations while proving that **zero** of them can seed or update the PR #69-equivalent Elo state.

This is the concrete execution proof that the capture envelope and the model replay boundary are separate concepts.

## Target-family FotMob accounting

Across the eleven model families, the exact campaign contains:

- 4,410 response files across 2,205 request dates;
- 43,280 target-family raw capture rows;
- 21,640 same-date fixture pairs after exact A/B agreement;
- 10 pre-boundary fixture/date occurrences;
- 21,326 reviewed ordinary-FT candidates at or after their family floor;
- 304 reviewed special-state occurrences at or after their family floor.

The accounting closes exactly:

```text
10 + 21,326 + 304 = 21,640
```

There is therefore no unreviewed residual state in this exact target-family projection for the initialization assessment.

The deterministic target-family projection is:

- SHA-256 `e98715f599fd9495f7a606e0a05a07bdc56781d35ba497522610efdab775c0b9`;
- `6,853,903` bytes.

## Initialization-state witness

For this boundary only, PR #114 walks each league's reviewed ordinary-FT candidate stream from its independent floor using source-scoped FotMob team IDs. A team's first admitted appearance creates an empty-state seed of `1500 / matches=0`; later appearances reuse the same source-team state without a season reset.

The execution observed:

- 282 first-seen source-team seeds;
- 42,370 later source-team state reuses;
- zero season resets;
- zero pre-boundary state updates;
- zero special/nonordinary state updates;
- zero out-of-universe state updates;
- zero team-identity violations.

This is a **state-lifetime and boundary witness**, not a new FotMob Elo artifact. PR #113 already froze and dynamically revalidated the PR #69 update mechanics. PR #114 does not claim team-by-team numerical equality between football-data.co.uk and FotMob, because no cross-source identity contract exists.

## Fail-closed checks

The exact execution also reports zero:

- malformed fixture identities;
- same-date A/B cardinality mismatches;
- same-date relevant-field conflicts;
- static source-fixture identity drift;
- pre-boundary leakage;
- special/nonordinary updates;
- out-of-universe updates;
- season resets;
- team identity violations.

Every one of the eleven independently derived floors has reviewed ordinary-FT evidence at or after the floor.

## Canonical durable receipt

The checked-in receipt is canonical sorted compact UTF-8 JSON with a final newline:

- path: `artifacts/research-manifests/fotmob-source-history-elo-initialization-boundary-qualification-v1.json`;
- SHA-256: `fbbec0b858c3e9630d9f4c7dec630012f57811de52d300db3a11b781a719e110`;
- size: `24,428` bytes.

It includes all 66 freshly observed football-data.co.uk source-file SHA-256 identities, the eleven source floor witnesses, the full family-level boundary assessment, and the exact preserved FotMob evidence identities.

## Safety and next boundary

`initialization_boundary_qualified=true` is a narrow research evidence fact. It is **not** a downstream capability flag. Every safety/authorization field remains exact `false`, including source-history adapter approval, historical completeness, ordinary result-row authorization, model training, probability inference, calibration, pricing, market activation, selection, production approval, and BET.

The next previously pre-registered boundary is:

```text
EXECUTE_REVIEWED_SOURCE_HISTORY_ADAPTER_AND_COMPLETENESS_ASSESSMENT
```

That later boundary must decide historical completeness and row admissibility independently. PR #114 does not prejudge its result.
