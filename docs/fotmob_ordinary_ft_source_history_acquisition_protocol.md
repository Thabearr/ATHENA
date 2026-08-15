# Reviewed FotMob ordinary-FT source-history acquisition protocol

PR #101 pre-registers the exact acquisition campaign required before ATHENA can attempt to prove historical completeness for the registered derived source:

`fotmob_data_matches_reviewed_ordinary_ft_finished_score`

This PR is a **protocol only**. It performs no network request, implements no campaign runner, materializes no history rows, changes no source capability, and authorizes nothing downstream.

## Why this boundary exists

PR #98 registered a narrow source-reported ordinary full-time score capability. PR #99 bound that source to the source-history completeness contract. PR #100 executed the contract and correctly stopped at `BLOCKED_HISTORICAL_COVERAGE_UNPROVEN`, while the initialization boundary and acquisition-backed league confirmation remained unproven.

The safe next step is therefore to freeze the request identity, six-season window, repetition schedule, eleven competition mappings, raw lineage, failure behavior, special-result handling, and chronology checks before any campaign runner or network acquisition exists.

## Frozen request identity

Every campaign slot must use the reviewed transparent data-matches capture boundary:

- method: `GET`
- scheme/host: `https://www.fotmob.com`
- port: `443`
- path: `/api/data/matches`
- `date`: canonical `YYYYMMDD`
- `timezone=Europe/London`
- `ccode3=GBR`
- headers exactly `Accept: application/json` and `User-Agent: ATHENA/1.0`
- no `x-mas`
- no redirects, cookies, browser impersonation, or proxy evasion

This corrects the draft's earlier UTC/NGA request identity and binds the campaign to the reviewed FotMob source context used by the finished-score evidence chain.

## Frozen six-season acquisition envelope

The initial campaign covers every Europe/London request date from:

- start: `2020-08-01`
- end: `2026-05-24`
- inclusive dates: `2,123`

The window is intentionally limited to the frozen PR #69 six-season replay envelope (`2020-21` through `2025-26`). It is not extended into 2026-27 merely because the protocol is being authored in August 2026.

The lower bound remains a **candidate** initialization boundary. This pre-registration does not prove equivalence to PR #69's replay start; that remains a later evidence gate after acquisition.

Frozen PR #69 context retained by this protocol:

- six seasons: `2020-21` through `2025-26`
- 66 source files
- 21,226 parsed source fixtures
- source-corpus SHA-256: `c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0`

## Repeated-capture schedule

Every required date has two successful capture slots:

- slot `A`
- slot `B`
- all `A` dates are attempted in ascending order, followed by all `B` dates in ascending order
- `B` must be observed at least `300` seconds after `A` for the same date
- the pair must remain within `86,400` seconds
- minimum inter-request spacing: `1.0` second
- maximum attempts per slot: `3`
- retry delays: `60`, then `300` seconds
- failed attempts never count as successful slots and remain durable evidence

Qualification therefore requires:

`2,123 dates × 2 successful slots = 4,246 successful captures`

The reviewed ordinary-FT adapter also requires distinct capture lineages. If the pair has the same raw SHA-256 or the same manifest SHA-256, that date cannot qualify under the current adapter contract; the protocol does not weaken that rule to make historical acquisition easier.

## Eleven frozen reviewed FotMob mapping candidates

The competition bridge is frozen as follows:

| Model league | FotMob ID | FotMob name | Country | Official path |
|---|---:|---|---|---|
| B1 | 40 | First Division A | Belgium | `/leagues/40/overview` |
| D1 | 54 | Bundesliga | Germany | `/leagues/54/overview` |
| E0 | 47 | Premier League | England | `/leagues/47/overview` |
| F1 | 53 | Ligue 1 | France | `/leagues/53/overview` |
| G1 | 135 | Super League 1 | Greece | `/leagues/135/overview` |
| I1 | 55 | Serie A | Italy | `/leagues/55/overview` |
| N1 | 57 | Eredivisie | Netherlands | `/leagues/57/overview` |
| P1 | 61 | Liga Portugal | Portugal | `/leagues/61/overview` |
| SC0 | 64 | Premiership | Scotland | `/leagues/64/overview` |
| SP1 | 87 | LaLiga | Spain | `/leagues/87/overview` |
| T1 | 71 | Super Lig | Türkiye | `/leagues/71/overview` |

Each carries the state:

`PRE_REGISTERED_REVIEWED_OFFICIAL_FOTMOB_MAPPING_REQUIRES_CAPTURE_CONFIRMATION`

The mapping candidates have been reviewed and are now part of the frozen protocol, but the later corpus still must observe the matching FotMob `leagueId` before a fixture can satisfy that league gate. The bridge does not create cross-source team or fixture identity.

## Raw evidence and lineage

Every successful slot must preserve exact raw response bytes and the canonical reviewed capture manifest. The campaign index must bind request date, slot, capture identifier, raw SHA-256 and byte size, manifest SHA-256, and exact UTC observation time.

The campaign index and failure journal must be canonical append-only research evidence outside Git. Raw historical captures are not to be committed merely for convenience. No overwrite is allowed: a later success cannot delete or rewrite an earlier failed attempt.

Before a date can feed the ordinary-FT adapter, its two selected captures must have distinct manifest SHA-256 values **and distinct raw SHA-256 values**, preserving the existing adapter's lineage requirement.

## Failure semantics

Any required date without two valid successful slots blocks campaign qualification. HTTP non-200 responses, timeouts, content-type failures, oversized/empty bodies, manifest verification errors, or durability failures must be recorded and fail closed.

Retries are bounded by the frozen slot policy. Missing dates may not be silently skipped or filled from `fotmob_historical`, football-data.co.uk, football-data.org, or any other provider.

## Ordinary-FT and special-result semantics

Only fixtures admitted by the reusable reviewed ordinary-FT finished-score adapter may enter the derived history. Every in-scope finished fixture rejected by that adapter must remain visible with its exact blocking disposition.

Penalties, extra time, awarded results, or another non-ordinary finish may not be coerced into ordinary FT. Postponed, cancelled, abandoned, and rearranged fixtures require explicit source-state disposition and may not disappear. Any unresolved in-scope finished fixture outside the ordinary-FT gate blocks completeness unless a later separate review qualifies its semantics.

## Identity and chronology

The later corpus must prove:

- stable exact FotMob fixture ID, league ID, team IDs, and kickoff across captures;
- no duplicate fixture ID or same-team/same-kickoff ambiguity;
- consistency between the Europe/London request date and source kickoff UTC, or an explicit blocking disposition;
- source-scoped team-ID continuity across seasons without fuzzy name merging;
- no target fixture included in its own prior history;
- deterministic replay order of kickoff UTC then source fixture ID after chronology qualification.

Capture-pair drift is evidence and must be reconciled or blocked before that date can support history.

## What remains unproven

After PR #101:

- PR #69 initialization-boundary equivalence remains unproven;
- each frozen league mapping still requires capture confirmation;
- daily historical coverage remains unproven;
- result-evidence completeness remains unproven;
- non-ordinary finished states remain subject to their existing semantic gates;
- identity/chronology consistency remains unproven;
- no source-history adapter is approved;
- `historical_coverage` remains `UNKNOWN`.

## Canonical identity

- Protocol: `REVIEWED_FOTMOB_ORDINARY_FT_SOURCE_HISTORY_ACQUISITION_PROTOCOL_V1`
- SHA-256: `6baeb5bc8fd03fb20024a20266092c85886c21e66da493b3100510ec871b5ebb`
- Size: `9,959` bytes
- Repository anchor: `06e180412381316b7cf521c912a6dd4dfe35ea50`

## Safety

Every safety flag remains exact `false`, including network acquisition, campaign-runner approval, source-history execution/completeness, PR #80 constructor input, successor/model approval, expected-goals production, probability execution, pricing, market activation, selection, production approval, and BET authority.

## Next boundary

`IMPLEMENT_REVIEWED_FOTMOB_ORDINARY_FT_SOURCE_HISTORY_ACQUISITION_RUNNER`

That PR may implement the deterministic orchestrator, durable retry/failure journal, and campaign index frozen here. Actual network execution and later source-history qualification remain separate reviewed boundaries.
