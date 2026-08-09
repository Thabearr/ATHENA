"""Offline CLI for verified FotMob date-page state assessment."""

from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path as _BootstrapPath

    _REPOSITORY_ROOT = _BootstrapPath(__file__).resolve().parents[1]
    if str(_REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPOSITORY_ROOT))

import argparse
from pathlib import Path
import stat
import sys
from typing import Any

from domain.fotmob_page_capture import (
    MAX_RESPONSE_BYTES,
    RAW_FILENAME,
    FotMobPageCaptureError,
    FotMobPageCaptureManifest,
    sha256_bytes,
    verify_page_capture_directory,
)
from domain.fotmob_page_state import (
    FotMobPageStateAssessment,
    FotMobPageStateError,
    assess_fotmob_page_state,
    canonical_page_state_assessment_bytes,
)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _reject_symlink_components(path: Path, label: str) -> None:
    absolute = path if path.is_absolute() else Path.cwd() / path
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise FotMobPageStateError(f"{label} contains a forbidden symlink")


def _resolve_repository_directory(
    value: Any,
    *,
    repository_root: Path,
    label: str,
) -> Path:
    try:
        supplied = Path(value)
    except (TypeError, ValueError) as exc:
        raise FotMobPageStateError(f"{label} path is invalid") from exc
    if ".." in supplied.parts:
        raise FotMobPageStateError(f"{label} must not contain traversal")
    absolute = supplied if supplied.is_absolute() else repository_root / supplied
    _reject_symlink_components(absolute, label)
    try:
        resolved = absolute.resolve(strict=True)
    except OSError as exc:
        raise FotMobPageStateError(f"{label} does not exist") from exc
    try:
        resolved.relative_to(repository_root)
    except ValueError as exc:
        raise FotMobPageStateError(
            f"{label} must remain within the repository root"
        ) from exc
    if resolved.is_symlink() or not resolved.is_dir():
        raise FotMobPageStateError(f"{label} must be a non-symlink directory")
    return resolved


def _read_bounded_raw_page(path: Path) -> bytes:
    try:
        candidate = Path(path)
    except (TypeError, ValueError) as exc:
        raise FotMobPageStateError("page.html path is invalid") from exc
    if candidate.is_symlink():
        raise FotMobPageStateError("page.html must not be a symlink")
    try:
        metadata = candidate.stat()
    except OSError as exc:
        raise FotMobPageStateError("page.html could not be inspected") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise FotMobPageStateError("page.html must be a regular file")
    if metadata.st_size <= 0:
        raise FotMobPageStateError("page.html must not be empty")
    if metadata.st_size > MAX_RESPONSE_BYTES:
        raise FotMobPageStateError("page.html exceeds the 8 MiB limit")
    try:
        with candidate.open("rb") as handle:
            content = handle.read(MAX_RESPONSE_BYTES + 1)
    except OSError as exc:
        raise FotMobPageStateError("page.html could not be read") from exc
    if type(content) is not bytes:
        raise FotMobPageStateError("page.html read did not return exact bytes")
    if len(content) > MAX_RESPONSE_BYTES:
        raise FotMobPageStateError("page.html exceeds the 8 MiB limit")
    if not content:
        raise FotMobPageStateError("page.html must not be empty")
    return content


def assess_capture_directory(
    capture_directory: Path,
    *,
    allowed_root: Path,
    repository_root: Path | None = None,
) -> FotMobPageStateAssessment:
    repository = (repository_root or _repository_root()).resolve(strict=True)
    root = _resolve_repository_directory(
        allowed_root,
        repository_root=repository,
        label="allowed root",
    )
    capture = _resolve_repository_directory(
        capture_directory,
        repository_root=repository,
        label="capture directory",
    )
    try:
        manifest = verify_page_capture_directory(
            capture,
            allowed_root=root,
            require_network_acquisition_performed=True,
        )
    except FotMobPageCaptureError as exc:
        raise FotMobPageStateError("source capture verification failed") from exc
    if not isinstance(manifest, FotMobPageCaptureManifest):
        raise FotMobPageStateError(
            "source capture verifier did not return a manifest"
        )
    raw_html = _read_bounded_raw_page(capture / RAW_FILENAME)
    if len(raw_html) != manifest.raw_size:
        raise FotMobPageStateError("second-read raw size does not match manifest")
    if sha256_bytes(raw_html) != manifest.raw_sha256:
        raise FotMobPageStateError("second-read raw SHA-256 does not match manifest")
    return assess_fotmob_page_state(raw_html, manifest)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assess one verified FotMob date-page capture offline."
    )
    parser.add_argument("--capture-directory", type=Path, required=True)
    parser.add_argument("--allowed-root", type=Path, required=True)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    repository_root: Path | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        assessment = assess_capture_directory(
            args.capture_directory,
            allowed_root=args.allowed_root,
            repository_root=repository_root,
        )
        sys.stdout.buffer.write(canonical_page_state_assessment_bytes(assessment))
        return 0
    except FotMobPageStateError as exc:
        parser.exit(1, f"assessment failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
