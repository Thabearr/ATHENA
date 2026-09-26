"""Offline audit for the evidence-bound P4.4L/SportyBet family bridge."""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from typing import Any

from domain import current_shadow_fixture_identity_compatibility as compatibility
from domain import current_shadow_fixture_identity_v2 as identity
from domain import current_shadow_sportybet_international_provider_family_bridge as bridge
from domain import current_shadow_sportybet_pc_upcoming_discovery as pc_upcoming
from domain import current_shadow_sportybet_upcoming_reconciliation as old_upcoming
from domain import current_shadow_sportybet_paginated_discovery_reconciliation as paginated
from domain import current_shadow_sportybet_catalog_fanout_reconciliation as fanout
from scripts import verify_p3_0_e1_live_readiness as p3_readiness


RECEIPT_PATH = Path("artifacts/architecture/post_p4_4l_international_provider_family_bridge_v1.json")
BASE_MAIN = "9e121e8e5022313bf715639a888949a67aa048b1"
SEED_REGISTRY_SHA256 = "7fe662fc91a80daabf1e774ddd5c8ecdb5215eaf63adb03822b3fb05f872df79"
V2_REGISTRY_SHA256_BEFORE = "fae19e6db66c1dca559895fb4ae30b591628b72965989c027c5f5ae785bced3f"
V2_REGISTRY_SHA256_AFTER = "fc64fb0c2df3cee4f425158c48cfaada6757ba01e1759dd5b976ca899f85421e"
COMPATIBILITY_SHA256_BEFORE = "e1ce7468c61dcf4067725f6d58cd34d36bd1dc01e3a2177c4a724647bcab324b"
COMPATIBILITY_SHA256_AFTER = "dbef6539dd7c5d1c1589debe8daca9378ea2e0c0bb32acf3315a0d1a005c2b58"
UPCOMING_COMPATIBILITY_SHA256_BEFORE = "29a250f3b7db3b0d84e8852df4a119df34e3eab914d5ac4e56c25d2e19ef64f2"
UPCOMING_COMPATIBILITY_SHA256_AFTER = "e0718a5e7c9e0c707ba5cc7369910f3ec371bd1a9f7520ab41aa30df69d0ab12"
UPSTREAM_SOURCE_SHA256 = "90c14bd68ed6e8205c16fedfa815d120c53f2af1a3a8f362eee2702a4223b9ff"
PAGINATED_SHA256_BEFORE = "106c296d2f5428dfdc1a27782c230bd57cde1f957df23d119a3989c4d9040a90"
PAGINATED_SHA256_AFTER = "6de2847f8ed32873f7ae50e902708c7e27ca5516f492e183063f3dfc0f1635a8"
FANOUT_SHA256_BEFORE = "cf9ee8d606288eb8f3b964b5a581fca007ce3d6baf018b50633e0288dc31ce58"
FANOUT_SHA256_AFTER = "2d8c1f7b533eea104c1951a9a1f963c4cd85933252aa44da7dbeb447528ad0a0"
EXPECTED_SOURCE_KEYS = {("INT", 9806), ("INT", 9807), ("INT", 9808), ("INT", 9821), ("INT", 10608), ("INT", 114)}
EXPECTED_PROVIDER_ROWS = {
    ("INT", 9806): ("sr:category:4", "International", "sr:tournament:23755", "UEFA Nations League"),
    ("INT", 9807): ("sr:category:4", "International", "sr:tournament:23755", "UEFA Nations League"),
    ("INT", 9808): ("sr:category:4", "International", "sr:tournament:23755", "UEFA Nations League"),
    ("INT", 9821): ("sr:category:4", "International", "sr:tournament:27420", "CONCACAF Nations League"),
    ("INT", 10608): ("sr:category:4", "International", "sr:tournament:1848", "Africa Cup of Nations Qualification"),
    ("INT", 114): ("sr:category:4", "International", "sr:tournament:851", "Int. Friendly Games"),
}
EXPECTED_UNMAPPED = {
    ("INT", 10437, "QUALIFIED_SOURCE_WITHOUT_PROVIDER_MAPPING"),
    ("INT", 9833, "QUALIFIED_SOURCE_WITHOUT_PROVIDER_MAPPING"),
    ("INT", 13287, "OBSERVED_UNQUALIFIED_SOURCE_IDENTITY"),
}


class InternationalProviderFamilyBridgeAuditError(ValueError):
    """Raised when bridge evidence or isolation semantics drift."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InternationalProviderFamilyBridgeAuditError(message)


def _receipt_mapping(row: bridge.ReviewedInternationalProviderFamilyMapping) -> dict[str, Any]:
    return {
        "source_ccode": row.source_ccode,
        "source_primary_id": row.source_primary_id,
        "source_canonical_name": row.source_canonical_name,
        "source_priority_band": row.source_priority_band,
        "source_priority_rank": row.source_priority_rank,
        "source_competition_kind": row.source_competition_kind.value,
        "provider_category_id": row.provider_category_id,
        "provider_category_name": row.provider_category_name,
        "provider_tournament_id": row.provider_tournament_id,
        "provider_tournament_name": row.provider_tournament_name,
        "mapping_cardinality": row.mapping_cardinality,
    }


def validate_receipt(receipt: Any) -> str:
    _require(type(receipt) is dict, "bridge architecture receipt must be an object")
    embedded = receipt.get("canonical_sha256")
    _require(type(embedded) is str and len(embedded) == 64, "bridge receipt canonical SHA is missing")
    semantic = dict(receipt)
    semantic.pop("canonical_sha256", None)
    actual = hashlib.sha256(_canonical(semantic)).hexdigest()
    _require(actual == embedded, "bridge receipt canonical SHA mismatch")
    _require(receipt.get("schema_version") == 1 and receipt.get("repository") == "Thabearr/ATHENA", "bridge receipt schema/repository drifted")
    _require(receipt.get("base_main_sha") == BASE_MAIN, "bridge receipt base main drifted")
    _require(receipt.get("bridge_policy_id") == bridge.POLICY_ID, "bridge policy ID drifted")
    _require(receipt.get("bridge_policy_sha256") == bridge.PINNED_POLICY_SHA256 == bridge.calculate_policy_sha256(), "bridge policy SHA drifted")
    _require(receipt.get("source_authority") == {
        "policy_id": bridge.SOURCE_POLICY_ID,
        "policy_sha256": bridge.SOURCE_POLICY_SHA256,
        "receipt_sha256": bridge.SOURCE_RECEIPT_SHA256,
    }, "P4.4L policy/receipt ancestry drifted")
    _require(receipt.get("provider_source_authority") == {
        "policy_id": bridge.PROVIDER_SOURCE_POLICY_ID,
        "policy_sha256": bridge.PROVIDER_SOURCE_POLICY_SHA256,
        "receipt_sha256": bridge.PROVIDER_RECEIPT_SHA256,
    }, "PR #405 policy/receipt ancestry drifted")
    receipt_rows = receipt.get("reviewed_mappings")
    _require(type(receipt_rows) is list and sorted(
        receipt_rows,
        key=lambda row: (row.get("source_ccode", ""), row.get("source_primary_id", -1)) if type(row) is dict else ("", -1),
    ) == [_receipt_mapping(row) for row in bridge.REVIEWED_MAPPINGS], "receipt exact mappings drifted")
    _require({row.source_key for row in bridge.REVIEWED_MAPPINGS} == EXPECTED_SOURCE_KEYS, "source mapping set drifted")
    _require({row.source_key: row.provider_key + (row.provider_category_name, row.provider_tournament_name) for row in bridge.REVIEWED_MAPPINGS} == {
        key: (value[0], value[2], value[1], value[3]) for key, value in EXPECTED_PROVIDER_ROWS.items()
    }, "provider-native mapping IDs or wrapper labels drifted")
    uefa = receipt.get("uefa_many_to_one")
    _require(type(uefa) is dict and uefa == {
        "provider_category_id": "sr:category:4",
        "provider_tournament_id": "sr:tournament:23755",
        "source_keys": [["INT", 9806], ["INT", 9807], ["INT", 9808]],
        "cardinality": "MANY_SOURCE_IDENTITIES_TO_ONE_PROVIDER_FAMILY",
    }, "bounded UEFA many-to-one semantics drifted")
    unmapped = receipt.get("unmapped_source_identities")
    _require(type(unmapped) is list and {
        (row.get("ccode"), row.get("primary_id"), row.get("state")) for row in unmapped if type(row) is dict
    } == EXPECTED_UNMAPPED and len(unmapped) == 3, "unmapped youth/unqualified source identities changed")
    _require(receipt.get("provider_only_unmapped_observation") == {
        "category_id": "sr:category:4",
        "category_name": "International",
        "tournament_id": "sr:tournament:622",
        "tournament_name": "Gulf Cup",
        "source_mapping_added": False,
    }, "provider-only Gulf Cup observation gained source authority")
    semantics = receipt.get("identity_semantics")
    _require(type(semantics) is dict and semantics == {
        "exact_provider_ids_and_reviewed_labels_required": True,
        "display_name_matching_authority": False,
        "fuzzy_matching": False,
        "suffix_stripping": False,
        "provider_team_seeds_added": False,
        "bridge_rows_persisted_as_learned_competition_mappings": False,
    }, "identity authority semantics broadened")
    continuity = receipt.get("continuity")
    _require(type(continuity) is dict, "runtime continuity evidence missing")
    _require(continuity.get("v2_seed_registry_sha256_before") == SEED_REGISTRY_SHA256 == continuity.get("v2_seed_registry_sha256_after") == identity.seed_registry_sha256(), "club/general V2 seed registry changed")
    _require(continuity.get("seed_registry_unchanged") is True, "V2 seed continuity assertion missing")
    _require(continuity.get("v2_registry_sha256_before") == V2_REGISTRY_SHA256_BEFORE, "historical V2 registry identity drifted")
    _require(continuity.get("v2_registry_sha256_after") == V2_REGISTRY_SHA256_AFTER == identity.REGISTRY_SHA256 == identity.registry_sha256(), "new V2 semantic registry identity drifted")
    _require(V2_REGISTRY_SHA256_AFTER != V2_REGISTRY_SHA256_BEFORE, "V2 semantic registry falsely retained old hash")
    _require(continuity.get("identity_compatibility_sha256_before") == COMPATIBILITY_SHA256_BEFORE, "historical compatibility identity drifted")
    _require(continuity.get("identity_compatibility_sha256_after") == COMPATIBILITY_SHA256_AFTER, "historical PR #406 compatibility identity drifted")
    _require(continuity.get("current_shadow_upcoming_compatibility_sha256_before") == UPCOMING_COMPATIBILITY_SHA256_BEFORE, "historical upcoming compatibility identity drifted")
    _require(continuity.get("current_shadow_upcoming_compatibility_sha256_after") == UPCOMING_COMPATIBILITY_SHA256_AFTER, "historical PR #406 upcoming compatibility identity drifted")
    _require(continuity.get("upstream_upcoming_source_contract_sha256_unchanged") == UPSTREAM_SOURCE_SHA256 == old_upcoming.UPSTREAM_UPCOMING_SOURCE_CONTRACT_SHA256, "upstream provider-source contract changed")
    _require(continuity.get("retained_paginated_compatibility_sha256_before") == PAGINATED_SHA256_BEFORE and continuity.get("retained_paginated_compatibility_sha256_after") == PAGINATED_SHA256_AFTER, "historical PR #406 paginated compatibility lineage drifted")
    _require(continuity.get("retained_fanout_compatibility_sha256_before") == FANOUT_SHA256_BEFORE and continuity.get("retained_fanout_compatibility_sha256_after") == FANOUT_SHA256_AFTER, "historical PR #406 fanout compatibility lineage drifted")
    _require(continuity.get("identity_state_schema_version") == 2 == identity.STATE_SCHEMA_VERSION, "identity-state schema changed")
    _require(continuity.get("current_shadow_runtime_source") == "ATHENA_CURRENT_SHADOW_UPCOMING_DISCOVERY_V1" and continuity.get("p3_runtime_source") == "ATHENA_CURRENT_SHADOW_UPCOMING_DISCOVERY_V1", "current runtime source owner changed")
    _require(continuity.get("pc_upcoming_status") == "EVIDENCE_QUALIFIED_CANDIDATE_NOT_RUNTIME_OWNER" and continuity.get("current_shadow_runtime_changed") is False and continuity.get("p3_runtime_changed") is False, "pcUpcoming candidate was promoted")
    authority = receipt.get("authority")
    authority_keys = {
        "current_shadow_runtime_discovery", "p3_runtime_discovery", "provider_acquisition",
        "workflow_dispatch", "live_retry", "model", "pricing", "router", "portfolio",
        "share_code", "login", "cookies", "wallet", "staking", "bet", "wager_placed",
    }
    _require(type(authority) is dict and set(authority) == authority_keys and all(value is False for value in authority.values()), "bridge authority flags broadened or receipt authority shape drifted")
    _require(receipt.get("governance") == {
        "source_review_counter_while_unmerged": "1/5",
        "p4_4_complete": False,
        "architecture_checkpoint_e_complete": False,
        "next_live_proof_authorized": False,
    }, "governance state drifted")
    return actual


def validate_runtime_isolation(repository_root: str | Path = ".") -> None:
    identity.reset_runtime_evidence()
    _require(identity.seed_registry_sha256() == SEED_REGISTRY_SHA256, "V2 club/general seed set changed")
    _require(identity.registry_sha256() == V2_REGISTRY_SHA256_AFTER, "V2 semantic registry hash drifted")
    registry = identity.registry_payload()
    _require(registry.get("international_provider_family_bridge_policy_id") == bridge.POLICY_ID and registry.get("international_provider_family_bridge_policy_sha256") == bridge.PINNED_POLICY_SHA256, "V2 registry omits bridge policy ancestry")
    _require(registry.get("provider_identity_projection_source_policy_id") == pc_upcoming.POLICY_ID and registry.get("provider_identity_projection_source_policy_sha256") == pc_upcoming.PINNED_POLICY_SHA256 and registry.get("provider_identity_projection_raw_ancestry_required") is True, "V2 registry omits projection raw ancestry")
    bridge_provider_keys = {row.provider_key for row in bridge.REVIEWED_MAPPINGS}
    _require(not (bridge_provider_keys & set(identity._comp_reverse)), "bridge rows were inserted in the learned one-to-one competition registry")
    _require(pc_upcoming.PINNED_POLICY_SHA256 == bridge.PROVIDER_SOURCE_POLICY_SHA256, "pcUpcoming source contract identity drifted")
    compatibility_source = inspect.getsource(compatibility.match_current_shadow_event)
    bridge_guard = compatibility_source.find("provider_event_requires_international_family_bridge")
    old_path = compatibility_source.find("run199_identity.match_event")
    _require(bridge_guard >= 0 and old_path > bridge_guard, "bridge-owned provider events can fall through legacy identity paths")
    compatibility_payload = compatibility._policy_payload()
    _require(compatibility_payload.get("match_order") == ["RUN199_EXACT_FIXTURE_IDENTITY_OVERLAY", "V3_IDENTITY_RECOVERY", "V2_STABLE_IDENTITY", "REVIEWED_LITERAL_MATCH"], "default compatibility order changed")
    preemption = compatibility_payload.get("international_bridge_preemption", {})
    _require(preemption.get("match_order") == ["V2_STABLE_IDENTITY_WITH_INTERNATIONAL_PROVIDER_FAMILY_BRIDGE", "FAIL_CLOSED_NO_RUN199_V3_ALIAS_LITERAL_FALLTHROUGH"] and preemption.get("bridge_policy_sha256") == bridge.PINNED_POLICY_SHA256, "bridge-first compatibility contract missing")
    _require(compatibility_payload.get("provider_evidence_observation_policy_id") == "VERIFIED_PROVIDER_RAW_BYTES_PLUS_RAW_ANCESTRY_BOUND_ATHENA_PCUPCOMING_PROJECTION_V2" and compatibility_payload.get("provider_evidence_observation", {}).get("athena_projection_requires_exact_observed_provider_page_raw_sha256") is True, "projection observation contract is stale")
    from scripts import audit_p4_4n_sportybet_team_label_shape_compatibility as p44n
    current = p44n.audit(repository_root)
    _require(current.get("status") == "PASSED", "P4.4N current-state supersession is not authenticated")
    _require(compatibility.EXPECTED_POLICY_SHA256 == current.get("identity_compatibility_sha256"), "current identity compatibility no longer matches P4.4N supersession")
    _require(old_upcoming.CURRENT_SHADOW_UPCOMING_COMPATIBILITY_SHA256 == current.get("retained_wap_compatibility_sha256"), "current WAP compatibility no longer matches P4.4N supersession")


def audit(repository_root: str | Path = ".") -> dict[str, str]:
    root = Path(repository_root)
    try:
        receipt = json.loads((root / RECEIPT_PATH).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InternationalProviderFamilyBridgeAuditError("bridge architecture receipt is unavailable") from exc
    receipt_sha = validate_receipt(receipt)
    validate_runtime_isolation(root)
    from scripts import audit_post_p4_4l_pc_upcoming_runtime_migration as migration
    supersession = migration.audit(root)
    _require(supersession.get("status") == "PASSED", "reviewed runtime migration supersession is not authenticated")
    return {
        "bridge_policy_sha256": bridge.calculate_policy_sha256(),
        "receipt_sha256": receipt_sha,
        "runtime_migration_receipt_sha256": supersession["migration_receipt_sha256"],
    }


if __name__ == "__main__":
    result = audit()
    print(json.dumps({"status": "PASS", **result}, sort_keys=True))
