"""Derive provider-native SportyBet selections from verified user evidence.

This boundary is deliberately offline. It consumes only a PR #153 verified
USER_CONTROLLED_BROWSER_EXPORT evidence directory, preserves PR #152 native
selection identities/odds, and keeps provider quote/fresh-price authority false.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
import re
import types
from typing import Any, Mapping

from domain import sportybet_user_controlled_evidence as manual
from domain.sportybet_lite_source_capture import (
    MAX_RESPONSE_BYTES,
    SportyBetLiteCaptureError,
    SportyBetLiteRequestKind,
    _ensure_directory_tree_durable,
    _read_regular,
    _reject_symlink_components,
    _sync_directory,
    parse_utc_timestamp,
    serialize_utc,
    sha256_bytes,
)
from domain.sportybet_provider_native_inventory import (
    NativeEvent,
    NativeSelection,
    SportyBetProviderInventoryError,
    extract_native_selections,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-sportybet-user-controlled-provider-native-inventory-v1"
PROVIDER = "SportyBet"
INVENTORY_FILENAME = "inventory.json"
ALLOWED_OUTPUT_RELATIVE = Path(
    ".cache/athena-research/sportybet-user-controlled-native-inventory"
)
MAX_INVENTORY_BYTES = 64 * 1024 * 1024
PROVIDER_QUOTE_TIMESTAMP_CAPABILITY = "UNPROVEN_ON_REVIEWED_LITE_HTML"
PROVIDER_SNAPSHOT_ID_CAPABILITY = "UNPROVEN_ON_REVIEWED_LITE_HTML"
_EVIDENCE_ID_RE = re.compile(r"^[0-9a-f]{24}$", flags=re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "bet_authorized",
        "bookmaker_equivalence_authorized",
        "canonical_market_mapping_authorized",
        "fixture_reconciliation_authorized",
        "fresh_price_authorized",
        "model_integration_authorized",
        "network_acquisition_authorized",
        "pricing_authorized",
        "selection_authorized",
        "slip_construction_authorized",
        "sportybet_execution_authorized",
    }
)


class SportyBetUserInventoryError(ValueError):
    """Raised when derived user-controlled SportyBet inventory fails closed."""


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise SportyBetUserInventoryError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise SportyBetUserInventoryError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(detached)


def _canonical_utc(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise SportyBetUserInventoryError(f"{label} must be a string")
    try:
        parsed = parse_utc_timestamp(value, label)
    except SportyBetLiteCaptureError as exc:
        raise SportyBetUserInventoryError(str(exc)) from exc
    if serialize_utc(parsed) != value:
        raise SportyBetUserInventoryError(f"{label} must use canonical UTC serialization")
    return value


def _validate_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise SportyBetUserInventoryError(f"{label} is invalid")
    return value


def _group_events(selections: tuple[NativeSelection, ...]) -> tuple[NativeEvent, ...]:
    grouped: dict[str, list[NativeSelection]] = {}
    for item in selections:
        grouped.setdefault(item.event_id, []).append(item)
    events: list[NativeEvent] = []
    for event_id, items in grouped.items():
        sport_ids = {item.sport_id for item in items if item.sport_id is not None}
        product_ids = {item.product_id for item in items if item.product_id is not None}
        if len(sport_ids) > 1 or len(product_ids) > 1:
            raise SportyBetUserInventoryError(
                "conflicting provider sport/product identity within one event"
            )
        try:
            event = NativeEvent(
                event_id=event_id,
                sport_id=next(iter(sport_ids)) if sport_ids else None,
                product_id=next(iter(product_ids)) if product_ids else None,
                competition_id=None,
                competition_name=None,
                home_participant_id=None,
                home_participant_name=None,
                away_participant_id=None,
                away_participant_name=None,
                kickoff=None,
                event_status=None,
                selection_count=len(items),
            )
        except SportyBetProviderInventoryError as exc:
            raise SportyBetUserInventoryError(str(exc)) from exc
        events.append(event)
    return tuple(sorted(events, key=lambda item: item.event_id))


def _validate_detail_population(
    manifest: manual.SportyBetUserControlledEvidenceManifest,
    selections: tuple[NativeSelection, ...],
) -> None:
    if manifest.request_kind is not SportyBetLiteRequestKind.EVENT_DETAIL:
        return
    if manifest.event_id is None or manifest.sport_id is None:
        raise SportyBetUserInventoryError("event-detail evidence identity is incomplete")
    event_ids = {item.event_id for item in selections}
    if event_ids != {manifest.event_id}:
        raise SportyBetUserInventoryError(
            "event-detail HTML selection population does not match source eventId"
        )
    for item in selections:
        if item.sport_id is not None and item.sport_id != manifest.sport_id:
            raise SportyBetUserInventoryError(
                "event-detail selection sportId does not match source sportId"
            )
        if (
            item.market_group is not None
            and item.market_group != manifest.market_groups_name
        ):
            raise SportyBetUserInventoryError(
                "event-detail selection market group does not match source request"
            )


@dataclasses.dataclass(frozen=True)
class SportyBetUserControlledNativeInventory:
    schema_version: int
    dataset_name: str
    provider: str
    source_evidence_id: str
    source_evidence_manifest_sha256: str
    source_raw_sha256: str
    source_url: str
    source_request_kind: SportyBetLiteRequestKind
    source_request_target: str
    source_event_id: str | None
    source_sport_id: str | None
    source_market_groups_name: str | None
    acquisition_mode: str
    observation_authority: str
    observed_at_user_attested: str
    imported_at_utc: str
    athena_network_acquisition_performed: bool
    provider_quote_at: None
    provider_snapshot_id: None
    provider_quote_timestamp_capability: str
    provider_snapshot_id_capability: str
    events: tuple[NativeEvent, ...]
    selections: tuple[NativeSelection, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise SportyBetUserInventoryError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME or self.provider != PROVIDER:
            raise SportyBetUserInventoryError("dataset/provider mismatch")
        if (
            not isinstance(self.source_evidence_id, str)
            or _EVIDENCE_ID_RE.fullmatch(self.source_evidence_id) is None
        ):
            raise SportyBetUserInventoryError("source_evidence_id is invalid")
        _validate_hash(
            self.source_evidence_manifest_sha256,
            "source_evidence_manifest_sha256",
        )
        _validate_hash(self.source_raw_sha256, "source_raw_sha256")
        if not isinstance(self.source_url, str) or not self.source_url:
            raise SportyBetUserInventoryError("source_url is invalid")
        try:
            kind, event_id, sport_id, market_group, target = manual.validate_source_url(
                self.source_url
            )
        except manual.SportyBetUserEvidenceError as exc:
            raise SportyBetUserInventoryError(str(exc)) from exc
        if self.source_request_kind is not kind or self.source_request_target != target:
            raise SportyBetUserInventoryError("source request identity mismatch")
        if (self.source_event_id, self.source_sport_id, self.source_market_groups_name) != (
            event_id,
            sport_id,
            market_group,
        ):
            raise SportyBetUserInventoryError("source provider request fields mismatch")
        if self.acquisition_mode != manual.ACQUISITION_MODE:
            raise SportyBetUserInventoryError("acquisition_mode mismatch")
        if self.observation_authority != manual.OBSERVATION_AUTHORITY:
            raise SportyBetUserInventoryError("observation_authority mismatch")
        _canonical_utc(self.observed_at_user_attested, "observed_at_user_attested")
        _canonical_utc(self.imported_at_utc, "imported_at_utc")
        try:
            observed = parse_utc_timestamp(
                self.observed_at_user_attested, "observed_at_user_attested"
            )
            imported = parse_utc_timestamp(self.imported_at_utc, "imported_at_utc")
        except SportyBetLiteCaptureError as exc:
            raise SportyBetUserInventoryError(str(exc)) from exc
        if imported < observed:
            raise SportyBetUserInventoryError(
                "imported_at_utc must not precede user-attested observation"
            )
        if self.athena_network_acquisition_performed is not False:
            raise SportyBetUserInventoryError("ATHENA network acquisition must remain false")
        if self.provider_quote_at is not None or self.provider_snapshot_id is not None:
            raise SportyBetUserInventoryError(
                "provider quote/snapshot identity is unproven and must remain null"
            )
        if self.provider_quote_timestamp_capability != PROVIDER_QUOTE_TIMESTAMP_CAPABILITY:
            raise SportyBetUserInventoryError("quote timestamp capability mismatch")
        if self.provider_snapshot_id_capability != PROVIDER_SNAPSHOT_ID_CAPABILITY:
            raise SportyBetUserInventoryError("snapshot capability mismatch")
        if type(self.events) is not tuple or type(self.selections) is not tuple:
            raise SportyBetUserInventoryError("events and selections must be tuples")
        if not self.events or not self.selections:
            raise SportyBetUserInventoryError(
                "inventory must contain provider-native selections"
            )
        if any(not isinstance(item, NativeEvent) for item in self.events):
            raise SportyBetUserInventoryError("events contain an invalid item")
        if any(not isinstance(item, NativeSelection) for item in self.selections):
            raise SportyBetUserInventoryError("selections contain an invalid item")
        event_ids = [item.event_id for item in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise SportyBetUserInventoryError("duplicate event identity")
        selection_ids = [item.selection_identity for item in self.selections]
        if len(selection_ids) != len(set(selection_ids)):
            raise SportyBetUserInventoryError("duplicate selection identity")
        expected_events = _group_events(self.selections)
        if tuple(item.to_dict() for item in expected_events) != tuple(
            item.to_dict() for item in self.events
        ):
            raise SportyBetUserInventoryError(
                "event inventory does not match native selection population"
            )
        safety = _validate_safety(self.safety)
        object.__setattr__(self, "safety", safety)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "provider": self.provider,
            "source_evidence_id": self.source_evidence_id,
            "source_evidence_manifest_sha256": self.source_evidence_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "source_url": self.source_url,
            "source_request_kind": self.source_request_kind.value,
            "source_request_target": self.source_request_target,
            "source_event_id": self.source_event_id,
            "source_sport_id": self.source_sport_id,
            "source_market_groups_name": self.source_market_groups_name,
            "acquisition_mode": self.acquisition_mode,
            "observation_authority": self.observation_authority,
            "observed_at_user_attested": self.observed_at_user_attested,
            "imported_at_utc": self.imported_at_utc,
            "athena_network_acquisition_performed": False,
            "provider_quote_at": None,
            "provider_snapshot_id": None,
            "provider_quote_timestamp_capability": self.provider_quote_timestamp_capability,
            "provider_snapshot_id_capability": self.provider_snapshot_id_capability,
            "events": [item.to_dict() for item in self.events],
            "selections": [item.to_dict() for item in self.selections],
            "safety": dict(self.safety),
        }


def _normalize_under_repository(path_value: Any, *, repository: Path, label: str) -> Path:
    try:
        path = Path(path_value)
    except (TypeError, ValueError) as exc:
        raise SportyBetUserInventoryError(f"{label} is invalid") from exc
    if ".." in path.parts:
        raise SportyBetUserInventoryError(f"{label} must not contain traversal")
    return path if path.is_absolute() else repository / path


def _load_verified_source(
    evidence_directory: Any,
    *,
    allowed_root: Path,
) -> tuple[manual.SportyBetUserControlledEvidenceManifest, bytes]:
    try:
        first_manifest = manual.verify_evidence_directory(
            evidence_directory,
            allowed_root=allowed_root,
        )
        raw = _read_regular(
            Path(evidence_directory) / manual.RAW_FILENAME,
            maximum=MAX_RESPONSE_BYTES,
            label="manual raw HTML",
        )
        second_manifest = manual.verify_evidence_directory(
            evidence_directory,
            allowed_root=allowed_root,
        )
    except (manual.SportyBetUserEvidenceError, SportyBetLiteCaptureError) as exc:
        raise SportyBetUserInventoryError(str(exc)) from exc
    if manual.canonical_manifest_bytes(first_manifest) != manual.canonical_manifest_bytes(
        second_manifest
    ):
        raise SportyBetUserInventoryError("source manifest changed during verification")
    if sha256_bytes(raw) != second_manifest.raw_sha256 or len(raw) != second_manifest.raw_size:
        raise SportyBetUserInventoryError("source raw HTML changed during verification")
    return second_manifest, raw


def build_inventory_from_evidence(
    evidence_directory: Any,
    *,
    allowed_root: Path,
) -> SportyBetUserControlledNativeInventory:
    manifest, raw = _load_verified_source(
        evidence_directory,
        allowed_root=allowed_root,
    )
    try:
        selections = extract_native_selections(raw)
    except SportyBetProviderInventoryError as exc:
        raise SportyBetUserInventoryError(str(exc)) from exc
    _validate_detail_population(manifest, selections)
    events = _group_events(selections)
    return SportyBetUserControlledNativeInventory(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        provider=PROVIDER,
        source_evidence_id=manual.evidence_identifier(manifest),
        source_evidence_manifest_sha256=manual.manifest_sha256(manifest),
        source_raw_sha256=manifest.raw_sha256,
        source_url=manifest.source_url,
        source_request_kind=manifest.request_kind,
        source_request_target=manifest.request_target,
        source_event_id=manifest.event_id,
        source_sport_id=manifest.sport_id,
        source_market_groups_name=manifest.market_groups_name,
        acquisition_mode=manifest.acquisition_mode,
        observation_authority=manifest.observation_authority,
        observed_at_user_attested=serialize_utc(manifest.observed_at_user_attested),
        imported_at_utc=serialize_utc(manifest.imported_at_utc),
        athena_network_acquisition_performed=False,
        provider_quote_at=None,
        provider_snapshot_id=None,
        provider_quote_timestamp_capability=PROVIDER_QUOTE_TIMESTAMP_CAPABILITY,
        provider_snapshot_id_capability=PROVIDER_SNAPSHOT_ID_CAPABILITY,
        events=events,
        selections=selections,
        safety=_default_safety(),
    )


def canonical_inventory_bytes(inventory: Any) -> bytes:
    if not isinstance(inventory, SportyBetUserControlledNativeInventory):
        raise SportyBetUserInventoryError(
            "inventory must be SportyBetUserControlledNativeInventory"
        )
    try:
        payload = (
            json.dumps(
                inventory.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportyBetUserInventoryError("inventory serialization failed") from exc
    if len(payload) > MAX_INVENTORY_BYTES:
        raise SportyBetUserInventoryError("canonical inventory exceeds reviewed size limit")
    return payload


def inventory_sha256(inventory: Any) -> str:
    return sha256_bytes(canonical_inventory_bytes(inventory))


def _validate_exact_root(
    supplied_root: Any,
    *,
    repository_root: Path,
    relative: Path,
    label: str,
) -> Path:
    repository = Path(repository_root).resolve(strict=True)
    if not repository.is_dir():
        raise SportyBetUserInventoryError("repository_root must be a directory")
    expected = repository / relative
    try:
        supplied = Path(supplied_root)
    except (TypeError, ValueError) as exc:
        raise SportyBetUserInventoryError(f"{label} is invalid") from exc
    if ".." in supplied.parts:
        raise SportyBetUserInventoryError(f"{label} must not contain traversal")
    supplied_abs = supplied if supplied.is_absolute() else repository / supplied
    try:
        _reject_symlink_components(supplied_abs, label)
    except SportyBetLiteCaptureError as exc:
        raise SportyBetUserInventoryError(str(exc)) from exc
    if supplied_abs.resolve(strict=False) != expected.resolve(strict=False):
        raise SportyBetUserInventoryError(f"{label} must be the reviewed exact root")
    return expected


def _write_exclusive(path: Path, content: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _sync_directory(path.parent)
    except FileExistsError as exc:
        raise SportyBetUserInventoryError(
            f"refusing to overwrite {path.name}"
        ) from exc
    except (OSError, SportyBetLiteCaptureError) as exc:
        raise SportyBetUserInventoryError(
            f"could not durably write {path.name}"
        ) from exc


def store_inventory_from_evidence(
    evidence_directory: Any,
    *,
    repository_root: Path,
    evidence_root: Path = manual.ALLOWED_OUTPUT_RELATIVE,
    output_root: Path = ALLOWED_OUTPUT_RELATIVE,
) -> tuple[Path, SportyBetUserControlledNativeInventory]:
    repository = Path(repository_root).resolve(strict=True)
    reviewed_evidence_root = _validate_exact_root(
        evidence_root,
        repository_root=repository,
        relative=manual.ALLOWED_OUTPUT_RELATIVE,
        label="evidence root",
    )
    reviewed_output_root = _validate_exact_root(
        output_root,
        repository_root=repository,
        relative=ALLOWED_OUTPUT_RELATIVE,
        label="inventory root",
    )
    evidence_path = _normalize_under_repository(
        evidence_directory,
        repository=repository,
        label="evidence directory",
    )
    inventory = build_inventory_from_evidence(
        evidence_path,
        allowed_root=reviewed_evidence_root,
    )
    payload = canonical_inventory_bytes(inventory)
    try:
        _ensure_directory_tree_durable(reviewed_output_root, boundary=repository)
    except SportyBetLiteCaptureError as exc:
        raise SportyBetUserInventoryError(str(exc)) from exc
    directory = reviewed_output_root / inventory.source_evidence_id
    if directory.exists():
        if directory.is_symlink() or not directory.is_dir():
            raise SportyBetUserInventoryError(
                "inventory identity path must be a non-symlink directory"
            )
        try:
            _reject_symlink_components(directory, "inventory directory")
            names = sorted(item.name for item in directory.iterdir())
            existing = _read_regular(
                directory / INVENTORY_FILENAME,
                maximum=MAX_INVENTORY_BYTES,
                label="manual native inventory",
            )
        except (OSError, SportyBetLiteCaptureError) as exc:
            raise SportyBetUserInventoryError(str(exc)) from exc
        if names != [INVENTORY_FILENAME]:
            raise SportyBetUserInventoryError("inventory directory contents mismatch")
        if existing != payload:
            raise SportyBetUserInventoryError("derived inventory identity collision")
        return directory, inventory
    try:
        directory.mkdir(exist_ok=False)
        _sync_directory(reviewed_output_root)
        _sync_directory(directory)
    except (OSError, SportyBetLiteCaptureError) as exc:
        raise SportyBetUserInventoryError("could not create inventory directory") from exc
    _write_exclusive(directory / INVENTORY_FILENAME, payload)
    verified = verify_inventory_directory(
        directory,
        evidence_directory=evidence_path,
        repository_root=repository,
        evidence_root=reviewed_evidence_root,
        output_root=reviewed_output_root,
    )
    return directory, verified


def verify_inventory_directory(
    inventory_directory: Any,
    *,
    evidence_directory: Any,
    repository_root: Path,
    evidence_root: Path = manual.ALLOWED_OUTPUT_RELATIVE,
    output_root: Path = ALLOWED_OUTPUT_RELATIVE,
) -> SportyBetUserControlledNativeInventory:
    repository = Path(repository_root).resolve(strict=True)
    reviewed_evidence_root = _validate_exact_root(
        evidence_root,
        repository_root=repository,
        relative=manual.ALLOWED_OUTPUT_RELATIVE,
        label="evidence root",
    )
    reviewed_output_root = _validate_exact_root(
        output_root,
        repository_root=repository,
        relative=ALLOWED_OUTPUT_RELATIVE,
        label="inventory root",
    )
    evidence_path = _normalize_under_repository(
        evidence_directory,
        repository=repository,
        label="evidence directory",
    )
    directory = _normalize_under_repository(
        inventory_directory,
        repository=repository,
        label="inventory directory",
    )
    try:
        _reject_symlink_components(directory, "inventory directory")
        resolved_root = reviewed_output_root.resolve(strict=True)
        resolved_dir = directory.resolve(strict=True)
        resolved_dir.relative_to(resolved_root)
    except (SportyBetLiteCaptureError, OSError, ValueError) as exc:
        raise SportyBetUserInventoryError(
            "inventory directory escapes or cannot resolve under reviewed root"
        ) from exc
    if directory.is_symlink() or not directory.is_dir():
        raise SportyBetUserInventoryError(
            "inventory directory must be a non-symlink directory"
        )
    try:
        names = sorted(item.name for item in directory.iterdir())
    except OSError as exc:
        raise SportyBetUserInventoryError("inventory directory cannot be read") from exc
    if names != [INVENTORY_FILENAME]:
        raise SportyBetUserInventoryError("inventory directory contents mismatch")
    expected = build_inventory_from_evidence(
        evidence_path,
        allowed_root=reviewed_evidence_root,
    )
    if directory.name != expected.source_evidence_id:
        raise SportyBetUserInventoryError("inventory directory evidence identity mismatch")
    try:
        stored = _read_regular(
            directory / INVENTORY_FILENAME,
            maximum=MAX_INVENTORY_BYTES,
            label="manual native inventory",
        )
    except SportyBetLiteCaptureError as exc:
        raise SportyBetUserInventoryError(str(exc)) from exc
    if stored != canonical_inventory_bytes(expected):
        raise SportyBetUserInventoryError(
            "stored inventory is noncanonical, stale, or does not match source evidence"
        )
    return expected
