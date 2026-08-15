"""Reusable reviewed adapter for ordinary-FT FotMob finished scores.

This adapter is deliberately narrow. It consumes two caller-supplied, provenance-
bound reviewed ``/api/data/matches`` captures, re-runs the reviewed structural
chain, applies the frozen PR83 repeat/stability requirements and the exact PR90
ordinary-FT reason gate, and emits only source-reported finished scores that pass
all of those gates.

It does not acquire network data, register a source capability, prove historical
coverage, infer regulation/extra-time/penalty/settlement semantics, or authorize
model, pricing, selection, production, or betting use.
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

import domain.fotmob_data_matches_eliminated_team_id_value_domain_extension as pr89
import domain.fotmob_data_matches_final_result_semantics_protocol as pr83
import domain.fotmob_data_matches_full_time_score_capability_promotion_assessment as pr94
import domain.fotmob_data_matches_status_reason_semantics_protocol as pr90
from domain.fotmob_data_matches_capture import (
    MAX_RESPONSE_BYTES,
    FotMobDataMatchesCaptureError,
    FotMobDataMatchesCaptureManifest,
    parse_utc_timestamp,
    serialize_utc,
    sha256_bytes,
    sha256_data_matches_capture_manifest,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-data-matches-ordinary-ft-finished-score-adapter-v1"
ADAPTER_SCOPE = "REUSABLE_REVIEWED_PROSPECTIVE_ORDINARY_FT_FINISHED_SCORE_PAIR_GATE_ONLY"
ADAPTER_STATE = "IMPLEMENTED_REUSABLE_PROSPECTIVE_GATE_NO_CAPABILITY_REGISTRATION"
REPOSITORY_MAIN_SHA = "c973dabcc43103a9c939706067ca23294f6870ad"
PARENT_SOURCE_KEY = "fotmob_data_matches_reviewed_catalog"
FUTURE_DERIVED_SOURCE_KEY = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"

PR83_PROTOCOL_SHA256 = "572dde2f5ba8e68c96188ec2df3cc1fdcfa554aa1023aa56e8b8f8b225d7194b"
PR83_PROTOCOL_SIZE = 3995
PR89_IMPLEMENTATION_REPOSITORY_MAIN_SHA = "df6b782e0e1b36c46089333a893a12f44e40fa07"
PR90_PROTOCOL_SHA256 = "08bbc2d1e53cfb1268ba71745ae80d9bc32f4bfad0f02d52225df936c7634f23"
PR90_PROTOCOL_SIZE = 5602
PR94_ASSESSMENT_SHA256 = "adfe1a6e0103a65c30ed19026940bfb5474c63dc44328b7c632ea8dbe15d2eb5"
PR94_ASSESSMENT_SIZE = 4568
PR94_PRIMARY_STATUS = "BLOCKED_REUSABLE_REVIEWED_SCORE_ADAPTER_NOT_IMPLEMENTED"

ORDINARY_FT_REASON_TUPLE = types.MappingProxyType(dict(pr90.ORDINARY_FT_REASON_TUPLE))
PENALTY_REASON_TUPLE = types.MappingProxyType(dict(pr90.PENALTY_REASON_TUPLE))
SEMANTIC_SCOPE_RULE = pr83.SEMANTIC_SCOPE_RULE
MINIMUM_REPEAT_SEPARATION_SECONDS = pr83.MINIMUM_REPEAT_SEPARATION_SECONDS

NEXT_REQUIRED_BOUNDARY = (
    "EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_ORDINARY_FT_FINISHED_SCORE_ADAPTER_VALIDATION"
)

_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "source_capability_registration_authorized",
        "source_capability_registry_update_performed",
        "parent_source_capability_mutation_authorized",
        "global_fotmob_full_time_score_capability_authorized",
        "historical_coverage_qualified",
        "status_reason_semantics_globally_qualified",
        "regulation_time_score_semantics_qualified",
        "extra_time_score_semantics_qualified",
        "penalty_score_semantics_qualified",
        "bookmaker_settlement_semantics_qualified",
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


class AdapterPairStatus(str, enum.Enum):
    QUALIFIED_WITH_ORDINARY_FT_SCORES = "QUALIFIED_WITH_ORDINARY_FT_SCORES"
    NO_QUALIFIED_ORDINARY_FT_SCORES = "NO_QUALIFIED_ORDINARY_FT_SCORES"
    BLOCKED_CAPTURE_LINEAGE_OR_REQUEST_IDENTITY = "BLOCKED_CAPTURE_LINEAGE_OR_REQUEST_IDENTITY"
    BLOCKED_CAPTURE_OBSERVATION_ORDER_OR_SEPARATION = (
        "BLOCKED_CAPTURE_OBSERVATION_ORDER_OR_SEPARATION"
    )
    BLOCKED_STRUCTURAL_REVALIDATION = "BLOCKED_STRUCTURAL_REVALIDATION"


class AdapterFixtureStatus(str, enum.Enum):
    QUALIFIED_ORDINARY_FT_SOURCE_REPORTED_FINISHED_SCORE = (
        "QUALIFIED_ORDINARY_FT_SOURCE_REPORTED_FINISHED_SCORE"
    )
    BLOCKED_INSUFFICIENT_REPEAT_OBSERVATIONS = "BLOCKED_INSUFFICIENT_REPEAT_OBSERVATIONS"
    BLOCKED_FIXTURE_IDENTITY_DRIFT = "BLOCKED_FIXTURE_IDENTITY_DRIFT"
    BLOCKED_SCORE_INVALID = "BLOCKED_SCORE_INVALID"
    BLOCKED_POST_FINISH_SCORE_INSTABILITY = "BLOCKED_POST_FINISH_SCORE_INSTABILITY"
    BLOCKED_REASON_TUPLE_UNREVIEWED = "BLOCKED_REASON_TUPLE_UNREVIEWED"
    BLOCKED_REASON_TUPLE_MISMATCH_OR_PARTIAL = "BLOCKED_REASON_TUPLE_MISMATCH_OR_PARTIAL"
    BLOCKED_AWARDED_RESULT_REQUIRES_SEPARATE_REVIEW = (
        "BLOCKED_AWARDED_RESULT_REQUIRES_SEPARATE_REVIEW"
    )
    BLOCKED_PEN_SCORE_PRESENT_REQUIRES_SEPARATE_REVIEW = (
        "BLOCKED_PEN_SCORE_PRESENT_REQUIRES_SEPARATE_REVIEW"
    )
    BLOCKED_PENALTY_REASON_REQUIRES_SEPARATE_SCORE_SEMANTICS = (
        "BLOCKED_PENALTY_REASON_REQUIRES_SEPARATE_SCORE_SEMANTICS"
    )


class FotMobDataMatchesOrdinaryFtFinishedScoreAdapterError(ValueError):
    """Raised when the capture pair cannot safely reach fixture-level review."""

    def __init__(self, status: AdapterPairStatus, message: str) -> None:
        if not isinstance(status, AdapterPairStatus):
            raise TypeError("status must be AdapterPairStatus")
        super().__init__(message)
        self.status = status


def _error(status: AdapterPairStatus, message: str) -> FotMobDataMatchesOrdinaryFtFinishedScoreAdapterError:
    return FotMobDataMatchesOrdinaryFtFinishedScoreAdapterError(status, message)


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _checked_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "adapter safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error(
            AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION,
            "all adapter safety values must remain exact False",
        )
    return _default_safety()


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise _error(AdapterPairStatus.BLOCKED_CAPTURE_LINEAGE_OR_REQUEST_IDENTITY, f"{label} must be datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise _error(
                AdapterPairStatus.BLOCKED_CAPTURE_LINEAGE_OR_REQUEST_IDENTITY,
                f"{label} must be timezone-aware",
            )
        return value.astimezone(datetime.timezone.utc)
    except FotMobDataMatchesOrdinaryFtFinishedScoreAdapterError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise _error(
            AdapterPairStatus.BLOCKED_CAPTURE_LINEAGE_OR_REQUEST_IDENTITY,
            f"{label} is invalid",
        ) from exc


def _verify_upstream() -> None:
    if (pr83.PROTOCOL_SHA256, pr83.PROTOCOL_SIZE) != (PR83_PROTOCOL_SHA256, PR83_PROTOCOL_SIZE):
        raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "PR83 protocol identity changed")
    if (pr90.PROTOCOL_SHA256, pr90.PROTOCOL_SIZE) != (PR90_PROTOCOL_SHA256, PR90_PROTOCOL_SIZE):
        raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "PR90 protocol identity changed")
    if pr89.REPOSITORY_MAIN_SHA != PR89_IMPLEMENTATION_REPOSITORY_MAIN_SHA:
        raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "PR89 implementation ancestry changed")
    if (pr94.ASSESSMENT_SHA256, pr94.ASSESSMENT_SIZE) != (
        PR94_ASSESSMENT_SHA256,
        PR94_ASSESSMENT_SIZE,
    ):
        raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "PR94 assessment identity changed")
    if pr94.PRIMARY_STATUS != PR94_PRIMARY_STATUS:
        raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "PR94 blocker status changed")
    if pr94.SMALLEST_MISSING_REVIEWED_BOUNDARY != (
        "BUILD_REVIEWED_FOTMOB_DATA_MATCHES_ORDINARY_FT_FINISHED_SCORE_ADAPTER"
    ):
        raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "PR94 next boundary changed")
    try:
        pr94_value = pr94.build_fotmob_data_matches_full_time_score_capability_promotion_assessment()
        pr94_bytes = pr94.canonical_fotmob_data_matches_full_time_score_capability_promotion_assessment_bytes(
            pr94_value
        )
    except Exception as exc:
        raise _error(
            AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION,
            "PR94 assessment ancestry no longer revalidates",
        ) from exc
    if hashlib.sha256(pr94_bytes).hexdigest() != PR94_ASSESSMENT_SHA256 or len(pr94_bytes) != PR94_ASSESSMENT_SIZE:
        raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "PR94 canonical assessment changed")

    capability = SOURCE_CAPABILITY_REGISTRY.get(PARENT_SOURCE_KEY)
    if capability is None:
        raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "parent reviewed source capability is missing")
    if capability.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "parent fixture identity is not confirmed")
    if capability.full_time_score is not CapabilityAvailability.NOT_CAPTURED:
        raise _error(
            AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION,
            "parent source must remain identity-only with full_time_score NOT_CAPTURED",
        )
    if capability.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "parent historical coverage changed")


def _validate_capture(
    raw_json: Any,
    source_manifest: Any,
    label: str,
) -> FotMobDataMatchesCaptureManifest:
    if type(raw_json) is not bytes or not raw_json or len(raw_json) > MAX_RESPONSE_BYTES:
        raise _error(
            AdapterPairStatus.BLOCKED_CAPTURE_LINEAGE_OR_REQUEST_IDENTITY,
            f"{label} raw_json must be non-empty exact bytes within the reviewed capture limit",
        )
    if not isinstance(source_manifest, FotMobDataMatchesCaptureManifest):
        raise _error(
            AdapterPairStatus.BLOCKED_CAPTURE_LINEAGE_OR_REQUEST_IDENTITY,
            f"{label} manifest must be the reviewed PR38 manifest type",
        )
    try:
        manifest = dataclasses.replace(source_manifest)
    except FotMobDataMatchesCaptureError as exc:
        raise _error(
            AdapterPairStatus.BLOCKED_CAPTURE_LINEAGE_OR_REQUEST_IDENTITY,
            f"{label} manifest does not revalidate",
        ) from exc
    if manifest.raw_size != len(raw_json) or manifest.raw_sha256 != sha256_bytes(raw_json):
        raise _error(
            AdapterPairStatus.BLOCKED_CAPTURE_LINEAGE_OR_REQUEST_IDENTITY,
            f"{label} raw bytes do not match manifest lineage",
        )
    if manifest.network_acquisition_performed is not True:
        raise _error(
            AdapterPairStatus.BLOCKED_CAPTURE_LINEAGE_OR_REQUEST_IDENTITY,
            f"{label} must be an actual reviewed network capture, not an internal projection",
        )
    return manifest


def _reason(value: Any) -> Mapping[str, str] | None:
    if value is None:
        return None
    if type(value) is not dict:
        return types.MappingProxyType({})
    keys = ("short", "shortKey", "long", "longKey")
    if set(value) != set(keys) or any(type(value.get(key)) is not str or not value.get(key) for key in keys):
        return types.MappingProxyType({})
    return types.MappingProxyType({key: value[key] for key in keys})


def _payload(raw_json: bytes) -> Mapping[str, Any]:
    try:
        payload = json.loads(raw_json.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "reviewed raw JSON cannot be decoded") from exc
    if type(payload) is not dict or type(payload.get("leagues")) is not list:
        raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "reviewed payload shape changed")
    return payload


def _terminal_index(payload: Mapping[str, Any], observed_at: datetime.datetime) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for league in payload["leagues"]:
        if type(league) is not dict or type(league.get("matches")) is not list:
            raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "reviewed league shape changed")
        for match in league["matches"]:
            if type(match) is not dict:
                raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "reviewed match shape changed")
            fixture_id = match.get("id")
            if type(fixture_id) is not int or fixture_id < 1 or fixture_id in result:
                raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "fixture id is invalid or duplicated")
            status = match.get("status")
            home = match.get("home")
            away = match.get("away")
            if not all(type(item) is dict for item in (status, home, away)):
                raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "reviewed match components changed")
            if status.get("finished") is not True or status.get("started") is not True or status.get("cancelled") is not False:
                continue
            kickoff_raw = status.get("utcTime")
            if type(kickoff_raw) is not str:
                raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "finished fixture kickoff is invalid")
            try:
                kickoff = parse_utc_timestamp(kickoff_raw, "status.utcTime")
            except Exception as exc:
                raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "finished fixture kickoff cannot be parsed") from exc
            if observed_at <= kickoff:
                continue
            league_id = match.get("leagueId")
            home_team_id = home.get("id")
            away_team_id = away.get("id")
            if any(type(value) is not int or value < 1 for value in (league_id, home_team_id, away_team_id)):
                raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "finished fixture identity is invalid")
            result[fixture_id] = {
                "fixture_id": fixture_id,
                "league_id": league_id,
                "home_team_id": home_team_id,
                "away_team_id": away_team_id,
                "kickoff": kickoff,
                "kickoff_raw": kickoff_raw,
                "home_score": home.get("score"),
                "away_score": away.get("score"),
                "reason": _reason(status.get("reason")) if "reason" in status else None,
                "awarded": status.get("awarded") if "awarded" in status else None,
                "home_pen_score_present": "penScore" in home,
                "away_pen_score_present": "penScore" in away,
            }
    return result


def _identity(item: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        item["fixture_id"],
        item["league_id"],
        item["home_team_id"],
        item["away_team_id"],
        item["kickoff_raw"],
    )


def _score_valid(item: Mapping[str, Any]) -> bool:
    return (
        type(item["home_score"]) is int
        and item["home_score"] >= 0
        and type(item["away_score"]) is int
        and item["away_score"] >= 0
    )


def _reason_dict(value: Mapping[str, str] | None) -> dict[str, str] | None:
    if value is None:
        return None
    return dict(value)


@dataclasses.dataclass(frozen=True)
class OrdinaryFtFinishedScore:
    fixture_id: int
    league_id: int
    home_team_id: int
    away_team_id: int
    kickoff_utc: datetime.datetime
    home_score: int
    away_score: int
    reason: Mapping[str, str]
    first_observed_at: datetime.datetime
    second_observed_at: datetime.datetime
    first_raw_sha256: str
    second_raw_sha256: str
    first_manifest_sha256: str
    second_manifest_sha256: str

    def __post_init__(self) -> None:
        for label, value in (
            ("fixture_id", self.fixture_id),
            ("league_id", self.league_id),
            ("home_team_id", self.home_team_id),
            ("away_team_id", self.away_team_id),
        ):
            if type(value) is not int or value < 1:
                raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, f"{label} must be a positive exact integer")
        for label, value in (("home_score", self.home_score), ("away_score", self.away_score)):
            if type(value) is not int or value < 0:
                raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, f"{label} must be a non-negative exact integer")
        if dict(self.reason) != dict(ORDINARY_FT_REASON_TUPLE):
            raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "qualified score escaped exact ordinary-FT reason tuple")
        object.__setattr__(self, "reason", types.MappingProxyType(dict(ORDINARY_FT_REASON_TUPLE)))
        object.__setattr__(self, "kickoff_utc", _utc(self.kickoff_utc, "kickoff_utc"))
        object.__setattr__(self, "first_observed_at", _utc(self.first_observed_at, "first_observed_at"))
        object.__setattr__(self, "second_observed_at", _utc(self.second_observed_at, "second_observed_at"))
        if self.second_observed_at <= self.first_observed_at:
            raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "qualified observation order changed")
        for label, value in (
            ("first_raw_sha256", self.first_raw_sha256),
            ("second_raw_sha256", self.second_raw_sha256),
            ("first_manifest_sha256", self.first_manifest_sha256),
            ("second_manifest_sha256", self.second_manifest_sha256),
        ):
            if type(value) is not str or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, f"{label} must be lowercase SHA-256")

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "league_id": self.league_id,
            "home_team_id": self.home_team_id,
            "away_team_id": self.away_team_id,
            "kickoff_utc": serialize_utc(self.kickoff_utc),
            "home_score": self.home_score,
            "away_score": self.away_score,
            "reason": dict(self.reason),
            "first_observed_at": serialize_utc(self.first_observed_at),
            "second_observed_at": serialize_utc(self.second_observed_at),
            "first_raw_sha256": self.first_raw_sha256,
            "second_raw_sha256": self.second_raw_sha256,
            "first_manifest_sha256": self.first_manifest_sha256,
            "second_manifest_sha256": self.second_manifest_sha256,
        }


@dataclasses.dataclass(frozen=True)
class FotMobDataMatchesOrdinaryFtFinishedScoreAdapterResult:
    schema_version: int
    dataset_name: str
    adapter_scope: str
    adapter_state: str
    pair_status: AdapterPairStatus
    request_date: str
    timezone: str
    ccode3: str
    first_raw_sha256: str
    second_raw_sha256: str
    first_manifest_sha256: str
    second_manifest_sha256: str
    first_observed_at: datetime.datetime
    second_observed_at: datetime.datetime
    observation_separation_microseconds: int
    first_pr89_assessment_sha256: str
    second_pr89_assessment_sha256: str
    terminal_candidate_union_count: int
    qualified_count: int
    blocked_fixture_ids_by_status: Mapping[str, tuple[int, ...]]
    qualified_scores: tuple[OrdinaryFtFinishedScore, ...]
    semantic_scope_rule: str
    source_capability_registration_performed: bool
    next_required_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "schema_version must remain exact integer 1")
        if self.dataset_name != DATASET_NAME or self.adapter_scope != ADAPTER_SCOPE or self.adapter_state != ADAPTER_STATE:
            raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "adapter identity changed")
        if not isinstance(self.pair_status, AdapterPairStatus):
            raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "pair_status must be AdapterPairStatus")
        if self.pair_status not in {
            AdapterPairStatus.QUALIFIED_WITH_ORDINARY_FT_SCORES,
            AdapterPairStatus.NO_QUALIFIED_ORDINARY_FT_SCORES,
        }:
            raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "successful result cannot carry pair-level blocker")
        if type(self.observation_separation_microseconds) is not int or self.observation_separation_microseconds < MINIMUM_REPEAT_SEPARATION_SECONDS * 1_000_000:
            raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "successful result has insufficient repeat separation")
        if type(self.terminal_candidate_union_count) is not int or self.terminal_candidate_union_count < 0:
            raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "terminal_candidate_union_count is invalid")
        if type(self.qualified_count) is not int or self.qualified_count < 0 or self.qualified_count != len(self.qualified_scores):
            raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "qualified_count disagrees with qualified_scores")
        if self.pair_status is AdapterPairStatus.QUALIFIED_WITH_ORDINARY_FT_SCORES and self.qualified_count < 1:
            raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "qualified pair status requires at least one score")
        if self.pair_status is AdapterPairStatus.NO_QUALIFIED_ORDINARY_FT_SCORES and self.qualified_count != 0:
            raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "no-qualified pair status cannot carry scores")
        if self.semantic_scope_rule != SEMANTIC_SCOPE_RULE:
            raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "semantic scope escaped PR83")
        if type(self.source_capability_registration_performed) is not bool or self.source_capability_registration_performed is not False:
            raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "adapter must not perform source capability registration")
        if self.next_required_boundary != NEXT_REQUIRED_BOUNDARY:
            raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "next boundary changed")
        if not isinstance(self.blocked_fixture_ids_by_status, Mapping):
            raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "blocked fixture mapping is invalid")
        frozen_blocked: dict[str, tuple[int, ...]] = {}
        seen: set[int] = set()
        for status, fixture_ids in self.blocked_fixture_ids_by_status.items():
            if status not in {item.value for item in AdapterFixtureStatus if item is not AdapterFixtureStatus.QUALIFIED_ORDINARY_FT_SOURCE_REPORTED_FINISHED_SCORE}:
                raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "blocked fixture status is outside adapter vocabulary")
            if type(fixture_ids) is not tuple or any(type(item) is not int or item < 1 for item in fixture_ids):
                raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "blocked fixture ids must be positive exact integers")
            if tuple(sorted(set(fixture_ids))) != fixture_ids:
                raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "blocked fixture ids must be unique and sorted")
            if seen.intersection(fixture_ids):
                raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "fixture cannot carry multiple terminal adapter dispositions")
            seen.update(fixture_ids)
            frozen_blocked[status] = fixture_ids
        qualified_ids = tuple(item.fixture_id for item in self.qualified_scores)
        if tuple(sorted(set(qualified_ids))) != qualified_ids:
            raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "qualified fixture ids must be unique and sorted")
        if seen.intersection(qualified_ids):
            raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "qualified fixture cannot also be blocked")
        if len(seen) + len(qualified_ids) != self.terminal_candidate_union_count:
            raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "fixture disposition counts do not cover candidate union")
        object.__setattr__(self, "blocked_fixture_ids_by_status", types.MappingProxyType(dict(frozen_blocked)))
        object.__setattr__(self, "qualified_scores", tuple(dataclasses.replace(item) for item in self.qualified_scores))
        object.__setattr__(self, "first_observed_at", _utc(self.first_observed_at, "first_observed_at"))
        object.__setattr__(self, "second_observed_at", _utc(self.second_observed_at, "second_observed_at"))
        object.__setattr__(self, "safety", _checked_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "adapter_scope": self.adapter_scope,
            "adapter_state": self.adapter_state,
            "pair_status": self.pair_status.value,
            "request_date": self.request_date,
            "timezone": self.timezone,
            "ccode3": self.ccode3,
            "first_raw_sha256": self.first_raw_sha256,
            "second_raw_sha256": self.second_raw_sha256,
            "first_manifest_sha256": self.first_manifest_sha256,
            "second_manifest_sha256": self.second_manifest_sha256,
            "first_observed_at": serialize_utc(self.first_observed_at),
            "second_observed_at": serialize_utc(self.second_observed_at),
            "observation_separation_microseconds": self.observation_separation_microseconds,
            "first_pr89_assessment_sha256": self.first_pr89_assessment_sha256,
            "second_pr89_assessment_sha256": self.second_pr89_assessment_sha256,
            "terminal_candidate_union_count": self.terminal_candidate_union_count,
            "qualified_count": self.qualified_count,
            "blocked_fixture_ids_by_status": {key: list(value) for key, value in sorted(self.blocked_fixture_ids_by_status.items())},
            "qualified_scores": [item.to_dict() for item in self.qualified_scores],
            "semantic_scope_rule": self.semantic_scope_rule,
            "source_capability_registration_performed": self.source_capability_registration_performed,
            "next_required_boundary": self.next_required_boundary,
            "safety": dict(self.safety),
        }


def adapt_fotmob_data_matches_ordinary_ft_finished_scores(
    first_raw_json: bytes,
    first_manifest: FotMobDataMatchesCaptureManifest,
    second_raw_json: bytes,
    second_manifest: FotMobDataMatchesCaptureManifest,
) -> FotMobDataMatchesOrdinaryFtFinishedScoreAdapterResult:
    """Apply the reusable reviewed ordinary-FT score gate to one capture pair."""

    _verify_upstream()
    first_manifest = _validate_capture(first_raw_json, first_manifest, "first")
    second_manifest = _validate_capture(second_raw_json, second_manifest, "second")

    if (first_manifest.request_date, first_manifest.timezone, first_manifest.ccode3) != (
        second_manifest.request_date,
        second_manifest.timezone,
        second_manifest.ccode3,
    ):
        raise _error(
            AdapterPairStatus.BLOCKED_CAPTURE_LINEAGE_OR_REQUEST_IDENTITY,
            "capture pair must share one exact request date/timezone/ccode3 identity",
        )
    first_manifest_sha = sha256_data_matches_capture_manifest(first_manifest)
    second_manifest_sha = sha256_data_matches_capture_manifest(second_manifest)
    if first_manifest.raw_sha256 == second_manifest.raw_sha256 or first_manifest_sha == second_manifest_sha:
        raise _error(
            AdapterPairStatus.BLOCKED_CAPTURE_LINEAGE_OR_REQUEST_IDENTITY,
            "capture pair must have distinct raw and manifest lineages",
        )
    separation = second_manifest.observed_at - first_manifest.observed_at
    separation_microseconds = (
        separation.days * 86_400_000_000
        + separation.seconds * 1_000_000
        + separation.microseconds
    )
    if second_manifest.observed_at <= first_manifest.observed_at or separation_microseconds < MINIMUM_REPEAT_SEPARATION_SECONDS * 1_000_000:
        raise _error(
            AdapterPairStatus.BLOCKED_CAPTURE_OBSERVATION_ORDER_OR_SEPARATION,
            "second capture must occur later and at least 300 seconds after first capture",
        )

    try:
        first_pr89 = pr89.assess_fotmob_data_matches_eliminated_team_id_value_domain(
            first_raw_json,
            first_manifest,
        )
        second_pr89 = pr89.assess_fotmob_data_matches_eliminated_team_id_value_domain(
            second_raw_json,
            second_manifest,
        )
    except Exception as exc:
        raise _error(
            AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION,
            "capture pair failed the reviewed PR89 structural chain",
        ) from exc
    qualified_structural = pr89.EliminatedTeamIdValueDomainStatus.QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN
    if first_pr89.status is not qualified_structural or second_pr89.status is not qualified_structural:
        raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "PR89 structural qualification changed")
    if first_pr89.status_reason_semantics_qualified or second_pr89.status_reason_semantics_qualified:
        raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "PR89 unexpectedly gained reason semantics")
    if first_pr89.final_result_semantics_qualified or second_pr89.final_result_semantics_qualified:
        raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "PR89 unexpectedly gained final-result semantics")

    first_pr89_sha = pr89.sha256_fotmob_data_matches_eliminated_team_id_value_domain_assessment(first_pr89)
    second_pr89_sha = pr89.sha256_fotmob_data_matches_eliminated_team_id_value_domain_assessment(second_pr89)
    first_index = _terminal_index(_payload(first_raw_json), first_manifest.observed_at)
    second_index = _terminal_index(_payload(second_raw_json), second_manifest.observed_at)

    qualified: list[OrdinaryFtFinishedScore] = []
    blocked: dict[str, list[int]] = {}

    def block(status: AdapterFixtureStatus, fixture_id: int) -> None:
        blocked.setdefault(status.value, []).append(fixture_id)

    for fixture_id in sorted(set(first_index) | set(second_index)):
        first = first_index.get(fixture_id)
        second = second_index.get(fixture_id)
        if first is None or second is None:
            block(AdapterFixtureStatus.BLOCKED_INSUFFICIENT_REPEAT_OBSERVATIONS, fixture_id)
            continue
        if _identity(first) != _identity(second):
            block(AdapterFixtureStatus.BLOCKED_FIXTURE_IDENTITY_DRIFT, fixture_id)
            continue
        if not _score_valid(first) or not _score_valid(second):
            block(AdapterFixtureStatus.BLOCKED_SCORE_INVALID, fixture_id)
            continue
        if (first["home_score"], first["away_score"]) != (second["home_score"], second["away_score"]):
            block(AdapterFixtureStatus.BLOCKED_POST_FINISH_SCORE_INSTABILITY, fixture_id)
            continue
        if _reason_dict(first["reason"]) != _reason_dict(second["reason"]):
            block(AdapterFixtureStatus.BLOCKED_REASON_TUPLE_MISMATCH_OR_PARTIAL, fixture_id)
            continue
        if _reason_dict(first["reason"]) == dict(PENALTY_REASON_TUPLE):
            block(AdapterFixtureStatus.BLOCKED_PENALTY_REASON_REQUIRES_SEPARATE_SCORE_SEMANTICS, fixture_id)
            continue
        if _reason_dict(first["reason"]) != dict(ORDINARY_FT_REASON_TUPLE):
            block(AdapterFixtureStatus.BLOCKED_REASON_TUPLE_UNREVIEWED, fixture_id)
            continue
        if first["awarded"] not in (None, False) or second["awarded"] not in (None, False):
            block(AdapterFixtureStatus.BLOCKED_AWARDED_RESULT_REQUIRES_SEPARATE_REVIEW, fixture_id)
            continue
        if (
            first["home_pen_score_present"]
            or first["away_pen_score_present"]
            or second["home_pen_score_present"]
            or second["away_pen_score_present"]
        ):
            block(AdapterFixtureStatus.BLOCKED_PEN_SCORE_PRESENT_REQUIRES_SEPARATE_REVIEW, fixture_id)
            continue
        qualified.append(
            OrdinaryFtFinishedScore(
                fixture_id=fixture_id,
                league_id=first["league_id"],
                home_team_id=first["home_team_id"],
                away_team_id=first["away_team_id"],
                kickoff_utc=first["kickoff"],
                home_score=first["home_score"],
                away_score=first["away_score"],
                reason=ORDINARY_FT_REASON_TUPLE,
                first_observed_at=first_manifest.observed_at,
                second_observed_at=second_manifest.observed_at,
                first_raw_sha256=first_manifest.raw_sha256,
                second_raw_sha256=second_manifest.raw_sha256,
                first_manifest_sha256=first_manifest_sha,
                second_manifest_sha256=second_manifest_sha,
            )
        )

    frozen_blocked = types.MappingProxyType(
        {key: tuple(sorted(value)) for key, value in sorted(blocked.items())}
    )
    pair_status = (
        AdapterPairStatus.QUALIFIED_WITH_ORDINARY_FT_SCORES
        if qualified
        else AdapterPairStatus.NO_QUALIFIED_ORDINARY_FT_SCORES
    )
    return FotMobDataMatchesOrdinaryFtFinishedScoreAdapterResult(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        adapter_scope=ADAPTER_SCOPE,
        adapter_state=ADAPTER_STATE,
        pair_status=pair_status,
        request_date=first_manifest.request_date,
        timezone=first_manifest.timezone,
        ccode3=first_manifest.ccode3,
        first_raw_sha256=first_manifest.raw_sha256,
        second_raw_sha256=second_manifest.raw_sha256,
        first_manifest_sha256=first_manifest_sha,
        second_manifest_sha256=second_manifest_sha,
        first_observed_at=first_manifest.observed_at,
        second_observed_at=second_manifest.observed_at,
        observation_separation_microseconds=separation_microseconds,
        first_pr89_assessment_sha256=first_pr89_sha,
        second_pr89_assessment_sha256=second_pr89_sha,
        terminal_candidate_union_count=len(set(first_index) | set(second_index)),
        qualified_count=len(qualified),
        blocked_fixture_ids_by_status=frozen_blocked,
        qualified_scores=tuple(qualified),
        semantic_scope_rule=SEMANTIC_SCOPE_RULE,
        source_capability_registration_performed=False,
        next_required_boundary=NEXT_REQUIRED_BOUNDARY,
        safety=_default_safety(),
    )


def canonical_fotmob_data_matches_ordinary_ft_finished_score_adapter_result_bytes(
    result: Any,
) -> bytes:
    if not isinstance(result, FotMobDataMatchesOrdinaryFtFinishedScoreAdapterResult):
        raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "result has wrong adapter type")
    try:
        return (
            json.dumps(
                result.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error(AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION, "adapter result serialization failed") from exc


def sha256_fotmob_data_matches_ordinary_ft_finished_score_adapter_result(result: Any) -> str:
    return hashlib.sha256(
        canonical_fotmob_data_matches_ordinary_ft_finished_score_adapter_result_bytes(result)
    ).hexdigest()


__all__ = [
    "ADAPTER_SCOPE",
    "ADAPTER_STATE",
    "DATASET_NAME",
    "FUTURE_DERIVED_SOURCE_KEY",
    "MINIMUM_REPEAT_SEPARATION_SECONDS",
    "NEXT_REQUIRED_BOUNDARY",
    "ORDINARY_FT_REASON_TUPLE",
    "PARENT_SOURCE_KEY",
    "PENALTY_REASON_TUPLE",
    "REPOSITORY_MAIN_SHA",
    "SCHEMA_VERSION",
    "SEMANTIC_SCOPE_RULE",
    "AdapterFixtureStatus",
    "AdapterPairStatus",
    "FotMobDataMatchesOrdinaryFtFinishedScoreAdapterError",
    "FotMobDataMatchesOrdinaryFtFinishedScoreAdapterResult",
    "OrdinaryFtFinishedScore",
    "adapt_fotmob_data_matches_ordinary_ft_finished_scores",
    "canonical_fotmob_data_matches_ordinary_ft_finished_score_adapter_result_bytes",
    "sha256_fotmob_data_matches_ordinary_ft_finished_score_adapter_result",
]
