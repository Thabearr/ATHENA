# FotMob source-history rearrangement chronology semantics protocol

## Purpose

This boundary pre-registers the exact chronology rules that the next execution pass must use for the 250 preserved FotMob fixture IDs whose source-reported kickoff changes across request dates.

It does **not** resolve chronology yet. It does not materialize model history, approve a source-history adapter, prove historical completeness, or authorize model, probability, pricing, selection, production, or BET use.

## Exact ancestry

The protocol is anchored to `main` commit:

`8bc0a8afc20b71958dee9d14ab1d783eff646447`

It requires the exact PR #110 special-result semantics qualification receipt:

- SHA-256: `7d6bb5c86391c45abdbb588a27325c99ebf88c4753f75c108387e2c4d3dbb99d`
- size: `8,558` bytes
- qualification domain blob: `ed3f2053ab9732e1e34e2e54f6f1e3531d01a4ca`
- preserved special-fixture history projection SHA-256: `459c94fd53430663562d9ce614ca2b52b518b6a8f06f6661b27b555c567c281d`
- projection size: `380,539` bytes

PR #110 must still report special-result semantics qualified, chronology unresolved, and historical coverage false before this protocol can build.

## Frozen chronology evidence

The next execution must account for all:

- 250 rearranged source fixture IDs
- 502 fixture/request-date occurrences
- 1,004 raw A/B capture observations
- 252 cross-date transition edges
- 243 fixtures whose later terminal source state is ordinary FT
- 7 fixtures whose later terminal source state is awarded win

Occurrence-state counts are frozen as:

| State | Fixture/date occurrences |
|---|---:|
| Postponed | 239 |
| Abandoned | 7 |
| Cancelled | 5 |
| Ordinary FT | 243 |
| Awarded win | 8 |

Every same-date occurrence must still have exactly two A/B captures with zero relevant-field conflict.

## Exact transition patterns

Only these six patterns are admitted by the protocol:

| Pattern | Fixtures | Reviewed chronology meaning |
|---|---:|---|
| `POSTPONED -> ORDINARY_FT` | 234 | source schedule revision followed by later ordinary FT |
| `ABANDONED -> ORDINARY_FT` | 7 | source later reports ordinary FT; no claim about resume, replay, restart, or continuation |
| `CANCELLED -> AWARDED_WIN` | 5 | later administrative awarded result; both states preserved |
| `POSTPONED -> POSTPONED -> ORDINARY_FT` | 2 | multiple schedule revisions followed by later ordinary FT |
| `POSTPONED -> AWARDED_WIN` | 1 | later administrative awarded result |
| `AWARDED_WIN -> AWARDED_WIN` | 1 | repeated administrative awarded state across changed kickoff metadata |

Any other state sequence, boolean/reason variant, fixture-membership drift, or count mismatch must fail closed.

## Source-scoped fixture identity

For this frozen corpus only, the protocol allows a changed kickoff to be treated as mutable source schedule metadata rather than a new source fixture identity **only when all reviewed static identity fields remain exact**:

- same FotMob fixture ID
- same qualified `primaryId`
- same wrapper `league.id`
- same home team ID
- same away team ID
- same-date A/B evidence agrees exactly

This rule is FotMob-source-scoped. It does not create a cross-source identity rule and does not globally redefine ATHENA fixture identity.

The execution must also require each occurrence's request date to equal the UTC calendar date of its source-reported kickoff and every successive kickoff revision to move strictly forward.

## No destructive collapse

All raw captures and every fixture/date occurrence remain evidence.

The next execution may produce a separate derived chronology disposition, but it may not delete, hide, overwrite, or rewrite earlier postponed, abandoned, cancelled, or awarded source states.

Pairing the two same-date captures is only a reproducible evidence view. Both raw capture lineages remain preserved.

## Ordinary-FT terminal states

The 243 later ordinary-FT states are **not automatically authorized as model-history rows** by this protocol.

A successful chronology qualification would establish only that the source lineage and ordering are reviewed. Those terminal ordinary-FT rows may then reach a separate history-materialization review.

For the seven `ABANDONED -> ORDINARY_FT` lineages, ATHENA must not infer whether the real-world match was resumed, replayed, restarted, continued, or replaced. The source evidence supports only that FotMob later reports the same source fixture lineage at a later kickoff with an ordinary-FT terminal state.

Earlier abandoned score scalars remain partial source evidence and cannot override the later reviewed disposition.

## Awarded terminal states

The seven lineages ending in `AWARDED_WIN` remain excluded from ordinary regulation-time model history because PR #110 qualified awarded wins as administrative source results, not observed football performance.

Fixture `3932603` must remain two separate awarded source occurrences on request dates `20230220` and `20230305`. The next pass may classify its chronology, but must not silently keep only the later occurrence.

## Qualification requirements

The execution boundary must use only the exact preserved PR #105 campaign artifact, perform no network reacquisition, revalidate PR #110 first, account for the complete 250-fixture membership, reproduce the exact six transition counts, prove zero same-date relevant-field drift, prove zero cross-date static identity drift, prove zero request-date/kickoff-date mismatch, and require all 252 kickoff revision edges to move strictly forward.

No source capability, competition, model, pricing, selection, or betting registry may be mutated.

## Safety

At protocol time:

- chronology execution is false
- rearrangement chronology qualification is false
- chronology resolution is false
- source-history mutation is false
- ordinary-FT history-row authorization is false
- special-result history-row authorization is false
- source-history adapter approval is false
- historical completeness is false
- initialization equivalence is still unproven
- all downstream model/probability/pricing/selection/production/BET authority remains false

## Canonical protocol identity

- SHA-256: `3f7caa751d0fe8114e50d8fee4bb2afa58023b4bee63429e4c6c51b9d2f92ce3`
- size: `7,642` bytes

## Next reviewed boundary

`EXECUTE_REVIEWED_FOTMOB_SOURCE_HISTORY_REARRANGEMENT_CHRONOLOGY_QUALIFICATION`
