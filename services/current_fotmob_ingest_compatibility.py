"""Offline compatibility adapter from a canonical ingest artifact to PR243.

The adapter accepts only one complete FotMob/UTC/NGA date capture.  It verifies
the canonical artifact with the existing offline replay contract, then feeds the
verified capture in place into the existing PR243 current-reviewed bootstrap
chain.  This module never acquires provider data or copies source bytes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path, PurePosixPath
import re
from typing import Any

from domain.current_fotmob_fixture_review_policy import (
    DEFAULT_MAX_SOURCE_AGE_SECONDS,
    DEFAULT_MINIMUM_LEAD_SECONDS,
    canonical_current_fotmob_fixture_review_policy_result_bytes,
)
from domain.fotmob_data_matches_capture import (
    FotMobDataMatchesCaptureError,
    verify_data_matches_capture_directory,
)
from domain.ingest_contracts import (
    AthenaCanonicalStoreUpdate,
    AthenaIngestContractError,
    AthenaIngestReceipt,
    AthenaIngestRequest,
    canonical_json_bytes,
    sha256_bytes,
    strict_json_loads,
)
from domain.fotmob_fixture_catalog_handoff import sha256_fotmob_fixture_catalog_handoff
from scripts.issue_current_fotmob_reviewed_source import (
    CurrentFotMobReviewedSourceError,
    _build_verified_current_fotmob_bootstrap_from_capture,
)
from scripts.replay_athena_ingest_artifact import (
    AthenaIngestReplayError,
    replay_ingest_artifact,
)
from services.athena_ingest_service import (
    RECEIPT_NAME,
    REPLAY_NAME,
    REQUEST_NAME,
    UPDATE_NAME,
)


COMPATIBILITY_POLICY_ID = (
    "ATHENA_P4_4D_CURRENT_FOTMOB_INGEST_COMPATIBILITY_V1"
)
COMPATIBILITY_SCOPE = (
    "SINGLE_DATE_FOTMOB_UTC_NGA_CANONICAL_INGEST_TO_PR243_BOOTSTRAP"
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}", re.ASCII)
_SHA1_RE = re.compile(r"[0-9a-f]{40}", re.ASCII)
_TOP_LEVEL_ARTIFACT_NAMES = frozenset({
    REQUEST_NAME,
    UPDATE_NAME,
    RECEIPT_NAME,
    REPLAY_NAME,
    "sources",
})
_PR243_AUTHORITY = {
    "transparent_fotmob_network_capture": True,
    "pr243_fixture_identity_policy_decisions": True,
    "reviewed_fixture_bootstrap": True,
    "fixture_intelligence_fact": False,
    "fixture_intelligence_snapshot": False,
    "model_feature": False,
    "probability": False,
    "pricing": False,
    "selection": False,
    "sportybet_execution": False,
    "bet": False,
}
_FALSE_RECEIPT_FIELDS = frozenset({
    "provider_acquisition_performed_by_adapter",
    "source_bytes_copied_by_adapter",
    "source_bytes_rewritten_by_adapter",
    "full_legacy_request_contract_equivalence_claimed",
    "noncanonical_timezone_or_ccode3_supported",
    "legacy_workflow_retirement_authorized",
    "legacy_workflow_modified",
    "canonical_ingest_workflow_modified",
    "canonical_ingest_request_schema_modified",
    "fixture_intelligence_fact_authority",
    "fixture_intelligence_snapshot_authority",
    "model_feature_authority",
    "probability_authority",
    "pricing_authority",
    "routing_authority",
    "portfolio_authority",
    "share_code_authority",
    "login",
    "cookies",
    "wallet",
    "staking",
    "wager",
    "backfill_authority",
    "wager_placed",
})
_RECEIPT_FIELDS = frozenset({
    "schema_version",
    "policy_id",
    "compatibility_scope",
    "ingest_request_sha256",
    "canonical_store_update_sha256",
    "canonical_ingest_receipt_sha256",
    "original_ingest_exact_commit_sha",
    "request_date",
    "provider",
    "timezone",
    "ccode3",
    "issued_at",
    "source_count",
    "source_capture_manifest_sha256",
    "source_raw_sha256",
    "policy_result_sha256",
    "handoff_sha256",
    "bootstrap_sha256",
    "verified_bootstrap_receipt_sha256",
    "fixture_identifiers",
    "approved_count",
    "minimum_lead_seconds",
    "max_source_age_seconds",
    "pr243_authority",
    "provider_request_count_by_adapter",
    *_FALSE_RECEIPT_FIELDS,
    "canonical_sha256",
})


class CurrentFotMobIngestCompatibilityError(ValueError):
    """Canonical ingest evidence cannot safely enter the PR243 replay chain."""


def _sha(value: Any, label: str, *, pattern: re.Pattern[str] = _SHA256_RE) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise CurrentFotMobIngestCompatibilityError(f"{label} is not a canonical hash")
    return value


def _no_symlink_components(path: Path, label: str) -> None:
    candidate = path if path.is_absolute() else Path.cwd() / path
    if ".." in candidate.parts:
        raise CurrentFotMobIngestCompatibilityError(f"{label} contains traversal")
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise CurrentFotMobIngestCompatibilityError(
                f"{label} contains a symlink component"
            )


def _artifact_root(value: Path) -> Path:
    try:
        candidate = Path(value)
        _no_symlink_components(candidate, "artifact root")
        if candidate.is_symlink() or not candidate.is_dir():
            raise CurrentFotMobIngestCompatibilityError(
                "artifact root must be an existing non-symlink directory"
            )
        return candidate.resolve(strict=True)
    except CurrentFotMobIngestCompatibilityError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise CurrentFotMobIngestCompatibilityError("artifact root is invalid") from exc


def _relative_parts(relative: Any, label: str) -> tuple[str, ...]:
    if type(relative) is not str or not relative or "\\" in relative:
        raise CurrentFotMobIngestCompatibilityError(f"{label} must be a nonempty POSIX path")
    parsed = PurePosixPath(relative)
    if (
        parsed.is_absolute()
        or parsed.as_posix() != relative
        or any(part in {"", ".", ".."} for part in parsed.parts)
    ):
        raise CurrentFotMobIngestCompatibilityError(f"{label} contains traversal or is not canonical")
    return parsed.parts


def _read_regular(root: Path, relative: str) -> bytes:
    parts = _relative_parts(relative, "artifact file path")
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise CurrentFotMobIngestCompatibilityError(
                f"artifact path contains a symlink: {relative}"
            )
    if not current.is_file():
        raise CurrentFotMobIngestCompatibilityError(
            f"artifact file is missing or not regular: {relative}"
        )
    try:
        return current.read_bytes()
    except OSError as exc:
        raise CurrentFotMobIngestCompatibilityError(
            f"artifact file could not be read: {relative}"
        ) from exc


def _canonical_mapping(root: Path, filename: str) -> tuple[dict[str, Any], bytes]:
    raw = _read_regular(root, filename)
    try:
        value = strict_json_loads(raw)
        if type(value) is not dict or canonical_json_bytes(value) != raw:
            raise CurrentFotMobIngestCompatibilityError(
                f"{filename} is not canonical JSON"
            )
        return value, raw
    except AthenaIngestContractError as exc:
        raise CurrentFotMobIngestCompatibilityError(
            f"{filename} is not valid strict canonical JSON"
        ) from exc


def _directory_names(path: Path, expected: set[str], label: str) -> None:
    if path.is_symlink() or not path.is_dir():
        raise CurrentFotMobIngestCompatibilityError(
            f"{label} must be a regular non-symlink directory"
        )
    try:
        entries = list(path.iterdir())
    except OSError as exc:
        raise CurrentFotMobIngestCompatibilityError(f"{label} cannot be inspected") from exc
    if {entry.name for entry in entries} != expected:
        raise CurrentFotMobIngestCompatibilityError(f"{label} entries differ from exact layout")
    if any(entry.is_symlink() for entry in entries):
        raise CurrentFotMobIngestCompatibilityError(f"{label} contains a symlink")


def _validate_exact_artifact_layout(root: Path, request: AthenaIngestRequest,
                                    capture_relative_path: str) -> Path:
    _directory_names(root, set(_TOP_LEVEL_ARTIFACT_NAMES), "artifact root")
    source_parts = _relative_parts(capture_relative_path, "capture path")
    if len(source_parts) != 4 or source_parts[:2] != ("sources", "fotmob"):
        raise CurrentFotMobIngestCompatibilityError("capture path is outside canonical FotMob layout")
    if source_parts[2] != request.dates[0]:
        raise CurrentFotMobIngestCompatibilityError("capture directory date differs from request")
    source_root = root / "sources"
    provider_root = source_root / "fotmob"
    date_root = provider_root / request.dates[0]
    capture_root = date_root / source_parts[3]
    _directory_names(source_root, {"fotmob"}, "sources directory")
    _directory_names(provider_root, {request.dates[0]}, "FotMob source directory")
    _directory_names(date_root, {source_parts[3]}, "capture date directory")
    _directory_names(capture_root, {"response.json", "manifest.json"}, "capture directory")
    return capture_root


def _utc(value: Any) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise CurrentFotMobIngestCompatibilityError("issued_at must be timezone-aware")
    try:
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentFotMobIngestCompatibilityError("issued_at is invalid") from exc


def _canonical_self_hash(payload: Mapping[str, Any]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "canonical_sha256"}
    return sha256_bytes(canonical_json_bytes(unsigned))


def _receipt_payload(
    *, request: AthenaIngestRequest,
    update: AthenaCanonicalStoreUpdate,
    ingest_receipt: AthenaIngestReceipt,
    execution: Any,
) -> dict[str, Any]:
    summary = execution.summary()
    policy_bytes = canonical_current_fotmob_fixture_review_policy_result_bytes(
        execution.policy_result
    )
    source = update.source_records[0]
    payload: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": COMPATIBILITY_POLICY_ID,
        "compatibility_scope": COMPATIBILITY_SCOPE,
        "ingest_request_sha256": request.canonical_sha256,
        "canonical_store_update_sha256": update.canonical_sha256,
        "canonical_ingest_receipt_sha256": ingest_receipt.canonical_sha256,
        "original_ingest_exact_commit_sha": ingest_receipt.exact_commit_sha,
        "request_date": request.dates[0],
        "provider": request.provider,
        "timezone": request.timezone,
        "ccode3": request.ccode3,
        "issued_at": execution.issued_at.isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z"),
        "source_count": 1,
        "source_capture_manifest_sha256": source.manifest_sha256,
        "source_raw_sha256": source.raw_sha256,
        "policy_result_sha256": sha256_bytes(policy_bytes),
        "handoff_sha256": sha256_fotmob_fixture_catalog_handoff(execution.handoff),
        "bootstrap_sha256": execution.verified_bootstrap.bootstrap_sha256,
        "verified_bootstrap_receipt_sha256": sha256_bytes(
            execution.verified_bootstrap_receipt_bytes
        ),
        "fixture_identifiers": list(summary["fixture_identifiers"]),
        "approved_count": execution.policy_result.policy_approved_count,
        "minimum_lead_seconds": execution.policy_result.minimum_lead_seconds,
        "max_source_age_seconds": execution.policy_result.max_source_age_seconds,
        "pr243_authority": summary["authority"],
        "provider_request_count_by_adapter": 0,
    }
    payload.update({key: False for key in _FALSE_RECEIPT_FIELDS})
    return payload


def _validate_receipt(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _RECEIPT_FIELDS:
        raise CurrentFotMobIngestCompatibilityError(
            "compatibility receipt fields differ from exact schema"
        )
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise CurrentFotMobIngestCompatibilityError("compatibility receipt schema mismatch")
    if value["policy_id"] != COMPATIBILITY_POLICY_ID or value["compatibility_scope"] != COMPATIBILITY_SCOPE:
        raise CurrentFotMobIngestCompatibilityError("compatibility receipt policy/scope mismatch")
    for name in (
        "ingest_request_sha256", "canonical_store_update_sha256",
        "canonical_ingest_receipt_sha256", "source_capture_manifest_sha256",
        "source_raw_sha256", "policy_result_sha256", "handoff_sha256",
        "bootstrap_sha256", "verified_bootstrap_receipt_sha256",
        "canonical_sha256",
    ):
        _sha(value[name], name)
    _sha(value["original_ingest_exact_commit_sha"], "original_ingest_exact_commit_sha", pattern=_SHA1_RE)
    if (
        value["provider"] != "fotmob"
        or value["timezone"] != "UTC"
        or value["ccode3"] != "NGA"
        or type(value["request_date"]) is not str
    ):
        raise CurrentFotMobIngestCompatibilityError("compatibility request scope mismatch")
    request = AthenaIngestRequest.for_dates((value["request_date"],))
    if request.provider != value["provider"] or request.timezone != value["timezone"] or request.ccode3 != value["ccode3"]:
        raise CurrentFotMobIngestCompatibilityError("compatibility request identity mismatch")
    if type(value["issued_at"]) is not str or not value["issued_at"].endswith("Z"):
        raise CurrentFotMobIngestCompatibilityError("issued_at is not canonical UTC")
    try:
        issued = datetime.fromisoformat(value["issued_at"][:-1] + "+00:00")
    except ValueError as exc:
        raise CurrentFotMobIngestCompatibilityError("issued_at is invalid") from exc
    if issued.utcoffset() != timezone.utc.utcoffset(issued):
        raise CurrentFotMobIngestCompatibilityError("issued_at is not UTC")
    if type(value["source_count"]) is not int or value["source_count"] != 1:
        raise CurrentFotMobIngestCompatibilityError("compatibility source count mismatch")
    if type(value["provider_request_count_by_adapter"]) is not int or value["provider_request_count_by_adapter"] != 0:
        raise CurrentFotMobIngestCompatibilityError("adapter provider request count is not zero")
    if type(value["fixture_identifiers"]) is not list or not value["fixture_identifiers"] or any(
        type(item) is not str or not item for item in value["fixture_identifiers"]
    ):
        raise CurrentFotMobIngestCompatibilityError("fixture identifiers are invalid")
    if type(value["approved_count"]) is not int or value["approved_count"] != len(value["fixture_identifiers"]):
        raise CurrentFotMobIngestCompatibilityError("approved fixture count mismatch")
    if type(value["minimum_lead_seconds"]) is not int or value["minimum_lead_seconds"] != DEFAULT_MINIMUM_LEAD_SECONDS:
        raise CurrentFotMobIngestCompatibilityError("PR243 minimum lead differs")
    if type(value["max_source_age_seconds"]) is not int or value["max_source_age_seconds"] != DEFAULT_MAX_SOURCE_AGE_SECONDS:
        raise CurrentFotMobIngestCompatibilityError("PR243 source age differs")
    if type(value["pr243_authority"]) is not dict or value["pr243_authority"] != _PR243_AUTHORITY or any(
        type(flag) is not bool for flag in value["pr243_authority"].values()
    ):
        raise CurrentFotMobIngestCompatibilityError("PR243 authority flags differ")
    for key in _FALSE_RECEIPT_FIELDS:
        if type(value[key]) is not bool or value[key] is not False:
            raise CurrentFotMobIngestCompatibilityError(f"{key} must be exact false")
    if value["canonical_sha256"] != _canonical_self_hash(value):
        raise CurrentFotMobIngestCompatibilityError("compatibility receipt self-hash mismatch")
    return value


@dataclass(frozen=True)
class CurrentFotMobIngestCompatibilityResult:
    """Deterministic PR243 projection and its canonical compatibility receipt."""

    receipt_bytes: bytes
    execution: Any

    @property
    def receipt(self) -> dict[str, Any]:
        value = strict_json_loads(self.receipt_bytes)
        return _validate_receipt(value)

    @property
    def compatibility_receipt_sha256(self) -> str:
        return sha256_bytes(self.receipt_bytes)


def project_current_reviewed_fotmob_source_from_ingest_artifact(
    artifact_root: Path,
    *,
    issued_at: datetime,
    repository_root: Path,
    code_state: Mapping[str, Any] | None = None,
) -> CurrentFotMobIngestCompatibilityResult:
    """Verify and project exactly one completed canonical capture through PR243."""

    root = _artifact_root(artifact_root)
    normalized_issued_at = _utc(issued_at)
    try:
        replay = replay_ingest_artifact(root)
    except (AthenaIngestReplayError, OSError, ValueError) as exc:
        raise CurrentFotMobIngestCompatibilityError(
            f"canonical ingest offline replay failed: {exc}"
        ) from exc

    try:
        request_mapping, request_raw = _canonical_mapping(root, REQUEST_NAME)
        request = AthenaIngestRequest.from_mapping(request_mapping)
        if request_raw != request.canonical_bytes:
            raise CurrentFotMobIngestCompatibilityError("request bytes are not canonical")
        if len(request.dates) != 1 or request.provider != "fotmob" or request.timezone != "UTC" or request.ccode3 != "NGA":
            raise CurrentFotMobIngestCompatibilityError("request is outside exact P4.4D scope")

        update_mapping, update_raw = _canonical_mapping(root, UPDATE_NAME)
        update = AthenaCanonicalStoreUpdate.from_mapping(update_mapping)
        if update_raw != update.canonical_bytes:
            raise CurrentFotMobIngestCompatibilityError("canonical update bytes are not canonical")
        receipt_mapping, ingest_receipt_raw = _canonical_mapping(root, RECEIPT_NAME)
        ingest_receipt = AthenaIngestReceipt.from_mapping(receipt_mapping)
        if ingest_receipt_raw != ingest_receipt.canonical_bytes:
            raise CurrentFotMobIngestCompatibilityError("ingest receipt bytes are not canonical")
        _replay_mapping, replay_raw = _canonical_mapping(root, REPLAY_NAME)
        if replay_raw != canonical_json_bytes(_replay_mapping):
            raise CurrentFotMobIngestCompatibilityError("replay manifest bytes are not canonical")

        if (
            ingest_receipt.status != "SUCCESS"
            or ingest_receipt.failure_code is not None
            or ingest_receipt.stage != "COMPLETED"
            or not ingest_receipt.canonical_store_update_committed
            or update.commit_status != "CANONICAL_SOURCE_UPDATE_READY"
            or not update.all_requested_dates_captured
        ):
            raise CurrentFotMobIngestCompatibilityError("only a completed committed ingest is compatible")
        if (
            update.request_sha256 != request.canonical_sha256
            or ingest_receipt.request_sha256 != request.canonical_sha256
            or ingest_receipt.canonical_store_update_sha256 != update.canonical_sha256
        ):
            raise CurrentFotMobIngestCompatibilityError("ingest request/update/receipt binding mismatch")
        if (
            len(update.source_records) != 1
            or update.source_record_count != 1
            or ingest_receipt.source_count != 1
            or ingest_receipt.provider_request_count != 1
        ):
            raise CurrentFotMobIngestCompatibilityError("compatible ingest requires exactly one acquired source")
        source = update.source_records[0]
        if (
            source.provider != "fotmob"
            or source.request_date != request.dates[0]
            or source.timezone != "UTC"
            or source.ccode3 != "NGA"
            or source.network_acquisition_performed is not True
        ):
            raise CurrentFotMobIngestCompatibilityError("source provenance differs from compatible request")
        if (
            replay.get("status") != "ATHENA_INGEST_OFFLINE_REPLAY_VERIFIED"
            or replay.get("network_acquisition_performed") is not False
            or replay.get("provider_request_count") != 0
            or replay.get("source_count") != 1
            or replay.get("request_sha256") != request.canonical_sha256
            or replay.get("canonical_store_update_sha256") != update.canonical_sha256
            or replay.get("exact_commit_sha") != ingest_receipt.exact_commit_sha
            or replay.get("original_ingest_receipt_sha256") != ingest_receipt.canonical_sha256
        ):
            raise CurrentFotMobIngestCompatibilityError("offline replay proof does not bind exact ingest")

        capture = _validate_exact_artifact_layout(
            root, request, source.capture_relative_path
        )
        raw_before = _read_regular(root, f"{source.capture_relative_path}/response.json")
        manifest_before = _read_regular(root, f"{source.capture_relative_path}/manifest.json")
        if sha256_bytes(raw_before) != source.raw_sha256 or sha256_bytes(manifest_before) != source.manifest_sha256:
            raise CurrentFotMobIngestCompatibilityError("source raw/manifest identity differs")
        capture_manifest = verify_data_matches_capture_directory(
            capture, allowed_root=root / "sources" / "fotmob",
            require_network_acquisition_performed=True,
        )
        if (
            capture_manifest.request_date != request.dates[0]
            or capture_manifest.timezone != "UTC"
            or capture_manifest.ccode3 != "NGA"
            or capture_manifest.network_acquisition_performed is not True
            or capture_manifest.raw_sha256 != source.raw_sha256
        ):
            raise CurrentFotMobIngestCompatibilityError("capture manifest provenance differs")

        try:
            execution = _build_verified_current_fotmob_bootstrap_from_capture(
                capture,
                issued_at=normalized_issued_at,
                repository_root=repository_root,
                code_state=code_state,
                shadow_policy=False,
                capture_root_override=root / "sources" / "fotmob",
            )
        except CurrentFotMobReviewedSourceError as exc:
            raise CurrentFotMobIngestCompatibilityError(
                f"existing PR243 replay rejected canonical source: {exc}"
            ) from exc
        if (
            execution.source_capture_manifest_sha256 != source.manifest_sha256
            or execution.source_raw_sha256 != source.raw_sha256
            or execution.source_capture_directory.resolve(strict=True) != capture.resolve(strict=True)
        ):
            raise CurrentFotMobIngestCompatibilityError(
                "PR243 replay did not preserve exact in-place source identity"
            )
        if (
            _read_regular(root, f"{source.capture_relative_path}/response.json") != raw_before
            or _read_regular(root, f"{source.capture_relative_path}/manifest.json") != manifest_before
        ):
            raise CurrentFotMobIngestCompatibilityError(
                "PR243 replay modified canonical source bytes"
            )

        payload = _receipt_payload(
            request=request,
            update=update,
            ingest_receipt=ingest_receipt,
            execution=execution,
        )
        payload["canonical_sha256"] = _canonical_self_hash(payload)
        receipt_bytes = canonical_json_bytes(payload)
        _validate_receipt(strict_json_loads(receipt_bytes))
        return CurrentFotMobIngestCompatibilityResult(
            receipt_bytes=receipt_bytes,
            execution=execution,
        )
    except CurrentFotMobIngestCompatibilityError:
        raise
    except (AthenaIngestContractError, FotMobDataMatchesCaptureError, OSError, TypeError, ValueError) as exc:
        raise CurrentFotMobIngestCompatibilityError(str(exc)) from exc


def verify_current_fotmob_ingest_compatibility_receipt(
    receipt: bytes | Mapping[str, Any],
    artifact_root: Path,
    *,
    repository_root: Path,
    code_state: Mapping[str, Any] | None = None,
) -> CurrentFotMobIngestCompatibilityResult:
    """Rebuild and compare a compatibility receipt against its source artifact."""

    try:
        raw = receipt if type(receipt) is bytes else canonical_json_bytes(dict(receipt))
        value = strict_json_loads(raw)
        if type(value) is not dict or canonical_json_bytes(value) != raw:
            raise CurrentFotMobIngestCompatibilityError("compatibility receipt is not canonical")
        _validate_receipt(value)
        issued_at = datetime.fromisoformat(value["issued_at"][:-1] + "+00:00")
        expected = project_current_reviewed_fotmob_source_from_ingest_artifact(
            artifact_root,
            issued_at=issued_at,
            repository_root=repository_root,
            code_state=code_state,
        )
        if raw != expected.receipt_bytes:
            raise CurrentFotMobIngestCompatibilityError(
                "compatibility receipt does not reproduce from exact ingest source"
            )
        return expected
    except CurrentFotMobIngestCompatibilityError:
        raise
    except (AthenaIngestContractError, TypeError, ValueError) as exc:
        raise CurrentFotMobIngestCompatibilityError(
            "compatibility receipt could not be verified"
        ) from exc


__all__ = [
    "COMPATIBILITY_POLICY_ID",
    "COMPATIBILITY_SCOPE",
    "CurrentFotMobIngestCompatibilityError",
    "CurrentFotMobIngestCompatibilityResult",
    "project_current_reviewed_fotmob_source_from_ingest_artifact",
    "verify_current_fotmob_ingest_compatibility_receipt",
]
