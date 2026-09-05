"""Restore a verified Current Shadow history transport cache from a prime artifact.

The prime artifact is transport-only.  Restoring it never grants evidence, model,
pricing, selection, execution, or wager authority.  Every cached entry is checked
against its canonical endpoint metadata and SHA-256 before it is admitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Mapping

from scripts import current_shadow_history_github_persistent_cache as cache
from scripts import prime_current_shadow_history_github_cache as prime


PRIME_RECEIPT_FILENAME = "current-shadow-history-cache-prime-receipt.json"
PRIME_STATUS = "CURRENT_SHADOW_HISTORY_TRANSPORT_CACHE_PRIMED_NO_EVIDENCE_AUTHORITY"
RESTORE_STATUS = "CURRENT_SHADOW_HISTORY_TRANSPORT_CACHE_ARTIFACT_RESTORED_NO_EVIDENCE_AUTHORITY"
_AUTHORITY_FIELDS = (
    "evidence_authority",
    "model_authority",
    "pricing_authority",
    "selection_authority",
    "execution_authority",
    "bet_authority",
    "wager_placed",
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "exact_commit_sha",
        "captured_run_universe_count",
        "cached_immutable_binary_entry_count",
        "cached_immutable_binary_payload_bytes",
        "cache_inventory_sha256",
        *_AUTHORITY_FIELDS,
    }
)


class CurrentShadowPrimeArtifactRestoreError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _hex(value: Any, length: int) -> bool:
    return (
        type(value) is str
        and len(value) == length
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _read_receipt(artifact_dir: Path) -> dict[str, Any]:
    path = artifact_dir / PRIME_RECEIPT_FILENAME
    try:
        if path.is_symlink() or not path.is_file():
            raise CurrentShadowPrimeArtifactRestoreError("prime receipt is unavailable")
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CurrentShadowPrimeArtifactRestoreError("prime receipt is unreadable") from exc
    if type(value) is not dict or _canonical(value) != raw:
        raise CurrentShadowPrimeArtifactRestoreError("prime receipt is not canonical")
    if set(value) != _RECEIPT_FIELDS:
        raise CurrentShadowPrimeArtifactRestoreError("prime receipt fields drifted")
    if value["schema_version"] != prime.SCHEMA_VERSION or value["status"] != PRIME_STATUS:
        raise CurrentShadowPrimeArtifactRestoreError("prime receipt identity drifted")
    if not _hex(value["exact_commit_sha"], 40):
        raise CurrentShadowPrimeArtifactRestoreError("prime receipt commit SHA is invalid")
    for field in ("captured_run_universe_count", "cached_immutable_binary_entry_count"):
        if type(value[field]) is not int or value[field] <= 0:
            raise CurrentShadowPrimeArtifactRestoreError(f"prime receipt {field} is invalid")
    if (
        type(value["cached_immutable_binary_payload_bytes"]) is not int
        or value["cached_immutable_binary_payload_bytes"] <= 0
        or not _hex(value["cache_inventory_sha256"], 64)
    ):
        raise CurrentShadowPrimeArtifactRestoreError("prime receipt cache inventory is invalid")
    if any(value[field] is not False for field in _AUTHORITY_FIELDS):
        raise CurrentShadowPrimeArtifactRestoreError("prime artifact attempted to claim authority")
    return value


def _validate_cache_tree(source: Path, receipt: Mapping[str, Any]) -> None:
    if source.is_symlink() or not source.is_dir():
        raise CurrentShadowPrimeArtifactRestoreError("prime history-cache directory is unavailable")

    files = sorted(source.iterdir(), key=lambda path: path.name)
    expected_count = receipt["cached_immutable_binary_entry_count"]
    if len(files) != expected_count * 2:
        raise CurrentShadowPrimeArtifactRestoreError("prime cache file count differs from receipt")
    if any(
        path.is_symlink()
        or not path.is_file()
        or path.suffix not in {".json", ".payload"}
        or not _hex(path.stem, 64)
        for path in files
    ):
        raise CurrentShadowPrimeArtifactRestoreError("prime cache contains an unexpected file")

    metadata_files = [path for path in files if path.suffix == ".json"]
    payload_files = [path for path in files if path.suffix == ".payload"]
    if len(metadata_files) != expected_count or len(payload_files) != expected_count:
        raise CurrentShadowPrimeArtifactRestoreError("prime cache metadata/payload cardinality differs")
    if {path.stem for path in metadata_files} != {path.stem for path in payload_files}:
        raise CurrentShadowPrimeArtifactRestoreError("prime cache metadata/payload pairing differs")

    for metadata_path in metadata_files:
        try:
            raw = metadata_path.read_bytes()
            metadata = json.loads(raw)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CurrentShadowPrimeArtifactRestoreError("prime cache metadata is unreadable") from exc
        if type(metadata) is not dict or _canonical(metadata) != raw:
            raise CurrentShadowPrimeArtifactRestoreError("prime cache metadata is not canonical")
        if set(metadata) != {
            "schema_version",
            "endpoint",
            "payload_sha256",
            "payload_size_bytes",
        }:
            raise CurrentShadowPrimeArtifactRestoreError("prime cache metadata fields drifted")
        endpoint = metadata.get("endpoint")
        digest = metadata.get("payload_sha256")
        size = metadata.get("payload_size_bytes")
        if (
            metadata.get("schema_version") != cache.CACHE_SCHEMA_VERSION
            or type(endpoint) is not str
            or cache._IMMUTABLE_BINARY_ENDPOINT.fullmatch(endpoint) is None
            or not _hex(digest, 64)
            or type(size) is not int
            or size <= 0
        ):
            raise CurrentShadowPrimeArtifactRestoreError("prime cache metadata is invalid")
        expected_payload, expected_metadata = cache._paths(source, endpoint)
        if expected_metadata != metadata_path:
            raise CurrentShadowPrimeArtifactRestoreError("prime cache endpoint key is inconsistent")
        try:
            payload = expected_payload.read_bytes()
        except OSError as exc:
            raise CurrentShadowPrimeArtifactRestoreError("prime cache payload is unreadable") from exc
        if len(payload) != size or hashlib.sha256(payload).hexdigest() != digest:
            raise CurrentShadowPrimeArtifactRestoreError("prime cache payload integrity failed")

    entry_count, payload_bytes, inventory_sha = prime._cache_inventory(source)
    if (
        entry_count != receipt["cached_immutable_binary_entry_count"]
        or payload_bytes != receipt["cached_immutable_binary_payload_bytes"]
        or inventory_sha != receipt["cache_inventory_sha256"]
    ):
        raise CurrentShadowPrimeArtifactRestoreError("prime cache inventory differs from receipt")


def restore(*, artifact_dir: Path, cache_dir: Path) -> dict[str, Any]:
    artifact_dir = artifact_dir.resolve()
    cache_dir = cache_dir.resolve()
    source = artifact_dir / "history-cache"
    receipt = _read_receipt(artifact_dir)
    _validate_cache_tree(source, receipt)

    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_dir.parent / f".{cache_dir.name}.prime-artifact-restore.tmp"
    if temporary.exists():
        if temporary.is_dir() and not temporary.is_symlink():
            shutil.rmtree(temporary)
        else:
            temporary.unlink()
    shutil.copytree(source, temporary)
    _validate_cache_tree(temporary, receipt)

    if cache_dir.exists():
        if cache_dir.is_dir() and not cache_dir.is_symlink():
            shutil.rmtree(cache_dir)
        else:
            cache_dir.unlink()
    os.replace(temporary, cache_dir)

    return {
        "schema_version": 1,
        "status": RESTORE_STATUS,
        "source_prime_commit_sha": receipt["exact_commit_sha"],
        "restored_immutable_binary_entry_count": receipt["cached_immutable_binary_entry_count"],
        "restored_immutable_binary_payload_bytes": receipt["cached_immutable_binary_payload_bytes"],
        "cache_inventory_sha256": receipt["cache_inventory_sha256"],
        "evidence_authority": False,
        "model_authority": False,
        "pricing_authority": False,
        "selection_authority": False,
        "execution_authority": False,
        "bet_authority": False,
        "wager_placed": False,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = restore(artifact_dir=args.artifact_dir, cache_dir=args.cache_dir)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
