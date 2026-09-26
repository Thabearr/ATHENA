"""Exact, evidence-bound SportyBet family mappings for senior internationals.

This bridge is orthogonal to the V2 one-to-one club/general seed registry.
It permits only the reviewed international source keys and exact provider
category/tournament identities listed below. It grants no runtime discovery,
model, pricing, selection, delivery, or wagering authority.
"""
from __future__ import annotations

import dataclasses
from enum import Enum
import hashlib
import json
from types import MappingProxyType
from typing import Any

from config.competition_review_priority import CompetitionKind
from domain import current_shadow_fotmob_international_source_identity as source_identity
from domain import current_shadow_sportybet_pc_upcoming_discovery as pc_upcoming


POLICY_ID = "ATHENA_CURRENT_SHADOW_INTERNATIONAL_PROVIDER_FAMILY_BRIDGE_V1"
POLICY_SCHEMA_VERSION = 1

SOURCE_POLICY_ID = "ATHENA_CURRENT_SHADOW_FOTMOB_INTERNATIONAL_SOURCE_HIERARCHY_V1"
SOURCE_POLICY_SHA256 = "f4a50b836540d4dd797631f50215598d852aab05a9c2e9a65ff8069afcde570b"
SOURCE_RECEIPT_SHA256 = "15f8b85ba2ef5c9a8dd65fa262eb44a49b61070040cd7ea09985416c063cd91f"
PROVIDER_SOURCE_POLICY_ID = "ATHENA_CURRENT_SHADOW_PC_UPCOMING_GLOBAL_FOOTBALL_SOURCE_V1"
PROVIDER_SOURCE_POLICY_SHA256 = "63799058bec00abefb8d9b2ec9ba6dcad0c6e4775a54f17b07c0018e543ec075"
PROVIDER_RECEIPT_SHA256 = "8dde6427c296d966ff8d7f4cdec33e57a8c4210e8ecdb37071af68b0ca75bb34"

if (
    source_identity.POLICY_ID != SOURCE_POLICY_ID
    or source_identity.PINNED_POLICY_SHA256 != SOURCE_POLICY_SHA256
    or source_identity.international_source_identity_policy_sha256() != SOURCE_POLICY_SHA256
    or pc_upcoming.POLICY_ID != PROVIDER_SOURCE_POLICY_ID
    or pc_upcoming.PINNED_POLICY_SHA256 != PROVIDER_SOURCE_POLICY_SHA256
    or pc_upcoming.calculate_policy_sha256() != PROVIDER_SOURCE_POLICY_SHA256
):
    raise RuntimeError("reviewed P4.4L source/provider policy ancestry drifted")


class InternationalProviderFamilyClassification(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    EXACT_REVIEWED_MAPPING = "EXACT_REVIEWED_MAPPING"
    REVIEWED_SOURCE_PROVIDER_CONFLICT = "REVIEWED_SOURCE_PROVIDER_CONFLICT"
    REVIEWED_PROVIDER_SOURCE_CONFLICT = "REVIEWED_PROVIDER_SOURCE_CONFLICT"
    QUALIFIED_SOURCE_WITHOUT_PROVIDER_MAPPING = "QUALIFIED_SOURCE_WITHOUT_PROVIDER_MAPPING"
    OBSERVED_UNQUALIFIED_SOURCE_IDENTITY = "OBSERVED_UNQUALIFIED_SOURCE_IDENTITY"


@dataclasses.dataclass(frozen=True)
class ReviewedInternationalProviderFamilyMapping:
    source_ccode: str
    source_primary_id: int
    source_canonical_name: str
    source_priority_band: str
    source_priority_rank: int
    source_competition_kind: CompetitionKind
    provider_category_id: str
    provider_category_name: str
    provider_tournament_id: str
    provider_tournament_name: str
    mapping_cardinality: str
    source_policy_id: str = SOURCE_POLICY_ID
    source_policy_sha256: str = SOURCE_POLICY_SHA256
    provider_source_policy_id: str = PROVIDER_SOURCE_POLICY_ID
    provider_source_policy_sha256: str = PROVIDER_SOURCE_POLICY_SHA256
    source_receipt_sha256: str = SOURCE_RECEIPT_SHA256
    provider_receipt_sha256: str = PROVIDER_RECEIPT_SHA256

    @property
    def source_key(self) -> tuple[str, int]:
        return (self.source_ccode, self.source_primary_id)

    @property
    def provider_key(self) -> tuple[str, str]:
        return (self.provider_category_id, self.provider_tournament_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_ccode": self.source_ccode,
            "source_primary_id": self.source_primary_id,
            "source_canonical_name": self.source_canonical_name,
            "source_priority_band": self.source_priority_band,
            "source_priority_rank": self.source_priority_rank,
            "source_competition_kind": self.source_competition_kind.value,
            "provider_category_id": self.provider_category_id,
            "provider_category_name": self.provider_category_name,
            "provider_tournament_id": self.provider_tournament_id,
            "provider_tournament_name": self.provider_tournament_name,
            "mapping_cardinality": self.mapping_cardinality,
            "source_policy_id": self.source_policy_id,
            "source_policy_sha256": self.source_policy_sha256,
            "provider_source_policy_id": self.provider_source_policy_id,
            "provider_source_policy_sha256": self.provider_source_policy_sha256,
            "source_receipt_sha256": self.source_receipt_sha256,
            "provider_receipt_sha256": self.provider_receipt_sha256,
        }


_FAMILY_SPECS = (
    {
        "source_primary_ids": (9806, 9807, 9808),
        "canonical_name": "Nations League",
        "priority_band": "INT-D",
        "priority_rank": 40,
        "kind": CompetitionKind.INTERNATIONAL_NATIONS_LEAGUE,
        "provider_category_id": "sr:category:4",
        "provider_category_name": "International",
        "provider_tournament_id": "sr:tournament:23755",
        "provider_tournament_name": "UEFA Nations League",
        "mapping_cardinality": "MANY_SOURCE_IDENTITIES_TO_ONE_PROVIDER_FAMILY",
    },
    {
        "source_primary_ids": (9821,),
        "canonical_name": "Nations League",
        "priority_band": "INT-D",
        "priority_rank": 40,
        "kind": CompetitionKind.INTERNATIONAL_NATIONS_LEAGUE,
        "provider_category_id": "sr:category:4",
        "provider_category_name": "International",
        "provider_tournament_id": "sr:tournament:27420",
        "provider_tournament_name": "CONCACAF Nations League",
        "mapping_cardinality": "ONE_SOURCE_IDENTITY_TO_ONE_PROVIDER_FAMILY",
    },
    {
        "source_primary_ids": (10608,),
        "canonical_name": "Continental Championship Qualification",
        "priority_band": "INT-C",
        "priority_rank": 30,
        "kind": CompetitionKind.INTERNATIONAL_QUALIFIER,
        "provider_category_id": "sr:category:4",
        "provider_category_name": "International",
        "provider_tournament_id": "sr:tournament:1848",
        "provider_tournament_name": "Africa Cup of Nations Qualification",
        "mapping_cardinality": "ONE_SOURCE_IDENTITY_TO_ONE_PROVIDER_FAMILY",
    },
    {
        "source_primary_ids": (114,),
        "canonical_name": "International Friendly",
        "priority_band": "INT-F",
        "priority_rank": 60,
        "kind": CompetitionKind.INTERNATIONAL_FRIENDLY,
        "provider_category_id": "sr:category:4",
        "provider_category_name": "International",
        "provider_tournament_id": "sr:tournament:851",
        "provider_tournament_name": "Int. Friendly Games",
        "mapping_cardinality": "ONE_SOURCE_IDENTITY_TO_ONE_PROVIDER_FAMILY",
    },
)


def _build_mappings() -> tuple[ReviewedInternationalProviderFamilyMapping, ...]:
    rows: list[ReviewedInternationalProviderFamilyMapping] = []
    for spec in _FAMILY_SPECS:
        for primary_id in spec["source_primary_ids"]:
            identity = source_identity.reviewed_current_fotmob_international_source_identity(
                source_competition_ccode="INT",
                source_competition_primary_id=primary_id,
            )
            priority = source_identity.resolve_current_shadow_international_source_priority(
                source_competition_ccode="INT",
                source_competition_primary_id=primary_id,
            )
            if identity is None or priority is None or (
                identity.canonical_name != spec["canonical_name"]
                or identity.priority_band != spec["priority_band"]
                or identity.priority_rank != spec["priority_rank"]
                or identity.competition_kind is not spec["kind"]
                or priority.canonical_name != spec["canonical_name"]
                or priority.priority_band != spec["priority_band"]
                or priority.rank != spec["priority_rank"]
                or priority.kind is not spec["kind"]
            ):
                raise RuntimeError(f"P4.4L source hierarchy binding drifted for INT:{primary_id}")
            rows.append(ReviewedInternationalProviderFamilyMapping(
                source_ccode="INT",
                source_primary_id=primary_id,
                source_canonical_name=identity.canonical_name,
                source_priority_band=identity.priority_band,
                source_priority_rank=identity.priority_rank,
                source_competition_kind=identity.competition_kind,
                provider_category_id=spec["provider_category_id"],
                provider_category_name=spec["provider_category_name"],
                provider_tournament_id=spec["provider_tournament_id"],
                provider_tournament_name=spec["provider_tournament_name"],
                mapping_cardinality=spec["mapping_cardinality"],
            ))
    return tuple(sorted(rows, key=lambda row: row.source_key))


REVIEWED_MAPPINGS = _build_mappings()
_BY_SOURCE = MappingProxyType({row.source_key: row for row in REVIEWED_MAPPINGS})
_BY_PROVIDER = MappingProxyType({row.provider_key: row for row in REVIEWED_MAPPINGS})
_BY_TOURNAMENT_ID = MappingProxyType({row.provider_tournament_id: row for row in REVIEWED_MAPPINGS})


def _validate_mapping_table() -> None:
    if len(_BY_SOURCE) != len(REVIEWED_MAPPINGS):
        raise RuntimeError("international provider bridge source keys collide")
    provider_rows: dict[tuple[str, str], list[ReviewedInternationalProviderFamilyMapping]] = {}
    for row in REVIEWED_MAPPINGS:
        provider_rows.setdefault(row.provider_key, []).append(row)
        if row.source_ccode != "INT" or row.provider_category_id != "sr:category:4":
            raise RuntimeError("international provider bridge has an invalid exact identity key")
        if row.provider_category_name != "International":
            raise RuntimeError("international provider category label drifted")
    expected_many = {
        ("INT", 9806), ("INT", 9807), ("INT", 9808),
    }
    many = {
        row.source_key for row in REVIEWED_MAPPINGS
        if row.mapping_cardinality == "MANY_SOURCE_IDENTITIES_TO_ONE_PROVIDER_FAMILY"
    }
    if many != expected_many:
        raise RuntimeError("only the three reviewed UEFA source IDs may use many-to-one mapping")
    for provider_key, rows in provider_rows.items():
        if len(rows) > 1 and provider_key != ("sr:category:4", "sr:tournament:23755"):
            raise RuntimeError("unreviewed international provider-family collision")
        if len(rows) == 1 and rows[0].mapping_cardinality != "ONE_SOURCE_IDENTITY_TO_ONE_PROVIDER_FAMILY":
            raise RuntimeError("single-source mapping has invalid cardinality declaration")


_validate_mapping_table()

UNMAPPED_QUALIFIED_SOURCE_IDENTITIES = (
    ("INT", 10437, "Youth / Olympic International", "INT-G"),
    ("INT", 9833, "Youth / Olympic International", "INT-G"),
)
OBSERVED_UNQUALIFIED_SOURCE_KEY = ("INT", 13287)
PROVIDER_ONLY_UNMAPPED_GULF_CUP = (
    "sr:category:4", "International", "sr:tournament:622", "Gulf Cup"
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def policy_payload() -> dict[str, Any]:
    qualified_unmapped = []
    for ccode, primary_id, canonical_name, band in UNMAPPED_QUALIFIED_SOURCE_IDENTITIES:
        identity = source_identity.reviewed_current_fotmob_international_source_identity(
            source_competition_ccode=ccode,
            source_competition_primary_id=primary_id,
        )
        if identity is None or identity.canonical_name != canonical_name or identity.priority_band != band:
            raise RuntimeError(f"qualified but provider-unmapped P4.4L source drifted: {ccode}:{primary_id}")
        qualified_unmapped.append({
            "source_ccode": ccode,
            "source_primary_id": primary_id,
            "source_canonical_name": identity.canonical_name,
            "source_priority_band": identity.priority_band,
            "state": InternationalProviderFamilyClassification.QUALIFIED_SOURCE_WITHOUT_PROVIDER_MAPPING.value,
        })
    unqualified = source_identity.observed_unqualified_current_fotmob_international_source_identity(
        source_competition_ccode=OBSERVED_UNQUALIFIED_SOURCE_KEY[0],
        source_competition_primary_id=OBSERVED_UNQUALIFIED_SOURCE_KEY[1],
    )
    if unqualified is None:
        raise RuntimeError("P4.4L observed-unqualified source identity disappeared")
    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "source_authority": {
            "policy_id": SOURCE_POLICY_ID,
            "policy_sha256": SOURCE_POLICY_SHA256,
            "receipt_sha256": SOURCE_RECEIPT_SHA256,
        },
        "provider_source_authority": {
            "policy_id": PROVIDER_SOURCE_POLICY_ID,
            "policy_sha256": PROVIDER_SOURCE_POLICY_SHA256,
            "receipt_sha256": PROVIDER_RECEIPT_SHA256,
        },
        "reviewed_mappings": [row.to_dict() for row in REVIEWED_MAPPINGS],
        "qualified_source_identities_without_provider_mapping": qualified_unmapped,
        "observed_unqualified_source_identity": {
            "source_ccode": unqualified.source_competition_ccode,
            "source_primary_id": unqualified.source_competition_primary_id,
            "state": InternationalProviderFamilyClassification.OBSERVED_UNQUALIFIED_SOURCE_IDENTITY.value,
            "evidence_workflow_run_id": unqualified.workflow_run_id,
            "evidence_artifact_id": unqualified.artifact_id,
            "evidence_artifact_sha256": unqualified.artifact_sha256,
        },
        "provider_only_unmapped_observation": {
            "category_id": PROVIDER_ONLY_UNMAPPED_GULF_CUP[0],
            "category_name": PROVIDER_ONLY_UNMAPPED_GULF_CUP[1],
            "tournament_id": PROVIDER_ONLY_UNMAPPED_GULF_CUP[2],
            "tournament_name": PROVIDER_ONLY_UNMAPPED_GULF_CUP[3],
            "source_mapping_added": False,
        },
        "identity_semantics": {
            "source_key": "EXACT_FOTMOB_SOURCE_SCOPE_CCODE_AND_PRIMARY_ID",
            "provider_key": "EXACT_SPORTYBET_CATEGORY_ID_AND_TOURNAMENT_ID_WITH_REVIEWED_LABELS",
            "names_are_identity_keys": False,
            "fuzzy_matching": False,
            "wrapper_suffix_stripping": False,
            "provider_team_seed_authority": False,
            "uefa_many_to_one_source_keys": [["INT", 9806], ["INT", 9807], ["INT", 9808]],
        },
        "authority": {
            "identity_family_bridge": True,
            "current_shadow_runtime_discovery": False,
            "p3_runtime_discovery": False,
            "provider_acquisition": False,
            "fixture_reconciliation": False,
            "model": False,
            "pricing": False,
            "router": False,
            "portfolio": False,
            "selection": False,
            "share_code": False,
            "login": False,
            "cookies": False,
            "wallet": False,
            "staking": False,
            "bet": False,
            "wager_placed": False,
        },
    }


def calculate_policy_sha256() -> str:
    return hashlib.sha256(_canonical(policy_payload())).hexdigest()


PINNED_POLICY_SHA256 = "7db676111a9be06f63fd207815837d53699d6bf1a98364fc2163046cd1c0a4bb"


def _strict_source_key(ccode: Any, primary_id: Any) -> tuple[str, int] | None:
    if type(ccode) is not str or type(primary_id) is not int:
        return None
    if ccode != "INT" or primary_id <= 0:
        return None
    return ccode, primary_id


def classify_source_provider_family(
    *,
    source_ccode: Any,
    source_primary_id: Any,
    provider_category_id: Any,
    provider_category_name: Any,
    provider_tournament_id: Any,
    provider_tournament_name: Any,
) -> InternationalProviderFamilyClassification:
    """Classify exact cross-path identities without name-based authority."""
    source_key = _strict_source_key(source_ccode, source_primary_id)
    source_mapping = _BY_SOURCE.get(source_key) if source_key is not None else None
    provider_key = (
        (provider_category_id, provider_tournament_id)
        if type(provider_category_id) is str and type(provider_tournament_id) is str
        else None
    )
    provider_mapping = _BY_PROVIDER.get(provider_key) if provider_key is not None else None

    observed_unqualified = (
        source_identity.observed_unqualified_current_fotmob_international_source_identity(
            source_competition_ccode=source_ccode,
            source_competition_primary_id=source_primary_id,
        )
        if source_key is not None
        else None
    )
    if observed_unqualified is not None:
        return InternationalProviderFamilyClassification.OBSERVED_UNQUALIFIED_SOURCE_IDENTITY

    qualified = (
        source_identity.reviewed_current_fotmob_international_source_identity(
            source_competition_ccode=source_ccode,
            source_competition_primary_id=source_primary_id,
        )
        if source_key is not None
        else None
    )
    if source_mapping is not None:
        current_priority = source_identity.resolve_current_shadow_international_source_priority(
            source_competition_ccode=source_mapping.source_ccode,
            source_competition_primary_id=source_mapping.source_primary_id,
        )
        if qualified is None or current_priority is None or (
            qualified.canonical_name != source_mapping.source_canonical_name
            or qualified.priority_band != source_mapping.source_priority_band
            or qualified.priority_rank != source_mapping.source_priority_rank
            or qualified.competition_kind is not source_mapping.source_competition_kind
            or current_priority.canonical_name != source_mapping.source_canonical_name
            or current_priority.priority_band != source_mapping.source_priority_band
            or current_priority.rank != source_mapping.source_priority_rank
            or current_priority.kind is not source_mapping.source_competition_kind
        ):
            return InternationalProviderFamilyClassification.REVIEWED_SOURCE_PROVIDER_CONFLICT
        if provider_key != source_mapping.provider_key:
            return InternationalProviderFamilyClassification.REVIEWED_SOURCE_PROVIDER_CONFLICT
        if (
            provider_category_name != source_mapping.provider_category_name
            or provider_tournament_name != source_mapping.provider_tournament_name
        ):
            return InternationalProviderFamilyClassification.REVIEWED_SOURCE_PROVIDER_CONFLICT
        return InternationalProviderFamilyClassification.EXACT_REVIEWED_MAPPING

    if qualified is not None:
        return InternationalProviderFamilyClassification.QUALIFIED_SOURCE_WITHOUT_PROVIDER_MAPPING

    if provider_mapping is not None:
        return InternationalProviderFamilyClassification.REVIEWED_PROVIDER_SOURCE_CONFLICT

    # A reviewed tournament ID paired with a contradictory category is still
    # recognizable as a conflict; it cannot be rescued by a matching label.
    if type(provider_tournament_id) is str and provider_tournament_id in _BY_TOURNAMENT_ID:
        return InternationalProviderFamilyClassification.REVIEWED_PROVIDER_SOURCE_CONFLICT

    return InternationalProviderFamilyClassification.NOT_APPLICABLE


def mapping_for_exact_pair(
    *,
    source_ccode: Any,
    source_primary_id: Any,
    provider_category_id: Any,
    provider_category_name: Any,
    provider_tournament_id: Any,
    provider_tournament_name: Any,
) -> ReviewedInternationalProviderFamilyMapping | None:
    classification = classify_source_provider_family(
        source_ccode=source_ccode,
        source_primary_id=source_primary_id,
        provider_category_id=provider_category_id,
        provider_category_name=provider_category_name,
        provider_tournament_id=provider_tournament_id,
        provider_tournament_name=provider_tournament_name,
    )
    if classification is not InternationalProviderFamilyClassification.EXACT_REVIEWED_MAPPING:
        return None
    return _BY_SOURCE[(source_ccode, source_primary_id)]


def provider_pair_is_reviewed_international_family(category_id: Any, tournament_id: Any) -> bool:
    """Return true only for the exact category/tournament pair IDs."""
    if type(category_id) is not str or type(tournament_id) is not str:
        return False
    return (category_id, tournament_id) in _BY_PROVIDER


def provider_tournament_is_reviewed_international_family(tournament_id: Any) -> bool:
    """Recognize a mapped tournament ID even if its observed category conflicts."""
    return type(tournament_id) is str and tournament_id in _BY_TOURNAMENT_ID


__all__ = [
    "InternationalProviderFamilyClassification",
    "POLICY_ID",
    "POLICY_SCHEMA_VERSION",
    "PINNED_POLICY_SHA256",
    "PROVIDER_RECEIPT_SHA256",
    "PROVIDER_SOURCE_POLICY_ID",
    "PROVIDER_SOURCE_POLICY_SHA256",
    "REVIEWED_MAPPINGS",
    "ReviewedInternationalProviderFamilyMapping",
    "SOURCE_POLICY_ID",
    "SOURCE_POLICY_SHA256",
    "SOURCE_RECEIPT_SHA256",
    "UNMAPPED_QUALIFIED_SOURCE_IDENTITIES",
    "OBSERVED_UNQUALIFIED_SOURCE_KEY",
    "PROVIDER_ONLY_UNMAPPED_GULF_CUP",
    "calculate_policy_sha256",
    "classify_source_provider_family",
    "mapping_for_exact_pair",
    "policy_payload",
    "provider_pair_is_reviewed_international_family",
    "provider_tournament_is_reviewed_international_family",
]
