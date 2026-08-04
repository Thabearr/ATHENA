"""Tests for Stage 5B3 Win Either Half capture-campaign planning."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from domain.markets import MARKET_REGISTRY, MarketId
from domain.model_status import MODEL_STATUS_REGISTRY, ModelStatus
from domain.win_either_half_capture_campaign import (
    ATTEMPT_WINDOW_SECONDS,
    DEFAULT_PROTOCOL_PATH,
    DEFAULT_STAGE_5B2_PROTOCOL_PATH,
    EXPECTED_TASKS_PER_FIXTURE,
    FROZEN_CANDIDATE_OFFSETS_SECONDS,
    MINIMUM_FIXTURES_FOR_INTERPRETATION,
    CaptureCampaignError,
    build_campaign_plan,
    build_expected_protocol_contract,
    load_fixtures,
    load_source_qualification,
    parse_utc,
    validate_campaign_protocol,
    validate_stage_5b2_protocol,
)
from scripts.manage_win_either_half_capture_campaign import (
    OUTPUT_FILENAMES,
    CaptureCampaignExportError,
    build_bundle,
    check_bundle,
    commit_bundle,
    run,
)


class TestWinEitherHalfCaptureCampaign(unittest.TestCase):
    REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

    def setUp(self) -> None:
        self.source_payload = {
            "schema_version": 1,
            "dataset_name": (
                "win-either-half-pricing-source-qualification-v1"
            ),
            "provider_identifier": "TEST_PROVIDER",
            "qualification": {
                "prospective_replay_status": (
                    "QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY"
                )
            },
            "holdout_governance": {
                "prospective_validation_required": True,
                "production_approval_authorized": False,
            },
            "market_statuses": {
                "HOME_WIN_EITHER_HALF": "DISABLED",
                "AWAY_WIN_EITHER_HALF": "DISABLED",
            },
            "no_production_approval": "Research only",
        }
        self.anchor_at = "2026-08-10T00:00:00Z"
        self.fixtures_payload = self._fixtures_payload(1)
        self.code_state = {
            "evidence_git_head_sha": "1" * 40,
            "tracked_worktree_clean": True,
        }

    def _fixtures_payload(self, count: int) -> dict:
        base = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
        return {
            "schema_version": 1,
            "fixtures": [
                {
                    "fixture_identifier": f"FIX-{index:04d}",
                    "kickoff": (
                        base + timedelta(hours=index)
                    ).isoformat().replace("+00:00", "Z"),
                }
                for index in range(count)
            ],
        }

    def _write_inputs(self, root: Path, fixture_count: int = 1) -> dict[str, Path]:
        source = root / "source.json"
        fixtures = root / "fixtures.json"
        stage5b2 = root / "stage5b2.json"
        campaign = root / "campaign.json"
        source.write_text(json.dumps(self.source_payload), encoding="utf-8")
        fixtures.write_text(
            json.dumps(self._fixtures_payload(fixture_count)),
            encoding="utf-8",
        )
        stage5b2.write_bytes(DEFAULT_STAGE_5B2_PROTOCOL_PATH.read_bytes())
        campaign.write_bytes(DEFAULT_PROTOCOL_PATH.read_bytes())
        return {
            "source": source,
            "fixtures": fixtures,
            "stage5b2": stage5b2,
            "campaign": campaign,
        }

    def _build_bundle(self, root: Path, fixture_count: int = 1):
        paths = self._write_inputs(root, fixture_count)
        return build_bundle(
            source_qualification_path=paths["source"],
            fixtures_path=paths["fixtures"],
            stage_5b2_protocol_path=paths["stage5b2"],
            campaign_protocol_path=paths["campaign"],
            anchor_at=self.anchor_at,
            code_state=self.code_state,
        )

    def test_committed_campaign_protocol_matches_python_contract(self) -> None:
        payload = json.loads(DEFAULT_PROTOCOL_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload, build_expected_protocol_contract())
        validate_campaign_protocol(payload)

    def test_every_top_level_campaign_protocol_mutation_fails(self) -> None:
        original = build_expected_protocol_contract()
        for key in original:
            mutated = copy.deepcopy(original)
            if isinstance(mutated[key], bool):
                mutated[key] = not mutated[key]
            elif isinstance(mutated[key], int):
                mutated[key] += 1
            elif isinstance(mutated[key], str):
                mutated[key] += "-MUTATED"
            elif isinstance(mutated[key], list):
                mutated[key] = list(reversed(mutated[key]))
            elif isinstance(mutated[key], dict):
                mutated[key]["unexpected"] = True
            with self.assertRaises(CaptureCampaignError, msg=key):
                validate_campaign_protocol(mutated)

    def test_stage5b2_protocol_contract_is_accepted(self) -> None:
        payload = json.loads(
            DEFAULT_STAGE_5B2_PROTOCOL_PATH.read_text(encoding="utf-8")
        )
        validate_stage_5b2_protocol(payload)

    def test_stage5b2_offset_drift_fails_closed(self) -> None:
        payload = json.loads(
            DEFAULT_STAGE_5B2_PROTOCOL_PATH.read_text(encoding="utf-8")
        )
        payload["candidate_offsets_seconds"] = [86400, 3600, 900]
        with self.assertRaises(CaptureCampaignError):
            validate_stage_5b2_protocol(payload)

    def test_one_fixture_creates_exactly_twelve_tasks(self) -> None:
        source = load_source_qualification(self.source_payload)
        fixtures = load_fixtures(self.fixtures_payload)
        plan = build_campaign_plan(
            source_qualification=source,
            fixtures=fixtures,
            anchor_at=parse_utc(self.anchor_at, "anchor"),
            stage_5b2_protocol_sha256="a" * 64,
            campaign_protocol_sha256="b" * 64,
        )
        self.assertEqual(len(plan.tasks), EXPECTED_TASKS_PER_FIXTURE)
        self.assertEqual(
            {task.market_id for task in plan.tasks},
            {
                MarketId.HOME_WIN_EITHER_HALF,
                MarketId.AWAY_WIN_EITHER_HALF,
            },
        )
        self.assertEqual(
            {task.offset_seconds_before_kickoff for task in plan.tasks},
            set(FROZEN_CANDIDATE_OFFSETS_SECONDS),
        )

    def test_one_hundred_fixtures_create_1200_tasks(self) -> None:
        source = load_source_qualification(self.source_payload)
        fixtures = load_fixtures(self._fixtures_payload(100))
        plan = build_campaign_plan(
            source_qualification=source,
            fixtures=fixtures,
            anchor_at=parse_utc(self.anchor_at, "anchor"),
            stage_5b2_protocol_sha256="a" * 64,
            campaign_protocol_sha256="b" * 64,
        )
        self.assertEqual(len(plan.tasks), 1200)
        self.assertTrue(plan.interpretation_eligible)

    def test_99_fixtures_are_not_interpretation_eligible(self) -> None:
        source = load_source_qualification(self.source_payload)
        plan = build_campaign_plan(
            source_qualification=source,
            fixtures=load_fixtures(self._fixtures_payload(99)),
            anchor_at=parse_utc(self.anchor_at, "anchor"),
            stage_5b2_protocol_sha256="a" * 64,
            campaign_protocol_sha256="b" * 64,
        )
        self.assertFalse(plan.interpretation_eligible)
        self.assertEqual(MINIMUM_FIXTURES_FOR_INTERPRETATION, 100)

    def test_scheduled_at_and_capture_window_are_exact(self) -> None:
        source = load_source_qualification(self.source_payload)
        fixture = load_fixtures(self.fixtures_payload)[0]
        plan = build_campaign_plan(
            source_qualification=source,
            fixtures=(fixture,),
            anchor_at=parse_utc(self.anchor_at, "anchor"),
            stage_5b2_protocol_sha256="a" * 64,
            campaign_protocol_sha256="b" * 64,
        )
        target = next(
            task
            for task in plan.tasks
            if task.market_id == MarketId.HOME_WIN_EITHER_HALF
            and task.offset_seconds_before_kickoff == 3600
        )
        self.assertEqual(
            target.scheduled_at,
            fixture.kickoff - timedelta(seconds=3600),
        )
        self.assertEqual(
            target.capture_window_opens_at,
            target.scheduled_at - timedelta(seconds=ATTEMPT_WINDOW_SECONDS),
        )
        self.assertEqual(
            target.capture_window_closes_at,
            target.scheduled_at + timedelta(seconds=ATTEMPT_WINDOW_SECONDS),
        )
        self.assertLess(target.capture_window_closes_at, fixture.kickoff)

    def test_fixture_input_order_does_not_change_campaign_or_tasks(self) -> None:
        source = load_source_qualification(self.source_payload)
        payload = self._fixtures_payload(3)
        first = load_fixtures(payload)
        reversed_payload = copy.deepcopy(payload)
        reversed_payload["fixtures"].reverse()
        second = load_fixtures(reversed_payload)
        kwargs = {
            "source_qualification": source,
            "anchor_at": parse_utc(self.anchor_at, "anchor"),
            "stage_5b2_protocol_sha256": "a" * 64,
            "campaign_protocol_sha256": "b" * 64,
        }
        plan_a = build_campaign_plan(fixtures=first, **kwargs)
        plan_b = build_campaign_plan(fixtures=second, **kwargs)
        self.assertEqual(plan_a.campaign_id, plan_b.campaign_id)
        self.assertEqual(plan_a.tasks, plan_b.tasks)

    def test_task_ids_are_unique_and_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = self._build_bundle(Path(tmp), 3)
            second = self._build_bundle(Path(tmp), 3)
        rows = [
            json.loads(line)
            for line in first.files["tasks"].decode("utf-8").splitlines()
        ]
        self.assertEqual(len(rows), len({row["task_id"] for row in rows}))
        self.assertEqual(first.files["tasks"], second.files["tasks"])
        self.assertEqual(first.summary["campaign_id"], second.summary["campaign_id"])

    def test_anchor_equal_to_first_window_open_is_allowed(self) -> None:
        payload = self._fixtures_payload(1)
        fixture = load_fixtures(payload)[0]
        anchor = fixture.kickoff - timedelta(
            seconds=max(FROZEN_CANDIDATE_OFFSETS_SECONDS)
            + ATTEMPT_WINDOW_SECONDS
        )
        source = load_source_qualification(self.source_payload)
        plan = build_campaign_plan(
            source_qualification=source,
            fixtures=(fixture,),
            anchor_at=anchor,
            stage_5b2_protocol_sha256="a" * 64,
            campaign_protocol_sha256="b" * 64,
        )
        self.assertEqual(len(plan.tasks), 12)

    def test_anchor_after_first_window_open_is_rejected(self) -> None:
        fixture = load_fixtures(self.fixtures_payload)[0]
        anchor = fixture.kickoff - timedelta(
            seconds=max(FROZEN_CANDIDATE_OFFSETS_SECONDS)
            + ATTEMPT_WINDOW_SECONDS
            - 1
        )
        source = load_source_qualification(self.source_payload)
        with self.assertRaises(CaptureCampaignError):
            build_campaign_plan(
                source_qualification=source,
                fixtures=(fixture,),
                anchor_at=anchor,
                stage_5b2_protocol_sha256="a" * 64,
                campaign_protocol_sha256="b" * 64,
            )

    def test_naive_anchor_and_fixture_timestamps_are_rejected(self) -> None:
        with self.assertRaises(CaptureCampaignError):
            parse_utc("2026-08-10T00:00:00", "anchor")
        payload = self._fixtures_payload(1)
        payload["fixtures"][0]["kickoff"] = "2026-08-12T15:00:00"
        with self.assertRaises(CaptureCampaignError):
            load_fixtures(payload)

    def test_duplicate_fixture_identifier_is_rejected(self) -> None:
        payload = self._fixtures_payload(2)
        payload["fixtures"][1]["fixture_identifier"] = "FIX-0000"
        with self.assertRaises(CaptureCampaignError):
            load_fixtures(payload)

    def test_fixture_extra_key_is_rejected(self) -> None:
        payload = self._fixtures_payload(1)
        payload["fixtures"][0]["league"] = "E0"
        with self.assertRaises(CaptureCampaignError):
            load_fixtures(payload)

    def test_supported_source_statuses_are_accepted(self) -> None:
        for status in (
            "QUALIFIED_FOR_HISTORICAL_RESEARCH",
            "QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY",
        ):
            payload = copy.deepcopy(self.source_payload)
            payload["qualification"]["prospective_replay_status"] = status
            self.assertEqual(
                load_source_qualification(payload).prospective_replay_status,
                status,
            )

    def test_unqualified_or_live_only_status_is_rejected(self) -> None:
        for status in ("UNKNOWN", "DISQUALIFIED", "QUALIFIED_FOR_LIVE_PRICING"):
            payload = copy.deepcopy(self.source_payload)
            payload["qualification"]["prospective_replay_status"] = status
            with self.assertRaises(CaptureCampaignError, msg=status):
                load_source_qualification(payload)

    def test_source_report_requires_disabled_markets(self) -> None:
        payload = copy.deepcopy(self.source_payload)
        payload["market_statuses"]["HOME_WIN_EITHER_HALF"] = "ENABLED"
        with self.assertRaises(CaptureCampaignError):
            load_source_qualification(payload)

    def test_source_report_requires_no_production_approval(self) -> None:
        payload = copy.deepcopy(self.source_payload)
        payload["holdout_governance"]["production_approval_authorized"] = True
        with self.assertRaises(CaptureCampaignError):
            load_source_qualification(payload)

    def test_forbidden_outcome_or_price_fields_are_rejected(self) -> None:
        payload = copy.deepcopy(self.fixtures_payload)
        payload["fixtures"][0]["decimal_odds"] = "1.85"
        with self.assertRaises(CaptureCampaignError):
            load_fixtures(payload)
        source = copy.deepcopy(self.source_payload)
        source["model_probability"] = 0.7
        with self.assertRaises(CaptureCampaignError):
            load_source_qualification(source)

    def test_generated_tasks_contain_no_odds_or_decision_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._build_bundle(Path(tmp))
        text = bundle.files["tasks"].decode("utf-8")
        for forbidden in (
            "decimal_odds",
            "model_probability",
            "edge",
            "expected_value",
            "kelly",
            "bet_decision",
            "selected_offset_seconds",
        ):
            self.assertNotIn(forbidden, text)

    def test_summary_and_manifest_keep_offset_unselected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._build_bundle(Path(tmp))
        self.assertIsNone(bundle.summary["selected_offset_seconds"])
        self.assertFalse(bundle.summary["selection_authorized"])
        self.assertIsNone(bundle.manifest["selected_offset_seconds"])
        self.assertFalse(bundle.manifest["selection_authorized"])
        self.assertFalse(bundle.manifest["production_approval_authorized"])

    def test_manifest_records_input_and_output_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._build_bundle(Path(tmp))
        self.assertEqual(
            set(bundle.manifest["inputs"]),
            {
                "source_qualification",
                "fixtures",
                "stage_5b2_protocol",
                "campaign_protocol",
            },
        )
        self.assertEqual(set(bundle.manifest["outputs"]), {"tasks", "summary"})
        for identity in list(bundle.manifest["inputs"].values()) + list(
            bundle.manifest["outputs"].values()
        ):
            self.assertEqual(len(identity["sha256"]), 64)

    def test_manifest_records_all_15_markets_and_both_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._build_bundle(Path(tmp))
        self.assertEqual(len(bundle.manifest["market_registry"]), 15)
        statuses = bundle.manifest["model_status_registry"]
        self.assertEqual(statuses["HOME_WIN_EITHER_HALF"], "DISABLED")
        self.assertEqual(statuses["AWAY_WIN_EITHER_HALF"], "DISABLED")
        self.assertEqual(len(MARKET_REGISTRY), 15)

    def test_dirty_worktree_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_inputs(Path(tmp))
            with self.assertRaises(CaptureCampaignExportError):
                build_bundle(
                    source_qualification_path=paths["source"],
                    fixtures_path=paths["fixtures"],
                    stage_5b2_protocol_path=paths["stage5b2"],
                    campaign_protocol_path=paths["campaign"],
                    anchor_at=self.anchor_at,
                    code_state={
                        "evidence_git_head_sha": "1" * 40,
                        "tracked_worktree_clean": False,
                    },
                )

    def test_invalid_git_sha_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_inputs(Path(tmp))
            with self.assertRaises(CaptureCampaignError):
                build_bundle(
                    source_qualification_path=paths["source"],
                    fixtures_path=paths["fixtures"],
                    stage_5b2_protocol_path=paths["stage5b2"],
                    campaign_protocol_path=paths["campaign"],
                    anchor_at=self.anchor_at,
                    code_state={
                        "evidence_git_head_sha": "short",
                        "tracked_worktree_clean": True,
                    },
                )

    def test_transactional_write_and_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = self._build_bundle(root)
            output_dir = root / "out"
            paths = {
                name: output_dir / filename
                for name, filename in OUTPUT_FILENAMES.items()
            }
            commit_bundle(output_paths=paths, contents=bundle.files, force=False)
            check_bundle(output_paths=paths, expected_contents=bundle.files)
            self.assertTrue(all(path.is_file() for path in paths.values()))

    def test_existing_output_requires_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = self._build_bundle(root)
            output_dir = root / "out"
            paths = {
                name: output_dir / filename
                for name, filename in OUTPUT_FILENAMES.items()
            }
            commit_bundle(output_paths=paths, contents=bundle.files, force=False)
            with self.assertRaises(CaptureCampaignExportError):
                commit_bundle(
                    output_paths=paths,
                    contents=bundle.files,
                    force=False,
                )
            commit_bundle(output_paths=paths, contents=bundle.files, force=True)

    def test_check_detects_byte_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = self._build_bundle(root)
            output_dir = root / "out"
            paths = {
                name: output_dir / filename
                for name, filename in OUTPUT_FILENAMES.items()
            }
            commit_bundle(output_paths=paths, contents=bundle.files, force=False)
            paths["summary"].write_bytes(bundle.files["summary"] + b" ")
            with self.assertRaises(CaptureCampaignExportError):
                check_bundle(output_paths=paths, expected_contents=bundle.files)

    @patch("scripts.manage_win_either_half_capture_campaign.get_code_state")
    def test_cli_generate_and_check(self, mock_code_state) -> None:
        mock_code_state.return_value = self.code_state
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._write_inputs(root)
            manifest = root / "out" / OUTPUT_FILENAMES["manifest"]
            common = [
                "--source-qualification",
                str(paths["source"]),
                "--fixtures",
                str(paths["fixtures"]),
                "--stage-5b2-protocol",
                str(paths["stage5b2"]),
                "--campaign-protocol",
                str(paths["campaign"]),
                "--anchor-at",
                self.anchor_at,
            ]
            self.assertEqual(
                run(common + ["--manifest-output", str(manifest)]),
                0,
            )
            self.assertEqual(run(common + ["--check", str(manifest)]), 0)

    @patch("scripts.manage_win_either_half_capture_campaign.get_code_state")
    def test_network_is_not_used(self, mock_code_state) -> None:
        mock_code_state.return_value = self.code_state
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._write_inputs(root)
            manifest = root / "out" / OUTPUT_FILENAMES["manifest"]
            with patch.object(socket.socket, "connect", side_effect=AssertionError):
                result = run(
                    [
                        "--source-qualification",
                        str(paths["source"]),
                        "--fixtures",
                        str(paths["fixtures"]),
                        "--stage-5b2-protocol",
                        str(paths["stage5b2"]),
                        "--campaign-protocol",
                        str(paths["campaign"]),
                        "--anchor-at",
                        self.anchor_at,
                        "--manifest-output",
                        str(manifest),
                    ]
                )
            self.assertEqual(result, 0)

    def test_direct_and_module_help_entrypoints(self) -> None:
        commands = (
            [
                sys.executable,
                "scripts/manage_win_either_half_capture_campaign.py",
                "--help",
            ],
            [
                sys.executable,
                "-m",
                "scripts.manage_win_either_half_capture_campaign",
                "--help",
            ],
        )
        for command in commands:
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
            self.assertIn("Stage 5B3", result.stdout)

    def test_markets_remain_disabled(self) -> None:
        self.assertEqual(
            MODEL_STATUS_REGISTRY[MarketId.HOME_WIN_EITHER_HALF].status,
            ModelStatus.DISABLED,
        )
        self.assertEqual(
            MODEL_STATUS_REGISTRY[MarketId.AWAY_WIN_EITHER_HALF].status,
            ModelStatus.DISABLED,
        )


if __name__ == "__main__":
    unittest.main()
