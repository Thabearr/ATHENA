"""Offline CORE-01D inventory and fail-closed Checkpoint-E disposition.

This evidence-only checkpoint deliberately grants no migration or retirement.
Base Git identities make historical integrity independently checkable in shallow
CI. No provider module, GitHub transport, executor or real SMTP is invoked.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import yaml

from domain.run_contracts import canonical_json_bytes
from services.athena_run_request_parser import parse_explicit_request
from services.athena_run_workflow_request import resolve_workflow_request
from services import athena_shadow_issue_comment_compatibility as comment
from services import athena_artifact_role_resolver as roles
from scripts import capture_p4_3_workflow_capability_matrix as census
from scripts import audit_p4_workflow_evolution_ledger as evolution
from scripts.restore_athena_artifact_roles import (
    extract_verified_paths, manifest_root, verify_archive_producer_receipt,
)

ROOT = Path(__file__).resolve().parents[1]
BASE = "f61ee8416025a97a3acf8233dbdb34e29f48bac5"
POLICY_ID = "ATHENA_CORE_01D_WORKFLOW_CONSOLIDATION_CHECKPOINT_E_V1"
MATRIX_POLICY_ID = "ATHENA_CORE_01D_TRIGGER_CAPABILITY_MATRIX_V1"
RECEIPT_PATH = "artifacts/architecture/checkpoint_e_workflow_consolidation_v1.json"
MATRIX_PATH = "artifacts/architecture/checkpoint_e_workflow_capability_matrix_v1.json"
RETAINED_STATUS_PATH = "artifacts/architecture/core_01d_retained_workflow_status_v1.json"
PASS1_SUPPORTING_SOURCE_PATHS = (
    ".github/workflows/audit-fotmob-utc-native-xg-fresh-holdout-lineage.yml",
    ".github/workflows/bridge-fotmob-fresh-holdout-continuity-receipts.yml",
    ".github/workflows/watch-fotmob-fresh-holdout-scheduler-liveness.yml",
    "docs/fotmob_utc_native_expected_goals_fresh_holdout_activation_runner.md",
    "docs/fotmob_utc_native_expected_goals_fresh_holdout_pr119_bootstrap_recovery.md",
    "domain/current_fotmob_latest_durable_fresh_history.py",
    "scripts/audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection.py",
    "scripts/audit_p4_3_workflow_retirement_ledger.py",
    "tests/test_fotmob_fresh_holdout_actions_lineage_audit_pr175_projection.py",
    "tests/test_fotmob_fresh_holdout_continuity_workflow.py",
    "tests/test_fotmob_fresh_holdout_pr119_bootstrap_recovery.py",
    "tests/test_fotmob_utc_native_expected_goals_fresh_holdout_activation_runner.py",
    "tests/test_fresh_holdout_release_visibility_race_hotfix.py",
    "tests/test_p4_2_athena_run_workflow.py",
    "tests/test_p4_4a1_baseline_workflow_maintenance_revision_authority.py",
)
PASS1_V1_BASE_SOURCE_FIXTURES = {
    ".github/workflows/audit-fotmob-utc-native-xg-fresh-holdout-lineage.yml": (
        "tests/fixtures/core_01d/pass1-v1-source/audit-lineage.yml",
        "0ba12d02fc2cd5f7a7d9fb1458eeec5cbe3bbd23",
        "13d8888ea802b2ef996b3e296a668f087a20a50fd0ee51ee8c5cbbc26673a274",
    ),
    ".github/workflows/bridge-fotmob-fresh-holdout-continuity-receipts.yml": (
        "tests/fixtures/core_01d/pass1-v1-source/bridge-continuity-receipts.yml",
        "74bfd162bd5fe67b79dd6c91550dbbb557b502e9",
        "6902f337ee1e33aaf9cd742cdd42796ef6f1a6e299097d4a204959b872b47ebd",
    ),
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml": (
        "tests/fixtures/architecture/revised_workflows/"
        "fotmob-utc-native-xg-fresh-holdout-pre-core-01d-pr119-release-only-bootstrap.yml",
        "1efe1e34d4459b2aeea17d5da8ba77bd4e2442f2",
        "9ee4a81f508196716ccd4454b24644f8f5c9aece479103f4a17f8f9a13cfdbb9",
    ),
    "docs/fotmob_utc_native_expected_goals_fresh_holdout_activation_runner.md": (
        "tests/fixtures/core_01d/pass1-v1-source/fotmob-activation-runner.md",
        "847d4f5466c8b5493d6a2bf0b784957d72c84d03",
        "d2482da65d38b36d10ca0edb87f6d710e380ad4cefa0660be2af587102355bb8",
    ),
    "docs/fotmob_utc_native_expected_goals_fresh_holdout_pr119_bootstrap_recovery.md": (
        "tests/fixtures/core_01d/pass1-v1-source/pr119-bootstrap-recovery.md",
        "1c76953ae04773ee19d7a701c9aa4a6f3b2aed21",
        "32b324f8cf92206abf7b4d1eb6fcdcc05a49776fae8b146811afc6027d5e1aa9",
    ),
    "domain/current_fotmob_latest_durable_fresh_history.py": (
        "tests/fixtures/core_01d/pass1-v1-source/current-latest-fresh-history.py",
        "bc3a9a81211a1ecd08f0ab05427d765a09bf2eea",
        "692ea083ad5a115b51a9d3e33da874b4bce7902f07d81034f9adc3fc7a979996",
    ),
    "scripts/audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection.py": (
        "tests/fixtures/core_01d/pass1-v1-source/schedule-recovery-lineage-projection.py",
        "4f9c0ffda3841434bacd5001164aeae29de8fcc4",
        "5fef00a24611cb134bb35409e9f9c668f942cca68ed6eb94404dc5804378ea03",
    ),
    "scripts/audit_p4_3_workflow_retirement_ledger.py": (
        "tests/fixtures/core_01d/pass1-v1-source/audit-p4-3-retirement-ledger.py",
        "4d1b7f131079bdc97877fe6fdba557fa03239266",
        "82b38665fdeaaf5a8478ae818d790aef67cb75458e2c5e8487661976c01799b6",
    ),
    "tests/test_fotmob_fresh_holdout_actions_lineage_audit_pr175_projection.py": (
        "tests/fixtures/core_01d/pass1-v1-source/test-lineage-pr175-projection.py",
        "abf4a91dd7060a5a5f4af70f4285fdc40c3b5d2a",
        "2708445ce510256952d98c4b4ba2d1f1f34fc09abc1de5801e44d55489b0ea15",
    ),
    "tests/test_fotmob_fresh_holdout_continuity_workflow.py": (
        "tests/fixtures/core_01d/pass1-v1-source/test-continuity-workflow.py",
        "2ffb1642e782ea0bc993302ca40a6e2645013fc3",
        "5333e445bb2a5fabc52717a322df688cf30d983cc8e45f3e36de5ad65a264987",
    ),
    "tests/test_fotmob_fresh_holdout_pr119_bootstrap_recovery.py": (
        "tests/fixtures/core_01d/pass1-v1-source/test-pr119-bootstrap-recovery.py",
        "a63368d629f00f24c4c2d900961d139abcda109f",
        "b7f718aa851964a4fa123ca8388fc77d4da45aaa788adeeb6ecf6b5022fb7aa9",
    ),
    ".github/workflows/watch-fotmob-fresh-holdout-scheduler-liveness.yml": (
        "tests/fixtures/core_01d/pass1-v1-source/scheduler-liveness.yml",
        "f613211018417435cb4ad7a22529b1ff0a38d690",
        "2c77dfc4070bdf76a26b2209622f3ffc5fd82758f1203504729e9c90d375da21",
    ),
    "tests/test_fotmob_utc_native_expected_goals_fresh_holdout_activation_runner.py": (
        "tests/fixtures/core_01d/pass1-v1-source/test-activation-runner.py",
        "7a2a3be430896fb05717bf2d293c8b88e6570a65",
        "941427ed48f0c2f96c97f69a728ec47e69bcbea4d625e296c211c38bc0895c7d",
    ),
    "tests/test_fresh_holdout_release_visibility_race_hotfix.py": (
        "tests/fixtures/core_01d/pass1-v1-source/test-visibility-race-hotfix.py",
        "43ffef4866e6ea3ba57f5d6d52457be9b80703a0",
        "09fd0d346bf6c7a62a0369e9767de19743578c5cb03d908a2ffe337abbb148b4",
    ),
    "tests/test_p4_2_athena_run_workflow.py": (
        "tests/fixtures/core_01d/pass1-v1-source/test-p42-athena-run-workflow.py",
        "84f520e3f35c11a0556fd02c4d5db37463bde1f7",
        "f6003ed26ab05d475f0ad28b6a87a6d0323b25f808a4dc5d15e2a317a6b50b73",
    ),
    "tests/test_p4_4a1_baseline_workflow_maintenance_revision_authority.py": (
        "tests/fixtures/core_01d/pass1-v1-source/test-p44a1-maintenance-authority.py",
        "ac77ec10776758b0a5209cbc227d8f50eb511d8e",
        "baabb01e1361139952b50f03df19b5f72cd78edc7d85b5795eba60fdef2dc438",
    ),
    "tests/test_core_01_schedule_date_disposition.py": (
        "tests/fixtures/core_01d/pass1-v1-source/test-core-01-schedule-date-disposition.py.txt",
        "f658773457d6a46bbd25f6b2a5636fff019b0043",
        "aa0ed975266cd905c956de2aa951828194ae4387a3cce45f2cdaa7dcab3f83b9",
    ),
}
BASE_PATH = "tests/fixtures/core_01d/exact-main-source-inventory.json"
HISTORY_PATH = "tests/fixtures/core_01d/workflow-history-20261001.json"
ZIP_PATH = "tests/fixtures/core_01d/accepted-athena-run-36860297707.zip"
ZIP_SHA = "9d14b71413ed68e9e157d668a79851e3fbc3dd746c204c8ddfc0eaf245bcf355"
HISTORICAL_AUDIT = "scripts/audit_lg_a_worker_launch_failure_remediation.py"
HISTORICAL_AUDIT_FIXTURE = "tests/fixtures/core_01d/pre-core01d-remediation-audit.py.txt"
CHECKPOINT_MATRIX_SHA = "9eb6e3fb35c7a58195a789aaf357fc35374b6f830f7da289ceeb3a84e403c815"
CHECKPOINT_RECEIPT_SHA = "7a0d0f0bd3e448e9c9643954b20d4a8b7aab17b93cc28116ffab22452ba146ab"
# Filled from the independently captured exact-main inputs; not derived from an
# adversarial receipt's declared hashes.
BASE_INPUT_SHA = "5eacf1cb186579b5632a516a853d925c24b85c38fa67ec5d6b96656f40c836fe"
HISTORY_INPUT_SHA = "66ef6267af033a6e907aebe16ae44c20a15d9a4c5425960aa1da2003c89e39b6"
CANONICAL = ".github/workflows/athena-run.yml"
SHADOW = ".github/workflows/current-shadow-all-market.yml"
ALLOWED_STATUS = {"CANONICAL_SUPPORTED", "EXPLICIT_RETAINED_COMPATIBILITY", "DIAGNOSTIC_ONLY", "HISTORICAL_ONLY", "UNKNOWN"}
PASS_A_HISTORICAL_SOURCE_BLOBS = {
    # D1 adds versioned identities/source projection support. Historical Pass-A
    # reconstruction continues to inspect each exact pre-D1 source blob.
    "domain/execution_envelope.py": "8f0a84db708fef11fabb857b21b1322cb5b5a36e",
    "scripts/audit_core_01_schedule_date_disposition.py": "6f8d453cee00a13865c984b9a80880678b4fd84c",
    "tests/test_core_01_schedule_date_disposition.py": "f658773457d6a46bbd25f6b2a5636fff019b0043",
    # D2 changes current sources that existed in the D1 main tree. Their
    # pre-D2 bytes remain in dedicated fixtures while the current versions are
    # authenticated first by the append-only A2 source inventory.
    "api/server.py": "1e8d3b8968a37eed78741e018fa4da057578223c",
    "run_desktop.py": "39c4cf8c780eb2831b637a69ff0648b6eb465874",
    "tests/test_api_error_handling.py": "a827e02b95779ca0478ffa74db34e41de1e04b42",
    "tests/test_product_baseline_v1.py": "2d552f49cf84462bd1b32e86eea2a96ee0570b64",
}
PASS_A_BASE_SOURCE_BLOBS = {
    "api/server.py": "21c9aa432aaccd8db041778a26365f12f6af80de",
    "run_desktop.py": "3495618a198ccde18cad7d578362b1366e4bcedc",
    "tests/test_api_error_handling.py": "a827e02b95779ca0478ffa74db34e41de1e04b42",
    "tests/test_product_baseline_v1.py": "2d552f49cf84462bd1b32e86eea2a96ee0570b64",
}
PASS_A_HISTORICAL_SOURCE_FIXTURES = {
    "api/server.py": "tests/fixtures/core_01d/app_01c_historical/api_server.py.b64",
    "run_desktop.py": "tests/fixtures/core_01d/app_01c_historical/run_desktop.py.txt",
    "tests/test_api_error_handling.py": "tests/fixtures/core_01d/app_01c_historical/test_api_error_handling.py.txt",
    "tests/test_product_baseline_v1.py": "tests/fixtures/core_01d/app_01c_historical/test_product_baseline_v1.py.txt",
}


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def self_sha(value):
    return sha(canonical({k: v for k, v in value.items() if k != "canonical_sha256"}))


def seal(value):
    value["canonical_sha256"] = self_sha(value)
    return value


def read(path):
    if path in PASS_A_HISTORICAL_SOURCE_FIXTURES:
        fixture = PASS_A_HISTORICAL_SOURCE_FIXTURES[path]
        raw = (ROOT / fixture).read_bytes()
        if fixture.endswith(".b64"):
            raw = base64.b64decode(raw.strip(), validate=True)
        else:
            raw = raw.replace(b"\r\n", b"\n")
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        require(blob == PASS_A_HISTORICAL_SOURCE_BLOBS[path],
                "pinned D2 predecessor source fixture drift: " + path)
        return raw
    from scripts import audit_app_01a_local_shell as app01a
    if path in app01a.HISTORICAL_RUNTIME_PATHS:
        return app01a.historical_runtime_payload(path)
    if path == "tests/conftest.py":
        from scripts import audit_core_01d_ci_offline_transport_boundary as a2
        a2.authenticate_inventory()
        raw = a2.HISTORICAL_CONFTEST_BYTES
        require(hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
                == a2.HISTORICAL_TEST_BLOBS[path], "historical conftest identity drift")
        return raw
    # V1 describes the merged predecessor, not the unmerged source cutover.
    from scripts.core_01d_historical_source import historical_bytes
    if path in PASS1_V1_BASE_SOURCE_FIXTURES:
        # These immutable V1 inputs are carried as source fixtures so shallow
        # checkouts can reproduce the original census without fetching history.
        # Pass 1's current versions are separately authenticated by status V2.
        fixture, expected_blob, expected_sha = PASS1_V1_BASE_SOURCE_FIXTURES[path]
        inventory_raw = (ROOT / BASE_PATH).read_bytes().replace(b"\r\n", b"\n")
        require(sha(inventory_raw) == BASE_INPUT_SHA, "exact-main base inventory identity drift")
        inventory = strict(inventory_raw)
        require(
            inventory.get("base_main_sha") == BASE
            and inventory.get("canonical_sha256") == self_sha(inventory)
            and inventory.get("files", {}).get(path, {}).get("git_blob_sha1") == expected_blob,
            "pinned Checkpoint E V1 source identity drift: " + path,
        )
        raw = (ROOT / fixture).read_bytes().replace(b"\r\n", b"\n")
        observed_blob = hashlib.sha1(
            b"blob " + str(len(raw)).encode() + b"\0" + raw
        ).hexdigest()
        require(
            observed_blob == expected_blob and sha(raw) == expected_sha,
            "pinned Checkpoint E V1 source fixture drift: " + path,
        )
        return raw
    from scripts import audit_data_01c_restore_portability as d5
    from scripts.core_01d_historical_source import identities
    if path not in identities() and path in d5.snapshot()["sources"]:
        d5.authenticate_workflow()
        return d5.predecessor_source(path)
    return historical_bytes(path)


def strict(raw):
    return roles.strict_json(raw)


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def git_inventory():
    result = {}
    for row in git("ls-tree", "-r", "-z", "HEAD").split(b"\0"):
        if row:
            metadata, path = row.split(b"\t", 1)
            mode, kind, identity = metadata.decode().split()
            require(kind == "blob", "unexpected non-blob tracked entry")
            result[path.decode()] = {"mode": mode, "git_blob_sha1": identity}
    from scripts import audit_data_01c_restore_portability as d5
    d5.authenticate_workflow()
    for path, row in d5.snapshot()["sources"].items():
        require(path in result, "D5 portability predecessor source missing: " + path)
        result[path]["git_blob_sha1"] = row["git_blob_sha1"]
    from scripts import audit_app_01a_local_shell as app01a
    paths, successor = app01a.authenticated_historical_paths()
    for path in paths:
        if path in successor["base_identities"]:
            require(path in result, "APP predecessor path missing: " + path)
            result[path]["git_blob_sha1"] = successor["base_identities"][path]["git_blob_sha1"]
        else:
            result.pop(path, None)
    for path, blob in PASS_A_HISTORICAL_SOURCE_BLOBS.items():
        require(path in result, "Pass-A historical source missing: " + path)
        result[path]["git_blob_sha1"] = blob
    from scripts.core_01d_historical_source import identities
    for path, entry in identities().items():
        result[path]["git_blob_sha1"] = entry["git_blob_sha1"]
    # V1 authenticates historical test sources; current guard sources are
    # independently authenticated before projecting these exact predecessor IDs.
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    a2.authenticate_inventory()
    for path, blob in a2.HISTORICAL_TEST_BLOBS.items():
        require(path in result, "historical test source missing: " + path)
        result[path]["git_blob_sha1"] = blob
    return result


def historical_audit_forward(base):
    before = read(HISTORICAL_AUDIT_FIXTURE)
    identity = hashlib.sha1(b"blob " + str(len(before)).encode() + b"\0" + before).hexdigest()
    require(identity == base["files"][HISTORICAL_AUDIT]["git_blob_sha1"], "historical audit before fixture drift")
    anchor = b'    historical_inventory = b"".join(row for row in rows.splitlines(keepends=True)\n'
    addition = (
        b'    # The immutable remediation checkpoint predates these two additive C4\n'
        b'    # documents. Authenticate their exact sealed identities before excluding\n'
        b'    # them from the historical inventory; every old artifact remains pinned.\n'
        b'    from scripts.audit_checkpoint_e_workflows import verified_additive_artifact_paths\n'
        b'    additive_paths = verified_additive_artifact_paths()\n'
    )
    old = b'                                    if row.split(b"\\t", 1)[1].strip() != RECEIPT_PATH.encode())\n'
    new = (b'                                    if row.split(b"\\t", 1)[1].strip() not in\n'
           b'                                    {RECEIPT_PATH.encode(), *(path.encode() for path in additive_paths)})\n')
    require(before.count(anchor) == before.count(old) == 1, "historical audit forward anchors ambiguous")
    after = before.replace(anchor, addition + anchor).replace(old, new)
    require(read(HISTORICAL_AUDIT) == after, "historical audit change exceeds authenticated additive artifact allowance")
    return before, hashlib.sha1(b"blob " + str(len(after)).encode() + b"\0" + after).hexdigest()


def verified_additive_artifact_paths():
    for path, expected in ((MATRIX_PATH, CHECKPOINT_MATRIX_SHA), (RECEIPT_PATH, CHECKPOINT_RECEIPT_SHA)):
        raw = read(path)
        value = strict(raw)
        require(raw == canonical(value) and value.get("canonical_sha256") == expected == self_sha(value),
                "unreviewed additive C4 artifact identity: " + path)
    from scripts.audit_core_01d_scheduled_shadow_ownership import verified_receipt_path, additive_paths
    verified_receipt_path()
    from scripts.audit_core_01d_retained_workflow_status import audit as audit_retained_status
    retained_status = audit_retained_status()
    require(retained_status.get("result") == "PASS",
            "supplementary retained-workflow status receipt failed authentication")
    from scripts import audit_core_01d_pr145_completed_one_shot_disposition as pr145
    pr145_status = pr145.audit()
    require(pr145_status.get("result") == "PASS",
            "PR145 retained-status and disposition receipts failed authentication")
    from scripts import audit_core_01d_canonical_drive_transfer_completed_history as transfer
    require(transfer.audit().get("result") == "PASS",
            "canonical transfer completed-history receipts failed authentication")
    from scripts import audit_core_01d_historical_retention_acceptance as retention
    from scripts import audit_core_01d_retained_workflow_status_v5 as retained_v5
    from scripts import audit_core_01d_checkpoint_e_completion_v2 as completion
    # The independent audit authenticates the committed evidence chain;
    # retained V5 alone is never completion authority.
    require(completion.audit().get("result") == "PASS",
            "Pass-4 retention and independent completion evidence failed authentication")
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    from scripts import audit_core_01d_checkpoint_e_completion_v3 as completion_v3
    require(a2.audit().get("result") == "PASS",
            "A2 additive offline-boundary receipt failed authentication")
    require(completion_v3.audit().get("result") == "PASS",
            "V3 additive completion overlay failed authentication")
    from scripts import audit_core_01d_historical_warehouse_transfer_authority_b2 as b2
    from scripts import audit_core_01d_checkpoint_e_completion_v5 as completion_v5
    from scripts import audit_core_01d_owner_one_shot_issue_comment_authority_b3 as b3
    from scripts import audit_core_01d_checkpoint_e_completion_v6 as completion_v6
    from scripts import audit_core_01d_sportybet_current_trigger_authority_b4 as b4
    from scripts import audit_core_01d_checkpoint_e_completion_v7 as completion_v7
    from scripts import audit_core_01d_frozen_artifact_replay_authority_b5 as b5
    from scripts import audit_core_01d_checkpoint_e_completion_v8 as completion_v8
    from scripts import audit_core_01d_port02c_trigger_authority_b6 as b6
    from scripts import audit_core_01d_checkpoint_e_completion_v9 as completion_v9
    from scripts import audit_core_01d_win_either_half_trigger_authority_b7 as b7
    from scripts import audit_core_01d_checkpoint_e_completion_v10 as completion_v10
    require(b2.audit().get("result") == "PASS",
            "historical warehouse/transfer authority B2 evidence failed authentication")
    require(completion_v5.audit().get("result") == "PASS",
            "immutable Completion V5 predecessor evidence failed authentication")
    require(b3.authenticate_predecessor_chain()["canonical_sha256"] == b3.COMPLETION_V5_SHA,
            "immutable B2/Completion V5 predecessor evidence failed authentication")
    require(b3.audit().get("result") == "PASS",
            "owner one-shot issue-comment B3 authority evidence failed authentication")
    require(completion_v6.audit().get("result") == "PASS",
            "Completion V6 B3 authority overlay failed authentication")
    require(b4.audit().get("result") == "PASS",
            "current SportyBet trigger authority B4 evidence failed authentication")
    require(completion_v7.audit().get("result") == "PASS",
            "Completion V7 B4 authority overlay failed authentication")
    require(b5.audit().get("result") == "PASS",
            "frozen artifact replay authority B5 evidence failed authentication")
    require(completion_v8.audit().get("result") == "PASS",
            "Completion V8 B5 authority overlay failed authentication")
    require(b6.audit().get("result") == "PASS",
            "PORT-02C trigger authority B6 evidence failed authentication")
    require(completion_v9.audit().get("result") == "PASS",
            "Completion V9 B6 authority overlay failed authentication")
    require(b7.audit().get("result") == "PASS",
            "Win-Either-Half trigger authority B7 evidence failed authentication")
    require(completion_v10.audit().get("result") == "PASS",
            "Completion V10 final authority closure failed authentication")
    from scripts import audit_app_01a_local_shell as app01a
    app01a.authenticated_historical_paths()
    from scripts import audit_data_01a_app_schema_core as data01a
    data01a.authenticate()
    from scripts import audit_data_01b_durable_run_state as data01b
    latest_a2 = a2.authenticate_inventory()
    data01b.authenticate_successor(latest_a2)
    from scripts import audit_data_01c_app_store_complete as data01c
    d5_paths = data01c.authenticate_successor()
    from scripts import audit_data_01c_restore_portability as portability
    portability.audit()
    require(data01c.RECEIPT in d5_paths,
            "D5 source receipt is absent from its authenticated successor set")
    from scripts import audit_run_01a_durable_admission as e1
    e1_paths = e1.authenticate_successor() if latest_a2["generation"] >= 116 else set()
    return (
        MATRIX_PATH,
        RECEIPT_PATH,
        *additive_paths(),
        RETAINED_STATUS_PATH,
        pr145.V3_RECEIPT_PATH,
        pr145.RECEIPT_PATH,
        transfer.v4.RECEIPT_PATH,
        transfer.RECEIPT_PATH,
        retention.RECEIPT_PATH,
        retained_v5.RECEIPT_PATH,
        completion.v1.RECEIPT_PATH,
        completion.review.RECEIPT_PATH,
        completion.RECEIPT_PATH,
        a2.RECEIPT_PATH,
        completion_v3.RECEIPT_PATH,
        b2.SOURCE_INVENTORY_PATH,
        b2.RECEIPT_PATH,
        completion_v5.RECEIPT_PATH,
        b3.SOURCE_INVENTORY_PATH,
        b3.RECEIPT_PATH,
        completion_v6.RECEIPT_PATH,
        a2.inventory_generation_path(5),
        b4.SOURCE_INVENTORY_PATH,
        b4.RECEIPT_PATH,
        completion_v7.RECEIPT_PATH,
        a2.inventory_generation_path(6),
        b5.SOURCE_INVENTORY_PATH,
        b5.RECEIPT_PATH,
        completion_v8.RECEIPT_PATH,
        a2.inventory_generation_path(7),
        b6.SOURCE_INVENTORY_PATH,
        b6.RECEIPT_PATH,
        completion_v9.RECEIPT_PATH,
        a2.inventory_generation_path(8),
        b7.SOURCE_INVENTORY_PATH,
        b7.RECEIPT_PATH,
        completion_v10.RECEIPT_PATH,
        a2.inventory_generation_path(9),
        app01a.RECEIPT,
        data01a.RECEIPT,
        data01b.RECEIPT,
        data01c.RECEIPT,
        "artifacts/product/data_01c_restore_portability_v1.json",
        *(path for path in sorted(e1_paths) if path.startswith("artifacts/")),
    )


def _authenticate_pr119_release_only_workflow_forward(current, before):
    """Allow only transition 14's exact protected-workflow source identity."""
    path = ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
    from scripts import audit_p4_workflow_evolution_ledger as evolution
    from scripts import audit_core_01d_retained_workflow_status_v2 as retained_status_v2

    require(
        tuple(retained_status_v2.SUPPORTING_SOURCE_PATHS) == PASS1_SUPPORTING_SOURCE_PATHS,
        "checkpoint and retained-status V2 supporting-source contracts differ",
    )
    ledger = evolution.validate_current_state()
    require(
        len(ledger["transitions"]) == 14
        and ledger["canonical_sha256"] == evolution.CORE01D_PR119_LEDGER_SHA256
        and ledger["current_workflow_tree_sha1"] == evolution.CORE01D_PR119_WORKFLOW_TREE_SHA1,
        "fresh-holdout forward is not the exact authenticated transition-14 tree/ledger tuple",
    )
    transition = ledger["transitions"][-1]
    observed = current.get(path)
    require(
        transition["transition_id"] == "CORE01D_FRESH_HOLDOUT_PR119_RELEASE_ONLY_BOOTSTRAP_V1"
        and transition["workflow_path"] == path
        and transition["operation"] == "MAINTENANCE_REVISE"
        and transition["phase_id"] == "CORE-01D"
        and transition["canonical_family"] == "PROTECTED_RESEARCH"
        and transition["before"]["git_blob_sha1"] == before["git_blob_sha1"]
        and observed is not None
        and observed["mode"] == before["mode"]
        and observed["git_blob_sha1"] == transition["after"]["git_blob_sha1"],
        "fresh-holdout current source differs from its exact transition-14 identity",
    )
    status = retained_status_v2.audit()
    require(
        status.get("result") == "PASS"
        and status.get("evolution_ledger_sha256") == evolution.CORE01D_PR119_LEDGER_SHA256
        and status.get("workflow_tree_sha1") == evolution.CORE01D_PR119_WORKFLOW_TREE_SHA1,
        "current retained-status V2 did not authenticate the exact transition-14 source",
    )
    supporting = retained_status_v2.build_receipt()["pass1_supporting_source_inventory"]
    require(
        [row["path"] for row in supporting] == list(retained_status_v2.SUPPORTING_SOURCE_PATHS),
        "Pass-1 supporting source inventory path set drift",
    )
    for row in supporting:
        observed_support = current.get(row["path"])
        require(
            observed_support is not None
            and observed_support["git_blob_sha1"] == row["git_blob_sha1"],
            "Pass-1 supporting source differs from its V2 authenticated identity: " + row["path"],
        )
    return {
        "workflow_blob": transition["after"]["git_blob_sha1"],
        "supporting_source_blobs": {
            row["path"]: row["git_blob_sha1"] for row in supporting
        },
    }


def base_input():
    raw = read(BASE_PATH)
    require(sha(raw) == BASE_INPUT_SHA, "exact-main base inventory identity drift")
    value = strict(raw)
    require(value["base_main_sha"] == BASE and value["canonical_sha256"] == self_sha(value), "base input binding drift")
    current = git_inventory()
    _, audit_after = historical_audit_forward(value)
    fresh_workflow_path = ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
    fresh_workflow_after_blob = None
    supporting_source_blobs = {}
    if current.get(fresh_workflow_path) != value["files"].get(fresh_workflow_path):
        forward = _authenticate_pr119_release_only_workflow_forward(
            current, value["files"][fresh_workflow_path]
        )
        fresh_workflow_after_blob = forward["workflow_blob"]
        supporting_source_blobs = forward["supporting_source_blobs"]
    for path, identity in value["files"].items():
        if path == HISTORICAL_AUDIT:
            require(current.get(path) in (identity, {"mode": identity["mode"], "git_blob_sha1": audit_after}), "historical audit forward Git identity differs")
        elif path == fresh_workflow_path and fresh_workflow_after_blob:
            require(
                current.get(path) == {
                    "mode": identity["mode"],
                    "git_blob_sha1": fresh_workflow_after_blob,
                },
                "fresh-holdout workflow differs from its transition-14 identity",
            )
        elif path in supporting_source_blobs:
            require(
                current.get(path) == {
                    "mode": identity["mode"],
                    "git_blob_sha1": supporting_source_blobs[path],
                },
                "Pass-1 supporting source differs from its V2 authenticated identity: " + path,
            )
        elif path in PASS_A_HISTORICAL_SOURCE_FIXTURES:
            require(
                identity == {
                    "mode": "100644",
                    "git_blob_sha1": PASS_A_BASE_SOURCE_BLOBS[path],
                },
                "Pass-A base inventory differs from its exact V1 source identity: " + path,
            )
        else:
            require(current.get(path) == identity, f"immutable base file changed/deleted: {path}")
    # Git can be clean while the working tree has edits. Verify inspected source
    # through Git's declared filters, without normalizing arbitrary evidence.
    hashed = subprocess.run(
        ["git", "-C", str(ROOT), "hash-object", "--stdin-paths"],
        input="".join(json.dumps(path, ensure_ascii=False) + "\n" for path in value["scan_paths"]).encode(),
        capture_output=True, check=True,
    ).stdout.decode().splitlines()
    require(len(hashed) == len(value["scan_paths"]), "worktree filtered hash inventory incomplete")
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    a2.authenticate_inventory()
    from scripts import audit_app_01a_local_shell as app01a
    successor_paths, successor = app01a.authenticated_historical_paths()
    for path, actual in zip(value["scan_paths"], hashed):
        if path in successor_paths and path in successor["base_identities"]:
            actual = successor["base_identities"][path]["git_blob_sha1"]
        if path in PASS_A_HISTORICAL_SOURCE_BLOBS:
            actual = PASS_A_HISTORICAL_SOURCE_BLOBS[path]
        if path in a2.HISTORICAL_TEST_BLOBS:
            actual = a2.HISTORICAL_TEST_BLOBS[path]
        from scripts.core_01d_historical_source import identities
        from scripts import audit_data_01c_restore_portability as d5
        if path in identities() or path in d5.snapshot()["sources"]:
            inspected = read(path)
            actual = hashlib.sha1(b"blob " + str(len(inspected)).encode() + b"\0" + inspected).hexdigest()
        expected_blob = (
            audit_after if path == HISTORICAL_AUDIT
            else fresh_workflow_after_blob if path == fresh_workflow_path and fresh_workflow_after_blob
            else supporting_source_blobs[path] if path in supporting_source_blobs
            else PASS_A_HISTORICAL_SOURCE_BLOBS[path] if path in PASS_A_HISTORICAL_SOURCE_FIXTURES
            else value["files"][path]["git_blob_sha1"]
        )
        require(actual == expected_blob, f"worktree source differs: {path}")
    require(value["workflow_tree_sha1"] == "134cdd8bfa54488770f562c93571e46ac84a8187", "immutable V1 workflow tree changed")
    return value


def history_input():
    raw = read(HISTORY_PATH)
    require(sha(raw) == HISTORY_INPUT_SHA, "captured GitHub history identity drift")
    value = strict(raw)
    require(value["base_main_sha"] == BASE and value["read_only"] is True, "history base/source differs")
    return value["workflow_history"]


def parity_evidence():
    rows = []
    for clock in ("09:00", "22:59", "23:00"):
        now = datetime.fromisoformat(f"2026-10-01T{clock}:00+00:00")
        scheduled = resolve_workflow_request(event_name="schedule", now=now)
        require((scheduled.authority_profile, scheduled.mode, scheduled.target_legs,
                 scheduled.bookie, scheduled.create_share_code, scheduled.place_wager) ==
                ("MAIN", "main_application", 20, "sportybet", False, False), "scheduled MAIN semantics changed")
        for suffix in ("scope=today", "scope=three-day", "dates=20261001", "dates=20261002,20261003"):
            result = comment.resolve_comment("/athena-shadow target=20 " + suffix, now=now)
            representable = clock != "23:00" or suffix == "dates=20261002,20261003"
            require((result.compatibility_status == comment.REPRESENTABLE) is representable, "date-shifting parity claim")
            if representable:
                # Preserve legacy intent for the parity proof. This is parsing,
                # not authority to create a code, and is never executed.
                request = parse_explicit_request(
                    days=",".join(datetime.strptime(day, "%Y%m%d").date().isoformat()
                                  for day in result.legacy_utc_resolved_dates),
                    target_legs=20, profile="shadow", create_share_code=True, now=now,
                )
                require(canonical_json_bytes(request) == result.canonical_request_bytes, "legacy request byte parity differs")
            else:
                require(result.canonical_request_bytes is None and result.canonical_request_sha256 is None, "fabricated canonical request for unrepresentable UTC intent")
            rows.append({"clock_utc": now.isoformat(), "legacy_input": suffix,
                         "status": result.compatibility_status, "legacy_dates": list(result.legacy_utc_resolved_dates),
                         "canonical_request_sha256": result.canonical_request_sha256,
                         "delivery_compatibility_intent": True, "date_shift": False,
                         "execution_authorized_by_test": False})
    return rows


def accepted_evidence():
    raw = (ROOT / ZIP_PATH).read_bytes()
    require(len(raw) == 2915212 and sha(raw) == ZIP_SHA, "accepted LG-A archive identity mismatch")
    with tempfile.TemporaryDirectory(prefix="athena-core01d-offline-") as directory:
        download = Path(directory)
        extract_verified_paths(raw, download)
        root = manifest_root(download)
        manifest_raw = (root / roles.MANIFEST_FILENAME).read_bytes()
        manifest = strict(manifest_raw)
        candidate = roles.Candidate(36860297707, BASE, CANONICAL, 11163921301, "athena-run-36860297707")
        verify_archive_producer_receipt(download, root, manifest_raw, candidate)
        roles.validate_manifest(manifest_raw, root, candidate, current_run_id=0,
                                role_id="PERSISTENT_FIXTURE_IDENTITY_STATE")
        request_sha = manifest["producer"]["request_sha256"]
        runroot = download / "athena-runs" / request_sha
        receipt_raw = (runroot / "athena-run-receipt.json").read_bytes()
        receipt = roles.validate_producer_receipt(receipt_raw, request_sha256=request_sha, head_sha=BASE)
        require(receipt.status == "RESEARCH_SHADOW_PORTFOLIO_READY_WITH_SHORTFALL" and
                receipt.request.create_share_code is False and receipt.request.place_wager is False and
                receipt.share_code_result is None and receipt.evidence["supervisor_returncode"] == 0,
                "accepted no-delivery terminal/worker contradiction")
        inner_raw = (runroot / "current-shadow/current-shadow-all-market-run-receipt.json").read_bytes()
        inner = strict(inner_raw)
        require(inner["status"] == receipt.status and inner["selected_leg_count"] == 9 and inner["shortfall"] == 11,
                "accepted inner/canonical mismatch")
        from domain.current_shadow_sportybet_pc_upcoming_discovery import _verify_manifest_at_root
        source = root / "source-evidence"
        discovery = _verify_manifest_at_root(evidence_root=source / "current-shadow-sportybet-pc-upcoming-discovery")
        require(discovery.canonical_sha256 == inner["source_summary"]["provider_discovery_manifest_sha256"], "accepted discovery source lineage mismatch")
        return {"run_id": candidate.run_id, "exact_head": BASE, "workflow_path": CANONICAL,
                "event": "workflow_dispatch", "attempt": 1, "github_conclusion": "SUCCESS",
                "terminal": receipt.status, "selected": 9, "target": 20, "shortfall": 11,
                "supervisor_returncode": 0, "restore_eligible": True,
                "artifact_id": candidate.artifact_id, "artifact_name": candidate.artifact_name,
                "artifact_size_bytes": len(raw), "github_digest": "sha256:" + ZIP_SHA,
                "local_zip_sha256": sha(raw), "durable_offline_archive": ZIP_PATH,
                "request_sha256": request_sha, "canonical_receipt_file_sha256": sha(receipt_raw),
                "inner_receipt_file_sha256": sha(inner_raw), "manifest_file_sha256": sha(manifest_raw),
                "source_inventory_sha256": next(row["inventory_sha256"] for row in manifest["roles"] if row["role_id"] == "RETAINED_SOURCE_EVIDENCE"),
                "retention": "EXACT_ARCHIVE_RETAINED_OFFLINE_DOES_NOT_DEPEND_ON_30_DAY_ACTIONS_EXPIRY"}


def reachability(path, name, artifact_names, texts):
    identifiers = sorted({path, Path(path).name, name, *artifact_names})
    matches = []
    for source, text in texts.items():
        if source == path:
            continue
        lines = []
        for number, line in enumerate(text.splitlines(), 1):
            hits = [term for term in identifiers if term and term in line]
            if hits:
                lines.append({"line": number, "identifiers": hits})
        if lines:
            matches.append({"path": source, "matches": lines,
                            "classification": "DOCS" if source.startswith("docs/") else
                            "TEST" if source.startswith("tests/") else "SOURCE_OR_WORKFLOW"})
    return {"scan_basis": "EXACT_BASE_TRACKED_SOURCE_NOT_ZERO_GREP_RETIREMENT_PROOF",
            "matches": matches, "dynamic_subprocess_reachability": "NOT_PROVEN_FOR_RETIREMENT",
            "retirement_reachability_pass": False}


def build_matrix(base, history):
    texts = {path: read(path).decode("utf-8") for path in base["scan_paths"]}
    texts[HISTORICAL_AUDIT] = read(HISTORICAL_AUDIT_FIXTURE).decode("utf-8")
    old = strict(read("artifacts/architecture/p4_3_workflow_capability_matrix_v1.json"))
    old_rows = {row["workflow_path"]: row for row in old["workflow_rows"]}
    rows = []
    for path in sorted(p for p in base["files"] if p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml"))):
        raw = read(path)
        doc = yaml.load(raw, Loader=yaml.BaseLoader)
        require(type(doc) is dict and type(doc.get("on")) is dict, f"unsupported trigger shape: {path}")
        name = doc.get("name", Path(path).stem)
        steps = census._steps(doc)
        uploads, downloads = census._artifacts(steps)
        artifacts = sorted({row["name"] for row in uploads if row["name"]})
        historical = old_rows.get(path, {})
        family = historical.get("successor_family", "RETAIN_PENDING_AUDIT")
        purpose = historical.get("purpose", "Newer workflow; explicit retained capability pending full successor proof")
        if path == ".github/workflows/athena-ingest.yml":
            family, purpose = "ATHENA_INGEST", "Canonical reviewed ingest transport (not a SHADOW run successor)"
        if path == ".github/workflows/native-runtime-tests.yml":
            family, purpose = "TESTS", "Offline native Windows runtime validation"
        status = "CANONICAL_SUPPORTED" if path in {CANONICAL, ".github/workflows/tests.yml", ".github/workflows/athena-ingest.yml", ".github/workflows/native-runtime-tests.yml"} else "EXPLICIT_RETAINED_COMPATIBILITY"
        reason = "Canonical family retained unchanged" if status == "CANONICAL_SUPPORTED" else (
            "Unique protected research/diagnostic/history/bridge capability; no exact successor or full retirement proof in C4"
        )
        if historical.get("date_hardcoded"):
            status = "HISTORICAL_ONLY"
            reason = "Frozen dated evidence workflow, not a supported current football run; dependent evidence consumers and retention require individual retirement proof"
        refs = reachability(path, name, artifacts, texts)
        surfaces = []
        for trigger, detail in sorted(doc["on"].items()):
            canonical_run = path == CANONICAL
            shadow = path == SHADOW
            main = canonical_run and trigger == "schedule"
            surface = {
                "trigger_kind": trigger, "event_details": detail,
                "supported_status": status, "purpose": purpose,
                "authority_profile": "MAIN" if main else "MAIN_OR_SHADOW_EXPLICIT" if canonical_run else "SHADOW" if shadow else "UNKNOWN_NOT_RECLASSIFIED_BY_CENSUS",
                "acquisition_authority": False if main else "EXPLICIT_SHADOW_ONLY" if canonical_run else True if shadow else "UNKNOWN",
                "delivery_authority": False if main else "EXPLICIT_CREATE_SHARE_CODE_INTENT" if canonical_run else "LEGACY_IMPLICIT_TRUE_RETAINED_NOT_EXECUTED_IN_C4" if shadow else "UNKNOWN",
                "wager_authority": False if canonical_run or shadow else "UNKNOWN",
                "request_parser_owner": "services/athena_run_workflow_request.py" if canonical_run else "services/athena_shadow_issue_comment_compatibility.py" if shadow and trigger == "issue_comment" else path,
                "date_policy_owner": "services/athena_run_request_parser.py" if canonical_run else "domain/current_shadow_fixture_date_request.py" if shadow else "WORKFLOW_SPECIFIC_NOT_MIGRATED",
                "date_timezone_semantics": "Africa/Lagos concrete date frozen once" if canonical_run else "UTC YYYYMMDD rolling today..today+6; no shift" if shadow else "WORKFLOW_SPECIFIC_NOT_PROVEN_EQUIVALENT",
                "target_semantics": "1..50 maximum desired legs; truthful shortfall; schedule=20" if canonical_run or shadow else "WORKFLOW_SPECIFIC",
                "provider_bookie_semantics": "sportybet" if canonical_run or shadow else "WORKFLOW_SPECIFIC",
                "notification_behavior": "NONE" if canonical_run else "EXPLICIT_RETAINED_SECONDARY_NON_AUTHORITATIVE" if shadow else "WORKFLOW_SPECIFIC_UNCHANGED",
                "canonical_successor_path": CANONICAL if canonical_run or shadow else historical.get("successor_workflow_path"),
                "successor_request_parity": "CURRENT_CANONICAL_OWNER" if canonical_run else "BLOCKED_UTC_DATE_AND_DELIVERY_INTENT" if shadow else "NOT_PROVEN",
                "successor_authority_parity": "CURRENT_CANONICAL_OWNER" if canonical_run else "NOT_PROVEN_NO_AUTHORITY_DELTA_CLAIM",
                "successor_artifact_parity": "CANONICAL_ROLES_VERIFIED_C2_AND_ACCEPTED_LGA" if canonical_run else "LEGACY_READ_ONLY_COMPATIBILITY_NOT_CUTOVER" if shadow else "NOT_PROVEN",
                "successor_notification_parity": "NO_CANONICAL_NOTIFICATION" if canonical_run else "RETAINED_NOT_MIGRATED",
                "retained_reason": reason, "deletion_eligible": False,
                "deletion_blockers": ["FULL_14_POINT_RETIREMENT_PROOF_NOT_ESTABLISHED", "DYNAMIC_REACHABILITY_AND_DURABLE_ARTIFACT_RETENTION_NOT_PROVEN"],
            }
            if shadow and trigger == "schedule":
                surface["successor_request_parity"] = "09Z_DATE_PARITY_ONLY_NO_REVIEWED_MULTI_PROFILE_SCHEDULE"
                surface["retained_reason"] = "Preserve MAIN-only canonical schedule and single-request/run artifact identity; multi-profile schedule/archive ownership needs explicit reviewed design; legacy implicit delivery is not analysis-only byte parity"
            if shadow and trigger == "issue_comment":
                surface["retained_reason"] = "Exact #276/owner grammars retained; UTC 23Z requests can be unrepresentable; legacy true delivery intent cannot silently become false; no implicit hybrid execution"
            surfaces.append(surface)
        rows.append({
            "workflow_path": path, "workflow_name": name, "workflow_family": family,
            "git_blob_sha1": base["files"][path]["git_blob_sha1"], "source_sha256": sha(raw),
            "supported_status": status, "purpose": purpose, "trigger_surfaces": surfaces,
            "artifact_names": artifacts, "artifact_uploads": uploads, "artifact_downloads": downloads,
            "canonical_artifact_roles": list(roles.ROLE_IDS) if path == CANONICAL else [],
            "historical_restore_role": "PERSISTENT_FIXTURE_IDENTITY_STATE" if path == SHADOW else "DURABLE_HISTORY_PRIME" if path.endswith("current-shadow-history-cache-prime.yml") else None,
            "supported_current_runtime_root": path == CANONICAL or historical.get("supported_runtime_root", False),
            "date_hardcoded_historical_evidence": historical.get("date_hardcoded", False),
            "current_callers_and_references": refs,
            "last_relevant_historical_runs": history[path],
            "retained_reason": reason, "deletion_eligible": False,
            "rollback": {"commit": BASE, "path": path, **base["files"][path]},
            "evidence_references": historical.get("evidence_references", []) + [BASE_PATH, HISTORY_PATH],
        })
    return seal({"schema_version": 1, "policy_id": MATRIX_POLICY_ID, "base_main_sha": BASE,
                 "source_scan_input_sha256": BASE_INPUT_SHA, "history_input_sha256": HISTORY_INPUT_SHA,
                 "workflow_count": len(rows), "trigger_surface_count": sum(len(row["trigger_surfaces"]) for row in rows),
                 "workflow_rows": rows, "retired_in_this_pr": [],
                 "unknown_means_not_proven": True, "retirement_authority_from_matrix": False})


def checkpoint_status(criteria):
    require(type(criteria) is dict and criteria and all(type(v) is bool for v in criteria.values()), "criteria must be explicit booleans")
    blockers = sorted(key for key, value in criteria.items() if not value)
    return ("COMPLETE" if not blockers else "INCOMPLETE"), blockers


def validate_retirement_row(row):
    require(row.get("deletion_eligible") is True, "retirement row not eligible")
    require(row.get("last_relevant_historical_runs", {}).get("last_successful"), "missing last successful run evidence")
    require(row.get("rollback"), "missing rollback identity")
    checklist = row.get("retirement_checklist", {})
    require(set(checklist) == set(range(1, 15)) and all(v is True for v in checklist.values()), "full 14-point retirement checklist required")
    require(row.get("supported_callers_remaining") == [] and row.get("required_restore_dependencies") == [], "retired workflow still reachable/required")


def validate_documents(matrix, receipt):
    require(matrix.get("canonical_sha256") == self_sha(matrix) and receipt.get("canonical_sha256") == self_sha(receipt), "matrix/receipt self hash mismatch")
    rows = matrix["workflow_rows"]
    paths = [row["workflow_path"] for row in rows]
    live = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / ".github/workflows").iterdir() if path.suffix in {".yml", ".yaml"})
    require(paths == live and len(set(paths)) == len(paths) == matrix["workflow_count"], "live workflow inventory count/coverage mismatch")
    for row in rows:
        doc = yaml.load(read(row["workflow_path"]), Loader=yaml.BaseLoader)
        surfaces = row["trigger_surfaces"]
        require([surface["trigger_kind"] for surface in surfaces] == sorted(doc["on"]), "trigger-specific row coverage mismatch")
        require(row["supported_status"] in ALLOWED_STATUS, "workflow lacks successor/retained status")
        for surface in surfaces:
            require(surface["supported_status"] in ALLOWED_STATUS and surface["retained_reason"], "supported surface missing exact retained/successor status")
            require(surface["deletion_eligible"] is False, "unsupported deletion eligibility claim")
    require(sum(len(row["trigger_surfaces"]) for row in rows) == matrix["trigger_surface_count"], "trigger count mismatch")
    require(not any(row["supported_current_runtime_root"] and row["date_hardcoded_historical_evidence"] for row in rows),
            "supported current runtime depends on date-hardcoded workflow")
    status, blockers = checkpoint_status(receipt["checkpoint_criteria"])
    require(receipt["checkpoint_e_status"] == receipt["p4_4_status"] == status and receipt["remaining_blocker_ids"] == blockers, "Checkpoint E COMPLETE with false mandatory criterion")
    require(receipt["workflow_matrix_sha256"] == matrix["canonical_sha256"], "matrix receipt binding mismatch")
    require(receipt["retired_workflows"] == matrix["retired_in_this_pr"] == [], "retirement not proven in this checkpoint")
    accepted = receipt["accepted_lg_a"]
    require((accepted["run_id"], accepted["exact_head"], accepted["artifact_id"], accepted["artifact_name"], accepted["local_zip_sha256"], accepted["attempt"], accepted["terminal"]) ==
            (36860297707, BASE, 11163921301, "athena-run-36860297707", ZIP_SHA, 1, "RESEARCH_SHADOW_PORTFOLIO_READY_WITH_SHORTFALL"), "accepted LG-A run/head/artifact mismatch")
    require(receipt["historical_failed_lg_a"]["restore_eligible"] is False and
            receipt["historical_failed_lg_a"]["disposition"] == "IMMUTABLE_FAILED_NON_RETRYABLE", "failed producer relabeled eligible/successful")
    require(receipt["issue_comment_disposition"]["grammars"] == [comment.SCOPE_GRAMMAR, comment.EXPLICIT_DATES_GRAMMAR] and
            receipt["issue_comment_disposition"]["issue"] == 276 and
            receipt["issue_comment_disposition"]["owner_guard"] == "github.repository_owner", "issue-comment grammar/admission drift")
    require(receipt["notification_disposition"]["legacy"] == "EXPLICIT_RETAINED_SECONDARY_NON_AUTHORITATIVE" and
            receipt["notification_disposition"]["security_integrity_failure"] == "FAIL_CLOSED" and
            receipt["notification_disposition"]["ordinary_transport_failure"] == "EMAIL_FAILED_WARNING_EXIT_ZERO", "notification authority/failure drift")
    require(all(case["date_shift"] is False for case in receipt["date_schedule_disposition"]["parity_evidence"]), "date-shifting parity claim")
    require(receipt["checkpoint_criteria"]["scheduled_shadow_canonical_ownership_proven_preserving_main"] is False,
            "no reviewed multi-profile scheduled SHADOW implementation exists")
    unknown = any(surface["acquisition_authority"] == "UNKNOWN" for row in rows for surface in row["trigger_surfaces"])
    require(receipt["checkpoint_criteria"]["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is (not unknown), "unknown authority treated as proven")
    require(all(value == 0 and type(value) is int for value in receipt["live_side_effect_counts"].values()) and
            all(value == 0 and type(value) is int for value in receipt["semantic_delta"].values()), "live/semantic authority expansion")


def expected_documents():
    base, history = base_input(), history_input()
    require(set(history) == set(path for path in base["files"] if path.startswith(".github/workflows/") and path.endswith(".yml")), "history capture coverage differs")
    matrix = build_matrix(base, history)
    accepted = accepted_evidence()
    accepted_history = history[CANONICAL]["last_successful"]
    require((accepted_history["id"], accepted_history["head_sha"], accepted_history["event"],
             accepted_history["run_attempt"], accepted_history["conclusion"]) ==
            (36860297707, BASE, "workflow_dispatch", 1, "success"), "accepted captured GitHub metadata contradicts archive anchor")
    parity = parity_evidence()
    ledger = strict(read("artifacts/architecture/p4_workflow_evolution_ledger_v1.json"))
    require(len(ledger["transitions"]) == 11 and ledger["transitions"][-1]["transition_id"] == "CORE01C_CURRENT_SHADOW_COMPATIBILITY_THIN_V1", "eleven-transition historical prefix changed")
    unknown = [row["workflow_path"] + "#" + surface["trigger_kind"] for row in matrix["workflow_rows"] for surface in row["trigger_surfaces"] if surface["acquisition_authority"] == "UNKNOWN"]
    criteria = {
        "canonical_workflow_family_exists": True, "all_live_workflows_and_triggers_enumerated": True,
        "every_surface_has_successor_or_explicit_retained_disposition": True,
        "canonical_artifact_roles_and_failed_producer_guard_preserved": True,
        "notification_explicit_and_non_authoritative": True,
        "retirement_requires_complete_evidence_no_deletions": True,
        "no_supported_current_run_depends_on_date_hardcoded_workflow": True,
        "historical_sources_and_evolution_prefix_preserved": True,
        "clean_successor_gate_satisfied": True,
        "scheduled_shadow_canonical_ownership_proven_preserving_main": False,
        "all_retained_workflow_authority_and_dynamic_reachability_review_complete": False,
    }
    status, blockers = checkpoint_status(criteria)
    receipt = seal({
        "schema_version": 1, "policy_id": POLICY_ID, "repository": "Thabearr/ATHENA", "master_issue": 337,
        "exact_base_sha": BASE, "exact_final_head_derivation": "git rev-parse HEAD in audit output; no self-referential commit SHA in receipt",
        "source_review_counter_while_open": "0/5", "source_review_counter_if_owner_merges": "1/5",
        "mandatory_reread_complete_at_authorization": True, "owner_authorization": "CORE_01D_OFFLINE_MIGRATION_PROOF_AND_EVIDENCE_BACKED_RETIREMENT_ONLY_NO_MERGE",
        "governing_sources": {path: base["files"][path] for path in base["files"] if path in {
            "artifacts/architecture/core_01_schedule_date_disposition_v1.json", "artifacts/architecture/core_01b_canonical_artifact_ancestry_v1.json",
            "artifacts/architecture/core_01c_notification_comment_compatibility_v1.json", "artifacts/architecture/lg_a_worker_launch_failure_remediation_v1.json",
            "artifacts/architecture/p4_4h_current_shadow_canonical_run_migration_review_v1.json", "artifacts/architecture/p4_4m_athena_run_pc_upcoming_evidence_preservation_v1.json",
            "artifacts/product/product_baseline_v1.json", "artifacts/architecture/runtime-reachability-v1.json",
            "artifacts/architecture/repository-architecture-inventory-v1.json"}},
        "predecessor_receipt_identities": {
            path: {"policy_id": strict(read(path))["policy_id"],
                   "canonical_sha256": strict(read(path))["canonical_sha256"],
                   "source_sha256": sha(read(path))}
            for path in ("artifacts/architecture/core_01_schedule_date_disposition_v1.json",
                         "artifacts/architecture/core_01b_canonical_artifact_ancestry_v1.json",
                         "artifacts/architecture/core_01c_notification_comment_compatibility_v1.json",
                         "artifacts/architecture/lg_a_worker_launch_failure_remediation_v1.json")},
        "accepted_lg_a": accepted,
        "historical_failed_lg_a": {"run_id": 36846297806, "exact_head": "426f36e60ebb421af003ed3154c4da48007d674a", "terminal": "EXECUTOR_UNAVAILABLE", "disposition": "IMMUTABLE_FAILED_NON_RETRYABLE", "restore_eligible": False, "old_true_manifest_preserved": True},
        "workflow_matrix_policy_id": MATRIX_POLICY_ID, "workflow_matrix_path": MATRIX_PATH, "workflow_matrix_sha256": matrix["canonical_sha256"],
        "before_workflow_count": len(matrix["workflow_rows"]), "after_workflow_count": len(matrix["workflow_rows"]),
        "before_after_workflow_inventory": [{"path": row["workflow_path"], "before": row["git_blob_sha1"], "after": row["git_blob_sha1"]} for row in matrix["workflow_rows"]],
        "trigger_by_trigger_dispositions": [{"workflow_path": row["workflow_path"], "trigger_kind": surface["trigger_kind"], "status": surface["supported_status"], "reason": surface["retained_reason"]} for row in matrix["workflow_rows"] for surface in row["trigger_surfaces"]],
        "migrated_callers": [], "retired_workflows": [], "workflow_yaml_delta": 0,
        "evolution_disposition": "NO_INVENTORY_OR_OWNERSHIP_CHANGE_NO_C4_TRANSITION_REQUIRED", "evolution_transition_count": 11,
        "historical_audit_forward": {"path": HISTORICAL_AUDIT, "before_fixture": HISTORICAL_AUDIT_FIXTURE,
            "before_git_blob_sha1": base["files"][HISTORICAL_AUDIT]["git_blob_sha1"],
            "after_git_blob_sha1": historical_audit_forward(base)[1],
            "scope": "AUTHENTICATE_EXACT_TWO_ADDITIVE_C4_ARTIFACTS_BEFORE_HISTORICAL_INVENTORY_EXCLUSION_NO_RECEIPT_REWRITE"},
        "evolution_ledger_sha256": ledger["canonical_sha256"], "historical_retired_count": 3,
        "date_schedule_disposition": {"canonical_main": "UNCHANGED_09Z_MAIN_NO_DELIVERY", "legacy_shadow": "EXPLICIT_RETAINED_09Z_SHADOW_NOT_MIGRATED", "parity_evidence": parity,
            "blocker": "MAIN_ONLY_RESOLVER_AND_ONE_RUN_ONE_REQUEST_ARTIFACT_IDENTITY_HAVE_NO_REVIEWED_MULTI_PROFILE_SCHEDULE_DESIGN",
            "clearance": "Review explicit same-cron MAIN+analysis-only SHADOW scheduling, concurrency, durable request and unique archive/producer ownership; prove offline without repurposing MAIN"},
        "manual_dispatch_disposition": "RETAINED_UTC_DATE_AND_LEGACY_TRUE_DELIVERY_INTENT_NO_FALSE_PARITY_CLAIM",
        "issue_comment_disposition": {"status": comment.DISPOSITION, "grammars": [comment.SCOPE_GRAMMAR, comment.EXPLICIT_DATES_GRAMMAR], "issue": 276, "owner_guard": "github.repository_owner", "unrepresentable_dates": "NO_CANONICAL_BYTES_NO_DATE_SHIFT", "implicit_hybrid_execution": False},
        "notification_disposition": {"legacy": "EXPLICIT_RETAINED_SECONDARY_NON_AUTHORITATIVE", "unconfigured": "EMAIL_SKIPPED_UNCONFIGURED", "ordinary_transport_failure": "EMAIL_FAILED_WARNING_EXIT_ZERO", "security_integrity_failure": "FAIL_CLOSED", "canonical": "NO_TRANSPORT", "desktop": "NOT_ENABLED_PENDING_RECIPIENT_CONSENT_TRANSPORT_LIFECYCLE_REVIEW"},
        "artifact_role_disposition": {"roles": list(roles.ROLE_IDS), "authority": "CANONICAL_ROLE_FIRST", "legacy_producer_names": "READ_ONLY_COMPATIBILITY_PROVENANCE_UNCHANGED", "fixed_bootstrap": roles.BOOTSTRAP_SHA256,
            "accepted_archive_retention": accepted["retention"], "legacy_retirement_retention": "NOT_PROVEN_NO_LEGACY_PRODUCER_RETIRED"},
        "reachability_result": "BASE_STATIC_AND_NAMED_DYNAMIC_REFERENCES_CAPTURED_RETIREMENT_REACHABILITY_NOT_PROVEN",
        "unknown_authority_surfaces": unknown,
        "historical_restore_replay": "ACCEPTED_ARCHIVE_VERIFIED_OFFLINE_C2_REMEDIATION_REGRESSIONS_REQUIRED_IN_VALIDATION_REPORT",
        "checkpoint_criteria": criteria, "checkpoint_e_status": status, "p4_4_status": status,
        "remaining_blocker_ids": blockers,
        "blocker_clearance": {"all_retained_workflow_authority_and_dynamic_reachability_review_complete": "Review each exact unknown_authority_surfaces row, dynamic caller chains, unique evidence and durable artifact retention before any candidate deletion. Static absence and CI success do not prove retirement."},
        "rollback": "No operational cutover to roll back; exact original files retained at base source identities",
        "live_side_effect_counts": dict.fromkeys(("provider", "live_run", "dispatch", "retry", "share_code_create", "share_code_reload", "delivery", "email", "login", "cookies", "wallet", "stake", "wager"), 0),
        "semantic_delta": dict.fromkeys(("model", "probability", "price_all", "router", "portfolio", "provider_market", "share_code", "authority"), 0),
    })
    validate_documents(matrix, receipt)
    return matrix, receipt


def audit():
    matrix, receipt = expected_documents()
    require(strict(read(MATRIX_PATH)) == matrix, "committed capability matrix differs from source-derived evidence")
    require(strict(read(RECEIPT_PATH)) == receipt, "committed Checkpoint-E receipt differs from independent evidence")
    evolution.validate_current_state()
    from scripts.audit_core_01d_scheduled_shadow_ownership import audit_forward_checkpoint
    forward = audit_forward_checkpoint()
    from scripts import audit_core_01d_checkpoint_e_completion_v10 as completion
    from scripts import audit_core_01d_checkpoint_e_completion_v2 as historical_completion
    current = completion.audit()
    completion_value = strict((ROOT / completion.RECEIPT_PATH).read_bytes())
    return {"result": "PASS", "checkpoint_e": current["checkpoint_e"], "p4_4": current["p4_4"],
            "policy_id": forward["policy_id"], "receipt_sha256": forward["canonical_sha256"],
            "matrix_sha256": forward["workflow_matrix_sha256"], "exact_head": git("rev-parse", "HEAD").decode().strip(),
            "workflow_count": forward["live_workflow_count"], "trigger_surface_count": forward["trigger_surface_count"],
            "historical_v1_receipt_sha256": receipt["canonical_sha256"], "historical_v1_matrix_sha256": matrix["canonical_sha256"],
            "historical_v1_trigger_surface_count": matrix["trigger_surface_count"],
            "blockers": current["remaining_blockers"], "live_side_effect_counts": receipt["live_side_effect_counts"],
            "current_retained_status_sha256": completion_value["retained_v5"]["canonical_sha256"],
            "current_completion_receipt_sha256": current["receipt_sha256"],
            "historical_completion_v1_receipt_sha256": historical_completion.review.COMPLETION_V1_SHA,
            "historical_completion_v2_receipt_sha256": completion_value["predecessor_completion_v2"]["canonical_sha256"],
            "current_a2_authority_review_sha256": completion_value["a2_review"]["canonical_sha256"],
            "current_authority_review_sha256": completion_value["pass_a_review"]["canonical_sha256"],
            "remaining_unreviewed_surface_count": current["remaining_unreviewed_surface_count"],
            "current_live_missing_artifact_relation_count": completion_value["live_missing_artifact_relation_count"],
            "historical_v1_checkpoint_e_status": receipt["checkpoint_e_status"],
            "historical_forward_v2_checkpoint_e_status": forward["checkpoint_e_status"],
            "terminal": current["terminal"],
            "forward_matrix_sha256": forward["workflow_matrix_sha256"], "forward_receipt_sha256": forward["canonical_sha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seal-base", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.seal_base:
        require(git("rev-parse", "HEAD").decode().strip() == BASE, "base capture must be on exact authorized main")
        files = git_inventory()
        scan = sorted(path for path in files if path.endswith((".py", ".md", ".yml", ".yaml", ".sh", ".ps1", ".cmd", ".bat")) and not path.startswith(("tests/fixtures/", ".venv/", ".cache/")))
        value = seal({"base_main_sha": BASE, "files": files, "scan_paths": scan,
                      "workflow_tree_sha1": git("rev-parse", "HEAD:.github/workflows").decode().strip()})
        (ROOT / BASE_PATH).write_bytes(canonical(value))
        print(json.dumps({"base_input_sha256": sha(canonical(value)), "history_input_sha256": sha(read(HISTORY_PATH)), "base_file_count": len(files)}))
    elif args.write:
        matrix, receipt = expected_documents()
        for path, value in ((MATRIX_PATH, matrix), (RECEIPT_PATH, receipt)):
            (ROOT / path).write_bytes(canonical(value))
        print(json.dumps({"matrix_sha256": matrix["canonical_sha256"], "receipt_sha256": receipt["canonical_sha256"]}))
    else:
        print(json.dumps(audit(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
