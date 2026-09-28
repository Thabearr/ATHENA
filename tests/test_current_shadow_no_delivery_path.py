from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import subprocess
from types import MappingProxyType, SimpleNamespace
import urllib.request

import pytest

from domain import current_shadow_all_market_runner as runner
from scripts import execute_current_shadow_request as request_cli
from scripts import execute_current_shadow_daily as daily_cli
from scripts import execute_current_shadow_all_market as all_market_cli
from scripts import execute_current_shadow_all_market_summary_reuse as summary_cli
from scripts import execute_current_shadow_all_market_fresh_reprice as fresh_cli
from scripts import execute_current_shadow_all_market_fresh_reprice_bound as bound_cli


NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
COMMIT = "a" * 40


def _source_bundle():
    return runner.CurrentShadowRunnerSourceBundle(
        router_inputs=(object(),),
        reviewed_fixture_count=1,
        reconciled_fixture_count=1,
        provider_event_count=1,
        priced_fixture_count=1,
        router_selected_count=1,
        router_no_bet_count=0,
        source_summary=MappingProxyType({"offline_fixture": True, "wager_placed": False}),
    )


def _portfolio(*, target_size: int, selected: int):
    legs = tuple(
        {
            "leg_id": f"LEG-{index + 1}",
            "fixture_identity": f"FOTMOB:{index + 1}",
            "provider_event_id": f"sr:match:{index + 1}",
            "market_id": "MATCH_RESULT",
            "outcome_id": "HOME",
            "decimal_odds": 1.75,
            "quote_identity_sha256": "b" * 64,
        }
        for index in range(selected)
    )
    reserve = ({"leg_id": "RESERVE-1", "reserve_reasons": ["TEAM_CAP:X"]},)
    return SimpleNamespace(
        selected_legs=legs,
        reserve_legs=reserve,
        shortfall=target_size - selected,
        canonical_sha256="c" * 64,
        to_dict=lambda: {
            "dataset_name": "athena-current-shadow-all-market-portfolio-v2",
            "requested_target_size": target_size,
            "selected_leg_count": selected,
            "selected_legs": list(legs),
            "reserve_legs": list(reserve),
            "shortfall": target_size - selected,
            "wager_placed": False,
        },
    )


def _install_offline_terminal_fixtures(monkeypatch, *, target_size: int, selected: int):
    monkeypatch.setattr(runner, "_git_head", lambda _root: COMMIT)
    monkeypatch.setattr(runner, "_expected_lineage_main_sha", lambda: "d" * 40)
    monkeypatch.setattr(runner, "_now", lambda: NOW)
    monkeypatch.setattr(runner, "_acquire_router_inputs", lambda **_kwargs: _source_bundle())
    observed_stages = []
    original_checkpoint = runner._checkpoint_stage

    def record_checkpoint(**kwargs):
        observed_stages.append(kwargs["stage"])
        return original_checkpoint(**kwargs)

    monkeypatch.setattr(runner, "_checkpoint_stage", record_checkpoint)

    # The real AUTH-01C wrapper composition chooses the fresh-reprice binding.
    # For this offline terminal-branch proof, use the already-reviewed source
    # bundle as the deterministic post-refresh fixture.
    from domain import current_shadow_fresh_reprice_runtime as fresh_runtime

    monkeypatch.setattr(fresh_runtime, "refresh_selected_inputs", lambda sources, **_kwargs: sources)
    selected_portfolio = _portfolio(target_size=target_size, selected=selected)
    monkeypatch.setattr(
        runner.portfolio_module,
        "optimize_shadow_portfolio",
        lambda *_args, **_kwargs: selected_portfolio,
    )
    share_calls = []

    def forbidden_share(**_kwargs):
        share_calls.append("called")
        raise AssertionError("no-delivery execution reached share-code transport")

    monkeypatch.setattr(
        runner.share_module,
        "create_verified_shadow_all_market_share_code",
        forbidden_share,
    )
    provider_calls = []
    monkeypatch.setattr(
        runner.current_fotmob_source,
        "issue_current_shadow_fotmob_reviewed_source",
        lambda **_kwargs: provider_calls.append("called"),
    )
    return selected_portfolio, share_calls, provider_calls, observed_stages


def test_real_request_to_fresh_wrapper_composition_reaches_runner_no_delivery_terminal(
    monkeypatch, tmp_path, capsys
):
    target_size = 2
    selected = 1
    portfolio, share_calls, provider_calls, observed_stages = _install_offline_terminal_fixtures(
        monkeypatch,
        target_size=target_size,
        selected=selected,
    )
    external_calls = []

    def deny_network(*_args, **_kwargs):
        external_calls.append("network")
        raise AssertionError("offline no-delivery proof attempted network access")

    worker_processes = []
    original_subprocess_run = subprocess.run

    def deny_runtime_worker(command, *args, **kwargs):
        command_parts = tuple(str(item) for item in command)
        if "-m" in command_parts and any(
            item.startswith("scripts.execute_current_shadow_") for item in command_parts
        ):
            worker_processes.append(command_parts)
            raise AssertionError("wrapper started a Current Shadow worker process")
        return original_subprocess_run(command, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(urllib.request, "urlopen", deny_network)
    monkeypatch.setattr(subprocess, "run", deny_runtime_worker)

    args = request_cli.build_parser().parse_args(
        ["--target-size", str(target_size), "--create-share-code", "false", "--output-dir", str(tmp_path)]
    )
    assert request_cli._execute_worker(args) == 0
    capsys.readouterr()

    policy = json.loads((tmp_path / request_cli.REQUEST_POLICY_FILENAME).read_text(encoding="utf-8"))
    receipt = json.loads((tmp_path / runner.RUN_RECEIPT_FILENAME).read_text(encoding="utf-8"))
    assert policy["create_share_code"] is False
    assert policy["authority"]["research_anonymous_share_code_generation"] is False
    assert policy["authority"]["provider_create_reload_verification"] is False
    assert receipt["create_share_code"] is False
    assert receipt["status"] == runner.STATUS_PORTFOLIO_READY_WITH_SHORTFALL
    assert receipt["selected_leg_count"] == len(portfolio.selected_legs) == selected
    assert receipt["reserve_leg_count"] == len(portfolio.reserve_legs) == 1
    assert receipt["shortfall"] == target_size - selected == 1
    assert receipt["portfolio"]["selected_legs"] == list(portfolio.selected_legs)
    assert receipt["share_code_receipt"] is None
    assert receipt["shareCode"] is None
    assert receipt["shareURL"] is None
    assert receipt["authority"]["research_anonymous_share_code_generation"] is False
    assert receipt["authority"]["provider_create_reload_verification"] is False
    assert runner.STAGE_SHARE_CODE_CREATE_RELOAD not in observed_stages
    assert share_calls == []
    assert provider_calls == []
    assert external_calls == []
    assert worker_processes == []


@pytest.mark.parametrize(
    "module",
    [request_cli, daily_cli, all_market_cli, summary_cli, fresh_cli, bound_cli],
)
@pytest.mark.parametrize(("intent", "serialized"), [(False, "false"), (True, "true")])
def test_every_cli_supervisor_relaunch_serializes_exact_delivery_bool(
    monkeypatch, tmp_path, module, intent, serialized
):
    captured = {}

    def offline_child(command, **_kwargs):
        captured["command"] = list(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.delenv(request_cli.WORKER_ENV, raising=False)
    monkeypatch.delenv(daily_cli.WORKER_ENV, raising=False)
    monkeypatch.delenv(all_market_cli.WORKER_ENV, raising=False)
    monkeypatch.setattr(module.subprocess, "run", offline_child)
    if module is request_cli:
        monkeypatch.setattr(module.bound, "_supervisor_timeout_seconds", lambda: 30)
    elif module is daily_cli:
        monkeypatch.setattr(module.bound, "_supervisor_timeout_seconds", lambda: 30)
    elif module is bound_cli:
        monkeypatch.setattr(module, "_supervisor_timeout_seconds", lambda: 30)

    argv = [
        "--target-size",
        "2",
        "--output-dir",
        str(tmp_path),
        "--create-share-code",
        serialized,
    ]
    assert module.main(argv) == 0
    command = captured["command"]
    index = command.index("--create-share-code")
    assert command[index + 1] == serialized


@pytest.mark.parametrize(
    "module",
    [request_cli, daily_cli, all_market_cli, summary_cli, fresh_cli, bound_cli],
)
def test_every_cli_timeout_finalizer_receives_exact_false_intent(
    monkeypatch, tmp_path, capsys, module
):
    def timeout(command, timeout, **_kwargs):
        raise subprocess.TimeoutExpired(command, timeout)

    forwarded = []

    def write_timeout(*, target_size, output_dir, create_share_code=True):
        forwarded.append((target_size, output_dir, create_share_code))
        return SimpleNamespace(to_dict=lambda: {"create_share_code": create_share_code})

    def bound_timeout(*, target_size, output_dir, create_share_code=True):
        forwarded.append((target_size, output_dir, create_share_code))
        return SimpleNamespace(to_dict=lambda: {"create_share_code": create_share_code})

    monkeypatch.delenv(request_cli.WORKER_ENV, raising=False)
    monkeypatch.delenv(daily_cli.WORKER_ENV, raising=False)
    monkeypatch.delenv(all_market_cli.WORKER_ENV, raising=False)
    monkeypatch.setattr(module.subprocess, "run", timeout)
    monkeypatch.setattr(runner, "write_current_shadow_timeout_receipt", write_timeout)
    monkeypatch.setattr(bound_cli, "_write_timeout_receipt", bound_timeout)
    if module is request_cli:
        monkeypatch.setattr(module.bound, "_supervisor_timeout_seconds", lambda: 30)
    elif module is daily_cli:
        monkeypatch.setattr(module.bound, "_supervisor_timeout_seconds", lambda: 30)
    elif module is bound_cli:
        monkeypatch.setattr(module, "_supervisor_timeout_seconds", lambda: 30)

    argv = ["--target-size", "2", "--output-dir", str(tmp_path), "--create-share-code", "false"]
    assert module.main(argv) == 0
    capsys.readouterr()
    assert forwarded == [(2, tmp_path, False)]


def test_each_cli_uses_explicit_legacy_delivery_default_but_rejects_noncanonical_values():
    for module in (request_cli, daily_cli, all_market_cli):
        assert module.build_parser().parse_args(["--target-size", "2"]).create_share_code is True
    assert runner.LEGACY_CREATE_SHARE_CODE_DEFAULT is True
    for value in ("False", "TRUE", "0", "1", "yes", "no", "", " false", "true "):
        with pytest.raises(ValueError):
            runner.parse_create_share_code_text(value)
