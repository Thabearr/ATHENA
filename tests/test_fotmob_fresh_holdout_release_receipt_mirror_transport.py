from __future__ import annotations

import datetime as dt
import hashlib
import json
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
OLD_TRANSPORT_BLOB = "f0b836304b1d46877e0396ea7a532c24b46a3d16"
OLD_TRANSPORT_SHA256 = "f103367791d26c59607569e286602d7d7c61ade407148b11326c38831588cc5f"
ARCHIVE_NAME = "success-20260923T100700Z-run-35847067175.tar.gz"
RECEIPT_NAME = f"{ARCHIVE_NAME}.receipt.json"
ARCHIVE_BYTES = b"exact durable archive bytes"
RECEIPT_BYTES = b'{"canonical":true}\n'


def _verified_bundle() -> dict:
    return {
        "artifact_name": ARCHIVE_NAME,
        "receipt_name": RECEIPT_NAME,
        "archive_size_bytes": len(ARCHIVE_BYTES),
        "archive_sha256": hashlib.sha256(ARCHIVE_BYTES).hexdigest(),
        "archive_bytes": ARCHIVE_BYTES,
        "receipt_size_bytes": len(RECEIPT_BYTES),
        "receipt_sha256": hashlib.sha256(RECEIPT_BYTES).hexdigest(),
        "receipt_bytes": RECEIPT_BYTES,
        "run_id": 35847067175,
        "actions_artifact_zip_sha256": "b" * 64,
        "release_tag": "athena-fresh-holdout-evidence-2026-W39",
    }


def _asset(name: str, raw: bytes, asset_id: int, **overrides: object) -> dict:
    return {
        "name": name,
        "state": "uploaded",
        "size": len(raw),
        "id": asset_id,
        **overrides,
    }


def _release(*, receipt: bytes | None = RECEIPT_BYTES, **archive_overrides: object) -> dict:
    assets = [_asset(ARCHIVE_NAME, ARCHIVE_BYTES, 1, **archive_overrides)]
    if receipt is not None:
        assets.append(_asset(RECEIPT_NAME, receipt, 2))
    return {"assets": assets}


def _verify_with_release(
    monkeypatch: pytest.MonkeyPatch,
    *,
    initial: dict,
    reload_release,
    upload_receipt=lambda _name, _raw: None,
    download_bytes: dict[int, bytes] | None = None,
) -> dict:
    monkeypatch.setattr(
        transport,
        "_ORIGINAL_VERIFY_RELEASE_ARCHIVE_AND_RECEIPT",
        mirror.verify_release_archive_and_receipt,
    )
    return transport._reviewed_verify_release_archive_and_receipt(
        verified=_verified_bundle(),
        release=initial,
        download_release_asset=lambda asset_id: (download_bytes or {1: ARCHIVE_BYTES, 2: RECEIPT_BYTES})[asset_id],
        upload_receipt=upload_receipt,
        reload_release=reload_release,
    )


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
    assert "0f880bfb161d2dd9547326611505a066019b7f06" in workflow
    assert "ac8ba91b8f3e1086f01d35f3ca6d6aa356417623" in workflow
    assert "3f19559205ddf24de8140d456dd8af0d3c15ccee" in workflow
    assert (
        "python -m scripts.run_fotmob_fresh_holdout_release_receipt_mirror" in workflow
    )
    assert "python scripts/run_fotmob_fresh_holdout_release_receipt_mirror.py" not in workflow
    assert "Accept: application/octet-stream" not in workflow
    assert "github.event.workflow_run.event == 'schedule'" in workflow
    assert "github.event.workflow_run.event == 'workflow_dispatch'" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow


def test_visibility_retry_budget_is_exactly_31_attempts_at_two_seconds() -> None:
    assert transport.RELEASE_ASSET_VISIBILITY_ATTEMPTS == 31
    assert transport.RELEASE_ASSET_VISIBILITY_INTERVAL_SECONDS == 2


def test_previous_transport_fixture_is_exact_historical_bytes() -> None:
    fixture = Path(
        "tests/fixtures/architecture/revised_modules/"
        "run_fotmob_fresh_holdout_release_receipt_mirror-pre-visibility-race-fix.py"
    ).read_bytes()
    git_blob = hashlib.sha1(b"blob " + str(len(fixture)).encode("ascii") + b"\0" + fixture).hexdigest()
    assert git_blob == OLD_TRANSPORT_BLOB
    assert hashlib.sha256(fixture).hexdigest() == OLD_TRANSPORT_SHA256


def test_archive_visible_in_initial_view_has_no_sleep_or_reload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    reloads: list[int] = []
    result = _verify_with_release(
        monkeypatch,
        initial=_release(),
        reload_release=lambda: reloads.append(1) or _release(),
    )
    assert result["release_archive_exact_bytes_verified"] is True
    assert sleeps == []
    assert reloads == []


def test_archive_visible_after_first_metadata_reload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reloads: list[int] = []
    monkeypatch.setattr(transport.time, "sleep", lambda _seconds: None)
    result = _verify_with_release(
        monkeypatch,
        initial={"assets": []},
        reload_release=lambda: reloads.append(1) or _release(),
    )
    assert result["archive_name"] == ARCHIVE_NAME
    assert len(reloads) == 1


def test_archive_visible_on_final_attempt_uses_30_sleeps_and_reloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []
    sleeps: list[float] = []

    def reload_release() -> dict:
        attempts.append(1)
        return _release() if len(attempts) == 30 else {"assets": []}

    monkeypatch.setattr(transport.time, "sleep", lambda seconds: sleeps.append(seconds))
    result = _verify_with_release(
        monkeypatch,
        initial={"assets": []},
        reload_release=reload_release,
    )
    assert result["archive_name"] == ARCHIVE_NAME
    assert len(attempts) == len(sleeps) == 30
    assert set(sleeps) == {2}


def test_archive_never_visible_fails_after_bounded_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reloads: list[int] = []
    sleeps: list[float] = []
    monkeypatch.setattr(transport.time, "sleep", lambda seconds: sleeps.append(seconds))
    with pytest.raises(transport.ReleaseAssetVisibilityTimeout, match="archive release asset"):
        transport._reviewed_verify_release_archive_and_receipt(
            verified=_verified_bundle(),
            release={"assets": []},
            download_release_asset=lambda _asset_id: ARCHIVE_BYTES,
            upload_receipt=lambda _name, _raw: None,
            reload_release=lambda: reloads.append(1) or {"assets": []},
        )
    assert len(reloads) == len(sleeps) == 30


def test_duplicate_archive_and_malformed_release_fail_without_retry() -> None:
    duplicate = _release(receipt=None)
    duplicate["assets"].append(_asset(ARCHIVE_NAME, ARCHIVE_BYTES, 3))
    with pytest.raises(mirror.FreshHoldoutReleaseReceiptMirrorError, match="duplicate asset name"):
        transport._wait_for_release_asset_visibility(
            initial_release=duplicate,
            asset_name=ARCHIVE_NAME,
            reload_release=lambda: pytest.fail("duplicate must not retry"),
            sleep_fn=lambda _seconds: pytest.fail("duplicate must not sleep"),
            attempts=31,
            interval_seconds=2,
            label="archive",
        )
    with pytest.raises(mirror.FreshHoldoutReleaseReceiptMirrorError, match="malformed"):
        transport._wait_for_release_asset_visibility(
            initial_release={"assets": [None]},
            asset_name=ARCHIVE_NAME,
            reload_release=lambda: pytest.fail("malformed must not retry"),
            sleep_fn=lambda _seconds: pytest.fail("malformed must not sleep"),
            attempts=31,
            interval_seconds=2,
            label="archive",
        )


@pytest.mark.parametrize(
    ("release", "download_bytes", "message"),
    [
        (_release(state="processing"), None, "not uploaded"),
        (_release(size=1), None, "size changed"),
        (_release(), {1: b"x" * len(ARCHIVE_BYTES), 2: RECEIPT_BYTES}, "SHA-256 disagrees"),
    ],
)
def test_visible_archive_integrity_mismatch_fails_immediately(
    monkeypatch: pytest.MonkeyPatch,
    release: dict,
    download_bytes: dict[int, bytes] | None,
    message: str,
) -> None:
    reloads: list[int] = []
    monkeypatch.setattr(transport.time, "sleep", lambda _seconds: pytest.fail("integrity mismatch retried"))
    with pytest.raises(mirror.FreshHoldoutReleaseReceiptMirrorError, match=message):
        _verify_with_release(
            monkeypatch,
            initial=release,
            reload_release=lambda: reloads.append(1) or _release(),
            download_bytes=download_bytes,
        )
    assert reloads == []


def test_exact_existing_receipt_does_not_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uploads: list[tuple[str, bytes]] = []
    result = _verify_with_release(
        monkeypatch,
        initial=_release(),
        reload_release=lambda: pytest.fail("existing receipt requires no reload"),
        upload_receipt=lambda name, raw: uploads.append((name, raw)),
    )
    assert result["release_receipt_exact_bytes_verified"] is True
    assert uploads == []


def test_uploaded_receipt_delayed_visibility_recovers_without_second_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    views = [{"assets": [_asset(ARCHIVE_NAME, ARCHIVE_BYTES, 1)]}, _release()]
    reloads: list[int] = []
    uploads: list[tuple[str, bytes]] = []
    sleeps: list[float] = []
    monkeypatch.setattr(transport.time, "sleep", lambda seconds: sleeps.append(seconds))
    result = _verify_with_release(
        monkeypatch,
        initial=views[0],
        reload_release=lambda: reloads.append(1) or views.pop(0),
        upload_receipt=lambda name, raw: uploads.append((name, raw)),
    )
    assert result["release_receipt_exact_bytes_verified"] is True
    assert uploads == [(RECEIPT_NAME, RECEIPT_BYTES)]
    assert len(reloads) == 2  # frozen post-upload reload, then visibility reload
    assert sleeps == [2]


def test_uploaded_receipt_never_visible_fails_after_bounded_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uploads: list[int] = []
    reloads: list[int] = []
    sleeps: list[float] = []
    archive_only = {"assets": [_asset(ARCHIVE_NAME, ARCHIVE_BYTES, 1)]}
    monkeypatch.setattr(transport.time, "sleep", lambda seconds: sleeps.append(seconds))
    with pytest.raises(transport.ReleaseAssetVisibilityTimeout, match="receipt release asset"):
        _verify_with_release(
            monkeypatch,
            initial=archive_only,
            reload_release=lambda: reloads.append(1) or archive_only,
            upload_receipt=lambda _name, _raw: uploads.append(1),
        )
    assert len(uploads) == 1
    assert len(reloads) == 31  # one frozen reload plus 30 reviewed polls
    assert len(sleeps) == 30


def test_failed_upload_collision_recovers_only_after_exact_receipt_appears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_only = {"assets": [_asset(ARCHIVE_NAME, ARCHIVE_BYTES, 1)]}
    views = [_release()]
    uploads: list[int] = []
    result = _verify_with_release(
        monkeypatch,
        initial=archive_only,
        reload_release=lambda: views.pop(0),
        upload_receipt=lambda _name, _raw: (
            uploads.append(1)
            or (_ for _ in ()).throw(
                mirror.FreshHoldoutReleaseReceiptMirrorError("GitHub release receipt upload failed")
            )
        ),
    )
    assert result["release_receipt_exact_bytes_verified"] is True
    assert uploads == [1]


def test_failed_upload_without_visible_receipt_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_only = {"assets": [_asset(ARCHIVE_NAME, ARCHIVE_BYTES, 1)]}
    uploads: list[int] = []
    reloads: list[int] = []
    monkeypatch.setattr(transport.time, "sleep", lambda _seconds: None)
    with pytest.raises(transport.ReleaseAssetVisibilityTimeout, match="receipt release asset"):
        _verify_with_release(
            monkeypatch,
            initial=archive_only,
            reload_release=lambda: reloads.append(1) or archive_only,
            upload_receipt=lambda _name, _raw: (
                uploads.append(1)
                or (_ for _ in ()).throw(
                    mirror.FreshHoldoutReleaseReceiptMirrorError("GitHub release receipt upload failed")
                )
            ),
        )
    assert uploads == [1]
    assert len(reloads) == 30


@pytest.mark.parametrize(
    ("receipt_raw", "receipt_size", "message"),
    [(RECEIPT_BYTES, 1, "size changed"), (b"wrong receipt", len(RECEIPT_BYTES), "bytes differ")],
)
def test_concurrent_receipt_collision_requires_exact_bytes_and_size(
    monkeypatch: pytest.MonkeyPatch,
    receipt_raw: bytes,
    receipt_size: int,
    message: str,
) -> None:
    archive_only = {"assets": [_asset(ARCHIVE_NAME, ARCHIVE_BYTES, 1)]}
    wrong_receipt_release = {
        "assets": [
            _asset(ARCHIVE_NAME, ARCHIVE_BYTES, 1),
            _asset(RECEIPT_NAME, receipt_raw, 2, size=receipt_size),
        ]
    }
    with pytest.raises(mirror.FreshHoldoutReleaseReceiptMirrorError, match=message):
        _verify_with_release(
            monkeypatch,
            initial=archive_only,
            reload_release=lambda: wrong_receipt_release,
            download_bytes={1: ARCHIVE_BYTES, 2: receipt_raw},
            upload_receipt=lambda _name, _raw: (_ for _ in ()).throw(
                mirror.FreshHoldoutReleaseReceiptMirrorError("GitHub release receipt upload failed")
            ),
        )


def test_duplicate_receipt_name_fails_immediately_after_upload_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duplicate = _release()
    duplicate["assets"].append(_asset(RECEIPT_NAME, RECEIPT_BYTES, 3))
    archive_only = {"assets": [_asset(ARCHIVE_NAME, ARCHIVE_BYTES, 1)]}
    with pytest.raises(mirror.FreshHoldoutReleaseReceiptMirrorError, match="duplicate asset name"):
        _verify_with_release(
            monkeypatch,
            initial=archive_only,
            reload_release=lambda: duplicate,
            upload_receipt=lambda _name, _raw: (_ for _ in ()).throw(
                mirror.FreshHoldoutReleaseReceiptMirrorError("GitHub release receipt upload failed")
            ),
        )


def test_visibility_helper_rejects_invalid_budgets_and_reload_errors() -> None:
    with pytest.raises(mirror.FreshHoldoutReleaseReceiptMirrorError, match="positive integer"):
        transport._wait_for_release_asset_visibility(
            initial_release={"assets": []}, asset_name=ARCHIVE_NAME,
            reload_release=lambda: {"assets": []}, sleep_fn=lambda _seconds: None,
            attempts=True, interval_seconds=2, label="archive",
        )
    with pytest.raises(mirror.FreshHoldoutReleaseReceiptMirrorError, match="non-negative number"):
        transport._wait_for_release_asset_visibility(
            initial_release={"assets": []}, asset_name=ARCHIVE_NAME,
            reload_release=lambda: {"assets": []}, sleep_fn=lambda _seconds: None,
            attempts=1, interval_seconds=float("nan"), label="archive",
        )
    with pytest.raises(mirror.FreshHoldoutReleaseReceiptMirrorError, match="reload failed"):
        transport._wait_for_release_asset_visibility(
            initial_release={"assets": []}, asset_name=ARCHIVE_NAME,
            reload_release=lambda: (_ for _ in ()).throw(RuntimeError("offline")),
            sleep_fn=lambda _seconds: None, attempts=2, interval_seconds=0,
            label="archive",
        )


def test_visibility_hook_install_is_idempotent_and_rejects_unknown_hook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mirror,
        "verify_release_archive_and_receipt",
        transport._ORIGINAL_VERIFY_RELEASE_ARCHIVE_AND_RECEIPT,
    )
    transport._install_reviewed_release_visibility_retry()
    assert mirror.verify_release_archive_and_receipt is transport._reviewed_verify_release_archive_and_receipt
    transport._install_reviewed_release_visibility_retry()
    assert mirror.verify_release_archive_and_receipt is transport._reviewed_verify_release_archive_and_receipt
    monkeypatch.setattr(mirror, "verify_release_archive_and_receipt", lambda **_kwargs: {})
    with pytest.raises(mirror.FreshHoldoutReleaseReceiptMirrorError, match="verifier hook changed"):
        transport._install_reviewed_release_visibility_retry()


def test_scheduled_nonempty_lane_uses_installed_visibility_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mirror, "verify_release_archive_and_receipt", transport._ORIGINAL_VERIFY_RELEASE_ARCHIVE_AND_RECEIPT)
    calls: list[int] = []
    frozen = transport._ORIGINAL_VERIFY_RELEASE_ARCHIVE_AND_RECEIPT

    def spy(**kwargs):
        calls.append(1)
        return frozen(**kwargs)

    monkeypatch.setattr(transport.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(mirror, "_gh_json", lambda endpoint: (
        _ambiguous_no_acquisition_run() if endpoint.endswith(f"/actions/runs/{RUN_ID}")
        else {"artifacts": [{"name": "has-evidence"}]}
    ))
    monkeypatch.setattr(
        transport,
        "_ORIGINAL_MIRROR_RUN",
        lambda **_kwargs: mirror.verify_release_archive_and_receipt(
            verified=_verified_bundle(), release=_release(),
            download_release_asset=lambda asset_id: {1: ARCHIVE_BYTES, 2: RECEIPT_BYTES}[asset_id],
            upload_receipt=lambda _name, _raw: None,
            reload_release=lambda: _release(),
        ),
    )
    transport._install_reviewed_release_visibility_retry()
    monkeypatch.setattr(transport, "_ORIGINAL_VERIFY_RELEASE_ARCHIVE_AND_RECEIPT", spy)
    result = transport._reviewed_mirror_run(repository=REPOSITORY, run_id=RUN_ID)
    assert result["release_archive_exact_bytes_verified"] is True
    assert calls == [1]


def test_continuity_artifact_lane_installs_and_uses_visibility_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mirror, "verify_release_archive_and_receipt", transport._ORIGINAL_VERIFY_RELEASE_ARCHIVE_AND_RECEIPT)
    frozen = transport._ORIGINAL_VERIFY_RELEASE_ARCHIVE_AND_RECEIPT
    calls: list[int] = []

    def spy(**kwargs):
        calls.append(1)
        return frozen(**kwargs)

    receipt = mirror._canonical_json({
        "workflow_event_schedule": "7 * * * *",
        "nominal_scheduled_for_utc": "2026-08-29T07:07:00Z",
    })
    verified = {
        **_verified_bundle(),
        "receipt_bytes": receipt,
        "receipt_size_bytes": len(receipt),
        "receipt_sha256": hashlib.sha256(receipt).hexdigest(),
    }
    monkeypatch.setattr(transport, "_reviewed_gh_download", lambda _endpoint: b"zip bytes")
    monkeypatch.setattr(mirror, "verify_actions_artifact_zip_digest", lambda *_args: "c" * 64)
    monkeypatch.setattr(mirror, "verify_actions_artifact_bundle", lambda **_kwargs: dict(verified))
    monkeypatch.setattr(mirror, "_release_for", lambda *_args: _release(receipt=receipt))
    monkeypatch.setattr(
        transport,
        "_ORIGINAL_GH_DOWNLOAD",
        lambda endpoint: {"/releases/assets/1": ARCHIVE_BYTES, "/releases/assets/2": receipt}[endpoint.split("/repos/Thabearr/ATHENA")[1]],
    )
    monkeypatch.setattr(transport.time, "sleep", lambda _seconds: None)
    transport._install_reviewed_release_visibility_retry()
    monkeypatch.setattr(transport, "_ORIGINAL_VERIFY_RELEASE_ARCHIVE_AND_RECEIPT", spy)
    result = transport._mirror_continuity_artifact(
        repository=REPOSITORY,
        run_id=35847067175,
        artifacts={"artifacts": [{"id": 7, "name": ARCHIVE_NAME, "expired": False, "digest": "sha256:" + "c" * 64}]},
        plan=continuity.plan_from_watchdog_created_at("2026-08-29T07:03:02Z"),
    )
    assert result["continuity_provenance_replayed"] is True
    assert result["release_receipt_exact_bytes_verified"] is True
    assert calls == [1]
    assert mirror.verify_release_archive_and_receipt is transport._reviewed_verify_release_archive_and_receipt
