"""Native PORT-02C resource, process-lock and restore-journal qualification."""
from __future__ import annotations

import multiprocessing
from pathlib import Path
import sqlite3
import uuid

import pytest

from database.app_migrations import APP_MIGRATIONS
from database.app_root_lock import app_root_lock
from scripts.port_02c_build_config import SLICE_RESOURCES
from services.backup_service import _activate_generation


ROOT = Path(__file__).resolve().parents[2]


def test_native_slice_stages_v3_migration_role_and_exact_20_table_schema():
    paths = [path for _, path in APP_MIGRATIONS]
    assert paths == [
        "database/migrations/0001_app_control_core.sql",
        "database/migrations/0002_app_runs_operations.sql",
        "database/migrations/0003_app_projections_exports.sql",
    ]
    for path in paths:
        assert SLICE_RESOURCES.count((path, "MIGRATION")) == 1
    assert "database/migrations/002_add_elo_columns.sql" not in paths
    assert SLICE_RESOURCES.count(("database/migrations/002_add_elo_columns.sql", "MIGRATION")) == 1
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        for path in paths:
            conn.executescript((ROOT / path).read_text(encoding="utf-8"))
        names = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        assert len(names) == 20
        assert {
            "app_fixture_projections", "app_opportunity_projections", "app_portfolio_members",
            "app_exports", "app_backups", "app_audit_events",
        } <= names
        projection_fks = conn.execute("PRAGMA foreign_key_list(app_opportunity_projections)").fetchall()
        assert any(row[2] == "app_fixture_projections" and row[3:5] ==
                   ("run_id", "run_id") and row[6] == "RESTRICT" for row in projection_fks)
        scoped_index = conn.execute(
            "PRAGMA index_list(app_run_artifacts)").fetchall()
        assert any(row[1] == "app_run_artifacts_run_artifact_unique" and row[2] == 1
                   for row in scoped_index)
        assert conn.execute("PRAGMA foreign_keys").fetchone() == (1,)
    finally:
        conn.close()


def _wait_for_lock(data_root, attempting, acquired):
    attempting.set()
    with app_root_lock(data_root):
        acquired.set()


def test_cross_process_app_root_lock_excludes_a_second_writer(tmp_path):
    root = tmp_path / "user-data"
    root.mkdir()
    context = multiprocessing.get_context("spawn")
    attempting = context.Event()
    acquired = context.Event()
    process = context.Process(target=_wait_for_lock, args=(str(root), attempting, acquired))
    with app_root_lock(root):
        process.start()
        assert attempting.wait(10)
        assert not acquired.wait(0.25)
    assert acquired.wait(10)
    process.join(10)
    assert process.exitcode == 0


@pytest.mark.parametrize("crash_phase", [
    "JOURNAL_PREPARED", "OLD_ROOT_PRESERVED", "NEW_ROOT_ACTIVE",
])
def test_native_same_volume_switch_recovers_each_crash_marker(tmp_path, crash_phase):
    root = tmp_path / "data"
    root.mkdir()
    (root / "generation.txt").write_text("old", encoding="utf-8")
    token = uuid.uuid4().hex
    stage = tmp_path / f".data.restore.{token}.staging"
    stage.mkdir()
    (stage / "generation.txt").write_text("new", encoding="utf-8")

    def crash(marker):
        if marker == crash_phase:
            raise RuntimeError("synthetic process interruption at " + marker)

    with pytest.raises(RuntimeError, match="synthetic process interruption"):
        with app_root_lock(root):
            _activate_generation(root, stage, "a" * 64, phase_hook=crash)
    # Taking the same OS lock on the next process entry performs journal
    # recovery before any store operation can see a partial root.
    with app_root_lock(root):
        assert (root / "generation.txt").read_text(encoding="utf-8") == "old"
    assert not (tmp_path / ".data.restore-journal.json").exists()
    if crash_phase == "NEW_ROOT_ACTIVE":
        failed = list(tmp_path.glob(".data.failed.*"))
        assert len(failed) == 1
        assert (failed[0] / "generation.txt").read_text(encoding="utf-8") == "new"
