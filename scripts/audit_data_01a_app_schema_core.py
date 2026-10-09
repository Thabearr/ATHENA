"""Authenticate D3 evidence before projecting the immutable pre-D3 build config."""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = "artifacts/product/data_01a_app_schema_core_v1.json"
BUILD_CONFIG = "scripts/port_02c_build_config.py"
SNAPSHOT = "tests/fixtures/core_01d/data_01a_historical/port_02c_build_config.py.b64"
BUILD_CONFIG_SHA256 = "ccda416cefd71854af226a23d8b4f2631dabb28e95912e99b2fa6333682d66ca"
BUILD_CONFIG_BLOB = "db26c06a915b643e985fd677451285f8a717e8b9"
NEW_PATHS = {
    "docs/product/data_01a_storage_safety.md",
    RECEIPT, SNAPSHOT, "scripts/audit_data_01a_app_schema_core.py",
    "database/app_migrations.py", "database/app_repository.py",
    "database/app_migration_evidence.py",
    "database/migrations/0001_app_control_core.sql",
    "services/app_preview_store.py", "tests/test_data_01a_app_schema.py",
}


def authenticate():
    latest = boundary.authenticate_inventory()
    receipt = boundary.read(RECEIPT)
    boundary.require((ROOT / RECEIPT).read_bytes() == boundary.canonical(receipt),
                     "D3 receipt is not canonical")
    boundary.require(receipt == boundary.seal(receipt), "D3 receipt seal mismatch")
    boundary.require(receipt["base_commit"] == "9d674169c680a256d20db81e2bddf733b13c85cb",
                     "D3 base identity drift")
    inventory = boundary.read_generation(receipt["a2_inventory"]["path"])
    boundary.require(inventory["generation"] == 68 and latest["generation"] >= 68
                     and inventory["canonical_sha256"] == receipt["a2_inventory"]["canonical_sha256"],
                     "D3 A2 binding drift")
    identities = {row["path"]: row["lf_source_sha256"] for row in inventory["source_identities"]}
    successor = None
    for path, expected in receipt["source_identities"].items():
        actual = hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        boundary.require(not path.endswith(".py") or identities.get(path) == expected,
                         "D3 frozen V68 source identity drift: " + path)
        if actual != expected:
            from scripts import audit_data_01b_durable_run_state as data01b
            if successor is None:
                successor = data01b.authenticate_successor(latest)
            current = {row["path"]: row["lf_source_sha256"] for row in latest["source_identities"]}
            boundary.require(current.get(path) == actual, "unreviewed D3 source successor: " + path)
            historical = data01b.historical_sources()[path]
            boundary.require(hashlib.sha256(historical.replace(b"\r\n", b"\n")).hexdigest() == expected,
                             "D3 historical source identity drift: " + path)
    boundary.require(receipt["workflow_yaml_delta"] == 0 and all(value == 0 for value in receipt["safety"].values()),
                     "D3 safety evidence drift")
    return receipt


def successor_paths():
    """Bounded D4 additions omitted only from authenticated historical views."""
    from scripts import audit_data_01b_durable_run_state as data01b
    data01b.authenticate_successor(boundary.authenticate_inventory())
    return data01b.NEW_PATHS


def historical_build_config():
    authenticate()
    raw = base64.b64decode((ROOT / SNAPSHOT).read_bytes(), validate=True)
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    boundary.require(hashlib.sha256(raw).hexdigest() == BUILD_CONFIG_SHA256 and blob == BUILD_CONFIG_BLOB,
                     "D3 historical build-config identity drift")
    return raw
