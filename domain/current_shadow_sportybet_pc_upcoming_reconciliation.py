"""Runtime reconciliation wrapper for the reviewed global pcUpcoming source.

This module is the only current Current Shadow/P3 discovery owner.  The source
contract remains owned by ``current_shadow_sportybet_pc_upcoming_discovery``;
this wrapper adds complete-pagination, identity, reconciliation, and direct
event-confirmation authority without creating another HTTP implementation.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import MappingProxyType, SimpleNamespace
from typing import Any, Mapping, Sequence

from domain import current_shadow_sportybet_pc_upcoming_discovery as source
from domain import current_shadow_sportybet_upcoming_reconciliation as legacy
from domain import current_shadow_fixture_identity_compatibility as identity_compatibility
from domain import current_shadow_fixture_identity_v2 as fixture_identity_v2
from domain import current_shadow_sportybet_international_provider_family_bridge as bridge
from domain import sportybet_current_event_discovery_reconciliation as reviewed
from domain import sportybet_live_event_quote_evidence as live
from domain.fotmob_data_matches_capture import FotMobDataMatchesCaptureManifest

POLICY_ID = "ATHENA_CURRENT_SHADOW_PC_UPCOMING_DISCOVERY_RECONCILIATION_V1"
STATUS = "CURRENT_SHADOW_PC_UPCOMING_DISCOVERY_RECONCILIATION_VERIFIED"
STRATEGY_ID = POLICY_ID
CURRENT_SHADOW_UPCOMING_POLICY_ID = POLICY_ID
DISCOVERY_SOURCE_METHOD = source.SOURCE_METHOD
UPCOMING_PATH = source.SOURCE_PATH
UPSTREAM_SOURCE_POLICY_ID = source.POLICY_ID
UPSTREAM_SOURCE_POLICY_SHA256 = "63799058bec00abefb8d9b2ec9ba6dcad0c6e4775a54f17b07c0018e543ec075"
UPSTREAM_SOURCE_RECEIPT_SHA256 = "8dde6427c296d966ff8d7f4cdec33e57a8c4210e8ecdb37071af68b0ca75bb34"
BRIDGE_POLICY_ID = bridge.POLICY_ID
BRIDGE_POLICY_SHA256 = "7db676111a9be06f63fd207815837d53699d6bf1a98364fc2163046cd1c0a4bb"
BRIDGE_RECEIPT_SHA256 = "34c183b5274e9e2c3320b5a8d75a123b7ebed2405aa55cdfb1af7d59c2613aa2"
V2_REGISTRY_SHA256 = "fc64fb0c2df3cee4f425158c48cfaada6757ba01e1759dd5b976ca899f85421e"
IDENTITY_COMPATIBILITY_SHA256 = "2fdbb8165262f6e633ee48276aea57c9235699272235798e1cef12fdc714ae04"
DIRECT_EVENT_CONTRACT_SHA256 = live.EXPECTED_CONTRACT_SHA256
MAX_SOURCE_AGE_SECONDS = legacy.MAX_SOURCE_AGE_SECONDS
MINIMUM_LEAD_SECONDS = legacy.MINIMUM_LEAD_SECONDS
MAX_PAGES = source.MAX_PAGES
PAGE_SIZE = source.PAGE_SIZE
MAX_CAPTURE_EPOCHS = 2
MAX_PAGES_PER_EPOCH = MAX_PAGES
MAX_SUCCESSFUL_PAGE_RESPONSES = MAX_CAPTURE_EPOCHS * MAX_PAGES_PER_EPOCH
TOTALNUM_DRIFT_ERROR = source.TOTALNUM_DRIFT_ERROR
EVIDENCE_ROOT = source.EVIDENCE_ROOT
ALLOWED_OUTPUT_RELATIVE = EVIDENCE_ROOT
RUNTIME_ATTEMPTS_DIRECTORY = "runtime-attempts"
STABILIZATION_RECEIPT_FILENAME = "runtime-capture-stabilization.json"
INCOMPLETE_PAGINATION_STATE = "PC_UPCOMING_RUNTIME_PAGINATION_INCOMPLETE"
PROSPECTIVE_DISCOVERY_ELIGIBLE = legacy.PROSPECTIVE_DISCOVERY_ELIGIBLE
PROSPECTIVE_DISCOVERY_NO_PREMATCH_EVENTS = legacy.PROSPECTIVE_DISCOVERY_NO_PREMATCH_EVENTS
PcUpcomingDiscoveryManifest = source.PcUpcomingDiscoveryManifest

AUTHORITY = MappingProxyType({
    "research_shadow_provider_acquisition": True,
    "p3_pre_router_provider_acquisition": True,
    "fixture_reconciliation": True,
    "direct_event_confirmation": True,
    "model": False,
    "pricing": False,
    "router": False,
    "portfolio": False,
    "production_main": False,
    "login": False,
    "cookies": False,
    "wallet": False,
    "staking": False,
    "bet": False,
    "wager_placed": False,
})


class PcUpcomingRuntimeReconciliationError(ValueError):
    """Raised when the runtime wrapper cannot prove a complete safe source."""


# The runner's bounded failure taxonomy historically catches this module-shaped
# exception. The alias preserves that seam while retaining the new source-boundary
# error identity and stable incomplete-pagination state.
SportyBetCurrentEventDiscoveryError = PcUpcomingRuntimeReconciliationError


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _policy_payload() -> dict[str, Any]:
    return {
        "policy_id": POLICY_ID,
        "status": STATUS,
        "source_policy_id": UPSTREAM_SOURCE_POLICY_ID,
        "source_policy_sha256": UPSTREAM_SOURCE_POLICY_SHA256,
        "source_receipt_sha256": UPSTREAM_SOURCE_RECEIPT_SHA256,
        "bridge_policy_id": BRIDGE_POLICY_ID,
        "bridge_policy_sha256": BRIDGE_POLICY_SHA256,
        "bridge_receipt_sha256": BRIDGE_RECEIPT_SHA256,
        "v2_semantic_registry_sha256": V2_REGISTRY_SHA256,
        "identity_compatibility_sha256": IDENTITY_COMPATIBILITY_SHA256,
        "source_method": DISCOVERY_SOURCE_METHOD,
        "source_path": UPCOMING_PATH,
        "fixed_query": {
            "sportId": source.FOOTBALL_SPORT_ID,
            "marketId": source.MARKET_ID,
            "pageSize": source.PAGE_SIZE,
            "todayGames": source.TODAY_GAMES,
            "timeline": source.TIMELINE_HOURS,
            "pageNum": "CONTIGUOUS_1_THROUGH_CEIL_PROVIDER_TOTAL_NUM_OVER_PAGE_SIZE",
            "_t": "RESPONSE_SCOPED_NONCE",
        },
        "runtime_pagination": {
            "required": True,
            "pagination_complete_exact_true": True,
            "captured_event_count_equals_provider_total_num": True,
            "required_page_count": "CEIL_PROVIDER_TOTAL_NUM_OVER_100",
            "max_pages": MAX_PAGES,
            "partial_capture_provider_absence_authority": False,
        },
        "capture_stabilization": {
            "recovery_semantics": "FRESH_CAPTURE_EPOCH_AFTER_EXACT_CROSS_PAGE_TOTALNUM_DRIFT",
            "exact_first_epoch_trigger": TOTALNUM_DRIFT_ERROR,
            "max_capture_epochs": MAX_CAPTURE_EPOCHS,
            "max_pages_per_epoch": MAX_PAGES_PER_EPOCH,
            "max_successful_page_responses": MAX_SUCCESSFUL_PAGE_RESPONSES,
            "each_epoch_starts_at_page": 1,
            "no_per_page_http_retry": True,
            "no_third_capture_epoch": True,
            "failed_epoch_provider_absence_authority": False,
            "failed_epoch_identity_learning_authority": False,
            "failed_epoch_reconciliation_authority": False,
            "failed_epoch_selection_authority": False,
            "failed_epoch_pricing_authority": False,
            "failed_epoch_router_authority": False,
            "failed_epoch_portfolio_authority": False,
            "failed_epoch_delivery_authority": False,
            "cross_epoch_event_merge": False,
            "accepted_epoch_independently_source_v1_verified": True,
            "accepted_epoch_independently_runtime_complete": True,
            "source_fallback": False,
            "all_attempt_evidence_retained_under_source_evidence_root": True,
            "workflow_retry": False,
            "per_page_transport_retry": False,
            "provider_request_upper_bound_is_finite": True,
        },
        "identity_observation_order": [
            "EXACT_PROVIDER_RAW_PAGE_BYTES",
            "RAW_ANCESTRY_BOUND_ATHENA_PROVIDER_IDENTITY_PROJECTION",
        ],
        "provider_identity_source_ancestry": "EXACT_PC_UPCOMING_PAGE_RAW_SHA256",
        "bundle_replay_provenance": [
            "VERIFIED_PC_UPCOMING_MANIFEST_AND_EACH_PAGE_RAW_SHA256",
            "ACCEPTED_RUNTIME_STABILIZATION_RECEIPT_SHA256",
            "EXACT_FOTMOB_ADMISSION_AND_CAPTURE_IDENTITIES",
            "DIRECT_EVENT_DETAIL_EVENT_IDS_AND_RAW_SHA256S",
            "APPEND_ONLY_IDENTITY_STATE_SNAPSHOT_SHA256",
        ],
        "direct_event_contract_sha256": DIRECT_EVENT_CONTRACT_SHA256,
        "reconciliation": {
            "kickoff": "EXACT_FULL_UTC",
            "orientation": "EXACT_HOME_AWAY",
            "international_bridge": "EXACT_REVIEWED_PROVIDER_FAMILY_ONLY",
            "no_fallback_source": True,
        },
        "authority": dict(AUTHORITY),
    }


def calculate_policy_sha256() -> str:
    return hashlib.sha256(_canonical(_policy_payload())).hexdigest()


PINNED_POLICY_SHA256 = "dac1f99da0b536b3808f8c7e41f66ad501101871d811131f8ede9e5dc99d4a5f"
EXPECTED_CONTRACT_SHA256 = PINNED_POLICY_SHA256
CURRENT_SHADOW_UPCOMING_COMPATIBILITY_SHA256 = PINNED_POLICY_SHA256


def validate_contract() -> Mapping[str, Any]:
    if source.POLICY_ID != UPSTREAM_SOURCE_POLICY_ID or source.calculate_policy_sha256() != UPSTREAM_SOURCE_POLICY_SHA256:
        raise PcUpcomingRuntimeReconciliationError("PR #405 pcUpcoming source policy ancestry drifted")
    if bridge.POLICY_ID != BRIDGE_POLICY_ID or bridge.calculate_policy_sha256() != BRIDGE_POLICY_SHA256:
        raise PcUpcomingRuntimeReconciliationError("PR #406 international bridge ancestry drifted")
    if fixture_identity_v2.registry_sha256() != V2_REGISTRY_SHA256:
        raise PcUpcomingRuntimeReconciliationError("V2 semantic identity registry pin drifted")
    if identity_compatibility.calculate_policy_sha256() != IDENTITY_COMPATIBILITY_SHA256:
        raise PcUpcomingRuntimeReconciliationError("identity compatibility policy pin drifted")
    if calculate_policy_sha256() != PINNED_POLICY_SHA256:
        raise PcUpcomingRuntimeReconciliationError("pcUpcoming runtime wrapper policy SHA drifted")
    for key, value in AUTHORITY.items():
        if type(value) is not bool:
            raise PcUpcomingRuntimeReconciliationError(f"authority value {key} is not boolean")
    return MappingProxyType({
        "runtime_policy_id": POLICY_ID,
        "runtime_policy_sha256": PINNED_POLICY_SHA256,
        "source_policy_id": UPSTREAM_SOURCE_POLICY_ID,
        "source_policy_sha256": UPSTREAM_SOURCE_POLICY_SHA256,
        "bridge_policy_id": BRIDGE_POLICY_ID,
        "bridge_policy_sha256": BRIDGE_POLICY_SHA256,
        "v2_semantic_registry_sha256": V2_REGISTRY_SHA256,
        "identity_compatibility_policy_sha256": IDENTITY_COMPATIBILITY_SHA256,
        "source_method": DISCOVERY_SOURCE_METHOD,
        "source_path": UPCOMING_PATH,
        "pagination_complete_required": True,
        "capture_stabilization": MappingProxyType(dict(_policy_payload()["capture_stabilization"])),
    })


def _require_complete(manifest: source.PcUpcomingDiscoveryManifest) -> None:
    required_pages = max(1, (manifest.provider_total_num + PAGE_SIZE - 1) // PAGE_SIZE)
    if (
        manifest.pagination_complete is not True
        or manifest.captured_event_count != manifest.provider_total_num
        or manifest.captured_page_count != required_pages
        or tuple(page.page_num for page in manifest.pages) != tuple(range(1, required_pages + 1))
        or required_pages > MAX_PAGES
    ):
        raise PcUpcomingRuntimeReconciliationError(INCOMPLETE_PAGINATION_STATE)


def _seal_document(payload: Mapping[str, Any]) -> dict[str, Any]:
    sealed = dict(payload)
    sealed["canonical_sha256"] = hashlib.sha256(_canonical(dict(payload))).hexdigest()
    return sealed


def _read_runtime_json(path: Path, *, max_bytes: int = source.MAX_MANIFEST_BYTES) -> Any:
    try:
        raw = source._read_regular(path, max_bytes=max_bytes)
        return source._strict_json_loads(raw)
    except source.PcUpcomingDiscoveryError as exc:
        raise PcUpcomingRuntimeReconciliationError("runtime capture journal is not a regular verified file") from exc


def _write_json(path: Path, payload: Mapping[str, Any], *, replace_existing: bool = False) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PcUpcomingRuntimeReconciliationError(
            "could not create runtime capture evidence directory"
        ) from exc
    raw = _canonical(dict(payload)) + b"\n"
    if not replace_existing:
        try:
            source._write_exclusive(path, raw)
        except Exception as exc:
            raise PcUpcomingRuntimeReconciliationError(
                "could not persist runtime capture evidence"
            ) from exc
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f"{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise PcUpcomingRuntimeReconciliationError(
            "could not persist runtime capture stabilization evidence"
        ) from exc


def _page_observation(page: source.PcUpcomingPageEvidence, attempt_index: int) -> dict[str, Any]:
    return {
        "attempt_index": attempt_index,
        "page_num": page.page_num,
        "request_target": page.request_target,
        "request_nonce": page.request_nonce_ms,
        "observed_at": source._utc_text(page.observed_at),
        "raw_sha256": page.raw_sha256,
        "raw_byte_count": page.raw_size,
        "totalNum": page.total_num,
        "tournament_count": page.tournament_count,
        "event_count": page.event_count,
    }


def _read_page_observations(attempt_root: Path) -> list[dict[str, Any]]:
    path = attempt_root / "page-observations.json"
    if not path.exists():
        return []
    try:
        value = _read_runtime_json(path)
    except PcUpcomingRuntimeReconciliationError as exc:
        raise PcUpcomingRuntimeReconciliationError("runtime page-observation journal is unreadable") from exc
    if type(value) is not dict:
        raise PcUpcomingRuntimeReconciliationError("runtime page-observation journal shape is invalid")
    embedded = value.get("canonical_sha256")
    semantic = dict(value)
    semantic.pop("canonical_sha256", None)
    if embedded != hashlib.sha256(_canonical(semantic)).hexdigest():
        raise PcUpcomingRuntimeReconciliationError("runtime page-observation journal SHA mismatch")
    pages = value.get("pages")
    if value.get("schema_version") != 1 or type(pages) is not list:
        raise PcUpcomingRuntimeReconciliationError("runtime page-observation journal shape is invalid")
    return pages


def _write_page_observations(attempt_root: Path, attempt_index: int,
                             pages: Sequence[Mapping[str, Any]]) -> None:
    payload = _seal_document({
        "schema_version": 1,
        "attempt_index": attempt_index,
        "pages": [dict(item) for item in pages],
    })
    _write_json(attempt_root / "page-observations.json", payload, replace_existing=True)


def _attempt_receipt(
    *, attempt_index: int, attempt_root: Path, status: str,
    failure_class: str | None, failure_message: str | None,
    observations: Sequence[Mapping[str, Any]], accepted: bool,
) -> dict[str, Any]:
    manifest_path = attempt_root / "manifest.json"
    manifest_sha256: str | None = None
    if manifest_path.is_file():
        try:
            raw_manifest = manifest_path.read_bytes()
            manifest_value = json.loads(raw_manifest.decode("utf-8"))
            manifest_sha256 = manifest_value.get("canonical_sha256") if type(manifest_value) is dict else None
        except (OSError, UnicodeError, json.JSONDecodeError):
            manifest_sha256 = None
    observation_document: dict[str, Any] | None = None
    observation_path = attempt_root / "page-observations.json"
    if observation_path.is_file():
        try:
            observation_document = json.loads(observation_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            observation_document = None
    payload = {
        "schema_version": 1,
        "attempt_index": attempt_index,
        "status": status,
        "failure_class": failure_class,
        "failure_message": failure_message,
        "successful_page_response_count": len(observations),
        "observed_totalNum_sequence": [item["totalNum"] for item in observations],
        "raw_page_sha256s": [item["raw_sha256"] for item in observations],
        "stable_totalNum": len({item["totalNum"] for item in observations}) <= 1,
        "manifest_emitted": manifest_path.is_file(),
        "manifest_canonical_sha256": manifest_sha256,
        "page_observations_sha256": (
            observation_document.get("canonical_sha256")
            if type(observation_document) is dict else None
        ),
        "accepted_by_runtime": accepted,
    }
    receipt = _seal_document(payload)
    _write_json(attempt_root / "attempt-receipt.json", receipt, replace_existing=True)
    return receipt


def _stabilization_base() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "runtime_policy_id": POLICY_ID,
        "runtime_policy_sha256": PINNED_POLICY_SHA256,
        "source_v1_policy_id": UPSTREAM_SOURCE_POLICY_ID,
        "source_v1_policy_sha256": UPSTREAM_SOURCE_POLICY_SHA256,
        "max_capture_epochs": MAX_CAPTURE_EPOCHS,
        "max_pages_per_epoch": MAX_PAGES_PER_EPOCH,
        "max_successful_page_responses": MAX_SUCCESSFUL_PAGE_RESPONSES,
        "attempt_count": 0,
        "accepted_attempt_index": None,
        "failed_attempt_indices": [],
        "attempt_receipts": [],
        "workflow_retry": False,
        "per_page_transport_retry": False,
        "fallback": False,
        "provider_absence_from_failed_attempt": False,
        "identity_learning_from_failed_attempt": False,
        "reconciliation_from_failed_attempt": False,
        "selection_from_failed_attempt": False,
        "pricing_from_failed_attempt": False,
        "router_from_failed_attempt": False,
        "portfolio_from_failed_attempt": False,
        "delivery_from_failed_attempt": False,
        "cross_epoch_event_merge": False,
        "final_state": "IN_PROGRESS",
    }


def _persist_stabilization(root: Path, state: Mapping[str, Any]) -> dict[str, Any]:
    receipt = _seal_document(state)
    _write_json(root / STABILIZATION_RECEIPT_FILENAME, receipt, replace_existing=True)
    return receipt


def _record_attempt(root: Path, state: dict[str, Any], receipt: Mapping[str, Any],
                    *, failed: bool, final_state: str) -> None:
    summaries = list(state["attempt_receipts"])
    summaries.append({
        "attempt_index": receipt["attempt_index"],
        "status": receipt["status"],
        "attempt_receipt_sha256": receipt["canonical_sha256"],
    })
    state["attempt_receipts"] = summaries
    state["attempt_count"] = int(receipt["attempt_index"])
    failed_indices = list(state["failed_attempt_indices"])
    if failed:
        failed_indices.append(int(receipt["attempt_index"]))
    state["failed_attempt_indices"] = failed_indices
    state["final_state"] = final_state
    _persist_stabilization(root, state)


def _promote_accepted_epoch(
    *, repository_root: Path, attempt_root: Path,
    manifest: source.PcUpcomingDiscoveryManifest,
) -> source.PcUpcomingDiscoveryManifest:
    root = repository_root / EVIDENCE_ROOT
    stage = root / "runtime-promotion-stage"
    if stage.exists() or (root / "pages").exists() or (root / "manifest.json").exists():
        raise PcUpcomingRuntimeReconciliationError("canonical pcUpcoming evidence destination already exists")
    stage.mkdir(parents=False, exist_ok=False)
    try:
        stage_pages = stage / "pages"
        stage_pages.mkdir()
        for page in manifest.pages:
            raw = (attempt_root / page.raw_relative_path).read_bytes()
            if hashlib.sha256(raw).hexdigest() != page.raw_sha256:
                raise PcUpcomingRuntimeReconciliationError("accepted attempt raw page changed before promotion")
            source._write_exclusive(stage_pages / Path(page.raw_relative_path).name, raw)
        manifest_bytes = (attempt_root / "manifest.json").read_bytes()
        source._write_exclusive(stage / "manifest.json", manifest_bytes)
        staged = source._verify_manifest_at_root(evidence_root=stage)
        _require_complete(staged)
        if staged.to_dict() != manifest.to_dict():
            raise PcUpcomingRuntimeReconciliationError("staged accepted V1 manifest differs from its capture epoch")
        stage_pages.rename(root / "pages")
        (stage / "manifest.json").rename(root / "manifest.json")
        promoted = source.verify_current_pc_upcoming_discovery(repository_root=repository_root)
        _require_complete(promoted)
        if promoted.to_dict() != manifest.to_dict():
            raise PcUpcomingRuntimeReconciliationError("canonical promoted V1 manifest differs from accepted epoch")
        stage.rmdir()
        return promoted
    except Exception:
        # Promotion never consumes attempt evidence. If canonical publication is
        # interrupted, move only these newly-created copies back into staging.
        try:
            promoted_manifest = root / "manifest.json"
            promoted_pages = root / "pages"
            if promoted_manifest.exists() and not (stage / "manifest.json").exists():
                promoted_manifest.rename(stage / "manifest.json")
            if promoted_pages.exists() and not (stage / "pages").exists():
                promoted_pages.rename(stage / "pages")
        except OSError:
            pass
        raise


def verify_runtime_capture_stabilization(
    *, repository_root: str | Path,
) -> Mapping[str, Any]:
    """Offline replay of the bounded runtime capture journal and accepted V1 epoch."""
    validate_contract()
    repository = Path(repository_root)
    root = repository / EVIDENCE_ROOT
    path = root / STABILIZATION_RECEIPT_FILENAME
    try:
        receipt = _read_runtime_json(path)
    except PcUpcomingRuntimeReconciliationError as exc:
        raise PcUpcomingRuntimeReconciliationError("runtime stabilization receipt is unavailable") from exc
    if type(receipt) is not dict:
        raise PcUpcomingRuntimeReconciliationError("runtime stabilization receipt shape is invalid")
    embedded = receipt.get("canonical_sha256")
    semantic = dict(receipt)
    semantic.pop("canonical_sha256", None)
    if embedded != hashlib.sha256(_canonical(semantic)).hexdigest():
        raise PcUpcomingRuntimeReconciliationError("runtime stabilization receipt SHA mismatch")
    expected_base = _stabilization_base()
    for key, value in expected_base.items():
        if key not in receipt and key not in {"attempt_count", "accepted_attempt_index", "failed_attempt_indices", "attempt_receipts", "final_state"}:
            raise PcUpcomingRuntimeReconciliationError(f"runtime stabilization field is missing: {key}")
    if (
        receipt.get("schema_version") != 1
        or receipt.get("runtime_policy_id") != POLICY_ID
        or receipt.get("runtime_policy_sha256") != PINNED_POLICY_SHA256
        or receipt.get("source_v1_policy_id") != UPSTREAM_SOURCE_POLICY_ID
        or receipt.get("source_v1_policy_sha256") != UPSTREAM_SOURCE_POLICY_SHA256
        or receipt.get("max_capture_epochs") != MAX_CAPTURE_EPOCHS
        or receipt.get("max_pages_per_epoch") != MAX_PAGES_PER_EPOCH
        or receipt.get("max_successful_page_responses") != MAX_SUCCESSFUL_PAGE_RESPONSES
        or receipt.get("workflow_retry") is not False
        or receipt.get("per_page_transport_retry") is not False
        or receipt.get("fallback") is not False
        or receipt.get("provider_absence_from_failed_attempt") is not False
        or receipt.get("identity_learning_from_failed_attempt") is not False
        or receipt.get("reconciliation_from_failed_attempt") is not False
        or receipt.get("selection_from_failed_attempt") is not False
        or receipt.get("pricing_from_failed_attempt") is not False
        or receipt.get("router_from_failed_attempt") is not False
        or receipt.get("portfolio_from_failed_attempt") is not False
        or receipt.get("delivery_from_failed_attempt") is not False
        or receipt.get("cross_epoch_event_merge") is not False
    ):
        raise PcUpcomingRuntimeReconciliationError("runtime stabilization policy or authority fields drifted")
    attempts = receipt.get("attempt_receipts")
    count = receipt.get("attempt_count")
    if type(attempts) is not list or type(count) is not int or not 1 <= count <= MAX_CAPTURE_EPOCHS or len(attempts) != count:
        raise PcUpcomingRuntimeReconciliationError("runtime capture epoch count is outside the pinned bound")
    attempts_root = root / RUNTIME_ATTEMPTS_DIRECTORY
    if root.is_symlink() or attempts_root.is_symlink():
        raise PcUpcomingRuntimeReconciliationError("runtime evidence root must not contain symlinks")
    failed_indices: list[int] = []
    attempt_documents: dict[int, dict[str, Any]] = {}
    total_successful_pages = 0
    for expected_index, summary in enumerate(attempts, 1):
        attempt_root = attempts_root / f"attempt-{expected_index:03d}"
        if attempt_root.is_symlink() or (attempt_root / "pages").is_symlink():
            raise PcUpcomingRuntimeReconciliationError("runtime attempt evidence must not contain symlinks")
        receipt_path = attempt_root / "attempt-receipt.json"
        observations_path = attempt_root / "page-observations.json"
        try:
            attempt_doc = _read_runtime_json(receipt_path)
        except PcUpcomingRuntimeReconciliationError as exc:
            raise PcUpcomingRuntimeReconciliationError("runtime attempt receipt is missing or malformed") from exc
        if type(attempt_doc) is not dict:
            raise PcUpcomingRuntimeReconciliationError("runtime attempt receipt shape is invalid")
        attempt_sha = attempt_doc.get("canonical_sha256")
        attempt_semantic = dict(attempt_doc)
        attempt_semantic.pop("canonical_sha256", None)
        if attempt_sha != hashlib.sha256(_canonical(attempt_semantic)).hexdigest():
            raise PcUpcomingRuntimeReconciliationError("runtime attempt receipt SHA mismatch")
        if summary != {
            "attempt_index": expected_index,
            "status": attempt_doc.get("status"),
            "attempt_receipt_sha256": attempt_sha,
        } or attempt_doc.get("attempt_index") != expected_index:
            raise PcUpcomingRuntimeReconciliationError("runtime attempt receipt index/ancestry drifted")
        observations = _read_page_observations(attempt_root)
        if any(type(item) is not dict for item in observations):
            raise PcUpcomingRuntimeReconciliationError("runtime page observation row is malformed")
        if observations_path.exists():
            observation_doc = _read_runtime_json(observations_path)
            if (
                type(observation_doc) is not dict
                or observation_doc.get("attempt_index") != expected_index
                or attempt_doc.get("page_observations_sha256") != observation_doc.get("canonical_sha256")
            ):
                raise PcUpcomingRuntimeReconciliationError("runtime attempt page-observation ancestry drifted")
        elif observations:
            raise PcUpcomingRuntimeReconciliationError("runtime page observations exist without their journal")
        elif attempt_doc.get("page_observations_sha256") is not None:
            raise PcUpcomingRuntimeReconciliationError("attempt receipt claims an absent page-observation journal")
        if len(observations) > MAX_PAGES_PER_EPOCH:
            raise PcUpcomingRuntimeReconciliationError("runtime attempt exceeds MAX_PAGES_PER_EPOCH")
        if tuple(item.get("page_num") for item in observations) != tuple(range(1, len(observations) + 1)):
            raise PcUpcomingRuntimeReconciliationError("runtime attempt pages are not contiguous from page 1")
        for item in observations:
            if type(item) is not dict or item.get("attempt_index") != expected_index:
                raise PcUpcomingRuntimeReconciliationError("runtime page observation row is malformed")
            try:
                raw = source._read_regular(
                    attempt_root / "pages" / f"page-{item['page_num']:03d}.raw.json",
                    max_bytes=source.MAX_RESPONSE_BYTES,
                )
                observed_at = source._parse_utc_text(item["observed_at"], "page observed_at")
                page = source.parse_page(
                    raw, page_num=item["page_num"],
                    request_nonce_ms=item["request_nonce"], observed_at=observed_at,
                )
            except Exception as exc:
                raise PcUpcomingRuntimeReconciliationError("runtime page observation raw replay failed") from exc
            if item != _page_observation(page, expected_index):
                raise PcUpcomingRuntimeReconciliationError("runtime page metadata differs from exact source replay")
        total_successful_pages += len(observations)
        if (
            attempt_doc.get("successful_page_response_count") != len(observations)
            or attempt_doc.get("observed_totalNum_sequence") != [item["totalNum"] for item in observations]
            or attempt_doc.get("raw_page_sha256s") != [item["raw_sha256"] for item in observations]
            or attempt_doc.get("stable_totalNum") is not (len({item["totalNum"] for item in observations}) <= 1)
            or attempt_doc.get("manifest_emitted") is not (attempt_root / "manifest.json").is_file()
        ):
            raise PcUpcomingRuntimeReconciliationError("runtime attempt summary differs from retained evidence")
        if attempt_doc.get("accepted_by_runtime") is True:
            if (
                attempt_doc.get("status") != "ACCEPTED"
                or attempt_doc.get("failure_class") is not None
                or attempt_doc.get("failure_message") is not None
                or attempt_doc.get("manifest_emitted") is not True
                or attempt_doc.get("stable_totalNum") is not True
            ):
                raise PcUpcomingRuntimeReconciliationError("accepted attempt receipt contains failure semantics")
        elif attempt_doc.get("failure_message") == TOTALNUM_DRIFT_ERROR:
            if (
                attempt_doc.get("status") != "FAILED_EXACT_TOTALNUM_DRIFT"
                or attempt_doc.get("failure_class") != "EXACT_CROSS_PAGE_TOTALNUM_DRIFT"
                or attempt_doc.get("stable_totalNum") is not False
            ):
                raise PcUpcomingRuntimeReconciliationError("exact drift failure classification is inconsistent")
        elif attempt_doc.get("status") == "FAILED_RUNTIME_INCOMPLETE":
            if (
                attempt_doc.get("failure_class") != "RUNTIME_COMPLETENESS_CHECK"
                or not str(attempt_doc.get("failure_message", "")).startswith(INCOMPLETE_PAGINATION_STATE)
            ):
                raise PcUpcomingRuntimeReconciliationError("runtime incompleteness failure classification is inconsistent")
        elif attempt_doc.get("status") == "FAILED_SOURCE_OR_EVIDENCE_ERROR":
            if type(attempt_doc.get("failure_class")) is not str or type(attempt_doc.get("failure_message")) is not str:
                raise PcUpcomingRuntimeReconciliationError("source/evidence failure receipt is incomplete")
        else:
            raise PcUpcomingRuntimeReconciliationError("attempt receipt has an unreviewed status")
        if attempt_doc.get("manifest_emitted") is True:
            try:
                attempt_manifest = source._verify_manifest_at_root(evidence_root=attempt_root)
            except source.PcUpcomingDiscoveryError as exc:
                raise PcUpcomingRuntimeReconciliationError("attempt V1 manifest failed exact raw replay") from exc
            if attempt_manifest.canonical_sha256 != attempt_doc.get("manifest_canonical_sha256"):
                raise PcUpcomingRuntimeReconciliationError("attempt manifest canonical SHA differs from attempt receipt")
        elif attempt_doc.get("manifest_canonical_sha256") is not None:
            raise PcUpcomingRuntimeReconciliationError("attempt receipt claims an absent manifest hash")
        attempt_documents[expected_index] = attempt_doc
    if total_successful_pages > MAX_SUCCESSFUL_PAGE_RESPONSES:
        raise PcUpcomingRuntimeReconciliationError("runtime successful page responses exceed the pinned request bound")
    accepted_index = receipt.get("accepted_attempt_index")
    if accepted_index is None:
        if (root / "manifest.json").exists() or (root / "pages").exists():
            raise PcUpcomingRuntimeReconciliationError("failed capture published a top-level provider manifest/pages")
        if receipt.get("final_state") == "IN_PROGRESS":
            raise PcUpcomingRuntimeReconciliationError("runtime stabilization receipt is not terminal")
        if any(item.get("accepted_by_runtime") is not False for item in attempt_documents.values()):
            raise PcUpcomingRuntimeReconciliationError("failed capture attempt unexpectedly has runtime authority")
        if receipt.get("final_state") == "FAILED_AFTER_EXACT_TOTALNUM_DRIFT":
            if (
                count != 2
                or attempt_documents[1].get("failure_message") != TOTALNUM_DRIFT_ERROR
                or attempt_documents[2].get("failure_message") != TOTALNUM_DRIFT_ERROR
                or attempt_documents[1].get("status") != "FAILED_EXACT_TOTALNUM_DRIFT"
                or attempt_documents[2].get("status") != "FAILED_EXACT_TOTALNUM_DRIFT"
            ):
                raise PcUpcomingRuntimeReconciliationError("two-epoch drift exhaustion does not match exact trigger semantics")
        else:
            if receipt.get("final_state") not in {"FAILED_RUNTIME_INCOMPLETE", "FAILED_SOURCE_OR_EVIDENCE_ERROR"}:
                raise PcUpcomingRuntimeReconciliationError("failed capture final state is not a reviewed terminal state")
            if count == 2 and attempt_documents[1].get("failure_message") != TOTALNUM_DRIFT_ERROR:
                raise PcUpcomingRuntimeReconciliationError("a second epoch exists without exact first-epoch total drift")
            if any(item.get("failure_message") == TOTALNUM_DRIFT_ERROR for index, item in attempt_documents.items() if index > 1):
                raise PcUpcomingRuntimeReconciliationError("second epoch drift was not classified as exhausted exact drift")
        if receipt.get("failed_attempt_indices") != list(range(1, count + 1)):
            raise PcUpcomingRuntimeReconciliationError("failed terminal state does not identify every failed epoch")
    else:
        if type(accepted_index) is not int or accepted_index != count or not 1 <= accepted_index <= MAX_CAPTURE_EPOCHS:
            raise PcUpcomingRuntimeReconciliationError("accepted epoch index is outside the attempt sequence")
        if any(attempt_documents[index].get("accepted_by_runtime") for index in attempt_documents if index != accepted_index):
            raise PcUpcomingRuntimeReconciliationError("more than one capture epoch has runtime authority")
        accepted_receipt = attempt_documents[accepted_index]
        if accepted_receipt.get("accepted_by_runtime") is not True or accepted_receipt.get("status") != "ACCEPTED":
            raise PcUpcomingRuntimeReconciliationError("accepted epoch receipt does not grant the exact runtime acceptance")
        if receipt.get("final_state") != f"ACCEPTED_ATTEMPT_{accepted_index}":
            raise PcUpcomingRuntimeReconciliationError("accepted epoch final state is not exact")
        if receipt.get("failed_attempt_indices") != list(range(1, accepted_index)):
            raise PcUpcomingRuntimeReconciliationError("accepted epoch failed-attempt ancestry is not exact")
        if any(
            attempt_documents[index].get("accepted_by_runtime") is not False
            for index in range(1, accepted_index)
        ):
            raise PcUpcomingRuntimeReconciliationError("failed earlier epoch has runtime authority")
        try:
            manifest = verify_current_pc_upcoming_discovery(repository_root=repository)
        except PcUpcomingRuntimeReconciliationError:
            raise
        _require_complete(manifest)
        accepted_manifest = source._verify_manifest_at_root(
            evidence_root=attempts_root / f"attempt-{accepted_index:03d}"
        )
        accepted_manifest_bytes = (
            attempts_root / f"attempt-{accepted_index:03d}" / "manifest.json"
        ).read_bytes()
        canonical_manifest_bytes = (root / "manifest.json").read_bytes()
        if manifest.to_dict() != accepted_manifest.to_dict():
            raise PcUpcomingRuntimeReconciliationError("top-level provider manifest is not the accepted epoch")
        if canonical_manifest_bytes != accepted_manifest_bytes:
            raise PcUpcomingRuntimeReconciliationError("top-level manifest bytes differ from the exact accepted epoch bytes")
        if accepted_index == 2 and attempt_documents[1].get("failure_message") != TOTALNUM_DRIFT_ERROR:
            raise PcUpcomingRuntimeReconciliationError("epoch 2 lacks exact epoch-1 drift trigger ancestry")
        if accepted_index == 2 and attempt_documents[1].get("status") != "FAILED_EXACT_TOTALNUM_DRIFT":
            raise PcUpcomingRuntimeReconciliationError("epoch 2 prior attempt did not fail the exact reviewed drift state")
        for page in manifest.pages:
            canonical_raw = (root / page.raw_relative_path).read_bytes()
            accepted_raw = (attempts_root / f"attempt-{accepted_index:03d}" / page.raw_relative_path).read_bytes()
            if canonical_raw != accepted_raw or hashlib.sha256(canonical_raw).hexdigest() != page.raw_sha256:
                raise PcUpcomingRuntimeReconciliationError("promoted page bytes differ from the accepted epoch")
    expected_failed = [
        index for index, item in attempt_documents.items()
        if item.get("accepted_by_runtime") is not True
    ]
    if receipt.get("failed_attempt_indices") != expected_failed:
        raise PcUpcomingRuntimeReconciliationError("failed-attempt index list differs from attempt receipts")
    return MappingProxyType(receipt)


def capture_current_pc_upcoming_discovery(
    *, repository_root: str | Path, execute_live_network: bool
) -> tuple[Path, source.PcUpcomingDiscoveryManifest]:
    """Orchestrate at most two independent V1 epochs; accept only one complete epoch."""
    validate_contract()
    if execute_live_network is not True:
        raise PcUpcomingRuntimeReconciliationError(
            "live runtime capture requires exact execute_live_network=True"
        )
    repository = Path(repository_root).resolve(strict=True)
    root = repository / EVIDENCE_ROOT
    if root.exists():
        raise PcUpcomingRuntimeReconciliationError(
            "refusing to overwrite an existing pcUpcoming runtime evidence root"
        )
    try:
        (root / RUNTIME_ATTEMPTS_DIRECTORY).mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise PcUpcomingRuntimeReconciliationError(
            "could not create pcUpcoming runtime evidence root"
        ) from exc

    state = _stabilization_base()
    _persist_stabilization(root, state)
    attempt_receipts: dict[int, dict[str, Any]] = {}
    for attempt_index in range(1, MAX_CAPTURE_EPOCHS + 1):
        attempt_root = root / RUNTIME_ATTEMPTS_DIRECTORY / f"attempt-{attempt_index:03d}"
        observations: list[dict[str, Any]] = []

        def observe_page(page: source.PcUpcomingPageEvidence) -> None:
            observation = _page_observation(page, attempt_index)
            observations.append(observation)
            _write_page_observations(attempt_root, attempt_index, observations)

        manifest: source.PcUpcomingDiscoveryManifest | None = None
        try:
            manifest = source._capture_current_pc_upcoming_discovery_once(
                evidence_root=attempt_root,
                execute_live_network=True,
                page_observer=observe_page,
            )
            verified = source._verify_manifest_at_root(evidence_root=attempt_root)
            if verified.to_dict() != manifest.to_dict():
                raise PcUpcomingRuntimeReconciliationError(
                    "captured source manifest differs from exact attempt replay"
                )
            _require_complete(verified)
            _promote_accepted_epoch(
                repository_root=repository,
                attempt_root=attempt_root,
                manifest=verified,
            )
            receipt = _attempt_receipt(
                attempt_index=attempt_index,
                attempt_root=attempt_root,
                status="ACCEPTED",
                failure_class=None,
                failure_message=None,
                observations=observations,
                accepted=True,
            )
            attempt_receipts[attempt_index] = receipt
            state["accepted_attempt_index"] = attempt_index
            _record_attempt(
                root,
                state,
                receipt,
                failed=False,
                final_state=f"ACCEPTED_ATTEMPT_{attempt_index}",
            )
            promoted = verify_current_pc_upcoming_discovery(repository_root=repository)
            return root, promoted
        except Exception as exc:
            exact_drift = (
                isinstance(exc, source.PcUpcomingDiscoveryError)
                and str(exc) == TOTALNUM_DRIFT_ERROR
            )
            incomplete = isinstance(exc, PcUpcomingRuntimeReconciliationError) and (
                str(exc) == INCOMPLETE_PAGINATION_STATE
                or str(exc).startswith(INCOMPLETE_PAGINATION_STATE + ":")
            )
            if exact_drift:
                status = "FAILED_EXACT_TOTALNUM_DRIFT"
                failure_class = "EXACT_CROSS_PAGE_TOTALNUM_DRIFT"
            elif incomplete:
                status = "FAILED_RUNTIME_INCOMPLETE"
                failure_class = "RUNTIME_COMPLETENESS_CHECK"
            else:
                status = "FAILED_SOURCE_OR_EVIDENCE_ERROR"
                failure_class = type(exc).__name__
            failure_message = str(exc)
            # If promotion succeeded but the receipt write failed, retain the
            # attempt bytes and do not leave a canonical manifest authoritative.
            # _promote_accepted_epoch itself rolls incomplete promotions back.
            receipt = _attempt_receipt(
                attempt_index=attempt_index,
                attempt_root=attempt_root,
                status=status,
                failure_class=failure_class,
                failure_message=failure_message,
                observations=observations,
                accepted=False,
            )
            attempt_receipts[attempt_index] = receipt
            should_start_fresh_epoch = exact_drift and attempt_index == 1
            final_state = (
                "WAITING_FOR_ONE_FRESH_EPOCH_AFTER_EXACT_TOTALNUM_DRIFT"
                if should_start_fresh_epoch
                else "FAILED_AFTER_EXACT_TOTALNUM_DRIFT"
                if exact_drift
                else "FAILED_RUNTIME_INCOMPLETE"
                if incomplete
                else "FAILED_SOURCE_OR_EVIDENCE_ERROR"
            )
            _record_attempt(
                root,
                state,
                receipt,
                failed=True,
                final_state=final_state,
            )
            if should_start_fresh_epoch:
                continue
            if exact_drift and attempt_index == MAX_CAPTURE_EPOCHS:
                raise PcUpcomingRuntimeReconciliationError(
                    f"{INCOMPLETE_PAGINATION_STATE}: both allowed capture epochs failed to produce one internally stable complete V1 manifest; epoch 1 and epoch 2 each ended with exact cross-page totalNum drift"
                ) from exc
            if incomplete:
                raise PcUpcomingRuntimeReconciliationError(
                    f"{INCOMPLETE_PAGINATION_STATE}: one internally stable V1 epoch did not satisfy runtime completeness"
                ) from exc
            if isinstance(exc, source.PcUpcomingDiscoveryError):
                raise PcUpcomingRuntimeReconciliationError(
                    f"PC_UPCOMING_RUNTIME_SOURCE_INCOMPLETE:{type(exc).__name__}:{failure_message}"
                ) from exc
            if isinstance(exc, PcUpcomingRuntimeReconciliationError):
                raise
            raise PcUpcomingRuntimeReconciliationError(
                f"PC_UPCOMING_RUNTIME_CAPTURE_FAILED:{type(exc).__name__}:{failure_message}"
            ) from exc
    raise PcUpcomingRuntimeReconciliationError(
        "PC_UPCOMING_RUNTIME_PAGINATION_INCOMPLETE: bounded epoch loop ended without an accepted manifest"
    )


def capture_current_upcoming_discovery(
    *, repository_root: str | Path, execute_live_network: bool
) -> tuple[Path, source.PcUpcomingDiscoveryManifest]:
    """Runner-compatible module seam; source remains the reviewed pcUpcoming owner."""
    return capture_current_pc_upcoming_discovery(
        repository_root=repository_root, execute_live_network=execute_live_network
    )


def verify_current_pc_upcoming_discovery(
    *, repository_root: str | Path, manifest: Mapping[str, Any] | None = None
) -> source.PcUpcomingDiscoveryManifest:
    validate_contract()
    rebuilt = source.verify_current_pc_upcoming_discovery(
        repository_root=repository_root, manifest=manifest
    )
    _require_complete(rebuilt)
    return rebuilt


def prospective_discovery_assessment(
    manifest: source.PcUpcomingDiscoveryManifest, *, evaluation_time: datetime
) -> Mapping[str, Any]:
    _require_complete(manifest)
    evaluation = evaluation_time.astimezone(timezone.utc)
    events = manifest.events
    prematch = sum(item.prematch_bookable_observed is True for item in events)
    inplay = sum(item.event_status in (1, "1") for item in events)
    future = sum(item.prematch_bookable_observed is True and
                 (item.kickoff_utc - evaluation).total_seconds() > MINIMUM_LEAD_SECONDS
                 for item in events)
    too_close = sum((item.kickoff_utc - evaluation).total_seconds() <= MINIMUM_LEAD_SECONDS
                    for item in events)
    verdict = PROSPECTIVE_DISCOVERY_ELIGIBLE if future else PROSPECTIVE_DISCOVERY_NO_PREMATCH_EVENTS
    return MappingProxyType({
        "provider_event_count": manifest.captured_event_count,
        "provider_total_num": manifest.provider_total_num,
        "provider_prematch_bookable_count": prematch,
        "provider_inplay_count": inplay,
        "provider_future_lead_eligible_count": future,
        "provider_too_close_count": too_close,
        "provider_discovery_source_method": DISCOVERY_SOURCE_METHOD,
        "provider_discovery_strategy_id": STRATEGY_ID,
        "provider_discovery_observed_at": manifest.last_observed_at.isoformat().replace("+00:00", "Z"),
        "provider_discovery_first_observed_at": manifest.first_observed_at.isoformat().replace("+00:00", "Z"),
        "provider_discovery_last_observed_at": manifest.last_observed_at.isoformat().replace("+00:00", "Z"),
        "provider_discovery_pagination_complete": True,
        "source_viability": verdict,
        "captured_page_count": manifest.captured_page_count,
    })


@dataclass(frozen=True, init=False)
class CurrentShadowPcUpcomingReconciliationBundle:
    _legacy_bundle: Any
    manifest: source.PcUpcomingDiscoveryManifest
    repository_root: Path
    stabilization_sha256: str

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise PcUpcomingRuntimeReconciliationError("runtime reconciliation bundles are builder-only")

    @property
    def rows(self):
        return self._legacy_bundle.rows

    @property
    def matched_rows(self):
        return self._legacy_bundle.matched_rows

    @property
    def contract_sha256(self) -> str:
        return PINNED_POLICY_SHA256

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "dataset_name": "athena-current-shadow-pc-upcoming-runtime-reconciliation-v1",
            "status": STATUS,
            "runtime_policy_id": POLICY_ID,
            "runtime_policy_sha256": PINNED_POLICY_SHA256,
            "source_policy_id": UPSTREAM_SOURCE_POLICY_ID,
            "source_policy_sha256": UPSTREAM_SOURCE_POLICY_SHA256,
            "manifest_sha256": self.manifest.canonical_sha256,
            "runtime_stabilization_receipt_sha256": self.stabilization_sha256,
            "provider_total_num": self.manifest.provider_total_num,
            "captured_event_count": self.manifest.captured_event_count,
            "captured_page_count": self.manifest.captured_page_count,
            "pagination_complete": self.manifest.pagination_complete,
            "provider_page_raw_sha256s": [page.raw_sha256 for page in self.manifest.pages],
            "fotmob_admission_sha256": self._legacy_bundle.source_fotmob_admission_sha256,
            "fotmob_capture_identities": [
                dict(item) for item in self._legacy_bundle.fotmob_capture_identities
            ],
            "direct_event_evidence_event_ids": [
                event_id for event_id, _path in self._legacy_bundle._detail_directories
            ],
            "identity_state_sha256": getattr(
                self._legacy_bundle, "_fixture_stable_identity_state_sha256", None
            ),
            "identity_state_schema_version": getattr(
                self._legacy_bundle, "_fixture_stable_identity_state_snapshot", {}
            ).get("schema_version"),
            "reconciliation": self._legacy_bundle.to_dict(),
        }

    def __getattr__(self, name: str) -> Any:
        return getattr(self._legacy_bundle, name)


def _provider_events(manifest: source.PcUpcomingDiscoveryManifest) -> tuple[Any, ...]:
    # Keep provider labels byte-faithful here. The pcUpcoming schema permits
    # provider-observed trailing whitespace; only an explicit existing team
    # alias may project it. Construct the shared attribute interface without
    # invoking the legacy one-page model's stricter label constructor.
    return tuple(SimpleNamespace(
        event_id=event.event_id,
        home_team_id=event.home_team_id,
        home_team_name=event.home_team_name,
        away_team_id=event.away_team_id,
        away_team_name=event.away_team_name,
        category_id=event.category_id,
        category_name=event.category_name,
        tournament_id=event.tournament_id,
        tournament_name=event.tournament_name,
        competition_name=event.tournament_name,
        competition_basis="EXACT_NATIVE_CATEGORY_TOURNAMENT_ANCESTRY",
        kickoff_utc=event.kickoff_utc,
        booking_status=event.booking_status,
        event_status=event.event_status,
        match_status=event.match_status,
        prematch_bookable_observed=event.prematch_bookable_observed,
        source_page_num=event.source_page_num,
        source_raw_sha256=event.source_raw_sha256,
        source_observed_at=event.source_observed_at,
    ) for event in manifest.events)


def _identity_scope(
    captures: Sequence[Any], raw_pages: Sequence[bytes], manifest: source.PcUpcomingDiscoveryManifest
) -> None:
    try:
        identity_compatibility.begin_identity_scope(
            captures,
            provider_raw_bytes=tuple(raw_pages),
            provider_identity_projection_bytes=(source.provider_identity_projection_bytes(manifest),),
        )
    except Exception as exc:
        raise PcUpcomingRuntimeReconciliationError("raw pages and ancestry-bound provider projection failed identity observation") from exc


def _read_pages(repository_root: Path, manifest: source.PcUpcomingDiscoveryManifest) -> tuple[bytes, ...]:
    root = repository_root / EVIDENCE_ROOT
    rows: list[bytes] = []
    for page in manifest.pages:
        relative = f"pages/page-{page.page_num:03d}.raw.json"
        raw = (root / relative).read_bytes()
        if hashlib.sha256(raw).hexdigest() != page.raw_sha256:
            raise PcUpcomingRuntimeReconciliationError("provider raw page changed after manifest verification")
        rows.append(raw)
    return tuple(rows)


def _provisional_details(repository: Path, manifest: source.PcUpcomingDiscoveryManifest,
                         admission: Any, *, execute_live_network: bool,
                         retained_details: Mapping[str, Path] | None = None) -> dict[str, Path]:
    reviewed_rows = reviewed._reviewed_rows(admission)
    events = tuple(legacy._project_event_labels(item) for item in _provider_events(manifest))
    provisional: dict[str, tuple[str, tuple[Any, ...]]] = {}
    for event in events:
        if not event.prematch_bookable_observed or event.competition_name is None:
            provisional[event.event_id] = ("NO_MATCH", ())
            continue
        matches = legacy._match_current_shadow_event(event, reviewed_rows)
        provisional[event.event_id] = ("UNIQUE" if len(matches) == 1 else "AMBIGUOUS" if matches else "NO_MATCH", matches)
    targets = Counter(matches[0].source_fixture_identifier for state, matches in provisional.values() if state == "UNIQUE")
    expected = {event_id for event_id, (state, matches) in provisional.items()
                if state == "UNIQUE" and targets[matches[0].source_fixture_identifier] == 1}
    if retained_details is not None:
        if set(retained_details) != expected:
            raise PcUpcomingRuntimeReconciliationError("retained direct detail set differs from exact provider candidates")
        return {key: Path(value) for key, value in retained_details.items()}
    details: dict[str, Path] = {}
    for event_id in sorted(expected):
        if execute_live_network is True:
            directory, _detail_manifest = live.capture_live_event_quote_evidence(
                event_id=event_id, repository_root=repository, execute_live_network=True
            )
            live_inventory = legacy.tolerant_inventory.build_shadow_live_event_quote_inventory(
                directory, repository_root=repository
            )
            if live_inventory.event_id != event_id:
                raise PcUpcomingRuntimeReconciliationError("direct event detail identity changed")
            details[event_id] = directory
        else:
            path = repository / live.ALLOWED_OUTPUT_RELATIVE / event_id.replace(":", "-")
            if not path.is_dir():
                raise PcUpcomingRuntimeReconciliationError(f"direct event-detail evidence missing for {event_id}")
            details[event_id] = path
    return details


def _validate_direct_native_ancestry(
    repository: Path,
    manifest: source.PcUpcomingDiscoveryManifest,
    detail_directories: Mapping[str, Path],
) -> None:
    """If direct detail repeats native category ancestry, require exact agreement."""
    event_by_id = {event.event_id: event for event in manifest.events}
    for event_id, directory in detail_directories.items():
        raw_path = Path(directory) / live.RAW_FILENAME
        try:
            raw = raw_path.read_bytes()
            payload = live.strict_json_loads(raw)
            detail = live._event_object(payload, event_id)
        except Exception as exc:
            raise PcUpcomingRuntimeReconciliationError(
                f"direct event-detail raw replay failed for {event_id}"
            ) from exc
        event = event_by_id.get(event_id)
        if event is None:
            raise PcUpcomingRuntimeReconciliationError("direct event ID is absent from pcUpcoming manifest")
        sport = detail.get("sport") if type(detail) is dict else None
        category = sport.get("category") if type(sport) is dict else None
        tournament = category.get("tournament") if type(category) is dict else None
        observations = (
            (category, "id", event.category_id),
            (category, "name", event.category_name),
            (tournament, "id", event.tournament_id),
            (tournament, "name", event.tournament_name),
        )
        for parent, field, expected in observations:
            if type(parent) is dict and field in parent and parent[field] != expected:
                raise PcUpcomingRuntimeReconciliationError(
                    f"direct event native {field} conflicts with pcUpcoming ancestry for {event_id}"
                )
        for field, expected in (("categoryId", event.category_id), ("tournamentId", event.tournament_id)):
            if field in detail and detail[field] != expected:
                raise PcUpcomingRuntimeReconciliationError(
                    f"direct event native {field} conflicts with pcUpcoming ancestry for {event_id}"
                )


def _build(
    *, repository_root: Path, manifest: source.PcUpcomingDiscoveryManifest,
    admission: Any, captures: tuple[tuple[bytes, FotMobDataMatchesCaptureManifest], ...],
    execute_live_network: bool, retained_details: Mapping[str, Path] | None = None,
    evaluation_time: datetime | None = None,
) -> CurrentShadowPcUpcomingReconciliationBundle:
    _require_complete(manifest)
    stabilization = verify_runtime_capture_stabilization(repository_root=repository_root)
    if stabilization.get("accepted_attempt_index") is None:
        raise PcUpcomingRuntimeReconciliationError(
            "runtime stabilization does not identify one accepted complete epoch"
        )
    raw_pages = _read_pages(repository_root, manifest)
    _identity_scope(captures, raw_pages, manifest)
    details = _provisional_details(repository_root, manifest, admission,
                                   execute_live_network=execute_live_network,
                                   retained_details=retained_details)
    _validate_direct_native_ancestry(repository_root, manifest, details)
    # Reuse the already-reviewed reconciliation row builder after adapting only
    # the event interface. Provider-native ancestry was observed above first.
    fake_discovery = SimpleNamespace(
        canonical_sha256=manifest.canonical_sha256,
        events=_provider_events(manifest),
    )
    rebuilt = legacy._build_bundle(
        repository_root=repository_root,
        discovery_directory=repository_root / EVIDENCE_ROOT,
        discovery=fake_discovery,
        admission=admission,
        captures=captures,
        detail_directories=details,
        evaluation_time=reviewed._now_utc() if evaluation_time is None else evaluation_time,
    )
    snapshot = legacy._identity_state_snapshot()
    object.__setattr__(rebuilt, "_fixture_stable_identity_state_sha256", legacy._identity_state_sha256(snapshot))
    object.__setattr__(rebuilt, "_fixture_stable_identity_state_snapshot", snapshot)
    object.__setattr__(rebuilt, "contract_sha256", PINNED_POLICY_SHA256)
    object.__setattr__(rebuilt, "dataset_name", "athena-current-shadow-pc-upcoming-runtime-reconciliation-v1")
    object.__setattr__(rebuilt, "status", STATUS)
    bundle = object.__new__(CurrentShadowPcUpcomingReconciliationBundle)
    object.__setattr__(bundle, "_legacy_bundle", rebuilt)
    object.__setattr__(bundle, "manifest", manifest)
    object.__setattr__(bundle, "repository_root", repository_root)
    object.__setattr__(bundle, "stabilization_sha256", stabilization["canonical_sha256"])
    return bundle


def reconcile_current_events_from_pc_upcoming_discovery(
    *, repository_root: str | Path, discovery_evidence_directory: str | Path,
    fotmob_admission_value: Any, fotmob_captures: Sequence[Any],
    execute_live_network: bool,
) -> CurrentShadowPcUpcomingReconciliationBundle:
    validate_contract()
    repository = Path(repository_root).resolve(strict=True)
    expected_dir = repository / EVIDENCE_ROOT
    if Path(discovery_evidence_directory).resolve(strict=True) != expected_dir.resolve(strict=True):
        raise PcUpcomingRuntimeReconciliationError("runtime discovery directory is not the reviewed pcUpcoming evidence root")
    manifest = verify_current_pc_upcoming_discovery(repository_root=repository)
    try:
        captures = reviewed._materialize_fotmob_captures(fotmob_captures)
        admission = reviewed._rederive_exact_fotmob_admission(fotmob_admission_value, captures)
    except reviewed.SportyBetCurrentEventDiscoveryError as exc:
        raise PcUpcomingRuntimeReconciliationError(str(exc)) from exc
    return _build(repository_root=repository, manifest=manifest, admission=admission,
                  captures=captures, execute_live_network=execute_live_network)


def reconcile_current_events_from_upcoming_discovery(**kwargs: Any) -> CurrentShadowPcUpcomingReconciliationBundle:
    """Runner-compatible alias retained while the active owner changes."""
    return reconcile_current_events_from_pc_upcoming_discovery(**kwargs)


def discover_and_reconcile_current_events(
    *, repository_root: str | Path, fotmob_admission_value: Any,
    fotmob_captures: Sequence[Any], execute_live_network: bool,
) -> CurrentShadowPcUpcomingReconciliationBundle:
    if execute_live_network is not True:
        raise PcUpcomingRuntimeReconciliationError("live runtime capture requires exact execute_live_network=True")
    directory, _manifest = capture_current_pc_upcoming_discovery(
        repository_root=repository_root, execute_live_network=True
    )
    return reconcile_current_events_from_pc_upcoming_discovery(
        repository_root=repository_root, discovery_evidence_directory=directory,
        fotmob_admission_value=fotmob_admission_value, fotmob_captures=fotmob_captures,
        execute_live_network=True,
    )


def verify_current_pc_upcoming_reconciliation_bundle(
    value: CurrentShadowPcUpcomingReconciliationBundle,
) -> CurrentShadowPcUpcomingReconciliationBundle:
    if type(value) is not CurrentShadowPcUpcomingReconciliationBundle:
        raise PcUpcomingRuntimeReconciliationError("value must be exact pcUpcoming runtime bundle")
    validate_contract()
    retained_state = getattr(value._legacy_bundle, "_fixture_stable_identity_state_snapshot", None)
    retained_sha = getattr(value._legacy_bundle, "_fixture_stable_identity_state_sha256", None)
    if type(retained_state) is not dict or legacy._identity_state_sha256(retained_state) != retained_sha:
        raise PcUpcomingRuntimeReconciliationError("identity-state replay ancestry is missing or changed")
    manifest = verify_current_pc_upcoming_discovery(repository_root=value.repository_root,
                                                    manifest=value.manifest.to_dict())
    details = dict(value._legacy_bundle._detail_directories)
    captures = reviewed._materialize_fotmob_captures(value._legacy_bundle._fotmob_captures)
    admission = reviewed._rederive_exact_fotmob_admission(value._legacy_bundle._fotmob_admission, captures)
    rebuilt = _build(repository_root=value.repository_root, manifest=manifest,
                     admission=admission, captures=captures,
                     execute_live_network=False, retained_details=details,
                     evaluation_time=value._legacy_bundle.evaluation_time)
    if _canonical(value.to_dict()) != _canonical(rebuilt.to_dict()):
        raise PcUpcomingRuntimeReconciliationError("pcUpcoming reconciliation differs from exact offline replay")
    legacy._verify_identity_state_append_only_extension(retained_state, legacy._identity_state_snapshot())
    object.__setattr__(rebuilt._legacy_bundle, "_fixture_stable_identity_state_sha256", retained_sha)
    object.__setattr__(rebuilt._legacy_bundle, "_fixture_stable_identity_state_snapshot", retained_state)
    return rebuilt


def verify_current_event_discovery_reconciliation_bundle(value: CurrentShadowPcUpcomingReconciliationBundle):
    return verify_current_pc_upcoming_reconciliation_bundle(value)


__all__ = [
    "AUTHORITY", "CurrentShadowPcUpcomingReconciliationBundle", "DISCOVERY_SOURCE_METHOD",
    "CURRENT_SHADOW_UPCOMING_COMPATIBILITY_SHA256", "CURRENT_SHADOW_UPCOMING_POLICY_ID",
    "ALLOWED_OUTPUT_RELATIVE", "EVIDENCE_ROOT", "EXPECTED_CONTRACT_SHA256", "INCOMPLETE_PAGINATION_STATE",
    "MAX_PAGES", "MINIMUM_LEAD_SECONDS", "PcUpcomingDiscoveryManifest",
    "PINNED_POLICY_SHA256", "POLICY_ID", "PROSPECTIVE_DISCOVERY_ELIGIBLE",
    "PROSPECTIVE_DISCOVERY_NO_PREMATCH_EVENTS", "STATUS", "STRATEGY_ID", "UPCOMING_PATH",
    "PcUpcomingRuntimeReconciliationError", "calculate_policy_sha256", "capture_current_pc_upcoming_discovery",
    "capture_current_upcoming_discovery", "discover_and_reconcile_current_events", "prospective_discovery_assessment",
    "reconcile_current_events_from_pc_upcoming_discovery", "reconcile_current_events_from_upcoming_discovery",
    "SportyBetCurrentEventDiscoveryError", "validate_contract", "verify_current_event_discovery_reconciliation_bundle",
    "verify_current_pc_upcoming_discovery", "verify_current_pc_upcoming_reconciliation_bundle",
    "verify_runtime_capture_stabilization",
]
