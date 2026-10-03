"""Source-safe A2 transport proof. Never executes discovered callers."""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
from functools import lru_cache
import io
from pathlib import Path
import subprocess
import tokenize
import yaml

ROOT = Path(__file__).resolve().parents[1]
BASE_MAIN = "86ffc41205d83f5e4b37d20d35d73f9f97f3b23f"
BASE_TREE = "1fd395339f09fa3726b1c633399c3ee79d7dfb4e"
WORKFLOW_TREE = "9b08653f1a12bb1b3d964fbd910396ff955740da"
POLICY_ID = "ATHENA_CORE_01D_CI_OFFLINE_TRANSPORT_BOUNDARY_V1"
INVENTORY_PATH = "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v1.json"
RECEIPT_PATH = "artifacts/architecture/core_01d_ci_offline_transport_boundary_v1.json"
COMPLETION_PATH = "artifacts/architecture/core_01d_checkpoint_e_completion_v3.json"
TARGETS = ((".github/workflows/athena-patch-bridge.yml", "issue_comment"),
           (".github/workflows/tests.yml", "pull_request"), (".github/workflows/tests.yml", "push"))
GUARD_PATHS = ("sitecustomize.py", "tests/conftest.py", "tests/offline_transport.py",
               "tests/offline_linux.py", "tests/_offline_bootstrap/sitecustomize.py")
A2_PATHS = frozenset((*GUARD_PATHS, INVENTORY_PATH, RECEIPT_PATH, COMPLETION_PATH,
    "scripts/audit_core_01d_ci_offline_transport_boundary.py",
    "scripts/audit_core_01d_checkpoint_e_completion_v3.py",
    "tests/test_core_01d_ci_offline_transport_boundary.py",
    "tests/test_core_01d_checkpoint_e_completion_v3.py",
    "tests/native/test_port_02c_qualifier_safety.py",
    "tests/test_accumulator_optimizer_trust_boundaries.py",
    "tests/test_market_router_trust_boundaries.py",
    "scripts/audit_core_01d_checkpoint_e_completion_v2.py",
    "scripts/audit_core_01d_authority_reachability_review_a.py",
    "scripts/audit_checkpoint_e_workflows.py",
    "tests/test_core_01d_checkpoint_e_completion.py",
    "tests/test_core_01d_checkpoint_e_completion_v2.py",
    "tests/test_win_either_half_campaign_commitment.py",
    "scripts/audit_core_01d_checkpoint_e_completion.py"))
# These are authenticated predecessor tree entries, not current source pins.
HISTORICAL_TEST_BLOBS = {
    "tests/conftest.py": "6d4d2ddb621a27f788d0c25499e418092f260ef1",
    "tests/native/test_port_02c_qualifier_safety.py": "2fe50e18837c36c5e97adac2e89a9da72f6847ec",
    "tests/test_accumulator_optimizer_trust_boundaries.py": "b4f22663fc5a72c341920de61d0ec7877298a5da",
    "tests/test_market_router_trust_boundaries.py": "e4a6ab718d5905bbe10d9ae57c0a94b3f98ce287",
}
HISTORICAL_CONFTEST_BYTES = base64.b64decode("ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKaW1wb3J0IHB5dGVzdAoKCl9QUjEyNV9SVU5ORVJfVEVTVF9NT0RVTEUgPSAidGVzdF9wcjY5X3ByaW1hcnlfdGltZV9iYXNpc19ldmlkZW5jZV9hY3F1aXNpdGlvbl9ydW5uZXIiCl9QUjEyNV9SRUFMX1VQU1RSRUFNX1RFU1RTID0gewogICAgInRlc3RfdXBzdHJlYW1fcHJvdG9jb2xfbXV0YXRpb25fZmFpbHNfY2xvc2VkIiwKfQoKCkBweXRlc3QuZml4dHVyZShzY29wZT0ic2Vzc2lvbiIpCmRlZiBfcHIxMjVfdmVyaWZpZWRfdXBzdHJlYW1fcHJvdG9jb2woKToKICAgICIiIlBlcmZvcm0gdGhlIGV4cGVuc2l2ZSBQUjEyNeKGklBSMTI0IGFuY2VzdHJ5IHZhbGlkYXRpb24gb25jZSBwZXIgdGVzdCBzZXNzaW9uLiIiIgogICAgaW1wb3J0IGRvbWFpbi5wcjY5X3ByaW1hcnlfdGltZV9iYXNpc19ldmlkZW5jZV9hY3F1aXNpdGlvbl9ydW5uZXIgYXMgY29udHJhY3QKCiAgICByZXR1cm4gY29udHJhY3QuX3ZlcmlmeV91cHN0cmVhbSgpCgoKQHB5dGVzdC5maXh0dXJlKGF1dG91c2U9VHJ1ZSkKZGVmIF9yZXVzZV9wcjEyNV92ZXJpZmllZF91cHN0cmVhbV9wcm90b2NvbChyZXF1ZXN0LCBtb25rZXlwYXRjaCk6CiAgICAiIiJSZXVzZSB2ZXJpZmllZCBpbW11dGFibGUgYW5jZXN0cnkgZm9yIFBSMTI1IHN0YXRlLW1hY2hpbmUgdGVzdHMgb25seS4KCiAgICBQcm9kdWN0aW9uIGNvZGUgaXMgdW5jaGFuZ2VkLiBUaGUgZGVkaWNhdGVkIHVwc3RyZWFtLW11dGF0aW9uIHRlc3QgZGVsaWJlcmF0ZWx5CiAgICByZXRhaW5zIHRoZSBvcmlnaW5hbCB2ZXJpZmllciBzbyBmYWlsLWNsb3NlZCB0YW1wZXIgZGV0ZWN0aW9uIHJlbWFpbnMgZXhlcmNpc2VkLgogICAgIiIiCiAgICBpZiByZXF1ZXN0Lm1vZHVsZS5fX25hbWVfXy5zcGxpdCgiLiIpWy0xXSAhPSBfUFIxMjVfUlVOTkVSX1RFU1RfTU9EVUxFOgogICAgICAgIHJldHVybgogICAgaWYgcmVxdWVzdC5ub2RlLm5hbWUgaW4gX1BSMTI1X1JFQUxfVVBTVFJFQU1fVEVTVFM6CiAgICAgICAgcmV0dXJuCgogICAgaW1wb3J0IGRvbWFpbi5wcjY5X3ByaW1hcnlfdGltZV9iYXNpc19ldmlkZW5jZV9hY3F1aXNpdGlvbl9ydW5uZXIgYXMgY29udHJhY3QKCiAgICB2ZXJpZmllZCA9IHJlcXVlc3QuZ2V0Zml4dHVyZXZhbHVlKCJfcHIxMjVfdmVyaWZpZWRfdXBzdHJlYW1fcHJvdG9jb2wiKQogICAgbW9ua2V5cGF0Y2guc2V0YXR0cihjb250cmFjdCwgIl92ZXJpZnlfdXBzdHJlYW0iLCBsYW1iZGE6IHZlcmlmaWVkKQo=")
PREDECESSORS = {
 "artifacts/architecture/core_01d_authority_reachability_review_a_v1.json": "9db3362af83eda04b6f005328b5d44f253fcd15ef5f39a62983cc6c3ff402521",
 "tests/fixtures/core_01d/authority-reachability-pass-a-source-inventory-v1.json": "f3cdbec57c380f7a77ce97e4bfab627241cc8b73d0817ec2abfa2f27cf2e209f",
 "artifacts/architecture/core_01d_checkpoint_e_completion_v2.json": "f9f49f22810bd789ed5774fba1dc2b239ca0de84606a0dd7cf0c5d4de9d9026e",
 "artifacts/architecture/core_01d_checkpoint_e_completion_v1.json": "aa65bef7841b7dd8a45ffddc65c25c06c14319d1711bc52ef62fcc50059b1731",
 "artifacts/architecture/checkpoint_e_workflow_capability_matrix_v2.json": "3c3cfec8b37e55161b24185941e72c3e096a00f38456a2c07a9072b62e31e5b7",
 "artifacts/architecture/core_01d_retained_workflow_status_v5.json": "c90d71a04f54c29ed094b262f0aef6cad9067316c6d548227f1c4c289a4abebf",
 "artifacts/architecture/p4_workflow_evolution_ledger_v1.json": "73e1eb3fe6593558c821600dd0f103353d45c15a139ab470a996c7cbb35da531",
 "artifacts/architecture/p4_3_workflow_retirement_ledger_v1.json": "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a",
}
ZERO_ACTIONS = dict.fromkeys(("provider", "sportsbook", "workflow_dispatch", "workflow_rerun", "workflow_cancel",
 "release_mutation", "smtp", "drive", "share_code", "login", "cookies", "wallet", "stake", "wager", "workflow_retirement", "workflow_deletion"), 0)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()


def seal(value):
    value = dict(value)
    value.pop("canonical_sha256", None)
    value["canonical_sha256"] = hashlib.sha256(canonical(value)).hexdigest()
    return value


def require(condition, reason):
    if not condition:
        raise AssertionError(reason)


def read(path):
    def pairs(items):
        value = {}
        for key, child in items:
            require(key not in value, "duplicate JSON key")
            value[key] = child
        return value
    raw = (ROOT / path).read_bytes()
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: require(False, "nonfinite JSON"))
    require(value == seal(value), "artifact self-hash mismatch: " + path)
    return value


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def source(path):
    raw = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
    return {"path": path, "lf_source_sha256": hashlib.sha256(raw).hexdigest()}


def obligations(path):
    raw = (ROOT / path).read_bytes()
    return classified_obligations(path, raw)


@lru_cache(maxsize=16384)
def classified_obligations(path, raw):
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
        text = raw.decode(encoding)
        tree = ast.parse(text)
    except (SyntaxError, UnicodeError) as error:
        return [{"path": path, "kind": "PYTHON_PARSER_REJECTS_EXACT_SOURCE_BYTES",
                 "classification": "UNREACHABLE_AS_EXECUTABLE_PYTHON_SOURCE_PARSER_FAIL_CLOSED",
                 "proof_rule": "EXACT_SOURCE_CANNOT_BE_COMPILED_OR_IMPORTED_AS_PYTHON",
                 "exception_type": type(error).__name__, "line": 0}]
    roots = {"socket", "subprocess", "asyncio", "multiprocessing", "ctypes", "os", "importlib",
             "urllib", "http", "requests", "httpx", "aiohttp", "smtplib", "ftplib",
             "websocket", "websockets", "paramiko", "curl_cffi"}
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split(".")[0]] = item.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for item in node.names:
                aliases[item.asname or item.name] = node.module + "." + item.name
    def resolve(name):
        for _ in range(8):
            matches = [key for key in aliases if name == key or name.startswith(key + ".")]
            if not matches: break
            key = max(matches, key=len)
            updated = aliases[key] + name[len(key):]
            if updated == name: break
            name = updated
        return name
    # Preserve the imported transport owner through common Session/socket/CDLL
    # factories and saved Popen/connect aliases; no factory is executed here.
    for _ in range(3):
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)): continue
            value = node.value
            if value is None: continue
            expression = value.func if isinstance(value, ast.Call) else value
            owned = resolve(ast.unparse(expression))
            if owned.split(".")[0] not in roots: continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, (ast.Name, ast.Attribute)):
                    aliases.setdefault(ast.unparse(target), owned)
    rows = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = ast.unparse(node.func)
        owned = resolve(name)
        tail = owned.rsplit(".", 1)[-1]
        if owned.split(".")[0] in roots or tail in {"connect", "connect_ex", "sendto", "sendmsg"}:
            root = owned.split(".")[0]
            if root == "os" and not tail.startswith(("exec", "spawn")) and tail not in {"system", "popen", "fork", "forkpty"}:
                category = "LOCAL_ONLY_FILESYSTEM_OR_HOST_INTROSPECTION"
                proof = "OS_NON_TRANSPORT_OPERATION_WITH_KERNEL_BACKSTOP"
            elif root == "subprocess" or tail.startswith(("create_subprocess", "exec", "spawn")) or tail in {"system", "popen", "fork", "forkpty"}:
                category = "GUARDED_NON_PYTHON_SUBPROCESS_POLICY"
                proof = "STRUCTURED_POPEN_AUDIT_OR_ALTERNATE_OS_SPAWN_DENIAL_PLUS_INHERITED_KERNEL_FILTER"
            elif root in {"ctypes", "importlib", "multiprocessing", "asyncio"}:
                category = "GUARDED_BY_NATIVE_KERNEL_TRANSPORT_DENIAL"
                proof = "NATIVE_TRANSPORT_SYSCALL_DENIAL_AND_FORK_CLONE_EXEC_FILTER_INHERITANCE"
            else:
                category = "GUARDED_BY_IN_PROCESS_TRANSPORT_DENIAL"
                proof = "SOCKET_AUDIT_DENIAL_WITH_NATIVE_KERNEL_BACKSTOP_INCLUDING_DNS_AND_UNIX_DAEMON_TRANSPORT"
            rows.append({"path": path, "line": node.lineno, "callee": owned,
                         "ast_sha256": hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest(),
                         "classification": category, "proof_rule": proof,
                         "source_expression": ast.unparse(node),
                         "caller_reachability": "CONSERVATIVELY_INCLUDED_ALL_REPOSITORY_PYTHON_NOT_ASSUMED_UNREACHABLE"})
    return sorted(rows, key=lambda row: (row["line"], row.get("callee", ""), row.get("ast_sha256", "")))


def build_inventory():
    paths = set(git("ls-files", "--cached", "--others", "--exclude-standard", "--", "*.py").decode().splitlines())
    paths.update(path.relative_to(ROOT).as_posix() for path in (ROOT / "tests").rglob("*.py"))
    # Target YAML creates Python 3.12 and installs requirements, never activates
    # the archived Python 3.10 .venv. Dependency native transport is still
    # constrained by the irreversible process/kernel boundary, not trusted.
    paths = {path for path in paths if not path.startswith(".venv/")}
    paths.add("requirements.txt")
    paths.update(path for path in A2_PATHS if path.endswith(".py") and (ROOT / path).exists())
    paths.update(path for path, _ in TARGETS)
    paths = sorted(paths)
    return seal({"schema_version": 1, "policy_id": "ATHENA_CORE_01D_CI_OFFLINE_TRANSPORT_SOURCE_INVENTORY_V1",
        "base_main_sha": BASE_MAIN, "base_tree_sha": BASE_TREE,
        "source_identities": [source(path) for path in paths],
        "transport_and_process_discovery_obligations": [row for path in paths if path.endswith(".py") for row in obligations(path)],
        "discovery_is_not_execution_proof": True,
        "proof_owner": "LINUX_X86_64_KERNEL_TRANSPORT_FILTER_AND_INHERITED_CHILD_POLICY",
        "classification_semantics": "CLASSIFIED_BY_ENFORCED_TRANSPORT_BOUNDARY_NOT_ASSERTED_FAKE_OR_UNREACHABLE_FROM_LEXICAL_HIT",
        "archived_environment": {"path": ".venv", "source_binding": "TARGET_YAML_SETUP_PYTHON_3_12_AND_REQUIREMENTS_NO_VENV_ACTIVATION",
            "dependency_transport_policy": "ALL_IMPORTED_DEPENDENCIES_INHERIT_KERNEL_DENIAL_NO_NATIVE_LIBRARY_EXEMPTION"},
        "historical_test_blob_projection": HISTORICAL_TEST_BLOBS,
        "no_out_of_scope_authority_rows_reviewed": True})


def authenticate_predecessors():
    values = {path: read(path) for path in PREDECESSORS}
    for path, expected in PREDECESSORS.items():
        require(values[path]["canonical_sha256"] == expected, "immutable predecessor identity drift: " + path)
    require(git("rev-parse", "HEAD:.github/workflows").decode().strip() == WORKFLOW_TREE, "workflow tree drift")
    require(not git("diff", "--name-only", "HEAD", "--", ".github/workflows").strip(), "dirty workflow source")
    return values


def authenticate_inventory():
    value = read(INVENTORY_PATH)
    require(value == build_inventory(), "source or process discovery drift requires reviewed A2 inventory")
    return value


def authenticate_activation_and_no_bypass():
    startup = ast.parse((ROOT / "sitecustomize.py").read_text())
    pins = next(ast.literal_eval(node.value) for node in startup.body
                if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                and target.id == "ROOT_TEST_SOURCE_PINS" for target in node.targets))
    protected = set(GUARD_PATHS) - {"sitecustomize.py"}
    protected.add("scripts/audit_core_01d_ci_offline_transport_boundary.py")
    require(pins == {path: source(path)["lf_source_sha256"] for path in sorted(protected)},
            "root bootstrap does not bind exact patchable guard/auditor source")
    workflow = yaml.safe_load((ROOT / ".github/workflows/athena-patch-bridge.yml").read_text())
    step = next(step for step in workflow["jobs"]["validate"]["steps"]
                if step.get("name") == "Enforce path and patch safety")
    policy = ast.parse(step["run"].split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0])
    allowed = {target.id: ast.literal_eval(node.value) for node in policy.body
               if isinstance(node, ast.Assign) for target in node.targets
               if isinstance(target, ast.Name) and target.id in {"allowed_prefixes", "allowed_exact"}}
    require("sitecustomize.py" not in allowed["allowed_exact"]
            and not "sitecustomize.py".startswith(allowed["allowed_prefixes"]),
            "Patch Bridge can replace the trusted root bootstrap")
    guard = ast.parse((ROOT / "tests/offline_transport.py").read_text())
    functions = {node.name: node for node in guard.body if isinstance(node, ast.FunctionDef)}
    install = functions["install"]
    calls = [ast.unparse(node.func) for node in ast.walk(install) if isinstance(node, ast.Call)]
    require("install_kernel" in calls and "sys.addaudithook" in calls, "parent/native activation missing")
    for node in ast.walk(guard):
        if not isinstance(node, ast.Call): continue
        callee = ast.unparse(node.func)
        require(callee not in {"os.getenv", "os.putenv", "eval", "exec"}, "unreviewed dynamic/environment bypass")
        if callee in {"os.environ.get", "env.get", "inherited.get"}:
            require(node.args and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == "PYTHONPATH", "generic environment policy gate")
    kernel = ast.parse((ROOT / "tests/offline_linux.py").read_text())
    require(not any(isinstance(node, ast.Call) and ast.unparse(node.func) in {"os.getenv", "eval", "exec"}
                    for node in ast.walk(kernel)), "kernel policy has a dynamic bypass")
    calls = [node for node in ast.walk(kernel) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "prctl"]
    require(any([ast.literal_eval(arg) for arg in node.args[:2]] == [38, 1] for node in calls), "no-new-privileges proof missing")
    require(any([ast.literal_eval(arg) for arg in node.args[:2]] == [22, 2] for node in calls), "kernel filter installation missing")
    return True


def build_receipt():
    predecessors = authenticate_predecessors()
    inventory = authenticate_inventory()
    authenticate_activation_and_no_bypass()
    # Unknown syntax is not converted into a safe caller classification.
    require(not any(row.get("discovery_status") == "REQUIRES_EXACT_CALLER_CLASSIFICATION"
                    or row.get("kind") == "PARSE_ERROR_REQUIRES_SOURCE_CLASSIFICATION"
                    for row in inventory["transport_and_process_discovery_obligations"]),
            "A2 remains PARTIAL: exact caller classification is not yet complete")
    import sys
    sys.path.insert(0, str(ROOT / "tests"))
    import offline_linux as kernel
    require(all(kernel.evaluate(number) == kernel.DENY for number in kernel.DENIED_SYSCALLS), "kernel syscall deny-list drift")
    require(all(kernel.evaluate(number, family=2) == kernel.DENY and kernel.evaluate(number, family=10) == kernel.DENY for number in kernel.SOCKET_CALLS), "native INET socket bypass")
    require(kernel.evaluate(41, arch=0) == kernel.DENY and kernel.evaluate(41 | kernel.X32_SYSCALL_BIT) == kernel.DENY, "alternate ABI bypass")
    require(kernel.evaluate(kernel.REVIEWED_ABI_CEILING + 1) == kernel.DENY, "unreviewed syscall ABI extension bypass")
    require(kernel.evaluate(44, destination=1) == kernel.DENY
            and kernel.evaluate(44, destination=1 << 32) == kernel.DENY
            and kernel.evaluate(44, destination=0) == kernel.ALLOW,
            "anonymous UNIX self-pipe versus address-bearing sendto boundary drift")
    for path in GUARD_PATHS:
        require(path in {row["path"] for row in inventory["source_identities"]}, "missing guard source identity")
    for path in {path for path, _ in TARGETS}:
        text = (ROOT / path).read_text()
        require("ubuntu-latest" in text and "python -m pytest" in text and "PYTHONPATH:" in text, "target execution/bootstrap contract drift")
    startup = (ROOT / "sitecustomize.py").read_text()
    require('"-m", "pytest"' in startup and 'raise SystemExit' in startup, "startup fail-closed activation drift")
    require("install()" in (ROOT / "tests/conftest.py").read_text(), "pytest activation drift")
    parent = next(value for path, value in predecessors.items() if path.endswith("checkpoint_e_completion_v2.json"))
    rows = parent["unresolved_pass_a_rows"]
    require({(row["workflow_path"], row["trigger_kind"]) for row in rows} == set(TARGETS), "exact three predecessor partials required")
    return seal({"schema_version": 1, "policy_id": POLICY_ID, "repository": "Thabearr/ATHENA", "master_issue": 337,
        "base_main_sha": BASE_MAIN, "base_tree_sha": BASE_TREE,
        "post_merge_ci_gate": {"run_id": 37066892743, "event": "push", "head_sha": BASE_MAIN, "conclusion": "success", "syntax_shards_1_to_8_aggregate": "SUCCESS"},
        "predecessor_identities": PREDECESSORS,
        "inventory": {"path": INVENTORY_PATH, "canonical_sha256": inventory["canonical_sha256"]},
        "guard_sources": [source(path) for path in GUARD_PATHS],
        "proof_gates": {"source_audit": "SOURCE_BOUND_CANDIDATE_COMPLETE",
            "local_windows": "SUPPLEMENTARY_PYTHON_AND_PURE_BPF_TESTS_NOT_LINUX_PROOF",
            "linux_hosted": "REQUIRED_EXTERNAL_EXACT_HEAD_GATE_BEFORE_REVIEW_READY_CLAIM",
            "authoritative_hosted_binding": "FINAL_ISSUE_337_COMMENT_NO_CIRCULAR_RUN_ID_IN_RECEIPT"},
        "target_rows": [{"workflow_path": path, "trigger_kind": trigger, "resolved": True,
            "review_state": "SOURCE_BOUND_GLOBAL_TEST_TRANSPORT_BOUNDARY_REVIEW_COMPLETE"} for path, trigger in TARGETS],
        "target_count": 3, "resolved_target_count": 3, "unresolved_target_count": 0,
        "ci_boundary": {"platform": "LINUX_X86_64_ONLY_TARGET_UBUNTU_WORKFLOWS", "kernel_filter": "SECCOMP_ERRNO_EPERM_WITH_NO_NEW_PRIVS",
            "native_and_child_process_inheritance": "FORK_CLONE_EXEC_FILTER_INHERITANCE",
            "unsupported_kernel_or_abi": "FAIL_BEFORE_PYTEST_PLUGIN_OR_TEST_EXECUTION",
            "network_socket_families": "ALL_DENIED_EXCEPT_AF_UNIX_ANONYMOUS_LOCAL_IPC",
            "loopback": "INET_LOOPBACK_DENIED_ON_TARGET_CI",
            "unix_daemon_connect_and_descriptor_transfer": "DENIED_CONNECT_SENDMSG_RECVMSG",
            "anonymous_unix_self_pipe_send": "NULL_DESTINATION_ONLY_BOTH_64_BIT_POINTER_HALVES_CHECKED",
            "alternate_syscall_abis_io_uring_ptrace_pidfd": "DENIED",
            "unknown_syscall_numbers": "DENIED_ABOVE_REVIEWED_X86_64_ABI_CEILING_450",
            "python_child_environment": "TRUSTED_BOOTSTRAP_FORCED_AT_PROCESS_BOUNDARY",
            "patch_bridge_guard_integrity": "ROOT_BOOTSTRAP_OUTSIDE_PATCH_ALLOWLIST_PINS_PATCHABLE_GUARD_AND_AUDITOR_SOURCE_BEFORE_IMPORT",
            "external_commands": "DEFAULT_DENY_STRUCTURED_ARGV_ONLY_LOCAL_GIT_BOUND_PYTHON_OR_EXACT_UNAME_P_HOST_QUERY",
            "native_git_helpers": "HOOKS_SIGNING_FSMONITOR_DISABLED_NATIVE_FILTERS_AND_DIFF_DRIVERS_DENIED",
            "generic_network_opt_out": False, "outside_pytest_production_activation": False,
            "windows_proof": "SUPPLEMENTARY_PYTHON_GUARD_ONLY_NOT_THE_CI_GLOBAL_KERNEL_PROOF"},
        "workflow_tree_before_sha1": WORKFLOW_TREE, "workflow_tree_after_sha1": WORKFLOW_TREE,
        "transition_count_before": 14, "transition_count_after": 14, "workflow_count": 39, "trigger_surface_count": 57, "retired_workflow_count": 3,
        "checkpoint_e_status": "INCOMPLETE", "p4_4_status": "INCOMPLETE", "global_unknown_before": 35, "global_unknown_after": 32,
        "out_of_scope_rows_reclassified": 0, "retention_blockers_A_B_C_D": "CLOSED_WITH_HISTORICAL_LIMITATIONS_PRESERVED",
        "live_missing_artifact_relation_count": 0, "historical_missing_artifact_relation_count": 14,
        "actions": ZERO_ACTIONS, "new_execution_authority_granted": False,
        "source_review_counter_while_open": "3/5", "source_review_counter_if_owner_merges": "4/5", "mandatory_source_reread_due": False,
        "terminal": "CORE_01D_CI_OFFLINE_TRANSPORT_BOUNDARY_REVIEW_READY_3_PARTIALS_RESOLVED_DO_NOT_MERGE"})


def audit():
    value = read(RECEIPT_PATH)
    require(value == build_receipt(), "A2 receipt differs from current independently authenticated boundary")
    return {"result": "PASS", "receipt_sha256": value["canonical_sha256"], "resolved_target_count": value["resolved_target_count"],
            "current_platform_kernel_executed": bool(__import__("offline_linux")._active), "authority_granted": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--emit-inventory", action="store_true")
    parser.add_argument("--emit-receipt", action="store_true")
    args = parser.parse_args()
    value = build_inventory() if args.emit_inventory else build_receipt() if args.emit_receipt else audit()
    print(canonical(value).decode(), end="")


if __name__ == "__main__":
    main()
