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


def test_bridge_is_one_shot_per_exact_main_and_fails_if_main_moves() -> None:
    text = _workflow()

    assert 'main_sha != os.environ["GITHUB_SHA"]' in text
    assert "event=workflow_dispatch&branch=main&per_page=100" in text
    assert 'select(.head_sha == \"${EXACT_MAIN_SHA}\")' in text
    assert 'if [ "${existing_count}" != "0" ]; then' in text
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
