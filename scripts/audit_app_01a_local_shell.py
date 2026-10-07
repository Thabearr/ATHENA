"""APP-01A source receipt builder; performs no provider, worker or workflow action."""
from __future__ import annotations

import hashlib
import base64
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = "40ee3fcabe34fbbcf1cabfe240fad5cc58ced805"
PATHS = ("api/app_factory.py", "api/server.py", "run_desktop.py", "runtime/local_session.py",
         "runtime/resources.py", "services/athena_capability_service.py", "ui/index.html", "ui/app.js",
         "ui/legacy-index.html", "ui/legacy-app.js",
         "tests/test_app_01a_local_shell.py", "scripts/audit_app_01a_local_shell.py",
         "scripts/audit_core_01d_win_either_half_trigger_authority_b7.py",
         "scripts/audit_core_01d_checkpoint_e_completion_v10.py",
         "tests/test_core_01d_checkpoint_e_completion_v10.py",
         "tests/test_core_01d_ci_offline_transport_inventory_evolution.py",
         "tests/test_core_01d_port02c_trigger_authority_b6.py",
         "tests/test_core_01d_owner_one_shot_issue_comment_authority_b3.py",
         "tests/test_core_01d_frozen_artifact_replay_authority_b5.py",
         "tests/portability/test_port_02_release_identity.py")
PATHS += ("scripts/audit_core_01d_checkpoint_e_completion_v2.py",
          "scripts/audit_core_01d_port02c_trigger_authority_b6.py",
          "scripts/audit_checkpoint_e_workflows.py", "docs/product/app_01a_local_shell.md")
PATHS += ("tests/test_core_01d_exact_pr_trigger_disposition_b1.py",)
RECEIPT = "artifacts/product/app_01a_local_shell_v1.json"
INVENTORY = "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v18.json"
HISTORICAL_A2_INVENTORY_PATHS = frozenset(
    f"tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v{generation}.json"
    for generation in range(10, 22)
)
HISTORICAL_RUNTIME_PATHS = {"api/server.py", "run_desktop.py", "ui/index.html", "ui/app.js"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode() + b"\n"


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def build():
    identities = {path: hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                  for path in PATHS}
    prior_paths = ("api/server.py", "run_desktop.py", "ui/index.html", "ui/app.js", "ui/styles.css",
                   "runtime/release_identity.py", "runtime/resources.py", "runtime/source_identity.py",
                   "runtime/worker_launcher.py", "artifacts/product/product_baseline_v1.json",
                   "artifacts/architecture/port_02_native_runtime_v1.json")
    base_paths = set(git("ls-tree", "-r", "--name-only", BASE).decode().splitlines())
    prior_paths = sorted(set(prior_paths) | (set(PATHS) & base_paths))
    base_ids = {path: {"git_blob_sha1": git("rev-parse", BASE + ":" + path).decode().strip(),
                       "sha256": hashlib.sha256(git("show", BASE + ":" + path)).hexdigest()}
                for path in prior_paths}
    document = {"schema_version": 1, "policy_id": "ATHENA_APP_01A_LOCAL_SHELL_V1", "repository": "Thabearr/ATHENA",
                "master_issue": 337, "base_commit": BASE, "base_tree": git("rev-parse", BASE + "^{tree}").decode().strip(),
                "workflow_tree": git("rev-parse", BASE + ":.github/workflows").decode().strip(),
                "source_review_counter_open": "2/5", "expected_counter_if_merged": "3/5",
                "base_identities": base_ids, "source_identities": identities,
                "historical_runtime_payloads": {path: base64.b64encode(git("show", BASE + ":" + path)).decode("ascii")
                                                for path in sorted(HISTORICAL_RUNTIME_PATHS)},
                "source_inventory_sha256": hashlib.sha256(canonical(identities)).hexdigest(),
                "a2_inventory": {"path": INVENTORY,
                                 "canonical_sha256": json.loads((ROOT / INVENTORY).read_bytes())["canonical_sha256"]},
                "resource_evolution": {"classification": "APP01A_VERIFIED_UI_BYTES_ONLY_NO_CORE_PARITY_CHANGE",
                                       "historical_port02a_manifest_sha256": "95eeb5bcd983dd66d3952a18948edf7aaf0a121dff247cdc7f67a42186d817c2",
                                       "changed_ui_resources": ["ui/index.html", "ui/app.js"]},
                "contracts": {"factory": "EXPLICIT_VERIFIED_DEPENDENCIES_AND_WRITABLE_ROOTS",
                              "application_data_root": "PORT_02A_WRITABLE_ROOTS_EXACT_TYPE_SEPARATE_FROM_RESOURCES",
                              "session": "OS_CSPRNG_256BIT_MEMORY_ONLY_V1",
                              "health": "ATHENA_LOCAL_HEALTH_V1", "capabilities": "ATHENA_LOCAL_CAPABILITIES_V1",
                              "bootstrap": "ORIGIN_GUARDED_NATIVE_TO_JS_SINGLE_DELIVERY_NO_JS_API"},
                "authority": {"provider": False, "model_readiness": "unproven", "run_admission": False,
                              "generic_js_python_bridge": False},
                "safety": {name: 0 for name in ("provider_acquisition", "external_delivery", "worker_execution", "workflow_dispatch",
                           "workflow_rerun", "workflow_cancel", "share_code", "email", "login", "account_cookie", "wallet", "stake", "wager",
                           "supported_fixed_port", "wildcard_cors", "historical_receipt_rewrite", "workflow_yaml_diff")},
                "validation_binding": "Exact final commit/tree, automatic Tests run and platform results are reported separately to avoid self-reference.",
                "rollback": "Revert the APP-01A semantic commit; no persisted credentials or external actions require recovery.",
                "limitations": ["Capabilities are UI information only; APP-01B must recheck admission.",
                                "No full run UX, packaging release, worker durability or model qualification is claimed.",
                                "Native Linux GUI proof requires an available GTK/WebKit environment; hosted Linux exercises HTTP/runtime seams."],
                "review_ready_terminal_requires_green_exact_head": "APP_01A_REVIEW_READY_LOCAL_SHELL_SECURE_DO_NOT_MERGE"}
    document["canonical_sha256"] = hashlib.sha256(canonical(document)).hexdigest()
    return document


def validate():
    document = json.loads((ROOT / RECEIPT).read_bytes())
    unsealed = {key: value for key, value in document.items() if key != "canonical_sha256"}
    if document.get("canonical_sha256") != hashlib.sha256(canonical(unsealed)).hexdigest():
        raise ValueError("APP-01A receipt seal mismatch")
    if document.get("canonical_sha256") != "3e58c91f5af38615786d634e088ad4c0f53a05f272453930ebef27705a47c537":
        raise ValueError("APP-01A immutable receipt identity mismatch")
    if document.get("base_commit") != BASE or document.get("base_tree") != "72fc46765b901276a890bf4d222b67087017d108":
        raise ValueError("APP-01A base identity mismatch")
    from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
    latest = boundary.authenticate_inventory()
    historical = boundary.read_generation(INVENTORY)
    if historical.get("generation") != 18:
        raise ValueError("APP-01A historical A2 generation mismatch")
    if document.get("a2_inventory") != {
        "path": INVENTORY,
        "canonical_sha256": historical.get("canonical_sha256"),
    }:
        raise ValueError("APP-01A historical A2 identity mismatch")
    if latest.get("generation") < 21:
        raise ValueError("APP-01A current source successor is unavailable")
    historical_source_ids = {
        row["path"]: row["lf_source_sha256"] for row in historical["source_identities"]
    }
    expected = document.get("source_identities")
    if type(expected) is not dict:
        raise ValueError("APP-01A source identity mismatch")
    for path in PATHS:
        pinned = expected.get(path)
        if path in historical_source_ids:
            observed = historical_source_ids[path]
        else:
            observed = hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        if pinned != observed:
            raise ValueError("APP-01A source identity mismatch")
    if document.get("source_inventory_sha256") != hashlib.sha256(canonical(expected)).hexdigest():
        raise ValueError("APP-01A source inventory mismatch")
    if any(type(value) is not int or value != 0 for value in document["safety"].values()):
        raise ValueError("APP-01A safety counts mismatch")
    return document


def authenticated_historical_paths():
    """Current evidence must pass before a bounded historical projection."""
    from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
    boundary.authenticate_inventory()
    document = validate()
    from scripts import audit_data_01a_app_schema_core as data01a
    data01a.historical_build_config()
    document = dict(document)
    document["base_identities"] = dict(document["base_identities"])
    document["base_identities"][data01a.BUILD_CONFIG] = {
        "git_blob_sha1": data01a.BUILD_CONFIG_BLOB, "sha256": data01a.BUILD_CONFIG_SHA256,
    }
    return set(PATHS) | {RECEIPT, INVENTORY, data01a.BUILD_CONFIG} | HISTORICAL_A2_INVENTORY_PATHS | data01a.NEW_PATHS, document


def historical_runtime_payload(path):
    _, document = authenticated_historical_paths()
    return _decode_historical_runtime_payload(document, path)


def _decode_historical_runtime_payload(document, path):
    """Decode an already authenticated snapshot, retaining exact blob checks."""
    if path not in HISTORICAL_RUNTIME_PATHS:
        raise ValueError("path is outside historical APP runtime projection")
    raw = base64.b64decode(document["historical_runtime_payloads"][path], validate=True)
    identity = document["base_identities"][path]
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if hashlib.sha256(raw).hexdigest() != identity["sha256"] or blob != identity["git_blob_sha1"]:
        raise ValueError("historical APP runtime payload identity mismatch")
    return raw


def historical_tree_projection(raw):
    paths, document = authenticated_historical_paths()
    paths |= HISTORICAL_A2_INVENTORY_PATHS
    rows = []
    for line in raw.splitlines(keepends=True):
        metadata, name = line.split(b"\t", 1)
        path = name.strip().decode()
        if path in paths:
            identity = document["base_identities"].get(path)
            if identity is None:
                continue
            line = metadata.rsplit(b" ", 1)[0] + b" " + identity["git_blob_sha1"].encode() + b"\t" + name
        rows.append(line)
    return b"".join(rows)


if __name__ == "__main__":
    result = validate()
    print(json.dumps({"receipt": RECEIPT, "canonical_sha256": result["canonical_sha256"],
                      "immutable": True}))
