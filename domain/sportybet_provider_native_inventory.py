"""Deterministic provider-native inventory for reviewed SportyBet Lite HTML.

The extractor intentionally stops before ATHENA fixture reconciliation and
canonical market mapping.  Provider identifiers and source uncertainty are
preserved exactly; unknown remains unknown.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal, InvalidOperation
import enum
from html.parser import HTMLParser
import json
import re
import types
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlsplit

from domain.sportybet_lite_source_capture import (
    ALLOWED_HOST,
    SportyBetLiteCaptureError,
    SportyBetLiteCaptureManifest,
    validate_event_id,
    validate_sport_id,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-sportybet-provider-native-inventory-v1"
MAX_HTML_BYTES = 8 * 1024 * 1024
MAX_LINKS = 100_000
MAX_TEXT = 512
_SAFE_NATIVE_ID_RE = re.compile(r"^[A-Za-z0-9_.:+/=-]{1,160}$", flags=re.ASCII)
_DECIMAL_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)?$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "bookmaker_equivalence_authorized",
        "canonical_market_mapping_authorized",
        "fixture_reconciliation_authorized",
        "fresh_price_authorized",
        "model_integration_authorized",
        "pricing_authorized",
        "selection_authorized",
        "slip_construction_authorized",
        "sportybet_execution_authorized",
        "bet_authorized",
    }
)


class SportyBetProviderInventoryError(ValueError):
    """Raised when provider-native SportyBet inventory evidence fails closed."""


class NativeAvailability(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise SportyBetProviderInventoryError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise SportyBetProviderInventoryError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(detached)


def _bounded_text(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SportyBetProviderInventoryError(f"{label} must be a string or None")
    normalized = " ".join(value.split())
    if not normalized:
        return None
    if len(normalized) > MAX_TEXT:
        raise SportyBetProviderInventoryError(f"{label} exceeds {MAX_TEXT} characters")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in normalized):
        raise SportyBetProviderInventoryError(f"{label} contains control characters")
    return normalized


def _native_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SAFE_NATIVE_ID_RE.fullmatch(value) is None:
        raise SportyBetProviderInventoryError(f"{label} is not a safe provider-native ID")
    return value


def validate_odds(value: Any) -> tuple[str, str]:
    if not isinstance(value, str) or _DECIMAL_RE.fullmatch(value) is None:
        raise SportyBetProviderInventoryError("odds must be a plain decimal string")
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise SportyBetProviderInventoryError("odds are not a valid decimal") from exc
    if not parsed.is_finite() or parsed <= Decimal("1"):
        raise SportyBetProviderInventoryError("decimal odds must be greater than 1")
    normalized = format(parsed.normalize(), "f")
    return value, normalized


def _query_mapping(href: str) -> tuple[str, dict[str, str]]:
    try:
        parsed = urlsplit(href)
    except ValueError as exc:
        raise SportyBetProviderInventoryError("selection href is invalid") from exc
    if parsed.scheme and parsed.scheme != "https":
        raise SportyBetProviderInventoryError("selection href must use HTTPS")
    if parsed.netloc and parsed.netloc not in {ALLOWED_HOST, "lite.sportybet.com"}:
        raise SportyBetProviderInventoryError("selection href host is not SportyBet")
    if not parsed.path.startswith("/ng/lite"):
        raise SportyBetProviderInventoryError("selection href is outside SportyBet Lite")
    try:
        pairs = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=False,
            encoding="utf-8",
            errors="strict",
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise SportyBetProviderInventoryError("selection query cannot be decoded") from exc
    query: dict[str, str] = {}
    for key, value in pairs:
        if key in query:
            raise SportyBetProviderInventoryError(
                f"duplicate query parameter {key!r} in selection href"
            )
        query[key] = value
    return parsed.path, query


def _explicit_availability(attrs: Mapping[str, str | None]) -> NativeAvailability:
    classes = set((attrs.get("class") or "").lower().split())
    data_status = (attrs.get("data-status") or "").strip().lower()
    aria_disabled = (attrs.get("aria-disabled") or "").strip().lower()
    data_active = (attrs.get("data-active") or "").strip().lower()
    if (
        "disabled" in attrs
        or aria_disabled == "true"
        or data_status in {"suspended", "locked", "inactive", "disabled"}
        or {"locked", "suspended", "disabled"}.intersection(classes)
    ):
        return NativeAvailability.SUSPENDED
    if data_active in {"1", "true"} or data_status in {"active", "available"}:
        return NativeAvailability.AVAILABLE
    return NativeAvailability.UNKNOWN


@dataclasses.dataclass(frozen=True)
class NativeSelection:
    event_id: str
    sport_id: str | None
    product_id: str | None
    market_id: str
    market_group: str | None
    market_name: str | None
    specifier: str | None
    outcome_id: str
    selection_label: str | None
    odds_raw: str
    odds_decimal: str
    availability: NativeAvailability
    provider_quote_at: None
    provider_snapshot_id: None
    href: str

    def __post_init__(self) -> None:
        try:
            event_id = validate_event_id(self.event_id)
        except SportyBetLiteCaptureError as exc:
            raise SportyBetProviderInventoryError(str(exc)) from exc
        sport_id = None
        if self.sport_id is not None:
            try:
                sport_id = validate_sport_id(self.sport_id)
            except SportyBetLiteCaptureError as exc:
                raise SportyBetProviderInventoryError(str(exc)) from exc
        product_id = None if self.product_id is None else _native_id(self.product_id, "product_id")
        market_id = _native_id(self.market_id, "market_id")
        outcome_id = _native_id(self.outcome_id, "outcome_id")
        market_group = _bounded_text(self.market_group, "market_group")
        market_name = _bounded_text(self.market_name, "market_name")
        selection_label = _bounded_text(self.selection_label, "selection_label")
        specifier = _bounded_text(self.specifier, "specifier")
        odds_raw, odds_decimal = validate_odds(self.odds_raw)
        if self.odds_decimal != odds_decimal:
            raise SportyBetProviderInventoryError("odds_decimal does not match odds_raw")
        if not isinstance(self.availability, NativeAvailability):
            raise SportyBetProviderInventoryError("availability is invalid")
        if self.provider_quote_at is not None:
            raise SportyBetProviderInventoryError(
                "provider_quote_at is unproven and must remain None"
            )
        if self.provider_snapshot_id is not None:
            raise SportyBetProviderInventoryError(
                "provider_snapshot_id is unproven and must remain None"
            )
        if not isinstance(self.href, str) or not self.href or len(self.href) > 4096:
            raise SportyBetProviderInventoryError("href is invalid")
        _query_mapping(self.href)
        object.__setattr__(self, "event_id", event_id)
        object.__setattr__(self, "sport_id", sport_id)
        object.__setattr__(self, "product_id", product_id)
        object.__setattr__(self, "market_id", market_id)
        object.__setattr__(self, "outcome_id", outcome_id)
        object.__setattr__(self, "market_group", market_group)
        object.__setattr__(self, "market_name", market_name)
        object.__setattr__(self, "selection_label", selection_label)
        object.__setattr__(self, "specifier", specifier)
        object.__setattr__(self, "odds_raw", odds_raw)
        object.__setattr__(self, "odds_decimal", odds_decimal)

    @property
    def market_identity(self) -> tuple[str, str | None]:
        return (self.market_id, self.specifier)

    @property
    def selection_identity(self) -> tuple[str, str, str | None, str]:
        return (self.event_id, self.market_id, self.specifier, self.outcome_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "sport_id": self.sport_id,
            "product_id": self.product_id,
            "market_id": self.market_id,
            "market_group": self.market_group,
            "market_name": self.market_name,
            "specifier": self.specifier,
            "outcome_id": self.outcome_id,
            "selection_label": self.selection_label,
            "odds_raw": self.odds_raw,
            "odds_decimal": self.odds_decimal,
            "availability": self.availability.value,
            "provider_quote_at": None,
            "provider_snapshot_id": None,
            "href": self.href,
        }


@dataclasses.dataclass(frozen=True)
class NativeEvent:
    event_id: str
    sport_id: str | None
    product_id: str | None
    competition_id: None
    competition_name: None
    home_participant_id: None
    home_participant_name: None
    away_participant_id: None
    away_participant_name: None
    kickoff: None
    event_status: None
    selection_count: int

    def __post_init__(self) -> None:
        try:
            event_id = validate_event_id(self.event_id)
        except SportyBetLiteCaptureError as exc:
            raise SportyBetProviderInventoryError(str(exc)) from exc
        sport_id = None
        if self.sport_id is not None:
            try:
                sport_id = validate_sport_id(self.sport_id)
            except SportyBetLiteCaptureError as exc:
                raise SportyBetProviderInventoryError(str(exc)) from exc
        product_id = None if self.product_id is None else _native_id(self.product_id, "product_id")
        if any(
            value is not None
            for value in (
                self.competition_id,
                self.competition_name,
                self.home_participant_id,
                self.home_participant_name,
                self.away_participant_id,
                self.away_participant_name,
                self.kickoff,
                self.event_status,
            )
        ):
            raise SportyBetProviderInventoryError(
                "unproven Lite event metadata must remain None"
            )
        if type(self.selection_count) is not int or self.selection_count <= 0:
            raise SportyBetProviderInventoryError("selection_count must be positive")
        object.__setattr__(self, "event_id", event_id)
        object.__setattr__(self, "sport_id", sport_id)
        object.__setattr__(self, "product_id", product_id)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class SportyBetProviderNativeInventory:
    schema_version: int
    dataset_name: str
    source_manifest_sha256: str
    source_raw_sha256: str
    source_request_target: str
    source_observed_at: str
    provider_quote_timestamp_capability: str
    provider_snapshot_id_capability: str
    events: tuple[NativeEvent, ...]
    selections: tuple[NativeSelection, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise SportyBetProviderInventoryError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME:
            raise SportyBetProviderInventoryError("dataset_name mismatch")
        for label, value in (
            ("source_manifest_sha256", self.source_manifest_sha256),
            ("source_raw_sha256", self.source_raw_sha256),
        ):
            if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
                raise SportyBetProviderInventoryError(f"{label} is invalid")
        if not isinstance(self.source_request_target, str) or not self.source_request_target.startswith("/ng/lite"):
            raise SportyBetProviderInventoryError("source_request_target is invalid")
        if not isinstance(self.source_observed_at, str) or not self.source_observed_at.endswith("Z"):
            raise SportyBetProviderInventoryError("source_observed_at is invalid")
        if self.provider_quote_timestamp_capability != "UNPROVEN_ON_REVIEWED_LITE_HTML":
            raise SportyBetProviderInventoryError("quote timestamp capability mismatch")
        if self.provider_snapshot_id_capability != "UNPROVEN_ON_REVIEWED_LITE_HTML":
            raise SportyBetProviderInventoryError("snapshot capability mismatch")
        if type(self.events) is not tuple or type(self.selections) is not tuple:
            raise SportyBetProviderInventoryError("events and selections must be tuples")
        if not self.events or not self.selections:
            raise SportyBetProviderInventoryError("inventory must contain provider-native selections")
        safety = _validate_safety(self.safety)
        object.__setattr__(self, "safety", safety)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "source_request_target": self.source_request_target,
            "source_observed_at": self.source_observed_at,
            "provider_quote_timestamp_capability": self.provider_quote_timestamp_capability,
            "provider_snapshot_id_capability": self.provider_snapshot_id_capability,
            "events": [item.to_dict() for item in self.events],
            "selections": [item.to_dict() for item in self.selections],
            "safety": dict(self.safety),
        }


class _SportyBetLiteLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, dict[str, str | None], str]] = []
        self._anchor_href: str | None = None
        self._anchor_attrs: dict[str, str | None] = {}
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        if self._anchor_href is not None:
            raise SportyBetProviderInventoryError("nested anchor tags are not accepted")
        detached: dict[str, str | None] = {}
        for key, value in attrs:
            key = key.lower()
            if key in detached:
                raise SportyBetProviderInventoryError(
                    f"duplicate anchor attribute {key!r}"
                )
            detached[key] = value
        href = detached.get("href")
        self._anchor_href = href if isinstance(href, str) else ""
        self._anchor_attrs = detached
        self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._anchor_href is not None:
            self._anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._anchor_href is None:
            return
        if len(self.links) >= MAX_LINKS:
            raise SportyBetProviderInventoryError("HTML contains too many links")
        self.links.append(
            (
                self._anchor_href,
                dict(self._anchor_attrs),
                " ".join("".join(self._anchor_text).split()),
            )
        )
        self._anchor_href = None
        self._anchor_attrs = {}
        self._anchor_text = []


def _selection_from_link(
    href: str,
    attrs: Mapping[str, str | None],
    anchor_text: str,
) -> NativeSelection | None:
    if not href:
        return None
    _, query = _query_mapping(href)
    required = {"eventId", "marketId", "outcomeId", "odds"}
    selection_specific = {"marketId", "outcomeId", "odds"}.intersection(query)
    if not selection_specific:
        return None
    present = required.intersection(query)
    if present != required:
        missing = sorted(required - present)
        raise SportyBetProviderInventoryError(
            f"provider selection link is incomplete; missing {missing}"
        )
    event_id = query["eventId"]
    market_id = query["marketId"]
    outcome_id = query["outcomeId"]
    odds_raw, odds_decimal = validate_odds(query["odds"])
    sport_id = query.get("sportId")
    product_id = query.get("productId")
    market_group = query.get("marketGroupsName")
    specifier = query.get("specifier")
    market_name = attrs.get("data-market-name")
    selection_label = attrs.get("data-outcome-name") or attrs.get("data-selection-name")
    normalized_anchor_text = _bounded_text(anchor_text, "anchor_text")
    if selection_label is None and normalized_anchor_text not in {None, odds_raw}:
        selection_label = normalized_anchor_text
    availability = _explicit_availability(attrs)
    return NativeSelection(
        event_id=event_id,
        sport_id=sport_id,
        product_id=product_id,
        market_id=market_id,
        market_group=market_group,
        market_name=market_name,
        specifier=specifier,
        outcome_id=outcome_id,
        selection_label=selection_label,
        odds_raw=odds_raw,
        odds_decimal=odds_decimal,
        availability=availability,
        provider_quote_at=None,
        provider_snapshot_id=None,
        href=href,
    )


def extract_native_selections(raw_html: Any) -> tuple[NativeSelection, ...]:
    if type(raw_html) is not bytes or not raw_html:
        raise SportyBetProviderInventoryError("raw_html must be non-empty exact bytes")
    if len(raw_html) > MAX_HTML_BYTES:
        raise SportyBetProviderInventoryError("raw_html exceeds the 8 MiB limit")
    try:
        text = raw_html.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SportyBetProviderInventoryError("raw_html is not valid UTF-8") from exc
    parser = _SportyBetLiteLinkParser()
    try:
        parser.feed(text)
        parser.close()
    except SportyBetProviderInventoryError:
        raise
    except Exception as exc:
        raise SportyBetProviderInventoryError(
            f"HTML parsing failed: {type(exc).__name__}"
        ) from exc
    selections: list[NativeSelection] = []
    identities: set[tuple[str, str, str | None, str]] = set()
    for href, attrs, anchor_text in parser.links:
        selection = _selection_from_link(href, attrs, anchor_text)
        if selection is None:
            continue
        identity = selection.selection_identity
        if identity in identities:
            raise SportyBetProviderInventoryError(
                "duplicate provider-native selection identity"
            )
        identities.add(identity)
        selections.append(selection)
    if not selections:
        raise SportyBetProviderInventoryError(
            "no structurally qualified provider-native selection links found"
        )
    return tuple(
        sorted(
            selections,
            key=lambda item: (
                item.event_id,
                item.market_id,
                item.specifier or "",
                item.outcome_id,
            ),
        )
    )


def build_inventory(
    manifest: Any,
    raw_html: Any,
    *,
    source_manifest_sha256: str,
) -> SportyBetProviderNativeInventory:
    if not isinstance(manifest, SportyBetLiteCaptureManifest):
        raise SportyBetProviderInventoryError(
            "manifest must be SportyBetLiteCaptureManifest"
        )
    if not isinstance(source_manifest_sha256, str) or re.fullmatch(
        r"[0-9a-f]{64}", source_manifest_sha256
    ) is None:
        raise SportyBetProviderInventoryError("source_manifest_sha256 is invalid")
    from domain.sportybet_lite_source_capture import sha256_bytes, serialize_utc

    if type(raw_html) is not bytes:
        raise SportyBetProviderInventoryError("raw_html must be exact bytes")
    if sha256_bytes(raw_html) != manifest.raw_sha256 or len(raw_html) != manifest.raw_size:
        raise SportyBetProviderInventoryError("raw_html does not match source manifest")
    selections = extract_native_selections(raw_html)
    grouped: dict[str, list[NativeSelection]] = {}
    for item in selections:
        grouped.setdefault(item.event_id, []).append(item)
    events: list[NativeEvent] = []
    for event_id, items in grouped.items():
        sport_ids = {item.sport_id for item in items if item.sport_id is not None}
        product_ids = {item.product_id for item in items if item.product_id is not None}
        if len(sport_ids) > 1 or len(product_ids) > 1:
            raise SportyBetProviderInventoryError(
                "conflicting provider sport/product identity within one event"
            )
        events.append(
            NativeEvent(
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
        )
    return SportyBetProviderNativeInventory(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        source_manifest_sha256=source_manifest_sha256,
        source_raw_sha256=manifest.raw_sha256,
        source_request_target=manifest.request_target,
        source_observed_at=serialize_utc(manifest.observed_at),
        provider_quote_timestamp_capability="UNPROVEN_ON_REVIEWED_LITE_HTML",
        provider_snapshot_id_capability="UNPROVEN_ON_REVIEWED_LITE_HTML",
        events=tuple(sorted(events, key=lambda item: item.event_id)),
        selections=selections,
        safety=_default_safety(),
    )


def canonical_inventory_bytes(inventory: Any) -> bytes:
    if not isinstance(inventory, SportyBetProviderNativeInventory):
        raise SportyBetProviderInventoryError(
            "inventory must be SportyBetProviderNativeInventory"
        )
    try:
        return (
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
        raise SportyBetProviderInventoryError("inventory serialization failed") from exc
