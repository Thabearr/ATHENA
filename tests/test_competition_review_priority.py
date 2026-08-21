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


def test_major_top_five_domestic_cups_share_one_review_tier():
    expected = {
        ("ENG", "FA Cup"): "FA Cup",
        ("ESP", "Copa del Rey"): "Copa del Rey",
        ("ITA", "Coppa Italia"): "Coppa Italia",
        ("GER", "DFB Pokal"): "DFB-Pokal",
        ("FRA", "Coupe de France"): "Coupe de France",
    }
    resolved = {
        key: resolve_source_competition_review_priority(*key)
        for key in expected
    }
    assert all(entry is not None for entry in resolved.values())
    assert {key: entry.canonical_name for key, entry in resolved.items()} == expected
    assert {entry.kind for entry in resolved.values()} == {CompetitionKind.DOMESTIC_CUP}
    assert {entry.tier for entry in resolved.values()} == {3}
    assert {entry.rank for entry in resolved.values()} == {9}


def test_portugal_turkey_and_eredivisie_rank_above_major_cups_which_rank_above_belgium():
    portugal = resolve_source_competition_review_priority("POR", "Liga Portugal")
    turkey = resolve_source_competition_review_priority("TUR", "Super Lig")
    eredivisie = resolve_source_competition_review_priority("NED", "Eredivisie")
    dfb = resolve_source_competition_review_priority("GER", "DFB Pokal")
    belgium = resolve_source_competition_review_priority("BEL", "Belgian Pro League")
    scotland = resolve_source_competition_review_priority("SCO", "Premiership")
    greece = resolve_source_competition_review_priority("GRE", "Super League")

    assert [item.rank for item in (portugal, turkey, eredivisie, dfb, belgium, scotland, greece)] == [
        6,
        7,
        8,
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


def test_accumulator_planner_uses_review_band_before_fixture_strength():
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
        _candidate(
            "turkey-weaker",
            league="Süper Lig",
            ccode="TUR",
            source_competition_name="Super Lig",
            probability=0.62,
        ),
        _candidate(
            "portugal-weaker",
            league="Primeira Liga",
            ccode="POR",
            source_competition_name="Liga Portugal",
            probability=0.60,
        ),
    ]
    ordered, exclusions = prioritize_accumulator_candidates(candidates)
    assert not exclusions
    assert [item["fixture_id"] for item in ordered] == [
        "portugal-weaker",
        "turkey-weaker",
        "eredivisie-strong",
        "dfb-moderate",
        "belgium-very-strong",
    ]
    dfb = next(item for item in ordered if item["fixture_id"] == "dfb-moderate")
    assert dfb["competition_review_priority_name"] == "DFB-Pokal"
    assert dfb["competition_review_priority_rank"] == 9
    assert dfb["competition_review_priority_basis"] == (
        "SOURCE_QUALIFIED_COMPETITION_REVIEW_PRIORITY"
    )
    assert dfb["model_league_priority_rank"] == 999
    assert dfb["model_league_priority_basis"] == LeagueReliabilityBasis.BOOTSTRAP_FALLBACK.value
    assert dfb["model_league_ranking_authorized"] is False


def test_same_rank_major_cups_are_ordered_by_fixture_quality_not_arbitrary_cup_prestige():
    candidates = [
        _candidate(
            "fa-lower",
            league="FA Cup",
            ccode="ENG",
            source_competition_name="FA Cup",
            probability=0.72,
        ),
        _candidate(
            "copa-higher",
            league="Copa del Rey",
            ccode="ESP",
            source_competition_name="Copa del Rey",
            probability=0.81,
        ),
        _candidate(
            "dfb-mid",
            league="DFB Pokal",
            ccode="GER",
            source_competition_name="DFB Pokal",
            probability=0.77,
        ),
    ]
    ordered, exclusions = prioritize_accumulator_candidates(candidates)
    assert not exclusions
    assert [item["fixture_id"] for item in ordered] == [
        "copa-higher",
        "dfb-mid",
        "fa-lower",
    ]
    assert {item["competition_review_priority_rank"] for item in ordered} == {9}


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


def test_unreviewed_secondary_or_super_cup_needs_explicit_expansion():
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
