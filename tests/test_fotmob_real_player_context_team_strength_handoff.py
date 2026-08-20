from __future__ import annotations

import ast
from pathlib import Path

import pytest

from domain.fotmob_real_player_context_team_strength_handoff import (
    HANDOFF_SCOPE,
    RealPlayerContextTeamStrengthHandoffError,
    ReviewedRealFotMobTeamStrengthHandoff,
    _source_identity,
)


def test_authoritative_handoff_has_no_public_constructor() -> None:
    with pytest.raises(
        RealPlayerContextTeamStrengthHandoffError,
        match="only from exact PR193 source replay",
    ):
        ReviewedRealFotMobTeamStrengthHandoff()


def test_handoff_scope_is_exact_observation_only() -> None:
    assert HANDOFF_SCOPE == "EXACT_PR193_OBSERVATION_TEAM_STRENGTH_FEATURE_HANDOFF_ONLY"


def test_source_identity_preserves_provider_type() -> None:
    assert _source_identity("FOTMOB_TEAM", 10203) == "FOTMOB_TEAM:INTEGER:10203"
    assert _source_identity("FOTMOB_MATCH", "5795367") == "FOTMOB_MATCH:STRING:5795367"
    with pytest.raises(RealPlayerContextTeamStrengthHandoffError):
        _source_identity("FOTMOB_TEAM", " 10203 ")


def test_boundary_hard_codes_only_exact_admitted_available_features() -> None:
    source = Path("domain/fotmob_real_player_context_team_strength_handoff.py").read_text(
        encoding="utf-8"
    )
    assert '"home_unavailable_player_count": 1.0' in source
    assert '"away_unavailable_player_count": 5.0' in source
    assert 'lineup_state=LineupState.UNVERIFIED_LINEUP_STATE' in source
    assert "source_position=None" in source
    assert "position_group=PositionGroup.UNKNOWN" in source
    assert "historical_appearances=()" in source
    assert "historical_fixtures=()" in source
    assert "base_components=()" in source


def test_boundary_authorizes_feature_handoff_but_not_model_or_bet_decision() -> None:
    source = Path("domain/fotmob_real_player_context_team_strength_handoff.py").read_text(
        encoding="utf-8"
    )
    for token in (
        '"team_strength_feature_authorized": True',
        '"prospective_reuse_after_source_freshness_authorized": False',
        '"bench_semantics_used": False',
        '"position_semantics_used": False',
        '"historical_player_evidence_used": False',
        '"probability_inference_authorized": False',
        '"probability_adjustment_authorized": False',
        '"pricing_authorized": False',
        '"selection_authorized": False',
        '"bet_authorized": False',
    ):
        assert token in source


def test_verifier_imports_no_network_sportybet_or_probability_runtime() -> None:
    tree = ast.parse(
        Path("scripts/verify_fotmob_real_player_context_team_strength_handoff.py").read_text(
            encoding="utf-8"
        )
    )
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append((node.module or "").casefold())
    forbidden = (
        "requests",
        "httpx",
        "aiohttp",
        "sportybet",
        "score_matrix",
        "prediction_engine",
        "pricing",
        "selection",
    )
    assert not any(token in name for name in imports for token in forbidden)


def test_hosted_proof_is_offline_and_exact_pr192_artifact_bound() -> None:
    workflow = Path(
        ".github/workflows/verify-fotmob-real-player-context-team-strength-handoff.yml"
    ).read_text(encoding="utf-8")
    for token in (
        "9422055017",
        "32410775191",
        "46f76e8033d3d498131c6f893111b437b6b459a9",
        "db5dc12b8863cbac15f210e018ddf0af9b9011a6ad8c3958a473a597254f44b5",
        "actions/download-artifact@",
        "persist-credentials: false",
    ):
        assert token in workflow
    assert "curl " not in workflow
    assert "capture_fotmob" not in workflow
