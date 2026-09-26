"""Source-agnostic Current Shadow fixture identity compatibility.

This module owns the reviewed identity/state stack shared by the active
upcoming discovery source and the retained paginated source replay.  It has no
provider acquisition or source-selection authority.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import timezone
import hashlib
import json
import os
from typing import Any

from domain import current_shadow_fixture_identity_aliases as alias_registry
from domain import current_shadow_fixture_identity_run199_overlay as run199_identity
from domain import current_shadow_fixture_identity_v2 as fixture_identity_v2
from domain import current_shadow_sportybet_team_label_compatibility as team_label_compatibility
from domain import sportybet_current_event_discovery_reconciliation as reviewed_discovery
from scripts import current_shadow_fixture_identity_reconciliation_recovery as identity_recovery


POLICY_ID = "ATHENA_CURRENT_SHADOW_FIXTURE_IDENTITY_COMPATIBILITY_V1"
STATUS = "CURRENT_SHADOW_SOURCE_AGNOSTIC_IDENTITY_COMPATIBILITY_VERIFIED"
PROVIDER_EVIDENCE_OBSERVATION_POLICY_ID = "VERIFIED_PROVIDER_RAW_BYTES_PLUS_RAW_ANCESTRY_BOUND_ATHENA_PCUPCOMING_PROJECTION_V2"
STATE_SCHEMA_VERSION = fixture_identity_v2.STATE_SCHEMA_VERSION
EXPECTED_POLICY_SHA256 = "dbef6539dd7c5d1c1589debe8daca9378ea2e0c0bb32acf3315a0d1a005c2b58"
_AUTHORITY = {
    "provider_evidence_observation": True,
    "fixture_identity_reconciliation": True,
    "provider_acquisition": False,
    "pricing": False,
    "market_router": False,
    "portfolio": False,
    "login": False,
    "cookies": False,
    "wallet": False,
    "staking": False,
    "bet": False,
    "wager_placed": False,
}


class CurrentShadowFixtureIdentityCompatibilityError(ValueError):
    """The reviewed source-agnostic Current Shadow identity stack failed closed."""


_IDENTITY_STATE_PAYLOAD_KEYS = frozenset({
    "schema_version",
    "policy_id",
    "matching_basis",
    "seed_registry_sha256",
    "alias_registry_ancestry",
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
    "alias_registry_ancestry",
    "learned_team_identities",
    "learned_competition_identities",
    "evidence_records",
)


def _copy_identity_state(state: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(
        dict(state),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ))


def identity_state_snapshot() -> dict[str, Any]:
    payload = fixture_identity_v2._state_payload()
    return _copy_identity_state(payload)


def identity_state_sha256(snapshot: Mapping[str, Any]) -> str:
    raw = (json.dumps(
        _copy_identity_state(snapshot),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def verify_identity_state_append_only_extension(
    retained_state: Mapping[str, Any],
    current_state: Mapping[str, Any],
) -> None:
    if (
        set(retained_state) != _IDENTITY_STATE_PAYLOAD_KEYS
        or set(current_state) != _IDENTITY_STATE_PAYLOAD_KEYS
    ):
        raise CurrentShadowFixtureIdentityCompatibilityError(
            "persisted Shadow fixture identity state payload shape drifted"
        )
    for key in _IDENTITY_STATE_IMMUTABLE_KEYS:
        if retained_state[key] != current_state[key]:
            raise CurrentShadowFixtureIdentityCompatibilityError(
                "persisted Shadow fixture identity changed retained policy ancestry"
            )
    for key in _IDENTITY_STATE_APPEND_ONLY_KEYS:
        retained_rows = retained_state.get(key, [])
        current_rows = current_state.get(key, [])
        if len(current_rows) < len(retained_rows):
            raise CurrentShadowFixtureIdentityCompatibilityError(
                f"persisted Shadow fixture identity state shrunk for {key}"
            )
        retained_counter = Counter(
            json.dumps(row, sort_keys=True, separators=(",", ":"))
            for row in retained_rows
        )
        current_counter = Counter(
            json.dumps(row, sort_keys=True, separators=(",", ":"))
            for row in current_rows
        )
        if retained_counter - current_counter:
            raise CurrentShadowFixtureIdentityCompatibilityError(
                f"persisted Shadow fixture identity state is not an append-only extension of retained {key}"
            )


def _policy_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "status": STATUS,
        "match_order": [
            "RUN199_EXACT_FIXTURE_IDENTITY_OVERLAY",
            "V3_IDENTITY_RECOVERY",
            "V2_STABLE_IDENTITY",
            "REVIEWED_LITERAL_MATCH",
        ],
        "international_bridge_preemption": {
            "trigger": "EXACT_REVIEWED_PROVIDER_FAMILY_OR_REVIEWED_SOURCE_CONFLICT",
            "match_order": [
                "V2_STABLE_IDENTITY_WITH_INTERNATIONAL_PROVIDER_FAMILY_BRIDGE",
                "FAIL_CLOSED_NO_RUN199_V3_ALIAS_LITERAL_FALLTHROUGH",
            ],
            "bridge_policy_id": fixture_identity_v2.international_bridge.POLICY_ID,
            "bridge_policy_sha256": fixture_identity_v2.international_bridge.PINNED_POLICY_SHA256,
        },
        "provider_evidence_observation": {
            "provider_raw_bytes_required": True,
            "athena_projection_requires_exact_observed_provider_page_raw_sha256": True,
            "athena_projection_is_provider_response": False,
            "provider_payload_ancestry": "EXACT_PROVIDER_SOURCE_PAGE_RAW_SHA256",
            "projection_sha_is_separate_evidence": True,
        },
        "team_label_policy_id": team_label_compatibility.POLICY_ID,
        "team_label_policy_sha256": team_label_compatibility.EXPECTED_POLICY_SHA256,
        "alias_v3_policy_id": alias_registry.POLICY_ID,
        "alias_v3_registry_sha256": alias_registry.REGISTRY_SHA256,
        "stable_identity_policy_id": fixture_identity_v2.POLICY_ID,
        "stable_identity_registry_sha256": fixture_identity_v2.REGISTRY_SHA256,
        "run199_policy_id": run199_identity.POLICY_ID,
        "run199_policy_sha256": run199_identity.POLICY_SHA256,
        "v3_recovery_policy_id": identity_recovery.POLICY_ID,
        "v3_recovery_matching_basis": identity_recovery.MATCHING_BASIS,
        "provider_evidence_observation_policy_id": PROVIDER_EVIDENCE_OBSERVATION_POLICY_ID,
        "provider_match_evidence_persistence": "EXACTLY_ONE_MATCH_ONLY",
        "persisted_state_schema_version": STATE_SCHEMA_VERSION,
        "authority": dict(_AUTHORITY),
    }


def calculate_policy_sha256() -> str:
    raw = json.dumps(
        _policy_payload(),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_contract() -> Mapping[str, str]:
    if STATE_SCHEMA_VERSION != 2:
        raise CurrentShadowFixtureIdentityCompatibilityError(
            "persisted identity state schema drifted"
        )
    if EXPECTED_POLICY_SHA256 == "__PENDING__":
        raise CurrentShadowFixtureIdentityCompatibilityError(
            "identity compatibility policy SHA is not pinned"
        )
    actual = calculate_policy_sha256()
    if actual != EXPECTED_POLICY_SHA256:
        raise CurrentShadowFixtureIdentityCompatibilityError(
            "identity compatibility policy SHA drifted"
        )
    return {
        "policy_id": POLICY_ID,
        "policy_sha256": actual,
        "provider_evidence_observation_policy_id": PROVIDER_EVIDENCE_OBSERVATION_POLICY_ID,
        "state_schema_version": str(STATE_SCHEMA_VERSION),
    }


def begin_identity_scope(
    fotmob_captures: Sequence[Any],
    *,
    provider_raw_bytes: Sequence[bytes] = (),
    historical_page_raw_bytes: Sequence[bytes] = (),
    provider_identity_projection_bytes: Sequence[bytes] = (),
) -> None:
    fixture_identity_v2.reset_runtime_evidence()
    fixture_identity_v2.configure_persistent_state(
        os.environ.get("ATHENA_CURRENT_SHADOW_IDENTITY_STATE_PATH")
    )
    fixture_identity_v2.observe_fotmob_captures(fotmob_captures)
    for raw in tuple(provider_raw_bytes) + tuple(historical_page_raw_bytes):
        if type(raw) is not bytes or not raw:
            raise CurrentShadowFixtureIdentityCompatibilityError(
                "verified provider evidence must be non-empty raw bytes"
            )
        fixture_identity_v2.observe_provider_payload(raw)
    for projection in tuple(provider_identity_projection_bytes):
        if type(projection) is not bytes or not projection:
            raise CurrentShadowFixtureIdentityCompatibilityError(
                "provider identity projection must be non-empty exact bytes"
            )
        try:
            fixture_identity_v2.observe_provider_identity_projection(projection)
        except fixture_identity_v2.CurrentShadowFixtureIdentityStateError as exc:
            raise CurrentShadowFixtureIdentityCompatibilityError(str(exc)) from exc


def project_event_labels(event: reviewed_discovery.SportyBetDiscoveredEvent) -> Any:
    """Apply the reviewed team-label projection without changing fixture identity."""
    try:
        projected_home = team_label_compatibility.project_team_label(
            event_id=event.event_id,
            field="homeTeamName",
            value=event.home_team_name,
        )
        projected_away = team_label_compatibility.project_team_label(
            event_id=event.event_id,
            field="awayTeamName",
            value=event.away_team_name,
        )
    except team_label_compatibility.CurrentShadowSportyBetTeamLabelCompatibilityError as exc:
        raise CurrentShadowFixtureIdentityCompatibilityError(str(exc)) from exc
    if projected_home == event.home_team_name and projected_away == event.away_team_name:
        return event
    return reviewed_discovery.SportyBetDiscoveredEvent(
        event_id=event.event_id,
        home_team_name=projected_home,
        away_team_name=projected_away,
        competition_name=event.competition_name,
        competition_basis=event.competition_basis,
        kickoff_utc=event.kickoff_utc,
        booking_status=event.booking_status,
        event_status=event.event_status,
        match_status=event.match_status,
        prematch_bookable_observed=event.prematch_bookable_observed,
        source_page_num=event.source_page_num,
        source_raw_sha256=event.source_raw_sha256,
        source_observed_at=event.source_observed_at,
    )


def match_current_shadow_event(
    event: reviewed_discovery.SportyBetDiscoveredEvent,
    reviewed_rows: Sequence[Any],
) -> tuple[Any, ...]:
    """Match with the reviewed V3 -> V2 -> alias -> literal identity order."""
    if fixture_identity_v2.provider_event_requires_international_family_bridge(
        getattr(event, "event_id", None), reviewed_rows
    ):
        result_v2 = fixture_identity_v2.match_event(event, reviewed_rows)
        if len(result_v2) == 1:
            _record_observed_provider_match(event, result_v2)
        # A bridge-owned provider identity never falls through to run199, V3,
        # aliases, or literal display-name matching, whether it matches zero,
        # one, or multiple reviewed source fixtures.
        return result_v2
    result = run199_identity.match_event(event, reviewed_rows)
    if len(result) == 1:
        _record_observed_provider_match(event, result)
    if result:
        return result
    result_v3 = identity_recovery.match_event(event, reviewed_rows)
    if len(result_v3) == 1:
        _record_observed_provider_match(event, result_v3)
    if result_v3:
        return result_v3
    result_v2 = fixture_identity_v2.match_event(event, reviewed_rows)
    if len(result_v2) == 1:
        _record_observed_provider_match(event, result_v2)
    if result_v2:
        return result_v2
    if event.competition_name is None:
        return ()
    return tuple(
        item
        for item in reviewed_rows
        if item.home_team == event.home_team_name
        and item.away_team == event.away_team_name
        and item.competition == event.competition_name
        and item.kickoff.astimezone(timezone.utc) == event.kickoff_utc
    )


def _record_observed_provider_match(event: Any, result: Sequence[Any]) -> None:
    """Retain exact provider/source evidence for every successful stable match."""
    event_id = getattr(event, "event_id", None)
    if type(event_id) is not str or len(result) != 1:
        return
    provider = fixture_identity_v2._provider.get(event_id)
    source_id = str(getattr(result[0], "source_fixture_identifier", ""))
    source = fixture_identity_v2._fotmob.get(source_id)
    if provider is None or source is None:
        return
    evidence = fixture_identity_v2._new_evidence_record(
        source_fixture_identifier=source_id,
        provider_event_id=event_id,
        source=source,
        provider=provider,
    )
    if evidence not in fixture_identity_v2._evidence_records:
        fixture_identity_v2._evidence_records.append(evidence)
        fixture_identity_v2._persist_state()


__all__ = [
    "CurrentShadowFixtureIdentityCompatibilityError",
    "EXPECTED_POLICY_SHA256",
    "POLICY_ID",
    "PROVIDER_EVIDENCE_OBSERVATION_POLICY_ID",
    "STATE_SCHEMA_VERSION",
    "begin_identity_scope",
    "calculate_policy_sha256",
    "identity_state_sha256",
    "identity_state_snapshot",
    "match_current_shadow_event",
    "project_event_labels",
    "_record_observed_provider_match",
    "validate_contract",
    "verify_identity_state_append_only_extension",
]
