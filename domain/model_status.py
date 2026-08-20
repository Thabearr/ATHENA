"""Canonical model/capability metadata for every ATHENA market.

This registry deliberately separates analytical model availability from pricing,
selection, and BET authority.  A market can have a mathematically valid research
probability model while all downstream bookmaker authorities remain false.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

from domain.markets import MarketId


class ModelStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPERIMENTAL = "EXPERIMENTAL"
    DISABLED = "DISABLED"
    UNSUPPORTED = "UNSUPPORTED"


class MissingInputPolicy(str, Enum):
    DEFAULT_AND_DISCLOSE = "DEFAULT_AND_DISCLOSE"
    REJECT_MARKET = "REJECT_MARKET"


class AnalyticalAvailability(str, Enum):
    """Whether ATHENA has an actual analytical model for the market."""

    AVAILABLE = "AVAILABLE"
    RESEARCH_MODEL_AVAILABLE = "RESEARCH_MODEL_AVAILABLE"
    PENDING_IMPLEMENTATION = "PENDING_IMPLEMENTATION"
    UNAVAILABLE = "UNAVAILABLE"


class SettlementCapability(str, Enum):
    """Shape of the analytical market result that must be preserved."""

    DIRECT_EVENT_PROBABILITY = "DIRECT_EVENT_PROBABILITY"
    OVERLAPPING_EVENT_PROBABILITIES = "OVERLAPPING_EVENT_PROBABILITIES"
    SETTLEMENT_DISTRIBUTION = "SETTLEMENT_DISTRIBUTION"
    SPECIALIZED_EVENT_MODEL = "SPECIALIZED_EVENT_MODEL"
    PROVIDER_RULES_AND_PATH_MODEL_REQUIRED = "PROVIDER_RULES_AND_PATH_MODEL_REQUIRED"


class CalibrationStatus(str, Enum):
    """Evidence status of the probability model, not a production authority."""

    FRESH_CONFIRMATION_PENDING = "FRESH_CONFIRMATION_PENDING"
    REVIEWED_RESEARCH_FINAL_TEST = "REVIEWED_RESEARCH_FINAL_TEST"
    PENDING_MODEL = "PENDING_MODEL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class MarketModelStatus:
    status: ModelStatus
    probability_method: Optional[str]
    reason: str
    probability_inputs: Tuple[str, ...]
    pricing_inputs: Tuple[str, ...]
    missing_input_policy: MissingInputPolicy
    analytical_availability: AnalyticalAvailability = AnalyticalAvailability.UNAVAILABLE
    settlement_capability: SettlementCapability = (
        SettlementCapability.DIRECT_EVENT_PROBABILITY
    )
    calibration_status: CalibrationStatus = CalibrationStatus.NOT_APPLICABLE
    pricing_authorized: bool = False
    selection_authorized: bool = False
    bet_authorized: bool = False

    @property
    def analytical_available(self) -> bool:
        return self.analytical_availability in {
            AnalyticalAvailability.AVAILABLE,
            AnalyticalAvailability.RESEARCH_MODEL_AVAILABLE,
        }

    @property
    def selectable(self) -> bool:
        """Legacy analytical-candidate eligibility, not selection authority.

        Existing runtime code still uses this compatibility property while the
        weekend-control work migrates consumers to the explicit authority
        fields above.  It must never be interpreted as SportyBet selection or
        BET authorization.
        """

        return self.status in {
            ModelStatus.ACTIVE,
            ModelStatus.EXPERIMENTAL,
        }


_PROBABILITY_INPUTS = (
    "home_form",
    "away_form",
    "home_elo",
    "away_elo",
    "fatigue",
    "live_data_freshness",
)
_PRICING_INPUTS = ("bookmaker_odds",)

_SCORE_MATRIX_CALIBRATION = CalibrationStatus.FRESH_CONFIRMATION_PENDING


MODEL_STATUS_REGISTRY: Dict[MarketId, MarketModelStatus] = {
    MarketId.MATCH_RESULT: MarketModelStatus(
        status=ModelStatus.ACTIVE,
        probability_method="normalized_independent_poisson_score_matrix",
        reason=(
            "Regulation-time result probabilities are derived from one "
            "normalized adaptive independent-Poisson score matrix."
        ),
        probability_inputs=_PROBABILITY_INPUTS,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=MissingInputPolicy.DEFAULT_AND_DISCLOSE,
        analytical_availability=AnalyticalAvailability.AVAILABLE,
        calibration_status=_SCORE_MATRIX_CALIBRATION,
    ),
    MarketId.ASIAN_HANDICAP: MarketModelStatus(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_asian_handicap_settlement",
        reason=(
            "Integer, half-goal, and quarter-goal Asian Handicap settlement is "
            "partitioned from the normalized score matrix into full-win, "
            "half-win, push, half-loss, and full-loss mass."
        ),
        probability_inputs=_PROBABILITY_INPUTS,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=MissingInputPolicy.DEFAULT_AND_DISCLOSE,
        analytical_availability=AnalyticalAvailability.AVAILABLE,
        settlement_capability=SettlementCapability.SETTLEMENT_DISTRIBUTION,
        calibration_status=_SCORE_MATRIX_CALIBRATION,
    ),
    MarketId.TOTAL_GOALS: MarketModelStatus(
        status=ModelStatus.ACTIVE,
        probability_method="normalized_score_matrix_total_goals",
        reason=(
            "Goal-line probabilities are summed directly from the normalized "
            "adaptive independent-Poisson score matrix.  The common analytical "
            "projector currently admits half-goal lines only so push mass is "
            "never discarded."
        ),
        probability_inputs=_PROBABILITY_INPUTS,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=MissingInputPolicy.DEFAULT_AND_DISCLOSE,
        analytical_availability=AnalyticalAvailability.AVAILABLE,
        calibration_status=_SCORE_MATRIX_CALIBRATION,
    ),
    MarketId.DRAW_OR_OVER_2_5: MarketModelStatus(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_union_probability",
        reason=(
            "The result-or-total probability is derived as an exact "
            "score-matrix union; fresh confirmation remains pending."
        ),
        probability_inputs=_PROBABILITY_INPUTS,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=MissingInputPolicy.DEFAULT_AND_DISCLOSE,
        analytical_availability=AnalyticalAvailability.AVAILABLE,
        calibration_status=_SCORE_MATRIX_CALIBRATION,
    ),
    MarketId.AWAY_OR_OVER_2_5: MarketModelStatus(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_union_probability",
        reason=(
            "The result-or-total probability is derived as an exact "
            "score-matrix union; fresh confirmation remains pending."
        ),
        probability_inputs=_PROBABILITY_INPUTS,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=MissingInputPolicy.DEFAULT_AND_DISCLOSE,
        analytical_availability=AnalyticalAvailability.AVAILABLE,
        calibration_status=_SCORE_MATRIX_CALIBRATION,
    ),
    MarketId.HOME_OR_OVER_2_5: MarketModelStatus(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_union_probability",
        reason=(
            "The result-or-total probability is derived as an exact "
            "score-matrix union; fresh confirmation remains pending."
        ),
        probability_inputs=_PROBABILITY_INPUTS,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=MissingInputPolicy.DEFAULT_AND_DISCLOSE,
        analytical_availability=AnalyticalAvailability.AVAILABLE,
        calibration_status=_SCORE_MATRIX_CALIBRATION,
    ),
    MarketId.HOME_WIN_EITHER_HALF: MarketModelStatus(
        status=ModelStatus.DISABLED,
        probability_method=(
            "win_either_half_logistic_l2_c0.1_v1_with_selected_home_isotonic_calibration"
        ),
        reason=(
            "A reviewed Home Win Either Half research model and independent "
            "final-test calibration evidence exist.  Runtime prospective "
            "inference still requires its dedicated weekend-sprint wrapper; "
            "production/selection authority remains false."
        ),
        probability_inputs=(),
        pricing_inputs=(),
        missing_input_policy=MissingInputPolicy.REJECT_MARKET,
        analytical_availability=AnalyticalAvailability.RESEARCH_MODEL_AVAILABLE,
        settlement_capability=SettlementCapability.SPECIALIZED_EVENT_MODEL,
        calibration_status=CalibrationStatus.REVIEWED_RESEARCH_FINAL_TEST,
    ),
    MarketId.AWAY_WIN_EITHER_HALF: MarketModelStatus(
        status=ModelStatus.DISABLED,
        probability_method=(
            "win_either_half_logistic_l2_c0.1_v1_with_selected_away_identity_calibration"
        ),
        reason=(
            "A reviewed Away Win Either Half research model and independent "
            "final-test calibration evidence exist.  Runtime prospective "
            "inference still requires its dedicated weekend-sprint wrapper; "
            "production/selection authority remains false."
        ),
        probability_inputs=(),
        pricing_inputs=(),
        missing_input_policy=MissingInputPolicy.REJECT_MARKET,
        analytical_availability=AnalyticalAvailability.RESEARCH_MODEL_AVAILABLE,
        settlement_capability=SettlementCapability.SPECIALIZED_EVENT_MODEL,
        calibration_status=CalibrationStatus.REVIEWED_RESEARCH_FINAL_TEST,
    ),
    MarketId.DOUBLE_CHANCE: MarketModelStatus(
        status=ModelStatus.ACTIVE,
        probability_method="normalized_score_matrix_result_sum",
        reason=(
            "Each covered event is the explicit sum of regulation-time "
            "score-matrix result probabilities.  The three displayed events "
            "overlap and are not a probability partition."
        ),
        probability_inputs=_PROBABILITY_INPUTS,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=MissingInputPolicy.DEFAULT_AND_DISCLOSE,
        analytical_availability=AnalyticalAvailability.AVAILABLE,
        settlement_capability=SettlementCapability.OVERLAPPING_EVENT_PROBABILITIES,
        calibration_status=_SCORE_MATRIX_CALIBRATION,
    ),
    MarketId.BTTS: MarketModelStatus(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_btts",
        reason=(
            "Both-teams-to-score probability is derived from the normalized "
            "matrix; fresh confirmation remains pending."
        ),
        probability_inputs=_PROBABILITY_INPUTS,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=MissingInputPolicy.DEFAULT_AND_DISCLOSE,
        analytical_availability=AnalyticalAvailability.AVAILABLE,
        calibration_status=_SCORE_MATRIX_CALIBRATION,
    ),
    MarketId.DRAW_NO_BET: MarketModelStatus(
        status=ModelStatus.DISABLED,
        probability_method="normalized_score_matrix_draw_no_bet_settlement",
        reason=(
            "Draw No Bet is analytically available as exact win/push/loss "
            "settlement mass from the normalized score matrix.  It remains "
            "disabled for legacy selection because fresh pricing and production "
            "authority are separate gates."
        ),
        probability_inputs=_PROBABILITY_INPUTS,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=MissingInputPolicy.REJECT_MARKET,
        analytical_availability=AnalyticalAvailability.AVAILABLE,
        settlement_capability=SettlementCapability.SETTLEMENT_DISTRIBUTION,
        calibration_status=_SCORE_MATRIX_CALIBRATION,
    ),
    MarketId.HOME_WIN_TO_NIL: MarketModelStatus(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_win_to_nil",
        reason=(
            "The event is derived directly from the normalized score matrix; "
            "fresh confirmation remains pending."
        ),
        probability_inputs=_PROBABILITY_INPUTS,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=MissingInputPolicy.DEFAULT_AND_DISCLOSE,
        analytical_availability=AnalyticalAvailability.AVAILABLE,
        calibration_status=_SCORE_MATRIX_CALIBRATION,
    ),
    MarketId.AWAY_WIN_TO_NIL: MarketModelStatus(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_win_to_nil",
        reason=(
            "The event is derived directly from the normalized score matrix; "
            "fresh confirmation remains pending."
        ),
        probability_inputs=_PROBABILITY_INPUTS,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=MissingInputPolicy.DEFAULT_AND_DISCLOSE,
        analytical_availability=AnalyticalAvailability.AVAILABLE,
        calibration_status=_SCORE_MATRIX_CALIBRATION,
    ),
    MarketId.MATCH_RESULT_1UP: MarketModelStatus(
        status=ModelStatus.DISABLED,
        probability_method=None,
        reason=(
            "The 1UP analytical target is part of the 15/15 weekend sprint, "
            "but exact provider promotion semantics plus a lead-path "
            "probability model are still pending implementation."
        ),
        probability_inputs=(),
        pricing_inputs=(),
        missing_input_policy=MissingInputPolicy.REJECT_MARKET,
        analytical_availability=AnalyticalAvailability.PENDING_IMPLEMENTATION,
        settlement_capability=(
            SettlementCapability.PROVIDER_RULES_AND_PATH_MODEL_REQUIRED
        ),
        calibration_status=CalibrationStatus.PENDING_MODEL,
    ),
    MarketId.MATCH_RESULT_2UP: MarketModelStatus(
        status=ModelStatus.DISABLED,
        probability_method=None,
        reason=(
            "The 2UP analytical target is part of the 15/15 weekend sprint, "
            "but exact provider promotion semantics plus a lead-path "
            "probability model are still pending implementation."
        ),
        probability_inputs=(),
        pricing_inputs=(),
        missing_input_policy=MissingInputPolicy.REJECT_MARKET,
        analytical_availability=AnalyticalAvailability.PENDING_IMPLEMENTATION,
        settlement_capability=(
            SettlementCapability.PROVIDER_RULES_AND_PATH_MODEL_REQUIRED
        ),
        calibration_status=CalibrationStatus.PENDING_MODEL,
    ),
}


if set(MODEL_STATUS_REGISTRY) != set(MarketId):
    missing = set(MarketId) - set(MODEL_STATUS_REGISTRY)
    extra = set(MODEL_STATUS_REGISTRY) - set(MarketId)
    raise RuntimeError(
        f"Model status registry is incomplete: missing={missing}, extra={extra}"
    )


def get_model_status(market_id: MarketId) -> MarketModelStatus:
    return MODEL_STATUS_REGISTRY[MarketId(market_id)]


__all__ = [
    "AnalyticalAvailability",
    "CalibrationStatus",
    "MODEL_STATUS_REGISTRY",
    "MarketModelStatus",
    "MissingInputPolicy",
    "ModelStatus",
    "SettlementCapability",
    "get_model_status",
]
