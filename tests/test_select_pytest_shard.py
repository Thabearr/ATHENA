from __future__ import annotations

from pathlib import Path

import pytest

from scripts import select_pytest_shard as sharder


def _write_pytest_ini(root: Path, *, python_files: str = "test_*.py") -> None:
    (root / "pytest.ini").write_text(
        f"[pytest]\ntestpaths = tests\npython_files = {python_files}\n",
        encoding="utf-8",
    )


def _write_test(root: Path, relative: str, size: int) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    padding = "x" * max(0, size - len("def test_ok():\n    pass\n"))
    path.write_text("def test_ok():\n    pass\n" + padding, encoding="utf-8")
    return path


def test_assignment_is_deterministic_complete_disjoint_and_balanced(tmp_path: Path) -> None:
    _write_pytest_ini(tmp_path)
    sizes = (100, 200, 300, 400, 500, 600, 700, 800)
    expected = set()
    for index, size in enumerate(sizes):
        relative = f"tests/group_{index % 2}/test_case_{index}.py"
        expected.add(Path(relative))
        _write_test(tmp_path, relative, size)

    first = sharder.assign_test_files(tmp_path, total_shards=4)
    second = sharder.assign_test_files(tmp_path, total_shards=4)
    assert first == second

    flattened = [path for assignment in first for path in assignment.paths]
    assert set(flattened) == expected
    assert len(flattened) == len(expected)
    assert all(assignment.paths for assignment in first)

    loads = [assignment.total_bytes for assignment in first]
    assert max(loads) - min(loads) <= max(sizes)


def test_discovery_matches_repository_pytest_python_file_pattern(tmp_path: Path) -> None:
    _write_pytest_ini(tmp_path)
    _write_test(tmp_path, "tests/test_alpha.py", 100)
    _write_test(tmp_path, "tests/nested/test_beta.py", 100)
    _write_test(tmp_path, "tests/nested/gamma_test.py", 100)
    _write_test(tmp_path, "tests/nested/helper.py", 100)
    _write_test(tmp_path, "tests/nested/not_a_test.pyx", 100)
    expected = (Path("tests/nested/test_beta.py"), Path("tests/test_alpha.py"))
    assert sharder.discover_test_files(tmp_path) == expected


def test_pytest_config_drift_fails_closed(tmp_path: Path) -> None:
    _write_pytest_ini(tmp_path, python_files="*_test.py")
    _write_test(tmp_path, "tests/test_alpha.py", 100)
    with pytest.raises(sharder.PytestShardError, match="python_files changed"):
        sharder.discover_test_files(tmp_path)


def test_invalid_shard_requests_fail_closed(tmp_path: Path) -> None:
    _write_pytest_ini(tmp_path)
    _write_test(tmp_path, "tests/test_only.py", 100)
    with pytest.raises(sharder.PytestShardError, match="positive"):
        sharder.assign_test_files(tmp_path, total_shards=0)
    with pytest.raises(sharder.PytestShardError, match="exceed"):
        sharder.assign_test_files(tmp_path, total_shards=2)
    with pytest.raises(sharder.PytestShardError, match="range"):
        sharder.select_shard(tmp_path, total_shards=1, shard_index=1)


def test_repository_four_shards_cover_every_current_test_file_exactly_once() -> None:
    repository = Path(__file__).resolve().parents[1]
    expected = sharder.discover_test_files(repository)
    assignments = sharder.assign_test_files(repository, total_shards=4)
    flattened = tuple(path for assignment in assignments for path in assignment.paths)
    assert len(flattened) == len(expected)
    assert set(flattened) == set(expected)
    assert all(assignment.paths for assignment in assignments)
