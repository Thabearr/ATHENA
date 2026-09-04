"""Persistent transport cache for immutable Current Shadow history GitHub bytes.

The reviewed latest-history builder remains authoritative: it still requests every
GitHub value through the same recorder surface and replays the resulting evidence
exactly.  This module only persists immutable binary transport payloads underneath
that recorder between hosted Current Shadow runs so the cumulative PR151 history
cannot become progressively slower as the campaign grows.

Only Actions artifact ZIP endpoints and immutable Release asset endpoints are
eligible.  Mutable JSON metadata is never persisted.  Cache corruption, stale
metadata, or an unrecognised endpoint causes a normal live GitHub read; cache
contents never grant evidence, model, pricing, selection, execution, or BET
authority.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from typing import Any

from scripts import current_shadow_history_github_prefetch as prefetch


CACHE_SCHEMA_VERSION = 1
CACHE_ENV = "ATHENA_CURRENT_SHADOW_HISTORY_CACHE_DIR"
DEFAULT_CACHE_DIR = Path(
    ".cache/athena-research/current-shadow-history-github-binary-cache-v1"
)
_IMMUTABLE_BINARY_ENDPOINT = re.compile(
    r"^/repos/Thabearr/ATHENA/(?:actions/artifacts/[1-9][0-9]*/zip|releases/assets/[1-9][0-9]*)$"
)


@dataclasses.dataclass(frozen=True)
class PersistentHistoryGitHubCacheHooks:
    original_gh_download: Any
    cached_disk_download: Any
    prefetch_hooks: prefetch.HistoryGitHubPrefetchHooks


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


def _cache_root() -> Path:
    raw = os.environ.get(CACHE_ENV)
    return Path(raw) if raw else DEFAULT_CACHE_DIR


def _cache_key(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()


def _paths(root: Path, endpoint: str) -> tuple[Path, Path]:
    key = _cache_key(endpoint)
    return root / f"{key}.payload", root / f"{key}.json"


def _load(root: Path, endpoint: str) -> bytes | None:
    if _IMMUTABLE_BINARY_ENDPOINT.fullmatch(endpoint) is None:
        return None
    payload_path, metadata_path = _paths(root, endpoint)
    try:
        if (
            payload_path.is_symlink()
            or metadata_path.is_symlink()
            or not payload_path.is_file()
            or not metadata_path.is_file()
        ):
            return None
        metadata_raw = metadata_path.read_bytes()
        metadata = json.loads(metadata_raw)
        if type(metadata) is not dict or _canonical(metadata) != metadata_raw:
            return None
        if set(metadata) != {
            "schema_version",
            "endpoint",
            "payload_sha256",
            "payload_size_bytes",
        }:
            return None
        if metadata.get("schema_version") != CACHE_SCHEMA_VERSION:
            return None
        if metadata.get("endpoint") != endpoint:
            return None
        payload = payload_path.read_bytes()
        if metadata.get("payload_size_bytes") != len(payload):
            return None
        digest = metadata.get("payload_sha256")
        if (
            type(digest) is not str
            or len(digest) != 64
            or hashlib.sha256(payload).hexdigest() != digest
        ):
            return None
        return payload
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _persist(root: Path, endpoint: str, payload: bytes) -> None:
    if _IMMUTABLE_BINARY_ENDPOINT.fullmatch(endpoint) is None:
        return
    if type(payload) is not bytes or not payload:
        return
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("Current Shadow history cache root must be a real directory")

    payload_path, metadata_path = _paths(root, endpoint)
    digest = hashlib.sha256(payload).hexdigest()
    metadata = _canonical(
        {
            "schema_version": CACHE_SCHEMA_VERSION,
            "endpoint": endpoint,
            "payload_sha256": digest,
            "payload_size_bytes": len(payload),
        }
    )
    suffix = f".{os.getpid()}.{threading.get_ident()}.tmp"
    payload_tmp = payload_path.with_name(payload_path.name + suffix)
    metadata_tmp = metadata_path.with_name(metadata_path.name + suffix)
    try:
        payload_tmp.write_bytes(payload)
        metadata_tmp.write_bytes(metadata)
        os.replace(payload_tmp, payload_path)
        os.replace(metadata_tmp, metadata_path)
    finally:
        payload_tmp.unlink(missing_ok=True)
        metadata_tmp.unlink(missing_ok=True)


def install(latest_history: Any) -> PersistentHistoryGitHubCacheHooks:
    """Install persistent immutable-binary caching below the existing prefetch."""
    root = _cache_root()
    original_gh_download = latest_history.pr175_projection._gh_download_compatible

    def cached_disk_download(endpoint: str) -> bytes:
        cached = _load(root, endpoint)
        if cached is not None:
            return cached
        payload = original_gh_download(endpoint)
        if type(payload) is bytes and payload:
            _persist(root, endpoint, payload)
        return payload

    latest_history.pr175_projection._gh_download_compatible = cached_disk_download
    try:
        prefetch_hooks = prefetch.install(latest_history)
    except Exception:
        latest_history.pr175_projection._gh_download_compatible = original_gh_download
        raise
    return PersistentHistoryGitHubCacheHooks(
        original_gh_download=original_gh_download,
        cached_disk_download=cached_disk_download,
        prefetch_hooks=prefetch_hooks,
    )


def restore(latest_history: Any, hooks: PersistentHistoryGitHubCacheHooks) -> None:
    """Restore both cache layers without changing any authoritative evidence."""
    if type(hooks) is not PersistentHistoryGitHubCacheHooks:
        raise TypeError("hooks must be PersistentHistoryGitHubCacheHooks")
    try:
        prefetch.restore(latest_history, hooks.prefetch_hooks)
    finally:
        latest_history.pr175_projection._gh_download_compatible = (
            hooks.original_gh_download
        )


__all__ = [
    "CACHE_ENV",
    "CACHE_SCHEMA_VERSION",
    "DEFAULT_CACHE_DIR",
    "PersistentHistoryGitHubCacheHooks",
    "install",
    "restore",
]
