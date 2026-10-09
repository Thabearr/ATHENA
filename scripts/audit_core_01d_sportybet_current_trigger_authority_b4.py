"""Authenticate the bounded B4 SportyBet trigger authority review.

This audit is offline after read-only GitHub metadata capture.  It never calls
SportyBet, creates/reloads a share code, dispatches/reruns a workflow, or reads
an Actions artifact payload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import yaml

from scripts.audit_data_01c_restore_portability import historical_workflow_tree

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary

ROOT = Path(__file__).resolve().parents[1]
BASE_MAIN = "dc9a09b8d0fa96a25f3b31e9fa588db40fde2ba9"
BASE_TREE = "167522cbb925a1bcab6982ed971de7ffb9a3cd8f"
WORKFLOW_TREE = "9b08653f1a12bb1b3d964fbd910396ff955740da"
EVOLUTION_SHA = "73e1eb3fe6593558c821600dd0f103353d45c15a139ab470a996c7cbb35da531"
RETIREMENT_SHA = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
COMPLETION_V6_PATH = "tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v6.json"
COMPLETION_V6_SHA = "9ec9debf1bfb3effbeeafb0f9a2a8f184fe131fa228d0b4778ee73974517d64d"
B3_RECEIPT_PATH = "tests/fixtures/core_01d/core-01d-owner-one-shot-issue-comment-authority-b3-v1.json"
B3_RECEIPT_SHA = "0ae8e31dab7989547e90d41a302f376a9aaf9ac6d2fcb12e2fb7f400d8352068"
B3_INVENTORY_PATH = "tests/fixtures/core_01d/owner-one-shot-issue-comment-authority-b3-source-inventory-v1.json"
B3_INVENTORY_SHA = "53c07ada31ddeb3a7f5fd0b3709c39bffcbce1c6f5b396d3a034879e8ce89509"
A2_V5_PATH = "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v5.json"
A2_V5_SHA = "8fbca3af87ecc7ac99da96252c3570e4ddef0d2e4071b180b2bc0299a10eeecd"
A2_V4_SHA = "82c440deb06d760d13bf73d914c5ec9181e568ba388f844a3fc6fa49976ab50f"
SOURCE_INVENTORY_PATH = "tests/fixtures/core_01d/sportybet-current-trigger-authority-b4-source-inventory-v1.json"
RECEIPT_PATH = "tests/fixtures/core_01d/core-01d-sportybet-current-trigger-authority-b4-v1.json"
POLICY_ID = "ATHENA_CORE_01D_SPORTYBET_CURRENT_TRIGGER_AUTHORITY_B4_V1"
SOURCE_INVENTORY_POLICY_ID = "ATHENA_CORE_01D_SPORTYBET_CURRENT_TRIGGER_AUTHORITY_B4_SOURCE_INVENTORY_V1"
OBSERVED_AT = "2026-10-04T01:19:57Z"

TARGETS = (
    (".github/workflows/create-saturday-2026-08-22-sportybet-direct-20-code.yml", "pull_request"),
    (".github/workflows/create-saturday-2026-08-22-sportybet-direct-20-code.yml", "workflow_dispatch"),
    (".github/workflows/pr258-sportybet-live-transport-proof.yml", "workflow_dispatch"),
    (".github/workflows/prb-sportybet-semantic-registry-proof.yml", "pull_request"),
    (".github/workflows/prb-sportybet-semantic-registry-proof.yml", "workflow_dispatch"),
    (".github/workflows/probe-sportybet-direct-20-markets.yml", "pull_request"),
    (".github/workflows/probe-sportybet-direct-20-markets.yml", "workflow_dispatch"),
    (".github/workflows/prove-sportybet-direct-share-code.yml", "pull_request"),
    (".github/workflows/prove-sportybet-direct-share-code.yml", "workflow_dispatch"),
)

# These pins authenticate the exact workflow and transitive source reviewed at
# the B4 base.  LF-normalized SHA-256 is separate from the Git blob identity.
SOURCE_PINS: dict[str, tuple[str, str]] = {
    ".github/workflows/create-saturday-2026-08-22-sportybet-direct-20-code.yml": ("84fd86333c34e8b6e27afe7f9d6e0e1c4234e93c", "c7493daa862a79788102ec85848c7f2161542c6d6e109967c34ddcc9ee6eb151"),
    ".github/workflows/pr258-sportybet-live-transport-proof.yml": ("af05c86521698cbc29a9434308e41c58497db84c", "f210e38e56460f626fc4ff33a346177c40beb828042f2ecc4a6cccd8bf6d5a3d"),
    ".github/workflows/prb-sportybet-semantic-registry-proof.yml": ("c8968bdb2a80a76e30b79f33a390184443765eb7", "8170ffbcda3658204eb706d9298857337f0c87d811dc2c6bc946870399f9594c"),
    ".github/workflows/probe-sportybet-direct-20-markets.yml": ("23fdbf26e950865e4e2bc5491f05f4be0e76617c", "62eee97a36fa2fe985fcf0c10fab966d43d0e95ca65663d9fa9980b6d27e3e4b"),
    ".github/workflows/prove-sportybet-direct-share-code.yml": ("18e5656c232102df141aaa614aca3d5d7575ec5b", "f3211e23db24f6519e9e3f2635e6ca46b0993f1f9efbdb706d53f80988b74382"),
    "scripts/sportybet_direct_share_bridge.py": ("681ce2a043a334dcb8523c81d092369d6540e6d5", "452a83426077ca758afef1f5e2a4d2e5100a1ef2401824cab733a4d31e0513cd"),
    "scripts/sportybet_direct_market_probe.py": ("0f64008df870ee881b54f193ea35156799237149", "4b5f8babed1b6c08c2ed2c505704de4d89e9f9a8b49c998dfcb2b1416c52a567"),
    "scripts/run_pr258_sportybet_live_transport_proof.py": ("fe132268d45ef61dac1316a2ee92f0f46cab1084", "9b1107103a18e0469af5f9cd62fee0368e4bb295e15bfcd272b44c2c9c065e07"),
    "scripts/run_prb_sportybet_semantic_registry_proof.py": ("ac8248e669e8a90ffabde3167c38211d0c5d1f88", "e10ffe0a9e5ab20aad4e6756ec937c7996c43fbc693c382e75a575f9dcbdb8ce"),
    "scripts/sportybet_semantic_share_bridge.py": ("272575e305707af20e1fe31a394caa6f8804e44e", "05307a0df5733145de81002c0ef6ebaa9bd95dd854916fc4d009de01a9f9d637"),
    "domain/current_shadow_sportybet_share_code.py": ("61efbddcf129bec5e5a117e43259f40227554a18", "7c84bc56253cec1f433471964a8c2039789d1ae0ce840c1acd7850978baae34c"),
    "domain/sportybet_current_event_discovery_reconciliation.py": ("42e3f635543694be67d5699f95100d776af18011", "636fe0407328bdc051a37ab1fd40c566c267bb238dba46178afb29c707f6b8c6"),
    "domain/sportybet_live_event_quote_evidence.py": ("096d54fe7493f6d81cdf3c4af7c4a9333c75fadc", "5d64143321e12313bb239b6d3973c8b5da5fb28855649e9890194f233ff0b48f"),
    "domain/sportybet_lite_source_capture.py": ("bfb8e79e04967f7aed08578bc63dc79f2511a503", "36843c8a8d953ac47e27a96235b3f757141ca68c7420f05d336e8f8c63ca1994"),
    "domain/current_sportybet_semantic_registry.py": ("646bf93549d0d859f00e1d42ba72aaa17a84a6e7", "53df590b9c69daeed3e98e512f466d382a1e9d021d7256745bae6a04c0746394"),
    "domain/current_direct_provider_canonical_market_mapping_rebind.py": ("28ca521845509ae2513c95929921c2608532a4c9", "ba31b555af98bb07febe23fe9cd33a2e2d8e5dd1c1aec04fba6ca0d4a93afa8a"),
    "domain/sportybet_reviewed_canonical_market_mapping.py": ("c08ac2cdec0570ca4eb5e16f2843c1b82b5b317c", "ccab33bff233465279a0eb7665ec5965a4e87cfaf2a48085238d40fd660c7918"),
    "domain/sportybet_early_payout_settlement.py": ("38daea3f390f9f4f721fdcb3a344cdfba975de02", "6ba999987b98d2532fc218e96bff51c34b81a05aece25629ff413aee2b3d3e32"),
    "domain/markets.py": ("07f181c951671c9d5131610370ee43a4530e243e", "fccd9a33e86bdbcd23cd59a069d585941fa6352eb33fccc837fc1a27a55ad77e"),
    "domain/model_status.py": ("f5ca1c05bc229346a946efcc72aa4033597fb997", "d6c113e3dc00427e007c58be6d7a287a158cf96ed08694d1b0202c49fac81e6b"),
    "domain/_portfolio_optimizer_v2_direct_provider_contracts.py": ("76cd2966b94259fd2752f2c2c236bfe60d5ee031", "c08a1543258dbd4a5211eebcd9a2927da9645ebee049c5ad18cac6ad467415d4"),
    "artifacts/research-protocols/saturday-2026-08-22-sportybet-final-20-selections-v1.json": ("db5bf9e75a711588611fbc5aa2fb91e8ed22702a", "e0fc1cbfda0001fc43ee956d629dac3e956844297da2e8b1ecf16c68169c0547"),
    "artifacts/research-protocols/saturday-2026-08-22-sportybet-direct-20-market-probe-v1.json": ("80404d9559a532913fb7d16c199415d288d4864a", "ddc8c104cc491057ea1e5e9de732cf72b6c6b74252bdd146974eb04be670fdd8"),
    "artifacts/research-protocols/saturday-2026-08-22-sportybet-direct-one-leg-proof-v1.json": ("b68597a5a52d6e9d9bfdabecff4875c1f1c4e884", "e644f377ceb71ab77cd3f41e5c159af36da621aeaa97f524b9668f020df3b94e"),
    "tests/test_sportybet_direct_share_bridge.py": ("7e8bd3398c9c103e4d7e298f7292fbd01d75b72f", "debbfd7bcfc2f116105eb3d31fe97750ce39041eeaba59c65caef3a6cd135bf6"),
    "tests/test_sportybet_direct_market_probe.py": ("8d0e5e1d19b7ac08931961b9c71cf72fbe92bf13", "5d4aaa61cb6872fb8a53e61c49ab993a2f97aee388894807ef53fd292890ac3c"),
}

TARGET_REACHABILITY = {
    (TARGETS[0]): "CONDITIONALLY_REACHABLE_PULL_REQUEST_PATH_FILTERED",
    (TARGETS[1]): "MANUALLY_REACHABLE_WORKFLOW_DISPATCH",
    (TARGETS[2]): "MANUALLY_REACHABLE_WORKFLOW_DISPATCH",
    (TARGETS[3]): "CONDITIONALLY_REACHABLE_PULL_REQUEST_EXACT_HEAD_REF",
    (TARGETS[4]): "MANUALLY_REACHABLE_WORKFLOW_DISPATCH",
    (TARGETS[5]): "CONDITIONALLY_REACHABLE_PULL_REQUEST_PATH_FILTERED",
    (TARGETS[6]): "MANUALLY_REACHABLE_WORKFLOW_DISPATCH",
    (TARGETS[7]): "CONDITIONALLY_REACHABLE_PULL_REQUEST_PATH_FILTERED",
    (TARGETS[8]): "MANUALLY_REACHABLE_WORKFLOW_DISPATCH",
}
PATH_FILTERS = {
    ".github/workflows/create-saturday-2026-08-22-sportybet-direct-20-code.yml": [
        ".github/workflows/create-saturday-2026-08-22-sportybet-direct-20-code.yml",
        "artifacts/research-protocols/saturday-2026-08-22-sportybet-final-20-selections-v1.json",
        "scripts/sportybet_direct_share_bridge.py", "tests/test_sportybet_direct_share_bridge.py",
    ],
    ".github/workflows/probe-sportybet-direct-20-markets.yml": [
        ".github/workflows/probe-sportybet-direct-20-markets.yml",
        "artifacts/research-protocols/saturday-2026-08-22-sportybet-direct-20-market-probe-v1.json",
        "scripts/sportybet_direct_market_probe.py", "tests/test_sportybet_direct_market_probe.py",
    ],
    ".github/workflows/prove-sportybet-direct-share-code.yml": [
        ".github/workflows/prove-sportybet-direct-share-code.yml",
        "artifacts/research-protocols/saturday-2026-08-22-sportybet-direct-one-leg-proof-v1.json",
        "scripts/sportybet_direct_share_bridge.py", "tests/test_sportybet_direct_share_bridge.py",
    ],
}

RUN_METADATA = {
    ".github/workflows/create-saturday-2026-08-22-sportybet-direct-20-code.yml": {
        "run_id": 33168982533, "event": "pull_request", "status": "completed", "conclusion": "success",
        "head_sha": "a9626e33de59ab5932321b85007f38201fbd11ad", "head_branch": "codex/sportybet-end-to-end-current-code",
        "created_at": "2026-08-28T11:55:10Z", "run_attempt": 1,
    },
    ".github/workflows/pr258-sportybet-live-transport-proof.yml": {
        "run_id": 33238889550, "event": "pull_request", "status": "completed", "conclusion": "success",
        "head_sha": "d159bf959e15ce23f8d56766f105dbd03f1b6549", "head_branch": "feature/pr258-research-shadow-sportybet-field-trial",
        "created_at": "2026-08-29T06:36:53Z", "run_attempt": 1,
    },
    ".github/workflows/prb-sportybet-semantic-registry-proof.yml": {
        "run_id": 37164923624, "event": "pull_request", "status": "completed", "conclusion": "skipped",
        "head_sha": "740249d6a527056193e80ec60300c518d627c4d2", "head_branch": "fix/core-01d-owner-one-shot-issue-comment-authority-b3",
        "created_at": "2026-10-04T00:25:55Z", "run_attempt": 1,
    },
    ".github/workflows/probe-sportybet-direct-20-markets.yml": {
        "run_id": 32563398849, "event": "pull_request", "status": "completed", "conclusion": "success",
        "head_sha": "fab36bf65b455e3ad28edb6f476f3dd312a2a648", "head_branch": "integration/sportybet-parse-booking-code",
        "created_at": "2026-08-22T08:51:50Z", "run_attempt": 1,
    },
    ".github/workflows/prove-sportybet-direct-share-code.yml": {
        "run_id": 33168982468, "event": "pull_request", "status": "completed", "conclusion": "success",
        "head_sha": "a9626e33de59ab5932321b85007f38201fbd11ad", "head_branch": "codex/sportybet-end-to-end-current-code",
        "created_at": "2026-08-28T11:55:10Z", "run_attempt": 1,
    },
}

ZERO_ACTIONS = {
    "sportybet_requests": 0, "share_codes_created_or_reloaded": 0, "live_market_or_upcoming_reads": 0,
    "workflow_dispatch": 0, "workflow_rerun": 0, "workflow_cancel": 0, "artifact_payload_downloads": 0,
    "github_comment_or_pr_mutation": 0, "github_branch_or_release_mutation": 0,
    "email_or_external_storage_write": 0, "login_or_cookie_or_wallet_or_stake_or_wager": 0,
    "workflow_retirement_or_deletion": 0,
}

ROLES = {
    ".github/workflows/create-saturday-2026-08-22-sportybet-direct-20-code.yml": "target_workflow_trigger_contract",
    ".github/workflows/pr258-sportybet-live-transport-proof.yml": "target_workflow_trigger_contract_sibling_pull_request_out_of_scope",
    ".github/workflows/prb-sportybet-semantic-registry-proof.yml": "target_workflow_trigger_contract",
    ".github/workflows/probe-sportybet-direct-20-markets.yml": "target_workflow_trigger_contract",
    ".github/workflows/prove-sportybet-direct-share-code.yml": "target_workflow_trigger_contract",
    "scripts/sportybet_direct_share_bridge.py": "anonymous_share_create_and_reload_transport",
    "scripts/sportybet_direct_market_probe.py": "anonymous_frozen_market_get_transport",
    "scripts/run_pr258_sportybet_live_transport_proof.py": "bounded_pr258_read_semantic_share_transport_runner",
    "scripts/run_prb_sportybet_semantic_registry_proof.py": "semantic_registry_runner_entrypoint",
    "scripts/sportybet_semantic_share_bridge.py": "anonymous_semantic_event_detail_read_and_resolution",
    "domain/current_shadow_sportybet_share_code.py": "anonymous_research_share_code_authority_and_safety_contract",
    "domain/sportybet_current_event_discovery_reconciliation.py": "anonymous_discovery_transport_and_uninvoked_reconciliation_boundary",
    "domain/sportybet_live_event_quote_evidence.py": "anonymous_event_detail_transport_and_no_production_authority_contract",
    "domain/sportybet_lite_source_capture.py": "local_evidence_persistence_helpers",
    "domain/current_sportybet_semantic_registry.py": "bounded_discovery_detail_registry_and_fail_closed_authority",
    "domain/current_direct_provider_canonical_market_mapping_rebind.py": "mapping_rebind_boundary_not_invoked_by_prb_runner",
    "domain/sportybet_reviewed_canonical_market_mapping.py": "reviewed_mapping_identity_not_minted_by_b4_paths",
    "domain/sportybet_early_payout_settlement.py": "settlement_semantics_identity_not_minted_by_b4_paths",
    "domain/markets.py": "market_identity_vocabulary",
    "domain/model_status.py": "model_authority_vocabulary",
    "domain/_portfolio_optimizer_v2_direct_provider_contracts.py": "portfolio_authority_vocabulary_only",
    "artifacts/research-protocols/saturday-2026-08-22-sportybet-final-20-selections-v1.json": "frozen_twenty_selection_input",
    "artifacts/research-protocols/saturday-2026-08-22-sportybet-direct-20-market-probe-v1.json": "frozen_twenty_event_market_probe_targets",
    "artifacts/research-protocols/saturday-2026-08-22-sportybet-direct-one-leg-proof-v1.json": "frozen_one_leg_share_code_input",
    "tests/test_sportybet_direct_share_bridge.py": "workflow_focused_offline_test_callee",
    "tests/test_sportybet_direct_market_probe.py": "workflow_focused_offline_test_callee",
}

EDGE_MAP = {
    ".github/workflows/create-saturday-2026-08-22-sportybet-direct-20-code.yml": [
        "workflow -> checkout/setup-python/pip/pytest -> direct share focused tests",
        "workflow -> scripts/sportybet_direct_share_bridge.py -> anonymous SportyBet create POST -> reload GET",
        "workflow -> actions/upload-artifact -> run-scoped proof artifact",
    ],
    ".github/workflows/pr258-sportybet-live-transport-proof.yml": [
        "workflow_dispatch -> scripts.run_pr258_sportybet_live_transport_proof -> anonymous upcoming GET",
        "runner -> domain.sportybet_live_event_quote_evidence -> anonymous event-detail GET",
        "runner -> scripts.sportybet_semantic_share_bridge -> fresh anonymous event-detail GET",
        "runner -> scripts.sportybet_direct_share_bridge -> anonymous create POST and reload GET",
        "workflow -> actions/upload-artifact -> run-scoped proof artifact",
    ],
    ".github/workflows/prb-sportybet-semantic-registry-proof.yml": [
        "workflow -> git ls-remote origin refs/heads/main only when manual base input is absent -> GitHub read",
        "workflow -> scripts.run_prb_sportybet_semantic_registry_proof -> domain.current_sportybet_semantic_registry",
        "registry -> anonymous live-or-prematch discovery GET, bounded upcoming fallback GET, and event-detail GETs",
        "workflow -> actions/upload-artifact -> run-scoped proof artifact; no share-code endpoint",
    ],
    ".github/workflows/probe-sportybet-direct-20-markets.yml": [
        "workflow -> focused market-probe tests -> scripts.sportybet_direct_market_probe.py",
        "probe -> anonymous GET /api/ng/factsCenter/event for each of twenty frozen event ids",
        "workflow -> actions/upload-artifact -> run-scoped raw and summary evidence",
    ],
    ".github/workflows/prove-sportybet-direct-share-code.yml": [
        "workflow -> focused direct-share tests -> scripts.sportybet_direct_share_bridge.py",
        "bridge -> anonymous POST /api/ng/orders/share?throwInvalidEvent=true -> GET /api/ng/orders/share/{code}",
        "workflow -> actions/upload-artifact -> run-scoped one-leg evidence",
    ],
}


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AssertionError(reason)


def _git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(boundary.canonical(value)).hexdigest()


def _identity(path: str) -> dict[str, str]:
    raw = (ROOT / path).read_bytes()
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    blob, digest = SOURCE_PINS[path]
    git_blob = _git("rev-parse", "HEAD:" + path).decode().strip()
    require(git_blob == blob, f"B4 source Git blob drift: {path}")
    require(hashlib.sha256(normalized).hexdigest() == digest, f"B4 normalized source SHA drift: {path}")
    return {"path": path, "git_blob_sha1": git_blob, "normalized_source_sha256": digest,
            "role": ROLES[path], "discovery_edges": EDGE_MAP.get(path, [])}


def _parse_workflow(path: str) -> dict[str, Any]:
    value = yaml.load((ROOT / path).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    require(type(value) is dict, f"workflow YAML did not parse as a mapping: {path}")
    return value


def _current_repository_callers() -> dict[str, Any]:
    # Search the checked-out executable source tree.  The source identities and
    # exact base SHA/tree are separately pinned in this evidence; relying on
    # BASE_MAIN's commit object here breaks the offline audit in shallow CI
    # checkouts after historical-proof tests intentionally drop ancestor data.
    # Audit/docs/tests and the workflow's own declaration are not callers.
    paths = [path for path in _git("ls-files", "-z").decode().split("\0") if path]
    candidates = [p for p in paths if (p.startswith(".github/workflows/") or p.startswith("scripts/") or p.startswith("domain/"))
                  and not p.startswith("scripts/audit_") and p != "scripts/capture_p4_3_workflow_capability_matrix.py"
                  and p not in {path for path, _ in TARGETS}]
    needles = ("gh workflow run", "createWorkflowDispatch", "actions.createWorkflowDispatch", "repository_dispatch")
    exact_names = {Path(path).name for path, _ in TARGETS}
    hits: list[dict[str, str]] = []
    for path in candidates:
        try:
            raw = (ROOT / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(needle in raw for needle in needles) and any(name in raw for name in exact_names):
            hits.append({"path": path, "classification": "POTENTIAL_STATIC_DISPATCH_CALL_REQUIRES_REVIEW"})
    return {"method": "CURRENT_CHECKED_OUT_SOURCE_SCAN_WORKFLOWS_SCRIPTS_DOMAIN_EXCLUDING_AUDIT_EVIDENCE_AND_TARGETS",
            "exact_target_name_or_dynamic_dispatch_hits": hits,
            "result": "NO_CURRENT_REPOSITORY_CALLER_FOUND_SOURCE_SCAN" if not hits else "CALLER_CANDIDATE_FOUND",
            "external_manual_dispatch_authority": "PRESERVED_NOT_ERASED_BY_NO_REPOSITORY_CALLER"}


def _validate_source_semantics() -> None:
    require(len(TARGETS) == 9 and len(set(TARGETS)) == 9, "B4 target surface set is not exactly nine unique keys")
    completion = boundary.read(COMPLETION_V6_PATH)
    require(completion.get("canonical_sha256") == COMPLETION_V6_SHA, "immutable Completion V6 SHA drift")
    inherited = {(r["workflow_path"], r["trigger_kind"]) for r in completion["unreviewed_authority_surfaces"]}
    require(len(inherited) == 16 and set(TARGETS) <= inherited, "B4 target scope differs from Completion V6 unresolved set")
    require(set(SOURCE_PINS) == set(ROLES), "B4 source inventory role/pin key mismatch")
    # Authenticate the pinned handoff identities from the sealed B4 evidence,
    # and verify the current checked-out workflow subtree.  Do not require the
    # historical main commit object: hosted pytest intentionally uses shallow
    # checkouts for some isolation tests.
    require(historical_workflow_tree(_git("rev-parse", "HEAD:.github/workflows").decode().strip()) == WORKFLOW_TREE,
            "B4 current workflow tree differs from the immutable handoff tree")
    evolution = boundary.read("artifacts/architecture/p4_workflow_evolution_ledger_v1.json")
    retirement = boundary.read("artifacts/architecture/p4_3_workflow_retirement_ledger_v1.json")
    require(evolution.get("canonical_sha256") == EVOLUTION_SHA and len(evolution.get("transitions", [])) == 14,
            "B4 workflow evolution ledger identity/transition count drift")
    require(retirement.get("canonical_sha256") == RETIREMENT_SHA and len(retirement.get("retirements", [])) == 3,
            "B4 workflow retirement ledger identity/retirement count drift")
    require(not _git("diff", "--name-only", "HEAD", "--", ".github/workflows").decode().strip(),
            "B4 worktree contains an uncommitted workflow change")
    for path in SOURCE_PINS:
        _identity(path)
    workflow_by_path = {path: _parse_workflow(path) for path, _ in TARGETS}
    expected_triggers = {
        ".github/workflows/create-saturday-2026-08-22-sportybet-direct-20-code.yml": {"pull_request", "workflow_dispatch"},
        ".github/workflows/pr258-sportybet-live-transport-proof.yml": {"pull_request", "workflow_dispatch"},
        ".github/workflows/prb-sportybet-semantic-registry-proof.yml": {"pull_request", "workflow_dispatch"},
        ".github/workflows/probe-sportybet-direct-20-markets.yml": {"pull_request", "workflow_dispatch"},
        ".github/workflows/prove-sportybet-direct-share-code.yml": {"pull_request", "workflow_dispatch"},
    }
    for path, workflow in workflow_by_path.items():
        triggers = workflow.get("on", {})
        require(set(triggers) == expected_triggers[path], f"trigger sibling set drift: {path}")
        require(workflow.get("permissions", {}).get("contents") == "read", f"contents permission drift: {path}")
        raw = (ROOT / path).read_text(encoding="utf-8")
        require("secrets." not in raw, f"B4 workflow acquired secrets.*: {path}")
        require("${{ github.token }}" not in raw and "${{ secrets." not in raw,
                f"B4 workflow acquired an explicit GitHub or external credential binding: {path}")
        require("upload-artifact" in raw, f"run-scoped artifact upload edge disappeared: {path}")
    for path, expected_paths in PATH_FILTERS.items():
        require(workflow_by_path[path]["on"]["pull_request"].get("branches") == ["main"]
                and workflow_by_path[path]["on"]["pull_request"].get("paths") == expected_paths,
                f"exact path-filtered pull_request contract drift: {path}")
    for path in (".github/workflows/pr258-sportybet-live-transport-proof.yml",
                 ".github/workflows/prb-sportybet-semantic-registry-proof.yml"):
        require(workflow_by_path[path]["on"]["pull_request"].get("types") == ["opened", "synchronize", "reopened"],
                f"pull_request activity contract drift: {path}")
        require(workflow_by_path[path]["on"]["workflow_dispatch"] in (None, {}, ""),
                f"manual dispatch unexpectedly has inputs: {path}")
    direct = (ROOT / "scripts/sportybet_direct_share_bridge.py").read_text(encoding="utf-8")
    require('CREATE_PATH = "/api/ng/orders/share?throwInvalidEvent=true"' in direct and
            'LOAD_PREFIX = "/api/ng/orders/share/"' in direct, "direct share create/load contract drift")
    require('method="POST"' in direct and 'method="GET"' in direct, "direct share HTTP methods drift")
    for field in ("sportybet_login_used", "sportybet_cookie_used", "sportybet_wallet_used", "stake_submitted", "wager_placed"):
        require(f'"{field}": False' in direct, f"direct share safety assertion missing: {field}")
    market = (ROOT / "scripts/sportybet_direct_market_probe.py").read_text(encoding="utf-8")
    require('EVENT_PATH = "/api/ng/factsCenter/event"' in market and 'method="GET"' in market,
            "direct market probe GET contract drift")
    require("method=\"POST\"" not in market, "direct market probe unexpectedly gained a POST")
    pr258 = (ROOT / "scripts/run_pr258_sportybet_live_transport_proof.py").read_text(encoding="utf-8")
    for anchor in ("UPCOMING_PATH = \"/api/ng/factsCenter/wapConfigurableUpcomingEvents\"",
                   "live.capture_live_event_quote_evidence(", "semantic_bridge.", "direct_bridge.create_and_roundtrip("):
        require(anchor in pr258, f"PR258 reviewed transport edge missing: {anchor}")
    require('"production_authority_minted": False' in pr258 and '"fixture_reconciliation_authority_from_discovery": False' in pr258,
            "PR258 fail-closed authority boundary drift")
    prb = (ROOT / "scripts/run_prb_sportybet_semantic_registry_proof.py").read_text(encoding="utf-8")
    registry = (ROOT / "domain/current_sportybet_semantic_registry.py").read_text(encoding="utf-8")
    require("scan_current_sportybet_semantic_registry" in prb and "capture_bounded_current_event_discovery" in registry,
            "PR-B discovery/registry call edge drift")
    require("_fetch_upcoming_sample" in registry and "capture_live_event_quote_evidence" in registry,
            "PR-B bounded upcoming fallback or event-detail read edge drift")
    require("anonymous_research_share_code_generation" not in registry and "wager_placed\": False" in registry,
            "PR-B registry authority contract drift")
    require("git ls-remote origin refs/heads/main" in (ROOT / ".github/workflows/prb-sportybet-semantic-registry-proof.yml").read_text(encoding="utf-8"),
            "PR-B manual GitHub read edge missing")
    for path, event in TARGETS:
        config = workflow_by_path[path]["on"][event]
        if event == "pull_request" and path != ".github/workflows/prb-sportybet-semantic-registry-proof.yml":
            require(config.get("branches") == ["main"] and len(config.get("paths", [])) >= 4,
                    f"path-filtered pull_request contract drift: {path}")
        if path == ".github/workflows/prb-sportybet-semantic-registry-proof.yml" and event == "pull_request":
            require("github.head_ref == 'feat/prb-sportybet-semantic-registry'" in workflow_by_path[path]["jobs"]["semantic-registry-proof"]["if"],
                    "PR-B exact head-ref guard drift")


def build_source_inventory() -> dict[str, Any]:
    _validate_source_semantics()
    rows = [_identity(path) for path in sorted(SOURCE_PINS)]
    workflow_contracts = {}
    for path in sorted({p for p, _ in TARGETS}):
        workflow = _parse_workflow(path)
        jobs = {}
        for job_name, job in workflow.get("jobs", {}).items():
            jobs[job_name] = {
                "if": job.get("if"),
                "permissions": job.get("permissions", {}),
                "steps": [{
                    "name": step.get("name"), "if": step.get("if"), "uses": step.get("uses"),
                    "run_sha256": hashlib.sha256(step.get("run", "").encode()).hexdigest()
                    if step.get("run") is not None else None,
                    "continue_on_error": step.get("continue-on-error"),
                    "environment_names": sorted(step.get("env", {})),
                } for step in job.get("steps", [])],
            }
        workflow_contracts[path] = {
            "permissions": workflow.get("permissions", {}),
            "trigger_names": sorted(workflow["on"]),
            "triggers": workflow["on"],
            "jobs": jobs,
            "dynamic_workflow_targets": [],
            "credential_binding_scan": "NO_SECRETS_DOT_EXPLICIT_GITHUB_TOKEN_OR_EXTERNAL_SESSION_BINDING",
        }
    return boundary.seal({
        "schema_version": 1, "policy_id": SOURCE_INVENTORY_POLICY_ID, "repository": "Thabearr/ATHENA",
        "base_main_sha": BASE_MAIN, "base_tree_sha": BASE_TREE, "observed_at_utc": OBSERVED_AT,
        "source_count": len(rows), "sources": rows, "workflow_contracts": workflow_contracts,
        "target_keys": [[path, event] for path, event in TARGETS],
        "repository_caller_scan": _current_repository_callers(),
        "github_run_metadata_observations": _run_observations(),
        "external_side_effect_entrypoints": {
            "sportybet_direct_share": {"method": "POST", "path": "/api/ng/orders/share?throwInvalidEvent=true",
                                         "followed_by": {"method": "GET", "path_prefix": "/api/ng/orders/share/"}},
            "sportybet_direct_market_probe": {"method": "GET", "path": "/api/ng/factsCenter/event"},
            "pr258_upcoming_discovery": {"method": "GET", "path": "/api/ng/factsCenter/wapConfigurableUpcomingEvents"},
            "pr258_or_prb_event_detail": {"method": "GET", "path": "/api/ng/factsCenter/event"},
            "prb_current_discovery": {"method": "GET", "path": "/api/ng/factsCenter/liveOrPrematchEvents"},
            "github_main_ref_fallback": {"method": "git ls-remote", "ref": "refs/heads/main", "write": False},
        },
        "no_workflow_mutation": True, "no_live_execution": True,
        "source_scope": "EXACT_NINE_B4_SURFACES_AND_DIRECT_TRANSITIVE_AUTHORITY_CALLEES_ONLY",
    })


def _run_observations() -> list[dict[str, Any]]:
    return [{"workflow_path": path, **RUN_METADATA[path], "read_only": True,
             "source_url": f"https://api.github.com/repos/Thabearr/ATHENA/actions/runs/{RUN_METADATA[path]['run_id']}",
             "observed_at_utc": OBSERVED_AT,
             "interpretation": "HISTORICAL_RUN_METADATA_ONLY_NOT_CURRENT_AUTHORITY_OR_CURRENT_PROVIDER_PROOF"}
            for path in sorted(RUN_METADATA)]


def _authority(kind: str) -> dict[str, Any]:
    no = "NO_SOURCE_PATH"
    yes = "YES_CURRENTLY_REACHABLE_UNDER_DECLARED_TRIGGER"
    if kind == "share":
        return {
            "sportybet_market_read_authority": no,
            "sportybet_upcoming_discovery_read_authority": no,
            "sportybet_event_detail_read_authority": no,
            "sportybet_share_code_create_authority": yes,
            "sportybet_share_code_reload_authority": yes,
            "sportybet_login_authority": no, "sportybet_cookie_authority": no,
            "sportybet_account_authority": no, "sportybet_wallet_authority": no,
            "sportybet_stake_submission_authority": no, "sportybet_wager_authority": no,
            "model_authority": no, "production_selection_authority": no,
            "fixture_reconciliation_authority": no, "delivery_authority": "NONE_USER_DELIVERY",
            "notification_authority": "NONE_NO_NOTIFICATION_STEP",
            "github_actions_artifact_write_authority": "RUN_SCOPED_ARTIFACT_UPLOAD",
            "github_branch_or_repository_write_authority": "NONE_CONTENTS_READ_ONLY_TOKEN",
            "github_release_write_authority": no, "external_storage_write_authority": no,
            "local_research_evidence_write_authority": "LOCAL_RUNNER_PROOF_FILES",
            "network_authority_summary": ["GITHUB_ACTIONS_AND_PACKAGE_TOOLCHAIN_NETWORK", "SPORTYBET_ANONYMOUS_SHARE_CODE_CREATE_POST", "SPORTYBET_ANONYMOUS_SHARE_CODE_RELOAD_GET"],
        }
    if kind == "market":
        value = _authority("none")
        value.update({"sportybet_market_read_authority": yes,
                      "network_authority_summary": ["GITHUB_ACTIONS_AND_PACKAGE_TOOLCHAIN_NETWORK", "SPORTYBET_ANONYMOUS_EVENT_MARKET_GET"]})
        return value
    if kind == "pr258":
        value = _authority("share")
        value.update({"sportybet_market_read_authority": yes,
                      "sportybet_upcoming_discovery_read_authority": yes,
                      "sportybet_event_detail_read_authority": yes,
                      "network_authority_summary": ["GITHUB_ACTIONS_AND_PACKAGE_TOOLCHAIN_NETWORK", "SPORTYBET_ANONYMOUS_UPCOMING_DISCOVERY_GET", "SPORTYBET_ANONYMOUS_EVENT_DETAIL_GET", "SPORTYBET_ANONYMOUS_SHARE_CODE_CREATE_POST", "SPORTYBET_ANONYMOUS_SHARE_CODE_RELOAD_GET"]})
        return value
    if kind == "prb":
        value = _authority("none")
        value.update({"sportybet_market_read_authority": "ANONYMOUS_LIVE_PROVIDER_OBSERVATION_NOT_PRICING",
                      "sportybet_upcoming_discovery_read_authority": "BOUNDED_ANONYMOUS_DISCOVERY_GET",
                      "sportybet_event_detail_read_authority": "BOUNDED_ANONYMOUS_EVENT_DETAIL_GET",
                      "sportybet_share_code_create_authority": no,
                      "sportybet_share_code_reload_authority": no,
                      "fixture_reconciliation_authority": no,
                      "network_authority_summary": ["GITHUB_ACTIONS_AND_PACKAGE_TOOLCHAIN_NETWORK", "GITHUB_GIT_LS_REMOTE_READ_ON_MANUAL_BASE_FALLBACK", "SPORTYBET_ANONYMOUS_DISCOVERY_GET", "SPORTYBET_ANONYMOUS_EVENT_DETAIL_GET"]})
        return value
    return {
        "sportybet_market_read_authority": no,
        "sportybet_upcoming_discovery_read_authority": no,
        "sportybet_event_detail_read_authority": no,
        "sportybet_share_code_create_authority": no,
        "sportybet_share_code_reload_authority": no,
        "sportybet_login_authority": no, "sportybet_cookie_authority": no,
        "sportybet_account_authority": no, "sportybet_wallet_authority": no,
        "sportybet_stake_submission_authority": no, "sportybet_wager_authority": no,
        "model_authority": no, "production_selection_authority": no,
        "fixture_reconciliation_authority": no, "delivery_authority": "NONE_USER_DELIVERY",
        "notification_authority": "NONE_NO_NOTIFICATION_STEP",
        "github_actions_artifact_write_authority": "RUN_SCOPED_ARTIFACT_UPLOAD",
        "github_branch_or_repository_write_authority": "NONE_CONTENTS_READ_ONLY_TOKEN",
        "github_release_write_authority": no, "external_storage_write_authority": no,
        "local_research_evidence_write_authority": "LOCAL_RUNNER_PROOF_FILES",
        "network_authority_summary": ["GITHUB_ACTIONS_AND_PACKAGE_TOOLCHAIN_NETWORK", "SPORTYBET_ANONYMOUS_LIVE_OR_PREMATCH_DISCOVERY_GET", "SPORTYBET_ANONYMOUS_EVENT_DETAIL_GET"],
    }


def _trigger_contract(path: str, event: str) -> dict[str, Any]:
    on = _parse_workflow(path)["on"]
    value = on[event] or {}
    return {
        "event": event,
        "branch_filters": value.get("branches", []),
        "path_filters": value.get("paths", []),
        "activity_types": value.get("types", []),
        "head_ref_guard": ("github.head_ref == 'feat/prb-sportybet-semantic-registry'"
                           if path == ".github/workflows/prb-sportybet-semantic-registry-proof.yml" and event == "pull_request" else None),
        "workflow_dispatch_input_schema": value.get("inputs", {}),
        "concurrency": _parse_workflow(path).get("concurrency", {}),
        "job_guard": _parse_workflow(path).get("jobs", {}).get(
            "live-transport-proof" if path.endswith("pr258-sportybet-live-transport-proof.yml") else "semantic-registry-proof", {}).get("if")
            if path.endswith(("pr258-sportybet-live-transport-proof.yml", "prb-sportybet-semantic-registry-proof.yml")) else None,
    }


def _kind(path: str) -> str:
    if path.endswith("create-saturday-2026-08-22-sportybet-direct-20-code.yml") or path.endswith("prove-sportybet-direct-share-code.yml"):
        return "share"
    if path.endswith("probe-sportybet-direct-20-markets.yml"):
        return "market"
    if path.endswith("pr258-sportybet-live-transport-proof.yml"):
        return "pr258"
    if path.endswith("prb-sportybet-semantic-registry-proof.yml"):
        return "prb"
    raise AssertionError(f"unrecognized B4 target: {path}")


def _local_paths(path: str) -> list[str]:
    if path.endswith("create-saturday-2026-08-22-sportybet-direct-20-code.yml"):
        return [".cache/athena-research/sportybet-direct-final-20", ".cache/athena-research/sportybet-direct-final-20.summary.json"]
    if path.endswith("pr258-sportybet-live-transport-proof.yml"):
        return [".cache/athena-research/pr258-live-transport-proof"]
    if path.endswith("prb-sportybet-semantic-registry-proof.yml"):
        return [".cache/athena-research/prb-sportybet-semantic-registry-proof"]
    if path.endswith("probe-sportybet-direct-20-markets.yml"):
        return [".cache/athena-research/sportybet-direct-20-market-probe"]
    if path.endswith("prove-sportybet-direct-share-code.yml"):
        return [".cache/athena-research/sportybet-direct-share-proof", ".cache/athena-research/sportybet-direct-share-proof.summary.json"]
    raise AssertionError(f"unrecognized B4 local evidence path: {path}")


def build_receipt() -> dict[str, Any]:
    _validate_source_semantics()
    inventory = build_source_inventory()
    inv_sha = inventory["canonical_sha256"]
    review_rows = []
    for path, event in TARGETS:
        source = next(row for row in inventory["sources"] if row["path"] == path)
        reachability = TARGET_REACHABILITY[(path, event)]
        review_rows.append({
            "identity": {"workflow_path": path, "trigger_kind": event,
                         "git_blob_sha1": source["git_blob_sha1"],
                         "normalized_source_sha256": source["normalized_source_sha256"]},
            "trigger_contract": _trigger_contract(path, event),
            "reachability": {
                "physical_trigger_runtime_authority": reachability,
                "reason": ("future pull_request to main matching the declared path filter can run the workflow"
                           if reachability == "CONDITIONALLY_REACHABLE_PULL_REQUEST_PATH_FILTERED" else
                           "head-ref guard is source-declared and the matching branch name is recreatable; no exact PR-number binding"
                           if reachability == "CONDITIONALLY_REACHABLE_PULL_REQUEST_EXACT_HEAD_REF" else
                           "workflow_dispatch is physically declared and manually invocable; no repository caller is required"),
                "repository_caller_state": "NO_CURRENT_REPOSITORY_CALLER_FOUND_SOURCE_SCAN",
                "manual_control_plane_state": ("DECLARED_AND_MANUALLY_REACHABLE" if event == "workflow_dispatch" else "NOT_THIS_TRIGGER"),
                "historical_actions_rerun_residual": "HISTORICAL_ACTIONS_RERUN_RESIDUAL_NOT_PROVEN_ABSENT",
                "sibling_trigger_state": ("PR258_PULL_REQUEST_RESOLVED_BY_B1_OUT_OF_SCOPE" if path.endswith("pr258-sportybet-live-transport-proof.yml") else
                                           "OTHER_DECLARED_SIBLING_TRIGGER_REMAINS_SEPARATE_AND_NOT_RECLASSIFIED"),
            },
            "permissions_and_credentials": {
                "workflow_permissions": _parse_workflow(path).get("permissions", {}),
                "explicit_secrets_bindings": [], "explicit_github_token_bindings": [],
                "checkout_persisted_token": "ACTIONS_CHECKOUT_DEFAULT_TOKEN_SCOPED_BY_CONTENTS_READ_PERMISSION",
                "environment_credentials": "NO_SOURCE_LOADED_SPORTYBET_ACCOUNT_OR_SESSION_CREDENTIALS",
                "package_and_action_network": "GITHUB_ACTIONS_AND_PACKAGE_INDEX_TOOLCHAIN_TRANSPORT_NOT_SPORTYBET_PRODUCT_AUTHORITY",
            },
            "dynamic_reachability": {
                "source_edges": EDGE_MAP[path],
                "local_research_evidence_paths": _local_paths(path),
                "artifact_upload": "RUN_SCOPED_GITHUB_ACTIONS_ARTIFACT_WRITE",
                "branch_or_repository_write": "NONE_WORKFLOW_PERMISSION_CONTENTS_READ_AND_NO_GIT_PUSH_CALL",
                "release_write": "NONE_NO_RELEASE_API_OR_PUBLISH_ACTION",
                "external_storage_write": "NONE_NO_DRIVE_OR_EXTERNAL_STORAGE_CLIENT",
                "notification": "NONE_NO_EMAIL_ISSUE_COMMENT_OR_USER_NOTIFICATION_STEP",
                "prb_git_ls_remote": "GITHUB_GIT_READ_ONLY_MAIN_REF_LOOKUP_ON_MANUAL_BASE_FALLBACK" if _kind(path) == "prb" else "NOT_PRESENT_IN_THIS_CALL_PATH",
            },
            "authority": _authority(_kind(path)),
            "support_disposition": {
                "product_supported_current_operation_dependency": "NONE_RETAINED_RESEARCH_ONLY",
                "retained_research_historical_status": "RETAINED_RESEARCH_CAPABILITY_SOURCE_AND_TRIGGER_REMAIN_PRESENT",
                "physical_trigger_runtime_authority": reachability,
            },
            "historical_run_metadata": next((row for row in _run_observations() if row["workflow_path"] == path), None),
            "review": {"status": "RESOLVED", "blocker": None},
        })
    parent = boundary.read(COMPLETION_V6_PATH)
    return boundary.seal({
        "schema_version": 1, "policy_id": POLICY_ID, "repository": "Thabearr/ATHENA", "master_issue": 337,
        "base_main_sha": BASE_MAIN, "base_tree_sha": BASE_TREE,
        "predecessor_completion_v6": {"path": COMPLETION_V6_PATH, "canonical_sha256": COMPLETION_V6_SHA, "rewritten": False},
        "predecessor_b3_receipt": {"path": B3_RECEIPT_PATH, "canonical_sha256": B3_RECEIPT_SHA, "rewritten": False},
        "predecessor_b3_source_inventory": {"path": B3_INVENTORY_PATH, "canonical_sha256": B3_INVENTORY_SHA, "rewritten": False},
        "a2_v5": {"path": A2_V5_PATH, "canonical_sha256": A2_V5_SHA, "generation": 5, "rewritten": False},
        "a2_v6": {"path": boundary.inventory_generation_path(6), "generation": 6,
                   "predecessor_path": A2_V5_PATH, "predecessor_canonical_sha256": A2_V5_SHA, "rewritten": False},
        "source_inventory": {"path": SOURCE_INVENTORY_PATH, "canonical_sha256": inv_sha},
        "scope": {"inherited_unresolved_surface_count": 16, "target_surface_count": 9,
                  "resolved_target_count": len([r for r in review_rows if r["review"]["status"] == "RESOLVED"]),
                  "partial_target_count": len([r for r in review_rows if r["review"]["status"] != "RESOLVED"]),
                  "global_unresolved_before": 16,
                  "global_unresolved_after": 16 - len([r for r in review_rows if r["review"]["status"] == "RESOLVED"]),
                  "target_keys": [[path, event] for path, event in TARGETS]},
        "review_rows": review_rows,
        "remaining_unreviewed_surface_keys": [[r["workflow_path"], r["trigger_kind"]]
                                                for r in parent["unreviewed_authority_surfaces"] if (r["workflow_path"], r["trigger_kind"]) not in set(TARGETS)],
        "workflow_tree_sha1": WORKFLOW_TREE, "evolution_ledger_sha256": EVOLUTION_SHA,
        "evolution_transition_count": 14, "retirement_ledger_sha256": RETIREMENT_SHA,
        "retired_workflow_count": 3, "workflow_count": 39, "trigger_surface_count": 57,
        "workflow_edit_count": 0, "trigger_edit_count": 0, "retirement_count": 0,
        "deletion_count": 0, "caller_migration_count": 0, "actions": ZERO_ACTIONS,
        "source_review_counter_while_open": "3/5", "source_review_counter_if_owner_merges": "4/5",
        "mandatory_governing_source_reread_after_b4_merge": False,
        "checkpoint_e_status": "INCOMPLETE", "p4_4_status": "INCOMPLETE",
        "criterion_11": False, "criterion_14": False,
        "terminal": "CORE_01D_SPORTYBET_CURRENT_TRIGGER_AUTHORITY_B4_REVIEW_READY_9_RESOLVED_DO_NOT_MERGE",
    })


def validate_source_inventory(value: dict[str, Any] | None = None) -> dict[str, Any]:
    if value is None:
        value = boundary.read(SOURCE_INVENTORY_PATH)
    require((ROOT / SOURCE_INVENTORY_PATH).read_bytes() == boundary.canonical(value), "B4 source inventory is not canonical")
    require(value == build_source_inventory(), "B4 source inventory differs from authenticated source/metadata")
    require(value["base_main_sha"] == BASE_MAIN and value["base_tree_sha"] == BASE_TREE, "B4 inventory base drift")
    require(value["target_keys"] == [[p, e] for p, e in TARGETS], "B4 inventory expanded or changed target scope")
    require(value["repository_caller_scan"]["result"] == "NO_CURRENT_REPOSITORY_CALLER_FOUND_SOURCE_SCAN",
            "B4 repository caller scan found an unreviewed candidate")
    return value


def validate_receipt(value: dict[str, Any] | None = None) -> dict[str, Any]:
    if value is None:
        value = boundary.read(RECEIPT_PATH)
    require((ROOT / RECEIPT_PATH).read_bytes() == boundary.canonical(value), "B4 receipt is not canonical")
    expected = build_receipt()
    require(value == expected, "B4 receipt differs from exact source and predecessor derivation")
    rows = value["review_rows"]
    require(len(rows) == 9 and len({(r["identity"]["workflow_path"], r["identity"]["trigger_kind"]) for r in rows}) == 9,
            "B4 review must contain nine unique target surfaces")
    require(all(r["review"]["status"] == "RESOLVED" for r in rows), "B4 contains partial target evidence")
    require(value["scope"]["global_unresolved_after"] == 7, "B4 unresolved count must derive to seven")
    require(value["criterion_11"] is False and value["criterion_14"] is False and
            value["checkpoint_e_status"] == value["p4_4_status"] == "INCOMPLETE", "B4 cannot complete Checkpoint E")
    require(value["actions"] == ZERO_ACTIONS, "B4 review performed or claimed a live action")
    return value


def audit() -> dict[str, Any]:
    validate_source_inventory()
    value = validate_receipt()
    return {"result": "PASS", "receipt_sha256": value["canonical_sha256"],
            "source_inventory_sha256": value["source_inventory"]["canonical_sha256"],
            "target_count": 9, "resolved_target_count": 9, "partial_target_count": 0,
            "global_unresolved_before": 16, "global_unresolved_after": 7,
            "criterion_11": False, "criterion_14": False,
            "checkpoint_e_status": "INCOMPLETE", "p4_4_status": "INCOMPLETE",
            "terminal": value["terminal"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-source-inventory", action="store_true")
    parser.add_argument("--write-receipt", action="store_true")
    args = parser.parse_args()
    if args.write_source_inventory:
        value = build_source_inventory()
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
