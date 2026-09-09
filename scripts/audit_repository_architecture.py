"""ATHENA Repository Architecture Inventory — P0.2

Deterministic, read-only, static inventory of the ATHENA repository at a
specific Git ref.  Does NOT import, execute, or modify any repository module.

Schema version: 1
Policy ID: ATHENA_REPOSITORY_ARCHITECTURE_INVENTORY_V1

Usage::

    python -m scripts.audit_repository_architecture \\
      --ref e04cbbeaeff999a1e5dd3ff7891857b4813a7fac \\
      --json-output artifacts/architecture/repository-architecture-inventory-v1.json \\
      --csv-output artifacts/architecture/repository-architecture-modules-v1.csv

"""
from __future__ import annotations

import argparse
import ast
import csv
import io
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

# ---------------------------------------------------------------------------
# Policy constants
# ---------------------------------------------------------------------------
SCHEMA_VERSION: int = 1
POLICY_ID: str = "ATHENA_REPOSITORY_ARCHITECTURE_INVENTORY_V1"
DISPOSITION_UNCLASSIFIED: str = "UNCLASSIFIED"

# Authority-role vocabulary (Architecture Remediation Specification v2)
AUTHORITY_SHARED_CANONICAL: str = "SHARED_CANONICAL"
AUTHORITY_MAIN_ONLY: str = "MAIN_ONLY"
AUTHORITY_SHADOW_ONLY: str = "SHADOW_ONLY"
AUTHORITY_RESEARCH_CHALLENGER: str = "RESEARCH_CHALLENGER"
AUTHORITY_HISTORICAL_EVIDENCE: str = "HISTORICAL_EVIDENCE"
AUTHORITY_UNKNOWN: str = "UNKNOWN"

ALL_AUTHORITY_PROFILES: tuple[str, ...] = (
    AUTHORITY_SHARED_CANONICAL,
    AUTHORITY_MAIN_ONLY,
    AUTHORITY_SHADOW_ONLY,
    AUTHORITY_RESEARCH_CHALLENGER,
    AUTHORITY_HISTORICAL_EVIDENCE,
    AUTHORITY_UNKNOWN,
)

# Supported-root evidence basis values
EVIDENCE_CURRENT_HOSTED_WORKFLOW: str = "CURRENT_HOSTED_WORKFLOW"
EVIDENCE_PACKAGING_ENTRYPOINT: str = "PACKAGING_ENTRYPOINT"
EVIDENCE_USER_FACING_CLI: str = "USER_FACING_CLI"

# CLI framework tags
CLI_TYPER: str = "TYPER_ENTRYPOINT"
CLI_ARGPARSE: str = "ARGPARSE_ENTRYPOINT"
CLI_CLICK: str = "CLICK_ENTRYPOINT"
CLI_MAIN: str = "DIRECT_PYTHON_ENTRYPOINT"
CLI_PACKAGING: str = "PACKAGING_ENTRYPOINT"
CLI_WORKFLOW: str = "WORKFLOW_INVOKED_ENTRYPOINT"

# Dynamic import marker
DYNAMIC_NONLITERAL: str = "DYNAMIC_IMPORT_NON_LITERAL"
EXEC_NONLITERAL: str = "DYNAMIC_EXECUTION_NON_LITERAL"

# ---------------------------------------------------------------------------
# Git helpers  (NO shell=True, NO arbitrary string eval)
# ---------------------------------------------------------------------------

def _git(repo_root: Path, *args: str) -> bytes:
    """Run a git command, return raw stdout bytes.  Raises on failure."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (exit {result.returncode}):\n"
            + result.stderr.decode("utf-8", errors="replace")
        )
    return result.stdout


def resolve_ref(repo_root: Path, ref: str) -> str:
    """Resolve *ref* to a 40-char commit SHA.  Raises on invalid ref."""
    out = _git(repo_root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    sha = out.decode().strip()
    if len(sha) != 40 or not all(c in "0123456789abcdef" for c in sha):
        raise RuntimeError(f"Unexpected rev-parse output for ref {ref!r}: {sha!r}")
    return sha


_EXCLUDED_PREFIXES = (
    ".git/",
    ".venv/",
    "venv/",
    "__pycache__/",
    ".pytest_cache/",
    ".cache/",
)


def _is_excluded(path: str) -> bool:
    norm = path.replace("\\", "/")
    if any(norm.startswith(pre) for pre in _EXCLUDED_PREFIXES):
        return True
    if "/__pycache__/" in norm or "/.pytest_cache/" in norm or "/.cache/" in norm:
        return True
    return False


def list_tracked_files(repo_root: Path, sha: str) -> list[str]:
    """Return sorted list of repo-relative paths tracked at *sha*."""
    out = _git(repo_root, "ls-tree", "-r", "--name-only", sha)
    paths = sorted(
        p for p in out.decode("utf-8").splitlines()
        if p and not _is_excluded(p)
    )
    return paths


def read_files_at_ref(repo_root: Path, sha: str, paths: list[str]) -> dict[str, bytes]:
    """Batch-read multiple files at sha:<path> using git cat-file --batch.

    Fails closed: every requested path must resolve to a valid blob.
    Missing objects, malformed headers, truncated bodies, or cardinality
    mismatches immediately raise a RuntimeError.
    """
    if not paths:
        return {}
    input_data = b"".join(f"{sha}:{p}\n".encode("utf-8") for p in paths)
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "cat-file", "--batch"],
        input=input_data,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git cat-file --batch failed (exit {proc.returncode}):\n"
            + proc.stderr.decode("utf-8", errors="replace")
        )

    out = proc.stdout
    idx = 0
    results: dict[str, bytes] = {}
    total = len(paths)

    for path_idx, req_path in enumerate(paths):
        if idx >= len(out):
            raise RuntimeError(
                f"FAIL-CLOSED: git cat-file --batch truncated: reached EOF before reading path {req_path!r} "
                f"({path_idx + 1}/{total})"
            )
        nl = out.find(b"\n", idx)
        if nl == -1:
            raise RuntimeError(
                f"FAIL-CLOSED: git cat-file --batch malformed: missing header newline for path {req_path!r} at offset {idx}"
            )
        header_bytes = out[idx:nl]
        idx = nl + 1
        try:
            header = header_bytes.decode("ascii")
        except UnicodeDecodeError as exc:
            raise RuntimeError(
                f"FAIL-CLOSED: non-ASCII characters in git cat-file header for path {req_path!r}: {header_bytes!r}"
            ) from exc

        # Check for missing object response: "<object-name> missing"
        if header.endswith(" missing"):
            raise RuntimeError(
                f"FAIL-CLOSED: missing Git blob for requested path {req_path!r} at ref {sha}: {header}"
            )

        # Header must contain exactly 3 space-separated tokens:
        # <40-char lowercase hex object id> blob <decimal size>
        parts = header.split(" ")
        if len(parts) != 3:
            raise RuntimeError(
                f"FAIL-CLOSED: unexpected git cat-file header for path {req_path!r} "
                f"(expected exactly 3 space-separated tokens '<oid> blob <size>'): {header!r}"
            )
        obj_id, obj_type, size_str = parts

        # Object ID must be exactly 40 lowercase hexadecimal characters
        if len(obj_id) != 40 or not all(c in "0123456789abcdef" for c in obj_id):
            raise RuntimeError(
                f"FAIL-CLOSED: invalid object id in git cat-file header for path {req_path!r} "
                f"(expected 40 lowercase hex chars): {obj_id!r}"
            )

        # Object type must be exactly "blob"
        if obj_type != "blob":
            raise RuntimeError(
                f"FAIL-CLOSED: unexpected object type in git cat-file header for path {req_path!r} "
                f"(expected 'blob'): {obj_type!r}"
            )

        # Size must parse as a non-negative decimal integer
        if not size_str.isdigit():
            raise RuntimeError(
                f"FAIL-CLOSED: invalid blob size in header for path {req_path!r} "
                f"(expected non-negative decimal integer): {size_str!r}"
            )
        size = int(size_str)

        if idx + size > len(out):
            raise RuntimeError(
                f"FAIL-CLOSED: truncated blob body for path {req_path!r}: "
                f"expected {size} bytes, but only {len(out) - idx} remaining"
            )
        blob_data = out[idx:idx + size]
        idx += size

        # The next byte MUST exist and MUST be b"\n"
        if idx >= len(out) or out[idx:idx + 1] != b"\n":
            raise RuntimeError(
                f"FAIL-CLOSED: missing trailing newline delimiter after blob {req_path!r}"
            )
        # Consume exactly that one protocol delimiter
        idx += 1

        if req_path in results:
            raise RuntimeError(
                f"FAIL-CLOSED: duplicate result for requested path {req_path!r}"
            )
        results[req_path] = blob_data

    # Check cardinality and trailing bytes
    if len(results) != total:
        raise RuntimeError(
            f"FAIL-CLOSED: requested {total} paths but parsed {len(results)} results"
        )
    for p in paths:
        if p not in results:
            raise RuntimeError(
                f"FAIL-CLOSED: requested path {p!r} not present in parsed results"
            )

    # After all requested objects are parsed: idx MUST equal len(out)
    # ANY additional byte, including whitespace/newline, must fail closed
    if idx != len(out):
        raise RuntimeError(
            f"FAIL-CLOSED: unparsed trailing data in git cat-file output ({len(out) - idx} bytes): {out[idx:idx + 64]!r}"
        )

    return results


def read_file_at_ref(repo_root: Path, sha: str, path: str) -> bytes:
    """Read a single file at sha:<path>."""
    res = read_files_at_ref(repo_root, sha, [path])
    return res[path]


# ---------------------------------------------------------------------------
# Module name derivation
# ---------------------------------------------------------------------------

def path_to_module(repo_relative_path: str) -> str | None:
    """Convert a repo-relative .py path to a dotted module name.

    Returns None if the path is not a Python source file or cannot be mapped.
    """
    p = PurePosixPath(repo_relative_path)
    if p.suffix != ".py":
        return None
    parts = list(p.with_suffix("").parts)
    # Strip __init__ suffix — the package itself is the module
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return None
    # Validate each part is a valid Python identifier component
    for part in parts:
        if not part.isidentifier():
            return None
    return ".".join(parts)


def is_test_path(repo_relative_path: str) -> bool:
    p = repo_relative_path.replace("\\", "/")
    return (
        p.startswith("tests/")
        or p.startswith("test/")
        or "/tests/" in p
        or "/test_" in p
        or p.startswith("test_")
    )


# ---------------------------------------------------------------------------
# AST parsing
# ---------------------------------------------------------------------------

def parse_imports(source: str, path: str) -> tuple[list[dict], list[dict]]:
    """Parse *source* for import statements.

    Returns:
        (imports, diagnostics) where imports is a list of dicts with keys:
          kind, module, names, level, lineno
    """
    imports: list[dict] = []
    diagnostics: list[dict] = []
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        diagnostics.append({
            "path": path,
            "category": "PARSE_ERROR",
            "detail": str(exc),
            "line": exc.lineno,
        })
        return imports, diagnostics

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({
                    "kind": "import",
                    "module": alias.name,
                    "names": [],
                    "level": 0,
                    "lineno": node.lineno,
                })
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.append({
                "kind": "from",
                "module": module,
                "names": [alias.name for alias in node.names],
                "level": node.level,
                "lineno": node.lineno,
            })
    return imports, diagnostics


def has_main_guard(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            if (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
                and len(test.ops) == 1
                and isinstance(test.ops[0], ast.Eq)
                and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value == "__main__"
            ):
                return True
    return False


def detect_cli_frameworks(source: str, path: str) -> list[str]:
    """Detect CLI framework usage statically."""
    frameworks: list[str] = []
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return frameworks

    source_lower = source.lower()

    # Detect Typer
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "Typer":
                frameworks.append(CLI_TYPER)
                break
            if isinstance(func, ast.Name) and func.id == "Typer":
                frameworks.append(CLI_TYPER)
                break
    # Detect argparse
    if "argumentparser" in source_lower or "argparse.argumentparser" in source_lower:
        frameworks.append(CLI_ARGPARSE)
    # Detect click
    if "@click." in source or "import click" in source:
        frameworks.append(CLI_CLICK)

    if has_main_guard(source):
        if CLI_MAIN not in frameworks:
            frameworks.append(CLI_MAIN)

    return sorted(set(frameworks))


# ---------------------------------------------------------------------------
# Dynamic import indicators
# ---------------------------------------------------------------------------

def detect_dynamic_imports(source: str, path: str) -> list[dict]:
    """Detect importlib.import_module and __import__ calls statically using AST import ownership."""
    indicators: list[dict] = []
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return indicators

    importlib_modules: set[str] = set()
    importlib_direct_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    importlib_modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "importlib":
                for alias in node.names:
                    if alias.name == "import_module":
                        importlib_direct_names.add(alias.asname or alias.name)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        call_kind: str | None = None

        # importlib.import_module(...) or aliased_importlib.import_module(...)
        if isinstance(func, ast.Attribute) and func.attr == "import_module":
            if isinstance(func.value, ast.Name) and func.value.id in importlib_modules:
                call_kind = "importlib.import_module"
        # direct import_module(...) or aliased from importlib import import_module
        elif isinstance(func, ast.Name):
            if func.id in importlib_direct_names:
                call_kind = "importlib.import_module"
            elif func.id == "__import__":
                call_kind = "__import__"

        if call_kind:
            # Try to extract literal target
            literal_target: str | None = None
            if node.args:
                first_arg = node.args[0]
                if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                    literal_target = first_arg.value
            indicators.append({
                "path": path,
                "call_kind": call_kind,
                "literal_target": literal_target,
                "is_literal": literal_target is not None,
                "marker": literal_target if literal_target else DYNAMIC_NONLITERAL,
                "lineno": node.lineno,
            })
    return indicators


# ---------------------------------------------------------------------------
# Execution / subprocess indicators
# ---------------------------------------------------------------------------

_SUBPROCESS_CALLS = {"run", "Popen", "call", "check_call", "check_output"}


def detect_execution_indicators(source: str, path: str) -> list[dict]:
    """Detect subprocess.run/Popen, os.system, python CLI invocations using AST import ownership."""
    indicators: list[dict] = []
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return indicators

    subprocess_modules: set[str] = set()
    subprocess_direct_names: dict[str, str] = {}  # alias -> method name (e.g. "my_run" -> "run")
    os_modules: set[str] = set()
    os_direct_names: dict[str, str] = {}  # alias -> "system"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    subprocess_modules.add(alias.asname or alias.name)
                elif alias.name == "os":
                    os_modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "subprocess":
                for alias in node.names:
                    if alias.name in _SUBPROCESS_CALLS:
                        subprocess_direct_names[alias.asname or alias.name] = alias.name
            elif node.module == "os":
                for alias in node.names:
                    if alias.name == "system":
                        os_direct_names[alias.asname or alias.name] = "system"

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        call_kind: str | None = None

        # 1. Attribute call: e.g. subprocess.run(...), sp.Popen(...), os.system(...)
        if isinstance(func, ast.Attribute):
            if func.attr in _SUBPROCESS_CALLS and isinstance(func.value, ast.Name):
                if func.value.id in subprocess_modules:
                    call_kind = f"subprocess.{func.attr}"
            elif func.attr == "system" and isinstance(func.value, ast.Name):
                if func.value.id in os_modules:
                    call_kind = "os.system"
        # 2. Name call: e.g. run(...), my_run(...), system(...)
        elif isinstance(func, ast.Name):
            if func.id in subprocess_direct_names:
                call_kind = f"subprocess.{subprocess_direct_names[func.id]}"
            elif func.id in os_direct_names:
                call_kind = "os.system"

        if call_kind:
            literal_cmd: str | None = None
            if node.args:
                first = node.args[0]
                if isinstance(first, ast.List):
                    parts = []
                    all_literal = True
                    for elt in first.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            parts.append(elt.value)
                        else:
                            all_literal = False
                            break
                    if all_literal and parts:
                        literal_cmd = " ".join(parts)
                elif isinstance(first, ast.Constant) and isinstance(first.value, str):
                    literal_cmd = first.value
            indicators.append({
                "path": path,
                "call_kind": call_kind,
                "literal_cmd": literal_cmd,
                "is_literal": literal_cmd is not None,
                "marker": literal_cmd if literal_cmd else EXEC_NONLITERAL,
                "lineno": node.lineno,
            })
    return indicators


# ---------------------------------------------------------------------------
# Workflow analysis
# ---------------------------------------------------------------------------

_WF_PYTHON_FILE_RE = re.compile(
    r'(?:python3?|PYTHONPATH=\S+\s+python3?)\s+([\w./-]+\.py)',
    re.IGNORECASE,
)
_WF_PYTHON_MOD_RE = re.compile(
    r'(?:python3?|PYTHONPATH=\S+\s+python3?)\s+-m\s+([\w.]+)',
    re.IGNORECASE,
)
_WF_NAME_RE = re.compile(r'^name:\s*(.+)$', re.MULTILINE)
_WF_UPLOAD_RE = re.compile(r'actions/upload-artifact', re.IGNORECASE)
_WF_DOWNLOAD_RE = re.compile(r'actions/download-artifact', re.IGNORECASE)
_WF_USES_RE = re.compile(r'uses:\s*(.+)', re.MULTILINE)


def analyze_workflow(path: str, content: str) -> dict:
    """Extract workflow metadata without executing any steps."""
    name_m = _WF_NAME_RE.search(content)
    wf_name = name_m.group(1).strip() if name_m else None

    py_files = sorted(set(_WF_PYTHON_FILE_RE.findall(content)))
    py_modules = sorted(set(_WF_PYTHON_MOD_RE.findall(content)))

    uses_all = [u.strip() for u in _WF_USES_RE.findall(content)]
    reusable_workflows = sorted(set(u for u in uses_all if ".github/workflows" in u or u.startswith("./")))

    upload_artifacts = bool(_WF_UPLOAD_RE.search(content))
    download_artifacts = bool(_WF_DOWNLOAD_RE.search(content))
    shell_scripts = sorted(set(re.findall(r'[\w./-]+\.sh', content)))

    return {
        "path": path,
        "workflow_name": wf_name,
        "referenced_python_files": py_files,
        "referenced_python_modules": py_modules,
        "shell_script_references": shell_scripts,
        "reusable_workflow_references": reusable_workflows,
        "upload_artifact_usage": upload_artifacts,
        "download_artifact_usage": download_artifacts,
    }


# ---------------------------------------------------------------------------
# Import resolution
# ---------------------------------------------------------------------------

def resolve_import(
    import_record: dict,
    source_module: str,
    known_modules: set[str],
    diagnostics: list[dict],
    path: str,
) -> list[str]:
    """Resolve an import record to a list of local target module names.

    Returns empty list if external/unresolvable.
    """
    level: int = import_record["level"]
    module: str = import_record["module"]
    kind: str = import_record["kind"]
    names: list[str] = import_record["names"]

    targets: list[str] = []

    if level == 0:
        # Absolute import
        if kind == "from":
            # "from package import foo, bar"
            # 1. Try each name as a submodule (e.g. from pkg import foo -> pkg.foo)
            for name in names:
                cand = f"{module}.{name}" if module else name
                if cand in known_modules:
                    targets.append(cand)
            # 2. If no name was a submodule, check if module itself is a local module
            if not targets and module in known_modules:
                targets.append(module)
        else:
            # "import module"
            if module in known_modules:
                targets.append(module)
            else:
                top = module.split(".")[0]
                if any(m == top or m.startswith(top + ".") for m in known_modules):
                    if module in known_modules:
                        targets.append(module)
    else:
        # Relative import from package context (PEP 328)
        # Normal module pkg/sub/mod.py has package context "pkg.sub".
        # Package initializer pkg/sub/__init__.py has package context "pkg.sub".
        is_init = path.replace("\\", "/").endswith("/__init__.py") or path == "__init__.py"
        if is_init:
            package_parts = source_module.split(".") if source_module else []
        else:
            source_parts = source_module.split(".") if source_module else []
            package_parts = source_parts[:-1]

        # Level 1 remains in current package (ascends 0 levels).
        # Level 2 ascends 1 package level.
        # Level N ascends N - 1 package levels.
        # Ascending beyond package root (level > len(package_parts)) is invalid.
        if level > len(package_parts):
            diagnostics.append({
                "path": path,
                "category": "RELATIVE_IMPORT_TOO_DEEP",
                "detail": f"level={level} module={module} source={source_module}",
                "line": import_record["lineno"],
            })
            return []

        ascend = level - 1
        base_parts = package_parts[:len(package_parts) - ascend] if ascend > 0 else package_parts
        base = ".".join(base_parts)

        if kind == "from":
            for name in names:
                if module:
                    cand = f"{base}.{module}.{name}" if base else f"{module}.{name}"
                else:
                    cand = f"{base}.{name}" if base else name
                if cand in known_modules:
                    targets.append(cand)
            if not targets:
                if module:
                    cand = f"{base}.{module}" if base else module
                else:
                    cand = base
                if cand and cand in known_modules:
                    targets.append(cand)
        else:
            cand = f"{base}.{module}" if base else module
            if cand in known_modules:
                targets.append(cand)

    return sorted(set(targets))


# ---------------------------------------------------------------------------
# Authority family detection
# ---------------------------------------------------------------------------

_FAMILY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("market_router", re.compile(r"market_router")),
    ("price_all", re.compile(r"price_all")),
    ("portfolio_optimizer", re.compile(r"portfolio_optimizer")),
    ("accumulator_optimizer", re.compile(r"accumulator_optimizer")),
    ("market_selector", re.compile(r"market_selector")),
    ("prediction_service", re.compile(r"prediction_service")),
    ("current_shadow", re.compile(r"current_shadow")),
    ("fotmob", re.compile(r"fotmob")),
    ("sportybet", re.compile(r"sportybet")),
]


def detect_authority_families(module_names: list[str]) -> list[dict]:
    """Group modules into named families based on naming conventions."""
    families: dict[str, list[str]] = defaultdict(list)
    for module in module_names:
        short = module.split(".")[-1]
        for family_name, pattern in _FAMILY_PATTERNS:
            if pattern.search(short):
                families[family_name].append(module)
    result = []
    for family_name in sorted(families):
        members = sorted(families[family_name])
        result.append({
            "family": family_name,
            "members": members,
        })
    return result


# ---------------------------------------------------------------------------
# Reachability via BFS
# ---------------------------------------------------------------------------

def compute_reachability(
    root_modules: list[str],
    static_edges: dict[str, list[str]],
) -> dict[str, set[str]]:
    """For each root, compute the set of reachable modules via BFS.

    Returns dict: module -> set of root_modules that can reach it.
    """
    reachable_from: dict[str, set[str]] = defaultdict(set)
    for root in root_modules:
        visited: set[str] = set()
        queue = [root]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            reachable_from[current].add(root)
            for target in static_edges.get(current, []):
                if target not in visited:
                    queue.append(target)
    return reachable_from


# ---------------------------------------------------------------------------
# Packaging entrypoints from setup.py (text-based, no import)
# ---------------------------------------------------------------------------

def extract_packaging_entrypoints(content: str) -> list[str]:
    """Extract console_scripts from setup.py source text."""
    pattern = re.compile(r'console_scripts["\']?\s*:\s*\[(.*?)\]', re.DOTALL)
    m = pattern.search(content)
    if not m:
        return []
    block = m.group(1)
    entries = re.findall(r'["\']([^"\']+)["\']', block)
    modules = []
    for entry in entries:
        if "=" in entry:
            module_func = entry.split("=", 1)[1].strip()
            module = module_func.split(":")[0].strip()
            modules.append(module)
    return modules


# ---------------------------------------------------------------------------
# Main inventory function
# ---------------------------------------------------------------------------

def build_inventory(
    repo_root: Path,
    ref: str,
    *,
    known_authority_profiles: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the complete inventory for *ref* in *repo_root*."""

    # ---- 1. Resolve ref ----
    resolved_sha = resolve_ref(repo_root, ref)

    # ---- 2. Enumerate tracked files ----
    all_tracked = list_tracked_files(repo_root, resolved_sha)

    # ---- 3. Classify files ----
    python_files: list[str] = []
    workflow_files: list[str] = []

    for path in all_tracked:
        if path.endswith(".py"):
            python_files.append(path)
        elif (path.startswith(".github/workflows/") and
              (path.endswith(".yml") or path.endswith(".yaml"))):
            workflow_files.append(path)

    # ---- 4. Build module name map (fail on collision) ----
    path_to_module_map: dict[str, str] = {}
    module_to_path_map: dict[str, str] = {}
    module_diagnostics: list[dict] = []

    for path in python_files:
        mod = path_to_module(path)
        if mod is None:
            module_diagnostics.append({
                "path": path,
                "category": "UNRESOLVABLE_MODULE_NAME",
                "detail": "Cannot derive dotted module name from path",
                "line": None,
            })
            continue
        if mod in module_to_path_map:
            raise RuntimeError(
                f"FAIL-CLOSED: two tracked files map to module {mod!r}:\n"
                f"  {module_to_path_map[mod]}\n"
                f"  {path}"
            )
        path_to_module_map[path] = mod
        module_to_path_map[mod] = path

    known_modules: set[str] = set(module_to_path_map.keys())

    # ---- 5. Fast batch-read all Python and workflow files ----
    files_to_read = python_files + workflow_files
    if "setup.py" in all_tracked and "setup.py" not in files_to_read:
        files_to_read.append("setup.py")

    file_contents = read_files_at_ref(repo_root, resolved_sha, files_to_read)

    parse_diagnostics: list[dict] = []
    module_records: dict[str, dict] = {}

    for path in python_files:
        mod = path_to_module_map.get(path)
        is_test = is_test_path(path)

        raw = file_contents[path]
        source = raw.decode("utf-8", errors="replace")

        raw_imports, diags = parse_imports(source, path)
        parse_diagnostics.extend(diags)
        cli_frameworks = detect_cli_frameworks(source, path)
        dynamic_indicators = detect_dynamic_imports(source, path)
        exec_indicators = detect_execution_indicators(source, path)

        profile = AUTHORITY_UNKNOWN
        if known_authority_profiles and mod in known_authority_profiles:
            assigned = known_authority_profiles[mod]
            if assigned not in ALL_AUTHORITY_PROFILES:
                raise RuntimeError(f"Invalid authority profile {assigned!r} for module {mod!r}")
            profile = assigned

        module_records[path] = {
            "path": path,
            "module": mod,
            "is_test": is_test,
            "has_main_guard": has_main_guard(source),
            "cli_frameworks": sorted(set(cli_frameworks)),
            "raw_imports": raw_imports,
            "dynamic_import_indicators": dynamic_indicators,
            "execution_refs": exec_indicators,
            "static_imports_local": [],
            "static_imported_by": [],
            "static_inbound_count": 0,
            "static_outbound_count": 0,
            "non_test_static_inbound_count": 0,
            "workflow_refs": [],
            "referenced_by_tests": False,
            "test_reference_count": 0,
            "supported_static_roots": [],
            "reachable_from_supported_static_root": False,
            "zero_static_inbound": True,
            "authority_profile": profile,
            "disposition": DISPOSITION_UNCLASSIFIED,
        }

    # ---- 6. Resolve imports into local edges ----
    static_edges: list[dict] = []
    outbound: dict[str, list[str]] = defaultdict(list)
    inbound: dict[str, list[str]] = defaultdict(list)
    inbound_test: dict[str, int] = defaultdict(int)
    inbound_nontest: dict[str, int] = defaultdict(int)

    for path, record in module_records.items():
        source_mod = record["module"]
        if source_mod is None:
            continue
        is_test = record["is_test"]
        for imp in record["raw_imports"]:
            targets = resolve_import(
                imp, source_mod, known_modules, parse_diagnostics, path
            )
            for target in targets:
                target_path = module_to_path_map.get(target)
                if target_path is None:
                    continue
                edge = {
                    "source_module": source_mod,
                    "source_path": path,
                    "target_module": target,
                    "target_path": target_path,
                    "import_kind": imp["kind"],
                    "line_number": imp["lineno"],
                }
                static_edges.append(edge)
                if target not in outbound[source_mod]:
                    outbound[source_mod].append(target)
                if source_mod not in inbound[target]:
                    inbound[target].append(source_mod)
                    if is_test:
                        inbound_test[target] += 1
                    else:
                        inbound_nontest[target] += 1

    # ---- 7. Fill in inbound/outbound counts ----
    for path, record in module_records.items():
        mod = record["module"]
        if mod is None:
            continue
        record["static_imports_local"] = sorted(outbound.get(mod, []))
        record["static_imported_by"] = sorted(inbound.get(mod, []))
        record["static_inbound_count"] = len(inbound.get(mod, []))
        record["static_outbound_count"] = len(outbound.get(mod, []))
        record["non_test_static_inbound_count"] = inbound_nontest.get(mod, 0)
        test_count = sum(
            1 for src in inbound.get(mod, [])
            if module_records.get(module_to_path_map.get(src, ""), {}).get("is_test", False)
        )
        record["test_reference_count"] = test_count
        record["referenced_by_tests"] = test_count > 0
        record["zero_static_inbound"] = record["static_inbound_count"] == 0

    # ---- 8. Workflow analysis ----
    workflow_inventory: list[dict] = []
    workflow_refs_flat: list[dict] = []
    workflow_referenced_modules: set[str] = set()

    for wf_path in workflow_files:
        raw = file_contents[wf_path]
        content = raw.decode("utf-8", errors="replace")
        wf_data = analyze_workflow(wf_path, content)
        workflow_inventory.append(wf_data)

        for mod_ref in wf_data["referenced_python_modules"]:
            workflow_referenced_modules.add(mod_ref)
            ref_entry = {"workflow_path": wf_path, "reference_kind": "python_module", "reference": mod_ref}
            workflow_refs_flat.append(ref_entry)
            target_path = module_to_path_map.get(mod_ref)
            if target_path and target_path in module_records:
                if ref_entry not in module_records[target_path]["workflow_refs"]:
                    module_records[target_path]["workflow_refs"].append(
                        {"workflow_path": wf_path, "kind": "python_module"}
                    )

        for file_ref in wf_data["referenced_python_files"]:
            ref_entry = {"workflow_path": wf_path, "reference_kind": "python_file", "reference": file_ref}
            workflow_refs_flat.append(ref_entry)
            norm = file_ref.lstrip("./")
            if norm in module_records:
                module_records[norm]["workflow_refs"].append(
                    {"workflow_path": wf_path, "kind": "python_file"}
                )
                workflow_referenced_modules.add(path_to_module_map.get(norm, norm))

    for path, record in module_records.items():
        record["workflow_refs"] = sorted(
            record["workflow_refs"],
            key=lambda x: (x["workflow_path"], x["kind"])
        )

    # ---- 9. Identify supported roots ----
    packaging_entrypoints: list[str] = []
    packaging_diagnostics: list[dict] = []
    if "setup.py" in file_contents:
        setup_py_src = file_contents["setup.py"].decode("utf-8", errors="replace")
        packaging_entrypoints = extract_packaging_entrypoints(setup_py_src)

    supported_roots: list[dict] = []
    candidate_entrypoints: list[dict] = []

    wf_invoked: dict[str, list[str]] = defaultdict(list)
    for wf in workflow_inventory:
        for mod in wf["referenced_python_modules"]:
            wf_invoked[mod].append(wf["path"])
        for f in wf["referenced_python_files"]:
            norm = f.lstrip("./")
            mod_from_path = path_to_module_map.get(norm)
            if mod_from_path:
                wf_invoked[mod_from_path].append(wf["path"])
            else:
                wf_invoked[norm].append(wf["path"])

    _REVIEWED_SUPPORTED_HOSTED_WORKFLOWS = {
        ".github/workflows/current-shadow-all-market.yml": "Active Current Shadow multi-market evaluation root",
        ".github/workflows/tests.yml": "Authoritative hosted CI test suite and syntax verification gate",
        ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml": "Active prospective FotMob fresh-holdout collection experiment root",
        ".github/workflows/bridge-fotmob-fresh-holdout-continuity-receipts.yml": "Active prospective fresh-holdout continuity durability bridge root",
    }

    supported_root_modules: list[str] = []

    for mod, wf_paths in sorted(wf_invoked.items()):
        mod_path = module_to_path_map.get(mod)
        if mod_path is None and mod in all_tracked:
            mod_path = mod

        # Supported roots and candidate entrypoints must be repository-local modules
        is_local = (mod in known_modules and mod_path is not None)
        if not is_local:
            continue

        is_hosted_current = any(wf in _REVIEWED_SUPPORTED_HOSTED_WORKFLOWS for wf in wf_paths)
        is_packaging = mod in packaging_entrypoints or any(
            mod == pe.split(":")[0] for pe in packaging_entrypoints
        )

        evidence_bases = []
        if is_hosted_current:
            evidence_bases.append(EVIDENCE_CURRENT_HOSTED_WORKFLOW)
        if is_packaging:
            evidence_bases.append(EVIDENCE_PACKAGING_ENTRYPOINT)

        if is_hosted_current or is_packaging:
            root_entry = {
                "root_identifier": mod,
                "root_path": mod_path,
                "root_module": mod,
                "root_type": "MODULE",
                "evidence_basis": sorted(evidence_bases),
                "invoking_workflows": sorted(set(wf_paths)),
            }
            supported_roots.append(root_entry)
            supported_root_modules.append(mod)
        else:
            cand_entry = {
                "candidate_identifier": mod,
                "candidate_path": mod_path,
                "candidate_module": mod,
                "workflow_referenced": True,
                "invoking_workflows": sorted(set(wf_paths)),
            }
            candidate_entrypoints.append(cand_entry)

    for pe in packaging_entrypoints:
        pe_mod = pe.split(":")[0].strip()
        pe_path = module_to_path_map.get(pe_mod)
        if pe_path is None and pe_mod in all_tracked:
            pe_path = pe_mod
        if pe_mod in known_modules and pe_path is not None:
            if not any(r["root_module"] == pe_mod for r in supported_roots):
                supported_roots.append({
                    "root_identifier": pe_mod,
                    "root_path": pe_path,
                    "root_module": pe_mod,
                    "root_type": "PACKAGING_ENTRYPOINT",
                    "evidence_basis": [EVIDENCE_PACKAGING_ENTRYPOINT],
                    "invoking_workflows": [],
                })
                supported_root_modules.append(pe_mod)
        else:
            packaging_diagnostics.append({
                "path": "setup.py",
                "category": "UNRESOLVABLE_PACKAGING_ENTRYPOINT",
                "detail": f"Packaging entrypoint '{pe}' references unresolvable module '{pe_mod}'",
                "line": None,
            })

    for path, record in sorted(module_records.items()):
        mod = record["module"]
        if mod is None:
            continue
        if record["has_main_guard"] or record["cli_frameworks"]:
            already_supported = any(r["root_module"] == mod for r in supported_roots)
            already_candidate = any(c["candidate_module"] == mod for c in candidate_entrypoints)
            if not already_supported and not already_candidate:
                candidate_entrypoints.append({
                    "candidate_identifier": mod,
                    "candidate_path": path,
                    "candidate_module": mod,
                    "workflow_referenced": False,
                    "invoking_workflows": [],
                })

    seen_roots = set()
    supported_roots_dedup = []
    for r in supported_roots:
        key = r["root_module"]
        if key not in seen_roots:
            seen_roots.add(key)
            supported_roots_dedup.append(r)
    supported_roots = sorted(supported_roots_dedup, key=lambda r: r["root_module"])
    supported_root_modules = [r["root_module"] for r in supported_roots]

    # Fail-closed validation assertions: every supported root must be local and tracked
    for r in supported_roots:
        if r["root_module"] not in known_modules:
            raise ValueError(f"Supported root '{r['root_module']}' is not in known_modules")
        if r["root_path"] is None or r["root_path"] not in all_tracked:
            raise ValueError(f"Supported root '{r['root_module']}' path '{r['root_path']}' is not a tracked file")

    seen_cands = set()
    candidate_entrypoints_dedup = []
    for c in candidate_entrypoints:
        key = c["candidate_module"]
        if key not in seen_cands:
            seen_cands.add(key)
            candidate_entrypoints_dedup.append(c)
    candidate_entrypoints = sorted(candidate_entrypoints_dedup, key=lambda c: c["candidate_module"])

    # ---- 10. Reachability from supported roots ----
    outbound_by_module: dict[str, list[str]] = {}
    for path, record in module_records.items():
        mod = record["module"]
        if mod:
            outbound_by_module[mod] = record["static_imports_local"]

    reachable_from = compute_reachability(supported_root_modules, outbound_by_module)

    for path, record in module_records.items():
        mod = record["module"]
        if mod and mod in reachable_from:
            roots_reaching = sorted(reachable_from[mod])
            record["supported_static_roots"] = roots_reaching
            record["reachable_from_supported_static_root"] = True
        else:
            record["supported_static_roots"] = []
            record["reachable_from_supported_static_root"] = False

    # ---- 11. Detect authority families ----
    all_module_names = sorted(m for m in known_modules)
    authority_families = detect_authority_families(all_module_names)

    for family in authority_families:
        members = family["members"]
        family_callers: list[str] = []
        family_workflows: list[str] = []
        family_root_reachable: list[str] = []
        for m in members:
            family_callers.extend(inbound.get(m, []))
            mp = module_to_path_map.get(m)
            if mp and mp in module_records:
                for wf_ref in module_records[mp]["workflow_refs"]:
                    family_workflows.append(wf_ref["workflow_path"])
                if module_records[mp]["reachable_from_supported_static_root"]:
                    family_root_reachable.extend(module_records[mp]["supported_static_roots"])
        family["static_callers"] = sorted(set(family_callers))
        family["workflow_references"] = sorted(set(family_workflows))
        family["supported_root_reachable"] = sorted(set(family_root_reachable))

    # ---- 12. Build final module list (sorted by path) ----
    final_modules: list[dict] = []
    for path in sorted(module_records.keys()):
        record = module_records[path]
        out_record = {k: v for k, v in record.items() if k != "raw_imports"}
        out_record["dynamic_import_indicators"] = [
            {
                "path": d.get("path", path),
                "call_kind": d["call_kind"],
                "is_literal": d["is_literal"],
                "lineno": d["lineno"],
                "marker": d["marker"],
            }
            for d in out_record["dynamic_import_indicators"]
        ]
        out_record["execution_refs"] = [
            {
                "path": d.get("path", path),
                "call_kind": d["call_kind"],
                "is_literal": d["is_literal"],
                "lineno": d["lineno"],
                "marker": d["marker"],
            }
            for d in out_record["execution_refs"]
        ]
        final_modules.append(out_record)

    # ---- 13. Build flat static edge list (deterministically sorted) ----
    sorted_edges = sorted(
        static_edges,
        key=lambda e: (e["source_path"], e["target_path"], e["line_number"]),
    )

    # ---- 14. Summary counts ----
    zero_static_inbound_count = sum(
        1 for r in final_modules if r["zero_static_inbound"] and not r["is_test"]
    )
    test_only_ref_candidates = sum(
        1 for r in final_modules
        if r["referenced_by_tests"] and r["non_test_static_inbound_count"] == 0 and not r["is_test"]
    )
    dynamic_indicator_total = sum(
        len(r["dynamic_import_indicators"]) for r in final_modules
    )
    exec_indicator_total = sum(
        len(r["execution_refs"]) for r in final_modules
    )

    runtime_py = sum(1 for r in final_modules if not r["is_test"])
    test_py = sum(1 for r in final_modules if r["is_test"])

    summary = {
        "tracked_file_count": len(all_tracked),
        "python_file_count": len(python_files),
        "runtime_python_file_count": runtime_py,
        "test_python_file_count": test_py,
        "workflow_count": len(workflow_files),
        "candidate_entrypoint_count": len(candidate_entrypoints),
        "supported_root_count": len(supported_roots),
        "static_import_edge_count": len(sorted_edges),
        "zero_static_inbound_count": zero_static_inbound_count,
        "workflow_referenced_module_count": len(workflow_referenced_modules),
        "test_only_reference_candidate_count": test_only_ref_candidates,
        "dynamic_import_indicator_count": dynamic_indicator_total,
        "execution_indicator_count": exec_indicator_total,
        "authority_family_count": len(authority_families),
    }

    # ---- 15. Diagnostics ----
    all_diagnostics = sorted(
        module_diagnostics + parse_diagnostics + packaging_diagnostics,
        key=lambda d: (d.get("path", ""), d.get("category", ""), d.get("line") or 0),
    )

    # ---- 16. Assemble final JSON payload ----
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "source_commit": resolved_sha,
        "generator_semantics": {
            "static_analysis_only": True,
            "no_import_execution": True,
            "no_network_requests": True,
            "git_ref_based": True,
            "deterministic": True,
        },
        "summary": summary,
        "supported_roots": supported_roots,
        "candidate_entrypoints": candidate_entrypoints,
        "python_modules": final_modules,
        "static_import_edges": sorted_edges,
        "workflow_inventory": sorted(workflow_inventory, key=lambda w: w["path"]),
        "workflow_references": sorted(workflow_refs_flat, key=lambda r: (r["workflow_path"], r["reference"])),
        "dynamic_import_indicators": sorted(
            [
                {"path": d["path"], "call_kind": d["call_kind"], "is_literal": d["is_literal"],
                 "lineno": d["lineno"], "marker": d["marker"]}
                for rec in final_modules
                for d in rec["dynamic_import_indicators"]
            ],
            key=lambda d: (d["path"], d["lineno"]),
        ),
        "execution_indicators": sorted(
            [
                {"path": d["path"], "call_kind": d["call_kind"], "is_literal": d["is_literal"],
                 "lineno": d["lineno"], "marker": d["marker"]}
                for rec in final_modules
                for d in rec["execution_refs"]
            ],
            key=lambda d: (d["path"], d["lineno"]),
        ),
        "authority_families": sorted(authority_families, key=lambda f: f["family"]),
        "diagnostics": all_diagnostics,
    }

    return payload


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

def build_csv(modules: list[dict]) -> str:
    """Build deterministic CSV string from module records."""
    fieldnames = [
        "path",
        "module",
        "is_test",
        "has_main_guard",
        "cli_frameworks",
        "static_inbound_count",
        "non_test_static_inbound_count",
        "static_outbound_count",
        "workflow_reference_count",
        "dynamic_import_indicator_count",
        "execution_reference_count",
        "test_reference_count",
        "supported_root_count",
        "reachable_from_supported_static_root",
        "zero_static_inbound",
        "authority_profile",
        "disposition",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for rec in sorted(modules, key=lambda r: r["path"]):
        writer.writerow({
            "path": rec["path"],
            "module": rec["module"] or "",
            "is_test": rec["is_test"],
            "has_main_guard": rec["has_main_guard"],
            "cli_frameworks": "|".join(sorted(rec["cli_frameworks"])),
            "static_inbound_count": rec["static_inbound_count"],
            "non_test_static_inbound_count": rec["non_test_static_inbound_count"],
            "static_outbound_count": rec["static_outbound_count"],
            "workflow_reference_count": len(rec["workflow_refs"]),
            "dynamic_import_indicator_count": len(rec["dynamic_import_indicators"]),
            "execution_reference_count": len(rec["execution_refs"]),
            "test_reference_count": rec["test_reference_count"],
            "supported_root_count": len(rec["supported_static_roots"]),
            "reachable_from_supported_static_root": rec["reachable_from_supported_static_root"],
            "zero_static_inbound": rec["zero_static_inbound"],
            "authority_profile": rec.get("authority_profile", AUTHORITY_UNKNOWN),
            "disposition": rec["disposition"],
        })
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Canonical JSON serialisation
# ---------------------------------------------------------------------------

def canonical_json(payload: dict) -> str:
    """Serialize to canonical JSON with trailing newline."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="ATHENA deterministic repository architecture inventory (P0.2)"
    )
    parser.add_argument(
        "--ref",
        required=True,
        help="Git ref (commit SHA, branch, tag) to inventory",
    )
    parser.add_argument(
        "--json-output",
        required=True,
        help="Path to write canonical JSON artifact",
    )
    parser.add_argument(
        "--csv-output",
        required=True,
        help="Path to write module CSV artifact",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Path to repository root (default: current directory)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()

    try:
        inventory = build_inventory(repo_root, args.ref)
    except RuntimeError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1

    json_str = canonical_json(inventory)
    csv_str = build_csv(inventory["python_modules"])

    json_path = Path(args.json_output)
    csv_path = Path(args.csv_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(json_str, encoding="utf-8")
    csv_path.write_text(csv_str, encoding="utf-8")

    summary = inventory["summary"]
    print("=== ATHENA Architecture Inventory ===")
    print(f"source_commit: {inventory['source_commit']}")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"JSON -> {json_path}")
    print(f"CSV  -> {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
