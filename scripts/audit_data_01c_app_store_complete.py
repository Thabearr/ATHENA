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
V75_SHA256 = "a4702d82a771bef07858f9399b9ab3821800cc98226df5795551155ca74634a4"
V76_SHA256 = "9e003cf42e26c41b3dd83b6ccc77750c94513edd81700d2661757ab81d61c841"
V77_SHA256 = "52bbbf3a6158b17e90ad220347e4a579530f3777694a8495432ac954592d5993"
V78_SHA256 = "6c1beaa0929157e1a10e0cf129c77e9c1373a14b6fdc9089e203e4cd4c9928b2"
V79_SHA256 = "00edfdb3273b78228e868947d705b74486db55ea1406cb9baed6e2cf267a2937"
V80_SHA256 = "ec4ddf9ccc080123daa1ad761b121d60beb319cca238617dcd3fe8f8257e0015"
V81_SHA256 = "238c1874e90e24ce3a7229d17ed2b50083f148296976dcc4181695ef65914e0f"
V82_SHA256 = "5aeae206741fc1712c8395a99c0d2b10a83802035962d81fcd0cb2b830d8b5db"
V83_SHA256 = "01eec956a8ab5676b8e748128595f3903892b0ce53940acc04dbc20f7c10c32f"
V84_SHA256 = "63fddfe34573db5bb2f38325ea2104d4daedf93c0138f3c49abb357dac4d0aa4"
V85_SHA256 = "f61bc64b1353de1c0cfd3642bd8ac33dacbd077e5368ba6773bd2d1f34f0d26b"
V86_SHA256 = "8fd98c20a7f1df1d3000ecfad019807c2f1193b53a58a4d8792fa581b223c755"
V87_SHA256 = "4cd47528cba22e318f790ec08c0186a05186bfebdbb44fb046d658cef40a1443"
V88_SHA256 = "311c0182f65b330b0a19edf1cc69917ea7a08b6a38b2867ad3600c111089a06c"
V89_SHA256 = "0aa7f77d2ce0af0288704555057d3462fcb512cf894aec9857ac1c44097871d9"
V90_SHA256 = "343c1b76d6d7bcb7c3f9389be7f4f7404acc010ce1355f3f35d7041769d6586f"
V91_SHA256 = "1d13e625de57d5311f10adaee8fa87ac145da64d87225c6545cc5219fa4edf17"
V92_SHA256 = "e342f26cf10ad6d0559c8357d1202bc03ccbe25a23e89bc9e3bb31f7dd8b5440"
V93_SHA256 = "7a8991a5fa4d2da54255f3693aa4c32fc0ebebe77013d53ad5ce35608cfb2827"
V94_SHA256 = "0b42dd92fbaa45c77340d710a884c1eb2730abbd07578c99d537dcab241e39d4"
V95_SHA256 = "9f7d33309c2cf5d6d1da61b350b4c4276481f30aa87e340f48eeb34d4fbdfc93"
V96_SHA256 = "3f5ef4013ae6800864045f6cb1286702ad9669d1d569bd0e2e2ed676aed777dd"
V97_SHA256 = "e687faa64f3ac5435e9aad29ad9d465c3c1f2c72c1ea514814e00e2f21b3e580"
V98_SHA256 = "a10af1e6a74693dab08363de8d70f329bac9b4126a90e5005a26f33faff35ce5"
V99_SHA256 = "8ce393324495c09410abedbc94dabd9788ea3bf48e70f4e72358e362adacef9d"
V100_SHA256 = "30c5749c06e6fedd8c37699f58d6100a263e1fda985c7a7079dd5c39fb8f8ec0"
V101_SHA256 = "4278e1dd9f965e796b0f7a0e7ee104f9b550e93c9408aab058c3a7fb9d3640c9"
V102_SHA256 = "dedae150932d0ab15bec84d2665a953a825eccccd7507b65a84eede6870349ba"
V103_SHA256 = "354db83a5d3a9ec659bd9de97cc9dccff28bd1351455d144862464159d68b4e3"
MINIMUM_A2_GENERATION = 103
D3_SHA256 = "3f1b04be1d97391b87e958eb008910b822567673582b61947f00099b9aa71c59"
D4_SHA256 = "d0b27962d852c9352306106b78ef26e00b919fc5a3a4070302c05ec667698b84"
MIGRATION_0001_SHA256 = "6d380b30733f99d3740b8d6dd89810fb31ca568625319b433023f48c9f667b7c"
MIGRATION_0002_LF_SHA256 = "3c0098dcd77e32a9e115dfcd40bd019901309894bb780ad66e90ed3846b60e97"
EXPECTED_D5_TABLES = {
    "app_fixture_projections", "app_opportunity_projections", "app_portfolio_members",
    "app_exports", "app_backups", "app_audit_events",
}
SOURCE_PATHS = (
    "scripts/audit_core_01d_checkpoint_e_completion_v2.py",
    "tests/fixtures/core_01d/data_01c_portability/predecessor_sources_v6.json",
    "tests/fixtures/core_01d/data_01c_portability/predecessor_sources_v5.json",
    "scripts/audit_app_01a_local_shell.py",
    "tests/fixtures/core_01d/data_01c_portability/predecessor_sources_v4.json",
    "sitecustomize.py",
    "tests/fixtures/core_01d/data_01c_portability/predecessor_sources_v3.json",
    'scripts/audit_core_01d_exact_pr_trigger_disposition_b1.py',
    'scripts/audit_core_01d_owner_one_shot_issue_comment_authority_b3.py',
    'tests/test_core_01d_historical_warehouse_transfer_authority_b2.py',
    'scripts/audit_core_01d_sportybet_current_trigger_authority_b4.py',
    'scripts/audit_core_01d_frozen_artifact_replay_authority_b5.py',
    'scripts/audit_core_01d_win_either_half_trigger_authority_b7.py',
    'scripts/audit_core_01d_retained_workflow_status.py',
    'scripts/audit_core_01d_retained_workflow_status_v3.py',
    'scripts/audit_core_01d_retained_workflow_status_v4.py',
    'tests/fixtures/core_01d/data_01c_portability/predecessor_sources_v2.json',
    '.github/workflows/port-02c-native-runtime.yml',
    'scripts/qualify_data_01c_restore_portability.py',
    'scripts/audit_data_01c_restore_portability.py',
    'scripts/audit_p4_workflow_evolution_ledger.py',
    'scripts/audit_core_01d_scheduled_shadow_ownership.py',
    'scripts/audit_core_01d_ci_offline_transport_boundary.py',
    'scripts/audit_core_01d_port02c_trigger_authority_b6.py',
    'scripts/audit_core_01d_checkpoint_e_completion.py',
    'scripts/audit_core_01d_retained_workflow_status_v2.py',
    'tests/native/test_port_02c_audit_source_forward.py',
    'tests/test_core_01d_cutover_authority.py',
    'tests/test_data_01c_restore_portability.py',
    'tests/fixtures/core_01d/data_01c_portability/predecessor_sources_v1.json',
    'artifacts/product/data_01c_restore_portability_v1.json',
    "database/migrations/0003_app_projections_exports.sql",
    "database/app_migrations.py", "database/app_root_lock.py",
    "database/app_storage_access.py", "database/app_repository.py",
    "database/run_repository.py", "services/app_projection_service.py",
    "services/export_service.py", "services/backup_service.py",
    "scripts/port_02c_build_config.py", "scripts/audit_data_01a_app_schema_core.py",
    "scripts/audit_data_01b_durable_run_state.py",
    "scripts/audit_data_01c_app_store_complete.py",
    "tests/test_data_01a_app_schema.py", "tests/test_data_01b_durable_run_state.py",
    "tests/native/test_data_01b_bundle_migrations.py",
    "tests/test_core_01d_ci_offline_transport_inventory_evolution.py",
    "tests/test_core_01d_exact_pr_trigger_disposition_b1.py",
    "tests/test_core_01d_owner_one_shot_issue_comment_authority_b3.py",
    "tests/test_core_01d_frozen_artifact_replay_authority_b5.py",
    "tests/test_core_01d_port02c_trigger_authority_b6.py",
    "tests/test_data_01c_app_storage.py", "tests/native/test_data_01c_bundle_migrations.py",
    "docs/product/data_01c_app_store_complete.md",
    "tests/fixtures/core_01d/data_01c_historical/d3_app_repository_source_v1.json",
    "tests/fixtures/core_01d/a2-v1-offline-transport.txt",
    "tests/fixtures/core_01d/a2-v1-ci-offline-transport-boundary.py.txt",
    "tests/fixtures/core_01d/a2-v1-p4-workflow-evolution-ledger.py.txt",
    "tests/fixtures/core_01d/a2-v1-port02c-source-forward-test.py.txt",
    "tests/fixtures/core_01d/a2-v1-p4-workflow-evolution-guard-test.py.txt",
    "scripts/audit_checkpoint_e_workflows.py",
    "tests/offline_transport.py",
    "tests/test_core_01d_ci_offline_transport_boundary.py",
    "tests/test_p4_4a_workflow_evolution_guard.py",
)
SUCCESSOR_SOURCE_PATHS = frozenset({
    "tests/fixtures/core_01d/data_01c_portability/predecessor_sources_v6.json",
    "tests/fixtures/core_01d/data_01c_portability/predecessor_sources_v5.json",
    "tests/fixtures/core_01d/data_01c_portability/predecessor_sources_v4.json",
    "tests/fixtures/core_01d/data_01c_portability/predecessor_sources_v3.json",
    'tests/fixtures/core_01d/data_01c_portability/predecessor_sources_v2.json',
    'scripts/qualify_data_01c_restore_portability.py',
    'scripts/audit_data_01c_restore_portability.py',
    'tests/test_data_01c_restore_portability.py',
    'tests/fixtures/core_01d/data_01c_portability/predecessor_sources_v1.json',
    'tests/test_core_01d_historical_warehouse_transfer_authority_b2.py',
    'artifacts/product/data_01c_restore_portability_v1.json',
    "database/app_root_lock.py",
    "database/app_storage_access.py",
    "database/migrations/0003_app_projections_exports.sql",
    "docs/product/data_01c_app_store_complete.md",
    "scripts/audit_data_01c_app_store_complete.py",
    "services/app_projection_service.py",
    "services/backup_service.py",
    "services/export_service.py",
    "tests/fixtures/core_01d/data_01c_historical/d3_app_repository_source_v1.json",
    "tests/fixtures/core_01d/a2-v1-offline-transport.txt",
    "tests/fixtures/core_01d/a2-v1-ci-offline-transport-boundary.py.txt",
    "tests/fixtures/core_01d/a2-v1-p4-workflow-evolution-ledger.py.txt",
    "tests/fixtures/core_01d/a2-v1-port02c-source-forward-test.py.txt",
    "tests/fixtures/core_01d/a2-v1-p4-workflow-evolution-guard-test.py.txt",
    "scripts/audit_core_01d_ci_offline_transport_boundary.py",
    "tests/test_core_01d_ci_offline_transport_inventory_evolution.py",
    "tests/native/test_data_01c_bundle_migrations.py",
    "tests/test_data_01c_app_storage.py",
    "sitecustomize.py",
    "tests/offline_transport.py",
    "tests/test_core_01d_ci_offline_transport_boundary.py",
})


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


def assert_prohibited_scope_unchanged():
    """Use pinned source trees, so the guard also works in depth-1 PR CI."""
    workflow_tree = boundary.git("rev-parse", "HEAD:.github/workflows").decode().strip()
    if workflow_tree != boundary.WORKFLOW_TREE:
        from scripts.audit_data_01c_restore_portability import historical_workflow_tree
        try:
            projected = historical_workflow_tree(workflow_tree)
        except ValueError as exc:
            raise AssertionError("prohibited workflow delta without base evidence") from exc
        if projected != boundary.WORKFLOW_TREE:
            raise AssertionError("prohibited workflow delta without base evidence")
    status = boundary.git(
        "status", "--porcelain", "--untracked-files=all", "--",
        ".github/workflows", "database/athena.db", "database/athena_history.db",
    ).decode().splitlines()
    if status:
        raise AssertionError("prohibited workflow or legacy database delta")


def authenticate_d5_a2_lineage(latest):
    """Retain the sealed D5 V103 checkpoint and authenticate later A2 successors."""
    chain = boundary.load_inventory_generations()
    if len(chain) < MINIMUM_A2_GENERATION:
        raise AssertionError("D5 A2 lineage ends before its authenticated V103 checkpoint")
    v103 = chain[MINIMUM_A2_GENERATION - 1][1]
    if (v103.get("canonical_sha256") != V103_SHA256
            or v103.get("predecessor_inventory") != {
                "path": boundary.inventory_generation_path(102),
                "canonical_sha256": V102_SHA256,
                "generation": 102,
                "rewritten": False,
            }
            or latest != chain[-1][1]):
        raise AssertionError("D5 A2 successor chain does not retain exact V103 ancestry")
    return latest


def build_receipt(latest=None):
    latest = boundary.authenticate_inventory() if latest is None else latest
    authenticate_d5_a2_lineage(latest)
    if not SUCCESSOR_SOURCE_PATHS <= set(SOURCE_PATHS):
        raise AssertionError("D5 successor source set is outside its authenticated source identities")
    predecessor = latest.get("predecessor_inventory")
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
    assert_prohibited_scope_unchanged()
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
        "a2_inventory": {"generation": latest["generation"],
                         "path": boundary.inventory_generation_path(latest["generation"]),
                         "canonical_sha256": latest["canonical_sha256"]},
        "a2_predecessor": predecessor,
        "successor_source_paths": sorted(SUCCESSOR_SOURCE_PATHS),
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
        "workflow_yaml_delta": 1,
        "workflow_source_evolution": "EXACT_PORT02C_D5_NATIVE_RESTORE_QUALIFICATION_ONLY",
        "restore_portability": {"source_receipt": "artifacts/product/data_01c_restore_portability_v1.json",
                               "native_receipts": "EXACT_FINAL_HEAD_WINDOWS_NTFS_LINUX_EXT4_REQUIRED_SEPARATELY"},
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


def audit(latest=None):
    rebuilt = build_receipt(latest=latest)
    expected = canonical(rebuilt)
    raw = (ROOT / RECEIPT).read_bytes()
    if rebuilt["a2_inventory"]["generation"] >= 116:
        value = json.loads(raw)
        if (raw != canonical(value)
                or value.get("canonical_sha256") != "c9be3cc4c74fea16c9f97c0db3fe7b54d9e12373fc5787d46677f36276f7441d"
                or hashlib.sha256(canonical({key: row for key, row in value.items()
                                             if key != "canonical_sha256"})).hexdigest() != value["canonical_sha256"]):
            raise AssertionError("D5 source receipt immutable predecessor mismatch")
        for key in set(value) - {"canonical_sha256", "source_identities", "a2_inventory", "a2_predecessor"}:
            if rebuilt.get(key) != value[key]:
                raise AssertionError("D5 predecessor semantics changed: " + key)
        frozen = {row["path"]: row["lf_sha256"] for row in value["source_identities"]}
        current = {row["path"]: row["lf_sha256"] for row in rebuilt["source_identities"]}
        evolved = {"database/run_repository.py", "scripts/audit_data_01b_durable_run_state.py",
                   "scripts/audit_data_01c_app_store_complete.py", "tests/test_data_01c_app_storage.py",
                   "scripts/audit_checkpoint_e_workflows.py", "scripts/audit_data_01c_restore_portability.py",
                   "tests/test_core_01d_exact_pr_trigger_disposition_b1.py"}
        inventory = boundary.authenticate_inventory()
        identities = {row["path"]: row["lf_source_sha256"] for row in inventory["source_identities"]}
        if (set(current) != set(frozen)
                or any(digest != frozen[path] and (path not in evolved or identities.get(path) != digest)
                       for path, digest in current.items())):
            raise AssertionError("unreviewed D5 source evolution")
        return value
    if raw != expected:
        raise AssertionError("D5 source receipt does not match exact current sources")
    value = json.loads(raw)
    if value.get("canonical_sha256") != hashlib.sha256(
            canonical({key: row for key, row in value.items() if key != "canonical_sha256"})).hexdigest():
        raise AssertionError("D5 source receipt seal mismatch")
    return value


def authenticate_successor():
    """Authenticate only D5's exact additive sources and A2 successor files."""
    latest = boundary.authenticate_inventory()
    value = audit(latest=latest)
    expected_paths = list(SOURCE_PATHS)
    identities = value.get("source_identities")
    if (type(identities) is not list
            or [row.get("path") for row in identities if type(row) is dict] != expected_paths
            or value.get("successor_source_paths") != sorted(SUCCESSOR_SOURCE_PATHS)
            or value.get("policy_id") != "ATHENA_DATA_01C_STORAGE_READY_PROJECTIONS_SOURCE_BLOCKED_V1"
            or value.get("a2_inventory") != {
                "generation": min(latest["generation"], 115),
                "path": boundary.inventory_generation_path(min(latest["generation"], 115)),
                "canonical_sha256": boundary.read_generation(boundary.inventory_generation_path(min(latest["generation"], 115)))["canonical_sha256"]}
            or value.get("projection_source", {}).get("typed_disposition") != "SOURCE_CONTRACT_UNAVAILABLE"
            or value.get("projection_source", {}).get("coverage_disposition") != "COVERAGE_UNAVAILABLE"
            or value.get("projection_source", {}).get("materialized_verified_rows") != 0):
        raise AssertionError("D5 successor receipt is not the exact source-blocked A2 successor record")
    a2_paths = {boundary.inventory_generation_path(generation)
                for generation in range(75, latest["generation"] + 1)}
    paths = set(SUCCESSOR_SOURCE_PATHS) | {RECEIPT} | a2_paths
    if latest["generation"] >= 116:
        from scripts import audit_run_01a_durable_admission as e1
        paths |= e1.authenticate_successor()
    return paths


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
