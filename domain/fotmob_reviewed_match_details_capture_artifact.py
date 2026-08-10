"""Detached artifact wrapper for reviewed FotMob match-details raw captures.

The wrapper freezes the exact canonical manifest bytes and their SHA-256 so a
later durable writer never has to redefine the artifact from a live nested
manifest object.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
from typing import Any

from domain.fotmob_reviewed_match_details_capture import (
    FotMobReviewedMatchDetailsCaptureError,
    FotMobReviewedMatchDetailsRawCapture,
    canonical_reviewed_match_details_capture_manifest_bytes,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-reviewed-match-details-capture-artifact-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)


class FotMobReviewedMatchDetailsCaptureArtifactError(ValueError):
    """Raised when detached raw-capture artifact identity fails closed."""


def _strict_sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise FotMobReviewedMatchDetailsCaptureArtifactError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _revalidate_capture(value: Any) -> FotMobReviewedMatchDetailsRawCapture:
    if type(value) is not FotMobReviewedMatchDetailsRawCapture:
        raise FotMobReviewedMatchDetailsCaptureArtifactError(
            "capture must be exact FotMobReviewedMatchDetailsRawCapture"
        )
    try:
        return dataclasses.replace(value)
    except (
        FotMobReviewedMatchDetailsCaptureError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsCaptureArtifactError(
            "raw capture failed current exact revalidation"
        ) from exc


@dataclasses.dataclass(frozen=True)
class FotMobReviewedMatchDetailsCaptureArtifact:
    """Exact raw bytes plus detached canonical manifest bytes and identities."""

    schema_version: int
    dataset_name: str
    capture: FotMobReviewedMatchDetailsRawCapture
    manifest_bytes: bytes
    manifest_sha256: str
    raw_sha256: str
    raw_size: int

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobReviewedMatchDetailsCaptureArtifactError(
                "schema_version must be exact integer 1"
            )
        if self.dataset_name != DATASET_NAME:
            raise FotMobReviewedMatchDetailsCaptureArtifactError("dataset_name mismatch")
        capture = _revalidate_capture(self.capture)
        if type(self.manifest_bytes) is not bytes:
            raise FotMobReviewedMatchDetailsCaptureArtifactError(
                "manifest_bytes must be exact immutable bytes"
            )
        expected_manifest_bytes = canonical_reviewed_match_details_capture_manifest_bytes(
            capture.manifest
        )
        if self.manifest_bytes != expected_manifest_bytes:
            raise FotMobReviewedMatchDetailsCaptureArtifactError(
                "manifest_bytes are not the exact canonical bytes of the revalidated manifest"
            )
        _strict_sha(self.manifest_sha256, "manifest_sha256")
        expected_manifest_sha = hashlib.sha256(expected_manifest_bytes).hexdigest()
        if self.manifest_sha256 != expected_manifest_sha:
            raise FotMobReviewedMatchDetailsCaptureArtifactError(
                "manifest_sha256 does not match exact canonical manifest bytes"
            )
        _strict_sha(self.raw_sha256, "raw_sha256")
        if self.raw_sha256 != capture.manifest.raw_sha256:
            raise FotMobReviewedMatchDetailsCaptureArtifactError(
                "raw_sha256 does not match revalidated capture manifest"
            )
        if type(self.raw_size) is not int or self.raw_size != capture.manifest.raw_size:
            raise FotMobReviewedMatchDetailsCaptureArtifactError(
                "raw_size does not match revalidated capture manifest"
            )
        object.__setattr__(self, "capture", capture)


def build_reviewed_match_details_capture_artifact(
    capture: Any,
) -> FotMobReviewedMatchDetailsCaptureArtifact:
    """Freeze exact manifest bytes for one currently valid PR #50 raw capture."""

    rebuilt = _revalidate_capture(capture)
    manifest_bytes = canonical_reviewed_match_details_capture_manifest_bytes(
        rebuilt.manifest
    )
    return FotMobReviewedMatchDetailsCaptureArtifact(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        capture=rebuilt,
        manifest_bytes=manifest_bytes,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        raw_sha256=rebuilt.manifest.raw_sha256,
        raw_size=rebuilt.manifest.raw_size,
    )


def revalidate_reviewed_match_details_capture_artifact(
    value: Any,
) -> FotMobReviewedMatchDetailsCaptureArtifact:
    if type(value) is not FotMobReviewedMatchDetailsCaptureArtifact:
        raise FotMobReviewedMatchDetailsCaptureArtifactError(
            "value must be exact FotMobReviewedMatchDetailsCaptureArtifact"
        )
    try:
        return dataclasses.replace(value)
    except (
        FotMobReviewedMatchDetailsCaptureArtifactError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        if isinstance(exc, FotMobReviewedMatchDetailsCaptureArtifactError):
            raise
        raise FotMobReviewedMatchDetailsCaptureArtifactError(
            "capture artifact failed current exact revalidation"
        ) from exc


__all__ = [
    "DATASET_NAME",
    "FotMobReviewedMatchDetailsCaptureArtifact",
    "FotMobReviewedMatchDetailsCaptureArtifactError",
    "SCHEMA_VERSION",
    "build_reviewed_match_details_capture_artifact",
    "revalidate_reviewed_match_details_capture_artifact",
]
