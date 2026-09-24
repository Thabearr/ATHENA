"""Offline audit for the P4.4D current-FotMob compatibility boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from scripts import audit_p4_3_workflow_retirement_ledger as retirement
from scripts import audit_p4_4c_scheduled_ingest_and_migration_review as p44c
from scripts import audit_p4_workflow_evolution_ledger as evolution


BASE_MAIN = "d6a188fa3b377f4b9477e0e5e04887d1bdc03177"
P44C_RECEIPT_SHA256 = "58c8ae0406210b51351097d8be4e6f761533443c334dc8bc47702f7d4a69755a"
P44C_MIGRATION_SHA256 = "24201e7d522f97863bebace3d2246ce18bc3c967098f7410c5a7ca1ae2629921"
EVOLUTION_SHA256 = "12abbe541ed807cf96238972f3120ffe9df8130b1dee452740917ea0995d75f7"
WORKFLOW_TREE_SHA1 = "02e62ab141627885652c304f83dda4274d7245a9"
P43_RETIREMENT_SHA256 = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
INGEST_PATH = ".github/workflows/athena-ingest.yml"
LEGACY_PATH = ".github/workflows/issue-current-fotmob-reviewed-source.yml"
INGEST_IDENTITY = {
    "git_blob_sha1": "1c3abb610477862663ccb1b077ff4413be819eda",
    "source_sha256": "9e5137b85a28f8552c4a6bc834c7657a2c690b4203382aa914d5f6854667d8d1",
}
LEGACY_IDENTITY = {
    "git_blob_sha1": "11bef2434088de1f8ac96e27e58b5ea07f1f06f4",
    "source_sha256": "8efb3b19d5fa580bca5a995ef9d9fbde84a62c153daea78a579c344f706df157",
}
RECEIPT_PATH = Path("artifacts/architecture/p4_4d_current_fotmob_ingest_compatibility_v1.json")
POLICY_ID = "ATHENA_P4_4D_CURRENT_FOTMOB_INGEST_COMPATIBILITY_AUTHORITY_V1"
FALSE_AUTHORITY_FIELDS = (
    "fixture_intelligence_fact_authority", "fixture_intelligence_snapshot_authority",
    "model_feature_authority", "probability_authority", "pricing_authority",
    "routing_authority", "portfolio_authority", "share_code_authority",
    "login", "cookies", "wallet", "staking", "wager", "backfill_authority",
)


class P44DCompatibilityAuditError(AssertionError):
    """P4.4D source or compatibility evidence does not match reviewed policy."""


def _git(*args: str) -> bytes:
    completed = subprocess.run(["git", *args], capture_output=True)
    if completed.returncode:
        raise P44DCompatibilityAuditError(
            f"git {' '.join(args)} failed: {completed.stderr.decode('utf-8', 'replace')}"
        )
    return completed.stdout


def _canonical_sha(value: dict[str, Any]) -> str:
    unsigned = {key: item for key, item in value.items() if key != "canonical_sha256"}
    return hashlib.sha256(retirement.canonical_json_bytes(unsigned)).hexdigest()


def _source_identity(path: str) -> dict[str, str]:
    # Use committed blob bytes as source identity. Windows may materialize a
    # tracked YAML file with CRLF despite an unchanged Git blob.
    raw = _git("show", f"HEAD:{path}")
    return {
        "git_blob_sha1": hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest(),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
    }


def expected_receipt() -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository_base_main_sha": BASE_MAIN,
        "p4_4c_receipt_sha256": P44C_RECEIPT_SHA256,
        "p4_4c_migration_review_sha256": P44C_MIGRATION_SHA256,
        "workflow_evolution_ledger_sha256": EVOLUTION_SHA256,
        "p4_3_retirement_ledger_sha256": P43_RETIREMENT_SHA256,
        "p4_3_retirement_count": 3,
        "workflow_tree_sha1_before": WORKFLOW_TREE_SHA1,
        "workflow_tree_sha1_after": WORKFLOW_TREE_SHA1,
        "workflow_count_before": 38,
        "workflow_count_after": 38,
        "workflow_evolution_transition_count_before": 4,
        "workflow_evolution_transition_count_after": 4,
        "legacy_current_reviewed_workflow_path": LEGACY_PATH,
        "legacy_current_reviewed_workflow_identity": LEGACY_IDENTITY,
        "canonical_ingest_workflow_path": INGEST_PATH,
        "canonical_ingest_workflow_identity": INGEST_IDENTITY,
        "compatibility_policy_id": "ATHENA_P4_4D_CURRENT_FOTMOB_INGEST_COMPATIBILITY_V1",
        "compatibility_scope": {
            "provider": "fotmob",
            "date_count": 1,
            "timezone": "UTC",
            "ccode3": "NGA",
            "successful_ingest_receipt_required": True,
            "canonical_store_update": "CANONICAL_SOURCE_UPDATE_READY",
            "source_count": 1,
            "network_acquired_source_provenance_required": True,
            "offline_replay_required": True,
        },
        "exact_source_in_place": True,
        "raw_and_manifest_identity_reverified": True,
        "pr243_semantic_parity_required": True,
        "provider_acquisition_by_adapter": False,
        "provider_request_count_by_adapter": 0,
        "source_bytes_copied_by_adapter": False,
        "source_bytes_rewritten_by_adapter": False,
        "full_legacy_request_contract_equivalence_claimed": False,
        "noncanonical_timezone_or_ccode3_supported": False,
        "legacy_workflow_modified": False,
        "canonical_ingest_workflow_modified": False,
        "canonical_ingest_request_schema_modified": False,
        "legacy_workflow_retirement_authorized": False,
        "provider_acquisition_during_pr": False,
        "provider_request_count_during_pr": 0,
        "workflow_dispatch_during_pr": False,
        "fixture_intelligence_fact_authority": False,
        "fixture_intelligence_snapshot_authority": False,
        "model_feature_authority": False,
        "probability_authority": False,
        "pricing_authority": False,
        "routing_authority": False,
        "portfolio_authority": False,
        "share_code_authority": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "wager": False,
        "backfill_authority": False,
        "p4_4_overall_complete": False,
        "architecture_checkpoint_e_fully_claimed": False,
        "source_review_counter_while_unmerged": "0/5",
        "source_review_counter_if_merged": "1/5",
    }
    value["canonical_sha256"] = _canonical_sha(value)
    return value


def validate_receipt(value: Any, *, check_live: bool = True) -> dict[str, Any]:
    expected = expected_receipt()
    if type(value) is not dict or set(value) != set(expected):
        raise P44DCompatibilityAuditError("P4.4D receipt fields differ from exact schema")
    if value != expected:
        raise P44DCompatibilityAuditError("P4.4D receipt differs from reviewed semantics")
    if value["canonical_sha256"] != _canonical_sha(value):
        raise P44DCompatibilityAuditError("P4.4D receipt self-hash mismatch")
    if check_live:
        _validate_live_state()
    return value


def _validate_live_state() -> None:
    if _git("rev-parse", "HEAD").decode("ascii").strip() != BASE_MAIN:
        # During implementation the branch HEAD remains the exact base until the
        # reviewed PR commits; after commits, ancestry must still start there.
        if _git("merge-base", "HEAD", BASE_MAIN).decode("ascii").strip() != BASE_MAIN:
            raise P44DCompatibilityAuditError("P4.4D branch is not based on exact reviewed main")
    if _git("rev-parse", f"{BASE_MAIN}:.github/workflows").decode("ascii").strip() != WORKFLOW_TREE_SHA1:
        raise P44DCompatibilityAuditError("P4.4C workflow tree base identity changed")
    if _git("rev-parse", f"{BASE_MAIN}:{evolution.LEDGER_PATH.as_posix()}").decode("ascii").strip() == "":
        raise P44DCompatibilityAuditError("P4.4C evolution ledger is missing at base")
    ledger = json.loads(_git("show", f"{BASE_MAIN}:{evolution.LEDGER_PATH.as_posix()}"))
    if ledger.get("canonical_sha256") != EVOLUTION_SHA256 or evolution.canonical_sha256(ledger) != EVOLUTION_SHA256:
        raise P44DCompatibilityAuditError("P4.4C evolution ledger identity changed")
    if len(ledger.get("transitions", [])) != 4:
        raise P44DCompatibilityAuditError("P4.4C transition count changed")
    transition = ledger["transitions"][3]
    if (
        transition.get("transition_id") != "P44C_ATHENA_INGEST_SCHEDULE_REVISE_V1"
        or transition.get("operation") != "REVISE"
        or transition.get("workflow_path") != INGEST_PATH
    ):
        raise P44DCompatibilityAuditError("P4.4C transition identity changed")
    current_ledger = json.loads(evolution.LEDGER_PATH.read_text(encoding="utf-8"))
    if current_ledger != ledger or evolution.canonical_sha256(current_ledger) != EVOLUTION_SHA256:
        raise P44DCompatibilityAuditError("current evolution ledger differs from P4.4C checkpoint")
    current_retirement = retirement.validate_retirement_history()
    if (
        current_retirement["canonical_sha256"] != P43_RETIREMENT_SHA256
        or current_retirement["current_retired_workflow_count"] != 3
    ):
        raise P44DCompatibilityAuditError("P4.3 retirement history changed")
    for path, identity in ((LEGACY_PATH, LEGACY_IDENTITY), (INGEST_PATH, INGEST_IDENTITY)):
        if _source_identity(path) != identity:
            raise P44DCompatibilityAuditError(f"protected workflow identity changed: {path}")
        if evolution.source_identity(_git("show", f"{BASE_MAIN}:{path}")) != identity:
            raise P44DCompatibilityAuditError(f"base workflow identity changed: {path}")
        if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", path]).returncode != 0:
            raise P44DCompatibilityAuditError(f"protected workflow has an uncommitted change: {path}")
        if subprocess.run(["git", "diff", "--cached", "--quiet", "HEAD", "--", path]).returncode != 0:
            raise P44DCompatibilityAuditError(f"protected workflow has a staged change: {path}")
    workflow_paths = list(Path(".github/workflows").glob("*.yml")) + list(Path(".github/workflows").glob("*.yaml"))
    if len(workflow_paths) != 38:
        raise P44DCompatibilityAuditError("live workflow count differs from P4.4C")
    tree = _git("rev-parse", "HEAD:.github/workflows").decode("ascii").strip()
    if tree != WORKFLOW_TREE_SHA1:
        raise P44DCompatibilityAuditError("live base workflow tree differs from P4.4C")
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", ".github/workflows"]).returncode != 0:
        raise P44DCompatibilityAuditError("workflow YAML has an uncommitted change")
    if subprocess.run(["git", "diff", "--cached", "--quiet", "HEAD", "--", ".github/workflows"]).returncode != 0:
        raise P44DCompatibilityAuditError("workflow YAML has a staged change")
    p44c_receipt = json.loads(Path(p44c.RECEIPT_PATH).read_text(encoding="utf-8"))
    p44c_migration = json.loads(Path(p44c.MIGRATION_PATH).read_text(encoding="utf-8"))
    p44c_snapshot = json.loads(Path(p44c.SNAPSHOT_PATH).read_text(encoding="utf-8"))
    if p44c_receipt.get("canonical_sha256") != P44C_RECEIPT_SHA256 or evolution.canonical_sha256(p44c_receipt) != P44C_RECEIPT_SHA256:
        raise P44DCompatibilityAuditError("P4.4C receipt is not byte-preserved")
    if p44c_migration.get("canonical_sha256") != P44C_MIGRATION_SHA256 or evolution.canonical_sha256(p44c_migration) != P44C_MIGRATION_SHA256:
        raise P44DCompatibilityAuditError("P4.4C migration review is not byte-preserved")
    if (
        p44c_snapshot != current_ledger
        or p44c_snapshot.get("canonical_sha256") != EVOLUTION_SHA256
        or evolution.canonical_sha256(p44c_snapshot) != EVOLUTION_SHA256
    ):
        raise P44DCompatibilityAuditError("P4.4C immutable evolution checkpoint changed")
    protected_evidence = (
        p44c.RECEIPT_PATH.as_posix(),
        p44c.MIGRATION_PATH.as_posix(),
        p44c.SNAPSHOT_PATH.as_posix(),
    )
    for path in protected_evidence:
        if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", path]).returncode != 0:
            raise P44DCompatibilityAuditError(f"historical P4.4C evidence was modified: {path}")
        if subprocess.run(["git", "diff", "--cached", "--quiet", "HEAD", "--", path]).returncode != 0:
            raise P44DCompatibilityAuditError(f"historical P4.4C evidence was staged: {path}")


def audit(path: Path = RECEIPT_PATH, *, check_live: bool = True) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise P44DCompatibilityAuditError("P4.4D receipt cannot be loaded") from exc
    return validate_receipt(value, check_live=check_live)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        audit()
        print("P4.4D current-FotMob ingest compatibility audit: PASS")
        return 0
    except (P44DCompatibilityAuditError, AssertionError, OSError, ValueError) as exc:
        print(f"P4.4D current-FotMob ingest compatibility audit: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
