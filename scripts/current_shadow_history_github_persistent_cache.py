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

import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
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
CURRENT_SHADOW_WORKER_ENV = "ATHENA_CURRENT_SHADOW_ALL_MARKET_WORKER"
CONTROL_ROW_PREFETCH_WORKERS = 8
_IMMUTABLE_BINARY_ENDPOINT = re.compile(
    r"^/repos/Thabearr/ATHENA/(?:actions/artifacts/[1-9][0-9]*/zip|releases/assets/[1-9][0-9]*)$"
)


@dataclasses.dataclass(frozen=True)
class _ControlRowReuseHooks:
    original_extract_control_rows: Any
    original_prefetch_universe: Any


@dataclasses.dataclass(frozen=True)
class _DurablePrefixReuseHooks:
    original_derive: Any


@dataclasses.dataclass(frozen=True)
class PersistentHistoryGitHubCacheHooks:
    original_gh_download: Any
    cached_disk_download: Any
    prefetch_hooks: prefetch.HistoryGitHubPrefetchHooks
    stats: "PersistentHistoryGitHubCacheStats"
    control_row_reuse_hooks: _ControlRowReuseHooks | None = None
    durable_prefix_reuse_hooks: _DurablePrefixReuseHooks | None = None


@dataclasses.dataclass
class PersistentHistoryGitHubCacheStats:
    """Transport-only counters; they are never lineage or model evidence."""

    cache_hits: int = 0
    cache_misses: int = 0
    cache_hit_bytes: int = 0
    cache_miss_bytes: int = 0
    _lock: threading.Lock = dataclasses.field(default_factory=threading.Lock, repr=False)

    def hit(self, payload: bytes) -> None:
        with self._lock:
            self.cache_hits += 1
            self.cache_hit_bytes += len(payload)

    def miss(self, payload: bytes) -> None:
        with self._lock:
            self.cache_misses += 1
            self.cache_miss_bytes += len(payload)

    def to_dict(self) -> dict[str, int]:
        with self._lock:
            return {
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "cache_hit_bytes": self.cache_hit_bytes,
                "cache_miss_bytes": self.cache_miss_bytes,
            }


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


def _run_fingerprint(run: Any) -> str | None:
    if type(run) is not dict:
        return None
    try:
        return hashlib.sha256(_canonical(run)).hexdigest()
    except (TypeError, ValueError, OverflowError):
        return None


def _install_control_row_reuse(latest_history: Any) -> _ControlRowReuseHooks:
    """Parallelize exact cumulative control-row extraction inside one worker.

    The reviewed PR151 audit still performs every authoritative GitHub read,
    artifact/release verification, control-lineage validation and append-only
    comparison.  This layer only pre-executes the audit engine's exact durable
    archive extraction for immutable archive SHA-256 identities after the
    existing transport prefetch has captured the workflow-run universe.  The
    later authoritative audit may reuse a result only for the same archive
    digest and the same ``require_control`` policy.  A speculative failure,
    malformed run or conflicting cache identity is discarded and therefore
    falls back to the untouched extraction path.

    A successfully prewarmed completed-run snapshot is also remembered by the
    SHA-256 of its exact canonical GitHub run object.  Re-entering the same
    reviewed lineage snapshot in this worker therefore does not resubmit all
    already-proven archives merely because a later current-date prefix replays
    the same immutable PR151 evidence.  Any run-metadata drift gets a different
    fingerprint and is re-evaluated normally.
    """

    lineage = latest_history.lineage_audit
    projection = latest_history.recovery_projection
    downloads = latest_history.pr175_projection
    mirror = latest_history.mirror
    original_extract = lineage._extract_control_rows
    original_prefetch_universe = projection._prefetch_workflow_run_universe
    rows_by_identity: dict[tuple[str, bool], tuple[dict[str, Any], ...]] = {}
    poisoned: set[tuple[str, bool]] = set()
    successfully_prewarmed_runs: set[str] = set()
    lock = threading.Lock()

    def prewarm_one(run: Any, fingerprint: str | None):
        if not prefetch._exact_primary_run(run, projection=projection):
            return None
        run_id = run.get("id")
        if type(run_id) is not int or run_id < 1:
            return None
        repository = latest_history.REPOSITORY
        artifacts = lineage._gh_json(
            f"/repos/{repository}/actions/runs/{run_id}/artifacts"
        )
        if not isinstance(artifacts, dict):
            return None
        if lineage._is_exact_zero_artifact_payload(artifacts):
            return None
        artifact = lineage._candidate_artifact(artifacts, run_id)
        artifact_id = artifact.get("id")
        if type(artifact_id) is not int or artifact_id < 1:
            return None
        zip_bytes = downloads._gh_download_compatible(
            f"/repos/{repository}/actions/artifacts/{artifact_id}/zip"
        )
        mirror.verify_actions_artifact_zip_digest(
            zip_bytes,
            artifact.get("digest"),
        )
        verified = mirror.verify_actions_artifact_bundle(
            run_id=run_id,
            artifact_name=artifact["name"],
            zip_bytes=zip_bytes,
        )
        match = lineage.ARTIFACT_RE.fullmatch(artifact["name"])
        if match is None:
            return None
        require_control = match.group(1) == "success"
        archive_sha = verified.get("archive_sha256")
        if type(archive_sha) is not str or len(archive_sha) != 64:
            return None
        rows = original_extract(
            verified["archive_bytes"],
            archive_sha,
            require_control=require_control,
        )
        return fingerprint, (archive_sha, require_control), rows

    def prefetch_with_control_rows(get_runs_page):
        universe = original_prefetch_universe(get_runs_page)
        runs = getattr(universe, "runs", ())
        if type(runs) is not tuple:
            return universe

        pending: list[tuple[Any, str | None]] = []
        reused_run_count = 0
        for run in runs:
            if not prefetch._exact_primary_run(run, projection=projection):
                continue
            fingerprint = _run_fingerprint(run)
            if fingerprint is not None:
                with lock:
                    already = fingerprint in successfully_prewarmed_runs
                if already:
                    reused_run_count += 1
                    continue
            pending.append((run, fingerprint))

        newly_cached = 0
        if pending:
            with ThreadPoolExecutor(
                max_workers=CONTROL_ROW_PREFETCH_WORKERS,
                thread_name_prefix="athena-history-control",
            ) as executor:
                futures = [
                    executor.submit(prewarm_one, run, fingerprint)
                    for run, fingerprint in pending
                ]
                for future in as_completed(futures):
                    try:
                        result = future.result()
                    except Exception:
                        # Speculative work is never evidence and may not convert a
                        # real audit failure into success.  The authoritative call
                        # below will execute the original path for this identity.
                        continue
                    if result is None:
                        continue
                    fingerprint, identity, rows = result
                    with lock:
                        if identity in poisoned:
                            continue
                        existing = rows_by_identity.get(identity)
                        if existing is None:
                            rows_by_identity[identity] = rows
                            newly_cached += 1
                        elif existing != rows:
                            rows_by_identity.pop(identity, None)
                            poisoned.add(identity)
                            continue
                        if fingerprint is not None:
                            successfully_prewarmed_runs.add(fingerprint)
        print(
            "Current Shadow durable-history prewarmed "
            f"{newly_cached} new exact control archives; "
            f"cached {len(rows_by_identity)}; "
            f"reused {reused_run_count} exact completed-run identities.",
            flush=True,
        )
        return universe

    def cached_extract_control_rows(
        archive_bytes: bytes,
        expected_sha256: str,
        *,
        require_control: bool,
    ) -> tuple[dict[str, Any], ...]:
        if (
            type(archive_bytes) is bytes
            and type(expected_sha256) is str
            and type(require_control) is bool
            and hashlib.sha256(archive_bytes).hexdigest() == expected_sha256
        ):
            identity = (expected_sha256, require_control)
            with lock:
                cached = rows_by_identity.get(identity)
                is_poisoned = identity in poisoned
            if cached is not None and not is_poisoned:
                return copy.deepcopy(cached)
        return original_extract(
            archive_bytes,
            expected_sha256,
            require_control=require_control,
        )

    lineage._extract_control_rows = cached_extract_control_rows
    projection._prefetch_workflow_run_universe = prefetch_with_control_rows
    return _ControlRowReuseHooks(
        original_extract_control_rows=original_extract,
        original_prefetch_universe=original_prefetch_universe,
    )


def _restore_control_row_reuse(
    latest_history: Any,
    hooks: _ControlRowReuseHooks,
) -> None:
    if type(hooks) is not _ControlRowReuseHooks:
        raise TypeError("hooks must be _ControlRowReuseHooks")
    latest_history.lineage_audit._extract_control_rows = (
        hooks.original_extract_control_rows
    )
    latest_history.recovery_projection._prefetch_workflow_run_universe = (
        hooks.original_prefetch_universe
    )


def _install_durable_prefix_reuse(latest_history: Any) -> _DurablePrefixReuseHooks:
    """Reuse only the invariant replay of one exact durable archive inside a worker.

    A three-date Current Shadow request may bind each current FotMob capture to the
    same latest-applicable PR151 success artifact.  The public prefix verifier
    intentionally re-extracts and replays that cumulative archive for every
    independent caller.  Inside this worker we keep that first successful exact
    replay as a transport/computation cache only.

    Reuse requires the same workflow-run id, artifact name, metadata digest and
    exact artifact ZIP SHA-256.  Every later current source still passes the
    reviewed source-bundle ancestry checks, the Actions ZIP digest and bundle
    commitment are reverified, the receipt is rechecked against that source's
    own observed_at, and PR244 rebuilds the current-source shadow handoff with
    the cached reviewed settlement tuple.  Any mismatch or reuse-path exception
    falls back to the untouched full derivation; the cache can never turn a
    failing authoritative replay into success.
    """

    prefix = latest_history.prefix
    original_derive = prefix._derive
    invariant_by_artifact: dict[tuple[Any, ...], Any] = {}
    lock = threading.Lock()

    def artifact_identity(source: Any) -> tuple[Any, ...] | None:
        if type(source) is not prefix.CurrentDurableFreshHistoryPrefixSourceBundle:
            return None
        payload = source.artifact_zip_bytes
        if type(payload) is not bytes or not payload:
            return None
        return (
            source.workflow_run_id,
            source.artifact_name,
            source.artifact_zip_metadata_digest,
            hashlib.sha256(payload).hexdigest(),
        )

    def cache_success(identity: tuple[Any, ...], value: Any) -> None:
        if type(value) is not prefix._DerivedPrefix:
            return
        with lock:
            existing = invariant_by_artifact.get(identity)
            if existing is None:
                invariant_by_artifact[identity] = value
            elif (
                existing.artifact_zip_sha256 != value.artifact_zip_sha256
                or existing.archive_sha256 != value.archive_sha256
                or existing.receipt_sha256 != value.receipt_sha256
                or existing.checkpoint_sha256 != value.checkpoint_sha256
                or existing.settlement_journal_sha256 != value.settlement_journal_sha256
                or existing.reviewed_fresh_settlements != value.reviewed_fresh_settlements
            ):
                invariant_by_artifact.pop(identity, None)

    def derive(source: Any):
        identity = artifact_identity(source)
        if identity is None:
            return original_derive(source)
        with lock:
            cached = invariant_by_artifact.get(identity)
        if cached is None:
            value = original_derive(source)
            cache_success(identity, value)
            return value

        try:
            zip_sha = prefix.mirror.verify_actions_artifact_zip_digest(
                source.artifact_zip_bytes,
                source.artifact_zip_metadata_digest,
            )
            verified = prefix.mirror.verify_actions_artifact_bundle(
                run_id=source.workflow_run_id,
                artifact_name=source.artifact_name,
                zip_bytes=source.artifact_zip_bytes,
            )
            receipt, nominal, committed_at = prefix._exact_receipt(
                verified["receipt_bytes"],
                run_id=source.workflow_run_id,
                artifact_name=source.artifact_name,
                source_observed_at=source.source_observed_at,
            )
            if (
                zip_sha != cached.artifact_zip_sha256
                or verified.get("archive_sha256") != cached.archive_sha256
                or verified.get("archive_size_bytes") != cached.archive_size_bytes
                or prefix._sha(verified["receipt_bytes"]) != cached.receipt_sha256
                or nominal != cached.nominal_scheduled_for_utc
                or committed_at != cached.committed_at_utc
                or receipt.get("workflow_run_id") != source.workflow_run_id
                or receipt.get("durable_asset_name") != source.artifact_name
            ):
                return original_derive(source)
            replay = prefix.shadow.build_current_fotmob_utc_native_shadow_prediction_handoff(
                current_bootstrap=source.current_bootstrap,
                source_raw_json=source.source_raw_json,
                source_manifest=source.source_manifest,
                legacy_bootstrap_projection_raw=source.legacy_bootstrap_projection_raw,
                reviewed_fresh_settlements=cached.reviewed_fresh_settlements,
            )
            return prefix._DerivedPrefix(
                artifact_zip_sha256=cached.artifact_zip_sha256,
                archive_sha256=cached.archive_sha256,
                archive_size_bytes=cached.archive_size_bytes,
                receipt_sha256=cached.receipt_sha256,
                nominal_scheduled_for_utc=cached.nominal_scheduled_for_utc,
                committed_at_utc=cached.committed_at_utc,
                checkpoint_sha256=cached.checkpoint_sha256,
                settlement_journal_sha256=cached.settlement_journal_sha256,
                settlement_journal_row_count=cached.settlement_journal_row_count,
                reviewed_fresh_settlements=cached.reviewed_fresh_settlements,
                reviewed_legacy_update_count=cached.reviewed_legacy_update_count,
                shadow_handoff=replay,
            )
        except Exception:
            return original_derive(source)

    prefix._derive = derive
    return _DurablePrefixReuseHooks(original_derive=original_derive)


def _restore_durable_prefix_reuse(
    latest_history: Any,
    hooks: _DurablePrefixReuseHooks,
) -> None:
    if type(hooks) is not _DurablePrefixReuseHooks:
        raise TypeError("hooks must be _DurablePrefixReuseHooks")
    latest_history.prefix._derive = hooks.original_derive


def install(latest_history: Any) -> PersistentHistoryGitHubCacheHooks:
    """Install persistent immutable-binary caching below the existing prefetch."""
    root = _cache_root()
    original_gh_download = latest_history.pr175_projection._gh_download_compatible
    stats = PersistentHistoryGitHubCacheStats()

    def cached_disk_download(endpoint: str) -> bytes:
        cached = _load(root, endpoint)
        if cached is not None:
            stats.hit(cached)
            return cached
        payload = original_gh_download(endpoint)
        if type(payload) is bytes and payload:
            if _IMMUTABLE_BINARY_ENDPOINT.fullmatch(endpoint) is not None:
                stats.miss(payload)
            _persist(root, endpoint, payload)
        return payload

    latest_history.pr175_projection._gh_download_compatible = cached_disk_download
    try:
        prefetch_hooks = prefetch.install(latest_history)
    except Exception:
        latest_history.pr175_projection._gh_download_compatible = original_gh_download
        raise

    control_row_reuse_hooks = None
    durable_prefix_reuse_hooks = None
    if os.environ.get(CURRENT_SHADOW_WORKER_ENV) == "1":
        try:
            control_row_reuse_hooks = _install_control_row_reuse(latest_history)
            durable_prefix_reuse_hooks = _install_durable_prefix_reuse(latest_history)
        except Exception:
            if durable_prefix_reuse_hooks is not None:
                _restore_durable_prefix_reuse(latest_history, durable_prefix_reuse_hooks)
            if control_row_reuse_hooks is not None:
                _restore_control_row_reuse(latest_history, control_row_reuse_hooks)
            prefetch.restore(latest_history, prefetch_hooks)
            latest_history.pr175_projection._gh_download_compatible = original_gh_download
            raise

    return PersistentHistoryGitHubCacheHooks(
        original_gh_download=original_gh_download,
        cached_disk_download=cached_disk_download,
        prefetch_hooks=prefetch_hooks,
        stats=stats,
        control_row_reuse_hooks=control_row_reuse_hooks,
        durable_prefix_reuse_hooks=durable_prefix_reuse_hooks,
    )


def restore(latest_history: Any, hooks: PersistentHistoryGitHubCacheHooks) -> None:
    """Restore all cache layers without changing any authoritative evidence."""
    if type(hooks) is not PersistentHistoryGitHubCacheHooks:
        raise TypeError("hooks must be PersistentHistoryGitHubCacheHooks")
    try:
        if hooks.durable_prefix_reuse_hooks is not None:
            _restore_durable_prefix_reuse(
                latest_history,
                hooks.durable_prefix_reuse_hooks,
            )
        if hooks.control_row_reuse_hooks is not None:
            _restore_control_row_reuse(
                latest_history,
                hooks.control_row_reuse_hooks,
            )
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
    "PersistentHistoryGitHubCacheStats",
    "install",
    "restore",
]
