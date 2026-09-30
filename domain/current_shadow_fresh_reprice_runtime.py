"""Explicit fresh-direct-quote refresh for the Current Shadow runtime.

Transport remains owned by the reviewed live-event evidence module. This
module composes its exact evidence into the existing Price-all -> Router ->
Portfolio path through a single source-controlled runtime binding; it installs
no verifier, Portfolio, or reconciliation monkeypatch.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable

from domain import current_shadow_all_market_portfolio as portfolio_module
from domain import current_shadow_canonical_core_adapter as canonical_adapter
from domain import current_sportybet_semantic_registry as prb
from domain import sportybet_live_event_quote_evidence as live
from domain._current_shadow_price_core import ShadowPriceError, ShadowRouterDecisionStatus
from domain._current_shadow_quote_binding import (
    FRESH_REPRICE_SOURCE_CONTEXT_POLICY_ID,
    build_current_shadow_price_context_for_fresh_reprice,
)


FRESH_REPRICE_POLICY_ID = FRESH_REPRICE_SOURCE_CONTEXT_POLICY_ID


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _replace_sources_after_reprice(
    sources: Any,
    refreshed_inputs: list[Any],
    reprice_evidence: dict[str, dict[str, Any]],
) -> Any:
    selected = sum(
        item.router_decision.status is ShadowRouterDecisionStatus.SELECTED
        for item in refreshed_inputs
    )
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
        router_no_bet_count=len(refreshed_inputs) - selected,
        source_summary=MappingProxyType(summary),
    )


def _refresh_selected_inputs(
    sources: Any,
    *,
    repository_root: Path,
    runtime_bindings: Any,
    evidence_loader: Callable[..., Any] | None = None,
    release_identity=None,
    resources=None,
) -> Any:
    """Refresh only initially selected exact fixtures; loader is an offline test seam."""

    if not isinstance(repository_root, Path):
        raise ShadowPriceError("fresh reprice requires the exact repository root")
    source_context = {}
    if release_identity is not None or resources is not None:
        canonical_adapter.resolve_shadow_canonical_core(release_identity=release_identity, resources=resources)
        source_context = {"release_identity": release_identity, "resources": resources}
    refreshed_inputs: list[Any] = []
    evidence_by_event: dict[str, dict[str, Any]] = {}
    for source in sources.router_inputs:
        if source.router_decision.status is not ShadowRouterDecisionStatus.SELECTED:
            refreshed_inputs.append(source)
            continue
        prior_context = source.price_all_bundle._context
        provider_event_id = prior_context.provider_event_id
        if evidence_loader is None:
            try:
                directory, _manifest = live.capture_live_event_quote_evidence(
                    event_id=provider_event_id,
                    repository_root=repository_root,
                    execute_live_network=True,
                )
            except live.SportyBetLiveEventQuoteEvidenceError as exc:
                raise ShadowPriceError("fresh reprice direct provider evidence acquisition failed") from exc
        else:
            directory = evidence_loader(
                event_id=provider_event_id,
                repository_root=repository_root,
            )
        reconciliation = prior_context._current_reconciliation_bundle
        if reconciliation is None:
            raise ShadowPriceError("fresh reprice prior context omitted retained reconciliation")
        # Load using the exact source-owned reconciliation family. The builder
        # independently replays and binds this evidence before accepting it.
        from domain import _current_shadow_quote_binding as quote_binding

        _replayed, _row, fixture_basis = quote_binding._verified_reconciliation_row(
            reconciliation,
            provider_event_id=provider_event_id,
            fixture_identity=prior_context.fixture_identity,
        )
        try:
            evidence = prb.load_provider_event_evidence(
                directory,
                repository_root=repository_root,
                fixture_identity=provider_event_id,
                fixture_identity_basis=fixture_basis,
            )
        except prb.CurrentSportyBetSemanticRegistryError as exc:
            raise ShadowPriceError("fresh reprice PR-B provider evidence replay failed") from exc
        fresh_context = build_current_shadow_price_context_for_fresh_reprice(
            prior_context=prior_context,
            fresh_provider_event_evidence=evidence,
            runtime_bindings=runtime_bindings,
        )
        priced_bundle = canonical_adapter.price_all_shadow_fixture(fresh_context, **source_context)
        decision = canonical_adapter.route_shadow_price_results(priced_bundle, **source_context)
        portfolio_input = canonical_adapter.build_shadow_portfolio_router_input(
            price_all_bundle=priced_bundle,
            router_decision=decision,
            **source_context,
        )
        refreshed_inputs.append(portfolio_input)
        inventory = fresh_context.provider_inventory
        evidence_by_event[provider_event_id] = {
            "fixture_identity": fresh_context.fixture_identity,
            "source_observed_at": _iso(inventory.observed_at),
            "source_raw_sha256": inventory.source_raw_sha256,
            "source_manifest_sha256": inventory.source_manifest_sha256,
            "source_inventory_sha256": inventory.canonical_sha256,
            "router_status_after_reprice": decision.status.value,
            "wager_placed": False,
        }
    return _replace_sources_after_reprice(sources, refreshed_inputs, evidence_by_event)


def refresh_selected_inputs(
    sources: Any,
    *,
    repository_root: Path,
    runtime_bindings: Any,
    release_identity=None,
    resources=None,
) -> Any:
    """Production refresh boundary; exact anonymous detail reads only when selected."""

    if release_identity is not None or resources is not None:
        canonical_adapter.resolve_shadow_canonical_core(release_identity=release_identity, resources=resources)
    if sources.router_selected_count == 0:
        return sources
    return _refresh_selected_inputs(
        sources,
        repository_root=repository_root,
        runtime_bindings=runtime_bindings,
        release_identity=release_identity,
        resources=resources,
    )


__all__ = ["FRESH_REPRICE_POLICY_ID", "refresh_selected_inputs"]
