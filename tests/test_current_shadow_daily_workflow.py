from pathlib import Path


def test_current_shadow_workflow_is_single_daily_and_on_demand_surface():
    path = Path(".github/workflows/current-shadow-all-market.yml")
    text = path.read_text(encoding="utf-8")

    assert 'cron: "0 7 * * *"' in text
    assert "workflow_dispatch:" in text
    assert 'default: "20"' in text
    assert "fixture_scope:" in text
    assert "- today" in text
    assert "- three-day" in text
    assert "python -m scripts.execute_current_shadow_daily" in text
    assert "python -m scripts.send_current_shadow_email" in text
    assert "--target-size \"${ATHENA_TARGET_SIZE}\"" in text
    assert "--fixture-scope \"${ATHENA_FIXTURE_SCOPE}\"" in text
    assert "cancel-in-progress: false" in text
    assert "build_acca.py generate" not in text


def test_legacy_daily_accumulator_workflow_is_retired():
    assert not Path(".github/workflows/daily_acca.yml").exists()
