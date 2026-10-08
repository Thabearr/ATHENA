"""Deterministic D4 source receipt; not hosted-CI or independent-review proof."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = "artifacts/product/data_01b_durable_run_state_v1.json"
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
    "tests/test_core_01d_ci_offline_transport_inventory_evolution.py",
    "tests/test_core_01d_port02c_trigger_authority_b6.py",
    "tests/test_core_01d_frozen_artifact_replay_authority_b5.py",
    "tests/test_core_01d_owner_one_shot_issue_comment_authority_b3.py",
    "scripts/audit_data_01b_durable_run_state.py",
)
TABLES = {"app_runs", "app_run_attempts", "app_run_events",
          "app_external_operations", "app_run_artifacts"}
NEW_PATHS = {
    "database/run_repository.py", "database/migrations/0002_app_runs_operations.sql",
    "tests/test_data_01b_durable_run_state.py", "docs/product/data_01b_run_storage.md",
    "scripts/audit_data_01b_durable_run_state.py", RECEIPT,
    "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v69.json",
    "tests/native/test_data_01b_bundle_migrations.py",
}


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def tracked_bytes(path):
    return subprocess.run(["git", "show", "HEAD:" + path], cwd=ROOT,
                          check=True, capture_output=True).stdout


def build_receipt():
    first = tracked_bytes("database/migrations/0001_app_control_core.sql")
    if hashlib.sha256(first).hexdigest() != FROZEN_MIGRATION_SHA:
        raise AssertionError("frozen migration 0001 changed")
    second = (ROOT / "database/migrations/0002_app_runs_operations.sql").read_bytes().replace(b"\r\n", b"\n")
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
    value = {
        "schema_version": 1, "policy_id": "ATHENA_DATA_01B_DURABLE_RUN_STATE_V1",
        "base_main_sha": "7e609e3d2006d2a72d9bf347cb917c0585538322",
        "base_tree_sha": "d002d7b616da89829a2382a94516ddaf32a5412f",
        "post_d3_main_tests_run": 37708586802,
        "d3_receipt_sha256": "3f1b04be1d97391b87e958eb008910b822567673582b61947f00099b9aa71c59",
        "migration_0001_raw_sha256": FROZEN_MIGRATION_SHA,
        "migration_0002_lf_sha256": hashlib.sha256(second).hexdigest(),
        "a2_predecessor": {"generation": 68, "rewritten": False,
                           "canonical_sha256": "38766b0fd2e2627bc05bd687ba404ddb2b6b186c034294ed4183150d52ec52dd"},
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
    raw = canonical(build_receipt())
    path = ROOT / RECEIPT
    if args.write:
        path.write_bytes(raw)
    elif path.read_bytes() != raw:
        raise AssertionError("D4 source receipt drift")
    print("DATA_01B_SOURCE_RECEIPT_OK")


def authenticate_successor(latest):
    raw = (ROOT / RECEIPT).read_bytes()
    value = build_receipt()
    if raw != canonical(value) or latest["generation"] < 69:
        raise AssertionError("D4 successor source receipt mismatch")
    inventory = {row["path"]: row["lf_source_sha256"] for row in latest["source_identities"]}
    for row in value["source_identities"]:
        if row["path"].endswith(".py") and inventory.get(row["path"]) != row["lf_sha256"]:
            raise AssertionError("D4 successor inventory binding mismatch: " + row["path"])
    return value


if __name__ == "__main__":
    main()
