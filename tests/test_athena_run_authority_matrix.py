from __future__ import annotations

from datetime import date, datetime, timezone
import subprocess

from domain.run_contracts import RunRequest
from services.athena_run_service import AthenaRunService, ExecutorResult


NOW = datetime(2026, 9, 22, 12, 30, tzinfo=timezone.utc)
COMMIT = "a" * 40


def _request(*, profile="MAIN", mode=None, bookie="sportybet", create_share_code=False):
    selected_mode = mode or ("main_application" if profile == "MAIN" else "research_shadow")
    return RunRequest(
        dates=(date(2026, 9, 23),),
        target_legs=2,
        target_total_odds=None,
        bookie=bookie,
        mode=selected_mode,
        authority_profile=profile,
        create_share_code=create_share_code,
        place_wager=False,
    )


def _service(executor=None):
    overrides = None
    if executor is not None:
        overrides = {
            ("MAIN", "main_application", "sportybet"): executor,
            ("SHADOW", "research_shadow", "sportybet"): executor,
        }
    return AthenaRunService(
        _test_executor_overrides=overrides,
        _commit_sha_provider=lambda: COMMIT,
        _clock=lambda: NOW,
    )


def _assert_sensitive_capabilities_denied(manifest):
    assert all(
        getattr(manifest, name) is False
        for name in ("login", "cookies", "wallet", "staking", "wager")
    )


def test_main_no_delivery_is_admitted_with_no_external_capability(tmp_path):
    calls = []

    def synthetic_executor(request, *, authority_manifest, **_kwargs):
        calls.append((request, authority_manifest))
        return ExecutorResult(status="SYNTHETIC_MAIN_ADMITTED")

    request = _request(profile="MAIN", create_share_code=False)
    manifest = AthenaRunService.authority_manifest_for(request)
    receipt = _service(synthetic_executor).run(request, output_root=tmp_path)

    assert manifest.provider_acquisition is False
    assert manifest.share_code_generation is False
    _assert_sensitive_capabilities_denied(manifest)
    assert calls == [(request, manifest)]
    assert receipt.status == "SYNTHETIC_MAIN_ADMITTED"
    assert receipt.share_code_result is None
    assert receipt.wager_placed is False


def test_main_production_path_remains_fail_closed_without_provider(monkeypatch, tmp_path):
    from domain import current_sportybet_accumulator_request as main_boundary

    provider_calls = []

    def safe_target_only(*, target_size, output_dir):
        return type("SafeTargetOnly", (), {
            "requested_target_size": target_size,
            "evaluation_time": NOW,
            "blocked_at": "REVIEW_REQUIRED",
            "real_current_provider_execution_attempted": False,
            "wager_placed": False,
            "to_dict": lambda self: {"status": "BLOCKED", "wager_placed": False},
        })()

    monkeypatch.setattr(main_boundary, "execute_current_accumulator_request", safe_target_only)
    request = _request(profile="MAIN", create_share_code=False)
    receipt = _service().run(request, output_root=tmp_path)
    assert receipt.status == "MAIN_PHASE6_AUTHORITY_REQUIRED"
    assert receipt.authority_manifest.provider_acquisition is False
    assert receipt.authority_manifest.share_code_generation is False
    assert provider_calls == []


def test_main_delivery_is_denied_before_synthetic_executor(tmp_path):
    calls = []
    request = _request(profile="MAIN", create_share_code=True)
    manifest = AthenaRunService.authority_manifest_for(request)
    receipt = _service(lambda *_args, **_kwargs: calls.append("executor")).run(
        request, output_root=tmp_path
    )

    assert manifest.provider_acquisition is False
    assert manifest.share_code_generation is False
    assert receipt.status == "REQUEST_AUTHORITY_MISMATCH"
    assert receipt.evidence["executor_invoked"] is False
    assert receipt.share_code_result is None
    assert calls == []


def test_shadow_no_delivery_is_admitted_to_synthetic_executor_and_narrows_delivery(tmp_path):
    calls = []

    def synthetic_executor(request, *, authority_manifest, **_kwargs):
        calls.append((request, authority_manifest))
        return ExecutorResult(status="SYNTHETIC_SHADOW_ADMITTED")

    request = _request(profile="SHADOW", create_share_code=False)
    manifest = AthenaRunService.authority_manifest_for(request)
    receipt = _service(synthetic_executor).run(request, output_root=tmp_path)

    assert manifest.provider_acquisition is True
    assert manifest.share_code_generation is False
    _assert_sensitive_capabilities_denied(manifest)
    assert calls == [(request, manifest)]
    assert receipt.status == "SYNTHETIC_SHADOW_ADMITTED"
    assert receipt.authority_manifest.share_code_generation is False
    assert receipt.share_code_result is None
    assert receipt.wager_placed is False


def test_shadow_no_delivery_production_executor_launches_with_explicit_false_flag_offline(
    monkeypatch, tmp_path
):
    from services import athena_run_service as service_module

    child_commands = []
    child_kwargs = []

    def offline_child(command, **kwargs):
        child_commands.append(command)
        child_kwargs.append(kwargs)
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="synthetic offline stop")

    monkeypatch.setattr(service_module.subprocess, "run", offline_child)
    request = _request(profile="SHADOW", create_share_code=False)
    receipt = _service().run(request, output_root=tmp_path)

    assert receipt.status == "SOURCE_INCOMPLETE"
    assert receipt.selected_legs == ()
    assert receipt.share_code_result is None
    assert receipt.counts["selected_leg_count"] == 0
    assert receipt.shortfall == request.target_legs
    assert len(child_commands) == 1
    index = child_commands[0].index("--create-share-code")
    assert child_commands[0][index + 1] == "false"
    assert "env" not in child_kwargs[0]
    assert "SHADOW_NO_DELIVERY_RUNTIME_NOT_YET_AVAILABLE" not in receipt.status


def test_shadow_delivery_remains_a_valid_synthetic_compatibility_shape(tmp_path):
    calls = []

    def synthetic_executor(request, *, authority_manifest, **_kwargs):
        calls.append((request, authority_manifest))
        return ExecutorResult(status="SYNTHETIC_SHADOW_DELIVERY_ADMITTED")

    request = _request(profile="SHADOW", create_share_code=True)
    manifest = AthenaRunService.authority_manifest_for(request)
    receipt = _service(synthetic_executor).run(request, output_root=tmp_path)

    assert manifest.provider_acquisition is True
    assert manifest.share_code_generation is True
    _assert_sensitive_capabilities_denied(manifest)
    assert calls == [(request, manifest)]
    assert receipt.status == "SYNTHETIC_SHADOW_DELIVERY_ADMITTED"
    assert receipt.share_code_result is None


def test_unsupported_identity_has_no_capabilities_and_fails_before_executor(tmp_path):
    calls = []
    request = _request(profile="SHADOW", mode="unreviewed_shadow_mode", create_share_code=True)
    manifest = AthenaRunService.authority_manifest_for(request)
    receipt = _service(lambda *_args, **_kwargs: calls.append("executor")).run(
        request, output_root=tmp_path
    )

    assert manifest.provider_acquisition is False
    assert manifest.share_code_generation is False
    _assert_sensitive_capabilities_denied(manifest)
    assert receipt.status == "EXECUTOR_UNAVAILABLE"
    assert receipt.evidence["executor_invoked"] is False
    assert calls == []
