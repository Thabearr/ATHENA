# SportyBet public Lite source evidence boundary

## Purpose

This boundary establishes ATHENA's first reviewed SportyBet source-shape and
provider-native market evidence contract without activating automated website
acquisition or the legacy betting product surface.

It preserves the exact request/capture contract needed for a future authorized
source path and deterministically inventories provider-native event/market/
outcome/odds evidence from reviewed Lite HTML bytes. It does **not** authorize
fixture reconciliation, canonical ATHENA market mapping, fresh-price use,
pricing, selection, slip construction, booking codes, SportyBet execution, or
`BET`.

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
`marketId=16` and `specifier=hcp=-2.5`. This proves provider source shape only;
it is not ATHENA canonical-market equivalence.

## Automated-access permission is not proven

ATHENA also reviewed SportyBet Nigeria's current Terms and Conditions on
2026-08-18. The terms reserve SportyBet's right to block access where automated
or robotic activity is indicated. Public unauthenticated accessibility is
therefore **not** treated as permission for an ATHENA automated collector.

The frozen state for this boundary is:

`BLOCKED_UNTIL_EXPLICIT_SPORTYBET_AUTOMATED_ACCESS_PERMISSION`

Accordingly:

- `network_acquisition_authorized = false`;
- no scheduled SportyBet collector is added;
- PR CI performs no SportyBet request;
- the command in `scripts/capture_sportybet_lite_source.py` performs no network
  I/O and emits a deterministic blocked receipt;
- no login, credentials, cookies, browser impersonation, CAPTCHA/anti-bot
  bypass, proxy evasion, write action, betslip action, or bet placement is used.

This is deliberately fail-closed. A later reviewed boundary may replace the
block only after an explicit permitted source method is established.

## What is proven and what is not

The reviewed Lite source proves that provider-native event/market/outcome IDs,
displayed decimal odds, and line specifiers can be embedded in public source
links. It does not prove a provider quote/update timestamp or provider snapshot
ID. Consequently:

- `observed_at` is capture/observation time only;
- `provider_quote_at` remains `null`;
- `provider_snapshot_id` remains `null`;
- observation time is never substituted for quote time;
- this evidence cannot authorize a future fresh-price decision by itself.

The visible Lite pages display competition, participant and kickoff text, but
this boundary does not guess a machine-readable association for those fields.
Until an exact representation is proven, competition IDs/names, participant
IDs/names, kickoff and event status remain `null` in structured event records.

## Raw capture contract

`domain/sportybet_lite_source_capture.py` freezes the contract a future
separately authorized acquisition method must satisfy:

- provider and reviewed host;
- exact INDEX and EVENT_DETAIL request targets;
- exact transparent request headers;
- HTTP 200 requirement;
- `text/html` media-type requirement;
- bounded exact raw bytes;
- Content-Length consistency when supplied;
- UTC `observed_at`;
- explicit network-acquisition provenance;
- raw byte size and SHA-256;
- canonical UTF-8/LF JSON manifest;
- fail-closed provider quote/snapshot fields;
- all downstream authority false.

Capture publication is restricted to:

`.cache/athena-research/sportybet-live-source-captures`

That root is ignored by repository policy. Capture identity is provider + exact
request target + exact `observed_at`. Same identity/same bytes is idempotent;
same identity/different bytes fails closed. Verification binds the directory
name to the canonical manifest identity, checks exact raw bytes/hash/size,
rejects extra files, traversal and symlinks, and requires network provenance by
default.

Raw and manifest files are file-fsynced and directory entries are explicitly
synchronized. Unsupported directory-durability platforms fail closed rather
than silently claiming durable publication.

The presence of this capture contract does **not** itself grant network
acquisition authority.

## Provider-native inventory

`domain/sportybet_provider_native_inventory.py` parses only structurally
qualified SportyBet Lite selection links from supplied evidence bytes. A usable
selection requires all of:

- valid `sr:match:<positive integer>` event ID;
- market ID;
- outcome ID;
- valid decimal odds greater than 1;
- SportyBet Lite path/host identity.

Market identity is `(market_id, specifier)`. Line-sensitive markets therefore
remain distinct; `total=2.5`, `total=3.5`, and `hcp=-2.5` are not collapsed.

Selection identity is `(event_id, market_id, specifier, outcome_id)`. Duplicate
selection identity is rejected, including duplicates that disagree on odds.

Provider market names and labels are preserved only when explicitly attached
to qualified selection evidence. The extractor does not infer names from nearby
page text and never fuzzy-maps to ATHENA canonical markets. Explicit
suspension/lock state is retained when attached to a qualified selection;
absent state remains `UNKNOWN`, never silently `AVAILABLE`. A visual locked item
without a qualified provider-native selection link remains raw evidence rather
than receiving invented IDs.

The inventory is canonically ordered and serialized. All downstream authority
remains false.

## Product safety

`services/betting_service.py` remains unchanged. SportyBet booking-code
resolution continues to return:

`BLOCKED_UNTIL_REVIEWED_LIVE_BOOKMAKER_RESOLVER`

No ATHENA approval percentage, model integration, edge, expected value, Kelly,
stake, ACCA, canonical market activation, booking code, slip, SportyBet
execution, or BET decision is produced by this boundary.

## Next boundary

The next SportyBet boundary is to establish a source method ATHENA is actually
permitted to use (for example, an explicit provider-approved interface or a
separately reviewed user-controlled evidence workflow). Only after real
reviewed captures exist should ATHENA perform exact SportyBet event identity
reconciliation against the trusted fixture side. Canonical market semantics,
fresh quote validation, value, selection and BET remain later independent
gates.
