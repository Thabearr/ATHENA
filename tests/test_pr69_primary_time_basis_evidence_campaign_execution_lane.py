from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/execute-pr69-primary-time-basis-evidence-campaign.yml"
DOC = ROOT / "docs/pr69_primary_time_basis_evidence_campaign_execution_lane.md"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def test_execution_workflow_is_valid_yaml() -> None:
    assert yaml.compose(_workflow()) is not None


def test_execution_lane_is_issue_comment_only_and_bound_to_pr128_owner() -> None:
    text = _workflow()
    assert "issue_comment:" in text
    assert "workflow_dispatch:" not in text
    assert "schedule:" not in text
    assert "push:" not in text
    assert "github.event.issue.number == 128" in text
    assert "github.event.comment.user.login == 'Thabearr'" in text
    assert "startsWith(github.event.comment.body, '/athena-run-pr69-time-basis-evidence')" in text
    assert "const controlPr = 128;" in text


def test_execution_command_requires_exact_current_main_and_confirmation() -> None:
    text = _workflow()
    assert "lines.length !== 3" in text
    assert "lines[0] !== '/athena-run-pr69-time-basis-evidence'" in text
    assert "/^main-sha: ([0-9a-f]{40})$/" in text
    assert "confirm: EXECUTE_8_PRIMARY_TIME_BASIS_CAPTURES" in text
    assert "!pr.merged_at || pr.state !== 'closed'" in text
    assert "ref.object.sha !== expectedMain" in text
    assert "repository.default_branch" in text


def test_one_shot_marker_is_durable_before_checkout_and_blocks_replay() -> None:
    text = _workflow()
    marker = "ATHENA_PR69_PRIMARY_TIME_BASIS_EVIDENCE_EXECUTION_ATTEMPT_V1"
    assert marker in text
    assert "priorMarker" in text
    assert "automatic replay is forbidden and requires reviewed reconciliation" in text
    assert "ATTEMPT_STARTED_NO_RESULT_YET" in text
    assert text.index("github.rest.issues.createComment") < text.index("Check out exact authorized main")


def test_execution_lane_permissions_are_narrow_but_allow_closed_pr_audit() -> None:
    text = _workflow()
    assert "contents: read" in text
    assert "issues: write" in text
    assert "pull-requests: write" in text
    assert "contents: write" not in text
    assert "persist-credentials: false" in text


def test_exact_merged_runner_protocol_and_dependency_blobs_are_pinned() -> None:
    text = _workflow()
    assert "6a990059cdc86297bb58a328afd4cb1fcd2c35d1" in text
    assert "4b9bfd0a1acc25ad3568d5087b94fa3bd3e98e97" in text
    assert "df1a25227b8fee5fbbb21dce7f5f8be5d2464954" in text
    assert "54d24a55dfa4c73ba3910d333257cfd2e68daf4b" in text
    assert "git rev-parse HEAD:domain/pr69_primary_time_basis_evidence_acquisition_runner.py" in text
    assert "git rev-parse HEAD:scripts/run_pr69_primary_time_basis_evidence_acquisition.py" in text
    assert "git rev-parse HEAD:domain/pr69_primary_time_basis_evidence_acquisition_protocol.py" in text
    assert "git rev-parse HEAD:requirements.txt" in text


def test_preflight_is_network_free_exact_empty_campaign_state() -> None:
    text = _workflow()
    assert "--status > campaign-preflight-status.json" in text
    assert "'completed_slots': 0" in text
    assert "'total_slots': 8" in text
    assert "'complete': False" in text
    assert "'blocked': False" in text
    assert "'inflight_attempt': None" in text
    assert "next_slot.get('ordinal') != 1" in text
    assert "'network_acquisition_performed_by_this_status_command': False" in text
    assert "'pr69_source_local_time_basis_resolved': False" in text
    assert "'bet_authorized': False" in text


def test_live_step_invokes_only_full_reviewed_campaign_without_overrides() -> None:
    text = _workflow()
    command = (
        "python scripts/run_pr69_primary_time_basis_evidence_acquisition.py "
        "--execute-reviewed-protocol"
    )
    assert text.count(command) == 1
    assert "--max-successful-slots" not in text
    assert "--repository-root" not in text
    assert "curl " not in text
    assert "wget " not in text
    assert "workflow_dispatch" not in text


def test_execution_metadata_freezes_request_and_schedule_without_semantics() -> None:
    text = _workflow()
    assert "'primary_origin': 'https://www.football-data.co.uk'" in text
    assert "['Accept', 'text/plain,text/html;q=0.9,*/*;q=0.1']" in text
    assert "['Accept-Encoding', 'identity']" in text
    assert "['User-Agent', 'ATHENA/1.0']" in text
    assert "'successful_capture_target': 8" in text
    assert "'target_count': 4" in text
    assert "'minimum_pair_separation_seconds': 300" in text
    assert "'maximum_pair_separation_seconds': 3600" in text
    assert "'retry_delays_seconds': [60, 300]" in text
    assert "'pr69_time_basis_resolution_authorized': False" in text
    assert "'bet_authorized': False" in text


def test_failure_paths_preserve_post_status_package_and_artifact() -> None:
    text = _workflow()
    assert "Capture network-free post-run status" in text
    assert "Package immutable execution evidence" in text
    assert "Assess preserved campaign state without semantic interpretation" in text
    assert "actions/upload-artifact@v4" in text
    assert "if: always()" in text
    assert "retention-days: 30" in text
    assert "pr69-primary-time-basis-evidence-campaign-${{ github.run_id }}" in text
    assert "pr69-primary-time-basis-evidence.tar" in text
    assert "package-metadata.json" in text
    assert "archive_sha256" in text
    assert "PACKAGE_OUTCOME: ${{ steps.package.outcome }}" in text
    assert "package_outcome == 'success'" in text


def test_success_gate_requires_exact_eight_captures_pairs_and_clean_state() -> None:
    text = _workflow()
    assert "status.get('completed_slots') == 8" in text
    assert "status.get('total_slots') == 8" in text
    assert "status.get('complete') is True" in text
    assert "status.get('blocked') is False" in text
    assert "status.get('inflight_attempt') is None" in text
    assert "status.get('next_slot') is None" in text
    assert "len(pairs) == 4" in text
    assert "300 <= separation <= 3600" in text
    assert "len(rows) == 8" in text
    assert "row.get('event_type') == 'SLOT_SUCCEEDED'" in text
    assert "not (root / 'inflight-attempt.json').exists()" in text
    assert "not (root / 'runner.lock').exists()" in text
    assert "archive.is_file()" in text
    assert "package_metadata.is_file()" in text


def test_final_result_requires_package_artifact_and_never_promotes_semantics() -> None:
    text = _workflow()
    assert "const packageOk = process.env.PACKAGE_OUTCOME === 'success';" in text
    assert "const qualified = stateOk && packageOk && uploadOk;" in text
    assert "PRIMARY_EVIDENCE_CAMPAIGN_EXECUTED_AND_PRESERVED_PENDING_SEMANTIC_QUALIFICATION" in text
    assert "EXECUTION_NOT_QUALIFIED_REVIEW_ARTIFACT_BEFORE_ANY_RETRY" in text
    assert "semantic-extraction: false" in text
    assert "historical-effective-scope-qualification: false" in text
    assert "pr69-source-local-time-basis-resolution: false" in text
    assert "model/probability/pricing/selection/production/BET authority: false" in text
    assert "Automatic replay is forbidden" in text


def test_documentation_preserves_separate_execution_and_semantic_boundaries() -> None:
    text = _doc()
    assert "**Control plane only. This PR does not execute the live campaign.**" in text
    assert "PR #128" in text
    assert "separate explicit live execution authorization" in text
    assert "EXECUTE_8_PRIMARY_TIME_BASIS_CAPTURES" in text
    assert "EXECUTION_NOT_QUALIFIED_REVIEW_ARTIFACT_BEFORE_ANY_RETRY" in text
    assert "PRIMARY_EVIDENCE_CAMPAIGN_EXECUTED_AND_PRESERVED_PENDING_SEMANTIC_QUALIFICATION" in text
    assert "infer a PR69 source-local timezone" in text
    assert "authorize BET" in text
