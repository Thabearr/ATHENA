"""Reviewed live-capture identity compatibility for the FotMob fresh holdout.

The frozen PR39 fixture-candidate schema predates reviewed terminal-state fields.
This adapter grants no football semantics. It admits only two additional opaque
``status.halfs`` string keys observed in preserved post-PR207 live captures,
projects those two keys away, re-runs the already-reviewed PR89 -> PR87 -> PR39
structural chain, and then rebuilds the existing PR40 fixture-candidate
population from a PR39-compatible projection.

Returned fixture identity remains bound to the exact original network capture
bytes and original manifest. Compatibility projections are validation-only and
are never promoted to source evidence.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import domain.fotmob_data_matches_capture as capture_contract
import domain.fotmob_data_matches_eliminated_team_id_value_domain_extension as pr89
import domain.fotmob_data_matches_schema as pr39_schema
import domain.fotmob_data_matches_terminal_state_schema_extension as pr87
import domain.fotmob_fixture_candidates as fixture_candidates
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh


SCHEMA_VERSION = 1
ADAPTER_ID = "FOTMOB_FRESH_HOLDOUT_REVIEWED_LIVE_CAPTURE_IDENTITY_ADAPTER_V1"
ADAPTER_STATE = "REVIEWED_STRUCTURAL_COMPATIBILITY_ONLY_NO_FOOTBALL_SEMANTIC_PROMOTION"

FRESH_HOLDOUT_CORE_BLOB_SHA = "5dabab12d5205d384fd3904cda0e68661ef90791"
PR39_SCHEMA_BLOB_SHA = "4dfff0eb05335895c3ee0fcaa7b8da1299ea692f"
PR87_IMPLEMENTATION_BLOB_SHA = "fc120476739293abbb5db4374a0b4d7cfe8a1fc3"
PR89_IMPLEMENTATION_BLOB_SHA = "f33dd31aedcd92b5691a3503914ed184d601b493"
FIXTURE_CANDIDATE_BLOB_SHA = "a3434951e87cfbd90dd2c43cccd413e7edfb08e0"
CAPTURE_CONTRACT_BLOB_SHA = "ca2149395de868104666620173b55a880b10c729"

EXTRA_HALFS_KEYS = ("firstExtraHalfStarted", "secondExtraHalfStarted")
EXTRA_HALFS_RULE = (
    "OPTIONAL_EXACT_STRING_NULL_FORBIDDEN_OPAQUE_NO_EXTRA_TIME_SEMANTICS"
)

SOURCE_WORKFLOW_RUN_ID = 32583079461
SOURCE_ACTIONS_ARTIFACT_ID = 9478318255
SOURCE_ACTIONS_ARTIFACT_NAME = "failure-20260822T153700Z-run-32583079461.tar.gz"
SOURCE_RELEASE_TAG = "athena-fresh-holdout-evidence-2026-W34"
SOURCE_RELEASE_ASSET_NAME = SOURCE_ACTIONS_ARTIFACT_NAME
SOURCE_CAPTURE_LINEAGES = (
    {
        "request_date": "20260821",
        "manifest_sha256": "1cacc67a60889c498dbc0877b2604382c619197c0e68a2e3253bf2739b3bae9d",
        "raw_sha256": "a0273b704e786fdce00abf27487a710a06fbdbeef3b4902a83d9ccf00f9e0176",
        "firstExtraHalfStarted_occurrences": 1,
        "secondExtraHalfStarted_occurrences": 1,
    },
    {
        "request_date": "20260822",
        "manifest_sha256": "aaacdc3ec7c7d4dce5b4a9bd1b8bcd3e222f2eb4a696c629bb4e5896457e58ff",
        "raw_sha256": "595e63c57f7b7a3876f9d7f3c6498b8a0fab84c13c7adac275ba30bf3e5a2730",
        "firstExtraHalfStarted_occurrences": 3,
        "secondExtraHalfStarted_occurrences": 3,
    },
)

SAFETY_KEYS = (
    "football_semantics_promoted",
    "final_result_semantics_promoted",
    "extra_time_semantics_promoted",
    "source_capability_changed",
    "model_feature_authorized",
    "probability_authorized",
    "pricing_authorized",
    "selection_authorized",
    "bet_authorized",
)


class FreshHoldoutCaptureQualificationAdapterError(RuntimeError):
    """Raised when structural compatibility cannot be proven exactly."""


def _error(message: str) -> FreshHoldoutCaptureQualificationAdapterError:
    return FreshHoldoutCaptureQualificationAdapterError(message)


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def verify_reviewed_dependencies() -> None:
    """Fail closed if any reviewed implementation dependency moved."""
    pins = (
        (Path(fresh.__file__), FRESH_HOLDOUT_CORE_BLOB_SHA, "fresh-holdout core"),
        (Path(pr39_schema.__file__), PR39_SCHEMA_BLOB_SHA, "PR39 schema"),
        (Path(pr87.__file__), PR87_IMPLEMENTATION_BLOB_SHA, "PR87 terminal extension"),
        (Path(pr89.__file__), PR89_IMPLEMENTATION_BLOB_SHA, "PR89 eliminatedTeamId extension"),
        (Path(fixture_candidates.__file__), FIXTURE_CANDIDATE_BLOB_SHA, "PR40 fixture candidates"),
        (Path(capture_contract.__file__), CAPTURE_CONTRACT_BLOB_SHA, "PR38 capture contract"),
    )
    try:
        for path, expected, label in pins:
            if _git_blob_sha(path) != expected:
                raise _error(f"{label} implementation blob changed")
    except OSError as exc:
        raise _error("could not verify reviewed adapter dependencies") from exc


def _strict_json(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not raw:
        raise _error("raw capture must be non-empty exact bytes")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise _error(f"raw capture contains duplicate JSON key {key!r}")
            out[key] = value
        return out

    def constant(token: str) -> None:
        raise _error(f"raw capture contains forbidden JSON constant {token!r}")

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except FreshHoldoutCaptureQualificationAdapterError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _error("raw capture is not strict UTF-8 JSON") from exc
    if type(value) is not dict:
        raise _error("raw capture top level must be an object")
    return value


def _canonical(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("compatibility projection serialization failed") from exc


def _projected_manifest(
    source_manifest: capture_contract.FotMobDataMatchesCaptureManifest,
    projected_raw: bytes,
) -> capture_contract.FotMobDataMatchesCaptureManifest:
    content_length = (
        None if source_manifest.content_length is None else len(projected_raw)
    )
    try:
        return dataclasses.replace(
            source_manifest,
            content_length=content_length,
            network_acquisition_performed=False,
            raw_sha256=hashlib.sha256(projected_raw).hexdigest(),
            raw_size=len(projected_raw),
        )
    except Exception as exc:
        raise _error("compatibility projection manifest failed validation") from exc


def _remove_reviewed_extra_halfs(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove only the two reviewed opaque keys after exact-type validation."""
    projected = copy.deepcopy(payload)
    leagues = projected.get("leagues")
    if type(leagues) is not list:
        return projected
    for league_index, league in enumerate(leagues):
        if type(league) is not dict:
            continue
        matches = league.get("matches")
        if type(matches) is not list:
            continue
        for match_index, match in enumerate(matches):
            if type(match) is not dict:
                continue
            status = match.get("status")
            if type(status) is not dict:
                continue
            halfs = status.get("halfs")
            if type(halfs) is not dict:
                continue
            for key in EXTRA_HALFS_KEYS:
                if key not in halfs:
                    continue
                value = halfs[key]
                if type(value) is not str:
                    raise _error(
                        f"leagues[{league_index}].matches[{match_index}]."
                        f"status.halfs.{key} must be an exact string"
                    )
                del halfs[key]
    return projected


def _project_to_pr39(payload: dict[str, Any]) -> dict[str, Any]:
    """Project only fields already qualified by PR89/PR87 down to frozen PR39."""
    projected = copy.deepcopy(payload)
    leagues = projected.get("leagues")
    if type(leagues) is not list:
        raise _error("qualified projection lost leagues list")
    for league in leagues:
        if type(league) is not dict:
            raise _error("qualified projection league is not an object")
        matches = league.get("matches")
        if type(matches) is not list:
            raise _error("qualified projection lost match list")
        for match in matches:
            if type(match) is not dict:
                raise _error("qualified projection match is not an object")
            match["eliminatedTeamId"] = None
            for side in ("home", "away"):
                team = match.get(side)
                if type(team) is not dict:
                    raise _error("qualified projection team is not an object")
                for key in tuple(team):
                    if key not in pr39_schema.TEAM_KEYS:
                        del team[key]
            status = match.get("status")
            if type(status) is not dict:
                raise _error("qualified projection status is not an object")
            for key in tuple(status):
                if key not in pr39_schema.STATUS_ALLOWED_KEYS:
                    del status[key]
            halfs = status.get("halfs")
            if type(halfs) is not dict:
                raise _error("qualified projection halfs is not an object")
            for key in tuple(halfs):
                if key not in pr39_schema.HALFS_KEYS:
                    del halfs[key]
    return projected


def qualify_capture_fixtures(
    raw_json: bytes,
    manifest: capture_contract.FotMobDataMatchesCaptureManifest,
) -> tuple[fresh.QualifiedCaptureFixture, ...]:
    """Qualify exact fixture identity while preserving original capture lineage."""
    verify_reviewed_dependencies()
    if not isinstance(manifest, capture_contract.FotMobDataMatchesCaptureManifest):
        raise _error("manifest must be the reviewed FotMob capture manifest type")
    if manifest.network_acquisition_performed is not True:
        raise _error("fresh holdout adapter requires an actual reviewed network capture")
    if type(raw_json) is not bytes:
        raise _error("raw capture must be exact bytes")
    if manifest.raw_size != len(raw_json):
        raise _error("raw capture size does not match original manifest")
    if hashlib.sha256(raw_json).hexdigest() != manifest.raw_sha256:
        raise _error("raw capture SHA-256 does not match original manifest")

    payload = _strict_json(raw_json)

    # The only newly admitted structure is the pair of opaque exact-string
    # status.halfs keys. Everything else must survive the already-reviewed
    # PR89 -> PR87 -> PR39 chain before any projection can be used.
    pr89_payload = _remove_reviewed_extra_halfs(payload)
    pr89_raw = _canonical(pr89_payload)
    pr89_manifest = _projected_manifest(manifest, pr89_raw)
    try:
        pr89_assessment = pr89.assess_fotmob_data_matches_eliminated_team_id_value_domain(
            pr89_raw,
            pr89_manifest,
        )
    except Exception as exc:
        raise _error("reviewed PR89->PR87->PR39 structural chain failed") from exc
    if (
        pr89_assessment.status
        is not pr89.EliminatedTeamIdValueDomainStatus.QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN
    ):
        raise _error("reviewed PR89 chain did not return its exact qualified status")
    if (
        pr89_assessment.status_reason_semantics_qualified
        or pr89_assessment.final_result_semantics_qualified
    ):
        raise _error("reviewed structural chain unexpectedly promoted semantics")

    candidate_payload = _project_to_pr39(pr89_payload)
    candidate_raw = _canonical(candidate_payload)
    candidate_manifest = _projected_manifest(manifest, candidate_raw)
    try:
        bundle = fixture_candidates.build_fotmob_fixture_candidate_bundle(
            ((candidate_raw, candidate_manifest),)
        )
    except Exception as exc:
        raise _error("reviewed PR39 fixture-candidate projection failed") from exc

    original_manifest_sha = capture_contract.sha256_data_matches_capture_manifest(
        manifest
    )
    qualified = fresh._qualify_provider_identity_payload(
        raw_json,
        capture_observed_at=manifest.observed_at,
        capture_manifest_sha256=original_manifest_sha,
        capture_raw_sha256=manifest.raw_sha256,
    )

    candidates = {item.source_match_id: item for item in bundle.candidates}
    if len(candidates) != len(bundle.candidates) or len(qualified) != len(bundle.candidates):
        raise _error("reviewed candidate and exact identity populations disagree")

    projected_manifest_sha = capture_contract.sha256_data_matches_capture_manifest(
        candidate_manifest
    )
    for item in qualified:
        candidate = candidates.get(item.fixture_id)
        if candidate is None:
            raise _error("qualified fixture absent from reviewed candidate population")
        expected_identity = (
            candidate.source_competition_primary_id,
            candidate.source_league_id,
            candidate.home_source_team_id,
            candidate.away_source_team_id,
            candidate.kickoff_utc,
            candidate.source_observed_at,
        )
        actual_identity = (
            item.provider_primary_id,
            item.wrapper_id,
            item.home_team_id,
            item.away_team_id,
            item.kickoff_utc,
            item.capture_observed_at,
        )
        if actual_identity != expected_identity:
            raise _error(
                "exact provider identity disagrees with reviewed candidate projection"
            )
        if (
            candidate.source_request_date != manifest.request_date
            or candidate.source_raw_sha256 != candidate_manifest.raw_sha256
            or candidate.source_capture_manifest_sha256 != projected_manifest_sha
        ):
            raise _error("candidate projection lineage is internally inconsistent")

        # The returned identity is deliberately bound to the original network
        # evidence, never to either compatibility projection.
        if (
            item.capture_raw_sha256 != manifest.raw_sha256
            or item.capture_manifest_sha256 != original_manifest_sha
        ):
            raise _error("returned fixture escaped original network capture lineage")
    return qualified


def adapter_receipt() -> dict[str, Any]:
    verify_reviewed_dependencies()
    return {
        "schema_version": SCHEMA_VERSION,
        "adapter_id": ADAPTER_ID,
        "adapter_state": ADAPTER_STATE,
        "reviewed_extra_halfs_keys": list(EXTRA_HALFS_KEYS),
        "reviewed_extra_halfs_rule": EXTRA_HALFS_RULE,
        "source_workflow_run_id": SOURCE_WORKFLOW_RUN_ID,
        "source_actions_artifact_id": SOURCE_ACTIONS_ARTIFACT_ID,
        "source_actions_artifact_name": SOURCE_ACTIONS_ARTIFACT_NAME,
        "source_release_tag": SOURCE_RELEASE_TAG,
        "source_release_asset_name": SOURCE_RELEASE_ASSET_NAME,
        "source_capture_lineages": [dict(item) for item in SOURCE_CAPTURE_LINEAGES],
        "original_network_capture_lineage_preserved_in_returned_fixtures": True,
        "compatibility_projection_is_not_source_evidence": True,
        "network_acquisition_performed": False,
        "safety": {key: False for key in SAFETY_KEYS},
    }


__all__ = [
    "ADAPTER_ID",
    "ADAPTER_STATE",
    "EXTRA_HALFS_KEYS",
    "EXTRA_HALFS_RULE",
    "FreshHoldoutCaptureQualificationAdapterError",
    "SOURCE_ACTIONS_ARTIFACT_ID",
    "SOURCE_ACTIONS_ARTIFACT_NAME",
    "SOURCE_CAPTURE_LINEAGES",
    "SOURCE_RELEASE_ASSET_NAME",
    "SOURCE_RELEASE_TAG",
    "SOURCE_WORKFLOW_RUN_ID",
    "adapter_receipt",
    "qualify_capture_fixtures",
    "verify_reviewed_dependencies",
]
