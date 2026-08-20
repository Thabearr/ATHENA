"""Exact 1UP/2UP lead-path probabilities from a normalized ScoreMatrix.

Conditional on final Home/Away goal counts under the independent homogeneous
Poisson model, every ordering of those goal labels is equiprobable.  This
module counts those orderings exactly and divides only at the conditional
probability boundary.  No Monte Carlo path is used.  It models normal
regulation-time football only and accepts no bookmaker price.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
from typing import Any

from domain.markets import MARKET_REGISTRY, MarketId, OutcomeId
from domain.model_status import (
    AnalyticalProbabilityCapability,
    PricingAuthority,
    SelectionAuthority,
    get_model_status,
)
from domain.score_matrix import ScoreMatrix
from domain.score_matrix_market_probabilities import (
    AnalyticalEventProbability,
    MarketTopology,
)
from domain.sportybet_early_payout_settlement import (
    reviewed_sportybet_early_payout_settlement_receipt,
    sha256_sportybet_early_payout_settlement_receipt,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-early-payout-lead-path-analytical-projection-v1"
PROBABILITY_METHOD = "independent_poisson_conditional_goal_order_lead_path_v1"
_MARKET_THRESHOLDS = {
    MarketId.MATCH_RESULT_1UP: 1,
    MarketId.MATCH_RESULT_2UP: 2,
}
_SAFETY = (
    ("bet_authorized", False),
    ("execution_authorized", False),
    ("fresh_price_authorized", False),
    ("market_activation_authorized", False),
    ("pricing_authorized", False),
    ("production_approval_authorized", False),
    ("selection_authorized", False),
    ("value_authorized", False),
)


class EarlyPayoutLeadPathError(ValueError):
    """Raised when an early-payout analytical claim is not defensible."""


def _non_negative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise EarlyPayoutLeadPathError(f"{label} must be an exact non-negative int")
    return value


def _threshold(value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise EarlyPayoutLeadPathError("threshold must be an exact positive int")
    return value


def _probability(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise EarlyPayoutLeadPathError(f"{label} must be a finite probability")
    return float(value)


@dataclass(frozen=True)
class ConditionalLeadHitProbabilities:
    home_goals: int
    away_goals: int
    threshold: int
    total_orderings: int
    home_only_orderings: int
    away_only_orderings: int
    both_orderings: int
    neither_orderings: int
    home_hit_probability: float
    away_hit_probability: float

    def __post_init__(self) -> None:
        home = _non_negative_int(self.home_goals, "home_goals")
        away = _non_negative_int(self.away_goals, "away_goals")
        threshold = _threshold(self.threshold)
        counts = (
            _non_negative_int(self.home_only_orderings, "home_only_orderings"),
            _non_negative_int(self.away_only_orderings, "away_only_orderings"),
            _non_negative_int(self.both_orderings, "both_orderings"),
            _non_negative_int(self.neither_orderings, "neither_orderings"),
        )
        total = math.comb(home + away, home)
        if self.total_orderings != total or sum(counts) != total:
            raise EarlyPayoutLeadPathError("conditional path counts do not partition")
        expected_home = (counts[0] + counts[2]) / total
        expected_away = (counts[1] + counts[2]) / total
        if self.home_hit_probability != expected_home:
            raise EarlyPayoutLeadPathError("home hit probability differs from counts")
        if self.away_hit_probability != expected_away:
            raise EarlyPayoutLeadPathError("away hit probability differs from counts")
        _probability(self.home_hit_probability, "home_hit_probability")
        _probability(self.away_hit_probability, "away_hit_probability")
        object.__setattr__(self, "threshold", threshold)

    def to_dict(self) -> dict[str, Any]:
        return {
            "home_goals": self.home_goals,
            "away_goals": self.away_goals,
            "threshold": self.threshold,
            "total_orderings": self.total_orderings,
            "home_only_orderings": self.home_only_orderings,
            "away_only_orderings": self.away_only_orderings,
            "both_orderings": self.both_orderings,
            "neither_orderings": self.neither_orderings,
            "home_hit_probability": self.home_hit_probability,
            "away_hit_probability": self.away_hit_probability,
        }


def conditional_lead_hit_probabilities(
    home_goals: int,
    away_goals: int,
    threshold: int,
) -> ConditionalLeadHitProbabilities:
    """Count exact H/A goal-label paths for one final score and threshold."""

    home = _non_negative_int(home_goals, "home_goals")
    away = _non_negative_int(away_goals, "away_goals")
    lead = _threshold(threshold)
    return _conditional_lead_hit_probabilities_validated(home, away, lead)


@lru_cache(maxsize=None)
def _conditional_lead_hit_probabilities_validated(
    home: int,
    away: int,
    lead: int,
) -> ConditionalLeadHitProbabilities:
    # State is (home goals used, away goals used, home hit, away hit) -> paths.
    states: dict[tuple[int, int, bool, bool], int] = {(0, 0, False, False): 1}
    for _ in range(home + away):
        advanced: dict[tuple[int, int, bool, bool], int] = {}
        for (used_home, used_away, hit_home, hit_away), count in states.items():
            if used_home < home:
                next_home = used_home + 1
                next_hit_home = hit_home or next_home - used_away >= lead
                key = (next_home, used_away, next_hit_home, hit_away)
                advanced[key] = advanced.get(key, 0) + count
            if used_away < away:
                next_away = used_away + 1
                next_hit_away = hit_away or next_away - used_home >= lead
                key = (used_home, next_away, hit_home, next_hit_away)
                advanced[key] = advanced.get(key, 0) + count
        states = advanced
    partition = {(False, False): 0, (True, False): 0, (False, True): 0, (True, True): 0}
    for (used_home, used_away, hit_home, hit_away), count in states.items():
        if (used_home, used_away) != (home, away):
            raise EarlyPayoutLeadPathError("conditional path did not reach final score")
        partition[(hit_home, hit_away)] += count
    total = math.comb(home + away, home)
    return ConditionalLeadHitProbabilities(
        home_goals=home,
        away_goals=away,
        threshold=lead,
        total_orderings=total,
        home_only_orderings=partition[(True, False)],
        away_only_orderings=partition[(False, True)],
        both_orderings=partition[(True, True)],
        neither_orderings=partition[(False, False)],
        home_hit_probability=(
            partition[(True, False)] + partition[(True, True)]
        )
        / total,
        away_hit_probability=(
            partition[(False, True)] + partition[(True, True)]
        )
        / total,
    )


def canonical_score_matrix_identity_bytes(score_matrix: ScoreMatrix) -> bytes:
    """Canonical identity receipt for the exact normalized matrix consumed."""

    if type(score_matrix) is not ScoreMatrix:
        raise TypeError("score_matrix must be an exact ScoreMatrix")
    payload = {
        "audit": score_matrix.audit_dict(),
        "probabilities": [
            [home, away, probability]
            for (home, away), probability in sorted(score_matrix.probabilities.items())
        ],
        "raw_probabilities": [
            [home, away, probability]
            for (home, away), probability in sorted(
                score_matrix.raw_probabilities.items()
            )
        ],
    }
    try:
        return (
            json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise EarlyPayoutLeadPathError("score matrix identity is not canonical") from exc


def sha256_score_matrix_identity(score_matrix: ScoreMatrix) -> str:
    return hashlib.sha256(canonical_score_matrix_identity_bytes(score_matrix)).hexdigest()


@dataclass(frozen=True)
class EarlyPayoutAnalyticalProjection:
    schema_version: int
    dataset_name: str
    market_id: MarketId
    probability_method: str
    topology: MarketTopology
    lead_threshold: int
    score_matrix_sha256: str
    provider_settlement_receipt_sha256: str
    event_probabilities: tuple[AnalyticalEventProbability, ...]
    analytical_prediction_authorized: bool
    abandonment_probability_modeled: bool
    safety: tuple[tuple[str, bool], ...]

    def __post_init__(self) -> None:
        if (self.schema_version, self.dataset_name) != (SCHEMA_VERSION, DATASET_NAME):
            raise EarlyPayoutLeadPathError("projection identity drifted")
        if type(self.market_id) is not MarketId or self.market_id not in _MARKET_THRESHOLDS:
            raise EarlyPayoutLeadPathError("projection market is not 1UP/2UP")
        status = get_model_status(self.market_id)
        if (
            status.analytical_probability_capability
            is not AnalyticalProbabilityCapability.AVAILABLE
            or status.probability_method != PROBABILITY_METHOD
            or self.probability_method != PROBABILITY_METHOD
        ):
            raise EarlyPayoutLeadPathError("registry analytical method drifted")
        if (
            status.pricing_authority is not PricingAuthority.NOT_AUTHORIZED
            or status.selection_authority is not SelectionAuthority.NOT_AUTHORIZED
        ):
            raise EarlyPayoutLeadPathError("registry authority expanded")
        if self.topology is not MarketTopology.OVERLAPPING_EVENTS:
            raise EarlyPayoutLeadPathError("early-payout topology must overlap")
        if self.lead_threshold != _MARKET_THRESHOLDS[self.market_id]:
            raise EarlyPayoutLeadPathError("lead threshold drifted")
        for value, label in (
            (self.score_matrix_sha256, "score matrix SHA-256"),
            (self.provider_settlement_receipt_sha256, "settlement receipt SHA-256"),
        ):
            if type(value) is not str or len(value) != 64 or any(
                char not in "0123456789abcdef" for char in value
            ):
                raise EarlyPayoutLeadPathError(f"{label} is invalid")
        receipt = reviewed_sportybet_early_payout_settlement_receipt()
        if self.provider_settlement_receipt_sha256 != (
            sha256_sportybet_early_payout_settlement_receipt(receipt)
        ):
            raise EarlyPayoutLeadPathError("provider settlement receipt drifted")
        if type(self.event_probabilities) is not tuple or any(
            type(item) is not AnalyticalEventProbability
            for item in self.event_probabilities
        ):
            raise EarlyPayoutLeadPathError("event probability type drifted")
        if tuple(item.outcome_id for item in self.event_probabilities) != (
            MARKET_REGISTRY[self.market_id].supported_outcomes
        ):
            raise EarlyPayoutLeadPathError("canonical outcome order drifted")
        detached = tuple(
            AnalyticalEventProbability(item.outcome_id, item.probability)
            for item in self.event_probabilities
        )
        if self.analytical_prediction_authorized is not True:
            raise EarlyPayoutLeadPathError("analytical prediction must be authorized")
        if self.abandonment_probability_modeled is not False:
            raise EarlyPayoutLeadPathError("abandonment probability cannot be invented")
        if self.safety != _SAFETY:
            raise EarlyPayoutLeadPathError("projection downstream safety drifted")
        object.__setattr__(self, "event_probabilities", detached)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "market_id": self.market_id.value,
            "probability_method": self.probability_method,
            "topology": self.topology.value,
            "lead_threshold": self.lead_threshold,
            "score_matrix_sha256": self.score_matrix_sha256,
            "provider_settlement_receipt_sha256": (
                self.provider_settlement_receipt_sha256
            ),
            "event_probabilities": [item.to_dict() for item in self.event_probabilities],
            "analytical_prediction_authorized": self.analytical_prediction_authorized,
            "abandonment_probability_modeled": self.abandonment_probability_modeled,
            "safety": dict(self.safety),
        }


def project_early_payout_market(
    score_matrix: ScoreMatrix,
    market_id: MarketId,
) -> EarlyPayoutAnalyticalProjection:
    """Project exact normal-completion 1UP/2UP events from one ScoreMatrix."""

    if type(score_matrix) is not ScoreMatrix:
        raise TypeError("score_matrix must be an exact ScoreMatrix")
    if type(market_id) is not MarketId or market_id not in _MARKET_THRESHOLDS:
        raise EarlyPayoutLeadPathError("market_id must be exact 1UP or 2UP MarketId")
    threshold = _MARKET_THRESHOLDS[market_id]
    weighted_home: list[float] = []
    weighted_away: list[float] = []
    draw_mass: list[float] = []
    for (home_goals, away_goals), cell_probability in sorted(
        score_matrix.probabilities.items()
    ):
        conditional = conditional_lead_hit_probabilities(
            home_goals, away_goals, threshold
        )
        home_event = conditional.home_hit_probability
        away_event = conditional.away_hit_probability
        if threshold == 2:
            # The official product is ordinary 1X2 with an earlier 2UP trigger.
            home_event = 1.0 if home_goals > away_goals else home_event
            away_event = 1.0 if away_goals > home_goals else away_event
        weighted_home.append(cell_probability * home_event)
        weighted_away.append(cell_probability * away_event)
        if home_goals == away_goals:
            draw_mass.append(cell_probability)
    receipt = reviewed_sportybet_early_payout_settlement_receipt()
    return EarlyPayoutAnalyticalProjection(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        market_id=market_id,
        probability_method=PROBABILITY_METHOD,
        topology=MarketTopology.OVERLAPPING_EVENTS,
        lead_threshold=threshold,
        score_matrix_sha256=sha256_score_matrix_identity(score_matrix),
        provider_settlement_receipt_sha256=(
            sha256_sportybet_early_payout_settlement_receipt(receipt)
        ),
        event_probabilities=(
            AnalyticalEventProbability(OutcomeId.HOME, math.fsum(weighted_home)),
            AnalyticalEventProbability(OutcomeId.DRAW, math.fsum(draw_mass)),
            AnalyticalEventProbability(OutcomeId.AWAY, math.fsum(weighted_away)),
        ),
        analytical_prediction_authorized=True,
        abandonment_probability_modeled=False,
        safety=_SAFETY,
    )


def canonical_early_payout_analytical_projection_bytes(
    projection: EarlyPayoutAnalyticalProjection,
) -> bytes:
    if type(projection) is not EarlyPayoutAnalyticalProjection:
        raise TypeError("projection must be exact EarlyPayoutAnalyticalProjection")
    rebuilt = EarlyPayoutAnalyticalProjection(
        schema_version=projection.schema_version,
        dataset_name=projection.dataset_name,
        market_id=projection.market_id,
        probability_method=projection.probability_method,
        topology=projection.topology,
        lead_threshold=projection.lead_threshold,
        score_matrix_sha256=projection.score_matrix_sha256,
        provider_settlement_receipt_sha256=(
            projection.provider_settlement_receipt_sha256
        ),
        event_probabilities=tuple(projection.event_probabilities),
        analytical_prediction_authorized=projection.analytical_prediction_authorized,
        abandonment_probability_modeled=projection.abandonment_probability_modeled,
        safety=tuple(projection.safety),
    )
    return (
        json.dumps(
            rebuilt.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha256_early_payout_analytical_projection(
    projection: EarlyPayoutAnalyticalProjection,
) -> str:
    return hashlib.sha256(
        canonical_early_payout_analytical_projection_bytes(projection)
    ).hexdigest()


__all__ = [
    "ConditionalLeadHitProbabilities",
    "DATASET_NAME",
    "EarlyPayoutAnalyticalProjection",
    "EarlyPayoutLeadPathError",
    "PROBABILITY_METHOD",
    "SCHEMA_VERSION",
    "canonical_early_payout_analytical_projection_bytes",
    "canonical_score_matrix_identity_bytes",
    "conditional_lead_hit_probabilities",
    "project_early_payout_market",
    "sha256_early_payout_analytical_projection",
    "sha256_score_matrix_identity",
]
