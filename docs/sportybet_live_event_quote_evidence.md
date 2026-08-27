# SportyBet direct current event/quote evidence

## Purpose

This boundary turns the already-reviewed public anonymous SportyBet event read used by ATHENA's semantic booking-code gate into durable, replayable evidence for provider-native current market/outcome/odds values.

It does **not** automate the separately blocked SportyBet Lite HTML surface. It does not use ParseBot, BookBet, a proxy, browser impersonation, cookie replay, WAF bypass, login, wallet, stake, or wager placement.

The reviewed direct endpoint is the same one already used for semantic code generation:

`GET https://www.sportybet.com/api/ng/factsCenter/event?productId=3&eventId=<sr:match:...>`

with Nigeria `OperId: 2`.

## Why this is a separate source boundary

The manual SportyBet Lite evidence lane remains valid evidence for reviewed fixture reconciliation and canonical market/settlement mapping, but its observation time is explicitly user-attested:

`USER_ATTESTED_NOT_PROVIDER_TIMESTAMP`

That timestamp must not be promoted into provider-native quote time or silently treated as machine-acquired current price evidence.

The direct FactsCenter event response is different: ATHENA itself performs an already-reviewed public anonymous provider read and records the exact response-completion time. Therefore #246 may prove that specific provider-native odds values were present in the exact SportyBet response observed by ATHENA at that acquisition time.

The authority remains deliberately narrower than a provider-native timestamp claim:

`ATHENA_DIRECT_PROVIDER_RESPONSE_COMPLETION_NOT_PROVIDER_QUOTE_TIMESTAMP`

Accordingly:

- `provider_quote_at = null`;
- `provider_snapshot_id = null`;
- no server-side quote timestamp is invented;
- no provider snapshot identity is invented.

## Durable evidence

Exact raw JSON and a canonical manifest are stored only under:

`.cache/athena-research/sportybet-live-event-quote-evidence`

The manifest binds:

- exact provider and Nigeria region;
- reviewed source method and endpoint identity;
- exact `eventId` request target;
- fixed request headers;
- HTTP 200 and SportyBet `bizCode == 10000`;
- ATHENA response-completion observation time;
- exact raw byte SHA-256 and byte length;
- null provider quote timestamp/snapshot identity;
- network acquisition provenance;
- downstream authority flags.

Verification is read-only: it does not create a missing evidence root. Traversal, symlinks, unexpected files, noncanonical manifests, changed raw bytes, duplicate JSON keys, non-UTF-8 JSON, response-shape drift, wrong event identity, and failed provider status all fail closed.

## Current event inventory

Replaying one verified capture extracts exact provider-native:

- event ID;
- home and away labels;
- kickoff;
- event/bookability status;
- market ID and source-preserved market name;
- exact specifier;
- outcome ID and source-preserved label;
- observed odds;
- outcome bookability state.

Native IDs use the same bounded ASCII identity shape as the direct share transport. Active outcomes must carry finite decimal odds greater than 1.0. Unavailable outcomes may be retained only when they carry valid odds; an explicitly active outcome with missing/invalid odds fails closed.

The inventory SHA-256 is calculated from the complete deterministic normalized inventory and binds the exact raw/manifest ancestry.

## Reviewed canonical mapping rebind

Current odds are **not** mapped by fuzzy market names or odds inference.

A mapped quote requires an existing exact `SportyBetReviewedCanonicalMarketMapping`. For every reviewed row, #246 checks the current event's exact:

`(eventId, marketId, specifier, outcomeId)`

If that native identity still exists, the current market and outcome labels must also equal the reviewed labels exactly. Reuse of the same native IDs with changed human-readable semantics is a hard failure.

Settlement equivalence remains owned by the reviewed mapping. Rows without bookmaker/settlement equivalence do not become quotes merely because current odds exist.

A reviewed row that is absent from the current response or currently unavailable is recorded as an audit disposition rather than guessed or replaced. Current provider prices may legitimately differ from the odds preserved in the older mapping evidence: the old evidence proves reviewed semantics; the **current direct event response** supplies the price.

## Replay versus current issuance

Two different proof modes are intentionally frozen.

### Deterministic replay

`issue_mapped_quote_bundle_as_of(...)`

replays preserved evidence against an explicit historical evaluation time. It may prove that the observation was within the frozen 900-second window *as of that evaluation time*, but it always emits:

`DIRECT_PROVIDER_ODDS_EVIDENCE_AS_OF_REPLAY_VERIFIED`

and:

`current_observation_freshness_proven = false`.

An old capture therefore cannot be relabelled as current by choosing a convenient timestamp.

### Live current issuance

`capture_and_issue_current_mapped_quote_bundle(...)`

is the only public issuer that can emit:

`CURRENT_DIRECT_PROVIDER_ODDS_EVIDENCE_VERIFIED`.

It derives the SportyBet event ID from the exact reviewed mapping, performs the reviewed network GET itself, records response completion internally, durably stores and replays the exact response, and then evaluates freshness using ATHENA's internal current clock. There is no caller-supplied evaluation timestamp on this live entry point.

Both modes freeze:

- maximum observation age: **900 seconds**;
- minimum kickoff lead: **120 seconds**.

Neither bound is caller-overridable.

## Tamper resistance

Mapped quote and quote-bundle types are builder-only. `dataclasses.replace()` cannot mint altered odds, status, hashes, or proof modes.

The bundle retains its exact mapping, normalized inventory, evidence path and repository root. `verify_mapped_quote_bundle()` rereads the exact raw evidence, rebuilds the inventory, reconstructs all quote/audit rows and compares the complete deterministic representation. Detached digest or row relabelling therefore fails closed.

## Authority boundary

A successful live bundle may prove:

- exact reviewed direct-provider event read evidence;
- provider-native odds observed in that exact response;
- current observation freshness under the fixed ATHENA acquisition-time policy;
- exact reviewed canonical mapping rebind.

It does **not** grant:

- provider-native quote timestamp authority;
- provider snapshot identity;
- Phase 6/model authority;
- Price-all authority;
- Market Router authority;
- Accumulator Optimizer authority;
- final selection;
- accumulator approval;
- SportyBet code/execution authority;
- staking or wallet authority;
- `BET`.

The exact next boundary is:

`PRICE_ALL_DIRECT_PROVIDER_QUOTE_SOURCE_ADAPTER_REQUIRED`

That next boundary must extend/replace the current Phase 7 quote-source contract explicitly. It must not silently reinterpret Phase 7 v1's user-controlled HTML quote ancestry.

## Known remaining source prerequisite

This boundary starts from a **known reviewed SportyBet event ID**. It does not discover today's SportyBet fixture universe and does not invent a FotMob-to-SportyBet event ID.

For fully autonomous “today's 20-fold” execution, ATHENA still needs a reviewed current provider-event discovery/reconciliation path (or another reviewed source that supplies the exact current SportyBet event IDs) before this quote capture can be invoked for every eligible fixture.

## Manual capture command

For a known reviewed event ID:

```text
git pull && python -m scripts.capture_sportybet_live_event_quote_evidence \
  --event-id 'sr:match:123' \
  --execute-live-network
```

The command captures evidence only. It prints hashes/provenance and explicitly reports Price-all, selection, SportyBet execution and BET authorization as false.
