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
    expected_schema_structure,
    read_app_migrations,
    verify_app_schema,
)
from database.app_repository import AppRepository, AppValidationError, CAPABILITY_PROFILES, LOCAL_PROFILE_ID, release_provenance, logical_locator
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
def roots(tmp_path, resources):
    r = WritableRoots(
        data_root=tmp_path / "user-data",
        cache_root=tmp_path / "user-cache",
        state_root=tmp_path / "user-state",
        installed_release_root=resources.identity.release_root,
    )
    r.ensure_created()
    return r


@pytest.fixture
def clock():
    return MutableClock()


def open_repo(resources, roots, *, release_id="test-release"):
    return AppRepository.open(resources, roots, release_id=release_id)


def record_test_release(repo, now):
    repo.record_release_manifest(**release_provenance(repo.verified_identity, verified_at=now))


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
        verify_app_schema(conn, expected_structure=expected_schema_structure(read_app_migrations(resources)))
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
            verify_app_schema(conn, expected_structure=expected_schema_structure(read_app_migrations(resources)))
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
            verify_app_schema(conn, expected_structure=expected_schema_structure(read_app_migrations(resources)))
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
            verify_app_schema(conn, expected_structure=expected_schema_structure(read_app_migrations(resources)))
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
        repo.set_preference(profile_id=LOCAL_PROFILE_ID, preference_key="theme", value=value, updated_at=now)
        assert repo.get_preference(profile_id=LOCAL_PROFILE_ID, preference_key="theme") == value
    finally:
        repo.close()


def test_repository_fk_restrict_blocks_orphan_delete(resources, roots, clock):
    repo = open_repo(resources, roots)
    now = clock()
    conn = connect_app_store(app_store_path(roots), synchronous="FULL")
    try:
        pid = repo.ensure_local_profile(now=now)
        repo.set_preference(profile_id=pid, preference_key="page_size", value=1, updated_at=now)
        conn.execute("BEGIN")
        with pytest.raises(Exception):
            conn.execute("DELETE FROM app_profiles WHERE profile_id = ?", (pid,))
        conn.execute("ROLLBACK")
    finally:
        conn.close()
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
        conn = connect_app_store(app_store_path(roots), synchronous="FULL")
        conn.execute("BEGIN")
        conn.execute(
            "UPDATE app_run_previews SET request_bytes = ? WHERE preview_id = ?",
            (b'{"tampered": true}', stored.preview_id),
        )
        conn.execute("COMMIT")
        conn.close()
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
    assert hashlib.sha256(legacy.replace(b"\r\n", b"\n")).hexdigest() == "07470e07648698be11f0d3067e0f7cc72f6ca0540f9e7ec1472b9702f057c759"
    from database.app_migrations import APP_MIGRATIONS
    paths = [path for _, path in APP_MIGRATIONS]
    assert "database/migrations/0001_app_control_core.sql" in paths
    assert "database/migrations/002_add_elo_columns.sql" not in paths


@pytest.mark.parametrize("path", ["../x", "a/../x", "/abs/x", "C:\\x", "C:/x", "//server/share", "a//b", "a/./b", "a\x00b", "a\nb"])
def test_artifact_locator_rejects_unsafe_forms(path):
    with pytest.raises(AppValidationError):
        logical_locator(path)
    assert logical_locator("artifacts/local/report.json") == "artifacts/local/report.json"


@pytest.mark.parametrize("key", ["provider_acquisition", "run_admission_authority", "authority_profile", "create_share_code", "wager", "unknown"])
def test_preferences_reject_authority_keys(resources, roots, clock, key):
    with open_repo(resources, roots) as repo:
        repo.ensure_local_profile(now=clock())
        with pytest.raises(AppValidationError):
            repo.set_preference(profile_id=LOCAL_PROFILE_ID, preference_key=key, value=True, updated_at=clock())


def test_atomic_preview_failure_rolls_back_both_rows(resources, roots, clock, monkeypatch):
    _, item = make_stored_preview(resources, clock)
    with open_repo(resources, roots) as repo:
        record_test_release(repo, clock())
        store = DurablePreviewStore(repo, release_id="test-release")
        def fail():
            raise RuntimeError("injected between capability and preview")
        monkeypatch.setattr(repo, "_after_capability_insert", fail)
        with pytest.raises(RuntimeError):
            store.put(item, now=clock())
        conn = connect_app_store(app_store_path(roots), readonly=True)
        try:
            assert conn.execute("SELECT COUNT(*) FROM app_capability_snapshots").fetchone() == (0,)
            assert conn.execute("SELECT COUNT(*) FROM app_run_previews").fetchone() == (0,)
        finally:
            conn.close()
        monkeypatch.setattr(repo, "_after_capability_insert", lambda: None)
        store.put(item, now=clock())
        assert store.get(item.preview_id, now=clock()) == item


def test_release_manifest_corruption_is_rejected(resources, roots, clock):
    with open_repo(resources, roots) as repo:
        record_test_release(repo, clock())
        conn = connect_app_store(app_store_path(roots), synchronous="FULL")
        try:
            conn.execute("UPDATE app_release_manifests SET manifest_bytes = ?", (b"corrupt",))
        finally:
            conn.close()
        with pytest.raises(AppValidationError):
            record_test_release(repo, clock())


def test_preview_source_cannot_persist_under_other_release(resources, roots, clock):
    _, item = make_stored_preview(resources, clock)
    with open_repo(resources, roots) as repo:
        record_test_release(repo, clock())
        with pytest.raises(AppValidationError):
            DurablePreviewStore(repo, release_id="different-release").put(item, now=clock())
        assert repo.fetch_preview_record(item.preview_id) is None


def test_migration_evidence_absent_then_existing_backup(resources, roots):
    from database.app_migration_evidence import verify_retained_manifest, publish
    store = apply_app_migrations(resources, roots, release_id="test-release")
    conn = connect_app_store(store, readonly=True)
    try:
        digest = conn.execute("SELECT backup_manifest_sha256 FROM app_schema_migrations").fetchone()[0]
    finally:
        conn.close()
    absent = verify_retained_manifest(roots.data_root, digest)
    assert absent["app_store_state"] == "ABSENT" and absent["backup"] is None
    assert absent["ownership_inventory"]["roots"][0]["exists"] is False
    apply_app_migrations(resources, roots, release_id="test-release")
    manifests = list((roots.data_root / "migration-evidence").glob("*.json"))
    assert len(manifests) == 1
    assert str(roots.data_root) not in (roots.data_root / "migration-evidence" / (digest + ".json")).read_text()
    with pytest.raises(ValueError):
        publish(roots.data_root, "migration-evidence/" + digest + ".json", b"overwrite")


def test_failed_migration_preserves_evidence(resources, roots, monkeypatch):
    import database.app_migrations as migrations
    inject_migration_ddl_failure(monkeypatch, migrations)
    with pytest.raises(Exception):
        apply_app_migrations(resources, roots, release_id="test-release")
    assert list((roots.data_root / "migration-evidence").glob("*.json"))


def test_failed_existing_store_migration_preserves_openable_backup(resources, roots, monkeypatch):
    import sqlite3
    import database.app_migrations as migrations
    conn = sqlite3.connect(app_store_path(roots))
    conn.close()
    inject_migration_ddl_failure(monkeypatch, migrations)
    with pytest.raises(Exception):
        apply_app_migrations(resources, roots, release_id="test-release")
    from database.app_migration_evidence import verify_retained_manifest
    manifest = next((roots.data_root / "migration-evidence").glob("*.json"))
    value = verify_retained_manifest(roots.data_root, manifest.stem)
    assert value["app_store_state"] == "EXISTING"
    backup = roots.data_root / value["backup"]["logical_path"]
    conn = sqlite3.connect(backup.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        conn.close()


def test_evidence_directory_link_escape_fails(resources, roots, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (roots.data_root / "migration-evidence").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this platform")
    with pytest.raises(ValueError):
        apply_app_migrations(resources, roots, release_id="test-release")
    assert list(outside.iterdir()) == []
    assert not app_store_path(roots).exists()


def test_installed_inventory_never_adopts_repository_legacy_db(resources, roots):
    legacy = resources.identity.release_root.parent / "database" / "athena.db"
    legacy.parent.mkdir()
    legacy.write_bytes(b"legacy evidence must remain exact")
    apply_app_migrations(resources, roots, release_id="test-release")
    assert legacy.read_bytes() == b"legacy evidence must remain exact"
    from database.app_migration_evidence import verify_retained_manifest
    path = next((roots.data_root / "migration-evidence").glob("*.json"))
    inventory = verify_retained_manifest(roots.data_root, path.stem)["ownership_inventory"]
    assert len(inventory["roots"]) == 1
    assert inventory["roots"][0]["owner"] == "APP_CONTROL"


def test_verified_development_inventory_preserves_legacy_and_warehouse(tmp_path):
    import subprocess
    import sqlite3
    from runtime.release_identity import verify_development_checkout
    from database.app_migration_evidence import verify_retained_manifest
    checkout = tmp_path / "development"
    checkout.mkdir()
    for path in ("runtime/source_identity.py", "database/migrations/0001_app_control_core.sql"):
        target = checkout / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / path).read_bytes())
    (checkout / ".gitignore").write_text("database/*.db\n", encoding="utf-8")
    def git(*args):
        return subprocess.run(["git", "-c", "user.name=Moses Oluwasegun",
                               "-c", "user.email=113853913+Thabearr@users.noreply.github.com", "-C", str(checkout), *args],
                              check=True, capture_output=True)
    git("init", "--quiet")
    git("add", ".")
    git("commit", "--quiet", "-m", "D3 bounded database inventory fixture")
    paths = [checkout / "database/athena.db", checkout / "database/athena_history.db"]
    for path in paths:
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE preserved (value TEXT)")
        conn.execute("INSERT INTO preserved VALUES ('evidence')")
        conn.commit()
        conn.close()
    before = {p: p.read_bytes() for p in paths}
    identity = verify_development_checkout(checkout)
    resolver = ResourceResolver.for_development(identity)
    roots = WritableRoots(data_root=tmp_path / "data", cache_root=tmp_path / "cache", state_root=tmp_path / "state")
    apply_app_migrations(resolver, roots, release_id="development-checkout:" + identity.head_commit_sha)
    manifest = next((roots.data_root / "migration-evidence").glob("*.json"))
    inventory = verify_retained_manifest(roots.data_root, manifest.stem)["ownership_inventory"]
    assert {r["owner"] for r in inventory["roots"]} == {"APP_CONTROL", "LEGACY_OPERATIONAL", "HISTORICAL_WAREHOUSE"}
    assert all(p.read_bytes() == before[p] for p in paths)
    assert all(not row["migration_write_target"] for row in inventory["roots"][1:])


def test_source_a_cannot_persist_under_verified_source_b(resources, roots, clock, tmp_path):
    import json
    import shutil
    _, item = make_stored_preview(resources, clock)
    root_b = tmp_path / "other-release"
    shutil.copytree(resources.identity.release_root, root_b)
    value = json.loads((root_b / "release-manifest.json").read_bytes())
    value["release_id"] = "release-b"
    raw = canonical_release_manifest_bytes(value)
    (root_b / "release-manifest.json").write_bytes(raw)
    resources_b = ResourceResolver.for_installed(verify_installed_release(root_b, hashlib.sha256(raw).hexdigest()))
    roots_b = WritableRoots(data_root=roots.data_root, cache_root=roots.cache_root,
                            state_root=roots.state_root, installed_release_root=root_b)
    with open_repo(resources_b, roots_b, release_id="release-b") as repo:
        record_test_release(repo, clock())
        with pytest.raises(AppValidationError):
            DurablePreviewStore(repo, release_id="release-b").put(item, now=clock())
        assert repo.fetch_preview_record(item.preview_id) is None


def test_repository_close_is_idempotent_and_rejects_use(resources, roots):
    repo = open_repo(resources, roots)
    repo.close()
    repo.close()
    with pytest.raises(AppValidationError):
        repo.get_profile(LOCAL_PROFILE_ID)
    with open_repo(resources, roots) as restarted:
        assert restarted.get_profile(LOCAL_PROFILE_ID) is None


def test_actual_preview_threadpool_and_concurrent_requests(resources, roots, clock, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import get_ident
    from fastapi.testclient import TestClient
    from api.app_factory import create_app
    from runtime.local_session import LocalSession
    from services.athena_capability_service import AthenaCapabilityService
    from services.athena_read_service import AthenaReadService
    import socket
    import subprocess
    actions = []
    def forbidden(*args, **kwargs):
        actions.append("network-or-worker")
        pytest.fail("preview attempted provider/delivery/network/worker work")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    origin = "http://127.0.0.1:8765"
    session = LocalSession()
    owner_thread = get_ident()
    with open_repo(resources, roots) as repo:
        record_test_release(repo, clock())
        observed_threads = []
        repo._after_capability_insert = lambda: observed_threads.append(get_ident())
        store = DurablePreviewStore(repo, release_id="test-release")
        service = AthenaPreviewAdmissionService(resources, preview_store=store, clock=clock)
        app = create_app(release_identity=resources.identity, resource_resolver=resources,
                         writable_roots=roots, local_session=session,
                         capability_service=AthenaCapabilityService(resources, preview_admission_service=service),
                         preview_admission_service=service, read_service=AthenaReadService.unavailable(), origin=origin)
        headers = {"Host": "127.0.0.1:8765", "Origin": origin, "X-Athena-Session": session.credential()}
        body = {"dates": [PREVIEW_DATE], "target_legs": 3, "target_total_odds": None,
                "bookie": "sportybet", "profile": "main", "acquire_sources": False, "create_share_code": False}
        with TestClient(app) as client:
            def preview(_):
                response = client.post("/api/v1/run-previews", headers=headers, json=body)
                assert response.status_code == 200, response.text
                return response.json()
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(preview, range(2)))
            refused = client.post("/api/v1/runs", headers=headers, json={
                "preview_id": results[0]["preview_id"],
                "execution_envelope_sha256": results[0]["execution_envelope_sha256"],
                "idempotency_key": "d3-must-not-admit",
            })
            assert "DURABLE_RUN_STORE_UNAVAILABLE" in refused.text
            assert refused.status_code != 200
        assert observed_threads and all(t != owner_thread for t in observed_threads)
        for result in results:
            assert store.get(result["preview_id"], now=clock()) is not None
    with open_repo(resources, roots) as reopened:
        restarted = DurablePreviewStore(reopened, release_id="test-release")
        for result in results:
            assert restarted.get(result["preview_id"], now=clock()) is not None
    assert actions == []


def inject_migration_ddl_failure(monkeypatch, migrations):
    original_connect = migrations.connect_app_store
    original_statements = migrations._statements
    writing = [False]
    def connect(*args, **kwargs):
        writing[0] = not kwargs.get("readonly", False)
        return original_connect(*args, **kwargs)
    monkeypatch.setattr(migrations, "connect_app_store", connect)
    monkeypatch.setattr(migrations, "_statements", lambda sql: ["INVALID SQL"] if writing[0] else original_statements(sql))


def evidence_files(roots):
    return {p.relative_to(roots.data_root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (roots.data_root / "migration-evidence").rglob("*") if p.is_file()}


def test_noop_startups_never_retain_new_evidence(resources, roots, clock):
    from database.app_migration_evidence import verify_retained_manifest
    _, item = make_stored_preview(resources, clock)
    with open_repo(resources, roots) as repo:
        record_test_release(repo, clock())
        DurablePreviewStore(repo, release_id="test-release").put(item, now=clock())
    before = evidence_files(roots)
    for _ in range(5):
        with open_repo(resources, roots) as repo:
            assert DurablePreviewStore(repo, release_id="test-release").get(item.preview_id, now=clock()) == item
        assert evidence_files(roots) == before
    conn = connect_app_store(app_store_path(roots), readonly=True)
    try:
        digest = conn.execute("SELECT backup_manifest_sha256 FROM app_schema_migrations").fetchone()[0]
    finally:
        conn.close()
    assert verify_retained_manifest(roots.data_root, digest)["app_store_state"] == "ABSENT"


@pytest.mark.parametrize("fail", [False, True])
def test_only_pending_version_retains_consistent_backup(resources, roots, monkeypatch, fail):
    import database.app_migrations as migrations
    from database.app_migration_evidence import verify_retained_manifest
    import sqlite3
    apply_app_migrations(resources, roots, release_id="test-release")
    before = evidence_files(roots)
    future = b"CREATE INDEX test_only_future_profile_name ON app_profiles(display_name);"
    logical = "database/migrations/test_only_future.sql"
    original_read = ResourceResolver.read_bytes
    def read(self, path, **kwargs):
        if path == logical:
            assert kwargs["expected_role"] == "MIGRATION"
            return future
        return original_read(self, path, **kwargs)
    monkeypatch.setattr(ResourceResolver, "read_bytes", read)
    monkeypatch.setattr(migrations, "APP_MIGRATIONS", migrations.APP_MIGRATIONS + ((2, logical),))
    if fail:
        original_connect = migrations.connect_app_store
        original_statements = migrations._statements
        writing = [False]
        def connect(*args, **kwargs):
            writing[0] = not kwargs.get("readonly", False)
            return original_connect(*args, **kwargs)
        def statements(sql):
            if writing[0] and "test_only_future_profile_name" in sql:
                return ["INVALID INJECTED DDL"]
            return original_statements(sql)
        monkeypatch.setattr(migrations, "connect_app_store", connect)
        monkeypatch.setattr(migrations, "_statements", statements)
        with pytest.raises(sqlite3.Error):
            apply_app_migrations(resources, roots, release_id="test-release")
    else:
        apply_app_migrations(resources, roots, release_id="test-release")
    added = set(evidence_files(roots)) - set(before)
    manifests = [p for p in added if p.count("/") == 1 and p.endswith(".json")]
    backups = [p for p in added if p.endswith(".sqlite3")]
    assert len(manifests) == len(backups) == 1
    digest = Path(manifests[0]).stem
    manifest = verify_retained_manifest(roots.data_root, digest)
    snapshot = sqlite3.connect((roots.data_root / manifest["backup"]["logical_path"]).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        assert snapshot.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert snapshot.execute("SELECT version FROM app_schema_migrations").fetchall() == [(1,)]
    finally:
        snapshot.close()
    conn = connect_app_store(app_store_path(roots), readonly=True)
    try:
        assert conn.execute("SELECT version FROM app_schema_migrations ORDER BY version").fetchall() == ([(1,)] if fail else [(1,), (2,)])
        if not fail:
            assert conn.execute("SELECT backup_manifest_sha256 FROM app_schema_migrations WHERE version=2").fetchone() == (digest,)
    finally:
        conn.close()
    if not fail:
        retained = evidence_files(roots)
        apply_app_migrations(resources, roots, release_id="test-release")
        assert evidence_files(roots) == retained


@pytest.mark.parametrize("table,old,new", [
    ("app_run_previews", ",\n    FOREIGN KEY (capability_snapshot_id) REFERENCES app_capability_snapshots(snapshot_id) ON DELETE RESTRICT", ""),
    ("app_favorites", ",\n    CHECK (entity_kind IN ('competition', 'market'))", ""),
    ("app_artifacts", "    UNIQUE (logical_path),\n", ""),
    ("app_run_previews", "ON DELETE RESTRICT", "ON DELETE CASCADE"),
    ("app_profiles", "display_name TEXT NOT NULL", "display_name INTEGER NOT NULL"),
    ("app_profiles", "display_name TEXT NOT NULL", "display_name TEXT"),
])
def test_constraint_tampering_same_columns_refuses_open(resources, roots, table, old, new):
    import sqlite3
    apply_app_migrations(resources, roots, release_id="test-release")
    conn = sqlite3.connect(app_store_path(roots))
    try:
        sql = conn.execute("SELECT sql FROM sqlite_schema WHERE name=?", (table,)).fetchone()[0]
        assert old in sql
        before_columns = conn.execute('PRAGMA table_info("' + table + '")').fetchall()
        conn.execute('DROP TABLE "' + table + '"')
        conn.execute(sql.replace(old, new))
        conn.commit()
        assert [r[1] for r in before_columns] == [r[1] for r in conn.execute('PRAGMA table_info("' + table + '")')]
    finally:
        conn.close()
    before = evidence_files(roots)
    with pytest.raises(AppSchemaMismatchError, match="structure drift"):
        open_repo(resources, roots)
    assert evidence_files(roots) == before


@pytest.mark.parametrize("sql", ["CREATE VIEW unreviewed AS SELECT * FROM app_profiles", "CREATE TRIGGER unreviewed AFTER INSERT ON app_profiles BEGIN SELECT 1; END"])
def test_unreviewed_schema_objects_refuse_open(resources, roots, sql):
    import sqlite3
    apply_app_migrations(resources, roots, release_id="test-release")
    conn = sqlite3.connect(app_store_path(roots))
    try:
        conn.execute(sql)
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(AppSchemaMismatchError, match="structure drift"):
        open_repo(resources, roots)
