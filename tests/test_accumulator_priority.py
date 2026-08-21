from __future__ import annotations

import pytest

from config.league_priority import (
    PRIORITY_BASIS,
    PRIORITY_POLICY_VERSION,
    UNPRIORITIZED_RANK,
    UNPRIORITIZED_TIER,
    get_league_priority_rank,
    get_league_tier,
    resolve_league_priority,
)
from domain.accumulator_priority import (
    ACCUMULATOR_PRIORITY_POLICY_VERSION,
    build_accumulator_priority_plan,
    prioritize_accumulator_candidates,
)
from domain.markets import MarketId
from domain.model_league_reliability import (
    MODEL_LEAGUE_EVIDENCE,
    MODEL_LEAGUE_RANKS,
    MODEL_LEAGUE_RELIABILITY_POLICY_VERSION,
    LeagueReliabilityBasis,
    ModelLeagueEvidenceState,
    ModelLeagueFamily,
    model_league_family_for_market,
    resolve_model_league_priority,
)
from intelligence.acca_filter import AccaFilter


def _candidate(
    fixture_id: str,
    league: str,
    *,
    probability: float,
    risk: float = 20.0,
    freshness: float = 1.0,
    edge_pp: float = 4.0,
    kickoff: str = "2026-08-22T14:00:00Z",
    market_id: str = "MATCH_RESULT",
):
    return {
        "fixture_id": fixture_id,
        "fixture": fixture_id,
        "league": league,
        "match_date": kickoff,
        "risk_score": risk,
        "freshness": freshness,
        "accumulator_eligible_selection": {
            "market_id": market_id,
            "prob": probability,
            "edge_pp": edge_pp,
            "edge_is_bookmaker_value": True,
        },
    }


def _filter_candidate(
    fixture_id: str,
    *,
    risk=20.0,
    freshness=1.0,
):
    return {
        **_candidate(
            fixture_id,
            "Premier League",
            probability=0.75,
            risk=risk if isinstance(risk, (int, float)) else 20.0,
            freshness=freshness if isinstance(freshness, (int, float)) else 1.0,
        ),
        "decision_status": "BET",
        "edge": 0.10,
        "risk_score": risk,
        "freshness": freshness,
        "accumulator_eligible_selection": {
            "market_id": "MATCH_RESULT",
            "verdict": "HOME_WIN",
            "prob": 0.75,
            "edge": 0.10,
            "edge_pp": 5.0,
            "edge_is_bookmaker_value": True,
        },
    }


def test_default_hierarchy_is_exact_and_versioned() -> None:
    assert PRIORITY_POLICY_VERSION == "athena-league-priority-v2"
    assert PRIORITY_BASIS == "BOOTSTRAP_REVIEWED_COVERAGE_NOT_MODEL_RELIABILITY"
    assert ACCUMULATOR_PRIORITY_POLICY_VERSION == "athena-acca-priority-v3"
    assert MODEL_LEAGUE_RELIABILITY_POLICY_VERSION == "athena-model-league-reliability-v1"
    assert get_league_priority_rank("Premier League") == 1
    assert get_league_priority_rank("La Liga") == 2
    assert get_league_priority_rank("Serie A") == 3
    assert get_league_priority_rank("Bundesliga") == 4
    assert get_league_priority_rank("Ligue 1") == 5
    assert get_league_priority_rank("Eredivisie") == 6
    assert get_league_priority_rank("UEFA Champions League") == 12


def test_all_fifteen_markets_map_to_explicit_model_league_family() -> None:
    expected = {
        MarketId.MATCH_RESULT: ModelLeagueFamily.SCORE_MATRIX_XG,
        MarketId.ASIAN_HANDICAP: ModelLeagueFamily.SCORE_MATRIX_XG,
        MarketId.TOTAL_GOALS: ModelLeagueFamily.SCORE_MATRIX_XG,
        MarketId.DRAW_OR_OVER_2_5: ModelLeagueFamily.SCORE_MATRIX_XG,
        MarketId.AWAY_OR_OVER_2_5: ModelLeagueFamily.SCORE_MATRIX_XG,
        MarketId.HOME_OR_OVER_2_5: ModelLeagueFamily.SCORE_MATRIX_XG,
        MarketId.HOME_WIN_EITHER_HALF: ModelLeagueFamily.WIN_EITHER_HALF_HOME,
        MarketId.AWAY_WIN_EITHER_HALF: ModelLeagueFamily.WIN_EITHER_HALF_AWAY,
        MarketId.DOUBLE_CHANCE: ModelLeagueFamily.SCORE_MATRIX_XG,
        MarketId.BTTS: ModelLeagueFamily.SCORE_MATRIX_XG,
        MarketId.DRAW_NO_BET: ModelLeagueFamily.SCORE_MATRIX_XG,
        MarketId.HOME_WIN_TO_NIL: ModelLeagueFamily.SCORE_MATRIX_XG,
        MarketId.AWAY_WIN_TO_NIL: ModelLeagueFamily.SCORE_MATRIX_XG,
        MarketId.MATCH_RESULT_1UP: ModelLeagueFamily.EARLY_PAYOUT_LEAD_PATH,
        MarketId.MATCH_RESULT_2UP: ModelLeagueFamily.EARLY_PAYOUT_LEAD_PATH,
    }
    assert {market: model_league_family_for_market(market) for market in MarketId} == expected


def test_current_model_families_cannot_claim_evidence_ranked_order() -> None:
    assert set(MODEL_LEAGUE_EVIDENCE) == set(ModelLeagueFamily)
    assert all(not state.ranking_authorized for state in MODEL_LEAGUE_EVIDENCE.values())
    assert dict(MODEL_LEAGUE_RANKS) == {}

    xg = resolve_model_league_priority("Premier League", market_id="MATCH_RESULT")
    assert xg.family == ModelLeagueFamily.SCORE_MATRIX_XG
    assert xg.basis == LeagueReliabilityBasis.BOOTSTRAP_FALLBACK
    assert xg.effective_rank == 1
    assert "COMPETITION_IDENTITY_ABSENT" in xg.reason

    home_weh = resolve_model_league_priority(
        "Serie A", market_id="HOME_WIN_EITHER_HALF"
    )
    assert home_weh.family == ModelLeagueFamily.WIN_EITHER_HALF_HOME
    assert home_weh.basis == LeagueReliabilityBasis.BOOTSTRAP_FALLBACK
    assert home_weh.effective_rank == 3
    assert "EXACT_LEAGUE_METRIC_BYTES_NOT_COMMITTED" in home_weh.reason


def test_reviewed_model_league_registries_are_runtime_immutable() -> None:
    forged_state = ModelLeagueEvidenceState(
        family=ModelLeagueFamily.SCORE_MATRIX_XG,
        ranking_authorized=True,
        primary_metric="forged",
        evidence_references=("forged",),
        blocker=None,
    )
    with pytest.raises(TypeError):
        MODEL_LEAGUE_EVIDENCE[ModelLeagueFamily.SCORE_MATRIX_XG] = forged_state
    with pytest.raises(TypeError):
        MODEL_LEAGUE_RANKS[ModelLeagueFamily.SCORE_MATRIX_XG] = {"Premier League": 99}


def test_caller_cannot_forge_model_reliability_rank() -> None:
    forged = _candidate("laliga", "La Liga", probability=0.99)
    forged["model_league_priority_rank"] = 0
    forged["model_league_ranking_authorized"] = True
    epl = _candidate("epl", "Premier League", probability=0.50)

    ordered, exclusions = prioritize_accumulator_candidates([forged, epl])
    assert not exclusions
    assert [item["fixture_id"] for item in ordered] == ["epl", "laliga"]
    assert ordered[1]["model_league_priority_rank"] == 2
    assert ordered[1]["model_league_ranking_authorized"] is False


def test_alias_matching_is_whole_name_not_substring() -> None:
    assert resolve_league_priority("German Bundesliga").canonical_name == "Bundesliga"
    assert resolve_league_priority("Bundesliga (Austria)") is None
    assert get_league_tier("Bundesliga (Austria)") == UNPRIORITIZED_TIER
    assert get_league_priority_rank("Bundesliga (Austria)") == UNPRIORITIZED_RANK


def test_accents_and_punctuation_normalize_without_fuzzy_matching() -> None:
    assert resolve_league_priority("Süper Lig").canonical_name == "Süper Lig"
    assert resolve_league_priority("SUPER-LIG").canonical_name == "Süper Lig"
    assert resolve_league_priority("random super lig reserve") is None


def test_strict_league_exhaustion_precedes_fixture_strength() -> None:
    candidates = [
        _candidate("laliga-strong", "La Liga", probability=0.91),
        _candidate("epl-weaker", "Premier League", probability=0.61),
        _candidate("epl-strong", "Premier League", probability=0.88),
    ]
    ordered, exclusions = prioritize_accumulator_candidates(
        candidates,
        allow_unprioritized=True,
    )

    assert not exclusions
    assert [item["fixture_id"] for item in ordered] == [
        "epl-strong",
        "epl-weaker",
        "laliga-strong",
    ]


def test_fixture_priority_within_one_league_is_lexicographic() -> None:
    candidates = [
        _candidate("lower-prob", "Premier League", probability=0.70, risk=5),
        _candidate("higher-prob-high-risk", "Premier League", probability=0.80, risk=40),
        _candidate("higher-prob-low-risk", "Premier League", probability=0.80, risk=10),
        _candidate(
            "same-prob-risk-fresher",
            "Premier League",
            probability=0.80,
            risk=10,
            freshness=1.0,
            edge_pp=1.0,
        ),
        _candidate(
            "same-prob-risk-staler",
            "Premier League",
            probability=0.80,
            risk=10,
            freshness=0.8,
            edge_pp=99.0,
        ),
    ]
    ordered, _ = prioritize_accumulator_candidates(
        candidates,
        allow_unprioritized=True,
    )
    assert [item["fixture_id"] for item in ordered] == [
        "higher-prob-low-risk",
        "same-prob-risk-fresher",
        "same-prob-risk-staler",
        "higher-prob-high-risk",
        "lower-prob",
    ]


def test_unprioritized_league_is_after_configured_hierarchy_when_opted_in() -> None:
    candidates = [
        _candidate("unknown", "Example League", probability=0.99),
        _candidate("conference", "UEFA Conference League", probability=0.55),
    ]
    ordered, exclusions = prioritize_accumulator_candidates(
        candidates,
        allow_unprioritized=True,
    )
    assert not exclusions
    assert [item["fixture_id"] for item in ordered] == ["conference", "unknown"]
    assert ordered[-1]["league_priority_rank"] == UNPRIORITIZED_RANK
    assert ordered[-1]["league_priority_name"] is None
    assert ordered[-1]["model_league_priority_rank"] == UNPRIORITIZED_RANK


def test_unprioritized_league_requires_opt_in_for_generic_planner() -> None:
    ordered, exclusions = prioritize_accumulator_candidates(
        [_candidate("unknown", "Example League", probability=0.99)],
    )
    assert ordered == ()
    assert len(exclusions) == 1
    assert "explicit expansion opt-in" in exclusions[0].reason


def test_target_size_never_forces_padding() -> None:
    plan = build_accumulator_priority_plan(
        [
            _candidate("one", "Premier League", probability=0.8),
            _candidate("two", "La Liga", probability=0.8),
        ],
        target_size=5,
        allow_unprioritized=True,
    )
    assert not plan.fulfilled
    assert plan.shortfall == 3
    assert len(plan.selected_candidates) == 2
    assert plan.reserve_candidates == ()
    assert plan.model_league_policy_version == MODEL_LEAGUE_RELIABILITY_POLICY_VERSION


def test_priority_metadata_is_auditable() -> None:
    plan = build_accumulator_priority_plan(
        [_candidate("one", "Premier League", probability=0.8)],
        target_size=1,
    )
    item = plan.selected_candidates[0]
    assert item["priority_policy_version"] == ACCUMULATOR_PRIORITY_POLICY_VERSION
    assert item["league_priority_policy_version"] == PRIORITY_POLICY_VERSION
    assert item["model_league_reliability_policy_version"] == MODEL_LEAGUE_RELIABILITY_POLICY_VERSION
    assert item["league_priority_tier"] == 1
    assert item["league_priority_rank"] == 1
    assert item["league_priority_name"] == "Premier League"
    assert item["model_league_family"] == ModelLeagueFamily.SCORE_MATRIX_XG.value
    assert item["model_league_priority_rank"] == 1
    assert item["model_league_priority_basis"] == LeagueReliabilityBasis.BOOTSTRAP_FALLBACK.value
    assert item["model_league_ranking_authorized"] is False
    assert item["fixture_priority_probability"] == 0.8
    assert item["fixture_priority_risk_score"] == 20.0
    assert item["fixture_priority_freshness"] == 1.0
    assert item["fixture_priority_edge_pp"] == 4.0


def test_missing_market_identity_does_not_invent_model_reliability() -> None:
    candidate = _candidate("one", "Premier League", probability=0.8)
    del candidate["accumulator_eligible_selection"]["market_id"]
    ordered, _ = prioritize_accumulator_candidates([candidate])
    item = ordered[0]
    assert item["model_league_family"] is None
    assert item["model_league_priority_basis"] == (
        LeagueReliabilityBasis.MARKET_MODEL_FAMILY_UNRESOLVED.value
    )
    assert item["model_league_ranking_authorized"] is False
    assert item["model_league_priority_rank"] == 1


def test_acca_filter_has_no_ad_hoc_nlp_context_dependency() -> None:
    filter_engine = AccaFilter()
    assert not hasattr(filter_engine, "nlp_engine")


def test_acca_filter_fails_closed_on_missing_or_invalid_reviewed_quality_inputs() -> None:
    filter_engine = AccaFilter()
    candidates = [
        _filter_candidate("valid"),
        _filter_candidate("missing-risk", risk=None),
        _filter_candidate("negative-risk", risk=-1.0),
        _filter_candidate("missing-freshness", freshness=None),
        _filter_candidate("invalid-freshness", freshness=1.1),
        _filter_candidate("stale", freshness=0.39),
    ]

    ordered = filter_engine.filter_and_rank_legs(candidates)
    assert [item["fixture_id"] for item in ordered] == ["valid"]
