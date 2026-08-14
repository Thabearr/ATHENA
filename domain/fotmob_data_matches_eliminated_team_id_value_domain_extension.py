"""Implement the reviewed FotMob ``eliminatedTeamId`` structural value domain.

PR #89 implements only the value-domain widening pre-registered by PR #88.
PR #39 and PR #87 remain frozen and unchanged. Accepted non-null values are
projected to ``null`` only so the unchanged PR #87 structural chain can be
re-run; the PR #89 receipt remains bound to the original source capture.
No football semantics or downstream authority is created here.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime
import enum
import hashlib
import json
import re
import types
from collections.abc import Mapping
from typing import Any

import domain.fotmob_data_matches_eliminated_team_id_value_domain_protocol as pr88_protocol
import domain.fotmob_data_matches_schema as pr39_schema
import domain.fotmob_data_matches_terminal_state_schema_extension as pr87_implementation
from domain.fotmob_data_matches_capture import (
    MAX_RESPONSE_BYTES,
    FotMobDataMatchesCaptureError,
    FotMobDataMatchesCaptureManifest,
    serialize_utc,
    sha256_bytes,
    sha256_data_matches_capture_manifest,
)
from domain.fotmob_data_matches_probe import (
    FotMobDataMatchesProbeError,
    validate_ccode3,
    validate_request_date,
    validate_timezone,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-data-matches-eliminated-team-id-value-domain-extension-v1"
IMPLEMENTATION_SCOPE = "REVIEWED_ELIMINATED_TEAM_ID_STRUCTURAL_VALUE_DOMAIN_ONLY"
IMPLEMENTATION_STATE = "IMPLEMENTED_STRUCTURAL_VALUE_DOMAIN_NO_SEMANTIC_PROMOTION"
REPOSITORY_MAIN_SHA = "df6b782e0e1b36c46089333a893a12f44e40fa07"
CANDIDATE_SOURCE_KEY = "fotmob_data_matches_reviewed_catalog"

PR39_SCHEMA_BLOB_SHA = "4dfff0eb05335895c3ee0fcaa7b8da1299ea692f"
PR85_EVIDENCE_BLOB_SHA = "7b74e9893071ef47ea425b4f106d92b0c5e1ddc2"
PR87_IMPLEMENTATION_BLOB_SHA = "fc120476739293abbb5db4374a0b4d7cfe8a1fc3"
PR88_PROTOCOL_BLOB_SHA = "85414d1377b231e11ff302d0706ddcd42e41c984"
PR88_PROTOCOL_SHA256 = "e1b435e8ed833518f9c4a6c5ba89b3c22773c6e3c30e9a50bb85b708b9ff77da"
PR88_PROTOCOL_SIZE = 4276

NEXT_REQUIRED_BOUNDARY = (
    "PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_STATUS_REASON_SEMANTICS_PROTOCOL"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "eliminated_team_id_value_domain_implementation_authorized",
        "eliminated_team_id_value_domain_qualified",
        "eliminated_team_id_semantics_qualified",
        "pr39_schema_mutation_authorized",
        "pr87_implementation_mutation_authorized",
        "status_reason_semantics_qualified",
        "final_result_semantics_qualified",
        "source_capability_update_authorized",
        "source_history_adapter_approved",
        "source_history_completeness_proven",
        "pr80_constructor_input_authorized",
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


class EliminatedTeamIdValueDomainStatus(str, enum.Enum):
    QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN = (
        "QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN"
    )
    BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT = "BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT"
    BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT = (
        "BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT"
    )
    BLOCKED_ELIMINATED_TEAM_ID_TYPE_OR_NULLABILITY_MISMATCH = (
        "BLOCKED_ELIMINATED_TEAM_ID_TYPE_OR_NULLABILITY_MISMATCH"
    )
    BLOCKED_ELIMINATED_TEAM_ID_NONPOSITIVE_INTEGER = (
        "BLOCKED_ELIMINATED_TEAM_ID_NONPOSITIVE_INTEGER"
    )


if tuple(item.value for item in EliminatedTeamIdValueDomainStatus) != pr88_protocol.STATUS_VOCABULARY:
    raise RuntimeError("PR89 status vocabulary differs from frozen PR88 protocol")


class FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError(ValueError):
    """Raised when the frozen PR #88 value-domain implementation fails closed."""

    def __init__(self, status: EliminatedTeamIdValueDomainStatus, message: str) -> None:
        if not isinstance(status, EliminatedTeamIdValueDomainStatus):
            raise TypeError("status must be EliminatedTeamIdValueDomainStatus")
        super().__init__(message)
        self.status = status


def _error(
    status: EliminatedTeamIdValueDomainStatus,
    message: str,
) -> FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError:
    return FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError(status, message)


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _checked_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
            "PR89 safety keys mismatch",
        )
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
            "all PR89 safety values must be exact False",
        )
    return _default_safety()


def _sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
            f"{label} must be a lowercase SHA-256",
        )
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            f"{label} must be a datetime",
        )
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise _error(
                EliminatedTeamIdValueDomainStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
                f"{label} must be timezone-aware",
            )
        return value.astimezone(datetime.timezone.utc)
    except FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            f"{label} is invalid",
        ) from exc


def _request_identity(
    request_date: Any,
    timezone: Any,
    ccode3: Any,
) -> tuple[str, str, str]:
    try:
        return (
            validate_request_date(request_date),
            validate_timezone(timezone),
            validate_ccode3(ccode3),
        )
    except FotMobDataMatchesProbeError as exc:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            "assessment request identity is invalid",
        ) from exc


def _verify_frozen_ancestry() -> None:
    if pr88_protocol.PR39_SCHEMA_BLOB_SHA != PR39_SCHEMA_BLOB_SHA:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
            "PR88 no longer binds the frozen PR39 schema",
        )
    if pr88_protocol.PR85_EVIDENCE_BLOB_SHA != PR85_EVIDENCE_BLOB_SHA:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            "PR88 no longer binds the frozen PR85 evidence receipt",
        )
    if pr88_protocol.PR87_IMPLEMENTATION_BLOB_SHA != PR87_IMPLEMENTATION_BLOB_SHA:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
            "PR88 no longer binds the frozen PR87 implementation",
        )
    if (
        pr88_protocol.PROTOCOL_SHA256 != PR88_PROTOCOL_SHA256
        or pr88_protocol.PROTOCOL_SIZE != PR88_PROTOCOL_SIZE
    ):
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            "PR88 protocol identity constants changed",
        )
    try:
        protocol = pr88_protocol.build_fotmob_data_matches_eliminated_team_id_value_domain_protocol()
        exact = (
            pr88_protocol.canonical_fotmob_data_matches_eliminated_team_id_value_domain_protocol_bytes(
                protocol
            )
        )
    except Exception as exc:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            "PR88 protocol or its frozen evidence ancestry no longer revalidates",
        ) from exc
    if (
        hashlib.sha256(exact).hexdigest() != PR88_PROTOCOL_SHA256
        or len(exact) != PR88_PROTOCOL_SIZE
    ):
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            "PR88 canonical protocol identity changed",
        )
    if pr87_implementation.PR39_SCHEMA_BLOB_SHA != PR39_SCHEMA_BLOB_SHA:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
            "PR87 no longer binds the frozen PR39 schema",
        )
    if pr87_implementation.NEXT_REQUIRED_BOUNDARY != (
        "PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_ELIMINATED_TEAM_ID_VALUE_DOMAIN_EXTENSION"
    ):
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
            "PR87 next boundary changed",
        )

    capability = SOURCE_CAPABILITY_REGISTRY.get(CANDIDATE_SOURCE_KEY)
    if capability is None:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            "reviewed FotMob data-matches source capability is missing",
        )
    if capability.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            "reviewed FotMob fixture identity premise changed",
        )
    if capability.full_time_score is not CapabilityAvailability.NOT_CAPTURED:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            "full-time-score capability changed before PR89",
        )
    if capability.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            "historical-coverage capability changed before PR89",
        )


def _validate_source_input(
    raw_json: Any,
    source_manifest: Any,
) -> FotMobDataMatchesCaptureManifest:
    if type(raw_json) is not bytes or not raw_json:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            "raw_json must be non-empty exact bytes",
        )
    if len(raw_json) > MAX_RESPONSE_BYTES:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            "raw_json exceeds the reviewed capture limit",
        )
    if not isinstance(source_manifest, FotMobDataMatchesCaptureManifest):
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            "source_manifest must be the reviewed PR38 manifest type",
        )
    try:
        manifest = dataclasses.replace(source_manifest)
    except FotMobDataMatchesCaptureError as exc:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            "source manifest does not revalidate",
        ) from exc
    if manifest.raw_size != len(raw_json) or manifest.raw_sha256 != sha256_bytes(raw_json):
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            "source raw bytes do not match manifest lineage",
        )
    return manifest


def _validate_and_project_eliminated_team_id(
    payload: Any,
) -> tuple[dict[str, Any], int, int, int]:
    if type(payload) is not dict:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
            "source JSON top level is not an object",
        )
    leagues = payload.get("leagues")
    if type(leagues) is not list:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
            "source JSON does not expose a list of leagues for the frozen PR87 chain",
        )

    projected = copy.deepcopy(payload)
    projected_leagues = projected.get("leagues")
    if type(projected_leagues) is not list:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
            "internal eliminatedTeamId projection failed",
        )

    total_count = 0
    null_count = 0
    non_null_count = 0
    for league_index, (source_league, projected_league) in enumerate(
        zip(leagues, projected_leagues, strict=True)
    ):
        if type(source_league) is not dict or type(projected_league) is not dict:
            raise _error(
                EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
                f"leagues[{league_index}] is not an object",
            )
        source_matches = source_league.get("matches")
        projected_matches = projected_league.get("matches")
        if type(source_matches) is not list or type(projected_matches) is not list:
            raise _error(
                EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
                f"leagues[{league_index}].matches is not a list",
            )
        if len(source_matches) != len(projected_matches):
            raise _error(
                EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
                "internal eliminatedTeamId projection changed match count",
            )
        for match_index, (source_match, projected_match) in enumerate(
            zip(source_matches, projected_matches, strict=True)
        ):
            label = f"leagues[{league_index}].matches[{match_index}].eliminatedTeamId"
            if type(source_match) is not dict or type(projected_match) is not dict:
                raise _error(
                    EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
                    f"{label} parent is not an object",
                )
            if "eliminatedTeamId" not in source_match:
                raise _error(
                    EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
                    f"{label} is missing from the frozen PR39 match contract",
                )

            total_count += 1
            value = source_match["eliminatedTeamId"]
            if value is None:
                null_count += 1
                continue
            if type(value) is not int:
                raise _error(
                    EliminatedTeamIdValueDomainStatus.BLOCKED_ELIMINATED_TEAM_ID_TYPE_OR_NULLABILITY_MISMATCH,
                    f"{label} must be null or an exact integer excluding bool",
                )
            if value < 1:
                raise _error(
                    EliminatedTeamIdValueDomainStatus.BLOCKED_ELIMINATED_TEAM_ID_NONPOSITIVE_INTEGER,
                    f"{label} must be at least 1 when non-null",
                )
            non_null_count += 1
            projected_match["eliminatedTeamId"] = None

    return projected, total_count, null_count, non_null_count


def _canonical_projection(payload: dict[str, Any]) -> bytes:
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
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
            "eliminatedTeamId projection serialization failed",
        ) from exc


def _projected_manifest(
    source_manifest: FotMobDataMatchesCaptureManifest,
    projected_raw: bytes,
) -> FotMobDataMatchesCaptureManifest:
    content_length = None if source_manifest.content_length is None else len(projected_raw)
    try:
        return dataclasses.replace(
            source_manifest,
            content_length=content_length,
            network_acquisition_performed=False,
            raw_sha256=sha256_bytes(projected_raw),
            raw_size=len(projected_raw),
        )
    except FotMobDataMatchesCaptureError as exc:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
            "internal projection manifest failed reviewed capture validation",
        ) from exc


@dataclasses.dataclass(frozen=True)
class FotMobDataMatchesEliminatedTeamIdValueDomainAssessment:
    schema_version: int
    dataset_name: str
    implementation_scope: str
    implementation_state: str
    status: EliminatedTeamIdValueDomainStatus
    source_capture_manifest_sha256: str
    source_raw_sha256: str
    source_raw_size: int
    source_observed_at: datetime.datetime
    request_date: str
    timezone: str
    ccode3: str
    eliminated_team_id_occurrence_count: int
    eliminated_team_id_null_count: int
    eliminated_team_id_non_null_count: int
    pr87_projection_raw_sha256: str
    pr87_projection_raw_size: int
    pr87_assessment_sha256: str
    pr87_assessment_size: int
    pr87_match_count: int
    status_reason_semantics_qualified: bool
    final_result_semantics_qualified: bool
    next_required_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise _error(
                EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
                "schema_version must be exact integer 1",
            )
        if self.dataset_name != DATASET_NAME:
            raise _error(
                EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
                "dataset_name mismatch",
            )
        if self.implementation_scope != IMPLEMENTATION_SCOPE:
            raise _error(
                EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
                "implementation_scope mismatch",
            )
        if self.implementation_state != IMPLEMENTATION_STATE:
            raise _error(
                EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
                "implementation_state mismatch",
            )
        if (
            self.status
            is not EliminatedTeamIdValueDomainStatus.QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN
        ):
            raise _error(
                EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
                "successful assessment must carry the exact qualified structural status",
            )

        for label, value in (
            ("source_capture_manifest_sha256", self.source_capture_manifest_sha256),
            ("source_raw_sha256", self.source_raw_sha256),
            ("pr87_projection_raw_sha256", self.pr87_projection_raw_sha256),
            ("pr87_assessment_sha256", self.pr87_assessment_sha256),
        ):
            _sha256(value, label)

        if (
            type(self.source_raw_size) is not int
            or not 0 < self.source_raw_size <= MAX_RESPONSE_BYTES
        ):
            raise _error(
                EliminatedTeamIdValueDomainStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
                "source_raw_size must be an exact positive integer within capture limit",
            )
        if (
            type(self.pr87_projection_raw_size) is not int
            or not 0 < self.pr87_projection_raw_size <= MAX_RESPONSE_BYTES
        ):
            raise _error(
                EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
                "pr87_projection_raw_size must be an exact positive integer within capture limit",
            )
        if type(self.pr87_assessment_size) is not int or self.pr87_assessment_size <= 0:
            raise _error(
                EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
                "pr87_assessment_size must be an exact positive integer",
            )

        for label, value in (
            ("eliminated_team_id_occurrence_count", self.eliminated_team_id_occurrence_count),
            ("eliminated_team_id_null_count", self.eliminated_team_id_null_count),
            ("eliminated_team_id_non_null_count", self.eliminated_team_id_non_null_count),
            ("pr87_match_count", self.pr87_match_count),
        ):
            if type(value) is not int or value < 0:
                raise _error(
                    EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
                    f"{label} must be an exact non-negative integer",
                )
        if (
            self.eliminated_team_id_null_count + self.eliminated_team_id_non_null_count
            != self.eliminated_team_id_occurrence_count
        ):
            raise _error(
                EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
                "eliminatedTeamId occurrence counts disagree",
            )
        if self.eliminated_team_id_occurrence_count != self.pr87_match_count:
            raise _error(
                EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
                "eliminatedTeamId occurrence count must equal the PR87 match count",
            )

        if (
            type(self.status_reason_semantics_qualified) is not bool
            or self.status_reason_semantics_qualified
        ):
            raise _error(
                EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
                "status.reason semantics must remain exact False",
            )
        if (
            type(self.final_result_semantics_qualified) is not bool
            or self.final_result_semantics_qualified
        ):
            raise _error(
                EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
                "final-result semantics must remain exact False",
            )
        if self.next_required_boundary != NEXT_REQUIRED_BOUNDARY:
            raise _error(
                EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
                "next boundary mismatch",
            )

        observed_at = _utc(self.source_observed_at, "source_observed_at")
        request_date, timezone, ccode3 = _request_identity(
            self.request_date,
            self.timezone,
            self.ccode3,
        )
        object.__setattr__(self, "source_observed_at", observed_at)
        object.__setattr__(self, "request_date", request_date)
        object.__setattr__(self, "timezone", timezone)
        object.__setattr__(self, "ccode3", ccode3)
        object.__setattr__(self, "safety", _checked_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "implementation_scope": self.implementation_scope,
            "implementation_state": self.implementation_state,
            "status": self.status.value,
            "source_capture_manifest_sha256": self.source_capture_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "source_raw_size": self.source_raw_size,
            "source_observed_at": serialize_utc(self.source_observed_at),
            "request_date": self.request_date,
            "timezone": self.timezone,
            "ccode3": self.ccode3,
            "eliminated_team_id_occurrence_count": self.eliminated_team_id_occurrence_count,
            "eliminated_team_id_null_count": self.eliminated_team_id_null_count,
            "eliminated_team_id_non_null_count": self.eliminated_team_id_non_null_count,
            "pr87_projection_raw_sha256": self.pr87_projection_raw_sha256,
            "pr87_projection_raw_size": self.pr87_projection_raw_size,
            "pr87_assessment_sha256": self.pr87_assessment_sha256,
            "pr87_assessment_size": self.pr87_assessment_size,
            "pr87_match_count": self.pr87_match_count,
            "status_reason_semantics_qualified": self.status_reason_semantics_qualified,
            "final_result_semantics_qualified": self.final_result_semantics_qualified,
            "next_required_boundary": self.next_required_boundary,
            "safety": dict(self.safety),
        }


def assess_fotmob_data_matches_eliminated_team_id_value_domain(
    raw_json: bytes,
    source_manifest: FotMobDataMatchesCaptureManifest,
) -> FotMobDataMatchesEliminatedTeamIdValueDomainAssessment:
    """Validate PR88's value domain and re-run the frozen PR87 structural chain."""

    _verify_frozen_ancestry()
    manifest = _validate_source_input(raw_json, source_manifest)
    try:
        payload = pr39_schema._strict_response_json(raw_json)
    except pr39_schema.FotMobDataMatchesSchemaError as exc:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
            "source JSON does not satisfy the frozen PR39 strict JSON parser",
        ) from exc

    projected_payload, occurrence_count, null_count, non_null_count = (
        _validate_and_project_eliminated_team_id(payload)
    )
    projected_raw = _canonical_projection(projected_payload)
    projected_manifest = _projected_manifest(manifest, projected_raw)

    try:
        pr87_assessment = (
            pr87_implementation.assess_fotmob_data_matches_terminal_state_schema_extension(
                projected_raw,
                projected_manifest,
            )
        )
        pr87_bytes = (
            pr87_implementation.canonical_fotmob_data_matches_terminal_state_schema_extension_assessment_bytes(
                pr87_assessment
            )
        )
    except pr87_implementation.FotMobDataMatchesTerminalStateSchemaExtensionError as exc:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
            "frozen PR87 structural chain rejected the eliminatedTeamId-null projection: "
            f"{exc.status.value}",
        ) from exc

    if (
        pr87_assessment.status
        is not pr87_implementation.TerminalStateSchemaExtensionStatus.QUALIFIED_STRUCTURAL_TERMINAL_STATE_SCHEMA_EXTENSION
    ):
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
            "frozen PR87 structural chain did not return its qualified status",
        )
    if pr87_assessment.reason_semantics_qualified or pr87_assessment.final_result_semantics_qualified:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
            "PR87 semantic authority changed unexpectedly",
        )
    if occurrence_count != pr87_assessment.match_count:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
            "eliminatedTeamId occurrence count disagrees with the frozen PR87 match count",
        )

    return FotMobDataMatchesEliminatedTeamIdValueDomainAssessment(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        implementation_scope=IMPLEMENTATION_SCOPE,
        implementation_state=IMPLEMENTATION_STATE,
        status=EliminatedTeamIdValueDomainStatus.QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN,
        source_capture_manifest_sha256=sha256_data_matches_capture_manifest(manifest),
        source_raw_sha256=manifest.raw_sha256,
        source_raw_size=manifest.raw_size,
        source_observed_at=manifest.observed_at,
        request_date=manifest.request_date,
        timezone=manifest.timezone,
        ccode3=manifest.ccode3,
        eliminated_team_id_occurrence_count=occurrence_count,
        eliminated_team_id_null_count=null_count,
        eliminated_team_id_non_null_count=non_null_count,
        pr87_projection_raw_sha256=sha256_bytes(projected_raw),
        pr87_projection_raw_size=len(projected_raw),
        pr87_assessment_sha256=hashlib.sha256(pr87_bytes).hexdigest(),
        pr87_assessment_size=len(pr87_bytes),
        pr87_match_count=pr87_assessment.match_count,
        status_reason_semantics_qualified=False,
        final_result_semantics_qualified=False,
        next_required_boundary=NEXT_REQUIRED_BOUNDARY,
        safety=_default_safety(),
    )


def canonical_fotmob_data_matches_eliminated_team_id_value_domain_assessment_bytes(
    assessment: Any,
) -> bytes:
    if not isinstance(assessment, FotMobDataMatchesEliminatedTeamIdValueDomainAssessment):
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
            "assessment must be FotMobDataMatchesEliminatedTeamIdValueDomainAssessment",
        )
    try:
        return (
            json.dumps(
                assessment.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error(
            EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT,
            "assessment serialization failed",
        ) from exc


def sha256_fotmob_data_matches_eliminated_team_id_value_domain_assessment(
    assessment: Any,
) -> str:
    return hashlib.sha256(
        canonical_fotmob_data_matches_eliminated_team_id_value_domain_assessment_bytes(
            assessment
        )
    ).hexdigest()


__all__ = [
    "CANDIDATE_SOURCE_KEY",
    "DATASET_NAME",
    "IMPLEMENTATION_SCOPE",
    "IMPLEMENTATION_STATE",
    "NEXT_REQUIRED_BOUNDARY",
    "PR39_SCHEMA_BLOB_SHA",
    "PR85_EVIDENCE_BLOB_SHA",
    "PR87_IMPLEMENTATION_BLOB_SHA",
    "PR88_PROTOCOL_BLOB_SHA",
    "PR88_PROTOCOL_SHA256",
    "PR88_PROTOCOL_SIZE",
    "REPOSITORY_MAIN_SHA",
    "SCHEMA_VERSION",
    "EliminatedTeamIdValueDomainStatus",
    "FotMobDataMatchesEliminatedTeamIdValueDomainAssessment",
    "FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError",
    "assess_fotmob_data_matches_eliminated_team_id_value_domain",
    "canonical_fotmob_data_matches_eliminated_team_id_value_domain_assessment_bytes",
    "sha256_fotmob_data_matches_eliminated_team_id_value_domain_assessment",
]
