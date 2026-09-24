import inspect
from pathlib import Path

from scripts.issue_current_fotmob_reviewed_source import (
    build_verified_current_fotmob_bootstrap_from_capture,
    issue_current_fotmob_reviewed_source,
)


def _workflow() -> str:
    repository = Path(__file__).resolve().parents[1]
    return (
        repository / ".github/workflows/issue-current-fotmob-reviewed-source.yml"
    ).read_text(encoding="utf-8")


def test_current_fotmob_workflow_uses_env_transport_and_only_date_reaches_provider_command() -> None:
    workflow = _workflow()
    assert "ATHENA_FOTMOB_REQUEST_DATE: ${{ inputs.date }}" in workflow
    assert "ATHENA_FOTMOB_REQUEST_TIMEZONE: ${{ inputs.timezone }}" in workflow
    assert "ATHENA_FOTMOB_REQUEST_CCODE3: ${{ inputs.ccode3 }}" in workflow
    assert '--date "${ATHENA_FOTMOB_REQUEST_DATE}"' in workflow
    assert '--timezone "${ATHENA_FOTMOB_REQUEST_TIMEZONE}"' not in workflow
    assert '--ccode3 "${ATHENA_FOTMOB_REQUEST_CCODE3}"' not in workflow
    assert "--date '${{ inputs.date }}'" not in workflow
    assert "--timezone '${{ inputs.timezone }}'" not in workflow
    assert "--ccode3 '${{ inputs.ccode3 }}'" not in workflow
    assert "fotmob-data-matches-captures/${{ inputs.date }}" not in workflow


def test_current_fotmob_workflow_is_canonical_or_fail_closed_only() -> None:
    workflow = _workflow()
    canonical = workflow.split(
        "- name: Issue current reviewed FotMob fixture bootstrap via canonical ingest",
        1,
    )[1].split(
        "- name: Reject unsupported noncanonical current-source request",
        1,
    )[0]
    rejected = workflow.split(
        "- name: Reject unsupported noncanonical current-source request",
        1,
    )[1].split(
        "- name: Upload reviewed source receipt and exact raw evidence",
        1,
    )[0]
    triggers = workflow.split("on:", 1)[1].split("permissions:", 1)[0]

    assert triggers.count("workflow_dispatch:") == 1
    assert "schedule:" not in triggers
    assert "push:" not in triggers
    assert "pull_request:" not in triggers
    assert "issue_comment:" not in triggers
    assert triggers.count("      date:") == 1
    assert triggers.count("      timezone:") == 1
    assert triggers.count("      ccode3:") == 1
    assert "default: UTC" in triggers
    assert "default: NGA" in triggers
    assert triggers.count("required: true") == 3
    assert triggers.count("type: string") == 3

    assert "permissions:\n  contents: read" in workflow
    assert "runs-on: ubuntu-latest" in workflow
    assert "timeout-minutes: 10" in workflow
    assert "if: ${{ inputs.timezone == 'UTC' && inputs.ccode3 == 'NGA' }}" in canonical
    assert "if: ${{ inputs.timezone != 'UTC' || inputs.ccode3 != 'NGA' }}" in rejected
    assert "scripts/issue_current_fotmob_reviewed_source_via_ingest.py" in canonical
    assert "scripts/issue_current_fotmob_reviewed_source.py" not in workflow
    assert "scripts/issue_current_fotmob_reviewed_source_via_ingest.py" not in rejected
    assert "--execute-live-network" in canonical
    assert "--execute-live-network" not in rejected
    assert "UNSUPPORTED_CURRENT_FOTMOB_WORKFLOW_SCOPE_REQUIRES_UTC_NGA" in rejected
    assert 'os.environ["ATHENA_FOTMOB_REQUEST_DATE"]' in rejected
    assert 'os.environ["ATHENA_FOTMOB_REQUEST_TIMEZONE"]' in rejected
    assert 'os.environ["ATHENA_FOTMOB_REQUEST_CCODE3"]' in rejected
    assert '"provider": "fotmob"' in rejected
    assert '"wager_placed": False' in rejected
    assert "exit 1" in rejected
    assert "GITHUB_SHA" not in canonical
    assert "GITHUB_REF" not in canonical
    assert "--minimum-lead-seconds" not in workflow
    assert "--max-source-age-seconds" not in workflow
    assert "continue-on-error:" not in workflow
    assert "workflow_run:" not in triggers
    assert "if: always()" in workflow
    assert "name: current-fotmob-reviewed-source-${{ github.run_id }}" in workflow
    assert "retention-days: 7" in workflow
    assert "if-no-files-found: error" in workflow
    assert ".cache/athena-research/current-fotmob-reviewed-source/execution.json" in workflow
    assert ".cache/athena-research/fotmob-data-matches-captures/" in workflow
    assert "artifacts/athena-ingest-workflow/" in workflow
    assert "athena-ingest.yml" not in workflow
    assert "SportyBet" not in workflow
    assert "share-code" not in workflow.lower()


def test_current_fotmob_workflow_has_no_policy_bound_dispatch_inputs() -> None:
    workflow = _workflow()
    assert "minimum_lead_seconds:" not in workflow
    assert "max_source_age_seconds:" not in workflow
    assert "--minimum-lead-seconds" not in workflow
    assert "--max-source-age-seconds" not in workflow


def test_live_and_replay_entry_points_cannot_override_policy_bounds() -> None:
    for callable_ in (
        issue_current_fotmob_reviewed_source,
        build_verified_current_fotmob_bootstrap_from_capture,
    ):
        parameters = inspect.signature(callable_).parameters
        assert "minimum_lead_seconds" not in parameters
        assert "max_source_age_seconds" not in parameters
