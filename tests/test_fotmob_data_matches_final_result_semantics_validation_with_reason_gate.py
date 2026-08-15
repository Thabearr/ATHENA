from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

import domain.fotmob_data_matches_final_result_semantics_validation_with_reason_gate as validation
from domain.fotmob_data_matches_capture import verify_data_matches_capture_directory
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = ROOT / "evidence" / "fotmob_data_matches" / "pr83_post_finish_pair"
DATE_ROOT = EVIDENCE_ROOT / "20260814"
FIRST = "a18e843fabe5aca74846b160"
SECOND = "e28d9ce746c1ef9102995517"


def _blob(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _capture(capture_id: str):
    directory = DATE_ROOT / capture_id
    manifest = verify_data_matches_capture_directory(
        directory,
        allowed_root=EVIDENCE_ROOT,
        require_network_acquisition_performed=True,
    )
    return (directory / "response.json").read_bytes(), manifest


def _execute():
    first_raw, first_manifest = _capture(FIRST)
    second_raw, second_manifest = _capture(SECOND)
    return validation.execute_fotmob_data_matches_final_result_semantics_validation_with_reason_gate(
        first_raw,
        first_manifest,
        second_raw,
        second_manifest,
    )


def test_exact_merged_ancestry_blobs_are_frozen() -> None:
    assert validation.REPOSITORY_MAIN_SHA == "50025517298ff5a05fdb708396b12f216f2e7e1e"
    assert (
        _blob(ROOT / "domain" / "fotmob_data_matches_final_result_semantics_protocol.py")
        == validation.PR83_PROTOCOL_BLOB_SHA
        == "25f8045524badcb90239df59ac9c47f36fcffe34"
    )
    assert (
        _blob(ROOT / "domain" / "fotmob_data_matches_eliminated_team_id_value_domain_extension.py")
        == validation.PR89_IMPLEMENTATION_BLOB_SHA
        == "f33dd31aedcd92b5691a3503914ed184d601b493"
    )
    assert (
        _blob(ROOT / "domain" / "fotmob_data_matches_status_reason_semantics_protocol.py")
        == validation.PR90_PROTOCOL_BLOB_SHA
        == "f9546ff05cddfe366d278d4dbdf1020bb7666951"
    )
    assert (
        _blob(ROOT / "domain" / "fotmob_data_matches_status_reason_semantics_validation.py")
        == validation.PR91_VALIDATION_BLOB_SHA
        == "a663a2c2879cb70dbd1f31f0f8bbe4ff8f1034d6"
    )
    assert validation.SOURCE_CAPABILITIES_BLOB_SHA == (
        "ffd9730d6675a7dbcc9e8622d6e9844b772b6f96"
    )


def test_exact_pair_qualifies_only_the_pr91_ordinary_ft_subset() -> None:
    receipt = _execute()
    assert receipt["execution_state"] == validation.EXECUTION_STATE
    assert receipt["stable_finished_identity_score_pair_count"] == 29
    assert receipt["pr91_reason_qualified_count"] == 28
    assert receipt["pr91_penalty_blocked_count"] == 1
    assert receipt["final_result_execution_input_count"] == 28
    assert receipt["qualified_stable_source_finished_score_count"] == 28
    assert receipt["nonqualified_execution_input_count"] == 0
    assert receipt["qualified_status"] == (
        "QUALIFIED_STABLE_SOURCE_FINISHED_SCORE_SEMANTICS"
    )


def test_semantic_scope_is_source_reported_finished_score_only() -> None:
    receipt = _execute()
    assert receipt["ordinary_ft_source_reported_finished_score_semantics_qualified"] is True
    assert receipt["regulation_time_score_semantics_qualified"] is False
    assert receipt["extra_time_score_semantics_qualified"] is False
    assert receipt["penalty_score_semantics_qualified"] is False
    assert receipt["bookmaker_settlement_semantics_qualified"] is False
    assert receipt["status_reason_semantics_globally_qualified"] is False
    assert receipt["global_source_full_time_score_capability_promoted"] is False
    assert receipt["penalty_fixture_id"] == 5844873
    assert dict(receipt["ordinary_ft_reason_tuple"]) == {
        "short": "FT",
        "shortKey": "fulltime_short",
        "long": "Full-Time",
        "longKey": "finished",
    }
    assert receipt["semantic_scope_rule"] == validation.SEMANTIC_SCOPE_RULE


def test_exact_pr91_receipt_identity_is_revalidated_before_qualification() -> None:
    assert validation.PR91_RECEIPT_SHA256 == (
        "3e8537a4ddfd2d558a493ace74bd302a7d9f835c4768dc05049682e8ddf94abf"
    )
    assert validation.PR91_RECEIPT_SIZE == 3307
    assert validation.FINAL_RESULT_EXECUTION_INPUT_COUNT == 28
    assert validation.QUALIFIED_STABLE_SOURCE_FINISHED_SCORE_COUNT == 28
    assert validation.NONQUALIFIED_EXECUTION_INPUT_COUNT == 0


def test_canonical_pr92_receipt_identity_is_exact() -> None:
    receipt = _execute()
    exact = validation.canonical_fotmob_data_matches_final_result_semantics_reason_gate_validation_receipt_bytes(
        receipt
    )
    assert hashlib.sha256(exact).hexdigest() == validation.RECEIPT_SHA256 == (
        "b821d5211de1e2a058b85ac1ca2ac50bdd0d3b577b54aa40c86ed6773bcb0c86"
    )
    assert len(exact) == validation.RECEIPT_SIZE == 3561


def test_source_capability_and_all_downstream_authority_remain_fail_closed() -> None:
    receipt = _execute()
    assert receipt["source_capability_full_time_score"] == "NOT_CAPTURED"
    assert receipt["historical_coverage"] == "UNKNOWN"
    assert all(type(flag) is bool and flag is False for flag in receipt["safety"].values())
    capability = SOURCE_CAPABILITY_REGISTRY["fotmob_data_matches_reviewed_catalog"]
    assert capability.full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert capability.historical_coverage is CapabilityAvailability.UNKNOWN
    assert receipt["next_required_boundary"] == validation.NEXT_REQUIRED_BOUNDARY == (
        "PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_FULL_TIME_SCORE_CAPABILITY_PROMOTION_PROTOCOL"
    )


def test_receipt_is_deeply_immutable_and_mutation_fails_closed() -> None:
    receipt = _execute()
    with pytest.raises(TypeError):
        receipt["global_source_full_time_score_capability_promoted"] = True
    with pytest.raises(TypeError):
        receipt["ordinary_ft_reason_tuple"]["short"] = "X"
    with pytest.raises(TypeError):
        receipt["safety"]["bet_authorized"] = True

    mutated = dict(receipt)
    mutated["qualified_stable_source_finished_score_count"] = 27
    with pytest.raises(
        validation.FotMobDataMatchesFinalResultSemanticsReasonGateValidationError
    ):
        validation.canonical_fotmob_data_matches_final_result_semantics_reason_gate_validation_receipt_bytes(
            mutated
        )


def test_capture_lineage_or_order_mutation_fails_closed() -> None:
    first_raw, first_manifest = _capture(FIRST)
    second_raw, second_manifest = _capture(SECOND)
    with pytest.raises(
        validation.FotMobDataMatchesFinalResultSemanticsReasonGateValidationError
    ):
        validation.execute_fotmob_data_matches_final_result_semantics_validation_with_reason_gate(
            first_raw + b" ",
            first_manifest,
            second_raw,
            second_manifest,
        )
    with pytest.raises(
        validation.FotMobDataMatchesFinalResultSemanticsReasonGateValidationError
    ):
        validation.execute_fotmob_data_matches_final_result_semantics_validation_with_reason_gate(
            second_raw,
            second_manifest,
            first_raw,
            first_manifest,
        )


def test_validation_imports_no_network_or_downstream_runtime_modules() -> None:
    tree = ast.parse(
        (
            ROOT
            / "domain"
            / "fotmob_data_matches_final_result_semantics_validation_with_reason_gate.py"
        ).read_text(encoding="utf-8")
    )
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert roots.isdisjoint(
        {"requests", "httpx", "aiohttp", "providers", "engine", "models", "services", "workers"}
    )
