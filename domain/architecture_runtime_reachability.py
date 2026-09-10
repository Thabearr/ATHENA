"""Deterministic evidence-only runtime reachability tracing for ATHENA P0.5.

This module is intentionally generic. It records reviewed execution checkpoints
without granting production, pricing, selection, router, portfolio, delivery,
or cleanup authority. Importing a module is never itself an execution event.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
import hashlib
import json
from typing import Any, Callable, Iterator, Mapping, MutableMapping

SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_RUNTIME_REACHABILITY_V1"

CHECKPOINT_KINDS = frozenset({
    "ENTRYPOINT",
    "ORCHESTRATION",
    "SUPPORTING_LOGIC",
    "DECISION_AUTHORITY",
    "DELIVERY",
    "TERMINUS",
})

AUTHORITY_CATEGORIES = frozenset({
    "NONE",
    "MODEL_ANALYSIS",
    "LEGACY_MARKET_SELECTION",
    "ACCUMULATOR_FILTERING",
    "ACCUMULATOR_CONSTRUCTION",
    "PRICE_ALL",
    "MARKET_ROUTING",
    "PORTFOLIO_CONSTRUCTION",
    "DELIVERY_ONLY",
})

RUNTIME_DISPOSITIONS = frozenset({
    "IMPORTED_ONLY",
    "EXECUTED_SUPPORTING_LOGIC",
    "EXECUTED_DECISION_AUTHORITY",
    "EXECUTED_DELIVERY_ONLY",
    "NO_DECISION_AUTHORITY_REACHED",
    "SYNTHETIC_EXECUTION_NOT_YET_PROVEN",
})


class RuntimeReachabilityError(ValueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize deterministic evidence JSON with no implicit coercion."""
    try:
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
    except (TypeError, ValueError, OverflowError) as exc:
        raise RuntimeReachabilityError("runtime evidence is not canonically serializable") from exc


def sha256_canonical(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha(value: str, label: str) -> str:
    if type(value) is not str:
        raise RuntimeReachabilityError(f"{label} must be an exact string")
    lowered = value.lower()
    if len(lowered) != 40 or any(ch not in "0123456789abcdef" for ch in lowered):
        raise RuntimeReachabilityError(f"{label} must be an exact 40-character Git SHA")
    return lowered


def _identity(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise RuntimeReachabilityError(f"{label} must be an exact string or null")
    lowered = value.lower()
    if len(lowered) != 64 or any(ch not in "0123456789abcdef" for ch in lowered):
        raise RuntimeReachabilityError(f"{label} must be an exact SHA-256 or null")
    return lowered


def _exact_text(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise RuntimeReachabilityError(f"{label} must be non-empty exact text")
    return value


@dataclass(frozen=True)
class TraceToken:
    index: int


class RuntimeTrace:
    """Ordered trace for one supported-root synthetic execution case.

    A checkpoint is appended at function entry and completed in place after the
    wrapped function returns. This preserves call-entry order even for nested
    wrappers while still retaining a deterministic output identity when the
    caller supplies one.
    """

    def __init__(
        self,
        *,
        source_commit: str,
        supported_root: str,
        root_authority_profile: str,
        synthetic_case_id: str,
    ) -> None:
        self.source_commit = _sha(source_commit, "source_commit")
        self.supported_root = _exact_text(supported_root, "supported_root")
        self.root_authority_profile = _exact_text(
            root_authority_profile,
            "root_authority_profile",
        )
        self.synthetic_case_id = _exact_text(synthetic_case_id, "synthetic_case_id")
        self._records: list[MutableMapping[str, Any]] = []

    @property
    def records(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(dict(item) for item in self._records)

    def begin(
        self,
        *,
        module: str,
        qualname: str,
        checkpoint_kind: str,
        authority_category: str,
        input_identity: str | None = None,
        notes: tuple[str, ...] = (),
    ) -> TraceToken:
        module = _exact_text(module, "module")
        qualname = _exact_text(qualname, "qualname")
        if checkpoint_kind not in CHECKPOINT_KINDS:
            raise RuntimeReachabilityError("checkpoint_kind escaped reviewed vocabulary")
        if authority_category not in AUTHORITY_CATEGORIES:
            raise RuntimeReachabilityError("authority_category escaped reviewed vocabulary")
        if type(notes) is not tuple or any(type(item) is not str for item in notes):
            raise RuntimeReachabilityError("notes must be an exact tuple of strings")
        record: MutableMapping[str, Any] = {
            "sequence": len(self._records),
            "module": module,
            "qualname": qualname,
            "checkpoint_kind": checkpoint_kind,
            "authority_category": authority_category,
            "input_identity": _identity(input_identity, "input_identity"),
            "output_identity": None,
            "outcome": "ENTERED",
            "notes": list(notes),
        }
        self._records.append(record)
        return TraceToken(index=len(self._records) - 1)

    def finish(
        self,
        token: TraceToken,
        *,
        output_identity: str | None = None,
        notes: tuple[str, ...] = (),
    ) -> None:
        if type(token) is not TraceToken or not 0 <= token.index < len(self._records):
            raise RuntimeReachabilityError("trace token is invalid")
        if type(notes) is not tuple or any(type(item) is not str for item in notes):
            raise RuntimeReachabilityError("notes must be an exact tuple of strings")
        record = self._records[token.index]
        if record["outcome"] != "ENTERED":
            raise RuntimeReachabilityError("trace checkpoint was already completed")
        record["output_identity"] = _identity(output_identity, "output_identity")
        record["outcome"] = "RETURNED"
        record["notes"].extend(notes)

    def fail(self, token: TraceToken, exc: BaseException) -> None:
        if type(token) is not TraceToken or not 0 <= token.index < len(self._records):
            raise RuntimeReachabilityError("trace token is invalid")
        record = self._records[token.index]
        if record["outcome"] != "ENTERED":
            raise RuntimeReachabilityError("trace checkpoint was already completed")
        record["outcome"] = "RAISED"
        record["notes"].append(f"exception_type={type(exc).__name__}")

    def to_dict(self, *, disposition: str) -> dict[str, Any]:
        if disposition not in RUNTIME_DISPOSITIONS:
            raise RuntimeReachabilityError("runtime disposition escaped reviewed vocabulary")
        if any(item["outcome"] == "ENTERED" for item in self._records):
            raise RuntimeReachabilityError("runtime trace contains unfinished checkpoints")
        return {
            "schema_version": SCHEMA_VERSION,
            "trace_policy_id": POLICY_ID,
            "source_commit": self.source_commit,
            "supported_root": self.supported_root,
            "root_authority_profile": self.root_authority_profile,
            "synthetic_case_id": self.synthetic_case_id,
            "runtime_disposition": disposition,
            "checkpoints": [dict(item) for item in self._records],
            "authority": {
                "production_model": False,
                "production_probability": False,
                "production_price_all": False,
                "production_market_router": False,
                "production_portfolio": False,
                "production_selection": False,
                "login": False,
                "cookies": False,
                "wallet": False,
                "staking": False,
                "bet": False,
                "wager_placed": False,
                "cleanup_authority": "NONE",
            },
        }


@contextmanager
def scoped_callable_checkpoint(
    owner: Any,
    attribute: str,
    *,
    trace: RuntimeTrace,
    module: str,
    qualname: str,
    checkpoint_kind: str,
    authority_category: str,
    input_identity: Callable[[tuple[Any, ...], dict[str, Any]], str | None] | None = None,
    output_identity: Callable[[Any], str | None] | None = None,
    notes: tuple[str, ...] = (),
) -> Iterator[Callable[..., Any]]:
    """Temporarily wrap one callable and restore it unconditionally.

    The wrapper does not alter arguments, return values, or exceptions. It is
    intentionally scoped and must never be used to imply that importability is
    execution authority.
    """

    original = getattr(owner, attribute)
    if not callable(original):
        raise RuntimeReachabilityError(
            f"{module}.{qualname} is not callable at instrumentation time"
        )

    @wraps(original)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        input_sha = None if input_identity is None else input_identity(args, kwargs)
        token = trace.begin(
            module=module,
            qualname=qualname,
            checkpoint_kind=checkpoint_kind,
            authority_category=authority_category,
            input_identity=input_sha,
            notes=notes,
        )
        try:
            result = original(*args, **kwargs)
        except BaseException as exc:
            trace.fail(token, exc)
            raise
        output_sha = None if output_identity is None else output_identity(result)
        trace.finish(token, output_identity=output_sha)
        return result

    setattr(owner, attribute, wrapped)
    try:
        yield original
    finally:
        setattr(owner, attribute, original)


def validate_trace_document(value: Any) -> dict[str, Any]:
    if type(value) is not dict:
        raise RuntimeReachabilityError("runtime trace document must be an object")
    required = {
        "schema_version",
        "trace_policy_id",
        "source_commit",
        "supported_root",
        "root_authority_profile",
        "synthetic_case_id",
        "runtime_disposition",
        "checkpoints",
        "authority",
    }
    if set(value) != required:
        raise RuntimeReachabilityError("runtime trace document fields drifted")
    if value["schema_version"] != SCHEMA_VERSION or value["trace_policy_id"] != POLICY_ID:
        raise RuntimeReachabilityError("runtime trace contract identity drifted")
    _sha(value["source_commit"], "source_commit")
    _exact_text(value["supported_root"], "supported_root")
    _exact_text(value["root_authority_profile"], "root_authority_profile")
    _exact_text(value["synthetic_case_id"], "synthetic_case_id")
    if value["runtime_disposition"] not in RUNTIME_DISPOSITIONS:
        raise RuntimeReachabilityError("runtime disposition escaped reviewed vocabulary")
    if type(value["checkpoints"]) is not list:
        raise RuntimeReachabilityError("checkpoints must be a list")
    for sequence, item in enumerate(value["checkpoints"]):
        if type(item) is not dict:
            raise RuntimeReachabilityError("checkpoint must be an object")
        if item.get("sequence") != sequence:
            raise RuntimeReachabilityError("checkpoint sequence is not contiguous")
        if item.get("checkpoint_kind") not in CHECKPOINT_KINDS:
            raise RuntimeReachabilityError("checkpoint kind drifted")
        if item.get("authority_category") not in AUTHORITY_CATEGORIES:
            raise RuntimeReachabilityError("checkpoint authority category drifted")
        if item.get("outcome") not in {"RETURNED", "RAISED"}:
            raise RuntimeReachabilityError("checkpoint outcome is invalid")
        _identity(item.get("input_identity"), "input_identity")
        _identity(item.get("output_identity"), "output_identity")
    authority = value["authority"]
    if type(authority) is not dict or authority.get("cleanup_authority") != "NONE":
        raise RuntimeReachabilityError("runtime evidence attempted to grant cleanup authority")
    forbidden_true = {
        "production_model",
        "production_probability",
        "production_price_all",
        "production_market_router",
        "production_portfolio",
        "production_selection",
        "login",
        "cookies",
        "wallet",
        "staking",
        "bet",
        "wager_placed",
    }
    if any(authority.get(key) is not False for key in forbidden_true):
        raise RuntimeReachabilityError("runtime evidence attempted to grant forbidden authority")
    return value


__all__ = [
    "AUTHORITY_CATEGORIES",
    "CHECKPOINT_KINDS",
    "POLICY_ID",
    "RUNTIME_DISPOSITIONS",
    "RuntimeReachabilityError",
    "RuntimeTrace",
    "SCHEMA_VERSION",
    "canonical_json_bytes",
    "scoped_callable_checkpoint",
    "sha256_canonical",
    "validate_trace_document",
]
