# Current direct-provider live quote mapping consumption

## Boundary

PR #253 implements the boundary declared by merged PR #252:

`CURRENT_DIRECT_PROVIDER_LIVE_QUOTE_MAPPING_CONSUMPTION_REQUIRED`

PR #252 proves exact current-event canonical semantics but intentionally emits no odds. PR #253 reconnects those semantics to the exact retained PR #246 direct event-detail evidence and may emit a bookmaker quote only when the exact current provider row is still present, bookable, and settlement-equivalent.

This is a quote-evidence boundary only. It does not compute value or make a betting decision.

## Exact source chain

Every output starts from an exact `CurrentDirectProviderCanonicalMarketMappingRebind`.

The source is verified through the PR #252 retained-source reconstruction path. PR #252 in turn replays the current SportyBet/FotMob reconciliation and the legacy reviewed canonical mapping ancestry.

PR #253 then replays the direct event-detail evidence retained by that PR #252 source through `sportybet_live_event_quote_evidence.build_live_event_quote_inventory(...)`.

The replayed inventory must exactly match the PR #252 event ID, fixture teams, kickoff UTC, response-completion observation time, inventory SHA-256, manifest SHA-256, and raw response SHA-256.

## Quote identity

A PR #252 mapped row is joined to the current PR #246 inventory only by the exact provider-native tuple:

- market ID;
- specifier, including exact `None`;
- outcome ID.

The provider market label, outcome label, current bookability flag, and bookability evidence basis must also remain exactly equal to the PR #252 row.

Any mismatch fails closed. There is no fuzzy matching, aliasing, label repair, line generalization, or nearest-market substitution.

## Price authority

The only odds emitted by PR #253 are the odds in the replayed current PR #246 direct-provider inventory.

Legacy mapping odds are never copied.

Each emitted quote retains:

- current event and fixture identity;
- exact provider market/specifier/outcome identity and labels;
- canonical market/outcome/line identity;
- PR #246 raw, manifest, and inventory SHA-256 ancestry;
- PR #252 mapping-rebind SHA-256 and contract identity;
- PR #251 current reconciliation SHA-256;
- legacy reviewed mapping SHA-256;
- exact source mapping-row SHA-256;
- ATHENA response-completion observation time;
- explicit null provider quote timestamp and snapshot identity.

`provider_quote_at` and `provider_snapshot_id` remain `null` because SportyBet does not provide reviewed provider-native identities for them in this source.

## Availability and settlement

An exact mapped row may exist without being usable as a quote.

`CURRENTLY_UNAVAILABLE` is emitted when the exact current provider selection is present but not currently bookable.

`SETTLEMENT_EQUIVALENCE_UNPROVEN` is emitted when the PR #252 row lacks reviewed bookmaker settlement equivalence. This preserves the fail-closed rule for unproven 1UP/2UP promotional settlement semantics.

Only exact mapped rows that are both currently bookable and bookmaker-equivalent receive `QUOTED`.

No missing or rejected row is substituted.

## Freshness

PR #253 rechecks freshness at its own issuance time.

- quote issuance may not predate PR #252 mapping issuance;
- discovery evidence age must remain at most 900 seconds;
- direct event-detail response-completion age must remain at most 900 seconds;
- kickoff lead must remain strictly greater than 120 seconds.

This prevents a mapping that was valid earlier from becoming a permanently reusable price source.

The deterministic `..._as_of(...)` issuer never claims wall-clock currentness.

The live issuer requires a PR #252 `LIVE_CURRENT` source, obtains UTC now internally, and independently rechecks age and kickoff lead before setting only `wall_clock_currentness_at_issuance=true`.

## Authority

PR #253 may authorize current mapped SportyBet quote evidence.

It does not authorize:

- Price-all/value computation;
- Market Router decisions;
- Portfolio Optimizer decisions;
- final selection;
- accumulator/slip construction;
- SportyBet execution;
- staking;
- BET.

A valid zero-quote output is allowed when no exact current mapped row is both bookable and settlement-equivalent.

`wager_placed=false` remains explicit.

## Frozen identities

- PR #252 current mapping contract:
  `de022fd931313fa8d3c2c093ff0cb9b12f2c0f1ba0d9adc4b646c94dfd306e96`
- PR #246 direct event evidence contract:
  `b888cebab6447cd4072d823dab67b56f1f75f72eb72d67b692d47a4378b27555`
- PR #253 contract:
  `671e6016093bc3f30141ddd13ab259bebb70086945fb30a588a185703fd128d4`

## Reconstruction

Mapped quote objects and the top-level bundle are builder-only.

The public verifier replays the retained PR #252 source, replays the exact retained PR #246 direct event evidence, recomputes freshness, reconstructs quote/audit rows, and requires byte-equivalent canonical output.

Public-field mutation therefore cannot mint quote authority.

## Next boundary

`PRICE_ALL_V3_CURRENT_DIRECT_PROVIDER_QUOTE_CONSUMPTION_REQUIRED`

That boundary must consume this new exact current quote source explicitly. The frozen Price-all v2 contract remains unchanged and bound to the earlier PR #247 adapter ancestry.
