#!/usr/bin/env python3
"""Offline, fail-closed audit for P4.4P pre-parse response evidence."""
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


RECEIPT_PATH = Path("artifacts/architecture/p4_4p_pc_upcoming_preparse_response_evidence_v1.json")
POLICY_ID = "ATHENA_P4_4P_PC_UPCOMING_PREPARSE_RESPONSE_EVIDENCE_V1"
BASE_MAIN_SHA = "2b1fbb921840182b35b38ddf4ebe5ca05123c30e"
OLD_RUNTIME_SHA256 = "dac1f99da0b536b3808f8c7e41f66ad501101871d811131f8ede9e5dc99d4a5f"
NEW_RUNTIME_SHA256 = "a5c42439e894d33950b5cba608dcd5a031896e7a8e75c6bf613b2314497b1c24"
SOURCE_SHA256 = "63799058bec00abefb8d9b2ec9ba6dcad0c6e4775a54f17b07c0018e543ec075"
TEAM_LABEL_SHA256 = "0c382ec8b12d802879a51b766daae8f655dd5b371509653e56a13190a85c6c7b"
IDENTITY_SHA256 = "2fdbb8165262f6e633ee48276aea57c9235699272235798e1cef12fdc714ae04"
BRIDGE_SHA256 = "7db676111a9be06f63fd207815837d53699d6bf1a98364fc2163046cd1c0a4bb"
V2_SHA256 = "fc64fb0c2df3cee4f425158c48cfaada6757ba01e1759dd5b976ca899f85421e"
V2_SEED_SHA256 = "7fe662fc91a80daabf1e774ddd5c8ecdb5215eaf63adb03822b3fb05f872df79"
WAP_SHA256 = "dd1b4366ef2cf4d1e12359c42fbff5cbae8bef60cc06ca40589ec0e8a157f943"
PAGINATED_SHA256 = "7373a05c25466206aa3a67bc53b219e8d2841f432fda13db2dc0808b40b47238"
FANOUT_SHA256 = "c1ce52d8c441a6a38aee08c05413d579f0f18a497e56eb7833faf1fbc60c622f"
P44M_WORKFLOW_SHA256 = "45f7fe3556f892320a12b15c210637782edca60792ccbf030a714414a32f005a"
FAILED_PAGE_SHAS = [
    "0cc80da1fc346c6b9910b7e92df5fc47e99f15aea74d50572aac1edd9de8410d",
    "bbc4029c7f05d7cdd1855dbd5aab7bb09c08d7cebd58ff0db2e3adaff83c3fdf",
    "e5b07ff7673cb33bf68647962bd79df2624392a8adb260163051e8168afd6077",
    "c0ffcb86e9d409376697bb4f9e3c9a69ea0e107187354e757c6cb6a1f6459bd8",
    "3601bbffe342d77b23df28450619e4c1ba0145461505a8afa5310bf3ee6b2917",
    "e3e03b46e60b815bb2a47509aedbaf6bf17578f599bc0d906309664f95f4dc98",
]
HISTORICAL_RECEIPTS = {
    "artifacts/architecture/post_p4_4l_pc_upcoming_shared_football_source_v1.json": "8dde6427c296d966ff8d7f4cdec33e57a8c4210e8ecdb37071af68b0ca75bb34",
    "artifacts/architecture/post_p4_4l_international_provider_family_bridge_v1.json": "34c183b5274e9e2c3320b5a8d75a123b7ebed2405aa55cdfb1af7d59c2613aa2",
    "artifacts/architecture/post_p4_4l_pc_upcoming_runtime_migration_v1.json": "09bbbb0842b0f92c214d5e868ec3fe5e2d047f9de7b5c3e6d620bc147092f6f3",
    "artifacts/architecture/p4_4m_athena_run_pc_upcoming_evidence_preservation_v1.json": "8202845b28abcea6ff8ea0ffb279a924b09ca7b2e5ab1d1918c957b757f345cf",
    "artifacts/architecture/p4_4n_sportybet_team_label_shape_compatibility_v1.json": "3f08b29da1cfa782d897d8bad9ea8cb4c05a962e5402144d3982d7f7e3e47ec5",
    "artifacts/architecture/p4_4o_pc_upcoming_stable_epoch_recovery_v1.json": "766b8d54dec4310b60c032a26a51cdac0dbab436dbbd0ee81bb0f5cde4e4db3f",
}


class P44PError(AssertionError):
    """Raised when the P4.4P evidence contract or immutable ancestry drifts."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise P44PError(message)


def _read_json(root: Path, relative: str | Path) -> dict[str, Any]:
    path = root / relative
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise P44PError(f"required P4.4P evidence is unavailable: {relative}") from exc
    _require(type(value) is dict, f"P4.4P evidence must be an object: {relative}")
    return value


def _verify_receipt(root: Path) -> dict[str, Any]:
    receipt = _read_json(root, RECEIPT_PATH)
    semantic = dict(receipt)
    actual = semantic.pop("canonical_sha256", None)
    _require(type(actual) is str and actual == hashlib.sha256(_canonical(semantic)).hexdigest(),
             "P4.4P receipt canonical SHA mismatch")
    _require(receipt.get("schema_version") == 1 and receipt.get("policy_id") == POLICY_ID,
             "P4.4P receipt schema/policy identity drifted")
    _require(receipt.get("repository") == "Thabearr/ATHENA" and receipt.get("base_main_sha") == BASE_MAIN_SHA,
             "P4.4P base/repository identity drifted")
    _require(receipt.get("source_review_counter_while_unmerged") == "1/5"
             and receipt.get("source_review_counter_if_merged") == "2/5",
             "P4.4P source-review counter drifted")
    _require(receipt.get("failed_proof_run") == 36266310513
             and receipt.get("failed_proof_artifact_id") == 10913452949
             and receipt.get("failed_proof_artifact_name") == "athena-run-36266310513"
             and receipt.get("failed_proof_artifact_zip_sha256") == "6d64fa8e288b0d1eb5911f0774770009eb92580dcb746897d3c1be0e27195fef"
             and receipt.get("failed_proof_evidence_comment") == 5849306915
             and receipt.get("diagnosis_comment") == 5849361201,
             "failed proof/artifact/comment identity drifted")
    _require(receipt.get("failed_proof_classification") == (
        "POST_P4_4O_CANONICAL_SHADOW_SUCCESSOR_PROOF_INCOMPLETE:"
        "PC_UPCOMING_RUNTIME_SOURCE_INCOMPLETE_TOURNAMENT_ID_NOT_EXACT_PROVIDER_NATIVE_ID"
    ), "failed proof classification drifted")
    _require(receipt.get("failed_proof_exact_offending_response_preserved") is False
             and receipt.get("failed_proof_exact_offending_value_known") is False,
             "receipt overclaims unavailable failed-response evidence")
    _require(receipt.get("retained_partial_page_count") == 6
             and receipt.get("retained_partial_event_rows") == 600
             and receipt.get("retained_stable_total_num") == 757
             and receipt.get("required_page_count") == 8
             and receipt.get("retained_partial_page_sha256s") == FAILED_PAGE_SHAS,
             "six retained partial-page evidence anchors drifted")
    runtime_row = receipt.get("runtime_policy")
    _require(runtime_row == {
        "policy_id": runtime.POLICY_ID,
        "sha256_before": OLD_RUNTIME_SHA256,
        "sha256_after": NEW_RUNTIME_SHA256,
    }, "runtime policy before/after lineage drifted")
    unchanged = receipt.get("unchanged_contracts")
    _require(type(unchanged) is dict, "unchanged-contract lineage is absent")
    expected_unchanged = {
        "source_v1_policy": {"policy_id": source.POLICY_ID, "sha256_before": SOURCE_SHA256, "sha256_after": SOURCE_SHA256},
        "team_label_v6_sha256_before": TEAM_LABEL_SHA256,
        "team_label_v6_sha256_after": TEAM_LABEL_SHA256,
        "identity_compatibility_sha256_before": IDENTITY_SHA256,
        "identity_compatibility_sha256_after": IDENTITY_SHA256,
        "international_bridge_sha256_before": BRIDGE_SHA256,
        "international_bridge_sha256_after": BRIDGE_SHA256,
        "v2_semantic_registry_sha256_before": V2_SHA256,
        "v2_semantic_registry_sha256_after": V2_SHA256,
        "v2_seed_registry_sha256_before": V2_SEED_SHA256,
        "v2_seed_registry_sha256_after": V2_SEED_SHA256,
        "retained_wap_compatibility_sha256_before": WAP_SHA256,
        "retained_wap_compatibility_sha256_after": WAP_SHA256,
        "retained_paginated_contract_sha256_before": PAGINATED_SHA256,
        "retained_paginated_contract_sha256_after": PAGINATED_SHA256,
        "retained_fanout_contract_sha256_before": FANOUT_SHA256,
        "retained_fanout_contract_sha256_after": FANOUT_SHA256,
        "p4_4m_workflow_sha256_before": P44M_WORKFLOW_SHA256,
        "p4_4m_workflow_sha256_after": P44M_WORKFLOW_SHA256,
    }
    _require(unchanged == expected_unchanged, "unchanged contract hashes drifted")
    evidence = receipt.get("preparse_response_evidence")
    _require(evidence == {
        "pre_parse_raw_response_preservation": True,
        "parse_failure_receipt": True,
        "raw_response_observed_before_semantic_parse": True,
        "raw_response_path": "runtime-attempts/attempt-NNN/raw-responses/page-NNN.raw.json",
        "raw_response_journal": "runtime-attempts/attempt-NNN/raw-response-observations.json",
        "parse_failure_path": "runtime-attempts/attempt-NNN/parse-failure.json",
        "raw_response_exclusive_write_and_fsync": True,
        "mutable_journals_canonical_self_hash_and_atomic_replace": True,
        "semantic_parse_failure_acceptance": False,
        "invalid_provider_id_coercion": False,
        "parse_failure_fresh_epoch": False,
        "total_num_drift_fresh_epoch": True,
        "max_capture_epochs": 2,
        "fallback": False,
        "public_source_v1_capture_observer": False,
    }, "P4.4P raw-response evidence contract drifted")
    _require(receipt.get("historical_receipts_unchanged") == {
        "p4_4l_runtime_migration_canonical_sha256": HISTORICAL_RECEIPTS["artifacts/architecture/post_p4_4l_pc_upcoming_runtime_migration_v1.json"],
        "p4_4m_canonical_sha256": HISTORICAL_RECEIPTS["artifacts/architecture/p4_4m_athena_run_pc_upcoming_evidence_preservation_v1.json"],
        "p4_4n_canonical_sha256": HISTORICAL_RECEIPTS["artifacts/architecture/p4_4n_sportybet_team_label_shape_compatibility_v1.json"],
        "p4_4o_canonical_sha256": HISTORICAL_RECEIPTS["artifacts/architecture/p4_4o_pc_upcoming_stable_epoch_recovery_v1.json"],
    }, "historical receipt ancestry inventory drifted")
    _require(receipt.get("current_state_supersession") == {
        "p4_4o_historical_runtime_sha256": OLD_RUNTIME_SHA256,
        "p4_4p_runtime_sha256": NEW_RUNTIME_SHA256,
        "current_shadow_owner_changed": False,
        "p3_owner_changed": False,
    }, "P4.4O/P4.4P runtime supersession lineage drifted")
    _require(receipt.get("p4_4o_recovery_policy") == {
        "exact_trigger": source.TOTALNUM_DRIFT_ERROR,
        "max_capture_epochs": 2,
        "max_pages_per_epoch": 20,
        "max_successful_page_responses": 40,
        "second_epoch_starts_at_page": 1,
        "non_totalnum_parse_failure_starts_epoch": False,
        "no_third_epoch": True,
        "no_per_page_http_retry": True,
        "no_workflow_retry": True,
        "no_fallback": True,
        "cross_epoch_merge": False,
    }, "P4.4O exact recovery policy drifted")
    _require(receipt.get("authority_and_execution") == {
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
    }, "P4.4P receipt overclaims authority or completion")
    return receipt


def _verify_historical_receipts(root: Path) -> None:
    for relative, expected_canonical in HISTORICAL_RECEIPTS.items():
        value = _read_json(root, relative)
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
                 f"historical receipt canonical contents changed: {relative}")
    from scripts import audit_p4_4o_pc_upcoming_stable_epoch_recovery as p44o
    historical = p44o.audit_historical(root)
    _require(historical.get("historical_runtime_wrapper_sha256") == OLD_RUNTIME_SHA256,
             "P4.4O historical runtime pin changed")


def _verify_source_private_observer_order(root: Path) -> None:
    source_path = root / "domain/current_shadow_sportybet_pc_upcoming_discovery.py"
    try:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeError) as exc:
        raise P44PError("pcUpcoming source module cannot be parsed for observer ordering") from exc
    helper = next((node for node in tree.body if isinstance(node, ast.FunctionDef)
                   and node.name == "_capture_current_pc_upcoming_discovery_once"), None)
    public = next((node for node in tree.body if isinstance(node, ast.FunctionDef)
                   and node.name == "capture_current_pc_upcoming_discovery"), None)
    _require(helper is not None and public is not None, "source capture functions are absent")
    calls = [node for node in ast.walk(helper) if isinstance(node, ast.Call)]
    parse_lines = [node.lineno for node in calls if isinstance(node.func, ast.Name) and node.func.id == "parse_page"]
    observer_lines = [node.lineno for node in calls if isinstance(node.func, ast.Name) and node.func.id == "raw_response_observer"]
    _require(parse_lines and observer_lines and min(observer_lines) < min(parse_lines),
             "runtime pre-parse observer is not invoked before semantic parse")
    public_calls = [node for node in ast.walk(public) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "_capture_current_pc_upcoming_discovery_once"]
    _require(len(public_calls) == 1
             and all(keyword.arg != "raw_response_observer" for keyword in public_calls[0].keywords),
             "public source V1 capture was given runtime-only observation semantics")


def _verify_current_contract(receipt: dict[str, Any], root: Path) -> dict[str, Any]:
    # Kept as an internal compatibility seam for callers of the old audit.
    # P4.4P itself is historical; the exact P4.4Q receipt owns current pins.
    from scripts import audit_p4_4q_pc_upcoming_simple_tournament_identity as p44q
    current = p44q.audit_current(root)
    _require(receipt.get("runtime_policy", {}).get("sha256_after") == NEW_RUNTIME_SHA256
             and current.get("runtime_policy_sha256") == runtime.PINNED_POLICY_SHA256,
             "P4.4P historical runtime/P4.4Q current supersession chain drifted")
    return current


def audit_historical(repository_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repository_root)
    receipt = _verify_receipt(root)
    _verify_historical_receipts(root)
    return {"status": "PASSED", "receipt_sha256": receipt["canonical_sha256"],
            "failed_proof_exact_offending_value_known": False}


def audit_current(repository_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repository_root)
    receipt = _verify_receipt(root)
    _verify_historical_receipts(root)
    current = _verify_current_contract(receipt, root)
    return {
        "status": "PASSED",
        "policy_id": POLICY_ID,
        **current,
        "receipt_sha256": receipt["canonical_sha256"],
        "p4_4q_receipt_sha256": current.get("receipt_sha256"),
        "provider_acquisition_during_implementation": False,
        "workflow_dispatch_during_implementation": False,
        "live_retry": False,
    }


def audit(repository_root: str | Path = ".") -> dict[str, Any]:
    return audit_current(repository_root)


if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True))
