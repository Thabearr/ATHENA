from __future__ import annotations

import pytest

from config.competition_review_priority import (
    COMPETITION_REVIEW_PRIORITY_BASIS,
    COMPETITION_REVIEW_PRIORITY_POLICY_VERSION,
    CompetitionKind,
    CompetitionScope,
    apply_stage_modifier,
    derive_non_big_five_domestic_cup_tier,
    resolve_canonical_competition_review_priority,
    resolve_source_competition_review_priority,
)
from domain.accumulator_priority import prioritize_accumulator_candidates
from domain.model_league_reliability import LeagueReliabilityBasis


def _candidate(
    fixture_id: str,
    *,
    league: str,
    probability: float = 0.75,
    ccode: str | None = None,
    source_competition_name: str | None = None,
    competition_scope: str = "CLUB",
):
    candidate = {
        "fixture_id": fixture_id,
        "fixture": fixture_id,
        "league": league,
        "competition_scope": competition_scope,
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
    if ccode is not None or source_competition_name is not None:
        candidate["source_competition_ccode"] = ccode
        candidate["source_competition_name"] = source_competition_name
    return candidate


def test_registry_is_exact_pdf_v1_consideration_order_not_bet_authority():
    assert COMPETITION_REVIEW_PRIORITY_POLICY_VERSION == (
        "athena-competition-review-priority-v2"
    )
    assert COMPETITION_REVIEW_PRIORITY_BASIS == (
        "ATHENA_FOOTBALL_COMPETITION_HIERARCHY_V1"
    )


def test_club_master_order_matches_pdf_bands():
    expected = [
        ("UEFA Champions League", 1, "S", 1, 100),
        ("UEFA Europa League", 1, "S", 2, 100),
        ("UEFA Conference League", 1, "S", 3, 100),
        ("Premier League", 2, "A", 10, 88),
        ("La Liga", 2, "A", 11, 86),
        ("Serie A", 2, "A", 12, 84),
        ("Bundesliga", 2, "A", 13, 82),
        ("Ligue 1", 2, "A", 14, 80),
        ("FA Cup", 3, "B", 20, 78),
        ("EFL Cup", 3, "B", 20, 78),
        ("Copa del Rey", 3, "B", 20, 78),
        ("Coppa Italia", 3, "B", 20, 78),
        ("DFB-Pokal", 3, "B", 20, 78),
        ("Coupe de France", 3, "B", 20, 78),
        ("Eredivisie", 4, "C1", 30, 76),
        ("Primeira Liga", 4, "C1", 31, 74),
        ("Süper Lig", 4, "C1", 32, 72),
        ("Belgian Pro League", 4, "C1", 33, 70),
        ("Eliteserien", 5, "C2", 40, 68),
        ("Danish Superliga", 5, "C2", 41, 66),
        ("Allsvenskan", 5, "C2", 42, 64),
        ("Swiss Super League", 5, "C2", 43, 62),
        ("Greek Super League", 5, "C2", 44, 60),
        ("EFL Championship", 6, "D", 50, 58),
        ("Major League Soccer", 7, "E", 60, 54),
        ("Saudi Pro League", 8, "F", 70, 50),
        ("Scottish Premiership", 9, "G", 80, 45),
    ]
    actual = []
    for name, *_ in expected:
        entry = resolve_canonical_competition_review_priority(name)
        assert entry is not None
        actual.append(
            (
                entry.canonical_name,
                entry.tier,
                entry.priority_band,
                entry.rank,
                entry.base_score,
            )
        )
    assert actual == expected


def test_exact_fotmob_source_pairs_cover_uefa_and_domestic_hierarchy():
    expected = {
        ("INT", "Champions League"): "UEFA Champions League",
        ("INT", "Europa League"): "UEFA Europa League",
        ("INT", "Conference League"): "UEFA Conference League",
        ("ENG", "Premier League"): "Premier League",
        ("ENG", "FA Cup"): "FA Cup",
        ("ENG", "League Cup"): "EFL Cup",
        ("NED", "Eredivisie"): "Eredivisie",
        ("NOR", "Eliteserien"): "Eliteserien",
        ("ENG", "Championship"): "EFL Championship",
        ("USA", "Major League Soccer"): "Major League Soccer",
        ("KSA", "Saudi Pro League"): "Saudi Pro League",
        ("SCO", "Premiership"): "Scottish Premiership",
    }
    for key, canonical in expected.items():
        entry = resolve_source_competition_review_priority(*key)
        assert entry is not None
        assert entry.canonical_name == canonical


def test_source_identity_blocks_same_name_foreign_leagues():
    assert resolve_source_competition_review_priority("ENG", "Premier League") is not None
    assert resolve_source_competition_review_priority("BLR", "Premier League") is None
    assert resolve_source_competition_review_priority("ITA", "Serie A") is not None
    assert resolve_source_competition_review_priority("ECU", "Serie A") is None
    assert resolve_source_competition_review_priority("GER", "Bundesliga") is not None
    assert resolve_source_competition_review_priority("AUT", "Bundesliga") is None


def test_accumulator_planner_exhausts_pdf_bands_before_fixture_strength():
    candidates = [
        _candidate(
            "scotland-very-strong",
            league="Scottish Premiership",
            ccode="SCO",
            source_competition_name="Premiership",
            probability=0.99,
        ),
        _candidate(
            "belgium-strong",
            league="Belgian Pro League",
            ccode="BEL",
            source_competition_name="Belgian Pro League",
            probability=0.95,
        ),
        _candidate(
            "dfb-moderate",
            league="DFB-Pokal",
            ccode="GER",
            source_competition_name="DFB Pokal",
            probability=0.70,
        ),
        _candidate(
            "epl-weaker",
            league="Premier League",
            ccode="ENG",
            source_competition_name="Premier League",
            probability=0.60,
        ),
        _candidate(
            "ucl-weakest",
            league="UEFA Champions League",
            ccode="INT",
            source_competition_name="Champions League",
            probability=0.55,
        ),
    ]
    ordered, exclusions = prioritize_accumulator_candidates(candidates)
    assert not exclusions
    assert [item["fixture_id"] for item in ordered] == [
        "ucl-weakest",
        "epl-weaker",
        "dfb-moderate",
        "belgium-strong",
        "scotland-very-strong",
    ]
    assert [item["competition_review_priority_band"] for item in ordered] == [
        "S",
        "A",
        "B",
        "C1",
        "G",
    ]


def test_same_rank_big_five_cups_are_ordered_by_fixture_quality():
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
    assert {item["competition_review_priority_rank"] for item in ordered} == {20}


def test_stage_modifiers_follow_pdf_and_require_reviewed_stage_evidence():
    cup = resolve_canonical_competition_review_priority("FA Cup")
    assert cup is not None
    assert cup.kind is CompetitionKind.DOMESTIC_CUP

    ignored = apply_stage_modifier(cup, stage="Final", stage_evidence_reviewed=False)
    assert (ignored.effective_tier, ignored.effective_band, ignored.band_delta) == (3, "B", 0)

    final = apply_stage_modifier(cup, stage="Final", stage_evidence_reviewed=True)
    assert (final.effective_tier, final.effective_band, final.band_delta) == (2, "A", 1)

    qf_plain = apply_stage_modifier(cup, stage="Quarter-final", stage_evidence_reviewed=True)
    assert (qf_plain.effective_tier, qf_plain.band_delta) == (3, 0)

    qf_strong = apply_stage_modifier(
        cup,
        stage="Quarter-final",
        stage_evidence_reviewed=True,
        both_sides_strong_lineups_expected=True,
    )
    assert (qf_strong.effective_tier, qf_strong.effective_band) == (2, "A")

    early_rotation = apply_stage_modifier(
        cup,
        stage="Third round",
        stage_evidence_reviewed=True,
        top_flight_rotation_expected=True,
    )
    assert (early_rotation.effective_tier, early_rotation.effective_band) == (4, "C1")

    second_leg = apply_stage_modifier(
        resolve_canonical_competition_review_priority("UEFA Champions League"),
        stage="Quarter-final",
        stage_evidence_reviewed=True,
        two_leg_second_leg=True,
    )
    assert second_leg.confidence_focus is True


def test_non_big_five_domestic_cup_rule_is_parent_league_minus_one_band():
    eredivisie = resolve_canonical_competition_review_priority("Eredivisie")
    assert eredivisie is not None
    assert derive_non_big_five_domestic_cup_tier(eredivisie) == 5
    assert derive_non_big_five_domestic_cup_tier(eredivisie, later_round=True) == 4


def test_international_hierarchy_is_separate_and_ordered():
    world_cup = resolve_canonical_competition_review_priority(
        "World Cup", scope=CompetitionScope.INTERNATIONAL
    )
    euro = resolve_canonical_competition_review_priority(
        "Euros", scope=CompetitionScope.INTERNATIONAL
    )
    qualifier = resolve_canonical_competition_review_priority(
        "World Cup qualifiers", scope=CompetitionScope.INTERNATIONAL
    )
    friendly = resolve_canonical_competition_review_priority(
        "Friendly", scope=CompetitionScope.INTERNATIONAL
    )
    assert world_cup and euro and qualifier and friendly
    assert [item.priority_band for item in (world_cup, euro, qualifier, friendly)] == [
        "INT-S",
        "INT-A",
        "INT-B",
        "INT-F",
    ]

    ordered, exclusions = prioritize_accumulator_candidates(
        [
            _candidate("friendly", league="Friendly", probability=0.99, competition_scope="INTERNATIONAL"),
            _candidate("wcq", league="World Cup qualifiers", probability=0.80, competition_scope="INTERNATIONAL"),
            _candidate("world-cup", league="World Cup", probability=0.60, competition_scope="INTERNATIONAL"),
        ]
    )
    assert not exclusions
    assert [item["fixture_id"] for item in ordered] == ["world-cup", "wcq", "friendly"]


def test_club_and_international_plans_cannot_be_mixed_mechanically():
    with pytest.raises(ValueError, match="club and international"):
        prioritize_accumulator_candidates(
            [
                _candidate("epl", league="Premier League", probability=0.70),
                _candidate("world-cup", league="World Cup", probability=0.70, competition_scope="INTERNATIONAL"),
            ]
        )


def test_source_identity_present_never_falls_back_to_ambiguous_bare_name():
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


def test_unreviewed_competition_needs_explicit_expansion():
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
    assert ordered[0]["model_league_priority_basis"] == LeagueReliabilityBasis.BOOTSTRAP_FALLBACK.value
