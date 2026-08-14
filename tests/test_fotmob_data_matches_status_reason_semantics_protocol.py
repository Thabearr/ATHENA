from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from domain.fotmob_data_matches_capture import (
    sha256_data_matches_capture_manifest,
    verify_data_matches_capture_directory,
)
from domain.fotmob_data_matches_eliminated_team_id_value_domain_extension import (
    EliminatedTeamIdValueDomainStatus,
    assess_fotmob_data_matches_eliminated_team_id_value_domain,
)
from domain.fotmob_data_matches_status_reason_semantics_protocol import (
    NEXT_REQUIRED_BOUNDARY,
    ORDINARY_FT_REASON_PAIR_COUNT,
    ORDINARY_FT_REASON_TUPLE,
    PENALTY_REASON_PAIR_COUNT,
    PENALTY_REASON_TUPLE,
    PROTOCOL_ID,
    PROTOCOL_SCOPE,
    PROTOCOL_SHA256,
    PROTOCOL_SIZE,
    PROTOCOL_STATE,
    QUALIFICATION_REQUIREMENTS,
    REPOSITORY_MAIN_SHA,
    STABLE_FINISHED_IDENTITY_SCORE_PAIR_COUNT,
    STATUS_VOCABULARY,
    FotMobDataMatchesStatusReasonSemanticsProtocolError,
    build_fotmob_data_matches_status_reason_semantics_protocol,
    canonical_fotmob_data_matches_status_reason_semantics_protocol_bytes,
    revalidate_fotmob_data_matches_status_reason_semantics_protocol,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = ROOT / "evidence" / "fotmob_data_matches" / "pr83_post_finish_pair"
DATE_ROOT = EVIDENCE_ROOT / "20260814"
FIRST_CAPTURE_ID = "a18e843fabe5aca74846b160"
SECOND_CAPTURE_ID = "e28d9ce746c1ef9102995517"
FIRST_RAW_SHA256 = "fbcf24729973dbe7153c87fe9f37bd988aaca14ad10cce6b260ac7df650ff80f"
SECOND_RAW_SHA256 = "175c6f94788fbf676e08a288ff0c46a995cd8798d60e4bc5044076e3c9713f8d"
FIRST_MANIFEST_SHA256 = "27bfb5dc90c67a305bdb045a7ff33010d87c4109925384d3e6d2a6e058d7b302"
SECOND_MANIFEST_SHA256 = "d60501a5b7b1b4e5c810a0a0463bdcecb3a0b806110ad4542c314f8fe536824e"
PR83_BLOB = "25f8045524badcb90239df59ac9c47f36fcffe34"
PR85_BLOB = "7b74e9893071ef47ea425b4f106d92b0c5e1ddc2"
PR89_BLOB = "f33dd31aedcd92b5691a3503914ed184d601b493"
SOURCE_CAPABILITIES_BLOB = "ffd9730d6675a7dbcc9e8622d6e9844b772b6f96"
PENALTY_FIXTURE_ID = 5844873


SAFETY_KEYS = {
    "network_acquisition_authorized",
    "status_reason_semantics_execution_authorized",
    "status_reason_semantics_qualified",
    "final_result_semantics_execution_authorized",
    "final_result_semantics_qualified",
    "source_capability_update_authorized",
    "source_history_adapter_approved",
    "source_history_completeness_proven",
    "pr80_constructor_input_authorized",
    "successor_live_inputs_qualified",
    "successor_candidate_approved",
    "expected_goals_transform_approved",
    "expected_goals_production_authorized",
    "score_matrix_authorized",
    "probability_inference_authorized",
    "probability_adjustment_authorized",
    "calibration_for_production_authorized",
    "pricing_authorized",
    "market_activation_authorized",
    "selection_authorized",
    "production_approval_authorized",
    "bet_authorized",
}


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _load_capture(capture_id: str):
    capture_dir = DATE_ROOT / capture_id
    manifest = verify_data_matches_capture_directory(
        capture_dir,
        allowed_root=EVIDENCE_ROOT,
        require_network_acquisition_performed=True,
    )
    return (capture_dir / "response.json").read_bytes(), manifest


def _match_index(raw: bytes) -> dict[int, dict[str, Any]]:
    payload = json.loads(raw)
    result: dict[int, dict[str, Any]] = {}
    for league in payload["leagues"]:
        for match in league["matches"]:
            match_id = match["id"]
            assert type(match_id) is int
            assert match_id not in result
            result[match_id] = match
    return result


def _stable_finished_pairs() -> list[tuple[dict[str, Any], dict[str, Any]]]:
    first_raw, _ = _load_capture(FIRST_CAPTURE_ID)
    second_raw, _ = _load_capture(SECOND_CAPTURE_ID)
    first = _match_index(first_raw)
    second = _match_index(second_raw)
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for match_id in sorted(set(first) & set(second)):
        left = first[match_id]
        right = second[match_id]
        left_status = left["status"]
        right_status = right["status"]
        if not (
            left_status.get("finished") is True
            and left_status.get("started") is True
            and left_status.get("cancelled") is False
            and right_status.get("finished") is True
            and right_status.get("started") is True
            and right_status.get("cancelled") is False
        ):
            continue
        if (
            left["leagueId"],
            left["home"]["id"],
            left["away"]["id"],
            left_status["utcTime"],
            left["home"]["score"],
            left["away"]["score"],
        ) != (
            right["leagueId"],
            right["home"]["id"],
            right["away"]["id"],
            right_status["utcTime"],
            right["home"]["score"],
            right["away"]["score"],
        ):
            continue
        pairs.append((left, right))
    return pairs


def _reason_tuple(match: dict[str, Any]) -> dict[str, Any]:
    return dict(match["status"]["reason"])


def test_exact_merged_main_and_upstream_blob_ancestry() -> None:
    assert REPOSITORY_MAIN_SHA == "812e9f36bcffabf5c583ea1af1dd138acf23240a"
    assert _git_blob_sha(ROOT / "domain" / "fotmob_data_matches_final_result_semantics_protocol.py") == PR83_BLOB
    assert _git_blob_sha(ROOT / "domain" / "fotmob_data_matches_post_finish_capture_pair_evidence.py") == PR85_BLOB
    assert _git_blob_sha(ROOT / "domain" / "fotmob_data_matches_eliminated_team_id_value_domain_extension.py") == PR89_BLOB
    assert _git_blob_sha(ROOT / "domain" / "source_capabilities.py") == SOURCE_CAPABILITIES_BLOB


def test_exact_pr85_capture_lineage_and_pr89_structural_qualification() -> None:
    expected = (
        (FIRST_CAPTURE_ID, FIRST_RAW_SHA256, FIRST_MANIFEST_SHA256),
        (SECOND_CAPTURE_ID, SECOND_RAW_SHA256, SECOND_MANIFEST_SHA256),
    )
    for capture_id, raw_sha, manifest_sha in expected:
        raw, manifest = _load_capture(capture_id)
        assert hashlib.sha256(raw).hexdigest() == raw_sha
        assert manifest.raw_sha256 == raw_sha
        assert sha256_data_matches_capture_manifest(manifest) == manifest_sha
        assessment = assess_fotmob_data_matches_eliminated_team_id_value_domain(raw, manifest)
        assert assessment.status is EliminatedTeamIdValueDomainStatus.QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN
        assert assessment.pr87_match_count == 183
        assert assessment.status_reason_semantics_qualified is False
        assert assessment.final_result_semantics_qualified is False


def test_exact_stable_finished_reason_distribution_is_frozen() -> None:
    pairs = _stable_finished_pairs()
    assert len(pairs) == STABLE_FINISHED_IDENTITY_SCORE_PAIR_COUNT == 29

    ordinary = []
    penalty = []
    other = []
    for left, right in pairs:
        left_reason = _reason_tuple(left)
        right_reason = _reason_tuple(right)
        assert left_reason == right_reason
        if left_reason == dict(ORDINARY_FT_REASON_TUPLE):
            ordinary.append((left, right))
        elif left_reason == dict(PENALTY_REASON_TUPLE):
            penalty.append((left, right))
        else:
            other.append((left, right))

    assert len(ordinary) == ORDINARY_FT_REASON_PAIR_COUNT == 28
    assert len(penalty) == PENALTY_REASON_PAIR_COUNT == 1
    assert other == []


def test_ordinary_ft_candidates_satisfy_preregistered_awarded_and_pen_score_guards() -> None:
    ordinary = [
        pair
        for pair in _stable_finished_pairs()
        if _reason_tuple(pair[0]) == dict(ORDINARY_FT_REASON_TUPLE)
    ]
    assert len(ordinary) == 28
    for left, right in ordinary:
        for match in (left, right):
            assert match["status"].get("awarded", False) is False
            assert "penScore" not in match["home"]
            assert "penScore" not in match["away"]


def test_penalty_candidate_is_exact_evidence_for_separate_score_semantics() -> None:
    pairs = [
        pair
        for pair in _stable_finished_pairs()
        if _reason_tuple(pair[0]) == dict(PENALTY_REASON_TUPLE)
    ]
    assert len(pairs) == 1
    left, right = pairs[0]
    for match in (left, right):
        assert match["id"] == PENALTY_FIXTURE_ID
        assert match["home"]["score"] == 1
        assert match["away"]["score"] == 1
        assert match["home"]["penScore"] == 5
        assert match["away"]["penScore"] == 6
        assert match["eliminatedTeamId"] == 6576
        assert match["status"].get("awarded") is False
        assert match["statusId"] == 13


def test_protocol_identity_scope_and_next_boundary_are_exact() -> None:
    value = build_fotmob_data_matches_status_reason_semantics_protocol()
    exact = canonical_fotmob_data_matches_status_reason_semantics_protocol_bytes(value)
    assert PROTOCOL_ID == "FOTMOB_DATA_MATCHES_STATUS_REASON_SEMANTICS_PROTOCOL_V1"
    assert PROTOCOL_SCOPE == "PRE_REGISTERED_REVIEWED_PR83_STATUS_REASON_GATE_ONLY"
    assert PROTOCOL_STATE == "PRE_REGISTERED_NOT_EXECUTED_STATUS_REASON_GATE_UNQUALIFIED"
    assert hashlib.sha256(exact).hexdigest() == PROTOCOL_SHA256
    assert len(exact) == PROTOCOL_SIZE == 5602
    assert revalidate_fotmob_data_matches_status_reason_semantics_protocol(value) == value
    assert value.next_required_boundary == NEXT_REQUIRED_BOUNDARY == (
        "EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_STATUS_REASON_SEMANTICS_VALIDATION"
    )


def test_protocol_is_narrow_about_semantic_authority() -> None:
    value = build_fotmob_data_matches_status_reason_semantics_protocol()
    assert value.ordinary_ft_disposition == (
        "ALLOW_PR83_REASON_GATE_FOR_SOURCE_REPORTED_FINISHED_SCORE_ONLY_IF_ALL_OTHER_PR83_AND_THIS_PROTOCOL_GATES_PASS"
    )
    assert value.penalty_disposition == (
        "BLOCK_PLAIN_HOME_AWAY_SCORE_SEMANTICS_PENDING_SEPARATE_PENALTY_SCORE_REVIEW"
    )
    assert "ALLOW_ONLY_THE_EXACT_ORDINARY_FT_TUPLE_TO_CLEAR_THE_REASON_GATE" in QUALIFICATION_REQUIREMENTS
    assert "BLOCK_THE_EXACT_PENALTY_REASON_TUPLE_FROM_PLAIN_HOME_AWAY_SCORE_SEMANTICS" in QUALIFICATION_REQUIREMENTS
    assert "DO_NOT_QUALIFY_REGULATION_TIME_EXTRA_TIME_PENALTY_SETTLEMENT_OR_BOOKMAKER_RULES" in QUALIFICATION_REQUIREMENTS


def test_status_vocabulary_and_all_safety_flags_are_exact() -> None:
    value = build_fotmob_data_matches_status_reason_semantics_protocol()
    assert value.status_vocabulary == STATUS_VOCABULARY
    assert set(value.safety) == SAFETY_KEYS
    assert all(type(flag) is bool and flag is False for flag in value.safety.values())
    capability = SOURCE_CAPABILITY_REGISTRY["fotmob_data_matches_reviewed_catalog"]
    assert capability.reliable_fixture_identity is CapabilityAvailability.CONFIRMED
    assert capability.full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert capability.historical_coverage is CapabilityAvailability.UNKNOWN


@pytest.mark.parametrize(
    ("field", "bad"),
    (
        ("schema_version", True),
        ("stable_finished_identity_score_pair_count", 28),
        ("ordinary_ft_reason_pair_count", 27),
        ("penalty_reason_pair_count", 2),
        ("penalty_home_pen_score", -1),
        ("next_required_boundary", "SKIP_TO_PRODUCTION"),
    ),
)
def test_mutations_fail_closed(field: str, bad: Any) -> None:
    value = build_fotmob_data_matches_status_reason_semantics_protocol()
    with pytest.raises(FotMobDataMatchesStatusReasonSemanticsProtocolError):
        dataclasses.replace(value, **{field: bad})


def test_reason_tuple_and_safety_mutations_fail_closed() -> None:
    value = build_fotmob_data_matches_status_reason_semantics_protocol()
    changed_reason = dict(value.ordinary_ft_reason_tuple)
    changed_reason["short"] = "ft"
    with pytest.raises(FotMobDataMatchesStatusReasonSemanticsProtocolError):
        dataclasses.replace(value, ordinary_ft_reason_tuple=changed_reason)

    changed_safety = dict(value.safety)
    changed_safety["final_result_semantics_qualified"] = True
    with pytest.raises(FotMobDataMatchesStatusReasonSemanticsProtocolError):
        dataclasses.replace(value, safety=changed_safety)
    with pytest.raises(TypeError):
        value.safety["bet_authorized"] = True  # type: ignore[index]


def test_protocol_has_no_network_or_downstream_runtime_imports() -> None:
    path = ROOT / "domain" / "fotmob_data_matches_status_reason_semantics_protocol.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
    assert imported_roots.isdisjoint(
        {"requests", "httpx", "aiohttp", "providers", "engine", "models", "services", "workers"}
    )
