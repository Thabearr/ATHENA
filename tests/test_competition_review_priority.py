from __future__ import annotations

from config.competition_review_priority import (
    COMPETITION_REVIEW_PRIORITY_BASIS,
    COMPETITION_REVIEW_PRIORITY_POLICY_VERSION,
    CompetitionKind,
    resolve_source_competition_review_priority,
)
from domain.accumulator_priority import prioritize_accumulator_candidates
from domain.model_league_reliability import LeagueReliabilityBasis


def _candidate(
    fixture_id: str,
    *,
    league: str,
    ccode: str,
    source_competition_name: str,
    probability: float = 0.75,
):
    return {
        "fixture_id": fixture_id,
        "fixture": fixture_id,
        "league": league,
        "source_competition_ccode": ccode,
        "source_competition_name": source_competition_name,
        "match_date": "2026-08-22T14:00:00Z",
        "risk_score": 20.0,
        "freshness": 1.0,
        "accumulator_eligible_selection": {
            "market_id": "MATCH_RESULT",
            "prob": probability,
            "edge_pp": 4.0,
            "edge_is_bookmaker_value": True,
        },
    }


def test_registry_is_explicitly_review_order_not_model_reliability():
    assert COMPETITION_REVIEW_PRIORITY_POLICY_VERSION == (
        "athena-competition-review-priority-v1"
    )
    assert COMPETITION_REVIEW_PRIORITY_BASIS == (
        "BOOTSTRAP_REVIEW_ORDER_NOT_MODEL_RELIABILITY"
    )


def test_dfb_pokal_is_ranked_before_eredivisie_belgium_scotland_turkey_and_greece():
    dfb = resolve_source_competition_review_priority("GER", "DFB Pokal")
    eredivisie = resolve_source_competition_review_priority("NED", "Eredivisie")
    belgium = resolve_source_competition_review_priority("BEL", "Belgian Pro League")
    scotland = resolve_source_competition_review_priority("SCO", "Premiership")
    turkey = resolve_source_competition_review_priority("TUR", "Super Lig")
    greece = resolve_source_competition_review_priority("GRE", "Super League")

    assert dfb is not None
    assert dfb.canonical_name == "DFB-Pokal"
    assert dfb.kind == CompetitionKind.DOMESTIC_CUP
    assert dfb.rank == 6
    assert [item.rank for item in (eredivisie, belgium, scotland, turkey, greece)] == [
        7,
        9,
        10,
        11,
        12,
    ]


def test_source_identity_blocks_same_name_foreign_leagues():
    assert resolve_source_competition_review_priority("ENG", "Premier League") is not None
    assert resolve_source_competition_review_priority("BLR", "Premier League") is None
    assert resolve_source_competition_review_priority("ITA", "Serie A") is not None
    assert resolve_source_competition_review_priority("ECU", "Serie A") is None
    assert resolve_source_competition_review_priority("GER", "Bundesliga") is not None
    assert resolve_source_competition_review_priority("AUT", "Bundesliga") is None


def test_accumulator_planner_uses_source_competition_review_order_before_fixture_strength():
    candidates = [
        _candidate(
            "belgium-very-strong",
            league="Belgian Pro League",
            ccode="BEL",
            source_competition_name="Belgian Pro League",
            probability=0.95,
        ),
        _candidate(
            "dfb-moderate",
            league="DFB Pokal",
            ccode="GER",
            source_competition_name="DFB Pokal",
            probability=0.70,
        ),
        _candidate(
            "eredivisie-strong",
            league="Eredivisie",
            ccode="NED",
            source_competition_name="Eredivisie",
            probability=0.90,
        ),
    ]
    ordered, exclusions = prioritize_accumulator_candidates(candidates)
    assert not exclusions
    assert [item["fixture_id"] for item in ordered] == [
        "dfb-moderate",
        "eredivisie-strong",
        "belgium-very-strong",
    ]
    dfb = ordered[0]
    assert dfb["competition_review_priority_name"] == "DFB-Pokal"
    assert dfb["competition_review_priority_rank"] == 6
    assert dfb["competition_review_priority_basis"] == (
        "SOURCE_QUALIFIED_COMPETITION_REVIEW_PRIORITY"
    )
    assert dfb["model_league_priority_rank"] == 999
    assert dfb["model_league_priority_basis"] == LeagueReliabilityBasis.BOOTSTRAP_FALLBACK.value
    assert dfb["model_league_ranking_authorized"] is False


def test_source_identity_present_never_falls_back_to_ambiguous_bare_league_name():
    foreign = _candidate(
        "belarus-premier",
        league="Premier League",
        ccode="BLR",
        source_competition_name="Premier League",
        probability=0.99,
    )
    ordered, exclusions = prioritize_accumulator_candidates([foreign])
    assert ordered == ()
    assert len(exclusions) == 1
    assert "source competition identity" in exclusions[0].reason


def test_unreviewed_cup_needs_explicit_expansion_even_if_label_looks_important():
    super_cup = _candidate(
        "german-super-cup",
        league="Super Cup",
        ccode="GER",
        source_competition_name="Super Cup",
        probability=0.99,
    )
    ordered, exclusions = prioritize_accumulator_candidates([super_cup])
    assert ordered == ()
    assert len(exclusions) == 1

    ordered, exclusions = prioritize_accumulator_candidates(
        [super_cup], allow_unprioritized=True
    )
    assert not exclusions
    assert ordered[0]["competition_review_priority_rank"] == 999
    assert ordered[0]["competition_review_priority_name"] is None
