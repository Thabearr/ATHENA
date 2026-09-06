"""Worker-local reuse of exact Current Shadow semantic history replays.

The reviewed PR245 -> PR244 durable-history path deliberately revalidates frozen
objects in dataclass ``__post_init__`` methods and canonical serializers.  That is
important for arbitrary callers, but the hosted Current Shadow worker immediately
recreates the same already-validated semantic inputs several times while building,
copying and hashing one history handoff.  Each PR244 semantic replay can rebuild
thousands of historical feature rows, so repeating it is the dominant CPU cost of
CURRENT_DURABLE_FRESH_HISTORY.

This module changes no public/frozen trust contract.  It is installed only for the
Current Shadow worker and caches *successful* results of the existing reviewed
functions under exact content identities:

* ``_history_ledger`` is keyed only by the exact PR119 bootstrap bytes plus every
  field of every reviewed settlement, because those are its complete inputs;
* ``_derive_shadow_state`` additionally binds the exact reviewed current bootstrap,
  capture manifest/raw identity and the same history identity.

The first unique input always executes the original reviewed implementation.
Malformed/unsupported identities and failures always fall back and are never
cached.  The cached ledger/result objects are frozen dataclasses.  This layer has
no source, evidence, model, pricing, selection, execution or BET authority.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import enum
import hashlib
import json
import os
from pathlib import Path
import threading
from collections.abc import Mapping
from typing import Any


DIAGNOSTIC_SCHEMA_VERSION = 1
DIAGNOSTIC_DATASET_NAME = "athena-current-shadow-history-semantic-replay-reuse-v1"


@dataclasses.dataclass
class SemanticReplayReuseStats:
    derive_authoritative_executed: int = 0
    derive_reused: int = 0
    history_ledger_authoritative_executed: int = 0
    history_ledger_reused: int = 0
    uncacheable_fallbacks: int = 0
    failures_not_cached: int = 0
    _lock: threading.Lock = dataclasses.field(default_factory=threading.Lock, repr=False)

    def increment(self, field: str) -> None:
        if field not in {
            "derive_authoritative_executed",
            "derive_reused",
            "history_ledger_authoritative_executed",
            "history_ledger_reused",
            "uncacheable_fallbacks",
            "failures_not_cached",
        }:
            raise ValueError("unknown semantic-replay reuse counter")
        with self._lock:
            setattr(self, field, getattr(self, field) + 1)

    def to_dict(self) -> dict[str, int]:
        with self._lock:
            return {
                "derive_authoritative_executed": self.derive_authoritative_executed,
                "derive_reused": self.derive_reused,
                "history_ledger_authoritative_executed": self.history_ledger_authoritative_executed,
                "history_ledger_reused": self.history_ledger_reused,
                "uncacheable_fallbacks": self.uncacheable_fallbacks,
                "failures_not_cached": self.failures_not_cached,
            }


@dataclasses.dataclass(frozen=True)
class SemanticReplayReuseHooks:
    original_derive_shadow_state: Any
    original_history_ledger: Any
    stats: SemanticReplayReuseStats
    diagnostic_path: Path | None


def _write_diagnostic(
    path: Path | None,
    *,
    stats: SemanticReplayReuseStats,
    last_operation: str,
    derive_cache_entries: int,
    ledger_cache_entries: int,
) -> None:
    """Persist best-effort progress only; this diagnostic grants no authority."""

    if path is None:
        return
    payload = {
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "dataset_name": DIAGNOSTIC_DATASET_NAME,
        "last_operation": last_operation,
        "stats": stats.to_dict(),
        "derive_cache_entries": derive_cache_entries,
        "history_ledger_cache_entries": ledger_cache_entries,
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
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(
            f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        temporary.write_bytes(raw)
        os.replace(temporary, path)
    except OSError:
        return
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _utc_identity(value: dt.datetime) -> tuple[str, str] | None:
    if value.tzinfo is None or value.utcoffset() is None:
        return None
    try:
        text = value.astimezone(dt.timezone.utc).isoformat(timespec="microseconds")
    except (TypeError, ValueError, OverflowError):
        return None
    return ("datetime", text.replace("+00:00", "Z"))


def _freeze_identity(value: Any) -> Any | None:
    """Return a hashable exact-content identity without invoking domain replay."""

    if value is None:
        return ("none",)
    if type(value) is bool:
        return ("bool", value)
    if type(value) is int:
        return ("int", value)
    if type(value) is str:
        return ("str", value)
    if type(value) is bytes:
        return ("bytes", len(value), hashlib.sha256(value).hexdigest())
    if type(value) is float:
        if value != value or value in {float("inf"), float("-inf")}:
            return None
        return ("float", value.hex())
    if isinstance(value, decimal.Decimal):
        return ("decimal", str(value))
    if isinstance(value, dt.datetime):
        return _utc_identity(value)
    if isinstance(value, enum.Enum):
        frozen = _freeze_identity(value.value)
        if frozen is None:
            return None
        return (
            "enum",
            type(value).__module__,
            type(value).__qualname__,
            frozen,
        )
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields: list[tuple[str, Any]] = []
        for field in dataclasses.fields(value):
            frozen = _freeze_identity(getattr(value, field.name))
            if frozen is None:
                return None
            fields.append((field.name, frozen))
        return (
            "dataclass",
            type(value).__module__,
            type(value).__qualname__,
            tuple(fields),
        )
    if type(value) is tuple:
        items = []
        for item in value:
            frozen = _freeze_identity(item)
            if frozen is None:
                return None
            items.append(frozen)
        return ("tuple", tuple(items))
    if type(value) is list:
        items = []
        for item in value:
            frozen = _freeze_identity(item)
            if frozen is None:
                return None
            items.append(frozen)
        return ("list", tuple(items))
    if isinstance(value, Mapping):
        items = []
        for key, item in value.items():
            frozen_key = _freeze_identity(key)
            frozen_item = _freeze_identity(item)
            if frozen_key is None or frozen_item is None:
                return None
            items.append((frozen_key, frozen_item))
        try:
            ordered = tuple(sorted(items, key=repr))
        except (TypeError, ValueError):
            return None
        return ("mapping", ordered)
    return None


def _history_identity(shadow: Any, source: Any) -> tuple[Any, ...] | None:
    if type(source) is not shadow.CurrentUtcNativeShadowPredictionSourceBundle:
        return None
    bootstrap_raw = getattr(source, "legacy_bootstrap_projection_raw", None)
    settlements = getattr(source, "reviewed_fresh_settlements", None)
    if type(bootstrap_raw) is not bytes or type(settlements) is not tuple:
        return None
    settlement_rows: list[Any] = []
    for settlement in settlements:
        if type(settlement) is not shadow.fresh.SettledFreshPrediction:
            return None
        frozen = _freeze_identity(settlement)
        if frozen is None:
            return None
        settlement_rows.append(frozen)
    return (
        "history-v1",
        len(bootstrap_raw),
        hashlib.sha256(bootstrap_raw).hexdigest(),
        tuple(settlement_rows),
    )


def _derive_identity(shadow: Any, source: Any) -> tuple[Any, ...] | None:
    history = _history_identity(shadow, source)
    if history is None:
        return None
    try:
        current_bootstrap_sha = source.current_bootstrap_sha256
        source_manifest_sha = source.source_manifest_sha256
        source_raw_sha = source.source_raw_sha256
    except Exception:
        return None
    for digest in (current_bootstrap_sha, source_manifest_sha, source_raw_sha):
        if (
            type(digest) is not str
            or len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest)
        ):
            return None
    return (
        "derive-v1",
        current_bootstrap_sha,
        source_manifest_sha,
        source_raw_sha,
        history,
    )


def install(
    shadow: Any,
    *,
    diagnostic_path: Path | None = None,
) -> SemanticReplayReuseHooks:
    """Install exact semantic reuse around the existing PR244 private replays."""

    original_derive = shadow._derive_shadow_state
    original_ledger = shadow._history_ledger
    stats = SemanticReplayReuseStats()
    derive_cache: dict[tuple[Any, ...], Any] = {}
    ledger_cache: dict[tuple[Any, ...], tuple[Any, int]] = {}
    lock = threading.Lock()

    def emit(last_operation: str) -> None:
        with lock:
            derive_entries = len(derive_cache)
            ledger_entries = len(ledger_cache)
        _write_diagnostic(
            diagnostic_path,
            stats=stats,
            last_operation=last_operation,
            derive_cache_entries=derive_entries,
            ledger_cache_entries=ledger_entries,
        )

    def history_ledger(source):
        key = _history_identity(shadow, source)
        if key is None:
            stats.increment("uncacheable_fallbacks")
            emit("HISTORY_LEDGER_UNCACHEABLE_FALLBACK")
            return original_ledger(source)
        with lock:
            cached = ledger_cache.get(key)
        if cached is not None:
            stats.increment("history_ledger_reused")
            emit("HISTORY_LEDGER_REUSED")
            return cached
        try:
            value = original_ledger(source)
        except Exception:
            stats.increment("failures_not_cached")
            emit("HISTORY_LEDGER_FAILED_NOT_CACHED")
            raise
        with lock:
            ledger_cache[key] = value
        stats.increment("history_ledger_authoritative_executed")
        emit("HISTORY_LEDGER_AUTHORITATIVE_EXECUTED")
        return value

    def derive_shadow_state(source):
        key = _derive_identity(shadow, source)
        if key is None:
            stats.increment("uncacheable_fallbacks")
            emit("DERIVE_UNCACHEABLE_FALLBACK")
            return original_derive(source)
        with lock:
            cached = derive_cache.get(key)
        if cached is not None:
            stats.increment("derive_reused")
            emit("DERIVE_REUSED")
            return cached
        try:
            value = original_derive(source)
        except Exception:
            stats.increment("failures_not_cached")
            emit("DERIVE_FAILED_NOT_CACHED")
            raise
        with lock:
            derive_cache[key] = value
        stats.increment("derive_authoritative_executed")
        emit("DERIVE_AUTHORITATIVE_EXECUTED")
        return value

    shadow._history_ledger = history_ledger
    shadow._derive_shadow_state = derive_shadow_state
    return SemanticReplayReuseHooks(
        original_derive_shadow_state=original_derive,
        original_history_ledger=original_ledger,
        stats=stats,
        diagnostic_path=diagnostic_path,
    )


def restore(shadow: Any, hooks: SemanticReplayReuseHooks) -> None:
    if type(hooks) is not SemanticReplayReuseHooks:
        raise TypeError("hooks must be SemanticReplayReuseHooks")
    shadow._derive_shadow_state = hooks.original_derive_shadow_state
    shadow._history_ledger = hooks.original_history_ledger


__all__ = [
    "DIAGNOSTIC_DATASET_NAME",
    "DIAGNOSTIC_SCHEMA_VERSION",
    "SemanticReplayReuseHooks",
    "SemanticReplayReuseStats",
    "install",
    "restore",
]
