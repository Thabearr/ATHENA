from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from domain._current_shadow_price_core import ShadowPriceError, ShadowRouterDecisionStatus
from domain import current_shadow_fresh_reprice_runtime as fresh
from domain import _current_shadow_quote_binding as quote_binding


UTC = timezone.utc
def test_unknown_reconciliation_context_is_rejected_by_canonical_fresh_contract():
    with pytest.raises(ShadowPriceError, match="bundle type is not reviewed"):
        quote_binding._verified_reconciliation_row(
            SimpleNamespace(),
            provider_event_id="sr:match:123",
            fixture_identity="FOTMOB:1",
        )


def test_source_bundle_records_only_fresh_reprice_evidence_and_recomputes_router_counts():
    selected = SimpleNamespace(
        router_decision=SimpleNamespace(status=ShadowRouterDecisionStatus.SELECTED)
    )
    no_bet = SimpleNamespace(
        router_decision=SimpleNamespace(status=ShadowRouterDecisionStatus.NO_BET)
    )
    sources = SimpleNamespace(
        router_inputs=(selected, selected),
        reviewed_fixture_count=44,
        reconciled_fixture_count=5,
        provider_event_count=923,
        priced_fixture_count=5,
        router_selected_count=2,
        router_no_bet_count=3,
        source_summary={"existing": "preserved", "wager_placed": False},
    )
    evidence = {
        "sr:match:123": {
            "fixture_identity": "FOTMOB:1",
            "source_observed_at": "2026-09-01T09:40:00.000000Z",
            "router_status_after_reprice": "SELECTED",
            "wager_placed": False,
        }
    }

    rebuilt = fresh._replace_sources_after_reprice(
        sources,
        (selected, no_bet),
        evidence,
    )

    assert rebuilt.router_inputs == (selected, no_bet)
    assert rebuilt.router_selected_count == 1
    assert rebuilt.router_no_bet_count == 1
    assert rebuilt.reviewed_fixture_count == 44
    assert rebuilt.reconciled_fixture_count == 5
    assert rebuilt.provider_event_count == 923
    assert rebuilt.priced_fixture_count == 5
    assert rebuilt.source_summary["existing"] == "preserved"
    assert rebuilt.source_summary["portfolio_reprice_policy_id"] == fresh.FRESH_REPRICE_POLICY_ID
    assert rebuilt.source_summary["portfolio_reprice_scope"] == "INITIAL_ROUTER_SELECTED_ONLY"
    assert rebuilt.source_summary["portfolio_repriced_fixture_count"] == 1
    assert rebuilt.source_summary["portfolio_repriced_provider_event_ids"] == ["sr:match:123"]
    assert rebuilt.source_summary["wager_placed"] is False


def test_fresh_runtime_does_not_expose_a_verifier_installation_hook():
    assert not hasattr(fresh, "_install_fresh_reprice_worker")
    assert hasattr(fresh, "refresh_selected_inputs")
