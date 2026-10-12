"""Non-writing prerequisite source/evidence audit; no execution authority."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = "artifacts/product/run_02a_pre_durable_share_send_v1.json"
BASE = "4125624948deb314278004df5f13a627d31f8fd2"
V142_SHA = "ea45174c6c5d6203ee9fab78f589c87ea86000871e4dd8b746e172befdd62b56"
SOURCES = (
    "database/run_repository.py", "runtime/worker_entry.py",
    "scripts/sportybet_direct_share_bridge.py", "services/athena_job_service.py",
    "services/durable_share_code_transport.py", "scripts/audit_run_01b_worker_lifecycle.py",
    "scripts/audit_core_01d_checkpoint_e_completion_v2.py", "scripts/audit_checkpoint_e_workflows.py",
    "scripts/audit_run_02a_pre_durable_share_send.py", "tests/test_core_01d_exact_pr_trigger_disposition_b1.py",
    "tests/test_run_02a_pre_durable_share_send.py", "tests/native/test_run_02a_pre_share_send_publication.py",
)
HISTORY = {
    "artifacts/product/run_01a_durable_admission_v1.json": "de2222e7f1c472d7a336f8a4c9c7bec84c2e6ed533b8f568689a3857adaf4f71",
    "artifacts/product/run_01b_worker_lifecycle_v1.json": "e0e76d6fa375028ca4f248134ae61fb2717fd7333104ae8a696544931febc203",
}


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode()


def seal(value):
    value = dict(value)
    value.pop("canonical_sha256", None)
    value["canonical_sha256"] = hashlib.sha256(canonical(value)).hexdigest()
    return value


def build_receipt(source_head):
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    from domain import current_shadow_sportybet_pc_upcoming_reconciliation as policy
    latest = a2.authenticate_inventory()
    chain = a2.load_inventory_generations()
    if latest["generation"] < 143 or chain[141][1]["canonical_sha256"] != V142_SHA:
        raise AssertionError("prerequisite requires append-only successor from V142")
    for path, expected in HISTORY.items():
        value = json.loads((ROOT / path).read_bytes())
        if seal(value) != value or value["canonical_sha256"] != expected:
            raise AssertionError("historical receipt changed: " + path)
    if policy.calculate_policy_sha256() != "9dc0cfb362cf7008d28bcf029755b7361481b683e41155528f9607047773ceba":
        raise AssertionError("PR457 runtime policy changed")
    current = {row["path"]:row["lf_source_sha256"] for row in latest["source_identities"]}
    identities = {}
    for path in SOURCES:
        digest = hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        if current.get(path) != digest:
            raise AssertionError("source differs from authenticated A2: " + path)
        identities[path] = digest
    if (type(source_head) is not str or len(source_head) != 40
            or any(c not in "0123456789abcdef" for c in source_head)):
        raise AssertionError("invalid source commit identity")
    return seal({
        "schema_version": 1, "policy_id": "ATHENA_RUN_02A_PRE_DURABLE_SHARE_SEND_V1",
        "base_main": BASE, "source_head": source_head,
        "final_head_binding": "PR_AND_NATURAL_HOSTED_EXACT_HEAD_ATTESTATION_WITH_EXACT_SOURCE_HASHES",
        "source_identities": identities,
        "document_lf_sha256": hashlib.sha256((ROOT / "docs/product/run_02a_pre_durable_share_send.md").read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        "a2": {"generation": latest["generation"], "canonical_sha256": latest["canonical_sha256"],
               "immutable_predecessor_generation": 142, "immutable_predecessor_canonical_sha256": V142_SHA,
               "predecessor_rewritten": False},
        "history": HISTORY,
        "operation_kind": "SPORTYBET_SHARE_CODE_CREATE_V1",
        "write_ahead": "PREPARED_FULL_COMMIT_THEN_SENT_FULL_COMMIT_THEN_ONE_POST_MAXIMUM",
        "intent": "EXACT_ADMITTED_RUN_REQUEST_ENVELOPE_RELEASE_AUTHORITY_AND_CANONICAL_POST_BODY",
        "response": "IMMUTABLE_LOSSLESS_RAW_BYTES_STATUS_SHA_BYTE_COUNT_RUN_OPERATION_METHOD_AND_INTENT_BINDING",
        "classification": {"before_sent": "FAILED_ONLY_WITH_SHARE_CREATE_NEVER_SENT_AND_ZERO_POST",
                           "retained_success": "HTTP_200_BIZCODE_10000_RECOGNIZED_CODE_TO_CONFIRMED",
                           "post_sent_unproven": "OUTCOME_UNKNOWN_NEVER_FAILED",
                           "provider_proven_failed": "BLOCKED_NO_REVIEWED_NO_CREATE_CONTRACT"},
        "no_resend": "SERIALIZED_RUN_KIND_INTENT_CHECK_ALL_STATES_ALL_ATTEMPTS_ALL_IDEMPOTENCY_KEYS",
        "reload": "EXPLICIT_GET_ONLY_FROM_RETAINED_CONFIRMED_CREATE_CODE_NO_SECOND_POST",
        "authority": "REAUTHENTICATED_ADMITTED_CAPABILITY_NO_ACCOUNT_OR_WAGER_AUTHORITY",
        "product_delivery": "BLOCKED_NO_WORKER_INTEGRATION",
        "migration": "NONE_EXISTING_BEGIN_IMMEDIATE_SERIALIZATION",
        "run_02a": "BLOCKED_UNSTARTED_PENDING_PREREQUISITE_MERGE_AND_INDEPENDENT_ACCEPTANCE",
        "e4_e5": "UNSTARTED", "source_review_counter_while_unmerged": "3/5",
        "restricted_action_counts": dict.fromkeys(("provider_acquisition", "live_current_shadow", "fresh_holdout",
            "real_share_code_create", "delivery", "login", "cookies", "wallet", "stake", "wager", "email",
            "manual_workflow_dispatch", "manual_workflow_rerun", "manual_workflow_cancel"), 0),
        "review_ready": False, "merge_authorized": False,
        "residual_blocker": "MANDATORY_PROVIDER_PROVEN_FAILED_ACCEPTANCE_HAS_NO_REVIEWED_CONTRACT",
        "hosted_gates": "NATURAL_EXACT_HEAD_TESTS_AND_PORT02C_REQUIRED_RECORDED_IN_PR_BODY",
    })


def audit():
    raw = (ROOT / RECEIPT_PATH).read_bytes()
    value = json.loads(raw)
    if raw != canonical(value) or value != build_receipt(value["source_head"]):
        raise AssertionError("prerequisite source/evidence drift")
    return {"result": "PASS", "canonical_sha256": value["canonical_sha256"],
            "a2_generation": value["a2"]["generation"], "review_ready": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
        (ROOT / RECEIPT_PATH).write_bytes(canonical(build_receipt(head)))
    print(json.dumps(audit(), sort_keys=True))


if __name__ == "__main__":
    main()
