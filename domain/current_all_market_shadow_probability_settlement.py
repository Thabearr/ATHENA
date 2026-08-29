"""Research-only all-market Shadow probability and settlement surface.

Composes already-reviewed ATHENA components into one deterministic handoff:

  sealed research xG rates
    → one ScoreMatrix
    → ScoreMatrix-derived markets (ordinary + full DNB/AH settlement)
    → specialist WEH (frozen inference)
    → specialist 1UP/2UP (lead-path)
    → exactly 15 canonical MarketId rows
    → optional PR-B provider-semantic readiness overlay
    → all production / pricing / selection / BET authority false

This module intentionally does NOT:
  - import legacy accumulator builders or analyst compilers
  - use global historical baseline tables or baseline-delta ranking
  - rank markets, build accumulators, or call Price-all / Router / Portfolio
  - create SportyBet share codes, stakes, or wagers
  - grant production authority or promote the fresh-holdout xG model
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence

from domain.early_payout_lead_path_probabilities import (
    EarlyPayoutAnalyticalProjection,
    project_early_payout_market,
)
from domain.markets import MARKET_REGISTRY, MarketFamily, MarketId, OutcomeId
from domain.model_status import (
    AnalyticalProbabilityCapability,
    PricingAuthority,
    SelectionAuthority,
    SettlementCapability,
    get_model_status,
)
from domain.score_matrix import ScoreMatrix, build_score_matrix
from domain.score_matrix_market_probabilities import (
    AnalyticalEventProbability,
    AnalyticalSettlementDistribution,
    MarketTopology,
    ScoreMatrixMarketProjection,
    project_score_matrix_market,
)
from domain.score_matrix_settlement import SettlementProbabilities
from domain.win_either_half_features import PRE_MATCH_FEATURE_NAMES
from domain.win_either_half_inference import (
    WinEitherHalfAnalyticalPrediction,
    WinEitherHalfInferenceError,
    predict_win_either_half,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-current-all-market-shadow-probability-settlement-v1"
DEFAULT_TOTAL_GOALS_LINE = 2.5
DEFAULT_AH_HOME_LINES: tuple[float, ...] = (-0.5, 0.0, 0.5, -0.25, 0.25, -0.75, 0.75)
PROBABILITY_SUM_TOLERANCE = 1e-12
SETTLEMENT_SUM_TOLERANCE = 1e-12

# Explicit ban list — enforced by tests that import this module's source.
_FORBIDDEN_IMPORT_MARKERS = (
    "legacy_accumulator_builder",
    "legacy_match_analyst",
    "legacy_market_baselines",
    "legacy_global_baseline_delta",
    "legacy_compile_master",
)

_AUTHORITY_KEYS = (
    "production_model",
    "production_probability",
    "score_matrix_production",
    "phase6",
    "production_price_all",
    "production_market_router",
    "production_portfolio",
    "production_selection",
    "sportybet_execution",
    "staking",
    "bet",
    "wager_placed",
)


class ShadowDisposition(str, Enum):
    ANALYTICAL_READY = "ANALYTICAL_READY"
    ANALYTICAL_READY_PROVIDER_BLOCKED = "ANALYTICAL_READY_PROVIDER_BLOCKED"
    MISSING_REQUIRED_INPUT = "MISSING_REQUIRED_INPUT"
    UNSUPPORTED_EXACT_LINE = "UNSUPPORTED_EXACT_LINE"
    NO_REVIEWED_XG = "NO_REVIEWED_XG"
    SPECIALIST_FEATURES_MISSING = "SPECIALIST_FEATURES_MISSING"
    PROVIDER_UNPROVEN = "PROVIDER_UNPROVEN"
    OUTSIDE_REVIEWED_XG_WINDOW = "OUTSIDE_REVIEWED_XG_WINDOW"


class AllMarketShadowError(ValueError):
    """Raised when the Shadow surface cannot be constructed defensibly."""


def _authority_map() -> Mapping[str, bool]:
    return MappingProxyType({key: False for key in _AUTHORITY_KEYS})


def _finite_non_negative(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise AllMarketShadowError(f"{label} must be a finite non-negative number")
    return float(value)


def _probability(value: Any, label: str = "probability") -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise AllMarketShadowError(f"{label} must be a finite probability in [0, 1]")
    return float(value)


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                dict(payload),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise AllMarketShadowError("canonical serialization failed") from exc


@dataclass(frozen=True)
class ResearchXGRates:
    """Reviewed research/shadow expected-goals pair (not production authority)."""

    calibrated_home: float
    calibrated_away: float
    sealed_prediction_sha256: Optional[str] = None
    feature_projection_identity: Optional[str] = None
    history_prefix_identity: Optional[str] = None
    source_fixture_identity: Optional[str] = None
    completeness_status: str = "SEALED_RESEARCH_RATES"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "calibrated_home", _finite_non_negative(self.calibrated_home, "calibrated_home")
        )
        object.__setattr__(
            self, "calibrated_away", _finite_non_negative(self.calibrated_away, "calibrated_away")
        )
        for field in (
            "sealed_prediction_sha256",
            "feature_projection_identity",
            "history_prefix_identity",
            "source_fixture_identity",
        ):
            value = getattr(self, field)
            if value is not None and (type(value) is not str or not value.strip()):
                raise AllMarketShadowError(f"{field} must be non-empty string or None")
        if type(self.completeness_status) is not str or not self.completeness_status.strip():
            raise AllMarketShadowError("completeness_status must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "calibrated_home": self.calibrated_home,
            "calibrated_away": self.calibrated_away,
            "sealed_prediction_sha256": self.sealed_prediction_sha256,
            "feature_projection_identity": self.feature_projection_identity,
            "history_prefix_identity": self.history_prefix_identity,
            "source_fixture_identity": self.source_fixture_identity,
            "completeness_status": self.completeness_status,
            "production_authority": False,
        }


@dataclass(frozen=True)
class ShadowMarketAssessment:
    market_id: MarketId
    market_family: MarketFamily
    disposition: ShadowDisposition
    probability_method: Optional[str]
    probability_input_namespace: Optional[str]
    analytical_capability: AnalyticalProbabilityCapability
    settlement_capability: SettlementCapability
    event_probabilities: tuple[AnalyticalEventProbability, ...]
    settlement_distributions: tuple[AnalyticalSettlementDistribution, ...]
    required_inputs: tuple[str, ...]
    missing_inputs: tuple[str, ...]
    blocker_reason: Optional[str]
    provider_semantic_status: Optional[str]
    pricing_authority: PricingAuthority
    selection_authority: SelectionAuthority
    score_matrix_audit: Optional[Mapping[str, Any]] = None
    specialist_evidence: Optional[Mapping[str, Any]] = None
