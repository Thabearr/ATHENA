"""Consumption-time verifier for the SportyBet/Sportradar event-ID bridge.

A serialized bridge artifact is never trusted by shape or lineage hashes alone.
Consumers must provide the exact preserved SportyBet source evidence again; this
module deterministically rebuilds the bridge and requires canonical byte equality.
"""

from __future__ import annotations

from typing import Any

from domain import sportybet_sportradar_event_identity as bridge
from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native


def revalidate_sportradar_event_identity_bridge(
    value: Any,
    *,
    manifest: manual.SportyBetUserControlledEvidenceManifest,
    inventory: native.SportyBetUserControlledNativeInventory,
    raw_html: bytes,
) -> bridge.SportyBetSportradarEventIdentityBridge:
    """Rebuild from exact source bytes and require canonical bridge equality."""

    if not isinstance(value, bridge.SportyBetSportradarEventIdentityBridge):
        raise bridge.SportyBetSportradarEventIdentityError("bridge type mismatch")
    rebuilt = bridge.build_sportradar_event_identity_bridge(
        manifest=manifest,
        inventory=inventory,
        raw_html=raw_html,
    )
    if bridge.canonical_bridge_bytes(value) != bridge.canonical_bridge_bytes(rebuilt):
        raise bridge.SportyBetSportradarEventIdentityError(
            "bridge is not the exact deterministic derivative of preserved SportyBet evidence"
        )
    return rebuilt


__all__ = ["revalidate_sportradar_event_identity_bridge"]
