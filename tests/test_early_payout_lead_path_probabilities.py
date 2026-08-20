import ast
import dataclasses
import inspect
import math
from pathlib import Path
from types import MappingProxyType

import pytest

from domain.early_payout_lead_path_probabilities import (
    DATASET_NAME,
    PROBABILITY_METHOD,
    EarlyPayoutLeadPathError,
    canonical_early_payout_analytical_projection_bytes,
    conditional_lead_hit_probabilities,
    project_early_payout_market,
    sha256_early_payout_analytical_projection,
)
from domain.markets import MarketId, OutcomeId
from domain.model_status import (
    AnalyticalProbabilityCapability,
    ModelStatus,
    PricingAuthority,
    SelectionAuthority,
    get_model_status,
)
from domain.score_matrix import NORMALIZATION_METHOD, ScoreMatrix, build_score_matrix
from domain.score_matrix_market_probabilities import (
    AnalyticalProjectionError,
    MarketTopology,
    project_score_matrix_market,
)


def _probabilities(projection):
    return {item.outcome_id: item.probability for item in projection.event_probabilities}


def _single_cell_matrix(home_goals: int, away_goals: int) -> ScoreMatrix:
    probabilities = MappingProxyType({(home_goals, away_goals): 1.0})
    return ScoreMatrix(
        home_expected_goals=float(home_goals),
        away_expected_goals=float(away_goals),
        probabilities=probabilities,
        raw_probabilities=probabilities,
        max_home_goal=home_goals,
        max_away_goal=away_goals,
        retained_mass_before_normalization=1.0,
        omitted_tail_mass=0.0,
        tail_tolerance=1e-10,
        normalization_method=NORMALIZATION_METHOD,
    )


@pytest.mark.parametrize(
    "home,away,threshold,counts,probabilities",
    (
        (0, 0, 1, (0, 0, 0, 1), (0.0, 0.0)),
        (1, 0, 1, (1, 0, 0, 0), (1.0, 0.0)),
        (0, 1, 1, (0, 1, 0, 0), (0.0, 1.0)),
        (1, 1, 1, (1, 1, 0, 0), (0.5, 0.5)),
        (2, 0, 2, (1, 0, 0, 0), (1.0, 0.0)),
        (0, 2, 2, (0, 1, 0, 0), (0.0, 1.0)),
        (2, 1, 1, (2, 0, 1, 0), (1.0, 1.0 / 3.0)),
        (1, 2, 1, (0, 2, 1, 0), (1.0 / 3.0, 1.0)),
        (2, 1, 2, (1, 0, 0, 2), (1.0 / 3.0, 0.0)),
        (1, 2, 2, (0, 1, 0, 2), (0.0, 1.0 / 3.0)),
        (2, 2, 1, (2, 2, 2, 0), (2.0 / 3.0, 2.0 / 3.0)),
        (2, 2, 2, (1, 1, 0, 4), (1.0 / 6.0, 1.0 / 6.0)),
    ),
)
def test_exact_conditional_path_counts(home, away, threshold, counts, probabilities):
    result = conditional_lead_hit_probabilities(home, away, threshold)
    assert result.total_orderings == math.comb(home + away, home)
    assert (
        result.home_only_orderings,
        result.away_only_orderings,
        result.both_orderings,
        result.neither_orderings,
    ) == counts
    assert result.home_hit_probability == probabilities[0]
    assert result.away_hit_probability == probabilities[1]
    assert 0.0 <= result.home_hit_probability <= 1.0
    assert 0.0 <= result.away_hit_probability <= 1.0


def test_path_counts_partition_and_home_away_transpose_symmetry():
    for home in range(7):
        for away in range(7):
            for threshold in (1, 2):
                result = conditional_lead_hit_probabilities(home, away, threshold)
                transposed = conditional_lead_hit_probabilities(away, home, threshold)
                assert sum(
                    (
                        result.home_only_orderings,
                        result.away_only_orderings,
                        result.both_orderings,
                        result.neither_orderings,
                    )
                ) == math.comb(home + away, home)
                assert result.home_only_orderings == transposed.away_only_orderings
                assert result.away_only_orderings == transposed.home_only_orderings
                assert result.both_orderings == transposed.both_orderings
                assert result.neither_orderings == transposed.neither_orderings
                assert result.home_hit_probability == transposed.away_hit_probability
                assert result.away_hit_probability == transposed.home_hit_probability


def test_final_score_matrix_integration_matches_independent_cell_sum():
    matrix = build_score_matrix(1.7, 1.1)
    for market_id, threshold in (
        (MarketId.MATCH_RESULT_1UP, 1),
        (MarketId.MATCH_RESULT_2UP, 2),
    ):
        projection = project_early_payout_market(matrix, market_id)
        actual = _probabilities(projection)
        expected_home = []
        expected_away = []
        for (home, away), mass in sorted(matrix.probabilities.items()):
            paths = conditional_lead_hit_probabilities(home, away, threshold)
            home_event = paths.home_hit_probability
            away_event = paths.away_hit_probability
            if threshold == 2:
                home_event = 1.0 if home > away else home_event
                away_event = 1.0 if away > home else away_event
            expected_home.append(mass * home_event)
            expected_away.append(mass * away_event)
        assert actual[OutcomeId.HOME] == math.fsum(expected_home)
        assert actual[OutcomeId.AWAY] == math.fsum(expected_away)
        assert actual[OutcomeId.DRAW] == matrix.draw


def test_1up_full_time_win_is_contained_in_one_goal_lead_event():
    for home in range(6):
        for away in range(6):
            paths = conditional_lead_hit_probabilities(home, away, 1)
            if home > away:
                assert paths.home_hit_probability == 1.0
            if away > home:
                assert paths.away_hit_probability == 1.0
    projection = project_early_payout_market(
        _single_cell_matrix(1, 0), MarketId.MATCH_RESULT_1UP
    )
    assert _probabilities(projection) == {
        OutcomeId.HOME: 1.0,
        OutcomeId.DRAW: 0.0,
        OutcomeId.AWAY: 0.0,
    }


def test_2up_applies_full_time_win_fallback_without_proxying_full_time_result():
    paths = conditional_lead_hit_probabilities(2, 1, 2)
    assert paths.home_hit_probability == 1.0 / 3.0
    projection = project_early_payout_market(
        _single_cell_matrix(2, 1), MarketId.MATCH_RESULT_2UP
    )
    assert _probabilities(projection)[OutcomeId.HOME] == 1.0

    draw_projection = project_early_payout_market(
        _single_cell_matrix(2, 2), MarketId.MATCH_RESULT_2UP
    )
    draw_probabilities = _probabilities(draw_projection)
    assert draw_probabilities[OutcomeId.HOME] == 1.0 / 6.0
    assert draw_probabilities[OutcomeId.DRAW] == 1.0
    assert draw_probabilities[OutcomeId.AWAY] == 1.0 / 6.0


def test_events_overlap_and_are_never_renormalized_as_ordinary_1x2():
    matrix = _single_cell_matrix(1, 1)
    one_up = project_early_payout_market(matrix, MarketId.MATCH_RESULT_1UP)
    probabilities = _probabilities(one_up)
    assert probabilities == {
        OutcomeId.HOME: 0.5,
        OutcomeId.DRAW: 1.0,
        OutcomeId.AWAY: 0.5,
    }
    assert math.fsum(probabilities.values()) == 2.0
    assert one_up.topology is MarketTopology.OVERLAPPING_EVENTS


def test_direct_score_matrix_projector_cannot_substitute_match_result():
    matrix = build_score_matrix(1.4, 1.0)
    ordinary = _probabilities(
        project_score_matrix_market(matrix, MarketId.MATCH_RESULT)
    )
    for early_market in (MarketId.MATCH_RESULT_1UP, MarketId.MATCH_RESULT_2UP):
        with pytest.raises(AnalyticalProjectionError):
            project_score_matrix_market(matrix, early_market)
        early = _probabilities(project_early_payout_market(matrix, early_market))
        assert early != ordinary


def test_registry_promotes_analytical_capability_only():
    for market_id in (MarketId.MATCH_RESULT_1UP, MarketId.MATCH_RESULT_2UP):
        status = get_model_status(market_id)
        assert status.status is ModelStatus.EXPERIMENTAL
        assert status.analytical_probability_capability is (
            AnalyticalProbabilityCapability.AVAILABLE
        )
        assert status.probability_method == PROBABILITY_METHOD
        assert status.pricing_authority is PricingAuthority.NOT_AUTHORIZED
        assert status.selection_authority is SelectionAuthority.NOT_AUTHORIZED
        assert status.pricing_authorized is False
        assert status.selectable is False


def test_projection_accepts_no_bookmaker_price_and_grants_no_downstream_authority():
    assert set(inspect.signature(project_early_payout_market).parameters) == {
        "score_matrix",
        "market_id",
    }
    projection = project_early_payout_market(
        build_score_matrix(1.3, 0.9), MarketId.MATCH_RESULT_1UP
    )
    assert projection.analytical_prediction_authorized is True
    assert projection.abandonment_probability_modeled is False
    assert all(value is False for value in dict(projection.safety).values())


def test_projection_canonicalization_and_mutation_fail_closed():
    projection = project_early_payout_market(
        build_score_matrix(1.3, 0.9), MarketId.MATCH_RESULT_2UP
    )
    first = canonical_early_payout_analytical_projection_bytes(projection)
    assert first == canonical_early_payout_analytical_projection_bytes(projection)
    assert first.endswith(b"\n")
    assert len(sha256_early_payout_analytical_projection(projection)) == 64
    with pytest.raises(EarlyPayoutLeadPathError):
        dataclasses.replace(
            projection,
            safety=tuple(
                (key, True if key == "bet_authorized" else value)
                for key, value in projection.safety
            ),
        )


@pytest.mark.parametrize(
    "args",
    ((True, 1, 1), (-1, 1, 1), (1, 1, 0), (1.0, 1, 1)),
)
def test_invalid_conditional_inputs_fail_closed(args):
    with pytest.raises(EarlyPayoutLeadPathError):
        conditional_lead_hit_probabilities(*args)


def test_production_module_has_no_pricing_execution_or_random_path():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "domain"
        / "early_payout_lead_path_probabilities.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    forbidden = {
        "random",
        "numpy",
        "scipy",
        "sklearn",
        "domain.pricing",
        "engine.probability_engine",
        "intelligence.prediction_engine",
    }
    assert not (imports & forbidden)
    source = module_path.read_text(encoding="utf-8").lower()
    assert "monte carlo" in source
    assert "bookmaker_odds" not in source
    assert DATASET_NAME in module_path.read_text(encoding="utf-8")
