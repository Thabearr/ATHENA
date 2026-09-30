#!/usr/bin/env python3
"""Validate the PORT-02C native installed-runtime slice receipt offline.

Strict shape, self-hash, predecessor, platform-parity, and safety checks.
Fails closed when the receipt is absent or incomplete (expected before native
CI evidence is assembled in Phase C).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACT_PATH = "artifacts/architecture/port_02_native_runtime_v1.json"
POLICY_ID = "ATHENA_PORT_02_NATIVE_RUNTIME_V1"
BASE_MAIN_SHA = "2d01a591f8b5da2d9e536f93a995c09ed407efc7"
CLASSIFICATION = "NATIVE_INSTALLED_RUNTIME_SLICE_VERIFIED_WINDOWS_LINUX"

PORT02A_POLICY_ID = "ATHENA_PORT_02_INSTALLED_RELEASE_IDENTITY_V1"
PORT02A_CANONICAL_SHA256 = "8e08b1e45d589e56f3f7577711fb919958f31ff77c147533ae834871ec85f70f"
PORT02B_POLICY_ID = "ATHENA_PORT_02_WORKER_LAUNCH_BOUNDARY_V1"
PORT02B_CANONICAL_SHA256 = "61df4e210c1352975ecdbdb26f90e0adf16a22ef59d6e78749cef0eee05a5cda"
P44R_POLICY_ID = "ATHENA_P4_4R_SHADOW_RUNTIME_COMPOSITION_STABILIZATION_V1"
P44R_CANONICAL_SHA256 = "90e2d7e984609ded80c9113a05453628bebadfcb3cede7fc95b9696931016552"
P44S_POLICY_ID = "ATHENA_P4_4S_CANONICAL_ADAPTER_BOUND_CONTEXT_BUILDER_V1"
P44S_CANONICAL_SHA256 = "0907272a20b439e6874ee3b3fa399a488e8dd3c9a6e428dafa2aa53202c513c3"

SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
SHA1_RE = re.compile(r"^[0-9a-f]{40}$", re.ASCII)

REQUIRED_TOP_FIELDS = frozenset(
    {
        "schema_version",
        "policy_id",
        "repository",
        "implementation_base_main_sha",
        "predecessors",
        "platforms",
        "cross_platform_parity",
        "safety",
        "classification",
        "canonical_sha256",
    }
)
REQUIRED_PLATFORM_FIELDS = frozenset(
    {
        "platform",
        "architecture",
        "python_version",
        "pyinstaller_version",
        "workflow_run_id",
        "release_manifest_sha256",
        "shell_executable_sha256",
        "worker_executable_sha256",
        "qualifier_executable_sha256",
        "semantic_replay_sha256",
        "worker_probe_sha256",
        "unicode_path",
        "no_git",
        "no_system_python",
        "unrelated_cwd",
        "read_only_install",
        "locked_file",
        "spawn",
        "shutdown",
        "variant_equality",
    }
)
REQUIRED_SAFETY_FIELDS = frozenset(
    {
        "provider_acquisition_calls",
        "delivery_calls",
        "share_code_actions",
        "login_actions",
        "cookie_actions",
        "wallet_actions",
        "stake_actions",
        "wager_actions",
        "live_shadow_runs",
        "provider_workflow_dispatches",
        "historical_receipts_rewritten",
        "runtime_identity_weakened",
        "first_launch_pip_install",
        "entire_repo_bundled",
        "entire_venv_bundled",
    }
)


class AuditError(ValueError):
    """The PORT-02C receipt failed validation."""


def _canonical_bytes(value: dict) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _receipt_canonical_sha(value: dict) -> str:
    payload = {key: item for key, item in value.items() if key != "canonical_sha256"}
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _check_receipt(path: Path) -> dict:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AuditError(f"receipt is missing: {ARTIFACT_PATH}: {exc}") from exc
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise AuditError("receipt is not valid JSON") from exc
    if type(value) is not dict or set(value) != REQUIRED_TOP_FIELDS:
        raise AuditError("receipt top-level fields are not exact")
    if raw != _canonical_bytes(value):
        raise AuditError("receipt bytes are not canonical")
    if value["schema_version"] != 1:
        raise AuditError("receipt schema version is unsupported")
    if value["policy_id"] != POLICY_ID:
        raise AuditError("receipt policy is unsupported")
    if value["repository"] != "Thabearr/ATHENA":
        raise AuditError("receipt repository drifted")
    if value["implementation_base_main_sha"] != BASE_MAIN_SHA:
        raise AuditError("receipt implementation base drifted")
    if value["canonical_sha256"] != _receipt_canonical_sha(value):
        raise AuditError("receipt self-hash mismatch")

    predecessors = value["predecessors"]
    expected_predecessors = {
        "port_02a_policy_id": PORT02A_POLICY_ID,
        "port_02a_canonical_sha256": PORT02A_CANONICAL_SHA256,
        "port_02b_policy_id": PORT02B_POLICY_ID,
        "port_02b_canonical_sha256": PORT02B_CANONICAL_SHA256,
        "p4_4r_policy_id": P44R_POLICY_ID,
        "p4_4r_canonical_sha256": P44R_CANONICAL_SHA256,
        "p4_4s_policy_id": P44S_POLICY_ID,
        "p4_4s_canonical_sha256": P44S_CANONICAL_SHA256,
    }
    if type(predecessors) is not dict or predecessors != expected_predecessors:
        raise AuditError("receipt predecessor identities drifted")
    for short, rel, policy_key, sha_key in (
        ("port_02a", "artifacts/architecture/port_02_installed_release_identity_v1.json", "port_02a_policy_id", "port_02a_canonical_sha256"),
        ("port_02b", "artifacts/architecture/port_02_worker_launch_boundary_v1.json", "port_02b_policy_id", "port_02b_canonical_sha256"),
        ("p4_4r", "artifacts/architecture/p4_4r_shadow_runtime_composition_stabilization_v1.json", "p4_4r_policy_id", "p4_4r_canonical_sha256"),
        ("p4_4s", "artifacts/architecture/p4_4s_canonical_adapter_bound_context_builder_v1.json", "p4_4s_policy_id", "p4_4s_canonical_sha256"),
    ):
        try:
            on_disk = json.loads((ROOT / rel).read_bytes().decode("utf-8"))
        except (OSError, ValueError) as exc:
            raise AuditError(f"predecessor artifact unreadable: {rel}") from exc
        if on_disk.get("policy_id") != predecessors[policy_key]:
            raise AuditError(f"predecessor policy drifted on disk: {rel}")
        if on_disk.get("canonical_sha256") != predecessors[sha_key]:
            raise AuditError(f"predecessor canonical SHA drifted on disk: {rel}")
        _ = short
    return value


def _check_platforms(value: dict) -> None:
    platforms = value["platforms"]
    if type(platforms) is not list or len(platforms) != 2:
        raise AuditError("receipt must carry exactly two platform rows")
    seen = set()
    for row in platforms:
        if type(row) is not dict or set(row) != REQUIRED_PLATFORM_FIELDS:
            raise AuditError("platform row fields are not exact")
        key = (row["platform"], row["architecture"])
        if key in seen:
            raise AuditError("duplicate platform row")
        seen.add(key)
        for sha_field in (
            "release_manifest_sha256",
            "shell_executable_sha256",
            "worker_executable_sha256",
            "qualifier_executable_sha256",
            "semantic_replay_sha256",
            "worker_probe_sha256",
        ):
            if type(row[sha_field]) is not str or SHA256_RE.fullmatch(row[sha_field]) is None:
                raise AuditError(f"platform {sha_field} is not an exact SHA-256")
        for flag in (
            "unicode_path",
            "no_git",
            "no_system_python",
            "unrelated_cwd",
            "read_only_install",
            "locked_file",
            "spawn",
            "shutdown",
            "variant_equality",
        ):
            if row[flag] is not True:
                raise AuditError(f"platform gate {flag} is not PASS")
        if not row["workflow_run_id"] or not row["python_version"] or not row["pyinstaller_version"]:
            raise AuditError("platform evidence identifiers are incomplete")
    if seen != {("windows", "x86_64"), ("linux", "x86_64")}:
        raise AuditError("platform rows must be exactly Windows + Ubuntu x86-64")
    by_platform = {row["platform"]: row for row in platforms}
    if by_platform["windows"]["semantic_replay_sha256"] != by_platform["linux"]["semantic_replay_sha256"]:
        raise AuditError("cross-platform semantic replay digests differ")
    parity = value["cross_platform_parity"]
    if type(parity) is not dict or parity.get("semantic_replay_equal") is not True:
        raise AuditError("cross-platform parity is not proven")


def _check_safety(value: dict) -> None:
    safety = value["safety"]
    if type(safety) is not dict or set(safety) != REQUIRED_SAFETY_FIELDS:
        raise AuditError("safety fields are not exact")
    for key, item in safety.items():
        if item is not False and item != 0:
            raise AuditError(f"safety gate {key} is not zero/false")
    if value["classification"] != CLASSIFICATION:
        raise AuditError("receipt classification drifted")


def _check_no_paths_or_secrets(raw: bytes) -> None:
    text = raw.decode("utf-8")
    for marker in ("C:\\Users", "C:/Users", "/home/", "LOCALAPPDATA", "gho_", "ghp_", "sk-"):
        if marker in text:
            raise AuditError(f"receipt leaks host-specific or secret text: {marker}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit the PORT-02C native runtime receipt.")
    parser.add_argument("--check", action="store_true", required=True)
    args = parser.parse_args(argv)
    _ = args
    try:
        path = ROOT / ARTIFACT_PATH
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise AuditError(f"receipt is missing (expected before Phase C): {exc}") from exc
        value = _check_receipt(path)
        _check_platforms(value)
        _check_safety(value)
        _check_no_paths_or_secrets(raw)
    except AuditError as exc:
        sys.stderr.write(f"PORT-02C audit failed: {exc}\n")
        return 1
    sys.stdout.write("PORT_02C_RECEIPT_OK\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
