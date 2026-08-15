# FotMob source-history rearrangement chronology qualification

## Purpose

This boundary executes the PR #111 source-scoped chronology contract against the exact preserved PR #105 FotMob campaign artifact. No network reacquisition occurs.

The result is narrow: the 250 preserved fixture IDs whose FotMob kickoff changes across request dates now have a reviewed source-lineage chronology disposition. This resolves `BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT` for this frozen corpus only.

It does **not** materialize source history, approve any ordinary-FT row for model replay, prove the Elo initialization boundary, prove historical completeness, or authorize model, probability, pricing, selection, production, or BET use.

## Exact ancestry

- base/main: `9c156e6022b0034dfe16e0d9446b4e1890f53753`
- PR #111 protocol SHA-256: `3f7caa751d0fe8114e50d8fee4bb2afa58023b4bee63429e4c6c51b9d2f92ce3`
- PR #111 protocol size: `7,642` bytes
- PR #111 protocol blob: `58eb56a6c55048cb163b7611da7ef85468c91f9a`
- PR #110 qualification receipt SHA-256: `7d6bb5c86391c45abdbb588a27325c99ebf88c4753f75c108387e2c4d3dbb99d`
- preserved campaign artifact ID: `9249856559`
- artifact SHA-256: `7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f`
- artifact size: `61,886,753` bytes
- embedded research cache SHA-256: `cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6`

The reproduction script refuses artifact, cache, upstream receipt, protocol, or deterministic projection drift.

## Reviewed chronology corpus

The qualification accounts for exactly:

- **250** rearranged source fixture IDs
- **502** fixture/request-date occurrences
- **1,004** raw same-date A/B capture observations
- **252** cross-date kickoff-revision edges

Each fixture/date occurrence still has exactly two A/B captures. Relevant-field pair conflicts are zero.

The deterministic rearranged-history projection is:

- SHA-256: `9fa899ebeb0e42154832c1ca9dc040685a359add2a4cf7c1029fd13b7d56dbe8`
- size: `349,277` bytes

The deterministic cross-date edge projection is:

- SHA-256: `2c85f3ccfa4fd34af928c339ec6ebc79048ed3a5252f88bb195b77fb61bb13b9`
- size: `90,086` bytes

## Chronology integrity checks

The execution proves, within the frozen reviewed corpus:

- zero same-date capture-cardinality mismatches
- zero same-date relevant-field conflicts
- zero cross-date drift in `primaryId`, wrapper `league.id`, home team ID, or away team ID
- zero request-date / kickoff-UTC-calendar-date mismatches
- zero non-forward kickoff revisions
- zero unregistered transition patterns

Changed kickoff is therefore treated only as mutable **FotMob source schedule metadata** for these exact source fixture lineages. This is not a cross-source identity rule and does not globally redefine ATHENA fixture identity.

## Exact transition evidence

| Source chronology pattern | Fixtures | Edges | Terminal source state |
|---|---:|---:|---|
| `POSTPONED -> ORDINARY_FT` | 234 | 234 | Ordinary FT |
| `ABANDONED -> ORDINARY_FT` | 7 | 7 | Ordinary FT |
| `CANCELLED -> AWARDED_WIN` | 5 | 5 | Awarded win |
| `POSTPONED -> POSTPONED -> ORDINARY_FT` | 2 | 4 | Ordinary FT |
| `POSTPONED -> AWARDED_WIN` | 1 | 1 | Awarded win |
| `AWARDED_WIN -> AWARDED_WIN` | 1 | 1 | Awarded win |

Occurrence-state counts across all 502 reviewed fixture/date rows are exactly:

- postponed: 239
- abandoned: 7
- cancelled: 5
- ordinary FT: 243
- awarded win: 8

## What “qualified chronology” means

For the 243 lineages ending in ordinary FT, ATHENA now has reviewed evidence that FotMob preserves one source fixture lineage across one or more forward kickoff revisions and later reports an ordinary-FT state.

That does **not** authorize those 243 terminal rows for model history yet. They may only reach a separate history-materialization review after the frozen Elo initialization boundary is established.

For the seven `ABANDONED -> ORDINARY_FT` lineages, no claim is made about whether real-world play resumed, replayed, restarted, continued, or was replaced. The source supports only the observed source-state sequence.

The seven lineages ending in `AWARDED_WIN` remain excluded from ordinary regulation-time model history because awarded scores are administrative source results, not observed football performance.

Fixture `3932603` remains two preserved awarded source occurrences on request dates `20230220` and `20230305`. No last-observation coercion is performed.

## Blocker movement

Resolved:

`BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT`

Still blocked:

- `BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN`
- `BLOCKED_HISTORICAL_COVERAGE_UNPROVEN`

Historical coverage therefore remains false.

## Safety

This PR performs no source-history mutation and no source-capability or competition-registry mutation.

It does not authorize:

- ordinary-FT history rows
- special-result history rows
- source-history adapter approval
- PR #80 constructor input
- model training
- expected-goals production use
- probability inference or adjustment
- pricing
- market activation
- selection
- production approval
- BET

## Canonical receipt

- SHA-256: `58c7a275580cc74489269a66de2836544e78ca232693d5283f1813ee817d3fc0`
- size: `7,980` bytes

## Reproduction

Run against the exact preserved campaign artifact:

```bash
python scripts/qualify_fotmob_source_history_rearrangement_chronology.py \
  /path/to/fotmob-ordinary-ft-source-history-campaign-31887523012.zip
```

The script reproduces the checked-in receipt byte-for-byte or fails closed.

## Next reviewed boundary

`PRE_REGISTER_REVIEWED_FOTMOB_SOURCE_HISTORY_ELO_INITIALIZATION_BOUNDARY_PROTOCOL`
