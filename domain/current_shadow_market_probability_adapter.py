"""One-way Current Shadow adapter into canonical market probability contracts.

The adapter intentionally removes the provider-pricing axis from PR-C fixture
scans.  Provider semantic status, quote identity and odds remain owned by the
pricing context; only model probabilities, model evidence and specialist
semantics cross into ``MarketProbabilityBundle``.
"""
from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType
from typing import Any, Mapping

from domain._all_market_shadow_types import (
    CurrentAllMarketShadowFixtureScan,
    ShadowDisposition,
    ShadowMarketAssessment,
)
from domain.market_probabilities import (
    EventProbability,
    MarketProbabilityBundle,
    MarketProbabilityDistribution,
    MarketProbabilityError,
    ProbabilityAvailability,
    ProbabilityTopology,
    ScoreGridIdentity,
    SettlementProbabilityDistribution,
    SpecialistModelOutput,
    canonical_sha256,
)
from domain.markets import MarketId
from domain.model_status import (
    AnalyticalProbabilityCapability,
    SettlementCapability,
    get_model_status,
)
from domain.score_matrix_market_probabilities import (
    AnalyticalEventProbability,
    AnalyticalSettlementDistribution,
)
from domain.score_matrix_settlement import SettlementProbabilities


_ANALYTICALLY_AVAILABLE_DISPOSITIONS = frozenset(
    {ShadowDisposition.ANALYTICAL_READY, ShadowDisposition.ANALYTICAL_READY_PROVIDER_BLOCKED}
)
_OVERLAPPING = frozenset(
    {MarketId.DOUBLE_CHANCE, MarketId.MATCH_RESULT_1UP, MarketId.MATCH_RESULT_2UP}
)
_SPECIALIST_KIND = {
    MarketId.HOME_WIN_EITHER_HALF: "WIN_EITHER_HALF_ANALYTICAL_INFERENCE",
    MarketId.AWAY_WIN_EITHER_HALF: "WIN_EITHER_HALF_ANALYTICAL_INFERENCE",
    MarketId.MATCH_RESULT_1UP: "EARLY_PAYOUT_LEAD_PATH",
    MarketId.MATCH_RESULT_2UP: "EARLY_PAYOUT_LEAD_PATH",
}


def _settlement_to_canonical(
    value: AnalyticalSettlementDistribution,
) -> SettlementProbabilityDistribution:
    settlement = value.settlement
    return SettlementProbabilityDistribution(
        outcome_id=value.outcome_id,
        full_win=settlement.full_win,
        half_win=settlement.half_win,
        push=settlement.push,
        half_loss=settlement.half_loss,
        full_loss=settlement.full_loss,
        settlement_method=settlement.method,
        line=settlement.line,
        component_lines=tuple(settlement.component_lines),
    )


def _probability_projection_payload(assessment: ShadowMarketAssessment) -> dict[str, Any]:
    """Return provider-free evidence used to bind one adapted market row."""

    return {
        "market_id": assessment.market_id.value,
        "probability_method": assessment.probability_method,
        "probability_input_namespace": assessment.probability_input_namespace,
        "analytical_capability": assessment.analytical_capability.value,
        "settlement_capability": assessment.settlement_capability.value,
        "event_probabilities": [item.to_dict() for item in assessment.event_probabilities],
        "settlement_distributions": [
            _settlement_to_canonical(item).to_dict()
            for item in assessment.settlement_distributions
        ],
        "required_inputs": list(assessment.required_inputs),
        "missing_inputs": list(assessment.missing_inputs),
        "blocker_reason": assessment.blocker_reason,
        "score_matrix_audit": (
            None if assessment.score_matrix_audit is None
            else dict(assessment.score_matrix_audit)
        ),
        "specialist_evidence": (
            None if assessment.specialist_evidence is None
            else dict(assessment.specialist_evidence)
        ),
    }


def _availability(assessment: ShadowMarketAssessment) -> ProbabilityAvailability:
    if (
        assessment.analytical_capability is AnalyticalProbabilityCapability.AVAILABLE
        and assessment.disposition in _ANALYTICALLY_AVAILABLE_DISPOSITIONS
        and bool(assessment.event_probabilities or assessment.settlement_distributions)
    ):
        return ProbabilityAvailability.AVAILABLE
    return ProbabilityAvailability.BLOCKED


def _topology(assessment: ShadowMarketAssessment) -> ProbabilityTopology:
    if assessment.settlement_capability is SettlementCapability.FULL_SETTLEMENT_DISTRIBUTION:
        return ProbabilityTopology.SETTLEMENT_DISTRIBUTIONS
    if assessment.market_id in _OVERLAPPING:
        return ProbabilityTopology.OVERLAPPING_EVENTS
    return ProbabilityTopology.MUTUALLY_EXCLUSIVE_PARTITION


def _distribution_from_assessment(
    assessment: ShadowMarketAssessment,
) -> MarketProbabilityDistribution:
    status = get_model_status(assessment.market_id)
    source_sha = canonical_sha256(_probability_projection_payload(assessment))
    availability = _availability(assessment)
    if availability is ProbabilityAvailability.BLOCKED:
        return MarketProbabilityDistribution(
            market_id=assessment.market_id,
            availability=availability,
            topology=None,
            probability_method=None,
            probability_input_namespace=None,
            calibration_status=status.calibration_status.value,
            event_probabilities=(),
            settlement_distributions=(),
            blocker_reason=(
                assessment.blocker_reason
                or "No canonical analytical probability distribution is available"
            ),
            source_projection_sha256=source_sha,
        )
    if assessment.probability_method is None or assessment.probability_input_namespace is None:
        raise MarketProbabilityError("available Current Shadow assessment omitted model semantics")
    return MarketProbabilityDistribution(
        market_id=assessment.market_id,
        availability=availability,
        topology=_topology(assessment),
        probability_method=assessment.probability_method,
        probability_input_namespace=assessment.probability_input_namespace,
        calibration_status=status.calibration_status.value,
        event_probabilities=tuple(
            EventProbability(item.outcome_id, item.probability, item.line)
            for item in assessment.event_probabilities
        ),
        settlement_distributions=tuple(
            _settlement_to_canonical(item)
            for item in assessment.settlement_distributions
        ),
        blocker_reason=None,
        source_projection_sha256=source_sha,
    )


def _score_grid_identity(
    scan: CurrentAllMarketShadowFixtureScan,
    markets: tuple[MarketProbabilityDistribution, ...],
) -> ScoreGridIdentity | None:
    grid_hashes: set[str] = set()
    for assessment in scan.market_assessments:
        evidence = assessment.specialist_evidence
        if assessment.market_id in {MarketId.MATCH_RESULT_1UP, MarketId.MATCH_RESULT_2UP} and evidence:
            value = evidence.get("score_matrix_sha256")
            if type(value) is str:
                grid_hashes.add(value)
    score_grid_required = any(
        row.availability is ProbabilityAvailability.AVAILABLE
        and row.market_id not in {
            MarketId.HOME_WIN_EITHER_HALF,
            MarketId.AWAY_WIN_EITHER_HALF,
        }
        for row in markets
    )
    if not score_grid_required:
        if grid_hashes:
            raise MarketProbabilityError("blocked score-grid lane unexpectedly carried score-grid identity")
        return None
    if len(grid_hashes) != 1 or scan.score_matrix_audit is None:
        raise MarketProbabilityError(
            "Current Shadow score-grid probabilities lack one exact score-grid identity"
        )
    return ScoreGridIdentity(
        sha256=next(iter(grid_hashes)),
        identity_method="normalized_score_matrix_content_sha256",
        audit=dict(scan.score_matrix_audit),
    )


def _specialist_outputs(
    scan: CurrentAllMarketShadowFixtureScan,
    by_market: Mapping[MarketId, MarketProbabilityDistribution],
) -> tuple[SpecialistModelOutput, ...]:
    outputs: list[SpecialistModelOutput] = []
    for assessment in scan.market_assessments:
        if assessment.market_id not in _SPECIALIST_KIND:
            continue
        distribution = by_market[assessment.market_id]
        if distribution.availability is ProbabilityAvailability.BLOCKED:
            continue
        if assessment.specialist_evidence is None:
            raise MarketProbabilityError("available specialist assessment omitted specialist evidence")
        outputs.append(
            SpecialistModelOutput(
                market_id=assessment.market_id,
                output_kind=_SPECIALIST_KIND[assessment.market_id],
                probability_method=distribution.probability_method or "",
                probability_input_namespace=distribution.probability_input_namespace or "",
                evidence=dict(assessment.specialist_evidence),
            )
        )
    return tuple(outputs)


def market_probability_bundle_from_current_shadow_fixture_scan(
    scan: CurrentAllMarketShadowFixtureScan,
) -> MarketProbabilityBundle:
    """Adapt one validated PR-C fixture scan without importing provider pricing."""

    if type(scan) is not CurrentAllMarketShadowFixtureScan:
        raise MarketProbabilityError("adapter requires exact CurrentAllMarketShadowFixtureScan")
    # Rebuild the exact type to re-run its fail-closed invariants before projection.
    checked = CurrentAllMarketShadowFixtureScan(
        fixture_identity=scan.fixture_identity,
        kickoff_utc_iso=scan.kickoff_utc_iso,
        research_xg=scan.research_xg,
        score_matrix_audit=scan.score_matrix_audit,
        market_assessments=tuple(scan.market_assessments),
        authority=dict(scan.authority),
    )
    markets = tuple(_distribution_from_assessment(item) for item in checked.market_assessments)
    by_market = MappingProxyType({item.market_id: item for item in markets})
    specialists = _specialist_outputs(checked, by_market)
    model_evidence: dict[str, Any] = {
        "kickoff_utc_iso": checked.kickoff_utc_iso,
        "research_xg": (
            None if checked.research_xg is None
            else {
                "calibrated_home": checked.research_xg.calibrated_home,
                "calibrated_away": checked.research_xg.calibrated_away,
                "sealed_prediction_sha256": checked.research_xg.sealed_prediction_sha256,
                "feature_projection_identity": checked.research_xg.feature_projection_identity,
                "history_prefix_identity": checked.research_xg.history_prefix_identity,
                "source_fixture_identity": checked.research_xg.source_fixture_identity,
                "completeness_status": checked.research_xg.completeness_status,
            }
        ),
    }
    return MarketProbabilityBundle(
        fixture_identity=checked.fixture_identity,
        score_grid=_score_grid_identity(checked, markets),
        markets=markets,
        specialist_outputs=specialists,
        model_evidence=model_evidence,
    )


def current_shadow_assessment_with_canonical_probability(
    assessment: ShadowMarketAssessment,
    distribution: MarketProbabilityDistribution,
) -> ShadowMarketAssessment:
    """Project canonical probability values back into legacy pricing shape.

    This compatibility direction exists only so the current Price-all helper can
    keep its provider/evidence ancestry while P1.2 makes the canonical bundle the
    probability source.  It performs no pricing, routing or selection.
    """

    if type(assessment) is not ShadowMarketAssessment:
        raise MarketProbabilityError("legacy pricing adapter requires ShadowMarketAssessment")
    if type(distribution) is not MarketProbabilityDistribution:
        raise MarketProbabilityError("canonical pricing adapter requires probability distribution")
    if assessment.market_id is not distribution.market_id:
        raise MarketProbabilityError("legacy/canonical market identity mismatch")
    expected = _distribution_from_assessment(assessment)
    if expected.to_dict() != distribution.to_dict():
        raise MarketProbabilityError("canonical probability row differs from source projection")

    if distribution.availability is ProbabilityAvailability.BLOCKED:
        return replace(
            assessment,
            event_probabilities=(),
            settlement_distributions=(),
        )
    events = tuple(
        AnalyticalEventProbability(item.outcome_id, item.probability, item.line)
        for item in distribution.event_probabilities
    )
    settlements = tuple(
        AnalyticalSettlementDistribution(
            item.outcome_id,
            SettlementProbabilities(
                full_win=item.full_win,
                half_win=item.half_win,
                push=item.push,
                half_loss=item.half_loss,
                full_loss=item.full_loss,
                method=item.settlement_method,
                side=item.outcome_id.value,
                line=item.line,
                component_lines=tuple(item.component_lines),
            ),
        )
        for item in distribution.settlement_distributions
    )
    return replace(
        assessment,
        probability_method=distribution.probability_method,
        probability_input_namespace=distribution.probability_input_namespace,
        event_probabilities=events,
        settlement_distributions=settlements,
    )


__all__ = [
    "current_shadow_assessment_with_canonical_probability",
    "market_probability_bundle_from_current_shadow_fixture_scan",
]
