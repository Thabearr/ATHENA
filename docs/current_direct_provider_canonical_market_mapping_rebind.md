# Current direct-provider canonical market mapping rebind

## Boundary

This boundary implements the post-PR #251 requirement:

`CURRENT_DIRECT_PROVIDER_CANONICAL_MARKET_MAPPING_REBIND_REQUIRED`

PR #251 can discover a current SportyBet football event, replay the reviewed FotMob fixture source, confirm the exact current provider event through the PR #246 direct event-detail source, and issue exact fixture-reconciliation authority. It deliberately does not authorize canonical market mapping.

The pre-existing SportyBet canonical mapping is also deliberately event-specific. Its reviewed native identity includes the SportyBet event ID, provider market ID, provider specifier, and provider outcome ID. A new current event ID therefore cannot receive canonical semantics by copying an old mapping object.

PR #252 adds a separate additive rebind boundary. It source-replays both sides before allowing any current canonical mapping:

1. the exact PR #251 current event reconciliation bundle is reconstructed from its retained SportyBet discovery/direct-detail evidence and raw reviewed FotMob ancestry;
2. the legacy `SportyBetReviewedCanonicalMarketMapping` is rebuilt through its public source-aware builder from the exact reviewed reconciliation receipt, native inventory, and explicit review decisions;
3. only exact provider semantic identities present on the current event may be rebound.

No existing Price-all, Router, Portfolio Optimizer, legacy canonical mapping, PR #246 direct-event source, or PR #251 current-event file is modified.

## Exact semantic rebind rule

The old event ID is provenance, not a reusable current event identity. Event ID is the only native identity component allowed to differ.

A current provider selection is eligible only when all of these fields are exactly equal to one reviewed source mapping row:

- provider market ID;
- provider specifier, including exact absence when `None`;
- provider outcome ID;
- provider market name;
- provider outcome/selection label.

There is no aliasing, case folding, fuzzy matching, synonym table, outcome guessing, team reversal, or label repair.

A provider-native identity with changed human-readable labels is explicitly audited as `CURRENT_PROVIDER_LABEL_DRIFT_REJECTED` and receives no mapping. A reviewed template absent from the current event is audited as `SOURCE_TEMPLATE_ABSENT_FROM_CURRENT_EVENT`. A current provider selection with no reviewed event-independent native template remains unreviewed and is counted; it is never assigned the nearest canonical market.

## Line markets do not generalize

The reviewed legacy contract only authorizes exact selections. PR #252 therefore does not generalize line semantics across values.

For example, a reviewed `TOTAL_GOALS` mapping at provider specifier `total=2.5` can rebind only `total=2.5`. It does not authorize `total=1.5`, `total=3.5`, or another total. The same rule applies to Asian Handicap `hcp=<line>` identities.

This deliberately leaves coverage short when the current event exposes unreviewed line values. Missing coverage is safer than silently converting an exact reviewed selection into a provider-wide mapping rule.

## Settlement authority is preserved, never upgraded

A rebound row carries the exact settlement-equivalence authority of its reviewed source row.

Standard reviewed settlement equivalence remains standard reviewed settlement equivalence. Early-payout 1UP/2UP rows whose provider promotion rules remain unproven stay `PROVIDER_PROMOTION_RULES_UNPROVEN` and keep `bookmaker_equivalence_authorized=false`. An exact reviewed early-payout settlement receipt may be supplied only through the legacy mapping rebuild path; PR #252 does not synthesize or upgrade that evidence.

## No odds are copied

Canonical semantic rebind and current price evidence remain separate trust boundaries.

The PR #252 mapped-selection output intentionally contains no `odds_raw`, no decimal odds, no provider quote timestamp, and no provider snapshot ID. The old reviewed mapping's historical/native odds are not copied. The current event-detail inventory is used only to prove that the exact provider semantic identity exists on the current event and to preserve its current bookability observation.

A currently unavailable provider selection can still prove semantic identity and therefore can receive canonical mapping. It cannot receive fresh-price authority. Availability and pricing are evaluated later from current direct-provider evidence.

## Currentness is rechecked again

PR #252 does not treat a successfully issued PR #251 bundle as current forever.

At mapping-rebind evaluation time:

- evaluation may not predate PR #251 issuance;
- current discovery evidence must be no older than 900 seconds;
- current direct event-detail evidence must be no older than 900 seconds;
- kickoff lead must remain strictly greater than 120 seconds;
- the rebuilt current event inventory must still match the exact manifest, raw SHA-256, inventory SHA-256, observation time, event ID, teams, and kickoff retained by PR #251.

`rebind_current_direct_provider_canonical_mapping_as_of(...)` is deterministic replay and does not claim wall-clock currentness. `rebind_current_direct_provider_canonical_mapping(...)` obtains ATHENA's current UTC time internally and marks only the mapping rebind's wall-clock-currentness proof. Neither function grants fresh-price authority.

## Coverage and explicit outcomes

The bundle reports:

- exact mapped selections;
- one audit for every reviewed source template;
- the number of current provider selections that have no reviewed template;
- represented and unrepresented ATHENA target markets;
- whether every source template was rebound;
- whether all 15 ATHENA target markets are represented.

The bundle disposition is `REBOUND_EXACT_REVIEWED_SEMANTICS` when at least one exact row survives. If none survives it is `NO_EXACT_REVIEWED_SEMANTICS`; this is a valid fail-closed result, not a reason to invent mappings.

## Frozen identities

- PR #251 current event discovery/reconciliation contract: `64c7a2b71304f94a39de7e608be1f76a10e14a1a52a338f89d1c695ba0e5f1ee`;
- legacy mapping dataset: `athena-sportybet-reviewed-canonical-market-mapping-v1`;
- legacy mapping status: `REVIEWED_PROVIDER_NATIVE_CANONICAL_MARKET_MAPPING`;
- legacy review basis: `EXPLICIT_REVIEW_OF_EXACT_PROVIDER_NATIVE_IDENTITY_AND_LABELS`;
- PR #252 contract: `de022fd931313fa8d3c2c093ff0cb9b12f2c0f1ba0d9adc4b646c94dfd306e96`.

The contract also pins the exact 15-market ATHENA registry inherited from the reviewed legacy mapping boundary.

## Authority

PR #252 may authorize only exact current-event canonical market semantics after both source chains verify.

It does **not** authorize:

- fresh price;
- Price-all/value computation;
- Market Router decisions;
- Portfolio Optimizer decisions;
- final selection;
- accumulator/slip construction;
- SportyBet execution;
- staking;
- BET.

`provider_quote_at=null`, `provider_snapshot_id=null`, and `wager_placed=false` remain explicit at the bundle boundary.

## Reconstruction and tamper resistance

Both mapped selections and the top-level rebind bundle are builder-only. The public verifier reconstructs the PR #251 bundle from retained current evidence, rebuilds the legacy reviewed mapping from its original reviewed source path, rebuilds the current direct event-detail inventory, reruns freshness and exact semantic matching, and requires exact deterministic output equality.

Mutation of a public output field cannot mint authority because verification reconstructs from retained sources rather than trusting the edited object.

## Next boundary

`CURRENT_DIRECT_PROVIDER_LIVE_QUOTE_MAPPING_CONSUMPTION_REQUIRED`

The next boundary may use these exact current-event canonical semantics to issue current mapped quote evidence. It must still consume the PR #246 current direct-provider quote source, enforce availability/freshness, preserve missing/unavailable rows, and must not reinterpret this mapping boundary as price, Router, portfolio, execution, staking, or BET authority.
