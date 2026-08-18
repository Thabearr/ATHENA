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

Current source discovery on 2026-08-18 verified an official, public,
unauthenticated SportyBet Nigeria Lite HTML surface at:

- `https://www.sportybet.com/ng/lite`
- `/ng/lite/preMatch/detail?...`

Current public selection links were inspected directly. They proved provider
query fields including, when supplied:

- `eventId` such as `sr:match:<number>`;
- `marketId`;
- `outcomeId`;
- decimal `odds`;
- `productId`;
- `sportId` such as `sr:sport:1`;
- `marketGroupsName`;
- `specifier` for line-sensitive markets.

The reviewed source showed, for example, a Total Goals selection with
`marketId=18` and `specifier=total=2.5`, and an Asian Handicap selection with
`marketId=16` and `specifier=hcp=-2.5`. This is source-shape evidence only; it
is not ATHENA canonical-market equivalence.

The implementation uses one ordinary HTTPS `GET`, fixed transparent headers,
no cookies, no credentials, no login, no browser impersonation, no CAPTCHA or
anti-bot bypass, and no write/betslip action.

This boundary does not claim or depend on a public developer API. It implements
only the exact Lite HTML surface actually reviewed.

## What is proven and what is not

The reviewed Lite source proves that provider-native event/market/outcome IDs,
displayed decimal odds, and line specifiers can be embedded in public source
links. It does not prove a provider quote/update timestamp or provider snapshot
ID. Consequently:

- `observed_at` is the ATHENA capture time only;
- `provider_quote_at` remains `null`;
- `provider_snapshot_id` remains `null`;
- capture time is never substituted for quote time;
- this evidence cannot authorize a future fresh-price decision by itself.

The visible Lite pages display competition, participant and kickoff text, but
this boundary does not guess a machine-readable association for those fields.
Until an exact representation is proven, competition IDs/names, participant
IDs/names, kickoff and event status remain `null` in the structured event
inventory. Exact raw HTML is retained so a later reviewed extractor can add
those fields without rewriting history.

## Raw capture contract

`domain/sportybet_lite_source_capture.py` freezes:

- provider and reviewed host;
- exact INDEX and EVENT_DETAIL request targets;
- request headers;
- HTTP 200 requirement;
- `text/html` media-type requirement;
- bounded exact raw bytes;
- Content-Length consistency when supplied;
- UTC `observed_at`;
- network-acquisition provenance;
- raw byte size and SHA-256;
- canonical UTF-8/LF JSON manifest;
- fail-closed provider quote/snapshot fields;
- all downstream authority false.

Capture publication is restricted to:

`.cache/athena-research/sportybet-live-source-captures`

That root is already ignored by repository policy. Capture identity is provider
+ exact request target + exact `observed_at`. Same identity/same bytes is
idempotent; same identity/different bytes fails closed. Verification binds the
capture directory name back to the canonical manifest identity, checks exact
raw bytes/hash/size, rejects extra files, traversal and symlinks, and requires
network provenance by default.

Raw and manifest files are file-fsynced and directory entries are explicitly
synchronized. Unsupported directory-durability platforms fail closed rather
than silently claiming durable publication.

## Provider-native inventory

`domain/sportybet_provider_native_inventory.py` parses only structurally
qualified SportyBet Lite selection links. A usable selection requires all of:

- valid `sr:match:<positive integer>` event ID;
- market ID;
- outcome ID;
- valid decimal odds greater than 1;
- SportyBet Lite path/host identity.

Market identity is `(market_id, specifier)`. Line-sensitive markets therefore
remain distinct; `total=2.5`, `total=3.5`, and `hcp=-2.5` are not collapsed.

Selection identity is `(event_id, market_id, specifier, outcome_id)`. Duplicate
selection identity is rejected, including duplicates that disagree on odds.

Provider market names and labels are preserved only when they are explicitly
attached to selection evidence. The extractor does not infer a market name from
nearby page text and never fuzzy-maps names to ATHENA canonical markets.
Explicit suspension/lock state is retained when attached to a qualified source
selection; absent state remains `UNKNOWN`, never silently `AVAILABLE`. A visual
locked item without a qualified provider-native selection link remains present
in raw evidence rather than receiving invented IDs.

The inventory is canonically ordered and serialized. All downstream authority
remains false.

## Explicit live capture command

The command is manual and explicit:

```powershell
python -m scripts.capture_sportybet_lite_source --index
python -m scripts.capture_sportybet_lite_source --event-id sr:match:12345678
```

It is **not** scheduled by this PR and PR CI makes no SportyBet request. A
successful command writes raw/manifest evidence plus provider-native inventory
under ignored research storage. Redirects, access blocks, media-type changes,
malformed evidence, or absence of structurally qualified selection links fail
closed with `BLOCKED`.

## Product safety

`services/betting_service.py` remains unchanged. SportyBet booking-code
resolution continues to return:

`BLOCKED_UNTIL_REVIEWED_LIVE_BOOKMAKER_RESOLVER`

No ATHENA approval percentage, model integration, edge, expected value, Kelly,
stake, ACCA, canonical market activation, booking code, slip, SportyBet
execution, or BET decision is produced by this boundary.

## Next boundary

After reviewed live source captures exist, the next independent boundary is
exact SportyBet event identity reconciliation against the trusted fixture side.
Only after exact fixture identity is proven should provider-native markets be
mapped to canonical ATHENA semantics. Fresh quote validation and value remain
later independent gates.
