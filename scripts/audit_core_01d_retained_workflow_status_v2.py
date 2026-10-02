"""Source-derived current CORE-01D retained-workflow status supplement."""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import yaml

from scripts import audit_core_01d_retained_workflow_status as v1
from scripts import audit_p4_workflow_evolution_ledger as evolution
from scripts import restore_fotmob_pr119_bootstrap_release as bootstrap
from services import athena_artifact_role_resolver as roles


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "ATHENA_CORE_01D_RETAINED_WORKFLOW_STATUS_V2"
RECEIPT_PATH = "artifacts/architecture/core_01d_retained_workflow_status_v2.json"
V1_RECEIPT_PATH = "artifacts/architecture/core_01d_retained_workflow_status_v1.json"
V1_RECEIPT_SHA256 = "267fae49a33137c44951c8b0e7499dfda8713e99adbf73e977129bf279081837"
BASE_MAIN_SHA = "74ce7a2c7a6fc9fff2335587af70e0aa5aeaa55f"
BASE_TREE_SHA = "bdb8fdc192f51ed89c23bed94afcbc513f54a77a"
PREDECESSOR_WORKFLOW_TREE_SHA1 = "9060b6fb263febc45332a7cf9c9da8448284b471"
PREDECESSOR_LEDGER_SHA256 = "b582a5ba8a31ddfba94324f8869dd253460dcc01102ef356327a3337275b8335"
FRESH_WORKFLOW = ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
TRANSITION_ID = "CORE01D_FRESH_HOLDOUT_PR119_RELEASE_ONLY_BOOTSTRAP_V1"
HISTORICAL_ARTIFACT_ID = 9249856559
PAYLOAD_FIXTURE = "tests/fixtures/core_01b_artifact_roles/pr119-bootstrap.ndjson.gz"
RELEASE_METADATA_FIXTURE = (
    "tests/fixtures/core_01b_artifact_roles/pr119-bootstrap-release-metadata.json"
)
SUPPORTING_SOURCE_PATHS = (
    ".github/workflows/audit-fotmob-utc-native-xg-fresh-holdout-lineage.yml",
    ".github/workflows/bridge-fotmob-fresh-holdout-continuity-receipts.yml",
    ".github/workflows/watch-fotmob-fresh-holdout-scheduler-liveness.yml",
    "docs/fotmob_utc_native_expected_goals_fresh_holdout_activation_runner.md",
    "docs/fotmob_utc_native_expected_goals_fresh_holdout_pr119_bootstrap_recovery.md",
    "domain/current_fotmob_latest_durable_fresh_history.py",
    "scripts/audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection.py",
    "tests/test_fotmob_fresh_holdout_actions_lineage_audit_pr175_projection.py",
    "tests/test_fotmob_fresh_holdout_continuity_workflow.py",
    "tests/test_fotmob_fresh_holdout_pr119_bootstrap_recovery.py",
    "tests/test_fotmob_utc_native_expected_goals_fresh_holdout_activation_runner.py",
    "tests/test_fresh_holdout_release_visibility_race_hotfix.py",
)
PAYLOAD_FIXTURE_SHA256 = "d596baef519ef1ac3ad459b0f49f4acf58557d416c549c159f3bd30d13b15ad0"
HISTORICAL_BLOCKER = "PROTECTED_FRESH_HOLDOUT_PR119_EXACT_FALLBACK_NOT_DURABLY_RECOVERED"
REMAINING_BLOCKER_IDS = (
    "OWNER_GATED_PR145_FEATURE_EVIDENCE_NOT_DURABLY_RECOVERED",
    "CANONICAL_HISTORY_TRANSFER_SOURCE_NOT_FULLY_DURABLE",
    "HISTORICAL_REPLAY_ARCHIVES_UNAVAILABLE",
)


class RetainedWorkflowStatusV2Error(AssertionError):
    """Raised when the current source or V2 receipt drifts."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RetainedWorkflowStatusV2Error(message)


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def seal(value: dict) -> dict:
    value["canonical_sha256"] = sha256(
        canonical_bytes({key: item for key, item in value.items() if key != "canonical_sha256"})
    )
    return value


def _git(*args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    if result.returncode:
        raise RetainedWorkflowStatusV2Error(
            f"git {' '.join(args)} failed: {result.stderr.decode('utf-8', 'replace')}"
        )
    return result.stdout


def _head_blob(path: str) -> bytes:
    return _git("show", f"HEAD:{path}")


def _require_head_file_identity(path: str, raw: bytes) -> None:
    filtered_blob = subprocess.run(
        ["git", "hash-object", f"--path={path}", "--stdin"],
        cwd=ROOT,
        input=raw,
        capture_output=True,
        check=True,
    ).stdout.decode("ascii").strip()
    head_blob = _git("rev-parse", f"HEAD:{path}").decode("ascii").strip()
    require(filtered_blob == head_blob, f"source-controlled fixture differs from HEAD: {path}")


def _head_workflow_paths() -> list[str]:
    paths = [
        item.decode("utf-8")
        for item in _git(
            "ls-tree", "-r", "-z", "--name-only", "HEAD", "--", ".github/workflows"
        ).split(b"\0")
        if item
    ]
    return sorted(path for path in paths if path.endswith((".yml", ".yaml")))


def _read_v1() -> dict:
    raw = (ROOT / V1_RECEIPT_PATH).read_bytes()
    value = roles.strict_json(raw)
    require(raw.replace(b"\r\n", b"\n") == canonical_bytes(value),
            "immutable retained-status V1 is not canonical after repository line-ending normalization")
    require(
        value.get("canonical_sha256") == V1_RECEIPT_SHA256
        and v1.self_sha(value) == V1_RECEIPT_SHA256,
        "immutable retained-status V1 identity drift",
    )
    require(value.get("policy_id") == "ATHENA_CORE_01D_RETAINED_WORKFLOW_STATUS_V1",
            "retained-status V1 policy identity drift")
    return value


def _current_workflows() -> tuple[list[str], dict[str, bytes], int]:
    paths = _head_workflow_paths()
    sources = {path: _head_blob(path) for path in paths}
    trigger_count = 0
    for path, raw in sources.items():
        document = yaml.load(raw, Loader=yaml.BaseLoader)
        require(type(document) is dict and type(document.get("on")) is dict,
                f"workflow trigger document is malformed: {path}")
        trigger_count += len(document["on"])
    require(len(paths) == 39, f"current workflow count drift: {len(paths)}")
    require(trigger_count == 57, f"current trigger-surface count drift: {trigger_count}")
    return paths, sources, trigger_count


def _supporting_source_inventory() -> list[dict[str, str]]:
    rows = []
    for path in SUPPORTING_SOURCE_PATHS:
        working_tree_raw = (ROOT / path).read_bytes()
        _require_head_file_identity(path, working_tree_raw)
        raw = _head_blob(path)
        blob = _git("rev-parse", f"HEAD:{path}").decode("ascii").strip()
        identity = roles.sha(raw)
        require(
            evolution.source_identity(raw)
            == {"git_blob_sha1": blob, "source_sha256": identity},
            f"Pass-1 supporting source identity differs from HEAD: {path}",
        )
        rows.append({"path": path, "git_blob_sha1": blob, "source_sha256": identity})
    return rows


def _current_relations(
    predecessor: dict,
    paths: list[str],
    sources: dict[str, bytes],
) -> tuple[list[dict], list[dict], dict]:
    previous_rows = predecessor["retained_status_rows"]
    require(len(previous_rows) == 17, "V1 relationship inventory identity drift")
    workflow_path_set = set(paths)
    spec_by_key = {
        (
            spec["artifact_id"],
            spec["workflow_path"],
            spec["event"],
            spec["qualifier"],
        ): spec
        for spec in v1.RELATION_SPECS
    }
    current_rows: list[dict] = []
    removed: list[dict] = []
    current_pairs: set[tuple[int, str]] = set()
    matching_lines_by_artifact = {artifact_id: 0 for artifact_id in v1.ARTIFACT_IDS}
    workflow_edges: list[dict] = []

    for row in previous_rows:
        artifact_id = row["artifact_id"]
        path = row["workflow_path"]
        require(path in workflow_path_set, f"retained consumer workflow missing: {path}")
        raw = sources[path]
        text = raw.decode("utf-8")
        token = str(artifact_id).encode("ascii")
        lines = raw.splitlines()
        line_numbers = [index for index, line in enumerate(lines, 1) if token in line]
        key = (artifact_id, path, row["event"], row["qualifier"])

        if artifact_id == HISTORICAL_ARTIFACT_ID and path == FRESH_WORKFLOW:
            require(not line_numbers,
                    "historical artifact 924 remains referenced by the current fresh-holdout workflow")
            document = yaml.load(raw, Loader=yaml.BaseLoader)
            require(row["event"] in document["on"],
                    "fresh-holdout trigger changed while removing the historical fallback")
            removed.append({
                "artifact_id": artifact_id,
                "workflow_path": path,
                "event": row["event"],
                "qualifier": row["qualifier"],
            })
            continue

        require(line_numbers, f"retained artifact consumer reference disappeared: {key}")
        spec = spec_by_key.get(key)
        require(spec is not None, f"V1 relation has no reviewed source predicate: {key}")
        v1._validate_relation_source(spec, text)
        copied = copy.deepcopy(row)
        copied["artifact_reference_lines"] = line_numbers
        copied["workflow_source_sha256"] = sha256(raw)
        copied["classification_basis"] = (
            "CURRENT_TRACKED_WORKFLOW_SOURCE_AND_REVIEWED_DISPOSITION; "
            "VOLATILE_ACTIONS_STATE_EXCLUDED"
        )
        copied["replay_authority_inferred"] = False
        copied["authorizations"] = dict(v1.NO_AUTHORITY)
        current_rows.append(copied)
        current_pairs.add((artifact_id, path))

    expected_removed = {
        (HISTORICAL_ARTIFACT_ID, FRESH_WORKFLOW, "schedule", "cron 7 * * * *"),
        (HISTORICAL_ARTIFACT_ID, FRESH_WORKFLOW, "schedule", "cron 37 * * * *"),
        (
            HISTORICAL_ARTIFACT_ID,
            FRESH_WORKFLOW,
            "workflow_dispatch",
            "continuity inputs and exact prospective-only confirmation",
        ),
    }
    actual_removed = {
        (row["artifact_id"], row["workflow_path"], row["event"], row["qualifier"])
        for row in removed
    }
    require(actual_removed == expected_removed,
            "current source did not remove exactly the three fresh-holdout artifact-924 relations")
    require(b"9249856559" not in sources[FRESH_WORKFLOW],
            "current fresh-holdout workflow still contains artifact 9249856559")

    previous_edges = {
        (row["artifact_id"], row["workflow_path"])
        for row in predecessor["source_reference_inventory"]["workflow_reference_edges"]
    }
    expected_edges = previous_edges - {(HISTORICAL_ARTIFACT_ID, FRESH_WORKFLOW)}
    for path in paths:
        lines = sources[path].splitlines()
        for artifact_id in v1.ARTIFACT_IDS:
            matches = [
                (index, line)
                for index, line in enumerate(lines, 1)
                if artifact_id.encode("ascii") in line
            ]
            if not matches:
                continue
            pair = (int(artifact_id), path)
            require(pair in expected_edges,
                    f"unreviewed current artifact/workflow edge: {pair}")
            current_pairs.add(pair)
            matching_lines_by_artifact[artifact_id] += len(matches)
            workflow_edges.append({
                "artifact_id": int(artifact_id),
                "workflow_path": path,
                "workflow_source_sha256": sha256(sources[path]),
                "matching_lines": [index for index, _line in matches],
                "line_text_sha256": [sha256(line) for _index, line in matches],
            })
    require(current_pairs == expected_edges,
            "current exact artifact/workflow edge set differs from the three removed fallback relations")

    relation_keys = [
        (row["artifact_id"], row["workflow_path"], row["event"], row["qualifier"])
        for row in current_rows
    ]
    require(len(relation_keys) == len(set(relation_keys)), "duplicate current artifact-trigger relation")
    return (
        current_rows,
        sorted(workflow_edges, key=lambda row: (row["artifact_id"], row["workflow_path"])),
        {
            "matching_lines_by_artifact": matching_lines_by_artifact,
            "workflow_matching_line_count": sum(matching_lines_by_artifact.values()),
            "unique_workflow_path_count": len({path for _artifact, path in current_pairs}),
            "artifact_workflow_edge_count": len(current_pairs),
            "workflow_reference_edges": sorted(
                workflow_edges, key=lambda row: (row["artifact_id"], row["workflow_path"])
            ),
        },
    )


def _evolution_context() -> tuple[dict, str]:
    raw = _head_blob(evolution.LEDGER_PATH.as_posix())
    ledger = roles.strict_json(raw)
    prefix_path = (
        "artifacts/architecture/p4_workflow_evolution_snapshots/"
        "core_01d_current_shadow_schedule_retirement_v1.json"
    )
    prefix = roles.strict_json((ROOT / prefix_path).read_bytes())
    require(prefix.get("canonical_sha256") == PREDECESSOR_LEDGER_SHA256
            and evolution.canonical_sha256(prefix) == PREDECESSOR_LEDGER_SHA256,
            "immutable 13-transition CORE-01D evolution prefix drift")
    require(ledger.get("transitions", [])[:13] == prefix.get("transitions"),
            "first 13 workflow evolution transitions changed")
    require(ledger.get("canonical_sha256") == evolution.canonical_sha256(ledger),
            "current workflow evolution ledger is not canonical")
    transitions = ledger.get("transitions")
    require(type(transitions) is list and len(transitions) in (13, 14),
            "workflow evolution transition count is not the bounded Pass-1 state")
    if len(transitions) == 14:
        transition = transitions[-1]
        require(transition.get("transition_id") == TRANSITION_ID
                and transition.get("workflow_path") == FRESH_WORKFLOW
                and transition.get("operation") == "MAINTENANCE_REVISE"
                and transition.get("phase_id") == "CORE-01D"
                and transition.get("canonical_family") == "PROTECTED_RESEARCH",
                "transition 14 is not the exact PR119 bootstrap workflow revision")
    tree = _git("rev-parse", "HEAD:.github/workflows").decode("ascii").strip()
    return ledger, tree


def build_receipt() -> dict:
    predecessor = _read_v1()
    require(predecessor["missing_artifact_count"] == 8
            and predecessor["exact_archive_recovered_count"] == 0
            and predecessor["partial_durable_copy_count"] == 1,
            "immutable V1 artifact inventory/recovery identity drift")
    predecessor_blocker_ids = [
        row["id"] for row in predecessor["exact_remaining_blocker_ids"]
    ]
    require(predecessor_blocker_ids == [HISTORICAL_BLOCKER, *REMAINING_BLOCKER_IDS],
            "immutable V1 blocker order/identity drift")

    metadata_raw = (ROOT / RELEASE_METADATA_FIXTURE).read_bytes()
    _require_head_file_identity(RELEASE_METADATA_FIXTURE, metadata_raw)
    metadata = roles.strict_json(metadata_raw)
    require(metadata_raw == canonical_bytes(metadata),
            "fixed release metadata fixture is not canonical")
    assets = bootstrap.validate_release_metadata(bootstrap.REPOSITORY, metadata)
    bootstrap.validate_asset_metadata(assets)

    compressed = (ROOT / PAYLOAD_FIXTURE).read_bytes()
    _require_head_file_identity(PAYLOAD_FIXTURE, compressed)
    require(sha256(compressed) == PAYLOAD_FIXTURE_SHA256,
            "fixed release payload fixture compressed-byte identity drift")
    payload = gzip.decompress(compressed)
    parsed_rows = bootstrap.validate_projection_payload(payload)
    require(len(parsed_rows) == bootstrap.ROW_COUNT,
            "fixed release payload fixture row count drift")

    origin = {
        "repository": bootstrap.REPOSITORY,
        "source_kind": "FIXED_RELEASE",
        "release": bootstrap.RELEASE_TAG,
        "release_id": bootstrap.RELEASE_ID,
        "asset": bootstrap.ASSET_NAME,
        "asset_id": bootstrap.ASSET_ID,
        "asset_size_bytes": bootstrap.ASSET_SIZE,
        "payload_sha256": bootstrap.PAYLOAD_SHA256,
    }
    roles.validate_origin("PR119_BOOTSTRAP", origin)
    require(roles.CLASSIFICATIONS["PR119_BOOTSTRAP"]
            == "EXACT_FIXED_BOOTSTRAP_NO_NEW_AUTHORITY",
            "canonical PR119 role classification drift")

    paths, sources, trigger_count = _current_workflows()
    require(FRESH_WORKFLOW in sources, "protected fresh-holdout workflow disappeared")
    current_rows, current_edges, relation_counts = _current_relations(
        predecessor, paths, sources
    )
    ledger, tree = _evolution_context()
    require(tree != PREDECESSOR_WORKFLOW_TREE_SHA1,
            "workflow tree did not change for the required maintenance revision")
    if len(ledger["transitions"]) == 14:
        require(ledger.get("current_workflow_tree_sha1") == tree,
                "evolution ledger tree differs from the current workflow tree")
        require(ledger.get("current_live_workflow_count") == len(paths) == 39,
                "workflow path count changed during the bootstrap-only revision")

    artifacts = copy.deepcopy(predecessor["artifact_dispositions"])
    artifact_924, = [
        row for row in artifacts if row["artifact_id"] == HISTORICAL_ARTIFACT_ID
    ]
    require(artifact_924["recovery_state"] == "METADATA_ONLY_NO_BYTES",
            "historical artifact 924 recovery state changed")
    artifact_924["dependency_types"] = ["HARD_EXACT_REPLAY_SOURCE"]
    artifact_924["missing_evidence_effect"] = (
        "The current live fresh-holdout bootstrap no longer references this source ZIP; "
        "spent PR139 V2 historical replay still requires the exact original archive. "
        "Artifact 9249856559 remains METADATA_ONLY_NO_BYTES."
    )
    artifact_924["owner_decision"] = (
        "Preserve the unrecovered original ZIP identity for PR139 historical replay; "
        "do not substitute, reacquire from a provider, backfill, or retire it."
    )

    live_rows = [row for row in current_rows if row["trigger_lifecycle"].startswith("LIVE_")]
    historical_rows = [row for row in current_rows if not row["trigger_lifecycle"].startswith("LIVE_")]
    require(len(current_rows) == 14 and len(live_rows) == 4 and len(historical_rows) == 10,
            "source-derived current artifact-trigger relationship counts differ")
    require(relation_counts["artifact_workflow_edge_count"] == 12,
            "source-derived current artifact/workflow edge count differs")
    require(sum(row["recovery_state"] == "METADATA_ONLY_NO_BYTES" for row in artifacts) == 7
            and sum(row["recovery_state"] == "PARTIAL_DURABLE_COPY_RECOVERED" for row in artifacts) == 1,
            "current artifact recovery-state counts differ from V1")

    bootstrap_role = {
        "workflow_path": FRESH_WORKFLOW,
        "triggers": [
            {"event": "schedule", "qualifier": "cron 7 * * * *"},
            {"event": "schedule", "qualifier": "cron 37 * * * *"},
            {
                "event": "workflow_dispatch",
                "qualifier": "authenticated continuity dispatch",
            },
        ],
        "role_id": "PR119_BOOTSTRAP",
        "source_kind": "FIXED_RELEASE",
        "fixed_release_identity": {
            "repository": bootstrap.REPOSITORY,
            "tag": bootstrap.RELEASE_TAG,
            "release_name": bootstrap.RELEASE_NAME,
            "release_id": bootstrap.RELEASE_ID,
            "draft": False,
            "prerelease": False,
            "asset_id": bootstrap.ASSET_ID,
            "asset_name": bootstrap.ASSET_NAME,
            "asset_state": "uploaded",
            "asset_size_bytes": bootstrap.ASSET_SIZE,
            "asset_digest": bootstrap.ASSET_DIGEST,
            "payload_sha256": bootstrap.PAYLOAD_SHA256,
            "row_count": bootstrap.ROW_COUNT,
        },
        "authority_classification": roles.CLASSIFICATIONS["PR119_BOOTSTRAP"],
        "provider_reacquisition_authorized": False,
        "provider_reacquisition_performed": False,
        "historical_source_artifact_id": HISTORICAL_ARTIFACT_ID,
        "historical_source_zip_recovered": False,
        "historical_source_zip_recovery_state": "METADATA_ONLY_NO_BYTES",
        "runtime_fallback_artifact_ids": [],
        "backfill_authorized": False,
        "live_protected_research_retained": True,
        "research_only": True,
    }

    remaining_blockers = [
        row
        for row in predecessor["exact_remaining_blocker_ids"]
        if row["id"] in REMAINING_BLOCKER_IDS
    ]
    require([row["id"] for row in remaining_blockers] == list(REMAINING_BLOCKER_IDS),
            "unresolved blocker B/C/D identities drift")

    receipt = {
        "schema_version": 2,
        "policy_id": POLICY_ID,
        "repository": bootstrap.REPOSITORY,
        "master_issue": 337,
        "predecessor_v1": {
            "path": V1_RECEIPT_PATH,
            "canonical_sha256": V1_RECEIPT_SHA256,
            "state": "IMMUTABLE_PRE_PASS_1_BEFORE_STATE",
        },
        "source_base_main_sha": BASE_MAIN_SHA,
        "source_base_tree_sha": BASE_TREE_SHA,
        "source_review_counter_while_open": "3/5",
        "source_review_counter_if_owner_merges": "4/5",
        "mandatory_source_reread_due": False,
        "predecessor_workflow_tree_sha1": PREDECESSOR_WORKFLOW_TREE_SHA1,
        "predecessor_evolution_ledger_sha256": PREDECESSOR_LEDGER_SHA256,
        "current_evolution_ledger_sha256": ledger["canonical_sha256"],
        "evolution_transition_id": TRANSITION_ID,
        "current_workflow_tree_sha1": tree,
        "workflow_count": len(paths),
        "trigger_surface_count": trigger_count,
        "missing_artifact_count": len(artifacts),
        "exact_archive_recovered_count": 0,
        "partial_durable_copy_count": 1,
        "artifact_workflow_edge_count": relation_counts["artifact_workflow_edge_count"],
        "artifact_trigger_relationship_count": len(current_rows),
        "live_artifact_trigger_relationship_count": len(live_rows),
        "historical_or_spent_artifact_trigger_relationship_count": len(historical_rows),
        "source_derived_workflow_reference_inventory": {
            "workflow_count": len(paths),
            "workflow_tree_sha1": tree,
            "matching_lines_by_artifact": relation_counts["matching_lines_by_artifact"],
            "workflow_matching_line_count": relation_counts["workflow_matching_line_count"],
            "unique_workflow_path_count": relation_counts["unique_workflow_path_count"],
            "artifact_workflow_edge_count": relation_counts["artifact_workflow_edge_count"],
            "workflow_reference_edges": current_edges,
        },
        "current_artifact_trigger_relationships": current_rows,
        "artifact_dispositions": artifacts,
        "fixed_release_payload_fixture": {
            "path": PAYLOAD_FIXTURE,
            "compressed_sha256": PAYLOAD_FIXTURE_SHA256,
            "payload_size_bytes": len(payload),
            "payload_sha256": sha256(payload),
            "row_count": len(parsed_rows),
        },
        "fixed_release_metadata_fixture": {
            "path": RELEASE_METADATA_FIXTURE,
            "sha256": sha256(metadata_raw),
        },
        "pass1_supporting_source_inventory": _supporting_source_inventory(),
        "current_protected_bootstrap_role": bootstrap_role,
        "closed_blockers": [
            {
                "id": HISTORICAL_BLOCKER,
                "resolved_fact": (
                    "The live protected fresh-holdout uses only the exact fixed PR119_BOOTSTRAP "
                    "release projection. Historical artifact 9249856559 itself remains "
                    "unrecovered and required only by retained PR139 replay history."
                ),
            }
        ],
        "remaining_blocker_family": (
            "RETAINED_ACTIVE_EVIDENCE_DEPENDENCIES_AND_OWNER_DISPOSITIONS_UNRESOLVED"
        ),
        "remaining_blockers": remaining_blockers,
        "workflow_deletion_count": 0,
        "trigger_surface_change_count": 0,
        "workflow_count_delta": 0,
        "retired_workflow_count": 3,
        "provider_action_count": 0,
        "workflow_dispatch_action_count": 0,
        "workflow_rerun_or_cancel_action_count": 0,
        "evidence_regeneration_count": 0,
        "share_code_action_count": 0,
        "email_action_count": 0,
        "login_cookie_wallet_stake_wager_action_count": 0,
        "semantic_delta": dict.fromkeys(
            (
                "model",
                "probability",
                "calibration",
                "xg",
                "elo",
                "fatigue",
                "price_all",
                "router",
                "portfolio",
                "provider_market",
                "share_code",
                "delivery",
                "authority",
            ),
            0,
        ),
        "volatile_runtime_observations_included": False,
        "volatile_run_state_used_for_static_classification": False,
        "checkpoint_e_status": "INCOMPLETE",
        "p4_4_status": "INCOMPLETE",
        "terminal": "CORE_01D_PR119_RELEASE_ONLY_BOOTSTRAP_REVIEW_READY_INCOMPLETE_DO_NOT_MERGE",
    }
    return seal(receipt)


def validate_receipt(value: dict, expected: dict | None = None) -> None:
    require(value.get("canonical_sha256") == sha256(
        canonical_bytes({key: item for key, item in value.items() if key != "canonical_sha256"})
    ), "retained-status V2 self-hash mismatch")
    expected = build_receipt() if expected is None else expected
    require(value == expected, "retained-status V2 differs from source-derived current state")
    require(value["checkpoint_e_status"] == value["p4_4_status"] == "INCOMPLETE",
            "V2 cannot claim Checkpoint E or P4.4 completion")
    require(value["closed_blockers"][0]["id"] == HISTORICAL_BLOCKER,
            "V2 did not close only the fresh-holdout fallback blocker")
    require([row["id"] for row in value["remaining_blockers"]] == list(REMAINING_BLOCKER_IDS),
            "V2 unresolved blocker identities drift")
    require(value["current_protected_bootstrap_role"]["historical_source_zip_recovered"] is False,
            "V2 claims recovery of the historical source ZIP")


def audit() -> dict:
    ledger = evolution.validate_current_state()
    require(len(ledger["transitions"]) == 14,
            "current V2 audit requires exactly transition 14 and no transition 15")
    expected = build_receipt()
    raw = (ROOT / RECEIPT_PATH).read_bytes()
    committed = roles.strict_json(raw)
    require(raw.replace(b"\r\n", b"\n") == canonical_bytes(committed),
            "retained-status V2 is not canonical JSON")
    _require_head_file_identity(RECEIPT_PATH, raw)
    validate_receipt(committed, expected)
    return {
        "result": "PASS",
        "terminal": committed["terminal"],
        "receipt_sha256": committed["canonical_sha256"],
        "predecessor_v1_sha256": V1_RECEIPT_SHA256,
        "workflow_tree_sha1": committed["current_workflow_tree_sha1"],
        "evolution_ledger_sha256": ledger["canonical_sha256"],
        "evolution_transition_count": len(ledger["transitions"]),
        "workflow_count": committed["workflow_count"],
        "trigger_surface_count": committed["trigger_surface_count"],
        "missing_artifact_count": committed["missing_artifact_count"],
        "artifact_workflow_edge_count": committed["artifact_workflow_edge_count"],
        "artifact_trigger_relationship_count": committed["artifact_trigger_relationship_count"],
        "live_relation_count": committed["live_artifact_trigger_relationship_count"],
        "historical_relation_count": committed[
            "historical_or_spent_artifact_trigger_relationship_count"
        ],
        "closed_blockers": [row["id"] for row in committed["closed_blockers"]],
        "remaining_blockers": [row["id"] for row in committed["remaining_blockers"]],
        "checkpoint_e": committed["checkpoint_e_status"],
        "p4_4": committed["p4_4_status"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        expected = build_receipt()
        if args.write:
            (ROOT / RECEIPT_PATH).write_bytes(canonical_bytes(expected))
            result = {"result": "WROTE", "receipt_sha256": expected["canonical_sha256"]}
        else:
            result = audit()
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, RetainedWorkflowStatusV2Error, TypeError, ValueError, yaml.YAMLError) as exc:
        print(json.dumps({"result": "BLOCKED", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
