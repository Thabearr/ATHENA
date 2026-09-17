"""P3.0-E1-only diagnostics for conflicting duplicate SportyBet event identities.

This module does not admit, merge, normalize, or otherwise reconcile a conflicting
provider event. It temporarily wraps the reviewed duplicate-event guard so the
existing fail-closed exception carries enough bounded evidence to identify which
identity fields disagreed during a hosted P3.0-E1 capture. The reviewed function
is restored when the scope exits.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Callable

from domain import sportybet_current_event_discovery_reconciliation as reviewed


DIAGNOSTIC_POLICY_ID = (
    "ATHENA_P3_0_E1_CONFLICTING_PROVIDER_EVENT_IDENTITY_DIAGNOSTIC_V1"
)
DIAGNOSTIC_SOURCE_WORKFLOW_RUN_ID = 35255630033
DIAGNOSTIC_SOURCE_ARTIFACT_ID = 10512920633
DIAGNOSTIC_SOURCE_ARTIFACT_SHA256 = (
    "e95b2befcdc7ff4e5ff2fcc20ee15718028119fd37a1a8d63eb4f0df509a9869"
)
DIAGNOSTIC_MESSAGE_MAX_CHARS = 780
_CONFLICT_PREFIX = "conflicting duplicate provider event identity: "
_DIAGNOSTIC_SEPARATOR = "; diagnostic="


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _identity_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(dict(payload)).encode("utf-8")).hexdigest()


def _first_conflict(
    events: Sequence[reviewed.SportyBetDiscoveredEvent],
) -> tuple[
    reviewed.SportyBetDiscoveredEvent,
    reviewed.SportyBetDiscoveredEvent,
] | None:
    by_id: dict[str, reviewed.SportyBetDiscoveredEvent] = {}
    for event in events:
        existing = by_id.get(event.event_id)
        if existing is None:
            by_id[event.event_id] = event
            continue
        if existing.identity_payload != event.identity_payload:
            return existing, event
        if event.source_observed_at > existing.source_observed_at:
            by_id[event.event_id] = event
    return None


def _bounded_diagnostic(
    first: reviewed.SportyBetDiscoveredEvent,
    second: reviewed.SportyBetDiscoveredEvent,
) -> str:
    first_identity = first.identity_payload
    second_identity = second.identity_payload
    keys = sorted(set(first_identity) | set(second_identity))
    differences = {
        key: [first_identity.get(key), second_identity.get(key)]
        for key in keys
        if first_identity.get(key) != second_identity.get(key)
    }
    common = {
        "event_id": second.event_id,
        "differing_fields": sorted(differences),
        "first_identity_sha256": _identity_sha256(first_identity),
        "second_identity_sha256": _identity_sha256(second_identity),
        "first_source_raw_sha256": first.source_raw_sha256,
        "second_source_raw_sha256": second.source_raw_sha256,
        "first_source_observed_at": reviewed.serialize_utc(first.source_observed_at),
        "second_source_observed_at": reviewed.serialize_utc(second.source_observed_at),
    }
    full = {**common, "differences": differences}

    def message(payload: Mapping[str, Any]) -> str:
        return _CONFLICT_PREFIX + second.event_id + _DIAGNOSTIC_SEPARATOR + _canonical_json(payload)

    candidate = message(full)
    if len(candidate) <= DIAGNOSTIC_MESSAGE_MAX_CHARS:
        return candidate

    candidate = message(common)
    if len(candidate) <= DIAGNOSTIC_MESSAGE_MAX_CHARS:
        return candidate

    minimal = {
        "event_id": second.event_id,
        "differing_fields": sorted(differences),
        "first_identity_sha256": common["first_identity_sha256"],
        "second_identity_sha256": common["second_identity_sha256"],
    }
    candidate = message(minimal)
    if len(candidate) > DIAGNOSTIC_MESSAGE_MAX_CHARS:
        raise RuntimeError("P3.0-E1 duplicate-event diagnostic exceeded its message bound")
    return candidate


def _diagnostic_wrapper(
    original: Callable[
        [Sequence[reviewed.SportyBetDiscoveredEvent]],
        tuple[reviewed.SportyBetDiscoveredEvent, ...],
    ],
    events: Sequence[reviewed.SportyBetDiscoveredEvent],
) -> tuple[reviewed.SportyBetDiscoveredEvent, ...]:
    try:
        return original(events)
    except reviewed.SportyBetCurrentEventDiscoveryError as exc:
        if not str(exc).startswith(_CONFLICT_PREFIX):
            raise
        conflict = _first_conflict(events)
        if conflict is None:
            raise
        first, second = conflict
        raise reviewed.SportyBetCurrentEventDiscoveryError(
            _bounded_diagnostic(first, second)
        ) from exc


@contextmanager
def scoped_duplicate_conflict_diagnostic() -> Iterator[None]:
    """Enrich only the hosted P3.0-E1 duplicate-conflict failure and restore exactly."""
    original = reviewed._dedupe_events

    def wrapped(events):
        return _diagnostic_wrapper(original, events)

    reviewed._dedupe_events = wrapped
    try:
        yield
    finally:
        reviewed._dedupe_events = original


__all__ = [
    "DIAGNOSTIC_MESSAGE_MAX_CHARS",
    "DIAGNOSTIC_POLICY_ID",
    "DIAGNOSTIC_SOURCE_ARTIFACT_ID",
    "DIAGNOSTIC_SOURCE_ARTIFACT_SHA256",
    "DIAGNOSTIC_SOURCE_WORKFLOW_RUN_ID",
    "scoped_duplicate_conflict_diagnostic",
]
