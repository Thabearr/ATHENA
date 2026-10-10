"""E1 source evidence only; never launches workers or dispatches workflows."""
from pathlib import Path
import argparse
import hashlib
import json
import base64

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = "artifacts/product/run_01a_durable_admission_v1.json"
SOURCES = (
    "docs/product/run_01a_durable_admission.md",
    "services/athena_job_service.py", "database/run_repository.py",
    "api/app_factory.py", "api/v1/run_previews.py", "run_desktop.py",
    "services/athena_capability_service.py",
    "scripts/audit_data_01b_durable_run_state.py",
    "scripts/audit_data_01c_app_store_complete.py",
    "scripts/audit_run_01a_durable_admission.py",
    "tests/test_run_01a_durable_admission.py",
    "tests/test_data_01c_app_storage.py",
    "tests/test_core_01d_exact_pr_trigger_disposition_b1.py",
    "scripts/audit_checkpoint_e_workflows.py",
    "scripts/audit_data_01c_restore_portability.py",
    "tests/fixtures/core_01d/run_01a_historical/d5_run_previews.py.b64",
    "tests/fixtures/core_01d/run_01a_historical/d3_run_desktop.py.b64",
)

def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()

def build_receipt():
    predecessors = {}
    for path, digest in (
        ("artifacts/product/data_01c_app_store_complete_v1.json", "c9be3cc4c74fea16c9f97c0db3fe7b54d9e12373fc5787d46677f36276f7441d"),
        ("artifacts/product/data_01c_restore_portability_v1.json", "f85937fae092981c655b0fa66756527633549b867209bb731171ab7d6e1e6a97"),
        ("tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v115.json", "aace476979f237523997ab8761ddcf6d27bf24b83be861d2d8ba4927116e30c8"),
    ):
        value = json.loads((ROOT / path).read_bytes())
        seal = value.pop("canonical_sha256")
        if seal != digest or hashlib.sha256(canonical(value)).hexdigest() != digest:
            raise AssertionError("E1 immutable predecessor mismatch: " + path)
        predecessors[path] = {"canonical_sha256": digest, "rewritten": False}
    value = {
        "schema_version": 1, "policy_id": "ATHENA_RUN_01A_DURABLE_ADMISSION_V1",
        "base_main_sha": "74b07c74a946fd19a63f5695055b09668268aef2",
        "post_d5_tests_run": 38013673204,
        "predecessors": predecessors,
        "a2_successor_generation": 119,
        "cancellation": "E3_DEFERRED_CANCEL_STORE_UNAVAILABLE_NON_MUTATING",
        "launch_failure_diagnostic": "WORKER_LAUNCH_FAILED_ATOMIC_WITH_INTERRUPTED",
        "launch_failure_atomicity": "DIAGNOSTIC_AND_INTERRUPTED_COMMIT_TOGETHER_OR_ROLL_BACK",
        "launch_failure_retry": "NO_RETRY",
        "later_missions": "E2_E3_E4_UNSTARTED",
        "ordering": "ATOMIC_ADMISSION_COMMIT_BEFORE_ATTEMPT_STAGING_OR_LAUNCH",
        "replay": "SAME_COMMITTED_IDENTITY_NO_SECOND_LAUNCH_INCLUDING_AFTER_EXPIRY_AND_RESTART",
        "launch_failure": "COMMIT_RETAINED_ATOMIC_DIAGNOSTIC_INTERRUPTION_OR_RUNNING_ON_STORE_FAILURE",
        "crash_gap": "QUEUED_OR_NONTERMINAL_NO_AUTOMATIC_REDISPATCH",
        "worker_operation": "OFFLINE_IDENTITY_PROBE",
        "installed_desktop": "FAIL_CLOSED_ADMISSION_UNTIL_PINNED_WORKER_INTEGRATION",
        "execution_completion_and_installed_producer_provenance": "E2_OPEN_NOT_IMPLEMENTED",
        "source_review_counter": "0/5_UNTIL_OWNER_AUTHORIZED_MERGE",
        "merge_authorized": False,
        "hosted_ci": "NATURAL_EXACT_HEAD_REQUIRED_SEPARATELY",
        "prohibited_runtime_actions": dict.fromkeys(("provider", "live_shadow", "share_code",
            "login", "cookie", "wallet", "stake", "wager", "delivery", "manual_workflow"), 0),
        "source_identities": [{"path": path, "lf_sha256": hashlib.sha256(
            (ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()} for path in SOURCES],
    }
    value["canonical_sha256"] = hashlib.sha256(canonical(value)).hexdigest()
    return value

def authenticate_successor():
    from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
    latest = boundary.authenticate_inventory()
    if latest["generation"] < 119:
        raise AssertionError("atomic E1 requires A2 V119 successor")
    if (ROOT / RECEIPT).read_bytes() != canonical(build_receipt()):
        raise AssertionError("E1 source evidence drift")
    return {RECEIPT, "docs/product/run_01a_durable_admission.md",
            "services/athena_job_service.py", "scripts/audit_run_01a_durable_admission.py",
            "tests/test_run_01a_durable_admission.py",
            "tests/fixtures/core_01d/run_01a_historical/d3_run_desktop.py.b64",
            "tests/fixtures/core_01d/run_01a_historical/d5_run_previews.py.b64"}

def predecessor_admission_source():
    from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
    payload = base64.b64decode((ROOT / "tests/fixtures/core_01d/run_01a_historical/d5_run_previews.py.b64").read_bytes(), validate=True)
    inventory = boundary.read_generation(boundary.inventory_generation_path(115))
    if inventory["canonical_sha256"] != "aace476979f237523997ab8761ddcf6d27bf24b83be861d2d8ba4927116e30c8":
        raise AssertionError("E1 admission predecessor inventory mismatch")
    expected = next(row["lf_source_sha256"] for row in inventory["source_identities"]
                    if row["path"] == "api/v1/run_previews.py")
    if hashlib.sha256(payload.replace(b"\r\n", b"\n")).hexdigest() != expected:
        raise AssertionError("E1 admission predecessor bytes mismatch")
    return payload

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    raw = canonical(build_receipt())
    path = ROOT / RECEIPT
    if args.write:
        path.write_bytes(raw)
    elif path.read_bytes() != raw:
        raise AssertionError("E1 source evidence drift")
    print("RUN_01A_SOURCE_EVIDENCE_OK")

if __name__ == "__main__":
    main()
