from __future__ import annotations

import ast
import dataclasses
import hashlib
from pathlib import Path

import pytest

import domain.fotmob_data_matches_final_result_semantics_validation as validation_module
from domain.fotmob_data_matches_final_result_semantics_protocol import (
    FinalResultSemanticsStatus,
    STATUS_VOCABULARY,
)
from domain.fotmob_data_matches_final_result_semantics_validation import (
    NEXT_REQUIRED_BOUNDARY,
    REVIEWED_CAPTURE_MANIFEST_SHA256,
    REVIEWED_CAPTURE_RAW_SHA256,
    REVIEWED_CAPTURE_RAW_SIZE,
    VALIDATION_SHA256,
    VALIDATION_SIZE,
    VALIDATION_STATE,
    FotMobDataMatchesFinalResultSemanticsValidationError,
    build_fotmob_data_matches_final_result_semantics_validation,
    canonical_fotmob_data_matches_final_result_semantics_validation_bytes,
    revalidate_fotmob_data_matches_final_result_semantics_validation,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


ROOT = Path(__file__).resolve().parents[1]


def _git_blob_oid(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()


def test_validation_is_exact_fail_closed_canonical_receipt() -> None:
    value = build_fotmob_data_matches_final_result_semantics_validation()
    exact = canonical_fotmob_data_matches_final_result_semantics_validation_bytes(value)

    assert VALIDATION_STATE == (
        "EXECUTED_FAIL_CLOSED_INSUFFICIENT_POST_FINISH_OBSERVATIONS"
    )
    assert value.validation_state == VALIDATION_STATE
    assert len(exact) == VALIDATION_SIZE == 2394
    assert hashlib.sha256(exact).hexdigest() == VALIDATION_SHA256
    assert VALIDATION_SHA256 == (
        "e83c7ae340348db5cf0830da1db47a23a20b95690267818e4426726dccfd61a6"
    )
    assert set(value.safety.values()) == {False}


def test_validation_binds_exact_merged_pr83_protocol_blob() -> None:
    protocol_path = ROOT / "domain" / "fotmob_data_matches_final_result_semantics_protocol.py"
    assert _git_blob_oid(protocol_path) == "25f8045524badcb90239df59ac9c47f36fcffe34"

    value = build_fotmob_data_matches_final_result_semantics_validation()
    assert value.repository_main_sha == "5cba22dfa480f66cf7fde22e31c730fb0848bcce"
    assert value.pr83_protocol_blob_sha == "25f8045524badcb90239df59ac9c47f36fcffe34"
    assert value.pr83_protocol_sha256 == (
        "572dde2f5ba8e68c96188ec2df3cc1fdcfa554aa1023aa56e8b8f8b225d7194b"
    )
    assert value.pr83_protocol_size == 3995


def test_pr39_reviewed_inventory_metadata_is_not_invented() -> None:
    documentation = (ROOT / "docs" / "fotmob_data_matches_schema.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(documentation.split())
    assert _git_blob_oid(ROOT / "docs" / "fotmob_data_matches_schema.md") == (
        "2d6a48287eb5d31f3aa63936264afcd6c463bb88"
    )
    assert "20260815/76d18629482ffda786e6b58e/" in documentation
    assert str(REVIEWED_CAPTURE_RAW_SIZE) in documentation
    assert REVIEWED_CAPTURE_RAW_SHA256 in documentation
    assert REVIEWED_CAPTURE_MANIFEST_SHA256 in documentation
    assert (
        "contains no reviewed started/finished evidence that establishes their football meaning"
        in normalized
    )


def test_execution_stops_at_insufficient_post_finish_observations() -> None:
    value = build_fotmob_data_matches_final_result_semantics_validation()

    assert value.reviewed_capture_count == 1
    assert value.reviewed_post_finish_capture_count == 0
    assert value.required_post_finish_capture_count == 2
    assert value.reviewed_capture_fixture_values_available_in_committed_reviewed_evidence is False
    assert value.reviewed_capture_started_finished_semantics_available is False
    assert value.status == (
        FinalResultSemanticsStatus.BLOCKED_INSUFFICIENT_POST_FINISH_OBSERVATIONS.value
    )
    assert value.status in STATUS_VOCABULARY
    assert value.final_result_semantics_qualified is False


def test_source_capability_remains_fail_closed() -> None:
    capability = SOURCE_CAPABILITY_REGISTRY["fotmob_data_matches_reviewed_catalog"]
    assert capability.reliable_fixture_identity is CapabilityAvailability.CONFIRMED
    assert capability.full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert capability.historical_coverage is CapabilityAvailability.UNKNOWN

    value = build_fotmob_data_matches_final_result_semantics_validation()
    assert value.source_capability_must_remain == "NOT_CAPTURED"
    assert value.historical_coverage_must_remain == "UNKNOWN"
    assert value.safety["source_capability_update_authorized"] is False


def test_no_fixture_or_score_is_fabricated_from_metadata_only_inventory() -> None:
    value = build_fotmob_data_matches_final_result_semantics_validation()
    keys = set(value.to_dict())
    assert "fixture_id" not in keys
    assert "home_score" not in keys
    assert "away_score" not in keys
    assert "finished" not in keys
    assert "started" not in keys
    assert "cancelled" not in keys


def test_next_boundary_requires_real_reviewed_post_finish_capture_pair() -> None:
    value = build_fotmob_data_matches_final_result_semantics_validation()
    assert value.next_required_boundary == NEXT_REQUIRED_BOUNDARY
    assert NEXT_REQUIRED_BOUNDARY == (
        "ACQUIRE_AND_PRESERVE_TWO_REVIEWED_POST_FINISH_DATA_MATCHES_CAPTURES_FOR_ONE_FINISHED_FIXTURE"
    )
    assert value.safety["network_acquisition_authorized"] is False


def test_validation_rejects_positive_or_inventory_mutations() -> None:
    value = build_fotmob_data_matches_final_result_semantics_validation()

    with pytest.raises(
        FotMobDataMatchesFinalResultSemanticsValidationError,
        match="differs from frozen PR84 receipt",
    ):
        dataclasses.replace(value, final_result_semantics_qualified=True)

    with pytest.raises(
        FotMobDataMatchesFinalResultSemanticsValidationError,
        match="differs from frozen PR84 receipt",
    ):
        dataclasses.replace(value, reviewed_post_finish_capture_count=2)

    safety = dict(value.safety)
    safety["source_capability_update_authorized"] = True
    with pytest.raises(
        FotMobDataMatchesFinalResultSemanticsValidationError,
        match="differs from frozen PR84 receipt",
    ):
        dataclasses.replace(value, safety=safety)


def test_revalidator_rejects_changed_receipt() -> None:
    value = build_fotmob_data_matches_final_result_semantics_validation()
    assert revalidate_fotmob_data_matches_final_result_semantics_validation(value) == value
    with pytest.raises(FotMobDataMatchesFinalResultSemanticsValidationError):
        dataclasses.replace(value, status_reason="changed")


def test_validation_module_cannot_acquire_network_or_run_downstream() -> None:
    source = Path(validation_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
            imported_modules.add(node.module)

    assert imported_roots.isdisjoint(
        {
            "requests",
            "httpx",
            "aiohttp",
            "playwright",
            "workers",
            "providers",
            "api",
            "services",
            "engine",
            "models",
            "database",
            "repositories",
        }
    )
    assert all(
        token not in module_name
        for module_name in imported_modules
        for token in (
            "score_matrix",
            "probability",
            "pricing",
            "selection",
            "betting",
            "sportybet",
        )
    )
