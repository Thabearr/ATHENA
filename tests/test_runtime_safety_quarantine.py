from domain.markets import DecisionStatus
from services.analysis_pipeline import (
    LEGACY_RUNTIME_AUTHORIZATION_STATE,
    LEGACY_RUNTIME_BET_BLOCK_REASON,
    AnalysisPipeline,
    apply_runtime_authorization,
)
from services.betting_service import (
    BOOKMAKER_RESOLUTION_BLOCK_STATE,
    BettingService,
)


def _bet_analysis() -> dict:
    return {
        "decision_status": DecisionStatus.BET.value,
        "recommended_analytical_verdict": "DC_1X",
        "kelly_stake_pct": 0.75,
        "accumulator_eligible_selection": {
            "verdict": "DC_1X",
            "bookmaker_odds": 1.5,
        },
        "reasoning_verdicts": [
            {
                "label": "Home or Draw",
                "status": DecisionStatus.BET.value,
            }
        ],
        "no_bet_reasons": [],
        "evidence_report": {
            "final_decision": DecisionStatus.BET.value,
            "decision_reasons": ["Synthetic legacy path cleared local gates."],
        },
    }


def test_legacy_bet_is_downgraded_without_erasing_analysis() -> None:
    original = _bet_analysis()
    safe = apply_runtime_authorization(original)

    assert original["decision_status"] == DecisionStatus.BET.value
    assert original["accumulator_eligible_selection"] is not None
    assert original["kelly_stake_pct"] == 0.75

    assert (
        safe["legacy_decision_status_before_runtime_gate"]
        == DecisionStatus.BET.value
    )
    assert safe["legacy_kelly_stake_pct_before_runtime_gate"] == 0.75
    assert safe["decision_status"] == DecisionStatus.ANALYTICAL_CANDIDATE.value
    assert safe["accumulator_eligible_selection"] is None
    assert safe["kelly_stake_pct"] is None
    assert safe["runtime_authorization_state"] == LEGACY_RUNTIME_AUTHORIZATION_STATE
    assert safe["runtime_authorization_reasons"] == [
        LEGACY_RUNTIME_BET_BLOCK_REASON
    ]
    assert LEGACY_RUNTIME_BET_BLOCK_REASON in safe["no_bet_reasons"]
    assert (
        safe["reasoning_verdicts"][0]["status"]
        == DecisionStatus.ANALYTICAL_CANDIDATE.value
    )
    assert (
        safe["evidence_report"]["legacy_decision_status_before_runtime_gate"]
        == DecisionStatus.BET.value
    )
    assert (
        safe["evidence_report"]["final_decision"]
        == DecisionStatus.ANALYTICAL_CANDIDATE.value
    )
    assert (
        safe["evidence_report"]["runtime_authorization_state"]
        == LEGACY_RUNTIME_AUTHORIZATION_STATE
    )


def test_non_bet_analysis_is_not_rewritten() -> None:
    analysis = {
        "decision_status": DecisionStatus.NO_BET.value,
        "accumulator_eligible_selection": None,
    }
    assert apply_runtime_authorization(analysis) == analysis


def test_pipeline_applies_runtime_gate_before_export() -> None:
    class StubAnalyst:
        def compile_master_fixture_prediction(self, fixture_context):
            assert fixture_context["fixture_id"] == 123
            return _bet_analysis()

    pipeline = object.__new__(AnalysisPipeline)
    pipeline.analyst = StubAnalyst()
    pipeline.form_svc = None
    pipeline._resolve_team_id = lambda team_name: 1 if team_name == "Home" else 2

    rows = pipeline.run_pipeline_snapshot(
        override_fixtures=[
            {
                "fixture_id": 123,
                "league": "Premier League",
                "home_team": "Home",
                "away_team": "Away",
                "match_date": "2026-08-22T15:00:00Z",
                "data_source": "fotmob",
            }
        ]
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["decision_status"] == DecisionStatus.ANALYTICAL_CANDIDATE.value
    assert (
        row["legacy_decision_status_before_runtime_gate"]
        == DecisionStatus.BET.value
    )
    assert row["legacy_kelly_stake_pct_before_runtime_gate"] == 0.75
    assert row["kelly_stake_pct"] is None
    assert row["accumulator_eligible_selection"] is None
    assert row["runtime_authorization_state"] == LEGACY_RUNTIME_AUTHORIZATION_STATE


def test_sportybet_resolver_never_returns_synthetic_success() -> None:
    result = BettingService().resolve_sportybet("ABC123")

    assert result["success"] is False
    assert result["bookmaker"] == "SportyBet"
    assert result["code"] == "ABC123"
    assert result["state"] == BOOKMAKER_RESOLUTION_BLOCK_STATE
    assert result["legs"] == []
    assert result["athena_approval"] is None
    assert "fabricate" in result["error"].lower()


def test_athenizer_vetting_fails_closed_without_reviewed_resolver() -> None:
    result = BettingService().vet_code("sportybet", "ABC123")

    assert result["success"] is False
    assert result["legs"] == []
    assert result["athena_approval"] is None
    assert result["state"] == BOOKMAKER_RESOLUTION_BLOCK_STATE


def test_blocked_slips_cannot_be_split_or_merged() -> None:
    service = BettingService()
    blocked = service.vet_code("sportybet", "ABC123")

    assert service.split_slip(blocked, 2) == []
    merged = service.merge_slips([blocked, blocked])
    assert merged["success"] is False
    assert merged["legs"] == []
    assert merged["total_estimated_odds"] == 0.0
