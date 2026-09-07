from pathlib import Path


def test_current_shadow_workflow_is_single_daily_and_on_demand_surface():
    path = Path(".github/workflows/current-shadow-all-market.yml")
    text = path.read_text(encoding="utf-8")

    assert 'cron: "0 9 * * *"' in text
    assert "workflow_dispatch:" in text
    assert "issue_comment:" in text
    assert "github.event.issue.number == 276" in text
    assert "github.event.comment.user.login == github.repository_owner" in text
    assert "'/athena-shadow '" in text
    assert r"/athena-shadow target=([0-9]+) scope=(today|three-day)" in text
    assert r"/athena-shadow target=([0-9]+) dates=([0-9]{8}(?:,[0-9]{8}){0,6})" in text
    assert 'default: "20"' in text
    assert "fixture_scope:" in text
    assert "fixture_dates:" in text
    assert "- today" in text
    assert "- three-day" in text
    assert "python -m scripts.execute_current_shadow_request" in text
    assert "python -m scripts.execute_current_shadow_daily" not in text
    assert "python -m scripts.send_current_shadow_email" in text
    assert "current-shadow-email-delivery-receipt.json" in text
    assert 'if [ -z "${GMAIL_ADDRESS}" ]' not in text
    assert "--target-size \"${ATHENA_TARGET_SIZE}\"" in text
    assert "--fixture-scope \"${ATHENA_FIXTURE_SCOPE}\"" in text
    assert "--fixture-dates \"${ATHENA_FIXTURE_DATES}\"" in text
    assert "current_shadow_fixture_date_request" in text
    assert "9249856559" in text
    assert "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f" in text
    assert "cancel-in-progress: false" in text
    assert "build_acca.py generate" not in text


def test_legacy_daily_accumulator_workflow_is_retired():
    assert not Path(".github/workflows/daily_acca.yml").exists()
