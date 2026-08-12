"""Freeze a research-only legacy expected-goals transform candidate.

This is deliberately the boundary immediately before probability execution. It
replays reviewed PR #67 ancestry, preserves exact PR #31 feature values, and
can only reproduce the legacy rate heuristic as a research candidate. It does
not construct a score matrix or authorize probability inference.
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import math
import re
import types
from collections.abc import Mapping
from typing import Any

from domain.fixture_model_features import (
    FixtureModelFeatureError,
    ModelFeatureBlocker,
    ModelFeatureId,
    ModelFeatureResolution,
    ModelFeatureStatus,
    canonical_model_feature_snapshot_bytes,
)
from domain.fotmob_reviewed_match_details_model_feature_handoff import (
    FotMobReviewedMatchDetailsModelFeatureHandoffError,
    canonical_reviewed_match_details_model_feature_handoff_bytes,
    revalidate_reviewed_match_details_model_feature_handoff,
)
from domain.fotmob_reviewed_match_details_probability_model_readiness import (
    FotMobReviewedMatchDetailsProbabilityModelReadinessError,
    canonical_reviewed_match_details_probability_model_readiness_bytes,
    revalidate_reviewed_match_details_probability_model_readiness,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-reviewed-match-details-expected-goals-transform-candidate-v1"
CANDIDATE_SCOPE = "EXACT_REVALIDATED_PR67_FEATURE_STATE_RESEARCH_ONLY"
TRANSFORM_ID = "LEGACY_MATCH_ANALYST_POISSON_RATE_HEURISTIC_V1"
TRANSFORM_SCHEMA_VERSION = 1
_SOURCE_REFERENCE = "intelligence.match_analyst:legacy_poisson_rate_heuristic"
_REQUIRED_FEATURE_IDS = tuple(sorted(ModelFeatureId, key=lambda item: item.value))
_SHA_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_FIXTURE_RE = re.compile(r"^FOTMOB:([1-9][0-9]*)$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "expected_goals_transform_approved",
        "probability_inference_authorized",
        "score_matrix_authorized",
        "probability_adjustment_authorized",
        "pricing_authorized",
        "market_activation_authorized",
        "selection_authorized",
        "production_approval_authorized",
        "bet_authorized",
    }
)


class FotMobReviewedMatchDetailsExpectedGoalsTransformCandidateError(ValueError):
    """Raised when a research candidate cannot be proven from reviewed ancestry."""


class ExpectedGoalsCandidateStatus(str, enum.Enum):
    AVAILABLE_RESEARCH_CANDIDATE = "AVAILABLE_RESEARCH_CANDIDATE"
    BLOCKED_FEATURE_INPUTS = "BLOCKED_FEATURE_INPUTS"


def _error(message: str) -> FotMobReviewedMatchDetailsExpectedGoalsTransformCandidateError:
    return FotMobReviewedMatchDetailsExpectedGoalsTransformCandidateError(message)


def _sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise _error(f"{label} must be exactly 64 lowercase hexadecimal characters")
    return value


def _positive_size(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise _error(f"{label} must be an exact positive integer")
    return value


def _text(value: Any, label: str, maximum: int = 4096) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > maximum:
        raise _error(f"{label} must be a non-empty exact trimmed string")
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime) or value.tzinfo is not datetime.timezone.utc:
        raise _error(f"{label} must already use exact datetime.timezone.utc")
    return value


def _iso(value: datetime.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _finite_float(value: Any, label: str) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise _error(f"{label} must be an exact finite float")
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("expected-goals candidate serialization failed") from exc
    return (payload + "\n").encode("utf-8")


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("candidate safety keys mismatch")
    if any(type(item) is not bool or item is not False for item in value.values()):
        raise _error("all candidate safety values must be exact bool False")
    return _default_safety()


@dataclasses.dataclass(frozen=True)
class LegacyExpectedGoalsTransformSpecification:
    transform_id: str
    schema_version: int
    source_reference: str
    required_feature_ids: tuple[ModelFeatureId, ...]
    freshness_switch_threshold: float
    freshness_switch_comparison: str
    form_path_description: str
    elo_center: float
    elo_divisor: float
    raw_min: float
    raw_max: float
    home_baseline: float
    away_baseline: float
    fatigue_coefficient: float
    minimum_rate: float
    decimal_rounding_places: int
    rounding_order: str
    candidate_only: bool

    def __post_init__(self) -> None:
        if self.transform_id != TRANSFORM_ID or self.schema_version != TRANSFORM_SCHEMA_VERSION:
            raise _error("legacy transform specification identity mismatch")
        if self.source_reference != _SOURCE_REFERENCE:
            raise _error("legacy transform source reference mismatch")
        if type(self.required_feature_ids) is not tuple or self.required_feature_ids != _REQUIRED_FEATURE_IDS:
            raise _error("legacy transform required feature IDs mismatch")
        for value, label in (
            (self.freshness_switch_threshold, "freshness_switch_threshold"),
            (self.elo_center, "elo_center"),
            (self.elo_divisor, "elo_divisor"),
            (self.raw_min, "raw_min"),
            (self.raw_max, "raw_max"),
            (self.home_baseline, "home_baseline"),
            (self.away_baseline, "away_baseline"),
            (self.fatigue_coefficient, "fatigue_coefficient"),
            (self.minimum_rate, "minimum_rate"),
        ):
            _finite_float(value, label)
        if self.freshness_switch_comparison != "LESS_THAN":
            raise _error("legacy freshness comparison mismatch")
        if self.form_path_description != "home_raw=home_form; away_raw=away_form":
            raise _error("legacy form path description mismatch")
        if self.elo_divisor == 0.0 or self.raw_min > self.raw_max:
            raise _error("legacy transform numeric bounds are invalid")
        if type(self.decimal_rounding_places) is not int or self.decimal_rounding_places != 3:
            raise _error("legacy decimal rounding places mismatch")
        if self.rounding_order != "round(base_rate, 3) then max(0.05, rounded_rate)":
            raise _error("legacy rounding order mismatch")
        if type(self.candidate_only) is not bool or self.candidate_only is not True:
            raise _error("legacy specification must remain research candidate only")
        if (
            self.freshness_switch_threshold,
            self.elo_center,
            self.elo_divisor,
            self.raw_min,
            self.raw_max,
            self.home_baseline,
            self.away_baseline,
            self.fatigue_coefficient,
            self.minimum_rate,
        ) != (0.05, 1500.0, 800.0, 0.1, 0.9, 1.45, 1.25, 0.5, 0.05):
            raise _error("legacy transform constants differ from frozen source behavior")

    def to_dict(self) -> dict[str, Any]:
        return {
            "transform_id": self.transform_id,
            "schema_version": self.schema_version,
            "source_reference": self.source_reference,
            "required_feature_ids": [item.value for item in self.required_feature_ids],
            "freshness_switch_threshold": self.freshness_switch_threshold,
            "freshness_switch_comparison": self.freshness_switch_comparison,
            "form_path_description": self.form_path_description,
            "elo_center": self.elo_center,
            "elo_divisor": self.elo_divisor,
            "raw_min": self.raw_min,
            "raw_max": self.raw_max,
            "home_baseline": self.home_baseline,
            "away_baseline": self.away_baseline,
            "fatigue_coefficient": self.fatigue_coefficient,
            "minimum_rate": self.minimum_rate,
            "decimal_rounding_places": self.decimal_rounding_places,
            "rounding_order": self.rounding_order,
            "candidate_only": self.candidate_only,
        }


def legacy_expected_goals_transform_specification() -> LegacyExpectedGoalsTransformSpecification:
    """Return the exact source-frozen legacy heuristic specification."""

    return LegacyExpectedGoalsTransformSpecification(
        transform_id=TRANSFORM_ID,
        schema_version=TRANSFORM_SCHEMA_VERSION,
        source_reference=_SOURCE_REFERENCE,
        required_feature_ids=_REQUIRED_FEATURE_IDS,
        freshness_switch_threshold=0.05,
        freshness_switch_comparison="LESS_THAN",
        form_path_description="home_raw=home_form; away_raw=away_form",
        elo_center=1500.0,
        elo_divisor=800.0,
        raw_min=0.1,
        raw_max=0.9,
        home_baseline=1.45,
        away_baseline=1.25,
        fatigue_coefficient=0.5,
        minimum_rate=0.05,
        decimal_rounding_places=3,
        rounding_order="round(base_rate, 3) then max(0.05, rounded_rate)",
        candidate_only=True,
    )


def canonical_legacy_expected_goals_transform_specification_bytes(value: Any) -> bytes:
    if type(value) is not LegacyExpectedGoalsTransformSpecification:
        raise _error("value must be exact legacy transform specification")
    return _canonical_json_bytes(dataclasses.replace(value).to_dict())


def sha256_legacy_expected_goals_transform_specification(value: Any) -> str:
    return hashlib.sha256(
        canonical_legacy_expected_goals_transform_specification_bytes(value)
    ).hexdigest()


@dataclasses.dataclass(frozen=True)
class ExpectedGoalsFeatureAudit:
    feature_id: ModelFeatureId
    status: ModelFeatureStatus
    value: float | None
    blockers: tuple[ModelFeatureBlocker, ...]
    evidence_sha256s: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.feature_id, ModelFeatureId) or not isinstance(self.status, ModelFeatureStatus):
            raise _error("candidate feature audit identities must be exact PR #31 enums")
        if type(self.blockers) is not tuple or any(not isinstance(item, ModelFeatureBlocker) for item in self.blockers):
            raise _error("candidate feature audit blockers must be an immutable exact tuple")
        if self.blockers != tuple(sorted(set(self.blockers), key=lambda item: item.value)):
            raise _error("candidate feature audit blockers must be unique and sorted")
        if type(self.evidence_sha256s) is not tuple:
            raise _error("candidate feature audit evidence identities must be a tuple")
        evidence = tuple(_sha256(item, "candidate feature audit evidence SHA") for item in self.evidence_sha256s)
        if evidence != tuple(sorted(set(evidence))):
            raise _error("candidate feature audit evidence identities must be unique and sorted")
        if self.status is ModelFeatureStatus.AVAILABLE:
            _finite_float(self.value, "AVAILABLE candidate feature value")
            if self.blockers:
                raise _error("AVAILABLE candidate feature must not have blockers")
        elif self.value is not None:
            raise _error("non-AVAILABLE candidate feature must not retain a value")
        if self.status is ModelFeatureStatus.MISSING and (self.blockers or evidence):
            raise _error("MISSING candidate feature must not invent blockers or evidence")
        if self.status is ModelFeatureStatus.BLOCKED and not self.blockers:
            raise _error("BLOCKED candidate feature must preserve blockers")
        object.__setattr__(self, "evidence_sha256s", evidence)

    @classmethod
    def from_resolution(cls, value: Any) -> "ExpectedGoalsFeatureAudit":
        if type(value) is not ModelFeatureResolution:
            raise _error("candidate feature audit source must be exact PR #31 resolution")
        try:
            rebuilt = dataclasses.replace(value)
        except (FixtureModelFeatureError, TypeError, ValueError) as exc:
            raise _error("PR #31 resolution reconstruction failed") from exc
        return cls(
            feature_id=rebuilt.feature_id,
            status=rebuilt.status,
            value=rebuilt.value,
            blockers=rebuilt.blockers,
            evidence_sha256s=rebuilt.evidence_sha256s,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id.value,
            "status": self.status.value,
            "value": self.value,
            "blockers": [item.value for item in self.blockers],
            "evidence_sha256s": list(self.evidence_sha256s),
        }


def _rates_from_audits(
    audits: tuple[ExpectedGoalsFeatureAudit, ...],
    specification: LegacyExpectedGoalsTransformSpecification,
) -> tuple[float, float]:
    values = {item.feature_id: item.value for item in audits}
    if set(values) != set(_REQUIRED_FEATURE_IDS) or any(value is None for value in values.values()):
        raise _error("candidate rate computation requires all six exact available features")
    home_raw = values[ModelFeatureId.HOME_FORM]
    away_raw = values[ModelFeatureId.AWAY_FORM]
    freshness = values[ModelFeatureId.LIVE_DATA_FRESHNESS]
    home_elo = values[ModelFeatureId.HOME_ELO]
    away_elo = values[ModelFeatureId.AWAY_ELO]
    fatigue = values[ModelFeatureId.FATIGUE]
    assert all(value is not None for value in (home_raw, away_raw, freshness, home_elo, away_elo, fatigue))
    if freshness < specification.freshness_switch_threshold:
        home_raw = 0.50 + ((home_elo - specification.elo_center) / specification.elo_divisor)
        away_raw = 0.50 + ((away_elo - specification.elo_center) / specification.elo_divisor)
        home_raw = max(specification.raw_min, min(specification.raw_max, home_raw))
        away_raw = max(specification.raw_min, min(specification.raw_max, away_raw))
    base_home = specification.home_baseline + (home_raw - away_raw) - (fatigue * specification.fatigue_coefficient)
    base_away = specification.away_baseline + (away_raw - home_raw) + (fatigue * specification.fatigue_coefficient)
    home_rate = max(specification.minimum_rate, round(base_home, specification.decimal_rounding_places))
    away_rate = max(specification.minimum_rate, round(base_away, specification.decimal_rounding_places))
    return _finite_float(home_rate, "home_expected_goals_candidate"), _finite_float(away_rate, "away_expected_goals_candidate")


@dataclasses.dataclass(frozen=True)
class ReviewedMatchDetailsExpectedGoalsTransformCandidate:
    schema_version: int
    dataset_name: str
    candidate_scope: str
    source_pr67_sha256: str
    source_pr67_size: int
    fixture_identifier: str
    source_match_id: str
    kickoff: datetime.datetime
    as_of: datetime.datetime
    source_pr31_snapshot_sha256: str
    source_pr31_snapshot_size: int
    transform_id: str
    transform_spec_sha256: str
    transform_spec_size: int
    required_feature_audits: tuple[ExpectedGoalsFeatureAudit, ...]
    status: ExpectedGoalsCandidateStatus
    blocking_feature_ids: tuple[ModelFeatureId, ...]
    home_expected_goals_candidate: float | None
    away_expected_goals_candidate: float | None
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise _error("candidate schema_version mismatch")
        if self.dataset_name != DATASET_NAME or self.candidate_scope != CANDIDATE_SCOPE:
            raise _error("candidate dataset identity mismatch")
        source_sha = _sha256(self.source_pr67_sha256, "source_pr67_sha256")
        snapshot_sha = _sha256(self.source_pr31_snapshot_sha256, "source_pr31_snapshot_sha256")
        spec_sha = _sha256(self.transform_spec_sha256, "transform_spec_sha256")
        source_size = _positive_size(self.source_pr67_size, "source_pr67_size")
        snapshot_size = _positive_size(self.source_pr31_snapshot_size, "source_pr31_snapshot_size")
        spec_size = _positive_size(self.transform_spec_size, "transform_spec_size")
        fixture = _text(self.fixture_identifier, "fixture_identifier", 512)
        source_match_id = _text(self.source_match_id, "source_match_id", 256)
        match = _FIXTURE_RE.fullmatch(fixture)
        if match is None or match.group(1) != source_match_id:
            raise _error("candidate fixture_identifier/source_match_id mismatch")
        kickoff = _utc(self.kickoff, "kickoff")
        as_of = _utc(self.as_of, "as_of")
        if as_of >= kickoff:
            raise _error("candidate as_of must be strictly before kickoff")
        specification = legacy_expected_goals_transform_specification()
        spec_bytes = canonical_legacy_expected_goals_transform_specification_bytes(specification)
        if self.transform_id != TRANSFORM_ID or spec_sha != hashlib.sha256(spec_bytes).hexdigest() or spec_size != len(spec_bytes):
            raise _error("candidate transform specification identity mismatch")
        if type(self.required_feature_audits) is not tuple or any(type(item) is not ExpectedGoalsFeatureAudit for item in self.required_feature_audits):
            raise _error("candidate required feature audits must be an immutable exact tuple")
        audits = tuple(dataclasses.replace(item) for item in self.required_feature_audits)
        if tuple(item.feature_id for item in audits) != _REQUIRED_FEATURE_IDS:
            raise _error("candidate required feature audits must contain each exact PR #31 feature")
        if not isinstance(self.status, ExpectedGoalsCandidateStatus):
            raise _error("candidate status must be exact ExpectedGoalsCandidateStatus")
        if type(self.blocking_feature_ids) is not tuple or any(not isinstance(item, ModelFeatureId) for item in self.blocking_feature_ids):
            raise _error("candidate blocking feature IDs must be exact immutable IDs")
        blocking = tuple(item.feature_id for item in audits if item.status is not ModelFeatureStatus.AVAILABLE)
        if self.blocking_feature_ids != blocking:
            raise _error("candidate blocking feature IDs differ from exact audits")
        if self.status is ExpectedGoalsCandidateStatus.BLOCKED_FEATURE_INPUTS:
            if not blocking or self.home_expected_goals_candidate is not None or self.away_expected_goals_candidate is not None:
                raise _error("blocked candidate must contain blockers and no rate values")
        else:
            if blocking:
                raise _error("available research candidate cannot retain blocking features")
            home_rate, away_rate = _rates_from_audits(audits, specification)
            if self.home_expected_goals_candidate != home_rate or self.away_expected_goals_candidate != away_rate:
                raise _error("candidate rates differ from frozen legacy transform")
            if home_rate < specification.minimum_rate or away_rate < specification.minimum_rate:
                raise _error("candidate rates violate frozen minimum rate")
        safety = _validate_safety(self.safety)
        object.__setattr__(self, "source_pr67_sha256", source_sha)
        object.__setattr__(self, "source_pr67_size", source_size)
        object.__setattr__(self, "source_pr31_snapshot_sha256", snapshot_sha)
        object.__setattr__(self, "source_pr31_snapshot_size", snapshot_size)
        object.__setattr__(self, "transform_spec_sha256", spec_sha)
        object.__setattr__(self, "transform_spec_size", spec_size)
        object.__setattr__(self, "fixture_identifier", fixture)
        object.__setattr__(self, "source_match_id", source_match_id)
        object.__setattr__(self, "kickoff", kickoff)
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "required_feature_audits", audits)
        object.__setattr__(self, "safety", safety)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "candidate_scope": self.candidate_scope,
            "source_pr67_sha256": self.source_pr67_sha256,
            "source_pr67_size": self.source_pr67_size,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "kickoff": _iso(self.kickoff),
            "as_of": _iso(self.as_of),
            "source_pr31_snapshot_sha256": self.source_pr31_snapshot_sha256,
            "source_pr31_snapshot_size": self.source_pr31_snapshot_size,
            "transform_id": self.transform_id,
            "transform_spec_sha256": self.transform_spec_sha256,
            "transform_spec_size": self.transform_spec_size,
            "required_feature_audits": [dataclasses.replace(item).to_dict() for item in self.required_feature_audits],
            "status": self.status.value,
            "blocking_feature_ids": [item.value for item in self.blocking_feature_ids],
            "home_expected_goals_candidate": self.home_expected_goals_candidate,
            "away_expected_goals_candidate": self.away_expected_goals_candidate,
            "safety": dict(self.safety),
        }


def build_reviewed_match_details_expected_goals_transform_candidate(
    *,
    materialization_inputs: Any,
    candidate_set: Any,
    candidate_set_bytes: Any,
    admission: Any,
    admission_bytes: Any,
    artifact: Any,
    artifact_bytes: Any,
    handoff: Any,
    handoff_bytes: Any,
    readiness: Any,
    readiness_bytes: Any,
) -> ReviewedMatchDetailsExpectedGoalsTransformCandidate:
    """Replay PR #52→PR #67 and freeze the legacy heuristic as research only."""

    try:
        rebuilt_pr67 = revalidate_reviewed_match_details_probability_model_readiness(
            materialization_inputs=materialization_inputs,
            candidate_set=candidate_set,
            candidate_set_bytes=candidate_set_bytes,
            admission=admission,
            admission_bytes=admission_bytes,
            artifact=artifact,
            artifact_bytes=artifact_bytes,
            handoff=handoff,
            handoff_bytes=handoff_bytes,
            readiness=readiness,
            readiness_bytes=readiness_bytes,
        )
        rebuilt_pr66 = revalidate_reviewed_match_details_model_feature_handoff(
            materialization_inputs=materialization_inputs,
            candidate_set=candidate_set,
            candidate_set_bytes=candidate_set_bytes,
            admission=admission,
            admission_bytes=admission_bytes,
            artifact=artifact,
            artifact_bytes=artifact_bytes,
            handoff=handoff,
            handoff_bytes=handoff_bytes,
        )
        pr67_bytes = canonical_reviewed_match_details_probability_model_readiness_bytes(rebuilt_pr67)
        pr31_bytes = canonical_model_feature_snapshot_bytes(rebuilt_pr66.model_feature_snapshot)
        if (
            rebuilt_pr67.source_pr66_sha256 != hashlib.sha256(canonical_reviewed_match_details_model_feature_handoff_bytes(rebuilt_pr66)).hexdigest()
            or rebuilt_pr67.source_model_feature_snapshot_sha256 != hashlib.sha256(pr31_bytes).hexdigest()
            or rebuilt_pr67.source_model_feature_snapshot_size != len(pr31_bytes)
            or rebuilt_pr67.fixture_identifier != rebuilt_pr66.fixture_identifier
            or rebuilt_pr67.source_match_id != rebuilt_pr66.source_match_id
            or rebuilt_pr67.kickoff != rebuilt_pr66.kickoff
            or rebuilt_pr67.as_of != rebuilt_pr66.as_of
        ):
            raise _error("PR #67 and rebuilt PR #66 identities differ")
        resolutions = rebuilt_pr66.model_feature_snapshot.features
        if type(resolutions) is not tuple or {item.feature_id for item in resolutions} != set(_REQUIRED_FEATURE_IDS) or len(resolutions) != len(_REQUIRED_FEATURE_IDS):
            raise _error("rebuilt PR #31 snapshot must contain every exact feature once")
        by_id = {item.feature_id: dataclasses.replace(item) for item in resolutions}
        audits = tuple(ExpectedGoalsFeatureAudit.from_resolution(by_id[item]) for item in _REQUIRED_FEATURE_IDS)
    except (
        FotMobReviewedMatchDetailsExpectedGoalsTransformCandidateError,
        FotMobReviewedMatchDetailsProbabilityModelReadinessError,
        FotMobReviewedMatchDetailsModelFeatureHandoffError,
        FixtureModelFeatureError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise _error("PR #52 -> PR #68 candidate construction failed closed") from exc

    specification = legacy_expected_goals_transform_specification()
    spec_bytes = canonical_legacy_expected_goals_transform_specification_bytes(specification)
    blocking = tuple(item.feature_id for item in audits if item.status is not ModelFeatureStatus.AVAILABLE)
    if blocking:
        status = ExpectedGoalsCandidateStatus.BLOCKED_FEATURE_INPUTS
        home_rate = None
        away_rate = None
    else:
        status = ExpectedGoalsCandidateStatus.AVAILABLE_RESEARCH_CANDIDATE
        home_rate, away_rate = _rates_from_audits(audits, specification)
    return ReviewedMatchDetailsExpectedGoalsTransformCandidate(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        candidate_scope=CANDIDATE_SCOPE,
        source_pr67_sha256=hashlib.sha256(pr67_bytes).hexdigest(),
        source_pr67_size=len(pr67_bytes),
        fixture_identifier=rebuilt_pr67.fixture_identifier,
        source_match_id=rebuilt_pr67.source_match_id,
        kickoff=rebuilt_pr67.kickoff,
        as_of=rebuilt_pr67.as_of,
        source_pr31_snapshot_sha256=hashlib.sha256(pr31_bytes).hexdigest(),
        source_pr31_snapshot_size=len(pr31_bytes),
        transform_id=TRANSFORM_ID,
        transform_spec_sha256=hashlib.sha256(spec_bytes).hexdigest(),
        transform_spec_size=len(spec_bytes),
        required_feature_audits=audits,
        status=status,
        blocking_feature_ids=blocking,
        home_expected_goals_candidate=home_rate,
        away_expected_goals_candidate=away_rate,
        safety=_default_safety(),
    )


def reviewed_match_details_expected_goals_transform_candidate_to_dict(value: Any) -> dict[str, Any]:
    if type(value) is not ReviewedMatchDetailsExpectedGoalsTransformCandidate:
        raise _error("value must be exact PR #68 candidate artifact")
    return dataclasses.replace(value).to_dict()


def canonical_reviewed_match_details_expected_goals_transform_candidate_bytes(value: Any) -> bytes:
    if type(value) is not ReviewedMatchDetailsExpectedGoalsTransformCandidate:
        raise _error("value must be exact PR #68 candidate artifact")
    try:
        return _canonical_json_bytes(dataclasses.replace(value).to_dict())
    except FotMobReviewedMatchDetailsExpectedGoalsTransformCandidateError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise _error("PR #68 candidate canonicalization failed") from exc


def sha256_reviewed_match_details_expected_goals_transform_candidate(value: Any) -> str:
    return hashlib.sha256(
        canonical_reviewed_match_details_expected_goals_transform_candidate_bytes(value)
    ).hexdigest()


def revalidate_reviewed_match_details_expected_goals_transform_candidate(
    *,
    materialization_inputs: Any,
    candidate_set: Any,
    candidate_set_bytes: Any,
    admission: Any,
    admission_bytes: Any,
    artifact: Any,
    artifact_bytes: Any,
    handoff: Any,
    handoff_bytes: Any,
    readiness: Any,
    readiness_bytes: Any,
    candidate: Any,
    candidate_bytes: Any,
) -> ReviewedMatchDetailsExpectedGoalsTransformCandidate:
    """Replay PR #52→PR #68 and reject detached or coordinated mutation."""

    if type(candidate) is not ReviewedMatchDetailsExpectedGoalsTransformCandidate:
        raise _error("candidate must be exact PR #68 artifact")
    if type(candidate_bytes) is not bytes:
        raise _error("candidate_bytes must be exact immutable bytes")
    try:
        supplied = canonical_reviewed_match_details_expected_goals_transform_candidate_bytes(candidate)
        rebuilt = build_reviewed_match_details_expected_goals_transform_candidate(
            materialization_inputs=materialization_inputs,
            candidate_set=candidate_set,
            candidate_set_bytes=candidate_set_bytes,
            admission=admission,
            admission_bytes=admission_bytes,
            artifact=artifact,
            artifact_bytes=artifact_bytes,
            handoff=handoff,
            handoff_bytes=handoff_bytes,
            readiness=readiness,
            readiness_bytes=readiness_bytes,
        )
        exact = canonical_reviewed_match_details_expected_goals_transform_candidate_bytes(rebuilt)
    except (
        FotMobReviewedMatchDetailsExpectedGoalsTransformCandidateError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise _error("PR #52 -> PR #68 candidate failed exact full-chain replay") from exc
    if supplied != exact:
        raise _error("supplied PR #68 candidate differs from exact full-chain rebuild")
    if candidate_bytes != exact:
        raise _error("candidate_bytes are not exact canonical PR #68 bytes")
    return rebuilt


__all__ = [
    "CANDIDATE_SCOPE",
    "DATASET_NAME",
    "SCHEMA_VERSION",
    "TRANSFORM_ID",
    "TRANSFORM_SCHEMA_VERSION",
    "ExpectedGoalsCandidateStatus",
    "ExpectedGoalsFeatureAudit",
    "FotMobReviewedMatchDetailsExpectedGoalsTransformCandidateError",
    "LegacyExpectedGoalsTransformSpecification",
    "ReviewedMatchDetailsExpectedGoalsTransformCandidate",
    "build_reviewed_match_details_expected_goals_transform_candidate",
    "canonical_legacy_expected_goals_transform_specification_bytes",
    "canonical_reviewed_match_details_expected_goals_transform_candidate_bytes",
    "legacy_expected_goals_transform_specification",
    "revalidate_reviewed_match_details_expected_goals_transform_candidate",
    "reviewed_match_details_expected_goals_transform_candidate_to_dict",
    "sha256_legacy_expected_goals_transform_specification",
    "sha256_reviewed_match_details_expected_goals_transform_candidate",
]
