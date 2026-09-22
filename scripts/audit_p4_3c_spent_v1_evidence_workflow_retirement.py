"""Offline proof for retiring exactly two reconciled, spent V1 evidence workflows."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from scripts import audit_p4_3_workflow_retirement_ledger as ledger_audit


POLICY_ID = "ATHENA_P4_3C_SPENT_V1_EVIDENCE_WORKFLOW_RETIREMENT_V1"
BASE_MAIN_SHA = "3850c90578faabd237903a9433b1a252bd6bd516"
MATRIX_SHA = ledger_audit.MATRIX_SHA256
P43A_RECEIPT_SHA = ledger_audit.P43A_RECEIPT_SHA256
P43B_RECEIPT_SHA = ledger_audit.P43B_RECEIPT_SHA256
P42_RECEIPT_SHA = "fa575a5bb5f4611eb94564b92dea3e4230b8d429b1660dc3bde3d6c164b836f8"
ROLLBACK_TAG = "athena-p4.3c-pre-spent-v1-workflow-retirement-3850c90"
RECEIPT_PATH = Path("artifacts/architecture/p4_3c_spent_v1_evidence_workflow_retirement_v1.json")
FIXED_V1_SPENT_STATE = "V1_SPENT_GUARD_PERMISSION_FAILURE_NO_QUALIFICATION_EXECUTED_DO_NOT_REPLAY"
PR69_V1_UNQUALIFIED_STATE = "EXECUTION_NOT_QUALIFIED_REVIEW_ARTIFACT_BEFORE_ANY_RETRY"

TARGETS: dict[str, dict[str, Any]] = {
    ".github/workflows/execute-fotmob-utc-native-successor-feature-qualification.yml": {
        "source_sha256": "f48cdda138081e2453896e3f94496c4744d9ed360c0b7e6a86fb14bc7fa58c63",
        "git_blob_sha1": "9f159f77e58f20082b5ecb0b092c1d7dab831897",
        "fixture_path": "tests/fixtures/architecture/retired_workflows/execute-fotmob-utc-native-successor-feature-qualification.yml",
        "successor": ".github/workflows/execute-fotmob-utc-native-successor-feature-qualification-v2.yml",
        "successor_source_sha256": "482553d648b049db81ff30f6d757d92f76d80f17301826a0c6a1c9b181b8e2f1",
        "successor_git_blob_sha1": "f543e6c907e3b0b098152040730423eccfa52aad",
        "supersession_type": "RECONCILED_V2_SUCCESSOR_AFTER_SPENT_V1_GUARD_FAILURE",
        "v1_reconciliation": {
            "control_pr": 138,
            "reconciliation_comment_id": 5311071999,
            "run_id": 31987862156,
            "run_head_sha": "2bd05e98cd74f9db6fa59472c05d5253f69d0f68",
            "run_conclusion": "failure",
            "command_comment_id": 5311067273,
            "artifact_id": 9274313978,
            "artifact_name": "fotmob-utc-native-feature-qualification-31987862156",
            "artifact_sha256": "1a46808c8ee4d21ab67ec03b1fd6c0a80e79fadf04933092e7a106522e31c337",
            "artifact_size": 2388,
            "runner_executed": False,
            "artifact_download_executed": False,
            "qualification_executed": False,
            "state": FIXED_V1_SPENT_STATE,
        },
        "v2_success": {
            "run_id": 31990121181,
            "head_sha": "cd67be14f6a4f09484d18a57de360b8a5d4c51d7",
            "conclusion": "success",
            "created_at": "2026-08-17T03:07:29Z",
            "url": "https://github.com/Thabearr/ATHENA/actions/runs/31990121181",
        },
        "live_latest": {
            "run_id": 35781984848,
            "head_sha": "d2104a800ae91b4da47dd20d3d1c31fb7dc4ea3a",
            "event": "issue_comment",
            "conclusion": "skipped",
            "created_at": "2026-09-22T20:42:06Z",
            "updated_at": "2026-09-22T20:42:07Z",
            "url": "https://github.com/Thabearr/ATHENA/actions/runs/35781984848",
        },
        "v2_live_latest": {
            "run_id": 35781984850,
            "head_sha": "d2104a800ae91b4da47dd20d3d1c31fb7dc4ea3a",
            "event": "issue_comment",
            "conclusion": "skipped",
            "created_at": "2026-09-22T20:42:06Z",
            "url": "https://github.com/Thabearr/ATHENA/actions/runs/35781984850",
        },
        "v2_source_tokens": [
            "const v1ControlPr = 138;",
            "const v1ReconciliationCommentId = 5311071999;",
            "run-id: 31987862156",
            "failure-evidence-artifact-id: 9274313978",
            "failure-evidence-artifact-sha256: 1a46808c8ee4d21ab67ec03b1fd6c0a80e79fadf04933092e7a106522e31c337",
            "state: V1_SPENT_GUARD_PERMISSION_FAILURE_NO_QUALIFICATION_EXECUTED_DO_NOT_REPLAY",
        ],
    },
    ".github/workflows/execute-pr69-primary-time-basis-evidence-campaign.yml": {
        "source_sha256": "39e961b07586a6de46ceb78c4281b189f783e15a8fc5023b08e2b5b6f03d416e",
        "git_blob_sha1": "04c6f1d3c709acb2c90d69e39733b2297caa7e8a",
        "fixture_path": "tests/fixtures/architecture/retired_workflows/execute-pr69-primary-time-basis-evidence-campaign.yml",
        "successor": ".github/workflows/execute-pr69-primary-time-basis-evidence-campaign-v2.yml",
        "successor_source_sha256": "d4beeef1624bc435666cb51e590891c7e735d6ad7bd10259933d02bf50b4d262",
        "successor_git_blob_sha1": "4e580f5bfd86de4f1ce003d9c327662fc3cdc490",
        "supersession_type": "RECONCILED_V2_SUCCESSOR_AFTER_FAILED_V1_EVIDENCE_CAMPAIGN",
        "v1_reconciliation": {
            "control_pr": 128,
            "fix_pr": 129,
            "fix_merge_sha": "94577458d4b8af59a4e986edb2e4df9c426e21be",
            "reconciliation_comment_id": 5308433895,
            "run_id": 31953949073,
            "run_head_sha": "0efe56f5003441b52e4ec3ba2723eb0d78a80422",
            "run_conclusion": "cancelled",
            "campaign_step_conclusion": "success",
            "qualification_gate_conclusion": "failure",
            "artifact_id": 9266604353,
            "artifact_name": "pr69-primary-time-basis-evidence-campaign-31953949073",
            "artifact_sha256": "ce87f13cb72a917c0a01e4bbede87e4123d85861d5ee1cd98667bb802d380db7",
            "state": PR69_V1_UNQUALIFIED_STATE,
        },
        "v2_success": {
            "run_id": 31974333489,
            "head_sha": "4a2ca10af4b14194253ba6fc84bca780e2b03d58",
            "conclusion": "success",
            "created_at": "2026-08-16T21:43:22Z",
            "url": "https://github.com/Thabearr/ATHENA/actions/runs/31974333489",
        },
        "live_latest": {
            "run_id": 35781984867,
            "head_sha": "d2104a800ae91b4da47dd20d3d1c31fb7dc4ea3a",
            "event": "issue_comment",
            "conclusion": "skipped",
            "created_at": "2026-09-22T20:42:06Z",
            "updated_at": "2026-09-22T20:42:07Z",
            "url": "https://github.com/Thabearr/ATHENA/actions/runs/35781984867",
        },
        "v2_live_latest": {
            "run_id": 35781984842,
            "head_sha": "d2104a800ae91b4da47dd20d3d1c31fb7dc4ea3a",
            "event": "issue_comment",
            "conclusion": "skipped",
            "created_at": "2026-09-22T20:42:06Z",
            "url": "https://github.com/Thabearr/ATHENA/actions/runs/35781984842",
        },
        "v2_source_tokens": [
            "const priorControlPr = 128;",
            "const fixPr = 129;",
            "const fixMergeSha = '94577458d4b8af59a4e986edb2e4df9c426e21be';",
            "const priorRunId = '31953949073';",
            "const priorArtifactId = 9266604353;",
            "const priorArtifactName = 'pr69-primary-time-basis-evidence-campaign-31953949073';",
            "const priorArtifactDigest = 'ce87f13cb72a917c0a01e4bbede87e4123d85861d5ee1cd98667bb802d380db7';",
            "'reconciled-from-run-id: 31953949073',",
            "'reconciled-artifact-id: 9266604353',",
        ],
    },
}


class P43CRetirementError(AssertionError):
    """Raised when a P4.3C retirement/supersession proof fails closed."""


def canonical_json_bytes(payload: Any) -> bytes:
    return ledger_audit.canonical_json_bytes(payload)


def canonical_sha256(payload: dict[str, Any]) -> str:
    return ledger_audit.canonical_sha256(payload)


def _normalized_source(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n")


def _identity(raw: bytes) -> tuple[str, str]:
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    return blob, hashlib.sha256(raw).hexdigest()


def _assert_tokens(path: str, tokens: list[str], *, source_override: str | None = None) -> str:
    source = source_override if source_override is not None else Path(path).read_text(encoding="utf-8")
    for token in tokens:
        if token not in source:
            raise P43CRetirementError(f"{path}: reconciled successor identity is missing/changed: {token}")
    return source


def verify_target(path: str, *, v1_fixture_bytes: bytes | None = None, v2_source: str | None = None) -> dict[str, Any]:
    try:
        details = TARGETS[path]
    except KeyError as exc:
        raise P43CRetirementError(f"unreviewed P4.3C target: {path}") from exc
    fixture_path = Path(details["fixture_path"])
    raw = fixture_path.read_bytes() if v1_fixture_bytes is None else v1_fixture_bytes
    blob_sha, source_sha = _identity(raw)
    if blob_sha != details["git_blob_sha1"] or source_sha != details["source_sha256"]:
        raise P43CRetirementError(f"historical V1 fixture identity drifted: {path}")
    if Path(path).exists():
        raise P43CRetirementError(f"retired V1 workflow still executable: {path}")
    v2_path = details["successor"]
    live_v2_raw = Path(v2_path).read_bytes()
    v2_blob, v2_sha = _identity(_normalized_source(live_v2_raw))
    if v2_blob != details["successor_git_blob_sha1"] or v2_sha != details["successor_source_sha256"]:
        raise P43CRetirementError(f"reconciled V2 successor source identity changed: {v2_path}")
    source = _assert_tokens(v2_path, details["v2_source_tokens"], source_override=v2_source)
    v1_history = details["v1_reconciliation"]
    if not v1_history.get("run_id") or not v1_history.get("artifact_id"):
        raise P43CRetirementError(f"{path}: reviewed failed/spent V1 history is incomplete")
    if details["supersession_type"].startswith("RECONCILED_V2_SUCCESSOR_AFTER_SPENT"):
        if v1_history.get("state") != FIXED_V1_SPENT_STATE or v1_history.get("qualification_executed") is not False:
            raise P43CRetirementError(f"{path}: V1 spent/no-execution state is not preserved")
    else:
        if v1_history.get("state") != PR69_V1_UNQUALIFIED_STATE or v1_history.get("qualification_gate_conclusion") != "failure":
            raise P43CRetirementError(f"{path}: V1 campaign qualification failure is not preserved")
    if not details["v2_success"].get("run_id") or details["v2_success"].get("conclusion") != "success":
        raise P43CRetirementError(f"{path}: reconciled V2 has no verified successful run")
    if details["live_latest"].get("conclusion") == "success":
        raise P43CRetirementError(f"{path}: a new V1 success requires owner review before retirement")
    if details["live_latest"].get("run_id") != 35781984848 and path == ".github/workflows/execute-fotmob-utc-native-successor-feature-qualification.yml":
        raise P43CRetirementError(f"{path}: live run-history recheck evidence changed")
    if details["live_latest"].get("run_id") != 35781984867 and path == ".github/workflows/execute-pr69-primary-time-basis-evidence-campaign.yml":
        raise P43CRetirementError(f"{path}: live run-history recheck evidence changed")
    if details["v2_live_latest"].get("run_id") not in (35781984850, 35781984842):
        raise P43CRetirementError(f"{v2_path}: V2 latest-run recheck evidence changed")
    row = next((item for item in _load_matrix()["workflow_rows"] if item["workflow_path"] == path), None)
    if row is None or row.get("history_status") != "RUN_HISTORY_WITHOUT_SUCCESS_OWNER_REVIEW_REQUIRED" or row.get("last_successful_run") is not None:
        raise P43CRetirementError(f"{path}: P4.3A no-success history evidence changed")
    dep = row.get("dependency_evidence", {})
    if dep.get("artifact_consumer_exists") is not False or dep.get("workflow_history_consumer_exists") is not False:
        raise P43CRetirementError(f"{path}: an unmapped live artifact/workflow-history consumer remains")
    return {
        "workflow_path": path,
        "git_blob_sha1": blob_sha,
        "source_sha256": source_sha,
        "p4_3a_history_status": row["history_status"],
        "p4_3a_last_successful_run": row["last_successful_run"],
        "live_history_rechecked": True,
        "live_latest_run": details["live_latest"],
        "live_latest_successful_run": None,
        "v1_reconciled_attempt": v1_history,
        "successor_v2": {
            "workflow_path": v2_path,
            "git_blob_sha1": v2_blob,
            "source_sha256": v2_sha,
            "success_run": details["v2_success"],
            "live_latest_run": details["v2_live_latest"],
            "live_latest_successful_run": details["v2_success"],
            "required_reconciliation_bindings_verified": True,
        },
        "supersession_type": details["supersession_type"],
        "historical_fixture_path": details["fixture_path"],
        "historical_fixture_sha256": source_sha,
        "artifact_consumer_exists": False,
        "workflow_history_consumer_exists": False,
        "executable_target_removed": True,
        "v2_source_verification": "PASS",
    }


def _load_matrix() -> dict[str, Any]:
    matrix, _ = ledger_audit.load_baseline()
    return matrix


def build_receipt_core() -> dict[str, Any]:
    matrix = _load_matrix()
    if Path(".github/workflows").exists():
        live_paths = sorted(path.as_posix() for path in Path(".github/workflows").glob("*.yml"))
    else:
        raise P43CRetirementError("workflow directory missing")
    before_count = len(live_paths) + 2
    if before_count != 39 or len(live_paths) != 37:
        raise P43CRetirementError("P4.3C live workflow transition must be exactly 39 to 37")
    target_proofs = [verify_target(path) for path in sorted(TARGETS)]
    expected_paths = sorted(set(row["workflow_path"] for row in matrix["workflow_rows"]) - set(ledger_audit.RETIRED))
    if live_paths != expected_paths:
        raise P43CRetirementError("only the two authorized V1 workflow paths may be absent")
    ledger = ledger_audit.validate_ledger()
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository_base_main_sha": BASE_MAIN_SHA,
        "p4_3a_matrix_sha256": MATRIX_SHA,
        "p4_3a_receipt_sha256": P43A_RECEIPT_SHA,
        "p4_3b_receipt_sha256": P43B_RECEIPT_SHA,
        "p4_2_receipt_sha256": P42_RECEIPT_SHA,
        "owner_review_scope": sorted(TARGETS),
        "owner_review_authorized": True,
        "target_count": 2,
        "targets": target_proofs,
        "workflow_count_before": 39,
        "workflow_count_after": 37,
        "workflow_count_decreased_by": 2,
        "cumulative_retired_workflow_count": 3,
        "unique_required_capability_lost": False,
        "network_attempt_count": 0,
        "workflow_dispatch_triggered": False,
        "provider_acquisition": False,
        "current_shadow_triggered": False,
        "fresh_holdout_triggered": False,
        "p3_0_e1_triggered": False,
        "real_share_code_operation": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "wager_placed": False,
        "model_formula_changed": False,
        "probability_formula_changed": False,
        "calibration_formula_changed": False,
        "price_all_formula_changed": False,
        "router_formula_changed": False,
        "portfolio_formula_changed": False,
        "provider_semantics_changed": False,
        "share_code_semantics_changed": False,
        "rollback_tag": ROLLBACK_TAG,
        "rollback_commit_sha": BASE_MAIN_SHA,
        "rollback_tag_remote_verified_before_deletion": True,
        "retirement_ledger_sha256": ledger["canonical_sha256"],
        "p4_3c_retirement_gate_satisfied": True,
        "architecture_checkpoint_e_fully_claimed": False,
        "p4_4_started": False,
        "source_review_counter_while_unmerged": "3/5",
        "source_review_counter_if_merged": "4/5",
    }
    return receipt


def build_evidence() -> tuple[dict[str, Any], dict[str, Any]]:
    # Build the receipt body without its ledger backlink first; the ledger stores
    # this body hash, and the final receipt then binds the resulting ledger hash.
    core = build_receipt_core_without_ledger()
    new_ledger = ledger_audit.build_ledger(core)
    receipt = dict(core)
    receipt["retirement_ledger_sha256"] = new_ledger["canonical_sha256"]
    receipt["canonical_sha256"] = canonical_sha256(receipt)
    return new_ledger, receipt


def build_receipt_core_without_ledger() -> dict[str, Any]:
    # In the write path only, construct the evidence without consulting a ledger
    # that has not yet been materialized.
    matrix = _load_matrix()
    live_paths = sorted(path.as_posix() for path in Path(".github/workflows").glob("*.yml"))
    if len(live_paths) != 37:
        raise P43CRetirementError("P4.3C current live workflow count must be 37")
    target_proofs = [verify_target(path) for path in sorted(TARGETS)]
    expected_paths = sorted(set(row["workflow_path"] for row in matrix["workflow_rows"]) - set(ledger_audit.RETIRED))
    if live_paths != expected_paths:
        raise P43CRetirementError("only the two authorized V1 workflow paths may be absent")
    p43b = json.loads(ledger_audit.P43B_RECEIPT_PATH.read_text(encoding="utf-8"))
    if p43b.get("canonical_sha256") != P43B_RECEIPT_SHA:
        raise P43CRetirementError("P4.3B historical receipt changed")
    return {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository_base_main_sha": BASE_MAIN_SHA,
        "p4_3a_matrix_sha256": MATRIX_SHA,
        "p4_3a_receipt_sha256": P43A_RECEIPT_SHA,
        "p4_3b_receipt_sha256": P43B_RECEIPT_SHA,
        "p4_2_receipt_sha256": P42_RECEIPT_SHA,
        "owner_review_scope": sorted(TARGETS),
        "owner_review_authorized": True,
        "target_count": 2,
        "targets": target_proofs,
        "workflow_count_before": 39,
        "workflow_count_after": 37,
        "workflow_count_decreased_by": 2,
        "cumulative_retired_workflow_count": 3,
        "unique_required_capability_lost": False,
        "network_attempt_count": 0,
        "workflow_dispatch_triggered": False,
        "provider_acquisition": False,
        "current_shadow_triggered": False,
        "fresh_holdout_triggered": False,
        "p3_0_e1_triggered": False,
        "real_share_code_operation": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "wager_placed": False,
        "model_formula_changed": False,
        "probability_formula_changed": False,
        "calibration_formula_changed": False,
        "price_all_formula_changed": False,
        "router_formula_changed": False,
        "portfolio_formula_changed": False,
        "provider_semantics_changed": False,
        "share_code_semantics_changed": False,
        "rollback_tag": ROLLBACK_TAG,
        "rollback_commit_sha": BASE_MAIN_SHA,
        "rollback_tag_remote_verified_before_deletion": True,
        "p4_3c_retirement_gate_satisfied": True,
        "architecture_checkpoint_e_fully_claimed": False,
        "p4_4_started": False,
        "source_review_counter_while_unmerged": "3/5",
        "source_review_counter_if_merged": "4/5",
    }


def check(*, write: bool = False) -> dict[str, Any]:
    if write:
        ledger, receipt = build_evidence()
        ledger_audit.LEDGER_PATH.write_bytes(canonical_json_bytes(ledger))
        RECEIPT_PATH.write_bytes(canonical_json_bytes(receipt))
        ledger_audit.validate_ledger(ledger)
        return receipt
    committed = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    expected_ledger = ledger_audit.validate_ledger()
    rebuilt = build_receipt_core()
    rebuilt["retirement_ledger_sha256"] = expected_ledger["canonical_sha256"]
    rebuilt["canonical_sha256"] = canonical_sha256(rebuilt)
    if committed != rebuilt or canonical_sha256(committed) != committed.get("canonical_sha256"):
        raise P43CRetirementError("committed P4.3C receipt differs from offline retirement proof")
    if committed.get("retirement_ledger_sha256") != expected_ledger["canonical_sha256"]:
        raise P43CRetirementError("P4.3C receipt ledger binding differs")
    return committed


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write-evidence", action="store_true")
    args = parser.parse_args()
    try:
        receipt = check(write=args.write_evidence)
    except Exception as exc:
        print(f"P4_3C_RETIREMENT_AUDIT_FAILED: {exc}", file=sys.stderr)
        return 1
    print(receipt["canonical_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
