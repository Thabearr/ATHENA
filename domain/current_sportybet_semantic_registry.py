"""Versioned, research-only SportyBet semantic coverage and readiness.

This module is an additive boundary between the reviewed anonymous SportyBet
source and the later all-market shadow adapters.  It deliberately does not
price a market, choose a selection, or grant execution authority.  Provider
rows are accepted only through exact provider-native IDs, names, specifiers,
outcome IDs and labels.  A row observed in one event is evidence for that
event; it is never a promise that the same market is offered on every event.

The two source contracts used here are the existing current discovery capture
and exact event-detail capture.  ``replay_event_evidence`` re-reads and
reconstructs both source files, so a detached hash or a caller-mutated summary
cannot become semantic authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
import shutil
import types
from typing import Any, Iterable, Mapping, Sequence

from domain.markets import MARKET_REGISTRY, MarketFamily, MarketId, OutcomeId
from domain.model_status import MODEL_STATUS_REGISTRY
from domain import current_direct_provider_canonical_market_mapping_rebind as current_mapping
from domain import sportybet_current_event_discovery_reconciliation as discovery
from domain import sportybet_early_payout_settlement as early_payout
from domain import sportybet_live_event_quote_evidence as live


SCHEMA_VERSION = 1
CONTRACT_VERSION = 1
DATASET_NAME = "athena-current-sportybet-semantic-readiness-registry-v1"
POLICY_ID = "PRB_EXACT_CURRENT_SPORTYBET_SEMANTIC_POLICIES_V1"
NEXT_BOUNDARY = "PRC_ALL_MARKET_SHADOW_PROBABILITY_SETTLEMENT_ADAPTER"

# These are source-contract identities, not caller-provided labels.  They are
# intentionally calculated from the reviewed modules at import time so source
# contract drift fails closed rather than being relabelled by this registry.
SOURCE_CONTRACT_IDENTITIES = types.MappingProxyType(
    {
        "event_detail": live.EXPECTED_CONTRACT_SHA256,
        "event_discovery": discovery.EXPECTED_CONTRACT_SHA256,
        "reviewed_canonical_mapping": current_mapping.EXPECTED_CONTRACT_SHA256,
        "early_payout_settlement": early_payout.sha256_sportybet_early_payout_settlement_receipt(
            early_payout.reviewed_sportybet_early_payout_settlement_receipt()
        ),
        "pr258_market18_reconciliation": (
            "PR258_REVIEWED_MARKET18_TOTAL_GOALS_TO_OVER_UNDER_EXACT_NATIVE_ID_"
            "SPECIFIER_OUTCOME_LABEL_V1"
        ),
    }
)

_SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_EVENT_RE = re.compile(r"^sr:match:[1-9][0-9]*$", re.ASCII)
_DECIMAL_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$", re.ASCII)
_TOTAL_SPECIFIER_RE = re.compile(
    r"^total=((?:0|[1-9][0-9]*)(?:\.[0-9]+)?)$", re.ASCII
)
_HCP_SPECIFIER_RE = re.compile(
    r"^hcp=(-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?)$", re.ASCII
)


class ProviderSemanticStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    SUPPORTED_WITH_EXACT_LINE_POLICY = "SUPPORTED_WITH_EXACT_LINE_POLICY"
    CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN = "CURRENT_PROVIDER_UNAVAILABLE/UNPROVEN"


# Short aliases are useful to callers while preserving the explicit public
# vocabulary required by the issue.
CURRENT_PROVIDER_UNAVAILABLE = ProviderSemanticStatus.CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN
CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN = ProviderSemanticStatus.CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN


class SettlementClass(str, Enum):
    REGULATION_1X2_PARTITION = "REGULATION_1X2_PARTITION"
    TOTALS_EXACT_LINE_SETTLEMENT = "TOTALS_EXACT_LINE_SETTLEMENT"
    RESULT_OR_TOTAL_UNION_COMPLEMENT = "RESULT_OR_TOTAL_UNION_COMPLEMENT"
    WEH_COMPLEMENTARY_BINARY = "WEH_COMPLEMENTARY_BINARY"
    DOUBLE_CHANCE_OVERLAPPING_EVENTS = "DOUBLE_CHANCE_OVERLAPPING_EVENTS"
    BTTS_COMPLEMENTARY_BINARY = "BTTS_COMPLEMENTARY_BINARY"
    DNB_WIN_PUSH_LOSS = "DNB_WIN_PUSH_LOSS"
    WIN_TO_NIL_COMPLEMENTARY_BINARY = "WIN_TO_NIL_COMPLEMENTARY_BINARY"
    EARLY_PAYOUT_OVERLAPPING_EVENTS = "EARLY_PAYOUT_OVERLAPPING_EVENTS"
    ASIAN_HANDICAP_FULL_SETTLEMENT = "ASIAN_HANDICAP_FULL_SETTLEMENT"


class EvidenceFreshnessState(str, Enum):
    CURRENT = "CURRENT"
    OBSERVED = "OBSERVED"
    NO_EVIDENCE = "NO_EVIDENCE"
    STALE = "STALE"
    FUTURE_DATED = "FUTURE_DATED"
    TOO_CLOSE_TO_KICKOFF = "TOO_CLOSE_TO_KICKOFF"
    NOT_PREMATCH_BOOKABLE = "NOT_PREMATCH_BOOKABLE"
    CONFLICTING = "CONFLICTING"


class CurrentSportyBetSemanticRegistryError(ValueError):
    """Raised when exact provider semantics cannot be established."""


def _canonical_bytes(value: Any, *, newline: bool = False) -> bytes:
    try:
        result = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentSportyBetSemanticRegistryError(
            "canonical JSON serialization failed"
        ) from exc
    return result + (b"\n" if newline else b"")


def canonical_json_bytes(value: Any) -> bytes:
    """Return the registry's deterministic canonical JSON representation."""

    return _canonical_bytes(value)


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise CurrentSportyBetSemanticRegistryError(
            f"{label} must be an exact lowercase SHA-256"
        )
    return value


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise CurrentSportyBetSemanticRegistryError(
            f"{label} must be timezone-aware"
        )
    try:
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentSportyBetSemanticRegistryError(f"{label} is invalid") from exc


def _text(value: Any, label: str, *, maximum: int = 300) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise CurrentSportyBetSemanticRegistryError(
            f"{label} must be an exact non-empty trimmed string"
        )
    return value


def _event(value: Any) -> str:
    if type(value) is not str or _EVENT_RE.fullmatch(value) is None:
        raise CurrentSportyBetSemanticRegistryError("provider_event_id is invalid")
    return value


def _provider_id(value: Any, label: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise CurrentSportyBetSemanticRegistryError(f"{label} is invalid")
    result = str(value)
    if not re.fullmatch(r"[A-Za-z0-9_.:+/=-]{1,160}", result, re.ASCII):
        raise CurrentSportyBetSemanticRegistryError(f"{label} is invalid")
    return result


def _enum_value(value: Any, enum_type: type[Enum], label: str) -> Enum:
    if not isinstance(value, enum_type):
        raise CurrentSportyBetSemanticRegistryError(f"{label} must be typed")
    return value


def _decimal_token(value: str, label: str) -> Decimal:
    if _DECIMAL_RE.fullmatch(value) is None:
        raise CurrentSportyBetSemanticRegistryError(f"{label} has invalid decimal grammar")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise CurrentSportyBetSemanticRegistryError(f"{label} is invalid") from exc
    if not number.is_finite() or number < 0:
        raise CurrentSportyBetSemanticRegistryError(f"{label} is invalid")
    return number


def _line_from_specifier(specifier: str | None, prefix: str) -> str | None:
    if specifier is None:
        return None
    pattern = _TOTAL_SPECIFIER_RE if prefix == "total" else _HCP_SPECIFIER_RE
    match = pattern.fullmatch(specifier)
    if match is None:
        raise CurrentSportyBetSemanticRegistryError(
            f"{prefix} specifier is not exact reviewed grammar"
        )
    return match.group(1)


def _line_decimal(line: str) -> Decimal:
    return _decimal_token(line, "line")


def _signed_line_decimal(line: str) -> Decimal:
    if re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", line, re.ASCII) is None:
        raise CurrentSportyBetSemanticRegistryError("signed line has invalid decimal grammar")
    try:
        value = Decimal(line)
    except InvalidOperation as exc:
        raise CurrentSportyBetSemanticRegistryError("signed line is invalid") from exc
    if not value.is_finite():
        raise CurrentSportyBetSemanticRegistryError("signed line is invalid")
    return value


def _is_half_line(line: str) -> bool:
    decimal = _line_decimal(line)
    # Current MODEL_STATUS is intentionally half-goal-only: integer lines are
    # push-capable and cannot inherit that analytical readiness.
    return decimal % 1 == Decimal("0.5")


def _format_ah_line(line: str) -> str:
    decimal = _signed_line_decimal(line)
    if decimal == 0:
        return "0"
    # The provider omits a plus sign in the market name, but includes a
    # signed one-decimal outcome label for positive/negative non-zero lines.
    return format(decimal, "f").rstrip("0").rstrip(".")


def _format_ah_outcome_line(line: str, *, home: bool) -> str:
    decimal = _signed_line_decimal(line)
    signed = decimal if home else -decimal
    if signed == 0:
        return "0"
    token = format(abs(signed), "f").rstrip("0").rstrip(".")
    if "." not in token:
        token += ".0"
    return f"+{token}" if signed > 0 else f"-{token}"


def _expected_policy(market_id: MarketId) -> Mapping[str, Any]:
    """Exact provider-native policy for one canonical market.

    These rules are intentionally explicit and market-specific.  They are not
    aliases in ``domain.markets`` and do not perform case folding or fuzzy
    matching.
    """

    common = {"line_policy": None}
    if market_id is MarketId.MATCH_RESULT:
        return {
            **common,
            "market_ids": ("1",),
            "market_names": ("1X2",),
            "outcomes": (("1", "Home", OutcomeId.HOME), ("2", "Draw", OutcomeId.DRAW), ("3", "Away", OutcomeId.AWAY)),
            "specifier": None,
            "settlement": SettlementClass.REGULATION_1X2_PARTITION,
            "ordinary_partition": True,
            "overlap": False,
            "push_split": False,
        }
    if market_id is MarketId.TOTAL_GOALS:
        return {
            **common,
            "market_ids": ("18",),
            "market_names": ("Over/Under", "Total Goals"),
            "outcomes": (("12", "Over", OutcomeId.OVER), ("13", "Under", OutcomeId.UNDER)),
            "specifier_prefix": "total",
            "line_policy": "EXACT_OBSERVED_TOTAL_SPECIFIERS_HALF_UNIT; HALF_LINES_ONLY_FOR_CURRENT_MODEL",
            "mapping_policy": "PR258_REVIEWED_MARKET18_TOTAL_GOALS_TO_OVER_UNDER_EXACT_NATIVE_ID_SPECIFIER_OUTCOME_LABEL_V1",
            "settlement": SettlementClass.TOTALS_EXACT_LINE_SETTLEMENT,
            "ordinary_partition": True,
            "overlap": False,
            "push_split": False,
        }
    if market_id is MarketId.ASIAN_HANDICAP:
        return {
            **common,
            "market_ids": ("16",),
            "market_names": ("__EXACT_COMPUTED_ASIAN_HANDICAP_NAME__",),
            "outcomes": (("1714", "Home", OutcomeId.HOME), ("1715", "Away", OutcomeId.AWAY)),
            "specifier_prefix": "hcp",
            "line_policy": "EXACT_OBSERVED_HCP_SPECIFIERS_QUARTER_UNIT_WITH_PROVIDER_ORIENTATION",
            "settlement": SettlementClass.ASIAN_HANDICAP_FULL_SETTLEMENT,
            "ordinary_partition": False,
            "overlap": False,
            "push_split": True,
        }
    if market_id in {
        MarketId.DRAW_OR_OVER_2_5,
        MarketId.AWAY_OR_OVER_2_5,
        MarketId.HOME_OR_OVER_2_5,
    }:
        market_names = {
            MarketId.DRAW_OR_OVER_2_5: "Draw or Over 2.5",
            MarketId.AWAY_OR_OVER_2_5: "Away or Over 2.5",
            MarketId.HOME_OR_OVER_2_5: "Home Team or Over 2.5",
        }
        market_ids = {
            MarketId.DRAW_OR_OVER_2_5: "856",
            MarketId.AWAY_OR_OVER_2_5: "858",
            MarketId.HOME_OR_OVER_2_5: "854",
        }
        return {
            **common,
            "market_ids": (market_ids[market_id],),
            "market_names": (market_names[market_id],),
            "outcomes": (("74", "Yes", OutcomeId.YES), ("76", "No", OutcomeId.NO)),
            "specifier": "total=2.5",
            "settlement": SettlementClass.RESULT_OR_TOTAL_UNION_COMPLEMENT,
            "ordinary_partition": True,
            "overlap": False,
            "push_split": False,
        }
    if market_id in {MarketId.HOME_WIN_EITHER_HALF, MarketId.AWAY_WIN_EITHER_HALF}:
        name = (
            "Home Team to Win Either Half"
            if market_id is MarketId.HOME_WIN_EITHER_HALF
            else "Away Team to Win Either Half"
        )
        return {
            **common,
            "market_ids": ("50" if market_id is MarketId.HOME_WIN_EITHER_HALF else "51",),
            "market_names": (name,),
            "outcomes": (("74", "Yes", OutcomeId.YES), ("76", "No", OutcomeId.NO)),
            "specifier": None,
            "settlement": SettlementClass.WEH_COMPLEMENTARY_BINARY,
            "ordinary_partition": True,
            "overlap": False,
            "push_split": False,
        }
    if market_id is MarketId.DOUBLE_CHANCE:
        return {
            **common,
            "market_ids": ("10",),
            "market_names": ("Double Chance",),
            "outcomes": (("9", "Home or Draw", OutcomeId.HOME_OR_DRAW), ("10", "Home or Away", OutcomeId.HOME_OR_AWAY), ("11", "Draw or Away", OutcomeId.DRAW_OR_AWAY)),
            "specifier": None,
            "settlement": SettlementClass.DOUBLE_CHANCE_OVERLAPPING_EVENTS,
            "ordinary_partition": False,
            "overlap": True,
            "push_split": False,
        }
    if market_id is MarketId.BTTS:
        return {
            **common,
            "market_ids": ("29",),
            "market_names": ("GG/NG",),
            "outcomes": (("74", "Yes", OutcomeId.YES), ("76", "No", OutcomeId.NO)),
            "specifier": None,
            "settlement": SettlementClass.BTTS_COMPLEMENTARY_BINARY,
            "ordinary_partition": True,
            "overlap": False,
            "push_split": False,
        }
    if market_id is MarketId.DRAW_NO_BET:
        return {
            **common,
            "market_ids": ("11",),
            "market_names": ("Draw No Bet",),
            "outcomes": (("4", "Home", OutcomeId.HOME), ("5", "Away", OutcomeId.AWAY)),
            "specifier": None,
            "settlement": SettlementClass.DNB_WIN_PUSH_LOSS,
            "ordinary_partition": False,
            "overlap": False,
            "push_split": True,
        }
    if market_id in {MarketId.HOME_WIN_TO_NIL, MarketId.AWAY_WIN_TO_NIL}:
        name = (
            "Home Team to Win to Nil"
            if market_id is MarketId.HOME_WIN_TO_NIL
            else "Away Team to Win to Nil"
        )
        return {
            **common,
            "market_ids": ("33" if market_id is MarketId.HOME_WIN_TO_NIL else "34",),
            "market_names": (name,),
            "outcomes": (("74", "Yes", OutcomeId.YES), ("76", "No", OutcomeId.NO)),
            "specifier": None,
            "settlement": SettlementClass.WIN_TO_NIL_COMPLEMENTARY_BINARY,
            "ordinary_partition": True,
            "overlap": False,
            "push_split": False,
        }
    if market_id in {MarketId.MATCH_RESULT_1UP, MarketId.MATCH_RESULT_2UP}:
        one_up = market_id is MarketId.MATCH_RESULT_1UP
        return {
            **common,
            "market_ids": ("60200" if one_up else "60100",),
            "market_names": ("1X2 - 1UP" if one_up else "1X2 - 2UP",),
            "outcomes": (("1", "Home", OutcomeId.HOME), ("2", "Draw", OutcomeId.DRAW), ("3", "Away", OutcomeId.AWAY)),
            "specifier": None,
            "mapping_policy": "REVIEWED_SPORTYBET_NIGERIA_EARLY_PAYOUT_SETTLEMENT_RECEIPT_V2",
            "settlement": SettlementClass.EARLY_PAYOUT_OVERLAPPING_EVENTS,
            "ordinary_partition": False,
            "overlap": True,
            "push_split": False,
        }
    raise CurrentSportyBetSemanticRegistryError(f"no provider policy for {market_id!r}")


def provider_policy(market_id: MarketId) -> Mapping[str, Any]:
    """Return an immutable copy of the exact policy for ``market_id``."""

    market = _coerce_market_id(market_id)
    return types.MappingProxyType(dict(_expected_policy(market)))


def _coerce_market_id(value: Any) -> MarketId:
    if isinstance(value, MarketId):
        return value
    try:
        return MarketId(value)
    except (TypeError, ValueError) as exc:
        raise CurrentSportyBetSemanticRegistryError(
            f"unknown canonical market: {value!r}"
        ) from exc


@dataclass(frozen=True)
class ProviderEventEvidence:
    """A source-bound event inventory and its immutable fixture identity."""

    evidence_directory: Path
    repository_root: Path
    fixture_identity: str
    fixture_identity_basis: str
    inventory: live.SportyBetLiveEventQuoteInventory
    discovery_event_id: str | None = None
    discovery_source_page_num: int | None = None
    discovery_source_raw_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_directory, Path) or not isinstance(self.repository_root, Path):
            raise CurrentSportyBetSemanticRegistryError("evidence paths must be Path")
        _text(self.fixture_identity, "fixture_identity")
        _text(self.fixture_identity_basis, "fixture_identity_basis")
        if type(self.inventory) is not live.SportyBetLiveEventQuoteInventory:
            raise CurrentSportyBetSemanticRegistryError("inventory type mismatch")
        _event(self.inventory.event_id)
        if self.fixture_identity != self.inventory.event_id:
            raise CurrentSportyBetSemanticRegistryError(
                "fixture identity must bind to exact provider event ID"
            )
        if self.discovery_event_id is not None and self.discovery_event_id != self.inventory.event_id:
            raise CurrentSportyBetSemanticRegistryError("discovery/event identity mismatch")
        if self.discovery_source_raw_sha256 is not None:
            _sha(self.discovery_source_raw_sha256, "discovery_source_raw_sha256")
        if self.discovery_source_page_num is not None and (
            type(self.discovery_source_page_num) is not int
            or self.discovery_source_page_num < 1
        ):
            raise CurrentSportyBetSemanticRegistryError("discovery source page is invalid")

    @property
    def source_inventory_sha256(self) -> str:
        return self.inventory.canonical_sha256

    @property
    def source_manifest_sha256(self) -> str:
        return self.inventory.source_manifest_sha256

    @property
    def source_raw_sha256(self) -> str:
        return self.inventory.source_raw_sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_directory": self.evidence_directory.as_posix(),
            "fixture_identity": self.fixture_identity,
            "fixture_identity_basis": self.fixture_identity_basis,
            "inventory": self.inventory.to_dict(),
            "source_inventory_sha256": self.source_inventory_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "discovery_event_id": self.discovery_event_id,
            "discovery_source_page_num": self.discovery_source_page_num,
            "discovery_source_raw_sha256": self.discovery_source_raw_sha256,
        }


def replay_event_evidence(evidence: ProviderEventEvidence) -> ProviderEventEvidence:
    """Replay retained raw+manifest evidence and reject detached summaries."""

    if type(evidence) is not ProviderEventEvidence:
        raise CurrentSportyBetSemanticRegistryError("event evidence type mismatch")
    manifest = live.verify_live_event_quote_evidence(
        evidence.evidence_directory, repository_root=evidence.repository_root
    )
    rebuilt = live.build_live_event_quote_inventory(
        evidence.evidence_directory, repository_root=evidence.repository_root
    )
    if rebuilt.to_dict() != evidence.inventory.to_dict():
        raise CurrentSportyBetSemanticRegistryError(
            "retained source inventory differs from replayed raw evidence"
        )
    if manifest.raw_sha256 != evidence.source_raw_sha256:
        raise CurrentSportyBetSemanticRegistryError("raw SHA identity differs on replay")
    if live.manifest_sha256(manifest) != evidence.source_manifest_sha256:
        raise CurrentSportyBetSemanticRegistryError(
            "manifest SHA identity differs on replay"
        )
    if rebuilt.canonical_sha256 != evidence.source_inventory_sha256:
        raise CurrentSportyBetSemanticRegistryError(
            "inventory SHA identity differs on replay"
        )
    if manifest.event_id != evidence.fixture_identity:
        raise CurrentSportyBetSemanticRegistryError("fixture identity differs on replay")
    return evidence


def load_provider_event_evidence(
    evidence_directory: Path,
    *,
    repository_root: Path,
    fixture_identity: str | None = None,
    fixture_identity_basis: str = "EXACT_PROVIDER_EVENT_ID",
    discovery_event: discovery.SportyBetDiscoveredEvent | None = None,
) -> ProviderEventEvidence:
    """Construct source-bound evidence by replaying an existing capture."""

    manifest = live.verify_live_event_quote_evidence(
        Path(evidence_directory), repository_root=Path(repository_root)
    )
    inventory = live.build_live_event_quote_inventory(
        Path(evidence_directory), repository_root=Path(repository_root)
    )
    if fixture_identity is not None and fixture_identity != manifest.event_id:
        raise CurrentSportyBetSemanticRegistryError("fixture identity differs from source event")
    if discovery_event is not None and discovery_event.event_id != manifest.event_id:
        raise CurrentSportyBetSemanticRegistryError("discovery event identity differs")
    if discovery_event is not None and (
        discovery_event.home_team_name != inventory.home_team_name
        or discovery_event.away_team_name != inventory.away_team_name
        or discovery_event.kickoff_utc != inventory.kickoff_utc
        or discovery_event.booking_status != inventory.booking_status
        or discovery_event.event_status != inventory.event_status
        or discovery_event.match_status != inventory.match_status
        or discovery_event.prematch_bookable_observed
        != inventory.prematch_bookable_observed
    ):
        raise CurrentSportyBetSemanticRegistryError(
            "discovery fixture identity differs from exact event-detail evidence"
        )
    evidence = ProviderEventEvidence(
        evidence_directory=Path(evidence_directory),
        repository_root=Path(repository_root),
        fixture_identity=manifest.event_id,
        fixture_identity_basis=fixture_identity_basis,
        inventory=inventory,
        discovery_event_id=None if discovery_event is None else discovery_event.event_id,
        discovery_source_page_num=None if discovery_event is None else discovery_event.source_page_num,
        discovery_source_raw_sha256=None if discovery_event is None else discovery_event.source_raw_sha256,
    )
    return replay_event_evidence(evidence)


def _policy_outcome(
    market_id: MarketId,
    selection: live.SportyBetLiveEventSelection,
    line: str | None,
) -> tuple[OutcomeId, str] | None:
    policy = _expected_policy(market_id)
    for provider_outcome_id, label_token, canonical_outcome in policy["outcomes"]:
        if selection.outcome_id != provider_outcome_id:
            continue
        expected_label = label_token
        if market_id is MarketId.TOTAL_GOALS:
            if line is None:
                return None
            expected_label = f"{label_token} {line}"
        elif market_id is MarketId.ASIAN_HANDICAP:
            if line is None:
                return None
            home = canonical_outcome is OutcomeId.HOME
            expected_label = f"{label_token} ({_format_ah_outcome_line(line, home=home)})"
        if selection.outcome_name != expected_label:
            return None
        return canonical_outcome, expected_label
    return None


def _matching_market_line(
    market_id: MarketId,
    selection: live.SportyBetLiveEventSelection,
) -> tuple[str | None, str] | None:
    policy = _expected_policy(market_id)
    if selection.market_id not in policy["market_ids"]:
        return None
    if market_id is MarketId.ASIAN_HANDICAP:
        try:
            line = _line_from_specifier(selection.specifier, "hcp")
        except CurrentSportyBetSemanticRegistryError:
            return None
        if line is None:
            return None
        if _signed_line_decimal(line) * 4 != (_signed_line_decimal(line) * 4).to_integral_value():
            return None
        expected_name = f"Asian Handicap {_format_ah_line(line)}"
        if selection.market_name != expected_name:
            return None
        return line, f"hcp={line}"
    if market_id is MarketId.TOTAL_GOALS:
        try:
            line = _line_from_specifier(selection.specifier, "total")
        except CurrentSportyBetSemanticRegistryError:
            return None
        if line is None or selection.market_name not in policy["market_names"]:
            return None
        if _line_decimal(line) % Decimal("0.5") != 0:
            return None
        return line, f"total={line}"
    if selection.market_name not in policy["market_names"]:
        return None
    if policy.get("specifier") is not None and selection.specifier != policy["specifier"]:
        return None
    if policy.get("specifier") is None and selection.specifier is not None:
        return None
    return None, "" if selection.specifier is None else selection.specifier


@dataclass(frozen=True)
class ProviderSemanticObservation:
    canonical_market_id: MarketId
    canonical_outcome_id: OutcomeId
    canonical_family: MarketFamily
    provider_market_id: str
    provider_market_name: str
    provider_specifier: str | None
    line: str | None
    provider_outcome_id: str
    provider_outcome_name: str
    bookable: bool
    bookability_basis: str
    provider_event_id: str
    fixture_identity: str
    fixture_identity_basis: str
    observed_at: datetime
    source_event_detail_raw_sha256: str
    source_manifest_sha256: str
    source_inventory_sha256: str
    source_contract_identity: str
    mapping_policy_identity: str
    settlement_class: SettlementClass
    settlement_equivalence_reviewed: bool
    ordinary_devig_partition_valid: bool
    event_set_overlaps: bool
    push_or_split_settlement: bool
    line_analytically_eligible: bool
    evidence_freshness: EvidenceFreshnessState

    def __post_init__(self) -> None:
        if type(self.canonical_market_id) is not MarketId:
            raise CurrentSportyBetSemanticRegistryError("canonical market must be typed")
        if type(self.canonical_outcome_id) is not OutcomeId:
            raise CurrentSportyBetSemanticRegistryError("canonical outcome must be typed")
        if type(self.canonical_family) is not MarketFamily:
            raise CurrentSportyBetSemanticRegistryError("canonical family must be typed")
        market = _coerce_market_id(self.canonical_market_id)
        if self.canonical_family is not MARKET_REGISTRY[market].family:
            raise CurrentSportyBetSemanticRegistryError("canonical family identity drifted")
        if self.canonical_outcome_id not in MARKET_REGISTRY[market].supported_outcomes:
            raise CurrentSportyBetSemanticRegistryError("canonical outcome identity drifted")
        _provider_id(self.provider_market_id, "provider_market_id")
        _provider_id(self.provider_outcome_id, "provider_outcome_id")
        _text(self.provider_market_name, "provider_market_name")
        _text(self.provider_outcome_name, "provider_outcome_name")
        if self.provider_specifier is not None:
            _text(self.provider_specifier, "provider_specifier", maximum=160)
        if self.line is not None:
            _text(self.line, "line", maximum=64)
        if type(self.bookable) is not bool or not self.bookability_basis:
            raise CurrentSportyBetSemanticRegistryError("bookability evidence is invalid")
        _event(self.provider_event_id)
        _text(self.fixture_identity, "fixture_identity")
        if self.fixture_identity != self.provider_event_id:
            raise CurrentSportyBetSemanticRegistryError("fixture identity is not source-bound")
        _text(self.fixture_identity_basis, "fixture_identity_basis")
        _utc(self.observed_at, "observed_at")
        _sha(self.source_event_detail_raw_sha256, "source_event_detail_raw_sha256")
        _sha(self.source_manifest_sha256, "source_manifest_sha256")
        _sha(self.source_inventory_sha256, "source_inventory_sha256")
        _text(self.source_contract_identity, "source_contract_identity")
        _text(self.mapping_policy_identity, "mapping_policy_identity")
        _enum_value(self.settlement_class, SettlementClass, "settlement_class")
        _enum_value(self.evidence_freshness, EvidenceFreshnessState, "evidence_freshness")
        if type(self.settlement_equivalence_reviewed) is not bool:
            raise CurrentSportyBetSemanticRegistryError("settlement review flag is invalid")
        if type(self.ordinary_devig_partition_valid) is not bool:
            raise CurrentSportyBetSemanticRegistryError("observation partition flag is invalid")
        if type(self.event_set_overlaps) is not bool:
            raise CurrentSportyBetSemanticRegistryError("observation overlap flag is invalid")
        if type(self.push_or_split_settlement) is not bool:
            raise CurrentSportyBetSemanticRegistryError("observation push/split flag is invalid")
        if type(self.line_analytically_eligible) is not bool:
            raise CurrentSportyBetSemanticRegistryError("line analytical flag is invalid")

        policy = _expected_policy(market)
        if self.provider_market_id not in policy["market_ids"]:
            raise CurrentSportyBetSemanticRegistryError("provider market ID is not reviewed")
        if market is MarketId.ASIAN_HANDICAP:
            try:
                parsed_line = _line_from_specifier(self.provider_specifier, "hcp")
            except CurrentSportyBetSemanticRegistryError as exc:
                raise CurrentSportyBetSemanticRegistryError(
                    "Asian Handicap specifier is not reviewed"
                ) from exc
            if parsed_line is None or parsed_line != self.line:
                raise CurrentSportyBetSemanticRegistryError("Asian Handicap line identity drifted")
            if _signed_line_decimal(parsed_line) * 4 != (
                _signed_line_decimal(parsed_line) * 4
            ).to_integral_value():
                raise CurrentSportyBetSemanticRegistryError("Asian Handicap line grammar drifted")
            if self.provider_market_name != f"Asian Handicap {_format_ah_line(parsed_line)}":
                raise CurrentSportyBetSemanticRegistryError("Asian Handicap market name drifted")
        elif market is MarketId.TOTAL_GOALS:
            try:
                parsed_line = _line_from_specifier(self.provider_specifier, "total")
            except CurrentSportyBetSemanticRegistryError as exc:
                raise CurrentSportyBetSemanticRegistryError(
                    "Total Goals specifier is not reviewed"
                ) from exc
            if parsed_line is None or parsed_line != self.line:
                raise CurrentSportyBetSemanticRegistryError("Total Goals line identity drifted")
            if _line_decimal(parsed_line) % Decimal("0.5") != 0:
                raise CurrentSportyBetSemanticRegistryError("Total Goals line grammar drifted")
            if self.provider_market_name not in policy["market_names"]:
                raise CurrentSportyBetSemanticRegistryError("Total Goals market name drifted")
        else:
            if self.provider_market_name not in policy["market_names"]:
                raise CurrentSportyBetSemanticRegistryError("provider market name is not reviewed")
            expected_specifier = policy.get("specifier")
            if self.provider_specifier != expected_specifier or self.line is not None:
                raise CurrentSportyBetSemanticRegistryError("provider specifier identity drifted")

        expected_outcome = next(
            (
                item
                for item in policy["outcomes"]
                if item[2] is self.canonical_outcome_id
            ),
            None,
        )
        if expected_outcome is None or self.provider_outcome_id != expected_outcome[0]:
            raise CurrentSportyBetSemanticRegistryError("provider outcome ID is not reviewed")
        expected_label = expected_outcome[1]
        if market is MarketId.TOTAL_GOALS:
            expected_label = f"{expected_label} {self.line}"
        elif market is MarketId.ASIAN_HANDICAP:
            expected_label = f"{expected_label} ({_format_ah_outcome_line(self.line, home=self.canonical_outcome_id is OutcomeId.HOME)})"
        if self.provider_outcome_name != expected_label:
            raise CurrentSportyBetSemanticRegistryError("provider outcome label is not reviewed")
        if self.source_contract_identity != live.EXPECTED_CONTRACT_SHA256:
            raise CurrentSportyBetSemanticRegistryError("event-detail contract identity drifted")
        if self.mapping_policy_identity != _mapping_policy(market):
            raise CurrentSportyBetSemanticRegistryError("mapping policy identity drifted")
        if self.settlement_class is not policy["settlement"]:
            raise CurrentSportyBetSemanticRegistryError("observation settlement class drifted")
        expected_ordinary_partition = policy["ordinary_partition"]
        expected_push_split = policy["push_split"]
        if market is MarketId.TOTAL_GOALS:
            if self.line is None:
                raise CurrentSportyBetSemanticRegistryError("Total Goals line is required")
            expected_ordinary_partition = _is_half_line(self.line)
            expected_push_split = not expected_ordinary_partition
        if self.ordinary_devig_partition_valid != expected_ordinary_partition:
            raise CurrentSportyBetSemanticRegistryError("observation partition topology drifted")
        if self.event_set_overlaps != policy["overlap"]:
            raise CurrentSportyBetSemanticRegistryError("observation overlap topology drifted")
        if self.push_or_split_settlement != expected_push_split:
            raise CurrentSportyBetSemanticRegistryError("observation push/split topology drifted")
        expected_line_eligibility = not (
            market is MarketId.TOTAL_GOALS and not _is_half_line(self.line or "")
        )
        if self.line_analytically_eligible != expected_line_eligibility:
            raise CurrentSportyBetSemanticRegistryError("line analytical eligibility drifted")

    @property
    def observation_identity(self) -> tuple[Any, ...]:
        return (
            self.canonical_market_id.value,
            self.canonical_outcome_id.value,
            self.provider_event_id,
            self.provider_market_id,
            self.provider_specifier,
            self.provider_outcome_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_market_id": self.canonical_market_id.value,
            "canonical_outcome_id": self.canonical_outcome_id.value,
            "canonical_family": self.canonical_family.value,
            "provider_market_id": self.provider_market_id,
            "provider_market_name": self.provider_market_name,
            "provider_specifier": self.provider_specifier,
            "line": self.line,
            "provider_outcome_id": self.provider_outcome_id,
            "provider_outcome_name": self.provider_outcome_name,
            "bookable": self.bookable,
            "bookability_basis": self.bookability_basis,
            "provider_event_id": self.provider_event_id,
            "fixture_identity": self.fixture_identity,
            "fixture_identity_basis": self.fixture_identity_basis,
            "observed_at": self.observed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source_event_detail_raw_sha256": self.source_event_detail_raw_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_inventory_sha256": self.source_inventory_sha256,
            "source_contract_identity": self.source_contract_identity,
            "mapping_policy_identity": self.mapping_policy_identity,
            "settlement_class": self.settlement_class.value,
            "settlement_equivalence_reviewed": self.settlement_equivalence_reviewed,
            "ordinary_devig_partition_valid": self.ordinary_devig_partition_valid,
            "event_set_overlaps": self.event_set_overlaps,
            "push_or_split_settlement": self.push_or_split_settlement,
            "line_analytically_eligible": self.line_analytically_eligible,
            "evidence_freshness": self.evidence_freshness.value,
        }


def _freshness(
    inventory: live.SportyBetLiveEventQuoteInventory,
    *,
    evaluation_time: datetime,
) -> EvidenceFreshnessState:
    evaluation = _utc(evaluation_time, "evaluation_time")
    observed = _utc(inventory.observed_at, "observed_at")
    kickoff = _utc(inventory.kickoff_utc, "kickoff_utc")
    if observed > evaluation:
        return EvidenceFreshnessState.FUTURE_DATED
    if evaluation - observed > timedelta(seconds=live.MAX_OBSERVATION_AGE_SECONDS):
        return EvidenceFreshnessState.STALE
    if not inventory.prematch_bookable_observed:
        return EvidenceFreshnessState.NOT_PREMATCH_BOOKABLE
    # Match the reviewed current-source contract exactly: an event at the
    # minimum lead boundary is already too close (``now + lead >= kickoff``).
    if kickoff - evaluation <= timedelta(seconds=live.MINIMUM_LEAD_SECONDS):
        return EvidenceFreshnessState.TOO_CLOSE_TO_KICKOFF
    return EvidenceFreshnessState.CURRENT


def _mapping_policy(market_id: MarketId) -> str:
    policy = _expected_policy(market_id)
    if policy.get("mapping_policy"):
        return str(policy["mapping_policy"])
    if market_id is MarketId.TOTAL_GOALS:
        return str(policy["mapping_policy"])
    return "PRB_EXACT_NATIVE_ID_NAME_SPECIFIER_OUTCOME_LABEL_V1"


def _settlement_reviewed(market_id: MarketId) -> bool:
    # PR252's reviewed mapping boundary already authorizes standard settlement
    # equivalence for every non-early market.  Early-payout rows additionally
    # bind to the exact reviewed Nigeria receipt above.
    return True


def _make_observations(
    evidence: ProviderEventEvidence,
    *,
    market_id: MarketId,
    evaluation_time: datetime,
) -> tuple[ProviderSemanticObservation, ...]:
    inventory = evidence.inventory
    policy = _expected_policy(market_id)
    freshness = _freshness(inventory, evaluation_time=evaluation_time)
    matches: list[ProviderSemanticObservation] = []
    for selection in inventory.selections:
        line_match = _matching_market_line(market_id, selection)
        if line_match is None:
            continue
        line, normalized_specifier = line_match
        outcome_match = _policy_outcome(market_id, selection, line)
        if outcome_match is None:
            continue
        canonical_outcome, _ = outcome_match
        # A provider row is still retained when stale/unbookable: it is durable
        # observed evidence, but it cannot issue CURRENT support.
        line_eligible = True
        if market_id is MarketId.TOTAL_GOALS:
            line_eligible = line is not None and _is_half_line(line)
        ordinary_partition = policy["ordinary_partition"] if market_id is not MarketId.TOTAL_GOALS else line_eligible
        push_split = policy["push_split"] if market_id is not MarketId.TOTAL_GOALS else not line_eligible
        matches.append(
            ProviderSemanticObservation(
                canonical_market_id=market_id,
                canonical_outcome_id=canonical_outcome,
                canonical_family=MARKET_REGISTRY[market_id].family,
                provider_market_id=selection.market_id,
                provider_market_name=selection.market_name,
                provider_specifier=selection.specifier,
                line=line,
                provider_outcome_id=selection.outcome_id,
                provider_outcome_name=selection.outcome_name,
                bookable=selection.bookable,
                bookability_basis=selection.bookability_basis,
                provider_event_id=selection.event_id,
                fixture_identity=evidence.fixture_identity,
                fixture_identity_basis=evidence.fixture_identity_basis,
                observed_at=inventory.observed_at,
                source_event_detail_raw_sha256=evidence.source_raw_sha256,
                source_manifest_sha256=evidence.source_manifest_sha256,
                source_inventory_sha256=evidence.source_inventory_sha256,
                source_contract_identity=live.EXPECTED_CONTRACT_SHA256,
                mapping_policy_identity=_mapping_policy(market_id),
                settlement_class=policy["settlement"],
                settlement_equivalence_reviewed=_settlement_reviewed(market_id),
                ordinary_devig_partition_valid=ordinary_partition,
                event_set_overlaps=policy["overlap"],
                push_or_split_settlement=push_split,
                line_analytically_eligible=line_eligible,
                evidence_freshness=freshness,
            )
        )
    return tuple(sorted(matches, key=lambda item: item.observation_identity))


def _has_exact_native_semantic_conflict(
    market_id: MarketId,
    evidence: ProviderEventEvidence,
) -> bool:
    """Detect drift hidden by exact-match filtering.

    A row under a reviewed native market ID is evidence about that market even
    when its name/specifier/outcome identity is wrong.  It must therefore make
    the coverage row conflicting rather than disappearing and allowing a
    different event's valid row to issue support.
    """

    policy = _expected_policy(market_id)
    native_ids = set(policy["market_ids"])
    for selection in evidence.inventory.selections:
        if selection.market_id not in native_ids:
            continue
        line_match = _matching_market_line(market_id, selection)
        if line_match is None:
            return True
        line, _normalized_specifier = line_match
        if _policy_outcome(market_id, selection, line) is None:
            return True
    return False


def _model_fields(market_id: MarketId) -> dict[str, Any]:
    definition = MARKET_REGISTRY[market_id]
    status = MODEL_STATUS_REGISTRY[market_id]
    return {
        "canonical_family": definition.family,
        "supported_canonical_outcomes": tuple(definition.supported_outcomes),
        "line_required": definition.line_required,
        "analytical_probability_capability": status.analytical_probability_capability,
        "probability_method": status.probability_method,
        "probability_input_namespace": status.probability_input_namespace,
        "required_probability_inputs": tuple(status.probability_inputs),
        "pricing_inputs": tuple(status.pricing_inputs),
        "missing_input_policy": status.missing_input_policy,
        "settlement_capability": status.settlement_capability,
        "calibration_status": status.calibration_status,
        "fresh_confirmation_status": status.fresh_confirmation_status,
        "pricing_authority": status.pricing_authority,
        "selection_authority": status.selection_authority,
    }


@dataclass(frozen=True)
class ProviderCoverageRecord:
    """One deterministic coverage row for one canonical ``MarketId``."""

    market_id: MarketId
    canonical_family: MarketFamily
    supported_canonical_outcomes: tuple[OutcomeId, ...]
    line_required: bool
    analytical_probability_capability: Any
    probability_method: str | None
    probability_input_namespace: Any
    required_probability_inputs: tuple[str, ...]
    pricing_inputs: tuple[str, ...]
    missing_input_policy: Any
    settlement_capability: Any
    calibration_status: Any
    fresh_confirmation_status: Any
    pricing_authority: Any
    selection_authority: Any
    provider_status: ProviderSemanticStatus
    provider_mapping_basis: str
    provider_market_patterns: tuple[str, ...]
    provider_outcome_patterns: tuple[str, ...]
    proven_line_policy: str | None
    proven_lines: tuple[str, ...]
    observations: tuple[ProviderSemanticObservation, ...]
    current_bookability_evidence: tuple[str, ...]
    settlement_class: SettlementClass
    ordinary_devig_partition_valid: bool
    event_set_overlaps: bool
    push_or_split_settlement: bool
    evidence_freshness: EvidenceFreshnessState
    research_readiness: str
    blocker: str | None

    def __post_init__(self) -> None:
        if type(self.market_id) is not MarketId:
            raise CurrentSportyBetSemanticRegistryError("coverage market must be typed")
        if type(self.canonical_family) is not MarketFamily:
            raise CurrentSportyBetSemanticRegistryError("coverage family must be typed")
        market = _coerce_market_id(self.market_id)
        expected = _model_fields(market)
        for field_name, expected_value in expected.items():
            actual_value = getattr(self, field_name)
            if type(actual_value) is not type(expected_value) or actual_value != expected_value:
                raise CurrentSportyBetSemanticRegistryError(
                    f"{market.value} model/canonical field {field_name} drifted"
                )
        if type(self.provider_status) is not ProviderSemanticStatus:
            raise CurrentSportyBetSemanticRegistryError("provider status must be typed")
        if type(self.supported_canonical_outcomes) is not tuple or not self.supported_canonical_outcomes:
            raise CurrentSportyBetSemanticRegistryError("canonical outcomes must be tuple")
        if any(type(item) is not ProviderSemanticObservation for item in self.observations):
            raise CurrentSportyBetSemanticRegistryError("observation type mismatch")
        if any(type(item) is not OutcomeId for item in self.supported_canonical_outcomes):
            raise CurrentSportyBetSemanticRegistryError("canonical outcome type mismatch")
        if type(self.observations) is not tuple:
            raise CurrentSportyBetSemanticRegistryError("observations must be tuple")
        identities = tuple(item.observation_identity for item in self.observations)
        if len(identities) != len(set(identities)):
            raise CurrentSportyBetSemanticRegistryError("duplicate semantic observation")
        if any(item.canonical_market_id is not market for item in self.observations):
            raise CurrentSportyBetSemanticRegistryError("observation market identity drifted")
        if type(self.provider_mapping_basis) is not str or not self.provider_mapping_basis:
            raise CurrentSportyBetSemanticRegistryError("provider mapping basis is required")
        if type(self.provider_market_patterns) is not tuple or type(self.provider_outcome_patterns) is not tuple:
            raise CurrentSportyBetSemanticRegistryError("provider patterns must be tuples")
        if type(self.proven_lines) is not tuple:
            raise CurrentSportyBetSemanticRegistryError("proven lines must be tuple")
        if type(self.current_bookability_evidence) is not tuple:
            raise CurrentSportyBetSemanticRegistryError("bookability references must be tuple")
        if self.blocker is not None:
            _text(self.blocker, "blocker", maximum=500)
        if self.provider_status is ProviderSemanticStatus.CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN and not self.blocker:
            raise CurrentSportyBetSemanticRegistryError("unproven row requires explicit blocker")
        policy = _expected_policy(market)
        if self.settlement_class is not policy["settlement"]:
            raise CurrentSportyBetSemanticRegistryError("settlement class drifted")
        expected_ordinary_partition = policy["ordinary_partition"]
        if market is MarketId.TOTAL_GOALS and self.observations:
            # Whole-goal totals retain a PUSH state; an aggregate row that
            # includes one cannot be treated as an ordinary binary partition.
            expected_ordinary_partition = all(
                item.line_analytically_eligible for item in self.observations
            )
        expected_push_split = policy["push_split"]
        if market is MarketId.TOTAL_GOALS and self.observations:
            expected_push_split = any(item.push_or_split_settlement for item in self.observations)
        if self.ordinary_devig_partition_valid != expected_ordinary_partition:
            raise CurrentSportyBetSemanticRegistryError("ordinary partition flag drifted")
        if self.event_set_overlaps != policy["overlap"] or self.push_or_split_settlement != expected_push_split:
            raise CurrentSportyBetSemanticRegistryError("settlement topology flag drifted")
        if self.pricing_authority.value != "NOT_AUTHORIZED" or self.selection_authority.value != "NOT_AUTHORIZED":
            raise CurrentSportyBetSemanticRegistryError("readiness row cannot grant authority")

    @property
    def canonical_market_id(self) -> MarketId:
        return self.market_id

    def to_dict(self) -> dict[str, Any]:
        def value(item: Any) -> Any:
            return item.value if isinstance(item, Enum) else item

        return {
            "canonical_market_id": self.market_id.value,
            "canonical_family": value(self.canonical_family),
            "supported_canonical_outcomes": [item.value for item in self.supported_canonical_outcomes],
            "line_required": self.line_required,
            "analytical_probability_capability": value(self.analytical_probability_capability),
            "probability_method": self.probability_method,
            "probability_input_namespace": value(self.probability_input_namespace),
            "required_probability_inputs": list(self.required_probability_inputs),
            "pricing_inputs": list(self.pricing_inputs),
            "missing_input_policy": value(self.missing_input_policy),
            "settlement_capability": value(self.settlement_capability),
            "calibration_status": value(self.calibration_status),
            "fresh_confirmation_status": value(self.fresh_confirmation_status),
            "pricing_authority": value(self.pricing_authority),
            "selection_authority": value(self.selection_authority),
            "provider_status": self.provider_status.value,
            "provider_mapping_basis": self.provider_mapping_basis,
            "provider_market_patterns": list(self.provider_market_patterns),
            "provider_outcome_patterns": list(self.provider_outcome_patterns),
            "proven_line_policy": self.proven_line_policy,
            "proven_lines": list(self.proven_lines),
            "observations": [item.to_dict() for item in self.observations],
            "current_bookability_evidence": list(self.current_bookability_evidence),
            "settlement_class": self.settlement_class.value,
            "ordinary_devig_partition_valid": self.ordinary_devig_partition_valid,
            "event_set_overlaps": self.event_set_overlaps,
            "push_or_split_settlement": self.push_or_split_settlement,
            "evidence_freshness": self.evidence_freshness.value,
            "research_readiness": self.research_readiness,
            "blocker": self.blocker,
        }


def _provider_patterns(market_id: MarketId) -> tuple[tuple[str, ...], tuple[str, ...]]:
    policy = _expected_policy(market_id)
    market_patterns = tuple(policy["market_ids"])
    outcomes = tuple(item[0] for item in policy["outcomes"])
    return market_patterns, outcomes


def build_coverage_record(
    market_id: MarketId,
    evidence: Sequence[ProviderEventEvidence],
    *,
    evaluation_time: datetime,
) -> ProviderCoverageRecord:
    """Build one row by replaying every supplied event evidence exactly."""

    market = _coerce_market_id(market_id)
    evaluation = _utc(evaluation_time, "evaluation_time")
    replayed = tuple(replay_event_evidence(item) for item in evidence)
    observations = tuple(
        observation
        for item in replayed
        for observation in _make_observations(item, market_id=market, evaluation_time=evaluation)
    )
    policy = _expected_policy(market)
    model = _model_fields(market)
    market_patterns, outcome_patterns = _provider_patterns(market)
    groups: dict[tuple[str, str | None, str], list[ProviderSemanticObservation]] = {}
    for observation in observations:
        groups.setdefault(
            (observation.provider_market_id, observation.provider_specifier, observation.provider_market_name),
            [],
        ).append(observation)
    complete_groups = [
        group
        for group in groups.values()
        if {item.provider_outcome_id for item in group}
        == {item[0] for item in policy["outcomes"]}
    ]
    current_groups = [
        group
        for group in complete_groups
        if all(
            item.bookable and item.evidence_freshness is EvidenceFreshnessState.CURRENT
            for item in group
        )
    ]
    # Different exact line values are expected for line markets.  A conflict
    # is only a disagreement for the same provider-native market/specifier,
    # such as a label or outcome-ID drift, never a second proven line.
    semantic_by_key: dict[tuple[str, str | None], set[tuple[str, tuple[tuple[str, str], ...]]]] = {}
    for group in groups.values():
        first = group[0]
        semantic_by_key.setdefault(
            (first.provider_market_id, first.provider_specifier), set()
        ).add(
            (
                first.provider_market_name,
                tuple(sorted((row.provider_outcome_id, row.provider_outcome_name) for row in group)),
            )
        )
    conflicting = any(len(signatures) > 1 for signatures in semantic_by_key.values()) or any(
        _has_exact_native_semantic_conflict(market, item) for item in replayed
    )
    if conflicting:
        status = ProviderSemanticStatus.CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN
        blocker = "CONFLICTING_CURRENT_PROVIDER_SEMANTICS"
        freshness_state = EvidenceFreshnessState.CONFLICTING
    elif current_groups:
        status = (
            ProviderSemanticStatus.SUPPORTED_WITH_EXACT_LINE_POLICY
            if market in {MarketId.ASIAN_HANDICAP, MarketId.TOTAL_GOALS}
            else ProviderSemanticStatus.SUPPORTED
        )
        blocker = None
        freshness_state = EvidenceFreshnessState.CURRENT
    elif observations:
        status = ProviderSemanticStatus.CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN
        freshness_state = observations[0].evidence_freshness
        blocker = (
            "INCOMPLETE_PROVIDER_OUTCOME_SET"
            if not complete_groups
            else "PROVIDER_EVIDENCE_NOT_CURRENT_BOOKABLE"
        )
    else:
        status = ProviderSemanticStatus.CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN
        freshness_state = EvidenceFreshnessState.NO_EVIDENCE
        blocker = "NO_EXACT_CURRENT_PROVIDER_SEMANTIC_EVIDENCE"
    proven_lines = tuple(
        sorted(
            {
                item.provider_specifier
                for item in observations
                if item.provider_specifier is not None
            }
        )
    )
    # A total integer line may be observed but is not analytical-ready under
    # the current half-goal-only model capability.
    line_blocked = market is MarketId.TOTAL_GOALS and any(
        item.line is not None and not item.line_analytically_eligible
        for item in observations
    )
    if status is not ProviderSemanticStatus.CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN and line_blocked:
        readiness = "SEMANTIC_READY_EXACT_LINE_MODEL_BLOCKED"
    elif status is ProviderSemanticStatus.CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN:
        readiness = "PROVIDER_UNPROVEN"
    else:
        readiness = "SEMANTIC_AND_MODEL_READY"
    if line_blocked and blocker is None:
        blocker = "OBSERVED_PROVIDER_LINE_OUTSIDE_CURRENT_MODEL_CAPABILITY"
    ordinary_partition = policy["ordinary_partition"]
    if market is MarketId.TOTAL_GOALS and observations:
        ordinary_partition = all(item.line_analytically_eligible for item in observations)
    push_split = policy["push_split"]
    if market is MarketId.TOTAL_GOALS and observations:
        push_split = any(item.push_or_split_settlement for item in observations)
    observed_market_names = tuple(sorted({item.provider_market_name for item in observations}))
    if observed_market_names:
        market_patterns = observed_market_names
    elif market is MarketId.ASIAN_HANDICAP:
        market_patterns = ("Asian Handicap <exact provider line>",)
    return ProviderCoverageRecord(
        market_id=market,
        **model,
        provider_status=status,
        provider_mapping_basis=(
            "EXACT_RETAINED_SOURCE_REPLAY_AND_PROVIDER_NATIVE_ID_NAME_OUTCOME_ID_LABEL"
        ),
        provider_market_patterns=market_patterns,
        provider_outcome_patterns=outcome_patterns,
        proven_line_policy=policy.get("line_policy"),
        proven_lines=proven_lines,
        observations=tuple(sorted(observations, key=lambda item: item.observation_identity)),
        current_bookability_evidence=tuple(
            sorted(
                {
                    item.provider_event_id
                    for item in observations
                    if item.bookable and item.evidence_freshness is EvidenceFreshnessState.CURRENT
                }
            )
        ),
        settlement_class=policy["settlement"],
        ordinary_devig_partition_valid=ordinary_partition,
        event_set_overlaps=policy["overlap"],
        push_or_split_settlement=push_split,
        evidence_freshness=freshness_state,
        research_readiness=readiness,
        blocker=blocker,
    )


_AUTHORITY = types.MappingProxyType(
    {
        "production_model": False,
        "production_probability": False,
        "phase6": False,
        "production_price_all": False,
        "production_market_router": False,
        "production_portfolio": False,
        "production_selection": False,
        "sportybet_execution": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
    }
)


@dataclass(frozen=True)
class CurrentSportyBetSemanticRegistry:
    schema_version: int
    dataset_name: str
    contract_version: int
    policy_id: str
    evaluation_time: datetime
    scan_cap: int
    scan_attempts: int
    coverage: tuple[ProviderCoverageRecord, ...]
    source_contract_identities: Mapping[str, str]
    authority: Mapping[str, bool]
    next_boundary: str = NEXT_BOUNDARY

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or self.dataset_name != DATASET_NAME or self.contract_version != CONTRACT_VERSION:
            raise CurrentSportyBetSemanticRegistryError("registry contract identity drifted")
        if self.policy_id != POLICY_ID:
            raise CurrentSportyBetSemanticRegistryError("registry policy identity drifted")
        if self.next_boundary != NEXT_BOUNDARY:
            raise CurrentSportyBetSemanticRegistryError("registry next boundary drifted")
        evaluation = _utc(self.evaluation_time, "evaluation_time")
        if type(self.scan_cap) is not int or self.scan_cap <= 0:
            raise CurrentSportyBetSemanticRegistryError("scan_cap is invalid")
        if type(self.scan_attempts) is not int or not 0 <= self.scan_attempts <= self.scan_cap:
            raise CurrentSportyBetSemanticRegistryError("scan_attempts is invalid")
        if type(self.coverage) is not tuple:
            raise CurrentSportyBetSemanticRegistryError("coverage must be tuple")
        if any(type(item) is not ProviderCoverageRecord for item in self.coverage):
            raise CurrentSportyBetSemanticRegistryError("coverage row type mismatch")
        ids = tuple(item.market_id for item in self.coverage)
        if len(ids) != len(set(ids)):
            raise CurrentSportyBetSemanticRegistryError("duplicate canonical market coverage")
        if set(ids) != set(MarketId):
            raise CurrentSportyBetSemanticRegistryError(
                f"canonical coverage is incomplete: missing={set(MarketId)-set(ids)}, extra={set(ids)-set(MarketId)}"
            )
        if dict(self.source_contract_identities) != dict(SOURCE_CONTRACT_IDENTITIES):
            raise CurrentSportyBetSemanticRegistryError("source contract identity drifted")
        if dict(self.authority) != dict(_AUTHORITY):
            raise CurrentSportyBetSemanticRegistryError("authority map is not fail-closed")
        object.__setattr__(self, "evaluation_time", evaluation)
        object.__setattr__(self, "source_contract_identities", types.MappingProxyType(dict(SOURCE_CONTRACT_IDENTITIES)))
        object.__setattr__(self, "authority", _AUTHORITY)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "contract_version": self.contract_version,
            "policy_id": self.policy_id,
            "evaluation_time": self.evaluation_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "scan_cap": self.scan_cap,
            "scan_attempts": self.scan_attempts,
            "coverage": [item.to_dict() for item in sorted(self.coverage, key=lambda item: item.market_id.value)],
            "source_contract_identities": dict(sorted(self.source_contract_identities.items())),
            "authority": dict(sorted(self.authority.items())),
            "next_boundary": self.next_boundary,
        }

    @property
    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict(), newline=True)

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    @property
    def registry_sha256(self) -> str:
        return self.canonical_sha256

    def readiness_matrix(self) -> tuple[dict[str, Any], ...]:
        return tuple(item.to_dict() for item in sorted(self.coverage, key=lambda item: item.market_id.value))


# Alias used by callers that describe the object as a registry rather than a
# current-provider registry.
SportyBetSemanticRegistry = CurrentSportyBetSemanticRegistry


def build_registry(
    evidence: Sequence[ProviderEventEvidence],
    *,
    evaluation_time: datetime,
    scan_cap: int = 20,
    scan_attempts: int | None = None,
) -> CurrentSportyBetSemanticRegistry:
    evaluation = _utc(evaluation_time, "evaluation_time")
    rows = tuple(
        build_coverage_record(
            market_id,
            evidence,
            evaluation_time=evaluation,
        )
        for market_id in MarketId
    )
    return CurrentSportyBetSemanticRegistry(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        contract_version=CONTRACT_VERSION,
        policy_id=POLICY_ID,
        evaluation_time=evaluation,
        scan_cap=scan_cap,
        scan_attempts=len(evidence) if scan_attempts is None else scan_attempts,
        coverage=rows,
        source_contract_identities=SOURCE_CONTRACT_IDENTITIES,
        authority=_AUTHORITY,
    )


# Descriptive aliases keep the additive boundary discoverable without creating
# a second implementation or a second canonical-market list.
build_current_sportybet_semantic_registry = build_registry


MAX_EVENT_DETAIL_READS = 20
SCAN_POLICY_ID = "PRB_DETERMINISTIC_PREMATCH_BOOKABLE_DISCOVERY_ORDER_CAP20_V1"
MAX_DISCOVERY_PAGES = discovery.MAX_PAGES


@dataclass(frozen=True)
class BoundedDiscoveryCapture:
    """A bounded prefix of the reviewed discovery endpoint.

    The frozen discovery reconciliation contract requires a terminal empty page
    and therefore cannot represent a still-populated current provider after its
    page cap.  PR-B keeps that contract untouched and records a separate,
    source-bound bounded prefix instead of retrying past the cap.
    """

    pages: tuple[discovery.SportyBetDiscoveryPage, ...]
    events: tuple[discovery.SportyBetDiscoveredEvent, ...]
    raw_pages: tuple[bytes, ...]
    terminal_empty_page_observed: bool

    def __post_init__(self) -> None:
        if type(self.pages) is not tuple or type(self.events) is not tuple or type(self.raw_pages) is not tuple:
            raise CurrentSportyBetSemanticRegistryError("bounded discovery rows must be tuples")
        if len(self.pages) != len(self.raw_pages) or not self.pages:
            raise CurrentSportyBetSemanticRegistryError("bounded discovery page evidence is invalid")
        if tuple(item.page_num for item in self.pages) != tuple(range(1, len(self.pages) + 1)):
            raise CurrentSportyBetSemanticRegistryError("bounded discovery pages are not contiguous")
        if any(type(raw) is not bytes or not raw for raw in self.raw_pages):
            raise CurrentSportyBetSemanticRegistryError("bounded discovery raw page is invalid")
        if any(type(item) is not discovery.SportyBetDiscoveredEvent for item in self.events):
            raise CurrentSportyBetSemanticRegistryError("bounded discovery event is invalid")
        if type(self.terminal_empty_page_observed) is not bool:
            raise CurrentSportyBetSemanticRegistryError("bounded discovery terminal flag is invalid")

    @property
    def canonical_sha256(self) -> str:
        value = {
            "source_contract_sha256": discovery.EXPECTED_CONTRACT_SHA256,
            "pages": [item.to_dict() for item in self.pages],
            "events": [item.to_dict() for item in self.events],
            "terminal_empty_page_observed": self.terminal_empty_page_observed,
        }
        return hashlib.sha256(_canonical_bytes(value)).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": discovery.DISCOVERY_DATASET_NAME,
            "source_contract_sha256": discovery.EXPECTED_CONTRACT_SHA256,
            "pages": [item.to_dict() for item in self.pages],
            "events": [item.to_dict() for item in self.events],
            "terminal_empty_page_observed": self.terminal_empty_page_observed,
            "canonical_sha256": self.canonical_sha256,
        }


def _dedupe_bounded_discovery_events(
    events: Sequence[discovery.SportyBetDiscoveredEvent],
) -> tuple[discovery.SportyBetDiscoveredEvent, ...]:
    """Deduplicate a live paginated prefix without weakening fixture identity.

    The reviewed discovery helper intentionally requires duplicate rows to have
    byte-equivalent semantic identity. A bounded live prefix is observed over
    several requests, though, so availability/status fields for the same event
    can legitimately move between pages while the scan is in flight. PR-B
    keeps the frozen helper unchanged and uses the newest observation only when
    the stable fixture identity still agrees exactly.
    """

    by_id: dict[str, discovery.SportyBetDiscoveredEvent] = {}
    for event in events:
        existing = by_id.get(event.event_id)
        if existing is None:
            by_id[event.event_id] = event
            continue
        stable_existing = (
            existing.event_id,
            existing.home_team_name,
            existing.away_team_name,
            existing.competition_name,
            existing.kickoff_utc,
        )
        stable_incoming = (
            event.event_id,
            event.home_team_name,
            event.away_team_name,
            event.competition_name,
            event.kickoff_utc,
        )
        if stable_existing != stable_incoming:
            raise CurrentSportyBetSemanticRegistryError(
                f"conflicting bounded discovery fixture identity: {event.event_id}"
            )
        if event.source_observed_at == existing.source_observed_at:
            if event.identity_payload != existing.identity_payload:
                raise CurrentSportyBetSemanticRegistryError(
                    f"ambiguous bounded discovery state collision: {event.event_id}"
                )
            continue
        if event.source_observed_at > existing.source_observed_at:
            by_id[event.event_id] = event
    return tuple(by_id[key] for key in sorted(by_id))


def capture_bounded_current_event_discovery(
    *,
    max_pages: int = MAX_DISCOVERY_PAGES,
) -> BoundedDiscoveryCapture:
    """Capture at most ``max_pages`` using the reviewed discovery parser.

    This helper intentionally uses the existing request/parser primitives and
    never calls the frozen terminal-empty reconciliation helper.  A populated
    cap is a valid bounded prefix, not permission for hidden pagination.
    """

    discovery.validate_current_event_discovery_contract()
    if type(max_pages) is not int or not 1 <= max_pages <= discovery.MAX_PAGES:
        raise CurrentSportyBetSemanticRegistryError("max_pages exceeds reviewed discovery bound")
    pages: list[discovery.SportyBetDiscoveryPage] = []
    raw_pages: list[bytes] = []
    events: list[discovery.SportyBetDiscoveredEvent] = []
    terminal = False
    for page_num in range(1, max_pages + 1):
        raw, status, observed_at = discovery._network_fetch_page(page_num)
        if status != 200:
            raise CurrentSportyBetSemanticRegistryError(
                f"SportyBet discovery returned HTTP {status}"
            )
        page, page_events = discovery._parse_page(
            raw,
            page_num=page_num,
            observed_at=observed_at,
        )
        pages.append(page)
        raw_pages.append(raw)
        events.extend(page_events)
        if not page_events:
            terminal = True
            break
    return BoundedDiscoveryCapture(
        pages=tuple(pages),
        events=_dedupe_bounded_discovery_events(events),
        raw_pages=tuple(raw_pages),
        terminal_empty_page_observed=terminal,
    )


def scan_current_sportybet_semantic_registry(
    *,
    repository_root: Path,
    output_directory: Path,
    evaluation_time: datetime | None = None,
    head_sha: str | None = None,
    base_sha: str | None = None,
) -> tuple[CurrentSportyBetSemanticRegistry, Path]:
    """Run the bounded anonymous discovery/detail scan and retain all evidence."""

    root = Path(repository_root).resolve(strict=True)
    output = Path(output_directory).resolve()
    if output == root:
        raise CurrentSportyBetSemanticRegistryError("proof output must not be repository root")
    output.mkdir(parents=True, exist_ok=True)
    discovery_capture = capture_bounded_current_event_discovery()
    evaluation_override = (
        _utc(evaluation_time, "evaluation_time")
        if evaluation_time is not None
        else None
    )
    candidate_time = evaluation_override or datetime.now(timezone.utc)
    discovery_candidates = sorted(
        (
            item
            for item in discovery_capture.events
            if item.prematch_bookable_observed
            and item.kickoff_utc - candidate_time > timedelta(seconds=live.MINIMUM_LEAD_SECONDS)
        ),
        key=lambda item: (item.kickoff_utc, item.event_id),
    )[:MAX_EVENT_DETAIL_READS]
    # The live-or-prematch endpoint can legitimately contain only in-play rows
    # at a given observation time.  Reuse PR258's already-reviewed anonymous
    # upcoming-event discovery as a bounded, discovery-only fallback; it does
    # not create/reload a share code or select by odds.
    candidate_rows: list[tuple[str, discovery.SportyBetDiscoveredEvent | None, str]] = [
        (item.event_id, item, "CURRENT_EVENT_DISCOVERY") for item in discovery_candidates
    ]
    fallback_error: str | None = None
    if not candidate_rows:
        from scripts import run_pr258_sportybet_live_transport_proof as pr258_proof

        try:
            upcoming_ids, _upcoming_metadata = pr258_proof._fetch_upcoming_sample(output)
            candidate_rows = [
                (event_id, None, "REVIEWED_UPCOMING_DISCOVERY_FALLBACK")
                for event_id in upcoming_ids[:MAX_EVENT_DETAIL_READS]
            ]
        except (pr258_proof.PR258LiveTransportProofError, OSError) as exc:
            # This fallback is best-effort discovery only. Keep its failure in
            # proof metadata and preserve an explicit all-unproven matrix.
            fallback_error = type(exc).__name__
    evidence_rows: list[ProviderEventEvidence] = []
    attempts: list[dict[str, Any]] = []
    for event_id, candidate, candidate_source in candidate_rows:
        try:
            event_dir, _manifest = live.capture_live_event_quote_evidence(
                event_id=event_id,
                repository_root=root,
                execute_live_network=True,
            )
            evidence_rows.append(
                load_provider_event_evidence(
                    event_dir,
                    repository_root=root,
                    discovery_event=candidate,
                )
            )
            attempts.append(
                {"event_id": event_id, "status": "CAPTURED", "candidate_source": candidate_source}
            )
        except (live.SportyBetLiveEventQuoteEvidenceError, OSError) as exc:
            # Preserve failed attempts; do not retry silently. Contract or
            # replay drift raises rather than being disguised as provider
            # absence.
            attempts.append(
                {
                    "event_id": event_id,
                    "status": "FAILED",
                    "reason": type(exc).__name__,
                    "candidate_source": candidate_source,
                }
            )
    # A live current claim is evaluated at the end of the reads it certifies,
    # not at the beginning of discovery. This avoids falsely classifying the
    # retained captures as future-dated merely because the scan took time.
    registry_time = evaluation_override or datetime.now(timezone.utc)
    registry = build_registry(
        evidence_rows,
        evaluation_time=registry_time,
        scan_cap=MAX_EVENT_DETAIL_READS,
        scan_attempts=len(candidate_rows),
    )
    # Copy exact source evidence used by the proof; no generated cache is
    # committed to the repository and no successful event hides failed reads.
    retained = output / "event-evidence"
    retained.mkdir(parents=True, exist_ok=True)
    retained_discovery = output / "discovery-evidence"
    if retained_discovery.exists():
        shutil.rmtree(retained_discovery)
    retained_discovery.mkdir(parents=True, exist_ok=True)
    for page, raw in zip(discovery_capture.pages, discovery_capture.raw_pages, strict=True):
        (retained_discovery / f"page-{page.page_num:03d}.raw.json").write_bytes(raw)
    (retained_discovery / "manifest.json").write_bytes(
        _canonical_bytes(discovery_capture.to_dict(), newline=True)
    )
    for row in evidence_rows:
        destination = retained / row.evidence_directory.name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(row.evidence_directory, destination)
    proof = {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "policy_id": POLICY_ID,
        "scan_policy_id": SCAN_POLICY_ID,
        "head_sha": head_sha,
        "base_sha": base_sha,
        "capture_evaluation_time": registry.to_dict()["evaluation_time"],
        "discovery_directory": retained_discovery.as_posix(),
        "discovery_manifest_sha256": discovery_capture.canonical_sha256,
        "discovery_event_count": len(discovery_capture.events),
        "discovery_pages_fetched": len(discovery_capture.pages),
        "discovery_terminal_empty_page_observed": discovery_capture.terminal_empty_page_observed,
        "attempts": attempts,
        "upcoming_fallback_error": fallback_error,
        "registry": registry.to_dict(),
        "registry_sha256": registry.canonical_sha256,
        "source_contract_identities": dict(SOURCE_CONTRACT_IDENTITIES),
        "authority": dict(_AUTHORITY),
        "retained_event_evidence": [row.to_dict() for row in evidence_rows],
    }
    registry_path = output / "registry.json"
    proof_path = output / "proof.json"
    registry_path.write_bytes(registry.canonical_bytes)
    proof_path.write_bytes(_canonical_bytes(proof, newline=True))
    return registry, proof_path


scan_current_provider_semantic_registry = scan_current_sportybet_semantic_registry


def validate_registry(registry: CurrentSportyBetSemanticRegistry) -> str:
    """Re-run immutable contract validation and return its canonical digest."""

    if type(registry) is not CurrentSportyBetSemanticRegistry:
        raise CurrentSportyBetSemanticRegistryError("registry type mismatch")
    # Reconstructing from the canonical object is intentionally done by the
    # dataclass invariants; this extra check catches mutable mapping tampering.
    if registry.canonical_sha256 != hashlib.sha256(registry.canonical_bytes).hexdigest():
        raise CurrentSportyBetSemanticRegistryError("registry digest is unstable")
    return registry.canonical_sha256


__all__ = [
    "CURRENT_PROVIDER_UNAVAILABLE",
    "CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN",
    "CONTRACT_VERSION",
    "BoundedDiscoveryCapture",
    "CurrentSportyBetSemanticRegistry",
    "CurrentSportyBetSemanticRegistryError",
    "DATASET_NAME",
    "EvidenceFreshnessState",
    "MAX_EVENT_DETAIL_READS",
    "MAX_DISCOVERY_PAGES",
    "NEXT_BOUNDARY",
    "POLICY_ID",
    "ProviderCoverageRecord",
    "ProviderEventEvidence",
    "ProviderSemanticObservation",
    "ProviderSemanticStatus",
    "SCAN_POLICY_ID",
    "SOURCE_CONTRACT_IDENTITIES",
    "SCHEMA_VERSION",
    "SettlementClass",
    "SportyBetSemanticRegistry",
    "build_coverage_record",
    "build_current_sportybet_semantic_registry",
    "build_registry",
    "capture_bounded_current_event_discovery",
    "canonical_json_bytes",
    "load_provider_event_evidence",
    "provider_policy",
    "replay_event_evidence",
    "scan_current_sportybet_semantic_registry",
    "scan_current_provider_semantic_registry",
    "validate_registry",
]
