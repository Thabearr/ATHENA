from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

import domain.fotmob_data_matches_capture as capture_contract
import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as runner
import domain.fotmob_utc_native_expected_goals_fresh_holdout_collection_control as control


UTC = dt.timezone.utc


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    state = repo / control.CONTROL_ROOT_RELATIVE
    return repo, state


def _capture(
    tmp_path: Path,
    request_date: str,
    observed_at: dt.datetime,
) -> runner.CaptureEvidence:
    raw = json.dumps(
        {"leagues": [], "request_test_date": request_date},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    response = capture_contract.CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json",
        content_length=len(raw),
        body=raw,
        observed_at=observed_at,
        network_acquisition_performed=True,
    )
    manifest = capture_contract.build_data_matches_capture_manifest(
        response,
        request_date=request_date,
        timezone=control.REQUEST_TIMEZONE,
        ccode3=control.REQUEST_CCODE3,
    )
    directory = tmp_path / f"capture-{request_date}-{observed_at.hour}-{observed_at.minute}"
    directory.mkdir(parents=True, exist_ok=False)
    return runner.CaptureEvidence(directory, raw, manifest)


def test_activation_receipt_pins_merged_control_and_grants_no_downstream_authority() -> None:
    receipt = runner.activation_runner_receipt()
    assert receipt["reviewed_control"] == {
        "pr150_merge_sha": "50684a85cd528d491be812ed77d2c744855aba84",
        "pr150_merge_utc": "2026-08-18T04:55:12Z",
        "control_blob_sha": "60865e35a92e28bb0d4360223dea42b8933bb706",
    }
    assert receipt["runtime"]["network_requires_explicit_execute_flag"] is True
    assert receipt["runtime"]["settlement_precedes_prediction_construction_within_tick"] is True
    assert receipt["runtime"]["actual_capture_observed_at_authoritative"] is True
    assert receipt["runtime"]["nominal_schedule_time_is_observation_time"] is False
    assert receipt["runtime"]["scheduler_gap_backfill_authorized"] is False
    assert receipt["runtime"]["duplicate_committed_tick_network_replay_authorized"] is False
    assert all(value is False for value in receipt["safety"].values())


def test_state_root_is_exact_and_rejects_traversal(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path)
    assert runner.validate_state_root(
        Path(control.CONTROL_ROOT_RELATIVE), repository_root=repo
    ) == state
    with pytest.raises(runner.FreshHoldoutActivationError, match="exact reviewed"):
        runner.validate_state_root(Path(".cache/elsewhere"), repository_root=repo)
    with pytest.raises(runner.FreshHoldoutActivationError, match="traversal"):
        runner.validate_state_root(Path("../outside"), repository_root=repo)


def test_prestart_tick_commits_without_network_and_duplicate_does_not_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _state = _repo(tmp_path)
    monkeypatch.setattr(runner, "_ledger", lambda *_args, **_kwargs: object())
    calls: list[str] = []

    def forbidden_capture(request_date: str, *, repository_root: Path):
        calls.append(request_date)
        raise AssertionError("network must not be called pre-start")

    scheduled = dt.datetime(2026, 8, 18, 23, 37, tzinfo=UTC)
    receipt = runner.execute_collection_tick(
        scheduled_for=scheduled,
        bootstrap_projection_raw=b"synthetic-test-bootstrap",
        durable_release_tag="athena-fresh-holdout-evidence-2026-W34",
        durable_asset_name="success-20260818T233700Z-run-1.tar.gz",
        execute_live_network=False,
        state_root=Path(control.CONTROL_ROOT_RELATIVE),
        repository_root=repo,
        capture_one=forbidden_capture,
        clock=lambda: scheduled + dt.timedelta(minutes=1),
    )
    assert receipt["phase"] == control.ControlPhase.PRE_START.value
    assert receipt["network_request_count"] == 0
    assert calls == []

    duplicate = runner.execute_collection_tick(
        scheduled_for=scheduled,
        bootstrap_projection_raw=b"synthetic-test-bootstrap",
        durable_release_tag="athena-fresh-holdout-evidence-2026-W34",
        durable_asset_name="success-20260818T233700Z-run-2.tar.gz",
        execute_live_network=True,
        state_root=Path(control.CONTROL_ROOT_RELATIVE),
        repository_root=repo,
        capture_one=forbidden_capture,
        clock=lambda: scheduled + dt.timedelta(minutes=2),
    )
    assert duplicate["disposition"] == "ALREADY_COMMITTED_NO_NETWORK_REPLAY"
    assert duplicate["network_acquisition_performed"] is False
    assert calls == []


def test_active_tick_requires_explicit_live_network_authorization(
    tmp_path: Path,
) -> None:
    repo, _state = _repo(tmp_path)
    with pytest.raises(
        runner.FreshHoldoutActivationError,
        match="explicit live-network authorization",
    ):
        runner.execute_collection_tick(
            scheduled_for=dt.datetime(2026, 8, 19, 0, 7, tzinfo=UTC),
            bootstrap_projection_raw=b"x",
            durable_release_tag="athena-fresh-holdout-evidence-2026-W34",
            durable_asset_name="success-20260819T000700Z-run-1.tar.gz",
            execute_live_network=False,
            state_root=Path(control.CONTROL_ROOT_RELATIVE),
            repository_root=repo,
        )


def test_active_tick_requests_three_provider_dates_and_journals_actual_observed_at(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, state = _repo(tmp_path)
    monkeypatch.setattr(runner, "_ledger", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(runner, "_qualify", lambda _evidence: ())

    scheduled = dt.datetime(2026, 8, 19, 0, 7, tzinfo=UTC)
    calls: list[str] = []

    def capture_one(request_date: str, *, repository_root: Path):
        assert repository_root == repo
        calls.append(request_date)
        offset = {"20260818": 1, "20260819": 2, "20260820": 3}[request_date]
        return _capture(
            tmp_path,
            request_date,
            scheduled + dt.timedelta(minutes=offset),
        )

    receipt = runner.execute_collection_tick(
        scheduled_for=scheduled,
        bootstrap_projection_raw=b"test-bootstrap",
        durable_release_tag="athena-fresh-holdout-evidence-2026-W34",
        durable_asset_name="success-20260819T000700Z-run-42.tar.gz",
        execute_live_network=True,
        state_root=Path(control.CONTROL_ROOT_RELATIVE),
        repository_root=repo,
        capture_one=capture_one,
        clock=lambda: scheduled + dt.timedelta(minutes=4),
    )
    assert calls == ["20260818", "20260819", "20260820"]
    assert receipt["network_request_count"] == 3
    assert receipt["network_acquisition_performed"] is True
    rows = [
        json.loads(line)
        for line in (state / control.CAPTURE_INDEX_FILENAME).read_text().splitlines()
    ]
    assert [row["request_date"] for row in rows] == calls
    assert [row["observed_at"] for row in rows] == [
        "2026-08-19T00:08:00.000000Z",
        "2026-08-19T00:09:00.000000Z",
        "2026-08-19T00:10:00.000000Z",
    ]
    assert all(row["observed_at"] != "2026-08-19T00:07:00.000000Z" for row in rows)


def test_live_capture_cannot_backdate_nominal_slot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _state = _repo(tmp_path)
    monkeypatch.setattr(runner, "_ledger", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(runner, "_qualify", lambda _evidence: ())
    scheduled = dt.datetime(2026, 8, 19, 0, 7, tzinfo=UTC)

    def capture_one(request_date: str, *, repository_root: Path):
        return _capture(
            tmp_path,
            request_date,
            scheduled - dt.timedelta(seconds=1),
        )

    with pytest.raises(runner.FreshHoldoutActivationError, match="predates nominal"):
        runner.execute_collection_tick(
            scheduled_for=scheduled,
            bootstrap_projection_raw=b"x",
            durable_release_tag="athena-fresh-holdout-evidence-2026-W34",
            durable_asset_name="success-20260819T000700Z-run-1.tar.gz",
            execute_live_network=True,
            state_root=Path(control.CONTROL_ROOT_RELATIVE),
            repository_root=repo,
            capture_one=capture_one,
        )


def test_scheduler_gap_is_journaled_and_not_backfilled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, state = _repo(tmp_path)
    monkeypatch.setattr(runner, "_ledger", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(runner, "_qualify", lambda _evidence: ())
    counter = 0
    current_tick = [dt.datetime(2026, 8, 19, 0, 7, tzinfo=UTC)]

    def capture_one(request_date: str, *, repository_root: Path):
        nonlocal counter
        counter += 1
        return _capture(
            tmp_path,
            request_date,
            current_tick[0] + dt.timedelta(minutes=((counter - 1) % 3) + 1),
        )

    first = current_tick[0]
    runner.execute_collection_tick(
        scheduled_for=first,
        bootstrap_projection_raw=b"x",
        durable_release_tag="athena-fresh-holdout-evidence-2026-W34",
        durable_asset_name="success-20260819T000700Z-run-1.tar.gz",
        execute_live_network=True,
        state_root=Path(control.CONTROL_ROOT_RELATIVE),
        repository_root=repo,
        capture_one=capture_one,
        clock=lambda: first + dt.timedelta(minutes=5),
    )
    second = dt.datetime(2026, 8, 19, 1, 7, tzinfo=UTC)
    current_tick[0] = second
    runner.execute_collection_tick(
        scheduled_for=second,
        bootstrap_projection_raw=b"x",
        durable_release_tag="athena-fresh-holdout-evidence-2026-W34",
        durable_asset_name="success-20260819T010700Z-run-2.tar.gz",
        execute_live_network=True,
        state_root=Path(control.CONTROL_ROOT_RELATIVE),
        repository_root=repo,
        capture_one=capture_one,
        clock=lambda: second + dt.timedelta(minutes=5),
    )
    control_rows = [
        json.loads(line)
        for line in (state / control.CONTROL_JOURNAL_FILENAME).read_text().splitlines()
    ]
    gaps = [row for row in control_rows if row["event"] == "SCHEDULER_GAP_RANGE"]
    assert len(gaps) == 1
    assert gaps[0]["first_missing_tick_utc"] == "2026-08-19T00:37:00.000000Z"
    assert gaps[0]["last_missing_tick_utc"] == "2026-08-19T00:37:00.000000Z"
    assert gaps[0]["missing_tick_count"] == 1
    assert gaps[0]["backfill_authorized"] is False


def test_release_and_asset_identity_are_strict(tmp_path: Path) -> None:
    repo, _state = _repo(tmp_path)
    with pytest.raises(runner.FreshHoldoutActivationError, match="release tag"):
        runner.execute_collection_tick(
            scheduled_for=dt.datetime(2026, 8, 18, 23, 37, tzinfo=UTC),
            bootstrap_projection_raw=b"x",
            durable_release_tag="wrong",
            durable_asset_name="success-20260818T233700Z-run-1.tar.gz",
            execute_live_network=False,
            state_root=Path(control.CONTROL_ROOT_RELATIVE),
            repository_root=repo,
        )
    with pytest.raises(runner.FreshHoldoutActivationError, match="success asset"):
        runner.execute_collection_tick(
            scheduled_for=dt.datetime(2026, 8, 18, 23, 37, tzinfo=UTC),
            bootstrap_projection_raw=b"x",
            durable_release_tag="athena-fresh-holdout-evidence-2026-W34",
            durable_asset_name="failure-20260818T233700Z-run-1.tar.gz",
            execute_live_network=False,
            state_root=Path(control.CONTROL_ROOT_RELATIVE),
            repository_root=repo,
        )


def test_cli_and_workflow_are_present_and_schedule_is_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    cli = root / "scripts/run_fotmob_utc_native_xg_fresh_holdout_tick.py"
    workflow = root / ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
    assert cli.is_file()
    assert workflow.is_file()
    text = workflow.read_text(encoding="utf-8")
    assert "- cron: '7 * * * *'" in text
    assert "- cron: '37 * * * *'" in text
    assert "cancel-in-progress: false" in text
    assert "actions: read" in text
    assert "contents: write" in text
    assert "workflow_dispatch:" not in text
    assert "--execute-live-network" in text
    assert "athena-fresh-holdout-bootstrap-v1" in text
    assert "athena-fresh-holdout-evidence-" in text
    assert "success-" in text
    assert "failure-" in text
    assert "retention-days: 90" in text
