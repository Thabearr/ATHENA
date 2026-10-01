#!/usr/bin/env python3
"""Validate the PORT-02B worker-launch contract offline and read-only."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Sequence

from runtime.source_identity import (
    SourceIdentityError,
    canonical_payload_sha256,
    read_tracked_head_blob,
    validate_repository_relative_path,
)
from scripts import audit_auth_01_analysis_only_shadow as auth_01d_historical
from scripts import audit_auth_01_analysis_only_shadow_worker_boundary as auth_01d_forward
from scripts import audit_port_02_installed_release_identity as port02a


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = "artifacts/architecture/port_02_worker_launch_boundary_v1.json"
POLICY_ID = "ATHENA_PORT_02_WORKER_LAUNCH_BOUNDARY_V1"
BASE_MAIN_SHA = "235fd86a1de26732473e7e839b5147b50bcfcd86"
PORT02A_CANONICAL_SHA256 = "8e08b1e45d589e56f3f7577711fb919958f31ff77c147533ae834871ec85f70f"
AUTH_01D_HISTORICAL_SHA256 = "7b09adb4882d49749c33efecbce0b1c8985a2d3bdec52417f7b02f8f335f4a86"
AUTH_01D_HISTORICAL_REPLAY_SHA256 = "3b792193ef813f4aab79d7c3f9d48550270f3ae008265cc9ceb9c3d629e974f5"
AUTH_01D_FORWARD_POLICY_ID = "ATHENA_AUTH_01_ANALYSIS_ONLY_SHADOW_WORKER_BOUNDARY_V1"
AUTH_01D_FORWARD_CANONICAL_SHA256 = "51385a66ecebe7e07516601ed2d19c6f6a007c9ee4274e987ddf499e45b4292c"
AUTH_01D_FORWARD_SEMANTIC_SHA256 = "aa019454ccc2bbad95f5a53fe3089ee9e8d2113e74f493de8735a6d77f5d9a63"
P44H_CANONICAL_SHA256 = "0000a5978268909dd07330d59079bc4d7f8d32c0fee161653a4a19eea9b97c64"
P44I_CANONICAL_SHA256 = "d6f65a382c4ef23318a81261e48b8e717f768864a6e1e5baed61af3c11351a7c"
GITATTRIBUTES_BASE_BLOB = "39ccd8d38ce17c105a906e2f1416f68e64fcc862"
SHA1_RE = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "policy_id",
        "repository",
        "implementation_base_main_sha",
        "predecessor",
        "worker_command_contract",
        "development_launcher",
        "installed_launcher",
        "service_migration",
        "process_ownership",
        "offline_probe",
        "negative_matrix",
        "historical_regressions",
        "immutable_anchors",
        "current_source_evolution",
        "safety",
        "governance",
        "canonical_sha256",
    }
)
SOURCE_PATHS = (
    "runtime/worker_entry.py",
    "runtime/worker_launcher.py",
    "services/athena_run_service.py",
)
EXPECTED_ANCHORS = (
    {
        "anchor_id": "PORT02A_RECEIPT",
        "path": "artifacts/architecture/port_02_installed_release_identity_v1.json",
        "git_blob_sha1": "3f507509432172b8334ad78f31ca664c5dbb1dfb",
        "git_blob_payload_sha256": "d13b5678bf6cde53de8117ec118f36ed2308f5af48954dbbf4893714c5c90c1b",
        "canonical_sha256": PORT02A_CANONICAL_SHA256,
    },
    {
        "anchor_id": "P44H_RECEIPT",
        "path": "artifacts/architecture/p4_4h_current_shadow_canonical_run_migration_review_v1.json",
        "git_blob_sha1": "924febf73ab39a55433e69fd64cc203d493d68df",
        "git_blob_payload_sha256": "95707fd03a83fa1c20a5128f9ec2b9494c25b24cf8f23c16a77b5fb62d25da15",
        "canonical_sha256": P44H_CANONICAL_SHA256,
    },
    {
        "anchor_id": "P44I_RECEIPT",
        "path": "artifacts/architecture/p4_4i_shadow_supervisor_failure_evidence_v1.json",
        "git_blob_sha1": "d2b5d79d93df230c922d31a06d9bbcb7bdaf2c16",
        "git_blob_payload_sha256": "699edcdda6f399315d119450fc15fb3021f7653f572b0e54bd170c7521865ee6",
        "canonical_sha256": P44I_CANONICAL_SHA256,
    },
    {
        "anchor_id": "P44R_RECEIPT",
        "path": "artifacts/architecture/p4_4r_shadow_runtime_composition_stabilization_v1.json",
        "git_blob_sha1": "0ed10b25f57a87037bf2d786a8f2ec77b0b2f55f",
        "git_blob_payload_sha256": "965f42e56823de78013c40a5b839ea81d0d5c79aadb4a02bc122110014a51eab",
        "canonical_sha256": "90e2d7e984609ded80c9113a05453628bebadfcb3cede7fc95b9696931016552",
    },
    {
        "anchor_id": "P44S_RECEIPT",
        "path": "artifacts/architecture/p4_4s_canonical_adapter_bound_context_builder_v1.json",
        "git_blob_sha1": "a8368721e2181e44a54bce25aae6171df11b6b40",
        "git_blob_payload_sha256": "78ee27a58dff7c9c22ca7aee6740d9aa35bcc7d655aa9e2ad0a6ff4047ad8d8e",
        "canonical_sha256": "0907272a20b439e6874ee3b3fa399a488e8dd3c9a6e428dafa2aa53202c513c3",
    },
    {
        "anchor_id": "BASE00_JSON",
        "path": "artifacts/product/product_baseline_v1.json",
        "git_blob_sha1": "a37c079b9175c1e24ac098b87fd6bc28e23e9527",
        "git_blob_payload_sha256": "c171cc6adf713d4c4ec97a0f23eb73ae3ac48abc472e71db9afbd33fbd0013a3",
        "canonical_sha256": "d3db092eb890f45cae9eccfefb7134a59bf4d1b9f43e43160421c4210832b27f",
    },
    {
        "anchor_id": "P05_RUNTIME_ARTIFACT",
        "path": "artifacts/architecture/runtime-reachability-v1.json",
        "git_blob_sha1": "0c840c9b245d0eb8610a62ac3cc8bbc3be1120a1",
        "git_blob_payload_sha256": "a8ccb4c0c8ab2bea9bd133bb7fa7e155957bf1e38e5bf7ae6cccb4f44640f7e4",
        "canonical_sha256": "a8ccb4c0c8ab2bea9bd133bb7fa7e155957bf1e38e5bf7ae6cccb4f44640f7e4",
    },
    {
        "anchor_id": "PORT01A_INVENTORY",
        "path": "artifacts/architecture/port_01_windows_failure_inventory_v1.json",
        "git_blob_sha1": "6ff6fd3153419e7dae7f789401dc1b757d207126",
        "git_blob_payload_sha256": "b6958170ab20752656d40a8809563fe939c2875a34d88366430af216536d5aec",
        "canonical_sha256": "78b92cde4681d3bbd71007ed4c3e434717c029f6745b3b37ecb93bb917738966",
    },
    {
        "anchor_id": "PORT01B_RECEIPT",
        "path": "artifacts/architecture/port_01_source_identity_parity_v1.json",
        "git_blob_sha1": "4ad2dd77cc95a82410aa973387f81c00175f04a8",
        "git_blob_payload_sha256": "a307f5a002c533ff25db62634329c27e772b7e441aab8d3583c719c60a9a614e",
        "canonical_sha256": "14d1c6e71f2f01aea720c451bf226efd9e667092c9d8a72062d966e59c2e9219",
    },
)
OFFLINE_PROBE_VECTOR = {
    "request_artifact_id": "99fc45ced4f4932395876a3782656f4fc1c4de59c52baad4757a180d9161f8a8",
    "development_release_identity_id": BASE_MAIN_SHA,
    "installed_release_identity_id": "a" * 64,
    "semantic_probe_sha256": "cf43f9841d66e7202c855f1f9624384274bff399d3193614d4dad356d63fa96b",
    "semantic_probe_inner_canonical_sha256": "28d778a3c675f7aa36775253bda4fc305cb232d018af7514104261c368d0fabb",
    "development_provenance_sha256": "6589b291b6c5b2239c415768704c9a82cee3b7a518f17db361d4a89311d8f48b",
    "development_provenance_inner_canonical_sha256": "e7b4fbc4c651e0ac129bee5e239a3d219108d86545f13739f558f4eb0e214367",
    "installed_provenance_sha256": "8532a8fddf457826821af0c69bdcb35f43d7b102bb034200c8b845ab86af4d80",
    "installed_provenance_inner_canonical_sha256": "c7a7f7254e05bb05be6df44ebf2840c847a8f6f836f03c10ff676c9c24376fa3",
}
BEFORE_SOURCE = {
    "runtime/worker_entry.py": (None, None),
    "runtime/worker_launcher.py": (None, None),
    "services/athena_run_service.py": (
        "4f0d41095df5d846d9dc9b892ad27a2af60183bc",
        "9433b1cea639a933d4e7ed1aaf713a2e5d48013154f29641854cbdc1fd557241",
    ),
}


class Port02BAuditError(ValueError):
    """PORT-02B receipt or worker source boundary is invalid."""


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise Port02BAuditError("PORT-02B receipt cannot be serialized canonically") from exc


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise Port02BAuditError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise Port02BAuditError(f"non-finite JSON value is forbidden: {value}")


def _load_strict(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object, parse_constant=_reject_constant)
    except Port02BAuditError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Port02BAuditError("PORT-02B receipt is not strict UTF-8 JSON") from exc
    if type(value) is not dict or raw != canonical_json_bytes(value):
        raise Port02BAuditError("PORT-02B receipt root or canonical bytes are invalid")
    return value


def _require_sha(value: Any, *, sha1: bool = False, label: str) -> str:
    pattern = SHA1_RE if sha1 else SHA256_RE
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise Port02BAuditError(f"{label} must be lowercase exact {'SHA-1' if sha1 else 'SHA-256'}")
    return value


def _walk_strings(value: Any):
    if type(value) is dict:
        for key, item in value.items():
            yield key, item
            yield from _walk_strings(item)
    elif type(value) is list:
        for item in value:
            yield from _walk_strings(item)
    elif type(value) is str:
        yield "", value


def _validate_no_local_paths_or_secrets(document: dict[str, Any]) -> None:
    forbidden = {"token", "cookie", "credential", "password", "share_code", "share_url", "secret"}
    for key, value in _walk_strings(document):
        if key.lower() in forbidden:
            raise Port02BAuditError("receipt contains a forbidden secret-bearing field")
        if type(value) is str and re.match(r"^[A-Za-z]:[\\/]|^/(?:Users|home|tmp)/", value):
            raise Port02BAuditError("receipt contains a workstation-specific absolute path")


def load_receipt() -> dict[str, Any]:
    try:
        raw, _identity = read_tracked_head_blob(ROOT, ARTIFACT_PATH)
    except SourceIdentityError as exc:
        raise Port02BAuditError("PORT-02B receipt must be an unchanged tracked HEAD blob") from exc
    return _load_strict(raw)


def _expected_fixed_fields(document: dict[str, Any]) -> None:
    if document["predecessor"] != {
        "policy_id": port02a.POLICY_ID,
        "canonical_sha256": PORT02A_CANONICAL_SHA256,
        "merged_main_sha": BASE_MAIN_SHA,
        "trusted_manifest_mode": "TRUSTED_MANIFEST_SHA256_V1",
    }:
        raise Port02BAuditError("PORT-02A predecessor identity drifted")

    command = document["worker_command_contract"]
    if command != {
        "schema_version": 1,
        "policy_id": "ATHENA_WORKER_COMMAND_V1",
        "allowed_operations": ["CURRENT_SHADOW_REQUEST", "OFFLINE_IDENTITY_PROBE"],
        "arbitrary_module": False,
        "arbitrary_function": False,
        "arbitrary_argv": False,
        "arbitrary_environment": False,
        "arbitrary_cwd": False,
        "shell": False,
        "request_artifact": "athena-run-request.json",
        "request_artifact_identity": "RUNREQUEST_V1_CANONICAL_SHA256",
        "envelope_artifact": "athena-execution-envelope-v2.json_if_actually_present",
        "current_envelope_artifact_id": None,
        "command_artifact": "athena-worker-command.json",
        "contradictory_existing_command": "FAIL_CLOSED",
        "command_is_retry_authority": False,
        "mode_is_user_extensible": False,
    }:
        raise Port02BAuditError("worker command vocabulary or identity binding drifted")

    if document["development_launcher"] != {
        "argv_prefix": ["sys.executable", "-m", "runtime.worker_entry"],
        "command_file_flag": "--command-file",
        "source_flag": "--development-root",
        "repository_root": "EXPLICIT_VERIFIED_DEVELOPMENT_CHECKOUT_ROOT",
        "head_binding": "EXACT_VERIFIED_GIT_HEAD_SHA1",
        "shell": False,
        "cwd_role": "IMPORT_CONTEXT_ONLY_NOT_IDENTITY_AUTHORITY",
    }:
        raise Port02BAuditError("DevelopmentCheckout launcher contract drifted")

    installed = document["installed_launcher"]
    if installed != {
        "worker_executable": "SEPARATELY_SUPPLIED_ABSOLUTE_RELEASE_ROOT_BIN_FILE",
        "worker_executable_hash_policy": "SYNTHETIC_INSTALLED_WORKER_EXECUTABLE_HASH_PIN",
        "worker_executable_sha256_checked_before_spawn": True,
        "manifest_authenticates_worker_executable": False,
        "no_path_lookup": True,
        "argv_prefix": ["CONFIGURED_WORKER_EXECUTABLE"],
        "command_file_flag": "--command-file",
        "release_root_flag": "--release-root",
        "trusted_manifest_flag": "--trusted-manifest-sha256",
        "sys_executable": False,
        "python_module_switch": False,
        "shell": False,
        "writable_roots": "PORT_02A_WRITABLE_ROOTS_REQUIRED",
        "classification": "SYNTHETIC_INSTALLED_WORKER_LAUNCH_CONTRACT_VERIFIED",
        "native_packaged_worker_execution_verified": False,
    }:
        raise Port02BAuditError("installed worker executable contract is overstated or changed")

    service = document["service_migration"]
    if service != {
        "executor_owner": "_ShadowSupervisorExecutor",
        "direct_service_subprocess_launch": False,
        "worker_launch_helper": "_run_reviewed_shadow_worker",
        "path": "RunRequest->AthenaRunService->_ShadowSupervisorExecutor->WorkerLauncher->worker_entry->CurrentShadowSupervisor",
        "current_shadow_supervisor_retained": True,
        "request_receipt_adaptation_unchanged": True,
        "business_timeout_owner": "scripts.execute_current_shadow_request",
        "business_timeout_moved": False,
        "second_timeout_added": False,
        "execution_envelope_artifact_id": None,
    }:
        raise Port02BAuditError("AthenaRunService migration changed its reviewed boundary")

    process = document["process_ownership"]
    if process != {
        "returncode": "EXACT_INTEGER_PRESERVED",
        "stdout": "CAPTURED_TEXT",
        "stderr": "CAPTURED_TEXT",
        "handle": "POLL_COMMUNICATE_REQUEST_CANCEL",
        "retry_or_requeue": False,
        "windows": "NEW_PROCESS_GROUP_INTERFACE",
        "linux": "NEW_SESSION_PROCESS_GROUP_INTERFACE",
        "process_group_ownership_interface_present": True,
        "native_tree_kill_qualified": False,
        "business_timeout": None,
    }:
        raise Port02BAuditError("process ownership classification drifted")

    negative = document["negative_matrix"]
    expected_negative = {
        "operation_injection", "module_or_function_injection", "argv_injection",
        "environment_or_cwd_injection", "run_path_traversal", "run_root_symlink",
        "request_identity_mismatch", "envelope_identity_mismatch", "release_identity_mismatch",
        "release_root_mismatch", "missing_worker_executable", "worker_executable_symlink",
        "worker_executable_hash_mismatch", "worker_executable_outside_bin",
        "worker_run_directory_outside_writable_roots", "no_second_timeout",
    }
    if type(negative) is not dict or set(negative) != expected_negative or any(
        value != "REJECTED_BEFORE_CHILD" for value in negative.values()
    ):
        raise Port02BAuditError("worker launch negative matrix is incomplete")

    if document["historical_regressions"] != {
        "p4_2": "REQUIRED_NO_OUTER_CURRENT_SHADOW_TIMEOUT",
        "p4_4h_receipt_canonical_sha256": P44H_CANONICAL_SHA256,
        "p4_4h_semantics_rewritten": False,
        "p4_4i_receipt_canonical_sha256": P44I_CANONICAL_SHA256,
        "p4_4i_semantics_rewritten": False,
        "auth_01d_historical": {
            "policy_id": auth_01d_historical.POLICY_ID,
            "canonical_sha256": AUTH_01D_HISTORICAL_SHA256,
            "deterministic_replay_sha256": AUTH_01D_HISTORICAL_REPLAY_SHA256,
            "audit_result_on_b4_source": "SKIP_SOURCE_MOVED",
            "historical_integrity": "PASS",
            "historical_replay_reexecuted": False,
        },
        "auth_01d_worker_boundary_forward": {
            "policy_id": AUTH_01D_FORWARD_POLICY_ID,
            "canonical_sha256": AUTH_01D_FORWARD_CANONICAL_SHA256,
            "audit_result": "PASS",
            "current_release_identity_required": True,
            "semantic_continuity_sha256": AUTH_01D_FORWARD_SEMANTIC_SHA256,
            "external_calls": 0,
        },
        "base_00_snapshot_rewritten": False,
        "port_01a_b2_and_02a_receipts_rewritten": False,
    }:
        raise Port02BAuditError("historical architecture claims changed")

    anchors = document["immutable_anchors"]
    if type(anchors) is not list or anchors != list(EXPECTED_ANCHORS):
        raise Port02BAuditError("immutable anchor list/order drifted")
    for item in anchors:
        path = validate_repository_relative_path(item["path"])
        _require_sha(item["git_blob_sha1"], sha1=True, label="immutable anchor Git blob SHA")
        _require_sha(item["git_blob_payload_sha256"], label="immutable anchor payload SHA")
        payload, identity = read_tracked_head_blob(ROOT, path)
        if (
            identity.git_blob_sha1 != item["git_blob_sha1"]
            or identity.git_blob_payload_sha256 != item["git_blob_payload_sha256"]
            or hashlib.sha256(payload).hexdigest() != item["git_blob_payload_sha256"]
        ):
            raise Port02BAuditError(f"immutable anchor source bytes changed: {path}")

    source_rows = document["current_source_evolution"]
    if type(source_rows) is not list or tuple(row.get("path") for row in source_rows) != SOURCE_PATHS:
        raise Port02BAuditError("current worker source evolution path list changed")
    for row in source_rows:
        path = validate_repository_relative_path(row.get("path"))
        before_blob, before_payload = BEFORE_SOURCE[path]
        if row.get("before_git_blob_sha1") != before_blob or row.get("before_git_blob_payload_sha256") != before_payload:
            raise Port02BAuditError(f"pre-B4 source identity changed for {path}")
        if before_blob is not None:
            _require_sha(before_blob, sha1=True, label=f"{path} before Git blob SHA")
            _require_sha(before_payload, label=f"{path} before Git payload SHA")
        _require_sha(row.get("after_git_blob_sha1"), sha1=True, label=f"{path} after Git blob SHA")
        _require_sha(row.get("after_git_blob_payload_sha256"), label=f"{path} after Git payload SHA")

    if document["safety"] != {
        "network_calls": 0,
        "provider_calls": 0,
        "delivery_calls": 0,
        "workflow_dispatches": 0,
        "current_shadow_live_runs": 0,
        "share_code_actions": 0,
        "email_actions": 0,
        "login_actions": 0,
        "cookie_actions": 0,
        "wallet_actions": 0,
        "staking_actions": 0,
        "wager_actions": 0,
        "historical_hashes_repinned": False,
        "historical_receipts_rewritten": False,
        "gitattributes_changed": False,
        "packaging_implemented": False,
    }:
        raise Port02BAuditError("PORT-02B safety statement drifted")
    if document["governance"] != {
        "source_review_counter_while_unmerged": "4/5",
        "source_review_counter_if_merged": "5/5",
        "mandatory_reread_after_merge": True,
        "reread_required_before_port_02c": True,
        "port_02c_started": False,
        "lg_a_run": False,
        "lg_a_authorized": False,
        "lg_a_status": "LG_A_WAITING_SEPARATE_OWNER_AUTHORIZATION",
        "p4_4_complete": False,
        "architecture_checkpoint_e_complete": False,
        "clean_successor_proof_complete": False,
        "caller_migration_authorized": False,
        "workflow_retirement_authorized": False,
    }:
        raise Port02BAuditError("PORT-02B governance state drifted")

    offline = document["offline_probe"]
    if (
        type(offline) is not dict
        or offline.get("classification") != "SYNTHETIC_INSTALLED_WORKER_LAUNCH_CONTRACT_VERIFIED"
        or offline.get("semantic_receipts_equal") is not True
        or offline.get("provenance_receipts_differ_by_source_mode") is not True
        or offline.get("development_release_identity_kind") != "DEVELOPMENT_CHECKOUT"
        or offline.get("installed_release_identity_kind") != "INSTALLED_RELEASE"
        or offline.get("envelope_artifact_id") is not None
        or offline.get("provider_calls") != 0
        or offline.get("delivery_calls") != 0
        or offline.get("wager") is not False
        or {key: offline.get(key) for key in OFFLINE_PROBE_VECTOR} != OFFLINE_PROBE_VECTOR
    ):
        raise Port02BAuditError("offline probe evidence is incomplete or overstated")
    for field in (
        "semantic_probe_sha256",
        "development_provenance_sha256",
        "installed_provenance_sha256",
    ):
        _require_sha(offline.get(field), label=field)
    if offline["development_provenance_sha256"] == offline["installed_provenance_sha256"]:
        raise Port02BAuditError("source-mode provenance must remain distinct")


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None


def _require_current_source(path: str, pinned_blob: str, pinned_payload: str) -> tuple[bytes, bool]:
    try:
        payload, identity = read_tracked_head_blob(ROOT, path)
    except SourceIdentityError as exc:
        raise Port02BAuditError(f"tracked worker source could not be read: {path}") from exc
    if identity.git_blob_sha1 != pinned_blob or identity.git_blob_payload_sha256 != pinned_payload:
        return payload, False
    return payload, True


def _validate_worker_sources(document: dict[str, Any]) -> list[str]:
    moved: list[str] = []
    sources = {row["path"]: row for row in document["current_source_evolution"]}
    current_payloads: dict[str, bytes] = {}
    for path in SOURCE_PATHS:
        row = sources[path]
        payload, same = _require_current_source(
            path,
            row["after_git_blob_sha1"],
            row["after_git_blob_payload_sha256"],
        )
        current_payloads[path] = payload
        if not same:
            moved.append(path)

    try:
        launcher_source = current_payloads["runtime/worker_launcher.py"].decode("utf-8")
        entry_source = current_payloads["runtime/worker_entry.py"].decode("utf-8")
        service_source = current_payloads["services/athena_run_service.py"].decode("utf-8")
        supervisor_source, _ = read_tracked_head_blob(ROOT, "scripts/execute_current_shadow_request.py")
        supervisor_text = supervisor_source.decode("utf-8")
    except (UnicodeDecodeError, SourceIdentityError) as exc:
        raise Port02BAuditError("worker source boundary is not readable from exact tracked HEAD") from exc

    try:
        launcher_tree = ast.parse(launcher_source)
        service_tree = ast.parse(service_source)
    except SyntaxError as exc:
        raise Port02BAuditError("worker launcher or AthenaRunService source is not valid Python") from exc
    if "shell=True" in launcher_source or "os.system(" in launcher_source:
        raise Port02BAuditError("worker launcher contains a forbidden shell surface")
    if "communicate(timeout=" in launcher_source or "wait(timeout=" in launcher_source:
        raise Port02BAuditError("worker launcher contains a business timeout")
    if "importlib.import_module" in launcher_source or "shlex.split" in launcher_source:
        raise Port02BAuditError("worker launcher contains dynamic command selection")
    spawn_calls = [
        node for node in ast.walk(launcher_tree)
        if isinstance(node, ast.Call) and _call_name(node.func) == "subprocess.Popen"
    ]
    if len(spawn_calls) != 1:
        raise Port02BAuditError("worker launch must have exactly one subprocess creation seam")
    popen = spawn_calls[0]
    shell = next((item.value for item in popen.keywords if item.arg == "shell"), None)
    if not isinstance(shell, ast.Constant) or shell.value is not False:
        raise Port02BAuditError("subprocess launch does not explicitly use shell=False")
    if not popen.args or not isinstance(popen.args[0], ast.Call):
        raise Port02BAuditError("subprocess launch argv is not constructed as a reviewed argument list")
    service_executor = next(
        (node for node in service_tree.body if isinstance(node, ast.ClassDef) and node.name == "_ShadowSupervisorExecutor"),
        None,
    )
    if service_executor is None:
        raise Port02BAuditError("canonical _ShadowSupervisorExecutor disappeared")
    if any(
        isinstance(node, ast.Call) and _call_name(node.func) == "subprocess.run"
        for node in ast.walk(service_executor)
    ):
        raise Port02BAuditError("AthenaRunService still directly launches the Current Shadow subprocess")
    if "Do not add a second timeout here" not in service_source:
        raise Port02BAuditError("service no-second-timeout invariant is missing")
    if "_supervisor_timeout_seconds()" not in supervisor_text or "_write_timeout_receipt(" not in supervisor_text:
        raise Port02BAuditError("Current Shadow supervisor no longer owns timeout/finalization")
    if "runtime.worker_launcher" not in entry_source:
        # The entry imports its exact WorkerCommand verifier from this boundary.
        raise Port02BAuditError("worker entry no longer shares the reviewed command verifier")

    attributes = read_tracked_head_blob(ROOT, ".gitattributes")[1]
    from scripts import audit_port_01_source_identity_parity as port01
    # Historical PORT-02B anchor remains exact; current byte materialization is
    # the same narrowly pinned PORT-02C successor verified by the predecessor.
    successor = port01.PORT02C_GIT_ATTRIBUTES_SUCCESSOR
    if (attributes.git_blob_sha1 != successor["git_blob_sha1"]
            or attributes.git_blob_payload_sha256 != successor["git_blob_payload_sha256"]):
        raise Port02BAuditError(".gitattributes differs from exact PORT-02C byte-materialization successor")
    return moved


def validate_current_state() -> dict[str, Any]:
    document = load_receipt()
    if type(document) is not dict or set(document) != RECEIPT_FIELDS:
        raise Port02BAuditError("PORT-02B receipt fields are not exact")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise Port02BAuditError("PORT-02B schema version drifted")
    if document["policy_id"] != POLICY_ID or document["repository"] != "Thabearr/ATHENA":
        raise Port02BAuditError("PORT-02B receipt identity drifted")
    if document["implementation_base_main_sha"] != BASE_MAIN_SHA:
        raise Port02BAuditError("PORT-02B implementation base changed")
    _require_sha(document["implementation_base_main_sha"], sha1=True, label="implementation base SHA")
    _expected_fixed_fields(document)
    _validate_no_local_paths_or_secrets(document)
    claimed = _require_sha(document.get("canonical_sha256"), label="receipt canonical SHA")
    unsigned = dict(document)
    del unsigned["canonical_sha256"]
    if claimed != canonical_payload_sha256(canonical_json_bytes(unsigned)):
        raise Port02BAuditError("PORT-02B receipt canonical self-hash mismatch")

    try:
        predecessor = port02a.validate_current_state()
    except (ValueError, SourceIdentityError) as exc:
        raise Port02BAuditError("PORT-02A installed release identity predecessor did not validate") from exc
    if predecessor.get("canonical_sha256") != PORT02A_CANONICAL_SHA256:
        raise Port02BAuditError("PORT-02A predecessor canonical identity changed")

    moved = _validate_worker_sources(document)
    historical_auth = auth_01d_historical.check_artifact()
    expected_historical_auth = document["historical_regressions"]["auth_01d_historical"]
    if historical_auth != {
        "result": "SKIP_SOURCE_MOVED",
        "policy_id": auth_01d_historical.POLICY_ID,
        "artifact_canonical_sha256": AUTH_01D_HISTORICAL_SHA256,
        "historical_integrity": "PASS",
        "historical_replay_sha256": AUTH_01D_HISTORICAL_REPLAY_SHA256,
        "historical_replay_reexecuted": False,
        "reason": "CURRENT_WORKER_BOUNDARY_REQUIRES_VERIFIED_CURRENT_RELEASE_IDENTITY",
        "moved_paths": [
            "services/athena_run_service.py",
            "runtime/worker_launcher.py",
            "runtime/worker_entry.py",
        ],
    } or expected_historical_auth != {
        "policy_id": auth_01d_historical.POLICY_ID,
        "canonical_sha256": AUTH_01D_HISTORICAL_SHA256,
        "deterministic_replay_sha256": AUTH_01D_HISTORICAL_REPLAY_SHA256,
        "audit_result_on_b4_source": "SKIP_SOURCE_MOVED",
        "historical_integrity": "PASS",
        "historical_replay_reexecuted": False,
    }:
        raise Port02BAuditError("AUTH-01D immutable historical evidence is not preserved exactly")

    forward_auth = auth_01d_forward.check_artifact()
    expected_forward_auth = document["historical_regressions"]["auth_01d_worker_boundary_forward"]
    if (
        forward_auth.get("result") != "PASS"
        or forward_auth.get("policy_id") != AUTH_01D_FORWARD_POLICY_ID
        or forward_auth.get("historical_predecessor_integrity") != "PASS"
        or forward_auth.get("semantic_continuity_sha256") != AUTH_01D_FORWARD_SEMANTIC_SHA256
        or forward_auth.get("historical_full_receipt_sha_compared") is not False
        or forward_auth.get("provider_network_calls") != 0
        or forward_auth.get("share_transport_calls") != 0
        or forward_auth.get("account_wager_calls") != 0
        or forward_auth.get("worker_command", {}).get("release_identity_id") != forward_auth.get("current_head_sha")
        or forward_auth.get("run_receipt_exact_commit_sha") != forward_auth.get("current_head_sha")
        or expected_forward_auth
        != {
            "policy_id": AUTH_01D_FORWARD_POLICY_ID,
            "canonical_sha256": AUTH_01D_FORWARD_CANONICAL_SHA256,
            "audit_result": "PASS",
            "current_release_identity_required": True,
            "semantic_continuity_sha256": AUTH_01D_FORWARD_SEMANTIC_SHA256,
            "external_calls": 0,
        }
    ):
        raise Port02BAuditError("AUTH-01D current worker-boundary forward evidence is not exact")
    return {
        "result": (
            "PORT_02B_WORKER_LAUNCH_BOUNDARY_SKIP_SOURCE_MOVED"
            if moved
            else "PORT_02B_WORKER_LAUNCH_BOUNDARY_PASS"
        ),
        "canonical_sha256": claimed,
        "source_moved_paths": moved,
        "predecessor_canonical_sha256": predecessor["canonical_sha256"],
        "auth_01d_historical_integrity": "PASS",
        "auth_01d_historical_replay_reexecuted": False,
        "auth_01d_forward_result": "PASS",
        "auth_01d_forward_canonical_sha256": AUTH_01D_FORWARD_CANONICAL_SHA256,
        "auth_01d_semantic_continuity_sha256": forward_auth["semantic_continuity_sha256"],
        "network_provider_delivery_calls": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate the committed PORT-02B receipt")
    args = parser.parse_args(argv)
    if not args.check:
        parser.error("--check is required; this audit has no write mode")
    try:
        result = validate_current_state()
    except (Port02BAuditError, SourceIdentityError) as exc:
        print(f"PORT-02B worker launch audit: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
