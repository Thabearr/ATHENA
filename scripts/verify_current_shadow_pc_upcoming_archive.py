"""Offline exact-byte retention audit; never acquires or promotes source data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat

from domain import current_shadow_sportybet_pc_upcoming_discovery as discovery
from domain import current_shadow_sportybet_pc_upcoming_reconciliation as runtime

OUTPUT = Path("artifacts/current-shadow-all-market")
SOURCE_ROOTS = (
    Path(".cache/athena-research/current-shadow-sportybet-catalog-fanout"),
    Path(".cache/athena-research/current-shadow-sportybet-upcoming-discovery"),
    discovery.EVIDENCE_ROOT,
    Path(".cache/athena-research/sportybet-live-event-quote-evidence"),
    Path(".cache/athena-research/fotmob-data-matches-captures"),
)
DIAGNOSTIC = "pc-upcoming-archive-verification.json"


class PcUpcomingArchiveError(ValueError):
    pass


def _safe_path(path: Path) -> Path:
    """lstat every component, before reading anything through it (also Windows)."""
    if ".." in path.parts:
        raise PcUpcomingArchiveError("evidence path traversal")
    path = path.absolute()
    cursor = Path(path.anchor)
    for index, part in enumerate(path.parts[1:]):
        cursor /= part
        try:
            info = cursor.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(info.st_mode)
                or getattr(cursor, "is_junction", lambda: False)()
                or getattr(info, "st_file_attributes", 0)
                    & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
            raise PcUpcomingArchiveError("evidence path contains a linked component")
        if not stat.S_ISDIR(info.st_mode):
            if index != len(path.parts) - 2 or not stat.S_ISREG(info.st_mode):
                raise PcUpcomingArchiveError("evidence path contains a nonregular component")
            if info.st_nlink != 1:
                raise PcUpcomingArchiveError("evidence file has multiple hard links")
    return path


def _roots(repository_root: Path, output_root: Path) -> tuple[Path, Path]:
    if not isinstance(repository_root, Path) or not isinstance(output_root, Path):
        raise PcUpcomingArchiveError("roots must be Path values")
    repository = _safe_path(repository_root)
    output = _safe_path(output_root)
    if output != repository / OUTPUT:
        raise PcUpcomingArchiveError("archive must use the fixed repository output root")
    return repository, output


def _file_inventory(root: Path) -> dict[str, tuple[int, str]]:
    root = _safe_path(root)
    if not root.is_dir():
        raise PcUpcomingArchiveError("evidence root is absent or not a directory")
    files = {}
    # Never follow directory links, including a symlink encountered during traversal.
    for directory, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            path = _safe_path(Path(directory) / name)
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                continue
            if not stat.S_ISREG(info.st_mode):
                raise PcUpcomingArchiveError("evidence contains a nonregular entry")
            files[path.relative_to(root).as_posix()] = (
                info.st_size, hashlib.sha256(path.read_bytes()).hexdigest())
    return files


def _json_unique(raw):
    def mapping(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise PcUpcomingArchiveError("duplicate receipt JSON key")
            value[key] = item
        return value
    def invalid_constant(value):
        raise PcUpcomingArchiveError("non-JSON numeric constant")
    return json.loads(raw, object_pairs_hook=mapping, parse_constant=invalid_constant)


def _summary(receipt_path: Path) -> dict:
    _safe_path(receipt_path)
    if not receipt_path.exists():
        return {}
    value = _json_unique(receipt_path.read_bytes())
    if type(value) is not dict or type(value.get("source_summary", {})) is not dict:
        raise PcUpcomingArchiveError("run receipt/source_summary is not a mapping")
    return value.get("source_summary", {})


def _claims(summary: dict) -> bool:
    keys = {key for key in summary if key.startswith("provider_discovery_")}
    # Unknown discovery fields cannot silently redefine the claim state.
    allowed = {"strategy_id", "manifest_sha256", "page_count", "event_count",
               "observation_count", "source_method", "pagination_complete",
               "first_observed_at", "last_observed_at", "observed_at"}
    if keys - {"provider_discovery_" + key for key in allowed}:
        raise PcUpcomingArchiveError("unrecognized discovery claim field")
    integer_bounds = {"provider_discovery_page_count": discovery.MAX_PAGES,
                      "provider_discovery_observation_count": discovery.MAX_PAGES,
                      "provider_discovery_event_count": discovery.MAX_PAGES * discovery.PAGE_SIZE,
                      "provider_total_num": discovery.MAX_PAGES * discovery.PAGE_SIZE,
                      "provider_event_count": discovery.MAX_PAGES * discovery.PAGE_SIZE}
    for key, bound in integer_bounds.items():
        if key in summary and (type(summary[key]) is not int or not 0 <= summary[key] <= bound):
            raise PcUpcomingArchiveError("discovery count must be an exact bounded integer: " + key)
    key = "provider_discovery_pagination_complete"
    if key in summary and type(summary[key]) is not bool:
        raise PcUpcomingArchiveError("discovery completeness must be a boolean")
    for key, expected in {
        "provider_discovery_source_method": runtime.DISCOVERY_SOURCE_METHOD,
        "provider_discovery_strategy_id": runtime.CURRENT_SHADOW_UPCOMING_POLICY_ID,
    }.items():
        if key in summary and summary[key] != expected:
            raise PcUpcomingArchiveError("discovery source identity mismatch: " + key)
    sha = summary.get("provider_discovery_manifest_sha256")
    if "provider_discovery_manifest_sha256" in summary and (
            type(sha) is not str or re.fullmatch(r"[0-9a-f]{64}", sha) is None):
        raise PcUpcomingArchiveError("discovery manifest SHA must be lowercase SHA256")
    # Presence has meaning: even zero-valued discovery fields cannot mean no attempt.
    return bool(keys or "provider_total_num" in summary or "provider_event_count" in summary)


def _match_manifest(summary: dict, manifest) -> None:
    expected = {
        "provider_discovery_manifest_sha256": manifest.canonical_sha256,
        "provider_discovery_page_count": manifest.captured_page_count,
        "provider_discovery_event_count": manifest.captured_event_count,
        "provider_discovery_observation_count": manifest.captured_page_count,
        "provider_discovery_pagination_complete": True,
        "provider_discovery_source_method": runtime.DISCOVERY_SOURCE_METHOD,
        "provider_discovery_strategy_id": runtime.CURRENT_SHADOW_UPCOMING_POLICY_ID,
    }
    for key, value in expected.items():
        if key not in summary or type(summary[key]) is not type(value) or summary[key] != value:
            raise PcUpcomingArchiveError("run receipt differs from accepted discovery: " + key)
    optional = {
        "provider_total_num": manifest.provider_total_num,
        "provider_event_count": manifest.captured_event_count,
        "provider_discovery_first_observed_at": manifest.first_observed_at.isoformat().replace("+00:00", "Z"),
        "provider_discovery_last_observed_at": manifest.last_observed_at.isoformat().replace("+00:00", "Z"),
        "provider_discovery_observed_at": manifest.last_observed_at.isoformat().replace("+00:00", "Z"),
    }
    for key, value in optional.items():
        if key in summary and (type(summary[key]) is not type(value) or summary[key] != value):
            raise PcUpcomingArchiveError("run receipt source correspondence mismatch: " + key)


def _runtime_inventory(root: Path, state, files: dict) -> None:
    """Require a closed file set after source-owned semantic replay.

    This adds archive inventory closure, not a second journal validator. Page
    and raw-response rows are read by the source's authenticated readers.
    """
    expected = {runtime.STABILIZATION_RECEIPT_FILENAME}
    allowed_dirs = {runtime.RUNTIME_ATTEMPTS_DIRECTORY}
    for index in range(1, state["attempt_count"] + 1):
        prefix = f"{runtime.RUNTIME_ATTEMPTS_DIRECTORY}/attempt-{index:03d}"
        attempt = root / prefix
        allowed_dirs.update({prefix, prefix + "/pages", prefix + "/raw-responses"})
        expected.add(prefix + "/attempt-receipt.json")
        for name in ("page-observations.json", runtime.RAW_RESPONSE_JOURNAL_FILENAME,
                     runtime.PARSE_FAILURE_FILENAME, "manifest.json"):
            if (attempt / name).exists():
                expected.add(prefix + "/" + name)
        expected.update(prefix + f"/pages/page-{row['page_num']:03d}.raw.json"
                        for row in runtime._read_page_observations(attempt))
        expected.update(prefix + "/" + row["raw_relative_path"]
                        for row in runtime._read_raw_response_observations(attempt))
    if state["accepted_attempt_index"] is not None:
        manifest = discovery._verify_manifest_at_root(evidence_root=root)
        expected.add("manifest.json")
        expected.update(page.raw_relative_path for page in manifest.pages)
        allowed_dirs.add("pages")
    if set(files) != expected:
        raise PcUpcomingArchiveError("capture file inventory contains unbound or missing evidence")
    for directory, dirs, _ in os.walk(root, followlinks=False):
        for name in dirs:
            if (Path(directory) / name).relative_to(root).as_posix() not in allowed_dirs:
                raise PcUpcomingArchiveError("capture directory is not a recorded runtime epoch")


def verify_archive(*, repository_root: Path, output_root: Path) -> dict[str, object]:
    try:
        repository, output = _roots(repository_root, output_root)
        original = _safe_path(repository / discovery.EVIDENCE_ROOT)
        preserved = _safe_path(output / "source-evidence" / discovery.EVIDENCE_ROOT.name)
        summary = _summary(output / "current-shadow-all-market-run-receipt.json")
        claimed = _claims(summary)
        if not original.exists() and not preserved.exists():
            if claimed:
                raise PcUpcomingArchiveError("discovery claims exist but original/archive are absent")
            return {"status": "NOT_ACQUIRED", "file_count": 0}
        source_files = _file_inventory(original)
        archive_files = _file_inventory(preserved)
        if not source_files or source_files != archive_files:
            raise PcUpcomingArchiveError("archive is incomplete or byte-inconsistent")
        # Source-owned replay uses its ORIGINAL repository + fixed EVIDENCE_ROOT.
        state = runtime.verify_runtime_capture_stabilization(repository_root=repository)
        _runtime_inventory(original, state, source_files)
        _runtime_inventory(preserved, state, archive_files)
        if state["accepted_attempt_index"] is None:
            if claimed:
                raise PcUpcomingArchiveError("failed capture cannot support discovery claims")
            return {"status": "VERIFIED_PARTIAL_CAPTURE", "file_count": len(archive_files),
                    "runtime_final_state": state["final_state"]}
        manifest = discovery._verify_manifest_at_root(evidence_root=preserved)
        _match_manifest(summary, manifest)
        return {"status": "VERIFIED_COMPLETE", "file_count": len(archive_files),
                "manifest_sha256": manifest.canonical_sha256,
                "runtime_final_state": state["final_state"]}
    except (ValueError, OSError, TypeError, KeyError) as exc:
        raise PcUpcomingArchiveError(str(exc)) from exc


def preserve_evidence(*, repository_root: Path, output_root: Path) -> None:
    """Collect independent evidence even if another source tree is malformed."""
    repository, output = _roots(repository_root, output_root)
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    identity = os.environ.get("ATHENA_CURRENT_SHADOW_IDENTITY_STATE_PATH", "")
    if identity:
        try:
            identity_path = Path(identity)
            if not identity_path.is_absolute():
                identity_path = repository / identity_path
            identity_path = _safe_path(identity_path)
            identity_path.relative_to(repository)
            if identity_path.exists():
                if not identity_path.is_file():
                    raise PcUpcomingArchiveError("identity state is not a regular file")
                destination = _safe_path(output / "identity-state" / identity_path.name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(identity_path, destination)
        except (ValueError, OSError) as exc:
            errors.append("identity: " + str(exc))
    for relative in SOURCE_ROOTS:
        try:
            original = _safe_path(repository / relative)
            if original.exists():
                _file_inventory(original)
                destination = _safe_path(output / "source-evidence" / relative.name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    raise PcUpcomingArchiveError("archive destination already exists")
                shutil.copytree(original, destination, symlinks=False)
        except (ValueError, OSError) as exc:
            errors.append(relative.as_posix() + ": " + str(exc))
    if errors:
        raise PcUpcomingArchiveError("; ".join(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path, default=OUTPUT)
    parser.add_argument("--preserve", action="store_true")
    args = parser.parse_args(argv)
    try:
        repository, output = _roots(args.repository_root, args.output_root)
        if args.preserve:
            preserve_evidence(repository_root=repository, output_root=output)
            result = {"status": "PRESERVED_PENDING_VERIFICATION"}
        else:
            # A failed preservation must never be overwritten by a green replay.
            prior = _safe_path(output / "pc-upcoming-archive-preservation.json")
            if prior.exists() and json.loads(prior.read_bytes()).get("status") == "FAILED":
                raise PcUpcomingArchiveError("independent evidence preservation failed")
            result = verify_archive(repository_root=repository, output_root=output)
        code = 0
    except (ValueError, OSError, TypeError) as exc:
        result, code = {"status": "FAILED", "error": str(exc)}, 2
    # Only write diagnostics through the same trusted, fixed archive root.
    _, output = _roots(args.repository_root, args.output_root)
    output.mkdir(parents=True, exist_ok=True)
    name = "pc-upcoming-archive-preservation.json" if args.preserve else DIAGNOSTIC
    destination = _safe_path(output / name)
    destination.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
