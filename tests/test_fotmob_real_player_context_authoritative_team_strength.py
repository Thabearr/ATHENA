from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

import domain.fotmob_real_player_context_authoritative_team_strength as bridge
from domain.fotmob_real_player_context_array_admission import (
    FIXTURE_IDENTIFIER,
    RAW_SHA256,
    STRUCTURE_SHA256,
)
from domain.fotmob_real_player_context_team_strength_handoff import (
    EXPECTED_CANDIDATE_SHA256,
    SOURCE_ADMISSION_SHA256,
)


def test_contract_is_exact_observation_only_and_not_source_wide() -> None:
    assert bridge.SCHEMA_VERSION == 1
    assert bridge.DATASET_NAME == (
        "athena-fotmob-real-player-context-authoritative-team-strength-v1"
    )
    assert bridge.AUTHORITY_SCOPE == (
        "EXACT_PR192_PR193_PR194_WITH_SAME_RAW_REVALIDATED_PR52_TO_PR66_LINEAGE_ONLY"
    )
    assert bridge.LINEAGE_FIELD_POINTER == "/content/lineup/lineupType"
    assert bridge.LINEAGE_FIELD_NAME == "lineup_type"


def test_frozen_source_constants_remain_bound_to_pr193_pr194() -> None:
    assert bridge.PR193_FIXTURE_IDENTIFIER == FIXTURE_IDENTIFIER
    assert bridge.PR193_RAW_SHA256 == RAW_SHA256
    assert bridge.PR193_STRUCTURE_SHA256 == STRUCTURE_SHA256
    assert bridge.PR193_ADMISSION_SHA256 == SOURCE_ADMISSION_SHA256
    assert bridge.PR194_CANDIDATE_SHA256 == EXPECTED_CANDIDATE_SHA256


def test_public_builder_accepts_only_exact_source_bytes_not_model_or_bookmaker_inputs() -> None:
    params = set(
        inspect.signature(
            bridge.build_reviewed_real_fotmob_authoritative_team_strength_context
        ).parameters
    )
    assert params == {
        "campaign_receipt_bytes",
        "manifest_bytes",
        "raw_bytes",
        "persisted_receipt_bytes",
        "structure_assessment_bytes",
    }
    forbidden = {
        "odds",
        "price",
        "bookmaker",
        "probability",
        "expected_goals",
        "coefficient",
        "selection",
        "market_id",
        "sportybet",
    }
    assert not (params & forbidden)


def test_authority_wrapper_cannot_be_directly_constructed_or_replaced() -> None:
    with pytest.raises(
        bridge.RealPlayerContextAuthoritativeTeamStrengthError,
        match="exact source replay",
    ):
        bridge.ReviewedRealFotMobAuthoritativeTeamStrengthContext()
    assert dataclasses.is_dataclass(
        bridge.ReviewedRealFotMobAuthoritativeTeamStrengthContext
    )


def test_production_module_has_no_network_bookmaker_or_probability_dependency() -> None:
    path = (
        Path(__file__).parents[1]
        / "domain"
        / "fotmob_real_player_context_authoritative_team_strength.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    forbidden_tokens = (
        "requests",
        "urllib",
        "httpx",
        "aiohttp",
        "socket",
        "sportybet",
        "bookmaker",
        "score_matrix",
        "probability",
        "selection",
        "betting",
        "advanced_scraper",
        "bypass",
    )
    assert not any(
        any(token in name.lower() for token in forbidden_tokens) for name in imports
    )


def test_expected_authority_contract_has_only_exact_team_strength_gate_true() -> None:
    authority = dict(bridge._AUTHORITY)
    assert authority["team_strength_feature_authorized"] is True
    assert authority["exact_observation_team_strength_feature_authorized"] is True
    assert authority["prospective_reuse_after_source_freshness_authorized"] is False
    assert authority["source_wide_team_strength_authorized"] is False
    for key in (
        "probability_inference_authorized",
        "probability_adjustment_authorized",
        "pricing_authorized",
        "selection_authorized",
        "production_approval_authorized",
        "bet_authorized",
    ):
        assert authority[key] is False


def test_only_exact_two_current_availability_features_are_eligible() -> None:
    assert bridge._EXPECTED_AVAILABLE_FEATURES == {
        "away_unavailable_player_count": 5.0,
        "home_unavailable_player_count": 1.0,
    }
    assert bridge._EXPECTED_AVAILABLE_FEATURE_IDS == (
        "away_unavailable_player_count",
        "home_unavailable_player_count",
    )
