"""Provenance-backed, explicitly unreviewed FotMob fixture candidates."""

from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import re
import types
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any, Tuple

from domain.fotmob_data_matches_capture import (
    DATASET_NAME as SOURCE_CAPTURE_DATASET_NAME,
    MAX_RESPONSE_BYTES,
    SCHEMA_VERSION as SOURCE_CAPTURE_SCHEMA_VERSION,
    FotMobDataMatchesCaptureError,
    FotMobDataMatchesCaptureManifest,
    serialize_utc,
    sha256_data_matches_capture_manifest,
)
from domain.fotmob_data_matches_schema import (
    FotMobDataMatchesSchemaError,
    assess_fotmob_data_matches_schema,
    sha256_data_matches_schema_assessment,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-fixture-candidates-v1"
SOURCE_NAME = "FOTMOB"
SUMMARY_SCHEMA_VERSION = 1
SUMMARY_DATASET_NAME = "athena-fotmob-fixture-candidate-build-summary-v1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "raw_json_capture_authorized",
        "schema_assessment_authorized",
        "fixture_candidate_generation_authorized",
        "team_identity_resolution_authorized",
        "competition_identity_resolution_authorized",
        "fixture_identity_resolution_authorized",
        "source_qualified",
        "fixture_promotion_authorized",
        "intelligence_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)


class FotMobFixtureCandidateError(ValueError):
    """Raised when unreviewed candidate evidence fails closed."""


class FixtureCandidateReviewStatus(str, enum.Enum):
    UNREVIEWED = "UNREVIEWED"


def _exact_int(value: Any, label: str, *, minimum: int | None = None) -> int:
    if type(value) is not int or (minimum is not None and value < minimum):
        qualifier = f" >= {minimum}" if minimum is not None else ""
        raise FotMobFixtureCandidateError(f"{label} must be an exact integer{qualifier}")
    return value


def _exact_str(value: Any, label: str) -> str:
    if type(value) is not str:
        raise FotMobFixtureCandidateError(f"{label} must be an exact string")
    return value


def _sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise FotMobFixtureCandidateError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FotMobFixtureCandidateError(f"{label} must be a datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise FotMobFixtureCandidateError(f"{label} must be timezone-aware")
        return value.astimezone(datetime.timezone.utc)
    except FotMobFixtureCandidateError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobFixtureCandidateError(f"{label} is invalid") from exc


def _reviewed_kickoff(value: Any) -> datetime.datetime:
    text = _exact_str(value, "status.utcTime")
    if not text.endswith("Z"):
        raise FotMobFixtureCandidateError("status.utcTime must end in Z")
    try:
        parsed = datetime.datetime.fromisoformat(text[:-1] + "+00:00")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobFixtureCandidateError("status.utcTime is invalid") from exc
    return _utc(parsed, "status.utcTime")


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobFixtureCandidateError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise FotMobFixtureCandidateError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(dict(detached))


def _manifest_sha_tuple(value: Any, label: str) -> Tuple[str, ...]:
    if type(value) is not tuple or not value:
        raise FotMobFixtureCandidateError(f"{label} must be a non-empty tuple")
    validated = tuple(_sha256(item, label) for item in value)
    if validated != tuple(sorted(set(validated))):
        raise FotMobFixtureCandidateError(f"{label} must be sorted and unique")
    return validated


@dataclasses.dataclass(frozen=True)
class FotMobFixtureCandidateSource:
    source_capture_dataset_name: str
    source_capture_schema_version: int
    source_capture_manifest_sha256: str
    source_raw_sha256: str
    source_raw_size: int
    source_observed_at: datetime.datetime
    request_date: str
    timezone: str
    ccode3: str
    schema_assessment_sha256: str
    candidate_count: int

    def __post_init__(self) -> None:
        if self.source_capture_dataset_name != SOURCE_CAPTURE_DATASET_NAME:
            raise FotMobFixtureCandidateError("source capture dataset must be PR #38 v1")
        if (
            type(self.source_capture_schema_version) is not int
            or self.source_capture_schema_version != SOURCE_CAPTURE_SCHEMA_VERSION
        ):
            raise FotMobFixtureCandidateError("source capture schema must be exact integer 1")
        object.__setattr__(
            self,
            "source_capture_manifest_sha256",
            _sha256(self.source_capture_manifest_sha256, "source_capture_manifest_sha256"),
        )
        object.__setattr__(
            self, "source_raw_sha256", _sha256(self.source_raw_sha256, "source_raw_sha256")
        )
        if (
            type(self.source_raw_size) is not int
            or not 0 < self.source_raw_size <= MAX_RESPONSE_BYTES
        ):
            raise FotMobFixtureCandidateError("source_raw_size must be within 8 MiB")
        object.__setattr__(
            self, "source_observed_at", _utc(self.source_observed_at, "source_observed_at")
        )
        for label in ("request_date", "timezone", "ccode3"):
            _exact_str(getattr(self, label), label)
        object.__setattr__(
            self,
            "schema_assessment_sha256",
            _sha256(self.schema_assessment_sha256, "schema_assessment_sha256"),
        )
        _exact_int(self.candidate_count, "candidate_count", minimum=0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_capture_dataset_name": self.source_capture_dataset_name,
            "source_capture_schema_version": self.source_capture_schema_version,
            "source_capture_manifest_sha256": self.source_capture_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "source_raw_size": self.source_raw_size,
            "source_observed_at": serialize_utc(self.source_observed_at),
            "request_date": self.request_date,
            "timezone": self.timezone,
            "ccode3": self.ccode3,
            "schema_assessment_sha256": self.schema_assessment_sha256,
            "candidate_count": self.candidate_count,
        }


@dataclasses.dataclass(frozen=True)
class FotMobFixtureCandidate:
    review_status: FixtureCandidateReviewStatus
    source: str
    source_match_id: int
    source_league_id: int
    source_competition_primary_id: int
    source_competition_name: str
    source_competition_ccode: str
    home_source_team_id: int
    home_name: str
    home_long_name: str
    away_source_team_id: int
    away_name: str
    away_long_name: str
    kickoff_utc: datetime.datetime
    source_capture_manifest_sha256: str
    source_raw_sha256: str
    source_request_date: str
    source_observed_at: datetime.datetime

    def __post_init__(self) -> None:
        if self.review_status is not FixtureCandidateReviewStatus.UNREVIEWED:
            raise FotMobFixtureCandidateError("candidate review status must be UNREVIEWED")
        if self.source != SOURCE_NAME:
            raise FotMobFixtureCandidateError("candidate source must be FOTMOB")
        for label in (
            "source_match_id",
            "source_league_id",
            "source_competition_primary_id",
            "home_source_team_id",
            "away_source_team_id",
        ):
            _exact_int(getattr(self, label), label)
        for label in (
            "source_competition_name",
            "source_competition_ccode",
            "home_name",
            "home_long_name",
            "away_name",
            "away_long_name",
            "source_request_date",
        ):
            _exact_str(getattr(self, label), label)
        object.__setattr__(self, "kickoff_utc", _utc(self.kickoff_utc, "kickoff_utc"))
        object.__setattr__(
            self,
            "source_capture_manifest_sha256",
            _sha256(self.source_capture_manifest_sha256, "source_capture_manifest_sha256"),
        )
        object.__setattr__(
            self, "source_raw_sha256", _sha256(self.source_raw_sha256, "source_raw_sha256")
        )
        object.__setattr__(
            self, "source_observed_at", _utc(self.source_observed_at, "source_observed_at")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_status": self.review_status.value,
            "source": self.source,
            "source_match_id": self.source_match_id,
            "source_league_id": self.source_league_id,
            "source_competition_primary_id": self.source_competition_primary_id,
            "source_competition_name": self.source_competition_name,
            "source_competition_ccode": self.source_competition_ccode,
            "home_source_team_id": self.home_source_team_id,
            "home_name": self.home_name,
            "home_long_name": self.home_long_name,
            "away_source_team_id": self.away_source_team_id,
            "away_name": self.away_name,
            "away_long_name": self.away_long_name,
            "kickoff_utc": serialize_utc(self.kickoff_utc),
            "source_capture_manifest_sha256": self.source_capture_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "source_request_date": self.source_request_date,
            "source_observed_at": serialize_utc(self.source_observed_at),
        }


@dataclasses.dataclass(frozen=True)
class FotMobTeamIdentityVariant:
    name: str
    long_name: str
    source_capture_manifest_sha256s: Tuple[str, ...]

    def __post_init__(self) -> None:
        _exact_str(self.name, "name")
        _exact_str(self.long_name, "long_name")
        object.__setattr__(
            self,
            "source_capture_manifest_sha256s",
            _manifest_sha_tuple(
                self.source_capture_manifest_sha256s,
                "source_capture_manifest_sha256s",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "long_name": self.long_name,
            "source_capture_manifest_sha256s": list(self.source_capture_manifest_sha256s),
        }


@dataclasses.dataclass(frozen=True)
class FotMobTeamIdentityConflict:
    source_team_id: int
    variants: Tuple[FotMobTeamIdentityVariant, ...]

    def __post_init__(self) -> None:
        _exact_int(self.source_team_id, "source_team_id")
        if type(self.variants) is not tuple or len(self.variants) < 2:
            raise FotMobFixtureCandidateError("team conflict requires at least two variants")
        if any(not isinstance(item, FotMobTeamIdentityVariant) for item in self.variants):
            raise FotMobFixtureCandidateError("team conflict variants are invalid")
        keys = tuple((item.name, item.long_name) for item in self.variants)
        if keys != tuple(sorted(keys)):
            raise FotMobFixtureCandidateError("team conflict variants must be sorted")
        if len(set(keys)) != len(keys):
            raise FotMobFixtureCandidateError("team conflict variant identities must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {"source_team_id": self.source_team_id, "variants": [v.to_dict() for v in self.variants]}


@dataclasses.dataclass(frozen=True)
class FotMobCompetitionIdentityVariant:
    name: str
    ccode: str
    primary_id: int
    source_capture_manifest_sha256s: Tuple[str, ...]

    def __post_init__(self) -> None:
        _exact_str(self.name, "name")
        _exact_str(self.ccode, "ccode")
        _exact_int(self.primary_id, "primary_id")
        object.__setattr__(
            self,
            "source_capture_manifest_sha256s",
            _manifest_sha_tuple(
                self.source_capture_manifest_sha256s,
                "source_capture_manifest_sha256s",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ccode": self.ccode,
            "primary_id": self.primary_id,
            "source_capture_manifest_sha256s": list(self.source_capture_manifest_sha256s),
        }


@dataclasses.dataclass(frozen=True)
class FotMobCompetitionIdentityConflict:
    source_league_id: int
    variants: Tuple[FotMobCompetitionIdentityVariant, ...]

    def __post_init__(self) -> None:
        _exact_int(self.source_league_id, "source_league_id")
        if type(self.variants) is not tuple or len(self.variants) < 2:
            raise FotMobFixtureCandidateError("competition conflict requires at least two variants")
        if any(not isinstance(item, FotMobCompetitionIdentityVariant) for item in self.variants):
            raise FotMobFixtureCandidateError("competition conflict variants are invalid")
        keys = tuple((item.name, item.ccode, item.primary_id) for item in self.variants)
        if keys != tuple(sorted(keys)):
            raise FotMobFixtureCandidateError("competition conflict variants must be sorted")
        if len(set(keys)) != len(keys):
            raise FotMobFixtureCandidateError("competition conflict variant identities must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {"source_league_id": self.source_league_id, "variants": [v.to_dict() for v in self.variants]}


@dataclasses.dataclass(frozen=True)
class FotMobFixtureIdentityVariant:
    source_league_id: int
    home_source_team_id: int
    away_source_team_id: int
    kickoff_utc: datetime.datetime
    source_capture_manifest_sha256s: Tuple[str, ...]

    def __post_init__(self) -> None:
        for label in ("source_league_id", "home_source_team_id", "away_source_team_id"):
            _exact_int(getattr(self, label), label)
        object.__setattr__(self, "kickoff_utc", _utc(self.kickoff_utc, "kickoff_utc"))
        object.__setattr__(
            self,
            "source_capture_manifest_sha256s",
            _manifest_sha_tuple(
                self.source_capture_manifest_sha256s,
                "source_capture_manifest_sha256s",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_league_id": self.source_league_id,
            "home_source_team_id": self.home_source_team_id,
            "away_source_team_id": self.away_source_team_id,
            "kickoff_utc": serialize_utc(self.kickoff_utc),
            "source_capture_manifest_sha256s": list(self.source_capture_manifest_sha256s),
        }


@dataclasses.dataclass(frozen=True)
class FotMobFixtureIdentityConflict:
    source_match_id: int
    variants: Tuple[FotMobFixtureIdentityVariant, ...]

    def __post_init__(self) -> None:
        _exact_int(self.source_match_id, "source_match_id")
        if type(self.variants) is not tuple or len(self.variants) < 2:
            raise FotMobFixtureCandidateError("fixture conflict requires at least two variants")
        if any(not isinstance(item, FotMobFixtureIdentityVariant) for item in self.variants):
            raise FotMobFixtureCandidateError("fixture conflict variants are invalid")
        keys = tuple(_fixture_variant_sort_key(item) for item in self.variants)
        if keys != tuple(sorted(keys)):
            raise FotMobFixtureCandidateError("fixture conflict variants must be sorted")
        if len(set(keys)) != len(keys):
            raise FotMobFixtureCandidateError("fixture conflict variant identities must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {"source_match_id": self.source_match_id, "variants": [v.to_dict() for v in self.variants]}


def _fixture_variant_sort_key(value: FotMobFixtureIdentityVariant) -> tuple[Any, ...]:
    return (
        value.source_league_id,
        value.home_source_team_id,
        value.away_source_team_id,
        value.kickoff_utc,
    )


@dataclasses.dataclass(frozen=True)
class FotMobFixtureCandidateBundle:
    schema_version: int
    dataset_name: str
    sources: Tuple[FotMobFixtureCandidateSource, ...]
    candidate_count: int
    candidates: Tuple[FotMobFixtureCandidate, ...]
    duplicate_source_match_id_count: int
    fixture_identity_conflict_count: int
    fixture_identity_conflicts: Tuple[FotMobFixtureIdentityConflict, ...]
    team_identity_conflict_count: int
    team_identity_conflicts: Tuple[FotMobTeamIdentityConflict, ...]
    competition_identity_conflict_count: int
    competition_identity_conflicts: Tuple[FotMobCompetitionIdentityConflict, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobFixtureCandidateError("schema_version must be exact integer 1")
        if self.dataset_name != DATASET_NAME:
            raise FotMobFixtureCandidateError(f"dataset_name must be {DATASET_NAME}")
        if type(self.sources) is not tuple or not self.sources or any(
            not isinstance(item, FotMobFixtureCandidateSource) for item in self.sources
        ):
            raise FotMobFixtureCandidateError("sources must be a non-empty source tuple")
        if self.sources != tuple(
            sorted(self.sources, key=lambda item: (item.request_date, item.source_capture_manifest_sha256))
        ):
            raise FotMobFixtureCandidateError("sources must be deterministically sorted")
        if len({item.source_capture_manifest_sha256 for item in self.sources}) != len(self.sources):
            raise FotMobFixtureCandidateError("source manifests must be unique")
        if type(self.candidates) is not tuple or any(
            not isinstance(item, FotMobFixtureCandidate) for item in self.candidates
        ):
            raise FotMobFixtureCandidateError("candidates must be an immutable candidate tuple")
        if self.candidates != tuple(sorted(self.candidates, key=_candidate_sort_key)):
            raise FotMobFixtureCandidateError("candidates must be deterministically sorted")
        _exact_int(self.candidate_count, "candidate_count", minimum=0)
        if self.candidate_count != len(self.candidates):
            raise FotMobFixtureCandidateError("candidate_count mismatch")
        if sum(item.candidate_count for item in self.sources) != self.candidate_count:
            raise FotMobFixtureCandidateError("source candidate counts do not equal bundle count")

        source_map = {item.source_capture_manifest_sha256: item for item in self.sources}
        source_candidate_counts = {manifest_sha: 0 for manifest_sha in source_map}
        for candidate in self.candidates:
            source = source_map.get(candidate.source_capture_manifest_sha256)
            if source is None:
                raise FotMobFixtureCandidateError("candidate source ancestry is absent")
            if (
                candidate.source_raw_sha256 != source.source_raw_sha256
                or candidate.source_request_date != source.request_date
                or candidate.source_observed_at != source.source_observed_at
            ):
                raise FotMobFixtureCandidateError("candidate source ancestry mismatch")
            source_candidate_counts[candidate.source_capture_manifest_sha256] += 1
        for source in self.sources:
            if source.candidate_count != source_candidate_counts[source.source_capture_manifest_sha256]:
                raise FotMobFixtureCandidateError("source candidate count mismatch")

        source_manifest_shas = set(source_map)
        self._validate_conflicts(source_manifest_shas)

        expected_duplicates, expected_fixture_conflicts = _make_fixture_observations(self.candidates)
        expected_team_conflicts = _make_team_conflicts(self.candidates)
        expected_competition_conflicts = _make_competition_conflicts(self.candidates)
        _exact_int(self.duplicate_source_match_id_count, "duplicate_source_match_id_count", minimum=0)
        if self.duplicate_source_match_id_count != expected_duplicates:
            raise FotMobFixtureCandidateError("duplicate source match ID count mismatch")

        derived_conflicts = (
            (
                "fixture_identity_conflict_count",
                self.fixture_identity_conflicts,
                expected_fixture_conflicts,
            ),
            (
                "team_identity_conflict_count",
                self.team_identity_conflicts,
                expected_team_conflicts,
            ),
            (
                "competition_identity_conflict_count",
                self.competition_identity_conflicts,
                expected_competition_conflicts,
            ),
        )
        for label, supplied, expected in derived_conflicts:
            if supplied != expected or getattr(self, label) != len(expected):
                raise FotMobFixtureCandidateError(f"{label} does not match candidate-derived conflicts")

        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def _validate_conflicts(self, source_manifest_shas: set[str]) -> None:
        specifications = (
            (
                "fixture_identity_conflict_count",
                self.fixture_identity_conflicts,
                FotMobFixtureIdentityConflict,
                lambda item: item.source_match_id,
            ),
            (
                "team_identity_conflict_count",
                self.team_identity_conflicts,
                FotMobTeamIdentityConflict,
                lambda item: item.source_team_id,
            ),
            (
                "competition_identity_conflict_count",
                self.competition_identity_conflicts,
                FotMobCompetitionIdentityConflict,
                lambda item: item.source_league_id,
            ),
        )
        for label, values, expected_type, key in specifications:
            if type(values) is not tuple or any(not isinstance(item, expected_type) for item in values):
                raise FotMobFixtureCandidateError(f"{label} conflict tuple is invalid")
            keys = tuple(key(item) for item in values)
            if keys != tuple(sorted(keys)):
                raise FotMobFixtureCandidateError(f"{label} conflicts must be sorted")
            if len(set(keys)) != len(keys):
                raise FotMobFixtureCandidateError(f"{label} conflict keys must be unique")
            for conflict in values:
                for variant in conflict.variants:
                    if not set(variant.source_capture_manifest_sha256s).issubset(source_manifest_shas):
                        raise FotMobFixtureCandidateError(
                            f"{label} conflict variant source ancestry is absent"
                        )
            count = getattr(self, label)
            _exact_int(count, label, minimum=0)
            if count != len(values):
                raise FotMobFixtureCandidateError(f"{label} mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "sources": [item.to_dict() for item in self.sources],
            "candidate_count": self.candidate_count,
            "candidates": [item.to_dict() for item in self.candidates],
            "duplicate_source_match_id_count": self.duplicate_source_match_id_count,
            "fixture_identity_conflict_count": self.fixture_identity_conflict_count,
            "fixture_identity_conflicts": [item.to_dict() for item in self.fixture_identity_conflicts],
            "team_identity_conflict_count": self.team_identity_conflict_count,
            "team_identity_conflicts": [item.to_dict() for item in self.team_identity_conflicts],
            "competition_identity_conflict_count": self.competition_identity_conflict_count,
            "competition_identity_conflicts": [item.to_dict() for item in self.competition_identity_conflicts],
            "safety": dict(self.safety),
        }


def _candidate_sort_key(value: FotMobFixtureCandidate) -> tuple[Any, ...]:
    return (value.kickoff_utc, value.source_match_id, value.source_capture_manifest_sha256)


def _reject_duplicate_keys(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FotMobFixtureCandidateError(f"duplicate response JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise FotMobFixtureCandidateError(f"invalid response JSON constant: {value}")


def _strict_json(raw_json: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(
            raw_json.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except FotMobFixtureCandidateError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobFixtureCandidateError("response is not strict UTF-8 JSON") from exc
    if type(payload) is not dict:
        raise FotMobFixtureCandidateError("response top level must be an object")
    return payload


def _validated_capture(
    raw_json: Any,
    source_manifest: Any,
) -> tuple[bytes, FotMobDataMatchesCaptureManifest, str]:
    if type(raw_json) is not bytes or not raw_json or len(raw_json) > MAX_RESPONSE_BYTES:
        raise FotMobFixtureCandidateError("raw capture must be non-empty exact bytes within 8 MiB")
    if not isinstance(source_manifest, FotMobDataMatchesCaptureManifest):
        raise FotMobFixtureCandidateError("source manifest must be a PR #38 manifest")
    try:
        manifest = dataclasses.replace(source_manifest)
    except FotMobDataMatchesCaptureError as exc:
        raise FotMobFixtureCandidateError("source manifest is invalid") from exc
    if (
        manifest.dataset_name != SOURCE_CAPTURE_DATASET_NAME
        or manifest.schema_version != SOURCE_CAPTURE_SCHEMA_VERSION
    ):
        raise FotMobFixtureCandidateError("source manifest must be PR #38 v1")
    if len(raw_json) != manifest.raw_size:
        raise FotMobFixtureCandidateError("raw capture size does not match manifest")
    if hashlib.sha256(raw_json).hexdigest() != manifest.raw_sha256:
        raise FotMobFixtureCandidateError("raw capture SHA-256 does not match manifest")
    manifest_sha = sha256_data_matches_capture_manifest(manifest)
    return raw_json, manifest, manifest_sha


def _make_team_conflicts(
    candidates: Sequence[FotMobFixtureCandidate],
) -> Tuple[FotMobTeamIdentityConflict, ...]:
    observations: dict[int, dict[tuple[str, str], set[str]]] = defaultdict(lambda: defaultdict(set))
    for item in candidates:
        observations[item.home_source_team_id][(item.home_name, item.home_long_name)].add(
            item.source_capture_manifest_sha256
        )
        observations[item.away_source_team_id][(item.away_name, item.away_long_name)].add(
            item.source_capture_manifest_sha256
        )
    conflicts = []
    for source_id, variants in observations.items():
        if len(variants) > 1:
            conflicts.append(
                FotMobTeamIdentityConflict(
                    source_team_id=source_id,
                    variants=tuple(
                        FotMobTeamIdentityVariant(name, long_name, tuple(sorted(manifests)))
                        for (name, long_name), manifests in sorted(variants.items())
                    ),
                )
            )
    return tuple(sorted(conflicts, key=lambda item: item.source_team_id))


def _make_competition_conflicts(
    candidates: Sequence[FotMobFixtureCandidate],
) -> Tuple[FotMobCompetitionIdentityConflict, ...]:
    observations: dict[int, dict[tuple[str, str, int], set[str]]] = defaultdict(lambda: defaultdict(set))
    for item in candidates:
        observations[item.source_league_id][
            (
                item.source_competition_name,
                item.source_competition_ccode,
                item.source_competition_primary_id,
            )
        ].add(item.source_capture_manifest_sha256)
    conflicts = []
    for league_id, variants in observations.items():
        if len(variants) > 1:
            conflicts.append(
                FotMobCompetitionIdentityConflict(
                    source_league_id=league_id,
                    variants=tuple(
                        FotMobCompetitionIdentityVariant(
                            name, ccode, primary_id, tuple(sorted(manifests))
                        )
                        for (name, ccode, primary_id), manifests in sorted(variants.items())
                    ),
                )
            )
    return tuple(sorted(conflicts, key=lambda item: item.source_league_id))


def _make_fixture_observations(
    candidates: Sequence[FotMobFixtureCandidate],
) -> tuple[int, Tuple[FotMobFixtureIdentityConflict, ...]]:
    occurrences: dict[int, dict[tuple[int, int, int, datetime.datetime], set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for item in candidates:
        occurrences[item.source_match_id][
            (
                item.source_league_id,
                item.home_source_team_id,
                item.away_source_team_id,
                item.kickoff_utc,
            )
        ].add(item.source_capture_manifest_sha256)
    duplicate_count = sum(
        1
        for variants in occurrences.values()
        if len(set().union(*variants.values())) > 1
    )
    conflicts = []
    for match_id, variants in occurrences.items():
        if len(variants) > 1:
            conflicts.append(
                FotMobFixtureIdentityConflict(
                    source_match_id=match_id,
                    variants=tuple(
                        sorted(
                            (
                                FotMobFixtureIdentityVariant(
                                    league_id,
                                    home_id,
                                    away_id,
                                    kickoff,
                                    tuple(sorted(manifests)),
                                )
                                for (league_id, home_id, away_id, kickoff), manifests in variants.items()
                            ),
                            key=_fixture_variant_sort_key,
                        )
                    ),
                )
            )
    return duplicate_count, tuple(sorted(conflicts, key=lambda item: item.source_match_id))


def build_fotmob_fixture_candidate_bundle(
    captures: Sequence[tuple[bytes, FotMobDataMatchesCaptureManifest]],
) -> FotMobFixtureCandidateBundle:
    """Build deterministic UNREVIEWED candidates after PR #39 assessment."""

    if not isinstance(captures, Sequence) or isinstance(captures, (str, bytes)) or not captures:
        raise FotMobFixtureCandidateError("at least one capture is required")
    sources: list[FotMobFixtureCandidateSource] = []
    candidates: list[FotMobFixtureCandidate] = []
    seen_manifest_shas: set[str] = set()
    for entry in captures:
        if type(entry) is not tuple or len(entry) != 2:
            raise FotMobFixtureCandidateError("each capture must be a (bytes, manifest) tuple")
        raw, manifest, manifest_sha = _validated_capture(entry[0], entry[1])
        if manifest_sha in seen_manifest_shas:
            raise FotMobFixtureCandidateError("duplicate source manifest input")
        seen_manifest_shas.add(manifest_sha)
        try:
            assessment = assess_fotmob_data_matches_schema(raw, manifest)
        except FotMobDataMatchesSchemaError as exc:
            raise FotMobFixtureCandidateError("PR #39 schema assessment failed") from exc
        assessment_sha = sha256_data_matches_schema_assessment(assessment)
        payload = _strict_json(raw)
        source_candidates: list[FotMobFixtureCandidate] = []
        for league in payload["leagues"]:
            for match in league["matches"]:
                home = match["home"]
                away = match["away"]
                source_candidates.append(
                    FotMobFixtureCandidate(
                        review_status=FixtureCandidateReviewStatus.UNREVIEWED,
                        source=SOURCE_NAME,
                        source_match_id=match["id"],
                        source_league_id=league["id"],
                        source_competition_primary_id=league["primaryId"],
                        source_competition_name=league["name"],
                        source_competition_ccode=league["ccode"],
                        home_source_team_id=home["id"],
                        home_name=home["name"],
                        home_long_name=home["longName"],
                        away_source_team_id=away["id"],
                        away_name=away["name"],
                        away_long_name=away["longName"],
                        kickoff_utc=_reviewed_kickoff(match["status"]["utcTime"]),
                        source_capture_manifest_sha256=manifest_sha,
                        source_raw_sha256=manifest.raw_sha256,
                        source_request_date=manifest.request_date,
                        source_observed_at=manifest.observed_at,
                    )
                )
        if len(source_candidates) != assessment.match_count:
            raise FotMobFixtureCandidateError("assessment and extraction match counts differ")
        sources.append(
            FotMobFixtureCandidateSource(
                source_capture_dataset_name=manifest.dataset_name,
                source_capture_schema_version=manifest.schema_version,
                source_capture_manifest_sha256=manifest_sha,
                source_raw_sha256=manifest.raw_sha256,
                source_raw_size=manifest.raw_size,
                source_observed_at=manifest.observed_at,
                request_date=manifest.request_date,
                timezone=manifest.timezone,
                ccode3=manifest.ccode3,
                schema_assessment_sha256=assessment_sha,
                candidate_count=len(source_candidates),
            )
        )
        candidates.extend(source_candidates)
    sorted_sources = tuple(
        sorted(sources, key=lambda item: (item.request_date, item.source_capture_manifest_sha256))
    )
    sorted_candidates = tuple(sorted(candidates, key=_candidate_sort_key))
    duplicate_count, fixture_conflicts = _make_fixture_observations(sorted_candidates)
    team_conflicts = _make_team_conflicts(sorted_candidates)
    competition_conflicts = _make_competition_conflicts(sorted_candidates)
    return FotMobFixtureCandidateBundle(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        sources=sorted_sources,
        candidate_count=len(sorted_candidates),
        candidates=sorted_candidates,
        duplicate_source_match_id_count=duplicate_count,
        fixture_identity_conflict_count=len(fixture_conflicts),
        fixture_identity_conflicts=fixture_conflicts,
        team_identity_conflict_count=len(team_conflicts),
        team_identity_conflicts=team_conflicts,
        competition_identity_conflict_count=len(competition_conflicts),
        competition_identity_conflicts=competition_conflicts,
        safety=_default_safety(),
    )


def fotmob_fixture_candidate_bundle_to_dict(bundle: Any) -> dict[str, Any]:
    if not isinstance(bundle, FotMobFixtureCandidateBundle):
        raise FotMobFixtureCandidateError("bundle must be FotMobFixtureCandidateBundle")
    return bundle.to_dict()


def canonical_fotmob_fixture_candidate_bundle_bytes(bundle: Any) -> bytes:
    if not isinstance(bundle, FotMobFixtureCandidateBundle):
        raise FotMobFixtureCandidateError("bundle must be FotMobFixtureCandidateBundle")
    try:
        return (
            json.dumps(
                bundle.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobFixtureCandidateError("bundle serialization failed") from exc


def sha256_fotmob_fixture_candidate_bundle(bundle: Any) -> str:
    return hashlib.sha256(canonical_fotmob_fixture_candidate_bundle_bytes(bundle)).hexdigest()


__all__ = [
    "DATASET_NAME",
    "SCHEMA_VERSION",
    "SOURCE_NAME",
    "SUMMARY_DATASET_NAME",
    "SUMMARY_SCHEMA_VERSION",
    "FixtureCandidateReviewStatus",
    "FotMobCompetitionIdentityConflict",
    "FotMobCompetitionIdentityVariant",
    "FotMobFixtureCandidate",
    "FotMobFixtureCandidateBundle",
    "FotMobFixtureCandidateError",
    "FotMobFixtureCandidateSource",
    "FotMobFixtureIdentityConflict",
    "FotMobFixtureIdentityVariant",
    "FotMobTeamIdentityConflict",
    "FotMobTeamIdentityVariant",
    "build_fotmob_fixture_candidate_bundle",
    "canonical_fotmob_fixture_candidate_bundle_bytes",
    "fotmob_fixture_candidate_bundle_to_dict",
    "sha256_fotmob_fixture_candidate_bundle",
]
