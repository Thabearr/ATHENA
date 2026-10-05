"""Authenticate the bounded PORT-02C native-runtime trigger review (B6).

This is a source and read-only GitHub metadata review. It does not dispatch,
rerun, cancel, download an artifact, contact a provider, or execute a native
qualification workflow.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from functools import lru_cache
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any

import yaml

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_frozen_artifact_replay_authority_b5 as b5
from scripts import audit_core_01d_checkpoint_e_completion_v8 as completion_v8

ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "ATHENA_CORE_01D_PORT02C_TRIGGER_AUTHORITY_B6_V1"
INVENTORY_POLICY_ID = "ATHENA_CORE_01D_PORT02C_TRIGGER_AUTHORITY_B6_SOURCE_INVENTORY_V1"
BASE_MAIN = "5e362343b5d7423e5634186b52c934437445dd12"
BASE_TREE = "704c7f8e6229919487befca590e69600da8866a3"
WORKFLOW_TREE = "9b08653f1a12bb1b3d964fbd910396ff955740da"
EVOLUTION_SHA = "73e1eb3fe6593558c821600dd0f103353d45c15a139ab470a996c7cbb35da531"
RETIREMENT_SHA = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
COMPLETION_V8_PATH = completion_v8.RECEIPT_PATH
COMPLETION_V8_SHA = "b096669da119a2c82ea4bb9fdeb2d2c10e417ecf54c834a621f8e643b6da8c8a"
B5_RECEIPT_PATH = b5.RECEIPT_PATH
B5_RECEIPT_SHA = "9ec2f8df2f0fbf765444f414302c7db16deeda71135950354e60eeb59e4fd440"
B5_SOURCE_INVENTORY_PATH = b5.SOURCE_INVENTORY_PATH
B5_SOURCE_INVENTORY_SHA = "c383ca73f30bc673662bdd392548c9f5f80ec25acab44e0a50ab51faf0997654"
A2_V7_PATH = "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v7.json"
A2_V7_SHA = "fdb9534212e814f6ac5a8a5c6f52af73354eef0029e3dbb5466dc32d6f252794"
PORT_RECEIPT_PATH = "artifacts/architecture/port_02_native_runtime_v1.json"
PORT_RECEIPT_SHA = "aaf1f684fa398effcff8e2135897ec669c353b20a34b966fb0d439eabb71a305"
PORT_RECEIPT_BLOB = "d21ff8cef38d6a06045f200bcdef981fa5034118"
PORT_WORKFLOW = ".github/workflows/port-02c-native-runtime.yml"
PORT_WORKFLOW_SHA = "5b2f4f8ade4f7b45b0db43023085ee0762b2e178564c6ecebd2a632932e8e07b"
PORT_WORKFLOW_BLOB = "29085814892b94b67435e5869ac60f316fb56e36"
SOURCE_INVENTORY_PATH = "tests/fixtures/core_01d/port02c-trigger-authority-b6-source-inventory-v1.json"
SOURCE_INVENTORY_SHA = "f0e3bbd523c0a75d47215d2b4f6cd732409c559f080d9391a6ae7520387368c6"
RECEIPT_PATH = "tests/fixtures/core_01d/core-01d-port02c-trigger-authority-b6-v1.json"
OBSERVED_AT = "2026-10-04T22:55:33Z"
SOURCE_REVIEW_RESET_COMMENT = 5981669839
POST_444_TESTS = {
    "run_id": 37212524494,
    "workflow": "Tests",
    "event": "push",
    "branch": "main",
    "head_sha": BASE_MAIN,
    "status": "completed",
    "conclusion": "success",
    "syntax": "SUCCESS",
    "shards_1_to_8": "SUCCESS",
    "aggregate": "SUCCESS",
}
TARGETS = (
    (PORT_WORKFLOW, "pull_request"),
    (PORT_WORKFLOW, "workflow_dispatch"),
)
WIN_EITHER_HALF = (
    ".github/workflows/validate-win-either-half-campaign-commitment.yml",
    "pull_request",
)
EXPECTED_UNRESOLVED = set((*TARGETS, WIN_EITHER_HALF))
EXPECTED_PR_PATHS = (
    "packaging/**",
    "scripts/build_dev_bundle.py",
    "scripts/qualify_port_02_native_runtime.py",
    "scripts/audit_port_02_native_runtime.py",
    "scripts/port_02c_offline_composed_replay.py",
    "scripts/port_02c_git_free_launch.py",
    "tests/fixtures/port_02c_run_36345657852/**",
    "tests/native/**",
    "run_desktop.py",
    "artifacts/architecture/port_02_native_runtime_v1.json",
    PORT_WORKFLOW,
)
FIXTURE_ROOT = "tests/fixtures/port_02c_run_36345657852"
FIXTURE_MANIFEST_PATH = FIXTURE_ROOT + "/fixture-manifest.json"
FIXTURE_MANIFEST_SHA = "2fa98f3b43a48e752c05a5b3cce9bce307eddedef5eebf6cadd9dc04ee706372"
FIXTURE_PROTOCOL = {
    "fixture_manifest_sha256": FIXTURE_MANIFEST_SHA,
    "time_policy_id": "ATHENA_PORT02C_EARLIEST_COMPLETE_RETAINED_SOURCE_EVALUATION_V1",
    "replay_scope": "RETAINED_SOURCE_DIRECT_FRESH_PRICE_ROUTER_PORTFOLIO_QUALIFICATION",
    "qualification_sha256": "ca520f8067e23b2a583ce348f22309e8752610aa5e1b0551c778d9272aed9e5a",
    "historical_sha256": "3879c81646f2d3385462824d3477bceaeb4b5e1ed09369ee41a59539f638040d",
    "source_head_sha": "eae938a268707f07db3da2d551ea589782902b1c",
    "source_artifact_id": 10940728036,
    "source_artifact_zip_sha256": "f0618654b49fcd7a6a2df95260025b6c655da5aefb477102696a812e9930b18a",
}

# Immutable contracts and source reachable from the two event surfaces. The
# retained fixture members are added from the byte-pinned fixture manifest.
BASE_SOURCE_PATHS = (
    PORT_WORKFLOW,
    "scripts/build_dev_bundle.py",
    "scripts/qualify_port_02_native_runtime.py",
    "scripts/port_02c_offline_composed_replay.py",
    "scripts/port_02c_git_free_launch.py",
    "scripts/audit_port_02_native_runtime.py",
    "scripts/port_02c_build_config.py",
    "requirements.txt",
    "packaging/build-requirements.txt",
    "packaging/linux/athena-port02c.spec",
    "packaging/windows/athena-port02c.spec",
    "run_desktop.py",
    "runtime/release_identity.py",
    "runtime/source_identity.py",
    "runtime/resources.py",
    "runtime/worker_launcher.py",
    "runtime/worker_entry.py",
    "domain/run_contracts.py",
    "domain/component_authority_registry.py",
    "domain/canonical_core.py",
    "domain/current_shadow_runtime_bindings.py",
    "domain/current_shadow_canonical_core_adapter.py",
    "domain/_current_shadow_quote_binding.py",
    "domain/current_shadow_all_market_price_all.py",
    "domain/current_shadow_all_market_router.py",
    "domain/current_shadow_all_market_portfolio.py",
    "domain/current_shadow_fresh_reprice_runtime.py",
    "domain/current_shadow_sportybet_pc_upcoming_reconciliation.py",
    "domain/current_shadow_sportybet_pc_upcoming_discovery.py",
    "domain/sportybet_live_event_quote_evidence.py",
    "domain/fotmob_data_matches_capture.py",
    "domain/current_fotmob_fixture_review_policy.py",
    "domain/fotmob_fixture_catalog_handoff.py",
    "domain/current_all_market_shadow_probability_settlement.py",
    "domain/current_fotmob_latest_durable_fresh_history.py",
    "domain/_current_shadow_price_core.py",
    "domain/provider_market_semantics.py",
    "domain/price_all.py",
    "domain/market_router.py",
    "domain/portfolio_optimizer.py",
    "domain/sportybet_share_code.py",
    "scripts/issue_current_fotmob_reviewed_source.py",
    "config/architecture/component-authority-registry-v1.json",
    "config/architecture/main-shadow-authority-parity-v1.json",
    "config/architecture/architecture-boundary-policy-v1.json",
    "config/release_manifest.schema.json",
    "config/model_weights.json",
    "database/migrations/002_add_elo_columns.sql",
    "ui/index.html",
    "ui/app.js",
    "ui/styles.css",
    "artifacts/research-manifests/sportybet-ng-early-payout-settlement-source-evidence-v1.json",
    "artifacts/architecture/port_02_installed_release_identity_v1.json",
    "artifacts/architecture/port_02_worker_launch_boundary_v1.json",
    "artifacts/architecture/p4_4r_shadow_runtime_composition_stabilization_v1.json",
    "artifacts/architecture/p4_4s_canonical_adapter_bound_context_builder_v1.json",
    "artifacts/architecture/port_02c_native_runtime_workflow_add_v1.json",
    "artifacts/architecture/p4_workflow_evolution_snapshots/port_02c_native_runtime_slice_v1.json",
    PORT_RECEIPT_PATH,
    "artifacts/architecture/p4_workflow_evolution_ledger_v1.json",
    "artifacts/architecture/p4_3_workflow_retirement_ledger_v1.json",
)

SOURCE_EDGES: dict[str, list[str]] = {
    PORT_WORKFLOW: [
        "pull_request/workflow_dispatch -> jobs.native-slice (same unconditional job body)",
        "jobs.native-slice -> actions/checkout@v4 + actions/setup-python@v5 + pip requirements",
        "jobs.native-slice -> scripts/build_dev_bundle.py --freeze -> installed qualifier",
        "jobs.native-slice -> actions/upload-artifact@v4 (run-scoped evidence, 14 days)",
    ],
    "scripts/build_dev_bundle.py": [
        "workflow -> build(repo=verified DevelopmentCheckout, platform_tag, disposable output, freeze=True)",
        "build -> runtime.release_identity.verify_development_checkout",
        "build -> runtime.source_identity.read_tracked_head_blob via source/resource identity",
        "build -> port_02c_build_config allowlists and retained qualification fixtures",
        "build --freeze -> local PyInstaller subprocess (no provider/network call in builder)",
    ],
    "scripts/qualify_port_02_native_runtime.py": [
        "workflow -> installed qualifier executable -> _NetworkSentinel.install",
        "qualify -> runtime.release_identity + runtime.resources + runtime.worker_launcher",
        "qualify -> domain.canonical_core.resolve_canonical_core + current_shadow_runtime_bindings",
        "qualify -> scripts.port_02c_offline_composed_replay.run_replay",
        "qualify -> no-wager OFFLINE_IDENTITY_PROBE RunRequest and qualification evidence",
    ],
    "scripts/port_02c_offline_composed_replay.py": [
        "qualifier -> verify exact retained fixture manifest and local retained bytes",
        "replay -> historical capture verification with require_network_acquisition_performed=True",
        "replay -> nested network/provider guards -> canonical source verification",
        "replay -> local Price-all -> Router -> fresh reprice -> Portfolio composition",
        "replay -> qualification-only retained diagnostic; no production/current-history authority",
    ],
    "scripts/port_02c_git_free_launch.py": [
        "workflow -> sanitized Git-free PATH -> shell=False local qualifier subprocess",
    ],
    "runtime/worker_launcher.py": [
        "qualifier -> exact InstalledRelease + writable roots -> OFFLINE_IDENTITY_PROBE worker process",
        "worker -> run-scoped command/probe/provenance artifacts under configured writable roots",
    ],
    "domain/canonical_core.py": [
        "qualifier -> canonical SHADOW owner resolution from installed registry",
        "canonical owner resolution includes delivery_share_code_transport owner; no transport call follows",
    ],
    "domain/current_shadow_runtime_bindings.py": [
        "retained replay -> pinned Current Shadow Price-all/Router/Portfolio bindings",
    ],
    FIXTURE_MANIFEST_PATH: [
        "port_02c_build_config.QUALIFICATION_FIXTURE_PREFIXES -> exact retained manifest and listed members",
        "offline replay -> fixture-manifest SHA and exact file byte identities",
    ],
    PORT_RECEIPT_PATH: [
        "immutable PORT-02C evidence contract -> release/runtime and qualification dispositions",
    ],
}

SOURCE_ROLES: dict[str, str] = {
    PORT_WORKFLOW: "current_target_workflow_and_physical_trigger_contract",
    "scripts/build_dev_bundle.py": "verified_checkout_allowlisted_local_bundle_builder",
    "scripts/qualify_port_02_native_runtime.py": "installed_runtime_qualification_entrypoint_and_transport_sentinel",
    "scripts/port_02c_offline_composed_replay.py": "qualification_only_retained_source_replay",
    "scripts/port_02c_git_free_launch.py": "local_git_free_process_launcher",
    "scripts/audit_port_02_native_runtime.py": "immutable_PORT_receipt_contract_auditor",
    "scripts/port_02c_build_config.py": "allowlisted_release_resources_and_fixture_protocol",
    "runtime/release_identity.py": "verified_development_and_installed_release_identity",
    "runtime/source_identity.py": "exact_local_Git_HEAD_read_identity",
    "runtime/resources.py": "read_only_release_resources_and_separate_writable_roots",
    "runtime/worker_launcher.py": "bounded_installed_native_worker_launch_and_run_scoped_artifacts",
    "domain/canonical_core.py": "canonical_SHADOW_owner_resolution_and_authority_manifest",
    "domain/component_authority_registry.py": "source_controlled_component_owner_registry",
    "domain/current_shadow_runtime_bindings.py": "retained_local_composition_bindings",
    PORT_RECEIPT_PATH: "immutable_PORT02C_qualification_and_product_disposition_receipt",
    FIXTURE_MANIFEST_PATH: "immutable_retained_qualification_fixture_protocol_manifest",
    "artifacts/architecture/p4_workflow_evolution_ledger_v1.json": "immutable_workflow_evolution_invariant",
    "artifacts/architecture/p4_3_workflow_retirement_ledger_v1.json": "immutable_workflow_retirement_invariant",
}

ZERO_ACTIONS = {
    "manual_port02c_dispatches": 0,
    "port02c_reruns": 0,
    "workflow_cancellations": 0,
    "artifact_payload_downloads": 0,
    "provider_requests": 0,
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


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _normalized(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _canonical(value: Any) -> bytes:
    return boundary.canonical(value)


def _read_json(path: str) -> dict[str, Any]:
    return boundary.read(path)


@lru_cache(maxsize=1)
def _parse_tree_entries(raw: bytes) -> dict[str, tuple[str, str, str]]:
    entries: dict[str, tuple[str, str, str]] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, path = record.split(b"\t", 1)
        mode, kind, blob = metadata.decode("ascii").split()
        entries[path.decode("utf-8")] = (mode, kind, blob)
    return entries


@lru_cache(maxsize=1)
def _checkout_tree_entries() -> dict[str, tuple[str, str, str]]:
    """Read the checked-out snapshot, which exists even in depth-one PR CI."""
    return _parse_tree_entries(_git("ls-tree", "-r", "-z", "HEAD"))


@lru_cache(maxsize=1)
def _base_tree_entries() -> dict[str, tuple[str, str, str]]:
    try:
        return _parse_tree_entries(_git("ls-tree", "-r", "-z", BASE_MAIN))
    except subprocess.CalledProcessError:
        # GitHub's natural pull_request checkout is a depth-one synthetic merge
        # commit. It contains the reviewed snapshot but omits the pinned base
        # commit object. The source inventory was sealed before the PR and its
        # identity is itself pinned here; verify every inventoried source against
        # both that baseline identity and the available checkout tree.
        raw = (ROOT / SOURCE_INVENTORY_PATH).read_bytes()
        value = json.loads(raw.decode("utf-8"))
        require(raw == _canonical(value), "pinned B6 source inventory is not canonical")
        require(value.get("canonical_sha256") == SOURCE_INVENTORY_SHA,
                "pinned B6 source inventory identity drift")
        require(value.get("base_main_sha") == BASE_MAIN and value.get("base_tree_sha") == BASE_TREE,
                "pinned B6 source inventory base identity drift")
        rows = value.get("source_identities")
        require(type(rows) is list and value.get("source_count") == len(rows),
                "pinned B6 source inventory rows are malformed")
        require(all(type(row) is dict for row in rows),
                "pinned B6 source inventory row is malformed")
        expected_paths = set(required_source_paths())
        require({row.get("path") for row in rows} == expected_paths,
                "pinned B6 source inventory scope drift")
        checkout = _checkout_tree_entries()
        entries: dict[str, tuple[str, str, str]] = {}
        for row in rows:
            path = row["path"]
            mode_kind_blob = checkout.get(path)
            require(mode_kind_blob is not None and mode_kind_blob[1] == "blob"
                    and mode_kind_blob[0] in {"100644", "100755"},
                    "required B6 source is not a checked-out regular Git blob: " + path)
            mode, _kind, blob = mode_kind_blob
            require(blob == row.get("git_blob_sha1"),
                    "checked-out B6 source differs from authenticated base blob: " + path)
            source = (ROOT / path).read_bytes()
            require(hashlib.sha1(b"blob " + str(len(source)).encode("ascii") + b"\0" + source).hexdigest()
                    == blob,
                    "checked-out B6 source bytes differ from Git blob: " + path)
            require(_sha(_normalized(source)) == row.get("normalized_source_sha256")
                    and len(source) == row.get("byte_size")
                    and row.get("role") == _source_role(path)
                    and row.get("discovery_edges") == _source_edges(path),
                    "checked-out B6 source identity or classification drift: " + path)
            entries[path] = (mode, "blob", blob)
        return entries


def _fixture_manifest() -> dict[str, Any]:
    raw = (ROOT / FIXTURE_MANIFEST_PATH).read_bytes()
    require(_sha(raw) == FIXTURE_MANIFEST_SHA, "retained PORT-02C fixture manifest SHA drift")
    value = json.loads(raw.decode("utf-8"))
    require(raw == _canonical(value), "retained PORT-02C fixture manifest is not canonical")
    files = value.get("files")
    require(type(files) is list and files, "retained fixture manifest files are missing")
    expected = {FIXTURE_MANIFEST_PATH}
    for row in files:
        require(type(row) is dict and type(row.get("staged_path")) is str,
                "retained fixture manifest member row is malformed")
        relative = PurePosixPath(row["staged_path"])
        require(not relative.is_absolute() and ".." not in relative.parts,
                "retained fixture manifest member escapes its root")
        path = f"{FIXTURE_ROOT}/{relative.as_posix()}"
        require(path not in expected, "duplicate retained fixture manifest member")
        expected.add(path)
        member = ROOT / path
        require(member.is_file() and not member.is_symlink(), "retained fixture member is missing or linked")
        payload = member.read_bytes()
        require(len(payload) == row.get("byte_size") and _sha(payload) == row.get("byte_sha256"),
                "retained fixture member bytes differ from the exact manifest")
    actual = {path.relative_to(ROOT).as_posix() for path in (ROOT / FIXTURE_ROOT).rglob("*")
              if path.is_file()}
    require(actual == expected, "retained fixture directory has unexpected or missing files")
    return value


def required_source_paths() -> tuple[str, ...]:
    manifest = _fixture_manifest()
    fixture_members = [f"{FIXTURE_ROOT}/{row['staged_path']}" for row in manifest["files"]]
    return tuple(sorted(set(BASE_SOURCE_PATHS) | {FIXTURE_MANIFEST_PATH} | set(fixture_members)))


def _source_role(path: str) -> str:
    if path.startswith(FIXTURE_ROOT + "/"):
        return "exact_retained_qualification_fixture_member"
    if path in SOURCE_ROLES:
        return SOURCE_ROLES[path]
    if path.startswith("domain/"):
        return "canonical_or_retained_runtime_business_logic_dependency"
    if path.startswith("runtime/"):
        return "native_runtime_identity_resource_or_worker_dependency"
    if path.startswith("artifacts/architecture/"):
        return "immutable_PORT_02_runtime_contract_or_lineage"
    if path.startswith("packaging/"):
        return "native_packaging_entrypoint"
    if path.startswith("scripts/"):
        return "PORT02C_qualification_or_review_dependency"
    return "PORT02C_reviewed_source_dependency"


def _source_edges(path: str) -> list[str]:
    if path in SOURCE_EDGES:
        return SOURCE_EDGES[path]
    if path.startswith(FIXTURE_ROOT + "/"):
        return [
            "scripts.build_dev_bundle._discover_qualification_files -> exact retained fixture staging",
            "scripts.port_02c_offline_composed_replay.verify_fixture_manifest -> local byte reconstruction",
        ]
    if path.startswith("artifacts/architecture/"):
        return ["PORT-02C builder, runtime, or receipt contract -> immutable source-controlled evidence"]
    if path.startswith("packaging/"):
        return ["workflow -> scripts.build_dev_bundle.py --freeze -> platform-specific PyInstaller spec"]
    if path.startswith("domain/"):
        return ["qualifier/replay -> retained canonical source verification and local composition"]
    if path.startswith("runtime/"):
        return ["builder or qualifier -> verified local identity, installed resources, worker process"]
    return ["PORT-02C exact current source dependency"]


def build_source_inventory() -> dict[str, Any]:
    entries = _base_tree_entries()
    identities = []
    for path in required_source_paths():
        require(path in entries and entries[path][1] == "blob", "required B6 source is not a base-main blob: " + path)
        mode, _kind, blob = entries[path]
        require(mode in {"100644", "100755"}, "required B6 source has unsupported Git mode: " + path)
        raw = (ROOT / path).read_bytes()
        git_blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
        require(git_blob == blob, "B6 current worktree source differs from exact main bytes: " + path)
        identities.append({
            "path": path,
            "git_blob_sha1": blob,
            "normalized_source_sha256": _sha(_normalized(raw)),
            "byte_size": len(raw),
            "role": _source_role(path),
            "discovery_edges": _source_edges(path),
        })
    workflow = next(row for row in identities if row["path"] == PORT_WORKFLOW)
    require(workflow["git_blob_sha1"] == PORT_WORKFLOW_BLOB
            and workflow["normalized_source_sha256"] == PORT_WORKFLOW_SHA,
            "PORT-02C current workflow source identity drift")
    receipt = _read_json(PORT_RECEIPT_PATH)
    require(receipt.get("canonical_sha256") == PORT_RECEIPT_SHA,
            "immutable PORT-02C receipt canonical identity drift")
    require(entries[PORT_RECEIPT_PATH][2] == PORT_RECEIPT_BLOB,
            "immutable PORT-02C receipt Git blob identity drift")
    require(receipt.get("qualification", {}).get("fixture_manifest_sha256") == FIXTURE_MANIFEST_SHA,
            "PORT-02C receipt no longer binds the retained fixture manifest")
    import scripts.port_02c_offline_composed_replay as replay
    require(replay.FIXTURE_MANIFEST_SHA256 == FIXTURE_MANIFEST_SHA
            and replay.TIME_POLICY_ID == FIXTURE_PROTOCOL["time_policy_id"]
            and replay.REPLAY_SCOPE == FIXTURE_PROTOCOL["replay_scope"]
            and replay.QUALIFICATION_SHA == FIXTURE_PROTOCOL["qualification_sha256"]
            and replay.HISTORICAL_SHA == FIXTURE_PROTOCOL["historical_sha256"]
            and replay.SOURCE_HEAD == FIXTURE_PROTOCOL["source_head_sha"]
            and replay.ZIP_SHA == FIXTURE_PROTOCOL["source_artifact_zip_sha256"],
            "retained composed-replay protocol identity drift")
    return boundary.seal({
        "schema_version": 1,
        "policy_id": INVENTORY_POLICY_ID,
        "repository": "Thabearr/ATHENA",
        "base_main_sha": BASE_MAIN,
        "base_tree_sha": BASE_TREE,
        "workflow_tree_sha1": WORKFLOW_TREE,
        "port_receipt": {"path": PORT_RECEIPT_PATH, "canonical_sha256": PORT_RECEIPT_SHA,
                         "git_blob_sha1": PORT_RECEIPT_BLOB},
        "fixture_protocol": FIXTURE_PROTOCOL,
        "source_count": len(identities),
        "source_identities": identities,
    })


def validate_source_inventory(value: dict[str, Any] | None = None) -> dict[str, Any]:
    value = boundary.read(SOURCE_INVENTORY_PATH) if value is None else value
    require((ROOT / SOURCE_INVENTORY_PATH).read_bytes() == _canonical(value),
            "B6 source inventory is not canonical")
    expected = build_source_inventory()
    require(value == expected, "B6 source inventory differs from exact current-main source")
    return value


def _workflow() -> dict[str, Any]:
    raw = (ROOT / PORT_WORKFLOW).read_text(encoding="utf-8")
    value = yaml.load(raw, Loader=yaml.BaseLoader)
    require(type(value) is dict, "PORT-02C workflow YAML is not a mapping")
    return value


def _workflow_contract() -> dict[str, Any]:
    value = _workflow()
    triggers = value.get("on")
    require(type(triggers) is dict and set(triggers) == {"pull_request", "workflow_dispatch"},
            "PORT-02C trigger family changed")
    pr = triggers["pull_request"]
    dispatch = triggers["workflow_dispatch"]
    require(pr.get("branches") == ["main"], "PORT-02C PR base branch contract changed")
    require(pr.get("paths") == list(EXPECTED_PR_PATHS), "PORT-02C PR path filter changed")
    # BaseLoader represents a YAML key with no mapping/value as the empty
    # string. Keep that form (and explicit null/empty mapping) equivalent to
    # no declared inputs or filters.
    require(dispatch in (None, {}, ""), "PORT-02C manual dispatch has declared inputs or filters")
    permissions = value.get("permissions") or {}
    require(permissions == {"contents": "read"}, "PORT-02C workflow contents permission changed")
    concurrency = value.get("concurrency") or {}
    expected_group = "port-02c-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"
    require(concurrency.get("group") == expected_group, "PORT-02C concurrency grouping changed")
    require(concurrency.get("cancel-in-progress") == "true",
            "PORT-02C platform cancellation behavior changed")
    jobs = value.get("jobs") or {}
    require(set(jobs) == {"native-slice"}, "PORT-02C job topology changed")
    job = jobs["native-slice"]
    matrix = job.get("strategy", {}).get("matrix", {}).get("include", [])
    require(matrix == [
        {"os": "windows", "runner": "windows-latest", "bundle_platform": "windows"},
        {"os": "linux", "runner": "ubuntu-24.04", "bundle_platform": "linux"},
    ], "PORT-02C native matrix changed")
    require("if" not in job, "PORT-02C job body is no longer reachable from both target triggers")
    steps = job.get("steps") or []
    checkout = next((s for s in steps if s.get("uses") == "actions/checkout@v4"), None)
    require(checkout is not None, "PORT-02C checkout step changed")
    checkout_with = checkout.get("with") or {}
    require(checkout_with.get("persist-credentials") != "false",
            "checkout token persistence source behavior changed")
    upload = next((s for s in steps if s.get("uses") == "actions/upload-artifact@v4"), None)
    require(upload is not None, "PORT-02C Actions artifact upload step is missing")
    upload_with = upload.get("with") or {}
    require(upload_with.get("name") == "port02c-${{ matrix.os }}-evidence"
            and upload_with.get("retention-days") == "14",
            "PORT-02C run-scoped artifact contract changed")
    install = next((s for s in steps if s.get("name") == "Install runtime and build dependencies"), None)
    require(install is not None and "pip install --upgrade pip" in install.get("run", "")
            and "-r requirements.txt" in install.get("run", "")
            and "-r packaging/build-requirements.txt" in install.get("run", ""),
            "PORT-02C build-toolchain package installation changed")
    return {
        "workflow_path": PORT_WORKFLOW,
        "trigger_keys": ["pull_request", "workflow_dispatch"],
        "pull_request": {
            "base_branches": list(pr["branches"]),
            "paths": list(pr["paths"]),
            "classification": "CONDITIONALLY_REACHABLE_PULL_REQUEST_PATH_FILTERED",
            "current_not_spent_historical_exact_pr_bound_or_retired": True,
        },
        "workflow_dispatch": {
            "declared_inputs": [],
            "yaml_branch_filter": None,
            "classification": "MANUALLY_REACHABLE_WORKFLOW_DISPATCH_REF_SELECTABLE",
            "external_manual_authority_preserved_without_repository_caller": True,
        },
        "same_job_body_reachable_from_both_triggers": True,
        "permissions": permissions,
        "checkout": {
            "action": "actions/checkout@v4",
            "persist_credentials_declared_false": False,
            "checkout_token_material": "PRESENT_BY_DEFAULT_CHECKOUT_CREDENTIAL_BEHAVIOR",
            "token_permission": "contents:read",
        },
        "concurrency": {
            "group": expected_group,
            "cancel_in_progress": True,
            "authority": "YES_PLATFORM_MANAGED_SAME_GROUP_CANCEL_IN_PROGRESS",
            "pull_request_group_key": "github.event.pull_request.number",
            "manual_non_pr_group_key": "github.ref",
            "explicit_api_cancel_source_path": False,
        },
        "matrix": matrix,
        "actions_artifact": {
            "name": upload_with["name"], "retention_days": 14,
            "authority": "YES_RUN_SCOPED",
        },
        "workflow_infrastructure_network": "YES",
        "build_toolchain_network": "YES_PIP_ACTIONS_AND_PACKAGE_INDEX_TRANSPORT",
        "runtime_qualification_outbound_network": "DENIED_AND_INSTRUMENTED",
    }


def _repository_caller_scan() -> dict[str, Any]:
    """Find static repository callers without treating absent callers as no authority."""
    dispatch_patterns = (
        "gh workflow run", "createWorkflowDispatch", "actions.createWorkflowDispatch",
        "repository_dispatch", "/actions/workflows/port-02c-native-runtime.yml/dispatches",
        "workflow_dispatch", "workflow_dispatches",
    )
    process_patterns = (
        "subprocess.run", "subprocess.popen", "subprocess.check_call", "subprocess.call",
        "execfile(", "child_process.spawn", "child_process.exec", "shell=true", "shell=True",
    )
    target_names = {Path(PORT_WORKFLOW).name.lower(), "port-02c native runtime"}
    hits = []
    for path in sorted(_checkout_tree_entries()):
        if not path.startswith((".github/workflows/", "scripts/", "domain/", "runtime/", "services/")):
            continue
        if path == PORT_WORKFLOW or (path.startswith("scripts/") and Path(path).name.startswith("audit_")):
            continue
        if path.endswith((".json", ".zip", ".sqlite", ".db")):
            continue
        try:
            raw = (ROOT / path).read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lowered = text.lower()
        has_target_reference = any(name in lowered for name in target_names)
        if not has_target_reference:
            continue
        if any(pattern.lower() in lowered for pattern in dispatch_patterns):
            hits.append({"path": path, "classification": "STATIC_PORT02C_DISPATCH_CALLER_CANDIDATE"})
            continue
        if path.startswith(".github/workflows/"):
            try:
                doc = yaml.load(text, Loader=yaml.BaseLoader) or {}
            except yaml.YAMLError:
                hits.append({"path": path, "classification": "WORKFLOW_SOURCE_REQUIRES_EXACT_CALLER_REVIEW"})
                continue
            on = doc.get("on", {}) if type(doc) is dict else {}
            workflow_uses = re.search(
                r"uses:\s*[^\n]*\.github/workflows/port-02c-native-runtime\.yml(?:@|\s|$)",
                text, flags=re.IGNORECASE,
            )
            if workflow_uses:
                hits.append({"path": path, "classification": "REUSABLE_WORKFLOW_CALLER"})
                continue
            upstream = on.get("workflow_run", {}) if type(on) is dict else {}
            if type(upstream) is dict and "PORT-02C native runtime" in (upstream.get("workflows") or []):
                hits.append({"path": path, "classification": "WORKFLOW_RUN_NAME_CALLER"})
                continue
            if "issue_comment" in on and has_target_reference:
                hits.append({"path": path, "classification": "ISSUE_COMMENT_TARGET_REFERENCE_REQUIRES_CALLER_REVIEW"})
            continue
        if any(pattern.lower() in lowered for pattern in process_patterns):
            hits.append({"path": path, "classification": "SUBPROCESS_WRAPPER_TARGET_REFERENCE_REQUIRES_CALLER_REVIEW"})
    return {
        "method": "TRACKED_SOURCE_SCAN_FOR_WORKFLOW_CALL_WORKFLOW_RUN_API_GH_SUBPROCESS_AND_ISSUE_COMMENT_BRIDGES",
        "search_dimensions": [
            "workflow_call", "workflow_run", "GitHub workflow dispatch API",
            "gh workflow run", "subprocess dispatch wrappers", "issue_comment bridges",
        ],
        "candidate_hits": hits,
        "result": "NO_CURRENT_REPOSITORY_CALLER_FOUND_SOURCE_SCAN" if not hits else "CALLER_CANDIDATE_FOUND",
        "external_manual_or_push_control_plane": "NOT_ERASED_BY_NO_REPOSITORY_CALLER_SCAN",
    }


def _assert_runtime_source_contract() -> dict[str, Any]:
    qualifier = (ROOT / "scripts/qualify_port_02_native_runtime.py").read_text(encoding="utf-8")
    replay = (ROOT / "scripts/port_02c_offline_composed_replay.py").read_text(encoding="utf-8")
    builder = (ROOT / "scripts/build_dev_bundle.py").read_text(encoding="utf-8")
    source_identity = (ROOT / "runtime/source_identity.py").read_text(encoding="utf-8")
    launcher = (ROOT / "runtime/worker_launcher.py").read_text(encoding="utf-8")
    workflow_text = (ROOT / PORT_WORKFLOW).read_text(encoding="utf-8")
    for expression in (
        "(socket.socket, \"connect\", self._deny)",
        "(socket.socket, \"connect_ex\", self._deny)",
        "(socket, \"create_connection\", self._deny)",
        "(urllib.request, \"urlopen\", self._deny)",
    ):
        require(expression in qualifier, "qualifier outbound transport sentinel is incomplete")
    for expression in (
        "socket.socket, \"connect\"", "socket.socket, \"connect_ex\"",
        "socket, \"create_connection\"", "urllib.request, \"urlopen\"",
        "capture_live_event_quote_evidence", "\"_fetch_page\"",
    ):
        require(expression in replay, "retained replay transport/provider guard is incomplete")
    require("require_network_acquisition_performed=True" in replay,
            "historical capture acquisition requirement was removed or reinterpreted")
    require("create_share_code=False" in qualifier and "place_wager=False" in qualifier,
            "exact no-delivery/no-wager probe RunRequest changed")
    require('"provider_calls": 0' in qualifier and '"delivery_calls": 0' in qualifier
            and '"login_actions": 0' in qualifier and '"cookie_actions": 0' in qualifier
            and '"wallet_actions": 0' in qualifier and '"stake_actions": 0' in qualifier
            and '"wager_actions": 0' in qualifier and '"wager": False' in qualifier,
            "qualifier result no longer binds zero provider/delivery/wager action fields")
    require("share_code_generation=True" in qualifier,
            "canonical delivery owner resolution/AuthorityManifest nuance changed")
    require("resolve_canonical_core" in qualifier and "domain.sportybet_share_code" in
            (ROOT / "domain/canonical_core.py").read_text(encoding="utf-8"),
            "canonical delivery-owner resolution is no longer explicit")
    for expression in (
        "price_all_shadow_fixture", "route_shadow_price_results", "optimize_shadow_portfolio",
        "production_model_authority\": False", "production_probability_authority\": False",
        "complete_current_history_reconstructed\": False",
    ):
        require(expression in replay, "retained replay business-logic/non-production contract changed")
    require("LOCAL_WINDOWS_11_NATIVE" in (ROOT / PORT_RECEIPT_PATH).read_text(encoding="utf-8")
            and '"windows_11_proof":false' in (ROOT / PORT_RECEIPT_PATH).read_text(encoding="utf-8").replace(" ", ""),
            "immutable PORT receipt lost Windows 11 versus hosted Windows distinction")
    require("verify_development_checkout" in builder and "subprocess.run" in builder
            and "ls-files" in builder and "status" in builder and "rev-parse" in builder
            and "ls-tree" in builder and '"show"' in builder,
            "bundle builder no longer requires verified tracked DevelopmentCheckout source")
    require("cat-file" in source_identity and "hash-object" in source_identity
            and "rev-parse" in source_identity and "show" in source_identity,
            "transitive source identity Git read commands changed")
    require("PyInstaller" in builder and "subprocess.run" in builder,
            "local native bundle freeze authority changed")
    require('"entire_repo_bundled": False' in builder
            and '"entire_venv_bundled": False' in builder
            and '"first_launch_pip_install": False' in builder,
            "bundle closed-world and installed first-launch contract changed")
    require("subprocess.Popen" in launcher and "shell=False" in launcher
            and "OFFLINE_IDENTITY_PROBE" in launcher,
            "local native worker process boundary changed")
    require("chmod -R a-w" in workflow_text and "time.sleep(60)" in workflow_text
            and "kill $LOCK_PID" in workflow_text,
            "read-only install or temporary lock-helper process contract changed")
    forbidden_write_markers = (
        "git push", "git commit", "gh release create", "createRelease",
        "createWorkflowDispatch", "/actions/runs/",
    )
    relevant = "\n".join((builder, qualifier, replay, workflow_text))
    require(not any(marker in relevant for marker in forbidden_write_markers),
            "PORT-02C source gained repository/release/dispatch mutation path")
    return {
        "qualifier_transport_sentinel": ["socket.connect", "socket.connect_ex",
                                         "socket.create_connection", "urllib.request.urlopen"],
        "nested_retained_replay_guards": True,
        "build_git_commands": ["ls-files", "status", "rev-parse", "show", "ls-tree",
                               "cat-file", "hash-object"],
        "build_git_authority": "LOCAL_GIT_REPOSITORY_READ_ONLY",
        "bundle_pyinstaller": "LOCAL_SUBPROCESS",
        "entire_repo_bundled": False,
        "entire_venv_bundled": False,
        "first_launch_pip_install": False,
        "qualification_worker": "LOCAL_NATIVE_SUBPROCESS_SHELL_FALSE_OFFLINE_IDENTITY_PROBE_ONLY",
        "local_runner_filesystem_write_authority": "YES_DISPOSABLE_STAGING_WRITABLE_ROOTS_AND_RUN_SCOPED_EVIDENCE",
        "local_subprocess_native_execution_authority": "YES",
    }


def _validate_inherited_state() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    parent = completion_v8.validate_receipt()
    require(parent["canonical_sha256"] == COMPLETION_V8_SHA,
            "immutable Completion V8 identity drift")
    b5_value = b5.validate_receipt()
    require(b5_value["canonical_sha256"] == B5_RECEIPT_SHA,
            "immutable B5 receipt identity drift")
    require(b5_value["source_inventory"]["canonical_sha256"] == B5_SOURCE_INVENTORY_SHA,
            "immutable B5 source inventory identity drift")
    a2_v7 = boundary.read(A2_V7_PATH)
    require(a2_v7.get("canonical_sha256") == A2_V7_SHA and a2_v7.get("generation") == 7,
            "immutable A2 generation V7 identity drift")
    inherited = parent["unreviewed_authority_surfaces"]
    keys = {(row["workflow_path"], row["trigger_kind"]) for row in inherited}
    require(len(inherited) == 3 and keys == EXPECTED_UNRESOLVED,
            "Completion V8 no longer authenticates the exact three-surface B6 baseline")
    require(parent["workflow_tree_after_sha1"] == WORKFLOW_TREE
            and parent["workflow_tree_before_sha1"] == WORKFLOW_TREE
            and parent["evolution_ledger_after_sha256"] == EVOLUTION_SHA
            and parent["evolution_ledger_before_sha256"] == EVOLUTION_SHA
            and parent["transition_count"] == 14
            and parent["retirement_ledger_sha256"] == RETIREMENT_SHA
            and parent["retired_workflow_count"] == 3,
            "Completion V8 workflow/evolution/retirement invariants drifted")
    return parent, b5_value, a2_v7


def _validate_architecture_ledgers() -> dict[str, Any]:
    # The pinned Completion V8 receipt binds the authoritative base/tree. Its
    # workflow subtree identity is the same immutable WORKFLOW_TREE constant.
    # In depth-one PR CI the base commit object is absent, so authenticate the
    # checked-out merge snapshot's workflow subtree against that pin directly.
    workflow_tree = _git("rev-parse", "HEAD:.github/workflows").decode().strip()
    require(workflow_tree == WORKFLOW_TREE, "checked-out workflow tree identity drift")
    evolution = _read_json("artifacts/architecture/p4_workflow_evolution_ledger_v1.json")
    retirement = _read_json("artifacts/architecture/p4_3_workflow_retirement_ledger_v1.json")
    require(evolution.get("canonical_sha256") == EVOLUTION_SHA
            and len(evolution.get("transitions", [])) == 14,
            "workflow evolution ledger identity/transition count drift")
    require(retirement.get("canonical_sha256") == RETIREMENT_SHA
            and len(retirement.get("retirements", [])) == 3,
            "workflow retirement ledger identity/count drift")
    require(workflow_tree == WORKFLOW_TREE, "B6 changed the workflow tree")
    return {
        "workflow_tree_sha1": workflow_tree,
        "workflow_diff_count": 0,
        "evolution_ledger_sha256": EVOLUTION_SHA,
        "transition_count": 14,
        "retirement_ledger_sha256": RETIREMENT_SHA,
        "retired_workflow_count": 3,
        "workflow_retirement_or_deletion_count": 0,
    }


def _historical_actions_metadata() -> dict[str, Any]:
    receipt = _read_json(PORT_RECEIPT_PATH)
    expected = {
        "id": 36792107722,
        "name": "PORT-02C native runtime",
        "event": "workflow_dispatch",
        "head_branch": "feat/port-02c-native-installed-runtime-slice",
        "head_sha": "535354619e4b775cc18ae3c7200e30df89031f73",
        "run_attempt": 1,
        "status": "completed",
        "conclusion": "success",
        "jobs": {
            "native slice (windows)": "success",
            "native slice (linux)": "success",
        },
        "artifacts": [
            {"id": 11133320259, "name": "port02c-linux-evidence",
             "digest": "sha256:5aa3319ccc0787e40124b74115296b05af0a02c03e862400b22241fd4a6b2b0c"},
            {"id": 11132725761, "name": "port02c-windows-evidence",
             "digest": "sha256:7d7d8b354e40e087992e22f4006b4bbf66eaff93344554b2dde3565a71f5348e"},
        ],
    }
    expected["rerun_endpoint_present"] = True
    windows = receipt["cross_platform_parity"]["hosted_windows_packaging_regression"]
    require(windows.get("workflow_run_id") == expected["id"] and windows.get("windows_11_proof") is False,
            "hosted Windows run was conflated with Windows 11 proof")
    platforms = {row["platform"]: row for row in receipt["platforms"]}
    require(platforms["windows"]["evidence_source"] == "LOCAL_WINDOWS_11_NATIVE"
            and platforms["linux"]["evidence_source"] == "GITHUB_ACTIONS_UBUNTU_24_04_NATIVE",
            "immutable native platform evidence-source distinction drifted")
    require(expected["artifacts"][0]["id"] != expected["artifacts"][1]["id"],
            "historical Actions artifact IDs collapsed")
    expected["metadata_source"] = "READ_ONLY_GITHUB_RUN_JOB_AND_ARTIFACT_METADATA"
    expected["artifact_payloads_downloaded"] = False
    expected["rerun_residual"] = "HISTORICAL_ACTIONS_RERUN_RESIDUAL_NOT_PROVEN_ABSENT"
    expected["run_proves_history_only"] = True
    return expected


def _target_rows(contract: dict[str, Any], caller: dict[str, Any], runtime: dict[str, Any],
                 history: dict[str, Any], port: dict[str, Any]) -> list[dict[str, Any]]:
    common = {
        "caller_state": caller["result"],
        "historical_actions_rerun_residual": history["rerun_residual"],
        "permissions_and_credentials": {
            "permissions": contract["permissions"],
            "checkout_token_material": contract["checkout"]["checkout_token_material"],
            "checkout_token_permission": "contents:read",
            "github_repository_write_authority": "NO_SOURCE_PATH_AND_TOKEN_CONTENTS_READ_ONLY",
        },
        "network_authority": {
            "workflow_infrastructure_network": contract["workflow_infrastructure_network"],
            "build_toolchain_network": contract["build_toolchain_network"],
            "runtime_qualification_outbound_network": contract["runtime_qualification_outbound_network"],
            "current_provider_acquisition": "NONE_IN_QUALIFICATION_PATH",
            "historical_provider_evidence_consumption": "YES_RETAINED_SOURCE_ONLY",
        },
        "build_git_authority": runtime["build_git_authority"],
        "local_filesystem_and_process_authority": {
            "filesystem_write": runtime["local_runner_filesystem_write_authority"],
            "native_subprocess": runtime["local_subprocess_native_execution_authority"],
            "persistent_canonical_database_write": "NO_SOURCE_PATH",
        },
        "retained_composition": {
            "local_offline_business_logic_replay": "YES",
            "price_all_router_portfolio": "RETAINED_QUALIFICATION_ONLY_LOCAL_REPLAY",
            "production_model_authority": "NO",
            "production_probability_authority": "NO",
            "production_selection_authority": "NO",
            "complete_current_history_reconstruction": False,
        },
        "delivery_and_wager": {
            "canonical_component_resolution_includes_delivery_owner": True,
            "canonical_delivery_component_owner": "domain.sportybet_share_code",
            "share_code_generation_execution": "NOT_EXERCISED_AND_NETWORK_GUARDED",
            "create_share_code": False,
            "place_wager": False,
            "provider_calls": 0,
            "delivery_calls": 0,
            "network_attempts": 0,
            "login_actions": 0,
            "cookie_actions": 0,
            "wallet_actions": 0,
            "stake_actions": 0,
            "wager_actions": 0,
            "live_delivery_authority": "NO_EXECUTED_DELIVERY",
            "wager_authority": "NO",
        },
        "write_authority": {
            "github_actions_artifact_write_authority": "YES_RUN_SCOPED",
            "github_repository_write_authority": "NO_SOURCE_PATH_AND_TOKEN_CONTENTS_READ_ONLY",
            "external_storage_write_authority": "NO_SOURCE_PATH",
            "release_publish_authority": "NO_SOURCE_PATH",
        },
        "concurrency_cancellation": contract["concurrency"],
        "product_release_disposition": {
            "release_qualification_capability": "CURRENT_RETAINED_SUPPORTED_ENGINEERING_GATE",
            "end_user_runtime_execution": "NOT_THIS_WORKFLOW",
            "physical_trigger_runtime_authority": "CURRENT_CONDITIONAL_OR_MANUAL_CI_QUALIFICATION",
            "retirement_authorized": False,
        },
        "historical_run": history,
        "status": "RESOLVED",
        "blocker": None,
        "source_evidence": {
            "PORT_receipt_canonical_sha256": port["canonical_sha256"],
            "workflow_tree_sha1": WORKFLOW_TREE,
        },
    }
    rows = []
    for workflow_path, trigger in TARGETS:
        if trigger == "pull_request":
            manual_control_plane = {
                "this_surface_is_manual": False,
                "this_surface_manual_classification": "PULL_REQUEST_EVENT_NOT_MANUAL_DISPATCH",
                "separate_workflow_dispatch_surface_remains_manual_ref_selectable": True,
                "current_manual_dispatch_count": 0,
                "absence_of_repository_caller_removes_manual_authority": False,
            }
        else:
            manual_control_plane = {
                "this_surface_is_manual": True,
                "workflow_dispatch_authority": "EXTERNAL_GITHUB_MANUAL_DISPATCH_AVAILABLE",
                "historical_non_main_dispatch": {
                    "branch": history["head_branch"], "head_sha": history["head_sha"],
                    "run_id": history["id"],
                },
                "current_manual_dispatch_count": 0,
                "absence_of_repository_caller_removes_manual_authority": False,
                "authority_independent_of_historical_rerun_residual": True,
            }
        if trigger == "pull_request":
            reachability = {
                "classification": "CONDITIONALLY_REACHABLE_PULL_REQUEST_PATH_FILTERED",
                "base_branches": ["main"],
                "path_filters": list(EXPECTED_PR_PATHS),
                "current": True,
                "spent_or_historical": False,
                "exact_PR_bound": False,
                "retired": False,
            }
        else:
            reachability = {
                "classification": "MANUALLY_REACHABLE_WORKFLOW_DISPATCH_REF_SELECTABLE",
                "declared_inputs": [],
                "yaml_branch_filter": None,
                "historical_non_main_branch_proves_ref_selectability": history["head_branch"],
            }
        row = deepcopy(common)
        row.update({
            "identity": {"workflow_path": workflow_path, "trigger_kind": trigger},
            "manual_control_plane": manual_control_plane,
            "trigger_contract": {
                "physical_trigger": trigger,
                "reachability": reachability,
                "same_job_body_reachable": True,
            },
            "workflow_control_plane": {
                "workflow_infrastructure_network": "YES",
                "build_toolchain_network": "YES",
                "runtime_qualification_outbound_network": "DENIED_AND_INSTRUMENTED",
                "actions_artifact_retention_days": 14,
                "default_checkout_credentials_persist": True,
                "contents_permission": "read",
                "manual_cancel_count": 0,
            },
        })
        rows.append(row)
    return rows


def build_receipt() -> dict[str, Any]:
    parent, b5_value, a2_v7 = _validate_inherited_state()
    require(a2_v7["canonical_sha256"] == A2_V7_SHA, "A2 V7 predecessor identity changed")
    source_inventory = validate_source_inventory()
    a2_current = boundary.authenticate_inventory()
    require(a2_current.get("generation") == 8, "A2 current source inventory is not generation V8")
    contract = _workflow_contract()
    caller = _repository_caller_scan()
    require(caller["result"] == "NO_CURRENT_REPOSITORY_CALLER_FOUND_SOURCE_SCAN",
            "an in-repository PORT-02C caller candidate needs exact review")
    runtime = _assert_runtime_source_contract()
    port = _read_json(PORT_RECEIPT_PATH)
    require(port["canonical_sha256"] == PORT_RECEIPT_SHA, "immutable PORT receipt identity drift")
    history = _historical_actions_metadata()
    ledgers = _validate_architecture_ledgers()
    rows = _target_rows(contract, caller, runtime, history, port)
    resolved = {(r["identity"]["workflow_path"], r["identity"]["trigger_kind"])
                for r in rows if r["status"] == "RESOLVED"}
    require(resolved == set(TARGETS), "B6 did not fully classify exactly its two trigger surfaces")
    inherited = parent["unreviewed_authority_surfaces"]
    inherited_keys = {(r["workflow_path"], r["trigger_kind"]) for r in inherited}
    require(inherited_keys == EXPECTED_UNRESOLVED, "Completion V8 source baseline changed")
    remaining = [deepcopy(r) for r in inherited
                 if (r["workflow_path"], r["trigger_kind"]) not in resolved]
    remaining_keys = {(r["workflow_path"], r["trigger_kind"]) for r in remaining}
    require(remaining_keys == {WIN_EITHER_HALF},
            "B6 must preserve the exact Win-Either-Half row as the sole remaining surface")
    require(len(remaining) == 3 - len(resolved) == 1,
            "B6 global unresolved count must be derived from resolved target count")
    require(parent["checkpoint_criteria"]["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False
            and parent["checkpoint_criteria"]["no_unknown_current_artifact_or_notification_authority"] is False,
            "B6 predecessor criteria 11/14 must remain false")
    require(parent["checkpoint_e_status"] == parent["p4_4_status"] == "INCOMPLETE",
            "B6 predecessor Checkpoint E/P4.4 must remain incomplete")
    require(parent["historical_missing_artifact_relation_count"] == 14
            and parent["live_missing_artifact_relation_count"] == 0
            and parent["retention_blockers_A_B_C_D"] == "CLOSED_WITH_HISTORICAL_LIMITATIONS_PRESERVED",
            "B6 predecessor retention state drifted")
    require(ZERO_ACTIONS == {key: 0 for key in ZERO_ACTIONS}, "B6 live review actions must remain zero")

    value = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository": "Thabearr/ATHENA",
        "master_issue": 337,
        "observed_at": OBSERVED_AT,
        "base": {"branch": "main", "commit_sha": BASE_MAIN, "tree_sha": BASE_TREE},
        "source_review_reset_comment": SOURCE_REVIEW_RESET_COMMENT,
        "source_review_counter_while_open": "0/5",
        "source_review_counter_if_owner_merges": "1/5",
        "mandatory_governing_source_reread_after_b6_merge": "NO",
        "post_444_tests": POST_444_TESTS,
        "predecessors": {
            "completion_v8": {"path": COMPLETION_V8_PATH, "canonical_sha256": COMPLETION_V8_SHA,
                               "rewritten": False},
            "b5_receipt": {"path": B5_RECEIPT_PATH, "canonical_sha256": B5_RECEIPT_SHA,
                           "rewritten": False},
            "b5_source_inventory": {"path": B5_SOURCE_INVENTORY_PATH,
                                    "canonical_sha256": B5_SOURCE_INVENTORY_SHA, "rewritten": False},
            "a2_generation_7": {"path": A2_V7_PATH, "canonical_sha256": A2_V7_SHA,
                                "generation": 7, "rewritten": False},
            "a2_generation_8": {"path": boundary.inventory_generation_path(8),
                                "canonical_sha256": a2_current["canonical_sha256"],
                                "generation": 8,
                                "predecessor": {"path": A2_V7_PATH, "canonical_sha256": A2_V7_SHA,
                                                "generation": 7, "rewritten": False}},
            "port_receipt": {"path": PORT_RECEIPT_PATH, "canonical_sha256": PORT_RECEIPT_SHA,
                             "git_blob_sha1": PORT_RECEIPT_BLOB, "rewritten": False},
        },
        "port_workflow": {
            "path": PORT_WORKFLOW, "git_blob_sha1": PORT_WORKFLOW_BLOB,
            "normalized_source_sha256": PORT_WORKFLOW_SHA,
            "workflow_tree_sha1": WORKFLOW_TREE,
        },
        "source_inventory": {
            "path": SOURCE_INVENTORY_PATH,
            "canonical_sha256": source_inventory["canonical_sha256"],
            "source_count": source_inventory["source_count"],
        },
        "target_count": 2,
        "resolved_target_count": len(resolved),
        "partial_target_count": 2 - len(resolved),
        "global_unknown_before": 3,
        "global_unknown_after": 3 - len(resolved),
        "target_keys": [[path, trigger] for path, trigger in TARGETS],
        "review_rows": rows,
        "remaining_unreviewed_surfaces": remaining,
        "repository_caller_scan": caller,
        "historical_actions_metadata": history,
        "runtime_source_contract": runtime,
        "workflow_contract": contract,
        "workflow_evolution_and_retirement_invariants": ledgers,
        "workflow_count": parent["workflow_count"],
        "trigger_surface_count": parent["trigger_surface_count"],
        "historical_missing_artifact_relation_count": parent["historical_missing_artifact_relation_count"],
        "live_missing_artifact_relation_count": parent["live_missing_artifact_relation_count"],
        "retention_blockers_A_B_C_D": parent["retention_blockers_A_B_C_D"],
        "criterion_11": False,
        "criterion_14": False,
        "checkpoint_e_status": "INCOMPLETE",
        "p4_4_status": "INCOMPLETE",
        "workflow_edit_count": 0,
        "trigger_edit_count": 0,
        "workflow_retirement_count": 0,
        "workflow_deletion_count": 0,
        "caller_migration_count": 0,
        "actions": deepcopy(ZERO_ACTIONS),
        "manual_cancel_count": 0,
        "terminal": "CORE_01D_PORT02C_TRIGGER_AUTHORITY_B6_REVIEW_READY_2_RESOLVED_DO_NOT_MERGE",
    }
    return boundary.seal(value)


def validate_receipt(value: dict[str, Any] | None = None) -> dict[str, Any]:
    value = boundary.read(RECEIPT_PATH) if value is None else value
    require((ROOT / RECEIPT_PATH).read_bytes() == _canonical(value), "B6 receipt is not canonical")
    expected = build_receipt()
    require(value == expected, "B6 receipt differs from exact source, metadata, and V8 overlay")
    require(value["target_count"] == 2 and value["resolved_target_count"] == 2
            and value["partial_target_count"] == 0, "B6 exact two-target scope or resolution count drift")
    require(value["global_unknown_after"] == value["global_unknown_before"] - value["resolved_target_count"] == 1,
            "B6 unresolved count is not derived")
    require({(r["workflow_path"], r["trigger_kind"]) for r in value["remaining_unreviewed_surfaces"]}
            == {WIN_EITHER_HALF}, "B6 must leave exactly the unchanged Win-Either-Half surface")
    require(value["checkpoint_e_status"] == value["p4_4_status"] == "INCOMPLETE"
            and value["criterion_11"] is False and value["criterion_14"] is False,
            "B6 cannot complete Checkpoint E/P4.4 or criteria 11/14")
    require(value["actions"] == ZERO_ACTIONS and value["manual_cancel_count"] == 0,
            "B6 live dispatch/rerun/cancel/download/provider action must remain zero")
    return value


def audit() -> dict[str, Any]:
    value = validate_receipt()
    return {
        "result": "PASS",
        "receipt_sha256": value["canonical_sha256"],
        "source_inventory_sha256": value["source_inventory"]["canonical_sha256"],
        "target_count": value["target_count"],
        "resolved_target_count": value["resolved_target_count"],
        "global_unknown_before": value["global_unknown_before"],
        "global_unknown_after": value["global_unknown_after"],
        "remaining": value["remaining_unreviewed_surfaces"],
        "checkpoint_e": value["checkpoint_e_status"],
        "p4_4": value["p4_4_status"],
        "criterion_11": value["criterion_11"],
        "criterion_14": value["criterion_14"],
        "terminal": value["terminal"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-source-inventory", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write_source_inventory:
        value = build_source_inventory()
        (ROOT / SOURCE_INVENTORY_PATH).write_bytes(_canonical(value))
        print(value["canonical_sha256"])
    elif args.write:
        value = build_receipt()
        (ROOT / RECEIPT_PATH).write_bytes(_canonical(value))
        print(value["canonical_sha256"])
    else:
        print(json.dumps(audit(), sort_keys=True))


if __name__ == "__main__":
    main()
