from pathlib import Path

import yaml


WORKFLOW = Path(
    ".github/workflows/execute-fotmob-utc-native-successor-feature-qualification-v2.yml"
)


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_v2_workflow_yaml_is_parseable() -> None:
    parsed = yaml.safe_load(_text())
    assert isinstance(parsed, dict)
    assert parsed["name"] == "Execute Reconciled FotMob UTC-Native Successor Feature Qualification V2"


def test_v2_is_bound_to_exact_control_pr_owner_and_command() -> None:
    text = _text()
    required = (
        "github.event.issue.number == 139",
        "github.event.comment.user.login == 'Thabearr'",
        "const controlPr = 139;",
        "V2 qualification control PR must already be merged and closed.",
        "/athena-run-fotmob-utc-native-feature-qualification-v2",
        "confirm: EXECUTE_RECONCILED_21326_UTC_NATIVE_FEATURE_QUALIFICATION_V2",
        "Current ${repository.default_branch}=",
    )
    for token in required:
        assert token in text


def test_v2_fixes_pr_comment_write_permission_regression() -> None:
    text = _text()
    assert "issues: write" in text
    assert "pull-requests: write" in text
    assert "pull-requests: read" not in text
    assert "github.rest.issues.createComment" in text


def test_v2_requires_exact_v1_reconciliation_receipt_identity() -> None:
    text = _text()
    required = (
        "const v1ReconciliationCommentId = 5311071999;",
        "comment.id === v1ReconciliationCommentId",
        "comment.user.login === 'Thabearr'",
        "ATHENA_FOTMOB_UTC_NATIVE_FEATURE_QUALIFICATION_V1_RECONCILIATION",
        "run-id: 31987862156",
        "main-sha: 2bd05e98cd74f9db6fa59472c05d5253f69d0f68",
        "command-comment-id: 5311067273",
        "runner-executed: false",
        "artifact-download-executed: false",
        "failure-evidence-artifact-id: 9274313978",
        "failure-evidence-artifact-sha256: 1a46808c8ee4d21ab67ec03b1fd6c0a80e79fadf04933092e7a106522e31c337",
        "failure-evidence-artifact-size: 2388",
        "V1_SPENT_GUARD_PERMISSION_FAILURE_NO_QUALIFICATION_EXECUTED_DO_NOT_REPLAY",
        "Required reviewed V1 reconciliation receipt identity is missing or changed.",
    )
    for token in required:
        assert token in text


def test_v2_is_one_shot_and_replay_fails_closed() -> None:
    text = _text()
    assert "ATHENA_FOTMOB_UTC_NATIVE_FEATURE_QUALIFICATION_ATTEMPT_V2" in text
    assert "A prior V2 qualification execution attempt marker already exists" in text
    assert "automatic replay is forbidden and requires reviewed reconciliation" in text
    assert "cancel-in-progress: false" in text


def test_exact_reviewed_runner_and_dependency_blobs_remain_pinned() -> None:
    text = _text()
    for sha in (
        "9c9e424791b65292f7bbe8849b3214c140834889",
        "68503c85569f31532a1a810249073c36242055e0",
        "57cc133a7fb9daa76c5d5d8e9156903e583c6575",
        "2409676b4993a25024e2e8554e84e3525e7c5e6e",
        "54d24a55dfa4c73ba3910d333257cfd2e68daf4b",
    ):
        assert sha in text
    assert 'test "$(git rev-parse HEAD)" = "${{ steps.guard.outputs.main_sha }}"' in text


def test_preserved_pr119_artifact_identity_and_archive_bytes_remain_exact() -> None:
    text = _text()
    required = (
        "artifactId = 9249856559",
        "fotmob-ordinary-ft-source-history-campaign-31887523012",
        "size: 61886753",
        "sha256:7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f",
        "runId: 31887523012",
        "headSha: '12a32de1cca8ffb657f67fa4a8d3106aec6ce31b'",
        "artifact.expired",
        'gh api "/repos/${GITHUB_REPOSITORY}/actions/artifacts/${ARTIFACT_ID}/zip"',
        'test "${actual_size}" = "${EXPECTED_SIZE}"',
        'test "${actual_sha256}" = "${EXPECTED_SHA256}"',
    )
    for token in required:
        assert token in text


def test_external_actions_are_immutable_commit_pinned() -> None:
    text = _text()
    assert "actions/checkout@11d5960a326750d5838078e36cf38b85af677262" in text
    assert "actions/github-script@f28e40c7f34bde8b3046d885e986cb6290c5673b" in text
    assert "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065" in text
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in text
    assert "actions/checkout@v" not in text
    assert "actions/github-script@v" not in text
    assert "actions/setup-python@v" not in text
    assert "actions/upload-artifact@v" not in text


def test_exact_offline_runner_emits_v2_receipt_and_projection() -> None:
    text = _text()
    assert "python scripts/qualify_fotmob_utc_native_successor_feature_construction.py" in text
    assert "pr119-preserved-artifact.zip" in text
    assert "--output qualification-v2-receipt.json" in text
    assert "--projection-output utc-native-feature-projection-v2.ndjson" in text
    assert "network_performed_by_qualification_runner': False" in text


def test_v2_success_gate_proves_exact_21326_row_research_result_only() -> None:
    text = _text()
    required = (
        "QUALIFIED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION",
        "EXECUTED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION_MODEL_USE_UNREVIEWED",
        "PRE_REGISTER_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_PROTOCOL",
        "projection.get('record_count') != 21326",
        "projection.get('total_rows_seen') != 21326",
        "projection.get('unique_fixture_count') != 21326",
        "identity_or_lineage_conflict_count",
        "{'AVAILABLE': 0, 'MISSING': 0, 'BLOCKED': 21326}",
        "NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE",
        "source_local_kickoff",
        "one or more downstream safety flags are not false",
    )
    for token in required:
        assert token in text


def test_v2_failure_evidence_is_preserved_and_not_auto_replayed() -> None:
    text = _text()
    assert "if: always()" in text
    assert "qualification-v2-artifact/" in text
    assert "if-no-files-found: error" in text
    assert "retention-days: 30" in text
    assert "EXECUTION_COMPLETED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION_EVIDENCE_PRESERVED_V2" in text
    assert "EXECUTION_NOT_QUALIFIED_V2_REVIEW_ARTIFACT_BEFORE_ANY_RETRY" in text
    assert (
        "Feature qualification evidence only. No model, pricing, selection, production, or BET authority is granted."
        in text
    )
