from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from domain import current_shadow_all_market_runner as runner
from domain import current_shadow_fixture_date_request as fixture_dates
from domain import current_shadow_fixture_identity_run199_overlay as run199_identity
from scripts import execute_current_shadow_request as request_cli
from scripts import execute_current_shadow_daily as daily


UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def _args(tmp_path: Path, dates=None):
    return argparse.Namespace(
        target_size=15,
        fixture_scope=daily.SCOPE_TODAY,
        fixture_dates=dates,
        output_dir=tmp_path,
    )


def test_selected_source_issuer_calls_only_requested_non_contiguous_dates(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "_now", lambda: NOW)
    calls = []
    values = {
        "20260908": SimpleNamespace(name="tue"),
        "20260910": SimpleNamespace(name="thu"),
    }

    def issue(**kwargs):
        request_date = kwargs["request_date"]
        calls.append(request_date)
        return values[request_date]

    monkeypatch.setattr(
        runner.current_fotmob_source,
        "issue_current_shadow_fotmob_reviewed_source",
        issue,
    )
    issuer = request_cli._selected_source_issuer(("20260910", "20260908"))
    sources, attempted = issuer(repository_root=tmp_path)
    assert attempted == ("20260908", "20260910")
    assert calls == ["20260908", "20260910"]
    assert sources == ((values["20260908"], "20260908"), (values["20260910"], "20260910"))


def test_selected_source_issuer_skips_only_exact_no_fixture_status(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "_now", lambda: NOW)
    expected = SimpleNamespace()

    def issue(**kwargs):
        if kwargs["request_date"] == "20260908":
            raise runner.current_fotmob_source.CurrentFotMobReviewedSourceError(
                runner.current_fotmob_source.STATUS_NO_FIXTURES
            )
        return expected

    monkeypatch.setattr(
        runner.current_fotmob_source,
        "issue_current_shadow_fotmob_reviewed_source",
        issue,
    )
    issuer = request_cli._selected_source_issuer(("20260908", "20260910"))
    sources, attempted = issuer(repository_root=tmp_path)
    assert attempted == ("20260908", "20260910")
    assert sources == ((expected, "20260910"),)


def test_selected_source_issuer_does_not_step_over_other_source_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "_now", lambda: NOW)

    def issue(**_kwargs):
        raise runner.current_fotmob_source.CurrentFotMobReviewedSourceError("schema drift")

    monkeypatch.setattr(
        runner.current_fotmob_source,
        "issue_current_shadow_fotmob_reviewed_source",
        issue,
    )
    issuer = request_cli._selected_source_issuer(("20260908",))
    with pytest.raises(
        runner.current_fotmob_source.CurrentFotMobReviewedSourceError,
        match="schema drift",
    ):
        issuer(repository_root=tmp_path)


def test_explicit_worker_binds_exact_count_and_restores_all_compatibility(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "_now", lambda: NOW)
    original_issuer = runner._issue_current_fixture_sources
    original_count = daily.SCOPE_DAY_COUNT[daily.SCOPE_TODAY]
    proxy = request_cli.reconciliation.legacy.reviewed
    before = dict(getattr(proxy, "__dict__", {}))
    seen = {}

    def execute(args):
        seen["count"] = runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT
        seen["issuer"] = runner._issue_current_fixture_sources
        seen["match"] = proxy._match_event
        seen["inventory"] = proxy._detail_inventory_from_directory
        return 17

    monkeypatch.setattr(daily, "_execute_worker", execute)
    args = _args(tmp_path, ("20260908", "20260909", "20260910"))
    assert request_cli._execute_worker(args) == 17
    assert seen["count"] == 3
    assert seen["issuer"] is not original_issuer
    assert seen["match"] is run199_identity.match_event
    assert seen["inventory"] is request_cli._detail_inventory
    assert daily.SCOPE_DAY_COUNT[daily.SCOPE_TODAY] == original_count
    assert runner._issue_current_fixture_sources is original_issuer
    assert dict(getattr(proxy, "__dict__", {})) == before

    policy = json.loads((tmp_path / request_cli.REQUEST_POLICY_FILENAME).read_text())
    assert policy["fixture_dates"] == ["20260908", "20260909", "20260910"]
    assert policy["run199_identity_policy_id"] == run199_identity.POLICY_ID
    assert policy["wager_placed"] is False
    assert policy["authority"]["bet"] is False


def test_outer_supervisor_forwards_exact_dates_to_worker(monkeypatch, tmp_path):
    captured = {}

    def run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0)

    monkeypatch.delenv(request_cli.WORKER_ENV, raising=False)
    monkeypatch.setattr(request_cli.subprocess, "run", run)
    monkeypatch.setattr(request_cli.bound, "_supervisor_timeout_seconds", lambda: 123)
    rc = request_cli.main(
        [
            "--target-size", "15",
            "--fixture-dates", "20260908,20260910",
            "--output-dir", str(tmp_path),
        ]
    )
    assert rc == 0
    command = captured["command"]
    assert command[:3] == [request_cli.sys.executable, "-m", request_cli.WORKER_MODULE]
    index = command.index("--fixture-dates")
    assert command[index + 1] == "20260908,20260910"
    assert captured["env"][request_cli.WORKER_ENV] == "1"


def test_fixture_date_argument_rejects_bad_format():
    with pytest.raises(argparse.ArgumentTypeError):
        request_cli._fixture_dates("2026-09-08")


def test_request_policy_date_contract_is_same_module_used_by_cli():
    assert request_cli.fixture_dates.POLICY_ID == fixture_dates.POLICY_ID
