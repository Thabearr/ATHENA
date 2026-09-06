"""Worker-local exact verification reuse for immutable PR151 artifact bytes.

The current-history audit deliberately replays the same captured Actions evidence
several times while proving one source-bound Shadow request. Each replay must
still consume and validate the exact recorded bytes, but repeatedly expanding and
hashing the same immutable Actions artifact ZIP is computation rather than new
evidence. This module caches only successful exact verifier outputs inside one
worker process.

No GitHub read is skipped. No failure is cached. Any change to run id, artifact
name, metadata digest, or ZIP bytes forces the original verifier. The cache never
grants evidence, model, pricing, selection, execution, or BET authority.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from pathlib import Path
import threading
from typing import Any


DIAGNOSTIC_SCHEMA_VERSION = 1
DIAGNOSTIC_DATASET_NAME = "athena-current-shadow-history-artifact-verification-reuse-v1"
_DIAGNOSTIC_LOCK = threading.Lock()


@dataclasses.dataclass
class ArtifactVerificationReuseStats:
    digest_verified: int = 0
    digest_reused: int = 0
    bundle_verified: int = 0
    bundle_reused: int = 0
    _lock: threading.Lock = dataclasses.field(default_factory=threading.Lock, repr=False)

    def increment(self, field: str) -> None:
        if field not in {
            "digest_verified",
            "digest_reused",
            "bundle_verified",
            "bundle_reused",
        }:
            raise ValueError("unknown artifact-verification reuse counter")
        with self._lock:
            setattr(self, field, getattr(self, field) + 1)

    def _snapshot_unlocked(self) -> dict[str, int]:
        return {
            "digest_verified": self.digest_verified,
            "digest_reused": self.digest_reused,
            "bundle_verified": self.bundle_verified,
            "bundle_reused": self.bundle_reused,
        }

    def to_dict(self) -> dict[str, int]:
        with self._lock:
            return self._snapshot_unlocked()


@dataclasses.dataclass(frozen=True)
class ArtifactVerificationReuseHooks:
    original_digest_verifier: Any
    original_bundle_verifier: Any
    stats: ArtifactVerificationReuseStats
    diagnostic_path: Path | None


def _zip_sha256(value: Any) -> str | None:
    if type(value) is not bytes or not value:
        return None
    return hashlib.sha256(value).hexdigest()


def _cacheable_bundle(
    value: Any,
    *,
    run_id: Any,
    artifact_name: Any,
    zip_sha256: str,
) -> bool:
    if type(value) is not dict:
        return False
    if value.get("run_id") != run_id or value.get("artifact_name") != artifact_name:
        return False
    archive = value.get("archive_bytes")
    archive_sha = value.get("archive_sha256")
    receipt = value.get("receipt_bytes")
    if type(archive) is not bytes or not archive:
        return False
    if type(receipt) is not bytes or not receipt:
        return False
    if type(archive_sha) is not str or hashlib.sha256(archive).hexdigest() != archive_sha:
        return False
    return len(zip_sha256) == 64


def _write_diagnostic(
    path: Path | None,
    *,
    stats: ArtifactVerificationReuseStats,
    last_operation: str,
    force: bool = False,
) -> None:
    if path is None:
        return
    snapshot = stats.to_dict()
    # Keep writes sparse enough that instrumentation cannot become a new runtime
    # cost, but ensure a long-running replay leaves durable progress before an
    # outer supervisor can terminate the worker.
    total = sum(snapshot.values())
    if not force and total not in {1, 2} and total % 25 != 0:
        return
    payload = {
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "dataset_name": DIAGNOSTIC_DATASET_NAME,
        "last_operation": last_operation,
        "stats": snapshot,
        "evidence_authority": False,
        "model_authority": False,
        "pricing_authority": False,
        "selection_authority": False,
        "execution_authority": False,
        "bet_authority": False,
        "wager_placed": False,
    }
    raw = (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    with _DIAGNOSTIC_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_bytes(raw)
        temporary.replace(path)


def install(
    latest_history: Any,
    *,
    diagnostic_path: Path | None = None,
) -> ArtifactVerificationReuseHooks:
    """Install exact successful verifier reuse on the shared mirror module."""

    mirror = latest_history.mirror
    original_digest = mirror.verify_actions_artifact_zip_digest
    original_bundle = mirror.verify_actions_artifact_bundle
    stats = ArtifactVerificationReuseStats()
    digest_by_identity: dict[tuple[str, str], str] = {}
    bundle_by_identity: dict[tuple[int, str, str], dict[str, Any]] = {}
    lock = threading.Lock()

    def verify_digest(zip_bytes: bytes, metadata_digest: Any) -> str:
        zip_sha = _zip_sha256(zip_bytes)
        if zip_sha is None or type(metadata_digest) is not str:
            return original_digest(zip_bytes, metadata_digest)
        identity = (zip_sha, metadata_digest)
        with lock:
            cached = digest_by_identity.get(identity)
        if cached is not None:
            stats.increment("digest_reused")
            _write_diagnostic(
                diagnostic_path,
                stats=stats,
                last_operation="DIGEST_REUSED",
            )
            return cached

        value = original_digest(zip_bytes, metadata_digest)
        # Cache only the exact successful identity proved by the reviewed
        # verifier. A strange/mutated verifier result remains uncached.
        if value == zip_sha and metadata_digest == f"sha256:{zip_sha}":
            with lock:
                digest_by_identity[identity] = value
            stats.increment("digest_verified")
            _write_diagnostic(
                diagnostic_path,
                stats=stats,
                last_operation="DIGEST_VERIFIED",
            )
        return value

    def verify_bundle(*, run_id: int, artifact_name: str, zip_bytes: bytes):
        zip_sha = _zip_sha256(zip_bytes)
        if (
            zip_sha is None
            or type(run_id) is not int
            or run_id < 1
            or type(artifact_name) is not str
        ):
            return original_bundle(
                run_id=run_id,
                artifact_name=artifact_name,
                zip_bytes=zip_bytes,
            )
        identity = (run_id, artifact_name, zip_sha)
        with lock:
            cached = bundle_by_identity.get(identity)
        if cached is not None:
            stats.increment("bundle_reused")
            _write_diagnostic(
                diagnostic_path,
                stats=stats,
                last_operation="BUNDLE_REUSED",
            )
            return copy.deepcopy(cached)

        value = original_bundle(
            run_id=run_id,
            artifact_name=artifact_name,
            zip_bytes=zip_bytes,
        )
        if _cacheable_bundle(
            value,
            run_id=run_id,
            artifact_name=artifact_name,
            zip_sha256=zip_sha,
        ):
            frozen = copy.deepcopy(value)
            with lock:
                existing = bundle_by_identity.get(identity)
                if existing is None:
                    bundle_by_identity[identity] = frozen
                elif existing != frozen:
                    # Concurrent exact verification disagreement is not reusable.
                    bundle_by_identity.pop(identity, None)
                    return value
            stats.increment("bundle_verified")
            _write_diagnostic(
                diagnostic_path,
                stats=stats,
                last_operation="BUNDLE_VERIFIED",
            )
        return value

    mirror.verify_actions_artifact_zip_digest = verify_digest
    mirror.verify_actions_artifact_bundle = verify_bundle
    return ArtifactVerificationReuseHooks(
        original_digest_verifier=original_digest,
        original_bundle_verifier=original_bundle,
        stats=stats,
        diagnostic_path=diagnostic_path,
    )


def restore(latest_history: Any, hooks: ArtifactVerificationReuseHooks) -> None:
    if type(hooks) is not ArtifactVerificationReuseHooks:
        raise TypeError("hooks must be ArtifactVerificationReuseHooks")
    try:
        _write_diagnostic(
            hooks.diagnostic_path,
            stats=hooks.stats,
            last_operation="RESTORED",
            force=True,
        )
    finally:
        # Diagnostic I/O can never be allowed to strand verifier monkeypatches.
        latest_history.mirror.verify_actions_artifact_zip_digest = (
            hooks.original_digest_verifier
        )
        latest_history.mirror.verify_actions_artifact_bundle = (
            hooks.original_bundle_verifier
        )


__all__ = [
    "ArtifactVerificationReuseHooks",
    "ArtifactVerificationReuseStats",
    "DIAGNOSTIC_DATASET_NAME",
    "DIAGNOSTIC_SCHEMA_VERSION",
    "install",
    "restore",
]
