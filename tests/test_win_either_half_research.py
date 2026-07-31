import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from database.database import Database
from domain.half_time_data import (
    HalfTimeObservation,
    HalfTimeValidationStatus,
    ScoreProvenance,
    _select_one_observation_per_fixture,
    audit_half_time_coverage,
    select_one_observation_per_fixture,
)
from domain.markets import MarketId
from domain.model_status import MODEL_STATUS_REGISTRY, ModelStatus
from domain.win_either_half_research import (
    HalfOutcome,
    LabelExclusionReason,
    ResearchLabelError,
    ResearchSplit,
    TemporalSplitConfig,
    build_win_either_half_labels,
    derive_win_either_half_label,
    label_exclusion_reasons,
)
from scripts.audit_half_time_coverage import load_observations_from_database
from scripts.export_win_either_half_research_dataset import (
    ResearchExportError,
    build_research_manifest,
    compare_research_manifests,
    main,
    render_dataset_csv,
    validate_market_safety,
    verify_stage_2_evidence,
    write_research_outputs,
)
from scripts.freeze_evidence_baseline import (
    build_evidence_baseline,
    get_code_state,
)


class WinEitherHalfResearchTests(unittest.TestCase):
    REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
    CODE_STATE = {
        "evidence_git_head_sha": "a" * 40,
        "tracked_worktree_clean": True,
    }
    SEASON_KICKOFFS = {
        "2020-21": datetime(2020, 9, 1, 15, 0, tzinfo=timezone.utc),
        "2021-22": datetime(2021, 9, 1, 15, 0, tzinfo=timezone.utc),
        "2022-23": datetime(2022, 9, 1, 15, 0, tzinfo=timezone.utc),
        "2023-24": datetime(2023, 9, 1, 15, 0, tzinfo=timezone.utc),
        "2024-25": datetime(2024, 9, 1, 15, 0, tzinfo=timezone.utc),
        "2025-26": datetime(2025, 9, 1, 15, 0, tzinfo=timezone.utc),
    }

    def _observation(self, **overrides):
        values = {
            "fixture_identity": "fixture-1",
            "home_team": "Alpha FC",
            "away_team": "Beta FC",
            "kickoff_time": self.SEASON_KICKOFFS["2025-26"],
            "full_time_home_goals": 2,
            "full_time_away_goals": 1,
            "half_time_home_goals": 1,
            "half_time_away_goals": 0,
            "source": "verified_test_source",
            "observed_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
            "source_fixture_id": "source-fixture-1",
            "half_time_score_provenance": ScoreProvenance.OBSERVED,
            "league": "E0",
            "season": "2025-26",
        }
        values.update(overrides)
        return HalfTimeObservation(**values)

    def _sample_observations(self, include_missing=True):
        observations = []
        for index, season in enumerate(self.SEASON_KICKOFFS, start=1):
            observations.append(
                self._observation(
                    fixture_identity=f"fixture-{index}",
                    source_fixture_id=f"source-{index}",
                    season=season,
                    kickoff_time=self.SEASON_KICKOFFS[season],
                    full_time_home_goals=2,
                    full_time_away_goals=1,
                    half_time_home_goals=1,
                    half_time_away_goals=0,
                )
            )
        if include_missing:
            observations.append(
                self._observation(
                    fixture_identity="fixture-missing",
                    source_fixture_id="source-missing",
                    half_time_home_goals=None,
                    half_time_away_goals=None,
                    half_time_score_provenance=ScoreProvenance.MISSING,
                )
            )
        return tuple(observations)

    @staticmethod
    def _create_cache(cache: Path):
        cache.mkdir(parents=True)
        (cache / "2526_E0.csv").write_bytes(b"Div,FTHG,FTAG,HTHG,HTAG\n")

    def _create_database(self, path: Path, order=(1, 2, 3, 4, 5, 6)):
        Database(str(path)).initialize()
        connection = sqlite3.connect(path)
        try:
            for fixture_id in order:
                season = tuple(self.SEASON_KICKOFFS)[fixture_id - 1]
                kickoff = self.SEASON_KICKOFFS[season].isoformat()
                home_id = fixture_id * 10 + 1
                away_id = fixture_id * 10 + 2
                connection.execute(
                    "INSERT INTO teams (team_id, name, league) VALUES (?, ?, ?)",
                    (home_id, f"Home {fixture_id}", "E0"),
                )
                connection.execute(
                    "INSERT INTO teams (team_id, name, league) VALUES (?, ?, ?)",
                    (away_id, f"Away {fixture_id}", "E0"),
                )
                connection.execute(
                    """
                    INSERT INTO historical_matches (
                        fixture_id, home_id, away_id, home_goals, away_goals,
                        match_date, data_source, season_label, league_code
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fixture_id,
                        home_id,
                        away_id,
                        2,
                        1,
                        kickoff,
                        "football_data_uk_csv",
                        season,
                        "E0",
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO half_time_observations (
                        fixture_identity, home_team, away_team, kickoff_time,
                        full_time_home_goals, full_time_away_goals,
                        half_time_home_goals, half_time_away_goals, source,
                        observed_at, source_fixture_id,
                        half_time_score_provenance, validation_status,
                        rejection_reasons, league, season
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(fixture_id),
                        f"Home {fixture_id}",
                        f"Away {fixture_id}",
                        kickoff,
                        2,
                        1,
                        1,
                        0,
                        "football_data_uk_csv",
                        "2026-07-01T00:00:00+00:00",
                        f"source-{fixture_id}",
                        "OBSERVED",
                        "VALID",
                        "[]",
                        "E0",
                        season,
                    ),
                )
            connection.commit()
        finally:
            connection.close()

    def _baseline(self, database: Path, cache: Path, code_state=None):
        return build_evidence_baseline(
            database_path=database,
            cache_directory=cache,
            baseline_name="test-stage-2",
            code_state=deepcopy(code_state or self.CODE_STATE),
            generated_at_utc="2026-07-31T00:00:00Z",
        )

    def _manifest_fixture(self, root: Path, code_state=None):
        root.mkdir(parents=True, exist_ok=True)
        database = root / "athena.db"
        cache = root / "cache"
        self._create_database(database)
        self._create_cache(cache)
        baseline = self._baseline(database, cache, code_state)
        current = verify_stage_2_evidence(
            baseline,
            database_path=database,
            cache_directory=cache,
        )
        dataset = build_win_either_half_labels(
            load_observations_from_database(str(database))
        )
        labels, exclusions = render_dataset_csv(dataset)
        manifest = build_research_manifest(
            dataset,
            labels_bytes=labels,
            exclusions_bytes=exclusions,
            labels_relative_name="labels-v1.csv",
            exclusions_relative_name="exclusions-v1.csv",
            stage_2_baseline=baseline,
            current_evidence=current,
            generator_code_state=deepcopy(code_state or self.CODE_STATE),
            generated_at_utc="2026-07-31T00:00:00Z",
        )
        return database, cache, baseline, dataset, labels, exclusions, manifest

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
        (repository / "artifacts" / "manifest.json").write_text(
            "{}\n", encoding="utf-8"
        )
        (repository / "tracked.txt").write_text("generator\n", encoding="utf-8")
        self._git(repository, "add", "artifacts/manifest.json", "tracked.txt")
        self._git(repository, "commit", "-m", "generator revision")
        return self._git(repository, "rev-parse", "HEAD")

    def test_label_settlement_semantics(self):
        cases = (
            ("home-first", (1, 0), (2, 1), (1, 0, 0, 0, 1, 0, 0)),
            ("home-second", (0, 0), (1, 0), (0, 0, 1, 0, 1, 0, 0)),
            ("away-first", (0, 1), (1, 2), (0, 1, 0, 0, 0, 1, 0)),
            ("away-second", (0, 0), (0, 1), (0, 0, 0, 1, 0, 1, 0)),
            ("different-halves", (1, 0), (1, 2), (1, 0, 0, 1, 1, 1, 1)),
            ("drawn-halves", (0, 0), (1, 1), (0, 0, 0, 0, 0, 0, 0)),
            ("zero-second", (2, 1), (2, 1), (1, 0, 0, 0, 1, 0, 0)),
            ("home-both", (1, 0), (3, 0), (1, 0, 1, 0, 1, 0, 0)),
        )
        for name, half_time, full_time, expected in cases:
            with self.subTest(name=name):
                label = derive_win_either_half_label(
                    self._observation(
                        fixture_identity=name,
                        half_time_home_goals=half_time[0],
                        half_time_away_goals=half_time[1],
                        full_time_home_goals=full_time[0],
                        full_time_away_goals=full_time[1],
                    ),
                    split=ResearchSplit.TEST,
                )
                actual = (
                    label.home_win_first_half,
                    label.away_win_first_half,
                    label.home_win_second_half,
                    label.away_win_second_half,
                    label.home_win_either_half_yes,
                    label.away_win_either_half_yes,
                    label.both_teams_won_a_half,
                )
                self.assertEqual(actual, expected)
                self.assertEqual(
                    label.second_half_home_goals,
                    full_time[0] - half_time[0],
                )
                self.assertEqual(
                    label.second_half_away_goals,
                    full_time[1] - half_time[1],
                )

    def test_home_and_away_labels_are_not_complements(self):
        both_yes = derive_win_either_half_label(
            self._observation(
                half_time_home_goals=1,
                half_time_away_goals=0,
                full_time_home_goals=1,
                full_time_away_goals=2,
            ),
            split=ResearchSplit.TEST,
        )
        both_no = derive_win_either_half_label(
            self._observation(
                half_time_home_goals=0,
                half_time_away_goals=0,
                full_time_home_goals=1,
                full_time_away_goals=1,
            ),
            split=ResearchSplit.TEST,
        )
        self.assertEqual(
            (both_yes.home_win_either_half_yes, both_yes.away_win_either_half_yes),
            (1, 1),
        )
        self.assertEqual(
            (both_no.home_win_either_half_yes, both_no.away_win_either_half_yes),
            (0, 0),
        )

    def test_half_outcomes_and_score_calculations_are_exact(self):
        label = derive_win_either_half_label(
            self._observation(
                half_time_home_goals=0,
                half_time_away_goals=1,
                full_time_home_goals=2,
                full_time_away_goals=1,
            ),
            split=ResearchSplit.TEST,
        )
        self.assertEqual(label.first_half_outcome, HalfOutcome.AWAY)
        self.assertEqual(label.second_half_outcome, HalfOutcome.HOME)
        self.assertEqual((label.second_half_home_goals, label.second_half_away_goals), (2, 0))

    def test_eligibility_exclusions_fail_closed(self):
        cases = (
            (
                "missing-half-time",
                {
                    "half_time_home_goals": None,
                    "half_time_away_goals": None,
                    "half_time_score_provenance": ScoreProvenance.MISSING,
                },
                LabelExclusionReason.MISSING_HALF_TIME_SCORE,
            ),
            ("invalid-score", {"half_time_home_goals": -1}, LabelExclusionReason.INVALID_SCORE_EVIDENCE),
            ("inferred", {"half_time_score_provenance": ScoreProvenance.INFERRED}, LabelExclusionReason.UNOBSERVED_PROVENANCE),
            ("conflict", {"conflict_status": True}, LabelExclusionReason.SOURCE_CONFLICT),
            ("kickoff", {"kickoff_time": None}, LabelExclusionReason.MISSING_KICKOFF),
            ("league", {"league": None}, LabelExclusionReason.MISSING_LEAGUE),
            ("season", {"season": None}, LabelExclusionReason.MISSING_SEASON),
            ("team", {"home_team": ""}, LabelExclusionReason.MISSING_TEAM_IDENTITY),
            (
                "negative-second",
                {"half_time_home_goals": 3, "full_time_home_goals": 2},
                LabelExclusionReason.NEGATIVE_SECOND_HALF_SCORE,
            ),
        )
        for name, overrides, expected in cases:
            with self.subTest(name=name):
                reasons = label_exclusion_reasons(
                    self._observation(fixture_identity=name, **overrides)
                )
                self.assertIn(expected, reasons)

    def test_multiple_exclusion_reasons_are_sorted_and_deterministic(self):
        observation = self._observation(
            fixture_identity="",
            home_team="",
            kickoff_time=None,
            league=None,
            season=None,
            half_time_home_goals=None,
            half_time_away_goals=None,
            half_time_score_provenance=ScoreProvenance.MISSING,
            conflict_status=True,
        )
        first = label_exclusion_reasons(observation)
        second = label_exclusion_reasons(observation)
        self.assertEqual(first, second)
        self.assertEqual(
            [reason.value for reason in first],
            sorted(reason.value for reason in first),
        )

    def test_public_selector_preserves_private_and_audit_semantics(self):
        older = self._observation(
            source="source-a",
            observed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            half_time_home_goals=0,
        )
        newer = self._observation(
            source="source-b",
            observed_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            half_time_home_goals=1,
        )
        public = select_one_observation_per_fixture((newer, older))
        private = _select_one_observation_per_fixture((older, newer))
        report = audit_half_time_coverage((older, newer)).to_dict()
        self.assertEqual(public, private)
        self.assertEqual(public, (newer,))
        self.assertEqual(report["total_historical_fixtures_inspected"], 1)
        self.assertEqual(report["fixtures_with_valid_half_time_scores"], 1)
        self.assertEqual(report["total_source_observations"], 2)
        dataset = build_win_either_half_labels((older, newer))
        self.assertEqual(dataset.labels[0].source, "source-b")

    def test_default_temporal_splits_assign_every_eligible_row_once(self):
        dataset = build_win_either_half_labels(self._sample_observations())
        counts = {split: 0 for split in ResearchSplit}
        for label in dataset.labels:
            counts[label.split] += 1
        self.assertEqual(dataset.selected_fixtures, 7)
        self.assertEqual(len(dataset.labels), 6)
        self.assertEqual(len(dataset.exclusions), 1)
        self.assertEqual(counts[ResearchSplit.TRAIN], 4)
        self.assertEqual(counts[ResearchSplit.VALIDATION], 1)
        self.assertEqual(counts[ResearchSplit.TEST], 1)
        self.assertEqual(sum(counts.values()), len(dataset.labels))

    def test_split_overlap_and_unassigned_seasons_fail(self):
        with self.assertRaisesRegex(ResearchLabelError, "overlap"):
            TemporalSplitConfig(
                train_seasons=("2024-25",),
                validation_seasons=("2024-25",),
                test_seasons=("2025-26",),
            )
        with self.assertRaisesRegex(ResearchLabelError, "not assigned"):
            build_win_either_half_labels(
                (self._observation(season="2019-20"),)
            )

    def test_explicit_temporal_split_override_is_honoured(self):
        config = TemporalSplitConfig(
            train_seasons=("2025-26",),
            validation_seasons=("2024-25",),
            test_seasons=("2023-24",),
        )
        dataset = build_win_either_half_labels(
            (self._observation(season="2025-26"),),
            split_config=config,
        )
        self.assertEqual(dataset.labels[0].split, ResearchSplit.TRAIN)

    def test_database_insertion_order_produces_identical_csv_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_db = root / "first.db"
            second_db = root / "second.db"
            self._create_database(first_db, order=(1, 2, 3, 4, 5, 6))
            self._create_database(second_db, order=(6, 5, 4, 3, 2, 1))
            first = render_dataset_csv(
                build_win_either_half_labels(
                    load_observations_from_database(str(first_db))
                )
            )
            second = render_dataset_csv(
                build_win_either_half_labels(
                    load_observations_from_database(str(second_db))
                )
            )
            self.assertEqual(first, second)
            self.assertEqual(hashlib.sha256(first[0]).hexdigest(), hashlib.sha256(second[0]).hexdigest())

    def test_exclusion_rows_have_stable_fixture_and_reason_ordering(self):
        first = self._observation(
            fixture_identity="fixture-z",
            half_time_home_goals=None,
            half_time_away_goals=None,
            half_time_score_provenance=ScoreProvenance.MISSING,
        )
        second = self._observation(
            fixture_identity="fixture-a",
            home_team="",
            kickoff_time=None,
        )
        forward = build_win_either_half_labels((first, second))
        reverse = build_win_either_half_labels((second, first))
        forward_csv = render_dataset_csv(forward)[1]
        reverse_csv = render_dataset_csv(reverse)[1]
        self.assertEqual(forward_csv, reverse_csv)
        rows = forward_csv.decode("utf-8").splitlines()[1:]
        self.assertTrue(rows[0].startswith("fixture-a,"))
        for exclusion in forward.exclusions:
            codes = [reason.value for reason in exclusion.reason_codes]
            self.assertEqual(codes, sorted(codes))

    def test_csv_ordering_paths_and_database_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "athena.db"
            self._create_database(database, order=(6, 2, 4, 1, 5, 3))
            before = hashlib.sha256(database.read_bytes()).hexdigest()
            dataset = build_win_either_half_labels(
                load_observations_from_database(str(database))
            )
            labels, exclusions = render_dataset_csv(dataset)
            after = hashlib.sha256(database.read_bytes()).hexdigest()
            rows = labels.decode("utf-8").splitlines()[1:]
            self.assertEqual(before, after)
            self.assertEqual(rows, sorted(rows, key=lambda row: row.split(",")[3:4] + row.split(",")[0:1]))
            self.assertNotIn(str(root), labels.decode("utf-8"))
            self.assertNotIn(str(root), exclusions.decode("utf-8"))

    def test_matching_stage_2_non_code_evidence_ignores_generator_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "athena.db"
            cache = root / "cache"
            self._create_database(database)
            self._create_cache(cache)
            baseline = self._baseline(database, cache)
            current = verify_stage_2_evidence(
                baseline,
                database_path=database,
                cache_directory=cache,
            )
            self.assertEqual(current["database"], baseline["database"])
            self.assertEqual(current["sources"], baseline["sources"])

    def test_stage_2_logical_schema_cache_source_audit_and_market_drift_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "athena.db"
            cache = root / "cache"
            self._create_database(database)
            self._create_cache(cache)
            baseline = self._baseline(database, cache)

            drifted_baselines = []
            source = deepcopy(baseline)
            source["sources"] = {"drift": {}}
            drifted_baselines.append(source)
            audit = deepcopy(baseline)
            audit["audit"]["readiness"] = "DATA_INVALID"
            drifted_baselines.append(audit)
            market = deepcopy(baseline)
            market["market_safety"]["home_win_either_half"] = "ACTIVE"
            drifted_baselines.append(market)
            for artifact in drifted_baselines:
                with self.subTest(drift=artifact):
                    with self.assertRaises(ResearchExportError):
                        verify_stage_2_evidence(
                            artifact,
                            database_path=database,
                            cache_directory=cache,
                        )

            changed_cache = root / "changed-cache"
            self._create_cache(changed_cache)
            (changed_cache / "2526_E0.csv").write_bytes(b"changed")
            with self.assertRaisesRegex(ResearchExportError, "cache"):
                verify_stage_2_evidence(
                    baseline,
                    database_path=database,
                    cache_directory=changed_cache,
                )

            connection = sqlite3.connect(database)
            connection.execute(
                "UPDATE half_time_observations SET half_time_home_goals = 0 WHERE fixture_identity = '1'"
            )
            connection.commit()
            connection.close()
            with self.assertRaisesRegex(ResearchExportError, "logical"):
                verify_stage_2_evidence(
                    baseline,
                    database_path=database,
                    cache_directory=cache,
                )

            connection = sqlite3.connect(database)
            connection.execute(
                "UPDATE half_time_observations SET half_time_home_goals = 1 WHERE fixture_identity = '1'"
            )
            connection.execute("CREATE TABLE schema_drift (value TEXT)")
            connection.commit()
            connection.close()
            with self.assertRaisesRegex(ResearchExportError, "schema"):
                verify_stage_2_evidence(
                    baseline,
                    database_path=database,
                    cache_directory=cache,
                )

    def test_manifest_counts_post_match_classification_and_no_absolute_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, _, dataset, labels, exclusions, manifest = self._manifest_fixture(root)
            serialized = json.dumps(manifest, sort_keys=True)
            self.assertEqual(manifest["selection"]["eligible_labels"], 6)
            self.assertEqual(manifest["selection"]["excluded_fixtures"], 0)
            self.assertEqual(manifest["splits"]["train"]["rows"], 4)
            self.assertEqual(manifest["splits"]["validation"]["rows"], 1)
            self.assertEqual(manifest["splits"]["test"]["rows"], 1)
            self.assertEqual(manifest["files"]["labels"]["sha256"], hashlib.sha256(labels).hexdigest())
            self.assertEqual(manifest["files"]["exclusions"]["sha256"], hashlib.sha256(exclusions).hexdigest())
            self.assertEqual(manifest["column_roles"]["purpose"], "LABEL_DATASET_NOT_FEATURE_MATRIX")
            self.assertNotIn(str(root), serialized)
            self.assertEqual(len(dataset.labels), 6)
            header, first_row = labels.decode("utf-8").splitlines()[:2]
            columns = header.split(",")
            values = first_row.split(",")
            for column in (
                "home_win_first_half",
                "away_win_first_half",
                "home_win_second_half",
                "away_win_second_half",
                "home_win_either_half_yes",
                "away_win_either_half_yes",
                "both_teams_won_a_half",
            ):
                self.assertIn(values[columns.index(column)], {"0", "1"})

    def test_manifest_timestamp_is_ignored_but_hash_and_count_drift_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self._manifest_fixture(Path(directory))[-1]
            later = deepcopy(manifest)
            later["generated_at_utc"] = "2030-01-01T00:00:00Z"
            self.assertEqual(compare_research_manifests(manifest, later), [])
            later["files"]["labels"]["sha256"] = "drift"
            later["selection"]["eligible_labels"] += 1
            differences = compare_research_manifests(manifest, later)
            self.assertIn("label or exclusion file identity differs", differences)
            self.assertIn("selection counts differ", differences)

    def test_output_is_atomic_and_overwrite_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            labels_path = root / "labels.csv"
            exclusions_path = root / "exclusions.csv"
            manifest_path = root / "manifest.json"
            manifest = self._manifest_fixture(root / "fixture")[-1]
            calls = []
            original_replace = os.replace

            def recording_replace(source, destination):
                calls.append((Path(source), Path(destination)))
                original_replace(source, destination)

            with patch(
                "scripts.export_win_either_half_research_dataset.os.replace",
                side_effect=recording_replace,
            ):
                write_research_outputs(
                    labels_path=labels_path,
                    exclusions_path=exclusions_path,
                    manifest_path=manifest_path,
                    labels_bytes=b"labels\n",
                    exclusions_bytes=b"exclusions\n",
                    manifest=manifest,
                )
            self.assertEqual(len(calls), 3)
            self.assertTrue(all(source.suffix == ".tmp" for source, _ in calls))
            with self.assertRaisesRegex(ResearchExportError, "--force"):
                write_research_outputs(
                    labels_path=labels_path,
                    exclusions_path=exclusions_path,
                    manifest_path=manifest_path,
                    labels_bytes=b"labels\n",
                    exclusions_bytes=b"exclusions\n",
                    manifest=manifest,
                )

    def test_both_win_either_half_markets_remain_disabled(self):
        self.assertEqual(
            MODEL_STATUS_REGISTRY[MarketId.HOME_WIN_EITHER_HALF].status,
            ModelStatus.DISABLED,
        )
        self.assertEqual(
            MODEL_STATUS_REGISTRY[MarketId.AWAY_WIN_EITHER_HALF].status,
            ModelStatus.DISABLED,
        )
        with self.assertRaises(ResearchExportError):
            validate_market_safety(
                {
                    "market_safety": {
                        "home_win_either_half": "ACTIVE",
                        "away_win_either_half": "DISABLED",
                    }
                }
            )

    def test_exact_generator_revision_check_passes_and_data_drift_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database, cache, baseline, _, labels, exclusions, manifest = self._manifest_fixture(root)
            baseline_path = root / "baseline.json"
            manifest_path = root / "manifest.json"
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            arguments = [
                "--database", str(database),
                "--cache-directory", str(cache),
                "--baseline", str(baseline_path),
                "--check", str(manifest_path),
            ]
            with patch(
                "scripts.export_win_either_half_research_dataset.get_code_state",
                return_value=deepcopy(self.CODE_STATE),
            ):
                self.assertEqual(main(arguments), 0)
            drift = deepcopy(manifest)
            drift["files"]["labels"]["sha256"] = "drift"
            manifest_path.write_text(json.dumps(drift), encoding="utf-8")
            with patch(
                "scripts.export_win_either_half_research_dataset.get_code_state",
                return_value=deepcopy(self.CODE_STATE),
            ):
                self.assertEqual(main(arguments), 1)
            self.assertTrue(labels)
            self.assertTrue(exclusions)

    def test_manifest_only_descendant_passes_and_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            generator_head = self._create_git_repository(repository)
            database, cache, baseline, _, _, _, manifest = self._manifest_fixture(
                repository / "evidence",
                {
                    "evidence_git_head_sha": generator_head,
                    "tracked_worktree_clean": True,
                },
            )
            baseline_path = repository / "evidence" / "baseline.json"
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            manifest_path = repository / "artifacts" / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self._git(repository, "add", "artifacts/manifest.json")
            self._git(repository, "commit", "-m", "add research manifest")

            output = io.StringIO()
            with redirect_stdout(output):
                result = main(
                    [
                        "--database", str(database),
                        "--cache-directory", str(cache),
                        "--baseline", str(baseline_path),
                        "--check", str(manifest_path),
                    ],
                    repository_root=repository,
                )
            self.assertEqual(result, 0)
            self.assertIn("accepted artifact-only descendant", output.getvalue())

    def test_manifest_plus_another_tracked_change_and_dirty_worktree_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            generator_head = self._create_git_repository(repository)
            database, cache, baseline, _, _, _, manifest = self._manifest_fixture(
                repository / "evidence",
                {
                    "evidence_git_head_sha": generator_head,
                    "tracked_worktree_clean": True,
                },
            )
            baseline_path = repository / "evidence" / "baseline.json"
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            manifest_path = repository / "artifacts" / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            (repository / "tracked.txt").write_text("changed\n", encoding="utf-8")
            self._git(repository, "add", "artifacts/manifest.json", "tracked.txt")
            self._git(repository, "commit", "-m", "manifest and code")
            arguments = [
                "--database", str(database),
                "--cache-directory", str(cache),
                "--baseline", str(baseline_path),
                "--check", str(manifest_path),
            ]
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(main(arguments, repository_root=repository), 1)
            self.assertIn("other than", stderr.getvalue())

            (repository / "tracked.txt").write_text("dirty\n", encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(main(arguments, repository_root=repository), 1)
            self.assertIn("worktree is dirty", stderr.getvalue())

    def _assert_real_entrypoint_generation_and_check(self, command_prefix):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "athena.db"
            cache = root / "cache"
            baseline_path = root / "baseline.json"
            labels_path = root / "labels.csv"
            exclusions_path = root / "exclusions.csv"
            manifest_path = root / "manifest.json"
            self._create_database(database)
            self._create_cache(cache)
            baseline = self._baseline(database, cache, get_code_state())
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            common = [
                "--database", str(database),
                "--cache-directory", str(cache),
                "--baseline", str(baseline_path),
            ]
            generation = subprocess.run(
                [
                    *command_prefix,
                    *common,
                    "--labels-output", str(labels_path),
                    "--exclusions-output", str(exclusions_path),
                    "--manifest-output", str(manifest_path),
                ],
                cwd=self.REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=90,
                shell=False,
            )
            self.assertEqual(generation.returncode, 0, generation.stderr)
            verification = subprocess.run(
                [*command_prefix, *common, "--check", str(manifest_path)],
                cwd=self.REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=90,
                shell=False,
            )
            self.assertEqual(verification.returncode, 0, verification.stderr)
            self.assertIn("Research manifest verified", verification.stdout)

    def test_direct_script_real_generation_and_check(self):
        self._assert_real_entrypoint_generation_and_check(
            [sys.executable, "scripts/export_win_either_half_research_dataset.py"]
        )

    def test_module_real_generation_and_check(self):
        self._assert_real_entrypoint_generation_and_check(
            [sys.executable, "-m", "scripts.export_win_either_half_research_dataset"]
        )

    def test_direct_and_module_help_make_no_network_request(self):
        for command in (
            [sys.executable, "scripts/export_win_either_half_research_dataset.py", "--help"],
            [sys.executable, "-m", "scripts.export_win_either_half_research_dataset", "--help"],
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
                self.assertIn("--train-seasons", result.stdout)
                self.assertIn("--require-baseline-evidence", result.stdout)


if __name__ == "__main__":
    unittest.main()
