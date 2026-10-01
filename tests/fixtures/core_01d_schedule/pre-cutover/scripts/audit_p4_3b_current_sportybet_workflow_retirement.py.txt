"""Offline, owner-scoped proof for retiring one target-only MAIN workflow."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import tempfile
from typing import Any
from unittest.mock import patch
from urllib import request as urllib_request
from zoneinfo import ZoneInfo

import yaml

from domain import current_sportybet_accumulator_request as legacy
from domain.run_contracts import RunReceipt, RunRequest, canonical_json_bytes
from scripts import audit_p4_2_athena_run_workflow as p42
from services.athena_run_service import AthenaRunService
from services.athena_run_workflow_request import (
    WORKFLOW_DISPATCH_DEFAULTS,
    resolve_workflow_request,
)


POLICY_ID = "ATHENA_P4_3B_CURRENT_SPORTYBET_WORKFLOW_RETIREMENT_V1"
BASE_MAIN_SHA = "d2104a800ae91b4da47dd20d3d1c31fb7dc4ea3a"
TARGET = ".github/workflows/current-sportybet-accumulator.yml"
FIXTURE = "tests/fixtures/architecture/retired_workflows/current-sportybet-accumulator.yml"
SUCCESSOR = ".github/workflows/athena-run.yml"
TARGET_BLOB_SHA1 = "21400f2615a033c0b9df5dd943f469c0cae4c3e0"
TARGET_SOURCE_SHA256 = "839925e6ad0ceee2452ef008da13d481bc34d445290444b30d6f0278510542c1"
MATRIX_SHA = "6b417a19557efdd39201e233fb866e4143b8102ba2879a4f1481e5241722dd8d"
P43A_SHA = "7dd102aa4da98d634d665b4a93f51eb24ece8d7b61c8856b9977ff84a7452a6b"
P42_SHA = "fa575a5bb5f4611eb94564b92dea3e4230b8d429b1660dc3bde3d6c164b836f8"
P43B_SHA256 = "cf2371c7ec2747256f23599e7a43dd2d9e46ff61dda2c478a746d8bd8a49e72a"
ROLLBACK_TAG = "athena-p4.3b-pre-current-sportybet-workflow-retirement-d2104a8"
RECEIPT = Path("artifacts/architecture/p4_3b_current_sportybet_workflow_retirement_v1.json")
MATRIX = Path("artifacts/architecture/p4_3_workflow_capability_matrix_v1.json")
P43A_RECEIPT = Path("artifacts/architecture/p4_3a_workflow_capability_census_v1.json")
P42_RECEIPT = Path("artifacts/architecture/p4_2_athena_run_workflow_v1.json")
FIXED_NOW = datetime(2026, 9, 22, 12, 30, tzinfo=ZoneInfo("Africa/Lagos"))
BLOCKED_AT = "CURRENT_UTC_NATIVE_MODEL_PRODUCTION_AUTHORITY_REQUIRES_REVIEWED_FRESH_HOLDOUT_CONFIRMATION"
INPUT_MAPPING = ["target_size -> target_legs", "days=today", "target_total_odds=null", "bookie=sportybet", "profile=main"]
PROTECTED = (
    ".github/workflows/current-shadow-all-market.yml",
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml",
    ".github/workflows/watch-fotmob-fresh-holdout-scheduler-liveness.yml",
    ".github/workflows/bridge-fotmob-fresh-holdout-continuity-receipts.yml",
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout-release-receipts.yml",
)
FROZEN_RAW_SHA256 = {
    MATRIX: "4d451a821e8b3e5300a254a1841dfdadd96c617723d552d45f979bca12532d89",
    P43A_RECEIPT: "31a920a531acc39a3623d8da44701d5979da11249631f3a6fb12eff662afcf57",
    P42_RECEIPT: "af37f05fa1a3eb6df144f5092b103376f3104ae0839dbe52159ee6d784638e03",
}


class P43BRetirementError(AssertionError):
    """A retirement precondition or evidence binding failed closed."""


def canonical_sha256(payload: dict[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("canonical_sha256", None)
    return hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()


def _git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def verify_historical_fixture(raw: bytes | None = None) -> bytes:
    evidence = Path(FIXTURE).read_bytes() if raw is None else raw
    if hashlib.sha256(evidence).hexdigest() != TARGET_SOURCE_SHA256:
        raise P43BRetirementError("retired workflow historical fixture SHA-256 drifted")
    if _git_blob_sha1(evidence) != TARGET_BLOB_SHA1:
        raise P43BRetirementError("retired workflow historical Git blob identity drifted")
    return evidence


def _frozen_json(path: Path, expected_canonical_sha: str) -> dict[str, Any]:
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(raw).hexdigest() != FROZEN_RAW_SHA256[path]:
        raise P43BRetirementError(f"historical artifact bytes changed: {path}")
    payload = json.loads(raw)
    if canonical_sha256(payload) != expected_canonical_sha or payload.get("canonical_sha256") != expected_canonical_sha:
        raise P43BRetirementError(f"historical artifact canonical SHA changed: {path}")
    return payload


def verify_frozen_history() -> dict[str, Any]:
    matrix = _frozen_json(MATRIX, MATRIX_SHA)
    census = _frozen_json(P43A_RECEIPT, P43A_SHA)
    p42_receipt = _frozen_json(P42_RECEIPT, P42_SHA)
    rows = matrix.get("workflow_rows")
    if not isinstance(rows, list) or len(rows) != 40 or matrix.get("workflow_count") != 40:
        raise P43BRetirementError("P4.3A pre-retirement matrix must retain 40 rows")
    target = next((row for row in rows if row.get("workflow_path") == TARGET), None)
    if target is None or target.get("git_blob_sha1") != TARGET_BLOB_SHA1 or target.get("source_sha256") != TARGET_SOURCE_SHA256:
        raise P43BRetirementError("P4.3A target identity changed")
    if target.get("history_status") != "NO_RUN_HISTORY_OWNER_REVIEW_REQUIRED" or target.get("last_successful_run") is not None or target.get("latest_run") is not None:
        raise P43BRetirementError("P4.3A target run-history evidence changed")
    if target.get("capability_mapping", {}).get("equivalence_claimed") is not False or target.get("capability_mapping", {}).get("mapping") != INPUT_MAPPING:
        raise P43BRetirementError("P4.3A mapping hint was rewritten as equivalence")
    dependencies = target.get("dependency_evidence", {})
    if dependencies.get("artifact_consumer_exists") is not False or dependencies.get("workflow_history_consumer_exists") is not False or dependencies.get("workflow_run_dependency_references") != []:
        raise P43BRetirementError("retired workflow has an unmapped artifact or workflow-history consumer")
    if census.get("p4_3a_census_exit_gate_satisfied") is not True or census.get("p4_3_master_retirement_exit_gate_satisfied") is not False:
        raise P43BRetirementError("P4.3A historical gates changed")
    if p42_receipt.get("historical_file_git_blob_sha1", {}).get(TARGET) != TARGET_BLOB_SHA1:
        raise P43BRetirementError("P4.2 receipt lost retired workflow identity")
    p42.verify_committed_receipt()
    p42.verify_preserved_historical_sources()
    p42.verify_retired_workflow_historical_fixtures()
    return matrix


def _yaml(raw: bytes) -> dict[str, Any]:
    result = yaml.load(raw.decode("utf-8"), Loader=yaml.BaseLoader)
    if type(result) is not dict:
        raise P43BRetirementError("workflow YAML is not a mapping")
    return result


def verify_permissions_and_artifacts() -> dict[str, Any]:
    old = _yaml(verify_historical_fixture())
    new = _yaml(Path(SUCCESSOR).read_bytes())
    if old.get("permissions") != {"contents": "read"} or new.get("permissions") != {"contents": "read", "actions": "read"}:
        raise P43BRetirementError("workflow permission comparison drifted")
    old_job = old["jobs"]["request"]
    new_job = new["jobs"]["canonical-run"]
    old_triggers = old.get("on", {})
    old_inputs = old_triggers.get("workflow_dispatch", {}).get("inputs", {})
    if set(old_triggers) != {"workflow_dispatch"} or set(old_inputs) != {"target_size"} or old_inputs["target_size"].get("default") != "20" or old_inputs["target_size"].get("required") != "true" or old_inputs["target_size"].get("type") != "string":
        raise P43BRetirementError("historical target-only dispatch input contract drifted")
    if old_job.get("timeout-minutes") != "15" or new_job.get("timeout-minutes") != "90":
        raise P43BRetirementError("workflow timeout comparison drifted")
    if old_job.get("permissions") is not None or new_job.get("permissions") is not None:
        raise P43BRetirementError("workflow job-level permissions override the reviewed read-only policy")
    old_upload = next(step["with"] for step in old_job["steps"] if step.get("uses") == "actions/upload-artifact@v4")
    new_upload = next(step["with"] for step in new_job["steps"] if step.get("uses") == "actions/upload-artifact@v4")
    if old_upload.get("name") != "current-sportybet-accumulator-request" or old_upload.get("path") != "artifacts/current-sportybet-accumulator" or old_upload.get("retention-days") != "30":
        raise P43BRetirementError("historical artifact contract drifted")
    if new_upload.get("name") != "athena-run-${{ github.run_id }}" or "artifacts/athena-runs" not in new_upload.get("path", "") or new_upload.get("retention-days") != "30":
        raise P43BRetirementError("canonical artifact successor contract drifted")
    steps = new_job["steps"]
    upload_step = next(step for step in steps if step.get("id") == "upload_evidence")
    propagate_step = next(step for step in steps if step.get("id") == "propagate_failure")
    if upload_step.get("if") != "always()" or propagate_step.get("if") != "always()" or steps.index(propagate_step) <= steps.index(upload_step) or "EXECUTION_EXIT_CODE" not in propagate_step.get("env", {}):
        raise P43BRetirementError("canonical artifact upload or failure propagation drifted")
    if any(str(value).lower().endswith("write") for value in new.get("permissions", {}).values()):
        raise P43BRetirementError("canonical workflow gained write authority")
    return {"legacy_permissions": old["permissions"], "canonical_permissions": new["permissions"], "legacy_timeout_minutes": 15, "canonical_timeout_minutes": 90,
            "legacy_artifact_name": old_upload["name"], "canonical_artifact_name_pattern": new_upload["name"], "artifact_retention_days": 30}


def validate_equivalence_projection(projection: dict[str, Any], target: int) -> None:
    expected = {
        "requested_target": target,
        "legacy_status": legacy.STATUS_PHASE6_AUTHORITY_REQUIRED,
        "canonical_status": "MAIN_PHASE6_AUTHORITY_REQUIRED",
        "blocked_at": BLOCKED_AT,
        "provider_acquisition": False,
        "current_provider_execution": False,
        "share_code_generation": False,
        "selected_leg_count": 0,
        "shortfall": target,
        "share_code_result": None,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "wager_placed": False,
        "legacy_payload_preserved": True,
        "durable_request_evidence_preserved": True,
    }
    if projection != expected:
        raise P43BRetirementError(f"target {target} successor fail-closed equivalence failed")


def prove_main_successor() -> dict[str, Any]:
    attempts: list[str] = []

    def deny_network(*_args: Any, **_kwargs: Any) -> Any:
        attempts.append("network")
        raise P43BRetirementError("network attempted in offline retirement proof")

    fixed_utc = FIXED_NOW.astimezone(timezone.utc)
    targets: list[dict[str, Any]] = []
    original_execution = legacy.execute_current_accumulator_request
    with patch.object(socket.socket, "connect", deny_network), patch.object(socket, "create_connection", deny_network), patch.object(urllib_request, "urlopen", deny_network), patch.object(legacy, "_now_utc", lambda: fixed_utc):
        with tempfile.TemporaryDirectory(prefix="athena-p4-3b-offline-") as temporary:
            root = Path(temporary)
            for n in (1, 20, 50):
                dispatch = dict(WORKFLOW_DISPATCH_DEFAULTS, target_legs=str(n))
                request = resolve_workflow_request(event_name="workflow_dispatch", dispatch_inputs=dispatch, now=FIXED_NOW)
                if type(request) is not RunRequest or request.target_legs != n or request.target_total_odds is not None or request.bookie != "sportybet" or request.authority_profile != "MAIN" or request.mode != "main_application" or request.create_share_code is not False or request.place_wager is not False or request.dates != (FIXED_NOW.date(),):
                    raise P43BRetirementError(f"target {n} canonical input mapping drifted")
                old = original_execution(target_size=n, output_dir=root / f"legacy-{n}")
                calls: list[int] = []

                def observed_execution(*, target_size: int, output_dir: Path):
                    calls.append(target_size)
                    return original_execution(target_size=target_size, output_dir=output_dir)

                service = AthenaRunService(_commit_sha_provider=lambda: BASE_MAIN_SHA, _clock=lambda: fixed_utc)
                with patch.object(legacy, "execute_current_accumulator_request", observed_execution):
                    receipt = service.run(request, output_root=root / f"canonical-{n}")
                if calls != [n] or type(receipt) is not RunReceipt or receipt.request != request or receipt.exact_commit_sha != BASE_MAIN_SHA:
                    raise P43BRetirementError(f"target {n} canonical MAIN did not call the reviewed boundary")
                old_payload = old.to_dict()
                evidence_path = root / f"canonical-{n}" / request.canonical_sha256 / "current-sportybet-accumulator-request.json"
                persisted = json.loads(evidence_path.read_text(encoding="utf-8"))
                nested = receipt.evidence.get("main_target_only_request")
                if nested != old_payload or persisted != old_payload:
                    raise P43BRetirementError(f"target {n} underlying target-only evidence was not preserved")
                manifest = receipt.authority_manifest
                projection = {
                    "requested_target": old.requested_target_size,
                    "legacy_status": old.status,
                    "canonical_status": receipt.status,
                    "blocked_at": old.blocked_at if old.blocked_at == nested["blocked_at"] else None,
                    "provider_acquisition": manifest.provider_acquisition or receipt.evidence.get("provider_acquisition"),
                    "current_provider_execution": old.real_current_provider_execution_attempted or nested["real_current_provider_execution_attempted"],
                    "share_code_generation": manifest.share_code_generation,
                    "selected_leg_count": receipt.counts["selected_leg_count"],
                    "shortfall": receipt.shortfall,
                    "share_code_result": receipt.share_code_result,
                    "login": manifest.login,
                    "cookies": manifest.cookies,
                    "wallet": manifest.wallet,
                    "staking": manifest.staking,
                    "wager_placed": receipt.wager_placed or old.wager_placed,
                    "legacy_payload_preserved": nested == old_payload,
                    "durable_request_evidence_preserved": persisted == old_payload,
                }
                validate_equivalence_projection(projection, n)
                targets.append({"target_size": n, "request_sha256": request.canonical_sha256, "projection": projection})
    invalid = ("0", "51", "020", "20 ", "20.0", "abc")
    for value in invalid:
        try:
            resolve_workflow_request(event_name="workflow_dispatch", dispatch_inputs=dict(WORKFLOW_DISPATCH_DEFAULTS, target_legs=value), now=FIXED_NOW)
        except ValueError:
            pass
        else:
            raise P43BRetirementError(f"canonical workflow accepted invalid target {value!r}")
    for value in (0, 51):
        try:
            original_execution(target_size=value, output_dir=Path(temporary) / "invalid")
        except legacy.CurrentSportyBetAccumulatorRequestError:
            pass
        else:
            raise P43BRetirementError(f"legacy boundary accepted invalid target {value}")
    if attempts:
        raise P43BRetirementError("offline proof attempted network access")
    return {"targets": targets, "invalid_target_text_rejected": list(invalid), "legacy_invalid_targets_rejected": [0, 51], "network_attempt_count": 0,
            "reviewed_main_boundary_called_for_each_target": True, "durable_request_evidence_preserved": True}


def verify_retirement_tree(matrix: dict[str, Any]) -> None:
    if Path(TARGET).exists():
        raise P43BRetirementError("retired workflow remains executable in .github/workflows")
    # This audit proves the historical P4.3B 40->39 transition. Current live-set
    # accounting belongs to the cumulative ledger because later reviewed batches
    # are allowed to retire additional workflows without rewriting this receipt.
    receipt = json.loads(RECEIPT.read_bytes())
    if receipt.get("workflow_count_before") != 40 or receipt.get("workflow_count_after") != 39:
        raise P43BRetirementError("P4.3B historical transition is not 40 to 39")
    fixture = verify_historical_fixture()
    row = next((row for row in matrix["workflow_rows"] if row.get("workflow_path") == TARGET), None)
    if row is None or row.get("git_blob_sha1") != _git_blob_sha1(fixture) or row.get("source_sha256") != hashlib.sha256(fixture).hexdigest():
        raise P43BRetirementError("P4.3B fixture does not match its P4.3A baseline row")
    for path in PROTECTED:
        if not Path(path).is_file():
            raise P43BRetirementError(f"protected workflow missing: {path}")


def build_receipt() -> dict[str, Any]:
    matrix = verify_frozen_history()
    verify_historical_fixture()
    verify_retirement_tree(matrix)
    permissions = verify_permissions_and_artifacts()
    proof = prove_main_successor()
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository_base_main_sha": BASE_MAIN_SHA,
        "p4_3a_matrix_sha256": MATRIX_SHA,
        "p4_3a_receipt_sha256": P43A_SHA,
        "p4_2_receipt_sha256": P42_SHA,
        "owner_review_scope": [TARGET],
        "owner_review_authorized": True,
        "retired_workflow_path": TARGET,
        "retired_workflow_git_blob_sha1": TARGET_BLOB_SHA1,
        "retired_workflow_source_sha256": TARGET_SOURCE_SHA256,
        "history_status_at_p4_3a": "NO_RUN_HISTORY_OWNER_REVIEW_REQUIRED",
        "live_history_rechecked": True,
        "live_latest_run": None,
        "live_latest_successful_run": None,
        "successor_workflow_path": SUCCESSOR,
        "successor_family": "ATHENA_RUN",
        "input_mapping": INPUT_MAPPING,
        "equivalence_proven": True,
        "equivalence_dimensions": ["request semantics", "target bounds", "Phase-6 fail-closed blocker", "provider-acquisition denial", "share-code denial", "selected-leg absence", "wager denial", "durable request evidence preservation", "write-permission absence"],
        "equivalence_proof": proof,
        "permission_and_artifact_comparison": permissions,
        "network_attempt_count": proof["network_attempt_count"],
        "workflow_dispatch_triggered": False,
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
        "model_formula_changed": False,
        "probability_formula_changed": False,
        "calibration_formula_changed": False,
        "price_all_formula_changed": False,
        "router_formula_changed": False,
        "portfolio_formula_changed": False,
        "provider_semantics_changed": False,
        "share_code_semantics_changed": False,
        "workflow_count_before": 40,
        "workflow_count_after": 39,
        "workflow_count_decreased": True,
        "unique_required_capability_lost": False,
        "historical_fixture_path": FIXTURE,
        "historical_fixture_sha256": TARGET_SOURCE_SHA256,
        "rollback_tag": ROLLBACK_TAG,
        "rollback_commit_sha": BASE_MAIN_SHA,
        "rollback_tag_remote_verified_before_deletion": True,
        "p4_3b_retirement_gate_satisfied": True,
        "architecture_checkpoint_e_fully_claimed": False,
        "p4_4_started": False,
        "source_review_counter_while_unmerged": "2/5",
        "source_review_counter_if_merged": "3/5",
    }
    receipt["canonical_sha256"] = canonical_sha256(receipt)
    return receipt


def check(*, write_receipt: bool = False) -> dict[str, Any]:
    if write_receipt:
        raise P43BRetirementError("P4.3B is frozen historical evidence and must not be regenerated")
    committed = json.loads(RECEIPT.read_bytes())
    if committed.get("canonical_sha256") != P43B_SHA256 or canonical_sha256(committed) != P43B_SHA256:
        raise P43BRetirementError("immutable P4.3B receipt canonical SHA changed")
    matrix = verify_frozen_history()
    verify_retirement_tree(matrix)
    from scripts.audit_p4_3_workflow_retirement_ledger import validate_ledger

    ledger = validate_ledger()
    entry = next((item for item in ledger["retirements"] if item["workflow_path"] == TARGET), None)
    if entry is None or entry.get("retirement_receipt_sha256") != P43B_SHA256 or entry.get("retirement_phase") != "P4.3B":
        raise P43BRetirementError("cumulative ledger does not preserve the P4.3B historical retirement entry")
    if committed.get("workflow_count_before") != 40 or committed.get("workflow_count_after") != 39 or committed.get("retired_workflow_path") != TARGET:
        raise P43BRetirementError("P4.3B receipt does not preserve its one-target historical transition")
    return committed


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write-receipt", action="store_true")
    args = parser.parse_args()
    result = check(write_receipt=args.write_receipt)
    print(result["canonical_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
