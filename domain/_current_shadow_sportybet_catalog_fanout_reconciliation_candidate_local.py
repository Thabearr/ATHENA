"""PR-F provider-catalog fanout using main's proven candidate-local SportyBet handling.

The low-level catalogue/fanout acquisition contract remains the reviewed PR-F
boundary.  This wrapper changes only the direct-event confirmation failure
scope: after a unique exact FotMob/provider identity candidate has been found,
a malformed direct event-detail market inventory cannot poison unrelated
candidates.  The candidate is retained as an explicit non-authorized failure
row and the remaining exact candidates continue, matching the already-proven
PR258 candidate-local transport behavior on main.

No failed candidate receives fixture reconciliation, canonical-market, price,
selection, execution, staking, BET, or wager authority.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime
import enum
import hashlib
import json
from pathlib import Path
import types
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from domain import _current_shadow_sportybet_catalog_fanout_reconciliation_base as base
from domain import sportybet_current_event_discovery_reconciliation as reviewed
from domain import sportybet_live_event_quote_evidence as live
from domain.fotmob_data_matches_capture import FotMobDataMatchesCaptureManifest
from domain.sportybet_lite_source_capture import serialize_utc

SCHEMA_VERSION = base.SCHEMA_VERSION
DATASET_NAME = base.DATASET_NAME
DISCOVERY_DATASET_NAME = base.DISCOVERY_DATASET_NAME
STATUS = base.STATUS
PROVIDER = base.PROVIDER
PROVIDER_REGION = base.PROVIDER_REGION
ORIGIN = base.ORIGIN
OPER_ID = base.OPER_ID
FOOTBALL_SPORT_ID = base.FOOTBALL_SPORT_ID
CATALOG_PATH = base.CATALOG_PATH
UPCOMING_PATH = base.UPCOMING_PATH
CATALOG_SOURCE_METHOD = base.CATALOG_SOURCE_METHOD
FANOUT_SOURCE_METHOD = base.FANOUT_SOURCE_METHOD
MAX_RESPONSE_BYTES = base.MAX_RESPONSE_BYTES
MAX_MANIFEST_BYTES = base.MAX_MANIFEST_BYTES
MAX_SOURCE_AGE_SECONDS = base.MAX_SOURCE_AGE_SECONDS
MINIMUM_LEAD_SECONDS = base.MINIMUM_LEAD_SECONDS
REQUEST_NONCE_MAX_SKEW_MS = base.REQUEST_NONCE_MAX_SKEW_MS
REQUEST_HEADERS = base.REQUEST_HEADERS
ALLOWED_OUTPUT_RELATIVE = base.ALLOWED_OUTPUT_RELATIVE
CATALOG_RAW_FILENAME = base.CATALOG_RAW_FILENAME
MANIFEST_FILENAME = base.MANIFEST_FILENAME
TOURNAMENT_DIRNAME = base.TOURNAMENT_DIRNAME
MATCHING_BASIS = base.MATCHING_BASIS
DETAIL_CONFIRMATION_POLICY = base.DETAIL_CONFIRMATION_POLICY
CATALOG_IDENTITY_POLICY = base.CATALOG_IDENTITY_POLICY
FANOUT_POLICY = base.FANOUT_POLICY
OBSERVATION_AUTHORITY = base.OBSERVATION_AUTHORITY
NEXT_BOUNDARY = base.NEXT_BOUNDARY
AUTHORITY = base.AUTHORITY

CANDIDATE_LOCAL_DIRECT_DETAIL_POLICY = (
    "PR258_CANDIDATE_LOCAL_DIRECT_DETAIL_PARSE_FAILURE_"
    "NO_RECONCILIATION_AUTHORITY_V1"
)
EXPECTED_CONTRACT_SHA256 = "cb0811d844150e873011c2f57b5d57f7eff663ab72d2912d1afd94217a0d4f2b"

CurrentEventReconciliationDisposition = reviewed.CurrentEventReconciliationDisposition
CurrentEventReconciliationRow = reviewed.CurrentEventReconciliationRow
ProviderCatalogTournament = base.ProviderCatalogTournament
ProviderTournamentObservation = base.ProviderTournamentObservation
CurrentShadowSportyBetCatalogFanoutSnapshot = base.CurrentShadowSportyBetCatalogFanoutSnapshot
CurrentShadowSportyBetCatalogFanoutReconciliationError = (
    base.CurrentShadowSportyBetCatalogFanoutReconciliationError
)
SportyBetCurrentEventDiscoveryError = CurrentShadowSportyBetCatalogFanoutReconciliationError

# Keep the reviewed low-level helpers available to existing tests and callers.
time = base.time
_canonical = base._canonical
_now_utc = base._now_utc
_utc = base._utc
_text = base._text
_sha = base._sha
_network_get = base._network_get
_parse_catalog = base._parse_catalog
_parse_tournament_response = base._parse_tournament_response
_evidence_root = base._evidence_root
_write_exclusive = base._write_exclusive
_raw_filename = base._raw_filename
_snapshot_from_parts = base._snapshot_from_parts
_event_from_mapping = base._event_from_mapping
_snapshot_from_manifest = base._snapshot_from_manifest
_set_frozen = base._set_frozen
catalog_request_target = base.catalog_request_target
tournament_request_target = base.tournament_request_target


def calculate_contract_sha256() -> str:
    payload = {
        "base_contract_sha256": base.EXPECTED_CONTRACT_SHA256,
        "candidate_local_direct_detail_policy": CANDIDATE_LOCAL_DIRECT_DETAIL_POLICY,
    }
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_contract() -> Mapping[str, str]:
    base.validate_contract()
    actual = calculate_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "catalog fanout candidate-local contract drifted"
        )
    return types.MappingProxyType(
        {
            "contract_sha256": actual,
            "base_contract_sha256": base.EXPECTED_CONTRACT_SHA256,
        }
    )


def capture_current_catalog_fanout_discovery(
    *, repository_root: Path, execute_live_network: bool
) -> tuple[Path, CurrentShadowSportyBetCatalogFanoutSnapshot]:
    """Capture the exact reviewed fanout while honoring wrapper monkeypatches."""
    validate_contract()
    if execute_live_network is not True:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "live catalog fanout requires execute_live_network=True"
        )
    repository = Path(repository_root).resolve(strict=True)
    catalog_raw, catalog_observed = _network_get(catalog_request_target())
    tournaments = _parse_catalog(catalog_raw)
    if not tournaments:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "provider football catalog has no active tournaments"
        )
    observations: list[ProviderTournamentObservation] = []
    events: list[reviewed.SportyBetDiscoveredEvent] = []
    raw_by_pair: dict[tuple[str, str], bytes] = {}
    for tournament in tournaments:
        nonce = int(time.time() * 1000)
        target = tournament_request_target(
            category_id=tournament.category_id,
            tournament_id=tournament.tournament_id,
            request_nonce_ms=nonce,
        )
        raw, observed = _network_get(target)
        observation, parsed = _parse_tournament_response(
            raw,
            category_id=tournament.category_id,
            tournament_id=tournament.tournament_id,
            request_nonce_ms=nonce,
            observed_at=observed,
        )
        observations.append(observation)
        events.extend(parsed)
        raw_by_pair[(tournament.category_id, tournament.tournament_id)] = raw
    ordered_observations = tuple(
        sorted(observations, key=lambda item: (item.category_id, item.tournament_id))
    )
    snapshot = _snapshot_from_parts(
        catalog_raw=catalog_raw,
        catalog_observed_at=catalog_observed,
        tournaments=tournaments,
        observations=ordered_observations,
        events=events,
    )
    root = _evidence_root(repository, create=True)
    directory = root / snapshot.canonical_sha256[:24]
    manifest_bytes = _canonical(snapshot.to_dict(), newline=True)
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "catalog fanout manifest exceeds byte bound"
        )
    if directory.exists():
        existing = verify_current_catalog_fanout_discovery(
            directory, repository_root=repository
        )
        if existing.to_dict() != snapshot.to_dict():
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
                "catalog fanout capture identity collision"
            )
        return directory, existing
    directory.mkdir(exist_ok=False)
    tournament_dir = directory / TOURNAMENT_DIRNAME
    tournament_dir.mkdir(exist_ok=False)
    base._sync_directory(root)
    base._sync_directory(directory)
    base._sync_directory(tournament_dir)
    _write_exclusive(directory / CATALOG_RAW_FILENAME, catalog_raw)
    for observation in ordered_observations:
        raw = raw_by_pair[(observation.category_id, observation.tournament_id)]
        _write_exclusive(tournament_dir / _raw_filename(observation), raw)
    _write_exclusive(directory / MANIFEST_FILENAME, manifest_bytes)
    verified = verify_current_catalog_fanout_discovery(
        directory, repository_root=repository
    )
    base._sync_directory(tournament_dir)
    base._sync_directory(directory)
    base._sync_directory(root)
    return directory, verified


def verify_current_catalog_fanout_discovery(
    evidence_directory: Path, *, repository_root: Path
) -> CurrentShadowSportyBetCatalogFanoutSnapshot:
    validate_contract()
    return base.verify_current_catalog_fanout_discovery(
        evidence_directory, repository_root=repository_root
    )


class CurrentShadowDirectConfirmationDisposition(str, enum.Enum):
    DIRECT_EVENT_DETAIL_SOURCE_INVALID = "DIRECT_EVENT_DETAIL_SOURCE_INVALID"


@dataclasses.dataclass(frozen=True)
class CurrentShadowDirectConfirmationFailureRow:
    event_id: str
    home_team_name: str
    away_team_name: str
    competition_name: str | None
    kickoff_utc: datetime
    discovery_observed_at: datetime
    discovery_age_seconds: float
    kickoff_lead_seconds: float
    disposition: CurrentShadowDirectConfirmationDisposition
    exact_fotmob_match_count: int
    matched_fotmob_fixture_id: str
    direct_event_observed_at: datetime
    direct_event_age_seconds: float
    direct_event_manifest_sha256: str
    direct_event_inventory_sha256: None
    direct_event_raw_sha256: str
    fixture_reconciliation_authorized: bool
    direct_event_failure_reason: str

    def __post_init__(self) -> None:
        reviewed._event_id(self.event_id)
        reviewed._text(self.home_team_name, "failure row home_team_name")
        reviewed._text(self.away_team_name, "failure row away_team_name")
        if self.competition_name is not None:
            reviewed._text(self.competition_name, "failure row competition_name")
        object.__setattr__(self, "kickoff_utc", reviewed._utc(self.kickoff_utc, "failure row kickoff_utc"))
        object.__setattr__(
            self,
            "discovery_observed_at",
            reviewed._utc(self.discovery_observed_at, "failure row discovery_observed_at"),
        )
        object.__setattr__(
            self,
            "direct_event_observed_at",
            reviewed._utc(self.direct_event_observed_at, "failure row direct_event_observed_at"),
        )
        if self.disposition is not CurrentShadowDirectConfirmationDisposition.DIRECT_EVENT_DETAIL_SOURCE_INVALID:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
                "direct confirmation failure disposition invalid"
            )
        if self.exact_fotmob_match_count != 1:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
                "direct confirmation failure must retain one exact FotMob candidate"
            )
        reviewed._text(
            self.matched_fotmob_fixture_id,
            "failure row matched_fotmob_fixture_id",
            maximum=64,
        )
        for value, label in (
            (self.direct_event_manifest_sha256, "direct_event_manifest_sha256"),
            (self.direct_event_raw_sha256, "direct_event_raw_sha256"),
        ):
            reviewed._sha(value, label)
        if self.direct_event_inventory_sha256 is not None:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
                "failed direct confirmation cannot have inventory identity"
            )
        if self.fixture_reconciliation_authorized is not False:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
                "failed direct confirmation cannot authorize reconciliation"
            )
        if type(self.direct_event_failure_reason) is not str or not self.direct_event_failure_reason.strip():
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
                "direct confirmation failure reason missing"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "home_team_name": self.home_team_name,
            "away_team_name": self.away_team_name,
            "competition_name": self.competition_name,
            "kickoff_utc": serialize_utc(self.kickoff_utc),
            "discovery_observed_at": serialize_utc(self.discovery_observed_at),
            "discovery_age_seconds": self.discovery_age_seconds,
            "kickoff_lead_seconds": self.kickoff_lead_seconds,
            "disposition": self.disposition.value,
            "exact_fotmob_match_count": self.exact_fotmob_match_count,
            "matched_fotmob_fixture_id": self.matched_fotmob_fixture_id,
            "direct_event_observed_at": serialize_utc(self.direct_event_observed_at),
            "direct_event_age_seconds": self.direct_event_age_seconds,
            "direct_event_manifest_sha256": self.direct_event_manifest_sha256,
            "direct_event_inventory_sha256": None,
            "direct_event_raw_sha256": self.direct_event_raw_sha256,
            "fixture_reconciliation_authorized": False,
            "direct_event_failure_reason": self.direct_event_failure_reason,
        }


@dataclasses.dataclass(frozen=True, init=False)
class CurrentShadowSportyBetCatalogFanoutReconciliationBundle:
    schema_version: int
    dataset_name: str
    status: str
    evaluation_time: datetime
    max_source_age_seconds: int
    minimum_lead_seconds: int
    fanout_snapshot_sha256: str
    source_fotmob_admission_sha256: str
    source_fotmob_candidate_bundle_sha256: str
    source_fotmob_review_bundle_sha256: str
    source_fotmob_handoff_sha256: str
    source_fotmob_catalog_sha256: str
    source_fotmob_manifest_sha256: str
    fotmob_capture_identities: tuple[Mapping[str, Any], ...]
    rows: tuple[Any, ...]
    authority: Mapping[str, bool]
    next_boundary: str
    contract_sha256: str
    _repository_root: Path
    _fanout_directory: Path
    _detail_directories: tuple[tuple[str, Path], ...]
    _fotmob_admission: Any
    _fotmob_captures: tuple[tuple[bytes, FotMobDataMatchesCaptureManifest], ...]

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "catalog fanout bundles are builder-only"
        )

    @property
    def matched_rows(self) -> tuple[reviewed.CurrentEventReconciliationRow, ...]:
        return tuple(
            row for row in self.rows if row.fixture_reconciliation_authorized
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "status": self.status,
            "evaluation_time": serialize_utc(self.evaluation_time),
            "max_source_age_seconds": self.max_source_age_seconds,
            "minimum_lead_seconds": self.minimum_lead_seconds,
            "fanout_snapshot_sha256": self.fanout_snapshot_sha256,
            "source_fotmob_admission_sha256": self.source_fotmob_admission_sha256,
            "source_fotmob_candidate_bundle_sha256": self.source_fotmob_candidate_bundle_sha256,
            "source_fotmob_review_bundle_sha256": self.source_fotmob_review_bundle_sha256,
            "source_fotmob_handoff_sha256": self.source_fotmob_handoff_sha256,
            "source_fotmob_catalog_sha256": self.source_fotmob_catalog_sha256,
            "source_fotmob_manifest_sha256": self.source_fotmob_manifest_sha256,
            "fotmob_capture_identities": [dict(row) for row in self.fotmob_capture_identities],
            "event_count": len(self.rows),
            "matched_count": len(self.matched_rows),
            "rows": [row.to_dict() for row in self.rows],
            "authority": dict(self.authority),
            "next_boundary": self.next_boundary,
            "contract_sha256": self.contract_sha256,
            "candidate_local_direct_detail_policy": CANDIDATE_LOCAL_DIRECT_DETAIL_POLICY,
            "provider_event_timestamp": None,
            "provider_snapshot_id": None,
            "wager_placed": False,
        }

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical(self.to_dict())).hexdigest()


SportyBetCurrentEventDiscoveryReconciliationBundle = (
    CurrentShadowSportyBetCatalogFanoutReconciliationBundle
)


def _standard_row(
    *,
    event: reviewed.SportyBetDiscoveredEvent,
    matches: tuple[Any, ...],
    discovery_age: float,
    kickoff_lead: float,
    disposition: reviewed.CurrentEventReconciliationDisposition,
    matched_id: str | None = None,
    direct_observed: datetime | None = None,
    direct_age: float | None = None,
    direct_manifest_sha: str | None = None,
    direct_inventory_sha: str | None = None,
    direct_raw_sha: str | None = None,
) -> reviewed.CurrentEventReconciliationRow:
    return reviewed.CurrentEventReconciliationRow(
        event_id=event.event_id,
        home_team_name=event.home_team_name,
        away_team_name=event.away_team_name,
        competition_name=event.competition_name,
        kickoff_utc=event.kickoff_utc,
        discovery_observed_at=event.source_observed_at,
        discovery_age_seconds=discovery_age,
        kickoff_lead_seconds=kickoff_lead,
        disposition=disposition,
        exact_fotmob_match_count=len(matches),
        matched_fotmob_fixture_id=matched_id,
        direct_event_observed_at=direct_observed,
        direct_event_age_seconds=direct_age,
        direct_event_manifest_sha256=direct_manifest_sha,
        direct_event_inventory_sha256=direct_inventory_sha,
        direct_event_raw_sha256=direct_raw_sha,
        fixture_reconciliation_authorized=(
            disposition
            is reviewed.CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED
        ),
    )


def _build_bundle(
    *,
    repository_root: Path,
    fanout_directory: Path,
    fanout: CurrentShadowSportyBetCatalogFanoutSnapshot,
    admission: Any,
    captures: tuple[tuple[bytes, FotMobDataMatchesCaptureManifest], ...],
    detail_directories: Mapping[str, Path],
    evaluation_time: datetime,
) -> CurrentShadowSportyBetCatalogFanoutReconciliationBundle:
    evaluation = _utc(evaluation_time, "evaluation_time")
    reviewed_rows = reviewed._reviewed_rows(admission)
    provisional: dict[str, tuple[str, tuple[Any, ...]]] = {}
    for event in fanout.events:
        if not event.prematch_bookable_observed:
            provisional[event.event_id] = ("NONBOOKABLE", ())
        elif event.competition_name is None:
            provisional[event.event_id] = ("NO_COMPETITION", ())
        else:
            matches = reviewed._match_event(event, reviewed_rows)
            if not matches:
                provisional[event.event_id] = ("NO_MATCH", ())
            elif len(matches) > 1:
                provisional[event.event_id] = ("AMBIGUOUS_FOTMOB", matches)
            else:
                provisional[event.event_id] = ("UNIQUE", matches)
    target_counts = Counter(
        matches[0].source_fixture_identifier
        for state, matches in provisional.values()
        if state == "UNIQUE"
    )
    expected_detail_ids = {
        event_id
        for event_id, (state, matches) in provisional.items()
        if state == "UNIQUE"
        and target_counts[matches[0].source_fixture_identifier] == 1
    }
    if set(detail_directories) != expected_detail_ids:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "direct event-detail evidence set mismatch"
        )

    rows: list[Any] = []
    for event in fanout.events:
        state, matches = provisional[event.event_id]
        discovery_age = (evaluation - event.source_observed_at).total_seconds()
        kickoff_lead = (event.kickoff_utc - evaluation).total_seconds()
        if discovery_age < 0:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
                "evaluation_time predates fanout response completion"
            )
        if discovery_age > MAX_SOURCE_AGE_SECONDS:
            rows.append(_standard_row(
                event=event, matches=matches, discovery_age=discovery_age,
                kickoff_lead=kickoff_lead,
                disposition=reviewed.CurrentEventReconciliationDisposition.DISCOVERY_EVIDENCE_STALE,
            ))
            continue
        if kickoff_lead <= MINIMUM_LEAD_SECONDS:
            rows.append(_standard_row(
                event=event, matches=matches, discovery_age=discovery_age,
                kickoff_lead=kickoff_lead,
                disposition=reviewed.CurrentEventReconciliationDisposition.PROVIDER_EVENT_TOO_CLOSE_TO_KICKOFF,
            ))
            continue
        if state == "NONBOOKABLE":
            rows.append(_standard_row(
                event=event, matches=matches, discovery_age=discovery_age,
                kickoff_lead=kickoff_lead,
                disposition=reviewed.CurrentEventReconciliationDisposition.DISCOVERY_EVENT_NOT_PREMATCH_BOOKABLE,
            ))
            continue
        if state == "NO_COMPETITION":
            rows.append(_standard_row(
                event=event, matches=matches, discovery_age=discovery_age,
                kickoff_lead=kickoff_lead,
                disposition=reviewed.CurrentEventReconciliationDisposition.PROVIDER_COMPETITION_UNPROVEN,
            ))
            continue
        if state == "NO_MATCH":
            rows.append(_standard_row(
                event=event, matches=matches, discovery_age=discovery_age,
                kickoff_lead=kickoff_lead,
                disposition=reviewed.CurrentEventReconciliationDisposition.NO_EXACT_REVIEWED_FOTMOB_MATCH,
            ))
            continue
        if state == "AMBIGUOUS_FOTMOB":
            rows.append(_standard_row(
                event=event, matches=matches, discovery_age=discovery_age,
                kickoff_lead=kickoff_lead,
                disposition=reviewed.CurrentEventReconciliationDisposition.AMBIGUOUS_EXACT_REVIEWED_FOTMOB_MATCH,
            ))
            continue
        matched = matches[0]
        if target_counts[matched.source_fixture_identifier] > 1:
            rows.append(_standard_row(
                event=event, matches=matches, discovery_age=discovery_age,
                kickoff_lead=kickoff_lead,
                disposition=reviewed.CurrentEventReconciliationDisposition.AMBIGUOUS_PROVIDER_EVENT_FOR_FIXTURE,
            ))
            continue

        directory = detail_directories[event.event_id]
        try:
            inventory = reviewed._detail_inventory_from_directory(
                directory, repository_root=repository_root
            )
        except reviewed.SportyBetCurrentEventDiscoveryError as exc:
            manifest = live.verify_live_event_quote_evidence(
                directory, repository_root=repository_root
            )
            direct_age = (evaluation - manifest.observed_at).total_seconds()
            if direct_age < 0:
                raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
                    "evaluation_time predates direct event-detail response"
                )
            rows.append(CurrentShadowDirectConfirmationFailureRow(
                event_id=event.event_id,
                home_team_name=event.home_team_name,
                away_team_name=event.away_team_name,
                competition_name=event.competition_name,
                kickoff_utc=event.kickoff_utc,
                discovery_observed_at=event.source_observed_at,
                discovery_age_seconds=discovery_age,
                kickoff_lead_seconds=kickoff_lead,
                disposition=CurrentShadowDirectConfirmationDisposition.DIRECT_EVENT_DETAIL_SOURCE_INVALID,
                exact_fotmob_match_count=1,
                matched_fotmob_fixture_id=matched.source_fixture_identifier,
                direct_event_observed_at=manifest.observed_at,
                direct_event_age_seconds=direct_age,
                direct_event_manifest_sha256=live.manifest_sha256(manifest),
                direct_event_inventory_sha256=None,
                direct_event_raw_sha256=manifest.raw_sha256,
                fixture_reconciliation_authorized=False,
                direct_event_failure_reason=str(exc),
            ))
            continue

        direct_age = (evaluation - inventory.observed_at).total_seconds()
        if direct_age < 0:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
                "evaluation_time predates direct event-detail response"
            )
        if (
            inventory.event_id != event.event_id
            or inventory.home_team_name != event.home_team_name
            or inventory.away_team_name != event.away_team_name
            or inventory.kickoff_utc != event.kickoff_utc
        ):
            disposition = reviewed.CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_IDENTITY_MISMATCH
        elif not inventory.prematch_bookable_observed:
            disposition = reviewed.CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_NOT_PREMATCH_BOOKABLE
        elif direct_age > MAX_SOURCE_AGE_SECONDS:
            disposition = reviewed.CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_STALE
        else:
            disposition = reviewed.CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED
        rows.append(_standard_row(
            event=event,
            matches=matches,
            discovery_age=discovery_age,
            kickoff_lead=kickoff_lead,
            disposition=disposition,
            matched_id=matched.source_fixture_identifier,
            direct_observed=inventory.observed_at,
            direct_age=direct_age,
            direct_manifest_sha=inventory.source_manifest_sha256,
            direct_inventory_sha=inventory.canonical_sha256,
            direct_raw_sha=inventory.source_raw_sha256,
        ))

    ordered = tuple(sorted(rows, key=lambda row: row.event_id))
    admission_payload = admission.to_dict()
    valid_rows = tuple(
        row for row in ordered if type(row) is reviewed.CurrentEventReconciliationRow
    )
    value = object.__new__(CurrentShadowSportyBetCatalogFanoutReconciliationBundle)
    return _set_frozen(value, {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "status": STATUS,
        "evaluation_time": evaluation,
        "max_source_age_seconds": MAX_SOURCE_AGE_SECONDS,
        "minimum_lead_seconds": MINIMUM_LEAD_SECONDS,
        "fanout_snapshot_sha256": fanout.canonical_sha256,
        "source_fotmob_admission_sha256": reviewed.fotmob_admission.sha256_reviewed_fixture_catalog_admission(admission),
        "source_fotmob_candidate_bundle_sha256": admission_payload["candidate_bundle_sha256"],
        "source_fotmob_review_bundle_sha256": admission_payload["review_bundle_sha256"],
        "source_fotmob_handoff_sha256": admission_payload["handoff_sha256"],
        "source_fotmob_catalog_sha256": admission_payload["catalog_sha256"],
        "source_fotmob_manifest_sha256": admission_payload["manifest_sha256"],
        "fotmob_capture_identities": reviewed._capture_identity_rows(captures),
        "rows": ordered,
        "authority": reviewed._output_authority(valid_rows),
        "next_boundary": NEXT_BOUNDARY,
        "contract_sha256": EXPECTED_CONTRACT_SHA256,
        "_repository_root": Path(repository_root),
        "_fanout_directory": Path(fanout_directory),
        "_detail_directories": tuple(
            sorted(
                ((event_id, Path(path)) for event_id, path in detail_directories.items()),
                key=lambda item: item[0],
            )
        ),
        "_fotmob_admission": admission,
        "_fotmob_captures": captures,
    })


def reconcile_current_events_from_catalog_fanout(
    *,
    repository_root: Path,
    fanout_evidence_directory: Path,
    fotmob_admission_value: Any,
    fotmob_captures: Sequence[tuple[bytes, FotMobDataMatchesCaptureManifest]],
    execute_live_network: bool,
) -> CurrentShadowSportyBetCatalogFanoutReconciliationBundle:
    validate_contract()
    if execute_live_network is not True:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "direct confirmation requires execute_live_network=True"
        )
    repository = Path(repository_root).resolve(strict=True)
    try:
        captures = reviewed._materialize_fotmob_captures(fotmob_captures)
        admission = reviewed._rederive_exact_fotmob_admission(
            fotmob_admission_value, captures
        )
    except reviewed.SportyBetCurrentEventDiscoveryError as exc:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(str(exc)) from exc
    fanout = verify_current_catalog_fanout_discovery(
        fanout_evidence_directory, repository_root=repository
    )
    reviewed_rows = reviewed._reviewed_rows(admission)
    provisional: dict[str, tuple[str, tuple[Any, ...]]] = {}
    for event in fanout.events:
        if not event.prematch_bookable_observed:
            provisional[event.event_id] = ("NONBOOKABLE", ())
        elif event.competition_name is None:
            provisional[event.event_id] = ("NO_COMPETITION", ())
        else:
            matches = reviewed._match_event(event, reviewed_rows)
            if not matches:
                provisional[event.event_id] = ("NO_MATCH", ())
            elif len(matches) > 1:
                provisional[event.event_id] = ("AMBIGUOUS_FOTMOB", matches)
            else:
                provisional[event.event_id] = ("UNIQUE", matches)
    counts = Counter(
        matches[0].source_fixture_identifier
        for state, matches in provisional.values()
        if state == "UNIQUE"
    )
    detail_dirs: dict[str, Path] = {}
    for event_id, (state, matches) in sorted(provisional.items()):
        if state != "UNIQUE" or counts[matches[0].source_fixture_identifier] != 1:
            continue
        try:
            directory, _manifest = live.capture_live_event_quote_evidence(
                event_id=event_id,
                repository_root=repository,
                execute_live_network=True,
            )
        except live.SportyBetLiveEventQuoteEvidenceError as exc:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
                f"direct event-detail capture failed closed for {event_id}: {exc}"
            ) from exc
        detail_dirs[event_id] = directory
    return _build_bundle(
        repository_root=repository,
        fanout_directory=Path(fanout_evidence_directory),
        fanout=fanout,
        admission=admission,
        captures=captures,
        detail_directories=detail_dirs,
        evaluation_time=_now_utc(),
    )


def discover_and_reconcile_current_events(
    *,
    repository_root: Path,
    fotmob_admission_value: Any,
    fotmob_captures: Sequence[tuple[bytes, FotMobDataMatchesCaptureManifest]],
    execute_live_network: bool,
) -> CurrentShadowSportyBetCatalogFanoutReconciliationBundle:
    directory, _snapshot = capture_current_catalog_fanout_discovery(
        repository_root=repository_root,
        execute_live_network=execute_live_network,
    )
    return reconcile_current_events_from_catalog_fanout(
        repository_root=repository_root,
        fanout_evidence_directory=directory,
        fotmob_admission_value=fotmob_admission_value,
        fotmob_captures=fotmob_captures,
        execute_live_network=execute_live_network,
    )


def verify_current_event_discovery_reconciliation_bundle(
    value: Any,
) -> CurrentShadowSportyBetCatalogFanoutReconciliationBundle:
    if type(value) is not CurrentShadowSportyBetCatalogFanoutReconciliationBundle:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "value must be exact catalog fanout reconciliation bundle"
        )
    validate_contract()
    try:
        captures = reviewed._materialize_fotmob_captures(value._fotmob_captures)
        admission = reviewed._rederive_exact_fotmob_admission(
            value._fotmob_admission, captures
        )
    except reviewed.SportyBetCurrentEventDiscoveryError as exc:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(str(exc)) from exc
    fanout = verify_current_catalog_fanout_discovery(
        value._fanout_directory, repository_root=value._repository_root
    )
    rebuilt = _build_bundle(
        repository_root=value._repository_root,
        fanout_directory=value._fanout_directory,
        fanout=fanout,
        admission=admission,
        captures=captures,
        detail_directories=dict(value._detail_directories),
        evaluation_time=value.evaluation_time,
    )
    if _canonical(value.to_dict()) != _canonical(rebuilt.to_dict()):
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "catalog fanout reconciliation differs from retained-source replay"
        )
    return rebuilt


__all__ = [
    "AUTHORITY",
    "CANDIDATE_LOCAL_DIRECT_DETAIL_POLICY",
    "CATALOG_IDENTITY_POLICY",
    "CATALOG_PATH",
    "CurrentEventReconciliationDisposition",
    "CurrentEventReconciliationRow",
    "CurrentShadowDirectConfirmationDisposition",
    "CurrentShadowDirectConfirmationFailureRow",
    "CurrentShadowSportyBetCatalogFanoutReconciliationBundle",
    "CurrentShadowSportyBetCatalogFanoutReconciliationError",
    "CurrentShadowSportyBetCatalogFanoutSnapshot",
    "EXPECTED_CONTRACT_SHA256",
    "FANOUT_POLICY",
    "ProviderCatalogTournament",
    "ProviderTournamentObservation",
    "SportyBetCurrentEventDiscoveryError",
    "SportyBetCurrentEventDiscoveryReconciliationBundle",
    "calculate_contract_sha256",
    "capture_current_catalog_fanout_discovery",
    "catalog_request_target",
    "discover_and_reconcile_current_events",
    "reconcile_current_events_from_catalog_fanout",
    "tournament_request_target",
    "validate_contract",
    "verify_current_catalog_fanout_discovery",
    "verify_current_event_discovery_reconciliation_bundle",
]
