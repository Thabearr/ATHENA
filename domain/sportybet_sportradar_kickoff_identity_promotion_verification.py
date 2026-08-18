"""Consumption-time revalidator for SportyBet/Sportradar kickoff identity promotion."""

from __future__ import annotations

from typing import Any

from domain import sportradar_user_controlled_event_metadata as metadata
from domain import sportybet_event_local_time_basis as local_time
from domain import sportybet_official_time_semantics as terms
from domain import sportybet_sportradar_event_identity as bridge
from domain import sportybet_sportradar_kickoff_identity_promotion as promotion
from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native


def revalidate_kickoff_identity_promotion(
    value: Any,
    *,
    event_time_basis: local_time.SportyBetEventLocalTimeBasis,
    event_manifest: manual.SportyBetUserControlledEvidenceManifest,
    event_inventory: native.SportyBetUserControlledNativeInventory,
    event_raw_html: bytes,
    terms_qualification: terms.SportyBetOfficialTimeSemanticsQualification,
    terms_raw_html: bytes,
    event_bridge: bridge.SportyBetSportradarEventIdentityBridge,
    sportradar_evidence: metadata.SportradarUserControlledEventMetadataEvidence,
    sportradar_raw_response: bytes,
) -> promotion.SportyBetSportradarKickoffIdentityPromotion:
    """Rebuild from every preserved source and require canonical byte equality."""

    if not isinstance(value, promotion.SportyBetSportradarKickoffIdentityPromotion):
        raise promotion.SportyBetSportradarKickoffIdentityPromotionError(
            "promotion type mismatch"
        )
    rebuilt = promotion.build_kickoff_identity_promotion(
        event_time_basis=event_time_basis,
        event_manifest=event_manifest,
        event_inventory=event_inventory,
        event_raw_html=event_raw_html,
        terms_qualification=terms_qualification,
        terms_raw_html=terms_raw_html,
        event_bridge=event_bridge,
        sportradar_evidence=sportradar_evidence,
        sportradar_raw_response=sportradar_raw_response,
    )
    if promotion.canonical_promotion_bytes(value) != promotion.canonical_promotion_bytes(
        rebuilt
    ):
        raise promotion.SportyBetSportradarKickoffIdentityPromotionError(
            "kickoff identity promotion is not the exact deterministic derivative of preserved sources"
        )
    return rebuilt


__all__ = ["revalidate_kickoff_identity_promotion"]
