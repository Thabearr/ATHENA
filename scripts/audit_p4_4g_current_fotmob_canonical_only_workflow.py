"""Fail-closed audit for P4.4G's canonical-only current FotMob workflow boundary."""

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
from scripts import audit_p4_4f_current_fotmob_exact_lane_caller_migration as p44f
from scripts import audit_p4_workflow_evolution_ledger as evolution


BASE_MAIN = "4cacd70378581a27785e4b10bd6205cde9241a41"
P44F_RECEIPT_SHA256 = "c5a3f66db6626acad2b3bcbcbadf5a5da62551cd4c2ffe4334b253e47ff2e60e"
P44F_SNAPSHOT_SHA256 = "0df166e1c71d67d2be5f1a5bffde5b467770dec8437d33675ec50e399812650a"
P43_RETIREMENT_SHA256 = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
WORKFLOW_TREE_BEFORE = "98133fd73c4b9d12eb9927016b071cb0fa7841b3"
WORKFLOW_TREE_AFTER = "d58f71b9ac653c8762f1d9b18eede15755ee1a76"
WORKFLOW_PATH = ".github/workflows/issue-current-fotmob-reviewed-source.yml"
WORKFLOW_BEFORE = {
    "git_blob_sha1": "7aaa7b9c3d26ff6454b26a094008c2bfd82c0b50",
    "source_sha256": "7d0d5ac1ca71722b560bb94ddeb7d5907d3824b74162976c2e3097c19a75243d",
}
WORKFLOW_AFTER = {
    "git_blob_sha1": "aaa913bc9636afbe2c4eb06d30f6c0fe61a434b0",
    "source_sha256": "37170b814b26f46cbdf33ed426b548e7e3edd731bef2457d96a52ef3798133bb",
}
BASE_EVOLUTION_SHA256 = P44F_SNAPSHOT_SHA256
P44F_SNAPSHOT_PATH = Path(
    "artifacts/architecture/p4_workflow_evolution_snapshots/p4_4f_current_fotmob_exact_lane_caller_migration_v1.json"
)
LEDGER_PATH = evolution.LEDGER_PATH
SNAPSHOT_PATH = Path(
    "artifacts/architecture/p4_workflow_evolution_snapshots/p4_4g_current_fotmob_canonical_only_workflow_v1.json"
)
RECEIPT_PATH = Path("artifacts/architecture/p4_4g_current_fotmob_canonical_only_workflow_v1.json")
HISTORY_PATH = Path("artifacts/architecture/p4_4g_current_fotmob_workflow_run_history_v1.json")
HISTORY_SHA256 = "b167073c9687d2ee65efdb46e2a49b867414d8f77a5fac7fa4ed1eae0000b5bd"
FIXTURE_PATH = (
    "tests/fixtures/architecture/revised_workflows/"
    "issue-current-fotmob-reviewed-source-pre-p4-4g-canonical-only.yml"
)
TRANSITION_ID = "P44G_CURRENT_FOTMOB_CANONICAL_ONLY_WORKFLOW_V1"
POLICY_ID = "ATHENA_P4_4G_CURRENT_FOTMOB_CANONICAL_ONLY_WORKFLOW_V1"
HISTORY_POLICY_ID = "ATHENA_P4_4G_CURRENT_FOTMOB_WORKFLOW_RUN_HISTORY_V1"
EXPECTED_CHANGED_PATHS = {
    WORKFLOW_PATH,
    "scripts/audit_p4_4g_current_fotmob_canonical_only_workflow.py",
    "tests/test_p4_4g_current_fotmob_canonical_only_workflow.py",
    "tests/test_issue_current_fotmob_workflow_contract.py",
    "scripts/audit_p4_4f_current_fotmob_exact_lane_caller_migration.py",
    "tests/test_p4_4f_current_fotmob_exact_lane_caller_migration.py",
    "artifacts/architecture/p4_4g_current_fotmob_canonical_only_workflow_v1.json",
    HISTORY_PATH.as_posix(),
    SNAPSHOT_PATH.as_posix(),
    LEDGER_PATH.as_posix(),
    FIXTURE_PATH,
    "docs/current_fotmob_reviewed_source.md",
    "docs/architecture/athena_ingest_workflow.md",
    "docs/architecture/workflow_capability_matrix.md",
    "tests/test_athena_ingest_architecture.py",
    "tests/test_p4_4c_scheduled_ingest_and_migration_review.py",
    "tests/test_p4_workflow_evolution_ledger.py",
    "tests/test_p4_4a_workflow_evolution_guard.py",
}
PROTECTED_PATHS = (
    ".github/workflows/athena-ingest.yml",
    "domain/ingest_contracts.py",
    "services/athena_ingest_service.py",
    "services/current_fotmob_ingest_compatibility.py",
    "services/current_fotmob_ingest_issuer.py",
    "scripts/issue_current_fotmob_reviewed_source.py",
    "scripts/issue_current_fotmob_reviewed_source_via_ingest.py",
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
    "scripts/issue_current_fotmob_reviewed_source_via_ingest.py": {
        "git_blob_sha1": "4a031358a1bf3bb13c77371f570d6436a17305c8",
        "source_sha256": "3c7f2d8705ca1e00ff2af744c212224edb77b165d06ac76eb45d0e1398b3be7e",
    },
}
FALSE_AUTHORITY_FIELDS = (
    "model_authority", "pricing_authority", "routing_authority", "portfolio_authority",
    "share_code_authority", "login_authority", "cookies_authority", "wallet_authority",
    "staking_authority", "wager_authority",
)


class P44GCanonicalOnlyWorkflowAuditError(AssertionError):
    """P4.4G workflow, caller, authority, or evidence chain differs from review."""


def _git(*args: str) -> bytes:
    result = subprocess.run(["git", *args], capture_output=True)
    if result.returncode:
        raise P44GCanonicalOnlyWorkflowAuditError(
            f"git {' '.join(args)} failed: {result.stderr.decode('utf-8', 'replace')}"
        )
    return result.stdout


def _load_json(path: Path) -> dict[str, Any]:
    # Restore canonical tracked bytes after Windows checkout EOL conversion;
    # this does not normalize any embedded source capture or receipt payload.
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    value = strict_json_loads(raw)
    if type(value) is not dict or canonical_json_bytes(value) != raw:
        raise P44GCanonicalOnlyWorkflowAuditError(f"canonical JSON evidence is invalid: {path}")
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
        "phase_id": "P4.4G",
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
        "p4_4f_receipt_sha256": P44F_RECEIPT_SHA256,
        "p4_4f_workflow_evolution_snapshot_sha256": P44F_SNAPSHOT_SHA256,
        "workflow_run_history_path": HISTORY_PATH.as_posix(),
        "workflow_run_history_sha256": HISTORY_SHA256,
        "workflow_path": WORKFLOW_PATH,
        "workflow_before_identity": dict(WORKFLOW_BEFORE),
        "workflow_after_identity": dict(WORKFLOW_AFTER),
        "workflow_count_before": 38,
        "workflow_count_after": 38,
        "workflow_tree_sha1_before": WORKFLOW_TREE_BEFORE,
        "workflow_tree_sha1_after": WORKFLOW_TREE_AFTER,
        "workflow_evolution_ledger_sha256_before": BASE_EVOLUTION_SHA256,
        "workflow_evolution_transition_count_before": 5,
        "workflow_evolution_transition_count_after": 6,
        "transition_id": TRANSITION_ID,
        "transition_operation": "MAINTENANCE_REVISE",
        "canonical_family": "ATHENA_INGEST_FUTURE",
        "p4_3_retirement_ledger_sha256": P43_RETIREMENT_SHA256,
        "canonical_supported_scope": {"date_count": 1, "provider": "fotmob", "timezone": "UTC", "ccode3": "NGA"},
        "historical_workflow_run_count": 12,
        "historical_workflow_dispatch_run_count": 12,
        "historical_exact_utc_nga_run_count": 12,
        "historical_noncanonical_timezone_or_ccode3_run_count": 0,
        "history_is_not_future_capability_authority": True,
        "legacy_noncanonical_lane_retained": False,
        "legacy_live_issuer_still_reachable_from_workflow": False,
        "legacy_cli_retained": True,
        "legacy_cli_modified": False,
        "legacy_cli_deletion_authorized": False,
        "full_legacy_workflow_equivalence_claimed": False,
        "legacy_workflow_retirement_authorized": False,
        "noncanonical_workflow_request_policy": "FAIL_CLOSED_NO_PROVIDER_ACQUISITION",
        "noncanonical_failure_status": "UNSUPPORTED_CURRENT_FOTMOB_WORKFLOW_SCOPE_REQUIRES_UTC_NGA",
        "noncanonical_failure_receipt_binds_request": True,
        "noncanonical_provider_request_count": 0,
        "trigger_surface_changed": False,
        "permissions_changed": False,
        "concurrency_changed": False,
        "provider_acquisition_authority_changed": False,
        "exact_utc_nga_provider_implementation_changed": False,
        "workflow_supported_provider_scope_narrowed": True,
        "owner_merge_required_to_activate_scope_narrowing": True,
        "live_behavior_changes_if_merged": True,
        "artifact_name_preserved": True,
        "artifact_name": "current-fotmob-reviewed-source-${{ github.run_id }}",
        "artifact_retention_days": 7,
        "execution_json_path": ".cache/athena-research/current-fotmob-reviewed-source/execution.json",
        "canonical_artifact_root_uploaded": "artifacts/athena-ingest-workflow/",
        "legacy_capture_root_upload_path_retained": ".cache/athena-research/fotmob-data-matches-captures/",
        "canonical_source_copied_or_rewritten": False,
        "acquisition_retry_added": False,
        "fallback_after_canonical_acquisition": False,
        "max_provider_requests_canonical_dispatch_path": 1,
        "provider_acquisition_during_pr": False,
        "provider_request_count_during_pr": 0,
        "workflow_dispatch_during_pr": False,
        "new_live_operational_proof_required": False,
        "p4_4f_operational_proof_reused": True,
        "p4_4f_operational_proof_receipt_path": p44f.PROOF_PATH.as_posix(),
        "p4_4f_operational_proof_receipt_sha256": p44f.PROOF_FILE_SHA256,
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
        "source_review_counter_while_unmerged": "3/5",
        "source_review_counter_if_merged": "4/5",
        "reviewed_workflow_transition": _transition_intent(),
    }


def build_evidence() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build the reviewed P4.4G transition from the immutable P4.4F checkpoint."""
    historical = _load_json(P44F_SNAPSHOT_PATH)
    if (
        historical.get("canonical_sha256") != BASE_EVOLUTION_SHA256
        or evolution.canonical_sha256(historical) != BASE_EVOLUTION_SHA256
        or len(historical.get("transitions", [])) != 5
    ):
        raise P44GCanonicalOnlyWorkflowAuditError("P4.4F cumulative checkpoint is not the exact P4.4G base")
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
        raise P44GCanonicalOnlyWorkflowAuditError("P4.4G receipt fields differ from the exact schema")
    if value != expected:
        raise P44GCanonicalOnlyWorkflowAuditError("P4.4G receipt differs from reviewed semantics")
    if value.get("canonical_sha256") != evolution.canonical_sha256(value):
        raise P44GCanonicalOnlyWorkflowAuditError("P4.4G receipt self-hash mismatch")
    return value


def _check_operational_proof() -> dict[str, Any]:
    try:
        return p44f._check_operational_proof()
    except (AssertionError, OSError, ValueError) as exc:
        raise P44GCanonicalOnlyWorkflowAuditError(f"P4.4F operational proof no longer validates: {exc}") from exc


def _check_history_evidence() -> dict[str, Any]:
    history = _load_json(HISTORY_PATH)
    unsigned = {
        key: item for key, item in history.items() if key != "canonical_sha256"
    }
    if history.get("canonical_sha256") != HISTORY_SHA256:
        raise P44GCanonicalOnlyWorkflowAuditError(
            "P4.4G workflow-history identity differs"
        )
    if hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest() != HISTORY_SHA256:
        raise P44GCanonicalOnlyWorkflowAuditError(
            "P4.4G workflow-history self-hash mismatch"
        )
    rows = history.get("runs")
    if (
        history.get("policy_id") != HISTORY_POLICY_ID
        or history.get("workflow_id") != 343652927
        or history.get("workflow_path") != WORKFLOW_PATH
        or history.get("captured_at_utc") != "2026-09-24T22:28:53.032418Z"
        or history.get("api_reported_total_count") != 12
        or history.get("all_api_returned_runs_included") is not True
        or history.get("observation_semantics")
        != "ALL_GITHUB_ACTIONS_WORKFLOW_RUNS_RETURNED_AT_CAPTURE"
        or history.get("run_inputs_observed_from_authenticated_job_logs") is not True
        or history.get("provider_acquisition_performed_by_review") is not False
        or history.get("workflow_dispatch_performed_by_review") is not False
        or history.get("observed_run_count") != 12
        or history.get("workflow_dispatch_run_count") != 12
        or history.get("successful_run_count") != 11
        or history.get("failed_run_count") != 1
        or history.get("exact_utc_nga_run_count") != 12
        or history.get("noncanonical_timezone_or_ccode3_run_count") != 0
        or history.get("all_observed_runs_exact_utc_nga") is not True
        or history.get("no_observed_noncanonical_workflow_use") is not True
        or history.get("history_is_not_future_capability_authority") is not True
        or not isinstance(rows, list)
        or len(rows) != 12
    ):
        raise P44GCanonicalOnlyWorkflowAuditError(
            "P4.4G workflow-history semantics differ"
        )
    expected_ids = [
        34761344932, 34761298182, 34761226581, 34761167767,
        34761120253, 34761069153, 34761009105, 34726297627,
        34726254770, 34726207087, 34726164828, 34726086987,
    ]
    if [row.get("run_id") for row in rows] != expected_ids:
        raise P44GCanonicalOnlyWorkflowAuditError(
            "P4.4G workflow-history run set differs"
        )
    if len({row.get("job_id") for row in rows}) != 12:
        raise P44GCanonicalOnlyWorkflowAuditError(
            "P4.4G workflow-history job identities are not unique"
        )
    for row in rows:
        if (
            row.get("event") != "workflow_dispatch"
            or row.get("timezone") != "UTC"
            or row.get("ccode3") != "NGA"
            or re.fullmatch(r"\d{8}", str(row.get("date", ""))) is None
            or row.get("conclusion") not in {"success", "failure"}
        ):
            raise P44GCanonicalOnlyWorkflowAuditError(
                "P4.4G history contains a noncanonical or malformed observed run"
            )
    if sum(row["conclusion"] == "success" for row in rows) != 11:
        raise P44GCanonicalOnlyWorkflowAuditError(
            "P4.4G workflow-history success count differs"
        )
    return history

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
            except (OSError, json.JSONDecodeError, P44GCanonicalOnlyWorkflowAuditError):
                valid = False
    if not valid:
        raise P44GCanonicalOnlyWorkflowAuditError("P4.4G branch is not based on exact authoritative main")


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
        raise P44GCanonicalOnlyWorkflowAuditError(
            f"cannot verify P4.4G changed paths against the exact base: "
            f"{result.stderr.decode('utf-8', 'replace')}"
        )
    _require_exact_base_ancestry()
    return None


def _check_workflow_contract() -> None:
    workflow = Path(WORKFLOW_PATH).read_text(encoding="utf-8")
    canonical_marker = "if: ${{ inputs.timezone == 'UTC' && inputs.ccode3 == 'NGA' }}"
    reject_marker = "if: ${{ inputs.timezone != 'UTC' || inputs.ccode3 != 'NGA' }}"
    canonical = workflow.split(
        "- name: Issue current reviewed FotMob fixture bootstrap via canonical ingest", 1
    )
    rejected = workflow.split(
        "- name: Reject unsupported noncanonical current-source request", 1
    )
    if (
        len(canonical) != 2
        or len(rejected) != 2
        or workflow.count(canonical_marker) != 1
        or workflow.count(reject_marker) != 1
    ):
        raise P44GCanonicalOnlyWorkflowAuditError(
            "canonical and fail-closed conditions are not exact complements"
        )
    canonical_body = canonical[1].split(
        "- name: Reject unsupported noncanonical current-source request", 1
    )[0]
    reject_body = rejected[1].split(
        "- name: Upload reviewed source receipt and exact raw evidence", 1
    )[0]
    triggers = re.search(r"(?ms)^on:\n(.*?)(?=^permissions:)", workflow)
    if (
        triggers is None
        or triggers.group(1).count("workflow_dispatch:") != 1
        or re.search(
            r"(?m)^  (?!workflow_dispatch:)[A-Za-z_][A-Za-z0-9_-]*:",
            triggers.group(1),
        )
        or triggers.group(1).count("      date:") != 1
        or triggers.group(1).count("      timezone:") != 1
        or triggers.group(1).count("      ccode3:") != 1
        or "default: UTC" not in triggers.group(1)
        or "default: NGA" not in triggers.group(1)
    ):
        raise P44GCanonicalOnlyWorkflowAuditError(
            "current-source workflow trigger/input contract changed"
        )
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
        raise P44GCanonicalOnlyWorkflowAuditError(
            "current-source workflow operational/artifact contract changed"
        )
    if (
        "scripts/issue_current_fotmob_reviewed_source_via_ingest.py" not in canonical_body
        or "--execute-live-network" not in canonical_body
        or "scripts/issue_current_fotmob_reviewed_source.py" in workflow
        or "scripts/issue_current_fotmob_reviewed_source_via_ingest.py" in reject_body
        or "--execute-live-network" in reject_body
        or "UNSUPPORTED_CURRENT_FOTMOB_WORKFLOW_SCOPE_REQUIRES_UTC_NGA" not in reject_body
        or "ATHENA_FOTMOB_REQUEST_DATE: ${{ inputs.date }}" not in reject_body
        or "ATHENA_FOTMOB_REQUEST_TIMEZONE: ${{ inputs.timezone }}" not in reject_body
        or "ATHENA_FOTMOB_REQUEST_CCODE3: ${{ inputs.ccode3 }}" not in reject_body
        or 'os.environ["ATHENA_FOTMOB_REQUEST_DATE"]' not in reject_body
        or 'os.environ["ATHENA_FOTMOB_REQUEST_TIMEZONE"]' not in reject_body
        or 'os.environ["ATHENA_FOTMOB_REQUEST_CCODE3"]' not in reject_body
        or '"provider": "fotmob"' not in reject_body
        or '"wager_placed": False' not in reject_body
        or "exit 1" not in reject_body
        or "continue-on-error:" in workflow
        or "--retry" in workflow.lower()
        or "GITHUB_SHA" in canonical_body
        or "GITHUB_REF" in canonical_body
    ):
        raise P44GCanonicalOnlyWorkflowAuditError(
            "workflow canonical/fail-closed provider contract changed"
        )
    if "--minimum-lead-seconds" in workflow or "--max-source-age-seconds" in workflow:
        raise P44GCanonicalOnlyWorkflowAuditError(
            "workflow exposes forbidden PR243 policy overrides"
        )
    run_bodies = re.findall(
        r"(?ms)^        run: \|\n(.*?)(?=^      - name:|\Z)", workflow
    )
    if any("||" in body or "&&" in body for body in run_bodies):
        raise P44GCanonicalOnlyWorkflowAuditError(
            "provider shell command contains fallback/control chaining"
        )

def _check_protected_sources() -> None:
    base_available = subprocess.run(
        ["git", "cat-file", "-e", f"{BASE_MAIN}^{{commit}}"], capture_output=True
    ).returncode == 0
    for path in PROTECTED_PATHS:
        expected = PROTECTED_IDENTITIES[path]
        if base_available and _identity_at(BASE_MAIN, path) != expected:
            raise P44GCanonicalOnlyWorkflowAuditError(f"pinned P4.4G base identity drifted: {path}")
        if _identity_at("HEAD", path) != expected:
            raise P44GCanonicalOnlyWorkflowAuditError(f"protected P4.4 dependency changed: {path}")
        if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", path]).returncode != 0:
            raise P44GCanonicalOnlyWorkflowAuditError(f"protected dependency has an unstaged change: {path}")
        if subprocess.run(["git", "diff", "--cached", "--quiet", "HEAD", "--", path]).returncode != 0:
            raise P44GCanonicalOnlyWorkflowAuditError(f"protected dependency has a staged change: {path}")


def _check_caller_inventory() -> None:
    canonical_cli = Path("scripts/issue_current_fotmob_reviewed_source_via_ingest.py")
    source = canonical_cli.read_text(encoding="utf-8")
    for forbidden in ("fetch_fotmob_data_matches", "write_data_matches_capture_directory", "issue_current_fotmob_reviewed_source("):
        if forbidden in source:
            raise P44GCanonicalOnlyWorkflowAuditError("canonical CLI duplicated or fell back to legacy provider acquisition")
    if not Path("scripts/issue_current_fotmob_reviewed_source.py").exists():
        raise P44GCanonicalOnlyWorkflowAuditError("legacy CLI was deleted instead of retained for history/rollback")
    legacy_ref = "scripts/issue_current_fotmob_reviewed_source.py"
    for workflow_path in Path(".github/workflows").glob("*.yml"):
        if legacy_ref in workflow_path.read_text(encoding="utf-8"):
            raise P44GCanonicalOnlyWorkflowAuditError(f"legacy current-source CLI remains workflow-live: {workflow_path}")
    caller_ref = "scripts/issue_current_fotmob_reviewed_source_via_ingest.py"
    runtime_refs = []
    for relative in _git("ls-files", "-z", "--", "*.py", "*.yml", "*.yaml").decode("utf-8").split("\0"):
        if not relative or relative.startswith(("tests/", "docs/", "scripts/audit_")) or relative == caller_ref:
            continue
        if any(part in {".venv", "venv", "site-packages", "__pycache__"} for part in Path(relative).parts):
            continue
        if caller_ref in Path(relative).read_text(encoding="utf-8"):
            runtime_refs.append(relative)
    if runtime_refs != [WORKFLOW_PATH]:
        raise P44GCanonicalOnlyWorkflowAuditError(f"canonical current-source workflow caller set differs: {runtime_refs}")


def audit(path: Path = RECEIPT_PATH, *, check_live: bool = True) -> dict[str, Any]:
    try:
        receipt = _load_json(path)
        validate_receipt(receipt)
        _check_history_evidence()
        _check_operational_proof()
        expected_ledger, expected_snapshot, expected_receipt_value = build_evidence()
        if receipt != expected_receipt_value:
            raise P44GCanonicalOnlyWorkflowAuditError(
                "P4.4G receipt differs from rebuilt canonical evidence"
            )
        if _load_json(LEDGER_PATH) != expected_ledger:
            raise P44GCanonicalOnlyWorkflowAuditError(
                "current evolution ledger differs from exact P4.4G state"
            )
        if _load_json(SNAPSHOT_PATH) != expected_snapshot:
            raise P44GCanonicalOnlyWorkflowAuditError(
                "P4.4G snapshot differs from exact cumulative ledger"
            )
        if check_live:
            _require_exact_base_ancestry()
            p44f.validate_receipt(
                json.loads(p44f.RECEIPT_PATH.read_text(encoding="utf-8"))
            )
            ledger = evolution.validate_current_state()
            if (
                len(ledger.get("transitions", [])) != 6
                or ledger["transitions"][:5]
                != expected_ledger["transitions"][:5]
                or ledger["transitions"][5]
                != expected_ledger["transitions"][5]
            ):
                raise P44GCanonicalOnlyWorkflowAuditError(
                    "evolution ledger lacks the exact P4.4F prefix plus P4.4G transition"
                )
            retirement_state = retirement.validate_retirement_history()
            if (
                retirement_state.get("canonical_sha256") != P43_RETIREMENT_SHA256
                or retirement_state.get("current_retired_workflow_count") != 3
            ):
                raise P44GCanonicalOnlyWorkflowAuditError(
                    "P4.3 retirement history changed"
                )
            current_tree = _git("rev-parse", "HEAD:.github/workflows").decode("ascii").strip()
            if current_tree != WORKFLOW_TREE_AFTER:
                raise P44GCanonicalOnlyWorkflowAuditError(
                    "final workflow tree differs from P4.4G receipt"
                )
            workflow_count = sum(
                item.endswith((".yml", ".yaml"))
                for item in _git(
                    "ls-tree", "-r", "--name-only", "HEAD", ".github/workflows"
                ).decode("utf-8").splitlines()
            )
            if workflow_count != 38:
                raise P44GCanonicalOnlyWorkflowAuditError(
                    "workflow count is not 38"
                )
            changed = _changed_paths_from_exact_base()
            if changed is not None and not changed <= EXPECTED_CHANGED_PATHS:
                raise P44GCanonicalOnlyWorkflowAuditError(
                    f"P4.4G changed paths exceed reviewed scope: "
                    f"{sorted(changed - EXPECTED_CHANGED_PATHS)}"
                )
            if _identity_at("HEAD", WORKFLOW_PATH) != WORKFLOW_AFTER:
                raise P44GCanonicalOnlyWorkflowAuditError(
                    "workflow final source identity differs from receipt"
                )
            fixture = Path(FIXTURE_PATH).read_bytes()
            if evolution.source_identity(fixture) != WORKFLOW_BEFORE:
                raise P44GCanonicalOnlyWorkflowAuditError(
                    "historical-before workflow fixture identity drifted"
                )
            if _identity_at("HEAD", FIXTURE_PATH) != WORKFLOW_BEFORE:
                raise P44GCanonicalOnlyWorkflowAuditError(
                    "historical-before fixture is not source-controlled at HEAD"
                )
            _check_protected_sources()
            _check_workflow_contract()
            _check_caller_inventory()
        return receipt
    except (OSError, ValueError, AssertionError, json.JSONDecodeError) as exc:
        if isinstance(exc, P44GCanonicalOnlyWorkflowAuditError):
            raise
        raise P44GCanonicalOnlyWorkflowAuditError(
            f"P4.4G evidence or live-state validation failed: {exc}"
        ) from exc

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        audit()
        print("P4.4G canonical-only current-source workflow audit: PASS")
        return 0
    except (P44GCanonicalOnlyWorkflowAuditError, OSError, ValueError) as exc:
        print(f"P4.4G audit: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
