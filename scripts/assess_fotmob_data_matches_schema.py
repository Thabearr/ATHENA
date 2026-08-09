"""Offline CLI for strict FotMob data-matches schema assessment."""

from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path as _BootstrapPath

    _REPOSITORY_ROOT = _BootstrapPath(__file__).resolve().parents[1]
    if str(_REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPOSITORY_ROOT))

import argparse
import hashlib
import stat
import sys
from pathlib import Path
from typing import Any

from domain.fotmob_data_matches_capture import (
    MAX_RESPONSE_BYTES,
    RAW_FILENAME,
    FotMobDataMatchesCaptureError,
    FotMobDataMatchesCaptureManifest,
    verify_data_matches_capture_directory,
)
from domain.fotmob_data_matches_schema import (
    FotMobDataMatchesSchemaError,
    assess_fotmob_data_matches_schema,
    canonical_data_matches_schema_assessment_bytes,
)


ALLOWED_ROOT_RELATIVE = Path(
    ".cache/athena-research/fotmob-data-matches-captures"
)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _reject_symlink_components(path: Path, label: str) -> None:
    absolute = path if path.is_absolute() else Path.cwd() / path
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise FotMobDataMatchesSchemaError(
                f"{label} contains a forbidden symlink"
            )


def _capture_path(
    value: Any,
    *,
    repository_root: Path,
) -> tuple[Path, Path]:
    if not isinstance(value, (str, Path)):
        raise FotMobDataMatchesSchemaError("capture directory path is invalid")
    supplied = Path(value)
    if ".." in supplied.parts:
        raise FotMobDataMatchesSchemaError(
            "capture directory must not contain traversal"
        )
    repository = repository_root.resolve(strict=True)
    allowed_root = repository / ALLOWED_ROOT_RELATIVE
    candidate = supplied if supplied.is_absolute() else repository / supplied
    _reject_symlink_components(allowed_root, "allowed root")
    _reject_symlink_components(candidate, "capture directory")
    try:
        candidate_resolved = candidate.resolve(strict=True)
        allowed_resolved = allowed_root.resolve(strict=True)
        candidate_resolved.relative_to(allowed_resolved)
    except (OSError, ValueError) as exc:
        raise FotMobDataMatchesSchemaError(
            "capture directory is outside the fixed repository-local root"
        ) from exc
    return candidate_resolved, allowed_resolved


def _read_bounded_response(path: Path) -> bytes:
    candidate = Path(path)
    if candidate.is_symlink():
        raise FotMobDataMatchesSchemaError("response.json must not be a symlink")
    try:
        metadata = candidate.stat()
    except OSError as exc:
        raise FotMobDataMatchesSchemaError(
            "response.json could not be inspected"
        ) from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise FotMobDataMatchesSchemaError("response.json must be a regular file")
    if metadata.st_size <= 0:
        raise FotMobDataMatchesSchemaError("response.json must not be empty")
    if metadata.st_size > MAX_RESPONSE_BYTES:
        raise FotMobDataMatchesSchemaError(
            "response.json exceeds the 8 MiB assessment limit"
        )
    try:
        with candidate.open("rb") as handle:
            raw = handle.read(MAX_RESPONSE_BYTES + 1)
    except OSError as exc:
        raise FotMobDataMatchesSchemaError("response.json could not be read") from exc
    if type(raw) is not bytes:
        raise FotMobDataMatchesSchemaError(
            "response.json read did not return exact bytes"
        )
    if len(raw) > MAX_RESPONSE_BYTES:
        raise FotMobDataMatchesSchemaError(
            "response.json exceeds the 8 MiB assessment limit"
        )
    if not raw:
        raise FotMobDataMatchesSchemaError("response.json must not be empty")
    return raw


def _verified_raw(
    capture_directory: Path,
    allowed_root: Path,
) -> tuple[bytes, FotMobDataMatchesCaptureManifest]:
    try:
        manifest = verify_data_matches_capture_directory(
            capture_directory,
            allowed_root=allowed_root,
            require_network_acquisition_performed=True,
        )
    except FotMobDataMatchesCaptureError as exc:
        raise FotMobDataMatchesSchemaError(
            f"source capture verification failed: {exc}"
        ) from exc
    raw = _read_bounded_response(capture_directory / RAW_FILENAME)
    if len(raw) != manifest.raw_size:
        raise FotMobDataMatchesSchemaError(
            "independent response read size does not match manifest"
        )
    if hashlib.sha256(raw).hexdigest() != manifest.raw_sha256:
        raise FotMobDataMatchesSchemaError(
            "independent response read SHA-256 does not match manifest"
        )
    return raw, manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Assess one verified FotMob data-matches capture against the "
            "reviewed offline V1 structural schema."
        )
    )
    parser.add_argument(
        "--capture-directory",
        required=True,
        help="Existing capture beneath the fixed ignored research root",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    repository_root: Path | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        repository = (repository_root or _repository_root()).resolve(strict=True)
        capture, allowed_root = _capture_path(
            args.capture_directory,
            repository_root=repository,
        )
        raw, manifest = _verified_raw(capture, allowed_root)
        assessment = assess_fotmob_data_matches_schema(raw, manifest)
        sys.stdout.buffer.write(
            canonical_data_matches_schema_assessment_bytes(assessment)
        )
        return 0
    except FotMobDataMatchesSchemaError as exc:
        parser.exit(1, f"assessment failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
