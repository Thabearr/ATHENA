"""Publish verified canonical role metadata; diagnostic upload is not eligibility."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil

from domain.run_contracts import RunReceipt, RunRequest, canonical_json_bytes
from services import athena_artifact_role_resolver as roles


def build_manifest(artifact_root: Path, *, producer: dict, origins: dict,
                   restore_eligible: bool) -> dict:
    roles.require(type(restore_eligible) is bool, "exact eligibility bool required")
    role_rows = []
    for role_id in sorted(origins):
        role_rows.append(roles.build_role(role_id, artifact_root, origins[role_id]))
    value = {"schema_version": 1, "policy_id": roles.MANIFEST_POLICY_ID,
             "repository": roles.REPOSITORY, "producer": producer,
             "restore_eligible": restore_eligible, "roles": role_rows}
    value["canonical_sha256"] = roles.self_sha(value)
    if restore_eligible:
        candidate = roles.Candidate(producer["run_id"], producer["head_sha"], producer["workflow_path"],
                                     1, f"athena-run-{producer['run_id']}", event_name=producer["event_name"])
        for row in role_rows:
            if row["role_id"] != "RETAINED_SOURCE_EVIDENCE":
                roles.validate_manifest(roles.canonical(value), artifact_root, candidate,
                                        current_run_id=0, role_id=row["role_id"])
    return value


def publish(workspace: Path, *, run_id: int, head_sha: str, head_branch: str,
            event_name: str, execution_exit_code: str, preservation_result: str) -> dict:
    root = roles.safe_path(workspace, "artifacts/athena-run-workflow")
    root.mkdir(parents=True, exist_ok=True)
    request_path = roles.safe_path(root, "resolved-run-request.json")
    producer = {"workflow_family": "ATHENA_RUN", "workflow_path": roles.CANONICAL_WORKFLOW,
                "run_id": run_id, "head_sha": head_sha, "head_branch": head_branch,
                "event_name": event_name, "request_sha256": None}
    origins = {}
    eligible = False
    if request_path.is_file():
        request = RunRequest.from_json_bytes(request_path.read_bytes())
        producer["request_sha256"] = request.canonical_sha256
        receipt_path = roles.safe_path(workspace, f"artifacts/athena-runs/{request.canonical_sha256}/athena-run-receipt.json")
        if (execution_exit_code == "0" and preservation_result == "success" and
                head_branch == "main" and roles.hex_sha(head_sha, 40) and
                event_name in {"schedule", "workflow_dispatch"} and receipt_path.is_file()):
            raw = receipt_path.read_bytes()
            receipt = RunReceipt.from_json_bytes(raw)
            roles.require(canonical_json_bytes(receipt) == raw and receipt.request == request and
                          receipt.exact_commit_sha == head_sha, "canonical receipt/producer binding differs")
            eligible = request.authority_profile == "SHADOW"
    provenance_path = roles.safe_path(root, "artifact-role-restore-provenance-v1.json")
    provenance = roles.strict_json(provenance_path.read_bytes()) if provenance_path.is_file() else {}
    for role_id in ("DURABLE_HISTORY_PRIME", "PR119_BOOTSTRAP"):
        if role_id in provenance:
            origin = provenance[role_id]["origin_provenance"]
            staged = roles.safe_path(root, roles.ROLE_ROOTS[role_id])
            roles.require(roles.sha(roles.canonical(roles.inventory(staged))) ==
                          provenance[role_id]["inventory_sha256"], "staged restored role drifted")
            origins[role_id] = origin  # exact old origin retained, never relabelled
    identity_source = roles.safe_path(root, "identity-state/" + roles.STATE_FILENAME)
    if identity_source.is_file():
        destination = roles.safe_path(root, roles.ROLE_ROOTS["PERSISTENT_FIXTURE_IDENTITY_STATE"])
        destination.mkdir(parents=True, exist_ok=True)
        # A newly verified final state may extend the restored state. The
        # provenance keeps the original ancestry; only this staged payload is final.
        output = roles.safe_path(destination, roles.STATE_FILENAME)
        shutil.copyfile(identity_source, output)
        origins["PERSISTENT_FIXTURE_IDENTITY_STATE"] = {
            "source_kind": "CANONICAL_EXECUTION", "repository": roles.REPOSITORY,
            "workflow_path": roles.CANONICAL_WORKFLOW, "run_id": run_id, "head_sha": head_sha,
            "restored_ancestry": provenance.get("PERSISTENT_FIXTURE_IDENTITY_STATE", {}).get("origin_provenance")}
    source = roles.safe_path(root, roles.ROLE_ROOTS["RETAINED_SOURCE_EVIDENCE"])
    if source.is_dir() and any(source.rglob("*")):
        origins["RETAINED_SOURCE_EVIDENCE"] = {"source_kind": "CANONICAL_EXECUTION",
            "repository": roles.REPOSITORY, "workflow_path": roles.CANONICAL_WORKFLOW,
            "run_id": run_id, "head_sha": head_sha}
    value = build_manifest(root, producer=producer, origins=origins, restore_eligible=eligible)
    (root / roles.MANIFEST_FILENAME).write_bytes(roles.canonical(value))
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    roles.require(os.environ.get("GITHUB_REPOSITORY") == roles.REPOSITORY, "producer repository differs")
    result = publish(Path.cwd(), run_id=int(os.environ["GITHUB_RUN_ID"]), head_sha=os.environ["GITHUB_SHA"],
                     head_branch=os.environ.get("GITHUB_REF_NAME", ""), event_name=os.environ["GITHUB_EVENT_NAME"],
                     execution_exit_code=os.environ.get("ATHENA_EXECUTION_EXIT_CODE", ""),
                     preservation_result=os.environ.get("ATHENA_PRESERVATION_RESULT", ""))
    print(json.dumps({"canonical_sha256": result["canonical_sha256"],
                      "restore_eligible": result["restore_eligible"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
