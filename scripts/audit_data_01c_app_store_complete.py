"""Bounded D5 source receipt audit; it grants no runtime or merge authority."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

from database.app_migrations import expected_app_tables, schema_structure
from domain.run_contracts import canonical_json_bytes
from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_data_01a_app_schema_core as data01a
from scripts import audit_data_01b_durable_run_state as data01b


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = "artifacts/product/data_01c_app_store_complete_v1.json"
V74_SHA256 = "8069d2ab272806ce803ed8b955c2227a136d65219408fc7bf87ba050f9f6523b"
D3_SHA256 = "3f1b04be1d97391b87e958eb008910b822567673582b61947f00099b9aa71c59"
D4_SHA256 = "d0b27962d852c9352306106b78ef26e00b919fc5a3a4070302c05ec667698b84"
MIGRATION_0001_SHA256 = "6d380b30733f99d3740b8d6dd89810fb31ca568625319b433023f48c9f667b7c"
MIGRATION_0002_LF_SHA256 = "3c0098dcd77e32a9e115dfcd40bd019901309894bb780ad66e90ed3846b60e97"
EXPECTED_D5_TABLES = {
    "app_fixture_projections", "app_opportunity_projections", "app_portfolio_members",
    "app_exports", "app_backups", "app_audit_events",
}
SOURCE_PATHS = (
    "database/migrations/0003_app_projections_exports.sql",
    "database/app_migrations.py", "database/app_root_lock.py",
    "database/app_storage_access.py", "database/app_repository.py",
    "database/run_repository.py", "services/app_projection_service.py",
    "services/export_service.py", "services/backup_service.py",
    "scripts/port_02c_build_config.py", "scripts/audit_data_01a_app_schema_core.py",
    "scripts/audit_data_01b_durable_run_state.py",
    "tests/test_data_01a_app_schema.py", "tests/test_data_01b_durable_run_state.py",
    "tests/native/test_data_01b_bundle_migrations.py",
    "tests/test_core_01d_ci_offline_transport_inventory_evolution.py",
    "tests/test_data_01c_app_storage.py", "tests/native/test_data_01c_bundle_migrations.py",
    "docs/product/data_01c_app_store_complete.md",
)


def canonical(value):
    return canonical_json_bytes(value)


def source_identities():
    rows = []
    for path in SOURCE_PATHS:
        raw = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
        rows.append({"path": path, "lf_sha256": hashlib.sha256(raw).hexdigest()})
    return rows


def _schema_evidence():
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        for path in (
            "database/migrations/0001_app_control_core.sql",
            "database/migrations/0002_app_runs_operations.sql",
            "database/migrations/0003_app_projections_exports.sql",
        ):
            conn.executescript((ROOT / path).read_text(encoding="utf-8"))
        names = sorted(expected_app_tables(3))
        if len(names) != 20 or not EXPECTED_D5_TABLES <= set(names):
            raise AssertionError("D5 schema is not the exact six-table / 20-table boundary")
        structure = schema_structure(conn)
        return {"app_table_count": len(names), "app_tables": names,
                "d5_added_tables": sorted(EXPECTED_D5_TABLES),
                "schema_structure_sha256": hashlib.sha256(canonical(structure)).hexdigest()}
    finally:
        conn.close()


def build_receipt():
    latest = boundary.authenticate_inventory()
    if latest.get("generation") != 75:
        raise AssertionError("D5 receipt requires canonical A2 V75 as latest")
    predecessor = latest.get("predecessor_inventory")
    if predecessor != {"path": boundary.inventory_generation_path(74),
                       "canonical_sha256": V74_SHA256, "generation": 74,
                       "rewritten": False}:
        raise AssertionError("A2 V75 predecessor is not exact immutable V74")
    data01b.authenticate_successor(latest)
    d3 = data01a.authenticate()
    if d3["canonical_sha256"] != D3_SHA256:
        raise AssertionError("D3 source receipt identity drift")
    d4 = json.loads((ROOT / data01b.RECEIPT).read_bytes())
    if d4.get("canonical_sha256") != D4_SHA256:
        raise AssertionError("D4 source receipt identity drift")
    migration1 = (ROOT / "database/migrations/0001_app_control_core.sql").read_bytes()
    migration2 = (ROOT / "database/migrations/0002_app_runs_operations.sql").read_bytes().replace(b"\r\n", b"\n")
    migration3 = (ROOT / "database/migrations/0003_app_projections_exports.sql").read_bytes()
    if (hashlib.sha256(migration1).hexdigest() != MIGRATION_0001_SHA256
            or hashlib.sha256(migration2).hexdigest() != MIGRATION_0002_LF_SHA256):
        raise AssertionError("frozen D3/D4 migration bytes changed")
    if [version for version, _ in __import__("database.app_migrations", fromlist=["APP_MIGRATIONS"]).APP_MIGRATIONS] != [1, 2, 3]:
        raise AssertionError("app migration registry is not explicit contiguous [1,2,3]")
    if ".github/workflows" in "\n".join(boundary.git("diff", "--name-only", "origin/main").decode().splitlines()):
        raise AssertionError("workflow YAML changed in D5 scope")
    schema = _schema_evidence()
    value = {
        "schema_version": 1,
        "policy_id": "ATHENA_DATA_01C_STORAGE_READY_PROJECTIONS_SOURCE_BLOCKED_V1",
        "repository": "Thabearr/ATHENA",
        "master_issue": 337,
        "base_main_sha": "57e632f1e150cd1429ce00005a3cdf9ef3673ff2",
        "source_review_counter": "2/5",
        "migration_registry": [
            {"version": version, "path": path, "sha256": digest}
            for version, path, _raw, digest in __import__(
                "database.app_migrations", fromlist=["read_app_migrations", "APP_MIGRATIONS"]
            ).read_app_migrations(boundary_resource_resolver())
        ],
        "frozen_migrations": {"0001_raw_sha256": MIGRATION_0001_SHA256,
                              "0002_lf_sha256": MIGRATION_0002_LF_SHA256},
        "migration_0003_raw_sha256": hashlib.sha256(migration3).hexdigest(),
        "schema": schema,
        "projection_source": {
            "resolver": "services/app_projection_service.py",
            "typed_disposition": "SOURCE_CONTRACT_UNAVAILABLE",
            "coverage_disposition": "COVERAGE_UNAVAILABLE",
            "materialized_verified_rows": 0,
            "source_contract": "E2/VERIFIED_DECISION_PROJECTION_SOURCE_CONTRACT:OPEN",
            "selected_legs_authority": "OPAQUE_GENERIC_RUN_RECEIPT_MAPPINGS_ONLY",
        },
        "implemented_facilities": {
            "offline_export": "HASH_VERIFIED_REDACTED_LOCAL_ONLY",
            "audit_events": "CANONICAL_REDACTED_APPEND_ONLY_SHA256",
            "backup": "SQLITE_ONLINE_SNAPSHOT_CROSS_PROCESS_ROOT_LOCK_RETAINED_BLOB_MANIFEST",
            "restore": "BOUNDED_STREAMING_STAGE_SAME_VOLUME_JOURNAL_ROLLBACK",
            "backup_index_snapshot_state": "PREPARING_UNTIL_LIVE_ARCHIVE_VERIFICATION_COMMITS",
            "installed_producer_provenance": "E2/PACKAGING_AUTHENTICATED_INSTALLED_PRODUCER_PROVENANCE:OPEN",
        },
        "a2_inventory": {"generation": 75, "path": boundary.inventory_generation_path(75),
                         "canonical_sha256": latest["canonical_sha256"]},
        "a2_predecessor": predecessor,
        "historical_receipts": {"d3_canonical_sha256": D3_SHA256,
                                "d4_canonical_sha256": D4_SHA256,
                                "source_authentication": "IMMUTABLE_HISTORICAL_BYTES_AND_A2_SUCCESSOR_BINDING"},
        "production_admission": "UNAVAILABLE_503",
        "execution_or_live_authority": False,
        "no_live_side_effects": True,
        "prohibited_action_counts": dict.fromkeys((
            "provider", "live", "share_code", "login", "cookie", "wallet", "staking",
            "wager", "worker", "manual_workflow", "router", "portfolio", "delivery",
        ), 0),
        "workflow_yaml_delta": 0,
        "legacy_database_delta": 0,
        "merge_authorized": False,
        "independent_review": "PENDING",
        "hosted_ci": "NATURAL_EXACT_FINAL_HEAD_TESTS_AND_WINDOWS_LINUX_PORT_02C_REQUIRED",
        "source_identities": source_identities(),
    }
    value["canonical_sha256"] = hashlib.sha256(canonical(value)).hexdigest()
    return value


def boundary_resource_resolver():
    from runtime.release_identity import verify_development_checkout
    from runtime.resources import ResourceResolver

    identity = verify_development_checkout(ROOT)
    return ResourceResolver.for_development(identity)


def audit():
    expected = canonical(build_receipt())
    raw = (ROOT / RECEIPT).read_bytes()
    if raw != expected:
        raise AssertionError("D5 source receipt does not match exact current sources")
    value = json.loads(raw)
    if value.get("canonical_sha256") != hashlib.sha256(
            canonical({key: row for key, row in value.items() if key != "canonical_sha256"})).hexdigest():
        raise AssertionError("D5 source receipt seal mismatch")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    value = build_receipt()
    raw = canonical(value)
    target = ROOT / RECEIPT
    if args.write:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    elif target.read_bytes() != raw:
        raise AssertionError("D5 source receipt drift")
    print("DATA_01C_SOURCE_RECEIPT_OK")


if __name__ == "__main__":
    main()
