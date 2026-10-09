"""Offline Pass-3 disposition: completed transfer history, incomplete retention.

This is an evidence classification, not a runtime interlock. The retained YAML
and its physical triggers are unchanged; no dispatch or replay is authorized.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

import yaml

from scripts.audit_data_01c_restore_portability import historical_workflow_tree

from scripts import audit_core_01d_retained_workflow_status_v3 as v3
from scripts import audit_core_01d_retained_workflow_status as v1
from services import athena_artifact_role_resolver as roles

ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "ATHENA_CORE_01D_RETAINED_WORKFLOW_STATUS_V4"
RECEIPT_PATH = "artifacts/architecture/core_01d_retained_workflow_status_v4.json"
V3_PATH = v3.RECEIPT_PATH
V3_SHA256 = "fe6ff060c6d8a1a829e7ad385eda8db350715b24983729803492dba64982317a"
BASE_MAIN_SHA = "5b3614b69591bf9d2eac80d4b850c724e0d2561f"
BASE_TREE_SHA = "a7355d922beb231016423f204294f85a39b306c8"
WORKFLOW = ".github/workflows/prepare-canonical-drive-transfer.yml"
WORKFLOW_BLOB = "f863d6c19696a519e9706c99f4b6effd6a182525"
WORKFLOW_SHA256 = "bbf0dda03803ca1484069e086eefa50df370a378e8a0520cdb0d6a7af9c7d5f2"
SNAPSHOT_PATH = "tests/fixtures/core_01d/canonical-drive-transfer-retention-snapshot-v1.json"
SNAPSHOT_SHA256 = "4611bd10d36f640ab2108c46933b5aac59bbc2531c545379a6de6fc37f11515c"
HISTORY_PATH = v3.CORROBORATING_HISTORY_PATH
HISTORY_SHA256 = "66ef6267af033a6e907aebe16ae44c20a15d9a4c5425960aa1da2003c89e39b6"
MIGRATION_PATH = "artifacts/architecture/p4_4c_ingest_capability_migration_review_v1.json"
MIGRATION_SHA256 = "b857c568cf1cad1e9f648e78fc49e9cec13bb308e30ad35291ce641fa61d2077"
ARTIFACT_ID = 9491418446
SOURCE_RUN_ID = 32628985683
TRANSFER_RUN_ID = 32635585415
TRANSFER_HEAD = "d2145f0e5ba74fb516797768f5d8a8681a3c3ffa"
ARCHIVE_SHA256 = "a783886d0906e357e26851fcb3eb182bb06bdcc184d21f2b6578bb3d1fa61511"
RETAINED_STATUS = "COMPLETED_HISTORICAL_TRANSFER_RETAIN"
LIFECYCLE = "RETAINED_NONEXECUTABLE_HISTORY"
DEPENDENCY = "HISTORICAL_TRANSFER_LINEAGE_AND_RETENTION_ONLY"
BLOCKER_C = "CANONICAL_HISTORY_TRANSFER_SOURCE_NOT_FULLY_DURABLE"
BLOCKER_D = v3.HISTORY_BLOCKER
TERMINAL = "CORE_01D_DRIVE_TRANSFER_COMPLETED_HISTORY_REVIEW_READY_BLOCKER_C_CLOSED_DO_NOT_MERGE"
VISIBLE = [f"{i:03d}" for i in range(11)] + ["022"]
MISSING = [f"{i:03d}" for i in range(11, 22)]
canonical_bytes = v3.canonical_bytes
sha256 = v3.sha256
seal = v3.seal


class TransferHistoryError(AssertionError):
    """Evidence, source, authority or retention truthfulness drift."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TransferHistoryError(message)


def authenticated_json(path: str, digest: str) -> dict:
    raw = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
    require(sha256(raw) == digest, f"immutable source SHA drift: {path}")
    return roles.strict_json(raw)


def validate_snapshot(value: dict) -> None:
    # Pin the complete bounded observation, including provenance and negative
    # claims. Resealing a false recovery/deletion claim cannot make it valid.
    require(sha256(canonical_bytes(value)) == SNAPSHOT_SHA256,
            "retention snapshot differs from authenticated read-only observation")
    run = value["historical_transfer_run"]
    require(run["id"] == TRANSFER_RUN_ID and run["path"] == WORKFLOW
            and run["head_sha"] == TRANSFER_HEAD and run["event"] == "push"
            and run["conclusion"] == "success" and run["status"] == "completed",
            "successful historical transfer identity drift")
    drive = value["external_drive_availability"]
    require(drive["recovery_state"] == "PARTIAL_DURABLE_COPY_RECOVERED"
            and drive["visible_part_indexes"] == VISIBLE
            and drive["missing_part_indexes"] == MISSING
            and drive["exact_archive_currently_reconstructable"] is False,
            "partial external retention cannot imply archive recovery")


def authenticate_sources() -> dict:
    snapshot = authenticated_json(SNAPSHOT_PATH, SNAPSHOT_SHA256)
    validate_snapshot(snapshot)
    history = authenticated_json(HISTORY_PATH, HISTORY_SHA256)
    migration = authenticated_json(MIGRATION_PATH, MIGRATION_SHA256)
    run = snapshot["historical_transfer_run"]
    historical = history["workflow_history"][WORKFLOW]["last_successful"]
    for key in ("id", "path", "head_sha", "head_branch", "event", "run_attempt",
                "status", "conclusion", "created_at"):
        require(historical[key] == run[key], f"source-controlled transfer history drift: {key}")
    row, = [r for r in migration["workflow_rows"] if r["workflow_path"] == WORKFLOW]
    old_run = row["latest_successful_run_observed_at_capture"]
    require(old_run["run_id"] == run["id"]
            and old_run["head_sha"] == run["head_sha"]
            and old_run["event"] == run["event"]
            and old_run["conclusion"] == run["conclusion"],
            "P4.4C does not corroborate the completed transfer")
    identity = v3._source_identity(WORKFLOW)
    require(identity["git_blob_sha1"] == WORKFLOW_BLOB
            and identity["source_sha256"] == WORKFLOW_SHA256,
            "transfer workflow source changed")
    source = (ROOT / WORKFLOW).read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    triggers = workflow.get("on", workflow.get(True))
    require(set(triggers) == {"workflow_dispatch", "push"}, "transfer trigger surface drift")
    inputs = triggers["workflow_dispatch"]["inputs"]
    require(set(inputs) == {"source_run_id", "source_artifact_id"}
            and inputs["source_run_id"]["default"] == str(SOURCE_RUN_ID)
            and inputs["source_artifact_id"]["default"] == str(ARTIFACT_ID),
            "transfer source defaults drift")
    require(triggers["push"] == {"branches": ["main"], "paths": [WORKFLOW]}
            and workflow["permissions"] == {"actions": "read", "contents": "write"},
            "transfer push filter/permissions drift")
    env = workflow["jobs"]["prepare-drive-transfer"]["env"]
    require(env["EXPECTED_ARCHIVE_BYTES"] == "2149256220"
            and env["EXPECTED_ARCHIVE_SHA256"] == ARCHIVE_SHA256
            and env["ARCHIVE_NAME"] == "athena-history-canonical.zip"
            and env["POINTER_BRANCH"] == "automation/canonical-drive-transfer-pointer",
            "exact archive contract drift")
    for needle in ('git push --force', 'split -b 90M -d -a 3',
                   'if [ "${PART_COUNT}" != "23" ]',
                   'ATHENA_CANONICAL_ARCHIVE_SHA256.txt', 'ATHENA_PART_SHA256.txt'):
        require(needle in source, f"historical preparation contract missing: {needle}")
    uploads = [step["with"]["name"] for step in
               workflow["jobs"]["prepare-drive-transfer"]["steps"]
               if step.get("uses") == "actions/upload-artifact@v4"]
    require(uploads == ["athena-canonical-manifest"] +
            [f"athena-canonical-part-{i:03d}" for i in range(23)],
            "23-part upload contract drift")
    require(historical_workflow_tree(v3._git("rev-parse", "HEAD:.github/workflows").decode().strip())
            == v3.WORKFLOW_TREE_SHA1, "workflow tree changed")
    # V3 authenticates the evolution ledger, retirement ledger, all source
    # artifact identities and current source-derived relationship inventory.
    return snapshot


def load_predecessor() -> dict:
    value = roles.strict_json((ROOT / V3_PATH).read_bytes())
    require(value.get("canonical_sha256") == V3_SHA256, "immutable V3 SHA changed")
    v3.validate_receipt(value)
    return value


def build_receipt() -> dict:
    predecessor = load_predecessor()
    snapshot = authenticate_sources()
    value = copy.deepcopy(predecessor)
    relations = value["current_artifact_trigger_relationships"]
    transfer = [row for row in relations if row["artifact_id"] == ARTIFACT_ID]
    require({row["logical_trigger_id"] for row in transfer} == {
        "canonical-transfer:workflow_dispatch", "canonical-transfer:push:main-workflow"
    } and len(transfer) == 2, "both physical transfer surfaces must remain represented")
    reason = (
        "Transfer-preparation run 32635585415 completed successfully historically. "
        "The exact source and transfer-run current Actions listings are empty; "
        "the accessible external copy remains partial 12/23. This workflow is "
        "retained non-executable history, not a supported current transfer operation."
    )
    decision = (
        "Preserve exact historical source identity and unchanged YAML/triggers. "
        "No dispatch, replay, reacquisition, substitution, retirement or deletion "
        "is authorized. Missing parts 011-021 remain a historical retention defect."
    )
    for row in transfer:
        require(all(flag is False for flag in row["authorizations"].values()),
                "transfer authority must remain false")
        row.update(trigger_lifecycle=LIFECYCLE, retained_status=RETAINED_STATUS,
                   dependency_type=DEPENDENCY, retained_reason=reason,
                   owner_decision=decision)
    artifact, = [row for row in value["artifact_dispositions"] if row["artifact_id"] == ARTIFACT_ID]
    require(artifact["recovery_state"] == "PARTIAL_DURABLE_COPY_RECOVERED",
            "canonical artifact recovery state changed")
    artifact.update(retained_status=RETAINED_STATUS, dependency_types=[DEPENDENCY],
                    retained_reason=reason, owner_decision=decision,
                    missing_evidence_effect=(
                        "No current supported transfer execution depends on this artifact. "
                        "Exact archive cannot currently be reconstructed: visible parts "
                        "000-010, 022; missing 011-021. Parts were not rehashed in this pass."
                    ))
    live = [row for row in relations if row["trigger_lifecycle"].startswith("LIVE_")]
    edges = {(row["artifact_id"], row["workflow_path"]) for row in relations}
    require(len(edges) == 12 and len(relations) == 14 and not live,
            "source-derived V4 relation counts drift")
    closed = value["closed_blockers"]
    closed.append({"id": BLOCKER_C, "closed_as_current_dependency": True,
                   "archive_recovered": False, "resolved_fact": reason + " " + decision})
    remaining = [row for row in value["remaining_blockers"] if row["id"] != BLOCKER_C]
    require(len(remaining) == 1 and remaining[0]["id"] == BLOCKER_D,
            "only historical retention blocker D must remain")
    remaining[0].update(
        artifact_ids=sorted(int(i) for i in v1.ARTIFACT_IDS),
        reason=("Exact historical replay archives remain unavailable, including the "
                "canonical history partial retention gap. Zero live missing-artifact "
                "dependencies does not complete Checkpoint E/P4.4. No retention "
                "acceptance, deprecation, retirement or replay is authorized."),
        canonical_history_retention_defect={
            "artifact_id": ARTIFACT_ID,
            "current_actions_availability": snapshot["current_actions_availability"],
            "external_drive_availability": snapshot["external_drive_availability"],
            "exact_archive_currently_reconstructable": False,
            "authorizations": copy.deepcopy(artifact["authorizations"]),
        },
        separate_retention_observations=copy.deepcopy(value["separate_retention_observations"]),
    )
    value.update(
        schema_version=4, policy_id=POLICY_ID,
        predecessor_v3={"path": V3_PATH, "canonical_sha256": V3_SHA256,
                        "state": "IMMUTABLE_PRE_PASS_3_BEFORE_STATE"},
        pass3_base_main_sha=BASE_MAIN_SHA, pass3_base_tree_sha=BASE_TREE_SHA,
        source_review_counter_while_open="0/5", source_review_counter_if_owner_merges="1/5",
        mandatory_source_reread_due=False,
        mandatory_source_reread_due_immediately_after_owner_merge=False,
        governing_source_reread_completed_after_pr434_before_this_pass=True,
        current_artifact_trigger_relationships=relations, artifact_workflow_edge_count=len(edges),
        artifact_trigger_relationship_count=len(relations),
        live_artifact_trigger_relationship_count=len(live),
        historical_or_spent_artifact_trigger_relationship_count=len(relations) - len(live),
        closed_blockers=closed, closed_blocker_ids=[row["id"] for row in closed],
        remaining_blockers=remaining, remaining_blocker_ids=[BLOCKER_D],
        remaining_blocker_family=BLOCKER_D,
        canonical_transfer_disposition={
            "workflow_path": WORKFLOW, "workflow_git_blob_sha1": WORKFLOW_BLOB,
            "workflow_source_sha256": WORKFLOW_SHA256, "physical_trigger_count": 2,
            "retained_status": RETAINED_STATUS, "trigger_lifecycle": LIFECYCLE,
            "dependency_type": DEPENDENCY, "historical_transfer_completed": True,
            "historical_transfer_run": snapshot["historical_transfer_run"],
            "source_run_id": SOURCE_RUN_ID, "source_artifact_id": ARTIFACT_ID,
            "recovery_state": "PARTIAL_DURABLE_COPY_RECOVERED",
            "current_supported_transfer_execution": False,
            "dispatch_authorized": False, "replay_authorized": False,
            "workflow_edited": False, "trigger_edited": False,
            "workflow_retired_or_deleted": False, "historical_retention_defect_remains": True,
        },
        retention_snapshot={"path": SNAPSHOT_PATH, "source_sha256": SNAPSHOT_SHA256},
        historical_transfer_source_evidence={HISTORY_PATH: HISTORY_SHA256,
                                             MIGRATION_PATH: MIGRATION_SHA256},
        drive_mutation_count=0, gmail_mutation_count=0, historical_warehouse_rebuild_count=0,
        dispatch_authorized=False, replay_authorized=False,
        checkpoint_e_status="INCOMPLETE", p4_4_status="INCOMPLETE", terminal=TERMINAL,
    )
    return seal(value)


def validate_receipt(value: dict, expected: dict | None = None) -> None:
    require(value.get("canonical_sha256") == sha256(canonical_bytes(
        {k: v for k, v in value.items() if k != "canonical_sha256"})), "V4 self-hash mismatch")
    require(value == (build_receipt() if expected is None else expected),
            "V4 differs from authenticated source/history and bounded disposition")


def audit() -> dict:
    expected = build_receipt()
    value = roles.strict_json((ROOT / RECEIPT_PATH).read_bytes())
    validate_receipt(value, expected)
    return {"result": "PASS", "receipt_sha256": value["canonical_sha256"],
            "policy_id": POLICY_ID, "workflow_count": value["workflow_count"],
            "trigger_surface_count": value["trigger_surface_count"],
            "live_relation_count": value["live_artifact_trigger_relationship_count"],
            "historical_relation_count": value["historical_or_spent_artifact_trigger_relationship_count"],
            "remaining_blockers": value["remaining_blocker_ids"],
            "checkpoint_e": value["checkpoint_e_status"], "p4_4": value["p4_4_status"],
            "terminal": TERMINAL}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.write:
            value = build_receipt()
            (ROOT / RECEIPT_PATH).write_bytes(canonical_bytes(value))
            result = {"result": "WROTE", "receipt_sha256": value["canonical_sha256"]}
        else:
            result = audit()
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, AssertionError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"result": "BLOCKED", "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
