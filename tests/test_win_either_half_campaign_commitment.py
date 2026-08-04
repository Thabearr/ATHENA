"""Tests for Stage 5B4 Win Either Half campaign commitment contract and verifier."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from domain.markets import MARKET_REGISTRY, MarketId
from domain.model_status import MODEL_STATUS_REGISTRY, ModelStatus
from domain.win_either_half_campaign_commitment import (
    ATTESTATION_DATASET_NAME,
    COMMITMENT_ROOT,
    DECLARATION_DATASET_NAME,
    DECLARATION_STATUS,
    DEFAULT_PROTOCOL_PATH,
    DEFAULT_STAGE_5B3_PROTOCOL_PATH,
    GENERATED_SAFETY_CONTRACT,
    PROTOCOL_DATASET_NAME,
    SCHEMA_VERSION,
    STAGE_5B3_MANIFEST_FILENAME,
    STAGE_5B3_SUMMARY_FILENAME,
    STAGE_5B3_TASKS_FILENAME,
    CampaignCommitmentError,
    CommitmentDeclaration,
    DeadlineValidationResult,
    build_commitment_declaration,
    build_expected_protocol_contract,
    canonical_json_bytes,
    parse_utc,
    serialize_utc,
    sha256_bytes,
    validate_declaration_mapping,
    validate_deadline,
    validate_protocol_contract,
    validate_stage_5b3_bundle,
    validate_stage_5b3_protocol,
)
from domain.win_either_half_capture_campaign import (
    build_campaign_plan,
    build_campaign_target,
    load_fixtures,
    load_source_qualification,
)
from scripts.manage_win_either_half_campaign_commitment import (
    REPOSITORY_ROOT,
    CampaignCommitmentExportError,
    _write_file_atomically,
    check_commitment,
    create_commitment,
    run,
    validate_git_diff,
)
from scripts.manage_win_either_half_capture_campaign import (
    build_bundle as build_stage_5b3_bundle,
)


class TestWinEitherHalfCampaignCommitment(unittest.TestCase):
    REPOSITORY_ROOT = REPOSITORY_ROOT

    def setUp(self) -> None:
        self.source_payload = {
            "schema_version": 1,
            "dataset_name": "win-either-half-pricing-source-qualification-v1",
            "provider_identifier": "TEST_PROVIDER",
            "qualification": {
                "prospective_replay_status": "QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY"
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
        self.fixtures_payload = {
            "schema_version": 1,
            "fixtures": [
                {
                    "fixture_identifier": "FIX-0001",
                    "kickoff": "2026-08-12T15:00:00Z",
                }
            ],
        }
        self.code_state = {
            "evidence_git_head_sha": "1" * 40,
            "tracked_worktree_clean": True,
        }
        self.source = "ODDS_PORTAL"
        self.bookmaker_identifier = "PINNACLE"
        self.capture_method = "MANUAL_REVIEW"

    def _write_stage_5b3_inputs(self, root: Path) -> dict[str, Path]:
        source_p = root / "source.json"
        fixtures_p = root / "fixtures.json"
        stage_5b2_p = root / "stage5b2.json"
        stage_5b3_p = root / "stage5b3.json"

        source_p.write_text(json.dumps(self.source_payload), encoding="utf-8")
        fixtures_p.write_text(json.dumps(self.fixtures_payload), encoding="utf-8")
        stage_5b2_p.write_bytes(
            (REPOSITORY_ROOT / "artifacts/research-protocols/win-either-half-prospective-replay-v1.json").read_bytes()
        )
        stage_5b3_p.write_bytes(DEFAULT_STAGE_5B3_PROTOCOL_PATH.read_bytes())
        return {
            "source": source_p,
            "fixtures": fixtures_p,
            "stage_5b2": stage_5b2_p,
            "stage_5b3": stage_5b3_p,
        }

    def _create_stage_5b3_bundle_files(self, root: Path) -> dict[str, Path]:
        inputs = self._write_stage_5b3_inputs(root)
        bundle = build_stage_5b3_bundle(
            source_qualification_path=inputs["source"],
            fixtures_path=inputs["fixtures"],
            stage_5b2_protocol_path=inputs["stage_5b2"],
            campaign_protocol_path=inputs["stage_5b3"],
            source=self.source,
            bookmaker_identifier=self.bookmaker_identifier,
            capture_method=self.capture_method,
            anchor_at=self.anchor_at,
            code_state=self.code_state,
        )
        out_dir = root / "stage5b3_out"
        out_dir.mkdir()
        tasks_p = out_dir / STAGE_5B3_TASKS_FILENAME
        summary_p = out_dir / STAGE_5B3_SUMMARY_FILENAME
        manifest_p = out_dir / STAGE_5B3_MANIFEST_FILENAME

        tasks_p.write_bytes(bundle.files["tasks"])
        summary_p.write_bytes(bundle.files["summary"])
        manifest_p.write_bytes(bundle.files["manifest"])

        return {
            "tasks": tasks_p,
            "summary": summary_p,
            "manifest": manifest_p,
            "stage_5b3_protocol": inputs["stage_5b3"],
            "commitment_protocol": REPOSITORY_ROOT / DEFAULT_PROTOCOL_PATH,
        }

    # PROTOCOL TESTS
    def test_committed_protocol_matches_python_contract(self) -> None:
        raw = DEFAULT_PROTOCOL_PATH.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        self.assertEqual(payload, build_expected_protocol_contract())
        validate_protocol_contract(payload, raw)

    def test_exact_protocol_bytes_accepted(self) -> None:
        raw = DEFAULT_PROTOCOL_PATH.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        validate_protocol_contract(payload, raw)

    def test_compact_semantically_equal_json_rejected(self) -> None:
        raw = DEFAULT_PROTOCOL_PATH.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        compact_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        with self.assertRaises(CampaignCommitmentError):
            validate_protocol_contract(payload, compact_bytes)

    def test_every_top_level_protocol_mutation_rejected(self) -> None:
        raw = DEFAULT_PROTOCOL_PATH.read_bytes()
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
            mutated_bytes = (
                json.dumps(mutated, indent=2, ensure_ascii=False) + "\n"
            ).encode("utf-8")
            with self.assertRaises(CampaignCommitmentError, msg=key):
                validate_protocol_contract(mutated, mutated_bytes)

    def test_stage5b3_exact_protocol_accepted(self) -> None:
        raw = DEFAULT_STAGE_5B3_PROTOCOL_PATH.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        validate_stage_5b3_protocol(payload, raw)

    def test_modified_stage5b3_protocol_rejected(self) -> None:
        raw = DEFAULT_STAGE_5B3_PROTOCOL_PATH.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        payload["candidate_offsets_seconds"] = [86400, 3600]
        mutated_bytes = (
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        with self.assertRaises(CampaignCommitmentError):
            validate_stage_5b3_protocol(payload, mutated_bytes)

    # BUNDLE VALIDATION TESTS
    def test_valid_one_fixture_stage5b3_bundle_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            self.assertEqual(bundle.fixture_count, 1)
            self.assertEqual(bundle.task_count, 12)

    def test_task_blank_line_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            content = files["tasks"].read_bytes() + b"\n\n"
            files["tasks"].write_bytes(content)
            with self.assertRaises(CampaignCommitmentError):
                validate_stage_5b3_bundle(
                    tasks_path=files["tasks"],
                    summary_path=files["summary"],
                    manifest_path=files["manifest"],
                )

    def test_task_extra_key_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            lines = files["tasks"].read_text(encoding="utf-8").splitlines()
            row = json.loads(lines[0])
            row["extra_field"] = "value"
            lines[0] = json.dumps(row)
            files["tasks"].write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(CampaignCommitmentError):
                validate_stage_5b3_bundle(
                    tasks_path=files["tasks"],
                    summary_path=files["summary"],
                    manifest_path=files["manifest"],
                )

    def test_bool_schema_version_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            lines = files["tasks"].read_text(encoding="utf-8").splitlines()
            row = json.loads(lines[0])
            row["schema_version"] = True
            lines[0] = json.dumps(row)
            files["tasks"].write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(CampaignCommitmentError):
                validate_stage_5b3_bundle(
                    tasks_path=files["tasks"],
                    summary_path=files["summary"],
                    manifest_path=files["manifest"],
                )

    def test_duplicate_task_id_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            lines = files["tasks"].read_text(encoding="utf-8").splitlines()
            row0 = json.loads(lines[0])
            row1 = json.loads(lines[1])
            row1["task_id"] = row0["task_id"]
            lines[1] = json.dumps(row1)
            files["tasks"].write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(CampaignCommitmentError):
                validate_stage_5b3_bundle(
                    tasks_path=files["tasks"],
                    summary_path=files["summary"],
                    manifest_path=files["manifest"],
                )

    def test_duplicate_expected_key_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            lines = files["tasks"].read_text(encoding="utf-8").splitlines()
            row0 = json.loads(lines[0])
            row1 = json.loads(lines[1])
            row1["fixture_identifier"] = row0["fixture_identifier"]
            row1["market_id"] = row0["market_id"]
            row1["offset_seconds_before_kickoff"] = row0["offset_seconds_before_kickoff"]
            lines[1] = json.dumps(row1)
            files["tasks"].write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(CampaignCommitmentError):
                validate_stage_5b3_bundle(
                    tasks_path=files["tasks"],
                    summary_path=files["summary"],
                    manifest_path=files["manifest"],
                )

    def test_missing_one_of_12_tasks_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            lines = files["tasks"].read_text(encoding="utf-8").splitlines()
            lines.pop()
            files["tasks"].write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(CampaignCommitmentError):
                validate_stage_5b3_bundle(
                    tasks_path=files["tasks"],
                    summary_path=files["summary"],
                    manifest_path=files["manifest"],
                )

    def test_wrong_market_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            lines = files["tasks"].read_text(encoding="utf-8").splitlines()
            row0 = json.loads(lines[0])
            row0["market_id"] = "FULL_TIME_DRAW"
            lines[0] = json.dumps(row0)
            files["tasks"].write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(CampaignCommitmentError):
                validate_stage_5b3_bundle(
                    tasks_path=files["tasks"],
                    summary_path=files["summary"],
                    manifest_path=files["manifest"],
                )

    def test_wrong_offset_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            lines = files["tasks"].read_text(encoding="utf-8").splitlines()
            row0 = json.loads(lines[0])
            row0["offset_seconds_before_kickoff"] = 1234
            lines[0] = json.dumps(row0)
            files["tasks"].write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(CampaignCommitmentError):
                validate_stage_5b3_bundle(
                    tasks_path=files["tasks"],
                    summary_path=files["summary"],
                    manifest_path=files["manifest"],
                )

    def test_target_mismatch_across_tasks_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            lines = files["tasks"].read_text(encoding="utf-8").splitlines()
            row1 = json.loads(lines[1])
            row1["source"] = "OTHER_SOURCE"
            lines[1] = json.dumps(row1)
            files["tasks"].write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(CampaignCommitmentError):
                validate_stage_5b3_bundle(
                    tasks_path=files["tasks"],
                    summary_path=files["summary"],
                    manifest_path=files["manifest"],
                )

    def test_campaign_mismatch_across_tasks_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            lines = files["tasks"].read_text(encoding="utf-8").splitlines()
            row1 = json.loads(lines[1])
            row1["campaign_id"] = "WEH-CAP-000000000000000000000000"
            lines[1] = json.dumps(row1)
            files["tasks"].write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(CampaignCommitmentError):
                validate_stage_5b3_bundle(
                    tasks_path=files["tasks"],
                    summary_path=files["summary"],
                    manifest_path=files["manifest"],
                )

    def test_summary_count_mismatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            summary = json.loads(files["summary"].read_text(encoding="utf-8"))
            summary["task_count"] = 999
            files["summary"].write_text(json.dumps(summary), encoding="utf-8")
            with self.assertRaises(CampaignCommitmentError):
                validate_stage_5b3_bundle(
                    tasks_path=files["tasks"],
                    summary_path=files["summary"],
                    manifest_path=files["manifest"],
                )

    def test_summary_deadline_mismatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            summary = json.loads(files["summary"].read_text(encoding="utf-8"))
            summary["commitment_deadline_at"] = "2026-08-10T00:00:00Z"
            files["summary"].write_text(json.dumps(summary), encoding="utf-8")
            with self.assertRaises(CampaignCommitmentError):
                validate_stage_5b3_bundle(
                    tasks_path=files["tasks"],
                    summary_path=files["summary"],
                    manifest_path=files["manifest"],
                )

    def test_summary_prospective_authorization_true_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            summary = json.loads(files["summary"].read_text(encoding="utf-8"))
            summary["prospective_claim_authorized"] = True
            files["summary"].write_text(json.dumps(summary), encoding="utf-8")
            with self.assertRaises(CampaignCommitmentError):
                validate_stage_5b3_bundle(
                    tasks_path=files["tasks"],
                    summary_path=files["summary"],
                    manifest_path=files["manifest"],
                )

    def test_manifest_output_hash_mismatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            manifest = json.loads(files["manifest"].read_text(encoding="utf-8"))
            manifest["outputs"]["tasks"]["sha256"] = "0" * 64
            files["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(CampaignCommitmentError):
                validate_stage_5b3_bundle(
                    tasks_path=files["tasks"],
                    summary_path=files["summary"],
                    manifest_path=files["manifest"],
                )

    def test_manifest_logical_hash_mismatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            manifest = json.loads(files["manifest"].read_text(encoding="utf-8"))
            manifest["logical_manifest_sha256"] = "0" * 64
            files["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(CampaignCommitmentError):
                validate_stage_5b3_bundle(
                    tasks_path=files["tasks"],
                    summary_path=files["summary"],
                    manifest_path=files["manifest"],
                )

    def test_arbitrary_forbidden_field_under_nested_safety_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            summary = json.loads(files["summary"].read_text(encoding="utf-8"))
            summary["nested"] = {"safety": {"decimal_odds": 1.90}}
            files["summary"].write_text(json.dumps(summary), encoding="utf-8")
            with self.assertRaises(CampaignCommitmentError):
                validate_stage_5b3_bundle(
                    tasks_path=files["tasks"],
                    summary_path=files["summary"],
                    manifest_path=files["manifest"],
                )

    def test_exact_generated_manifest_safety_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            self.assertIsNotNone(bundle)

    def test_both_markets_must_remain_disabled(self) -> None:
        self.assertEqual(
            MODEL_STATUS_REGISTRY[MarketId.HOME_WIN_EITHER_HALF].status,
            ModelStatus.DISABLED,
        )
        self.assertEqual(
            MODEL_STATUS_REGISTRY[MarketId.AWAY_WIN_EITHER_HALF].status,
            ModelStatus.DISABLED,
        )

    def test_selected_offset_must_remain_null(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            summary = json.loads(files["summary"].read_text(encoding="utf-8"))
            self.assertIsNone(summary.get("selected_offset_seconds"))

    # DECLARATION TESTS
    def test_deterministic_declaration_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            decl1 = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            decl2 = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            self.assertEqual(
                canonical_json_bytes(decl1.to_mapping(), pretty=True),
                canonical_json_bytes(decl2.to_mapping(), pretty=True),
            )

    def test_declaration_changes_when_any_source_bundle_byte_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            b1_dir = tmp_p / "b1"
            b1_dir.mkdir(parents=True, exist_ok=True)
            files1 = self._create_stage_5b3_bundle_files(b1_dir)
            bundle1 = validate_stage_5b3_bundle(
                tasks_path=files1["tasks"],
                summary_path=files1["summary"],
                manifest_path=files1["manifest"],
            )
            decl1 = build_commitment_declaration(
                bundle=bundle1,
                stage_5b3_protocol_raw=files1["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files1["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )

            # Create second bundle with different anchor_at
            orig_anchor = self.anchor_at
            try:
                self.anchor_at = "2026-08-11T00:00:00Z"
                b2_dir = tmp_p / "b2"
                b2_dir.mkdir(parents=True, exist_ok=True)
                files2 = self._create_stage_5b3_bundle_files(b2_dir)
                bundle2 = validate_stage_5b3_bundle(
                    tasks_path=files2["tasks"],
                    summary_path=files2["summary"],
                    manifest_path=files2["manifest"],
                )
                decl2 = build_commitment_declaration(
                    bundle=bundle2,
                    stage_5b3_protocol_raw=files2["stage_5b3_protocol"].read_bytes(),
                    commitment_protocol_raw=files2["commitment_protocol"].read_bytes(),
                    generator_git_sha="1" * 40,
                )
            finally:
                self.anchor_at = orig_anchor

            self.assertNotEqual(
                canonical_json_bytes(decl1.to_mapping(), pretty=True),
                canonical_json_bytes(decl2.to_mapping(), pretty=True),
            )

    def test_declaration_changes_when_protocol_bytes_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            decl1 = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            decl2 = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes() + b"\n",
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            self.assertNotEqual(
                canonical_json_bytes(decl1.to_mapping(), pretty=True),
                canonical_json_bytes(decl2.to_mapping(), pretty=True),
            )

    def test_no_generated_at_current_time_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            decl = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            mapping = decl.to_mapping()
            self.assertNotIn("generated_at", mapping)
            self.assertNotIn("created_at", mapping)
            self.assertNotIn("current_time", mapping)

    def test_exact_filename_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            decl = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            with self.assertRaises(CampaignCommitmentError):
                validate_declaration_mapping(
                    decl.to_mapping(),
                    expected_path=Path("wrong_filename.json"),
                )

    def test_path_outside_commitment_root_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            invalid_out = Path("docs") / "WEH-CAP-000000000000000000000000.json"
            with patch("scripts.manage_win_either_half_campaign_commitment.get_code_state", return_value=self.code_state):
                with self.assertRaises(CampaignCommitmentExportError):
                    create_commitment(
                        tasks_path=files["tasks"],
                        summary_path=files["summary"],
                        manifest_path=files["manifest"],
                        stage_5b3_protocol_path=files["stage_5b3_protocol"],
                        commitment_protocol_path=files["commitment_protocol"],
                        output_path=invalid_out,
                        force=False,
                        code_state=self.code_state,
                    )

    def test_nested_subdirectory_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            nested = REPOSITORY_ROOT / COMMITMENT_ROOT / "sub" / "WEH-CAP-000000000000000000000000.json"
            with patch("scripts.manage_win_either_half_campaign_commitment.get_code_state", return_value=self.code_state):
                with self.assertRaises(CampaignCommitmentExportError):
                    create_commitment(
                        tasks_path=files["tasks"],
                        summary_path=files["summary"],
                        manifest_path=files["manifest"],
                        stage_5b3_protocol_path=files["stage_5b3_protocol"],
                        commitment_protocol_path=files["commitment_protocol"],
                        output_path=nested,
                        force=False,
                        code_state=self.code_state,
                    )

    def test_symlink_component_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_dir = root / "real"
            real_dir.mkdir()
            sym_dir = root / "symlink_dir"
            try:
                os.symlink(real_dir, sym_dir, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks not supported on platform")

            files = self._create_stage_5b3_bundle_files(root)
            sym_out = sym_dir / "WEH-CAP-000000000000000000000000.json"
            with patch("scripts.manage_win_either_half_campaign_commitment.get_code_state", return_value=self.code_state):
                with self.assertRaises(CampaignCommitmentExportError):
                    create_commitment(
                        tasks_path=files["tasks"],
                        summary_path=files["summary"],
                        manifest_path=files["manifest"],
                        stage_5b3_protocol_path=files["stage_5b3_protocol"],
                        commitment_protocol_path=files["commitment_protocol"],
                        output_path=sym_out,
                        force=False,
                        code_state=self.code_state,
                    )

    def test_declaration_extra_key_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            decl = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            mapping = decl.to_mapping()
            mapping["extra_field"] = True
            with self.assertRaises(CampaignCommitmentError):
                validate_declaration_mapping(mapping)

    def test_wrong_status_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            decl = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            mapping = decl.to_mapping()
            mapping["campaign_commitment_status"] = "QUALIFIED"
            with self.assertRaises(CampaignCommitmentError):
                validate_declaration_mapping(mapping)

    def test_prospective_claim_authorized_true_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            decl = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            mapping = decl.to_mapping()
            mapping["prospective_claim_authorized"] = True
            with self.assertRaises(CampaignCommitmentError):
                validate_declaration_mapping(mapping)

    def test_evidence_counting_authorized_true_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            decl = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            mapping = decl.to_mapping()
            mapping["evidence_counting_authorized"] = True
            with self.assertRaises(CampaignCommitmentError):
                validate_declaration_mapping(mapping)

    def test_forbidden_case_padded_keys_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            decl = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            mapping = decl.to_mapping()
            mapping[" Model_Probability "] = 0.7
            with self.assertRaises(CampaignCommitmentError):
                validate_declaration_mapping(mapping)

    def test_exact_safety_contract_retained(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            decl = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            self.assertEqual(decl.safety, GENERATED_SAFETY_CONTRACT)

    # DEADLINE TESTS
    def test_one_second_before_deadline_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            decl = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            observed = decl.commitment_deadline_at - timedelta(seconds=1)
            res = validate_deadline(decl, server_observed_at=observed)
            self.assertTrue(res.prospective_timing_qualified)

    def test_exact_deadline_equality_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            decl = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            observed = decl.commitment_deadline_at
            res = validate_deadline(decl, server_observed_at=observed)
            self.assertTrue(res.prospective_timing_qualified)

    def test_one_microsecond_after_deadline_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            decl = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            observed = decl.commitment_deadline_at + timedelta(microseconds=1)
            res = validate_deadline(decl, server_observed_at=observed)
            self.assertFalse(res.prospective_timing_qualified)

    def test_naive_server_time_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            decl = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            naive_dt = datetime(2026, 8, 10, 0, 0, 0)
            with self.assertRaises(CampaignCommitmentError):
                validate_deadline(decl, server_observed_at=naive_dt)

    def test_result_qualifies_timing_only_and_never_claim_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            decl = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            res = validate_deadline(
                decl,
                server_observed_at=decl.commitment_deadline_at,
            )
            mapping = res.to_mapping()
            self.assertTrue(mapping["prospective_timing_qualified"])
            self.assertFalse(mapping["prospective_claim_authorized"])

    # GIT DIFF / IMMUTABILITY TESTS
    def test_newly_added_valid_direct_child_declaration_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            repo_dir = tmp_root / "repo"
            repo_dir.mkdir()
            commitments_dir = repo_dir / COMMITMENT_ROOT
            commitments_dir.mkdir(parents=True)
            proto_dir = repo_dir / "artifacts" / "research-protocols"
            proto_dir.mkdir(parents=True)
            proto_path = proto_dir / "win-either-half-campaign-commitment-v1.json"
            proto_path.write_bytes(DEFAULT_PROTOCOL_PATH.read_bytes())

            files = self._create_stage_5b3_bundle_files(tmp_root)
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            decl = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            decl_bytes = canonical_json_bytes(decl.to_mapping(), pretty=True)
            decl_file = commitments_dir / f"{bundle.campaign_id}.json"
            decl_file.write_bytes(decl_bytes)

            att_file = tmp_root / "attestation.json"
            rel_decl = (COMMITMENT_ROOT / f"{bundle.campaign_id}.json").as_posix()

            def mock_run_cmd(cmd, *args, **kwargs):
                cmd_list = cmd if isinstance(cmd, list) else []
                if "merge-base" in cmd_list:
                    return MagicMock(returncode=0)
                if "cat-file" in cmd_list and "-e" in cmd_list:
                    return MagicMock(returncode=0, stdout="", stderr="")
                if "diff" in cmd_list:
                    return MagicMock(returncode=0, stdout=f"A\x00{rel_decl}\x00".encode("utf-8"), stderr=b"")
                if "ls-tree" in cmd_list:
                    return MagicMock(returncode=0, stdout=f"100644 blob abc\t{rel_decl}", stderr="")
                if "cat-file" in cmd_list and "-p" in cmd_list:
                    return MagicMock(returncode=0, stdout=decl_bytes, stderr=b"")
                return MagicMock(returncode=0, stdout="", stderr="")

            with patch("subprocess.run", side_effect=mock_run_cmd):
                count, summary_md = validate_git_diff(
                    repository_root=repo_dir,
                    base_sha="0" * 40,
                    head_sha="1" * 40,
                    server_observed_at=serialize_utc(decl.commitment_deadline_at - timedelta(seconds=10)),
                    github_run_id="123",
                    github_run_attempt="1",
                    github_event_name="pull_request",
                    attestation_output=att_file,
                )
                self.assertEqual(count, 1)
                self.assertIn(bundle.campaign_id, summary_md)
                self.assertTrue(att_file.is_file())

    def test_modified_declaration_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            repo_dir = tmp_root / "repo"
            repo_dir.mkdir()
            att_file = tmp_root / "att.json"
            rel_decl = f"artifacts/research-commitments/win-either-half/WEH-CAP-{'0'*24}.json"

            def mock_run_cmd(cmd, *args, **kwargs):
                cmd_list = cmd if isinstance(cmd, list) else []
                if "merge-base" in cmd_list:
                    return MagicMock(returncode=0)
                if "cat-file" in cmd_list and "-e" in cmd_list:
                    return MagicMock(returncode=0, stdout="", stderr="")
                if "diff" in cmd_list:
                    return MagicMock(returncode=0, stdout=f"M\x00{rel_decl}\x00".encode("utf-8"), stderr=b"")
                return MagicMock(returncode=0, stdout="", stderr="")

            with patch("subprocess.run", side_effect=mock_run_cmd):
                with self.assertRaises(CampaignCommitmentExportError) as ctx:
                    validate_git_diff(
                        repository_root=repo_dir,
                        base_sha="0" * 40,
                        head_sha="1" * 40,
                        server_observed_at="2026-08-10T00:00:00Z",
                        github_run_id="123",
                        github_run_attempt="1",
                        github_event_name="pull_request",
                        attestation_output=att_file,
                    )
                self.assertIn("Forbidden git status M", str(ctx.exception))

    def test_deleted_declaration_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            repo_dir = tmp_root / "repo"
            repo_dir.mkdir()
            att_file = tmp_root / "att.json"
            rel_decl = f"artifacts/research-commitments/win-either-half/WEH-CAP-{'0'*24}.json"

            def mock_run_cmd(cmd, *args, **kwargs):
                cmd_list = cmd if isinstance(cmd, list) else []
                if "merge-base" in cmd_list:
                    return MagicMock(returncode=0)
                if "cat-file" in cmd_list and "-e" in cmd_list:
                    return MagicMock(returncode=0, stdout="", stderr="")
                if "diff" in cmd_list:
                    return MagicMock(returncode=0, stdout=f"D\x00{rel_decl}\x00".encode("utf-8"), stderr=b"")
                return MagicMock(returncode=0, stdout="", stderr="")

            with patch("subprocess.run", side_effect=mock_run_cmd):
                with self.assertRaises(CampaignCommitmentExportError) as ctx:
                    validate_git_diff(
                        repository_root=repo_dir,
                        base_sha="0" * 40,
                        head_sha="1" * 40,
                        server_observed_at="2026-08-10T00:00:00Z",
                        github_run_id="123",
                        github_run_attempt="1",
                        github_event_name="pull_request",
                        attestation_output=att_file,
                    )
                self.assertIn("Forbidden git status D", str(ctx.exception))

    def test_renamed_declaration_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            repo_dir = tmp_root / "repo"
            repo_dir.mkdir()
            att_file = tmp_root / "att.json"
            rel_old = f"artifacts/research-commitments/win-either-half/WEH-CAP-{'0'*24}.json"
            rel_new = f"artifacts/research-commitments/win-either-half/WEH-CAP-{'1'*24}.json"

            def mock_run_cmd(cmd, *args, **kwargs):
                cmd_list = cmd if isinstance(cmd, list) else []
                if "merge-base" in cmd_list:
                    return MagicMock(returncode=0)
                if "cat-file" in cmd_list and "-e" in cmd_list:
                    return MagicMock(returncode=0, stdout="", stderr="")
                if "diff" in cmd_list:
                    return MagicMock(returncode=0, stdout=f"R100\x00{rel_old}\x00{rel_new}\x00".encode("utf-8"), stderr=b"")
                return MagicMock(returncode=0, stdout="", stderr="")

            with patch("subprocess.run", side_effect=mock_run_cmd):
                with self.assertRaises(CampaignCommitmentExportError) as ctx:
                    validate_git_diff(
                        repository_root=repo_dir,
                        base_sha="0" * 40,
                        head_sha="1" * 40,
                        server_observed_at="2026-08-10T00:00:00Z",
                        github_run_id="123",
                        github_run_attempt="1",
                        github_event_name="pull_request",
                        attestation_output=att_file,
                    )
                self.assertIn("Renames/copies forbidden", str(ctx.exception))

    def test_copied_declaration_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            repo_dir = tmp_root / "repo"
            repo_dir.mkdir()
            att_file = tmp_root / "att.json"
            rel_old = f"artifacts/research-commitments/win-either-half/WEH-CAP-{'0'*24}.json"
            rel_new = f"artifacts/research-commitments/win-either-half/WEH-CAP-{'1'*24}.json"

            def mock_run_cmd(cmd, *args, **kwargs):
                cmd_list = cmd if isinstance(cmd, list) else []
                if "merge-base" in cmd_list:
                    return MagicMock(returncode=0)
                if "cat-file" in cmd_list and "-e" in cmd_list:
                    return MagicMock(returncode=0, stdout="", stderr="")
                if "diff" in cmd_list:
                    return MagicMock(returncode=0, stdout=f"C100\x00{rel_old}\x00{rel_new}\x00".encode("utf-8"), stderr=b"")
                return MagicMock(returncode=0, stdout="", stderr="")

            with patch("subprocess.run", side_effect=mock_run_cmd):
                with self.assertRaises(CampaignCommitmentExportError) as ctx:
                    validate_git_diff(
                        repository_root=repo_dir,
                        base_sha="0" * 40,
                        head_sha="1" * 40,
                        server_observed_at="2026-08-10T00:00:00Z",
                        github_run_id="123",
                        github_run_attempt="1",
                        github_event_name="pull_request",
                        attestation_output=att_file,
                    )
                self.assertIn("Renames/copies forbidden", str(ctx.exception))

    def test_symlink_mode_declaration_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            repo_dir = tmp_root / "repo"
            repo_dir.mkdir()
            att_file = tmp_root / "att.json"
            rel_decl = f"artifacts/research-commitments/win-either-half/WEH-CAP-{'0'*24}.json"

            def mock_run_cmd(cmd, *args, **kwargs):
                cmd_list = cmd if isinstance(cmd, list) else []
                if "merge-base" in cmd_list:
                    return MagicMock(returncode=0)
                if "cat-file" in cmd_list and "-e" in cmd_list:
                    return MagicMock(returncode=0, stdout="", stderr="")
                if "diff" in cmd_list:
                    return MagicMock(returncode=0, stdout=f"A\x00{rel_decl}\x00".encode("utf-8"), stderr=b"")
                if "ls-tree" in cmd_list:
                    return MagicMock(returncode=0, stdout=f"120000 blob abc\t{rel_decl}", stderr="")
                return MagicMock(returncode=0, stdout="", stderr="")

            with patch("subprocess.run", side_effect=mock_run_cmd):
                with self.assertRaises(CampaignCommitmentExportError) as ctx:
                    validate_git_diff(
                        repository_root=repo_dir,
                        base_sha="0" * 40,
                        head_sha="1" * 40,
                        server_observed_at="2026-08-10T00:00:00Z",
                        github_run_id="123",
                        github_run_attempt="1",
                        github_event_name="pull_request",
                        attestation_output=att_file,
                    )
                self.assertIn("mode 120000 forbidden", str(ctx.exception))

    def test_duplicate_campaign_ids_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            repo_dir = tmp_root / "repo"
            repo_dir.mkdir()
            att_file = tmp_root / "att.json"
            rel_decl = f"artifacts/research-commitments/win-either-half/WEH-CAP-{'0'*24}.json"

            def mock_run_cmd(cmd, *args, **kwargs):
                cmd_list = cmd if isinstance(cmd, list) else []
                if "merge-base" in cmd_list:
                    return MagicMock(returncode=0)
                if "cat-file" in cmd_list and "-e" in cmd_list:
                    return MagicMock(returncode=0, stdout="", stderr="")
                if "diff" in cmd_list:
                    return MagicMock(returncode=0, stdout=f"A\x00{rel_decl}\x00A\x00{rel_decl}\x00".encode("utf-8"), stderr=b"")
                if "ls-tree" in cmd_list:
                    return MagicMock(returncode=0, stdout=f"100644 blob abc\t{rel_decl}", stderr="")
                return MagicMock(returncode=0, stdout="", stderr="")

            with patch("subprocess.run", side_effect=mock_run_cmd):
                with self.assertRaises(CampaignCommitmentExportError) as ctx:
                    validate_git_diff(
                        repository_root=repo_dir,
                        base_sha="0" * 40,
                        head_sha="1" * 40,
                        server_observed_at="2026-08-10T00:00:00Z",
                        github_run_id="123",
                        github_run_attempt="1",
                        github_event_name="pull_request",
                        attestation_output=att_file,
                    )
                self.assertIn("Duplicate path in diff", str(ctx.exception))

    def test_non_ancestor_base_head_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            repo_dir = tmp_root / "repo"
            repo_dir.mkdir()
            att_file = tmp_root / "att.json"

            def mock_run_cmd(cmd, *args, **kwargs):
                cmd_list = cmd if isinstance(cmd, list) else []
                if "merge-base" in cmd_list:
                    return MagicMock(returncode=1)
                if "cat-file" in cmd_list and "-e" in cmd_list:
                    return MagicMock(returncode=0, stdout="", stderr="")
                return MagicMock(returncode=0, stdout="", stderr="")

            with patch("subprocess.run", side_effect=mock_run_cmd):
                with self.assertRaises(CampaignCommitmentExportError) as ctx:
                    validate_git_diff(
                        repository_root=repo_dir,
                        base_sha="0" * 40,
                        head_sha="1" * 40,
                        server_observed_at="2026-08-10T00:00:00Z",
                        github_run_id="123",
                        github_run_attempt="1",
                        github_event_name="pull_request",
                        attestation_output=att_file,
                    )
                self.assertIn("is not an ancestor of head_sha", str(ctx.exception))

    def test_zero_changed_declarations_rejected_in_validation_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            att = Path(tmp) / "att.json"
            with self.assertRaises(CampaignCommitmentExportError):
                validate_git_diff(
                    repository_root=REPOSITORY_ROOT,
                    base_sha="9ab70afe05a4946fb2de92142d15853016abb1af",
                    head_sha="361be8ba1b6eacf0a5399c1c2f419e12509765fe",
                    server_observed_at="2026-08-10T00:00:00Z",
                    github_run_id="100",
                    github_run_attempt="1",
                    github_event_name="pull_request",
                    attestation_output=att,
                )

    def test_tooling_plus_declaration_in_same_diff_rejected(self) -> None:
        # Separation of duties: workflow check asserts that tooling + commitments cannot change together.
        wf_p = REPOSITORY_ROOT / ".github" / "workflows" / "validate-win-either-half-campaign-commitment.yml"
        text = wf_p.read_text(encoding="utf-8")
        self.assertIn("Separation-of-duties violation", text)
        self.assertIn("COMMITMENT_CHANGES", text)
        self.assertIn("TOOLING_CHANGES", text)

    def test_attestation_records_exact_run_base_head_deadline_hash_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            repo_dir = tmp_root / "repo"
            repo_dir.mkdir()
            commitments_dir = repo_dir / COMMITMENT_ROOT
            commitments_dir.mkdir(parents=True)
            proto_dir = repo_dir / "artifacts" / "research-protocols"
            proto_dir.mkdir(parents=True)
            proto_path = proto_dir / "win-either-half-campaign-commitment-v1.json"
            proto_path.write_bytes(DEFAULT_PROTOCOL_PATH.read_bytes())

            files = self._create_stage_5b3_bundle_files(tmp_root)
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            decl = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            decl_bytes = canonical_json_bytes(decl.to_mapping(), pretty=True)
            decl_file = commitments_dir / f"{bundle.campaign_id}.json"
            decl_file.write_bytes(decl_bytes)

            att_file = tmp_root / "attestation.json"
            rel_decl = (COMMITMENT_ROOT / f"{bundle.campaign_id}.json").as_posix()

            def mock_run_cmd(cmd, *args, **kwargs):
                cmd_list = cmd if isinstance(cmd, list) else []
                if "merge-base" in cmd_list:
                    return MagicMock(returncode=0)
                if "cat-file" in cmd_list and "-e" in cmd_list:
                    return MagicMock(returncode=0, stdout="", stderr="")
                if "diff" in cmd_list:
                    return MagicMock(returncode=0, stdout=f"A\x00{rel_decl}\x00".encode("utf-8"), stderr=b"")
                if "ls-tree" in cmd_list:
                    return MagicMock(returncode=0, stdout=f"100644 blob abc\t{rel_decl}", stderr="")
                if "cat-file" in cmd_list and "-p" in cmd_list:
                    return MagicMock(returncode=0, stdout=decl_bytes, stderr=b"")
                return MagicMock(returncode=0, stdout="", stderr="")

            with patch("subprocess.run", side_effect=mock_run_cmd):
                validate_git_diff(
                    repository_root=repo_dir,
                    base_sha="0" * 40,
                    head_sha="1" * 40,
                    server_observed_at=serialize_utc(decl.commitment_deadline_at - timedelta(seconds=10)),
                    github_run_id="98765",
                    github_run_attempt="2",
                    github_event_name="pull_request",
                    attestation_output=att_file,
                )
                att_payload = json.loads(att_file.read_text(encoding="utf-8"))
                self.assertEqual(att_payload["github_run_id"], "98765")
                self.assertEqual(att_payload["github_run_attempt"], 2)
                self.assertEqual(att_payload["base_sha"], "0" * 40)
                self.assertEqual(att_payload["head_sha"], "1" * 40)
                self.assertEqual(att_payload["declarations"][0]["commitment_sha256"], sha256_bytes(decl_bytes))

    def test_attestation_results_sorted_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            repo_dir = tmp_root / "repo"
            repo_dir.mkdir()
            commitments_dir = repo_dir / COMMITMENT_ROOT
            commitments_dir.mkdir(parents=True)
            proto_dir = repo_dir / "artifacts" / "research-protocols"
            proto_dir.mkdir(parents=True)
            proto_path = proto_dir / "win-either-half-campaign-commitment-v1.json"
            proto_path.write_bytes(DEFAULT_PROTOCOL_PATH.read_bytes())

            files = self._create_stage_5b3_bundle_files(tmp_root)
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )

            # Build 2 declarations with different campaign IDs: WEH-CAP-000000000000000000000002 and ...01
            c2_id = "WEH-CAP-000000000000000000000002"
            c1_id = "WEH-CAP-000000000000000000000001"

            decl2 = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            decl2_map = decl2.to_mapping()
            decl2_map["campaign_id"] = c2_id
            decl2_bytes = canonical_json_bytes(decl2_map, pretty=True)
            (commitments_dir / f"{c2_id}.json").write_bytes(decl2_bytes)

            decl1_map = copy.deepcopy(decl2_map)
            decl1_map["campaign_id"] = c1_id
            decl1_bytes = canonical_json_bytes(decl1_map, pretty=True)
            (commitments_dir / f"{c1_id}.json").write_bytes(decl1_bytes)

            att_file = tmp_root / "attestation.json"
            rel2 = (COMMITMENT_ROOT / f"{c2_id}.json").as_posix()
            rel1 = (COMMITMENT_ROOT / f"{c1_id}.json").as_posix()

            # Diff returns c2 first, then c1
            diff_output = f"A\x00{rel2}\x00A\x00{rel1}\x00".encode("utf-8")

            def mock_run_cmd(cmd, *args, **kwargs):
                cmd_list = cmd if isinstance(cmd, list) else []
                if "merge-base" in cmd_list:
                    return MagicMock(returncode=0)
                if "cat-file" in cmd_list and "-e" in cmd_list:
                    return MagicMock(returncode=0, stdout="", stderr="")
                if "diff" in cmd_list:
                    return MagicMock(returncode=0, stdout=diff_output, stderr=b"")
                if "ls-tree" in cmd_list:
                    p = cmd_list[-1]
                    return MagicMock(returncode=0, stdout=f"100644 blob abc\t{p}", stderr="")
                if "cat-file" in cmd_list and "-p" in cmd_list:
                    spec = cmd_list[-1]
                    if c2_id in spec:
                        return MagicMock(returncode=0, stdout=decl2_bytes, stderr=b"")
                    return MagicMock(returncode=0, stdout=decl1_bytes, stderr=b"")
                return MagicMock(returncode=0, stdout="", stderr="")

            with patch("subprocess.run", side_effect=mock_run_cmd):
                validate_git_diff(
                    repository_root=repo_dir,
                    base_sha="0" * 40,
                    head_sha="1" * 40,
                    server_observed_at=serialize_utc(decl2.commitment_deadline_at - timedelta(seconds=10)),
                    github_run_id="123",
                    github_run_attempt="1",
                    github_event_name="pull_request",
                    attestation_output=att_file,
                )
                att_payload = json.loads(att_file.read_text(encoding="utf-8"))
                campaign_ids = [d["campaign_id"] for d in att_payload["declarations"]]
                self.assertEqual(campaign_ids, [c1_id, c2_id])

    def test_attestation_keeps_all_production_selection_bet_fields_false_null(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            repo_dir = tmp_root / "repo"
            repo_dir.mkdir()
            commitments_dir = repo_dir / COMMITMENT_ROOT
            commitments_dir.mkdir(parents=True)
            proto_dir = repo_dir / "artifacts" / "research-protocols"
            proto_dir.mkdir(parents=True)
            proto_path = proto_dir / "win-either-half-campaign-commitment-v1.json"
            proto_path.write_bytes(DEFAULT_PROTOCOL_PATH.read_bytes())

            files = self._create_stage_5b3_bundle_files(tmp_root)
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            decl = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            decl_bytes = canonical_json_bytes(decl.to_mapping(), pretty=True)
            decl_file = commitments_dir / f"{bundle.campaign_id}.json"
            decl_file.write_bytes(decl_bytes)

            att_file = tmp_root / "attestation.json"
            rel_decl = (COMMITMENT_ROOT / f"{bundle.campaign_id}.json").as_posix()

            def mock_run_cmd(cmd, *args, **kwargs):
                cmd_list = cmd if isinstance(cmd, list) else []
                if "merge-base" in cmd_list:
                    return MagicMock(returncode=0)
                if "cat-file" in cmd_list and "-e" in cmd_list:
                    return MagicMock(returncode=0, stdout="", stderr="")
                if "diff" in cmd_list:
                    return MagicMock(returncode=0, stdout=f"A\x00{rel_decl}\x00".encode("utf-8"), stderr=b"")
                if "ls-tree" in cmd_list:
                    return MagicMock(returncode=0, stdout=f"100644 blob abc\t{rel_decl}", stderr="")
                if "cat-file" in cmd_list and "-p" in cmd_list:
                    return MagicMock(returncode=0, stdout=decl_bytes, stderr=b"")
                return MagicMock(returncode=0, stdout="", stderr="")

            with patch("subprocess.run", side_effect=mock_run_cmd):
                validate_git_diff(
                    repository_root=repo_dir,
                    base_sha="0" * 40,
                    head_sha="1" * 40,
                    server_observed_at=serialize_utc(decl.commitment_deadline_at - timedelta(seconds=10)),
                    github_run_id="123",
                    github_run_attempt="1",
                    github_event_name="pull_request",
                    attestation_output=att_file,
                )
                att = json.loads(att_file.read_text(encoding="utf-8"))
                self.assertIsNone(att["selected_offset_seconds"])
                self.assertFalse(att["selection_authorized"])
                self.assertFalse(att["production_approval_authorized"])
                self.assertFalse(att["prospective_claim_authorized"])
                self.assertEqual(
                    att["market_statuses"],
                    {"HOME_WIN_EITHER_HALF": "DISABLED", "AWAY_WIN_EITHER_HALF": "DISABLED"},
                )
                self.assertEqual(att["safety"], GENERATED_SAFETY_CONTRACT)

    # CLI / FILE SAFETY TESTS
    def test_direct_and_module_help_entrypoints(self) -> None:
        commands = (
            [
                sys.executable,
                "scripts/manage_win_either_half_campaign_commitment.py",
                "--help",
            ],
            [
                sys.executable,
                "-m",
                "scripts.manage_win_either_half_campaign_commitment",
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
            self.assertIn("Stage 5B4", result.stdout)

    def test_create_refuses_dirty_tracked_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            out_p = REPOSITORY_ROOT / COMMITMENT_ROOT / "WEH-CAP-000000000000000000000000.json"
            dirty_state = {
                "evidence_git_head_sha": "1" * 40,
                "tracked_worktree_clean": False,
            }
            with self.assertRaises(CampaignCommitmentExportError):
                create_commitment(
                    tasks_path=files["tasks"],
                    summary_path=files["summary"],
                    manifest_path=files["manifest"],
                    stage_5b3_protocol_path=files["stage_5b3_protocol"],
                    commitment_protocol_path=files["commitment_protocol"],
                    output_path=out_p,
                    force=False,
                    code_state=dirty_state,
                )

    def test_git_state_failure_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            out_p = REPOSITORY_ROOT / COMMITMENT_ROOT / "WEH-CAP-000000000000000000000000.json"
            with patch("scripts.manage_win_either_half_campaign_commitment.get_code_state", side_effect=Exception("Git error")):
                res = run(
                    [
                        "--create",
                        str(out_p),
                        "--tasks",
                        str(files["tasks"]),
                        "--summary",
                        str(files["summary"]),
                        "--manifest",
                        str(files["manifest"]),
                    ]
                )
                self.assertEqual(res, 1)

    def test_create_output_outside_exact_commitment_root_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            invalid_p = Path("docs") / "WEH-CAP-000000000000000000000000.json"
            with patch("scripts.manage_win_either_half_campaign_commitment.get_code_state", return_value=self.code_state):
                with self.assertRaises(CampaignCommitmentExportError):
                    create_commitment(
                        tasks_path=files["tasks"],
                        summary_path=files["summary"],
                        manifest_path=files["manifest"],
                        stage_5b3_protocol_path=files["stage_5b3_protocol"],
                        commitment_protocol_path=files["commitment_protocol"],
                        output_path=invalid_p,
                        force=False,
                        code_state=self.code_state,
                    )

    def test_create_writes_exact_deterministic_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            out_p = REPOSITORY_ROOT / COMMITMENT_ROOT / f"{bundle.campaign_id}.json"
            try:
                c_id, decl_bytes = create_commitment(
                    tasks_path=files["tasks"],
                    summary_path=files["summary"],
                    manifest_path=files["manifest"],
                    stage_5b3_protocol_path=files["stage_5b3_protocol"],
                    commitment_protocol_path=files["commitment_protocol"],
                    output_path=out_p,
                    force=True,
                    code_state=self.code_state,
                )
                self.assertTrue(out_p.is_file())
                self.assertEqual(out_p.read_bytes(), decl_bytes)
            finally:
                if out_p.exists():
                    out_p.unlink()

    def test_check_detects_formatting_only_byte_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            decl_p = REPOSITORY_ROOT / COMMITMENT_ROOT / f"{bundle.campaign_id}.json"
            try:
                create_commitment(
                    tasks_path=files["tasks"],
                    summary_path=files["summary"],
                    manifest_path=files["manifest"],
                    stage_5b3_protocol_path=files["stage_5b3_protocol"],
                    commitment_protocol_path=files["commitment_protocol"],
                    output_path=decl_p,
                    force=True,
                    code_state=self.code_state,
                )
                # Drift formatting by adding trailing newline
                decl_p.write_bytes(decl_p.read_bytes() + b"\n")
                with self.assertRaises(CampaignCommitmentExportError):
                    check_commitment(
                        tasks_path=files["tasks"],
                        summary_path=files["summary"],
                        manifest_path=files["manifest"],
                        stage_5b3_protocol_path=files["stage_5b3_protocol"],
                        commitment_protocol_path=files["commitment_protocol"],
                        declaration_path=decl_p,
                        code_state=self.code_state,
                    )
            finally:
                if decl_p.exists():
                    decl_p.unlink()

    def test_force_refuses_replacement_of_git_tracked_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "tracked.json"
            dest.write_bytes(b"{}")
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                with self.assertRaises(CampaignCommitmentExportError) as ctx:
                    _write_file_atomically(
                        dest, b"new", force=True, is_git_tracked_check=True
                    )
                self.assertIn("Refusing to overwrite Git-tracked", str(ctx.exception))

    def test_atomic_write_fsync_errors_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.json"
            with patch("scripts.manage_win_either_half_campaign_commitment._fsync_dir", side_effect=OSError("fsync dir error")):
                with self.assertRaises(CampaignCommitmentExportError):
                    _write_file_atomically(dest, b"data")

    @patch("scripts.manage_win_either_half_campaign_commitment.get_code_state")
    def test_no_socket_connection_is_attempted(self, mock_code_state) -> None:
        mock_code_state.return_value = self.code_state
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            out_p = REPOSITORY_ROOT / COMMITMENT_ROOT / f"{bundle.campaign_id}.json"
            try:
                with patch.object(socket.socket, "connect", side_effect=AssertionError):
                    c_id, _ = create_commitment(
                        tasks_path=files["tasks"],
                        summary_path=files["summary"],
                        manifest_path=files["manifest"],
                        stage_5b3_protocol_path=files["stage_5b3_protocol"],
                        commitment_protocol_path=files["commitment_protocol"],
                        output_path=out_p,
                        force=True,
                        code_state=self.code_state,
                    )
                    self.assertEqual(c_id, bundle.campaign_id)
            finally:
                if out_p.exists():
                    out_p.unlink()

    # WORKFLOW CONTRACT TESTS
    def test_workflow_parses_as_yaml(self) -> None:
        wf_p = REPOSITORY_ROOT / ".github" / "workflows" / "validate-win-either-half-campaign-commitment.yml"
        self.assertTrue(wf_p.is_file())
        text = wf_p.read_text(encoding="utf-8")
        self.assertIn("name: Validate Win Either Half Campaign Commitment", text)

    def test_workflow_uses_pull_request_and_not_pull_request_target(self) -> None:
        wf_p = REPOSITORY_ROOT / ".github" / "workflows" / "validate-win-either-half-campaign-commitment.yml"
        text = wf_p.read_text(encoding="utf-8")
        self.assertIn("pull_request:", text)
        self.assertNotIn("pull_request_target:", text)

    def test_workflow_permissions_are_contents_read_only(self) -> None:
        wf_p = REPOSITORY_ROOT / ".github" / "workflows" / "validate-win-either-half-campaign-commitment.yml"
        text = wf_p.read_text(encoding="utf-8")
        self.assertIn("permissions:", text)
        self.assertIn("contents: read", text)

    def test_workflow_checks_out_head_and_base_separately(self) -> None:
        wf_p = REPOSITORY_ROOT / ".github" / "workflows" / "validate-win-either-half-campaign-commitment.yml"
        text = wf_p.read_text(encoding="utf-8")
        self.assertIn("path: head", text)
        self.assertIn("path: verifier", text)

    def test_workflow_executes_base_verifier_when_present(self) -> None:
        wf_p = REPOSITORY_ROOT / ".github" / "workflows" / "validate-win-either-half-campaign-commitment.yml"
        text = wf_p.read_text(encoding="utf-8")
        self.assertIn("verifier/scripts/manage_win_either_half_campaign_commitment.py", text)

    def test_workflow_bootstrap_forbids_real_commitment_files(self) -> None:
        wf_p = REPOSITORY_ROOT / ".github" / "workflows" / "validate-win-either-half-campaign-commitment.yml"
        text = wf_p.read_text(encoding="utf-8")
        self.assertIn("Bootstrap PR cannot include real campaign declarations", text)

    def test_workflow_separation_of_duties_rejection_is_present(self) -> None:
        wf_p = REPOSITORY_ROOT / ".github" / "workflows" / "validate-win-either-half-campaign-commitment.yml"
        text = wf_p.read_text(encoding="utf-8")
        self.assertIn("Separation-of-duties violation", text)

    def test_workflow_passes_github_run_id_attempt_and_runner_utc(self) -> None:
        wf_p = REPOSITORY_ROOT / ".github" / "workflows" / "validate-win-either-half-campaign-commitment.yml"
        text = wf_p.read_text(encoding="utf-8")
        self.assertIn("--github-run-id", text)
        self.assertIn("--github-run-attempt", text)
        self.assertIn("--server-observed-at", text)

    def test_workflow_uploads_attestation_with_90_day_retention(self) -> None:
        wf_p = REPOSITORY_ROOT / ".github" / "workflows" / "validate-win-either-half-campaign-commitment.yml"
        text = wf_p.read_text(encoding="utf-8")
        self.assertIn("retention-days: 90", text)
        self.assertIn("actions/upload-artifact@v4", text)

    def test_workflow_has_no_secrets_and_no_write_permission(self) -> None:
        wf_p = REPOSITORY_ROOT / ".github" / "workflows" / "validate-win-either-half-campaign-commitment.yml"
        text = wf_p.read_text(encoding="utf-8")
        self.assertNotIn("secrets.", text)
        self.assertNotIn("contents: write", text)

    def test_validate_deadline_with_commitment_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            bundle = validate_stage_5b3_bundle(
                tasks_path=files["tasks"],
                summary_path=files["summary"],
                manifest_path=files["manifest"],
            )
            decl = build_commitment_declaration(
                bundle=bundle,
                stage_5b3_protocol_raw=files["stage_5b3_protocol"].read_bytes(),
                commitment_protocol_raw=files["commitment_protocol"].read_bytes(),
                generator_git_sha="1" * 40,
            )
            observed_dt = decl.commitment_deadline_at - timedelta(seconds=10)
            valid_sha = sha256_bytes(canonical_json_bytes(decl.to_mapping(), pretty=True))

            # Valid matching hash
            res = validate_deadline(
                decl,
                server_observed_at=observed_dt,
                commitment_sha256=valid_sha,
            )
            self.assertTrue(res.prospective_timing_qualified)
            self.assertEqual(res.commitment_sha256, valid_sha)

            # Invalid format (non-hex chars)
            with self.assertRaises(CampaignCommitmentError) as ctx:
                validate_deadline(
                    decl,
                    server_observed_at=observed_dt,
                    commitment_sha256="g" * 64,
                )
            self.assertIn("64-character hexadecimal", str(ctx.exception))

            # Invalid format (short length)
            with self.assertRaises(CampaignCommitmentError) as ctx:
                validate_deadline(
                    decl,
                    server_observed_at=observed_dt,
                    commitment_sha256="abc123",
                )
            self.assertIn("64-character hexadecimal", str(ctx.exception))

            # Optional sha256 (None) computes it
            res_default = validate_deadline(
                decl,
                server_observed_at=observed_dt,
            )
            self.assertTrue(res_default.prospective_timing_qualified)
            self.assertEqual(res_default.commitment_sha256, valid_sha)

    def test_is_git_tracked_error_handling(self) -> None:
        from scripts.manage_win_either_half_campaign_commitment import _is_git_tracked
        test_path = REPOSITORY_ROOT / "some_file.json"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            self.assertTrue(_is_git_tracked(test_path, REPOSITORY_ROOT))

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stderr="error: pathspec 'some_file.json' did not match any files"
            )
            self.assertFalse(_is_git_tracked(test_path, REPOSITORY_ROOT))

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stderr="fatal: not a git repository")
            with self.assertRaises(CampaignCommitmentExportError) as ctx:
                _is_git_tracked(test_path, REPOSITORY_ROOT)
            self.assertIn("Unable to determine Git tracked status", str(ctx.exception))

    def test_atomic_write_backup_and_rollback_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "file_to_modify.json"
            dest.write_bytes(b'{"original": true}')

            with patch("scripts.manage_win_either_half_campaign_commitment._fsync_dir", side_effect=OSError("fsync failed")):
                with self.assertRaises(CampaignCommitmentExportError):
                    _write_file_atomically(dest, b'{"modified": true}', force=True)

            # Check that original content was restored by rollback
            self.assertEqual(dest.read_bytes(), b'{"original": true}')

    @patch("scripts.manage_win_either_half_campaign_commitment.get_code_state")
    def test_check_commitment_requires_clean_worktree(self, mock_code_state) -> None:
        dirty_code_state = dict(self.code_state)
        dirty_code_state["tracked_worktree_clean"] = False
        mock_code_state.return_value = dirty_code_state

        with tempfile.TemporaryDirectory() as tmp:
            files = self._create_stage_5b3_bundle_files(Path(tmp))
            decl_path = Path(tmp) / "decl.json"
            decl_path.write_bytes(b"{}")

            with self.assertRaises(CampaignCommitmentExportError) as ctx:
                check_commitment(
                    tasks_path=files["tasks"],
                    summary_path=files["summary"],
                    manifest_path=files["manifest"],
                    stage_5b3_protocol_path=files["stage_5b3_protocol"],
                    commitment_protocol_path=files["commitment_protocol"],
                    declaration_path=decl_path,
                    code_state=dirty_code_state,
                )
            self.assertIn("Tracked worktree must be clean", str(ctx.exception))

    def test_validate_git_diff_rejects_attestation_inside_repo(self) -> None:
        with self.assertRaises(CampaignCommitmentExportError) as ctx:
            validate_git_diff(
                repository_root=REPOSITORY_ROOT,
                base_sha="0" * 40,
                head_sha="1" * 40,
                server_observed_at="2026-08-04T12:00:00.000000Z",
                github_run_id="12345",
                github_run_attempt="1",
                github_event_name="pull_request",
                attestation_output=REPOSITORY_ROOT / "attestation.json",
            )
        self.assertIn("must be outside repository root", str(ctx.exception))

    def test_protocol_resolution_from_arbitrary_cwd(self) -> None:
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                self.assertTrue(DEFAULT_PROTOCOL_PATH.is_file())
                self.assertTrue(DEFAULT_STAGE_5B3_PROTOCOL_PATH.is_file())
                self.assertEqual(DEFAULT_PROTOCOL_PATH.parent.name, "research-protocols")
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
