"""Audit the CORE-01D Pass-2 PR145 completed-one-shot receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from scripts import audit_core_01d_retained_workflow_status_v3 as retained_v3
from services import athena_artifact_role_resolver as roles


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "ATHENA_CORE_01D_PR145_COMPLETED_ONE_SHOT_DISPOSITION_V1"
RECEIPT_PATH = "artifacts/architecture/core_01d_pr145_completed_one_shot_disposition_v1.json"
V3_RECEIPT_PATH = retained_v3.RECEIPT_PATH


class Pr145DispositionError(AssertionError):
    """Raised when the pass-2 receipt differs from authenticated V3 history."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Pr145DispositionError(message)


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


def build_receipt(status: dict | None = None) -> dict:
    status = retained_v3.build_receipt() if status is None else status
    disposition = status["pr145_disposition"]
    review = status["pr145_result_review"]
    followup = status["pr145_next_boundary_protocol"]
    relations = [
        row for row in status["current_artifact_trigger_relationships"]
        if row["artifact_id"] in (retained_v3.SOURCE_ARTIFACT_ID, retained_v3.FORENSIC_ARTIFACT_ID)
    ]
    require(len(relations) == 2, "Pass-2 PR145 relation inventory is incomplete")
    receipt = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository": "Thabearr/ATHENA",
        "master_issue": 337,
        "base_main_sha": retained_v3.BASE_MAIN_SHA,
        "base_tree_sha": retained_v3.BASE_TREE_SHA,
        "workflow_tree_sha1": retained_v3.WORKFLOW_TREE_SHA1,
        "workflow_evolution_ledger_sha256": retained_v3.EVOLUTION_LEDGER_SHA256,
        "workflow_evolution_transition_count": retained_v3.EVOLUTION_TRANSITION_COUNT,
        "retained_status_v2": {
            "path": retained_v3.V2_RECEIPT_PATH,
            "canonical_sha256": retained_v3.V2_RECEIPT_SHA256,
            "rewritten": False,
        },
        "retained_status_v3": {
            "path": V3_RECEIPT_PATH,
            "canonical_sha256": status["canonical_sha256"],
        },
        "workflow": {
            "path": retained_v3.PR145_WORKFLOW,
            "git_blob_sha1": status["pr145_source_identities"][retained_v3.PR145_WORKFLOW]["git_blob_sha1"],
            "source_sha256": status["pr145_source_identities"][retained_v3.PR145_WORKFLOW]["source_sha256"],
            "edited": False,
            "trigger_edited": False,
            "deleted": False,
        },
        "failed_pre_attempt_history": {
            "owner_command_comment_id": 5317747534,
            "run_id": 32046244761,
            "main_sha": "21bff3fe96e8c9b250c9776240ba7bede9f74c89",
            "reconciliation_comment_id": 5317758294,
            "attempt_marker_created": False,
            "checkout_executed": False,
            "source_artifact_download_executed": False,
            "validator_executed": False,
            "research_training_executed": False,
            "failure_artifact_id": 9292984849,
            "failure_artifact_sha256": "91965dee1fdb496e776a914de9a9e789a830141ea6b17276a7b1bade541835c1",
            "state": "FAILED_BEFORE_DURABLE_ATTEMPT_MARKER_NO_MODEL_VALIDATION_EXECUTED",
        },
        "successful_one_shot_history": {
            "owner_command_comment_id": 5318114406,
            "run_id": 32049714066,
            "main_sha": "b8ddc00f7529c5533c9da2daad613d997498cbf2",
            "durable_attempt_marker_comment_id": 5318115383,
            "result_comment_id": 5318117332,
            "runner_exit_code": 0,
            "artifact_download_outcome": "success",
            "package_outcome": "success",
            "artifact_upload_outcome": "success",
            "verification_outcome": "success",
            "state": "EXECUTION_COMPLETED_REVIEWED_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_EVIDENCE_PRESERVED",
            "artifact_name": "fotmob-utc-native-expected-goals-validation-32049714066",
        },
        "source_artifact": {
            "artifact_id": 9275052993,
            "run_id": 31990121181,
            "name": "fotmob-utc-native-feature-qualification-v2-31990121181",
            "size_bytes": 23349191,
            "sha256": "f69ffad8f47faadb3ec743c96efa35fb6f4b43776a7650cf0414fb40455d29eb",
            "source_head_sha": "cd67be14f6a4f09484d18a57de360b8a5d4c51d7",
            "recovery_state": "METADATA_ONLY_NO_BYTES",
            "dependency_type": "HARD_EXACT_HISTORICAL_REPLAY_SOURCE",
            "current_pr145_execution_dependency": False,
            "replay_authorized": False,
        },
        "failed_artifact": {
            "artifact_id": 9292984849,
            "sha256": "91965dee1fdb496e776a914de9a9e789a830141ea6b17276a7b1bade541835c1",
            "retained_status": "FORENSIC_PRE_ATTEMPT_HISTORY_RETAIN",
            "validator_input": False,
            "replay_authorized": False,
        },
        "successful_result_artifact": {
            "artifact_id": 9294215497,
            "name": "fotmob-utc-native-expected-goals-validation-32049714066",
            "size_bytes": 5441951,
            "sha256": "e9eac385a66df04bf28e7d69062e55db516829e94405e4a8def0e4d6a346d6c5",
            "result_receipt_sha256": "1fffee7474ab37ee613e6a7943b57fd9231f6d6bdf53ffa6b13ee2b62ceca06a",
            "predictions_sha256": "2f4939a8f2d41674660144f5315d2420ce2f006ce2b885e52c6655abd0e52420",
            "prediction_rows": 6948,
            "current_actions_listing_state": "CURRENT_ACTIONS_ARTIFACT_LISTING_EMPTY",
            "durable_byte_retention_reviewed": False,
            "disappearance_time_or_reason_inferred": False,
        },
        "reviewed_result": {
            "state": review["review_state"],
            "successor_approved": False,
            "evaluation_a_b_labels_consumed": True,
            "all_production_model_scorematrix_probability_pricing_selection_bet_authority_false": True,
        },
        "next_boundary": {
            "protocol_state": followup["protocol_state"],
            "identity": followup["next_boundary"],
            "executed_in_this_pr": False,
        },
        "attempt_authority_spent": disposition["state"] == "SPENT_HISTORICAL_ONE_SHOT_RETAIN",
        "replay_authorized": False,
        "blockers": {
            "A": "CLOSED",
            "B": "CLOSED",
            "C": "REMAINS_OPEN",
            "D": "REMAINS_OPEN",
            "checkpoint_e": "INCOMPLETE",
            "p4_4": "INCOMPLETE",
        },
        "actions": {
            "workflow_edit_count": 0,
            "trigger_edit_count": 0,
            "workflow_deletion_count": 0,
            "provider_acquisition_count": 0,
            "provider_action_count": 0,
            "pr145_execution_count": 0,
            "model_validation_count": 0,
            "model_training_count": 0,
            "model_fit_count": 0,
            "workflow_dispatch_count": 0,
            "workflow_rerun_or_cancel_count": 0,
            "issue_comment_write_count": 0,
            "release_mutation_count": 0,
            "evidence_regeneration_count": 0,
            "share_code_count": 0,
            "email_count": 0,
            "login_count": 0,
            "cookie_count": 0,
            "wallet_count": 0,
            "stake_count": 0,
            "wager_count": 0,
        },
        "protected_semantic_delta": dict.fromkeys(
            ("model", "probability", "calibration", "xg", "elo", "fatigue", "price_all",
             "router", "portfolio", "provider_market", "share_code", "delivery", "authority"),
            0,
        ),
        "authority": {
            "production": False,
            "model": False,
            "scorematrix": False,
            "probability": False,
            "pricing": False,
            "selection": False,
            "bet": False,
        },
        "authority_action_counts": dict.fromkeys(
            ("production", "model", "scorematrix", "probability", "pricing", "selection", "bet"), 0
        ),
        "checkpoint_e_status": "INCOMPLETE",
        "p4_4_status": "INCOMPLETE",
        "terminal": "CORE_01D_PR145_SPENT_ONE_SHOT_REVIEW_READY_BLOCKER_B_CLOSED_DO_NOT_MERGE",
    }
    return seal(receipt)


def validate_receipt(value: dict, expected: dict | None = None) -> None:
    require(value.get("canonical_sha256") == sha256(
        canonical_bytes({key: item for key, item in value.items() if key != "canonical_sha256"})
    ), "Pass-2 PR145 receipt self-hash mismatch")
    expected = build_receipt() if expected is None else expected
    require(value == expected, "Pass-2 PR145 receipt differs from authenticated V3 disposition")
    require(value["failed_pre_attempt_history"]["validator_executed"] is False
            and value["failed_pre_attempt_history"]["research_training_executed"] is False,
            "failed pre-attempt run was recast as validation")
    require(value["source_artifact"]["recovery_state"] == "METADATA_ONLY_NO_BYTES"
            and value["source_artifact"]["replay_authorized"] is False,
            "source bytes recovery or replay authority was overclaimed")
    require(value["successful_result_artifact"]["current_actions_listing_state"]
            == "CURRENT_ACTIONS_ARTIFACT_LISTING_EMPTY"
            and value["successful_result_artifact"]["durable_byte_retention_reviewed"] is False,
            "successful result archive availability was overclaimed")
    require(value["checkpoint_e_status"] == value["p4_4_status"] == "INCOMPLETE",
            "Pass-2 receipt cannot claim completion")


def audit() -> dict:
    status_raw = (ROOT / V3_RECEIPT_PATH).read_bytes()
    status = roles.strict_json(status_raw)
    require(status_raw.replace(b"\r\n", b"\n") == retained_v3.canonical_bytes(status),
            "retained-status V3 is not canonical JSON")
    retained_v3.validate_receipt(status)
    expected = build_receipt(status)
    raw = (ROOT / RECEIPT_PATH).read_bytes()
    value = roles.strict_json(raw)
    require(raw.replace(b"\r\n", b"\n") == canonical_bytes(value),
            "Pass-2 PR145 receipt is not canonical JSON")
    validate_receipt(value, expected)
    return {
        "result": "PASS",
        "receipt_sha256": value["canonical_sha256"],
        "retained_status_v3_sha256": status["canonical_sha256"],
        "terminal": value["terminal"],
        "blockers": value["blockers"],
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
    except (OSError, retained_v3.RetainedWorkflowStatusV3Error, Pr145DispositionError,
            TypeError, ValueError) as exc:
        print(json.dumps({"result": "BLOCKED", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
