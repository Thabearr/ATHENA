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
from pathlib import Path
from typing import Any

from domain import current_shadow_fixture_identity_run199_overlay as run199_identity
from domain import current_shadow_fixture_identity_v2 as fixture_identity_v2
from domain import current_shadow_sportybet_team_label_compatibility as team_label_compatibility
from domain import sportybet_current_event_discovery_reconciliation as reviewed_discovery
from scripts import current_shadow_fixture_identity_reconciliation_recovery as identity_recovery


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


def begin_identity_scope(
    fotmob_captures: Sequence[Any],
    discovery_evidence_directory: Path | None = None,
) -> None:
    fixture_identity_v2.reset_runtime_evidence()
    fixture_identity_v2.configure_persistent_state(
        os.environ.get("ATHENA_CURRENT_SHADOW_IDENTITY_STATE_PATH")
    )
    fixture_identity_v2.observe_fotmob_captures(fotmob_captures)
    if discovery_evidence_directory is not None:
        fixture_identity_v2.observe_provider_directory(discovery_evidence_directory)


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
    result = run199_identity.match_event(event, reviewed_rows)
    if result:
        return result
    result_v3 = identity_recovery.match_event(event, reviewed_rows)
    if result_v3:
        return result_v3
    result_v2 = fixture_identity_v2.match_event(event, reviewed_rows)
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


__all__ = [
    "CurrentShadowFixtureIdentityCompatibilityError",
    "begin_identity_scope",
    "identity_state_sha256",
    "identity_state_snapshot",
    "match_current_shadow_event",
    "project_event_labels",
    "verify_identity_state_append_only_extension",
]
