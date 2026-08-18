"""Fail-closed SportyBet -> FotMob fixture reconciliation candidate contract.

The reviewed SportyBet Lite inventory currently proves provider event IDs and odds,
but it does not yet prove machine-readable competition/participant/kickoff fields.
This boundary therefore accepts only an explicit user-attested event header bound
to a verified PR #154 inventory and compares it against already-reviewed FotMob
catalog inputs with exact equality only.

An exact candidate is evidence for later review. It is not fixture-reconciliation,
pricing, selection, slip, booking-code, execution, or BET authority.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import re
import types
from collections.abc import Iterable, Mapping
from typing import Any

from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native
from domain.fotmob_fixture_candidate_review import FotMobReviewedFixtureCatalogInput
from domain.sportybet_lite_source_capture import (
    SportyBetLiteCaptureError,
    SportyBetLiteRequestKind,
    parse_utc_timestamp,
    serialize_utc,
)

SCHEMA_VERSION = 1
IDENTITY_DATASET_NAME = "athena-sportybet-user-attested-event-identity-v1"
RECONCILIATION_DATASET_NAME = "athena-sportybet-fotmob-exact-reconciliation-candidate-v1"
PROVIDER = "SportyBet"
IDENTITY_AUTHORITY = "USER_ATTESTED_FROM_REVIEWED_SPORTYBET_PAGE"
MATCHING_BASIS = "EXACT_HOME_AWAY_COMPETITION_KICKOFF_NO_FUZZY_NO_REVERSAL"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_EVIDENCE_ID_RE = re.compile(r"^[0-9a-f]{24}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "bet_authorized",
        "bookmaker_equivalence_authorized",
        "canonical_market_mapping_authorized",
        "fixture_reconciliation_authorized",
        "fresh_price_authorized",
        "model_integration_authorized",
        "pricing_authorized",
        "selection_authorized",
        "slip_construction_authorized",
        "sportybet_execution_authorized",
    }
)


class SportyBetFotMobReconciliationError(ValueError):
    """Raised when the SportyBet/FotMob candidate boundary fails closed."""


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise SportyBetFotMobReconciliationError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise SportyBetFotMobReconciliationError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(detached)


def _hash(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise SportyBetFotMobReconciliationError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _evidence_id(value: Any) -> str:
    if type(value) is not str or _EVIDENCE_ID_RE.fullmatch(value) is None:
        raise SportyBetFotMobReconciliationError("source_evidence_id is invalid")
    return value


def _exact_text(value: Any, label: str, *, maximum: int = 512) -> str:
    if type(value) is not str or not value:
        raise SportyBetFotMobReconciliationError(f"{label} must be a non-empty exact string")
    if value != value.strip():
        raise SportyBetFotMobReconciliationError(
            f"{label} must not contain surrounding whitespace"
        )
    if len(value) > maximum:
        raise SportyBetFotMobReconciliationError(
            f"{label} exceeds {maximum} characters"
        )
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise SportyBetFotMobReconciliationError(f"{label} contains control characters")
    return value


def _canonical_utc(value: Any, label: str) -> str:
    if type(value) is not str:
        raise SportyBetFotMobReconciliationError(f"{label} must be a string")
    try:
        parsed = parse_utc_timestamp(value, label)
    except SportyBetLiteCaptureError as exc:
        raise SportyBetFotMobReconciliationError(str(exc)) from exc
    if serialize_utc(parsed) != value:
        raise SportyBetFotMobReconciliationError(
            f"{label} must use canonical UTC serialization"
        )
    return value


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
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
        raise SportyBetFotMobReconciliationError("canonical serialization failed") from exc


@dataclasses.dataclass(frozen=True)
class SportyBetUserAttestedEventIdentity:
    schema_version: int
    dataset_name: str
    provider: str
    source_evidence_id: str
    source_inventory_sha256: str
    source_raw_sha256: str
    source_url: str
    event_id: str
    sport_id: str
    competition_displayed: str
    home_participant_displayed: str
    away_participant_displayed: str
    kickoff_displayed: str
    kickoff_utc_user_attested: str
    observed_at_user_attested: str
    identity_authority: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise SportyBetFotMobReconciliationError("schema_version mismatch")
        if self.dataset_name != IDENTITY_DATASET_NAME or self.provider != PROVIDER:
            raise SportyBetFotMobReconciliationError("identity dataset/provider mismatch")
        _evidence_id(self.source_evidence_id)
        _hash(self.source_inventory_sha256, "source_inventory_sha256")
        _hash(self.source_raw_sha256, "source_raw_sha256")
        if type(self.source_url) is not str or not self.source_url:
            raise SportyBetFotMobReconciliationError("source_url is invalid")
        try:
            kind, event_id, sport_id, _market_group, _target = manual.validate_source_url(
                self.source_url
            )
        except manual.SportyBetUserEvidenceError as exc:
            raise SportyBetFotMobReconciliationError(str(exc)) from exc
        if kind is not SportyBetLiteRequestKind.EVENT_DETAIL:
            raise SportyBetFotMobReconciliationError(
                "event identity requires reviewed SportyBet event-detail evidence"
            )
        if event_id != self.event_id or sport_id != self.sport_id:
            raise SportyBetFotMobReconciliationError(
                "attested provider event/sport identity does not match source URL"
            )
        _exact_text(self.event_id, "event_id", maximum=160)
        _exact_text(self.sport_id, "sport_id", maximum=160)
        competition = _exact_text(self.competition_displayed, "competition_displayed")
        home = _exact_text(self.home_participant_displayed, "home_participant_displayed")
        away = _exact_text(self.away_participant_displayed, "away_participant_displayed")
        _exact_text(self.kickoff_displayed, "kickoff_displayed")
        _canonical_utc(self.kickoff_utc_user_attested, "kickoff_utc_user_attested")
        _canonical_utc(self.observed_at_user_attested, "observed_at_user_attested")
        if home == away:
            raise SportyBetFotMobReconciliationError(
                "home and away participant attestations must differ"
            )
        if self.identity_authority != IDENTITY_AUTHORITY:
            raise SportyBetFotMobReconciliationError("identity_authority mismatch")
        object.__setattr__(self, "competition_displayed", competition)
        object.__setattr__(self, "home_participant_displayed", home)
        object.__setattr__(self, "away_participant_displayed", away)
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "provider": self.provider,
            "source_evidence_id": self.source_evidence_id,
            "source_inventory_sha256": self.source_inventory_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "source_url": self.source_url,
            "event_id": self.event_id,
            "sport_id": self.sport_id,
            "competition_displayed": self.competition_displayed,
            "home_participant_displayed": self.home_participant_displayed,
            "away_participant_displayed": self.away_participant_displayed,
            "kickoff_displayed": self.kickoff_displayed,
            "kickoff_utc_user_attested": self.kickoff_utc_user_attested,
            "observed_at_user_attested": self.observed_at_user_attested,
            "identity_authority": self.identity_authority,
            "safety": dict(self.safety),
        }


def build_user_attested_event_identity(
    inventory: Any,
    *,
    competition_displayed: str,
    home_participant_displayed: str,
    away_participant_displayed: str,
    kickoff_displayed: str,
    kickoff_utc_user_attested: str,
) -> SportyBetUserAttestedEventIdentity:
    """Bind explicit visible SportyBet event-header observations to PR #154 evidence."""

    if not isinstance(inventory, native.SportyBetUserControlledNativeInventory):
        raise SportyBetFotMobReconciliationError(
            "inventory must be a verified SportyBet user-controlled native inventory"
        )
    if inventory.source_request_kind is not SportyBetLiteRequestKind.EVENT_DETAIL:
        raise SportyBetFotMobReconciliationError(
            "only event-detail inventories can receive an event identity attestation"
        )
    if inventory.source_event_id is None or inventory.source_sport_id is None:
        raise SportyBetFotMobReconciliationError("source event/sport identity is incomplete")
    if len(inventory.events) != 1:
        raise SportyBetFotMobReconciliationError(
            "event-detail inventory must contain exactly one provider event"
        )
    event = inventory.events[0]
    if event.event_id != inventory.source_event_id:
        raise SportyBetFotMobReconciliationError(
            "inventory event does not match source event identity"
        )
    if event.sport_id is not None and event.sport_id != inventory.source_sport_id:
        raise SportyBetFotMobReconciliationError(
            "inventory event sport does not match source sport identity"
        )
    return SportyBetUserAttestedEventIdentity(
        schema_version=SCHEMA_VERSION,
        dataset_name=IDENTITY_DATASET_NAME,
        provider=PROVIDER,
        source_evidence_id=inventory.source_evidence_id,
        source_inventory_sha256=native.inventory_sha256(inventory),
        source_raw_sha256=inventory.source_raw_sha256,
        source_url=inventory.source_url,
        event_id=inventory.source_event_id,
        sport_id=inventory.source_sport_id,
        competition_displayed=competition_displayed,
        home_participant_displayed=home_participant_displayed,
        away_participant_displayed=away_participant_displayed,
        kickoff_displayed=kickoff_displayed,
        kickoff_utc_user_attested=kickoff_utc_user_attested,
        observed_at_user_attested=inventory.observed_at_user_attested,
        identity_authority=IDENTITY_AUTHORITY,
        safety=_default_safety(),
    )


def canonical_event_identity_bytes(identity: Any) -> bytes:
    if not isinstance(identity, SportyBetUserAttestedEventIdentity):
        raise SportyBetFotMobReconciliationError(
            "identity must be SportyBetUserAttestedEventIdentity"
        )
    return _canonical_bytes(identity.to_dict())


def event_identity_sha256(identity: Any) -> str:
    return hashlib.sha256(canonical_event_identity_bytes(identity)).hexdigest()


def _fotmob_rows(
    fixtures: Iterable[FotMobReviewedFixtureCatalogInput],
) -> tuple[FotMobReviewedFixtureCatalogInput, ...]:
    try:
        rows = tuple(fixtures)
    except TypeError as exc:
        raise SportyBetFotMobReconciliationError("fixtures must be iterable") from exc
    if not rows:
        raise SportyBetFotMobReconciliationError(
            "at least one reviewed FotMob fixture is required"
        )
    if any(type(item) is not FotMobReviewedFixtureCatalogInput for item in rows):
        raise SportyBetFotMobReconciliationError(
            "fixture population contains a non-reviewed FotMob catalog input"
        )
    ids = [item.source_fixture_identifier for item in rows]
    if len(ids) != len(set(ids)):
        raise SportyBetFotMobReconciliationError(
            "duplicate FotMob source_fixture_identifier in reconciliation population"
        )
    return tuple(sorted(rows, key=lambda item: int(item.source_fixture_identifier)))


def canonical_fotmob_population_bytes(
    fixtures: Iterable[FotMobReviewedFixtureCatalogInput],
) -> bytes:
    rows = _fotmob_rows(fixtures)
    return b"".join(_canonical_bytes(item.to_dict()) for item in rows)


def fotmob_population_sha256(
    fixtures: Iterable[FotMobReviewedFixtureCatalogInput],
) -> str:
    return hashlib.sha256(canonical_fotmob_population_bytes(fixtures)).hexdigest()


@dataclasses.dataclass(frozen=True)
class MatchedFotMobFixture:
    source_fixture_identifier: str
    source_capture_manifest_sha256: str
    candidate_sha256: str
    evidence_sha256: str
    home_team: str
    away_team: str
    competition: str
    kickoff: str

    def __post_init__(self) -> None:
        _exact_text(self.source_fixture_identifier, "source_fixture_identifier", maximum=64)
        _hash(self.source_capture_manifest_sha256, "source_capture_manifest_sha256")
        _hash(self.candidate_sha256, "candidate_sha256")
        _hash(self.evidence_sha256, "evidence_sha256")
        _exact_text(self.home_team, "home_team")
        _exact_text(self.away_team, "away_team")
        _exact_text(self.competition, "competition")
        _canonical_utc(self.kickoff, "kickoff")

    @classmethod
    def from_reviewed(cls, value: FotMobReviewedFixtureCatalogInput) -> "MatchedFotMobFixture":
        return cls(
            source_fixture_identifier=value.source_fixture_identifier,
            source_capture_manifest_sha256=value.source_capture_manifest_sha256,
            candidate_sha256=value.candidate_sha256,
            evidence_sha256=value.evidence_sha256,
            home_team=value.home_team,
            away_team=value.away_team,
            competition=value.competition,
            kickoff=serialize_utc(value.kickoff),
        )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class ReconciliationDisposition(str, enum.Enum):
    EXACT_MATCH_CANDIDATE_USER_ATTESTED = "EXACT_MATCH_CANDIDATE_USER_ATTESTED"
    NO_EXACT_MATCH = "NO_EXACT_MATCH"
    AMBIGUOUS_EXACT_MATCH = "AMBIGUOUS_EXACT_MATCH"


@dataclasses.dataclass(frozen=True)
class SportyBetFotMobReconciliationCandidate:
    schema_version: int
    dataset_name: str
    sportybet_event_identity_sha256: str
    fotmob_population_sha256: str
    sportybet_event_id: str
    sportybet_identity_authority: str
    matching_basis: str
    disposition: ReconciliationDisposition
    exact_match_count: int
    matched_fixture: MatchedFotMobFixture | None
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise SportyBetFotMobReconciliationError("schema_version mismatch")
        if self.dataset_name != RECONCILIATION_DATASET_NAME:
            raise SportyBetFotMobReconciliationError("reconciliation dataset mismatch")
        _hash(self.sportybet_event_identity_sha256, "sportybet_event_identity_sha256")
        _hash(self.fotmob_population_sha256, "fotmob_population_sha256")
        _exact_text(self.sportybet_event_id, "sportybet_event_id", maximum=160)
        if self.sportybet_identity_authority != IDENTITY_AUTHORITY:
            raise SportyBetFotMobReconciliationError("SportyBet identity authority mismatch")
        if self.matching_basis != MATCHING_BASIS:
            raise SportyBetFotMobReconciliationError("matching_basis mismatch")
        if type(self.disposition) is not ReconciliationDisposition:
            raise SportyBetFotMobReconciliationError("disposition is invalid")
        if type(self.exact_match_count) is not int or self.exact_match_count < 0:
            raise SportyBetFotMobReconciliationError("exact_match_count is invalid")
        if self.disposition is ReconciliationDisposition.EXACT_MATCH_CANDIDATE_USER_ATTESTED:
            if self.exact_match_count != 1 or not isinstance(
                self.matched_fixture, MatchedFotMobFixture
            ):
                raise SportyBetFotMobReconciliationError(
                    "exact-match candidate requires exactly one matched fixture"
                )
        elif self.disposition is ReconciliationDisposition.NO_EXACT_MATCH:
            if self.exact_match_count != 0 or self.matched_fixture is not None:
                raise SportyBetFotMobReconciliationError(
                    "no-match disposition cannot contain a matched fixture"
                )
        else:
            if self.exact_match_count < 2 or self.matched_fixture is not None:
                raise SportyBetFotMobReconciliationError(
                    "ambiguous disposition requires multiple matches and no chosen fixture"
                )
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "sportybet_event_identity_sha256": self.sportybet_event_identity_sha256,
            "fotmob_population_sha256": self.fotmob_population_sha256,
            "sportybet_event_id": self.sportybet_event_id,
            "sportybet_identity_authority": self.sportybet_identity_authority,
            "matching_basis": self.matching_basis,
            "disposition": self.disposition.value,
            "exact_match_count": self.exact_match_count,
            "matched_fixture": None if self.matched_fixture is None else self.matched_fixture.to_dict(),
            "safety": dict(self.safety),
        }


def build_exact_reconciliation_candidate(
    identity: Any,
    fixtures: Iterable[FotMobReviewedFixtureCatalogInput],
) -> SportyBetFotMobReconciliationCandidate:
    """Compare exact event identity only; never fuzzy-match or reverse participants."""

    if not isinstance(identity, SportyBetUserAttestedEventIdentity):
        raise SportyBetFotMobReconciliationError(
            "identity must be SportyBetUserAttestedEventIdentity"
        )
    rows = _fotmob_rows(fixtures)
    kickoff = identity.kickoff_utc_user_attested
    matches = tuple(
        item
        for item in rows
        if item.home_team == identity.home_participant_displayed
        and item.away_team == identity.away_participant_displayed
        and item.competition == identity.competition_displayed
        and serialize_utc(item.kickoff) == kickoff
    )
    if len(matches) == 1:
        disposition = ReconciliationDisposition.EXACT_MATCH_CANDIDATE_USER_ATTESTED
        matched = MatchedFotMobFixture.from_reviewed(matches[0])
    elif not matches:
        disposition = ReconciliationDisposition.NO_EXACT_MATCH
        matched = None
    else:
        disposition = ReconciliationDisposition.AMBIGUOUS_EXACT_MATCH
        matched = None
    return SportyBetFotMobReconciliationCandidate(
        schema_version=SCHEMA_VERSION,
        dataset_name=RECONCILIATION_DATASET_NAME,
        sportybet_event_identity_sha256=event_identity_sha256(identity),
        fotmob_population_sha256=fotmob_population_sha256(rows),
        sportybet_event_id=identity.event_id,
        sportybet_identity_authority=identity.identity_authority,
        matching_basis=MATCHING_BASIS,
        disposition=disposition,
        exact_match_count=len(matches),
        matched_fixture=matched,
        safety=_default_safety(),
    )


def canonical_reconciliation_candidate_bytes(candidate: Any) -> bytes:
    if not isinstance(candidate, SportyBetFotMobReconciliationCandidate):
        raise SportyBetFotMobReconciliationError(
            "candidate must be SportyBetFotMobReconciliationCandidate"
        )
    return _canonical_bytes(candidate.to_dict())


def reconciliation_candidate_sha256(candidate: Any) -> str:
    return hashlib.sha256(canonical_reconciliation_candidate_bytes(candidate)).hexdigest()


__all__ = [
    "IDENTITY_AUTHORITY",
    "IDENTITY_DATASET_NAME",
    "MATCHING_BASIS",
    "RECONCILIATION_DATASET_NAME",
    "MatchedFotMobFixture",
    "ReconciliationDisposition",
    "SportyBetFotMobReconciliationCandidate",
    "SportyBetFotMobReconciliationError",
    "SportyBetUserAttestedEventIdentity",
    "build_exact_reconciliation_candidate",
    "build_user_attested_event_identity",
    "canonical_event_identity_bytes",
    "canonical_fotmob_population_bytes",
    "canonical_reconciliation_candidate_bytes",
    "event_identity_sha256",
    "fotmob_population_sha256",
    "reconciliation_candidate_sha256",
]
