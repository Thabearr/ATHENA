from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import domain.fotmob_data_matches_post_finish_capture_pair_evidence as evidence_module
from domain.fotmob_data_matches_capture import (
    manifest_from_mapping,
    sha256_data_matches_capture_manifest,
    strict_manifest_json_loads,
)
from domain.fotmob_data_matches_post_finish_capture_pair_evidence import (
    EVIDENCE_SHA256,
    EVIDENCE_SIZE,
    EVIDENCE_STATE,
    NEXT_REQUIRED_BOUNDARY,
    FotMobDataMatchesPostFinishCapturePairEvidenceError,
    build_fotmob_data_matches_post_finish_capture_pair_evidence,
    canonical_fotmob_data_matches_post_finish_capture_pair_evidence_bytes,
    revalidate_fotmob_data_matches_post_finish_capture_pair_evidence,
)
from domain.fotmob_data_matches_schema import (
    HALFS_KEYS,
    STATUS_ALLOWED_KEYS,
    TEAM_KEYS,
    FotMobDataMatchesSchemaError,
    assess_fotmob_data_matches_schema,
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


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_capture(directory: Path) -> tuple[bytes, Any, dict[str, Any]]:
    raw = (directory / "response.json").read_bytes()
    manifest_raw = (directory / "manifest.json").read_bytes()
    manifest = manifest_from_mapping(strict_manifest_json_loads(manifest_raw))
    payload = json.loads(raw.decode("utf-8", errors="strict"))
    return raw, manifest, payload


def _observed(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def _kickoff(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def _rows(payload: dict[str, Any]) -> dict[int, tuple[dict[str, Any], dict[str, Any]]]:
    result: dict[int, tuple[dict[str, Any], dict[str, Any]]] = {}
    for league in payload["leagues"]:
        for match in league["matches"]:
            result[match["id"]] = (league, match)
    return result


def _key_unions(payload: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    team_keys: set[str] = set()
    status_keys: set[str] = set()
    halfs_keys: set[str] = set()
    for league in payload["leagues"]:
        for match in league["matches"]:
            team_keys.update(match["home"])
            team_keys.update(match["away"])
            status_keys.update(match["status"])
            halfs_keys.update(match["status"]["halfs"])
    return team_keys, status_keys, halfs_keys


def _stable_finished_pairs(
    first_payload: dict[str, Any],
    second_payload: dict[str, Any],
    first_observed_at: str,
    second_observed_at: str,
) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
    first = _rows(first_payload)
    second = _rows(second_payload)
    result: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    first_observed = _observed(first_observed_at)
    second_observed = _observed(second_observed_at)

    for fixture_id in sorted(set(first) & set(second)):
        first_league, first_match = first[fixture_id]
        _, second_match = second[fixture_id]
        first_status = first_match["status"]
        second_status = second_match["status"]
        first_identity = (
            first_match["id"],
            first_match["leagueId"],
            first_match["home"]["id"],
            first_match["away"]["id"],
            first_status["utcTime"],
        )
        second_identity = (
            second_match["id"],
            second_match["leagueId"],
            second_match["home"]["id"],
            second_match["away"]["id"],
            second_status["utcTime"],
        )
        first_score = (first_match["home"]["score"], first_match["away"]["score"])
        second_score = (
            second_match["home"]["score"],
            second_match["away"]["score"],
        )
        kickoff = _kickoff(first_status["utcTime"])
        if not (
            first_identity == second_identity
            and first_score == second_score
            and all(type(score) is int and score >= 0 for score in first_score)
            and first_status.get("finished") is True
            and second_status.get("finished") is True
            and first_status.get("started") is True
            and second_status.get("started") is True
            and first_status.get("cancelled") is False
            and second_status.get("cancelled") is False
            and first_observed > kickoff
            and second_observed > kickoff
        ):
            continue
        result.append((first_league, first_match, second_match))
    return result


def test_exact_canonical_evidence_receipt() -> None:
    value = build_fotmob_data_matches_post_finish_capture_pair_evidence()
    exact = canonical_fotmob_data_matches_post_finish_capture_pair_evidence_bytes(value)

    assert EVIDENCE_STATE == (
        "ACQUIRED_DISTINCT_CAPTURE_PAIR_BLOCKED_BY_PR39_TERMINAL_SCHEMA_DRIFT"
    )
    assert len(exact) == EVIDENCE_SIZE == 3921
    assert _sha256(exact) == EVIDENCE_SHA256
    assert EVIDENCE_SHA256 == (
        "a181e40c1264eecf6c9da897d826131c48177168e5592a64caa211ce64dacf02"
    )
    assert set(value.safety.values()) == {False}


def test_exact_pr38_capture_lineage_and_request_identity() -> None:
    value = build_fotmob_data_matches_post_finish_capture_pair_evidence()
    first_raw, first_manifest, _ = _load_capture(FIRST_DIR)
    second_raw, second_manifest, _ = _load_capture(SECOND_DIR)

    assert len(first_raw) == value.first_raw_size == 114920
    assert _sha256(first_raw) == value.first_raw_sha256
    assert len(second_raw) == value.second_raw_size == 114964
    assert _sha256(second_raw) == value.second_raw_sha256

    assert sha256_data_matches_capture_manifest(first_manifest) == value.first_manifest_sha256
    assert sha256_data_matches_capture_manifest(second_manifest) == value.second_manifest_sha256
    assert first_manifest.network_acquisition_performed is True
    assert second_manifest.network_acquisition_performed is True
    assert first_manifest.x_mas_included is False
    assert second_manifest.x_mas_included is False
    assert (first_manifest.request_date, first_manifest.timezone, first_manifest.ccode3) == (
        "20260814",
        "UTC",
        "NGA",
    )
    assert (second_manifest.request_date, second_manifest.timezone, second_manifest.ccode3) == (
        "20260814",
        "UTC",
        "NGA",
    )


def test_capture_pair_is_distinct_and_more_than_300_seconds_apart() -> None:
    value = build_fotmob_data_matches_post_finish_capture_pair_evidence()
    first_raw, first_manifest, _ = _load_capture(FIRST_DIR)
    second_raw, second_manifest, _ = _load_capture(SECOND_DIR)

    separation = (
        second_manifest.observed_at - first_manifest.observed_at
    ).total_seconds()
    assert separation == value.observation_separation_seconds == 310.605739
    assert separation >= 300
    assert _sha256(first_raw) != _sha256(second_raw)
    assert value.raw_lineage_distinct is True
    assert value.manifest_lineage_distinct is True
    assert value.first_manifest_sha256 != value.second_manifest_sha256


def test_current_terminal_snapshots_fail_frozen_pr39_schema_revalidation() -> None:
    value = build_fotmob_data_matches_post_finish_capture_pair_evidence()
    for directory in (FIRST_DIR, SECOND_DIR):
        raw, manifest, _ = _load_capture(directory)
        with pytest.raises(FotMobDataMatchesSchemaError):
            assess_fotmob_data_matches_schema(raw, manifest)

    assert value.pr39_schema_revalidation_passed is False
    assert value.primary_blocker == (
        "PR39_STRICT_SCHEMA_REVALIDATION_FAILED_TERMINAL_SNAPSHOT_EXTRA_KEYS"
    )


def test_exact_terminal_schema_drift_is_frozen_from_both_raw_captures() -> None:
    value = build_fotmob_data_matches_post_finish_capture_pair_evidence()
    expected_team = {"penScore", "redCards"}
    expected_status = {
        "awarded",
        "liveTime",
        "numberOfAwayRedCards",
        "numberOfHomeRedCards",
        "ongoing",
        "scoreStr",
    }
    expected_halfs = {"secondHalfStarted"}

    for directory in (FIRST_DIR, SECOND_DIR):
        _, _, payload = _load_capture(directory)
        team_keys, status_keys, halfs_keys = _key_unions(payload)
        assert team_keys - TEAM_KEYS == expected_team
        assert status_keys - STATUS_ALLOWED_KEYS == expected_status
        assert halfs_keys - HALFS_KEYS == expected_halfs

    assert set(value.pr39_extra_team_keys) == expected_team
    assert set(value.pr39_extra_status_keys) == expected_status
    assert set(value.pr39_extra_halfs_keys) == expected_halfs


def test_pair_contains_29_stable_finished_identity_score_candidates() -> None:
    value = build_fotmob_data_matches_post_finish_capture_pair_evidence()
    _, first_manifest, first_payload = _load_capture(FIRST_DIR)
    _, second_manifest, second_payload = _load_capture(SECOND_DIR)

    first_matches = sum(len(league["matches"]) for league in first_payload["leagues"])
    second_matches = sum(len(league["matches"]) for league in second_payload["leagues"])
    assert (first_matches, second_matches) == (value.first_match_count, value.second_match_count)
    assert (first_matches, second_matches) == (183, 183)

    pairs = _stable_finished_pairs(
        first_payload,
        second_payload,
        first_manifest.to_dict()["observed_at"],
        second_manifest.to_dict()["observed_at"],
    )
    assert len(pairs) == value.stable_finished_identity_score_pair_count == 29
    reasons = [first_match["status"].get("reason", {}).get("short") for _, first_match, _ in pairs]
    assert reasons.count("FT") == value.ordinary_ft_reason_pair_count == 28
    assert reasons.count("Pen") == value.penalty_reason_pair_count == 1
    assert all(
        first_match["status"].get("reason") == second_match["status"].get("reason")
        for _, first_match, second_match in pairs
    )


def test_selected_simple_finished_fixture_is_stable_but_reason_blocked() -> None:
    value = build_fotmob_data_matches_post_finish_capture_pair_evidence()
    _, first_manifest, first_payload = _load_capture(FIRST_DIR)
    _, second_manifest, second_payload = _load_capture(SECOND_DIR)
    first_league, first_match = _rows(first_payload)[value.selected_fixture_id]
    second_league, second_match = _rows(second_payload)[value.selected_fixture_id]

    assert value.selected_fixture_id == 5186581
    assert first_match["id"] == second_match["id"] == 5186581
    assert first_match["leagueId"] == second_match["leagueId"] == value.selected_league_id == 920266
    assert first_league["name"] == second_league["name"] == value.selected_league_name == "Super League"
    assert first_match["home"]["id"] == second_match["home"]["id"] == value.selected_home_team_id == 8623
    assert first_match["away"]["id"] == second_match["away"]["id"] == value.selected_away_team_id == 4183
    assert first_match["home"]["score"] == second_match["home"]["score"] == value.selected_home_score == 3
    assert first_match["away"]["score"] == second_match["away"]["score"] == value.selected_away_score == 1
    assert first_match["status"]["utcTime"] == second_match["status"]["utcTime"] == value.selected_kickoff_utc
    assert first_match["status"]["finished"] is second_match["status"]["finished"] is True
    assert first_match["status"]["started"] is second_match["status"]["started"] is True
    assert first_match["status"]["cancelled"] is second_match["status"]["cancelled"] is False
    assert first_match["status"]["reason"] == second_match["status"]["reason"] == {
        "short": "FT",
        "shortKey": "fulltime_short",
        "long": "Full-Time",
        "longKey": "finished",
    }
    assert first_manifest.observed_at > _kickoff(value.selected_kickoff_utc)
    assert second_manifest.observed_at > _kickoff(value.selected_kickoff_utc)
    assert value.secondary_blocker == "PR83_STATUS_REASON_REQUIRES_EXPLICIT_REVIEW"

    projection = {
        "league": {key: item for key, item in first_league.items() if key != "matches"},
        "match": first_match,
    }
    projection_bytes = (
        json.dumps(
            projection,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    assert len(projection_bytes) == value.selected_fixture_projection_size == 788
    assert _sha256(projection_bytes) == value.selected_fixture_projection_sha256


def test_acquired_pair_does_not_promote_source_or_pr83_semantics() -> None:
    value = build_fotmob_data_matches_post_finish_capture_pair_evidence()
    capability = SOURCE_CAPABILITY_REGISTRY["fotmob_data_matches_reviewed_catalog"]

    assert value.pr83_eligibility is False
    assert value.final_result_semantics_qualified is False
    assert capability.full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert capability.historical_coverage is CapabilityAvailability.UNKNOWN
    assert value.source_capability_full_time_score_must_remain == "NOT_CAPTURED"
    assert value.historical_coverage_must_remain == "UNKNOWN"
    assert NEXT_REQUIRED_BOUNDARY == (
        "PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_TERMINAL_STATE_SCHEMA_EXTENSION"
    )
    assert value.next_required_boundary == NEXT_REQUIRED_BOUNDARY


def test_mutations_and_positive_authority_fail_closed() -> None:
    value = build_fotmob_data_matches_post_finish_capture_pair_evidence()

    with pytest.raises(FotMobDataMatchesPostFinishCapturePairEvidenceError):
        dataclasses.replace(value, pr83_eligibility=True)
    with pytest.raises(FotMobDataMatchesPostFinishCapturePairEvidenceError):
        dataclasses.replace(value, final_result_semantics_qualified=True)
    with pytest.raises(FotMobDataMatchesPostFinishCapturePairEvidenceError):
        dataclasses.replace(value, pr39_schema_revalidation_passed=True)
    with pytest.raises(FotMobDataMatchesPostFinishCapturePairEvidenceError):
        dataclasses.replace(value, stable_finished_identity_score_pair_count=30)

    safety = dict(value.safety)
    safety["source_capability_update_authorized"] = True
    with pytest.raises(FotMobDataMatchesPostFinishCapturePairEvidenceError):
        dataclasses.replace(value, safety=safety)


def test_revalidator_rejects_changed_receipt() -> None:
    value = build_fotmob_data_matches_post_finish_capture_pair_evidence()
    assert revalidate_fotmob_data_matches_post_finish_capture_pair_evidence(value) == value
    with pytest.raises(FotMobDataMatchesPostFinishCapturePairEvidenceError):
        dataclasses.replace(value, primary_blocker="changed")


def test_receipt_module_cannot_acquire_network_or_run_downstream() -> None:
    source = Path(evidence_module.__file__).read_text(encoding="utf-8")
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
