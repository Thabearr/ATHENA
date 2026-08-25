from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

import scripts.mirror_fotmob_fresh_holdout_release_receipt as mirror
import scripts.run_fotmob_fresh_holdout_release_receipt_mirror as transport


RUN_ID = 32804045592
REPOSITORY = "Thabearr/ATHENA"


def _ambiguous_no_acquisition_run() -> dict:
    return {
        "id": RUN_ID,
        "name": mirror.WORKFLOW_NAME,
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
        match="not a proven ambiguous no-acquisition success",
    ):
        transport._reviewed_mirror_run(repository=REPOSITORY, run_id=RUN_ID)


def test_nonempty_artifact_run_delegates_to_frozen_mirror(
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


def test_workflow_pins_and_invokes_reviewed_transport_only_after_success() -> None:
    workflow = Path(
        ".github/workflows/fotmob-utc-native-xg-fresh-holdout-release-receipts.yml"
    ).read_text(encoding="utf-8")
    assert "ddabb6ae83cbe6c81c9264119a121a54715df960" in workflow
    assert "69166bf26c32f2385c9b26d651292754dae85be0" in workflow
    assert (
        "python -m scripts.run_fotmob_fresh_holdout_release_receipt_mirror" in workflow
    )
    assert "python scripts/run_fotmob_fresh_holdout_release_receipt_mirror.py" not in workflow
    assert "Accept: application/octet-stream" not in workflow
    assert (
        "github.event.workflow_run.event == 'schedule' && "
        "github.event.workflow_run.conclusion == 'success'"
    ) in workflow
