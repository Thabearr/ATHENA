"""Restore the reviewed PR119 projection from its exact fixed GitHub Release.

This module performs GitHub Release metadata/asset transport only. It has no
FotMob/provider transport and deliberately has no historical-artifact fallback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any, Callable


REPOSITORY = "Thabearr/ATHENA"
RELEASE_ID = 373205103
RELEASE_TAG = "athena-fresh-holdout-bootstrap-v1"
RELEASE_NAME = "PR119 Materialized Bootstrap Projection"
ASSET_ID = 521090702
ASSET_NAME = "pr119-materialized.ndjson"
ASSET_SIZE = 10_545_099
PAYLOAD_SHA256 = "e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2"
ASSET_DIGEST = "sha256:" + PAYLOAD_SHA256
ROW_COUNT = 21_326


class FixedBootstrapError(RuntimeError):
    """Base class for fail-closed fixed-release bootstrap failures."""


class ReleaseMetadataError(FixedBootstrapError):
    pass


class AssetMetadataError(FixedBootstrapError):
    pass


class AssetDownloadError(FixedBootstrapError):
    pass


class ProjectionPayloadError(FixedBootstrapError):
    pass


class BootstrapTargetError(FixedBootstrapError):
    pass


def validate_release_metadata(repository: str, release: Any) -> list[dict[str, Any]]:
    """Validate every reviewed fixed-release identity before asset lookup."""
    if repository != REPOSITORY:
        raise ReleaseMetadataError("repository is not the reviewed ATHENA repository")
    if type(release) is not dict:
        raise ReleaseMetadataError("release metadata must be an object")
    if type(release.get("id")) is not int or release["id"] != RELEASE_ID:
        raise ReleaseMetadataError("fixed release ID differs")
    if release.get("tag_name") != RELEASE_TAG or release.get("name") != RELEASE_NAME:
        raise ReleaseMetadataError("fixed release tag or name differs")
    if type(release.get("draft")) is not bool or release["draft"] is not False:
        raise ReleaseMetadataError("fixed release must not be a draft")
    if type(release.get("prerelease")) is not bool or release["prerelease"] is not False:
        raise ReleaseMetadataError("fixed release must not be a prerelease")
    assets = release.get("assets")
    if type(assets) is not list:
        raise ReleaseMetadataError("fixed release assets must be an array")
    return assets


def validate_asset_metadata(assets: Any) -> int:
    """Resolve exactly one expected asset and authenticate its metadata."""
    if type(assets) is not list:
        raise AssetMetadataError("fixed release assets must be an array")
    matches = [
        asset for asset in assets
        if type(asset) is dict
        and (asset.get("id") == ASSET_ID or asset.get("name") == ASSET_NAME)
    ]
    if len(matches) != 1:
        raise AssetMetadataError(
            f"expected exactly one fixed bootstrap asset, found {len(matches)}"
        )
    asset = matches[0]
    if type(asset.get("id")) is not int or asset["id"] != ASSET_ID:
        raise AssetMetadataError("fixed bootstrap asset ID differs")
    if asset.get("name") != ASSET_NAME:
        raise AssetMetadataError("fixed bootstrap asset name differs")
    if asset.get("state") != "uploaded":
        raise AssetMetadataError("fixed bootstrap asset is not uploaded")
    if type(asset.get("size")) is not int or asset["size"] != ASSET_SIZE:
        raise AssetMetadataError("fixed bootstrap asset size differs")
    if "digest" in asset and asset["digest"] is not None and asset["digest"] != ASSET_DIGEST:
        raise AssetMetadataError("fixed bootstrap asset digest differs")
    return ASSET_ID


def validate_projection_payload(raw: bytes) -> tuple[Any, ...]:
    """Authenticate exact bytes and the existing reviewed projection parser."""
    if type(raw) is not bytes:
        raise ProjectionPayloadError("bootstrap payload must be exact bytes")
    if len(raw) != ASSET_SIZE:
        raise ProjectionPayloadError("bootstrap payload size differs")
    if hashlib.sha256(raw).hexdigest() != PAYLOAD_SHA256:
        raise ProjectionPayloadError("bootstrap payload SHA-256 differs")
    try:
        from domain.fotmob_utc_native_expected_goals_fresh_holdout import (
            parse_reviewed_legacy_bootstrap_projection,
        )

        rows = parse_reviewed_legacy_bootstrap_projection(raw)
    except Exception as exc:
        raise ProjectionPayloadError(
            "bootstrap payload failed the reviewed projection parser"
        ) from exc
    if len(rows) != ROW_COUNT:
        raise ProjectionPayloadError("bootstrap projection row count differs")
    return rows


def _write_exact_target(target: Path, raw: bytes) -> None:
    """Write exact verified bytes, rejecting symlink and non-regular targets."""
    target = Path(target)
    if target.parent.is_symlink() or not target.parent.is_dir():
        raise BootstrapTargetError("bootstrap target parent must be a real directory")
    try:
        existing = target.lstat()
    except FileNotFoundError:
        existing = None
    except OSError as exc:
        raise BootstrapTargetError("bootstrap target cannot be inspected") from exc
    if target.is_symlink():
        raise BootstrapTargetError("symlink bootstrap target is forbidden")
    if existing is not None and not stat.S_ISREG(existing.st_mode):
        raise BootstrapTargetError("bootstrap target must be a regular file")

    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags, 0o600)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise BootstrapTargetError("bootstrap target must be a regular file")
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
        written = target.lstat()
    except BootstrapTargetError:
        raise
    except OSError as exc:
        raise BootstrapTargetError("could not write exact bootstrap bytes") from exc
    if (
        not stat.S_ISREG(written.st_mode)
        or written.st_size != ASSET_SIZE
        or hashlib.sha256(target.read_bytes()).hexdigest() != PAYLOAD_SHA256
    ):
        raise BootstrapTargetError("written bootstrap target failed exact-byte verification")


def restore_pr119_bootstrap(
    *,
    repository: str,
    get_release_metadata: Callable[[int], Any],
    download_asset: Callable[[int], bytes],
    target: Path | None = None,
) -> bytes:
    """Authenticate fixed release and payload, then optionally write exact bytes."""
    if repository != REPOSITORY:
        raise ReleaseMetadataError("repository is not the reviewed ATHENA repository")
    try:
        release = get_release_metadata(RELEASE_ID)
    except Exception as exc:
        raise ReleaseMetadataError("fixed release metadata lookup failed") from exc
    assets = validate_release_metadata(repository, release)
    asset_id = validate_asset_metadata(assets)
    try:
        payload = download_asset(asset_id)
    except Exception as exc:
        raise AssetDownloadError("fixed release asset download failed") from exc
    validate_projection_payload(payload)
    if target is not None:
        _write_exact_target(Path(target), payload)
    return payload


def _gh_release_metadata(repository: str, release_id: int) -> Any:
    raw = subprocess.check_output(
        ["gh", "api", f"/repos/{repository}/releases/{release_id}"],
        text=True,
    )
    return json.loads(raw)


def _gh_download_asset(repository: str, asset_id: int) -> bytes:
    return subprocess.check_output(
        [
            "gh", "api", "-H", "Accept: application/octet-stream",
            f"/repos/{repository}/releases/assets/{asset_id}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", default=ASSET_NAME)
    args = parser.parse_args(argv)
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    try:
        raw = restore_pr119_bootstrap(
            repository=repository,
            get_release_metadata=lambda release_id: _gh_release_metadata(
                repository, release_id
            ),
            download_asset=lambda asset_id: _gh_download_asset(repository, asset_id),
            target=Path(args.target),
        )
    except FixedBootstrapError as exc:
        print(f"FIXED_PR119_BOOTSTRAP_FAILED_CLOSED: {exc}", file=sys.stderr)
        return 1
    print(
        "fixed PR119 bootstrap verified: "
        f"release_id={RELEASE_ID} asset_id={ASSET_ID} "
        f"sha256={PAYLOAD_SHA256} size={len(raw)} rows={ROW_COUNT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
