"""Immutable prediction/post-match audit contracts for ATHENA field trials.

The ledger deliberately keeps pre-match decisions, post-match settlement, and
post-match attribution in separate typed namespaces.  It is an audit surface
only: every authority flag is permanently false and no outcome is converted
into a decision-quality or failure-attribution judgment.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from enum import Enum
import hashlib
import json
import math
import re
import types
from collections.abc import Mapping, Sequence
from typing import Any

from domain.markets import MarketRegistryError, MarketId, OutcomeId, validate_selection


SCHEMA_VERSION = 1
DATASET_NAME = "athena-prediction-postmatch-field-trial-v1"
IMPORT_DATASET_NAME = "athena-prediction-field-trial-import-v1"
IMPORTER_ID = "athena-prediction-field-trial-importer-v1"
CONTRACT_ORIGIN_SHA = "a9bcba9271dd516f4a5754f3128af0178fcffff9"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$", flags=re.ASCII)
_IDENTIFIER_RE = re.compile(r"^[A-Z0-9][A-Z0-9_.:-]{2,127}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "bet_authority_granted",
        "market_selection_authority_granted",
        "model_authority_granted",
        "pricing_authority_granted",
        "production_state_mutation_authorized",
        "value_router_authority_granted",
    }
)


class PredictionPostMatchAuditError(ValueError):
    """Raised when field-trial audit evidence fails closed."""


class EvidenceAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


class EvidenceAuthority(str, Enum):
    PRESERVED_ARTIFACT = "PRESERVED_ARTIFACT"
    USER_REPORTED = "USER_REPORTED"
    SOURCE_DECLARATION = "SOURCE_DECLARATION"


class VerificationState(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    CONFLICTING = "CONFLICTING"
    UNKNOWN = "UNKNOWN"


class SettlementOutcome(str, Enum):
    WON = "WON"
    LOST = "LOST"
    VOID = "VOID"
    PARTIAL_WIN = "PARTIAL_WIN"
    PARTIAL_LOSS = "PARTIAL_LOSS"
    UNKNOWN = "UNKNOWN"


class AttributionFactor(str, Enum):
    MODEL_ERROR = "MODEL_ERROR"
    CONTEXT_ERROR = "CONTEXT_ERROR"
    MARKET_CHOICE_ERROR = "MARKET_CHOICE_ERROR"
    PRICE_VALUE_ERROR = "PRICE_VALUE_ERROR"
    DATA_ERROR = "DATA_ERROR"
    IRREDUCIBLE_VARIANCE = "IRREDUCIBLE_VARIANCE"
    UNKNOWN = "UNKNOWN"


class DecisionQuality(str, Enum):
    GOOD_DECISION = "GOOD_DECISION"
    BAD_DECISION = "BAD_DECISION"
    UNKNOWN = "UNKNOWN"


class ReconstructionStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    SUMMARY_ONLY = "SUMMARY_ONLY"
    UNKNOWN = "UNKNOWN"


class LegReconstructionState(str, Enum):
    RECONSTRUCTED = "RECONSTRUCTED"
    UNRESOLVED = "UNRESOLVED"


def _fail(message: str) -> PredictionPostMatchAuditError:
    return PredictionPostMatchAuditError(message)


def _strict_string(value: Any, label: str, *, identifier: bool = False) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise _fail(f"{label} must be a non-empty exact string without padding")
    if identifier and _IDENTIFIER_RE.fullmatch(value) is None:
        raise _fail(f"{label} must be an uppercase stable identifier")
    return value


def _strict_sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise _fail(f"{label} must be 64 lowercase hexadecimal characters")
    return value


def _strict_git_sha(value: Any, label: str) -> str:
    if type(value) is not str or _GIT_SHA_RE.fullmatch(value) is None:
        raise _fail(f"{label} must be 40 lowercase hexadecimal characters")
    return value


def _strict_count(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise _fail(f"{label} must be a non-negative exact integer")
    return value


def _strict_refs(value: Any, label: str) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise _fail(f"{label} must be an exact tuple")
    refs = tuple(_strict_string(item, f"{label} item") for item in value)
    if len(set(refs)) != len(refs):
        raise _fail(f"{label} contains duplicate evidence references")
    return refs


def _parse_timestamp_text(value: Any, label: str) -> str:
    text = _strict_string(value, label)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise _fail(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _fail(f"{label} must include a timezone")
    return text


def _freeze_json(value: Any, label: str = "value") -> Any:
    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise _fail(f"{label} contains NaN or Infinity")
        return value
    if isinstance(value, Mapping):
        detached: dict[str, Any] = {}
        for key, child in value.items():
            if type(key) is not str:
                raise _fail(f"{label} contains a non-string object key")
            detached[key] = _freeze_json(child, f"{label}.{key}")
        return types.MappingProxyType(detached)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_freeze_json(child, f"{label}[]") for child in value)
    raise _fail(f"{label} contains a non-JSON value")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(child) for child in value]
    return value


def _evidenced_references_in(value: Any) -> tuple[str, ...]:
    """Return references carried inside nested EvidencedValue fields."""

    if type(value) is EvidencedValue:
        return value.evidence_references
    if dataclasses.is_dataclass(value):
        return tuple(
            reference
            for field in dataclasses.fields(value)
            for reference in _evidenced_references_in(getattr(value, field.name))
        )
    if type(value) is tuple:
        return tuple(
            reference
            for child in value
            for reference in _evidenced_references_in(child)
        )
    return ()


def _canonical_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise _fail("canonical audit serialization failed") from exc


@dataclasses.dataclass(frozen=True)
class EvidencedValue:
    status: EvidenceAvailability
    value: Any
    evidence_references: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.status) is not EvidenceAvailability:
            raise _fail("evidenced value status must be typed")
        refs = _strict_refs(self.evidence_references, "evidence_references")
        if self.status is EvidenceAvailability.AVAILABLE:
            if self.value is None:
                raise _fail("AVAILABLE evidenced value cannot be null")
            if not refs:
                raise _fail("AVAILABLE evidenced value requires evidence")
        elif self.value is not None:
            raise _fail("MISSING/UNKNOWN evidenced value must remain null")
        object.__setattr__(self, "value", _freeze_json(self.value))
        object.__setattr__(self, "evidence_references", refs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "value": _thaw_json(self.value),
            "evidence_references": list(self.evidence_references),
        }


def missing_value(*evidence_references: str) -> EvidencedValue:
    return EvidencedValue(
        EvidenceAvailability.MISSING,
        None,
        tuple(evidence_references),
    )


def unknown_value(*evidence_references: str) -> EvidencedValue:
    return EvidencedValue(
        EvidenceAvailability.UNKNOWN,
        None,
        tuple(evidence_references),
    )


@dataclasses.dataclass(frozen=True)
class SourceEvidence:
    source_id: str
    authority: EvidenceAuthority
    reference: str
    content_sha256: EvidencedValue
    observed_at: EvidencedValue
    verification_state: VerificationState
    notes: str

    def __post_init__(self) -> None:
        _strict_string(self.source_id, "source_id")
        if type(self.authority) is not EvidenceAuthority:
            raise _fail("source evidence authority must be typed")
        _strict_string(self.reference, "source evidence reference")
        _strict_string(self.notes, "source evidence notes")
        if type(self.content_sha256) is not EvidencedValue:
            raise _fail("source content_sha256 must be an EvidencedValue")
        if self.content_sha256.status is EvidenceAvailability.AVAILABLE:
            _strict_sha256(self.content_sha256.value, "source content_sha256")
        if type(self.observed_at) is not EvidencedValue:
            raise _fail("source observed_at must be an EvidencedValue")
        if self.observed_at.status is EvidenceAvailability.AVAILABLE:
            _parse_timestamp_text(self.observed_at.value, "source observed_at")
        if type(self.verification_state) is not VerificationState:
            raise _fail("source verification_state must be typed")
        if (
            self.authority is EvidenceAuthority.USER_REPORTED
            and self.verification_state is VerificationState.VERIFIED
        ):
            raise _fail("USER_REPORTED evidence cannot be silently marked VERIFIED")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "authority": self.authority.value,
            "reference": self.reference,
            "content_sha256": self.content_sha256.to_dict(),
            "observed_at": self.observed_at.to_dict(),
            "verification_state": self.verification_state.value,
            "notes": self.notes,
        }


@dataclasses.dataclass(frozen=True)
class MarketCandidate:
    candidate_id: str
    market_id: MarketId
    outcome_id: OutcomeId
    line: float | None
    model_probability: EvidencedValue
    fair_price: EvidencedValue
    risk_uncertainty: EvidencedValue
    original_rank: EvidencedValue
    original_score: EvidencedValue
    bookmaker_source: EvidencedValue
    exact_bookmaker_mapping: EvidencedValue
    bookmaker_price: EvidencedValue
    quote_observed_at: EvidencedValue
    quote_identity: EvidencedValue
    reason_not_selected: EvidencedValue
    pre_match_evidence_references: tuple[str, ...]

    def __post_init__(self) -> None:
        _strict_string(self.candidate_id, "candidate_id")
        try:
            market, outcome, line = validate_selection(
                self.market_id,
                self.outcome_id,
                self.line,
            )
        except MarketRegistryError as exc:
            raise _fail(str(exc)) from exc
        if self.market_id is not market or self.outcome_id is not outcome or self.line != line:
            raise _fail("market candidate is not canonical")
        for name in (
            "model_probability",
            "fair_price",
            "risk_uncertainty",
            "original_rank",
            "original_score",
            "bookmaker_source",
            "exact_bookmaker_mapping",
            "bookmaker_price",
            "quote_observed_at",
            "quote_identity",
            "reason_not_selected",
        ):
            if type(getattr(self, name)) is not EvidencedValue:
                raise _fail(f"candidate {name} must be an EvidencedValue")
        if self.model_probability.status is EvidenceAvailability.AVAILABLE:
            value = self.model_probability.value
            if type(value) not in {int, float} or type(value) is bool or not 0.0 <= float(value) <= 1.0:
                raise _fail("model probability must be finite and within [0, 1]")
        for value, label in (
            (self.fair_price, "fair price"),
            (self.bookmaker_price, "bookmaker price"),
        ):
            if value.status is EvidenceAvailability.AVAILABLE:
                number = value.value
                if type(number) not in {int, float} or type(number) is bool or float(number) <= 1.0:
                    raise _fail(f"{label} must be finite decimal odds above 1.0")
        if self.original_rank.status is EvidenceAvailability.AVAILABLE:
            if type(self.original_rank.value) is not int or self.original_rank.value <= 0:
                raise _fail("original rank must be a positive exact integer")
        if self.quote_observed_at.status is EvidenceAvailability.AVAILABLE:
            _parse_timestamp_text(self.quote_observed_at.value, "quote_observed_at")
        refs = _strict_refs(
            self.pre_match_evidence_references,
            "pre_match_evidence_references",
        )
        if not refs:
            raise _fail("market candidate requires preserved pre-match evidence")
        object.__setattr__(self, "pre_match_evidence_references", refs)

    @property
    def canonical_selection_key(self) -> tuple[str, str, float | None]:
        return (self.market_id.value, self.outcome_id.value, self.line)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "market_id": self.market_id.value,
            "outcome_id": self.outcome_id.value,
            "line": self.line,
            "model_probability": self.model_probability.to_dict(),
            "fair_price": self.fair_price.to_dict(),
            "risk_uncertainty": self.risk_uncertainty.to_dict(),
            "original_rank": self.original_rank.to_dict(),
            "original_score": self.original_score.to_dict(),
            "bookmaker_source": self.bookmaker_source.to_dict(),
            "exact_bookmaker_mapping": self.exact_bookmaker_mapping.to_dict(),
            "bookmaker_price": self.bookmaker_price.to_dict(),
            "quote_observed_at": self.quote_observed_at.to_dict(),
            "quote_identity": self.quote_identity.to_dict(),
            "reason_not_selected": self.reason_not_selected.to_dict(),
            "pre_match_evidence_references": list(self.pre_match_evidence_references),
        }


@dataclasses.dataclass(frozen=True)
class PreMatchDecisionRecord:
    record_key: str
    fixture_identity: EvidencedValue
    home_team: EvidencedValue
    away_team: EvidencedValue
    competition: EvidencedValue
    kickoff_time: EvidencedValue
    source_fixture_identifiers: EvidencedValue
    generated_at: EvidencedValue
    athena_version: EvidencedValue
    athena_commit: EvidencedValue
    model_identity: EvidencedValue
    pre_match_evidence_references: tuple[str, ...]
    model_raw_outputs: EvidencedValue
    score_distribution_model_identifiers: EvidencedValue
    eligible_candidates_status: EvidenceAvailability
    eligible_market_candidates: tuple[MarketCandidate, ...]
    selected_candidate_id: EvidencedValue
    candidate_ranking: EvidencedValue
    counterfactual_candidate_ids: EvidencedValue

    def __post_init__(self) -> None:
        _strict_string(self.record_key, "pre-match record_key")
        value_fields = (
            "fixture_identity",
            "home_team",
            "away_team",
            "competition",
            "kickoff_time",
            "source_fixture_identifiers",
            "generated_at",
            "athena_version",
            "athena_commit",
            "model_identity",
            "model_raw_outputs",
            "score_distribution_model_identifiers",
            "selected_candidate_id",
            "candidate_ranking",
            "counterfactual_candidate_ids",
        )
        for name in value_fields:
            if type(getattr(self, name)) is not EvidencedValue:
                raise _fail(f"pre-match {name} must be an EvidencedValue")
        for value, label in (
            (self.kickoff_time, "kickoff_time"),
            (self.generated_at, "generated_at"),
        ):
            if value.status is EvidenceAvailability.AVAILABLE:
                _parse_timestamp_text(value.value, label)
        if self.athena_commit.status is EvidenceAvailability.AVAILABLE:
            _strict_git_sha(self.athena_commit.value, "athena_commit")
        refs = _strict_refs(
            self.pre_match_evidence_references,
            "pre_match_evidence_references",
        )
        object.__setattr__(self, "pre_match_evidence_references", refs)
        if type(self.eligible_candidates_status) is not EvidenceAvailability:
            raise _fail("eligible_candidates_status must be typed")
        if type(self.eligible_market_candidates) is not tuple or any(
            type(item) is not MarketCandidate for item in self.eligible_market_candidates
        ):
            raise _fail("eligible_market_candidates must be an exact tuple of MarketCandidate")
        candidates = self.eligible_market_candidates
        if self.eligible_candidates_status is EvidenceAvailability.AVAILABLE:
            if not candidates:
                raise _fail("AVAILABLE eligible candidates cannot be empty")
        elif candidates:
            raise _fail("MISSING/UNKNOWN eligible candidates must remain empty")
        ids = [candidate.candidate_id for candidate in candidates]
        if len(set(ids)) != len(ids):
            raise _fail("duplicate candidate_id in pre-match decision")
        keys = [candidate.canonical_selection_key for candidate in candidates]
        if len(set(keys)) != len(keys):
            raise _fail("duplicate canonical market candidate in pre-match decision")
        selected: str | None = None
        if self.selected_candidate_id.status is EvidenceAvailability.AVAILABLE:
            selected = _strict_string(
                self.selected_candidate_id.value,
                "selected_candidate_id",
            )
            if selected not in ids:
                raise _fail("selected candidate is absent from preserved eligible candidates")
        elif self.eligible_candidates_status is not EvidenceAvailability.AVAILABLE:
            selected = None
        if self.counterfactual_candidate_ids.status is EvidenceAvailability.AVAILABLE:
            raw_ids = self.counterfactual_candidate_ids.value
            if type(raw_ids) is not tuple or not raw_ids:
                raise _fail("available counterfactuals must be a non-empty JSON array")
            counterfactuals = tuple(
                _strict_string(item, "counterfactual candidate_id") for item in raw_ids
            )
            if len(set(counterfactuals)) != len(counterfactuals):
                raise _fail("counterfactual candidate IDs contain duplicates")
            if selected is None:
                raise _fail("counterfactuals require an evidenced selected candidate")
            if selected in counterfactuals or not set(counterfactuals).issubset(ids):
                raise _fail("counterfactuals must reference other preserved pre-match candidates")
        if self.candidate_ranking.status is EvidenceAvailability.AVAILABLE:
            ranking = self.candidate_ranking.value
            if type(ranking) is not tuple or set(ranking) != set(ids) or len(ranking) != len(ids):
                raise _fail("candidate ranking must contain every candidate exactly once")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "record_key": self.record_key,
            "fixture_identity": self.fixture_identity.to_dict(),
            "home_team": self.home_team.to_dict(),
            "away_team": self.away_team.to_dict(),
            "competition": self.competition.to_dict(),
            "kickoff_time": self.kickoff_time.to_dict(),
            "source_fixture_identifiers": self.source_fixture_identifiers.to_dict(),
            "generated_at": self.generated_at.to_dict(),
            "athena_version": self.athena_version.to_dict(),
            "athena_commit": self.athena_commit.to_dict(),
            "model_identity": self.model_identity.to_dict(),
            "pre_match_evidence_references": list(self.pre_match_evidence_references),
            "model_raw_outputs": self.model_raw_outputs.to_dict(),
            "score_distribution_model_identifiers": self.score_distribution_model_identifiers.to_dict(),
            "eligible_market_candidates": {
                "status": self.eligible_candidates_status.value,
                "records": [item.to_dict() for item in self.eligible_market_candidates],
            },
            "selected_candidate_id": self.selected_candidate_id.to_dict(),
            "candidate_ranking": self.candidate_ranking.to_dict(),
            "counterfactual_candidate_ids": self.counterfactual_candidate_ids.to_dict(),
        }

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self._content_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["pre_match_sha256"] = self.content_sha256
        return result


@dataclasses.dataclass(frozen=True)
class PostMatchSettlementRecord:
    final_home_score: EvidencedValue
    final_away_score: EvidencedValue
    regulation_score_semantics: EvidencedValue
    result_source: EvidencedValue
    observed_at: EvidencedValue
    source_evidence_reference: EvidencedValue
    settlement_outcome: SettlementOutcome
    settlement_evidence_references: tuple[str, ...]
    verification_state: VerificationState

    def __post_init__(self) -> None:
        for name in (
            "final_home_score",
            "final_away_score",
            "regulation_score_semantics",
            "result_source",
            "observed_at",
            "source_evidence_reference",
        ):
            if type(getattr(self, name)) is not EvidencedValue:
                raise _fail(f"settlement {name} must be an EvidencedValue")
        scores = (self.final_home_score, self.final_away_score)
        if (scores[0].status is EvidenceAvailability.AVAILABLE) != (
            scores[1].status is EvidenceAvailability.AVAILABLE
        ):
            raise _fail("final home/away scores must be evidenced together")
        if scores[0].status is EvidenceAvailability.AVAILABLE:
            for value in scores:
                if type(value.value) is not int or value.value < 0:
                    raise _fail("final score values must be non-negative exact integers")
            if self.regulation_score_semantics.status is not EvidenceAvailability.AVAILABLE:
                raise _fail("an evidenced final score requires regulation score semantics")
        if self.observed_at.status is EvidenceAvailability.AVAILABLE:
            _parse_timestamp_text(self.observed_at.value, "settlement observed_at")
        if type(self.settlement_outcome) is not SettlementOutcome:
            raise _fail("settlement outcome must be typed")
        if type(self.verification_state) is not VerificationState:
            raise _fail("settlement verification_state must be typed")
        refs = _strict_refs(
            self.settlement_evidence_references,
            "settlement_evidence_references",
        )
        if self.settlement_outcome is not SettlementOutcome.UNKNOWN:
            if not refs:
                raise _fail("a non-UNKNOWN settlement requires evidence")
            if self.verification_state is VerificationState.UNKNOWN:
                raise _fail(
                    "a non-UNKNOWN settlement requires an explicit verification state"
                )
        object.__setattr__(self, "settlement_evidence_references", refs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_home_score": self.final_home_score.to_dict(),
            "final_away_score": self.final_away_score.to_dict(),
            "regulation_score_semantics": self.regulation_score_semantics.to_dict(),
            "result_source": self.result_source.to_dict(),
            "observed_at": self.observed_at.to_dict(),
            "source_evidence_reference": self.source_evidence_reference.to_dict(),
            "settlement_outcome": self.settlement_outcome.value,
            "settlement_evidence_references": list(self.settlement_evidence_references),
            "verification_state": self.verification_state.value,
        }


@dataclasses.dataclass(frozen=True)
class PostMatchAttribution:
    primary_factor: AttributionFactor
    contributing_factors: tuple[AttributionFactor, ...]
    decision_quality: DecisionQuality
    evidence_references: tuple[str, ...]
    observation_source_identity: EvidencedValue
    explanatory_notes: EvidencedValue
    verification_state: VerificationState

    def __post_init__(self) -> None:
        if type(self.primary_factor) is not AttributionFactor:
            raise _fail("primary attribution factor must be typed")
        if type(self.contributing_factors) is not tuple or any(
            type(item) is not AttributionFactor for item in self.contributing_factors
        ):
            raise _fail("contributing attribution factors must be an exact typed tuple")
        if AttributionFactor.UNKNOWN in self.contributing_factors:
            raise _fail("UNKNOWN cannot be a contributing attribution factor")
        if len(set(self.contributing_factors)) != len(self.contributing_factors):
            raise _fail("contributing attribution factors contain duplicates")
        if self.primary_factor in self.contributing_factors:
            raise _fail("primary attribution cannot also be contributing")
        refs = _strict_refs(self.evidence_references, "attribution evidence_references")
        if type(self.observation_source_identity) is not EvidencedValue:
            raise _fail("attribution observation_source_identity must be evidenced")
        if type(self.explanatory_notes) is not EvidencedValue:
            raise _fail("attribution explanatory_notes must be evidenced")
        if type(self.verification_state) is not VerificationState:
            raise _fail("attribution verification_state must be typed")
        if type(self.decision_quality) is not DecisionQuality:
            raise _fail("decision_quality must be typed")
        if self.primary_factor is AttributionFactor.UNKNOWN:
            if self.contributing_factors:
                raise _fail("UNKNOWN primary attribution cannot carry contributing factors")
        else:
            if not refs:
                raise _fail("non-UNKNOWN attribution requires evidence")
            if self.observation_source_identity.status is not EvidenceAvailability.AVAILABLE:
                raise _fail("non-UNKNOWN attribution requires a source identity")
            if self.explanatory_notes.status is not EvidenceAvailability.AVAILABLE:
                raise _fail("non-UNKNOWN attribution requires explanatory notes")
            if self.verification_state is VerificationState.UNKNOWN:
                raise _fail("non-UNKNOWN attribution requires an explicit verification state")
        if (
            self.primary_factor is AttributionFactor.IRREDUCIBLE_VARIANCE
            and self.verification_state is not VerificationState.VERIFIED
        ):
            raise _fail("IRREDUCIBLE_VARIANCE requires verified event evidence")
        if (
            self.decision_quality is not DecisionQuality.UNKNOWN
            and self.verification_state is not VerificationState.VERIFIED
        ):
            raise _fail("non-UNKNOWN decision quality requires verified evidence")
        object.__setattr__(self, "evidence_references", refs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_factor": self.primary_factor.value,
            "contributing_factors": [item.value for item in self.contributing_factors],
            "decision_quality": self.decision_quality.value,
            "evidence_references": list(self.evidence_references),
            "observation_source_identity": self.observation_source_identity.to_dict(),
            "explanatory_notes": self.explanatory_notes.to_dict(),
            "verification_state": self.verification_state.value,
        }


@dataclasses.dataclass(frozen=True)
class FieldTrialLeg:
    pre_match_decision: PreMatchDecisionRecord
    post_match_settlement: PostMatchSettlementRecord
    post_match_attribution: PostMatchAttribution

    def __post_init__(self) -> None:
        if type(self.pre_match_decision) is not PreMatchDecisionRecord:
            raise _fail("leg pre_match_decision must be typed")
        if type(self.post_match_settlement) is not PostMatchSettlementRecord:
            raise _fail("leg post_match_settlement must be typed")
        if type(self.post_match_attribution) is not PostMatchAttribution:
            raise _fail("leg post_match_attribution must be typed")

    @property
    def leg_identity(self) -> str:
        return self.pre_match_decision.content_sha256

    @property
    def reconstruction_blockers(self) -> tuple[str, ...]:
        """Explain why a recorded shell is not a reconstructed prediction leg."""

        decision = self.pre_match_decision
        blockers: list[str] = []
        if decision.fixture_identity.status is not EvidenceAvailability.AVAILABLE:
            blockers.append("EVIDENCE_BACKED_FIXTURE_IDENTITY_MISSING")
        if decision.selected_candidate_id.status is not EvidenceAvailability.AVAILABLE:
            blockers.append("EVIDENCE_BACKED_SELECTED_CANDIDATE_MISSING")
        else:
            selected_id = decision.selected_candidate_id.value
            selected = next(
                (
                    candidate
                    for candidate in decision.eligible_market_candidates
                    if candidate.candidate_id == selected_id
                ),
                None,
            )
            if selected is None or not selected.pre_match_evidence_references:
                blockers.append("EVIDENCE_BACKED_SELECTED_MARKET_SELECTION_MISSING")
        return tuple(blockers)

    @property
    def reconstruction_state(self) -> LegReconstructionState:
        return (
            LegReconstructionState.UNRESOLVED
            if self.reconstruction_blockers
            else LegReconstructionState.RECONSTRUCTED
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "leg_identity": self.leg_identity,
            "reconstruction_state": self.reconstruction_state.value,
            "reconstruction_blockers": list(self.reconstruction_blockers),
            "pre_match_decision": self.pre_match_decision.to_dict(),
            "post_match_settlement": self.post_match_settlement.to_dict(),
            "post_match_attribution": self.post_match_attribution.to_dict(),
        }


@dataclasses.dataclass(frozen=True)
class SettlementSummary:
    won: int
    lost: int
    void: int
    partial_win: int
    partial_loss: int
    unknown: int

    def __post_init__(self) -> None:
        for field in dataclasses.fields(self):
            _strict_count(getattr(self, field.name), f"settlement summary {field.name}")

    @property
    def total(self) -> int:
        return sum(getattr(self, field.name) for field in dataclasses.fields(self))

    def to_dict(self) -> dict[str, int]:
        return {
            "WON": self.won,
            "LOST": self.lost,
            "VOID": self.void,
            "PARTIAL_WIN": self.partial_win,
            "PARTIAL_LOSS": self.partial_loss,
            "UNKNOWN": self.unknown,
        }

    @classmethod
    def from_legs(cls, legs: Sequence[FieldTrialLeg]) -> "SettlementSummary":
        counts = {outcome: 0 for outcome in SettlementOutcome}
        for leg in legs:
            counts[leg.post_match_settlement.settlement_outcome] += 1
        return cls(
            won=counts[SettlementOutcome.WON],
            lost=counts[SettlementOutcome.LOST],
            void=counts[SettlementOutcome.VOID],
            partial_win=counts[SettlementOutcome.PARTIAL_WIN],
            partial_loss=counts[SettlementOutcome.PARTIAL_LOSS],
            unknown=counts[SettlementOutcome.UNKNOWN],
        )


@dataclasses.dataclass(frozen=True)
class DeclaredSettlementSummary:
    status: EvidenceAvailability
    summary: SettlementSummary | None
    evidence_references: tuple[str, ...]
    verification_state: VerificationState

    def __post_init__(self) -> None:
        if type(self.status) is not EvidenceAvailability:
            raise _fail("declared settlement summary status must be typed")
        refs = _strict_refs(
            self.evidence_references,
            "declared settlement summary evidence_references",
        )
        if type(self.verification_state) is not VerificationState:
            raise _fail("declared settlement summary verification_state must be typed")
        if self.status is EvidenceAvailability.AVAILABLE:
            if type(self.summary) is not SettlementSummary or not refs:
                raise _fail("AVAILABLE declared settlement summary requires counts and evidence")
        elif self.summary is not None:
            raise _fail("MISSING/UNKNOWN declared settlement summary must remain null")
        object.__setattr__(self, "evidence_references", refs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "counts": None if self.summary is None else self.summary.to_dict(),
            "evidence_references": list(self.evidence_references),
            "verification_state": self.verification_state.value,
        }


@dataclasses.dataclass(frozen=True)
class DiagnosticNote:
    note_id: str
    text: str
    evidence_references: tuple[str, ...]
    verification_state: VerificationState

    def __post_init__(self) -> None:
        _strict_string(self.note_id, "diagnostic note_id")
        _strict_string(self.text, "diagnostic note text")
        refs = _strict_refs(self.evidence_references, "diagnostic evidence_references")
        if not refs:
            raise _fail("diagnostic note requires evidence references")
        if type(self.verification_state) is not VerificationState:
            raise _fail("diagnostic verification_state must be typed")
        object.__setattr__(self, "evidence_references", refs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "note_id": self.note_id,
            "text": self.text,
            "evidence_references": list(self.evidence_references),
            "verification_state": self.verification_state.value,
        }


@dataclasses.dataclass(frozen=True)
class ImportIdentity:
    importer_id: str
    contract_origin_sha: str
    execution_commit_sha: str
    source_repository_path: str
    source_sha256: str
    source_size: int

    def __post_init__(self) -> None:
        _strict_string(self.importer_id, "importer_id", identifier=False)
        _strict_git_sha(self.contract_origin_sha, "contract_origin_sha")
        _strict_git_sha(self.execution_commit_sha, "execution_commit_sha")
        _strict_string(self.source_repository_path, "source_repository_path")
        _strict_sha256(self.source_sha256, "source_sha256")
        if type(self.source_size) is not int or self.source_size <= 0:
            raise _fail("source_size must be a positive exact integer")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "importer_id": self.importer_id,
            "contract_origin_sha": self.contract_origin_sha,
            "execution_commit_sha": self.execution_commit_sha,
            "source_repository_path": self.source_repository_path,
            "source_sha256": self.source_sha256,
            "source_size": self.source_size,
        }

    @property
    def identity_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self._content_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["import_identity_sha256"] = self.identity_sha256
        return result


def default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validated_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _fail("field-trial safety keys mismatch")
    detached: dict[str, bool] = {}
    for key in sorted(_SAFETY_KEYS):
        if type(value[key]) is not bool or value[key] is not False:
            raise _fail(f"safety[{key!r}] must be exact bool False")
        detached[key] = False
    return types.MappingProxyType(detached)


@dataclasses.dataclass(frozen=True)
class PredictionFieldTrial:
    trial_key: str
    declared_leg_count: int
    reconstruction_status: ReconstructionStatus
    declared_settlement_summary: DeclaredSettlementSummary
    source_evidence: tuple[SourceEvidence, ...]
    diagnostic_notes: tuple[DiagnosticNote, ...]
    creation_import_identity: ImportIdentity
    legs: tuple[FieldTrialLeg, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        _strict_string(self.trial_key, "trial_key", identifier=True)
        declared = _strict_count(self.declared_leg_count, "declared_leg_count")
        if declared <= 0:
            raise _fail("declared_leg_count must be positive")
        if type(self.reconstruction_status) is not ReconstructionStatus:
            raise _fail("reconstruction_status must be typed")
        if type(self.declared_settlement_summary) is not DeclaredSettlementSummary:
            raise _fail("declared_settlement_summary must be typed")
        if (
            self.declared_settlement_summary.summary is not None
            and self.declared_settlement_summary.summary.total != declared
        ):
            raise _fail("declared settlement counts must equal declared_leg_count")
        if type(self.source_evidence) is not tuple or any(
            type(item) is not SourceEvidence for item in self.source_evidence
        ):
            raise _fail("source_evidence must be an exact tuple of SourceEvidence")
        if not self.source_evidence:
            raise _fail("field trial requires at least one source evidence record")
        source_ids = [item.source_id for item in self.source_evidence]
        if len(set(source_ids)) != len(source_ids):
            raise _fail("conflicting or duplicate source evidence identity")
        if type(self.diagnostic_notes) is not tuple or any(
            type(item) is not DiagnosticNote for item in self.diagnostic_notes
        ):
            raise _fail("diagnostic_notes must be an exact tuple of DiagnosticNote")
        if type(self.creation_import_identity) is not ImportIdentity:
            raise _fail("creation_import_identity must be typed")
        if type(self.legs) is not tuple or any(type(item) is not FieldTrialLeg for item in self.legs):
            raise _fail("legs must be an exact tuple of FieldTrialLeg")
        if len(self.legs) > declared:
            raise _fail("reconstructed legs exceed declared_leg_count")
        identities = [leg.leg_identity for leg in self.legs]
        if len(set(identities)) != len(identities):
            raise _fail("duplicate pre-match leg identity")
        unresolved = declared - self.reconstructed_leg_count
        expected_status = (
            ReconstructionStatus.COMPLETE
            if unresolved == 0
            else ReconstructionStatus.SUMMARY_ONLY
            if self.reconstructed_leg_count == 0
            else ReconstructionStatus.PARTIAL
        )
        if self.reconstruction_status is not expected_status:
            raise _fail(
                f"reconstruction_status must be {expected_status.value} for the leg counts"
            )
        if self.reconstruction_status is ReconstructionStatus.COMPLETE and unresolved:
            raise _fail("COMPLETE reconstruction cannot contain unresolved legs")
        source_by_id = {item.source_id: item for item in self.source_evidence}
        refs: list[str] = list(self.declared_settlement_summary.evidence_references)
        refs.extend(_evidenced_references_in(self.source_evidence))
        refs.extend(_evidenced_references_in(self.legs))
        verified_reference_groups: list[tuple[str, ...]] = []
        if (
            self.declared_settlement_summary.verification_state
            is VerificationState.VERIFIED
        ):
            verified_reference_groups.append(
                self.declared_settlement_summary.evidence_references
            )
        for note in self.diagnostic_notes:
            refs.extend(note.evidence_references)
            if note.verification_state is VerificationState.VERIFIED:
                verified_reference_groups.append(note.evidence_references)
        for leg in self.legs:
            refs.extend(leg.pre_match_decision.pre_match_evidence_references)
            refs.extend(leg.post_match_settlement.settlement_evidence_references)
            refs.extend(leg.post_match_attribution.evidence_references)
            for candidate in leg.pre_match_decision.eligible_market_candidates:
                refs.extend(candidate.pre_match_evidence_references)
            attribution = leg.post_match_attribution
            settlement = leg.post_match_settlement
            if settlement.verification_state is VerificationState.VERIFIED:
                verified_reference_groups.append(
                    settlement.settlement_evidence_references
                )
            if attribution.verification_state is VerificationState.VERIFIED:
                verified_reference_groups.append(attribution.evidence_references)
        missing_refs = sorted(set(refs).difference(source_by_id))
        if missing_refs:
            raise _fail(
                "audit record references unknown source evidence: "
                + ", ".join(missing_refs)
            )
        for group in verified_reference_groups:
            if not group or any(
                source_by_id[ref].verification_state is not VerificationState.VERIFIED
                for ref in group
            ):
                raise _fail(
                    "VERIFIED audit claims require VERIFIED source evidence"
                )
        object.__setattr__(self, "safety", _validated_safety(self.safety))

    @property
    def trial_identity(self) -> str:
        identity = {"dataset_name": DATASET_NAME, "trial_key": self.trial_key}
        return hashlib.sha256(_canonical_bytes(identity)).hexdigest()

    @property
    def reconstructed_leg_count(self) -> int:
        return len(self.reconstructed_legs)

    @property
    def recorded_leg_count(self) -> int:
        return len(self.legs)

    @property
    def reconstructed_legs(self) -> tuple[FieldTrialLeg, ...]:
        return tuple(
            leg
            for leg in self.legs
            if leg.reconstruction_state is LegReconstructionState.RECONSTRUCTED
        )

    @property
    def unresolved_leg_count(self) -> int:
        return self.declared_leg_count - self.reconstructed_leg_count

    @property
    def reconstructed_settlement_summary(self) -> SettlementSummary:
        return SettlementSummary.from_legs(self.reconstructed_legs)

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "trial_key": self.trial_key,
            "trial_identity": self.trial_identity,
            "declared_leg_count": self.declared_leg_count,
            "recorded_leg_count": self.recorded_leg_count,
            "reconstructed_leg_count": self.reconstructed_leg_count,
            "unresolved_leg_count": self.unresolved_leg_count,
            "reconstruction_status": self.reconstruction_status.value,
            "declared_settlement_summary": self.declared_settlement_summary.to_dict(),
            "reconstructed_settlement_summary": self.reconstructed_settlement_summary.to_dict(),
            "source_evidence": [item.to_dict() for item in self.source_evidence],
            "diagnostic_notes": [item.to_dict() for item in self.diagnostic_notes],
            "creation_import_identity": self.creation_import_identity.to_dict(),
            "legs": [leg.to_dict() for leg in self.legs],
            "safety": dict(self.safety),
        }

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self._content_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["canonical_sha256"] = self.canonical_sha256
        return result


def canonical_pre_match_decision_bytes(value: Any) -> bytes:
    if type(value) is not PreMatchDecisionRecord:
        raise _fail("pre-match value must be exact PreMatchDecisionRecord")
    return _canonical_bytes(value._content_dict())


def canonical_prediction_field_trial_bytes(value: Any) -> bytes:
    if type(value) is not PredictionFieldTrial:
        raise _fail("field-trial value must be exact PredictionFieldTrial")
    return _canonical_bytes(value.to_dict())


def _require_keys(value: Any, expected: set[str] | frozenset[str], label: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != set(expected):
        raise _fail(f"{label} keys do not match the exact contract")
    return value


def _evidenced_from_mapping(value: Any, label: str) -> EvidencedValue:
    payload = _require_keys(
        value,
        {"status", "value", "evidence_references"},
        label,
    )
    try:
        status = EvidenceAvailability(payload["status"])
    except (TypeError, ValueError) as exc:
        raise _fail(f"{label}.status is invalid") from exc
    refs = payload["evidence_references"]
    if type(refs) is not list:
        raise _fail(f"{label}.evidence_references must be an exact JSON array")
    return EvidencedValue(status, payload["value"], tuple(refs))


_CANDIDATE_KEYS = frozenset(
    {
        "candidate_id",
        "market_id",
        "outcome_id",
        "line",
        "model_probability",
        "fair_price",
        "risk_uncertainty",
        "original_rank",
        "original_score",
        "bookmaker_source",
        "exact_bookmaker_mapping",
        "bookmaker_price",
        "quote_observed_at",
        "quote_identity",
        "reason_not_selected",
        "pre_match_evidence_references",
    }
)


def _candidate_from_mapping(value: Any, label: str) -> MarketCandidate:
    payload = _require_keys(value, _CANDIDATE_KEYS, label)
    refs = payload["pre_match_evidence_references"]
    if type(refs) is not list:
        raise _fail(f"{label}.pre_match_evidence_references must be an exact JSON array")
    try:
        market, outcome, line = validate_selection(
            payload["market_id"], payload["outcome_id"], payload["line"]
        )
    except MarketRegistryError as exc:
        raise _fail(str(exc)) from exc
    kwargs = {
        name: _evidenced_from_mapping(payload[name], f"{label}.{name}")
        for name in (
            "model_probability",
            "fair_price",
            "risk_uncertainty",
            "original_rank",
            "original_score",
            "bookmaker_source",
            "exact_bookmaker_mapping",
            "bookmaker_price",
            "quote_observed_at",
            "quote_identity",
            "reason_not_selected",
        )
    }
    return MarketCandidate(
        candidate_id=payload["candidate_id"],
        market_id=market,
        outcome_id=outcome,
        line=line,
        pre_match_evidence_references=tuple(refs),
        **kwargs,
    )


_PRE_MATCH_KEYS = frozenset(
    {
        "record_key",
        "fixture_identity",
        "home_team",
        "away_team",
        "competition",
        "kickoff_time",
        "source_fixture_identifiers",
        "generated_at",
        "athena_version",
        "athena_commit",
        "model_identity",
        "pre_match_evidence_references",
        "model_raw_outputs",
        "score_distribution_model_identifiers",
        "eligible_market_candidates",
        "selected_candidate_id",
        "candidate_ranking",
        "counterfactual_candidate_ids",
    }
)


def _pre_match_from_mapping(value: Any, label: str) -> PreMatchDecisionRecord:
    payload = _require_keys(value, _PRE_MATCH_KEYS, label)
    refs = payload["pre_match_evidence_references"]
    if type(refs) is not list:
        raise _fail(f"{label}.pre_match_evidence_references must be an exact JSON array")
    candidates_payload = _require_keys(
        payload["eligible_market_candidates"],
        {"status", "records"},
        f"{label}.eligible_market_candidates",
    )
    try:
        candidate_status = EvidenceAvailability(candidates_payload["status"])
    except (TypeError, ValueError) as exc:
        raise _fail(f"{label}.eligible_market_candidates.status is invalid") from exc
    records = candidates_payload["records"]
    if type(records) is not list:
        raise _fail(f"{label}.eligible_market_candidates.records must be an exact JSON array")
    value_names = (
        "fixture_identity",
        "home_team",
        "away_team",
        "competition",
        "kickoff_time",
        "source_fixture_identifiers",
        "generated_at",
        "athena_version",
        "athena_commit",
        "model_identity",
        "model_raw_outputs",
        "score_distribution_model_identifiers",
        "selected_candidate_id",
        "candidate_ranking",
        "counterfactual_candidate_ids",
    )
    kwargs = {
        name: _evidenced_from_mapping(payload[name], f"{label}.{name}")
        for name in value_names
    }
    return PreMatchDecisionRecord(
        record_key=payload["record_key"],
        pre_match_evidence_references=tuple(refs),
        eligible_candidates_status=candidate_status,
        eligible_market_candidates=tuple(
            _candidate_from_mapping(item, f"{label}.eligible_market_candidates.records[{index}]")
            for index, item in enumerate(records)
        ),
        **kwargs,
    )


_SETTLEMENT_KEYS = frozenset(
    {
        "final_home_score",
        "final_away_score",
        "regulation_score_semantics",
        "result_source",
        "observed_at",
        "source_evidence_reference",
        "settlement_outcome",
        "settlement_evidence_references",
        "verification_state",
    }
)


def _settlement_from_mapping(value: Any, label: str) -> PostMatchSettlementRecord:
    payload = _require_keys(value, _SETTLEMENT_KEYS, label)
    refs = payload["settlement_evidence_references"]
    if type(refs) is not list:
        raise _fail(f"{label}.settlement_evidence_references must be an exact JSON array")
    try:
        outcome = SettlementOutcome(payload["settlement_outcome"])
        verification = VerificationState(payload["verification_state"])
    except (TypeError, ValueError) as exc:
        raise _fail(f"{label} settlement enum is invalid") from exc
    names = (
        "final_home_score",
        "final_away_score",
        "regulation_score_semantics",
        "result_source",
        "observed_at",
        "source_evidence_reference",
    )
    return PostMatchSettlementRecord(
        settlement_outcome=outcome,
        settlement_evidence_references=tuple(refs),
        verification_state=verification,
        **{
            name: _evidenced_from_mapping(payload[name], f"{label}.{name}")
            for name in names
        },
    )


_ATTRIBUTION_KEYS = frozenset(
    {
        "primary_factor",
        "contributing_factors",
        "decision_quality",
        "evidence_references",
        "observation_source_identity",
        "explanatory_notes",
        "verification_state",
    }
)


def _attribution_from_mapping(value: Any, label: str) -> PostMatchAttribution:
    payload = _require_keys(value, _ATTRIBUTION_KEYS, label)
    factors = payload["contributing_factors"]
    refs = payload["evidence_references"]
    if type(factors) is not list or type(refs) is not list:
        raise _fail(f"{label} contributing_factors/evidence_references must be arrays")
    try:
        return PostMatchAttribution(
            primary_factor=AttributionFactor(payload["primary_factor"]),
            contributing_factors=tuple(AttributionFactor(item) for item in factors),
            decision_quality=DecisionQuality(payload["decision_quality"]),
            evidence_references=tuple(refs),
            observation_source_identity=_evidenced_from_mapping(
                payload["observation_source_identity"],
                f"{label}.observation_source_identity",
            ),
            explanatory_notes=_evidenced_from_mapping(
                payload["explanatory_notes"],
                f"{label}.explanatory_notes",
            ),
            verification_state=VerificationState(payload["verification_state"]),
        )
    except ValueError as exc:
        if isinstance(exc, PredictionPostMatchAuditError):
            raise
        raise _fail(f"{label} contains an invalid enum") from exc


def _leg_from_mapping(value: Any, label: str) -> FieldTrialLeg:
    payload = _require_keys(
        value,
        {"pre_match_decision", "post_match_settlement", "post_match_attribution"},
        label,
    )
    return FieldTrialLeg(
        pre_match_decision=_pre_match_from_mapping(
            payload["pre_match_decision"], f"{label}.pre_match_decision"
        ),
        post_match_settlement=_settlement_from_mapping(
            payload["post_match_settlement"], f"{label}.post_match_settlement"
        ),
        post_match_attribution=_attribution_from_mapping(
            payload["post_match_attribution"], f"{label}.post_match_attribution"
        ),
    )


def _source_from_mapping(value: Any, label: str) -> SourceEvidence:
    payload = _require_keys(
        value,
        {
            "source_id",
            "authority",
            "reference",
            "content_sha256",
            "observed_at",
            "verification_state",
            "notes",
        },
        label,
    )
    try:
        return SourceEvidence(
            source_id=payload["source_id"],
            authority=EvidenceAuthority(payload["authority"]),
            reference=payload["reference"],
            content_sha256=_evidenced_from_mapping(
                payload["content_sha256"], f"{label}.content_sha256"
            ),
            observed_at=_evidenced_from_mapping(
                payload["observed_at"], f"{label}.observed_at"
            ),
            verification_state=VerificationState(payload["verification_state"]),
            notes=payload["notes"],
        )
    except ValueError as exc:
        if isinstance(exc, PredictionPostMatchAuditError):
            raise
        raise _fail(f"{label} contains an invalid enum") from exc


def _summary_from_mapping(value: Any, label: str) -> SettlementSummary:
    payload = _require_keys(
        value,
        {"WON", "LOST", "VOID", "PARTIAL_WIN", "PARTIAL_LOSS", "UNKNOWN"},
        label,
    )
    return SettlementSummary(
        won=payload["WON"],
        lost=payload["LOST"],
        void=payload["VOID"],
        partial_win=payload["PARTIAL_WIN"],
        partial_loss=payload["PARTIAL_LOSS"],
        unknown=payload["UNKNOWN"],
    )


def _declared_summary_from_mapping(value: Any) -> DeclaredSettlementSummary:
    payload = _require_keys(
        value,
        {"status", "counts", "evidence_references", "verification_state"},
        "declared_settlement_summary",
    )
    refs = payload["evidence_references"]
    if type(refs) is not list:
        raise _fail("declared settlement evidence_references must be an array")
    try:
        status = EvidenceAvailability(payload["status"])
        verification = VerificationState(payload["verification_state"])
    except (TypeError, ValueError) as exc:
        raise _fail("declared settlement summary enum is invalid") from exc
    summary = (
        None
        if payload["counts"] is None
        else _summary_from_mapping(payload["counts"], "declared_settlement_summary.counts")
    )
    return DeclaredSettlementSummary(status, summary, tuple(refs), verification)


def _diagnostic_from_mapping(value: Any, label: str) -> DiagnosticNote:
    payload = _require_keys(
        value,
        {"note_id", "text", "evidence_references", "verification_state"},
        label,
    )
    refs = payload["evidence_references"]
    if type(refs) is not list:
        raise _fail(f"{label}.evidence_references must be an exact JSON array")
    try:
        verification = VerificationState(payload["verification_state"])
    except (TypeError, ValueError) as exc:
        raise _fail(f"{label}.verification_state is invalid") from exc
    return DiagnosticNote(
        note_id=payload["note_id"],
        text=payload["text"],
        evidence_references=tuple(refs),
        verification_state=verification,
    )


_IMPORT_KEYS = frozenset(
    {
        "schema_version",
        "dataset_name",
        "trial_key",
        "declared_leg_count",
        "declared_settlement_summary",
        "source_evidence",
        "diagnostic_notes",
        "legs",
        "safety",
    }
)


def build_prediction_field_trial_from_import(
    value: Any,
    *,
    source_repository_path: str,
    source_sha256: str,
    source_size: int,
    execution_commit_sha: str,
) -> PredictionFieldTrial:
    """Build one deterministic audit object from strict local import JSON."""

    payload = _require_keys(value, _IMPORT_KEYS, "field-trial import")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != SCHEMA_VERSION:
        raise _fail(f"import schema_version must be exact integer {SCHEMA_VERSION}")
    if payload["dataset_name"] != IMPORT_DATASET_NAME:
        raise _fail(f"import dataset_name must be {IMPORT_DATASET_NAME}")
    if type(payload["source_evidence"]) is not list:
        raise _fail("source_evidence must be an exact JSON array")
    if type(payload["diagnostic_notes"]) is not list:
        raise _fail("diagnostic_notes must be an exact JSON array")
    if type(payload["legs"]) is not list:
        raise _fail("legs must be an exact JSON array")
    legs = tuple(
        _leg_from_mapping(item, f"legs[{index}]")
        for index, item in enumerate(payload["legs"])
    )
    declared = _strict_count(payload["declared_leg_count"], "declared_leg_count")
    reconstructed_count = sum(
        leg.reconstruction_state is LegReconstructionState.RECONSTRUCTED
        for leg in legs
    )
    status = (
        ReconstructionStatus.COMPLETE
        if reconstructed_count == declared
        else ReconstructionStatus.SUMMARY_ONLY
        if reconstructed_count == 0
        else ReconstructionStatus.PARTIAL
    )
    return PredictionFieldTrial(
        trial_key=payload["trial_key"],
        declared_leg_count=declared,
        reconstruction_status=status,
        declared_settlement_summary=_declared_summary_from_mapping(
            payload["declared_settlement_summary"]
        ),
        source_evidence=tuple(
            _source_from_mapping(item, f"source_evidence[{index}]")
            for index, item in enumerate(payload["source_evidence"])
        ),
        diagnostic_notes=tuple(
            _diagnostic_from_mapping(item, f"diagnostic_notes[{index}]")
            for index, item in enumerate(payload["diagnostic_notes"])
        ),
        creation_import_identity=ImportIdentity(
            importer_id=IMPORTER_ID,
            contract_origin_sha=CONTRACT_ORIGIN_SHA,
            execution_commit_sha=_strict_git_sha(
                execution_commit_sha,
                "execution_commit_sha",
            ),
            source_repository_path=source_repository_path,
            source_sha256=_strict_sha256(source_sha256, "source_sha256"),
            source_size=source_size,
        ),
        legs=legs,
        safety=_validated_safety(payload["safety"]),
    )


__all__ = [
    "CONTRACT_ORIGIN_SHA",
    "AttributionFactor",
    "DATASET_NAME",
    "DecisionQuality",
    "DeclaredSettlementSummary",
    "DiagnosticNote",
    "EvidenceAuthority",
    "EvidenceAvailability",
    "EvidencedValue",
    "FieldTrialLeg",
    "IMPORTER_ID",
    "IMPORT_DATASET_NAME",
    "ImportIdentity",
    "LegReconstructionState",
    "MarketCandidate",
    "PostMatchAttribution",
    "PostMatchSettlementRecord",
    "PreMatchDecisionRecord",
    "PredictionFieldTrial",
    "PredictionPostMatchAuditError",
    "ReconstructionStatus",
    "SCHEMA_VERSION",
    "SettlementOutcome",
    "SettlementSummary",
    "SourceEvidence",
    "VerificationState",
    "build_prediction_field_trial_from_import",
    "canonical_pre_match_decision_bytes",
    "canonical_prediction_field_trial_bytes",
    "default_safety",
    "missing_value",
    "unknown_value",
]
