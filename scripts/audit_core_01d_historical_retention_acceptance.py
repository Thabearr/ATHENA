"""Offline owner-authorized retention limitation; no recovery or execution authority."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime
import json
from pathlib import Path
import sys

from scripts import audit_core_01d_retained_workflow_status_v4 as v4
from services import athena_artifact_role_resolver as roles

ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "ATHENA_CORE_01D_HISTORICAL_RETENTION_ACCEPTANCE_V1"
RECEIPT_PATH = "artifacts/architecture/core_01d_historical_retention_acceptance_v1.json"
BASE_MAIN = "bccb33f009d57b9874243e52e79ebcb42c195be4"
BASE_TREE = "ec6817b0bf58261ed0c9b38af5b1e24c25c50297"
V4_SHA = "aee531727b1c1db3e382062b89d197b05ab9080126eeb2a596be23336e848410"
SNAPSHOT_PATH = "tests/fixtures/core_01d/historical-retention-availability-snapshot-v1.json"
SNAPSHOT_SHA = "458ff1a0adb312e4233b03e269b344efbbd2ba1b226015f2f78637b37490ed5e"
PAIRS = [(31887523012, 9249856559), (32410775191, 9422055017),
         (32455713912, 9437181220), (31953949073, 9266604353),
         (31987862156, 9274313978), (31990121181, 9275052993),
         (32046244761, 9292984849), (32628985683, 9491418446),
         (32049714066, 9294215497)]
CLASSIFICATIONS = {
    9249856559: "UNAVAILABLE_EXACT_HISTORICAL_REPLAY_SOURCE",
    9422055017: "UNAVAILABLE_EXACT_HISTORICAL_VERIFICATION_SOURCE",
    9437181220: "UNAVAILABLE_EXACT_HISTORICAL_VERIFICATION_SOURCE",
    9266604353: "UNAVAILABLE_HISTORICAL_LINEAGE_ARCHIVE",
    9274313978: "UNAVAILABLE_FORENSIC_FAILURE_ARCHIVE",
    9275052993: "UNAVAILABLE_EXACT_HISTORICAL_REPLAY_SOURCE",
    9292984849: "UNAVAILABLE_FORENSIC_PRE_ATTEMPT_ARCHIVE",
    9491418446: "PARTIAL_HISTORICAL_ARCHIVE_RETENTION",
    9294215497: "UNAVAILABLE_SUCCESSFUL_RESULT_ARCHIVE_WITH_SOURCE_CONTROLLED_REVIEW",
}
NO_AUTHORITY = dict.fromkeys(("replay_authorized", "provider_reacquisition_authorized",
    "synthetic_backfill_authorized", "evidence_substitution_authorized",
    "retirement_authorized", "deletion_authorized", "trigger_change_authorized",
    "caller_migration_authorized", "dispatch_authorized"), False)
ZERO_ACTIONS = dict.fromkeys(("provider", "sportsbook", "workflow_dispatch", "workflow_rerun",
    "workflow_cancel", "artifact_reconstruction", "source_regeneration", "drive_mutation",
    "gmail_mutation", "smtp", "model_training", "model_validation", "warehouse_rebuild",
    "share_code", "login", "cookies", "wallet", "stake", "wager", "evidence_substitution",
    "workflow_edit", "trigger_edit", "workflow_retirement", "workflow_deletion"), 0)
ZERO_DELTA = dict.fromkeys(("model", "probability", "price_all", "router", "portfolio",
    "provider", "authority"), 0)
canonical_bytes, seal, sha256 = v4.canonical_bytes, v4.seal, v4.sha256


class RetentionAcceptanceError(AssertionError):
    """Historical truth, authority or immutable evidence drift."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RetentionAcceptanceError(message)


def predecessor() -> dict:
    value = roles.strict_json((ROOT / v4.RECEIPT_PATH).read_bytes())
    require(value.get("canonical_sha256") == V4_SHA, "immutable V4 SHA changed")
    v4.validate_receipt(value)
    require(value["live_artifact_trigger_relationship_count"] == 0
            and value["historical_or_spent_artifact_trigger_relationship_count"] == 14,
            "unavailable bytes still have a live relationship")
    require(value["remaining_blocker_ids"] == [v4.BLOCKER_D], "V4 sole blocker D drift")
    require(all(not row["trigger_lifecycle"].startswith("LIVE_")
                and all(flag is False for flag in row["authorizations"].values())
                for row in value["current_artifact_trigger_relationships"]),
            "live relationship or granted authority in predecessor")
    return value


def validate_snapshot(value: dict) -> None:
    require(sha256(canonical_bytes(value)) == SNAPSHOT_SHA, "availability capture/provenance drift")
    rows = value["actions_observations"]
    require([(r["run_id"], r["expected_historical_artifact_id"]) for r in rows] == PAIRS,
            "nine run/artifact identities changed")
    for row in rows:
        require(row["state"] == "CURRENT_ACTIONS_ARTIFACT_LISTING_EMPTY"
                and row["total_count"] == 0 and row["artifacts"] == []
                and row["read_only"] is True
                and row["disappearance_cause_date_or_actor_inferred"] is False,
                "empty listing cannot imply disappearance cause or exact recovery")
        require(row["query_endpoint"] ==
                f"/repos/Thabearr/ATHENA/actions/runs/{row['run_id']}/artifacts",
                "availability endpoint drift")
        require(row["observed_at_utc"].endswith("Z") and
                datetime.fromisoformat(row["observed_at_utc"].replace("Z", "+00:00")).tzinfo,
                "UTC observation timestamp missing")
    old = v4.authenticate_sources()["external_drive_availability"]
    require(value["canonical_history_external_availability"] == old,
            "prior partial external copy was upgraded or reverified")


def load_snapshot() -> dict:
    raw = (ROOT / SNAPSHOT_PATH).read_bytes().replace(b"\r\n", b"\n")
    require(sha256(raw) == SNAPSHOT_SHA, "availability snapshot SHA changed")
    value = roles.strict_json(raw)
    validate_snapshot(value)
    return value


def historical_truth(old: dict) -> dict[int, dict]:
    artifacts = {r["artifact_id"]: r for r in old["artifact_dispositions"]}
    return {
        9249856559: {"fixed_projection_is_original_zip_recovery": False,
                    "fixed_projection_sha256": artifacts[9249856559]["distinct_successor_evidence"]["sha256"],
                    "pr139_raw_replay_available": False},
        9422055017: {"pr193_derived_output_is_raw_source": False,
                    "pr193_pr194_pr197_raw_replay_available": False},
        9437181220: {"pr202_catalog_admission_proven": False,
                    "candidate_upload_is_admission": False, "later_owner_sha_comment_is_admission": False,
                    "exact_byte_approval_gate_passed": False, "store_step_skipped": True},
        9266604353: {"metadata_reconciliation_is_v1_bytes_or_semantic_qualification": False,
                    "pr130_v2_spent": True},
        9274313978: {"qualification_success": False, "failure_before_runner_and_source": True},
        9275052993: {"raw_source_recovered": False, "pr145_successful_consumer_run_id": 32049714066,
                    "pr145_one_shot_completed": True, "pr145_successor_approved": False},
        9292984849: {"validator_input": False, "success_evidence": False,
                    "marker_checkout_download_validator_or_training_executed": False},
        9491418446: {"fully_recovered": False, "exact_archive_reconstructable": False,
                    "historical_transfer_completed": True, "successful_transfer_run_id": 32635585415,
                    "parts_found": artifacts[9491418446]["parts_found"],
                    "missing_parts": artifacts[9491418446]["missing_parts"]},
        9294215497: {"source_controlled_review_is_byte_equivalent_zip_substitute": False,
                    "review_state": old["pr145_result_review"]["review_state"],
                    "successor_approved": False,
                    "result_receipt": old["pr145_result_review"]["result_receipt"],
                    "predictions": old["pr145_result_review"]["predictions"]},
    }


def build_receipt(old: dict | None = None, snapshot: dict | None = None) -> dict:
    old = predecessor() if old is None else old
    snapshot = load_snapshot() if snapshot is None else snapshot
    truths = historical_truth(old)
    sources = {r["artifact_id"]: copy.deepcopy(r) for r in old["artifact_dispositions"]}
    sources[9294215497] = {
        "artifact_id": 9294215497, "run_id": 32049714066,
        "historical_result_identity": old["pr145_result_review"]["result_artifact"],
        "source_controlled_result_review": old["pr145_result_review"],
        "recovery_state": "METADATA_ONLY_NO_BYTES",
        "outside_original_eight_artifact_mission": True,
    }
    rows = []
    for run_id, artifact_id in PAIRS:
        rows.append({
            "artifact_id": artifact_id, "run_id": run_id,
            "historical_source": sources[artifact_id], "historical_truth": truths[artifact_id],
            "classification": CLASSIFICATIONS[artifact_id],
            "retention_disposition": "ACCEPTED_HISTORICAL_RETENTION_LIMITATION",
            "exact_bytes_recovered": False, "supported_current_runtime_dependency": False,
            "replay_available": False, **NO_AUTHORITY,
            "historical_claims_preserved": True, "checkpoint_e_blocking": False,
            "future_exact_recovery": "ADDITIVE_IF_LATER_DISCOVERED_DO_NOT_REWRITE_HISTORY",
        })
    return seal({
        "schema_version": 1, "policy_id": POLICY_ID, "repository": "Thabearr/ATHENA",
        "master_issue": 337, "base_main_sha": BASE_MAIN, "base_tree_sha": BASE_TREE,
        "predecessor_v4": {"path": v4.RECEIPT_PATH, "canonical_sha256": V4_SHA, "rewritten": False},
        "availability_snapshot": {"path": SNAPSHOT_PATH, "source_sha256": SNAPSHOT_SHA},
        "owner_authorization": {
            "source": "Owner CHECKPOINT-E BOUNDED PASS 4 instruction after PR #435 merge",
            "scope": "HISTORICAL_RETENTION_LIMITATION_CLASSIFICATION_ONLY",
            "standards_lowered": False, "completion_authority": False, **NO_AUTHORITY,
        },
        "artifact_retentions": rows, "original_artifact_count": 8,
        "separate_result_artifact_id": 9294215497, "retention_decision_count": len(rows),
        "current_actions_availability": snapshot["actions_observations"],
        "canonical_history_external_availability": snapshot["canonical_history_external_availability"],
        "live_missing_artifact_relation_count": 0, "historical_relation_count": 14,
        "supported_operations_depending_on_unavailable_bytes": 0,
        "exact_archive_recovery_count": 0, "replay_available_count": 0,
        "blocker_D": {"id": v4.BLOCKER_D, "state": "CLOSED_BY_OWNER_RETENTION_LIMITATION_ACCEPTANCE",
                      "archive_recovery_claimed": False, "limitations_preserved": True},
        "actions": ZERO_ACTIONS, "protected_semantic_delta": ZERO_DELTA,
        "action_count_scope": "Operational actions; excludes authorized Git/PR/master-issue administration",
        "source_review_counter_while_open": "1/5", "source_review_counter_if_owner_merges": "2/5",
        "mandatory_source_reread_due": False,
    })


def validate_receipt(value: dict, expected: dict | None = None) -> None:
    require(value.get("canonical_sha256") == sha256(canonical_bytes(
        {k: v for k, v in value.items() if k != "canonical_sha256"})), "retention receipt self-hash mismatch")
    for row in value["artifact_retentions"]:
        require(all(row[k] is False for k in NO_AUTHORITY)
                and row["exact_bytes_recovered"] is False
                and row["supported_current_runtime_dependency"] is False,
                "retention acceptance grants authority or falsely recovers bytes")
    require(value == (build_receipt() if expected is None else expected),
            "retention acceptance differs from immutable historical meanings/source")


def audit() -> dict:
    value = roles.strict_json((ROOT / RECEIPT_PATH).read_bytes())
    validate_receipt(value)
    return {"result": "PASS", "policy_id": POLICY_ID, "receipt_sha256": value["canonical_sha256"],
            "closed_blocker": v4.BLOCKER_D, "exact_archive_recovery_count": 0}


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
