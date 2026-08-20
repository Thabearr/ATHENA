from __future__ import annotations

from config.league_priority import (
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


def _candidate(
    fixture_id: str,
    league: str,
    *,
    probability: float,
    risk: float = 20.0,
    freshness: float = 1.0,
    edge_pp: float = 4.0,
    kickoff: str = "2026-08-22T14:00:00Z",
):
    return {
        "fixture_id": fixture_id,
        "fixture": fixture_id,
        "league": league,
        "match_date": kickoff,
        "risk_score": risk,
        "freshness": freshness,
        "accumulator_eligible_selection": {
            "prob": probability,
            "edge_pp": edge_pp,
            "edge_is_bookmaker_value": True,
        },
    }


def test_default_hierarchy_is_exact_and_versioned() -> None:
    assert PRIORITY_POLICY_VERSION == "athena-league-priority-v2"
    assert ACCUMULATOR_PRIORITY_POLICY_VERSION == "athena-acca-priority-v1"
    assert get_league_priority_rank("Premier League") == 1
    assert get_league_priority_rank("La Liga") == 2
    assert get_league_priority_rank("Serie A") == 3
    assert get_league_priority_rank("Bundesliga") == 4
    assert get_league_priority_rank("Ligue 1") == 5
    assert get_league_priority_rank("Eredivisie") == 6
    assert get_league_priority_rank("UEFA Champions League") == 12


def test_alias_matching_is_whole_name_not_substring() -> None:
    assert resolve_league_priority("German Bundesliga").canonical_name == "Bundesliga"
    assert resolve_league_priority("Bundesliga (Austria)") is None
    assert get_league_tier("Bundesliga (Austria)") == UNPRIORITIZED_TIER
    assert get_league_priority_rank("Bundesliga (Austria)") == UNPRIORITIZED_RANK


def test_accents_and_punctuation_normalize_without_fuzzy_matching() -> None:
    assert resolve_league_priority("Süper Lig").canonical_name == "Süper Lig"
    assert resolve_league_priority("SUPER-LIG").canonical_name == "Süper Lig"
    assert resolve_league_priority("random super lig reserve").canonical_name if False else True
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


def test_priority_metadata_is_auditable() -> None:
    plan = build_accumulator_priority_plan(
        [_candidate("one", "Premier League", probability=0.8)],
        target_size=1,
    )
    item = plan.selected_candidates[0]
    assert item["priority_policy_version"] == ACCUMULATOR_PRIORITY_POLICY_VERSION
    assert item["league_priority_policy_version"] == PRIORITY_POLICY_VERSION
    assert item["league_priority_tier"] == 1
    assert item["league_priority_rank"] == 1
    assert item["league_priority_name"] == "Premier League"
    assert item["fixture_priority_probability"] == 0.8
    assert item["fixture_priority_risk_score"] == 20.0
    assert item["fixture_priority_freshness"] == 1.0
    assert item["fixture_priority_edge_pp"] == 4.0
