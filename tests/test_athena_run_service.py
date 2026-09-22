from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from domain.run_contracts import (
    AuthorityManifest,
    RunReceipt,
    RunRequest,
    RunStage,
    canonical_json_bytes,
)
from services.athena_run_service import (
    AthenaRunService,
    AthenaRunServiceError,
    ExecutorResult,
)


NOW = datetime(2026, 9, 22, 11, 30, 0, 123456, tzinfo=timezone.utc)
COMMIT = "a" * 40


def _request(**overrides) -> RunRequest:
    values = {
        "dates": (date(2026, 9, 23), date(2026, 9, 24)),
        "target_legs": 2,
        "target_total_odds": None,
        "bookie": "sportybet",
        "mode": "main_application",
        "authority_profile": "MAIN",
        "create_share_code": False,
        "place_wager": False,
    }
    values.update(overrides)
    return RunRequest(**values)


def _service(tmp_executor, *, commit=COMMIT, now=NOW) -> AthenaRunService:
    return AthenaRunService(
        _test_executor_overrides={
            ("MAIN", "main_application", "sportybet"): tmp_executor,
            ("SHADOW", "research_shadow", "sportybet"): tmp_executor,
        },
        _commit_sha_provider=lambda: commit,
        _clock=lambda: now,
    )


def _manifest(request: RunRequest) -> AuthorityManifest:
    return AthenaRunService.authority_manifest_for(request)


def _captured_shadow_policy(day: str) -> dict:
    return {
        "schema_version": 1,
        "dataset_name": "athena-current-shadow-request-policy-v1",
        "fixture_scope": "today",
        "fixture_dates": [day],
        "rolling_date_policy": {"policy_id": "CAPTURED_TEST_POLICY"},
        "run199_identity_policy_id": "CAPTURED_RUN199",
        "run199_identity_policy_sha256": "b" * 64,
        "row_local_quote_policy": {"policy_id": "CAPTURED_ROW_LOCAL"},
        "current_asof_elo_only_policy": {"policy_id": "CAPTURED_ELO"},
        "authority": {
            "research_shadow_request": True,
            "production_model": False,
            "pricing": False,
            "selection": False,
            "sportybet_execution": False,
            "bet": False,
            "wager_placed": False,
        },
        "wager_placed": False,
    }


def _captured_shadow_receipt(*, target: int, exact_commit: str, observed_at: datetime) -> dict:
    return {
        "schema_version": 1,
        "dataset_name": "athena-current-shadow-all-market-runner-v1",
        "status": "RESEARCH_NO_CODE_NO_BET",
        "observed_at": observed_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "exact_commit_sha": exact_commit,
        "requested_target_size": target,
        "reviewed_fixture_count": 0,
        "reconciled_fixture_count": 0,
        "provider_event_count": 0,
        "priced_fixture_count": 0,
        "router_selected_count": 0,
        "router_no_bet_count": 0,
        "source_summary": {"wager_placed": False},
        "portfolio": None,
        "portfolio_sha256": None,
        "selected_leg_count": 0,
        "reserve_leg_count": 0,
        "shortfall": target,
        "share_code_receipt": None,
        "fixture_funnel": {},
        "opportunity_funnel": {},
        "market_diagnostics": [],
        "market_family_diagnostics": [],
        "final_selected_legs": [],
        "fresh_fallback_events": [],
        "shareCode": None,
        "shareURL": None,
        "reasons": ["SYNTHETIC_CAPTURED_NO_BET"],
        "authority": {
            "research_shadow_current_runner": True,
            "research_shadow_source_acquisition": True,
            "research_shadow_probability_consumption": True,
            "research_shadow_price_all": True,
            "research_shadow_market_routing": True,
            "research_shadow_portfolio": True,
            "research_shadow_shortfall": True,
            "research_anonymous_share_code_generation": True,
            "provider_create_reload_verification": True,
            "production_model": False,
            "production_probability": False,
            "phase6": False,
            "production_price_all": False,
            "production_market_router": False,
            "production_portfolio": False,
            "production_selection": False,
            "production_sportybet_execution": False,
            "login": False,
            "cookies": False,
            "wallet": False,
            "staking": False,
            "bet": False,
            "wager_placed": False,
        },
        "sportybet_login_used": False,
        "sportybet_cookie_used": False,
        "sportybet_wallet_used": False,
        "stake_submitted": False,
        "wager_placed": False,
    }


def test_run_requires_exact_run_request(tmp_path):
    service = _service(lambda *_args, **_kwargs: pytest.fail("executor called"))
    with pytest.raises(AthenaRunServiceError, match="exact domain.run_contracts.RunRequest"):
        service.run({"dates": []}, output_root=tmp_path)  # type: ignore[arg-type]


def test_main_authority_manifest_is_all_false_and_source_controlled():
    request = _request()
    manifest = _manifest(request)
    assert manifest == AuthorityManifest(
        authority_profile="MAIN",
        mode="main_application",
        provider_acquisition=False,
        share_code_generation=False,
        login=False,
        cookies=False,
        wallet=False,
        staking=False,
        wager=False,
    )
    assert manifest.provider_acquisition is False
    assert manifest.share_code_generation is False
    assert all(getattr(manifest, name) is False for name in ("login", "cookies", "wallet", "staking", "wager"))


def test_shadow_manifest_declares_only_reviewed_research_capabilities():
    request = _request(
        authority_profile="SHADOW", mode="research_shadow", create_share_code=True
    )
    manifest = _manifest(request)
    assert manifest.provider_acquisition is True
    assert manifest.share_code_generation is True
    assert all(getattr(manifest, name) is False for name in ("login", "cookies", "wallet", "staking", "wager"))


def test_request_is_persisted_canonically_before_synthetic_executor(tmp_path):
    request = _request()
    observed = {}

    def executor(actual_request, *, authority_manifest, run_directory, exact_commit_sha, observed_at):
        request_path = run_directory / "athena-run-request.json"
        observed["bytes"] = request_path.read_bytes()
        observed["manifest"] = authority_manifest
        observed["commit"] = exact_commit_sha
        observed["time"] = observed_at
        assert observed["bytes"] == canonical_json_bytes(actual_request)
        return ExecutorResult(status="NO_BET", evidence={"source": "offline synthetic"})

    receipt = _service(executor).run(request, output_root=tmp_path)
    assert observed["bytes"] == canonical_json_bytes(request)
    assert observed["manifest"] == _manifest(request)
    assert observed["commit"] == COMMIT
    assert observed["time"] == NOW
    assert type(receipt) is RunReceipt
    assert receipt.request == request
    assert receipt.exact_commit_sha == COMMIT
    assert receipt.wager_placed is False
    assert receipt.selected_legs == ()
    assert receipt.counts["selected_leg_count"] == 0
    assert receipt.shortfall == 2
    run_directory = tmp_path / request.canonical_sha256
    assert (run_directory / "athena-run-request.json").read_bytes() == canonical_json_bytes(request)
    receipt_bytes = (run_directory / "athena-run-receipt.json").read_bytes()
    assert receipt_bytes == canonical_json_bytes(receipt)
    assert RunReceipt.from_json_bytes(receipt_bytes) == receipt


def test_service_binds_synthetic_selected_legs_and_truthful_shortfall(tmp_path):
    request = _request(target_legs=3)
    calls = []

    def executor(actual, **_kwargs):
        calls.append(actual)
        return ExecutorResult(
            status="SHORTFALL",
            stages=(RunStage(stage="SYNTHETIC", status="COMPLETED", observed_at=NOW),),
            selected_legs=({"selection": "fixture-1"},),
            evidence={"synthetic": True},
        )

    receipt = _service(executor).run(request, output_root=tmp_path)
    assert calls == [request]
    assert receipt.selected_legs == ({"selection": "fixture-1"},)
    assert receipt.counts["selected_leg_count"] == 1
    assert receipt.counts["target_legs"] == 3
    assert receipt.counts["shortfall"] == 2
    assert receipt.shortfall == 2


def test_idempotent_replay_returns_exact_persisted_receipt_without_executor(tmp_path):
    request = _request()
    calls = []

    def executor(_request, **_kwargs):
        calls.append(1)
        return ExecutorResult(status="NO_BET", evidence={"synthetic": True})

    service = _service(executor)
    first = service.run(request, output_root=tmp_path)
    second = service.run(request, output_root=tmp_path)
    assert first == second
    assert calls == [1]


@pytest.mark.parametrize("bad_payload", [b"not-json\n", b"{}\n"])
def test_corrupt_existing_receipt_fails_closed_without_overwrite(tmp_path, bad_payload):
    request = _request()
    calls = []

    def executor(_request, **_kwargs):
        calls.append(1)
        return ExecutorResult(status="NO_BET")

    service = _service(executor)
    first = service.run(request, output_root=tmp_path)
    receipt_path = tmp_path / request.canonical_sha256 / "athena-run-receipt.json"
    receipt_path.write_bytes(bad_payload)
    before = receipt_path.read_bytes()
    with pytest.raises(AthenaRunServiceError, match="corrupt"):
        service.run(request, output_root=tmp_path)
    assert receipt_path.read_bytes() == before
    assert calls == [1]
    assert first.status == "NO_BET"


def test_mismatched_existing_request_fails_without_executor_or_overwrite(tmp_path):
    request = _request()
    calls = []
    service = _service(lambda *_args, **_kwargs: calls.append(1))
    run_directory = tmp_path / request.canonical_sha256
    run_directory.mkdir(parents=True)
    request_path = run_directory / "athena-run-request.json"
    contradictory = canonical_json_bytes(_request(target_legs=1))
    request_path.write_bytes(contradictory)

    with pytest.raises(AthenaRunServiceError, match="does not bind exact RunRequest"):
        service.run(request, output_root=tmp_path)
    assert request_path.read_bytes() == contradictory
    assert calls == []


def test_preexisting_request_without_receipt_fails_closed_without_rerun(tmp_path):
    request = _request()
    calls = []
    run_directory = tmp_path / request.canonical_sha256
    run_directory.mkdir(parents=True)
    request_path = run_directory / "athena-run-request.json"
    request_path.write_bytes(canonical_json_bytes(request))
    original = request_path.read_bytes()
    service = _service(lambda *_args, **_kwargs: calls.append(1))

    with pytest.raises(AthenaRunServiceError, match="without a terminal receipt; refusing rerun"):
        service.run(request, output_root=tmp_path)
    assert request_path.read_bytes() == original
    assert calls == []


def test_existing_receipt_for_other_commit_fails_closed(tmp_path):
    request = _request()
    first_service = _service(lambda *_args, **_kwargs: ExecutorResult(status="NO_BET"))
    first_service.run(request, output_root=tmp_path)
    second_service = _service(
        lambda *_args, **_kwargs: pytest.fail("executor reran"), commit="b" * 40
    )
    with pytest.raises(AthenaRunServiceError, match="does not bind this exact run"):
        second_service.run(request, output_root=tmp_path)


def test_non_null_target_total_odds_is_durable_failure_before_executor(tmp_path):
    request = _request(target_total_odds=Decimal("2.5"))
    calls = []
    receipt = _service(lambda *_args, **_kwargs: calls.append(1)).run(request, output_root=tmp_path)
    assert receipt.status == "TARGET_TOTAL_ODDS_NOT_SUPPORTED"
    assert calls == []
    assert receipt.selected_legs == ()
    assert receipt.shortfall == request.target_legs
    assert receipt.evidence["executor_invoked"] is False
    assert (tmp_path / request.canonical_sha256 / "athena-run-receipt.json").exists()


def test_unsupported_bookie_or_mode_fails_closed_before_executor(tmp_path):
    calls = []
    service = _service(lambda *_args, **_kwargs: calls.append(1))
    for request in (
        _request(bookie="unknownbookie"),
        _request(mode="unreviewed_mode"),
    ):
        receipt = service.run(request, output_root=tmp_path)
        assert receipt.status == "EXECUTOR_UNAVAILABLE"
        assert receipt.selected_legs == ()
        assert receipt.shortfall == request.target_legs
    assert calls == []


@pytest.mark.parametrize(
    "outcome",
    [
        {"status": "NO_BET"},
        ExecutorResult(status="NO_BET", evidence={"nested": {"wager_placed": True}}),
        ExecutorResult(status="NO_BET", selected_legs=({"x": 1}, {"x": 2}, {"x": 3})),
    ],
)
def test_malformed_or_unsafe_executor_output_is_rejected(tmp_path, outcome):
    with pytest.raises(AthenaRunServiceError):
        _service(lambda *_args, **_kwargs: outcome).run(_request(), output_root=tmp_path)


def test_executor_cannot_return_an_authority_mismatched_share_result(tmp_path):
    outcome = ExecutorResult(
        status="NO_BET",
        selected_legs=({"selection": "one"},),
        share_code_result={"verified": True},
    )
    with pytest.raises(AthenaRunServiceError, match="could not form a safe RunReceipt"):
        _service(lambda *_args, **_kwargs: outcome).run(_request(), output_root=tmp_path)


def test_main_default_executor_maps_existing_phase6_boundary_without_provider(monkeypatch, tmp_path):
    from domain import current_sportybet_accumulator_request as main_request

    captured = {}

    def fake_target_only(*, target_size, output_dir):
        captured["target_size"] = target_size
        captured["output_dir"] = output_dir
        return SimpleNamespace(
            requested_target_size=target_size,
            evaluation_time=NOW,
            blocked_at="REVIEW_REQUIRED",
            real_current_provider_execution_attempted=False,
            wager_placed=False,
            to_dict=lambda: {"status": "BLOCKED", "wager_placed": False},
        )

    monkeypatch.setattr(main_request, "execute_current_accumulator_request", fake_target_only)
    service = AthenaRunService(_commit_sha_provider=lambda: COMMIT, _clock=lambda: NOW)
    receipt = service.run(_request(target_legs=4), output_root=tmp_path)
    assert receipt.status == "MAIN_PHASE6_AUTHORITY_REQUIRED"
    assert receipt.shortfall == 4
    assert receipt.authority_manifest.provider_acquisition is False
    assert receipt.authority_manifest.share_code_generation is False
    assert receipt.evidence["fixture_execution"] is False
    assert captured["target_size"] == 4
    assert captured["output_dir"] == tmp_path / _request(target_legs=4).canonical_sha256


def test_shadow_synthetic_executor_preserves_exact_request_dates_without_live_path(tmp_path):
    request = _request(
        dates=(date(2026, 9, 23),),
        authority_profile="SHADOW",
        mode="research_shadow",
        create_share_code=True,
    )
    calls = []

    def synthetic_executor(actual, **kwargs):
        calls.append((actual, kwargs["authority_manifest"]))
        return ExecutorResult(
            status="NO_BET",
            counts={"provider_event_count": 0},
            evidence={"synthetic": True, "provider_acquisition": False},
        )

    service = _service(synthetic_executor)
    receipt = service.run(request, output_root=tmp_path)
    assert receipt.status == "NO_BET"
    assert receipt.request.dates == (date(2026, 9, 23),)
    assert receipt.counts["provider_event_count"] == 0
    assert calls == [(request, _manifest(request))]


def test_shadow_default_adapter_preserves_timeout_receipt_and_progress_without_outer_timeout(
    monkeypatch, tmp_path
):
    from services import athena_run_service as service_module
    from scripts import execute_current_shadow_all_market_fresh_reprice_bound as bound

    observed_at = datetime(2026, 9, 23, 12, 0, 0, 123456, tzinfo=timezone.utc)
    reviewed_budget_seconds = bound._supervisor_timeout_seconds()
    assert reviewed_budget_seconds == 75 * 60
    request = _request(
        dates=(date(2026, 9, 23),),
        target_legs=2,
        authority_profile="SHADOW",
        mode="research_shadow",
        create_share_code=True,
    )
    invocations = []

    def fake_supervisor(command, **kwargs):
        invocations.append((list(command), dict(kwargs)))
        output_dir = Path(command[command.index("--output-dir") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        policy = _captured_shadow_policy("20260923")
        legacy_receipt = _captured_shadow_receipt(
            target=request.target_legs,
            exact_commit=COMMIT,
            observed_at=observed_at,
        )
        legacy_receipt.update(
            {
                "status": "RESEARCH_NO_CODE_SOURCE_INCOMPLETE",
                "reviewed_fixture_count": 3,
                "reconciled_fixture_count": 2,
                "provider_event_count": 2,
                "priced_fixture_count": 0,
                "router_selected_count": 0,
                "router_no_bet_count": 0,
                "source_summary": {
                    "timeout_stage": "CURRENT_DURABLE_FRESH_HISTORY",
                    "timeout_progress_status": "IN_PROGRESS",
                    "run_budget_seconds": reviewed_budget_seconds,
                    "wager_placed": False,
                },
                "reasons": [
                    f"RUN_BUDGET_EXCEEDED:{reviewed_budget_seconds}:STAGE:CURRENT_DURABLE_FRESH_HISTORY"
                ],
            }
        )
        checkpoint_base = {
            "schema_version": 1,
            "dataset_name": "athena-current-shadow-all-market-runner-v1",
            "stage": "CURRENT_DURABLE_FRESH_HISTORY",
            "stage_index": 3,
            "observed_at": observed_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "exact_commit_sha": COMMIT,
            "requested_target_size": request.target_legs,
            "wager_placed": False,
        }
        progress = {
            **checkpoint_base,
            "progress_status": "IN_PROGRESS",
            "counts": {
                "reviewed_fixture_count": 3,
                "reconciled_fixture_count": 2,
                "provider_event_count": 2,
                "priced_fixture_count": 0,
                "router_selected_count": 0,
                "router_no_bet_count": 0,
            },
            "source_summary": {
                "timeout_stage": "CURRENT_DURABLE_FRESH_HISTORY",
                "wager_placed": False,
            },
        }
        (output_dir / "current-shadow-request-policy.json").write_text(
            json.dumps(policy), encoding="utf-8"
        )
        (output_dir / "current-shadow-all-market-run-receipt.json").write_text(
            json.dumps(legacy_receipt), encoding="utf-8"
        )
        (output_dir / "current-shadow-all-market-stage.json").write_text(
            json.dumps(checkpoint_base), encoding="utf-8"
        )
        (output_dir / "current-shadow-all-market-progress.json").write_text(
            json.dumps(progress), encoding="utf-8"
        )
        return SimpleNamespace(returncode=0, stdout="synthetic child", stderr="")

    monkeypatch.setattr(service_module.subprocess, "run", fake_supervisor)
    service = AthenaRunService(
        _commit_sha_provider=lambda: COMMIT,
        _clock=lambda: observed_at,
    )
    receipt = service.run(request, output_root=tmp_path)

    assert receipt.status == "RESEARCH_NO_CODE_SOURCE_INCOMPLETE"
    assert receipt.request == request
    assert receipt.request.dates == (date(2026, 9, 23),)
    assert receipt.selected_legs == ()
    assert receipt.shortfall == 2
    assert receipt.counts["reviewed_fixture_count"] == 3
    assert receipt.counts["reconciled_fixture_count"] == 2
    assert receipt.counts["provider_event_count"] == 2
    assert receipt.counts["priced_fixture_count"] == 0
    assert receipt.counts["selected_leg_count"] == 0
    assert receipt.counts["shortfall"] == 2
    assert receipt.share_code_result is None
    assert receipt.wager_placed is False
    assert receipt.authority_manifest == _manifest(request)
    assert len(invocations) == 1
    command, kwargs = invocations[0]
    assert "timeout" not in kwargs
    assert command[command.index("--fixture-dates") + 1] == "20260923"
    assert "scripts.execute_current_shadow_request" in command
    adapted_evidence = receipt.evidence["current_shadow_adapter"]["evidence"]
    preserved_legacy = adapted_evidence["legacy_current_shadow"]
    assert preserved_legacy["receipt"]["source_summary"]["timeout_stage"] == (
        "CURRENT_DURABLE_FRESH_HISTORY"
    )
    assert preserved_legacy["latest_progress_checkpoint"]["counts"] == {
        "reviewed_fixture_count": 3,
        "reconciled_fixture_count": 2,
        "provider_event_count": 2,
        "priced_fixture_count": 0,
        "router_selected_count": 0,
        "router_no_bet_count": 0,
    }


def test_shadow_lagos_date_outside_exact_utc_window_fails_closed_without_shift(tmp_path):
    request = _request(
        dates=(date(2026, 10, 10),),
        authority_profile="SHADOW",
        mode="research_shadow",
        create_share_code=True,
    )
    late_utc = datetime(2026, 10, 2, 23, 30, tzinfo=timezone.utc)
    service = AthenaRunService(_commit_sha_provider=lambda: COMMIT, _clock=lambda: late_utc)
    receipt = service.run(request, output_root=tmp_path)
    assert receipt.status == "SHADOW_DATE_POLICY_UNREPRESENTABLE"
    assert receipt.request.dates == (date(2026, 10, 10),)
    assert receipt.evidence["request_dates_preserved"] == ("2026-10-10",)


def test_request_rejects_untrusted_executor_factory_surface():
    with pytest.raises(TypeError, match="invalid test-only executor override"):
        AthenaRunService(_test_executor_overrides={("MAIN", "main_application", "sportybet"): "module.factory"})  # type: ignore[dict-item]
