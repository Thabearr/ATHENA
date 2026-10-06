"""Authenticate the final bounded Win-Either-Half trigger authority review (B7).

This review is source/evidence only. It does not create a campaign declaration,
dispatch or rerun a workflow, download an Actions artifact, acquire provider
data, enable a market, create/reload a share code, log in, touch a wallet,
stake, or wager.
"""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import yaml

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_checkpoint_e_completion_v9 as completion_v9
from scripts import audit_core_01d_port02c_trigger_authority_b6 as b6

ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "ATHENA_CORE_01D_WIN_EITHER_HALF_TRIGGER_AUTHORITY_B7_V1"
INVENTORY_POLICY_ID = "ATHENA_CORE_01D_WIN_EITHER_HALF_TRIGGER_AUTHORITY_B7_SOURCE_INVENTORY_V1"
BASE_MAIN = "a6e36f8e482ab71ca7d5cec196c579671fed0fb4"
BASE_TREE = "0c8772f62a0d984eb1c23b6bbe2257b9f5b614d0"
WORKFLOW_TREE = "9b08653f1a12bb1b3d964fbd910396ff955740da"
EVOLUTION_SHA = "73e1eb3fe6593558c821600dd0f103353d45c15a139ab470a996c7cbb35da531"
RETIREMENT_SHA = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
COMPLETION_V9_PATH = completion_v9.RECEIPT_PATH
COMPLETION_V9_SHA = "e587da6b663a7f98fda4aa3d8be53525a35354a7b2a2ff51b8cae86adfa47177"
B6_RECEIPT_PATH = b6.RECEIPT_PATH
B6_RECEIPT_SHA = "b9efafc34139a26de58da6cd2421dd43a174e375cabd0a2ccecdd5f21cb04966"
A2_V8_PATH = boundary.inventory_generation_path(8)
A2_V8_SHA = "856129ba6eafb0281f10a16639f26fd477b2ba6a2fb00957ee79fa539539412d"
A2_V9_SHA = "24c350c282ca07f1efd46828b777bfc8795e0dec689dc1f91b471da099492a96"
WORKFLOW = ".github/workflows/validate-win-either-half-campaign-commitment.yml"
WORKFLOW_BLOB = "24432c98ce2000ad5eb43276f99ef93d67da22ad"
WORKFLOW_SOURCE_SHA256 = "6ffd59b561c083bb305c1241927220882248b69ce47f34f4bf97f2f60b873e3b"
TARGET = (WORKFLOW, "pull_request")
SOURCE_INVENTORY_PATH = "tests/fixtures/core_01d/win-either-half-trigger-authority-b7-source-inventory-v1.json"
SOURCE_INVENTORY_SHA = "525d43ca4fc6abeb77fbaf9e74f4a3c53d5a4dba492fce809df09a482a95dbac"
RECEIPT_PATH = "tests/fixtures/core_01d/core-01d-win-either-half-trigger-authority-b7-v1.json"
OBSERVED_AT = "2026-10-05T08:06:02Z"
SOURCE_REVIEW_COUNTER_WHILE_OPEN = "1/5"
SOURCE_REVIEW_COUNTER_IF_OWNER_MERGES = "2/5"
POST_445_TESTS = {
    "run_id": 37274587030,
    "workflow": "Tests",
    "event": "push",
    "branch": "main",
    "head_sha": BASE_MAIN,
    "status": "completed",
    "conclusion": "success",
    "run_attempt": 1,
}
EXPECTED_PR_PATHS = (
    "artifacts/research-commitments/win-either-half/**",
    WORKFLOW,
    "artifacts/research-protocols/win-either-half-campaign-commitment-v1.json",
    "domain/win_either_half_campaign_commitment.py",
    "scripts/manage_win_either_half_campaign_commitment.py",
    "docs/win_either_half_campaign_commitment.md",
    "tests/test_win_either_half_campaign_commitment.py",
)
SOURCE_PATHS = (
    WORKFLOW,
    "requirements.txt",
    "artifacts/research-protocols/win-either-half-campaign-commitment-v1.json",
    "artifacts/research-protocols/win-either-half-prospective-capture-campaign-v1.json",
    "artifacts/research-protocols/win-either-half-prospective-replay-v1.json",
    "docs/win_either_half_campaign_commitment.md",
    "domain/markets.py",
    "domain/model_status.py",
    "domain/win_either_half_campaign_commitment.py",
    "domain/win_either_half_capture_campaign.py",
    "domain/win_either_half_prospective_replay.py",
    "domain/win_either_half_pricing_source_qualification.py",
    "scripts/freeze_evidence_baseline.py",
    "scripts/manage_win_either_half_campaign_commitment.py",
    "scripts/manage_win_either_half_capture_campaign.py",
    "tests/test_win_either_half_campaign_commitment.py",
)
SOURCE_ROLES = {
    WORKFLOW: "current_target_workflow_and_direct_pull_request_trigger_contract",
    "requirements.txt": "workflow_build_dependency_manifest",
    "artifacts/research-protocols/win-either-half-campaign-commitment-v1.json": "stage_5b4_exact_protocol_contract",
    "artifacts/research-protocols/win-either-half-prospective-capture-campaign-v1.json": "stage_5b3_exact_protocol_dependency",
    "artifacts/research-protocols/win-either-half-prospective-replay-v1.json": "stage_5b2_exact_protocol_dependency",
    "docs/win_either_half_campaign_commitment.md": "governance_and_operator_contract",
    "domain/markets.py": "canonical_market_registry_dependency",
    "domain/model_status.py": "market_pricing_and_selection_authority_registry_dependency",
    "domain/win_either_half_campaign_commitment.py": "stage_5b4_offline_commitment_and_deadline_contract",
    "domain/win_either_half_capture_campaign.py": "stage_5b3_offline_campaign_contract_dependency",
    "domain/win_either_half_prospective_replay.py": "stage_5b2_offline_replay_contract_dependency",
    "domain/win_either_half_pricing_source_qualification.py": "stage_5b1_qualification_contract_dependency",
    "scripts/freeze_evidence_baseline.py": "local_git_code_state_dependency",
    "scripts/manage_win_either_half_campaign_commitment.py": "stage_5b4_local_git_validator_and_attestation_writer",
    "scripts/manage_win_either_half_capture_campaign.py": "focused_test_dependency_for_offline_stage_5b3_bundle_logic",
    "tests/test_win_either_half_campaign_commitment.py": "workflow_focused_stage_5b4_regression_suite",
}
ZERO_ACTIONS = {
    "workflow_dispatches": 0,
    "workflow_reruns": 0,
    "workflow_cancellations": 0,
    "artifact_payload_downloads": 0,
    "campaign_declarations_created_or_modified": 0,
    "timing_attestations_created": 0,
    "provider_requests": 0,
    "market_activations": 0,
    "share_code_create_or_reload": 0,
    "login_cookie_wallet_stake_wager_actions": 0,
    "release_mutations": 0,
    "workflow_retirements_or_deletions": 0,
}


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AssertionError(reason)


def _git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.PIPE)


def _normalized(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


@lru_cache(maxsize=4)
def _tree_entries(ref: str) -> dict[str, tuple[str, str, str]]:
    raw = _git("ls-tree", "-r", "-z", ref)
    result: dict[str, tuple[str, str, str]] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, path = record.split(b"\t", 1)
        mode, kind, blob = metadata.decode("ascii").split()
        result[path.decode("utf-8")] = (mode, kind, blob)
    return result


def _base_objects_available() -> bool:
    try:
        _git("cat-file", "-e", f"{BASE_MAIN}^{{commit}}")
    except subprocess.CalledProcessError:
        return False
    return True


def _source_edges(path: str) -> list[str]:
    if path == WORKFLOW:
        return [
            "pull_request(base=main,path-filtered) -> jobs.validate-commitment",
            "job -> exact PR-head checkout + exact base checkout, credentials disabled",
            "job -> Stage 5B4 base-revision declaration validator OR tooling-only focused tests",
            "declaration validation success -> conditional run-scoped timing-attestation artifact (90 days)",
        ]
    if path == "scripts/manage_win_either_half_campaign_commitment.py":
        return [
            "workflow declaration mode -> local Git diff/tree verification using shell=False Git subprocesses",
            "validator -> exact Stage 5B4/5B3 protocol and bundle checks",
            "validator -> runner.temp timing attestation only; no repository write",
        ]
    if path == "domain/win_either_half_campaign_commitment.py":
        return [
            "validator -> deterministic Stage 5B4 contract/deadline validation",
            "contract -> prospective_claim_authorized=false, markets disabled, no bet authority",
        ]
    if path == "tests/test_win_either_half_campaign_commitment.py":
        return ["tooling-only workflow path -> focused offline Stage 5B4 regression suite"]
    if path.startswith("artifacts/research-protocols/"):
        return ["Stage 5B4/5B3/5B2 validator -> exact committed protocol bytes"]
    if path.startswith("domain/"):
        return ["Stage 5B4 contract -> offline domain dependency"]
    if path.startswith("scripts/"):
        return ["Stage 5B4 workflow/test -> local tooling dependency"]
    return ["Stage 5B4 exact current source dependency"]


def _inventory_from_base() -> dict[str, Any]:
    require(_base_objects_available(), "exact B7 base-main Git objects are unavailable")
    entries = _tree_entries(BASE_MAIN)
    require(_git("rev-parse", f"{BASE_MAIN}^{{tree}}").decode().strip() == BASE_TREE,
            "B7 base tree identity drift")
    identities = []
    for path in SOURCE_PATHS:
        require(path in entries, "B7 source missing from exact base tree: " + path)
        mode, kind, blob = entries[path]
        require(kind == "blob" and mode in {"100644", "100755"},
                "B7 source is not a regular tracked blob: " + path)
        blob_raw = _git("cat-file", "blob", blob)
        worktree_raw = (ROOT / path).read_bytes()
        require(_git_blob(blob_raw) == blob,
                "B7 base-main blob bytes do not match the Git object identity: " + path)
        require(_sha(_normalized(worktree_raw)) == _sha(_normalized(blob_raw)),
                "B7 current worktree source differs from exact base-main content: " + path)
        identities.append({
            "path": path,
            "git_blob_sha1": blob,
            "normalized_source_sha256": _sha(_normalized(blob_raw)),
            "byte_size": len(blob_raw),
            "role": SOURCE_ROLES[path],
            "discovery_edges": _source_edges(path),
        })
    workflow = next(row for row in identities if row["path"] == WORKFLOW)
    require(workflow["git_blob_sha1"] == WORKFLOW_BLOB
            and workflow["normalized_source_sha256"] == WORKFLOW_SOURCE_SHA256,
            "B7 target workflow exact source identity drift")
    return boundary.seal({
        "schema_version": 1,
        "policy_id": INVENTORY_POLICY_ID,
        "repository": "Thabearr/ATHENA",
        "base_main_sha": BASE_MAIN,
        "base_tree_sha": BASE_TREE,
        "workflow_tree_sha1": WORKFLOW_TREE,
        "source_count": len(identities),
        "source_identities": identities,
    })


def _pinned_inventory_fallback() -> dict[str, Any]:
    raw = (ROOT / SOURCE_INVENTORY_PATH).read_bytes()
    value = json.loads(raw.decode("utf-8"))
    require(raw == boundary.canonical(value), "pinned B7 source inventory is not canonical")
    require(value.get("canonical_sha256") == SOURCE_INVENTORY_SHA,
            "pinned B7 source inventory identity drift")
    require(value.get("base_main_sha") == BASE_MAIN and value.get("base_tree_sha") == BASE_TREE,
            "pinned B7 source inventory base identity drift")
    rows = value.get("source_identities")
    require(type(rows) is list and value.get("source_count") == len(rows),
            "pinned B7 source inventory rows malformed")
    require({row.get("path") for row in rows} == set(SOURCE_PATHS),
            "pinned B7 source inventory scope drift")
    checkout = _tree_entries("HEAD")
    for row in rows:
        path = row["path"]
        require(path in checkout and checkout[path][1] == "blob",
                "B7 checked-out source missing in shallow checkout: " + path)
        raw_source = (ROOT / path).read_bytes()
        checkout_blob = _git("cat-file", "blob", checkout[path][2])
        require(_git_blob(checkout_blob) == row["git_blob_sha1"] == checkout[path][2],
                "B7 checked-out Git blob differs from pinned base blob: " + path)
        require(_sha(_normalized(raw_source)) == row["normalized_source_sha256"]
                and _sha(_normalized(checkout_blob)) == row["normalized_source_sha256"]
                and len(checkout_blob) == row["byte_size"],
                "B7 checked-out source identity drift: " + path)
    return value


def build_source_inventory() -> dict[str, Any]:
    return _inventory_from_base() if _base_objects_available() else _pinned_inventory_fallback()


def validate_source_inventory(value: dict[str, Any] | None = None) -> dict[str, Any]:
    value = boundary.read(SOURCE_INVENTORY_PATH) if value is None else value
    require((ROOT / SOURCE_INVENTORY_PATH).read_bytes() == boundary.canonical(value),
            "B7 source inventory is not canonical")
    require(value.get("canonical_sha256") == SOURCE_INVENTORY_SHA,
            "B7 source inventory canonical identity drift")
    require(value == build_source_inventory(),
            "B7 source inventory differs from exact base-main/current checked-out source")
    return value


def _workflow() -> dict[str, Any]:
    value = yaml.load((ROOT / WORKFLOW).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    require(type(value) is dict, "B7 target workflow YAML is not a mapping")
    return value


def _workflow_contract() -> dict[str, Any]:
    value = _workflow()
    triggers = value.get("on")
    require(type(triggers) is dict and set(triggers) == {"pull_request"},
            "Win-Either-Half trigger family changed")
    pr = triggers["pull_request"]
    require(pr.get("branches") == ["main"], "Win-Either-Half PR base branch contract changed")
    require(pr.get("paths") == list(EXPECTED_PR_PATHS), "Win-Either-Half PR path filter changed")
    require(value.get("permissions") == {"contents": "read"},
            "Win-Either-Half workflow permission changed")
    concurrency = value.get("concurrency") or {}
    require(concurrency.get("group") == "${{ github.workflow }}-${{ github.event.pull_request.number }}"
            and concurrency.get("cancel-in-progress") == "false",
            "Win-Either-Half concurrency contract changed")
    jobs = value.get("jobs") or {}
    require(set(jobs) == {"validate-commitment"}, "Win-Either-Half job topology changed")
    job = jobs["validate-commitment"]
    require("if" not in job and job.get("runs-on") == "ubuntu-latest",
            "Win-Either-Half direct job reachability changed")
    steps = job.get("steps") or []
    checkouts = [step for step in steps if step.get("uses") == "actions/checkout@v4"]
    require(len(checkouts) == 2, "Win-Either-Half exact head/base checkout topology changed")
    by_name = {step.get("name"): step for step in checkouts}
    require(set(by_name) == {"Checkout PR Head Revision", "Checkout Base Revision"},
            "Win-Either-Half checkout labels changed")
    head = by_name["Checkout PR Head Revision"].get("with") or {}
    base = by_name["Checkout Base Revision"].get("with") or {}
    require(head == {
        "ref": "${{ github.event.pull_request.head.sha }}",
        "path": "head", "fetch-depth": "0", "persist-credentials": "false",
    }, "Win-Either-Half PR-head checkout contract changed")
    require(base == {
        "ref": "${{ github.event.pull_request.base.sha }}",
        "path": "verifier", "fetch-depth": "1", "persist-credentials": "false",
    }, "Win-Either-Half base checkout contract changed")
    setup = next((s for s in steps if s.get("uses") == "actions/setup-python@v5"), None)
    require(setup is not None and (setup.get("with") or {}).get("python-version") == "3.12",
            "Win-Either-Half Python runtime contract changed")
    install = next((s for s in steps if s.get("name") == "Install Dependencies"), None)
    require(install is not None and "pip install -r verifier/requirements.txt" in install.get("run", "")
            and "pip install -r head/requirements.txt" in install.get("run", ""),
            "Win-Either-Half dependency-install contract changed")
    validate = next((s for s in steps if s.get("name") == "Run Commitment Deadline Validation"), None)
    require(validate is not None, "Win-Either-Half validation step missing")
    run = validate.get("run", "")
    required_fragments = (
        "SERVER_UTC=$(date -u +%Y-%m-%dT%H:%M:%S.%6NZ)",
        "ATTESTATION_PATH=\"${{ runner.temp }}/attestation-${{ github.run_id }}.json\"",
        "--validate-git-diff", "--repository-root head",
        "--base-sha \"${{ github.event.pull_request.base.sha }}\"",
        "--head-sha \"${{ github.event.pull_request.head.sha }}\"",
        "--github-event-name pull_request", "--attestation-output \"$ATTESTATION_PATH\"",
        "VALIDATION_MODE=DECLARATION_VALIDATION", "ATTESTATION_CREATED=true",
        "VALIDATION_MODE=TOOLING_ONLY_VALIDATION", "ATTESTATION_CREATED=false",
        "No timing qualification or attestation was created.",
        "Markets and all authorization remain disabled.",
        "Bootstrap PR cannot include real campaign declarations",
    )
    require(all(fragment in run for fragment in required_fragments),
            "Win-Either-Half declaration/tooling separation or timing contract changed")
    upload = next((s for s in steps if s.get("uses") == "actions/upload-artifact@v4"), None)
    require(upload is not None and upload.get("if") == "env.ATTESTATION_CREATED == 'true'",
            "Win-Either-Half timing-attestation upload guard changed")
    upload_with = upload.get("with") or {}
    require(upload_with == {
        "name": "win-either-half-campaign-commitment-${{ github.run_id }}",
        "path": "${{ env.ATTESTATION_PATH }}",
        "retention-days": "90",
        "if-no-files-found": "error",
    }, "Win-Either-Half timing-attestation artifact contract changed")
    return {
        "workflow_path": WORKFLOW,
        "trigger_keys": ["pull_request"],
        "pull_request": {
            "base_branches": ["main"],
            "paths": list(EXPECTED_PR_PATHS),
            "classification": "CONDITIONALLY_REACHABLE_PULL_REQUEST_PATH_FILTERED",
            "current": True,
            "spent_or_historical": False,
            "exact_PR_bound": False,
            "retired": False,
        },
        "direct_event_surface_requires_repository_caller": False,
        "permissions": {"contents": "read"},
        "checkouts": {
            "pr_head": head,
            "base_verifier": base,
            "credentials_persist": False,
        },
        "concurrency": {
            "group": "${{ github.workflow }}-${{ github.event.pull_request.number }}",
            "cancel_in_progress": False,
            "platform_auto_cancel_authority": "NO_WORKFLOW_CONFIGURED_AUTO_CANCEL",
            "external_actions_run_control_plane": "KNOWN_GITHUB_PLATFORM_CAPABILITY_NOT_REPOSITORY_PRODUCT_AUTHORITY",
        },
        "dependency_transport": "YES_PIP_ACTIONS_AND_PACKAGE_INDEX_TRANSPORT",
        "action_versions": {
            "checkout": "actions/checkout@v4",
            "setup_python": "actions/setup-python@v5",
            "upload_artifact": "actions/upload-artifact@v4",
        },
        "actions_control_plane": {
            "workflow_dispatch_declared": False,
            "repository_dispatch_declared": False,
            "issue_comment_declared": False,
            "schedule_declared": False,
            "manual_rerun_residual": (
                "KNOWN_GITHUB_ACTIONS_CONTROL_PLANE_CAPABILITY_REUSES_EXISTING_RUN_EVENT_AND_REVISION_"
                "NOT_A_DECLARED_REPOSITORY_TRIGGER_AND_NOT_NEW_PRODUCT_AUTHORITY"
            ),
            "b7_manual_reruns_performed": 0,
        },
        "timing_attestation_artifact": {
            "conditional": True,
            "guard": "env.ATTESTATION_CREATED == 'true'",
            "name": upload_with["name"],
            "retention_days": 90,
            "scope": "RUN_SCOPED_ACTIONS_ARTIFACT",
        },
    }


def _assert_no_application_network_imports() -> dict[str, Any]:
    paths = (
        "domain/win_either_half_campaign_commitment.py",
        "domain/win_either_half_capture_campaign.py",
        "domain/win_either_half_prospective_replay.py",
        "domain/win_either_half_pricing_source_qualification.py",
        "scripts/manage_win_either_half_campaign_commitment.py",
        "scripts/manage_win_either_half_capture_campaign.py",
        "scripts/freeze_evidence_baseline.py",
    )
    forbidden = {"requests", "httpx", "aiohttp", "urllib", "socket"}
    imported: dict[str, list[str]] = {}
    for path in paths:
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        require(not roots.intersection(forbidden),
                "Win-Either-Half validation source gained application network import: "
                + path + " -> " + ",".join(sorted(roots.intersection(forbidden))))
        imported[path] = sorted(roots)
    manager = (ROOT / "scripts/manage_win_either_half_campaign_commitment.py").read_text(encoding="utf-8")
    require('["git", "-C", str(cwd), *args]' in manager and "shell=False" in manager,
            "Stage 5B4 local Git subprocess boundary changed")
    return {
        "reviewed_paths": list(paths),
        "forbidden_application_network_roots": sorted(forbidden),
        "forbidden_import_hits": [],
        "local_git_subprocess": "READ_ONLY_GIT_CLI_WITH_SHELL_FALSE",
        "imports_by_path": imported,
    }


def _domain_authority_contract() -> dict[str, Any]:
    from domain.markets import MarketId
    from domain.model_status import MODEL_STATUS_REGISTRY, PricingAuthority, SelectionAuthority
    from domain import win_either_half_campaign_commitment as commitment

    commitment.assert_market_safety()
    require(commitment.PROSPECTIVE_CLAIM_AUTHORIZED is False
            and commitment.EVIDENCE_COUNTING_AUTHORIZED is False,
            "Stage 5B4 prospective/evidence-counting authority changed")
    require(commitment.GENERATED_SAFETY_CONTRACT == {
        "network_requests": False,
        "scraping": False,
        "browser_automation": False,
        "credential_use": False,
        "odds_collection": False,
        "provider_qualification": False,
        "offset_selection": False,
        "market_activation": False,
        "bet_decision": False,
    }, "Stage 5B4 generated safety contract changed")
    market_rows = {}
    for market in (MarketId.HOME_WIN_EITHER_HALF, MarketId.AWAY_WIN_EITHER_HALF):
        status = MODEL_STATUS_REGISTRY[market]
        require(status.pricing_authority is PricingAuthority.NOT_AUTHORIZED
                and status.selection_authority is SelectionAuthority.NOT_AUTHORIZED,
                "Win-Either-Half market unexpectedly gained pricing/selection authority")
        market_rows[market.value] = {
            "model_status": status.status.value,
            "pricing_authority": status.pricing_authority.value,
            "selection_authority": status.selection_authority.value,
            "campaign_status": "DISABLED",
        }
    return {
        "prospective_claim_authorized": False,
        "evidence_counting_authorized": False,
        "generated_safety": deepcopy(commitment.GENERATED_SAFETY_CONTRACT),
        "markets": market_rows,
        "selected_offset_seconds": None,
        "production_approval_authorized": False,
    }


def _architecture_invariants() -> dict[str, Any]:
    require(_git("rev-parse", "HEAD:.github/workflows").decode().strip() == WORKFLOW_TREE,
            "B7 changed the workflow tree")
    evolution = boundary.read("artifacts/architecture/p4_workflow_evolution_ledger_v1.json")
    retirement = boundary.read("artifacts/architecture/p4_3_workflow_retirement_ledger_v1.json")
    require(evolution.get("canonical_sha256") == EVOLUTION_SHA
            and len(evolution.get("transitions", [])) == 14,
            "B7 workflow evolution ledger identity/count drift")
    require(retirement.get("canonical_sha256") == RETIREMENT_SHA
            and len(retirement.get("retirements", [])) == 3,
            "B7 workflow retirement ledger identity/count drift")
    return {
        "workflow_tree_sha1": WORKFLOW_TREE,
        "workflow_diff_count": 0,
        "evolution_ledger_sha256": EVOLUTION_SHA,
        "transition_count": 14,
        "retirement_ledger_sha256": RETIREMENT_SHA,
        "retired_workflow_count": 3,
        "workflow_retirement_or_deletion_count": 0,
    }


def _review_row(contract: dict[str, Any], domain: dict[str, Any], network_scan: dict[str, Any]) -> dict[str, Any]:
    return {
        "identity": {"workflow_path": WORKFLOW, "trigger_kind": "pull_request"},
        "trigger_contract": {
            "physical_trigger": "pull_request",
            "reachability": deepcopy(contract["pull_request"]),
            "repository_caller_requirement": "NOT_APPLICABLE_DIRECT_GITHUB_PULL_REQUEST_EVENT",
        },
        "permissions_and_credentials": {
            "permissions": {"contents": "read"},
            "checkout_persist_credentials": False,
            "github_repository_write_authority": "NO_SOURCE_PATH_AND_CREDENTIALS_DISABLED_CONTENTS_READ_ONLY",
        },
        "concurrency_cancellation": deepcopy(contract["concurrency"]),
        "action_versions": deepcopy(contract["action_versions"]),
        "actions_control_plane": deepcopy(contract["actions_control_plane"]),
        "network_authority": {
            "workflow_infrastructure_network": "YES",
            "build_toolchain_network": contract["dependency_transport"],
            "application_validation_network_imports": "NONE_IN_REVIEWED_STAGE_5B1_TO_5B4_SOURCE_PATH",
            "current_provider_acquisition": "NONE_IN_VALIDATION_PATH",
            "source_scan": network_scan,
        },
        "local_filesystem_and_process_authority": {
            "runner_workspace_write": "YES_TOOLING_TEST_OUTPUT_AND_LOCAL_GIT_CHECKOUT_FILES",
            "runner_temp_write": "CONDITIONAL_TIMING_ATTESTATION_ONLY",
            "local_git_subprocess": "YES_READ_ONLY_GIT_CLI_SHELL_FALSE",
            "persistent_canonical_database_write": "NO_SOURCE_PATH",
        },
        "write_authority": {
            "github_actions_artifact_write_authority": "YES_CONDITIONAL_RUN_SCOPED_TIMING_ATTESTATION",
            "artifact_retention_days": 90,
            "github_repository_write_authority": "NO_SOURCE_PATH_AND_CREDENTIALS_DISABLED_CONTENTS_READ_ONLY",
            "external_storage_write_authority": "NO_SOURCE_PATH",
            "release_publish_authority": "NO_SOURCE_PATH",
        },
        "notification_authority": {
            "github_step_summary": "YES_RUN_SCOPED",
            "stdout_stderr": "YES_RUN_SCOPED",
            "external_email_or_message_transport": "NO_SOURCE_PATH",
        },
        "attestation_authority": {
            "declaration_mode_can_create_timing_attestation": True,
            "tooling_only_mode_creates_attestation": False,
            "bootstrap_mode_creates_attestation": False,
            "attestation_meaning": "TIMING_QUALIFICATION_ONLY",
            "prospective_claim_authorized": False,
            "evidence_counting_authorized": False,
            "production_approval_authorized": False,
        },
        "model_market_delivery_and_wager": {
            "domain_authority": domain,
            "production_model_authority": "NO",
            "production_probability_authority": "NO",
            "production_selection_authority": "NO",
            "provider_calls": 0,
            "share_code_create_or_reload": 0,
            "login_actions": 0,
            "cookie_actions": 0,
            "wallet_actions": 0,
            "stake_actions": 0,
            "wager_actions": 0,
        },
        "product_release_disposition": {
            "capability": "CURRENT_RETAINED_STAGE_5B4_RESEARCH_GOVERNANCE_GATE",
            "end_user_runtime_execution": "NOT_THIS_WORKFLOW",
            "production_market_activation": "NO",
            "retirement_authorized": False,
        },
        "status": "RESOLVED",
        "blocker": None,
    }


def authenticated_historical_a2_v9() -> dict[str, Any]:
    """Authenticate latest corpus first, then exact immutable B7 generation.

    A later local-shell inventory is not a rewrite of the B7 review. A broken
    latest generation still fails closed; this is never a fallback selector.
    """
    boundary.authenticate_inventory()
    value = boundary.read_generation(boundary.inventory_generation_path(9))
    require(value.get("canonical_sha256") == A2_V9_SHA,
            "immutable B7 A2 V9 identity drift")
    return value


def build_receipt() -> dict[str, Any]:
    parent = completion_v9.validate_receipt()
    require(parent.get("canonical_sha256") == COMPLETION_V9_SHA,
            "immutable Completion V9 identity drift")
    inherited = parent["unreviewed_authority_surfaces"]
    require(len(inherited) == 1
            and {(row["workflow_path"], row["trigger_kind"]) for row in inherited} == {TARGET},
            "B7 predecessor must contain exactly the Win-Either-Half pull_request surface")
    require(parent["checkpoint_criteria"]["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False
            and parent["checkpoint_criteria"]["no_unknown_current_artifact_or_notification_authority"] is False,
            "B7 predecessor criteria 11/14 must both remain false")
    require(parent["remaining_blocker_ids"] == [
        "all_retained_workflow_authority_and_dynamic_reachability_review_complete",
        "no_unknown_current_artifact_or_notification_authority",
    ], "B7 predecessor blocker set drift")
    require(parent["checkpoint_e_status"] == parent["p4_4_status"] == "INCOMPLETE",
            "B7 predecessor must be incomplete")
    b6_receipt = b6.validate_receipt()
    require(b6_receipt.get("canonical_sha256") == B6_RECEIPT_SHA,
            "immutable B6 receipt identity drift")
    inventory = validate_source_inventory()
    a2_current = authenticated_historical_a2_v9()
    require(a2_current.get("generation") == 9,
            "B7 requires its immutable A2 generation V9")
    require(a2_current.get("predecessor_inventory") == {
        "path": A2_V8_PATH,
        "canonical_sha256": A2_V8_SHA,
        "generation": 8,
        "rewritten": False,
    }, "A2 V9 predecessor binding is not exact V8")
    contract = _workflow_contract()
    network_scan = _assert_no_application_network_imports()
    domain = _domain_authority_contract()
    invariants = _architecture_invariants()
    row = _review_row(contract, domain, network_scan)
    require(row["status"] == "RESOLVED" and row["blocker"] is None,
            "B7 final row is not fully resolved")
    require(ZERO_ACTIONS == {key: 0 for key in ZERO_ACTIONS},
            "B7 live actions must remain zero")
    return boundary.seal({
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository": "Thabearr/ATHENA",
        "master_issue": 337,
        "observed_at": OBSERVED_AT,
        "base": {"branch": "main", "commit_sha": BASE_MAIN, "tree_sha": BASE_TREE},
        "post_445_tests": deepcopy(POST_445_TESTS),
        "source_review_counter_while_open": SOURCE_REVIEW_COUNTER_WHILE_OPEN,
        "source_review_counter_if_owner_merges": SOURCE_REVIEW_COUNTER_IF_OWNER_MERGES,
        "mandatory_governing_source_reread_after_b7_merge": "NO",
        "predecessors": {
            "completion_v9": {"path": COMPLETION_V9_PATH, "canonical_sha256": COMPLETION_V9_SHA, "rewritten": False},
            "b6_receipt": {"path": B6_RECEIPT_PATH, "canonical_sha256": B6_RECEIPT_SHA, "rewritten": False},
            "a2_generation_8": {"path": A2_V8_PATH, "canonical_sha256": A2_V8_SHA, "generation": 8, "rewritten": False},
            "a2_generation_9": {"path": boundary.inventory_generation_path(9),
                                "canonical_sha256": a2_current["canonical_sha256"],
                                "generation": 9,
                                "predecessor": deepcopy(a2_current["predecessor_inventory"]),
                                "rewritten": False},
        },
        "target_count": 1,
        "resolved_target_count": 1,
        "partial_target_count": 0,
        "global_unknown_before": 1,
        "global_unknown_after": 0,
        "target_keys": [[WORKFLOW, "pull_request"]],
        "review_rows": [row],
        "remaining_unreviewed_surfaces": [],
        "workflow_contract": contract,
        "source_inventory": {
            "path": SOURCE_INVENTORY_PATH,
            "canonical_sha256": inventory["canonical_sha256"],
            "source_count": inventory["source_count"],
        },
        "workflow_evolution_and_retirement_invariants": invariants,
        "workflow_count": parent["workflow_count"],
        "trigger_surface_count": parent["trigger_surface_count"],
        "historical_missing_artifact_relation_count": parent["historical_missing_artifact_relation_count"],
        "live_missing_artifact_relation_count": parent["live_missing_artifact_relation_count"],
        "retention_blockers_A_B_C_D": parent["retention_blockers_A_B_C_D"],
        "criterion_11": True,
        "criterion_14": True,
        "checkpoint_e_status": "COMPLETE",
        "p4_4_status": "COMPLETE",
        "workflow_edit_count": 0,
        "trigger_edit_count": 0,
        "workflow_retirement_count": 0,
        "workflow_deletion_count": 0,
        "caller_migration_count": 0,
        "actions": deepcopy(ZERO_ACTIONS),
        "terminal": "CORE_01D_WIN_EITHER_HALF_TRIGGER_AUTHORITY_B7_REVIEW_READY_1_RESOLVED_ZERO_REMAINING_DO_NOT_MERGE",
    })


def validate_receipt(value: dict[str, Any] | None = None) -> dict[str, Any]:
    value = boundary.read(RECEIPT_PATH) if value is None else value
    require((ROOT / RECEIPT_PATH).read_bytes() == boundary.canonical(value),
            "B7 receipt is not canonical")
    expected = build_receipt()
    require(value == expected, "B7 receipt differs from exact source and Completion V9 overlay")
    require(value["target_count"] == value["resolved_target_count"] == 1
            and value["partial_target_count"] == 0
            and value["global_unknown_before"] == 1
            and value["global_unknown_after"] == 0
            and value["remaining_unreviewed_surfaces"] == [],
            "B7 final scope/count derivation drift")
    require(value["criterion_11"] is True and value["criterion_14"] is True
            and value["checkpoint_e_status"] == value["p4_4_status"] == "COMPLETE",
            "B7 must close criteria 11/14 and Checkpoint E/P4.4")
    require(value["actions"] == ZERO_ACTIONS,
            "B7 performed or claimed a prohibited live action")
    return value


def audit() -> dict[str, Any]:
    value = validate_receipt()
    return {
        "result": "PASS",
        "receipt_sha256": value["canonical_sha256"],
        "source_inventory_sha256": value["source_inventory"]["canonical_sha256"],
        "target_count": 1,
        "resolved_target_count": 1,
        "global_unknown_before": 1,
        "global_unknown_after": 0,
        "remaining": [],
        "checkpoint_e": "COMPLETE",
        "p4_4": "COMPLETE",
        "criterion_11": True,
        "criterion_14": True,
        "terminal": value["terminal"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-source-inventory", action="store_true")
    parser.add_argument("--write-receipt", action="store_true")
    args = parser.parse_args()
    if args.write_source_inventory:
        value = _inventory_from_base()
        (ROOT / SOURCE_INVENTORY_PATH).write_bytes(boundary.canonical(value))
        print(value["canonical_sha256"])
    elif args.write_receipt:
        validate_source_inventory()
        value = build_receipt()
        (ROOT / RECEIPT_PATH).write_bytes(boundary.canonical(value))
        print(value["canonical_sha256"])
    else:
        print(json.dumps(audit(), sort_keys=True))


if __name__ == "__main__":
    main()
