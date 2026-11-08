"""Offline-only exact-byte audit of the legacy Current Shadow pcUpcoming archive.

This audit runs after the research worker, never acquires provider data, and
fails if a completed discovery claims evidence absent from the uploaded tree.
It also copies no files and never mutates historical evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
from pathlib import Path

from domain import current_shadow_sportybet_pc_upcoming_discovery as discovery


class PcUpcomingArchiveError(ValueError):
    pass


def _file_inventory(root: Path) -> dict[str, tuple[int, str]]:
    if root.is_symlink() or not root.is_dir():
        raise PcUpcomingArchiveError("pcUpcoming evidence root is absent, linked or not a directory")
    files: dict[str, tuple[int, str]] = {}
    for path in root.rglob("*"):
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode):
            raise PcUpcomingArchiveError("pcUpcoming evidence contains a nonregular path")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        files[path.relative_to(root).as_posix()] = (info.st_size, digest.hexdigest())
    return files


def verify_archive(*, repository_root: Path, output_root: Path) -> dict[str, object]:
    if not isinstance(repository_root, Path) or not isinstance(output_root, Path):
        raise PcUpcomingArchiveError("repository_root and output_root must be Path values")
    original = repository_root / discovery.EVIDENCE_ROOT
    preserved = output_root / "source-evidence" / discovery.EVIDENCE_ROOT.name
    receipt_path = output_root / "current-shadow-all-market-run-receipt.json"
    expected_sha = None
    expected_pages = None
    expected_events = None
    expected_pagination = None
    if receipt_path.is_file():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            summary = receipt.get("source_summary") or {}
            if type(summary) is not dict:
                raise ValueError("source_summary is not a mapping")
            expected_sha = summary.get("provider_discovery_manifest_sha256")
            expected_pages = summary.get("provider_discovery_page_count")
            expected_events = summary.get("provider_discovery_event_count")
            expected_pagination = summary.get("provider_discovery_pagination_complete")
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            raise PcUpcomingArchiveError("run receipt source-summary cannot be verified") from exc

    source_exists = original.exists() or original.is_symlink()
    archive_exists = preserved.exists() or preserved.is_symlink()
    if not source_exists and not archive_exists:
        if expected_sha is not None:
            raise PcUpcomingArchiveError("receipt claims complete pcUpcoming discovery but its source and archive are absent")
        return {"status": "NOT_ACQUIRED", "file_count": 0}

    if not source_exists or not archive_exists:
        raise PcUpcomingArchiveError("pcUpcoming original/archive evidence directories differ in presence")
    source_files = _file_inventory(original)
    archive_files = _file_inventory(preserved)
    if not source_files or source_files != archive_files:
        raise PcUpcomingArchiveError("pcUpcoming archive is incomplete or byte-inconsistent")

    manifest_path = preserved / "manifest.json"
    if expected_sha is not None and (type(expected_sha) is not str or not manifest_path.is_file()):
        raise PcUpcomingArchiveError("completed discovery manifest is not archived")
    if manifest_path.is_file():
        try:
            manifest = discovery._verify_manifest_at_root(evidence_root=preserved)
        except (ValueError, OSError, TypeError) as exc:
            raise PcUpcomingArchiveError("archived pcUpcoming manifest and exact pages fail replay") from exc
        if expected_sha is not None and (
            manifest.canonical_sha256 != expected_sha
            or manifest.captured_page_count != expected_pages
            or manifest.captured_event_count != expected_events
            or manifest.pagination_complete is not expected_pagination
        ):
            raise PcUpcomingArchiveError("archived pcUpcoming source does not match run receipt")
        if expected_sha is not None:
            for required in ("runtime-capture-stabilization.json", "runtime-attempts"):
                if not (preserved / required).exists():
                    raise PcUpcomingArchiveError(f"pcUpcoming capture-epoch evidence missing: {required}")
        return {"status": "VERIFIED_COMPLETE", "file_count": len(archive_files), "manifest_sha256": manifest.canonical_sha256}
    if expected_sha is not None:
        raise PcUpcomingArchiveError("completed pcUpcoming discovery lacks an archived manifest")
    return {"status": "VERIFIED_PARTIAL_CAPTURE", "file_count": len(archive_files)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/current-shadow-all-market"))
    args = parser.parse_args(argv)
    try:
        result = verify_archive(repository_root=args.repository_root, output_root=args.output_root)
    except PcUpcomingArchiveError as exc:
        parser.exit(2, f"pcUpcoming archive verification failed: {exc}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
