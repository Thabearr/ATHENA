"""E1 source evidence only; never launches workers or dispatches workflows."""
from pathlib import Path
import argparse
import hashlib
import json
import base64
import stat
import subprocess

from runtime.source_identity import (
    SourceIdentityError,
    read_tracked_head_blob,
    validate_repository_relative_path,
)

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
E1_RECEIPT_SHA256 = "de2222e7f1c472d7a336f8a4c9c7bec84c2e6ed533b8f568689a3857adaf4f71"
FORWARD_EVOLVED_SOURCE_PATHS = frozenset({
    "scripts/audit_checkpoint_e_workflows.py",
    "scripts/audit_data_01c_app_store_complete.py",
    "tests/test_core_01d_exact_pr_trigger_disposition_b1.py",
    "scripts/audit_run_01a_durable_admission.py",
    "services/athena_job_service.py",
    "database/run_repository.py",
    "run_desktop.py",
    "tests/test_run_01a_durable_admission.py",
    "services/athena_capability_service.py",
    "scripts/audit_data_01b_durable_run_state.py",
    "scripts/audit_data_01c_restore_portability.py",
    "tests/test_data_01c_app_storage.py",
})
FORWARD_EVOLVED_SOURCES = {
    "scripts/audit_checkpoint_e_workflows.py": {
        "predecessor_lf_sha256": "15f9e170d830358839a1d1ef5b500b28c8fa141dba6cf338bfe3af0656c4b794",
        "predecessor_fixture": "tests/fixtures/core_01d/run_01a_historical/pr457/audit-checkpoint-e-workflows-predecessor.py.txt",
    },
    "scripts/audit_data_01c_app_store_complete.py": {
        "predecessor_lf_sha256": "d14a742672454455ac82f9fc5a2a46e7b2124e7997986e6aa756ec0ddbe12369",
        "predecessor_fixture": "tests/fixtures/core_01d/run_01a_historical/pr457/audit-data-01c-app-store-complete-predecessor.py.txt",
    },
    "tests/test_core_01d_exact_pr_trigger_disposition_b1.py": {
        "predecessor_lf_sha256": "2dcbb770fec81944b3a1b504ec8041f6e87c915f16bb87ba616fd7966463d483",
        "predecessor_fixture": "tests/fixtures/core_01d/run_01a_historical/pr457/test-core-01d-exact-pr-trigger-disposition-b1-predecessor.py.txt",
    },
    "scripts/audit_run_01a_durable_admission.py": {
        "predecessor_lf_sha256": "97f62ebc4bd67932fe8b8acbe08d75b28c81acc5f99a0a2fb1f504e42a30ba4c",
        "predecessor_fixture": "tests/fixtures/core_01d/run_01a_historical/pr457/audit-run-01a-durable-admission-predecessor.py.txt",
    },
    "services/athena_job_service.py": {
        "predecessor_lf_sha256": "66e6b47836e9751d8791f7b70d93e723174dcf2257d90db8d3b8d981c92714c3",
        "predecessor_fixture": "tests/fixtures/core_01d/run_01a_historical/pr458/athena-job-service-predecessor.py.txt",
    },
    "database/run_repository.py": {
        "predecessor_lf_sha256": "b394a7013d3926f52af36223187eea8c44bb9b8424d21e6cfce6d5c0f6283e9f",
        "predecessor_fixture": "tests/fixtures/core_01d/run_01a_historical/pr458/run-repository-predecessor.py.txt",
    },
    "run_desktop.py": {
        "predecessor_lf_sha256": "c827b1ad3fe51a56b87e096af9d0ccf36f29a02f2e471967e4091c2b3fead5b4",
        "predecessor_fixture": "tests/fixtures/core_01d/run_01a_historical/pr463/run-desktop-predecessor.py.txt",
    },
    "tests/test_run_01a_durable_admission.py": {
        "predecessor_lf_sha256": "62ba29d3d3a05c15c50435dd1cee4eb9d4793939e784c292f2d5c157e127b122",
        "predecessor_fixture": "tests/fixtures/core_01d/run_01a_historical/pr463/test-run-01a-durable-admission-predecessor.py.txt",
    },
    "scripts/audit_data_01b_durable_run_state.py": {
        "predecessor_lf_sha256": "06cd75cab23b13553b561821c5e761bdefbc3393ab38f92e03465c35736bd0ff",
        "predecessor_fixture": "tests/fixtures/core_01d/run_01a_historical/pr461/audit-data-01b-durable-run-state-predecessor.py.txt",
    },
    "scripts/audit_data_01c_restore_portability.py": {
        "predecessor_lf_sha256": "5faf6540116e17e089382a296e16278e145da86aa0da682e02b22182d22f4728",
        "predecessor_fixture": "tests/fixtures/core_01d/run_01a_historical/pr461/audit-data-01c-restore-portability-predecessor.py.txt",
    },
    "tests/test_data_01c_app_storage.py": {
        "predecessor_lf_sha256": "3be15604a25453310671e965ec622c41513e8441a6e0b8ea4bc1568151d8606c",
        "predecessor_fixture": "tests/fixtures/core_01d/run_01a_historical/pr463/test-data-01c-app-storage-predecessor.py.txt",
        "predecessor_git_blob_sha1": "2110631b57af44102b36ce07e6124251310e855e",
    },
    "services/athena_capability_service.py": {
        "predecessor_lf_sha256": "f33cdb4207bac0ecc5daa72bfe0d264ea28c6453a9f6d6d6070c960501c8aef0",
        "predecessor_fixture": "tests/fixtures/core_01d/run_01a_historical/pr463/athena-capability-service-predecessor.py.txt",
        "predecessor_git_blob_sha1": "00fab1b190326f748fe705298838bf76a0ee78d0",
    },
}
FORWARD_SUCCESSOR_PATHS = frozenset({
    "tests/fixtures/core_01d/run_01a_historical/pr457/audit-checkpoint-e-workflows-predecessor.py.txt",
    "tests/fixtures/core_01d/run_01a_historical/pr457/audit-data-01c-app-store-complete-predecessor.py.txt",
    "tests/fixtures/core_01d/run_01a_historical/pr457/test-core-01d-exact-pr-trigger-disposition-b1-predecessor.py.txt",
    "tests/fixtures/core_01d/run_01a_historical/pr457/audit-run-01a-durable-admission-predecessor.py.txt",
    "tests/fixtures/core_01d/run_01a_historical/pr458/athena-job-service-predecessor.py.txt",
    "tests/fixtures/core_01d/run_01a_historical/pr458/run-repository-predecessor.py.txt",
    "tests/fixtures/core_01d/run_01a_historical/pr463/run-desktop-predecessor.py.txt",
    "tests/fixtures/core_01d/run_01a_historical/pr463/test-run-01a-durable-admission-predecessor.py.txt",
    "tests/fixtures/core_01d/run_01a_historical/pr463/test-data-01c-app-storage-predecessor.py.txt",
    "tests/fixtures/core_01d/run_01a_historical/pr463/athena-capability-service-predecessor.py.txt",
    "tests/fixtures/core_01d/run_01a_historical/pr461/audit-data-01b-durable-run-state-predecessor.py.txt",
    "tests/fixtures/core_01d/run_01a_historical/pr461/audit-data-01c-restore-portability-predecessor.py.txt",
    "tests/test_run_01a_forward_successor_pr457.py",
})

def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()

def _lf(raw):
    return raw.replace(b"\r\n", b"\n")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _validate_forward_evolved_sources():
    if set(FORWARD_EVOLVED_SOURCES) != set(FORWARD_EVOLVED_SOURCE_PATHS):
        raise AssertionError("E1 forward source allowlist drift")
    if not FORWARD_EVOLVED_SOURCE_PATHS <= set(SOURCES):
        raise AssertionError("E1 forward source is outside the frozen source set")
    for path, entry in FORWARD_EVOLVED_SOURCES.items():
        if (not {"predecessor_lf_sha256", "predecessor_fixture"} <= set(entry)
                or set(entry) - {"predecessor_lf_sha256", "predecessor_fixture",
                                 "predecessor_git_blob_sha1"}):
            raise AssertionError("E1 forward predecessor descriptor drift: " + path)


def _predecessor_bytes(path, *, root=ROOT):
    _validate_forward_evolved_sources()
    entry = FORWARD_EVOLVED_SOURCES.get(path)
    if entry is None:
        raise AssertionError("E1 predecessor fixture is not authorized: " + path)
    fixture = validate_repository_relative_path(entry["predecessor_fixture"])
    fixture_path = root.joinpath(*fixture.split("/"))
    try:
        resolved_root = root.resolve(strict=True)
        resolved_fixture = fixture_path.resolve(strict=True)
        resolved_fixture.relative_to(resolved_root)
        cursor = root
        parts = fixture.split("/")
        fixture_stat = None
        for index, part in enumerate(parts):
            cursor = cursor / part
            current = cursor.lstat()
            is_junction = getattr(cursor, "is_junction", lambda: False)()
            reparse = bool(getattr(current, "st_file_attributes", 0)
                           & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
            if stat.S_ISLNK(current.st_mode) or is_junction or reparse:
                raise AssertionError("E1 predecessor fixture path contains a symlink or junction: " + fixture)
            if index < len(parts) - 1 and not stat.S_ISDIR(current.st_mode):
                raise AssertionError("E1 predecessor fixture parent is not a directory: " + fixture)
            if index == len(parts) - 1:
                fixture_stat = current
        if fixture_stat is None or not stat.S_ISREG(fixture_stat.st_mode) or fixture_stat.st_nlink != 1:
            raise AssertionError("E1 predecessor fixture is not one regular file: " + fixture)
        tree = subprocess.run(
            ["git", "-C", str(root), "ls-tree", "-z", "HEAD", "--", fixture],
            check=True, capture_output=True, timeout=10,
        ).stdout
        if not tree:
            raise AssertionError("E1 predecessor fixture is not tracked at HEAD: " + fixture)
        metadata, tree_path = tree.rstrip(b"\0").split(b"\t", 1)
        mode, kind, tree_blob = metadata.decode("ascii").split(" ")
        if tree_path.decode("utf-8") != fixture or mode != "100644" or kind != "blob":
            raise AssertionError("E1 predecessor fixture HEAD mode or path mismatch: " + fixture)
        object_size = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-s", tree_blob],
            check=True, capture_output=True, timeout=10,
        ).stdout.decode("ascii").strip()
        if not object_size.isdecimal() or int(object_size) > 2_000_000:
            raise AssertionError("E1 predecessor fixture exceeds its fixed byte bound: " + fixture)
        fixture_raw, identity = read_tracked_head_blob(
            root, fixture, verify_worktree_filtered_identity=False,
        )
    except SourceIdentityError as error:
        raise AssertionError("E1 predecessor fixture HEAD identity is unavailable: " + fixture) from error
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError, ValueError) as error:
        raise AssertionError("E1 predecessor fixture cannot be authenticated from HEAD: " + fixture) from error
    if (len(fixture_raw) != int(object_size)
            or identity.git_blob_sha1 != tree_blob
            or (entry.get("predecessor_git_blob_sha1") is not None
                and tree_blob != entry["predecessor_git_blob_sha1"])):
        raise AssertionError("E1 predecessor fixture Git blob identity drift: " + path)
    worktree_limit = len(fixture_raw) + fixture_raw.count(b"\n")
    with fixture_path.open("rb") as handle:
        worktree_raw = handle.read(worktree_limit + 1)
    raw = _lf(fixture_raw)
    worktree_lf = _lf(worktree_raw)
    if len(worktree_raw) > worktree_limit or worktree_lf != raw:
        raise AssertionError("E1 predecessor fixture worktree differs from exact HEAD text: " + path)
    if _sha(raw) != entry["predecessor_lf_sha256"]:
        raise AssertionError("E1 predecessor fixture identity drift: " + path)
    return raw


def _historical_source_bytes(path, *, root=ROOT):
    if path in FORWARD_EVOLVED_SOURCE_PATHS:
        return _predecessor_bytes(path, root=root)
    return _lf((root / path).read_bytes())


def _source_identity_map(rows, *, label, digest_key="lf_source_sha256"):
    if not isinstance(rows, list):
        raise AssertionError(label + " source identities are missing")
    result = {}
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("path"), str)
                or not isinstance(row.get(digest_key), str)
                or row["path"] in result):
            raise AssertionError(label + " source identity shape drift")
        result[row["path"]] = row[digest_key]
    return result


def _verify_immutable_receipt():
    raw = (ROOT / RECEIPT).read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AssertionError("E1 immutable receipt is not valid JSON") from error
    digest = value.get("canonical_sha256") if isinstance(value, dict) else None
    body = {key: child for key, child in value.items() if key != "canonical_sha256"} if isinstance(value, dict) else {}
    if (raw != canonical(value) or digest != E1_RECEIPT_SHA256
            or _sha(canonical(body)) != E1_RECEIPT_SHA256):
        raise AssertionError("E1 immutable receipt identity drift")
    rebuilt = canonical(build_receipt())
    if raw != rebuilt:
        raise AssertionError("E1 immutable receipt source identity drift")
    return value


def _authenticate_current_sources(historical_identities, a2_rows, *, root=ROOT, tracked_paths=None):
    _validate_forward_evolved_sources()
    if set(historical_identities) != set(SOURCES):
        raise AssertionError("E1 frozen source identity set drift")
    current_a2 = _source_identity_map(a2_rows, label="A2")
    if tracked_paths is None:
        from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
        tracked_paths = set(boundary.git(
            "ls-files", "--", *sorted(FORWARD_EVOLVED_SOURCE_PATHS)
        ).decode().splitlines())
    for path in SOURCES:
        current = _sha(_lf((root / path).read_bytes()))
        frozen = historical_identities[path]
        if path not in FORWARD_EVOLVED_SOURCE_PATHS:
            if current != frozen:
                raise AssertionError("E1 unlisted source evidence drift: " + path)
            continue
        entry = FORWARD_EVOLVED_SOURCES[path]
        predecessor = _predecessor_bytes(path, root=root)
        if _sha(predecessor) != frozen or frozen != entry["predecessor_lf_sha256"]:
            raise AssertionError("E1 predecessor does not match frozen receipt: " + path)
        if path not in tracked_paths:
            raise AssertionError("E1 current successor source is not tracked: " + path)
        a2_identity = current_a2.get(path)
        if a2_identity is None:
            raise AssertionError("E1 current source is absent from A2 inventory: " + path)
        if current != a2_identity:
            raise AssertionError("E1 current source differs from authenticated A2 bytes: " + path)
    return current_a2


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
        "source_identities": [{"path": path, "lf_sha256": _sha(
            _historical_source_bytes(path))} for path in SOURCES],
    }
    value["canonical_sha256"] = _sha(canonical(value))
    if value["canonical_sha256"] != E1_RECEIPT_SHA256:
        raise AssertionError("E1 immutable receipt reconstruction identity drift")
    return value

def authenticate_successor():
    from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
    latest = boundary.authenticate_inventory()
    if type(latest.get("generation")) is not int or latest["generation"] < 119:
        raise AssertionError("atomic E1 requires A2 V119 successor")
    receipt = _verify_immutable_receipt()
    historical = _source_identity_map(
        receipt.get("source_identities"), label="E1", digest_key="lf_sha256"
    )
    _authenticate_current_sources(
        historical,
        latest.get("source_identities"),
        tracked_paths=set(boundary.git(
            "ls-files", "--", *sorted(FORWARD_EVOLVED_SOURCE_PATHS)
        ).decode().splitlines()),
    )
    return {RECEIPT, "docs/product/run_01a_durable_admission.md",
            "services/athena_job_service.py", "scripts/audit_run_01a_durable_admission.py",
            "tests/test_run_01a_durable_admission.py",
            "tests/fixtures/core_01d/run_01a_historical/d3_run_desktop.py.b64",
            "tests/fixtures/core_01d/run_01a_historical/d5_run_previews.py.b64",
            *FORWARD_SUCCESSOR_PATHS}

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
