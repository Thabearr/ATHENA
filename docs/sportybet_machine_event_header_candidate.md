# SportyBet machine event-header candidate

## Purpose

PR #153 established user-controlled preservation of exact SportyBet Lite HTML. PR #154 derives exact provider-native event, market, outcome and odds identities from those preserved bytes. PR #155 can compare a SportyBet event header with reviewed FotMob fixtures, but its participant/competition/kickoff input is still explicitly user-attested.

This boundary removes one part of that manual dependency without pretending the remaining gaps are solved. It derives a **machine event-header candidate** from the same exact preserved SportyBet event-detail HTML that produced the PR #154 odds inventory.

The candidate contains:

- exact SportyBet `eventId` and `sportId` from the reviewed event-detail source identity;
- visible competition text;
- visible home participant text;
- visible away participant text;
- visible `DD/MM Weekday HH:MM` kickoff text and its parsed day/month/weekday/hour/minute components;
- exact source evidence ID, manifest SHA-256, raw HTML SHA-256 and PR #154 native-inventory SHA-256.

It remains research evidence only. `fixture_reconciliation_authorized` stays false.

## Exact lineage

The builder accepts only:

1. a valid PR #153 `SportyBetUserControlledEvidenceManifest` for the reviewed **event-detail** URL;
2. a PR #154 `SportyBetUserControlledNativeInventory` derived from that exact evidence;
3. the exact raw HTML bytes whose SHA-256 and byte count match the manifest.

It first re-proves the evidence ID, evidence-manifest hash, raw hash, source URL, event ID, sport ID and event population. It then **re-runs the PR #154 provider-native selection extraction against the exact raw HTML bytes**, reconstructs the expected PR #154 user-controlled inventory with the manifest's exact acquisition/observation metadata, and requires the supplied inventory's canonical JSON bytes to equal that deterministic reconstruction exactly.

This second replay matters because matching stored hashes alone is insufficient: a coordinated in-memory inventory forgery could otherwise preserve the source lineage fields while altering odds, selections, availability or other inventory metadata. Such a forged inventory now fails closed even when its own dataclass invariants remain internally coherent.

The frozen protocol records this rule as:

`native_inventory_revalidation = EXACT_DETERMINISTIC_REDERIVATION_FROM_SAME_RAW_HTML_REQUIRED`

The candidate therefore cannot be detached from the exact provider-native odds inventory implied by the preserved source bytes without failing closed.

## Visible-text extraction rule

The extractor operates on rendered-text candidates only. It ignores `script`, `style`, `noscript`, `svg` and `template` content and collapses rendered whitespace. It does **not** case-fold, Unicode-normalize, infer aliases, shorten club names, reverse participants, or use fuzzy matching.

A candidate window must contain one of these exact shapes:

- one text token: `DD/MM Weekday HH:MM`; or
- two adjacent text tokens: `DD/MM Weekday` then `HH:MM`.

The nearest non-navigation visible text before the time window is the competition candidate. The next two non-navigation visible text tokens are the home and away candidates. Labels that look like odds, navigation, or another date/time token are rejected.

Month/day values are checked without inventing a year: February 29 remains possible, while dates such as 31 February or 31 April are impossible and fail closed.

If no complete candidate exists, extraction fails. If more than one **distinct** complete candidate exists, extraction fails as ambiguous. Repeated identical rendered copies may collapse to the same semantic candidate; this accommodates duplicate responsive markup without allowing conflicting event identity to pass.

## What this does not prove

The preserved event-detail HTML contract still does not prove a year or timezone field for the displayed kickoff. This PR therefore records:

- `kickoff_year = null`;
- `kickoff_timezone = null`;
- `kickoff_utc = null`;
- `display_time_basis = UNPROVEN_IN_PRESERVED_EVENT_DETAIL_HTML`.

The displayed time is not treated as a provider quote timestamp, and `provider_quote_at` and `provider_snapshot_id` remain null.

A separate reviewed source-qualification boundary must establish SportyBet's displayed-time basis before this candidate can provide an exact UTC kickoff for production reconciliation. Discovery outside ATHENA's preserved evidence chain is not silently promoted into trust evidence.

## Safety state

This PR does not change `BettingService` and does not authorize:

- network acquisition;
- production SportyBet ↔ FotMob fixture reconciliation;
- bookmaker equivalence;
- canonical market mapping;
- fresh SportyBet price claims;
- model/value integration;
- selection;
- ACCA/slip construction;
- booking-code generation;
- SportyBet execution;
- `BET`.

Every corresponding safety field is exactly `false`.

## Why this advances the SportyBet path

Before this boundary, the event-level join candidate depended on a human copying competition, participants and kickoff from the SportyBet page. After this boundary, the competition/participants/displayed clock can be derived deterministically from the exact same provider page bytes that contain the provider-native odds, while the PR #154 inventory itself is replay-verified against those bytes.

The remaining event-identity blocker is narrower: prove the displayed clock's provider time basis/year semantics on preserved reviewed evidence, then re-evaluate whether an exact machine-derived SportyBet event can be reconciled to one reviewed FotMob fixture.

The wider product chain remains:

`SportyBet event + native odds -> reviewed fixture identity -> canonical market equivalence -> fresh-price proof -> calibrated model/value + fragility -> selection -> ACCA/slip -> SportyBet booking code`

No later gate is skipped.

## Hosted validation

The final replay-hardened exact head is validated by hosted Tests run `32154163383` / run #749. Syntax, all eight deterministic shards, and the aggregate test gate succeeded. Shard 8 contains this boundary's adversarial suite and finished `580 passed, 16 subtests passed`.

No local pytest was run and no SportyBet network request is made by this PR's tests.

## Next boundary

The next SportyBet trust boundary should preserve and qualify the provider's official displayed-time semantics as exact evidence, then test this extractor against genuine preserved event-detail pages. Only if that evidence is unambiguous should the PR #155 user-attested kickoff be replaceable with a machine-derived UTC fixture identity.
