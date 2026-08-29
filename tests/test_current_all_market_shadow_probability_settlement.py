"""Focused tests for the PR C all-market Shadow probability/settlement adapter."""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from domain.markets import MarketId, OutcomeId
from domain.model_status import PricingAuthority, SelectionAuthority
from domain.score_matrix import build_score_matrix
from domain.score_matrix_settlement import (
    asian_handicap_settlement,
    draw_no_bet_settlement,
)
from domain.win_either_half_features import PRE_MATCH_FEATURE_NAMES

from domain import current_all_market_shadow_probability_settlement as adapter


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "domain"
    / "current_all_market_shadow_probability_settlement.py"
)


def _research_xg(home: float = 1.4, away: float = 1.1) -> adapter.ResearchXGRates:
    return adapter.ResearchXGRates(
        calibrated_home=home,
        calibrated_away=away,
        sealed_prediction_sha256="a" * 64,
        completeness_status="SEALED_RESEARCH_RATES",
    )


def _empty_weh_features() -> dict:
    return {name: 0.0 for name in PRE_MATCH_FEATURE_NAMES}


def test_canonical_completeness_exactly_15_markets():
    scan = adapter.scan_fixture_all_markets(
        fixture_identity="FOTMOB:12345",
        research_xg=_research_xg(),
    )
    ids = [a.market_id for a in scan.market_assessments]
    assert len(ids) == 15
    assert len(set(ids)) == 15
    assert set(ids) == set(MarketId)


def test_no_legacy_shortcut_imports():
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_names.add(node.module.split(".")[0])
            for alias in node.names:
                imported_names.add(alias.name)
    forbidden = {"AccaBuilder", "MatchAnalyst", "MARKET_BASELINES", "global_baseline_delta"}
    assert forbidden.isdisjoint(imported_names)
    assert "AccaBuilder" not in source
    assert "MatchAnalyst" not in source
    assert "MARKET_BASELINES" not in source


def test_score_matrix_integrity_and_match_result():
    xg = _research_xg(1.5, 1.2)
    scan = adapter.scan_fixture_all_markets(
        fixture_identity="FOTMOB:1",
        research_xg=xg,
    )
    assert scan.score_matrix_audit is not None
    mr = next(a for a in scan.market_assessments if a.market_id is MarketId.MATCH_RESULT)
    probs = {e.outcome_id: e.probability for e in mr.event_probabilities}
    total = math.fsum(probs.values())
    assert math.isclose(total, 1.0, abs_tol=1e-12)
    assert set(probs) == {OutcomeId.HOME, OutcomeId.DRAW, OutcomeId.AWAY}


def test_total_goals_half_line_and_btts():
    scan = adapter.scan_fixture_all_markets(
        fixture_identity="FOTMOB:2",
        research_xg=_research_xg(),
        total_goals_line=2.5,
    )
    tg = next(a for a in scan.market_assessments if a.market_id is MarketId.TOTAL_GOALS)
    assert tg.disposition is adapter.ShadowDisposition.ANALYTICAL_READY
    probs = {e.outcome_id: e.probability for e in tg.event_probabilities}
    assert math.isclose(probs[OutcomeId.OVER] + probs[OutcomeId.UNDER], 1.0, abs_tol=1e-12)

    btts = next(a for a in scan.market_assessments if a.market_id is MarketId.BTTS)
    bprobs = {e.outcome_id: e.probability for e in btts.event_probabilities}
    assert math.isclose(bprobs[OutcomeId.YES] + bprobs[OutcomeId.NO], 1.0, abs_tol=1e-12)


def test_double_chance_overlapping_not_partition():
    scan = adapter.scan_fixture_all_markets(
        fixture_identity="FOTMOB:3",
        research_xg=_research_xg(),
    )
    dc = next(a for a in scan.market_assessments if a.market_id is MarketId.DOUBLE_CHANCE)
    total = math.fsum(e.probability for e in dc.event_probabilities)
    # Overlapping events: sum is near 2, not 1
    assert total > 1.5


def test_dnb_full_settlement_distribution():
    scan = adapter.scan_fixture_all_markets(
        fixture_identity="FOTMOB:4",
        research_xg=_research_xg(1.6, 1.0),
    )
    dnb = next(a for a in scan.market_assessments if a.market_id is MarketId.DRAW_NO_BET)
    assert dnb.settlement_distributions
    for item in dnb.settlement_distributions:
        assert math.isclose(item.settlement.total_probability, 1.0, abs_tol=1e-12)
        assert item.settlement.half_win == 0.0
        assert item.settlement.half_loss == 0.0


def test_asian_handicap_full_settlement_and_provider_separation():
    scan = adapter.scan_fixture_all_markets(
        fixture_identity="FOTMOB:5",
        research_xg=_research_xg(),
        asian_handicap_home_lines=(-0.5, 0.0, 0.25, -0.25, 0.75, -0.75),
        provider_semantic_by_market={
            MarketId.ASIAN_HANDICAP: "CURRENT_PROVIDER_UNPROVEN",
        },
    )
    ah = next(a for a in scan.market_assessments if a.market_id is MarketId.ASIAN_HANDICAP)
    assert ah.disposition is adapter.ShadowDisposition.ANALYTICAL_READY_PROVIDER_BLOCKED
    assert ah.provider_semantic_status == "CURRENT_PROVIDER_UNPROVEN"
    assert ah.settlement_distributions
    for item in ah.settlement_distributions:
        assert math.isclose(item.settlement.total_probability, 1.0, abs_tol=1e-12)

    # Direct settlement math still works independently
    matrix = build_score_matrix(1.4, 1.1)
    for line in (-0.5, 0.0, 0.5, -0.25, 0.25, -0.75, 0.75):
        home = asian_handicap_settlement(matrix, "HOME", line)
        away = asian_handicap_settlement(matrix, "AWAY", -line)
        assert math.isclose(home.total_probability, 1.0, abs_tol=1e-12)
        assert math.isclose(away.total_probability, 1.0, abs_tol=1e-12)


def test_win_to_nil_complementary():
    scan = adapter.scan_fixture_all_markets(
        fixture_identity="FOTMOB:6",
        research_xg=_research_xg(),
    )
    for market_id in (MarketId.HOME_WIN_TO_NIL, MarketId.AWAY_WIN_TO_NIL):
        row = next(a for a in scan.market_assessments if a.market_id is market_id)
        total = math.fsum(e.probability for e in row.event_probabilities)
        assert math.isclose(total, 1.0, abs_tol=1e-12)


def test_1up_2up_overlap_preserved():
    scan = adapter.scan_fixture_all_markets(
        fixture_identity="FOTMOB:7",
        research_xg=_research_xg(2.0, 0.8),
    )
    for market_id in (MarketId.MATCH_RESULT_1UP, MarketId.MATCH_RESULT_2UP):
        row = next(a for a in scan.market_assessments if a.market_id is market_id)
        assert row.disposition is adapter.ShadowDisposition.ANALYTICAL_READY
        assert row.specialist_evidence is not None
        for event in row.event_probabilities:
            assert 0.0 <= event.probability <= 1.0
        # Overlap: sum need not be 1
        total = math.fsum(e.probability for e in row.event_probabilities)
        assert total > 0.0


def test_1up_symmetry_equal_xg():
    scan = adapter.scan_fixture_all_markets(
        fixture_identity="FOTMOB:8",
        research_xg=_research_xg(1.3, 1.3),
    )
    row = next(a for a in scan.market_assessments if a.market_id is MarketId.MATCH_RESULT_1UP)
    probs = {e.outcome_id: e.probability for e in row.event_probabilities}
    assert math.isclose(probs[OutcomeId.HOME], probs[OutcomeId.AWAY], abs_tol=1e-9)


def test_weh_missing_features_fail_closed():
    scan = adapter.scan_fixture_all_markets(
        fixture_identity="FOTMOB:9",
        research_xg=_research_xg(),
        weh_feature_row=None,
    )
    for market_id in (MarketId.HOME_WIN_EITHER_HALF, MarketId.AWAY_WIN_EITHER_HALF):
        row = next(a for a in scan.market_assessments if a.market_id is market_id)
        assert row.disposition is adapter.ShadowDisposition.SPECIALIST_FEATURES_MISSING
        assert row.event_probabilities == ()


def test_no_xg_blocks_score_matrix_markets_but_preserves_rows():
    scan = adapter.scan_fixture_all_markets(
        fixture_identity="FOTMOB:10",
        research_xg=None,
    )
    assert len(scan.market_assessments) == 15
    for a in scan.market_assessments:
        if a.market_id in {
            MarketId.HOME_WIN_EITHER_HALF,
            MarketId.AWAY_WIN_EITHER_HALF,
        }:
            assert a.disposition is adapter.ShadowDisposition.SPECIALIST_FEATURES_MISSING
        else:
            assert a.disposition is adapter.ShadowDisposition.NO_REVIEWED_XG


def test_authority_all_false():
    scan = adapter.scan_fixture_all_markets(
        fixture_identity="FOTMOB:11",
        research_xg=_research_xg(),
    )
    for key, value in scan.authority.items():
        assert value is False, key
    full = adapter.build_current_all_market_shadow_scan([scan])
    for key, value in full.authority.items():
        assert value is False, key
    assert full.to_dict()["wager_placed"] is False


def test_serialization_stable():
    scan = adapter.scan_fixture_all_markets(
        fixture_identity="FOTMOB:12",
        research_xg=_research_xg(1.2, 1.0),
    )
    full = adapter.build_current_all_market_shadow_scan([scan])
    b1 = adapter.canonical_current_all_market_shadow_scan_bytes(full)
    b2 = adapter.canonical_current_all_market_shadow_scan_bytes(full)
    assert b1 == b2
    h1 = adapter.sha256_current_all_market_shadow_scan(full)
    h2 = adapter.sha256_current_all_market_shadow_scan(full)
    assert h1 == h2
    assert len(h1) == 64


def test_pricing_selection_authority_remain_not_authorized():
    scan = adapter.scan_fixture_all_markets(
        fixture_identity="FOTMOB:13",
        research_xg=_research_xg(),
    )
    for a in scan.market_assessments:
        assert a.pricing_authority is PricingAuthority.NOT_AUTHORIZED
        assert a.selection_authority is SelectionAuthority.NOT_AUTHORIZED


def test_dnb_matches_direct_settlement_helper():
    xg = _research_xg(1.7, 0.9)
    matrix = build_score_matrix(xg.calibrated_home, xg.calibrated_away)
    direct_home = draw_no_bet_settlement(matrix, "HOME")
    scan = adapter.scan_fixture_all_markets(
        fixture_identity="FOTMOB:14",
        research_xg=xg,
    )
    dnb = next(a for a in scan.market_assessments if a.market_id is MarketId.DRAW_NO_BET)
    home = next(s for s in dnb.settlement_distributions if s.outcome_id is OutcomeId.HOME)
    assert math.isclose(home.settlement.full_win, direct_home.full_win, abs_tol=1e-15)
    assert math.isclose(home.settlement.push, direct_home.push, abs_tol=1e-15)
    assert math.isclose(home.settlement.full_loss, direct_home.full_loss, abs_tol=1e-15)
