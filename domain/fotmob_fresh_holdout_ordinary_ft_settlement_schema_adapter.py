"""Reviewed settlement-schema compatibility for the FotMob fresh holdout.

The frozen ordinary-FT score adapter re-runs the frozen PR89 structural chain
against each settlement capture. Live captures can contain the two opaque
``status.halfs`` keys reviewed by the fresh-holdout capture adapter, and a
provider request bucket can contain separately reviewed previous-UTC-day
spillover fixtures that are not fresh candidates. This module projects only
those reviewed compatibility shapes away before PR89 settlement revalidation,
while leaving the frozen ordinary-FT adapter to parse scores/reasons from the
original network bytes.

The compatibility projection is validation-only. It does not replace source
evidence, infer request-bucket, timezone, extra-time, or football semantics,
alter score/reason semantics, or authorize model, pricing, selection,
production, or betting use.
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
import domain.fotmob_data_matches_ordinary_ft_finished_score_adapter as score_adapter
import domain.fotmob_fresh_holdout_capture_qualification_adapter as live_capture_adapter


SCHEMA_VERSION = 1
ADAPTER_ID = "FOTMOB_FRESH_HOLDOUT_ORDINARY_FT_SETTLEMENT_SCHEMA_ADAPTER_V1"
ADAPTER_STATE = "REVIEWED_STRUCTURAL_COMPATIBILITY_ONLY_FROZEN_SCORE_SEMANTICS_UNCHANGED"

LIVE_CAPTURE_ADAPTER_BLOB_SHA = "50e717cc52eb54c84f1804ad07932c0cb01251b5"
ORDINARY_FT_ADAPTER_BLOB_SHA = "868563206e09010fce74b4ba7954028930baad54"
PR89_IMPLEMENTATION_BLOB_SHA = "f33dd31aedcd92b5691a3503914ed184d601b493"
CAPTURE_CONTRACT_BLOB_SHA = "ca2149395de868104666620173b55a880b10c729"

EXTRA_HALFS_KEYS = ("firstExtraHalfStarted", "secondExtraHalfStarted")
EXTRA_HALFS_RULE = "OPTIONAL_EXACT_STRING_NULL_FORBIDDEN_OPAQUE_NO_EXTRA_TIME_SEMANTICS"

SOURCE_WORKFLOW_RUN_ID = 32592483626
SOURCE_ACTIONS_ARTIFACT_ID = 9480687035
SOURCE_ACTIONS_ARTIFACT_NAME = "failure-20260822T183700Z-run-32592483626.tar.gz"
SOURCE_RELEASE_TAG = "athena-fresh-holdout-evidence-2026-W34"
SOURCE_FIXTURE_ID = 5749644
SOURCE_CAPTURE_LINEAGES = (
    {
        "request_date": "20260822",
        "observed_at": "2026-08-22T18:45:30.330380Z",
        "manifest_sha256": "f3502002916426fee38eb542c9974c8f424dce06c5909bab64d7294118d2f3ad",
        "raw_sha256": "cb4d6e512da2f9ff35ba1c2b1331008d744f88df265a0c95cda0be9019bfd054",
    },
    {
        "request_date": "20260822",
        "observed_at": "2026-08-22T19:01:58.639959Z",
        "manifest_sha256": "4bf0da5e5519d2c8101a521509b05bab447c0384bb5ebfda0e93c806f8efbcb7",
        "raw_sha256": "45511d2197a59c057ec19a2993ee2ba57534ec3ddaa33c8747fb6a4cc312833e",
    },
)

SAFETY_KEYS = (
    "football_semantics_promoted",
    "final_result_semantics_promoted",
    "extra_time_semantics_promoted",
    "request_bucket_semantics_promoted",
    "timezone_semantics_promoted",
    "ordinary_ft_score_semantics_changed",
    "source_capability_changed",
    "model_feature_authorized",
    "probability_authorized",
    "pricing_authorized",
    "selection_authorized",
    "bet_authorized",
)


class FreshHoldoutOrdinaryFtSettlementSchemaAdapterError(RuntimeError):
    """Raised when settlement structural compatibility cannot be proven exactly."""


def _error(message: str) -> FreshHoldoutOrdinaryFtSettlementSchemaAdapterError:
    return FreshHoldoutOrdinaryFtSettlementSchemaAdapterError(message)


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def verify_reviewed_dependencies() -> None:
    pins = (
        (Path(live_capture_adapter.__file__), LIVE_CAPTURE_ADAPTER_BLOB_SHA, "reviewed live-capture adapter"),
        (Path(score_adapter.__file__), ORDINARY_FT_ADAPTER_BLOB_SHA, "frozen ordinary-FT adapter"),
        (Path(pr89.__file__), PR89_IMPLEMENTATION_BLOB_SHA, "PR89 structural implementation"),
        (Path(capture_contract.__file__), CAPTURE_CONTRACT_BLOB_SHA, "capture contract"),
    )
    try:
        for path, expected, label in pins:
            if _git_blob_sha(path) != expected:
                raise _error(f"{label} implementation blob changed")
    except OSError as exc:
        raise _error("could not verify reviewed settlement adapter dependencies") from exc
    if tuple(live_capture_adapter.EXTRA_HALFS_KEYS) != EXTRA_HALFS_KEYS:
        raise _error("reviewed extra-halfs key set changed")
    if live_capture_adapter.EXTRA_HALFS_RULE != EXTRA_HALFS_RULE:
        raise _error("reviewed extra-halfs rule changed")
    if not isinstance(live_capture_adapter.REQUEST_BUCKET_SPILLOVER_RULE, str):
        raise _error("reviewed request-bucket spillover rule changed")


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
    except FreshHoldoutOrdinaryFtSettlementSchemaAdapterError:
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
        raise _error("settlement compatibility projection serialization failed") from exc


def _projected_manifest(
    source_manifest: capture_contract.FotMobDataMatchesCaptureManifest,
    projected_raw: bytes,
) -> capture_contract.FotMobDataMatchesCaptureManifest:
    content_length = None if source_manifest.content_length is None else len(projected_raw)
    try:
        return dataclasses.replace(
            source_manifest,
            content_length=content_length,
            network_acquisition_performed=False,
            raw_sha256=hashlib.sha256(projected_raw).hexdigest(),
            raw_size=len(projected_raw),
        )
    except Exception as exc:
        raise _error("settlement compatibility projection manifest failed validation") from exc


def _remove_reviewed_extra_halfs(payload: dict[str, Any]) -> dict[str, Any]:
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
                if type(halfs[key]) is not str:
                    raise _error(
                        f"leagues[{league_index}].matches[{match_index}]."
                        f"status.halfs.{key} must be an exact string"
                    )
                del halfs[key]
    return projected


def assess_eliminated_team_id_value_domain_for_settlement(
    raw_json: bytes,
    manifest: capture_contract.FotMobDataMatchesCaptureManifest,
):
    """Run frozen PR89 on the reviewed requested-date settlement projection."""
    verify_reviewed_dependencies()
    if not isinstance(manifest, capture_contract.FotMobDataMatchesCaptureManifest):
        raise _error("manifest must be the reviewed FotMob capture manifest type")
    if manifest.network_acquisition_performed is not True:
        raise _error("settlement compatibility requires an actual reviewed network capture")
    if type(raw_json) is not bytes:
        raise _error("raw capture must be exact bytes")
    if manifest.raw_size != len(raw_json):
        raise _error("raw capture size does not match original manifest")
    if hashlib.sha256(raw_json).hexdigest() != manifest.raw_sha256:
        raise _error("raw capture SHA-256 does not match original manifest")

    try:
        live_capture_adapter.qualify_capture_fixtures(raw_json, manifest)
    except Exception as exc:
        raise _error("reviewed fresh-capture compatibility qualification failed") from exc

    payload = _strict_json(raw_json)
    try:
        requested_payload, _spillover_payload, _spillover_ids = (
            live_capture_adapter.partition_reviewed_request_bucket_spillover(
                payload,
                manifest.request_date,
            )
        )
    except Exception as exc:
        raise _error("reviewed request-bucket settlement partition failed") from exc
    projected_payload = _remove_reviewed_extra_halfs(requested_payload)
    projected_raw = _canonical(projected_payload)
    projected_manifest = _projected_manifest(manifest, projected_raw)
    try:
        assessment = pr89.assess_fotmob_data_matches_eliminated_team_id_value_domain(
            projected_raw,
            projected_manifest,
        )
    except Exception as exc:
        raise _error("reviewed PR89 settlement structural projection failed") from exc
    if (
        assessment.status
        is not pr89.EliminatedTeamIdValueDomainStatus.QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN
    ):
        raise _error("reviewed PR89 settlement projection did not qualify structurally")
    if assessment.status_reason_semantics_qualified or assessment.final_result_semantics_qualified:
        raise _error("settlement structural projection unexpectedly promoted semantics")
    return assessment


class ReviewedPr89SettlementCompatibilityProxy:
    """Delegate frozen PR89 except for the one reviewed structural assessment hook."""

    __slots__ = ()

    def __getattr__(self, name: str):
        return getattr(pr89, name)

    def assess_fotmob_data_matches_eliminated_team_id_value_domain(
        self,
        raw_json: bytes,
        manifest: capture_contract.FotMobDataMatchesCaptureManifest,
    ):
        return assess_eliminated_team_id_value_domain_for_settlement(raw_json, manifest)


def build_pr89_settlement_compatibility_proxy() -> ReviewedPr89SettlementCompatibilityProxy:
    verify_reviewed_dependencies()
    return ReviewedPr89SettlementCompatibilityProxy()


def adapter_receipt() -> dict[str, Any]:
    verify_reviewed_dependencies()
    return {
        "schema_version": SCHEMA_VERSION,
        "adapter_id": ADAPTER_ID,
        "adapter_state": ADAPTER_STATE,
        "reviewed_extra_halfs_keys": list(EXTRA_HALFS_KEYS),
        "reviewed_extra_halfs_rule": EXTRA_HALFS_RULE,
        "reviewed_request_bucket_spillover_rule": live_capture_adapter.REQUEST_BUCKET_SPILLOVER_RULE,
        "source_workflow_run_id": SOURCE_WORKFLOW_RUN_ID,
        "source_actions_artifact_id": SOURCE_ACTIONS_ARTIFACT_ID,
        "source_actions_artifact_name": SOURCE_ACTIONS_ARTIFACT_NAME,
        "source_release_tag": SOURCE_RELEASE_TAG,
        "source_fixture_id": SOURCE_FIXTURE_ID,
        "source_capture_lineages": [dict(item) for item in SOURCE_CAPTURE_LINEAGES],
        "compatibility_projection_is_validation_only": True,
        "ordinary_ft_adapter_consumes_original_network_bytes": True,
        "request_bucket_spillover_excluded_only_from_structural_projection": True,
        "network_acquisition_performed": False,
        "safety": {key: False for key in SAFETY_KEYS},
    }


__all__ = [
    "ADAPTER_ID",
    "ADAPTER_STATE",
    "EXTRA_HALFS_KEYS",
    "EXTRA_HALFS_RULE",
    "FreshHoldoutOrdinaryFtSettlementSchemaAdapterError",
    "ReviewedPr89SettlementCompatibilityProxy",
    "adapter_receipt",
    "assess_eliminated_team_id_value_domain_for_settlement",
    "build_pr89_settlement_compatibility_proxy",
    "verify_reviewed_dependencies",
]
