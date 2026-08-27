from pathlib import Path


def test_current_fotmob_workflow_uses_env_transport_for_dispatch_inputs() -> None:
    repository = Path(__file__).resolve().parents[1]
    workflow = (
        repository / ".github/workflows/issue-current-fotmob-reviewed-source.yml"
    ).read_text(encoding="utf-8")

    assert "ATHENA_FOTMOB_REQUEST_DATE: ${{ inputs.date }}" in workflow
    assert "ATHENA_FOTMOB_REQUEST_TIMEZONE: ${{ inputs.timezone }}" in workflow
    assert "ATHENA_FOTMOB_REQUEST_CCODE3: ${{ inputs.ccode3 }}" in workflow
    assert '--date "${ATHENA_FOTMOB_REQUEST_DATE}"' in workflow
    assert '--timezone "${ATHENA_FOTMOB_REQUEST_TIMEZONE}"' in workflow
    assert '--ccode3 "${ATHENA_FOTMOB_REQUEST_CCODE3}"' in workflow

    assert "--date '${{ inputs.date }}'" not in workflow
    assert "--timezone '${{ inputs.timezone }}'" not in workflow
    assert "--ccode3 '${{ inputs.ccode3 }}'" not in workflow
    assert "fotmob-data-matches-captures/${{ inputs.date }}" not in workflow


def test_current_fotmob_workflow_has_no_policy_bound_dispatch_inputs() -> None:
    repository = Path(__file__).resolve().parents[1]
    workflow = (
        repository / ".github/workflows/issue-current-fotmob-reviewed-source.yml"
    ).read_text(encoding="utf-8")

    assert "minimum_lead_seconds:" not in workflow
    assert "max_source_age_seconds:" not in workflow
    assert "--minimum-lead-seconds" not in workflow
    assert "--max-source-age-seconds" not in workflow
