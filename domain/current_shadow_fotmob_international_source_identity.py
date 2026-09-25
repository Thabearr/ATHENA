"""Evidence-qualified current FotMob identities for ATHENA's international hierarchy.

This is a source-identity bridge only.  It resolves exact source-scoped FotMob
``(ccode, primaryId)`` keys into the existing international competition
hierarchy; it does not qualify history, models, pricing, selection, or betting.
Display names and season/group wrapper IDs are retained only as evidence metadata.
"""
from __future__ import annotations

import dataclasses
from enum import Enum
import hashlib
import json
from typing import Any

from config.competition_review_priority import (
    CompetitionKind,
    CompetitionReviewPriorityEntry,
    CompetitionScope,
    INTERNATIONAL_COMPETITION_REVIEW_PRIORITY,
    resolve_canonical_competition_review_priority,
)


POLICY_ID = "ATHENA_CURRENT_SHADOW_FOTMOB_INTERNATIONAL_SOURCE_HIERARCHY_V1"
POLICY_SCHEMA_VERSION = 1

P4_4K_WORKFLOW_RUN_ID = 36136878384
P4_4K_EXACT_MAIN_SHA = "b17e97dbea043d45d47db9ad2011354fe4682baf"
P4_4K_ARTIFACT_ID = 10865656841
P4_4K_ARTIFACT_SHA256 = (
    "3d8733e2bd9ed1ad4eef94b877e22603e1043fa5a658801548223b5c298c48b8"
)
P4_4K_CAPTURE_MANIFEST_SHA256 = (
    "759eb16f0daac610efdc9d9532bd7d8348b153c35c11a041b772f2fc83ec1670"
)
P4_4K_CAPTURE_RAW_SHA256 = (
    "9246263b90f1b997fce87a2cff4d4918d06cc2e446055c3f80b7eef4bbfe6210"
)
P4_4K_REQUEST_DATE = "20260925"
P4_4K_CAPTURE_OBSERVED_AT = "2026-09-25T12:47:40.911642Z"


class InternationalSourceCoverageState(str, Enum):
    QUALIFIED_CURRENT_SOURCE_IDENTITY = "QUALIFIED_CURRENT_SOURCE_IDENTITY"
    NO_REVIEWED_CURRENT_SOURCE_IDENTITY_EVIDENCE = (
        "NO_REVIEWED_CURRENT_SOURCE_IDENTITY_EVIDENCE"
    )
    OBSERVED_IDENTITY_NOT_HIERARCHY_QUALIFIED = (
        "OBSERVED_IDENTITY_NOT_HIERARCHY_QUALIFIED"
    )


@dataclasses.dataclass(frozen=True)
class ReviewedCurrentFotMobInternationalSourceIdentity:
    source_competition_ccode: str
    source_competition_primary_id: int
    canonical_name: str
    priority_band: str
    priority_rank: int
    competition_kind: CompetitionKind
    observed_source_labels: tuple[str, ...]
    class_evidence: str
    workflow_run_id: int = P4_4K_WORKFLOW_RUN_ID
    artifact_id: int = P4_4K_ARTIFACT_ID
    artifact_sha256: str = P4_4K_ARTIFACT_SHA256
    capture_manifest_sha256: str = P4_4K_CAPTURE_MANIFEST_SHA256
    capture_raw_sha256: str = P4_4K_CAPTURE_RAW_SHA256

    @property
    def key(self) -> tuple[str, int]:
        return (
            self.source_competition_ccode,
            self.source_competition_primary_id,
        )


@dataclasses.dataclass(frozen=True)
class ObservedUnqualifiedInternationalSourceIdentity:
    source_competition_ccode: str
    source_competition_primary_id: int
    observed_source_labels: tuple[str, ...]
    reason: str
    workflow_run_id: int = P4_4K_WORKFLOW_RUN_ID
    artifact_id: int = P4_4K_ARTIFACT_ID
    artifact_sha256: str = P4_4K_ARTIFACT_SHA256

    @property
    def key(self) -> tuple[str, int]:
        return (
            self.source_competition_ccode,
            self.source_competition_primary_id,
        )


@dataclasses.dataclass(frozen=True)
class InternationalHierarchyCoverage:
    canonical_name: str
    scope: CompetitionScope
    priority_band: str
    priority_rank: int
    competition_kind: CompetitionKind
    coverage_state: InternationalSourceCoverageState
    active_source_identities: tuple[
        ReviewedCurrentFotMobInternationalSourceIdentity, ...
    ]
    observed_unqualified_source_identities: tuple[
        ObservedUnqualifiedInternationalSourceIdentity, ...
    ]


# These keys are explicitly reviewed against the immutable P4.4K capture.  The
# final three mappings use direct age-grade fixture metadata from that exact
# capture as class evidence; no runtime name/participant matching is performed.
REVIEWED_CURRENT_SOURCE_IDENTITIES: tuple[
    ReviewedCurrentFotMobInternationalSourceIdentity, ...
] = (
    ReviewedCurrentFotMobInternationalSourceIdentity(
        "INT", 9806, "Nations League", "INT-D", 40,
        CompetitionKind.INTERNATIONAL_NATIONS_LEAGUE,
        ("UEFA Nations League A Grp. 1",),
        "P4.4K exact primaryId and ccode; observed UEFA Nations League A group wrapper.",
    ),
    ReviewedCurrentFotMobInternationalSourceIdentity(
        "INT", 9807, "Nations League", "INT-D", 40,
        CompetitionKind.INTERNATIONAL_NATIONS_LEAGUE,
        ("UEFA Nations League B Grp. 2", "UEFA Nations League B Grp. 4"),
        "P4.4K exact primaryId and ccode; observed UEFA Nations League B group wrappers.",
    ),
    ReviewedCurrentFotMobInternationalSourceIdentity(
        "INT", 9808, "Nations League", "INT-D", 40,
        CompetitionKind.INTERNATIONAL_NATIONS_LEAGUE,
        ("UEFA Nations League C Grp. 2",),
        "P4.4K exact primaryId and ccode; observed UEFA Nations League C group wrapper.",
    ),
    ReviewedCurrentFotMobInternationalSourceIdentity(
        "INT", 9821, "Nations League", "INT-D", 40,
        CompetitionKind.INTERNATIONAL_NATIONS_LEAGUE,
        (
            "CONCACAF Nations League A Grp. 1",
            "CONCACAF Nations League B Grp. 1",
            "CONCACAF Nations League B Grp. 2",
            "CONCACAF Nations League B Grp. 3",
        ),
        "P4.4K exact primaryId and ccode; observed CONCACAF Nations League group wrappers.",
    ),
    ReviewedCurrentFotMobInternationalSourceIdentity(
        "INT", 10608, "Continental Championship Qualification", "INT-C", 30,
        CompetitionKind.INTERNATIONAL_QUALIFIER,
        tuple(
            f"Africa Cup of Nations Qualification Grp. {group}"
            for group in ("A", "B", "C", "F", "I", "J", "K", "L")
        ),
        "P4.4K exact primaryId and ccode; observed AFCON qualification groups.",
    ),
    ReviewedCurrentFotMobInternationalSourceIdentity(
        "INT", 114, "International Friendly", "INT-F", 60,
        CompetitionKind.INTERNATIONAL_FRIENDLY,
        ("Friendlies",),
        "P4.4K exact primaryId and ccode; observed the current international friendly family.",
    ),
    ReviewedCurrentFotMobInternationalSourceIdentity(
        "INT", 10437, "Youth / Olympic International", "INT-G", 70,
        CompetitionKind.INTERNATIONAL_YOUTH,
        (
            "EURO U21 Qualification Grp. A",
            "EURO U21 Qualification Grp. B",
            "EURO U21 Qualification Grp. C",
            "EURO U21 Qualification Grp. D",
            "EURO U21 Qualification Grp. G",
        ),
        "P4.4K exact primaryId/ccode plus U21 fixture-team metadata; current source class only.",
    ),
    ReviewedCurrentFotMobInternationalSourceIdentity(
        "INT", 9833, "Youth / Olympic International", "INT-G", 70,
        CompetitionKind.INTERNATIONAL_YOUTH,
        ("Asian Games",),
        "P4.4K exact primaryId/ccode plus U23 fixture-team metadata; current source class only.",
    ),
)

OBSERVED_UNQUALIFIED_SOURCE_IDENTITIES: tuple[
    ObservedUnqualifiedInternationalSourceIdentity, ...
] = (
    ObservedUnqualifiedInternationalSourceIdentity(
        "INT", 13287,
        ("FIFA ASEAN Cup Premier Division Grp. A",),
        "P4.4K observes the exact source identity, but the capture does not independently establish its INT-E official-secondary-senior class.",
    ),
)


def _entry_for(canonical_name: str) -> CompetitionReviewPriorityEntry:
    entry = resolve_canonical_competition_review_priority(
        canonical_name, scope=CompetitionScope.INTERNATIONAL
    )
    if entry is None or entry.scope is not CompetitionScope.INTERNATIONAL:
        raise RuntimeError(f"missing canonical international hierarchy entry: {canonical_name}")
    return entry


def _assert_mapping_targets() -> None:
    seen: set[tuple[str, int]] = set()
    for identity in REVIEWED_CURRENT_SOURCE_IDENTITIES:
        if identity.key in seen:
            raise RuntimeError(f"duplicate international FotMob source identity: {identity.key!r}")
        seen.add(identity.key)
        entry = _entry_for(identity.canonical_name)
        if (
            entry.priority_band != identity.priority_band
            or entry.rank != identity.priority_rank
            or entry.kind is not identity.competition_kind
        ):
            raise RuntimeError(
                f"international identity hierarchy target drift: {identity.key!r}"
            )
    for observation in OBSERVED_UNQUALIFIED_SOURCE_IDENTITIES:
        if observation.key in seen:
            raise RuntimeError(f"qualified/unqualified source identity collision: {observation.key!r}")
        seen.add(observation.key)


_assert_mapping_targets()
_IDENTITY_BY_KEY = {
    identity.key: identity for identity in REVIEWED_CURRENT_SOURCE_IDENTITIES
}
_OBSERVED_UNQUALIFIED_BY_KEY = {
    item.key: item for item in OBSERVED_UNQUALIFIED_SOURCE_IDENTITIES
}


def international_hierarchy_coverage_table() -> tuple[InternationalHierarchyCoverage, ...]:
    """Return every canonical international hierarchy entry with explicit coverage."""

    rows: list[InternationalHierarchyCoverage] = []
    for entry in INTERNATIONAL_COMPETITION_REVIEW_PRIORITY:
        active = tuple(
            item
            for item in REVIEWED_CURRENT_SOURCE_IDENTITIES
            if item.canonical_name == entry.canonical_name
        )
        if active:
            state = InternationalSourceCoverageState.QUALIFIED_CURRENT_SOURCE_IDENTITY
        else:
            state = InternationalSourceCoverageState.NO_REVIEWED_CURRENT_SOURCE_IDENTITY_EVIDENCE
        rows.append(
            InternationalHierarchyCoverage(
                canonical_name=entry.canonical_name,
                scope=entry.scope,
                priority_band=entry.priority_band,
                priority_rank=entry.rank,
                competition_kind=entry.kind,
                coverage_state=state,
                active_source_identities=active,
                observed_unqualified_source_identities=(),
            )
        )
    return tuple(rows)


def resolve_current_shadow_international_source_priority(
    *,
    source_competition_ccode: Any,
    source_competition_primary_id: Any,
) -> CompetitionReviewPriorityEntry | None:
    """Resolve an exact, qualified current FotMob international source identity."""

    if type(source_competition_ccode) is not str or source_competition_ccode != "INT":
        return None
    if type(source_competition_primary_id) is not int:
        return None
    identity = _IDENTITY_BY_KEY.get(
        (source_competition_ccode, source_competition_primary_id)
    )
    if identity is None:
        return None
    entry = resolve_canonical_competition_review_priority(
        identity.canonical_name, scope=CompetitionScope.INTERNATIONAL
    )
    if entry is None or (
        entry.scope is not CompetitionScope.INTERNATIONAL
        or entry.canonical_name != identity.canonical_name
        or entry.priority_band != identity.priority_band
        or entry.rank != identity.priority_rank
        or entry.kind is not identity.competition_kind
    ):
        return None
    return entry


def reviewed_current_fotmob_international_source_identity(
    *,
    source_competition_ccode: Any,
    source_competition_primary_id: Any,
) -> ReviewedCurrentFotMobInternationalSourceIdentity | None:
    """Return reviewed identity evidence for the exact key, never by label."""

    if type(source_competition_ccode) is not str or source_competition_ccode != "INT":
        return None
    if type(source_competition_primary_id) is not int:
        return None
    return _IDENTITY_BY_KEY.get((source_competition_ccode, source_competition_primary_id))


def observed_unqualified_current_fotmob_international_source_identity(
    *,
    source_competition_ccode: Any,
    source_competition_primary_id: Any,
) -> ObservedUnqualifiedInternationalSourceIdentity | None:
    """Return an exact observed-but-unqualified key, never by display name."""

    if type(source_competition_ccode) is not str or source_competition_ccode != "INT":
        return None
    if type(source_competition_primary_id) is not int:
        return None
    return _OBSERVED_UNQUALIFIED_BY_KEY.get(
        (source_competition_ccode, source_competition_primary_id)
    )


def international_source_identity_policy_payload() -> dict[str, Any]:
    """Build the deterministic, evidence-backed identity policy payload."""

    coverage = []
    for row in international_hierarchy_coverage_table():
        coverage.append(
            {
                "canonical_name": row.canonical_name,
                "scope": row.scope.value,
                "priority_band": row.priority_band,
                "priority_rank": row.priority_rank,
                "competition_kind": row.competition_kind.value,
                "coverage_state": row.coverage_state.value,
                "active_source_identities": [
                    {
                        "ccode": item.source_competition_ccode,
                        "primary_id": item.source_competition_primary_id,
                        "observed_source_labels": list(item.observed_source_labels),
                        "class_evidence": item.class_evidence,
                        "evidence": {
                            "workflow_run_id": item.workflow_run_id,
                            "artifact_id": item.artifact_id,
                            "artifact_sha256": item.artifact_sha256,
                            "capture_manifest_sha256": item.capture_manifest_sha256,
                            "capture_raw_sha256": item.capture_raw_sha256,
                        },
                    }
                    for item in row.active_source_identities
                ],
                "observed_unqualified_source_identities": [
                    {
                        "ccode": item.source_competition_ccode,
                        "primary_id": item.source_competition_primary_id,
                        "observed_source_labels": list(item.observed_source_labels),
                        "reason": item.reason,
                        "state": InternationalSourceCoverageState.OBSERVED_IDENTITY_NOT_HIERARCHY_QUALIFIED.value,
                        "evidence": {
                            "workflow_run_id": item.workflow_run_id,
                            "artifact_id": item.artifact_id,
                            "artifact_sha256": item.artifact_sha256,
                        },
                    }
                    for item in row.observed_unqualified_source_identities
                ],
            }
        )
    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "identity_semantics": "EXACT_FOTMOB_SOURCE_SCOPED_CCODE_AND_PRIMARY_ID",
        "cross_path_identity_conflict_rule": (
            "FAIL_CLOSED_WHEN_KNOWN_P4_4L_PRIMARY_ID_CONFLICTS_WITH_EXISTING_SOURCE_NAME_RESOLUTION"
        ),
        "unknown_primary_id_preserves_existing_reviewed_source_name_path": True,
        "observed_unqualified_primary_id_cannot_be_reclassified_by_source_name": True,
        "p4_4k_evidence": {
            "workflow_run_id": P4_4K_WORKFLOW_RUN_ID,
            "exact_main_sha": P4_4K_EXACT_MAIN_SHA,
            "artifact_id": P4_4K_ARTIFACT_ID,
            "artifact_sha256": P4_4K_ARTIFACT_SHA256,
            "capture_manifest_sha256": P4_4K_CAPTURE_MANIFEST_SHA256,
            "capture_raw_sha256": P4_4K_CAPTURE_RAW_SHA256,
            "request_date": P4_4K_REQUEST_DATE,
            "capture_observed_at": P4_4K_CAPTURE_OBSERVED_AT,
            "capture_timezone": "UTC",
            "capture_ccode3": "NGA",
            "http_status": 200,
            "network_acquisition_performed_in_prior_evidence": True,
        },
        "coverage": coverage,
        "observed_unqualified_identities": [
            {
                "ccode": item.source_competition_ccode,
                "primary_id": item.source_competition_primary_id,
                "observed_source_labels": list(item.observed_source_labels),
                "reason": item.reason,
            }
            for item in OBSERVED_UNQUALIFIED_SOURCE_IDENTITIES
        ],
        "authority": {
            "display_name_identity_authority": False,
            "league_wrapper_identity_authority": False,
            "historical_international_mapping_qualified": False,
            "production_source_authority": False,
            "model_authority": False,
            "pricing_authority": False,
            "router_authority": False,
            "portfolio_authority": False,
            "selection_authority": False,
            "sportybet_execution_authority": False,
            "bet_authority": False,
            "wager_placed": False,
        },
    }


def canonical_international_source_identity_policy_bytes() -> bytes:
    return (
        json.dumps(
            international_source_identity_policy_payload(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def international_source_identity_policy_sha256() -> str:
    return hashlib.sha256(canonical_international_source_identity_policy_bytes()).hexdigest()


PINNED_POLICY_SHA256 = "f4a50b836540d4dd797631f50215598d852aab05a9c2e9a65ff8069afcde570b"


__all__ = [
    "InternationalHierarchyCoverage",
    "InternationalSourceCoverageState",
    "OBSERVED_UNQUALIFIED_SOURCE_IDENTITIES",
    "P4_4K_ARTIFACT_ID",
    "P4_4K_ARTIFACT_SHA256",
    "P4_4K_CAPTURE_MANIFEST_SHA256",
    "P4_4K_CAPTURE_OBSERVED_AT",
    "P4_4K_CAPTURE_RAW_SHA256",
    "P4_4K_EXACT_MAIN_SHA",
    "P4_4K_REQUEST_DATE",
    "P4_4K_WORKFLOW_RUN_ID",
    "PINNED_POLICY_SHA256",
    "POLICY_ID",
    "REVIEWED_CURRENT_SOURCE_IDENTITIES",
    "international_hierarchy_coverage_table",
    "international_source_identity_policy_payload",
    "international_source_identity_policy_sha256",
    "observed_unqualified_current_fotmob_international_source_identity",
    "resolve_current_shadow_international_source_priority",
    "reviewed_current_fotmob_international_source_identity",
]
