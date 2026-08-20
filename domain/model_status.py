"""Typed analytical capabilities and authorities for every ATHENA market.

Model maturity is retained as compatibility metadata. It is deliberately not
an execution authority: analytical mathematics, settlement support,
calibration, pricing, and selection are independent questions.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

from domain.markets import MarketId
from domain.win_either_half_features import PRE_MATCH_FEATURE_NAMES


class ModelStatus(str, Enum):
    """Legacy maturity label; never a pricing or selection permission."""

    ACTIVE = "ACTIVE"
    EXPERIMENTAL = "EXPERIMENTAL"
    DISABLED = "DISABLED"
    UNSUPPORTED = "UNSUPPORTED"


class MissingInputPolicy(str, Enum):
    DEFAULT_AND_DISCLOSE = "DEFAULT_AND_DISCLOSE"
    REJECT_MARKET = "REJECT_MARKET"


class AnalyticalProbabilityCapability(str, Enum):
    AVAILABLE = "AVAILABLE"
    BLOCKED = "BLOCKED"


class SettlementCapability(str, Enum):
    ORDINARY_EVENT_PROBABILITY = "ORDINARY_EVENT_PROBABILITY"
    FULL_SETTLEMENT_DISTRIBUTION = "FULL_SETTLEMENT_DISTRIBUTION"
    BLOCKED = "BLOCKED"


class ProbabilityInputNamespace(str, Enum):
    GENERIC_FIXTURE_MODEL_FEATURES = "GENERIC_FIXTURE_MODEL_FEATURES"
    SPECIALIZED_WEH_PRE_MATCH_FEATURES = "SPECIALIZED_WEH_PRE_MATCH_FEATURES"


class CalibrationStatus(str, Enum):
    MIXED_OR_WEAK_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED = (
        "MIXED_OR_WEAK_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED"
    )
    NOT_APPLICABLE_ANALYTICAL_CAPABILITY_BLOCKED = (
        "NOT_APPLICABLE_ANALYTICAL_CAPABILITY_BLOCKED"
    )
    FROZEN_STAGE_4B_CALIBRATION_RESEARCH_EVIDENCE = (
        "FROZEN_STAGE_4B_CALIBRATION_RESEARCH_EVIDENCE"
    )


class FreshConfirmationStatus(str, Enum):
    ZERO_COMMITTED_OBSERVATIONS = "ZERO_COMMITTED_OBSERVATIONS"
    NOT_APPLICABLE_ANALYTICAL_CAPABILITY_BLOCKED = (
        "NOT_APPLICABLE_ANALYTICAL_CAPABILITY_BLOCKED"
    )


class PricingAuthority(str, Enum):
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    AUTHORIZED = "AUTHORIZED"


class SelectionAuthority(str, Enum):
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    AUTHORIZED = "AUTHORIZED"


@dataclass(frozen=True)
class MarketModelStatus:
    status: ModelStatus
    probability_method: Optional[str]
    reason: str
    probability_input_namespace: ProbabilityInputNamespace
    probability_inputs: Tuple[str, ...]
    pricing_inputs: Tuple[str, ...]
    missing_input_policy: MissingInputPolicy
    analytical_probability_capability: AnalyticalProbabilityCapability
    settlement_capability: SettlementCapability
    calibration_status: CalibrationStatus
    fresh_confirmation_status: FreshConfirmationStatus
    pricing_authority: PricingAuthority
    selection_authority: SelectionAuthority

    def __post_init__(self) -> None:
        typed_values = (
            (self.status, ModelStatus, "status"),
            (
                self.analytical_probability_capability,
                AnalyticalProbabilityCapability,
                "analytical capability",
            ),
            (self.settlement_capability, SettlementCapability, "settlement capability"),
            (
                self.probability_input_namespace,
                ProbabilityInputNamespace,
                "probability input namespace",
            ),
            (self.calibration_status, CalibrationStatus, "calibration status"),
            (
                self.fresh_confirmation_status,
                FreshConfirmationStatus,
                "fresh confirmation status",
            ),
            (self.pricing_authority, PricingAuthority, "pricing authority"),
            (self.selection_authority, SelectionAuthority, "selection authority"),
            (self.missing_input_policy, MissingInputPolicy, "missing input policy"),
        )
        for value, expected_type, label in typed_values:
            if not isinstance(value, expected_type):
                raise TypeError(f"{label} must be typed")
        if type(self.probability_inputs) is not tuple:
            raise TypeError("probability_inputs must be an exact tuple")
        if type(self.pricing_inputs) is not tuple:
            raise TypeError("pricing_inputs must be an exact tuple")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must be non-empty")
        if (
            self.probability_input_namespace
            is ProbabilityInputNamespace.SPECIALIZED_WEH_PRE_MATCH_FEATURES
            and self.probability_inputs != PRE_MATCH_FEATURE_NAMES
        ):
            raise ValueError("specialized WEH input order differs from frozen contract")

        available = (
            self.analytical_probability_capability
            is AnalyticalProbabilityCapability.AVAILABLE
        )
        if available:
            if not isinstance(self.probability_method, str) or not self.probability_method:
                raise ValueError("analytically available market requires a method")
            if not self.probability_inputs:
                raise ValueError("analytically available market requires inputs")
            if self.settlement_capability is SettlementCapability.BLOCKED:
                raise ValueError("analytically available market needs settlement semantics")
        else:
            if self.probability_method is not None or self.probability_inputs:
                raise ValueError("blocked analytical market cannot declare a method or inputs")
            if self.settlement_capability is not SettlementCapability.BLOCKED:
                raise ValueError("blocked analytical market must block settlement")

    @property
    def analytically_available(self) -> bool:
        return (
            self.analytical_probability_capability
            is AnalyticalProbabilityCapability.AVAILABLE
        )

    @property
    def pricing_authorized(self) -> bool:
        return self.pricing_authority is PricingAuthority.AUTHORIZED

    @property
    def selectable(self) -> bool:
        """Compatibility property derived only from explicit authority."""

        return self.selection_authority is SelectionAuthority.AUTHORIZED


_PROBABILITY_INPUTS = (
    "home_form",
    "away_form",
    "home_elo",
    "away_elo",
    "fatigue",
    "live_data_freshness",
)
_PRICING_INPUTS = ("bookmaker_odds",)
_REVIEW_REQUIRED = (
    CalibrationStatus.MIXED_OR_WEAK_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED
)
_ZERO_CONFIRMATION = FreshConfirmationStatus.ZERO_COMMITTED_OBSERVATIONS
_NO_PRICING = PricingAuthority.NOT_AUTHORIZED
_NO_SELECTION = SelectionAuthority.NOT_AUTHORIZED


def _available(
    *,
    status: ModelStatus,
    probability_method: str,
    reason: str,
    settlement: SettlementCapability = SettlementCapability.ORDINARY_EVENT_PROBABILITY,
    probability_input_namespace: ProbabilityInputNamespace = (
        ProbabilityInputNamespace.GENERIC_FIXTURE_MODEL_FEATURES
    ),
    probability_inputs: Tuple[str, ...] = _PROBABILITY_INPUTS,
    missing_input_policy: MissingInputPolicy = MissingInputPolicy.DEFAULT_AND_DISCLOSE,
    calibration_status: CalibrationStatus = _REVIEW_REQUIRED,
) -> MarketModelStatus:
    return MarketModelStatus(
        status=status,
        probability_method=probability_method,
        reason=reason,
        probability_input_namespace=probability_input_namespace,
        probability_inputs=probability_inputs,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=missing_input_policy,
        analytical_probability_capability=AnalyticalProbabilityCapability.AVAILABLE,
        settlement_capability=settlement,
        calibration_status=calibration_status,
        fresh_confirmation_status=_ZERO_CONFIRMATION,
        pricing_authority=_NO_PRICING,
        selection_authority=_NO_SELECTION,
    )


def _blocked(reason: str) -> MarketModelStatus:
    return MarketModelStatus(
        status=ModelStatus.DISABLED,
        probability_method=None,
        reason=reason,
        probability_input_namespace=(
            ProbabilityInputNamespace.GENERIC_FIXTURE_MODEL_FEATURES
        ),
        probability_inputs=(),
        pricing_inputs=(),
        missing_input_policy=MissingInputPolicy.REJECT_MARKET,
        analytical_probability_capability=AnalyticalProbabilityCapability.BLOCKED,
        settlement_capability=SettlementCapability.BLOCKED,
        calibration_status=(
            CalibrationStatus.NOT_APPLICABLE_ANALYTICAL_CAPABILITY_BLOCKED
        ),
        fresh_confirmation_status=(
            FreshConfirmationStatus.NOT_APPLICABLE_ANALYTICAL_CAPABILITY_BLOCKED
        ),
        pricing_authority=_NO_PRICING,
        selection_authority=_NO_SELECTION,
    )


MODEL_STATUS_REGISTRY: Dict[MarketId, MarketModelStatus] = {
    MarketId.MATCH_RESULT: _available(
        status=ModelStatus.ACTIVE,
        probability_method="normalized_independent_poisson_score_matrix",
        reason=(
            "Regulation-time 1X2 probabilities are mechanically derivable from "
            "one normalized score matrix; calibration review remains unresolved "
            "and pricing/selection are not authorized."
        ),
    ),
    MarketId.ASIAN_HANDICAP: _available(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_asian_handicap_settlement",
        settlement=SettlementCapability.FULL_SETTLEMENT_DISTRIBUTION,
        reason=(
            "Integer, half-goal, and quarter-goal Asian Handicap full/half/push "
            "settlement masses are mechanically derivable from the normalized "
            "score matrix; this grants no price or selection authority."
        ),
    ),
    MarketId.TOTAL_GOALS: _available(
        status=ModelStatus.ACTIVE,
        probability_method="normalized_score_matrix_total_goals_half_line",
        reason=(
            "Over/under event probabilities are mechanically derivable for exact "
            "half-goal total lines; push-capable total settlements remain outside "
            "this capability."
        ),
    ),
    MarketId.DRAW_OR_OVER_2_5: _available(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_union_probability",
        reason="The draw-or-over event and its complement are exact matrix sums.",
    ),
    MarketId.AWAY_OR_OVER_2_5: _available(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_union_probability",
        reason="The away-or-over event and its complement are exact matrix sums.",
    ),
    MarketId.HOME_OR_OVER_2_5: _available(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_union_probability",
        reason="The home-or-over event and its complement are exact matrix sums.",
    ),
    MarketId.HOME_WIN_EITHER_HALF: _available(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="frozen_weh_stage4a4b_analytical_inference_v1",
        probability_input_namespace=(
            ProbabilityInputNamespace.SPECIALIZED_WEH_PRE_MATCH_FEATURES
        ),
        probability_inputs=PRE_MATCH_FEATURE_NAMES,
        missing_input_policy=MissingInputPolicy.REJECT_MARKET,
        calibration_status=(
            CalibrationStatus.FROZEN_STAGE_4B_CALIBRATION_RESEARCH_EVIDENCE
        ),
        reason=(
            "The frozen TRAIN-fitted Home WEH logistic model and reviewed "
            "isotonic calibration are prospectively callable from the exact "
            "specialized 74-feature namespace; pricing and selection remain "
            "unauthorized."
        ),
    ),
    MarketId.AWAY_WIN_EITHER_HALF: _available(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="frozen_weh_stage4a4b_analytical_inference_v1",
        probability_input_namespace=(
            ProbabilityInputNamespace.SPECIALIZED_WEH_PRE_MATCH_FEATURES
        ),
        probability_inputs=PRE_MATCH_FEATURE_NAMES,
        missing_input_policy=MissingInputPolicy.REJECT_MARKET,
        calibration_status=(
            CalibrationStatus.FROZEN_STAGE_4B_CALIBRATION_RESEARCH_EVIDENCE
        ),
        reason=(
            "The frozen TRAIN-fitted Away WEH logistic model and reviewed identity "
            "calibration are prospectively callable from the exact specialized "
            "74-feature namespace; pricing and selection remain unauthorized."
        ),
    ),
    MarketId.DOUBLE_CHANCE: _available(
        status=ModelStatus.ACTIVE,
        probability_method="normalized_score_matrix_result_sum",
        reason=(
            "Each overlapping double-chance event is the exact sum of its two "
            "covered regulation-time results."
        ),
    ),
    MarketId.BTTS: _available(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_btts",
        reason="BTTS YES and NO are complementary normalized-matrix events.",
    ),
    MarketId.DRAW_NO_BET: _available(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_draw_no_bet_settlement",
        settlement=SettlementCapability.FULL_SETTLEMENT_DISTRIBUTION,
        reason=(
            "HOME and AWAY Draw No Bet preserve exact win, draw-push, and loss "
            "mass; the settlement distribution is analytical evidence, not raw "
            "event probability or selection authority."
        ),
    ),
    MarketId.HOME_WIN_TO_NIL: _available(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_win_to_nil",
        reason="Home win-to-nil YES and NO are complementary matrix events.",
    ),
    MarketId.AWAY_WIN_TO_NIL: _available(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_win_to_nil",
        reason="Away win-to-nil YES and NO are complementary matrix events.",
    ),
    MarketId.MATCH_RESULT_1UP: _blocked(
        "Blocked because provider promotion rules and lead-path probability "
        "modelling are both required."
    ),
    MarketId.MATCH_RESULT_2UP: _blocked(
        "Blocked because provider promotion rules and lead-path probability "
        "modelling are both required."
    ),
}


if set(MODEL_STATUS_REGISTRY) != set(MarketId):
    missing = set(MarketId) - set(MODEL_STATUS_REGISTRY)
    extra = set(MODEL_STATUS_REGISTRY) - set(MarketId)
    raise RuntimeError(
        f"Model status registry is incomplete: missing={missing}, extra={extra}"
    )

_SETTLEMENT_DISTRIBUTION_MARKETS = {
    MarketId.ASIAN_HANDICAP,
    MarketId.DRAW_NO_BET,
}
if {
    market_id
    for market_id, definition in MODEL_STATUS_REGISTRY.items()
    if definition.settlement_capability
    is SettlementCapability.FULL_SETTLEMENT_DISTRIBUTION
} != _SETTLEMENT_DISTRIBUTION_MARKETS:
    raise RuntimeError("full-settlement capability market set drifted")

if any(
    definition.pricing_authority is not PricingAuthority.NOT_AUTHORIZED
    or definition.selection_authority is not SelectionAuthority.NOT_AUTHORIZED
    for definition in MODEL_STATUS_REGISTRY.values()
):
    raise RuntimeError("current market registry must grant no pricing/selection authority")


def get_model_status(market_id: MarketId) -> MarketModelStatus:
    return MODEL_STATUS_REGISTRY[MarketId(market_id)]


__all__ = [
    "AnalyticalProbabilityCapability",
    "CalibrationStatus",
    "FreshConfirmationStatus",
    "MODEL_STATUS_REGISTRY",
    "MarketModelStatus",
    "MissingInputPolicy",
    "ModelStatus",
    "PricingAuthority",
    "ProbabilityInputNamespace",
    "SelectionAuthority",
    "SettlementCapability",
    "get_model_status",
]
