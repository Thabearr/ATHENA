from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from domain.fotmob_data_matches_capture import (
    manifest_from_mapping,
    sha256_bytes,
    strict_manifest_json_loads,
)
from domain.fotmob_data_matches_ordinary_ft_finished_score_adapter import (
    ADAPTER_SCOPE,
    ADAPTER_STATE,
    DATASET_NAME,
    FUTURE_DERIVED_SOURCE_KEY,
    NEXT_REQUIRED_BOUNDARY,
    ORDINARY_FT_REASON_TUPLE,
    PENALTY_REASON_TUPLE,
    REPOSITORY_MAIN_SHA,
    AdapterFixtureStatus,
    AdapterPairStatus,
    FotMobDataMatchesOrdinaryFtFinishedScoreAdapterError,
    adapt_fotmob_data_matches_ordinary_ft_finished_scores,
    canonical_fotmob_data_matches_ordinary_ft_finished_score_adapter_result_bytes,
    sha256_fotmob_data_matches_ordinary_ft_finished_score_adapter_result,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = (
    ROOT
    / "evidence"
    / "fotmob_data_matches"
    / "pr83_post_finish_pair"
    / "20260814"
)
FIRST_DIR = EVIDENCE_ROOT / "a18e843fabe5aca74846b160"
SECOND_DIR = EVIDENCE_ROOT / "e28d9ce746c1ef9102995517"
ORDINARY_FIXTURE_ID = 5186581
PENALTY_FIXTURE_ID = 5844873

UPSTREAM_BLOBS = {
    "domain/fotmob_data_matches_capture.py": "ca2149395de868104666620173b55a880b10c729",
    "domain/fotmob_data_matches_eliminated_team_id_value_domain_extension.py": "f33dd31aedcd92b5691a3503914ed184d601b493",
    "domain/fotmob_data_matches_status_reason_semantics_protocol.py": "f9546ff05cddfe366d278d4dbdf1020bb7666951",
    "domain/fotmob_data_matches_full_time_score_capability_promotion_assessment.py": "e81be529acc5471e875d4c619e9f77e885217716",
}


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _load_capture(directory: Path) -> tuple[bytes, Any]:
    raw = (directory / "response.json").read_bytes()
    manifest = manifest_from_mapping(
        strict_manifest_json_loads((directory / "manifest.json").read_bytes())
    )
    return raw, manifest


def _find_match(payload: dict[str, Any], fixture_id: int) -> dict[str, Any]:
    for league in payload["leagues"]:
        for match in league["matches"]:
            if match["id"] == fixture_id:
                return match
    raise AssertionError(f"fixture {fixture_id} not found")


def _mutate_capture(
    raw: bytes,
    manifest: Any,
    mutator: Callable[[dict[str, Any]], None],
) -> tuple[bytes, Any]:
    payload = json.loads(raw.decode("utf-8", errors="strict"))
    mutator(payload)
    mutated = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    mutated_manifest = dataclasses.replace(
        manifest,
        content_length=(len(mutated) if manifest.content_length is not None else None),
        raw_sha256=sha256_bytes(mutated),
        raw_size=len(mutated),
    )
    return mutated, mutated_manifest


def _exact_pair():
    first_raw, first_manifest = _load_capture(FIRST_DIR)
    second_raw, second_manifest = _load_capture(SECOND_DIR)
    return first_raw, first_manifest, second_raw, second_manifest


def test_exact_upstream_blob_ancestry_and_adapter_identity() -> None:
    assert REPOSITORY_MAIN_SHA == "c973dabcc43103a9c939706067ca23294f6870ad"
    assert DATASET_NAME == "athena-fotmob-data-matches-ordinary-ft-finished-score-adapter-v1"
    assert ADAPTER_SCOPE == "REUSABLE_REVIEWED_PROSPECTIVE_ORDINARY_FT_FINISHED_SCORE_PAIR_GATE_ONLY"
    assert ADAPTER_STATE == "IMPLEMENTED_REUSABLE_PROSPECTIVE_GATE_NO_CAPABILITY_REGISTRATION"
    assert NEXT_REQUIRED_BOUNDARY == (
        "EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_ORDINARY_FT_FINISHED_SCORE_ADAPTER_VALIDATION"
    )
    for relative, expected in UPSTREAM_BLOBS.items():
        assert _git_blob_sha(ROOT / relative) == expected


def test_exact_pr85_pair_reproduces_28_ordinary_ft_scores_and_excludes_penalty() -> None:
    result = adapt_fotmob_data_matches_ordinary_ft_finished_scores(*_exact_pair())

    assert result.pair_status is AdapterPairStatus.QUALIFIED_WITH_ORDINARY_FT_SCORES
    assert result.qualified_count == 28
    assert result.terminal_candidate_union_count >= 29
    assert tuple(item.fixture_id for item in result.qualified_scores) == tuple(
        sorted(item.fixture_id for item in result.qualified_scores)
    )
    assert PENALTY_FIXTURE_ID not in {item.fixture_id for item in result.qualified_scores}
    assert PENALTY_FIXTURE_ID in result.blocked_fixture_ids_by_status[
        AdapterFixtureStatus.BLOCKED_PENALTY_REASON_REQUIRES_SEPARATE_SCORE_SEMANTICS.value
    ]

    ordinary = next(item for item in result.qualified_scores if item.fixture_id == ORDINARY_FIXTURE_ID)
    assert (ordinary.home_score, ordinary.away_score) == (3, 1)
    assert dict(ordinary.reason) == dict(ORDINARY_FT_REASON_TUPLE)
    assert result.observation_separation_microseconds == 310_605_739
    assert result.request_date == "20260814"
    assert result.timezone == "UTC"
    assert result.ccode3 == "NGA"


def test_exact_pair_preserves_source_and_structural_lineage() -> None:
    first_raw, first_manifest, second_raw, second_manifest = _exact_pair()
    result = adapt_fotmob_data_matches_ordinary_ft_finished_scores(
        first_raw,
        first_manifest,
        second_raw,
        second_manifest,
    )

    assert result.first_raw_sha256 == first_manifest.raw_sha256 == sha256_bytes(first_raw)
    assert result.second_raw_sha256 == second_manifest.raw_sha256 == sha256_bytes(second_raw)
    assert result.first_raw_sha256 != result.second_raw_sha256
    assert result.first_manifest_sha256 != result.second_manifest_sha256
    assert len(result.first_pr89_assessment_sha256) == 64
    assert len(result.second_pr89_assessment_sha256) == 64
    assert result.first_pr89_assessment_sha256 != result.second_pr89_assessment_sha256


def test_adapter_is_deterministic_and_result_is_immutable() -> None:
    first = adapt_fotmob_data_matches_ordinary_ft_finished_scores(*_exact_pair())
    second = adapt_fotmob_data_matches_ordinary_ft_finished_scores(*_exact_pair())
    first_bytes = canonical_fotmob_data_matches_ordinary_ft_finished_score_adapter_result_bytes(first)
    second_bytes = canonical_fotmob_data_matches_ordinary_ft_finished_score_adapter_result_bytes(second)

    assert first_bytes == second_bytes
    assert sha256_fotmob_data_matches_ordinary_ft_finished_score_adapter_result(first) == hashlib.sha256(
        first_bytes
    ).hexdigest()
    assert all(flag is False for flag in first.safety.values())
    assert first.source_capability_registration_performed is False

    with pytest.raises(TypeError):
        first.safety["pricing_authorized"] = True  # type: ignore[index]
    with pytest.raises(TypeError):
        first.blocked_fixture_ids_by_status["X"] = (1,)  # type: ignore[index]
    with pytest.raises(TypeError):
        first.qualified_scores[0].reason["short"] = "X"  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.qualified_scores[0].home_score = 99  # type: ignore[misc]


def test_adapter_does_not_mutate_source_capability_registry() -> None:
    before = dict(SOURCE_CAPABILITY_REGISTRY)
    result = adapt_fotmob_data_matches_ordinary_ft_finished_scores(*_exact_pair())
    after = dict(SOURCE_CAPABILITY_REGISTRY)

    assert before == after
    parent = SOURCE_CAPABILITY_REGISTRY["fotmob_data_matches_reviewed_catalog"]
    assert parent.full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert parent.reliable_fixture_identity is CapabilityAvailability.CONFIRMED
    assert parent.historical_coverage is CapabilityAvailability.UNKNOWN
    assert result.source_capability_registration_performed is False
    assert FUTURE_DERIVED_SOURCE_KEY == "fotmob_data_matches_reviewed_ordinary_ft_finished_score"


def test_same_capture_lineage_fails_closed_before_fixture_review() -> None:
    first_raw, first_manifest, _, _ = _exact_pair()
    with pytest.raises(FotMobDataMatchesOrdinaryFtFinishedScoreAdapterError) as exc:
        adapt_fotmob_data_matches_ordinary_ft_finished_scores(
            first_raw,
            first_manifest,
            first_raw,
            first_manifest,
        )
    assert exc.value.status is AdapterPairStatus.BLOCKED_CAPTURE_LINEAGE_OR_REQUEST_IDENTITY


def test_reversed_capture_order_fails_closed() -> None:
    first_raw, first_manifest, second_raw, second_manifest = _exact_pair()
    with pytest.raises(FotMobDataMatchesOrdinaryFtFinishedScoreAdapterError) as exc:
        adapt_fotmob_data_matches_ordinary_ft_finished_scores(
            second_raw,
            second_manifest,
            first_raw,
            first_manifest,
        )
    assert exc.value.status is AdapterPairStatus.BLOCKED_CAPTURE_OBSERVATION_ORDER_OR_SEPARATION


def test_raw_manifest_mismatch_fails_closed() -> None:
    first_raw, first_manifest, second_raw, second_manifest = _exact_pair()
    with pytest.raises(FotMobDataMatchesOrdinaryFtFinishedScoreAdapterError) as exc:
        adapt_fotmob_data_matches_ordinary_ft_finished_scores(
            first_raw + b" ",
            first_manifest,
            second_raw,
            second_manifest,
        )
    assert exc.value.status is AdapterPairStatus.BLOCKED_CAPTURE_LINEAGE_OR_REQUEST_IDENTITY


def test_unknown_reason_is_blocked_without_discarding_other_qualified_scores() -> None:
    first_raw, first_manifest, second_raw, second_manifest = _exact_pair()

    def mutate(payload: dict[str, Any]) -> None:
        _find_match(payload, ORDINARY_FIXTURE_ID)["status"]["reason"] = {
            "short": "Other",
            "shortKey": "other_short",
            "long": "Other terminal label",
            "longKey": "other_terminal",
        }

    first_raw, first_manifest = _mutate_capture(first_raw, first_manifest, mutate)
    second_raw, second_manifest = _mutate_capture(second_raw, second_manifest, mutate)
    result = adapt_fotmob_data_matches_ordinary_ft_finished_scores(
        first_raw,
        first_manifest,
        second_raw,
        second_manifest,
    )

    assert result.qualified_count == 27
    assert ORDINARY_FIXTURE_ID in result.blocked_fixture_ids_by_status[
        AdapterFixtureStatus.BLOCKED_REASON_TUPLE_UNREVIEWED.value
    ]


def test_reason_mismatch_blocks_fixture() -> None:
    first_raw, first_manifest, second_raw, second_manifest = _exact_pair()

    def mutate(payload: dict[str, Any]) -> None:
        _find_match(payload, ORDINARY_FIXTURE_ID)["status"]["reason"] = dict(PENALTY_REASON_TUPLE)

    second_raw, second_manifest = _mutate_capture(second_raw, second_manifest, mutate)
    result = adapt_fotmob_data_matches_ordinary_ft_finished_scores(
        first_raw,
        first_manifest,
        second_raw,
        second_manifest,
    )
    assert result.qualified_count == 27
    assert ORDINARY_FIXTURE_ID in result.blocked_fixture_ids_by_status[
        AdapterFixtureStatus.BLOCKED_REASON_TUPLE_MISMATCH_OR_PARTIAL.value
    ]


def test_awarded_true_blocks_ordinary_ft_fixture() -> None:
    first_raw, first_manifest, second_raw, second_manifest = _exact_pair()

    def mutate(payload: dict[str, Any]) -> None:
        _find_match(payload, ORDINARY_FIXTURE_ID)["status"]["awarded"] = True

    first_raw, first_manifest = _mutate_capture(first_raw, first_manifest, mutate)
    second_raw, second_manifest = _mutate_capture(second_raw, second_manifest, mutate)
    result = adapt_fotmob_data_matches_ordinary_ft_finished_scores(
        first_raw,
        first_manifest,
        second_raw,
        second_manifest,
    )
    assert result.qualified_count == 27
    assert ORDINARY_FIXTURE_ID in result.blocked_fixture_ids_by_status[
        AdapterFixtureStatus.BLOCKED_AWARDED_RESULT_REQUIRES_SEPARATE_REVIEW.value
    ]


def test_pen_score_presence_blocks_ordinary_ft_fixture_even_when_zero() -> None:
    first_raw, first_manifest, second_raw, second_manifest = _exact_pair()

    def mutate(payload: dict[str, Any]) -> None:
        _find_match(payload, ORDINARY_FIXTURE_ID)["home"]["penScore"] = 0

    first_raw, first_manifest = _mutate_capture(first_raw, first_manifest, mutate)
    second_raw, second_manifest = _mutate_capture(second_raw, second_manifest, mutate)
    result = adapt_fotmob_data_matches_ordinary_ft_finished_scores(
        first_raw,
        first_manifest,
        second_raw,
        second_manifest,
    )
    assert result.qualified_count == 27
    assert ORDINARY_FIXTURE_ID in result.blocked_fixture_ids_by_status[
        AdapterFixtureStatus.BLOCKED_PEN_SCORE_PRESENT_REQUIRES_SEPARATE_REVIEW.value
    ]


def test_post_finish_score_instability_blocks_fixture() -> None:
    first_raw, first_manifest, second_raw, second_manifest = _exact_pair()

    def mutate(payload: dict[str, Any]) -> None:
        match = _find_match(payload, ORDINARY_FIXTURE_ID)
        match["home"]["score"] += 1

    second_raw, second_manifest = _mutate_capture(second_raw, second_manifest, mutate)
    result = adapt_fotmob_data_matches_ordinary_ft_finished_scores(
        first_raw,
        first_manifest,
        second_raw,
        second_manifest,
    )
    assert result.qualified_count == 27
    assert ORDINARY_FIXTURE_ID in result.blocked_fixture_ids_by_status[
        AdapterFixtureStatus.BLOCKED_POST_FINISH_SCORE_INSTABILITY.value
    ]


def test_fixture_identity_drift_blocks_fixture() -> None:
    first_raw, first_manifest, second_raw, second_manifest = _exact_pair()

    def mutate(payload: dict[str, Any]) -> None:
        match = _find_match(payload, ORDINARY_FIXTURE_ID)
        match["away"]["id"] += 1_000_000

    second_raw, second_manifest = _mutate_capture(second_raw, second_manifest, mutate)
    result = adapt_fotmob_data_matches_ordinary_ft_finished_scores(
        first_raw,
        first_manifest,
        second_raw,
        second_manifest,
    )
    assert result.qualified_count == 27
    assert ORDINARY_FIXTURE_ID in result.blocked_fixture_ids_by_status[
        AdapterFixtureStatus.BLOCKED_FIXTURE_IDENTITY_DRIFT.value
    ]


def test_finished_in_only_one_capture_is_insufficient_repeat_evidence() -> None:
    first_raw, first_manifest, second_raw, second_manifest = _exact_pair()

    def mutate(payload: dict[str, Any]) -> None:
        _find_match(payload, ORDINARY_FIXTURE_ID)["status"]["finished"] = False

    second_raw, second_manifest = _mutate_capture(second_raw, second_manifest, mutate)
    result = adapt_fotmob_data_matches_ordinary_ft_finished_scores(
        first_raw,
        first_manifest,
        second_raw,
        second_manifest,
    )
    assert result.qualified_count == 27
    assert ORDINARY_FIXTURE_ID in result.blocked_fixture_ids_by_status[
        AdapterFixtureStatus.BLOCKED_INSUFFICIENT_REPEAT_OBSERVATIONS.value
    ]


def test_adapter_module_imports_no_network_or_downstream_runtime_modules() -> None:
    path = ROOT / "domain" / "fotmob_data_matches_ordinary_ft_finished_score_adapter.py"
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
