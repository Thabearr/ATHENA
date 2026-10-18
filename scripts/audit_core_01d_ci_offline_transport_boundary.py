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
from pathlib import Path, PurePosixPath
import re
import subprocess
import tokenize
import yaml

from runtime.source_identity import read_tracked_head_blob, validate_repository_relative_path

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


def read(path):
    raw = (ROOT / path).read_bytes()
    return json.loads(_authenticated_json_bytes(raw, path))


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
    return json.loads(_authenticated_json_bytes(raw, path, True))


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

    current, current_identity = read_tracked_head_blob(ROOT, path)
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
    fixture_path = ROOT / fixture
    import stat
    try:
        resolved_root = ROOT.resolve(strict=True)
        resolved_fixture = fixture_path.resolve(strict=True)
        resolved_fixture.relative_to(resolved_root)
        cursor = ROOT
        fixture_parts = PurePosixPath(fixture).parts
        fixture_stat = None
        for index, part in enumerate(fixture_parts):
            cursor = cursor / part
            candidate_stat = cursor.lstat()
            is_junction = getattr(cursor, "is_junction", lambda: False)()
            reparse = bool(getattr(candidate_stat, "st_file_attributes", 0)
                           & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
            require(not stat.S_ISLNK(candidate_stat.st_mode) and not is_junction and not reparse,
                    "A2 source-forward fixture path contains a symlink or junction")
            if index < len(fixture_parts) - 1:
                require(stat.S_ISDIR(candidate_stat.st_mode),
                        "A2 source-forward fixture parent is not a regular directory")
            else:
                fixture_stat = candidate_stat
    except (OSError, ValueError) as error:
        raise AssertionError("A2 source-forward predecessor fixture is unavailable or escapes scope") from error
    require(fixture_stat is not None and stat.S_ISREG(fixture_stat.st_mode),
            "A2 source-forward predecessor fixture is not a regular file")
    fixture_raw = fixture_path.read_bytes()
    require(len(fixture_raw) == transition["predecessor_byte_size"],
            "A2 source-forward predecessor fixture size mismatch")
    try:
        fixture_raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise AssertionError("A2 source-forward predecessor fixture encoding is invalid") from error
    fixture_lf = fixture_raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    fixture_blob = hashlib.sha1(b"blob " + str(len(fixture_raw)).encode("ascii") + b"\0" + fixture_raw).hexdigest()
    require(fixture_blob == transition["predecessor_git_blob_sha1"]
            and hashlib.sha256(fixture_lf).hexdigest() == transition["predecessor_lf_source_sha256"],
            "A2 source-forward predecessor fixture identity mismatch")

    # In a committed checkout, bind the fixture's Git mode and object bytes.
    # During local authoring, the byte and path checks above still apply before
    # the new evidence fixture is added to the next commit.
    fixture_entry = git("ls-tree", "-z", "HEAD", "--", fixture)
    if fixture_entry:
        metadata, tree_path = fixture_entry.rstrip(b"\0").split(b"\t", 1)
        mode, kind, blob = metadata.decode("ascii").split(" ")
        committed = git("cat-file", "blob", blob)
        require(tree_path.decode("utf-8") == fixture and mode == "100644" and kind == "blob"
                and blob == transition["predecessor_git_blob_sha1"]
                and committed == fixture_raw,
                "A2 source-forward committed predecessor fixture identity mismatch")

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

    a2_path = Path(__file__).resolve().relative_to(ROOT).as_posix()
    a2_source, a2_identity = read_tracked_head_blob(ROOT, a2_path)
    a2_lf = a2_source.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    a2_worktree_lf = (ROOT / a2_path).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    a2_digest = hashlib.sha256(a2_lf).hexdigest()
    require(a2_digest == hashlib.sha256(a2_worktree_lf).hexdigest()
            and by_path.get(a2_path) == a2_digest
            and a2_identity.git_blob_sha1,
            "A2 source-forward inventory does not authenticate its current primitive")
    return fixture_raw


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
    workflow_tree = git("rev-parse", "HEAD:.github/workflows").decode().strip()
    if workflow_tree != WORKFLOW_TREE:
        from scripts.audit_data_01c_restore_portability import historical_workflow_tree
        require(historical_workflow_tree(workflow_tree) == WORKFLOW_TREE, "workflow tree drift")
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
