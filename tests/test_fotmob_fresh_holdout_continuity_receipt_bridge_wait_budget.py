from __future__ import annotations

from pathlib import Path


BRIDGE = Path(
    ".github/workflows/bridge-fotmob-fresh-holdout-continuity-receipts.yml"
)
PRIMARY = Path(".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml")


def test_bridge_wait_outlives_primary_collection_execution_budget_with_margin() -> None:
    bridge = BRIDGE.read_text(encoding="utf-8")
    primary = PRIMARY.read_text(encoding="utf-8")

    primary_timeout_minutes = 25
    bridge_wait_attempts = 1051
    bridge_poll_seconds = 2
    bridge_timeout_minutes = 45

    assert f"timeout-minutes: {primary_timeout_minutes}" in primary
    assert f"for _attempt in range({bridge_wait_attempts}):" in bridge
    assert "time.sleep(2)" in bridge
    assert f"timeout-minutes: {bridge_timeout_minutes}" in bridge

    # The receipt bridge is started from watchdog completion, before the
    # continuity collection itself has necessarily finished. Keep enough
    # bounded wait to cover the primary 25-minute job plus ten minutes of
    # runner/startup margin, while preserving time for exact mirror verification.
    assert bridge_wait_attempts * bridge_poll_seconds > (
        primary_timeout_minutes + 10
    ) * 60
    assert bridge_timeout_minutes * 60 > (
        bridge_wait_attempts * bridge_poll_seconds + 5 * 60
    )


def test_bridge_wait_still_fails_closed_after_the_reviewed_bound() -> None:
    bridge = BRIDGE.read_text(encoding="utf-8")

    assert "bounded 35-minute wait" in bridge
    assert (
        'raise SystemExit("continuity collection run did not complete within reviewed wait")'
        in bridge
    )
    assert "durability bridge only accepts prospective continuity dispatch runs" in bridge
