from __future__ import annotations

import datetime as dt
from pathlib import Path
import subprocess
import sys

import pytest

import domain.fotmob_fresh_holdout_continuity as continuity
import scripts.mirror_fotmob_fresh_holdout_release_receipt as mirror
import scripts.run_fotmob_fresh_holdout_release_receipt_mirror as transport


RUN_ID = 32804045592
CONTINUITY_RUN_ID = 456
SOURCE_WATCHDOG_RUN_ID = 123
SHA = "a" * 40
REPOSITORY = "Thabearr/ATHENA"


def _ambiguous_no_acquisition_run() -> dict:
    return {
        "id": RUN_ID,
        "workflow_id": continuity.PRIMARY_WORKFLOW_ID,
        "name": continuity.PRIMARY_SCHEDULE_RUN_NAME,
        "event": "schedule",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "path": mirror.WORKFLOW_PATH,
        "created_at": "2026-08-25T03:08:32Z",
    }


def _ambiguous_no_acquisition_jobs() -> dict:
    expected = {
        "Restore newest durable lineage and resolve schedule slot": "success",
        "Acknowledge ambiguous schedule without acquisition": "success",
        "Restore or materialize PR119 bootstrap projection": "skipped",
        "Execute reviewed fresh-holdout collection tick": "skipped",
        "Reconcile any staged capture lineage": "skipped",
        "Package durable state archive": "skipped",
        "Upload authoritative 90-day Actions artifact": "skipped",
        "Publish and verify long-lived evidence release asset": "skipped",
    }
    return {
        "jobs": [
            {
                "name": "execute fresh holdout tick",
                "status": "completed",
                "conclusion": "success",
                "steps": [
                    {
                        "name": name,
                        "status": "completed",
                        "conclusion": conclusion,
                    }
                    for name, conclusion in expected.items()
                ],
            }
        ]
    }


def _continuity_run() -> dict:
    run_name = (
        "ATHENA fresh-holdout workflow_dispatch "
        f"source={SOURCE_WATCHDOG_RUN_ID} "
        "target=2026-08-29T07:07:00Z "
        "cron=7 * * * * "
        f"confirm={continuity.CONTINUITY_CONFIRMATION}"
    )
    return {
        "id": CONTINUITY_RUN_ID,
        "workflow_id": continuity.PRIMARY_WORKFLOW_ID,
        "name": run_name,
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": SHA,
        "path": mirror.WORKFLOW_PATH,
        "created_at": "2026-08-29T07:07:08Z",
        "display_title": run_name,
    }


def _source_watchdog() -> dict:
    return {
        "id": SOURCE_WATCHDOG_RUN_ID,
        "name": continuity.WATCHDOG_WORKFLOW_NAME,
        "path": continuity.WATCHDOG_WORKFLOW_PATH,
        "event": "schedule",
        "head_branch": "main",
        "head_sha": SHA,
        "created_at": "2026-08-29T07:03:02Z",
        "status": "completed",
        "conclusion": "success",
    }


def _source_watchdog_jobs() -> dict:
    return {
        "jobs": [
            {
                "run_id": SOURCE_WATCHDOG_RUN_ID,
                "workflow_name": continuity.WATCHDOG_WORKFLOW_NAME,
                "name": continuity.WATCHDOG_JOB_NAME,
                "head_branch": "main",
                "head_sha": SHA,
                "status": "completed",
                "conclusion": "success",
                "created_at": "2026-08-29T07:03:04Z",
                "steps": [
                    {
                        "name": name,
                        "status": "completed",
                        "conclusion": "success",
                    }
                    for name in continuity.WATCHDOG_PROSPECTIVE_DISPATCH_REQUIRED_STEPS
                ],
            }
        ]
    }


def test_actions_artifact_zip_uses_github_json_media_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_check_output(command: list[str]) -> bytes:
        calls.append(command)
        return b"zip-bytes"

    monkeypatch.setattr(transport.subprocess, "check_output", fake_check_output)
    endpoint = "/repos/Thabearr/ATHENA/actions/artifacts/9478318255/zip"
    assert transport._reviewed_gh_download(endpoint) == b"zip-bytes"
    assert calls == [
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github+json",
            endpoint,
        ]
    ]


def test_release_asset_download_stays_on_frozen_octet_stream_implementation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def original(endpoint: str) -> bytes:
        calls.append(endpoint)
        return b"release-bytes"

    monkeypatch.setattr(transport, "_ORIGINAL_GH_DOWNLOAD", original)
    endpoint = "/repos/Thabearr/ATHENA/releases/assets/123"
    assert transport._reviewed_gh_download(endpoint) == b"release-bytes"
    assert calls == [endpoint]


def test_actions_artifact_transport_rejects_unreviewed_endpoint_shape() -> None:
    with pytest.raises(
        mirror.FreshHoldoutReleaseReceiptMirrorError,
        match="escaped reviewed ZIP endpoint",
    ):
        transport._reviewed_gh_download(
            "/repos/Thabearr/ATHENA/actions/artifacts/not-an-id/zip"
        )


def test_transport_install_is_idempotent_and_refuses_unknown_hook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mirror, "_gh_download", transport._ORIGINAL_GH_DOWNLOAD)
    transport._install_reviewed_actions_artifact_transport()
    assert mirror._gh_download is transport._reviewed_gh_download
    transport._install_reviewed_actions_artifact_transport()
    assert mirror._gh_download is transport._reviewed_gh_download

    monkeypatch.setattr(mirror, "_gh_download", lambda _endpoint: b"unknown")
    with pytest.raises(
        mirror.FreshHoldoutReleaseReceiptMirrorError,
        match="download hook changed",
    ):
        transport._install_reviewed_actions_artifact_transport()


def test_no_acquisition_install_is_idempotent_and_refuses_unknown_hook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mirror, "mirror_run", transport._ORIGINAL_MIRROR_RUN)
    transport._install_reviewed_no_acquisition_compatibility()
    assert mirror.mirror_run is transport._reviewed_mirror_run
    transport._install_reviewed_no_acquisition_compatibility()
    assert mirror.mirror_run is transport._reviewed_mirror_run

    monkeypatch.setattr(mirror, "mirror_run", lambda **_kwargs: {})
    with pytest.raises(
        mirror.FreshHoldoutReleaseReceiptMirrorError,
        match="run hook changed",
    ):
        transport._install_reviewed_no_acquisition_compatibility()


def test_proven_ambiguous_no_acquisition_run_is_green_no_mirror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _ambiguous_no_acquisition_run()
    artifacts = {"artifacts": []}
    jobs = _ambiguous_no_acquisition_jobs()
    calls: list[str] = []

    def fake_gh_json(endpoint: str) -> dict:
        calls.append(endpoint)
        if endpoint.endswith(f"/actions/runs/{RUN_ID}"):
            return run
        if endpoint.endswith(f"/actions/runs/{RUN_ID}/artifacts"):
            return artifacts
        if endpoint.endswith(f"/actions/runs/{RUN_ID}/jobs?per_page=100"):
            return jobs
        raise AssertionError(endpoint)

    monkeypatch.setattr(mirror, "_gh_json", fake_gh_json)
    monkeypatch.setattr(
        transport,
        "_ORIGINAL_MIRROR_RUN",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("must not mirror")),
    )

    result = transport._reviewed_mirror_run(repository=REPOSITORY, run_id=RUN_ID)

    assert result == {
        "schema_version": 1,
        "run_id": RUN_ID,
        "disposition": "VERIFIED_AMBIGUOUS_NO_ACQUISITION_NO_MIRROR_REQUIRED",
        "actions_artifact_count": 0,
        "receipt_mirror_required": False,
        "release_asset_written": False,
        "provider_network_acquisition_performed": False,
        "model_or_betting_authority_changed": False,
    }
    assert calls == [
        f"/repos/{REPOSITORY}/actions/runs/{RUN_ID}",
        f"/repos/{REPOSITORY}/actions/runs/{RUN_ID}/artifacts",
        f"/repos/{REPOSITORY}/actions/runs/{RUN_ID}/jobs?per_page=100",
    ]


def test_unproven_zero_artifact_success_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _ambiguous_no_acquisition_run()
    jobs = _ambiguous_no_acquisition_jobs()
    for step in jobs["jobs"][0]["steps"]:
        if step["name"] == "Execute reviewed fresh-holdout collection tick":
            step["conclusion"] = "success"

    def fake_gh_json(endpoint: str) -> dict:
        if endpoint.endswith(f"/actions/runs/{RUN_ID}"):
            return run
        if endpoint.endswith(f"/actions/runs/{RUN_ID}/artifacts"):
            return {"artifacts": []}
        if endpoint.endswith(f"/actions/runs/{RUN_ID}/jobs?per_page=100"):
            return jobs
        raise AssertionError(endpoint)

    monkeypatch.setattr(mirror, "_gh_json", fake_gh_json)
    with pytest.raises(
        mirror.FreshHoldoutReleaseReceiptMirrorError,
        match="not a proven reviewed no-acquisition success",
    ):
        transport._reviewed_mirror_run(repository=REPOSITORY, run_id=RUN_ID)


def test_nonempty_scheduled_artifact_run_delegates_to_frozen_mirror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _ambiguous_no_acquisition_run()
    artifact_payload = {"artifacts": [{"name": "canonical-evidence-present"}]}
    expected = {"delegated": True}

    def fake_gh_json(endpoint: str) -> dict:
        if endpoint.endswith(f"/actions/runs/{RUN_ID}"):
            return run
        if endpoint.endswith(f"/actions/runs/{RUN_ID}/artifacts"):
            return artifact_payload
        raise AssertionError(endpoint)

    monkeypatch.setattr(mirror, "_gh_json", fake_gh_json)
    monkeypatch.setattr(
        transport,
        "_ORIGINAL_MIRROR_RUN",
        lambda *, repository, run_id: (
            expected
            if repository == REPOSITORY and run_id == RUN_ID
            else (_ for _ in ()).throw(AssertionError("wrong delegation"))
        ),
    )

    assert transport._reviewed_mirror_run(repository=REPOSITORY, run_id=RUN_ID) == expected


def test_continuity_run_name_and_watchdog_jobs_replay_exact_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _continuity_run()
    source = _source_watchdog()
    jobs = _source_watchdog_jobs()

    def fake_gh_json(endpoint: str) -> dict:
        if endpoint.endswith(f"/actions/runs/{SOURCE_WATCHDOG_RUN_ID}"):
            return source
        if endpoint.endswith(
            f"/actions/runs/{SOURCE_WATCHDOG_RUN_ID}/jobs?per_page=100"
        ):
            return jobs
        raise AssertionError(endpoint)

    monkeypatch.setattr(mirror, "_gh_json", fake_gh_json)
    plan = transport._continuity_plan_from_run(repository=REPOSITORY, run=run)
    assert plan.target_slot == dt.datetime(
        2026, 8, 29, 7, 7, tzinfo=dt.timezone.utc
    )
    assert plan.target_cron == "7 * * * *"


def test_continuity_source_step_drift_fails_before_mirror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _continuity_run()
    jobs = _source_watchdog_jobs()
    for step in jobs["jobs"][0]["steps"]:
        if step["name"] == "Record prospective continuity dispatch request":
            step["conclusion"] = "skipped"

    def fake_gh_json(endpoint: str) -> dict:
        if endpoint.endswith(f"/actions/runs/{SOURCE_WATCHDOG_RUN_ID}"):
            return _source_watchdog()
        if endpoint.endswith(
            f"/actions/runs/{SOURCE_WATCHDOG_RUN_ID}/jobs?per_page=100"
        ):
            return jobs
        raise AssertionError(endpoint)

    monkeypatch.setattr(mirror, "_gh_json", fake_gh_json)
    with pytest.raises(
        mirror.FreshHoldoutReleaseReceiptMirrorError,
        match="continuity workflow_dispatch provenance replay failed",
    ):
        transport._continuity_plan_from_run(repository=REPOSITORY, run=run)


def test_unreviewed_continuity_run_name_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = {**_continuity_run(), "display_title": "manual dispatch"}
    monkeypatch.setattr(
        mirror,
        "_gh_json",
        lambda endpoint: (_ for _ in ()).throw(AssertionError(endpoint)),
    )
    with pytest.raises(
        mirror.FreshHoldoutReleaseReceiptMirrorError,
        match="run-name escaped reviewed provenance grammar",
    ):
        transport._continuity_plan_from_run(repository=REPOSITORY, run=run)


def test_nonempty_continuity_artifact_uses_source_replayed_mirror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _continuity_run()
    artifact_payload = {"artifacts": [{"name": "canonical-evidence-present"}]}
    plan = continuity.plan_from_watchdog_created_at("2026-08-29T07:03:02Z")
    expected = {"continuity_mirrored": True}

    def fake_gh_json(endpoint: str) -> dict:
        if endpoint.endswith(f"/actions/runs/{CONTINUITY_RUN_ID}"):
            return run
        if endpoint.endswith(f"/actions/runs/{CONTINUITY_RUN_ID}/artifacts"):
            return artifact_payload
        raise AssertionError(endpoint)

    monkeypatch.setattr(mirror, "_gh_json", fake_gh_json)
    monkeypatch.setattr(
        transport,
        "_continuity_plan_from_run",
        lambda *, repository, run: plan,
    )
    monkeypatch.setattr(
        transport,
        "_mirror_continuity_artifact",
        lambda *, repository, run_id, artifacts, plan: expected,
    )
    monkeypatch.setattr(
        transport,
        "_ORIGINAL_MIRROR_RUN",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("continuity must not delegate to schedule-only frozen entrypoint")
        ),
    )

    assert (
        transport._reviewed_mirror_run(
            repository=REPOSITORY,
            run_id=CONTINUITY_RUN_ID,
        )
        == expected
    )


def test_transport_module_entrypoint_imports_from_repo_root() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.run_fotmob_fresh_holdout_release_receipt_mirror",
            "--help",
        ],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--repository" in result.stdout
    assert "--run-id" in result.stdout


def test_workflow_pins_and_invokes_reviewed_transport_after_reviewed_success() -> None:
    workflow = Path(
        ".github/workflows/fotmob-utc-native-xg-fresh-holdout-release-receipts.yml"
    ).read_text(encoding="utf-8")
    assert "ddabb6ae83cbe6c81c9264119a121a54715df960" in workflow
    assert "1752fd5b96823f8b52e99a2dbbf84250676809d8" in workflow
    assert "6d768a506d579ef88f1d321102cb9c53d846c72a" in workflow
    assert "9e09e13d145f9ad2419b11073d4219aec14e54a8" in workflow
    assert (
        "python -m scripts.run_fotmob_fresh_holdout_release_receipt_mirror" in workflow
    )
    assert "python scripts/run_fotmob_fresh_holdout_release_receipt_mirror.py" not in workflow
    assert "Accept: application/octet-stream" not in workflow
    assert "github.event.workflow_run.event == 'schedule'" in workflow
    assert "github.event.workflow_run.event == 'workflow_dispatch'" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
