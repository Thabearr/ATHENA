from pathlib import Path

import yaml


WORKFLOW = Path(
    ".github/workflows/audit-fotmob-utc-native-xg-fresh-holdout-lineage.yml"
)


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_open_control_issue_workflow_remains_valid_yaml():
    parsed = yaml.safe_load(_text())
    assert isinstance(parsed, dict)
    assert isinstance(parsed.get("jobs"), dict)
    assert "audit" in parsed["jobs"]


def test_open_issue_172_is_primary_exact_non_pr_control_surface():
    text = _text()
    assert "github.event.issue.number == 172" in text
    assert "!github.event.issue.pull_request" in text
    assert "github.event.issue.state == 'open'" in text
    assert "const controlIssue = 172;" in text
    assert (
        "const exactControlIssueTitle = "
        "'ATHENA Fresh-Holdout Lineage Audit Control';"
    ) in text
    assert "issue_number: controlIssue" in text
    assert "issue.state !== 'open' || issue.pull_request" in text
    assert "issue.user?.login !== context.repo.owner" in text
    assert "issue.title !== exactControlIssueTitle" in text


def test_legacy_pr_170_remains_fail_closed_fallback_only():
    text = _text()
    assert "github.event.issue.number == 170" in text
    assert "const legacyControlPr = 170;" in text
    assert "pull_number: legacyControlPr" in text
    assert "pr.state !== 'closed' || !pr.merged_at || !pr.merge_commit_sha" in text
    assert "Legacy control PR #170 must remain merged and closed." in text


def test_exact_owner_command_and_current_main_still_gate_authorization():
    text = _text()
    command = (
        "^\\/athena-audit-fresh-holdout-lineage\\n"
        "main-sha: ([0-9a-f]{40})\\n"
        "confirm: READ_ONLY_ACTIONS_LINEAGE_AUDIT$"
    )
    assert command in text
    assert "context.payload.comment.user.login !== context.repo.owner" in text
    assert "if (ref.object.sha !== expectedMain)" in text
    assert "core.setOutput('comment_target', String(context.issue.number));" in text
    assert "core.setOutput('authorized', 'true');" in text
    assert text.index("if (ref.object.sha !== expectedMain)") < text.index(
        "core.setOutput('authorized', 'true');"
    )


def test_success_and_failure_results_return_to_exact_authorized_surface():
    text = _text()
    assert text.count("if (target === 172)") == 2
    assert text.count("issue_number: 172") == 2
    assert text.count("else if (target === 170)") == 2
    assert text.count("issue_number: 170") == 2
    assert text.count("Unexpected authorized comment target") == 2
    assert "steps.guard.outputs.comment_target" in text


def test_open_issue_migration_preserves_read_only_network_and_authority_boundary():
    text = _text().lower()
    assert "actions: read" in text
    assert "contents: read" in text
    assert "issues: write" in text
    assert "actions: write" not in text
    assert "contents: write" not in text
    assert "continue-on-error" not in text
    assert "rerun" not in text
    assert "fotmob.com" not in text
    assert "sportybet.com" not in text
    assert "api.sportradar.com" not in text
    assert "curl " not in text
    assert "wget " not in text
    for line in (
        "provider-network-acquisition-performed-by-audit: false",
        "backfill-authorized: false",
        "model-approval-authorized: false",
        "pricing-authorized: false",
        "selection-authorized: false",
        "bet-authorized: false",
    ):
        assert line in text


def test_result_comments_cannot_self_authorize_followup_audit():
    text = _text()
    success = text[text.index("- name: Post compact audit result") :]
    failure = text[text.index("- name: Post fail-closed control-workflow result") :]
    assert "/athena-audit-fresh-holdout-lineage" not in success
    assert "READ_ONLY_ACTIONS_LINEAGE_AUDIT" not in success
    assert "/athena-audit-fresh-holdout-lineage" not in failure
    assert "READ_ONLY_ACTIONS_LINEAGE_AUDIT" not in failure
