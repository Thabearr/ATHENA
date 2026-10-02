"""Offline proof of the owner-authorized source cutover on unmerged PR #431.

No executor, worker, provider, SMTP or GitHub transport is called. Immutable
predecessors and the pre-cutover design remain independently authenticated.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import tempfile

import yaml

from domain.run_contracts import canonical_json_bytes
from scripts import audit_checkpoint_e_workflows as predecessor
from scripts import audit_p4_workflow_evolution_ledger as evolution
from scripts.core_01d_historical_source import historical_bytes, identities
from services.athena_run_request_parser import parse_explicit_request

ROOT = Path(__file__).resolve().parents[1]
BASE = "24aed845e24396d813a91552a70703a76c52ef71"
POLICY_ID = "ATHENA_CORE_01D_SCHEDULED_SHADOW_OWNERSHIP_V1"
RECEIPT_PATH = "artifacts/architecture/core_01d_scheduled_shadow_ownership_v1.json"
PRIOR_DESIGN_SHA = "41dfb5b25d4b92a3137af29bc1717fd52b86b9794239617a2d59845aa312f138"
RECEIPT_SHA = "8e83fd5443149af74e14ceea44766809d1858ce856772a6500b8f55e073afde6"
INPUT_PATH = "tests/fixtures/core_01d_schedule/base-source-identities.json"
INPUT_SHA = "f7a167ac1677915346cd3358a6b53d3ffd507e7422bba14e41769e32247b4674"
BEFORE_AUDIT = "tests/fixtures/core_01d_schedule/pre-schedule-checkpoint-audit.py.txt"
CANONICAL = ".github/workflows/athena-run.yml"
LEGACY = ".github/workflows/current-shadow-all-market.yml"
REQUEST = "services/athena_run_workflow_request.py"
PERSIST = "scripts/resolve_athena_run_workflow_request.py"
ROLES = "services/athena_artifact_role_resolver.py"
RESTORE = "scripts/restore_athena_artifact_roles.py"
OLD_AUDIT = "scripts/audit_checkpoint_e_workflows.py"
LANE_EXPRESSION = "${{ github.event_name == 'schedule' && fromJSON('[\"main\",\"shadow\"]') || fromJSON(format('[\"{0}\"]', inputs.profile)) }}"
GROUP_EXPRESSION = "${{ matrix.lane == 'shadow' && 'current-shadow-all-market' || 'athena-run-main' }}"
ARTIFACT_EXPRESSION = "athena-run-${{ github.run_id }}${{ github.event_name == 'schedule' && matrix.lane == 'shadow' && '-scheduled-shadow' || '' }}"
DELIVERY = "LEGACY_SCHEDULED_DELIVERY_DEPRECATED_BY_EXPLICIT_OWNER_POLICY"
NOTIFICATION = "LEGACY_SCHEDULE_EMAIL_EXPLICITLY_RETIRED_BY_OWNER_POLICY"
BLOCKER = "all_retained_workflow_authority_and_dynamic_reachability_review_complete"
FORWARD_MATRIX = "artifacts/architecture/checkpoint_e_workflow_capability_matrix_v2.json"
FORWARD_RECEIPT = "artifacts/architecture/checkpoint_e_workflow_consolidation_v2.json"
TRANSITION_IDS = ["CORE01D_ATHENA_RUN_SCHEDULED_SHADOW_CUTOVER_V1", "CORE01D_CURRENT_SHADOW_SCHEDULE_RETIRE_V1"]


def require(value, message):
    if not value:
        raise ValueError(message)


def raw(path):
    return (ROOT / path).read_bytes().replace(b"\r\n", b"\n")


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def blob(value):
    return hashlib.sha1(b"blob " + str(len(value)).encode() + b"\0" + value).hexdigest()


def actual_modules():
    return {path: importlib.import_module(path[:-3].replace("/", "."))
            for path in (REQUEST, PERSIST, ROLES, RESTORE)}


def verify_inputs():
    payload = raw(INPUT_PATH)
    require(predecessor.sha(payload) == INPUT_SHA, "base source inventory drift")
    value = predecessor.strict(payload)
    require(value["base_sha"] == BASE and value["canonical_sha256"] == predecessor.self_sha(value), "base source identity differs")
    for path, identity in value["inputs"].items():
        inspected = raw(BEFORE_AUDIT) if path == OLD_AUDIT else historical_bytes(path)
        require(blob(inspected) == identity["git_blob_sha1"], "protected historical source drift: " + path)
    old = predecessor.strict(historical_bytes(RECEIPT_PATH))
    require(old["canonical_sha256"] == PRIOR_DESIGN_SHA == predecessor.self_sha(old), "prior design receipt lineage drift")
    return value


def validate_workflow_source():
    current = yaml.load(raw(CANONICAL), Loader=yaml.BaseLoader)
    old = yaml.load(historical_bytes(CANONICAL), Loader=yaml.BaseLoader)
    legacy = yaml.load(raw(LEGACY), Loader=yaml.BaseLoader)
    old_legacy = yaml.load(historical_bytes(LEGACY), Loader=yaml.BaseLoader)
    require(current["on"] == old["on"] and set(current["jobs"]) == {"canonical-run"}, "canonical trigger/manual input drift")
    require(current["on"]["schedule"] == [{"cron": "0 9 * * *"}], "MAIN cron drift")
    job = current["jobs"]["canonical-run"]
    require("concurrency" not in current and job["concurrency"] == {"group": GROUP_EXPRESSION, "cancel-in-progress": "false"}, "lane concurrency drift")
    require(job["strategy"] == {"fail-fast": "false", "matrix": {"lane": LANE_EXPRESSION}}, "schedule/manual lane cardinality drift")
    expected_legacy = copy.deepcopy(old_legacy)
    del expected_legacy["on"]["schedule"]
    require(legacy == expected_legacy and set(legacy["on"]) == {"workflow_dispatch", "issue_comment"}, "legacy change beyond schedule removal")
    require(legacy["concurrency"] == {"group": "current-shadow-all-market", "cancel-in-progress": "false"}, "legacy SHADOW exclusion drift")
    expected = copy.deepcopy(old)
    del expected["concurrency"]
    expected_job = expected["jobs"]["canonical-run"]
    expected_job["concurrency"] = job["concurrency"]
    expected_job["strategy"] = job["strategy"]
    step = next(s for s in expected_job["steps"] if s["id"] == "resolve_request")
    step["env"]["SCHEDULE_LANE"] = "${{ github.event_name == 'schedule' && matrix.lane || '' }}"
    step["run"] = (
        'args=(--output-root artifacts/athena-run-workflow)\n'
        'if [ -n "${SCHEDULE_LANE}" ]; then\n'
        '  args+=(--schedule-lane "${SCHEDULE_LANE}")\n'
        '  if [ "${SCHEDULE_LANE}" = shadow ]; then\n'
        '    # Explicit owner policy: scheduled delivery intentionally deprecated.\n'
        '    args+=(--scheduled-shadow-create-share-code false)\n'
        '  fi\n'
        'fi\n'
        'python -m scripts.resolve_athena_run_workflow_request "${args[@]}"\n')
    next(s for s in expected_job["steps"] if s["id"] == "upload_evidence")["with"]["name"] = ARTIFACT_EXPRESSION
    require(current == expected, "canonical workflow change beyond reviewed lane/request/concurrency/artifact seams")
    from services import athena_shadow_issue_comment_compatibility as comment
    require(comment.SCOPE_GRAMMAR == r"/athena-shadow target=([0-9]+) scope=(today|three-day)" and
            comment.EXPLICIT_DATES_GRAMMAR == r"/athena-shadow target=([0-9]+) dates=([0-9]{8}(?:,[0-9]{8}){0,6})", "comment grammar drift")


def validate_evolution():
    ledger = evolution.validate_current_state()
    before = json.loads(historical_bytes(evolution.LEDGER_PATH.as_posix()))
    require(ledger["transitions"][:11] == before["transitions"]
            and len(ledger["transitions"]) in (13, 14),
            "eleven-transition prefix/CORE-01D append drift")
    require([t["transition_id"] for t in ledger["transitions"][11:13]] == TRANSITION_IDS,
            "CORE-01D transition order drift")
    expected_tree, expected_ledger = (
        (evolution.CORE01D_PR119_WORKFLOW_TREE_SHA1, evolution.CORE01D_PR119_LEDGER_SHA256)
        if len(ledger["transitions"]) == 14
        else (evolution.CORE01D_WORKFLOW_TREE_SHA1, evolution.CORE01D_LEDGER_SHA256)
    )
    require(ledger["canonical_sha256"] == expected_ledger
            and ledger["current_workflow_tree_sha1"] == expected_tree,
            "exact current PORT-02C forward context drift")
    transitions = [t for t in ledger["transitions"] if t["workflow_path"] == evolution.PORT02C_REPLAY_WORKFLOW_PATH]
    require(len(transitions) == 1 and transitions[0]["transition_id"] == "PORT02C_NATIVE_RUNTIME_SLICE_ADD_V1", "false new PORT-02C transition")
    require(evolution.source_identity(raw(evolution.PORT02C_REPLAY_WORKFLOW_PATH)) == evolution.PORT02C_REPLAY_WORKFLOW_AFTER, "PORT-02C successor source drift")
    for t, path, contract in zip(ledger["transitions"][11:], (CANONICAL, LEGACY),
                                (evolution.CORE01D_SCHEDULE_OWNER_CONTRACT, evolution.CORE01D_SCHEDULE_RETIRE_CONTRACT)):
        require(t["workflow_path"] == path and t["operation"] == "MAINTENANCE_REVISE" and
                t["phase_id"] == "CORE-01D" and t["canonical_family"] == "ATHENA_RUN" and
                t["maintenance_contract"] == contract and t["before"] == evolution.source_identity(historical_bytes(path)), "CORE-01D maintenance identity drift")
    if len(ledger["transitions"]) == 14:
        transition = ledger["transitions"][13]
        path = ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
        before_fixture = transition["historical_before_fixture"]["path"]
        fixture_identity = evolution.source_identity((ROOT / before_fixture).read_bytes())
        require(transition["transition_id"] == "CORE01D_FRESH_HOLDOUT_PR119_RELEASE_ONLY_BOOTSTRAP_V1"
                and transition["workflow_path"] == path
                and transition["operation"] == "MAINTENANCE_REVISE"
                and transition["phase_id"] == "CORE-01D"
                and transition["canonical_family"] == "PROTECTED_RESEARCH"
                and transition["maintenance_contract"] == evolution.CORE01D_PR119_RELEASE_ONLY_CONTRACT
                and transition["before"] == fixture_identity
                and transition["after"] == evolution.source_identity(raw(path)),
                "PR119 release-only transition 14 identity drift")
    return ledger


def artifact_policy_proof(modules):
    """Synthetic metadata traverses production discovery, without an API call."""
    roles, transport = modules[ROLES], modules[RESTORE]
    run = {"id": 100, "repository": {"full_name": roles.REPOSITORY},
        "head_repository": {"full_name": roles.REPOSITORY}, "path": CANONICAL,
        "head_branch": "main", "head_sha": BASE, "status": "completed", "conclusion": "success", "event": "schedule"}
    old = {"id": 200, "name": "athena-run-100", "expired": False,
        "workflow_run": {"id": 100, "head_sha": BASE, "head_branch": "main"}}
    suffix = {**old, "id": 201, "name": "athena-run-100-scheduled-shadow"}
    class Metadata(transport.GitHubTransport):
        def api(self, *args, **kwargs):
            raise AssertionError("offline audit forbids GitHub transport")
        def pages(self, endpoint, field):
            return [run] if field == "workflow_runs" else artifacts
    artifacts = [old, suffix]
    selected, = Metadata().candidates(CANONICAL, canonical_producer=True)
    require(selected.artifact_id == 201, "scheduled SHADOW transport selection drift")
    roles.validate_candidate(selected, current_run_id=101, role_id="PR119_BOOTSTRAP", canonical_producer=True)
    suffix["expired"] = True
    require(not Metadata().candidates(CANONICAL, canonical_producer=True), "expired suffix downgraded to MAIN")
    suffix["expired"] = False
    suffix["workflow_run"] = {**old["workflow_run"], "head_sha": "0" * 40}
    require(not Metadata().candidates(CANONICAL, canonical_producer=True), "bad-bound suffix downgraded to MAIN")
    artifacts = [old]
    historical, = Metadata().candidates(CANONICAL, canonical_producer=True)
    require(historical.artifact_name == old["name"], "historical schedule fallback drift")
    run["event"] = "workflow_dispatch"
    manual, = Metadata().candidates(CANONICAL, canonical_producer=True)
    require(manual.artifact_name == old["name"], "manual artifact name drift")
    artifacts = [old, suffix]
    try:
        Metadata().candidates(CANONICAL, canonical_producer=True)
    except roles.ArtifactRoleError:
        pass
    else:
        raise ValueError("manual suffix accepted")
    return "PRODUCTION_DISCOVERY_AND_CANDIDATE_CHECKS_PASSED_SYNTHETIC_METADATA_NO_API"


def expected_receipt():
    verify_inputs()
    validate_workflow_source()
    ledger = validate_evolution()
    modules = actual_modules()
    artifact_proof = artifact_policy_proof(modules)
    adapter = modules[REQUEST]
    date_rows = []
    for clock in ("09:00", "22:59", "23:00"):
        now = datetime.fromisoformat("2026-10-01T" + clock + ":00+00:00")
        main = adapter.resolve_workflow_request(event_name="schedule", schedule_lane="main", now=now)
        old_main = parse_explicit_request(days="today", target_legs=20, profile="main", create_share_code=False, now=now)
        require(canonical_json_bytes(main) == canonical_json_bytes(old_main), "MAIN schedule byte regression")
        with tempfile.TemporaryDirectory(prefix="athena-core01d-no-provider-") as directory:
            root = Path(directory) / "request"
            try:
                request, metadata = modules[PERSIST].resolve_and_persist(event_name="schedule", dispatch_inputs=None,
                    schedule_lane="shadow", scheduled_shadow_create_share_code=False, now=now,
                    github_sha=BASE, github_ref="refs/heads/main", output_root=root)
            except adapter.AthenaRunWorkflowRequestError:
                require(clock == "23:00" and not root.exists(), "UTC date rejection/persistence drift")
                date_rows.append({"clock_utc": now.isoformat(), "status": "UNREPRESENTABLE_FAIL_CLOSED_BEFORE_PERSISTENCE_OR_PROVIDER", "request_sha256": None})
            else:
                require(clock != "23:00" and request.dates[0].isoformat() == "2026-10-01" and
                    (request.authority_profile, request.mode, request.target_legs, request.bookie, request.target_total_odds,
                     request.create_share_code, request.place_wager) == ("SHADOW", "research_shadow", 20, "sportybet", None, False, False), "scheduled SHADOW contract drift")
                require(metadata["schedule_lane"] == "shadow" and metadata["original_schedule_intent"] == "UTC_TODAY" and
                        metadata["request_canonical_sha256"] == request.canonical_sha256, "schedule metadata drift")
                date_rows.append({"clock_utc": now.isoformat(), "status": "EXACT_UTC_DATE_REPRESENTABLE", "request_sha256": request.canonical_sha256})
    from scripts import audit_lg_a_worker_launch_failure_remediation as lg
    failed = lg.historical_producer_proof()
    accepted = predecessor.accepted_evidence()
    require(failed["historical_manifest_true_unchanged"] and accepted["restore_eligible"], "LG-A history drift")
    return predecessor.seal({
        "schema_version": 1, "policy_id": POLICY_ID, "exact_base_main_sha": BASE,
        "prior_design_receipt_sha256": PRIOR_DESIGN_SHA, "prior_design_receipt_fixture": identities()[RECEIPT_PATH]["fixture"],
        "owner_authorization": "EXPLICIT_SCHEDULED_DELIVERY_DEPRECATION_SCHEDULE_EMAIL_RETIREMENT_ATOMIC_SOURCE_CUTOVER_AND_EXACT_PORT02C_FORWARD_CONTEXT_NO_MERGE_NO_LIVE_ACTION",
        "master_issue": 337, "pr": 431, "source_review_counter_while_open": "1/5", "source_review_counter_if_owner_merges": "2/5",
        "delivery_disposition": DELIVERY, "notification_disposition": NOTIFICATION,
        "legacy_delivery_byte_or_intention_parity_claimed": False,
        "scheduled_shadow_create_share_code": False, "scheduled_shadow_email": False,
        "retained_manual_comment_delivery_and_email": "UNCHANGED",
        "source_cutover_implemented_on_unmerged_pr": True, "deployed_on_main": False,
        "canonical_scheduled_shadow_active": True, "legacy_schedule_trigger_removed": True, "dual_live_schedule_in_pr_source": False,
        "date_matrix": date_rows, "main_schedule": "UNCHANGED_09Z_MAIN_LAGOS_TODAY_TARGET20_SPORTYBET_NO_DELIVERY_NO_WAGER",
        "concurrency": {"main": "athena-run-main", "shadow": "current-shadow-all-market", "placement": "JOB_LEVEL", "cancel_in_progress": False},
        "artifact_names": {"manual_main": "athena-run-<run_id>", "manual_shadow": "athena-run-<run_id>",
                           "scheduled_main": "athena-run-<run_id>", "scheduled_shadow": "athena-run-<run_id>-scheduled-shadow"},
        "discovery_policy": "UNIQUE_EXACT_SCHEDULE_SUFFIX_FIRST_NO_DOWNGRADE_IF_PRESENT_OLD_EXACT_NAME_ONLY_WHEN_ABSENT_MANUAL_SUFFIX_FORBIDDEN",
        "manifest_schema": modules[ROLES].MANIFEST_POLICY_ID,
        "restore_authority": "INDEPENDENT_SUCCESSFUL_SHADOW_REQUEST_RECEIPT_MANIFEST_ROLE_VALIDATION_NOT_FILENAME",
        "artifact_policy_offline_proof": artifact_proof,
        "accepted_lg_a": accepted,
        "failed_lg_a": {"run_id": 36846297806, "disposition": "IMMUTABLE_FAILED_NON_RETRYABLE", "restore_eligible": False},
        "evolution": {"transition_count_before": 11, "transition_count_after": 13, "transition_ids": TRANSITION_IDS,
            "ledger_sha256": ledger["canonical_sha256"], "workflow_tree_before": evolution.CORE01C_WORKFLOW_TREE_SHA1,
            "workflow_tree_after": ledger["current_workflow_tree_sha1"],
            "checkpoints": [{"receipt_path": t["evidence_receipt_path"], "receipt_sha256": json.loads(raw(t["evidence_receipt_path"]))["canonical_sha256"],
                "snapshot_path": t["checkpoint_snapshot_path"], "snapshot_sha256": json.loads(raw(t["checkpoint_snapshot_path"]))["canonical_sha256"]}
                for t in ledger["transitions"][11:]]},
        "port02c_forward_context": {"classification": "EXACT_EXISTING_SUCCESSOR_CONTEXT_EXTENSION_NO_NEW_WORKFLOW_TRANSITION",
            "workflow_path": evolution.PORT02C_REPLAY_WORKFLOW_PATH,
            "transition_history_identity": evolution.PORT02C_REPLAY_WORKFLOW_BEFORE,
            "current_reviewed_successor_identity": evolution.PORT02C_REPLAY_WORKFLOW_AFTER,
            "core01d_workflow_tree_sha1": evolution.CORE01D_WORKFLOW_TREE_SHA1,
            "core01d_evolution_ledger_sha256": evolution.CORE01D_LEDGER_SHA256,
            "new_port02c_transition": False, "context_count_before": 3, "context_count_after": 4},
        "production_source_identities": {p: evolution.source_identity(raw(p)) for p in (CANONICAL, LEGACY, REQUEST, PERSIST, ROLES, RESTORE)},
        "checkpoint_forward_paths": [FORWARD_MATRIX, FORWARD_RECEIPT],
        "checkpoint_e_status": "INCOMPLETE", "p4_4_status": "INCOMPLETE", "blockers": [BLOCKER],
        "blocker_2_scope": "RETAINED_FAMILY_AUTHORITY_DYNAMIC_REACHABILITY_DURABLE_RETENTION_UNTOUCHED",
        "live_side_effect_counts": dict.fromkeys(("provider", "live_run", "dispatch", "share_code_create", "share_code_reload", "delivery", "email", "login", "cookies", "wallet", "stake", "wager"), 0),
        "semantic_delta": dict.fromkeys(("model", "probability", "calibration", "xg", "elo", "price_all", "router", "portfolio", "provider_market", "share_code_implementation"), 0),
    })


def verified_receipt_path():
    ledger = evolution.validate_current_state()
    if len(ledger["transitions"]) == 14:
        value = predecessor.strict(raw(RECEIPT_PATH))
        require(value.get("canonical_sha256") == RECEIPT_SHA == predecessor.self_sha(value),
                "unreviewed immutable scheduled-ownership receipt identity drift")
        return RECEIPT_PATH
    value = predecessor.strict(raw(RECEIPT_PATH))
    require(value.get("canonical_sha256") == RECEIPT_SHA == predecessor.self_sha(value), "unreviewed scheduled ownership receipt identity")
    require(value == expected_receipt(), "unreviewed scheduled ownership receipt/source drift")
    return RECEIPT_PATH


def expected_forward_documents(schedule):
    old_matrix = predecessor.strict(raw(predecessor.MATRIX_PATH))
    old_receipt = predecessor.strict(raw(predecessor.RECEIPT_PATH))
    require(old_matrix["canonical_sha256"] == predecessor.CHECKPOINT_MATRIX_SHA == predecessor.self_sha(old_matrix) and
            old_receipt["canonical_sha256"] == predecessor.CHECKPOINT_RECEIPT_SHA == predecessor.self_sha(old_receipt), "immutable Checkpoint-E V1 drift")
    matrix = copy.deepcopy(old_matrix)
    matrix.update(schema_version=2, policy_id="ATHENA_CORE_01D_TRIGGER_CAPABILITY_MATRIX_V2",
        predecessor_matrix_sha256=old_matrix["canonical_sha256"], predecessor_receipt_sha256=old_receipt["canonical_sha256"],
        schedule_ownership_receipt_sha256=schedule["canonical_sha256"], evolution_ledger_sha256=evolution.CORE01D_LEDGER_SHA256,
        current_workflow_tree_sha1=evolution.CORE01D_WORKFLOW_TREE_SHA1)
    for row in matrix["workflow_rows"]:
        path = row["workflow_path"]
        doc = yaml.load(raw(path), Loader=yaml.BaseLoader)
        row["trigger_surfaces"] = [s for s in row["trigger_surfaces"] if s["trigger_kind"] in doc["on"]]
        row["git_blob_sha1"] = blob(raw(path))
        row["source_sha256"] = predecessor.sha(raw(path))
        row["current_callers_and_references"]["scan_basis"] = "IMMUTABLE_V1_REFERENCE_INVENTORY_NOT_CURRENT_DYNAMIC_REACHABILITY_PROOF"
        if path == CANONICAL:
            steps = predecessor.census._steps(doc)
            uploads, downloads = predecessor.census._artifacts(steps)
            row.update(artifact_uploads=uploads, artifact_downloads=downloads,
                       artifact_names=sorted({u["name"] for u in uploads if u["name"]}))
            surface = next(s for s in row["trigger_surfaces"] if s["trigger_kind"] == "schedule")
            surface.update(authority_profile="MAIN_AND_SHADOW_EXPLICIT_LANES", acquisition_authority="EXPLICIT_SHADOW_ONLY",
                delivery_authority=False, date_timezone_semantics="MAIN_LAGOS_TODAY_SHADOW_UTC_TODAY_FROZEN_THEN_LAGOS_VALIDATED_NO_SHIFT",
                successor_request_parity="MAIN_UNCHANGED_SHADOW_DELIVERY_INTENTIONALLY_DEPRECATED_BY_OWNER_POLICY",
                schedule_lanes=[{"lane": "main", "authority_profile": "MAIN", "create_share_code": False, "date_intent": "LAGOS_TODAY"},
                                {"lane": "shadow", "authority_profile": "SHADOW", "create_share_code": False, "date_intent": "UTC_TODAY"}])
        require([s["trigger_kind"] for s in row["trigger_surfaces"]] == sorted(doc["on"]), "forward trigger enumeration drift")
    matrix["trigger_surface_count"] = sum(len(r["trigger_surfaces"]) for r in matrix["workflow_rows"])
    require(matrix["workflow_count"] == len(matrix["workflow_rows"]) == 39 and matrix["trigger_surface_count"] == 57, "forward workflow/trigger census drift")
    predecessor.seal(matrix)
    criteria = copy.deepcopy(old_receipt["checkpoint_criteria"])
    criteria["scheduled_shadow_canonical_ownership_proven_preserving_main"] = True
    status, blockers = predecessor.checkpoint_status(criteria)
    require(status == "INCOMPLETE" and blockers == [BLOCKER], "unsupported Checkpoint-E completion")
    receipt = predecessor.seal({"schema_version": 2, "policy_id": "ATHENA_CORE_01D_WORKFLOW_CONSOLIDATION_CHECKPOINT_E_V2",
        "predecessor_matrix_sha256": old_matrix["canonical_sha256"], "predecessor_receipt_sha256": old_receipt["canonical_sha256"],
        "schedule_ownership_receipt_sha256": schedule["canonical_sha256"], "evolution_ledger_sha256": evolution.CORE01D_LEDGER_SHA256,
        "current_workflow_tree_sha1": evolution.CORE01D_WORKFLOW_TREE_SHA1,
        "workflow_matrix_path": FORWARD_MATRIX, "workflow_matrix_sha256": matrix["canonical_sha256"],
        "live_workflow_count": 39, "trigger_surface_count": 57, "historical_p4_3_retired_count": 3,
        "checkpoint_criteria": criteria, "checkpoint_e_status": status, "p4_4_status": status,
        "remaining_blocker_ids": blockers, "remaining_blocker": "RETAINED_FAMILY_AUTHORITY_DYNAMIC_REACHABILITY_DURABLE_RETENTION_REVIEW",
        "source_cutover_on_unmerged_pr": True, "deployed_on_main": False,
        "retired_workflows": [], "live_side_effect_counts": schedule["live_side_effect_counts"]})
    return matrix, receipt


def audit_forward_checkpoint():
    ledger = evolution.validate_current_state()
    if len(ledger["transitions"]) == 14:
        schedule = predecessor.strict(raw(RECEIPT_PATH))
        matrix = predecessor.strict(raw(FORWARD_MATRIX))
        receipt = predecessor.strict(raw(FORWARD_RECEIPT))
        from scripts import audit_core_01d_retained_workflow_status as retained_status_v1

        require(schedule.get("canonical_sha256") == RECEIPT_SHA == predecessor.self_sha(schedule),
                "unreviewed immutable scheduled-ownership receipt identity drift")
        require(matrix.get("canonical_sha256") == retained_status_v1.PREDECESSOR_V2_MATRIX_SHA256
                == predecessor.self_sha(matrix), "forward Checkpoint-E immutable V2 matrix identity drift")
        require(receipt.get("canonical_sha256") == retained_status_v1.PREDECESSOR_V2_RECEIPT_SHA256
                == predecessor.self_sha(receipt), "forward Checkpoint-E immutable V2 receipt identity drift")
        require(receipt.get("evolution_ledger_sha256") == evolution.CORE01D_LEDGER_SHA256
                and receipt.get("current_workflow_tree_sha1") == evolution.CORE01D_WORKFLOW_TREE_SHA1
                and receipt.get("checkpoint_e_status") == receipt.get("p4_4_status") == "INCOMPLETE",
                "immutable Checkpoint-E V2 before-state binding drift")
        from scripts.audit_core_01d_retained_workflow_status_v2 import audit as audit_status_v2
        current = audit_status_v2()
        require(current.get("result") == "PASS"
                and current.get("evolution_transition_count") == 14
                and current.get("checkpoint_e") == current.get("p4_4") == "INCOMPLETE",
                "current retained-status V2 / Pass-1 evidence failed authentication")
        return receipt
    require(len(ledger["transitions"]) == 13,
            "scheduled ownership forward supports only its immutable predecessor or exact Pass-1 successor")
    schedule = expected_receipt()
    require(predecessor.strict(raw(RECEIPT_PATH)) == schedule, "schedule receipt drift")
    matrix, receipt = expected_forward_documents(schedule)
    require(predecessor.strict(raw(FORWARD_MATRIX)) == matrix and predecessor.strict(raw(FORWARD_RECEIPT)) == receipt, "forward Checkpoint-E evidence drift")
    return receipt


def additive_paths():
    audit_forward_checkpoint()
    ledger = json.loads(raw(evolution.LEDGER_PATH))
    paths = (
        RECEIPT_PATH,
        FORWARD_MATRIX,
        FORWARD_RECEIPT,
        *(p for t in ledger["transitions"][11:]
          for p in (t["evidence_receipt_path"], t["checkpoint_snapshot_path"])),
    )
    if len(ledger["transitions"]) == 14:
        return (*paths, "artifacts/architecture/core_01d_retained_workflow_status_v2.json")
    return paths


def audit():
    verified_receipt_path()
    forward = audit_forward_checkpoint()
    return {"result": "PASS", "terminal": "CORE_01D_SCHEDULED_SHADOW_OWNERSHIP_REVIEW_READY_CUTOVER_PROVEN_DO_NOT_MERGE",
            "exact_head": git("rev-parse", "HEAD").decode().strip(), "receipt_sha256": json.loads(raw(RECEIPT_PATH))["canonical_sha256"],
            "workflow_tree_sha1": evolution.CORE01D_WORKFLOW_TREE_SHA1, "ledger_sha256": evolution.CORE01D_LEDGER_SHA256,
            "workflow_count": 39, "trigger_surface_count": 57, "checkpoint_e": "INCOMPLETE", "blockers": forward["remaining_blocker_ids"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        schedule = expected_receipt()
        matrix, receipt = expected_forward_documents(schedule)
        for path, value in ((RECEIPT_PATH, schedule), (FORWARD_MATRIX, matrix), (FORWARD_RECEIPT, receipt)):
            (ROOT / path).write_bytes(predecessor.canonical(value))
        print(json.dumps({"schedule_receipt_sha256": schedule["canonical_sha256"], "matrix_sha256": matrix["canonical_sha256"], "checkpoint_receipt_sha256": receipt["canonical_sha256"]}, sort_keys=True))
    else:
        print(json.dumps(audit(), sort_keys=True))


if __name__ == "__main__":
    main()
