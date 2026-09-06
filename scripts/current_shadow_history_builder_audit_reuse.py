"""Worker-local exact reuse of the builder-issued PR151 captured-audit replay.

The reviewed latest-history builder first runs the complete projected PR151
Actions audit while recording every GitHub read.  It then constructs a
``GitHubActionsLineageEvidenceBundle`` whose public validator deliberately reruns
that same complete audit from the captured reads to prove that the snapshot
reproduces the live result.

For arbitrary callers that second replay is essential.  Inside one Current
Shadow worker, however, the exact read tuple handed to the evidence constructor
was just issued by the same reviewed builder from the successful live audit.
This module lets only that exact same-process payload identity reuse the already
completed audit result.  The evidence dataclass itself still runs unchanged and
still compares the returned canonical audit with ``audit_result_bytes``.

No failed audit is cached.  Different main SHA, read key/kind/status, payload
object, or payload length falls back to the original replay.  Cached entries hold
strong references to every immutable payload byte object so Python object-id
reuse cannot create a false match.  This layer grants no evidence, model,
pricing, selection, execution, or BET authority.
"""
from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
import threading
from typing import Any


DIAGNOSTIC_SCHEMA_VERSION = 1
DIAGNOSTIC_DATASET_NAME = "athena-current-shadow-history-builder-audit-reuse-v1"


@dataclasses.dataclass
class BuilderAuditReplayReuseStats:
    live_audits_captured: int = 0
    builder_replays_reused: int = 0
    fallback_replays_executed: int = 0
    _lock: threading.Lock = dataclasses.field(default_factory=threading.Lock, repr=False)

    def increment(self, field: str) -> None:
        if field not in {
            "live_audits_captured",
            "builder_replays_reused",
            "fallback_replays_executed",
        }:
            raise ValueError("unknown builder-audit reuse counter")
        with self._lock:
            setattr(self, field, getattr(self, field) + 1)

    def to_dict(self) -> dict[str, int]:
        with self._lock:
            return {
                "live_audits_captured": self.live_audits_captured,
                "builder_replays_reused": self.builder_replays_reused,
                "fallback_replays_executed": self.fallback_replays_executed,
            }


@dataclasses.dataclass(frozen=True)
class _IssuedAudit:
    payload_refs: tuple[bytes, ...]
    audit_result_bytes: bytes
    used_keys: frozenset[str]


@dataclasses.dataclass(frozen=True)
class BuilderAuditReplayReuseHooks:
    original_build_with_readers: Any
    original_run_projected_audit: Any
    original_recorder_freeze: Any
    original_replay_audit: Any
    stats: BuilderAuditReplayReuseStats
    diagnostic_path: Path | None


def _write_diagnostic(
    path: Path | None,
    *,
    stats: BuilderAuditReplayReuseStats,
    last_operation: str,
) -> None:
    if path is None:
        return
    payload = {
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "dataset_name": DIAGNOSTIC_DATASET_NAME,
        "last_operation": last_operation,
        "stats": stats.to_dict(),
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
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        temporary.write_bytes(raw)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _valid_main_sha(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def _reads_identity(latest_history: Any, expected_main_sha: Any, reads: Any):
    if not _valid_main_sha(expected_main_sha) or type(reads) is not tuple or not reads:
        return None
    rows: list[tuple[Any, ...]] = []
    refs: list[bytes] = []
    keys: list[str] = []
    for item in reads:
        if type(item) is not latest_history.GitHubReadSnapshot:
            return None
        payload = item.payload
        if type(payload) is not bytes or not payload:
            return None
        if type(item.key) is not str or not item.key:
            return None
        if item.payload_kind not in {"json", "binary"} or type(item.succeeded) is not bool:
            return None
        rows.append(
            (
                item.key,
                item.payload_kind,
                item.succeeded,
                id(payload),
                len(payload),
            )
        )
        refs.append(payload)
        keys.append(item.key)
    if len(set(keys)) != len(keys):
        return None
    return (
        (expected_main_sha, tuple(rows)),
        tuple(refs),
        frozenset(keys),
    )


def install(
    latest_history: Any,
    *,
    diagnostic_path: Path | None = None,
) -> BuilderAuditReplayReuseHooks:
    """Install exact same-builder reuse around the public evidence replay."""

    original_build = latest_history._build_with_readers
    original_run_audit = latest_history._run_reviewed_projected_audit
    original_freeze = latest_history._ReadRecorder.freeze
    original_replay = latest_history._replay_audit_from_evidence

    stats = BuilderAuditReplayReuseStats()
    issued_by_identity: dict[tuple[Any, ...], _IssuedAudit] = {}
    poisoned: set[tuple[Any, ...]] = set()
    lock = threading.Lock()
    local = threading.local()

    def in_active_builder() -> bool:
        return getattr(local, "builder_depth", 0) > 0

    def build_with_readers(*args, **kwargs):
        prior_depth = getattr(local, "builder_depth", 0)
        prior_captures = getattr(local, "live_audit_captures", None)
        local.builder_depth = prior_depth + 1
        if prior_depth == 0:
            local.live_audit_captures = []
        try:
            return original_build(*args, **kwargs)
        finally:
            local.builder_depth = prior_depth
            if prior_depth == 0:
                if prior_captures is None:
                    try:
                        del local.live_audit_captures
                    except AttributeError:
                        pass
                else:
                    local.live_audit_captures = prior_captures

    def run_projected_audit(*args, **kwargs):
        value = original_run_audit(*args, **kwargs)
        if in_active_builder() and not getattr(local, "inside_replay", False):
            expected_main_sha = kwargs.get("expected_main_sha")
            if _valid_main_sha(expected_main_sha):
                try:
                    audit_raw = latest_history._canonical(value)
                except Exception:
                    return value
                captures = getattr(local, "live_audit_captures", None)
                if type(captures) is list:
                    captures.append((expected_main_sha, audit_raw))
        return value

    def recorder_freeze(recorder):
        reads = original_freeze(recorder)
        if not in_active_builder() or getattr(local, "inside_replay", False):
            return reads
        captures = getattr(local, "live_audit_captures", None)
        if type(captures) is not list or len(captures) != 1:
            if type(captures) is list:
                captures.clear()
            return reads
        expected_main_sha, audit_raw = captures.pop()
        identity_value = _reads_identity(latest_history, expected_main_sha, reads)
        if identity_value is None:
            return reads
        identity, refs, keys = identity_value
        issued = _IssuedAudit(
            payload_refs=refs,
            audit_result_bytes=audit_raw,
            used_keys=keys,
        )
        cached = False
        with lock:
            if identity not in poisoned:
                existing = issued_by_identity.get(identity)
                if existing is None:
                    issued_by_identity[identity] = issued
                    cached = True
                elif (
                    len(existing.payload_refs) == len(refs)
                    and all(left is right for left, right in zip(existing.payload_refs, refs))
                    and existing.audit_result_bytes == audit_raw
                    and existing.used_keys == keys
                ):
                    cached = True
                else:
                    issued_by_identity.pop(identity, None)
                    poisoned.add(identity)
        if cached:
            stats.increment("live_audits_captured")
            _write_diagnostic(
                diagnostic_path,
                stats=stats,
                last_operation="LIVE_AUDIT_CAPTURED",
            )
        return reads

    def replay_audit_from_evidence(*, expected_main_sha, reads):
        identity_value = _reads_identity(latest_history, expected_main_sha, reads)
        if identity_value is not None:
            identity, refs, _keys = identity_value
            with lock:
                issued = issued_by_identity.get(identity)
                is_poisoned = identity in poisoned
            if issued is not None and not is_poisoned:
                if (
                    len(issued.payload_refs) == len(refs)
                    and all(left is right for left, right in zip(issued.payload_refs, refs))
                ):
                    stats.increment("builder_replays_reused")
                    _write_diagnostic(
                        diagnostic_path,
                        stats=stats,
                        last_operation="BUILDER_REPLAY_REUSED",
                    )
                    return (
                        latest_history._parse_object(
                            issued.audit_result_bytes,
                            "builder-issued captured Actions lineage audit",
                        ),
                        set(issued.used_keys),
                    )

        prior = getattr(local, "inside_replay", False)
        local.inside_replay = True
        try:
            value = original_replay(
                expected_main_sha=expected_main_sha,
                reads=reads,
            )
        finally:
            local.inside_replay = prior
        stats.increment("fallback_replays_executed")
        _write_diagnostic(
            diagnostic_path,
            stats=stats,
            last_operation="FALLBACK_REPLAY_EXECUTED",
        )
        return value

    latest_history._build_with_readers = build_with_readers
    latest_history._run_reviewed_projected_audit = run_projected_audit
    latest_history._ReadRecorder.freeze = recorder_freeze
    latest_history._replay_audit_from_evidence = replay_audit_from_evidence
    return BuilderAuditReplayReuseHooks(
        original_build_with_readers=original_build,
        original_run_projected_audit=original_run_audit,
        original_recorder_freeze=original_freeze,
        original_replay_audit=original_replay,
        stats=stats,
        diagnostic_path=diagnostic_path,
    )


def restore(latest_history: Any, hooks: BuilderAuditReplayReuseHooks) -> None:
    if type(hooks) is not BuilderAuditReplayReuseHooks:
        raise TypeError("hooks must be BuilderAuditReplayReuseHooks")
    latest_history._build_with_readers = hooks.original_build_with_readers
    latest_history._run_reviewed_projected_audit = hooks.original_run_projected_audit
    latest_history._ReadRecorder.freeze = hooks.original_recorder_freeze
    latest_history._replay_audit_from_evidence = hooks.original_replay_audit


__all__ = [
    "BuilderAuditReplayReuseHooks",
    "BuilderAuditReplayReuseStats",
    "DIAGNOSTIC_DATASET_NAME",
    "DIAGNOSTIC_SCHEMA_VERSION",
    "install",
    "restore",
]
