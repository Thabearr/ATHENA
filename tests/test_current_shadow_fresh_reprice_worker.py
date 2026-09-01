from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from domain._current_shadow_price_core import ShadowPriceError, ShadowRouterDecisionStatus
from scripts import execute_current_shadow_all_market_fresh_reprice as fresh


UTC = timezone.utc
OLD = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
KICKOFF = datetime(2026, 9, 1, 19, 0, tzinfo=UTC)


def _row():
    return SimpleNamespace(
        home_team_name="Home",
        away_team_name="Away",
        kickoff_utc=KICKOFF,
    )


def _inventory(**overrides):
    values = {
        "event_id": "sr:match:123",
        "home_team_name": "Home",
        "away_team_name": "Away",
        "kickoff_utc": KICKOFF,
        "observed_at": OLD + timedelta(seconds=1),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_fresh_reprice_requires_strictly_newer_exact_same_provider_fixture():
    fresh._validate_fresh_inventory(
        inventory=_inventory(),
        row=_row(),
        provider_event_id="sr:match:123",
        prior_observed_at=OLD,
    )

    with pytest.raises(ShadowPriceError, match="not strictly newer"):
        fresh._validate_fresh_inventory(
            inventory=_inventory(observed_at=OLD),
            row=_row(),
            provider_event_id="sr:match:123",
            prior_observed_at=OLD,
        )

    for changed in (
        {"event_id": "sr:match:124"},
        {"home_team_name": "Other"},
        {"away_team_name": "Other"},
        {"kickoff_utc": KICKOFF + timedelta(minutes=1)},
    ):
        with pytest.raises(ShadowPriceError, match="identity changed"):
            fresh._validate_fresh_inventory(
                inventory=_inventory(**changed),
                row=_row(),
                provider_event_id="sr:match:123",
                prior_observed_at=OLD,
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


def test_reconciliation_type_dispatch_remains_exact_and_rejects_unknown_bundle():
    with pytest.raises(ShadowPriceError, match="exact reviewed current reconciliation"):
        fresh._reconciliation_verifier_and_basis(SimpleNamespace())
