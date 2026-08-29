from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest

import scripts.mirror_fotmob_fresh_holdout_release_receipt as mirror


RUN_ID = 32199999999
ARCHIVE_NAME = f"success-20260819T000700Z-run-{RUN_ID}.tar.gz"
TAG = "athena-fresh-holdout-evidence-2026-W34"
ARCHIVE = b"reviewed-cumulative-state-archive\x00bytes"


def _canonical(value: dict) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _receipt(*, archive: bytes = ARCHIVE, exit_code: int = 0, committed: bool = True) -> bytes:
    return _canonical(
        {
            "durable_asset_name": ARCHIVE_NAME,
            "durable_asset_sha256": hashlib.sha256(archive).hexdigest(),
            "durable_asset_size_bytes": len(archive),
            "durable_release_tag": TAG,
            "failure_lineage_reconcile_outcome": "skipped",
            "nominal_scheduled_for_utc": "2026-08-19T00:07:00+00:00",
            "tick_committed": committed,
            "tick_exit_code": exit_code,
            "workflow_event_schedule": "7 * * * *",
            "workflow_run_id": RUN_ID,
        }
    )


def _artifact_zip(*, archive: bytes = ARCHIVE, receipt: bytes | None = None) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as value:
        value.writestr(ARCHIVE_NAME, archive)
        value.writestr(mirror.RECEIPT_MEMBER, _receipt(archive=archive) if receipt is None else receipt)
    return output.getvalue()


def _verified() -> dict:
    zip_bytes = _artifact_zip()
    digest = mirror.verify_actions_artifact_zip_digest(
        zip_bytes,
        f"sha256:{hashlib.sha256(zip_bytes).hexdigest()}",
    )
    result = mirror.verify_actions_artifact_bundle(
        run_id=RUN_ID,
        artifact_name=ARCHIVE_NAME,
        zip_bytes=zip_bytes,
    )
    result["actions_artifact_zip_sha256"] = digest
    return result


def test_actions_artifact_zip_is_bound_to_github_digest_metadata() -> None:
    zip_bytes = _artifact_zip()
    expected = hashlib.sha256(zip_bytes).hexdigest()
    assert (
        mirror.verify_actions_artifact_zip_digest(zip_bytes, f"sha256:{expected}")
        == expected
    )
    with pytest.raises(
        mirror.FreshHoldoutReleaseReceiptMirrorError,
        match="GitHub digest metadata",
    ):
        mirror.verify_actions_artifact_zip_digest(
            zip_bytes,
            "sha256:" + "0" * 64,
        )
    with pytest.raises(
        mirror.FreshHoldoutReleaseReceiptMirrorError,
        match="lacks SHA-256 digest",
    ):
        mirror.verify_actions_artifact_zip_digest(zip_bytes, None)


def test_actions_bundle_binds_exact_archive_receipt_and_run() -> None:
    result = _verified()
    assert result["run_id"] == RUN_ID
    assert result["release_tag"] == TAG
    assert result["archive_sha256"] == hashlib.sha256(ARCHIVE).hexdigest()
    assert result["receipt_name"] == f"{ARCHIVE_NAME}.receipt.json"
    assert result["archive_bytes"] == ARCHIVE
    assert result["receipt_bytes"] == _receipt()


def test_tampered_archive_is_rejected_by_receipt_digest() -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as value:
        value.writestr(ARCHIVE_NAME, ARCHIVE + b"tamper")
        value.writestr(mirror.RECEIPT_MEMBER, _receipt())
    with pytest.raises(
        mirror.FreshHoldoutReleaseReceiptMirrorError,
        match="receipt SHA-256",
    ):
        mirror.verify_actions_artifact_bundle(
            run_id=RUN_ID,
            artifact_name=ARCHIVE_NAME,
            zip_bytes=output.getvalue(),
        )


def test_noncanonical_receipt_is_rejected() -> None:
    parsed = json.loads(_receipt())
    noncanonical = json.dumps(parsed, indent=2).encode("utf-8") + b"\n"
    with pytest.raises(
        mirror.FreshHoldoutReleaseReceiptMirrorError,
        match="not canonical",
    ):
        mirror.verify_actions_artifact_bundle(
            run_id=RUN_ID,
            artifact_name=ARCHIVE_NAME,
            zip_bytes=_artifact_zip(receipt=noncanonical),
        )


def test_artifact_name_must_bind_exact_run() -> None:
    with pytest.raises(
        mirror.FreshHoldoutReleaseReceiptMirrorError,
        match="exact workflow run",
    ):
        mirror.verify_actions_artifact_bundle(
            run_id=RUN_ID + 1,
            artifact_name=ARCHIVE_NAME,
            zip_bytes=_artifact_zip(),
        )


def test_success_archive_requires_zero_exit_committed_tick() -> None:
    with pytest.raises(
        mirror.FreshHoldoutReleaseReceiptMirrorError,
        match="committed zero-exit",
    ):
        mirror.verify_actions_artifact_bundle(
            run_id=RUN_ID,
            artifact_name=ARCHIVE_NAME,
            zip_bytes=_artifact_zip(receipt=_receipt(exit_code=1, committed=False)),
        )


def test_release_verification_uploads_and_rechecks_exact_receipt() -> None:
    verified = _verified()
    archive_asset = {
        "id": 101,
        "name": ARCHIVE_NAME,
        "state": "uploaded",
        "size": len(ARCHIVE),
    }
    receipt_asset = {
        "id": 102,
        "name": verified["receipt_name"],
        "state": "uploaded",
        "size": len(verified["receipt_bytes"]),
    }
    release_before = {"assets": [archive_asset]}
    release_after = {"assets": [archive_asset, receipt_asset]}
    uploaded: list[tuple[str, bytes]] = []

    def download(asset_id: int) -> bytes:
        if asset_id == 101:
            return ARCHIVE
        if asset_id == 102:
            return verified["receipt_bytes"]
        raise AssertionError(asset_id)

    result = mirror.verify_release_archive_and_receipt(
        verified=verified,
        release=release_before,
        download_release_asset=download,
        upload_receipt=lambda name, raw: uploaded.append((name, raw)),
        reload_release=lambda: release_after,
    )
    assert uploaded == [(verified["receipt_name"], verified["receipt_bytes"])]
    assert result["actions_artifact_zip_sha256"] == verified["actions_artifact_zip_sha256"]
    assert result["release_archive_exact_bytes_verified"] is True
    assert result["release_receipt_exact_bytes_verified"] is True
    assert result["provider_network_acquisition_performed"] is False
    assert result["model_or_betting_authority_changed"] is False


def test_existing_identical_release_receipt_is_idempotent() -> None:
    verified = _verified()
    release = {
        "assets": [
            {"id": 101, "name": ARCHIVE_NAME, "state": "uploaded", "size": len(ARCHIVE)},
            {
                "id": 102,
                "name": verified["receipt_name"],
                "state": "uploaded",
                "size": len(verified["receipt_bytes"]),
            },
        ]
    }
    uploads: list[tuple[str, bytes]] = []
    mirror.verify_release_archive_and_receipt(
        verified=verified,
        release=release,
        download_release_asset=lambda asset_id: (
            ARCHIVE if asset_id == 101 else verified["receipt_bytes"]
        ),
        upload_receipt=lambda name, raw: uploads.append((name, raw)),
        reload_release=lambda: release,
    )
    assert uploads == []


def test_release_archive_digest_mismatch_fails_before_receipt_upload() -> None:
    verified = _verified()
    release = {
        "assets": [
            {"id": 101, "name": ARCHIVE_NAME, "state": "uploaded", "size": len(ARCHIVE)}
        ]
    }
    uploads: list[tuple[str, bytes]] = []
    with pytest.raises(
        mirror.FreshHoldoutReleaseReceiptMirrorError,
        match="SHA-256",
    ):
        mirror.verify_release_archive_and_receipt(
            verified=verified,
            release=release,
            download_release_asset=lambda _asset_id: b"X" * len(ARCHIVE),
            upload_receipt=lambda name, raw: uploads.append((name, raw)),
            reload_release=lambda: release,
        )
    assert uploads == []


def test_release_receipt_mismatch_fails_closed() -> None:
    verified = _verified()
    release = {
        "assets": [
            {"id": 101, "name": ARCHIVE_NAME, "state": "uploaded", "size": len(ARCHIVE)},
            {
                "id": 102,
                "name": verified["receipt_name"],
                "state": "uploaded",
                "size": len(verified["receipt_bytes"]),
            },
        ]
    }
    with pytest.raises(
        mirror.FreshHoldoutReleaseReceiptMirrorError,
        match="receipt bytes differ",
    ):
        mirror.verify_release_archive_and_receipt(
            verified=verified,
            release=release,
            download_release_asset=lambda asset_id: (
                ARCHIVE if asset_id == 101 else b"X" * len(verified["receipt_bytes"])
            ),
            upload_receipt=lambda _name, _raw: None,
            reload_release=lambda: release,
        )


def test_workflow_is_post_run_only_and_pins_implementation_blob() -> None:
    workflow = Path(
        ".github/workflows/fotmob-utc-native-xg-fresh-holdout-release-receipts.yml"
    ).read_text(encoding="utf-8")
    assert "workflow_run:" in workflow
    assert "\n  workflow_dispatch:\n" not in workflow
    assert "github.event.workflow_run.event == 'workflow_dispatch'" in workflow
    assert "schedule:" not in workflow
    assert mirror.WORKFLOW_NAME in workflow
    assert "ddabb6ae83cbe6c81c9264119a121a54715df960" in workflow
    assert "actions: read" in workflow
    assert "contents: write" in workflow
    assert "provider" not in workflow.lower()
