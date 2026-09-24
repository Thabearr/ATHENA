"""P4.4C scheduled-ingest activation and legacy capability review evidence."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from scripts import audit_p4_3_workflow_retirement_ledger as retirement
from scripts import audit_p4_4b_athena_ingest_workflow as p44b
from scripts import audit_p4_workflow_evolution_ledger as evolution


BASE_MAIN = "ef540c8b6483f85eebf048636eb3b65ab0894f43"
P44B_LEDGER_SHA256 = "3c06063d4cc57e71d712e95ba5fee81c5f9656de1ea045d56ec5ef7cabae5b6b"
P44B_WORKFLOW_TREE = "8a65d5b4ed767d71d77c729d91f3fc95daa6d10a"
P44B_WORKFLOW_BLOB = "7f5fecabd8ada0ccac1fb35a8d2749601cc293c7"
P44B_WORKFLOW_SOURCE = "acdb74d306e7cd2220123186112ee5ae197b7719761e304e7e3cd08dea628cbe"
P44B_RECEIPT_SHA256 = "557e2c2dc78ea18ce12705c1418f8deff3b2b7611e7fb1daf90a75740b75a999"
P43_LEDGER_SHA256 = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
MATRIX_PATH = retirement.MATRIX_PATH
MIGRATION_PATH = Path("artifacts/architecture/p4_4c_ingest_capability_migration_review_v1.json")
RECEIPT_PATH = Path("artifacts/architecture/p4_4c_athena_ingest_schedule_and_migration_review_v1.json")
SNAPSHOT_PATH = Path("artifacts/architecture/p4_workflow_evolution_snapshots/p4_4c_athena_ingest_schedule_v1.json")
WORKFLOW_PATH = ".github/workflows/athena-ingest.yml"
TRANSITION_ID = "P44C_ATHENA_INGEST_SCHEDULE_REVISE_V1"
POLICY_ID = "ATHENA_P4_4C_SCHEDULED_INGEST_AND_MIGRATION_REVIEW_V1"
MIGRATION_POLICY_ID = "ATHENA_P4_4C_INGEST_CAPABILITY_MIGRATION_REVIEW_V1"
EXPECTED_PATHS = (
    ".github/workflows/build-historical-warehouse.yml",
    ".github/workflows/execute-fotmob-ordinary-ft-source-history-campaign.yml",
    ".github/workflows/execute-fotmob-prospective-player-context-campaign.yml",
    ".github/workflows/issue-current-fotmob-reviewed-source.yml",
    ".github/workflows/prepare-canonical-drive-transfer.yml",
)
DISPOSITIONS = {
    EXPECTED_PATHS[0]: "RETAIN_DISTINCT_HISTORICAL_WAREHOUSE_CAPABILITY",
    EXPECTED_PATHS[1]: "RETAIN_RESEARCH_CAMPAIGN_NOT_CANONICAL_INGEST_EQUIVALENT",
    EXPECTED_PATHS[2]: "RETAIN_PROSPECTIVE_PLAYER_CONTEXT_RESEARCH_CAPABILITY",
    EXPECTED_PATHS[3]: "RETAIN_PENDING_EXACT_CURRENT_SOURCE_COMPATIBILITY_MIGRATION",
    EXPECTED_PATHS[4]: "RETAIN_DISTINCT_ARCHIVE_TRANSFER_CAPABILITY",
}
RUN_HISTORY = {
    EXPECTED_PATHS[0]: {
        "latest_run": {"run_id": 33541247244, "event": "push", "status": "completed", "conclusion": "success", "head_sha": "5c0ccfd21e421c432217bf229ca94ab71f783a1f", "head_branch": "main", "url": "https://github.com/Thabearr/ATHENA/actions/runs/33541247244"},
        "latest_successful_run": {"run_id": 33541247244, "event": "push", "status": "completed", "conclusion": "success", "head_sha": "5c0ccfd21e421c432217bf229ca94ab71f783a1f", "head_branch": "main", "url": "https://github.com/Thabearr/ATHENA/actions/runs/33541247244"},
    },
    EXPECTED_PATHS[1]: {
        "latest_run": {"run_id": 35936265994, "event": "issue_comment", "status": "completed", "conclusion": "skipped", "head_sha": "cb273ad4d0ca44f5b5fb8615ab99f1b9432dc8a3", "head_branch": "main", "url": "https://github.com/Thabearr/ATHENA/actions/runs/35936265994"},
        "latest_successful_run": {"run_id": 31887523012, "event": "issue_comment", "status": "completed", "conclusion": "success", "head_sha": "12a32de1cca8ffb657f67fa4a8d3106aec6ce31b", "head_branch": "main", "url": "https://github.com/Thabearr/ATHENA/actions/runs/31887523012"},
    },
    EXPECTED_PATHS[2]: {
        "latest_run": {"run_id": 35936241499, "event": "pull_request", "status": "completed", "conclusion": "skipped", "head_sha": "8f78f019ce2d306c2d17f1e8e27d0d95c9cff283", "head_branch": "feat/architecture-p4.4b-canonical-athena-ingest", "url": "https://github.com/Thabearr/ATHENA/actions/runs/35936241499"},
        "latest_successful_run": {"run_id": 32410775191, "event": "pull_request", "status": "completed", "conclusion": "success", "head_sha": "46f76e8033d3d498131c6f893111b437b6b459a9", "head_branch": "evidence/fotmob-prospective-player-context-campaign", "url": "https://github.com/Thabearr/ATHENA/actions/runs/32410775191"},
    },
    EXPECTED_PATHS[3]: {
        "latest_run": {"run_id": 34761344932, "event": "workflow_dispatch", "status": "completed", "conclusion": "success", "head_sha": "7e50835f1ffa85c96553d7da29ce5a44502ec182", "head_branch": "main", "url": "https://github.com/Thabearr/ATHENA/actions/runs/34761344932"},
        "latest_successful_run": {"run_id": 34761344932, "event": "workflow_dispatch", "status": "completed", "conclusion": "success", "head_sha": "7e50835f1ffa85c96553d7da29ce5a44502ec182", "head_branch": "main", "url": "https://github.com/Thabearr/ATHENA/actions/runs/34761344932"},
    },
    EXPECTED_PATHS[4]: {
        "latest_run": {"run_id": 32635585415, "event": "push", "status": "completed", "conclusion": "success", "head_sha": "d2145f0e5ba74fb516797768f5d8a8681a3c3ffa", "head_branch": "main", "url": "https://github.com/Thabearr/ATHENA/actions/runs/32635585415"},
        "latest_successful_run": {"run_id": 32635585415, "event": "push", "status": "completed", "conclusion": "success", "head_sha": "d2145f0e5ba74fb516797768f5d8a8681a3c3ffa", "head_branch": "main", "url": "https://github.com/Thabearr/ATHENA/actions/runs/32635585415"},
    },
}
ASSESSMENTS = {
    EXPECTED_PATHS[0]: (
        "Canonical ingest captures bounded daily FotMob match data only; it does not build, enrich, audit, or export the multi-source historical warehouse.",
        ["SQLite/CSV/completeness warehouse outputs", "Football-Data/OpenFootball/global-backbone imports and enrichment", "prepare-canonical-drive-transfer consumes athena-history-sqlite"],
    ),
    EXPECTED_PATHS[1]: (
        "Canonical ingest does not reproduce the owner-controlled long-running ordinary-FT source-history campaign or its control-PR evidence contract.",
        ["one-shot issue-comment authorization", "campaign-specific preflight/status and execution metadata", "330-minute run and campaign artifact/reporting semantics"],
    ),
    EXPECTED_PATHS[2]: (
        "Canonical ingest does not capture the fixed prospective player-context campaign or its continuation artifact consumed by downstream verification workflows.",
        ["fixed prospective player-context request and stage", "continuation from an exact prior artifact", "three downstream workflow consumers and campaign verification"],
    ),
    EXPECTED_PATHS[3]: (
        "There is one-date FotMob capture overlap, but no reviewed adapter preserves the legacy configurable request and fixture-bootstrap contract.",
        ["legacy date input versus canonical dates list", "legacy timezone/ccode3 inputs versus canonical fixed UTC/NGA", "legacy artifact name/layout and receipt/output semantics", "fixture policy/catalog/bootstrap behavior beyond canonical source/update/replay evidence"],
    ),
    EXPECTED_PATHS[4]: (
        "Canonical ingest does not download and split the historical SQLite archive, publish its pointer, or upload transfer parts.",
        ["historical warehouse artifact ID/run ID inputs", "contents:write and actions:read permissions", "archive integrity, 23-part transfer manifest and pointer publication"],
    ),
}


def _git(*args: str) -> bytes:
    result = subprocess.run(["git", *args], capture_output=True)
    if result.returncode:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr.decode('utf-8', 'replace')}")
    return result.stdout


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _workflow_tree_from_index() -> str:
    tree = _git("write-tree").decode("ascii").strip()
    return _git("rev-parse", f"{tree}:.github/workflows").decode("ascii").strip()


def _current_identity(path: str) -> dict[str, str]:
    raw = _git("show", f"HEAD:{path}")
    return evolution.source_identity(raw)


def build_migration_review() -> dict[str, Any]:
    matrix = _load(MATRIX_PATH)
    if matrix.get("canonical_sha256") != retirement.MATRIX_SHA256 or retirement.canonical_sha256(matrix) != retirement.MATRIX_SHA256:
        raise AssertionError("frozen P4.3A matrix identity changed")
    rows = {row["workflow_path"]: row for row in matrix["workflow_rows"] if row.get("successor_family") == "ATHENA_INGEST_FUTURE"}
    if tuple(sorted(rows)) != tuple(sorted(EXPECTED_PATHS)):
        raise AssertionError("frozen ATHENA_INGEST_FUTURE path inventory changed")
    reviewed_rows: list[dict[str, Any]] = []
    for path in EXPECTED_PATHS:
        row = rows[path]
        frozen_identity = {key: row[key] for key in evolution.IDENTITY_KEYS}
        current_identity = _current_identity(path)
        if current_identity != frozen_identity:
            raise AssertionError(f"P4.3A ingest-future workflow has unreviewed source drift: {path}")
        if not Path(path).is_file():
            raise AssertionError(f"P4.3A ingest-future workflow is missing: {path}")
        dependency = row.get("dependency_evidence", {})
        assessment, differences = ASSESSMENTS[path]
        reviewed_rows.append({
            "workflow_path": path,
            "frozen_p4_3a_source_identity": frozen_identity,
            "current_live_source_identity": current_identity,
            "path_exists": True,
            "trigger_types": row.get("trigger_types", []),
            "permissions": row.get("permissions", {}),
            "inputs": row.get("workflow_dispatch_inputs", {}),
            "outputs_artifact_names": row.get("outputs_or_receipts", []),
            "artifact_upload_names": dependency.get("artifact_upload_names", []),
            "timeout_minutes": row.get("job_timeout_minutes", []),
            "concurrency_group": row.get("concurrency_group"),
            "latest_successful_run": RUN_HISTORY[path]["latest_successful_run"],
            "latest_run": RUN_HISTORY[path]["latest_run"],
            "unique_responsibilities": row.get("unique_responsibilities", []),
            "known_workflow_consumers": dependency.get("known_workflow_consumers", []),
            "known_artifact_and_document_consumers": dependency.get("consumer_sources", []),
            "canonical_athena_ingest_coverage_assessment": assessment,
            "exact_unresolved_differences": differences,
            "reviewed_disposition": DISPOSITIONS[path],
            "equivalence_claimed": False,
            "retirement_authorized": False,
        })
    artifact: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": MIGRATION_POLICY_ID,
        "repository_base_main_sha": BASE_MAIN,
        "p4_3a_matrix_sha256": retirement.MATRIX_SHA256,
        "p4_4b_receipt_sha256": P44B_RECEIPT_SHA256,
        "p4_4b_canonical_ingest_identity": {
            "workflow_path": WORKFLOW_PATH,
            "git_blob_sha1": P44B_WORKFLOW_BLOB,
            "source_sha256": P44B_WORKFLOW_SOURCE,
        },
        "github_actions_history_rechecked_read_only": True,
        "workflow_rows": reviewed_rows,
        "reviewed_workflow_count": len(reviewed_rows),
        "equivalence_claim_count": 0,
        "retirement_authorization_count": 0,
        "canonical_sha256": "",
    }
    artifact["canonical_sha256"] = evolution.canonical_sha256(artifact)
    return artifact


def build_evidence(migration_review: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    if _git("rev-parse", "origin/main").decode("ascii").strip() != BASE_MAIN:
        raise AssertionError("authoritative main moved from the P4.4C reviewed base")
    if migration_review is None:
        migration_review = _load(MIGRATION_PATH)
    if migration_review.get("canonical_sha256") != evolution.canonical_sha256(migration_review):
        raise AssertionError("P4.4C migration-review artifact is not canonical")
    base_ledger = _load(evolution.LEDGER_PATH)
    if (
        base_ledger.get("canonical_sha256") != P44B_LEDGER_SHA256
        or evolution.canonical_sha256(base_ledger) != P44B_LEDGER_SHA256
        or len(base_ledger.get("transitions", [])) != 3
        or base_ledger.get("current_workflow_tree_sha1") != P44B_WORKFLOW_TREE
    ):
        raise AssertionError("P4.4B evolution checkpoint changed")
    before = _git("show", f"HEAD:{WORKFLOW_PATH}")
    if evolution.source_identity(before) != {"git_blob_sha1": P44B_WORKFLOW_BLOB, "source_sha256": P44B_WORKFLOW_SOURCE}:
        raise AssertionError("P4.4B athena-ingest before identity changed")
    after = _git("show", f":{WORKFLOW_PATH}")
    after_identity = evolution.source_identity(after)
    final_tree = _workflow_tree_from_index()
    transition: dict[str, Any] = {
        "transition_id": TRANSITION_ID,
        "operation": "REVISE",
        "workflow_path": WORKFLOW_PATH,
        "before": {"git_blob_sha1": P44B_WORKFLOW_BLOB, "source_sha256": P44B_WORKFLOW_SOURCE},
        "after": after_identity,
        "phase_id": "P4.4C",
        "canonical_family": "ATHENA_INGEST",
        "evidence_receipt_path": RECEIPT_PATH.as_posix(),
        "checkpoint_snapshot_path": SNAPSHOT_PATH.as_posix(),
    }
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository_base_main_sha": BASE_MAIN,
        "source_review_counter_while_unmerged": "4/5",
        "source_review_counter_if_merged": "5/5",
        "p4_4b_receipt_sha256": P44B_RECEIPT_SHA256,
        "p4_3_retirement_ledger_sha256": P43_LEDGER_SHA256,
        "migration_review_artifact_path": MIGRATION_PATH.as_posix(),
        "migration_review_artifact_sha256": migration_review["canonical_sha256"],
        "reviewed_workflow_transition": copy.deepcopy(transition),
        "workflow_evolution_checkpoint_path": SNAPSHOT_PATH.as_posix(),
        "workflow_evolution_ledger_sha256": "0" * 64,
        "workflow_path": WORKFLOW_PATH,
        "workflow_before_identity": {"git_blob_sha1": P44B_WORKFLOW_BLOB, "source_sha256": P44B_WORKFLOW_SOURCE},
        "workflow_after_identity": after_identity,
        "scheduled_acquisition_enabled": True,
        "schedule_cron": "0 8 * * *",
        "schedule_timezone": "UTC",
        "scheduled_date_count": 1,
        "scheduled_max_provider_requests": 1,
        "manual_max_dates": 7,
        "provider_scope": ["fotmob"],
        "timezone": "UTC",
        "ccode3": "NGA",
        "service_budget_seconds": 900,
        "workflow_timeout_minutes": 20,
        "finalization_headroom_seconds": 300,
        "acquisition_retry_count": 0,
        "offline_replay_supported": True,
        "p4_3_retirements_added": 0,
        "legacy_ingest_workflows_retired": 0,
        "workflow_count_before": 38,
        "workflow_count_after": 38,
        "transition_count_before": 3,
        "transition_count_after": 4,
        "model_authority": False,
        "routing_authority": False,
        "portfolio_authority": False,
        "share_code_authority": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "wager": False,
        "provider_acquisition_during_pr": False,
        "provider_request_count_during_pr": 0,
        "workflow_dispatch_during_pr": False,
        "automatic_acquisition_active_on_main_while_pr_open": False,
        "automatic_daily_side_effect_if_merged": "one current UTC date and at most one FotMob request per scheduled run",
        "backfill_authority": False,
        "authority_expansion": False,
        "workflow_tree_before_sha1": P44B_WORKFLOW_TREE,
        "workflow_tree_after_sha1": final_tree,
        "p4_4_overall_complete": False,
        "architecture_checkpoint_e_fully_claimed": False,
        "mandatory_source_reread_required_after_merge": True,
        "next_required_step_if_merged": "MANDATORY_5_OF_5_ARCHITECTURE_SOURCE_REREAD_BEFORE_NEXT_REMEDIATION_MISSION",
    }
    transition["evidence_body_sha256"] = evolution.receipt_evidence_body_sha256(receipt)
    ledger = copy.deepcopy(base_ledger)
    ledger["transitions"].append(transition)
    ledger["current_live_workflow_count"] = 38
    ledger["current_workflow_tree_sha1"] = final_tree
    ledger["canonical_sha256"] = evolution.canonical_sha256(ledger)
    receipt["workflow_evolution_ledger_sha256"] = ledger["canonical_sha256"]
    receipt["canonical_sha256"] = evolution.canonical_sha256(receipt)
    return ledger, receipt


def write_evidence() -> None:
    if MIGRATION_PATH.exists() or RECEIPT_PATH.exists() or SNAPSHOT_PATH.exists():
        raise AssertionError("P4.4C evidence already exists; refusing to overwrite phase evidence")
    migration = build_migration_review()
    ledger, receipt = build_evidence(migration)
    MIGRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    MIGRATION_PATH.write_bytes(evolution.canonical_json_bytes(migration))
    SNAPSHOT_PATH.write_bytes(evolution.canonical_json_bytes(ledger))
    RECEIPT_PATH.write_bytes(evolution.canonical_json_bytes(receipt))
    evolution.LEDGER_PATH.write_bytes(evolution.canonical_json_bytes(ledger))


def _validate_migration_review(review: dict[str, Any]) -> None:
    if review.get("canonical_sha256") != evolution.canonical_sha256(review):
        raise AssertionError("P4.4C migration-review canonical SHA mismatch")
    if review.get("p4_3a_matrix_sha256") != retirement.MATRIX_SHA256:
        raise AssertionError("P4.4C review changed frozen P4.3A matrix identity")
    if review.get("reviewed_workflow_count") != 5 or len(review.get("workflow_rows", [])) != 5:
        raise AssertionError("P4.4C review must contain exactly five future-ingest rows")
    if [row.get("workflow_path") for row in review["workflow_rows"]] != list(EXPECTED_PATHS):
        raise AssertionError("P4.4C reviewed workflow path set/order changed")
    matrix, _ = retirement.load_baseline()
    frozen = {row["workflow_path"]: row for row in matrix["workflow_rows"]}
    for row in review["workflow_rows"]:
        path = row["workflow_path"]
        expected = frozen[path]
        expected_identity = {key: expected[key] for key in evolution.IDENTITY_KEYS}
        if row.get("frozen_p4_3a_source_identity") != expected_identity:
            raise AssertionError(f"P4.4C review lost frozen P4.3A identity: {path}")
        if row.get("path_exists") is not True or not Path(path).is_file():
            raise AssertionError(f"P4.4C reviewed workflow is missing: {path}")
        if _current_identity(path) != row.get("current_live_source_identity"):
            raise AssertionError(f"P4.4C current workflow identity changed: {path}")
        if row.get("current_live_source_identity") != expected_identity:
            raise AssertionError(f"P4.4C current workflow no longer matches its frozen source: {path}")
        if row.get("reviewed_disposition") != DISPOSITIONS[path]:
            raise AssertionError(f"P4.4C disposition changed: {path}")
        if row.get("equivalence_claimed") is not False or row.get("retirement_authorized") is not False:
            raise AssertionError(f"P4.4C cannot claim equivalence or authorize retirement: {path}")
        for field in (
            "trigger_types", "permissions", "inputs", "outputs_artifact_names",
            "timeout_minutes", "concurrency_group", "unique_responsibilities",
        ):
            expected_value = {
                "trigger_types": expected.get("trigger_types", []),
                "permissions": expected.get("permissions", {}),
                "inputs": expected.get("workflow_dispatch_inputs", {}),
                "outputs_artifact_names": expected.get("outputs_or_receipts", []),
                "timeout_minutes": expected.get("job_timeout_minutes", []),
                "concurrency_group": expected.get("concurrency_group"),
                "unique_responsibilities": expected.get("unique_responsibilities", []),
            }[field]
            if row.get(field) != expected_value:
                raise AssertionError(f"P4.4C review metadata differs from frozen census ({field}): {path}")


def check() -> dict[str, Any]:
    p44b.check()
    history = retirement.validate_retirement_history()
    if history.get("canonical_sha256") != P43_LEDGER_SHA256:
        raise AssertionError("P4.3 retirement ledger changed during P4.4C")
    ledger = evolution.validate_current_state()
    if len(ledger.get("transitions", [])) != 4:
        raise AssertionError("P4.4C evolution ledger must contain exactly four transitions")
    transition = ledger["transitions"][3]
    if transition.get("transition_id") != TRANSITION_ID or transition.get("operation") != "REVISE" or transition.get("workflow_path") != WORKFLOW_PATH:
        raise AssertionError("P4.4C must append exactly the scheduled-ingest REVISE transition")
    if transition.get("before") != {"git_blob_sha1": P44B_WORKFLOW_BLOB, "source_sha256": P44B_WORKFLOW_SOURCE}:
        raise AssertionError("P4.4C REVISE before identity differs from P4.4B")
    snapshot = _load(SNAPSHOT_PATH)
    receipt = _load(RECEIPT_PATH)
    review = _load(MIGRATION_PATH)
    if snapshot != ledger or snapshot.get("canonical_sha256") != evolution.canonical_sha256(snapshot):
        raise AssertionError("P4.4C checkpoint snapshot differs from the final cumulative ledger")
    if receipt.get("canonical_sha256") != evolution.canonical_sha256(receipt):
        raise AssertionError("P4.4C receipt canonical SHA mismatch")
    if receipt.get("workflow_evolution_ledger_sha256") != snapshot.get("canonical_sha256"):
        raise AssertionError("P4.4C receipt does not bind its exact checkpoint")
    if receipt.get("reviewed_workflow_transition") != {key: value for key, value in transition.items() if key != "evidence_body_sha256"}:
        raise AssertionError("P4.4C receipt does not bind the exact transition intent")
    if evolution.receipt_evidence_body_sha256(receipt) != transition.get("evidence_body_sha256"):
        raise AssertionError("P4.4C transition evidence-body digest mismatch")
    if receipt.get("migration_review_artifact_sha256") != review.get("canonical_sha256"):
        raise AssertionError("P4.4C receipt does not bind the migration-review artifact")
    _validate_migration_review(review)
    if receipt.get("workflow_after_identity") != transition.get("after"):
        raise AssertionError("P4.4C receipt workflow identity differs from the reviewed transition")
    workflow = Path(WORKFLOW_PATH).read_text(encoding="utf-8")
    if workflow.count('    - cron: "0 8 * * *"') != 1 or workflow.count("  schedule:") != 1:
        raise AssertionError("P4.4C must enable exactly the reviewed daily UTC cron")
    if "workflow_dispatch:" not in workflow or workflow.count("      dates:") != 1:
        raise AssertionError("P4.4C must preserve the existing manual dates interface")
    triggers = re.search(r"(?ms)^on:\n(.*?)(?=^permissions:)", workflow)
    if not triggers or re.search(r"(?m)^  (?!schedule:|workflow_dispatch:)[A-Za-z_][A-Za-z0-9_-]*:", triggers.group(1)):
        raise AssertionError("P4.4C added an unreviewed acquisition trigger")
    expected_flags = {
        "scheduled_acquisition_enabled": True,
        "schedule_cron": "0 8 * * *",
        "schedule_timezone": "UTC",
        "scheduled_date_count": 1,
        "scheduled_max_provider_requests": 1,
        "manual_max_dates": 7,
        "provider_scope": ["fotmob"],
        "timezone": "UTC",
        "ccode3": "NGA",
        "service_budget_seconds": 900,
        "workflow_timeout_minutes": 20,
        "finalization_headroom_seconds": 300,
        "acquisition_retry_count": 0,
        "p4_3_retirements_added": 0,
        "legacy_ingest_workflows_retired": 0,
        "workflow_count_before": 38,
        "workflow_count_after": 38,
        "transition_count_before": 3,
        "transition_count_after": 4,
        "provider_acquisition_during_pr": False,
        "provider_request_count_during_pr": 0,
        "workflow_dispatch_during_pr": False,
        "automatic_acquisition_active_on_main_while_pr_open": False,
        "backfill_authority": False,
        "authority_expansion": False,
        "p4_4_overall_complete": False,
        "architecture_checkpoint_e_fully_claimed": False,
        "mandatory_source_reread_required_after_merge": True,
    }
    if any(receipt.get(key) != value for key, value in expected_flags.items()):
        raise AssertionError("P4.4C receipt violates the scheduled-ingest/authority contract")
    if ledger.get("current_live_workflow_count") != 38 or ledger.get("current_workflow_tree_sha1") != _git("rev-parse", "HEAD:.github/workflows").decode("ascii").strip():
        raise AssertionError("P4.4C current workflow tree/count does not match reviewed state")
    if history.get("current_retired_workflow_count") != 3:
        raise AssertionError("P4.4C unexpectedly changed P4.3 retirement count")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--write-evidence", action="store_true")
    args = parser.parse_args()
    try:
        if args.write_evidence:
            write_evidence()
        else:
            check()
        return 0
    except Exception as exc:
        print(f"P4_4C_SCHEDULED_INGEST_MIGRATION_REVIEW_FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
