# SportyBet current event discovery + source-replayed FotMob reconciliation

## Purpose

PR #251 closes the autonomous event-identity gap left after Portfolio Optimizer v2. The direct SportyBet quote lane already knew how to read one exact `sr:match:<id>` once that provider event ID was known. This boundary discovers current SportyBet football event IDs and reconciles them conservatively to ATHENA's reviewed FotMob fixture truth.

The boundary is deliberately narrow. It grants current event discovery, direct event-detail confirmation, and exact fixture reconciliation only. It does not grant canonical market mapping, Price-all, Router, portfolio optimization, final selection, slip construction, execution, staking, or BET authority.

## Provider discovery source

The discovery request is an anonymous read-only FactsCenter GET:

`/api/ng/factsCenter/liveOrPrematchEvents?sportId=sr%3Asport%3A1&pageSize=100&pageNum=<n>`

ATHENA sends the reviewed public headers only. It does not use login state, cookies, wallet data, account tokens, a betslip, staking, or browser impersonation.

Pagination is bounded at 20 pages. A successful discovery capture must observe a terminal empty page. Reaching the bound without an empty terminal page fails closed rather than claiming complete coverage. This contract therefore describes the exact observed current SportyBet event-list source; it does not claim mathematical completeness of every possible SportyBet catalogue surface.

Every raw page is retained under:

`.cache/athena-research/sportybet-current-event-discovery/<capture-id>/`

with a canonical manifest that records request target, response-completion observation time, raw SHA-256, size, and the exact events derived from that page.

## Time semantics

`observed_at` is ATHENA's response-completion time. It is not relabelled as a SportyBet provider event timestamp, provider quote timestamp, or provider snapshot ID.

The discovery contract uses the same reviewed currentness bounds as PR #246:

- maximum source age: 900 seconds;
- minimum kickoff lead: strictly greater than 120 seconds.

Both the discovery observation and the PR #246 direct event-detail observation are checked at the final PR #251 issuance time. An event is not authorized when either observation is stale or when the final kickoff lead is 120 seconds or less.

## FotMob remains fixture truth

SportyBet is not promoted into ATHENA's primary fixture catalogue merely because it lists a betting event.

Before any SportyBet/FotMob match can receive reconciliation authority, PR #251 requires an exact `ReviewedFixtureCatalogAdmission` plus the exact raw FotMob `/api/data/matches` captures from which that admission was derived.

The boundary then replays the existing reviewed FotMob chain:

1. verify every raw capture against its exact capture manifest;
2. rebuild the FotMob fixture-candidate bundle from those raw bytes;
3. replay the explicit human fixture-review decisions;
4. rebuild the exact `FotMobFixtureCatalogHandoff`;
5. require canonical equality with the handoff retained by the supplied reviewed admission;
6. require the catalog admission disposition to be exactly `ADMITTED`;
7. require the reviewed FotMob source capability and fail-closed admission safety state;
8. only then expose the reviewed FotMob catalog inputs for reconciliation.

A prebuilt handoff by itself is therefore insufficient. This prevents a caller from presenting a semantically plausible catalog object without the raw FotMob ancestry that earned its authority.

The issued bundle retains immutable identities for the admitted catalog and its raw capture population, including the admission, candidate bundle, review bundle, handoff, catalog, manifest, raw-capture, and capture-manifest SHA-256 identities.

## Exact reconciliation

The matching basis is:

`EXACT_CASE_SENSITIVE_HOME_AWAY_COMPETITION_FULL_UTC_NO_ALIAS_NO_FUZZY_NO_REVERSAL_NO_ROUNDING_NO_TOLERANCE`

The provider event must exactly equal one reviewed FotMob input on:

- home team display name;
- away team display name;
- competition display name;
- full UTC kickoff.

There is no case folding, alias table, fuzzy score, home/away reversal, kickoff rounding, or tolerance window in this boundary.

Missing or conflicted provider competition identity remains explicit and cannot reconcile.

One provider event matching multiple reviewed FotMob fixtures is ambiguous. Multiple distinct provider event IDs targeting one reviewed FotMob fixture are also all ambiguous. ATHENA does not choose among them.

## Direct event-detail confirmation

Discovery alone is not enough to grant fixture reconciliation.

For each uniquely matched, non-ambiguous candidate, PR #251 executes the already reviewed PR #246 anonymous direct event GET and preserves that evidence under the PR #246 evidence root. The direct event inventory must confirm the same:

- `event_id`;
- home team;
- away team;
- full UTC kickoff;
- prematch/bookable state.

The direct event observation must also remain within the 900-second age limit at PR #251 issuance.

This two-source SportyBet check prevents an event-list row from gaining fixture authority without confirmation from the event-specific source that later supplies current quote evidence.

## Explicit dispositions

Every discovered event remains visible with one deterministic disposition:

- `UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED`;
- `DISCOVERY_EVENT_NOT_PREMATCH_BOOKABLE`;
- `PROVIDER_COMPETITION_UNPROVEN`;
- `DISCOVERY_EVIDENCE_STALE`;
- `PROVIDER_EVENT_TOO_CLOSE_TO_KICKOFF`;
- `NO_EXACT_REVIEWED_FOTMOB_MATCH`;
- `AMBIGUOUS_EXACT_REVIEWED_FOTMOB_MATCH`;
- `AMBIGUOUS_PROVIDER_EVENT_FOR_FIXTURE`;
- `DIRECT_EVENT_DETAIL_IDENTITY_MISMATCH`;
- `DIRECT_EVENT_DETAIL_NOT_PREMATCH_BOOKABLE`;
- `DIRECT_EVENT_DETAIL_STALE`.

Only `UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED` sets `fixture_reconciliation_authorized=true`.

A successful empty SportyBet discovery feed remains a valid zero-event observation. ATHENA does not fill it from another source and does not fabricate provider event IDs.

## Reconstruction and tamper resistance

`SportyBetCurrentEventDiscoveryReconciliationBundle` is builder-only.

`verify_current_event_discovery_reconciliation_bundle()` replays:

- the exact raw FotMob captures into the reviewed admitted catalog chain;
- every preserved SportyBet discovery page into the discovery manifest;
- every retained PR #246 direct event-detail capture into its current event inventory;
- the exact matching, ambiguity, freshness, and kickoff-lead policy at the original issuance time.

The rebuilt canonical bundle must equal the supplied bundle exactly. Public-field mutation or retained-source mutation fails closed.

The verifier proves what was true at the original PR #251 issuance time. It does not make an old bundle perpetually current; downstream current market mapping and pricing consumers must perform their own currentness checks when they consume it.

## Contract identities

PR #251 pins:

- PR #246 direct event source contract: `b888cebab6447cd4072d823dab67b56f1f75f72eb72d67b692d47a4378b27555`;
- PR #250 Portfolio Optimizer v2 contract: `919149759ffc9aabef2fefe7c6e0db72d697ebd1ffe33205054fc3ffb4f785fd`;
- reviewed FotMob catalog-admission dataset/schema;
- raw FotMob data-matches capture dataset/schema;
- the 900-second / 120-second currentness policy;
- the exact source-replay and matching semantics above.

Current PR #251 contract SHA-256:

`64c7a2b71304f94a39de7e608be1f76a10e14a1a52a338f89d1c695ba0e5f1ee`

## Authority boundary

The contract can issue:

- current SportyBet event discovery evidence;
- PR #246 event-detail confirmation evidence;
- exact source-replayed SportyBet-to-FotMob fixture reconciliation.

It cannot issue:

- provider event timestamps or snapshot identities that the source did not provide;
- canonical market mappings;
- bookmaker value or Price-all outputs;
- Router decisions;
- portfolio decisions;
- final selections;
- booking/slip instructions;
- SportyBet execution;
- stakes;
- wagers.

`wager_placed` is always `false`.

## Next reviewed boundary

`CURRENT_DIRECT_PROVIDER_CANONICAL_MARKET_MAPPING_REBIND_REQUIRED`

The existing reviewed canonical market mapping is event-specific. Discovering a fresh provider event ID does not authorize copying a mapping object from a different event. The next boundary must bind canonical market semantics to the newly reconciled current provider event before the direct-provider Price-all/Router/portfolio chain can operate autonomously on it.
