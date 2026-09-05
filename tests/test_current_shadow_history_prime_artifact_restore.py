from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import current_shadow_history_github_persistent_cache as cache
from scripts import prime_current_shadow_history_github_cache as prime
from scripts import restore_current_shadow_history_prime_artifact as restore


ACTIONS_ENDPOINT = "/repos/Thabearr/ATHENA/actions/artifacts/123/zip"
RELEASE_ENDPOINT = "/repos/Thabearr/ATHENA/releases/assets/456"


def _build_prime_artifact(root: Path) -> tuple[Path, dict[str, object]]:
    artifact_dir = root / "artifact"
    history_cache = artifact_dir / "history-cache"
    cache._persist(history_cache, ACTIONS_ENDPOINT, b"artifact-zip-bytes")
    cache._persist(history_cache, RELEASE_ENDPOINT, b"release-asset-bytes")
    entry_count, payload_bytes, inventory_sha = prime._cache_inventory(history_cache)
    receipt: dict[str, object] = {
        "schema_version": prime.SCHEMA_VERSION,
        "status": prime.STATUS,
        "exact_commit_sha": "a" * 40,
        "captured_run_universe_count": 2,
        "cached_immutable_binary_entry_count": entry_count,
        "cached_immutable_binary_payload_bytes": payload_bytes,
        "cache_inventory_sha256": inventory_sha,
        "evidence_authority": False,
        "model_authority": False,
        "pricing_authority": False,
        "selection_authority": False,
        "execution_authority": False,
        "bet_authority": False,
        "wager_placed": False,
    }
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / restore.PRIME_RECEIPT_FILENAME).write_bytes(
        prime._canonical(receipt)
    )
    return artifact_dir, receipt


def test_verified_prime_artifact_restores_transport_cache(tmp_path) -> None:
    artifact_dir, receipt = _build_prime_artifact(tmp_path)
    destination = tmp_path / "restored-cache"

    result = restore.restore(artifact_dir=artifact_dir, cache_dir=destination)

    assert result["status"] == restore.RESTORE_STATUS
    assert result["restored_immutable_binary_entry_count"] == 2
    assert result["cache_inventory_sha256"] == receipt["cache_inventory_sha256"]
    assert cache._load(destination, ACTIONS_ENDPOINT) == b"artifact-zip-bytes"
    assert cache._load(destination, RELEASE_ENDPOINT) == b"release-asset-bytes"
    assert result["evidence_authority"] is False
    assert result["bet_authority"] is False
    assert result["wager_placed"] is False


def test_tampered_prime_payload_is_rejected_without_overwriting_destination(tmp_path) -> None:
    artifact_dir, _receipt = _build_prime_artifact(tmp_path)
    history_cache = artifact_dir / "history-cache"
    payload_path, _metadata_path = cache._paths(history_cache, ACTIONS_ENDPOINT)
    payload_path.write_bytes(b"tampered")
    destination = tmp_path / "restored-cache"
    destination.mkdir()
    sentinel = destination / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(
        restore.CurrentShadowPrimeArtifactRestoreError,
        match="payload integrity failed",
    ):
        restore.restore(artifact_dir=artifact_dir, cache_dir=destination)

    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_unexpected_prime_cache_file_is_rejected(tmp_path) -> None:
    artifact_dir, _receipt = _build_prime_artifact(tmp_path)
    (artifact_dir / "history-cache" / "unexpected.txt").write_text(
        "no",
        encoding="utf-8",
    )

    with pytest.raises(
        restore.CurrentShadowPrimeArtifactRestoreError,
        match="file count differs",
    ):
        restore.restore(
            artifact_dir=artifact_dir,
            cache_dir=tmp_path / "restored-cache",
        )


def test_prime_receipt_cannot_claim_authority(tmp_path) -> None:
    artifact_dir, _receipt = _build_prime_artifact(tmp_path)
    receipt_path = artifact_dir / restore.PRIME_RECEIPT_FILENAME
    value = json.loads(receipt_path.read_text(encoding="utf-8"))
    value["evidence_authority"] = True
    receipt_path.write_bytes(prime._canonical(value))

    with pytest.raises(
        restore.CurrentShadowPrimeArtifactRestoreError,
        match="attempted to claim authority",
    ):
        restore.restore(
            artifact_dir=artifact_dir,
            cache_dir=tmp_path / "restored-cache",
        )
