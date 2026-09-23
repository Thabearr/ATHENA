"""Offline P4.3D audit-lifecycle checkpoint and extensibility proof."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts import (
    audit_p4_2_athena_run_workflow as p42_audit,
    audit_p4_3_workflow_retirement_ledger as ledger_audit,
    audit_p4_3a_workflow_capability_census as p43a_audit,
    audit_p4_3b_current_sportybet_workflow_retirement as p43b_audit,
    audit_p4_3c_spent_v1_evidence_workflow_retirement as p43c_audit,
)


POLICY_ID = "ATHENA_P4_3D_RETIREMENT_AUDIT_EXTENSIBILITY_V1"
BASE_MAIN_SHA = "0033f5daf96bcc580be015f5eb001326a4467757"
P42_SHA = "fa575a5bb5f4611eb94564b92dea3e4230b8d429b1660dc3bde3d6c164b836f8"
P43A_MATRIX_SHA = "6b417a19557efdd39201e233fb866e4143b8102ba2879a4f1481e5241722dd8d"
P43A_RECEIPT_SHA = "7dd102aa4da98d634d665b4a93f51eb24ece8d7b61c8856b9977ff84a7452a6b"
P43B_SHA = "cf2371c7ec2747256f23599e7a43dd2d9e46ff61dda2c478a746d8bd8a49e72a"
P43C_SHA = "c4afd0d0052c7b14d643f7868d7eac85344042da20a9d7aa0e8bf3b59ab9bd24"
LEDGER_SHA = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
BASE_MAIN_WORKFLOW_TREE_SHA1 = "6391a5a17b9925c91849a758852915d509a64703"
SNAPSHOT_PATH = ledger_audit.P43C_LEDGER_SNAPSHOT_PATH
RECEIPT_PATH = Path("artifacts/architecture/p4_3d_retirement_audit_extensibility_v1.json")
LEDGER_PATH = ledger_audit.LEDGER_PATH
FROZEN_CANONICAL_FILES = {
    "artifacts/architecture/p4_2_athena_run_workflow_v1.json": P42_SHA,
    "artifacts/architecture/p4_3_workflow_capability_matrix_v1.json": P43A_MATRIX_SHA,
    "artifacts/architecture/p4_3a_workflow_capability_census_v1.json": P43A_RECEIPT_SHA,
    "artifacts/architecture/p4_3b_current_sportybet_workflow_retirement_v1.json": P43B_SHA,
    "artifacts/architecture/p4_3c_spent_v1_evidence_workflow_retirement_v1.json": P43C_SHA,
    "artifacts/architecture/p4_3_workflow_retirement_ledger_v1.json": LEDGER_SHA,
}
FROZEN_GIT_BLOBS = {
    "artifacts/architecture/p4_2_athena_run_workflow_v1.json": "6bbaa431c4a4fa42e4845f70045b75c319e27193",
    "artifacts/architecture/p4_3_workflow_capability_matrix_v1.json": "918c27faabe07a8711117e7cd3dbbb768b49158f",
    "artifacts/architecture/p4_3a_workflow_capability_census_v1.json": "ba417487dd9fd55aafc1011d8393fa13a43e5780",
    "artifacts/architecture/p4_3b_current_sportybet_workflow_retirement_v1.json": "51d57acbab449826cafa4bd91987bd55066b26ef",
    "artifacts/architecture/p4_3c_spent_v1_evidence_workflow_retirement_v1.json": "754d8211546c2c3c7ffe1398141c0b88281e5406",
    "artifacts/architecture/p4_3_workflow_retirement_ledger_v1.json": "a46cb2a50fd9398931da94533f7a67fb237a0f9e",
}


class P43DRetirementAuditError(AssertionError):
    """Raised when frozen retirement evidence or current accounting drifts."""


def _git(*args: str) -> bytes:
    result = subprocess.run(["git", *args], capture_output=True)
    if result.returncode:
        raise P43DRetirementAuditError(
            f"git {' '.join(args)} failed: {result.stderr.decode('utf-8', 'replace')}"
        )
    return result.stdout


def _blob(commit: str, path: str) -> str:
    path = path.replace("\\", "/")
    return _git("rev-parse", f"{commit}:{path}").decode("ascii").strip()


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _live_paths_at(commit: str) -> list[str]:
    return sorted(
        item.decode("utf-8")
        for item in _git("ls-tree", "-r", "-z", "--name-only", commit).split(b"\0")
        if item and item.decode("utf-8").startswith(".github/workflows/") and item.decode("utf-8").endswith(".yml")
    )


def _live_workflow_proof(ledger: dict[str, Any]) -> dict[str, str]:
    paths = sorted(path.as_posix() for path in Path(".github/workflows").glob("*.yml"))
    baseline_rows = ledger_audit.load_baseline()[0]["workflow_rows"]
    baseline_paths = {row["workflow_path"] for row in baseline_rows}
    if paths != sorted(baseline_paths - set(ledger["retired_workflow_paths"])):
        raise P43DRetirementAuditError("live workflow set is not baseline minus the reviewed ledger paths")
    if len(paths) != ledger["current_live_workflow_count"]:
        raise P43DRetirementAuditError("live workflow count differs from the cumulative ledger")
    head_paths = _live_paths_at("HEAD")
    if paths != head_paths:
        raise P43DRetirementAuditError("live workflow tree differs from the checkout tree")
    workflow_tree = _git("rev-parse", "HEAD:.github/workflows").decode("ascii").strip()
    if workflow_tree != BASE_MAIN_WORKFLOW_TREE_SHA1:
        raise P43DRetirementAuditError("live workflow tree differs from the frozen P4.3D base-main tree identity")
    if _git("diff", "--name-only", "--", ".github/workflows"):
        raise P43DRetirementAuditError("working-tree workflow YAML diff must be empty")
    blobs: dict[str, str] = {}
    baseline_blobs = {row["workflow_path"]: row["git_blob_sha1"] for row in baseline_rows}
    for path in paths:
        head_blob = _blob("HEAD", path)
        if baseline_blobs.get(path) != head_blob:
            raise P43DRetirementAuditError(f"live workflow blob differs from the frozen P4.3A identity: {path}")
        blobs[path] = head_blob
    return blobs


def _validate_frozen_files() -> dict[str, str]:
    blobs: dict[str, str] = {}
    for path, expected_sha in FROZEN_CANONICAL_FILES.items():
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise P43DRetirementAuditError(f"frozen evidence is unreadable: {path}") from exc
        if payload.get("canonical_sha256") != expected_sha or ledger_audit.canonical_sha256(payload) != expected_sha:
            raise P43DRetirementAuditError(f"frozen evidence canonical SHA changed: {path}")
        head_blob = _blob("HEAD", path)
        if head_blob != FROZEN_GIT_BLOBS[path]:
            raise P43DRetirementAuditError(f"frozen historical artifact blob differs from the P4.3D base pin: {path}")
        if _git("diff", "--name-only", "--", path):
            raise P43DRetirementAuditError(f"frozen historical artifact has a working-tree diff: {path}")
        blobs[path] = head_blob
    return blobs


def _validate_snapshot_and_ledger() -> tuple[dict[str, Any], dict[str, Any]]:
    ledger = ledger_audit.validate_ledger()
    try:
        snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise P43DRetirementAuditError("P4.3C historical ledger snapshot is unreadable") from exc
    if snapshot.get("canonical_sha256") != LEDGER_SHA or ledger_audit.canonical_sha256(snapshot) != LEDGER_SHA:
        raise P43DRetirementAuditError("P4.3C ledger snapshot canonical identity changed")
    if snapshot.get("current_retired_workflow_count") != 3 or snapshot.get("current_live_workflow_count") != 37:
        raise P43DRetirementAuditError("P4.3C ledger snapshot must remain 3 retired / 37 live")
    if snapshot.get("canonical_sha256") != p43c_audit.P43C_LEDGER_SNAPSHOT_SHA:
        raise P43DRetirementAuditError("P4.3C snapshot SHA differs from the frozen receipt backlink")
    current_bytes = LEDGER_PATH.read_bytes()
    snapshot_bytes = SNAPSHOT_PATH.read_bytes()
    if current_bytes != snapshot_bytes:
        raise P43DRetirementAuditError("P4.3C snapshot must byte-match the unchanged current ledger at this checkpoint")
    current_ledger_blob = _blob("HEAD", LEDGER_PATH.as_posix())
    if current_ledger_blob != FROZEN_GIT_BLOBS[LEDGER_PATH.as_posix()]:
        raise P43DRetirementAuditError("current retirement ledger Git blob changed from base main")
    snapshot_blob = _git(
        "hash-object",
        f"--path={LEDGER_PATH.as_posix()}",
        str(SNAPSHOT_PATH).replace("\\", "/"),
    ).decode("ascii").strip()
    if FROZEN_GIT_BLOBS[LEDGER_PATH.as_posix()] != snapshot_blob:
        raise P43DRetirementAuditError("snapshot Git blob does not preserve the exact base ledger blob")
    ledger_audit.validate_historical_snapshot_extension(snapshot, ledger)
    return snapshot, ledger


def _assert_p43a_count_is_ledger_derived() -> None:
    source = Path("scripts/audit_p4_3a_workflow_capability_census.py").read_text(encoding="utf-8")
    if "expected_current_count = 40 - len(retired_paths)" not in source:
        raise P43DRetirementAuditError("P4.3A current count is not derived from the validated ledger")
    if any(marker in source for marker in ("len(surviving_paths) != 37", "len(worktree_paths) != 37", "current workflow counts are not 40/37")):
        raise P43DRetirementAuditError("P4.3A auditor still hardcodes current workflow count 37")


def build_receipt() -> dict[str, Any]:
    frozen_blobs = _validate_frozen_files()
    snapshot, ledger = _validate_snapshot_and_ledger()
    if len(ledger["retirements"]) != 3 or ledger["current_live_workflow_count"] != 37:
        raise P43DRetirementAuditError("P4.3D must preserve the 3-retired / 37-live checkpoint")
    workflow_blobs = _live_workflow_proof(ledger)
    _assert_p43a_count_is_ledger_derived()
    p43a_receipt = p43a_audit.check(write_receipt=False)
    p43b_receipt = p43b_audit.check()
    p43c_receipt = p43c_audit.check()
    p42_audit.verify_committed_receipt()
    p42_audit.verify_preserved_historical_sources()
    p42_audit.verify_retired_workflow_historical_fixtures()
    try:
        p43c_audit.check(write=True)
    except p43c_audit.P43CRetirementError as exc:
        if "write mode is disabled" not in str(exc):
            raise P43DRetirementAuditError("P4.3C write/regeneration disablement changed") from exc
    else:
        raise P43DRetirementAuditError("P4.3C historical write mode unexpectedly succeeded")
    if p43a_receipt["canonical_sha256"] != P43A_RECEIPT_SHA or p43b_receipt["canonical_sha256"] != P43B_SHA or p43c_receipt["canonical_sha256"] != P43C_SHA:
        raise P43DRetirementAuditError("a frozen prior P4 receipt identity changed")

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository_base_main_sha": BASE_MAIN_SHA,
        "base_main_workflow_tree_sha1": BASE_MAIN_WORKFLOW_TREE_SHA1,
        "p4_2_receipt_sha256": P42_SHA,
        "p4_3a_matrix_sha256": P43A_MATRIX_SHA,
        "p4_3a_receipt_sha256": P43A_RECEIPT_SHA,
        "p4_3b_receipt_sha256": P43B_SHA,
        "p4_3c_receipt_sha256": P43C_SHA,
        "current_retirement_ledger_sha256": ledger["canonical_sha256"],
        "p4_3c_ledger_snapshot_path": SNAPSHOT_PATH.as_posix(),
        "p4_3c_ledger_snapshot_sha256": snapshot["canonical_sha256"],
        "p4_3c_snapshot_byte_identical_to_checkpoint_ledger": True,
        "live_workflow_count_before": 37,
        "live_workflow_count_after": len(workflow_blobs),
        "retired_workflow_count_before": 3,
        "retired_workflow_count_after": len(ledger["retirements"]),
        "live_workflow_git_blobs": workflow_blobs,
        "frozen_historical_git_blobs": FROZEN_GIT_BLOBS,
        "frozen_evidence_git_blobs": frozen_blobs,
        "workflow_yaml_changed": False,
        "workflow_added": False,
        "workflow_deleted": False,
        "retirement_performed": False,
        "p4_3a_current_count_hardcoding_removed": True,
        "p4_3c_receipt_regeneration_disabled": True,
        "p4_3c_binds_historical_ledger_snapshot": True,
        "current_ledger_monotonic_extension_validation_added": True,
        "reviewed_source_resolver_added": True,
        "historical_snapshot_extension_equality_passed": True,
        "synthetic_future_extension_supported": True,
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
        "architecture_checkpoint_e_fully_claimed": False,
        "p4_4_started": False,
        "source_review_counter_while_unmerged": "4/5",
        "source_review_counter_if_merged": "5/5",
        "mandatory_source_reread_required_after_merge": True,
        "p4_3d_exit_gate_satisfied": True,
        "canonical_sha256": "",
    }
    receipt["canonical_sha256"] = ledger_audit.canonical_sha256(receipt)
    return receipt


def check(*, write: bool = False) -> dict[str, Any]:
    receipt = build_receipt()
    if write:
        RECEIPT_PATH.write_bytes(ledger_audit.canonical_json_bytes(receipt))
        return receipt
    try:
        committed = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise P43DRetirementAuditError("P4.3D receipt is unreadable; use --write to create it") from exc
    if committed != receipt or ledger_audit.canonical_sha256(committed) != committed.get("canonical_sha256"):
        raise P43DRetirementAuditError("committed P4.3D receipt differs from validated checkpoint proof")
    return committed


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="validate the committed P4.3D receipt without writing")
    group.add_argument("--write", action="store_true", help="write the deterministic P4.3D receipt")
    args = parser.parse_args(argv)
    try:
        receipt = check(write=args.write)
    except Exception as exc:
        print(f"P4_3D_RETIREMENT_AUDIT_EXTENSIBILITY_FAILED: {exc}", file=sys.stderr)
        return 1
    print(receipt["canonical_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
