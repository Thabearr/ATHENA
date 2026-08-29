from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from domain import current_shadow_sportybet_field_trial as trial
from domain.fotmob_data_matches_capture import (
    sha256_data_matches_capture_manifest,
)
from domain.markets import MarketId, OutcomeId
from tests import test_current_direct_provider_canonical_market_mapping_rebind as mapping_helpers
from tests import test_current_fotmob_latest_durable_fresh_history as latest_helpers


UTC = dt.timezone.utc


def _complete_history(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    source, _lower, _evidence = latest_helpers._source_bundle(
        tmp_path / "latest-history",
        monkeypatch,
    )
    return latest_helpers._handoff(source)


def _source_capture_identity(history) -> dict[str, object]:
    manifest = history.selected_prefix.source_bundle.source_manifest
    return {
        "request_date": manifest.request_date,
        "raw_sha256": history.shadow_handoff.source_raw_sha256,
        "raw_size": manifest.raw_size,
        "manifest_sha256": history.shadow_handoff.source_manifest_sha256,
        "observed_at": manifest.observed_at.isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z"),
    }


def _selection(
    *,
    line: float,
    outcome_id: str,
    odds: float,
    market_id: str = "18",
):
    return dataclasses.replace(
        mapping_helpers._selection(
            market_id=market_id,
            market_name="Total Goals",
            specifier=f"total={line:g}",
            outcome_id=outcome_id,
            outcome_name=(
                f"Over {line:g}"
                if outcome_id == "O"
                else f"Under {line:g}"
            ),
        ),
        odds_raw=f"{odds:g}",
        odds_decimal=odds,
    )


def _source_row(
    *,
    line: float,
    outcome_id: str,
    market_id: str = "18",
):
    return mapping_helpers._source_row(
        market_id=market_id,
        market_name="Total Goals",
        specifier=f"total={line:g}",
        outcome_id=outcome_id,
        outcome_name=(
            f"Over {line:g}"
            if outcome_id == "O"
            else f"Under {line:g}"
        ),
        canonical_market=MarketId.TOTAL_GOALS,
        canonical_outcome=(
            OutcomeId.OVER if outcome_id == "O" else OutcomeId.UNDER
        ),
        line=line,
    )


def _current_mapping(
    history,
    monkeypatch: pytest.MonkeyPatch,
    *,
    line: float = 6.5,
    mapping_evaluation: dt.datetime | None = None,
    include_unreviewed_line: bool = False,
):
    shadow_row = history.shadow_handoff.rows[0]
    kickoff = shadow_row.kickoff_utc
    source_observed = (
        history.selected_prefix.source_bundle.source_manifest.observed_at
    )
    evaluation = mapping_evaluation or (
        source_observed + dt.timedelta(minutes=5)
    )

    monkeypatch.setattr(mapping_helpers, "CURRENT_FIXTURE", "1001")
    monkeypatch.setattr(mapping_helpers, "KICKOFF", kickoff)
    monkeypatch.setattr(mapping_helpers, "EVALUATION", evaluation)

    source_mapping = mapping_helpers._source_mapping(
        _source_row(line=line, outcome_id="O"),
        _source_row(line=line, outcome_id="U"),
    )
    selections = [
        _selection(line=line, outcome_id="O", odds=6.0),
        _selection(line=line, outcome_id="U", odds=1.25),
    ]
    if include_unreviewed_line:
        selections.extend(
            (
                _selection(
                    line=9.5,
                    outcome_id="O",
                    odds=50.0,
                    market_id="19",
                ),
                _selection(
                    line=9.5,
                    outcome_id="U",
                    odds=5.0,
                    market_id="19",
                ),
            )
        )
    inventory = mapping_helpers._inventory(
        *selections,
        observed_at=evaluation - dt.timedelta(seconds=60),
        kickoff=kickoff,
    )
    current_bundle = mapping_helpers._current_bundle(
        inventory,
        kickoff=kickoff,
    )
    current_bundle.fotmob_capture_identities = (
        _source_capture_identity(history),
    )
    mapping, _calls = mapping_helpers._build(
        monkeypatch,
        inventory=inventory,
        source_mapping=source_mapping,
        current_bundle=current_bundle,
        evaluation=evaluation,
    )
    return mapping, inventory, evaluation


def _decision(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    include_unreviewed_line: bool = False,
    mapping_evaluation: dt.datetime | None = None,
    decision_evaluation: dt.datetime | None = None,
):
    history = _complete_history(tmp_path, monkeypatch)
    mapping, inventory, mapping_time = _current_mapping(
        history,
        monkeypatch,
        include_unreviewed_line=include_unreviewed_line,
        mapping_evaluation=mapping_evaluation,
    )
    evaluation = decision_evaluation or (
        max(mapping_time, inventory.observed_at)
        + dt.timedelta(seconds=30)
    )
    decision = trial.build_source_bound_total_goals_research_decision(
        complete_current_history=history,
        current_mapping_rebind=mapping,
        evaluation_time=evaluation,
    )
    return history, mapping, inventory, evaluation, decision


def test_source_bound_research_lane_never_claims_production_or_bet_authority(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history, mapping, _inventory, _evaluation, decision = _decision(
        tmp_path,
        monkeypatch,
    )
    selected = decision.selected

    assert history.current_fresh_history_prefix_complete is True
    assert mapping.mapped_selection_count == 2
    assert decision.status == "SELECTED"
    assert selected is not None
    assert selected.provider_market_name == "Total Goals"
    assert selected.outcome_id is OutcomeId.UNDER
    assert selected.net_expected_value > 0.0
    assert selected.robust_edge > 0.0
    assert selected.latest_history_sha256 == decision.latest_history_sha256
    assert (
        selected.current_mapping_rebind_sha256
        == decision.current_mapping_rebind_sha256
    )

    for key in (
        "complete_current_fresh_history_proof",
        "reviewed_current_fixture_identity",
        "reviewed_shadow_expected_goals",
        "exact_reviewed_current_market_mapping",
        "research_score_matrix",
        "research_market_probability",
        "research_current_provider_value",
        "research_field_trial_routing",
        "research_field_trial_portfolio",
    ):
        assert trial.AUTHORITY[key] is True
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
        assert trial.AUTHORITY[key] is False


def test_unreviewed_provider_total_line_is_never_generalized_into_research_surface(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_prefix, decision = _decision(
        tmp_path,
        monkeypatch,
        include_unreviewed_line=True,
    )
    assert decision.opportunities
    assert {item.line for item in decision.opportunities} == {6.5}
    assert {
        (item.provider_market_id, item.provider_specifier)
        for item in decision.opportunities
    } == {("18", "total=6.5")}


def test_latest_history_and_mapping_must_share_exact_fotmob_capture_ancestry(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = _complete_history(tmp_path, monkeypatch)
    mapping, inventory, mapping_time = _current_mapping(
        history,
        monkeypatch,
    )
    mapping._current_bundle.fotmob_capture_identities = (
        {
            **_source_capture_identity(history),
            "manifest_sha256": "f" * 64,
        },
    )
    with pytest.raises(
        trial.CurrentShadowSportyBetFieldTrialError,
        match="share one exact FotMob capture ancestry",
    ):
        trial.build_source_bound_total_goals_research_decision(
            complete_current_history=history,
            current_mapping_rebind=mapping,
            evaluation_time=max(mapping_time, inventory.observed_at)
            + dt.timedelta(seconds=30),
        )


def test_incomplete_pr244_shadow_object_cannot_substitute_for_latest_history(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = _complete_history(tmp_path, monkeypatch)
    mapping, inventory, mapping_time = _current_mapping(
        history,
        monkeypatch,
    )
    with pytest.raises(
        trial.CurrentShadowSportyBetFieldTrialError,
        match="complete latest PR151 history",
    ):
        trial.build_source_bound_total_goals_research_decision(
            complete_current_history=history.shadow_handoff,
            current_mapping_rebind=mapping,
            evaluation_time=max(mapping_time, inventory.observed_at)
            + dt.timedelta(seconds=30),
        )


def test_stale_current_provider_quote_is_no_bet(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = _complete_history(tmp_path, monkeypatch)
    mapping, inventory, _mapping_time = _current_mapping(
        history,
        monkeypatch,
    )
    evaluation = inventory.observed_at + dt.timedelta(seconds=901)
    decision = trial.build_source_bound_total_goals_research_decision(
        complete_current_history=history,
        current_mapping_rebind=mapping,
        evaluation_time=evaluation,
    )
    assert decision.status == "NO_BET"
    assert decision.selected is None
    assert "CURRENT_PROVIDER_QUOTE_STALE" in decision.decision_reasons


def test_exact_120_second_kickoff_boundary_is_no_bet_with_fresh_quote(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = _complete_history(tmp_path, monkeypatch)
    kickoff = history.shadow_handoff.rows[0].kickoff_utc
    mapping_time = kickoff - dt.timedelta(seconds=180)
    mapping, _inventory, _ = _current_mapping(
        history,
        monkeypatch,
        mapping_evaluation=mapping_time,
    )
    decision = trial.build_source_bound_total_goals_research_decision(
        complete_current_history=history,
        current_mapping_rebind=mapping,
        evaluation_time=kickoff - dt.timedelta(seconds=120),
    )
    assert decision.status == "NO_BET"
    assert decision.selected is None
    assert "FIXTURE_TOO_CLOSE_TO_KICKOFF" in decision.decision_reasons
    assert "CURRENT_PROVIDER_QUOTE_STALE" not in decision.decision_reasons


def test_invalid_sportybet_event_identity_is_rejected() -> None:
    with pytest.raises(
        trial.CurrentShadowSportyBetFieldTrialError,
        match="sr:match",
    ):
        trial.ResearchFixtureIdentity(
            fixture_identifier="FOTMOB:1001",
            event_id="700001",
            home_team="Home FC",
            away_team="Away FC",
            competition="Premier League",
            kickoff_utc=dt.datetime(
                2026,
                8,
                29,
                15,
                0,
                tzinfo=UTC,
            ),
        )


def test_portfolio_rechecks_exact_120_second_boundary_and_preserves_exclusion(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = _complete_history(tmp_path, monkeypatch)
    kickoff = history.shadow_handoff.rows[0].kickoff_utc
    mapping_time = kickoff - dt.timedelta(seconds=240)
    *_prefix, decision = _decision(
        tmp_path,
        monkeypatch,
        mapping_evaluation=mapping_time,
        decision_evaluation=kickoff - dt.timedelta(seconds=180),
    )
    assert decision.selected is not None

    portfolio = trial.optimize_research_shadow_portfolio(
        (decision,),
        target_size=1,
        evaluation_time=kickoff - dt.timedelta(seconds=120),
    )
    assert portfolio.selected_legs == ()
    assert portfolio.shortfall == 1
    assert len(portfolio.exclusions) == 1
    assert (
        "FIXTURE_TOO_CLOSE_TO_KICKOFF_AT_PORTFOLIO_TIME"
        in portfolio.exclusions[0].reasons
    )


def _clone_selected_decision(
    base: trial.ResearchFixtureDecision,
    *,
    index: int,
) -> trial.ResearchFixtureDecision:
    selected = base.selected
    assert selected is not None
    fixture = dataclasses.replace(
        selected.fixture,
        fixture_identifier=f"FOTMOB:{9000 + index}",
        event_id=f"sr:match:{800000 + index}",
        home_team=f"Home {index}",
        away_team=f"Away {index}",
        competition=f"League {index}",
    )
    identity_payload = trial._opportunity_identity_payload(
        fixture=fixture,
        sealed_prediction_sha256=selected.sealed_prediction_sha256,
        latest_history_sha256=selected.latest_history_sha256,
        current_mapping_rebind_sha256=(
            selected.current_mapping_rebind_sha256
        ),
        mapped_selection_sha256=selected.mapped_selection_sha256,
        current_inventory_sha256=selected.current_inventory_sha256,
        provider_market_id=selected.provider_market_id,
        provider_specifier=selected.provider_specifier,
        provider_outcome_id=selected.provider_outcome_id,
        decimal_odds=selected.decimal_odds,
        event_probability=selected.event_probability,
        evaluation_time=selected.decision_evaluation_time,
    )
    opportunity = dataclasses.replace(
        selected,
        opportunity_id=trial._sha(identity_payload),
        fixture=fixture,
    )
    return trial.ResearchFixtureDecision(
        fixture=fixture,
        evaluation_time=base.evaluation_time,
        latest_history_sha256=base.latest_history_sha256,
        current_mapping_rebind_sha256=(
            base.current_mapping_rebind_sha256
        ),
        status="SELECTED",
        selected_opportunity_id=opportunity.opportunity_id,
        opportunities=(opportunity,),
        decision_reasons=(
            "RESEARCH_SHADOW_TOTAL_GOALS_ROBUST_VALUE_SELECTED",
        ),
    )


def test_frozen_market_family_cap_preserves_shortfall_instead_of_padding(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_prefix, evaluation, decision = _decision(
        tmp_path,
        monkeypatch,
    )
    assert decision.selected is not None
    decisions = tuple(
        _clone_selected_decision(decision, index=index)
        for index in range(20)
    )
    portfolio = trial.optimize_research_shadow_portfolio(
        decisions,
        target_size=20,
        evaluation_time=evaluation,
    )
    assert len(portfolio.selected_legs) == 10
    assert len(portfolio.reserve_legs) == 10
    assert portfolio.shortfall == 10
    assert portfolio.fulfilled is False
    assert (
        portfolio.field_trial_status
        == "RESEARCH_QUALIFIED_WITH_SHORTFALL"
    )
    assert portfolio.caps["market_family"] == 10
    assert portfolio.to_dict()["wager_placed"] is False
    assert portfolio.authority["production_selection"] is False


def test_transport_intent_is_semantic_and_contains_no_native_ids_or_odds(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_prefix, decision = _decision(tmp_path, monkeypatch)
    selected = decision.selected
    assert selected is not None

    intent = selected.semantic_intent()
    assert set(intent) == {
        "eventId",
        "homeTeamName",
        "awayTeamName",
        "marketName",
        "outcomeName",
        "specifier",
    }
    assert not {"marketId", "outcomeId", "odds"} & set(intent)
    assert selected.expected_provider_native_identity() == {
        "eventId": selected.fixture.event_id,
        "marketId": selected.provider_market_id,
        "outcomeId": selected.provider_outcome_id,
        "specifier": selected.provider_specifier,
    }
