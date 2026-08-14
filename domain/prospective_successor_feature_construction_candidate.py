"""Pure candidate construction of the five raw successor inputs.

PR #80 reproduces the form, Elo and fatigue mathematics frozen by PR #78 over
an explicit caller-supplied source-scoped result history.  It does not claim
that any current live source supplies a complete/equivalent corpus and it
authorizes no expected-goals, probability, pricing, selection or betting path.
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
CONSTRUCTION_SPEC_SHA256 = "fd83222e0d0efe04cd312634ee113cc5757565a6c943770dd6d47b0df142af8f"
CONSTRUCTION_SPEC_SIZE = 2118

HISTORY_SEMANTIC_EQUIVALENCE = (
    "UNPROVEN_UNTIL_REVIEWED_SOURCE_ADAPTER_PROVES_HISTORY_COMPLETENESS_IDENTITY_AND_CHRONOLOGY"
)
SOURCE_LOCAL_TIME_BASIS = "SOURCE_LOCAL_NAIVE_DATETIME_REQUIRED_FOR_PR78_PARITY"
FEATURE_ORDER = ("home_elo", "away_elo", "home_form", "away_form", "fatigue")

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
    pass


class ConstructedFeatureStatus(str, enum.Enum):
    CONSTRUCTED_FROM_SUPPLIED_HISTORY = "CONSTRUCTED_FROM_SUPPLIED_HISTORY"
    MISSING_PRIOR_HISTORY = "MISSING_PRIOR_HISTORY"


def _error(message: str) -> ProspectiveSuccessorFeatureConstructionError:
    return ProspectiveSuccessorFeatureConstructionError(message)


def _text(value: Any, label: str, maximum: int = 1024) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > maximum:
        raise _error(f"{label} must be exact non-empty trimmed text")
    return value


def _identifier(value: Any, label: str) -> str:
    value = _text(value, label, 256)
    if _ID_RE.fullmatch(value) is None:
        raise _error(f"{label} has unsupported identity characters")
    return value


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
        raise _error("canonical serialization failed") from exc


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
    form_semantics_source: str
    fatigue_semantics_source: str
    elo_semantics_source: str
    history_semantic_equivalence: str
    output_semantic_equivalence_authorized: bool
    next_required_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.to_dict(include_safety=False) != _spec_payload():
            raise _error("construction specification differs from frozen PR80 contract")
        object.__setattr__(self, "safety", _checked_safety(self.safety))

    def to_dict(self, *, include_safety: bool = True) -> dict[str, Any]:
        payload = {
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
            "form_semantics_source": self.form_semantics_source,
            "fatigue_semantics_source": self.fatigue_semantics_source,
            "elo_semantics_source": self.elo_semantics_source,
            "history_semantic_equivalence": self.history_semantic_equivalence,
            "output_semantic_equivalence_authorized": self.output_semantic_equivalence_authorized,
            "next_required_boundary": self.next_required_boundary,
        }
        if include_safety:
            payload["safety"] = dict(self.safety)
        return payload


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
            "CALLER_SUPPLIED_SOURCE_SCOPED_FINAL_RESULT_EVIDENCE_ROWS;"
            "NO_CURRENT_LIVE_SOURCE_ADAPTER_AUTHORIZED"
        ),
        "source_local_time_basis": SOURCE_LOCAL_TIME_BASIS,
        "history_selection_rule": (
            "USE_ONLY_FIXTURES_STRICTLY_PRIOR_IN_SOURCE_LOCAL_AND_UTC;"
            "RESULT_EVIDENCE_MUST_BE_OBSERVED_BY_TARGET_AS_OF"
        ),
        "history_order_rule": (
            "SOURCE_LOCAL_KICKOFF_ASC_THEN_FIXTURE_IDENTIFIER_ASC;UTC_ORDER_MUST_AGREE"
        ),
        "duplicate_fixture_behavior": "FAIL_CLOSED",
        "temporal_ambiguity_behavior": (
            "FAIL_CLOSED_ON_LOCAL_UTC_ORDER_DISAGREEMENT_OR_SAME_TEAM_SAME_KICKOFF"
        ),
        "form_semantics_source": "PR78_FROZEN_HISTORICAL_FORM_SEMANTICS",
        "fatigue_semantics_source": "PR78_FROZEN_HISTORICAL_FATIGUE_SEMANTICS",
        "elo_semantics_source": "PR78_FROZEN_HISTORICAL_ELO_SEMANTICS",
        "history_semantic_equivalence": HISTORY_SEMANTIC_EQUIVALENCE,
        "output_semantic_equivalence_authorized": False,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
    }


def build_prospective_successor_feature_construction_specification(
) -> ProspectiveSuccessorFeatureConstructionSpecification:
    _verify_upstream()
    value = ProspectiveSuccessorFeatureConstructionSpecification(
        **_spec_payload(),
        safety=_safety(),
    )
    exact = canonical_prospective_successor_feature_construction_specification_bytes(value)
    if hashlib.sha256(exact).hexdigest() != CONSTRUCTION_SPEC_SHA256 or len(exact) != CONSTRUCTION_SPEC_SIZE:
        raise _error("PR80 construction specification canonical identity changed")
    return value


def canonical_prospective_successor_feature_construction_specification_bytes(
    value: Any,
) -> bytes:
    if type(value) is not ProspectiveSuccessorFeatureConstructionSpecification:
        raise _error("value must be exact construction specification")
    try:
        value = dataclasses.replace(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise _error("construction specification failed invariant reconstruction") from exc
    return _canonical(value.to_dict())


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
        object.__setattr__(self, "source_namespace", _identifier(self.source_namespace, "source_namespace"))
        object.__setattr__(self, "fixture_identifier", _identifier(self.fixture_identifier, "fixture_identifier"))
        object.__setattr__(self, "source_local_kickoff", _local(self.source_local_kickoff, "source_local_kickoff"))
        object.__setattr__(self, "kickoff_utc", _utc(self.kickoff_utc, "kickoff_utc"))
        object.__setattr__(self, "home_team_identifier", _identifier(self.home_team_identifier, "home_team_identifier"))
        object.__setattr__(self, "away_team_identifier", _identifier(self.away_team_identifier, "away_team_identifier"))
        if self.home_team_identifier == self.away_team_identifier:
            raise _error("fixture cannot use the same team identity twice")
        if type(self.home_goals) is not int or self.home_goals < 0 or type(self.away_goals) is not int or self.away_goals < 0:
            raise _error("goals must be exact non-negative integers")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "observed_at"))
        if self.observed_at <= self.kickoff_utc:
            raise _error("final-result evidence must be observed after fixture kickoff")
        object.__setattr__(self, "evidence_sha256", _sha(self.evidence_sha256, "evidence_sha256"))
        object.__setattr__(self, "evidence_reference", _text(self.evidence_reference, "evidence_reference"))

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
        object.__setattr__(self, "source_namespace", _identifier(self.source_namespace, "source_namespace"))
        object.__setattr__(self, "fixture_identifier", _identifier(self.fixture_identifier, "fixture_identifier"))
        object.__setattr__(self, "source_local_kickoff", _local(self.source_local_kickoff, "source_local_kickoff"))
        object.__setattr__(self, "kickoff_utc", _utc(self.kickoff_utc, "kickoff_utc"))
        object.__setattr__(self, "home_team_identifier", _identifier(self.home_team_identifier, "home_team_identifier"))
        object.__setattr__(self, "away_team_identifier", _identifier(self.away_team_identifier, "away_team_identifier"))
        if self.home_team_identifier == self.away_team_identifier:
            raise _error("target cannot use the same team identity twice")
        object.__setattr__(self, "as_of", _utc(self.as_of, "as_of"))
        if self.as_of >= self.kickoff_utc:
            raise _error("target as_of must remain strictly pre-kickoff")
        object.__setattr__(self, "evidence_sha256", _sha(self.evidence_sha256, "evidence_sha256"))
        object.__setattr__(self, "evidence_reference", _text(self.evidence_reference, "evidence_reference"))

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
    direct_fixture_identifiers: tuple[str, ...]
    direct_evidence_sha256s: tuple[str, ...]
    construction_semantics: str

    def __post_init__(self) -> None:
        if self.feature_id not in FEATURE_ORDER or not isinstance(self.status, ConstructedFeatureStatus):
            raise _error("constructed feature identity/status mismatch")
        if self.status is ConstructedFeatureStatus.CONSTRUCTED_FROM_SUPPLIED_HISTORY:
            if type(self.value) not in (int, float) or not math.isfinite(self.value):
                raise _error("constructed feature value must be finite")
        elif self.value is not None:
            raise _error("missing feature value must be None")
        if type(self.direct_fixture_identifiers) is not tuple or type(self.direct_evidence_sha256s) is not tuple:
            raise _error("feature lineage must be immutable tuples")
        fixtures = tuple(_identifier(item, "direct_fixture_identifier") for item in self.direct_fixture_identifiers)
        hashes = tuple(_sha(item, "direct_evidence_sha256") for item in self.direct_evidence_sha256s)
        if fixtures != tuple(sorted(set(fixtures))) or hashes != tuple(sorted(set(hashes))):
            raise _error("feature lineage must be sorted and unique")
        if self.status is ConstructedFeatureStatus.MISSING_PRIOR_HISTORY and (fixtures or hashes):
            raise _error("missing feature cannot claim direct evidence")
        object.__setattr__(self, "direct_fixture_identifiers", fixtures)
        object.__setattr__(self, "direct_evidence_sha256s", hashes)
        object.__setattr__(self, "construction_semantics", _text(self.construction_semantics, "construction_semantics", 256))

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "status": self.status.value,
            "value": self.value,
            "direct_fixture_identifiers": list(self.direct_fixture_identifiers),
            "direct_evidence_sha256s": list(self.direct_evidence_sha256s),
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
    all_five_constructed_from_supplied_history: bool
    all_five_exact_semantic_equivalence: bool
    history_semantic_equivalence: str
    elo_initialization_semantics: str
    next_required_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if (
            self.schema_version != SCHEMA_VERSION
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
        if any(type(value) is not int or value < 0 for value in (self.supplied_history_count, self.eligible_history_count)):
            raise _error("history counts must be non-negative exact integers")
        if self.eligible_history_count > self.supplied_history_count:
            raise _error("eligible history cannot exceed supplied history")
        object.__setattr__(self, "history_prefix_sha256", _sha(self.history_prefix_sha256, "history_prefix_sha256"))
        if type(self.history_prefix_size) is not int or self.history_prefix_size <= 0:
            raise _error("history_prefix_size must be positive")
        if type(self.features) is not tuple or tuple(item.feature_id for item in self.features) != FEATURE_ORDER:
            raise _error("candidate must contain exact frozen five-feature order")
        object.__setattr__(self, "features", tuple(dataclasses.replace(item) for item in self.features))
        expected_all = all(item.status is ConstructedFeatureStatus.CONSTRUCTED_FROM_SUPPLIED_HISTORY for item in self.features)
        if type(self.all_five_constructed_from_supplied_history) is not bool or self.all_five_constructed_from_supplied_history is not expected_all:
            raise _error("all-five construction summary mismatch")
        if type(self.all_five_exact_semantic_equivalence) is not bool or self.all_five_exact_semantic_equivalence:
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
            "all_five_constructed_from_supplied_history": self.all_five_constructed_from_supplied_history,
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
    feature_id: str,
    value: float | int | None,
    fixtures: Sequence[str],
    hashes: Sequence[str],
    semantics: str,
) -> ConstructedSuccessorFeature:
    return ConstructedSuccessorFeature(
        feature_id=feature_id,
        status=(
            ConstructedFeatureStatus.CONSTRUCTED_FROM_SUPPLIED_HISTORY
            if value is not None
            else ConstructedFeatureStatus.MISSING_PRIOR_HISTORY
        ),
        value=value,
        direct_fixture_identifiers=tuple(sorted(set(fixtures))),
        direct_evidence_sha256s=tuple(sorted(set(hashes))),
        construction_semantics=semantics,
    )


def _form(history: Sequence[ProspectiveMatchEvidence], team: str, feature_id: str) -> ConstructedSuccessorFeature:
    recent = sorted(
        (row for row in history if team in (row.home_team_identifier, row.away_team_identifier)),
        key=lambda row: (row.source_local_kickoff, row.fixture_identifier),
        reverse=True,
    )[:5]
    if not recent:
        return _feature(feature_id, None, (), (), "PR78_EXACT_RECENT_FIVE_FORM_NO_DEFAULT")
    points = sum(3 if _outcome(row, team) == "W" else 1 if _outcome(row, team) == "D" else 0 for row in recent)
    value = round(0.10 + ((points / (len(recent) * 3)) * 0.85), 3)
    return _feature(
        feature_id,
        value,
        [row.fixture_identifier for row in recent],
        [row.evidence_sha256 for row in recent],
        "PR78_EXACT_RECENT_FIVE_FORM_NO_DEFAULT",
    )


def _fatigue(history: Sequence[ProspectiveMatchEvidence], target: ProspectiveTargetFixture) -> ConstructedSuccessorFeature:
    home = [row for row in history if target.home_team_identifier in (row.home_team_identifier, row.away_team_identifier)]
    away = [row for row in history if target.away_team_identifier in (row.home_team_identifier, row.away_team_identifier)]
    if not home or not away:
        return _feature("fatigue", None, (), (), "PR78_EXACT_HOME_RELATIVE_REST_DAY_FATIGUE_NO_DEFAULT")
    home_last = max(home, key=lambda row: (row.source_local_kickoff, row.fixture_identifier))
    away_last = max(away, key=lambda row: (row.source_local_kickoff, row.fixture_identifier))
    difference = (
        (target.source_local_kickoff - home_last.source_local_kickoff).days
        - (target.source_local_kickoff - away_last.source_local_kickoff).days
    )
    value = 0.30 if difference < -2 else 0.10 if difference < 0 else 0.0
    return _feature(
        "fatigue",
        value,
        (home_last.fixture_identifier, away_last.fixture_identifier),
        (home_last.evidence_sha256, away_last.evidence_sha256),
        "PR78_EXACT_HOME_RELATIVE_REST_DAY_FATIGUE_NO_DEFAULT",
    )


def _expected_score(home_rating: int, away_rating: int, home_boost: bool) -> float:
    adjusted = home_rating + 50 if home_boost else home_rating
    return 1.0 / (1.0 + 10.0 ** ((away_rating - adjusted) / 400.0))


def _k(matches: int) -> int:
    return 32 if matches < 20 else 24 if matches < 50 else 16


def _elo(
    history: Sequence[ProspectiveMatchEvidence],
    target: ProspectiveTargetFixture,
    prefix_sha: str,
) -> tuple[ConstructedSuccessorFeature, ConstructedSuccessorFeature]:
    ratings: dict[str, int] = {}
    counts: dict[str, int] = {}
    for row in history:
        hr = ratings.get(row.home_team_identifier, 1500)
        ar = ratings.get(row.away_team_identifier, 1500)
        hc = counts.get(row.home_team_identifier, 0)
        ac = counts.get(row.away_team_identifier, 0)
        eh = _expected_score(hr, ar, True)
        ea = _expected_score(ar, hr, False)
        if row.home_goals > row.away_goals:
            ah, aa = 1.0, 0.0
        elif row.home_goals < row.away_goals:
            ah, aa = 0.0, 1.0
        else:
            ah = aa = 0.5
        ratings[row.home_team_identifier] = int(hr + _k(hc) * (ah - eh))
        ratings[row.away_team_identifier] = int(ar + _k(ac) * (aa - ea))
        counts[row.home_team_identifier] = hc + 1
        counts[row.away_team_identifier] = ac + 1
    semantics = "PR78_EXACT_1500_PLUS50_K32_24_16_PREMATCH_ELO_REPLAY"
    return (
        _feature("home_elo", ratings.get(target.home_team_identifier, 1500), (), (prefix_sha,), semantics),
        _feature("away_elo", ratings.get(target.away_team_identifier, 1500), (), (prefix_sha,), semantics),
    )


def _eligible_history(
    history: Sequence[ProspectiveMatchEvidence],
    target: ProspectiveTargetFixture,
) -> tuple[ProspectiveMatchEvidence, ...]:
    if not isinstance(history, Sequence) or isinstance(history, (str, bytes, bytearray, memoryview)):
        raise _error("history must be an ordered sequence")
    rows = tuple(history)
    if any(type(row) is not ProspectiveMatchEvidence for row in rows):
        raise _error("history rows must be exact ProspectiveMatchEvidence")
    rows = tuple(dataclasses.replace(row) for row in rows)
    seen: set[str] = set()
    for row in rows:
        if row.source_namespace != target.source_namespace:
            raise _error("history/target source namespace mismatch")
        if row.fixture_identifier == target.fixture_identifier:
            raise _error("target fixture cannot appear in result history")
        if row.fixture_identifier in seen:
            raise _error("duplicate source fixture identifier")
        seen.add(row.fixture_identifier)
        if (row.source_local_kickoff < target.source_local_kickoff) != (row.kickoff_utc < target.kickoff_utc):
            raise _error("source-local and UTC chronology disagree relative to target")
        if (
            (row.source_local_kickoff == target.source_local_kickoff or row.kickoff_utc == target.kickoff_utc)
            and (
                target.home_team_identifier in (row.home_team_identifier, row.away_team_identifier)
                or target.away_team_identifier in (row.home_team_identifier, row.away_team_identifier)
            )
        ):
            raise _error("target team has another supplied fixture at target kickoff")
    eligible_unsorted = tuple(
        row
        for row in rows
        if row.source_local_kickoff < target.source_local_kickoff
        and row.kickoff_utc < target.kickoff_utc
        and row.observed_at <= target.as_of
    )
    local_order = tuple(sorted(eligible_unsorted, key=lambda row: (row.source_local_kickoff, row.fixture_identifier)))
    utc_order = tuple(sorted(eligible_unsorted, key=lambda row: (row.kickoff_utc, row.fixture_identifier)))
    if tuple(row.fixture_identifier for row in local_order) != tuple(row.fixture_identifier for row in utc_order):
        raise _error("source-local and UTC eligible-history ordering disagree")
    occupied: set[tuple[datetime.datetime, str]] = set()
    for row in local_order:
        for team in (row.home_team_identifier, row.away_team_identifier):
            key = (row.source_local_kickoff, team)
            if key in occupied:
                raise _error("same source-scoped team has multiple fixtures at one kickoff")
            occupied.add(key)
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
    spec_bytes = canonical_prospective_successor_feature_construction_specification_bytes(spec)
    eligible = _eligible_history(history, target)
    prefix = _prefix_bytes(eligible)
    prefix_sha = hashlib.sha256(prefix).hexdigest()
    home_elo, away_elo = _elo(eligible, target, prefix_sha)
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
        supplied_history_count=len(history),
        eligible_history_count=len(eligible),
        history_prefix_sha256=prefix_sha,
        history_prefix_size=len(prefix),
        features=features,
        all_five_constructed_from_supplied_history=all(
            item.status is ConstructedFeatureStatus.CONSTRUCTED_FROM_SUPPLIED_HISTORY
            for item in features
        ),
        all_five_exact_semantic_equivalence=False,
        history_semantic_equivalence=HISTORY_SEMANTIC_EQUIVALENCE,
        elo_initialization_semantics=ELO_INITIALIZATION_SEMANTICS,
        next_required_boundary=NEXT_REQUIRED_BOUNDARY,
        safety=_safety(),
    )


def canonical_prospective_successor_feature_construction_candidate_bytes(value: Any) -> bytes:
    if type(value) is not ProspectiveSuccessorFeatureConstructionCandidate:
        raise _error("value must be exact construction candidate")
    try:
        value = dataclasses.replace(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise _error("construction candidate failed invariant reconstruction") from exc
    return _canonical(value.to_dict())


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
    if type(candidate) is not ProspectiveSuccessorFeatureConstructionCandidate or type(candidate_bytes) is not bytes:
        raise _error("candidate/candidate_bytes type mismatch")
    supplied = canonical_prospective_successor_feature_construction_candidate_bytes(candidate)
    rebuilt = build_prospective_successor_feature_construction_candidate(history=history, target=target)
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
