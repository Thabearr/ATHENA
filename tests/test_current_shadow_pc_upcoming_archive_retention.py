"""Offline regression tests for the legacy Current Shadow source-evidence repair."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

import pytest

from domain import current_shadow_sportybet_pc_upcoming_discovery as source
from scripts.verify_current_shadow_pc_upcoming_archive import (
    PcUpcomingArchiveError,
    verify_archive,
)


def _build(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    repository = tmp_path / "repo"
    output = repository / "artifacts/current-shadow-all-market"
    original = repository / source.EVIDENCE_ROOT
    preserved = output / "source-evidence" / source.EVIDENCE_ROOT.name
    original.mkdir(parents=True)
    observed = datetime.now(timezone.utc)
    nonce = int(observed.timestamp() * 1000)
    raw = b'{"bizCode":10000,"data":{"totalNum":0,"tournaments":[]}}'
    page = source.parse_page(
        raw, page_num=1, request_nonce_ms=nonce, observed_at=observed
    )
    manifest = source.build_manifest((page,))
    (original / "pages").mkdir()
    (original / "pages/page-001.raw.json").write_bytes(raw)
    (original / "manifest.json").write_bytes(
        source._canonical(manifest.to_dict(), newline=True)
    )
    (original / "runtime-capture-stabilization.json").write_bytes(b'{"retained":true}')
    (original / "runtime-attempts/attempt-001/raw-responses").mkdir(parents=True)
    (original / "runtime-attempts/attempt-001/raw-responses/page-001.raw.json").write_bytes(raw)
    output.mkdir(parents=True)
    (output / "current-shadow-all-market-run-receipt.json").write_text(
        json.dumps({
            "status": "RESEARCH_SHADOW_PORTFOLIO_READY_WITH_SHORTFALL",
            "source_summary": {
                "provider_discovery_manifest_sha256": manifest.canonical_sha256,
                "provider_discovery_page_count": 1,
                "provider_discovery_event_count": 0,
                "provider_discovery_pagination_complete": True,
            }
        }), encoding="utf-8"
    )
    preserved.parent.mkdir(parents=True)
    shutil.copytree(original, preserved)
    return repository, output, original, preserved


def test_workflow_preserves_live_pc_upcoming_root_and_invokes_audit():
    workflow = Path(".github/workflows/current-shadow-all-market.yml").read_text(
        encoding="utf-8"
    )
    source_path = f".cache/athena-research/{source.EVIDENCE_ROOT.name}"
    assert source_path == source.EVIDENCE_ROOT.as_posix()
    preservation = workflow.split("- name: Preserve exact current source evidence", 1)[1]
    preservation = preservation.split("- name: Email durable Shadow result", 1)[0]
    assert source_path in preservation
    assert "cp -a \"${source_dir}\" \"${evidence_root}/\"" in preservation
    assert "python -m scripts.verify_current_shadow_pc_upcoming_archive" in preservation
    assert "if: always()" in preservation
    assert "name: current-shadow-all-market-request" in workflow
    assert "retention-days: 30" in workflow


def test_complete_archive_replays_exact_page_and_retains_capture_epoch(tmp_path):
    repository, output, original, preserved = _build(tmp_path)
    result = verify_archive(repository_root=repository, output_root=output)
    assert result["status"] == "VERIFIED_COMPLETE"
    assert result["file_count"] == 4
    assert (preserved / "runtime-attempts/attempt-001/raw-responses/page-001.raw.json").read_bytes() == (
        original / "runtime-attempts/attempt-001/raw-responses/page-001.raw.json"
    ).read_bytes()


@pytest.mark.parametrize("relative", [
    "manifest.json",
    "pages/page-001.raw.json",
    "runtime-capture-stabilization.json",
    "runtime-attempts/attempt-001/raw-responses/page-001.raw.json",
])
def test_archive_omission_cannot_pass(tmp_path, relative):
    repository, output, _original, preserved = _build(tmp_path)
    (preserved / relative).unlink()
    with pytest.raises(PcUpcomingArchiveError):
        verify_archive(repository_root=repository, output_root=output)


def test_archive_raw_tampering_cannot_pass(tmp_path):
    repository, output, _original, preserved = _build(tmp_path)
    (preserved / "pages/page-001.raw.json").write_bytes(b"modified")
    with pytest.raises(PcUpcomingArchiveError, match="byte-inconsistent"):
        verify_archive(repository_root=repository, output_root=output)


def test_claimed_discovery_without_source_or_archive_fails_closed(tmp_path):
    repository, output, original, preserved = _build(tmp_path)
    shutil.rmtree(original)
    shutil.rmtree(preserved)
    with pytest.raises(PcUpcomingArchiveError, match="absent"):
        verify_archive(repository_root=repository, output_root=output)


def test_source_not_started_does_not_create_false_archive(tmp_path):
    repository = tmp_path / "repo"
    output = repository / "artifacts/current-shadow-all-market"
    output.mkdir(parents=True)
    assert verify_archive(repository_root=repository, output_root=output) == {
        "status": "NOT_ACQUIRED", "file_count": 0
    }


def test_partial_epoch_retained_without_inventing_complete_discovery(tmp_path):
    repository, output, original, preserved = _build(tmp_path)
    (original / "manifest.json").unlink()
    (preserved / "manifest.json").unlink()
    (output / "current-shadow-all-market-run-receipt.json").write_text(
        json.dumps({"status": "RESEARCH_NO_CODE_SOURCE_INCOMPLETE", "source_summary": {}}),
        encoding="utf-8",
    )
    assert verify_archive(repository_root=repository, output_root=output)["status"] == "VERIFIED_PARTIAL_CAPTURE"
    (preserved / "pages/page-001.raw.json").unlink()
    with pytest.raises(PcUpcomingArchiveError, match="incomplete"):
        verify_archive(repository_root=repository, output_root=output)


def test_archive_symlink_is_rejected(tmp_path):
    repository, output, _original, preserved = _build(tmp_path)
    (preserved / "runtime-attempts/evil").symlink_to(preserved / "manifest.json")
    with pytest.raises(PcUpcomingArchiveError, match="nonregular"):
        verify_archive(repository_root=repository, output_root=output)
