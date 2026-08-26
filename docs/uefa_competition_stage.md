# UEFA competition-stage semantics v1 (PR #238)

## Purpose

PR #238 adds a **separate, source-qualified UEFA stage identity** for historical
research and future hosted backtests. It does **not** replace ATHENA's stable
parent competition keys:

- `uefa_ucl` — UEFA Champions League
- `uefa_uel` — UEFA Europa League
- `uefa_uecl` — UEFA Conference League

This follows the expansion blueprint rule that hierarchy priority and
competition stage are different concepts. UEFA qualifying fixtures remain UEFA
fixtures; stage changes modeling context and later backtest stratification, not
the parent competition identity.

## Frozen identities

- parent identity SHA-256: `1ec3df0b5c1a428cf92b1427929acb0c80e04143b90166fdd2e74da8516b8fec`
- stage registry SHA-256: `3125b6673b30a6706d9f03e335ae79ebca65a9a6c4b291504a7e5ae92a36d69b`
- stage contract SHA-256: `54fc67276364d8e447a95afcefcc5efdb36f7f33a8e0b69869d659e84916c943`

The registry is era-aware. Historical `GROUP_PHASE` and the 2024+ `LEAGUE_PHASE`
are distinct. The registry also preserves older Europa League / UEFA Cup
`ROUND_OF_32` semantics where the reviewed era allows them. A stage that is not
allowed for the exact parent competition and season remains `UNKNOWN`.

## Historical evidence boundary

The canonical historical warehouse already stores `stage`, `round_name`, and
field-level provenance. PR #238 replays those exact fields rather than accepting
a caller's stage assertion.

Generic labels are deliberately not trusted by themselves. For example,
OpenFootball's current UEFA qualifier files use labels such as `1. Round`,
`2. Round`, `3. Round`, and `Play-offs`. Those labels become
`QUALIFYING_R1/R2/R3/QUALIFYING_PLAYOFF` only when:

1. the `stage` field is provenance-owned by `openfootball`;
2. the `extra_json` path evidence is also provenance-owned by `openfootball`;
3. the exact basename proves the matching parent qualifier source:
   `clq.txt`, `elq.txt`, or `confq.txt`;
4. the stage is allowed in the parent competition's frozen era registry; and
5. the match has one unambiguous `warehouse_match_sources` lineage row for the
   source.

A qualifier-file path for one parent cannot authorize another parent. If field
provenance is absent, mixed across sources, or ambiguous, the stage stays
`UNKNOWN`.

Explicit labels such as group/league phase, Round of 16, quarter-final,
semi-final, and final still require exact field provenance and source lineage.
No missing stage is reconstructed merely to improve coverage.

## Two-leg and aggregate semantics

A knockout stage label alone does not prove that an exact historical fixture is
leg one, leg two, or a one-off exception. Therefore the default tie format for a
knockout row is `UNKNOWN`.

`TWO_LEG`, `leg_number=2`, and entering aggregate state are issued only when the
warehouse contains one **strictly prior reciprocal fixture** with:

- the same parent competition and season;
- the exact same raw stage/round fields;
- the same stage source;
- both full-time scores provenance-owned by that same source; and
- one unambiguous source-lineage row.

The first leg never uses a future reciprocal fixture to prove its tie format.
That avoids a future-data dependency in historical pre-match research.

For second legs, aggregate scores are oriented to the current home/away teams.
The frozen away-goals rule is applied only through season `2020-21`; from
`2021-22` onward a level aggregate remains `LEVEL`. Extra time and penalties are
marked possible only for a proven second leg or an explicit final. They remain
unknown for an unproven knockout tie format.

The deterministic `stage_source_identity` includes the exact current warehouse
evidence and, when aggregate state is issued, the exact prior-leg source/score
ancestry.

## Goal/Score training integration

The frozen Goal/Score training-view v1 contract is **not modified**. PR #238
instead exposes an exact sidecar projection joined by:

- exact `match_key`; and
- exact `source_warehouse_sha256`.

`project_training_view_uefa_stages()` rejects a training view whose frozen
warehouse SHA does not equal the exact warehouse bytes used for stage
projection. This lets PR #239 stratify historical backtests by stage without
silently changing the already-reviewed Phase 4–9 probability/calibration/value
contracts.

Active SQLite `-wal`, `-shm`, or `-journal` companions fail closed before file
identity is calculated.

## Coverage audit

Run:

```bash
python scripts/audit_uefa_stage_coverage.py --warehouse <athena_history.db>
```

For the Goal/Score training population:

```bash
python scripts/audit_uefa_stage_coverage.py \
  --warehouse <athena_history.db> \
  --training-view <goal_score_training_view.db>
```

The report preserves total, authorized, and `UNKNOWN` counts, stage counts,
competition counts, blockers, contract identities, and the explicit authority
flags. No partial or unknown stage is silently promoted.

**Repository status at PR creation:** the real full-corpus stage backfill audit
has not yet been executed against the hosted canonical warehouse artifact.
Therefore PR #238 makes no stage-coverage percentage claim. The required next
checkpoint after merge is the real backfill/audit report before PR #239 creates
long-lived hosted backtest artifacts.

## Authority boundary

True authority is limited to:

- historical stage projection;
- research stage stratification; and
- exact training-sidecar join.

This PR grants **no live Fixture State stage authority**. The existing
`FixtureStateFieldId.COMPETITION_STAGE` remains a future-source-required slot
until a separately reviewed current pre-match source path proves it.

It also grants no probability inference, calibration, bookmaker pricing, market
routing, final selection, accumulator, production approval, or BET authority.
