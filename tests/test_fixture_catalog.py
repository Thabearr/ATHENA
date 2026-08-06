"""Tests for the offline ATHENA fixture-catalog compiler."""

from __future__ import annotations

import ast
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from domain.fixture_catalog import (
    FixtureCatalogError,
    FixtureProvenanceRecord,
    SAFETY_FLAGS,
    build_strict_catalog,
    canonical_json_bytes,
    compile_fixture_catalog,
    parse_utc_timestamp,
    serialize_utc,
    sha256_bytes,
)
from scripts import manage_fixture_catalog


class FixtureCatalogTests(unittest.TestCase):
    REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

    def setUp(self) -> None:
        self.as_of = datetime(2026, 8, 6, 0, 0, tzinfo=timezone.utc)
        self.as_of_text = "2026-08-06T00:00:00Z"
        self.minimum_lead_seconds = 86700
        self.clean_code_state = {
            "evidence_git_head_sha": "1" * 40,
            "tracked_worktree_clean": True,
        }
        self.dirty_code_state = {
            "evidence_git_head_sha": "1" * 40,
            "tracked_worktree_clean": False,
        }

    def _record_spec(
        self,
        *,
        source_fixture_identifier: str,
        kickoff: str,
        reviewed_at: str,
        evidence_file_path: str,
        evidence_bytes: bytes,
        home_team: str = "Home Team",
        away_team: str = "Away Team",
        competition: str = "Premier League",
        source_reference: str = "FotMob reviewed record",
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "source": "FOTMOB",
            "source_fixture_identifier": source_fixture_identifier,
            "home_team": home_team,
            "away_team": away_team,
            "competition": competition,
            "kickoff": kickoff,
            "source_reference": source_reference,
            "reviewed_at": reviewed_at,
            "evidence_file_path": evidence_file_path,
            "evidence_bytes": evidence_bytes,
        }

    def _write_input(self, root: Path, specs: list[dict[str, object]]) -> tuple[Path, Path, list[dict[str, object]]]:
        root.mkdir(parents=True, exist_ok=True)
        evidence_root = root / "evidence"
        evidence_root.mkdir(parents=True, exist_ok=True)
        records: list[dict[str, object]] = []
        for spec in specs:
            record = {
                key: value
                for key, value in spec.items()
                if key != "evidence_bytes"
            }
            if "evidence_bytes" in spec:
                evidence_path = evidence_root / Path(str(spec["evidence_file_path"]))
                evidence_path.parent.mkdir(parents=True, exist_ok=True)
                evidence_bytes = bytes(spec["evidence_bytes"])
                evidence_path.write_bytes(evidence_bytes)
                record["evidence_sha256"] = hashlib.sha256(evidence_bytes).hexdigest()
            records.append(record)
        input_path = root / "fixture-provenance.jsonl"
        raw = "\n".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False)
            for record in records
        )
        input_path.write_text(raw + "\n", encoding="utf-8")
        return input_path, evidence_root, records

    def _compile(self, root: Path, specs: list[dict[str, object]], *, minimum: int | None = None):
        input_path, evidence_root, _ = self._write_input(root, specs)
        return compile_fixture_catalog(
            input_path=input_path,
            evidence_root=evidence_root,
            as_of=self.as_of,
            minimum_lead_seconds=self.minimum_lead_seconds if minimum is None else minimum,
            code_state=self.clean_code_state,
        )

    def _valid_specs(self) -> list[dict[str, object]]:
        kickoff_1 = "2026-08-07T00:05:00Z"
        kickoff_2 = "2026-08-07T01:05:00Z"
        reviewed = "2026-08-05T23:30:00Z"
        return [
            self._record_spec(
                source_fixture_identifier="beta-2",
                kickoff=kickoff_2,
                reviewed_at=reviewed,
                evidence_file_path="evidence/beta.txt",
                evidence_bytes=b"beta evidence",
                home_team="Beta Home",
                away_team="Beta Away",
                competition="Competition B",
                source_reference="FotMob /fixtures/beta",
            ),
            self._record_spec(
                source_fixture_identifier="alpha-1",
                kickoff=kickoff_1,
                reviewed_at=reviewed,
                evidence_file_path="evidence/alpha.txt",
                evidence_bytes=b"alpha evidence",
                home_team="Alpha Home",
                away_team="Alpha Away",
                competition="Competition A",
                source_reference="FotMob /fixtures/alpha",
            ),
        ]

    def _same_kickoff_specs(self) -> list[dict[str, object]]:
        kickoff = "2026-08-07T00:05:00Z"
        reviewed = "2026-08-05T23:30:00Z"
        return [
            self._record_spec(
                source_fixture_identifier="zeta",
                kickoff=kickoff,
                reviewed_at=reviewed,
                evidence_file_path="evidence/zeta.txt",
                evidence_bytes=b"zeta evidence",
                home_team="Zeta Home",
                away_team="Zeta Away",
                competition="Competition Z",
                source_reference="FotMob /fixtures/zeta",
            ),
            self._record_spec(
                source_fixture_identifier="alpha",
                kickoff=kickoff,
                reviewed_at=reviewed,
                evidence_file_path="evidence/alpha.txt",
                evidence_bytes=b"alpha evidence",
                home_team="Alpha Home",
                away_team="Alpha Away",
                competition="Competition A",
                source_reference="FotMob /fixtures/alpha",
            ),
        ]

    def test_valid_catalog_generation_and_sorting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            specs = self._valid_specs()
            result = self._compile(root, specs)
            catalog = result.catalog
            manifest = result.manifest
            self.assertEqual(catalog["schema_version"], 1)
            self.assertEqual(len(catalog["fixtures"]), 2)
            self.assertEqual(
                [item["fixture_identifier"] for item in catalog["fixtures"]],
                ["FOTMOB:alpha-1", "FOTMOB:beta-2"],
            )
            self.assertEqual(manifest["fixture_count"], 2)
            self.assertEqual(
                [item["fixture_identifier"] for item in manifest["provenance_records"]],
                ["FOTMOB:alpha-1", "FOTMOB:beta-2"],
            )

    def test_valid_multiple_and_reordering_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            specs = self._valid_specs()
            result_one = self._compile(root, specs)
            result_two = self._compile(root, list(reversed(specs)))
            self.assertEqual(result_one.catalog_bytes, result_two.catalog_bytes)
            self.assertEqual(result_one.manifest_bytes, result_two.manifest_bytes)

    def test_utc_normalization_and_exact_lead_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            specs = [
                self._record_spec(
                    source_fixture_identifier="utc-normalized",
                    kickoff="2026-08-07T02:05:00+02:00",
                    reviewed_at="2026-08-05T23:00:00-01:00",
                    evidence_file_path="evidence/utc.txt",
                    evidence_bytes=b"utc evidence",
                    source_reference="FotMob /fixtures/utc",
                )
            ]
            result = self._compile(root, specs)
            self.assertEqual(result.catalog["fixtures"][0]["kickoff"], "2026-08-07T00:05:00.000000Z")
            self.assertEqual(result.manifest["as_of"], "2026-08-06T00:00:00.000000Z")
            self.assertEqual(result.records[0].reviewed_at, self.as_of)

    def test_invalid_input_contracts_fail_closed(self) -> None:
        valid = self._valid_specs()[0]
        cases: list[tuple[str, object]] = [
            ("insufficient lead", self._record_spec(
                source_fixture_identifier="lead-too-short",
                kickoff="2026-08-07T00:04:59Z",
                reviewed_at="2026-08-05T23:00:00Z",
                evidence_file_path="evidence/lead.txt",
                evidence_bytes=b"lead",
            )),
            ("naive kickoff", self._record_spec(
                source_fixture_identifier="naive-kickoff",
                kickoff="2026-08-07T00:05:00",
                reviewed_at="2026-08-05T23:00:00Z",
                evidence_file_path="evidence/naive1.txt",
                evidence_bytes=b"naive",
            )),
            ("naive reviewed_at", self._record_spec(
                source_fixture_identifier="naive-reviewed",
                kickoff="2026-08-07T00:05:00Z",
                reviewed_at="2026-08-05T23:00:00",
                evidence_file_path="evidence/naive2.txt",
                evidence_bytes=b"naive",
            )),
            ("reviewed after as_of", self._record_spec(
                source_fixture_identifier="late-review",
                kickoff="2026-08-07T00:05:00Z",
                reviewed_at="2026-08-06T00:00:01Z",
                evidence_file_path="evidence/late.txt",
                evidence_bytes=b"late",
            )),
            ("duplicate source identifier", [
                valid,
                dict(valid),
            ]),
            ("extra keys", self._record_spec(
                source_fixture_identifier="extra-keys",
                kickoff="2026-08-07T00:05:00Z",
                reviewed_at="2026-08-05T23:00:00Z",
                evidence_file_path="evidence/extra.txt",
                evidence_bytes=b"extra",
            )),
            ("missing keys", {
                "schema_version": 1,
                "source": "FOTMOB",
                "source_fixture_identifier": "missing-keys",
                "home_team": "Home",
                "away_team": "Away",
                "competition": "Competition",
                "kickoff": "2026-08-07T00:05:00Z",
                "reviewed_at": "2026-08-05T23:00:00Z",
                "evidence_file_path": "evidence/missing.txt",
            }),
            ("boolean schema version", self._record_spec(
                source_fixture_identifier="bool-schema",
                kickoff="2026-08-07T00:05:00Z",
                reviewed_at="2026-08-05T23:00:00Z",
                evidence_file_path="evidence/bool.txt",
                evidence_bytes=b"bool",
            )),
            ("blank line", "blank-line"),
            ("duplicate keys", "duplicate-keys"),
            ("nan", "nan"),
            ("infinity", "infinity"),
            ("empty input", ""),
            ("home equals away", self._record_spec(
                source_fixture_identifier="same-teams",
                kickoff="2026-08-07T00:05:00Z",
                reviewed_at="2026-08-05T23:00:00Z",
                evidence_file_path="evidence/same.txt",
                evidence_bytes=b"same",
                home_team="Same Team",
                away_team="Same Team",
            )),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_root = root / "evidence"
            evidence_root.mkdir()
            self._write_input(root, [valid])
            self.assertEqual(valid["source"], "FOTMOB")
            for label, case in cases:
                with self.subTest(label=label):
                    if label == "duplicate source identifier":
                        input_path, dup_evidence_root, _ = self._write_input(root / "dup", case)  # type: ignore[arg-type]
                        with self.assertRaises(FixtureCatalogError):
                            compile_fixture_catalog(
                                input_path=input_path,
                                evidence_root=dup_evidence_root,
                                as_of=self.as_of,
                                minimum_lead_seconds=self.minimum_lead_seconds,
                                code_state=self.clean_code_state,
                            )
                    elif label == "blank line":
                        input_path, evidence_root, records = self._write_input(root / "blank", [valid])
                        input_path.write_text(
                            json.dumps(records[0], ensure_ascii=False, sort_keys=True) + "\n\n",
                            encoding="utf-8",
                        )
                        with self.assertRaises(FixtureCatalogError):
                            compile_fixture_catalog(
                                input_path=input_path,
                                evidence_root=evidence_root,
                                as_of=self.as_of,
                                minimum_lead_seconds=self.minimum_lead_seconds,
                                code_state=self.clean_code_state,
                            )
                    elif label == "duplicate keys":
                        input_path = root / "duplicate.jsonl"
                        input_path.write_text(
                            '{"schema_version":1,"source":"FOTMOB","source":"FOTMOB","source_fixture_identifier":"dup","home_team":"H","away_team":"A","competition":"C","kickoff":"2026-08-07T00:05:00Z","source_reference":"ref","reviewed_at":"2026-08-05T23:00:00Z","evidence_file_path":"evidence/dup.txt","evidence_sha256":"'
                            + "0" * 64
                            + '"}\n',
                            encoding="utf-8",
                        )
                        with self.assertRaises(FixtureCatalogError):
                            compile_fixture_catalog(
                                input_path=input_path,
                                evidence_root=evidence_root,
                                as_of=self.as_of,
                                minimum_lead_seconds=self.minimum_lead_seconds,
                                code_state=self.clean_code_state,
                            )
                    elif label == "extra keys":
                        input_path, extra_evidence_root, _ = self._write_input(root / "extra", [case])  # type: ignore[list-item]
                        payload = json.loads(input_path.read_text(encoding="utf-8"))
                        payload["extra"] = True
                        input_path.write_text(
                            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
                            encoding="utf-8",
                        )
                        with self.assertRaises(FixtureCatalogError):
                            compile_fixture_catalog(
                                input_path=input_path,
                                evidence_root=extra_evidence_root,
                                as_of=self.as_of,
                                minimum_lead_seconds=self.minimum_lead_seconds,
                                code_state=self.clean_code_state,
                            )
                    elif label == "nan":
                        input_path = root / "nan.jsonl"
                        input_path.write_text(
                            '{"schema_version":1,"source":"FOTMOB","source_fixture_identifier":"nan","home_team":"H","away_team":"A","competition":"C","kickoff":NaN,"source_reference":"ref","reviewed_at":"2026-08-05T23:00:00Z","evidence_file_path":"evidence/nan.txt","evidence_sha256":"'
                            + "0" * 64
                            + '"}\n',
                            encoding="utf-8",
                        )
                        with self.assertRaises(FixtureCatalogError):
                            compile_fixture_catalog(
                                input_path=input_path,
                                evidence_root=evidence_root,
                                as_of=self.as_of,
                                minimum_lead_seconds=self.minimum_lead_seconds,
                                code_state=self.clean_code_state,
                            )
                    elif label == "infinity":
                        input_path = root / "inf.jsonl"
                        input_path.write_text(
                            '{"schema_version":1,"source":"FOTMOB","source_fixture_identifier":"inf","home_team":"H","away_team":"A","competition":"C","kickoff":Infinity,"source_reference":"ref","reviewed_at":"2026-08-05T23:00:00Z","evidence_file_path":"evidence/inf.txt","evidence_sha256":"'
                            + "0" * 64
                            + '"}\n',
                            encoding="utf-8",
                        )
                        with self.assertRaises(FixtureCatalogError):
                            compile_fixture_catalog(
                                input_path=input_path,
                                evidence_root=evidence_root,
                                as_of=self.as_of,
                                minimum_lead_seconds=self.minimum_lead_seconds,
                                code_state=self.clean_code_state,
                            )
                    elif label == "empty input":
                        input_path = root / "empty.jsonl"
                        input_path.write_text("", encoding="utf-8")
                        with self.assertRaises(FixtureCatalogError):
                            compile_fixture_catalog(
                                input_path=input_path,
                                evidence_root=evidence_root,
                                as_of=self.as_of,
                                minimum_lead_seconds=self.minimum_lead_seconds,
                                code_state=self.clean_code_state,
                            )
                    elif label == "boolean schema version":
                        input_path, local_evidence_root, records = self._write_input(root / "bool", [case])  # type: ignore[list-item]
                        record = dict(records[0])
                        record["schema_version"] = True
                        input_path.write_text(
                            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n",
                            encoding="utf-8",
                        )
                        with self.assertRaises(FixtureCatalogError):
                            compile_fixture_catalog(
                                input_path=input_path,
                                evidence_root=local_evidence_root,
                                as_of=self.as_of,
                                minimum_lead_seconds=self.minimum_lead_seconds,
                                code_state=self.clean_code_state,
                            )
                    elif isinstance(case, list):
                        input_path = root / "dup_source.jsonl"
                        input_path.write_text(
                            "\n".join(
                                json.dumps(item, ensure_ascii=False, sort_keys=True)
                                for item in case
                            )
                            + "\n",
                            encoding="utf-8",
                        )
                        with self.assertRaises(FixtureCatalogError):
                            compile_fixture_catalog(
                                input_path=input_path,
                                evidence_root=evidence_root,
                                as_of=self.as_of,
                                minimum_lead_seconds=self.minimum_lead_seconds,
                                code_state=self.clean_code_state,
                            )
                    else:
                        input_path, local_evidence_root, _ = self._write_input(root / label.replace(" ", "_"), [case])  # type: ignore[list-item]
                        with self.assertRaises(FixtureCatalogError):
                            compile_fixture_catalog(
                                input_path=input_path,
                                evidence_root=local_evidence_root,
                                as_of=self.as_of,
                                minimum_lead_seconds=self.minimum_lead_seconds,
                                code_state=self.clean_code_state,
                            )

    def test_duplicate_derived_identifier_fails(self) -> None:
        kickoff = self.as_of + timedelta(seconds=self.minimum_lead_seconds)
        one = FixtureProvenanceRecord(
            fixture_identifier="FOTMOB:opaque-1",
            source_fixture_identifier="opaque-1",
            home_team="Home 1",
            away_team="Away 1",
            competition="Competition",
            kickoff=kickoff,
            source_reference="ref 1",
            reviewed_at=self.as_of,
            evidence_file_path="evidence/one.txt",
            evidence_sha256="0" * 64,
        )
        two = FixtureProvenanceRecord(
            fixture_identifier="FOTMOB:opaque-1",
            source_fixture_identifier="opaque-2",
            home_team="Home 2",
            away_team="Away 2",
            competition="Competition",
            kickoff=kickoff + timedelta(seconds=1),
            source_reference="ref 2",
            reviewed_at=self.as_of,
            evidence_file_path="evidence/two.txt",
            evidence_sha256="1" * 64,
        )
        with self.assertRaises(FixtureCatalogError):
            build_strict_catalog([one, two])

    def test_evidence_validation_and_path_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._record_spec(
                source_fixture_identifier="evidence-rule",
                kickoff="2026-08-07T00:05:00Z",
                reviewed_at="2026-08-05T23:00:00Z",
                evidence_file_path="evidence/rule.txt",
                evidence_bytes=b"rule",
            )
            input_path, evidence_root, _ = self._write_input(root, [base])
            bad = json.loads(input_path.read_text(encoding="utf-8"))
            bad["evidence_sha256"] = "f" * 64
            input_path.write_text(
                json.dumps(bad, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(FixtureCatalogError):
                compile_fixture_catalog(
                    input_path=input_path,
                    evidence_root=evidence_root,
                    as_of=self.as_of,
                    minimum_lead_seconds=self.minimum_lead_seconds,
                    code_state=self.clean_code_state,
                )
            missing = root / "missing.jsonl"
            missing_payload = {
                key: value
                for key, value in base.items()
                if key != "evidence_bytes"
            }
            missing_payload["evidence_sha256"] = "0" * 64
            missing.write_text(
                json.dumps(missing_payload, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(FixtureCatalogError):
                compile_fixture_catalog(
                    input_path=missing,
                    evidence_root=evidence_root,
                    as_of=self.as_of,
                    minimum_lead_seconds=self.minimum_lead_seconds,
                    code_state=self.clean_code_state,
                )
            absolute = dict(base)
            absolute.pop("evidence_bytes", None)
            absolute["evidence_file_path"] = str((evidence_root / "rule.txt").resolve())
            input_path.write_text(
                json.dumps(absolute, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(FixtureCatalogError):
                compile_fixture_catalog(
                    input_path=input_path,
                    evidence_root=evidence_root,
                    as_of=self.as_of,
                    minimum_lead_seconds=self.minimum_lead_seconds,
                    code_state=self.clean_code_state,
                )
            traversal = dict(base)
            traversal.pop("evidence_bytes", None)
            traversal["evidence_file_path"] = "../escape.txt"
            input_path.write_text(
                json.dumps(traversal, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(FixtureCatalogError):
                compile_fixture_catalog(
                    input_path=input_path,
                    evidence_root=evidence_root,
                    as_of=self.as_of,
                    minimum_lead_seconds=self.minimum_lead_seconds,
                    code_state=self.clean_code_state,
                )
            if hasattr(os, "symlink"):
                symlink_root = root / "symlink-root"
                target_root = root / "real-root"
                target_root.mkdir()
                try:
                    os.symlink(target_root, symlink_root, target_is_directory=True)
                except OSError as error:
                    self.skipTest(f"symlinks unavailable: {error}")
                symlink_file = target_root / "evidence.txt"
                symlink_target = target_root / "target.txt"
                symlink_target.write_bytes(b"target")
                os.symlink(symlink_target, symlink_file)
                symlink_input = root / "symlink.jsonl"
                record = self._record_spec(
                    source_fixture_identifier="symlink",
                    kickoff="2026-08-07T00:05:00Z",
                    reviewed_at="2026-08-05T23:00:00Z",
                    evidence_file_path="evidence.txt",
                    evidence_bytes=b"target",
                )
                payload = dict(record)
                payload.pop("evidence_bytes", None)
                payload["evidence_file_path"] = "evidence.txt"
                payload["evidence_sha256"] = hashlib.sha256(b"target").hexdigest()
                symlink_input.write_text(
                    json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                with self.assertRaises(FixtureCatalogError):
                    compile_fixture_catalog(
                        input_path=symlink_input,
                        evidence_root=symlink_root,
                        as_of=self.as_of,
                        minimum_lead_seconds=self.minimum_lead_seconds,
                        code_state=self.clean_code_state,
                    )
            else:
                self.skipTest("symlink creation not supported on this platform")

    def test_symlinked_evidence_file_and_parent_component_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            if not hasattr(os, "symlink"):
                self.skipTest("symlinks unavailable on this platform")
            real_root = root / "real"
            real_root.mkdir()
            evidence_file = real_root / "reviewed.txt"
            evidence_file.write_bytes(b"reviewed")
            evidence_sha = hashlib.sha256(b"reviewed").hexdigest()
            input_path = root / "fixture-provenance.jsonl"
            record = self._record_spec(
                source_fixture_identifier="symlink-file",
                kickoff="2026-08-07T00:05:00Z",
                reviewed_at="2026-08-05T23:00:00Z",
                evidence_file_path="reviewed-link.txt",
                evidence_bytes=b"reviewed",
            )
            payload = {
                key: value for key, value in record.items() if key != "evidence_bytes"
            }
            payload["evidence_sha256"] = evidence_sha
            input_path.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.symlink(evidence_file, real_root / "reviewed-link.txt")
            with self.assertRaises(FixtureCatalogError):
                compile_fixture_catalog(
                    input_path=input_path,
                    evidence_root=real_root,
                    as_of=self.as_of,
                    minimum_lead_seconds=self.minimum_lead_seconds,
                    code_state=self.clean_code_state,
                )

            symlink_parent = root / "parent-link"
            os.symlink(real_root, symlink_parent, target_is_directory=True)
            with self.assertRaises(FixtureCatalogError):
                compile_fixture_catalog(
                    input_path=input_path,
                    evidence_root=symlink_parent,
                    as_of=self.as_of,
                    minimum_lead_seconds=self.minimum_lead_seconds,
                    code_state=self.clean_code_state,
                )

    def test_git_status_checks_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            tracked = repo / "tracked.txt"
            tracked.write_text("tracked", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
            self.assertTrue(manage_fixture_catalog._is_git_tracked(tracked, repo))
            self.assertFalse(manage_fixture_catalog._is_git_tracked(repo / "untracked.txt", repo))
            with self.assertRaises(FixtureCatalogError):
                manage_fixture_catalog._is_git_tracked(Path(tmp) / "outside.txt", repo)
            with patch.object(
                manage_fixture_catalog,
                "_run_git_process",
                side_effect=FixtureCatalogError("git failed"),
            ):
                with self.assertRaises(FixtureCatalogError):
                    manage_fixture_catalog._is_git_tracked(tracked, repo)
            with patch.object(
                manage_fixture_catalog.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(
                    args=["git"], returncode=1, stdout=b"", stderr=b"fatal"
                ),
            ):
                with self.assertRaises(FixtureCatalogError):
                    manage_fixture_catalog._is_git_tracked(tracked, repo)
            with patch.object(
                manage_fixture_catalog,
                "_run_git_process",
                return_value=subprocess.CompletedProcess(
                    args=["git"], returncode=0, stdout=b"\xff\x00", stderr=b""
                ),
            ):
                with self.assertRaises(FixtureCatalogError):
                    manage_fixture_catalog._is_git_tracked(tracked, repo)
            with patch.object(
                manage_fixture_catalog,
                "_run_git_process",
                return_value=subprocess.CompletedProcess(
                    args=["git"], returncode=0, stdout=b"tracked\x00extra\x00", stderr=b""
                ),
            ):
                with self.assertRaises(FixtureCatalogError):
                    manage_fixture_catalog._is_git_tracked(tracked, repo)

    def test_windows_directory_fsync_checks_are_fail_closed(self) -> None:
        class FakeKernel32:
            def __init__(self, create_value=1, flush_value=True, close_value=True):
                self.create_value = create_value
                self.flush_value = flush_value
                self.close_value = close_value

            def CreateFileW(self, *args, **kwargs):
                return self.create_value

            def FlushFileBuffers(self, handle):
                return self.flush_value

            def CloseHandle(self, handle):
                return self.close_value

        original_error = manage_fixture_catalog.ctypes.get_last_error
        try:
            manage_fixture_catalog.ctypes.get_last_error = lambda: 123  # type: ignore[assignment]
            with patch.object(
                manage_fixture_catalog.ctypes,
                "windll",
                type("Windll", (), {"kernel32": FakeKernel32(create_value=0)})(),
            ):
                with self.assertRaises(FixtureCatalogError):
                    manage_fixture_catalog._win_fsync_directory(Path("."))
            with patch.object(
                manage_fixture_catalog.ctypes,
                "windll",
                type("Windll", (), {"kernel32": FakeKernel32(flush_value=False)})(),
            ):
                with self.assertRaises(FixtureCatalogError):
                    manage_fixture_catalog._win_fsync_directory(Path("."))
            with patch.object(
                manage_fixture_catalog.ctypes,
                "windll",
                type("Windll", (), {"kernel32": FakeKernel32(close_value=False)})(),
            ):
                with self.assertRaises(FixtureCatalogError):
                    manage_fixture_catalog._win_fsync_directory(Path("."))
            with patch.object(
                manage_fixture_catalog.ctypes,
                "windll",
                type("Windll", (), {"kernel32": FakeKernel32()})(),
            ):
                manage_fixture_catalog._win_fsync_directory(Path("."))
        finally:
            manage_fixture_catalog.ctypes.get_last_error = original_error  # type: ignore[assignment]

    def test_transaction_preparation_and_same_path_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self._compile(root, self._valid_specs())
            catalog_output = root / "catalog.json"
            manifest_output = root / "manifest.json"
            original_prepare = manage_fixture_catalog._prepare_output

            def fail_second(destination, content, *, force):
                if destination.name == manifest_output.name:
                    raise FixtureCatalogError("manifest prep failed")
                return original_prepare(destination, content, force=force)

            with patch.object(manage_fixture_catalog, "_prepare_output", side_effect=fail_second):
                with self.assertRaises(FixtureCatalogError):
                    manage_fixture_catalog._write_outputs_atomically(
                        catalog_output=catalog_output,
                        manifest_output=manifest_output,
                        catalog_bytes=result.catalog_bytes,
                        manifest_bytes=result.manifest_bytes,
                        force=True,
                    )
            self.assertFalse(any(p.name.startswith(".fixture-catalog-") for p in root.iterdir()))
            with self.assertRaises(FixtureCatalogError):
                manage_fixture_catalog._write_outputs_atomically(
                    catalog_output=catalog_output,
                    manifest_output=catalog_output,
                    catalog_bytes=result.catalog_bytes,
                    manifest_bytes=result.manifest_bytes,
                    force=True,
                )
            alias = root / "alias"
            alias.mkdir()
            with self.assertRaises(FixtureCatalogError):
                manage_fixture_catalog._write_outputs_atomically(
                    catalog_output=alias / ".." / "catalog.json",
                    manifest_output=alias / ".." / "." / "catalog.json",
                    catalog_bytes=result.catalog_bytes,
                    manifest_bytes=result.manifest_bytes,
                    force=True,
                )

    def test_transaction_finalization_and_rollback_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self._compile(root, self._valid_specs())
            catalog_output = root / "catalog.json"
            manifest_output = root / "manifest.json"
            catalog_output.write_text("original-catalog", encoding="utf-8")
            catalog_mode = catalog_output.stat().st_mode
            original_manifest_exists = manifest_output.exists()
            original_commit = manage_fixture_catalog._commit_prepared

            def fail_cleanup(prepared):
                if prepared.destination.name == manifest_output.name:
                    raise FixtureCatalogError("staged cleanup failed")
                return None

            with patch.object(
                manage_fixture_catalog,
                "_cleanup_staged_artifacts",
                side_effect=fail_cleanup,
            ):
                with self.assertRaises(FixtureCatalogError):
                    manage_fixture_catalog._write_outputs_atomically(
                        catalog_output=catalog_output,
                        manifest_output=manifest_output,
                        catalog_bytes=result.catalog_bytes,
                        manifest_bytes=result.manifest_bytes,
                        force=True,
                    )
            self.assertEqual(catalog_output.read_text(encoding="utf-8"), "original-catalog")
            self.assertEqual(catalog_output.stat().st_mode & 0o777, catalog_mode & 0o777)
            self.assertEqual(manifest_output.exists(), original_manifest_exists)

            def fail_restore(prepared):
                raise FixtureCatalogError("restore failed")

            with patch.object(
                manage_fixture_catalog,
                "_cleanup_staged_artifacts",
                side_effect=FixtureCatalogError("cleanup failed"),
            ), patch.object(
                manage_fixture_catalog,
                "_rollback_prepared_outputs",
                side_effect=lambda prepared: ["rollback failed"],
            ):
                with self.assertRaises(FixtureCatalogError):
                    manage_fixture_catalog._write_outputs_atomically(
                        catalog_output=catalog_output,
                        manifest_output=manifest_output,
                        catalog_bytes=result.catalog_bytes,
                        manifest_bytes=result.manifest_bytes,
                        force=True,
                    )

    def test_catalog_and_manifest_shape_and_check_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            specs = self._valid_specs()
            result = self._compile(root, specs)
            self.assertEqual(set(result.catalog), {"schema_version", "fixtures"})
            for fixture in result.catalog["fixtures"]:
                self.assertEqual(set(fixture), {"fixture_identifier", "kickoff"})
            self.assertIn("provenance_records", result.manifest)
            self.assertEqual(
                [item["fixture_identifier"] for item in result.catalog["fixtures"]],
                [item["fixture_identifier"] for item in result.manifest["provenance_records"]],
            )

            catalog_output = root / "future-fixtures.json"
            manifest_output = root / "fixture-catalog-manifest-v1.json"
            catalog_output.write_bytes(result.catalog_bytes)
            manifest_output.write_bytes(result.manifest_bytes)
            checked = manage_fixture_catalog.run(
                input_path=root / "fixture-provenance.jsonl",
                evidence_root=root / "evidence",
                as_of=self.as_of_text,
                minimum_lead_seconds=self.minimum_lead_seconds,
                check_catalog=catalog_output,
                check_manifest=manifest_output,
                code_state=self.clean_code_state,
            )
            self.assertEqual(checked.catalog_bytes, result.catalog_bytes)
            self.assertEqual(checked.manifest_bytes, result.manifest_bytes)

            broken_catalog = root / "broken-catalog.json"
            broken_catalog.write_bytes(result.catalog_bytes + b" ")
            with self.assertRaises(FixtureCatalogError):
                manage_fixture_catalog.run(
                    input_path=root / "fixture-provenance.jsonl",
                    evidence_root=root / "evidence",
                    as_of=self.as_of_text,
                    minimum_lead_seconds=self.minimum_lead_seconds,
                    check_catalog=broken_catalog,
                    check_manifest=manifest_output,
                    code_state=self.clean_code_state,
                )
            broken_manifest = root / "broken-manifest.json"
            broken_manifest.write_bytes(result.manifest_bytes + b" ")
            with self.assertRaises(FixtureCatalogError):
                manage_fixture_catalog.run(
                    input_path=root / "fixture-provenance.jsonl",
                    evidence_root=root / "evidence",
                    as_of=self.as_of_text,
                    minimum_lead_seconds=self.minimum_lead_seconds,
                    check_catalog=catalog_output,
                    check_manifest=broken_manifest,
                    code_state=self.clean_code_state,
                )

    def test_output_control_force_and_track_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            (repo / ".gitignore").write_text(".cache/athena-research/\n", encoding="utf-8")
            subprocess.run(["git", "add", ".gitignore"], cwd=repo, check=True, capture_output=True)
            input_root = Path(tmp) / "input"
            input_root.mkdir()
            result = self._compile(input_root, self._valid_specs())
            output_catalog = repo / ".cache" / "athena-research" / "future-fixtures.json"
            output_manifest = repo / ".cache" / "athena-research" / "fixture-catalog-manifest-v1.json"
            output_catalog.parent.mkdir(parents=True, exist_ok=True)
            output_catalog.write_text("stale", encoding="utf-8")
            output_manifest.write_text("stale", encoding="utf-8")
            with patch.object(manage_fixture_catalog, "REPOSITORY_ROOT", repo), patch.object(
                manage_fixture_catalog,
                "ALLOWED_REPOSITORY_OUTPUT_ROOT",
                repo / ".cache" / "athena-research",
            ):
                with self.assertRaises(FixtureCatalogError):
                    manage_fixture_catalog.run(
                        input_path=input_root / "fixture-provenance.jsonl",
                        evidence_root=input_root / "evidence",
                        as_of=self.as_of_text,
                        minimum_lead_seconds=self.minimum_lead_seconds,
                        catalog_output=output_catalog,
                        manifest_output=output_manifest,
                        code_state=self.clean_code_state,
                    )
                # replace ignored outputs with --force
                manage_fixture_catalog.run(
                    input_path=input_root / "fixture-provenance.jsonl",
                    evidence_root=input_root / "evidence",
                    as_of=self.as_of_text,
                    minimum_lead_seconds=self.minimum_lead_seconds,
                    catalog_output=output_catalog,
                    manifest_output=output_manifest,
                    force=True,
                    code_state=self.clean_code_state,
                )
                self.assertEqual(output_catalog.read_bytes(), result.catalog_bytes)
                self.assertEqual(output_manifest.read_bytes(), result.manifest_bytes)
                subprocess.run(
                    ["git", "add", "-f", ".cache/athena-research/future-fixtures.json"],
                    cwd=repo,
                    check=True,
                    capture_output=True,
                )
                with self.assertRaises(FixtureCatalogError):
                    manage_fixture_catalog.run(
                        input_path=input_root / "fixture-provenance.jsonl",
                        evidence_root=input_root / "evidence",
                        as_of=self.as_of_text,
                        minimum_lead_seconds=self.minimum_lead_seconds,
                        catalog_output=output_catalog,
                        manifest_output=output_manifest,
                        force=True,
                        code_state=self.clean_code_state,
                    )

    def test_transaction_failure_rolls_back_and_cleans_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self._compile(root, self._valid_specs())
            catalog_output = root / "catalog.json"
            manifest_output = root / "manifest.json"
            catalog_output.write_text("original-catalog", encoding="utf-8")
            manifest_output.write_text("original-manifest", encoding="utf-8")
            original_commit = manage_fixture_catalog._commit_prepared

            def fail_on_second(prepared):
                if prepared.destination.name == manifest_output.name:
                    raise RuntimeError("simulated commit failure")
                return original_commit(prepared)

            with patch.object(manage_fixture_catalog, "_commit_prepared", side_effect=fail_on_second):
                with self.assertRaises(FixtureCatalogError):
                    manage_fixture_catalog._write_outputs_atomically(
                        catalog_output=catalog_output,
                        manifest_output=manifest_output,
                        catalog_bytes=result.catalog_bytes,
                        manifest_bytes=result.manifest_bytes,
                        force=True,
                    )
            self.assertEqual(catalog_output.read_text(encoding="utf-8"), "original-catalog")
            self.assertEqual(manifest_output.read_text(encoding="utf-8"), "original-manifest")
            leftovers = [
                entry.name
                for entry in root.iterdir()
                if entry.name.startswith(".fixture-catalog-")
            ]
            self.assertEqual(leftovers, [])

    def test_repo_dirty_generation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path, evidence_root, _ = self._write_input(root, self._valid_specs())
            with self.assertRaises(FixtureCatalogError):
                compile_fixture_catalog(
                    input_path=input_path,
                    evidence_root=evidence_root,
                    as_of=self.as_of,
                    minimum_lead_seconds=self.minimum_lead_seconds,
                    code_state=self.dirty_code_state,
                )

    def test_no_network_or_browser_dependencies_and_safety_flags(self) -> None:
        blocked = {"requests", "urllib3", "selenium", "playwright", "browser", "mechanize"}
        modules = [
            self.REPOSITORY_ROOT / "domain" / "fixture_catalog.py",
            self.REPOSITORY_ROOT / "scripts" / "manage_fixture_catalog.py",
        ]
        imported: set[str] = set()
        for path in modules:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
        self.assertTrue(blocked.isdisjoint(imported))
        self.assertTrue(all(flag is False for flag in SAFETY_FLAGS.values()))
        self.assertTrue(all(flag is False for flag in manage_fixture_catalog.GENERATED_SAFETY_CONTRACT.values()))

    def test_forbidden_betting_fields_are_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self._compile(root, self._valid_specs())
            forbidden = {
                "decimal_odds",
                "expected_value",
                "edge",
                "edge_pp",
                "kelly",
                "kelly_stake",
                "stake",
                "profit",
                "profitability",
                "bet",
                "bet_decision",
                "bookmaker_odds",
            }
            catalog_text = json.dumps(result.catalog)
            keys: set[str] = set()
            catalog_obj = result.catalog

            def collect_keys(value):
                if isinstance(value, dict):
                    for key, child in value.items():
                        keys.add(key)
                        collect_keys(child)
                elif isinstance(value, list):
                    for child in value:
                        collect_keys(child)

            collect_keys(catalog_obj)
            for field in forbidden:
                self.assertNotIn(field, keys)
            self.assertNotIn("source_reference", catalog_text)
            self.assertNotIn("home_team", catalog_text)
            self.assertNotIn("away_team", catalog_text)
            self.assertNotIn("competition", catalog_text)
            self.assertTrue(all(flag is False for flag in result.manifest["safety"].values()))


__all__ = ["FixtureCatalogTests"]
