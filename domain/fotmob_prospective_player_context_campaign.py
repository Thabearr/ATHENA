"""Fail-closed receipt and neutral schema discovery for PR #192.

This module is deliberately offline. Network acquisition and filesystem
publication live in the campaign runner; the domain boundary only resolves an
exact target, inventories review-candidate paths from PR #53, and seals the
evidence-file receipt.
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import re
import types
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

from domain.fotmob_fixture_candidate_review import sha256_fotmob_fixture_candidate
from domain.fotmob_fixture_candidates import FotMobFixtureCandidate
from domain.fotmob_reviewed_match_details_structure import (
    FotMobReviewedMatchDetailsStructureAssessment,
    JsonValueKind,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-prospective-player-context-campaign-v1"
CAMPAIGN_SCOPE = "EXACT_PROSPECTIVE_FOTMOB_PLAYER_CONTEXT_EVIDENCE_CAPTURE_ONLY"
REPORT_DATASET_NAME = "athena-fotmob-player-context-review-candidates-v1"
TARGET_REQUEST_DATE = "20260822"
EXPECTED_HOME_TEAM = "Nottingham Forest"
EXPECTED_AWAY_TEAM = "Leeds United"
EXPECTED_KICKOFF = "2026-08-22T14:00:00Z"
REQUEST_TIMEZONE = "UTC"
REQUEST_CCODE3 = "NGA"

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")
_CANDIDATE_TOKENS = (
    "bench",
    "formation",
    "home",
    "injur",
    "lineup",
    "naplayer",
    "player",
    "position",
    "reason",
    "squad",
    "starter",
    "suspension",
    "team",
    "unavailable",
)
_SAFETY_KEYS = frozenset(
    {
        "array_semantics_authorized",
        "automatic_review_authorized",
        "bet_authorized",
        "intelligence_fact_authorized",
        "model_feature_authorized",
        "pricing_authorized",
        "probability_adjustment_authorized",
        "probability_inference_authorized",
        "production_approval_authorized",
        "selection_authorized",
        "source_wide_qualification_authorized",
        "team_strength_feature_authorized",
    }
)


class FotMobProspectivePlayerContextCampaignError(ValueError):
    """Raised when campaign evidence or receipt state fails closed."""


class CampaignResult(str, enum.Enum):
    SUCCESS_PROSPECTIVE_PLAYER_CONTEXT_EVIDENCE_CAPTURED = (
        "SUCCESS_PROSPECTIVE_PLAYER_CONTEXT_EVIDENCE_CAPTURED"
    )
    TARGET_FIXTURE_NOT_EXACTLY_RESOLVED = "TARGET_FIXTURE_NOT_EXACTLY_RESOLVED"
    FIXTURE_REVIEW_NOT_GRANTED = "FIXTURE_REVIEW_NOT_GRANTED"
    TARGET_NO_LONGER_PROSPECTIVE = "TARGET_NO_LONGER_PROSPECTIVE"
    FIXTURE_CATALOG_ACQUISITION_FAILED = "FIXTURE_CATALOG_ACQUISITION_FAILED"
    FIXTURE_SCHEMA_ASSESSMENT_FAILED = "FIXTURE_SCHEMA_ASSESSMENT_FAILED"
    FIXTURE_CANDIDATE_EXTRACTION_FAILED = "FIXTURE_CANDIDATE_EXTRACTION_FAILED"
    MATCH_DETAILS_ACQUISITION_FAILED = "MATCH_DETAILS_ACQUISITION_FAILED"
    MATCH_DETAILS_NOT_JSON = "MATCH_DETAILS_NOT_JSON"
    PERSISTED_EVIDENCE_VERIFICATION_FAILED = (
        "PERSISTED_EVIDENCE_VERIFICATION_FAILED"
    )
    STRUCTURE_ASSESSMENT_FAILED = "STRUCTURE_ASSESSMENT_FAILED"
    NO_PLAYER_CONTEXT_CANDIDATE_STRUCTURE_OBSERVED = (
        "NO_PLAYER_CONTEXT_CANDIDATE_STRUCTURE_OBSERVED"
    )
    CAMPAIGN_ARTIFACT_INCOMPLETE = "CAMPAIGN_ARTIFACT_INCOMPLETE"


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FotMobProspectivePlayerContextCampaignError(f"{label} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise FotMobProspectivePlayerContextCampaignError(
            f"{label} must be timezone-aware"
        )
    return value.astimezone(datetime.timezone.utc)


def serialize_utc(value: datetime.datetime) -> str:
    return _utc(value, "timestamp").isoformat().replace("+00:00", "Z")


def parse_utc(value: Any, label: str) -> datetime.datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise FotMobProspectivePlayerContextCampaignError(
            f"{label} must be canonical UTC text"
        )
    try:
        parsed = datetime.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise FotMobProspectivePlayerContextCampaignError(
            f"{label} must be canonical UTC text"
        ) from exc
    if serialize_utc(parsed) != value:
        raise FotMobProspectivePlayerContextCampaignError(
            f"{label} must be canonical UTC text"
        )
    return parsed


def _sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise FotMobProspectivePlayerContextCampaignError(
            f"{label} must be lowercase SHA-256"
        )
    return value


def _exact_string(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str or value != value.strip() or (not value and not allow_empty):
        raise FotMobProspectivePlayerContextCampaignError(f"{label} is invalid")
    return value


def safety_flags() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobProspectivePlayerContextCampaignError("safety keys mismatch")
    if any(type(item) is not bool or item is not False for item in value.values()):
        raise FotMobProspectivePlayerContextCampaignError(
            "every campaign authority must be exact False"
        )
    return safety_flags()


def canonical_json_bytes(value: Any) -> bytes:
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
        raise FotMobProspectivePlayerContextCampaignError(
            "canonical serialization failed"
        ) from exc


@dataclasses.dataclass(frozen=True)
class EvidenceFile:
    relative_path: str
    sha256: str
    byte_size: int

    def __post_init__(self) -> None:
        path = PurePosixPath(_exact_string(self.relative_path, "relative_path"))
        if path.is_absolute() or ".." in path.parts or str(path) != self.relative_path:
            raise FotMobProspectivePlayerContextCampaignError(
                "evidence relative_path must be normalized and relative"
            )
        object.__setattr__(self, "sha256", _sha256(self.sha256, "sha256"))
        if type(self.byte_size) is not int or self.byte_size <= 0:
            raise FotMobProspectivePlayerContextCampaignError(
                "evidence byte_size must be positive"
            )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class PlayerContextReviewCandidate:
    json_pointer_pattern: str
    json_kinds: tuple[str, ...]
    occurrence_count: int
    parent_pointer: str
    neutral_classification: str = "PLAYER_CONTEXT_REVIEW_CANDIDATE"
    array_cardinality: int | None = None

    def __post_init__(self) -> None:
        pointer = _exact_string(
            self.json_pointer_pattern, "json_pointer_pattern", allow_empty=True
        )
        if type(self.json_kinds) is not tuple or not self.json_kinds:
            raise FotMobProspectivePlayerContextCampaignError("json_kinds invalid")
        if self.json_kinds != tuple(sorted(set(self.json_kinds))):
            raise FotMobProspectivePlayerContextCampaignError(
                "json_kinds must be sorted and unique"
            )
        if type(self.occurrence_count) is not int or self.occurrence_count <= 0:
            raise FotMobProspectivePlayerContextCampaignError(
                "occurrence_count must be positive"
            )
        if self.neutral_classification != "PLAYER_CONTEXT_REVIEW_CANDIDATE":
            raise FotMobProspectivePlayerContextCampaignError(
                "schema discovery cannot authorize semantics"
            )
        expected_parent = pointer.rsplit("/", 1)[0] if "/" in pointer else ""
        if self.parent_pointer != expected_parent:
            raise FotMobProspectivePlayerContextCampaignError("parent_pointer mismatch")
        if self.array_cardinality is not None and (
            type(self.array_cardinality) is not int or self.array_cardinality < 0
        ):
            raise FotMobProspectivePlayerContextCampaignError(
                "array_cardinality must be nonnegative or None"
            )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def resolve_exact_target_candidate(
    candidates: Sequence[FotMobFixtureCandidate],
    *,
    request_date: str = TARGET_REQUEST_DATE,
    expected_home_team: str = EXPECTED_HOME_TEAM,
    expected_away_team: str = EXPECTED_AWAY_TEAM,
    expected_kickoff: str = EXPECTED_KICKOFF,
) -> FotMobFixtureCandidate:
    """Resolve exactly one source candidate without normalization or fuzzy matching."""

    if request_date != TARGET_REQUEST_DATE:
        raise FotMobProspectivePlayerContextCampaignError(
            "target request date differs from the frozen campaign"
        )
    kickoff = parse_utc(expected_kickoff, "expected_kickoff")
    matches = tuple(
        item
        for item in candidates
        if type(item) is FotMobFixtureCandidate
        and item.source_request_date == request_date
        and item.home_name == expected_home_team
        and item.away_name == expected_away_team
        and item.kickoff_utc == kickoff
    )
    if len(matches) != 1:
        raise FotMobProspectivePlayerContextCampaignError(
            "target fixture was not resolved by one exact source candidate"
        )
    return matches[0]


def build_player_context_review_candidate_report(
    assessment: Any,
    *,
    observed_at: datetime.datetime,
) -> dict[str, Any]:
    """Build a neutral, deterministic report solely from an exact PR #53 inventory."""

    if type(assessment) is not FotMobReviewedMatchDetailsStructureAssessment:
        raise FotMobProspectivePlayerContextCampaignError(
            "assessment must be exact PR #53 structure assessment"
        )
    observed = _utc(observed_at, "observed_at")
    records: list[PlayerContextReviewCandidate] = []
    for field in assessment.fields:
        lowered = field.json_pointer.casefold()
        if not any(token in lowered for token in _CANDIDATE_TOKENS):
            continue
        kinds = tuple(sorted(item.value for item in field.kinds))
        records.append(
            PlayerContextReviewCandidate(
                json_pointer_pattern=field.json_pointer,
                json_kinds=kinds,
                occurrence_count=field.occurrences,
                parent_pointer=(
                    field.json_pointer.rsplit("/", 1)[0]
                    if "/" in field.json_pointer
                    else ""
                ),
                # PR #53 inventories kinds/occurrences, not per-array lengths.
                array_cardinality=None,
            )
        )
    ordered = tuple(sorted(records, key=lambda item: item.json_pointer_pattern))
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": REPORT_DATASET_NAME,
        "scope": "SCHEMA_DISCOVERY_ONLY_NO_FOOTBALL_SEMANTICS",
        "fixture_identifier": assessment.fixture_identifier,
        "source_match_id": assessment.source_match_id,
        "observed_at": serialize_utc(observed),
        "raw_sha256": assessment.raw_sha256,
        "structure_assessment_sha256": hashlib.sha256(
            canonical_json_bytes(assessment.to_dict())
        ).hexdigest(),
        "candidate_count": len(ordered),
        "candidates": [item.to_dict() for item in ordered],
        "array_cardinality_limit": (
            "PR53_DOES_NOT_RETAIN_PER_ARRAY_CARDINALITY_NO_VALUE_INFERRED"
        ),
        "safety": dict(safety_flags()),
    }


@dataclasses.dataclass(frozen=True)
class FotMobProspectivePlayerContextCampaignReceipt:
    repository: str
    base_sha: str
    repository_head_sha: str
    workflow_name: str
    workflow_run_id: int
    workflow_run_attempt: int
    github_actor: str
    started_at: datetime.datetime
    completed_at: datetime.datetime
    campaign_result: CampaignResult
    resolved_fixture_identifier: str | None
    resolved_source_match_id: str | None
    resolved_home_team: str | None
    resolved_away_team: str | None
    resolved_kickoff: datetime.datetime | None
    fixture_candidate_sha256: str | None
    fixture_raw_sha256: str | None
    fixture_raw_size: int | None
    fixture_manifest_sha256: str | None
    fixture_schema_assessment_sha256: str | None
    fixture_candidate_bundle_sha256: str | None
    fixture_review_ledger_sha256: str | None
    fixture_catalog_sha256: str | None
    fixture_catalog_manifest_sha256: str | None
    fixture_admission_sha256: str | None
    fixture_bootstrap_sha256: str | None
    fixture_bootstrap_receipt_sha256: str | None
    match_details_raw_sha256: str | None
    match_details_raw_size: int | None
    match_details_manifest_sha256: str | None
    persisted_evidence_receipt_sha256: str | None
    structure_assessment_sha256: str | None
    player_context_report_sha256: str | None
    files: tuple[EvidenceFile, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.repository != "Thabearr/ATHENA":
            raise FotMobProspectivePlayerContextCampaignError("repository mismatch")
        if type(self.base_sha) is not str or _GIT_SHA_RE.fullmatch(self.base_sha) is None:
            raise FotMobProspectivePlayerContextCampaignError("base_sha invalid")
        if (
            type(self.repository_head_sha) is not str
            or _GIT_SHA_RE.fullmatch(self.repository_head_sha) is None
        ):
            raise FotMobProspectivePlayerContextCampaignError(
                "repository_head_sha invalid"
            )
        _exact_string(self.workflow_name, "workflow_name")
        _exact_string(self.github_actor, "github_actor")
        if type(self.workflow_run_id) is not int or self.workflow_run_id <= 0:
            raise FotMobProspectivePlayerContextCampaignError("workflow_run_id invalid")
        if type(self.workflow_run_attempt) is not int or self.workflow_run_attempt <= 0:
            raise FotMobProspectivePlayerContextCampaignError(
                "workflow_run_attempt invalid"
            )
        started = _utc(self.started_at, "started_at")
        completed = _utc(self.completed_at, "completed_at")
        if completed < started:
            raise FotMobProspectivePlayerContextCampaignError(
                "completed_at predates started_at"
            )
        if not isinstance(self.campaign_result, CampaignResult):
            raise FotMobProspectivePlayerContextCampaignError("campaign_result invalid")
        if type(self.files) is not tuple or any(type(item) is not EvidenceFile for item in self.files):
            raise FotMobProspectivePlayerContextCampaignError("files invalid")
        if self.files != tuple(sorted(self.files, key=lambda item: item.relative_path)):
            raise FotMobProspectivePlayerContextCampaignError("files must be sorted")
        if len({item.relative_path for item in self.files}) != len(self.files):
            raise FotMobProspectivePlayerContextCampaignError("duplicate evidence file")
        for label in (
            "fixture_candidate_sha256",
            "fixture_raw_sha256",
            "fixture_manifest_sha256",
            "fixture_schema_assessment_sha256",
            "fixture_candidate_bundle_sha256",
            "fixture_review_ledger_sha256",
            "fixture_catalog_sha256",
            "fixture_catalog_manifest_sha256",
            "fixture_admission_sha256",
            "fixture_bootstrap_sha256",
            "fixture_bootstrap_receipt_sha256",
            "match_details_raw_sha256",
            "match_details_manifest_sha256",
            "persisted_evidence_receipt_sha256",
            "structure_assessment_sha256",
            "player_context_report_sha256",
        ):
            value = getattr(self, label)
            if value is not None:
                _sha256(value, label)
        for label in ("fixture_raw_size", "match_details_raw_size"):
            value = getattr(self, label)
            if value is not None and (type(value) is not int or value <= 0):
                raise FotMobProspectivePlayerContextCampaignError(f"{label} invalid")
        if self.resolved_kickoff is not None:
            object.__setattr__(
                self, "resolved_kickoff", _utc(self.resolved_kickoff, "resolved_kickoff")
            )
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "completed_at", completed)
        object.__setattr__(self, "safety", _validate_safety(self.safety))
        self._validate_stage_invariants()

    def _validate_stage_invariants(self) -> None:
        fixture_capture = (
            self.fixture_raw_sha256,
            self.fixture_raw_size,
            self.fixture_manifest_sha256,
        )
        if any(item is not None for item in fixture_capture) and not all(
            item is not None for item in fixture_capture
        ):
            raise FotMobProspectivePlayerContextCampaignError(
                "fixture capture identity must be complete or absent"
            )
        resolved = (
            self.resolved_fixture_identifier,
            self.resolved_source_match_id,
            self.resolved_home_team,
            self.resolved_away_team,
            self.resolved_kickoff,
            self.fixture_candidate_sha256,
        )
        if any(item is not None for item in resolved) and not all(
            item is not None for item in resolved
        ):
            raise FotMobProspectivePlayerContextCampaignError(
                "resolved fixture identity must be complete or absent"
            )
        match_capture = (
            self.match_details_raw_sha256,
            self.match_details_raw_size,
            self.match_details_manifest_sha256,
        )
        if any(item is not None for item in match_capture) and not all(
            item is not None for item in match_capture
        ):
            raise FotMobProspectivePlayerContextCampaignError(
                "match-details capture identity must be complete or absent"
            )
        file_map = {item.relative_path: item for item in self.files}

        def require_file(path: str, sha: str | None, size: int | None = None) -> None:
            if sha is None:
                if path in file_map:
                    raise FotMobProspectivePlayerContextCampaignError(
                        f"completed evidence file lacks receipt identity: {path}"
                    )
                return
            record = file_map.get(path)
            if record is None or record.sha256 != sha:
                raise FotMobProspectivePlayerContextCampaignError(
                    f"receipt identity does not match evidence file: {path}"
                )
            if size is not None and record.byte_size != size:
                raise FotMobProspectivePlayerContextCampaignError(
                    f"receipt size does not match evidence file: {path}"
                )

        require_file("fixture/response.json", self.fixture_raw_sha256, self.fixture_raw_size)
        require_file("fixture/manifest.json", self.fixture_manifest_sha256)
        require_file(
            "fixture/schema-assessment.json", self.fixture_schema_assessment_sha256
        )
        require_file(
            "fixture/fixture-candidates.json", self.fixture_candidate_bundle_sha256
        )
        require_file(
            "fixture/review-decision-ledger.json", self.fixture_review_ledger_sha256
        )
        require_file("fixture/catalog.json", self.fixture_catalog_sha256)
        require_file(
            "fixture/catalog-manifest.json", self.fixture_catalog_manifest_sha256
        )
        require_file("fixture/admission.json", self.fixture_admission_sha256)
        require_file("fixture/bootstrap.json", self.fixture_bootstrap_sha256)
        require_file(
            "fixture/bootstrap-verification-receipt.json",
            self.fixture_bootstrap_receipt_sha256,
        )
        require_file(
            "match-details/response.json",
            self.match_details_raw_sha256,
            self.match_details_raw_size,
        )
        require_file(
            "match-details/manifest.json", self.match_details_manifest_sha256
        )
        require_file(
            "match-details/persisted-evidence-receipt.json",
            self.persisted_evidence_receipt_sha256,
        )
        require_file(
            "match-details/structure-assessment.json",
            self.structure_assessment_sha256,
        )
        require_file(
            "player-context-review-candidates.json",
            self.player_context_report_sha256,
        )

        fixture_derived = (
            self.fixture_schema_assessment_sha256,
            self.fixture_candidate_bundle_sha256,
        )
        if any(item is not None for item in fixture_derived) and not all(
            item is not None for item in fixture_capture
        ):
            raise FotMobProspectivePlayerContextCampaignError(
                "derived fixture evidence requires exact fixture capture"
            )
        review_chain = (
            self.fixture_review_ledger_sha256,
            self.fixture_catalog_sha256,
            self.fixture_catalog_manifest_sha256,
            self.fixture_admission_sha256,
            self.fixture_bootstrap_sha256,
            self.fixture_bootstrap_receipt_sha256,
        )
        ledger, catalog, catalog_manifest, admission, bootstrap, bootstrap_receipt = review_chain
        if (catalog is None) != (catalog_manifest is None):
            raise FotMobProspectivePlayerContextCampaignError(
                "catalog and catalog manifest identities must appear together"
            )
        ordered_review_stages = (
            ledger is not None,
            catalog is not None and catalog_manifest is not None,
            admission is not None,
            bootstrap is not None,
            bootstrap_receipt is not None,
        )
        seen_missing = False
        for present in ordered_review_stages:
            if not present:
                seen_missing = True
            elif seen_missing:
                raise FotMobProspectivePlayerContextCampaignError(
                    "fixture review/bootstrap stage identity has a gap"
                )
        if any(item is not None for item in match_capture) and not all(
            item is not None for item in review_chain
        ):
            raise FotMobProspectivePlayerContextCampaignError(
                "match-details capture requires exact reviewed fixture bootstrap"
            )
        if self.persisted_evidence_receipt_sha256 is not None and not all(
            item is not None for item in match_capture
        ):
            raise FotMobProspectivePlayerContextCampaignError(
                "PR52 evidence requires exact match-details capture"
            )
        if self.structure_assessment_sha256 is not None and self.persisted_evidence_receipt_sha256 is None:
            raise FotMobProspectivePlayerContextCampaignError(
                "PR53 evidence requires exact PR52 receipt"
            )
        if self.player_context_report_sha256 is not None and self.structure_assessment_sha256 is None:
            raise FotMobProspectivePlayerContextCampaignError(
                "player-context report requires exact PR53 assessment"
            )
        if self.campaign_result in {
            CampaignResult.SUCCESS_PROSPECTIVE_PLAYER_CONTEXT_EVIDENCE_CAPTURED,
            CampaignResult.NO_PLAYER_CONTEXT_CANDIDATE_STRUCTURE_OBSERVED,
        }:
            required = resolved + fixture_capture + fixture_derived + review_chain + match_capture + (
                self.persisted_evidence_receipt_sha256,
                self.structure_assessment_sha256,
                self.player_context_report_sha256,
            )
            if not all(item is not None for item in required):
                raise FotMobProspectivePlayerContextCampaignError(
                    "terminal structural result requires the complete evidence chain"
                )
        if self.campaign_result is CampaignResult.FIXTURE_REVIEW_NOT_GRANTED:
            if not all(item is not None for item in resolved + fixture_capture + fixture_derived):
                raise FotMobProspectivePlayerContextCampaignError(
                    "review-not-granted result must retain exact candidate evidence"
                )
            if any(item is not None for item in review_chain + match_capture):
                raise FotMobProspectivePlayerContextCampaignError(
                    "review-not-granted result cannot contain downstream evidence"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "campaign_scope": CAMPAIGN_SCOPE,
            "repository": self.repository,
            "base_sha": self.base_sha,
            "repository_head_sha": self.repository_head_sha,
            "workflow_name": self.workflow_name,
            "workflow_run_id": self.workflow_run_id,
            "workflow_run_attempt": self.workflow_run_attempt,
            "github_actor": self.github_actor,
            "started_at": serialize_utc(self.started_at),
            "completed_at": serialize_utc(self.completed_at),
            "target_request_date": TARGET_REQUEST_DATE,
            "expected_home_team": EXPECTED_HOME_TEAM,
            "expected_away_team": EXPECTED_AWAY_TEAM,
            "expected_kickoff": EXPECTED_KICKOFF,
            "resolved_fixture_identifier": self.resolved_fixture_identifier,
            "resolved_source_match_id": self.resolved_source_match_id,
            "resolved_home_team": self.resolved_home_team,
            "resolved_away_team": self.resolved_away_team,
            "resolved_kickoff": (
                serialize_utc(self.resolved_kickoff)
                if self.resolved_kickoff is not None
                else None
            ),
            "fixture_candidate_sha256": self.fixture_candidate_sha256,
            "fixture_raw_sha256": self.fixture_raw_sha256,
            "fixture_raw_size": self.fixture_raw_size,
            "fixture_manifest_sha256": self.fixture_manifest_sha256,
            "fixture_schema_assessment_sha256": self.fixture_schema_assessment_sha256,
            "fixture_candidate_bundle_sha256": self.fixture_candidate_bundle_sha256,
            "fixture_review_ledger_sha256": self.fixture_review_ledger_sha256,
            "fixture_catalog_sha256": self.fixture_catalog_sha256,
            "fixture_catalog_manifest_sha256": self.fixture_catalog_manifest_sha256,
            "fixture_admission_sha256": self.fixture_admission_sha256,
            "fixture_bootstrap_sha256": self.fixture_bootstrap_sha256,
            "fixture_bootstrap_receipt_sha256": self.fixture_bootstrap_receipt_sha256,
            "match_details_raw_sha256": self.match_details_raw_sha256,
            "match_details_raw_size": self.match_details_raw_size,
            "match_details_manifest_sha256": self.match_details_manifest_sha256,
            "persisted_evidence_receipt_sha256": self.persisted_evidence_receipt_sha256,
            "structure_assessment_sha256": self.structure_assessment_sha256,
            "player_context_report_sha256": self.player_context_report_sha256,
            "campaign_result": self.campaign_result.value,
            "files": [item.to_dict() for item in self.files],
            "safety": dict(self.safety),
        }


def canonical_campaign_receipt_bytes(
    value: FotMobProspectivePlayerContextCampaignReceipt,
) -> bytes:
    if type(value) is not FotMobProspectivePlayerContextCampaignReceipt:
        raise FotMobProspectivePlayerContextCampaignError(
            "value must be exact campaign receipt"
        )
    return canonical_json_bytes(dataclasses.replace(value).to_dict())


def campaign_receipt_from_bytes(raw: Any) -> FotMobProspectivePlayerContextCampaignReceipt:
    """Strictly reconstruct one exact canonical campaign receipt."""

    if type(raw) is not bytes or not raw:
        raise FotMobProspectivePlayerContextCampaignError(
            "campaign receipt must be non-empty exact bytes"
        )

    def pairs(items: list[tuple[Any, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if type(key) is not str or key in result:
                raise FotMobProspectivePlayerContextCampaignError(
                    "campaign receipt contains duplicate or invalid JSON key"
                )
            result[key] = value
        return result

    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                FotMobProspectivePlayerContextCampaignError(
                    f"non-finite JSON constant forbidden: {value}"
                )
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FotMobProspectivePlayerContextCampaignError(
            "campaign receipt is not strict UTF-8 JSON"
        ) from exc
    expected_keys = {
        "schema_version", "dataset_name", "campaign_scope", "repository",
        "base_sha", "repository_head_sha", "workflow_name", "workflow_run_id",
        "workflow_run_attempt", "github_actor", "started_at", "completed_at",
        "target_request_date", "expected_home_team", "expected_away_team",
        "expected_kickoff", "resolved_fixture_identifier", "resolved_source_match_id",
        "resolved_home_team", "resolved_away_team", "resolved_kickoff",
        "fixture_candidate_sha256", "fixture_raw_sha256", "fixture_raw_size",
        "fixture_manifest_sha256", "fixture_schema_assessment_sha256",
        "fixture_candidate_bundle_sha256", "fixture_review_ledger_sha256",
        "fixture_catalog_sha256", "fixture_catalog_manifest_sha256",
        "fixture_admission_sha256", "fixture_bootstrap_sha256",
        "fixture_bootstrap_receipt_sha256", "match_details_raw_sha256",
        "match_details_raw_size", "match_details_manifest_sha256",
        "persisted_evidence_receipt_sha256", "structure_assessment_sha256",
        "player_context_report_sha256", "campaign_result", "files", "safety",
    }
    if type(payload) is not dict or set(payload) != expected_keys:
        raise FotMobProspectivePlayerContextCampaignError(
            "campaign receipt keys do not match the exact contract"
        )
    frozen = {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "campaign_scope": CAMPAIGN_SCOPE,
        "target_request_date": TARGET_REQUEST_DATE,
        "expected_home_team": EXPECTED_HOME_TEAM,
        "expected_away_team": EXPECTED_AWAY_TEAM,
        "expected_kickoff": EXPECTED_KICKOFF,
    }
    if any(payload[key] != value for key, value in frozen.items()):
        raise FotMobProspectivePlayerContextCampaignError(
            "campaign receipt frozen identity mismatch"
        )
    raw_files = payload["files"]
    if type(raw_files) is not list:
        raise FotMobProspectivePlayerContextCampaignError("receipt files must be list")
    files: list[EvidenceFile] = []
    for item in raw_files:
        if type(item) is not dict or set(item) != {"relative_path", "sha256", "byte_size"}:
            raise FotMobProspectivePlayerContextCampaignError(
                "receipt evidence file keys mismatch"
            )
        files.append(EvidenceFile(**item))
    kickoff = payload["resolved_kickoff"]
    try:
        result = FotMobProspectivePlayerContextCampaignReceipt(
            repository=payload["repository"],
            base_sha=payload["base_sha"],
            repository_head_sha=payload["repository_head_sha"],
            workflow_name=payload["workflow_name"],
            workflow_run_id=payload["workflow_run_id"],
            workflow_run_attempt=payload["workflow_run_attempt"],
            github_actor=payload["github_actor"],
            started_at=parse_utc(payload["started_at"], "started_at"),
            completed_at=parse_utc(payload["completed_at"], "completed_at"),
            campaign_result=CampaignResult(payload["campaign_result"]),
            resolved_fixture_identifier=payload["resolved_fixture_identifier"],
            resolved_source_match_id=payload["resolved_source_match_id"],
            resolved_home_team=payload["resolved_home_team"],
            resolved_away_team=payload["resolved_away_team"],
            resolved_kickoff=(
                parse_utc(kickoff, "resolved_kickoff") if kickoff is not None else None
            ),
            fixture_candidate_sha256=payload["fixture_candidate_sha256"],
            fixture_raw_sha256=payload["fixture_raw_sha256"],
            fixture_raw_size=payload["fixture_raw_size"],
            fixture_manifest_sha256=payload["fixture_manifest_sha256"],
            fixture_schema_assessment_sha256=payload["fixture_schema_assessment_sha256"],
            fixture_candidate_bundle_sha256=payload["fixture_candidate_bundle_sha256"],
            fixture_review_ledger_sha256=payload["fixture_review_ledger_sha256"],
            fixture_catalog_sha256=payload["fixture_catalog_sha256"],
            fixture_catalog_manifest_sha256=payload["fixture_catalog_manifest_sha256"],
            fixture_admission_sha256=payload["fixture_admission_sha256"],
            fixture_bootstrap_sha256=payload["fixture_bootstrap_sha256"],
            fixture_bootstrap_receipt_sha256=payload["fixture_bootstrap_receipt_sha256"],
            match_details_raw_sha256=payload["match_details_raw_sha256"],
            match_details_raw_size=payload["match_details_raw_size"],
            match_details_manifest_sha256=payload["match_details_manifest_sha256"],
            persisted_evidence_receipt_sha256=payload["persisted_evidence_receipt_sha256"],
            structure_assessment_sha256=payload["structure_assessment_sha256"],
            player_context_report_sha256=payload["player_context_report_sha256"],
            files=tuple(files),
            safety=payload["safety"],
        )
    except (ValueError, TypeError) as exc:
        if isinstance(exc, FotMobProspectivePlayerContextCampaignError):
            raise
        raise FotMobProspectivePlayerContextCampaignError(
            "campaign receipt values are invalid"
        ) from exc
    if canonical_campaign_receipt_bytes(result) != raw:
        raise FotMobProspectivePlayerContextCampaignError(
            "campaign receipt bytes are not exact canonical bytes"
        )
    return result


def sha256_campaign_receipt(
    value: FotMobProspectivePlayerContextCampaignReceipt,
) -> str:
    return hashlib.sha256(canonical_campaign_receipt_bytes(value)).hexdigest()


def evidence_file(relative_path: str, content: bytes) -> EvidenceFile:
    if type(content) is not bytes or not content:
        raise FotMobProspectivePlayerContextCampaignError(
            "evidence content must be non-empty exact bytes"
        )
    return EvidenceFile(
        relative_path=relative_path,
        sha256=hashlib.sha256(content).hexdigest(),
        byte_size=len(content),
    )


def verify_evidence_files(
    expected: Sequence[EvidenceFile],
    contents: Mapping[str, bytes],
) -> None:
    """Verify an exact detached artifact payload against its receipt entries."""

    if not isinstance(expected, Sequence) or isinstance(expected, (str, bytes)):
        raise FotMobProspectivePlayerContextCampaignError("expected files invalid")
    records = tuple(expected)
    if any(type(item) is not EvidenceFile for item in records):
        raise FotMobProspectivePlayerContextCampaignError("expected files invalid")
    if records != tuple(sorted(records, key=lambda item: item.relative_path)):
        raise FotMobProspectivePlayerContextCampaignError("expected files not sorted")
    if not isinstance(contents, Mapping) or set(contents) != {
        item.relative_path for item in records
    }:
        raise FotMobProspectivePlayerContextCampaignError(
            "artifact file set differs from receipt"
        )
    for item in records:
        raw = contents[item.relative_path]
        if type(raw) is not bytes:
            raise FotMobProspectivePlayerContextCampaignError(
                "artifact file content must be exact bytes"
            )
        if len(raw) != item.byte_size or hashlib.sha256(raw).hexdigest() != item.sha256:
            raise FotMobProspectivePlayerContextCampaignError(
                f"artifact file differs from receipt: {item.relative_path}"
            )


def candidate_identity(candidate: FotMobFixtureCandidate) -> dict[str, Any]:
    if type(candidate) is not FotMobFixtureCandidate:
        raise FotMobProspectivePlayerContextCampaignError("candidate type invalid")
    return {
        "fixture_identifier": f"FOTMOB:{candidate.source_match_id}",
        "source_match_id": str(candidate.source_match_id),
        "home_team": candidate.home_name,
        "away_team": candidate.away_name,
        "kickoff": candidate.kickoff_utc,
        "candidate_sha256": sha256_fotmob_fixture_candidate(candidate),
    }


__all__ = [
    "CAMPAIGN_SCOPE",
    "DATASET_NAME",
    "EXPECTED_AWAY_TEAM",
    "EXPECTED_HOME_TEAM",
    "EXPECTED_KICKOFF",
    "EvidenceFile",
    "FotMobProspectivePlayerContextCampaignError",
    "FotMobProspectivePlayerContextCampaignReceipt",
    "CampaignResult",
    "REPORT_DATASET_NAME",
    "REQUEST_CCODE3",
    "REQUEST_TIMEZONE",
    "SCHEMA_VERSION",
    "TARGET_REQUEST_DATE",
    "build_player_context_review_candidate_report",
    "campaign_receipt_from_bytes",
    "candidate_identity",
    "canonical_campaign_receipt_bytes",
    "canonical_json_bytes",
    "evidence_file",
    "resolve_exact_target_candidate",
    "safety_flags",
    "sha256_campaign_receipt",
    "verify_evidence_files",
]
