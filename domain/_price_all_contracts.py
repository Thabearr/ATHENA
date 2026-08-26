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
from pathlib import Path
from typing import Any, Mapping, Sequence

from domain._forward_calibration_contracts import (
    ForwardCalibrationError,
    validate_calibration_contract,
)
from domain._forward_calibration_fit import ForwardCalibrationArtifact
from domain._forward_calibration_projection import (
    CalibrationUnitSpec,
    CalibrationVectorRow,
    calibration_unit_specs,
)
from domain.historical_training_coverage import validate_contracts as validate_label_contracts
from domain.markets import MARKET_REGISTRY, MarketFamily, MarketId, OutcomeId, validate_selection
from domain.pricing import DEFAULT_MAX_QUOTE_AGE_SECONDS, parse_observed_at
from domain import sportybet_user_controlled_native_inventory as source_inventory
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
QUOTE_POLICY_ID = "SPORTYBET_VERIFIED_SOURCE_REPLAY_EVIDENCE_SNAPSHOT_FRESH_900S_V1"
DEVIG_POLICY_ID = "PROPORTIONAL_ONLY_MUTUALLY_EXCLUSIVE_EXHAUSTIVE_PARTITIONS_V1"
SETTLEMENT_RETURN_POLICY_ID = "UNIT_STAKE_FULL_PUSH_SPLIT_SETTLEMENT_RETURNS_V1"
CALIBRATED_INPUT_POLICY_ID = "EXACT_PHASE6_ARTIFACT_UNIT_PROJECTION_ISSUANCE_V1"
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
    "partition_binding": (
        "same_fixture_event_source_evidence_snapshot_provider_market_specifier_"
        "exact_line_mapping_inventory_and_reconciliation_ancestry"
    ),
})
QUOTE_SOURCE_ISSUANCE_SEMANTICS = MappingProxyType({
    "source_contract": "SportyBetUserControlledNativeInventory",
    "price_origin": "exact_native_selection_replayed_from_verified_raw_html",
    "observation_time_origin": "verified_manifest_user_attested_observation",
    "observation_authority": "USER_ATTESTED_NOT_PROVIDER_TIMESTAMP",
    "evidence_snapshot_identity": "canonical_native_inventory_sha256",
    "raw_identity": "source_raw_sha256",
    "provider_quote_timestamp": None,
    "provider_snapshot_id": None,
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
        "quote_source_issuance_semantics": dict(QUOTE_SOURCE_ISSUANCE_SEMANTICS),
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
    1: "1fb0a6c891adccd76b4864a6197e55d22154176a4191f57ce92cde13501535aa",
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


def _validate_phase6_unit(unit: CalibrationUnitSpec, outcome: OutcomeId) -> None:
    if type(unit) is not CalibrationUnitSpec or type(outcome) is not OutcomeId:
        raise PriceAllError("calibration unit and outcome must be exact reviewed types")
    try:
        if unit.market_id is MarketId.TOTAL_GOALS:
            reviewed = calibration_unit_specs(total_goal_lines=(unit.line,))
        elif unit.market_id is MarketId.ASIAN_HANDICAP:
            if unit.selection_outcome not in {OutcomeId.HOME, OutcomeId.AWAY}:
                raise PriceAllError("unsupported Phase 6 calibration unit semantics")
            home_line = unit.line if unit.selection_outcome is OutcomeId.HOME else -unit.line
            reviewed = calibration_unit_specs(asian_handicap_home_lines=(home_line,))
        else:
            reviewed = calibration_unit_specs()
    except ForwardCalibrationError as exc:
        raise PriceAllError("unsupported Phase 6 calibration unit semantics") from exc
    if unit not in reviewed:
        raise PriceAllError("unsupported Phase 6 calibration unit semantics")
    if outcome not in MARKET_REGISTRY[unit.market_id].supported_outcomes:
        raise PriceAllError("candidate outcome is not canonical for calibration market")
    if unit.selection_outcome is not None:
        if outcome is not unit.selection_outcome:
            raise PriceAllError("candidate outcome differs from selection-specific calibration unit")
    elif outcome.value not in unit.components:
        raise PriceAllError("candidate outcome is absent from calibration partition components")


@dataclass(frozen=True, init=False)
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
    calibration_unit: tuple[tuple[str, Any], ...]
    raw_probability_identity: str

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise PriceAllError("candidates are issued only from exact Phase 6 calibration ancestry")

    @classmethod
    def from_phase6_calibration(
        cls,
        artifact: ForwardCalibrationArtifact,
        row: CalibrationVectorRow,
        *,
        fixture_id: str,
        sportybet_event_id: str,
        outcome_id: OutcomeId,
        strategy: str = "HIERARCHICAL",
    ) -> "CalibratedValueCandidate":
        if type(artifact) is not ForwardCalibrationArtifact or type(row) is not CalibrationVectorRow:
            raise PriceAllError("exact Phase 6 artifact and calibration row are required")
        if dict(artifact.contract_identities) != validate_calibration_contract():
            raise PriceAllError("Phase 6 artifact frozen dependency identity mismatch")
        if artifact.model_id != row.model_id:
            raise PriceAllError("Phase 6 artifact/model identity mismatch")
        model = artifact.unit_models.get(row.unit.unit_id)
        if model is None or model.unit != row.unit:
            raise PriceAllError("calibration unit is absent or differs from exact artifact")
        _validate_phase6_unit(row.unit, outcome_id)
        market, outcome, line = validate_selection(row.unit.market_id, outcome_id, row.unit.line)
        strategy_value = str(strategy).strip().upper()
        try:
            probabilities = artifact.predict(row, strategy_value)
        except ForwardCalibrationError as exc:
            raise PriceAllError("Phase 6 calibration projection failed") from exc
        calibrated = _probabilities(row.unit.components, probabilities)
        for label, value in (("fixture_id", fixture_id), ("sportybet_event_id", sportybet_event_id)):
            if type(value) is not str or not value.strip():
                raise PriceAllError(f"{label} is required")
        row_payload = {
            "match_key": row.match_key,
            "match_date": row.match_date,
            "competition_key": row.competition_key,
            "season": row.season,
            "regime": row.regime,
            "model_id": row.model_id,
            "fold_index": row.fold_index,
            "fit_end_date": row.fit_end_date,
            "partition": row.partition.value,
            "unit": row.unit.stable_dict(),
            "raw_probabilities": list(row.raw_probabilities),
        }
        raw_identity = hashlib.sha256(_canonical_bytes(row_payload)).hexdigest()
        candidate_payload = {
            "fixture_id": fixture_id,
            "sportybet_event_id": sportybet_event_id,
            "market_id": market.value,
            "outcome_id": outcome.value,
            "line": line,
            "artifact_sha256": artifact.artifact_sha256,
            "raw_probability_identity": raw_identity,
            "strategy": strategy_value,
        }
        candidate_id = hashlib.sha256(_canonical_bytes(candidate_payload)).hexdigest()
        result = object.__new__(cls)
        stable_unit = row.unit.stable_dict()
        stable_unit["components"] = tuple(stable_unit["components"])
        values = {
            "candidate_id": candidate_id,
            "fixture_id": fixture_id,
            "sportybet_event_id": sportybet_event_id,
            "market_id": market,
            "outcome_id": outcome,
            "line": line,
            "settlement_probabilities": calibrated,
            "model_id": artifact.model_id,
            "calibration_artifact_sha256": artifact.artifact_sha256,
            "calibration_strategy": strategy_value,
            "calibration_unit": tuple(sorted(stable_unit.items())),
            "raw_probability_identity": raw_identity,
        }
        for name, value in values.items():
            object.__setattr__(result, name, value)
        return result

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
            "calibration_unit": dict(self.calibration_unit),
            "raw_probability_identity": self.raw_probability_identity,
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
    evidence_snapshot_sha256: str
    provider_snapshot_id: None
    observed_at: datetime
    observation_authority: str
    odds_raw: str
    decimal_odds: float
    source_evidence_manifest_sha256: str
    source_raw_sha256: str
    source_native_inventory_sha256: str
    mapping_evidence_sha256: str
    fixture_reconciliation_sha256: str
    settlement_equivalence_authority: SettlementEquivalenceAuthority

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise PriceAllError(
            "exact quotes are issued only by replaying reviewed SportyBet source ancestry"
        )

    @classmethod
    def from_reviewed_mapping(
        cls,
        mapping: SportyBetReviewedCanonicalMarketMapping,
        *,
        provider_selection_sha256: str,
        evidence_directory: Path,
        allowed_evidence_root: Path,
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
        try:
            inventory = source_inventory.build_inventory_from_evidence(
                evidence_directory, allowed_root=Path(allowed_evidence_root))
            inventory_sha = source_inventory.inventory_sha256(inventory)
        except source_inventory.SportyBetUserInventoryError as exc:
            raise PriceAllError("verified SportyBet source evidence replay failed") from exc
        if inventory_sha != mapping.source_native_inventory_sha256:
            raise PriceAllError("reviewed mapping does not bind exact replayed native inventory")
        if (
            inventory.source_event_id != mapping.sportybet_event_id
            or inventory.source_sport_id != mapping.sportybet_sport_id
            or inventory.source_evidence_id != mapping.source_event_evidence_id
        ):
            raise PriceAllError("source inventory event ancestry differs from reviewed mapping")
        native_identity = (
            mapped.event_id, mapped.provider_market_id,
            mapped.provider_specifier, mapped.provider_outcome_id,
        )
        source_rows = tuple(
            item for item in inventory.selections
            if item.selection_identity == native_identity
        )
        if len(source_rows) != 1:
            raise PriceAllError("mapped provider selection is absent or ambiguous in source evidence")
        source_selection = source_rows[0]
        source_selection_sha = hashlib.sha256(
            _canonical_bytes(source_selection.to_dict()) + b"\n"
        ).hexdigest()
        if source_selection_sha != mapped.provider_selection_sha256:
            raise PriceAllError("mapped provider selection identity differs from source evidence")
        if (
            source_selection.odds_raw != mapped.odds_raw
            or source_selection.odds_decimal != mapped.odds_decimal
        ):
            raise PriceAllError("mapped odds differ from exact source evidence")
        if source_selection.availability.value != "AVAILABLE":
            raise PriceAllError("source evidence selection is not explicitly available")
        market, outcome, line = validate_selection(
            mapped.canonical_market_id, mapped.canonical_outcome_id, mapped.canonical_line)
        try:
            observed = parse_observed_at(inventory.observed_at_user_attested)
        except ValueError as exc:
            raise PriceAllError("source observation time is invalid") from exc
        odds = float(source_selection.odds_decimal)
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
            "evidence_snapshot_sha256": inventory_sha,
            "provider_snapshot_id": None,
            "observed_at": observed,
            "observation_authority": inventory.observation_authority,
            "odds_raw": source_selection.odds_raw,
            "decimal_odds": odds,
            "source_evidence_manifest_sha256": inventory.source_evidence_manifest_sha256,
            "source_raw_sha256": inventory.source_raw_sha256,
            "source_native_inventory_sha256": inventory_sha,
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
                self.provider_specifier, self.provider_outcome_id,
                self.evidence_snapshot_sha256)

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
            "evidence_snapshot_sha256": self.evidence_snapshot_sha256,
            "provider_snapshot_id": None,
            "observed_at": self.observed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "observation_authority": self.observation_authority,
            "odds_raw": self.odds_raw,
            "decimal_odds": self.decimal_odds,
            "source_evidence_manifest_sha256": self.source_evidence_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "source_native_inventory_sha256": self.source_native_inventory_sha256,
            "mapping_evidence_sha256": self.mapping_evidence_sha256,
            "fixture_reconciliation_sha256": self.fixture_reconciliation_sha256,
            "settlement_equivalence_authority": self.settlement_equivalence_authority.value,
        }


__all__ = [name for name in globals() if not name.startswith("_")]
