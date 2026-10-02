"""Add retention acceptance over immutable V4; delegate completion authority."""
from __future__ import annotations

import argparse
import copy
import json

from scripts import audit_core_01d_historical_retention_acceptance as policy

ROOT = policy.ROOT
POLICY_ID = "ATHENA_CORE_01D_RETAINED_WORKFLOW_STATUS_V5"
RECEIPT_PATH = "artifacts/architecture/core_01d_retained_workflow_status_v5.json"
COMPLETION_PATH = "artifacts/architecture/core_01d_checkpoint_e_completion_v1.json"


def build_receipt(old: dict | None = None, accepted: dict | None = None) -> dict:
    old = policy.predecessor() if old is None else old
    accepted = policy.build_receipt(old) if accepted is None else accepted
    committed = policy.roles.strict_json((ROOT / policy.RECEIPT_PATH).read_bytes())
    policy.validate_receipt(committed, accepted)
    value = copy.deepcopy(old)
    value["closed_blockers"].append({
        "id": policy.v4.BLOCKER_D, "resolved_by": policy.POLICY_ID,
        "resolved_fact": "Owner accepts nine historical exact-byte retention limitations; no recovery, substitution or replay. Completion independently audited.",
    })
    value.update(
        schema_version=5, policy_id=POLICY_ID,
        predecessor_v4={"path": policy.v4.RECEIPT_PATH, "canonical_sha256": policy.V4_SHA,
                        "state": "IMMUTABLE_PRE_PASS_4_BEFORE_STATE"},
        pass4_base_main_sha=policy.BASE_MAIN, pass4_base_tree_sha=policy.BASE_TREE,
        historical_retention_policy=policy.POLICY_ID,
        historical_retention_acceptance={"path": policy.RECEIPT_PATH,
                                        "canonical_sha256": accepted["canonical_sha256"]},
        historical_retention_acceptance_layer=accepted["artifact_retentions"],
        supported_runtime_dependencies_on_unavailable_exact_bytes=0,
        unresolved_current_execution_blockers_from_these_artifacts=0,
        historical_exact_replay_limitations_explicitly_accepted=True,
        remaining_blocker_ids=[], remaining_blockers=[], remaining_blocker_family=None,
        closed_blocker_ids=[r["id"] for r in value["closed_blockers"]],
        checkpoint_e_status="CANDIDATE_COMPLETE_SUBJECT_TO_INDEPENDENT_AUDIT",
        p4_4_status="CANDIDATE_COMPLETE_SUBJECT_TO_INDEPENDENT_AUDIT",
        completion_authority=False, completion_authority_receipt_path=COMPLETION_PATH,
        remaining_blocker_scope="Missing-artifact retention only; independent completion criteria may still fail",
        source_review_counter_while_open="1/5", source_review_counter_if_owner_merges="2/5",
        mandatory_source_reread_due=False,
        terminal="CORE_01D_RETENTION_LIMITATIONS_ACCEPTED_COMPLETION_DELEGATED_DO_NOT_MERGE",
    )
    return policy.seal(value)


def validate_receipt(value: dict, expected: dict | None = None) -> None:
    policy.require(value.get("canonical_sha256") == policy.sha256(policy.canonical_bytes(
        {k: v for k, v in value.items() if k != "canonical_sha256"})), "V5 self-hash mismatch")
    policy.require(value["completion_authority"] is False, "V5 cannot authorize completion")
    policy.require(value == (build_receipt() if expected is None else expected),
                   "V5 rewrites historical meanings or bypasses independent completion")


def audit() -> dict:
    value = policy.roles.strict_json((ROOT / RECEIPT_PATH).read_bytes())
    validate_receipt(value)
    return {"result": "PASS", "policy_id": POLICY_ID, "receipt_sha256": value["canonical_sha256"],
            "completion_authority": False, "retention_blockers": value["remaining_blocker_ids"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if args.write:
        value = build_receipt()
        (ROOT / RECEIPT_PATH).write_bytes(policy.canonical_bytes(value))
        print(json.dumps({"result": "WROTE", "receipt_sha256": value["canonical_sha256"]}))
    else:
        print(json.dumps(audit(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
