"""Fail-closed audit for P4.4F's exact UTC/NGA current-source caller migration."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from domain.ingest_contracts import canonical_json_bytes, strict_json_loads
from scripts import audit_p4_3_workflow_retirement_ledger as retirement
from scripts import audit_p4_4b_athena_ingest_workflow as p44b
from scripts import audit_p4_4c_scheduled_ingest_and_migration_review as p44c
from scripts import audit_p4_4d_current_fotmob_ingest_compatibility as p44d
from scripts import audit_p4_4e_current_fotmob_ingest_issuer as p44e
from scripts import audit_p4_workflow_evolution_ledger as evolution


BASE_MAIN = "42341585c37a5e346b3aaea5cb550f004fa3f6a4"
P44E_RECEIPT_SHA256 = "30d8034198b44e4b81f9256223786e54367d8e1c7dd0c5075ddc1e527d98d5e6"
P44D_RECEIPT_SHA256 = "4f24db8a93068688192203aab5a4f1e9e0600cd684ee23f53e06a027e9f953e0"
P43_RETIREMENT_SHA256 = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
WORKFLOW_TREE_BEFORE = "02e62ab141627885652c304f83dda4274d7245a9"
WORKFLOW_TREE_AFTER = "98133fd73c4b9d12eb9927016b071cb0fa7841b3"
WORKFLOW_PATH = ".github/workflows/issue-current-fotmob-reviewed-source.yml"
WORKFLOW_BEFORE = {
    "git_blob_sha1": "11bef2434088de1f8ac96e27e58b5ea07f1f06f4",
    "source_sha256": "8efb3b19d5fa580bca5a995ef9d9fbde84a62c153daea78a579c344f706df157",
}
WORKFLOW_AFTER = {
    "git_blob_sha1": "7aaa7b9c3d26ff6454b26a094008c2bfd82c0b50",
    "source_sha256": "7d0d5ac1ca71722b560bb94ddeb7d5907d3824b74162976c2e3097c19a75243d",
}
BASE_EVOLUTION_SHA256 = "12abbe541ed807cf96238972f3120ffe9df8130b1dee452740917ea0995d75f7"
P44C_SNAPSHOT_PATH = Path(
    "artifacts/architecture/p4_workflow_evolution_snapshots/p4_4c_athena_ingest_schedule_v1.json"
)
LEDGER_PATH = evolution.LEDGER_PATH
SNAPSHOT_PATH = Path(
    "artifacts/architecture/p4_workflow_evolution_snapshots/p4_4f_current_fotmob_exact_lane_caller_migration_v1.json"
)
RECEIPT_PATH = Path(
    "artifacts/architecture/p4_4f_current_fotmob_exact_lane_caller_migration_v1.json"
)
PROOF_PATH = Path("artifacts/architecture/p4_4f_operational_proof_v1.json")
PROOF_FILE_SHA256 = "4740158a4b5b51764dbed1cf438544ddb05859dc0a5a353da385d1679c04b873"
PROOF_BODY_SHA256 = "77ea5d0579ccbc5a34fef215f7ab87cf9d64618ba5a16ab44c82a424534f12d9"
PROOF_POLICY_ID = "ATHENA_P4_4F_COMPOSITIONAL_OPERATIONAL_PROOF_V1"
FIXTURE_PATH = (
    "tests/fixtures/architecture/revised_workflows/"
    "issue-current-fotmob-reviewed-source-pre-p4-4f-canonical-lane.yml"
)
TRANSITION_ID = "P44F_CURRENT_FOTMOB_EXACT_LANE_CANONICAL_INGEST_MIGRATION_V1"
POLICY_ID = "ATHENA_P4_4F_CURRENT_FOTMOB_EXACT_LANE_CALLER_MIGRATION_V1"
EXPECTED_CHANGED_PATHS = {
    WORKFLOW_PATH,
    "scripts/issue_current_fotmob_reviewed_source_via_ingest.py",
    "tests/test_issue_current_fotmob_reviewed_source_via_ingest.py",
    "tests/test_issue_current_fotmob_workflow_contract.py",
    "scripts/audit_p4_4f_current_fotmob_exact_lane_caller_migration.py",
    "tests/test_p4_4f_current_fotmob_exact_lane_caller_migration.py",
    "artifacts/architecture/p4_4f_current_fotmob_exact_lane_caller_migration_v1.json",
    PROOF_PATH.as_posix(),
    SNAPSHOT_PATH.as_posix(),
    LEDGER_PATH.as_posix(),
    FIXTURE_PATH,
    "docs/current_fotmob_reviewed_source.md",
    "docs/architecture/athena_ingest_workflow.md",
    "docs/architecture/workflow_capability_matrix.md",
    "scripts/audit_p4_4c_scheduled_ingest_and_migration_review.py",
    "tests/test_p4_4c_scheduled_ingest_and_migration_review.py",
    "tests/test_athena_ingest_architecture.py",
    "tests/test_p4_4e_current_fotmob_ingest_issuer.py",
    "tests/test_current_fotmob_ingest_issuer.py",
    "tests/test_p4_4d_current_fotmob_ingest_compatibility.py",
    "tests/test_p4_workflow_evolution_ledger.py",
    "tests/test_athena_ingest_architecture.py",
    "tests/test_p4_4a_workflow_evolution_guard.py",
    "tests/test_p4_4a1_baseline_workflow_maintenance_revision_authority.py",
    "tests/test_fresh_holdout_release_visibility_race_hotfix.py",
}
PROTECTED_PATHS = (
    ".github/workflows/athena-ingest.yml",
    "domain/ingest_contracts.py",
    "services/athena_ingest_service.py",
    "services/current_fotmob_ingest_compatibility.py",
    "services/current_fotmob_ingest_issuer.py",
    "scripts/issue_current_fotmob_reviewed_source.py",
)
PROTECTED_IDENTITIES = {
    ".github/workflows/athena-ingest.yml": {
        "git_blob_sha1": "1c3abb610477862663ccb1b077ff4413be819eda",
        "source_sha256": "9e5137b85a28f8552c4a6bc834c7657a2c690b4203382aa914d5f6854667d8d1",
    },
    "domain/ingest_contracts.py": {
        "git_blob_sha1": "77f71e1570d7f0b6aed7641b45074ef462997d7d",
        "source_sha256": "e00f6e5c9d1670abae57bed097d89a01f78fcf059fa17a95caec238c4f6fc5fb",
    },
    "services/athena_ingest_service.py": {
        "git_blob_sha1": "08a177bea47b52bed0890d0f43e0f25c5fa14246",
        "source_sha256": "4fe52bb56047b6adfacdee71673d41412669ecf2c61eace636a29b2d567bac5a",
    },
    "services/current_fotmob_ingest_compatibility.py": {
        "git_blob_sha1": "a1fecd955c7b9e4966dc7248cbae0851414371c5",
        "source_sha256": "04a36fe3d51d9609aa215d3623e0e260a665e817c4b1830a080ed8fc67cb7934",
    },
    "services/current_fotmob_ingest_issuer.py": {
        "git_blob_sha1": "0721d34cf6c53264c197d1ce0c5867592b1c8b01",
        "source_sha256": "7de9ad0a6ffa68491aad7c2c5034123d3beab569748515e3e2bd482dc803ecec",
    },
    "scripts/issue_current_fotmob_reviewed_source.py": {
        "git_blob_sha1": "b50689971ee20cb6800145317a0e9fcb3486f40f",
        "source_sha256": "449e83af1a8e25bf5b054b88682b8559363196ca2d6e1dad87c742949b8d0484",
    },
}
FALSE_AUTHORITY_FIELDS = (
    "model_authority",
    "pricing_authority",
    "routing_authority",
    "portfolio_authority",
    "share_code_authority",
    "login_authority",
    "cookies_authority",
    "wallet_authority",
    "staking_authority",
    "wager_authority",
)


class P44FMigrationAuditError(AssertionError):
    """P4.4F workflow, caller, authority, or evidence chain differs from review."""


def _git(*args: str) -> bytes:
    result = subprocess.run(["git", *args], capture_output=True)
    if result.returncode:
        raise P44FMigrationAuditError(
            f"git {' '.join(args)} failed: {result.stderr.decode('utf-8', 'replace')}"
        )
    return result.stdout


def _load_json(path: Path) -> dict[str, Any]:
    # Restore canonical tracked bytes after Windows checkout EOL conversion;
    # this does not normalize any embedded source capture or receipt payload.
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    value = strict_json_loads(raw)
    if type(value) is not dict or canonical_json_bytes(value) != raw:
        raise P44FMigrationAuditError(f"canonical JSON evidence is invalid: {path}")
    return value


def _identity_at(ref: str, path: str) -> dict[str, str]:
    raw = _git("show", f"{ref}:{path}")
    return evolution.source_identity(raw)


def _transition_intent() -> dict[str, Any]:
    return {
        "transition_id": TRANSITION_ID,
        "operation": "MAINTENANCE_REVISE",
        "workflow_path": WORKFLOW_PATH,
        "before": dict(WORKFLOW_BEFORE),
        "after": dict(WORKFLOW_AFTER),
        "phase_id": "P4.4F",
        "canonical_family": "ATHENA_INGEST_FUTURE",
        "evidence_receipt_path": RECEIPT_PATH.as_posix(),
        "checkpoint_snapshot_path": SNAPSHOT_PATH.as_posix(),
        "historical_before_fixture": {
            "path": FIXTURE_PATH,
            **WORKFLOW_BEFORE,
        },
        "maintenance_contract": dict(evolution.MAINTENANCE_CONTRACT),
    }


def _receipt_body() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository_base_main_sha": BASE_MAIN,
        "p4_4e_receipt_sha256": P44E_RECEIPT_SHA256,
        "p4_4d_receipt_sha256": P44D_RECEIPT_SHA256,
        "workflow_path": WORKFLOW_PATH,
        "workflow_before_identity": dict(WORKFLOW_BEFORE),
        "workflow_after_identity": dict(WORKFLOW_AFTER),
        "workflow_count_before": 38,
        "workflow_count_after": 38,
        "workflow_tree_sha1_before": WORKFLOW_TREE_BEFORE,
        "workflow_tree_sha1_after": WORKFLOW_TREE_AFTER,
        "workflow_evolution_ledger_sha256_before": BASE_EVOLUTION_SHA256,
        "workflow_evolution_transition_count_before": 4,
        "workflow_evolution_transition_count_after": 5,
        "transition_id": TRANSITION_ID,
        "transition_operation": "MAINTENANCE_REVISE",
        "canonical_family": "ATHENA_INGEST_FUTURE",
        "p4_3_retirement_ledger_sha256": P43_RETIREMENT_SHA256,
        "migration_scope": {
            "date_count": 1,
            "provider": "fotmob",
            "timezone": "UTC",
            "ccode3": "NGA",
        },
        "legacy_noncanonical_lane_retained": True,
        "legacy_live_issuer_still_reachable": True,
        "full_legacy_workflow_equivalence_claimed": False,
        "legacy_workflow_retirement_authorized": False,
        "trigger_surface_changed": False,
        "permissions_changed": False,
        "concurrency_changed": False,
        "provider_acquisition_authority_changed": False,
        "exact_utc_nga_provider_implementation_changed": True,
        "live_behavior_changes_if_merged": True,
        "artifact_name_preserved": True,
        "artifact_name": "current-fotmob-reviewed-source-${{ github.run_id }}",
        "artifact_retention_days": 7,
        "execution_json_path": ".cache/athena-research/current-fotmob-reviewed-source/execution.json",
        "canonical_artifact_root_uploaded": "artifacts/athena-ingest-workflow/",
        "legacy_capture_root_still_uploaded": ".cache/athena-research/fotmob-data-matches-captures/",
        "canonical_source_copied_or_rewritten": False,
        "acquisition_retry_added": False,
        "fallback_after_canonical_acquisition": False,
        "max_provider_requests_per_dispatch_path": 1,
        "provider_acquisition_during_pr": True,
        "provider_request_count_during_pr": 1,
        "workflow_dispatch_during_pr": False,
        "operational_proof_required": True,
        "operational_proof_completed": True,
        "owner_operational_proof_authorization_received": True,
        "operational_proof_receipt_path": PROOF_PATH.as_posix(),
        "operational_proof_receipt_sha256": PROOF_FILE_SHA256,
        "operational_proof_evidence_body_sha256": PROOF_BODY_SHA256,
        "operational_proof_main_sha": BASE_MAIN,
        "operational_proof_request_date": "20260926",
        "operational_proof_ingest_receipt_sha256": "baff4ed293f46f7d6b5a5b51d47a9516e02b7c8b8aae35b38b691a63642ab6cc",
        "operational_proof_source_raw_sha256": "05ba602de32315a472b468bcacab23c0800c2a88def380316fd5df6618dd56f6",
        "operational_proof_source_manifest_sha256": "d9264b007f83040e01038e2ce0e408874f9369209defb0ec138f814dcb9c92e9",
        "operational_proof_compatibility_sha256": "cd75e4399e5198e04e26af2d436316b13ed1b1c93fe88fe80486e3bae762430a",
        "operational_proof_approved_count": 26,
        "model_authority": False,
        "pricing_authority": False,
        "routing_authority": False,
        "portfolio_authority": False,
        "share_code_authority": False,
        "login_authority": False,
        "cookies_authority": False,
        "wallet_authority": False,
        "staking_authority": False,
        "wager_authority": False,
        "p4_4_overall_complete": False,
        "architecture_checkpoint_e_complete": False,
        "source_review_counter_while_unmerged": "2/5",
        "source_review_counter_if_merged": "3/5",
        "reviewed_workflow_transition": _transition_intent(),
    }


def build_evidence() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build the single reviewed P4.4F transition and cumulative evidence chain."""
    historical = _load_json(P44C_SNAPSHOT_PATH)
    if (
        historical.get("canonical_sha256") != BASE_EVOLUTION_SHA256
        or evolution.canonical_sha256(historical) != BASE_EVOLUTION_SHA256
        or len(historical.get("transitions", [])) != 4
    ):
        raise P44FMigrationAuditError("P4.4C cumulative checkpoint is not the exact P4.4F base")
    transition = _transition_intent()
    body_receipt = _receipt_body()
    transition["evidence_body_sha256"] = evolution.receipt_evidence_body_sha256(body_receipt)

    ledger = dict(historical)
    ledger["transitions"] = [*historical["transitions"], transition]
    ledger["current_live_workflow_count"] = 38
    ledger["current_workflow_tree_sha1"] = WORKFLOW_TREE_AFTER
    ledger["canonical_sha256"] = evolution.canonical_sha256(ledger)
    snapshot = dict(ledger)

    receipt = dict(body_receipt)
    receipt["workflow_evolution_ledger_sha256"] = ledger["canonical_sha256"]
    receipt["canonical_sha256"] = evolution.canonical_sha256(receipt)
    return ledger, snapshot, receipt


def expected_receipt() -> dict[str, Any]:
    return build_evidence()[2]


def validate_receipt(value: Any) -> dict[str, Any]:
    expected = expected_receipt()
    if type(value) is not dict or set(value) != set(expected):
        raise P44FMigrationAuditError("P4.4F receipt fields differ from the exact schema")
    if value != expected:
        raise P44FMigrationAuditError("P4.4F receipt differs from reviewed semantics")
    if value.get("canonical_sha256") != evolution.canonical_sha256(value):
        raise P44FMigrationAuditError("P4.4F receipt self-hash mismatch")
    return value


def _check_operational_proof() -> dict[str, Any]:
    raw = PROOF_PATH.read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(raw).hexdigest() != PROOF_FILE_SHA256:
        raise P44FMigrationAuditError("P4.4F operational proof file hash differs")
    proof = strict_json_loads(raw)
    if type(proof) is not dict or canonical_json_bytes(proof) != raw:
        raise P44FMigrationAuditError("P4.4F operational proof is not canonical JSON")
    unsigned = {key: item for key, item in proof.items() if key != "evidence_body_sha256"}
    if (
        proof.get("policy_id") != PROOF_POLICY_ID
        or proof.get("evidence_body_sha256") != PROOF_BODY_SHA256
        or hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest() != PROOF_BODY_SHA256
        or proof.get("compositional_operational_proof_complete") is not True
        or proof.get("second_live_provider_attempt_performed") is not False
    ):
        raise P44FMigrationAuditError("P4.4F operational proof identity/completion differs")
    authorization = proof.get("authorization", {})
    live = proof.get("live_attempt", {})
    offline = proof.get("offline_continuation", {})
    if (
        authorization.get("owner_authorized") is not True
        or authorization.get("provider_request_budget") != 1
        or authorization.get("provider_request_budget_consumed") is not True
        or authorization.get("retry_budget") != 0
        or authorization.get("workflow_dispatch_budget") != 0
        or live.get("status") != "SUCCESS"
        or live.get("stage") != "COMPLETED"
        or live.get("failure_code") is not None
        or live.get("exact_commit_sha") != BASE_MAIN
        or live.get("provider_request_count") != 1
        or live.get("source_count") != 1
        or live.get("retry_count") != 0
        or live.get("workflow_dispatch_count") != 0
    ):
        raise P44FMigrationAuditError("P4.4F live proof budget/ingest evidence differs")
    if (
        offline.get("replay_status") != "ATHENA_INGEST_OFFLINE_REPLAY_VERIFIED"
        or offline.get("network_acquisition_performed") is not False
        or offline.get("provider_request_count") != 0
        or offline.get("provider_request_count_by_adapter") != 0
        or offline.get("exact_commit_sha") != BASE_MAIN
        or offline.get("source_raw_sha256") != "05ba602de32315a472b468bcacab23c0800c2a88def380316fd5df6618dd56f6"
        or offline.get("source_capture_manifest_sha256") != "d9264b007f83040e01038e2ce0e408874f9369209defb0ec138f814dcb9c92e9"
        or offline.get("compatibility_receipt_canonical_sha256") != "cd75e4399e5198e04e26af2d436316b13ed1b1c93fe88fe80486e3bae762430a"
        or offline.get("approved_count") != 26
        or offline.get("wager_placed") is not False
    ):
        raise P44FMigrationAuditError("P4.4F zero-network compatibility proof differs")
    if any(proof.get("authority", {}).values()):
        raise P44FMigrationAuditError("P4.4F operational proof expanded forbidden authority")
    return proof


def _require_exact_base_ancestry() -> None:
    merge_base = subprocess.run(
        ["git", "merge-base", "HEAD", BASE_MAIN], capture_output=True
    )
    if merge_base.returncode == 0:
        valid = merge_base.stdout.decode("ascii").strip() == BASE_MAIN
    else:
        parents = _git("show", "-s", "--format=%P", "HEAD").decode("ascii").split()
        valid = BASE_MAIN in parents
        if not valid and os.environ.get("GITHUB_EVENT_NAME") == "pull_request":
            event_path = os.environ.get("GITHUB_EVENT_PATH")
            try:
                event = json.loads(Path(event_path).read_text(encoding="utf-8")) if event_path else {}
                pull_request = event.get("pull_request", {})
                base = pull_request.get("base", {})
                head = pull_request.get("head", {})
                current = _git("rev-parse", "HEAD").decode("ascii").strip()
                valid = (
                    base.get("ref") == "main"
                    and base.get("sha") == BASE_MAIN
                    and re.fullmatch(r"[0-9a-f]{40}", str(head.get("sha", ""))) is not None
                    and current in {head.get("sha"), os.environ.get("GITHUB_SHA")}
                )
            except (OSError, json.JSONDecodeError, P44FMigrationAuditError):
                valid = False
    if not valid:
        raise P44FMigrationAuditError("P4.4F branch is not based on exact authoritative main")


def _changed_paths_from_exact_base() -> set[str] | None:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{BASE_MAIN}...HEAD"], capture_output=True
    )
    if result.returncode == 0:
        return set(result.stdout.decode("utf-8").splitlines())

    # Hosted pull_request checkouts can contain only the synthetic merge commit.
    # In that case the exact base object is absent, so a tree diff cannot be
    # computed locally. Accept this limitation only after independently binding
    # the exact base/head through the trusted pull_request event above; all
    # source identities, protected files, and workflow/evolution invariants are
    # still checked directly below. A present base object with a failed diff is
    # an actual audit error, not a shallow-checkout fallback.
    base_object = subprocess.run(
        ["git", "cat-file", "-e", f"{BASE_MAIN}^{{commit}}"], capture_output=True
    )
    if base_object.returncode == 0 or os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
        raise P44FMigrationAuditError(
            f"cannot verify P4.4F changed paths against the exact base: "
            f"{result.stderr.decode('utf-8', 'replace')}"
        )
    _require_exact_base_ancestry()
    return None


def _check_workflow_contract() -> None:
    workflow = Path(WORKFLOW_PATH).read_text(encoding="utf-8")
    canonical_marker = "if: ${{ inputs.timezone == 'UTC' && inputs.ccode3 == 'NGA' }}"
    legacy_marker = "if: ${{ inputs.timezone != 'UTC' || inputs.ccode3 != 'NGA' }}"
    canonical = workflow.split("- name: Issue current reviewed FotMob fixture bootstrap via canonical ingest", 1)
    legacy = workflow.split("- name: Issue current reviewed FotMob fixture bootstrap via legacy compatibility lane", 1)
    if (
        len(canonical) != 2
        or len(legacy) != 2
        or canonical_marker not in workflow
        or legacy_marker not in workflow
        or workflow.count(canonical_marker) != 1
        or workflow.count(legacy_marker) != 1
    ):
        raise P44FMigrationAuditError("canonical and legacy lanes are not exact complementary conditions")
    canonical_body = canonical[1].split(
        "- name: Issue current reviewed FotMob fixture bootstrap via legacy compatibility lane", 1
    )[0]
    legacy_body = legacy[1].split(
        "- name: Upload reviewed source receipt and exact raw evidence", 1
    )[0]
    triggers = re.search(r"(?ms)^on:\n(.*?)(?=^permissions:)", workflow)
    if (
        triggers is None
        or triggers.group(1).count("workflow_dispatch:") != 1
        or re.search(r"(?m)^  (?!workflow_dispatch:)[A-Za-z_][A-Za-z0-9_-]*:", triggers.group(1))
        or "      date:" not in triggers.group(1)
        or "      timezone:" not in triggers.group(1)
        or "      ccode3:" not in triggers.group(1)
    ):
        raise P44FMigrationAuditError("current-source workflow trigger/input contract changed")
    if (
        "permissions:\n  contents: read" not in workflow
        or "runs-on: ubuntu-latest" not in workflow
        or "timeout-minutes: 10" not in workflow
        or "name: current-fotmob-reviewed-source-${{ github.run_id }}" not in workflow
        or "retention-days: 7" not in workflow
        or "if: always()" not in workflow
        or "if-no-files-found: error" not in workflow
        or "artifacts/athena-ingest-workflow/" not in workflow
        or ".cache/athena-research/fotmob-data-matches-captures/" not in workflow
        or ".cache/athena-research/current-fotmob-reviewed-source/execution.json" not in workflow
    ):
        raise P44FMigrationAuditError("current-source workflow operational/artifact contract changed")
    if (
        "scripts/issue_current_fotmob_reviewed_source_via_ingest.py" not in canonical_body
        or "scripts/issue_current_fotmob_reviewed_source.py" in canonical_body
        or "scripts/issue_current_fotmob_reviewed_source.py" not in legacy_body
        or "scripts/issue_current_fotmob_reviewed_source_via_ingest.py" in legacy_body
        or "--execute-live-network" not in canonical_body
        or "--execute-live-network" not in legacy_body
        or "continue-on-error:" in workflow
        or "--retry" in workflow.lower()
        or "GITHUB_SHA" in canonical_body
        or "GITHUB_REF" in canonical_body
        or "${{ inputs." in canonical_body.split("run: |", 1)[-1]
        or "${{ inputs." in legacy_body.split("run: |", 1)[-1]
    ):
        raise P44FMigrationAuditError("workflow provider command has fallback, override, or direct input interpolation")
    if "--minimum-lead-seconds" in workflow or "--max-source-age-seconds" in workflow:
        raise P44FMigrationAuditError("workflow exposes forbidden PR243 policy overrides")
    run_bodies = re.findall(r"(?ms)^        run: \|\n(.*?)(?=^      - name:|\Z)", workflow)
    if any("||" in body or "&&" in body for body in run_bodies):
        raise P44FMigrationAuditError("provider shell command contains fallback/control chaining")


def _check_protected_sources() -> None:
    base_available = subprocess.run(
        ["git", "cat-file", "-e", f"{BASE_MAIN}^{{commit}}"], capture_output=True
    ).returncode == 0
    for path in PROTECTED_PATHS:
        expected = PROTECTED_IDENTITIES[path]
        if base_available and _identity_at(BASE_MAIN, path) != expected:
            raise P44FMigrationAuditError(f"pinned P4.4F base identity drifted: {path}")
        if _identity_at("HEAD", path) != expected:
            raise P44FMigrationAuditError(f"protected P4.4 dependency changed: {path}")
        if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", path]).returncode != 0:
            raise P44FMigrationAuditError(f"protected dependency has an unstaged change: {path}")
        if subprocess.run(["git", "diff", "--cached", "--quiet", "HEAD", "--", path]).returncode != 0:
            raise P44FMigrationAuditError(f"protected dependency has a staged change: {path}")


def _check_caller_inventory() -> None:
    cli_path = Path("scripts/issue_current_fotmob_reviewed_source_via_ingest.py")
    source = cli_path.read_text(encoding="utf-8")
    for forbidden in (
        "fetch_fotmob_data_matches",
        "write_data_matches_capture_directory",
        "issue_current_fotmob_reviewed_source(",
    ):
        if forbidden in source:
            raise P44FMigrationAuditError("canonical CLI duplicated or fell back to legacy provider acquisition")
    paths = _git("ls-files", "-z", "--", "*.py", "*.yml", "*.yaml").decode("utf-8").split("\0")
    caller = "scripts/issue_current_fotmob_reviewed_source_via_ingest.py"
    for relative in paths:
        if (
            not relative
            or relative.startswith(("tests/", "scripts/audit_"))
            or relative == caller
        ):
            continue
        if any(
            part in {".venv", "venv", "site-packages", "__pycache__"}
            for part in Path(relative).parts
        ):
            continue
        if relative.startswith("docs/"):
            continue
        if relative == WORKFLOW_PATH:
            continue
        content = Path(relative).read_text(encoding="utf-8")
        if caller in content:
            raise P44FMigrationAuditError(f"unexpected P4.4F caller reference: {relative}")


def audit(path: Path = RECEIPT_PATH, *, check_live: bool = True) -> dict[str, Any]:
    try:
        receipt = _load_json(path)
        validate_receipt(receipt)
        _check_operational_proof()
        expected_ledger, expected_snapshot, expected_receipt_value = build_evidence()
        if receipt != expected_receipt_value:
            raise P44FMigrationAuditError(
                "P4.4F receipt differs from rebuilt canonical evidence"
            )
        if _load_json(SNAPSHOT_PATH) != expected_snapshot:
            raise P44FMigrationAuditError(
                "P4.4F snapshot differs from exact cumulative ledger"
            )
        if check_live:
            p44d.audit(check_live=False)
            p44e.validate_receipt(
                json.loads(p44e.RECEIPT_PATH.read_text(encoding="utf-8")),
                check_live=False,
            )
            p44c.check_historical()
            p44b.check()
            ledger = evolution.validate_current_state()
            transitions = ledger.get("transitions", [])
            if (
                len(transitions) < 5
                or transitions[:5] != expected_ledger["transitions"]
            ):
                raise P44FMigrationAuditError(
                    "evolution ledger no longer preserves exact P4.4F prefix"
                )
            retirement_state = retirement.validate_retirement_history()
            if (
                retirement_state.get("canonical_sha256") != P43_RETIREMENT_SHA256
                or retirement_state.get("current_retired_workflow_count") != 3
            ):
                raise P44FMigrationAuditError("P4.3 retirement history changed")
            current_tree = _git(
                "rev-parse", "HEAD:.github/workflows"
            ).decode("ascii").strip()
            if current_tree != ledger.get("current_workflow_tree_sha1"):
                raise P44FMigrationAuditError(
                    "live workflow tree differs from reviewed evolution ledger"
                )
            workflow_count = sum(
                item.endswith((".yml", ".yaml"))
                for item in _git(
                    "ls-tree", "-r", "--name-only", "HEAD", ".github/workflows"
                ).decode("utf-8").splitlines()
            )
            if workflow_count != ledger.get("current_live_workflow_count"):
                raise P44FMigrationAuditError(
                    "live workflow count differs from reviewed evolution ledger"
                )
            fixture = Path(FIXTURE_PATH).read_bytes()
            if evolution.source_identity(fixture) != WORKFLOW_BEFORE:
                raise P44FMigrationAuditError(
                    "historical-before workflow fixture identity drifted"
                )
            if _identity_at("HEAD", FIXTURE_PATH) != WORKFLOW_BEFORE:
                raise P44FMigrationAuditError(
                    "historical-before fixture is not source-controlled at HEAD"
                )
            historical_after = _git(
                "cat-file", "-p", WORKFLOW_AFTER["git_blob_sha1"]
            )
            if evolution.source_identity(historical_after) != WORKFLOW_AFTER:
                raise P44FMigrationAuditError(
                    "historical P4.4F workflow-after blob identity drifted"
                )
            _check_protected_sources()
            _check_caller_inventory()
            if len(transitions) == 5:
                _require_exact_base_ancestry()
                changed = _changed_paths_from_exact_base()
                if changed is not None and not changed <= EXPECTED_CHANGED_PATHS:
                    raise P44FMigrationAuditError(
                        f"P4.4F changed paths exceed reviewed scope: "
                        f"{sorted(changed - EXPECTED_CHANGED_PATHS)}"
                    )
                if _identity_at("HEAD", WORKFLOW_PATH) != WORKFLOW_AFTER:
                    raise P44FMigrationAuditError(
                        "workflow final source identity differs from P4.4F receipt"
                    )
                _check_workflow_contract()
        return receipt
    except (OSError, ValueError, AssertionError, json.JSONDecodeError) as exc:
        if isinstance(exc, P44FMigrationAuditError):
            raise
        raise P44FMigrationAuditError(
            f"P4.4F evidence or live-state validation failed: {exc}"
        ) from exc

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        audit()
        print("P4.4F exact current-source caller migration audit: PASS")
        return 0
    except (P44FMigrationAuditError, OSError, ValueError) as exc:
        print(f"P4.4F audit: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
