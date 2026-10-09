"""Focused DATA-01C migrations, fail-closed projections, exports and recovery."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile

import pytest

from database.app_migrations import (
    APP_MIGRATIONS, app_store_path, apply_app_migrations, connect_app_store,
    current_schema_version, expected_app_tables, expected_schema_structure,
    read_app_migrations, schema_structure, verify_app_schema,
)
from database.app_repository import LOCAL_PROFILE_ID
from database.app_storage_access import app_store_connection
from domain.execution_envelope import ExecutionEnvelope
from domain.run_contracts import canonical_json_bytes
from runtime.resources import ResourceResolver, WritableRoots
from services.app_projection_service import (
    ProjectionDisposition, ProjectionSourceError, resolve_projection_source,
    verify_projection_tables_empty,
)
from services.backup_service import (
    BackupError, RestoreError, activate_staged_restore, create_backup,
    stage_indexed_backup, stage_restore_archive, verify_backup,
)
from services.export_service import (
    AuditEventError, ExportError, append_audit_event, create_run_export,
    read_audit_events, read_verified_export,
)
from test_data_01a_app_schema import (
    clock, make_stored_preview, open_repo, record_test_release, resources, roots,
)
from test_data_01b_durable_run_state import (
    _receipt, _running, development_durable,
)
from services.athena_preview_service import AdmissionCandidate
from database.run_repository import DurableRunRepository


def _terminal_with_untyped_leg(development_durable, clock):
    repo, candidate, verified_resources, verified_roots = development_durable
    run_id, attempt, lease = _running(repo, candidate)
    original = _receipt(repo, candidate, run_id, clock)
    opaque = {"opaque_selection": {"candidate": "legacy-mapping-with-no-reviewed-field-contract"}}
    receipt = replace(original, counts={"selected_leg_count": 1}, selected_legs=(opaque,),
                      shortfall=original.request.target_legs - 1)
    digest = repo.publish_terminal_receipt(
        run_id, expected_version=1, receipt_bytes=canonical_json_bytes(receipt),
        attempt_id=attempt, lease_token=lease,
    )
    assert repo.project_terminal_receipt(digest) is True
    return repo, candidate, verified_resources, verified_roots, run_id, attempt, lease, digest


def test_v3_schema_is_exact_six_table_delta_with_frozen_v1_v2(resources, roots):
    apply_app_migrations(resources, roots, release_id="test-release")
    migrations = read_app_migrations(resources)
    with connect_app_store(app_store_path(roots), readonly=True) as conn:
        verify_app_schema(conn, expected_structure=expected_schema_structure(migrations))
        assert current_schema_version(conn) == 3
        assert len(expected_app_tables(3)) == 20
        assert set(expected_app_tables(3)) - set(expected_app_tables(2)) == {
            "app_fixture_projections", "app_opportunity_projections", "app_portfolio_members",
            "app_exports", "app_backups", "app_audit_events",
        }
        assert schema_structure(conn) == expected_schema_structure(migrations)
        assert conn.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert "stake" not in {column.lower() for columns in expected_app_tables(3).values() for column in columns}
        assert "wager" not in {column.lower() for columns in expected_app_tables(3).values() for column in columns}
        fixture_fks = conn.execute("PRAGMA foreign_key_list(app_opportunity_projections)").fetchall()
        assert any(row[2] == "app_fixture_projections" and row[3] == "run_id"
                   and row[4] == "run_id" and row[6] == "RESTRICT" for row in fixture_fks)
        same_run_artifact_index = conn.execute("PRAGMA index_list(app_run_artifacts)").fetchall()
        assert any(row[1] == "app_run_artifacts_run_artifact_unique" and row[2] == 1
                   for row in same_run_artifact_index)


def test_populated_v2_to_v3_preserves_run_event_and_noop_migration_evidence(
        resources, roots, clock, monkeypatch):
    import database.app_migrations as migrations
    from domain.execution_envelope import ExecutionEnvelope
    all_migrations = migrations.APP_MIGRATIONS
    monkeypatch.setattr(migrations, "APP_MIGRATIONS", all_migrations[:2])
    app = open_repo(resources, roots)
    record_test_release(app, clock())
    _, item = make_stored_preview(resources, clock)
    envelope = ExecutionEnvelope.from_json_bytes(item.envelope_bytes)
    app.persist_preview_bundle(item=item, envelope=envelope, release_id="test-release",
                               profile_id=LOCAL_PROFILE_ID, now=clock())
    app.close()
    candidate = AdmissionCandidate(
        item.preview_id, item.request_bytes, envelope.request_sha256,
        item.envelope_bytes, envelope.canonical_sha256, "d5-v2-upgrade",
        envelope.authority_manifest_sha256,
        hashlib.sha256(canonical_json_bytes(envelope.source_identity)).hexdigest(),
        envelope.expires_at,
    )
    run_repo = DurableRunRepository(resources, roots, clock=clock)
    run_id = run_repo.admit(candidate).run_id
    attempt, lease, _number = run_repo.claim_attempt(
        run_id, worker_instance_id="d5-upgrade", process_locator={"kind": "OFFLINE_TEST", "label": "v2"})
    run_repo.transition_run(run_id, expected_version=0, state="RUNNING",
                            attempt_id=attempt, lease_token=lease)
    run_repo.append_event(run_id, attempt_id=attempt, lease_token=lease,
                          event_type="D5_V2_UPGRADE_FIXTURE", payload={"hash": "preserve-me"})
    with app_store_connection(resources, roots) as conn:
        before_run = conn.execute("SELECT run_id,request_sha256,envelope_sha256,state,state_version "
                                  "FROM app_runs WHERE run_id=?", (run_id,)).fetchone()
        before_events = conn.execute("SELECT sequence,event_type,payload_bytes,payload_sha256 "
                                     "FROM app_run_events WHERE run_id=? ORDER BY sequence", (run_id,)).fetchall()
        before_artifact_bytes = conn.execute("SELECT COUNT(*) FROM app_artifacts").fetchone()[0]
    monkeypatch.setattr(migrations, "APP_MIGRATIONS", all_migrations)
    apply_app_migrations(resources, roots, release_id="test-release")
    with app_store_connection(resources, roots) as conn:
        after_run = conn.execute("SELECT run_id,request_sha256,envelope_sha256,state,state_version "
                                 "FROM app_runs WHERE run_id=?", (run_id,)).fetchone()
        after_events = conn.execute("SELECT sequence,event_type,payload_bytes,payload_sha256 "
                                    "FROM app_run_events WHERE run_id=? ORDER BY sequence", (run_id,)).fetchall()
        assert conn.execute("SELECT COUNT(*) FROM app_artifacts").fetchone()[0] == before_artifact_bytes
    assert after_run == before_run
    assert after_events == before_events
    with connect_app_store(app_store_path(roots), readonly=True) as conn:
        assert current_schema_version(conn) == 3
    before_noop = sorted((path.relative_to(roots.data_root), path.read_bytes())
                         for path in (roots.data_root / "migration-evidence").rglob("*") if path.is_file())
    apply_app_migrations(resources, roots, release_id="test-release")
    after_noop = sorted((path.relative_to(roots.data_root), path.read_bytes())
                        for path in (roots.data_root / "migration-evidence").rglob("*") if path.is_file())
    assert after_noop == before_noop


def test_verified_generic_selected_leg_returns_typed_source_unavailable_and_writes_no_rows(
        development_durable, clock):
    repo, _candidate, verified_resources, verified_roots, run_id, _attempt, _lease, digest = \
        _terminal_with_untyped_leg(development_durable, clock)
    artifact_id = "receipt-" + digest
    before = repo.run_snapshot(run_id)
    result = resolve_projection_source(verified_resources, verified_roots,
                                       run_id=run_id, artifact_id=artifact_id)
    assert before["state"] == "TERMINAL"
    assert result.disposition is ProjectionDisposition.SOURCE_CONTRACT_UNAVAILABLE
    assert result.selected_leg_count == 1
    assert result.selected_leg_fields_typed is False
    assert result.materialized_rows == 0
    assert result.dependency == "E2/VERIFIED_DECISION_PROJECTION_SOURCE_CONTRACT"
    assert verify_projection_tables_empty(verified_resources, verified_roots)
    with app_store_connection(verified_resources, verified_roots) as conn:
        assert conn.execute("SELECT COUNT(*) FROM app_external_operations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM app_fixture_projections").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM app_opportunity_projections").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM app_portfolio_members").fetchone()[0] == 0


@pytest.mark.parametrize("case", ["wrong_type", "wrong_artifact", "unauthorized_role", "tampered_bytes"])
def test_projection_resolver_rejects_bad_identity_role_and_tamper(development_durable, clock, case):
    repo, _candidate, verified_resources, verified_roots, run_id, _attempt, _lease, digest = \
        _terminal_with_untyped_leg(development_durable, clock)
    artifact_id = "receipt-" + digest
    if case == "wrong_type":
        with pytest.raises(ProjectionSourceError):
            resolve_projection_source(verified_resources, verified_roots,
                                      run_id=run_id, artifact_id=17)
    elif case == "wrong_artifact":
        with pytest.raises(ProjectionSourceError):
            resolve_projection_source(verified_resources, verified_roots,
                                      run_id=run_id, artifact_id="receipt-" + "0" * 64)
    elif case == "unauthorized_role":
        with repo._operation(write=True) as conn:
            conn.execute("UPDATE app_run_artifacts SET role='EXTERNAL_RESPONSE' "
                         "WHERE run_id=? AND artifact_id=?", (run_id, artifact_id))
        with pytest.raises(ProjectionSourceError):
            resolve_projection_source(verified_resources, verified_roots,
                                      run_id=run_id, artifact_id=artifact_id)
    else:
        with repo._operation() as conn:
            locator = conn.execute("SELECT logical_path FROM app_artifacts WHERE artifact_id=?",
                                   (artifact_id,)).fetchone()[0]
        (verified_roots.data_root / locator).write_bytes(b"tampered")
        with pytest.raises(ProjectionSourceError):
            resolve_projection_source(verified_resources, verified_roots,
                                      run_id=run_id, artifact_id=artifact_id)
    assert verify_projection_tables_empty(verified_resources, verified_roots)


def test_redacted_export_and_append_only_audit_are_reauthenticated(development_durable, clock):
    repo, _candidate, verified_resources, verified_roots, run_id, _attempt, _lease, digest = \
        _terminal_with_untyped_leg(development_durable, clock)
    app = open_repo(verified_resources, verified_roots,
                    release_id=repo.run_snapshot(run_id)["release_id"])
    app.ensure_local_profile(now=clock())
    app.close()
    export_id = create_run_export(verified_resources, verified_roots,
                                  profile_id=LOCAL_PROFILE_ID, run_id=run_id, created_at=clock())
    archive = read_verified_export(verified_resources, verified_roots, export_id)
    with zipfile.ZipFile(__import__("io").BytesIO(archive), "r") as bundle:
        names = set(bundle.namelist())
        assert "run/request.json" in names
        assert "run/receipt.json" in names
        manifest = json.loads(bundle.read("manifest.json"))
        receipt = json.loads(bundle.read("run/receipt.json"))
        assert receipt["selected_legs"] == [{"opaque_selection": {
            "candidate": "legacy-mapping-with-no-reviewed-field-contract"}}]
        assert manifest["identity"]["run_id"] == run_id
        assert not any("cookie" in name.lower() or "secret" in name.lower() for name in names)
    audit_id = append_audit_event(verified_resources, verified_roots,
                                  event_type="D5_EXPORT_REVIEWED",
                                  payload={"export_id": export_id,
                                           "receipt_artifact_sha256": digest},
                                  run_id=run_id, created_at=clock())
    events = read_audit_events(verified_resources, verified_roots, run_id=run_id)
    event = next(item for item in events if item["audit_id"] == audit_id)
    assert event["payload_sha256"] == hashlib.sha256(
        canonical_json_bytes(event["payload"])).hexdigest()
    with app_store_connection(verified_resources, verified_roots, write=True) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("UPDATE app_audit_events SET event_type='MUTATED' WHERE audit_id=?", (audit_id,))
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM app_audit_events WHERE audit_id=?", (audit_id,))
    with pytest.raises(AuditEventError):
        append_audit_event(verified_resources, verified_roots,
                           event_type="D5_REJECT_SECRET",
                           payload={"session_cookie": "secret-cookie-value"},
                           run_id=run_id, created_at=clock())
    with app_store_connection(verified_resources, verified_roots) as conn:
        export_path = conn.execute("SELECT logical_path FROM app_exports WHERE export_id=?",
                                   (export_id,)).fetchone()[0]
    (verified_roots.data_root / export_path).write_bytes(b"corrupt archive")
    with pytest.raises(ExportError):
        read_verified_export(verified_resources, verified_roots, export_id)
    with repo._operation(write=True) as conn:
        conn.execute("UPDATE app_exports SET state='PREPARING' WHERE export_id=?", (export_id,))
    with pytest.raises(ExportError):
        read_verified_export(verified_resources, verified_roots, export_id)


def test_consistent_backup_contains_terminal_receipt_and_stages_before_activation(
        development_durable, clock):
    repo, _candidate, verified_resources, verified_roots, run_id, _attempt, _lease, digest = \
        _terminal_with_untyped_leg(development_durable, clock)
    release_id = repo.run_snapshot(run_id)["release_id"]
    before_db_sha = hashlib.sha256(app_store_path(verified_roots).read_bytes()).hexdigest()
    result = create_backup(verified_resources, verified_roots, release_id=release_id, created_at=clock())
    verified = verify_backup(verified_resources, verified_roots, result.backup_id)
    assert verified["manifest_byte_sha256"] == result.manifest_byte_sha256
    assert run_id in verified["app_run_ids"]
    receipt_member = "run-receipts/" + digest + ".json"
    assert any(row["logical_path"] == receipt_member for row in verified["manifest"]["referenced_evidence"])
    archive = verified_roots.data_root.parent / (verified_roots.data_root.name + ".backup-vault") / (result.backup_id + ".zip")
    with zipfile.ZipFile(archive) as bundle:
        snapshot_path = __import__("tempfile").NamedTemporaryFile(delete=False)
        snapshot_path.write(bundle.read("data/athena-app.sqlite3"))
        snapshot_path.close()
    try:
        snap = sqlite3.connect(snapshot_path.name)
        try:
            assert snap.execute("SELECT state FROM app_backups WHERE backup_id=?",
                                (result.backup_id,)).fetchone() == ("PREPARING",)
            assert snap.execute("SELECT run_id FROM app_runs WHERE run_id=?", (run_id,)).fetchone() == (run_id,)
        finally:
            snap.close()
    finally:
        Path(snapshot_path.name).unlink(missing_ok=True)
    staged = stage_indexed_backup(verified_resources, verified_roots, result.backup_id)
    assert staged.activation_eligible is True
    assert staged.terminal_producer_authentication == "NONE"
    assert hashlib.sha256(app_store_path(verified_roots).read_bytes()).hexdigest() != before_db_sha
    history = activate_staged_restore(verified_resources, verified_roots, staged)
    assert history.is_dir()
    with app_store_connection(verified_resources, verified_roots) as conn:
        assert conn.execute("SELECT run_id FROM app_runs WHERE run_id=?", (run_id,)).fetchone() == (run_id,)
        # A snapshot captures its own index as PREPARING; restore never upgrades
        # that pre-verification image to a false VERIFIED claim.
        assert conn.execute("SELECT state FROM app_backups WHERE backup_id=?",
                            (result.backup_id,)).fetchone() == ("PREPARING",)
    assert hashlib.sha256((history / "athena-app.sqlite3").read_bytes()).hexdigest() == before_db_sha


@pytest.mark.parametrize("attack", ["traversal", "duplicate_casefold", "symlink", "deflated"])
def test_restore_archive_adversaries_are_rejected_without_active_root_mutation(
        development_durable, clock, tmp_path, attack):
    repo, _candidate, verified_resources, verified_roots, run_id, _attempt, _lease, _digest = \
        _terminal_with_untyped_leg(development_durable, clock)
    result = create_backup(verified_resources, verified_roots,
                           release_id=repo.run_snapshot(run_id)["release_id"], created_at=clock())
    source = verified_roots.data_root.parent / (verified_roots.data_root.name + ".backup-vault") / (result.backup_id + ".zip")
    malicious = tmp_path / (attack + ".zip")
    with zipfile.ZipFile(source) as original:
        entries = [(item.filename, original.read(item.filename), item.external_attr)
                   for item in original.infolist()]
    with zipfile.ZipFile(malicious, "w") as altered:
        for index, (name, raw, external_attr) in enumerate(entries):
            if attack == "traversal" and index == 0:
                manifest = json.loads(raw)
                manifest["members"].append({"path": "data/../escape", "byte_sha256": hashlib.sha256(b"x").hexdigest(), "byte_count": 1})
                manifest["members"].sort(key=lambda row: row["path"])
                manifest["membership"]["member_count"] += 1
                manifest["membership"]["total_byte_count"] += 1
                manifest.pop("canonical_manifest_sha256", None)
                manifest["canonical_manifest_sha256"] = hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()
                raw = canonical_json_bytes(manifest)
            compression = zipfile.ZIP_STORED
            info = zipfile.ZipInfo(name)
            info.compress_type = compression
            info.external_attr = external_attr
            altered.writestr(info, raw)
            if attack == "duplicate_casefold" and index == 1:
                altered.writestr("data/ATHENA-APP.SQLITE3", raw)
            if attack == "symlink" and index == 1:
                link = zipfile.ZipInfo("data/link")
                link.compress_type = zipfile.ZIP_STORED
                link.external_attr = (0o120777 << 16)
                altered.writestr(link, b"target")
            if attack == "deflated" and index == 1:
                compressed = zipfile.ZipInfo("data/deflated")
                compressed.compress_type = zipfile.ZIP_DEFLATED
                altered.writestr(compressed, b"x" * 100)
    active_hash = hashlib.sha256(app_store_path(verified_roots).read_bytes()).hexdigest()
    with pytest.raises(RestoreError):
        stage_restore_archive(verified_resources, verified_roots, malicious)
    assert hashlib.sha256(app_store_path(verified_roots).read_bytes()).hexdigest() == active_hash
    assert not list(verified_roots.data_root.parent.glob(".dev-data.restore.*.staging"))


def test_export_default_redaction_rejects_credential_like_audit_values(resources, roots, clock):
    app = open_repo(resources, roots)
    record_test_release(app, clock())
    app.ensure_local_profile(now=clock())
    app.close()
    with pytest.raises(AuditEventError):
        append_audit_event(resources, roots, event_type="D5_REDACTION_NEGATIVE",
                           payload={"authorization": "Bearer abcdefghijklmnop"}, created_at=clock())
