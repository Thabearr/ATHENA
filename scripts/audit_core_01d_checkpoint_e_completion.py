"""Independent 19-criterion current status; retention acceptance is not completion."""
from __future__ import annotations

import argparse
import json

import yaml

from scripts import audit_core_01d_historical_retention_acceptance as policy
from scripts import audit_core_01d_retained_workflow_status_v5 as v5
from scripts import audit_p4_workflow_evolution_ledger as evolution
from scripts import audit_core_01d_scheduled_shadow_ownership as schedule

ROOT = policy.ROOT
POLICY_ID = "ATHENA_CORE_01D_CHECKPOINT_E_COMPLETION_V1"
RECEIPT_PATH = v5.COMPLETION_PATH
CRITERIA = (
    "canonical_workflow_family_exists",
    "all_live_workflows_and_triggers_enumerated",
    "every_surface_has_successor_or_explicit_retained_disposition",
    "canonical_artifact_roles_and_failed_producer_guard_preserved",
    "notification_explicit_and_non_authoritative",
    "retirement_requires_complete_evidence_no_unreviewed_deletions",
    "no_supported_current_run_depends_on_date_hardcoded_workflow",
    "historical_sources_and_evolution_prefix_preserved",
    "clean_successor_gate_satisfied",
    "scheduled_shadow_canonical_ownership_proven_preserving_main",
    "all_retained_workflow_authority_and_dynamic_reachability_review_complete",
    "no_supported_current_operation_depends_on_unavailable_exact_historical_artifact",
    "historical_retention_limitations_explicitly_dispositioned",
    "no_unknown_current_artifact_or_notification_authority",
    "no_new_retirement_or_deletion_required_for_checkpoint_e",
    "workflow_evolution_current_state_authenticated",
    "existing_retirement_ledger_authenticated",
    "live_side_effect_count_for_pass4",
    "semantic_delta_for_pass4",
)
COMPLETE_TERMINAL = "CORE_01D_HISTORICAL_RETENTION_ACCEPTANCE_REVIEW_READY_CHECKPOINT_E_COMPLETE_DO_NOT_MERGE"
BLOCKED_TERMINAL = "CORE_01D_HISTORICAL_RETENTION_ACCEPTANCE_REVIEW_READY_CHECKPOINT_E_STILL_BLOCKED_DO_NOT_MERGE"
ALLOWED_PASS4_PATHS = {
    policy.RECEIPT_PATH, v5.RECEIPT_PATH, RECEIPT_PATH,
    "scripts/audit_core_01d_historical_retention_acceptance.py",
    "scripts/audit_core_01d_retained_workflow_status_v5.py",
    "scripts/audit_core_01d_checkpoint_e_completion.py",
    policy.SNAPSHOT_PATH,
    "tests/test_core_01d_historical_retention_acceptance.py",
    "tests/test_core_01d_checkpoint_e_completion.py",
    "scripts/audit_checkpoint_e_workflows.py",
    "docs/architecture/core_01d_checkpoint_e.md",
    "tests/test_core_01d_canonical_drive_transfer_completed_history.py",
}
APP01C_BOUNDED_PATHS = {
    "api/app_factory.py",
    "api/schemas.py",
    "api/server.py",
    "api/v1/common.py",
    "api/v1/exports.py",
    "api/v1/fixtures.py",
    "api/v1/runs.py",
    "docs/product/app_01c_versioned_api.md",
    "run_desktop.py",
    "scripts/audit_checkpoint_e_workflows.py",
    "scripts/audit_core_01d_checkpoint_e_completion_v2.py",
    "services/athena_capability_service.py",
    "services/athena_read_service.py",
    "tests/fixtures/core_01d/app_01c_historical/api_server.py.b64",
    "tests/fixtures/core_01d/app_01c_historical/checkpoint_e_completion.py.b64",
    "tests/fixtures/core_01d/app_01c_historical/run_desktop.py.txt",
    "tests/fixtures/core_01d/app_01c_historical/test_api_error_handling.py.txt",
    "tests/fixtures/core_01d/app_01c_historical/test_product_baseline_v1.py.txt",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v31.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v32.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v33.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v34.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v35.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v36.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v37.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v38.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v39.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v40.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v41.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v42.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v43.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v44.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v45.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v46.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v47.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v48.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v49.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v50.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v51.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v52.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v53.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v54.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v55.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v56.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v57.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v58.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v59.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v60.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v61.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v62.json",
    "tests/test_api_error_handling.py",
    "tests/test_app_01a_local_shell.py",
    "tests/test_app_01b_preview_admission.py",
    "tests/test_app_01c_versioned_read_api.py",
    "tests/test_core_01d_ci_offline_transport_inventory_evolution.py",
    "tests/test_core_01d_exact_pr_trigger_disposition_b1.py",
    "tests/test_core_01d_frozen_artifact_replay_authority_b5.py",
    "tests/test_core_01d_owner_one_shot_issue_comment_authority_b3.py",
    "tests/test_core_01d_port02c_trigger_authority_b6.py",
    "tests/test_product_baseline_v1.py",
}
APP01C_CURRENT_SOURCE_PATHS = {
    "scripts/audit_core_01d_authority_reachability_review_a.py",
}
APP01C_PREDECESSOR_SOURCE_BLOBS = {
    "scripts/audit_core_01d_authority_reachability_review_a.py":
        "036e483000ce07b2dab5fb7136e4992820026262",
}
ALLOWED_PASS4_PATHS |= APP01C_BOUNDED_PATHS | APP01C_CURRENT_SOURCE_PATHS
# Exact handoff ls-tree inventory excluding only the twelve bounded evidence
# paths. Available in shallow CI without requiring the handoff commit object.
UNCHANGED_REPOSITORY_INVENTORY_SHA = "6b407c284a7c2f759e6345f53444478de53427ceae1aaa7d412d078270c5ad27"


def validate_bounded_inventory(raw: bytes) -> None:
    unchanged_lines = []
    for line in raw.splitlines(keepends=True):
        metadata, separator, path_bytes = line.partition(b"\t")
        path = path_bytes.strip().decode()
        if path in ALLOWED_PASS4_PATHS and path not in APP01C_CURRENT_SOURCE_PATHS:
            continue
        if path in APP01C_PREDECESSOR_SOURCE_BLOBS:
            metadata = metadata.rsplit(b" ", 1)[0] + b" " + APP01C_PREDECESSOR_SOURCE_BLOBS[path].encode()
            line = metadata + separator + path_bytes
        unchanged_lines.append(line)
    unchanged = b"".join(unchanged_lines)
    policy.require(policy.sha256(unchanged) == UNCHANGED_REPOSITORY_INVENTORY_SHA,
                   "unapproved repository change: runtime/workflows/ledgers/history must remain exact")


def authenticate_bounded_scope() -> bool:
    validate_bounded_inventory(policy.v4.v3._git("ls-tree", "-r", "HEAD"))
    dirty = policy.v4.v3._git("diff", "--name-only", "HEAD").decode().splitlines()
    policy.require(set(dirty) <= ALLOWED_PASS4_PATHS,
                   "working tree has an unapproved operational or historical source change")
    return True


def authenticate_notification_without_transport() -> bool:
    """Authenticate C3 bytes/guards without invoking even a mocked sender."""
    from scripts import audit_core_01c_notification_comment_compatibility as notification
    value = policy.roles.strict_json(notification.tracked(notification.RECEIPT_PATH))
    policy.require(value["canonical_sha256"] ==
                   "d89c38790bb0dc36a052e865bf2e5bd17411d0089ec4797b5aa145f40705ffc8"
                   == evolution.canonical_sha256(value), "sealed C3 notification identity drift")
    for path in notification.SOURCE_PATHS:
        policy.require(evolution.source_identity(notification.tracked(path)) == value["source_identities"][path],
                       f"notification historical source identity drift: {path}")
    notification.verify_workflow_authority(notification.tracked(notification.BEFORE_FIXTURE),
                                           notification.tracked(notification.WORKFLOW))
    facts = value["notification"]
    return (facts["status"] == "EXPLICIT_RETAINED_SECONDARY_NON_AUTHORITATIVE"
            and facts["integrity_security_failure"] == "FAIL_CLOSED"
            and facts["transport_failure"] == "EMAIL_FAILED_WARNING_EXIT_ZERO"
            and facts["business_receipt_mutation"] is False and facts["core_rerun"] is False)


def status_from_criteria(criteria: dict) -> tuple[str, list[str]]:
    policy.require(set(criteria) == set(CRITERIA)
                   and all(type(flag) is bool for flag in criteria.values()),
                   "all 19 explicit boolean criteria are mandatory")
    blockers = [key for key in CRITERIA if criteria[key] is not True]
    return ("INCOMPLETE" if blockers else "COMPLETE"), blockers


def build_receipt() -> dict:
    # Use historical source derivation, not the master audit's CURRENT answer;
    # otherwise the new completion receipt would authenticate itself in a cycle.
    from scripts import audit_checkpoint_e_workflows as checkpoint
    from scripts import audit_p4_3_workflow_retirement_ledger as retirement
    from scripts import audit_core_01b_canonical_artifact_ancestry as ancestry

    old = policy.predecessor()
    bounded_scope_verified = authenticate_bounded_scope()
    availability = policy.load_snapshot()
    accepted = policy.build_receipt(old)
    policy.validate_receipt(policy.roles.strict_json((ROOT / policy.RECEIPT_PATH).read_bytes()), accepted)
    retained = v5.build_receipt(old, accepted)
    v5.validate_receipt(policy.roles.strict_json((ROOT / v5.RECEIPT_PATH).read_bytes()), retained)
    historical_matrix, historical_checkpoint = checkpoint.expected_documents()
    forward = schedule.audit_forward_checkpoint()
    matrix_path = schedule.FORWARD_MATRIX
    matrix = policy.roles.strict_json((ROOT / matrix_path).read_bytes())
    policy.require(matrix["canonical_sha256"] == forward["workflow_matrix_sha256"]
                   == policy.v4.v1.PREDECESSOR_V2_MATRIX_SHA256,
                   "immutable forward matrix identity drift")
    policy.require(matrix["canonical_sha256"] == checkpoint.self_sha(matrix), "forward matrix self-hash drift")
    rows = matrix["workflow_rows"]
    paths = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / ".github/workflows").glob("*.yml"))
    policy.require(paths == [r["workflow_path"] for r in rows], "current workflow enumeration drift")
    inventory, unknown = [], []
    covered = True
    for row in rows:
        path = row["workflow_path"]
        source = (ROOT / path).read_bytes()
        doc = yaml.load(source, Loader=yaml.BaseLoader)
        identity = policy.v4.v3._source_identity(path)
        actual = sorted(doc["on"])
        represented = sorted(s["trigger_kind"] for s in row["trigger_surfaces"])
        policy.require(actual == represented, f"current trigger enumeration drift: {path}")
        inventory.append({**identity, "trigger_kinds": actual})
        for surface in row["trigger_surfaces"]:
            covered = covered and surface["supported_status"] in checkpoint.ALLOWED_STATUS and bool(surface["retained_reason"])
            # These UNKNOWN fields are unreviewed authority, not inferred live
            # authority. Explicit retained status alone does not review them.
            unknown_fields = {key: surface.get(key) for key in
                ("authority_profile", "acquisition_authority", "delivery_authority", "wager_authority")
                if "UNKNOWN" in str(surface.get(key, ""))}
            if unknown_fields:
                unknown.append({"workflow_path": path, "trigger_kind": surface["trigger_kind"],
                                "unreviewed_authority_fields": unknown_fields,
                                "notification_behavior": surface["notification_behavior"],
                                "current_source_sha256": identity["source_sha256"],
                                "evidence": matrix_path})
    ledger = evolution.validate_current_state()
    p43 = retirement.validate_retirement_history()
    role_audit = ancestry.audit()
    notification_source_verified = authenticate_notification_without_transport()
    authority_review_complete = not unknown and forward["checkpoint_criteria"][CRITERIA[10]]
    effects = policy.ZERO_ACTIONS
    delta = policy.ZERO_DELTA
    criteria = dict(zip(CRITERIA, (
        checkpoint.CANONICAL in paths and ".github/workflows/athena-ingest.yml" in paths,
        len(inventory) == matrix["workflow_count"] == 39 and sum(len(r["trigger_kinds"]) for r in inventory) == matrix["trigger_surface_count"] == 57,
        bool(covered),
        role_audit["result"] == "PASS" and historical_checkpoint["historical_failed_lg_a"]["restore_eligible"] is False,
        notification_source_verified and historical_checkpoint["notification_disposition"]["legacy"] == "EXPLICIT_RETAINED_SECONDARY_NON_AUTHORITATIVE",
        p43["canonical_sha256"] == policy.v4.v3.P43_LEDGER_SHA256 and matrix["retired_in_this_pr"] == [],
        not any(r["supported_current_runtime_root"] and r["date_hardcoded_historical_evidence"] for r in rows),
        old["canonical_sha256"] == policy.V4_SHA and ledger["canonical_sha256"] == policy.v4.v3.EVOLUTION_LEDGER_SHA256,
        historical_checkpoint["accepted_lg_a"]["run_id"] == 36860297707 and historical_checkpoint["checkpoint_criteria"]["clean_successor_gate_satisfied"],
        forward["checkpoint_criteria"]["scheduled_shadow_canonical_ownership_proven_preserving_main"],
        bool(authority_review_complete),
        not any(r["trigger_lifecycle"].startswith("LIVE_") for r in old["current_artifact_trigger_relationships"])
            and not any(r["supported_current_runtime_dependency"] for r in accepted["artifact_retentions"]),
        len(accepted["artifact_retentions"]) == 9 and all(r["retention_disposition"] == "ACCEPTED_HISTORICAL_RETENTION_LIMITATION" for r in accepted["artifact_retentions"]),
        not unknown,
        bool(covered) and not any(r["deletion_eligible"] for r in rows),
        ledger["canonical_sha256"] == policy.v4.v3.EVOLUTION_LEDGER_SHA256 and len(ledger["transitions"]) == 14,
        p43["canonical_sha256"] == policy.v4.v3.P43_LEDGER_SHA256,
        all(type(count) is int and count == 0 for count in effects.values())
            and availability["read_only"] is True and availability["new_provider_or_workflow_operation"] is False,
        bounded_scope_verified and all(type(count) is int and count == 0 for count in delta.values()),
    )))
    status, blockers = status_from_criteria(criteria)
    return policy.seal({
        "schema_version": 1, "policy_id": POLICY_ID, "repository": "Thabearr/ATHENA",
        "master_issue": 337, "base_main_sha": policy.BASE_MAIN, "base_tree_sha": policy.BASE_TREE,
        "retention_acceptance": {"path": policy.RECEIPT_PATH, "canonical_sha256": accepted["canonical_sha256"]},
        "retained_status_v5": {"path": v5.RECEIPT_PATH, "canonical_sha256": retained["canonical_sha256"]},
        "historical_checkpoint_e_v1": {"path": checkpoint.RECEIPT_PATH, "canonical_sha256": historical_checkpoint["canonical_sha256"], "status": "INCOMPLETE", "rewritten": False},
        "historical_forward_checkpoint_e_v2": {"path": schedule.FORWARD_RECEIPT, "canonical_sha256": forward["canonical_sha256"], "status": "INCOMPLETE", "rewritten": False},
        "forward_matrix": {"path": matrix_path, "canonical_sha256": matrix["canonical_sha256"]},
        "workflow_source_inventory": inventory, "workflow_count": len(inventory),
        "trigger_surface_count": sum(len(r["trigger_kinds"]) for r in inventory),
        "workflow_tree_before_sha1": policy.v4.v3.WORKFLOW_TREE_SHA1,
        "workflow_tree_after_sha1": policy.v4.v3.WORKFLOW_TREE_SHA1,
        "evolution_ledger_before_sha256": ledger["canonical_sha256"],
        "evolution_ledger_after_sha256": ledger["canonical_sha256"], "transition_count": len(ledger["transitions"]),
        "retirement_ledger_sha256": p43["canonical_sha256"], "retired_workflow_count": old["retired_workflow_count"],
        "checkpoint_criteria": criteria,
        "unreviewed_authority_surfaces": unknown,
        "criterion_failure_evidence": {key: {
            "reason": "The immutable forward matrix retains unreviewed authority fields; no independent current authority/dynamic-caller review closes them. Retention acceptance does not supply that proof.",
            "matrix_path": matrix_path, "unreviewed_surface_count": len(unknown),
            "no_retirement_proof_required_or_inferred": True,
        } for key in blockers},
        "checkpoint_e_status": status, "p4_4_status": status, "remaining_blocker_ids": blockers,
        "retention_blocker_D_closed": True, "exact_bytes_recovered": 0,
        "live_missing_artifact_relation_count": 0, "historical_relation_count": 14,
        "supported_operations_depending_on_unavailable_bytes": 0,
        "actions": effects, "protected_semantic_delta": delta, **policy.NO_AUTHORITY,
        "source_review_counter_while_open": "1/5", "source_review_counter_if_owner_merges": "2/5",
        "mandatory_source_reread_due": False,
        "terminal": COMPLETE_TERMINAL if status == "COMPLETE" else BLOCKED_TERMINAL,
    })


def validate_receipt(value: dict, expected: dict | None = None) -> None:
    policy.require(value.get("canonical_sha256") == policy.sha256(policy.canonical_bytes(
        {k: v for k, v in value.items() if k != "canonical_sha256"})), "completion self-hash mismatch")
    status, blockers = status_from_criteria(value["checkpoint_criteria"])
    policy.require(value["checkpoint_e_status"] == value["p4_4_status"] == status
                   and value["remaining_blocker_ids"] == blockers,
                   "completion requires all 19 proven criteria and no blockers")
    policy.require(all(value[k] is False for k in policy.NO_AUTHORITY), "completion grants forbidden authority")
    policy.require(value == (build_receipt() if expected is None else expected),
                   "completion differs from independently authenticated current criteria")


def audit() -> dict:
    value = policy.roles.strict_json((ROOT / RECEIPT_PATH).read_bytes())
    validate_receipt(value)
    return {"result": "PASS", "policy_id": POLICY_ID, "receipt_sha256": value["canonical_sha256"],
            "checkpoint_e": value["checkpoint_e_status"], "p4_4": value["p4_4_status"],
            "remaining_blockers": value["remaining_blocker_ids"], "terminal": value["terminal"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if args.write:
        value = build_receipt()
        (ROOT / RECEIPT_PATH).write_bytes(policy.canonical_bytes(value))
        print(json.dumps({"result": "WROTE", "receipt_sha256": value["canonical_sha256"],
                          "status": value["checkpoint_e_status"], "blockers": value["remaining_blocker_ids"]}))
    else:
        print(json.dumps(audit(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
