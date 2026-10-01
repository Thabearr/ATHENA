"""Offline CORE-01B ancestry parity, exact maintenance and append-only evidence."""
from __future__ import annotations

import argparse
import copy
import gzip
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

import yaml

from runtime.source_identity import read_tracked_head_blob
from services import athena_artifact_role_resolver as roles
from scripts import audit_p4_workflow_evolution_ledger as evolution
from scripts.build_athena_artifact_role_manifest import build_manifest
from scripts.restore_athena_artifact_roles import restore_inputs

ROOT = Path(__file__).resolve().parents[1]
BASE_MAIN = "50867a67b08eb6a5be653d41962d132fd2d81a58"
POLICY_ID = "ATHENA_CORE_01B_CANONICAL_ARTIFACT_ANCESTRY_V1"
TRANSITION_ID = "CORE01B_ATHENA_RUN_CANONICAL_ARTIFACT_ANCESTRY_V1"
RECEIPT_PATH = "artifacts/architecture/core_01b_canonical_artifact_ancestry_v1.json"
SNAPSHOT_PATH = "artifacts/architecture/p4_workflow_evolution_snapshots/core_01b_athena_run_canonical_artifact_ancestry_v1.json"
PREDECESSOR_PATH = "artifacts/architecture/p4_workflow_evolution_snapshots/port_02c_native_runtime_slice_v1.json"
PREDECESSOR_SHA = "d1c8d79ac48bf0521a609e29991014513bd2f7afed2389c5e3a9d6ec8bfba8a2"
BEFORE_FIXTURE = "tests/fixtures/architecture/revised_workflows/athena-run-pre-core-01b-canonical-artifact-ancestry.yml"
BEFORE_IDENTITY = {"git_blob_sha1": "08a05d011d570695a2191153b5c55a4e536cbd04",
                   "source_sha256": "7826f24c589f37b5908461cf949d818445c3dbacffe021f7290d67f9edbfae74"}
BOOTSTRAP_FIXTURE = "tests/fixtures/core_01b_artifact_roles/pr119-bootstrap.ndjson.gz"
SOURCE_PATHS = ["services/athena_artifact_role_resolver.py", "scripts/restore_athena_artifact_roles.py",
                "scripts/build_athena_artifact_role_manifest.py", roles.CANONICAL_WORKFLOW]
HISTORICAL_PATHS = [
    "artifacts/architecture/core_01_schedule_date_disposition_v1.json",
    "artifacts/architecture/auth_01b_athena_run_explicit_delivery_intent_v1.json",
    "artifacts/architecture/p4_4h_current_shadow_canonical_run_migration_review_v1.json",
    "artifacts/architecture/p4_4m_athena_run_pc_upcoming_evidence_preservation_v1.json",
    "artifacts/architecture/auth_01_analysis_only_shadow_v1.json",
    "artifacts/architecture/port_02_native_runtime_v1.json",
    PREDECESSOR_PATH,
    ".github/workflows/current-shadow-all-market.yml",
    ".github/workflows/current-shadow-history-cache-prime.yml",
    ".github/workflows/p3-0-comparison-evidence-capture.yml",
]
HISTORICAL_BLOBS = {
    ".github/workflows/current-shadow-all-market.yml": "4321d70563e98acaf1663f5a7b28781908535328",
    ".github/workflows/current-shadow-history-cache-prime.yml": "22d3f04288e434b5edf67e419e99a706641a859d",
    ".github/workflows/p3-0-comparison-evidence-capture.yml": "0d0d2285e7b17ca625288ec295884433e3c3cedd",
    "artifacts/architecture/auth_01_analysis_only_shadow_v1.json": "2270ae97e1529e620ad9df4e77df9510b10a453a",
    "artifacts/architecture/auth_01b_athena_run_explicit_delivery_intent_v1.json": "f9134cba777859c923d5eec0812d586d2ee5671c",
    "artifacts/architecture/core_01_schedule_date_disposition_v1.json": "508d444bc981f332420fa10ac6b394fe4f22efa6",
    "artifacts/architecture/p4_4h_current_shadow_canonical_run_migration_review_v1.json": "924febf73ab39a55433e69fd64cc203d493d68df",
    "artifacts/architecture/p4_4m_athena_run_pc_upcoming_evidence_preservation_v1.json": "b79f610bfe06c550584a7c305bf721b94c5efba9",
    PREDECESSOR_PATH: "a8882c7659e4f92c0a6b50d5bb3e2c85363d87a3",
    "artifacts/architecture/port_02_native_runtime_v1.json": "d21ff8cef38d6a06045f200bcdef981fa5034118",
}


def tracked(path: str):
    if path == ".github/workflows/current-shadow-all-market.yml":
        from scripts import audit_core_01_schedule_date_disposition as c1
        raw, identity = read_tracked_head_blob(ROOT, path)
        if identity.git_blob_sha1 == c1.CORE01C_WORKFLOW_AFTER_BLOB:
            roles.require(identity.git_blob_payload_sha256 == c1.CORE01C_WORKFLOW_AFTER_SHA256, "C2/C3 successor SHA differs")
            from scripts.audit_core_01c_notification_comment_compatibility import verify_workflow_authority as verify_c3
            historical, historical_identity = read_tracked_head_blob(ROOT, c1.CORE01C_BEFORE_FIXTURE)
            verify_c3(historical, raw)
            return historical, historical_identity
    return read_tracked_head_blob(ROOT, path)


def verify_workflow_authority(before: bytes, after: bytes) -> None:
    old = yaml.load(before, Loader=yaml.BaseLoader)
    new = yaml.load(after, Loader=yaml.BaseLoader)
    old_job = old["jobs"]["canonical-run"]
    new_job = new["jobs"]["canonical-run"]
    for key in ("name", "on", "permissions", "concurrency"):
        roles.require(old[key] == new[key], f"workflow authority surface drift: {key}")
    roles.require(set(old["jobs"]) == set(new["jobs"]) and
                  {k: v for k, v in old_job.items() if k != "steps"} ==
                  {k: v for k, v in new_job.items() if k != "steps"}, "job authority/timeout/Python runner drift")
    old_steps = {step["id"]: step for step in old_job["steps"]}
    new_steps = {step["id"]: step for step in new_job["steps"]}
    removed = {"restore_history_prime", "restore_pr119", "restore_identity"}
    added = {"restore_artifact_roles", "build_artifact_roles"}
    roles.require(set(new_steps) == (set(old_steps) - removed) | added, "unexpected step change")
    for key in set(old_steps) - removed - {"propagate_failure"}:
        roles.require(old_steps[key] == new_steps[key], f"unchanged step drift: {key}")
    restore = new_steps["restore_artifact_roles"]
    roles.require(restore["run"] == "python -m scripts.restore_athena_artifact_roles --restore-inputs" and
                  restore["if"] == old_steps["restore_history_prime"]["if"] and
                  restore["env"] == old_steps["restore_history_prime"]["env"] and restore["shell"] == "bash",
                  "role restore transport/guard differs")
    build = new_steps["build_artifact_roles"]
    roles.require(build["run"] == "python -m scripts.build_athena_artifact_role_manifest" and
                  build["if"] == "always()" and build["shell"] == "bash" and build["env"] == {
                      "ATHENA_EXECUTION_EXIT_CODE": "${{ steps.execute_request.outputs.exit_code }}",
                      "ATHENA_PRESERVATION_RESULT": "${{ steps.preserve_shadow_evidence.outcome }}",
                      "PYTHONPATH": "${{ github.workspace }}"}, "role publication contract differs")
    expected = copy.deepcopy(old_steps["propagate_failure"])
    for key in ("HISTORY_PRIME_RESULT", "PR119_RESULT", "IDENTITY_RESULT"):
        del expected["env"][key]
    expected["env"].update(ARTIFACT_ROLES_RESULT="${{ steps.restore_artifact_roles.outcome }}",
                           ROLE_MANIFEST_RESULT="${{ steps.build_artifact_roles.outcome }}")
    expected["run"] = expected["run"].replace(
        '"${HISTORY_PRIME_RESULT}"', '"${ARTIFACT_ROLES_RESULT}"').replace(
        '"${PR119_RESULT}" "${IDENTITY_RESULT}"', '"${ROLE_MANIFEST_RESULT}"')
    roles.require(new_steps["propagate_failure"] == expected, "failure propagation changed beyond role steps")
    order = [step["id"] for step in new_job["steps"]]
    roles.require(order.index("install_dependencies") < order.index("restore_artifact_roles") <
                  order.index("execute_request") < order.index("preserve_shadow_evidence") <
                  order.index("build_artifact_roles") < order.index("upload_evidence") <
                  order.index("propagate_failure"), "role restore/publication ordering differs")
    for literal in ("current-shadow-history-cache-prime.yml/runs", "--name current-shadow-history-cache-prime",
                    "current-shadow-all-market.yml/runs", "--name current-shadow-all-market-request"):
        roles.require(literal not in after.decode(), "direct legacy lookup remains")


def zip_tree(root: Path) -> bytes:
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.writestr(path.relative_to(root).as_posix(), path.read_bytes())
    return result.getvalue()


def synthetic_inputs(root: Path) -> tuple[Path, Path]:
    """Synthetic prime cache and seed-only identity; never live/retained history proof."""
    from scripts import current_shadow_history_github_persistent_cache as cache
    from scripts import prime_current_shadow_history_github_cache as prime
    from scripts import restore_current_shadow_history_prime_artifact as restore
    from domain import current_shadow_fixture_identity_v2 as identity
    history = root / "synthetic-history"
    cache._persist(history / "history-cache", "/repos/Thabearr/ATHENA/actions/artifacts/123/zip", b"SYNTHETIC_C2_CACHE_PAYLOAD")
    count, size, inventory_sha = prime._cache_inventory(history / "history-cache")
    receipt = {"schema_version": prime.SCHEMA_VERSION, "status": prime.STATUS,
               "exact_commit_sha": "a" * 40, "captured_run_universe_count": 1,
               "cached_immutable_binary_entry_count": count, "cached_immutable_binary_payload_bytes": size,
               "cache_inventory_sha256": inventory_sha,
               **dict.fromkeys(restore._AUTHORITY_FIELDS, False)}
    (history / restore.PRIME_RECEIPT_FILENAME).write_bytes(prime._canonical(receipt))
    state = root / "synthetic-identity"
    state.mkdir()
    payload = {"schema_version": identity.STATE_SCHEMA_VERSION, "policy_id": identity.POLICY_ID,
               "matching_basis": identity.MATCHING_BASIS, "seed_registry_sha256": identity.SEED_REGISTRY_SHA256,
               "alias_registry_ancestry": [dict(identity._REVIEWED_ALIAS_V3)],
               "learned_team_identities": [], "learned_competition_identities": [], "evidence_records": [],
               "authority": identity._state_authority()}
    document = {"payload": payload, "state_sha256": roles.sha(identity._canonical(payload))}
    (state / roles.STATE_FILENAME).write_bytes(identity._canonical(document) + b"\n")
    return history, state


def offline_parity() -> dict:
    # Retained fixed release bytes; gzip is transport/storage only, no newline repair.
    bootstrap = gzip.decompress(tracked(BOOTSTRAP_FIXTURE)[0])
    roles.require(roles.sha(bootstrap) == roles.BOOTSTRAP_SHA256, "retained PR119 fixture SHA differs")
    with tempfile.TemporaryDirectory(prefix="athena-c2-offline-") as directory:
        root = Path(directory)
        history, identity = synthetic_inputs(root)
        history_candidate = roles.Candidate(11, "a" * 40, roles.LEGACY_PRODUCERS["DURABLE_HISTORY_PRIME"]["workflow_path"],
                                            111, roles.LEGACY_PRODUCERS["DURABLE_HISTORY_PRIME"]["artifact_name"])
        identity_candidate = roles.Candidate(12, "a" * 40, roles.LEGACY_PRODUCERS["PERSISTENT_FIXTURE_IDENTITY_STATE"]["workflow_path"],
                                             112, roles.LEGACY_PRODUCERS["PERSISTENT_FIXTURE_IDENTITY_STATE"]["artifact_name"])
        archives = {111: zip_tree(history), 112: zip_tree(identity)}

        class FixtureTransport:
            bootstrap_origin = {"release_id": 373205103, "asset_id": 521090702,
                                "asset_size_bytes": 10545099}

            def artifact(self, candidate):
                return archives[candidate.artifact_id]

            def bootstrap(self):
                return bootstrap

        first = root / "legacy-produced"
        restored = restore_inputs(first, FixtureTransport(), current_run_id=100, canonical_candidates=[],
                                  legacy_candidates={"DURABLE_HISTORY_PRIME": [history_candidate],
                                                     "PERSISTENT_FIXTURE_IDENTITY_STATE": [identity_candidate]})
        artifact_root = first / "artifacts/athena-run-workflow"
        producer = {"workflow_family": "ATHENA_RUN", "workflow_path": roles.CANONICAL_WORKFLOW,
                    "run_id": 100, "head_sha": "b" * 40, "head_branch": "main",
                    "event_name": "workflow_dispatch", "request_sha256": "c" * 64}
        manifest = build_manifest(artifact_root, producer=producer,
                                  origins={key: row["origin_provenance"] for key, row in restored["roles"].items()},
                                  restore_eligible=True)
        (artifact_root / roles.MANIFEST_FILENAME).write_bytes(roles.canonical(manifest))
        canonical_candidate = roles.Candidate(100, "b" * 40, roles.CANONICAL_WORKFLOW, 200, "athena-run-100")
        archives[200] = zip_tree(first / "artifacts")
        second = root / "canonical-produced"
        again = restore_inputs(second, FixtureTransport(), current_run_id=101,
                               canonical_candidates=[canonical_candidate], legacy_candidates={})
        result = {}
        for role_id in roles.ROLE_IDS[:3]:
            left = roles.inventory(artifact_root / roles.ROLE_ROOTS[role_id])
            right = roles.inventory(second / "artifacts/athena-run-workflow" / roles.ROLE_ROOTS[role_id])
            roles.require(left == right and restored["roles"][role_id]["origin_provenance"] ==
                          again["roles"][role_id]["origin_provenance"], "restore parity/origin differs")
            result[role_id] = {"result": "PASS_EXACT_BYTES_AND_INVENTORY", "file_count": len(left),
                               "byte_count": sum(row["size_bytes"] for row in left),
                               "inventory_sha256": roles.sha(roles.canonical(left)),
                               "fixture_classification": "RETAINED_FIXED_RELEASE" if role_id == "PR119_BOOTSTRAP" else "SYNTHETIC_NO_LIVE_HISTORY_CLAIM"}
        return result


def expected_evidence():
    roles.require(roles.POLICY_ID == "ATHENA_CANONICAL_ARTIFACT_ROLES_V1" and
                  roles.MANIFEST_POLICY_ID == "ATHENA_CANONICAL_RUN_ARTIFACT_ROLE_MANIFEST_V1" and
                  roles.ROLE_IDS == ("DURABLE_HISTORY_PRIME", "PERSISTENT_FIXTURE_IDENTITY_STATE",
                                     "PR119_BOOTSTRAP", "RETAINED_SOURCE_EVIDENCE") and
                  roles.BOOTSTRAP_SHA256 == "e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2",
                  "exact canonical role policy drift")
    predecessor = roles.strict_json(tracked(PREDECESSOR_PATH)[0])
    roles.require(predecessor["canonical_sha256"] == PREDECESSOR_SHA == evolution.canonical_sha256(predecessor) and
                  len(predecessor["transitions"]) == 9 and
                  predecessor["transitions"][8]["transition_id"] == "PORT02C_NATIVE_RUNTIME_SLICE_ADD_V1",
                  "immutable nine-transition predecessor differs")
    before = tracked(BEFORE_FIXTURE)[0]
    after = tracked(roles.CANONICAL_WORKFLOW)[0]
    roles.require(evolution.source_identity(before) == BEFORE_IDENTITY, "before fixture differs")
    verify_workflow_authority(before, after)
    transition = {"transition_id": TRANSITION_ID, "phase_id": "CORE-01B", "operation": "MAINTENANCE_REVISE",
                  "workflow_path": roles.CANONICAL_WORKFLOW, "canonical_family": "ATHENA_RUN",
                  "before": BEFORE_IDENTITY, "after": evolution.source_identity(after),
                  "historical_before_fixture": {"path": BEFORE_FIXTURE, **BEFORE_IDENTITY},
                  "maintenance_contract": evolution.MAINTENANCE_CONTRACT,
                  "evidence_receipt_path": RECEIPT_PATH, "checkpoint_snapshot_path": SNAPSHOT_PATH}
    source_ids = {}
    for path in SOURCE_PATHS + HISTORICAL_PATHS:
        raw, identity = tracked(path)
        if path in HISTORICAL_BLOBS:
            roles.require(identity.git_blob_sha1 == HISTORICAL_BLOBS[path], f"historical source drift: {path}")
        source_ids[path] = {"git_blob_sha1": identity.git_blob_sha1,
                            "git_blob_payload_sha256": identity.git_blob_payload_sha256}
    c1 = roles.strict_json(tracked(HISTORICAL_PATHS[0])[0])
    receipt = {"schema_version": 1, "policy_id": POLICY_ID, "repository": roles.REPOSITORY,
               "base_main_sha": BASE_MAIN, "core_01a_reviewed_head": "8f58cec03a01530be45b8f8c362d8b81de58657a",
               "core_01a_merge_commit": BASE_MAIN, "core_01a_canonical_sha256": c1["canonical_sha256"],
               "postmerge_tests": {"run_id": 36806839224, "head_sha": BASE_MAIN, "result": "SUCCESS_SYNTAX_SHARDS_1_8_AGGREGATE"},
               "postmerge_fixture_catalog": {"run_id": 36806839302, "head_sha": BASE_MAIN, "result": "SUCCESS"},
               "governance": {"source_review_counter_while_open": "2/5", "source_review_counter_if_merged": "3/5",
                   "mandatory_reread_due": False, "p4_4": "INCOMPLETE", "checkpoint_e": "INCOMPLETE",
                   "clean_successor_proof": "INCOMPLETE_NOT_RERUN", "lg_a": "NOT_RUN_NOT_AUTHORIZED",
                   "caller_schedule_migration_workflow_retirement": "NOT_AUTHORIZED"},
               "role_policy": roles.POLICY_ID, "manifest_policy": roles.MANIFEST_POLICY_ID,
               "role_ids": list(roles.ROLE_IDS), "legacy_compatibility_map": roles.LEGACY_PRODUCERS,
               "resolution": "NEWEST_VERIFIED_TRUSTED_MAIN_CANONICAL_ROLE_THEN_LEGACY_READ_ONLY_COMPATIBILITY",
               "trust": ["Thabearr/ATHENA", "SUCCESS", "main", "VALID_HEAD_SHA", "NOT_SELF",
                         "ARTIFACT_BELONGS_TO_RUN", "MANIFEST_RUN_HEAD_MATCH", "RESTORE_ELIGIBLE_TRUE", "EXACT_ROLE_INVENTORY"],
               "role_behavior": {"DURABLE_HISTORY_PRIME": "OPTIONAL_KEEP_LIVE_TRANSPORT_FALLBACK_NO_FAKE_PRIME",
                   "PERSISTENT_FIXTURE_IDENTITY_STATE": "OPTIONAL_EMPTY_WORKER_LOCAL_STATE_NO_FABRICATION",
                   "PR119_BOOTSTRAP": "REQUIRED_EXACT_SHA_BEFORE_PROVIDER", "RETAINED_SOURCE_EVIDENCE": "PUBLICATION_ONLY"},
               "offline_parity": offline_parity(), "source_identities": source_ids,
               "workflow_before_identity": BEFORE_IDENTITY, "workflow_after_identity": evolution.source_identity(after),
               "reviewed_workflow_transition": transition, "workflow_evolution_checkpoint_path": SNAPSHOT_PATH,
               "predecessor_checkpoint_sha256": PREDECESSOR_SHA, "predecessor_transition_count": 9,
               "transition_position": 10, "current_live_workflow_count": 39, "current_p4_3_retired_workflow_count": 3,
               "workflow_authority_delta": 0, "historical_receipts_changed": False,
               "closed_blocker": "PERSISTENT_IDENTITY_ANCESTRY_CANONICAL_RUN_ONLY",
               "remaining_blockers": ["SCHEDULED_SHADOW_OWNERSHIP", "NOTIFICATION_EMAIL",
                                      "ISSUE_COMMENT_COMPATIBILITY", "LIVE_CANONICAL_SHADOW_PROOF"],
               "safety_counts": dict.fromkeys(("provider", "share_code", "delivery", "email", "live_dispatch",
                                               "login", "cookies", "wallet", "stake", "wager"), 0)}
    transition["evidence_body_sha256"] = evolution.receipt_evidence_body_sha256(receipt)
    # The receipt's intent deliberately excludes the evidence-body hash.
    receipt["reviewed_workflow_transition"] = {k: v for k, v in transition.items() if k != "evidence_body_sha256"}
    ledger = copy.deepcopy(predecessor)
    ledger["transitions"].append(transition)
    ledger["current_workflow_tree_sha1"] = evolution.CORE01B_WORKFLOW_TREE_SHA1
    ledger["canonical_sha256"] = evolution.canonical_sha256(ledger)
    receipt["workflow_evolution_ledger_sha256"] = ledger["canonical_sha256"]
    receipt["canonical_sha256"] = evolution.canonical_sha256(receipt)
    return receipt, ledger


def audit() -> dict:
    expected, checkpoint = expected_evidence()
    actual = roles.strict_json(tracked(RECEIPT_PATH)[0])
    roles.require(roles.canonical(actual) == roles.canonical(expected), "C2 receipt differs from rederived evidence")
    ledger = evolution.validate_current_state()
    snapshot = roles.strict_json(tracked(SNAPSHOT_PATH)[0])
    roles.require(snapshot == checkpoint and len(snapshot["transitions"]) == 10, "C2 ten-transition snapshot differs")
    predecessor = roles.strict_json(tracked(PREDECESSOR_PATH)[0])
    evolution.validate_evolution_snapshot_extension(predecessor, ledger)
    evolution.validate_evolution_snapshot_extension(snapshot, ledger)
    return {"result": "PASS", "policy_id": POLICY_ID, "canonical_sha256": actual["canonical_sha256"],
            "snapshot_sha256": snapshot["canonical_sha256"], "transition_count": 10,
            "live_count": 39, "retired_count": 3, "provider_live_actions": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        receipt, ledger = expected_evidence()
        for path, value in ((RECEIPT_PATH, receipt), (SNAPSHOT_PATH, ledger), (str(evolution.LEDGER_PATH), ledger)):
            (ROOT / path).write_bytes(roles.canonical(value))
        print(json.dumps({"receipt_sha": receipt["canonical_sha256"], "ledger_sha": ledger["canonical_sha256"]}))
    else:
        print(json.dumps(audit(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
