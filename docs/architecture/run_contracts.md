# Canonical RunRequest and RunReceipt

P1.1 establishes ATHENA's stable, unversioned orchestration data boundary before any CLI, workflow, model, pricing, Router, Portfolio, or delivery migration. The canonical implementation is `domain.run_contracts`; the Current Shadow compatibility boundary is `domain.current_shadow_run_contract_adapter`.

This PR implements the P1.1 contract only. It does **not** introduce `AthenaRunService`, change Current Shadow execution, change `build_acca`, parse weekday/relative-day shorthand, promote a pricing/router/portfolio implementation, perform provider acquisition, create a real SportyBet share code, or place a wager.

## RunRequest

`RunRequest` is immutable and contains only resolved orchestration intent:

- `dates`: one through seven unique concrete `datetime.date` values. Canonical serialization uses sorted `YYYY-MM-DD` values. Relative terms such as `today`, `tomorrow`, and weekday names must be resolved before this boundary. The user-facing parser remains a later P4.1 responsibility.
- `target_legs`: an exact integer from 1 through 50. It is a maximum desired construction target, not a quota.
- `target_total_odds`: an optional, independent decimal portfolio objective. It is never inferred from `target_legs`; canonical serialization preserves it as exact decimal text.
- `bookie`: delivery-adapter identity. P1.1's Current Shadow adapter maps the reviewed delivery target to `sportybet`.
- `mode` and `authority_profile`: explicit orchestration/authority identity. P1.1 recognizes the frozen `MAIN` / `SHADOW` execution-profile vocabulary.
- `create_share_code`: explicit delivery intent.
- `place_wager`: must remain `false` throughout this remediation programme.

A request serializes canonically with sorted object keys, compact JSON, UTF-8, and one trailing LF. Duplicate object keys, NaN/infinity, extra/missing contract fields, noncanonical dates, and ambiguous or unsupported values fail closed.

## AuthorityManifest

`AuthorityManifest` makes the run's side-effect boundary explicit. The canonical capability vocabulary includes:

- provider acquisition;
- share-code generation;
- login;
- cookies;
- wallet;
- staking;
- wager.

P1.1 grants no wager authority. `SHADOW` additionally cannot grant login, cookies, wallet, staking, or wager capability. Compatibility-only boolean capabilities can be preserved in `additional_capabilities` without turning them into canonical production authority.

## RunReceipt

`RunReceipt` is immutable and binds a terminal result to its exact `RunRequest`. It contains:

- status and exact executed commit SHA;
- canonical resolved request;
- zero or more proven `RunStage` checkpoints;
- non-negative funnel/count fields, including `selected_leg_count`;
- the concrete selected-leg records;
- truthful `shortfall`;
- optional share-code result/verification evidence;
- the authority/profile manifest;
- preserved source/compatibility evidence;
- `wager_placed=false`.

The contract enforces:

```text
shortfall = target_legs - selected_leg_count
selected_leg_count = number of concrete selected-leg records
```

ATHENA therefore cannot satisfy a requested target by inventing filler legs. If `target_legs=25` and only fourteen concrete legs survive, the canonical receipt contains fourteen selected legs and `shortfall=11`.

Canonical receipts use the same deterministic JSON rules as requests and support byte-exact round-trip validation.

## Current Shadow compatibility

`domain.current_shadow_run_contract_adapter` is intentionally a **one-way** dependency:

```text
Current Shadow legacy request/receipt
              |
              v
current_shadow_run_contract_adapter
              |
              v
domain.run_contracts
```

The canonical module never imports Current Shadow.

The adapter maps `requested_target_size` to canonical `target_legs`, explicit legacy `YYYYMMDD` fixture dates to concrete dates, the current receipt funnel/counts to canonical counts, concrete legacy selected-leg records to canonical selected legs, and the current research-only authority map to `AuthorityManifest`.

A legacy `fixture_scope` such as `today` or `three-day` is **not** a concrete date. If an older request policy has `fixture_dates=null`, the adapter requires the caller to provide the already-resolved concrete dates. It never guesses dates from a scope string.

The current runner stores a latest stage checkpoint and a latest progress checkpoint, not a complete historical stage list. The adapter therefore converts only checkpoints actually supplied to it and records `legacy_stage_history_complete=false`. It does not reconstruct missing stages. The full legacy request policy, terminal receipt, and optional latest stage/progress payloads are preserved under `evidence.legacy_current_shadow` so compatibility does not discard existing evidence.

If a legacy receipt reports positive `selected_leg_count` but contains no concrete selected-leg records, adaptation fails closed. Likewise, a share-code string without its verification receipt is never promoted into a canonical verified delivery result.

## P1.1 safety and ownership boundary

P1.1 changes interface ownership only. It does not change football probabilities, provider odds, de-vig/settlement mathematics, Router selection, Portfolio constraints, Current Shadow source acquisition, share-code transport, or legacy Main behavior. It gives no `KEEP`, `MIGRATE_THEN_DELETE`, `ARCHIVE_OR_RETIRE`, or `DELETE` authority to any existing implementation.

The P0.3 parity contract continues to describe request/date semantics and run-receipt/observability as exact shared responsibilities whose runtime migration is still pending. P1.1 establishes the stable interface those later migrations can target; it does not claim the callers have already migrated.

## Verification

Focused offline validation requires no provider access:

```bash
git pull --ff-only && PYTHONPATH=. python -m pytest tests/test_run_contracts.py tests/test_current_shadow_run_contract_adapter.py -q
```

The existing Current Shadow backward-compatibility tests remain part of the hosted full suite. No live Current Shadow workflow or provider acquisition is required for P1.1 acceptance.

## Next programme gate

P1.1 is the fifth merged remediation PR in the current source-review cycle **only after it merges**. Until then the counter remains `4/5`. After P1.1 merges, the controlling architecture sources and relevant live contracts must be reread before P1.2 is drafted or opened.
