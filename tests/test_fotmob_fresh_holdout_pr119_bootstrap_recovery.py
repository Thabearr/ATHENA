from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess

from domain import fotmob_utc_native_expected_goals_fresh_holdout as fresh
from scripts import qualify_fotmob_historical_source_history_completeness_materialization as pr119


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
PR119_EXECUTOR = (
    "scripts/qualify_fotmob_historical_source_history_completeness_materialization.py"
)
PR119_EXECUTOR_BLOB = "2409676b4993a25024e2e8554e84e3525e7c5e6e"
PR119_ARTIFACT_ID = "9249856559"
PR119_ARTIFACT_SHA256 = (
    "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"
)
PR119_ARTIFACT_SIZE = 61_886_753
PR119_RECEIPT_SHA256 = (
    "da8037cd9b4a4f91be942a4052e76134b66cc94221ed66e624c14008c9e562a0"
)
PR119_RECEIPT_SIZE = 6_810
BOOTSTRAP_SHA256 = "e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2"
BOOTSTRAP_SIZE = 10_545_099
BOOTSTRAP_ROWS = 21_326


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _git_blob(path: str) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", f"HEAD:{path}"],
        cwd=ROOT,
        text=True,
    ).strip()


def test_frozen_pr119_bootstrap_identities_still_match_reviewed_sources() -> None:
    assert _git_blob(PR119_EXECUTOR) == PR119_EXECUTOR_BLOB
    assert pr119.MATERIALIZATION_PROJECTION_SHA256 == BOOTSTRAP_SHA256
    assert pr119.MATERIALIZATION_PROJECTION_SIZE == BOOTSTRAP_SIZE
    assert pr119.EXPECTED_RECEIPT_SHA256 == PR119_RECEIPT_SHA256
    assert pr119.EXPECTED_RECEIPT_SIZE == PR119_RECEIPT_SIZE
    assert fresh.BOOTSTRAP_PROJECTION_SHA256 == BOOTSTRAP_SHA256
    assert fresh.BOOTSTRAP_PROJECTION_SIZE == BOOTSTRAP_SIZE
    assert fresh.BOOTSTRAP_PROJECTION_ROWS == BOOTSTRAP_ROWS


def test_workflow_replays_exact_pr119_executor_from_preserved_artifact_zip() -> None:
    text = _workflow_text()
    assert f'artifact_id = "{PR119_ARTIFACT_ID}"' in text
    assert f'expected_artifact_sha = "{PR119_ARTIFACT_SHA256}"' in text
    assert f"expected_artifact_size = {PR119_ARTIFACT_SIZE:_}" in text
    assert f'executor = "{PR119_EXECUTOR}"' in text
    assert f'expected_executor_blob = "{PR119_EXECUTOR_BLOB}"' in text
    assert f'expected_receipt_sha = "{PR119_RECEIPT_SHA256}"' in text
    assert f"expected_receipt_size = {PR119_RECEIPT_SIZE:_}" in text
    assert '["git", "rev-parse", f"HEAD:{executor}"]' in text
    assert '"--projection-output", str(target)' in text
    assert '"--output", str(receipt_path)' in text
    assert "preserved PR119 artifact ZIP identity changed" in text
    assert "replayed PR119 materialization receipt identity changed" in text


def test_workflow_no_longer_assumes_materialized_ndjson_is_inside_pr119_zip() -> None:
    text = _workflow_text()
    forbidden = (
        "preserved_pr119/database/market_evidence/",
        "fotmob_data_matches_epl_historical_raw_features.ndjson",
        "archive.extractall",
        "source ndjson missing from PR119 artifact",
    )
    for value in forbidden:
        assert value not in text


def test_bootstrap_is_verified_before_collection_and_cache_publish_is_not_authority() -> None:
    text = _workflow_text()
    bootstrap_start = text.index("- name: Restore or materialize PR119 bootstrap projection")
    execute_start = text.index("- name: Execute reviewed fresh-holdout collection tick")
    bootstrap = text[bootstrap_start:execute_start]
    assert "hashlib.sha256(raw).hexdigest() != expected_sha" in bootstrap
    assert "len(raw) != expected_size" in bootstrap
    assert 'rows != expected_rows' in bootstrap
    assert '"--clobber", "--repo", repo' in bootstrap
    assert "check=False" in bootstrap
    assert "--execute-live-network" not in bootstrap
    assert "curl " not in bootstrap
    assert "wget " not in bootstrap


def test_prebootstrap_failure_packaging_uses_resolved_shell_identity_without_python_nameerror() -> None:
    text = _workflow_text()
    package_start = text.index("- name: Package durable state archive")
    upload_start = text.index("- name: Upload authoritative 90-day Actions artifact")
    package = text[package_start:upload_start]
    assert 'if [ -z "${NOMINAL_SLOT:-}" ]; then' in package
    assert 'tar_name="${FAILURE_ASSET}"' in package
    assert 'tar_path = Path("${tar_name}")' in package
    assert 'f"packaged {tar_path.name}: sha256={tar_sha} size={tar_size}"' in package
    assert 'f"packaged {tar_name}:' not in package
    assert 'receipt_data["tick_committed"] = "${TICK_EXIT:-1}" == "0"' in package
    assert 'echo "archive_name=${tar_name}" >> "${GITHUB_OUTPUT}"' in package


def test_pr175_does_not_change_schedule_or_backfill_authority() -> None:
    text = _workflow_text()
    assert "- cron: '7 * * * *'" in text
    assert "- cron: '37 * * * *'" in text
    # PR262 adds only the fail-closed prospective continuity dispatch surface;
    # it does not turn the historical collector into a manually runnable source.
    assert "workflow_dispatch:" in text
    for required_input in (
        "continuity_source_watchdog_run_id:",
        "continuity_target_slot:",
        "continuity_target_cron:",
        "continuity_confirmation:",
    ):
        assert required_input in text
        assert text.index(required_input) < text.index("concurrency:")
    assert "required: true" in text
    assert '"PROSPECTIVE_ONLY_NO_BACKFILL_V1"' in text
    assert "continuity.validate_watchdog_source_run(" in text
    assert "continuity.validate_watchdog_source_jobs(" in text
    assert "continuity.validate_continuity_dispatch(" in text
    assert "current_main = subprocess.check_output(" in text
    assert "checkout_head != current_main" in text
    assert "Exact future :07/:37 UTC slot derived from the watchdog run" in text
    assert "refusing to fabricate a nominal slot or backfill evidence" in text
    assert "CONTINUITY_ALREADY_ATTEMPTED_NO_ACQUISITION" in text
    assert "--execute-live-network" in text
    assert text.count("--execute-live-network") == 1
    assert "backfill_authorized: true" not in text
    assert "backfill_authorized = True" not in text
    assert "rerun" not in text.lower()
