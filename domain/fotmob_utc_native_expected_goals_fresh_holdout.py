"""Implement PR #148's prospective UTC-native xG fresh-holdout core.

This module is deliberately offline and research-only. It qualifies exact
provider-native fixture identity from caller-supplied reviewed FotMob captures,
selects the frozen pre-kickoff observation, reconstructs the exact reviewed
UTC-native five-feature state from the immutable legacy bootstrap plus reviewed
fresh legacy settlements, seals the frozen native/Elo/calibrated xG rates, and
binds reviewed ordinary-FT settlement evidence. It performs no network
request, installs no scheduler, and grants no production/BET authority.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import hashlib
import json
import math
import types
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import domain.fotmob_data_matches_capture as capture_contract
import domain.fotmob_data_matches_ordinary_ft_finished_score_adapter as score_adapter
import domain.fotmob_fixture_candidates as fixture_candidates
import domain.fotmob_utc_native_expected_goals_fresh_holdout_calibration_competition_protocol as pr148
import domain.fotmob_utc_native_successor_feature_construction_qualification as utc_features


IMPLEMENTATION_STATE = (
    "IMPLEMENTED_REVIEWED_FRESH_HOLDOUT_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_"
    "CALIBRATION_AND_COMPETITION_IDENTITY_FOLLOWUP_NOT_ACTIVATED"
)
NEXT_REQUIRED_BOUNDARY = (
    "INSTALL_REVIEWED_FRESH_HOLDOUT_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_"
    "COLLECTION_CONTROL"
)

PR148_PROTOCOL_BLOB_SHA = "9f45e17603a2678741ccc596d2542a0c6e29fa6c"
UTC_FEATURE_CONSTRUCTOR_BLOB_SHA = "9c9e424791b65292f7bbe8849b3214c140834889"
FIXTURE_CANDIDATE_BLOB_SHA = "a3434951e87cfbd90dd2c43cccd413e7edfb08e0"
CAPTURE_CONTRACT_BLOB_SHA = "ca2149395de868104666620173b55a880b10c729"
ORDINARY_FT_ADAPTER_BLOB_SHA = "868563206e09010fce74b4ba7954028930baad54"

BOOTSTRAP_PROJECTION_SHA256 = "e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2"
BOOTSTRAP_PROJECTION_SIZE = 10_545_099
BOOTSTRAP_PROJECTION_ROWS = 21_326
SOURCE_NAMESPACE = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"

SAFETY_KEYS = tuple(sorted(pr148.SAFETY_KEYS))


class FotMobFreshHoldoutError(RuntimeError):
    """Raised when the reviewed prospective holdout cannot fail closed."""


class PredictionDisposition(str, enum.Enum):
    SEALED_COMPLETE_CASE = "SEALED_COMPLETE_CASE"
    MISSING_REVIEWED_FEATURES = "MISSING_REVIEWED_FEATURES"


class HoldoutBoundaryDecision(str, enum.Enum):
    OPEN_BEFORE_MINIMUM_GATE = "OPEN_BEFORE_MINIMUM_GATE"
    OPEN_WAITING_FOR_COUNT_ONLY_COVERAGE = "OPEN_WAITING_FOR_COUNT_ONLY_COVERAGE"
    CLOSE_COUNT_ONLY_COVERAGE_QUALIFIED = "CLOSE_COUNT_ONLY_COVERAGE_QUALIFIED"
    CLOSE_INSUFFICIENT_COVERAGE_NO_SUCCESSOR_DECISION = (
        "FRESH_HOLDOUT_INSUFFICIENT_COVERAGE_NO_SUCCESSOR_DECISION"
    )


def _error(message: str) -> FotMobFreshHoldoutError:
    return FotMobFreshHoldoutError(message)


def _canonical(value: Any) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("canonical serialization failed") from exc
    return (text + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    if type(value) is not bytes:
        raise _error("SHA-256 input must be exact bytes")
    return hashlib.sha256(value).hexdigest()


def _sha256(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise _error(f"{label} must be exactly 64 lowercase hexadecimal characters")
    return value


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 1:
        raise _error(f"{label} must be an exact positive integer")
    return value


def _non_negative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise _error(f"{label} must be an exact non-negative integer")
    return value


def _text(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise _error(f"{label} must be exact non-empty trimmed text")
    return value


def _utc(value: Any, label: str) -> dt.datetime:
    if type(value) is not dt.datetime:
        raise _error(f"{label} must be an exact datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise _error(f"{label} must be timezone-aware")
    try:
        return value.astimezone(dt.timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error(f"{label} is invalid") from exc


def _parse_utc(value: Any, label: str) -> dt.datetime:
    if type(value) is not str or not value.endswith("Z") or value != value.strip():
        raise _error(f"{label} must be exact UTC Z text")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise _error(f"{label} is malformed") from exc
    return _utc(parsed, label)


def _utc_text(value: dt.datetime) -> str:
    return _utc(value, "timestamp").isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _holdout_start(value: Any) -> dt.datetime:
    start = _utc(value, "holdout_start")
    if start.time() != dt.time.min:
        raise _error("holdout_start must be an exact UTC midnight")
    floor = _parse_utc(pr148.FRESH_HOLDOUT_NOT_BEFORE_UTC, "not_before_utc")
    if start < floor:
        raise _error("holdout_start precedes the frozen not-before boundary")
    return start


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in SAFETY_KEYS})


def verify_reviewed_dependencies() -> None:
    """Fail closed if any frozen implementation dependency moved."""
    protocol = pr148.build_fresh_holdout_home_calibration_competition_identity_protocol()
    protocol_raw = pr148.canonical_fresh_holdout_home_calibration_competition_identity_protocol_bytes(
        protocol
    )
    if (_sha256_bytes(protocol_raw), len(protocol_raw)) != (
        pr148.PROTOCOL_SHA256,
        pr148.PROTOCOL_SIZE,
    ):
        raise _error("PR148 canonical protocol identity changed")
    if pr148.NEXT_REQUIRED_BOUNDARY != (
        "IMPLEMENT_REVIEWED_FRESH_HOLDOUT_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_"
        "CALIBRATION_AND_COMPETITION_IDENTITY_FOLLOWUP"
    ):
        raise _error("PR148 next boundary changed")
    if any(protocol["safety"].values()):
        raise _error("PR148 downstream authority changed")

    pins = (
        (Path(pr148.__file__), PR148_PROTOCOL_BLOB_SHA, "PR148 protocol"),
        (Path(utc_features.__file__), UTC_FEATURE_CONSTRUCTOR_BLOB_SHA, "UTC feature constructor"),
        (Path(fixture_candidates.__file__), FIXTURE_CANDIDATE_BLOB_SHA, "fixture candidate builder"),
        (Path(capture_contract.__file__), CAPTURE_CONTRACT_BLOB_SHA, "capture contract"),
        (Path(score_adapter.__file__), ORDINARY_FT_ADAPTER_BLOB_SHA, "ordinary-FT adapter"),
    )
    try:
        for path, expected, label in pins:
            if _git_blob_sha(path) != expected:
                raise _error(f"{label} implementation blob changed")
    except OSError as exc:
        raise _error("could not verify reviewed dependency blobs") from exc


@dataclasses.dataclass(frozen=True)
class QualifiedCaptureFixture:
    fixture_id: int
    provider_primary_id: int
    wrapper_id: int
    home_team_id: int
    away_team_id: int
    kickoff_utc: dt.datetime
    capture_observed_at: dt.datetime
    capture_manifest_sha256: str
    capture_raw_sha256: str

    def __post_init__(self) -> None:
        for label in (
            "fixture_id",
            "provider_primary_id",
            "wrapper_id",
            "home_team_id",
            "away_team_id",
        ):
            object.__setattr__(self, label, _positive_int(getattr(self, label), label))
        if self.home_team_id == self.away_team_id:
            raise _error("fixture cannot use one team twice")
        object.__setattr__(self, "kickoff_utc", _utc(self.kickoff_utc, "kickoff_utc"))
        object.__setattr__(
            self,
            "capture_observed_at",
            _utc(self.capture_observed_at, "capture_observed_at"),
        )
        object.__setattr__(
            self,
            "capture_manifest_sha256",
            _sha256(self.capture_manifest_sha256, "capture_manifest_sha256"),
        )
        object.__setattr__(
            self,
            "capture_raw_sha256",
            _sha256(self.capture_raw_sha256, "capture_raw_sha256"),
        )

    def identity(self) -> tuple[Any, ...]:
        return (
            self.fixture_id,
            self.provider_primary_id,
            self.wrapper_id,
            self.home_team_id,
            self.away_team_id,
            self.kickoff_utc,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "provider_primary_id": self.provider_primary_id,
            "wrapper_id": self.wrapper_id,
            "home_team_id": self.home_team_id,
            "away_team_id": self.away_team_id,
            "kickoff_utc": _utc_text(self.kickoff_utc),
            "capture_observed_at": _utc_text(self.capture_observed_at),
            "capture_manifest_sha256": self.capture_manifest_sha256,
            "capture_raw_sha256": self.capture_raw_sha256,
        }


@dataclasses.dataclass(frozen=True)
class FreshHistoryResult:
    fixture_identifier: str
    home_team_id: int
    away_team_id: int
    kickoff_utc: dt.datetime
    home_goals: int
    away_goals: int
    observed_at: dt.datetime
    evidence_sha256: str
    evidence_reference: str
    provider_primary_id: int | None
    source_kind: str

    def __post_init__(self) -> None:
        fixture = _text(self.fixture_identifier, "fixture_identifier")
        if not fixture.isdigit() or int(fixture) < 1:
            raise _error("fixture_identifier must be a positive decimal source id")
        object.__setattr__(self, "fixture_identifier", fixture)
        object.__setattr__(self, "home_team_id", _positive_int(self.home_team_id, "home_team_id"))
        object.__setattr__(self, "away_team_id", _positive_int(self.away_team_id, "away_team_id"))
        if self.home_team_id == self.away_team_id:
            raise _error("history fixture cannot use one team twice")
        object.__setattr__(self, "kickoff_utc", _utc(self.kickoff_utc, "kickoff_utc"))
        object.__setattr__(self, "home_goals", _non_negative_int(self.home_goals, "home_goals"))
        object.__setattr__(self, "away_goals", _non_negative_int(self.away_goals, "away_goals"))
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "observed_at"))
        if self.observed_at <= self.kickoff_utc:
            raise _error("history result must be observed strictly after kickoff")
        object.__setattr__(self, "evidence_sha256", _sha256(self.evidence_sha256, "evidence_sha256"))
        object.__setattr__(self, "evidence_reference", _text(self.evidence_reference, "evidence_reference"))
        source = _text(self.source_kind, "source_kind")
        if source == "REVIEWED_PR119_BOOTSTRAP":
            if self.provider_primary_id is not None:
                raise _error("exact bootstrap rows must not invent per-row primaryId")
        elif source == "FRESH_REVIEWED_ORDINARY_FT_LEGACY_UPDATE":
            primary = _positive_int(self.provider_primary_id, "provider_primary_id")
            if primary not in pr148.LEGACY_PRIMARY_IDS:
                raise _error("fresh history state update escaped frozen legacy primary IDs")
            object.__setattr__(self, "provider_primary_id", primary)
        else:
            raise _error("history source_kind is outside reviewed vocabulary")
        object.__setattr__(self, "source_kind", source)

    def constructor_row(self) -> dict[str, Any]:
        return {
            "source_namespace": SOURCE_NAMESPACE,
            "fixture_identifier": self.fixture_identifier,
            "kickoff_utc": _utc_text(self.kickoff_utc),
            "home_team_identifier": str(self.home_team_id),
            "away_team_identifier": str(self.away_team_id),
            "home_goals": self.home_goals,
            "away_goals": self.away_goals,
            "evidence_sha256": self.evidence_sha256,
            "evidence_reference": self.evidence_reference,
        }


@dataclasses.dataclass(frozen=True)
class FreshHistoryLedger:
    bootstrap_projection_sha256: str
    bootstrap_projection_size: int
    bootstrap_row_count: int
    rows: tuple[FreshHistoryResult, ...]

    def __post_init__(self) -> None:
        if self.bootstrap_projection_sha256 != BOOTSTRAP_PROJECTION_SHA256:
            raise _error("history ledger bootstrap SHA-256 changed")
        if self.bootstrap_projection_size != BOOTSTRAP_PROJECTION_SIZE:
            raise _error("history ledger bootstrap size changed")
        if self.bootstrap_row_count != BOOTSTRAP_PROJECTION_ROWS:
            raise _error("history ledger bootstrap row count changed")
        if type(self.rows) is not tuple or any(type(item) is not FreshHistoryResult for item in self.rows):
            raise _error("history ledger rows must be immutable FreshHistoryResult values")
        if len(self.rows) < BOOTSTRAP_PROJECTION_ROWS:
            raise _error("history ledger cannot omit reviewed bootstrap rows")
        copied = tuple(dataclasses.replace(item) for item in self.rows)
        bootstrap = copied[:BOOTSTRAP_PROJECTION_ROWS]
        fresh_rows = copied[BOOTSTRAP_PROJECTION_ROWS:]
        if any(item.source_kind != "REVIEWED_PR119_BOOTSTRAP" for item in bootstrap):
            raise _error("history ledger bootstrap prefix source kind changed")
        if any(item.source_kind != "FRESH_REVIEWED_ORDINARY_FT_LEGACY_UPDATE" for item in fresh_rows):
            raise _error("history ledger fresh suffix escaped reviewed legacy updates")
        fixture_ids = tuple(item.fixture_identifier for item in copied)
        if len(set(fixture_ids)) != len(fixture_ids):
            raise _error("history ledger fixture identity duplicated")
        object.__setattr__(self, "rows", copied)


@dataclasses.dataclass(frozen=True)
class SealedFreshPrediction:
    schema_version: int
    implementation_state: str
    protocol_sha256: str
    holdout_start_utc: dt.datetime
    fixture: QualifiedCaptureFixture
    history_prefix_sha256: str
    history_prefix_count: int
    feature_projection_sha256: str
    features: Mapping[str, float]
    rates: Mapping[str, float]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.schema_version != 1 or self.implementation_state != IMPLEMENTATION_STATE:
            raise _error("sealed prediction identity changed")
        if self.protocol_sha256 != pr148.PROTOCOL_SHA256:
            raise _error("sealed prediction protocol identity changed")
        start = _holdout_start(self.holdout_start_utc)
        object.__setattr__(self, "holdout_start_utc", start)
        if type(self.fixture) is not QualifiedCaptureFixture:
            raise _error("sealed prediction fixture type mismatch")
        fixture = dataclasses.replace(self.fixture)
        if fixture.capture_observed_at < start or fixture.kickoff_utc < start:
            raise _error("sealed prediction escaped resolved holdout start")
        if not (
            fixture.kickoff_utc - dt.timedelta(hours=24)
            <= fixture.capture_observed_at
            <= fixture.kickoff_utc - dt.timedelta(minutes=60)
        ):
            raise _error("sealed prediction capture escaped frozen pre-kickoff window")
        object.__setattr__(self, "fixture", fixture)
        object.__setattr__(
            self,
            "history_prefix_sha256",
            _sha256(self.history_prefix_sha256, "history_prefix_sha256"),
        )
        if type(self.history_prefix_count) is not int or self.history_prefix_count < 0:
            raise _error("history_prefix_count must be a non-negative integer")
        object.__setattr__(
            self,
            "feature_projection_sha256",
            _sha256(self.feature_projection_sha256, "feature_projection_sha256"),
        )
        expected_features = {"home_elo", "away_elo", "home_form", "away_form", "fatigue"}
        if not isinstance(self.features, Mapping) or set(self.features) != expected_features:
            raise _error("sealed prediction feature set changed")
        frozen_features: dict[str, float] = {}
        for key, value in self.features.items():
            if type(value) not in (int, float) or not math.isfinite(float(value)):
                raise _error(f"sealed feature {key} must be finite numeric")
            frozen_features[key] = float(value)
        object.__setattr__(self, "features", types.MappingProxyType(frozen_features))
        expected_rates = {
            "native_home",
            "native_away",
            "elo_only_home",
            "elo_only_away",
            "calibrated_home",
            "calibrated_away",
        }
        if not isinstance(self.rates, Mapping) or set(self.rates) != expected_rates:
            raise _error("sealed prediction rate set changed")
        frozen_rates: dict[str, float] = {}
        for key, value in self.rates.items():
            if type(value) is not float or not math.isfinite(value) or value <= 0.0:
                raise _error(f"sealed rate {key} must be a finite positive float")
            frozen_rates[key] = value
        if frozen_rates["calibrated_away"] != frozen_rates["native_away"]:
            raise _error("away calibration must remain exact native identity")
        object.__setattr__(self, "rates", types.MappingProxyType(frozen_rates))
        if not isinstance(self.safety, Mapping) or set(self.safety) != set(SAFETY_KEYS):
            raise _error("sealed prediction safety keys changed")
        if any(type(value) is not bool or value is not False for value in self.safety.values()):
            raise _error("sealed prediction downstream authority must remain false")
        object.__setattr__(self, "safety", _safety())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "implementation_state": self.implementation_state,
            "protocol_sha256": self.protocol_sha256,
            "holdout_start_utc": _utc_text(self.holdout_start_utc),
            "fixture": self.fixture.to_dict(),
            "history_prefix_sha256": self.history_prefix_sha256,
            "history_prefix_count": self.history_prefix_count,
            "feature_projection_sha256": self.feature_projection_sha256,
            "features": dict(sorted(self.features.items())),
            "rates": dict(sorted(self.rates.items())),
            "safety": dict(self.safety),
        }


@dataclasses.dataclass(frozen=True)
class FreshPredictionAssessment:
    disposition: PredictionDisposition
    fixture: QualifiedCaptureFixture
    missing_feature_ids: tuple[str, ...]
    sealed_prediction: SealedFreshPrediction | None

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, PredictionDisposition):
            raise _error("prediction disposition is invalid")
        if type(self.fixture) is not QualifiedCaptureFixture:
            raise _error("prediction assessment fixture type mismatch")
        object.__setattr__(self, "fixture", dataclasses.replace(self.fixture))
        if type(self.missing_feature_ids) is not tuple:
            raise _error("missing_feature_ids must be a tuple")
        if tuple(sorted(set(self.missing_feature_ids))) != self.missing_feature_ids:
            raise _error("missing_feature_ids must be sorted and unique")
        if self.disposition is PredictionDisposition.SEALED_COMPLETE_CASE:
            if self.missing_feature_ids or type(self.sealed_prediction) is not SealedFreshPrediction:
                raise _error("complete-case assessment must carry exactly one sealed prediction")
            object.__setattr__(
                self, "sealed_prediction", dataclasses.replace(self.sealed_prediction)
            )
        elif self.sealed_prediction is not None or not self.missing_feature_ids:
            raise _error("missing-feature assessment must carry missing IDs and no prediction")


@dataclasses.dataclass(frozen=True)
class SettledFreshPrediction:
    prediction: SealedFreshPrediction
    home_goals: int
    away_goals: int
    settlement_observed_at: dt.datetime
    settlement_evidence_sha256: str
    ordinary_ft_first_manifest_sha256: str
    ordinary_ft_second_manifest_sha256: str
    legacy_history_state_update: FreshHistoryResult | None

    def __post_init__(self) -> None:
        if type(self.prediction) is not SealedFreshPrediction:
            raise _error("settlement prediction type mismatch")
        object.__setattr__(self, "prediction", dataclasses.replace(self.prediction))
        object.__setattr__(self, "home_goals", _non_negative_int(self.home_goals, "home_goals"))
        object.__setattr__(self, "away_goals", _non_negative_int(self.away_goals, "away_goals"))
        object.__setattr__(
            self,
            "settlement_observed_at",
            _utc(self.settlement_observed_at, "settlement_observed_at"),
        )
        object.__setattr__(
            self,
            "settlement_evidence_sha256",
            _sha256(self.settlement_evidence_sha256, "settlement_evidence_sha256"),
        )
        object.__setattr__(
            self,
            "ordinary_ft_first_manifest_sha256",
            _sha256(self.ordinary_ft_first_manifest_sha256, "ordinary_ft_first_manifest_sha256"),
        )
        object.__setattr__(
            self,
            "ordinary_ft_second_manifest_sha256",
            _sha256(self.ordinary_ft_second_manifest_sha256, "ordinary_ft_second_manifest_sha256"),
        )
        primary = self.prediction.fixture.provider_primary_id
        should_update = primary in pr148.LEGACY_PRIMARY_IDS
        if should_update != (self.legacy_history_state_update is not None):
            raise _error("legacy history-state update disposition changed")
        if self.legacy_history_state_update is not None:
            if type(self.legacy_history_state_update) is not FreshHistoryResult:
                raise _error("legacy history-state update type mismatch")
            object.__setattr__(
                self,
                "legacy_history_state_update",
                dataclasses.replace(self.legacy_history_state_update),
            )


def canonical_sealed_fresh_prediction_bytes(value: SealedFreshPrediction) -> bytes:
    if type(value) is not SealedFreshPrediction:
        raise _error("value must be exact SealedFreshPrediction")
    return _canonical(dataclasses.replace(value).to_dict())


def sha256_sealed_fresh_prediction(value: SealedFreshPrediction) -> str:
    return _sha256_bytes(canonical_sealed_fresh_prediction_bytes(value))


def resolve_holdout_start(implementation_merge_utc: dt.datetime) -> dt.datetime:
    """Resolve the first UTC midnight strictly after implementation merge."""
    merge = _utc(implementation_merge_utc, "implementation_merge_utc")
    next_midnight = dt.datetime.combine(
        merge.date() + dt.timedelta(days=1),
        dt.time.min,
        tzinfo=dt.timezone.utc,
    )
    floor = _parse_utc(pr148.FRESH_HOLDOUT_NOT_BEFORE_UTC, "not_before_utc")
    return max(next_midnight, floor)


def minimum_gate_boundary(holdout_start: dt.datetime) -> dt.datetime:
    return _holdout_start(holdout_start) + dt.timedelta(
        days=pr148.MINIMUM_CALENDAR_SPAN_DAYS
    )


def hard_close_boundary(holdout_start: dt.datetime) -> dt.datetime:
    return _holdout_start(holdout_start) + dt.timedelta(
        days=pr148.MAXIMUM_CALENDAR_SPAN_DAYS
    )


def _strict_json(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not raw:
        raise _error("raw capture must be non-empty exact bytes")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise _error(f"raw capture contains duplicate JSON key {key!r}")
            result[key] = value
        return result

    def constant(token: str) -> None:
        raise _error(f"raw capture contains forbidden JSON constant {token!r}")

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except FotMobFreshHoldoutError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _error("raw capture is not strict UTF-8 JSON") from exc
    if type(value) is not dict:
        raise _error("raw capture top level must be an object")
    return value


def _qualify_provider_identity_payload(
    raw_json: bytes,
    *,
    capture_observed_at: dt.datetime,
    capture_manifest_sha256: str,
    capture_raw_sha256: str,
) -> tuple[QualifiedCaptureFixture, ...]:
    """Pure structural check used after the reviewed capture/schema chain."""
    payload = _strict_json(raw_json)
    leagues = payload.get("leagues")
    if type(leagues) is not list:
        raise _error("raw capture leagues must be a list")
    observed = _utc(capture_observed_at, "capture_observed_at")
    manifest_sha = _sha256(capture_manifest_sha256, "capture_manifest_sha256")
    raw_sha = _sha256(capture_raw_sha256, "capture_raw_sha256")
    if _sha256_bytes(raw_json) != raw_sha:
        raise _error("raw capture SHA-256 lineage changed")

    result: list[QualifiedCaptureFixture] = []
    seen: set[int] = set()
    seen_wrappers: set[int] = set()
    for league in leagues:
        if type(league) is not dict or type(league.get("matches")) is not list:
            raise _error("league wrapper shape changed")
        primary_id = _positive_int(league.get("primaryId"), "league.primaryId")
        wrapper_id = _positive_int(league.get("id"), "league.id")
        if wrapper_id in seen_wrappers:
            raise _error("competition wrapper id duplicated in one capture")
        seen_wrappers.add(wrapper_id)
        for match in league["matches"]:
            if type(match) is not dict:
                raise _error("match shape changed")
            fixture_id = _positive_int(match.get("id"), "match.id")
            if fixture_id in seen:
                raise _error("fixture id duplicated in one capture")
            seen.add(fixture_id)
            match_league_id = _positive_int(match.get("leagueId"), "match.leagueId")
            if match_league_id != wrapper_id:
                raise _error("match.leagueId does not equal containing league.id")
            home = match.get("home")
            away = match.get("away")
            status = match.get("status")
            if type(home) is not dict or type(away) is not dict or type(status) is not dict:
                raise _error("match home/away/status shape changed")
            home_id = _positive_int(home.get("id"), "match.home.id")
            away_id = _positive_int(away.get("id"), "match.away.id")
            if home_id == away_id:
                raise _error("match cannot use one team twice")
            kickoff = _parse_utc(status.get("utcTime"), "status.utcTime")
            result.append(
                QualifiedCaptureFixture(
                    fixture_id=fixture_id,
                    provider_primary_id=primary_id,
                    wrapper_id=wrapper_id,
                    home_team_id=home_id,
                    away_team_id=away_id,
                    kickoff_utc=kickoff,
                    capture_observed_at=observed,
                    capture_manifest_sha256=manifest_sha,
                    capture_raw_sha256=raw_sha,
                )
            )
    result.sort(key=lambda item: (item.kickoff_utc, item.fixture_id))
    return tuple(result)


def qualify_capture_fixtures(
    raw_json: bytes,
    manifest: capture_contract.FotMobDataMatchesCaptureManifest,
) -> tuple[QualifiedCaptureFixture, ...]:
    """Re-run reviewed capture/schema ancestry then enforce PR148 identity rules."""
    verify_reviewed_dependencies()
    if not isinstance(manifest, capture_contract.FotMobDataMatchesCaptureManifest):
        raise _error("manifest must be the reviewed FotMob capture manifest type")
    if manifest.network_acquisition_performed is not True:
        raise _error("fresh holdout evidence requires an actual reviewed network capture")
    try:
        bundle = fixture_candidates.build_fotmob_fixture_candidate_bundle(((raw_json, manifest),))
        manifest_sha = capture_contract.sha256_data_matches_capture_manifest(manifest)
    except Exception as exc:
        raise _error("reviewed capture/schema/candidate chain failed") from exc
    qualified = _qualify_provider_identity_payload(
        raw_json,
        capture_observed_at=manifest.observed_at,
        capture_manifest_sha256=manifest_sha,
        capture_raw_sha256=manifest.raw_sha256,
    )
    candidates = {item.source_match_id: item for item in bundle.candidates}
    if len(candidates) != len(bundle.candidates) or len(qualified) != len(bundle.candidates):
        raise _error("reviewed candidate and exact identity populations disagree")
    for item in qualified:
        candidate = candidates.get(item.fixture_id)
        if candidate is None:
            raise _error("qualified fixture absent from reviewed candidate population")
        expected = (
            candidate.source_competition_primary_id,
            candidate.source_league_id,
            candidate.home_source_team_id,
            candidate.away_source_team_id,
            candidate.kickoff_utc,
            candidate.source_observed_at,
            candidate.source_raw_sha256,
            candidate.source_capture_manifest_sha256,
        )
        actual = (
            item.provider_primary_id,
            item.wrapper_id,
            item.home_team_id,
            item.away_team_id,
            item.kickoff_utc,
            item.capture_observed_at,
            item.capture_raw_sha256,
            item.capture_manifest_sha256,
        )
        if actual != expected:
            raise _error("exact provider identity disagrees with reviewed candidate extraction")
    return qualified


def select_earliest_qualifying_capture(
    observations: Sequence[QualifiedCaptureFixture],
    *,
    holdout_start: dt.datetime,
) -> QualifiedCaptureFixture | None:
    if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)):
        raise _error("observations must be a sequence")
    values = tuple(observations)
    if not values:
        return None
    if any(type(item) is not QualifiedCaptureFixture for item in values):
        raise _error("observations must contain exact QualifiedCaptureFixture values")
    start = _holdout_start(holdout_start)
    identities = {item.identity() for item in values}
    if len(identities) != 1:
        raise _error("capture observations disagree on sealed fixture/competition identity")
    kickoff = values[0].kickoff_utc
    if kickoff < start:
        return None
    earliest = kickoff - dt.timedelta(hours=24)
    latest = kickoff - dt.timedelta(minutes=60)
    eligible = tuple(
        item
        for item in values
        if start <= item.capture_observed_at
        and earliest <= item.capture_observed_at <= latest
    )
    if not eligible:
        return None
    return dataclasses.replace(
        min(
            eligible,
            key=lambda item: (item.capture_observed_at, item.capture_manifest_sha256),
        )
    )


def parse_reviewed_legacy_bootstrap_projection(raw: bytes) -> tuple[FreshHistoryResult, ...]:
    """Load only the exact reviewed PR119 21,326-row legacy bootstrap."""
    if type(raw) is not bytes:
        raise _error("bootstrap projection must be exact bytes")
    if (len(raw), _sha256_bytes(raw)) != (
        BOOTSTRAP_PROJECTION_SIZE,
        BOOTSTRAP_PROJECTION_SHA256,
    ):
        raise _error("reviewed legacy bootstrap projection identity changed")
    rows: list[FreshHistoryResult] = []
    previous: tuple[dt.datetime, int] | None = None
    seen: set[str] = set()
    for line in raw.splitlines(keepends=True):
        if not line.endswith(b"\n"):
            raise _error("bootstrap projection contains torn NDJSON row")
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _error("bootstrap projection row is malformed") from exc
        if type(value) is not dict or _canonical(value) != line:
            raise _error("bootstrap projection row is not canonical JSON")
        if value.get("source_namespace") != SOURCE_NAMESPACE:
            raise _error("bootstrap source namespace changed")
        fixture_id = _text(value.get("fixture_identifier"), "fixture_identifier")
        if fixture_id in seen:
            raise _error("bootstrap fixture identity duplicated")
        seen.add(fixture_id)
        home = _text(value.get("home_team_identifier"), "home_team_identifier")
        away = _text(value.get("away_team_identifier"), "away_team_identifier")
        if not home.isdigit() or int(home) < 1 or not away.isdigit() or int(away) < 1:
            raise _error("bootstrap team identity is not a positive decimal source id")
        row = FreshHistoryResult(
            fixture_identifier=fixture_id,
            home_team_id=int(home),
            away_team_id=int(away),
            kickoff_utc=_parse_utc(value.get("kickoff_utc"), "kickoff_utc"),
            home_goals=_non_negative_int(value.get("home_goals"), "home_goals"),
            away_goals=_non_negative_int(value.get("away_goals"), "away_goals"),
            observed_at=_parse_utc(value.get("observed_at"), "observed_at"),
            evidence_sha256=_sha256(value.get("evidence_sha256"), "evidence_sha256"),
            evidence_reference=_text(value.get("evidence_reference"), "evidence_reference"),
            provider_primary_id=None,
            source_kind="REVIEWED_PR119_BOOTSTRAP",
        )
        key = (row.kickoff_utc, int(row.fixture_identifier))
        if previous is not None and key < previous:
            raise _error("bootstrap projection UTC ordering changed")
        previous = key
        rows.append(row)
    if len(rows) != BOOTSTRAP_PROJECTION_ROWS:
        raise _error("bootstrap projection row count changed")
    return tuple(rows)


def build_fresh_history_ledger(
    bootstrap_projection_raw: bytes,
    *,
    fresh_legacy_updates: Sequence[FreshHistoryResult] = (),
) -> FreshHistoryLedger:
    """Build a reusable ledger only from the exact reviewed bootstrap bytes."""
    bootstrap = parse_reviewed_legacy_bootstrap_projection(bootstrap_projection_raw)
    if not isinstance(fresh_legacy_updates, Sequence) or isinstance(
        fresh_legacy_updates, (str, bytes)
    ):
        raise _error("fresh_legacy_updates must be a sequence")
    updates = tuple(fresh_legacy_updates)
    if any(
        type(item) is not FreshHistoryResult
        or item.source_kind != "FRESH_REVIEWED_ORDINARY_FT_LEGACY_UPDATE"
        for item in updates
    ):
        raise _error("fresh_legacy_updates escaped reviewed legacy settlement rows")
    ordered_updates = tuple(
        sorted(
            (dataclasses.replace(item) for item in updates),
            key=lambda item: (item.kickoff_utc, int(item.fixture_identifier)),
        )
    )
    return FreshHistoryLedger(
        bootstrap_projection_sha256=BOOTSTRAP_PROJECTION_SHA256,
        bootstrap_projection_size=BOOTSTRAP_PROJECTION_SIZE,
        bootstrap_row_count=BOOTSTRAP_PROJECTION_ROWS,
        rows=bootstrap + ordered_updates,
    )


def append_fresh_legacy_history_update(
    ledger: FreshHistoryLedger,
    update: FreshHistoryResult,
) -> FreshHistoryLedger:
    if type(ledger) is not FreshHistoryLedger:
        raise _error("ledger must be exact FreshHistoryLedger")
    if (
        type(update) is not FreshHistoryResult
        or update.source_kind != "FRESH_REVIEWED_ORDINARY_FT_LEGACY_UPDATE"
    ):
        raise _error("update must be a reviewed fresh legacy history row")
    rows = tuple(ledger.rows) + (dataclasses.replace(update),)
    bootstrap = rows[:BOOTSTRAP_PROJECTION_ROWS]
    fresh_rows = tuple(
        sorted(
            rows[BOOTSTRAP_PROJECTION_ROWS:],
            key=lambda item: (item.kickoff_utc, int(item.fixture_identifier)),
        )
    )
    return FreshHistoryLedger(
        bootstrap_projection_sha256=ledger.bootstrap_projection_sha256,
        bootstrap_projection_size=ledger.bootstrap_projection_size,
        bootstrap_row_count=ledger.bootstrap_row_count,
        rows=bootstrap + fresh_rows,
    )


def _history_prefix(
    history: Sequence[FreshHistoryResult],
    *,
    target: QualifiedCaptureFixture,
) -> tuple[FreshHistoryResult, ...]:
    if not isinstance(history, Sequence) or isinstance(history, (str, bytes)):
        raise _error("history must be a sequence")
    rows = tuple(history)
    if any(type(item) is not FreshHistoryResult for item in rows):
        raise _error("history must contain exact FreshHistoryResult values")
    seen: set[str] = set()
    eligible: list[FreshHistoryResult] = []
    for item in rows:
        if item.fixture_identifier in seen:
            raise _error("history fixture identity duplicated")
        seen.add(item.fixture_identifier)
        if int(item.fixture_identifier) == target.fixture_id:
            raise _error("target fixture cannot already exist in result history")
        if item.kickoff_utc < target.kickoff_utc and item.observed_at <= target.capture_observed_at:
            eligible.append(dataclasses.replace(item))
    eligible.sort(key=lambda item: (item.kickoff_utc, int(item.fixture_identifier)))
    return tuple(eligible)


def _constructor_prefix_bytes(history: Sequence[FreshHistoryResult]) -> bytes:
    return b"".join(_canonical(item.constructor_row()) for item in history)


def _rate(predictors: Sequence[float], coefficients: Sequence[float], label: str) -> float:
    if len(predictors) != len(coefficients):
        raise _error(f"{label} predictor/coefficient dimension mismatch")
    eta = math.fsum(float(value) * float(coef) for value, coef in zip(predictors, coefficients))
    if not math.isfinite(eta):
        raise _error(f"{label} linear predictor is non-finite")
    try:
        value = math.exp(eta)
    except OverflowError as exc:
        raise _error(f"{label} expected-goals rate overflowed") from exc
    if not math.isfinite(value) or value <= 0.0:
        raise _error(f"{label} expected-goals rate must be finite and positive")
    return value


def _build_fresh_prediction_assessment_from_rows(
    *,
    history: Sequence[FreshHistoryResult],
    selected_capture: QualifiedCaptureFixture,
    holdout_start: dt.datetime,
) -> FreshPredictionAssessment:
    """Internal deterministic core after reviewed bootstrap ancestry is established."""
    verify_reviewed_dependencies()
    if type(selected_capture) is not QualifiedCaptureFixture:
        raise _error("selected_capture must be exact QualifiedCaptureFixture")
    capture = dataclasses.replace(selected_capture)
    start = _holdout_start(holdout_start)
    if capture.capture_observed_at < start or capture.kickoff_utc < start:
        raise _error("selected capture is outside resolved holdout start")
    earliest = capture.kickoff_utc - dt.timedelta(hours=24)
    latest = capture.kickoff_utc - dt.timedelta(minutes=60)
    if not earliest <= capture.capture_observed_at <= latest:
        raise _error("selected capture is outside the frozen 24h-to-60m window")

    prefix = _history_prefix(history, target=capture)
    prefix_raw = _constructor_prefix_bytes(prefix)
    target_row = {
        "source_namespace": SOURCE_NAMESPACE,
        "fixture_identifier": str(capture.fixture_id),
        "kickoff_utc": _utc_text(capture.kickoff_utc),
        "home_team_identifier": str(capture.home_team_id),
        "away_team_identifier": str(capture.away_team_id),
        "home_goals": 0,
        "away_goals": 0,
        "evidence_sha256": capture.capture_raw_sha256,
        "evidence_reference": (
            f"fresh-holdout-capture:{capture.capture_manifest_sha256}:{capture.fixture_id}"
        ),
    }
    constructor_rows = [item.constructor_row() for item in prefix]
    constructor_rows.append(target_row)
    try:
        projection_raw, _summary = utc_features.construct_utc_native_feature_projection(
            constructor_rows
        )
    except Exception as exc:
        raise _error("reviewed UTC-native feature constructor failed") from exc

    target_value: dict[str, Any] | None = None
    for line in projection_raw.splitlines(keepends=True):
        if not line.endswith(b"\n"):
            raise _error("reviewed feature projection contains torn row")
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _error("reviewed feature projection contains malformed row") from exc
        if line != _canonical(value):
            raise _error("reviewed feature projection row is not canonical")
        if value.get("fixture_identifier") == str(capture.fixture_id):
            if target_value is not None:
                raise _error("reviewed feature projection duplicated target fixture")
            target_value = value
    if target_value is None:
        raise _error("reviewed feature projection omitted target fixture")

    feature_keys = ("home_elo", "away_elo", "home_form", "away_form", "fatigue")
    missing: list[str] = []
    values: dict[str, float] = {}
    for key in feature_keys:
        feature = target_value.get(key)
        if type(feature) is not dict:
            raise _error(f"reviewed target feature {key} shape changed")
        status = feature.get("status")
        value = feature.get("value")
        if status == "MISSING":
            if value is not None:
                raise _error(f"reviewed target feature {key} missingness changed")
            missing.append(key)
            continue
        if type(value) not in (int, float) or not math.isfinite(float(value)):
            raise _error(f"reviewed target feature {key} value is invalid")
        values[key] = float(value)
    if missing:
        return FreshPredictionAssessment(
            disposition=PredictionDisposition.MISSING_REVIEWED_FEATURES,
            fixture=capture,
            missing_feature_ids=tuple(sorted(missing)),
            sealed_prediction=None,
        )

    predictors = (
        1.0,
        (values["home_elo"] - 1500.0) / 400.0,
        (values["away_elo"] - 1500.0) / 400.0,
        values["home_form"] - 0.5,
        values["away_form"] - 0.5,
        values["fatigue"],
    )
    elo_predictors = predictors[:3]
    native_home = _rate(predictors, pr148.NATIVE_HOME_COEFFICIENTS, "native home")
    native_away = _rate(predictors, pr148.NATIVE_AWAY_COEFFICIENTS, "native away")
    elo_home = _rate(elo_predictors, pr148.ELO_ONLY_HOME_COEFFICIENTS, "Elo-only home")
    elo_away = _rate(elo_predictors, pr148.ELO_ONLY_AWAY_COEFFICIENTS, "Elo-only away")
    calibrated_home = pr148.apply_frozen_home_calibration(native_home)
    if type(calibrated_home) is not float or not math.isfinite(calibrated_home) or calibrated_home <= 0.0:
        raise _error("frozen home calibration produced invalid rate")

    sealed = SealedFreshPrediction(
        schema_version=1,
        implementation_state=IMPLEMENTATION_STATE,
        protocol_sha256=pr148.PROTOCOL_SHA256,
        holdout_start_utc=start,
        fixture=capture,
        history_prefix_sha256=_sha256_bytes(prefix_raw),
        history_prefix_count=len(prefix),
        feature_projection_sha256=_sha256_bytes(projection_raw),
        features=values,
        rates={
            "native_home": native_home,
            "native_away": native_away,
            "elo_only_home": elo_home,
            "elo_only_away": elo_away,
            "calibrated_home": calibrated_home,
            "calibrated_away": native_away,
        },
        safety=_safety(),
    )
    return FreshPredictionAssessment(
        disposition=PredictionDisposition.SEALED_COMPLETE_CASE,
        fixture=capture,
        missing_feature_ids=(),
        sealed_prediction=sealed,
    )


def build_fresh_prediction_assessment(
    *,
    history_ledger: FreshHistoryLedger,
    selected_capture: QualifiedCaptureFixture,
    holdout_start: dt.datetime,
) -> FreshPredictionAssessment:
    """Public seal path requiring the exact reviewed bootstrap-ledger ancestry."""
    if type(history_ledger) is not FreshHistoryLedger:
        raise _error("history_ledger must be exact FreshHistoryLedger")
    ledger = dataclasses.replace(history_ledger)
    return _build_fresh_prediction_assessment_from_rows(
        history=ledger.rows,
        selected_capture=selected_capture,
        holdout_start=holdout_start,
    )


def settle_sealed_prediction(
    prediction: SealedFreshPrediction,
    adapter_result: score_adapter.FotMobDataMatchesOrdinaryFtFinishedScoreAdapterResult,
) -> SettledFreshPrediction:
    """Bind one sealed prediction through the reviewed successful pair adapter."""
    verify_reviewed_dependencies()
    if type(prediction) is not SealedFreshPrediction:
        raise _error("prediction must be exact SealedFreshPrediction")
    if type(adapter_result) is not score_adapter.FotMobDataMatchesOrdinaryFtFinishedScoreAdapterResult:
        raise _error("adapter_result must be exact reviewed ordinary-FT adapter result")
    if adapter_result.pair_status is not score_adapter.AdapterPairStatus.QUALIFIED_WITH_ORDINARY_FT_SCORES:
        raise _error("ordinary-FT adapter result does not carry qualified scores")
    prediction = dataclasses.replace(prediction)
    fixture = prediction.fixture
    matches = tuple(
        item for item in adapter_result.qualified_scores if item.fixture_id == fixture.fixture_id
    )
    if len(matches) != 1:
        raise _error("sealed fixture must match exactly one qualified ordinary-FT score")
    score = matches[0]
    if (
        score.league_id != fixture.wrapper_id
        or score.home_team_id != fixture.home_team_id
        or score.away_team_id != fixture.away_team_id
        or score.kickoff_utc != fixture.kickoff_utc
    ):
        raise _error("ordinary-FT settlement identity differs from sealed prediction")

    settlement_payload = {
        "prediction_sha256": sha256_sealed_fresh_prediction(prediction),
        "adapter_pair": {
            "first_manifest_sha256": adapter_result.first_manifest_sha256,
            "second_manifest_sha256": adapter_result.second_manifest_sha256,
            "first_raw_sha256": adapter_result.first_raw_sha256,
            "second_raw_sha256": adapter_result.second_raw_sha256,
            "first_observed_at": _utc_text(adapter_result.first_observed_at),
            "second_observed_at": _utc_text(adapter_result.second_observed_at),
        },
        "ordinary_ft_score": score.to_dict(),
        "provider_primary_id": fixture.provider_primary_id,
        "wrapper_id": fixture.wrapper_id,
    }
    settlement_sha = _sha256_bytes(_canonical(settlement_payload))
    update: FreshHistoryResult | None = None
    if fixture.provider_primary_id in pr148.LEGACY_PRIMARY_IDS:
        update = FreshHistoryResult(
            fixture_identifier=str(fixture.fixture_id),
            home_team_id=fixture.home_team_id,
            away_team_id=fixture.away_team_id,
            kickoff_utc=fixture.kickoff_utc,
            home_goals=score.home_score,
            away_goals=score.away_score,
            observed_at=score.second_observed_at,
            evidence_sha256=settlement_sha,
            evidence_reference=(
                f"fresh-holdout-settlement:{score.first_manifest_sha256}:"
                f"{score.second_manifest_sha256}:{fixture.fixture_id}"
            ),
            provider_primary_id=fixture.provider_primary_id,
            source_kind="FRESH_REVIEWED_ORDINARY_FT_LEGACY_UPDATE",
        )
    return SettledFreshPrediction(
        prediction=prediction,
        home_goals=score.home_score,
        away_goals=score.away_score,
        settlement_observed_at=score.second_observed_at,
        settlement_evidence_sha256=settlement_sha,
        ordinary_ft_first_manifest_sha256=score.first_manifest_sha256,
        ordinary_ft_second_manifest_sha256=score.second_manifest_sha256,
        legacy_history_state_update=update,
    )


def coverage_at_boundary(
    predictions: Sequence[SealedFreshPrediction],
    *,
    holdout_start: dt.datetime,
    boundary: dt.datetime,
) -> dict[str, Any]:
    """Compute only pre-registered time/count coverage; accepts no result data."""
    start = _holdout_start(holdout_start)
    close = _utc(boundary, "boundary")
    if close <= start:
        raise _error("coverage boundary must be strictly after holdout start")
    if close.time() != dt.time.min:
        raise _error("coverage boundary must be an exact UTC midnight")
    if not isinstance(predictions, Sequence) or isinstance(predictions, (str, bytes)):
        raise _error("predictions must be a sequence")
    values = tuple(predictions)
    if any(type(item) is not SealedFreshPrediction for item in values):
        raise _error("coverage population must contain exact sealed predictions")
    seen: set[int] = set()
    included: list[SealedFreshPrediction] = []
    for prediction in values:
        fixture = prediction.fixture
        if fixture.fixture_id in seen:
            raise _error("coverage population duplicates a fixture")
        seen.add(fixture.fixture_id)
        if (
            start <= fixture.capture_observed_at
            and start <= fixture.kickoff_utc < close
        ):
            included.append(prediction)
    counts = Counter(item.fixture.provider_primary_id for item in included)
    qualifying = tuple(
        sorted(
            primary_id
            for primary_id, count in counts.items()
            if count >= pr148.QUALIFYING_COMPETITION_MIN_FIXTURES
        )
    )
    non_legacy = tuple(
        primary_id for primary_id in qualifying if primary_id not in pr148.LEGACY_PRIMARY_IDS
    )
    gates = {
        "minimum_complete_case_fixtures": len(included) >= pr148.MINIMUM_COMPLETE_CASE_FIXTURES,
        "minimum_qualifying_competitions": len(qualifying) >= pr148.MINIMUM_QUALIFYING_COMPETITIONS,
        "minimum_non_legacy_qualifying_competitions": (
            len(non_legacy) >= pr148.MINIMUM_NON_LEGACY_QUALIFYING_COMPETITIONS
        ),
    }
    return {
        "holdout_start_utc": _utc_text(start),
        "boundary_utc": _utc_text(close),
        "complete_case_fixture_count": len(included),
        "primary_id_counts": {str(key): counts[key] for key in sorted(counts)},
        "qualifying_primary_ids": list(qualifying),
        "non_legacy_qualifying_primary_ids": list(non_legacy),
        "count_only_gates": gates,
        "all_count_only_gates_pass": all(gates.values()),
    }


def evaluate_holdout_boundary(
    predictions: Sequence[SealedFreshPrediction],
    *,
    holdout_start: dt.datetime,
    boundary: dt.datetime,
) -> dict[str, Any]:
    """Return the frozen close/open decision without accepting outcome metrics."""
    start = _holdout_start(holdout_start)
    current = _utc(boundary, "boundary")
    if current.time() != dt.time.min:
        raise _error("evaluated boundary must be an exact UTC midnight")
    minimum = minimum_gate_boundary(start)
    hard = hard_close_boundary(start)
    if current > hard:
        raise _error("cannot evaluate a boundary after the frozen hard close")
    coverage = coverage_at_boundary(predictions, holdout_start=start, boundary=current)
    if current < minimum:
        decision = HoldoutBoundaryDecision.OPEN_BEFORE_MINIMUM_GATE
    elif coverage["all_count_only_gates_pass"]:
        decision = HoldoutBoundaryDecision.CLOSE_COUNT_ONLY_COVERAGE_QUALIFIED
    elif current == hard:
        decision = HoldoutBoundaryDecision.CLOSE_INSUFFICIENT_COVERAGE_NO_SUCCESSOR_DECISION
    else:
        decision = HoldoutBoundaryDecision.OPEN_WAITING_FOR_COUNT_ONLY_COVERAGE
    return {
        "decision": decision.value,
        "minimum_gate_boundary_utc": _utc_text(minimum),
        "hard_close_boundary_utc": _utc_text(hard),
        "coverage": coverage,
        "outcome_or_performance_input_used": False,
    }


def implementation_receipt() -> dict[str, Any]:
    """Describe this offline implementation boundary without starting a holdout."""
    verify_reviewed_dependencies()
    return {
        "schema_version": 1,
        "implementation_state": IMPLEMENTATION_STATE,
        "protocol": {
            "id": pr148.PROTOCOL_ID,
            "sha256": pr148.PROTOCOL_SHA256,
            "size_bytes": pr148.PROTOCOL_SIZE,
            "blob_sha": PR148_PROTOCOL_BLOB_SHA,
        },
        "reviewed_dependencies": {
            "utc_feature_constructor_blob_sha": UTC_FEATURE_CONSTRUCTOR_BLOB_SHA,
            "fixture_candidate_blob_sha": FIXTURE_CANDIDATE_BLOB_SHA,
            "capture_contract_blob_sha": CAPTURE_CONTRACT_BLOB_SHA,
            "ordinary_ft_adapter_blob_sha": ORDINARY_FT_ADAPTER_BLOB_SHA,
            "bootstrap_projection_sha256": BOOTSTRAP_PROJECTION_SHA256,
            "bootstrap_projection_size_bytes": BOOTSTRAP_PROJECTION_SIZE,
            "bootstrap_projection_rows": BOOTSTRAP_PROJECTION_ROWS,
        },
        "network_acquisition_performed": False,
        "fresh_holdout_started": False,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


__all__ = [
    "BOOTSTRAP_PROJECTION_ROWS",
    "BOOTSTRAP_PROJECTION_SHA256",
    "BOOTSTRAP_PROJECTION_SIZE",
    "FreshHistoryLedger",
    "FreshHistoryResult",
    "FreshPredictionAssessment",
    "FotMobFreshHoldoutError",
    "HoldoutBoundaryDecision",
    "IMPLEMENTATION_STATE",
    "NEXT_REQUIRED_BOUNDARY",
    "PredictionDisposition",
    "QualifiedCaptureFixture",
    "SealedFreshPrediction",
    "SettledFreshPrediction",
    "append_fresh_legacy_history_update",
    "build_fresh_history_ledger",
    "build_fresh_prediction_assessment",
    "canonical_sealed_fresh_prediction_bytes",
    "coverage_at_boundary",
    "evaluate_holdout_boundary",
    "hard_close_boundary",
    "implementation_receipt",
    "minimum_gate_boundary",
    "parse_reviewed_legacy_bootstrap_projection",
    "qualify_capture_fixtures",
    "resolve_holdout_start",
    "select_earliest_qualifying_capture",
    "settle_sealed_prediction",
    "sha256_sealed_fresh_prediction",
    "verify_reviewed_dependencies",
]
