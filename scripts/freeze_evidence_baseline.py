#!/usr/bin/env python3
"""Generate or verify a reproducible ATHENA evidence baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from domain.half_time_data import (  # noqa: E402
    HalfTimeObservation,
    ResearchReadiness,
    audit_half_time_coverage,
)
from domain.markets import MarketId  # noqa: E402
from domain.model_status import (  # noqa: E402
    MODEL_STATUS_REGISTRY,
    ModelStatus,
)
from scripts.audit_half_time_coverage import (  # noqa: E402
    load_observations_from_database,
)


SCHEMA_VERSION = 1
DEFAULT_BASELINE_NAME = "half-time-ready-for-research"
_CACHE_NAME_PATTERN = re.compile(
    r"^(?P<start>\d{2})(?P<end>\d{2})_(?P<league>[A-Z0-9]{1,8})\.csv$",
    re.IGNORECASE,
)
_AUDIT_COMPARISON_FIELDS = (
    "readiness",
    "total_historical_fixtures_inspected",
    "fixtures_with_valid_half_time_scores",
    "fixtures_missing_half_time_scores",
    "invalid_observations",
    "total_source_observations",
    "invalid_source_observations",
    "conflicting_fixtures",
    "fixtures_with_unknown_league_metadata",
    "coverage_percentage",
)


class BaselineError(RuntimeError):
    """A safe, user-facing baseline generation or verification error."""


def _canonical_json_bytes(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_datetime(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    normalized = value.astimezone(timezone.utc)
    return normalized.isoformat(timespec="microseconds").replace(
        "+00:00",
        "Z",
    )


def canonical_observation(observation: HalfTimeObservation) -> dict:
    """Return every evidence-relevant field in a stable JSON shape."""
    provenance = observation.half_time_score_provenance
    validation_status = observation.validation_status
    return {
        "authoritative_full_time_source": (
            observation.authoritative_full_time_source
        ),
        "conflict_fingerprint": observation.conflict_fingerprint,
        "conflict_observed_at": _canonical_datetime(
            observation.conflict_observed_at
        ),
        "conflict_reason": observation.conflict_reason,
        "conflict_status": bool(observation.conflict_status),
        "fixture_identity": observation.fixture_identity,
        "full_time_away_goals": observation.full_time_away_goals,
        "full_time_home_goals": observation.full_time_home_goals,
        "half_time_away_goals": observation.half_time_away_goals,
        "half_time_home_goals": observation.half_time_home_goals,
        "half_time_score_provenance": getattr(
            provenance,
            "value",
            str(provenance),
        ),
        "home_team": observation.home_team,
        "away_team": observation.away_team,
        "kickoff_time": _canonical_datetime(observation.kickoff_time),
        "league": observation.league,
        "observed_at": _canonical_datetime(observation.observed_at),
        "rejection_reasons": list(observation.rejection_reasons),
        "season": observation.season,
        "source": observation.source,
        "source_fixture_id": observation.source_fixture_id,
        "stored_full_time_away_goals": (
            observation.stored_full_time_away_goals
        ),
        "stored_full_time_home_goals": (
            observation.stored_full_time_home_goals
        ),
        "validation_status": getattr(
            validation_status,
            "value",
            str(validation_status),
        ),
    }


def logical_evidence_manifest(
    observations: Iterable[HalfTimeObservation],
) -> list:
    canonical = [canonical_observation(item) for item in observations]
    return sorted(canonical, key=_canonical_json_bytes)


def logical_evidence_sha256(
    observations: Iterable[HalfTimeObservation],
) -> str:
    return _sha256_bytes(
        _canonical_json_bytes(logical_evidence_manifest(observations))
    )


def _read_only_connection(database_path: Path) -> sqlite3.Connection:
    resolved = database_path.resolve()
    if not resolved.is_file():
        raise BaselineError(f"Database does not exist: {database_path}")
    connection = sqlite3.connect(
        f"{resolved.as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def database_schema_sha256(database_path: Path) -> str:
    connection = _read_only_connection(database_path)
    try:
        rows = connection.execute(
            """
            SELECT type, name, tbl_name, sql
            FROM sqlite_master
            WHERE sql IS NOT NULL
              AND name NOT LIKE 'sqlite_%'
            ORDER BY type, name, tbl_name
            """
        )
        schema = [
            {
                "name": row["name"],
                "sql": " ".join(str(row["sql"]).split()),
                "table": row["tbl_name"],
                "type": row["type"],
            }
            for row in rows
        ]
    finally:
        connection.close()
    return _sha256_bytes(_canonical_json_bytes(schema))


def _stream_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_filename_metadata(filename: str) -> tuple:
    match = _CACHE_NAME_PATTERN.fullmatch(filename)
    if not match:
        return None, None
    season = f"20{match.group('start')}-{match.group('end')}"
    return season, match.group("league").upper()


def build_cache_manifest(cache_directory: Path) -> dict:
    root = cache_directory.resolve()
    if not root.is_dir():
        raise BaselineError(
            f"Cache directory does not exist: {cache_directory}"
        )

    files = []
    for candidate in cache_directory.rglob("*"):
        if candidate.suffix.casefold() != ".csv":
            continue
        if candidate.is_symlink() or not candidate.is_file():
            continue
        resolved = candidate.resolve()
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError:
            continue
        season, league = _cache_filename_metadata(candidate.name)
        files.append(
            {
                "byte_size": resolved.stat().st_size,
                "league": league,
                "relative_path": relative,
                "season": season,
                "sha256": _stream_file_sha256(resolved),
            }
        )

    files.sort(
        key=lambda item: (
            item["relative_path"].casefold(),
            item["relative_path"],
        )
    )
    return {
        "file_count": len(files),
        "files": files,
        "manifest_sha256": _sha256_bytes(_canonical_json_bytes(files)),
    }


def _run_git(arguments: list, repository_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository_root), *arguments],
            capture_output=True,
            check=False,
            shell=False,
        )
    except FileNotFoundError as error:
        raise BaselineError("Git executable could not be found") from error
    stderr = result.stderr.decode("utf-8", errors="replace").strip()
    if result.returncode != 0:
        detail = " ".join(stderr.split())[:240]
        raise BaselineError(
            "Git repository state could not be determined"
            + (f": {detail}" if detail else "")
        )
    return result.stdout.decode("utf-8", errors="strict").strip()


def get_code_state(repository_root: Path = REPOSITORY_ROOT) -> dict:
    head = _run_git(["rev-parse", "HEAD"], repository_root)
    status = _run_git(
        ["status", "--porcelain", "--untracked-files=no"],
        repository_root,
    )
    if not re.fullmatch(r"[0-9a-fA-F]{40}", head):
        raise BaselineError("Git HEAD did not resolve to a full SHA")
    return {
        "git_head_sha": head.lower(),
        "tracked_worktree_clean": not bool(status),
    }


def _source_summary(audit: dict) -> dict:
    sources = {}
    for source, bucket in sorted(audit["source_breakdown"].items()):
        sources[source] = {
            **bucket,
            "local_file_identity": (
                "football_data_uk_cache_manifest"
                if source == "football_data_uk_csv"
                else "persisted_database_evidence_only"
            ),
            "source_file_sha256": None,
        }
    return sources


def _market_safety() -> dict:
    return {
        "away_win_either_half": MODEL_STATUS_REGISTRY[
            MarketId.AWAY_WIN_EITHER_HALF
        ].status.value,
        "home_win_either_half": MODEL_STATUS_REGISTRY[
            MarketId.HOME_WIN_EITHER_HALF
        ].status.value,
    }


def _generated_at_utc() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def build_evidence_baseline(
    *,
    database_path: Path,
    cache_directory: Path,
    baseline_name: str = DEFAULT_BASELINE_NAME,
    code_state: Optional[dict] = None,
    generated_at_utc: Optional[str] = None,
) -> dict:
    observations = tuple(
        load_observations_from_database(str(database_path))
    )
    audit = audit_half_time_coverage(observations).to_dict()
    return {
        "audit": audit,
        "baseline_name": str(baseline_name),
        "code": code_state if code_state is not None else get_code_state(),
        "database": {
            "logical_evidence_sha256": logical_evidence_sha256(
                observations
            ),
            "schema_sha256": database_schema_sha256(database_path),
        },
        "football_data_uk_cache": build_cache_manifest(cache_directory),
        "generated_at_utc": generated_at_utc or _generated_at_utc(),
        "market_safety": _market_safety(),
        "schema_version": SCHEMA_VERSION,
        "sources": _source_summary(audit),
    }


def validate_expectations(
    artifact: dict,
    *,
    total_fixtures: Optional[int] = None,
    valid_half_time: Optional[int] = None,
    missing_half_time: Optional[int] = None,
    cache_files: Optional[int] = None,
) -> None:
    expected = {
        "cache files": (
            cache_files,
            artifact["football_data_uk_cache"]["file_count"],
        ),
        "missing half-time observations": (
            missing_half_time,
            artifact["audit"]["fixtures_missing_half_time_scores"],
        ),
        "total fixtures": (
            total_fixtures,
            artifact["audit"]["total_historical_fixtures_inspected"],
        ),
        "valid half-time observations": (
            valid_half_time,
            artifact["audit"]["fixtures_with_valid_half_time_scores"],
        ),
    }
    failures = [
        f"{label}: expected {wanted}, found {actual}"
        for label, (wanted, actual) in expected.items()
        if wanted is not None and wanted != actual
    ]
    if failures:
        raise BaselineError("Expectation mismatch: " + "; ".join(failures))


def validate_ready_baseline(artifact: dict) -> None:
    audit = artifact["audit"]
    market_safety = artifact["market_safety"]
    failures = []
    if audit["readiness"] != ResearchReadiness.READY_FOR_RESEARCH.value:
        failures.append("readiness is not READY_FOR_RESEARCH")
    if audit["invalid_observations"] != 0:
        failures.append("invalid observations are present")
    if audit["invalid_source_observations"] != 0:
        failures.append("invalid source observations are present")
    if audit["conflicting_fixtures"]:
        failures.append("conflicting fixtures are present")
    if audit["fixtures_with_unknown_league_metadata"] != 0:
        failures.append("fixtures with unknown league metadata are present")
    if not artifact["code"]["tracked_worktree_clean"]:
        failures.append("tracked worktree is dirty")
    for key in ("home_win_either_half", "away_win_either_half"):
        if market_safety.get(key) != ModelStatus.DISABLED.value:
            failures.append(f"{key} is not DISABLED")
    if failures:
        raise BaselineError("Baseline safety gate failed: " + "; ".join(failures))


def write_baseline_atomic(
    output_path: Path,
    artifact: dict,
    *,
    force: bool = False,
) -> None:
    if output_path.exists() and not force:
        raise BaselineError(
            f"Baseline already exists; use --force to replace: {output_path}"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            dir=output_path.parent,
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            json.dump(
                artifact,
                stream,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, output_path)
        temporary_path = None
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def load_baseline(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as stream:
            artifact = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise BaselineError(f"Baseline could not be read: {path}") from error
    if not isinstance(artifact, dict):
        raise BaselineError("Baseline root must be a JSON object")
    if artifact.get("schema_version") != SCHEMA_VERSION:
        raise BaselineError(
            "Unsupported baseline schema_version: "
            f"{artifact.get('schema_version')!r}"
        )
    return artifact


def compare_baselines(stored: dict, current: dict) -> list:
    differences = []
    if stored.get("schema_version") != current.get("schema_version"):
        differences.append("baseline schema version differs")
    if stored.get("baseline_name") != current.get("baseline_name"):
        differences.append("baseline name differs")
    if stored.get("code", {}).get("git_head_sha") != current.get(
        "code", {}
    ).get("git_head_sha"):
        differences.append("Git revision differs")
    if stored.get("code", {}).get("tracked_worktree_clean") != current.get(
        "code", {}
    ).get("tracked_worktree_clean"):
        differences.append("tracked worktree cleanliness differs")
    for key, label in (
        ("logical_evidence_sha256", "logical evidence fingerprint differs"),
        ("schema_sha256", "database schema fingerprint differs"),
    ):
        if stored.get("database", {}).get(key) != current.get(
            "database", {}
        ).get(key):
            differences.append(label)
    stored_audit = stored.get("audit", {})
    current_audit = current.get("audit", {})
    changed_audit = [
        field
        for field in _AUDIT_COMPARISON_FIELDS
        if stored_audit.get(field) != current_audit.get(field)
    ]
    if changed_audit:
        differences.append(
            "audit totals/readiness differ: " + ", ".join(changed_audit)
        )
    if stored.get("sources") != current.get("sources"):
        differences.append("source totals differ")
    if stored.get("football_data_uk_cache", {}).get(
        "manifest_sha256"
    ) != current.get("football_data_uk_cache", {}).get("manifest_sha256"):
        differences.append("cache manifest fingerprint differs")
    if stored.get("market_safety") != current.get("market_safety"):
        differences.append("market safety state differs")
    return differences


def _non_negative_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a non-negative integer") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze or verify ATHENA's read-only historical evidence state."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path, help="Write a new baseline JSON.")
    mode.add_argument("--check", type=Path, help="Verify an existing baseline JSON.")
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("database/athena.db"),
    )
    parser.add_argument(
        "--cache-directory",
        type=Path,
        default=Path(".cache/football-data-uk"),
    )
    parser.add_argument("--baseline-name")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument("--expect-total-fixtures", type=_non_negative_integer)
    parser.add_argument("--expect-valid-half-time", type=_non_negative_integer)
    parser.add_argument("--expect-missing-half-time", type=_non_negative_integer)
    parser.add_argument("--expect-cache-files", type=_non_negative_integer)
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.check is not None and args.force:
        parser.error("--force is valid only with --output")
    if args.output is not None and args.output.exists() and not args.force:
        print(
            f"error: baseline already exists; use --force: {args.output}",
            file=sys.stderr,
        )
        return 1
    try:
        stored = load_baseline(args.check) if args.check else None
        baseline_name = (
            args.baseline_name
            or (
                stored["baseline_name"]
                if stored is not None
                else args.output.stem
            )
        )
        artifact = build_evidence_baseline(
            database_path=args.database,
            cache_directory=args.cache_directory,
            baseline_name=baseline_name,
        )
        validate_expectations(
            artifact,
            total_fixtures=args.expect_total_fixtures,
            valid_half_time=args.expect_valid_half_time,
            missing_half_time=args.expect_missing_half_time,
            cache_files=args.expect_cache_files,
        )
        if args.require_ready:
            validate_ready_baseline(artifact)
        if stored is not None:
            differences = compare_baselines(stored, artifact)
            if differences:
                print("Evidence baseline verification failed:", file=sys.stderr)
                for difference in differences:
                    print(f"  - {difference}", file=sys.stderr)
                return 1
            print(f"Evidence baseline verified: {args.check}")
            return 0
        write_baseline_atomic(args.output, artifact, force=args.force)
        print(f"Evidence baseline written: {args.output}")
        return 0
    except (BaselineError, OSError, sqlite3.Error, UnicodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
