"""Shadow reconciliation overlay with evidence-backed fixture identity V2.

The reviewed candidate-local PR258/PR-F implementation remains the transport and
replay authority.  This wrapper replaces run-specific display-name matching with a
versioned Shadow-only identity boundary that can use exact retained FotMob team IDs,
SportyBet competitor IDs, FotMob short/long names, explicit reviewed aliases and
reviewed competition-name equivalences.

Everything else stays exact: full UTC kickoff, home/away orientation, unique-match
enforcement, current provider discovery, direct provider event-detail confirmation,
freshness, lead window and downstream authority.  No fuzzy matching, substring
matching, generic suffix stripping, reversal, rounding or time tolerance is added.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Sequence

from domain import (
    _current_shadow_sportybet_catalog_fanout_reconciliation_candidate_local as legacy,
)
from domain import current_shadow_fixture_identity_aliases as fixture_aliases
from domain import current_shadow_fixture_identity_v2 as fixture_identity_v2
from domain import sportybet_current_event_discovery_reconciliation as _reviewed


SCHEMA_VERSION = legacy.SCHEMA_VERSION
DATASET_NAME = legacy.DATASET_NAME
DISCOVERY_DATASET_NAME = legacy.DISCOVERY_DATASET_NAME
STATUS = legacy.STATUS
PROVIDER = legacy.PROVIDER
PROVIDER_REGION = legacy.PROVIDER_REGION
ORIGIN = legacy.ORIGIN
OPER_ID = legacy.OPER_ID
FOOTBALL_SPORT_ID = legacy.FOOTBALL_SPORT_ID
CATALOG_PATH = legacy.CATALOG_PATH
UPCOMING_PATH = legacy.UPCOMING_PATH
CATALOG_SOURCE_METHOD = legacy.CATALOG_SOURCE_METHOD
FANOUT_SOURCE_METHOD = legacy.FANOUT_SOURCE_METHOD
MAX_RESPONSE_BYTES = legacy.MAX_RESPONSE_BYTES
MAX_MANIFEST_BYTES = legacy.MAX_MANIFEST_BYTES
MAX_SOURCE_AGE_SECONDS = legacy.MAX_SOURCE_AGE_SECONDS
MINIMUM_LEAD_SECONDS = legacy.MINIMUM_LEAD_SECONDS
REQUEST_NONCE_MAX_SKEW_MS = legacy.REQUEST_NONCE_MAX_SKEW_MS
REQUEST_HEADERS = legacy.REQUEST_HEADERS
ALLOWED_OUTPUT_RELATIVE = legacy.ALLOWED_OUTPUT_RELATIVE
CATALOG_RAW_FILENAME = legacy.CATALOG_RAW_FILENAME
MANIFEST_FILENAME = legacy.MANIFEST_FILENAME
TOURNAMENT_DIRNAME = legacy.TOURNAMENT_DIRNAME
DETAIL_CONFIRMATION_POLICY = legacy.DETAIL_CONFIRMATION_POLICY
CATALOG_IDENTITY_POLICY = legacy.CATALOG_IDENTITY_POLICY
FANOUT_POLICY = legacy.FANOUT_POLICY
OBSERVATION_AUTHORITY = legacy.OBSERVATION_AUTHORITY
NEXT_BOUNDARY = legacy.NEXT_BOUNDARY
AUTHORITY = legacy.AUTHORITY
CANDIDATE_LOCAL_DIRECT_DETAIL_POLICY = legacy.CANDIDATE_LOCAL_DIRECT_DETAIL_POLICY

FIXTURE_TEAM_ALIAS_POLICY_ID = fixture_aliases.POLICY_ID
FIXTURE_TEAM_ALIAS_REGISTRY_SHA256 = fixture_aliases.REGISTRY_SHA256
FIXTURE_IDENTITY_POLICY_ID = fixture_identity_v2.POLICY_ID
FIXTURE_IDENTITY_REGISTRY_SHA256 = fixture_identity_v2.REGISTRY_SHA256
FIXTURE_IDENTITY_SOURCE_REPLAY_POLICY_ID = fixture_identity_v2.SOURCE_REPLAY_POLICY_ID
FIXTURE_IDENTITY_PROVIDER_ID_POLICY_ID = fixture_identity_v2.PROVIDER_ID_POLICY_ID
MATCHING_BASIS = fixture_identity_v2.MATCHING_BASIS
EXPECTED_CONTRACT_SHA256 = "7dc03972f1ac9ef63a023508fa28439db30fe6c31a3a2c00523ca61aad4a93b4"

CurrentEventReconciliationDisposition = legacy.CurrentEventReconciliationDisposition
CurrentEventReconciliationRow = legacy.CurrentEventReconciliationRow
ProviderCatalogTournament = legacy.ProviderCatalogTournament
ProviderTournamentObservation = legacy.ProviderTournamentObservation
CurrentShadowSportyBetCatalogFanoutSnapshot = legacy.CurrentShadowSportyBetCatalogFanoutSnapshot
CurrentShadowDirectConfirmationDisposition = legacy.CurrentShadowDirectConfirmationDisposition
CurrentShadowDirectConfirmationFailureRow = legacy.CurrentShadowDirectConfirmationFailureRow
CurrentShadowSportyBetCatalogFanoutReconciliationBundle = (
    legacy.CurrentShadowSportyBetCatalogFanoutReconciliationBundle
)
SportyBetCurrentEventDiscoveryReconciliationBundle = (
    CurrentShadowSportyBetCatalogFanoutReconciliationBundle
)
CurrentShadowSportyBetCatalogFanoutReconciliationError = (
    legacy.CurrentShadowSportyBetCatalogFanoutReconciliationError
)
SportyBetCurrentEventDiscoveryError = legacy.SportyBetCurrentEventDiscoveryError

# Keep low-level helpers available to existing tests/callers.  ``_network_get``
# remains a wrapper-local test seam.
time = legacy.time
_canonical = legacy._canonical
_now_utc = legacy._now_utc
_utc = legacy._utc
_text = legacy._text
_sha = legacy._sha
_network_get = legacy._network_get
_parse_catalog = legacy._parse_catalog
_parse_tournament_response = legacy._parse_tournament_response
_evidence_root = legacy._evidence_root
_write_exclusive = legacy._write_exclusive
_raw_filename = legacy._raw_filename
_snapshot_from_parts = legacy._snapshot_from_parts
_event_from_mapping = legacy._event_from_mapping
_snapshot_from_manifest = legacy._snapshot_from_manifest
_set_frozen = legacy._set_frozen
catalog_request_target = legacy.catalog_request_target
tournament_request_target = legacy.tournament_request_target
live = legacy.live
base = legacy.base
reviewed = _reviewed


class _ReviewedShadowProxy:
    """Delegate the frozen reviewed module except for Shadow fixture matching."""

    def __getattr__(self, name: str) -> Any:
        if name == "_match_event":
            return fixture_identity_v2.match_event
        return getattr(_reviewed, name)


# Only the copied candidate-local module sees this proxy.  Non-Shadow consumers of
# the reviewed module retain their original literal matcher.
legacy.reviewed = _ReviewedShadowProxy()


def calculate_contract_sha256() -> str:
    payload = {
        "base_contract_sha256": legacy.base.EXPECTED_CONTRACT_SHA256,
        "candidate_local_direct_detail_policy": CANDIDATE_LOCAL_DIRECT_DETAIL_POLICY,
        "fixture_team_alias_policy_id": FIXTURE_TEAM_ALIAS_POLICY_ID,
        "fixture_team_alias_registry_sha256": FIXTURE_TEAM_ALIAS_REGISTRY_SHA256,
        "fixture_identity_policy_id": FIXTURE_IDENTITY_POLICY_ID,
        "fixture_identity_registry_sha256": FIXTURE_IDENTITY_REGISTRY_SHA256,
        "fixture_identity_source_replay_policy_id": FIXTURE_IDENTITY_SOURCE_REPLAY_POLICY_ID,
        "fixture_identity_provider_id_policy_id": FIXTURE_IDENTITY_PROVIDER_ID_POLICY_ID,
        "matching_basis": MATCHING_BASIS,
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
    legacy.base.validate_contract()
    if fixture_aliases.registry_sha256() != FIXTURE_TEAM_ALIAS_REGISTRY_SHA256:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "Shadow fixture alias registry identity drifted"
        )
    if fixture_identity_v2.registry_sha256() != FIXTURE_IDENTITY_REGISTRY_SHA256:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "Shadow fixture identity V2 registry drifted"
        )
    actual = calculate_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "catalog fanout Shadow fixture identity V2 contract drifted"
        )
    return {
        "contract_sha256": actual,
        "base_contract_sha256": legacy.base.EXPECTED_CONTRACT_SHA256,
        "fixture_team_alias_policy_id": FIXTURE_TEAM_ALIAS_POLICY_ID,
        "fixture_team_alias_registry_sha256": FIXTURE_TEAM_ALIAS_REGISTRY_SHA256,
        "fixture_identity_policy_id": FIXTURE_IDENTITY_POLICY_ID,
        "fixture_identity_registry_sha256": FIXTURE_IDENTITY_REGISTRY_SHA256,
    }


legacy.MATCHING_BASIS = MATCHING_BASIS
legacy.EXPECTED_CONTRACT_SHA256 = EXPECTED_CONTRACT_SHA256
legacy.calculate_contract_sha256 = calculate_contract_sha256
legacy.validate_contract = validate_contract


# Extend the durable bundle representation with both the retained alias identity
# and the new ID/source-replay identity.  The underlying source evidence remains
# unchanged and replayed byte-for-byte.
_legacy_bundle_to_dict = CurrentShadowSportyBetCatalogFanoutReconciliationBundle.to_dict


def _bundle_to_dict_with_identity(self: Any) -> dict[str, Any]:
    payload = _legacy_bundle_to_dict(self)
    payload["matching_basis"] = MATCHING_BASIS
    payload["fixture_team_alias_policy_id"] = FIXTURE_TEAM_ALIAS_POLICY_ID
    payload["fixture_team_alias_registry_sha256"] = FIXTURE_TEAM_ALIAS_REGISTRY_SHA256
    payload["fixture_identity_policy_id"] = FIXTURE_IDENTITY_POLICY_ID
    payload["fixture_identity_registry_sha256"] = FIXTURE_IDENTITY_REGISTRY_SHA256
    payload["fixture_identity_source_replay_policy_id"] = FIXTURE_IDENTITY_SOURCE_REPLAY_POLICY_ID
    payload["fixture_identity_provider_id_policy_id"] = FIXTURE_IDENTITY_PROVIDER_ID_POLICY_ID
    return payload


CurrentShadowSportyBetCatalogFanoutReconciliationBundle.to_dict = _bundle_to_dict_with_identity


def _sync_wrapper_hooks() -> None:
    legacy._network_get = _network_get
    legacy.time = time


def capture_current_catalog_fanout_discovery(
    *, repository_root: Path, execute_live_network: bool
):
    validate_contract()
    _sync_wrapper_hooks()
    return legacy.capture_current_catalog_fanout_discovery(
        repository_root=repository_root,
        execute_live_network=execute_live_network,
    )


def verify_current_catalog_fanout_discovery(
    evidence_directory: Path, *, repository_root: Path
):
    validate_contract()
    return legacy.verify_current_catalog_fanout_discovery(
        evidence_directory,
        repository_root=repository_root,
    )


def reconcile_current_events_from_catalog_fanout(
    *,
    repository_root: Path,
    fanout_evidence_directory: Path,
    fotmob_admission_value: Any,
    fotmob_captures: Sequence[Any],
    execute_live_network: bool,
):
    validate_contract()
    _sync_wrapper_hooks()
    fanout_snapshot = legacy.verify_current_catalog_fanout_discovery(
        fanout_evidence_directory,
        repository_root=repository_root,
    )
    with fixture_identity_v2.identity_context(
        fotmob_captures=fotmob_captures,
        fanout_evidence_directory=fanout_evidence_directory,
        fanout_snapshot=fanout_snapshot,
    ):
        return legacy.reconcile_current_events_from_catalog_fanout(
            repository_root=repository_root,
            fanout_evidence_directory=fanout_evidence_directory,
            fotmob_admission_value=fotmob_admission_value,
            fotmob_captures=fotmob_captures,
            execute_live_network=execute_live_network,
        )


def discover_and_reconcile_current_events(
    *,
    repository_root: Path,
    fotmob_admission_value: Any,
    fotmob_captures: Sequence[Any],
    execute_live_network: bool,
):
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


def verify_current_event_discovery_reconciliation_bundle(value: Any):
    validate_contract()
    fanout_snapshot = legacy.verify_current_catalog_fanout_discovery(
        value._fanout_directory,
        repository_root=value._repository_root,
    )
    with fixture_identity_v2.identity_context(
        fotmob_captures=value._fotmob_captures,
        fanout_evidence_directory=value._fanout_directory,
        fanout_snapshot=fanout_snapshot,
    ):
        return legacy.verify_current_event_discovery_reconciliation_bundle(value)


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
    "FIXTURE_IDENTITY_POLICY_ID",
    "FIXTURE_IDENTITY_PROVIDER_ID_POLICY_ID",
    "FIXTURE_IDENTITY_REGISTRY_SHA256",
    "FIXTURE_IDENTITY_SOURCE_REPLAY_POLICY_ID",
    "FIXTURE_TEAM_ALIAS_POLICY_ID",
    "FIXTURE_TEAM_ALIAS_REGISTRY_SHA256",
    "MATCHING_BASIS",
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
