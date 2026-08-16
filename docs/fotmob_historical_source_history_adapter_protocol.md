# Reviewed FotMob historical source-history adapter protocol

## Scope

This boundary pre-registers a **historical-only** ordinary-FT source-history adapter for the exact preserved FotMob campaign after PR #115 established that the existing prospective adapter cannot be reused without changing its reviewed contract.

Protocol state:

`PRE_REGISTERED_NOT_EXECUTED_HISTORICAL_SOURCE_HISTORY_ADAPTER_UNQUALIFIED`

The protocol is anchored to merged `main`:

`3b49eccc9476754972c18b9abcfe013f783a6205`

It binds the exact PR #115 fail-closed receipt:

- SHA-256 `247dd06389f17cc2d27af568b92f19de1da49b3d3fce1c73ad901d904a2366b2`
- size `6,634` bytes
- primary status `BLOCKED_RESULT_EVIDENCE_GAP`

No adapter qualification is executed in this PR. No source-history row is materialized and no source capability, model, probability, pricing, selection, production, or BET authority is created.

## Why a separate historical adapter is required

PR #115 proved two incompatibilities between the frozen historical campaign and the prospective ordinary-FT adapter.

First, all 2,205 capture dates have two distinct manifest lineages, but 2,204 of those date pairs return byte-identical response bodies. The prospective adapter intentionally requires both manifest and raw-response hashes to differ, so it blocks historical static evidence.

Second, the sole distinct-raw date reaches the frozen structural chain and fails because historical `status.halfs` contains a field outside the reviewed prospective schema.

PR #116 does **not** loosen the prospective adapter. It freezes separate historical semantics that apply only to the exact hashed campaign artifact.

## Exact evidence envelope

The future qualification must use only:

- campaign artifact ID `9249856559`
- outer SHA-256 `7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f`
- outer size `61,886,753` bytes
- embedded research-cache SHA-256 `cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6`
- embedded cache size `61,881,610` bytes
- request envelope `2020-08-01` through `2026-08-14`, `timezone=UTC`, `ccode3=NGA`

The expected acquisition/accounting remains:

- 2,205 request dates
- 4,410 capture manifests
- exactly two manifests per date
- 2,205 distinct manifest pairs
- 2,204 byte-identical raw-response pairs
- one distinct-raw date: `20250712`
- zero target-family fixtures on that distinct-raw date
- 21,640 target-family fixture/date pairs
- zero same-date target relevant-field conflicts

## Historical pair-lineage semantics

For this historical adapter, two independently timestamped acquisition manifests may corroborate one static completed-date response even when their raw SHA-256 values are identical.

That rule is deliberately narrow:

- both manifests must be canonical, distinct lineages;
- both must share one exact request date, timezone and `ccode3`;
- each response body must independently match its own manifest SHA-256 and size;
- `network_acquisition_performed` must remain exact `true`;
- the second observation must be strictly later and at least 300 seconds after the first;
- every target-relevant field must be exactly stable across the pair.

An identical raw SHA-256 means only **the same bytes were retrieved twice**. It must never be described as two distinct content lineages.

ATHENA must never salt, rewrite, mutate or synthesize a response body or manifest merely to manufacture distinct hashes.

The prospective adapter's existing distinct-raw requirement remains unchanged and continues to govern prospective use.

## Historical structural boundary

The historical adapter is campaign-scoped, not a new global FotMob schema.

For ordinary-FT target rows the future qualification must find `status.halfs` with exactly:

`firstHalfStarted`

`secondHalfStarted`

Both values must be exact strings parseable with:

`%d.%m.%Y %H:%M:%S`

Those strings are **opaque source metadata**. In particular, `firstHalfStarted` is not interpreted as authoritative kickoff, halftime, match duration, resumption, restart, continuation, replay, or settlement evidence.

The canonical kickoff remains `status.utcTime`, parsed as UTC. `match.time` is only a frozen-corpus corroboration field and must continue to match `status.utcTime` converted through `Europe/Oslo` at minute precision. This creates no global FotMob timezone claim.

Fields outside the required historical result projection remain preserved in the exact raw evidence and do not participate in result qualification. An opaque field may never override identity, score, reason, awarded, penalty, chronology, or source-provenance gates.

PR #89 and the prospective adapter remain untouched.

## Ordinary-FT result semantics

The historical adapter may consider only the eleven already-qualified PR #108 source-scoped competition families:

| Model family | FotMob `primaryId` |
|---|---:|
| B1 | 40 |
| D1 | 54 |
| E0 | 47 |
| F1 | 53 |
| G1 | 135 |
| I1 | 55 |
| N1 | 57 |
| P1 | 61 |
| SC0 | 64 |
| SP1 | 87 |
| T1 | 71 |

These eleven families are the current validated historical/model-research universe only; this protocol does not redefine ATHENA's broader competition universe.

An admitted ordinary-FT occurrence must require all of the following:

- exact source-scoped fixture and competition identity;
- exact stable wrapper league ID, home team ID, away team ID and kickoff UTC across A/B;
- `finished=true`;
- `started=true`;
- `cancelled=false`;
- `awarded` absent or exact `false`;
- exact PR #90 reason tuple `FT / fulltime_short / Full-Time / finished`;
- non-negative exact integer home and away scores;
- no `penScore` on either team.

`statusId`, `scoreStr`, `periodLength`, half-start strings, team names, red-card metadata and other opaque fields cannot create result semantics.

Awarded wins, after-extra-time, after-penalties, abandoned, cancelled, postponed, or any unreviewed state remain outside ordinary regulation-time history. PR #110 special-result dispositions and PR #112 rearrangement chronology remain authoritative.

## Frozen candidate accounting

The qualification must reproduce exactly:

- 21,336 ordinary-FT fixture/date occurrences;
- 21,336 unique source fixture IDs;
- zero duplicate ordinary-FT source fixture IDs;
- 304 reviewed special-state occurrences;
- `21,336 + 304 = 21,640` total target-family fixture/date pairs.

The PR #114 initialization boundary remains binding:

- 10 ordinary-FT occurrences are before their family replay floor and remain evidence only;
- 21,326 ordinary-FT occurrences are on or after the family replay floors.

The on-or-after-floor count by model family remains:

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

These 21,326 occurrences are **not authorized history rows by PR #116**. They are only future materialization candidates if the historical adapter is separately qualified and the completeness boundary is rerun successfully.

## Qualification output boundary

The next execution may produce only deterministic derived evidence:

- one projection record per reviewed ordinary-FT source fixture/date occurrence;
- exact source/competition/team/kickoff/score/reason fields;
- both manifest lineages and acquisition observation times;
- the before-floor versus on-or-after-floor disposition;
- deterministic projection and receipt hashes.

It must preserve all raw captures and may not destructively collapse source evidence.

It must materialize zero source-history rows and pass zero projection records into PR #80.

## Fail-closed requirements

Execution must fail closed on any change in artifact identity, manifest lineage, request identity, observation separation, A/B target stability, competition mapping, fixture/team identity, kickoff, score, reason tuple, awarded state, penalty evidence, `status.halfs` shape/type, source display-time corroboration, special-result disposition, or chronology.

No network reacquisition is allowed during qualification.

No source capability, competition, history, model, probability, pricing, market, selection, production, or betting registry may be mutated.

## Next boundary

`EXECUTE_REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_ADAPTER_QUALIFICATION`

That execution must qualify the newly pre-registered historical adapter against the exact preserved campaign. Even successful adapter qualification must not itself prove source-history completeness or authorize PR #80. Completeness/history materialization remains a later separately reviewed boundary.

## Canonical protocol identity

- SHA-256 `f987bc68eaf9f4c7b57a66788f3dcac5d704be6dad36ecae92bf5dd7e315ea9a`
- size `9,898` bytes
