"""D4 native-bundle resource regression; no worker or transport actions."""
from pathlib import Path
import sqlite3

from database.app_migrations import APP_MIGRATIONS
from scripts.port_02c_build_config import SLICE_RESOURCES

ROOT = Path(__file__).resolve().parents[2]


def test_native_slice_stages_all_three_reviewed_app_migrations():
    paths = [path for _, path in APP_MIGRATIONS]
    assert paths == ["database/migrations/0001_app_control_core.sql",
                     "database/migrations/0002_app_runs_operations.sql",
                     "database/migrations/0003_app_projections_exports.sql"]
    for path in paths:
        assert SLICE_RESOURCES.count((path, "MIGRATION")) == 1
    assert not any("002_add_elo_columns.sql" in path for path in paths)
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        for path in paths:
            conn.executescript((ROOT / path).read_text(encoding="utf-8"))
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        assert len(names) == 20
        assert {"app_runs", "app_run_attempts", "app_run_events",
                "app_external_operations", "app_run_artifacts"} <= names
    finally:
        conn.close()
