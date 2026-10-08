"""Server-owned pre-DDL recovery evidence, not a user-facing backup product."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from runtime.release_identity import DevelopmentCheckoutIdentity, verify_development_checkout

POLICY_ID = "ATHENA_APP_PRE_MIGRATION_RECOVERY_V1"


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode()


def contained(root, relative):
    """Internal constants/digests only; reject links including Windows junctions."""
    root = Path(root)
    target = root / relative
    cursor = target
    while cursor != root.parent:
        if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()):
            raise ValueError("migration evidence link/junction forbidden")
        if cursor == root:
            break
        cursor = cursor.parent
    target.resolve().relative_to(root.resolve())
    return target


def publish(root, relative, raw):
    """Contained fsynced temp + atomic hard-link publication; never overwrite."""
    target = contained(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    contained(root, relative)
    fd, temporary = tempfile.mkstemp(prefix=".migration-", dir=target.parent)
    temp = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp, target)
        except FileExistsError:
            contained(root, relative)
            if target.read_bytes() != raw:
                raise ValueError("immutable migration evidence collision")
        if os.name != "nt":
            directory = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temp.unlink(missing_ok=True)
    return target


def ownership_inventory(resources, roots, existed):
    rows = [{"owner": "APP_CONTROL", "root": "DATA_ROOT", "logical_path": "athena-app.sqlite3",
             "exists": existed, "migration_write_target": True}]
    identity = resources.identity
    if type(identity) is DevelopmentCheckoutIdentity:
        current = verify_development_checkout(identity.repository_root)
        if current.head_commit_sha != identity.head_commit_sha:
            raise ValueError("development identity changed before DB inventory")
        for owner, locator in (("LEGACY_OPERATIONAL", "database/athena.db"),
                               ("HISTORICAL_WAREHOUSE", "database/athena_history.db")):
            path = contained(identity.repository_root, locator)
            row = {"owner": owner, "root": "VERIFIED_DEVELOPMENT_CHECKOUT", "logical_path": locator,
                   "exists": path.exists(), "migration_write_target": False}
            if path.exists():
                if not path.is_file():
                    raise ValueError("reviewed database locator is not a regular file")
                raw = path.read_bytes()
                row.update(byte_sha256=hashlib.sha256(raw).hexdigest(), byte_count=len(raw))
            rows.append(row)
    # No reviewed source-controlled generated DB locator currently exists.
    # Unknown paths are never searched recursively or adopted by this policy.
    return {"policy_id": "REVIEWED_DB_LOCATORS_ONLY_V1", "roots": rows,
            "generated_research_locators": [], "unknown_policy": "UNCLASSIFIED_NEVER_ADOPTED",
            "verified_development_head": identity.head_commit_sha if type(identity) is DevelopmentCheckoutIdentity else None,
            "installed_repository_locators_assumed": False}


def retain_pre_migration_evidence(resources, roots, store, existed):
    root = roots.data_root
    contained(root, "athena-app.sqlite3")
    inventory = ownership_inventory(resources, roots, existed)
    inventory_raw = canonical(inventory)
    inventory_sha = hashlib.sha256(inventory_raw).hexdigest()
    inventory_locator = "migration-evidence/inventories/" + inventory_sha + ".json"
    publish(root, inventory_locator, inventory_raw)
    backup = None
    tables = {}
    if existed:
        backup_dir = contained(root, "migration-evidence/backups")
        backup_dir.mkdir(parents=True, exist_ok=True)
        contained(root, "migration-evidence/backups")
        fd, temporary = tempfile.mkstemp(prefix=".snapshot-", suffix=".sqlite3", dir=backup_dir)
        os.close(fd)
        source = destination = None
        try:
            source = sqlite3.connect(store.resolve().as_uri() + "?mode=ro", uri=True)
            destination = sqlite3.connect(temporary)
            for conn in (source, destination):
                conn.execute("PRAGMA foreign_keys=ON")
                if conn.execute("PRAGMA foreign_keys").fetchone() != (1,):
                    raise ValueError("backup connection foreign_keys unavailable")
            source.backup(destination)
            destination.commit()
            names = destination.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
            for (name,) in names:
                escaped = name.replace('"', '""')
                tables[name] = destination.execute('SELECT COUNT(*) FROM "' + escaped + '"').fetchone()[0]
            destination.close()
            destination = None
            raw = Path(temporary).read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            locator = "migration-evidence/backups/" + digest + ".sqlite3"
            publish(root, locator, raw)
            backup = {"logical_path": locator, "byte_sha256": digest, "byte_count": len(raw),
                      "snapshot_policy": "SQLITE_BACKUP_API_CONSISTENT_SNAPSHOT"}
        finally:
            if destination is not None:
                destination.close()
            if source is not None:
                source.close()
            Path(temporary).unlink(missing_ok=True)
    manifest = {"policy_id": POLICY_ID, "app_store_state": "EXISTING" if existed else "ABSENT",
                "ownership_inventory": inventory, "app_tables_before": tables, "backup": backup,
                "ownership_inventory_evidence": {"logical_path": inventory_locator, "byte_sha256": inventory_sha},
                "rollback": "RESTORE_SQLITE_BACKUP_WITH_APP_STOPPED" if existed else "RESTORE_ABSENT_APP_STORE_WITH_APP_STOPPED"}
    raw = canonical(manifest)
    digest = hashlib.sha256(raw).hexdigest()
    publish(root, "migration-evidence/" + digest + ".json", raw)
    return digest


def verify_retained_manifest(root, digest):
    if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("invalid migration manifest digest")
    path = contained(root, "migration-evidence/" + digest + ".json")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("migration manifest hash mismatch")
    value = json.loads(raw)
    if canonical(value) != raw or value["policy_id"] != POLICY_ID:
        raise ValueError("migration manifest not canonical")
    backup = value["backup"]
    inventory = value["ownership_inventory_evidence"]
    inventory_locator = "migration-evidence/inventories/" + inventory["byte_sha256"] + ".json"
    inventory_raw = canonical(value["ownership_inventory"])
    if (inventory["logical_path"] != inventory_locator
            or hashlib.sha256(inventory_raw).hexdigest() != inventory["byte_sha256"]
            or contained(root, inventory_locator).read_bytes() != inventory_raw):
        raise ValueError("ownership inventory evidence mismatch")
    if backup is not None:
        locator = "migration-evidence/backups/" + backup["byte_sha256"] + ".sqlite3"
        if backup["logical_path"] != locator:
            raise ValueError("backup locator mismatch")
        data = contained(root, locator).read_bytes()
        if hashlib.sha256(data).hexdigest() != backup["byte_sha256"] or len(data) != backup["byte_count"]:
            raise ValueError("backup bytes mismatch")
    return value
