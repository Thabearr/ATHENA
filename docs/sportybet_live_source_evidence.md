# SportyBet public Lite source evidence boundary

## Purpose

This boundary establishes a read-only evidence path for SportyBet Nigeria without
activating the legacy betting product surface. It preserves exact source bytes
and extracts only provider-native identifiers that can be proven from the
reviewed public Lite HTML surface.

It does **not** authorize fixture reconciliation, canonical ATHENA market
mapping, fresh-price use, pricing, selection, slip construction, booking codes,
SportyBet execution, or `BET`.

## Reviewed public source surface

Current source discovery on 2026-08-18 found an official, public,
unauthenticated SportyBet Nigeria Lite surface:

- `https://www.sportybet.com/ng/lite`
- `https://www.sportybet.com/ng/lite/preMatch/detail?...`

The public HTML links expose provider-native selection references containing,
when present:

- `eventId` such as `sr:match:<number>`;
- `marketId`;
- `outcomeId`;
- decimal `odds`;
- `productId`;
- `sportId` such as `sr:sport:1`;
- `marketGroupsName`;
- line/specifier query data when the provider supplies it.

The implementation uses only ordinary HTTPS `GET`, fixed transparent headers,
no cookies, no credentials, no login, no browser impersonation, no CAPTCHA or
anti-bot bypass, and no write/betslip action.

SportyBet does not publish a documented third-party developer API. This PR
therefore does **not** treat third-party wrappers as authoritative source data
and does not invent a JSON API contract.

## What is proven and what is not

The reviewed Lite source proves that provider-native event/market/outcome IDs
and displayed odds can be embedded in public source links. It does not yet
prove a provider quote/update timestamp or provider snapshot ID. Consequently:

- `observed_at` is the ATHENA capture time only;
- `provider_quote_at` remains `null`;
- `provider_snapshot_id` remains `null`;
- capture time is never substituted for quote time;
- this evidence cannot authorize a future fresh-price decision by itself.

The visible Lite pages also display competition, team and kickoff text, but this
boundary does not guess a machine-readable association for those fields. Until
an exact provider-native representation is proven, competition IDs/names,
participant IDs/names, kickoff and event status remain `null` in the structured
event inventory. The exact raw HTML is retained so a later reviewed extractor
can add those fields without rewriting history.

## Raw capture contract

`domain/sportybet_lite_source_capture.py` freezes:

- provider and allowed host;
- exact INDEX and EVENT_DETAIL request targets;
- request headers;
- HTTP 200 requirement;
- `text/html` media-type requirement;
- bounded exact raw bytes;
- content-length consistency;
- UTC `observed_at`;
- network-acquisition provenance;
- raw byte size and SHA-256;
- canonical UTF-8/LF JSON manifest;
- fail-closed provider quote/snapshot fields;
- all downstream authority false.

Capture publication is restricted to the ignored research root:

`.cache/athena-research/sportybet-live-source-captures`

A capture identity is provider + request target + exact `observed_at`. Reusing
the same observation identity with identical bytes is idempotent. Reusing it
with different bytes fails closed. Traversal and symlink escape are rejected.

## Provider-native inventory

`domain/sportybet_provider_native_inventory.py` parses only structurally
qualified SportyBet Lite selection links. A usable selection requires all of:

- valid `sr:match:<positive integer>` event ID;
- market ID;
- outcome ID;
- valid decimal odds greater than 1;
- SportyBet Lite path/host identity.

Market identity is `(market_id, specifier)`, so line-sensitive markets are not
collapsed. For example, market `18` with `total=2.5` and market `18` with
`total=3.5` remain distinct provider-native markets.

Selection identity is `(event_id, market_id, specifier, outcome_id)`. Duplicate
selection identity is rejected, including duplicates that disagree on odds.

Provider market names and labels are preserved only when explicitly attached to
the source link. They are never fuzzy-mapped to ATHENA canonical markets.
Explicit suspension/lock markers are preserved as `SUSPENDED`; absent explicit
state remains `UNKNOWN`, not silently `AVAILABLE`.

The inventory is canonically ordered and serialized. All downstream authority
remains false.

## Explicit live capture command

The new command is manual and explicit:

```powershell
python -m scripts.capture_sportybet_lite_source --index
python -m scripts.capture_sportybet_lite_source --event-id sr:match:12345678
```

It is **not** scheduled by this PR and PR CI does not make SportyBet requests.
A successful command writes raw/manifest evidence plus a provider-native
inventory under ignored research storage. If the current SportyBet surface
redirects, blocks, changes media type, returns malformed evidence, or no longer
contains structurally qualified selection links, the command fails closed with
`BLOCKED`.

## Product safety

`services/betting_service.py` remains unchanged. SportyBet booking-code
resolution continues to return:

`BLOCKED_UNTIL_REVIEWED_LIVE_BOOKMAKER_RESOLVER`

No ATHENA approval percentage, edge, expected value, Kelly, stake, ACCA,
booking code, slip, or BET decision is produced by this boundary.

## Next boundary

After reviewed live source captures exist, the next independent boundary is
exact SportyBet event identity reconciliation against the trusted fixture side.
Only after exact fixture identity is proven should ATHENA map provider-native
SportyBet markets to canonical ATHENA market semantics. Fresh quote validation
and value remain later gates.
