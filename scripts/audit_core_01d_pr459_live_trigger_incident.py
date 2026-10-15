"""Audit the offline-only successor to the PR #459 direct-share workflows."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import types
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
PR459_REVIEWED_HEAD = "c96c74a319d79d2cbc4ed3f8ee2aab9f1b0bd47e"
PR459_MERGE_SHA = "7c787130e2662e34813a61422b865046fae52ebd"
MISSION_A2_BASE_GENERATION = 167
MISSION_A2_BASE_SHA = "c8a9e9123811104f625b13692b74beee0b16eba619bde6e03f5e74eda0fecb3a"
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
NATIVE_TEST = "tests/native/test_pr459_hosted_pr_live_share_trigger_safety.py"
BRIDGE = "scripts/sportybet_direct_share_bridge.py"

HISTORICAL_RUNS = [
    {
        "run_id": 38335345800,
        "workflow": "Create Saturday 2026-08-22 SportyBet direct 20 code",
        "job_id": 115094049269,
        "conclusion": "failure",
        "failing_step": "Run focused direct-share tests",
        "provider_operation_step": "Create and exact-roundtrip the 20-fold booking code",
        "provider_operation_step_conclusion": "skipped",
        "create_outcome": "skipped",
        "direct_outcome": "skipped",
    },
    {
        "run_id": 38335345629,
        "workflow": "Prove SportyBet direct share code",
        "job_id": 115094048229,
        "conclusion": "failure",
        "failing_step": "Run focused direct-share tests",
        "provider_operation_step": "Create and round-trip one anonymous SportyBet share code",
        "provider_operation_step_conclusion": "skipped",
        "create_outcome": "skipped",
        "direct_outcome": "skipped",
    },
    {
        "run_id": 38335345866,
        "workflow": "Tests",
        "conclusion": "success",
    },
    {
        "run_id": 38335345741,
        "workflow": "PORT-02C native runtime",
        "conclusion": "success",
        "linux": "success",
        "windows": "success",
    },
]

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


def _git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


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
        "Install repository dependencies for offline source audit",
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
             and python.get("with") == {
                 "python-version": "3.12", "cache": "pip",
                 "cache-dependency-path": "requirements.txt",
             },
             "offline workflow Python runtime drift: " + path)
    _require(install.get("run") ==
             "python -m pip install --disable-pip-version-check -r requirements.txt",
             "offline source audit dependencies are not installed from requirements.txt: " + path)
    declared_dependencies = {
        line.strip().split("=", 1)[0].strip().casefold()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    _require({"pytest", "pyyaml", "numpy"}.issubset(declared_dependencies),
             "requirements.txt omits dependencies used by offline tests/source audit")
    _require("python -m pytest -q" in test.get("run", ""),
             "offline workflow does not run focused deterministic tests: " + path)
    if path == CREATE_WORKFLOW:
        expected_test_command = [
            "python", "-m", "pytest", "-q", DIRECT_TEST,
            POLICY_TEST + "::test_both_direct_share_workflows_are_offline_only",
        ]
    else:
        expected_test_command = [
            "python", "-m", "pytest", "-q", "-k",
            "not audit_does_not_require_the_base_commit_object", B4_TEST,
            POLICY_TEST + "::test_tampered_b4_predecessor_fixture_fails",
            POLICY_TEST + "::test_current_workflow_tampering_cannot_hide_behind_b4_fixture",
        ]
    _require(shlex.split(test.get("run", "")) == expected_test_command,
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


# PR #461's merged incident checkpoint is immutable. Later A2 generations
# authenticate current sources, never become a new historical incident receipt.
HISTORICAL_GENERATION = 208
HISTORICAL_INVENTORY_SHA = "eac19de61bc8db38c8fd0496d9224c9de5377408c994800452bb84911180f626"
HISTORICAL_RECEIPT_SHA = "42569818232faed0dd35725e574676149dd9886eb6d20953a034ad03b0b9c579"
HISTORICAL_SOURCE = "tests/fixtures/core_01d/pr459_live_trigger_incident/incident-audit-v208-predecessor.py.txt"
HISTORICAL_SOURCE_BLOB = "4d877d598ea3aa161f1a19ed86f46d6dfc2b5bb0"
HISTORICAL_SOURCE_SHA = "212501c2653be6d01297e0d954c94631e1a3a3ff8f6142ad4f1fe2dadfc48532"


def historical_incident_source() -> bytes:
    historical = a2.read_generation(a2.inventory_generation_path(HISTORICAL_GENERATION))
    _require(historical["canonical_sha256"] == HISTORICAL_INVENTORY_SHA,
             "immutable incident A2 V208 identity drift")
    fixture = ROOT / HISTORICAL_SOURCE
    _require(fixture.is_file() and not fixture.is_symlink(),
             "incident predecessor source must be a regular file")
    source = (ROOT / HISTORICAL_SOURCE).read_bytes().replace(b"\r\n", b"\n")
    _require(_git_blob_sha1(source) == HISTORICAL_SOURCE_BLOB
             and hashlib.sha256(source).hexdigest() == HISTORICAL_SOURCE_SHA
             == _source_rows(historical).get(AUDIT_SCRIPT),
             "incident predecessor source fixture identity drift")
    return source


def build_receipt() -> dict[str, Any]:
    # Authenticate the entire current corpus before opening the bounded
    # historical view. Imported B4/D5/RUN-02A auditors still use current A2.
    current = a2.authenticate_inventory()
    chain = a2.load_inventory_generations()
    _require(current["generation"] >= HISTORICAL_GENERATION,
             "incident checkpoint requires A2 V208 or its authenticated successor")
    historical = chain[HISTORICAL_GENERATION - 1][1]
    _require(historical["canonical_sha256"] == HISTORICAL_INVENTORY_SHA,
             "immutable incident A2 V208 identity drift")
    source = historical_incident_source()
    # Execute only the exact authenticated predecessor implementation. Its
    # local A2 binding reconstructs V208/V207; no shared module is patched.
    checkpoint = types.ModuleType("_athena_pr459_incident_v208")
    checkpoint.__file__ = str(ROOT / HISTORICAL_SOURCE)
    exec(compile(source, checkpoint.__file__, "exec"), checkpoint.__dict__)
    checkpoint.ROOT = ROOT
    checkpoint.a2 = types.SimpleNamespace(
        canonical=a2.canonical,
        authenticate_inventory=lambda: historical,
        load_inventory_generations=lambda: chain[:HISTORICAL_GENERATION],
    )
    value = checkpoint.build_receipt()
    _require(value["canonical_sha256"] == HISTORICAL_RECEIPT_SHA,
             "immutable incident reconstruction identity drift")
    return value


def audit(expected_receipt: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = (ROOT / RECEIPT_PATH).read_bytes()
    value = json.loads(raw)
    _require(raw == _canonical(value), "incident evidence is not canonical JSON")
    _require(value.get("canonical_sha256") == HISTORICAL_RECEIPT_SHA,
             "immutable incident receipt identity drift")
    expected = build_receipt() if expected_receipt is None else expected_receipt
    _require(value == expected, "incident evidence differs from current source and history")
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
        raise SystemExit("PR #459 incident receipt is immutable; use a reviewed forward successor")
    elif not (ROOT / RECEIPT_PATH).is_file():
        raise SystemExit("incident evidence artifact is missing; use --write after source qualification")
    result = "PASS" if args.write else audit(value)["result"]
    print(json.dumps({"result": result,
                      "canonical_sha256": value["canonical_sha256"],
                      "a2_generation": value["a2"]["successor_generation"],
                      "review_ready": False}, sort_keys=True))


if __name__ == "__main__":
    main()
