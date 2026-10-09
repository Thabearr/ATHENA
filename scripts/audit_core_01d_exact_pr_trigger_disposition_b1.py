"""Authenticate the bounded exact-PR pull_request disposition for CORE-01D B1.

This audit consumes committed read-only GitHub metadata and source identities. It
never queries GitHub or executes a workflow. It distinguishes merged-PR event
reachability from the guarded authority available after an event is delivered.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

import yaml

from scripts.audit_data_01c_restore_portability import historical_workflow_tree

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary

ROOT = Path(__file__).resolve().parents[1]
BASE_MAIN = "48f5896ccc6fa30e49b1cba636cc6e1e498a235a"
BASE_TREE = "7267d80ce43c46d0d67295e8fafd98abd6c2a692"
WORKFLOW_TREE = "9b08653f1a12bb1b3d964fbd910396ff955740da"
EVOLUTION_SHA = "73e1eb3fe6593558c821600dd0f103353d45c15a139ab470a996c7cbb35da531"
RETIREMENT_SHA = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
V1_INVENTORY_SHA = "ca8c07c071538298ffb293027e7a0be1c5766e8a943b3d2b605627f9ffe922dd"
V2_INVENTORY_SHA = "c7b12447b7f671b2ece76d1207b404cd4555cc45d2e2ec88451682d6e0b4f14e"
A2_RECEIPT_SHA = "5d0385f77463d3e7a9f804b431df7e2c2c9c4908c266326bf35b05a50086f8e2"
BRIDGE_RECEIPT_SHA = "6ba76fc9362db44df9c901784b7bdea0ab9284c0db763e8168eefc83ab2e3a8d"
COMPLETION_V3_SHA = "27516b35fb5e836ac2d851fa60e4300ebf347e00b00f3858b46671cd77af9d79"
COMPLETION_V2_SHA = "f9f49f22810bd789ed5774fba1dc2b239ca0de84606a0dd7cf0c5d4de9d9026e"
PASS_A_SHA = "9db3362af83eda04b6f005328b5d44f253fcd15ef5f39a62983cc6c3ff402521"
MATRIX_V2_SHA = "3c3cfec8b37e55161b24185941e72c3e096a00f38456a2c07a9072b62e31e5b7"
RETAINED_V5_SHA = "c90d71a04f54c29ed094b262f0aef6cad9067316c6d548227f1c4c289a4abebf"
SOURCE_INVENTORY_PATH = "tests/fixtures/core_01d/exact-pr-trigger-disposition-b1-source-inventory-v1.json"
RECEIPT_PATH = "tests/fixtures/core_01d/core-01d-exact-pr-trigger-disposition-b1-v1.json"
COMPLETION_V3_PATH = "artifacts/architecture/core_01d_checkpoint_e_completion_v3.json"
POLICY_ID = "ATHENA_CORE_01D_EXACT_PR_TRIGGER_DISPOSITION_B1_V1"
SOURCE_INVENTORY_SHA256 = "0319548793ac2c2fee576e6445d271148638478b70ab339cf05511e2247fa074"
CURRENT_SOURCE_IDENTITIES_SHA256 = "4f65403d61777e3b88ad4d402149654ac942e8704cb4ebaf4a84e1b743b6d063"
HISTORICAL_SOURCE_IDENTITIES_SHA256 = "17608b3becd5ddedf8ab8f8b3234409e853e2229524678b8b6042032f1d2e259"

PR_HEADS = {
    258: "d159bf959e15ce23f8d56766f105dbd03f1b6549",
    199: "b879b2140d0bc3fb64fa8fec4c73c735240a3b41",
    200: "7a93b553b785bc7b3518b32575da9cb212c8cdd4",
    201: "090487c7cbb46996fb819790afed6b5b67d260ab",
    192: "46f76e8033d3d498131c6f893111b437b6b459a9",
    202: "09b9a8f4afdc18d4165d531958f087130566ac20",
}

TARGETS = {
    ".github/workflows/pr258-sportybet-live-transport-proof.yml#pull_request": {
        "path": ".github/workflows/pr258-sportybet-live-transport-proof.yml",
        "pr": 258,
        "head_ref": "feature/pr258-research-shadow-sportybet-field-trial",
        "base_sha": None,
        "base_branch_filter": None,
        "event_types": ["opened", "synchronize", "reopened"],
        "explicit_event_types": True,
        "job": "live-transport-proof",
        "steps": ["Run bounded real SportyBet transport proof"],
        "siblings": [".github/workflows/pr258-sportybet-live-transport-proof.yml#workflow_dispatch"],
        "history": {
            "provider_acquisition_authority": "NONE_NO_FOTMOB_ACQUISITION",
            "sportsbook_read_authority": "SPORTYBET_PUBLIC_EVENT_AND_MARKET_READ",
            "share_code_authority": "ANONYMOUS_PROOF_CREATE_AND_RELOAD",
            "wager_authority": "NONE",
            "delivery_authority": "NONE_NO_USER_FACING_DELIVERY",
            "notification_authority": "GITHUB_STEP_SUMMARY_ONLY",
            "artifact_read_authority": "NONE",
            "artifact_write_authority": "RUN_SCOPED_PR258_PROOF_ARTIFACT_WRITE",
            "github_api_read_authority": "NONE_FROM_JOB_CODE",
            "github_api_write_authority": "NONE",
            "release_read_authority": "NONE",
            "release_write_authority": "NONE",
            "issue_comment_write_authority": "NONE",
            "pull_request_mutation_authority": "NONE",
            "branch_or_repository_write_authority": "NONE_CONTENTS_READ_ONLY",
            "workflow_dispatch_authority": "NONE_FROM_PULL_REQUEST_SURFACE",
            "external_storage_write_authority": "NONE",
            "database_or_canonical_store_write_authority": "NONE",
            "model_or_research_execution_authority": "RESEARCH_SHADOW_TRANSPORT_PROOF_NO_MODEL_SELECTION",
            "credential_surface": "NO_SECRETS; ACTIONS_CHECKOUT_IMPLICIT_READ_ONLY_GITHUB_TOKEN; ANONYMOUS_PUBLIC_SPORTYBET_TRANSPORT",
            "network_authority_summary": "PUBLIC_SPORTYBET_UPCOMING_AND_EVENT_GETS_PLUS_ANONYMOUS_SHARE_CREATE_POST_AND_RELOAD_GET; PYPI_INSTALL; NO_LOGIN_COOKIE_WALLET_STAKE_OR_WAGER",
        },
        "callee_edges": [
            {"source": ".github/workflows/pr258-sportybet-live-transport-proof.yml", "step": "Run bounded real SportyBet transport proof", "line": 38, "callee": "scripts.run_pr258_sportybet_live_transport_proof:main/run", "classification": "SOURCE_BOUND_LIVE_RESEARCH_SHADOW_RUNNER"},
            {"source": "scripts/run_pr258_sportybet_live_transport_proof.py", "symbol": "_fetch_upcoming_sample", "line": 98, "callee": "SportyBet upcoming public HTTP GET", "classification": "PUBLIC_SPORTYBET_READ"},
            {"source": "scripts/run_pr258_sportybet_live_transport_proof.py", "symbol": "_capture_candidate", "line": 194, "callee": "domain.sportybet_live_event_quote_evidence.capture_live_event_quote_evidence", "classification": "PUBLIC_SPORTYBET_EVENT_READ"},
            {"source": "scripts/run_pr258_sportybet_live_transport_proof.py", "symbol": "run", "line": 354, "callee": "scripts.sportybet_direct_share_bridge.create_and_roundtrip", "classification": "ANONYMOUS_SHARE_CREATE_AND_RELOAD"},
            {"source": "scripts/sportybet_direct_share_bridge.py", "symbol": "create_and_roundtrip", "line": 270, "callee": "SportyBet POST /api/ng/orders/share", "classification": "SHARE_CODE_CREATE"},
            {"source": "scripts/sportybet_direct_share_bridge.py", "symbol": "create_and_roundtrip", "line": 278, "callee": "SportyBet GET /api/ng/orders/share/{code}", "classification": "SHARE_CODE_RELOAD_READ"},
        ],
    },
    ".github/workflows/capture-saturday-2026-08-22-fixture-universe.yml#pull_request": {
        "path": ".github/workflows/capture-saturday-2026-08-22-fixture-universe.yml",
        "pr": 199,
        "head_ref": "evidence/saturday-2026-08-22-fixture-universe-capture",
        "base_sha": "a149d523ee4e8859bfead7b7a42bfcb002fc37a8",
        "base_branch_filter": None,
        "event_types": ["edited"],
        "explicit_event_types": True,
        "job": "capture",
        "steps": ["Capture exact Saturday fixture universe"],
        "siblings": [],
        "history": {
            "provider_acquisition_authority": "FOTMOB_READ_ONLY_SOURCE_CAPTURE",
            "sportsbook_read_authority": "NONE",
            "share_code_authority": "NONE",
            "wager_authority": "NONE",
            "delivery_authority": "NONE_NO_USER_FACING_DELIVERY",
            "notification_authority": "GITHUB_STEP_SUMMARY_ONLY",
            "artifact_read_authority": "NONE",
            "artifact_write_authority": "RUN_SCOPED_FOTMOB_FIXTURE_UNIVERSE_EVIDENCE_WRITE",
            "github_api_read_authority": "OWNER_GATED_PR_EVENT_CONTEXT_READ_ONLY",
            "github_api_write_authority": "NONE",
            "release_read_authority": "NONE",
            "release_write_authority": "NONE",
            "issue_comment_write_authority": "NONE",
            "pull_request_mutation_authority": "NONE",
            "branch_or_repository_write_authority": "NONE_CONTENTS_READ_ONLY",
            "workflow_dispatch_authority": "NONE",
            "external_storage_write_authority": "NONE",
            "database_or_canonical_store_write_authority": "RUNNER_LOCAL_CAPTURE_EVIDENCE_ONLY_NO_SHARED_STORE",
            "model_or_research_execution_authority": "PROSPECTIVE_FIXTURE_UNIVERSE_CAPTURE_UNREVIEWED",
            "credential_surface": "NO_SECRETS; JOB_TOKEN_READ_ONLY_ACTIONS_CONTENTS_PULL_REQUESTS",
            "network_authority_summary": "BOUNDED_FOTMOB_DATA_MATCHES_GET_REQUIRES_EXACT_HEAD_AND_EXECUTE_LIVE_NETWORK; PYPI_INSTALL; NO_SPORTSBOOK_OR_USER_DELIVERY",
        },
        "callee_edges": [
            {"source": ".github/workflows/capture-saturday-2026-08-22-fixture-universe.yml", "step": "Capture exact Saturday fixture universe", "line": 112, "callee": "scripts.capture_saturday_2026_08_22_fixture_universe:main/execute", "classification": "OWNER_GATED_LIVE_FOTMOB_CAPTURE"},
            {"source": ".github/workflows/capture-saturday-2026-08-22-fixture-universe.yml", "step": "Capture exact Saturday fixture universe", "line": 114, "callee": "--execute-live-network", "classification": "EXPLICIT_LIVE_NETWORK_GATE"},
            {"source": "scripts/capture_saturday_2026_08_22_fixture_universe.py", "symbol": "execute", "line": 122, "callee": "scripts.capture_fotmob_data_matches.fetch_fotmob_data_matches", "classification": "FOTMOB_DATA_MATCHES_READ"},
            {"source": "scripts/capture_fotmob_data_matches.py", "symbol": "fetch_fotmob_data_matches", "line": 141, "callee": "FotMob fixed-host HTTPS GET", "classification": "BOUNDED_FOTMOB_PROVIDER_READ"},
        ],
    },
    ".github/workflows/verify-saturday-competition-review-priority.yml#pull_request": {
        "path": ".github/workflows/verify-saturday-competition-review-priority.yml",
        "pr": 200,
        "head_ref": "policy/competition-fixture-review-priority",
        "base_sha": "19b5574ddc610cb7f231c51143580d38f89ea35f",
        "base_branch_filter": "main",
        "event_types": ["opened", "synchronize", "reopened"],
        "explicit_event_types": False,
        "job": "verify",
        "steps": ["Replay exact source through competition review policy"],
        "siblings": [],
        "history": {
            "provider_acquisition_authority": "NONE_EXACT_EXISTING_ACTIONS_ARTIFACT_ONLY",
            "sportsbook_read_authority": "NONE",
            "share_code_authority": "NONE",
            "wager_authority": "NONE",
            "delivery_authority": "NONE_NO_USER_FACING_DELIVERY",
            "notification_authority": "GITHUB_CHECK_AND_LOG_ONLY",
            "artifact_read_authority": "CROSS_RUN_READ_EXACT_ARTIFACT_9437181220",
            "artifact_write_authority": "RUN_SCOPED_COMPETITION_REVIEW_REPORT_WRITE",
            "github_api_read_authority": "READ_PR_CONTEXT_AND_EXACT_ARTIFACT_RUN_METADATA",
            "github_api_write_authority": "NONE_READ_METHODS_ONLY",
            "release_read_authority": "NONE",
            "release_write_authority": "NONE",
            "issue_comment_write_authority": "NONE",
            "pull_request_mutation_authority": "NONE",
            "branch_or_repository_write_authority": "NONE_CONTENTS_READ_ONLY",
            "workflow_dispatch_authority": "NONE",
            "external_storage_write_authority": "NONE",
            "database_or_canonical_store_write_authority": "NONE_LOCAL_VERIFICATION_OUTPUT_ONLY",
            "model_or_research_execution_authority": "OFFLINE_EXACT_SOURCE_COMPETITION_POLICY_REPLAY",
            "credential_surface": "NO_SECRETS; JOB_TOKEN_READ_ONLY_ACTIONS_CONTENTS_PULL_REQUESTS",
            "network_authority_summary": "READ_ONLY_GITHUB_ACTIONS_METADATA_AND_EXACT_ARTIFACT_PLUS_PYPI_INSTALL; REPLAY_CODE_IS_LOCAL_AND_DETERMINISTIC",
        },
        "callee_edges": [
            {"source": ".github/workflows/verify-saturday-competition-review-priority.yml", "step": "Validate exact PR and frozen source artifact", "line": 46, "callee": "github.rest.actions.getArtifact(9437181220)", "classification": "GITHUB_ACTIONS_EXACT_ARTIFACT_METADATA_READ"},
            {"source": ".github/workflows/verify-saturday-competition-review-priority.yml", "step": "Validate exact PR and frozen source artifact", "line": 63, "callee": "github.rest.actions.getWorkflowRun(32455713912)", "classification": "GITHUB_ACTIONS_RUN_METADATA_READ"},
            {"source": ".github/workflows/verify-saturday-competition-review-priority.yml", "step": "Download exact PR199 Saturday source artifact", "line": 109, "callee": "actions/download-artifact exact id 9437181220/run 32455713912", "classification": "CROSS_RUN_EXACT_ARTIFACT_READ"},
            {"source": ".github/workflows/verify-saturday-competition-review-priority.yml", "step": "Replay exact source through competition review policy", "line": 124, "callee": "inline deterministic source-candidate/policy replay", "classification": "LOCAL_NO_PROVIDER_IO"},
            {"source": ".github/workflows/verify-saturday-competition-review-priority.yml", "step": "Upload replayed competition-review report", "line": 231, "callee": "actions/upload-artifact run-scoped report", "classification": "RUN_SCOPED_ARTIFACT_WRITE"},
        ],
    },
    ".github/workflows/verify-saturday-2026-08-22-fixture-identity-review.yml#pull_request": {
        "path": ".github/workflows/verify-saturday-2026-08-22-fixture-identity-review.yml",
        "pr": 201,
        "head_ref": "evidence/saturday-2026-08-22-fixture-identity-review",
        "base_sha": "5a77c55b939ac447f8409b945a576d5a9ad3b26a",
        "base_branch_filter": "main",
        "event_types": ["opened", "synchronize", "reopened"],
        "explicit_event_types": False,
        "job": "verify",
        "steps": ["Run focused explicit-review test", "Replay exact 50-fixture explicit identity review"],
        "siblings": [],
        "history": {
            "provider_acquisition_authority": "NONE_EXACT_EXISTING_ACTIONS_ARTIFACT_ONLY",
            "sportsbook_read_authority": "NONE",
            "share_code_authority": "NONE",
            "wager_authority": "NONE",
            "delivery_authority": "NONE_NO_USER_FACING_DELIVERY",
            "notification_authority": "GITHUB_STEP_SUMMARY_ONLY",
            "artifact_read_authority": "CROSS_RUN_READ_EXACT_ARTIFACT_9437181220",
            "artifact_write_authority": "RUN_SCOPED_EXPLICIT_IDENTITY_REVIEW_PROOF_WRITE",
            "github_api_read_authority": "READ_PR_CONTEXT_AND_EXACT_ARTIFACT_RUN_METADATA",
            "github_api_write_authority": "NONE_READ_METHODS_ONLY",
            "release_read_authority": "NONE",
            "release_write_authority": "NONE",
            "issue_comment_write_authority": "NONE",
            "pull_request_mutation_authority": "NONE",
            "branch_or_repository_write_authority": "NONE_CONTENTS_READ_ONLY",
            "workflow_dispatch_authority": "NONE",
            "external_storage_write_authority": "NONE",
            "database_or_canonical_store_write_authority": "NONE_LOCAL_REVIEW_OUTPUT_ONLY",
            "model_or_research_execution_authority": "EXPLICIT_FIXTURE_IDENTITY_REVIEW_REPLAY_ONLY",
            "credential_surface": "NO_SECRETS; JOB_TOKEN_READ_ONLY_ACTIONS_CONTENTS_PULL_REQUESTS",
            "network_authority_summary": "READ_ONLY_GITHUB_ACTIONS_METADATA_AND_EXACT_ARTIFACT_PLUS_PYPI_INSTALL; REPLAY_CODE_IS_LOCAL_AND_DETERMINISTIC",
        },
        "callee_edges": [
            {"source": ".github/workflows/verify-saturday-2026-08-22-fixture-identity-review.yml", "step": "Validate exact PR and frozen PR199 source evidence", "line": 46, "callee": "github.rest.actions.getArtifact(9437181220)", "classification": "GITHUB_ACTIONS_EXACT_ARTIFACT_METADATA_READ"},
            {"source": ".github/workflows/verify-saturday-2026-08-22-fixture-identity-review.yml", "step": "Validate exact PR and frozen PR199 source evidence", "line": 63, "callee": "github.rest.actions.getWorkflowRun(32455713912)", "classification": "GITHUB_ACTIONS_RUN_METADATA_READ"},
            {"source": ".github/workflows/verify-saturday-2026-08-22-fixture-identity-review.yml", "step": "Run focused explicit-review test", "line": 112, "callee": "tests.test_saturday_2026_08_22_fixture_identity_review", "classification": "LOCAL_DETERMINISTIC_TEST"},
            {"source": ".github/workflows/verify-saturday-2026-08-22-fixture-identity-review.yml", "step": "Download exact PR199 Saturday source artifact", "line": 115, "callee": "actions/download-artifact exact id 9437181220/run 32455713912", "classification": "CROSS_RUN_EXACT_ARTIFACT_READ"},
            {"source": ".github/workflows/verify-saturday-2026-08-22-fixture-identity-review.yml", "step": "Replay exact 50-fixture explicit identity review", "line": 131, "callee": "scripts.verify_saturday_2026_08_22_fixture_identity_review:main/execute", "classification": "OFFLINE_EXACT_ARTIFACT_REPLAY"},
            {"source": ".github/workflows/verify-saturday-2026-08-22-fixture-identity-review.yml", "step": "Upload exact explicit fixture-identity review proof", "line": 176, "callee": "actions/upload-artifact run-scoped proof", "classification": "RUN_SCOPED_ARTIFACT_WRITE"},
        ],
    },
    ".github/workflows/execute-fotmob-prospective-player-context-campaign.yml#pull_request": {
        "path": ".github/workflows/execute-fotmob-prospective-player-context-campaign.yml",
        "pr": 192,
        "head_ref": "evidence/fotmob-prospective-player-context-campaign",
        "base_sha": "74cec8bc649bc8d2181ca2806a460a84664f7f2e",
        "base_branch_filter": None,
        "event_types": ["edited"],
        "explicit_event_types": True,
        "job": "capture",
        "steps": ["Execute transparent prospective campaign stage"],
        "siblings": [],
        "history": {
            "provider_acquisition_authority": "FOTMOB_PROSPECTIVE_FIXTURE_AND_PLAYER_CONTEXT_READ_ONLY_CAPTURE",
            "sportsbook_read_authority": "NONE",
            "share_code_authority": "NONE",
            "wager_authority": "NONE",
            "delivery_authority": "NONE_NO_USER_FACING_DELIVERY",
            "notification_authority": "GITHUB_STEP_SUMMARY_ONLY",
            "artifact_read_authority": "CONDITIONAL_EXACT_ACTIONS_ARTIFACT_READ_FOR_CONTINUATION_MODE",
            "artifact_write_authority": "RUN_SCOPED_PROSPECTIVE_PLAYER_CONTEXT_EVIDENCE_WRITE",
            "github_api_read_authority": "READ_PR_CONTEXT_AND_EXACT_SOURCE_ARTIFACT_RUN_METADATA",
            "github_api_write_authority": "NONE_READ_METHODS_ONLY",
            "release_read_authority": "NONE",
            "release_write_authority": "NONE",
            "issue_comment_write_authority": "NONE",
            "pull_request_mutation_authority": "NONE",
            "branch_or_repository_write_authority": "NONE_CONTENTS_READ_ONLY",
            "workflow_dispatch_authority": "NONE",
            "external_storage_write_authority": "NONE",
            "database_or_canonical_store_write_authority": "RUNNER_LOCAL_CAMPAIGN_AND_TEMPORARY_CATALOG_EVIDENCE_ONLY_NO_SHARED_STORE",
            "model_or_research_execution_authority": "PROSPECTIVE_PLAYER_CONTEXT_EVIDENCE_CAMPAIGN_NO_PRODUCTION_MODEL_AUTHORITY",
            "credential_surface": "NO_SECRETS; JOB_TOKEN_READ_ONLY_ACTIONS_CONTENTS_PULL_REQUESTS; EXACT_BODY_FIELDS_GATE_CONDITIONAL_ARTIFACT_READ",
            "network_authority_summary": "FOTMOB_DATA_MATCHES_AND_REVIEWED_MATCH_DETAILS_READS_REQUIRE_EXECUTE_LIVE_NETWORK; CONDITIONAL_GITHUB_ACTIONS_METADATA_AND_EXACT_ARTIFACT_READ; PYPI_INSTALL",
        },
        "callee_edges": [
            {"source": ".github/workflows/execute-fotmob-prospective-player-context-campaign.yml", "step": "Validate exact owner control block and source artifact", "line": 99, "callee": "github.rest.actions.getArtifact(body-bound exact id/name/digest/run/head)", "classification": "CONDITIONAL_GITHUB_ACTIONS_EXACT_ARTIFACT_METADATA_READ"},
            {"source": ".github/workflows/execute-fotmob-prospective-player-context-campaign.yml", "step": "Validate exact owner control block and source artifact", "line": 115, "callee": "github.rest.actions.getWorkflowRun(body-bound exact run/head)", "classification": "CONDITIONAL_GITHUB_ACTIONS_RUN_METADATA_READ"},
            {"source": ".github/workflows/execute-fotmob-prospective-player-context-campaign.yml", "step": "Download exact first-run fixture artifact for continuation", "line": 164, "callee": "actions/download-artifact validated continuation identity", "classification": "CONDITIONAL_CROSS_RUN_EXACT_ARTIFACT_READ"},
            {"source": ".github/workflows/execute-fotmob-prospective-player-context-campaign.yml", "step": "Execute transparent prospective campaign stage", "line": 192, "callee": "--execute-live-network; scripts.run_fotmob_prospective_player_context_campaign", "classification": "OWNER_GATED_FOTMOB_CAPTURE"},
            {"source": "scripts/run_fotmob_prospective_player_context_campaign.py", "symbol": "execute:CAPTURE_FIXTURE", "line": 484, "callee": "scripts.capture_fotmob_data_matches.fetch_fotmob_data_matches", "classification": "FOTMOB_DATA_MATCHES_READ"},
            {"source": "scripts/run_fotmob_prospective_player_context_campaign.py", "symbol": "execute:CONTINUE_EXACT_FIXTURE_ARTIFACT", "line": 593, "callee": "scripts.capture_fotmob_reviewed_match_details.capture_fotmob_reviewed_match_details", "classification": "FOTMOB_MATCH_DETAILS_READ"},
            {"source": "scripts/run_fotmob_prospective_player_context_campaign.py", "symbol": "_build_verified_bootstrap", "line": 207, "callee": "scripts.manage_fotmob_reviewed_fixture_catalog.run into campaign-local paths", "classification": "LOCAL_TEMPORARY_CATALOG_EVIDENCE_ONLY"},
        ],
    },
    ".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml#pull_request": {
        "path": ".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml",
        "pr": 202,
        "head_ref": "evidence/saturday-2026-08-22-reviewed-fixture-catalog",
        "base_sha": "08d54c11a4e5fb11ff7d7d886bda95c1efb01f05",
        "base_branch_filter": "main",
        "event_types": ["opened", "synchronize", "reopened"],
        "explicit_event_types": True,
        "job": "verify-pr",
        "steps": ["Run focused reviewed-catalog tests", "Replay exact reviewed catalog and prepare admission decision candidate"],
        "siblings": [".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml#push"],
        "history": {
            "provider_acquisition_authority": "NONE_EXACT_EXISTING_ACTIONS_ARTIFACT_ONLY",
            "sportsbook_read_authority": "NONE",
            "share_code_authority": "NONE",
            "wager_authority": "NONE",
            "delivery_authority": "NONE_NO_USER_FACING_DELIVERY",
            "notification_authority": "GITHUB_STEP_SUMMARY_ONLY",
            "artifact_read_authority": "CROSS_RUN_READ_EXACT_ARTIFACT_9437181220",
            "artifact_write_authority": "RUN_SCOPED_REVIEWED_CATALOG_CANDIDATE_WRITE",
            "github_api_read_authority": "READ_PR_CONTEXT_AND_EXACT_ARTIFACT_RUN_METADATA",
            "github_api_write_authority": "NONE_READ_METHODS_ONLY",
            "release_read_authority": "NONE",
            "release_write_authority": "NONE",
            "issue_comment_write_authority": "NONE",
            "pull_request_mutation_authority": "NONE",
            "branch_or_repository_write_authority": "NONE_CONTENTS_READ_ONLY",
            "workflow_dispatch_authority": "NONE",
            "external_storage_write_authority": "NONE",
            "database_or_canonical_store_write_authority": "NONE_ADMISSION_STORE_NOT_IN_PULL_REQUEST_JOB",
            "model_or_research_execution_authority": "OFFLINE_REVIEWED_CATALOG_CANDIDATE_PREPARATION_NO_ADMISSION",
            "credential_surface": "NO_SECRETS; JOB_TOKEN_READ_ONLY_ACTIONS_CONTENTS_PULL_REQUESTS",
            "network_authority_summary": "READ_ONLY_GITHUB_ACTIONS_METADATA_AND_EXACT_ARTIFACT_PLUS_PYPI_INSTALL; CATALOG_PREPARATION_IS_OFFLINE",
        },
        "callee_edges": [
            {"source": ".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml", "step": "Validate exact PR and frozen source evidence", "line": 51, "callee": "github.rest.actions.getArtifact(9437181220)", "classification": "GITHUB_ACTIONS_EXACT_ARTIFACT_METADATA_READ"},
            {"source": ".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml", "step": "Validate exact PR and frozen source evidence", "line": 68, "callee": "github.rest.actions.getWorkflowRun(32455713912)", "classification": "GITHUB_ACTIONS_RUN_METADATA_READ"},
            {"source": ".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml", "step": "Download exact PR199 Saturday source artifact", "line": 119, "callee": "actions/download-artifact exact id 9437181220/run 32455713912", "classification": "CROSS_RUN_EXACT_ARTIFACT_READ"},
            {"source": ".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml", "step": "Replay exact reviewed catalog and prepare admission decision candidate", "line": 134, "callee": "scripts.prepare_saturday_2026_08_22_reviewed_fixture_catalog:main/execute", "classification": "OFFLINE_CATALOG_CANDIDATE_PREPARATION"},
            {"source": ".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml", "step": "Upload exact PR-head reviewed catalog proof", "line": 160, "callee": "actions/upload-artifact run-scoped candidate", "classification": "RUN_SCOPED_ARTIFACT_WRITE"},
        ],
    },
    ".github/workflows/verify-competition-review-priority-tests.yml#pull_request": {
        "path": ".github/workflows/verify-competition-review-priority-tests.yml",
        "pr": 200,
        "head_ref": "policy/competition-fixture-review-priority",
        "base_sha": "19b5574ddc610cb7f231c51143580d38f89ea35f",
        "base_branch_filter": "main",
        "event_types": ["opened", "synchronize", "reopened"],
        "explicit_event_types": False,
        "job": "test",
        "steps": ["Run focused competition-priority tests"],
        "siblings": [],
        "history": {
            "provider_acquisition_authority": "NONE",
            "sportsbook_read_authority": "NONE",
            "share_code_authority": "NONE",
            "wager_authority": "NONE",
            "delivery_authority": "NONE_NO_USER_FACING_DELIVERY",
            "notification_authority": "GITHUB_CHECK_AND_LOG_ONLY",
            "artifact_read_authority": "NONE",
            "artifact_write_authority": "NONE",
            "github_api_read_authority": "NONE_FROM_TEST_JOB_CODE",
            "github_api_write_authority": "NONE_CONTENTS_READ_ONLY_AND_CHECKOUT_CREDENTIALS_DISABLED",
            "release_read_authority": "NONE",
            "release_write_authority": "NONE",
            "issue_comment_write_authority": "NONE",
            "pull_request_mutation_authority": "NONE",
            "branch_or_repository_write_authority": "NONE_CONTENTS_READ_ONLY",
            "workflow_dispatch_authority": "NONE",
            "external_storage_write_authority": "NONE",
            "database_or_canonical_store_write_authority": "NONE_LOCAL_UNIT_TESTS_ONLY",
            "model_or_research_execution_authority": "LOCAL_COMPETITION_PRIORITY_UNIT_TESTS_ONLY",
            "credential_surface": "NO_SECRETS; CHECKOUT_PERSIST_CREDENTIALS_FALSE; CONTENTS_READ_ONLY",
            "network_authority_summary": "PYPI_DEPENDENCY_INSTALL_ONLY_FOR_WORKFLOW_COMMANDS; TEST_MODULES_HAVE_NO_PROVIDER_OR_SPORTSBOOK_TRANSPORT_CALLS",
        },
        "callee_edges": [
            {"source": ".github/workflows/verify-competition-review-priority-tests.yml", "step": "Check out exact PR head", "line": 22, "callee": "actions/checkout exact PR head persist-credentials=false", "classification": "READ_ONLY_SOURCE_CHECKOUT"},
            {"source": ".github/workflows/verify-competition-review-priority-tests.yml", "step": "Run focused competition-priority tests", "line": 55, "callee": "pytest tests/test_competition_review_priority.py tests/test_accumulator_priority.py tests/test_saturday_2026_08_22_fixture_universe.py", "classification": "LOCAL_DETERMINISTIC_TESTS_NO_TRANSPORT"},
        ],
    },
}

EXPECTED_PRS = {
258: {"title": "[Shadow] Add current research-only SportyBet field-trial accumulator", "state": "closed", "merged": True, "draft": True, "merged_at": "2026-08-29T06:47:02Z", "closed_at": "2026-08-29T06:47:02Z", "merge_commit_sha": "51065316a2a75473f4ac0ca08e0d66666390c2ab", "base": {"ref": "main", "sha": "2a4bfdce503f22def972f3d7d5d161eae814a1fb", "repo": "Thabearr/ATHENA"}, "head": {"ref": "feature/pr258-research-shadow-sportybet-field-trial", "sha": "d159bf959e15ce23f8d56766f105dbd03f1b6549", "repo": "Thabearr/ATHENA"}},
199: {"title": "[Saturday Acca][FotMob] Capture exact 2026-08-22 fixture universe", "state": "closed", "merged": True, "draft": False, "merged_at": "2026-08-21T07:14:15Z", "closed_at": "2026-08-21T07:14:15Z", "merge_commit_sha": "19b5574ddc610cb7f231c51143580d38f89ea35f", "base": {"ref": "main", "sha": "a149d523ee4e8859bfead7b7a42bfcb002fc37a8", "repo": "Thabearr/ATHENA"}, "head": {"ref": "evidence/saturday-2026-08-22-fixture-universe-capture", "sha": "b879b2140d0bc3fb64fa8fec4c73c735240a3b41", "repo": "Thabearr/ATHENA"}},
200: {"title": "[Saturday Acca][Priority] Separate competition review order from model reliability", "state": "closed", "merged": True, "draft": False, "merged_at": "2026-08-21T07:25:26Z", "closed_at": "2026-08-21T07:25:26Z", "merge_commit_sha": "5a77c55b939ac447f8409b945a576d5a9ad3b26a", "base": {"ref": "main", "sha": "19b5574ddc610cb7f231c51143580d38f89ea35f", "repo": "Thabearr/ATHENA"}, "head": {"ref": "policy/competition-fixture-review-priority", "sha": "7a93b553b785bc7b3518b32575da9cb212c8cdd4", "repo": "Thabearr/ATHENA"}},
201: {"title": "[Saturday Acca][Fixtures] Explicitly review exact 50 fixture identities", "state": "closed", "merged": True, "draft": False, "merged_at": "2026-08-21T08:55:04Z", "closed_at": "2026-08-21T08:55:04Z", "merge_commit_sha": "08d54c11a4e5fb11ff7d7d886bda95c1efb01f05", "base": {"ref": "main", "sha": "5a77c55b939ac447f8409b945a576d5a9ad3b26a", "repo": "Thabearr/ATHENA"}, "head": {"ref": "evidence/saturday-2026-08-22-fixture-identity-review", "sha": "090487c7cbb46996fb819790afed6b5b67d260ab", "repo": "Thabearr/ATHENA"}},
192: {"title": "[FotMob][Evidence] Capture prospective player-context source evidence", "state": "closed", "merged": True, "draft": False, "merged_at": "2026-08-20T20:19:51Z", "closed_at": "2026-08-20T20:19:51Z", "merge_commit_sha": "79c9e82c0d4604147bbef1704656ab4eec24fa35", "base": {"ref": "main", "sha": "74cec8bc649bc8d2181ca2806a460a84664f7f2e", "repo": "Thabearr/ATHENA"}, "head": {"ref": "evidence/fotmob-prospective-player-context-campaign", "sha": "46f76e8033d3d498131c6f893111b437b6b459a9", "repo": "Thabearr/ATHENA"}},
202: {"title": "[Saturday Acca][Catalog] Compile exact 50 reviewed fixture identities", "state": "closed", "merged": True, "draft": False, "merged_at": "2026-08-21T09:24:09Z", "closed_at": "2026-08-21T09:24:09Z", "merge_commit_sha": "1428802b0e9c00ff0ed6d1a6c3873a751c763416", "base": {"ref": "main", "sha": "08d54c11a4e5fb11ff7d7d886bda95c1efb01f05", "repo": "Thabearr/ATHENA"}, "head": {"ref": "evidence/saturday-2026-08-22-reviewed-fixture-catalog", "sha": "09b9a8f4afdc18d4165d531958f087130566ac20", "repo": "Thabearr/ATHENA"}},
}

EXPECTED_RUNS = {
    33238889550: {"pr": 258, "name": "PR258 SportyBet Live Transport Proof", "event": "pull_request", "status": "completed", "conclusion": "success", "run_attempt": 1, "created_at": "2026-08-29T06:36:53Z", "updated_at": "2026-08-29T06:37:59Z", "head_branch": "feature/pr258-research-shadow-sportybet-field-trial", "head_sha": "d159bf959e15ce23f8d56766f105dbd03f1b6549", "head_repository": "Thabearr/ATHENA", "workflow_id": 345138925},
    32455713912: {"pr": 199, "name": "Capture Saturday 2026-08-22 FotMob Fixture Universe", "event": "pull_request", "status": "completed", "conclusion": "success", "run_attempt": 1, "created_at": "2026-08-21T06:45:49Z", "updated_at": "2026-08-21T06:46:45Z", "head_branch": "evidence/saturday-2026-08-22-fixture-universe-capture", "head_sha": "b879b2140d0bc3fb64fa8fec4c73c735240a3b41", "head_repository": "Thabearr/ATHENA", "workflow_id": 339124448},
    32455307207: {"pr": 199, "name": "Capture Saturday 2026-08-22 FotMob Fixture Universe", "event": "pull_request", "status": "completed", "conclusion": "skipped", "run_attempt": 1, "created_at": "2026-08-21T06:39:53Z", "updated_at": "2026-08-21T06:39:54Z", "head_branch": "evidence/saturday-2026-08-22-fixture-universe-capture", "head_sha": "b879b2140d0bc3fb64fa8fec4c73c735240a3b41", "head_repository": "Thabearr/ATHENA", "workflow_id": 339124448},
    32457975325: {"pr": 200, "name": "Verify Saturday Competition Review Priority", "event": "pull_request", "status": "completed", "conclusion": "success", "run_attempt": 1, "created_at": "2026-08-21T07:17:26Z", "updated_at": "2026-08-21T07:18:29Z", "head_branch": "policy/competition-fixture-review-priority", "head_sha": "7a93b553b785bc7b3518b32575da9cb212c8cdd4", "head_repository": "Thabearr/ATHENA", "workflow_id": 339158316},
    32457975289: {"pr": 200, "name": "Verify Competition Review Priority Tests", "event": "pull_request", "status": "completed", "conclusion": "success", "run_attempt": 1, "created_at": "2026-08-21T07:17:26Z", "updated_at": "2026-08-21T07:18:24Z", "head_branch": "policy/competition-fixture-review-priority", "head_sha": "7a93b553b785bc7b3518b32575da9cb212c8cdd4", "head_repository": "Thabearr/ATHENA", "workflow_id": 339158771},
    32460062462: {"pr": 201, "name": "Verify Saturday 2026-08-22 Fixture Identity Review", "event": "pull_request", "status": "completed", "conclusion": "success", "run_attempt": 1, "created_at": "2026-08-21T07:45:43Z", "updated_at": "2026-08-21T07:46:43Z", "head_branch": "evidence/saturday-2026-08-22-fixture-identity-review", "head_sha": "090487c7cbb46996fb819790afed6b5b67d260ab", "head_repository": "Thabearr/ATHENA", "workflow_id": 339185906},
    32410775191: {"pr": 192, "name": "Execute FotMob Prospective Player-Context Campaign", "event": "pull_request", "status": "completed", "conclusion": "success", "run_attempt": 1, "created_at": "2026-08-20T19:49:44Z", "updated_at": "2026-08-20T19:50:54Z", "head_branch": "evidence/fotmob-prospective-player-context-campaign", "head_sha": "46f76e8033d3d498131c6f893111b437b6b459a9", "head_repository": "Thabearr/ATHENA", "workflow_id": 338837874},
    32410590032: {"pr": 192, "name": "Execute FotMob Prospective Player-Context Campaign", "event": "pull_request", "status": "completed", "conclusion": "success", "run_attempt": 1, "created_at": "2026-08-20T19:47:41Z", "updated_at": "2026-08-20T19:48:43Z", "head_branch": "evidence/fotmob-prospective-player-context-campaign", "head_sha": "46f76e8033d3d498131c6f893111b437b6b459a9", "head_repository": "Thabearr/ATHENA", "workflow_id": 338837874},
    32466721852: {"pr": 202, "name": "Verify Saturday 2026-08-22 Reviewed Fixture Catalog", "event": "pull_request", "status": "completed", "conclusion": "success", "run_attempt": 1, "created_at": "2026-08-21T09:11:50Z", "updated_at": "2026-08-21T09:13:00Z", "head_branch": "evidence/saturday-2026-08-22-reviewed-fixture-catalog", "head_sha": "09b9a8f4afdc18d4165d531958f087130566ac20", "head_repository": "Thabearr/ATHENA", "workflow_id": 339238972},
}

# These tracked source files are the bounded execution/review chain. Unrelated
# family code and sibling workflow jobs are intentionally not traversed.
HISTORICAL_PATHS_BY_PR = {
    258: [".github/workflows/pr258-sportybet-live-transport-proof.yml", "scripts/run_pr258_sportybet_live_transport_proof.py", "domain/current_shadow_sportybet_share_code.py", "domain/sportybet_current_event_discovery_reconciliation.py", "domain/sportybet_live_event_quote_evidence.py", "scripts/sportybet_direct_share_bridge.py", "scripts/sportybet_semantic_share_bridge.py", "domain/_portfolio_optimizer_v2_direct_provider_contracts.py"],
    199: [".github/workflows/capture-saturday-2026-08-22-fixture-universe.yml", "scripts/capture_saturday_2026_08_22_fixture_universe.py", "scripts/capture_fotmob_data_matches.py", "domain/fotmob_data_matches_capture.py", "domain/fotmob_data_matches_probe.py", "domain/fotmob_data_matches_schema.py", "domain/fotmob_fixture_candidates.py", "domain/saturday_2026_08_22_fixture_universe.py", "config/league_priority.py"],
    200: [".github/workflows/verify-saturday-competition-review-priority.yml", ".github/workflows/verify-competition-review-priority-tests.yml", "domain/fotmob_data_matches_capture.py", "domain/fotmob_fixture_candidates.py", "domain/saturday_2026_08_22_fixture_universe.py", "config/competition_review_priority.py", "tests/test_competition_review_priority.py", "tests/test_accumulator_priority.py", "tests/test_saturday_2026_08_22_fixture_universe.py", "tests/conftest.py", "requirements.txt", "config/league_priority.py", "domain/accumulator_priority.py", "domain/model_league_reliability.py", "domain/markets.py", "intelligence/acca_filter.py"],
    201: [".github/workflows/verify-saturday-2026-08-22-fixture-identity-review.yml", "scripts/verify_saturday_2026_08_22_fixture_identity_review.py", "scripts/manage_fotmob_reviewed_fixture_catalog.py", "domain/fotmob_data_matches_capture.py", "domain/fotmob_fixture_candidates.py", "domain/fotmob_fixture_candidate_review.py", "domain/saturday_2026_08_22_fixture_universe.py", "tests/test_saturday_2026_08_22_fixture_identity_review.py", "tests/conftest.py", "requirements.txt"],
    192: [".github/workflows/execute-fotmob-prospective-player-context-campaign.yml", "scripts/run_fotmob_prospective_player_context_campaign.py", "scripts/capture_fotmob_data_matches.py", "scripts/capture_fotmob_reviewed_match_details.py", "scripts/manage_fotmob_reviewed_fixture_catalog.py", "scripts/manage_fixture_catalog.py", "domain/fixture_catalog.py", "domain/fotmob_data_matches_capture.py", "domain/fotmob_data_matches_probe.py", "domain/fotmob_data_matches_schema.py", "domain/fotmob_fixture_candidates.py", "domain/fotmob_fixture_candidate_review.py", "domain/fotmob_prospective_player_context_campaign.py", "domain/fotmob_reviewed_match_details_persisted_evidence.py", "domain/fotmob_reviewed_match_details_structure.py", "domain/fotmob_fixture_catalog_handoff.py", "domain/reviewed_fixture_catalog_admission.py", "domain/reviewed_fixture_catalog_admission_artifact.py", "domain/reviewed_fixture_intelligence_bootstrap.py", "domain/reviewed_fixture_intelligence_bootstrap_artifact.py", "requirements.txt"],
    202: [".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml", "scripts/prepare_saturday_2026_08_22_reviewed_fixture_catalog.py", "scripts/replay_reviewed_fixture_catalog_admission.py", "scripts/manage_fotmob_reviewed_fixture_catalog.py", "scripts/manage_fixture_catalog.py", "scripts/freeze_evidence_baseline.py", "domain/reviewed_fixture_catalog_admission_source_replay.py", "domain/fotmob_data_matches_capture.py", "domain/fotmob_fixture_candidates.py", "domain/fotmob_fixture_candidate_review.py", "domain/fotmob_fixture_catalog_handoff.py", "domain/reviewed_fixture_catalog_admission.py", "domain/fixture_catalog.py", "tests/test_saturday_2026_08_22_reviewed_fixture_catalog.py", "tests/conftest.py", "requirements.txt"],
}

CURRENT_SOURCE_PATHS = sorted({
    path for rows in HISTORICAL_PATHS_BY_PR.values() for path in rows
} | {
    ".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml",
    "config/competition_review_priority.py",
})
TARGET_KEYS = tuple(TARGETS)
RERUN_RESIDUAL = "HISTORICAL_ACTIONS_RERUN_RESIDUAL_NOT_PROVEN_ABSENT"
CURRENT_SPENT = "NONE_BECAUSE_EXACT_MERGED_PR_PULL_REQUEST_TRIGGER_IS_SPENT"
CURRENT_EDIT_GUARD_BLOCKED = "NONE_CURRENT_EDIT_EVENT_REACHES_DRAFT_GUARD_BEFORE_CAPTURE_AUTHORITY"
ZERO_ACTIONS = {
    "provider_network": 0, "sportsbook_network": 0, "workflow_dispatch": 0,
    "workflow_rerun": 0, "workflow_cancel": 0, "pr_reopen_or_close": 0,
    "release_mutation": 0, "issue_comment_write": 0, "artifact_download": 0,
    "provider_payload_download": 0, "email": 0, "external_storage_write": 0,
    "share_code": 0, "login": 0, "cookies": 0, "wallet": 0, "stake": 0, "wager": 0,
}


def _git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def _normalized(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n")


def _identity_for_worktree(path: str) -> dict[str, str]:
    raw = (ROOT / path).read_bytes()
    blob = _git("hash-object", path).decode().strip()
    head_blob = _git("rev-parse", "HEAD:" + path).decode().strip()
    boundary.require(blob == head_blob, "reviewed source differs from committed HEAD: " + path)
    return {"path": path, "git_blob_sha1": blob,
            "normalized_source_sha256": hashlib.sha256(_normalized(raw)).hexdigest()}


def _identity_at_commit(commit: str, path: str, pr: int) -> dict[str, object]:
    raw = _git("show", commit + ":" + path)
    blob = _git("rev-parse", commit + ":" + path).decode().strip()
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    boundary.require(actual == blob, "historical Git blob identity mismatch: PR #" + str(pr) + " " + path)
    return {"pr_number": pr, "pr_head_sha": commit, "path": path,
            "git_blob_sha1": blob,
            "normalized_source_sha256": hashlib.sha256(_normalized(raw)).hexdigest()}


def capture_historical_source_identities() -> list[dict[str, object]]:
    rows = []
    for pr, paths in sorted(HISTORICAL_PATHS_BY_PR.items()):
        for path in paths:
            rows.append(_identity_at_commit(PR_HEADS[pr], path, pr))
    return rows


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(boundary.canonical(value)).hexdigest()


def _strict_json(path: str) -> dict[str, object]:
    raw = (ROOT / path).read_bytes()
    value = boundary.read(path)
    boundary.require(raw == boundary.canonical(value), "non-canonical evidence bytes: " + path)
    return value


def _yaml(path: str) -> dict[str, object]:
    return yaml.load((ROOT / path).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _normalize_guard(value: str) -> str:
    return " ".join(value.split())


def _target_step(workflow: dict[str, object], job_name: str, step_name: str) -> dict[str, object]:
    job = workflow["jobs"][job_name]
    matches = [step for step in job.get("steps", []) if step.get("name") == step_name]
    boundary.require(len(matches) == 1, "target step missing/duplicated: " + step_name)
    return matches[0]


def _guard_contract(key: str) -> dict[str, object]:
    spec = TARGETS[key]
    wf = _yaml(spec["path"])
    events = wf.get("on", {})
    boundary.require("pull_request" in events, "pull_request trigger missing: " + key)
    trigger = events["pull_request"] or {}
    explicit_types = trigger.get("types")
    effective_types = explicit_types or ["opened", "synchronize", "reopened"]
    branch_filter = trigger.get("branches")
    paths = trigger.get("paths")
    paths_ignore = trigger.get("paths-ignore")
    job = wf["jobs"][spec["job"]]
    job_if = _normalize_guard(job.get("if", ""))
    boundary.require(job_if, "exact-PR job guard missing: " + key)
    number_match = re.search(r"github\.event\.pull_request\.number\s*==\s*(\d+)", job_if)
    boundary.require(number_match is not None and int(number_match.group(1)) == spec["pr"],
                     "bound PR number differs from exact trigger source: " + key)
    ref_match = re.search(r"github\.(?:event\.pull_request\.head\.ref|head_ref)\s*==\s*'([^']+)'", job_if)
    boundary.require(ref_match is not None and ref_match.group(1) == spec["head_ref"],
                     "bound head branch differs from exact trigger source: " + key)
    full_text = (ROOT / spec["path"]).read_text(encoding="utf-8")
    base_values = re.findall(r"(?:base\.sha|pull_request\.base\.sha)[^\n]{0,80}?['\"]([0-9a-f]{40})['\"]", full_text)
    base_values = sorted(set(base_values))
    boundary.require((spec["base_sha"] is None and not base_values)
                     or (spec["base_sha"] is not None and spec["base_sha"] in base_values),
                     "frozen base SHA guard differs from reviewed trigger: " + key)
    current_repo_guard = "github.event.pull_request.head.repo.full_name == github.repository" in job_if or "pr.head.repo.full_name !== context.repo.owner" in full_text
    owner_guard = "github.actor == 'Thabearr'" in job_if or "context.actor !== 'Thabearr'" in full_text
    draft_guard = "github.event.pull_request.draft == true" in job_if or "!pr.draft" in full_text
    marker_matches = re.findall(r"<!-- ATHENA_[A-Z0-9_]+ -->", full_text)
    marker = marker_matches[0] if marker_matches else None
    concurrency = wf.get("concurrency")
    github_scripts = []
    for step in job.get("steps", []):
        if str(step.get("uses", "")).startswith("actions/github-script@"):
            script = step.get("with", {}).get("script", "")
            github_scripts.append({"step": step.get("name"), "id": step.get("id"),
                                   "script_sha256": hashlib.sha256(script.encode()).hexdigest()})
    permission = {"workflow": wf.get("permissions", {}), "job": job.get("permissions", {})}
    boundary.require(not re.search(r"secrets\.[A-Za-z_]|smtp|sendmail|releases\.createRelease|createWorkflowDispatch|repository_dispatch|git push", full_text, re.I),
                     "target workflow contains an unreviewed credential or mutation edge: " + key)
    return {
        "pull_request": {"explicit_types": explicit_types or [], "types_explicit": bool(explicit_types),
                         "effective_event_types": effective_types,
                         "branches": branch_filter or [], "paths": paths or [], "paths_ignore": paths_ignore or []},
        "bound_pr_number": int(number_match.group(1)),
        "head_repository_guard": "SAME_REPOSITORY" if current_repo_guard else "NOT_ENFORCED_BY_THIS_TRIGGER",
        "head_branch_guard": ref_match.group(1),
        "base_branch_filter": branch_filter or [],
        "base_sha_guard": spec["base_sha"],
        "owner_guard": owner_guard,
        "draft_guard": draft_guard,
        "body_control_marker": marker,
        "job": spec["job"], "job_if_normalized": job_if,
        "job_if_sha256": hashlib.sha256(job_if.encode()).hexdigest(),
        "github_script_guards": github_scripts,
        "concurrency": concurrency or {},
        "permissions": permission,
        "step_names": [step.get("name") for step in job.get("steps", [])],
        "sibling_trigger_kinds": sorted(k for k in wf.get("on", {}) if k != "pull_request"),
    }


def _discover_workflow_edges(key: str) -> list[dict[str, object]]:
    spec = TARGETS[key]
    wf = _yaml(spec["path"])
    job = wf["jobs"][spec["job"]]
    text = (ROOT / spec["path"]).read_text(encoding="utf-8")
    lines = text.splitlines()
    result: list[dict[str, object]] = []
    cursor = 0
    for step in job.get("steps", []):
        name = step.get("name") or "unnamed"
        start = next((i for i in range(cursor, len(lines)) if lines[i].strip() == "- name: " + name), None)
        boundary.require(start is not None, "step source line not found: " + name)
        end = next((i for i in range(start + 1, len(lines))
                    if re.match(r"^\s+- name:\s+", lines[i])), len(lines))
        cursor = end
        uses = step.get("uses")
        if uses:
            line = next((i for i in range(start + 1, end) if re.match(r"^\s+uses:\s*", lines[i])), None)
            boundary.require(line is not None, "action source line missing: " + name)
            action = str(uses).split("@", 1)[0]
            if action == "actions/checkout": classification = "READ_ONLY_SOURCE_CHECKOUT"
            elif action == "actions/setup-python": classification = "RUNTIME_SETUP_AND_PUBLIC_PACKAGE_INSTALL_PATH"
            elif action == "actions/github-script": classification = "READ_ONLY_GITHUB_METADATA_SCRIPT"
            elif action == "actions/download-artifact": classification = "RUN_SCOPED_OR_EXACT_CROSS_RUN_ARTIFACT_READ"
            elif action == "actions/upload-artifact": classification = "RUN_SCOPED_EVIDENCE_ARTIFACT_WRITE"
            else: classification = "UNRESOLVED_ACTION_EDGE"
            boundary.require(classification != "UNRESOLVED_ACTION_EDGE", "unclassified action in target job: " + action)
            result.append({"step": name, "kind": "uses", "line": line + 1,
                           "reference": uses, "classification": classification})
        run = step.get("run")
        if run:
            line = next((i for i in range(start + 1, end) if re.match(r"^\s+run:\s*", lines[i])), None)
            boundary.require(line is not None, "run source line missing: " + name)
            compact = " ".join(str(run).split())
            if "pip install" in compact:
                classification = "PUBLIC_PACKAGE_INDEX_INSTALL"
            elif "pytest" in compact:
                classification = "LOCAL_DETERMINISTIC_TEST"
            elif "--execute-live-network" in compact:
                classification = "EXPLICIT_LIVE_PROVIDER_ENTRYPOINT"
            elif "scripts." in compact or "python scripts/" in compact:
                classification = "SOURCE_BOUND_LOCAL_ENTRYPOINT"
            else:
                classification = "LOCAL_GUARD_OR_SUMMARY_ONLY"
            result.append({"step": name, "kind": "run", "line": line + 1,
                           "command_sha256": hashlib.sha256(compact.encode()).hexdigest(),
                           "classification": classification})
    return result


def _current_source_identities() -> list[dict[str, str]]:
    return [_identity_for_worktree(path) for path in CURRENT_SOURCE_PATHS]


def _read_predecessors() -> dict[str, object]:
    expected = {
        "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v1.json": V1_INVENTORY_SHA,
        "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v2.json": V2_INVENTORY_SHA,
        boundary.RECEIPT_PATH: A2_RECEIPT_SHA,
        boundary.BRIDGE_RECEIPT_PATH: BRIDGE_RECEIPT_SHA,
        COMPLETION_V3_PATH: COMPLETION_V3_SHA,
        "artifacts/architecture/core_01d_checkpoint_e_completion_v2.json": COMPLETION_V2_SHA,
        "artifacts/architecture/core_01d_authority_reachability_review_a_v1.json": PASS_A_SHA,
        "artifacts/architecture/checkpoint_e_workflow_capability_matrix_v2.json": MATRIX_V2_SHA,
        "artifacts/architecture/core_01d_retained_workflow_status_v5.json": RETAINED_V5_SHA,
        "artifacts/architecture/p4_workflow_evolution_ledger_v1.json": EVOLUTION_SHA,
        "artifacts/architecture/p4_3_workflow_retirement_ledger_v1.json": RETIREMENT_SHA,
    }
    values = {}
    for path, sha in expected.items():
        value = _strict_json(path)
        boundary.require(value.get("canonical_sha256") == sha, "immutable predecessor drift: " + path)
        values[path] = value
    boundary.require(historical_workflow_tree(_git("rev-parse", "HEAD:.github/workflows").decode().strip()) == WORKFLOW_TREE,
                     "workflow tree changed in B1")
    boundary.require(not _git("diff", "--name-only", "HEAD", "--", ".github/workflows").strip(),
                     "workflow diff must remain empty")
    return values


def build_source_inventory(*, historical_rows: list[dict[str, object]] | None = None) -> dict[str, object]:
    boundary.authenticate_predecessors()
    existing_chain = boundary.load_inventory_generations()
    boundary.require(len(existing_chain) == 2,
                     "A2 source-inventory predecessor chain drift before V3 build")
    boundary.require(existing_chain[-1][1]["canonical_sha256"] == V2_INVENTORY_SHA,
                     "A2 V2 predecessor identity drift before V3 build")
    predecessors = _read_predecessors()
    current = _current_source_identities()
    if historical_rows is None:
        fixture_path = ROOT / SOURCE_INVENTORY_PATH
        if fixture_path.exists():
            existing = boundary.read(SOURCE_INVENTORY_PATH)
            historical_rows = existing["historical_pr_head_source_identities"]
        else:
            historical_rows = capture_historical_source_identities()
    contract = {key: _guard_contract(key) for key in TARGET_KEYS}
    edge_rows = {key: _discover_workflow_edges(key) + TARGETS[key]["callee_edges"] for key in TARGET_KEYS}
    return boundary.seal({
        "schema_version": 1, "policy_id": "ATHENA_CORE_01D_EXACT_PR_TRIGGER_DISPOSITION_B1_SOURCE_INVENTORY_V1",
        "repository": "Thabearr/ATHENA", "master_issue": 337,
        "base_main_sha": BASE_MAIN, "base_tree_sha": BASE_TREE,
        "workflow_tree_sha1": WORKFLOW_TREE,
        "workflow_evolution_ledger_sha256": EVOLUTION_SHA, "transition_count": 14,
        "retirement_ledger_sha256": RETIREMENT_SHA, "retired_workflow_count": 3,
        "completion_v3": {"path": COMPLETION_V3_PATH, "canonical_sha256": COMPLETION_V3_SHA, "rewritten": False},
        "a2_predecessors": {
            "inventory_v1_sha256": V1_INVENTORY_SHA, "inventory_v2_sha256": V2_INVENTORY_SHA,
            "receipt_sha256": A2_RECEIPT_SHA, "bridge_receipt_sha256": BRIDGE_RECEIPT_SHA,
            "latest_generation": 2, "successor_required": "V3",
        },
        "predecessor_receipts": {path: value["canonical_sha256"] for path, value in predecessors.items()},
        "scope": {"target_surface_count": len(TARGET_KEYS), "target_keys": list(TARGET_KEYS),
                  "workflow_count": 7, "out_of_scope_sibling_triggers_reclassified": 0},
        "current_source_identities": current,
        "historical_pr_head_source_identities": historical_rows,
        "historical_pr_heads": {str(pr): sha for pr, sha in sorted(PR_HEADS.items())},
        "trigger_contracts": contract,
        "workflow_edges": edge_rows,
        "dynamic_caller_discovery": {
            "method": "SOURCE_SEARCH_OF_CURRENT_WORKFLOW_YAML_AND_EXECUTABLE_SCRIPT_CALLS_FOR_REUSABLE_WORKFLOW_PATHS, WORKFLOW_RUN TARGET TITLES, GH WORKFLOW RUN TARGETS, AND CREATEWORKFLOWDISPATCH TARGETS",
            "external_callers_found": [],
            "trigger_local_siblings": {
                ".github/workflows/pr258-sportybet-live-transport-proof.yml": ["workflow_dispatch"],
                ".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml": ["push"],
            },
            "sibling_disposition": "OUT_OF_SCOPE_UNRESOLVED_REMAINS_IN_COMPLETION_V3",
        },
        "external_side_effect_entrypoints": [
            "SportyBet public GET and anonymous share POST/GET are only in PR258 historical job path",
            "FotMob bounded source GET is only in PR199/PR192 historical job paths",
            "Actions artifact reads/writes are run-scoped or exact source artifact transfers as described per row",
            "No workflow dispatch, issue/PR write, branch write, release write, SMTP, external storage, wallet, stake, or wager path is in a target pull_request job",
        ],
        "source_capture": {"github_metadata_reads_only": True, "provider_network_calls": 0,
                           "sportsbook_network_calls": 0, "workflow_execution_or_rerun": 0,
                           "artifact_payload_download": 0, "workflow_source_edit": 0},
    })


def _expected_run_rows(key: str) -> list[dict[str, object]]:
    mapping = {
        ".github/workflows/pr258-sportybet-live-transport-proof.yml#pull_request": [33238889550],
        ".github/workflows/capture-saturday-2026-08-22-fixture-universe.yml#pull_request": [32455713912, 32455307207],
        ".github/workflows/verify-saturday-competition-review-priority.yml#pull_request": [32457975325],
        ".github/workflows/verify-saturday-2026-08-22-fixture-identity-review.yml#pull_request": [32460062462],
        ".github/workflows/execute-fotmob-prospective-player-context-campaign.yml#pull_request": [32410775191, 32410590032],
        ".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml#pull_request": [32466721852],
        ".github/workflows/verify-competition-review-priority-tests.yml#pull_request": [32457975289],
    }
    return [{"run_id": run_id, "source_endpoint": f"GET /repos/Thabearr/ATHENA/actions/runs/{run_id}",
             "read_only": True, "api_pull_request_links": [],
             "pr_identity_match_basis": "PULL_REQUEST_EVENT_AND_EXACT_HEAD_REPOSITORY_BRANCH_SHA_MATCH_BOUND_LIVE_PR",
             **EXPECTED_RUNS[run_id]} for run_id in mapping[key]]


def _receipt_row(key: str, source_inventory: dict[str, object], observed_at: str) -> dict[str, object]:
    spec = TARGETS[key]
    pr = EXPECTED_PRS[spec["pr"]]
    guard = source_inventory["trigger_contracts"][key]
    identity = next(row for row in source_inventory["current_source_identities"] if row["path"] == spec["path"])
    boundary.require(pr["merged"] is True and pr["state"] == "closed", "bound PR is not merged/closed: " + key)
    boundary.require(pr["merged_at"] is not None and pr["closed_at"] is not None
                     and pr["merge_commit_sha"] is not None,
                     "merged PR lacks merge/close evidence: " + key)
    boundary.require(pr["head"]["ref"] == spec["head_ref"] and pr["head"]["repo"] == "Thabearr/ATHENA",
                     "live PR head identity does not match source guard: " + key)
    boundary.require(pr["head"]["sha"] == PR_HEADS[spec["pr"]],
                     "live PR head SHA differs from the reviewed historical run binding: " + key)
    if spec["base_sha"] is not None:
        boundary.require(pr["base"]["sha"] == spec["base_sha"], "live PR base SHA differs from workflow guard: " + key)
    runs = _expected_run_rows(key)
    for run in runs:
        run["observed_at_utc"] = observed_at
        boundary.require(run["pr"] == spec["pr"] and run["event"] == "pull_request"
                         and run["head_sha"] == pr["head"]["sha"]
                         and run["head_branch"] == pr["head"]["ref"]
                         and run["head_repository"] == pr["head"]["repo"],
                         "historical Actions run is not bound to the exact PR identity: " + key)
        boundary.require(run["api_pull_request_links"] == []
                         and run["pr_identity_match_basis"] == "PULL_REQUEST_EVENT_AND_EXACT_HEAD_REPOSITORY_BRANCH_SHA_MATCH_BOUND_LIVE_PR",
                         "historical run PR linkage is misrepresented: " + key)
    edited_event = guard["pull_request"]["effective_event_types"] == ["edited"]
    if edited_event:
        boundary.require(guard["draft_guard"] is True and pr["draft"] is False,
                         "edited-event draft guard or current draft metadata changed: " + key)
        current_authority = {
            field: CURRENT_EDIT_GUARD_BLOCKED for field in spec["history"]
            if field.endswith("_authority")
        }
        current_authority["notification_authority"] = (
            "GITHUB_SKIPPED_JOB_STATUS_ONLY" if spec["pr"] == 199
            else "GITHUB_FAILED_CHECK_LOG_AND_STEP_SUMMARY_ONLY"
        )
        current_authority["network_authority_summary"] = (
            "EDIT_EVENT_MAY_BE_DELIVERED; DRAFT_GUARD_STOPS_PROVIDER_PATH; PR192_ALWAYS_UPLOAD_FAILS_ON_MISSING_OUTPUT"
        )
        current_authority["credential_surface"] = (
            "READ_ONLY_EVENT_CONTEXT; PR199_JOB_IF_SKIPS_RUNNER; PR192_FIRST_SCRIPT_REJECTS_NON_DRAFT_BEFORE_PROVIDER_AND_ALWAYS_STEPS_REMAIN"
        )
        current_steps = (
            [] if spec["pr"] == 199 else [
                {
                    "step": "Upload exact evidence on success or fail-closed conclusion",
                    "condition": "always()",
                    "effect": "RUN_SCOPED_ARTIFACT_UPLOAD_ATTEMPT",
                    "path": "campaign-artifact/",
                    "if_no_files_found": "error",
                    "guard_result": "FIRST_GITHUB_SCRIPT_FAILS_BEFORE_CHECKOUT_AND_CAMPAIGN_CREATION",
                    "result": "UPLOAD_FAILS_CLOSED_WITH_NO_CAMPAIGN_ARTIFACT",
                },
                {
                    "step": "Publish campaign summary",
                    "condition": "always()",
                    "effect": "GITHUB_STEP_SUMMARY_WRITE",
                    "result": "SUMMARY_RECORDS_GUARD_FAILURE_AND_UPLOAD_OUTCOME",
                },
            ]
        )
        if spec["pr"] == 192:
            current_authority["artifact_write_authority"] = (
                "RUN_SCOPED_UPLOAD_ACTION_REACHABLE; CAMPAIGN_PATH_NOT_CREATED_AFTER_GUARD_FAILURE; IF_NO_FILES_FOUND_ERROR"
            )
        reachability = {
            "declared_trigger_current_reachability": "CURRENT_EDIT_EVENT_MAY_BE_DELIVERED_BUT_MERGED_DRAFT_GUARD_BLOCKS_CAPTURE_AUTHORITY",
            "pull_request_event_may_be_delivered": True,
            "execution_guard_after_merge": (
                "JOB_IF_REQUIRES_DRAFT_TRUE; CURRENT_PR_DRAFT_FALSE_SKIPS_CAPTURE_JOB"
                if spec["pr"] == 199 else
                "FIRST_GITHUB_SCRIPT_REQUIRES_PR_DRAFT_TRUE; CURRENT_PR_DRAFT_FALSE_FAILS_BEFORE_CHECKOUT_OR_PROVIDER; ALWAYS_UPLOAD_FAILS_NO_FILES; ALWAYS_SUMMARY_WRITES_STEP_SUMMARY"
            ),
            "current_external_capture_authority": (
                "NONE_DRAFT_GUARD_FAILS_CLOSED"
                if spec["pr"] == 199 else
                "NO_PROVIDER_CAPTURE; ALWAYS_UPLOAD_ACTION_FAILS_ON_ABSENT_CAMPAIGN_PATH; STEP_SUMMARY_IS_WRITTEN"
            ),
            "current_post_guard_effects": current_steps,
            "reason": (
                "The pull_request edited event can still be delivered for this merged PR when title or body is edited. "
                "GitHub reports the exact bound PR as draft=false. For PR #199 the job-level if requires draft=true "
                "and skips the capture job; for PR #192 the first github-script guard rejects non-draft PRs before "
                "checkout or provider capture. Its later always() uploader fails closed because campaign-artifact/ "
                "was never created, and its always() summary writes only the job summary. This resolves current "
                "guarded authority without "
                "claiming the edited event itself is impossible."
            ),
            "reopenability": "MERGED_PR_CANNOT_RETURN_TO_UNMERGED; EDITED_EVENT_REMAINS_POSSIBLE; CURRENT_DRAFT_FALSE_BLOCKS_CAPTURE",
        }
    else:
        current_authority = {field: CURRENT_SPENT for field in spec["history"]
                             if field.endswith("_authority")}
        current_authority["network_authority_summary"] = CURRENT_SPENT
        current_authority["credential_surface"] = "NO_NEW_PULL_REQUEST_EVENT_CREDENTIAL_CONTEXT_AFTER_MERGED_EXACT_BINDING"
        reachability = {
            "declared_trigger_current_reachability": "CURRENT_DECLARED_PULL_REQUEST_TRIGGER_SPENT_EXACT_MERGED_PR_BINDING",
            "pull_request_event_may_be_delivered": False,
            "execution_guard_after_merge": "NO_OPEN_OR_UNMERGED_EXACT_PR_EVENT_STATE_REMAINS",
            "current_external_capture_authority": "NONE_EXACT_MERGED_PR_EVENT_CONDITION_CANNOT_RECUR",
            "reason": "The exact PR number and source-derived head identity are merged; GitHub reports merged=true and merged_at. The declared opened/synchronize/reopened pull_request event condition cannot recur for this merged PR.",
            "reopenability": "IMPOSSIBLE_AS_MERGED_PR",
        }
    edge_rows = source_inventory["workflow_edges"][key]
    historical_mutations = [edge for edge in spec["callee_edges"]
                            if edge["classification"] in {
                                "SHARE_CODE_CREATE", "SHARE_CODE_RELOAD_READ",
                                "OWNER_GATED_LIVE_FOTMOB_CAPTURE", "EXPLICIT_LIVE_NETWORK_GATE",
                                "FOTMOB_DATA_MATCHES_READ", "FOTMOB_MATCH_DETAILS_READ",
                            }]
    return {
        "workflow_path": spec["path"], "trigger_kind": "pull_request",
        "source_identity": identity,
        "trigger_contract": guard,
        "live_bound_pr": {"source_endpoint": f"GET /repos/Thabearr/ATHENA/pulls/{spec['pr']}",
                           "observed_at_utc": observed_at, "read_only": True,
                           "metadata": pr, "exact_pr_number": spec["pr"]},
        "historical_runs": runs,
        "reachability": {
            **reachability,
            "historical_actions_rerun_residual": RERUN_RESIDUAL,
            "sibling_trigger_state": ("OUT_OF_SCOPE_UNRESOLVED_" + ",".join(guard["sibling_trigger_kinds"])
                                       if guard["sibling_trigger_kinds"] else "NO_SIBLING_TRIGGER_IN_THIS_WORKFLOW"),
        },
        "historical_guarded_capability": spec["history"],
        "current_declared_pull_request_authority": current_authority,
        "dynamic_reachability": {
            "review_state": "SOURCE_AND_METADATA_BOUND",
            "workflow_edges": edge_rows,
            "discovered_callees": sorted({edge["callee"] for edge in spec["callee_edges"]}),
            "outbound_dynamic_targets": sorted({edge["callee"] for edge in spec["callee_edges"]}),
            "inbound_dynamic_callers": [],
            "static_repository_callers": [],
            "dynamic_repository_callers": [],
            "external_api_mutations_historically_reachable": historical_mutations,
            "external_api_mutations_on_current_declared_pull_request_event": [],
            "sibling_surfaces_reclassified": [],
            "network_provider_calls_currently_performed_by_this_review": 0,
        },
        "review": {"status": "RESOLVED", "blocker": None,
            "disposition": reachability["declared_trigger_current_reachability"],
                   "workflow_file_disposition": "NOT_CLASSIFIED_BY_THIS_TRIGGER_SURFACE_REVIEW"},
    }


def build_receipt(*, observed_at: str | None = None) -> dict[str, object]:
    boundary.authenticate_predecessors()
    latest_a2 = boundary.authenticate_inventory()
    chain = boundary.load_inventory_generations()
    boundary.require(len(chain) >= 4,
                     "B1 audit requires the immutable append-only A2 V1-V4 prefix")
    a2_v4 = chain[3][1]
    boundary.require(a2_v4.get("canonical_sha256") == "82c440deb06d760d13bf73d914c5ec9181e568ba388f844a3fc6fa49976ab50f"
                     and a2_v4.get("generation") == 4,
                     "immutable A2 V4 identity drift")
    boundary.require(a2_v4.get("predecessor_inventory") == {
        "path": boundary.inventory_generation_path(3),
        "canonical_sha256": "f7646fd5008d12cc7c5b0379455c384742b893a26cac00fa55df19f28c8a8017",
        "generation": 3, "rewritten": False,
    }, "A2 V4 does not extend the exact immutable V3 inventory")
    a2_v3 = chain[2][1]
    boundary.require(a2_v3.get("canonical_sha256") == "f7646fd5008d12cc7c5b0379455c384742b893a26cac00fa55df19f28c8a8017"
                     and a2_v3.get("predecessor_inventory") == {
        "path": boundary.inventory_generation_path(2), "canonical_sha256": V2_INVENTORY_SHA,
        "generation": 2, "rewritten": False,
    }, "immutable A2 V3 predecessor contract differs from reviewed V2")
    completion = _strict_json(COMPLETION_V3_PATH)
    boundary.require(completion["canonical_sha256"] == COMPLETION_V3_SHA,
                     "Completion V3 immutable identity drift")
    surfaces = completion["unreviewed_authority_surfaces"]
    inherited_keys = [(row["workflow_path"], row["trigger_kind"]) for row in surfaces]
    boundary.require(len(surfaces) == 32 and len(set(inherited_keys)) == 32,
                     "Completion V3 unresolved surface census drift")
    boundary.require(all(inherited_keys.count((spec["path"], "pull_request")) == 1 for spec in TARGETS.values()),
                     "one or more B1 targets are missing or duplicated in Completion V3")
    boundary.require(all(next(row for row in surfaces if (row["workflow_path"], row["trigger_kind"]) == (spec["path"], "pull_request"))["unreviewed_authority_fields"]
                         and all("UNKNOWN" in str(value) for value in next(row for row in surfaces if (row["workflow_path"], row["trigger_kind"]) == (spec["path"], "pull_request"))["unreviewed_authority_fields"].values())
                         for spec in TARGETS.values()), "a B1 target is not currently unresolved")
    source_inventory = _strict_json(SOURCE_INVENTORY_PATH)
    validate_source_inventory(source_inventory)
    observed_at = observed_at or "2026-10-03T16:44:52Z"
    rows = [_receipt_row(key, source_inventory, observed_at) for key in TARGET_KEYS]
    return boundary.seal({
        "schema_version": 1, "policy_id": POLICY_ID,
        "repository": "Thabearr/ATHENA", "master_issue": 337,
        "base_main_sha": BASE_MAIN, "base_tree_sha": BASE_TREE,
        "workflow_tree_sha1": WORKFLOW_TREE,
        "workflow_evolution_ledger_sha256": EVOLUTION_SHA, "transition_count": 14,
        "retirement_ledger_sha256": RETIREMENT_SHA, "retired_workflow_count": 3,
        "predecessors": {
            "a2_v1_inventory_sha256": V1_INVENTORY_SHA,
            "a2_v2_inventory_sha256": V2_INVENTORY_SHA,
            "a2_v3_inventory": {"path": boundary.inventory_generation_path(3),
                                 "canonical_sha256": a2_v3["canonical_sha256"], "generation": 3},
            "a2_receipt_sha256": A2_RECEIPT_SHA,
            "a2_evolution_bridge_sha256": BRIDGE_RECEIPT_SHA,
            "completion_v3_sha256": COMPLETION_V3_SHA,
            "completion_v2_sha256": COMPLETION_V2_SHA,
            "pass_a_sha256": PASS_A_SHA,
            "capability_matrix_v2_sha256": MATRIX_V2_SHA,
            "retained_v5_sha256": RETAINED_V5_SHA,
            "rewritten": False,
        },
        "source_inventory": {"path": SOURCE_INVENTORY_PATH, "canonical_sha256": source_inventory["canonical_sha256"]},
        "scope": {"surface_count": 7, "workflow_count": 7, "target_keys": list(TARGET_KEYS),
                  "resolved_count": sum(row["review"]["status"] == "RESOLVED" for row in rows),
                  "partial_count": sum(row["review"]["status"] != "RESOLVED" for row in rows)},
        "review_rows": rows,
        "sibling_trigger_isolation": {
            ".github/workflows/pr258-sportybet-live-transport-proof.yml#workflow_dispatch": "UNRESOLVED_OUT_OF_SCOPE_INHERITED_UNCHANGED",
            ".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml#push": "UNRESOLVED_OUT_OF_SCOPE_INHERITED_UNCHANGED",
        },
        "actions": ZERO_ACTIONS,
        "workflow_edit_count": 0, "trigger_edit_count": 0,
        "workflow_retirement_count": 0, "workflow_deletion_count": 0,
        "source_review_counter_while_open": "0/5",
        "source_review_counter_if_owner_merges": "1/5",
        "mandatory_source_reread_after_b1_merge": False,
        "checkpoint_e_status": "INCOMPLETE", "p4_4_status": "INCOMPLETE",
        "criteria_11_and_14_remain_false": True,
        "terminal": "CORE_01D_EXACT_PR_TRIGGER_DISPOSITION_B1_REVIEW_READY_7_RESOLVED_DO_NOT_MERGE",
    })


def validate_source_inventory(value: dict[str, object]) -> None:
    raw = (ROOT / SOURCE_INVENTORY_PATH).read_bytes()
    boundary.require(raw == boundary.canonical(value), "source inventory is not canonical")
    boundary.require(value.get("canonical_sha256") == SOURCE_INVENTORY_SHA256,
                     "B1 source inventory pinned identity drift")
    current = _current_source_identities()
    boundary.require(current == value.get("current_source_identities"),
                     "current relevant source identity drift")
    boundary.require(_canonical_digest(current) == CURRENT_SOURCE_IDENTITIES_SHA256,
                     "current source identity set differs from reviewed B1 inventory")
    historical = value.get("historical_pr_head_source_identities")
    boundary.require(isinstance(historical, list)
                     and _canonical_digest(historical) == HISTORICAL_SOURCE_IDENTITIES_SHA256,
                     "historical PR-head source inventory drift")
    expected_historical_keys = {(pr, PR_HEADS[pr], path)
                                for pr, paths in HISTORICAL_PATHS_BY_PR.items() for path in paths}
    actual_historical_keys = {(row["pr_number"], row["pr_head_sha"], row["path"]) for row in historical}
    boundary.require(actual_historical_keys == expected_historical_keys,
                     "historical PR-head source scope drift")
    boundary.require(value.get("base_main_sha") == BASE_MAIN and value.get("base_tree_sha") == BASE_TREE,
                     "B1 source inventory base drift")
    boundary.require(value.get("scope", {}).get("target_keys") == list(TARGET_KEYS),
                     "B1 source inventory target set drift")


def validate_receipt(value: dict[str, object], expected: dict[str, object] | None = None) -> None:
    raw = (ROOT / RECEIPT_PATH).read_bytes()
    boundary.require(raw == boundary.canonical(value), "B1 receipt is not canonical")
    expected = build_receipt(observed_at=_receipt_observation_time(value)) if expected is None else expected
    boundary.require(value == expected, "B1 receipt differs from source/metadata-derived disposition")
    boundary.require(len(value["review_rows"]) == 7 and value["scope"]["resolved_count"] == 7,
                     "B1 must resolve exactly seven target surfaces")
    boundary.require(all(row["reachability"]["historical_actions_rerun_residual"] == RERUN_RESIDUAL
                         for row in value["review_rows"]), "historical Actions rerun residual was erased")
    for row in value["review_rows"]:
        key = row["workflow_path"] + "#" + row["trigger_kind"]
        edited_event = TARGETS[key]["event_types"] == ["edited"]
        expected_reachability = (
            "CURRENT_EDIT_EVENT_MAY_BE_DELIVERED_BUT_MERGED_DRAFT_GUARD_BLOCKS_CAPTURE_AUTHORITY"
            if edited_event else
            "CURRENT_DECLARED_PULL_REQUEST_TRIGGER_SPENT_EXACT_MERGED_PR_BINDING"
        )
        boundary.require(row["reachability"]["declared_trigger_current_reachability"] == expected_reachability,
                         "pull_request event reachability is not source-derived: " + key)
        boundary.require(row["reachability"]["pull_request_event_may_be_delivered"] is edited_event,
                         "pull_request event delivery possibility was misstated: " + key)
        if edited_event:
            pr_number = TARGETS[key]["pr"]
            expected_effect = (
                "NONE_DRAFT_GUARD_FAILS_CLOSED" if pr_number == 199 else
                "NO_PROVIDER_CAPTURE; ALWAYS_UPLOAD_ACTION_FAILS_ON_ABSENT_CAMPAIGN_PATH; STEP_SUMMARY_IS_WRITTEN"
            )
            boundary.require(row["reachability"]["current_external_capture_authority"] == expected_effect,
                             "edited event bypasses the exact merged draft guard: " + key)
    boundary.require(not any("WORKFLOW_HAS_NO_AUTHORITY" in str(row) for row in value["review_rows"]),
                     "per-trigger result overclaims workflow-wide authority")


def _receipt_observation_time(value: dict[str, object]) -> str:
    timestamps = {row["live_bound_pr"]["observed_at_utc"] for row in value["review_rows"]}
    boundary.require(len(timestamps) == 1, "GitHub PR observation timestamps differ")
    timestamp = next(iter(timestamps))
    boundary.require(bool(re.fullmatch(r"2026-10-03T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", timestamp)),
                     "invalid bounded GitHub metadata observation time")
    return timestamp


def audit() -> dict[str, object]:
    inventory = _strict_json(SOURCE_INVENTORY_PATH)
    validate_source_inventory(inventory)
    value = _strict_json(RECEIPT_PATH)
    validate_receipt(value)
    return {"result": "PASS", "source_inventory_sha256": inventory["canonical_sha256"],
            "receipt_sha256": value["canonical_sha256"], "resolved": value["scope"]["resolved_count"],
            "partial": value["scope"]["partial_count"], "terminal": value["terminal"]}


def _write_evidence() -> None:
    historical = capture_historical_source_identities()
    inventory = build_source_inventory(historical_rows=historical)
    (ROOT / SOURCE_INVENTORY_PATH).write_bytes(boundary.canonical(inventory))
    # Inventory pins are intentionally computed after the first capture; no
    # predecessor generation or receipt is ever rewritten.
    current_sha = _canonical_digest(inventory["current_source_identities"])
    historical_sha = _canonical_digest(inventory["historical_pr_head_source_identities"])
    print(json.dumps({"source_inventory_sha256": inventory["canonical_sha256"],
                      "current_source_identities_sha256": current_sha,
                      "historical_source_identities_sha256": historical_sha}, sort_keys=True))


def _write_receipt(observed_at: str) -> None:
    value = build_receipt(observed_at=observed_at)
    (ROOT / RECEIPT_PATH).write_bytes(boundary.canonical(value))
    print(value["canonical_sha256"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-source-inventory", action="store_true")
    parser.add_argument("--write-receipt")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.capture_source_inventory:
        _write_evidence()
    elif args.write_receipt:
        _write_receipt(args.write_receipt)
    else:
        print(json.dumps(audit(), sort_keys=True))


if __name__ == "__main__":
    main()
