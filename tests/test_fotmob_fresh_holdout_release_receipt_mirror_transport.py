from __future__ import annotations

from pathlib import Path

import pytest

import scripts.mirror_fotmob_fresh_holdout_release_receipt as mirror
import scripts.run_fotmob_fresh_holdout_release_receipt_mirror as transport


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


def test_workflow_pins_and_invokes_reviewed_transport() -> None:
    workflow = Path(
        ".github/workflows/fotmob-utc-native-xg-fresh-holdout-release-receipts.yml"
    ).read_text(encoding="utf-8")
    assert "ddabb6ae83cbe6c81c9264119a121a54715df960" in workflow
    assert "a9e6414288e98e9788b987aa9dd10ac35cc2d4cc" in workflow
    assert "python scripts/run_fotmob_fresh_holdout_release_receipt_mirror.py" in workflow
    assert "Accept: application/octet-stream" not in workflow
