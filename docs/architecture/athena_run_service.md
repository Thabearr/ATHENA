# AthenaRunService

`AthenaRunService` is the canonical orchestration boundary beneath the CLI. It accepts the existing exact `domain.run_contracts.RunRequest` and returns the existing exact `RunReceipt`; it does not define duplicate request/result types or calculate football, probability, pricing, routing, portfolio, Kelly, or stake formulas.

## Request and authority

The service resolves the executor from a source-controlled `(authority_profile, mode, bookie)` mapping. The matching `AuthorityManifest` is fixed by that mapping and binds provider-acquisition and share-code permissions. Login, cookies, wallet, staking, and wager remain false in both profiles; `RunRequest.place_wager` and `RunReceipt.wager_placed` are false.

MAIN (`MAIN` / `main_application` / `sportybet`) uses the existing fixed target-only request boundary. It presently terminates at the reviewed Phase 6 authority hold. It has no provider or share-code authority, selects no legs, and records full truthful shortfall. Request dates remain bound as user intent and are not represented as analyzed fixtures.

SHADOW (`SHADOW` / `research_shadow` / `sportybet`) is bound to the existing Current Shadow supervisor/worker and one-way `current_shadow_run_contract_adapter`. It does not duplicate source acquisition, date policy, reconciliation, canonical calculations, timeout, or share-code verification. The existing `scripts.execute_current_shadow_request` supervisor exclusively owns the reviewed 75-minute timeout and its timeout-receipt finalization. AthenaRunService deliberately applies no competing outer timeout, so the supervisor can persist its terminal receipt and last completed progress before returning; the service then adapts that evidence without inventing selected legs or a share-code result. Before invoking that boundary, the service checks that the exact requested Lagos calendar dates are representable by the existing UTC rolling window. It never shifts dates; a mismatch returns `SHADOW_DATE_POLICY_UNREPRESENTABLE` before provider work.

## Persistence and idempotency

Each canonical request has a deterministic directory under the supplied output root, named by `RunRequest.canonical_sha256`. The exact canonical request bytes are atomically persisted before the executor can perform side effects. The terminal canonical receipt is atomically persisted beside it and binds the exact request, `AuthorityManifest`, current Git commit SHA, truthful selected-leg count/shortfall, stage evidence, and `wager_placed=false`.

Repeating the same request at the same exact commit returns the validated persisted receipt without rerunning the executor. Malformed, contradictory, or cross-commit evidence fails closed and is never overwritten. A non-null `target_total_odds` currently receives a durable `TARGET_TOTAL_ODDS_NOT_SUPPORTED` receipt before an executor is invoked; it is not inferred from `target_legs`.

## CLI and validation boundary

`build_acca.py` parses `athena run` and the documented shorthand into the same `RunRequest`, displays the resolved dates and permission manifest before execution, then delegates to `AthenaRunService` and renders the returned receipt. Relative days are resolved with `ZoneInfo("Africa/Lagos")` across the local today-through-six-day horizon. Offline tests inject only synthetic executors; they do not invoke the real SHADOW supervisor or any provider.

P4.1 does not add or adopt a GitHub Actions workflow. Workflow convergence remains P4.2 work.
