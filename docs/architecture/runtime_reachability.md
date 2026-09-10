# ATHENA Runtime Reachability Evidence (P0.5)

## Purpose

P0.5 adds deterministic runtime evidence to the static repository inventory from
P0.2.  The purpose is to answer a narrower question than static import analysis:
which reviewed supported command surfaces actually execute decision-bearing
functions, and which imported or support modules do not become decision
authority during the reviewed synthetic probe.

This is evidence and observability only.  It does not migrate callers, promote a
canonical owner, change Main/Shadow authority, alter football or pricing
semantics, or authorize cleanup.

**Trace policy:** `ATHENA_RUNTIME_REACHABILITY_V1`  
**Schema version:** `1`  
**P0.5 subject commit:** `b428dbd00380dd71456640d77b26ac79fe945c5f`
(the exact pre-P0.5 `main` after the reviewed fresh-holdout `shortName`
continuity repair).

P0.5 changes no business-path module.  The committed evidence therefore targets
that frozen pre-P0.5 runtime subject while the audit harness supplies scoped
instrumentation around the unchanged functions.

## Evidence semantics

A static import and an executed function are different facts.  P0.5 uses an
ordered scoped trace with the following checkpoint classes:

- `ENTRYPOINT`
- `ORCHESTRATION`
- `SUPPORTING_LOGIC`
- `DECISION_AUTHORITY`
- `DELIVERY`
- `TERMINUS`

Decision authority is further typed as model analysis, legacy market selection,
accumulator filtering/construction, Price-all, market routing, or Portfolio
construction.  Delivery is explicitly separate.

The tracer wraps an existing callable, calls the exact original callable, keeps
its return value/exception unchanged, records the checkpoint, and restores the
original callable in `finally`.  Importing a module produces no checkpoint.
Supporting logic is not automatically promoted to `DECISION_AUTHORITY`.

Trace output contains no wall-clock timestamp, machine path, random UUID, or
network-derived observation.

## Synthetic-only methodology

The audit is deliberately hostile to accidental external activity.

- Main-facing `build_acca` receives a deterministic analyzed fixture at the
  analysis-output seam so the existing accumulator filtering and construction
  functions can execute without FotMob/OpenFootball/database acquisition.
- `PredictionService.predict` is separately exercised with a deterministic
  analyzer seed and the actual `ProbabilityEngine`, `RiskEngine`,
  `ReliabilityEngine`, and `MarketSelector` implementations.
- Current Shadow executes the real request wrapper and real daily wrapper, then
  crosses a bounded synthetic worker seam.  The real current Shadow Price-all,
  Router and Portfolio algorithms execute.  Only deep source-replay/verifier and
  external acquisition boundaries are replaced with deterministic synthetic
  evidence.  The real share-code create/reload function is not called.
- Protected fresh-holdout collection is exercised only through a fail-closed
  invalid-bootstrap invocation with `--execute-live-network` absent; collection
  cannot begin.
- Fresh-holdout receipt mirroring executes its entrypoint while the downstream
  GitHub transport main is replaced before any remote read.
- Current Shadow history-prime restore uses a deterministic local transport
  artifact and performs no provider access.
- Email delivery uses a deterministic no-code receipt with all SMTP credentials
  removed and an SMTP guard that fails if contacted.  The expected result is
  `EMAIL_SKIPPED_UNCONFIGURED`.

No live FotMob/SportyBet acquisition, Current Shadow workflow trigger,
fresh-holdout live trigger, real SportyBet create/reload, login, cookies, wallet,
stake, wager, or SMTP send is permitted by the audit.

## P0.2 supported-root coverage

The audit reads the exact supported-root registry from the committed P0.2 JSON
artifact and fails if that reviewed set drifts.  The current expected coverage is:

| Supported root | P0.3 profile | P0.5 runtime disposition | Market-decision result |
| --- | --- | --- | --- |
| `build_acca` | `MAIN_ONLY` | `EXECUTED_DECISION_AUTHORITY` | Accumulator filter/construction executes; `PredictionService.predict` and `MarketSelector.select` do not execute in this root probe. |
| `scripts.execute_current_shadow_request` | `SHADOW_ONLY` | `EXECUTED_DECISION_AUTHORITY` | Transitional current Shadow Price-all, Router, and Portfolio owners execute. |
| `scripts.restore_current_shadow_history_prime_artifact` | `SHADOW_ONLY` | `NO_DECISION_AUTHORITY_REACHED` | Transport-cache validation/restore only. |
| `scripts.run_fotmob_fresh_holdout_release_receipt_mirror` | `UNKNOWN` / protected research | `NO_DECISION_AUTHORITY_REACHED` | Receipt transport entrypoint only; no GitHub transport executed in the synthetic probe. |
| `scripts.run_fotmob_utc_native_xg_fresh_holdout_tick` | `UNKNOWN` / protected research | `NO_DECISION_AUTHORITY_REACHED` | Fails closed before collection because the exact bootstrap is intentionally absent and live-network permission is not supplied. |
| `scripts.send_current_shadow_email` | `SHADOW_ONLY` | `EXECUTED_DELIVERY_ONLY` | Delivery-only path; SMTP is intentionally unconfigured and guarded. |

## Main-facing `build_acca` trace

The deterministic downstream-selection probe executes this ordered decision
path:

```text
build_acca.AccaBuilder.build
  -> intelligence.acca_filter.AccaFilter.filter_and_rank_legs
  -> intelligence.acca_filter.AccaFilter.build_filtered_acca
  -> intelligence.accumulator.AccumulatorEngine.generate_accumulator
  -> terminus
```

`services.prediction_service.PredictionService.predict` and
`engine.market_selector.MarketSelector.select` are wrapped as measurement
checkpoints during the same root execution.  Their absence from the trace is the
runtime fact: they did not execute in the reviewed `build_acca` synthetic root
probe.

The synthetic analyzed result is injected *after* analysis specifically to avoid
provider/database activity and to make the accumulator decision boundary
executable.  This does not claim that an unquarantined legacy analyzer result has
runtime BET authority; existing `AnalysisPipeline.apply_runtime_authorization`
remains unchanged.

## Supplemental legacy `PredictionService` trace

`PredictionService` remains a P0.3 legacy-reachability-review component.  P0.5
therefore exercises it separately rather than pretending it is reachable from
`build_acca`.

```text
services.prediction_service.PredictionService.predict
  -> engine.probability_engine.ProbabilityEngine.calculate
  -> engine.risk_engine.RiskEngine.evaluate
  -> engine.reliability_engine.ReliabilityEngine.evaluate
  -> engine.market_selector.MarketSelector.select
```

The final call is classified as `LEGACY_MARKET_SELECTION` decision authority
*inside this legacy service path*.  That is not a canonical-ownership or
production-authority assignment.

## Current Shadow trace

The Current Shadow probe executes the real supported request wrapper and real
daily wrapper, while replacing the external worker boundary with a deterministic
synthetic evidence worker.  Inside that seam the actual decision owners execute:

```text
scripts.execute_current_shadow_request._execute_worker
  -> scripts.execute_current_shadow_daily._execute_worker
  -> domain.current_shadow_all_market_price_all.price_all_shadow_fixture
  -> domain.current_shadow_all_market_router.route_shadow_price_results
  -> domain.current_shadow_all_market_portfolio.optimize_shadow_portfolio
  -> TERMINUS before domain.current_shadow_all_market_share_code.create_verified_shadow_all_market_share_code
```

This proves the currently executed decision ownership is the transitional
`domain.current_shadow_all_market_*` family for this reviewed synthetic path.  It
does **not** promote `price_all_v3_current_provider`,
`market_router_v3_current_provider`, or `portfolio_optimizer_v3_current_provider`.
Those P0.3 promotion candidates remain unproven until later reviewed migration
work.

The share-code function is deliberately represented as a non-executed terminus.
P0.5 does not create or reload a real SportyBet code.

## Reproducible legacy MarketSelector problem cases

`tests/fixtures/architecture/legacy_market_selection_cases_v1.json` freezes five
current behaviors for later migration review:

| Case ID | Current observed behavior |
| --- | --- |
| `LEGACY_SELECTOR_NO_QUOTE_RECOMMENDATION` | Recommends `Both Teams To Score` at `84.0` with no bookmaker quote/value input. |
| `LEGACY_SELECTOR_QUOTE_INDEPENDENT_OUTPUT` | Quote-like/provider-like attributes do not participate in `MarketSelector.select`; the same heuristic recommendation remains. |
| `LEGACY_SELECTOR_NO_PROVIDER_FAIL_CLOSED_DISPOSITION` | Recommends `Under 2.5` at `77.0` without a provider-unavailable/unpriced disposition. |
| `LEGACY_SELECTOR_NONCANONICAL_OVER15_COMBO` | Can recommend the ad-hoc `Home or Over 1.5` label (`88.0`), which is not a reviewed current canonical `MarketId`. |
| `LEGACY_SELECTOR_CONSTRUCTION_ORDER_TIE` | Equal-score `Home or Draw` / `Home or Away` rows retain legacy append/stable-sort order. |

The current outputs are asserted as evidence.  Separate strict `xfail` tests
state the not-yet-satisfied future properties.  An unexpected `XPASS` is a
review signal, not permission to silently rewrite the evidence.

## Determinism

`canonical_json_bytes(...)` uses sorted keys, rejects NaN/Infinity, and embeds
no timestamps generated by the tracer.  Repeated synthetic executions are
required to produce byte-identical runtime evidence.

The CLI is:

```bash
git pull --ff-only && PYTHONPATH=. python -m scripts.audit_runtime_reachability \
  --ref b428dbd00380dd71456640d77b26ac79fe945c5f \
  --output artifacts/architecture/runtime-reachability-v1.json
```

A review should regenerate twice into temporary files and compare SHA-256 before
accepting the committed artifact.

## Relationship to P0.2 / P0.3 / P0.4

- **P0.2** supplies deterministic modules, static edges, workflow references and
  the exact supported-root registry.
- **P0.3** supplies the normative Main/Shadow authority/parity assignments.
- **P0.4** enforces architecture boundaries in CI.
- **P0.5** adds runtime execution evidence without changing those assignments.

Together P0.2 + P0.4 + a reviewed P0.5 provide the evidence required to evaluate
Checkpoint A.  P0.5 does not change Checkpoint B0, which was already established.

## Cleanup limitation

**NO MODULE RECEIVES DELETE AUTHORITY FROM P0.5 ALONE.**

P0.2 static evidence plus P0.5 runtime evidence are inputs to later migration
and cleanup review.  Neither automatically assigns `KEEP`,
`MIGRATE_THEN_DELETE`, `ARCHIVE_OR_RETIRE`, or `DELETE`.

All reviewed cleanup dispositions remain `UNCLASSIFIED` in this wave.  Active
prospective research and historical evidence remain protected even when they do
not participate in a market-decision trace.
