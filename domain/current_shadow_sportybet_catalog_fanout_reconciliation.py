"""Shadow reconciliation overlay with stable source/provider fixture identities.

The previously reviewed candidate-local PR258/PR-F implementation is preserved
byte-for-byte in ``_current_shadow_sportybet_catalog_fanout_reconciliation_candidate_local``.
The PR278 explicit alias registry remains a reviewed bootstrap, while the V2
boundary binds stable FotMob competition/team IDs to provider-native
category/tournament/competitor IDs so harmless later display-name drift does not
recreate the same reconciliation bottleneck.

Full UTC kickoff, home/away orientation, unique-match enforcement, current provider
discovery, direct provider event-detail confirmation, freshness, lead window and
downstream authority stay exact. No fuzzy matching, generic suffix stripping,
substring matching, reversal or time tolerance is added.
"""
from __future__ import annotations

import hashlib
import json
import os
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
FIXTURE_STABLE_IDENTITY_POLICY_ID = fixture_identity_v2.POLICY_ID
FIXTURE_STABLE_IDENTITY_REGISTRY_SHA256 = fixture_identity_v2.REGISTRY_SHA256
MATCHING_BASIS = fixture_identity_v2.MATCHING_BASIS
EXPECTED_CONTRACT_SHA256 = "c9f238039f14202159d055fadc3236684832403f74637323eb3b2cf83e836a33"

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


legacy.reviewed = _ReviewedShadowProxy()


def calculate_contract_sha256() -> str:
    payload = {
        "base_contract_sha256": legacy.base.EXPECTED_CONTRACT_SHA256,
        "candidate_local_direct_detail_policy": CANDIDATE_LOCAL_DIRECT_DETAIL_POLICY,
        "fixture_team_alias_policy_id": FIXTURE_TEAM_ALIAS_POLICY_ID,
        "fixture_team_alias_registry_sha256": FIXTURE_TEAM_ALIAS_REGISTRY_SHA256,
        "fixture_stable_identity_policy_id": FIXTURE_STABLE_IDENTITY_POLICY_ID,
        "fixture_stable_identity_registry_sha256": FIXTURE_STABLE_IDENTITY_REGISTRY_SHA256,
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
    if fixture_identity_v2.registry_sha256() != FIXTURE_STABLE_IDENTITY_REGISTRY_SHA256:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "Shadow stable fixture identity registry drifted"
        )
    actual = calculate_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "catalog fanout Shadow stable identity contract drifted"
        )
    return {
        "contract_sha256": actual,
        "base_contract_sha256": legacy.base.EXPECTED_CONTRACT_SHA256,
        "fixture_team_alias_policy_id": FIXTURE_TEAM_ALIAS_POLICY_ID,
        "fixture_team_alias_registry_sha256": FIXTURE_TEAM_ALIAS_REGISTRY_SHA256,
        "fixture_stable_identity_policy_id": FIXTURE_STABLE_IDENTITY_POLICY_ID,
        "fixture_stable_identity_registry_sha256": FIXTURE_STABLE_IDENTITY_REGISTRY_SHA256,
    }


legacy.MATCHING_BASIS = MATCHING_BASIS
legacy.EXPECTED_CONTRACT_SHA256 = EXPECTED_CONTRACT_SHA256
legacy.calculate_contract_sha256 = calculate_contract_sha256
legacy.validate_contract = validate_contract


_legacy_bundle_to_dict = CurrentShadowSportyBetCatalogFanoutReconciliationBundle.to_dict


def _bundle_to_dict_with_stable_identity(self: Any) -> dict[str, Any]:
    payload = _legacy_bundle_to_dict(self)
    payload["matching_basis"] = MATCHING_BASIS
    payload["fixture_team_alias_policy_id"] = FIXTURE_TEAM_ALIAS_POLICY_ID
    payload["fixture_team_alias_registry_sha256"] = FIXTURE_TEAM_ALIAS_REGISTRY_SHA256
    payload["fixture_stable_identity_policy_id"] = FIXTURE_STABLE_IDENTITY_POLICY_ID
    payload["fixture_stable_identity_registry_sha256"] = FIXTURE_STABLE_IDENTITY_REGISTRY_SHA256
    payload["fixture_stable_identity_state_sha256"] = getattr(
        self,
        "_fixture_stable_identity_state_sha256",
        fixture_identity_v2.state_sha256(),
    )
    return payload


CurrentShadowSportyBetCatalogFanoutReconciliationBundle.to_dict = (
    _bundle_to_dict_with_stable_identity
)


def _identity_observing_network_get(target: str):
    raw, observed = _network_get(target)
    fixture_identity_v2.observe_provider_payload(raw)
    return raw, observed


def _begin_identity_scope(
    fotmob_captures: Sequence[Any],
    fanout_evidence_directory: Path | None = None,
) -> None:
    fixture_identity_v2.reset_runtime_evidence()
    fixture_identity_v2.configure_persistent_state(
        os.environ.get("ATHENA_CURRENT_SHADOW_IDENTITY_STATE_PATH")
    )
    fixture_identity_v2.observe_fotmob_captures(fotmob_captures)
    if fanout_evidence_directory is not None:
        fixture_identity_v2.observe_provider_directory(fanout_evidence_directory)


def _bind_identity_state(bundle: Any) -> Any:
    object.__setattr__(
        bundle,
        "_fixture_stable_identity_state_sha256",
        fixture_identity_v2.state_sha256(),
    )
    return bundle


def _sync_wrapper_hooks() -> None:
    legacy._network_get = _identity_observing_network_get
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
    _begin_identity_scope(fotmob_captures, fanout_evidence_directory)
    _sync_wrapper_hooks()
    result = legacy.reconcile_current_events_from_catalog_fanout(
        repository_root=repository_root,
        fanout_evidence_directory=fanout_evidence_directory,
        fotmob_admission_value=fotmob_admission_value,
        fotmob_captures=fotmob_captures,
        execute_live_network=execute_live_network,
    )
    return _bind_identity_state(result)


def discover_and_reconcile_current_events(
    *,
    repository_root: Path,
    fotmob_admission_value: Any,
    fotmob_captures: Sequence[Any],
    execute_live_network: bool,
):
    validate_contract()
    _begin_identity_scope(fotmob_captures)
    _sync_wrapper_hooks()
    result = legacy.discover_and_reconcile_current_events(
        repository_root=repository_root,
        fotmob_admission_value=fotmob_admission_value,
        fotmob_captures=fotmob_captures,
        execute_live_network=execute_live_network,
    )
    return _bind_identity_state(result)


def verify_current_event_discovery_reconciliation_bundle(value: Any):
    validate_contract()
    captures = getattr(value, "_fotmob_captures", ())
    fanout_directory = getattr(value, "_fanout_directory", None)
    if fanout_directory is not None:
        _begin_identity_scope(captures, fanout_directory)
    expected_state = getattr(value, "_fixture_stable_identity_state_sha256", None)
    if (
        expected_state is not None
        and expected_state != fixture_identity_v2.state_sha256()
    ):
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "persisted Shadow fixture identity state differs from retained bundle"
        )
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
    "FIXTURE_STABLE_IDENTITY_POLICY_ID",
    "FIXTURE_STABLE_IDENTITY_REGISTRY_SHA256",
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
