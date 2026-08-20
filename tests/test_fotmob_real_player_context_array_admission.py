from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

from domain.fotmob_real_player_context_array_admission import (
    AWAY_TEAM_ID,
    BenchEvidenceStatus,
    CLASSIFIED_AT,
    FIXTURE_IDENTIFIER,
    HOME_TEAM_ID,
    KICKOFF,
    OBSERVED_AT,
    PlayerContextSetScope,
    RealPlayerContextAdmissionError,
    ReviewedRealFotMobPlayerContextAdmission,
    ReviewedRealPlayerRecord,
    ReviewedRealPlayerRecordSet,
    SOURCE_ARTIFACT_DIGEST,
    SOURCE_ARTIFACT_ID,
    SOURCE_REPOSITORY_HEAD_SHA,
    SOURCE_WORKFLOW_RUN_ID,
    STATE_FRESH_UNTIL,
)
from domain.fotmob_team_strength_fixture_intelligence import LineupState, TeamSide


def test_real_admission_is_frozen_to_exact_successful_pr192_lineage() -> None:
    assert FIXTURE_IDENTIFIER == "FOTMOB:5795367"
    assert HOME_TEAM_ID == 10203
    assert AWAY_TEAM_ID == 8463
    assert SOURCE_REPOSITORY_HEAD_SHA == "46f76e8033d3d498131c6f893111b437b6b459a9"
    assert SOURCE_WORKFLOW_RUN_ID == 32410775191
    assert SOURCE_ARTIFACT_ID == 9422055017
    assert SOURCE_ARTIFACT_DIGEST == (
        "sha256:db5dc12b8863cbac15f210e018ddf0af9b9011a6ad8c3958a473a597254f44b5"
    )
    assert OBSERVED_AT < CLASSIFIED_AT < KICKOFF


def test_state_freshness_does_not_project_thursday_snapshot_forward() -> None:
    assert STATE_FRESH_UNTIL == CLASSIFIED_AT
    assert STATE_FRESH_UNTIL < KICKOFF


def test_authoritative_wrapper_has_no_public_constructor() -> None:
    with pytest.raises(RealPlayerContextAdmissionError, match="only from exact PR192 replay"):
        ReviewedRealFotMobPlayerContextAdmission()


def test_predicted_starting_xi_requires_exact_expected_eleven() -> None:
    row = ReviewedRealPlayerRecordSet(
        scope=PlayerContextSetScope.STARTING_XI,
        team_side=TeamSide.HOME,
        source_team_id=HOME_TEAM_ID,
        source_team_name="Nottingham Forest",
        array_root_pointer="/content/lineup/homeTeam/starters",
        record_count=11,
        provider_player_ids=tuple(range(1, 12)),
        completeness_attested=True,
        lineup_state=LineupState.EXPECTED,
        state_fresh_until=STATE_FRESH_UNTIL,
        evidence_sha256="a" * 64,
    )
    with pytest.raises(RealPlayerContextAdmissionError, match="EXPECTED eleven"):
        dataclasses.replace(row, record_count=10, provider_player_ids=tuple(range(1, 11)))
    with pytest.raises(RealPlayerContextAdmissionError, match="EXPECTED eleven"):
        dataclasses.replace(row, lineup_state=LineupState.CONFIRMED)


def test_unavailable_set_does_not_claim_fixture_lineup_state() -> None:
    row = ReviewedRealPlayerRecordSet(
        scope=PlayerContextSetScope.UNAVAILABLE,
        team_side=TeamSide.AWAY,
        source_team_id=AWAY_TEAM_ID,
        source_team_name="Leeds United",
        array_root_pointer="/content/lineup/awayTeam/unavailable",
        record_count=1,
        provider_player_ids=(123,),
        completeness_attested=True,
        lineup_state=None,
        state_fresh_until=STATE_FRESH_UNTIL,
        evidence_sha256="b" * 64,
    )
    with pytest.raises(RealPlayerContextAdmissionError, match="cannot claim"):
        dataclasses.replace(row, lineup_state=LineupState.NOT_AVAILABLE)


def test_numeric_source_fields_are_preserved_without_position_inference() -> None:
    row = ReviewedRealPlayerRecord(
        scope=PlayerContextSetScope.STARTING_XI,
        team_side=TeamSide.HOME,
        source_team_id=HOME_TEAM_ID,
        provider_player_id=181069,
        source_position_id=11,
        source_usual_playing_position_id=0,
        source_market_value=3851901,
        unavailability_type=None,
        source_record_pointer="/content/lineup/homeTeam/starters/0",
        evidence_sha256="c" * 64,
    )
    assert row.source_position_id == 11
    assert row.source_usual_playing_position_id == 0
    assert row.source_market_value == 3851901


def test_unavailable_semantics_cannot_leak_into_starter() -> None:
    with pytest.raises(RealPlayerContextAdmissionError, match="starter cannot"):
        ReviewedRealPlayerRecord(
            PlayerContextSetScope.STARTING_XI,
            TeamSide.HOME,
            HOME_TEAM_ID,
            181069,
            11,
            0,
            3851901,
            "injury",
            "/content/lineup/homeTeam/starters/0",
            "c" * 64,
        )


def test_unavailable_record_requires_exact_reviewed_type() -> None:
    with pytest.raises(RealPlayerContextAdmissionError, match="requires reviewed type"):
        ReviewedRealPlayerRecord(
            PlayerContextSetScope.UNAVAILABLE,
            TeamSide.AWAY,
            AWAY_TEAM_ID,
            1080983,
            None,
            None,
            11864849,
            None,
            "/content/lineup/awayTeam/unavailable/0",
            "d" * 64,
        )


def test_hosted_proof_is_exact_pr192_artifact_bound_and_offline() -> None:
    workflow = Path(
        ".github/workflows/verify-fotmob-real-player-context-array-admission.yml"
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


def test_runner_imports_no_network_sportybet_or_model_runtime() -> None:
    tree = ast.parse(
        Path("scripts/verify_fotmob_real_player_context_admission.py").read_text(
            encoding="utf-8"
        )
    )
    imports = []
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


def test_boundary_refuses_bench_position_market_value_and_model_authority() -> None:
    source = Path("domain/fotmob_real_player_context_array_admission.py").read_text(
        encoding="utf-8"
    )
    for token in (
        '"bench_semantics_authorized": False',
        '"position_semantics_authorized": False',
        '"market_value_semantics_authorized": False',
        '"expected_return_semantics_authorized": False',
        '"team_strength_feature_authorized": False',
        '"probability_inference_authorized": False',
        '"pricing_authorized": False',
        '"selection_authorized": False',
        '"bet_authorized": False',
    ):
        assert token in source
    assert BenchEvidenceStatus.MISSING_SOURCE_ROOT.value in source
