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
import marshal
from functools import lru_cache
import io
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tokenize
from typing import TypedDict
import yaml

from runtime.source_identity import (
    SourceIdentityError,
    read_tracked_head_blob,
    validate_repository_relative_path,
)

ROOT = Path(__file__).resolve().parents[1]
_A2_PATH_READ_BYTES_BASELINE = Path.read_bytes
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
# These path-exact forward-source transitions preserve immutable historical
# B4/B6 identities while authenticating each reviewed E3 successor separately.
# Predecessor fixtures are evidence only; they are never imported or packaged.
SOURCE_FORWARD_PREDECESSOR_GENERATION = 273
SOURCE_FORWARD_PREDECESSOR_SHA256 = "9d9ad9404d659c7548b89aec6a795ee3d511fdca23f4d8673550d1f2c569e809"
SOURCE_FORWARD_AUTHORIZATION_GENERATION = 274
SOURCE_FORWARD_AUTHORIZATION_SHA256 = "0655816adeb22f4ec5dcdb1012ee15af5c98c08c95c0b98286d451216e5377fc"
E3_B6_SOURCE_FORWARD_PREDECESSOR_GENERATION = 275
E3_B6_SOURCE_FORWARD_PREDECESSOR_SHA256 = "8457db3718c62c42895f306818598fd0f48d6bf6f5b70a41e1a7938c59880fdc"
E3_B6_SOURCE_FORWARD_AUTHORIZATION_GENERATION = 276
E3_B6_SOURCE_FORWARD_AUTHORIZATION_SHA256 = "b648df655f80af20482ea8810aaf82a0d6d41799854908a3f3d18b697d3f3d29"
E3_B6_SOURCE_FORWARD_PATHS = frozenset({
    "domain/current_fotmob_latest_durable_fresh_history.py",
    "domain/current_shadow_sportybet_pc_upcoming_discovery.py",
    "scripts/issue_current_fotmob_reviewed_source.py",
})
SOURCE_FORWARD_ALLOWED_PATHS = frozenset({
    "domain/sportybet_live_event_quote_evidence.py",
    *E3_B6_SOURCE_FORWARD_PATHS,
})
SOURCE_FORWARD_TRANSITIONS = {
    "domain/sportybet_live_event_quote_evidence.py": {
        "predecessor_fixture": (
            "tests/fixtures/core_01d/sportybet_event_detail_e3_forward/"
            "original-b4-b6-sportybet-live-event-quote-evidence.py.txt"
        ),
        "predecessor_byte_size": 56007,
        "predecessor_git_blob_sha1": "096d54fe7493f6d81cdf3c4af7c4a9333c75fadc",
        "predecessor_lf_source_sha256": "5d64143321e12313bb239b6d3973c8b5da5fb28855649e9890194f233ff0b48f",
        "successor_git_blob_sha1": "13e83b15e4d01cdaa95b83d4aeb5a465a63322d2",
        "successor_lf_source_sha256": "4c316538ac87c8f8e6151c0f9dae37e58e349e6c84b7e01eaeb29b4bc36f66bb",
        "a2_predecessor_generation": SOURCE_FORWARD_PREDECESSOR_GENERATION,
        "a2_predecessor_sha256": SOURCE_FORWARD_PREDECESSOR_SHA256,
        "a2_generation": SOURCE_FORWARD_AUTHORIZATION_GENERATION,
        "a2_authorization_sha256": SOURCE_FORWARD_AUTHORIZATION_SHA256,
        "reason_type": "E3_RUN_02A_DURABLE_CANCELLATION_OPERATION_AUTHORIZATION",
        "reason": (
            "E3 RUN-02A durable cancellation/operation-authorization boundary for "
            "product SportyBet event-detail GET and bounded evidence publication"
        ),
    },
    "domain/current_fotmob_latest_durable_fresh_history.py": {
        "predecessor_fixture": (
            "tests/fixtures/core_01d/e3_b6_three_source_forward/"
            "original-current-fotmob-latest-durable-fresh-history.py.txt"
        ),
        "predecessor_byte_size": 43798,
        "predecessor_git_blob_sha1": "4e5695711078acb06fba537f3f69ca1e2c9df470",
        "predecessor_lf_source_sha256": "2f3eb3473acdcab1bf10a0e6431708aa8225b2b2f279bf10405e669f453386ab",
        "successor_git_blob_sha1": "8efc9d0f70e651be74bcf528119f2fc462bd7c50",
        "successor_lf_source_sha256": "bb89e01104ccf6357cba9f3e935a6ed3d32a2ab09d0a1064dd63a6221c9b9a09",
        "a2_predecessor_generation": E3_B6_SOURCE_FORWARD_PREDECESSOR_GENERATION,
        "a2_predecessor_sha256": E3_B6_SOURCE_FORWARD_PREDECESSOR_SHA256,
        "a2_generation": E3_B6_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
        "a2_authorization_sha256": E3_B6_SOURCE_FORWARD_AUTHORIZATION_SHA256,
        "reason_type": "E3_RUN_02A_DURABLE_CANCELLATION_OPERATION_AUTHORIZATION",
        "reason": (
            "E3 RUN-02A durable cancellation/operation-authorization boundary for "
            "current FotMob latest durable fresh-history provider operations"
        ),
    },
    "domain/current_shadow_sportybet_pc_upcoming_discovery.py": {
        "predecessor_fixture": (
            "tests/fixtures/core_01d/e3_b6_three_source_forward/"
            "original-current-shadow-sportybet-pc-upcoming-discovery.py.txt"
        ),
        "predecessor_byte_size": 45046,
        "predecessor_git_blob_sha1": "fa2069a2ea1201a93a84b5ce3856f9d9574dea71",
        "predecessor_lf_source_sha256": "0d4d1af14a47e935bf2669c8abf6dbf6409e9f8d72f4070c3bb0b8abc7eec1a3",
        "successor_git_blob_sha1": "2a4030b3a330637dcbfe0e688da8054c1158d157",
        "successor_lf_source_sha256": "d3b2db5331883b96b8af4a2a5520461fad774cac1d246659413527d13ba788af",
        "a2_predecessor_generation": E3_B6_SOURCE_FORWARD_PREDECESSOR_GENERATION,
        "a2_predecessor_sha256": E3_B6_SOURCE_FORWARD_PREDECESSOR_SHA256,
        "a2_generation": E3_B6_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
        "a2_authorization_sha256": E3_B6_SOURCE_FORWARD_AUTHORIZATION_SHA256,
        "reason_type": "E3_RUN_02A_DURABLE_CANCELLATION_OPERATION_AUTHORIZATION",
        "reason": (
            "E3 RUN-02A durable cancellation/operation-authorization boundary for "
            "current Shadow SportyBet PC upcoming discovery"
        ),
    },
    "scripts/issue_current_fotmob_reviewed_source.py": {
        "predecessor_fixture": (
            "tests/fixtures/core_01d/e3_b6_three_source_forward/"
            "original-issue-current-fotmob-reviewed-source.py.txt"
        ),
        "predecessor_byte_size": 27513,
        "predecessor_git_blob_sha1": "b50689971ee20cb6800145317a0e9fcb3486f40f",
        "predecessor_lf_source_sha256": "449e83af1a8e25bf5b054b88682b8559363196ca2d6e1dad87c742949b8d0484",
        "successor_git_blob_sha1": "432f72290bd7f10e61e13173bd89e0eed8b96aea",
        "successor_lf_source_sha256": "9dabb9e9844000509028d9933b3ee54c290d7df3de2f35b0046f8a5a0b188cfd",
        "a2_predecessor_generation": E3_B6_SOURCE_FORWARD_PREDECESSOR_GENERATION,
        "a2_predecessor_sha256": E3_B6_SOURCE_FORWARD_PREDECESSOR_SHA256,
        "a2_generation": E3_B6_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
        "a2_authorization_sha256": E3_B6_SOURCE_FORWARD_AUTHORIZATION_SHA256,
        "reason_type": "E3_RUN_02A_DURABLE_CANCELLATION_OPERATION_AUTHORIZATION",
        "reason": (
            "E3 RUN-02A durable cancellation/operation-authorization boundary for "
            "reviewed current FotMob source issuance"
        ),
    },
}
# E3 cross-contract compatibility is a separate, append-only transition from
# the exact A2 V283 candidate.  V274/V276 and their predecessor records above
# remain unchanged.  This finite path set covers only current E3 sources whose
# historical auditors or retained source pins must keep reading exact bytes.
E3_CROSS_CONTRACT_SOURCE_FORWARD_PREDECESSOR_GENERATION = 283
E3_CROSS_CONTRACT_SOURCE_FORWARD_PREDECESSOR_SHA256 = \
    "870906754447e9044294b21350a68d34afd86c3513a82cc4a83ef3dfdf800209"
E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION = 284
E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_SHA256 = "c2f31e8268eadb282465ee85132cacc6eff572de98dea6e811d42b0e74cc7a7a"
# V284 recorded the capture anchor's exact Git blob and size but its normalized
# SHA-256 literal omitted one character. Preserve that immutable generation and
# append a one-anchor correction after V287; the correction grants no authority.
E3_CROSS_CONTRACT_V284_CAPTURE_ANCHOR_LF_SHA256 = \
    "7364da10ff20f48aee24808de115a9dbcfca7dc58c93b571b9e87b13cccce4f"
E3_CROSS_CONTRACT_ANCHOR_CORRECTION_PREDECESSOR_GENERATION = 287
E3_CROSS_CONTRACT_ANCHOR_CORRECTION_PREDECESSOR_SHA256 = \
    "7679a71844aa2b89280a9b7d65760cafe791e7efeed878717700fdd483f26c91"
E3_CROSS_CONTRACT_ANCHOR_CORRECTION_GENERATION = 288
E3_CROSS_CONTRACT_ANCHOR_CORRECTION_SHA256 = "da515b92b3cd8b50e7ce7866d37e98abfb116d712a7a965f7a2c6f1558110511"
E3_CROSS_CONTRACT_CAPTURE_ANCHOR_CORRECTED_LF_SHA256 = \
    "7364da10ff20f48aee24808bde115a9dbcfca7dc58c93b571b9e87b13cccce4f"
E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION = 297
E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_PREDECESSOR_SHA256 = \
    "280104293e58f49ae2b9ce12f2eeee12ffa76a9ab4c975583c3898b2d315dcd0"
E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_GENERATION = 298
E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_PATH = \
    "scripts/audit_core_01d_checkpoint_e_completion_v2.py"
E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_IDENTITY = (
    "414d1253bec0e03730b1f7ac9c2f0f3a53ff86ac",
    "7da9fa4c2b3f44764a15bedb71d75b018553af624fd794d6540db5574b3cb451",
)
E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_CANONICAL_SHA256 = \
    "6b4c8471e2839c626fe432129cdda34053a13aed81d480b299c2a4534fc0a985"
E3_CROSS_CONTRACT_V284_SOURCE_FORWARD_PATHS = frozenset({
    "domain/sportybet_live_event_quote_evidence.py",
    "domain/current_fotmob_latest_durable_fresh_history.py",
    "domain/current_shadow_sportybet_pc_upcoming_discovery.py",
    "scripts/issue_current_fotmob_reviewed_source.py",
    "domain/current_shadow_all_market_runner.py",
    "domain/reviewed_fixture_catalog_admission_source_replay.py",
    "scripts/execute_current_shadow_request.py",
    "scripts/audit_core_01d_port02c_trigger_authority_b6.py",
    "runtime/worker_entry.py",
    "scripts/audit_auth_01_analysis_only_shadow_worker_boundary.py",
    "scripts/audit_core_01d_checkpoint_e_completion_v2.py",
})
# Keep the historical public V284 view exact. Existing consumers use this
# eleven-entry set together with the V284 transition table.
E3_CROSS_CONTRACT_SOURCE_FORWARD_PATHS = E3_CROSS_CONTRACT_V284_SOURCE_FORWARD_PATHS
_E3_CROSS_CONTRACT_SUCCESSORS = {
    "domain/sportybet_live_event_quote_evidence.py": (
        "13e83b15e4d01cdaa95b83d4aeb5a465a63322d2",
        "4c316538ac87c8f8e6151c0f9dae37e58e349e6c84b7e01eaeb29b4bc36f66bb",
    ),
    "domain/current_fotmob_latest_durable_fresh_history.py": (
        "8efc9d0f70e651be74bcf528119f2fc462bd7c50",
        "bb89e01104ccf6357cba9f3e935a6ed3d32a2ab09d0a1064dd63a6221c9b9a09",
    ),
    "domain/current_shadow_sportybet_pc_upcoming_discovery.py": (
        "71eb1b288a2c18caf907c29bec476b7db6c5e9da",
        "c39f80f857d2dc5e898bbf0b9bad85908e0e9bdd6fdc1a1f924c3f14bc8a6234",
    ),
    "scripts/issue_current_fotmob_reviewed_source.py": (
        "9aeb6d26d7d8fd2b83229cbf4e057847622e70f4",
        "ea349d025e650e120aa0ca1eba95bd1e35583f0791789397447a4be015681917",
    ),
    "domain/current_shadow_all_market_runner.py": (
        "2dbfaa1f2367e494c01df01c48cd86322d2975bb",
        "8b80a61d1705d396688b26bc9bb12b1eb63ba205a8dcb83a91fa42012b48d08a",
    ),
    "domain/reviewed_fixture_catalog_admission_source_replay.py": (
        "4fa64f4d134a8f7042575185f9b97f1a6b8fcbd2",
        "fa15bba1a4d0c3000e3fcfa64ad62d38c93bb9f07ea3eb2047d8d70dd69586f8",
    ),
    "scripts/execute_current_shadow_request.py": (
        "d92cd7159fcedab33f78865cc4f46fb27ab0204f",
        "d356cc5ddbac2642aaf3fcb9b237a53eed0b2c33065b53ced3db0a4048a7c2d6",
    ),
    "scripts/audit_core_01d_port02c_trigger_authority_b6.py": (
        "89fa1378743fbbf7db4b3aa0ed9d5bd35f9ef513",
        "831ac85757db1517071e2c6ef57148ce60367f92c061dc4ce66ae93e355474a0",
    ),
    "runtime/worker_entry.py": (
        "58ff830f63b5d875d873c1927b95e1b045da7364",
        "c5378dfbdcb4bbfac0815847cc48de04c7049a25268a04e364efaed6a26e788e",
    ),
    "scripts/audit_auth_01_analysis_only_shadow_worker_boundary.py": (
        "1e7b6bee6bb01287067f70269722c2bd492ddea9",
        "dff62d695f3f7246d14df22aededcefe8c5fc576ef92dec7ed6355dffe92451c",
    ),
    "scripts/audit_core_01d_checkpoint_e_completion_v2.py": (
        "9564fcafdb53d99d674109b6fb5a27ab518a80fa",
        "2655acceb3226db0c111ee2cb5d4adb1a7a254c65f180fdd27a39016415125c7",
    ),
}
E3_CROSS_CONTRACT_SOURCE_FORWARD_TRANSITIONS = {}
for _e3_path in SOURCE_FORWARD_ALLOWED_PATHS:
    _e3_transition = dict(SOURCE_FORWARD_TRANSITIONS[_e3_path])
    _e3_transition["successor_git_blob_sha1"], _e3_transition["successor_lf_source_sha256"] = \
        _E3_CROSS_CONTRACT_SUCCESSORS[_e3_path]
    _e3_transition["a2_predecessor_generation"] = E3_CROSS_CONTRACT_SOURCE_FORWARD_PREDECESSOR_GENERATION
    _e3_transition["a2_predecessor_sha256"] = E3_CROSS_CONTRACT_SOURCE_FORWARD_PREDECESSOR_SHA256
    _e3_transition["a2_generation"] = E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION
    _e3_transition["a2_authorization_sha256"] = E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_SHA256
    E3_CROSS_CONTRACT_SOURCE_FORWARD_TRANSITIONS[_e3_path] = _e3_transition
E3_CROSS_CONTRACT_SOURCE_FORWARD_TRANSITIONS.update({
    "domain/current_shadow_all_market_runner.py": {
        "predecessor_fixture": "tests/fixtures/core_01d/e3_cross_contract_source_forward/original-current-shadow-all-market-runner.py.txt",
        "predecessor_byte_size": 68966,
        "predecessor_git_blob_sha1": "b21a9d8a24ac60def6d76e7111ae8a473e9f1a8c",
        "predecessor_lf_source_sha256": "43f770741b10747bc917e039b2aeca6a466ac6a3d59d0a42a8f5b2bb5a086cf7",
        "successor_git_blob_sha1": _E3_CROSS_CONTRACT_SUCCESSORS["domain/current_shadow_all_market_runner.py"][0],
        "successor_lf_source_sha256": _E3_CROSS_CONTRACT_SUCCESSORS["domain/current_shadow_all_market_runner.py"][1],
        "reason_type": "E3_RUN_02A_CROSS_CONTRACT_COMPATIBILITY_V1",
        "reason": "E3 product provider operations are authorized at the owned Current Shadow request boundary",
    },
    "domain/reviewed_fixture_catalog_admission_source_replay.py": {
        "predecessor_fixture": "tests/fixtures/core_01d/e3_cross_contract_source_forward/original-reviewed-fixture-catalog-admission-source-replay.py.txt",
        "predecessor_byte_size": 24800,
        "predecessor_git_blob_sha1": "b2fd258fa89afc492da35cbbe242b15203040759",
        "predecessor_lf_source_sha256": "2061974642bc903482772303db49e589a991c58d8ffbd94d6a137f24f8582de5",
        "successor_git_blob_sha1": _E3_CROSS_CONTRACT_SUCCESSORS["domain/reviewed_fixture_catalog_admission_source_replay.py"][0],
        "successor_lf_source_sha256": _E3_CROSS_CONTRACT_SUCCESSORS["domain/reviewed_fixture_catalog_admission_source_replay.py"][1],
        "reason_type": "E3_RUN_02A_CROSS_CONTRACT_COMPATIBILITY_V1",
        "reason": "E3 keeps frozen fixture replay data-only while authenticating its current source successor",
    },
    "scripts/execute_current_shadow_request.py": {
        "predecessor_fixture": "tests/fixtures/core_01d/e3_cross_contract_source_forward/original-execute-current-shadow-request.py.txt",
        "predecessor_byte_size": 11076,
        "predecessor_git_blob_sha1": "52519a5f32cc0d8c130ea053fde5647b751e3fc0",
        "predecessor_lf_source_sha256": "bbaa767d45db82b4dec4dfb7e64abdfcb92a90e5c63d7c915b246eb6306155c5",
        "successor_git_blob_sha1": _E3_CROSS_CONTRACT_SUCCESSORS["scripts/execute_current_shadow_request.py"][0],
        "successor_lf_source_sha256": _E3_CROSS_CONTRACT_SUCCESSORS["scripts/execute_current_shadow_request.py"][1],
        "reason_type": "E3_RUN_02A_CROSS_CONTRACT_COMPATIBILITY_V1",
        "reason": "E3 nested Current Shadow supervisor proves the exact owner, run, attempt, lease and gate",
    },
    "scripts/audit_core_01d_port02c_trigger_authority_b6.py": {
        "predecessor_fixture": "tests/fixtures/core_01d/e3_cross_contract_source_forward/original-port02c-trigger-authority-b6.py.txt",
        "predecessor_byte_size": 63794,
        "predecessor_git_blob_sha1": "a36066a0b03c03f76e416f1b9235146717b2f483",
        "predecessor_lf_source_sha256": "261692333467a99de066abe046ba61614dd1879d68856fec980781f884a7588a",
        "successor_git_blob_sha1": _E3_CROSS_CONTRACT_SUCCESSORS["scripts/audit_core_01d_port02c_trigger_authority_b6.py"][0],
        "successor_lf_source_sha256": _E3_CROSS_CONTRACT_SUCCESSORS["scripts/audit_core_01d_port02c_trigger_authority_b6.py"][1],
        "reason_type": "E3_RUN_02A_CROSS_CONTRACT_COMPATIBILITY_V1",
        "reason": "E3 PR459 compatibility reads the V154 B6 auditor predecessor as evidence only",
    },
    "runtime/worker_entry.py": {
        "predecessor_fixture": "tests/fixtures/core_01d/run_02a_pre_historical/worker-entry-pr463-base.py.txt",
        "predecessor_byte_size": 8914,
        "predecessor_git_blob_sha1": "113acdf1ece29ca2977e4e3d2d84576a31fe7828",
        "predecessor_lf_source_sha256": "98d5b1d7cfbc524be876f7000f9e605caac013039893d4f028ac2452216a2a61",
        "successor_git_blob_sha1": _E3_CROSS_CONTRACT_SUCCESSORS["runtime/worker_entry.py"][0],
        "successor_lf_source_sha256": _E3_CROSS_CONTRACT_SUCCESSORS["runtime/worker_entry.py"][1],
        "reason_type": "E3_RUN_02A_CROSS_CONTRACT_COMPATIBILITY_V1",
        "reason": "E3 historical AUTH-01 parser replay is data-only; product execution remains gate-bound",
    },
    "scripts/audit_auth_01_analysis_only_shadow_worker_boundary.py": {
        "predecessor_fixture": "tests/fixtures/core_01d/run_02a_pre_historical/auth-worker-boundary-pr463-base.py.txt",
        "predecessor_byte_size": 27128,
        "predecessor_git_blob_sha1": "8115c18631e445f825dee0b0fa78c1a7cd77e460",
        "predecessor_lf_source_sha256": "7b6532d9155f5a096c38c12ad003c6bd076e0f329cc0ee26898cf0b5b0b5e795",
        "successor_git_blob_sha1": _E3_CROSS_CONTRACT_SUCCESSORS["scripts/audit_auth_01_analysis_only_shadow_worker_boundary.py"][0],
        "successor_lf_source_sha256": _E3_CROSS_CONTRACT_SUCCESSORS["scripts/audit_auth_01_analysis_only_shadow_worker_boundary.py"][1],
        "reason_type": "E3_RUN_02A_CROSS_CONTRACT_COMPATIBILITY_V1",
        "reason": "E3 AUTH-01 static replay distinguishes exact historical parsing from product gate authority",
    },
    "scripts/audit_core_01d_checkpoint_e_completion_v2.py": {
        "predecessor_fixture": "tests/fixtures/core_01d/e3_cross_contract_source_forward/original-checkpoint-e-completion-v2.py.txt",
        "predecessor_byte_size": 35648,
        "predecessor_git_blob_sha1": "957bc5376fd7707e15e0e292f04d1e413151e95c",
        "predecessor_lf_source_sha256": "5798f64d84a578496a8a2ecb9174e9246590f1daee1b79013f28d6b6d797b706",
        "successor_git_blob_sha1": _E3_CROSS_CONTRACT_SUCCESSORS["scripts/audit_core_01d_checkpoint_e_completion_v2.py"][0],
        "successor_lf_source_sha256": _E3_CROSS_CONTRACT_SUCCESSORS["scripts/audit_core_01d_checkpoint_e_completion_v2.py"][1],
        "reason_type": "E3_RUN_02A_CROSS_CONTRACT_COMPATIBILITY_V1",
        "reason": "Pass-A historical tree projection preserves exact source rows while authenticating E3 successors",
    },
})
# The seven additive records above are part of the same V284 authorization.
# Bind every declaration to that exact predecessor and authorization, matching
# the four records constructed from the pre-existing B4/B6 transition table.
for _e3_transition in E3_CROSS_CONTRACT_SOURCE_FORWARD_TRANSITIONS.values():
    _e3_transition.update({
        "a2_predecessor_generation": E3_CROSS_CONTRACT_SOURCE_FORWARD_PREDECESSOR_GENERATION,
        "a2_predecessor_sha256": E3_CROSS_CONTRACT_SOURCE_FORWARD_PREDECESSOR_SHA256,
        "a2_generation": E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
        "a2_authorization_sha256": E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_SHA256,
    })

# The following exact Pass-A paths are current E3 compatibility successors
# whose frozen V2 source rows predate the product changes. Keep them in a
# separate append-only authorization so the immutable V284 eleven-path
# payload above remains byte-for-byte unchanged.
E3_PASS_A_SOURCE_FORWARD_PREDECESSOR_GENERATION = 2
E3_PASS_A_SOURCE_FORWARD_PREDECESSOR_SHA256 = (
    "c7b12447b7f671b2ece76d1207b404cd4555cc45d2e2ec88451682d6e0b4f14e"
)
E3_PASS_A_SOURCE_FORWARD_BASE_MAIN_SHA = \
    "84d452f354dd09714db541f28488058b61e72033"
E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_GENERATION = 300
E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_PREDECESSOR_GENERATION = 299
E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_PREDECESSOR_SHA256 = (
    "81c47aa1bbcd55604908257fe468e5f9066d3b8cf66787dd18308dccd2c124e4"
)
E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY = \
    "tests/fixtures/core_01d/pass_a_e3_audit_predecessors"


class E3PassASourceForwardTransition(TypedDict):
    predecessor_fixture: str
    predecessor_git_mode: str
    predecessor_byte_size: int
    predecessor_git_blob_sha1: str
    predecessor_lf_source_sha256: str
    successor_git_blob_sha1: str
    successor_lf_source_sha256: str
    successor_git_mode: str


E3_PASS_A_SOURCE_FORWARD_TRANSITIONS: dict[str, E3PassASourceForwardTransition] = {
    "scripts/audit_p4_4e_current_fotmob_ingest_issuer.py": {
        "predecessor_fixture": E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/original-audit-p4-4e-current-fotmob-ingest-issuer.py.txt",
        "predecessor_git_mode": "100644",
        "predecessor_byte_size": 17207,
        "predecessor_git_blob_sha1": "fc772ced8b8c1d0d433179fcc04765ed1b273438",
        "predecessor_lf_source_sha256": "8be7e40aad917dcd52e79473224aff520aba9c5d3072bdd18ee52d2e1b00d0ce",
        "successor_git_blob_sha1": "0012001df95ca82853d3cd80c5dd0cd11830eec4",
        "successor_lf_source_sha256": "1d07e6be402462a2cf09309111c511d80db0f35764601e77641b10ba96ac943f",
        "successor_git_mode": "100644",
    },
    "scripts/audit_p4_4f_current_fotmob_exact_lane_caller_migration.py": {
        "predecessor_fixture": E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/original-audit-p4-4f-current-fotmob-exact-lane-caller-migration.py.txt",
        "predecessor_git_mode": "100644",
        "predecessor_byte_size": 30193,
        "predecessor_git_blob_sha1": "74dc0f87592bf956ab649070d9059075e2645989",
        "predecessor_lf_source_sha256": "a015a817253878cc192d0ca26b99bb393ae6354e20cfa4ab418ee69bcd9d64cf",
        "successor_git_blob_sha1": "11836a56e930b71236567d84507e0f0cef51fb6b",
        "successor_lf_source_sha256": "2196516b5b929d237676548de4f4fd5ca49ebcbd7d229ccb93f45c75fc347fb6",
        "successor_git_mode": "100644",
    },
    "scripts/audit_p4_4g_current_fotmob_canonical_only_workflow.py": {
        "predecessor_fixture": E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/original-audit-p4-4g-current-fotmob-canonical-only-workflow.py.txt",
        "predecessor_git_mode": "100644",
        "predecessor_byte_size": 36776,
        "predecessor_git_blob_sha1": "0884f6837db4c27745f67601574a2a9f20e97df2",
        "predecessor_lf_source_sha256": "94455db594506e20b23668fbd5eab187ed4d47836a82de930090ed1fd5f782f5",
        "successor_git_blob_sha1": "a49a34706038b5ed94180316fd5d0b32a2bb979d",
        "successor_lf_source_sha256": "d3b7fad2ac90531b79e591f0d939a20efd4febcba9a85a54f012f05b49231542",
        "successor_git_mode": "100644",
    },
    "scripts/audit_p4_4h_current_shadow_canonical_run_migration_review.py": {
        "predecessor_fixture": E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/original-audit-p4-4h-current-shadow-canonical-run-migration-review.py.txt",
        "predecessor_git_mode": "100644",
        "predecessor_byte_size": 42050,
        "predecessor_git_blob_sha1": "ab0f2261e0a30a165b5e48ee9643feda8e4273ab",
        "predecessor_lf_source_sha256": "d1b9c361444f31f157dbbf011827ccda5dad8bed19f73daca32fd32c3cedddae",
        "successor_git_blob_sha1": "4ad358f9d808d7068a1dabea244912ee0c84f97f",
        "successor_lf_source_sha256": "404b2b49519ecd3f5f9a2357f2d7fe8fc58fc899422ee314db83895f23865621",
        "successor_git_mode": "100644",
    },
    "scripts/audit_port_01_source_identity_parity.py": {
        "predecessor_fixture": E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/original-audit-port-01-source-identity-parity.py.txt",
        "predecessor_git_mode": "100644",
        "predecessor_byte_size": 24728,
        "predecessor_git_blob_sha1": "ef19eedecff06268f5c2c2c1b6372d240ff39df3",
        "predecessor_lf_source_sha256": "a9464ba8e7110a2ad6a93bffcdabe1dd8fc64ac544751edee726d67e7832d42b",
        "successor_git_blob_sha1": "da065883ddf343298e0968f04ca7ee5a28146249",
        "successor_lf_source_sha256": "acad737c52226ff749a17420712fefcb67fb67747bc58cd531d06e66ba75bf8c",
        "successor_git_mode": "100644",
    },
    "scripts/execute_current_shadow_daily.py": {
        "predecessor_fixture": E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/original-execute-current-shadow-daily.py.txt",
        "predecessor_git_mode": "100644",
        "predecessor_byte_size": 12262,
        "predecessor_git_blob_sha1": "c2ea5eb021fd7ce72bfd5447458468f75a28a101",
        "predecessor_lf_source_sha256": "014882f29144bfa6e84437da5fb742f2a83cb253082910b834a2e24c1130cc4d",
        "successor_git_blob_sha1": "0bb82c9beff1d6e47bf010aa753973253eeb4ec4",
        "successor_lf_source_sha256": "692ca308d08242cdb80c05f299fe10c107535d3c75c854d5c747e0bc4dcec0fe",
        "successor_git_mode": "100644",
    },
    "tests/test_issue_current_fotmob_reviewed_source.py": {
        "predecessor_fixture": E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/original-test-issue-current-fotmob-reviewed-source.py.txt",
        "predecessor_git_mode": "100644",
        "predecessor_byte_size": 13713,
        "predecessor_git_blob_sha1": "4fa54db086b2689b1dd7a60ae12c64f50c8eec75",
        "predecessor_lf_source_sha256": "9dae4210bf8e326ca87f8caa737852a07f8ca5d53e717568430473451df405c6",
        "successor_git_blob_sha1": "8b02c6c298ee598979d8d12362bd7b6eaf81880b",
        "successor_lf_source_sha256": "d84b6385ecab8fdeda7cf4e4acedbafb0ce18a0e97d372ace8e9abc7c4ff78f3",
        "successor_git_mode": "100644",
    },
    "tests/test_p4_4h_current_shadow_canonical_run_migration_review.py": {
        "predecessor_fixture": E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/original-test-p4-4h-current-shadow-canonical-run-migration-review.py.txt",
        "predecessor_git_mode": "100644",
        "predecessor_byte_size": 28883,
        "predecessor_git_blob_sha1": "204a756c040bc00c36fd676449f970537209e0cf",
        "predecessor_lf_source_sha256": "3a57ac069fee56b2af03438050d92bd02704baa5c175e1cb4dab5a113fbb952c",
        "successor_git_blob_sha1": "09b3cc311e73d1c93c9de0e59fea9491649edcd2",
        "successor_lf_source_sha256": "9b1aeab3b86d1896c845e180b7e94286712afc3f127034a6293241e26ae82a9f",
        "successor_git_mode": "100644",
    },
}
E3_PASS_A_SOURCE_FORWARD_PATHS = frozenset({
    "scripts/audit_p4_4e_current_fotmob_ingest_issuer.py",
    "scripts/audit_p4_4f_current_fotmob_exact_lane_caller_migration.py",
    "scripts/audit_p4_4g_current_fotmob_canonical_only_workflow.py",
    "scripts/audit_p4_4h_current_shadow_canonical_run_migration_review.py",
    "scripts/audit_port_01_source_identity_parity.py",
    "scripts/execute_current_shadow_daily.py",
    "tests/test_issue_current_fotmob_reviewed_source.py",
    "tests/test_p4_4h_current_shadow_canonical_run_migration_review.py",
})
E3_PASS_A_SOURCE_FORWARD_FIXTURE_PATHS = frozenset({
    E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/original-audit-p4-4e-current-fotmob-ingest-issuer.py.txt",
    E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/original-audit-p4-4f-current-fotmob-exact-lane-caller-migration.py.txt",
    E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/original-audit-p4-4g-current-fotmob-canonical-only-workflow.py.txt",
    E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/original-audit-p4-4h-current-shadow-canonical-run-migration-review.py.txt",
    E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/original-audit-port-01-source-identity-parity.py.txt",
    E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/original-execute-current-shadow-daily.py.txt",
    E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/original-test-issue-current-fotmob-reviewed-source.py.txt",
    E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/original-test-p4-4h-current-shadow-canonical-run-migration-review.py.txt",
})
# Three pre-existing B3/B5/B6 snapshots share the directory. They remain owned
# by their original Checkpoint-E predecessor map and are not V300 sources.
E3_PASS_A_SOURCE_FORWARD_EXISTING_FIXTURE_PATHS = frozenset({
    E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/original-audit-core-01d-frozen-artifact-replay-authority-b5.py.txt",
    E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/original-audit-core-01d-owner-one-shot-issue-comment-authority-b3.py.txt",
    E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/original-audit-core-01d-scheduled-shadow-ownership.py.txt",
})
E3_PASS_A_COMPAT_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION = 300
E3_PASS_A_COMPAT_SUCCESSOR_EXTENSION_GENERATION = 301
E3_PASS_A_COMPAT_SUCCESSOR_EXTENSION_PATH = \
    "scripts/audit_core_01d_checkpoint_e_completion_v2.py"
E3_PASS_A_COMPAT_SUCCESSOR_EXTENSION_IDENTITY = (
    "12069f4c4d39890db743501913be17e6559973ca",
    "fd1a5b45171aebe4538d712863d3d4c3790625ba123564a61c7decd102bfa9a1",
)
E3_PASS_A_V309_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION = 308
E3_PASS_A_V309_SUCCESSOR_EXTENSION_PREDECESSOR_SHA256 = \
    "a77faa05b57ac16074658f2d01c106b541f1c80ddb3d4ac5a72003aceeb87020"
E3_PASS_A_V309_SUCCESSOR_EXTENSION_GENERATION = 309
E3_PASS_A_V309_SUCCESSOR_EXTENSION_PATH = \
    "scripts/audit_core_01d_checkpoint_e_completion_v2.py"
E3_PASS_A_V309_SUCCESSOR_EXTENSION_PREDECESSOR = {
    "fixture_path": "tests/fixtures/core_01d/e3_v309_source_forward/original-checkpoint-e-completion-v2-v308.py.txt",
    "git_blob_sha1": "12069f4c4d39890db743501913be17e6559973ca",
    "lf_source_sha256": "fd1a5b45171aebe4538d712863d3d4c3790625ba123564a61c7decd102bfa9a1",
    "byte_size": 41516,
}
E3_PASS_A_V309_SUCCESSOR_EXTENSION_IDENTITY = (
    "eb0bbff694c051d83ad93c3d731569308fbf44cd",
    "565b84b7d2b21b5a3e17ae1cdc837428e928ebc3fe8b143b2ff28ba1127b900d",
)
E3_PASS_A_V312_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION = 311
E3_PASS_A_V312_SUCCESSOR_EXTENSION_PREDECESSOR_SHA256 = \
    "10284bd90f45a3eddd5ccca203c5a2749dc7ff3508fcd487987ff03ff72dac3d"
E3_PASS_A_V312_SUCCESSOR_EXTENSION_GENERATION = 312
E3_PASS_A_V312_SUCCESSOR_EXTENSION_PATH = \
    "scripts/audit_core_01d_checkpoint_e_completion_v2.py"
E3_PASS_A_V312_SUCCESSOR_EXTENSION_PREDECESSOR = {
    "git_blob_sha1": "938ee2a10e1f34d1226da537b8591fc3d6f098f4",
    "lf_source_sha256": "1d818d3c0be8d9b64b4318374e48c0f36258bacf98eb4c99d9275842600aaf0c",
}
E3_PASS_A_V312_SUCCESSOR_EXTENSION_IDENTITY = (
    "938ee2a10e1f34d1226da537b8591fc3d6f098f4",
    "1d818d3c0be8d9b64b4318374e48c0f36258bacf98eb4c99d9275842600aaf0c",
)
E3_PASS_A_V313_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION = 312
E3_PASS_A_V313_SUCCESSOR_EXTENSION_PREDECESSOR_SHA256 = \
    "83e988fecb8d24464ec68663f3896a9e37f5e5bcd0591525ac6c348efe1e2c32"
E3_PASS_A_V313_SUCCESSOR_EXTENSION_GENERATION = 313
E3_PASS_A_V313_SUCCESSOR_EXTENSION_PATH = \
    "scripts/audit_core_01d_checkpoint_e_completion_v2.py"
E3_PASS_A_V313_SUCCESSOR_EXTENSION_PREDECESSOR = {
    "git_blob_sha1": "938ee2a10e1f34d1226da537b8591fc3d6f098f4",
    "lf_source_sha256": "1d818d3c0be8d9b64b4318374e48c0f36258bacf98eb4c99d9275842600aaf0c",
}
E3_PASS_A_V313_SUCCESSOR_EXTENSION_IDENTITY = (
    "3768669aaa4400ead8cdf63978bf6da953b0062e",
    "c376e7c55ad95d4e182b2e4c6626e0c1605bf7834e6b81abeae432e1d06212f1",
)
RCV_RECOVERY_V376_SOURCE_PREDECESSOR_SHA256 = (
    "486e41d2e67bf844371683b5efcdd6cae7510e874889bb3416d2ff5713646102"
)
RCV_RECOVERY_V377_INVENTORY_SHA256 = (
    "467846f44798c99dd8582e6bcc54b23c8a390c9e833a3ae175722b0bf288c191"
)
RCV_RECOVERY_V377_CHECKPOINT_V2_IDENTITY = {
    "git_blob_sha1": "5422fe486af775744cc249a3fa6ec8f8eeaac127",
    "lf_source_sha256": "9bff92fb1d98486ddb6cc0f5fb3f585338a078724643278b2045fe6afd2c32e3",
    "git_mode": "100644",
}
RCV_RECOVERY_V378_CHECKPOINT_V2_GENERATION = 378


def resolve_historical_source_transition(path, *, expected_generation):
    """Resolve one path only through its explicitly requested A2 generation."""
    require(type(path) is str, "historical source path must be exact text")
    require(type(expected_generation) is int,
            "historical source generation must be an exact integer")
    if expected_generation == E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION:
        paths = E3_CROSS_CONTRACT_V284_SOURCE_FORWARD_PATHS
        transitions = E3_CROSS_CONTRACT_SOURCE_FORWARD_TRANSITIONS
        expected_count = 11
    elif expected_generation == E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_GENERATION:
        paths = E3_PASS_A_SOURCE_FORWARD_PATHS
        transitions = E3_PASS_A_SOURCE_FORWARD_TRANSITIONS
        expected_count = 8
    else:
        raise AssertionError("unsupported historical source transition generation")
    require(len(paths) == expected_count and set(transitions) == set(paths),
            "historical source transition table has an unreviewed path set")
    require(not (set(E3_CROSS_CONTRACT_V284_SOURCE_FORWARD_PATHS)
                 & set(E3_PASS_A_SOURCE_FORWARD_PATHS)),
            "historical source path is ambiguous across V284 and V300")
    require(path in paths,
            "path is not authorized by the requested historical source generation: " + repr(path))
    if expected_generation == E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_GENERATION:
        fixture_paths = [row.get("predecessor_fixture")
                         for row in transitions.values() if type(row) is dict]
        require(set(fixture_paths) == set(E3_PASS_A_SOURCE_FORWARD_FIXTURE_PATHS)
                and len(fixture_paths) == len(set(fixture_paths)),
                "V300 predecessor fixture table has a duplicate or unreviewed path")
    return transitions[path]


def _e3_pass_a_v309_source_successor_extension(chain):
    """Append one exact V309 successor to the unchanged V301 source chain."""
    predecessor_generation = E3_PASS_A_V309_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION
    require(type(chain) is list and len(chain) >= predecessor_generation,
            "E3 V309 source successor requires the exact V308 predecessor")
    predecessor_path, predecessor = chain[predecessor_generation - 1]
    require(predecessor_path == inventory_generation_path(predecessor_generation)
            and predecessor.get("generation") == predecessor_generation
            and predecessor.get("canonical_sha256")
                == E3_PASS_A_V309_SUCCESSOR_EXTENSION_PREDECESSOR_SHA256,
            "E3 V309 source successor predecessor inventory drift")
    predecessor_rows = {row["path"]: row["lf_source_sha256"]
                        for row in predecessor.get("source_identities", [])
                        if type(row) is dict and type(row.get("path")) is str}
    expected_predecessor = E3_PASS_A_V309_SUCCESSOR_EXTENSION_PREDECESSOR
    require(predecessor_rows.get(E3_PASS_A_V309_SUCCESSOR_EXTENSION_PATH)
            == expected_predecessor["lf_source_sha256"],
            "E3 V309 source successor does not match the V308 source identity")
    return {
        "path": E3_PASS_A_V309_SUCCESSOR_EXTENSION_PATH,
        "generation": E3_PASS_A_V309_SUCCESSOR_EXTENSION_GENERATION,
        "predecessor_inventory": {
            "path": predecessor_path,
            "canonical_sha256": predecessor["canonical_sha256"],
            "generation": predecessor_generation,
            "rewritten": False,
        },
        "previous_successor": {
            "generation": predecessor_generation,
            "canonical_sha256": predecessor["canonical_sha256"],
            "git_blob_sha1": expected_predecessor["git_blob_sha1"],
            "lf_source_sha256": expected_predecessor["lf_source_sha256"],
            "rewritten": False,
        },
        "predecessor_fixture": {
            "path": expected_predecessor["fixture_path"],
            "git_blob_sha1": expected_predecessor["git_blob_sha1"],
            "lf_source_sha256": expected_predecessor["lf_source_sha256"],
            "byte_size": expected_predecessor["byte_size"],
        },
        "successor": {
            "git_blob_sha1": E3_PASS_A_V309_SUCCESSOR_EXTENSION_IDENTITY[0],
            "lf_source_sha256": E3_PASS_A_V309_SUCCESSOR_EXTENSION_IDENTITY[1],
            "git_mode": "100644",
        },
        "reason_type": "E3_RUN_02A_PASS_A_SOURCE_FORWARD_V309",
        "reason": "V309 authenticates the exact successor while preserving the V1/V2 historical source projections",
        "authority_granted": False,
        "historical_bytes_changed": False,
        "rewritten": False,
    }


def _e3_pass_a_v312_source_successor_extension(chain):
    """Bind the current V2 auditor source row to the exact V311 inventory."""
    predecessor_generation = E3_PASS_A_V312_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION
    require(type(chain) is list and len(chain) >= predecessor_generation,
            "E3 V312 source successor requires the exact V311 predecessor")
    predecessor_path, predecessor = chain[predecessor_generation - 1]
    require(predecessor_path == inventory_generation_path(predecessor_generation)
            and predecessor.get("generation") == predecessor_generation
            and predecessor.get("schema_version") == predecessor_generation
            and predecessor.get("canonical_sha256")
                == E3_PASS_A_V312_SUCCESSOR_EXTENSION_PREDECESSOR_SHA256,
            "E3 V312 source successor predecessor inventory drift")
    predecessor_rows = {row["path"]: row["lf_source_sha256"]
                        for row in predecessor.get("source_identities", [])
                        if type(row) is dict and type(row.get("path")) is str}
    expected_predecessor = E3_PASS_A_V312_SUCCESSOR_EXTENSION_PREDECESSOR
    require(predecessor_rows.get(E3_PASS_A_V312_SUCCESSOR_EXTENSION_PATH)
            == expected_predecessor["lf_source_sha256"],
            "E3 V312 source successor does not match the exact V311 source row")
    # V312 is a historical source-forward row. The latest generation below
    # authenticates the current source, which may have advanced at V313.
    return {
        "path": E3_PASS_A_V312_SUCCESSOR_EXTENSION_PATH,
        "generation": E3_PASS_A_V312_SUCCESSOR_EXTENSION_GENERATION,
        "predecessor_inventory": {
            "path": predecessor_path,
            "canonical_sha256": predecessor["canonical_sha256"],
            "generation": predecessor_generation,
            "rewritten": False,
        },
        "previous_successor": {
            "generation": predecessor_generation,
            "canonical_sha256": predecessor["canonical_sha256"],
            "git_blob_sha1": expected_predecessor["git_blob_sha1"],
            "lf_source_sha256": expected_predecessor["lf_source_sha256"],
            "rewritten": False,
        },
        "successor": {
            "git_blob_sha1": E3_PASS_A_V312_SUCCESSOR_EXTENSION_IDENTITY[0],
            "lf_source_sha256": E3_PASS_A_V312_SUCCESSOR_EXTENSION_IDENTITY[1],
            "git_mode": "100644",
        },
        "reason_type": "E3_RUN_02A_PASS_A_SOURCE_FORWARD_V312",
        "reason": "V312 binds the exact V311 Pass-A V2 auditor source row while preserving its authenticated historical projections",
        "authority_granted": False,
        "historical_bytes_changed": False,
        "rewritten": False,
    }


def _e3_pass_a_v313_source_successor_extension(chain):
    """Append the exact current V2 auditor source to its unchanged V312 row."""
    predecessor_generation = E3_PASS_A_V313_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION
    require(type(chain) is list and len(chain) >= predecessor_generation,
            "E3 V313 source successor requires the exact V312 predecessor")
    predecessor_path, predecessor = chain[predecessor_generation - 1]
    require(predecessor_path == inventory_generation_path(predecessor_generation)
            and predecessor.get("generation") == predecessor_generation
            and predecessor.get("schema_version") == predecessor_generation
            and predecessor.get("canonical_sha256")
                == E3_PASS_A_V313_SUCCESSOR_EXTENSION_PREDECESSOR_SHA256,
            "E3 V313 source successor predecessor inventory drift")
    predecessor_rows = {row["path"]: row["lf_source_sha256"]
                        for row in predecessor.get("source_identities", [])
                        if type(row) is dict and type(row.get("path")) is str}
    expected_predecessor = E3_PASS_A_V313_SUCCESSOR_EXTENSION_PREDECESSOR
    require(predecessor_rows.get(E3_PASS_A_V313_SUCCESSOR_EXTENSION_PATH)
            == expected_predecessor["lf_source_sha256"],
            "E3 V313 source successor does not match the exact V312 source row")
    _e3_source_forward_file_identity(
        E3_PASS_A_V313_SUCCESSOR_EXTENSION_PATH,
        fixture=False,
        expected_blob=E3_PASS_A_V313_SUCCESSOR_EXTENSION_IDENTITY[0],
        expected_lf=E3_PASS_A_V313_SUCCESSOR_EXTENSION_IDENTITY[1],
        expected_size=0,
        expected_mode="100644",
    )
    return {
        "path": E3_PASS_A_V313_SUCCESSOR_EXTENSION_PATH,
        "generation": E3_PASS_A_V313_SUCCESSOR_EXTENSION_GENERATION,
        "predecessor_inventory": {
            "path": predecessor_path,
            "canonical_sha256": predecessor["canonical_sha256"],
            "generation": predecessor_generation,
            "rewritten": False,
        },
        "previous_successor": {
            "generation": predecessor_generation,
            "canonical_sha256": predecessor["canonical_sha256"],
            "git_blob_sha1": expected_predecessor["git_blob_sha1"],
            "lf_source_sha256": expected_predecessor["lf_source_sha256"],
            "rewritten": False,
        },
        "successor": {
            "git_blob_sha1": E3_PASS_A_V313_SUCCESSOR_EXTENSION_IDENTITY[0],
            "lf_source_sha256": E3_PASS_A_V313_SUCCESSOR_EXTENSION_IDENTITY[1],
            "git_mode": "100644",
        },
        "reason_type": "E3_RUN_02A_PASS_A_SOURCE_FORWARD_V313",
        "reason": "V313 authenticates the exact V2 auditor successor while retaining V312 and the immutable V1/V2 projections",
        "authority_granted": False,
        "historical_bytes_changed": False,
        "rewritten": False,
    }


# The root bootstrap pins this auditor: the adapter cannot choose its own after identity.
RETENTION_MAIN347_CHECKPOINT_EXTENSION = {'path': 'scripts/audit_core_01d_checkpoint_e_completion_v2.py', 'generation': 348, 'predecessor_inventory': {'path': 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v347.json', 'generation': 347, 'canonical_sha256': '55d1aa9b8899b3d680b51117e1d596204ffae8536edeed3ceb453b40611d5a29', 'rewritten': False}, 'previous_successor': {'generation': 313, 'canonical_sha256': 'c71dd53f24e1bf70d216d7a71e9b914ed8a8cb9a452fc12455106bd921d5eac8', 'git_blob_sha1': '3768669aaa4400ead8cdf63978bf6da953b0062e', 'lf_source_sha256': 'c376e7c55ad95d4e182b2e4c6626e0c1605bf7834e6b81abeae432e1d06212f1', 'rewritten': False}, 'successor': {'git_blob_sha1': '1c8eb65538550f5f196b7af4520323c391f6291b', 'lf_source_sha256': '98608e88c84defa2dc7065a00108250bd0b891fabb503907aa7bfc82d3753773', 'git_mode': '100644'}, 'reason_type': 'PHASE_A_RETENTION_MAIN347_SOURCE_FORWARD_V348', 'reason': 'Path-exact retention projection after the unchanged V313 evaluator and canonical main V347', 'authority_granted': False, 'historical_bytes_changed': False, 'rewritten': False}


def _e3_cross_contract_source_forward_successor_extensions(chain=None, generation=None):
    """Exact V298, V301, V309, V312 and V313 append-only source successors."""
    path = E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_PATH
    prior = resolve_historical_source_transition(
        path, expected_generation=E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
    )
    extension = {
        "path": path,
        "generation": E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_GENERATION,
        "predecessor_inventory": {
            "path": inventory_generation_path(E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION),
            "canonical_sha256": E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_PREDECESSOR_SHA256,
            "generation": E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION,
            "rewritten": False,
        },
        "previous_successor": {
            "generation": E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
            "canonical_sha256": E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_SHA256,
            "git_blob_sha1": prior["successor_git_blob_sha1"],
            "lf_source_sha256": prior["successor_lf_source_sha256"],
            "rewritten": False,
        },
        "successor": {
            "git_blob_sha1": E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_IDENTITY[0],
            "lf_source_sha256": E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_IDENTITY[1],
        },
        "reason_type": "E3_RUN_02A_PASS_A_COMPATIBILITY_SOURCE_FORWARD_V1",
        "reason": "Pass-A source projection preserves its immutable historical tree while the current source remains A2-authenticated",
        "authority_granted": False,
        "historical_bytes_changed": False,
        "rewritten": False,
    }
    if chain is None:
        chain = load_inventory_generations()
    if generation is None:
        generation = len(chain)
    require(type(generation) is int,
            "E3 source-forward corpus generation must be an exact integer")
    extensions = [extension]
    if generation >= E3_PASS_A_COMPAT_SUCCESSOR_EXTENSION_GENERATION:
        predecessor_generation = E3_PASS_A_COMPAT_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION
        require(len(chain) >= predecessor_generation
                and chain[predecessor_generation - 1][0]
                    == inventory_generation_path(predecessor_generation),
                "V301 E3 successor extension requires the exact V300 predecessor")
        predecessor = chain[predecessor_generation - 1][1]
        require(predecessor.get("generation") == predecessor_generation
                and predecessor.get("canonical_sha256")
                and predecessor.get("e3_pass_a_source_predecessor_authorization")
                    == _e3_pass_a_source_predecessor_authorization(),
                "V301 E3 successor extension predecessor identity drift")
        extensions.append({
            "path": E3_PASS_A_COMPAT_SUCCESSOR_EXTENSION_PATH,
            "generation": E3_PASS_A_COMPAT_SUCCESSOR_EXTENSION_GENERATION,
            "predecessor_inventory": {
                "path": inventory_generation_path(predecessor_generation),
                "canonical_sha256": predecessor["canonical_sha256"],
                "generation": predecessor_generation,
                "rewritten": False,
            },
            "previous_successor": {
                "generation": E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_GENERATION,
                "canonical_sha256": E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_CANONICAL_SHA256,
                "git_blob_sha1": E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_IDENTITY[0],
                "lf_source_sha256": E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_IDENTITY[1],
                "rewritten": False,
            },
            "successor": {
                "git_blob_sha1": E3_PASS_A_COMPAT_SUCCESSOR_EXTENSION_IDENTITY[0],
                "lf_source_sha256": E3_PASS_A_COMPAT_SUCCESSOR_EXTENSION_IDENTITY[1],
                "git_mode": "100644",
            },
            "reason_type": "E3_RUN_02A_PASS_A_COMPATIBILITY_SOURCE_FORWARD_V2",
            "reason": "V301 preserves the V284 historical predecessor while authenticating the generation-aware D5 projection successor",
            "authority_granted": False,
            "historical_bytes_changed": False,
            "rewritten": False,
        })
    if generation >= E3_PASS_A_V309_SUCCESSOR_EXTENSION_GENERATION:
        extensions.append(_e3_pass_a_v309_source_successor_extension(chain))
    if generation >= E3_PASS_A_V312_SUCCESSOR_EXTENSION_GENERATION:
        extensions.append(_e3_pass_a_v312_source_successor_extension(chain))
    if generation >= E3_PASS_A_V313_SUCCESSOR_EXTENSION_GENERATION:
        extensions.append(_e3_pass_a_v313_source_successor_extension(chain))
    if generation >= 348:
        from scripts import audit_phase_a_pc_upcoming_retention_successor as retention
        current_retention = retention.checkpoint_retention_extension(chain)
        require(canonical(current_retention) == canonical(RETENTION_MAIN347_CHECKPOINT_EXTENSION),
                "retention source-forward extension exceeds the root-pinned contract")
        extensions.append(current_retention)
    if generation >= 377:
        extensions.append(_e3_checkpoint_v2_v377_source_extension(chain, generation))
        extensions.append(_e3_port02c_b6_v377_source_extension(chain, generation))
    if generation >= RCV_RECOVERY_V378_CHECKPOINT_V2_GENERATION:
        extensions.append(_e3_checkpoint_v2_v378_source_extension(chain, generation))
    return extensions


def _e3_checkpoint_v2_v377_source_extension(chain, generation):
    """Reconstruct the frozen V377 V2 edge without consulting today's source."""
    predecessor_generation = 376
    require(type(chain) is list and len(chain) >= predecessor_generation
            and type(generation) is int and generation >= 377,
            "E3 checkpoint V377 source successor requires the exact V376 chain")
    predecessor_path, predecessor = chain[predecessor_generation - 1]
    require(predecessor_path == inventory_generation_path(predecessor_generation)
            and predecessor.get("generation") == predecessor_generation
            and predecessor.get("schema_version") == predecessor_generation
            and predecessor.get("canonical_sha256")
                == RCV_RECOVERY_V376_SOURCE_PREDECESSOR_SHA256,
            "E3 checkpoint V377 source predecessor path or generation drift")
    path = E3_PASS_A_V313_SUCCESSOR_EXTENSION_PATH
    previous_rows = {row["path"]: row["lf_source_sha256"]
                     for row in predecessor.get("source_identities", [])
                     if type(row) is dict and type(row.get("path")) is str}
    previous_lf = previous_rows.get(path)
    require(type(previous_lf) is str and len(previous_lf) == 64,
            "E3 checkpoint V377 previous source identity is absent")
    require(previous_lf == RETENTION_MAIN347_CHECKPOINT_EXTENSION["successor"]["lf_source_sha256"],
            "E3 checkpoint V377 predecessor differs from the authenticated V348 source")
    return {
        "path": path,
        "generation": 377,
        "predecessor_inventory": {
            "path": predecessor_path,
            "canonical_sha256": predecessor["canonical_sha256"],
            "generation": predecessor_generation,
            "rewritten": False,
        },
        "previous_successor": {
            "generation": predecessor_generation,
            "canonical_sha256": predecessor["canonical_sha256"],
            "lf_source_sha256": previous_lf,
            "rewritten": False,
        },
        "successor": dict(RCV_RECOVERY_V377_CHECKPOINT_V2_IDENTITY),
        "reason_type": "RCV_RECOVERY_CHECKPOINT_V2_SOURCE_FORWARD_V377",
        "reason": "Append-only current source identity after the unchanged V1-V376 chain and exact V313/V348 historical projections",
        "authority_granted": False,
        "historical_bytes_changed": False,
        "rewritten": False,
    }


def _e3_checkpoint_v2_v378_source_extension(chain, generation):
    """Append the current V2 bytes after the immutable V377 source identity."""
    require(type(chain) is list and len(chain) >= 377
            and type(generation) is int and generation >= RCV_RECOVERY_V378_CHECKPOINT_V2_GENERATION,
            "E3 checkpoint V378 source successor requires the exact V377 chain")
    v377_path, v377 = chain[376]
    frozen = _e3_checkpoint_v2_v377_source_extension(chain, 377)
    require(v377_path == inventory_generation_path(377)
            and v377.get("generation") == 377
            and v377.get("schema_version") == 377
            and v377.get("canonical_sha256") == RCV_RECOVERY_V377_INVENTORY_SHA256
            and v377.get("predecessor_inventory") == frozen["predecessor_inventory"],
            "E3 checkpoint V378 predecessor is not the immutable V377 inventory")
    frozen_rows = {row["path"]: row["lf_source_sha256"]
                   for row in v377.get("source_identities", [])
                   if type(row) is dict and type(row.get("path")) is str}
    require(frozen_rows.get(frozen["path"]) == frozen["successor"]["lf_source_sha256"],
            "E3 checkpoint V377 inventory does not preserve its frozen V2 identity")
    frozen_extensions = [row for row in v377.get("e3_cross_contract_source_forward_successor_extensions", [])
                         if type(row) is dict and row.get("path") == frozen["path"]
                         and row.get("generation") == 377]
    require(frozen_extensions == [frozen],
            "E3 checkpoint V377 historical source edge is missing or altered")

    from scripts import audit_phase_a_pc_upcoming_retention_successor as retention
    current_source = retention.checkpoint_v2_current_source()
    current = retention.identity(current_source)
    require(current["git_blob_sha1"] != frozen["successor"]["git_blob_sha1"]
            and current["source_sha256"] != frozen["successor"]["lf_source_sha256"],
            "E3 checkpoint V378 source successor did not change the frozen V377 bytes")
    return {
        "path": frozen["path"],
        "generation": RCV_RECOVERY_V378_CHECKPOINT_V2_GENERATION,
        "predecessor_inventory": {
            "path": v377_path,
            "canonical_sha256": v377["canonical_sha256"],
            "generation": 377,
            "rewritten": False,
        },
        "previous_successor": {
            "generation": 377,
            "canonical_sha256": v377["canonical_sha256"],
            "git_blob_sha1": frozen["successor"]["git_blob_sha1"],
            "lf_source_sha256": frozen["successor"]["lf_source_sha256"],
            "rewritten": False,
        },
        "successor": {
            "git_blob_sha1": current["git_blob_sha1"],
            "lf_source_sha256": current["source_sha256"],
            "git_mode": "100644",
        },
        "reason_type": "RCV_RECOVERY_CHECKPOINT_V2_SOURCE_FORWARD_V378",
        "reason": "Append-only current V2 source after the frozen V377 identity; V1-V377 history is unchanged",
        "authority_granted": False,
        "historical_bytes_changed": False,
        "rewritten": False,
    }


def _e3_port02c_b6_v377_source_extension(chain, generation):
    """Append the current B6 source after its unchanged V284 successor."""
    predecessor_generation = 376
    path = "scripts/audit_core_01d_port02c_trigger_authority_b6.py"
    require(type(chain) is list and len(chain) >= predecessor_generation
            and type(generation) is int and generation >= 377,
            "E3 B6 V377 source successor requires the exact V376 chain")
    predecessor_path, predecessor = chain[predecessor_generation - 1]
    require(predecessor_path == inventory_generation_path(predecessor_generation)
            and predecessor.get("generation") == predecessor_generation
            and predecessor.get("schema_version") == predecessor_generation
            and predecessor.get("canonical_sha256")
                == RCV_RECOVERY_V376_SOURCE_PREDECESSOR_SHA256,
            "E3 B6 V377 source predecessor path or generation drift")
    transition = resolve_historical_source_transition(
        path, expected_generation=E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
    )
    predecessor_rows = {
        row["path"]: row["lf_source_sha256"]
        for row in predecessor.get("source_identities", [])
        if type(row) is dict and type(row.get("path")) is str
    }
    previous_lf = predecessor_rows.get(path)
    require(previous_lf == transition["successor_lf_source_sha256"],
            "E3 B6 V377 predecessor does not preserve the exact V284 successor")

    candidate = _e3_path_stat(path, label="B6 V377 current source")
    try:
        raw, identity = _read_tracked_head_blob_scoped(ROOT, path)
        worktree_raw = candidate.read_bytes()
    except (OSError, SourceIdentityError) as error:
        raise AssertionError("E3 B6 V377 current source identity is unavailable") from error
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    worktree_normalized = worktree_raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    require(worktree_normalized == normalized
            and identity.git_blob_sha1 != transition["successor_git_blob_sha1"],
            "E3 B6 V377 source is unchanged or differs from exact tracked bytes")
    entry = git("ls-tree", "-z", "HEAD", "--", path)
    require(bool(entry), "E3 B6 V377 source is not tracked at HEAD")
    try:
        metadata, tree_path = entry.rstrip(b"\0").split(b"\t", 1)
        mode, kind, blob = metadata.decode("ascii").split(" ")
    except (UnicodeDecodeError, ValueError) as error:
        raise AssertionError("E3 B6 V377 HEAD tree entry is malformed") from error
    require(tree_path.decode("utf-8") == path and mode == "100644"
            and kind == "blob" and blob == identity.git_blob_sha1,
            "E3 B6 V377 source mode/path/blob identity drift")
    return {
        "path": path,
        "generation": 377,
        "predecessor_inventory": {
            "path": predecessor_path,
            "canonical_sha256": predecessor["canonical_sha256"],
            "generation": predecessor_generation,
            "rewritten": False,
        },
        "previous_successor": {
            "generation": predecessor_generation,
            "canonical_sha256": predecessor["canonical_sha256"],
            "git_blob_sha1": transition["successor_git_blob_sha1"],
            "lf_source_sha256": previous_lf,
            "rewritten": False,
        },
        "successor": {
            "git_blob_sha1": identity.git_blob_sha1,
            "lf_source_sha256": hashlib.sha256(normalized).hexdigest(),
            "git_mode": "100644",
        },
        "reason_type": "RCV_RECOVERY_B6_SOURCE_FORWARD_V377",
        "reason": "Append-only B6 source identity after the unchanged V1-V376 chain and exact V284 predecessor projection",
        "authority_granted": False,
        "historical_bytes_changed": False,
        "rewritten": False,
    }


def _authenticate_e3_v309_predecessor_fixture(extension):
    expected = E3_PASS_A_V309_SUCCESSOR_EXTENSION_PREDECESSOR
    fixture_path = expected["fixture_path"]
    require(extension.get("predecessor_fixture") == {
        "path": fixture_path,
        "git_blob_sha1": expected["git_blob_sha1"],
        "lf_source_sha256": expected["lf_source_sha256"],
        "byte_size": expected["byte_size"],
    }, "E3 V309 source predecessor fixture authorization drift")
    raw = _e3_read_exact_head_fixture(
        fixture_path,
        expected_blob=expected["git_blob_sha1"],
        expected_lf=expected["lf_source_sha256"],
        expected_size=expected["byte_size"],
        label="V309 predecessor fixture",
    )
    entry = git("ls-tree", "-z", "HEAD", "--", fixture_path)
    require(bool(entry), "E3 V309 source predecessor fixture is not tracked")
    metadata, path_bytes = entry.rstrip(b"\0").split(b"\t", 1)
    mode, kind, tracked_blob = metadata.decode("ascii").split(" ")
    require(path_bytes.decode("utf-8") == fixture_path and mode == "100644"
            and kind == "blob" and tracked_blob == expected["git_blob_sha1"],
            "E3 V309 source predecessor fixture mode or HEAD blob mismatch")
    return raw


E3_CROSS_CONTRACT_SUPPORTING_SOURCE_ANCHORS = {
    "scripts/capture_fotmob_data_matches.py": {
        "fixture_path": "tests/fixtures/core_01d/e3_cross_contract_source_forward/original-capture-fotmob-data-matches.py.txt",
        "byte_size": 26628,
        "git_blob_sha1": "10b8858ab62f2708bd564d578a627c43718e5a12",
        "lf_source_sha256": "7364da10ff20f48aee24808bde115a9dbcfca7dc58c93b571b9e87b13cccce4f",
        "purpose": "exact unchanged capture source preserving direct Fresh Holdout and ordinary-FT semantics",
    },
    "domain/fotmob_utc_native_expected_goals_fresh_holdout_activation_runner.py": {
        "fixture_path": "tests/fixtures/core_01d/e3_cross_contract_source_forward/original-fresh-holdout-activation-runner.py.txt",
        "byte_size": 60460,
        "git_blob_sha1": "901ab137d6601a3485eac30da7e6bad7eeefa397",
        "lf_source_sha256": "ac14ac89a60a80cae736483dfd4516424a553401a31af4a1934204d81205dc4b",
        "purpose": "exact unchanged direct Fresh Holdout source; no product authority added",
    },
    "scripts/run_fotmob_ordinary_ft_source_history_acquisition.py": {
        "fixture_path": "tests/fixtures/core_01d/e3_cross_contract_source_forward/original-ordinary-ft-source-history-acquisition.py.txt",
        "byte_size": 38943,
        "git_blob_sha1": "6f067b8f069a760248a3b0b624c88d4f91aaa7ef",
        "lf_source_sha256": "68707cee683a2194b933c6e2a10a3f1f80699b1ccf40204f299c1501a586e40d",
        "purpose": "exact unchanged ordinary FT source-history request timing and offline semantics",
    },
}
E3_CROSS_CONTRACT_SUPPORTING_SOURCE_CORRECTIONS = {
    "scripts/capture_fotmob_data_matches.py": {
        "fixture_path": "tests/fixtures/core_01d/e3_cross_contract_source_forward/original-capture-fotmob-data-matches.py.txt",
        "byte_size": 26628,
        "git_blob_sha1": "10b8858ab62f2708bd564d578a627c43718e5a12",
        "superseded_lf_source_sha256": E3_CROSS_CONTRACT_V284_CAPTURE_ANCHOR_LF_SHA256,
        "lf_source_sha256": E3_CROSS_CONTRACT_CAPTURE_ANCHOR_CORRECTED_LF_SHA256,
        "purpose": "correct the V284 normalized digest typo for the unchanged direct capture source",
    },
}
E3_CROSS_CONTRACT_SUPPORTING_SOURCE_PATHS = frozenset({
    "scripts/capture_fotmob_data_matches.py",
    "domain/fotmob_utc_native_expected_goals_fresh_holdout_activation_runner.py",
    "scripts/run_fotmob_ordinary_ft_source_history_acquisition.py",
})
E3_CROSS_CONTRACT_FIXTURE_DIRECTORY = \
    "tests/fixtures/core_01d/e3_cross_contract_source_forward"
E3_CROSS_CONTRACT_FIXTURE_PATHS = frozenset({
    transition["predecessor_fixture"]
    for transition in E3_CROSS_CONTRACT_SOURCE_FORWARD_TRANSITIONS.values()
    if transition["predecessor_fixture"].startswith(E3_CROSS_CONTRACT_FIXTURE_DIRECTORY + "/")
} | {
    anchor["fixture_path"] for anchor in E3_CROSS_CONTRACT_SUPPORTING_SOURCE_ANCHORS.values()
})
# Frozen repository location: a successor's predecessor binding always names the
# canonical committed path, whichever isolated directory the chain is checked in.
INVENTORY_CANONICAL_DIRECTORY = INVENTORY_DIRECTORY
RECEIPT_PATH = "artifacts/architecture/core_01d_ci_offline_transport_boundary_v1.json"
RECEIPT_SHA256 = "5d0385f77463d3e7a9f804b431df7e2c2c9c4908c266326bf35b05a50086f8e2"
COMPLETION_PATH = "artifacts/architecture/core_01d_checkpoint_e_completion_v3.json"
COMPLETION_V3_SHA256 = "27516b35fb5e836ac2d851fa60e4300ebf347e00b00f3858b46671cd77af9d79"
# The immutable lg_a remediation receipt pins the hash of every tracked row
# under artifacts/ at HEAD, and the allowance list that could exempt a new
# artifact row is itself inside the pinned bounded evidence scope, so a new
# artifacts/ row could only be admitted by rewriting immutable evidence. This
# generation-chain receipt therefore lives with the inventory generations it
# binds rather than under artifacts/.
BRIDGE_RECEIPT_PATH = "tests/fixtures/core_01d/ci-offline-transport-boundary-evolution-bridge-receipt-v1.json"
EVOLUTION_TEST_PATH = "tests/test_core_01d_ci_offline_transport_inventory_evolution.py"
TARGETS = ((".github/workflows/athena-patch-bridge.yml", "issue_comment"),
           (".github/workflows/tests.yml", "pull_request"), (".github/workflows/tests.yml", "push"))
A2_SUCCESSOR_WORKFLOWS = (
    ".github/workflows/create-saturday-2026-08-22-sportybet-direct-20-code.yml",
    ".github/workflows/prove-sportybet-direct-share-code.yml",
)
GUARD_PATHS = ("sitecustomize.py", "tests/conftest.py", "tests/offline_transport.py",
               "tests/offline_linux.py", "tests/_offline_bootstrap/sitecustomize.py")
A2_PATHS = frozenset((*GUARD_PATHS, INVENTORY_PATH, INVENTORY_V2_PATH, RECEIPT_PATH, COMPLETION_PATH,
    BRIDGE_RECEIPT_PATH, EVOLUTION_TEST_PATH,
    ".github/workflows/create-saturday-2026-08-22-sportybet-direct-20-code.yml",
    ".github/workflows/prove-sportybet-direct-share-code.yml",
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
# Exact A2 reviewed-head bytes for guard sources subsequently changed by a
# reviewed bridge. Hosted CI checks out depth 1, so the reviewed-head object is
# absent there and no fetch is permitted. These fallbacks keep the historical
# activation proof bound to immutable V1 identities instead of current source.
HISTORICAL_TEXT_BYTES = {
    "sitecustomize.py": base64.b64decode("IiIiQWN0aXZhdGUgdGhlIHRlc3QgYm91bmRhcnkgYmVmb3JlIHB5dGVzdCBwbHVnaW4gZGlzY292ZXJ5OyBvdGhlciBDTEkgaXMgaW5lcnQuIiIiCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aAppbXBvcnQgc3lzCgojIFBhdGNoIEJyaWRnZSBmb3JiaWRzIHRoaXMgcm9vdCBwYXRoLiBJdHMgYWxsb3dlZCB0ZXN0cy9zY3JpcHRzIHBhdGNoZXMgbXVzdAojIG5vdCByZXBsYWNlIHRoZSB0cnVzdGVkIGJvdW5kYXJ5IG9yIGF1ZGl0b3IgYmVmb3JlIHB5dGVzdCBzdGFydHMuIFRoZXNlIGFyZQojIExGIHNvdXJjZSBpZGVudGl0aWVzLCBub3Qgbm9ybWFsaXphdGlvbiBvZiBhbnkgcmF3IHJ1bnRpbWUgYXJ0aWZhY3QuClJPT1RfVEVTVF9TT1VSQ0VfUElOUyA9IHsKICAgICJzY3JpcHRzL2F1ZGl0X2NvcmVfMDFkX2NpX29mZmxpbmVfdHJhbnNwb3J0X2JvdW5kYXJ5LnB5IjogImM4MzBjODk3OTUxODA3N2ViYTBhNzc2ZjRkZjk2NTM5YjZkNTE1ZjNlNjIyZTE1MzVkZWMyYWY4YjUzNmRkYjAiLAogICAgInRlc3RzL19vZmZsaW5lX2Jvb3RzdHJhcC9zaXRlY3VzdG9taXplLnB5IjogIjFiMTk2ODIxNWI3MmY5MTNlMTdhODQwYjdiM2FjMjJhYTRlODUwOGU1ZmE1Mjk5OTA0ODdjNTliMmUwYzg3OGQiLAogICAgInRlc3RzL2NvbmZ0ZXN0LnB5IjogIjUwMGU0N2Q5OTM3ZGRmODlmNzI1ZDQxMTE3YTg0YWJmMjA3ZGUyZTc2OGE4NjFhZGM1YzRhNDljN2E4N2UwNTIiLAogICAgInRlc3RzL29mZmxpbmVfbGludXgucHkiOiAiNTY1ZTE2OThiZWJmYzMwZDU0NjNhM2MzYjZkZWQ0M2U2ZmY5Mzc4YWY5NTUxMjlhMDExYmYyOGUxYTViOTk5ZiIsCiAgICAidGVzdHMvb2ZmbGluZV90cmFuc3BvcnQucHkiOiAiYTM1ZGNjYTUyOTI5NTk4YTVmNmQ5N2E2OTI3NGU0NzVmMTBjMjIyOTg4OTU5OWE4MmQ1MzcxODg2YzQzN2FkMSIsCn0KCl9hcmdzID0gZ2V0YXR0cihzeXMsICJvcmlnX2FyZ3YiLCAoKSkKX3B5dGVzdF9tb2R1bGUgPSBhbnkoCiAgICBfYXJnc1tpOmkgKyAyXSA9PSBbIi1tIiwgInB5dGVzdCJdCiAgICBhbmQgYWxsKGZsYWcgaW4geyItdSIsICItQiIsICItcyIsICItcSIsICItdiIsICItdnYiLCAiLWIiLCAiLWJiIiwgIi1PIiwgIi1PTyJ9IGZvciBmbGFnIGluIF9hcmdzWzE6aV0pCiAgICBmb3IgaSBpbiByYW5nZSgxLCBsZW4oX2FyZ3MpIC0gMSkKKQpfcHl0ZXN0X3NjcmlwdCA9IGFueShQYXRoKGFyZykubmFtZS5sb3dlcigpIGluIHsicHl0ZXN0IiwgInB5dGVzdC5leGUiLCAicHkudGVzdCJ9IGZvciBhcmcgaW4gX2FyZ3NbMToyXSkKaWYgX3B5dGVzdF9tb2R1bGUgb3IgX3B5dGVzdF9zY3JpcHQ6CiAgICB0cnk6CiAgICAgICAgaW1wb3J0IGhhc2hsaWIKCiAgICAgICAgX3Jvb3QgPSBQYXRoKF9fZmlsZV9fKS5yZXNvbHZlKCkucGFyZW50CiAgICAgICAgZm9yIF9wYXRoLCBfZXhwZWN0ZWQgaW4gUk9PVF9URVNUX1NPVVJDRV9QSU5TLml0ZW1zKCk6CiAgICAgICAgICAgIF9yYXcgPSAoX3Jvb3QgLyBfcGF0aCkucmVhZF9ieXRlcygpLnJlcGxhY2UoYiJcclxuIiwgYiJcbiIpCiAgICAgICAgICAgIGlmIGhhc2hsaWIuc2hhMjU2KF9yYXcpLmhleGRpZ2VzdCgpICE9IF9leHBlY3RlZDoKICAgICAgICAgICAgICAgIHJhaXNlIFJ1bnRpbWVFcnJvcigidGVzdCBib3VuZGFyeSBzb3VyY2UgaWRlbnRpdHkgZHJpZnQ6ICIgKyBfcGF0aCkKICAgICAgICBzeXMucGF0aC5pbnNlcnQoMCwgc3RyKFBhdGgoX19maWxlX18pLnJlc29sdmUoKS5wYXJlbnQgLyAidGVzdHMiKSkKICAgICAgICBmcm9tIG9mZmxpbmVfdHJhbnNwb3J0IGltcG9ydCBpbnN0YWxsCgogICAgICAgIGluc3RhbGwoKQogICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlcnJvcjoKICAgICAgICAjIFB5dGhvbiBvdGhlcndpc2UgcHJpbnRzIGFuZCBpZ25vcmVzIGFuIGV4Y2VwdGlvbiBpbiBzaXRlY3VzdG9taXplLgogICAgICAgIHJhaXNlIFN5c3RlbUV4aXQoInB5dGVzdCBvZmZsaW5lIGJvdW5kYXJ5IGZhaWxlZCB0byBhY3RpdmF0ZSIpIGZyb20gZXJyb3IK"),
}
HISTORICAL_TEXT_FIXTURES = {
    "tests/offline_transport.py": "tests/fixtures/core_01d/a2-v1-offline-transport.txt",
    ".github/workflows/tests.yml": "tests/fixtures/architecture/revised_workflows/tests-pre-shard-balance-v1.yml",
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
    "no_out_of_scope_authority_rows_reviewed",
    "e3_cross_contract_source_forward_successor_extensions",
    "e3_pass_a_source_predecessor_authorization"))


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


@lru_cache(maxsize=512)
def _authenticated_json_bytes(raw, path, canonical_generation=False):
    """Cache only successful validation of exact immutable input bytes.

    No path/mtime/source-corpus verdict is cached. Callers reread the file and
    receive a newly decoded object, so neither file changes nor caller mutation
    can reuse a stale verdict. Eviction only causes validation to run again.
    """
    def pairs(items):
        value = {}
        for key, child in items:
            require(key not in value, "duplicate JSON key")
            value[key] = child
        return value
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: require(False, "nonfinite JSON"))
    require(value == seal(value), "artifact self-hash mismatch: " + path)
    if canonical_generation:
        require(lf(raw) == canonical(value), "artifact self-hash mismatch: " + path)
    return raw


@lru_cache(maxsize=512)
def _immutable_json_snapshot(raw, path, canonical_generation, validator):
    """Pure content-addressed transformation, never a current authority verdict.

    Only internally constructed marshal bytes are retained. Every caller first
    reads its actual file; a new raw payload or validator gets a new cache key.
    Loading the snapshot returns a fresh mutable tree, so caller mutation cannot
    poison the next read. No serialized input is accepted from disk or callers.
    """
    checked = validator(raw, path, True) if canonical_generation else validator(raw, path)
    return marshal.dumps(json.loads(checked), 4)


def read(path):
    raw = (ROOT / path).read_bytes()
    return marshal.loads(_immutable_json_snapshot(raw, path, False, _authenticated_json_bytes))


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
    paths.update(path for path in A2_SUCCESSOR_WORKFLOWS if (ROOT / path).is_file())
    return sorted(paths)


def current_corpus_fields(*, generation=None, chain=None):
    if chain is None:
        chain = load_inventory_generations()
    if generation is None:
        generation = len(chain)
    require(type(generation) is int and 1 <= generation <= len(chain) + 1,
            "current A2 corpus generation is outside the authenticated chain boundary")
    paths = current_source_paths()
    value = inventory_fields(paths, source, obligations)
    value["e3_cross_contract_source_forward_successor_extensions"] = \
        _e3_cross_contract_source_forward_successor_extensions(
            chain=chain, generation=generation,
        )
    if generation >= E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_GENERATION:
        value["e3_pass_a_source_predecessor_authorization"] = \
            _e3_pass_a_source_predecessor_authorization()
    return value


@lru_cache(maxsize=8)
def historical_objects_available(commit=A2_REVIEWED_HEAD):
    """True when the exact reviewed-head objects exist in this object database.

    Hosted CI checks out with fetch-depth 1, so no ancestor commit exists there
    and this probe returns False. Historical reads then use the byte-pinned
    identity chain instead of Git history; nothing is fetched and no
    environment variable selects a proof.
    """
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


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
    if path in HISTORICAL_TEXT_FIXTURES:
        fixture_path = ROOT / HISTORICAL_TEXT_FIXTURES[path]
        if path == ".github/workflows/tests.yml":
            from scripts import audit_tests_shard_balance_successor as shards
            require(HISTORICAL_TEXT_FIXTURES[path] == shards.FIXTURE,
                    "pinned historical Tests fixture differs from the reviewed shard predecessor")
            shards.authenticate()
            raw = shards.read_blob(shards.FIXTURE)
            require(shards.identity(raw) == shards.BEFORE,
                    "pinned historical Tests source identity differs from the shard predecessor")
        else:
            require(fixture_path.is_file() and not fixture_path.is_symlink(),
                    "pinned historical text fixture is missing: " + path)
            raw = lf(fixture_path.read_bytes())
        require(hashlib.sha256(raw).hexdigest() == pinned_historical_identity(path),
                "pinned historical text fixture identity mismatch: " + path)
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
    raw = (ROOT / path).read_bytes()
    return marshal.loads(_immutable_json_snapshot(raw, path, True, _authenticated_json_bytes))


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
    """Authenticate the chain, reusing a same-scope parsed chain snapshot only.

    The scope binds the canonical generation namespace and every raw generation
    byte at its outer entry/exit. The cached value is a marshal serialization,
    never a mutable object graph; every public return is a fresh list/dict tree.
    Custom directories and changed public verifier seams retain the uncached
    legacy path.
    """
    canonical_directory = directory is None or directory == INVENTORY_DIRECTORY
    scope = _active_a2_derivation_scope() if canonical_directory else None
    if scope is None:
        return _load_inventory_generations_uncached(directory)
    contract = _a2_scoped_contract()
    key = "a2.inventory-generations.chain"
    if contract is None:
        require(key not in scope.derivation_bytes,
                "A2 verifier contract changed after scoped chain authentication")
        return _load_inventory_generations_uncached(directory)
    cached = scope.load_derivation(key, contract)
    if cached is not None:
        _verify_scoped_a2_live_state(scope, directory=directory, check_git=False)
        chain = marshal.loads(cached)
        require(type(chain) is list and bool(chain)
                and all(type(item) is tuple and len(item) == 2
                        and type(item[0]) is str and type(item[1]) is dict
                        for item in chain),
                "A2 scoped generation chain clone is malformed")
        from scripts import audit_core_01d_checkpoint_e_completion_v8 as receipt_scope
        receipt_scope._record_scope_metric("a2.load_inventory_generations_scope_hits")
        return chain
    chain = _load_inventory_generations_uncached(directory)
    scope.store_derivation(key, contract, marshal.dumps(chain, 4))
    from scripts import audit_core_01d_checkpoint_e_completion_v8 as receipt_scope
    receipt_scope._record_scope_metric("a2.load_inventory_generations_scope_misses")
    return chain


def _load_inventory_generations_uncached(directory=None):
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


def _e3_b6_source_forward_authorization():
    """Exact three-path A2 authorization payload committed in generation V276."""
    sources = []
    for path in sorted(E3_B6_SOURCE_FORWARD_PATHS):
        transition = SOURCE_FORWARD_TRANSITIONS[path]
        sources.append({
            "path": path,
            "predecessor": {
                "fixture_path": transition["predecessor_fixture"],
                "git_blob_sha1": transition["predecessor_git_blob_sha1"],
                "lf_source_sha256": transition["predecessor_lf_source_sha256"],
                "byte_size": transition["predecessor_byte_size"],
            },
            "successor": {
                "git_blob_sha1": transition["successor_git_blob_sha1"],
                "lf_source_sha256": transition["successor_lf_source_sha256"],
            },
            "reason_type": transition["reason_type"],
            "reason": transition["reason"],
        })
    return {
        "schema_version": 1,
        "policy_id": "ATHENA_E3_RUN_02A_B6_THREE_SOURCE_FORWARD_V1",
        "scope": "EXACT_THREE_OWNER_AUTHORIZED_B6_SOURCE_PATHS_ONLY",
        "predecessor_inventory": {
            "path": inventory_generation_path(E3_B6_SOURCE_FORWARD_PREDECESSOR_GENERATION),
            "canonical_sha256": E3_B6_SOURCE_FORWARD_PREDECESSOR_SHA256,
            "generation": E3_B6_SOURCE_FORWARD_PREDECESSOR_GENERATION,
            "rewritten": False,
        },
        "source_identities": sources,
    }


def read_authenticated_forward_predecessor(path):
    """Return one exact B4/B6 predecessor after authenticating its E3 successor.

    This primitive is independent of B4/B6. It accepts only the four reviewed
    source paths, validates each path's own A2 authorization link, checks the
    exact current tracked source and latest A2 row, and returns evidence-only
    predecessor bytes. Callers cannot supply a digest, fixture path, generation,
    or bypass flag.
    """
    require(type(path) is str and set(SOURCE_FORWARD_TRANSITIONS) == SOURCE_FORWARD_ALLOWED_PATHS
            and path in SOURCE_FORWARD_ALLOWED_PATHS,
            "unreviewed A2 source-forward path: " + repr(path))
    transition = SOURCE_FORWARD_TRANSITIONS[path]
    require(type(transition) is dict and set(transition) == {
        "predecessor_fixture", "predecessor_byte_size", "predecessor_git_blob_sha1",
        "predecessor_lf_source_sha256", "successor_git_blob_sha1", "successor_lf_source_sha256",
        "a2_predecessor_generation", "a2_predecessor_sha256", "a2_generation",
        "a2_authorization_sha256", "reason_type", "reason",
    }, "A2 source-forward declaration shape drift")
    require(transition["reason_type"] == "E3_RUN_02A_DURABLE_CANCELLATION_OPERATION_AUTHORIZATION"
            and type(transition["reason"]) is str and transition["reason"],
            "A2 source-forward declaration is not a reviewed E3 transition")
    generation_bindings = {
        "domain/sportybet_live_event_quote_evidence.py": (
            SOURCE_FORWARD_PREDECESSOR_GENERATION, SOURCE_FORWARD_PREDECESSOR_SHA256,
            SOURCE_FORWARD_AUTHORIZATION_GENERATION, SOURCE_FORWARD_AUTHORIZATION_SHA256,
        ),
        "domain/current_fotmob_latest_durable_fresh_history.py": (
            E3_B6_SOURCE_FORWARD_PREDECESSOR_GENERATION, E3_B6_SOURCE_FORWARD_PREDECESSOR_SHA256,
            E3_B6_SOURCE_FORWARD_AUTHORIZATION_GENERATION, E3_B6_SOURCE_FORWARD_AUTHORIZATION_SHA256,
        ),
        "domain/current_shadow_sportybet_pc_upcoming_discovery.py": (
            E3_B6_SOURCE_FORWARD_PREDECESSOR_GENERATION, E3_B6_SOURCE_FORWARD_PREDECESSOR_SHA256,
            E3_B6_SOURCE_FORWARD_AUTHORIZATION_GENERATION, E3_B6_SOURCE_FORWARD_AUTHORIZATION_SHA256,
        ),
        "scripts/issue_current_fotmob_reviewed_source.py": (
            E3_B6_SOURCE_FORWARD_PREDECESSOR_GENERATION, E3_B6_SOURCE_FORWARD_PREDECESSOR_SHA256,
            E3_B6_SOURCE_FORWARD_AUTHORIZATION_GENERATION, E3_B6_SOURCE_FORWARD_AUTHORIZATION_SHA256,
        ),
    }
    expected_predecessor_generation, expected_predecessor_sha, expected_generation, expected_authorization_sha = \
        generation_bindings[path]
    require(type(transition["predecessor_byte_size"]) is int and transition["predecessor_byte_size"] > 0
            and transition["a2_predecessor_generation"] == expected_predecessor_generation
            and transition["a2_predecessor_sha256"] == expected_predecessor_sha
            and transition["a2_generation"] == expected_generation
            and transition["a2_authorization_sha256"] == expected_authorization_sha,
            "A2 source-forward generation authorization binding drift: " + path)

    current, current_identity = _read_tracked_head_blob_scoped(ROOT, path)
    current_lf = current.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    require(current_identity.git_blob_sha1 == transition["successor_git_blob_sha1"]
            and hashlib.sha256(current_lf).hexdigest() == transition["successor_lf_source_sha256"],
            "A2 source-forward current successor identity mismatch: " + path)
    current_tree_entry = git("ls-tree", "-z", "HEAD", "--", path)
    require(bool(current_tree_entry), "A2 source-forward current successor is not tracked: " + path)
    current_metadata, current_tree_path = current_tree_entry.rstrip(b"\0").split(b"\t", 1)
    current_mode, current_kind, current_blob = current_metadata.decode("ascii").split(" ")
    require(current_tree_path.decode("utf-8") == path and current_mode == "100644"
            and current_kind == "blob" and current_blob == transition["successor_git_blob_sha1"],
            "A2 source-forward current successor tree identity or mode mismatch: " + path)
    worktree_path = ROOT / path
    worktree_lf = worktree_path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    require(hashlib.sha256(worktree_lf).hexdigest() == transition["successor_lf_source_sha256"],
            "A2 source-forward current worktree differs from the approved successor: " + path)

    fixture = validate_repository_relative_path(transition["predecessor_fixture"])
    fixture_raw = _e3_read_exact_head_fixture(
        fixture,
        expected_blob=transition["predecessor_git_blob_sha1"],
        expected_lf=transition["predecessor_lf_source_sha256"],
        expected_size=transition["predecessor_byte_size"],
        label="B4/B6 predecessor fixture",
    )

    scope = _active_a2_derivation_scope()
    scoped_state = None if scope is None else _load_scoped_a2_source_state(scope)
    if scoped_state is not None:
        successor = scoped_state["successors"].get(path)
        require(type(successor) is dict
                and successor.get("git_blob_sha1") == transition["successor_git_blob_sha1"]
                and successor.get("lf_source_sha256") == transition["successor_lf_source_sha256"]
                and scoped_state["by_path"].get(path) == transition["successor_lf_source_sha256"],
                "A2 scoped forward-predecessor successor identity drift: " + path)
        current_raw = _e3_source_forward_file_identity(
            path, fixture=False,
            expected_blob=successor["git_blob_sha1"],
            expected_lf=successor["lf_source_sha256"],
            expected_size=0,
        )
        require(hashlib.sha256(
                    current_raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
                ).hexdigest() == scoped_state["by_path"].get(path),
                "A2 scoped current source differs from authenticated latest row: " + path)
        _authenticate_cross_contract_supporting_sources(scoped_state["by_path"])
        return fixture_raw

    # Reject a changed predecessor or successor before doing the more expensive
    # append-only inventory parse.
    chain = load_inventory_generations()
    predecessor_generation = transition["a2_predecessor_generation"]
    authorization_generation = transition["a2_generation"]
    require(len(chain) > authorization_generation
            and chain[predecessor_generation - 1][0] == inventory_generation_path(predecessor_generation)
            and chain[predecessor_generation - 1][1].get("canonical_sha256")
                == transition["a2_predecessor_sha256"],
            "A2 source-forward transition does not extend its exact authenticated predecessor")
    authorization_path, authorization = chain[authorization_generation - 1]
    require(authorization_path == inventory_generation_path(authorization_generation)
            and authorization.get("generation") == authorization_generation
            and authorization.get("canonical_sha256") == transition["a2_authorization_sha256"]
            and authorization.get("predecessor_inventory") == {
                "path": inventory_generation_path(predecessor_generation),
                "canonical_sha256": transition["a2_predecessor_sha256"],
                "generation": predecessor_generation,
                "rewritten": False,
            }, "A2 source-forward authorization generation identity drift")
    if path in E3_B6_SOURCE_FORWARD_PATHS:
        require(authorization.get("source_forward_authorization")
                == _e3_b6_source_forward_authorization(),
                "A2 source-forward three-source authorization content mismatch")
    latest_path, latest = chain[-1]
    latest_generation = len(chain)
    latest_predecessor = latest.get("predecessor_inventory")
    require(latest_path == inventory_generation_path(latest_generation)
            and latest.get("generation") == latest_generation
            and latest.get("schema_version") == latest_generation
            and latest.get("policy_id") == INVENTORY_POLICY_PREFIX + "_V" + str(latest_generation)
            and type(latest_predecessor) is dict
            and latest_predecessor == {
                "path": inventory_generation_path(latest_generation - 1),
                "canonical_sha256": chain[-2][1]["canonical_sha256"],
                "generation": latest_generation - 1,
                "rewritten": False,
            }, "A2 source-forward transition latest-generation binding drift")

    rows = latest.get("source_identities")
    require(type(rows) is list and all(
        type(row) is dict and type(row.get("path")) is str
        and type(row.get("lf_source_sha256")) is str
        and re.fullmatch(r"[0-9a-f]{64}", row["lf_source_sha256"])
        for row in rows
    ), "A2 source-forward latest inventory rows are malformed")
    row_paths = [row["path"] for row in rows]
    require(row_paths == sorted(row_paths) and len(row_paths) == len(set(row_paths)),
            "A2 source-forward latest inventory rows are not uniquely path ordered")
    by_path = {row["path"]: row["lf_source_sha256"] for row in rows}
    require(by_path.get(path) == transition["successor_lf_source_sha256"],
            "A2 source-forward current successor row differs from authenticated latest inventory")
    require(inventory_document(latest, chain=chain) == latest,
            "A2 source-forward latest inventory is stale against the current corpus")

    a2_path = Path(__file__).resolve().relative_to(ROOT).as_posix()
    a2_source, a2_identity = _read_tracked_head_blob_scoped(ROOT, a2_path)
    a2_lf = a2_source.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    a2_worktree_lf = (ROOT / a2_path).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    a2_digest = hashlib.sha256(a2_lf).hexdigest()
    require(a2_digest == hashlib.sha256(a2_worktree_lf).hexdigest()
            and by_path.get(a2_path) == a2_digest
            and a2_identity.git_blob_sha1,
            "A2 source-forward inventory does not authenticate its current primitive")
    return fixture_raw


def _e3_cross_contract_source_forward_authorization():
    """Exact V284 source transition set; predecessor bytes remain evidence only."""
    sources = []
    for path in sorted(E3_CROSS_CONTRACT_V284_SOURCE_FORWARD_PATHS):
        transition = E3_CROSS_CONTRACT_SOURCE_FORWARD_TRANSITIONS[path]
        sources.append({
            "path": path,
            "predecessor": {
                "fixture_path": transition["predecessor_fixture"],
                "git_blob_sha1": transition["predecessor_git_blob_sha1"],
                "lf_source_sha256": transition["predecessor_lf_source_sha256"],
                "byte_size": transition["predecessor_byte_size"],
            },
            "successor": {
                "git_blob_sha1": transition["successor_git_blob_sha1"],
                "lf_source_sha256": transition["successor_lf_source_sha256"],
            },
            "reason_type": transition["reason_type"],
            "reason": transition["reason"],
        })
    anchors = []
    for path in sorted(E3_CROSS_CONTRACT_SUPPORTING_SOURCE_ANCHORS):
        anchor = E3_CROSS_CONTRACT_SUPPORTING_SOURCE_ANCHORS[path]
        # Reconstruct immutable V284 exactly, including its malformed digest.
        anchor_lf = (
            E3_CROSS_CONTRACT_V284_CAPTURE_ANCHOR_LF_SHA256
            if path == "scripts/capture_fotmob_data_matches.py"
            else anchor["lf_source_sha256"]
        )
        anchors.append({
            "path": path,
            "fixture_path": anchor["fixture_path"],
            "git_blob_sha1": anchor["git_blob_sha1"],
            "lf_source_sha256": anchor_lf,
            "byte_size": anchor["byte_size"],
            "purpose": anchor["purpose"],
        })
    return {
        "schema_version": 1,
        "policy_id": "ATHENA_E3_RUN_02A_CROSS_CONTRACT_SOURCE_FORWARD_V1",
        "scope": "EXACT_ELEVEN_RUN_02A_SOURCE_PATHS_AND_THREE_UNCHANGED_SOURCE_ANCHORS",
        "predecessor_inventory": {
            "path": inventory_generation_path(E3_CROSS_CONTRACT_SOURCE_FORWARD_PREDECESSOR_GENERATION),
            "canonical_sha256": E3_CROSS_CONTRACT_SOURCE_FORWARD_PREDECESSOR_SHA256,
            "generation": E3_CROSS_CONTRACT_SOURCE_FORWARD_PREDECESSOR_GENERATION,
            "rewritten": False,
        },
        "source_identities": sources,
        "unchanged_source_anchors": anchors,
    }


def _e3_pass_a_source_predecessor_authorization():
    """Exact V300 Pass-A source predecessors; history grants no runtime authority."""
    sources = []
    for path in sorted(E3_PASS_A_SOURCE_FORWARD_PATHS):
        transition = resolve_historical_source_transition(
            path,
            expected_generation=E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
        )
        sources.append({
            "path": path,
            "original_source_base_main_sha": E3_PASS_A_SOURCE_FORWARD_BASE_MAIN_SHA,
            "predecessor": {
                "fixture_path": transition["predecessor_fixture"],
                "git_mode": transition["predecessor_git_mode"],
                "git_blob_sha1": transition["predecessor_git_blob_sha1"],
                "lf_source_sha256": transition["predecessor_lf_source_sha256"],
                "byte_size": transition["predecessor_byte_size"],
            },
            "successor": {
                "git_mode": transition["successor_git_mode"],
                "git_blob_sha1": transition["successor_git_blob_sha1"],
                "lf_source_sha256": transition["successor_lf_source_sha256"],
            },
            "reason": "E3 compatibility preserves the frozen Pass-A source projection while the current source remains A2-authenticated",
        })
    return {
        "schema_version": 1,
        "policy_id": "ATHENA_E3_RUN_02A_PASS_A_SOURCE_PREDECESSOR_V1",
        "scope": "EXACT_EIGHT_A2_V2_SOURCE_PREDECESSORS",
        "authorization_generation": E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
        "authorization_predecessor": {
            "path": inventory_generation_path(
                E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_PREDECESSOR_GENERATION
            ),
            "canonical_sha256": E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_PREDECESSOR_SHA256,
            "generation": E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_PREDECESSOR_GENERATION,
            "rewritten": False,
        },
        "source_predecessor_inventory": {
            "path": inventory_generation_path(E3_PASS_A_SOURCE_FORWARD_PREDECESSOR_GENERATION),
            "canonical_sha256": E3_PASS_A_SOURCE_FORWARD_PREDECESSOR_SHA256,
            "generation": E3_PASS_A_SOURCE_FORWARD_PREDECESSOR_GENERATION,
            "rewritten": False,
        },
        "source_identities": sources,
        "authority_granted": False,
        "historical_bytes_changed": False,
    }


def _e3_cross_contract_supporting_source_anchor_correction():
    """Exact V288 correction for the single malformed V284 anchor digest."""
    anchor = E3_CROSS_CONTRACT_SUPPORTING_SOURCE_CORRECTIONS[
        "scripts/capture_fotmob_data_matches.py"
    ]
    return {
        "schema_version": 1,
        "policy_id": "ATHENA_E3_RUN_02A_CROSS_CONTRACT_SOURCE_ANCHOR_CORRECTION_V1",
        "scope": "EXACT_ONE_UNCHANGED_CAPTURE_SOURCE_ANCHOR",
        "supersedes": {
            "path": inventory_generation_path(E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION),
            "canonical_sha256": E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_SHA256,
            "generation": E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
            "rewritten": False,
        },
        "anchor": {
            "path": "scripts/capture_fotmob_data_matches.py",
            "fixture_path": anchor["fixture_path"],
            "git_blob_sha1": anchor["git_blob_sha1"],
            "byte_size": anchor["byte_size"],
            "superseded_lf_source_sha256": anchor["superseded_lf_source_sha256"],
            "lf_source_sha256": anchor["lf_source_sha256"],
            "purpose": anchor["purpose"],
        },
        "authority_granted": False,
        "historical_bytes_changed": False,
    }


def _e3_path_stat(relative_path, *, label):
    """Reject links, reparse points, non-files, and hardlinks in pinned paths."""
    relative = validate_repository_relative_path(relative_path)
    import stat
    cursor = ROOT
    final = None
    try:
        for index, part in enumerate(PurePosixPath(relative).parts):
            cursor = cursor / part
            current = cursor.lstat()
            is_junction = getattr(cursor, "is_junction", lambda: False)()
            reparse = bool(getattr(current, "st_file_attributes", 0)
                           & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
            require(not stat.S_ISLNK(current.st_mode) and not is_junction and not reparse,
                    "E3 source-forward " + label + " contains a symlink or junction: " + relative)
            if index < len(PurePosixPath(relative).parts) - 1:
                require(stat.S_ISDIR(current.st_mode),
                        "E3 source-forward " + label + " parent is not a directory: " + relative)
            else:
                final = current
    except (OSError, ValueError, SourceIdentityError) as error:
        raise AssertionError("E3 source-forward " + label + " is unavailable: " + relative) from error
    require(final is not None and stat.S_ISREG(final.st_mode),
            "E3 source-forward " + label + " is not a regular file: " + relative)
    require(final.st_nlink == 1,
            "E3 source-forward " + label + " is hardlinked: " + relative)
    return ROOT / relative


def _e3_read_exact_head_fixture(
    relative_path, *, expected_blob, expected_lf, expected_size, expected_mode="100644",
    label="predecessor fixture",
):
    """Read a pinned fixture from HEAD and separately prove its checkout text.

    Git filters may materialize CRLF on Windows. Historical identity always
    comes from the tracked HEAD blob; the worktree is accepted only when its
    reviewed LF-normalized text is byte-identical to that blob.
    """
    relative = validate_repository_relative_path(relative_path)
    require(type(expected_blob) is str and re.fullmatch(r"[0-9a-f]{40}", expected_blob) is not None
            and type(expected_lf) is str and re.fullmatch(r"[0-9a-f]{64}", expected_lf) is not None
            and type(expected_size) is int and 1 <= expected_size <= 2_000_000
            and expected_mode == "100644",
            "E3 source-forward " + label + " declaration is malformed: " + relative)
    candidate = _e3_path_stat(relative, label=label)
    try:
        entry = git("ls-tree", "-z", "HEAD", "--", relative)
    except subprocess.SubprocessError as error:
        raise AssertionError("E3 source-forward " + label + " HEAD tree is unavailable: " + relative) from error
    require(bool(entry), "E3 source-forward " + label + " is not tracked at HEAD: " + relative)
    try:
        metadata, tree_path = entry.rstrip(b"\0").split(b"\t", 1)
        mode, kind, blob = metadata.decode("ascii").split(" ")
    except (UnicodeDecodeError, ValueError) as error:
        raise AssertionError("E3 source-forward " + label + " HEAD tree entry is malformed: " + relative) from error
    require(tree_path.decode("utf-8") == relative and mode == expected_mode
            and kind == "blob" and blob == expected_blob,
            "E3 source-forward " + label + " HEAD mode/path/blob mismatch: " + relative)
    try:
        object_size_raw = git("cat-file", "-s", blob).decode("ascii").strip()
    except (subprocess.SubprocessError, UnicodeDecodeError) as error:
        raise AssertionError("E3 source-forward " + label + " HEAD blob is unavailable: " + relative) from error
    require(object_size_raw.isdecimal() and int(object_size_raw) == expected_size,
            "E3 source-forward " + label + " HEAD object size mismatch: " + relative)
    try:
        raw, identity = _read_tracked_head_blob_scoped(
            ROOT, relative, verify_worktree_filtered_identity=False,
        )
    except SourceIdentityError as error:
        raise AssertionError("E3 source-forward " + label + " HEAD object is unavailable: " + relative) from error
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    require(len(raw) == expected_size and identity.git_blob_sha1 == expected_blob
            and hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
                == expected_blob
            and hashlib.sha256(normalized).hexdigest() == expected_lf,
            "E3 source-forward " + label + " exact HEAD identity mismatch: " + relative)
    try:
        raw.decode("utf-8", errors="strict")
        worktree_limit = len(raw) + raw.count(b"\n")
        with candidate.open("rb") as handle:
            worktree_raw = handle.read(worktree_limit + 1)
    except (UnicodeDecodeError, OSError) as error:
        raise AssertionError("E3 source-forward " + label + " checkout is unreadable: " + relative) from error
    worktree_normalized = worktree_raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    require(len(worktree_raw) <= worktree_limit
            and worktree_normalized == normalized,
            "E3 source-forward " + label + " checkout differs from exact HEAD text: " + relative)
    return raw


def _e3_directory_path(relative_path, *, label):
    relative = validate_repository_relative_path(relative_path)
    import stat
    cursor = ROOT
    try:
        for part in PurePosixPath(relative).parts:
            cursor = cursor / part
            current = cursor.lstat()
            is_junction = getattr(cursor, "is_junction", lambda: False)()
            reparse = bool(getattr(current, "st_file_attributes", 0)
                           & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
            require(not stat.S_ISLNK(current.st_mode) and not is_junction and not reparse
                    and stat.S_ISDIR(current.st_mode),
                    "E3 source-forward " + label + " contains a link or non-directory: " + relative)
    except (OSError, ValueError, SourceIdentityError) as error:
        raise AssertionError("E3 source-forward " + label + " is unavailable: " + relative) from error
    return cursor


def _e3_source_forward_file_identity(
    path, *, fixture, expected_blob, expected_lf, expected_size, expected_mode="100644",
):
    relative = validate_repository_relative_path(path)
    if fixture:
        return _e3_read_exact_head_fixture(
            relative, expected_blob=expected_blob, expected_lf=expected_lf,
            expected_size=expected_size, expected_mode=expected_mode,
            label="Pass-A predecessor fixture",
        )
    candidate = _e3_path_stat(relative, label="current source")
    raw, identity = _read_tracked_head_blob_scoped(ROOT, relative)
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if (relative == E3_PASS_A_V313_SUCCESSOR_EXTENSION_PATH
            and expected_blob == E3_PASS_A_V313_SUCCESSOR_EXTENSION_IDENTITY[0]
            and expected_lf == E3_PASS_A_V313_SUCCESSOR_EXTENSION_IDENTITY[1]
            and identity.git_blob_sha1 != expected_blob):
        from scripts import audit_phase_a_pc_upcoming_retention_successor as retention
        predecessor, retained = retention.checkpoint_v2_retention_sources()
        fixed = RETENTION_MAIN347_CHECKPOINT_EXTENSION["successor"]
        retained_identity = retention.identity(retained)
        require(retained_identity["git_blob_sha1"] == fixed["git_blob_sha1"]
                and retained_identity["source_sha256"] == fixed["lf_source_sha256"],
                "retention V348 delegated source identity drift")
        if (identity.git_blob_sha1 == fixed["git_blob_sha1"]
                and hashlib.sha256(normalized).hexdigest() == fixed["lf_source_sha256"]
                and retained == normalized):
            current_source = raw
        else:
            current_source = retention.checkpoint_v2_current_source()
            current_identity = retention.identity(current_source)
            require(raw == current_source
                    and identity.git_blob_sha1 == current_identity["git_blob_sha1"]
                    and hashlib.sha256(normalized).hexdigest()
                        == current_identity["source_sha256"],
                    "retention current successor identity drift")
        # V313 authenticates its original exact bytes; V348 separately binds
        # the only current replacement. Never substitute a new historic pin.
        require(expected_mode == "100644" and retention.identity(predecessor)["git_blob_sha1"] == expected_blob
                and hashlib.sha256(predecessor).hexdigest() == expected_lf,
                "retention V313 predecessor identity drift")
        return predecessor
    require(identity.git_blob_sha1 == expected_blob
            and hashlib.sha256(normalized).hexdigest() == expected_lf,
            "E3 source-forward current successor identity mismatch: " + relative)
    worktree_raw = candidate.read_bytes()
    worktree_normalized = worktree_raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    require(worktree_normalized == normalized,
            "E3 source-forward worktree bytes differ from tracked identity: " + relative)
    entry = git("ls-tree", "-z", "HEAD", "--", relative)
    require(bool(entry), "E3 source-forward path is not committed at HEAD: " + relative)
    metadata, tree_path = entry.rstrip(b"\0").split(b"\t", 1)
    mode, kind, blob = metadata.decode("ascii").split(" ")
    require(tree_path.decode("utf-8") == relative and mode == expected_mode and kind == "blob"
            and blob == identity.git_blob_sha1,
            "E3 source-forward tracked path mode or Git blob mismatch: " + relative)
    return raw


def _e3_require_frozen_v378_source_edge_preserved(chain, path, expected_history):
    """Prove the complete authenticated V378 checkpoint history is preserved.

    V378 is the immutable source-forward edge for the Checkpoint V2 auditor.
    Later A2 generations may advance the inventory, but each one must retain
    the complete checkpoint-path edge history recorded at V378, its latest
    source identity, and the immediately preceding canonical generation.
    """
    generation = RCV_RECOVERY_V378_CHECKPOINT_V2_GENERATION
    require(type(chain) is list and len(chain) >= generation
            and type(path) is str and type(expected_history) is list,
            "retention V378 checkpoint history is missing or malformed")
    frozen_edges = [row for row in expected_history
                    if type(row) is dict and row.get("path") == path
                    and row.get("generation") == generation]
    require(len(frozen_edges) == 1
            and all(type(row) is dict and row.get("path") == path
                    for row in expected_history),
            "retention V378 checkpoint history has an invalid edge set")
    frozen_edge = frozen_edges[0]

    v377_path, v377_inventory = chain[generation - 2]
    v378_path, v378_inventory = chain[generation - 1]
    expected_v378_predecessor = {
        "path": v377_path,
        "canonical_sha256": v377_inventory.get("canonical_sha256"),
        "generation": generation - 1,
        "rewritten": False,
    }
    frozen_successor = frozen_edge.get("successor")
    require(type(frozen_successor) is dict,
            "retention V378 frozen successor identity is malformed")
    frozen_digest = frozen_successor.get("lf_source_sha256")
    require(v377_path == inventory_generation_path(generation - 1)
            and v377_inventory.get("generation") == generation - 1
            and v378_path == inventory_generation_path(generation)
            and v378_inventory.get("generation") == generation
            and v378_inventory.get("schema_version") == generation
            and frozen_edge.get("predecessor_inventory") == expected_v378_predecessor
            and v378_inventory.get("predecessor_inventory") == expected_v378_predecessor
            and type(frozen_digest) is str
            and re.fullmatch(r"[0-9a-f]{64}", frozen_digest) is not None,
            "retention V378 source edge does not bind the exact V377 predecessor")

    v378_history = [row for row in v378_inventory.get(
        "e3_cross_contract_source_forward_successor_extensions", [])
        if type(row) is dict and row.get("path") == path]
    v378_rows = [row for row in v378_inventory.get("source_identities", [])
                 if type(row) is dict and row.get("path") == path]
    require(v378_history == expected_history and len(v378_rows) == 1
            and v378_rows[0].get("lf_source_sha256") == frozen_digest,
            "retention V378 inventory does not authenticate its complete checkpoint edge history")

    previous_path = v378_path
    previous = v378_inventory
    for current_generation in range(generation + 1, len(chain) + 1):
        current_path, current = chain[current_generation - 1]
        expected_predecessor = {
            "path": previous_path,
            "canonical_sha256": previous.get("canonical_sha256"),
            "generation": current_generation - 1,
            "rewritten": False,
        }
        checkpoint_history = [row for row in current.get(
            "e3_cross_contract_source_forward_successor_extensions", [])
            if type(row) is dict and row.get("path") == path]
        source_rows = [row for row in current.get("source_identities", [])
                       if type(row) is dict and row.get("path") == path]
        require(current_path == inventory_generation_path(current_generation)
                and current.get("generation") == current_generation
                and current.get("schema_version") == current_generation
                and current.get("predecessor_inventory") == expected_predecessor
                and checkpoint_history == expected_history
                and len(source_rows) == 1
                and source_rows[0].get("lf_source_sha256") == frozen_digest,
                "retention A2 successor does not preserve the complete frozen V378 checkpoint history")
        previous_path, previous = current_path, current

    return frozen_edge["successor"]


def _authenticated_e3_successor_identity(path, chain, latest):
    latest_generation = len(chain)
    expected_extensions = _e3_cross_contract_source_forward_successor_extensions(
        chain=chain, generation=latest_generation,
    )
    require(latest.get("e3_cross_contract_source_forward_successor_extensions")
            == expected_extensions,
            "E3 source-forward successor extension is missing or altered")
    matches = [row for row in expected_extensions if row["path"] == path]
    if not matches:
        transition = resolve_historical_source_transition(
            path,
            expected_generation=E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
        )
        return {
            "git_blob_sha1": transition["successor_git_blob_sha1"],
            "lf_source_sha256": transition["successor_lf_source_sha256"],
        }
    if path == "scripts/audit_core_01d_port02c_trigger_authority_b6.py":
        require(len(matches) == 1 and matches[0].get("generation") == 377
                and latest_generation >= 377,
                "E3 B6 source-forward extension has an unsupported suffix")
        v377_path, v377_inventory = chain[376]
        v377_extensions = _e3_cross_contract_source_forward_successor_extensions(
            chain=chain, generation=377,
        )
        v377_rows = {row["path"]: row["lf_source_sha256"]
                     for row in v377_inventory.get("source_identities", [])
                     if type(row) is dict and type(row.get("path")) is str}
        require(v377_path == inventory_generation_path(377)
                and v377_inventory.get("generation") == 377
                and v377_inventory.get("schema_version") == 377
                and v377_inventory.get("predecessor_inventory")
                    == matches[0]["predecessor_inventory"]
                and v377_inventory.get("e3_cross_contract_source_forward_successor_extensions")
                    == v377_extensions
                and matches[0] == _e3_port02c_b6_v377_source_extension(chain, latest_generation)
                and v377_rows.get(path) == matches[0]["successor"]["lf_source_sha256"],
                "E3 B6 V377 successor does not append to exact V376")
        return matches[0]["successor"]
    v298 = next((row for row in matches
                 if row["generation"] == E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_GENERATION), None)
    require(v298 is not None,
            "E3 source-forward V298 successor extension is missing")
    generation = E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_GENERATION
    v298_extensions = _e3_cross_contract_source_forward_successor_extensions(
        chain=chain, generation=generation,
    )
    require(len(chain) >= generation
            and chain[generation - 1][0] == inventory_generation_path(generation),
            "E3 source-forward extension generation is missing")
    predecessor_path, predecessor = chain[generation - 2]
    extension_path, extension_inventory = chain[generation - 1]
    require(predecessor_path == inventory_generation_path(generation - 1)
            and predecessor.get("canonical_sha256")
                == E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_PREDECESSOR_SHA256
            and extension_path == inventory_generation_path(generation)
            and extension_inventory.get("generation") == generation
            and extension_inventory.get("schema_version") == generation
            and extension_inventory.get("predecessor_inventory")
                == v298["predecessor_inventory"]
            and extension_inventory.get("e3_cross_contract_source_forward_successor_extensions")
                == v298_extensions,
            "E3 source-forward extension does not append to its exact predecessor")
    original = resolve_historical_source_transition(
        path,
        expected_generation=E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
    )
    require(v298["previous_successor"] == {
                "generation": E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
                "canonical_sha256": E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_SHA256,
                "git_blob_sha1": original["successor_git_blob_sha1"],
                "lf_source_sha256": original["successor_lf_source_sha256"],
                "rewritten": False,
            }, "E3 source-forward extension rewrites the immutable V284 successor")
    extension_rows = {row["path"]: row["lf_source_sha256"]
                      for row in extension_inventory.get("source_identities", [])
                      if type(row) is dict}
    require(extension_rows.get(path) == v298["successor"]["lf_source_sha256"],
            "E3 source-forward extension successor is absent from its generation")
    if len(matches) == 1:
        return v298["successor"]

    require(path == E3_PASS_A_COMPAT_SUCCESSOR_EXTENSION_PATH
            and len(matches) in {3, 4, 5, 6, 7, 8}
            and latest_generation >= E3_PASS_A_COMPAT_SUCCESSOR_EXTENSION_GENERATION,
            "E3 source-forward path has an unsupported extension chain")
    v301 = next((row for row in matches
                 if row["generation"] == E3_PASS_A_COMPAT_SUCCESSOR_EXTENSION_GENERATION), None)
    require(v301 is not None,
            "E3 source-forward V301 D5 successor extension is missing")
    generation = E3_PASS_A_COMPAT_SUCCESSOR_EXTENSION_GENERATION
    v301_extensions = _e3_cross_contract_source_forward_successor_extensions(
        chain=chain, generation=generation,
    )
    v300_index = E3_PASS_A_COMPAT_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION - 1
    v300_path, v300 = chain[v300_index]
    extension_path, extension_inventory = chain[generation - 1]
    require(v300_path == inventory_generation_path(E3_PASS_A_COMPAT_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION)
            and v300.get("canonical_sha256")
                == v301["predecessor_inventory"]["canonical_sha256"]
            and v300.get("e3_pass_a_source_predecessor_authorization")
                == _e3_pass_a_source_predecessor_authorization()
            and extension_path == inventory_generation_path(generation)
            and extension_inventory.get("generation") == generation
            and extension_inventory.get("schema_version") == generation
            and extension_inventory.get("predecessor_inventory")
                == v301["predecessor_inventory"]
            and extension_inventory.get("e3_cross_contract_source_forward_successor_extensions")
                == v301_extensions,
            "E3 source-forward V301 extension does not append to authenticated V300")
    require(v301["previous_successor"] == {
                "generation": E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_GENERATION,
                "canonical_sha256": E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_CANONICAL_SHA256,
                "git_blob_sha1": E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_IDENTITY[0],
                "lf_source_sha256": E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_IDENTITY[1],
                "rewritten": False,
            }
            and v301["successor"] == {
                "git_blob_sha1": E3_PASS_A_COMPAT_SUCCESSOR_EXTENSION_IDENTITY[0],
                "lf_source_sha256": E3_PASS_A_COMPAT_SUCCESSOR_EXTENSION_IDENTITY[1],
                "git_mode": "100644",
            }, "E3 source-forward V301 successor identity drift")
    v301_rows = {row["path"]: row["lf_source_sha256"]
                 for row in extension_inventory.get("source_identities", [])
                 if type(row) is dict}
    require(v301_rows.get(path) == v301["successor"]["lf_source_sha256"],
            "E3 source-forward V301 successor is absent from its generation")
    v309 = next((row for row in matches
                 if row["generation"] == E3_PASS_A_V309_SUCCESSOR_EXTENSION_GENERATION), None)
    require(v309 is not None
            and latest_generation >= E3_PASS_A_V309_SUCCESSOR_EXTENSION_GENERATION,
            "E3 source-forward V309 extension is missing or outside its exact generation")
    v308_path, v308 = chain[E3_PASS_A_V309_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION - 1]
    v309_path, v309_inventory = chain[E3_PASS_A_V309_SUCCESSOR_EXTENSION_GENERATION - 1]
    v309_extensions = _e3_cross_contract_source_forward_successor_extensions(
        chain=chain, generation=E3_PASS_A_V309_SUCCESSOR_EXTENSION_GENERATION,
    )
    require(v308_path == inventory_generation_path(
                E3_PASS_A_V309_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION)
            and v308.get("canonical_sha256")
                == E3_PASS_A_V309_SUCCESSOR_EXTENSION_PREDECESSOR_SHA256
            and v309_path == inventory_generation_path(
                E3_PASS_A_V309_SUCCESSOR_EXTENSION_GENERATION)
            and v309_inventory.get("generation")
                == E3_PASS_A_V309_SUCCESSOR_EXTENSION_GENERATION
            and v309_inventory.get("schema_version")
                == E3_PASS_A_V309_SUCCESSOR_EXTENSION_GENERATION
            and v309_inventory.get("predecessor_inventory")
                == v309["predecessor_inventory"]
            and v309_inventory.get("e3_cross_contract_source_forward_successor_extensions")
                == v309_extensions,
            "E3 source-forward V309 extension does not append to exact V308")
    require(v309["previous_successor"] == {
                "generation": E3_PASS_A_V309_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION,
                "canonical_sha256": E3_PASS_A_V309_SUCCESSOR_EXTENSION_PREDECESSOR_SHA256,
                "git_blob_sha1": E3_PASS_A_V309_SUCCESSOR_EXTENSION_PREDECESSOR["git_blob_sha1"],
                "lf_source_sha256": E3_PASS_A_V309_SUCCESSOR_EXTENSION_PREDECESSOR["lf_source_sha256"],
                "rewritten": False,
            }
            and v309["successor"] == {
                "git_blob_sha1": E3_PASS_A_V309_SUCCESSOR_EXTENSION_IDENTITY[0],
                "lf_source_sha256": E3_PASS_A_V309_SUCCESSOR_EXTENSION_IDENTITY[1],
                "git_mode": "100644",
            }, "E3 source-forward V309 successor identity drift")
    _authenticate_e3_v309_predecessor_fixture(v309)
    v309_rows = {row["path"]: row["lf_source_sha256"]
                 for row in v309_inventory.get("source_identities", [])
                 if type(row) is dict}
    require(v309_rows.get(path) == v309["successor"]["lf_source_sha256"],
            "E3 source-forward V309 successor is absent from its generation")
    if len(matches) == 3:
        return v309["successor"]

    require(path == E3_PASS_A_V312_SUCCESSOR_EXTENSION_PATH
            and latest_generation >= E3_PASS_A_V312_SUCCESSOR_EXTENSION_GENERATION,
            "E3 source-forward V312 extension is missing or outside its exact generation")
    v312 = next((row for row in matches
                 if row["generation"] == E3_PASS_A_V312_SUCCESSOR_EXTENSION_GENERATION), None)
    v311_path, v311 = chain[E3_PASS_A_V312_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION - 1]
    v312_path, v312_inventory = chain[E3_PASS_A_V312_SUCCESSOR_EXTENSION_GENERATION - 1]
    v312_extensions = _e3_cross_contract_source_forward_successor_extensions(
        chain=chain, generation=E3_PASS_A_V312_SUCCESSOR_EXTENSION_GENERATION,
    )
    require(v312 is not None
            and v311_path == inventory_generation_path(
                E3_PASS_A_V312_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION)
            and v311.get("canonical_sha256")
                == E3_PASS_A_V312_SUCCESSOR_EXTENSION_PREDECESSOR_SHA256
            and v312_path == inventory_generation_path(
                E3_PASS_A_V312_SUCCESSOR_EXTENSION_GENERATION)
            and v312_inventory.get("generation")
                == E3_PASS_A_V312_SUCCESSOR_EXTENSION_GENERATION
            and v312_inventory.get("schema_version")
                == E3_PASS_A_V312_SUCCESSOR_EXTENSION_GENERATION
            and v312_inventory.get("predecessor_inventory")
                == v312["predecessor_inventory"]
            and v312_inventory.get("e3_cross_contract_source_forward_successor_extensions")
                == v312_extensions,
            "E3 source-forward V312 extension does not append to exact V311")
    predecessor = E3_PASS_A_V312_SUCCESSOR_EXTENSION_PREDECESSOR
    successor = E3_PASS_A_V312_SUCCESSOR_EXTENSION_IDENTITY
    require(v312["predecessor_inventory"] == {
                "path": inventory_generation_path(
                    E3_PASS_A_V312_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION),
                "canonical_sha256": E3_PASS_A_V312_SUCCESSOR_EXTENSION_PREDECESSOR_SHA256,
                "generation": E3_PASS_A_V312_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION,
                "rewritten": False,
            }
            and v312["previous_successor"] == {
                "generation": E3_PASS_A_V312_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION,
                "canonical_sha256": E3_PASS_A_V312_SUCCESSOR_EXTENSION_PREDECESSOR_SHA256,
                "git_blob_sha1": predecessor["git_blob_sha1"],
                "lf_source_sha256": predecessor["lf_source_sha256"],
                "rewritten": False,
            }
            and v312["successor"] == {
                "git_blob_sha1": successor[0],
                "lf_source_sha256": successor[1],
                "git_mode": "100644",
            }
            and v312.get("authority_granted") is False
            and v312.get("historical_bytes_changed") is False
            and v312.get("rewritten") is False,
            "E3 source-forward V312 predecessor/successor identity drift")
    _e3_pass_a_v312_source_successor_extension(chain)
    v312_rows = {row["path"]: row["lf_source_sha256"]
                 for row in v312_inventory.get("source_identities", [])
                 if type(row) is dict}
    require(v312_rows.get(path) == successor[1],
            "E3 source-forward V312 successor is absent from its generation")
    if len(matches) == 4:
        return v312["successor"]

    require(path == E3_PASS_A_V313_SUCCESSOR_EXTENSION_PATH
            and latest_generation >= E3_PASS_A_V313_SUCCESSOR_EXTENSION_GENERATION,
            "E3 source-forward V313 extension is missing or outside its exact generation")
    v313 = next((row for row in matches
                 if row["generation"] == E3_PASS_A_V313_SUCCESSOR_EXTENSION_GENERATION), None)
    v312_predecessor_path, v312_predecessor = chain[
        E3_PASS_A_V313_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION - 1
    ]
    v313_path, v313_inventory = chain[
        E3_PASS_A_V313_SUCCESSOR_EXTENSION_GENERATION - 1
    ]
    v313_extensions = _e3_cross_contract_source_forward_successor_extensions(
        chain=chain, generation=E3_PASS_A_V313_SUCCESSOR_EXTENSION_GENERATION,
    )
    require(v313 is not None
            and v312_predecessor_path == inventory_generation_path(
                E3_PASS_A_V313_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION)
            and v312_predecessor.get("canonical_sha256")
                == E3_PASS_A_V313_SUCCESSOR_EXTENSION_PREDECESSOR_SHA256
            and v313_path == inventory_generation_path(
                E3_PASS_A_V313_SUCCESSOR_EXTENSION_GENERATION)
            and v313_inventory.get("generation")
                == E3_PASS_A_V313_SUCCESSOR_EXTENSION_GENERATION
            and v313_inventory.get("schema_version")
                == E3_PASS_A_V313_SUCCESSOR_EXTENSION_GENERATION
            and v313_inventory.get("predecessor_inventory")
                == v313["predecessor_inventory"]
            and v313_inventory.get("e3_cross_contract_source_forward_successor_extensions")
                == v313_extensions,
            "E3 source-forward V313 extension does not append to exact V312")
    predecessor = E3_PASS_A_V313_SUCCESSOR_EXTENSION_PREDECESSOR
    current_successor = E3_PASS_A_V313_SUCCESSOR_EXTENSION_IDENTITY
    require(v313["predecessor_inventory"] == {
                "path": inventory_generation_path(
                    E3_PASS_A_V313_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION),
                "canonical_sha256": E3_PASS_A_V313_SUCCESSOR_EXTENSION_PREDECESSOR_SHA256,
                "generation": E3_PASS_A_V313_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION,
                "rewritten": False,
            }
            and v313["previous_successor"] == {
                "generation": E3_PASS_A_V313_SUCCESSOR_EXTENSION_PREDECESSOR_GENERATION,
                "canonical_sha256": E3_PASS_A_V313_SUCCESSOR_EXTENSION_PREDECESSOR_SHA256,
                "git_blob_sha1": predecessor["git_blob_sha1"],
                "lf_source_sha256": predecessor["lf_source_sha256"],
                "rewritten": False,
            }
            and v313["successor"] == {
                "git_blob_sha1": current_successor[0],
                "lf_source_sha256": current_successor[1],
                "git_mode": "100644",
            }
            and v313.get("authority_granted") is False
            and v313.get("historical_bytes_changed") is False
            and v313.get("rewritten") is False,
            "E3 source-forward V313 predecessor/successor identity drift")
    _e3_pass_a_v313_source_successor_extension(chain)
    v313_rows = {row["path"]: row["lf_source_sha256"]
                 for row in v313_inventory.get("source_identities", [])
                 if type(row) is dict}
    require(v313_rows.get(path) == current_successor[1],
            "E3 source-forward V313 successor is absent from its generation")
    if len(matches) == 5:
        return v313["successor"]
    from scripts import audit_phase_a_pc_upcoming_retention_successor as retention
    require(len(matches) in {6, 7, 8} and latest_generation >= 348,
            "retention checkpoint has an unreviewed source-forward suffix")
    extension = retention.checkpoint_retention_extension(chain)
    v348 = next((row for row in matches if row.get("generation") == 348), None)
    stored = [row for row in latest.get("e3_cross_contract_source_forward_successor_extensions", [])
              if type(row) is dict and row.get("path") == path and row.get("generation") == 348]
    require(v348 is not None
            and canonical(v348) == canonical(extension)
            and canonical(extension) == canonical(RETENTION_MAIN347_CHECKPOINT_EXTENSION)
            and len(stored) == 1 and canonical(stored[0]) == canonical(RETENTION_MAIN347_CHECKPOINT_EXTENSION),
            "E3 source-forward successor extension is missing or altered")
    require(chain[347][0] == inventory_generation_path(348)
            and chain[347][1].get("predecessor_inventory") == extension["predecessor_inventory"]
            and chain[347][1].get("e3_cross_contract_source_forward_successor_extensions")
                == _e3_cross_contract_source_forward_successor_extensions(chain=chain, generation=348),
            "retention V348 does not append the exact source-forward contract")
    bound_rows = {row["path"]: row["lf_source_sha256"] for row in chain[347][1]["source_identities"]}
    require(bound_rows.get(path) == extension["successor"]["lf_source_sha256"],
            "retention V348 checkpoint source is not bound by its inventory")
    if len(matches) == 6:
        return extension["successor"]

    v377 = _e3_checkpoint_v2_v377_source_extension(chain, 377)
    v377_path, v377_inventory = chain[376]
    v377_extensions = _e3_cross_contract_source_forward_successor_extensions(
        chain=chain, generation=377,
    )
    v377_rows = {row["path"]: row["lf_source_sha256"]
                 for row in v377_inventory.get("source_identities", [])
                 if type(row) is dict and type(row.get("path")) is str}
    expected_path_generations = [
        E3_CROSS_CONTRACT_SUCCESSOR_EXTENSION_GENERATION,
        E3_PASS_A_COMPAT_SUCCESSOR_EXTENSION_GENERATION,
        E3_PASS_A_V309_SUCCESSOR_EXTENSION_GENERATION,
        E3_PASS_A_V312_SUCCESSOR_EXTENSION_GENERATION,
        E3_PASS_A_V313_SUCCESSOR_EXTENSION_GENERATION,
        348,
        377,
    ]
    require(v377_path == inventory_generation_path(377)
            and v377_inventory.get("generation") == 377
            and v377_inventory.get("schema_version") == 377
            and v377_inventory.get("canonical_sha256") == RCV_RECOVERY_V377_INVENTORY_SHA256
            and v377_inventory.get("predecessor_inventory") == v377["predecessor_inventory"]
            and v377_inventory.get("e3_cross_contract_source_forward_successor_extensions")
                == v377_extensions
            and v377 in matches
            and v377_rows.get(path) == v377["successor"]["lf_source_sha256"],
            "retention V377 checkpoint source does not preserve its frozen V376 edge")

    if latest_generation == 377:
        require([row.get("generation") for row in matches] == expected_path_generations,
                "retention V377 checkpoint source has an unknown extension suffix")
        return v377["successor"]

    require(latest_generation >= RCV_RECOVERY_V378_CHECKPOINT_V2_GENERATION
            and [row.get("generation") for row in matches]
                == expected_path_generations + [RCV_RECOVERY_V378_CHECKPOINT_V2_GENERATION],
            "retention checkpoint source has an unsupported generation suffix")
    latest_path, latest_inventory = chain[-1]
    v378_matches = [row for row in matches
                    if row.get("generation") == RCV_RECOVERY_V378_CHECKPOINT_V2_GENERATION]
    require(latest_path == inventory_generation_path(latest_generation)
            and latest_inventory == latest and len(v378_matches) == 1,
            "retention latest inventory or frozen V378 edge identity drift")
    return _e3_require_frozen_v378_source_edge_preserved(chain, path, matches)


def _authenticated_pass_a_source_inventory_state(chain=None):
    """Authenticate V1-V313 ancestry and the live latest corpus once."""
    chain = load_inventory_generations() if chain is None else chain
    require(type(chain) is list
            and len(chain) >= E3_PASS_A_V313_SUCCESSOR_EXTENSION_GENERATION,
            "E3 Pass-A V300/V301/V309/V312/V313 authorization chain or its complete ancestry is missing")

    v2_path, v2 = chain[E3_PASS_A_SOURCE_FORWARD_PREDECESSOR_GENERATION - 1]
    require(v2_path == inventory_generation_path(E3_PASS_A_SOURCE_FORWARD_PREDECESSOR_GENERATION)
            and v2.get("generation") == E3_PASS_A_SOURCE_FORWARD_PREDECESSOR_GENERATION
            and v2.get("canonical_sha256") == E3_PASS_A_SOURCE_FORWARD_PREDECESSOR_SHA256,
            "E3 Pass-A predecessor does not bind immutable A2 V2")

    v284_path, v284 = chain[E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION - 1]
    require(v284_path == inventory_generation_path(E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION)
            and v284.get("canonical_sha256") == E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_SHA256
            and v284.get("e3_cross_contract_source_forward_authorization")
                == _e3_cross_contract_source_forward_authorization(),
            "E3 Pass-A ancestry does not preserve the exact V284 authorization")

    correction_generation = E3_CROSS_CONTRACT_ANCHOR_CORRECTION_GENERATION
    v288_path, v288 = chain[correction_generation - 1]
    require(v288_path == inventory_generation_path(correction_generation)
            and v288.get("canonical_sha256") == E3_CROSS_CONTRACT_ANCHOR_CORRECTION_SHA256
            and v288.get("e3_cross_contract_supporting_source_anchor_correction")
                == _e3_cross_contract_supporting_source_anchor_correction(),
            "E3 Pass-A ancestry does not preserve the exact V288 correction")

    v299_path, v299 = chain[E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_PREDECESSOR_GENERATION - 1]
    require(v299_path == inventory_generation_path(E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_PREDECESSOR_GENERATION)
            and v299.get("generation") == E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_PREDECESSOR_GENERATION
            and v299.get("canonical_sha256")
                == E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_PREDECESSOR_SHA256,
            "E3 Pass-A V300 does not extend the exact V299 predecessor")

    authorization_generation = E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_GENERATION
    authorization_path, authorization = chain[authorization_generation - 1]
    authorization_parent = authorization.get("predecessor_inventory")
    require(authorization_path == inventory_generation_path(authorization_generation)
            and authorization.get("generation") == authorization_generation
            and authorization.get("schema_version") == authorization_generation
            and authorization.get("policy_id") == INVENTORY_POLICY_PREFIX + "_V" + str(authorization_generation)
            and authorization_parent == {
                "path": inventory_generation_path(E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_PREDECESSOR_GENERATION),
                "canonical_sha256": E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_PREDECESSOR_SHA256,
                "generation": E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_PREDECESSOR_GENERATION,
                "rewritten": False,
            }
            and authorization.get("e3_pass_a_source_predecessor_authorization")
                == _e3_pass_a_source_predecessor_authorization(),
            "E3 Pass-A V300 source authorization identity drift")

    fixture_directory = _e3_directory_path(
        E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY, label="Pass-A predecessor fixture directory",
    )
    actual_fixtures = {
        E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/" + child.name
        for child in fixture_directory.iterdir()
    }
    require(actual_fixtures == (set(E3_PASS_A_SOURCE_FORWARD_FIXTURE_PATHS)
                                | set(E3_PASS_A_SOURCE_FORWARD_EXISTING_FIXTURE_PATHS)),
            "E3 Pass-A V300 fixture directory has missing, extra, or renamed evidence")

    latest_path, latest = chain[-1]
    latest_generation = len(chain)
    latest_predecessor = latest.get("predecessor_inventory")
    require(latest_path == inventory_generation_path(latest_generation)
            and latest.get("generation") == latest_generation
            and latest.get("schema_version") == latest_generation
            and latest.get("policy_id") == INVENTORY_POLICY_PREFIX + "_V" + str(latest_generation)
            and type(latest_predecessor) is dict
            and latest_predecessor == {
                "path": inventory_generation_path(latest_generation - 1),
                "canonical_sha256": chain[-2][1].get("canonical_sha256"),
                "generation": latest_generation - 1,
                "rewritten": False,
            }
            and latest.get("e3_pass_a_source_predecessor_authorization")
                == _e3_pass_a_source_predecessor_authorization()
            and latest.get("e3_cross_contract_source_forward_successor_extensions")
                == _e3_cross_contract_source_forward_successor_extensions(
                    chain=chain, generation=latest_generation,
                ), "E3 Pass-A latest A2 authorization or generation link drift")
    rows = latest.get("source_identities")
    require(type(rows) is list and all(
        type(row) is dict and type(row.get("path")) is str
        and type(row.get("lf_source_sha256")) is str
        and re.fullmatch(r"[0-9a-f]{64}", row["lf_source_sha256"])
        for row in rows
    ), "E3 Pass-A latest A2 source rows are malformed")
    row_paths = [row["path"] for row in rows]
    require(row_paths == sorted(row_paths) and len(row_paths) == len(set(row_paths)),
            "E3 Pass-A latest A2 rows are not uniquely path ordered")
    latest_rows = {row["path"]: row["lf_source_sha256"] for row in rows}

    compat_path = E3_PASS_A_COMPAT_SUCCESSOR_EXTENSION_PATH
    compat_successor = _authenticated_e3_successor_identity(compat_path, chain, latest)
    compat_raw = _e3_source_forward_file_identity(
        compat_path,
        fixture=False,
        expected_blob=compat_successor["git_blob_sha1"],
        expected_lf=compat_successor["lf_source_sha256"],
        expected_size=0,
    )
    require(latest_rows.get(compat_path) == compat_successor["lf_source_sha256"]
            and hashlib.sha256(
                compat_raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            ).hexdigest() == compat_successor["lf_source_sha256"],
            "E3 Pass-A latest D5 compatibility successor is not current")

    a2_path = Path(__file__).resolve().relative_to(ROOT).as_posix()
    _e3_path_stat(a2_path, label="current A2 source")
    a2_source, a2_identity = _read_tracked_head_blob_scoped(ROOT, a2_path)
    a2_lf = a2_source.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    a2_worktree = (ROOT / a2_path).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    a2_tree = git("ls-tree", "-z", "HEAD", "--", a2_path)
    require(bool(a2_tree), "E3 Pass-A current A2 source is not committed")
    a2_metadata, a2_tree_path = a2_tree.rstrip(b"\0").split(b"\t", 1)
    a2_mode, a2_kind, a2_blob = a2_metadata.decode("ascii").split(" ")
    a2_digest = hashlib.sha256(a2_lf).hexdigest()
    require(a2_tree_path.decode("utf-8") == a2_path and a2_mode == "100644"
            and a2_kind == "blob" and a2_blob == a2_identity.git_blob_sha1
            and a2_lf == a2_worktree and latest_rows.get(a2_path) == a2_digest,
            "E3 Pass-A current A2 source differs from authenticated latest A2")
    require(inventory_document(latest, chain=chain) == latest,
            "E3 Pass-A latest inventory is stale against the current source corpus")
    authenticate_historical_v1()
    return chain, latest, latest_rows


def _read_authenticated_pass_a_source_predecessor(path, state):
    if type(state) is dict and state.get("schema") == 3:
        latest_rows = state["by_path"]
        predecessor_rows = state["pass_a_v2_rows"]
    else:
        chain, _latest, latest_rows = state
        predecessor = chain[E3_PASS_A_SOURCE_FORWARD_PREDECESSOR_GENERATION - 1][1]
        predecessor_rows = {row["path"]: row["lf_source_sha256"]
                            for row in predecessor.get("source_identities", [])
                            if type(row) is dict}
    transition = resolve_historical_source_transition(
        path,
        expected_generation=E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
    )
    require(type(transition) is dict and set(transition) == {
        "predecessor_fixture", "predecessor_git_mode", "predecessor_byte_size",
        "predecessor_git_blob_sha1", "predecessor_lf_source_sha256",
        "successor_git_blob_sha1", "successor_lf_source_sha256", "successor_git_mode",
    }, "E3 Pass-A predecessor declaration shape drift: " + path)
    require(transition["predecessor_git_mode"] == "100644"
            and transition["successor_git_mode"] == "100644"
            and type(transition["predecessor_byte_size"]) is int
            and transition["predecessor_byte_size"] > 0,
            "E3 Pass-A predecessor mode or size is malformed: " + path)
    if type(state) is dict and state.get("schema") == 3:
        successor = state["pass_a_successors"].get(path)
        require(type(successor) is dict
                and successor == {
                    "git_blob_sha1": transition["successor_git_blob_sha1"],
                    "lf_source_sha256": transition["successor_lf_source_sha256"],
                }
                and latest_rows.get(path) == successor["lf_source_sha256"],
                "E3 Pass-A scoped successor differs from its V300/latest A2 identity: " + path)

    fixture_path = transition["predecessor_fixture"]
    require(fixture_path in E3_PASS_A_SOURCE_FORWARD_FIXTURE_PATHS,
            "E3 Pass-A fixture is outside its exact V300 fixture allowlist: " + repr(fixture_path))
    fixture_raw = _e3_source_forward_file_identity(
        fixture_path,
        fixture=True,
        expected_blob=transition["predecessor_git_blob_sha1"],
        expected_lf=transition["predecessor_lf_source_sha256"],
        expected_size=transition["predecessor_byte_size"],
        expected_mode=transition["predecessor_git_mode"],
    )
    current_raw = _e3_source_forward_file_identity(
        path,
        fixture=False,
        expected_blob=transition["successor_git_blob_sha1"],
        expected_lf=transition["successor_lf_source_sha256"],
        expected_size=0,
        expected_mode=transition["successor_git_mode"],
    )

    require(predecessor_rows.get(path) == transition["predecessor_lf_source_sha256"],
            "E3 Pass-A predecessor differs from immutable A2 V2 source row: " + path)

    if historical_objects_available(E3_PASS_A_SOURCE_FORWARD_BASE_MAIN_SHA):
        original_tree = git("ls-tree", "-z", E3_PASS_A_SOURCE_FORWARD_BASE_MAIN_SHA, "--", path)
        require(bool(original_tree), "E3 Pass-A original source is absent from pinned base main: " + path)
        metadata, original_path = original_tree.rstrip(b"\0").split(b"\t", 1)
        mode, kind, blob = metadata.decode("ascii").split(" ")
        original_raw = git("cat-file", "blob", blob)
        require(original_path.decode("utf-8") == path
                and mode == transition["predecessor_git_mode"]
                and kind == "blob"
                and blob == transition["predecessor_git_blob_sha1"]
                and original_raw == fixture_raw,
                "E3 Pass-A fixture differs from exact base-main Git object: " + path)

    require(latest_rows.get(path) == transition["successor_lf_source_sha256"]
            and hashlib.sha256(
                current_raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            ).hexdigest() == transition["successor_lf_source_sha256"],
            "E3 Pass-A current successor differs from authenticated latest A2: " + path)
    return fixture_raw


def read_authenticated_pass_a_source_predecessors():
    """Read the exact eight V300 predecessors as inert data in one chain check."""
    require(set(E3_PASS_A_SOURCE_FORWARD_TRANSITIONS) == E3_PASS_A_SOURCE_FORWARD_PATHS
            and len(E3_PASS_A_SOURCE_FORWARD_PATHS) == 8,
            "unreviewed E3 Pass-A predecessor path set")
    scope = _active_a2_derivation_scope()
    state = None if scope is None else _load_scoped_a2_source_state(scope)
    if state is None:
        state = _authenticated_pass_a_source_inventory_state()
    return {
        path: _read_authenticated_pass_a_source_predecessor(path, state)
        for path in sorted(E3_PASS_A_SOURCE_FORWARD_PATHS)
    }


def read_authenticated_pass_a_source_predecessor(path):
    """Read one exact A2 V2 source predecessor for offline Pass-A replay only."""
    resolve_historical_source_transition(
        path,
        expected_generation=E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
    )
    scope = _active_a2_derivation_scope()
    state = None if scope is None else _load_scoped_a2_source_state(scope)
    if state is None:
        state = _authenticated_pass_a_source_inventory_state()
    return _read_authenticated_pass_a_source_predecessor(path, state)


def _authenticated_cross_contract_inventory_state():
    """Authenticate immutable V284/V288 ancestry and the current A2 state once."""
    chain = load_inventory_generations()
    _authenticated_pass_a_source_inventory_state(chain)
    predecessor_generation = E3_CROSS_CONTRACT_SOURCE_FORWARD_PREDECESSOR_GENERATION
    authorization_generation = E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION
    for old_path in SOURCE_FORWARD_ALLOWED_PATHS:
        old = SOURCE_FORWARD_TRANSITIONS[old_path]
        old_predecessor_generation = old["a2_predecessor_generation"]
        old_authorization_generation = old["a2_generation"]
        require(chain[old_predecessor_generation - 1][0]
                == inventory_generation_path(old_predecessor_generation)
                and chain[old_predecessor_generation - 1][1].get("canonical_sha256")
                == old["a2_predecessor_sha256"],
                "immutable B4/B6 predecessor generation changed: " + old_path)
        old_auth_path, old_auth = chain[old_authorization_generation - 1]
        require(old_auth_path == inventory_generation_path(old_authorization_generation)
                and old_auth.get("generation") == old_authorization_generation
                and old_auth.get("canonical_sha256") == old["a2_authorization_sha256"]
                and old_auth.get("predecessor_inventory") == {
                    "path": inventory_generation_path(old_predecessor_generation),
                    "canonical_sha256": old["a2_predecessor_sha256"],
                    "generation": old_predecessor_generation,
                    "rewritten": False,
                }, "immutable B4/B6 source-forward generation changed: " + old_path)
        old_rows = {row["path"]: row["lf_source_sha256"]
                    for row in old_auth.get("source_identities", []) if type(row) is dict}
        require(old_rows.get(old_path) == old["successor_lf_source_sha256"],
                "immutable B4/B6 successor row changed: " + old_path)
        if old_path in E3_B6_SOURCE_FORWARD_PATHS:
            require(old_auth.get("source_forward_authorization")
                    == _e3_b6_source_forward_authorization(),
                    "immutable V276 B6 authorization content changed: " + old_path)

    require(len(chain) > authorization_generation
            and chain[predecessor_generation - 1][0] == inventory_generation_path(predecessor_generation)
            and chain[predecessor_generation - 1][1].get("canonical_sha256")
                == E3_CROSS_CONTRACT_SOURCE_FORWARD_PREDECESSOR_SHA256,
            "E3 cross-contract transition does not extend exact authenticated V283")
    authorization_path, authorization = chain[authorization_generation - 1]
    require(authorization_path == inventory_generation_path(authorization_generation)
            and authorization.get("generation") == authorization_generation
            and authorization.get("canonical_sha256") == E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_SHA256
            and authorization.get("predecessor_inventory") == {
                "path": inventory_generation_path(predecessor_generation),
                "canonical_sha256": E3_CROSS_CONTRACT_SOURCE_FORWARD_PREDECESSOR_SHA256,
                "generation": predecessor_generation,
                "rewritten": False,
            }
            and authorization.get("e3_cross_contract_source_forward_authorization")
                == _e3_cross_contract_source_forward_authorization(),
            "E3 cross-contract V284 authorization identity or payload drift")

    correction_generation = E3_CROSS_CONTRACT_ANCHOR_CORRECTION_GENERATION
    correction_path, correction = chain[correction_generation - 1]
    require(correction_path == inventory_generation_path(correction_generation)
            and correction.get("generation") == correction_generation
            and correction.get("schema_version") == correction_generation
            and correction.get("policy_id") == INVENTORY_POLICY_PREFIX + "_V" + str(correction_generation)
            and correction.get("canonical_sha256") == E3_CROSS_CONTRACT_ANCHOR_CORRECTION_SHA256
            and correction.get("predecessor_inventory") == {
                "path": inventory_generation_path(E3_CROSS_CONTRACT_ANCHOR_CORRECTION_PREDECESSOR_GENERATION),
                "canonical_sha256": E3_CROSS_CONTRACT_ANCHOR_CORRECTION_PREDECESSOR_SHA256,
                "generation": E3_CROSS_CONTRACT_ANCHOR_CORRECTION_PREDECESSOR_GENERATION,
                "rewritten": False,
            }
            and chain[E3_CROSS_CONTRACT_ANCHOR_CORRECTION_PREDECESSOR_GENERATION - 1][1].get("canonical_sha256")
                == E3_CROSS_CONTRACT_ANCHOR_CORRECTION_PREDECESSOR_SHA256
            and correction.get("e3_cross_contract_supporting_source_anchor_correction")
                == _e3_cross_contract_supporting_source_anchor_correction(),
            "E3 cross-contract V288 supporting-anchor correction identity or payload drift")

    latest_path, latest = chain[-1]
    latest_generation = len(chain)
    latest_predecessor = latest.get("predecessor_inventory")
    require(latest_generation >= correction_generation + 1
            and latest_path == inventory_generation_path(latest_generation)
            and latest.get("generation") == latest_generation
            and latest.get("schema_version") == latest_generation
            and latest.get("policy_id") == INVENTORY_POLICY_PREFIX + "_V" + str(latest_generation)
            and type(latest_predecessor) is dict
            and latest_predecessor == {
                "path": inventory_generation_path(latest_generation - 1),
                "canonical_sha256": chain[-2][1]["canonical_sha256"],
                "generation": latest_generation - 1,
                "rewritten": False,
            }, "E3 cross-contract latest-generation binding drift")
    rows = latest.get("source_identities")
    require(type(rows) is list and all(
        type(row) is dict and type(row.get("path")) is str
        and type(row.get("lf_source_sha256")) is str
        and re.fullmatch(r"[0-9a-f]{64}", row["lf_source_sha256"])
        for row in rows
    ), "E3 cross-contract latest inventory rows are malformed")
    row_paths = [row["path"] for row in rows]
    require(row_paths == sorted(row_paths) and len(row_paths) == len(set(row_paths)),
            "E3 cross-contract latest inventory rows are not uniquely path ordered")
    return chain, latest, {row["path"]: row["lf_source_sha256"] for row in rows}


def _load_scoped_a2_source_state(scope):
    """Return compact same-scope A2 proof inputs after one full chain walk.

    The scope itself fences HEAD, index, worktree, Git configuration and every
    A2 generation byte at entry and exit. This payload keeps only authenticated
    source-row hashes and successor identities, never the large parsed chain.
    Each caller still rereads its own fixture and current source bytes.
    """
    key = "a2.source-forward-summary"
    contract = _a2_scoped_contract()
    if contract is None:
        require(key not in scope.derivation_bytes,
                "A2 verifier contract changed after scoped source-forward authentication")
        return None
    cached = scope.load_derivation(key, contract)
    if cached is not None:
        _verify_scoped_a2_live_state(scope, directory=None, check_git=False)
        state = json.loads(cached)
        expected_paths = sorted(set(E3_CROSS_CONTRACT_V284_SOURCE_FORWARD_PATHS)
                                 | set(SOURCE_FORWARD_ALLOWED_PATHS))
        expected_pass_a_paths = sorted(E3_PASS_A_SOURCE_FORWARD_PATHS)
        from scripts import audit_core_01d_checkpoint_e_completion_v8 as receipt_scope
        receipt_scope._record_scope_metric("a2.source_forward_summary_hits")
        require(type(state) is dict and set(state) == {
                    "schema", "latest_generation", "latest_path", "latest_sha256",
                    "predecessor_sha256", "by_path", "successors",
                    "pass_a_v2_rows", "pass_a_v2_sha256", "pass_a_successors",
                }
                and state.get("schema") == 3
                and type(state.get("latest_generation")) is int
                and state.get("latest_generation", 0) >= E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION
                and state.get("latest_path") == inventory_generation_path(state["latest_generation"])
                and type(state.get("latest_sha256")) is str
                and re.fullmatch(r"[0-9a-f]{64}", state["latest_sha256"])
                and type(state.get("predecessor_sha256")) is str
                and re.fullmatch(r"[0-9a-f]{64}", state["predecessor_sha256"])
                and type(state.get("by_path")) is dict
                and type(state.get("pass_a_v2_rows")) is dict
                and type(state.get("pass_a_v2_sha256")) is str
                and state.get("pass_a_v2_sha256") == E3_PASS_A_SOURCE_FORWARD_PREDECESSOR_SHA256
                and all(type(path) is str and type(digest) is str
                        and re.fullmatch(r"[0-9a-f]{64}", digest)
                        for path, digest in state["pass_a_v2_rows"].items())
                and type(state.get("successors")) is dict
                and sorted(state["successors"]) == expected_paths
                and all(type(identity) is dict
                        and set(identity) == {"git_blob_sha1", "lf_source_sha256"}
                        and re.fullmatch(r"[0-9a-f]{40}", identity["git_blob_sha1"])
                        and re.fullmatch(r"[0-9a-f]{64}", identity["lf_source_sha256"])
                        for identity in state["successors"].values())
                and type(state.get("pass_a_successors")) is dict
                and sorted(state["pass_a_successors"]) == expected_pass_a_paths
                and all(type(identity) is dict
                        and set(identity) == {"git_blob_sha1", "lf_source_sha256"}
                        and re.fullmatch(r"[0-9a-f]{40}", identity["git_blob_sha1"])
                        and re.fullmatch(r"[0-9a-f]{64}", identity["lf_source_sha256"])
                        for identity in state["pass_a_successors"].values())
                and all(type(path) is str and type(digest) is str
                        and re.fullmatch(r"[0-9a-f]{64}", digest)
                        for path, digest in state["by_path"].items())
                and canonical(state) == cached,
                "A2 scoped source-forward summary is malformed or noncanonical")
        return state

    chain, latest, by_path = _authenticated_cross_contract_inventory_state()
    paths = sorted(set(E3_CROSS_CONTRACT_V284_SOURCE_FORWARD_PATHS)
                   | set(SOURCE_FORWARD_ALLOWED_PATHS))
    successors = {}
    for path in paths:
        identity = _authenticated_e3_successor_identity(path, chain, latest)
        require(type(identity) is dict
                and type(identity.get("git_blob_sha1")) is str
                and type(identity.get("lf_source_sha256")) is str,
                "A2 source-forward successor identity is malformed: " + path)
        successors[path] = {
            "git_blob_sha1": identity["git_blob_sha1"],
            "lf_source_sha256": identity["lf_source_sha256"],
        }
    pass_a_successors = {}
    for path in sorted(E3_PASS_A_SOURCE_FORWARD_PATHS):
        transition = resolve_historical_source_transition(
            path,
            expected_generation=E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
        )
        identity = {
            "git_blob_sha1": transition["successor_git_blob_sha1"],
            "lf_source_sha256": transition["successor_lf_source_sha256"],
        }
        require(by_path.get(path) == identity["lf_source_sha256"],
                "A2 scoped Pass-A successor differs from the authenticated current row: " + path)
        pass_a_successors[path] = identity
    latest_path = chain[-1][0]
    v2_path, v2 = chain[E3_PASS_A_SOURCE_FORWARD_PREDECESSOR_GENERATION - 1]
    require(v2_path == inventory_generation_path(E3_PASS_A_SOURCE_FORWARD_PREDECESSOR_GENERATION)
            and v2.get("canonical_sha256") == E3_PASS_A_SOURCE_FORWARD_PREDECESSOR_SHA256,
            "scoped Pass-A predecessor state does not bind immutable A2 V2")
    pass_a_v2_rows = {row["path"]: row["lf_source_sha256"]
                      for row in v2.get("source_identities", []) if type(row) is dict}
    state = {
        "schema": 3,
        "latest_generation": len(chain),
        "latest_path": latest_path,
        "latest_sha256": latest.get("canonical_sha256"),
        "predecessor_sha256": chain[-2][1].get("canonical_sha256"),
        "by_path": by_path,
        "successors": successors,
        "pass_a_successors": pass_a_successors,
        "pass_a_v2_rows": pass_a_v2_rows,
        "pass_a_v2_sha256": v2.get("canonical_sha256"),
    }
    payload = canonical(state)
    require(type(payload) is bytes, "A2 scoped source-forward summary could not be canonicalized")
    scope.store_derivation(key, contract, payload)
    from scripts import audit_core_01d_checkpoint_e_completion_v8 as receipt_scope
    receipt_scope._record_scope_metric("a2.source_forward_summary_misses")
    return state


def _authenticate_cross_contract_supporting_sources(by_path):
    """Freshly authenticate unchanged support anchors and current A2 source."""
    for anchor_path, anchor in E3_CROSS_CONTRACT_SUPPORTING_SOURCE_ANCHORS.items():
        _e3_path_stat(anchor_path, label="supporting source")
        anchor_raw, anchor_identity = _read_tracked_head_blob_scoped(ROOT, anchor_path)
        anchor_lf = anchor_raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        require(anchor_identity.git_blob_sha1 == anchor["git_blob_sha1"]
                and by_path.get(anchor_path) == hashlib.sha256(anchor_lf).hexdigest()
                == anchor["lf_source_sha256"],
                "E3 unchanged supporting source differs from latest A2 inventory: " + anchor_path)

    a2_path = Path(__file__).resolve().relative_to(ROOT).as_posix()
    _e3_path_stat(a2_path, label="current A2 source")
    a2_source, a2_identity = _read_tracked_head_blob_scoped(ROOT, a2_path)
    a2_lf = a2_source.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    a2_worktree_lf = (ROOT / a2_path).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    require(hashlib.sha256(a2_lf).hexdigest() == hashlib.sha256(a2_worktree_lf).hexdigest()
            and by_path.get(a2_path) == hashlib.sha256(a2_lf).hexdigest()
            and a2_identity.git_blob_sha1,
            "E3 cross-contract latest inventory does not authenticate the current A2 source")


def _read_authenticated_cross_contract_predecessor(path, common_state=None, *, batch_mode=False):
    """Read one exact predecessor, sharing only a caller-local authenticated state."""
    require(type(path) is str, "E3 cross-contract predecessor path is malformed")
    transition = resolve_historical_source_transition(
        path,
        expected_generation=E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
    )
    require(
        set(SOURCE_FORWARD_TRANSITIONS) == SOURCE_FORWARD_ALLOWED_PATHS
        and set(E3_CROSS_CONTRACT_SOURCE_FORWARD_TRANSITIONS)
            == E3_CROSS_CONTRACT_V284_SOURCE_FORWARD_PATHS
        and path in E3_CROSS_CONTRACT_V284_SOURCE_FORWARD_PATHS
        and set(E3_CROSS_CONTRACT_V284_SOURCE_FORWARD_PATHS)
            == set(SOURCE_FORWARD_ALLOWED_PATHS) | {
                "domain/current_shadow_all_market_runner.py",
                "domain/reviewed_fixture_catalog_admission_source_replay.py",
                "scripts/execute_current_shadow_request.py",
                "scripts/audit_core_01d_port02c_trigger_authority_b6.py",
                "runtime/worker_entry.py",
                "scripts/audit_auth_01_analysis_only_shadow_worker_boundary.py",
                "scripts/audit_core_01d_checkpoint_e_completion_v2.py",
            }, "unreviewed E3 cross-contract predecessor path: " + repr(path))
    require(set(_E3_CROSS_CONTRACT_SUCCESSORS) == E3_CROSS_CONTRACT_V284_SOURCE_FORWARD_PATHS,
            "E3 cross-contract successor table path set drift")
    require(set(E3_CROSS_CONTRACT_SOURCE_FORWARD_TRANSITIONS) == E3_CROSS_CONTRACT_V284_SOURCE_FORWARD_PATHS,
            "E3 cross-contract transition table path set drift")
    require(set(E3_CROSS_CONTRACT_SUPPORTING_SOURCE_ANCHORS)
            == E3_CROSS_CONTRACT_SUPPORTING_SOURCE_PATHS,
            "E3 unchanged supporting-source anchor path set drift")
    require(path not in E3_CROSS_CONTRACT_SUPPORTING_SOURCE_ANCHORS,
            "unchanged source anchor is not a predecessor transition: " + path)
    require(type(transition) is dict and set(transition) == {
        "predecessor_fixture", "predecessor_byte_size", "predecessor_git_blob_sha1",
        "predecessor_lf_source_sha256", "successor_git_blob_sha1", "successor_lf_source_sha256",
        "a2_predecessor_generation", "a2_predecessor_sha256", "a2_generation",
        "a2_authorization_sha256", "reason_type", "reason",
    }, "E3 cross-contract transition declaration shape drift")
    require(type(transition["predecessor_byte_size"]) is int and transition["predecessor_byte_size"] > 0
            and transition["reason_type"] in {
                "E3_RUN_02A_DURABLE_CANCELLATION_OPERATION_AUTHORIZATION",
                "E3_RUN_02A_CROSS_CONTRACT_COMPATIBILITY_V1",
            }
            and type(transition["reason"]) is str and transition["reason"],
            "E3 cross-contract transition is not narrowly reviewed: " + path)
    require(transition["a2_predecessor_generation"]
            == E3_CROSS_CONTRACT_SOURCE_FORWARD_PREDECESSOR_GENERATION
            and transition["a2_predecessor_sha256"]
                == E3_CROSS_CONTRACT_SOURCE_FORWARD_PREDECESSOR_SHA256
            and transition["a2_generation"]
                == E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION
            and transition["a2_authorization_sha256"]
                == E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_SHA256,
            "E3 cross-contract A2 generation binding drift: " + path)

    if path in SOURCE_FORWARD_ALLOWED_PATHS:
        old = SOURCE_FORWARD_TRANSITIONS[path]
        for field in ("predecessor_fixture", "predecessor_byte_size",
                      "predecessor_git_blob_sha1", "predecessor_lf_source_sha256"):
            require(transition[field] == old[field],
                    "E3 cross-contract predecessor rewrites prior B4/B6 identity: " + path)

    fixture_path = validate_repository_relative_path(transition["predecessor_fixture"])
    fixture_raw = _e3_read_exact_head_fixture(
        fixture_path,
        expected_blob=transition["predecessor_git_blob_sha1"],
        expected_lf=transition["predecessor_lf_source_sha256"],
        expected_size=transition["predecessor_byte_size"],
        label="V284 predecessor fixture",
    )

    scope = _active_a2_derivation_scope()
    scoped_state = (common_state if type(common_state) is dict
                    and common_state.get("schema") == 1
                    and "successors" in common_state else None)
    if scoped_state is None and scope is not None:
        scoped_state = _load_scoped_a2_source_state(scope)
    if scoped_state is not None:
        successor = scoped_state["successors"].get(path)
        require(type(successor) is dict
                and set(successor) == {"git_blob_sha1", "lf_source_sha256"},
                "E3 scoped successor identity is unavailable: " + path)
        current_raw = _e3_source_forward_file_identity(
            path, fixture=False,
            expected_blob=successor["git_blob_sha1"],
            expected_lf=successor["lf_source_sha256"],
            expected_size=0,
        )
        current_lf = hashlib.sha256(
            current_raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        ).hexdigest()
        require(scoped_state["by_path"].get(path) == current_lf,
                "E3 cross-contract latest inventory omits the exact current source")
        if not batch_mode or common_state is None:
            _authenticate_cross_contract_supporting_sources(scoped_state["by_path"])
        return fixture_raw, scoped_state

    if common_state is None:
        directory = _e3_directory_path(E3_CROSS_CONTRACT_FIXTURE_DIRECTORY, label="fixture directory")
        actual_fixtures = {
            E3_CROSS_CONTRACT_FIXTURE_DIRECTORY + "/" + child.name
            for child in directory.iterdir()
        }
        require(actual_fixtures == set(E3_CROSS_CONTRACT_FIXTURE_PATHS),
                "E3 source-forward fixture directory has missing, extra, or renamed evidence")
        chain, latest, by_path = _authenticated_cross_contract_inventory_state()
    else:
        chain, latest, by_path = common_state

    predecessor_generation = E3_CROSS_CONTRACT_SOURCE_FORWARD_PREDECESSOR_GENERATION
    authorization_generation = E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION
    successor = _authenticated_e3_successor_identity(path, chain, latest)
    current_raw = _e3_source_forward_file_identity(
        path, fixture=False,
        expected_blob=successor["git_blob_sha1"],
        expected_lf=successor["lf_source_sha256"],
        expected_size=0,
    )
    current_lf = hashlib.sha256(
        current_raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    ).hexdigest()
    require(by_path.get(path) == current_lf,
            "E3 cross-contract latest inventory omits the exact current source")
    if not batch_mode:
        require(inventory_document(latest, chain=chain) == latest,
                "E3 cross-contract latest inventory is stale or omits the exact current source")
        _authenticate_cross_contract_supporting_sources(by_path)
    elif common_state is None:
        _authenticate_cross_contract_supporting_sources(by_path)
    return fixture_raw, (chain, latest, by_path)


def read_authenticated_cross_contract_predecessor(path):
    """Read one historical source with a fresh chain and corpus observation."""
    raw, _state = _read_authenticated_cross_contract_predecessor(path)
    return raw


_CROSS_CONTRACT_SINGLE_READER_BASELINE = (
    read_authenticated_cross_contract_predecessor,
    read_authenticated_cross_contract_predecessor.__code__,
    read_authenticated_cross_contract_predecessor.__defaults__,
    read_authenticated_cross_contract_predecessor.__kwdefaults__,
    read_authenticated_cross_contract_predecessor.__closure__,
)


def _cross_contract_single_reader_is_baseline():
    current = read_authenticated_cross_contract_predecessor
    baseline = _CROSS_CONTRACT_SINGLE_READER_BASELINE
    return (current is baseline[0]
            and current.__code__ is baseline[1]
            and current.__defaults__ is baseline[2]
            and current.__kwdefaults__ is baseline[3]
            and current.__closure__ is baseline[4])


def read_authenticated_cross_contract_predecessors(paths):
    """Read a closed set of V284 predecessors after one authenticated A2 scan.

    Each requested fixture/current source is still reread independently. When
    an enabled checkpoint scope exists, only the compact chain-derived proof
    summary is reused; the owning scope fences repository/A2 state at entry
    and exit. No derivation survives that bounded scope.
    """
    require(type(paths) in (tuple, list), "E3 cross-contract batch paths are malformed")
    requested = tuple(paths)
    require(requested and all(type(path) is str for path in requested)
            and len(requested) == len(set(requested))
            and set(requested) <= set(E3_CROSS_CONTRACT_V284_SOURCE_FORWARD_PATHS),
            "E3 cross-contract batch path set is malformed or unauthorized")
    # Existing callers/tests may deliberately replace the public single-reader
    # seam. Preserve that behavior by executing it per path instead of silently
    # routing around the replacement through the private batch implementation.
    if not _cross_contract_single_reader_is_baseline():
        from scripts import audit_core_01d_checkpoint_e_completion_v8 as receipt_scope
        receipt_scope._record_scope_metric("a2.cross_contract_batch_fallbacks")
        return {path: read_authenticated_cross_contract_predecessor(path)
                for path in requested}
    from scripts import audit_core_01d_checkpoint_e_completion_v8 as receipt_scope
    scope = _active_a2_derivation_scope()
    if scope is not None:
        require(scope.enabled,
                "E3 cross-contract batch requires an enabled checkpoint receipt scope")
    receipt_scope._record_scope_metric("a2.cross_contract_batches")
    receipt_scope._record_scope_metric("a2.cross_contract_batch_paths", len(requested))
    common_state = None
    output = {}
    for path in requested:
        raw, common_state = _read_authenticated_cross_contract_predecessor(
            path, common_state, batch_mode=True)
        output[path] = raw
    require(common_state is not None, "E3 cross-contract batch did not authenticate a chain")
    require(_cross_contract_single_reader_is_baseline(),
            "E3 cross-contract public reader changed during batch authentication")
    return output


def inventory_document(template, corpus=None, *, chain=None):
    """Current corpus sealed into the shape of an authenticated generation."""
    value = {key: val for key, val in template.items()
             if key not in CORPUS_FIELDS and key != "canonical_sha256"}
    if corpus is None:
        chain = load_inventory_generations() if chain is None else chain
        generation = template.get("generation", len(chain))
        value.update(current_corpus_fields(generation=generation, chain=chain))
    else:
        value.update(corpus)
    return seal(value)


def build_inventory(directory=None):
    """Full current reviewed inventory for the latest discovered generation."""
    chain = load_inventory_generations(directory)
    return inventory_document(chain[-1][1], chain=chain)


def build_cross_contract_authorization_inventory(directory=None):
    """Propose V284 without rewriting V1–V283 or their immutable receipts."""
    directory = INVENTORY_DIRECTORY if directory is None else directory
    chain = load_inventory_generations(directory)
    require(len(chain) == E3_CROSS_CONTRACT_SOURCE_FORWARD_PREDECESSOR_GENERATION,
            "E3 cross-contract V284 must append directly after V283")
    previous_path, previous = chain[-1]
    require(previous_path == inventory_generation_path(E3_CROSS_CONTRACT_SOURCE_FORWARD_PREDECESSOR_GENERATION)
            and previous.get("canonical_sha256")
                == E3_CROSS_CONTRACT_SOURCE_FORWARD_PREDECESSOR_SHA256,
            "E3 cross-contract V284 predecessor V283 identity drift")
    generation = E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION
    value = {key: val for key, val in previous.items()
             if key not in CORPUS_FIELDS and key != "canonical_sha256"}
    value.update({
        "schema_version": generation,
        "policy_id": INVENTORY_POLICY_PREFIX + "_V" + str(generation),
        "generation": generation,
        "bridge_base_main_sha": BRIDGE_BASE_MAIN,
        "historical_a2_reviewed_head": A2_REVIEWED_HEAD,
        "predecessor_inventory": {
            "path": inventory_generation_path(generation - 1),
            "canonical_sha256": previous["canonical_sha256"],
            "generation": generation - 1,
            "rewritten": False,
        },
        "e3_cross_contract_source_forward_authorization":
            _e3_cross_contract_source_forward_authorization(),
    })
    return seal(value)


def build_cross_contract_anchor_correction_inventory(directory=None):
    """Propose the append-only V288 correction to the single V284 digest typo."""
    directory = INVENTORY_DIRECTORY if directory is None else directory
    chain = load_inventory_generations(directory)
    require(len(chain) == E3_CROSS_CONTRACT_ANCHOR_CORRECTION_PREDECESSOR_GENERATION,
            "E3 supporting-anchor correction must append directly after V287")
    previous_path, previous = chain[-1]
    require(previous_path == inventory_generation_path(E3_CROSS_CONTRACT_ANCHOR_CORRECTION_PREDECESSOR_GENERATION)
            and previous.get("canonical_sha256")
                == E3_CROSS_CONTRACT_ANCHOR_CORRECTION_PREDECESSOR_SHA256,
            "E3 supporting-anchor correction predecessor V287 identity drift")
    generation = E3_CROSS_CONTRACT_ANCHOR_CORRECTION_GENERATION
    value = {key: val for key, val in previous.items()
             if key not in CORPUS_FIELDS and key != "canonical_sha256"}
    value.update({
        "schema_version": generation,
        "policy_id": INVENTORY_POLICY_PREFIX + "_V" + str(generation),
        "generation": generation,
        "bridge_base_main_sha": BRIDGE_BASE_MAIN,
        "historical_a2_reviewed_head": A2_REVIEWED_HEAD,
        "predecessor_inventory": {
            "path": inventory_generation_path(generation - 1),
            "canonical_sha256": previous["canonical_sha256"],
            "generation": generation - 1,
            "rewritten": False,
        },
        "e3_cross_contract_supporting_source_anchor_correction":
            _e3_cross_contract_supporting_source_anchor_correction(),
    })
    return seal(value)


def build_successor_inventory(directory=None, corpus=None):
    """Propose the next contiguous generation bound to the current corpus."""
    chain = load_inventory_generations(directory)
    latest = chain[-1][1]
    generation = len(chain) + 1
    value = {key: val for key, val in latest.items()
             if key not in CORPUS_FIELDS and key != "canonical_sha256"}
    value.update(current_corpus_fields(generation=generation, chain=chain)
                 if corpus is None else corpus)
    value["schema_version"] = generation
    value["policy_id"] = INVENTORY_POLICY_PREFIX + "_V" + str(generation)
    value["generation"] = generation
    value["bridge_base_main_sha"] = BRIDGE_BASE_MAIN
    value["historical_a2_reviewed_head"] = A2_REVIEWED_HEAD
    value["predecessor_inventory"] = {"path": inventory_generation_path(generation - 1),
                                      "canonical_sha256": latest["canonical_sha256"],
                                      "generation": generation - 1, "rewritten": False}
    return seal(value)


def _authenticate_predecessors_uncached():
    values = {path: read(path) for path in PREDECESSORS}
    for path, expected in PREDECESSORS.items():
        require(values[path]["canonical_sha256"] == expected, "immutable predecessor identity drift: " + path)
    workflow_tree = git("rev-parse", "HEAD:.github/workflows").decode().strip()
    if workflow_tree != WORKFLOW_TREE:
        from scripts.audit_data_01c_restore_portability import historical_workflow_tree
        require(historical_workflow_tree(workflow_tree) == WORKFLOW_TREE, "workflow tree drift")
    require(not git("diff", "--name-only", "HEAD", "--", ".github/workflows").strip(), "dirty workflow source")
    return values


def authenticate_predecessors():
    """Authenticate startup predecessors inside one bounded source-read scope."""
    from scripts import audit_core_01d_checkpoint_e_completion_v8 as receipt_scope
    active = receipt_scope._ACTIVE_RECEIPT_SCOPES.get()
    if any(getattr(scope, "enabled", False)
           and getattr(scope, "unit", None) == receipt_scope._execution_unit()
           for scope in active.values()):
        return _authenticate_predecessors_uncached()
    roots = (sys.modules[__name__],)
    trusted = receipt_scope._auditor_contract_digest(*roots)
    with receipt_scope._bounded_receipt_scope(
            "pytest-session-a2-predecessors", roots, trusted):
        return _authenticate_predecessors_uncached()


def authenticate_inventory(directory=None, current=None):
    """Authenticate latest A2 state, reusing only a fenced same-call derivation."""
    default_call = directory is None and current is None
    if default_call:
        scope = _active_a2_derivation_scope()
        if scope is not None:
            contract = _a2_scoped_contract()
            key = "a2.authenticate-inventory.latest"
            if contract is None:
                require(key not in scope.derivation_bytes,
                        "A2 verifier contract changed after scoped inventory authentication")
            else:
                cached = scope.load_derivation(key, contract)
                if cached is not None:
                    _verify_scoped_a2_live_state(scope, directory=directory, check_git=True)
                    latest = marshal.loads(cached)
                    require(type(latest) is dict
                            and type(latest.get("generation")) is int
                            and type(latest.get("canonical_sha256")) is str,
                            "A2 scoped latest inventory clone is malformed")
                    from scripts import audit_core_01d_checkpoint_e_completion_v8 as receipt_scope
                    receipt_scope._record_scope_metric("a2.authenticate_inventory_scope_hits")
                    return latest
                from scripts import audit_core_01d_checkpoint_e_completion_v8 as receipt_scope
                receipt_scope._record_scope_metric("a2.authenticate_inventory_scope_misses")
                latest = _authenticate_inventory_uncached(directory, current)
                scope.store_derivation(key, contract, marshal.dumps(latest, 4))
                return latest
    return _authenticate_inventory_uncached(directory, current)


def _authenticate_inventory_uncached(directory=None, current=None):
    """Latest reviewed generation must equal the current source corpus."""
    directory = INVENTORY_DIRECTORY if directory is None else directory
    chain = load_inventory_generations(directory)
    latest_path, latest = chain[-1]
    # Generation 1 is proven against exact historical Git bytes on every run,
    # independently of whichever generation is currently latest.
    authenticate_historical_v1()
    if current is None:
        if directory == INVENTORY_DIRECTORY and _current_source_identities_match(latest):
            # All current inventory-derived fields are pure functions of this
            # exact path/byte corpus. Avoid rebuilding the historical
            # cross-contract projection on every pytest process.
            return latest
        current = build_inventory() if directory == INVENTORY_DIRECTORY else inventory_document(latest)
    if current != latest:
        differing = sorted(key for key in set(current) | set(latest)
                           if current.get(key) != latest.get(key))
        detail = {"fields": differing}
        if "source_identities" in differing:
            actual = {row["path"]: row["lf_source_sha256"] for row in current["source_identities"]}
            expected = {row["path"]: row["lf_source_sha256"] for row in latest["source_identities"]}
            detail["source_identities"] = {
                "added_paths": sorted(set(actual) - set(expected)),
                "removed_paths": sorted(set(expected) - set(actual)),
                "changed_paths": sorted(path for path in set(actual) & set(expected)
                                        if actual[path] != expected[path]),
            }
        obligation_field = "transport_and_process_discovery_obligations"
        if obligation_field in differing:
            def counts(rows):
                result = {}
                for row in rows:
                    key = json.dumps(row, sort_keys=True, separators=(",", ":"))
                    result[key] = result.get(key, 0) + 1
                return result
            actual = counts(current[obligation_field])
            expected = counts(latest[obligation_field])
            detail[obligation_field] = {
                "current_count": len(current[obligation_field]),
                "expected_count": len(latest[obligation_field]),
                "current_only": [
                    {"row": json.loads(key), "count": count - expected.get(key, 0)}
                    for key, count in sorted(actual.items()) if count > expected.get(key, 0)
                ][:30],
                "expected_only": [
                    {"row": json.loads(key), "count": count - actual.get(key, 0)}
                    for key, count in sorted(expected.items()) if count > actual.get(key, 0)
                ][:30],
            }
        raise AssertionError(
            "source or process discovery drift requires reviewed A2 inventory successor generation: "
            + latest_path + "; detail=" + json.dumps(detail, sort_keys=True)
        )
    return latest


def _current_source_identities_match(latest):
    """Cheaply verify the reviewed current corpus without rebuilding A2."""
    expected = {row["path"]: row["lf_source_sha256"]
                for row in latest.get("source_identities", [])}
    paths = current_source_paths()
    if set(paths) != set(expected):
        return False
    for path in paths:
        raw = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(raw).hexdigest() != expected[path]:
            return False
    return True


def activation_and_no_bypass(startup_text, workflow_text, guard_text, kernel_text, identity):
    """Root bootstrap, patch allowlist, guard hooks and kernel policy checks."""
    startup = ast.parse(startup_text)
    pins = next(ast.literal_eval(node.value) for node in startup.body
                if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                and target.id == "ROOT_TEST_SOURCE_PINS" for target in node.targets))
    protected = set(GUARD_PATHS) - {"sitecustomize.py"}
    protected.add("scripts/audit_core_01d_ci_offline_transport_boundary.py")
    successor_declarations = [node for node in startup.body
                              if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                              and target.id == "ROOT_TEST_SOURCE_SUCCESSORS" for target in node.targets)]
    if successor_declarations:
        from scripts import audit_phase_a_pc_upcoming_retention_successor as retention
        retention.authenticate_bootstrap_successor(startup_text, identity)
    else:
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


_A2_BASELINE_TRACKED_HEAD_READER = read_tracked_head_blob


def _read_tracked_head_blob_scoped(repository_root, relative_path, **kwargs):
    """Reuse a HEAD-blob derivation only inside the active fenced scope."""
    reader = read_tracked_head_blob
    if reader is not _A2_BASELINE_TRACKED_HEAD_READER:
        return reader(repository_root, relative_path, **kwargs)
    scope = _active_a2_derivation_scope()
    if scope is None:
        return reader(repository_root, relative_path, **kwargs)
    from scripts import audit_phase_a_pass_a_tests_source_successor as pass_a
    return pass_a.read_tracked_head_blob_scoped(
        repository_root, relative_path, **kwargs)


_A2_SCOPED_FUNCTION_NAMES = (
    "authenticate_inventory", "_authenticate_inventory_uncached",
    "authenticate_predecessors", "_authenticate_predecessors_uncached",
    "load_inventory_generations", "read_generation", "discover_inventory_generations",
    "_load_inventory_generations_uncached", "_load_scoped_a2_source_state",
    "inventory_generation_path",
    "_authenticated_json_bytes", "_immutable_json_snapshot",
    "authenticate_historical_v1", "build_inventory", "inventory_document",
    "current_corpus_fields", "resolve_historical_source_transition",
    "_authenticated_cross_contract_inventory_state",
    "_authenticated_pass_a_source_inventory_state",
    "_read_authenticated_pass_a_source_predecessor",
    "read_authenticated_pass_a_source_predecessor",
    "read_authenticated_pass_a_source_predecessors",
    "_authenticated_e3_successor_identity", "_read_authenticated_cross_contract_predecessor",
    "read_authenticated_cross_contract_predecessor",
    "read_authenticated_cross_contract_predecessors",
    "read_authenticated_forward_predecessor", "_e3_read_exact_head_fixture",
    "_e3_source_forward_file_identity", "_authenticate_cross_contract_supporting_sources",
    "read_tracked_head_blob", "_read_tracked_head_blob_scoped", "git", "canonical", "seal",
)


def _a2_stable_scope_value(value):
    if type(value) is dict:
        return tuple(sorted((repr(key), _a2_stable_scope_value(item))
                            for key, item in value.items()))
    if type(value) in (list, tuple):
        return tuple(_a2_stable_scope_value(item) for item in value)
    if type(value) in (set, frozenset):
        return tuple(sorted((_a2_stable_scope_value(item) for item in value), key=repr))
    if type(value) is bytes:
        return ("bytes", hashlib.sha256(value).hexdigest(), len(value))
    if isinstance(value, Path):
        return ("path", str(value))
    if callable(value):
        code = getattr(value, "__code__", None)
        return ("callable", getattr(value, "__module__", None),
                getattr(value, "__qualname__", None), id(value), id(code))
    if hasattr(value, "__name__") and hasattr(value, "__dict__"):
        return ("named", getattr(value, "__name__", None), id(value))
    return (type(value).__name__, repr(value))


def _a2_function_scope_value(function):
    target = getattr(function, "__wrapped__", function)
    closure = (() if target.__closure__ is None else
               tuple(_a2_stable_scope_value(cell.cell_contents)
                     for cell in target.__closure__))
    return (
        _a2_stable_scope_value(target.__defaults__),
        _a2_stable_scope_value(target.__kwdefaults__),
        closure,
        _a2_stable_scope_value(target.__annotations__),
        _a2_stable_scope_value(function.__dict__),
    )


def _a2_function_scope_code(function):
    """Return the underlying code object for functions and cache wrappers."""
    return getattr(getattr(function, "__wrapped__", function), "__code__", None)


_A2_SCOPED_FUNCTION_BASELINES = {
    name: (globals()[name], _a2_function_scope_code(globals()[name]),
           getattr(getattr(globals()[name], "__wrapped__", globals()[name]), "__defaults__", None),
           getattr(getattr(globals()[name], "__wrapped__", globals()[name]), "__kwdefaults__", None),
           getattr(getattr(globals()[name], "__wrapped__", globals()[name]), "__closure__", None),
           _a2_function_scope_value(globals()[name]))
    for name in _A2_SCOPED_FUNCTION_NAMES
}
_A2_SCOPED_RULE_BASELINES = {
    name: _a2_stable_scope_value(value)
    for name, value in globals().items()
    if name.isupper() and not name.startswith("__")
    and not name.startswith("_A2_SCOPED")
    and not callable(value)
    and not (hasattr(value, "__name__") and hasattr(value, "__dict__"))
}
_A2_SCOPED_MARSHAL_BASELINES = (marshal.dumps, marshal.loads)


def _a2_scoped_contract():
    """Return the pinned same-scope cache contract or None on any seam drift."""
    if (marshal.dumps is not _A2_SCOPED_MARSHAL_BASELINES[0]
            or marshal.loads is not _A2_SCOPED_MARSHAL_BASELINES[1]):
        return None
    for name, baseline in _A2_SCOPED_FUNCTION_BASELINES.items():
        function = globals().get(name)
        target = None if function is None else getattr(function, "__wrapped__", function)
        if (function is not baseline[0] or _a2_function_scope_code(function) is not baseline[1]
                or getattr(target, "__defaults__", None) is not baseline[2]
                or getattr(target, "__kwdefaults__", None) is not baseline[3]
                or getattr(target, "__closure__", None) is not baseline[4]
                or _a2_function_scope_value(function) != baseline[5]):
            return None
    for name, baseline in _A2_SCOPED_RULE_BASELINES.items():
        if name not in globals() or _a2_stable_scope_value(globals()[name]) != baseline:
            return None
    signature = repr((
        tuple((name, id(value[0]), id(value[1]), value[5])
              for name, value in sorted(_A2_SCOPED_FUNCTION_BASELINES.items())),
        tuple(sorted(_A2_SCOPED_RULE_BASELINES.items())),
    )).encode("utf-8")
    return "a2-same-scope-v1:" + hashlib.sha256(signature).hexdigest()


def _active_a2_derivation_scope():
    """Find a bounded checkpoint scope without importing Pass-A on cold paths."""
    engine = sys.modules.get("scripts.audit_core_01d_checkpoint_e_completion_v8")
    if engine is None or not engine._ACTIVE_RECEIPT_SCOPES.get():
        return None
    from scripts import audit_phase_a_pass_a_tests_source_successor as pass_a
    scope = pass_a._active_checkpoint_derivation_scope()
    if scope is not None:
        require(scope.enabled,
                "A2 same-invocation derivation requires an enabled receipt scope")
    return scope


def _verify_scoped_a2_live_state(scope, *, directory=None, check_git=True):
    """Recheck A2 generation identity and optionally the live Git fence.

    The owning scope hashes the raw bytes of the complete generation chain at
    entry and exit (currently V1-V377). Between those boundaries, every scoped
    hit rediscovers the exact namespace, checks regular-file and mode identity,
    unconditionally rereads and hashes the latest generation (currently V377),
    and uses the POSIX ``(st_mode, st_ino, st_size, st_mtime_ns, st_ctime_ns)``
    fence to decide when to reread V1-V376. Replacing ``Path.read_bytes``
    forces a full byte reread as well. Thus older generations are not byte-
    hashed on every unchanged intermediate hit: same-stat edits to an older
    file are deferred to the scope-exit full hash. A change fully reverted
    before that boundary can evade content comparison if the metadata fence
    also cannot distinguish it (an ABA limitation). The POSIX metadata fence
    is an optimization, not an atomic filesystem snapshot or inode-proof claim.
    """
    require(getattr(scope, "enabled", False),
            "A2 scoped derivation requires an enabled receipt scope")
    owner = getattr(scope, "state_owner", scope)
    from scripts import audit_core_01d_checkpoint_e_completion_v8 as receipt_scope
    require(receipt_scope._execution_unit() == owner.unit,
            "A2 scoped derivation crossed process, thread, or async-task boundary")
    expected_names = sorted([
        label.split(":", 1)[1]
        for label in owner.state_components_at_entry
        if label.startswith("a2-bytes:")
    ], key=lambda name: int(INVENTORY_NAME.fullmatch(name).group(1)))
    effective_directory = INVENTORY_DIRECTORY if directory is None else directory
    require(effective_directory == INVENTORY_DIRECTORY,
            "A2 scoped derivation cannot verify a noncanonical inventory directory")
    live = discover_inventory_generations(directory)
    live_paths = [path for _generation, path in live]
    expected_paths = [effective_directory + "/" + name for name in expected_names]
    require(live_paths == expected_paths,
            "A2 scoped generation namespace changed during receipt scope")
    current_components = {}
    receipt_scope._execution_state_digest(
        _components=current_components, _include_git=check_git, _include_a2=False)

    inventory_root = ROOT / INVENTORY_DIRECTORY
    directory_metadata = inventory_root.lstat()
    directory_mode = stat.S_IMODE(directory_metadata.st_mode).to_bytes(4, "big")
    current_components["a2-directory-mode"] = hashlib.sha256(directory_mode).hexdigest()
    if stat.S_ISLNK(directory_metadata.st_mode):
        current_components["a2-directory-link"] = hashlib.sha256(
            os.fsencode(os.readlink(inventory_root))).hexdigest()
    resolved_directory = inventory_root.resolve(strict=True)
    current_components["a2-directory"] = hashlib.sha256(
        str(resolved_directory).encode("utf-8")).hexdigest()

    force_all_bytes = Path.read_bytes is not _A2_PATH_READ_BYTES_BASELINE
    for index, (_generation, relative_path) in enumerate(live):
        path = ROOT / relative_path
        metadata = path.lstat()
        require(stat.S_ISREG(metadata.st_mode),
                "A2 generation observation encountered a non-regular file")
        stat_raw = repr((metadata.st_mode, metadata.st_ino, metadata.st_size,
                         metadata.st_mtime_ns, metadata.st_ctime_ns)).encode("ascii")
        stat_sha = hashlib.sha256(stat_raw).hexdigest()
        mode_raw = (path.name.encode("utf-8") + b"\0" +
                    stat.S_IMODE(metadata.st_mode).to_bytes(4, "big"))
        mode_sha = hashlib.sha256(mode_raw).hexdigest()
        stat_label = "a2-path-stat:" + path.name
        mode_label = "a2-path-mode:" + path.name
        byte_label = "a2-bytes:" + path.name
        expected_stat = owner.state_components_at_entry.get(stat_label)
        expected_mode = owner.state_components_at_entry.get(mode_label)
        expected_bytes = owner.state_components_at_entry.get(byte_label)
        require(expected_stat is not None and expected_mode is not None
                and expected_bytes is not None,
                "A2 generation lacks an entry-state component: " + path.name)
        require(mode_sha == expected_mode,
                "A2 generation file mode changed during receipt scope: " + path.name)
        current_components[stat_label] = stat_sha
        current_components[mode_label] = mode_sha
        read_bytes = (index == len(live) - 1 or stat_sha != expected_stat
                      or force_all_bytes)
        if read_bytes:
            observed_bytes = hashlib.sha256(path.read_bytes()).hexdigest()
            require(observed_bytes == expected_bytes,
                    "receipt execution state changed during scope: a2-bytes:" + path.name)
            current_components[byte_label] = observed_bytes

    expected_components = owner.state_components_at_entry
    if check_git:
        expected_labels = set(expected_components) - {
            label for label in expected_components if label.startswith("a2-bytes:")
        }
        current_labels = set(current_components) - {
            label for label in current_components if label.startswith("a2-bytes:")
        }
    else:
        relevant = ("root", "a2-directory", "a2-directory-mode", "a2-directory-link",
                    "a2-path-stat:", "a2-path-mode:")
        expected_labels = {label for label in expected_components
                           if label == "root" or label.startswith(relevant[1:])}
        current_labels = {label for label in current_components
                          if label == "root" or label.startswith(relevant[1:])}
    changed = sorted(
        label for label in expected_labels | current_labels
        if label not in expected_labels or label not in current_labels
        or expected_components.get(label) != current_components.get(label)
    )
    if changed:
        raise AssertionError("receipt execution state changed during scope: "
                             + ", ".join(changed[:20]))


for _name in ("_a2_scoped_contract", "_active_a2_derivation_scope",
              "_verify_scoped_a2_live_state"):
    _function = globals()[_name]
    _A2_SCOPED_FUNCTION_BASELINES[_name] = (
        _function, _a2_function_scope_code(_function), _function.__defaults__,
        _function.__kwdefaults__, _function.__closure__,
        _a2_function_scope_value(_function),
    )


if __name__ == "__main__":
    main()
