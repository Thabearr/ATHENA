#!/usr/bin/env python3
"""Offline, fail-closed audit for P4.4Q pcUpcoming simple-tournament identity admission."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

from domain import current_shadow_all_market_runner as runner
from domain import current_shadow_fixture_identity_compatibility as identity_compatibility
from domain import current_shadow_fixture_identity_v2 as identity_v2
from domain import current_shadow_sportybet_international_provider_family_bridge as bridge
from domain import current_shadow_sportybet_pc_upcoming_discovery as source
from domain import current_shadow_sportybet_pc_upcoming_reconciliation as runtime
from domain import current_shadow_sportybet_paginated_discovery_reconciliation as paginated
from domain import current_shadow_sportybet_catalog_fanout_reconciliation as fanout
from domain import current_shadow_sportybet_team_label_compatibility as team_labels
from domain import current_shadow_sportybet_upcoming_reconciliation as wap
from scripts import verify_p3_0_e1_live_readiness as p3


RECEIPT_PATH = Path("artifacts/architecture/p4_4q_pc_upcoming_simple_tournament_identity_v1.json")
SOURCE_RECEIPT_PATH = Path("artifacts/architecture/p4_4q_pc_upcoming_simple_tournament_source_compatibility_v1.json")
BRIDGE_RECEIPT_PATH = Path("artifacts/architecture/p4_4q_international_bridge_source_ancestry_v1.json")

POLICY_ID = "ATHENA_P4_4Q_PC_UPCOMING_SIMPLE_TOURNAMENT_IDENTITY_V1"
SOURCE_RECEIPT_POLICY_ID = "ATHENA_P4_4Q_PC_UPCOMING_SIMPLE_TOURNAMENT_SOURCE_COMPATIBILITY_V1"
BRIDGE_RECEIPT_POLICY_ID = "ATHENA_P4_4Q_INTERNATIONAL_BRIDGE_SOURCE_ANCESTRY_V1"

BASE_MAIN_SHA = "1c70a32ce16afd633af85922edcda8ac058bed43"

OLD_SOURCE_SHA256 = "63799058bec00abefb8d9b2ec9ba6dcad0c6e4775a54f17b07c0018e543ec075"
NEW_SOURCE_SHA256 = "f0e25a0da8fab8ae22a6d8f4b2d6931c5d16297e28365d8c492c2504a05f431b"

OLD_BRIDGE_SHA256 = "7db676111a9be06f63fd207815837d53699d6bf1a98364fc2163046cd1c0a4bb"
NEW_BRIDGE_SHA256 = "e6e937ff72c83ff2120fcfdfbc3dc3cbf6c8fa10a17122308d60dd0fb0505d2d"

OLD_V2_SHA256 = "fc64fb0c2df3cee4f425158c48cfaada6757ba01e1759dd5b976ca899f85421e"
NEW_V2_SHA256 = "d787ace95bcd9e95c8ade0120580f8f42245f2a32bedd1441825cf42a78f67db"

V2_SEED_SHA256 = "7fe662fc91a80daabf1e774ddd5c8ecdb5215eaf63adb03822b3fb05f872df79"

OLD_IDENTITY_SHA256 = "2fdbb8165262f6e633ee48276aea57c9235699272235798e1cef12fdc714ae04"
NEW_IDENTITY_SHA256 = "5b5f804fc0ca21a8f5a15334a32faedc5f9eaa23024adac5c42d467f9fef37fc"

TEAM_LABEL_SHA256 = "0c382ec8b12d802879a51b766daae8f655dd5b371509653e56a13190a85c6c7b"

OLD_WAP_SHA256 = "dd1b4366ef2cf4d1e12359c42fbff5cbae8bef60cc06ca40589ec0e8a157f943"
NEW_WAP_SHA256 = "1ef767b2de32b4d3a51bd9ec5c8244744ce5ba9ddf45c7d61b307327351e81a4"

OLD_PAGINATED_SHA256 = "7373a05c25466206aa3a67bc53b219e8d2841f432fda13db2dc0808b40b47238"
NEW_PAGINATED_SHA256 = "17b5e525ea5a253738ab3daed06e0af93ac54eed6e3f06a2278262e6898ad7b6"

OLD_FANOUT_SHA256 = "c1ce52d8c441a6a38aee08c05413d579f0f18a497e56eb7833faf1fbc60c622f"
NEW_FANOUT_SHA256 = "9fa6673848e627e1b59d922dd83b93dd979fa2325eac26b84917cd20f187e022"

OLD_RUNTIME_SHA256 = "a5c42439e894d33950b5cba608dcd5a031896e7a8e75c6bf613b2314497b1c24"
NEW_RUNTIME_SHA256 = "5af808f2dddba92088d80fe6572b6ec895ee1e0df0938f8ba143d07df845bdec"

P44M_WORKFLOW_SHA256 = "45f7fe3556f892320a12b15c210637782edca60792ccbf030a714414a32f005a"

HISTORICAL_RECEIPTS = {
    "artifacts/architecture/post_p4_4l_pc_upcoming_shared_football_source_v1.json": "8dde6427c296d966ff8d7f4cdec33e57a8c4210e8ecdb37071af68b0ca75bb34",
    "artifacts/architecture/post_p4_4l_international_provider_family_bridge_v1.json": "34c183b5274e9e2c3320b5a8d75a123b7ebed2405aa55cdfb1af7d59c2613aa2",
    "artifacts/architecture/post_p4_4l_pc_upcoming_runtime_migration_v1.json": "09bbbb0842b0f92c214d5e868ec3fe5e2d047f9de7b5c3e6d620bc147092f6f3",
    "artifacts/architecture/p4_4m_athena_run_pc_upcoming_evidence_preservation_v1.json": "8202845b28abcea6ff8ea0ffb279a924b09ca7b2e5ab1d1918c957b757f345cf",
    "artifacts/architecture/p4_4n_sportybet_team_label_shape_compatibility_v1.json": "3f08b29da1cfa782d897d8bad9ea8cb4c05a962e5402144d3982d7f7e3e47ec5",
    "artifacts/architecture/p4_4o_pc_upcoming_stable_epoch_recovery_v1.json": "766b8d54dec4310b60c032a26a51cdac0dbab436dbbd0ee81bb0f5cde4e4db3f",
    "artifacts/architecture/p4_4p_pc_upcoming_preparse_response_evidence_v1.json": "d7d8c9733b41b0146e73940769f66c6103c48c87bed054ecbbadb512aae1ffae",
}


class P44QError(RuntimeError):
    """Raised when P4.4Q verification fails closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise P44QError(message)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _read_json(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise P44QError(f"required P4.4Q evidence is unavailable: {relative}") from exc
    _require(type(value) is dict, f"P4.4Q evidence must be an object: {relative}")
    return value


def _verify_receipt(root: Path) -> dict[str, Any]:
    receipt = _read_json(root, RECEIPT_PATH)
    semantic = dict(receipt)
    actual = semantic.pop("canonical_sha256", None)
    _require(type(actual) is str and actual == hashlib.sha256(_canonical(semantic)).hexdigest(),
             "P4.4Q receipt canonical SHA mismatch")
    _require(receipt.get("schema_version") == 1 and receipt.get("policy_id") == POLICY_ID,
             "P4.4Q receipt schema/policy identity drifted")
    _require(receipt.get("repository") == "Thabearr/ATHENA" and receipt.get("base_main_sha") == BASE_MAIN_SHA,
             "P4.4Q base/repository identity drifted")
    _require(receipt.get("source_review_counter_while_unmerged") == "2/5"
             and receipt.get("source_review_counter_if_merged") == "3/5",
             "P4.4Q source-review counter drifted")

    failed = receipt.get("failed_proof", {})
    _require(failed.get("run_id") == 36273291448
             and failed.get("artifact_id") == 10915589630
             and failed.get("artifact_name") == "athena-run-36273291448"
             and failed.get("artifact_zip_sha256") == "cf71cc2b502e2ca9ebfbb6b9da07a8196508e015291ea1c37734a062e8f14b12"
             and failed.get("evidence_comment_id") == 5850164306
             and failed.get("diagnosis_comment_id") == 5850251689
             and failed.get("classification") == (
                 "POST_P4_4P_CANONICAL_SHADOW_SUCCESSOR_PROOF_INCOMPLETE:"
                 "PC_UPCOMING_RUNTIME_SOURCE_INCOMPLETE_TOURNAMENT_ID_NOT_EXACT_PROVIDER_NATIVE_ID"
             )
             and failed.get("exact_failing_page_num") == 7
             and failed.get("exact_failing_raw_sha256") == "77fc822ef8448e97ec46937fc51d023b2179c39fbf14daa5637a44e23a6664ad"
             and failed.get("parse_failure_receipt_sha256") == "bb766117f7e3855f515c6d783cb602634c84458f17e9437e686cc2d14a750f5c"
             and failed.get("exact_failing_path") == "$.data.tournaments[8].id"
             and failed.get("exact_failing_value") == "sr:simple_tournament:11141",
             "P4.4Q failed proof binding drifted")

    source_receipt = _read_json(root, SOURCE_RECEIPT_PATH)
    source_sem = dict(source_receipt)
    source_actual = source_sem.pop("canonical_sha256", None)
    _require(source_actual == hashlib.sha256(_canonical(source_sem)).hexdigest(),
             "source receipt self-hash drifted")
    _require(receipt.get("source_receipt", {}).get("canonical_sha256") == source_actual,
             "source receipt SHA mismatch in final receipt")

    bridge_receipt = _read_json(root, BRIDGE_RECEIPT_PATH)
    bridge_sem = dict(bridge_receipt)
    bridge_actual = bridge_sem.pop("canonical_sha256", None)
    _require(bridge_actual == hashlib.sha256(_canonical(bridge_sem)).hexdigest(),
             "bridge receipt self-hash drifted")
    _require(receipt.get("bridge_receipt", {}).get("canonical_sha256") == bridge_actual,
             "bridge receipt SHA mismatch in final receipt")

    hashes = receipt.get("lineage_hashes", {})
    _require(hashes == {
        "source_sha256_before": OLD_SOURCE_SHA256,
        "source_sha256_after": NEW_SOURCE_SHA256,
        "bridge_sha256_before": OLD_BRIDGE_SHA256,
        "bridge_sha256_after": NEW_BRIDGE_SHA256,
        "v2_semantic_registry_sha256_before": OLD_V2_SHA256,
        "v2_semantic_registry_sha256_after": NEW_V2_SHA256,
        "v2_seed_registry_sha256_before": V2_SEED_SHA256,
        "v2_seed_registry_sha256_after": V2_SEED_SHA256,
        "seed_registry_unchanged": True,
        "identity_compatibility_sha256_before": OLD_IDENTITY_SHA256,
        "identity_compatibility_sha256_after": NEW_IDENTITY_SHA256,
        "retained_wap_compatibility_sha256_before": OLD_WAP_SHA256,
        "retained_wap_compatibility_sha256_after": NEW_WAP_SHA256,
        "retained_paginated_contract_sha256_before": OLD_PAGINATED_SHA256,
        "retained_paginated_contract_sha256_after": NEW_PAGINATED_SHA256,
        "retained_fanout_contract_sha256_before": OLD_FANOUT_SHA256,
        "retained_fanout_contract_sha256_after": NEW_FANOUT_SHA256,
        "runtime_policy_sha256_before": OLD_RUNTIME_SHA256,
        "runtime_policy_sha256_after": NEW_RUNTIME_SHA256,
    }, "lineage hashes before/after drifted")

    invariants = receipt.get("invariants", {})
    _require(invariants == {
        "team_label_v6_sha256": TEAM_LABEL_SHA256,
        "team_label_v6_unchanged": True,
        "p4_4o_stable_epoch_recovery_unchanged": True,
        "p4_4p_preparse_response_evidence_unchanged": True,
        "workflow_sha256": P44M_WORKFLOW_SHA256,
        "workflow_yaml_changed": False,
        "admitted_tournament_grammar": "^sr:(?:tournament|simple_tournament):[1-9][0-9]*$",
        "mapping_additions": 0,
        "seed_additions": 0,
    }, "invariants drifted")

    auth = receipt.get("authority_and_execution", {})
    _require(auth == {
        "provider_acquisition_during_implementation": False,
        "workflow_dispatch_during_implementation": False,
        "live_retry": False,
        "share_code_action": False,
        "wager_action": False,
        "caller_migration": False,
        "workflow_retirement": False,
        "successor_proof_complete": False,
        "successor_proof_rerun": False,
        "next_live_proof_authorized": False,
        "p4_4_complete": False,
        "architecture_checkpoint_e_complete": False,
    }, "authority and execution profile overclaims capabilities")
    return receipt


def _verify_historical_receipts(root: Path) -> None:
    for relative, expected_canonical in HISTORICAL_RECEIPTS.items():
        value = _read_json(root, Path(relative))
        _require(value.get("canonical_sha256") == expected_canonical,
                 f"historical receipt canonical identity changed: {relative}")
        semantic = dict(value)
        embedded = semantic.pop("canonical_sha256", None)
        if relative.endswith("p4_4m_athena_run_pc_upcoming_evidence_preservation_v1.json"):
            from scripts import audit_p4_workflow_evolution_ledger as evolution
            computed = evolution.canonical_sha256(semantic)
        else:
            computed = hashlib.sha256(_canonical(semantic)).hexdigest()
        _require(embedded == computed,
                 f"historical receipt self-hash invalid: {relative}")


def _verify_current_contract(receipt: dict[str, Any], root: Path) -> dict[str, Any]:
    runtime.validate_contract()
    _require(runtime.POLICY_ID == "ATHENA_CURRENT_SHADOW_PC_UPCOMING_DISCOVERY_RECONCILIATION_V1"
             and runtime.calculate_policy_sha256() == NEW_RUNTIME_SHA256
             and runtime.PINNED_POLICY_SHA256 == NEW_RUNTIME_SHA256,
             "runtime wrapper policy SHA drifted")

    _require(source.POLICY_ID == "ATHENA_CURRENT_SHADOW_PC_UPCOMING_GLOBAL_FOOTBALL_SOURCE_V1"
             and source.calculate_policy_sha256() == NEW_SOURCE_SHA256
             and source.PINNED_POLICY_SHA256 == NEW_SOURCE_SHA256,
             "source discovery policy SHA drifted")

    _require(bridge.POLICY_ID == "ATHENA_CURRENT_SHADOW_INTERNATIONAL_PROVIDER_FAMILY_BRIDGE_V1"
             and bridge.calculate_policy_sha256() == NEW_BRIDGE_SHA256
             and bridge.PINNED_POLICY_SHA256 == NEW_BRIDGE_SHA256,
             "bridge policy SHA drifted")

    _require(identity_v2.REGISTRY_SHA256 == NEW_V2_SHA256
             and identity_v2.registry_sha256() == NEW_V2_SHA256
             and identity_v2.SEED_REGISTRY_SHA256 == V2_SEED_SHA256
             and identity_v2.seed_registry_sha256() == V2_SEED_SHA256,
             "identity V2 registry drifted")

    _require(identity_compatibility.POLICY_ID == "ATHENA_CURRENT_SHADOW_FIXTURE_IDENTITY_COMPATIBILITY_V1"
             and identity_compatibility.calculate_policy_sha256() == NEW_IDENTITY_SHA256
             and identity_compatibility.EXPECTED_POLICY_SHA256 == NEW_IDENTITY_SHA256,
             "identity compatibility policy SHA drifted")

    _require(team_labels.policy_sha256() == TEAM_LABEL_SHA256
             and team_labels.EXPECTED_POLICY_SHA256 == TEAM_LABEL_SHA256,
             "team label V6 policy SHA drifted")

    _require(wap.CURRENT_SHADOW_UPCOMING_COMPATIBILITY_SHA256 == NEW_WAP_SHA256
             and wap.calculate_current_shadow_upcoming_compatibility_sha256() == NEW_WAP_SHA256,
             "retained WAP compatibility contract SHA drifted")

    _require(paginated.EXPECTED_CONTRACT_SHA256 == NEW_PAGINATED_SHA256
             and paginated.calculate_contract_sha256() == NEW_PAGINATED_SHA256,
             "retained paginated discovery contract SHA drifted")

    _require(fanout.EXPECTED_CONTRACT_SHA256 == NEW_FANOUT_SHA256
             and fanout.calculate_contract_sha256() == NEW_FANOUT_SHA256,
             "retained catalog fanout contract SHA drifted")

    _require(runner.reconciliation is runtime and runner.upcoming_discovery is runtime,
             "Current Shadow active source owner changed")

    p3_contract = p3.check_f_upcoming_discovery_contract()
    _require(p3_contract.get("runtime_policy_id") == runtime.POLICY_ID
             and p3_contract.get("runtime_policy_sha256") == NEW_RUNTIME_SHA256,
             "P3 readiness does not pin the exact current runtime")

    _require(runtime.AUTHORITY["model"] is False and runtime.AUTHORITY["pricing"] is False
             and runtime.AUTHORITY["router"] is False and runtime.AUTHORITY["portfolio"] is False
             and runtime.AUTHORITY["login"] is False and runtime.AUTHORITY["cookies"] is False
             and runtime.AUTHORITY["wallet"] is False and runtime.AUTHORITY["staking"] is False
             and runtime.AUTHORITY["bet"] is False and runtime.AUTHORITY["wager_placed"] is False,
             "runtime authority profile broadened")

    workflow = root / ".github/workflows/athena-run.yml"
    try:
        workflow_sha = hashlib.sha256(workflow.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    except OSError as exc:
        raise P44QError("P4.4M workflow is unavailable") from exc
    _require(workflow_sha == P44M_WORKFLOW_SHA256, "P4.4M workflow bytes changed")

    return {
        "runtime_policy_id": runtime.POLICY_ID,
        "runtime_policy_sha256": runtime.PINNED_POLICY_SHA256,
        "source_policy_sha256": source.PINNED_POLICY_SHA256,
        "team_label_policy_sha256": team_labels.EXPECTED_POLICY_SHA256,
        "identity_compatibility_sha256": identity_compatibility.EXPECTED_POLICY_SHA256,
        "bridge_policy_sha256": bridge.PINNED_POLICY_SHA256,
        "v2_semantic_registry_sha256": identity_v2.REGISTRY_SHA256,
        "v2_seed_registry_sha256": identity_v2.SEED_REGISTRY_SHA256,
        "current_shadow_and_p3_shared_source": True,
        "workflow_sha256": workflow_sha,
    }


def audit_historical(repository_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repository_root)
    receipt = _verify_receipt(root)
    _verify_historical_receipts(root)
    return {
        "status": "PASSED",
        "receipt_sha256": receipt["canonical_sha256"],
        "source_receipt_sha256": receipt["source_receipt"]["canonical_sha256"],
        "bridge_receipt_sha256": receipt["bridge_receipt"]["canonical_sha256"],
    }


def audit_current(repository_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repository_root)
    receipt = _verify_receipt(root)
    _verify_historical_receipts(root)
    current = _verify_current_contract(receipt, root)
    return {
        "status": "PASSED",
        "policy_id": POLICY_ID,
        "receipt_sha256": receipt["canonical_sha256"],
        **current,
        "provider_acquisition_during_implementation": False,
        "workflow_dispatch_during_implementation": False,
        "live_retry": False,
    }


def audit(repository_root: str | Path = ".") -> dict[str, Any]:
    return audit_current(repository_root)


if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True))
