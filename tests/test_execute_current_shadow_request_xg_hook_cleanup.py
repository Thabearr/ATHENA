from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from scripts import execute_current_shadow_request as request_cli
from scripts import execute_current_shadow_daily as daily


def _args(tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        target_size=15,
        fixture_scope=daily.SCOPE_TODAY,
        fixture_dates=None,
        output_dir=tmp_path,
    )


def test_xg_fallback_hook_restores_when_policy_write_fails(monkeypatch, tmp_path):
    sentinel = object()
    seen = []

    monkeypatch.setattr(
        request_cli.xg_fallback,
        "install",
        lambda: seen.append("install") or sentinel,
    )

    def restore(value):
        assert value is sentinel
        seen.append("restore")

    monkeypatch.setattr(request_cli.xg_fallback, "restore", restore)
    monkeypatch.setattr(
        request_cli,
        "_write_request_policy",
        lambda _args: (_ for _ in ()).throw(RuntimeError("policy failed")),
    )
    monkeypatch.setattr(
        request_cli.daily,
        "_execute_worker",
        lambda _args: pytest.fail("worker must not run after policy failure"),
    )

    with pytest.raises(RuntimeError, match="policy failed"):
        request_cli._execute_worker(_args(tmp_path))
    assert seen == ["install", "restore"]


def test_request_policy_records_non_authoritative_elo_only_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(
        request_cli.runner,
        "_now",
        lambda: __import__("datetime").datetime(
            2026, 9, 7, 12, 0, tzinfo=__import__("datetime").timezone.utc
        ),
    )
    args = _args(tmp_path)
    request_cli._write_request_policy(args)
    import json

    payload = json.loads((tmp_path / request_cli.REQUEST_POLICY_FILENAME).read_text())
    fallback = payload["current_asof_elo_only_policy"]
    assert fallback["base_binding_runs_first"] is True
    assert fallback["only_outside_seal_window_missing_full_model"] is True
    assert fallback["fallback"]["missing_feature_imputation"] is False
    assert fallback["fallback"]["historical_feature_scope_expansion"] is False
    assert fallback["wager_placed"] is False
