"""D3 / DATA-01A app-schema migration framework.

Versioned migration ownership for the separate app-owned SQLite store
(``athena-app.sqlite3``) resolved from ``WritableRoots.data_root``. This
framework owns exactly one migration family: the additive R1 application
control core (``database/migrations/0001_app_control_core.sql``). It is
deliberately separate from the legacy ``database.database.Database`` football /
history / warehouse ownership and never touches those stores.

Every connection enables ``PRAGMA foreign_keys = ON`` and requires WAL mode
(fail-closed when unavailable). ``synchronous`` is ``FULL`` during durable
migration / commit work and ``NORMAL`` during read-only verification.

Migrations are applied exactly once under the ``app_schema_migrations`` ledger
with transactional DDL. This module never fabricates release provenance: the
recorded ``release_id`` is supplied by the caller from the verified release
identity, and the ``backup_manifest_sha256`` is the canonical SHA-256 of the
truthful pre-migration inventory (empty for a fresh store).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

from domain.run_contracts import canonical_sha256
from runtime.resources import ResourceResolver, WritableRoots
from runtime.release_identity import InstalledReleaseIdentity
from database.app_migration_evidence import contained, retain_pre_migration_evidence, verify_retained_manifest

APP_STORE_FILENAME = "athena-app.sqlite3"

# The single additive R1 application migration. Exact version -> tracked
# migration resource path. Legacy ``002_add_elo_columns.sql`` is intentionally
# absent: it is a football-history migration and must never run as an app
# migration.
APP_MIGRATIONS: tuple[tuple[int, str], ...] = (
    (1, "database/migrations/0001_app_control_core.sql"),
)

APP_MIGRATION_ROLE = "MIGRATION"


class AppSchemaMismatchError(RuntimeError):
    """Fail-closed on any missing, empty, partial, or inconsistent schema state."""


def app_store_path(writable_roots: WritableRoots) -> Path:
    """Resolve the app-owned store under ``WritableRoots.data_root``."""
    return Path(writable_roots.data_root) / APP_STORE_FILENAME


def _utc_text(now: datetime | None = None) -> str:
    value = now if now is not None else datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise AppSchemaMismatchError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _synchronous_value(name: str) -> int:
    if name == "FULL":
        return 2
    if name == "NORMAL":
        return 1
    raise AppSchemaMismatchError("unsupported synchronous level")


def connect_app_store(
    path: Path,
    *,
    readonly: bool = False,
    synchronous: str = "NORMAL",
) -> sqlite3.Connection:
    """Open the app store with reviewed durability and integrity settings.

    ``readonly=True`` opens a true read-only connection (``mode=ro``) and does
    not attempt to (re)bind WAL. Non-readonly connections set and verify WAL.
    """
    target = str(path)
    uri = False
    if readonly:
        target = path.resolve().as_uri() + "?mode=ro"
        uri = True
    try:
        conn = sqlite3.connect(
            target,
            timeout=30.0,
            isolation_level=None,  # manual transaction control
            uri=uri,
        )
    except sqlite3.Error as exc:  # pragma: no cover - surfaced to caller
        raise AppSchemaMismatchError(f"unable to open app store: {exc}") from exc
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        if not _pragma_flag(conn, "foreign_keys"):
            raise AppSchemaMismatchError("app store did not enable foreign_keys")
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        if readonly:
            if str(journal).lower() != "wal":
                raise AppSchemaMismatchError("app store is not in WAL mode")
        else:
            bound = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            if str(bound).lower() != "wal":
                raise AppSchemaMismatchError("WAL mode unavailable for app store")
        conn.execute(f"PRAGMA synchronous = {_synchronous_value(synchronous)}")
        conn.execute("PRAGMA busy_timeout = 30000")
    except AppSchemaMismatchError:
        conn.close()
        raise
    except sqlite3.Error as exc:
        conn.close()
        raise AppSchemaMismatchError(f"app store pragma setup failed: {exc}") from exc
    return conn


def _pragma_flag(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(f"PRAGMA {name}").fetchone()
    return row is not None and int(row[0]) == 1


def read_app_migrations(resources: ResourceResolver) -> list[tuple[int, str, bytes, str]]:
    """Read exact migration bytes through the verified ResourceResolver.

    Returns ``(version, logical_path, raw_bytes, byte_sha256)`` ordered by
    version. DevelopmentCheckout reads exact tracked HEAD bytes; InstalledRelease
    reads exact manifest-pinned resource bytes (``expected_role='MIGRATION'``).
    """
    loaded: list[tuple[int, str, bytes, str]] = []
    expected_versions = [version for version, _ in APP_MIGRATIONS]
    if expected_versions != sorted(expected_versions) or len(set(expected_versions)) != len(expected_versions):
        raise AppSchemaMismatchError("APP_MIGRATIONS versions must be strictly increasing from 1")
    for version, logical_path in APP_MIGRATIONS:
        if version < 1:
            raise AppSchemaMismatchError("app migration versions must be >= 1")
        raw = resources.read_bytes(logical_path, expected_role=APP_MIGRATION_ROLE)
        if not isinstance(raw, bytes) or not raw:
            raise AppSchemaMismatchError(f"migration {logical_path} produced no bytes")
        loaded.append((version, logical_path, raw, hashlib.sha256(raw).hexdigest()))
    if [item[0] for item in loaded] != list(range(1, len(loaded) + 1)):
        raise AppSchemaMismatchError("app migration versions must be contiguous from 1")
    return loaded


def _statements(sql: str) -> list[str]:
    """Split reviewed migration SQL into executable statements.

    The app migration carries no triggers and no semicolons inside literals, so
    stripping ``--`` line comments and splitting on ``;`` is exact.
    """
    buffer: list[str] = []
    for line in sql.splitlines():
        cut = line.split("--", 1)[0]
        buffer.append(cut)
    text = "\n".join(buffer)
    return [piece.strip() for piece in text.split(";") if piece.strip()]


def pre_migration_backup_manifest(conn: sqlite3.Connection) -> dict[str, Any]:
    """Truthful inventory of the app schema immediately before a migration.

    For a fresh store this records version 0 with no app tables and no rows; it
    never claims a backup that was not taken. Its canonical SHA-256 is recorded
    as ``app_schema_migrations.backup_manifest_sha256``.
    """
    version_before = current_schema_version(conn)
    tables_before: dict[str, int] = {}
    for name in sorted(_app_tables(conn)):
        count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        tables_before[name] = int(count)
    return {
        "kind": "APP_SCHEMA_MIGRATION_BACKUP_MANIFEST",
        "schema_version_before": version_before,
        "app_tables_before": tables_before,
    }


def current_schema_version(conn: sqlite3.Connection) -> int:
    if "app_schema_migrations" not in _table_names(conn):
        return 0
    row = conn.execute("SELECT MAX(version) FROM app_schema_migrations").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def applied_versions(conn: sqlite3.Connection) -> list[int]:
    if "app_schema_migrations" not in _table_names(conn):
        return []
    rows = conn.execute("SELECT version FROM app_schema_migrations ORDER BY version").fetchall()
    return [int(row[0]) for row in rows]


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _app_tables(conn: sqlite3.Connection) -> set[str]:
    return {name for name in _table_names(conn) if name.startswith("app_")}


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [str(row[1]) for row in rows]


# Expected schema for migration version 1. Used for fail-closed verification of
# exact table and column agreement (guards against drift and partial state).
_EXPECTED_APP_TABLES_V1: dict[str, tuple[str, ...]] = {
    "app_schema_migrations": (
        "version",
        "migration_sha256",
        "applied_at",
        "release_id",
        "backup_manifest_sha256",
    ),
    "app_profiles": ("profile_id", "display_name", "created_at"),
    "app_preferences": ("profile_id", "preference_key", "value_json", "updated_at"),
    "app_favorites": ("profile_id", "entity_kind", "entity_identity", "created_at"),
    "app_release_manifests": (
        "release_id",
        "source_mode",
        "source_commit",
        "platform",
        "architecture",
        "build_id",
        "manifest_bytes",
        "manifest_byte_sha256",
        "trust_mode",
        "signature_key_id",
        "verified_at",
    ),
    "app_artifacts": (
        "artifact_id",
        "byte_sha256",
        "canonical_sha256",
        "byte_count",
        "media_type",
        "artifact_kind",
        "logical_path",
        "evidence_class",
        "verification_policy_id",
        "verified_at",
        "created_at",
    ),
    "app_artifact_edges": ("parent_artifact_id", "child_artifact_id", "relation"),
    "app_capability_snapshots": (
        "snapshot_id",
        "release_id",
        "profile",
        "report_bytes",
        "report_sha256",
        "evaluated_at",
        "expires_at",
    ),
    "app_run_previews": (
        "preview_id",
        "profile_id",
        "request_bytes",
        "request_sha256",
        "envelope_bytes",
        "envelope_sha256",
        "capability_snapshot_id",
        "created_at",
        "expires_at",
    ),
}


def expected_app_tables() -> dict[str, tuple[str, ...]]:
    return dict(_EXPECTED_APP_TABLES_V1)


def verify_app_schema(conn: sqlite3.Connection) -> None:
    """Fail-closed ledger/schema agreement for the current binary."""
    max_binary = APP_MIGRATIONS[-1][0]
    versions = applied_versions(conn)
    if not versions:
        raise AppSchemaMismatchError("app schema ledger is empty")
    if versions != list(range(1, len(versions) + 1)):
        raise AppSchemaMismatchError("app schema ledger has a version gap")
    if versions[-1] > max_binary:
        raise AppSchemaMismatchError("app schema is newer than the current binary")
    if versions[-1] < max_binary:
        raise AppSchemaMismatchError("app schema is older than the current binary")

    expected = expected_app_tables()
    actual_tables = _table_names(conn)
    expected_names = set(expected)
    missing = expected_names - actual_tables
    unexpected_app = {name for name in actual_tables if name.startswith("app_")} - expected_names
    unexpected_any = actual_tables - expected_names
    if missing:
        raise AppSchemaMismatchError(f"app schema missing tables: {sorted(missing)}")
    if unexpected_app:
        raise AppSchemaMismatchError(f"unknown app tables present: {sorted(unexpected_app)}")
    if unexpected_any:
        raise AppSchemaMismatchError(f"unexpected non-app tables present: {sorted(unexpected_any)}")

    for table, columns in expected.items():
        actual_columns = _table_columns(conn, table)
        if actual_columns != list(columns):
            raise AppSchemaMismatchError(
                f"app table {table} columns drifted: {actual_columns} != {list(columns)}"
            )

    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise AppSchemaMismatchError(f"app schema foreign key violation: {violations}")


def _verify_pre_state(conn: sqlite3.Connection) -> None:
    """Fail-closed ownership / version state before applying a migration."""
    versions = applied_versions(conn)
    app_tables = _app_tables(conn)
    if not versions and app_tables:
        raise AppSchemaMismatchError("app tables present without a ledger (partial state)")
    if _table_names(conn) - set(expected_app_tables()):
        raise AppSchemaMismatchError("unowned tables in app migration target")
    if versions and not app_tables:
        raise AppSchemaMismatchError("app ledger present without app tables (partial state)")
    if versions != list(range(1, len(versions) + 1)):
        raise AppSchemaMismatchError("app schema ledger has a version gap")
    max_binary = APP_MIGRATIONS[-1][0]
    if versions and versions[-1] > max_binary:
        raise AppSchemaMismatchError("app schema is newer than the current binary")


def apply_app_migrations(
    resources: ResourceResolver,
    writable_roots: WritableRoots,
    *,
    release_id: str,
    now: datetime | None = None,
) -> Path:
    """Apply pending app migrations exactly once, transactionally.

    Follows the reviewed atomicity sequence: verify exact migration resource
    bytes, verify ownership/version state, produce the pre-migration backup
    manifest, then per migration run transactional DDL + validation +
    ``foreign_key_check`` + ledger insert and commit. Finally reopen a fresh
    connection and re-verify pragma and schema agreement.
    """
    if type(release_id) is not str or not release_id:
        raise AppSchemaMismatchError("release_id must be non-empty exact text")
    if type(resources) is not ResourceResolver or type(writable_roots) is not WritableRoots:
        raise AppSchemaMismatchError("verified resolver and writable roots are required")
    if type(resources.identity) is InstalledReleaseIdentity and writable_roots.installed_release_root != resources.identity.release_root:
        raise AppSchemaMismatchError("writable roots do not bind the verified installed release")
    writable_roots.ensure_created()
    store = app_store_path(writable_roots)
    contained(writable_roots.data_root, APP_STORE_FILENAME)
    for suffix in ("-wal", "-shm", "-journal"):
        contained(writable_roots.data_root, APP_STORE_FILENAME + suffix)
    existed = store.exists()
    backup_sha = retain_pre_migration_evidence(resources, writable_roots, store, existed)
    migrations = read_app_migrations(resources)

    conn = connect_app_store(store, synchronous="FULL")
    try:
        _verify_pre_state(conn)
        for version, logical_path, raw, byte_sha in migrations:
            recorded = applied_versions(conn)
            if version in recorded:
                row = conn.execute(
                    "SELECT migration_sha256, backup_manifest_sha256 FROM app_schema_migrations WHERE version = ?",
                    (version,),
                ).fetchone()
                if row is None or str(row[0]) != byte_sha:
                    raise AppSchemaMismatchError(
                        f"migration {version} recorded SHA-256 disagrees with resource bytes"
                    )
                verify_retained_manifest(writable_roots.data_root, row[1])
                continue
            if version != len(recorded) + 1:
                raise AppSchemaMismatchError(f"migration {version} would introduce a version gap")

            sql_text = raw.decode("utf-8")

            conn.execute("BEGIN")
            try:
                for statement in _statements(sql_text):
                    conn.execute(statement)
                # Validate the migration created the full expected table set.
                for table in expected_app_tables():
                    if table not in _table_names(conn):
                        raise AppSchemaMismatchError(
                            f"migration {logical_path} did not create table {table}"
                        )
                if _table_names(conn) != set(expected_app_tables()):
                    raise AppSchemaMismatchError("migration created an unexpected table set")
                for table, columns in expected_app_tables().items():
                    if _table_columns(conn, table) != list(columns):
                        raise AppSchemaMismatchError("migration column identity drift")
                violations = conn.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise AppSchemaMismatchError(
                        f"migration {logical_path} left foreign key violations: {violations}"
                    )
                conn.execute(
                    "INSERT INTO app_schema_migrations "
                    "(version, migration_sha256, applied_at, release_id, backup_manifest_sha256) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (version, byte_sha, _utc_text(now), release_id, backup_sha),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
    finally:
        conn.close()

    # Reopen a fresh connection and verify pragma + schema agreement.
    fresh = connect_app_store(store, synchronous="FULL")
    try:
        if not _pragma_flag(fresh, "foreign_keys"):
            raise AppSchemaMismatchError("app store did not re-enable foreign_keys after migration")
        verify_app_schema(fresh)
    finally:
        fresh.close()
    return store
