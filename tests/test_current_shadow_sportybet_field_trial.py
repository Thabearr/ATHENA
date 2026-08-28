from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from domain import score_matrix
from domain import sportybet_live_event_quote_evidence as live
from domain.current_shadow_sportybet_field_trial import (
    AUTHORITY,
    CurrentShadowSportyBetFieldTrialError,
    ResearchFixtureDecision,
    ResearchFixtureIdentity,
    build_total_goals_research_decision,
    optimize_research_shadow_portfolio,
)
from tests.test_current_fotmob_utc_native_shadow_prediction import _handoff

UTC = dt.timezone.utc


def _sealed(tmp_path, monkeypatch):
    handoff, *_rest = _handoff(tmp_path, monkeypatch)
    row = handoff.rows[0]
    assert row.sealed_prediction is not None
    assert row.sealed_prediction_sha256 is not None
    return row


def _fixture(row, *, suffix: int = 1) -> ResearchFixtureIdentity:
    return ResearchFixtureIdentity(
        fixture_identifier=row.fixture_identifier,
        event_id=str(700000 + suffix),
        home_team="Home FC",
        away_team="Away FC",
        competition="Premier League",
        kickoff_utc=row.fixture.kickoff_utc,
    )


def _inventory(row, fixture: ResearchFixtureIdentity):
    rates = dict(row.sealed_prediction.rates)
    matrix = score_matrix.build_score_matrix(
        rates["calibrated_home"],
        rates["calibrated_away"],
    )
    line = next(
        candidate
        for candidate in (3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5)
        if matrix.under(candidate) > 0.85
    )
    specifier = f"total={line:g}"
    observed = fixture.kickoff_utc - dt.timedelta(hours=2)
    selections = (
        live.SportyBetLiveEventSelection(
            event_id=fixture.event_id,
            market_id="18",
            market_name="Total Goals",
            specifier=specifier,
            outcome_id="O",
            outcome_name=f"Over {line:g}",
            bookable=True,
            bookability_basis="EXPLICIT_ACTIVE_FLAG",
            odds_raw="5.0",
            odds_decimal=5.0,
        ),
        live.SportyBetLiveEventSelection(
            event_id=fixture.event_id,
            market_id="18",
            market_name="Total Goals",
            specifier=specifier,
            outcome_id="U",
            outcome_name=f"Under {line:g}",
            bookable=True,
            bookability_basis="EXPLICIT_ACTIVE_FLAG",
            odds_raw="1.3",
            odds_decimal=1.3,
        ),
    )
    return live.SportyBetLiveEventQuoteInventory(
        dataset_name=live.INVENTORY_DATASET_NAME,
        event_id=fixture.event_id,
        home_team_name=fixture.home_team,
        away_team_name=fixture.away_team,
        kickoff_utc=fixture.kickoff_utc,
        booking_status=None,
        event_status=0,
        match_status="Not started",
        prematch_bookable_observed=True,
        observed_at=observed,
        observation_authority=live.OBSERVATION_AUTHORITY,
        provider_quote_at=None,
        provider_snapshot_id=None,
        source_manifest_sha256="a" * 64,
        source_raw_sha256="b" * 64,
        selections=selections,
    )


def _decision(tmp_path, monkeypatch):
    row = _sealed(tmp_path, monkeypatch)
    fixture = _fixture(row)
    inventory = _inventory(row, fixture)
    evaluation = inventory.observed_at + dt.timedelta(minutes=5)
    decision = build_total_goals_research_decision(
        fixture=fixture,
        sealed_prediction=row.sealed_prediction,
        sealed_prediction_sha256=row.sealed_prediction_sha256,
        inventory=inventory,
        evaluation_time=evaluation,
    )
    return row, fixture, inventory, evaluation, decision


def test_research_lane_never_claims_production_or_bet_authority(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_prefix, decision = _decision(tmp_path, monkeypatch)
    selected = decision.selected

    assert decision.status == "SELECTED"
    assert selected is not None
    assert selected.provider_market_name == "Total Goals"
    assert selected.outcome_id.value == "UNDER"
    assert selected.event_probability > 0.85
    assert selected.net_expected_value > 0.0
    assert selected.robust_edge > 0.0
    assert AUTHORITY["research_market_probability"] is True
    for key in (
        "production_model",
        "production_probability",
        "phase6",
        "production_price_all",
        "production_market_router",
        "production_portfolio",
        "production_selection",
        "sportybet_execution",
        "staking",
        "bet",
        "wager_placed",
    ):
        assert AUTHORITY[key] is False


def test_stale_current_provider_quote_is_no_bet(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row, fixture, inventory, evaluation, _decision_value = _decision(tmp_path, monkeypatch)
    stale = dataclasses.replace(
        inventory,
        observed_at=evaluation - dt.timedelta(seconds=901),
    )
    decision = build_total_goals_research_decision(
        fixture=fixture,
        sealed_prediction=row.sealed_prediction,
        sealed_prediction_sha256=row.sealed_prediction_sha256,
        inventory=stale,
        evaluation_time=evaluation,
    )
    assert decision.status == "NO_BET"
    assert decision.selected is None
    assert "CURRENT_PROVIDER_QUOTE_STALE" in decision.decision_reasons


def test_exact_120_second_kickoff_boundary_is_no_bet(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _sealed(tmp_path, monkeypatch)
    fixture = _fixture(row)
    inventory = _inventory(row, fixture)
    evaluation = fixture.kickoff_utc - dt.timedelta(seconds=120)
    fresh_inventory = dataclasses.replace(
        inventory,
        observed_at=evaluation - dt.timedelta(seconds=30),
    )
    decision = build_total_goals_research_decision(
        fixture=fixture,
        sealed_prediction=row.sealed_prediction,
        sealed_prediction_sha256=row.sealed_prediction_sha256,
        inventory=fresh_inventory,
        evaluation_time=evaluation,
    )
    assert decision.status == "NO_BET"
    assert decision.selected is None
    assert "FIXTURE_TOO_CLOSE_TO_KICKOFF" in decision.decision_reasons


def test_provider_semantic_label_drift_is_not_guessed(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _sealed(tmp_path, monkeypatch)
    fixture = _fixture(row)
    inventory = _inventory(row, fixture)
    selections = list(inventory.selections)
    under_index = next(index for index, item in enumerate(selections) if item.outcome_id == "U")
    selections[under_index] = dataclasses.replace(
        selections[under_index],
        outcome_name="Under Goals",
    )
    drifted = dataclasses.replace(inventory, selections=tuple(selections))
    decision = build_total_goals_research_decision(
        fixture=fixture,
        sealed_prediction=row.sealed_prediction,
        sealed_prediction_sha256=row.sealed_prediction_sha256,
        inventory=drifted,
        evaluation_time=inventory.observed_at + dt.timedelta(minutes=5),
    )
    assert decision.status == "NO_BET"
    assert decision.selected is None
    assert decision.opportunities == ()


def test_provider_fixture_identity_mismatch_fails_closed(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _sealed(tmp_path, monkeypatch)
    fixture = _fixture(row)
    inventory = dataclasses.replace(_inventory(row, fixture), home_team_name="Other FC")
    with pytest.raises(CurrentShadowSportyBetFieldTrialError, match="provider event identity"):
        build_total_goals_research_decision(
            fixture=fixture,
            sealed_prediction=row.sealed_prediction,
            sealed_prediction_sha256=row.sealed_prediction_sha256,
            inventory=inventory,
            evaluation_time=inventory.observed_at + dt.timedelta(minutes=5),
        )


def test_frozen_market_family_cap_preserves_shortfall_instead_of_padding(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _row, _fixture_value, _inventory_value, evaluation, decision = _decision(
        tmp_path, monkeypatch
    )
    selected = decision.selected
    assert selected is not None
    decisions = []
    for index in range(20):
        fixture = dataclasses.replace(
            selected.fixture,
            fixture_identifier=f"FOTMOB:{9000 + index}",
            event_id=str(800000 + index),
            home_team=f"Home {index}",
            away_team=f"Away {index}",
            competition=f"League {index}",
        )
        opportunity = dataclasses.replace(
            selected,
            opportunity_id=f"{index + 1:064x}",
            fixture=fixture,
        )
        decisions.append(
            ResearchFixtureDecision(
                fixture=fixture,
                status="SELECTED",
                selected_opportunity_id=opportunity.opportunity_id,
                opportunities=(opportunity,),
                decision_reasons=("RESEARCH_SHADOW_TOTAL_GOALS_ROBUST_VALUE_SELECTED",),
            )
        )

    portfolio = optimize_research_shadow_portfolio(
        decisions,
        target_size=20,
        evaluation_time=evaluation,
    )
    assert len(portfolio.selected_legs) == 10
    assert portfolio.shortfall == 10
    assert portfolio.fulfilled is False
    assert portfolio.field_trial_status == "RESEARCH_QUALIFIED_WITH_SHORTFALL"
    assert portfolio.caps["market_family"] == 10
    assert portfolio.to_dict()["wager_placed"] is False


def test_direct_transport_intent_contains_no_caller_odds(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_prefix, decision = _decision(tmp_path, monkeypatch)
    selected = decision.selected
    assert selected is not None
    assert set(selected.direct_selection()) == {
        "eventId",
        "marketId",
        "outcomeId",
        "specifier",
    }
    assert "odds" not in selected.direct_selection()
