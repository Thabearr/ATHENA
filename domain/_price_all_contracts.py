"""Frozen contracts for ATHENA Phase 7 price-all value evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from domain._forward_calibration_contracts import validate_calibration_contract
from domain.historical_training_coverage import validate_contracts as validate_label_contracts
from domain.markets import MarketId, OutcomeId, validate_selection
from domain.pricing import DEFAULT_MAX_QUOTE_AGE_SECONDS, parse_observed_at
from domain.sportybet_reviewed_canonical_market_mapping import (
    DATASET_NAME as SPORTYBET_MAPPING_DATASET,
    PROVIDER as SPORTYBET_MAPPING_PROVIDER,
    REVIEW_BASIS as SPORTYBET_MAPPING_REVIEW_BASIS,
    SportyBetReviewedCanonicalMarketMapping,
    SCHEMA_VERSION as SPORTYBET_MAPPING_SCHEMA_VERSION,
    STATUS as SPORTYBET_MAPPING_STATUS,
    TARGET_MARKET_IDS as SPORTYBET_MAPPING_TARGET_MARKETS,
    SettlementEquivalenceAuthority,
    canonical_mapping_sha256,
)

PRICE_ALL_DATASET = "athena_price_all_value_engine"
PRICE_ALL_SCHEMA_VERSION = 1
PRICE_ALL_CONTRACT_VERSION = 1
QUOTE_POLICY_ID = "SPORTYBET_EXACT_MAPPING_SINGLE_SNAPSHOT_TZ_FRESH_900S_V1"
DEVIG_POLICY_ID = "PROPORTIONAL_ONLY_MUTUALLY_EXCLUSIVE_EXHAUSTIVE_PARTITIONS_V1"
SETTLEMENT_RETURN_POLICY_ID = "UNIT_STAKE_FULL_PUSH_SPLIT_SETTLEMENT_RETURNS_V1"
CALIBRATED_INPUT_POLICY_ID = "UPSTREAM_AUTHORIZED_FULL_SETTLEMENT_DISTRIBUTION_V1"
NO_ROUTER_POLICY_ID = "PRICE_ALL_NO_RANK_ROUTE_SELECT_OR_BET_V1"
REAL_CURRENT_SPORTYBET_PRICE_ALL_STATUS = "NOT_RUN_VERIFIED_QUOTE_CORPUS_UNAVAILABLE"
_SHA = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

AUTHORITY_FLAGS = MappingProxyType({
    "verified_price_consumption": True,
    "value_record_computation": True,
    "football_probability_generation": False,
    "model_promotion": False,
    "market_routing": False,
    "final_selection": False,
    "accumulator": False,
    "production_approval": False,
    "bet": False,
})

SETTLEMENT_RETURN_SEMANTICS = MappingProxyType({
    "WIN": "decimal_odds_minus_one",
    "HALF_WIN": "decimal_odds_minus_one_divided_by_two",
    "PUSH": "zero",
    "HALF_LOSS": "minus_one_half",
    "LOSS": "minus_one",
})
DEVIG_CLASSIFICATION_SEMANTICS = MappingProxyType({
    "ordinary_complete_partitions": (
        "MATCH_RESULT", "BTTS", "TOTAL_GOALS_EXACT_HALF_LINE",
        "RESULT_OR_TOTALS_YES_NO", "WIN_TO_NIL_YES_NO",
    ),
    "overlapping_no_ordinary_devig": ("DOUBLE_CHANCE", "EARLY_PAYOUT"),
    "push_or_split_no_ordinary_devig": ("DRAW_NO_BET", "ASIAN_HANDICAP"),
    "totals_line_settlement": "integer_push_quarter_split_half_win_loss",
    "partition_binding": "same_fixture_event_source_snapshot_market_and_exact_line",
})


class PriceAllError(ValueError):
    pass


class PriceDisposition(str, Enum):
    PRICED = "PRICED"
    UNPRICED_NO_EXACT_QUOTE = "UNPRICED_NO_EXACT_QUOTE"
    UNPRICED_STALE_QUOTE = "UNPRICED_STALE_QUOTE"
    UNPRICED_FUTURE_QUOTE = "UNPRICED_FUTURE_QUOTE"
    UNPRICED_AMBIGUOUS_QUOTE = "UNPRICED_AMBIGUOUS_QUOTE"
    UNPRICED_SETTLEMENT_EQUIVALENCE_UNPROVEN = "UNPRICED_SETTLEMENT_EQUIVALENCE_UNPROVEN"
    UNPRICED_INVALID_SNAPSHOT = "UNPRICED_INVALID_SNAPSHOT"
    UNPRICED_SOURCE_MISMATCH = "UNPRICED_SOURCE_MISMATCH"
    BLOCKED_UPSTREAM_PROBABILITY_UNAVAILABLE = "BLOCKED_UPSTREAM_PROBABILITY_UNAVAILABLE"
    BLOCKED_SETTLEMENT_DISTRIBUTION_INCOMPLETE = "BLOCKED_SETTLEMENT_DISTRIBUTION_INCOMPLETE"


class DevigStatus(str, Enum):
    AVAILABLE_COMPLETE_PARTITION = "AVAILABLE_COMPLETE_PARTITION"
    UNAVAILABLE_INCOMPLETE_PARTITION = "UNAVAILABLE_INCOMPLETE_PARTITION"
    UNAVAILABLE_CROSS_SNAPSHOT_PARTITION = "UNAVAILABLE_CROSS_SNAPSHOT_PARTITION"
    NOT_IDENTIFIABLE_OVERLAPPING_EVENTS = "NOT_IDENTIFIABLE_OVERLAPPING_EVENTS"
    NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT = "NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT"


class SettlementState(str, Enum):
    WIN = "WIN"
    HALF_WIN = "HALF_WIN"
    PUSH = "PUSH"
    HALF_LOSS = "HALF_LOSS"
    LOSS = "LOSS"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _sha(value: str, label: str) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise PriceAllError(f"{label} must be an exact SHA-256")
    return value


def calculate_sportybet_mapping_semantics_sha256() -> str:
    payload = {
        "dataset": SPORTYBET_MAPPING_DATASET,
        "schema_version": SPORTYBET_MAPPING_SCHEMA_VERSION,
        "provider": SPORTYBET_MAPPING_PROVIDER,
        "status": SPORTYBET_MAPPING_STATUS,
        "review_basis": SPORTYBET_MAPPING_REVIEW_BASIS,
        "target_markets": [item.value for item in SPORTYBET_MAPPING_TARGET_MARKETS],
        "settlement_authorities": [item.value for item in SettlementEquivalenceAuthority],
    }
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


EXPECTED_SPORTYBET_MAPPING_SEMANTICS_SHA256 = (
    "6741cf93a91616e3c4cdca1b40c9ee91e612b023ed8e0e5b1d45f2b5c1913b90"
)


def contract_payload(calibration_sha: str, market_sha: str, mapping_sha: str) -> dict[str, Any]:
    return {
        "schema_version": PRICE_ALL_SCHEMA_VERSION,
        "calibration_contract_sha256": calibration_sha,
        "canonical_market_semantics_sha256": market_sha,
        "sportybet_mapping_semantics_sha256": mapping_sha,
        "quote_policy_id": QUOTE_POLICY_ID,
        "max_quote_age_seconds": DEFAULT_MAX_QUOTE_AGE_SECONDS,
        "devig_policy_id": DEVIG_POLICY_ID,
        "settlement_return_policy_id": SETTLEMENT_RETURN_POLICY_ID,
        "settlement_return_semantics": dict(SETTLEMENT_RETURN_SEMANTICS),
        "calibrated_input_policy_id": CALIBRATED_INPUT_POLICY_ID,
        "devig_classification_semantics": {
            key: list(value) if type(value) is tuple else value
            for key, value in DEVIG_CLASSIFICATION_SEMANTICS.items()
        },
        "no_router_policy_id": NO_ROUTER_POLICY_ID,
        "authority_flags": dict(AUTHORITY_FLAGS),
    }


def calculate_price_all_contract_sha256(*, calibration_sha: str, market_sha: str,
                                        mapping_sha: str, version: int = PRICE_ALL_CONTRACT_VERSION) -> str:
    return hashlib.sha256(_canonical_bytes({"version": version,
        "semantics": contract_payload(calibration_sha, market_sha, mapping_sha)})).hexdigest()


EXPECTED_PRICE_ALL_CONTRACT_SHA256_BY_VERSION = MappingProxyType({
    1: "b62bbac793a1b2ff60c405cc954105237c1353b995645406f5da7ac4d10e97d5",
})


def validate_price_all_contract() -> Mapping[str, str]:
    calibration = validate_calibration_contract()["calibration_contract_sha256"]
    _labels, market, _generation = validate_label_contracts()
    mapping = calculate_sportybet_mapping_semantics_sha256()
    if mapping != EXPECTED_SPORTYBET_MAPPING_SEMANTICS_SHA256:
        raise PriceAllError("SportyBet mapping semantic drift")
    actual = calculate_price_all_contract_sha256(
        calibration_sha=calibration, market_sha=market, mapping_sha=mapping)
    expected = EXPECTED_PRICE_ALL_CONTRACT_SHA256_BY_VERSION.get(PRICE_ALL_CONTRACT_VERSION)
    if expected is None or actual != expected:
        raise PriceAllError("Price-all contract drift")
    return MappingProxyType({"calibration_contract_sha256": calibration,
        "canonical_market_semantics_sha256": market,
        "sportybet_mapping_semantics_sha256": mapping,
        "price_all_contract_sha256": actual})


def _probabilities(components: Sequence[str], values: Sequence[float]) -> tuple[tuple[str, float], ...]:
    names = tuple(str(item) for item in components)
    probabilities = tuple(float(item) for item in values)
    if not names or len(names) != len(set(names)) or len(names) != len(probabilities):
        raise PriceAllError("settlement probability components are invalid")
    if any(not math.isfinite(item) or item < 0 or item > 1 for item in probabilities):
        raise PriceAllError("settlement probabilities must be finite in [0,1]")
    if not math.isclose(math.fsum(probabilities), 1.0, abs_tol=1e-9, rel_tol=0):
        raise PriceAllError("settlement probabilities must sum to one")
    return tuple(zip(names, probabilities))


@dataclass(frozen=True)
class CalibratedValueCandidate:
    candidate_id: str
    fixture_id: str
    sportybet_event_id: str
    market_id: MarketId
    outcome_id: OutcomeId
    line: float | None
    settlement_probabilities: tuple[tuple[str, float], ...]
    model_id: str
    calibration_artifact_sha256: str
    calibration_strategy: str
    raw_probability_identity: str | None
    upstream_probability_authorized: bool

    @classmethod
    def create(cls, *, components: Sequence[str], probabilities: Sequence[float], **value: Any) -> "CalibratedValueCandidate":
        market, outcome, line = validate_selection(value["market_id"], value["outcome_id"], value.get("line"))
        for field in ("candidate_id", "fixture_id", "sportybet_event_id", "model_id", "calibration_strategy"):
            if type(value.get(field)) is not str or not value[field].strip():
                raise PriceAllError(f"{field} is required")
        _sha(value["calibration_artifact_sha256"], "calibration_artifact_sha256")
        if value.get("raw_probability_identity") is not None:
            _sha(value["raw_probability_identity"], "raw_probability_identity")
        return cls(value["candidate_id"], value["fixture_id"], value["sportybet_event_id"],
                   market, outcome, line, _probabilities(components, probabilities), value["model_id"],
                   value["calibration_artifact_sha256"], value["calibration_strategy"],
                   value.get("raw_probability_identity"), value.get("upstream_probability_authorized") is True)

    @property
    def probability_map(self) -> Mapping[str, float]:
        return MappingProxyType(dict(self.settlement_probabilities))

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "fixture_id": self.fixture_id,
            "sportybet_event_id": self.sportybet_event_id,
            "market_id": self.market_id.value,
            "outcome_id": self.outcome_id.value,
            "line": self.line,
            "settlement_probabilities": [
                {"component": name, "probability": probability}
                for name, probability in self.settlement_probabilities
            ],
            "model_id": self.model_id,
            "calibration_artifact_sha256": self.calibration_artifact_sha256,
            "calibration_strategy": self.calibration_strategy,
            "raw_probability_identity": self.raw_probability_identity,
            "upstream_probability_authorized": self.upstream_probability_authorized,
        }


@dataclass(frozen=True, init=False)
class SportyBetExactQuote:
    fixture_id: str
    event_id: str
    provider_market_id: str
    provider_outcome_id: str
    provider_specifier: str | None
    canonical_market_id: MarketId
    canonical_outcome_id: OutcomeId
    canonical_line: float | None
    source: str
    snapshot_id: str
    observed_at: datetime
    decimal_odds: float
    mapping_evidence_sha256: str
    fixture_reconciliation_sha256: str
    settlement_equivalence_authority: SettlementEquivalenceAuthority

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise PriceAllError("exact quotes are issued only from a reviewed SportyBet mapping")

    @classmethod
    def from_reviewed_mapping(
        cls,
        mapping: SportyBetReviewedCanonicalMarketMapping,
        *,
        provider_selection_sha256: str,
        snapshot_id: str,
        observed_at: datetime | str,
        decimal_odds: float,
    ) -> "SportyBetExactQuote":
        if type(mapping) is not SportyBetReviewedCanonicalMarketMapping:
            raise PriceAllError("quote mapping must be an exact reviewed SportyBet mapping")
        matching = tuple(item for item in mapping.mapped_selections
                         if item.provider_selection_sha256 == provider_selection_sha256)
        if len(matching) != 1:
            raise PriceAllError("provider selection is not uniquely present in reviewed mapping")
        mapped = matching[0]
        if mapped.event_id != mapping.sportybet_event_id:
            raise PriceAllError("mapped selection event conflicts with reconciled SportyBet event")
        if not mapped.canonical_market_mapping_authorized:
            raise PriceAllError("reviewed canonical mapping authority is absent")
        market, outcome, line = validate_selection(
            mapped.canonical_market_id, mapped.canonical_outcome_id, mapped.canonical_line)
        if type(snapshot_id) is not str or not snapshot_id.strip():
            raise PriceAllError("snapshot_id is required")
        observed_value = observed_at
        try:
            if type(observed_value) is datetime:
                if observed_value.tzinfo is None or observed_value.utcoffset() is None:
                    raise ValueError("timezone required")
                observed = observed_value.astimezone(timezone.utc)
            else:
                observed = parse_observed_at(observed_value)
        except ValueError as exc:
            raise PriceAllError("observed_at must be a timezone-aware timestamp") from exc
        odds = decimal_odds
        if isinstance(odds, bool) or not isinstance(odds, (int, float)) or not math.isfinite(float(odds)) or float(odds) <= 1:
            raise PriceAllError("decimal_odds must be finite and above 1.0")
        result = object.__new__(cls)
        fields = {
            "fixture_id": mapping.matched_fotmob_fixture_id,
            "event_id": mapped.event_id,
            "provider_market_id": mapped.provider_market_id,
            "provider_outcome_id": mapped.provider_outcome_id,
            "provider_specifier": mapped.provider_specifier,
            "canonical_market_id": market,
            "canonical_outcome_id": outcome,
            "canonical_line": line,
            "source": "SportyBet",
            "snapshot_id": snapshot_id,
            "observed_at": observed,
            "decimal_odds": float(odds),
            "mapping_evidence_sha256": canonical_mapping_sha256(mapping),
            "fixture_reconciliation_sha256": mapping.source_reconciliation_receipt_sha256,
            "settlement_equivalence_authority": mapped.settlement_equivalence_authority,
        }
        for name, item in fields.items():
            object.__setattr__(result, name, item)
        return result

    @property
    def quote_identity(self) -> tuple[Any, ...]:
        return (self.fixture_id, self.event_id, self.provider_market_id,
                self.provider_specifier, self.provider_outcome_id, self.snapshot_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "event_id": self.event_id,
            "provider_market_id": self.provider_market_id,
            "provider_outcome_id": self.provider_outcome_id,
            "provider_specifier": self.provider_specifier,
            "canonical_market_id": self.canonical_market_id.value,
            "canonical_outcome_id": self.canonical_outcome_id.value,
            "canonical_line": self.canonical_line,
            "source": self.source,
            "snapshot_id": self.snapshot_id,
            "observed_at": self.observed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "decimal_odds": self.decimal_odds,
            "mapping_evidence_sha256": self.mapping_evidence_sha256,
            "fixture_reconciliation_sha256": self.fixture_reconciliation_sha256,
            "settlement_equivalence_authority": self.settlement_equivalence_authority.value,
        }


__all__ = [name for name in globals() if not name.startswith("_")]
