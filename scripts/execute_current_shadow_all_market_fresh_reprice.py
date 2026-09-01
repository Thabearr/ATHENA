#!/usr/bin/env python3
"""PR-F worker: fresh reprice exact Router-selected legs before Portfolio."""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from types import MappingProxyType
from typing import Any

from domain import _current_shadow_quote_binding as quote_binding
from domain import current_shadow_all_market_portfolio as portfolio_module
from domain import current_shadow_sportybet_catalog_fanout_reconciliation as catalog_reconciliation
from domain import current_shadow_sportybet_upcoming_reconciliation as upcoming_reconciliation
from domain import current_sportybet_semantic_registry as prb
from domain import sportybet_current_event_discovery_reconciliation as pr251_reconciliation
from domain import sportybet_live_event_quote_evidence as live
from domain._current_shadow_price_core import (
    ShadowPriceError,
    ShadowRouterDecisionStatus,
)
from scripts import execute_current_shadow_all_market as cli
from scripts import execute_current_shadow_all_market_summary_reuse as summary_cli


WORKER_MODULE = "scripts.execute_current_shadow_all_market_fresh_reprice"
FRESH_REPRICE_MODE = "PRF_CURRENT_RECONCILIATION_FRESH_REPRICE"
FRESH_REPRICE_POLICY_ID = (
    "PRF_RETAINED_EXACT_RECONCILIATION_PLUS_FRESH_DIRECT_EVENT_REPRICE_V1"
)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _reconciliation_verifier_and_basis(bundle):
    if type(bundle) is pr251_reconciliation.SportyBetCurrentEventDiscoveryReconciliationBundle:
        return (
            pr251_reconciliation.verify_current_event_discovery_reconciliation_bundle,
            pr251_reconciliation.SportyBetCurrentEventDiscoveryError,
            "PR251_UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILIATION",
        )
    if type(bundle) is upcoming_reconciliation.CurrentShadowSportyBetUpcomingReconciliationBundle:
        return (
            upcoming_reconciliation.verify_current_event_discovery_reconciliation_bundle,
            upcoming_reconciliation.CurrentShadowSportyBetUpcomingReconciliationError,
            "PRF_PR258_UPCOMING_UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILIATION",
        )
    if type(bundle) is catalog_reconciliation.CurrentShadowSportyBetCatalogFanoutReconciliationBundle:
        return (
            catalog_reconciliation.verify_current_event_discovery_reconciliation_bundle,
            catalog_reconciliation.CurrentShadowSportyBetCatalogFanoutReconciliationError,
            "PRF_PROVIDER_CATALOG_FANOUT_UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILIATION",
        )
    raise ShadowPriceError("fresh reprice requires an exact reviewed current reconciliation bundle")


def _reconciliation_row(bundle, *, provider_event_id: str, fixture_identity: str):
    verifier, reconciliation_error, basis = _reconciliation_verifier_and_basis(bundle)
    try:
        reconciled = verifier(bundle)
    except reconciliation_error as exc:
        raise ShadowPriceError("fresh reprice current reconciliation replay failed") from exc
    rows = [row for row in reconciled.rows if row.event_id == provider_event_id]
    if len(rows) != 1 or rows[0].fixture_reconciliation_authorized is not True:
        raise ShadowPriceError("fresh reprice provider event lacks one exact fixture reconciliation")
    row = rows[0]
    if row.matched_fotmob_fixture_id is None:
        raise ShadowPriceError("fresh reprice reconciliation omitted FotMob fixture identity")
    if fixture_identity != f"FOTMOB:{row.matched_fotmob_fixture_id}":
        raise ShadowPriceError("fresh reprice fixture identity differs from exact reconciliation")
    if row.competition_name is None:
        raise ShadowPriceError("fresh reprice reconciliation omitted exact competition identity")
    return reconciled, row, basis


def _validate_fresh_inventory(
    *,
    inventory,
    row,
    provider_event_id: str,
    prior_observed_at: datetime,
) -> None:
    """Require a strictly newer direct read of the same exact provider fixture."""

    if inventory.event_id != provider_event_id:
        raise ShadowPriceError("fresh reprice provider event identity changed")
    if (
        inventory.home_team_name != row.home_team_name
        or inventory.away_team_name != row.away_team_name
        or inventory.kickoff_utc != row.kickoff_utc
    ):
        raise ShadowPriceError("fresh reprice provider fixture identity changed")
    if inventory.observed_at <= prior_observed_at:
        raise ShadowPriceError("fresh reprice evidence is not strictly newer than retained quote evidence")


def _replace_sources_after_reprice(sources, refreshed_inputs, reprice_evidence):
    selected = sum(
        1
        for item in refreshed_inputs
        if item.router_decision.status is ShadowRouterDecisionStatus.SELECTED
    )
    no_bet = len(refreshed_inputs) - selected
    summary = dict(sources.source_summary)
    summary.update(
        {
            "portfolio_reprice_policy_id": FRESH_REPRICE_POLICY_ID,
            "portfolio_reprice_scope": "INITIAL_ROUTER_SELECTED_ONLY",
            "portfolio_repriced_fixture_count": len(reprice_evidence),
            "portfolio_repriced_provider_event_ids": sorted(reprice_evidence),
            "portfolio_reprice_evidence_by_event": {
                key: dict(reprice_evidence[key]) for key in sorted(reprice_evidence)
            },
            "wager_placed": False,
        }
    )
    return sources.__class__(
        router_inputs=tuple(refreshed_inputs),
        reviewed_fixture_count=sources.reviewed_fixture_count,
        reconciled_fixture_count=sources.reconciled_fixture_count,
        provider_event_count=sources.provider_event_count,
        priced_fixture_count=sources.priced_fixture_count,
        router_selected_count=selected,
        router_no_bet_count=no_bet,
        source_summary=MappingProxyType(summary),
    )


def _install_fresh_reprice_worker():
    """Install same-process-only fresh reprice support around the frozen PR-D/E APIs."""

    from domain import current_shadow_all_market_runner as runner

    original_quote_verify = quote_binding.verify_current_shadow_price_context
    original_acquire = runner._acquire_router_inputs
    original_portfolio_builder = portfolio_module.build_shadow_portfolio_router_input
    issued_contexts: dict[int, tuple[object, str]] = {}

    def validate_issued_context(value):
        issued = issued_contexts.get(id(value))
        if issued is None or issued[0] is not value:
            return original_quote_verify(value)
        if type(value) is not quote_binding.CurrentShadowPriceContext:
            raise ShadowPriceError("fresh reprice context type drifted")
        if value.source_context_mode != FRESH_REPRICE_MODE:
            raise ShadowPriceError("fresh reprice context mode drifted")
        if value.source_context_policy_id != FRESH_REPRICE_POLICY_ID:
            raise ShadowPriceError("fresh reprice source policy drifted")
        if value._bridge_bundle is not None:
            raise ShadowPriceError("fresh reprice cannot retain a legacy fixture bridge")
        if value.current_mapping_rebind_sha256 is not None or value.bridge_bundle_sha256 is not None:
            raise ShadowPriceError("fresh reprice cannot fabricate legacy mapping identities")
        if value._current_reconciliation_bundle is None:
            raise ShadowPriceError("fresh reprice omitted retained current reconciliation")
        if value.canonical_sha256 != issued[1]:
            raise ShadowPriceError("fresh reprice context canonical identity drifted")

        reconciled, row, basis = _reconciliation_row(
            value._current_reconciliation_bundle,
            provider_event_id=value.provider_event_id,
            fixture_identity=value.fixture_identity,
        )
        try:
            evidence = prb.replay_event_evidence(value._event_evidence)
        except prb.CurrentSportyBetSemanticRegistryError as exc:
            raise ShadowPriceError("fresh reprice PR-B evidence replay failed") from exc
        if evidence.fixture_identity != value.provider_event_id:
            raise ShadowPriceError("fresh reprice evidence event identity drifted")
        if evidence.fixture_identity_basis != basis:
            raise ShadowPriceError("fresh reprice evidence fixture basis drifted")
        inventory = evidence.inventory
        _validate_fresh_inventory(
            inventory=inventory,
            row=row,
            provider_event_id=value.provider_event_id,
            prior_observed_at=row.direct_event_observed_at,
        )
        if value.evaluation_time != inventory.observed_at:
            raise ShadowPriceError("fresh reprice evaluation time differs from direct response completion")
        if value.fixture_reconciliation_sha256 != reconciled.canonical_sha256:
            raise ShadowPriceError("fresh reprice reconciliation SHA drifted")
        if (
            value.source_raw_sha256 != inventory.source_raw_sha256
            or value.source_manifest_sha256 != inventory.source_manifest_sha256
            or value.source_inventory_sha256 != inventory.canonical_sha256
            or value.provider_inventory.canonical_sha256 != inventory.canonical_sha256
            or value.provider_registry.canonical_sha256 != value.provider_registry_sha256
            or quote_binding._sha256(value.scan.to_dict()) != value.prc_scan_sha256
        ):
            raise ShadowPriceError("fresh reprice retained source identities drifted")
        return value

    quote_binding.verify_current_shadow_price_context = validate_issued_context

    def build_portfolio_input(*, price_all_bundle, router_decision):
        context = getattr(price_all_bundle, "_context", None)
        if (
            type(context) is not quote_binding.CurrentShadowPriceContext
            or context.source_context_mode != FRESH_REPRICE_MODE
        ):
            return original_portfolio_builder(
                price_all_bundle=price_all_bundle,
                router_decision=router_decision,
            )
        if id(context) not in issued_contexts or issued_contexts[id(context)][0] is not context:
            raise portfolio_module.CurrentShadowPortfolioError(
                "fresh reprice Portfolio input was not issued by this worker"
            )
        try:
            checked_bundle = runner.price_module.verify_shadow_price_all_bundle(price_all_bundle)
            rebuilt_decision = runner.router_module.route_shadow_price_results(checked_bundle)
        except ShadowPriceError as exc:
            raise portfolio_module.CurrentShadowPortfolioError(
                "fresh reprice PR-D exact source/Router reconstruction failed"
            ) from exc
        if portfolio_module._canonical(rebuilt_decision.to_dict()) != portfolio_module._canonical(
            router_decision.to_dict()
        ):
            raise portfolio_module.CurrentShadowPortfolioError(
                "fresh reprice Router decision differs from exact reconstruction"
            )
        if rebuilt_decision.price_all_bundle_sha256 != checked_bundle.canonical_sha256:
            raise portfolio_module.CurrentShadowPortfolioError(
                "fresh reprice Router/Price-all SHA identity mismatch"
            )
        checked_context = validate_issued_context(checked_bundle._context)
        reconciled, row, _basis = _reconciliation_row(
            checked_context._current_reconciliation_bundle,
            provider_event_id=checked_context.provider_event_id,
            fixture_identity=checked_context.fixture_identity,
        )
        inventory = checked_context.provider_inventory
        _validate_fresh_inventory(
            inventory=inventory,
            row=row,
            provider_event_id=checked_context.provider_event_id,
            prior_observed_at=row.direct_event_observed_at,
        )

        value = object.__new__(portfolio_module.ShadowPortfolioRouterInput)
        values = {
            "price_all_bundle": checked_bundle,
            "router_decision": rebuilt_decision,
            "price_all_bundle_sha256": checked_bundle.canonical_sha256,
            "router_decision_sha256": rebuilt_decision.decision_sha256,
            "fixture_identity": checked_context.fixture_identity,
            "provider_event_id": checked_context.provider_event_id,
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "competition": row.competition_name,
            "kickoff_utc": row.kickoff_utc,
            "source_observed_at": inventory.observed_at,
            "fixture_reconciliation_sha256": reconciled.canonical_sha256,
            "source_raw_sha256": inventory.source_raw_sha256,
            "source_manifest_sha256": inventory.source_manifest_sha256,
            "source_inventory_sha256": inventory.canonical_sha256,
        }
        for name, item in values.items():
            object.__setattr__(value, name, item)
        return value

    portfolio_module.build_shadow_portfolio_router_input = build_portfolio_input

    def fresh_context(prior_context, *, repository_root: Path):
        checked = quote_binding.verify_current_shadow_price_context(prior_context)
        if checked.source_context_mode != quote_binding.CURRENT_RECONCILIATION_DIRECT:
            raise ShadowPriceError("fresh reprice accepts only the direct current reconciliation path")
        if checked._current_reconciliation_bundle is None:
            raise ShadowPriceError("fresh reprice prior context omitted reconciliation")
        reconciled, row, basis = _reconciliation_row(
            checked._current_reconciliation_bundle,
            provider_event_id=checked.provider_event_id,
            fixture_identity=checked.fixture_identity,
        )
        try:
            directory, _manifest = live.capture_live_event_quote_evidence(
                event_id=checked.provider_event_id,
                repository_root=repository_root,
                execute_live_network=True,
            )
            evidence = prb.load_provider_event_evidence(
                directory,
                repository_root=repository_root,
                fixture_identity=checked.provider_event_id,
                fixture_identity_basis=basis,
            )
            evidence = prb.replay_event_evidence(evidence)
        except (live.SportyBetLiveEventQuoteEvidenceError, prb.CurrentSportyBetSemanticRegistryError) as exc:
            raise ShadowPriceError("fresh reprice direct provider evidence acquisition failed") from exc
        inventory = evidence.inventory
        _validate_fresh_inventory(
            inventory=inventory,
            row=row,
            provider_event_id=checked.provider_event_id,
            prior_observed_at=checked.provider_inventory.observed_at,
        )
        context = quote_binding._compose(
            complete_current_history=checked._complete_current_history,
            fixture_identity=checked.fixture_identity,
            evidence=evidence,
            evaluation=inventory.observed_at,
            fixture_reconciliation_sha256=reconciled.canonical_sha256,
            current_mapping_rebind_sha256=None,
            bridge_bundle_sha256=None,
            source_context_mode=FRESH_REPRICE_MODE,
            source_context_policy_id=FRESH_REPRICE_POLICY_ID,
            bridge_bundle=None,
            reconciliation_bundle=reconciled,
        )
        issued_contexts[id(context)] = (context, context.canonical_sha256)
        validate_issued_context(context)
        return context

    def acquire(*args, **kwargs):
        sources = original_acquire(*args, **kwargs)
        if sources.router_selected_count == 0:
            return sources
        repository_root = kwargs.get("repository_root")
        if not isinstance(repository_root, Path):
            raise runner.CurrentShadowAllMarketRunnerError(
                "fresh reprice requires the exact repository root"
            )
        refreshed_inputs = []
        evidence_rows: dict[str, dict[str, Any]] = {}
        for source in sources.router_inputs:
            if source.router_decision.status is not ShadowRouterDecisionStatus.SELECTED:
                refreshed_inputs.append(source)
                continue
            context = fresh_context(
                source.price_all_bundle._context,
                repository_root=repository_root,
            )
            priced_bundle = runner.price_module.price_all_shadow_fixture(context)
            decision = runner.router_module.route_shadow_price_results(priced_bundle)
            refreshed = runner.portfolio_module.build_shadow_portfolio_router_input(
                price_all_bundle=priced_bundle,
                router_decision=decision,
            )
            refreshed_inputs.append(refreshed)
            inventory = context.provider_inventory
            evidence_rows[context.provider_event_id] = {
                "fixture_identity": context.fixture_identity,
                "source_observed_at": _iso(inventory.observed_at),
                "source_raw_sha256": inventory.source_raw_sha256,
                "source_manifest_sha256": inventory.source_manifest_sha256,
                "source_inventory_sha256": inventory.canonical_sha256,
                "router_status_after_reprice": decision.status.value,
                "wager_placed": False,
            }
        return _replace_sources_after_reprice(
            sources,
            refreshed_inputs,
            evidence_rows,
        )

    runner._acquire_router_inputs = acquire

    def restore() -> None:
        runner._acquire_router_inputs = original_acquire
        portfolio_module.build_shadow_portfolio_router_input = original_portfolio_builder
        quote_binding.verify_current_shadow_price_context = original_quote_verify

    return restore


def _execute_worker(args) -> int:
    restore = _install_fresh_reprice_worker()
    try:
        return summary_cli._execute_worker(args)
    finally:
        restore()


def main(argv: list[str] | None = None) -> int:
    args = cli.build_parser().parse_args(argv)
    if os.environ.get(cli.WORKER_ENV) == "1":
        return _execute_worker(args)

    env = dict(os.environ)
    env[cli.WORKER_ENV] = "1"
    command = [
        sys.executable,
        "-m",
        WORKER_MODULE,
        "--target-size",
        str(args.target_size),
        "--output-dir",
        str(args.output_dir),
    ]
    try:
        completed = subprocess.run(
            command,
            env=env,
            check=False,
            timeout=runner_timeout(),
        )
    except subprocess.TimeoutExpired:
        from domain import current_shadow_all_market_runner as runner

        result = runner.write_current_shadow_timeout_receipt(
            target_size=args.target_size,
            output_dir=args.output_dir,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return 0
    return completed.returncode


def runner_timeout() -> int:
    from domain import current_shadow_all_market_runner as runner

    return runner.CURRENT_SHADOW_RUN_TIMEOUT_SECONDS


if __name__ == "__main__":
    raise SystemExit(main())
