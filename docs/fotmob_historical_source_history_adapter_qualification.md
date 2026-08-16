# FotMob historical source-history adapter qualification

## Scope

PR #117 executes only the historical adapter contract pre-registered by PR #116 against the exact preserved PR #105 FotMob campaign.

The execution state is:

`EXECUTED_HISTORICAL_SOURCE_HISTORY_ADAPTER_QUALIFIED_COMPLETENESS_UNPROVEN`

The frozen repository anchor is:

`cbebb42393be50c77011463906b5d2b70e0ef2c5`

This boundary does **not** prove source-history completeness, materialize source-history rows, authorize PR #80 constructor input, mutate source capabilities, or authorize model, probability, pricing, selection, production, or BET use.

## Exact PR #116 contract

The execution binds:

- protocol ID `REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_ADAPTER_PROTOCOL_V1`;
- protocol blob `53682e3810bf3c06b1afc90b847361b6dcb3e04f`;
- protocol SHA-256 `f987bc68eaf9f4c7b57a66788f3dcac5d704be6dad36ecae92bf5dd7e315ea9a`;
- protocol size `9,898` bytes.

It also revalidates the exact PR #110 special-result, PR #112 rearrangement chronology, PR #114 Elo-initialization, and PR #115 fail-closed adapter/completeness receipts before scanning the campaign.

## Evidence envelope

Only the preserved campaign is used:

- artifact ID `9249856559`;
- artifact SHA-256 `7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f`;
- artifact size `61,886,753` bytes;
- embedded research-cache SHA-256 `cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6`;
- embedded cache size `61,881,610` bytes;
- request interval `2020-08-01` through `2026-08-14`;
- `timezone=UTC`;
- `ccode3=NGA`.

No network reacquisition occurs.

## Historical pair-lineage result

All `2,205` request dates contain exactly two canonical acquisition manifests, for `4,410` manifests total.

The pair evidence is exactly:

- `2,205` distinct manifest pairs;
- `2,204` pairs with byte-identical raw responses;
- one distinct-raw date, `20250712`;
- zero target-family fixtures on that distinct-raw date;
- minimum observation separation `3,761,138,022` microseconds;
- maximum observation separation `7,454,335,835` microseconds.

This qualifies the **historical** lineage rule from PR #116: two distinct, independently provenance-bound acquisitions may corroborate one static response body even when the bytes are identical.

It does not reinterpret identical bytes as two content lineages. No response or manifest was salted, rewritten, mutated, or synthesized to manufacture a different hash. The prospective ordinary-FT adapter remains unchanged.

## Historical structural result

Every one of the `21,336` ordinary-FT candidate occurrences has the exact historical `status.halfs` keyset:

- `firstHalfStarted`;
- `secondHalfStarted`.

Both fields are exact strings parseable with `%d.%m.%Y %H:%M:%S`. There are zero keyset, type, or parse mismatches.

Those values remain opaque metadata. They do not establish kickoff, halftime, duration, resumption, replay, restart, continuation, or bookmaker settlement semantics.

`status.utcTime` remains the canonical kickoff field. Across the frozen corpus, `match.time` corroborates that UTC kickoff through `Europe/Oslo` at minute precision with zero mismatches. This remains a corpus-specific observation, not a global FotMob timezone rule.

## Result and state accounting

The eleven already-qualified historical/model families contain exactly `21,640` fixture/date pairs.

They split exactly into:

- `21,336` ordinary-FT occurrences;
- `304` reviewed special-state occurrences;
- zero unreviewed target-state occurrences.

The `304` reviewed special occurrences remain excluded from ordinary regulation-time history and reproduce the qualified source-state counts:

| State | Occurrences |
|---|---:|
| ABANDONED | 20 |
| AFTER_EXTRA_TIME | 3 |
| AFTER_PENALTIES | 3 |
| AWARDED_WIN | 26 |
| CANCELLED | 11 |
| POSTPONED | 241 |

PR #110 special-result semantics and PR #112 rearrangement chronology remain authoritative.

## Ordinary-FT projection

The qualification creates a deterministic **derived evidence projection only**. It does not create source-history rows.

There is one projection record for each ordinary-FT source fixture/date occurrence, with source-scoped fixture/competition/team identity, canonical kickoff, score, exact FT reason tuple, both acquisition manifest lineages and observation times, raw hashes, and PR #114 floor disposition.

The exact projection identity is:

- records `21,336`;
- unique source fixture IDs `21,336`;
- duplicate ordinary source fixture IDs `0`;
- SHA-256 `eddb7f5b58eb3cb92087dc7bf57a45a270aebabce38641cd3b4ffc2277d67ed3`;
- size `22,080,831` bytes.

All `21,336` projection records are supported by byte-identical A/B raw content retrieved under two distinct acquisition manifests. That is expected because the one distinct-raw campaign date contains no target-family fixture.

## Elo initialization split

PR #114 remains binding. Of the `21,336` ordinary-FT occurrences:

- `10` are before their model-family Elo replay floor and remain evidence only;
- `21,326` are on or after the replay floor.

The on-or-after-floor counts remain:

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

These `21,326` are still **candidates**, not authorized history rows.

## Qualification conclusion

The historical adapter itself is now qualified for the exact frozen campaign:

`QUALIFIED_FROZEN_CAMPAIGN_HISTORICAL_ORDINARY_FT_ADAPTER`

This resolves the PR #115 adapter-specific:

`BLOCKED_RESULT_EVIDENCE_GAP`

only for this historical adapter boundary.

The remaining blocker is still:

`BLOCKED_HISTORICAL_COVERAGE_UNPROVEN`

`source_history_adapter_approved`, `source_history_completeness_proven`, and `historical_coverage_proven` all remain `false`. Zero history rows are materialized or authorized.

## Why completeness is still separate

PR #99 froze a reusable-prospective-adapter requirement before the historical incompatibility was known. PR #116 and PR #117 deliberately do not mutate that frozen contract after seeing the campaign.

A later boundary must therefore explicitly pre-register how the newly qualified historical adapter participates in completeness and materialization while preserving the prospective adapter for prospective use. That prevents ATHENA from silently treating adapter qualification as historical coverage proof.

## Next boundary

`PRE_REGISTER_REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_COMPLETENESS_AND_MATERIALIZATION_PROTOCOL`

That boundary must reconcile the frozen PR #81/PR #99 completeness requirements with the qualified historical adapter, define exact materialization eligibility, preserve the ten pre-floor evidence-only occurrences, and keep PR #80/model/pricing/selection/BET authority fail-closed until completeness is separately executed and proven.

## Canonical receipt

The committed qualification receipt is canonical compact sorted UTF-8 JSON plus a final newline:

- SHA-256 `a8f06a9d789b20b4ef49766bd771fb5c4d13c4be657ac6a5fc8f284701054020`;
- size `5,081` bytes.
