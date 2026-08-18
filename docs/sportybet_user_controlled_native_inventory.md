# SportyBet user-controlled provider-native inventory

## Purpose

PR #152 froze the reviewed SportyBet Lite provider-native parser and PR #153 created an offline, user-controlled evidence lane. This boundary joins those two reviewed pieces without authorizing automated SportyBet access.

A user may manually save a reviewed SportyBet Lite page, import it through the PR #153 evidence command, then derive an exact provider-native inventory containing the SportyBet market IDs, outcome IDs, line/specifier identity and decimal odds actually present in those preserved HTML bytes.

This is the first boundary that makes preserved user-controlled SportyBet odds machine-readable inside ATHENA. It is still evidence only.

## Trust chain

The exact flow is:

`manual browser observation -> PR #153 preserved HTML + manifest -> exact evidence verification -> PR #152 provider-native parser -> canonical derived inventory`

The source HTML is re-read and re-hashed after the evidence directory is verified. Any evidence tampering fails closed before parsing.

For event-detail evidence, ATHENA additionally requires the provider-native selection population in the saved HTML to agree with the exact event ID and sport ID in the attested source URL. A non-null selection market group must agree with the reviewed `marketGroupsName=Main` request. This prevents a validly stored page from being silently interpreted as a different SportyBet event.

## What is preserved

The derived inventory preserves the reviewed PR #152 native selection semantics, including:

- `event_id`;
- `sport_id` when supplied by the provider link;
- `product_id` when supplied;
- `market_id`;
- `market_group` when supplied;
- provider market label when explicitly present in HTML attributes;
- exact `specifier`/line identity;
- `outcome_id`;
- provider selection label when present;
- exact raw decimal odds string;
- lossless normalized decimal interpretation;
- explicit availability state (`AVAILABLE`, `SUSPENDED`, or `UNKNOWN`);
- exact selection href.

Distinct specifiers under one market ID remain distinct. For example, Total Goals 2.5 and Total Goals 3.5 cannot collapse into one market identity.

Unknown provider markets are not mapped to ATHENA canonical markets in this boundary.

## Time and price semantics

The inventory retains all three relevant concepts separately:

1. `observed_at_user_attested` — the time the user says they observed/exported the page;
2. `imported_at_utc` — the later ATHENA import time;
3. `provider_quote_at` — still `null` because a provider-native quote timestamp has not been proven on the reviewed Lite HTML.

`provider_snapshot_id` also remains `null`.

Therefore the odds are real preserved SportyBet page evidence, but the user-attested observation time is **not** promoted to provider fresh-price authority. This inventory cannot by itself authorize value, selection, or `BET`.

## Derived evidence durability

Canonical inventories are stored only under:

`.cache/athena-research/sportybet-user-controlled-native-inventory`

Each source evidence ID gets exactly one `inventory.json`. The directory name is the PR #153 evidence ID, so the derived inventory is bound back to the exact preserved source evidence. Exact replay is idempotent; stale, altered, noncanonical, extra-file, symlink, traversal, or conflicting output fails closed.

The canonical inventory also records:

- source evidence ID;
- source evidence manifest SHA-256;
- source raw HTML SHA-256;
- exact source URL/request identity;
- manual acquisition mode;
- observation authority;
- user-observed/import timestamps;
- provider timestamp/snapshot capability status;
- all downstream authority flags as false.

## Command

After a PR #153 evidence directory exists:

```text
python -m scripts.build_sportybet_user_controlled_native_inventory \
  --evidence-directory .cache/athena-research/sportybet-user-controlled-evidence/<evidence-id>
```

The command emits a deterministic receipt with the inventory hash and counts for events, market identities and selections. It performs no SportyBet network I/O.

## Product boundary

This does **not** yet perform:

- SportyBet event <-> trusted FotMob fixture reconciliation;
- canonical ATHENA market mapping;
- provider-native quote freshness proof;
- model integration;
- value calculation;
- recommendation/selection authority;
- ACCA/slip construction;
- SportyBet booking-code generation;
- SportyBet execution;
- `BET`.

The odds preserved here are an input to those later trust gates, not permission to skip them.

## Next boundary

Once real user-controlled SportyBet evidence has been preserved and inventoried, the next reviewed boundary can reconcile the exact provider-native SportyBet event identity against ATHENA's trusted FotMob fixture identity. That reconciliation must fail closed rather than use fuzzy names or silently reverse home/away participants.
