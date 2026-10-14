"""Audit the offline-only successor to the PR #459 direct-share workflows."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

import yaml

from scripts import audit_core_01d_ci_offline_transport_boundary as a2
from scripts import audit_core_01d_sportybet_current_trigger_authority_b4 as b4
from scripts import audit_data_01c_restore_portability as d5
from scripts import audit_run_02a_pre_durable_share_send as run02a

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = "tests/fixtures/core_01d/pr459_live_trigger_incident_v1.json"
BASE_MAIN = "bca71d0614e50b32f99077f092e9e22190b4d79c"
BASE_TREE = "99e411e31052b7ebc1f03daf7edd55d851999355"
MISSION_A2_BASE_GENERATION = 167
MISSION_A2_BASE_SHA = "c8a9e9123811104f625b13692b74beee0b16eba619bde6e03f5e74eda0fecb3a"
IMMEDIATE_A2_PREDECESSOR_GENERATION = 171
IMMEDIATE_A2_PREDECESSOR_SHA = "0550db750224aa5c0e24dcc9bfc3de18bc32e7e657263b2772d25a6ff528bf5c"
FINAL_A2_GENERATION = 172
B4_RECEIPT_SHA = "915e41796a419c2b360935ee3f21b293f233b6a356329694d0a3e9cd0fecb1fe"
B4_INVENTORY_SHA = "01c826a6e7e50e2a7f7b7a5ace946e0c8cdb72f58a6eb170b9d44ee5c1565f6a"
PR_TITLE = "[CORE-01D][CI Safety] Keep direct share-code proofs offline on PRs"
BRANCH = "fix/pr459-hosted-pr-live-share-trigger-incident"
SOURCE_REVIEW_COUNTER = "0/5"
SOURCE_REVIEW_COUNTER_IF_MERGED = "1/5"

CREATE_WORKFLOW = ".github/workflows/create-saturday-2026-08-22-sportybet-direct-20-code.yml"
PROVE_WORKFLOW = ".github/workflows/prove-sportybet-direct-share-code.yml"
AUDIT_SCRIPT = "scripts/audit_core_01d_pr459_live_trigger_incident.py"
POLICY_TEST = "tests/test_core_01d_pr459_live_trigger_incident.py"
B4_TEST = "tests/test_core_01d_sportybet_current_trigger_authority_b4.py"
DIRECT_TEST = "tests/test_sportybet_direct_share_bridge.py"
BRIDGE = "scripts/sportybet_direct_share_bridge.py"

WORKFLOW_PATHS = {
    CREATE_WORKFLOW: [
        CREATE_WORKFLOW,
        PROVE_WORKFLOW,
        "artifacts/research-protocols/saturday-2026-08-22-sportybet-final-20-selections-v1.json",
        BRIDGE,
        AUDIT_SCRIPT,
        DIRECT_TEST,
        POLICY_TEST,
        B4_TEST,
    ],
    PROVE_WORKFLOW: [
        CREATE_WORKFLOW,
        PROVE_WORKFLOW,
        "artifacts/research-protocols/saturday-2026-08-22-sportybet-direct-one-leg-proof-v1.json",
        BRIDGE,
        AUDIT_SCRIPT,
        DIRECT_TEST,
        POLICY_TEST,
        B4_TEST,
    ],
}

LIVE_MARKERS = (
    "python scripts/sportybet_direct_share_bridge.py",
    ".create_and_roundtrip(",
    "/api/ng/orders/share",
    "requests.post(",
    "urlopen(",
    "curl ",
    "wget ",
    "upload-artifact",
)


class IncidentAuditError(AssertionError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise IncidentAuditError(reason)


def _canonical(value: Any) -> bytes:
    return a2.canonical(value)


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("canonical_sha256", None)
    result["canonical_sha256"] = hashlib.sha256(_canonical(result)).hexdigest()
    return result


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _workflow(path: str) -> dict[str, Any]:
    raw = (ROOT / path).read_text(encoding="utf-8")
    value = yaml.load(raw, Loader=yaml.BaseLoader)
    _require(type(value) is dict, "workflow YAML is not a mapping: " + path)
    return value


def _validate_workflow(path: str) -> dict[str, Any]:
    workflow = _workflow(path)
    _require(set(workflow.get("on", {})) == {"pull_request", "workflow_dispatch"},
             "direct-share workflow trigger set drift: " + path)
    pr = workflow["on"]["pull_request"]
    _require(pr.get("branches") == ["main"] and pr.get("paths") == WORKFLOW_PATHS[path],
             "direct-share offline PR path filter drift: " + path)

    dispatch = workflow["on"]["workflow_dispatch"]
    _require(set(dispatch.get("inputs", {})) == {"validation_mode"},
             "manual workflow exposes an unreviewed input: " + path)
    mode = dispatch["inputs"]["validation_mode"]
    _require(mode.get("type") == "choice" and mode.get("required") == "true"
             and mode.get("default") == "offline_only"
             and mode.get("options") == ["offline_only"],
             "manual workflow mode is not restricted to offline-only: " + path)

    _require(workflow.get("permissions") == {"contents": "read"},
             "direct-share offline workflow permissions drift: " + path)
    jobs = workflow.get("jobs", {})
    _require(set(jobs) == {"offline-validation"},
             "workflow contains a non-offline job: " + path)
    steps = jobs["offline-validation"].get("steps", [])
    _require([step.get("name") for step in steps] == [
        "Checkout repository without persisted credentials",
        "Enforce offline-only manual mode",
        "Set up Python 3.12",
        "Install focused offline test dependencies",
        ("Run focused offline boundary tests" if path == CREATE_WORKFLOW
         else "Run historical trigger-projection regressions"),
        "Audit both direct-share workflow surfaces",
    ], "offline workflow step sequence drift: " + path)

    checkout, mode_guard, python, install, test, audit = steps
    _require(checkout.get("uses") == "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
             and checkout.get("with") == {"persist-credentials": "false"},
             "checkout credentials are not disabled: " + path)
    _require(mode_guard.get("env") == {
        "EVENT_NAME": "${{ github.event_name }}",
        "VALIDATION_MODE": "${{ inputs.validation_mode }}",
    }, "manual mode guard does not bind exact event/input: " + path)
    guard_source = mode_guard.get("run", "")
    _require("EVENT_NAME" in guard_source and "workflow_dispatch" in guard_source
             and "VALIDATION_MODE" in guard_source and "offline_only" in guard_source
             and "exit 1" in guard_source,
             "non-offline manual dispatch does not fail closed: " + path)
    _require(python.get("uses") == "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065"
             and python.get("with", {}).get("python-version") == "3.12",
             "offline workflow Python runtime drift: " + path)
    _require("pytest" in install.get("run", "") and "PyYAML" in install.get("run", ""),
             "focused offline workflow omits the conftest YAML dependency: " + path)
    _require("python -m pytest -q" in test.get("run", ""),
             "offline workflow does not run focused deterministic tests: " + path)
    expected_test_paths = ((DIRECT_TEST, POLICY_TEST) if path == CREATE_WORKFLOW
                           else (B4_TEST, POLICY_TEST))
    _require(all(test_path in test.get("run", "") for test_path in expected_test_paths),
             "offline workflow test selection drift: " + path)
    _require(audit.get("run") == "python -m scripts.audit_core_01d_pr459_live_trigger_incident",
             "offline workflow omits the source-controlled authority audit: " + path)

    for step in steps:
        _require(step.get("continue-on-error") is None,
                 "offline workflow suppresses a failing safety check: " + path)
        for key in ("run", "uses"):
            value = str(step.get(key, "")).casefold()
            _require(not any(marker.casefold() in value for marker in LIVE_MARKERS),
                     "offline workflow retains a provider/live/artifact call edge: " + path)
    _require(not any("secret" in str(key).casefold() for step in steps
                     for key in step.get("env", {})),
             "offline workflow binds a secret environment variable: " + path)
    return workflow


def _source_rows(inventory: dict[str, Any]) -> dict[str, str]:
    return {row["path"]: row["lf_source_sha256"] for row in inventory["source_identities"]}


def build_receipt() -> dict[str, Any]:
    latest = a2.authenticate_inventory()
    chain = a2.load_inventory_generations()
    _require(latest["generation"] == FINAL_A2_GENERATION,
             "incident requires the final append-only A2 successor")
    mission_predecessor = chain[MISSION_A2_BASE_GENERATION - 1][1]
    immediate_predecessor = chain[IMMEDIATE_A2_PREDECESSOR_GENERATION - 1][1]
    _require(mission_predecessor["generation"] == MISSION_A2_BASE_GENERATION
             and mission_predecessor["canonical_sha256"] == MISSION_A2_BASE_SHA,
             "V167 predecessor changed or was rewritten")
    _require(immediate_predecessor["generation"] == IMMEDIATE_A2_PREDECESSOR_GENERATION
             and immediate_predecessor["canonical_sha256"] == IMMEDIATE_A2_PREDECESSOR_SHA,
             "intermediate V168 was rewritten")

    _, expected_d5_tree = d5.authenticate_workflow()
    current_workflow_tree = _git("rev-parse", "HEAD:.github/workflows")
    projected_tree = b4.project_b4_workflow_tree(current_workflow_tree)
    _require(projected_tree == expected_d5_tree,
             "current workflow tree is not the exact B4/D5 projection")
    _require(d5.historical_workflow_tree(current_workflow_tree) == b4.WORKFLOW_TREE,
             "immutable B4 workflow tree cannot be rederived")

    _require(b4.audit()["result"] == "PASS", "immutable B4 evidence no longer rederives")
    b4_receipt = b4.boundary.read(b4.RECEIPT_PATH)
    b4_inventory = b4.boundary.read(b4.SOURCE_INVENTORY_PATH)
    _require(hashlib.sha256(b4.boundary.canonical(b4_receipt)).hexdigest() == B4_RECEIPT_SHA
             and hashlib.sha256(b4.boundary.canonical(b4_inventory)).hexdigest() == B4_INVENTORY_SHA,
             "immutable B4 evidence changed")
    _require(run02a.audit()["canonical_sha256"] == run02a.RETAINED_RECEIPT_SHA,
             "RUN-02A-PRE retained evidence changed")

    workflow_contracts = {}
    current_sources = _source_rows(latest)
    for path in (CREATE_WORKFLOW, PROVE_WORKFLOW):
        source = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
        _require(current_sources.get(path) == hashlib.sha256(source).hexdigest(),
                 "current workflow is not authenticated by A2: " + path)
        workflow = _validate_workflow(path)
        workflow_contracts[path] = {
            "source_lf_sha256": current_sources[path],
            "event_names": sorted(workflow["on"]),
            "pr_branches": workflow["on"]["pull_request"]["branches"],
            "pr_paths": workflow["on"]["pull_request"]["paths"],
            "dispatch_mode": "OFFLINE_ONLY",
            "permissions": workflow["permissions"],
            "reachable_provider_calls": [],
            "reachable_share_code_create_or_reload": False,
            "artifact_upload": False,
            "checkout_credentials_persisted": False,
        }

    return _seal({
        "schema_version": 1,
        "policy_id": "ATHENA_CORE_01D_PR459_LIVE_TRIGGER_INCIDENT_V1",
        "repository": "Thabearr/ATHENA",
        "pr_title": PR_TITLE,
        "branch": BRANCH,
        "base_main_sha": BASE_MAIN,
        "base_tree_sha": BASE_TREE,
        "a2": {
            "successor_generation": latest["generation"],
            "successor_canonical_sha256": latest["canonical_sha256"],
            "mission_base_generation": MISSION_A2_BASE_GENERATION,
            "mission_base_canonical_sha256": MISSION_A2_BASE_SHA,
            "intermediate_generation": IMMEDIATE_A2_PREDECESSOR_GENERATION,
            "intermediate_canonical_sha256": IMMEDIATE_A2_PREDECESSOR_SHA,
            "predecessor_generation": IMMEDIATE_A2_PREDECESSOR_GENERATION,
            "predecessor_canonical_sha256": IMMEDIATE_A2_PREDECESSOR_SHA,
            "predecessor_rewritten": False,
        },
        "incident": {
            "pr459_merged_with_two_failed_non_skipped_checks": True,
            "failed_runs": [38335345800, 38335345629],
            "failure": "MISSING_PYYAML_BEFORE_LIVE_STEP; LIVE_CREATE_AND_RELOAD_STEPS_SKIPPED",
            "root_cause": "PYTEST_INSTALL_OMITTED_PYYAML_IMPORTED_BY_TESTS_CONFTEST",
            "accidental_dependency_failure_is_not_a_safety_guard": True,
        },
        "current_workflow_contracts": workflow_contracts,
        "delivery_authority": {
            "automatic_pr_share_code_create": False,
            "manual_workflow_share_code_create": False,
            "manual_workflow_mode": "OFFLINE_ONLY",
            "direct_bridge_product_authority_changed": False,
            "future_live_proof_requires_separate_reviewed_authority": True,
            "no_live_proof_or_provider_request_performed": True,
        },
        "historical_evidence": {
            "b4_receipt_path": b4.RECEIPT_PATH,
            "b4_receipt_canonical_sha256": B4_RECEIPT_SHA,
            "b4_source_inventory_path": b4.SOURCE_INVENTORY_PATH,
            "b4_source_inventory_canonical_sha256": B4_INVENTORY_SHA,
            "b4_workflow_predecessors": {
                path: {
                    "fixture": fixture,
                    "git_blob_sha1": b4.SOURCE_PINS[path][0],
                    "lf_source_sha256": b4.SOURCE_PINS[path][1],
                }
                for path, fixture in b4.B4_WORKFLOW_PREDECESSORS.items()
            },
            "run_02a_pre_receipt_canonical_sha256": run02a.RETAINED_RECEIPT_SHA,
            "run_01a_receipt_unchanged": True,
            "run_01b_receipt_unchanged": True,
            "pr457_policy_unchanged": True,
        },
        "branch_protection": {
            "repository_ruleset_og": "OBSERVED_DISABLED",
            "main_protection_api": "UNVERIFIED_403_INTEGRATION_LIMIT",
            "owner_settings_followup_required": True,
            "settings_mutated": False,
        },
        "governance": {
            "source_review_counter_while_unmerged": SOURCE_REVIEW_COUNTER,
            "source_review_counter_if_owner_merges": SOURCE_REVIEW_COUNTER_IF_MERGED,
            "run_02a": "BLOCKED_UNSTARTED",
            "e4": "UNSTARTED",
            "e5": "UNSTARTED",
            "merge_authorized": False,
            "final_head_and_exact_head_ci": "RECORDED_IN_PR_BODY_AFTER_NATURAL_HOSTED_GATES",
        },
        "restricted_action_counts": dict.fromkeys((
            "provider_acquisition", "live_current_shadow", "fresh_holdout_manual",
            "real_share_code_create", "delivery", "login", "cookies", "wallet",
            "stake", "wager", "email", "manual_workflow_dispatch",
            "manual_workflow_rerun", "manual_workflow_cancel",
        ), 0),
        "review_state": "SOURCE_POLICY_PASS_EXACT_HEAD_HOSTED_GATES_PENDING",
        "review_ready": False,
        "merge_authorized": False,
    })


def audit() -> dict[str, Any]:
    raw = (ROOT / RECEIPT_PATH).read_bytes()
    value = json.loads(raw)
    _require(raw == _canonical(value), "incident evidence is not canonical JSON")
    _require(value == build_receipt(), "incident evidence differs from current source and history")
    _require(value.get("canonical_sha256") == hashlib.sha256(_canonical({
        key: child for key, child in value.items() if key != "canonical_sha256"
    })).hexdigest(), "incident evidence canonical hash mismatch")
    return {"result": "PASS", "canonical_sha256": value["canonical_sha256"],
            "a2_generation": value["a2"]["successor_generation"],
            "review_ready": value["review_ready"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write the forward incident evidence artifact")
    args = parser.parse_args()
    value = build_receipt()
    if args.write:
        target = ROOT / RECEIPT_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_canonical(value))
    elif not (ROOT / RECEIPT_PATH).is_file():
        raise SystemExit("incident evidence artifact is missing; use --write after source qualification")
    print(json.dumps({"result": "PASS" if args.write else audit()["result"],
                      "canonical_sha256": value["canonical_sha256"],
                      "a2_generation": value["a2"]["successor_generation"],
                      "review_ready": False}, sort_keys=True))


if __name__ == "__main__":
    main()
