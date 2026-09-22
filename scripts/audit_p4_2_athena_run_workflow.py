"""Deterministically audit the offline P4.2 canonical workflow contract."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import socket
import subprocess
import tempfile
from typing import Any, Callable
from urllib import request as urllib_request
from zoneinfo import ZoneInfo

import yaml

from domain.run_contracts import (
    POLICY_ID as RUN_CONTRACT_POLICY_ID,
    RunReceipt,
    RunRequest,
    canonical_json_bytes,
)
from services.athena_run_request_parser import CLI_TIMEZONE_ID
from services.athena_run_service import AthenaRunService, ExecutorResult
from services.athena_run_workflow_request import (
    SCHEDULE_BOOKIE,
    SCHEDULE_DAYS,
    SCHEDULE_PROFILE,
    SCHEDULE_TARGET_LEGS,
    SCHEDULE_TARGET_TOTAL_ODDS,
    WORKFLOW_DISPATCH_DEFAULTS,
    WORKFLOW_INPUT_NAMES,
    resolve_workflow_request,
)
from scripts.resolve_athena_run_workflow_request import resolve_and_persist


SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_P4_2_ATHENA_RUN_WORKFLOW_V1"
BASE_MAIN_SHA = "d2db57cb5a68430d2d5222385abaf2d16f73ec62"
P4_1_RECEIPT_SHA256 = "268933433aaab84cb2533840f2e01eba96ec5906e796c9eced2032e1d6706208"
REGISTRY_CANONICAL_SHA256 = "74e79e216497c2e7f31a51e278251a5c62645e1085d04ebb8712022658f8f109"
FIXED_NOW = datetime(2026, 9, 22, 12, 30, tzinfo=ZoneInfo("Africa/Lagos"))
FIXED_COMMIT_SHA = BASE_MAIN_SHA
WORKFLOW_PATH = ".github/workflows/athena-run.yml"
DEFAULT_OUTPUT = Path("artifacts/architecture/p4_2_athena_run_workflow_v1.json")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# Git blob IDs captured from authoritative P4.2 base main. These remain stable
# across the Windows/Linux line-ending conversion used by local and hosted tests.
PRESERVED_FILE_GIT_BLOB_SHA1 = {
    "artifacts/architecture/runtime-reachability-v1.json": "0c840c9b245d0eb8610a62ac3cc8bbc3be1120a1",
    "artifacts/architecture/p3_1_main_canonical_core_promotion_v1.json": "421e7bb7a7ce154e9507672ddc881402f4b6d6a0",
    "artifacts/architecture/p3_1_main_caller_migration_v1.json": "66e4d0c0afe13ee91342e5fecb9bcf4dbf5e7a35",
    "artifacts/architecture/p3_2_frozen_v2_runtime_externalization_v1.json": "b88993fde2663afc2b1b88908292d79f1eba0e10",
    "tests/fixtures/architecture/p3_2_frozen_v2_policy_vectors_v1.json": "6d3abf80ecd7e0baad329f34e6dfe9330c15c390",
    "artifacts/architecture/p3_3_module_canonicalization_v1.json": "524d150c4c43a451d2a223e6a6de87f9d7ac9784",
    "artifacts/architecture/p4_1_cli_consolidation_v1.json": "7ef7309b805a091f3cb09f80bd2944c4f1fe10a1",
    "config/architecture/component-authority-registry-v1.json": "fbc812c6b5629efb2ac8f8b27380a585c2915689",
    ".github/workflows/current-shadow-all-market.yml": "4321d70563e98acaf1663f5a7b28781908535328",
    ".github/workflows/current-sportybet-accumulator.yml": "21400f2615a033c0b9df5dd943f469c0cae4c3e0",
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml": "1efe1e34d4459b2aeea17d5da8ba77bd4e2442f2",
    ".github/workflows/watch-fotmob-fresh-holdout-scheduler-liveness.yml": "f613211018417435cb4ad7a22529b1ff0a38d690",
    ".github/workflows/bridge-fotmob-fresh-holdout-continuity-receipts.yml": "d880f07fc7d5f407f9f4bdc7a7311bb89f713fd0",
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout-release-receipts.yml": "c34528d5bf21556d85585ed7c807b34ca5f7666f",
}
RETIRED_WORKFLOW_PATH = ".github/workflows/current-sportybet-accumulator.yml"
RETIRED_WORKFLOW_FIXTURE = "tests/fixtures/architecture/retired_workflows/current-sportybet-accumulator.yml"
RETIRED_WORKFLOW_SOURCE_SHA256 = "839925e6ad0ceee2452ef008da13d481bc34d445290444b30d6f0278510542c1"
FROZEN_P42_RECEIPT_SHA256 = "fa575a5bb5f4611eb94564b92dea3e4230b8d429b1660dc3bde3d6c164b836f8"


class P42AuditError(RuntimeError):
    """Raised when the P4.2 source or evidence contract drifts."""


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _normalized_source_sha256(path: Path) -> str:
    normalized = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def _git_blob_sha1(relative_path: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(REPOSITORY_ROOT), "rev-parse", f"HEAD:{relative_path}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise P42AuditError(f"could not resolve frozen Git blob for {relative_path}") from exc
    value = completed.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", value, re.ASCII) is None:
        raise P42AuditError(f"frozen Git blob identity is invalid for {relative_path}")
    return value


def verify_preserved_historical_sources() -> dict[str, str]:
    """Verify P4.2 identities without requiring a retired YAML at its live path."""
    try:
        raw = (REPOSITORY_ROOT / RETIRED_WORKFLOW_FIXTURE).read_bytes()
    except OSError as exc:
        raise P42AuditError("retired P4.2 workflow fixture is missing") from exc
    source_sha = hashlib.sha256(raw).hexdigest()
    blob_sha = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if source_sha != RETIRED_WORKFLOW_SOURCE_SHA256 or blob_sha != PRESERVED_FILE_GIT_BLOB_SHA1[RETIRED_WORKFLOW_PATH]:
        raise P42AuditError("retired P4.2 workflow fixture identity drifted")
    if (REPOSITORY_ROOT / RETIRED_WORKFLOW_PATH).exists():
        raise P42AuditError("retired P4.2 workflow remains at the live path")
    identities = {RETIRED_WORKFLOW_PATH: blob_sha}
    for relative, expected in PRESERVED_FILE_GIT_BLOB_SHA1.items():
        if relative == RETIRED_WORKFLOW_PATH:
            continue
        actual = _git_blob_sha1(relative)
        if actual != expected:
            raise P42AuditError(f"protected historical source changed: {relative}")
        identities[relative] = actual
    return identities


def _shadow_service_outer_timeout_present(source: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "_ShadowSupervisorExecutor":
            continue
        for method in node.body:
            if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) or method.name != "__call__":
                continue
            for child in ast.walk(method):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                    if (
                        child.func.attr == "run"
                        and isinstance(child.func.value, ast.Name)
                        and child.func.value.id == "subprocess"
                        and any(keyword.arg == "timeout" for keyword in child.keywords)
                    ):
                        return True
    return False


def _int_constant(node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        left = _int_constant(node.left)
        right = _int_constant(node.right)
        if left is not None and right is not None:
            return left * right
    return None


def _supervisor_timeout_constants() -> tuple[int | None, int | None]:
    source = (REPOSITORY_ROOT / "scripts/execute_current_shadow_all_market_fresh_reprice_bound.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    values: dict[str, int | None] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in {
                "HOSTED_SUPERVISOR_TIMEOUT_SECONDS", "WORKFLOW_JOB_TIMEOUT_SECONDS"
            }:
                values[target.id] = _int_constant(node.value)
    return values.get("HOSTED_SUPERVISOR_TIMEOUT_SECONDS"), values.get("WORKFLOW_JOB_TIMEOUT_SECONDS")


def _load_workflow() -> dict[str, Any]:
    try:
        value = yaml.load((REPOSITORY_ROOT / WORKFLOW_PATH).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise P42AuditError("canonical workflow YAML is missing or invalid") from exc
    if type(value) is not dict:
        raise P42AuditError("canonical workflow YAML root must be a mapping")
    return value


def _workflow_contract(workflow: dict[str, Any]) -> dict[str, Any]:
    triggers = workflow.get("on")
    if type(triggers) is not dict or set(triggers) != {"schedule", "workflow_dispatch"}:
        raise P42AuditError("athena-run triggers drifted")
    schedule = triggers["schedule"]
    if type(schedule) is not list or len(schedule) != 1 or schedule[0].get("cron") != "0 9 * * *":
        raise P42AuditError("athena-run schedule drifted")
    dispatch = triggers["workflow_dispatch"]
    inputs = dispatch.get("inputs") if type(dispatch) is dict else None
    if type(inputs) is not dict or tuple(sorted(inputs)) != WORKFLOW_INPUT_NAMES:
        raise P42AuditError("workflow_dispatch input vocabulary drifted")
    defaults = {key: str(value.get("default", "")) for key, value in inputs.items()}
    if defaults != dict(WORKFLOW_DISPATCH_DEFAULTS):
        raise P42AuditError("workflow_dispatch defaults differ from source resolver")
    if workflow.get("permissions") != {"contents": "read", "actions": "read"}:
        raise P42AuditError("workflow permissions are not exact read-only permissions")
    concurrency = workflow.get("concurrency")
    if type(concurrency) is not dict or concurrency.get("cancel-in-progress") != "false":
        raise P42AuditError("workflow concurrency/cancellation policy drifted")
    concurrency_group = concurrency.get("group", "")
    if "current-shadow-all-market" not in concurrency_group or "athena-run-main" not in concurrency_group:
        raise P42AuditError("workflow concurrency groups do not isolate Shadow/Main runs")

    jobs = workflow.get("jobs")
    job = jobs.get("canonical-run") if type(jobs) is dict else None
    if type(job) is not dict or job.get("timeout-minutes") != "90":
        raise P42AuditError("canonical workflow must retain the 90-minute job ceiling")
    steps = job.get("steps")
    if type(steps) is not list:
        raise P42AuditError("canonical workflow steps are missing")
    by_id = {step.get("id"): step for step in steps if type(step) is dict and step.get("id")}
    checkout = by_id.get("checkout", {})
    if checkout.get("uses") != "actions/checkout@v4" or checkout.get("with", {}).get("ref") != "${{ github.sha }}":
        raise P42AuditError("workflow checkout does not pin exact github.sha")
    setup = by_id.get("setup_python", {})
    if setup.get("uses") != "actions/setup-python@v5" or setup.get("with", {}).get("python-version") != "3.12":
        raise P42AuditError("workflow Python setup drifted")
    upload = by_id.get("upload_evidence", {})
    upload_with = upload.get("with", {})
    if (
        upload.get("uses") != "actions/upload-artifact@v4"
        or upload.get("if") != "always()"
        or upload_with.get("retention-days") != "30"
        or upload_with.get("name") != "athena-run-${{ github.run_id }}"
    ):
        raise P42AuditError("durable artifact upload policy drifted")

    step_ids = [step.get("id") for step in steps if type(step) is dict]
    required_order = ["verify_lineage", "resolve_request", "setup_python", "install_dependencies", "execute_request", "upload_evidence"]
    if any(item not in step_ids for item in required_order):
        raise P42AuditError("canonical workflow is missing a required transport step")
    positions = [step_ids.index(item) for item in required_order]
    if positions != sorted(positions):
        raise P42AuditError("request resolution must precede setup/install/execution/upload")
    execution = by_id["execute_request"].get("run", "")
    if "scripts.execute_athena_run_workflow" not in execution or "resolved-run-request.json" not in execution:
        raise P42AuditError("workflow execution does not consume persisted request")
    if "scripts.execute_current_shadow_request" in execution or "execute_current_sportybet_accumulator.py" in execution:
        raise P42AuditError("workflow bypasses AthenaRunService transport")
    all_run_text = "\n".join(step.get("run", "") for step in steps if type(step) is dict)
    for forbidden in (
        "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "RECIPIENT_EMAIL", "KellyCalculator",
        "MarketSelector", "AccaFilter", "AccumulatorEngine", "--stake", "--wager",
    ):
        if forbidden.casefold() in all_run_text.casefold():
            raise P42AuditError(f"workflow contains forbidden business/notification control: {forbidden}")
    workflow_text = json.dumps(workflow, sort_keys=True).casefold()
    for secret_name in ("gmail_address", "gmail_app_password", "recipient_email"):
        if secret_name in workflow_text:
            raise P42AuditError("notification credentials must remain outside the core workflow")
    for direct_path in (
        "scripts.execute_current_shadow_request",
        "scripts.execute_current_sportybet_accumulator",
        "build_acca.py",
    ):
        if direct_path.casefold() in workflow_text:
            raise P42AuditError("workflow bypasses the canonical AthenaRunService transport")
    install_position = step_ids.index("install_dependencies")
    if positions[1] >= install_position:
        raise P42AuditError("relative dates are not frozen before dependency installation")
    verify_run = by_id.get("verify_lineage", {}).get("run", "")
    if "git rev-parse HEAD" not in verify_run or "GITHUB_SHA" not in verify_run or "refs/heads/main" not in verify_run:
        raise P42AuditError("workflow does not bind exact checked-out main lineage")
    resolve_step = by_id.get("resolve_request", {})
    if (
        "scripts.resolve_athena_run_workflow_request" not in resolve_step.get("run", "")
        or resolve_step.get("env", {}).get("GITHUB_EVENT_NAME") != "${{ github.event_name }}"
        or "INPUT_DAYS" not in resolve_step.get("env", {})
    ):
        raise P42AuditError("workflow request resolver transport drifted")
    restore_history = by_id.get("restore_history_prime", {})
    history_run = restore_history.get("run", "")
    if any(token not in history_run for token in (
        "current-shadow-history-cache-prime.yml", "current-shadow-history-cache-prime",
        "restore_current_shadow_history_prime_artifact", "--expected-prime-commit-sha",
    )):
        raise P42AuditError("trusted-main history-prime restore contract is incomplete")
    restore_bootstrap = by_id.get("restore_pr119", {}).get("run", "")
    if any(token not in restore_bootstrap for token in (
        "athena-fresh-holdout-bootstrap-v1", "pr119-materialized.ndjson",
        "e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2",
    )):
        raise P42AuditError("fixed PR119 bootstrap restore contract is incomplete")
    restore_identity = by_id.get("restore_identity", {}).get("run", "")
    if any(token not in restore_identity for token in (
        "current-shadow-all-market.yml", "current-shadow-all-market-request",
        "current-shadow-fixture-identity-v2-state.json", "ATHENA_CURRENT_SHADOW_IDENTITY_STATE_PATH",
    )):
        raise P42AuditError("persistent Shadow identity restore contract is incomplete")
    lineage_run = by_id.get("bind_lineage_main", {}).get("run", "")
    if "git/ref/heads/main" not in lineage_run or "ATHENA_EXPECTED_LINEAGE_MAIN_SHA" not in lineage_run:
        raise P42AuditError("Shadow lineage-main binding is missing")
    preserved = by_id.get("preserve_shadow_evidence", {}).get("run", "")
    for family in (
        "current-shadow-sportybet-catalog-fanout",
        "current-shadow-sportybet-upcoming-discovery",
        "sportybet-live-event-quote-evidence",
        "fotmob-data-matches-captures",
        "identity-state",
    ):
        if family not in preserved:
            raise P42AuditError(f"Shadow evidence-preservation family is missing: {family}")
    upload_paths = upload_with.get("path", "")
    if "artifacts/athena-run-workflow" not in upload_paths or "artifacts/athena-runs" not in upload_paths:
        raise P42AuditError("workflow artifact upload paths are incomplete")
    preservation = by_id.get("preserve_shadow_evidence", {})
    if preservation.get("if") != "always() && steps.resolve_request.outputs.authority_profile == 'SHADOW'":
        raise P42AuditError("Shadow evidence preservation is not unconditional after resolution")
    propagate = by_id.get("propagate_failure", {})
    if (
        propagate.get("if") != "always()"
        or step_ids.index("propagate_failure") <= step_ids.index("upload_evidence")
        or "EXECUTION_EXIT_CODE" not in propagate.get("env", {})
    ):
        raise P42AuditError("control-plane failure is not propagated after artifact upload")

    return {
        "workflow": workflow,
        "triggers": ["schedule", "workflow_dispatch"],
        "cron": schedule[0]["cron"],
        "inputs": list(sorted(inputs)),
        "permissions": {"contents": "read", "actions": "read"},
        "concurrency_group": concurrency_group,
        "steps": steps,
        "job": job,
    }


def _synthetic_parity_proof() -> dict[str, Any]:
    network_attempts: list[str] = []
    original_connect = socket.socket.connect
    original_create_connection = socket.create_connection
    original_urlopen = urllib_request.urlopen

    def deny_network(name: str) -> Callable[..., Any]:
        def blocked(*_args: Any, **_kwargs: Any) -> Any:
            network_attempts.append(name)
            raise AssertionError("network access is forbidden in the P4.2 audit")

        return blocked

    socket.socket.connect = deny_network("socket.connect")  # type: ignore[method-assign]
    socket.create_connection = deny_network("socket.create_connection")  # type: ignore[assignment]
    urllib_request.urlopen = deny_network("urllib.urlopen")  # type: ignore[assignment]
    try:
        calls: list[str] = []
        persisted_before_executor: list[bool] = []

        def synthetic_executor(
            request: RunRequest,
            *,
            authority_manifest,
            run_directory: Path,
            exact_commit_sha: str,
            observed_at: datetime,
        ) -> ExecutorResult:
            calls.append(request.canonical_sha256)
            request_file = run_directory / "athena-run-request.json"
            persisted_before_executor.append(
                request_file.is_file() and request_file.read_bytes() == canonical_json_bytes(request)
            )
            return ExecutorResult(
                status="MAIN_PHASE6_AUTHORITY_REQUIRED",
                evidence={
                    "synthetic": True,
                    "provider_acquisition": authority_manifest.provider_acquisition,
                    "share_code_generation": authority_manifest.share_code_generation,
                    "exact_commit_sha": exact_commit_sha,
                    "observed_at": observed_at.isoformat(timespec="microseconds"),
                },
            )

        service = AthenaRunService(
            _test_executor_overrides={
                ("MAIN", "main_application", "sportybet"): synthetic_executor,
            },
            _commit_sha_provider=lambda: FIXED_COMMIT_SHA,
            _clock=lambda: FIXED_NOW,
        )
        dispatch = dict(WORKFLOW_DISPATCH_DEFAULTS)
        with tempfile.TemporaryDirectory(prefix="athena-p4-2-parity-") as temporary:
            root = Path(temporary)
            manual_root = root / "workflow_dispatch"
            schedule_root = root / "schedule"
            manual, _manual_meta = resolve_and_persist(
                event_name="workflow_dispatch",
                dispatch_inputs=dispatch,
                github_sha=FIXED_COMMIT_SHA,
                github_ref="refs/heads/main",
                output_root=manual_root,
                now=FIXED_NOW,
            )
            manual_from_disk = RunRequest.from_json_bytes(
                (manual_root / "resolved-run-request.json").read_bytes()
            )
            manual_receipt = service.run(manual_from_disk, output_root=manual_root / "runs")
            manual_replay = service.run(manual_from_disk, output_root=manual_root / "runs")

            scheduled, _schedule_meta = resolve_and_persist(
                event_name="schedule",
                dispatch_inputs=None,
                github_sha=FIXED_COMMIT_SHA,
                github_ref="refs/heads/main",
                output_root=schedule_root,
                now=FIXED_NOW,
            )
            scheduled_from_disk = RunRequest.from_json_bytes(
                (schedule_root / "resolved-run-request.json").read_bytes()
            )
            scheduled_receipt = service.run(scheduled_from_disk, output_root=schedule_root / "runs")
            manual_bytes = canonical_json_bytes(manual_receipt)
            scheduled_bytes = canonical_json_bytes(scheduled_receipt)
            if type(manual_receipt) is not RunReceipt or type(scheduled_receipt) is not RunReceipt:
                raise P42AuditError("synthetic service did not return exact RunReceipt")
            if (
                manual != scheduled
                or manual_from_disk != manual
                or scheduled_from_disk != scheduled
                or canonical_json_bytes(manual) != canonical_json_bytes(scheduled)
            ):
                raise P42AuditError("scheduled/manual default RunRequest bytes differ")
            if manual_receipt.request != manual or scheduled_receipt.request != scheduled:
                raise P42AuditError("synthetic receipt does not bind the resolved request")
            if manual_receipt.exact_commit_sha != FIXED_COMMIT_SHA or scheduled_receipt.exact_commit_sha != FIXED_COMMIT_SHA:
                raise P42AuditError("synthetic receipt does not bind the exact fixed commit")
            if manual_bytes != scheduled_bytes or manual_receipt.to_dict().keys() != scheduled_receipt.to_dict().keys():
                raise P42AuditError("scheduled/manual synthetic receipt schema or bytes differ")
            if manual_replay != manual_receipt or calls != [manual.canonical_sha256, scheduled.canonical_sha256]:
                raise P42AuditError("synthetic replay/idempotency behavior drifted")
            if not all(persisted_before_executor):
                raise P42AuditError("resolved request was not persisted before synthetic execution")
            for receipt in (manual_receipt, scheduled_receipt):
                if (
                    receipt.counts["selected_leg_count"] != 0
                    or receipt.shortfall != receipt.request.target_legs
                    or receipt.share_code_result is not None
                    or receipt.wager_placed is not False
                    or receipt.authority_manifest.provider_acquisition is not False
                    or receipt.authority_manifest.share_code_generation is not False
                ):
                    raise P42AuditError("synthetic default receipt carries unsupported authority/result")

            shadow_override = resolve_workflow_request(
                event_name="workflow_dispatch",
                dispatch_inputs={
                    "days": "tomorrow,thursday",
                    "target_legs": "25",
                    "target_total_odds": "",
                    "bookie": "sportybet",
                    "profile": "shadow",
                },
                now=FIXED_NOW,
            )
            return {
                "network_attempt_count": len(network_attempts),
                "provider_acquisition": False,
                "share_code_operation": False,
                "wager_placed": False,
                "manual_request_sha": manual.canonical_sha256,
                "scheduled_request_sha": scheduled.canonical_sha256,
                "manual_receipt_sha": manual_receipt.canonical_sha256,
                "scheduled_receipt_sha": scheduled_receipt.canonical_sha256,
                "request_bytes_identical": canonical_json_bytes(manual) == canonical_json_bytes(scheduled),
                "receipt_bytes_identical": manual_bytes == scheduled_bytes,
                "schema_equal": tuple(manual_receipt.to_dict()) == tuple(scheduled_receipt.to_dict()),
                "manual_status": manual_receipt.status,
                "scheduled_status": scheduled_receipt.status,
                "synthetic_executor_call_count": len(calls),
                "request_persisted_before_executor": all(persisted_before_executor),
                "idempotent_replay": manual_replay == manual_receipt,
                "manual_shadow_override": shadow_override.to_dict(),
                "manual_shadow_dispatched": False,
            }
    finally:
        socket.socket.connect = original_connect  # type: ignore[method-assign]
        socket.create_connection = original_create_connection  # type: ignore[assignment]
        urllib_request.urlopen = original_urlopen  # type: ignore[assignment]


def build_receipt() -> dict[str, Any]:
    if RUN_CONTRACT_POLICY_ID != "ATHENA_CANONICAL_RUN_CONTRACT_V1":
        raise P42AuditError("RunRequest/RunReceipt policy identity drifted")
    if CLI_TIMEZONE_ID != "Africa/Lagos":
        raise P42AuditError("P4.1 parser timezone identity drifted")
    preserved_blobs: dict[str, str] = {}
    for relative, expected in PRESERVED_FILE_GIT_BLOB_SHA1.items():
        actual = _git_blob_sha1(relative)
        if actual != expected:
            raise P42AuditError(f"protected historical source changed: {relative}")
        preserved_blobs[relative] = actual

    p4_1_path = REPOSITORY_ROOT / "artifacts/architecture/p4_1_cli_consolidation_v1.json"
    try:
        p4_1_receipt = json.loads(p4_1_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise P42AuditError("P4.1 source receipt is unreadable") from exc
    p4_1_unsigned = dict(p4_1_receipt)
    p4_1_stored_sha = p4_1_unsigned.pop("canonical_sha256", None)
    timeout_evidence = p4_1_receipt.get("shadow_timeout_budget_proof", {})
    if (
        p4_1_stored_sha != P4_1_RECEIPT_SHA256
        or canonical_sha256(p4_1_unsigned) != p4_1_stored_sha
        or timeout_evidence.get("reviewed_inner_supervisor_seconds") != 4500
        or timeout_evidence.get("outer_equal_timeout_present") is not False
    ):
        raise P42AuditError("P4.1 timeout ownership receipt identity or semantics drifted")

    workflow_facts = _workflow_contract(_load_workflow())
    scheduled = resolve_workflow_request(event_name="schedule", now=FIXED_NOW)
    manual = resolve_workflow_request(
        event_name="workflow_dispatch",
        dispatch_inputs=dict(WORKFLOW_DISPATCH_DEFAULTS),
        now=FIXED_NOW,
    )
    manual_schedule_identical = canonical_json_bytes(scheduled) == canonical_json_bytes(manual)
    if not manual_schedule_identical:
        raise P42AuditError("scheduled and default manual canonical requests differ")
    scheduled_manifest = AthenaRunService.authority_manifest_for(scheduled)
    if (
        scheduled.authority_profile != "MAIN"
        or scheduled.mode != "main_application"
        or scheduled.target_legs != 20
        or scheduled.target_total_odds is not None
        or scheduled_manifest.provider_acquisition is not False
        or scheduled_manifest.share_code_generation is not False
        or scheduled.place_wager is not False
    ):
        raise P42AuditError("scheduled defaults are not the source-controlled fail-closed MAIN request")
    proof = _synthetic_parity_proof()
    if proof["network_attempt_count"] != 0:
        raise P42AuditError("offline parity proof attempted network access")
    if proof["manual_shadow_dispatched"] is not False:
        raise P42AuditError("manual SHADOW was dispatched during offline proof")

    service_source = (REPOSITORY_ROOT / "services/athena_run_service.py").read_text(encoding="utf-8")
    if _shadow_service_outer_timeout_present(service_source):
        raise P42AuditError("P4.1 Current Shadow timeout ownership changed")
    inner_timeout, reviewed_workflow_timeout = _supervisor_timeout_constants()
    if inner_timeout != 75 * 60 or reviewed_workflow_timeout != 90 * 60:
        raise P42AuditError("reviewed Current Shadow 75/90-minute operating budget changed")
    job_timeout = int(workflow_facts["job"].get("timeout-minutes", "0"))
    if job_timeout != 90 or job_timeout <= 75:
        raise P42AuditError("workflow timeout does not preserve the reviewed supervisor headroom")

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "repository_base_main_sha": BASE_MAIN_SHA,
        "p4_1_receipt_sha256": P4_1_RECEIPT_SHA256,
        "component_registry_canonical_sha256": REGISTRY_CANONICAL_SHA256,
        "run_contract_policy_id": RUN_CONTRACT_POLICY_ID,
        "workflow_path": WORKFLOW_PATH,
        "workflow_name": workflow_facts["workflow"].get("name"),
        "workflow_source_lf_sha256": _normalized_source_sha256(REPOSITORY_ROOT / WORKFLOW_PATH),
        "auditor_source_lf_sha256": _normalized_source_sha256(Path(__file__)),
        "triggers": workflow_facts["triggers"],
        "schedule_cron": workflow_facts["cron"],
        "scheduled_default_request": scheduled.to_dict(),
        "scheduled_default_request_sha256": scheduled.canonical_sha256,
        "workflow_dispatch_default_request": manual.to_dict(),
        "workflow_dispatch_default_request_sha256": manual.canonical_sha256,
        "manual_schedule_default_request_bytes_identical": manual_schedule_identical,
        "workflow_dispatch_inputs": workflow_facts["inputs"],
        "permissions": workflow_facts["permissions"],
        "write_permissions": [],
        "concurrency": {
            "cancel_in_progress": False,
            "shadow_group": "current-shadow-all-market",
            "main_group": "athena-run-main",
            "expression": workflow_facts["concurrency_group"],
        },
        "job_timeout_minutes": job_timeout,
        "reviewed_shadow_supervisor_minutes": 75,
        "timeout_headroom_minutes": job_timeout - 75,
        "equal_outer_service_timeout_present": False,
        "checkout_exact_github_sha": True,
        "operational_ref_restricted_to_main": True,
        "python_version": "3.12",
        "workflow_resolver_module": "services.athena_run_workflow_request.resolve_workflow_request",
        "resolution_script": "scripts.resolve_athena_run_workflow_request",
        "workflow_executor_script": "scripts.execute_athena_run_workflow",
        "resolution_script_lf_sha256": _normalized_source_sha256(REPOSITORY_ROOT / "scripts/resolve_athena_run_workflow_request.py"),
        "executor_script_lf_sha256": _normalized_source_sha256(REPOSITORY_ROOT / "scripts/execute_athena_run_workflow.py"),
        "workflow_resolver_lf_sha256": _normalized_source_sha256(REPOSITORY_ROOT / "services/athena_run_workflow_request.py"),
        "athena_run_service_lf_sha256": _normalized_source_sha256(REPOSITORY_ROOT / "services/athena_run_service.py"),
        "relative_dates_resolved_once": True,
        "execution_reparses_relative_dates": False,
        "persisted_request_path": "artifacts/athena-run-workflow/resolved-run-request.json",
        "artifact_name_pattern": "athena-run-${{ github.run_id }}",
        "artifact_paths": ["artifacts/athena-run-workflow", "artifacts/athena-runs"],
        "artifact_retention_days": 30,
        "upload_if_always": True,
        "shadow_restore_contract": {
            "history_prime": True,
            "pr119_bootstrap": True,
            "persistent_identity": True,
            "lineage_main": True,
        },
        "scheduled_provider_acquisition": scheduled_manifest.provider_acquisition,
        "scheduled_share_code_generation": scheduled_manifest.share_code_generation,
        "scheduled_profile": "MAIN",
        "manual_shadow_supported": True,
        "manual_shadow_dispatched_during_p4_2_proof": False,
        "legacy_current_shadow_workflow_changed": False,
        "legacy_current_sportybet_workflow_changed": False,
        "workflow_retirement_started": False,
        "workflow_retirement_deferred_to_p4_3": True,
        "protected_fresh_holdout_workflows_changed": False,
        "notification_in_core_workflow": False,
        "notification_migration_status": "PENDING_P4_3_CAPABILITY_MAPPING",
        "manual_schedule_request_schema_identical": proof["schema_equal"],
        "manual_schedule_request_byte_identical": proof["request_bytes_identical"],
        "manual_schedule_receipt_schema_identical": proof["schema_equal"],
        "manual_schedule_receipt_byte_identical": proof["receipt_bytes_identical"],
        "offline_synthetic_proof": proof,
        "historical_artifacts_changed": False,
        "historical_file_git_blob_sha1": preserved_blobs,
        "p4_1_receipt_changed": False,
        "component_registry_changed": False,
        "model_formula_changed": False,
        "probability_formula_changed": False,
        "calibration_formula_changed": False,
        "price_all_formula_changed": False,
        "router_formula_changed": False,
        "portfolio_formula_changed": False,
        "provider_semantics_changed": False,
        "share_code_semantics_changed": False,
        "provider_acquisition": False,
        "current_shadow_triggered": False,
        "fresh_holdout_triggered": False,
        "p3_0_e1_triggered": False,
        "real_share_code_operation": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "wager_placed": False,
        "p4_2_exit_gate_satisfied": True,
        "p4_3_started": False,
        "next_required_step": "P4_3_WORKFLOW_CAPABILITY_MIGRATION_AND_RETIREMENT_REQUIRED",
        "source_review_completed_before_p4_2": True,
        "source_review_counter_while_unmerged": "0/5",
        "source_review_counter_if_merged": "1/5",
    }
    if not receipt["p4_2_exit_gate_satisfied"]:
        raise P42AuditError("P4.2 exit gate did not pass")
    receipt["canonical_sha256"] = canonical_sha256(receipt)
    return receipt


def verify_committed_receipt(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_OUTPUT
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise P42AuditError("committed P4.2 receipt is unreadable") from exc
    if type(payload) is not dict:
        raise P42AuditError("committed P4.2 receipt must be an object")
    stored_sha = payload.get("canonical_sha256")
    unsigned = dict(payload)
    unsigned.pop("canonical_sha256", None)
    if type(stored_sha) is not str or stored_sha != FROZEN_P42_RECEIPT_SHA256 or canonical_sha256(unsigned) != stored_sha:
        raise P42AuditError("P4.2 receipt canonical SHA failed verification")
    if (
        payload.get("policy_id") != POLICY_ID
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("repository_base_main_sha") != BASE_MAIN_SHA
        or payload.get("p4_1_receipt_sha256") != P4_1_RECEIPT_SHA256
        or payload.get("component_registry_canonical_sha256") != REGISTRY_CANONICAL_SHA256
        or payload.get("p4_2_exit_gate_satisfied") is not True
    ):
        raise P42AuditError("P4.2 receipt identity/exit gate failed")
    if payload.get("offline_synthetic_proof", {}).get("network_attempt_count") != 0:
        raise P42AuditError("P4.2 receipt records offline network attempts")
    for flag in (
        "provider_acquisition", "current_shadow_triggered", "fresh_holdout_triggered",
        "p3_0_e1_triggered", "real_share_code_operation", "login", "cookies",
        "wallet", "staking", "wager_placed", "component_registry_changed",
        "p4_1_receipt_changed", "workflow_retirement_started", "notification_in_core_workflow",
    ):
        if payload.get(flag) is not False:
            raise P42AuditError(f"P4.2 receipt safety/state flag is not false: {flag}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        committed = verify_committed_receipt(args.output)
        if committed.get("historical_file_git_blob_sha1") != verify_preserved_historical_sources():
            raise SystemExit("P4.2 historical source identities differ from the frozen receipt")
        print(committed["canonical_sha256"])
        return 0
    raise SystemExit("P4.2 receipt is a frozen historical checkpoint; use --check")


if __name__ == "__main__":
    raise SystemExit(main())
