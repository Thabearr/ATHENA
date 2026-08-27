# UEFA competition-stage semantics v1 (PR #238)

## Purpose

PR #238 adds a **separate, source-qualified UEFA stage identity** for historical research and future hosted backtests. It does **not** replace ATHENA's stable parent competition keys:

- `uefa_ucl` — UEFA Champions League
- `uefa_uel` — UEFA Europa League
- `uefa_uecl` — UEFA Conference League

Hierarchy priority and competition stage remain different concepts. A UEFA qualifying fixture stays inside its parent UEFA competition; stage changes research context and later backtest stratification, not the parent hierarchy identity.

## Frozen identities

- parent identity SHA-256: `1ec3df0b5c1a428cf92b1427929acb0c80e04143b90166fdd2e74da8516b8fec`
- stage registry v1 SHA-256: `3125b6673b30a6706d9f03e335ae79ebca65a9a6c4b291504a7e5ae92a36d69b`
- stage contract v1 SHA-256: `069a838cf9561243e5f02c56f814c6c458b7a883ec7c4d84d4dcbd95af0154ce`
- Goal/Score training-sidecar contract v1 SHA-256: `2c1bfdd6d21892fba7cb1a1df64e02e188cf76c5fb2368716093df4343121014`
- canonical historical warehouse schema SQL SHA-256: `d5a3b545a639c43a2b35fb18529a429ba2572d2861ac52c638cce42a8141306f`
- frozen Goal/Score training-view v1 contract SHA-256: `bac5380814de579dffe96d4e5daa39b0cf1e2d6144b59b5d89f2a81f7b27017b`

The stage registry is era-aware. Historical `GROUP_PHASE` and 2024+ `LEAGUE_PHASE` are distinct. Unsupported competition/season/stage combinations remain `UNKNOWN`; coverage pressure never authorizes reconstruction.

## Reviewed historical evidence boundary

The canonical historical warehouse already stores `stage`, `round_name`, field-level provenance, and source lineage. PR #238 replays those exact objects through the existing canonical `ReadOnlyHistoricalWarehouse` validation boundary instead of accepting caller stage assertions.

The v1 reviewed historical stage-source allowlist contains only:

- `openfootball`

That allowlist is frozen in the stage contract. A future source merely writing a `stage` field into the warehouse does not gain stage authority automatically.

For an OpenFootball stage to become authoritative, the stage/round field must be provenance-owned by `openfootball`, the match must have exactly one matching source-lineage row, the source match ID must be present, and the source URL must match the reviewed OpenFootball repository archive route. Missing, duplicate, mixed, or unreviewed ancestry fails closed.

### Qualifying files and source-path consistency

The reviewed OpenFootball qualifier files use source-native labels such as `Round 1`, `Round 2`, `Round 3`, and `Playoffs`. Historical spelling variants such as `1. Round` remain accepted only under the same source/path proof. These labels are ambiguous by themselves. They become `QUALIFYING_R1`, `QUALIFYING_R2`, `QUALIFYING_R3`, or `QUALIFYING_PLAYOFF` only when the same OpenFootball provenance also owns the `extra_json` source path and the basename proves the matching parent qualifier file:

- `clq.txt` → `uefa_ucl`
- `elq.txt` → `uefa_uel`
- `confq.txt` → `uefa_uecl`

Recognized main files are likewise parent-bound:

- `cl.txt` → `uefa_ucl`
- `el.txt` → `uefa_uel`
- `conf.txt` → `uefa_uecl`

When one of those reviewed basenames is present, both parent and phase must agree with the derived canonical stage. Therefore an explicit `Quarterfinals` label cannot be authorized from `clq.txt`, and a Europa League row cannot borrow a Champions League file path. Unknown OpenFootball basenames are not reinterpreted solely from their name; the stage must still pass all other source and era gates.

### Source-native main-stage labels

The main-stage policy is frozen separately from qualifier interpretation. Reviewed source-native forms include:

- UCL 2024+: `League, Matchday N`, `Playoffs, Matchday N`, `Finals, Round of 16`, `Finals, Quarterfinals`, `Finals, Semifinals`, and `Finals, Final`;
- UEL / UECL 2024+: `League phase`, `Playoffs`, `Round of 16`, `Quarterfinals`, `Semifinals`, and `Final`;
- UEL 2004-05 through 2020-21 `Round of 32`, including the source-native `Sechzehntelfinale` spelling used by OpenFootball;
- UEL / UECL `Playoffs` from 2021-22 onward, matching the introduction of the knockout playoff round in those competitions; and
- reviewed historical OpenFootball group headings beginning with either `Group` or the source-native `Gruppe` spelling.

The `Playoffs` label is path- and era-sensitive because the same raw word can mean a qualifying playoff in a qualifier file or a knockout playoff in a main file. UCL main-file playoffs are recognized only from the 2024-25 era onward; UEL and UECL main-file playoffs are recognized from 2021-22 onward. A stage still has to pass the parent-file and era registry gates after label interpretation.

## Era-aware stage semantics

The v1 stage vocabulary is:

- `QUALIFYING_R1`
- `QUALIFYING_R2`
- `QUALIFYING_R3`
- `QUALIFYING_PLAYOFF`
- `GROUP_PHASE`
- `LEAGUE_PHASE`
- `ROUND_OF_32`
- `KNOCKOUT_PLAYOFF`
- `ROUND_OF_16`
- `QUARTER_FINAL`
- `SEMI_FINAL`
- `FINAL`
- `UNKNOWN`

The registry explicitly prevents modern terminology from being projected backward into eras where the format did not exist. `UNKNOWN` is a valid research result, not an error to be patched with a guess.

## Two-leg and aggregate semantics

A knockout label alone does not prove whether an exact historical match is leg one, leg two, or a one-off exception. The default tie format for an otherwise authorized knockout stage is therefore `UNKNOWN`.

`TWO_LEG`, `leg_number=2`, entering aggregate state, and qualification state are issued only if the warehouse contains exactly one strictly prior reciprocal fixture that independently replays through the same stage contract and proves:

- same parent competition and season;
- reversed teams;
- the same canonical stage after replay, not merely matching raw text;
- the same reviewed stage source;
- finite non-negative regulation full-time scores; and
- both score fields provenance-owned by that same reviewed source.

The first leg never inspects a future reciprocal match to label itself as leg one. That intentionally sacrifices some descriptive completeness to preserve historical pre-match chronology.

For a proven second leg, aggregate scores are oriented to the current home/away teams. The away-goals rule is applied only through season `2020-21`; from `2021-22` onward a level aggregate remains `LEVEL`.

Historical UEFA Cup final format is also era-aware: finals through `1996-97` are not assumed to be single-match, while `1997-98` and later Europa/UEFA Cup finals are single-match under this reviewed rule. UCL and UECL finals in their supported eras are single-match.

Extra time and penalties are marked possible only where the tie/final format has actually been proven by the contract. They remain unknown for an unproven knockout format.

## Projection records are not authentication primitives

`UEFAStageProjection` is a deterministic research record. Its public constructor is disabled, but the Python type itself is not claimed to be cryptographically unforgeable. Future authoritative research consumers must obtain stage data by replaying the public warehouse/training-sidecar boundary against the exact frozen source artifacts; they must not trust a caller-supplied serialized projection merely because its fields look valid.

Coverage reporting validates exact projection types, exact stage-contract identity, and a single warehouse identity, but this remains research-report integrity rather than production betting authority.

## Goal/Score training-sidecar integration

The frozen Goal/Score training-view v1 contract is **not modified**. PR #238 exposes a separate sidecar join so #239 and later hosted backtests can stratify by stage without silently rewriting the already-reviewed Phase 4–9 probability/calibration/value contracts.

The sidecar requires all of the following:

- the exact live Goal/Score training-view contract validates to the independently pinned v1 SHA;
- training metadata pins the expected dataset/schema, feature registry, model registry, evaluation contract, training-view contract, and source warehouse SHA;
- exact `match_key` and `competition_key` join columns exist;
- the stage warehouse bytes validate through the canonical warehouse contract;
- the warehouse SHA used by the training view equals the warehouse SHA used by every returned stage projection; and
- the training-view file remains byte-for-byte and stat-stable across the join.

The audit report records the exact training-view SHA when this sidecar is used.

## SQLite and file-integrity rule

The stage boundary follows ATHENA's canonical historical-warehouse SQLite safety rule: a **non-empty** `-wal` or `-journal` companion is active state and fails closed. Merely finding a zero-length WAL or a standalone SHM pathname is not sufficient evidence of uncheckpointed source bytes.

This is paired with explicit size/mtime/SHA checks before and after training-sidecar reads. The warehouse itself is protected by the existing `ReadOnlyHistoricalWarehouse.assert_unchanged()` SHA/stat checks, and the sidecar additionally rejects a warehouse identity change between training metadata validation and stage replay.

## Coverage audit

Warehouse-only audit:

```bash
python scripts/audit_uefa_stage_coverage.py --warehouse <athena_history.db>
```

Goal/Score training-population audit:

```bash
python scripts/audit_uefa_stage_coverage.py \
  --warehouse <athena_history.db> \
  --training-view <goal_score_training_view.db>
```

The report preserves total, authorized, and `UNKNOWN` counts; per-stage and per-competition counts; blocker counts; exact contract/artifact identities; and authority flags. No unknown stage is silently promoted.

**PR #238 does not claim a real full-corpus coverage percentage.** The mandatory next checkpoint after merge is to run this audit against the hosted canonical warehouse/training artifacts and inspect the unresolved stage distribution before PR #239 freezes long-lived backtest artifacts.

## Live Fixture State remains unchanged

This historical research contract does **not** qualify a current pre-match competition-stage source. `FixtureStateFieldId.COMPETITION_STAGE` remains `FUTURE_SOURCE_REQUIRED` with `currently_reviewed_path_exists=False`. A separate current-source review is required before live Fixture State can consume stage as authoritative evidence.

## Authority boundary

True authority in PR #238 is limited to historical stage projection, historical research stratification, and exact training-sidecar joining.

It grants no live Fixture State stage authority, probability inference, calibration, bookmaker pricing, market routing, final selection, accumulator authority, production approval, or BET authority.
