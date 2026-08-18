"""Consumption-time verifier for SportyBet/FotMob full-UTC reconciliation."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from domain import sportradar_user_controlled_event_metadata as metadata
from domain import sportybet_event_local_time_basis as local_time
from domain import sportybet_fotmob_full_utc_reconciliation as reconciliation
from domain import sportybet_official_time_semantics as terms
from domain import sportybet_sportradar_event_identity as bridge
from domain import sportybet_sportradar_kickoff_identity_promotion as promotion
from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native
from domain.fotmob_fixture_candidate_review import FotMobReviewedFixtureCatalogInput


def revalidate_full_utc_reconciliation(
    value: Any,
    *,
    kickoff_promotion: promotion.SportyBetSportradarKickoffIdentityPromotion,
    event_time_basis: local_time.SportyBetEventLocalTimeBasis,
    event_manifest: manual.SportyBetUserControlledEvidenceManifest,
    event_inventory: native.SportyBetUserControlledNativeInventory,
    event_raw_html: bytes,
    terms_qualification: terms.SportyBetOfficialTimeSemanticsQualification,
    terms_raw_html: bytes,
    event_bridge: bridge.SportyBetSportradarEventIdentityBridge,
    sportradar_evidence: metadata.SportradarUserControlledEventMetadataEvidence,
    sportradar_raw_response: bytes,
    fixtures: Iterable[FotMobReviewedFixtureCatalogInput],
) -> reconciliation.SportyBetFotMobFullUtcReconciliation:
    """Rebuild from exact preserved sources/population and require canonical equality."""

    if not isinstance(value, reconciliation.SportyBetFotMobFullUtcReconciliation):
        raise reconciliation.SportyBetFotMobFullUtcReconciliationError(
            "reconciliation type mismatch"
        )
    fixture_rows = tuple(fixtures)
    rebuilt = reconciliation.build_full_utc_reconciliation(
        kickoff_promotion=kickoff_promotion,
        event_time_basis=event_time_basis,
        event_manifest=event_manifest,
        event_inventory=event_inventory,
        event_raw_html=event_raw_html,
        terms_qualification=terms_qualification,
        terms_raw_html=terms_raw_html,
        event_bridge=event_bridge,
        sportradar_evidence=sportradar_evidence,
        sportradar_raw_response=sportradar_raw_response,
        fixtures=fixture_rows,
    )
    if reconciliation.canonical_reconciliation_bytes(
        value
    ) != reconciliation.canonical_reconciliation_bytes(rebuilt):
        raise reconciliation.SportyBetFotMobFullUtcReconciliationError(
            "full-UTC reconciliation is not the exact deterministic derivative of preserved sources and FotMob population"
        )
    return rebuilt


__all__ = ["revalidate_full_utc_reconciliation"]
