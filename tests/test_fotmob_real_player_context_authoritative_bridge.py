from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from domain.fotmob_real_player_context_authoritative_bridge import (
    BRIDGE_SCOPE,
    LINEAGE_SCALAR_FIELD,
    LINEAGE_SCALAR_POINTER,
    LINEAGE_SCALAR_VALUE,
    RealPlayerContextAuthoritativeBridgeError,
    ReviewedRealFotMobAuthoritativeTeamStrengthBridge,
    SOURCE_PR194_HANDOFF_SHA256,
    build_reviewed_real_fotmob_authoritative_team_strength_bridge,
)
from domain.fotmob_real_player_context_array_admission import CLASSIFIED_AT, KICKOFF
from domain.fotmob_real_player_context_pr191_authoritative_adapter import (
    build_reviewed_real_fotmob_pr191_team_strength_context,
)
from domain.fotmob_real_player_context_team_strength_handoff import EXPECTED_CANDIDATE_SHA256


def test_authoritative_bridge_has_no_public_constructor() -> None:
    with pytest.raises(
        RealPlayerContextAuthoritativeBridgeError,
        match="only be created by exact PR192→PR66 source replay",
    ):
        ReviewedRealFotMobAuthoritativeTeamStrengthBridge()


def test_bridge_scope_and_exact_lineage_sentinel_are_frozen() -> None:
    assert BRIDGE_SCOPE == "EXACT_PR193_OBSERVATION_PR65_PR66_TEAM_STRENGTH_AUTHORITY_ONLY"
    assert LINEAGE_SCALAR_POINTER == "/content/lineup/lineupType"
    assert LINEAGE_SCALAR_FIELD == "source_lineup_type"
    assert LINEAGE_SCALAR_VALUE == "predicted"
    assert SOURCE_PR194_HANDOFF_SHA256 == (
        "b5aab660cb4aebca6c1fd9b0d8bfb2d4e422d614e2fe4c59e796a2e670957ff3"
    )
    assert EXPECTED_CANDIDATE_SHA256 == (
        "cc48bbcea5a17ff57a39cc951c5e69005008d857366359528aaf46f979c30745"
    )


def test_source_freshness_is_not_projected_to_saturday() -> None:
    assert CLASSIFIED_AT < KICKOFF
    source = Path("domain/fotmob_real_player_context_authoritative_bridge.py").read_text(
        encoding="utf-8"
    )
    assert '"prospective_reuse_after_source_freshness_authorized": False' in source
    assert "fresh_until=PR193_CLASSIFIED_AT" in source
    assert "classified_at=PR193_CLASSIFIED_AT" in source


def test_prerequisite_bridge_stays_all_false_and_only_existing_pr191_wrapper_authorizes() -> None:
    bridge_source = Path(
        "domain/fotmob_real_player_context_authoritative_bridge.py"
    ).read_text(encoding="utf-8")
    adapter_source = Path(
        "domain/fotmob_real_player_context_pr191_authoritative_adapter.py"
    ).read_text(encoding="utf-8")

    assert '"team_strength_feature_authorized": False' in bridge_source
    assert '"team_strength_feature_authorized": True' not in bridge_source
    assert '"team_strength_feature_authorized": True' in adapter_source
    assert "ReviewedFotMobTeamStrengthContext" in adapter_source
    assert "PR197 prerequisite bridge must keep every authority flag false" in adapter_source

    for token in (
        '"lineage_scalar_model_feature_authorized": False',
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
        assert token in bridge_source


def test_exact_candidate_available_features_remain_only_unavailable_counts() -> None:
    source = Path("domain/fotmob_real_player_context_authoritative_bridge.py").read_text(
        encoding="utf-8"
    )
    assert '"home_unavailable_player_count": 1.0' in source
    assert '"away_unavailable_player_count": 5.0' in source
    assert "available != _EXPECTED_AVAILABLE_FEATURES" in source
    assert "item.source_position is not None" in source
    assert "PositionGroup.UNKNOWN" in source
    assert "historical player evidence was invented" in source


def test_lineage_sentinel_cannot_create_a_generic_pr31_feature() -> None:
    source = Path("domain/fotmob_real_player_context_authoritative_bridge.py").read_text(
        encoding="utf-8"
    )
    assert "item.status is not ModelFeatureStatus.MISSING" in source
    assert "lineage sentinel must not create any PR31 model feature" in source
    assert "pr65.fact_count != 1" in source
    assert "pr65.member_count != 1" in source


def test_builders_accept_only_exact_pr192_source_bytes_not_model_or_bookmaker_inputs() -> None:
    expected = {
        "campaign_receipt_bytes",
        "manifest_bytes",
        "raw_bytes",
        "persisted_receipt_bytes",
        "structure_assessment_bytes",
    }
    assert set(
        inspect.signature(
            build_reviewed_real_fotmob_authoritative_team_strength_bridge
        ).parameters
    ) == expected
    assert set(
        inspect.signature(
            build_reviewed_real_fotmob_pr191_team_strength_context
        ).parameters
    ) == expected

    forbidden = {
        "candidate",
        "historical_appearances",
        "historical_fixtures",
        "base_components",
        "odds",
        "price",
        "expected_goals",
        "probability",
        "coefficient",
        "sportybet",
    }
    assert not (expected & forbidden)


def _imports(path: str) -> list[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append((node.module or "").casefold())
    return names


def test_domain_adapter_and_verifier_import_no_network_bookmaker_probability_or_old_runtime() -> None:
    imports = _imports("domain/fotmob_real_player_context_authoritative_bridge.py")
    imports += _imports("domain/fotmob_real_player_context_pr191_authoritative_adapter.py")
    imports += _imports("scripts/verify_fotmob_real_player_context_authoritative_bridge.py")
    forbidden = (
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "sportybet",
        "score_matrix",
        "prediction_engine",
        "fixture_reasoner",
        "pricing",
        "selection",
    )
    assert not any(token in name for name in imports for token in forbidden)


def test_hosted_proof_is_exact_pr192_artifact_bound_offline_and_single_authority() -> None:
    workflow = Path(
        ".github/workflows/verify-fotmob-real-player-context-authoritative-bridge.yml"
    ).read_text(encoding="utf-8")
    for token in (
        "9422055017",
        "32410775191",
        "46f76e8033d3d498131c6f893111b437b6b459a9",
        "db5dc12b8863cbac15f210e018ddf0af9b9011a6ad8c3958a473a597254f44b5",
        "actions/download-artifact@",
        "persist-credentials: false",
        "exact_same_raw_pr53_pr65_pr66_lineage_verified=true",
        "team_strength_feature_authorized=true",
        "prospective_reuse_after_source_freshness_authorized=false",
    ):
        assert token in workflow
    assert "curl " not in workflow
    assert "capture_fotmob" not in workflow
    assert "sportybet" not in workflow.casefold()

    verifier = Path(
        "scripts/verify_fotmob_real_player_context_authoritative_bridge.py"
    ).read_text(encoding="utf-8")
    assert "prerequisite bridge illegally grants authority" in verifier
    assert "existing_pr191_authority_type_verified=true" in verifier
    assert "prerequisite_bridge_authority_all_false=true" in verifier


def test_temporary_self_modifying_pr_workflow_is_not_part_of_the_reviewed_boundary() -> None:
    assert not Path(".github/workflows/pr197-authority-path-self-fix.yml").exists()
