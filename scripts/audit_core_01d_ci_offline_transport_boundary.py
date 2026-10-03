"""Source-safe A2 transport proof with an append-only inventory generation chain.

Two independent proof paths are authenticated on every run:

1. HISTORICAL: the immutable A2 V1 inventory, the immutable A2 receipt and the
   guard/activation sources are rederived from exact Git bytes at the A2
   reviewed head, never from current worktree bytes. Hosted CI checks out with
   fetch-depth 1, where no ancestor object exists and no fetch is permitted, so
   the same evidence is also cross-checked through a byte-pinned identity chain
   (pinned V1 inventory + pinned A2 receipt + pinned row counts/shapes); the
   exact Git rederivation runs whenever the reviewed-head objects are present.
2. CURRENT: the latest reviewed inventory generation must equal the current
   repository Python corpus, so unreviewed source still fails before collection.
   This path needs no ancestor object, so any source drift still fails before
   test collection on every runner.
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
from functools import lru_cache
import io
from pathlib import Path
import re
import subprocess
import tokenize
import yaml

ROOT = Path(__file__).resolve().parents[1]
BASE_MAIN = "86ffc41205d83f5e4b37d20d35d73f9f97f3b23f"
BASE_TREE = "1fd395339f09fa3726b1c633399c3ee79d7dfb4e"
WORKFLOW_TREE = "9b08653f1a12bb1b3d964fbd910396ff955740da"
POLICY_ID = "ATHENA_CORE_01D_CI_OFFLINE_TRANSPORT_BOUNDARY_V1"
# Historical A2 evidence is proven against exact A2 reviewed-head Git bytes.
# Current boundary activation is proven against the current worktree.
A2_REVIEWED_HEAD = "a03c5bbf0c045233c9b08112e28927d3bde4f3e2"
BRIDGE_BASE_MAIN = "7328ecaaae62649e09c996d277683e81a9e7fc84"
BRIDGE_BASE_TREE = "39c29ee425a0b3d6ac5d15e697c8aa920daa8718"
INVENTORY_DIRECTORY = "tests/fixtures/core_01d"
INVENTORY_PREFIX = "ci-offline-transport-boundary-source-inventory-"
INVENTORY_NAME = re.compile(re.escape(INVENTORY_PREFIX) + r"v([0-9]+)\.json\Z")
INVENTORY_POLICY_PREFIX = "ATHENA_CORE_01D_CI_OFFLINE_TRANSPORT_SOURCE_INVENTORY"
INVENTORY_PATH = INVENTORY_DIRECTORY + "/" + INVENTORY_PREFIX + "v1.json"
INVENTORY_V1_SHA256 = "ca8c07c071538298ffb293027e7a0be1c5766e8a943b3d2b605627f9ffe922dd"
# Pinned row counts of the immutable generation-1 inventory: the shape a
# depth-1 checkout can still assert when no reviewed-head object exists.
V1_SOURCE_IDENTITY_COUNT = 1150
V1_OBLIGATION_COUNT = 1693
INVENTORY_V2_PATH = INVENTORY_DIRECTORY + "/" + INVENTORY_PREFIX + "v2.json"
# Frozen repository location: a successor's predecessor binding always names the
# canonical committed path, whichever isolated directory the chain is checked in.
INVENTORY_CANONICAL_DIRECTORY = INVENTORY_DIRECTORY
RECEIPT_PATH = "artifacts/architecture/core_01d_ci_offline_transport_boundary_v1.json"
RECEIPT_SHA256 = "5d0385f77463d3e7a9f804b431df7e2c2c9c4908c266326bf35b05a50086f8e2"
COMPLETION_PATH = "artifacts/architecture/core_01d_checkpoint_e_completion_v3.json"
COMPLETION_V3_SHA256 = "27516b35fb5e836ac2d851fa60e4300ebf347e00b00f3858b46671cd77af9d79"
BRIDGE_RECEIPT_PATH = "artifacts/architecture/core_01d_a2_inventory_evolution_bridge_v1.json"
EVOLUTION_TEST_PATH = "tests/test_core_01d_ci_offline_transport_inventory_evolution.py"
TARGETS = ((".github/workflows/athena-patch-bridge.yml", "issue_comment"),
           (".github/workflows/tests.yml", "pull_request"), (".github/workflows/tests.yml", "push"))
GUARD_PATHS = ("sitecustomize.py", "tests/conftest.py", "tests/offline_transport.py",
               "tests/offline_linux.py", "tests/_offline_bootstrap/sitecustomize.py")
A2_PATHS = frozenset((*GUARD_PATHS, INVENTORY_PATH, INVENTORY_V2_PATH, RECEIPT_PATH, COMPLETION_PATH,
    BRIDGE_RECEIPT_PATH, EVOLUTION_TEST_PATH,
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
    "tests/test_win_either_half_campaign_commitment.py"))
# These are authenticated predecessor tree entries, not current source pins.
HISTORICAL_TEST_BLOBS = {
    "tests/test_win_either_half_campaign_commitment.py": "783704cffa6ae95be80a432422b7b341bfb64949",
    "tests/conftest.py": "6d4d2ddb621a27f788d0c25499e418092f260ef1",
    "tests/native/test_port_02c_qualifier_safety.py": "2fe50e18837c36c5e97adac2e89a9da72f6847ec",
    "tests/test_accumulator_optimizer_trust_boundaries.py": "b4f22663fc5a72c341920de61d0ec7877298a5da",
    "tests/test_market_router_trust_boundaries.py": "e4a6ab718d5905bbe10d9ae57c0a94b3f98ce287",
}
HISTORICAL_CONFTEST_BYTES = base64.b64decode("ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKaW1wb3J0IHB5dGVzdAoKCl9QUjEyNV9SVU5ORVJfVEVTVF9NT0RVTEUgPSAidGVzdF9wcjY5X3ByaW1hcnlfdGltZV9iYXNpc19ldmlkZW5jZV9hY3F1aXNpdGlvbl9ydW5uZXIiCl9QUjEyNV9SRUFMX1VQU1RSRUFNX1RFU1RTID0gewogICAgInRlc3RfdXBzdHJlYW1fcHJvdG9jb2xfbXV0YXRpb25fZmFpbHNfY2xvc2VkIiwKfQoKCkBweXRlc3QuZml4dHVyZShzY29wZT0ic2Vzc2lvbiIpCmRlZiBfcHIxMjVfdmVyaWZpZWRfdXBzdHJlYW1fcHJvdG9jb2woKToKICAgICIiIlBlcmZvcm0gdGhlIGV4cGVuc2l2ZSBQUjEyNeKGklBSMTI0IGFuY2VzdHJ5IHZhbGlkYXRpb24gb25jZSBwZXIgdGVzdCBzZXNzaW9uLiIiIgogICAgaW1wb3J0IGRvbWFpbi5wcjY5X3ByaW1hcnlfdGltZV9iYXNpc19ldmlkZW5jZV9hY3F1aXNpdGlvbl9ydW5uZXIgYXMgY29udHJhY3QKCiAgICByZXR1cm4gY29udHJhY3QuX3ZlcmlmeV91cHN0cmVhbSgpCgoKQHB5dGVzdC5maXh0dXJlKGF1dG91c2U9VHJ1ZSkKZGVmIF9yZXVzZV9wcjEyNV92ZXJpZmllZF91cHN0cmVhbV9wcm90b2NvbChyZXF1ZXN0LCBtb25rZXlwYXRjaCk6CiAgICAiIiJSZXVzZSB2ZXJpZmllZCBpbW11dGFibGUgYW5jZXN0cnkgZm9yIFBSMTI1IHN0YXRlLW1hY2hpbmUgdGVzdHMgb25seS4KCiAgICBQcm9kdWN0aW9uIGNvZGUgaXMgdW5jaGFuZ2VkLiBUaGUgZGVkaWNhdGVkIHVwc3RyZWFtLW11dGF0aW9uIHRlc3QgZGVsaWJlcmF0ZWx5CiAgICByZXRhaW5zIHRoZSBvcmlnaW5hbCB2ZXJpZmllciBzbyBmYWlsLWNsb3NlZCB0YW1wZXIgZGV0ZWN0aW9uIHJlbWFpbnMgZXhlcmNpc2VkLgogICAgIiIiCiAgICBpZiByZXF1ZXN0Lm1vZHVsZS5fX25hbWVfXy5zcGxpdCgiLiIpWy0xXSAhPSBfUFIxMjVfUlVOTkVSX1RFU1RfTU9EVUxFOgogICAgICAgIHJldHVybgogICAgaWYgcmVxdWVzdC5ub2RlLm5hbWUgaW4gX1BSMTI1X1JFQUxfVVBTVFJFQU1fVEVTVFM6CiAgICAgICAgcmV0dXJuCgogICAgaW1wb3J0IGRvbWFpbi5wcjY5X3ByaW1hcnlfdGltZV9iYXNpc19ldmlkZW5jZV9hY3F1aXNpdGlvbl9ydW5uZXIgYXMgY29udHJhY3QKCiAgICB2ZXJpZmllZCA9IHJlcXVlc3QuZ2V0Zml4dHVyZXZhbHVlKCJfcHIxMjVfdmVyaWZpZWRfdXBzdHJlYW1fcHJvdG9jb2wiKQogICAgbW9ua2V5cGF0Y2guc2V0YXR0cihjb250cmFjdCwgIl92ZXJpZnlfdXBzdHJlYW0iLCBsYW1iZGE6IHZlcmlmaWVkKQo=")
# Exact A2 reviewed-head sitecustomize bytes (the only guard source this bridge
# changes). Hosted CI checks out depth 1, so the reviewed-head object is absent
# there and no fetch is permitted: these bytes are the fallback text for the
# historical activation proof and are themselves pinned by the immutable V1
# inventory identity for the same path, so a substituted blob fails closed.
HISTORICAL_TEXT_BYTES = {
    "sitecustomize.py": base64.b64decode("IiIiQWN0aXZhdGUgdGhlIHRlc3QgYm91bmRhcnkgYmVmb3JlIHB5dGVzdCBwbHVnaW4gZGlzY292ZXJ5OyBvdGhlciBDTEkgaXMgaW5lcnQuIiIiCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aAppbXBvcnQgc3lzCgojIFBhdGNoIEJyaWRnZSBmb3JiaWRzIHRoaXMgcm9vdCBwYXRoLiBJdHMgYWxsb3dlZCB0ZXN0cy9zY3JpcHRzIHBhdGNoZXMgbXVzdAojIG5vdCByZXBsYWNlIHRoZSB0cnVzdGVkIGJvdW5kYXJ5IG9yIGF1ZGl0b3IgYmVmb3JlIHB5dGVzdCBzdGFydHMuIFRoZXNlIGFyZQojIExGIHNvdXJjZSBpZGVudGl0aWVzLCBub3Qgbm9ybWFsaXphdGlvbiBvZiBhbnkgcmF3IHJ1bnRpbWUgYXJ0aWZhY3QuClJPT1RfVEVTVF9TT1VSQ0VfUElOUyA9IHsKICAgICJzY3JpcHRzL2F1ZGl0X2NvcmVfMDFkX2NpX29mZmxpbmVfdHJhbnNwb3J0X2JvdW5kYXJ5LnB5IjogImM4MzBjODk3OTUxODA3N2ViYTBhNzc2ZjRkZjk2NTM5YjZkNTE1ZjNlNjIyZTE1MzVkZWMyYWY4YjUzNmRkYjAiLAogICAgInRlc3RzL19vZmZsaW5lX2Jvb3RzdHJhcC9zaXRlY3VzdG9taXplLnB5IjogIjFiMTk2ODIxNWI3MmY5MTNlMTdhODQwYjdiM2FjMjJhYTRlODUwOGU1ZmE1Mjk5OTA0ODdjNTliMmUwYzg3OGQiLAogICAgInRlc3RzL2NvbmZ0ZXN0LnB5IjogIjUwMGU0N2Q5OTM3ZGRmODlmNzI1ZDQxMTE3YTg0YWJmMjA3ZGUyZTc2OGE4NjFhZGM1YzRhNDljN2E4N2UwNTIiLAogICAgInRlc3RzL29mZmxpbmVfbGludXgucHkiOiAiNTY1ZTE2OThiZWJmYzMwZDU0NjNhM2MzYjZkZWQ0M2U2ZmY5Mzc4YWY5NTUxMjlhMDExYmYyOGUxYTViOTk5ZiIsCiAgICAidGVzdHMvb2ZmbGluZV90cmFuc3BvcnQucHkiOiAiYTM1ZGNjYTUyOTI5NTk4YTVmNmQ5N2E2OTI3NGU0NzVmMTBjMjIyOTg4OTU5OWE4MmQ1MzcxODg2YzQzN2FkMSIsCn0KCl9hcmdzID0gZ2V0YXR0cihzeXMsICJvcmlnX2FyZ3YiLCAoKSkKX3B5dGVzdF9tb2R1bGUgPSBhbnkoCiAgICBfYXJnc1tpOmkgKyAyXSA9PSBbIi1tIiwgInB5dGVzdCJdCiAgICBhbmQgYWxsKGZsYWcgaW4geyItdSIsICItQiIsICItcyIsICItcSIsICItdiIsICItdnYiLCAiLWIiLCAiLWJiIiwgIi1PIiwgIi1PTyJ9IGZvciBmbGFnIGluIF9hcmdzWzE6aV0pCiAgICBmb3IgaSBpbiByYW5nZSgxLCBsZW4oX2FyZ3MpIC0gMSkKKQpfcHl0ZXN0X3NjcmlwdCA9IGFueShQYXRoKGFyZykubmFtZS5sb3dlcigpIGluIHsicHl0ZXN0IiwgInB5dGVzdC5leGUiLCAicHkudGVzdCJ9IGZvciBhcmcgaW4gX2FyZ3NbMToyXSkKaWYgX3B5dGVzdF9tb2R1bGUgb3IgX3B5dGVzdF9zY3JpcHQ6CiAgICB0cnk6CiAgICAgICAgaW1wb3J0IGhhc2hsaWIKCiAgICAgICAgX3Jvb3QgPSBQYXRoKF9fZmlsZV9fKS5yZXNvbHZlKCkucGFyZW50CiAgICAgICAgZm9yIF9wYXRoLCBfZXhwZWN0ZWQgaW4gUk9PVF9URVNUX1NPVVJDRV9QSU5TLml0ZW1zKCk6CiAgICAgICAgICAgIF9yYXcgPSAoX3Jvb3QgLyBfcGF0aCkucmVhZF9ieXRlcygpLnJlcGxhY2UoYiJcclxuIiwgYiJcbiIpCiAgICAgICAgICAgIGlmIGhhc2hsaWIuc2hhMjU2KF9yYXcpLmhleGRpZ2VzdCgpICE9IF9leHBlY3RlZDoKICAgICAgICAgICAgICAgIHJhaXNlIFJ1bnRpbWVFcnJvcigidGVzdCBib3VuZGFyeSBzb3VyY2UgaWRlbnRpdHkgZHJpZnQ6ICIgKyBfcGF0aCkKICAgICAgICBzeXMucGF0aC5pbnNlcnQoMCwgc3RyKFBhdGgoX19maWxlX18pLnJlc29sdmUoKS5wYXJlbnQgLyAidGVzdHMiKSkKICAgICAgICBmcm9tIG9mZmxpbmVfdHJhbnNwb3J0IGltcG9ydCBpbnN0YWxsCgogICAgICAgIGluc3RhbGwoKQogICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlcnJvcjoKICAgICAgICAjIFB5dGhvbiBvdGhlcndpc2UgcHJpbnRzIGFuZCBpZ25vcmVzIGFuIGV4Y2VwdGlvbiBpbiBzaXRlY3VzdG9taXplLgogICAgICAgIHJhaXNlIFN5c3RlbUV4aXQoInB5dGVzdCBvZmZsaW5lIGJvdW5kYXJ5IGZhaWxlZCB0byBhY3RpdmF0ZSIpIGZyb20gZXJyb3IK"),
}
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
# Corpus fields are rederived from current source on every run; every other
# inventory field is inherited from the authenticated generation document.
CORPUS_FIELDS = frozenset((
    "source_identities", "transport_and_process_discovery_obligations",
    "discovery_is_not_execution_proof", "proof_owner", "classification_semantics",
    "archived_environment", "historical_test_blob_projection",
    "no_out_of_scope_authority_rows_reviewed"))


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


def git(*args, data=None):
    return subprocess.check_output(["git", *args], cwd=ROOT, input=data)


def lf(raw):
    return raw.replace(b"\r\n", b"\n")


def source(path):
    raw = lf((ROOT / path).read_bytes())
    return {"path": path, "lf_source_sha256": hashlib.sha256(raw).hexdigest()}


def obligations(path):
    # End-of-line normalization is not a classification change: CRLF and LF
    # bytes of the same source classify identically, so one reviewed parse
    # serves both the historical and the current corpus.
    return classified_obligations(path, lf((ROOT / path).read_bytes()))


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


def inventory_fields(paths, identity, obligation):
    """Conservative inventory body shared by historical and current proofs."""
    return {
        "source_identities": [identity(path) for path in paths],
        "transport_and_process_discovery_obligations": [row for path in paths if path.endswith(".py") for row in obligation(path)],
        "discovery_is_not_execution_proof": True,
        "proof_owner": "LINUX_X86_64_KERNEL_TRANSPORT_FILTER_AND_INHERITED_CHILD_POLICY",
        "classification_semantics": "CLASSIFIED_BY_ENFORCED_TRANSPORT_BOUNDARY_NOT_ASSERTED_FAKE_OR_UNREACHABLE_FROM_LEXICAL_HIT",
        "archived_environment": {"path": ".venv", "source_binding": "TARGET_YAML_SETUP_PYTHON_3_12_AND_REQUIREMENTS_NO_VENV_ACTIVATION",
            "dependency_transport_policy": "ALL_IMPORTED_DEPENDENCIES_INHERIT_KERNEL_DENIAL_NO_NATIVE_LIBRARY_EXEMPTION"},
        "historical_test_blob_projection": HISTORICAL_TEST_BLOBS,
        "no_out_of_scope_authority_rows_reviewed": True,
    }


def current_source_paths():
    paths = set(git("ls-files", "--cached", "--others", "--exclude-standard", "--", "*.py").decode().splitlines())
    paths.update(path.relative_to(ROOT).as_posix() for path in (ROOT / "tests").rglob("*.py"))
    # Target YAML creates Python 3.12 and installs requirements, never activates
    # the archived Python 3.10 .venv. Dependency native transport is still
    # constrained by the irreversible process/kernel boundary, not trusted.
    paths = {path for path in paths if not path.startswith(".venv/")}
    paths.add("requirements.txt")
    paths.update(path for path in A2_PATHS if path.endswith(".py") and (ROOT / path).exists())
    paths.update(path for path, _ in TARGETS)
    return sorted(paths)


def current_corpus_fields():
    paths = current_source_paths()
    return inventory_fields(paths, source, obligations)


@lru_cache(maxsize=8)
def historical_objects_available(commit=A2_REVIEWED_HEAD):
    """True when the exact reviewed-head objects exist in this object database.

    Hosted CI checks out with fetch-depth 1, so no ancestor commit exists there
    and this probe returns False. Historical reads then use the byte-pinned
    identity chain instead of Git history; nothing is fetched and no
    environment variable selects a proof.
    """
    try:
        git("cat-file", "-e", f"{commit}^{{commit}}")
    except subprocess.CalledProcessError:
        return False
    return True


def pinned_historical_identity(path, commit=A2_REVIEWED_HEAD):
    """Reviewed A2 source identity for `path` from the immutable V1 inventory.

    The generation-1 inventory is byte-pinned by INVENTORY_V1_SHA256 and is
    cross-checked against the byte-pinned A2 receipt (which names both that
    inventory and the same guard identities), so its rows are an equivalent,
    fail-closed source of the exact A2 identities in a depth-1 checkout.
    """
    require(commit == A2_REVIEWED_HEAD, "no pinned historical identity for commit: " + commit)
    identities = {row["path"]: row["lf_source_sha256"]
                  for row in read(INVENTORY_PATH)["source_identities"]}
    require(path in identities, "no pinned historical identity for path: " + path)
    return identities[path]


def pinned_historical_text(path, commit=A2_REVIEWED_HEAD):
    """Reviewed A2 text for `path` without reading any ancestor Git object.

    A file whose current bytes still equal its pinned A2 identity is proven
    unchanged before those bytes are used. A file this bridge changed
    (sitecustomize.py) is served from its exact pinned A2 blob instead, so the
    historical activation proof never silently reads current source.
    """
    require(commit == A2_REVIEWED_HEAD, "no pinned historical text for commit: " + commit)
    if path in HISTORICAL_TEXT_BYTES:
        raw = lf(HISTORICAL_TEXT_BYTES[path])
        require(hashlib.sha256(raw).hexdigest() == pinned_historical_identity(path),
                "pinned historical text identity mismatch: " + path)
        return raw.decode("utf-8")
    # The pin is resolved before any worktree byte is read, so an unknown path
    # fails closed as a review rejection rather than as a read error.
    identity = pinned_historical_identity(path)
    target = ROOT / path
    require(target.is_file(), "pinned historical text source is missing: " + path)
    raw = lf(target.read_bytes())
    require(hashlib.sha256(raw).hexdigest() == identity,
            "pinned historical text is not the reviewed A2 source: " + path)
    return raw.decode("utf-8")


@lru_cache(maxsize=8)
def historical_tree(commit):
    """Exact tracked path/mode/blob-id record at `commit` (never a checkout)."""
    entries = {}
    try:
        raw = git("ls-tree", "-r", "-z", commit)
    except subprocess.CalledProcessError as error:
        raise AssertionError("exact historical Git objects are unavailable for " + commit
                             + " (depth-1 checkout)") from error
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, path = record.split(b"\t", 1)
        mode, kind, identity = metadata.decode().split()
        entries[path.decode("utf-8")] = {"mode": mode, "kind": kind, "identity": identity}
    return entries


def historical_source_paths(commit=A2_REVIEWED_HEAD):
    tree = historical_tree(commit)
    paths = {path for path, entry in tree.items()
             if path.endswith(".py") and not path.startswith(".venv/") and entry["kind"] == "blob"}
    paths.add("requirements.txt")
    paths.update(path for path in A2_PATHS if path.endswith(".py") and path in tree)
    paths.update(path for path, _ in TARGETS if path in tree)
    return sorted(paths)


@lru_cache(maxsize=4)
def historical_blobs(commit=A2_REVIEWED_HEAD):
    """Exact Git blob bytes for the A2 source corpus at `commit`."""
    tree = historical_tree(commit)
    paths = historical_source_paths(commit)
    missing = [path for path in paths if tree.get(path, {}).get("kind") != "blob"]
    require(not missing, "historical source is not a tracked blob: " + ", ".join(missing[:5]))
    identifiers = [tree[path]["identity"] for path in paths]
    payload = git("cat-file", "--batch", data=("\n".join(identifiers) + "\n").encode())
    blobs, offset = [], 0
    for path, identity in zip(paths, identifiers):
        end = payload.index(b"\n", offset)
        header = payload[offset:end].split()
        offset = end + 1
        require(len(header) == 3 and header[0].decode() == identity and header[1] == b"blob",
                "historical blob batch identity mismatch: " + path)
        size = int(header[2])
        raw = payload[offset:offset + size]
        offset = offset + size + 1
        require(payload[offset - 1:offset] == b"\n", "historical blob batch framing mismatch: " + path)
        require(hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == identity,
                "historical blob payload mismatch: " + path)
        blobs.append(raw)
    require(offset == len(payload), "extra historical blob batch data")
    return dict(zip(paths, blobs))


def historical_source(path, commit=A2_REVIEWED_HEAD):
    if not historical_objects_available(commit):
        return {"path": path, "lf_source_sha256": pinned_historical_identity(path, commit)}
    raw = lf(historical_blobs(commit)[path])
    return {"path": path, "lf_source_sha256": hashlib.sha256(raw).hexdigest()}


def historical_text(path, commit=A2_REVIEWED_HEAD):
    if historical_objects_available(commit):
        return historical_blobs(commit)[path].decode("utf-8")
    return pinned_historical_text(path, commit)


def build_inventory_historical(commit=A2_REVIEWED_HEAD):
    """Generation-1 inventory rederived from exact A2 reviewed-head Git bytes."""
    blobs = historical_blobs(commit)
    paths = sorted(blobs)
    return seal({"schema_version": 1, "policy_id": INVENTORY_POLICY_PREFIX + "_V1",
        "base_main_sha": BASE_MAIN, "base_tree_sha": BASE_TREE,
        **inventory_fields(paths, lambda path: historical_source(path, commit),
                           lambda path: classified_obligations(path, lf(blobs[path])))})


def authenticate_historical_v1():
    value = read(INVENTORY_PATH)
    require(value.get("canonical_sha256") == INVENTORY_V1_SHA256, "immutable A2 V1 inventory identity drift")
    require(value.get("schema_version") == 1 and value.get("policy_id") == INVENTORY_POLICY_PREFIX + "_V1",
            "immutable A2 V1 policy/schema drift")
    require("generation" not in value and "predecessor_inventory" not in value,
            "immutable A2 V1 must not claim a successor generation")
    authenticate_pinned_v1_identity_chain(value)
    if historical_objects_available():
        require(value == build_inventory_historical(),
                "immutable A2 V1 inventory differs from exact A2 reviewed-head Git source")
    return value


def authenticate_pinned_v1_identity_chain(value):
    """Cross-artifact proof of the immutable A2 evidence needing no Git history.

    Hosted CI checks out depth 1: no reviewed-head object exists there and no
    fetch is permitted. The byte-pinned generation-1 inventory, the byte-pinned
    A2 receipt that names it, and the pinned row counts/shapes must therefore
    agree with each other, so neither immutable artifact can drift alone. The
    exact reviewed-head rederivation runs on top of this whenever the objects
    are present.
    """
    require(value.get("base_main_sha") == BASE_MAIN and value.get("base_tree_sha") == BASE_TREE,
            "immutable A2 V1 base binding drift")
    identities = value.get("source_identities")
    require(isinstance(identities, list) and len(identities) == V1_SOURCE_IDENTITY_COUNT,
            "immutable A2 V1 source identity count drift")
    require(all(isinstance(row, dict) and isinstance(row.get("path"), str) and row["path"]
                and re.fullmatch(r"[0-9a-f]{64}", row.get("lf_source_sha256") or "")
                for row in identities), "immutable A2 V1 source identity shape drift")
    require(len({row["path"] for row in identities}) == len(identities),
            "immutable A2 V1 duplicate source identity")
    require(identities == sorted(identities, key=lambda row: row["path"]),
            "immutable A2 V1 source identity order drift")
    rows = value.get("transport_and_process_discovery_obligations")
    require(isinstance(rows, list) and len(rows) == V1_OBLIGATION_COUNT,
            "immutable A2 V1 obligation count drift")
    require(all(isinstance(row, dict) and isinstance(row.get("path"), str) and row["path"]
                and isinstance(row.get("line"), int) and isinstance(row.get("classification"), str)
                and row["classification"] for row in rows),
            "immutable A2 V1 obligation shape drift")
    receipt = read(RECEIPT_PATH)
    require(receipt.get("canonical_sha256") == RECEIPT_SHA256, "immutable A2 receipt identity drift")
    require(receipt.get("inventory") == {"path": INVENTORY_PATH,
                                         "canonical_sha256": INVENTORY_V1_SHA256},
            "immutable A2 receipt does not bind the immutable A2 V1 inventory")
    require(receipt.get("guard_sources") == [historical_source(path) for path in GUARD_PATHS],
            "immutable A2 receipt guard sources disagree with the immutable A2 V1 inventory")
    return True


def inventory_generation_path(generation):
    """Canonical committed path of a reviewed inventory generation."""
    require(type(generation) is int and generation >= 1,
            "invalid inventory generation: " + repr(generation))
    return (INVENTORY_CANONICAL_DIRECTORY + "/" + INVENTORY_PREFIX
            + "v" + str(generation) + ".json")


def read_generation(path):
    """A sealed generation must be exactly its own canonical serialization.

    Trailing bytes, reordering or any other textual rewrite is rejected even
    when it would still parse to a document with a matching self-hash.
    """
    raw = lf((ROOT / path).read_bytes())
    value = read(path)
    require(raw == canonical(value), "artifact self-hash mismatch: " + path)
    return value


def discover_inventory_generations(directory=None):
    """Strict integer generation discovery from the exact trusted prefix.

    No lexicographic maximum, no gaps, no forks, no environment selection and
    no fallback to an older generation after a latest-generation failure.
    """
    directory = INVENTORY_DIRECTORY if directory is None else directory
    root = ROOT / directory
    require(root.is_dir(), "inventory generation directory missing: " + str(directory))
    found = {}
    for entry in sorted(root.iterdir()):
        if not entry.name.startswith(INVENTORY_PREFIX):
            continue  # other reviewed fixtures live beside the inventory chain
        match = INVENTORY_NAME.match(entry.name)
        require(match is not None, "malformed inventory generation filename: " + entry.name)
        generation = int(match.group(1))
        require(generation not in found, "duplicate inventory generation: " + entry.name)
        require(str(generation) == match.group(1), "non-canonical inventory generation: " + entry.name)
        found[generation] = entry.name
    require(found, "no reviewed inventory generation discovered in " + str(directory))
    require(min(found) == 1, "inventory generations must begin at V1")
    expected = list(range(1, max(found) + 1))
    require(sorted(found) == expected, "missing intermediate inventory generation: " + str(expected))
    base = Path(directory)
    return [(generation, (base / found[generation]).as_posix()) for generation in expected]


def load_inventory_generations(directory=None):
    """Authenticate contiguity, self-hashes and predecessor binding for all."""
    directory = INVENTORY_DIRECTORY if directory is None else directory
    chain = []
    for generation, path in discover_inventory_generations(directory):
        value = read_generation(path)
        require(value.get("schema_version") == generation, "inventory generation/schema mismatch: " + path)
        require(value.get("policy_id") == INVENTORY_POLICY_PREFIX + "_V" + str(generation),
                "inventory policy generation mismatch: " + path)
        if generation == 1:
            require(value.get("canonical_sha256") == INVENTORY_V1_SHA256,
                    "generation 1 must be the immutable A2 V1 inventory: " + path)
            require(value.get("generation") in (None, 1), "V1 generation field drift: " + path)
            require("predecessor_inventory" not in value, "V1 must not bind a predecessor: " + path)
        else:
            require(value.get("generation") == generation, "generation number mismatch: " + path)
            require(value.get("bridge_base_main_sha") == BRIDGE_BASE_MAIN,
                    "bridge base main anchor missing: " + path)
            require(value.get("historical_a2_reviewed_head") == A2_REVIEWED_HEAD,
                    "A2 reviewed head anchor missing: " + path)
            previous = chain[-1][1]
            predecessor = value.get("predecessor_inventory")
            require(isinstance(predecessor, dict), "successor inventory must bind its predecessor: " + path)
            require(predecessor.get("path") == inventory_generation_path(generation - 1),
                    "predecessor path mismatch: " + path)
            require(predecessor.get("generation") == generation - 1, "predecessor generation mismatch: " + path)
            require(predecessor.get("canonical_sha256") == previous["canonical_sha256"],
                    "predecessor canonical hash mismatch: " + path)
            require(predecessor.get("rewritten") is False, "predecessor rewrite claim: " + path)
        chain.append((path, value))
    return chain


def inventory_document(template, corpus=None):
    """Current corpus sealed into the shape of an authenticated generation."""
    value = {key: val for key, val in template.items()
             if key not in CORPUS_FIELDS and key != "canonical_sha256"}
    value.update(current_corpus_fields() if corpus is None else corpus)
    return seal(value)


def build_inventory(directory=None):
    """Full current reviewed inventory for the latest discovered generation."""
    return inventory_document(load_inventory_generations(directory)[-1][1])


def build_successor_inventory(directory=None, corpus=None):
    """Propose the next contiguous generation bound to the current corpus."""
    chain = load_inventory_generations(directory)
    latest = chain[-1][1]
    generation = len(chain) + 1
    value = {key: val for key, val in latest.items()
             if key not in CORPUS_FIELDS and key != "canonical_sha256"}
    value.update(current_corpus_fields() if corpus is None else corpus)
    value["schema_version"] = generation
    value["policy_id"] = INVENTORY_POLICY_PREFIX + "_V" + str(generation)
    value["generation"] = generation
    value["bridge_base_main_sha"] = BRIDGE_BASE_MAIN
    value["historical_a2_reviewed_head"] = A2_REVIEWED_HEAD
    value["predecessor_inventory"] = {"path": inventory_generation_path(generation - 1),
                                      "canonical_sha256": latest["canonical_sha256"],
                                      "generation": generation - 1, "rewritten": False}
    return seal(value)


def authenticate_predecessors():
    values = {path: read(path) for path in PREDECESSORS}
    for path, expected in PREDECESSORS.items():
        require(values[path]["canonical_sha256"] == expected, "immutable predecessor identity drift: " + path)
    require(git("rev-parse", "HEAD:.github/workflows").decode().strip() == WORKFLOW_TREE, "workflow tree drift")
    require(not git("diff", "--name-only", "HEAD", "--", ".github/workflows").strip(), "dirty workflow source")
    return values


def authenticate_inventory(directory=None, current=None):
    """Latest reviewed generation must equal the current source corpus."""
    directory = INVENTORY_DIRECTORY if directory is None else directory
    chain = load_inventory_generations(directory)
    latest_path, latest = chain[-1]
    # Generation 1 is proven against exact historical Git bytes on every run,
    # independently of whichever generation is currently latest.
    authenticate_historical_v1()
    if current is None:
        current = build_inventory() if directory == INVENTORY_DIRECTORY else inventory_document(latest)
    require(current == latest, "source or process discovery drift requires reviewed A2 inventory successor generation: "
             + latest_path)
    return latest


def activation_and_no_bypass(startup_text, workflow_text, guard_text, kernel_text, identity):
    """Root bootstrap, patch allowlist, guard hooks and kernel policy checks."""
    startup = ast.parse(startup_text)
    pins = next(ast.literal_eval(node.value) for node in startup.body
                if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                and target.id == "ROOT_TEST_SOURCE_PINS" for target in node.targets))
    protected = set(GUARD_PATHS) - {"sitecustomize.py"}
    protected.add("scripts/audit_core_01d_ci_offline_transport_boundary.py")
    require(pins == {path: identity(path)["lf_source_sha256"] for path in sorted(protected)},
            "root bootstrap does not bind exact patchable guard/auditor source")
    workflow = yaml.safe_load(workflow_text)
    step = next(step for step in workflow["jobs"]["validate"]["steps"]
                if step.get("name") == "Enforce path and patch safety")
    policy = ast.parse(step["run"].split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0])
    allowed = {target.id: ast.literal_eval(node.value) for node in policy.body
               if isinstance(node, ast.Assign) for target in node.targets
               if isinstance(target, ast.Name) and target.id in {"allowed_prefixes", "allowed_exact"}}
    require("sitecustomize.py" not in allowed["allowed_exact"]
            and not "sitecustomize.py".startswith(allowed["allowed_prefixes"]),
            "Patch Bridge can replace the trusted root bootstrap")
    guard = ast.parse(guard_text)
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
    kernel = ast.parse(kernel_text)
    require(not any(isinstance(node, ast.Call) and ast.unparse(node.func) in {"os.getenv", "eval", "exec"}
                    for node in ast.walk(kernel)), "kernel policy has a dynamic bypass")
    calls = [node for node in ast.walk(kernel) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "prctl"]
    require(any([ast.literal_eval(arg) for arg in node.args[:2]] == [38, 1] for node in calls), "no-new-privileges proof missing")
    require(any([ast.literal_eval(arg) for arg in node.args[:2]] == [22, 2] for node in calls), "kernel filter installation missing")
    return True


def authenticate_activation_and_no_bypass():
    """CURRENT root bootstrap/guard/kernel proof from exact worktree source."""
    return activation_and_no_bypass(
        (ROOT / "sitecustomize.py").read_text(),
        (ROOT / ".github/workflows/athena-patch-bridge.yml").read_text(),
        (ROOT / "tests/offline_transport.py").read_text(),
        (ROOT / "tests/offline_linux.py").read_text(),
        source)


def authenticate_historical_activation_and_no_bypass(commit=A2_REVIEWED_HEAD):
    """HISTORICAL A2 activation proof from exact A2 reviewed-head Git bytes."""
    return activation_and_no_bypass(
        historical_text("sitecustomize.py", commit),
        historical_text(".github/workflows/athena-patch-bridge.yml", commit),
        historical_text("tests/offline_transport.py", commit),
        historical_text("tests/offline_linux.py", commit),
        lambda path: historical_source(path, commit))


def build_receipt():
    """Reconstruct the immutable A2 receipt from historical A2 evidence only."""
    predecessors = authenticate_predecessors()
    inventory = authenticate_historical_v1()
    authenticate_historical_activation_and_no_bypass()
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
        text = historical_text(path)
        require("ubuntu-latest" in text and "python -m pytest" in text and "PYTHONPATH:" in text, "target execution/bootstrap contract drift")
    startup = historical_text("sitecustomize.py")
    require('"-m", "pytest"' in startup and 'raise SystemExit' in startup, "startup fail-closed activation drift")
    require("install()" in historical_text("tests/conftest.py"), "pytest activation drift")
    parent = next(value for path, value in predecessors.items() if path.endswith("checkpoint_e_completion_v2.json"))
    rows = parent["unresolved_pass_a_rows"]
    require({(row["workflow_path"], row["trigger_kind"]) for row in rows} == set(TARGETS), "exact three predecessor partials required")
    return seal({"schema_version": 1, "policy_id": POLICY_ID, "repository": "Thabearr/ATHENA", "master_issue": 337,
        "base_main_sha": BASE_MAIN, "base_tree_sha": BASE_TREE,
        "post_merge_ci_gate": {"run_id": 37066892743, "event": "push", "head_sha": BASE_MAIN, "conclusion": "success", "syntax_shards_1_to_8_aggregate": "SUCCESS"},
        "predecessor_identities": PREDECESSORS,
        "inventory": {"path": INVENTORY_PATH, "canonical_sha256": inventory["canonical_sha256"]},
        "guard_sources": [historical_source(path) for path in GUARD_PATHS],
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
    require(value.get("canonical_sha256") == RECEIPT_SHA256, "immutable A2 receipt identity drift")
    require(value == build_receipt(), "A2 receipt differs from its immutable historical A2 evidence reconstruction")
    # Both proof paths must hold: current activation and current corpus.
    authenticate_activation_and_no_bypass()
    authenticate_inventory()
    return {"result": "PASS", "receipt_sha256": value["canonical_sha256"], "resolved_target_count": value["resolved_target_count"],
            "historical_proof_mode": ("EXACT_A2_GIT_OBJECTS" if historical_objects_available()
                                      else "PINNED_IDENTITY_CHAIN_DEPTH1"),
            "current_platform_kernel_executed": bool(__import__("offline_linux")._active), "authority_granted": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--emit-inventory", action="store_true")
    parser.add_argument("--emit-successor-inventory", action="store_true")
    parser.add_argument("--emit-receipt", action="store_true")
    args = parser.parse_args()
    value = (build_successor_inventory() if args.emit_successor_inventory else
             build_inventory() if args.emit_inventory else
             build_receipt() if args.emit_receipt else audit())
    print(canonical(value).decode(), end="")


if __name__ == "__main__":
    main()
