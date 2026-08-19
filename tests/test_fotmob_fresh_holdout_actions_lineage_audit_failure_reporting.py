from pathlib import Path

import yaml


WORKFLOW = Path(
    ".github/workflows/audit-fotmob-utc-native-xg-fresh-holdout-lineage.yml"
)


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_failure_reporting_workflow_remains_valid_yaml():
    parsed = yaml.safe_load(_text())
    assert isinstance(parsed, dict)
    assert isinstance(parsed.get("jobs"), dict)
    assert "audit" in parsed["jobs"]


def test_authorized_guard_exposes_exact_failure_reporting_anchor_only_after_main_check():
    text = _text()
    main_check = "if (ref.object.sha !== expectedMain)"
    authorized = "core.setOutput('authorized', 'true');"
    assert main_check in text
    assert authorized in text
    assert text.index(main_check) < text.index(authorized)
    assert "core.setOutput('main_sha', expectedMain);" in text


def test_audit_step_is_named_and_success_path_remains_success_only():
    text = _text()
    assert "- name: Execute read-only GitHub lineage audit\n        id: lineage_audit" in text
    assert "- name: Upload audit result\n        if: ${{ success() }}" in text
    assert "- name: Post compact audit result\n        if: ${{ success() }}" in text
    assert "continue-on-error" not in text


def test_failure_comment_runs_only_after_authorized_control_workflow_failure():
    text = _text()
    marker = "- name: Post fail-closed control-workflow result"
    condition = "if: ${{ failure() && steps.guard.outputs.authorized == 'true' }}"
    assert marker in text
    assert condition in text
    assert text.index(marker) > text.index("- name: Post compact audit result")


def test_failure_comment_is_explicitly_non_authoritative_and_does_not_invent_lineage():
    text = _text()
    assert "audit-state: AUDIT_CONTROL_WORKFLOW_FAILED_CLOSED" in text
    assert "lineage-result-authority: false" in text
    assert "first-slot-status: NOT_DERIVED" in text
    assert "audit-actions-run-id: ${context.runId}" in text
    assert "first-run-id:" not in text[text.index("- name: Post fail-closed control-workflow result") :]
    assert "first-run-head-sha:" not in text[text.index("- name: Post fail-closed control-workflow result") :]


def test_failure_reporting_keeps_every_downstream_authority_false():
    full_text = _text()
    text = full_text[full_text.index("- name: Post fail-closed control-workflow result") :]
    for line in (
        "provider-network-acquisition-performed-by-audit: false",
        "backfill-authorized: false",
        "model-approval-authorized: false",
        "production-authorized: false",
        "pricing-authorized: false",
        "selection-authorized: false",
        "bet-authorized: false",
    ):
        assert line in text


def test_failure_reporting_does_not_add_retry_write_or_provider_acquisition_surface():
    text = _text().lower()
    assert "actions: write" not in text
    assert "contents: write" not in text
    assert "continue-on-error" not in text
    assert "rerun" not in text
    assert "fotmob.com" not in text
    assert "sportybet.com" not in text
    assert "api.sportradar.com" not in text
    assert "curl " not in text
    assert "wget " not in text


def test_failure_result_comment_cannot_self_authorize_another_audit():
    text = _text()
    failure_section = text[text.index("- name: Post fail-closed control-workflow result") :]
    assert "ATHENA FRESH-HOLDOUT LINEAGE AUDIT" in failure_section
    assert "/athena-audit-fresh-holdout-lineage" not in failure_section
    assert "READ_ONLY_ACTIONS_LINEAGE_AUDIT" not in failure_section
