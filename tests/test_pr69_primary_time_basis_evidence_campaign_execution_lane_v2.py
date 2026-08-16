from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/execute-pr69-primary-time-basis-evidence-campaign-v2.yml"
DOC = ROOT / "docs/pr69_primary_time_basis_evidence_campaign_reconciled_execution_lane_v2.md"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_v2_control_workflow_parses_as_yaml() -> None:
    parsed = yaml.safe_load(_workflow())
    assert isinstance(parsed, dict)
    assert "jobs" in parsed
    assert "execute" in parsed["jobs"]


def test_v2_lane_is_owner_only_pr130_and_exact_command() -> None:
    text = _workflow()
    assert "github.event.issue.number == 130" in text
    assert "github.event.comment.user.login == 'Thabearr'" in text
    assert "/athena-run-pr69-time-basis-evidence-v2" in text
    assert "confirm: EXECUTE_RECONCILED_8_PRIMARY_TIME_BASIS_CAPTURES_V2" in text
    assert "const controlPr = 130;" in text
    assert "Campaign V2 control PR must already be merged and closed." in text


def test_v2_lane_binds_exact_failed_receipt_artifact_and_fix() -> None:
    text = _workflow()
    required = (
        "const priorControlPr = 128;",
        "const fixPr = 129;",
        "94577458d4b8af59a4e986edb2e4df9c426e21be",
        "31953949073",
        "9266604353",
        "pr69-primary-time-basis-evidence-campaign-31953949073",
        "ce87f13cb72a917c0a01e4bbede87e4123d85861d5ee1cd98667bb802d380db7",
        "EXECUTION_NOT_QUALIFIED_REVIEW_ARTIFACT_BEFORE_ANY_RETRY",
        "github.rest.actions.getArtifact",
        "priorArtifact.digest !== expectedArtifactDigest",
        "String(priorArtifact.workflow_run?.id || '') !== priorRunId",
        "ATHENA_PR69_PRIMARY_TIME_BASIS_EVIDENCE_EXECUTION_ATTEMPT_V2",
    )
    for value in required:
        assert value in text


def test_v2_lane_pins_exact_reconciled_main_inputs() -> None:
    text = _workflow()
    for value in (
        "04c30b177c2338848a448972cc0cfad0328e602c",
        "b44a010d0957ad8d76474aae2f090d52ae5b0e6e",
        "df1a25227b8fee5fbbb21dce7f5f8be5d2464954",
        "54d24a55dfa4c73ba3910d333257cfd2e68daf4b",
        "git merge-base --is-ancestor 94577458d4b8af59a4e986edb2e4df9c426e21be HEAD",
    ):
        assert value in text


def test_v2_external_actions_are_immutable_commit_pins() -> None:
    text = _workflow()
    assert "actions/checkout@11d5960a326750d5838078e36cf38b85af677262" in text
    assert "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065" in text
    assert "actions/github-script@f28e40c7f34bde8b3046d885e986cb6290c5673b" in text
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in text
    for movable in ("actions/checkout@v4", "actions/setup-python@v5", "actions/github-script@v7", "actions/upload-artifact@v4"):
        assert movable not in text


def test_v2_lane_preserves_frozen_protocol_order_and_timing() -> None:
    text = _workflow()
    assert "ALL_TARGETS_SLOT_A_IN_FROZEN_ORDER_THEN_ALL_TARGETS_SLOT_B_IN_FROZEN_ORDER" in text
    assert "'minimum_pair_separation_seconds': 300" in text
    assert "'maximum_pair_separation_seconds': 3600" in text
    assert "'maximum_attempts_per_slot': 3" in text
    assert "'retry_delays_seconds': [60, 300]" in text
    assert "--execute-reviewed-protocol" in text
    assert "--max-successful-slots" not in text
    assert "--repository-root" not in text


def test_v2_preflight_and_post_status_are_network_free_and_fail_closed() -> None:
    text = _workflow()
    assert text.count("--status") == 2
    for key in (
        "'semantic_extraction_performed': False",
        "'historical_effective_scope_qualified': False",
        "'pr69_source_local_time_basis_resolved': False",
        "'pr80_constructor_input_authorized': False",
        "'model_training_authorized': False",
        "'probability_inference_authorized': False",
        "'pricing_authorized': False",
        "'selection_authorized': False",
        "'production_approval_authorized': False",
        "'bet_authorized': False",
    ):
        assert key in text


def test_v2_preservation_gate_requires_package_assessment_and_artifact() -> None:
    text = _workflow()
    assert "if: always() && steps.guard.outcome == 'success'" in text
    assert "packageOutcome === 'success'" in text
    assert "assessOutcome === 'success'" in text
    assert "assessmentValid === 'true'" in text
    assert "artifactOutcome === 'success'" in text
    assert "PRIMARY_EVIDENCE_CAMPAIGN_V2_EXECUTED_AND_PRESERVED_PENDING_SEMANTIC_QUALIFICATION" in text
    assert "EXECUTION_V2_NOT_QUALIFIED_REVIEW_ARTIFACT_BEFORE_ANY_FURTHER_RETRY" in text
    assert "Automatic replay remains forbidden" in text


def test_v2_docs_keep_semantic_and_downstream_authority_closed() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "Control plane only. This boundary does not execute the live campaign." in text
    assert "does not infer the football-data.co.uk CSV timezone" in text
    assert "authorize PR80 constructor input" in text
    assert "authorize BET" in text
    assert "separate explicit V2 live-execution authorization" in text
