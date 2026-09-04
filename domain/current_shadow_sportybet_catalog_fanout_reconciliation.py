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

from collections import Counter
from contextlib import contextmanager
import hashlib
import json
import os
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, Sequence

from domain import (
    _current_shadow_sportybet_catalog_fanout_reconciliation_candidate_local as legacy,
)
from domain import current_shadow_fixture_identity_aliases as fixture_aliases
from domain import current_shadow_fixture_identity_v2 as fixture_identity_v2
from domain import current_shadow_sportybet_team_label_compatibility as team_label_compatibility
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
TEAM_LABEL_COMPATIBILITY_POLICY_ID = team_label_compatibility.POLICY_ID
TEAM_LABEL_COMPATIBILITY_POLICY_SHA256 = (
    team_label_compatibility.EXPECTED_POLICY_SHA256
)
MATCHING_BASIS = fixture_identity_v2.MATCHING_BASIS
EXPECTED_CONTRACT_SHA256 = "8c88c40beabd1a35ac2d5519e4e26b91bb1289548ec23b27c2b7b94a3229eb62"

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


def _reviewed_shadow_event_from_mapping(
    value: Mapping[str, Any],
    *,
    inherited_competition: str | None,
    page_num: int,
    raw_sha256: str,
    observed_at: Any,
):
    """Project only exact evidence-reviewed provider label whitespace cases."""
    event_id = _reviewed._event_id(value.get("eventId"))
    projected = dict(value)
    try:
        projected["homeTeamName"] = team_label_compatibility.project_team_label(
            event_id=event_id,
            field="homeTeamName",
            value=value.get("homeTeamName"),
        )
        projected["awayTeamName"] = team_label_compatibility.project_team_label(
            event_id=event_id,
            field="awayTeamName",
            value=value.get("awayTeamName"),
        )
    except team_label_compatibility.CurrentShadowSportyBetTeamLabelCompatibilityError as exc:
        raise _reviewed.SportyBetCurrentEventDiscoveryError(str(exc)) from exc
    return _reviewed._event_from_mapping(
        projected,
        inherited_competition=inherited_competition,
        page_num=page_num,
        raw_sha256=raw_sha256,
        observed_at=observed_at,
    )


class _ReviewedShadowProxy:
    """Delegate the frozen reviewed module except for Shadow-specific compatibility."""

    def __getattr__(self, name: str) -> Any:
        if name == "_match_event":
            return fixture_identity_v2.match_event
        if name == "_event_from_mapping":
            return _reviewed_shadow_event_from_mapping
        return getattr(_reviewed, name)


legacy.reviewed = _ReviewedShadowProxy()


def _shadow_parse_tournament_response(
    raw: bytes,
    *,
    category_id: str,
    tournament_id: str,
    request_nonce_ms: int,
    observed_at: Any,
):
    """Frozen fanout parser plus the exact reviewed team-label projection only."""
    if type(raw) is not bytes or not raw or len(raw) > MAX_RESPONSE_BYTES:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "fanout response must be bounded non-empty bytes"
        )
    try:
        payload = live.strict_json_loads(raw)
    except live.SportyBetLiveEventQuoteEvidenceError as exc:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(str(exc)) from exc
    if type(payload) is not dict or payload.get("bizCode") != 10000:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "fanout provider response must be successful"
        )
    data = payload.get("data")
    if type(data) is not list:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "fanout data must be a list"
        )
    raw_hash = base.sha256_bytes(raw)
    observed = _utc(observed_at, "observed_at")
    events = []
    for row in data:
        if type(row) is not dict:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
                "fanout event row must be object"
            )
        try:
            event = _reviewed_shadow_event_from_mapping(
                row,
                inherited_competition=None,
                page_num=1,
                raw_sha256=raw_hash,
                observed_at=observed,
            )
        except _reviewed.SportyBetCurrentEventDiscoveryError as exc:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError(str(exc)) from exc
        events.append(event)
    ids = [item.event_id for item in events]
    if len(ids) != len(set(ids)):
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "fanout response contains duplicate event IDs"
        )
    target = tournament_request_target(
        category_id=category_id,
        tournament_id=tournament_id,
        request_nonce_ms=request_nonce_ms,
    )
    observation = ProviderTournamentObservation(
        category_id=category_id,
        tournament_id=tournament_id,
        request_target=target,
        request_nonce_ms=request_nonce_ms,
        observed_at=observed,
        raw_sha256=raw_hash,
        raw_size=len(raw),
        event_ids=tuple(sorted(ids)),
    )
    return observation, tuple(sorted(events, key=lambda item: item.event_id))


_parse_tournament_response = _shadow_parse_tournament_response


@contextmanager
def _shadow_parser_scope() -> Iterator[None]:
    """Use the compatibility parser only while the Shadow wrapper is executing."""
    previous_legacy_parser = legacy._parse_tournament_response
    previous_base_parser = base._parse_tournament_response
    legacy._parse_tournament_response = _shadow_parse_tournament_response
    base._parse_tournament_response = _shadow_parse_tournament_response
    try:
        yield
    finally:
        legacy._parse_tournament_response = previous_legacy_parser
        base._parse_tournament_response = previous_base_parser


def calculate_contract_sha256() -> str:
    payload = {
        "base_contract_sha256": legacy.base.EXPECTED_CONTRACT_SHA256,
        "candidate_local_direct_detail_policy": CANDIDATE_LOCAL_DIRECT_DETAIL_POLICY,
        "fixture_team_alias_policy_id": FIXTURE_TEAM_ALIAS_POLICY_ID,
        "fixture_team_alias_registry_sha256": FIXTURE_TEAM_ALIAS_REGISTRY_SHA256,
        "fixture_stable_identity_policy_id": FIXTURE_STABLE_IDENTITY_POLICY_ID,
        "fixture_stable_identity_registry_sha256": FIXTURE_STABLE_IDENTITY_REGISTRY_SHA256,
        "matching_basis": MATCHING_BASIS,
        "team_label_compatibility_policy_id": TEAM_LABEL_COMPATIBILITY_POLICY_ID,
        "team_label_compatibility_policy_sha256": TEAM_LABEL_COMPATIBILITY_POLICY_SHA256,
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
    if (
        team_label_compatibility.policy_sha256()
        != TEAM_LABEL_COMPATIBILITY_POLICY_SHA256
    ):
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "Shadow SportyBet team-label compatibility identity drifted"
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
        "team_label_compatibility_policy_id": TEAM_LABEL_COMPATIBILITY_POLICY_ID,
        "team_label_compatibility_policy_sha256": TEAM_LABEL_COMPATIBILITY_POLICY_SHA256,
    }


legacy.MATCHING_BASIS = MATCHING_BASIS
legacy.EXPECTED_CONTRACT_SHA256 = EXPECTED_CONTRACT_SHA256
legacy.calculate_contract_sha256 = calculate_contract_sha256
legacy.validate_contract = validate_contract


_legacy_bundle_to_dict = CurrentShadowSportyBetCatalogFanoutReconciliationBundle.to_dict
_replay_identity_state_sha256: str | None = None


def _serialized_identity_state_sha256(self: Any) -> str:
    explicit = getattr(self, "_fixture_stable_identity_state_sha256", None)
    if explicit is not None:
        return explicit
    if _replay_identity_state_sha256 is not None:
        return _replay_identity_state_sha256
    return fixture_identity_v2.state_sha256()


@contextmanager
def _retained_identity_serialization_scope(state_sha256: str) -> Iterator[None]:
    """Serialize rebuilt replay bundles with their retained identity-state ancestry."""
    global _replay_identity_state_sha256
    previous = _replay_identity_state_sha256
    _replay_identity_state_sha256 = state_sha256
    try:
        yield
    finally:
        _replay_identity_state_sha256 = previous


def _bundle_to_dict_with_stable_identity(self: Any) -> dict[str, Any]:
    payload = _legacy_bundle_to_dict(self)
    payload["matching_basis"] = MATCHING_BASIS
    payload["fixture_team_alias_policy_id"] = FIXTURE_TEAM_ALIAS_POLICY_ID
    payload["fixture_team_alias_registry_sha256"] = FIXTURE_TEAM_ALIAS_REGISTRY_SHA256
    payload["fixture_stable_identity_policy_id"] = FIXTURE_STABLE_IDENTITY_POLICY_ID
    payload["fixture_stable_identity_registry_sha256"] = FIXTURE_STABLE_IDENTITY_REGISTRY_SHA256
    payload["team_label_compatibility_policy_id"] = TEAM_LABEL_COMPATIBILITY_POLICY_ID
    payload["team_label_compatibility_policy_sha256"] = TEAM_LABEL_COMPATIBILITY_POLICY_SHA256
    payload["fixture_stable_identity_state_sha256"] = _serialized_identity_state_sha256(self)
    return payload


CurrentShadowSportyBetCatalogFanoutReconciliationBundle.to_dict = (
    _bundle_to_dict_with_stable_identity
)


_IDENTITY_STATE_PAYLOAD_KEYS = frozenset({
    "schema_version",
    "policy_id",
    "matching_basis",
    "seed_registry_sha256",
    "learned_team_identities",
    "learned_competition_identities",
    "evidence_records",
    "authority",
})
_IDENTITY_STATE_IMMUTABLE_KEYS = (
    "schema_version",
    "policy_id",
    "matching_basis",
    "seed_registry_sha256",
    "authority",
)
_IDENTITY_STATE_APPEND_ONLY_KEYS = (
    "learned_team_identities",
    "learned_competition_identities",
    "evidence_records",
)


def _identity_state_snapshot() -> dict[str, Any]:
    """Retain an exact JSON-safe copy of the current stable-identity state."""
    payload = fixture_identity_v2._state_payload()
    return json.loads(json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ))


def _identity_state_sha256(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _copy_identity_state(payload: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ))


def _verify_identity_state_append_only_extension(
    retained: Mapping[str, Any],
    current: Mapping[str, Any],
) -> None:
    """Require current persistent learning to preserve every retained fact exactly."""
    if (
        set(retained) != _IDENTITY_STATE_PAYLOAD_KEYS
        or set(current) != _IDENTITY_STATE_PAYLOAD_KEYS
    ):
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "Shadow fixture identity state payload shape drifted"
        )
    for key in _IDENTITY_STATE_IMMUTABLE_KEYS:
        if retained[key] != current[key]:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
                "persisted Shadow fixture identity state changed retained policy ancestry"
            )
    for key in _IDENTITY_STATE_APPEND_ONLY_KEYS:
        retained_rows = retained[key]
        current_rows = current[key]
        if type(retained_rows) is not list or type(current_rows) is not list:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
                "Shadow fixture identity append-only state collection drifted"
            )
        retained_counter = Counter(
            json.dumps(
                row,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for row in retained_rows
        )
        current_counter = Counter(
            json.dumps(
                row,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for row in current_rows
        )
        if retained_counter - current_counter:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
                "persisted Shadow fixture identity state is not an append-only extension of retained bundle"
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
    snapshot = _identity_state_snapshot()
    object.__setattr__(
        bundle,
        "_fixture_stable_identity_state_sha256",
        _identity_state_sha256(snapshot),
    )
    object.__setattr__(bundle, "_fixture_stable_identity_state_snapshot", snapshot)
    return bundle


def _bind_retained_identity_state(
    bundle: Any,
    *,
    state_sha256: str,
    snapshot: Mapping[str, Any],
) -> Any:
    object.__setattr__(bundle, "_fixture_stable_identity_state_sha256", state_sha256)
    object.__setattr__(
        bundle,
        "_fixture_stable_identity_state_snapshot",
        _copy_identity_state(snapshot),
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
    with _shadow_parser_scope():
        return legacy.capture_current_catalog_fanout_discovery(
            repository_root=repository_root,
            execute_live_network=execute_live_network,
        )


def verify_current_catalog_fanout_discovery(
    evidence_directory: Path, *, repository_root: Path
):
    validate_contract()
    _sync_wrapper_hooks()
    with _shadow_parser_scope():
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
    with _shadow_parser_scope():
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
    with _shadow_parser_scope():
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
    _sync_wrapper_hooks()
    expected_state = getattr(value, "_fixture_stable_identity_state_sha256", None)
    retained_state = None
    if expected_state is not None:
        retained_state = getattr(value, "_fixture_stable_identity_state_snapshot", None)
        if type(retained_state) is not dict:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
                "retained Shadow fixture identity state snapshot is unavailable"
            )
        if _identity_state_sha256(retained_state) != expected_state:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
                "retained Shadow fixture identity state snapshot hash drifted"
            )
        current_state = _identity_state_snapshot()
        _verify_identity_state_append_only_extension(retained_state, current_state)
    with _shadow_parser_scope():
        if expected_state is None:
            return legacy.verify_current_event_discovery_reconciliation_bundle(value)
        with _retained_identity_serialization_scope(expected_state):
            rebuilt = legacy.verify_current_event_discovery_reconciliation_bundle(value)
    return _bind_retained_identity_state(
        rebuilt,
        state_sha256=expected_state,
        snapshot=retained_state,
    )


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
    "TEAM_LABEL_COMPATIBILITY_POLICY_ID",
    "TEAM_LABEL_COMPATIBILITY_POLICY_SHA256",
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
