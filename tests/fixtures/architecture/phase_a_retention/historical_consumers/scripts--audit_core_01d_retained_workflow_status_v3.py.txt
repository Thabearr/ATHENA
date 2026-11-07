"""Audit the additive CORE-01D PR145 spent-one-shot disposition (V3)."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from scripts.audit_data_01c_restore_portability import historical_workflow_tree

from scripts import audit_core_01d_retained_workflow_status_v2 as v2
from services import athena_artifact_role_resolver as roles


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "ATHENA_CORE_01D_RETAINED_WORKFLOW_STATUS_V3"
RECEIPT_PATH = "artifacts/architecture/core_01d_retained_workflow_status_v3.json"
V2_RECEIPT_PATH = "artifacts/architecture/core_01d_retained_workflow_status_v2.json"
V2_RECEIPT_SHA256 = "70e9215922883a1a4c083230b2c5ac54926b6c5cb2c8b45d299dbd65cd825934"
BASE_MAIN_SHA = "6366e3ac1f960def08e4971e1424fe3efbb1b4de"
BASE_TREE_SHA = "0d6df2679d5ac4ca39327c4d93d1c1229981f795"
WORKFLOW_TREE_SHA1 = "9b08653f1a12bb1b3d964fbd910396ff955740da"
EVOLUTION_LEDGER_SHA256 = "73e1eb3fe6593558c821600dd0f103353d45c15a139ab470a996c7cbb35da531"
EVOLUTION_TRANSITION_COUNT = 14
P43_LEDGER_SHA256 = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
PR145_WORKFLOW = (
    ".github/workflows/execute-fotmob-utc-native-expected-goals-model-validation.yml"
)
HISTORY_FIXTURE_PATH = "tests/fixtures/core_01d/pr145-model-validation-history-v1.json"
CORROBORATING_HISTORY_PATH = "tests/fixtures/core_01d/workflow-history-20261001.json"
PR145_BLOCKER = "OWNER_GATED_PR145_FEATURE_EVIDENCE_NOT_DURABLY_RECOVERED"
HISTORY_BLOCKER = "HISTORICAL_REPLAY_ARCHIVES_UNAVAILABLE"
SOURCE_ARTIFACT_ID = 9275052993
FORENSIC_ARTIFACT_ID = 9292984849
RESULT_ARTIFACT_ID = 9294215497
ATTEMPT_MARKER = (
    "<!-- ATHENA_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_ATTEMPT -->"
)
REVIEW_STATE = "REVIEWED_MIXED_OR_WEAK_FOTMOB_UTC_NATIVE_SUCCESSOR_NOT_APPROVED"
NEXT_BOUNDARY = (
    "IMPLEMENT_REVIEWED_FRESH_HOLDOUT_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_"
    "CALIBRATION_AND_COMPETITION_IDENTITY_FOLLOWUP"
)


class RetainedWorkflowStatusV3Error(AssertionError):
    """Raised when immutable history or current source-derived state drifts."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RetainedWorkflowStatusV3Error(message)


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
        raise RetainedWorkflowStatusV3Error(
            f"git {' '.join(args)} failed: {result.stderr.decode('utf-8', 'replace')}"
        )
    return result.stdout


def _blob(path: str, revision: str = "HEAD") -> bytes:
    return _git("show", f"{revision}:{path}")


def _source_identity(path: str, *, must_match_head: bool = True) -> dict[str, str]:
    working = (ROOT / path).read_bytes()
    normalized = working.replace(b"\r\n", b"\n")
    blob = subprocess.run(
        ["git", "hash-object", f"--path={path}", "--stdin"],
        cwd=ROOT,
        input=working,
        capture_output=True,
        check=True,
    ).stdout.decode("ascii").strip()
    head = _git("rev-parse", f"HEAD:{path}").decode("ascii").strip()
    if must_match_head:
        require(blob == head, f"authenticated source differs from HEAD: {path}")
    return {
        "path": path,
        "git_blob_sha1": blob,
        "source_sha256": sha256(normalized),
    }


def _expected_comment_bodies() -> dict[int, str]:
    command_prefix = "/athena-run-fotmob-utc-native-expected-goals-validation"
    confirmation = "confirm: EXECUTE_REVIEWED_21129_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION"
    failed_sha = "21bff3fe96e8c9b250c9776240ba7bede9f74c89"
    successful_sha = "b8ddc00f7529c5533c9da2daad613d997498cbf2"
    failure_reconciliation = [
        "<!-- ATHENA_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_FAILED_PRE_ATTEMPT_RECONCILIATION -->",
        "ATHENA UTC-native expected-goals validation execution command reached the control workflow but failed before the durable attempt marker could be created.",
        "run-id: 32046244761",
        f"main-sha: {failed_sha}",
        "command-comment-id: 5317747534",
        "attempt-marker-created: false",
        "checkout-executed: false",
        "source-artifact-download-executed: false",
        "validator-executed: false",
        "research-training-executed: false",
        "failure-step: Validate one-shot owner command and current main",
        "failure: GitHub API POST /issues/145/comments returned 403 Resource not accessible by integration because the closed-PR receipt path requires pull_requests=write.",
        "failure-artifact-id: 9292984849",
        "failure-artifact-name: fotmob-utc-native-expected-goals-validation-32046244761",
        "failure-artifact-size-bytes: 2448",
        "failure-artifact-sha256: 91965dee1fdb496e776a914de9a9e789a830141ea6b17276a7b1bade541835c1",
        "state: FAILED_BEFORE_DURABLE_ATTEMPT_MARKER_NO_MODEL_VALIDATION_EXECUTED",
        "Automatic replay of run 32046244761 is forbidden. A reviewed control-plane correction and a new explicit execution command are required before another attempt.",
    ]
    successful_marker = [
        ATTEMPT_MARKER,
        "ATHENA reviewed FotMob UTC-native expected-goals model-validation attempt started.",
        "run-id: 32049714066",
        f"main-sha: {successful_sha}",
        "command-comment-id: 5318114406",
        "upstream-v2-result-comment-id: 5311318782",
        "state: ATTEMPT_STARTED_NO_RESULT_YET",
        "Automatic replay is forbidden if this run does not complete cleanly.",
    ]
    successful_result = [
        "<!-- ATHENA_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_RESULT -->",
        "ATHENA reviewed FotMob UTC-native expected-goals model-validation execution result.",
        "run-id: 32049714066",
        f"main-sha: {successful_sha}",
        "runner-exit-code: 0",
        "artifact-download-outcome: success",
        "package-outcome: success",
        "artifact-upload-outcome: success",
        "verification-outcome: success",
        "state: EXECUTION_COMPLETED_REVIEWED_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_EVIDENCE_PRESERVED",
        "artifact-name: fotmob-utc-native-expected-goals-validation-32049714066",
        "Research model-validation evidence only. Result review is required.",
        "No ScoreMatrix, probability, pricing, selection, production, or BET authority is granted.",
    ]
    return {
        5317747534: "\n".join(
            (command_prefix, f"main-sha: {failed_sha}", confirmation)
        ),
        5317758294: "\n".join(failure_reconciliation),
        5318114406: "\n".join(
            (command_prefix, f"main-sha: {successful_sha}", confirmation)
        ),
        5318115383: "\n".join(successful_marker),
        5318117332: "\n".join(successful_result),
    }


def validate_history(value: dict) -> None:
    """Authenticate the deterministic, read-only capture of PR145 history."""
    require(value.get("schema_version") == 1, "PR145 history fixture schema drift")
    require(value.get("repository") == "Thabearr/ATHENA", "PR145 history repository drift")
    require(value.get("issue_number") == 145, "PR145 history issue identity drift")
    require(value.get("read_only_capture") is True, "history was not marked read-only")
    require(value.get("capture_method") == "GitHub REST API GET", "history capture method drift")
    require(value.get("no_action_performed") is True, "history capture claims an action")
    require(value.get("workflow_dispatch_performed") is False,
            "history capture claims workflow dispatch")
    require(value.get("provider_operation_performed") is False,
            "history capture claims provider operation")

    comment_meta = {
        5317747534: ("Thabearr", "2026-08-17T16:34:38Z"),
        5317758294: ("Thabearr", "2026-08-17T16:35:48Z"),
        5318114406: ("Thabearr", "2026-08-17T17:18:05Z"),
        5318115383: ("github-actions[bot]", "2026-08-17T17:18:14Z"),
        5318117332: ("github-actions[bot]", "2026-08-17T17:18:31Z"),
    }
    comments = value.get("comments")
    require(type(comments) is list and len(comments) == 5,
            "PR145 comment capture inventory drift")
    expected_bodies = _expected_comment_bodies()
    for row in comments:
        comment_id = row.get("id")
        require(comment_id in expected_bodies, "unexpected PR145 history comment")
        author, created_at = comment_meta[comment_id]
        require(row == {
            "id": comment_id,
            "author_login": author,
            "created_at": created_at,
            "html_url": (
                f"https://github.com/Thabearr/ATHENA/pull/145#issuecomment-{comment_id}"
            ),
            "body": expected_bodies[comment_id],
        }, f"PR145 comment {comment_id} identity/body changed")
    require({row["id"] for row in comments} == set(expected_bodies),
            "required PR145 comment is missing")

    expected_runs = [
        {
            "id": 32046244761,
            "name": "Execute Reviewed FotMob UTC-Native Expected-Goals Model Validation",
            "path": PR145_WORKFLOW,
            "head_sha": "21bff3fe96e8c9b250c9776240ba7bede9f74c89",
            "head_branch": "main",
            "event": "issue_comment",
            "status": "completed",
            "conclusion": "failure",
            "run_attempt": 1,
            "created_at": "2026-08-17T16:34:45Z",
            "updated_at": "2026-08-17T16:34:54Z",
            "html_url": "https://github.com/Thabearr/ATHENA/actions/runs/32046244761",
        },
        {
            "id": 32049714066,
            "name": "Execute Reviewed FotMob UTC-Native Expected-Goals Model Validation",
            "path": PR145_WORKFLOW,
            "head_sha": "b8ddc00f7529c5533c9da2daad613d997498cbf2",
            "head_branch": "main",
            "event": "issue_comment",
            "status": "completed",
            "conclusion": "success",
            "run_attempt": 1,
            "created_at": "2026-08-17T17:18:08Z",
            "updated_at": "2026-08-17T17:18:33Z",
            "html_url": "https://github.com/Thabearr/ATHENA/actions/runs/32049714066",
        },
    ]
    require(value.get("runs") == expected_runs, "PR145 run capture identity drift")

    require(value.get("successful_result_artifact_current_listing") == {
        "run_id": 32049714066,
        "artifact_id": RESULT_ARTIFACT_ID,
        "read_only_capture": True,
        "state": "CURRENT_ACTIONS_ARTIFACT_LISTING_EMPTY",
        "total_count": 0,
        "artifacts": [],
        "captured_on_utc_date": "2026-10-02",
        "artifact_disappearance_time_known": False,
        "artifact_disappearance_reason_known": False,
        "external_durable_archive_checked": False,
        "durable_byte_retention_reviewed": False,
        "source_controlled_summary_claims_equal_original_zip_bytes": False,
    }, "current result-artifact availability observation overclaims or changed")
    require(value.get("capture_safety") == {
        "issue_comment_writes": 0,
        "workflow_dispatches": 0,
        "workflow_reruns": 0,
        "provider_operations": 0,
        "evidence_regeneration": 0,
        "secrets_tokens_or_headers_included": False,
    }, "PR145 history capture safety declaration changed")


def load_history() -> tuple[dict, bytes]:
    raw = (ROOT / HISTORY_FIXTURE_PATH).read_bytes()
    value = roles.strict_json(raw)
    validate_history(value)
    return value, raw


def _validate_successor_sources() -> tuple[dict, dict, dict[str, dict[str, str]]]:
    from domain import (
        fotmob_utc_native_expected_goals_fresh_holdout_calibration_competition_protocol as protocol_source,
    )
    from domain import fotmob_utc_native_expected_goals_model_validation_result_review as review_source

    review = review_source.build_fotmob_utc_native_expected_goals_model_validation_result_review()
    evidence = review["execution_evidence"]
    source = review["source_evidence"]
    decision = review["reviewed_decision"]
    require(review["review_id"] == "FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_RESULT_REVIEW_V1",
            "result-review identity drift")
    require(review["review_state"] == REVIEW_STATE, "result-review state drift")
    require(evidence["main_sha"] == "b8ddc00f7529c5533c9da2daad613d997498cbf2",
            "reviewed execution main identity drift")
    require(evidence["run_id"] == 32049714066, "reviewed execution run drift")
    require(evidence["command_comment_id"] == 5318114406,
            "reviewed command-comment identity drift")
    require(evidence["attempt_comment_id"] == 5318115383,
            "reviewed attempt-marker identity drift")
    require(evidence["result_comment_id"] == 5318117332,
            "reviewed result-comment identity drift")
    require(evidence["artifact"] == {
        "id": RESULT_ARTIFACT_ID,
        "name": "fotmob-utc-native-expected-goals-validation-32049714066",
        "size_bytes": 5441951,
        "sha256": "e9eac385a66df04bf28e7d69062e55db516829e94405e4a8def0e4d6a346d6c5",
    }, "successful result artifact identity drift")
    require(evidence["receipt"]["size_bytes"] == 55507
            and evidence["receipt"]["sha256"]
            == "1fffee7474ab37ee613e6a7943b57fd9231f6d6bdf53ffa6b13ee2b62ceca06a",
            "canonical result receipt identity drift")
    require(evidence["predictions"]["record_count"] == 6948
            and evidence["predictions"]["sha256"]
            == "2f4939a8f2d41674660144f5315d2420ce2f006ce2b885e52c6655abd0e52420",
            "reviewed predictions identity drift")
    require(source["artifact_id"] == SOURCE_ARTIFACT_ID
            and source["artifact_sha256"]
            == "f69ffad8f47faadb3ec743c96efa35fb6f4b43776a7650cf0414fb40455d29eb"
            and source["projection_sha256"]
            == "5519ef40db3efc678c9eef73046c0e577e5f33a85f11b3fe043fc22bca2fcfed"
            and source["projection_rows"] == 21326,
            "source feature artifact identity drift")
    require(source["pooled_evaluation_rows"] == 6948,
            "reviewed development row count drift")
    require(decision["native_refit_successor_candidate_approved"] is False
            and decision["historical_fixed_transfer_promoted_instead"] is False
            and decision["evaluation_a_and_b_labels_now_consumed_by_review"] is True
            and decision["home_calibration_followup_required"] is True
            and decision["competition_identity_followup_required"] is True,
            "result-review decision or consumed-label status drift")
    require(all(flag is False for flag in review["safety"].values()),
            "result-review grants a prohibited authority")

    protocol = protocol_source.build_fresh_holdout_home_calibration_competition_identity_protocol()
    parent = protocol["reviewed_parent"]
    require(protocol["protocol_state"] == (
        "PRE_REGISTERED_FRESH_HOLDOUT_CALIBRATION_AND_COMPETITION_IDENTITY_"
        "NOT_IMPLEMENTED_NOT_EXECUTED"
    ), "follow-up protocol state drift")
    require(protocol["next_required_boundary"] == NEXT_BOUNDARY,
            "follow-up next boundary drift")
    require(parent["execution_run_id"] == 32049714066
            and parent["result_artifact_id"] == RESULT_ARTIFACT_ID
            and parent["result_artifact_sha256"] == evidence["artifact"]["sha256"]
            and parent["result_receipt_sha256"] == evidence["receipt"]["sha256"]
            and parent["predictions_sha256"] == evidence["predictions"]["sha256"]
            and parent["development_rows"] == 6948
            and parent["reviewed_state_required"] == REVIEW_STATE,
            "follow-up protocol does not bind the consumed reviewed result")
    require(all(flag is False for flag in protocol["safety"].values()),
            "follow-up protocol grants a prohibited authority")

    source_paths = (
        "domain/fotmob_utc_native_expected_goals_model_validation_result_review.py",
        "docs/fotmob_utc_native_expected_goals_model_validation_result_review.md",
        "domain/fotmob_utc_native_expected_goals_fresh_holdout_calibration_competition_protocol.py",
        "docs/fotmob_utc_native_expected_goals_fresh_holdout_calibration_competition_protocol.md",
    )
    identities = {path: _source_identity(path) for path in source_paths}
    return review, protocol, identities


def _validate_workflow_and_prior_fixture() -> dict[str, dict[str, str]]:
    workflow = _blob(PR145_WORKFLOW)
    workflow_tree = historical_workflow_tree(_git("rev-parse", "HEAD:.github/workflows").decode("ascii").strip())
    require(workflow_tree == WORKFLOW_TREE_SHA1,
            "PR145 workflow directory differs from the exact pass-2 base tree")
    from scripts import audit_p4_3_workflow_retirement_ledger as p43

    p43_ledger = p43.validate_retirement_history()
    require(p43_ledger.get("canonical_sha256") == P43_LEDGER_SHA256,
            "P4.3 retirement ledger differs from the exact pass-2 base identity")
    for needle in (
        "issue_comment:",
        ATTEMPT_MARKER,
        "const priorMarker = comments.find(",
        "automatic replay is forbidden and requires reviewed reconciliation.",
    ):
        require(needle.encode("utf-8") in workflow,
                f"PR145 one-shot source guard missing: {needle}")
    workflow_identity = _source_identity(PR145_WORKFLOW)
    require(workflow_identity["git_blob_sha1"] == "52958ce34e07179226c6d14c86daf7b2d229459b"
            and workflow_identity["source_sha256"]
            == "d1fcc4453d84875bbbe73e95bb1a769d3e27bdc3fec0cb93662ca114c25d9bf6",
            "PR145 workflow base blob/source identity drift")

    old_fixture_raw = (ROOT / CORROBORATING_HISTORY_PATH).read_bytes()
    v2._require_head_file_identity(CORROBORATING_HISTORY_PATH, old_fixture_raw)
    old_fixture = roles.strict_json(old_fixture_raw)
    old_run = old_fixture["workflow_history"][PR145_WORKFLOW]["last_successful"]
    require(old_run["id"] == 32049714066
            and old_run["head_sha"] == "b8ddc00f7529c5533c9da2daad613d997498cbf2"
            and old_run["conclusion"] == "success",
            "preserved 2026-10-01 history fixture does not corroborate successful run")

    identities = {
        PR145_WORKFLOW: workflow_identity,
        CORROBORATING_HISTORY_PATH: _source_identity(CORROBORATING_HISTORY_PATH),
    }
    return identities


def _load_and_authenticate_v2() -> dict:
    raw = (ROOT / V2_RECEIPT_PATH).read_bytes()
    value = roles.strict_json(raw)
    require(raw.replace(b"\r\n", b"\n") == canonical_bytes(value),
            "immutable retained-status V2 is not canonical")
    require(value.get("canonical_sha256") == V2_RECEIPT_SHA256,
            "immutable retained-status V2 SHA-256 changed")
    v2._require_head_file_identity(V2_RECEIPT_PATH, raw)
    expected = v2.build_receipt()
    v2.validate_receipt(value, expected)
    require(expected["canonical_sha256"] == V2_RECEIPT_SHA256,
            "source-derived V2 differs from its fixed SHA")
    return value


def build_receipt() -> dict:
    """Derive V3 from immutable V2 plus authenticated one-shot history."""
    predecessor = _load_and_authenticate_v2()
    history, history_raw = load_history()
    review, protocol, result_source_identities = _validate_successor_sources()
    other_source_identities = _validate_workflow_and_prior_fixture()

    failed_command, reconciliation, successful_command, marker, result_comment = history["comments"]
    failed_run, successful_run = history["runs"]
    require(failed_command["id"] == 5317747534
            and reconciliation["id"] == 5317758294
            and failed_run["id"] == 32046244761,
            "failed pre-attempt history identity drift")
    require(reconciliation["body"].count("attempt-marker-created: false") == 1
            and reconciliation["body"].count("validator-executed: false") == 1
            and reconciliation["body"].count("research-training-executed: false") == 1,
            "failed run is not proven pre-marker/pre-validator/pre-training")
    require("failure-artifact-id: 9292984849" in reconciliation["body"]
            and "failure-artifact-sha256: 91965dee1fdb496e776a914de9a9e789a830141ea6b17276a7b1bade541835c1" in reconciliation["body"],
            "failed forensic artifact identity drift")
    require(successful_command["id"] == 5318114406
            and marker["id"] == 5318115383
            and successful_run["id"] == 32049714066
            and result_comment["id"] == 5318117332,
            "successful one-shot execution identity drift")
    for outcome in (
        "runner-exit-code: 0",
        "artifact-download-outcome: success",
        "package-outcome: success",
        "artifact-upload-outcome: success",
        "verification-outcome: success",
        "state: EXECUTION_COMPLETED_REVIEWED_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_EVIDENCE_PRESERVED",
    ):
        require(outcome in result_comment["body"],
                f"successful execution result field missing: {outcome}")
    require(marker["id"] == review["execution_evidence"]["attempt_comment_id"]
            and result_comment["id"] == review["execution_evidence"]["result_comment_id"],
            "result review is not bound to the durable attempt and result comments")

    workflow_identity = other_source_identities[PR145_WORKFLOW]
    require(marker["body"].startswith(ATTEMPT_MARKER)
            and b"automatic replay is forbidden and requires reviewed reconciliation." in _blob(PR145_WORKFLOW),
            "successful marker is not guarded against automatic replay")
    require(successful_run["conclusion"] == "success"
            and review["review_state"] == REVIEW_STATE
            and protocol["protocol_state"].endswith("NOT_IMPLEMENTED_NOT_EXECUTED"),
            "PR145 spent-state prerequisites are not all satisfied")

    source_rows = copy.deepcopy(predecessor["current_artifact_trigger_relationships"])
    artifact_rows = copy.deepcopy(predecessor["artifact_dispositions"])
    source_row, = [row for row in source_rows if row["artifact_id"] == SOURCE_ARTIFACT_ID]
    forensic_row, = [row for row in source_rows if row["artifact_id"] == FORENSIC_ARTIFACT_ID]
    source_artifact, = [row for row in artifact_rows if row["artifact_id"] == SOURCE_ARTIFACT_ID]
    forensic_artifact, = [row for row in artifact_rows if row["artifact_id"] == FORENSIC_ARTIFACT_ID]

    require(source_artifact["recovery_state"] == "METADATA_ONLY_NO_BYTES"
            and source_artifact["run_id"] == 31990121181
            and source_artifact["expected_size_bytes"] == 23349191
            and source_artifact["expected_sha256"]
            == "f69ffad8f47faadb3ec743c96efa35fb6f4b43776a7650cf0414fb40455d29eb",
            "PR145 source artifact was overclaimed or its exact identity changed")
    require(source_artifact["source_head_sha"] == "cd67be14f6a4f09484d18a57de360b8a5d4c51d7",
            "PR145 source artifact main identity drift")
    require(forensic_artifact["recovery_state"] == "METADATA_ONLY_NO_BYTES"
            and forensic_artifact["retained_status"] == "FORENSIC_PRE_ATTEMPT_HISTORY_RETAIN"
            and forensic_artifact["dependency_types"] == [
                "FORENSIC_RECONCILIATION_METADATA_ONLY", "HISTORICAL_LINEAGE_ONLY"
            ], "failed artifact forensic-only disposition drift")
    require(source_row["workflow_path"] == PR145_WORKFLOW
            and forensic_row["workflow_path"] == PR145_WORKFLOW,
            "PR145 artifact relation is not attached to the retained workflow")

    source_row.update({
        "trigger_lifecycle": "CLOSED_OR_SPENT",
        "retained_status": "SPENT_HISTORICAL_ONE_SHOT_RETAIN",
        "dependency_type": "HARD_EXACT_HISTORICAL_REPLAY_SOURCE",
        "retained_reason": (
            "PR145 completed and reviewed its single successful execution in run 32049714066. "
            "The durable attempt marker makes this issue-comment lane spent; artifact 9275052993 "
            "remains exact historical raw-source replay evidence only and is still "
            "METADATA_ONLY_NO_BYTES."
        ),
        "owner_decision": (
            "Retain the exact unrecovered archive for historical replay/audit. The spent PR145 "
            "one-shot cannot be replayed; no current execution, reacquisition, or substitution is authorized."
        ),
    })
    forensic_row.update({
        "trigger_lifecycle": "CLOSED_OR_SPENT_FORENSIC_HISTORY",
        "retained_status": "FORENSIC_PRE_ATTEMPT_HISTORY_RETAIN",
        "dependency_type": "FORENSIC_RECONCILIATION_METADATA_ONLY",
        "retained_reason": (
            "The failed run 32046244761 is preserved as pre-attempt forensic history only; "
            "it did not execute the validator or training and is not a payload input."
        ),
        "owner_decision": (
            "Preserve the exact failure identity as forensic history; no validator input, "
            "replay, or recovery authority is granted."
        ),
    })
    require(source_row["authorizations"]["replay_authorized"] is False
            and forensic_row["authorizations"]["replay_authorized"] is False,
            "PR145 replay authority must remain false")

    source_artifact.update({
        "dependency_types": ["HARD_EXACT_HISTORICAL_REPLAY_SOURCE"],
        "retained_status": "SPENT_HISTORICAL_ONE_SHOT_RETAIN",
        "retained_reason": (
            "The successful PR145 one-shot completed and its result was reviewed. Exact bytes "
            "remain required for historical raw-source replay/audit; the archive is not recovered."
        ),
        "missing_evidence_effect": (
            "No current PR145 execution depends on this archive. Exact bytes remain necessary "
            "for historical raw-source replay/audit. Recovery state remains METADATA_ONLY_NO_BYTES."
        ),
        "owner_decision": (
            "Preserve the exact unrecovered archive for historical replay/audit. No PR145 workflow "
            "replay or current execution is authorized; do not reacquire or substitute the source."
        ),
    })
    require(source_artifact["authorizations"]["replay_authorized"] is False,
            "historical replay must remain unauthorized")

    live_rows = [row for row in source_rows if row["trigger_lifecycle"].startswith("LIVE_")]
    historical_rows = [row for row in source_rows if not row["trigger_lifecycle"].startswith("LIVE_")]
    workflow_edges = {
        (row["artifact_id"], row["workflow_path"]) for row in source_rows
    }
    require(len(source_rows) == 14 and len(live_rows) == 2 and len(historical_rows) == 12,
            "V3 source-derived artifact-trigger relationship counts drift")
    require(len(workflow_edges) == predecessor["artifact_workflow_edge_count"] == 12,
            "V3 source-derived artifact/workflow edge count drift")

    closed_blockers = copy.deepcopy(predecessor["closed_blockers"])
    require([row["id"] for row in closed_blockers] == [
        "PROTECTED_FRESH_HOLDOUT_PR119_EXACT_FALLBACK_NOT_DURABLY_RECOVERED"
    ], "V2 blocker A was not the only prior closure")
    closed_blockers.append({
        "id": PR145_BLOCKER,
        "resolved_fact": (
            "PR145 successfully completed its single reviewed execution in run 32049714066; "
            "the result was source-controlled and reviewed; durable attempt marker 5318115383 "
            "makes the original workflow one-shot spent; exact artifact 9275052993 remains "
            "unrecovered and is a HISTORICAL replay-retention defect rather than a live "
            "owner-gated execution prerequisite."
        ),
    })
    remaining_blockers = copy.deepcopy(predecessor["remaining_blockers"])
    require([row["id"] for row in remaining_blockers] == [
        PR145_BLOCKER,
        "CANONICAL_HISTORY_TRANSFER_SOURCE_NOT_FULLY_DURABLE",
        HISTORY_BLOCKER,
    ], "V2 unresolved blocker identities drift")
    remaining_blockers = [row for row in remaining_blockers if row["id"] != PR145_BLOCKER]
    history_blocker, = [row for row in remaining_blockers if row["id"] == HISTORY_BLOCKER]
    history_blocker["artifact_ids"] = sorted(set(
        history_blocker["artifact_ids"] + [SOURCE_ARTIFACT_ID, FORENSIC_ARTIFACT_ID]
    ))
    history_blocker["reason"] = (
        "Exact historical replay archives remain unavailable, including 9422055017, "
        "9437181220, 9266604353, 9274313978, 9275052993, and 9292984849. "
        "These are historical retention defects, not proof of current product-runtime blockage "
        "or retirement authority."
    )

    fixture_identity = {
        "path": HISTORY_FIXTURE_PATH,
        "source_sha256": sha256(history_raw.replace(b"\r\n", b"\n")),
    }
    source_identities = {
        **result_source_identities,
        **other_source_identities,
        HISTORY_FIXTURE_PATH: {
            "path": HISTORY_FIXTURE_PATH,
            "git_blob_sha1": subprocess.run(
                ["git", "hash-object", f"--path={HISTORY_FIXTURE_PATH}", "--stdin"],
                cwd=ROOT,
                input=history_raw,
                capture_output=True,
                check=True,
            ).stdout.decode("ascii").strip(),
            "source_sha256": fixture_identity["source_sha256"],
        },
    }
    history_listing = history["successful_result_artifact_current_listing"]
    result_review = {
        "review_id": review["review_id"],
        "review_state": review["review_state"],
        "execution_main_sha": review["execution_evidence"]["main_sha"],
        "run_id": review["execution_evidence"]["run_id"],
        "command_comment_id": review["execution_evidence"]["command_comment_id"],
        "attempt_comment_id": review["execution_evidence"]["attempt_comment_id"],
        "result_comment_id": review["execution_evidence"]["result_comment_id"],
        "source_artifact_id": review["source_evidence"]["artifact_id"],
        "source_artifact_sha256": review["source_evidence"]["artifact_sha256"],
        "source_projection_sha256": review["source_evidence"]["projection_sha256"],
        "source_projection_rows": review["source_evidence"]["projection_rows"],
        "result_artifact": review["execution_evidence"]["artifact"],
        "result_receipt": review["execution_evidence"]["receipt"],
        "predictions": review["execution_evidence"]["predictions"],
        "successor_candidate_approved": False,
        "evaluation_labels_consumed": True,
        "all_authority_false": all(flag is False for flag in review["safety"].values()),
    }
    followup = {
        "protocol_state": protocol["protocol_state"],
        "next_boundary": protocol["next_required_boundary"],
        "execution_run_id": protocol["reviewed_parent"]["execution_run_id"],
        "result_artifact_id": protocol["reviewed_parent"]["result_artifact_id"],
        "result_artifact_sha256": protocol["reviewed_parent"]["result_artifact_sha256"],
        "result_receipt_sha256": protocol["reviewed_parent"]["result_receipt_sha256"],
        "predictions_sha256": protocol["reviewed_parent"]["predictions_sha256"],
        "development_rows": protocol["reviewed_parent"]["development_rows"],
        "reviewed_state_required": protocol["reviewed_parent"]["reviewed_state_required"],
        "executed_in_this_pass": False,
    }

    receipt = copy.deepcopy(predecessor)
    receipt.update({
        "schema_version": 3,
        "policy_id": POLICY_ID,
        "predecessor_v2": {
            "path": V2_RECEIPT_PATH,
            "canonical_sha256": V2_RECEIPT_SHA256,
            "state": "IMMUTABLE_PRE_PASS_2_BEFORE_STATE",
        },
        "pass2_base_main_sha": BASE_MAIN_SHA,
        "pass2_base_tree_sha": BASE_TREE_SHA,
        "source_review_counter_while_open": "4/5",
        "source_review_counter_if_owner_merges": "5/5",
        "mandatory_source_reread_due": False,
        "mandatory_source_reread_due_immediately_after_owner_merge": True,
        "current_workflow_tree_sha1": WORKFLOW_TREE_SHA1,
        "current_evolution_ledger_sha256": EVOLUTION_LEDGER_SHA256,
        "evolution_transition_count": EVOLUTION_TRANSITION_COUNT,
        "current_artifact_trigger_relationships": source_rows,
        "artifact_dispositions": artifact_rows,
        "closed_blockers": closed_blockers,
        "remaining_blockers": remaining_blockers,
        "workflow_deletion_count": 0,
        "trigger_surface_change_count": 0,
        "workflow_count_delta": 0,
        "provider_action_count": 0,
        "workflow_dispatch_action_count": 0,
        "workflow_rerun_or_cancel_action_count": 0,
        "evidence_regeneration_count": 0,
        "model_training_action_count": 0,
        "validator_execution_count": 0,
        "issue_comment_write_count": 0,
        "release_mutation_count": 0,
        "email_action_count": 0,
        "share_code_action_count": 0,
        "login_cookie_wallet_stake_wager_action_count": 0,
        "volatile_runtime_observations_included": True,
        "volatile_run_state_used_for_static_classification": False,
        "pr145_history_fixture": fixture_identity,
        "pr145_source_identities": source_identities,
        "pr145_workflow_unchanged": True,
        "pr145_attempt_authority_spent": True,
        "pr145_replay_authorized": False,
        "pr145_disposition": {
            "state": "SPENT_HISTORICAL_ONE_SHOT_RETAIN",
            "workflow_path": PR145_WORKFLOW,
            "failed_pre_attempt_run_id": 32046244761,
            "failed_pre_attempt_command_comment_id": 5317747534,
            "failed_pre_attempt_reconciliation_comment_id": 5317758294,
            "failed_artifact_id": FORENSIC_ARTIFACT_ID,
            "failed_artifact_sha256": "91965dee1fdb496e776a914de9a9e789a830141ea6b17276a7b1bade541835c1",
            "failed_validator_executed": False,
            "failed_training_executed": False,
            "successful_command_comment_id": 5318114406,
            "successful_run_id": 32049714066,
            "successful_main_sha": "b8ddc00f7529c5533c9da2daad613d997498cbf2",
            "durable_attempt_marker_comment_id": 5318115383,
            "successful_result_comment_id": 5318117332,
            "successful_result_state": "EXECUTION_COMPLETED_REVIEWED_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_EVIDENCE_PRESERVED",
            "source_artifact_id": SOURCE_ARTIFACT_ID,
            "source_artifact_sha256": source_artifact["expected_sha256"],
            "source_artifact_recovery_state": "METADATA_ONLY_NO_BYTES",
            "source_artifact_dependency": "HARD_EXACT_HISTORICAL_REPLAY_SOURCE",
            "current_pr145_execution_dependency": False,
            "missing_source_bytes_reopen_authority": False,
            "result_artifact_id": RESULT_ARTIFACT_ID,
            "result_artifact_sha256": review["execution_evidence"]["artifact"]["sha256"],
            "result_artifact_current_listing_state": history_listing["state"],
            "result_artifact_durable_retention_reviewed": False,
            "result_review_state": review["review_state"],
            "successor_approved": False,
            "next_boundary": protocol["next_required_boundary"],
            "workflow_edited": False,
            "trigger_edited": False,
            "replay_authorized": False,
        },
        "pr145_result_review": result_review,
        "pr145_next_boundary_protocol": followup,
        "separate_retention_observations": [
            {
                "id": "PR145_SUCCESSFUL_RESULT_ARTIFACT_CURRENTLY_UNAVAILABLE_RETENTION_NOT_REVIEWED",
                "run_id": 32049714066,
                "artifact_id": RESULT_ARTIFACT_ID,
                "state": history_listing["state"],
                "total_count": history_listing["total_count"],
                "captured_on_utc_date": history_listing["captured_on_utc_date"],
                "artifact_disappearance_time_known": False,
                "artifact_disappearance_reason_known": False,
                "external_durable_archive_checked": False,
                "durable_byte_retention_reviewed": False,
                "source_controlled_summary_claims_equal_original_zip_bytes": False,
                "reopens_pr145_execution_lane": False,
            }
        ],
        "protected_semantic_delta": dict.fromkeys(
            ("model", "probability", "calibration", "xg", "elo", "fatigue", "price_all",
             "router", "portfolio", "provider_market", "share_code", "delivery", "authority"),
            0,
        ),
        "checkpoint_e_status": "INCOMPLETE",
        "p4_4_status": "INCOMPLETE",
        "terminal": "CORE_01D_PR145_SPENT_ONE_SHOT_REVIEW_READY_BLOCKER_B_CLOSED_DO_NOT_MERGE",
    })
    receipt["artifact_trigger_relationship_count"] = len(source_rows)
    receipt["live_artifact_trigger_relationship_count"] = len(live_rows)
    receipt["historical_or_spent_artifact_trigger_relationship_count"] = len(historical_rows)
    receipt["closed_blocker_ids"] = [row["id"] for row in closed_blockers]
    receipt["remaining_blocker_ids"] = [row["id"] for row in remaining_blockers]
    return seal(receipt)


def validate_receipt(value: dict, expected: dict | None = None) -> None:
    require(value.get("canonical_sha256") == sha256(
        canonical_bytes({key: item for key, item in value.items() if key != "canonical_sha256"})
    ), "retained-status V3 self-hash mismatch")
    expected = build_receipt() if expected is None else expected
    require(value == expected, "retained-status V3 differs from authenticated source/history")
    require(value["predecessor_v2"]["canonical_sha256"] == V2_RECEIPT_SHA256,
            "V3 did not preserve exact V2 identity")
    require(value["workflow_count"] == 39 and value["trigger_surface_count"] == 57,
            "V3 workflow/trigger counts changed")
    require(value["artifact_workflow_edge_count"] == 12
            and value["artifact_trigger_relationship_count"] == 14
            and value["live_artifact_trigger_relationship_count"] == 2
            and value["historical_or_spent_artifact_trigger_relationship_count"] == 12,
            "V3 source-derived relation counts changed")
    require(value["evolution_transition_count"] == 14
            and value["current_evolution_ledger_sha256"] == EVOLUTION_LEDGER_SHA256,
            "V3 evolution ledger identity changed")
    require(value["checkpoint_e_status"] == value["p4_4_status"] == "INCOMPLETE",
            "V3 cannot claim Checkpoint E or P4.4 completion")
    require(value["closed_blocker_ids"] == [
        "PROTECTED_FRESH_HOLDOUT_PR119_EXACT_FALLBACK_NOT_DURABLY_RECOVERED",
        PR145_BLOCKER,
    ], "V3 must close blocker B only in addition to preserved blocker A")
    require(value["remaining_blocker_ids"] == [
        "CANONICAL_HISTORY_TRANSFER_SOURCE_NOT_FULLY_DURABLE", HISTORY_BLOCKER
    ], "V3 remaining blocker C/D identities changed")
    require(value["pr145_disposition"]["source_artifact_recovery_state"]
            == "METADATA_ONLY_NO_BYTES"
            and value["pr145_disposition"]["replay_authorized"] is False,
            "V3 overclaims historical source recovery or replay authority")


def audit() -> dict:
    expected = build_receipt()
    raw = (ROOT / RECEIPT_PATH).read_bytes()
    value = roles.strict_json(raw)
    require(raw.replace(b"\r\n", b"\n") == canonical_bytes(value),
            "retained-status V3 is not canonical JSON")
    validate_receipt(value, expected)
    return {
        "result": "PASS",
        "policy_id": POLICY_ID,
        "receipt_sha256": value["canonical_sha256"],
        "predecessor_v2_sha256": V2_RECEIPT_SHA256,
        "workflow_tree_sha1": value["current_workflow_tree_sha1"],
        "evolution_ledger_sha256": value["current_evolution_ledger_sha256"],
        "evolution_transition_count": value["evolution_transition_count"],
        "workflow_count": value["workflow_count"],
        "trigger_surface_count": value["trigger_surface_count"],
        "artifact_workflow_edge_count": value["artifact_workflow_edge_count"],
        "artifact_trigger_relationship_count": value["artifact_trigger_relationship_count"],
        "live_relation_count": value["live_artifact_trigger_relationship_count"],
        "historical_or_spent_relation_count": value[
            "historical_or_spent_artifact_trigger_relationship_count"
        ],
        "closed_blockers": value["closed_blocker_ids"],
        "remaining_blockers": value["remaining_blocker_ids"],
        "checkpoint_e": value["checkpoint_e_status"],
        "p4_4": value["p4_4_status"],
        "terminal": value["terminal"],
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
    except (OSError, RetainedWorkflowStatusV3Error, TypeError, ValueError) as exc:
        print(json.dumps({"result": "BLOCKED", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
