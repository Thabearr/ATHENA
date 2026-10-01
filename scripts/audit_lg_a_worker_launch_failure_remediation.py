"""Offline LG-A caller-boundary and immutable failed-producer remediation proof."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timezone
import gzip
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
import zipfile

from domain.run_contracts import AuthorityManifest, RunReceipt, RunRequest, canonical_json_bytes
from runtime import worker_launcher as worker
from runtime.release_identity import verify_development_checkout
from runtime.source_identity import read_tracked_head_blob
from services import athena_artifact_role_resolver as roles
from services.athena_run_service import _run_reviewed_shadow_worker
from scripts.build_athena_artifact_role_manifest import publish
from scripts.restore_athena_artifact_roles import extract_verified_paths, manifest_root, restore_inputs, verify_archive_producer_receipt

ROOT = Path(__file__).resolve().parents[1]
BASE_MAIN = "426f36e60ebb421af003ed3154c4da48007d674a"
POLICY_ID = "ATHENA_LG_A_WORKER_LAUNCH_FAILURE_REMEDIATION_V1"
RECEIPT_PATH = "artifacts/architecture/lg_a_worker_launch_failure_remediation_v1.json"
FIXTURE = ROOT / "tests/fixtures/lg_a_worker_launch_failure"
SOURCE_PATHS = ("services/athena_run_service.py", "domain/current_shadow_run_contract_adapter.py",
                "services/athena_artifact_role_resolver.py", "scripts/build_athena_artifact_role_manifest.py",
                "scripts/restore_athena_artifact_roles.py")
FAILED = roles.Candidate(36846297806, BASE_MAIN, roles.CANONICAL_WORKFLOW, 11153681944, "athena-run-36846297806")
REQUEST_SHA = "a35cb4a421e5834a701ca64083d5c8e4494f1d0ded78ff0716f18976151c346b"
FAILED_RECEIPT_SHA = "f79d20e2a36bf15f8e92d6463fe764472326c2a4cc7a811eadb360a865a0f208"
MANIFEST_SELF_SHA = "f55b1cc0680ef9a8fee6e049924396dcb1239612cce9266954372c6fe83ff105"
REVIEWED_RECEIPT_SHA = "aa019106a5880bdace586da52c4e827dd6e8cd0d3663163fc8302305691e4927"


def tracked(path):
    return read_tracked_head_blob(ROOT, path)[0]


def historical_source(path, *, root=ROOT):
    """Permit only this sealed remediation successor, preserving old audit pins."""
    raw, identity = read_tracked_head_blob(root, path)
    value = roles.strict_json(read_tracked_head_blob(root, RECEIPT_PATH)[0])
    roles.require(value["canonical_sha256"] == REVIEWED_RECEIPT_SHA == roles.self_sha(value),
                  "exact reviewed remediation receipt differs")
    roles.require(path in SOURCE_PATHS and roles.sha(raw) == value["source_payload_sha256"][path],
                  "unreviewed remediation successor source")
    fixture = "tests/fixtures/lg_a_worker_launch_failure/pre-remediation-sources/" + Path(path).name + ".txt"
    return read_tracked_head_blob(root, fixture)


def bootstrap():
    raw = gzip.decompress(tracked("tests/fixtures/core_01b_artifact_roles/pr119-bootstrap.ndjson.gz"))
    roles.require(roles.sha(raw) == roles.BOOTSTRAP_SHA256, "retained bootstrap differs")
    return raw


def fixture_bytes(name):
    return tracked("tests/fixtures/lg_a_worker_launch_failure/" + name)


def successful_receipt(request=None, *, head=BASE_MAIN, status="RESEARCH_SHADOW_PORTFOLIO_READY_WITH_SHORTFALL"):
    request = request or RunRequest(dates=(date(2026, 10, 1),), target_legs=20, target_total_odds=None,
        bookie="sportybet", mode="research_shadow", authority_profile="SHADOW", create_share_code=False, place_wager=False)
    return RunReceipt(status=status, observed_at=datetime(2026, 10, 1, 10, tzinfo=timezone.utc),
        exact_commit_sha=head, request=request, selected_legs=({"synthetic": "OFFLINE_ONLY"},), shortfall=request.target_legs-1,
        stages=(), counts={"selected_leg_count": 1}, share_code_result=None,
        authority_manifest=AuthorityManifest(authority_profile="SHADOW", mode="research_shadow",
            provider_acquisition=True, share_code_generation=request.create_share_code,
            login=False, cookies=False, wallet=False, staking=False, wager=False), wager_placed=False)


def failed_archive(*, older=False):
    manifest = json.loads(fixture_bytes("artifact-role-manifest-v1.json"))
    receipt = fixture_bytes("athena-run-receipt.json")
    if older:
        manifest["producer"]["run_id"] = FAILED.run_id - 1
        receipt = canonical_json_bytes(successful_receipt())
        manifest["canonical_sha256"] = roles.self_sha(manifest)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("athena-run-workflow/" + roles.MANIFEST_FILENAME, roles.canonical(manifest))
        z.writestr(f"athena-runs/{REQUEST_SHA}/athena-run-receipt.json", receipt)
        z.writestr("athena-run-workflow/" + roles.ROLE_ROOTS["PR119_BOOTSTRAP"] + "/" + roles.BOOTSTRAP_FILENAME, bootstrap())
    return output.getvalue()


class OfflineTransport:
    bootstrap_origin = {"release_id": 373205103, "asset_id": 521090702, "asset_size_bytes": 10545099}
    def __init__(self, archives): self.archives, self.release_reads = archives, 0
    def artifact(self, candidate): return self.archives[candidate.artifact_id]
    def bootstrap(self):
        self.release_reads += 1
        return bootstrap()


def historical_producer_proof():
    roles.require(roles.sha(fixture_bytes("resolved-run-request.json")) == REQUEST_SHA, "failed request changed")
    roles.require(roles.sha(fixture_bytes("athena-run-receipt.json")) == FAILED_RECEIPT_SHA, "failed receipt changed")
    manifest_raw = fixture_bytes("artifact-role-manifest-v1.json")
    manifest = roles.strict_json(manifest_raw)
    roles.require(manifest["canonical_sha256"] == MANIFEST_SELF_SHA == roles.self_sha(manifest), "old manifest changed")
    roles.require(manifest["restore_eligible"] is True, "historical bad eligibility must remain true")
    with tempfile.TemporaryDirectory(prefix="lg-a-offline-restore-") as directory:
        root = Path(directory)
        download = root / "download"
        download.mkdir()
        bad = failed_archive()
        extract_verified_paths(bad, download)
        role_root = manifest_root(download)
        roles.validate_manifest(manifest_raw, role_root, FAILED, current_run_id=FAILED.run_id+1, role_id="PR119_BOOTSTRAP")
        try:
            verify_archive_producer_receipt(download, role_root, manifest_raw, FAILED)
        except roles.ArtifactRoleError as exc:
            roles.require("restore-ineligible" in str(exc), "unexpected historical rejection")
        else:
            raise ValueError("historical bad producer accepted")
        from dataclasses import replace
        older = replace(FAILED, run_id=FAILED.run_id-1, artifact_id=FAILED.artifact_id-1,
                        artifact_name=f"athena-run-{FAILED.run_id-1}")
        transport = OfflineTransport({FAILED.artifact_id: bad, older.artifact_id: failed_archive(older=True)})
        result = restore_inputs(root / "older", transport, current_run_id=FAILED.run_id+1,
                                canonical_candidates=[FAILED, older], legacy_candidates={})
        selected = result["roles"]["PR119_BOOTSTRAP"]["selected_source"]
        roles.require(selected["run_id"] == older.run_id and transport.release_reads == 0, "older valid fallback failed")
        result = restore_inputs(root / "release", transport, current_run_id=FAILED.run_id+1,
                                canonical_candidates=[FAILED], legacy_candidates={})
        roles.require(result["roles"]["PR119_BOOTSTRAP"]["selected_source"]["source_kind"] ==
                      "FIXED_RELEASE_READ_ONLY_COMPATIBILITY" and transport.release_reads == 1, "fixed release fallback failed")
    return {"historical_manifest_true_unchanged": True, "structural_manifest": "PASS",
            "producer_receipt_rejection": "PASS", "older_canonical_fallback": "PASS", "fixed_pr119_fallback": "PASS"}


@contextmanager
def production_run_directory(root):
    previous = Path.cwd()
    try:
        os.chdir(root)
        request = successful_receipt().request
        directory = Path("artifacts/athena-runs") / request.canonical_sha256
        directory.mkdir(parents=True)
        (directory / "athena-run-request.json").write_bytes(canonical_json_bytes(request))
        yield request, directory
    finally:
        os.chdir(previous)


def worker_boundary_proof():
    captured = []
    class Process:
        pid, returncode = 1234, 0
        def communicate(self): return "OFFLINE_OS_SEAM_ONLY", ""
        def poll(self): return 0
    def spawn(argv, **kwargs):
        roles.require(kwargs["shell"] is False and "timeout" not in kwargs, "worker launch authority drift")
        command = worker.WorkerCommand.from_json_bytes(Path(argv[argv.index("--command-file")+1]).read_bytes())
        captured.append(command)
        return Process()
    with tempfile.TemporaryDirectory(prefix="lg-a-offline-worker-") as directory:
        with production_run_directory(directory) as (request, run):
            identity = verify_development_checkout(ROOT)
            with patch.object(worker, "_spawn_process", spawn):
                _run_reviewed_shadow_worker(request, run_directory=run, exact_commit_sha=identity.head_commit_sha)
            command = captured[0]
            roles.require(command.run_directory.is_absolute() and command.run_directory == Path.cwd()/run,
                          "caller did not preserve exact absolute path")
            roles.require(command.operation == "CURRENT_SHADOW_REQUEST" and command.mode == "research_shadow" and
                          command.release_identity_id == identity.head_commit_sha and
                          command.request_artifact_id == request.canonical_sha256, "command binding drift")
            roles.require(roles.sha((run / "athena-run-request.json").read_bytes()) == request.canonical_sha256,
                          "request artifact changed")
    return {"production_relative_root": "PASS", "worker_command_publication": "PASS",
            "same_path_exact_request": "PASS", "shell": False, "operation": "CURRENT_SHADOW_REQUEST",
            "mode": "research_shadow", "outer_timeout_added": False, "real_children_spawned": 0}


def builder_proof():
    rows = []
    for status, delivery in (("RESEARCH_SHADOW_PORTFOLIO_READY", False),
        ("RESEARCH_SHADOW_PORTFOLIO_READY_WITH_SHORTFALL", False), ("RESEARCH_SHADOW_CODE_VERIFIED", True),
        ("RESEARCH_SHADOW_CODE_VERIFIED_WITH_SHORTFALL", True), ("EXECUTOR_UNAVAILABLE", False),
        ("SOURCE_INCOMPLETE", False), ("CODE_VERIFICATION_FAILED", True),
        ("SHADOW_DATE_POLICY_UNREPRESENTABLE", False), ("TARGET_TOTAL_ODDS_NOT_SUPPORTED", False)):
        from dataclasses import replace
        request = replace(successful_receipt().request, create_share_code=delivery)
        receipt = successful_receipt(request, status=status)
        with tempfile.TemporaryDirectory(prefix="lg-a-offline-builder-") as directory:
            root = Path(directory)
            workflow = root / "artifacts/athena-run-workflow"
            workflow.mkdir(parents=True)
            (workflow / "resolved-run-request.json").write_bytes(canonical_json_bytes(request))
            run = root / "artifacts/athena-runs" / request.canonical_sha256
            run.mkdir(parents=True)
            (run / "athena-run-receipt.json").write_bytes(canonical_json_bytes(receipt))
            value = publish(root, run_id=2, head_sha=BASE_MAIN, head_branch="main", event_name="workflow_dispatch",
                            execution_exit_code="0", preservation_result="success")
            expected = status in {"RESEARCH_SHADOW_PORTFOLIO_READY", "RESEARCH_SHADOW_PORTFOLIO_READY_WITH_SHORTFALL",
                                  "RESEARCH_SHADOW_CODE_VERIFIED", "RESEARCH_SHADOW_CODE_VERIFIED_WITH_SHORTFALL"}
            roles.require(value["restore_eligible"] is expected, "builder terminal eligibility differs")
            rows.append({"status": status, "create_share_code": delivery, "eligible": expected})
    return rows


def expected_receipt():
    changed = subprocess.check_output(["git", "diff", "--name-only", BASE_MAIN, "HEAD"], cwd=ROOT, text=True).splitlines()
    roles.require(not any(path.startswith(".github/workflows/") for path in changed), "workflow YAML changed")
    historical_changes = subprocess.check_output(["git", "diff", "--diff-filter=MD", "--name-only", BASE_MAIN,
                                                  "HEAD", "--", "artifacts"], cwd=ROOT, text=True).splitlines()
    roles.require(not historical_changes, "historical evidence artifact changed")
    for path in ("runtime/worker_launcher.py", "runtime/worker_entry.py"):
        roles.require(path not in changed, "worker security/operation boundary changed")
    roles.require("--output-root artifacts/athena-runs" in tracked(roles.CANONICAL_WORKFLOW).decode(), "production root changed")
    value = {"schema_version": 1, "policy_id": POLICY_ID, "base_main": BASE_MAIN,
        "failed_live_proof": {"run_id": FAILED.run_id, "attempt": 1, "head": BASE_MAIN, "github_conclusion": "SUCCESS",
            "canonical_status": "EXECUTOR_UNAVAILABLE", "error_type": "WorkerLaunchError", "current_shadow_triggered": False,
            "provider_acquisition": False, "dispatches_used": "1/1", "retries": 0},
        "artifact": {"id": FAILED.artifact_id, "name": FAILED.artifact_name, "size_bytes": 1366481,
            "zip_sha256": "efe42a986203619cfbffa1c01be10951c027ecb2636cdc4ddc2edb283a2adf56",
            "request_sha256": REQUEST_SHA, "receipt_sha256": FAILED_RECEIPT_SHA, "manifest_self_sha256": MANIFEST_SELF_SHA,
            "authority_manifest_canonical_json_lf_sha256": "0518b0fe59c4d65a02718180780d951da1f81f5c184fda9fdc65fea0e8eef8bb",
            "pr119_sha256": roles.BOOTSTRAP_SHA256, "worker_command_present": False, "inner_receipt_present": False},
        "root_cause": "RELATIVE_SERVICE_RUN_DIRECTORY_REJECTED_BY_ABSOLUTE_WORKER_COMMAND_BEFORE_PUBLICATION",
        "fix": "CWD_PREFIX_SAME_PATH_NO_RESOLVE_WORKER_SECURITY_UNCHANGED",
        "worker_boundary": worker_boundary_proof(), "restore_eligibility": historical_producer_proof(),
        "builder_matrix": builder_proof(), "role_manifest_schema": roles.MANIFEST_POLICY_ID,
        "source_payload_sha256": {path: roles.sha(tracked(path)) for path in SOURCE_PATHS},
        "worker_security_payload_sha256": roles.sha(tracked("runtime/worker_launcher.py")),
        "historical_evidence_changed": False, "workflow_yaml_changed": False,
        "safety_counts": dict.fromkeys(("live_dispatch", "provider", "delivery", "share_code_create", "share_code_reload",
                                       "email", "login", "cookies", "wallet", "stake", "wager"), 0),
        "governance": {"counter_while_open": "4/5", "counter_if_merged": "5/5", "mandatory_reread_after_merge": True,
            "reset_after_reread": "0/5", "clean_successor_proof": "INCOMPLETE", "new_lg_a_authorization": False,
            "core_01d": "BLOCKED", "caller_schedule_migration_retirement": "NOT_AUTHORIZED",
            "p4_4": "INCOMPLETE", "checkpoint_e": "INCOMPLETE"}}
    value["canonical_sha256"] = roles.self_sha(value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    expected = expected_receipt()
    if args.write:
        (ROOT / RECEIPT_PATH).write_bytes(roles.canonical(expected))
    else:
        roles.require(json.loads(tracked(RECEIPT_PATH)) == expected, "remediation evidence differs from rederivation")
    print(json.dumps({"result": "PASS", "canonical_sha256": expected["canonical_sha256"], "safety_counts": expected["safety_counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
