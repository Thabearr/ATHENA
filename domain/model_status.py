"""Canonical model availability metadata for every ATHENA market."""

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


@dataclass(frozen=True)
class MarketModelStatus:
    status: ModelStatus
    probability_method: Optional[str]
    reason: str
    probability_inputs: Tuple[str, ...]
    pricing_inputs: Tuple[str, ...]
    missing_input_policy: MissingInputPolicy

    @property
    def selectable(self) -> bool:
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
    ),
    MarketId.ASIAN_HANDICAP: MarketModelStatus(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_handicap_cover",
        reason=(
            "Only exact half-goal Asian Handicap cover probabilities are "
            "derived from the normalized matrix; integer, quarter-goal, and "
            "push-aware settlements remain unavailable."
        ),
        probability_inputs=_PROBABILITY_INPUTS,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=MissingInputPolicy.DEFAULT_AND_DISCLOSE,
    ),
    MarketId.TOTAL_GOALS: MarketModelStatus(
        status=ModelStatus.ACTIVE,
        probability_method="normalized_score_matrix_total_goals",
        reason=(
            "Goal-line probabilities are summed directly from the normalized "
            "adaptive independent-Poisson score matrix."
        ),
        probability_inputs=_PROBABILITY_INPUTS,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=MissingInputPolicy.DEFAULT_AND_DISCLOSE,
    ),
    MarketId.DRAW_OR_OVER_2_5: MarketModelStatus(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_union_probability",
        reason=(
            "The result-or-total probability is derived as a score-matrix "
            "union and remains experimental pending calibration."
        ),
        probability_inputs=_PROBABILITY_INPUTS,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=MissingInputPolicy.DEFAULT_AND_DISCLOSE,
    ),
    MarketId.AWAY_OR_OVER_2_5: MarketModelStatus(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_union_probability",
        reason=(
            "The result-or-total probability is derived as a score-matrix "
            "union and remains experimental pending calibration."
        ),
        probability_inputs=_PROBABILITY_INPUTS,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=MissingInputPolicy.DEFAULT_AND_DISCLOSE,
    ),
    MarketId.HOME_OR_OVER_2_5: MarketModelStatus(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_union_probability",
        reason=(
            "The result-or-total probability is derived as a score-matrix "
            "union and remains experimental pending calibration."
        ),
        probability_inputs=_PROBABILITY_INPUTS,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=MissingInputPolicy.DEFAULT_AND_DISCLOSE,
    ),
    MarketId.HOME_WIN_EITHER_HALF: MarketModelStatus(
        status=ModelStatus.DISABLED,
        probability_method=None,
        reason=(
            "Disabled until ATHENA has a defensible half-by-half probability "
            "model."
        ),
        probability_inputs=(),
        pricing_inputs=(),
        missing_input_policy=MissingInputPolicy.REJECT_MARKET,
    ),
    MarketId.AWAY_WIN_EITHER_HALF: MarketModelStatus(
        status=ModelStatus.DISABLED,
        probability_method=None,
        reason=(
            "Disabled until ATHENA has a defensible half-by-half probability "
            "model."
        ),
        probability_inputs=(),
        pricing_inputs=(),
        missing_input_policy=MissingInputPolicy.REJECT_MARKET,
    ),
    MarketId.DOUBLE_CHANCE: MarketModelStatus(
        status=ModelStatus.ACTIVE,
        probability_method="normalized_score_matrix_result_sum",
        reason=(
            "Each covered outcome is the explicit sum of regulation-time "
            "score-matrix result probabilities."
        ),
        probability_inputs=_PROBABILITY_INPUTS,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=MissingInputPolicy.DEFAULT_AND_DISCLOSE,
    ),
    MarketId.BTTS: MarketModelStatus(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_btts",
        reason=(
            "Both-teams-to-score probability is derived from the normalized "
            "matrix; calibration is still required."
        ),
        probability_inputs=_PROBABILITY_INPUTS,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=MissingInputPolicy.DEFAULT_AND_DISCLOSE,
    ),
    MarketId.DRAW_NO_BET: MarketModelStatus(
        status=ModelStatus.DISABLED,
        probability_method=None,
        reason=(
            "Disabled until ATHENA implements draw-push-aware probability and "
            "value semantics; the full-time-win proxy is not selectable."
        ),
        probability_inputs=(),
        pricing_inputs=(),
        missing_input_policy=MissingInputPolicy.REJECT_MARKET,
    ),
    MarketId.HOME_WIN_TO_NIL: MarketModelStatus(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_win_to_nil",
        reason=(
            "The event is derived directly from the normalized score matrix "
            "and remains experimental pending calibration."
        ),
        probability_inputs=_PROBABILITY_INPUTS,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=MissingInputPolicy.DEFAULT_AND_DISCLOSE,
    ),
    MarketId.AWAY_WIN_TO_NIL: MarketModelStatus(
        status=ModelStatus.EXPERIMENTAL,
        probability_method="normalized_score_matrix_win_to_nil",
        reason=(
            "The event is derived directly from the normalized score matrix "
            "and remains experimental pending calibration."
        ),
        probability_inputs=_PROBABILITY_INPUTS,
        pricing_inputs=_PRICING_INPUTS,
        missing_input_policy=MissingInputPolicy.DEFAULT_AND_DISCLOSE,
    ),
    MarketId.MATCH_RESULT_1UP: MarketModelStatus(
        status=ModelStatus.DISABLED,
        probability_method=None,
        reason=(
            "Disabled because early-payout settlement requires provider rules "
            "and a lead-path probability model."
        ),
        probability_inputs=(),
        pricing_inputs=(),
        missing_input_policy=MissingInputPolicy.REJECT_MARKET,
    ),
    MarketId.MATCH_RESULT_2UP: MarketModelStatus(
        status=ModelStatus.DISABLED,
        probability_method=None,
        reason=(
            "Disabled because early-payout settlement requires provider rules "
            "and a lead-path probability model."
        ),
        probability_inputs=(),
        pricing_inputs=(),
        missing_input_policy=MissingInputPolicy.REJECT_MARKET,
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
    "MODEL_STATUS_REGISTRY",
    "MarketModelStatus",
    "MissingInputPolicy",
    "ModelStatus",
    "get_model_status",
]
