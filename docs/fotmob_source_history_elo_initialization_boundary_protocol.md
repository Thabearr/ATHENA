# FotMob source-history Elo initialization boundary protocol

## Purpose

PR #113 pre-registers the next source-history boundary after PR #112. It freezes exactly what ATHENA must mean by a **PR #69-equivalent Elo initialization boundary** before any FotMob history rows may be materialized for the successor model.

This is a protocol-only boundary. It does not execute the qualification, build a source-history adapter, authorize any ordinary-FT history row, prove historical completeness, train a model, produce probabilities, use prices, select a market, or authorize BET.

The frozen state is:

```text
PRE_REGISTERED_NOT_EXECUTED_INITIALIZATION_BOUNDARY_UNQUALIFIED
```

The next boundary is:

```text
EXECUTE_REVIEWED_FOTMOB_SOURCE_HISTORY_ELO_INITIALIZATION_BOUNDARY_QUALIFICATION
```

## Exact ancestry

The protocol binds:

- repository main: `4f99b482d4c3f3f1e3ef19e3134e235f1c4c7da8`;
- PR #112 chronology qualification receipt: `58c7a275580cc74489269a66de2836544e78ca232693d5283f1813ee817d3fc0` / `7,980` bytes;
- PR #112 qualification domain blob: `2028c7e4d847ba293bc88ffc718a406853f96d11`;
- PR #81 source-history completeness protocol: `9d16fcc79e9809a82ef154c75b8e263f782a4e1d4723b57cc216d893c88780ec` / `4,223` bytes;
- PR #69 football-data.co.uk source corpus: `c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0`;
- PR #69 canonical replay: `b44166b9543a8f436e62a644efc5316ad12fcc260a4c2c5908ad112928bedfe3` / `39,952,730` bytes;
- PR #69 replay implementation blob: `b67a7e52954f47cc90c578ad193545c541984964`;
- 66 PR #69 source files and 21,226 source fixtures;
- PR #69 initial model season: `2020-21`;
- Elo initialization semantics: `1500_REPLAY_INITIAL_STATE_ASSUMPTION_NOT_OBSERVED_EVIDENCE`;
- preserved FotMob campaign artifact: `7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f` / `61,886,753` bytes.

PR #112 must still report rearrangement chronology qualified, historical coverage false, and exactly the two remaining blockers `BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN` and `BLOCKED_HISTORICAL_COVERAGE_UNPROVEN`.

## Why `2020-08-01` is not the Elo reset date

The FotMob campaign deliberately starts on `2020-08-01` because it is a conservative acquisition envelope. PR #69, however, is a six-season replay beginning with each league's exact **2020-21** football-data.co.uk source file.

Those are different concepts. A capture envelope can begin before a particular league's PR #69 season begins. Promoting the campaign start directly into an Elo reset date would allow prior-season observations to leak into a replay that was trained from a later boundary.

PR #113 therefore forbids choosing the start from FotMob itself. The execution pass must rebuild the exact PR #69 source corpus and derive one reference floor for each frozen model league from the earliest source-local fixture in that league's exact 2020-21 source file. Any FotMob observation before that independently derived floor remains preserved evidence but is excluded from PR #69-equivalent Elo state.

PR #69 retained source-local clock times without resolving their timezone. For this start-boundary proof, cross-provider clock equality is therefore not invented. The reference-floor comparison is limited to source calendar-date granularity. Historical completeness and full source-local/UTC chronology remain separate reviewed questions.

## Exact eleven-family replay universe

The legacy successor was researched on these exact top-flight league families:

| Model code | FotMob `primaryId` | Country lineage |
|---|---:|---|
| B1 | 40 | BEL |
| D1 | 54 | GER |
| E0 | 47 | ENG |
| F1 | 53 | FRA |
| G1 | 135 | GRE |
| I1 | 55 | ITA |
| N1 | 57 | NED |
| P1 | 61 | POR |
| SC0 | 64 | SCO |
| SP1 | 87 | ESP |
| T1 | 71 | TUR |

These eleven are the **model replay universe for this legacy successor boundary**, not ATHENA's permanent competition universe. Cups, lower divisions, Champions League/Europa/Conference League, international matches and other competitions remain valid ATHENA research targets, but their results cannot silently update this PR #69-equivalent Elo replay because the historical model was not trained with those updates.

No name fallback or wrapper-ID fallback is permitted for these mappings. The previously qualified FotMob `primaryId` family semantics remain authoritative for this boundary.

## Frozen PR #69 initialization semantics

PR #69 begins with an empty rating dictionary. An unseen source-scoped team is created immediately before its first admitted fixture with:

```text
overall = 1500
home    = 1500
away    = 1500
matches = 0
```

The `1500` is a model assumption, not a historical observation.

After a team enters the replay, there is **no season reset**. If the same source team identity appears in a later season, its prior replay state carries forward. A team first appearing later—for example a promoted club absent from earlier top-flight history—starts at `1500 / 0` at that first admitted appearance.

The protocol dynamically revalidates this behavior with a tiny two-season synthetic PR #69 replay. The first `Alpha FC` fixture exposes `1500` as an initial-state assumption. After a 1-0 win, `Alpha FC` reaches pre-match overall Elo `1513` when it reappears in the next season, while new opponent `Gamma FC` starts at `1500`. This is a code-semantics witness only; it is not real football evidence.

PR #69 update mechanics remain frozen as context: home expected-score boost `+50`, base-10 `400` denominator, K=`32` below 20 matches / `24` below 50 / `16` otherwise, and integer conversion after each update. The current fixture's result updates state only after its own pre-match Elo is captured.

## Result-state and chronology interaction

The PR #109–#112 evidence chain remains binding:

- awarded wins are administrative source results and cannot update ordinary regulation-time model history;
- after-extra-time and after-penalties scores are not regulation-time model targets;
- abandoned, cancelled and postponed states are not completed ordinary results;
- chronology-qualified later ordinary-FT terminal states remain preserved at their later reviewed kickoff;
- PR #113 still does **not** authorize those later ordinary-FT terminal rows for model history.

Initialization qualification must not erase any earlier source state or collapse evidence merely to obtain a convenient replay.

## No cross-source Elo equality claim

PR #69 identities are football-data.co.uk source identities. The FotMob chain uses FotMob source fixture/team identities. ATHENA has deliberately not inferred cross-provider team or fixture identity here.

Therefore the future qualification must **not** attempt to prove initialization by making FotMob Elo values numerically equal to the historical PR #69 values team-by-team. Such a comparison would require a separately reviewed cross-source identity and row-equivalence contract that does not exist.

The proof required here is narrower and defensible: the replay must begin at the independently derived PR #69 season boundary, with the same empty-state/1500-first-appearance/no-season-reset mechanics and the same eleven-family competition scope.

## Execution requirements

The execution pass must:

1. use the exact preserved FotMob campaign artifact with no FotMob network reacquisition;
2. revalidate the exact PR #112 receipt first;
3. rebuild all 66 exact PR #69 football-data.co.uk source files and reproduce the frozen source-corpus and canonical-replay hashes before trusting any reference floor;
4. derive all eleven 2020-21 reference floors from PR #69 evidence **before** classifying FotMob pre-boundary observations;
5. preserve and count every target-family FotMob observation before each reference floor but allow none of them to seed/update Elo;
6. require reviewed ordinary-FT or chronology-qualified terminal ordinary-FT evidence at or after every reference floor before a positive result;
7. verify the empty-state `1500 / matches=0` seed, no season reset, no pre-boundary leakage and no out-of-universe update rules;
8. infer no cross-source team or fixture alignment;
9. emit one deterministic canonical receipt containing every reference floor, pre-boundary count, first admitted FotMob fixture IDs and all violation counts;
10. mutate no registry and grant no downstream authority.

If the exact PR #69 source bytes cannot be reproduced, the correct result is blocked. A convenient date inferred from the preserved FotMob corpus is not an acceptable substitute.

## Frozen status vocabulary

The execution may use only:

```text
QUALIFIED_PR69_EQUIVALENT_EMPTY_1500_INITIALIZATION_BOUNDARY
BLOCKED_PR69_EXACT_SOURCE_REBUILD_UNAVAILABLE_OR_CHANGED
BLOCKED_PR69_REFERENCE_FLOOR_DERIVATION_FAILED
BLOCKED_FOTMOB_MODEL_FAMILY_MAPPING_DRIFT
BLOCKED_FOTMOB_PREBOUNDARY_STATE_LEAKAGE
BLOCKED_FOTMOB_REFERENCE_FLOOR_RESULT_EVIDENCE_GAP
BLOCKED_SEASON_RESET_OR_PRESEEDED_RATING
BLOCKED_OUT_OF_UNIVERSE_ELO_UPDATE
BLOCKED_TEAM_IDENTITY_CONTINUITY
BLOCKED_UPSTREAM_CHRONOLOGY_OR_SPECIAL_RESULT_DISPOSITION_DRIFT
```

A positive initialization status would resolve only the initialization boundary. It would not automatically prove historical completeness or authorize history rows.

## Safety

Every downstream safety value remains exact `false`, including:

- `initialization_boundary_proven`;
- ordinary/special history-row authorization;
- source-history adapter approval and completeness;
- PR #80 constructor input;
- successor/live model approval;
- expected-goals production use;
- score matrix/probability/calibration execution;
- pricing/market activation/selection;
- production approval;
- model training;
- BET;
- source-capability or competition-registry mutation.

## Canonical protocol

Canonical sorted compact UTF-8 JSON plus a final newline:

- SHA-256: `61f62252c178fb2e87a1f704848dfadb19213a9dede8fd2925b5d938faf0186c`;
- size: `8,405` bytes.

## Next reviewed boundary

```text
EXECUTE_REVIEWED_FOTMOB_SOURCE_HISTORY_ELO_INITIALIZATION_BOUNDARY_QUALIFICATION
```
