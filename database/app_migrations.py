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
import re
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
    (2, "database/migrations/0002_app_runs_operations.sql"),
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


# Expected schema for migration version 2: the v1 control core plus exactly the
# five D4 run control-plane tables. D5 projection/export/backup/audit tables are
# deliberately absent. A v1 database is a valid upgrade candidate; a v2 database
# must match this set exactly.
_EXPECTED_APP_TABLES_V2: dict[str, tuple[str, ...]] = {
    **_EXPECTED_APP_TABLES_V1,
    "app_runs": (
        "run_id",
        "profile_id",
        "preview_id",
        "idempotency_key",
        "request_bytes",
        "request_sha256",
        "envelope_bytes",
        "envelope_sha256",
        "release_id",
        "state",
        "state_version",
        "created_at",
        "updated_at",
        "receipt_artifact_id",
    ),
    "app_run_attempts": (
        "attempt_id",
        "run_id",
        "attempt_number",
        "lease_token",
        "worker_instance_id",
        "process_locator_json",
        "heartbeat_at",
        "started_at",
        "finished_at",
        "exit_code",
        "recovery_disposition",
    ),
    "app_run_events": (
        "run_id",
        "sequence",
        "state_version",
        "event_type",
        "payload_bytes",
        "payload_sha256",
        "observed_at",
    ),
    "app_external_operations": (
        "operation_id",
        "run_id",
        "attempt_id",
        "operation_kind",
        "intent_sha256",
        "authority_sha256",
        "input_artifact_id",
        "idempotency_key",
        "state",
        "prepared_at",
        "sent_at",
        "completed_at",
        "response_artifact_id",
        "error_code",
    ),
    "app_run_artifacts": (
        "run_id",
        "artifact_id",
        "role",
        "retained_root",
    ),
}


# Static review dicts exist only for the reviewed migration versions. Schema
# versions beyond the reviewed set (offline test successors) authenticate solely
# against structure derived from the verified migration bytes themselves.
_EXPECTED_APP_TABLES_BY_VERSION: dict[int, dict[str, tuple[str, ...]]] = {
    1: _EXPECTED_APP_TABLES_V1,
    2: _EXPECTED_APP_TABLES_V2,
}


def expected_app_tables(version: int | None = None) -> dict[str, tuple[str, ...]]:
    if version is None:
        version = APP_MIGRATIONS[-1][0]
    try:
        return dict(_EXPECTED_APP_TABLES_BY_VERSION[version])
    except KeyError:
        raise AppSchemaMismatchError("no expected schema for migration version") from None


def schema_structure(conn):
    """SQLite structure plus tokenized constraints; whitespace/comments have no meaning."""
    def tokens(sql):
        if sql is None:
            return None
        parts = re.findall(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`[^`]*`|\[[^\]]*\]|--[^\n]*|/\*[\s\S]*?\*/|[A-Za-z_][A-Za-z_0-9]*|\d+|[^\s]", sql)
        return tuple(p if p[0] in "'\"`[" else p.upper() for p in parts if not p.startswith(("--", "/*")))
    objects = conn.execute("SELECT type, name, tbl_name, sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name").fetchall()
    result = [(kind, name, table, tokens(sql)) for kind, name, table, sql in objects]
    for kind, name, _, _ in objects:
        if kind != "table":
            continue
        quoted = '"' + name.replace('"', '""') + '"'
        result.append(("columns", name, tuple(conn.execute("PRAGMA table_xinfo(" + quoted + ")"))))
        result.append(("foreign_keys", name, tuple(conn.execute("PRAGMA foreign_key_list(" + quoted + ")"))))
        indexes = sorted(conn.execute("PRAGMA index_list(" + quoted + ")").fetchall(), key=lambda row: row[1])
        result.append(("indexes", name, tuple(tuple(row[1:]) for row in indexes)))
        for index in indexes:
            index_name = '"' + index[1].replace('"', '""') + '"'
            result.append(("index_columns", index[1], tuple(conn.execute("PRAGMA index_xinfo(" + index_name + ")"))))
    return tuple(result)


def expected_schema_structure(migrations):
    expected = sqlite3.connect(":memory:")
    try:
        expected.execute("PRAGMA foreign_keys=ON")
        for _, _, raw, _ in migrations:
            for statement in _statements(raw.decode("utf-8")):
                expected.execute(statement)
        return schema_structure(expected)
    finally:
        expected.close()


def verify_app_schema(conn: sqlite3.Connection, *, expected_structure=None) -> None:
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

    if expected_structure is None:
        raise AppSchemaMismatchError("verified expected schema structure is required")
    expected = {
        entry[1]: tuple(column[1] for column in entry[2])
        for entry in expected_structure if entry[0] == "columns"
    }
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
    if expected_structure is None:
        raise AppSchemaMismatchError("verified expected schema structure is required")
    if schema_structure(conn) != expected_structure:
        raise AppSchemaMismatchError("app schema constraint/structure drift")


def _verify_pre_state(conn: sqlite3.Connection, migrations) -> None:
    """Fail-closed ownership / version state before applying a migration."""
    versions = applied_versions(conn)
    app_tables = _app_tables(conn)
    if not versions and app_tables:
        raise AppSchemaMismatchError("app tables present without a ledger (partial state)")
    if versions and not app_tables:
        raise AppSchemaMismatchError("app ledger present without app tables (partial state)")
    if versions != list(range(1, len(versions) + 1)):
        raise AppSchemaMismatchError("app schema ledger has a version gap")
    max_binary = APP_MIGRATIONS[-1][0]
    if versions and versions[-1] > max_binary:
        raise AppSchemaMismatchError("app schema is newer than the current binary")
    version = versions[-1] if versions else 1
    structure = expected_schema_structure(migrations[:version])
    names = {entry[1] for entry in structure if entry[0] == "columns"}
    if _table_names(conn) - names:
        raise AppSchemaMismatchError("unowned tables in app migration target")


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
    migrations = read_app_migrations(resources)
    expected_structure = expected_schema_structure(migrations)
    existed = store.exists()
    recorded_versions: list[int] = []
    if existed:
        probe = sqlite3.connect(store.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            probe.execute("PRAGMA foreign_keys=ON")
            _verify_pre_state(probe, migrations)
            recorded_versions = applied_versions(probe)
            for version, _, _, digest in migrations[:len(recorded_versions)]:
                row = probe.execute("SELECT migration_sha256, backup_manifest_sha256 FROM app_schema_migrations WHERE version=?", (version,)).fetchone()
                if row is None or row[0] != digest:
                    raise AppSchemaMismatchError("recorded migration identity drift")
                verify_retained_manifest(writable_roots.data_root, row[1])
            if recorded_versions:
                prior_structure = expected_schema_structure(migrations[:len(recorded_versions)])
                if schema_structure(probe) != prior_structure:
                    raise AppSchemaMismatchError("app schema constraint/structure drift before migration")
            if len(recorded_versions) == len(migrations):
                verify_app_schema(probe, expected_structure=expected_structure)
                return store
        finally:
            probe.close()
    # Per-migration pre-state evidence. The first pending migration records the
    # exact pre-invocation store state before the write connection mutates
    # anything; each later pending migration snapshots the committed state its
    # predecessor left behind. No-op startups retain nothing at all.
    pending_versions = [
        version for version, _, _, _ in migrations if version not in set(recorded_versions)
    ]
    backup_sha = None
    if pending_versions:
        backup_sha = retain_pre_migration_evidence(resources, writable_roots, store, existed)

    conn = connect_app_store(store, synchronous="FULL")
    try:
        _verify_pre_state(conn, migrations)
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

            if version != pending_versions[0]:
                backup_sha = retain_pre_migration_evidence(resources, writable_roots, store, True)

            sql_text = raw.decode("utf-8")

            conn.execute("BEGIN")
            try:
                for statement in _statements(sql_text):
                    conn.execute(statement)
                # Validate the migration created the exact expected table set for
                # the schema version it produces. Static review dicts cover
                # versions 1-2; offline test successors beyond the reviewed set
                # authenticate against structure derived from the verified
                # migration bytes themselves.
                expected_at_version = expected_schema_structure(migrations[:version])
                version_tables = {
                    name for kind, name, *_ in expected_at_version if kind == "columns"
                }
                for table in version_tables:
                    if table not in _table_names(conn):
                        raise AppSchemaMismatchError(
                            f"migration {logical_path} did not create table {table}"
                        )
                if _table_names(conn) != version_tables:
                    raise AppSchemaMismatchError("migration created an unexpected table set")
                for table, columns in _EXPECTED_APP_TABLES_BY_VERSION.get(version, {}).items():
                    if _table_columns(conn, table) != list(columns):
                        raise AppSchemaMismatchError("migration column identity drift")
                if schema_structure(conn) != expected_at_version:
                    raise AppSchemaMismatchError("migration constraint/structure drift")
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
        verify_app_schema(fresh, expected_structure=expected_structure)
    finally:
        fresh.close()
    return store
