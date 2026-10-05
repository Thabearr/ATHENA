"""APP-01A source receipt builder; performs no provider, worker or workflow action."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = "40ee3fcabe34fbbcf1cabfe240fad5cc58ced805"
PATHS = ("api/app_factory.py", "api/server.py", "run_desktop.py", "runtime/local_session.py",
         "services/athena_capability_service.py", "ui/index.html", "ui/app.js",
         "ui/legacy-index.html", "ui/legacy-app.js",
         "tests/test_app_01a_local_shell.py", "scripts/audit_app_01a_local_shell.py",
         "scripts/audit_core_01d_win_either_half_trigger_authority_b7.py",
         "scripts/audit_core_01d_checkpoint_e_completion_v10.py",
         "tests/test_core_01d_checkpoint_e_completion_v10.py",
         "tests/test_core_01d_ci_offline_transport_inventory_evolution.py",
         "tests/test_core_01d_port02c_trigger_authority_b6.py",
         "tests/test_core_01d_owner_one_shot_issue_comment_authority_b3.py",
         "tests/test_core_01d_frozen_artifact_replay_authority_b5.py")
RECEIPT = "artifacts/product/app_01a_local_shell_v1.json"


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
    base_ids = {path: {"git_blob_sha1": git("rev-parse", BASE + ":" + path).decode().strip(),
                       "sha256": hashlib.sha256(git("show", BASE + ":" + path)).hexdigest()}
                for path in prior_paths}
    document = {"schema_version": 1, "policy_id": "ATHENA_APP_01A_LOCAL_SHELL_V1", "repository": "Thabearr/ATHENA",
                "master_issue": 337, "base_commit": BASE, "base_tree": git("rev-parse", BASE + "^{tree}").decode().strip(),
                "workflow_tree": git("rev-parse", BASE + ":.github/workflows").decode().strip(),
                "source_review_counter_open": "2/5", "expected_counter_if_merged": "3/5",
                "base_identities": base_ids, "source_identities": identities,
                "source_inventory_sha256": hashlib.sha256(canonical(identities)).hexdigest(),
                "a2_inventory": {"path": "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v10.json",
                                 "canonical_sha256": json.loads((ROOT / "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v10.json").read_bytes())["canonical_sha256"]},
                "contracts": {"factory": "EXPLICIT_VERIFIED_DEPENDENCIES", "session": "OS_CSPRNG_256BIT_MEMORY_ONLY_V1",
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
    if document.get("base_commit") != BASE or document.get("base_tree") != "72fc46765b901276a890bf4d222b67087017d108":
        raise ValueError("APP-01A base identity mismatch")
    observed = {path: hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest() for path in PATHS}
    if document.get("source_identities") != observed:
        raise ValueError("APP-01A source identity mismatch")
    if document.get("source_inventory_sha256") != hashlib.sha256(canonical(observed)).hexdigest():
        raise ValueError("APP-01A source inventory mismatch")
    if any(type(value) is not int or value != 0 for value in document["safety"].values()):
        raise ValueError("APP-01A safety counts mismatch")
    return document


if __name__ == "__main__":
    target = ROOT / RECEIPT
    target.parent.mkdir(parents=True, exist_ok=True)
    result = build()
    target.write_bytes(canonical(result))
    print(json.dumps({"receipt": RECEIPT, "canonical_sha256": result["canonical_sha256"]}))
