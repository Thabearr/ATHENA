from __future__ import annotations

import hashlib
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def test_primary_continuity_dispatch_authenticates_completed_watchdog_before_state() -> None:
    workflow = (
        _repo_root() / ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
    ).read_text(encoding="utf-8")

    auth = workflow.index("- name: Authenticate continuity dispatch source")
    state = workflow.index("- name: Restore newest durable lineage and resolve schedule slot")
    execute = workflow.index("- name: Execute reviewed fresh-holdout collection tick")

    assert auth < state < execute
    assert "if: github.event_name == 'workflow_dispatch'" in workflow[auth:state]
    assert 'source_run.get("status") == "completed"' in workflow[auth:state]
    assert 'source_run.get("conclusion") != "success"' in workflow[auth:state]
    assert "/jobs?per_page=100" in workflow[auth:state]
    assert "continuity.validate_watchdog_source_run(" in workflow[auth:state]
    assert "continuity.validate_watchdog_source_jobs(" in workflow[auth:state]


def test_continuity_run_name_preserves_dispatch_inputs_outside_canonical_receipt() -> None:
    workflow = (
        _repo_root() / ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
    ).read_text(encoding="utf-8")
    first_lines = "\n".join(workflow.splitlines()[:4])
    assert "run-name: ATHENA fresh-holdout ${{ github.event_name }}" in first_lines
    assert "source=${{ inputs.continuity_source_watchdog_run_id }}" in first_lines
    assert "target=${{ inputs.continuity_target_slot }}" in first_lines
    assert "cron=${{ inputs.continuity_target_cron }}" in first_lines
    assert "confirm=${{ inputs.continuity_confirmation }}" in first_lines


def test_watchdog_pins_exact_current_primary_continuity_workflow_blob() -> None:
    root = _repo_root()
    primary = root / ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
    watchdog = (
        root / ".github/workflows/watch-fotmob-fresh-holdout-scheduler-liveness.yml"
    ).read_text(encoding="utf-8")
    expected = _git_blob_sha(primary)
    assert (
        'git rev-parse HEAD:.github/workflows/fotmob-utc-native-xg-fresh-holdout.yml)" '
        f'= "{expected}"'
    ) in watchdog
