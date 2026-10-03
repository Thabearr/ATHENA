"""Additive A2 overlay; authenticate immutable V2 and retain all other unknowns."""
from __future__ import annotations

import argparse
from copy import deepcopy

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary

ROOT = boundary.ROOT
POLICY_ID = "ATHENA_CORE_01D_CHECKPOINT_E_COMPLETION_V3"
RECEIPT_PATH = boundary.COMPLETION_PATH
PARENT_PATH = "artifacts/architecture/core_01d_checkpoint_e_completion_v2.json"
AUTHORITY_FIELDS = ("provider_acquisition_authority", "sportsbook_read_authority", "share_code_authority",
                    "wager_authority", "external_storage_write_authority")


def build_receipt():
    boundary.audit()
    old = boundary.read(PARENT_PATH)
    a2 = boundary.read(boundary.RECEIPT_PATH)
    rows = []
    for original in old["unresolved_pass_a_rows"]:
        row = deepcopy(original)
        key = (row["workflow_path"], row["trigger_kind"])
        proof = next(item for item in a2["target_rows"] if (item["workflow_path"], item["trigger_kind"]) == key)
        if proof["resolved"]:
            for field in AUTHORITY_FIELDS:
                row[field] = "NONE_TEST_TRANSPORT_DENIED"
            row["delivery_authority"] = "NONE_EXTERNAL_DELIVERY_TEST_TRANSPORT_DENIED"
            row["notification_authority"] = "GITHUB_CHECK_OR_LOG_ONLY_NO_EXTERNAL_TEST_TRANSPORT"
            row["network_authority_summary"] = "GLOBAL_PYTEST_EXTERNAL_TRANSPORT_FAIL_CLOSED_WITH_NATIVE_AND_CHILD_PROCESS_COVERAGE"
            row["dynamic_reachability_review_state"] = proof["review_state"]
            row.update(resolved=True, unresolved_fields=[], evidence_gap=None, safest_next_action=None)
        rows.append(row)
    resolved = {(row["workflow_path"], row["trigger_kind"]) for row in rows if row["resolved"]}
    remaining = [deepcopy(row) for row in old["unreviewed_authority_surfaces"]
                 if (row["workflow_path"], row["trigger_kind"]) not in resolved]
    boundary.require(resolved <= set(boundary.TARGETS), "out-of-scope A2 authority overlay")
    boundary.require(len(remaining) == old["remaining_unreviewed_surface_count"] - len(resolved), "counts not derived from proven rows")
    criteria = deepcopy(old["checkpoint_criteria"])
    boundary.require(len(criteria) == 19 and sum(criteria.values()) == 17, "inherited 19-criterion framework drift")
    boundary.require(criteria["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False
                     and criteria["no_unknown_current_artifact_or_notification_authority"] is False,
                     "criteria 11/14 cannot be made true")
    return boundary.seal({
        "schema_version": 3, "policy_id": POLICY_ID, "repository": "Thabearr/ATHENA", "master_issue": 337,
        "base_main_sha": boundary.BASE_MAIN, "base_tree_sha": boundary.BASE_TREE,
        "predecessor_completion_v2": {"path": PARENT_PATH, "canonical_sha256": old["canonical_sha256"], "rewritten": False},
        "a2_review": {"path": boundary.RECEIPT_PATH, "canonical_sha256": a2["canonical_sha256"]},
        "retained_v5": old["retained_v5"], "pass_a_review": old["pass_a_review"],
        "reviewed_a2_target_count": len(rows), "resolved_a2_target_count": len(resolved), "unresolved_a2_target_count": len(rows) - len(resolved),
        "a2_authority_rows": rows, "inherited_reviewed_authority_rows": old["reviewed_authority_rows"],
        "unreviewed_authority_surfaces": remaining,
        "remaining_unreviewed_surface_count_before": old["remaining_unreviewed_surface_count"],
        "remaining_unreviewed_surface_count": len(remaining), "out_of_scope_unreviewed_surface_count": old["out_of_scope_unreviewed_surface_count"],
        "checkpoint_criteria": criteria, "checkpoint_e_status": "INCOMPLETE", "p4_4_status": "INCOMPLETE",
        "remaining_blocker_ids": old["remaining_blocker_ids"],
        **{field: old[field] for field in ("workflow_count", "trigger_surface_count", "workflow_tree_before_sha1", "workflow_tree_after_sha1",
             "evolution_ledger_before_sha256", "evolution_ledger_after_sha256", "transition_count", "retirement_ledger_sha256", "retired_workflow_count",
             "live_missing_artifact_relation_count", "historical_missing_artifact_relation_count", "retention_blockers_A_B_C_D")},
        "actions": boundary.ZERO_ACTIONS, "review_grants_new_execution_authority": False,
        "caller_migration_authorized": False, "retirement_authorized": False,
        "source_review_counter_while_open": "3/5", "source_review_counter_if_owner_merges": "4/5", "mandatory_source_reread_due": False,
        "terminal": a2["terminal"],
    })


def validate_receipt(value, expected=None):
    boundary.require(value == (build_receipt() if expected is None else expected), "V3 differs from authenticated bounded A2 overlay")


def audit():
    value = boundary.read(RECEIPT_PATH)
    validate_receipt(value)
    return {"result": "PASS", "receipt_sha256": value["canonical_sha256"], "checkpoint_e": value["checkpoint_e_status"],
            "p4_4": value["p4_4_status"], "remaining_blockers": value["remaining_blocker_ids"],
            "remaining_unreviewed_surface_count": value["remaining_unreviewed_surface_count"], "terminal": value["terminal"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--emit-receipt", action="store_true")
    args = parser.parse_args()
    print(boundary.canonical(build_receipt() if args.emit_receipt else audit()).decode(), end="")


if __name__ == "__main__":
    main()
