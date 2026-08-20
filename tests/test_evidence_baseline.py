import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from database.database import Database
from domain.model_status import ModelStatus, PricingAuthority, SelectionAuthority
from scripts.freeze_evidence_baseline import (
    BaselineError,
    LEGACY_SCHEMA_VERSION,
    SCHEMA_VERSION,
    build_cache_manifest,
    build_evidence_baseline,
    compare_baselines,
    database_schema_sha256,
    load_baseline,
    main,
    get_code_state,
    rebuild_evidence_baseline_for_verification,
    validate_expectations,
    validate_ready_baseline,
    verify_revision_relationship,
    write_baseline_atomic,
)


class EvidenceBaselineTests(unittest.TestCase):
    REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
    CODE_STATE = {
        "evidence_git_head_sha": "a" * 40,
        "tracked_worktree_clean": True,
    }

    @staticmethod
    def _database_rows(database_path, query, parameters=()):
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        try:
            return [
                dict(row)
                for row in connection.execute(query, parameters)
            ]
        finally:
            connection.close()

    def _create_database(
        self,
        database_path: Path,
        *,
        insertion_order=(1, 2),
        missing_fixture_ids=(),
        half_time_overrides=None,
        full_time_overrides=None,
        conflict_fixture_ids=(),
        unknown_league_fixture_ids=(),
    ):
        Database(str(database_path)).initialize()
        half_time_overrides = half_time_overrides or {}
        full_time_overrides = full_time_overrides or {}
        connection = sqlite3.connect(database_path)
        try:
            for fixture_id in insertion_order:
                home_id = fixture_id * 10 + 1
                away_id = fixture_id * 10 + 2
                connection.execute(
                    """
                    INSERT INTO teams (team_id, name, league)
                    VALUES (?, ?, ?)
                    """,
                    (home_id, f"Home {fixture_id}", "E0"),
                )
                connection.execute(
                    """
                    INSERT INTO teams (team_id, name, league)
                    VALUES (?, ?, ?)
                    """,
                    (away_id, f"Away {fixture_id}", "E0"),
                )
                full_time = full_time_overrides.get(fixture_id, (2, 1))
                league = (
                    None
                    if fixture_id in unknown_league_fixture_ids
                    else "E0"
                )
                connection.execute(
                    """
                    INSERT INTO historical_matches (
                        fixture_id, home_id, away_id, home_goals,
                        away_goals, match_date, data_source,
                        season_label, league_code
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fixture_id,
                        home_id,
                        away_id,
                        full_time[0],
                        full_time[1],
                        f"2024-08-0{fixture_id}T15:00:00+00:00",
                        "football_data_uk_csv",
                        "2024-25",
                        league,
                    ),
                )
                if fixture_id in missing_fixture_ids:
                    continue
                half_time = half_time_overrides.get(fixture_id, (1, 0))
                conflict = fixture_id in conflict_fixture_ids
                connection.execute(
                    """
                    INSERT INTO half_time_observations (
                        fixture_identity, home_team, away_team,
                        kickoff_time, full_time_home_goals,
                        full_time_away_goals, half_time_home_goals,
                        half_time_away_goals, source, observed_at,
                        source_fixture_id, half_time_score_provenance,
                        validation_status, rejection_reasons, league,
                        season, conflict_status, conflict_fingerprint,
                        conflict_reason, conflict_observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(fixture_id),
                        f"Home {fixture_id}",
                        f"Away {fixture_id}",
                        f"2024-08-0{fixture_id}T15:00:00+00:00",
                        full_time[0],
                        full_time[1],
                        half_time[0],
                        half_time[1],
                        "football_data_uk_csv",
                        "2024-08-10T12:00:00+00:00",
                        f"source-{fixture_id}",
                        "OBSERVED",
                        "VALID",
                        "[]",
                        league,
                        "2024-25",
                        int(conflict),
                        "conflict-fingerprint" if conflict else None,
                        "conflicting scores received" if conflict else None,
                        (
                            "2024-08-11T12:00:00+00:00"
                            if conflict
                            else None
                        ),
                    ),
                )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _create_cache(cache_directory: Path):
        nested = cache_directory / "nested"
        nested.mkdir(parents=True)
        (cache_directory / "2425_E0.csv").write_bytes(b"a,b\n1,2\n")
        (nested / "2324_D1.csv").write_bytes(b"x,y\n3,4\n")
        (nested / "unmapped.csv").write_bytes(b"z\n5\n")

    def _git(self, repository: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            shell=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def _create_git_repository(self, repository: Path) -> str:
        repository.mkdir(parents=True)
        self._git(repository, "init")
        self._git(repository, "config", "user.name", "ATHENA Tests")
        self._git(
            repository,
            "config",
            "user.email",
            "athena-tests@example.invalid",
        )
        (repository / "artifacts").mkdir()
        (repository / "artifacts" / "baseline.json").write_text(
            "{}\n",
            encoding="utf-8",
        )
        (repository / "tracked.txt").write_text(
            "evidence code state\n",
            encoding="utf-8",
        )
        self._git(repository, "add", "artifacts/baseline.json", "tracked.txt")
        self._git(repository, "commit", "-m", "evidence revision")
        return self._git(repository, "rev-parse", "HEAD")

    def _build(
        self,
        database_path: Path,
        cache_directory: Path,
        *,
        generated_at="2026-07-31T00:00:00Z",
    ):
        return build_evidence_baseline(
            database_path=database_path,
            cache_directory=cache_directory,
            baseline_name="test-baseline",
            code_state=deepcopy(self.CODE_STATE),
            generated_at_utc=generated_at,
        )

    @staticmethod
    def _ready_artifact():
        return {
            "audit": {
                "readiness": "READY_FOR_RESEARCH",
                "invalid_observations": 0,
                "invalid_source_observations": 0,
                "conflicting_fixtures": [],
                "fixtures_with_unknown_league_metadata": 0,
                "total_historical_fixtures_inspected": 21829,
                "fixtures_with_valid_half_time_scores": 21791,
                "fixtures_missing_half_time_scores": 38,
            },
            "code": {
                "evidence_git_head_sha": "a" * 40,
                "tracked_worktree_clean": True,
            },
            "football_data_uk_cache": {"file_count": 66},
            "market_safety": {
                "home_win_either_half": {
                    "model_status": "EXPERIMENTAL",
                    "pricing_authority": "NOT_AUTHORIZED",
                    "selection_authority": "NOT_AUTHORIZED",
                },
                "away_win_either_half": {
                    "model_status": "EXPERIMENTAL",
                    "pricing_authority": "NOT_AUTHORIZED",
                    "selection_authority": "NOT_AUTHORIZED",
                },
            },
            "schema_version": SCHEMA_VERSION,
        }

    def test_output_is_deterministic_across_database_insertion_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_db = root / "first.db"
            second_db = root / "second.db"
            cache = root / "cache"
            self._create_cache(cache)
            self._create_database(first_db, insertion_order=(1, 2))
            self._create_database(second_db, insertion_order=(2, 1))

            first = self._build(first_db, cache)
            second = self._build(second_db, cache)

            self.assertEqual(first["database"], second["database"])
            self.assertEqual(first["audit"], second["audit"])
            self.assertEqual(first["sources"], second["sources"])
            self.assertEqual(
                first["market_safety"]["home_win_either_half"],
                {
                    "model_status": ModelStatus.EXPERIMENTAL.value,
                    "pricing_authority": PricingAuthority.NOT_AUTHORIZED.value,
                    "selection_authority": SelectionAuthority.NOT_AUTHORIZED.value,
                },
            )
            self.assertEqual(
                first["market_safety"]["away_win_either_half"],
                {
                    "model_status": ModelStatus.EXPERIMENTAL.value,
                    "pricing_authority": PricingAuthority.NOT_AUTHORIZED.value,
                    "selection_authority": SelectionAuthority.NOT_AUTHORIZED.value,
                },
            )

    def test_new_baseline_is_truthful_and_v1_is_verification_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "athena.db"
            cache = root / "cache"
            self._create_database(database)
            self._create_cache(cache)
            current = self._build(database, cache)
            self.assertEqual(current["schema_version"], SCHEMA_VERSION)
            self.assertEqual(
                current["market_safety"]["home_win_either_half"],
                {
                    "model_status": "EXPERIMENTAL",
                    "pricing_authority": "NOT_AUTHORIZED",
                    "selection_authority": "NOT_AUTHORIZED",
                },
            )

            legacy = deepcopy(current)
            legacy["schema_version"] = LEGACY_SCHEMA_VERSION
            legacy["market_safety"] = {
                "away_win_either_half": "DISABLED",
                "home_win_either_half": "DISABLED",
            }
            rebuilt = rebuild_evidence_baseline_for_verification(
                legacy,
                database_path=database,
                cache_directory=cache,
                baseline_name=legacy["baseline_name"],
                code_state=legacy["code"],
                generated_at_utc=legacy["generated_at_utc"],
            )
            self.assertEqual(rebuilt, legacy)
            self.assertEqual(
                build_evidence_baseline(
                    database_path=database,
                    cache_directory=cache,
                    baseline_name=legacy["baseline_name"],
                    code_state=legacy["code"],
                    generated_at_utc=legacy["generated_at_utc"],
                )["schema_version"],
                SCHEMA_VERSION,
            )

    def test_logical_fingerprint_changes_for_ht_and_ft_score_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "cache"
            self._create_cache(cache)
            original_db = root / "original.db"
            ht_changed_db = root / "ht-changed.db"
            ft_changed_db = root / "ft-changed.db"
            self._create_database(original_db)
            self._create_database(
                ht_changed_db,
                half_time_overrides={1: (0, 1)},
            )
            self._create_database(
                ft_changed_db,
                full_time_overrides={1: (3, 1)},
            )

            original = self._build(original_db, cache)["database"][
                "logical_evidence_sha256"
            ]
            ht_changed = self._build(ht_changed_db, cache)["database"][
                "logical_evidence_sha256"
            ]
            ft_changed = self._build(ft_changed_db, cache)["database"][
                "logical_evidence_sha256"
            ]

            self.assertNotEqual(original, ht_changed)
            self.assertNotEqual(original, ft_changed)

    def test_logical_fingerprint_changes_when_missing_becomes_populated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "cache"
            self._create_cache(cache)
            missing_db = root / "missing.db"
            populated_db = root / "populated.db"
            self._create_database(missing_db, missing_fixture_ids=(1,))
            self._create_database(populated_db)

            missing = self._build(missing_db, cache)
            populated = self._build(populated_db, cache)

            self.assertNotEqual(
                missing["database"]["logical_evidence_sha256"],
                populated["database"]["logical_evidence_sha256"],
            )
            self.assertEqual(
                missing["audit"]["fixtures_missing_half_time_scores"],
                1,
            )
            self.assertEqual(
                populated["audit"]["fixtures_missing_half_time_scores"],
                0,
            )

    def test_logical_fingerprint_includes_conflict_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "cache"
            self._create_cache(cache)
            clean_db = root / "clean.db"
            conflict_db = root / "conflict.db"
            self._create_database(clean_db)
            self._create_database(conflict_db, conflict_fixture_ids=(1,))

            clean = self._build(clean_db, cache)
            conflict = self._build(conflict_db, cache)

            self.assertNotEqual(
                clean["database"]["logical_evidence_sha256"],
                conflict["database"]["logical_evidence_sha256"],
            )
            self.assertEqual(conflict["audit"]["conflicting_fixtures"], ["1"])

    def test_generated_timestamp_does_not_affect_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "cache"
            database = root / "athena.db"
            self._create_cache(cache)
            self._create_database(database)
            first = self._build(
                database,
                cache,
                generated_at="2026-07-31T00:00:00Z",
            )
            second = self._build(
                database,
                cache,
                generated_at="2026-08-01T00:00:00Z",
            )

            self.assertNotEqual(first["generated_at_utc"], second["generated_at_utc"])
            self.assertEqual(compare_baselines(first, second), [])

    def test_schema_fingerprint_is_deterministic_and_data_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.db"
            second = root / "second.db"
            self._create_database(first, insertion_order=(1, 2))
            self._create_database(second, insertion_order=(2, 1))

            self.assertEqual(
                database_schema_sha256(first),
                database_schema_sha256(second),
            )
            self.assertEqual(
                database_schema_sha256(first),
                database_schema_sha256(first),
            )

    def test_cache_manifest_is_deterministic_relative_and_byte_sensitive(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "cache"
            self._create_cache(cache)
            first = build_cache_manifest(cache)
            second = build_cache_manifest(cache)

            self.assertEqual(first, second)
            self.assertEqual(first["file_count"], 3)
            self.assertTrue(
                all(not Path(item["relative_path"]).is_absolute() for item in first["files"])
            )
            mapped = next(
                item for item in first["files"] if item["relative_path"] == "2425_E0.csv"
            )
            unmapped = next(
                item for item in first["files"] if item["relative_path"].endswith("unmapped.csv")
            )
            self.assertEqual(mapped["season"], "2024-25")
            self.assertEqual(mapped["league"], "E0")
            self.assertIsNone(unmapped["season"])
            self.assertIsNone(unmapped["league"])

            (cache / "2425_E0.csv").write_bytes(b"changed bytes")
            changed = build_cache_manifest(cache)
            self.assertNotEqual(first["manifest_sha256"], changed["manifest_sha256"])

    def test_artifact_contains_no_absolute_user_paths_and_database_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "cache"
            database = root / "athena.db"
            self._create_cache(cache)
            self._create_database(database)
            before = hashlib.sha256(database.read_bytes()).hexdigest()

            artifact = self._build(database, cache)

            after = hashlib.sha256(database.read_bytes()).hexdigest()
            serialized = json.dumps(artifact, sort_keys=True)
            self.assertEqual(before, after)
            self.assertNotIn(str(root), serialized)
            self.assertNotIn(os.environ.get("USERNAME", "__missing__"), serialized)

    def test_atomic_write_and_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "baseline.json"
            artifact = {"schema_version": 1, "value": "first"}
            original_replace = os.replace
            calls = []

            def recording_replace(source, destination):
                calls.append((Path(source), Path(destination)))
                original_replace(source, destination)

            with patch(
                "scripts.freeze_evidence_baseline.os.replace",
                side_effect=recording_replace,
            ):
                write_baseline_atomic(output, artifact)

            self.assertEqual(load_baseline(output)["value"], "first")
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0].parent, output.parent)
            self.assertEqual(calls[0][1], output)
            self.assertEqual(list(output.parent.glob("*.tmp")), [])
            with self.assertRaisesRegex(BaselineError, "--force"):
                write_baseline_atomic(output, {"schema_version": 1})

    def test_check_mode_passes_identical_and_fails_evidence_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "cache"
            database = root / "athena.db"
            baseline_path = root / "baseline.json"
            self._create_cache(cache)
            self._create_database(database)
            artifact = self._build(database, cache)
            write_baseline_atomic(baseline_path, artifact)
            arguments = [
                "--database",
                str(database),
                "--cache-directory",
                str(cache),
                "--check",
                str(baseline_path),
            ]
            with patch(
                "scripts.freeze_evidence_baseline.get_code_state",
                return_value=deepcopy(self.CODE_STATE),
            ):
                self.assertEqual(main(arguments), 0)

            connection = sqlite3.connect(database)
            try:
                connection.execute(
                    "UPDATE half_time_observations SET half_time_home_goals = 0 WHERE fixture_identity = '1'"
                )
                connection.commit()
            finally:
                connection.close()
            with patch(
                "scripts.freeze_evidence_baseline.get_code_state",
                return_value=deepcopy(self.CODE_STATE),
            ):
                self.assertEqual(main(arguments), 1)

    def test_exact_evidence_head_verification_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            head = self._create_git_repository(repository)
            code = {
                "evidence_git_head_sha": head,
                "tracked_worktree_clean": True,
            }

            result = verify_revision_relationship(
                code,
                get_code_state(repository),
                check_path=Path(directory) / "outside.json",
                repository_root=repository,
            )

            self.assertEqual(result["mode"], "exact_evidence_revision")

    def test_artifact_only_descendant_verification_passes_and_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            evidence_head = self._create_git_repository(repository)
            cache = repository / "cache"
            database = repository / "athena.db"
            baseline_path = repository / "artifacts" / "baseline.json"
            self._create_cache(cache)
            self._create_database(database)
            artifact = build_evidence_baseline(
                database_path=database,
                cache_directory=cache,
                baseline_name="test-baseline",
                code_state={
                    "evidence_git_head_sha": evidence_head,
                    "tracked_worktree_clean": True,
                },
                generated_at_utc="2026-07-31T00:00:00Z",
            )
            write_baseline_atomic(baseline_path, artifact, force=True)
            self._git(repository, "add", "artifacts/baseline.json")
            self._git(repository, "commit", "-m", "add evidence baseline")

            output = io.StringIO()
            with redirect_stdout(output):
                return_code = main(
                    [
                        "--database",
                        str(database),
                        "--cache-directory",
                        str(cache),
                        "--check",
                        str(baseline_path),
                    ],
                    repository_root=repository,
                )

            self.assertEqual(return_code, 0)
            self.assertIn(
                "accepted artifact-only descendant relationship",
                output.getvalue(),
            )

    def test_artifact_only_descendant_with_additional_tracked_change_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            evidence_head = self._create_git_repository(repository)
            baseline_path = repository / "artifacts" / "baseline.json"
            baseline_path.write_text('{"baseline": true}\n', encoding="utf-8")
            (repository / "tracked.txt").write_text(
                "code changed too\n",
                encoding="utf-8",
            )
            self._git(repository, "add", "artifacts/baseline.json", "tracked.txt")
            self._git(repository, "commit", "-m", "baseline and code drift")

            with self.assertRaisesRegex(BaselineError, "other than"):
                verify_revision_relationship(
                    {
                        "evidence_git_head_sha": evidence_head,
                        "tracked_worktree_clean": True,
                    },
                    get_code_state(repository),
                    check_path=baseline_path,
                    repository_root=repository,
                )

    def test_descendant_changing_only_another_tracked_file_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            evidence_head = self._create_git_repository(repository)
            (repository / "tracked.txt").write_text(
                "only code changed\n",
                encoding="utf-8",
            )
            self._git(repository, "add", "tracked.txt")
            self._git(repository, "commit", "-m", "code drift")

            with self.assertRaisesRegex(BaselineError, "other than"):
                verify_revision_relationship(
                    {
                        "evidence_git_head_sha": evidence_head,
                        "tracked_worktree_clean": True,
                    },
                    get_code_state(repository),
                    check_path=repository / "artifacts" / "baseline.json",
                    repository_root=repository,
                )

    def test_non_ancestor_revision_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            common_head = self._create_git_repository(repository)
            default_branch = self._git(
                repository,
                "branch",
                "--show-current",
            )
            self._git(repository, "checkout", "-b", "evidence-side")
            (repository / "tracked.txt").write_text(
                "side evidence\n",
                encoding="utf-8",
            )
            self._git(repository, "commit", "-am", "side evidence")
            non_ancestor = self._git(repository, "rev-parse", "HEAD")
            self._git(repository, "checkout", default_branch)
            self.assertEqual(
                self._git(repository, "rev-parse", "HEAD"),
                common_head,
            )
            (repository / "artifacts" / "baseline.json").write_text(
                '{"baseline": true}\n',
                encoding="utf-8",
            )
            self._git(repository, "commit", "-am", "current baseline")

            with self.assertRaisesRegex(BaselineError, "not an ancestor"):
                verify_revision_relationship(
                    {
                        "evidence_git_head_sha": non_ancestor,
                        "tracked_worktree_clean": True,
                    },
                    get_code_state(repository),
                    check_path=repository / "artifacts" / "baseline.json",
                    repository_root=repository,
                )

    def test_outside_repository_baseline_cannot_use_descendant_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            evidence_head = self._create_git_repository(repository)
            baseline_path = repository / "artifacts" / "baseline.json"
            baseline_path.write_text('{"baseline": true}\n', encoding="utf-8")
            self._git(repository, "commit", "-am", "add baseline")
            outside = root / "outside.json"
            outside.write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(BaselineError, "inside the repository"):
                verify_revision_relationship(
                    {
                        "evidence_git_head_sha": evidence_head,
                        "tracked_worktree_clean": True,
                    },
                    get_code_state(repository),
                    check_path=outside,
                    repository_root=repository,
                )

    def test_symlinked_baseline_path_is_rejected_for_descendant(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            evidence_head = self._create_git_repository(repository)
            baseline_path = repository / "artifacts" / "baseline.json"
            baseline_path.write_text('{"baseline": true}\n', encoding="utf-8")
            self._git(repository, "commit", "-am", "add baseline")

            with patch(
                "scripts.freeze_evidence_baseline._path_is_symlink",
                side_effect=lambda path: path == baseline_path,
            ):
                with self.assertRaisesRegex(BaselineError, "symlinked"):
                    verify_revision_relationship(
                        {
                            "evidence_git_head_sha": evidence_head,
                            "tracked_worktree_clean": True,
                        },
                        get_code_state(repository),
                        check_path=baseline_path,
                        repository_root=repository,
                    )

    def test_dirty_tracked_worktree_fails_revision_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            evidence_head = self._create_git_repository(repository)
            (repository / "tracked.txt").write_text(
                "uncommitted tracked change\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(BaselineError, "worktree is dirty"):
                verify_revision_relationship(
                    {
                        "evidence_git_head_sha": evidence_head,
                        "tracked_worktree_clean": True,
                    },
                    get_code_state(repository),
                    check_path=repository / "artifacts" / "baseline.json",
                    repository_root=repository,
                )

    def test_non_revision_evidence_checks_remain_strict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "cache"
            database = root / "athena.db"
            self._create_cache(cache)
            self._create_database(database)
            stored = self._build(database, cache)
            current = deepcopy(stored)
            current["code"]["evidence_git_head_sha"] = "b" * 40
            current["database"]["logical_evidence_sha256"] = "logical-drift"
            current["database"]["schema_sha256"] = "schema-drift"
            current["audit"]["readiness"] = "DATA_INVALID"
            current["sources"] = {"changed": {}}
            current["football_data_uk_cache"]["manifest_sha256"] = "cache-drift"
            current["market_safety"]["home_win_either_half"][
                "model_status"
            ] = "ACTIVE"

            differences = compare_baselines(
                stored,
                current,
                allow_revision_difference=True,
            )

            self.assertIn("logical evidence fingerprint differs", differences)
            self.assertIn("database schema fingerprint differs", differences)
            self.assertTrue(
                any(item.startswith("audit totals/readiness differ") for item in differences)
            )
            self.assertIn("source totals differ", differences)
            self.assertIn("cache manifest fingerprint differs", differences)
            self.assertIn("market safety state differs", differences)

    def test_require_ready_safety_gates(self):
        ready = self._ready_artifact()
        validate_ready_baseline(ready)

        cases = []
        insufficient = deepcopy(ready)
        insufficient["audit"]["readiness"] = "INSUFFICIENT_DATA"
        cases.append(insufficient)
        conflict = deepcopy(ready)
        conflict["audit"]["readiness"] = "DATA_INVALID"
        conflict["audit"]["conflicting_fixtures"] = ["fixture-1"]
        cases.append(conflict)
        unknown = deepcopy(ready)
        unknown["audit"]["readiness"] = "INSUFFICIENT_DATA"
        unknown["audit"]["fixtures_with_unknown_league_metadata"] = 1
        cases.append(unknown)
        dirty = deepcopy(ready)
        dirty["code"]["tracked_worktree_clean"] = False
        cases.append(dirty)

        for artifact in cases:
            with self.subTest(artifact=artifact):
                with self.assertRaises(BaselineError):
                    validate_ready_baseline(artifact)

    def test_market_safety_and_expectation_mismatch(self):
        artifact = self._ready_artifact()
        self.assertEqual(
            artifact["market_safety"]["home_win_either_half"]["model_status"],
            ModelStatus.EXPERIMENTAL.value,
        )
        self.assertEqual(
            artifact["market_safety"]["away_win_either_half"]["model_status"],
            ModelStatus.EXPERIMENTAL.value,
        )
        validate_expectations(
            artifact,
            total_fixtures=21829,
            valid_half_time=21791,
            missing_half_time=38,
            cache_files=66,
        )
        with self.assertRaisesRegex(BaselineError, "Expectation mismatch"):
            validate_expectations(artifact, total_fixtures=1)

        unsafe = deepcopy(artifact)
        unsafe["market_safety"]["home_win_either_half"][
            "selection_authority"
        ] = "AUTHORIZED"
        with self.assertRaises(BaselineError):
            validate_ready_baseline(unsafe)

    def test_direct_and_module_help_do_not_access_network_or_database(self):
        for command in (
            [sys.executable, "-m", "scripts.freeze_evidence_baseline", "--help"],
            [sys.executable, "scripts/freeze_evidence_baseline.py", "--help"],
        ):
            with self.subTest(command=command):
                result = subprocess.run(
                    command,
                    cwd=self.REPOSITORY_ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=30,
                    shell=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--require-ready", result.stdout)
                self.assertIn("--expect-cache-files", result.stdout)
                self.assertNotIn("ModuleNotFoundError", result.stderr)

    def _assert_entrypoint_generates_and_checks(self, command_prefix):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "cache"
            database = root / "athena.db"
            baseline = root / "baseline.json"
            self._create_cache(cache)
            self._create_database(database)
            common = [
                "--database",
                str(database),
                "--cache-directory",
                str(cache),
            ]
            generation = subprocess.run(
                [*command_prefix, *common, "--output", str(baseline)],
                cwd=self.REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
                shell=False,
            )
            self.assertEqual(generation.returncode, 0, generation.stderr)
            self.assertTrue(baseline.is_file())
            verification = subprocess.run(
                [*command_prefix, *common, "--check", str(baseline)],
                cwd=self.REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
                shell=False,
            )
            self.assertEqual(verification.returncode, 0, verification.stderr)
            self.assertIn("Evidence baseline verified", verification.stdout)

    def test_module_entrypoint_performs_real_generation_and_check(self):
        self._assert_entrypoint_generates_and_checks(
            [sys.executable, "-m", "scripts.freeze_evidence_baseline"]
        )

    def test_direct_script_entrypoint_performs_real_generation_and_check(self):
        self._assert_entrypoint_generates_and_checks(
            [sys.executable, "scripts/freeze_evidence_baseline.py"]
        )


if __name__ == "__main__":
    unittest.main()
