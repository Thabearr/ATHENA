"""Helpers for all-market Shadow probability settlement (PR C)."""
from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping, Optional

from domain.early_payout_lead_path_probabilities import EarlyPayoutAnalyticalProjection
from domain.markets import MARKET_REGISTRY, MarketId
from domain.model_status import (
    AnalyticalProbabilityCapability,
    PricingAuthority,
    SelectionAuthority,
    SettlementCapability,
    get_model_status,
)
from domain.score_matrix_market_probabilities import (
    AnalyticalEventProbability,
    ScoreMatrixMarketProjection,
)
from domain.win_either_half_inference import WinEitherHalfAnalyticalPrediction
from domain._all_market_shadow_types import (
    ShadowDisposition,
    ShadowMarketAssessment,
)

def _blocked_assessment(
    market_id: MarketId,
    disposition: ShadowDisposition,
    *,
    missing_inputs: tuple[str, ...] = (),
    blocker_reason: Optional[str] = None,
    provider_semantic_status: Optional[str] = None,
) -> ShadowMarketAssessment:
    status = get_model_status(market_id)
    definition = MARKET_REGISTRY[market_id]
    return ShadowMarketAssessment(
        market_id=market_id,
        market_family=definition.family,
        disposition=disposition,
        probability_method=None,
        probability_input_namespace=None,
        analytical_capability=AnalyticalProbabilityCapability.BLOCKED,
        settlement_capability=SettlementCapability.BLOCKED,
        event_probabilities=(),
        settlement_distributions=(),
        required_inputs=status.probability_inputs,
        missing_inputs=missing_inputs,
        blocker_reason=blocker_reason or status.reason,
        provider_semantic_status=provider_semantic_status,
        pricing_authority=PricingAuthority.NOT_AUTHORIZED,
        selection_authority=SelectionAuthority.NOT_AUTHORIZED,
    )


def _from_score_matrix_projection(
    projection: ScoreMatrixMarketProjection,
    *,
    disposition: ShadowDisposition,
    score_matrix_audit: Mapping[str, Any],
    provider_semantic_status: Optional[str] = None,
) -> ShadowMarketAssessment:
    status = get_model_status(projection.market_id)
    definition = MARKET_REGISTRY[projection.market_id]
    return ShadowMarketAssessment(
        market_id=projection.market_id,
        market_family=definition.family,
        disposition=disposition,
        probability_method=projection.probability_method,
        probability_input_namespace=status.probability_input_namespace.value,
        analytical_capability=AnalyticalProbabilityCapability.AVAILABLE,
        settlement_capability=status.settlement_capability,
        event_probabilities=tuple(projection.event_probabilities),
        settlement_distributions=tuple(projection.settlement_distributions),
        required_inputs=status.probability_inputs,
        missing_inputs=(),
        blocker_reason=None,
        provider_semantic_status=provider_semantic_status,
        pricing_authority=PricingAuthority.NOT_AUTHORIZED,
        selection_authority=SelectionAuthority.NOT_AUTHORIZED,
        score_matrix_audit=MappingProxyType(dict(score_matrix_audit)),
    )


def _from_early_payout(
    projection: EarlyPayoutAnalyticalProjection,
    *,
    disposition: ShadowDisposition,
    score_matrix_audit: Mapping[str, Any],
    provider_semantic_status: Optional[str] = None,
) -> ShadowMarketAssessment:
    status = get_model_status(projection.market_id)
    definition = MARKET_REGISTRY[projection.market_id]
    return ShadowMarketAssessment(
        market_id=projection.market_id,
        market_family=definition.family,
        disposition=disposition,
        probability_method=projection.probability_method,
        probability_input_namespace=status.probability_input_namespace.value,
        analytical_capability=AnalyticalProbabilityCapability.AVAILABLE,
        settlement_capability=status.settlement_capability,
        event_probabilities=tuple(projection.event_probabilities),
        settlement_distributions=(),
        required_inputs=status.probability_inputs,
        missing_inputs=(),
        blocker_reason=None,
        provider_semantic_status=provider_semantic_status,
        pricing_authority=PricingAuthority.NOT_AUTHORIZED,
        selection_authority=SelectionAuthority.NOT_AUTHORIZED,
        score_matrix_audit=MappingProxyType(dict(score_matrix_audit)),
        specialist_evidence=MappingProxyType(
            {
                "lead_threshold": projection.lead_threshold,
                "topology": projection.topology.value,
                "score_matrix_sha256": projection.score_matrix_sha256,
                "provider_settlement_receipt_sha256": projection.provider_settlement_receipt_sha256,
            }
        ),
    )


def _from_weh(
    prediction: WinEitherHalfAnalyticalPrediction,
    market_id: MarketId,
    *,
    disposition: ShadowDisposition,
    provider_semantic_status: Optional[str] = None,
) -> ShadowMarketAssessment:
    status = get_model_status(market_id)
    definition = MARKET_REGISTRY[market_id]
    if market_id is MarketId.HOME_WIN_EITHER_HALF:
        yes = prediction.home_yes_probability
        no = prediction.home_no_probability
    else:
        yes = prediction.away_yes_probability
        no = prediction.away_no_probability
    events = (
        AnalyticalEventProbability(OutcomeId.YES, yes),
        AnalyticalEventProbability(OutcomeId.NO, no),
    )
    return ShadowMarketAssessment(
        market_id=market_id,
        market_family=definition.family,
        disposition=disposition,
        probability_method=status.probability_method,
        probability_input_namespace=status.probability_input_namespace.value,
        analytical_capability=AnalyticalProbabilityCapability.AVAILABLE,
        settlement_capability=status.settlement_capability,
        event_probabilities=events,
        settlement_distributions=(),
        required_inputs=status.probability_inputs,
        missing_inputs=(),
        blocker_reason=None,
        provider_semantic_status=provider_semantic_status,
        pricing_authority=PricingAuthority.NOT_AUTHORIZED,
        selection_authority=SelectionAuthority.NOT_AUTHORIZED,
        specialist_evidence=MappingProxyType(
            {
                "inference_state_fingerprint_sha256": prediction.inference_state_fingerprint_sha256,
                "home_base_model_identifier": prediction.home_base_model_identifier,
                "away_base_model_identifier": prediction.away_base_model_identifier,
                "home_calibration_identifier": prediction.home_calibration_identifier,
                "away_calibration_identifier": prediction.away_calibration_identifier,
            }
        ),
    )


def _provider_status(
    provider_semantic_by_market: Optional[Mapping[MarketId, str]],
    market_id: MarketId,
) -> Optional[str]:
    if provider_semantic_by_market is None:
        return None
    return provider_semantic_by_market.get(market_id)
