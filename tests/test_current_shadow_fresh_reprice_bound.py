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


def test_bound_supervisor_extends_generic_budget_but_preserves_workflow_margin():
    assert cli.HOSTED_SUPERVISOR_TIMEOUT_SECONDS == 50 * 60
    assert bound.HOSTED_SUPERVISOR_TIMEOUT_SECONDS == 55 * 60
    assert bound._supervisor_timeout_seconds() == 55 * 60
    assert bound._supervisor_timeout_seconds() < bound.WORKFLOW_JOB_TIMEOUT_SECONDS
    assert bound.WORKFLOW_JOB_TIMEOUT_SECONDS == 60 * 60
    assert runner.portfolio_module.MAX_QUOTE_AGE_SECONDS == 900


def test_bound_main_uses_exact_prf_supervisor_budget(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.delenv(cli.WORKER_ENV, raising=False)

    def fake_run(command, *, env, check, timeout):
        seen["command"] = command
        seen["env"] = env
        seen["check"] = check
        seen["timeout"] = timeout
        return SimpleNamespace(returncode=23)

    monkeypatch.setattr(bound.subprocess, "run", fake_run)

    result = bound.main(
        [
            "--target-size",
            "20",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert result == 23
    assert seen["timeout"] == 55 * 60
    assert seen["check"] is False
    assert seen["env"][cli.WORKER_ENV] == "1"
    assert seen["command"][0] == bound.sys.executable
    assert seen["command"][1:3] == ["-m", bound.WORKER_MODULE]
    assert runner.portfolio_module.MAX_QUOTE_AGE_SECONDS == 900


def test_timeout_receipt_reports_exact_prf_budget_and_restores_generic_budget(
    monkeypatch, tmp_path
):
    original = runner.CURRENT_SHADOW_RUN_TIMEOUT_SECONDS
    observed = {}
    sentinel = SimpleNamespace(to_dict=lambda: {"status": "timeout"})

    def fake_timeout_receipt(*, target_size, output_dir):
        observed["target_size"] = target_size
        observed["output_dir"] = output_dir
        observed["budget"] = runner.CURRENT_SHADOW_RUN_TIMEOUT_SECONDS
        return sentinel

    monkeypatch.setattr(
        runner,
        "write_current_shadow_timeout_receipt",
        fake_timeout_receipt,
    )

    result = bound._write_timeout_receipt(target_size=20, output_dir=tmp_path)

    assert result is sentinel
    assert observed == {
        "target_size": 20,
        "output_dir": tmp_path,
        "budget": 55 * 60,
    }
    assert runner.CURRENT_SHADOW_RUN_TIMEOUT_SECONDS == original
