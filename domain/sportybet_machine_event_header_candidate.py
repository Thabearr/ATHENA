"""Machine-derived SportyBet event-header candidate from preserved event-detail HTML.

This research boundary consumes the exact PR #153 user-controlled event-detail
manifest, the exact PR #154 provider-native inventory derived from the same HTML,
and the preserved raw HTML bytes.  It extracts only visible event-header text:
competition, displayed date/time, home participant and away participant.

The result is deliberately a candidate.  The reviewed Lite HTML has not yet
proved a provider-supplied year or timezone field, and this module does not turn
a displayed clock into UTC by assumption.  No fixture-reconciliation, pricing,
selection, slip, booking-code, execution or BET authority is created.
"""

from __future__ import annotations

import dataclasses
import html.parser
import json
import re
import types
from collections.abc import Mapping
from typing import Any

from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native
from domain.sportybet_lite_source_capture import (
    SportyBetLiteCaptureError,
    SportyBetLiteRequestKind,
    sha256_bytes,
    validate_event_id,
    validate_sport_id,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-sportybet-machine-event-header-candidate-v1"
PROVIDER = "SportyBet"
EXTRACTION_AUTHORITY = "MACHINE_DERIVED_FROM_PRESERVED_PROVIDER_HTML_VISIBLE_TEXT"
DISPLAY_TIME_BASIS = "UNPROVEN_IN_PRESERVED_EVENT_DETAIL_HTML"
MATCHING_STATUS = "EVENT_HEADER_CANDIDATE_ONLY"
MAX_RAW_BYTES = 8 * 1024 * 1024
MAX_CANONICAL_BYTES = 256 * 1024

_EVIDENCE_ID_RE = re.compile(r"^[0-9a-f]{24}$", flags=re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_DATE_WEEKDAY_RE = re.compile(
    r"^(?P<day>0[1-9]|[12][0-9]|3[01])/(?P<month>0[1-9]|1[0-2]) "
    r"(?P<weekday>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)$",
    flags=re.ASCII,
)
_TIME_RE = re.compile(
    r"^(?P<hour>[01][0-9]|2[0-3]):(?P<minute>[0-5][0-9])$",
    flags=re.ASCII,
)
_COMBINED_DATE_TIME_RE = re.compile(
    r"^(?P<day>0[1-9]|[12][0-9]|3[01])/(?P<month>0[1-9]|1[0-2]) "
    r"(?P<weekday>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) "
    r"(?P<hour>[01][0-9]|2[0-3]):(?P<minute>[0-5][0-9])$",
    flags=re.ASCII,
)
_DECIMAL_ODDS_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)?$", flags=re.ASCII)
_MONTH_MAX_DAY = {
    1: 31,
    2: 29,
    3: 31,
    4: 30,
    5: 31,
    6: 30,
    7: 31,
    8: 31,
    9: 30,
    10: 31,
    11: 30,
    12: 31,
}

_IGNORED_TAGS = frozenset({"script", "style", "noscript", "svg", "template"})
_NAVIGATION_TOKENS = frozenset(
    {
        "Please turn JavaScript on in browser",
        "Don't know how?",
        "Register",
        "Log In",
        "Cashout",
        "Back",
        "Refresh",
    }
)
_SAFETY_KEYS = frozenset(
    {
        "bet_authorized",
        "bookmaker_equivalence_authorized",
        "booking_code_authorized",
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


class SportyBetMachineEventHeaderError(ValueError):
    """Raised when the event-header candidate boundary fails closed."""


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise SportyBetMachineEventHeaderError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise SportyBetMachineEventHeaderError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(detached)


def _hash(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise SportyBetMachineEventHeaderError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _text(value: Any, label: str, *, maximum: int = 160) -> str:
    if type(value) is not str:
        raise SportyBetMachineEventHeaderError(f"{label} must be a string")
    if not value or value != value.strip() or len(value) > maximum:
        raise SportyBetMachineEventHeaderError(
            f"{label} is not canonical visible text"
        )
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise SportyBetMachineEventHeaderError(
            f"{label} contains a control character"
        )
    return value


def _validate_month_day(day: Any, month: Any) -> tuple[int, int]:
    if type(day) is not int or type(month) is not int:
        raise SportyBetMachineEventHeaderError("kickoff month/day must be exact integers")
    maximum = _MONTH_MAX_DAY.get(month)
    if maximum is None or day < 1 or day > maximum:
        raise SportyBetMachineEventHeaderError("kickoff month/day is impossible")
    return day, month


def _normalize_visible_text(value: str) -> str | None:
    # HTML rendering collapses whitespace. Preserve character/case content
    # otherwise; do not apply Unicode normalization, case folding or aliases.
    collapsed = " ".join(value.split())
    return collapsed or None


class _VisibleTextParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.tokens: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag.lower() in _IGNORED_TAGS:
            self._ignored_depth += 1

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del tag, attrs

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _IGNORED_TAGS:
            if self._ignored_depth <= 0:
                raise SportyBetMachineEventHeaderError(
                    "ignored-tag nesting is malformed"
                )
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        token = _normalize_visible_text(data)
        if token is not None:
            self.tokens.append(token)

    def close_checked(self) -> tuple[str, ...]:
        try:
            self.close()
        except SportyBetMachineEventHeaderError:
            raise
        except Exception as exc:  # pragma: no cover - defensive parser boundary
            raise SportyBetMachineEventHeaderError("HTML parsing failed") from exc
        if self._ignored_depth != 0:
            raise SportyBetMachineEventHeaderError(
                "ignored-tag nesting is incomplete"
            )
        return tuple(self.tokens)


def visible_text_tokens(raw_html: Any) -> tuple[str, ...]:
    if type(raw_html) is not bytes or not 0 < len(raw_html) <= MAX_RAW_BYTES:
        raise SportyBetMachineEventHeaderError(
            "raw_html must be bounded non-empty bytes"
        )
    try:
        decoded = raw_html.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SportyBetMachineEventHeaderError(
            "raw_html must be valid UTF-8"
        ) from exc
    parser = _VisibleTextParser()
    try:
        parser.feed(decoded)
        tokens = parser.close_checked()
    except SportyBetMachineEventHeaderError:
        raise
    except Exception as exc:  # pragma: no cover - defensive parser boundary
        raise SportyBetMachineEventHeaderError("HTML parsing failed") from exc
    if not tokens:
        raise SportyBetMachineEventHeaderError("raw_html contains no visible text")
    return tokens


def _is_navigation_token(token: str) -> bool:
    if token in _NAVIGATION_TOKENS:
        return True
    if token.startswith("Betslip(") and token.endswith(")"):
        return True
    if token.startswith("Cashout Betslip(") and token.endswith(")"):
        return True
    return False


def _event_label(token: str, label: str) -> str:
    value = _text(token, label)
    if _is_navigation_token(value):
        raise SportyBetMachineEventHeaderError(f"{label} is navigation text")
    if _DECIMAL_ODDS_RE.fullmatch(value) is not None:
        raise SportyBetMachineEventHeaderError(f"{label} looks like an odds value")
    if (
        _DATE_WEEKDAY_RE.fullmatch(value)
        or _TIME_RE.fullmatch(value)
        or _COMBINED_DATE_TIME_RE.fullmatch(value)
    ):
        raise SportyBetMachineEventHeaderError(
            f"{label} looks like date/time text"
        )
    return value


def _candidate_windows(tokens: tuple[str, ...]) -> list[tuple[int, int, str]]:
    windows: list[tuple[int, int, str]] = []
    for index, token in enumerate(tokens):
        combined = _COMBINED_DATE_TIME_RE.fullmatch(token)
        if combined is not None:
            _validate_month_day(
                int(combined.group("day")),
                int(combined.group("month")),
            )
            windows.append((index, index, token))
        if index + 1 < len(tokens):
            first = _DATE_WEEKDAY_RE.fullmatch(token)
            second = _TIME_RE.fullmatch(tokens[index + 1])
            if first is not None and second is not None:
                _validate_month_day(
                    int(first.group("day")),
                    int(first.group("month")),
                )
                windows.append(
                    (index, index + 1, f"{token} {tokens[index + 1]}")
                )
    return windows


def _nearest_content_before(
    tokens: tuple[str, ...],
    start: int,
) -> tuple[int, str]:
    index = start - 1
    while index >= 0 and _is_navigation_token(tokens[index]):
        index -= 1
    if index < 0:
        raise SportyBetMachineEventHeaderError(
            "event competition text is missing"
        )
    return index, _event_label(tokens[index], "competition_display")


def _next_content(
    tokens: tuple[str, ...],
    start: int,
    label: str,
) -> tuple[int, str]:
    index = start
    while index < len(tokens) and _is_navigation_token(tokens[index]):
        index += 1
    if index >= len(tokens):
        raise SportyBetMachineEventHeaderError(f"{label} is missing")
    return index, _event_label(tokens[index], label)


@dataclasses.dataclass(frozen=True)
class ExtractedVisibleEventHeader:
    competition_display: str
    kickoff_display: str
    home_display: str
    away_display: str
    kickoff_day: int
    kickoff_month: int
    kickoff_weekday: str
    kickoff_hour: int
    kickoff_minute: int

    def __post_init__(self) -> None:
        competition = _event_label(
            self.competition_display,
            "competition_display",
        )
        kickoff = _text(
            self.kickoff_display,
            "kickoff_display",
            maximum=40,
        )
        match = _COMBINED_DATE_TIME_RE.fullmatch(kickoff)
        if match is None:
            raise SportyBetMachineEventHeaderError(
                "kickoff_display format mismatch"
            )
        home = _event_label(self.home_display, "home_display")
        away = _event_label(self.away_display, "away_display")
        if home == away:
            raise SportyBetMachineEventHeaderError(
                "home and away display names must differ"
            )
        _validate_month_day(
            int(match.group("day")),
            int(match.group("month")),
        )
        expected = (
            int(match.group("day")),
            int(match.group("month")),
            match.group("weekday"),
            int(match.group("hour")),
            int(match.group("minute")),
        )
        actual = (
            self.kickoff_day,
            self.kickoff_month,
            self.kickoff_weekday,
            self.kickoff_hour,
            self.kickoff_minute,
        )
        if expected != actual:
            raise SportyBetMachineEventHeaderError(
                "parsed kickoff fields mismatch display text"
            )
        object.__setattr__(self, "competition_display", competition)
        object.__setattr__(self, "home_display", home)
        object.__setattr__(self, "away_display", away)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def extract_visible_event_header(raw_html: Any) -> ExtractedVisibleEventHeader:
    tokens = visible_text_tokens(raw_html)
    extracted: list[ExtractedVisibleEventHeader] = []
    for start, end, kickoff_display in _candidate_windows(tokens):
        try:
            _, competition = _nearest_content_before(tokens, start)
            home_index, home = _next_content(
                tokens,
                end + 1,
                "home_display",
            )
            _, away = _next_content(
                tokens,
                home_index + 1,
                "away_display",
            )
            match = _COMBINED_DATE_TIME_RE.fullmatch(kickoff_display)
            assert match is not None
            extracted.append(
                ExtractedVisibleEventHeader(
                    competition_display=competition,
                    kickoff_display=kickoff_display,
                    home_display=home,
                    away_display=away,
                    kickoff_day=int(match.group("day")),
                    kickoff_month=int(match.group("month")),
                    kickoff_weekday=match.group("weekday"),
                    kickoff_hour=int(match.group("hour")),
                    kickoff_minute=int(match.group("minute")),
                )
            )
        except SportyBetMachineEventHeaderError:
            continue
    unique = {
        json.dumps(
            item.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ): item
        for item in extracted
    }
    if len(unique) != 1:
        if not unique:
            raise SportyBetMachineEventHeaderError(
                "no unique machine-readable event header candidate"
            )
        raise SportyBetMachineEventHeaderError(
            "multiple machine-readable event header candidates"
        )
    return next(iter(unique.values()))


def _validate_lineage(
    manifest: Any,
    inventory: Any,
    raw_html: bytes,
) -> tuple[str, str, str, str, str]:
    if not isinstance(
        manifest,
        manual.SportyBetUserControlledEvidenceManifest,
    ):
        raise SportyBetMachineEventHeaderError("manifest type mismatch")
    if not isinstance(
        inventory,
        native.SportyBetUserControlledNativeInventory,
    ):
        raise SportyBetMachineEventHeaderError("inventory type mismatch")
    if manifest.request_kind is not SportyBetLiteRequestKind.EVENT_DETAIL:
        raise SportyBetMachineEventHeaderError(
            "machine event header requires event-detail evidence"
        )
    if manifest.event_id is None or manifest.sport_id is None:
        raise SportyBetMachineEventHeaderError(
            "event-detail provider identity is incomplete"
        )
    raw_sha = sha256_bytes(raw_html)
    if raw_sha != manifest.raw_sha256 or len(raw_html) != manifest.raw_size:
        raise SportyBetMachineEventHeaderError(
            "raw HTML does not match source manifest"
        )
    evidence_id = manual.evidence_identifier(manifest)
    manifest_sha = manual.manifest_sha256(manifest)
    if (
        inventory.source_evidence_id != evidence_id
        or inventory.source_evidence_manifest_sha256 != manifest_sha
        or inventory.source_raw_sha256 != raw_sha
        or inventory.source_url != manifest.source_url
        or inventory.source_event_id != manifest.event_id
        or inventory.source_sport_id != manifest.sport_id
        or inventory.source_request_kind
        is not SportyBetLiteRequestKind.EVENT_DETAIL
    ):
        raise SportyBetMachineEventHeaderError(
            "native inventory lineage does not match source evidence"
        )
    if {event.event_id for event in inventory.events} != {manifest.event_id}:
        raise SportyBetMachineEventHeaderError(
            "native inventory event population mismatch"
        )
    return (
        evidence_id,
        manifest_sha,
        native.inventory_sha256(inventory),
        raw_sha,
        manifest.event_id,
    )


@dataclasses.dataclass(frozen=True)
class SportyBetMachineEventHeaderCandidate:
    schema_version: int
    dataset_name: str
    provider: str
    source_evidence_id: str
    source_evidence_manifest_sha256: str
    source_native_inventory_sha256: str
    source_raw_sha256: str
    source_url: str
    event_id: str
    sport_id: str
    extraction_authority: str
    matching_status: str
    competition_display: str
    home_display: str
    away_display: str
    kickoff_display: str
    kickoff_day: int
    kickoff_month: int
    kickoff_weekday: str
    kickoff_hour: int
    kickoff_minute: int
    kickoff_year: None
    kickoff_timezone: None
    kickoff_utc: None
    display_time_basis: str
    provider_quote_at: None
    provider_snapshot_id: None
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != SCHEMA_VERSION
        ):
            raise SportyBetMachineEventHeaderError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME or self.provider != PROVIDER:
            raise SportyBetMachineEventHeaderError("dataset/provider mismatch")
        if (
            type(self.source_evidence_id) is not str
            or _EVIDENCE_ID_RE.fullmatch(self.source_evidence_id) is None
        ):
            raise SportyBetMachineEventHeaderError(
                "source_evidence_id is invalid"
            )
        _hash(
            self.source_evidence_manifest_sha256,
            "source_evidence_manifest_sha256",
        )
        _hash(
            self.source_native_inventory_sha256,
            "source_native_inventory_sha256",
        )
        _hash(self.source_raw_sha256, "source_raw_sha256")
        try:
            kind, event_id, sport_id, _, _ = manual.validate_source_url(
                self.source_url
            )
        except manual.SportyBetUserEvidenceError as exc:
            raise SportyBetMachineEventHeaderError(str(exc)) from exc
        if kind is not SportyBetLiteRequestKind.EVENT_DETAIL:
            raise SportyBetMachineEventHeaderError(
                "source_url must be exact reviewed event-detail URL"
            )
        try:
            checked_event_id = validate_event_id(self.event_id)
            checked_sport_id = validate_sport_id(self.sport_id)
        except SportyBetLiteCaptureError as exc:
            raise SportyBetMachineEventHeaderError(str(exc)) from exc
        if checked_event_id != event_id or checked_sport_id != sport_id:
            raise SportyBetMachineEventHeaderError(
                "provider event/sport identity does not match source_url"
            )
        if (
            self.extraction_authority != EXTRACTION_AUTHORITY
            or self.matching_status != MATCHING_STATUS
        ):
            raise SportyBetMachineEventHeaderError(
                "candidate authority/status mismatch"
            )
        header = ExtractedVisibleEventHeader(
            competition_display=self.competition_display,
            kickoff_display=self.kickoff_display,
            home_display=self.home_display,
            away_display=self.away_display,
            kickoff_day=self.kickoff_day,
            kickoff_month=self.kickoff_month,
            kickoff_weekday=self.kickoff_weekday,
            kickoff_hour=self.kickoff_hour,
            kickoff_minute=self.kickoff_minute,
        )
        if (
            self.kickoff_year is not None
            or self.kickoff_timezone is not None
            or self.kickoff_utc is not None
        ):
            raise SportyBetMachineEventHeaderError(
                "year/timezone/UTC are unproven and must remain null"
            )
        if self.display_time_basis != DISPLAY_TIME_BASIS:
            raise SportyBetMachineEventHeaderError(
                "display_time_basis mismatch"
            )
        if (
            self.provider_quote_at is not None
            or self.provider_snapshot_id is not None
        ):
            raise SportyBetMachineEventHeaderError(
                "quote/snapshot identity remains unproven"
            )
        object.__setattr__(
            self,
            "competition_display",
            header.competition_display,
        )
        object.__setattr__(self, "home_display", header.home_display)
        object.__setattr__(self, "away_display", header.away_display)
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "provider": self.provider,
            "source_evidence_id": self.source_evidence_id,
            "source_evidence_manifest_sha256": self.source_evidence_manifest_sha256,
            "source_native_inventory_sha256": self.source_native_inventory_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "source_url": self.source_url,
            "event_id": self.event_id,
            "sport_id": self.sport_id,
            "extraction_authority": self.extraction_authority,
            "matching_status": self.matching_status,
            "competition_display": self.competition_display,
            "home_display": self.home_display,
            "away_display": self.away_display,
            "kickoff_display": self.kickoff_display,
            "kickoff_day": self.kickoff_day,
            "kickoff_month": self.kickoff_month,
            "kickoff_weekday": self.kickoff_weekday,
            "kickoff_hour": self.kickoff_hour,
            "kickoff_minute": self.kickoff_minute,
            "kickoff_year": None,
            "kickoff_timezone": None,
            "kickoff_utc": None,
            "display_time_basis": self.display_time_basis,
            "provider_quote_at": None,
            "provider_snapshot_id": None,
            "safety": dict(self.safety),
        }


def build_machine_event_header_candidate(
    *,
    manifest: manual.SportyBetUserControlledEvidenceManifest,
    inventory: native.SportyBetUserControlledNativeInventory,
    raw_html: bytes,
) -> SportyBetMachineEventHeaderCandidate:
    (
        evidence_id,
        manifest_sha,
        inventory_sha,
        raw_sha,
        event_id,
    ) = _validate_lineage(manifest, inventory, raw_html)
    header = extract_visible_event_header(raw_html)
    assert manifest.sport_id is not None
    return SportyBetMachineEventHeaderCandidate(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        provider=PROVIDER,
        source_evidence_id=evidence_id,
        source_evidence_manifest_sha256=manifest_sha,
        source_native_inventory_sha256=inventory_sha,
        source_raw_sha256=raw_sha,
        source_url=manifest.source_url,
        event_id=event_id,
        sport_id=manifest.sport_id,
        extraction_authority=EXTRACTION_AUTHORITY,
        matching_status=MATCHING_STATUS,
        competition_display=header.competition_display,
        home_display=header.home_display,
        away_display=header.away_display,
        kickoff_display=header.kickoff_display,
        kickoff_day=header.kickoff_day,
        kickoff_month=header.kickoff_month,
        kickoff_weekday=header.kickoff_weekday,
        kickoff_hour=header.kickoff_hour,
        kickoff_minute=header.kickoff_minute,
        kickoff_year=None,
        kickoff_timezone=None,
        kickoff_utc=None,
        display_time_basis=DISPLAY_TIME_BASIS,
        provider_quote_at=None,
        provider_snapshot_id=None,
        safety=_default_safety(),
    )


def canonical_candidate_bytes(candidate: Any) -> bytes:
    if not isinstance(candidate, SportyBetMachineEventHeaderCandidate):
        raise SportyBetMachineEventHeaderError("candidate type mismatch")
    try:
        payload = (
            json.dumps(
                candidate.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportyBetMachineEventHeaderError(
            "candidate serialization failed"
        ) from exc
    if len(payload) > MAX_CANONICAL_BYTES:
        raise SportyBetMachineEventHeaderError(
            "candidate exceeds reviewed size limit"
        )
    return payload


def candidate_sha256(candidate: Any) -> str:
    return sha256_bytes(canonical_candidate_bytes(candidate))
