from __future__ import annotations

from pathlib import Path

import pytest

from domain.ingest_contracts import AthenaIngestRequest, strict_json_loads
from services.athena_ingest_service import ARTIFACT_RELATIVE, execute_ingest_request
from scripts.replay_athena_ingest_artifact import AthenaIngestReplayError, replay_ingest_artifact
from tests.test_athena_ingest_service import fake_response


def _artifact(tmp_path: Path) -> tuple[Path, list[str]]:
    calls: list[str] = []
    def acquire(*, request_date: str, timezone: str, ccode3: str):
        calls.append(request_date)
        return fake_response(request_date)
    receipt = execute_ingest_request(
        AthenaIngestRequest.for_dates(("20260901", "20260902")),
        repository_root=tmp_path, acquisition_callable=acquire,
    )
    assert receipt.status == "SUCCESS"
    return tmp_path / ARTIFACT_RELATIVE, calls


def test_two_date_artifact_replays_without_acquisition(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, calls = _artifact(tmp_path)
    assert calls == ["20260901", "20260902"]
    def no_network(*args, **kwargs):
        raise AssertionError("network attempted during offline replay")
    monkeypatch.setattr("scripts.capture_fotmob_data_matches.fetch_fotmob_data_matches", no_network)
    result = replay_ingest_artifact(root)
    assert result["status"] == "ATHENA_INGEST_OFFLINE_REPLAY_VERIFIED"
    assert result["source_count"] == 2
    assert result["provider_request_count"] == 0
    assert result["network_acquisition_performed"] is False
    assert calls == ["20260901", "20260902"]


@pytest.mark.parametrize("filename", [
    "resolved-ingest-request.json", "canonical-store-update.json",
    "ingest-receipt.json", "replay-manifest.json",
])
def test_top_level_mutation_fails(tmp_path: Path, filename: str) -> None:
    root, _ = _artifact(tmp_path)
    target = root / filename
    target.write_bytes(target.read_bytes()[:-2] + b"x}\n")
    with pytest.raises((AthenaIngestReplayError, ValueError)):
        replay_ingest_artifact(root)


def test_raw_manifest_and_symlink_mutations_fail(tmp_path: Path) -> None:
    root, _ = _artifact(tmp_path)
    update = strict_json_loads((root / "canonical-store-update.json").read_bytes())
    capture = root / update["source_records"][0]["capture_relative_path"]
    raw = capture / "response.json"
    original = raw.read_bytes()
    raw.write_bytes(original + b" ")
    with pytest.raises((AthenaIngestReplayError, ValueError)):
        replay_ingest_artifact(root)
    raw.write_bytes(original)
    manifest = capture / "manifest.json"
    original_manifest = manifest.read_bytes()
    manifest.write_bytes(original_manifest + b" ")
    with pytest.raises((AthenaIngestReplayError, ValueError)):
        replay_ingest_artifact(root)
    manifest.write_bytes(original_manifest)
    raw.unlink()
    try:
        raw.symlink_to(root / "resolved-ingest-request.json")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(AthenaIngestReplayError):
        replay_ingest_artifact(root)
