from pathlib import Path


def _workflow_text() -> str:
    root = Path(__file__).resolve().parents[1]
    return (
        root / ".github" / "workflows" / "p3-0-comparison-evidence-capture.yml"
    ).read_text(encoding="utf-8")


def test_failed_capture_preserves_exact_source_material_in_separate_artifact():
    text = _workflow_text()
    marker = "      - name: Upload P3.0-E1 source diagnostics on capture failure\n"
    start = text.index(marker)
    step = text[start:]

    assert "        if: failure()" in step
    assert "name: p3-0-comparison-evidence-source-diagnostics" in step
    for path in (
        "artifacts/p3-0-comparison-evidence",
        ".cache/athena-research/fotmob-data-matches-captures",
        ".cache/athena-research/current-shadow-sportybet-catalog-fanout",
        ".cache/athena-research/sportybet-live-event-quote-evidence",
        ".cache/athena-research/current-shadow-fixture-identity-v2",
    ):
        assert path in step
    assert "retention-days: 30" in step


def test_failure_diagnostic_retention_does_not_add_write_or_betting_authority():
    text = _workflow_text()
    assert "contents: read" in text
    assert "actions: read" in text
    assert "contents: write" not in text
    assert "actions: write" not in text
    for forbidden in (
        "send_current_shadow_email",
        "share-code",
        "wallet",
        "staking",
        "wager",
        "BET",
    ):
        assert forbidden not in text
