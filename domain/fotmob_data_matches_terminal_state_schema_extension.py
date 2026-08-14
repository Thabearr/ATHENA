"""Implement the reviewed FotMob terminal-state structural schema extension.

PR #87 implements only the additive structural layer pre-registered by PR #86.
The frozen PR #39 schema remains unchanged. This module does not infer football
semantics, promote source capabilities, or authorize downstream modelling,
pricing, selection, production, or betting.
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import re
import types
from collections.abc import Mapping
from typing import Any

import domain.fotmob_data_matches_schema as pr39_schema
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
from domain.fotmob_data_matches_terminal_state_schema_extension_protocol import (
    BASE_HALFS_KEYS,
    BASE_STATUS_OPTIONAL_KEYS,
    BASE_STATUS_REQUIRED_KEYS,
    BASE_TEAM_KEYS,
    EXTENSION_HALFS_OPTIONAL_KEYS,
    EXTENSION_STATUS_OPTIONAL_KEYS,
    EXTENSION_TEAM_OPTIONAL_KEYS,
    LIVE_TIME_REQUIRED_KEYS,
    PROTOCOL_SHA256 as PR86_PROTOCOL_SHA256,
    PROTOCOL_SIZE as PR86_PROTOCOL_SIZE,
    STATUS_VOCABULARY,
    build_fotmob_data_matches_terminal_state_schema_extension_protocol,
    canonical_fotmob_data_matches_terminal_state_schema_extension_protocol_bytes,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-data-matches-terminal-state-schema-extension-v1"
IMPLEMENTATION_SCOPE = "REVIEWED_ADDITIVE_TERMINAL_STATE_STRUCTURAL_SCHEMA_ONLY"
IMPLEMENTATION_STATE = "IMPLEMENTED_STRUCTURAL_EXTENSION_NO_FINAL_RESULT_SEMANTICS"
REPOSITORY_MAIN_SHA = "11f34a1856d0cbb4b5f7a0b6b8c757fa8c07bbc9"
PR86_PROTOCOL_BLOB_SHA = "71b2f1a8add05929835d469df94396375a115391"
PR39_SCHEMA_BLOB_SHA = "4dfff0eb05335895c3ee0fcaa7b8da1299ea692f"
CANDIDATE_SOURCE_KEY = "fotmob_data_matches_reviewed_catalog"
NEXT_REQUIRED_BOUNDARY = (
    "PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_ELIMINATED_TEAM_ID_VALUE_DOMAIN_EXTENSION"
)

_BASE_TEAM_KEYS = frozenset(BASE_TEAM_KEYS)
_BASE_STATUS_REQUIRED_KEYS = frozenset(BASE_STATUS_REQUIRED_KEYS)
_BASE_STATUS_OPTIONAL_KEYS = frozenset(BASE_STATUS_OPTIONAL_KEYS)
_BASE_STATUS_KEYS = _BASE_STATUS_REQUIRED_KEYS | _BASE_STATUS_OPTIONAL_KEYS
_BASE_HALFS_KEYS = frozenset(BASE_HALFS_KEYS)
_EXTENSION_TEAM_KEYS = frozenset(EXTENSION_TEAM_OPTIONAL_KEYS)
_EXTENSION_STATUS_KEYS = frozenset(EXTENSION_STATUS_OPTIONAL_KEYS)
_EXTENSION_HALFS_KEYS = frozenset(EXTENSION_HALFS_OPTIONAL_KEYS)
_LIVE_TIME_KEYS = frozenset(LIVE_TIME_REQUIRED_KEYS)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)

_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "terminal_schema_extension_implementation_authorized",
        "terminal_schema_extension_qualified",
        "pr39_schema_mutation_authorized",
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


class TerminalStateSchemaExtensionStatus(str, enum.Enum):
    QUALIFIED_STRUCTURAL_TERMINAL_STATE_SCHEMA_EXTENSION = (
        "QUALIFIED_STRUCTURAL_TERMINAL_STATE_SCHEMA_EXTENSION"
    )
    BLOCKED_BASE_PR39_CONTRACT_DRIFT = "BLOCKED_BASE_PR39_CONTRACT_DRIFT"
    BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT = "BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT"
    BLOCKED_EXTRA_KEY_OUTSIDE_PRE_REGISTERED_SET = (
        "BLOCKED_EXTRA_KEY_OUTSIDE_PRE_REGISTERED_SET"
    )
    BLOCKED_EXTENSION_TYPE_OR_NULLABILITY_MISMATCH = (
        "BLOCKED_EXTENSION_TYPE_OR_NULLABILITY_MISMATCH"
    )
    BLOCKED_LIVE_TIME_SHAPE_MISMATCH = "BLOCKED_LIVE_TIME_SHAPE_MISMATCH"


if tuple(item.value for item in TerminalStateSchemaExtensionStatus) != STATUS_VOCABULARY:
    raise RuntimeError("PR87 status vocabulary differs from frozen PR86 protocol")


class FotMobDataMatchesTerminalStateSchemaExtensionError(ValueError):
    """Raised when the PR #86 structural extension fails closed."""

    def __init__(self, status: TerminalStateSchemaExtensionStatus, message: str) -> None:
        if not isinstance(status, TerminalStateSchemaExtensionStatus):
            raise TypeError("status must be TerminalStateSchemaExtensionStatus")
        super().__init__(message)
        self.status = status


def _error(
    status: TerminalStateSchemaExtensionStatus, message: str
) -> FotMobDataMatchesTerminalStateSchemaExtensionError:
    return FotMobDataMatchesTerminalStateSchemaExtensionError(status, message)


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _checked_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "safety keys mismatch",
        )
    if any(type(item) is not bool or item is not False for item in value.values()):
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "all PR87 safety values must be exact False",
        )
    return _default_safety()


def _sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            f"{label} must be exactly 64 lowercase hexadecimal characters",
        )
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            f"{label} must be a datetime",
        )
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise _error(
                TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
                f"{label} must be timezone-aware",
            )
        return value.astimezone(datetime.timezone.utc)
    except FotMobDataMatchesTerminalStateSchemaExtensionError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            f"{label} is invalid",
        ) from exc


def _request_identity(
    request_date: Any, timezone: Any, ccode3: Any
) -> tuple[str, str, str]:
    try:
        return (
            validate_request_date(request_date),
            validate_timezone(timezone),
            validate_ccode3(ccode3),
        )
    except FotMobDataMatchesProbeError as exc:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "assessment request identity is invalid",
        ) from exc


def _verify_frozen_ancestry() -> None:
    if tuple(sorted(pr39_schema.TEAM_KEYS)) != tuple(sorted(BASE_TEAM_KEYS)):
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "PR39 team-key contract changed",
        )
    if tuple(sorted(pr39_schema.STATUS_REQUIRED_KEYS)) != tuple(
        sorted(BASE_STATUS_REQUIRED_KEYS)
    ):
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "PR39 status-required contract changed",
        )
    if tuple(sorted(pr39_schema.STATUS_OPTIONAL_KEYS)) != tuple(
        sorted(BASE_STATUS_OPTIONAL_KEYS)
    ):
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "PR39 status-optional contract changed",
        )
    if tuple(sorted(pr39_schema.HALFS_KEYS)) != tuple(sorted(BASE_HALFS_KEYS)):
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "PR39 halfs-key contract changed",
        )
    try:
        protocol = build_fotmob_data_matches_terminal_state_schema_extension_protocol()
        exact = canonical_fotmob_data_matches_terminal_state_schema_extension_protocol_bytes(
            protocol
        )
    except Exception as exc:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            "PR86 protocol or its frozen PR85 ancestry no longer revalidates",
        ) from exc
    if (
        hashlib.sha256(exact).hexdigest() != PR86_PROTOCOL_SHA256
        or len(exact) != PR86_PROTOCOL_SIZE
    ):
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            "PR86 canonical protocol identity changed",
        )
    capability = SOURCE_CAPABILITY_REGISTRY.get(CANDIDATE_SOURCE_KEY)
    if capability is None:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            "reviewed data-matches source capability is missing",
        )
    if capability.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            "reviewed fixture identity premise changed",
        )
    if capability.full_time_score is not CapabilityAvailability.NOT_CAPTURED:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            "full-time-score capability premise changed",
        )
    if capability.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT,
            "historical-coverage premise changed",
        )


def _validate_source_input(
    raw_json: Any, source_manifest: Any
) -> FotMobDataMatchesCaptureManifest:
    if type(raw_json) is not bytes or not raw_json:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "raw_json must be non-empty exact bytes",
        )
    if len(raw_json) > MAX_RESPONSE_BYTES:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "raw_json exceeds capture limit",
        )
    if not isinstance(source_manifest, FotMobDataMatchesCaptureManifest):
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "source_manifest must be the reviewed PR38 manifest type",
        )
    try:
        manifest = dataclasses.replace(source_manifest)
    except FotMobDataMatchesCaptureError as exc:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "source manifest does not revalidate",
        ) from exc
    if manifest.raw_size != len(raw_json) or manifest.raw_sha256 != sha256_bytes(raw_json):
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "source raw bytes do not match manifest lineage",
        )
    return manifest


def _exact_nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_EXTENSION_TYPE_OR_NULLABILITY_MISMATCH,
            f"{label} must be an exact non-negative integer",
        )
    return value


def _exact_bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_EXTENSION_TYPE_OR_NULLABILITY_MISMATCH,
            f"{label} must be an exact bool",
        )
    return value


def _exact_str(value: Any, label: str) -> str:
    if type(value) is not str:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_EXTENSION_TYPE_OR_NULLABILITY_MISMATCH,
            f"{label} must be an exact string",
        )
    return value


def _require_no_unknown_keys(
    value: Any,
    *,
    allowed: frozenset[str],
    label: str,
) -> dict[str, Any]:
    if type(value) is not dict:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            f"{label} must be an object",
        )
    unknown = set(value) - allowed
    if unknown:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_EXTRA_KEY_OUTSIDE_PRE_REGISTERED_SET,
            f"{label} has keys outside the PR39 base plus PR86 extension",
        )
    return value


def _validate_live_time(value: Any, label: str) -> None:
    if type(value) is not dict:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_EXTENSION_TYPE_OR_NULLABILITY_MISMATCH,
            f"{label} must be an exact object and must not be null",
        )
    if set(value) != _LIVE_TIME_KEYS:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_LIVE_TIME_SHAPE_MISMATCH,
            f"{label} must contain exactly the seven pre-registered keys",
        )
    for key in ("addedTime", "basePeriod", "maxTime"):
        _exact_nonnegative_int(value[key], f"{label}.{key}")
    for key in ("long", "longKey", "short", "shortKey"):
        _exact_str(value[key], f"{label}.{key}")


def _validate_extension_fields_and_project(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, int], dict[str, int], dict[str, int], int]:
    if set(payload) != pr39_schema.TOP_LEVEL_KEYS:
        unknown = set(payload) - pr39_schema.TOP_LEVEL_KEYS
        if unknown:
            raise _error(
                TerminalStateSchemaExtensionStatus.BLOCKED_EXTRA_KEY_OUTSIDE_PRE_REGISTERED_SET,
                "top level has unreviewed keys",
            )
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "top level is missing PR39 keys",
        )
    leagues = payload.get("leagues")
    if type(leagues) is not list:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "payload.leagues must be a list",
        )

    projected = {"date": payload.get("date"), "leagues": []}
    team_counts = {key: 0 for key in EXTENSION_TEAM_OPTIONAL_KEYS}
    status_counts = {key: 0 for key in EXTENSION_STATUS_OPTIONAL_KEYS}
    halfs_counts = {key: 0 for key in EXTENSION_HALFS_OPTIONAL_KEYS}
    live_time_count = 0

    for league_index, raw_league in enumerate(leagues):
        league_label = f"leagues[{league_index}]"
        league = _require_no_unknown_keys(
            raw_league,
            allowed=pr39_schema.LEAGUE_ALLOWED_KEYS,
            label=league_label,
        )
        projected_league = dict(league)
        matches = league.get("matches")
        if type(matches) is not list:
            raise _error(
                TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
                f"{league_label}.matches must be a list",
            )
        projected_matches: list[dict[str, Any]] = []

        for match_index, raw_match in enumerate(matches):
            match_label = f"{league_label}.matches[{match_index}]"
            match = _require_no_unknown_keys(
                raw_match,
                allowed=pr39_schema.MATCH_KEYS,
                label=match_label,
            )
            projected_match = dict(match)

            for side in ("home", "away"):
                team_label = f"{match_label}.{side}"
                team = _require_no_unknown_keys(
                    match.get(side),
                    allowed=_BASE_TEAM_KEYS | _EXTENSION_TEAM_KEYS,
                    label=team_label,
                )
                projected_team = {
                    key: value for key, value in team.items() if key in _BASE_TEAM_KEYS
                }
                for key in EXTENSION_TEAM_OPTIONAL_KEYS:
                    if key in team:
                        _exact_nonnegative_int(team[key], f"{team_label}.{key}")
                        team_counts[key] += 1
                projected_match[side] = projected_team

            status_label = f"{match_label}.status"
            status = _require_no_unknown_keys(
                match.get("status"),
                allowed=_BASE_STATUS_KEYS | _EXTENSION_STATUS_KEYS,
                label=status_label,
            )
            projected_status = {
                key: value for key, value in status.items() if key in _BASE_STATUS_KEYS
            }

            for key in ("awarded", "ongoing"):
                if key in status:
                    _exact_bool(status[key], f"{status_label}.{key}")
                    status_counts[key] += 1
            for key in ("numberOfAwayRedCards", "numberOfHomeRedCards"):
                if key in status:
                    _exact_nonnegative_int(status[key], f"{status_label}.{key}")
                    status_counts[key] += 1
            if "scoreStr" in status:
                _exact_str(status["scoreStr"], f"{status_label}.scoreStr")
                status_counts["scoreStr"] += 1
            if "liveTime" in status:
                _validate_live_time(status["liveTime"], f"{status_label}.liveTime")
                status_counts["liveTime"] += 1
                live_time_count += 1

            halfs = status.get("halfs")
            halfs_label = f"{status_label}.halfs"
            halfs_value = _require_no_unknown_keys(
                halfs,
                allowed=_BASE_HALFS_KEYS | _EXTENSION_HALFS_KEYS,
                label=halfs_label,
            )
            projected_halfs = {
                key: value for key, value in halfs_value.items() if key in _BASE_HALFS_KEYS
            }
            if "secondHalfStarted" in halfs_value:
                _exact_str(
                    halfs_value["secondHalfStarted"],
                    f"{halfs_label}.secondHalfStarted",
                )
                halfs_counts["secondHalfStarted"] += 1
            projected_status["halfs"] = projected_halfs
            projected_match["status"] = projected_status
            projected_matches.append(projected_match)

        projected_league["matches"] = projected_matches
        projected["leagues"].append(projected_league)

    return projected, team_counts, status_counts, halfs_counts, live_time_count


def _non_null_eliminated_team_id_count(payload: dict[str, Any]) -> int:
    count = 0
    for league in payload.get("leagues", []):
        if type(league) is not dict:
            continue
        matches = league.get("matches", [])
        if type(matches) is not list:
            continue
        for match in matches:
            if type(match) is dict and match.get("eliminatedTeamId") is not None:
                count += 1
    return count


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
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "PR39 base projection serialization failed",
        ) from exc


def _projected_manifest(
    source_manifest: FotMobDataMatchesCaptureManifest, projected_raw: bytes
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
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "internal PR39 projection manifest failed validation",
        ) from exc


@dataclasses.dataclass(frozen=True)
class FotMobDataMatchesTerminalStateSchemaExtensionAssessment:
    schema_version: int
    dataset_name: str
    implementation_scope: str
    implementation_state: str
    status: TerminalStateSchemaExtensionStatus
    source_capture_manifest_sha256: str
    source_raw_sha256: str
    source_raw_size: int
    source_observed_at: datetime.datetime
    request_date: str
    timezone: str
    ccode3: str
    pr39_projection_assessment_sha256: str
    pr39_projection_assessment_size: int
    match_count: int
    team_extension_occurrences: Mapping[str, int]
    status_extension_occurrences: Mapping[str, int]
    halfs_extension_occurrences: Mapping[str, int]
    live_time_occurrence_count: int
    reason_semantics_qualified: bool
    final_result_semantics_qualified: bool
    next_required_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        try:
            if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
                raise _error(
                    TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
                    "schema_version must be exact integer 1",
                )
            if self.dataset_name != DATASET_NAME:
                raise _error(
                    TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
                    "dataset_name mismatch",
                )
            if self.implementation_scope != IMPLEMENTATION_SCOPE:
                raise _error(
                    TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
                    "implementation_scope mismatch",
                )
            if self.implementation_state != IMPLEMENTATION_STATE:
                raise _error(
                    TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
                    "implementation_state mismatch",
                )
            if (
                self.status
                is not TerminalStateSchemaExtensionStatus.QUALIFIED_STRUCTURAL_TERMINAL_STATE_SCHEMA_EXTENSION
            ):
                raise _error(
                    TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
                    "successful assessment must carry the exact qualified structural status",
                )
            manifest_sha = _sha256(
                self.source_capture_manifest_sha256,
                "source_capture_manifest_sha256",
            )
            raw_sha = _sha256(self.source_raw_sha256, "source_raw_sha256")
            projection_sha = _sha256(
                self.pr39_projection_assessment_sha256,
                "pr39_projection_assessment_sha256",
            )
            if (
                type(self.source_raw_size) is not int
                or not 0 < self.source_raw_size <= MAX_RESPONSE_BYTES
            ):
                raise _error(
                    TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
                    "source_raw_size must be an exact positive integer within capture limit",
                )
            if (
                type(self.pr39_projection_assessment_size) is not int
                or self.pr39_projection_assessment_size <= 0
            ):
                raise _error(
                    TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
                    "pr39_projection_assessment_size must be an exact positive integer",
                )
            if type(self.match_count) is not int or self.match_count < 0:
                raise _error(
                    TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
                    "match_count must be an exact non-negative integer",
                )
            if (
                type(self.live_time_occurrence_count) is not int
                or self.live_time_occurrence_count < 0
                or self.live_time_occurrence_count > self.match_count
            ):
                raise _error(
                    TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
                    "live_time_occurrence_count is inconsistent with match_count",
                )
            observed_at = _utc(self.source_observed_at, "source_observed_at")
            request_date, timezone, ccode3 = _request_identity(
                self.request_date, self.timezone, self.ccode3
            )
            for value, keys, label, maximum in (
                (
                    self.team_extension_occurrences,
                    _EXTENSION_TEAM_KEYS,
                    "team_extension_occurrences",
                    self.match_count * 2,
                ),
                (
                    self.status_extension_occurrences,
                    _EXTENSION_STATUS_KEYS,
                    "status_extension_occurrences",
                    self.match_count,
                ),
                (
                    self.halfs_extension_occurrences,
                    _EXTENSION_HALFS_KEYS,
                    "halfs_extension_occurrences",
                    self.match_count,
                ),
            ):
                if not isinstance(value, Mapping) or set(value) != keys:
                    raise _error(
                        TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
                        f"{label} keys mismatch",
                    )
                if any(
                    type(item) is not int or item < 0 or item > maximum
                    for item in value.values()
                ):
                    raise _error(
                        TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
                        f"{label} values are inconsistent with match_count",
                    )
            if self.status_extension_occurrences["liveTime"] != self.live_time_occurrence_count:
                raise _error(
                    TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
                    "liveTime occurrence counts disagree",
                )
            if (
                type(self.reason_semantics_qualified) is not bool
                or self.reason_semantics_qualified
            ):
                raise _error(
                    TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
                    "reason semantics must remain exact False",
                )
            if (
                type(self.final_result_semantics_qualified) is not bool
                or self.final_result_semantics_qualified
            ):
                raise _error(
                    TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
                    "final-result semantics must remain exact False",
                )
            if self.next_required_boundary != NEXT_REQUIRED_BOUNDARY:
                raise _error(
                    TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
                    "next boundary mismatch",
                )
            object.__setattr__(self, "source_capture_manifest_sha256", manifest_sha)
            object.__setattr__(self, "source_raw_sha256", raw_sha)
            object.__setattr__(
                self, "pr39_projection_assessment_sha256", projection_sha
            )
            object.__setattr__(self, "source_observed_at", observed_at)
            object.__setattr__(self, "request_date", request_date)
            object.__setattr__(self, "timezone", timezone)
            object.__setattr__(self, "ccode3", ccode3)
            object.__setattr__(
                self,
                "team_extension_occurrences",
                types.MappingProxyType(dict(self.team_extension_occurrences)),
            )
            object.__setattr__(
                self,
                "status_extension_occurrences",
                types.MappingProxyType(dict(self.status_extension_occurrences)),
            )
            object.__setattr__(
                self,
                "halfs_extension_occurrences",
                types.MappingProxyType(dict(self.halfs_extension_occurrences)),
            )
            object.__setattr__(self, "safety", _checked_safety(self.safety))
        except FotMobDataMatchesTerminalStateSchemaExtensionError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise _error(
                TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
                f"invalid terminal-state extension assessment: {type(exc).__name__}",
            ) from exc

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
            "pr39_projection_assessment_sha256": self.pr39_projection_assessment_sha256,
            "pr39_projection_assessment_size": self.pr39_projection_assessment_size,
            "match_count": self.match_count,
            "team_extension_occurrences": dict(self.team_extension_occurrences),
            "status_extension_occurrences": dict(self.status_extension_occurrences),
            "halfs_extension_occurrences": dict(self.halfs_extension_occurrences),
            "live_time_occurrence_count": self.live_time_occurrence_count,
            "reason_semantics_qualified": self.reason_semantics_qualified,
            "final_result_semantics_qualified": self.final_result_semantics_qualified,
            "next_required_boundary": self.next_required_boundary,
            "safety": dict(self.safety),
        }


def assess_fotmob_data_matches_terminal_state_schema_extension(
    raw_json: bytes,
    source_manifest: FotMobDataMatchesCaptureManifest,
) -> FotMobDataMatchesTerminalStateSchemaExtensionAssessment:
    """Validate the PR39 base contract plus the exact PR86 additive key layer."""

    _verify_frozen_ancestry()
    manifest = _validate_source_input(raw_json, source_manifest)
    try:
        payload = pr39_schema._strict_response_json(raw_json)
    except pr39_schema.FotMobDataMatchesSchemaError as exc:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "source JSON does not satisfy PR39 strict JSON parsing",
        ) from exc

    (
        projected_payload,
        team_counts,
        status_counts,
        halfs_counts,
        live_time_count,
    ) = _validate_extension_fields_and_project(payload)

    non_null_eliminated_team_id_count = _non_null_eliminated_team_id_count(
        projected_payload
    )
    if non_null_eliminated_team_id_count:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "PR39 base projection contains "
            f"{non_null_eliminated_team_id_count} non-null eliminatedTeamId value(s); "
            "PR39 V1 requires null",
        )

    projected_raw = _canonical_projection(projected_payload)
    projected_manifest = _projected_manifest(manifest, projected_raw)

    try:
        base_assessment = pr39_schema.assess_fotmob_data_matches_schema(
            projected_raw, projected_manifest
        )
        base_bytes = pr39_schema.canonical_data_matches_schema_assessment_bytes(
            base_assessment
        )
    except pr39_schema.FotMobDataMatchesSchemaError as exc:
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "PR39 base projection failed the frozen PR39 assessment",
        ) from exc

    return FotMobDataMatchesTerminalStateSchemaExtensionAssessment(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        implementation_scope=IMPLEMENTATION_SCOPE,
        implementation_state=IMPLEMENTATION_STATE,
        status=TerminalStateSchemaExtensionStatus.QUALIFIED_STRUCTURAL_TERMINAL_STATE_SCHEMA_EXTENSION,
        source_capture_manifest_sha256=sha256_data_matches_capture_manifest(manifest),
        source_raw_sha256=manifest.raw_sha256,
        source_raw_size=manifest.raw_size,
        source_observed_at=manifest.observed_at,
        request_date=manifest.request_date,
        timezone=manifest.timezone,
        ccode3=manifest.ccode3,
        pr39_projection_assessment_sha256=hashlib.sha256(base_bytes).hexdigest(),
        pr39_projection_assessment_size=len(base_bytes),
        match_count=base_assessment.match_count,
        team_extension_occurrences=team_counts,
        status_extension_occurrences=status_counts,
        halfs_extension_occurrences=halfs_counts,
        live_time_occurrence_count=live_time_count,
        reason_semantics_qualified=False,
        final_result_semantics_qualified=False,
        next_required_boundary=NEXT_REQUIRED_BOUNDARY,
        safety=_default_safety(),
    )


def canonical_fotmob_data_matches_terminal_state_schema_extension_assessment_bytes(
    assessment: Any,
) -> bytes:
    if not isinstance(
        assessment, FotMobDataMatchesTerminalStateSchemaExtensionAssessment
    ):
        raise _error(
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "assessment must be FotMobDataMatchesTerminalStateSchemaExtensionAssessment",
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
            TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT,
            "assessment serialization failed",
        ) from exc


def sha256_fotmob_data_matches_terminal_state_schema_extension_assessment(
    assessment: Any,
) -> str:
    return hashlib.sha256(
        canonical_fotmob_data_matches_terminal_state_schema_extension_assessment_bytes(
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
    "PR86_PROTOCOL_BLOB_SHA",
    "REPOSITORY_MAIN_SHA",
    "SCHEMA_VERSION",
    "TerminalStateSchemaExtensionStatus",
    "FotMobDataMatchesTerminalStateSchemaExtensionAssessment",
    "FotMobDataMatchesTerminalStateSchemaExtensionError",
    "assess_fotmob_data_matches_terminal_state_schema_extension",
    "canonical_fotmob_data_matches_terminal_state_schema_extension_assessment_bytes",
    "sha256_fotmob_data_matches_terminal_state_schema_extension_assessment",
]
