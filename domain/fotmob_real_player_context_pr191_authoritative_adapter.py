"""Source-specific PR193/PR194 adapter into ATHENA's single PR191 authority type.

The generic PR191 array builder cannot represent the frozen PR193 observation
without inventing an ``is_home`` boolean that the source did not expose.  This
adapter therefore consumes PR197's same-raw PR52→PR66 prerequisite proof and
then constructs the *existing* ``ReviewedFotMobTeamStrengthContext`` authority
type.  It does not create a second team-strength authority dialect.
"""

from __future__ import annotations

import hashlib
import types
from typing import Any

from domain.fotmob_real_player_context_authoritative_bridge import (
    RealPlayerContextAuthoritativeBridgeError,
    build_reviewed_real_fotmob_authoritative_team_strength_bridge,
    canonical_reviewed_real_fotmob_authoritative_team_strength_bridge_bytes,
)
from domain.fotmob_real_player_context_team_strength_handoff import (
    EXPECTED_CANDIDATE_SHA256,
    SOURCE_ADMISSION_SIZE,
)
from domain.fotmob_reviewed_team_strength_context_adapter import (
    ADAPTER_SCOPE,
    DATASET_NAME,
    SCHEMA_VERSION,
    ReviewedFotMobTeamStrengthContext,
    ReviewedTeamStrengthContextAdapterError,
    _new_reviewed_context,
    canonical_reviewed_fotmob_team_strength_context_bytes,
)
from domain.fotmob_team_strength_fixture_intelligence import (
    FeatureStatus,
    canonical_team_strength_context_candidate_bytes,
)


SOURCE_SPECIFIC_ADAPTER_ID = "PR193_REAL_ARRAY_OBSERVATION_TO_EXISTING_PR191_AUTHORITY_V1"
_PR191_SAFETY = {
    "bet_authorized": False,
    "pricing_authorized": False,
    "probability_adjustment_authorized": False,
    "probability_inference_authorized": False,
    "production_approval_authorized": False,
    "selection_authorized": False,
    "team_strength_feature_authorized": True,
}
_EXPECTED_AVAILABLE_FEATURES = {
    "away_unavailable_player_count": 5.0,
    "home_unavailable_player_count": 1.0,
}


class RealPlayerContextPR191AdapterError(ValueError):
    """Raised when real player context cannot enter the existing PR191 authority type."""


def _sha(raw: bytes) -> str:
    if type(raw) is not bytes:
        raise RealPlayerContextPR191AdapterError("hash input must be exact bytes")
    return hashlib.sha256(raw).hexdigest()


def build_reviewed_real_fotmob_pr191_team_strength_context(
    *,
    campaign_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
    persisted_receipt_bytes: Any,
    structure_assessment_bytes: Any,
) -> ReviewedFotMobTeamStrengthContext:
    """Return the existing PR191 authority type after exact source-specific replay."""

    try:
        bridge = build_reviewed_real_fotmob_authoritative_team_strength_bridge(
            campaign_receipt_bytes=campaign_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            persisted_receipt_bytes=persisted_receipt_bytes,
            structure_assessment_bytes=structure_assessment_bytes,
        )
        canonical_reviewed_real_fotmob_authoritative_team_strength_bridge_bytes(bridge)
    except RealPlayerContextAuthoritativeBridgeError as exc:
        raise RealPlayerContextPR191AdapterError(
            "PR197 same-raw PR52→PR66 prerequisite proof failed"
        ) from exc

    # The prerequisite bridge is evidence proof only.  It must not itself be a
    # competing feature-authority wrapper.
    if any(dict(bridge.authority).values()):
        raise RealPlayerContextPR191AdapterError(
            "PR197 prerequisite bridge must keep every authority flag false"
        )

    candidate_bytes = canonical_team_strength_context_candidate_bytes(bridge.candidate)
    if _sha(candidate_bytes) != EXPECTED_CANDIDATE_SHA256:
        raise RealPlayerContextPR191AdapterError("exact PR194 candidate identity drift")
    available = {
        item.feature_id.value: item.value
        for item in bridge.candidate.features
        if item.status is FeatureStatus.AVAILABLE
    }
    if available != _EXPECTED_AVAILABLE_FEATURES:
        raise RealPlayerContextPR191AdapterError(
            "real source candidate exceeds exact admitted unavailable-count semantics"
        )

    try:
        context = _new_reviewed_context(
            schema_version=SCHEMA_VERSION,
            dataset_name=DATASET_NAME,
            adapter_scope=ADAPTER_SCOPE,
            source_array_artifact_sha256=bridge.source_pr193_admission_sha256,
            source_array_artifact_size=SOURCE_ADMISSION_SIZE,
            source_raw_sha256=bridge.source_raw_sha256,
            source_pr65_artifact_sha256=bridge.source_pr65_artifact_sha256,
            source_pr65_artifact_size=bridge.source_pr65_artifact_size,
            source_pr66_handoff_sha256=bridge.source_pr66_handoff_sha256,
            source_pr66_handoff_size=bridge.source_pr66_handoff_size,
            source_fixture_intelligence_snapshot_sha256=(
                bridge.source_fixture_intelligence_snapshot_sha256
            ),
            source_model_feature_snapshot_sha256=bridge.source_model_feature_snapshot_sha256,
            fixture_identifier=bridge.fixture_identifier,
            source_match_id=bridge.source_match_id,
            home_team_id=bridge.home_team_id,
            away_team_id=bridge.away_team_id,
            candidate=bridge.candidate,
            candidate_sha256=bridge.candidate_sha256,
            candidate_size=bridge.candidate_size,
            safety=types.MappingProxyType(dict(_PR191_SAFETY)),
        )
        exact = canonical_reviewed_fotmob_team_strength_context_bytes(context)
    except (ReviewedTeamStrengthContextAdapterError, TypeError, ValueError) as exc:
        raise RealPlayerContextPR191AdapterError(
            "existing PR191 authoritative context construction failed"
        ) from exc

    if dict(context.safety) != _PR191_SAFETY:
        raise RealPlayerContextPR191AdapterError("PR191 safety/authority map drift")
    if context.candidate_sha256 != EXPECTED_CANDIDATE_SHA256:
        raise RealPlayerContextPR191AdapterError("PR191 nested candidate identity drift")
    if not exact:
        raise RealPlayerContextPR191AdapterError("PR191 canonical authority bytes are empty")
    return context


def revalidate_reviewed_real_fotmob_pr191_team_strength_context(
    *,
    campaign_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
    persisted_receipt_bytes: Any,
    structure_assessment_bytes: Any,
    context: Any,
    context_bytes: Any,
) -> ReviewedFotMobTeamStrengthContext:
    if type(context) is not ReviewedFotMobTeamStrengthContext or type(context_bytes) is not bytes:
        raise RealPlayerContextPR191AdapterError(
            "context/object bytes must be exact existing PR191 authority values"
        )
    try:
        supplied = canonical_reviewed_fotmob_team_strength_context_bytes(context)
    except ReviewedTeamStrengthContextAdapterError as exc:
        raise RealPlayerContextPR191AdapterError("supplied PR191 context is invalid") from exc
    rebuilt = build_reviewed_real_fotmob_pr191_team_strength_context(
        campaign_receipt_bytes=campaign_receipt_bytes,
        manifest_bytes=manifest_bytes,
        raw_bytes=raw_bytes,
        persisted_receipt_bytes=persisted_receipt_bytes,
        structure_assessment_bytes=structure_assessment_bytes,
    )
    exact = canonical_reviewed_fotmob_team_strength_context_bytes(rebuilt)
    if supplied != exact or context_bytes != exact:
        raise RealPlayerContextPR191AdapterError(
            "PR191 authoritative context differs from exact PR192→PR197 replay"
        )
    return rebuilt


def sha256_reviewed_real_fotmob_pr191_team_strength_context(value: Any) -> str:
    if type(value) is not ReviewedFotMobTeamStrengthContext:
        raise RealPlayerContextPR191AdapterError("value must be existing PR191 authority type")
    return _sha(canonical_reviewed_fotmob_team_strength_context_bytes(value))


__all__ = [
    "RealPlayerContextPR191AdapterError",
    "SOURCE_SPECIFIC_ADAPTER_ID",
    "build_reviewed_real_fotmob_pr191_team_strength_context",
    "revalidate_reviewed_real_fotmob_pr191_team_strength_context",
    "sha256_reviewed_real_fotmob_pr191_team_strength_context",
]
