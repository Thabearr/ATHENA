"""Source-aware consumption verifier for durable Sportradar metadata evidence.

The ordinary evidence-directory verifier proves storage shape, canonical manifest
bytes, raw-response hash/size, and deterministic directory identity.  That is not
provider-lineage authority by itself.  A downstream consumer must also provide
the exact SportyBet source chain used to rederive PR #160.  This module combines
both checks and then rebuilds the complete metadata evidence from the preserved
raw Sportradar response, requiring canonical byte equality.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from domain import sportradar_user_controlled_event_metadata as metadata
from domain import sportybet_sportradar_event_identity as bridge
from domain import sportybet_user_controlled_evidence as sporty_manual
from domain import sportybet_user_controlled_native_inventory as sporty_native
from domain.sportybet_lite_source_capture import (
    MAX_RESPONSE_BYTES,
    SportyBetLiteCaptureError,
    _read_regular,
)


def revalidate_event_metadata_evidence_directory(
    evidence_directory: Any,
    *,
    allowed_root: Path,
    event_bridge: bridge.SportyBetSportradarEventIdentityBridge,
    sportybet_manifest: sporty_manual.SportyBetUserControlledEvidenceManifest,
    sportybet_inventory: sporty_native.SportyBetUserControlledNativeInventory,
    sportybet_raw_html: bytes,
) -> metadata.SportradarUserControlledEventMetadataEvidence:
    """Require durable storage integrity plus exact source-aware rederivation."""

    stored = metadata.verify_evidence_directory(
        evidence_directory,
        allowed_root=allowed_root,
    )
    directory = Path(evidence_directory)
    try:
        raw_response = _read_regular(
            directory / metadata.RAW_FILENAME,
            maximum=MAX_RESPONSE_BYTES,
            label="Sportradar raw response",
        )
    except SportyBetLiteCaptureError as exc:
        raise metadata.SportradarUserControlledEventMetadataError(str(exc)) from exc

    return metadata.revalidate_event_metadata_evidence(
        stored,
        raw_response,
        event_bridge=event_bridge,
        sportybet_manifest=sportybet_manifest,
        sportybet_inventory=sportybet_inventory,
        sportybet_raw_html=sportybet_raw_html,
    )


__all__ = ["revalidate_event_metadata_evidence_directory"]
