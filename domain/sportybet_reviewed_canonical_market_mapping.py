"""Fail-closed SportyBet provider-native -> ATHENA canonical market mapping."""
from __future__ import annotations

import dataclasses
from decimal import Decimal, InvalidOperation
import enum
import hashlib
import json
import math
import re
import types
from pathlib import Path
from typing import Any, Mapping, Sequence

from domain import sportybet_fotmob_full_utc_reconciliation as reconciliation
from domain import sportybet_fotmob_full_utc_reconciliation_receipt as receipts
from domain import sportybet_user_controlled_native_inventory as native
from domain.markets import MARKET_REGISTRY, InvalidSelectionError, MarketId, OutcomeId, make_selection
from domain.sportybet_early_payout_settlement import (
    ONE_UP_PROVIDER_MAPPED_MARKET_ID,
    SportyBetEarlyPayoutSettlementReceipt,
    TWO_UP_PROVIDER_MAPPED_MARKET_ID,
    canonical_sportybet_early_payout_settlement_receipt_bytes,
    reviewed_sportybet_early_payout_settlement_receipt,
    sha256_sportybet_early_payout_settlement_receipt,
)
from domain.sportybet_provider_native_inventory import NativeAvailability, NativeSelection, validate_odds

SCHEMA_VERSION = 1
DATASET_NAME = "athena-sportybet-reviewed-canonical-market-mapping-v1"
PROVIDER = "SportyBet"
STATUS = "REVIEWED_PROVIDER_NATIVE_CANONICAL_MARKET_MAPPING"
REVIEW_BASIS = "EXPLICIT_REVIEW_OF_EXACT_PROVIDER_NATIVE_IDENTITY_AND_LABELS"
MAX_CANONICAL_BYTES = 2 * 1024 * 1024

TARGET_MARKET_IDS = (
    MarketId.MATCH_RESULT,
    MarketId.TOTAL_GOALS,
    MarketId.DOUBLE_CHANCE,
    MarketId.ASIAN_HANDICAP,
    MarketId.DRAW_OR_OVER_2_5,
    MarketId.AWAY_OR_OVER_2_5,
    MarketId.HOME_OR_OVER_2_5,
    MarketId.BTTS,
    MarketId.HOME_WIN_TO_NIL,
    MarketId.AWAY_WIN_TO_NIL,
    MarketId.HOME_WIN_EITHER_HALF,
    MarketId.AWAY_WIN_EITHER_HALF,
    MarketId.DRAW_NO_BET,
    MarketId.MATCH_RESULT_1UP,
    MarketId.MATCH_RESULT_2UP,
)
_EARLY = frozenset({MarketId.MATCH_RESULT_1UP, MarketId.MATCH_RESULT_2UP})
_LINE_KEYS = {MarketId.TOTAL_GOALS: "total", MarketId.ASIAN_HANDICAP: "hcp"}
_LINE_RE = re.compile(r"^(total|hcp)=(-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?)$", re.ASCII)
_PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9_.:+/=-]{1,160}$", re.ASCII)
_HASH_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)


class SportyBetReviewedCanonicalMarketMappingError(ValueError):
    pass


class SettlementEquivalenceAuthority(str, enum.Enum):
    REVIEWED_STANDARD_SETTLEMENT_EQUIVALENCE = "REVIEWED_STANDARD_SETTLEMENT_EQUIVALENCE"
    REVIEWED_SPORTYBET_EARLY_PAYOUT_SETTLEMENT_EQUIVALENCE = (
        "REVIEWED_SPORTYBET_EARLY_PAYOUT_SETTLEMENT_EQUIVALENCE"
    )
    PROVIDER_PROMOTION_RULES_UNPROVEN = "PROVIDER_PROMOTION_RULES_UNPROVEN"


def _fail(message: str) -> SportyBetReviewedCanonicalMarketMappingError:
    return SportyBetReviewedCanonicalMarketMappingError(message)


def _text(value: Any, label: str, *, maximum: int = 512) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > maximum:
        raise _fail(f"{label} must be an exact non-empty trimmed string")
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise _fail(f"{label} contains control characters")
    return value


def _provider_id(value: Any, label: str) -> str:
    if type(value) is not str or _PROVIDER_ID_RE.fullmatch(value) is None:
        raise _fail(f"{label} is not a safe provider-native ID")
    return value


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _HASH_RE.fullmatch(value) is None:
        raise _fail(f"{label} is invalid")
    return value


def _json_bytes(value: Any, label: str) -> bytes:
    try:
        data = (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    except (TypeError, ValueError, OverflowError) as exc:
        raise _fail(f"{label} canonical serialization failed") from exc
    if not data or len(data) > MAX_CANONICAL_BYTES:
        raise _fail(f"{label} canonical payload exceeds reviewed bounds")
    return data


def _assert_target_registry() -> None:
    if len(TARGET_MARKET_IDS) != 15 or len(set(TARGET_MARKET_IDS)) != 15:
        raise _fail("reviewed target market registry must contain exactly 15 unique markets")
    if set(TARGET_MARKET_IDS) != set(MARKET_REGISTRY):
        raise _fail("ATHENA canonical market registry drifted from reviewed 15-market scope")


def _line(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _fail("canonical_line must be finite numeric or None")
    result = float(value)
    if not math.isfinite(result):
        raise _fail("canonical_line must be finite numeric or None")
    return result


@dataclasses.dataclass(frozen=True)
class ReviewedCanonicalMappingDecision:
    event_id: str
    provider_market_id: str
    provider_market_name: str
    provider_specifier: str | None
    provider_outcome_id: str
    provider_selection_label: str
    canonical_market_id: MarketId
    canonical_outcome_id: OutcomeId
    canonical_line: float | None = None
    review_basis: str = REVIEW_BASIS

    def __post_init__(self) -> None:
        _provider_id(self.event_id, "event_id")
        _provider_id(self.provider_market_id, "provider_market_id")
        _provider_id(self.provider_outcome_id, "provider_outcome_id")
        _text(self.provider_market_name, "provider_market_name")
        _text(self.provider_selection_label, "provider_selection_label")
        if self.provider_specifier is not None:
            _text(self.provider_specifier, "provider_specifier")
        if type(self.canonical_market_id) is not MarketId or self.canonical_market_id not in TARGET_MARKET_IDS:
            raise _fail("canonical_market_id is outside reviewed 15-market scope")
        if type(self.canonical_outcome_id) is not OutcomeId:
            raise _fail("canonical_outcome_id must be exact OutcomeId")
        try:
            checked = make_selection(self.canonical_market_id, self.canonical_outcome_id, line=_line(self.canonical_line))
        except InvalidSelectionError as exc:
            raise _fail(str(exc)) from exc
        if self.review_basis != REVIEW_BASIS:
            raise _fail("review_basis mismatch")
        object.__setattr__(self, "canonical_line", checked.line)

    @property
    def native_identity(self) -> tuple[str, str, str | None, str]:
        return (self.event_id, self.provider_market_id, self.provider_specifier, self.provider_outcome_id)

    @property
    def canonical_identity(self) -> tuple[MarketId, OutcomeId, float | None]:
        return (self.canonical_market_id, self.canonical_outcome_id, self.canonical_line)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "provider_market_id": self.provider_market_id,
            "provider_market_name": self.provider_market_name,
            "provider_specifier": self.provider_specifier,
            "provider_outcome_id": self.provider_outcome_id,
            "provider_selection_label": self.provider_selection_label,
            "canonical_market_id": self.canonical_market_id.value,
            "canonical_outcome_id": self.canonical_outcome_id.value,
            "canonical_line": self.canonical_line,
            "review_basis": self.review_basis,
        }


def _decisions(values: Sequence[ReviewedCanonicalMappingDecision]) -> tuple[ReviewedCanonicalMappingDecision, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise _fail("review_decisions must be a non-empty sequence")
    rows = tuple(values)
    if not rows or any(type(x) is not ReviewedCanonicalMappingDecision for x in rows):
        raise _fail("review_decisions contain an invalid item")
    native_keys = [x.native_identity for x in rows]
    canonical_keys = [x.canonical_identity for x in rows]
    if len(native_keys) != len(set(native_keys)):
        raise _fail("duplicate provider-native review decision identity")
    if len(canonical_keys) != len(set(canonical_keys)):
        raise _fail("multiple provider selections cannot claim the same canonical selection identity")
    return tuple(sorted(rows, key=lambda x: (x.event_id, x.provider_market_id, x.provider_specifier or "", x.provider_outcome_id)))


def canonical_review_decisions_bytes(values: Sequence[ReviewedCanonicalMappingDecision]) -> bytes:
    return _json_bytes([x.to_dict() for x in _decisions(values)], "review decisions")


def _validate_line_semantics(selection: NativeSelection, decision: ReviewedCanonicalMappingDecision) -> None:
    market = decision.canonical_market_id
    if market in _LINE_KEYS:
        if selection.specifier is None:
            raise _fail(f"{market.value} requires an exact provider line specifier")
        match = _LINE_RE.fullmatch(selection.specifier)
        if match is None or match.group(1) != _LINE_KEYS[market]:
            raise _fail(f"provider specifier does not prove {market.value} line semantics")
        try:
            provider_line = Decimal(match.group(2))
            canonical_line = Decimal(str(decision.canonical_line))
        except (InvalidOperation, ValueError) as exc:
            raise _fail("provider/canonical line cannot be compared exactly") from exc
        if not provider_line.is_finite() or provider_line != canonical_line:
            raise _fail("provider specifier line does not equal reviewed canonical line")
    elif selection.specifier is not None:
        raise _fail("a provider specifier cannot be absorbed into a non-line canonical market")


@dataclasses.dataclass(frozen=True)
class MappedSportyBetCanonicalSelection:
    provider_selection_sha256: str
    event_id: str
    provider_market_id: str
    provider_market_name: str
    provider_specifier: str | None
    provider_outcome_id: str
    provider_selection_label: str
    availability: str
    odds_raw: str
    odds_decimal: str
    provider_quote_at: None
    provider_snapshot_id: None
    canonical_market_id: MarketId
    canonical_outcome_id: OutcomeId
    canonical_line: float | None
    canonical_display_label: str
    canonical_selection_display_name: str
    settlement_equivalence_authority: SettlementEquivalenceAuthority
    settlement_evidence_sha256: str | None
    bookmaker_equivalence_authorized: bool
    canonical_market_mapping_authorized: bool
    fresh_price_authorized: bool
    href: str

    def __post_init__(self) -> None:
        _sha(self.provider_selection_sha256, "provider_selection_sha256")
        _provider_id(self.event_id, "event_id")
        _provider_id(self.provider_market_id, "provider_market_id")
        _provider_id(self.provider_outcome_id, "provider_outcome_id")
        _text(self.provider_market_name, "provider_market_name")
        _text(self.provider_selection_label, "provider_selection_label")
        if self.provider_specifier is not None:
            _text(self.provider_specifier, "provider_specifier")
        if type(self.canonical_market_id) is not MarketId or self.canonical_market_id not in TARGET_MARKET_IDS:
            raise _fail("mapped canonical market is outside reviewed scope")
        if type(self.canonical_outcome_id) is not OutcomeId:
            raise _fail("mapped canonical outcome must be exact OutcomeId")
        try:
            canonical = make_selection(self.canonical_market_id, self.canonical_outcome_id, line=self.canonical_line)
        except InvalidSelectionError as exc:
            raise _fail(str(exc)) from exc
        if (self.canonical_display_label, self.canonical_selection_display_name) != (canonical.display_label, canonical.selection_display_name):
            raise _fail("mapped canonical display fields mismatch registry")
        early = self.canonical_market_id in _EARLY
        reviewed_early = early and self.settlement_evidence_sha256 is not None
        expected_authority = (
            SettlementEquivalenceAuthority.REVIEWED_SPORTYBET_EARLY_PAYOUT_SETTLEMENT_EQUIVALENCE
            if reviewed_early
            else (
                SettlementEquivalenceAuthority.PROVIDER_PROMOTION_RULES_UNPROVEN
                if early
                else SettlementEquivalenceAuthority.REVIEWED_STANDARD_SETTLEMENT_EQUIVALENCE
            )
        )
        if self.settlement_equivalence_authority is not expected_authority:
            raise _fail("settlement equivalence authority mismatch")
        expected_equivalence = not early or reviewed_early
        if self.bookmaker_equivalence_authorized is not expected_equivalence:
            raise _fail("bookmaker equivalence authority mismatch")
        if reviewed_early:
            expected_provider_market_id = {
                MarketId.MATCH_RESULT_1UP: ONE_UP_PROVIDER_MAPPED_MARKET_ID,
                MarketId.MATCH_RESULT_2UP: TWO_UP_PROVIDER_MAPPED_MARKET_ID,
            }[self.canonical_market_id]
            if self.provider_market_id != expected_provider_market_id:
                raise _fail(
                    "early-payout settlement equivalence requires the exact "
                    "reviewed provider mapped market identity"
                )
            expected_receipt = reviewed_sportybet_early_payout_settlement_receipt()
            expected_sha = sha256_sportybet_early_payout_settlement_receipt(
                expected_receipt
            )
            if self.settlement_evidence_sha256 != expected_sha:
                raise _fail("early-payout settlement evidence identity mismatch")
        elif self.settlement_evidence_sha256 is not None:
            raise _fail("settlement evidence is not legal for this mapping state")
        if self.canonical_market_mapping_authorized is not True or self.fresh_price_authorized is not False:
            raise _fail("mapped authority flags violate reviewed boundary")
        if self.provider_quote_at is not None or self.provider_snapshot_id is not None:
            raise _fail("provider quote timestamp/snapshot must remain null")
        _text(self.href, "href", maximum=4096)
        if self.availability not in {x.value for x in NativeAvailability}:
            raise _fail("mapped availability is invalid")
        try:
            odds_raw, odds_decimal = validate_odds(self.odds_raw)
        except Exception as exc:
            raise _fail("mapped odds are invalid") from exc
        if (odds_raw, odds_decimal) != (self.odds_raw, self.odds_decimal):
            raise _fail("mapped odds normalization mismatch")

    def to_dict(self) -> dict[str, Any]:
        result = {
            "provider_selection_sha256": self.provider_selection_sha256,
            "event_id": self.event_id,
            "provider_market_id": self.provider_market_id,
            "provider_market_name": self.provider_market_name,
            "provider_specifier": self.provider_specifier,
            "provider_outcome_id": self.provider_outcome_id,
            "provider_selection_label": self.provider_selection_label,
            "availability": self.availability,
            "odds_raw": self.odds_raw,
            "odds_decimal": self.odds_decimal,
            "provider_quote_at": None,
            "provider_snapshot_id": None,
            "canonical_market_id": self.canonical_market_id.value,
            "canonical_outcome_id": self.canonical_outcome_id.value,
            "canonical_line": self.canonical_line,
            "canonical_display_label": self.canonical_display_label,
            "canonical_selection_display_name": self.canonical_selection_display_name,
            "settlement_equivalence_authority": self.settlement_equivalence_authority.value,
            "bookmaker_equivalence_authorized": self.bookmaker_equivalence_authorized,
            "canonical_market_mapping_authorized": True,
            "fresh_price_authorized": False,
            "href": self.href,
        }
        if self.settlement_evidence_sha256 is not None:
            result["settlement_evidence_sha256"] = self.settlement_evidence_sha256
        return result


def _validated_early_payout_evidence(
    receipt: SportyBetEarlyPayoutSettlementReceipt | None,
    receipt_bytes: bytes | None,
) -> SportyBetEarlyPayoutSettlementReceipt | None:
    if receipt is None and receipt_bytes is None:
        return None
    if type(receipt) is not SportyBetEarlyPayoutSettlementReceipt or type(receipt_bytes) is not bytes:
        raise _fail("early-payout settlement receipt and exact bytes are both required")
    expected = reviewed_sportybet_early_payout_settlement_receipt()
    expected_bytes = canonical_sportybet_early_payout_settlement_receipt_bytes(expected)
    if canonical_sportybet_early_payout_settlement_receipt_bytes(receipt) != expected_bytes:
        raise _fail("early-payout settlement receipt differs from reviewed evidence")
    if receipt_bytes != expected_bytes:
        raise _fail("early-payout settlement receipt bytes differ from reviewed evidence")
    return expected


def _map_one(
    selection: NativeSelection,
    decision: ReviewedCanonicalMappingDecision,
    *,
    early_payout_settlement_receipt: SportyBetEarlyPayoutSettlementReceipt | None = None,
) -> MappedSportyBetCanonicalSelection:
    if selection.market_name is None or selection.selection_label is None:
        raise _fail("reviewed mapping requires exact provider market and selection labels")
    if selection.market_name != decision.provider_market_name or selection.selection_label != decision.provider_selection_label:
        raise _fail("review decision labels do not exactly match source-replayed provider evidence")
    if selection.provider_quote_at is not None or selection.provider_snapshot_id is not None:
        raise _fail("provider quote timestamp/snapshot capability remains unproven")
    _validate_line_semantics(selection, decision)
    try:
        canonical = make_selection(decision.canonical_market_id, decision.canonical_outcome_id, line=decision.canonical_line)
    except InvalidSelectionError as exc:
        raise _fail(str(exc)) from exc
    early = canonical.market_id in _EARLY
    early_evidence_sha256 = None
    if early and early_payout_settlement_receipt is not None:
        rules = {
            rule.market_id: rule
            for rule in early_payout_settlement_receipt.market_rules
        }
        rule = rules.get(canonical.market_id)
        if rule is None or selection.market_id != rule.provider_mapped_market_id:
            raise _fail(
                "early-payout receipt does not prove this exact provider mapped "
                "market identity"
            )
        early_evidence_sha256 = sha256_sportybet_early_payout_settlement_receipt(
            early_payout_settlement_receipt
        )
    authority = (
        SettlementEquivalenceAuthority.REVIEWED_SPORTYBET_EARLY_PAYOUT_SETTLEMENT_EQUIVALENCE
        if early and early_evidence_sha256 is not None
        else (
            SettlementEquivalenceAuthority.PROVIDER_PROMOTION_RULES_UNPROVEN
            if early
            else SettlementEquivalenceAuthority.REVIEWED_STANDARD_SETTLEMENT_EQUIVALENCE
        )
    )
    return MappedSportyBetCanonicalSelection(
        provider_selection_sha256=hashlib.sha256(_json_bytes(selection.to_dict(), "provider selection")).hexdigest(),
        event_id=selection.event_id,
        provider_market_id=selection.market_id,
        provider_market_name=selection.market_name,
        provider_specifier=selection.specifier,
        provider_outcome_id=selection.outcome_id,
        provider_selection_label=selection.selection_label,
        availability=selection.availability.value,
        odds_raw=selection.odds_raw,
        odds_decimal=selection.odds_decimal,
        provider_quote_at=None,
        provider_snapshot_id=None,
        canonical_market_id=canonical.market_id,
        canonical_outcome_id=canonical.outcome_id,
        canonical_line=canonical.line,
        canonical_display_label=canonical.display_label,
        canonical_selection_display_name=canonical.selection_display_name,
        settlement_equivalence_authority=authority,
        settlement_evidence_sha256=(
            early_evidence_sha256 if early else None
        ),
        bookmaker_equivalence_authorized=(
            not early or early_evidence_sha256 is not None
        ),
        canonical_market_mapping_authorized=True,
        fresh_price_authorized=False,
        href=selection.href,
    )


@dataclasses.dataclass(frozen=True)
class SportyBetReviewedCanonicalMarketMapping:
    schema_version: int
    dataset_name: str
    provider: str
    status: str
    review_basis: str
    source_reconciliation_receipt_sha256: str
    source_native_inventory_sha256: str
    source_event_evidence_id: str
    sportybet_event_id: str
    sportybet_sport_id: str
    matched_fotmob_fixture_id: str
    review_decisions_sha256: str
    mapped_selections: tuple[MappedSportyBetCanonicalSelection, ...]
    represented_target_market_ids: tuple[MarketId, ...]
    unrepresented_target_market_ids: tuple[MarketId, ...]
    all_15_target_markets_represented: bool
    mapped_selection_count: int
    unmapped_native_selection_count: int
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        _assert_target_registry()
        if (self.schema_version, self.dataset_name, self.provider, self.status, self.review_basis) != (SCHEMA_VERSION, DATASET_NAME, PROVIDER, STATUS, REVIEW_BASIS):
            raise _fail("mapping metadata mismatch")
        _sha(self.source_reconciliation_receipt_sha256, "source_reconciliation_receipt_sha256")
        _sha(self.source_native_inventory_sha256, "source_native_inventory_sha256")
        _sha(self.review_decisions_sha256, "review_decisions_sha256")
        _text(self.source_event_evidence_id, "source_event_evidence_id")
        _provider_id(self.sportybet_event_id, "sportybet_event_id")
        _provider_id(self.sportybet_sport_id, "sportybet_sport_id")
        _text(self.matched_fotmob_fixture_id, "matched_fotmob_fixture_id")
        if type(self.mapped_selections) is not tuple or not self.mapped_selections or any(type(x) is not MappedSportyBetCanonicalSelection for x in self.mapped_selections):
            raise _fail("mapped_selections must be a non-empty exact tuple")
        represented = tuple(m for m in TARGET_MARKET_IDS if any(x.canonical_market_id is m for x in self.mapped_selections))
        missing = tuple(m for m in TARGET_MARKET_IDS if m not in represented)
        if self.represented_target_market_ids != represented or self.unrepresented_target_market_ids != missing:
            raise _fail("target-market representation mismatch")
        if self.all_15_target_markets_represented is not (not missing):
            raise _fail("all_15_target_markets_represented mismatch")
        if self.mapped_selection_count != len(self.mapped_selections) or self.unmapped_native_selection_count < 0:
            raise _fail("mapped/unmapped selection counts are invalid")
        expected = {
            "bet_authorized": False,
            "bookmaker_equivalence_authorized": all(x.bookmaker_equivalence_authorized for x in self.mapped_selections),
            "booking_code_authorized": False,
            "canonical_market_mapping_authorized": True,
            "fixture_reconciliation_authorized": True,
            "fresh_price_authorized": False,
            "model_integration_authorized": False,
            "network_acquisition_authorized": False,
            "pricing_authorized": False,
            "selection_authorized": False,
            "slip_construction_authorized": False,
            "sportybet_execution_authorized": False,
        }
        if not isinstance(self.safety, Mapping) or dict(self.safety) != expected:
            raise _fail("mapping safety authority mismatch")
        object.__setattr__(self, "safety", types.MappingProxyType(expected))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "provider": self.provider,
            "status": self.status,
            "review_basis": self.review_basis,
            "source_reconciliation_receipt_sha256": self.source_reconciliation_receipt_sha256,
            "source_native_inventory_sha256": self.source_native_inventory_sha256,
            "source_event_evidence_id": self.source_event_evidence_id,
            "sportybet_event_id": self.sportybet_event_id,
            "sportybet_sport_id": self.sportybet_sport_id,
            "matched_fotmob_fixture_id": self.matched_fotmob_fixture_id,
            "review_decisions_sha256": self.review_decisions_sha256,
            "mapped_selections": [x.to_dict() for x in self.mapped_selections],
            "represented_target_market_ids": [x.value for x in self.represented_target_market_ids],
            "unrepresented_target_market_ids": [x.value for x in self.unrepresented_target_market_ids],
            "all_15_target_markets_represented": self.all_15_target_markets_represented,
            "mapped_selection_count": self.mapped_selection_count,
            "unmapped_native_selection_count": self.unmapped_native_selection_count,
            "safety": dict(self.safety),
        }


def _build(
    reconciled: Any,
    inventory: Any,
    review_decisions: Sequence[ReviewedCanonicalMappingDecision],
    *,
    early_payout_settlement_receipt: SportyBetEarlyPayoutSettlementReceipt | None = None,
    early_payout_settlement_receipt_bytes: bytes | None = None,
) -> SportyBetReviewedCanonicalMarketMapping:
    _assert_target_registry()
    if (
        reconciled.disposition is not reconciliation.FullUtcReconciliationDisposition.UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED
        or reconciled.fixture_reconciliation_authorized is not True
        or reconciled.matched_fixture is None
    ):
        raise _fail("canonical mapping requires exact source-replayed unique full-UTC fixture reconciliation")
    if not isinstance(inventory, native.SportyBetUserControlledNativeInventory):
        raise _fail("source bundle event inventory must be reviewed user-controlled native inventory")
    try:
        inventory_sha = native.inventory_sha256(inventory)
    except native.SportyBetUserInventoryError as exc:
        raise _fail(str(exc)) from exc
    if inventory_sha != reconciled.source_native_inventory_sha256:
        raise _fail("source-replayed reconciliation does not bind this exact native inventory")
    if (inventory.source_event_id, inventory.source_sport_id, inventory.source_evidence_id) != (
        reconciled.sportybet_event_id, reconciled.sportybet_sport_id, reconciled.source_event_evidence_id
    ):
        raise _fail("native inventory event/source lineage does not match reconciled fixture")
    if inventory.provider_quote_at is not None or inventory.provider_snapshot_id is not None:
        raise _fail("provider quote timestamp/snapshot capability remains unproven")

    decisions = _decisions(review_decisions)
    early_evidence_receipt = _validated_early_payout_evidence(
        early_payout_settlement_receipt,
        early_payout_settlement_receipt_bytes,
    )
    source_index = {x.selection_identity: x for x in inventory.selections}
    if len(source_index) != len(inventory.selections):
        raise _fail("source inventory contains duplicate provider selection identity")
    mapped = []
    for decision in decisions:
        if decision.event_id != reconciled.sportybet_event_id:
            raise _fail("review decision event identity does not match reconciled fixture")
        selection = source_index.get(decision.native_identity)
        if selection is None:
            raise _fail("review decision does not match an exact source-replayed provider selection")
        mapped.append(
            _map_one(
                selection,
                decision,
                early_payout_settlement_receipt=early_evidence_receipt,
            )
        )
    mapped_rows = tuple(sorted(mapped, key=lambda x: (TARGET_MARKET_IDS.index(x.canonical_market_id), x.canonical_outcome_id.value, x.canonical_line or 0.0, x.provider_market_id, x.provider_outcome_id)))
    represented = tuple(m for m in TARGET_MARKET_IDS if any(x.canonical_market_id is m for x in mapped_rows))
    missing = tuple(m for m in TARGET_MARKET_IDS if m not in represented)
    all_equivalent = all(x.bookmaker_equivalence_authorized for x in mapped_rows)
    safety = {
        "bet_authorized": False,
        "bookmaker_equivalence_authorized": all_equivalent,
        "booking_code_authorized": False,
        "canonical_market_mapping_authorized": True,
        "fixture_reconciliation_authorized": True,
        "fresh_price_authorized": False,
        "model_integration_authorized": False,
        "network_acquisition_authorized": False,
        "pricing_authorized": False,
        "selection_authorized": False,
        "slip_construction_authorized": False,
        "sportybet_execution_authorized": False,
    }
    receipt_sha = hashlib.sha256(reconciliation.canonical_reconciliation_bytes(reconciled)).hexdigest()
    decision_sha = hashlib.sha256(canonical_review_decisions_bytes(decisions)).hexdigest()
    _sha(receipt_sha, "source_reconciliation_receipt_sha256")
    _sha(inventory_sha, "source_native_inventory_sha256")
    return SportyBetReviewedCanonicalMarketMapping(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        provider=PROVIDER,
        status=STATUS,
        review_basis=REVIEW_BASIS,
        source_reconciliation_receipt_sha256=receipt_sha,
        source_native_inventory_sha256=inventory_sha,
        source_event_evidence_id=inventory.source_evidence_id,
        sportybet_event_id=reconciled.sportybet_event_id,
        sportybet_sport_id=reconciled.sportybet_sport_id,
        matched_fotmob_fixture_id=reconciled.matched_fixture.source_fixture_identifier,
        review_decisions_sha256=decision_sha,
        mapped_selections=mapped_rows,
        represented_target_market_ids=represented,
        unrepresented_target_market_ids=missing,
        all_15_target_markets_represented=not missing,
        mapped_selection_count=len(mapped_rows),
        unmapped_native_selection_count=len(inventory.selections) - len(mapped_rows),
        safety=safety,
    )


def build_reviewed_canonical_market_mapping(
    *,
    reconciliation_receipt_directory: Any,
    reconciliation_source_bundle: receipts.FullUtcReconciliationSourceBundle,
    review_decisions: Sequence[ReviewedCanonicalMappingDecision],
    repository_root: Path,
    early_payout_settlement_receipt: SportyBetEarlyPayoutSettlementReceipt | None = None,
    early_payout_settlement_receipt_bytes: bytes | None = None,
) -> SportyBetReviewedCanonicalMarketMapping:
    try:
        reconciled = receipts.verify_reconciliation_receipt_directory(
            reconciliation_receipt_directory,
            source_bundle=reconciliation_source_bundle,
            repository_root=repository_root,
        )
    except receipts.SportyBetFotMobFullUtcReconciliationReceiptError as exc:
        raise _fail(str(exc)) from exc
    return _build(
        reconciled,
        reconciliation_source_bundle.event_inventory,
        review_decisions,
        early_payout_settlement_receipt=early_payout_settlement_receipt,
        early_payout_settlement_receipt_bytes=early_payout_settlement_receipt_bytes,
    )


def canonical_mapping_bytes(value: Any) -> bytes:
    if type(value) is not SportyBetReviewedCanonicalMarketMapping:
        raise _fail("value must be exact SportyBetReviewedCanonicalMarketMapping")
    return _json_bytes(value.to_dict(), "canonical market mapping")


def canonical_mapping_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_mapping_bytes(value)).hexdigest()
