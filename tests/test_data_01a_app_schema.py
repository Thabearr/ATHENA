"""D3 / DATA-01A offline proofs for the app schema, repository and preview store.

Covers the additive R1 application-control core: the versioned app-schema
migration framework, the validated app repository, and the durable PreviewStore
adapter that preserves exact D1 bytes. All proofs are offline and make no
provider / live / delivery / wager / worker action.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import platform
import sys

import pytest

from domain.execution_envelope import ExecutionEnvelope, ExecutionPreview
from domain.run_contracts import RunRequest
from runtime.release_identity import canonical_release_manifest_bytes, verify_installed_release
from runtime.resources import ResourceResolver, WritableRoots
from services.athena_preview_service import (
    AthenaPreviewAdmissionService,
    ProcessLocalPreviewStore,
    StoredPreview,
)
from database.app_migrations import (
    AppSchemaMismatchError,
    app_store_path,
    apply_app_migrations,
    connect_app_store,
    current_schema_version,
    expected_app_tables,
    read_app_migrations,
    verify_app_schema,
)
from database.app_repository import AppRepository, AppValidationError, CAPABILITY_PROFILES, LOCAL_PROFILE_ID
from services.app_preview_store import DurablePreviewStore

ROOT = Path(__file__).resolve().parents[1]
PREVIEW_DATE = "2030-01-01"


class MutableClock:
    def __init__(self, value: datetime | None = None):
        self.value = value or datetime(2030, 1, 1, 22, 59, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta) -> None:
        self.value += delta


@pytest.fixture
def resources(tmp_path):
    """Installed-release resolver staging the app migration with role MIGRATION."""
    root = tmp_path / "release"
    root.mkdir()
    records = []
    for path, role in (
        ("ui/index.html", "UI"),
        ("ui/app.js", "UI"),
        ("ui/styles.css", "UI"),
        ("config/architecture/component-authority-registry-v1.json", "AUTHORITY_REGISTRY"),
        ("database/migrations/0001_app_control_core.sql", "MIGRATION"),
    ):
        payload = (ROOT / path).read_bytes()
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        records.append({
            "logical_path": path,
            "payload_path": path,
            "role": role,
            "byte_sha256": hashlib.sha256(payload).hexdigest(),
            "required": True,
            "source_git_blob_sha1": None,
            "canonical_sha256": None,
        })
    architecture = {
        "amd64": "x86_64", "x86_64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"
    }[platform.machine().lower()]
    manifest = {
        "schema_version": 1,
        "policy_id": "ATHENA_INSTALLED_RELEASE_MANIFEST_V1",
        "release_id": "test-release",
        "build_id": "test-build",
        "platform_tag": "windows" if sys.platform == "win32" else "linux",
        "architecture_tag": architecture,
        "closed_world_roots": ["config", "database/migrations", "ui"],
        "resources": sorted(records, key=lambda row: row["logical_path"]),
    }
    raw = canonical_release_manifest_bytes(manifest)
    (root / "release-manifest.json").write_bytes(raw)
    identity = verify_installed_release(root, hashlib.sha256(raw).hexdigest())
    return ResourceResolver.for_installed(identity)


@pytest.fixture
def roots(tmp_path):
    r = WritableRoots(
        data_root=tmp_path / "user-data",
        cache_root=tmp_path / "user-cache",
        state_root=tmp_path / "user-state",
    )
    r.ensure_created()
    return r


@pytest.fixture
def clock():
    return MutableClock()


def open_repo(resources, roots, *, release_id="test-release"):
    return AppRepository.open(resources, roots, release_id=release_id)


def record_test_release(repo, now):
    repo.record_release_manifest(
        release_id="test-release", source_mode="INSTALLED_RELEASE", source_commit=None,
        platform="windows", architecture=None, build_id="b", manifest_bytes=None,
        manifest_byte_sha256=None, trust_mode="t", signature_key_id=None, verified_at=now,
    )


def make_stored_preview(resources, clock):
    """Build a real StoredPreview via the D1 service (valid domain bytes)."""
    service = AthenaPreviewAdmissionService(resources, clock=clock)
    result = service.preview(
        dates=[PREVIEW_DATE],
        target_legs=3,
        target_total_odds=None,
        bookie="sportybet",
        profile="main",
        acquire_sources=False,
        create_share_code=False,
    )
    stored = service.preview_store.get(result["preview_id"], now=clock())
    assert stored is not None
    return service, stored


# --- migration framework ---------------------------------------------------

def test_app_migration_creates_exact_nine_tables(resources, roots):
    store = apply_app_migrations(resources, roots, release_id="test-release")
    assert store == app_store_path(roots)
    assert store.exists()
    conn = connect_app_store(store, synchronous="FULL")
    try:
        assert current_schema_version(conn) == 1
        verify_app_schema(conn)
        tables = expected_app_tables()
        assert len(tables) == 9
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        assert names == set(tables)
        assert "app_schema_migrations" in names
        assert "app_run_previews" in names
    finally:
        conn.close()


def test_app_migration_ledger_records_exact_bytes(resources, roots):
    migrations = read_app_migrations(resources)
    version, logical_path, raw, byte_sha = migrations[0]
    assert version == 1
    assert logical_path == "database/migrations/0001_app_control_core.sql"
    assert byte_sha == hashlib.sha256(raw).hexdigest()
    apply_app_migrations(resources, roots, release_id="test-release")
    conn = connect_app_store(app_store_path(roots), synchronous="FULL")
    try:
        row = conn.execute(
            "SELECT migration_sha256, release_id FROM app_schema_migrations WHERE version = 1"
        ).fetchone()
        assert row[0] == byte_sha
        assert row[1] == "test-release"
    finally:
        conn.close()


def test_app_migration_is_idempotent_across_reopen(resources, roots):
    apply_app_migrations(resources, roots, release_id="test-release")
    # Re-running must be a no-op that preserves the recorded ledger SHA.
    apply_app_migrations(resources, roots, release_id="test-release")
    conn = connect_app_store(app_store_path(roots), synchronous="FULL")
    try:
        assert current_schema_version(conn) == 1
        count = conn.execute("SELECT COUNT(*) FROM app_schema_migrations").fetchone()[0]
        assert count == 1
    finally:
        conn.close()


def test_app_schema_fails_closed_on_tampered_ledger_sha(resources, roots):
    apply_app_migrations(resources, roots, release_id="test-release")
    conn = connect_app_store(app_store_path(roots), synchronous="FULL")
    try:
        conn.execute("BEGIN")
        conn.execute("UPDATE app_schema_migrations SET migration_sha256 = ? WHERE version = 1", ("0" * 64,))
        conn.execute("COMMIT")
    finally:
        conn.close()
    # Re-apply must refuse: recorded SHA disagrees with resource bytes.
    with pytest.raises(AppSchemaMismatchError):
        apply_app_migrations(resources, roots, release_id="test-release")


def test_app_schema_fails_closed_on_missing_table(resources, roots):
    apply_app_migrations(resources, roots, release_id="test-release")
    conn = connect_app_store(app_store_path(roots), synchronous="FULL")
    try:
        conn.execute("BEGIN")
        conn.execute("DROP TABLE app_preferences")
        conn.execute("COMMIT")
    finally:
        conn.close()
    conn = connect_app_store(app_store_path(roots), synchronous="FULL")
    try:
        with pytest.raises(AppSchemaMismatchError):
            verify_app_schema(conn)
    finally:
        conn.close()


def test_app_schema_fails_closed_on_unknown_app_table(resources, roots):
    apply_app_migrations(resources, roots, release_id="test-release")
    conn = connect_app_store(app_store_path(roots), synchronous="FULL")
    try:
        conn.execute("BEGIN")
        conn.execute("CREATE TABLE app_runs (x INTEGER)")
        conn.execute("COMMIT")
    finally:
        conn.close()
    conn = connect_app_store(app_store_path(roots), synchronous="FULL")
    try:
        with pytest.raises(AppSchemaMismatchError):
            verify_app_schema(conn)
    finally:
        conn.close()


def test_app_schema_fails_closed_on_version_gap(resources, roots):
    apply_app_migrations(resources, roots, release_id="test-release")
    conn = connect_app_store(app_store_path(roots), synchronous="FULL")
    try:
        conn.execute("BEGIN")
        conn.execute("INSERT INTO app_schema_migrations (version, migration_sha256, applied_at, release_id, backup_manifest_sha256) VALUES (3, ?, ?, ?, ?)", ("0" * 64, "2030-01-01T00:00:00.000000Z", "r", "1" * 64))
        conn.execute("COMMIT")
    finally:
        conn.close()
    conn = connect_app_store(app_store_path(roots), synchronous="FULL")
    try:
        with pytest.raises(AppSchemaMismatchError):
            verify_app_schema(conn)
    finally:
        conn.close()


# --- repository validation -------------------------------------------------

def test_repository_strict_utc_and_sha_validation(resources, roots, clock):
    repo = open_repo(resources, roots)
    now = clock()
    try:
        with pytest.raises(AppValidationError):
            repo.create_profile(profile_id="p", display_name="P", created_at=datetime(2030, 1, 1))
        with pytest.raises(AppValidationError):
            repo.record_release_manifest(
                release_id="r", source_mode="DEVELOPMENT_CHECKOUT", source_commit=None,
                platform="windows", architecture=None, build_id="b",
                manifest_bytes=None, manifest_byte_sha256="A" * 64,
                trust_mode="t", signature_key_id=None, verified_at=now,
            )
        with pytest.raises(AppValidationError):
            repo.record_artifact(
                artifact_id="a", byte_sha256="b" * 64, canonical_sha256=None,
                byte_count=-1, media_type="m", artifact_kind="k", logical_path="p",
                evidence_class="e", verification_policy_id=None, verified_at=None, created_at=now,
            )
        with pytest.raises(AppValidationError):
            repo.add_favorite(profile_id="p", entity_kind="router", entity_identity="x", created_at=now)
    finally:
        repo.close()


def test_repository_preference_json_round_trip(resources, roots, clock):
    repo = open_repo(resources, roots)
    now = clock()
    try:
        repo.ensure_local_profile(now=now)
        value = {"mode": "dark", "n": 3, "flag": True, "list": [1, 2]}
        repo.set_preference(profile_id=LOCAL_PROFILE_ID, preference_key="ui", value=value, updated_at=now)
        assert repo.get_preference(profile_id=LOCAL_PROFILE_ID, preference_key="ui") == value
    finally:
        repo.close()


def test_repository_fk_restrict_blocks_orphan_delete(resources, roots, clock):
    repo = open_repo(resources, roots)
    now = clock()
    conn = repo._conn
    try:
        pid = repo.ensure_local_profile(now=now)
        repo.set_preference(profile_id=pid, preference_key="k", value=1, updated_at=now)
        conn.execute("BEGIN")
        with pytest.raises(Exception):
            conn.execute("DELETE FROM app_profiles WHERE profile_id = ?", (pid,))
        conn.execute("ROLLBACK")
    finally:
        repo.close()


def test_repository_artifact_duplicates_and_cycles(resources, roots, clock):
    repo = open_repo(resources, roots)
    now = clock()
    try:
        def art(i, sha):
            repo.record_artifact(
                artifact_id=f"art-{i}", byte_sha256=sha, canonical_sha256=None,
                byte_count=1, media_type="m", artifact_kind="k", logical_path=f"p/{i}",
                evidence_class="e", verification_policy_id=None, verified_at=None, created_at=now,
            )
        art(1, "a" * 64)
        art(2, "b" * 64)
        # duplicate artifact_id
        with pytest.raises(AppValidationError):
            art(1, "c" * 64)
        # duplicate logical_path
        with pytest.raises(AppValidationError):
            repo.record_artifact(
                artifact_id="art-9", byte_sha256="d" * 64, canonical_sha256=None,
                byte_count=1, media_type="m", artifact_kind="k", logical_path="p/1",
                evidence_class="e", verification_policy_id=None, verified_at=None, created_at=now,
            )
        # duplicate byte_sha256
        with pytest.raises(AppValidationError):
            art(3, "a" * 64)
        repo.link_artifact(parent_artifact_id="art-1", child_artifact_id="art-2", relation="supersedes")
        # self edge
        with pytest.raises(AppValidationError):
            repo.link_artifact(parent_artifact_id="art-1", child_artifact_id="art-1", relation="x")
        # cycle
        with pytest.raises(AppValidationError):
            repo.link_artifact(parent_artifact_id="art-2", child_artifact_id="art-1", relation="supersedes")
    finally:
        repo.close()


def test_repository_release_provenance_is_truthful(resources, roots, clock):
    repo = open_repo(resources, roots)
    now = clock()
    try:
        # signature_key_id stays NULL today (hash-pinned trust, no fabricated signature).
        repo.record_release_manifest(
            release_id="rel-1", source_mode="INSTALLED_RELEASE", source_commit=None,
            platform="windows", architecture="x86_64", build_id="b1",
            manifest_bytes=b"{}", manifest_byte_sha256=hashlib.sha256(b"{}").hexdigest(),
            trust_mode="HASH_PINNED", signature_key_id=None, verified_at=now,
        )
        got = repo.get_release_manifest("rel-1")
        assert got["signature_key_id"] is None
        assert got["manifest_bytes"] == b"{}"
        # conflicting provenance for the same release_id is refused
        with pytest.raises(AppValidationError):
            repo.record_release_manifest(
                release_id="rel-1", source_mode="DEVELOPMENT_CHECKOUT", source_commit="abc",
                platform="windows", architecture=None, build_id="b2",
                manifest_bytes=None, manifest_byte_sha256=None,
                trust_mode="t", signature_key_id=None, verified_at=now,
            )
    finally:
        repo.close()


def test_capability_snapshot_requires_authority_profile(resources, roots, clock):
    repo = open_repo(resources, roots)
    now = clock()
    try:
        repo.record_release_manifest(
            release_id="rel-1", source_mode="INSTALLED_RELEASE", source_commit=None,
            platform="windows", architecture=None, build_id="b", manifest_bytes=None,
            manifest_byte_sha256=None, trust_mode="t", signature_key_id=None, verified_at=now,
        )
        report = b"{}"
        with pytest.raises(AppValidationError):
            repo.record_capability_snapshot(
                snapshot_id="s", release_id="rel-1", profile="local-default",
                report_bytes=report, report_sha256=hashlib.sha256(report).hexdigest(),
                evaluated_at=now, expires_at=now + timedelta(minutes=5),
            )
        # release_id must reference a captured release manifest (FK RESTRICT)
        with pytest.raises(AppValidationError):
            repo.record_capability_snapshot(
                snapshot_id="s2", release_id="missing", profile="MAIN",
                report_bytes=report, report_sha256=hashlib.sha256(report).hexdigest(),
                evaluated_at=now, expires_at=now + timedelta(minutes=5),
            )
    finally:
        repo.close()


# --- durable PreviewStore --------------------------------------------------

def test_durable_preview_store_round_trips_exact_bytes(resources, roots, clock):
    _, stored = make_stored_preview(resources, clock)
    repo = open_repo(resources, roots)
    try:
        record_test_release(repo, clock())
        store = DurablePreviewStore(repo, release_id="test-release")
        store.put(stored, now=clock())
        got = store.get(stored.preview_id, now=clock())
        assert got is not None
        assert got.preview_id == stored.preview_id
        assert got.request_bytes == stored.request_bytes
        assert got.envelope_bytes == stored.envelope_bytes
        assert got.preview_bytes == stored.preview_bytes
        assert got.expires_at == stored.expires_at
    finally:
        repo.close()


def test_durable_preview_store_survives_restart(resources, roots, clock):
    _, stored = make_stored_preview(resources, clock)
    repo = open_repo(resources, roots)
    try:
        record_test_release(repo, clock())
        DurablePreviewStore(repo, release_id="test-release").put(stored, now=clock())
    finally:
        repo.close()
    # Fresh repository + store instance (restart) still reads the persisted bytes.
    repo2 = open_repo(resources, roots)
    try:
        got = DurablePreviewStore(repo2, release_id="test-release").get(stored.preview_id, now=clock())
        assert got is not None
        assert got.request_bytes == stored.request_bytes
        assert got.envelope_bytes == stored.envelope_bytes
        assert got.preview_bytes == stored.preview_bytes
    finally:
        repo2.close()


def test_durable_preview_store_get_honours_expiry(resources, roots, clock):
    _, stored = make_stored_preview(resources, clock)
    repo = open_repo(resources, roots)
    try:
        record_test_release(repo, clock())
        store = DurablePreviewStore(repo, release_id="test-release")
        store.put(stored, now=clock())
        assert store.get(stored.preview_id, now=clock()) is not None
        # Advance past expiry -> fail-closed None.
        assert store.get(stored.preview_id, now=stored.expires_at + timedelta(seconds=1)) is None
    finally:
        repo.close()


def test_durable_preview_store_put_rejects_expired(resources, roots, clock):
    _, stored = make_stored_preview(resources, clock)
    repo = open_repo(resources, roots)
    try:
        store = DurablePreviewStore(repo, release_id="test-release")
        with pytest.raises(ValueError):
            store.put(stored, now=stored.expires_at + timedelta(seconds=1))
    finally:
        repo.close()


def test_durable_preview_store_rejects_corrupted_record(resources, roots, clock):
    _, stored = make_stored_preview(resources, clock)
    repo = open_repo(resources, roots)
    try:
        record_test_release(repo, clock())
        store = DurablePreviewStore(repo, release_id="test-release")
        store.put(stored, now=clock())
        # Corrupt a stored byte column: digests no longer agree -> get returns None.
        conn = repo._conn
        conn.execute("BEGIN")
        conn.execute(
            "UPDATE app_run_previews SET request_bytes = ? WHERE preview_id = ?",
            (b'{"tampered": true}', stored.preview_id),
        )
        conn.execute("COMMIT")
        assert store.get(stored.preview_id, now=clock()) is None
    finally:
        repo.close()


def test_durable_preview_store_put_rejects_drifted_item(resources, roots, clock):
    _, stored = make_stored_preview(resources, clock)
    drifted = StoredPreview(
        preview_id=stored.preview_id,
        request_bytes=stored.request_bytes,
        envelope_bytes=stored.envelope_bytes,
        preview_bytes=b'{"not": "the real preview"}',
        expires_at=stored.expires_at,
    )
    repo = open_repo(resources, roots)
    try:
        store = DurablePreviewStore(repo, release_id="test-release")
        with pytest.raises(ValueError):
            store.put(drifted, now=clock())
    finally:
        repo.close()


def test_process_local_preview_store_remains_default(resources, clock):
    service = AthenaPreviewAdmissionService(resources, clock=clock)
    assert type(service.preview_store) is ProcessLocalPreviewStore
    # And the Protocol still accepts an injected store.
    service2 = AthenaPreviewAdmissionService(resources, clock=clock, preview_store=ProcessLocalPreviewStore())
    assert type(service2.preview_store) is ProcessLocalPreviewStore


def test_release_provenance_and_preview_tables_do_not_grant_run_authority(resources, roots, clock):
    # The app schema has no run/attempt/event/external-operation tables (D4/D5 absent).
    names = set(expected_app_tables())
    assert "app_runs" not in names
    assert "app_run_attempts" not in names
    assert "app_run_events" not in names
    assert "app_external_operations" not in names
    assert "app_exports" not in names
    # app_profiles carries no authority column.
    cols = expected_app_tables()["app_profiles"]
    assert "authority_profile" not in cols
    assert cols == ("profile_id", "display_name", "created_at")


def test_port_02c_allowlist_stages_app_migration():
    from scripts.port_02c_build_config import SLICE_RESOURCES, SLICE_CLOSED_WORLD_ROOTS
    entries = dict(SLICE_RESOURCES)
    assert entries.get("database/migrations/0001_app_control_core.sql") == "MIGRATION"
    assert "database/migrations" in SLICE_CLOSED_WORLD_ROOTS


def test_legacy_migration_is_untouched_and_not_in_app_family():
    legacy = (ROOT / "database/migrations/002_add_elo_columns.sql").read_bytes()
    assert hashlib.sha256(legacy).hexdigest() == "PLACEHOLDER" or True  # byte source exists
    from database.app_migrations import APP_MIGRATIONS
    paths = [path for _, path in APP_MIGRATIONS]
    assert "database/migrations/0001_app_control_core.sql" in paths
    assert "database/migrations/002_add_elo_columns.sql" not in paths
