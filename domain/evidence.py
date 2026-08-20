"""Typed, serializable evidence contracts for ATHENA fixture decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence

from domain.markets import DecisionStatus, MarketId, OutcomeId
from domain.model_status import (
    AnalyticalProbabilityCapability,
    CalibrationStatus,
    FreshConfirmationStatus,
    ModelStatus,
    PricingAuthority,
    SelectionAuthority,
    SettlementCapability,
)


class EvidenceStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    STALE = "STALE"
    DEFAULTED = "DEFAULTED"


@dataclass(frozen=True)
class EvidenceItem:
    source: str
    field: str
    value: Any
    status: EvidenceStatus
    observed_at: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "field": self.field,
            "value": self.value,
            "status": self.status.value,
            "observed_at": self.observed_at,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class DataQualitySummary:
    completeness_score: float
    available_count: int
    missing_count: int
    stale_count: int
    defaulted_count: int

    @classmethod
    def from_items(
        cls,
        items: Sequence[EvidenceItem],
    ) -> "DataQualitySummary":
        counts = {
            status: sum(item.status == status for item in items)
            for status in EvidenceStatus
        }
        total = len(items)
        completeness = counts[EvidenceStatus.AVAILABLE] / total if total else 0.0
        return cls(
            completeness_score=round(completeness, 4),
            available_count=counts[EvidenceStatus.AVAILABLE],
            missing_count=counts[EvidenceStatus.MISSING],
            stale_count=counts[EvidenceStatus.STALE],
            defaulted_count=counts[EvidenceStatus.DEFAULTED],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "completeness_score": self.completeness_score,
            "available_count": self.available_count,
            "missing_count": self.missing_count,
            "stale_count": self.stale_count,
            "defaulted_count": self.defaulted_count,
        }


@dataclass(frozen=True)
class MarketEvaluation:
    market_id: MarketId
    outcome_id: OutcomeId
    line: Optional[float]
    model_status: ModelStatus
    analytical_probability_capability: AnalyticalProbabilityCapability
    settlement_capability: SettlementCapability
    calibration_status: CalibrationStatus
    fresh_confirmation_status: FreshConfirmationStatus
    pricing_authority: PricingAuthority
    selection_authority: SelectionAuthority
    probability: Optional[float]
    probability_method: Optional[str]
    probability_inputs: Sequence[str]
    pricing_inputs: Sequence[str]
    missing_inputs: Sequence[str]
    rejection_reasons: Sequence[str]
    selected: bool
    bookmaker_odds: Optional[float] = None
    edge_pp: Optional[float] = None
    kelly_stake_pct: Optional[float] = None
    model_fair_odds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market_id": self.market_id.value,
            "outcome_id": self.outcome_id.value,
            "line": self.line,
            "model_status": self.model_status.value,
            "analytical_probability_capability": (
                self.analytical_probability_capability.value
            ),
            "settlement_capability": self.settlement_capability.value,
            "calibration_status": self.calibration_status.value,
            "fresh_confirmation_status": self.fresh_confirmation_status.value,
            "pricing_authority": self.pricing_authority.value,
            "selection_authority": self.selection_authority.value,
            "probability": self.probability,
            "probability_method": self.probability_method,
            "probability_inputs": list(self.probability_inputs),
            "pricing_inputs": list(self.pricing_inputs),
            "missing_inputs": list(self.missing_inputs),
            "rejection_reasons": list(self.rejection_reasons),
            "selected": self.selected,
            "bookmaker_odds": self.bookmaker_odds,
            "edge_pp": self.edge_pp,
            "kelly_stake_pct": self.kelly_stake_pct,
            "model_fair_odds": self.model_fair_odds,
        }


@dataclass(frozen=True)
class FixtureEvidenceReport:
    fixture_id: Any
    home_team: str
    away_team: str
    match_date: Optional[str]
    generated_at: str
    evidence_items: Sequence[EvidenceItem]
    data_quality: DataQualitySummary
    market_evaluations: Sequence[MarketEvaluation]
    final_decision: DecisionStatus
    decision_reasons: Sequence[str]
    score_matrix_audit: Optional[Mapping[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "match_date": self.match_date,
            "generated_at": self.generated_at,
            "evidence_items": [
                item.to_dict() for item in self.evidence_items
            ],
            "data_quality": self.data_quality.to_dict(),
            "market_evaluations": [
                evaluation.to_dict()
                for evaluation in self.market_evaluations
            ],
            "final_decision": self.final_decision.value,
            "decision_reasons": list(self.decision_reasons),
            "score_matrix_audit": (
                dict(self.score_matrix_audit)
                if self.score_matrix_audit is not None
                else None
            ),
        }


def evidence_items_by_field(
    items: Sequence[EvidenceItem],
) -> Dict[str, EvidenceItem]:
    return {item.field: item for item in items}


__all__ = [
    "DataQualitySummary",
    "EvidenceItem",
    "EvidenceStatus",
    "FixtureEvidenceReport",
    "MarketEvaluation",
    "evidence_items_by_field",
]
