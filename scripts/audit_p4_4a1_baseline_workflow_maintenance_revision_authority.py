"""Offline audit for the P4.4A1 baseline-workflow maintenance authority."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts import audit_p4_3_workflow_retirement_ledger as retirement
from scripts import audit_p4_4a_workflow_evolution_guard as p44a
from scripts import audit_p4_workflow_evolution_ledger as evolution


POLICY_ID = "ATHENA_P4_4A1_BASELINE_WORKFLOW_MAINTENANCE_REVISION_AUTHORITY_V1"
BASE_MAIN_SHA = "c33fdb01cbe022361abd8d1cc8e3d3178f862013"
P44A_RECEIPT_SHA256 = "bd0471dc34327a16f1d501297d57017f90d535c25fbf418c772551d99d287720"
P44A_SNAPSHOT_SHA256 = "92f2e8a3dd4255bbf5dd75e6dbdd9878f4938ec91c22751e228bb079ffe32e9f"
EVOLUTION_LEDGER_SHA256 = P44A_SNAPSHOT_SHA256
P43_RETIREMENT_CHECKPOINT_SHA256 = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
BASE_WORKFLOW_TREE_SHA1 = "6391a5a17b9925c91849a758852915d509a64703"
BASE_WORKFLOW_COUNT = 37
RECEIPT_PATH = Path("artifacts/architecture/p4_4a1_baseline_workflow_maintenance_revision_authority_v1.json")
FRESH_HOLDOUT_WORKFLOW_BLOBS = {
    ".github/workflows/bridge-fotmob-fresh-holdout-continuity-receipts.yml": "d880f07fc7d5f407f9f4bdc7a7311bb89f713fd0",
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout-release-receipts.yml": "c34528d5bf21556d85585ed7c807b34ca5f7666f",
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml": "1efe1e34d4459b2aeea17d5da8ba77bd4e2442f2",
    ".github/workflows/watch-fotmob-fresh-holdout-scheduler-liveness.yml": "f613211018417435cb4ad7a22529b1ff0a38d690",
}
FRESH_HOLDOUT_SCRIPT_BLOBS = {
    "scripts/mirror_fotmob_fresh_holdout_release_receipt.py": "ddabb6ae83cbe6c81c9264119a121a54715df960",
    "scripts/run_fotmob_fresh_holdout_release_receipt_mirror.py": "f0b836304b1d46877e0396ea7a532c24b46a3d16",
}
P44A_SNAPSHOT_PATH = "artifacts/architecture/p4_workflow_evolution_snapshots/p4_4a_workflow_evolution_ledger_v1.json"
EVOLUTION_LEDGER_PATH = "artifacts/architecture/p4_workflow_evolution_ledger_v1.json"
FROZEN_ARTIFACTS = {
    "artifacts/architecture/p4_1_cli_consolidation_v1.json": "268933433aaab84cb2533840f2e01eba96ec5906e796c9eced2032e1d6706208",
    "artifacts/architecture/p4_2_athena_run_workflow_v1.json": "fa575a5bb5f4611eb94564b92dea3e4230b8d429b1660dc3bde3d6c164b836f8",
    "artifacts/architecture/p4_3_workflow_capability_matrix_v1.json": "6b417a19557efdd39201e233fb866e4143b8102ba2879a4f1481e5241722dd8d",
    "artifacts/architecture/p4_3a_workflow_capability_census_v1.json": "7dd102aa4da98d634d665b4a93f51eb24ece8d7b61c8856b9977ff84a7452a6b",
    "artifacts/architecture/p4_3b_current_sportybet_workflow_retirement_v1.json": "cf2371c7ec2747256f23599e7a43dd2d9e46ff61dda2c478a746d8bd8a49e72a",
    "artifacts/architecture/p4_3c_spent_v1_evidence_workflow_retirement_v1.json": "c4afd0d0052c7b14d643f7868d7eac85344042da20a9d7aa0e8bf3b59ab9bd24",
    "artifacts/architecture/p4_3d_retirement_audit_extensibility_v1.json": "4b43e084f82f65330429388732990ed8e49abe8e05fd30fc57a319a210dfb25f",
    "artifacts/architecture/p4_3_retirement_ledger_snapshots/p4_3c_workflow_retirement_ledger_v1.json": P43_RETIREMENT_CHECKPOINT_SHA256,
    "artifacts/architecture/p4_4a_workflow_evolution_guard_v1.json": P44A_RECEIPT_SHA256,
    P44A_SNAPSHOT_PATH: P44A_SNAPSHOT_SHA256,
}


class MaintenanceAuthorityError(AssertionError):
    """Raised when P4.4A1 authority or historical evidence is inconsistent."""


def _git(*args: str) -> bytes:
    result = subprocess.run(["git", *args], capture_output=True)
    if result.returncode:
        raise MaintenanceAuthorityError(f"git {' '.join(args)} failed: {result.stderr.decode('utf-8', 'replace')}")
    return result.stdout


def _base_commit_available() -> bool:
    return subprocess.run(["git", "cat-file", "-e", f"{BASE_MAIN_SHA}^{{commit}}"], capture_output=True).returncode == 0


def _canonical_file_sha(path: str, expected: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MaintenanceAuthorityError(f"frozen evidence is unreadable: {path}") from exc
    if value.get("canonical_sha256") != expected or evolution.canonical_sha256(value) != expected:
        raise MaintenanceAuthorityError(f"frozen evidence canonical SHA changed: {path}")
    return value


def _verify_base_checkpoint() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    for path, expected in FROZEN_ARTIFACTS.items():
        _canonical_file_sha(path, expected)
    p44a_receipt = _canonical_file_sha(p44a.RECEIPT_PATH.as_posix(), P44A_RECEIPT_SHA256)
    p44a_snapshot = _canonical_file_sha(P44A_SNAPSHOT_PATH, P44A_SNAPSHOT_SHA256)
    try:
        evolution_ledger = json.loads(Path(EVOLUTION_LEDGER_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MaintenanceAuthorityError("current workflow evolution ledger is unreadable") from exc
    if (
        evolution_ledger.get("canonical_sha256") != EVOLUTION_LEDGER_SHA256
        or evolution.canonical_sha256(evolution_ledger) != EVOLUTION_LEDGER_SHA256
    ):
        # The P4.4A1 creation writer requires the exact zero-transition checkpoint.
        # The normal checker separately allows reviewed future extensions.
        raise MaintenanceAuthorityError("current evolution ledger is not the P4.4A1 creation checkpoint")
    if p44a_snapshot != evolution_ledger or p44a_snapshot.get("transitions") != []:
        raise MaintenanceAuthorityError("P4.4A1 creation requires the immutable zero-transition P4.4A snapshot")
    if p44a_receipt.get("workflow_evolution_checkpoint_sha256") != P44A_SNAPSHOT_SHA256:
        raise MaintenanceAuthorityError("P4.4A receipt does not bind its immutable evolution snapshot")
    return p44a_receipt, p44a_snapshot, evolution_ledger


def _verify_base_only_file_identity(path: str, blob_sha: str) -> None:
    if _base_commit_available():
        observed = _git("rev-parse", f"{BASE_MAIN_SHA}:{path}").decode("ascii").strip()
        if observed != blob_sha:
            raise MaintenanceAuthorityError(f"P4.4A1 base source identity changed: {path}")


def build_receipt() -> dict[str, Any]:
    """Build the one-time P4.4A1 checkpoint receipt from verified base state."""
    p44a_receipt, p44a_snapshot, evolution_ledger = _verify_base_checkpoint()
    p43_ledger = retirement.validate_retirement_history()
    current = evolution.validate_current_state(retirement_ledger=p43_ledger)
    if (
        current["transitions"] != []
        or current["current_live_workflow_count"] != BASE_WORKFLOW_COUNT
        or current["current_workflow_tree_sha1"] != BASE_WORKFLOW_TREE_SHA1
        or p43_ledger.get("current_retired_workflow_count") != 3
        or p43_ledger.get("canonical_sha256") != P43_RETIREMENT_CHECKPOINT_SHA256
    ):
        raise MaintenanceAuthorityError("P4.4A1 receipt creation requires the untouched 37/3/zero-transition state")
    tree_sha = _git("rev-parse", "HEAD:.github/workflows").decode("ascii").strip()
    paths = sorted(
        item.decode("utf-8")
        for item in _git("ls-tree", "-r", "-z", "--name-only", "HEAD", "--", ".github/workflows").split(b"\0")
        if item
    )
    if tree_sha != BASE_WORKFLOW_TREE_SHA1 or len(paths) != BASE_WORKFLOW_COUNT:
        raise MaintenanceAuthorityError("P4.4A1 creation requires the exact 37-workflow tree")
    if ".github/workflows/athena-ingest.yml" in paths:
        raise MaintenanceAuthorityError("athena-ingest.yml must remain absent in P4.4A1")
    if p44a_receipt.get("base_workflow_tree_sha1") != BASE_WORKFLOW_TREE_SHA1:
        raise MaintenanceAuthorityError("P4.4A receipt base workflow tree differs")

    for path, blob in {**FRESH_HOLDOUT_WORKFLOW_BLOBS, **FRESH_HOLDOUT_SCRIPT_BLOBS}.items():
        _verify_base_only_file_identity(path, blob)

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository_base_main_sha": BASE_MAIN_SHA,
        "p4_4a_receipt_sha256": P44A_RECEIPT_SHA256,
        "p4_4a_evolution_checkpoint_sha256": P44A_SNAPSHOT_SHA256,
        "current_evolution_ledger_sha256": evolution_ledger["canonical_sha256"],
        "current_transition_count": 0,
        "p4_3_retirement_ledger_sha256": p43_ledger["canonical_sha256"],
        "workflow_count_before": BASE_WORKFLOW_COUNT,
        "workflow_count_after": BASE_WORKFLOW_COUNT,
        "workflow_tree_before_sha1": BASE_WORKFLOW_TREE_SHA1,
        "workflow_tree_after_sha1": BASE_WORKFLOW_TREE_SHA1,
        "fresh_holdout_workflow_blob_sha1": FRESH_HOLDOUT_WORKFLOW_BLOBS,
        "fresh_holdout_script_blob_sha1": FRESH_HOLDOUT_SCRIPT_BLOBS,
        "new_transition_operation": "MAINTENANCE_REVISE",
        "ordinary_revise_of_p43a_survivor_allowed": False,
        "maintenance_revise_of_p43a_survivor_allowed": True,
        "evolution_retire_of_p43a_survivor_allowed": False,
        "add_existing_p43a_path_allowed": False,
        "historical_before_fixture_required": True,
        "maintenance_contract_required": True,
        "maintenance_revision_net_workflow_count_delta": 0,
        "real_workflow_revision_performed": False,
        "workflow_yaml_changed": False,
        "fresh_holdout_workflow_changed": False,
        "athena_ingest_created": False,
        "fresh_holdout_durability_incident_source_run_id": 35847067175,
        "fresh_holdout_durability_bridge_run_id": 35847076204,
        "fresh_holdout_durability_repair_run_id": 35857443476,
        "fresh_holdout_durability_repair_complete": True,
        "fresh_holdout_durability_repair_additional_provider_requests": 0,
        "permanent_fresh_holdout_hotfix_implemented": False,
        "real_share_code_operation": False,
        "backfill_performed": False,
        "provider_acquisition": False,
        "workflow_dispatch_triggered": False,
        "current_shadow_triggered": False,
        "fresh_holdout_triggered": False,
        "p3_0_e1_triggered": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "wager_placed": False,
        "model_formula_changed": False,
        "router_formula_changed": False,
        "portfolio_formula_changed": False,
        "provider_semantics_changed": False,
        "authority_semantics_changed": False,
        "next_required_step": "FRESH_HOLDOUT_RELEASE_VISIBILITY_RACE_HOTFIX_REQUIRED",
        "p4_4b_started": False,
        "p4_4_overall_complete": False,
        "architecture_checkpoint_e_fully_claimed": False,
        "source_review_counter_while_unmerged": "1/5",
        "source_review_counter_if_merged": "2/5",
    }
    receipt["canonical_sha256"] = evolution.canonical_sha256(receipt)
    return receipt


def check() -> dict[str, Any]:
    try:
        receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MaintenanceAuthorityError("P4.4A1 receipt is unreadable") from exc
    if receipt.get("policy_id") != POLICY_ID or receipt.get("schema_version") != 1:
        raise MaintenanceAuthorityError("P4.4A1 receipt schema/policy mismatch")
    if receipt.get("canonical_sha256") != evolution.canonical_sha256(receipt):
        raise MaintenanceAuthorityError("P4.4A1 receipt self-hash mismatch")
    if receipt.get("canonical_sha256") != RECEIPT_SHA256:
        raise MaintenanceAuthorityError("immutable P4.4A1 receipt identity changed")
    if receipt.get("repository_base_main_sha") != BASE_MAIN_SHA:
        raise MaintenanceAuthorityError("P4.4A1 base main identity changed")

    for path, expected in FROZEN_ARTIFACTS.items():
        _canonical_file_sha(path, expected)
    p44a_receipt = _canonical_file_sha(p44a.RECEIPT_PATH.as_posix(), P44A_RECEIPT_SHA256)
    p44a_snapshot = _canonical_file_sha(P44A_SNAPSHOT_PATH, P44A_SNAPSHOT_SHA256)
    p43_checkpoint = retirement._load_p43c_ledger_snapshot()
    p43_current = retirement.validate_retirement_history()
    current = evolution.validate_current_state(retirement_ledger=p43_current)
    current_p43_snapshot = evolution.load_retirement_snapshot_for_evolution(current)
    evolution.validate_evolution_snapshot_extension(
        p44a_snapshot,
        current,
        snapshot_retirement_snapshot=p43_checkpoint,
        current_retirement_snapshot=current_p43_snapshot,
        current_retirement=p43_current,
    )
    if p44a_receipt.get("workflow_evolution_checkpoint_sha256") != P44A_SNAPSHOT_SHA256:
        raise MaintenanceAuthorityError("P4.4A receipt checkpoint backlink changed")
    if p44a_snapshot.get("transitions") != [] or p44a_snapshot.get("current_live_workflow_count") != 37:
        raise MaintenanceAuthorityError("immutable P4.4A zero-transition checkpoint changed")
    historical_fields = {
        "p4_4a_receipt_sha256": P44A_RECEIPT_SHA256,
        "p4_4a_evolution_checkpoint_sha256": P44A_SNAPSHOT_SHA256,
        "current_evolution_ledger_sha256": P44A_SNAPSHOT_SHA256,
        "current_transition_count": 0,
        "p4_3_retirement_ledger_sha256": P43_RETIREMENT_CHECKPOINT_SHA256,
        "workflow_count_before": 37,
        "workflow_count_after": 37,
        "workflow_tree_before_sha1": BASE_WORKFLOW_TREE_SHA1,
        "workflow_tree_after_sha1": BASE_WORKFLOW_TREE_SHA1,
        "new_transition_operation": "MAINTENANCE_REVISE",
        "maintenance_revise_of_p43a_survivor_allowed": True,
        "ordinary_revise_of_p43a_survivor_allowed": False,
        "evolution_retire_of_p43a_survivor_allowed": False,
        "add_existing_p43a_path_allowed": False,
        "historical_before_fixture_required": True,
        "maintenance_contract_required": True,
        "maintenance_revision_net_workflow_count_delta": 0,
        "real_workflow_revision_performed": False,
        "workflow_yaml_changed": False,
        "fresh_holdout_workflow_changed": False,
        "athena_ingest_created": False,
        "fresh_holdout_durability_incident_source_run_id": 35847067175,
        "fresh_holdout_durability_bridge_run_id": 35847076204,
        "fresh_holdout_durability_repair_run_id": 35857443476,
        "fresh_holdout_durability_repair_complete": True,
        "fresh_holdout_durability_repair_additional_provider_requests": 0,
        "permanent_fresh_holdout_hotfix_implemented": False,
        "real_share_code_operation": False,
        "backfill_performed": False,
        "provider_acquisition": False,
        "workflow_dispatch_triggered": False,
        "current_shadow_triggered": False,
        "fresh_holdout_triggered": False,
        "p3_0_e1_triggered": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "wager_placed": False,
        "model_formula_changed": False,
        "router_formula_changed": False,
        "portfolio_formula_changed": False,
        "provider_semantics_changed": False,
        "authority_semantics_changed": False,
        "next_required_step": "FRESH_HOLDOUT_RELEASE_VISIBILITY_RACE_HOTFIX_REQUIRED",
        "p4_4b_started": False,
        "p4_4_overall_complete": False,
        "architecture_checkpoint_e_fully_claimed": False,
        "source_review_counter_while_unmerged": "1/5",
        "source_review_counter_if_merged": "2/5",
    }
    if any(receipt.get(key) != value for key, value in historical_fields.items()):
        raise MaintenanceAuthorityError("P4.4A1 frozen authority/zero-change claims changed")
    if receipt.get("fresh_holdout_workflow_blob_sha1") != FRESH_HOLDOUT_WORKFLOW_BLOBS:
        raise MaintenanceAuthorityError("P4.4A1 Fresh-Holdout workflow identity evidence changed")
    if receipt.get("fresh_holdout_script_blob_sha1") != FRESH_HOLDOUT_SCRIPT_BLOBS:
        raise MaintenanceAuthorityError("P4.4A1 Fresh-Holdout mirror/transport identity evidence changed")
    if _base_commit_available():
        base_tree = _git("rev-parse", f"{BASE_MAIN_SHA}:.github/workflows").decode("ascii").strip()
        if base_tree != BASE_WORKFLOW_TREE_SHA1:
            raise MaintenanceAuthorityError("P4.4A1 historical base workflow tree does not match its receipt")
        base_paths = [
            item.decode("utf-8")
            for item in _git("ls-tree", "-r", "-z", "--name-only", BASE_MAIN_SHA, "--", ".github/workflows").split(b"\0")
            if item
        ]
        if len(base_paths) != BASE_WORKFLOW_COUNT:
            raise MaintenanceAuthorityError("P4.4A1 historical base workflow count does not match its receipt")
        for path, blob in {**FRESH_HOLDOUT_WORKFLOW_BLOBS, **FRESH_HOLDOUT_SCRIPT_BLOBS}.items():
            if _git("rev-parse", f"{BASE_MAIN_SHA}:{path}").decode("ascii").strip() != blob:
                raise MaintenanceAuthorityError(f"P4.4A1 historical base source identity mismatch: {path}")
    if current.get("canonical_sha256") != json.loads(Path(EVOLUTION_LEDGER_PATH).read_text(encoding="utf-8"))["canonical_sha256"]:
        raise MaintenanceAuthorityError("current evolution ledger validation returned an inconsistent state")
    return receipt


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="validate frozen P4.4A1 evidence offline")
    mode.add_argument("--write", action="store_true", help="create the one-time P4.4A1 receipt")
    args = parser.parse_args(argv)
    if args.write:
        if RECEIPT_PATH.exists():
            raise MaintenanceAuthorityError("P4.4A1 receipt already exists and is immutable")
        receipt = build_receipt()
        RECEIPT_PATH.write_bytes(evolution.canonical_json_bytes(receipt))
    else:
        receipt = check()
    print(receipt["canonical_sha256"])
    return 0


RECEIPT_SHA256 = "0a3833622c94f71dce0524cb9da9f77653e5f2de29d192d0a0f2e02565e4c18b"


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"P4_4A1_MAINTENANCE_AUTHORITY_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
