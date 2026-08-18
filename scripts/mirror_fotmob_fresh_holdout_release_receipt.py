"""Mirror and verify long-lived receipts for fresh-holdout release archives.

This script never contacts FotMob. It runs only against GitHub repository metadata and
bytes already emitted by the reviewed scheduled fresh-holdout workflow. Its purpose is
to preserve a canonical SHA-256 commitment beside each long-lived release archive so
source replay remains independently checkable after the 90-day Actions artifact expires.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from typing import Any, Callable
import zipfile


WORKFLOW_NAME = "FotMob UTC-Native xG Fresh-Holdout Collection Runner"
WORKFLOW_PATH = ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
RECEIPT_MEMBER = "fresh-holdout-tick-receipt.json"
ARTIFACT_RE = re.compile(r"^(success|failure)-(\d{8}T\d{6}Z)-run-(\d+)\.tar\.gz$")
RELEASE_TAG_RE = re.compile(r"^athena-fresh-holdout-evidence-\d{4}-W\d{2}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class FreshHoldoutReleaseReceiptMirrorError(RuntimeError):
    """Raised when a long-lived evidence receipt cannot be proven exactly."""


def _error(message: str) -> FreshHoldoutReleaseReceiptMirrorError:
    return FreshHoldoutReleaseReceiptMirrorError(message)


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise _error(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _canonical_json(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("canonical JSON serialization failed") from exc


def _parse_canonical_json(raw: bytes, label: str) -> dict[str, Any]:
    if type(raw) is not bytes or not raw:
        raise _error(f"{label} must be non-empty exact bytes")
    try:
        value = json.loads(raw, object_pairs_hook=_no_duplicate_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error(f"{label} is malformed JSON") from exc
    if type(value) is not dict or _canonical_json(value) != raw:
        raise _error(f"{label} is not canonical compact sorted-key JSON")
    return value


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 1:
        raise _error(f"{label} must be an exact positive integer")
    return value


def _non_negative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise _error(f"{label} must be an exact non-negative integer")
    return value


def _sha256(value: Any, label: str) -> str:
    if type(value) is not str or SHA256_RE.fullmatch(value) is None:
        raise _error(f"{label} must be lowercase SHA-256")
    return value


def verify_actions_artifact_zip_digest(zip_bytes: bytes, metadata_digest: Any) -> str:
    """Bind exact downloaded Actions artifact ZIP bytes to GitHub's independent digest."""
    if type(zip_bytes) is not bytes or not zip_bytes:
        raise _error("Actions artifact ZIP must be non-empty exact bytes")
    if type(metadata_digest) is not str or not metadata_digest.startswith("sha256:"):
        raise _error("Actions artifact metadata lacks SHA-256 digest")
    expected = _sha256(
        metadata_digest.removeprefix("sha256:"),
        "Actions artifact ZIP digest",
    )
    actual = hashlib.sha256(zip_bytes).hexdigest()
    if actual != expected:
        raise _error("Actions artifact ZIP disagrees with GitHub digest metadata")
    return actual


def _parse_nominal(value: Any) -> dt.datetime:
    if type(value) is not str or value != value.strip():
        raise _error("nominal scheduled time must be exact text")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _error("nominal scheduled time is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _error("nominal scheduled time must be timezone-aware")
    parsed = parsed.astimezone(dt.timezone.utc)
    if parsed.second or parsed.microsecond or parsed.minute not in (7, 37):
        raise _error("nominal scheduled time escaped reviewed :07/:37 cadence")
    return parsed


def _safe_artifact_members(zip_bytes: bytes, expected_archive_name: str) -> tuple[bytes, bytes]:
    if type(zip_bytes) is not bytes or not zip_bytes:
        raise _error("Actions artifact ZIP must be non-empty exact bytes")
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            expected = {expected_archive_name, RECEIPT_MEMBER}
            if len(infos) != 2 or set(names) != expected or len(set(names)) != 2:
                raise _error("Actions artifact must contain exactly archive + canonical receipt")
            for info in infos:
                path = Path(info.filename)
                mode = (info.external_attr >> 16) & 0xFFFF
                if (
                    info.is_dir()
                    or path.is_absolute()
                    or ".." in path.parts
                    or len(path.parts) != 1
                    or (mode and stat.S_ISLNK(mode))
                ):
                    raise _error("Actions artifact contains unsafe member metadata")
            return archive.read(expected_archive_name), archive.read(RECEIPT_MEMBER)
    except (zipfile.BadZipFile, KeyError) as exc:
        raise _error("Actions artifact ZIP is invalid") from exc


def verify_actions_artifact_bundle(
    *,
    run_id: int,
    artifact_name: str,
    zip_bytes: bytes,
) -> dict[str, Any]:
    """Verify exact archive/receipt bytes from one completed workflow run artifact."""
    run_id = _positive_int(run_id, "run_id")
    match = ARTIFACT_RE.fullmatch(artifact_name) if type(artifact_name) is str else None
    if match is None or int(match.group(3)) != run_id:
        raise _error("artifact name is not bound to the exact workflow run")
    kind, compact, _run_text = match.groups()
    archive_bytes, receipt_bytes = _safe_artifact_members(zip_bytes, artifact_name)
    receipt = _parse_canonical_json(receipt_bytes, "tick receipt")

    if receipt.get("workflow_run_id") != run_id:
        raise _error("tick receipt workflow_run_id changed")
    if receipt.get("durable_asset_name") != artifact_name:
        raise _error("tick receipt durable asset identity changed")
    tag = receipt.get("durable_release_tag")
    if type(tag) is not str or RELEASE_TAG_RE.fullmatch(tag) is None:
        raise _error("tick receipt durable release tag is invalid")
    nominal = _parse_nominal(receipt.get("nominal_scheduled_for_utc"))
    if nominal.strftime("%Y%m%dT%H%M%SZ") != compact:
        raise _error("artifact nominal slot disagrees with canonical receipt")

    expected_sha = _sha256(receipt.get("durable_asset_sha256"), "durable asset digest")
    expected_size = _positive_int(receipt.get("durable_asset_size_bytes"), "durable asset size")
    if hashlib.sha256(archive_bytes).hexdigest() != expected_sha:
        raise _error("Actions artifact archive bytes disagree with receipt SHA-256")
    if len(archive_bytes) != expected_size:
        raise _error("Actions artifact archive bytes disagree with receipt size")

    exit_code = _non_negative_int(receipt.get("tick_exit_code"), "tick exit code")
    committed = receipt.get("tick_committed")
    if type(committed) is not bool:
        raise _error("tick_committed must be exact bool")
    if kind == "success":
        if exit_code != 0 or committed is not True:
            raise _error("success archive does not prove committed zero-exit tick")
    elif exit_code == 0 or committed is not False:
        raise _error("failure archive does not prove failed uncommitted tick")

    return {
        "run_id": run_id,
        "artifact_name": artifact_name,
        "release_tag": tag,
        "receipt_name": f"{artifact_name}.receipt.json",
        "archive_sha256": expected_sha,
        "archive_size_bytes": expected_size,
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "receipt_size_bytes": len(receipt_bytes),
        "receipt_bytes": receipt_bytes,
        "archive_bytes": archive_bytes,
    }


def _asset_by_name(release: dict[str, Any], name: str) -> dict[str, Any] | None:
    assets = release.get("assets")
    if type(assets) is not list:
        raise _error("GitHub release assets payload is malformed")
    matching = [asset for asset in assets if type(asset) is dict and asset.get("name") == name]
    if len(matching) > 1:
        raise _error(f"GitHub release contains duplicate asset name: {name}")
    return None if not matching else matching[0]


def verify_release_archive_and_receipt(
    *,
    verified: dict[str, Any],
    release: dict[str, Any],
    download_release_asset: Callable[[int], bytes],
    upload_receipt: Callable[[str, bytes], None],
    reload_release: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Verify release archive bytes and create/recheck an immutable canonical receipt sidecar."""
    archive_name = verified["artifact_name"]
    receipt_name = verified["receipt_name"]
    archive_asset = _asset_by_name(release, archive_name)
    if archive_asset is None:
        raise _error("long-lived release is missing the durable archive")
    if archive_asset.get("state") != "uploaded":
        raise _error("long-lived archive release asset is not uploaded")
    if archive_asset.get("size") != verified["archive_size_bytes"]:
        raise _error("long-lived archive release asset size changed")
    archive_id = _positive_int(archive_asset.get("id"), "release archive asset id")
    release_archive = download_release_asset(archive_id)
    if len(release_archive) != verified["archive_size_bytes"]:
        raise _error("downloaded release archive size changed")
    if hashlib.sha256(release_archive).hexdigest() != verified["archive_sha256"]:
        raise _error("downloaded release archive SHA-256 disagrees with canonical receipt")
    if release_archive != verified["archive_bytes"]:
        raise _error("release archive bytes differ from authoritative Actions artifact bytes")

    receipt_asset = _asset_by_name(release, receipt_name)
    if receipt_asset is None:
        upload_receipt(receipt_name, verified["receipt_bytes"])
        release = reload_release()
        receipt_asset = _asset_by_name(release, receipt_name)
        if receipt_asset is None:
            raise _error("receipt upload returned without a release receipt asset")
    if receipt_asset.get("state") != "uploaded":
        raise _error("long-lived receipt release asset is not uploaded")
    if receipt_asset.get("size") != verified["receipt_size_bytes"]:
        raise _error("long-lived receipt release asset size changed")
    receipt_id = _positive_int(receipt_asset.get("id"), "release receipt asset id")
    release_receipt = download_release_asset(receipt_id)
    if release_receipt != verified["receipt_bytes"]:
        raise _error("long-lived release receipt bytes differ from authoritative receipt")
    if hashlib.sha256(release_receipt).hexdigest() != verified["receipt_sha256"]:
        raise _error("long-lived release receipt SHA-256 changed")

    return {
        "schema_version": 1,
        "run_id": verified["run_id"],
        "actions_artifact_zip_sha256": verified["actions_artifact_zip_sha256"],
        "release_tag": verified["release_tag"],
        "archive_name": archive_name,
        "archive_sha256": verified["archive_sha256"],
        "archive_size_bytes": verified["archive_size_bytes"],
        "receipt_name": receipt_name,
        "receipt_sha256": verified["receipt_sha256"],
        "receipt_size_bytes": verified["receipt_size_bytes"],
        "release_archive_exact_bytes_verified": True,
        "release_receipt_exact_bytes_verified": True,
        "provider_network_acquisition_performed": False,
        "model_or_betting_authority_changed": False,
    }


def _parse_canonical_or_general_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=_no_duplicate_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error(f"{label} is malformed JSON") from exc
    if type(value) is not dict:
        raise _error(f"{label} must be an object")
    return value


def _gh_json(endpoint: str) -> dict[str, Any]:
    try:
        raw = subprocess.check_output(["gh", "api", endpoint])
    except (OSError, subprocess.CalledProcessError) as exc:
        raise _error(f"GitHub API request failed: {endpoint}") from exc
    return _parse_canonical_or_general_json(raw, f"GitHub API response {endpoint}")


def _gh_download(endpoint: str) -> bytes:
    try:
        return subprocess.check_output(
            ["gh", "api", "-H", "Accept: application/octet-stream", endpoint]
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise _error(f"GitHub binary download failed: {endpoint}") from exc


def _release_for(repo: str, tag: str) -> dict[str, Any]:
    return _gh_json(f"/repos/{repo}/releases/tags/{tag}")


def mirror_run(*, repository: str, run_id: int) -> dict[str, Any]:
    """Mirror one completed collection run's canonical receipt into its long-lived release."""
    if type(repository) is not str or repository.count("/") != 1 or repository != repository.strip():
        raise _error("repository must be exact owner/name text")
    run_id = _positive_int(run_id, "run_id")

    run = _gh_json(f"/repos/{repository}/actions/runs/{run_id}")
    if run.get("name") != WORKFLOW_NAME:
        raise _error("workflow run name escaped reviewed collection workflow")
    if run.get("event") != "schedule" or run.get("status") != "completed":
        raise _error("receipt mirroring requires one completed scheduled collection run")
    if run.get("head_branch") != "main":
        raise _error("collection run did not execute from default main")
    path = run.get("path")
    if type(path) is not str or not path.startswith(WORKFLOW_PATH):
        raise _error("workflow run path escaped reviewed collection workflow")

    artifacts = _gh_json(f"/repos/{repository}/actions/runs/{run_id}/artifacts")
    values = artifacts.get("artifacts")
    if type(values) is not list:
        raise _error("workflow artifacts payload is malformed")
    candidates = [
        value
        for value in values
        if type(value) is dict
        and type(value.get("name")) is str
        and ARTIFACT_RE.fullmatch(value["name"]) is not None
        and value["name"].endswith(f"-run-{run_id}.tar.gz")
        and value.get("expired") is False
    ]
    if len(candidates) != 1:
        raise _error("completed collection run must expose exactly one unexpired evidence artifact")
    artifact = candidates[0]
    artifact_id = _positive_int(artifact.get("id"), "Actions artifact id")
    artifact_name = artifact["name"]
    zip_bytes = _gh_download(f"/repos/{repository}/actions/artifacts/{artifact_id}/zip")
    artifact_zip_sha = verify_actions_artifact_zip_digest(
        zip_bytes,
        artifact.get("digest"),
    )
    verified = verify_actions_artifact_bundle(
        run_id=run_id,
        artifact_name=artifact_name,
        zip_bytes=zip_bytes,
    )
    verified["actions_artifact_zip_sha256"] = artifact_zip_sha

    tag = verified["release_tag"]
    release = _release_for(repository, tag)

    def download_release_asset(asset_id: int) -> bytes:
        return _gh_download(f"/repos/{repository}/releases/assets/{asset_id}")

    def upload_receipt(name: str, raw: bytes) -> None:
        with tempfile.TemporaryDirectory(prefix="athena-release-receipt-") as temporary:
            path = Path(temporary) / name
            path.write_bytes(raw)
            try:
                subprocess.check_call(
                    ["gh", "release", "upload", tag, str(path), "--repo", repository]
                )
            except (OSError, subprocess.CalledProcessError) as exc:
                raise _error("GitHub release receipt upload failed") from exc

    return verify_release_archive_and_receipt(
        verified=verified,
        release=release,
        download_release_asset=download_release_asset,
        upload_receipt=upload_receipt,
        reload_release=lambda: _release_for(repository, tag),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    arguments = parser.parse_args(argv)
    if not os.environ.get("GH_TOKEN"):
        raise _error("GH_TOKEN is required for GitHub evidence mirroring")
    result = mirror_run(repository=arguments.repository, run_id=arguments.run_id)
    print(_canonical_json(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
