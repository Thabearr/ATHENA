from __future__ import annotations

import ast
import dataclasses
import hashlib
from pathlib import Path

import pytest

from domain.fotmob_data_matches_capture import manifest_from_mapping, strict_manifest_json_loads
from domain.fotmob_data_matches_ordinary_ft_finished_score_adapter_validation import (
    ADAPTER_RESULT_SHA256,
    ADAPTER_RESULT_SIZE,
    BLOCKED_FIXTURE_IDS_BY_STATUS,
    DATASET_NAME,
    EXECUTION_SCOPE,
    EXECUTION_STATE,
    NEXT_REQUIRED_BOUNDARY,
    PENALTY_FIXTURE_ID,
    PR95_ADAPTER_BLOB_SHA,
    QUALIFIED_COUNT,
    QUALIFIED_SCORES_PROJECTION_SHA256,
    RECEIPT_SHA256,
    RECEIPT_SIZE,
    REPOSITORY_MAIN_SHA,
    SOURCE_CAPABILITIES_BLOB_SHA,
    TERMINAL_CANDIDATE_UNION_COUNT,
    FotMobDataMatchesOrdinaryFtFinishedScoreAdapterValidationError,
    canonical_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation_receipt_bytes,
    execute_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation,
    sha256_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation_receipt,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = ROOT / "evidence" / "fotmob_data_matches" / "pr83_post_finish_pair" / "20260814"
FIRST_DIR = EVIDENCE_ROOT / "a18e843fabe5aca74846b160"
SECOND_DIR = EVIDENCE_ROOT / "e28d9ce746c1ef9102995517"
PROPOSED_SOURCE_KEY = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"
PENALTY_STATUS = "BLOCKED_PENALTY_REASON_REQUIRES_SEPARATE_SCORE_SEMANTICS"

UPSTREAM_BLOBS = {
    "domain/fotmob_data_matches_ordinary_ft_finished_score_adapter.py": "868563206e09010fce74b4ba7954028930baad54",
    "domain/fotmob_data_matches_post_finish_capture_pair_evidence.py": "7b74e9893071ef47ea425b4f106d92b0c5e1ddc2",
}
HISTORICAL_SOURCE_CAPABILITIES_BLOB = "ffd9730d6675a7dbcc9e8622d6e9844b772b6f96"


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _load(directory: Path):
    raw = (directory / "response.json").read_bytes()
    manifest = manifest_from_mapping(strict_manifest_json_loads((directory / "manifest.json").read_bytes()))
    return raw, manifest


def _exact_pair():
    first_raw, first_manifest = _load(FIRST_DIR)
    second_raw, second_manifest = _load(SECOND_DIR)
    return first_raw, first_manifest, second_raw, second_manifest


def _receipt():
    return execute_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation(*_exact_pair())


def test_exact_identity_and_upstream_blob_ancestry() -> None:
    assert REPOSITORY_MAIN_SHA == "d836e6bafb71bdefbc47ae00895229eaa0a136a5"
    assert DATASET_NAME == "athena-fotmob-data-matches-ordinary-ft-finished-score-adapter-validation-v1"
    assert EXECUTION_SCOPE == "EXECUTE_PR95_REUSABLE_ADAPTER_AGAINST_EXACT_PRESERVED_PR85_PAIR_ONLY"
    assert EXECUTION_STATE == "EXECUTED_EXACT_PR85_PAIR_28_ORDINARY_FT_SCORES_QUALIFIED_PENALTY_BLOCKED"
    assert NEXT_REQUIRED_BOUNDARY == (
        "EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_FULL_TIME_SCORE_CAPABILITY_PROMOTION_ASSESSMENT_WITH_VALIDATED_ADAPTER"
    )
    assert PR95_ADAPTER_BLOB_SHA == UPSTREAM_BLOBS["domain/fotmob_data_matches_ordinary_ft_finished_score_adapter.py"]
    for relative, expected in UPSTREAM_BLOBS.items():
        assert _git_blob_sha(ROOT / relative) == expected
    assert SOURCE_CAPABILITIES_BLOB_SHA == HISTORICAL_SOURCE_CAPABILITIES_BLOB


def test_exact_pr85_pair_freezes_validated_adapter_result() -> None:
    receipt = _receipt()
    assert receipt["adapter_validation_qualified"] is True
    assert receipt["pair_status"] == "QUALIFIED_WITH_ORDINARY_FT_SCORES"
    assert receipt["adapter_result_sha256"] == ADAPTER_RESULT_SHA256 == (
        "7e3fcb2c8a4fa8f883ec7dcac2fd15ea8d2f1aa359c5c5f42ab7eaf604bdce27"
    )
    assert receipt["adapter_result_size"] == ADAPTER_RESULT_SIZE == 22570
    assert receipt["qualified_scores_projection_sha256"] == QUALIFIED_SCORES_PROJECTION_SHA256 == (
        "ffdb20556808a1a6459d959b050e3aa5780f3c017d6971adf0c17a3c91ce03ab"
    )
    assert receipt["terminal_candidate_union_count"] == TERMINAL_CANDIDATE_UNION_COUNT == 29
    assert receipt["qualified_count"] == QUALIFIED_COUNT == 28
    assert dict(receipt["blocked_fixture_ids_by_status"]) == dict(BLOCKED_FIXTURE_IDS_BY_STATUS) == {
        PENALTY_STATUS: (PENALTY_FIXTURE_ID,)
    }
    assert receipt["penalty_fixture_id"] == PENALTY_FIXTURE_ID == 5844873
    assert receipt["ordinary_anchor_fixture_id"] == 5186581
    assert receipt["ordinary_anchor_score"] == (3, 1)


def test_receipt_canonical_identity_is_exact_and_deterministic() -> None:
    first = _receipt()
    second = _receipt()
    first_bytes = canonical_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation_receipt_bytes(first)
    second_bytes = canonical_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation_receipt_bytes(second)
    assert first_bytes == second_bytes
    assert len(first_bytes) == RECEIPT_SIZE == 3610
    assert hashlib.sha256(first_bytes).hexdigest() == RECEIPT_SHA256 == (
        "09dd9fdff1eddb7b421e968c8de93262b09ce526adeb3d3b95050ddf1f2d4562"
    )
    assert sha256_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation_receipt(first) == RECEIPT_SHA256


def test_receipt_and_nested_boundaries_are_immutable() -> None:
    receipt = _receipt()
    with pytest.raises(TypeError):
        receipt["qualified_count"] = 99  # type: ignore[index]
    with pytest.raises(TypeError):
        receipt["blocked_fixture_ids_by_status"][PENALTY_STATUS] = ()  # type: ignore[index]
    with pytest.raises(TypeError):
        receipt["safety"]["pricing_authorized"] = True  # type: ignore[index]


def test_canonicalizer_rejects_security_and_scope_mutations() -> None:
    receipt = _receipt()
    base = dict(receipt)
    mutations = []

    changed = dict(base)
    changed["adapter_result_sha256"] = "0" * 64
    mutations.append(changed)

    changed = dict(base)
    changed["terminal_candidate_union_count"] = 30
    mutations.append(changed)

    changed = dict(base)
    changed["blocked_fixture_ids_by_status"] = {}
    mutations.append(changed)

    changed = dict(base)
    changed["adapter_validation_qualified"] = False
    mutations.append(changed)

    changed = dict(base)
    changed["source_capability_registration_performed"] = True
    mutations.append(changed)

    changed = dict(base)
    changed["proposed_source_key_registered"] = True
    mutations.append(changed)

    changed = dict(base)
    changed["next_required_boundary"] = "BYPASS"
    mutations.append(changed)

    changed = dict(base)
    changed_safety = dict(receipt["safety"])
    changed_safety["pricing_authorized"] = True
    changed["safety"] = changed_safety
    mutations.append(changed)

    for mutated in mutations:
        with pytest.raises(FotMobDataMatchesOrdinaryFtFinishedScoreAdapterValidationError):
            canonical_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation_receipt_bytes(mutated)


def test_exact_capture_lineage_and_order_fail_closed() -> None:
    first_raw, first_manifest, second_raw, second_manifest = _exact_pair()
    bad_first = dataclasses.replace(first_manifest, raw_sha256="0" * 64)
    with pytest.raises(FotMobDataMatchesOrdinaryFtFinishedScoreAdapterValidationError):
        execute_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation(
            first_raw, bad_first, second_raw, second_manifest
        )
    with pytest.raises(FotMobDataMatchesOrdinaryFtFinishedScoreAdapterValidationError):
        execute_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation(
            second_raw, second_manifest, first_raw, first_manifest
        )


def test_historical_receipt_survives_later_reviewed_registration() -> None:
    receipt = _receipt()
    parent = SOURCE_CAPABILITY_REGISTRY["fotmob_data_matches_reviewed_catalog"]
    derived = SOURCE_CAPABILITY_REGISTRY[PROPOSED_SOURCE_KEY]
    assert parent.reliable_fixture_identity is CapabilityAvailability.CONFIRMED
    assert parent.full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert parent.historical_coverage is CapabilityAvailability.UNKNOWN
    assert derived.full_time_score is CapabilityAvailability.CONFIRMED
    assert receipt["source_capability_registration_performed"] is False
    assert receipt["proposed_source_key_registered"] is False
    assert receipt["parent_source_full_time_score"] == "NOT_CAPTURED"
    assert receipt["parent_source_historical_coverage"] == "UNKNOWN"
    assert all(flag is False for flag in receipt["safety"].values())


def test_validation_module_has_no_network_or_downstream_execution_imports() -> None:
    path = ROOT / "domain" / "fotmob_data_matches_ordinary_ft_finished_score_adapter_validation.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint({"requests", "httpx", "aiohttp", "playwright", "providers", "engine", "services", "workers"})
