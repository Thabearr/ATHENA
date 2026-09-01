from __future__ import annotations

from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import subprocess
from types import MappingProxyType, SimpleNamespace

import pytest

from domain import current_shadow_all_market_runner as runner
from scripts import execute_current_shadow_all_market as cli

UTC = timezone.utc
NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
SHA = "a" * 40


def _sources(*, reconciled: int, selected: int, no_bet: int, router_inputs=()):
    return runner.CurrentShadowRunnerSourceBundle(
        router_inputs=tuple(router_inputs),
        reviewed_fixture_count=max(reconciled, 1),
        reconciled_fixture_count=reconciled,
        provider_event_count=max(reconciled, 1),
        priced_fixture_count=selected + no_bet,
        router_selected_count=selected,
        router_no_bet_count=no_bet,
        source_summary=MappingProxyType({"source": "test", "wager_placed": False}),
    )


def _portfolio(*, target: int, selected: int, reserve: int = 0):
    value = SimpleNamespace()
    value.selected_legs = tuple(SimpleNamespace(leg_id=str(i)) for i in range(selected))
    value.reserve_legs = tuple(SimpleNamespace(reserve_reasons=("TEAM_CAP:X",)) for _ in range(reserve))
    value.shortfall = target - selected
    value.canonical_sha256 = "b" * 64
    value.to_dict = lambda: {
        "requested_target_size": target,
        "selected_leg_count": selected,
        "shortfall": target - selected,
        "wager_placed": False,
    }
    return value


def _share(status: str, *, code: str | None = None, url: str | None = None, reasons=()):
    value = SimpleNamespace()
    value.status = status
    value.share_code = code
    value.share_url = url
    value.reasons = tuple(reasons)
    value.to_dict = lambda: {
        "status": status,
        "shareCode": code,
        "shareURL": url,
        "reasons": list(reasons),
        "wager_placed": False,
    }
    return value


def _install_common(monkeypatch):
    monkeypatch.setattr(runner, "_git_head", lambda _root: SHA)
    monkeypatch.setattr(runner, "_expected_lineage_main_sha", lambda: "b" * 40)
    monkeypatch.setattr(runner, "_now", lambda: NOW)


def _receipt_payload(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _fake_terminal_receipt():
    return SimpleNamespace(to_dict=lambda: {"status": runner.STATUS_SOURCE_INCOMPLETE,
                                            "wager_placed": False})


def test_public_runner_and_cli_accept_no_provider_native_ids_odds_or_preselected_legs():
    params = inspect.signature(runner.execute_current_shadow_all_market).parameters
    assert set(params) == {"target_size", "output_dir"}
    parser = cli.build_parser()
    option_strings = {option for action in parser._actions for option in action.option_strings}
    assert "--target-size" in option_strings
    assert "--output-dir" in option_strings
    forbidden = {
        "--event-id", "--provider-market-id", "--provider-outcome-id", "--odds",
        "--probability", "--xg", "--preselected-leg", "--fixture-list",
    }
    assert forbidden.isdisjoint(option_strings)


def test_provisional_receipt_exists_before_source_work(monkeypatch, tmp_path):
    _install_common(monkeypatch)

    def acquire(**_kwargs):
        payload = _receipt_payload(tmp_path / runner.RUN_RECEIPT_FILENAME)
        assert payload["status"] == runner.STATUS_SOURCE_INCOMPLETE
        assert payload["reasons"] == ["SOURCE_CHAIN_PENDING:STARTED"]
        assert payload["wager_placed"] is False
        return _sources(reconciled=0, selected=0, no_bet=0)

    monkeypatch.setattr(runner, "_acquire_router_inputs", acquire)
    runner.execute_current_shadow_all_market(target_size=20, output_dir=tmp_path)


def test_stage_sequence_tracks_the_exact_source_bound_chain(monkeypatch, tmp_path):
    _install_common(monkeypatch)
    observed = []
    monkeypatch.setattr(
        runner,
        "_checkpoint_stage",
        lambda **kwargs: observed.append(kwargs["stage"]),
    )
    sources = _sources(reconciled=1, selected=1, no_bet=0, router_inputs=(object(),))
    chosen = _portfolio(target=1, selected=1)

    def acquire(**kwargs):
        callback = kwargs["stage_callback"]
        for stage in runner.STAGE_SEQUENCE[1:5]:
            callback(stage)
        return sources

    monkeypatch.setattr(runner, "_acquire_router_inputs", acquire)
    monkeypatch.setattr(runner.portfolio_module, "optimize_shadow_portfolio", lambda *_a, **_k: chosen)
    monkeypatch.setattr(
        runner.share_module,
        "create_verified_shadow_all_market_share_code",
        lambda **_kwargs: _share(runner.share_module.STATUS_CODE_VERIFIED,
                                 code="CHAIN", url="https://example.test/chain"),
    )
    runner.execute_current_shadow_all_market(target_size=1, output_dir=tmp_path)
    assert tuple(observed) == runner.STAGE_SEQUENCE


def test_timeout_receipt_is_durable_fail_closed_and_identifies_stage(monkeypatch, tmp_path):
    _install_common(monkeypatch)
    runner._checkpoint_stage(
        output_dir=tmp_path,
        stage=runner.STAGE_CURRENT_DURABLE_FRESH_HISTORY,
        exact_commit_sha=SHA,
        target_size=20,
    )
    result = runner.write_current_shadow_timeout_receipt(target_size=20, output_dir=tmp_path)
    payload = _receipt_payload(tmp_path / runner.RUN_RECEIPT_FILENAME)
    assert result.status == runner.STATUS_SOURCE_INCOMPLETE
    assert result.share_code is None
    assert result.shortfall == 20
    assert result.source_summary["timeout_stage"] == runner.STAGE_CURRENT_DURABLE_FRESH_HISTORY
    assert result.reasons == (
        f"RUN_BUDGET_EXCEEDED:{runner.CURRENT_SHADOW_RUN_TIMEOUT_SECONDS}:"
        f"STAGE:{runner.STAGE_CURRENT_DURABLE_FRESH_HISTORY}",
    )
    assert payload["wager_placed"] is False
    assert payload["stake_submitted"] is False


def test_cli_supervisor_times_out_worker_and_emits_durable_receipt(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv(cli.WORKER_ENV, raising=False)
    captured = {}

    def timeout(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(cli.subprocess, "run", timeout)
    monkeypatch.setattr(runner, "write_current_shadow_timeout_receipt",
                        lambda **_kwargs: _fake_terminal_receipt())
    rc = cli.main(["--target-size", "20", "--output-dir", str(tmp_path)])
    assert rc == 0
    assert captured["timeout"] == runner.CURRENT_SHADOW_RUN_TIMEOUT_SECONDS
    assert captured["env"][cli.WORKER_ENV] == "1"
    assert captured["command"][0] == cli.sys.executable
    assert json.loads(capsys.readouterr().out)["wager_placed"] is False


def test_zero_exact_reconciliations_is_truthful_insufficient_supported_markets(monkeypatch, tmp_path):
    _install_common(monkeypatch)
    monkeypatch.setattr(runner, "_acquire_router_inputs", lambda **_kwargs: _sources(reconciled=0, selected=0, no_bet=0))
    result = runner.execute_current_shadow_all_market(target_size=20, output_dir=tmp_path)
    assert result.status == runner.STATUS_INSUFFICIENT_SUPPORTED_MARKETS
    assert result.share_code is None
    assert result.shortfall == 20


def test_executed_head_and_audited_main_are_distinct_exact_identities(monkeypatch, tmp_path):
    _install_common(monkeypatch)
    captured = {}

    def acquire(**kwargs):
        captured.update(kwargs)
        return _sources(reconciled=0, selected=0, no_bet=0)

    monkeypatch.setattr(runner, "_acquire_router_inputs", acquire)
    result = runner.execute_current_shadow_all_market(target_size=1, output_dir=tmp_path)
    assert result.exact_commit_sha == SHA
    assert captured["lineage_main_sha"] == "b" * 40
    assert captured["lineage_main_sha"] != result.exact_commit_sha


def test_all_router_no_bet_is_first_class_successful_no_code_state(monkeypatch, tmp_path):
    _install_common(monkeypatch)
    monkeypatch.setattr(
        runner,
        "_acquire_router_inputs",
        lambda **_kwargs: _sources(reconciled=3, selected=0, no_bet=3, router_inputs=(object(), object(), object())),
    )
    result = runner.execute_current_shadow_all_market(target_size=20, output_dir=tmp_path)
    assert result.status == runner.STATUS_NO_BET
    assert result.share_code is None
    assert result.router_no_bet_count == 3


def test_verified_exact_target_maps_to_verified_terminal_state(monkeypatch, tmp_path):
    _install_common(monkeypatch)
    sources = _sources(reconciled=2, selected=2, no_bet=0, router_inputs=(object(), object()))
    chosen = _portfolio(target=2, selected=2)
    monkeypatch.setattr(runner, "_acquire_router_inputs", lambda **_kwargs: sources)
    monkeypatch.setattr(runner.portfolio_module, "optimize_shadow_portfolio", lambda *_args, **_kwargs: chosen)
    monkeypatch.setattr(
        runner.share_module,
        "create_verified_shadow_all_market_share_code",
        lambda **_kwargs: _share(runner.share_module.STATUS_CODE_VERIFIED, code="ABC123", url="https://example.test/code"),
    )
    result = runner.execute_current_shadow_all_market(target_size=2, output_dir=tmp_path)
    assert result.status == runner.STATUS_CODE_VERIFIED
    assert result.shortfall == 0
    assert result.share_code == "ABC123"
    assert result.to_dict()["wager_placed"] is False


def test_verified_shortfall_is_preserved_not_padded(monkeypatch, tmp_path):
    _install_common(monkeypatch)
    sources = _sources(reconciled=2, selected=2, no_bet=0, router_inputs=(object(), object()))
    chosen = _portfolio(target=20, selected=2, reserve=1)
    monkeypatch.setattr(runner, "_acquire_router_inputs", lambda **_kwargs: sources)
    monkeypatch.setattr(runner.portfolio_module, "optimize_shadow_portfolio", lambda *_args, **_kwargs: chosen)
    monkeypatch.setattr(
        runner.share_module,
        "create_verified_shadow_all_market_share_code",
        lambda **_kwargs: _share(
            runner.share_module.STATUS_CODE_VERIFIED_WITH_SHORTFALL,
            code="SHORT",
            url="https://example.test/short",
        ),
    )
    result = runner.execute_current_shadow_all_market(target_size=20, output_dir=tmp_path)
    assert result.status == runner.STATUS_CODE_VERIFIED_WITH_SHORTFALL
    assert result.selected_leg_count == 2
    assert result.shortfall == 18


def test_transport_reprice_and_provider_change_never_expose_code(monkeypatch, tmp_path):
    _install_common(monkeypatch)
    sources = _sources(reconciled=1, selected=1, no_bet=0, router_inputs=(object(),))
    chosen = _portfolio(target=1, selected=1)
    monkeypatch.setattr(runner, "_acquire_router_inputs", lambda **_kwargs: sources)
    monkeypatch.setattr(runner.portfolio_module, "optimize_shadow_portfolio", lambda *_args, **_kwargs: chosen)
    for status, expected in (
        (runner.share_module.STATUS_REPRICE_REQUIRED, runner.STATUS_REPRICE_REQUIRED),
        (runner.share_module.STATUS_PROVIDER_CHANGED, runner.STATUS_PROVIDER_CHANGED),
    ):
        monkeypatch.setattr(
            runner.share_module,
            "create_verified_shadow_all_market_share_code",
            lambda status=status, **_kwargs: _share(status, reasons=("changed",)),
        )
        result = runner.execute_current_shadow_all_market(target_size=1, output_dir=tmp_path / status)
        assert result.status == expected
        assert result.share_code is None


def test_target_size_bounds_fail_before_any_source_network(monkeypatch, tmp_path):
    called = False
    def bad(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("source acquisition should not run")
    monkeypatch.setattr(runner, "_acquire_router_inputs", bad)
    with pytest.raises(runner.CurrentShadowAllMarketRunnerError):
        runner.execute_current_shadow_all_market(target_size=0, output_dir=tmp_path)
    with pytest.raises(runner.CurrentShadowAllMarketRunnerError):
        runner.execute_current_shadow_all_market(target_size=51, output_dir=tmp_path)
    assert called is False


def test_shadow_price_failure_is_captured_as_source_incomplete(monkeypatch, tmp_path):
    _install_common(monkeypatch)

    def fail(**_kwargs):
        raise runner.ShadowPriceError("synthetic price-chain failure")

    monkeypatch.setattr(runner, "_acquire_router_inputs", fail)
    result = runner.execute_current_shadow_all_market(target_size=1, output_dir=tmp_path)
    assert result.status == runner.STATUS_SOURCE_INCOMPLETE
    assert result.share_code is None
    assert result.reasons == (
        "SOURCE_CHAIN_FAILED:ShadowPriceError:synthetic price-chain failure",
    )


def test_source_failure_preserves_bounded_cause_identity(monkeypatch, tmp_path):
    _install_common(monkeypatch)

    def fail(**_kwargs):
        try:
            raise ValueError("exact inner cause")
        except ValueError as inner:
            raise runner.CurrentShadowAllMarketRunnerError("outer boundary") from inner

    monkeypatch.setattr(runner, "_acquire_router_inputs", fail)
    result = runner.execute_current_shadow_all_market(target_size=1, output_dir=tmp_path)
    assert result.reasons == (
        "SOURCE_CHAIN_FAILED:CurrentShadowAllMarketRunnerError:outer boundary<-ValueError:exact inner cause",
    )


def test_runner_authority_never_grants_production_or_wager():
    assert runner.AUTHORITY["research_shadow_current_runner"] is True
    for key in (
        "production_model", "production_probability", "phase6", "production_price_all",
        "production_market_router", "production_portfolio", "production_selection",
        "production_sportybet_execution", "login", "cookies", "wallet", "staking", "bet", "wager_placed",
    ):
        assert runner.AUTHORITY[key] is False
