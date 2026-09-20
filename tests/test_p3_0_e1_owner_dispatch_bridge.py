from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "p3-0-e1-owner-dispatch-bridge.yml"
)


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_bridge_is_issue_comment_only_and_owner_bound_to_master_issue() -> None:
    text = _workflow()

    assert "issue_comment:" in text
    assert "types: [created]" in text
    assert "workflow_dispatch:" not in text
    assert "schedule:" not in text
    assert "push:" not in text
    assert "github.event.issue.number == 337" in text
    assert "github.event.comment.user.login == github.repository_owner" in text
    assert "github.event.comment.body == '/athena-run-p3-e1'" in text
    assert 'if issue.get("number") != 337:' in text
    assert 'comment.get("body") != command' in text


def test_bridge_requires_unique_exact_owner_authorization_comment() -> None:
    text = _workflow()

    assert "issues: read" in text
    assert "issues/337/comments?per_page=100&page={page}" in text
    assert 'row.get("user", {}).get("login") == owner' in text
    assert 'row.get("body") == command' in text
    assert "if len(exact_authorizations) != 1:" in text
    assert 'exact_authorizations[0].get("id") != comment["id"]' in text
    assert "authorization pagination exceeded bound" in text


def test_bridge_derives_exact_seven_day_utc_window_and_cap_50() -> None:
    text = _workflow()

    assert "dt.datetime.now(dt.timezone.utc).date()" in text
    assert "for offset in range(7)" in text
    assert 'strftime("%Y%m%d")' in text
    assert 'handle.write("fixture_cap=50\\n")' in text
    assert "fixture_cap=50" in text


def test_bridge_enforces_bounded_corpus_accumulation_rate_limits_and_cooldown() -> None:
    text = _workflow()

    assert 'main_sha != os.environ["GITHUB_SHA"]' in text
    assert "PAGE_SIZE = 100" in text
    assert "MAX_WORKFLOW_DISPATCH_HISTORY_PAGES = 100" in text
    assert "COOLDOWN_SECONDS = 90 * 60" in text
    assert "MAX_RUNS_24H = 8" in text
    assert "ROLLING_WINDOW_SECONDS = 24 * 3600" in text
    assert "for page in range(1, MAX_WORKFLOW_DISPATCH_HISTORY_PAGES + 1):" in text
    assert "event=workflow_dispatch&branch=main&per_page={PAGE_SIZE}&page={page}" in text
    assert "if type(response) is not dict:" in text
    assert "if type(workflow_runs) is not list:" in text
    assert 'if type(run) is not dict:' in text
    assert 'if type(status) is not str:' in text
    assert 'if type(created_at_raw) is not str:' in text
    assert "if len(workflow_runs) < PAGE_SIZE:" in text
    assert "pagination exceeded bound before exhaustion" in text
    assert 'active_runs = [r for r in all_runs if r[1] in ("in_progress", "queued", "waiting", "requested")]' in text
    assert "if elapsed < COOLDOWN_SECONDS:" in text
    assert "if len(runs_24h) >= MAX_RUNS_24H:" in text
    assert 'if [ "${live_main_sha}" != "${EXACT_MAIN_SHA}" ]; then' in text



def test_bridge_dispatches_only_reviewed_p3_capture_workflow() -> None:
    text = _workflow()

    assert "actions: write" in text
    assert "contents: read" in text
    assert "gh workflow run p3-0-comparison-evidence-capture.yml" in text
    assert '--repo "${GITHUB_REPOSITORY}"' in text
    assert "--ref main" in text
    assert '-f fixture_dates="${ATHENA_P3_FIXTURE_DATES}"' in text
    assert '-f fixture_cap="${ATHENA_P3_FIXTURE_CAP}"' in text

    for forbidden in (
        "current-shadow-all-market.yml",
        "fotmob-utc-native-xg-fresh-holdout.yml",
        "current-shadow-sportybet-source-diagnostic.yml",
        "send_current_shadow_email",
        "sportybet_share_code",
        "wallet",
        "staking",
        "wager",
    ):
        assert forbidden not in text


import datetime as dt
import pytest


def _evaluate_bounded_accumulation_rules(
    workflow_runs: list[dict],
    now: dt.datetime,
    cooldown_seconds: int = 90 * 60,
    max_runs_24h: int = 8,
    rolling_window_seconds: int = 24 * 3600,
) -> None:
    all_runs = []
    for run in workflow_runs:
        if type(run) is not dict:
            raise ValueError("bounded-dispatch run is malformed")
        status = run.get("status")
        if type(status) is not str:
            raise ValueError("bounded-dispatch run status is malformed")
        created_at_raw = run.get("run_started_at") or run.get("created_at")
        if type(created_at_raw) is not str:
            raise ValueError("bounded-dispatch run timestamp is malformed")
        try:
            run_time = dt.datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"bounded-dispatch run timestamp unparseable: {exc}")
        all_runs.append((run.get("id"), status, run_time))

    active_runs = [r for r in all_runs if r[1] in ("in_progress", "queued", "waiting", "requested")]
    if active_runs:
        raise ValueError(
            f"P3.0-E1 capture run ({active_runs[0][0]}) is currently active with status '{active_runs[0][1]}'."
        )

    if all_runs:
        last_run_id, _, last_run_time = all_runs[0]
        elapsed = (now - last_run_time).total_seconds()
        if elapsed < cooldown_seconds:
            raise ValueError(
                f"P3.0-E1 capture cooldown violated: last run ({last_run_id}) started {elapsed:.0f}s ago; "
                f"minimum interval is {cooldown_seconds}s (90 minutes)."
            )

    runs_24h = [r for r in all_runs if (now - r[2]).total_seconds() <= rolling_window_seconds]
    if len(runs_24h) >= max_runs_24h:
        raise ValueError(
            f"P3.0-E1 rolling 24-hour rate limit exceeded: {len(runs_24h)} run(s) in last 24 hours; "
            f"maximum allowed is {max_runs_24h}."
        )


def test_bounded_accumulation_rejects_active_run() -> None:
    now = dt.datetime(2026, 9, 20, 12, 0, tzinfo=dt.timezone.utc)
    runs = [
        {"id": 1, "status": "in_progress", "created_at": "2026-09-20T10:00:00Z"},
    ]
    with pytest.raises(ValueError, match="is currently active with status 'in_progress'"):
        _evaluate_bounded_accumulation_rules(runs, now)

    runs_queued = [
        {"id": 2, "status": "queued", "created_at": "2026-09-20T10:00:00Z"},
    ]
    with pytest.raises(ValueError, match="is currently active with status 'queued'"):
        _evaluate_bounded_accumulation_rules(runs_queued, now)


def test_bounded_accumulation_rejects_cooldown_violation() -> None:
    now = dt.datetime(2026, 9, 20, 10, 0, tzinfo=dt.timezone.utc)
    # Run was 45 minutes ago (< 90 minutes)
    runs = [
        {"id": 10, "status": "completed", "created_at": "2026-09-20T09:15:00Z"},
    ]
    with pytest.raises(ValueError, match="P3.0-E1 capture cooldown violated"):
        _evaluate_bounded_accumulation_rules(runs, now)


def test_bounded_accumulation_rejects_rolling_24h_limit() -> None:
    now = dt.datetime(2026, 9, 20, 20, 0, tzinfo=dt.timezone.utc)
    # 8 runs spaced every 100 minutes within last 24h
    runs = [
        {
            "id": 100 + i,
            "status": "completed",
            "created_at": (now - dt.timedelta(minutes=100 * (i + 1))).isoformat(),
        }
        for i in range(8)
    ]
    with pytest.raises(ValueError, match="P3.0-E1 rolling 24-hour rate limit exceeded"):
        _evaluate_bounded_accumulation_rules(runs, now)


def test_bounded_accumulation_accepts_valid_cooldown_and_limit() -> None:
    now = dt.datetime(2026, 9, 20, 12, 0, tzinfo=dt.timezone.utc)
    # Run was 95 minutes ago (> 90 min)
    runs = [
        {"id": 20, "status": "completed", "created_at": "2026-09-20T10:25:00Z"},
        {"id": 19, "status": "completed", "created_at": "2026-09-20T08:00:00Z"},
    ]
    # Should not raise
    _evaluate_bounded_accumulation_rules(runs, now)


def test_bounded_accumulation_fails_closed_on_malformed_run() -> None:
    now = dt.datetime(2026, 9, 20, 12, 0, tzinfo=dt.timezone.utc)
    with pytest.raises(ValueError, match="malformed"):
        _evaluate_bounded_accumulation_rules(["not-a-dict"], now)  # type: ignore[list-item]

    with pytest.raises(ValueError, match="malformed"):
        _evaluate_bounded_accumulation_rules([{"id": 1, "status": 123}], now)

    with pytest.raises(ValueError, match="malformed"):
        _evaluate_bounded_accumulation_rules([{"id": 1, "status": "completed", "created_at": 123}], now)
