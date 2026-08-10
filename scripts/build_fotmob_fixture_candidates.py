"""Offline CLI for provenance-backed UNREVIEWED FotMob candidates."""

from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path as _BootstrapPath

    _REPOSITORY_ROOT = _BootstrapPath(__file__).resolve().parents[1]
    if str(_REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPOSITORY_ROOT))

import argparse
import hashlib
import json
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
from domain.fotmob_fixture_candidates import (
    SUMMARY_DATASET_NAME,
    SUMMARY_SCHEMA_VERSION,
    FotMobFixtureCandidateError,
    build_fotmob_fixture_candidate_bundle,
    sha256_fotmob_fixture_candidate_bundle,
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
            raise FotMobFixtureCandidateError(f"{label} contains a forbidden symlink")


def _capture_path(value: Any, *, repository_root: Path) -> tuple[Path, Path]:
    if not isinstance(value, (str, Path)):
        raise FotMobFixtureCandidateError("capture directory path is invalid")
    supplied = Path(value)
    if ".." in supplied.parts:
        raise FotMobFixtureCandidateError("capture directory must not contain traversal")
    repository = repository_root.resolve(strict=True)
    allowed_root = repository / ALLOWED_ROOT_RELATIVE
    candidate = supplied if supplied.is_absolute() else repository / supplied
    _reject_symlink_components(allowed_root, "allowed root")
    _reject_symlink_components(candidate, "capture directory")
    try:
        allowed_resolved = allowed_root.resolve(strict=True)
        candidate_resolved = candidate.resolve(strict=True)
        candidate_resolved.relative_to(allowed_resolved)
    except (OSError, ValueError) as exc:
        raise FotMobFixtureCandidateError(
            "capture directory is outside the fixed repository-local root"
        ) from exc
    return candidate_resolved, allowed_resolved


def _read_bounded_response(path: Path) -> bytes:
    candidate = Path(path)
    if candidate.is_symlink():
        raise FotMobFixtureCandidateError("response.json must not be a symlink")
    try:
        metadata = candidate.stat()
    except OSError as exc:
        raise FotMobFixtureCandidateError("response.json could not be inspected") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise FotMobFixtureCandidateError("response.json must be a regular file")
    if metadata.st_size <= 0:
        raise FotMobFixtureCandidateError("response.json must not be empty")
    if metadata.st_size > MAX_RESPONSE_BYTES:
        raise FotMobFixtureCandidateError("response.json exceeds the 8 MiB limit")
    try:
        with candidate.open("rb") as handle:
            raw = handle.read(MAX_RESPONSE_BYTES + 1)
    except OSError as exc:
        raise FotMobFixtureCandidateError("response.json could not be read") from exc
    if type(raw) is not bytes:
        raise FotMobFixtureCandidateError("response.json read did not return exact bytes")
    if len(raw) > MAX_RESPONSE_BYTES:
        raise FotMobFixtureCandidateError("response.json exceeds the 8 MiB limit")
    if not raw:
        raise FotMobFixtureCandidateError("response.json must not be empty")
    return raw


def _verified_capture(
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
        raise FotMobFixtureCandidateError(
            f"source capture verification failed: {exc}"
        ) from exc
    raw = _read_bounded_response(capture_directory / RAW_FILENAME)
    if len(raw) != manifest.raw_size:
        raise FotMobFixtureCandidateError("independent response size does not match manifest")
    if hashlib.sha256(raw).hexdigest() != manifest.raw_sha256:
        raise FotMobFixtureCandidateError("independent response SHA-256 does not match manifest")
    return raw, manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic summary of UNREVIEWED FotMob fixture "
            "candidates from verified local captures."
        )
    )
    parser.add_argument(
        "--capture-directory",
        action="append",
        required=True,
        help="Repeatable capture directory beneath the fixed ignored research root",
    )
    return parser


def _summary_bytes(bundle: Any) -> bytes:
    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "dataset_name": SUMMARY_DATASET_NAME,
        "source_capture_count": len(bundle.sources),
        "source_request_dates": [item.request_date for item in bundle.sources],
        "candidate_count": bundle.candidate_count,
        "duplicate_source_match_id_count": bundle.duplicate_source_match_id_count,
        "fixture_identity_conflict_count": bundle.fixture_identity_conflict_count,
        "team_identity_conflict_count": bundle.team_identity_conflict_count,
        "competition_identity_conflict_count": bundle.competition_identity_conflict_count,
        "bundle_sha256": sha256_fotmob_fixture_candidate_bundle(bundle),
    }
    return (
        json.dumps(
            summary,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def main(
    argv: list[str] | None = None,
    *,
    repository_root: Path | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        repository = (repository_root or _repository_root()).resolve(strict=True)
        captures = []
        for value in args.capture_directory:
            capture, allowed_root = _capture_path(value, repository_root=repository)
            captures.append(_verified_capture(capture, allowed_root))
        bundle = build_fotmob_fixture_candidate_bundle(captures)
        sys.stdout.buffer.write(_summary_bytes(bundle))
        return 0
    except FotMobFixtureCandidateError as exc:
        parser.exit(1, f"candidate build failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
