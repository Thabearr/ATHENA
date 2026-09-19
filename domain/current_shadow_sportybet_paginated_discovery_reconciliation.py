"""Current Shadow paginated global provider discovery reconciliation overlay.

This module provides the Current Shadow reconciliation layer over the reviewed
paginated SportyBet event discovery endpoint (/api/ng/factsCenter/liveOrPrematchEvents).

It layers the reviewed Current Shadow compatibility stack:
- Team label whitespace/display projection (domain.current_shadow_sportybet_team_label_compatibility)
- Stable fixture identity recovery V2 and V3 (domain.current_shadow_fixture_identity_v2,
  scripts.current_shadow_fixture_identity_reconciliation_recovery)
- Run-199 retained display/competition alias overlay (domain.current_shadow_fixture_identity_run199_overlay)
- Tolerant direct event-detail quote inventory (domain.current_shadow_sportybet_tolerant_live_inventory)
- Strict append-only fixture identity state tracking

This boundary issues fixture-reconciliation authority only. It does not map
canonical markets, compute value, route, optimize, construct a slip, stake,
execute, or place a bet.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
import dataclasses
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import types
from typing import Any, Iterator

from domain import current_shadow_fixture_identity_aliases as fixture_aliases
from domain import current_shadow_fixture_identity_compatibility as identity_compatibility
from domain import current_shadow_fixture_identity_run199_overlay as run199_identity
from domain import current_shadow_fixture_identity_v2 as fixture_identity_v2
from domain import current_shadow_sportybet_team_label_compatibility as team_label_compatibility
from domain import current_shadow_sportybet_tolerant_live_inventory as tolerant_inventory
from domain import reviewed_fixture_catalog_admission as fotmob_admission
from domain import sportybet_current_event_discovery_reconciliation as reviewed_discovery
from domain import sportybet_live_event_quote_evidence as live
from domain.fotmob_data_matches_capture import (
    DATASET_NAME as FOTMOB_CAPTURE_DATASET_NAME,
    SCHEMA_VERSION as FOTMOB_CAPTURE_SCHEMA_VERSION,
    FotMobDataMatchesCaptureManifest,
    sha256_bytes as fotmob_sha256_bytes,
    sha256_data_matches_capture_manifest,
)
from domain.fotmob_fixture_candidate_review import FotMobReviewedFixtureCatalogInput
from domain.sportybet_lite_source_capture import (
    SportyBetLiteCaptureError,
    parse_utc_timestamp,
    serialize_utc,
    sha256_bytes,
)
from scripts import current_shadow_fixture_identity_reconciliation_recovery as identity_recovery

SCHEMA_VERSION = 1
CONTRACT_VERSION = 1
DATASET_NAME = (
    "athena-current-shadow-sportybet-paginated-discovery-reconciliation-v1"
)
DISCOVERY_DATASET_NAME = reviewed_discovery.DISCOVERY_DATASET_NAME
STATUS = "CURRENT_SHADOW_PAGINATED_GLOBAL_DISCOVERY_RECONCILIATION_VERIFIED"
POLICY_ID = "ATHENA_CURRENT_SHADOW_PAGINATED_GLOBAL_DISCOVERY_V1"
PROVIDER = reviewed_discovery.PROVIDER
PROVIDER_REGION = reviewed_discovery.PROVIDER_REGION
DISCOVERY_SOURCE_METHOD = reviewed_discovery.DISCOVERY_SOURCE_METHOD
ORIGIN = reviewed_discovery.ORIGIN
OPER_ID = reviewed_discovery.OPER_ID
DISCOVERY_PATH = reviewed_discovery.DISCOVERY_PATH
FOOTBALL_SPORT_ID = reviewed_discovery.FOOTBALL_SPORT_ID
PAGE_SIZE = reviewed_discovery.PAGE_SIZE
MAX_PAGES = reviewed_discovery.MAX_PAGES
MAX_RESPONSE_BYTES = reviewed_discovery.MAX_RESPONSE_BYTES
MAX_MANIFEST_BYTES = reviewed_discovery.MAX_MANIFEST_BYTES
MAX_SOURCE_AGE_SECONDS = reviewed_discovery.MAX_SOURCE_AGE_SECONDS
MINIMUM_LEAD_SECONDS = reviewed_discovery.MINIMUM_LEAD_SECONDS
ALLOWED_OUTPUT_RELATIVE = reviewed_discovery.ALLOWED_OUTPUT_RELATIVE
MANIFEST_FILENAME = reviewed_discovery.MANIFEST_FILENAME
PAGE_FILENAME_TEMPLATE = reviewed_discovery.PAGE_FILENAME_TEMPLATE
OBSERVATION_AUTHORITY = reviewed_discovery.OBSERVATION_AUTHORITY
NEXT_BOUNDARY = reviewed_discovery.NEXT_BOUNDARY

FIXTURE_TEAM_ALIAS_POLICY_ID = fixture_aliases.POLICY_ID
FIXTURE_TEAM_ALIAS_REGISTRY_SHA256 = fixture_aliases.REGISTRY_SHA256
FIXTURE_STABLE_IDENTITY_POLICY_ID = fixture_identity_v2.POLICY_ID
FIXTURE_STABLE_IDENTITY_REGISTRY_SHA256 = fixture_identity_v2.REGISTRY_SHA256
TEAM_LABEL_COMPATIBILITY_POLICY_ID = team_label_compatibility.POLICY_ID
TEAM_LABEL_COMPATIBILITY_POLICY_SHA256 = (
    team_label_compatibility.EXPECTED_POLICY_SHA256
)
RUN199_IDENTITY_POLICY_ID = run199_identity.POLICY_ID
RUN199_IDENTITY_POLICY_SHA256 = run199_identity.POLICY_SHA256
IDENTITY_RECOVERY_V3_POLICY_ID = identity_recovery.POLICY_ID

MATCHING_BASIS = (
    reviewed_discovery.MATCHING_BASIS
    + "_PLUS_CURRENT_SHADOW_TEAM_LABEL_AND_STABLE_IDENTITY_RECOVERY_V3_AND_RUN199_OVERLAY"
)
EXPECTED_CONTRACT_SHA256 = (
    "98bedacc3ccbc080312855fdd973545374ba2448dc89b841420bc70147ffaf21"
)

CurrentEventReconciliationDisposition = (
    reviewed_discovery.CurrentEventReconciliationDisposition
)
CurrentEventReconciliationRow = (
    reviewed_discovery.CurrentEventReconciliationRow
)
SportyBetDiscoveryPage = reviewed_discovery.SportyBetDiscoveryPage
SportyBetDiscoveredEvent = reviewed_discovery.SportyBetDiscoveredEvent
SportyBetCurrentEventDiscoveryManifest = (
    reviewed_discovery.SportyBetCurrentEventDiscoveryManifest
)
SportyBetCurrentEventDiscoveryReconciliationBundle = (
    reviewed_discovery.SportyBetCurrentEventDiscoveryReconciliationBundle
)
SportyBetCurrentEventDiscoveryError = (
    reviewed_discovery.SportyBetCurrentEventDiscoveryError
)


class CurrentShadowPaginatedDiscoveryReconciliationError(
    SportyBetCurrentEventDiscoveryError
):
    """Raised when Current Shadow paginated discovery reconciliation fails closed."""


AUTHORITY = types.MappingProxyType(
    {
        "current_event_discovery_issuer": True,
        "current_event_detail_confirmation_issuer": True,
        "fixture_reconciliation_issuer": True,
        "canonical_market_mapping": False,
        "price_all": False,
        "market_router": False,
        "portfolio_optimization": False,
        "final_selection": False,
        "accumulator_slip_construction": False,
        "sportybet_execution": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
    }
)


def _canonical_bytes(value: Any, *, newline: bool = False) -> bytes:
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentShadowPaginatedDiscoveryReconciliationError(
            "canonical JSON serialization failed"
        ) from exc
    return raw + (b"\n" if newline else b"")


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "status": STATUS,
        "policy_id": POLICY_ID,
        "base_discovery_contract_sha256": (
            reviewed_discovery.EXPECTED_CONTRACT_SHA256
        ),
        "fixture_team_alias_policy_id": FIXTURE_TEAM_ALIAS_POLICY_ID,
        "fixture_team_alias_registry_sha256": (
            FIXTURE_TEAM_ALIAS_REGISTRY_SHA256
        ),
        "fixture_stable_identity_policy_id": FIXTURE_STABLE_IDENTITY_POLICY_ID,
        "fixture_stable_identity_registry_sha256": (
            FIXTURE_STABLE_IDENTITY_REGISTRY_SHA256
        ),
        "team_label_compatibility_policy_id": (
            TEAM_LABEL_COMPATIBILITY_POLICY_ID
        ),
        "team_label_compatibility_policy_sha256": (
            TEAM_LABEL_COMPATIBILITY_POLICY_SHA256
        ),
        "run199_identity_policy_id": RUN199_IDENTITY_POLICY_ID,
        "run199_identity_policy_sha256": RUN199_IDENTITY_POLICY_SHA256,
        "identity_recovery_v3_policy_id": IDENTITY_RECOVERY_V3_POLICY_ID,
        "matching_basis": MATCHING_BASIS,
        "next_boundary": NEXT_BOUNDARY,
        "authority": dict(AUTHORITY),
    }


def calculate_contract_sha256() -> str:
    return hashlib.sha256(
        _canonical_bytes(
            {"version": CONTRACT_VERSION, "semantics": _contract_payload()},
            newline=False,
        )
    ).hexdigest()


def validate_contract() -> Mapping[str, Any]:
    reviewed_discovery.validate_current_event_discovery_contract()
    if fixture_aliases.registry_sha256() != FIXTURE_TEAM_ALIAS_REGISTRY_SHA256:
        raise CurrentShadowPaginatedDiscoveryReconciliationError(
            "Shadow fixture alias registry identity drifted"
        )
    if (
        fixture_identity_v2.registry_sha256()
        != FIXTURE_STABLE_IDENTITY_REGISTRY_SHA256
    ):
        raise CurrentShadowPaginatedDiscoveryReconciliationError(
            "Shadow stable fixture identity registry drifted"
        )
    if (
        team_label_compatibility.policy_sha256()
        != TEAM_LABEL_COMPATIBILITY_POLICY_SHA256
    ):
        raise CurrentShadowPaginatedDiscoveryReconciliationError(
            "Shadow SportyBet team-label compatibility identity drifted"
        )
    if run199_identity.policy_sha256() != RUN199_IDENTITY_POLICY_SHA256:
        raise CurrentShadowPaginatedDiscoveryReconciliationError(
            "Shadow run-199 identity policy drifted"
        )
    actual = calculate_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise CurrentShadowPaginatedDiscoveryReconciliationError(
            f"Current Shadow paginated discovery reconciliation contract drifted: actual {actual}"
        )
    return types.MappingProxyType(
        {
            "contract_sha256": actual,
            "base_discovery_contract_sha256": (
                reviewed_discovery.EXPECTED_CONTRACT_SHA256
            ),
        }
    )


# ---------------------------------------------------------------------------
# Stable identity tracking & state scoping
# ---------------------------------------------------------------------------

def _copy_identity_state(state: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(
        dict(state),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ))


def _identity_state_snapshot() -> dict[str, Any]:
    return identity_compatibility.identity_state_snapshot()


def _identity_state_sha256(snapshot: Mapping[str, Any]) -> str:
    return identity_compatibility.identity_state_sha256(snapshot)


def _bind_identity_state(bundle: Any) -> Any:
    snapshot = _identity_state_snapshot()
    object.__setattr__(
        bundle,
        "_fixture_stable_identity_state_sha256",
        _identity_state_sha256(snapshot),
    )
    object.__setattr__(
        bundle, "_fixture_stable_identity_state_snapshot", snapshot
    )
    return bundle


def _bind_retained_identity_state(
    bundle: Any,
    *,
    state_sha256: str,
    snapshot: Mapping[str, Any],
) -> Any:
    object.__setattr__(
        bundle, "_fixture_stable_identity_state_sha256", state_sha256
    )
    object.__setattr__(
        bundle,
        "_fixture_stable_identity_state_snapshot",
        _copy_identity_state(snapshot),
    )
    return bundle


# The implementation lives in the source-agnostic compatibility owner.  These
# narrow adapters preserve the historical module's replay API without making
# its paginated acquisition path the active Current Shadow authority.
def _identity_state_snapshot() -> dict[str, Any]:
    return identity_compatibility.identity_state_snapshot()


def _identity_state_sha256(snapshot: Mapping[str, Any]) -> str:
    return identity_compatibility.identity_state_sha256(snapshot)


def _verify_identity_state_append_only_extension(
    retained_state: Mapping[str, Any],
    current_state: Mapping[str, Any],
) -> None:
    try:
        identity_compatibility.verify_identity_state_append_only_extension(
            retained_state, current_state
        )
    except Exception as exc:
        raise CurrentShadowPaginatedDiscoveryReconciliationError(str(exc)) from exc


def _begin_identity_scope(
    fotmob_captures: Sequence[Any],
    discovery_evidence_directory: Path | None = None,
) -> None:
    try:
        identity_compatibility.begin_identity_scope(
            fotmob_captures, discovery_evidence_directory
        )
    except Exception as exc:
        raise CurrentShadowPaginatedDiscoveryReconciliationError(str(exc)) from exc


def _project_event_labels(
    event: SportyBetDiscoveredEvent,
) -> SportyBetDiscoveredEvent:
    try:
        return identity_compatibility.project_event_labels(event)
    except Exception as exc:
        raise CurrentShadowPaginatedDiscoveryReconciliationError(str(exc)) from exc


def _match_current_shadow_event(
    event: SportyBetDiscoveredEvent,
    reviewed_rows: Sequence[FotMobReviewedFixtureCatalogInput],
) -> tuple[FotMobReviewedFixtureCatalogInput, ...]:
    try:
        return identity_compatibility.match_current_shadow_event(event, reviewed_rows)
    except Exception as exc:
        raise CurrentShadowPaginatedDiscoveryReconciliationError(str(exc)) from exc


class _Legacy:
    reviewed = reviewed_discovery


legacy = _Legacy()


# ---------------------------------------------------------------------------
# Discovery & Reconciliation APIs
# ---------------------------------------------------------------------------

def capture_current_paginated_discovery(
    *, repository_root: Path, execute_live_network: bool
) -> tuple[Path, SportyBetCurrentEventDiscoveryManifest]:
    """Capture paginated SportyBet event discovery via the FactsCenter endpoint."""
    validate_contract()
    return reviewed_discovery.capture_current_event_discovery(
        repository_root=repository_root,
        execute_live_network=execute_live_network,
    )


capture_current_catalog_fanout_discovery = capture_current_paginated_discovery


def verify_current_paginated_discovery(
    evidence_directory: Path, *, repository_root: Path
) -> SportyBetCurrentEventDiscoveryManifest:
    """Verify an existing paginated discovery directory against exact raw replay."""
    validate_contract()
    return reviewed_discovery.verify_current_event_discovery(
        evidence_directory, repository_root=repository_root
    )


def _build_shadow_bundle(
    *,
    repository_root: Path,
    discovery_directory: Path,
    discovery: SportyBetCurrentEventDiscoveryManifest,
    admission: fotmob_admission.ReviewedFixtureCatalogAdmission,
    captures: tuple[tuple[bytes, FotMobDataMatchesCaptureManifest], ...],
    detail_directories: Mapping[str, Path],
    evaluation_time: datetime,
) -> SportyBetCurrentEventDiscoveryReconciliationBundle:
    evaluation = reviewed_discovery._utc(evaluation_time, "evaluation_time")
    reviewed = reviewed_discovery._reviewed_rows(admission)

    # Project team labels on all discovered events
    projected_events = [_project_event_labels(ev) for ev in discovery.events]

    provisional: dict[
        str, tuple[str, tuple[FotMobReviewedFixtureCatalogInput, ...]]
    ] = {}
    for event in projected_events:
        if not event.prematch_bookable_observed:
            provisional[event.event_id] = ("NONBOOKABLE", ())
        elif event.competition_name is None:
            provisional[event.event_id] = ("NO_COMPETITION", ())
        else:
            matches = _match_current_shadow_event(event, reviewed)
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
        raise CurrentShadowPaginatedDiscoveryReconciliationError(
            "direct event-detail evidence set does not match exact unique reconciliation candidates"
        )

    rows: list[CurrentEventReconciliationRow] = []
    for event in projected_events:
        state, matches = provisional[event.event_id]
        discovery_age = (
            evaluation - event.source_observed_at
        ).total_seconds()
        kickoff_lead = (event.kickoff_utc - evaluation).total_seconds()
        if discovery_age < 0:
            raise CurrentShadowPaginatedDiscoveryReconciliationError(
                "evaluation_time predates a discovery response completion"
            )
        disposition: CurrentEventReconciliationDisposition
        matched_id: str | None = None
        direct_observed: datetime | None = None
        direct_age: float | None = None
        direct_manifest_sha: str | None = None
        direct_inventory_sha: str | None = None
        direct_raw_sha: str | None = None

        if discovery_age > MAX_SOURCE_AGE_SECONDS:
            disposition = (
                CurrentEventReconciliationDisposition.DISCOVERY_EVIDENCE_STALE
            )
        elif kickoff_lead <= MINIMUM_LEAD_SECONDS:
            disposition = (
                CurrentEventReconciliationDisposition.PROVIDER_EVENT_TOO_CLOSE_TO_KICKOFF
            )
        elif state == "NONBOOKABLE":
            disposition = (
                CurrentEventReconciliationDisposition.DISCOVERY_EVENT_NOT_PREMATCH_BOOKABLE
            )
        elif state == "NO_COMPETITION":
            disposition = (
                CurrentEventReconciliationDisposition.PROVIDER_COMPETITION_UNPROVEN
            )
        elif state == "NO_MATCH":
            disposition = (
                CurrentEventReconciliationDisposition.NO_EXACT_REVIEWED_FOTMOB_MATCH
            )
        elif state == "AMBIGUOUS_FOTMOB":
            disposition = (
                CurrentEventReconciliationDisposition.AMBIGUOUS_EXACT_REVIEWED_FOTMOB_MATCH
            )
        elif target_counts[matches[0].source_fixture_identifier] > 1:
            disposition = (
                CurrentEventReconciliationDisposition.AMBIGUOUS_PROVIDER_EVENT_FOR_FIXTURE
            )
        else:
            matched = matches[0]
            matched_id = matched.source_fixture_identifier
            inventory = (
                tolerant_inventory.build_shadow_live_event_quote_inventory(
                    detail_directories[event.event_id],
                    repository_root=repository_root,
                )
            )
            direct_observed = inventory.observed_at
            direct_age = (evaluation - inventory.observed_at).total_seconds()
            if direct_age < 0:
                raise CurrentShadowPaginatedDiscoveryReconciliationError(
                    "evaluation_time predates a direct event-detail response completion"
                )
            direct_manifest_sha = inventory.source_manifest_sha256
            direct_inventory_sha = inventory.canonical_sha256
            direct_raw_sha = inventory.source_raw_sha256

            # For identity check, compare with projected or raw names
            home_matches = (
                inventory.home_team_name == event.home_team_name
                or team_label_compatibility.project_team_label(
                    event_id=event.event_id,
                    field="homeTeamName",
                    value=inventory.home_team_name,
                )
                == event.home_team_name
            )
            away_matches = (
                inventory.away_team_name == event.away_team_name
                or team_label_compatibility.project_team_label(
                    event_id=event.event_id,
                    field="awayTeamName",
                    value=inventory.away_team_name,
                )
                == event.away_team_name
            )
            if (
                inventory.event_id != event.event_id
                or not (home_matches and away_matches)
                or inventory.kickoff_utc != event.kickoff_utc
            ):
                disposition = (
                    CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_IDENTITY_MISMATCH
                )
            elif not inventory.prematch_bookable_observed:
                disposition = (
                    CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_NOT_PREMATCH_BOOKABLE
                )
            elif direct_age > MAX_SOURCE_AGE_SECONDS:
                disposition = (
                    CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_STALE
                )
            else:
                disposition = (
                    CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED
                )

        rows.append(
            CurrentEventReconciliationRow(
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
                    is CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED
                ),
            )
        )

    ordered = tuple(sorted(rows, key=lambda item: item.event_id))
    admission_payload = admission.to_dict()
    detail_tuple = tuple(
        sorted(
            (
                (event_id, Path(path))
                for event_id, path in detail_directories.items()
            ),
            key=lambda item: item[0],
        )
    )
    value = object.__new__(
        SportyBetCurrentEventDiscoveryReconciliationBundle
    )
    bundle = reviewed_discovery._set_frozen(
        value,
        {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "status": STATUS,
            "evaluation_time": evaluation,
            "max_source_age_seconds": MAX_SOURCE_AGE_SECONDS,
            "minimum_lead_seconds": MINIMUM_LEAD_SECONDS,
            "discovery_manifest_sha256": discovery.canonical_sha256,
            "source_fotmob_admission_sha256": (
                fotmob_admission.sha256_reviewed_fixture_catalog_admission(
                    admission
                )
            ),
            "source_fotmob_candidate_bundle_sha256": admission_payload[
                "candidate_bundle_sha256"
            ],
            "source_fotmob_review_bundle_sha256": admission_payload[
                "review_bundle_sha256"
            ],
            "source_fotmob_handoff_sha256": admission_payload[
                "handoff_sha256"
            ],
            "source_fotmob_catalog_sha256": admission_payload[
                "catalog_sha256"
            ],
            "source_fotmob_manifest_sha256": admission_payload[
                "manifest_sha256"
            ],
            "fotmob_capture_identities": (
                reviewed_discovery._capture_identity_rows(captures)
            ),
            "rows": ordered,
            "authority": reviewed_discovery._output_authority(ordered),
            "next_boundary": NEXT_BOUNDARY,
            "contract_sha256": EXPECTED_CONTRACT_SHA256,
            "_repository_root": Path(repository_root),
            "_discovery_directory": Path(discovery_directory),
            "_detail_directories": detail_tuple,
            "_fotmob_admission": admission,
            "_fotmob_captures": captures,
        },
    )
    return _bind_identity_state(bundle)


def reconcile_current_events_from_paginated_discovery(
    *,
    repository_root: Path,
    discovery_evidence_directory: Path,
    fotmob_admission_value: Any,
    fotmob_captures: Sequence[Any],
    execute_live_network: bool,
) -> SportyBetCurrentEventDiscoveryReconciliationBundle:
    """Reconcile already-discovered events against a reviewed FotMob admission."""
    validate_contract()
    repository = Path(repository_root).resolve(strict=True)
    _begin_identity_scope(fotmob_captures, discovery_evidence_directory)
    captures = reviewed_discovery._materialize_fotmob_captures(fotmob_captures)
    admission = reviewed_discovery._rederive_exact_fotmob_admission(
        fotmob_admission_value, captures
    )
    discovery = reviewed_discovery.verify_current_event_discovery(
        discovery_evidence_directory, repository_root=repository
    )
    reviewed = reviewed_discovery._reviewed_rows(admission)

    projected_events = [_project_event_labels(ev) for ev in discovery.events]
    provisional: dict[
        str, tuple[str, tuple[FotMobReviewedFixtureCatalogInput, ...]]
    ] = {}
    for event in projected_events:
        if not event.prematch_bookable_observed:
            provisional[event.event_id] = ("NONBOOKABLE", ())
        elif event.competition_name is None:
            provisional[event.event_id] = ("NO_COMPETITION", ())
        else:
            matches = _match_current_shadow_event(event, reviewed)
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
        detail_dir = (
            repository
            / live.ALLOWED_OUTPUT_RELATIVE
            / event_id.replace(":", "-")
        )
        if execute_live_network:
            try:
                directory, _manifest = live.capture_live_event_quote_evidence(
                    event_id=event_id,
                    repository_root=repository,
                    execute_live_network=True,
                )
                tolerant_inventory.build_shadow_live_event_quote_inventory(
                    directory,
                    repository_root=repository,
                )
                detail_dirs[event_id] = directory
            except Exception as exc:
                raise CurrentShadowPaginatedDiscoveryReconciliationError(
                    f"direct event-detail acquisition failed closed for {event_id}: {exc}"
                ) from exc
        elif detail_dir.exists() and detail_dir.is_dir():
            detail_dirs[event_id] = detail_dir
        else:
            raise CurrentShadowPaginatedDiscoveryReconciliationError(
                f"direct event-detail evidence missing for {event_id} with execute_live_network=False"
            )

    evaluation_time = reviewed_discovery._now_utc()
    return _build_shadow_bundle(
        repository_root=repository,
        discovery_directory=discovery_evidence_directory,
        discovery=discovery,
        admission=admission,
        captures=captures,
        detail_directories=detail_dirs,
        evaluation_time=evaluation_time,
    )


def discover_and_reconcile_current_events(
    *,
    repository_root: Path,
    fotmob_admission_value: Any,
    fotmob_captures: Sequence[Any],
    execute_live_network: bool,
) -> SportyBetCurrentEventDiscoveryReconciliationBundle:
    """Discover events via FactsCenter and reconcile under Current Shadow compatibility."""
    validate_contract()
    if execute_live_network is not True:
        raise CurrentShadowPaginatedDiscoveryReconciliationError(
            "live current-event reconciliation requires exact execute_live_network=True"
        )
    repository = Path(repository_root).resolve(strict=True)
    discovery_directory, _discovery = capture_current_paginated_discovery(
        repository_root=repository,
        execute_live_network=True,
    )
    return reconcile_current_events_from_paginated_discovery(
        repository_root=repository,
        discovery_evidence_directory=discovery_directory,
        fotmob_admission_value=fotmob_admission_value,
        fotmob_captures=fotmob_captures,
        execute_live_network=True,
    )


def verify_current_event_discovery_reconciliation_bundle(
    value: Any,
) -> SportyBetCurrentEventDiscoveryReconciliationBundle:
    """Replay retained sources and require exact deterministic bundle equality."""
    validate_contract()
    captures = getattr(value, "_fotmob_captures", ())
    discovery_directory = getattr(value, "_discovery_directory", None)
    if discovery_directory is not None:
        _begin_identity_scope(captures, discovery_directory)
    expected_state = getattr(
        value, "_fixture_stable_identity_state_sha256", None
    )
    retained_state = None
    if expected_state is not None:
        retained_state = getattr(
            value, "_fixture_stable_identity_state_snapshot", None
        )
        if type(retained_state) is not dict:
            raise CurrentShadowPaginatedDiscoveryReconciliationError(
                "retained Shadow fixture identity state snapshot is unavailable"
            )
        if _identity_state_sha256(retained_state) != expected_state:
            raise CurrentShadowPaginatedDiscoveryReconciliationError(
                "retained Shadow fixture identity state snapshot hash drifted"
            )
        current_state = _identity_state_snapshot()
        _verify_identity_state_append_only_extension(
            retained_state, current_state
        )

    repository = value._repository_root
    captures_mat = reviewed_discovery._materialize_fotmob_captures(
        value._fotmob_captures
    )
    admission = reviewed_discovery._rederive_exact_fotmob_admission(
        value._fotmob_admission, captures_mat
    )
    discovery = reviewed_discovery.verify_current_event_discovery(
        value._discovery_directory,
        repository_root=repository,
    )
    detail_dirs = dict(value._detail_directories)
    rebuilt = _build_shadow_bundle(
        repository_root=repository,
        discovery_directory=value._discovery_directory,
        discovery=discovery,
        admission=admission,
        captures=captures_mat,
        detail_directories=detail_dirs,
        evaluation_time=value.evaluation_time,
    )
    if _canonical_bytes(value.to_dict()) != _canonical_bytes(rebuilt.to_dict()):
        raise CurrentShadowPaginatedDiscoveryReconciliationError(
            "current event reconciliation differs from exact retained-source replay"
        )
    if expected_state is not None and retained_state is not None:
        return _bind_retained_identity_state(
            rebuilt,
            state_sha256=expected_state,
            snapshot=retained_state,
        )
    return rebuilt


__all__ = [
    "AUTHORITY",
    "CONTRACT_VERSION",
    "CurrentEventReconciliationDisposition",
    "CurrentEventReconciliationRow",
    "CurrentShadowPaginatedDiscoveryReconciliationError",
    "DATASET_NAME",
    "DISCOVERY_DATASET_NAME",
    "DISCOVERY_PATH",
    "EXPECTED_CONTRACT_SHA256",
    "FIXTURE_STABLE_IDENTITY_POLICY_ID",
    "FIXTURE_STABLE_IDENTITY_REGISTRY_SHA256",
    "FIXTURE_TEAM_ALIAS_POLICY_ID",
    "FIXTURE_TEAM_ALIAS_REGISTRY_SHA256",
    "IDENTITY_RECOVERY_V3_POLICY_ID",
    "MATCHING_BASIS",
    "MAX_PAGES",
    "MAX_SOURCE_AGE_SECONDS",
    "MINIMUM_LEAD_SECONDS",
    "NEXT_BOUNDARY",
    "PAGE_SIZE",
    "POLICY_ID",
    "RUN199_IDENTITY_POLICY_ID",
    "RUN199_IDENTITY_POLICY_SHA256",
    "SCHEMA_VERSION",
    "STATUS",
    "SportyBetCurrentEventDiscoveryError",
    "SportyBetCurrentEventDiscoveryManifest",
    "SportyBetCurrentEventDiscoveryReconciliationBundle",
    "SportyBetDiscoveredEvent",
    "SportyBetDiscoveryPage",
    "TEAM_LABEL_COMPATIBILITY_POLICY_ID",
    "TEAM_LABEL_COMPATIBILITY_POLICY_SHA256",
    "calculate_contract_sha256",
    "capture_current_catalog_fanout_discovery",
    "capture_current_paginated_discovery",
    "discover_and_reconcile_current_events",
    "legacy",
    "reconcile_current_events_from_paginated_discovery",
    "validate_contract",
    "verify_current_event_discovery_reconciliation_bundle",
    "verify_current_paginated_discovery",
]
