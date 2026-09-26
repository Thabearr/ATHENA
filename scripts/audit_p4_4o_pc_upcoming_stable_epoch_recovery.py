#!/usr/bin/env python3
"""Offline, fail-closed audit for the P4.4O pcUpcoming stable-epoch recovery."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from domain import current_shadow_all_market_runner as runner
from domain import current_shadow_fixture_identity_compatibility as compatibility
from domain import current_shadow_fixture_identity_v2 as identity_v2
from domain import current_shadow_sportybet_international_provider_family_bridge as bridge
from domain import current_shadow_sportybet_pc_upcoming_discovery as source
from domain import current_shadow_sportybet_pc_upcoming_reconciliation as runtime
from domain import current_shadow_sportybet_paginated_discovery_reconciliation as paginated
from domain import current_shadow_sportybet_catalog_fanout_reconciliation as fanout
from domain import current_shadow_sportybet_team_label_compatibility as team_labels
from domain import current_shadow_sportybet_upcoming_reconciliation as wap
from scripts import verify_p3_0_e1_live_readiness as p3


RECEIPT_PATH = Path("artifacts/architecture/p4_4o_pc_upcoming_stable_epoch_recovery_v1.json")
POLICY_ID = "ATHENA_P4_4O_PC_UPCOMING_STABLE_EPOCH_RECOVERY_V1"
BASE_MAIN_SHA = "a8c9776889b38ad412ac8887fa104f7546fad238"
OLD_RUNTIME_SHA256 = "fd203fc4b857bb3c5faa22536e87e1bc214cd4fdcf79ec5b6c4c681cd9d0cf73"
SOURCE_SHA256 = "63799058bec00abefb8d9b2ec9ba6dcad0c6e4775a54f17b07c0018e543ec075"
TEAM_LABEL_SHA256 = "0c382ec8b12d802879a51b766daae8f655dd5b371509653e56a13190a85c6c7b"
IDENTITY_COMPATIBILITY_SHA256 = "2fdbb8165262f6e633ee48276aea57c9235699272235798e1cef12fdc714ae04"
BRIDGE_SHA256 = "7db676111a9be06f63fd207815837d53699d6bf1a98364fc2163046cd1c0a4bb"
V2_SHA256 = "fc64fb0c2df3cee4f425158c48cfaada6757ba01e1759dd5b976ca899f85421e"
V2_SEED_SHA256 = "7fe662fc91a80daabf1e774ddd5c8ecdb5215eaf63adb03822b3fb05f872df79"
WAP_SHA256 = "dd1b4366ef2cf4d1e12359c42fbff5cbae8bef60cc06ca40589ec0e8a157f943"
PAGINATED_SHA256 = "7373a05c25466206aa3a67bc53b219e8d2841f432fda13db2dc0808b40b47238"
FANOUT_SHA256 = "c1ce52d8c441a6a38aee08c05413d579f0f18a497e56eb7833faf1fbc60c622f"
P44M_WORKFLOW_SHA256 = "45f7fe3556f892320a12b15c210637782edca60792ccbf030a714414a32f005a"
HISTORICAL_RECEIPTS = {
    "artifacts/architecture/post_p4_4l_pc_upcoming_shared_football_source_v1.json": {
        "raw_sha256": "8754e2e826e6783a85c38394354dcf80af61dafbc4f4ba6a467a3696166bbaff",
        "canonical_sha256": "8dde6427c296d966ff8d7f4cdec33e57a8c4210e8ecdb37071af68b0ca75bb34",
    },
    "artifacts/architecture/post_p4_4l_international_provider_family_bridge_v1.json": {
        "raw_sha256": "8e4c9af2993d7a0a3698176f17b4f73e99177003139d45f7e98d40dfa80fa495",
        "canonical_sha256": "34c183b5274e9e2c3320b5a8d75a123b7ebed2405aa55cdfb1af7d59c2613aa2",
    },
    "artifacts/architecture/post_p4_4l_pc_upcoming_runtime_migration_v1.json": {
        "raw_sha256": "1e4e302cff57719beca3db3402cc19526bae7bc056515c0b399473855ed14f30",
        "canonical_sha256": "09bbbb0842b0f92c214d5e868ec3fe5e2d047f9de7b5c3e6d620bc147092f6f3",
    },
    "artifacts/architecture/p4_4m_athena_run_pc_upcoming_evidence_preservation_v1.json": {
        "raw_sha256": "88c7c1423b81251515da0ca145fbbfd26040df4966da10b5a5d322aaf44aacb3",
        "canonical_sha256": "8202845b28abcea6ff8ea0ffb279a924b09ca7b2e5ab1d1918c957b757f345cf",
    },
    "artifacts/architecture/p4_4n_sportybet_team_label_shape_compatibility_v1.json": {
        "raw_sha256": "0cc979b15c7eff7e783563dbed30ea0901bbfc801fec6d419474f1a6f59f6314",
        "canonical_sha256": "3f08b29da1cfa782d897d8bad9ea8cb4c05a962e5402144d3982d7f7e3e47ec5",
    },
}


class P44OError(AssertionError):
    """Raised when the current recovery policy or historical ancestry drifts."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise P44OError(message)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise P44OError(f"required architecture evidence is unavailable: {path}") from exc
    _require(type(value) is dict, f"architecture receipt must be an object: {path}")
    return value


def _verify_receipt(root: Path) -> dict[str, Any]:
    value = _read_json(root / RECEIPT_PATH)
    semantic = dict(value)
    embedded = semantic.pop("canonical_sha256", None)
    actual = hashlib.sha256(_canonical(semantic)).hexdigest()
    _require(type(embedded) is str and embedded == actual, "P4.4O receipt canonical SHA mismatch")
    _require(value.get("schema_version") == 1 and value.get("policy_id") == POLICY_ID,
             "P4.4O receipt schema or policy identity drifted")
    _require(value.get("repository") == "Thabearr/ATHENA" and value.get("base_main_sha") == BASE_MAIN_SHA,
             "P4.4O base/repository identity drifted")
    _require(value.get("failed_proof_run") == 36245444226
             and value.get("failed_proof_artifact_id") == 10907222195
             and value.get("failed_proof_artifact_name") == "athena-run-36245444226"
             and value.get("failed_proof_artifact_zip_sha256") == "4fdffc9a9333e587175e4f90d4a5973ba0a6f858be8979ec40b489b981667aac"
             and value.get("failed_proof_evidence_comment_id") == 5846756520,
             "failed proof evidence identity drifted")
    page_evidence = value.get("retained_drift_pages")
    _require(page_evidence == [
        {"page_num": 1, "totalNum": 1053, "event_count": 100,
         "raw_sha256": "9a3626dba5eb96c509301e1f98275a7df2a29454a3cc2dbacf0db9a7b318d07d"},
        {"page_num": 2, "totalNum": 1052, "event_count": 100,
         "raw_sha256": "cc4bff10b3cea3e405e32acadf994b126e39f3a124149e20a5935f935d08d855"},
    ], "retained failed-run page evidence drifted")
    _require(value.get("recovery_policy") == {
        "recovery_semantics": "FRESH_CAPTURE_EPOCH_AFTER_EXACT_CROSS_PAGE_TOTALNUM_DRIFT",
        "exact_trigger": source.TOTALNUM_DRIFT_ERROR,
        "max_capture_epochs": 2,
        "max_pages_per_epoch": 20,
        "max_successful_page_responses": 40,
        "epoch_2_starts_at_page": 1,
        "no_per_page_http_retry": True,
        "no_third_epoch": True,
        "no_cross_epoch_event_merge": True,
        "failed_epoch_provider_absence_authority": False,
        "failed_epoch_identity_learning_authority": False,
        "failed_epoch_reconciliation_authority": False,
        "failed_epoch_selection_authority": False,
        "failed_epoch_pricing_authority": False,
        "failed_epoch_router_authority": False,
        "failed_epoch_portfolio_authority": False,
        "failed_epoch_delivery_authority": False,
        "accepted_epoch_independently_source_v1_verified": True,
        "accepted_epoch_independently_runtime_complete": True,
        "fallback": False,
        "workflow_retry": False,
        "provider_request_upper_bound": 40,
    }, "P4.4O bounded recovery semantics drifted")
    for key in (
        "provider_acquisition_during_implementation", "workflow_dispatch_during_implementation",
        "live_proof_during_implementation", "share_code_action", "wager_action",
    ):
        _require(value.get(key) is False, f"P4.4O implementation was not offline: {key}")
    for key in (
        "workflow_yaml_changed", "caller_migration", "workflow_retirement",
        "successor_proof_complete", "next_live_proof_authorized",
        "source_review_counter_reset", "p4_4_complete", "architecture_checkpoint_e_complete",
    ):
        _require(value.get(key) is False, f"P4.4O receipt overclaims scope/completion: {key}")
    _require(value.get("source_review_counter_while_unmerged") == "0/5"
             and value.get("source_review_counter_if_merged") == "1/5",
             "P4.4O source-review counter drifted")
    return value


def _verify_historical_receipts(root: Path, receipt: dict[str, Any]) -> None:
    if receipt.get("historical_receipts") != HISTORICAL_RECEIPTS:
        raise P44OError("historical receipt hash inventory drifted")
    for relative, expected in HISTORICAL_RECEIPTS.items():
        path = root / relative
        try:
            raw = path.read_bytes().replace(b"\r\n", b"\n")
            parsed = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise P44OError(f"immutable prior receipt is unavailable: {relative}") from exc
        if "raw_sha256" in expected:
            _require(hashlib.sha256(raw).hexdigest() == expected["raw_sha256"],
                     f"historical receipt bytes changed: {relative}")
        _require(parsed.get("canonical_sha256") == expected["canonical_sha256"],
                 f"historical receipt canonical identity changed: {relative}")
    from scripts import audit_p4_4n_sportybet_team_label_shape_compatibility as p44n
    historical = p44n.audit_historical(root)
    _require(historical.get("historical_runtime_wrapper_sha256") == OLD_RUNTIME_SHA256,
             "P4.4N historical runtime identity changed")


def _verify_current_contract(receipt: dict[str, Any], root: Path) -> None:
    runtime.validate_contract()
    _require(runtime.POLICY_ID == "ATHENA_CURRENT_SHADOW_PC_UPCOMING_DISCOVERY_RECONCILIATION_V1"
             and runtime.calculate_policy_sha256() == runtime.PINNED_POLICY_SHA256
             and runtime.PINNED_POLICY_SHA256 != OLD_RUNTIME_SHA256
             and receipt.get("current_runtime_policy_id") == runtime.POLICY_ID
             and receipt.get("runtime_policy_sha256_after") == runtime.PINNED_POLICY_SHA256,
             "current runtime wrapper is not the exact P4.4O supersession")
    stabilization = runtime._policy_payload().get("capture_stabilization")
    _require(stabilization == {
        "recovery_semantics": "FRESH_CAPTURE_EPOCH_AFTER_EXACT_CROSS_PAGE_TOTALNUM_DRIFT",
        "exact_first_epoch_trigger": source.TOTALNUM_DRIFT_ERROR,
        "max_capture_epochs": 2,
        "max_pages_per_epoch": 20,
        "max_successful_page_responses": 40,
        "each_epoch_starts_at_page": 1,
        "no_per_page_http_retry": True,
        "no_third_capture_epoch": True,
        "failed_epoch_provider_absence_authority": False,
        "failed_epoch_identity_learning_authority": False,
        "failed_epoch_reconciliation_authority": False,
        "failed_epoch_selection_authority": False,
        "failed_epoch_pricing_authority": False,
        "failed_epoch_router_authority": False,
        "failed_epoch_portfolio_authority": False,
        "failed_epoch_delivery_authority": False,
        "cross_epoch_event_merge": False,
        "accepted_epoch_independently_source_v1_verified": True,
        "accepted_epoch_independently_runtime_complete": True,
        "source_fallback": False,
        "all_attempt_evidence_retained_under_source_evidence_root": True,
        "workflow_retry": False,
        "per_page_transport_retry": False,
        "provider_request_upper_bound_is_finite": True,
    }, "runtime capture-stabilization policy drifted")
    _require(source.POLICY_ID == "ATHENA_CURRENT_SHADOW_PC_UPCOMING_GLOBAL_FOOTBALL_SOURCE_V1"
             and source.calculate_policy_sha256() == SOURCE_SHA256
             and source.PINNED_POLICY_SHA256 == SOURCE_SHA256,
             "PR #405 source V1 policy changed")
    _require(team_labels.EXPECTED_POLICY_SHA256 == TEAM_LABEL_SHA256
             and compatibility.EXPECTED_POLICY_SHA256 == IDENTITY_COMPATIBILITY_SHA256
             and bridge.PINNED_POLICY_SHA256 == BRIDGE_SHA256,
             "P4.4N or P4.4L identity ancestry changed")
    _require(identity_v2.REGISTRY_SHA256 == V2_SHA256
             and identity_v2.SEED_REGISTRY_SHA256 == V2_SEED_SHA256,
             "V2 semantic or seed registry changed")
    _require(wap.CURRENT_SHADOW_UPCOMING_COMPATIBILITY_SHA256 == WAP_SHA256
             and paginated.EXPECTED_CONTRACT_SHA256 == PAGINATED_SHA256
             and fanout.EXPECTED_CONTRACT_SHA256 == FANOUT_SHA256,
             "retained WAP/paginated/fanout contract changed")
    _require(runner.reconciliation is runtime and runner.upcoming_discovery is runtime,
             "Current Shadow runtime source owner changed")
    p3_contract = p3.check_f_upcoming_discovery_contract()
    _require(p3_contract.get("runtime_policy_id") == runtime.POLICY_ID
             and p3_contract.get("runtime_policy_sha256") == runtime.PINNED_POLICY_SHA256,
             "P3 source owner/runtime pin differs from Current Shadow")
    _require(runtime.AUTHORITY["model"] is False and runtime.AUTHORITY["pricing"] is False
             and runtime.AUTHORITY["router"] is False and runtime.AUTHORITY["portfolio"] is False
             and runtime.AUTHORITY["login"] is False and runtime.AUTHORITY["cookies"] is False
             and runtime.AUTHORITY["wallet"] is False and runtime.AUTHORITY["staking"] is False
             and runtime.AUTHORITY["bet"] is False and runtime.AUTHORITY["wager_placed"] is False,
             "runtime authority profile broadened")

    workflow_path = root / ".github/workflows/athena-run.yml"
    p4m = _read_json(root / "artifacts/architecture/p4_4m_athena_run_pc_upcoming_evidence_preservation_v1.json")
    try:
        workflow_sha = hashlib.sha256(workflow_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    except OSError as exc:
        raise P44OError("P4.4M workflow preservation contract is unavailable") from exc
    _require(workflow_sha == P44M_WORKFLOW_SHA256
             and p4m.get("workflow_after_identity", {}).get("source_sha256") == workflow_sha,
             "P4.4M workflow bytes changed")
    _require(value_has_preservation_root(workflow_path), "P4.4M active pcUpcoming evidence root is not preserved")


def value_has_preservation_root(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    return text.count(".cache/athena-research/current-shadow-sportybet-pc-upcoming-discovery") == 1


def audit(repository_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repository_root)
    receipt = _verify_receipt(root)
    _verify_historical_receipts(root, receipt)
    _verify_current_contract(receipt, root)
    return {
        "status": "PASSED",
        "policy_id": POLICY_ID,
        "receipt_sha256": receipt["canonical_sha256"],
        "runtime_policy_id": runtime.POLICY_ID,
        "runtime_policy_sha256": runtime.PINNED_POLICY_SHA256,
        "source_policy_sha256": source.PINNED_POLICY_SHA256,
        "team_label_policy_sha256": team_labels.EXPECTED_POLICY_SHA256,
        "identity_compatibility_sha256": compatibility.EXPECTED_POLICY_SHA256,
        "bridge_policy_sha256": bridge.PINNED_POLICY_SHA256,
        "v2_semantic_registry_sha256": identity_v2.REGISTRY_SHA256,
        "v2_seed_registry_sha256": identity_v2.SEED_REGISTRY_SHA256,
        "current_shadow_and_p3_shared_source": True,
        "workflow_yaml_changed": False,
        "provider_acquisition_during_implementation": False,
        "workflow_dispatch_during_implementation": False,
        "live_proof_during_implementation": False,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True))
