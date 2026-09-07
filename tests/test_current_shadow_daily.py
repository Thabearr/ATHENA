from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from types import SimpleNamespace

import pytest

from domain import current_shadow_all_market_runner as runner
from scripts import execute_current_shadow_all_market_fresh_reprice_bound as bound
from scripts import execute_current_shadow_daily as daily


def test_target_size_accepts_frozen_upper_bound_50():
    args = daily.build_parser().parse_args(["--target-size", "50"])
    assert args.target_size == 50
    assert args.fixture_scope == daily.SCOPE_TODAY
    assert args.fixture_dates is None


@pytest.mark.parametrize("value", ["0", "51", "nope"])
def test_target_size_rejects_values_outside_frozen_contract(value):
    with pytest.raises(SystemExit):
        daily.build_parser().parse_args(["--target-size", value])


def test_explicit_dates_accept_non_contiguous_rolling_seven_day_window(monkeypatch):
    monkeypatch.setattr(
        runner,
        "_now",
        lambda: datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc),
    )
    args = daily.build_parser().parse_args(
        [
            "--target-size",
            "15",
            "--fixture-dates",
            "20260910,20260907,20260909",
        ]
    )
    assert args.fixture_dates == ("20260907", "20260909", "20260910")


@pytest.mark.parametrize(
    "value",
    [
        "20260907,20260907",
        "20260905",
        "20260913",
        "2026-09-07",
        "20260230",
        "20260907,",
    ],
)
def test_explicit_dates_fail_closed_outside_exact_rolling_contract(monkeypatch, value):
    monkeypatch.setattr(
        runner,
        "_now",
        lambda: datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc),
    )
    with pytest.raises(SystemExit):
        daily.build_parser().parse_args(
            ["--target-size", "15", "--fixture-dates", value]
        )


def test_today_scope_sets_one_day_only_and_restores_runner(monkeypatch):
    original = runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT
    original_issuer = runner._issue_current_fixture_sources
    seen = {}

    def fake_worker(args):
        seen["day_count"] = runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT
        seen["target_size"] = args.target_size
        seen["issuer"] = runner._issue_current_fixture_sources
        return 17

    monkeypatch.setattr(bound, "_execute_worker", fake_worker)
    args = daily.build_parser().parse_args(
        ["--target-size", "20", "--fixture-scope", "today"]
    )

    assert daily._execute_worker(args) == 17
    assert seen == {
        "day_count": 1,
        "target_size": 20,
        "issuer": original_issuer,
    }
    assert runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT == original
    assert runner._issue_current_fixture_sources is original_issuer


def test_three_day_scope_preserves_existing_prf_horizon_and_activates_all_market_worker(monkeypatch):
    original = runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT
    seen = {}
    monkeypatch.delenv(daily.all_market_cli.WORKER_ENV, raising=False)

    def fake_worker(_args):
        seen["day_count"] = runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT
        seen["all_market_worker"] = os.environ.get(daily.all_market_cli.WORKER_ENV)
        return 0

    monkeypatch.setattr(bound, "_execute_worker", fake_worker)
    args = daily.build_parser().parse_args(
        ["--target-size", "20", "--fixture-scope", "three-day"]
    )

    assert daily._execute_worker(args) == 0
    assert seen["day_count"] == 3
    assert seen["all_market_worker"] == "1"
    assert runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT == original
    assert daily.all_market_cli.WORKER_ENV not in os.environ


def test_exact_dates_issue_only_requested_dates_and_restore_runner(monkeypatch, tmp_path):
    original_count = runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT
    original_issuer = runner._issue_current_fixture_sources
    monkeypatch.setattr(
        runner,
        "_now",
        lambda: datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc),
    )
    calls = []

    def issue(**kwargs):
        calls.append(kwargs["request_date"])
        return SimpleNamespace(request_date=kwargs["request_date"])

    monkeypatch.setattr(
        runner.current_fotmob_source,
        "issue_current_shadow_fotmob_reviewed_source",
        issue,
    )

    def fake_worker(_args):
        seen, attempted = runner._issue_current_fixture_sources(
            repository_root=tmp_path
        )
        assert attempted == ("20260907", "20260909", "20260910")
        assert [date for _execution, date in seen] == list(attempted)
        assert runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT == 3
        return 0

    monkeypatch.setattr(bound, "_execute_worker", fake_worker)
    args = daily.build_parser().parse_args(
        [
            "--target-size",
            "15",
            "--fixture-dates",
            "20260910,20260907,20260909",
        ]
    )
    assert daily._execute_worker(args) == 0
    assert calls == ["20260907", "20260909", "20260910"]
    assert runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT == original_count
    assert runner._issue_current_fixture_sources is original_issuer


def test_scope_and_all_market_worker_marker_restore_after_worker_failure(monkeypatch):
    original = runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT
    original_issuer = runner._issue_current_fixture_sources
    monkeypatch.setenv(daily.all_market_cli.WORKER_ENV, "preexisting")

    def boom(_args):
        assert runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT == 1
        assert os.environ[daily.all_market_cli.WORKER_ENV] == "1"
        raise RuntimeError("failed")

    monkeypatch.setattr(bound, "_execute_worker", boom)
    args = daily.build_parser().parse_args(["--target-size", "20"])

    with pytest.raises(RuntimeError, match="failed"):
        daily._execute_worker(args)
    assert runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT == original
    assert runner._issue_current_fixture_sources is original_issuer
    assert os.environ[daily.all_market_cli.WORKER_ENV] == "preexisting"


def test_source_adapter_failure_finalizes_durable_source_incomplete(monkeypatch, tmp_path):
    original = runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT
    exact_sha = "c" * 40
    monkeypatch.setattr(runner, "_git_head", lambda _root: exact_sha)
    runner._checkpoint_stage(
        output_dir=tmp_path,
        stage=runner.STAGE_CURRENT_FOTMOB_SOURCE,
        exact_commit_sha=exact_sha,
        target_size=15,
    )
    provisional = runner._receipt(
        status=runner.STATUS_SOURCE_INCOMPLETE,
        exact_commit_sha=exact_sha,
        target_size=15,
        sources=None,
        portfolio=None,
        share_receipt=None,
        reasons=("SOURCE_CHAIN_PENDING:STARTED",),
    )
    runner._write(tmp_path / runner.RUN_RECEIPT_FILENAME, provisional.to_dict())

    def source_adapter_failure(_args):
        try:
            raise ValueError("status.halfs has keys outside reviewed allowlist")
        except ValueError as inner:
            raise daily.CurrentFotMobFixtureCandidateAdapterError(
                "reviewed PR87/PR89 additive schema assessment failed"
            ) from inner

    monkeypatch.setattr(bound, "_execute_worker", source_adapter_failure)
    args = daily.build_parser().parse_args(
        [
            "--target-size",
            "15",
            "--fixture-scope",
            "three-day",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert daily._execute_worker(args) == 0
    payload = json.loads((tmp_path / runner.RUN_RECEIPT_FILENAME).read_text(encoding="utf-8"))
    assert payload["status"] == runner.STATUS_SOURCE_INCOMPLETE
    assert payload["reasons"] == [
        "SOURCE_CHAIN_FAILED:CurrentFotMobFixtureCandidateAdapterError:"
        "reviewed PR87/PR89 additive schema assessment failed<-ValueError:"
        "status.halfs has keys outside reviewed allowlist"
    ]
    assert payload["reasons"] != ["SOURCE_CHAIN_PENDING:STARTED"]
    assert payload["source_summary"] == {
        "source_failure_stage": runner.STAGE_CURRENT_FOTMOB_SOURCE,
        "source_failure_type": "CurrentFotMobFixtureCandidateAdapterError",
        "wager_placed": False,
    }
    assert payload["shareCode"] is None
    assert payload["wager_placed"] is False
    assert runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT == original


def test_parent_process_passes_scope_and_uses_prf_supervisor(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.delenv(daily.WORKER_ENV, raising=False)

    def fake_run(command, *, env, check, timeout):
        seen.update(command=command, env=env, check=check, timeout=timeout)
        return SimpleNamespace(returncode=23)

    monkeypatch.setattr(daily.subprocess, "run", fake_run)

    result = daily.main(
        [
            "--target-size",
            "50",
            "--fixture-scope",
            "today",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert result == 23
    assert seen["check"] is False
    assert seen["timeout"] == bound._supervisor_timeout_seconds()
    assert seen["env"][daily.WORKER_ENV] == "1"
    assert seen["command"][0] == daily.sys.executable
    assert seen["command"][1:3] == ["-m", daily.WORKER_MODULE]
    assert "--fixture-scope" in seen["command"]
    assert "today" in seen["command"]
    assert "50" in seen["command"]


def test_parent_process_passes_exact_fixture_dates(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.delenv(daily.WORKER_ENV, raising=False)
    monkeypatch.setattr(
        runner,
        "_now",
        lambda: datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc),
    )

    def fake_run(command, *, env, check, timeout):
        seen.update(command=command, env=env, check=check, timeout=timeout)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(daily.subprocess, "run", fake_run)
    assert daily.main(
        [
            "--target-size",
            "15",
            "--fixture-dates",
            "20260909,20260907",
            "--output-dir",
            str(tmp_path),
        ]
    ) == 0
    assert "--fixture-dates" in seen["command"]
    assert "20260907,20260909" in seen["command"]
    assert "--fixture-scope" not in seen["command"]
