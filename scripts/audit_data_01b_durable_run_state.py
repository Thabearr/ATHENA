"""Deterministic D4 source receipt; not hosted-CI or independent-review proof."""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = "artifacts/product/data_01b_durable_run_state_v1.json"
SNAPSHOT = "tests/fixtures/core_01d/data_01b_historical/d3_source_bytes.json"
D3_EXTENSION = "tests/fixtures/core_01d/data_01c_historical/d3_app_repository_source_v1.json"
REVIEWED_HEAD = "e5b9793d1c609ad331819c228484e5c088e686d9"
REVIEWED_A2_SHA = "009185f7e2743b29bd5fa4f7c71815c54ccf1158e759a10aa0c68fdb263d910a"
V70_A2_SHA256 = "bc12c07f2d840be6abf77f2ec2bea1ffca8b34256b5c293db67dfbbf5b3909a5"
V71_A2_SHA256 = "0aaf97fca9ee2870910c63dc9d7aacef2b6caf56a5fb02293b900142d8c6bc11"
V72_A2_SHA256 = "9b74eccdb1868ed5ad1b71b6f3bdb99d49a6f42a2892656067bc0a885ab2e7ca"
V73_A2_SHA256 = "dfd1127f090745f40667d3cab52cc40e5df90f48c747be7691233feb80f86b98"
FROZEN_SECOND_MIGRATION_SHA = "3c0098dcd77e32a9e115dfcd40bd019901309894bb780ad66e90ed3846b60e97"
FROZEN_RECEIPT_SHA256 = "d0b27962d852c9352306106b78ef26e00b919fc5a3a4070302c05ec667698b84"
WORKFLOW_TREE_PIN = "9b08653f1a12bb1b3d964fbd910396ff955740da"
FROZEN_MIGRATION_SHA = "6d380b30733f99d3740b8d6dd89810fb31ca568625319b433023f48c9f667b7c"
SOURCES = (
    "database/app_migrations.py", "database/run_repository.py",
    "database/migrations/0002_app_runs_operations.sql",
    "scripts/port_02c_build_config.py", "tests/test_data_01a_app_schema.py",
    "tests/test_data_01b_durable_run_state.py", "docs/product/data_01b_run_storage.md",
    "tests/test_app_01a_local_shell.py",
    "tests/native/test_data_01b_bundle_migrations.py",
    "scripts/audit_data_01a_app_schema_core.py",
    "scripts/audit_app_01a_local_shell.py",
    "scripts/audit_core_01d_checkpoint_e_completion.py",
    "scripts/audit_checkpoint_e_workflows.py",
    "tests/test_core_01d_exact_pr_trigger_disposition_b1.py",
    "tests/test_core_01d_ci_offline_transport_inventory_evolution.py",
    "tests/test_core_01d_port02c_trigger_authority_b6.py",
    "tests/test_core_01d_frozen_artifact_replay_authority_b5.py",
    "tests/test_core_01d_owner_one_shot_issue_comment_authority_b3.py",
    "scripts/audit_data_01b_durable_run_state.py",
    SNAPSHOT,
)
TABLES = {"app_runs", "app_run_attempts", "app_run_events",
          "app_external_operations", "app_run_artifacts"}
NEW_PATHS = {
    "database/run_repository.py", "database/migrations/0002_app_runs_operations.sql",
    "tests/test_data_01b_durable_run_state.py", "docs/product/data_01b_run_storage.md",
    "scripts/audit_data_01b_durable_run_state.py", RECEIPT,
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v69.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v70.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v71.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v72.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v73.json",
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v74.json",
    "tests/native/test_data_01b_bundle_migrations.py",
    SNAPSHOT,
}


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def tracked_bytes(path):
    return subprocess.run(["git", "show", "HEAD:" + path], cwd=ROOT,
                          check=True, capture_output=True).stdout


def historical_sources():
    d3_raw = (ROOT / "artifacts/product/data_01a_app_schema_core_v1.json").read_bytes()
    d3 = json.loads(d3_raw)
    unsealed = {key: value for key, value in d3.items() if key != "canonical_sha256"}
    expected = "3f1b04be1d97391b87e958eb008910b822567673582b61947f00099b9aa71c59"
    if (d3["canonical_sha256"] != expected or hashlib.sha256(canonical(unsealed)).hexdigest() != expected
            or canonical(d3) != d3_raw):
        raise AssertionError("immutable D3 source receipt drift")
    raw = (ROOT / SNAPSHOT).read_bytes()
    snapshot = json.loads(raw)
    if (raw != canonical(snapshot) or set(snapshot) != {"base_main_sha", "source_bytes"}
            or snapshot["base_main_sha"] != "7e609e3d2006d2a72d9bf347cb917c0585538322"):
        raise AssertionError("D3 retained source snapshot identity drift")
    paths = set(SOURCES) & set(d3["source_identities"])
    if set(snapshot["source_bytes"]) != paths:
        raise AssertionError("D3 retained source snapshot scope drift")
    result = {}
    for path, encoded in snapshot["source_bytes"].items():
        payload = base64.b64decode(encoded, validate=True)
        if hashlib.sha256(payload.replace(b"\r\n", b"\n")).hexdigest() != d3["source_identities"][path]:
            raise AssertionError("D3 retained source bytes drift: " + path)
        result[path] = payload
    # The frozen D4 snapshot intentionally contains only D4 source paths that
    # overlapped D3. D5 also evolves app_repository.py, so retain that one
    # missing D3 byte identity in a separate additive record rather than
    # rewriting either historical receipt or snapshot.
    extension_raw = (ROOT / D3_EXTENSION).read_bytes()
    extension = json.loads(extension_raw)
    if (extension_raw != canonical(extension)
            or type(extension) is not dict
            or set(extension) != {"schema_version", "policy_id", "d3_receipt_sha256",
                                  "source_commit", "a2_inventory", "source_bytes",
                                  "canonical_sha256"}
            or extension.get("schema_version") != 1
            or extension.get("policy_id") != "ATHENA_DATA_01C_D3_HISTORICAL_SOURCE_EXTENSION_V1"
            or extension.get("d3_receipt_sha256") != expected
            or extension.get("source_commit") != snapshot["base_main_sha"]):
        raise AssertionError("D5 additive D3 historical source extension identity drift")
    extension_seal = dict(extension)
    seal = extension_seal.pop("canonical_sha256")
    if hashlib.sha256(canonical(extension_seal)).hexdigest() != seal:
        raise AssertionError("D5 additive D3 historical source extension seal mismatch")
    from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
    inventory = boundary.read_generation(d3["a2_inventory"]["path"])
    if (extension["a2_inventory"] != d3["a2_inventory"]
            or inventory.get("generation") != 68
            or inventory.get("canonical_sha256") != d3["a2_inventory"]["canonical_sha256"]):
        raise AssertionError("D5 additive D3 source extension A2 V68 binding drift")
    added = extension["source_bytes"]
    if type(added) is not list or len(added) != 1 or added[0].get("path") != "database/app_repository.py":
        raise AssertionError("D5 additive D3 source extension scope drift")
    row = added[0]
    payload = base64.b64decode(row["base64"], validate=True)
    source_identity = d3["source_identities"].get(row["path"])
    v68_identity = {item["path"]: item["lf_source_sha256"]
                    for item in inventory["source_identities"]}.get(row["path"])
    if (type(row.get("byte_count")) is not int or row["byte_count"] != len(payload)
            or row.get("byte_sha256") != hashlib.sha256(payload).hexdigest()
            or row.get("git_blob_sha1") != hashlib.sha1(
                b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()
            or hashlib.sha256(payload.replace(b"\r\n", b"\n")).hexdigest() != source_identity
            or source_identity != v68_identity):
        raise AssertionError("D5 additive D3 historical source bytes fail D3/A2 authentication")
    result[row["path"]] = payload
    return result


def build_receipt():
    historical_sources()
    first = tracked_bytes("database/migrations/0001_app_control_core.sql")
    if hashlib.sha256(first).hexdigest() != FROZEN_MIGRATION_SHA:
        raise AssertionError("frozen migration 0001 changed")
    second = (ROOT / "database/migrations/0002_app_runs_operations.sql").read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(second).hexdigest() != FROZEN_SECOND_MIGRATION_SHA:
        raise AssertionError("reviewed migration 0002 changed")
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(first.decode("utf-8"))
        v1 = {row[0] for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        conn.executescript(second.decode("utf-8"))
        v2 = {row[0] for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        if len(v1) != 9 or len(v2) != 14 or v2 - v1 != TABLES:
            raise AssertionError("D4 exact additive table boundary changed")
        for table in TABLES:
            if any(row[6] != "RESTRICT" for row in conn.execute("PRAGMA foreign_key_list(" + table + ")")):
                raise AssertionError("retained evidence delete policy changed")
    finally:
        conn.close()
    api = (ROOT / "api/v1/run_previews.py").read_text(encoding="utf-8")
    service = (ROOT / "services/athena_preview_service.py").read_text(encoding="utf-8")
    for path in ("api/v1/run_previews.py", "api/v1/runs.py", "run_desktop.py", "services/athena_preview_service.py"):
        if (ROOT / path).read_bytes().replace(b"\r\n", b"\n") != tracked_bytes(path).replace(b"\r\n", b"\n"):
            raise AssertionError("out-of-scope admission wiring changed: " + path)
    if "DURABLE_RUN_STORE_UNAVAILABLE" not in api or "UnavailableAdmissionRepository() if admission_repository is None" not in service:
        raise AssertionError("production unavailable admission boundary changed")
    from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
    predecessor = boundary.read_generation(boundary.inventory_generation_path(73))
    inventory = boundary.read_generation(boundary.inventory_generation_path(74))
    if (predecessor["canonical_sha256"] != V73_A2_SHA256
            or inventory["predecessor_inventory"] != {
                "path": boundary.inventory_generation_path(73), "canonical_sha256": V73_A2_SHA256,
                "generation": 73, "rewritten": False}):
        raise AssertionError("review successor A2 ancestry drift")
    regressions = {
        "confirmed_response": "test_confirmed_requires_retained_response_without_mutation",
        "cancel_send_race": "test_cancel_send_race_independent_connections_serializes_winner",
        "historical_release": "test_historical_release_a_read_replay_under_b_but_no_current_mutation",
        "receipt_producer": "test_unverified_receipt_producer_rejected_before_publication",
        "blocked_admission": "test_genuinely_blocked_snapshot_cannot_admit",
        "terminal_receipt_positive": "test_terminal_receipt_positive_proof_exact_replay_and_repeat_projection",
        "terminal_missing_receipt": "test_terminal_read_fails_closed_when_retained_receipt_missing",
        "terminal_corrupt_artifact": "test_terminal_read_rejects_corrupt_or_mismatched_artifact_evidence",
        "terminal_projection_tamper": "test_terminal_read_rejects_projection_metadata_and_event_tampering",
        "terminal_nonterminal_pointer": "test_nonterminal_run_cannot_silently_carry_projected_receipt_pointer",
        "terminal_crash_gap_reconcile": "test_receipt_first_projection_gap_stays_nonterminal_until_explicit_reconcile",
        "terminal_historical_source_switch": "test_historical_terminal_read_survives_source_switch_without_producer_fabrication",
        "terminal_nonterminal_resurrection": "test_nonterminal_resurrection_with_residual_terminal_evidence_fails_closed",
        "terminal_forged_event": "test_nonterminal_run_with_forged_terminal_event_and_no_pointer_fails_closed",
        "terminal_duplicate_receipt_role": "test_terminal_read_rejects_duplicate_or_cross_run_receipt_role_linkage",
        "terminal_honest_nonterminal_states": "test_honest_nonterminal_states_remain_readable_without_terminal_evidence",
    }
    definitions = {node.name for node in ast.walk(ast.parse(
        (ROOT / "tests/test_data_01b_durable_run_state.py").read_text(encoding="utf-8")))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if not set(regressions.values()) <= definitions:
        raise AssertionError("independent-review adversarial regressions missing")
    try:
        changed = subprocess.run(["git", "diff", "--name-only", "7e609e3d2006d2a72d9bf347cb917c0585538322"],
                                 cwd=ROOT, check=True, capture_output=True).stdout.decode().splitlines()
    except subprocess.CalledProcessError:
        changed = None
    if changed is None:
        tree = subprocess.run(["git", "rev-parse", "HEAD:.github/workflows"], cwd=ROOT, check=True,
                              capture_output=True).stdout.decode().strip()
        if tree != WORKFLOW_TREE_PIN:
            raise AssertionError("prohibited workflow delta without base evidence")
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--",
                                 ".github/workflows", "database"], cwd=ROOT, check=True,
                                capture_output=True).stdout.decode().splitlines()
        changed = [line[3:] for line in status if len(line) > 3]
    if any(path.startswith(".github/workflows/") or path in {
            "database/athena.db", "database/athena_history.db"} for path in changed):
        raise AssertionError("prohibited workflow or legacy database delta")
    value = {
        "schema_version": 1, "policy_id": "ATHENA_DATA_01B_DURABLE_RUN_STATE_V1",
        "base_main_sha": "7e609e3d2006d2a72d9bf347cb917c0585538322",
        "base_tree_sha": "d002d7b616da89829a2382a94516ddaf32a5412f",
        "post_d3_main_tests_run": 37708586802,
        "d3_receipt_sha256": "3f1b04be1d97391b87e958eb008910b822567673582b61947f00099b9aa71c59",
        "migration_0001_raw_sha256": FROZEN_MIGRATION_SHA,
        "migration_0002_lf_sha256": hashlib.sha256(second).hexdigest(),
        "reviewed_blocked_head": REVIEWED_HEAD,
        "reviewed_blocked_receipt_sha256": "41891924ca3b7ca207fe5ba26e6ea1440b7f5937e4ea6e9aef07a92974545388",
        "open_future_dependencies": [{"id": "E2/PACKAGING_AUTHENTICATED_INSTALLED_PRODUCER_PROVENANCE", "status": "OPEN"}],
        "a2_inventory": {"generation": 74, "path": boundary.inventory_generation_path(74),
                         "canonical_sha256": inventory["canonical_sha256"]},
        "a2_predecessor": {"generation": 73, "rewritten": False, "canonical_sha256": V73_A2_SHA256},
        "proof_semantics": {
            "confirmed_requires_retained_same_run_response": True,
            "new_send_requires_running_inside_writer_transaction": True,
            "historical_provenance_separate_from_current_mutation_authority": True,
            "terminal_requires_verified_git_producer_and_run_bindings": True,
            "installed_commit_lineage_not_fabricated": True,
            "admission_reauthenticates_capability_and_current_authority": True,
            "terminal_reads_authenticate_retained_receipt_linkage_bytes_and_projection": True,
            "terminal_reads_fail_closed_typed_without_current_release_eligibility": True,
            "bidirectional_terminal_nonterminal_integrity_fail_closed": True,
            "nonterminal_resurrection_never_regains_authenticated_reads_or_mutation_authority": True,
            "receipt_role_linkage_unique_per_run_rejects_residual_and_forged_terminal_evidence": True,
            "adversarial_regressions": regressions,
        },
        "workflow_yaml_delta": 0, "legacy_database_delta": 0,
        "prohibited_runtime_actions": dict.fromkeys(("provider", "live", "share_code", "login",
            "cookie", "wallet", "stake", "wager", "worker", "manual_workflow"), 0),
        "app_table_count": 14, "added_tables": sorted(TABLES),
        "production_admission": "UNAVAILABLE_503", "production_operations_enabled": False,
        "executor_authority": False, "merge_authorized": False,
        "hosted_ci_and_independent_review": "SEPARATE_REQUIRED_GATES",
        "source_identities": [{"path": path, "lf_sha256": hashlib.sha256(
            (ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()} for path in SOURCES],
    }
    value["canonical_sha256"] = hashlib.sha256(canonical(value)).hexdigest()
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    latest = None
    if not args.write:
        from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
        latest = boundary.authenticate_inventory()
    if latest is not None and latest["generation"] >= 75:
        authenticate_successor(latest)
        print("DATA_01B_SOURCE_RECEIPT_HISTORICAL_SUCCESSOR_OK")
        return
    raw = canonical(build_receipt())
    path = ROOT / RECEIPT
    if args.write:
        path.write_bytes(raw)
    elif path.read_bytes() != raw:
        raise AssertionError("D4 source receipt drift")
    print("DATA_01B_SOURCE_RECEIPT_OK")


def authenticate_successor(latest):
    raw = (ROOT / RECEIPT).read_bytes()
    value = json.loads(raw)
    if (type(value) is not dict or raw != canonical(value)
            or value.get("canonical_sha256") != FROZEN_RECEIPT_SHA256
            or hashlib.sha256(canonical({key: row for key, row in value.items()
                                         if key != "canonical_sha256"})).hexdigest() != FROZEN_RECEIPT_SHA256
            or latest["generation"] < 75):
        raise AssertionError("D4 successor source receipt mismatch")
    if value.get("policy_id") != "ATHENA_DATA_01B_DURABLE_RUN_STATE_V1":
        raise AssertionError("D4 immutable receipt policy drift")
    latest_inventory = {row["path"]: row["lf_source_sha256"] for row in latest["source_identities"]}
    from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
    v74 = boundary.read_generation(boundary.inventory_generation_path(74))
    v75 = boundary.read_generation(boundary.inventory_generation_path(75))
    if (v74.get("generation") != 74
            or v74.get("canonical_sha256") != "8069d2ab272806ce803ed8b955c2227a136d65219408fc7bf87ba050f9f6523b"
            or v75.get("canonical_sha256") != "a4702d82a771bef07858f9399b9ab3821800cc98226df5795551155ca74634a4"
            or v75.get("predecessor_inventory") != {
                "path": boundary.inventory_generation_path(74),
                "canonical_sha256": v74["canonical_sha256"],
                "generation": 74, "rewritten": False}):
        raise AssertionError("D4 source receipt does not retain immutable A2 V74 -> V75 lineage")
    v74_inventory = {row["path"]: row["lf_source_sha256"] for row in v74["source_identities"]}
    frozen_sources = {row["path"]: row["lf_sha256"] for row in value["source_identities"]}
    if (set(frozen_sources) != set(SOURCES)
            or any(v74_inventory.get(path) != digest for path, digest in frozen_sources.items()
                   if path.endswith(".py"))):
        raise AssertionError("D4 frozen source identities differ from authenticated A2 V74")
    current = {path: hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
               for path in SOURCES}
    for path, digest in current.items():
        if path.endswith(".py"):
            if latest_inventory.get(path) != digest:
                raise AssertionError("current successor source is not bound by latest A2 inventory: " + path)
        elif frozen_sources.get(path) != digest:
            raise AssertionError("non-Python D4 source changed outside its immutable receipt: " + path)
    rebuilt = build_receipt()
    for key in set(value) - {"source_identities", "canonical_sha256"}:
        if rebuilt.get(key) != value.get(key):
            raise AssertionError("D4 immutable semantics changed in successor view: " + key)
    return value


if __name__ == "__main__":
    main()
