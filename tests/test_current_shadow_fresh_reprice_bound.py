from __future__ import annotations

from types import SimpleNamespace

import pytest

from domain import _current_shadow_quote_binding as quote_binding
from domain import current_shadow_all_market_runner as runner
from scripts import execute_current_shadow_all_market as cli
from scripts import execute_current_shadow_all_market_fresh_reprice as fresh_cli
from scripts import execute_current_shadow_all_market_fresh_reprice_bound as bound


def test_bound_worker_delegates_price_all_verification_to_installed_quote_binding(monkeypatch):
    original_price_verify = runner.price_module.verify_current_shadow_price_context
    original_quote_verify = quote_binding.verify_current_shadow_price_context
    seen = []

    def fake_fresh_worker(_args):
        def installed(value):
            seen.append(value)
            return ("fresh", value)

        quote_binding.verify_current_shadow_price_context = installed
        try:
            assert runner.price_module.verify_current_shadow_price_context("context") == (
                "fresh",
                "context",
            )
            return 17
        finally:
            quote_binding.verify_current_shadow_price_context = original_quote_verify

    monkeypatch.setattr(fresh_cli, "_execute_worker", fake_fresh_worker)

    assert bound._execute_worker(SimpleNamespace()) == 17
    assert seen == ["context"]
    assert runner.price_module.verify_current_shadow_price_context is original_price_verify


def test_bound_worker_restores_price_all_verifier_after_failure(monkeypatch):
    original_price_verify = runner.price_module.verify_current_shadow_price_context

    def boom(_args):
        raise RuntimeError("worker failed")

    monkeypatch.setattr(fresh_cli, "_execute_worker", boom)

    with pytest.raises(RuntimeError, match="worker failed"):
        bound._execute_worker(SimpleNamespace())

    assert runner.price_module.verify_current_shadow_price_context is original_price_verify


def test_bound_worker_does_not_replace_frozen_portfolio_freshness_policy():
    original_optimizer = runner.portfolio_module.optimize_shadow_portfolio
    original_max_age = runner.portfolio_module.MAX_QUOTE_AGE_SECONDS

    assert original_max_age == 900
    assert runner.portfolio_module.optimize_shadow_portfolio is original_optimizer


def test_bound_main_uses_bounded_create_reload_tail_without_weakening_freshness(
    monkeypatch, tmp_path
):
    seen = {}

    monkeypatch.delenv(cli.WORKER_ENV, raising=False)
    monkeypatch.setattr(runner, "CURRENT_SHADOW_RUN_TIMEOUT_SECONDS", 25 * 60)

    def fake_run(command, *, env, check, timeout):
        seen["command"] = command
        seen["env"] = env
        seen["check"] = check
        seen["timeout"] = timeout
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(bound.subprocess, "run", fake_run)

    assert bound.main(
        [
            "--target-size",
            "20",
            "--output-dir",
            str(tmp_path),
        ]
    ) == 0
    assert bound.HOSTED_SUPERVISOR_TIMEOUT_SECONDS == 60 * 60
    assert seen["timeout"] == 60 * 60
    assert seen["check"] is False
    assert seen["env"][cli.WORKER_ENV] == "1"
    assert runner.CURRENT_SHADOW_RUN_TIMEOUT_SECONDS == 60 * 60
    assert runner.portfolio_module.MAX_QUOTE_AGE_SECONDS == 900
