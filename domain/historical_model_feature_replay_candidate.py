"""Pure, research-only replay of historical football-data.co.uk evidence.

This module deliberately accepts exact CSV bytes supplied by a caller.  It
does not read files, query SQLite, acquire data, run a score matrix, or create
probabilities.  Source identities mirror the football-data.co.uk importer and
remain scoped to that source.
"""

from __future__ import annotations

import csv
import dataclasses
import datetime
import enum
import hashlib
import io
import json
import math
import re
import types
from collections.abc import Mapping, Sequence
from typing import Any

from domain.fixture_model_features import ModelFeatureId
from domain.fotmob_reviewed_match_details_expected_goals_transform_candidate import (
    TRANSFORM_ID,
    canonical_legacy_expected_goals_transform_specification_bytes,
    legacy_expected_goals_transform_specification,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-historical-model-feature-replay-candidate-v1"
REPLAY_SCOPE = "FOOTBALL_DATA_UK_SOURCE_EVIDENCE_RESEARCH_ONLY"
SOURCE = "football_data_uk_csv"
SOURCE_LOCAL_TIMEZONE_UNRESOLVED = "SOURCE_LOCAL_TIMEZONE_UNRESOLVED"
MISSING_SOURCE_TIME = "MISSING_SOURCE_TIME"
PR31_FATIGUE_SEMANTIC_EQUIVALENCE = "UNPROVEN"
_REQUIRED_FIELDS = frozenset(
    {
        "Div",
        "Date",
        "Time",
        "HomeTeam",
        "AwayTeam",
        "FTHG",
        "FTAG",
        "FTR",
        "HTHG",
        "HTAG",
        "HTR",
    }
)
_LEAGUE_RE = re.compile(r"^[A-Z0-9]{1,8}$", flags=re.ASCII)
_SEASON_RE = re.compile(r"^(20[0-9]{2})-([0-9]{2})$", flags=re.ASCII)
_INT_RE = re.compile(r"^[0-9]+$", flags=re.ASCII)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "historical_replay_approved",
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
_REPLAY_FEATURE_IDS = tuple(sorted(ModelFeatureId, key=lambda item: item.value))


class HistoricalModelFeatureReplayCandidateError(ValueError):
    """Raised when source evidence cannot support a deterministic replay."""


class HistoricalFeatureReplayStatus(str, enum.Enum):
    AVAILABLE_RESEARCH_REPLAY = "AVAILABLE_RESEARCH_REPLAY"
    MISSING_PRIOR_HISTORY = "MISSING_PRIOR_HISTORY"
    BLOCKED_TEMPORAL_AMBIGUITY = "BLOCKED_TEMPORAL_AMBIGUITY"
    BLOCKED_IDENTITY_AMBIGUITY = "BLOCKED_IDENTITY_AMBIGUITY"
    NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE = (
        "NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE"
    )
    SEMANTIC_EQUIVALENCE_UNPROVEN = "SEMANTIC_EQUIVALENCE_UNPROVEN"


def _error(message: str) -> HistoricalModelFeatureReplayCandidateError:
    return HistoricalModelFeatureReplayCandidateError(message)


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("historical replay serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _exact_text(value: Any, label: str, *, maximum: int = 4096) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > maximum:
        raise _error(f"{label} must be a non-empty exact trimmed string")
    return value


def _season(value: Any) -> str:
    result = _exact_text(value, "season", maximum=7)
    match = _SEASON_RE.fullmatch(result)
    if match is None or int(match.group(2)) != (int(match.group(1)) + 1) % 100:
        raise _error("season must be consecutive YYYY-YY")
    return result


def _league(value: Any) -> str:
    result = _exact_text(value, "league", maximum=8).upper()
    if _LEAGUE_RE.fullmatch(result) is None:
        raise _error("league must be an exact football-data.co.uk league code")
    return result


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise _error(f"{label} must be an exact positive integer")
    return value


def _finite_number(value: Any, label: str) -> float | int:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise _error(f"{label} must be a finite exact numeric value")
    return value


def _source_hash(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise _error(f"{label} must be lowercase SHA-256")
    return value


def _source_team_identity(name: str) -> int:
    payload = json.dumps(
        [SOURCE, "team", name.casefold()],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    result = int(_sha256(payload.encode("utf-8"))[:16], 16) & ((1 << 63) - 1)
    return result or 1


def _fixture_identity(
    *, season: str, league: str, match_date: str, match_time: str, home: str, away: str
) -> tuple[int, str]:
    payload = json.dumps(
        [SOURCE, season, league, match_date, match_time, home.casefold(), away.casefold()],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    fingerprint = _sha256(payload.encode("utf-8"))
    result = int(fingerprint[:16], 16) & ((1 << 63) - 1)
    return result or 1, fingerprint


def _decode_csv(raw: bytes) -> str:
    if type(raw) is not bytes or not raw:
        raise _error("source CSV bytes must be exact non-empty immutable bytes")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return raw.decode("cp1252")
        except UnicodeDecodeError as exc:
            raise _error("source CSV bytes have no importer-supported decoding") from exc


def _parse_date(value: Any, label: str) -> datetime.date:
    text = _exact_text(str(value or "").strip(), label, maximum=16)
    for pattern in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise _error(f"{label} is not an importer-supported date")


def _parse_local_kickoff(match_date: datetime.date, value: Any) -> datetime.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in ("%H:%M", "%H:%M:%S", "%H.%M"):
        try:
            return datetime.datetime.combine(
                match_date, datetime.datetime.strptime(text, pattern).time()
            )
        except ValueError:
            continue
    raise _error("Time is not an importer-supported local clock value")


def _parse_goals(value: Any, label: str) -> int:
    text = str(value or "").strip()
    if _INT_RE.fullmatch(text) is None:
        raise _error(f"{label} must be an explicit non-negative integer")
    result = int(text)
    if result < 0:
        raise _error(f"{label} must be non-negative")
    return result


def _parse_optional_score(value: Any) -> int | str | None:
    """Importer parity for half-time fields, which are outside this replay."""

    text = str(value or "").strip()
    if not text:
        return None
    return int(text) if _INT_RE.fullmatch(text) is not None else text


def _normalize_optional_result(value: Any, label: str) -> str:
    result = str(value or "").strip().upper()
    if result and result not in {"H", "D", "A"}:
        raise _error(f"{label} must be H, D, A, or blank")
    return result


def _expected_result(home_goals: int, away_goals: int) -> str:
    return "H" if home_goals > away_goals else "A" if home_goals < away_goals else "D"


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error("all safety values must be exact bool False")
    return _default_safety()


@dataclasses.dataclass(frozen=True)
class HistoricalReplaySourceInput:
    """Execution input: one preserved source file supplied as immutable bytes."""

    season: str
    acquisition_league: str
    raw_bytes: bytes

    def __post_init__(self) -> None:
        object.__setattr__(self, "season", _season(self.season))
        object.__setattr__(self, "acquisition_league", _league(self.acquisition_league))
        if type(self.raw_bytes) is not bytes or not self.raw_bytes:
            raise _error("raw_bytes must be exact non-empty immutable bytes")


@dataclasses.dataclass(frozen=True)
class HistoricalReplaySourceFile:
    season: str
    acquisition_league: str
    raw_sha256: str
    raw_size: int
    source_row_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "season", _season(self.season))
        object.__setattr__(self, "acquisition_league", _league(self.acquisition_league))
        object.__setattr__(self, "raw_sha256", _source_hash(self.raw_sha256, "raw_sha256"))
        object.__setattr__(self, "raw_size", _positive_int(self.raw_size, "raw_size"))
        object.__setattr__(self, "source_row_count", _positive_int(self.source_row_count, "source_row_count"))

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class HistoricalReplayFeatureValue:
    feature_id: ModelFeatureId
    status: HistoricalFeatureReplayStatus
    value: float | int | None
    evidence_origin: str
    replay_initial_state_assumption: bool

    def __post_init__(self) -> None:
        if not isinstance(self.feature_id, ModelFeatureId):
            raise _error("feature_id must be an exact ModelFeatureId")
        if not isinstance(self.status, HistoricalFeatureReplayStatus):
            raise _error("feature status must be HistoricalFeatureReplayStatus")
        _exact_text(self.evidence_origin, "evidence_origin")
        if type(self.replay_initial_state_assumption) is not bool:
            raise _error("replay_initial_state_assumption must be exact bool")
        if self.status is HistoricalFeatureReplayStatus.AVAILABLE_RESEARCH_REPLAY:
            _finite_number(self.value, "available feature value")
        elif self.value is not None:
            raise _error("non-available historical feature value must be None")
        if self.feature_id not in (ModelFeatureId.HOME_ELO, ModelFeatureId.AWAY_ELO) and self.replay_initial_state_assumption:
            raise _error("only Elo replay may carry an initial-state assumption")

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id.value,
            "status": self.status.value,
            "value": self.value,
            "evidence_origin": self.evidence_origin,
            "replay_initial_state_assumption": self.replay_initial_state_assumption,
        }


@dataclasses.dataclass(frozen=True)
class HistoricalReplayFixture:
    fixture_identifier: str
    source: str
    season: str
    observed_league: str | None
    identity_league: str
    source_local_date: datetime.date
    source_local_kickoff: datetime.datetime | None
    kickoff_timezone_status: str
    home_source_team_identifier: str
    away_source_team_identifier: str
    home_team_name: str
    away_team_name: str
    home_goals: int
    away_goals: int
    source_file_sha256: str
    source_row_number: int
    features: tuple[HistoricalReplayFeatureValue, ...]
    fatigue_pr31_semantic_equivalence: str
    form_path_component_eligible: bool
    elo_fallback_component_eligible: bool

    def __post_init__(self) -> None:
        _exact_text(self.fixture_identifier, "fixture_identifier")
        if self.source != SOURCE:
            raise _error("fixture source must remain football_data_uk_csv")
        object.__setattr__(self, "season", _season(self.season))
        if self.observed_league is not None:
            object.__setattr__(self, "observed_league", _league(self.observed_league))
        object.__setattr__(self, "identity_league", _league(self.identity_league))
        if type(self.source_local_date) is not datetime.date:
            raise _error("source_local_date must be an exact source date")
        if self.source_local_kickoff is not None:
            if type(self.source_local_kickoff) is not datetime.datetime or self.source_local_kickoff.tzinfo is not None:
                raise _error("source_local_kickoff must be naive source-local datetime or None")
            if self.kickoff_timezone_status != SOURCE_LOCAL_TIMEZONE_UNRESOLVED:
                raise _error("dated source-local kickoff must retain unresolved timezone status")
        elif self.kickoff_timezone_status != MISSING_SOURCE_TIME:
            raise _error("missing source time must retain MISSING_SOURCE_TIME")
        for label in ("home_source_team_identifier", "away_source_team_identifier", "home_team_name", "away_team_name"):
            _exact_text(getattr(self, label), label)
        if self.home_source_team_identifier == self.away_source_team_identifier:
            raise _error("source fixture cannot use the same source-scoped identity twice")
        for value, label in ((self.home_goals, "home_goals"), (self.away_goals, "away_goals"), (self.source_row_number, "source_row_number")):
            if type(value) is not int or value < 0 or (label == "source_row_number" and value < 2):
                raise _error(f"{label} must be valid non-negative source evidence")
        object.__setattr__(self, "source_file_sha256", _source_hash(self.source_file_sha256, "source_file_sha256"))
        if type(self.features) is not tuple or len(self.features) != len(_REPLAY_FEATURE_IDS):
            raise _error("fixture must carry exactly six replay feature records")
        if any(type(item) is not HistoricalReplayFeatureValue for item in self.features):
            raise _error("fixture feature records must be exact detached values")
        if tuple(item.feature_id for item in self.features) != _REPLAY_FEATURE_IDS:
            raise _error("fixture feature records must be sorted exact PR31 feature IDs")
        if self.fatigue_pr31_semantic_equivalence != PR31_FATIGUE_SEMANTIC_EQUIVALENCE:
            raise _error("fatigue PR31 semantic equivalence must remain UNPROVEN")
        if type(self.form_path_component_eligible) is not bool or type(self.elo_fallback_component_eligible) is not bool:
            raise _error("component eligibility values must be exact bool")
        by_id = {item.feature_id: item for item in self.features}
        expected_form = all(by_id[key].status is HistoricalFeatureReplayStatus.AVAILABLE_RESEARCH_REPLAY for key in (ModelFeatureId.HOME_FORM, ModelFeatureId.AWAY_FORM, ModelFeatureId.FATIGUE))
        expected_elo = all(by_id[key].status is HistoricalFeatureReplayStatus.AVAILABLE_RESEARCH_REPLAY for key in (ModelFeatureId.HOME_ELO, ModelFeatureId.AWAY_ELO, ModelFeatureId.FATIGUE))
        if self.form_path_component_eligible != expected_form or self.elo_fallback_component_eligible != expected_elo:
            raise _error("component eligibility must derive mechanically from replay statuses")

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_identifier": self.fixture_identifier,
            "source": self.source,
            "season": self.season,
            "observed_league": self.observed_league,
            "identity_league": self.identity_league,
            "source_local_date": self.source_local_date.isoformat(),
            "source_local_kickoff": self.source_local_kickoff.isoformat() if self.source_local_kickoff else None,
            "kickoff_timezone_status": self.kickoff_timezone_status,
            "home_source_team_identifier": self.home_source_team_identifier,
            "away_source_team_identifier": self.away_source_team_identifier,
            "home_team_name": self.home_team_name,
            "away_team_name": self.away_team_name,
            "home_goals": self.home_goals,
            "away_goals": self.away_goals,
            "source_file_sha256": self.source_file_sha256,
            "source_row_number": self.source_row_number,
            "features": [item.to_dict() for item in self.features],
            "fatigue_pr31_semantic_equivalence": self.fatigue_pr31_semantic_equivalence,
            "form_path_component_eligible": self.form_path_component_eligible,
            "elo_fallback_component_eligible": self.elo_fallback_component_eligible,
        }


@dataclasses.dataclass(frozen=True)
class HistoricalReplayCorpus:
    schema_version: int
    dataset_name: str
    scope: str
    source_files: tuple[HistoricalReplaySourceFile, ...]
    fixture_count: int
    source_corpus_sha256: str
    target_pr68_transform_id: str
    target_pr68_transform_spec_sha256: str
    fixtures: tuple[HistoricalReplayFixture, ...]
    aggregate_coverage: Mapping[str, int]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise _error("schema_version must be exact int 1")
        if self.dataset_name != DATASET_NAME or self.scope != REPLAY_SCOPE:
            raise _error("historical replay corpus contract identity mismatch")
        if type(self.source_files) is not tuple or not self.source_files or any(type(item) is not HistoricalReplaySourceFile for item in self.source_files):
            raise _error("source_files must be non-empty exact source records")
        expected_files = tuple(sorted(self.source_files, key=lambda item: (item.season, item.acquisition_league, item.raw_sha256)))
        if self.source_files != expected_files or len({(item.season, item.acquisition_league) for item in self.source_files}) != len(self.source_files):
            raise _error("source files must be uniquely and deterministically ordered")
        if type(self.fixture_count) is not int or self.fixture_count < 0 or self.fixture_count != len(self.fixtures):
            raise _error("fixture_count must exactly equal fixture records")
        object.__setattr__(self, "source_corpus_sha256", _source_hash(self.source_corpus_sha256, "source_corpus_sha256"))
        if self.target_pr68_transform_id != TRANSFORM_ID:
            raise _error("target transform must be exact PR68 legacy candidate")
        object.__setattr__(self, "target_pr68_transform_spec_sha256", _source_hash(self.target_pr68_transform_spec_sha256, "target_pr68_transform_spec_sha256"))
        if type(self.fixtures) is not tuple or any(type(item) is not HistoricalReplayFixture for item in self.fixtures):
            raise _error("fixtures must be exact replay fixtures")
        expected_fixtures = tuple(sorted(self.fixtures, key=lambda item: item.fixture_identifier))
        if self.fixtures != expected_fixtures or len({item.fixture_identifier for item in self.fixtures}) != len(self.fixtures):
            raise _error("fixtures must be uniquely and deterministically ordered")
        if not isinstance(self.aggregate_coverage, Mapping):
            raise _error("aggregate_coverage must be a mapping")
        detached: dict[str, int] = {}
        for key, value in self.aggregate_coverage.items():
            _exact_text(key, "aggregate coverage key")
            if type(value) is not int or value < 0:
                raise _error("aggregate coverage values must be non-negative exact integers")
            detached[key] = value
        object.__setattr__(self, "aggregate_coverage", types.MappingProxyType(dict(sorted(detached.items()))))
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "scope": self.scope,
            "source_files": [item.to_dict() for item in self.source_files],
            "fixture_count": self.fixture_count,
            "source_corpus_sha256": self.source_corpus_sha256,
            "target_pr68_transform_id": self.target_pr68_transform_id,
            "target_pr68_transform_spec_sha256": self.target_pr68_transform_spec_sha256,
            "fixtures": [item.to_dict() for item in self.fixtures],
            "aggregate_coverage": dict(self.aggregate_coverage),
            "safety": dict(self.safety),
        }


@dataclasses.dataclass(frozen=True)
class _ParsedFixture:
    fixture_identifier: str
    season: str
    observed_league: str | None
    identity_league: str
    source_local_date: datetime.date
    source_local_kickoff: datetime.datetime | None
    home_name: str
    away_name: str
    home_team_id: int
    away_team_id: int
    home_goals: int
    away_goals: int
    source_file_sha256: str
    source_row_number: int


def _parse_source_input(source_input: HistoricalReplaySourceInput) -> tuple[HistoricalReplaySourceFile, tuple[_ParsedFixture, ...]]:
    if type(source_input) is not HistoricalReplaySourceInput:
        raise _error("source inputs must be exact HistoricalReplaySourceInput values")
    decoded = _decode_csv(source_input.raw_bytes)
    prefix = decoded.lstrip()[:256].casefold()
    if prefix.startswith("<!doctype html") or prefix.startswith("<html"):
        raise _error("source CSV must not contain HTML")
    try:
        reader = csv.DictReader(io.StringIO(decoded, newline=""), strict=True)
        fieldnames = {str(name or "").strip() for name in (reader.fieldnames or ())}
    except csv.Error as exc:
        raise _error("source CSV is not parseable") from exc
    missing = sorted(_REQUIRED_FIELDS - fieldnames)
    if missing:
        raise _error("source CSV is missing required importer fields: " + ", ".join(missing))
    raw_hash = _sha256(source_input.raw_bytes)
    parsed: list[_ParsedFixture] = []
    try:
        for row_number, raw_row in enumerate(reader, start=2):
            row = {str(key or "").strip(): value for key, value in raw_row.items()}
            date = _parse_date(row.get("Date"), "Date")
            local_kickoff = _parse_local_kickoff(date, row.get("Time"))
            actual_league = str(row.get("Div") or "").strip()
            observed_league = _league(actual_league) if actual_league else None
            identity_league = observed_league or source_input.acquisition_league
            home = _exact_text(str(row.get("HomeTeam") or "").strip(), "HomeTeam")
            away = _exact_text(str(row.get("AwayTeam") or "").strip(), "AwayTeam")
            if home.casefold() == away.casefold():
                raise _error("source row cannot contain equivalent home and away names")
            home_goals = _parse_goals(row.get("FTHG"), "FTHG")
            away_goals = _parse_goals(row.get("FTAG"), "FTAG")
            result = _normalize_optional_result(row.get("FTR"), "FTR")
            if result and result != _expected_result(home_goals, away_goals):
                raise _error("FTR conflicts with explicit full-time goals")
            half_home = _parse_optional_score(row.get("HTHG"))
            half_away = _parse_optional_score(row.get("HTAG"))
            half_time_result = _normalize_optional_result(row.get("HTR"), "HTR")
            if (
                half_time_result
                and type(half_home) is int
                and type(half_away) is int
                and half_home >= 0
                and half_away >= 0
                and half_time_result != _expected_result(half_home, half_away)
            ):
                raise _error("HTR conflicts with half-time scores")
            _, fingerprint = _fixture_identity(
                season=source_input.season,
                league=identity_league,
                match_date=date.isoformat(),
                match_time=str(row.get("Time") or "").strip(),
                home=home,
                away=away,
            )
            parsed.append(
                _ParsedFixture(
                    fixture_identifier=f"{SOURCE}:{fingerprint}",
                    season=source_input.season,
                    observed_league=observed_league,
                    identity_league=identity_league,
                    source_local_date=date,
                    source_local_kickoff=local_kickoff,
                    home_name=home,
                    away_name=away,
                    home_team_id=_source_team_identity(home),
                    away_team_id=_source_team_identity(away),
                    home_goals=home_goals,
                    away_goals=away_goals,
                    source_file_sha256=raw_hash,
                    source_row_number=row_number,
                )
            )
    except (csv.Error, HistoricalModelFeatureReplayCandidateError) as exc:
        raise _error("source CSV contains a malformed evidence row") from exc
    if not parsed:
        raise _error("source CSV contains no data rows")
    source_file = HistoricalReplaySourceFile(
        season=source_input.season,
        acquisition_league=source_input.acquisition_league,
        raw_sha256=raw_hash,
        raw_size=len(source_input.raw_bytes),
        source_row_count=len(parsed),
    )
    return source_file, tuple(parsed)


def _feature(
    feature_id: ModelFeatureId,
    status: HistoricalFeatureReplayStatus,
    value: float | int | None,
    origin: str,
    *,
    initial: bool = False,
) -> HistoricalReplayFeatureValue:
    return HistoricalReplayFeatureValue(feature_id, status, value, origin, initial)


def _blocked_features(status: HistoricalFeatureReplayStatus) -> tuple[HistoricalReplayFeatureValue, ...]:
    if status not in (
        HistoricalFeatureReplayStatus.BLOCKED_TEMPORAL_AMBIGUITY,
        HistoricalFeatureReplayStatus.BLOCKED_IDENTITY_AMBIGUITY,
    ):
        raise _error("only explicit ambiguity states can block complete replay")
    return tuple(
        _feature(
            feature_id,
            HistoricalFeatureReplayStatus.NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE if feature_id is ModelFeatureId.LIVE_DATA_FRESHNESS else status,
            None,
            "NO_RETAINED_PRE_KICKOFF_FRESHNESS_EVIDENCE" if feature_id is ModelFeatureId.LIVE_DATA_FRESHNESS else "SOURCE_LOCAL_ORDERING_NOT_MECHANICALLY_SAFE",
        )
        for feature_id in _REPLAY_FEATURE_IDS
    )


def _form(history: list[tuple[datetime.datetime, str]], target: datetime.datetime) -> HistoricalReplayFeatureValue:
    prior = [item for item in history if item[0] < target]
    recent = sorted(prior, key=lambda item: item[0], reverse=True)[:5]
    if not recent:
        return _feature(ModelFeatureId.HOME_FORM, HistoricalFeatureReplayStatus.MISSING_PRIOR_HISTORY, None, "NO_STRICTLY_PRIOR_SOURCE_FIXTURE")
    points = sum(3 if result == "W" else 1 if result == "D" else 0 for _, result in recent)
    return _feature(ModelFeatureId.HOME_FORM, HistoricalFeatureReplayStatus.AVAILABLE_RESEARCH_REPLAY, round(0.10 + ((points / (len(recent) * 3)) * 0.85), 3), "STRICTLY_PRIOR_SOURCE_FIXTURES")


def _replace_feature_id(value: HistoricalReplayFeatureValue, feature_id: ModelFeatureId) -> HistoricalReplayFeatureValue:
    return HistoricalReplayFeatureValue(feature_id, value.status, value.value, value.evidence_origin, value.replay_initial_state_assumption)


def _fatigue(home_last: datetime.datetime | None, away_last: datetime.datetime | None, target: datetime.datetime) -> HistoricalReplayFeatureValue:
    if home_last is None or away_last is None:
        return _feature(ModelFeatureId.FATIGUE, HistoricalFeatureReplayStatus.MISSING_PRIOR_HISTORY, None, "NO_STRICTLY_PRIOR_SOURCE_FIXTURE")
    difference = (target - home_last).days - (target - away_last).days
    value = 0.30 if difference < -2 else 0.10 if difference < 0 else 0.0
    return _feature(ModelFeatureId.FATIGUE, HistoricalFeatureReplayStatus.AVAILABLE_RESEARCH_REPLAY, value, "STRICTLY_PRIOR_SOURCE_FIXTURE_DATES")


def _expected_score(home_rating: int, away_rating: int, *, home_boost: bool) -> float:
    adjusted = home_rating + 50 if home_boost else home_rating
    return 1.0 / (1.0 + 10.0 ** ((away_rating - adjusted) / 400.0))


def _k_factor(matches: int) -> int:
    return 32 if matches < 20 else 24 if matches < 50 else 16


def _coverage(fixtures: Sequence[HistoricalReplayFixture]) -> Mapping[str, int]:
    counts: dict[str, int] = {"fixture_count": len(fixtures)}
    for feature_id in _REPLAY_FEATURE_IDS:
        counts[f"{feature_id.value}_available_count"] = sum(
            1
            for fixture in fixtures
            if next(item for item in fixture.features if item.feature_id is feature_id).status
            is HistoricalFeatureReplayStatus.AVAILABLE_RESEARCH_REPLAY
        )
    counts["form_path_component_eligible_count"] = sum(item.form_path_component_eligible for item in fixtures)
    counts["elo_fallback_component_eligible_count"] = sum(item.elo_fallback_component_eligible for item in fixtures)
    counts["exact_six_feature_eligible_count"] = 0
    return types.MappingProxyType(dict(sorted(counts.items())))


def _source_corpus_sha256(source_files: Sequence[HistoricalReplaySourceFile]) -> str:
    return _sha256(_canonical_json_bytes([item.to_dict() for item in source_files]))


def _is_temporally_tainted(
    taint_starts: Mapping[int, list[datetime.date | datetime.datetime]],
    team_id: int,
    target: datetime.datetime,
) -> bool:
    """Return whether an unresolved prior event can affect ``target``.

    A missing clock is only ordered to its source date, so it blocks every
    same-or-later-date target for that team.  A same-team same-clock collision
    is ordered through its known local clock.  This intentionally conservative
    model never inserts an uncertain result into form, fatigue, or Elo state.
    """

    for start in taint_starts.get(team_id, []):
        if type(start) is datetime.datetime:
            if start <= target:
                return True
        elif start <= target.date():
            return True
    return False


def _fixture(
    item: _ParsedFixture,
    *,
    features: tuple[HistoricalReplayFeatureValue, ...],
) -> HistoricalReplayFixture:
    feature_map = {value.feature_id: value for value in features}
    return HistoricalReplayFixture(
        fixture_identifier=item.fixture_identifier,
        source=SOURCE,
        season=item.season,
        observed_league=item.observed_league,
        identity_league=item.identity_league,
        source_local_date=item.source_local_date,
        source_local_kickoff=item.source_local_kickoff,
        kickoff_timezone_status=(
            SOURCE_LOCAL_TIMEZONE_UNRESOLVED
            if item.source_local_kickoff is not None
            else MISSING_SOURCE_TIME
        ),
        home_source_team_identifier=f"{SOURCE}:team:{item.home_team_id}",
        away_source_team_identifier=f"{SOURCE}:team:{item.away_team_id}",
        home_team_name=item.home_name,
        away_team_name=item.away_name,
        home_goals=item.home_goals,
        away_goals=item.away_goals,
        source_file_sha256=item.source_file_sha256,
        source_row_number=item.source_row_number,
        features=features,
        fatigue_pr31_semantic_equivalence=PR31_FATIGUE_SEMANTIC_EQUIVALENCE,
        form_path_component_eligible=all(
            feature_map[key].status is HistoricalFeatureReplayStatus.AVAILABLE_RESEARCH_REPLAY
            for key in (ModelFeatureId.HOME_FORM, ModelFeatureId.AWAY_FORM, ModelFeatureId.FATIGUE)
        ),
        elo_fallback_component_eligible=all(
            feature_map[key].status is HistoricalFeatureReplayStatus.AVAILABLE_RESEARCH_REPLAY
            for key in (ModelFeatureId.HOME_ELO, ModelFeatureId.AWAY_ELO, ModelFeatureId.FATIGUE)
        ),
    )


def build_historical_model_feature_replay_corpus(
    source_inputs: Sequence[HistoricalReplaySourceInput],
) -> HistoricalReplayCorpus:
    """Build a deterministic research replay solely from supplied CSV bytes."""

    if type(source_inputs) not in (tuple, list) or not source_inputs:
        raise _error("source_inputs must be a non-empty ordered sequence")
    parsed_pairs = tuple(_parse_source_input(item) for item in source_inputs)
    source_files = tuple(sorted((pair[0] for pair in parsed_pairs), key=lambda item: (item.season, item.acquisition_league, item.raw_sha256)))
    if len({(item.season, item.acquisition_league) for item in source_files}) != len(source_files):
        raise _error("each season/league source file may occur only once")
    parsed = [fixture for _, values in parsed_pairs for fixture in values]
    identifiers = [item.fixture_identifier for item in parsed]
    if len(set(identifiers)) != len(identifiers):
        raise _error("duplicate source fixture identity is rejected without reconciliation")

    names_by_team: dict[int, set[str]] = {}
    for item in parsed:
        names_by_team.setdefault(item.home_team_id, set()).add(item.home_name.casefold())
        names_by_team.setdefault(item.away_team_id, set()).add(item.away_name.casefold())
    ambiguous_team_ids = {team_id for team_id, names in names_by_team.items() if len(names) != 1}
    collision_keys: dict[tuple[int, datetime.datetime], list[str]] = {}
    for item in parsed:
        if item.source_local_kickoff is not None:
            collision_keys.setdefault((item.home_team_id, item.source_local_kickoff), []).append(item.fixture_identifier)
            collision_keys.setdefault((item.away_team_id, item.source_local_kickoff), []).append(item.fixture_identifier)
    temporal_collisions = {fixture_id for values in collision_keys.values() if len(values) > 1 for fixture_id in values}

    # Unresolved fixtures are never inserted into state.  Instead their
    # outcome taints each participating source-scoped team prospectively.  For
    # a missing clock, only the source date is known, so every same-or-later
    # local target is blocked.  A known-clock collision taints at that clock.
    taint_starts: dict[int, list[datetime.date | datetime.datetime]] = {}
    for item in parsed:
        if item.home_team_id in ambiguous_team_ids or item.away_team_id in ambiguous_team_ids:
            continue
        if item.source_local_kickoff is None or item.fixture_identifier in temporal_collisions:
            start: datetime.date | datetime.datetime = item.source_local_kickoff or item.source_local_date
            taint_starts.setdefault(item.home_team_id, []).append(start)
            taint_starts.setdefault(item.away_team_id, []).append(start)

    histories: dict[int, list[tuple[datetime.datetime, str]]] = {}
    ratings: dict[int, dict[str, int]] = {}
    fixtures: list[HistoricalReplayFixture] = []
    safe = sorted(
        (
            item
            for item in parsed
            if item.source_local_kickoff is not None
            and item.fixture_identifier not in temporal_collisions
            and item.home_team_id not in ambiguous_team_ids
            and item.away_team_id not in ambiguous_team_ids
        ),
        key=lambda item: (item.source_local_kickoff, item.fixture_identifier),
    )
    replayed: dict[str, HistoricalReplayFixture] = {}
    for item in safe:
        assert item.source_local_kickoff is not None
        if _is_temporally_tainted(taint_starts, item.home_team_id, item.source_local_kickoff) or _is_temporally_tainted(taint_starts, item.away_team_id, item.source_local_kickoff):
            replayed[item.fixture_identifier] = _fixture(
                item,
                features=_blocked_features(HistoricalFeatureReplayStatus.BLOCKED_TEMPORAL_AMBIGUITY),
            )
            # Do not update either side.  In particular, a tainted team may
            # not propagate a fabricated Elo update to an otherwise clean
            # opponent. Its known outcome also cannot restore that opponent's
            # clean replay state, so the ambiguity propagates prospectively.
            taint_starts.setdefault(item.home_team_id, []).append(item.source_local_kickoff)
            taint_starts.setdefault(item.away_team_id, []).append(item.source_local_kickoff)
            continue
        home_history = histories.get(item.home_team_id, [])
        away_history = histories.get(item.away_team_id, [])
        home_form = _replace_feature_id(_form(home_history, item.source_local_kickoff), ModelFeatureId.HOME_FORM)
        away_form = _replace_feature_id(_form(away_history, item.source_local_kickoff), ModelFeatureId.AWAY_FORM)
        fatigue = _fatigue(home_history[-1][0] if home_history else None, away_history[-1][0] if away_history else None, item.source_local_kickoff)
        home_rating = ratings.setdefault(item.home_team_id, {"overall": 1500, "home": 1500, "away": 1500, "matches": 0})
        away_rating = ratings.setdefault(item.away_team_id, {"overall": 1500, "home": 1500, "away": 1500, "matches": 0})
        home_elo = _feature(ModelFeatureId.HOME_ELO, HistoricalFeatureReplayStatus.AVAILABLE_RESEARCH_REPLAY, home_rating["overall"], "DERIVED_HISTORICAL_ELO_REPLAY", initial=home_rating["matches"] == 0)
        away_elo = _feature(ModelFeatureId.AWAY_ELO, HistoricalFeatureReplayStatus.AVAILABLE_RESEARCH_REPLAY, away_rating["overall"], "DERIVED_HISTORICAL_ELO_REPLAY", initial=away_rating["matches"] == 0)
        freshness = _feature(ModelFeatureId.LIVE_DATA_FRESHNESS, HistoricalFeatureReplayStatus.NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE, None, "NO_RETAINED_PRE_KICKOFF_FRESHNESS_EVIDENCE")
        feature_map = {value.feature_id: value for value in (home_form, away_form, home_elo, away_elo, fatigue, freshness)}
        feature_values = tuple(feature_map[key] for key in _REPLAY_FEATURE_IDS)
        replayed[item.fixture_identifier] = _fixture(item, features=feature_values)
        home_expected = _expected_score(home_rating["overall"], away_rating["overall"], home_boost=True)
        away_expected = _expected_score(away_rating["overall"], home_rating["overall"], home_boost=False)
        home_score = 1.0 if item.home_goals > item.away_goals else 0.5 if item.home_goals == item.away_goals else 0.0
        away_score = 1.0 - home_score
        home_k, away_k = _k_factor(home_rating["matches"]), _k_factor(away_rating["matches"])
        home_delta, away_delta = home_k * (home_score - home_expected), away_k * (away_score - away_expected)
        home_rating["overall"], away_rating["overall"] = int(home_rating["overall"] + home_delta), int(away_rating["overall"] + away_delta)
        home_rating["home"], away_rating["away"] = int(home_rating["home"] + home_delta), int(away_rating["away"] + away_delta)
        home_rating["matches"] += 1
        away_rating["matches"] += 1
        histories.setdefault(item.home_team_id, []).append((item.source_local_kickoff, "W" if home_score == 1.0 else "D" if home_score == 0.5 else "L"))
        histories.setdefault(item.away_team_id, []).append((item.source_local_kickoff, "W" if away_score == 1.0 else "D" if away_score == 0.5 else "L"))

    for item in parsed:
        if item.fixture_identifier in replayed:
            fixtures.append(replayed[item.fixture_identifier])
            continue
        status = HistoricalFeatureReplayStatus.BLOCKED_IDENTITY_AMBIGUITY if item.home_team_id in ambiguous_team_ids or item.away_team_id in ambiguous_team_ids else HistoricalFeatureReplayStatus.BLOCKED_TEMPORAL_AMBIGUITY
        features = _blocked_features(status)
        fixtures.append(_fixture(item, features=features))
    ordered_fixtures = tuple(sorted(fixtures, key=lambda item: item.fixture_identifier))
    specification = legacy_expected_goals_transform_specification()
    specification_bytes = canonical_legacy_expected_goals_transform_specification_bytes(specification)
    return HistoricalReplayCorpus(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        scope=REPLAY_SCOPE,
        source_files=source_files,
        fixture_count=len(ordered_fixtures),
        source_corpus_sha256=_source_corpus_sha256(source_files),
        target_pr68_transform_id=TRANSFORM_ID,
        target_pr68_transform_spec_sha256=_sha256(specification_bytes),
        fixtures=ordered_fixtures,
        aggregate_coverage=_coverage(ordered_fixtures),
        safety=_default_safety(),
    )


def historical_model_feature_replay_corpus_to_dict(value: Any) -> dict[str, Any]:
    if type(value) is not HistoricalReplayCorpus:
        raise _error("value must be exact historical replay corpus")
    return value.to_dict()


def canonical_historical_model_feature_replay_corpus_bytes(value: Any) -> bytes:
    return _canonical_json_bytes(historical_model_feature_replay_corpus_to_dict(value))


def sha256_historical_model_feature_replay_corpus(value: Any) -> str:
    return _sha256(canonical_historical_model_feature_replay_corpus_bytes(value))


def revalidate_historical_model_feature_replay_corpus(
    *,
    source_inputs: Sequence[HistoricalReplaySourceInput],
    corpus: HistoricalReplayCorpus,
    corpus_bytes: bytes,
) -> HistoricalReplayCorpus:
    """Rebuild from exact source bytes and reject detached or local mutation."""

    if type(corpus) is not HistoricalReplayCorpus or type(corpus_bytes) is not bytes:
        raise _error("corpus and corpus_bytes must be exact immutable artifact values")
    supplied = canonical_historical_model_feature_replay_corpus_bytes(corpus)
    rebuilt = build_historical_model_feature_replay_corpus(source_inputs)
    exact = canonical_historical_model_feature_replay_corpus_bytes(rebuilt)
    if supplied != exact:
        raise _error("supplied corpus differs from exact source-byte rebuild")
    if corpus_bytes != exact:
        raise _error("corpus_bytes are not exact canonical source-byte replay bytes")
    return rebuilt


__all__ = [
    "DATASET_NAME",
    "MISSING_SOURCE_TIME",
    "PR31_FATIGUE_SEMANTIC_EQUIVALENCE",
    "REPLAY_SCOPE",
    "SCHEMA_VERSION",
    "SOURCE",
    "SOURCE_LOCAL_TIMEZONE_UNRESOLVED",
    "HistoricalFeatureReplayStatus",
    "HistoricalModelFeatureReplayCandidateError",
    "HistoricalReplayCorpus",
    "HistoricalReplayFeatureValue",
    "HistoricalReplayFixture",
    "HistoricalReplaySourceFile",
    "HistoricalReplaySourceInput",
    "build_historical_model_feature_replay_corpus",
    "canonical_historical_model_feature_replay_corpus_bytes",
    "historical_model_feature_replay_corpus_to_dict",
    "revalidate_historical_model_feature_replay_corpus",
    "sha256_historical_model_feature_replay_corpus",
]
