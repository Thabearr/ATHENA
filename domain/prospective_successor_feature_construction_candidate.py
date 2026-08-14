"""Pure candidate construction of the five raw successor inputs.

PR #80 reproduces the form, Elo and fatigue mathematics frozen by PR #78 over
explicit caller-supplied source-scoped final-result evidence. It intentionally
does not prove that any current/live source supplies a complete equivalent
history corpus and it authorizes no expected-goals, probability, pricing,
selection, production, or betting path.
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
from collections.abc import Mapping, Sequence
from typing import Any

from domain.successor_live_input_semantic_qualification_execution import (
    build_successor_live_input_semantic_qualification_execution,
    canonical_successor_live_input_semantic_qualification_execution_bytes,
)
from domain.successor_live_input_semantic_qualification_protocol import (
    ELO_INITIALIZATION_SEMANTICS,
    build_successor_live_input_semantic_qualification_protocol,
    canonical_successor_live_input_semantic_qualification_protocol_bytes,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-prospective-successor-feature-construction-candidate-v1"
CONSTRUCTION_SCOPE = (
    "PURE_CALLER_SUPPLIED_SOURCE_SCOPED_HISTORY_TO_FROZEN_SUCCESSOR_RAW_FEATURES_ONLY"
)
CONSTRUCTION_STATE = (
    "CONSTRUCTED_CANDIDATE_NOT_LIVE_SOURCE_QUALIFIED_NOT_SUCCESSOR_AUTHORIZED"
)
NEXT_REQUIRED_BOUNDARY = "BUILD_REVIEWED_SOURCE_HISTORY_ADAPTER_AND_COMPLETENESS_PROOF"

PR79_MAIN_SHA = "d118fa702856d267bb6dc49301ebaee2a50dd533"
PR78_PROTOCOL_SHA256 = "97a47d431ce57468598b17fcb24e9e0e9a41fa26c80ff1f4df9e2e611107ed7c"
PR78_PROTOCOL_SIZE = 4904
PR79_ASSESSMENT_SHA256 = "aea27d67b93bf777a01c4956757ba7b31c521e9eea71006d20ca5bd4acf791f4"
PR79_ASSESSMENT_SIZE = 6204

SOURCE_LOCAL_TIME_BASIS = "SOURCE_LOCAL_NAIVE_DATETIME_REQUIRED_FOR_PR78_PARITY"
HISTORY_SEMANTIC_EQUIVALENCE = (
    "UNPROVEN_UNTIL_REVIEWED_SOURCE_ADAPTER_PROVES_HISTORY_COMPLETENESS_IDENTITY_AND_CHRONOLOGY"
)
FEATURE_ORDER = ("home_elo", "away_elo", "home_form", "away_form", "fatigue")
CONSTRUCTION_SPEC_SHA256 = "75fe157d1b767cf374e5c2a27cc3d96434aa12f2214fc37d7c91b1e7127eb4b7"
CONSTRUCTION_SPEC_SIZE = 2330

_SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/-]{0,255}$", re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "source_history_adapter_approved",
        "source_history_completeness_proven",
        "successor_live_inputs_qualified",
        "successor_candidate_approved",
        "expected_goals_transform_approved",
        "expected_goals_production_authorized",
        "score_matrix_authorized",
        "probability_inference_authorized",
        "probability_adjustment_authorized",
        "calibration_for_production_authorized",
        "pricing_authorized",
        "market_activation_authorized",
        "selection_authorized",
        "production_approval_authorized",
        "bet_authorized",
    }
)


class ProspectiveSuccessorFeatureConstructionError(ValueError):
    """Raised when a prospective construction cannot be proven deterministic/safe."""


class ConstructedFeatureStatus(str, enum.Enum):
    CONSTRUCTED_FROM_SUPPLIED_HISTORY = "CONSTRUCTED_FROM_SUPPLIED_HISTORY"
    CONSTRUCTED_FROM_FROZEN_INITIAL_STATE_ASSUMPTION = (
        "CONSTRUCTED_FROM_FROZEN_INITIAL_STATE_ASSUMPTION"
    )
    MISSING_PRIOR_HISTORY = "MISSING_PRIOR_HISTORY"


def _error(message: str) -> ProspectiveSuccessorFeatureConstructionError:
    return ProspectiveSuccessorFeatureConstructionError(message)


def _text(value: Any, label: str, maximum: int = 1024) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > maximum:
        raise _error(f"{label} must be exact non-empty trimmed text")
    return value


def _identifier(value: Any, label: str) -> str:
    result = _text(value, label, 256)
    if _ID_RE.fullmatch(result) is None:
        raise _error(f"{label} has unsupported identity characters")
    return result


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise _error(f"{label} must be exact lowercase SHA-256")
    return value


def _local(value: Any, label: str) -> datetime.datetime:
    if type(value) is not datetime.datetime or value.tzinfo is not None:
        raise _error(f"{label} must be exact naive source-local datetime")
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if type(value) is not datetime.datetime or value.tzinfo is not datetime.timezone.utc:
        raise _error(f"{label} must use exact datetime.timezone.utc")
    return value


def _canonical(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("canonical serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _checked_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error("all downstream safety values must be exact False")
    return _safety()


def _verify_upstream() -> None:
    protocol = build_successor_live_input_semantic_qualification_protocol()
    protocol_bytes = canonical_successor_live_input_semantic_qualification_protocol_bytes(protocol)
    if (
        hashlib.sha256(protocol_bytes).hexdigest() != PR78_PROTOCOL_SHA256
        or len(protocol_bytes) != PR78_PROTOCOL_SIZE
    ):
        raise _error("PR78 protocol identity changed")

    assessment = build_successor_live_input_semantic_qualification_execution()
    assessment_bytes = canonical_successor_live_input_semantic_qualification_execution_bytes(
        assessment
    )
    if (
        hashlib.sha256(assessment_bytes).hexdigest() != PR79_ASSESSMENT_SHA256
        or len(assessment_bytes) != PR79_ASSESSMENT_SIZE
    ):
        raise _error("PR79 assessment identity changed")


def _spec_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "construction_scope": CONSTRUCTION_SCOPE,
        "repository_main_sha": PR79_MAIN_SHA,
        "pr78_protocol_sha256": PR78_PROTOCOL_SHA256,
        "pr78_protocol_size": PR78_PROTOCOL_SIZE,
        "pr79_assessment_sha256": PR79_ASSESSMENT_SHA256,
        "pr79_assessment_size": PR79_ASSESSMENT_SIZE,
        "source_history_contract": (
            "CALLER_SUPPLIED_SOURCE_SCOPED_FINAL_RESULT_EVIDENCE_ONLY_NO_COMPLETENESS_CLAIM"
        ),
        "source_local_time_basis": SOURCE_LOCAL_TIME_BASIS,
        "history_selection_rule": (
            "STRICTLY_PRIOR_IN_BOTH_LOCAL_AND_UTC;"
            "EVERY_SUPPLIED_PRIOR_RESULT_MUST_BE_OBSERVED_BY_TARGET_AS_OF"
        ),
        "history_order_rule": (
            "SOURCE_LOCAL_KICKOFF_ASC_THEN_FIXTURE_IDENTIFIER_ASC;"
            "UTC_ORDER_MUST_MATCH_EXACTLY"
        ),
        "duplicate_fixture_behavior": "FAIL_CLOSED",
        "temporal_ambiguity_behavior": (
            "FAIL_ON_RELATIVE_ORDER_DISAGREEMENT_OR_SAME_TEAM_SAME_LOCAL_OR_UTC_KICKOFF"
        ),
        "form_semantics": (
            "RECENT_5_STRICTLY_PRIOR;W3_D1_L0;"
            "round(0.10+((points/(n*3))*0.85),3);NO_DEFAULT"
        ),
        "fatigue_semantics": (
            "MOST_RECENT_PRIOR_PER_TARGET_TEAM;"
            "DIFF=(TARGET-HOME_LAST).days-(TARGET-AWAY_LAST).days;"
            "0.30_IF_LT_-2_ELSE_0.10_IF_LT_0_ELSE_0.0;NO_DEFAULT"
        ),
        "elo_semantics": (
            "PREMATCH_OVERALL;INIT_1500_ASSUMPTION;HOME_EXPECTED_PLUS50;"
            "AWAY_EXPECTED_NO_BOOST;DIVISOR_400;W1_D0.5_L0;"
            "K32_LT20_K24_LT50_ELSE16;int(old+delta)"
        ),
        "history_semantic_equivalence": HISTORY_SEMANTIC_EQUIVALENCE,
        "output_semantic_equivalence_authorized": False,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


@dataclasses.dataclass(frozen=True)
class ProspectiveSuccessorFeatureConstructionSpecification:
    schema_version: int
    dataset_name: str
    construction_scope: str
    repository_main_sha: str
    pr78_protocol_sha256: str
    pr78_protocol_size: int
    pr79_assessment_sha256: str
    pr79_assessment_size: int
    source_history_contract: str
    source_local_time_basis: str
    history_selection_rule: str
    history_order_rule: str
    duplicate_fixture_behavior: str
    temporal_ambiguity_behavior: str
    form_semantics: str
    fatigue_semantics: str
    elo_semantics: str
    history_semantic_equivalence: str
    output_semantic_equivalence_authorized: bool
    next_required_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.to_dict() != _spec_payload():
            raise _error("construction specification differs from frozen PR80 contract")
        object.__setattr__(self, "safety", _checked_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "construction_scope": self.construction_scope,
            "repository_main_sha": self.repository_main_sha,
            "pr78_protocol_sha256": self.pr78_protocol_sha256,
            "pr78_protocol_size": self.pr78_protocol_size,
            "pr79_assessment_sha256": self.pr79_assessment_sha256,
            "pr79_assessment_size": self.pr79_assessment_size,
            "source_history_contract": self.source_history_contract,
            "source_local_time_basis": self.source_local_time_basis,
            "history_selection_rule": self.history_selection_rule,
            "history_order_rule": self.history_order_rule,
            "duplicate_fixture_behavior": self.duplicate_fixture_behavior,
            "temporal_ambiguity_behavior": self.temporal_ambiguity_behavior,
            "form_semantics": self.form_semantics,
            "fatigue_semantics": self.fatigue_semantics,
            "elo_semantics": self.elo_semantics,
            "history_semantic_equivalence": self.history_semantic_equivalence,
            "output_semantic_equivalence_authorized": self.output_semantic_equivalence_authorized,
            "next_required_boundary": self.next_required_boundary,
            "safety": dict(self.safety),
        }


def build_prospective_successor_feature_construction_specification(
) -> ProspectiveSuccessorFeatureConstructionSpecification:
    _verify_upstream()
    value = ProspectiveSuccessorFeatureConstructionSpecification(**_spec_payload())
    exact = canonical_prospective_successor_feature_construction_specification_bytes(value)
    if (
        hashlib.sha256(exact).hexdigest() != CONSTRUCTION_SPEC_SHA256
        or len(exact) != CONSTRUCTION_SPEC_SIZE
    ):
        raise _error("PR80 construction specification canonical identity changed")
    return value


def canonical_prospective_successor_feature_construction_specification_bytes(
    value: Any,
) -> bytes:
    if type(value) is not ProspectiveSuccessorFeatureConstructionSpecification:
        raise _error("value must be exact construction specification")
    try:
        rebuilt = dataclasses.replace(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise _error("construction specification failed invariant reconstruction") from exc
    return _canonical(rebuilt.to_dict())


def sha256_prospective_successor_feature_construction_specification(value: Any) -> str:
    return hashlib.sha256(
        canonical_prospective_successor_feature_construction_specification_bytes(value)
    ).hexdigest()


@dataclasses.dataclass(frozen=True)
class ProspectiveMatchEvidence:
    source_namespace: str
    fixture_identifier: str
    source_local_kickoff: datetime.datetime
    kickoff_utc: datetime.datetime
    home_team_identifier: str
    away_team_identifier: str
    home_goals: int
    away_goals: int
    observed_at: datetime.datetime
    evidence_sha256: str
    evidence_reference: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_namespace", _identifier(self.source_namespace, "source_namespace")
        )
        object.__setattr__(
            self,
            "fixture_identifier",
            _identifier(self.fixture_identifier, "fixture_identifier"),
        )
        object.__setattr__(
            self,
            "source_local_kickoff",
            _local(self.source_local_kickoff, "source_local_kickoff"),
        )
        object.__setattr__(self, "kickoff_utc", _utc(self.kickoff_utc, "kickoff_utc"))
        object.__setattr__(
            self,
            "home_team_identifier",
            _identifier(self.home_team_identifier, "home_team_identifier"),
        )
        object.__setattr__(
            self,
            "away_team_identifier",
            _identifier(self.away_team_identifier, "away_team_identifier"),
        )
        if self.home_team_identifier == self.away_team_identifier:
            raise _error("fixture cannot use the same team identity twice")
        if (
            type(self.home_goals) is not int
            or self.home_goals < 0
            or type(self.away_goals) is not int
            or self.away_goals < 0
        ):
            raise _error("goals must be exact non-negative integers")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "observed_at"))
        if self.observed_at <= self.kickoff_utc:
            raise _error("final-result evidence must be observed after fixture kickoff")
        object.__setattr__(
            self, "evidence_sha256", _sha(self.evidence_sha256, "evidence_sha256")
        )
        object.__setattr__(
            self,
            "evidence_reference",
            _text(self.evidence_reference, "evidence_reference"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_namespace": self.source_namespace,
            "fixture_identifier": self.fixture_identifier,
            "source_local_kickoff": self.source_local_kickoff.isoformat(),
            "kickoff_utc": self.kickoff_utc.isoformat().replace("+00:00", "Z"),
            "home_team_identifier": self.home_team_identifier,
            "away_team_identifier": self.away_team_identifier,
            "home_goals": self.home_goals,
            "away_goals": self.away_goals,
            "observed_at": self.observed_at.isoformat().replace("+00:00", "Z"),
            "evidence_sha256": self.evidence_sha256,
            "evidence_reference": self.evidence_reference,
        }


@dataclasses.dataclass(frozen=True)
class ProspectiveTargetFixture:
    source_namespace: str
    fixture_identifier: str
    source_local_kickoff: datetime.datetime
    kickoff_utc: datetime.datetime
    home_team_identifier: str
    away_team_identifier: str
    as_of: datetime.datetime
    evidence_sha256: str
    evidence_reference: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_namespace", _identifier(self.source_namespace, "source_namespace")
        )
        object.__setattr__(
            self,
            "fixture_identifier",
            _identifier(self.fixture_identifier, "fixture_identifier"),
        )
        object.__setattr__(
            self,
            "source_local_kickoff",
            _local(self.source_local_kickoff, "source_local_kickoff"),
        )
        object.__setattr__(self, "kickoff_utc", _utc(self.kickoff_utc, "kickoff_utc"))
        object.__setattr__(
            self,
            "home_team_identifier",
            _identifier(self.home_team_identifier, "home_team_identifier"),
        )
        object.__setattr__(
            self,
            "away_team_identifier",
            _identifier(self.away_team_identifier, "away_team_identifier"),
        )
        if self.home_team_identifier == self.away_team_identifier:
            raise _error("target cannot use the same team identity twice")
        object.__setattr__(self, "as_of", _utc(self.as_of, "as_of"))
        if self.as_of >= self.kickoff_utc:
            raise _error("target as_of must remain strictly pre-kickoff")
        object.__setattr__(
            self, "evidence_sha256", _sha(self.evidence_sha256, "evidence_sha256")
        )
        object.__setattr__(
            self,
            "evidence_reference",
            _text(self.evidence_reference, "evidence_reference"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_namespace": self.source_namespace,
            "fixture_identifier": self.fixture_identifier,
            "source_local_kickoff": self.source_local_kickoff.isoformat(),
            "kickoff_utc": self.kickoff_utc.isoformat().replace("+00:00", "Z"),
            "home_team_identifier": self.home_team_identifier,
            "away_team_identifier": self.away_team_identifier,
            "as_of": self.as_of.isoformat().replace("+00:00", "Z"),
            "evidence_sha256": self.evidence_sha256,
            "evidence_reference": self.evidence_reference,
        }


@dataclasses.dataclass(frozen=True)
class ConstructedSuccessorFeature:
    feature_id: str
    status: ConstructedFeatureStatus
    value: float | int | None
    derivation_fixture_identifiers: tuple[str, ...]
    derivation_evidence_sha256s: tuple[str, ...]
    construction_semantics: str

    def __post_init__(self) -> None:
        if self.feature_id not in FEATURE_ORDER or not isinstance(
            self.status, ConstructedFeatureStatus
        ):
            raise _error("constructed feature identity/status mismatch")
        if self.status is ConstructedFeatureStatus.MISSING_PRIOR_HISTORY:
            if self.value is not None:
                raise _error("missing feature value must be None")
        elif type(self.value) not in (int, float) or not math.isfinite(self.value):
            raise _error("constructed feature value must be finite")

        if type(self.derivation_fixture_identifiers) is not tuple or type(
            self.derivation_evidence_sha256s
        ) is not tuple:
            raise _error("feature lineage must be immutable tuples")
        fixtures = tuple(
            _identifier(item, "derivation_fixture_identifier")
            for item in self.derivation_fixture_identifiers
        )
        hashes = tuple(
            _sha(item, "derivation_evidence_sha256")
            for item in self.derivation_evidence_sha256s
        )
        if fixtures != tuple(sorted(set(fixtures))):
            raise _error("feature fixture lineage must be sorted and unique")
        if self.status is ConstructedFeatureStatus.MISSING_PRIOR_HISTORY and (
            fixtures or hashes
        ):
            raise _error("missing feature cannot claim derivation evidence")
        if len(fixtures) != len(hashes):
            raise _error("feature derivation fixture/hash lineage cardinality mismatch")
        if (
            self.status
            is ConstructedFeatureStatus.CONSTRUCTED_FROM_FROZEN_INITIAL_STATE_ASSUMPTION
            and (fixtures or hashes)
        ):
            raise _error("initial-state-only Elo cannot claim result evidence")
        object.__setattr__(self, "derivation_fixture_identifiers", fixtures)
        object.__setattr__(self, "derivation_evidence_sha256s", hashes)
        object.__setattr__(
            self,
            "construction_semantics",
            _text(self.construction_semantics, "construction_semantics", 512),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "status": self.status.value,
            "value": self.value,
            "derivation_fixture_identifiers": list(self.derivation_fixture_identifiers),
            "derivation_evidence_sha256s": list(self.derivation_evidence_sha256s),
            "construction_semantics": self.construction_semantics,
        }


@dataclasses.dataclass(frozen=True)
class ProspectiveSuccessorFeatureConstructionCandidate:
    schema_version: int
    dataset_name: str
    construction_scope: str
    construction_state: str
    construction_spec_sha256: str
    construction_spec_size: int
    repository_main_sha: str
    target: ProspectiveTargetFixture
    supplied_history_count: int
    eligible_history_count: int
    history_prefix_sha256: str
    history_prefix_size: int
    features: tuple[ConstructedSuccessorFeature, ...]
    all_five_values_available: bool
    all_five_exact_semantic_equivalence: bool
    history_semantic_equivalence: str
    elo_initialization_semantics: str
    next_required_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != SCHEMA_VERSION
            or self.dataset_name != DATASET_NAME
            or self.construction_scope != CONSTRUCTION_SCOPE
            or self.construction_state != CONSTRUCTION_STATE
            or self.repository_main_sha != PR79_MAIN_SHA
            or self.construction_spec_sha256 != CONSTRUCTION_SPEC_SHA256
            or self.construction_spec_size != CONSTRUCTION_SPEC_SIZE
        ):
            raise _error("candidate identity/ancestry mismatch")
        if type(self.target) is not ProspectiveTargetFixture:
            raise _error("candidate target type mismatch")
        object.__setattr__(self, "target", dataclasses.replace(self.target))
        if (
            type(self.supplied_history_count) is not int
            or self.supplied_history_count < 0
            or type(self.eligible_history_count) is not int
            or self.eligible_history_count < 0
            or self.eligible_history_count > self.supplied_history_count
        ):
            raise _error("history counts are invalid")
        object.__setattr__(
            self, "history_prefix_sha256", _sha(self.history_prefix_sha256, "history_prefix_sha256")
        )
        if type(self.history_prefix_size) is not int or self.history_prefix_size <= 0:
            raise _error("history_prefix_size must be positive")
        if (
            type(self.features) is not tuple
            or tuple(item.feature_id for item in self.features) != FEATURE_ORDER
            or any(type(item) is not ConstructedSuccessorFeature for item in self.features)
        ):
            raise _error("candidate must contain exact frozen five-feature order")
        rebuilt_features = tuple(dataclasses.replace(item) for item in self.features)
        object.__setattr__(self, "features", rebuilt_features)
        expected_available = all(
            item.status is not ConstructedFeatureStatus.MISSING_PRIOR_HISTORY
            for item in rebuilt_features
        )
        if (
            type(self.all_five_values_available) is not bool
            or self.all_five_values_available is not expected_available
        ):
            raise _error("all-five availability summary mismatch")
        if (
            type(self.all_five_exact_semantic_equivalence) is not bool
            or self.all_five_exact_semantic_equivalence is not False
        ):
            raise _error("PR80 cannot claim live exact semantic equivalence")
        if (
            self.history_semantic_equivalence != HISTORY_SEMANTIC_EQUIVALENCE
            or self.elo_initialization_semantics != ELO_INITIALIZATION_SEMANTICS
            or self.next_required_boundary != NEXT_REQUIRED_BOUNDARY
        ):
            raise _error("candidate caveat/next-boundary mismatch")
        object.__setattr__(self, "safety", _checked_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "construction_scope": self.construction_scope,
            "construction_state": self.construction_state,
            "construction_spec_sha256": self.construction_spec_sha256,
            "construction_spec_size": self.construction_spec_size,
            "repository_main_sha": self.repository_main_sha,
            "target": self.target.to_dict(),
            "supplied_history_count": self.supplied_history_count,
            "eligible_history_count": self.eligible_history_count,
            "history_prefix_sha256": self.history_prefix_sha256,
            "history_prefix_size": self.history_prefix_size,
            "features": [item.to_dict() for item in self.features],
            "all_five_values_available": self.all_five_values_available,
            "all_five_exact_semantic_equivalence": self.all_five_exact_semantic_equivalence,
            "history_semantic_equivalence": self.history_semantic_equivalence,
            "elo_initialization_semantics": self.elo_initialization_semantics,
            "next_required_boundary": self.next_required_boundary,
            "safety": dict(self.safety),
        }


def _outcome(row: ProspectiveMatchEvidence, team: str) -> str:
    if team == row.home_team_identifier:
        scored, conceded = row.home_goals, row.away_goals
    elif team == row.away_team_identifier:
        scored, conceded = row.away_goals, row.home_goals
    else:
        raise _error("team not in fixture")
    return "W" if scored > conceded else "L" if scored < conceded else "D"


def _feature(
    *,
    feature_id: str,
    status: ConstructedFeatureStatus,
    value: float | int | None,
    rows: Sequence[ProspectiveMatchEvidence],
    semantics: str,
) -> ConstructedSuccessorFeature:
    by_fixture: dict[str, ProspectiveMatchEvidence] = {}
    for row in rows:
        existing = by_fixture.get(row.fixture_identifier)
        if existing is not None and existing != row:
            raise _error("feature lineage repeats a fixture with conflicting evidence")
        by_fixture[row.fixture_identifier] = row
    ordered = tuple(by_fixture[key] for key in sorted(by_fixture))
    return ConstructedSuccessorFeature(
        feature_id=feature_id,
        status=status,
        value=value,
        derivation_fixture_identifiers=tuple(row.fixture_identifier for row in ordered),
        derivation_evidence_sha256s=tuple(row.evidence_sha256 for row in ordered),
        construction_semantics=semantics,
    )


def _missing(feature_id: str, semantics: str) -> ConstructedSuccessorFeature:
    return _feature(
        feature_id=feature_id,
        status=ConstructedFeatureStatus.MISSING_PRIOR_HISTORY,
        value=None,
        rows=(),
        semantics=semantics,
    )


def _form(
    history: Sequence[ProspectiveMatchEvidence],
    team: str,
    feature_id: str,
) -> ConstructedSuccessorFeature:
    recent = sorted(
        (
            row
            for row in history
            if team in (row.home_team_identifier, row.away_team_identifier)
        ),
        key=lambda row: (row.source_local_kickoff, row.fixture_identifier),
        reverse=True,
    )[:5]
    semantics = "PR78_EXACT_RECENT_FIVE_FORM_NO_DEFAULT"
    if not recent:
        return _missing(feature_id, semantics)
    points = sum(
        3 if _outcome(row, team) == "W" else 1 if _outcome(row, team) == "D" else 0
        for row in recent
    )
    value = round(0.10 + ((points / (len(recent) * 3)) * 0.85), 3)
    return _feature(
        feature_id=feature_id,
        status=ConstructedFeatureStatus.CONSTRUCTED_FROM_SUPPLIED_HISTORY,
        value=value,
        rows=recent,
        semantics=semantics,
    )


def _fatigue(
    history: Sequence[ProspectiveMatchEvidence],
    target: ProspectiveTargetFixture,
) -> ConstructedSuccessorFeature:
    home = [
        row
        for row in history
        if target.home_team_identifier
        in (row.home_team_identifier, row.away_team_identifier)
    ]
    away = [
        row
        for row in history
        if target.away_team_identifier
        in (row.home_team_identifier, row.away_team_identifier)
    ]
    semantics = "PR78_EXACT_HOME_RELATIVE_REST_DAY_FATIGUE_NO_DEFAULT"
    if not home or not away:
        return _missing("fatigue", semantics)
    home_last = max(
        home, key=lambda row: (row.source_local_kickoff, row.fixture_identifier)
    )
    away_last = max(
        away, key=lambda row: (row.source_local_kickoff, row.fixture_identifier)
    )
    difference = (
        (target.source_local_kickoff - home_last.source_local_kickoff).days
        - (target.source_local_kickoff - away_last.source_local_kickoff).days
    )
    value = 0.30 if difference < -2 else 0.10 if difference < 0 else 0.0
    return _feature(
        feature_id="fatigue",
        status=ConstructedFeatureStatus.CONSTRUCTED_FROM_SUPPLIED_HISTORY,
        value=value,
        rows=(home_last, away_last),
        semantics=semantics,
    )


def _expected_score(home_rating: int, away_rating: int, *, home_boost: bool) -> float:
    adjusted = home_rating + 50 if home_boost else home_rating
    return 1.0 / (1.0 + 10.0 ** ((away_rating - adjusted) / 400.0))


def _k_factor(matches: int) -> int:
    return 32 if matches < 20 else 24 if matches < 50 else 16


def _elo(
    history: Sequence[ProspectiveMatchEvidence],
    target: ProspectiveTargetFixture,
) -> tuple[ConstructedSuccessorFeature, ConstructedSuccessorFeature]:
    ratings: dict[str, int] = {}
    counts: dict[str, int] = {}

    for row in history:
        home_rating = ratings.get(row.home_team_identifier, 1500)
        away_rating = ratings.get(row.away_team_identifier, 1500)
        home_matches = counts.get(row.home_team_identifier, 0)
        away_matches = counts.get(row.away_team_identifier, 0)

        home_expected = _expected_score(home_rating, away_rating, home_boost=True)
        away_expected = _expected_score(away_rating, home_rating, home_boost=False)
        if row.home_goals > row.away_goals:
            home_score, away_score = 1.0, 0.0
        elif row.home_goals < row.away_goals:
            home_score, away_score = 0.0, 1.0
        else:
            home_score = away_score = 0.5

        ratings[row.home_team_identifier] = int(
            home_rating + _k_factor(home_matches) * (home_score - home_expected)
        )
        ratings[row.away_team_identifier] = int(
            away_rating + _k_factor(away_matches) * (away_score - away_expected)
        )
        counts[row.home_team_identifier] = home_matches + 1
        counts[row.away_team_identifier] = away_matches + 1

    semantics = "PR78_EXACT_1500_PLUS50_K32_24_16_PREMATCH_ELO_REPLAY"

    def make(feature_id: str, team: str) -> ConstructedSuccessorFeature:
        seen = counts.get(team, 0) > 0
        return _feature(
            feature_id=feature_id,
            status=(
                ConstructedFeatureStatus.CONSTRUCTED_FROM_SUPPLIED_HISTORY
                if seen
                else ConstructedFeatureStatus.CONSTRUCTED_FROM_FROZEN_INITIAL_STATE_ASSUMPTION
            ),
            value=ratings.get(team, 1500),
            rows=history if seen else (),
            semantics=semantics,
        )

    return (
        make("home_elo", target.home_team_identifier),
        make("away_elo", target.away_team_identifier),
    )


def _relative_order(
    row_local: datetime.datetime,
    row_utc: datetime.datetime,
    target_local: datetime.datetime,
    target_utc: datetime.datetime,
) -> tuple[int, int]:
    local = -1 if row_local < target_local else 1 if row_local > target_local else 0
    utc = -1 if row_utc < target_utc else 1 if row_utc > target_utc else 0
    return local, utc


def _eligible_history(
    history: Sequence[ProspectiveMatchEvidence],
    target: ProspectiveTargetFixture,
) -> tuple[ProspectiveMatchEvidence, ...]:
    if not isinstance(history, Sequence) or isinstance(
        history, (str, bytes, bytearray, memoryview)
    ):
        raise _error("history must be an ordered sequence")
    rows = tuple(history)
    if any(type(row) is not ProspectiveMatchEvidence for row in rows):
        raise _error("history rows must be exact ProspectiveMatchEvidence")
    rows = tuple(dataclasses.replace(row) for row in rows)

    seen: set[str] = set()
    prior: list[ProspectiveMatchEvidence] = []
    for row in rows:
        if row.source_namespace != target.source_namespace:
            raise _error("history/target source namespace mismatch")
        if row.fixture_identifier == target.fixture_identifier:
            raise _error("target fixture cannot appear in result history")
        if row.fixture_identifier in seen:
            raise _error("duplicate source fixture identifier")
        seen.add(row.fixture_identifier)

        local_relation, utc_relation = _relative_order(
            row.source_local_kickoff,
            row.kickoff_utc,
            target.source_local_kickoff,
            target.kickoff_utc,
        )
        if local_relation != utc_relation:
            raise _error("source-local and UTC chronology disagree relative to target")

        if local_relation == 0 and (
            target.home_team_identifier
            in (row.home_team_identifier, row.away_team_identifier)
            or target.away_team_identifier
            in (row.home_team_identifier, row.away_team_identifier)
        ):
            raise _error("target team has another supplied fixture at target kickoff")

        if local_relation < 0:
            if row.observed_at > target.as_of:
                raise _error(
                    "supplied prior fixture result was not observed by target as_of"
                )
            prior.append(row)

    local_order = tuple(
        sorted(prior, key=lambda row: (row.source_local_kickoff, row.fixture_identifier))
    )
    utc_order = tuple(
        sorted(prior, key=lambda row: (row.kickoff_utc, row.fixture_identifier))
    )
    if tuple(row.fixture_identifier for row in local_order) != tuple(
        row.fixture_identifier for row in utc_order
    ):
        raise _error("source-local and UTC eligible-history ordering disagree")

    local_occupied: set[tuple[datetime.datetime, str]] = set()
    utc_occupied: set[tuple[datetime.datetime, str]] = set()
    for row in local_order:
        for team in (row.home_team_identifier, row.away_team_identifier):
            local_key = (row.source_local_kickoff, team)
            utc_key = (row.kickoff_utc, team)
            if local_key in local_occupied or utc_key in utc_occupied:
                raise _error("same source-scoped team has multiple fixtures at one kickoff")
            local_occupied.add(local_key)
            utc_occupied.add(utc_key)

    return local_order


def _prefix_bytes(history: Sequence[ProspectiveMatchEvidence]) -> bytes:
    return _canonical(
        {
            "source_local_time_basis": SOURCE_LOCAL_TIME_BASIS,
            "elo_initialization_semantics": ELO_INITIALIZATION_SEMANTICS,
            "rows": [row.to_dict() for row in history],
        }
    )


def build_prospective_successor_feature_construction_candidate(
    *,
    history: Sequence[ProspectiveMatchEvidence],
    target: ProspectiveTargetFixture,
) -> ProspectiveSuccessorFeatureConstructionCandidate:
    if type(target) is not ProspectiveTargetFixture:
        raise _error("target must be exact ProspectiveTargetFixture")
    target = dataclasses.replace(target)
    spec = build_prospective_successor_feature_construction_specification()
    spec_bytes = canonical_prospective_successor_feature_construction_specification_bytes(
        spec
    )
    if not isinstance(history, Sequence) or isinstance(
        history, (str, bytes, bytearray, memoryview)
    ):
        raise _error("history must be an ordered sequence")
    supplied_history = tuple(history)
    eligible = _eligible_history(supplied_history, target)
    prefix = _prefix_bytes(eligible)

    home_elo, away_elo = _elo(eligible, target)
    features = (
        home_elo,
        away_elo,
        _form(eligible, target.home_team_identifier, "home_form"),
        _form(eligible, target.away_team_identifier, "away_form"),
        _fatigue(eligible, target),
    )

    return ProspectiveSuccessorFeatureConstructionCandidate(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        construction_scope=CONSTRUCTION_SCOPE,
        construction_state=CONSTRUCTION_STATE,
        construction_spec_sha256=hashlib.sha256(spec_bytes).hexdigest(),
        construction_spec_size=len(spec_bytes),
        repository_main_sha=PR79_MAIN_SHA,
        target=target,
        supplied_history_count=len(supplied_history),
        eligible_history_count=len(eligible),
        history_prefix_sha256=hashlib.sha256(prefix).hexdigest(),
        history_prefix_size=len(prefix),
        features=features,
        all_five_values_available=all(
            item.status is not ConstructedFeatureStatus.MISSING_PRIOR_HISTORY
            for item in features
        ),
        all_five_exact_semantic_equivalence=False,
        history_semantic_equivalence=HISTORY_SEMANTIC_EQUIVALENCE,
        elo_initialization_semantics=ELO_INITIALIZATION_SEMANTICS,
        next_required_boundary=NEXT_REQUIRED_BOUNDARY,
        safety=_safety(),
    )


def canonical_prospective_successor_feature_construction_candidate_bytes(
    value: Any,
) -> bytes:
    if type(value) is not ProspectiveSuccessorFeatureConstructionCandidate:
        raise _error("value must be exact construction candidate")
    try:
        rebuilt = dataclasses.replace(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise _error("construction candidate failed invariant reconstruction") from exc
    return _canonical(rebuilt.to_dict())


def sha256_prospective_successor_feature_construction_candidate(value: Any) -> str:
    return hashlib.sha256(
        canonical_prospective_successor_feature_construction_candidate_bytes(value)
    ).hexdigest()


def revalidate_prospective_successor_feature_construction_candidate(
    *,
    history: Sequence[ProspectiveMatchEvidence],
    target: ProspectiveTargetFixture,
    candidate: Any,
    candidate_bytes: Any,
) -> ProspectiveSuccessorFeatureConstructionCandidate:
    if type(candidate) is not ProspectiveSuccessorFeatureConstructionCandidate:
        raise _error("candidate must be exact ProspectiveSuccessorFeatureConstructionCandidate")
    if type(candidate_bytes) is not bytes:
        raise _error("candidate_bytes must be exact immutable bytes")
    supplied = canonical_prospective_successor_feature_construction_candidate_bytes(
        candidate
    )
    rebuilt = build_prospective_successor_feature_construction_candidate(
        history=history, target=target
    )
    exact = canonical_prospective_successor_feature_construction_candidate_bytes(rebuilt)
    if supplied != exact or candidate_bytes != exact:
        raise _error("candidate differs from exact deterministic reconstruction")
    return rebuilt


__all__ = [
    "CONSTRUCTION_SCOPE",
    "CONSTRUCTION_SPEC_SHA256",
    "CONSTRUCTION_SPEC_SIZE",
    "CONSTRUCTION_STATE",
    "ConstructedFeatureStatus",
    "ConstructedSuccessorFeature",
    "DATASET_NAME",
    "FEATURE_ORDER",
    "HISTORY_SEMANTIC_EQUIVALENCE",
    "NEXT_REQUIRED_BOUNDARY",
    "PR79_MAIN_SHA",
    "ProspectiveMatchEvidence",
    "ProspectiveSuccessorFeatureConstructionCandidate",
    "ProspectiveSuccessorFeatureConstructionError",
    "ProspectiveSuccessorFeatureConstructionSpecification",
    "ProspectiveTargetFixture",
    "SCHEMA_VERSION",
    "build_prospective_successor_feature_construction_candidate",
    "build_prospective_successor_feature_construction_specification",
    "canonical_prospective_successor_feature_construction_candidate_bytes",
    "canonical_prospective_successor_feature_construction_specification_bytes",
    "revalidate_prospective_successor_feature_construction_candidate",
    "sha256_prospective_successor_feature_construction_candidate",
    "sha256_prospective_successor_feature_construction_specification",
]
