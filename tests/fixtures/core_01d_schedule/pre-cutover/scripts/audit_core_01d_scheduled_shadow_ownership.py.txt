"""Offline, non-deployed schedule design projection; grants no cutover authority.

The projection modifies copies of the existing seams in memory. It is not an
executor, another workflow family, or a production request adapter. Delivery
and scheduled-email policy remain owner decisions; operational source is pinned.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import yaml

from domain.run_contracts import canonical_json_bytes
from scripts import audit_checkpoint_e_workflows as predecessor

ROOT = Path(__file__).resolve().parents[1]
BASE = "24aed845e24396d813a91552a70703a76c52ef71"
POLICY_ID = "ATHENA_CORE_01D_SCHEDULED_SHADOW_OWNERSHIP_V1"
RECEIPT_PATH = "artifacts/architecture/core_01d_scheduled_shadow_ownership_v1.json"
INPUT_PATH = "tests/fixtures/core_01d_schedule/base-source-identities.json"
BEFORE_AUDIT = "tests/fixtures/core_01d_schedule/pre-schedule-checkpoint-audit.py.txt"
INPUT_SHA = "f7a167ac1677915346cd3358a6b53d3ffd507e7422bba14e41769e32247b4674"
RECEIPT_SHA = "41dfb5b25d4b92a3137af29bc1717fd52b86b9794239617a2d59845aa312f138"
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


def require(value, message):
    if not value:
        raise ValueError(message)


def raw(path):
    return (ROOT / path).read_bytes().replace(b"\r\n", b"\n")


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def blob(value):
    return hashlib.sha1(b"blob " + str(len(value)).encode() + b"\0" + value).hexdigest()


def replace_one(source, before, after):
    require(source.count(before) == 1, "proposal source anchor missing/ambiguous")
    return source.replace(before, after)


def verify_inputs():
    payload = raw(INPUT_PATH)
    require(predecessor.sha(payload) == INPUT_SHA, "base source inventory drift")
    value = predecessor.strict(payload)
    require(value["base_sha"] == BASE and value["canonical_sha256"] == predecessor.self_sha(value), "base source identity differs")
    for path, identity in value["inputs"].items():
        inspected = raw(BEFORE_AUDIT if path == OLD_AUDIT else path)
        require(blob(inspected) == identity["git_blob_sha1"], "protected source/receipt drift: " + path)
    before = raw(BEFORE_AUDIT).decode()
    expected = replace_one(before, "    return (MATRIX_PATH, RECEIPT_PATH)\n",
        "    from scripts.audit_core_01d_scheduled_shadow_ownership import verified_receipt_path\n"
        "    return (MATRIX_PATH, RECEIPT_PATH, verified_receipt_path())\n")
    require(raw(OLD_AUDIT).decode() == expected, "predecessor audit forward exceeds exact additive receipt allowance")
    return value


def verified_receipt_path():
    payload = raw(RECEIPT_PATH)
    value = predecessor.strict(payload)
    require(payload == predecessor.canonical(value) and value.get("canonical_sha256") == RECEIPT_SHA == predecessor.self_sha(value),
            "unreviewed scheduled-shadow additive receipt")
    return RECEIPT_PATH


def projected_sources():
    """Exact proposed deltas, never written to production paths or dispatched."""
    sources = {path: raw(path).decode() for path in (CANONICAL, REQUEST, PERSIST, ROLES, RESTORE)}
    request = sources[REQUEST]
    request = replace_one(request, "from datetime import datetime\n", "from datetime import datetime, timezone\n")
    request = replace_one(request, "    now: datetime | None = None,\n) -> RunRequest:",
        "    now: datetime | None = None,\n    schedule_lane: str | None = None,\n"
        "    scheduled_shadow_create_share_code: bool | None = None,\n) -> RunRequest:")
    request = replace_one(request, "    if event_name == \"schedule\":\n",
        "    if schedule_lane is not None and (type(schedule_lane) is not str or schedule_lane not in {'main', 'shadow'}):\n"
        "        raise AthenaRunWorkflowRequestError('unsupported schedule lane')\n"
        "    if event_name != 'schedule' and (schedule_lane is not None or scheduled_shadow_create_share_code is not None):\n"
        "        raise AthenaRunWorkflowRequestError('schedule contract forbidden for non-schedule event')\n"
        "    if event_name == \"schedule\":\n")
    request = replace_one(request, "        create_share_code = SCHEDULE_CREATE_SHARE_CODE\n",
        "        create_share_code = SCHEDULE_CREATE_SHARE_CODE\n"
        "        if schedule_lane == 'shadow':\n"
        "            if type(scheduled_shadow_create_share_code) is not bool:\n"
        "                raise AthenaRunWorkflowRequestError('scheduled delivery policy must be explicit; no profile default')\n"
        "            now = datetime.now(timezone.utc) if now is None else now\n"
        "            if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:\n"
        "                raise AthenaRunWorkflowRequestError('schedule clock must be timezone-aware')\n"
        "            from domain.current_shadow_fixture_date_request import validate_fixture_dates\n"
        "            utc_day = now.astimezone(timezone.utc).date()\n"
        "            validate_fixture_dates((utc_day.strftime('%Y%m%d'),), current_utc=now)\n"
        "            days = utc_day.isoformat()  # freeze UTC today; canonical parser rejects, never shifts\n"
        "            profile = 'shadow'\n"
        "            create_share_code = scheduled_shadow_create_share_code\n"
        "        elif scheduled_shadow_create_share_code is not None:\n"
        "            raise AthenaRunWorkflowRequestError('MAIN schedule cannot receive SHADOW delivery policy')\n")
    sources[REQUEST] = request
    persist = sources[PERSIST]
    persist = replace_one(persist, "    now: datetime | None = None,\n) -> tuple", "    now: datetime | None = None,\n    schedule_lane: str | None = None,\n    scheduled_shadow_create_share_code: bool | None = None,\n) -> tuple")
    persist = replace_one(persist, "        now=now,\n    )\n", "        now=now,\n        schedule_lane=schedule_lane,\n        scheduled_shadow_create_share_code=scheduled_shadow_create_share_code,\n    )\n")
    persist = replace_one(persist, "    _write_consistent(request_path, request_bytes)\n",
        "    if event_name == 'schedule':\n"
        "        metadata.update(schedule_lane=schedule_lane or 'main',\n"
        "            original_schedule_intent='UTC_TODAY' if schedule_lane == 'shadow' else 'LAGOS_TODAY',\n"
        "            date_policy_status='EXACT_UTC_DATE_REPRESENTABLE' if schedule_lane == 'shadow' else 'ESTABLISHED_MAIN_DATE_POLICY')\n"
        "    _write_consistent(request_path, request_bytes)\n")
    persist = replace_one(persist, "    args = parser.parse_args(argv)\n",
        "    parser.add_argument('--schedule-lane', choices=('main', 'shadow'))\n"
        "    parser.add_argument('--scheduled-shadow-create-share-code', choices=('true', 'false'))\n"
        "    args = parser.parse_args(argv)\n")
    persist = replace_one(persist, "            event_name=event_name,\n",
        "            schedule_lane=args.schedule_lane,\n"
        "            scheduled_shadow_create_share_code=(None if args.scheduled_shadow_create_share_code is None else args.scheduled_shadow_create_share_code == 'true'),\n"
        "            event_name=event_name,\n")
    sources[PERSIST] = persist
    sources[ROLES] = replace_one(sources[ROLES],
        '                candidate.artifact_name == f"athena-run-{candidate.run_id}" and\n',
        '                candidate.artifact_name in ({f"athena-run-{candidate.run_id}",\n'
        '                    f"athena-run-{candidate.run_id}-scheduled-shadow"} if candidate.event_name == "schedule"\n'
        '                    else {f"athena-run-{candidate.run_id}"}) and\n')
    restore = sources[RESTORE]
    restore = replace_one(restore, '            name = f"athena-run-{run[\'id\']}" if canonical_producer else artifact_name\n',
        '            if canonical_producer and run.get("event") not in {"schedule", "workflow_dispatch"}:\n'
        '                continue\n'
        '            name = f"athena-run-{run[\'id\']}" if canonical_producer else artifact_name\n')
    restore = replace_one(restore, '            matches = [item for item in artifacts if item.get("name") == name and item.get("expired") is False]\n',
        '            if canonical_producer:\n'
        '                suffix = f"athena-run-{run[\'id\']}-scheduled-shadow"\n'
        '                suffixed = [item for item in artifacts if item.get("name") == suffix]\n'
        '                old = [item for item in artifacts if item.get("name") == name]\n'
        '                roles.require(len(suffixed) <= 1 and len(old) <= 1, "ambiguous canonical artifact name")\n'
        '                if run.get("event") == "workflow_dispatch":\n'
        '                    roles.require(not suffixed, "scheduled suffix on manual event")\n'
        '                elif suffixed:\n'
        '                    # A known dual-lane producer must never downgrade to MAIN\n'
        '                    # when its SHADOW artifact expires or has bad binding.\n'
        '                    if suffixed[0].get("expired") is not False:\n'
        '                        continue\n'
        '                    name = suffix\n'
        '            matches = [item for item in artifacts if item.get("name") == name and item.get("expired") is False]\n')
    sources[RESTORE] = restore
    workflow = sources[CANONICAL]
    workflow = replace_one(workflow, "concurrency:\n  group: ${{ github.event_name == 'workflow_dispatch' && inputs.profile == 'shadow' && 'current-shadow-all-market' || 'athena-run-main' }}\n  cancel-in-progress: false\n\n", "")
    workflow = replace_one(workflow, "  canonical-run:\n    runs-on:",
        "  canonical-run:\n    strategy:\n      fail-fast: false\n      matrix:\n        lane: " + LANE_EXPRESSION + "\n"
        "    concurrency:\n      group: " + GROUP_EXPRESSION + "\n      cancel-in-progress: false\n"
        "    runs-on:")
    workflow = replace_one(workflow, "          GITHUB_EVENT_NAME: ${{ github.event_name }}\n",
        "          SCHEDULE_LANE: ${{ github.event_name == 'schedule' && matrix.lane || '' }}\n"
        "          # UNDECIDED: no live deployment until delivery/email policy is approved.\n"
        "          SCHEDULE_SHADOW_DELIVERY: \"\"\n"
        "          GITHUB_EVENT_NAME: ${{ github.event_name }}\n")
    workflow = replace_one(workflow, "        run: python -m scripts.resolve_athena_run_workflow_request --output-root artifacts/athena-run-workflow\n",
        "        run: |\n"
        "          args=(--output-root artifacts/athena-run-workflow)\n"
        "          if [ -n \"${SCHEDULE_LANE}\" ]; then\n"
        "            args+=(--schedule-lane \"${SCHEDULE_LANE}\")\n"
        "            if [ \"${SCHEDULE_LANE}\" = shadow ]; then\n"
        "              test \"${SCHEDULE_SHADOW_DELIVERY}\" = true || test \"${SCHEDULE_SHADOW_DELIVERY}\" = false || exit 2\n"
        "              args+=(--scheduled-shadow-create-share-code \"${SCHEDULE_SHADOW_DELIVERY}\")\n"
        "            fi\n"
        "          fi\n"
        "          python -m scripts.resolve_athena_run_workflow_request \"${args[@]}\"\n")
    workflow = replace_one(workflow, "          name: athena-run-${{ github.run_id }}\n", "          name: " + ARTIFACT_EXPRESSION + "\n")
    sources[CANONICAL] = workflow
    return sources


def load_projection():
    """Trusted projected source only; never mutate installed production modules."""
    modules = {}
    for path, source in projected_sources().items():
        if path.endswith(".yml"):
            continue
        name = "_athena_core01d_schedule_design_" + Path(path).stem
        module = ModuleType(name)
        module.__file__ = str(ROOT / path)
        sys.modules[name] = module  # dataclass introspection needs its own namespace
        exec(compile(source, "<NON_DEPLOYED_PROJECTION:" + path + ">", "exec"), module.__dict__)
        modules[path] = module
    modules[PERSIST].resolve_workflow_request = modules[REQUEST].resolve_workflow_request
    modules[RESTORE].roles = modules[ROLES]
    return modules


def validate_workflow_design():
    projected = yaml.load(projected_sources()[CANONICAL], Loader=yaml.BaseLoader)
    current = yaml.load(raw(CANONICAL), Loader=yaml.BaseLoader)
    legacy = yaml.load(raw(LEGACY), Loader=yaml.BaseLoader)
    job = projected["jobs"]["canonical-run"]
    require(projected["on"] == current["on"] and set(projected["jobs"]) == {"canonical-run"}, "new workflow/trigger family or manual input drift")
    require("concurrency" not in projected and job["concurrency"] == {"group": GROUP_EXPRESSION, "cancel-in-progress": "false"}, "lane concurrency collision")
    require(job["strategy"] == {"fail-fast": "false", "matrix": {"lane": LANE_EXPRESSION}}, "lane cardinality drift")
    require(legacy["concurrency"]["group"] == "current-shadow-all-market", "legacy exclusion drift")
    steps = job["steps"]
    old = current["jobs"]["canonical-run"]["steps"]
    require([step.get("id") for step in steps] == [step.get("id") for step in old], "business/control-plane step ownership drift")
    for before, after in zip(old, steps):
        if before["id"] not in {"resolve_request", "upload_evidence"}:
            require(before == after, "projection changed non-schedule business step")
    upload = next(step for step in steps if step["id"] == "upload_evidence")
    require(upload["with"]["name"] == ARTIFACT_EXPRESSION, "artifact name collision")
    require(len(projected_sources()) == 5, "unbounded proposal scope")


def expected_receipt():
    inputs = verify_inputs()
    validate_workflow_design()
    modules = load_projection()
    adapter = modules[REQUEST]
    date_rows = []
    for clock in ("09:00", "22:59", "23:00"):
        now = datetime.fromisoformat("2026-10-01T" + clock + ":00+00:00")
        main = adapter.resolve_workflow_request(event_name="schedule", schedule_lane="main", now=now)
        old_main = predecessor.resolve_workflow_request(event_name="schedule", now=now)
        require(canonical_json_bytes(main) == canonical_json_bytes(old_main), "MAIN schedule byte regression")
        for intent in (False, True):
            try:
                request = adapter.resolve_workflow_request(event_name="schedule", schedule_lane="shadow",
                    scheduled_shadow_create_share_code=intent, now=now)
            except adapter.AthenaRunWorkflowRequestError:
                require(clock == "23:00", "unexpected scheduled UTC rejection")
                date_rows.append({"clock_utc": now.isoformat(), "create_share_code": intent,
                                  "status": "UNREPRESENTABLE_FAIL_CLOSED_BEFORE_PROVIDER", "request_sha256": None})
            else:
                require(clock != "23:00" and request.dates[0].isoformat() == "2026-10-01", "legacy UTC date shifted")
                date_rows.append({"clock_utc": now.isoformat(), "create_share_code": intent,
                                  "status": "EXACT_UTC_DATE_REPRESENTABLE", "request_sha256": request.canonical_sha256})
    predecessor_receipt = predecessor.strict(raw(predecessor.RECEIPT_PATH))
    require(predecessor_receipt["canonical_sha256"] == predecessor.CHECKPOINT_RECEIPT_SHA, "merged CORE-01D receipt drift")
    auth = predecessor.strict(raw("artifacts/architecture/auth_01_analysis_only_shadow_v1.json"))
    require(any(row.get("state") == "RETAINED_COMPATIBILITY_REQUIRES_EXPLICIT_INTENT_AND_SEPARATE_EXTERNAL_AUTHORIZATION" for row in auth["capability_snapshot"]), "delivery authority anchor changed")
    return predecessor.seal({
        "schema_version": 1, "policy_id": POLICY_ID, "exact_base_main_sha": BASE,
        "exact_final_head_derivation": "git rev-parse HEAD in audit output",
        "master_issue": 337, "predecessor_pr": 430, "predecessor_reviewed_head": "ff761afe51bb1ea94ef3acb7d1c5eab805468501",
        "predecessor_merge": BASE, "post_merge_state_comment": 5935622452,
        "predecessor_receipt_sha256": predecessor_receipt["canonical_sha256"],
        "source_review_counter_while_open": "1/5", "source_review_counter_if_merged": "2/5", "mandatory_reread_due": False,
        "design_status": "SOURCE_BOUND_OFFLINE_PROJECTION_NOT_DEPLOYED",
        "projection_owner": "EXISTING_CANONICAL_SEAMS_NO_SECOND_BUSINESS_EXECUTION_OWNER",
        "proposal_source_sha256": {path: predecessor.sha(source.encode()) for path, source in projected_sources().items()},
        "base_source_inventory_sha256": INPUT_SHA,
        "main_schedule_before_after": {"cron": "0 9 * * *", "profile": "MAIN", "mode": "main_application", "target": 20, "bookie": "sportybet", "create_share_code": False, "place_wager": False, "byte_parity": True, "active_change": False},
        "legacy_shadow_before": {"cron": "0 9 * * *", "utc_scope": "today", "target": 20, "create_share_code": True, "email": "OPTIONAL_SECONDARY", "active_after": "UNCHANGED"},
        "intended_shadow_request": {"profile": "SHADOW", "mode": "research_shadow", "target": 20, "odds": None, "bookie": "sportybet", "place_wager": False, "date_intent": "UTC_TODAY_CONCRETE_BEFORE_LAGOS_VALIDATION", "create_share_code": "EXACT_BOOL_REQUIRED_NO_DEFAULT_POLICY_UNDECIDED"},
        "date_matrix": date_rows, "date_shift": False,
        "delivery_disposition": "SCHEDULE_DELIVERY_POLICY_DECISION_REQUIRED",
        "delivery_authority_source": {"path": "artifacts/architecture/auth_01_analysis_only_shadow_v1.json", "sha256": auth["canonical_sha256"], "contract": "EXPLICIT_INTENT_AND_SEPARATE_EXTERNAL_AUTHORIZATION"},
        "delivery_options": {"true": "BYTE_INTENT_PARITY_TESTED_NOT_AUTHORIZED_AS_NEW_SCHEDULE_POLICY", "false": "INTENTIONAL_DEPRECATION_NOT_PARITY_REQUIRES_EXPLICIT_OWNER_POLICY"},
        "notification_disposition": "SCHEDULE_NOTIFICATION_DISPOSITION_REQUIRED",
        "notification_clearance": "OWNER_EXPLICIT_RETIREMENT_OR_REVIEWED_NON_AUTHORITATIVE_POST_CORE_CONSUMER_NO_DESKTOP",
        "concurrency_proposal": {"main": "athena-run-main", "shadow": "current-shadow-all-market", "legacy_manual_comment": "current-shadow-all-market", "placement": "JOB_LEVEL_SAME_GROUP_ACROSS_WORKFLOWS", "cancel_in_progress": False, "production": "UNCHANGED"},
        "artifact_name_proposal": {"manual_main": "athena-run-<run_id>", "manual_shadow": "athena-run-<run_id>", "scheduled_main": "athena-run-<run_id>", "scheduled_shadow": "athena-run-<run_id>-scheduled-shadow", "production": "UNCHANGED"},
        "restore_discovery_proposal": {"per_run_candidates": 1, "manual": "EXACT_OLD_NAME_ONLY", "schedule": "UNIQUE_LIVE_SUFFIX_FIRST_OLD_ONLY_IF_SUFFIX_ABSENT", "expired_suffix": "NO_DOWNGRADE_TO_MAIN", "duplicate_name": "FAIL_CLOSED", "wrong_event_suffix": "FAIL_CLOSED", "filename_eligibility": False},
        "manifest_schema_disposition": "V1_UNCHANGED_REQUEST_SHA_AND_EVENT_PLUS_TRANSPORT_IDENTITY_SUFFICIENT",
        "builder_disposition": "UNCHANGED_INTERNAL_HISTORICAL_NAME_VALIDATES_SAME_REQUEST_RUN_EVENT_NO_SCHEMA_FIELD_NEEDED",
        "historical_compatibility": "OLD_CANONICAL_AND_LEGACY_ROLE_PROVENANCE_UNCHANGED_ACCEPTED_LGA_RETAINED_FAILED_LGA_REJECTED_FORWARD",
        "schedule_cutover_status": "POLICY_BLOCKED_NOT_DEPLOYED", "legacy_schedule_trigger_removed": False,
        "canonical_scheduled_shadow_active": False, "dual_live_schedule": False,
        "manual_dispatch_changed": False, "issue_comment_changed": False,
        "evolution": {"transition_count": 11, "new_transition": False, "reason": "NO_PRODUCTION_OWNERSHIP_NAMING_OR_CONCURRENCY_CHANGE_MEMORY_ONLY_PROPOSAL", "future_cutover": "EXACTLY_ONE_APPEND_ONLY_TRANSITION_AND_NEW_SNAPSHOT_REQUIRED"},
        "cutover_gate": {"date_contract": True, "explicit_delivery_policy": False, "explicit_notification_policy": False,
                         "artifact_design": True, "concurrency_design": True, "production_deployment": False},
        "blockers": ["SCHEDULE_DELIVERY_POLICY_DECISION_REQUIRED", "SCHEDULE_NOTIFICATION_DISPOSITION_REQUIRED"],
        "blocker_2_scope": "CORE_01D_RETAINED_FAMILY_AUTHORITY_REACHABILITY_BLOCKER_UNTOUCHED",
        "p4_4_status": "INCOMPLETE", "checkpoint_e_status": "INCOMPLETE",
        "rollback_identities": {path: inputs["inputs"][path] for path in (CANONICAL, LEGACY, REQUEST, PERSIST, ROLES, RESTORE)},
        "side_effect_counts": dict.fromkeys(("provider", "live_run", "dispatch", "share_code_create", "share_code_reload", "delivery", "email", "login", "cookies", "wallet", "stake", "wager"), 0),
        "outside_control_plane_semantic_delta": 0,
    })


def audit():
    expected = expected_receipt()
    verified_receipt_path()
    require(predecessor.strict(raw(RECEIPT_PATH)) == expected, "scheduled-shadow receipt differs from independently rederived design")
    predecessor.audit()
    return {"result": "PASS", "design_status": expected["design_status"], "cutover": expected["schedule_cutover_status"],
            "exact_head": git("rev-parse", "HEAD").decode().strip(), "policy_id": POLICY_ID,
            "receipt_sha256": expected["canonical_sha256"], "blockers": expected["blockers"], "side_effect_counts": expected["side_effect_counts"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-base", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--export-proposal", type=Path)
    args = parser.parse_args()
    if args.capture_base:
        require(git("rev-parse", "HEAD").decode().strip() == BASE, "capture only on exact authorized base")
        paths = {CANONICAL, LEGACY, REQUEST, PERSIST, ROLES, RESTORE, OLD_AUDIT,
                 "scripts/build_athena_artifact_role_manifest.py", "services/athena_run_service.py", "scripts/execute_current_shadow_request.py",
                 "domain/current_shadow_fixture_date_request.py", "domain/current_shadow_run_contract_adapter.py",
                 "services/athena_run_request_parser.py", "services/athena_shadow_issue_comment_compatibility.py"}
        rows = git("ls-tree", "-r", "HEAD", "--", "artifacts/architecture", "artifacts/product").decode().splitlines()
        paths.update(row.split("\t", 1)[1] for row in rows)
        inputs = {path: {"git_blob_sha1": git("rev-parse", "HEAD:" + path).decode().strip()} for path in sorted(paths)}
        (ROOT / INPUT_PATH).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / BEFORE_AUDIT).write_bytes(git("show", "HEAD:" + OLD_AUDIT))
        value = predecessor.seal({"base_sha": BASE, "inputs": inputs})
        (ROOT / INPUT_PATH).write_bytes(predecessor.canonical(value))
        print(json.dumps({"input_sha": predecessor.sha(predecessor.canonical(value)), "input_count": len(inputs)}))
    elif args.write:
        value = expected_receipt()
        (ROOT / RECEIPT_PATH).write_bytes(predecessor.canonical(value))
        print(value["canonical_sha256"])
    elif args.export_proposal:
        verify_inputs()
        require(not args.export_proposal.exists(), "proposal export refuses overwrite")
        for path, text in projected_sources().items():
            target = args.export_proposal / (path + ".txt")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
        print("NON_DEPLOYED_PROPOSAL_ONLY", args.export_proposal)
    else:
        print(json.dumps(audit(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
