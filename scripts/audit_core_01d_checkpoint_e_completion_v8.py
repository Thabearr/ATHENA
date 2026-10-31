"""Derive the current Checkpoint-E overlay after B5's four replay reviews."""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
import hashlib
import json
import os
import stat
import sys
import threading
import types
from typing import Any

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary

ROOT = boundary.ROOT
POLICY_ID = "ATHENA_CORE_01D_CHECKPOINT_E_COMPLETION_V8"
PARENT_SHA = "a047bcf6b5fadd2118f6c817b03a43312e0a9094a1269f4b6b22750c5e638512"
RECEIPT_PATH = "tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v8.json"
EXPECTED_FINAL_KEYS = {
    (".github/workflows/port-02c-native-runtime.yml", "pull_request"),
    (".github/workflows/port-02c-native-runtime.yml", "workflow_dispatch"),
    (".github/workflows/validate-win-either-half-campaign-commitment.yml", "pull_request"),
}
_CONTRACT_EXTERNAL_ROOTS = tuple(
    sys.modules[name]
    for name in ("sitecustomize", "offline_transport", "tests.offline_transport",
                 "offline_linux", "tests.offline_linux")
    if isinstance(sys.modules.get(name), types.ModuleType)
)


def _runtime_container(module_name: str, name: str, value: Any) -> bool:
    """Identify mutable telemetry/cache containers whose contents are runtime state."""
    if not isinstance(value, (dict, list, set)):
        return False
    upper = name.upper()
    if any(token in upper for token in (
            "CACHE", "CACHED", "TELEMETRY", "METRIC", "COUNTER", "TIMING",
            "EVENT_LOG", "TRACE_LOG", "SAMPLE_LOG")):
        return True
    # Offline transport modules may maintain mutable audit-hook telemetry.
    # Their immutable command/guard constants remain part of the contract.
    return (module_name.rsplit(".", 1)[-1] in {"offline_transport", "offline_linux"}
            and name.startswith("_")
            and any(token in upper for token in ("STATE", "OBSERVED", "SEEN", "EVENTS")))


def _runtime_global(module_name: str, name: str, value: Any) -> tuple[Any, ...] | None:
    """Return a stable descriptor for known runtime state, else None."""
    if (module_name == "scripts.audit_core_01d_ci_offline_transport_boundary"
            and name in {"_A2_SCOPED_FUNCTION_BASELINES", "_A2_SCOPED_RULE_BASELINES"}):
        # The auditor module binds every verifier and immutable rule directly.
        # Rewalking these two duplicate baseline tables from every transitive
        # contract hash adds no independent authority and is prohibitively costly.
        return ("a2-scoped-baseline-table", id(value))
    if (module_name == "scripts.audit_checkpoint_e_workflows"
            and name == "_VERIFIED_ADDITIVE_PATHS"):
        # Pre-existing path-list memo, populated by the checkpoint helper
        # after its bounded scope exits. It is not a trusted verifier input.
        return ("preexisting-path-list-cache",)
    if _runtime_container(module_name, name, value):
        return ("runtime-container", type(value).__module__, type(value).__qualname__, id(value))
    if (module_name.rsplit(".", 1)[-1] in {"offline_transport", "offline_linux"}
            and name in {"_active", "_installed", "_syscall", "_audited_argv"}):
        # These change as the guard installs or scopes an exact local command;
        # their trusted code and immutable policy constants remain hashed.
        identity = () if name in {"_active", "_installed"} else (id(value),)
        return ("runtime-state", type(value).__module__, type(value).__qualname__, *identity)
    return None


def _code_constant(value: Any) -> Any:
    """Normalize immutable code constants without marshal's runtime encoding."""
    value_type = type(value)
    if value is None or value is Ellipsis or value is NotImplemented:
        return (value_type.__qualname__,)
    if value_type in {bool, int, str, bytes}:
        return (value_type.__qualname__, value)
    if value_type is float:
        return ("float", value.hex())
    if value_type is complex:
        return ("complex", value.real.hex(), value.imag.hex())
    if value_type is types.CodeType:
        return ("code", _code_digest(value))
    if value_type is tuple:
        return ("tuple", tuple(_code_constant(item) for item in value))
    if value_type is frozenset:
        items = [_code_constant(item) for item in value]
        return ("frozenset", tuple(sorted(items, key=repr)))
    # CPython code constants are immutable. Keep any implementation-specific
    # constant bound to this process object rather than invoking repr() on it.
    return (value_type.__module__, value_type.__qualname__, id(value))


@lru_cache(maxsize=8192)
def _code_digest(code: types.CodeType) -> str:
    """Hash stable code-object fields, not adaptive bytecode marshal output."""
    payload = (
        code.co_argcount, code.co_posonlyargcount, code.co_kwonlyargcount,
        code.co_nlocals, code.co_stacksize, code.co_flags, code.co_code,
        tuple(_code_constant(item) for item in code.co_consts),
        code.co_names, code.co_varnames, code.co_freevars, code.co_cellvars,
        code.co_filename, code.co_name, code.co_qualname, code.co_firstlineno,
        code.co_linetable, code.co_exceptiontable,
    )
    return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()


def _contract_value(value: Any, seen: set[int] | None = None,
                    *, include_mutable_contents: bool = True) -> Any:
    """Bind code, defaults, closures and stable values without repr() side effects."""
    value_type = type(value)
    if value is None or value_type in {bool, int, float, str, bytes}:
        return (value_type.__qualname__, value)
    if value_type is types.CodeType:
        return ("code", _code_digest(value))
    if seen is None:
        seen = set()
    identity = id(value)
    if identity in seen:
        return (value_type.__module__, value_type.__qualname__, "CYCLE", identity)
    if value_type in {tuple, list, set, frozenset, dict}:
        if value_type in {list, set, dict} and not include_mutable_contents:
            return (value_type.__qualname__, identity)
        seen.add(identity)
        try:
            if value_type is dict:
                pairs = [(_contract_value(key, seen,
                                          include_mutable_contents=include_mutable_contents),
                          _contract_value(item, seen,
                                          include_mutable_contents=include_mutable_contents))
                         for key, item in value.items()]
                return ("dict", identity, tuple(sorted(pairs, key=repr)))
            items = [_contract_value(item, seen,
                                     include_mutable_contents=include_mutable_contents)
                     for item in value]
            if value_type in {set, frozenset}:
                items.sort(key=repr)
            return (value_type.__qualname__,
                    identity if value_type in {list, set} else None, tuple(items))
        finally:
            seen.remove(identity)
    if isinstance(value, types.ModuleType):
        return ("module", value.__name__, identity)
    if isinstance(value, types.FunctionType):
        code_sha256 = _code_digest(value.__code__)
        closure = () if value.__closure__ is None else tuple(
            _contract_value(cell.cell_contents, seen,
                            include_mutable_contents=include_mutable_contents)
            for cell in value.__closure__
        )
        attributes = tuple((name, _contract_value(
            item, seen, include_mutable_contents=include_mutable_contents))
                           for name, item in sorted(vars(value).items()))
        return ("function", identity, code_sha256,
                _contract_value(value.__defaults__, seen,
                                include_mutable_contents=include_mutable_contents),
                _contract_value(value.__kwdefaults__, seen,
                                include_mutable_contents=include_mutable_contents), closure, attributes)
    if isinstance(value, type):
        if not value.__module__.startswith("scripts.audit_"):
            return ("class", value.__module__, value.__qualname__, identity)
        seen.add(identity)
        try:
            attributes = tuple(
                (name, _contract_value(item, seen,
                                       include_mutable_contents=include_mutable_contents))
                for name, item in sorted(vars(value).items())
                if name not in {"__dict__", "__weakref__"}
            )
            return ("class", value.__module__, value.__qualname__, identity, attributes)
        finally:
            seen.remove(identity)
    return (value_type.__module__, value_type.__qualname__, identity)


def _auditor_contract_digest(*roots: types.ModuleType) -> str:
    """Import-time trust digest: executable code and stable validator contract only.

    Mutable semantic constants are included, except named runtime telemetry/cache
    containers. Cache contents therefore cannot invalidate a trusted contract.
    """
    digest = hashlib.sha256()
    scope_module = sys.modules[__name__]
    # Other auditors can import this scope engine while V8 is still importing.
    # Bind the already-defined scope kernel in that case; when V8 is an explicit
    # target root, its complete auditor module is included below.
    include_scope_module = any(root is scope_module for root in roots)
    pending = [*roots, boundary]
    if include_scope_module:
        pending.append(scope_module)
    pending.extend(_CONTRACT_EXTERNAL_ROOTS)
    modules: dict[str, types.ModuleType] = {}
    while pending:
        module = pending.pop()
        if module.__name__ in modules:
            continue
        modules[module.__name__] = module
        for name, value in vars(module).items():
            # Excluded aliases must not affect the transitive module set either:
            # while V8 is importing a predecessor, this alias can point at the
            # partially initialized V8 module and would otherwise hash a
            # different module graph before and after V8 finishes importing.
            if (name == "__builtins__" or name == "_receipt_scope_module"
                    or name.startswith("_TRUSTED_") and name.endswith("_CONTRACT")):
                continue
            if (isinstance(value, types.ModuleType)
                    and value.__name__.startswith("scripts.audit_")):
                pending.append(value)
    for module_name, module in sorted(modules.items()):
        digest.update(module_name.encode("utf-8") + b"\0")
        digest.update(repr((id(module), id(sys.modules.get(module_name)))).encode("ascii") + b"\0")
        for name, value in sorted(vars(module).items()):
            if (name == "__builtins__" or name == "_receipt_scope_module"
                    or name.startswith("_TRUSTED_") and name.endswith("_CONTRACT")):
                continue
            digest.update(name.encode("utf-8") + b"\0")
            runtime = _runtime_global(module.__name__, name, value)
            if runtime is not None:
                # Cache/telemetry contents and known guard installation state
                # are excluded. Semantic mutable constants stay content-bound.
                digest.update(repr(runtime).encode("utf-8") + b"\0")
            else:
                digest.update(repr(_contract_value(value, include_mutable_contents=True)).encode("utf-8") + b"\0")
    if not include_scope_module:
        digest.update(repr(_scope_engine_projection()).encode("utf-8") + b"\0")
    return digest.hexdigest()


def _auditor_live_contract_digest(*roots: types.ModuleType,
                                  _components: dict[str, str] | None = None) -> str:
    """Scope-local binding digest; telemetry contents may change, seams may not."""
    digest = hashlib.sha256()
    scope_module = sys.modules[__name__]
    include_scope_module = any(root is scope_module for root in roots)
    pending = [*roots, boundary]
    if include_scope_module:
        pending.append(scope_module)
    pending.extend(_CONTRACT_EXTERNAL_ROOTS)
    modules: dict[str, types.ModuleType] = {}
    while pending:
        module = pending.pop()
        if module.__name__ in modules:
            continue
        modules[module.__name__] = module
        for name, value in vars(module).items():
            if (name == "__builtins__" or name == "_receipt_scope_module"
                    or name.startswith("_TRUSTED_") and name.endswith("_CONTRACT")):
                continue
            if (isinstance(value, types.ModuleType)
                    and value.__name__.startswith("scripts.audit_")):
                pending.append(value)
    for module_name, module in sorted(modules.items()):
        digest.update(module_name.encode("utf-8") + b"\0")
        digest.update(repr((id(module), id(sys.modules.get(module_name)))).encode("ascii") + b"\0")
        for name, value in sorted(vars(module).items()):
            if (name == "__builtins__" or name == "_receipt_scope_module"
                    or name.startswith("_TRUSTED_") and name.endswith("_CONTRACT")):
                continue
            digest.update(name.encode("utf-8") + b"\0")
            runtime = _runtime_global(module.__name__, name, value)
            if runtime is not None:
                representation = runtime
            else:
                representation = _contract_value(value, include_mutable_contents=True)
            encoded = repr(representation).encode("utf-8")
            digest.update(encoded + b"\0")
            if _components is not None:
                _components[module_name + ":" + name] = hashlib.sha256(encoded).hexdigest()
    if not include_scope_module:
        digest.update(repr(_scope_engine_projection()).encode("utf-8") + b"\0")
    return digest.hexdigest()


_SCOPE_ENGINE_NAMES = (
    "ROOT", "_CONTRACT_EXTERNAL_ROOTS", "asyncio", "boundary", "contextmanager",
    "ContextVar", "lru_cache", "hashlib", "json", "os", "stat", "sys",
    "threading", "types", "_runtime_container", "_runtime_global",
    "_code_constant", "_code_digest", "_contract_value",
    "_auditor_contract_digest", "_auditor_live_contract_digest",
    "_execution_state_digest", "_execution_unit", "_BoundedReceiptScope",
    "_ACTIVE_RECEIPT_SCOPES", "_SCOPE_METRICS", "_record_scope_metric",
    "_SCOPE_ENGINE_NAMES", "_STATE_ENVIRONMENT_EXCLUSIONS",
    "_scope_engine_projection", "_bounded_receipt_scope",
    "_active_receipt_scope", "require",
)


def _scope_engine_projection() -> tuple[Any, ...]:
    module = sys.modules[__name__]
    values = vars(module)
    return tuple((name, _contract_value(values[name], include_mutable_contents=True))
                 for name in _SCOPE_ENGINE_NAMES if name in values)


_STATE_ENVIRONMENT_EXCLUSIONS = frozenset({
    "OPENBLAS_MAIN_FREE", "GOTOBLAS_MAIN_FREE", "KMP_DUPLICATE_LIB_OK",
    "KMP_INIT_AT_FORK", "PYTEST_CURRENT_TEST", "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
})


def _execution_state_digest(*, _components: dict[str, str] | None = None,
                            _include_git: bool = True,
                            _include_a2: bool = True) -> str:
    """Bind scoped reuse to fresh Git/worktree and A2 state components.

    The default remains the complete entry/exit snapshot. A2 cache hits may
    request only the Git/worktree portion and compare selected A2 bytes after
    a cheap live namespace/stat pass.
    """
    digest = hashlib.sha256()

    def add(label: str, raw: bytes) -> None:
        label_bytes = label.encode("utf-8")
        digest.update(len(label_bytes).to_bytes(8, "big"))
        digest.update(label_bytes)
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
        if _components is not None:
            require(label not in _components,
                    "duplicate receipt execution-state component label: " + label)
            _components[label] = hashlib.sha256(raw).hexdigest()

    repository_root = ROOT.resolve(strict=True)
    add("root", str(repository_root).encode("utf-8"))
    if _include_git:
        for args in (
            ("rev-parse", "--symbolic-full-name", "HEAD"),
            ("rev-parse", "HEAD"),
            ("ls-files", "--stage", "-z"),
            ("diff", "--binary", "--no-ext-diff", "--no-textconv", "HEAD"),
            ("config", "--show-scope", "--null", "--list"),
        ):
            add("git " + " ".join(args), boundary.git(*args))
        environment = b"\0".join(
            os.fsencode(key) + b"=" + os.fsencode(value)
            for key, value in sorted(os.environ.items())
            if key not in _STATE_ENVIRONMENT_EXCLUSIONS
        )
        add("environment", environment)

    if _include_a2:
        inventory_root = ROOT / boundary.INVENTORY_DIRECTORY
        inventory_root_stat = inventory_root.lstat()
        add("a2-directory-mode", stat.S_IMODE(inventory_root_stat.st_mode).to_bytes(4, "big"))
        if stat.S_ISLNK(inventory_root_stat.st_mode):
            add("a2-directory-link", os.fsencode(os.readlink(inventory_root)))
        inventory_directory = inventory_root.resolve(strict=True)
        add("a2-directory", str(inventory_directory).encode("utf-8"))
        for path in sorted(inventory_directory.iterdir(), key=lambda item: item.name):
            if not path.name.startswith(boundary.INVENTORY_PREFIX):
                continue
            metadata = path.lstat()
            require(stat.S_ISREG(metadata.st_mode),
                    "A2 generation observation encountered a non-regular file")
            add("a2-path-stat:" + path.name, repr((metadata.st_mode, metadata.st_ino,
                metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns)).encode("ascii"))
            add("a2-path-mode:" + path.name, path.name.encode("utf-8") + b"\0" +
                stat.S_IMODE(metadata.st_mode).to_bytes(4, "big"))
            add("a2-bytes:" + path.name, path.read_bytes())

    if _include_git:
        untracked = boundary.git("ls-files", "--others", "--exclude-standard", "-z")
        add("untracked-list", untracked)
        for raw_path in untracked.split(b"\0"):
            if not raw_path:
                continue
            relative = os.fsdecode(raw_path)
            path = ROOT / relative
            resolved_parent = path.parent.resolve(strict=True)
            require(resolved_parent == repository_root
                    or repository_root in resolved_parent.parents,
                    "untracked source observation escaped repository root")
            metadata = path.lstat()
            add("untracked-path-mode:" + relative, raw_path + b"\0" +
                stat.S_IMODE(metadata.st_mode).to_bytes(4, "big"))
            if stat.S_ISREG(metadata.st_mode):
                add("untracked-bytes:" + relative, path.read_bytes())
            elif stat.S_ISLNK(metadata.st_mode):
                add("untracked-link:" + relative, os.fsencode(os.readlink(path)))
            else:
                raise AssertionError("untracked source observation encountered a special file")
    return digest.hexdigest()


def _execution_unit() -> tuple[int, int, int | None]:
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    return os.getpid(), threading.get_ident(), None if task is None else id(task)


class _BoundedReceiptScope:
    """One-call immutable receipt reuse; never stores a PASS verdict.

    Each reuse is guarded by fresh state and verifier-contract observations.
    A mutation that is fully reverted between observations is an explicit
    filesystem/in-memory ABA limitation, not an atomic-snapshot guarantee.
    """

    def __init__(self, key: str, roots: tuple[types.ModuleType, ...],
                 trusted_contract: str) -> None:
        self.key = key
        self.roots = roots
        self.trusted_contract = trusted_contract
        self.enabled = False
        self.contract_at_entry = ""
        self.live_contract_at_entry = ""
        self.live_contract_components_at_entry: dict[str, str] = {}
        self.state_at_entry = ""
        self.state_components_at_entry: dict[str, str] = {}
        self.unit = _execution_unit()
        self.state_owner: _BoundedReceiptScope = self
        self.receipt_reuse_disabled = False
        self.receipt_bytes: bytes | None = None
        # Opaque immutable derivation payloads are confined to this one scope.
        # Callers supply a live verifier-contract digest. The first derivation
        # access and the owning scope's exit recheck HEAD, index, worktree, Git
        # config and A2 bytes; intermediate hits recheck verifier code/unit.
        self.derivation_bytes: dict[str, tuple[str, bytes]] = {}
        self.derivation_objects: dict[str, Any] = {}
        self.derivation_state_checked = False
        self.token: Any = None

    def __enter__(self) -> "_BoundedReceiptScope":
        self.contract_at_entry = _auditor_contract_digest(*self.roots)
        self.live_contract_at_entry = _auditor_live_contract_digest(
            *self.roots, _components=self.live_contract_components_at_entry)
        self.enabled = self.contract_at_entry == self.trusted_contract
        _record_scope_metric(self.key + (".enabled" if self.enabled else ".disabled"))
        require(self.enabled,
                "trusted auditor contract mismatch; bounded receipt reuse disabled")
        scopes = dict(_ACTIVE_RECEIPT_SCOPES.get())
        require(self.key not in scopes, "nested receipt reuse scope for the same verifier")
        active_scopes = tuple(scopes.values())
        outer = next((scope for scope in active_scopes
                      if getattr(scope, "enabled", False)
                      and getattr(scope, "unit", None) == self.unit), None)
        self.receipt_reuse_disabled = any(
            getattr(scope, "receipt_reuse_disabled", False)
            for scope in active_scopes
            if getattr(scope, "unit", None) == self.unit
        )
        if outer is None:
            self.state_at_entry = _execution_state_digest(
                _components=self.state_components_at_entry)
            self.state_owner = self
        else:
            owner = getattr(outer, "state_owner", outer)
            self.state_owner = owner
            self.state_at_entry = owner.state_at_entry
            self.state_components_at_entry = dict(owner.state_components_at_entry)
            self.derivation_state_checked = owner.derivation_state_checked
        scopes[self.key] = self
        self.token = _ACTIVE_RECEIPT_SCOPES.set(scopes)
        return self

    def _assert_live_contract_unchanged(self) -> None:
        current_contract = _auditor_live_contract_digest(*self.roots)
        if current_contract == self.live_contract_at_entry:
            return
        current_components: dict[str, str] = {}
        _auditor_live_contract_digest(*self.roots, _components=current_components)
        changed = sorted(
            name for name in set(self.live_contract_components_at_entry)
            | set(current_components)
            if self.live_contract_components_at_entry.get(name) != current_components.get(name)
        )
        detail = ", ".join(changed[:12]) or "<unlocalized contract drift>"
        raise AssertionError(
            "auditor code or monkeypatched verifier attributes changed in receipt scope: "
            + detail)

    def _unchanged(self, *, verify_state: bool = True) -> None:
        require(_execution_unit() == self.unit,
                "receipt reuse scope crossed process, thread, or async-task boundary")
        self._assert_live_contract_unchanged()
        if verify_state and self.enabled and self.state_owner is not self:
            self.state_owner._unchanged()
            return
        if self.enabled and verify_state and self.state_owner is self:
            current_components: dict[str, str] = {}
            current_state = _execution_state_digest(_components=current_components)
            if current_state != self.state_at_entry:
                changed = sorted(
                    label for label in set(self.state_components_at_entry)
                    | set(current_components)
                    if self.state_components_at_entry.get(label) != current_components.get(label)
                )
                detail = ", ".join(changed[:20]) or "<unlocalized state drift>"
                raise AssertionError(
                    "receipt execution state changed during scope: " + detail)

    def _derivation_contract_unchanged(self) -> None:
        # Each derivation caller recomputes its exact verifier contract before
        # lookup and after calculation; load_derivation compares that fresh
        # contract with the stored immutable payload. The full transitive root
        # contract is checked at scope entry and exit, so repeating that deep
        # graph walk on every hit is redundant while the execution-unit fence
        # remains mandatory here.
        require(_execution_unit() == self.unit,
                "receipt reuse derivation crossed process, thread, or async-task boundary")

    def _check_derivation_state_once(self) -> None:
        owner = self.state_owner
        if owner.derivation_state_checked:
            self._derivation_contract_unchanged()
            return
        owner._unchanged()
        owner.derivation_state_checked = True

    def load(self) -> Any | None:
        _record_scope_metric(self.key + ".loads")
        if not self.enabled or self.receipt_reuse_disabled or self.receipt_bytes is None:
            _record_scope_metric(self.key + ".misses")
            return None
        self._unchanged(verify_state=False)
        _record_scope_metric(self.key + ".hits")
        return json.loads(self.receipt_bytes)

    def store(self, value: Any) -> None:
        _record_scope_metric(self.key + ".stores")
        if not self.enabled or self.receipt_reuse_disabled:
            return
        self._unchanged(verify_state=False)
        self.receipt_bytes = boundary.canonical(value)

    def load_derivation(self, name: str, contract: str) -> bytes | None:
        """Load same-call bytes inside the entry/exit-fenced receipt scope."""
        require(type(name) is str and type(contract) is str,
                "bounded derivation cache key is malformed")
        self._check_derivation_state_once()
        entry = self.derivation_bytes.get(name)
        if entry is None:
            _record_scope_metric(self.key + ".derivation_misses")
            return None
        prior_contract, payload = entry
        require(prior_contract == contract,
                "bounded derivation verifier contract changed within scope")
        require(type(payload) is bytes,
                "bounded derivation payload is not immutable bytes")
        _record_scope_metric(self.key + ".derivation_hits")
        return payload

    def store_derivation(self, name: str, contract: str, payload: bytes) -> None:
        require(type(name) is str and type(contract) is str and type(payload) is bytes,
                "bounded derivation cache entry is malformed")
        self._check_derivation_state_once()
        existing = self.derivation_bytes.get(name)
        require(existing is None or existing[0] == contract,
                "bounded derivation verifier contract changed before store")
        self.derivation_bytes[name] = (contract, payload)
        _record_scope_metric(self.key + ".derivation_stores")

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        try:
            # Nested scopes share the outer owner's execution-state snapshot.
            # Their own verifier contract is still checked, while only the
            # outer boundary performs the expensive full Git/A2 state scan.
            self._unchanged(verify_state=self.state_owner is self)
        finally:
            self.derivation_bytes.clear()
            self.derivation_objects.clear()
            self.receipt_bytes = None
            _record_scope_metric(self.key + ".exits")
            _ACTIVE_RECEIPT_SCOPES.reset(self.token)
        return False


_ACTIVE_RECEIPT_SCOPES: ContextVar[dict[str, _BoundedReceiptScope]] = ContextVar(
    "athena_checkpoint_receipt_scopes", default={})
_SCOPE_METRICS: ContextVar[dict[str, int] | None] = ContextVar(
    "athena_checkpoint_receipt_scope_metrics", default=None)


def _record_scope_metric(name: str, delta: int = 1) -> None:
    metrics = _SCOPE_METRICS.get()
    if metrics is not None:
        metrics[name] = metrics.get(name, 0) + delta


@contextmanager
def _bounded_receipt_scope(key: str, roots: tuple[types.ModuleType, ...],
                           trusted_contract: str):
    active = _ACTIVE_RECEIPT_SCOPES.get().get(key)
    if active is not None:
        require(active.roots == roots and active.trusted_contract == trusted_contract,
                "nested receipt scope contract differs from its active owner")
        _record_scope_metric(key + ".reentrant_entries")
        yield active
        return
    with _BoundedReceiptScope(key, roots, trusted_contract) as scope:
        yield scope


def _active_receipt_scope(key: str) -> _BoundedReceiptScope | None:
    scope = _ACTIVE_RECEIPT_SCOPES.get().get(key)
    if scope is not None and _execution_unit() != scope.unit:
        raise AssertionError("receipt reuse scope crossed process, thread, or async-task boundary")
    return scope


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AssertionError(reason)


from scripts import audit_core_01d_checkpoint_e_completion_v7 as completion_v7
from scripts import audit_core_01d_exact_pr_trigger_disposition_b1 as b1
from scripts import audit_core_01d_historical_warehouse_transfer_authority_b2 as b2
from scripts import audit_core_01d_frozen_artifact_replay_authority_b5 as b5

PARENT_PATH = completion_v7.RECEIPT_PATH
TARGET_KEYS = set(b5.TARGETS)


def build_receipt() -> dict[str, Any]:
    with _bounded_receipt_scope("checkpoint-b5", (b5,), _TRUSTED_B5_CONTRACT):
        with _bounded_receipt_scope(
                "checkpoint-v7", (completion_v7, completion_v7.b4),
                _TRUSTED_V7_B4_CONTRACT):
            return _build_receipt()


def _build_receipt() -> dict[str, Any]:
    parent = boundary.read(PARENT_PATH)
    require(parent.get("canonical_sha256") == PARENT_SHA, "immutable Completion V7 identity drift")
    completion_v7.audit()
    review = b5.validate_receipt()
    inherited = parent["unreviewed_authority_surfaces"]
    inherited_keys = {(row["workflow_path"], row["trigger_kind"]) for row in inherited}
    require(len(inherited) == 7 and len(inherited_keys) == 7,
            "Completion V7 unresolved surface census drift")
    require(TARGET_KEYS <= inherited_keys, "a B5 surface is not inherited as unresolved")
    resolved = {
        (row["identity"]["workflow_path"], row["identity"]["trigger_kind"])
        for row in review["review_rows"] if row["review"]["status"] == "RESOLVED"
    }
    require(resolved <= TARGET_KEYS, "B5 overlay added an out-of-scope surface")
    remaining = [deepcopy(row) for row in inherited
                 if (row["workflow_path"], row["trigger_kind"]) not in resolved]
    remaining_keys = {(row["workflow_path"], row["trigger_kind"]) for row in remaining}
    require(len(remaining) == 7 - len(resolved), "Completion V8 remaining count is not derived")
    require(not (remaining_keys & resolved), "a surface appears as both reviewed and unresolved")
    if len(resolved) == 4:
        require(remaining_keys == EXPECTED_FINAL_KEYS,
                "the exact three inherited non-B5 unknown surfaces changed")
    criteria = deepcopy(parent["checkpoint_criteria"])
    require(len(criteria) == 19, "Completion V7 criterion set drift")
    require(criteria["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False,
            "B5 cannot complete criterion 11")
    require(criteria["no_unknown_current_artifact_or_notification_authority"] is False,
            "B5 cannot complete criterion 14")

    value = deepcopy(parent)
    value.update({
        "schema_version": 8,
        "policy_id": POLICY_ID,
        "base_main_sha": b5.BASE_MAIN,
        "base_tree_sha": b5.BASE_TREE,
        "predecessor_completion_v7": {"path": PARENT_PATH, "canonical_sha256": PARENT_SHA,
                                       "rewritten": False},
        "b5_review": {"path": b5.RECEIPT_PATH, "canonical_sha256": review["canonical_sha256"]},
        "b5_source_inventory": {"path": b5.SOURCE_INVENTORY_PATH,
                                "canonical_sha256": review["source_inventory"]["canonical_sha256"]},
        "a2_generation_7": deepcopy(review["a2_generation_7"]),
        "scope": {
            "inherited_unresolved_count": len(inherited),
            "target_surface_count": len(TARGET_KEYS),
            "resolved_target_count": len(resolved),
            "partial_target_count": len(TARGET_KEYS) - len(resolved),
            "remaining_global_unreviewed_surface_count": len(remaining),
            "target_keys": [[path, trigger] for path, trigger in b5.TARGETS],
        },
        "b5_reviewed_target_surfaces": [{
            "workflow_path": path,
            "trigger_kind": trigger,
            "review_status": next(
                row["review"]["status"] for row in review["review_rows"]
                if (row["identity"]["workflow_path"], row["identity"]["trigger_kind"]) == (path, trigger)
            ),
            "b5_receipt_sha256": review["canonical_sha256"],
        } for path, trigger in b5.TARGETS],
        "unresolved_b5_target_keys": [[path, trigger] for path, trigger in sorted(TARGET_KEYS - resolved)],
        "unreviewed_authority_surfaces": remaining,
        "checkpoint_criteria": criteria,
        "checkpoint_e_status": "INCOMPLETE",
        "p4_4_status": "INCOMPLETE",
        "workflow_edit_count": 0,
        "trigger_edit_count": 0,
        "workflow_retirement_count": 0,
        "workflow_deletion_count": 0,
        "caller_migration_count": 0,
        "source_review_counter_while_open": "4/5",
        "source_review_counter_if_owner_merges": "5/5",
        "mandatory_governing_source_reread_after_b5_merge": True,
        "do_not_start_b6_before_reread": True,
        "terminal": "CORE_01D_FROZEN_ARTIFACT_REPLAY_AUTHORITY_B5_REVIEW_READY_4_RESOLVED_DO_NOT_MERGE"
        if len(resolved) == 4 else "CORE_01D_FROZEN_ARTIFACT_REPLAY_AUTHORITY_B5_REVIEW_READY_PARTIAL_DO_NOT_MERGE",
    })
    return boundary.seal(value)


def validate_receipt(value: dict[str, Any] | None = None) -> dict[str, Any]:
    value = boundary.read(RECEIPT_PATH) if value is None else value
    require((ROOT / RECEIPT_PATH).read_bytes() == boundary.canonical(value),
            "Completion V8 is not canonical")
    scope = _active_receipt_scope("checkpoint-v8")
    cached = None if scope is None else scope.load()
    if cached is None:
        require(value == build_receipt(),
                "Completion V8 differs from immutable V7 plus the B5 overlay")
    else:
        require(value == cached,
                "Completion V8 changed after its same-call authenticated derivation")
    require(value["scope"]["remaining_global_unreviewed_surface_count"] ==
            7 - value["scope"]["resolved_target_count"],
            "Completion V8 unresolved count is not derived")
    require(value["checkpoint_e_status"] == value["p4_4_status"] == "INCOMPLETE",
            "B5 cannot complete Checkpoint E/P4.4")
    require(value["checkpoint_criteria"]["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False
            and value["checkpoint_criteria"]["no_unknown_current_artifact_or_notification_authority"] is False,
            "Completion V8 criteria 11/14 must remain false")
    if scope is not None and cached is None:
        scope.store(value)
    return value


def audit() -> dict[str, Any]:
    value = validate_receipt()
    return {
        "result": "PASS",
        "receipt_sha256": value["canonical_sha256"],
        "resolved_target_count": value["scope"]["resolved_target_count"],
        "remaining_unreviewed_surface_count": value["scope"]["remaining_global_unreviewed_surface_count"],
        "checkpoint_e": value["checkpoint_e_status"],
        "p4_4": value["p4_4_status"],
        "remaining_blockers": value["remaining_blocker_ids"],
        "terminal": value["terminal"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        value = build_receipt()
        (ROOT / RECEIPT_PATH).write_bytes(boundary.canonical(value))
        print(value["canonical_sha256"])
    else:
        print(json.dumps(audit(), sort_keys=True))


# These immutable baselines must be captured only after every V8 scope helper
# and module-level verifier definition above has been installed. Capturing them
# earlier would compare an incomplete module surface at scope entry.
_B3_MODULE = sys.modules.get(
    "scripts.audit_core_01d_owner_one_shot_issue_comment_authority_b3")
if _B3_MODULE is None:
    raise RuntimeError("B3 verifier module was not loaded through the completion predecessor chain")
_TRUSTED_B5_CONTRACT = _auditor_contract_digest(b5)
_TRUSTED_B1_CONTRACT = _auditor_contract_digest(b1)
_TRUSTED_B2_CONTRACT = _auditor_contract_digest(b2)
_TRUSTED_B4_CONTRACT = _auditor_contract_digest(completion_v7.b4)
_TRUSTED_V7_B4_CONTRACT = _auditor_contract_digest(completion_v7, completion_v7.b4)
_TRUSTED_B3_CONTRACT = _auditor_contract_digest(_B3_MODULE)


if __name__ == "__main__":
    main()
