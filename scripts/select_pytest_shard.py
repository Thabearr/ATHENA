#!/usr/bin/env python3
"""Deterministically partition the existing pytest file suite across CI shards.

The sharder preserves ATHENA's configured ``pytest tests`` file-discovery boundary
(``python_files = test_*.py``) while running each test file exactly once across
isolated GitHub Actions runners. Files are assigned with deterministic largest-first
greedy balancing using file size as a cheap, result-independent proxy for work.
Runtime durations are reported by CI and may support a later reviewed weighting
refinement without dropping coverage.
"""
from __future__ import annotations

import argparse
import fnmatch
import sys
from dataclasses import dataclass
from pathlib import Path

PYTEST_FILE_PATTERN = "test_*.py"


class PytestShardError(ValueError):
    """Raised when a shard request or test-suite layout is invalid."""


@dataclass(frozen=True)
class ShardAssignment:
    shard_index: int
    paths: tuple[Path, ...]
    total_bytes: int


def discover_test_files(repository_root: Path) -> tuple[Path, ...]:
    root = Path(repository_root).resolve(strict=True)
    tests_root = root / "tests"
    if not tests_root.is_dir():
        raise PytestShardError("repository tests directory is missing")

    discovered: list[Path] = []
    for path in tests_root.rglob("*.py"):
        if not path.is_file():
            continue
        if any(part == "__pycache__" for part in path.parts):
            continue
        if not fnmatch.fnmatchcase(path.name, PYTEST_FILE_PATTERN):
            continue
        relative = path.relative_to(root)
        if "\n" in relative.as_posix() or "\r" in relative.as_posix():
            raise PytestShardError("test path contains a forbidden newline")
        discovered.append(relative)

    result = tuple(sorted(set(discovered), key=lambda item: item.as_posix()))
    if not result:
        raise PytestShardError("no pytest test files were discovered")
    return result


def assign_test_files(
    repository_root: Path,
    *,
    total_shards: int,
) -> tuple[ShardAssignment, ...]:
    if type(total_shards) is not int or total_shards <= 0:
        raise PytestShardError("total_shards must be a positive integer")

    root = Path(repository_root).resolve(strict=True)
    files = discover_test_files(root)
    if total_shards > len(files):
        raise PytestShardError("total_shards may not exceed discovered test-file count")

    weighted = sorted(
        ((max(1, (root / path).stat().st_size), path) for path in files),
        key=lambda item: (-item[0], item[1].as_posix()),
    )
    shard_paths: list[list[Path]] = [[] for _ in range(total_shards)]
    shard_bytes = [0 for _ in range(total_shards)]

    for weight, path in weighted:
        target = min(range(total_shards), key=lambda index: (shard_bytes[index], index))
        shard_paths[target].append(path)
        shard_bytes[target] += weight

    assignments = tuple(
        ShardAssignment(
            shard_index=index,
            paths=tuple(sorted(paths, key=lambda item: item.as_posix())),
            total_bytes=shard_bytes[index],
        )
        for index, paths in enumerate(shard_paths)
    )

    flattened = [path for assignment in assignments for path in assignment.paths]
    if len(flattened) != len(files) or set(flattened) != set(files):
        raise PytestShardError("shard assignment omitted or duplicated test files")
    if any(not assignment.paths for assignment in assignments):
        raise PytestShardError("every configured shard must receive at least one test file")
    return assignments


def select_shard(
    repository_root: Path,
    *,
    total_shards: int,
    shard_index: int,
) -> ShardAssignment:
    if type(shard_index) is not int or not 0 <= shard_index < total_shards:
        raise PytestShardError("shard_index must be within the configured shard range")
    return assign_test_files(repository_root, total_shards=total_shards)[shard_index]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Select one deterministic pytest file shard")
    parser.add_argument("--total-shards", required=True, type=int)
    parser.add_argument("--shard-index", required=True, type=int)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="write shard count/weight diagnostics to stderr",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        assignment = select_shard(
            args.repository_root,
            total_shards=args.total_shards,
            shard_index=args.shard_index,
        )
    except (OSError, PytestShardError) as exc:
        raise SystemExit(f"pytest shard selection failed: {exc}") from exc

    if args.summary:
        print(
            f"pytest shard {assignment.shard_index}/{args.total_shards - 1}: "
            f"{len(assignment.paths)} files, {assignment.total_bytes} source bytes",
            file=sys.stderr,
        )
    for path in assignment.paths:
        print(path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
