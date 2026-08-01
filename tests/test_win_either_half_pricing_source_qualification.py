from datetime import datetime, timedelta, timezone
import hashlib
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
from domain.win_either_half_pricing_source_qualification import (
    DEFAULT_DECISION_PROTOCOL,
    EXECUTION_REQUIRED_GATES,
    HISTORICAL_REQUIRED_GATES,
    LIVE_REQUIRED_GATES,
    MARKET_SEMANTICS,
    PERMITTED_MARKETS,
    PROSPECTIVE_REQUIRED_GATES,
    FixtureMappingStatus,
    FixtureReference,
    GateEvidence,
    GateId,
    GateStatus,
    QualificationStatus,
    SourceRole,
    evaluate_fixture_mapping,
    qualify_mandatory_gates,
    qualify_prospective_replay,
    validate_market_semantics,
    validate_snapshot_identity,
)
from scripts.qualify_win_either_half_pricing_source import (
    CONSUMED_HOLDOUT_GOVERNANCE,
    DEFAULT_PROTOCOL_PATH,
    QualificationExportError,
    _canonical_json_bytes,
    main,
    qualify_candidate,
    validate_evidence_files,
    write_report,
)


class WinEitherHalfPricingSourceQualificationTests(unittest.TestCase):
    REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
    CHECKED_AT = "2026-08-01T12:00:00Z"

    def setUp(self):
        self.checked_at = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        self.protocol = json.loads(DEFAULT_PROTOCOL_PATH.read_text(encoding="utf-8"))
        self.original_statuses = {
            market: status.status for market, status in MODEL_STATUS_REGISTRY.items()
        }

    def _gate(self, status=GateStatus.PASS, reason="reviewed evidence"):
        return GateEvidence(status, reason, "review.txt", self.checked_at)

    def _gates(self, default=GateStatus.PASS):
        return {gate: self._gate(default) for gate in GateId}

    def _semantics(self, market, **changes):
        expected = MARKET_SEMANTICS[market]
        row = {
            "market_id": market.value,
            "market_description": expected["market_description"],
            "subject": expected["subject"],
            "yes_settlement": expected["yes_settlement"],
            "no_settlement": expected["no_settlement"],
            "line": None,
            "outcome_identifiers": ["YES", "NO"],
            "evidence_reference": "review.txt",
            "checked_at": self.CHECKED_AT,
        }
        row.update(changes)
        return row

    def _candidate(self, evidence_file):
        gate_evidence = {
            gate.value: self._gate(
                GateStatus.NOT_APPLICABLE
                if gate is GateId.BOOKING_CODE_SUPPORT
                else GateStatus.PASS
            ).to_dict()
            for gate in GateId
        }
        content = evidence_file.read_bytes()
        return {
            "schema_version": 1,
            "provider_identifier": "reviewed-provider",
            "provider_name": "Reviewed Provider",
            "candidate_roles": [role.value for role in SourceRole],
            "evidence_checked_at": self.CHECKED_AT,
            "market_semantics_evidence": {
                "markets": [
                    self._semantics(MarketId.HOME_WIN_EITHER_HALF),
                    self._semantics(MarketId.AWAY_WIN_EITHER_HALF),
                ]
            },
            "outcome_evidence": {"identifiers": ["YES", "NO"]},
            "quote_field_evidence": {
                "price_type": "RAW_DECIMAL_BOOKMAKER_ODDS",
                "bookmaker_identifier": True,
                "bookmaker_name_or_source": True,
                "provider_event_identifier": True,
                "provider_market_identifier": True,
                "provider_selection_identifier": True,
                "fixture_kickoff_or_stable_reference": True,
            },
            "timestamp_evidence": {
                "timestamp_source": "PROVIDER_QUOTE_OR_UPDATE"
            },
            "snapshot_evidence": {"yes_no_common_snapshot": True},
            "historical_retention_evidence": {},
            "live_pricing_evidence": {},
            "fixture_mapping_evidence": {},
            "export_reproducibility_evidence": {},
            "licensing_and_retention_evidence": {},
            "execution_workflow_evidence": {},
            "booking_code_evidence": {"provided": False},
            "gate_evidence": gate_evidence,
            "limitations": ["Research protocol only"],
            "evidence_files": [
                {
                    "path": evidence_file.name,
                    "byte_size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            ],
        }

    def test_exact_market_semantics_and_yes_no_identifiers_pass(self):
        for market in PERMITTED_MARKETS:
            with self.subTest(market=market):
                result = validate_market_semantics(self._semantics(market))
                self.assertEqual(result.status, GateStatus.PASS)

    def test_market_substitutions_and_fuzzy_descriptions_fail(self):
        substitutions = (
            "Home Team First Half Winner",
            "Home Team Second Half Winner",
            "Home Team to Win Both Halves",
            "Full Time Result Home",
            "Double Chance 1X",
            "Bet Builder Home Wins a Half",
        )
        for description in substitutions:
            with self.subTest(description=description):
                result = validate_market_semantics(
                    self._semantics(
                        MarketId.HOME_WIN_EITHER_HALF,
                        market_description=description,
                    )
                )
                self.assertEqual(result.status, GateStatus.FAIL)
                self.assertEqual(result.reason, "MARKET_SEMANTICS_MISMATCH")
        missing = self._semantics(MarketId.HOME_WIN_EITHER_HALF)
        missing.pop("market_description")
        self.assertEqual(validate_market_semantics(missing).status, GateStatus.UNKNOWN)

    def test_exact_outcomes_and_quote_evidence_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("review", encoding="utf-8")
            cases = (
                ("outcome_evidence", {"identifiers": ["YES", "HOME"]}, GateId.EXACT_YES_NO_STRUCTURE),
                ("quote_field_evidence", {"price_type": "BEST_PRICE", "bookmaker_identifier": True, "bookmaker_name_or_source": True, "provider_event_identifier": True, "provider_market_identifier": True, "provider_selection_identifier": True, "fixture_kickoff_or_stable_reference": True}, GateId.RAW_DECIMAL_ODDS),
                ("quote_field_evidence", {"price_type": "CONSENSUS_PROBABILITY", "bookmaker_identifier": True, "bookmaker_name_or_source": True, "provider_event_identifier": True, "provider_market_identifier": True, "provider_selection_identifier": True, "fixture_kickoff_or_stable_reference": True}, GateId.RAW_DECIMAL_ODDS),
                ("quote_field_evidence", {"price_type": "MODEL_PROBABILITY", "bookmaker_identifier": True, "bookmaker_name_or_source": True, "provider_event_identifier": True, "provider_market_identifier": True, "provider_selection_identifier": True, "fixture_kickoff_or_stable_reference": True}, GateId.RAW_DECIMAL_ODDS),
                ("quote_field_evidence", {"price_type": "RAW_DECIMAL_BOOKMAKER_ODDS", "bookmaker_identifier": False, "bookmaker_name_or_source": False, "provider_event_identifier": True, "provider_market_identifier": True, "provider_selection_identifier": True, "fixture_kickoff_or_stable_reference": True}, GateId.BOOKMAKER_PROVENANCE),
                ("timestamp_evidence", {"timestamp_source": "DOWNLOAD_TIME"}, GateId.QUOTE_OBSERVED_AT),
                ("timestamp_evidence", {}, GateId.QUOTE_OBSERVED_AT),
                ("snapshot_evidence", {"yes_no_common_snapshot": False}, GateId.SAME_BOOKMAKER_SNAPSHOT),
            )
            for section, changed, gate in cases:
                with self.subTest(section=section, changed=changed):
                    candidate = self._candidate(evidence)
                    candidate[section] = changed
                    report = qualify_candidate(
                        candidate,
                        evidence_root=root,
                        protocol=self.protocol,
                        code_state={"evidence_git_head_sha": "1" * 40, "tracked_worktree_clean": True},
                        input_identity={"byte_size": 1, "sha256": "a" * 64},
                    )
                    self.assertEqual(report["gate_results"][gate.value]["status"], "FAIL")

    def test_native_and_derived_snapshot_identity_and_timestamp_safety(self):
        common = dict(
            provider_identifier="provider",
            fixture_identifier="fixture",
            market_id=MarketId.HOME_WIN_EITHER_HALF,
            bookmaker_identifier="book",
            yes_observed_at=self.CHECKED_AT,
            no_observed_at=self.CHECKED_AT,
        )
        native = validate_snapshot_identity(**common, native_snapshot_id="native-1")
        self.assertEqual((native.status, native.derived), (GateStatus.PASS, False))
        derived = validate_snapshot_identity(**common)
        self.assertTrue(derived.snapshot_identifier.startswith("derived-sha256:"))
        self.assertTrue(derived.derived)
        mixed = validate_snapshot_identity(
            **{**common, "no_observed_at": "2026-08-01T12:00:01Z"}
        )
        self.assertEqual((mixed.status, mixed.reason), (GateStatus.FAIL, "MIXED_OBSERVED_AT"))

    def test_fixture_mapping_exact_reversed_conflict_ambiguous_and_fuzzy(self):
        kickoff = datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)
        canonical = FixtureReference("athena-1", "E0", "2025-26", kickoff, "home-1", "Home", "away-1", "Away", False, "SCHEDULED")
        exact = FixtureReference("provider-1", "E0", "2025-26", kickoff + timedelta(seconds=300), "home-1", "Home", "away-1", "Away", False, "SCHEDULED")
        self.assertEqual(evaluate_fixture_mapping(exact, canonical), FixtureMappingStatus.EXACT)
        reversed_fixture = FixtureReference("provider-1", "E0", "2025-26", kickoff, "away-1", "Away", "home-1", "Home", False, "SCHEDULED")
        self.assertEqual(evaluate_fixture_mapping(reversed_fixture, canonical), FixtureMappingStatus.CONFLICT)
        conflict = FixtureReference(**{**exact.__dict__, "kickoff": kickoff + timedelta(seconds=301)})
        self.assertEqual(evaluate_fixture_mapping(conflict, canonical), FixtureMappingStatus.CONFLICT)
        competition_conflict = FixtureReference(**{**exact.__dict__, "competition_identifier": "E1"})
        self.assertEqual(evaluate_fixture_mapping(competition_conflict, canonical), FixtureMappingStatus.CONFLICT)
        ambiguous = FixtureReference(**{**exact.__dict__, "home_participant_identifier": "unknown"})
        self.assertEqual(evaluate_fixture_mapping(ambiguous, canonical), FixtureMappingStatus.AMBIGUOUS)
        self.assertEqual(evaluate_fixture_mapping(exact, canonical, fuzzy_only=True), FixtureMappingStatus.AMBIGUOUS)

    def test_roles_are_independent_and_unknown_or_failure_never_passes(self):
        all_pass = self._gates()
        self.assertEqual(
            qualify_mandatory_gates(SourceRole.HISTORICAL_RESEARCH_SOURCE, all_pass),
            QualificationStatus.QUALIFIED_FOR_HISTORICAL_RESEARCH,
        )
        execution_only = dict(all_pass)
        execution_only[GateId.HISTORICAL_RETENTION] = self._gate(GateStatus.FAIL)
        execution_only[GateId.CURRENT_MARKET_AVAILABILITY] = self._gate(GateStatus.FAIL)
        self.assertEqual(qualify_mandatory_gates(SourceRole.HISTORICAL_RESEARCH_SOURCE, execution_only), QualificationStatus.DISQUALIFIED)
        self.assertEqual(qualify_mandatory_gates(SourceRole.EXECUTION_BOOKMAKER, execution_only), QualificationStatus.QUALIFIED_AS_EXECUTION_BOOKMAKER)
        history_only = dict(all_pass)
        history_only[GateId.DETERMINISTIC_BETSLIP] = self._gate(GateStatus.FAIL)
        self.assertEqual(qualify_mandatory_gates(SourceRole.HISTORICAL_RESEARCH_SOURCE, history_only), QualificationStatus.QUALIFIED_FOR_HISTORICAL_RESEARCH)
        self.assertEqual(qualify_mandatory_gates(SourceRole.EXECUTION_BOOKMAKER, history_only), QualificationStatus.DISQUALIFIED)
        unknown = {gate: self._gate(GateStatus.UNKNOWN) for gate in GateId}
        self.assertEqual(qualify_mandatory_gates(SourceRole.LIVE_PRICING_SOURCE, unknown), QualificationStatus.UNKNOWN)

    def test_short_retention_blocks_history_but_can_support_prospective_replay(self):
        gates = self._gates()
        gates[GateId.HISTORICAL_RETENTION] = self._gate(GateStatus.FAIL, "short retention")
        gates[GateId.FROZEN_PERIOD_COVERAGE] = self._gate(GateStatus.FAIL, "no frozen backfill")
        self.assertEqual(qualify_mandatory_gates(SourceRole.HISTORICAL_RESEARCH_SOURCE, gates), QualificationStatus.DISQUALIFIED)
        self.assertEqual(qualify_prospective_replay(gates), QualificationStatus.QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY)

        frozen_unknown = self._gates()
        frozen_unknown[GateId.FROZEN_PERIOD_COVERAGE] = self._gate(
            GateStatus.UNKNOWN, "frozen period not proven"
        )
        self.assertEqual(
            qualify_mandatory_gates(
                SourceRole.HISTORICAL_RESEARCH_SOURCE, frozen_unknown
            ),
            QualificationStatus.PARTIALLY_QUALIFIED,
        )

    def test_evidence_paths_hashes_and_sizes_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_bytes(b"review")
            valid = [{"path": "review.txt", "byte_size": 6, "sha256": hashlib.sha256(b"review").hexdigest()}]
            self.assertEqual(validate_evidence_files(valid, evidence_root=root)[0]["relative_path"], "review.txt")
            invalid_cases = (
                [{**valid[0], "path": "../review.txt"}],
                [{**valid[0], "sha256": "0" * 64}],
                [{**valid[0], "byte_size": 7}],
                [{**valid[0], "path": str(evidence.resolve())}],
            )
            for records in invalid_cases:
                with self.subTest(records=records):
                    with self.assertRaises(QualificationExportError):
                        validate_evidence_files(records, evidence_root=root)

    def test_report_is_deterministic_atomic_and_contains_no_value_or_bet_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("review", encoding="utf-8")
            candidate = self._candidate(evidence)
            kwargs = dict(
                evidence_root=root,
                protocol=self.protocol,
                code_state={"evidence_git_head_sha": "1" * 40, "tracked_worktree_clean": True},
                input_identity={"byte_size": 1, "sha256": "a" * 64},
            )
            first = qualify_candidate(candidate, **kwargs)
            second = qualify_candidate(candidate, **kwargs)
            self.assertEqual(_canonical_json_bytes(first), _canonical_json_bytes(second))
            self.assertEqual(first["qualification"]["historical_status"], "QUALIFIED_FOR_HISTORICAL_RESEARCH")
            self.assertEqual(first["qualification"]["live_pricing_status"], "QUALIFIED_FOR_LIVE_PRICING")
            self.assertEqual(first["qualification"]["execution_bookmaker_status"], "QUALIFIED_AS_EXECUTION_BOOKMAKER")
            self.assertEqual(set(first["gate_results"]), {gate.value for gate in GateId})
            output = root / "output.json"
            write_report(output, first)
            self.assertTrue(output.exists())
            with self.assertRaises(QualificationExportError):
                write_report(output, first)
            text = output.read_text(encoding="utf-8").lower()
            for forbidden in ('"edge"', '"kelly"', '"expected_value"', '"profitability"', '"stake"', '"bet"', '"acca"'):
                self.assertNotIn(forbidden, text)

    def test_clean_worktree_enforcement_and_offline_entrypoints(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("review", encoding="utf-8")
            candidate_path = root / "candidate.json"
            candidate_path.write_text(json.dumps(self._candidate(evidence)), encoding="utf-8")
            with patch(
                "scripts.qualify_win_either_half_pricing_source.get_code_state",
                return_value={"evidence_git_head_sha": "1" * 40, "tracked_worktree_clean": False},
            ):
                self.assertEqual(main(["--input", str(candidate_path), "--evidence-root", str(root), "--output", str(root / "out.json")]), 1)
            commands = (
                [sys.executable, "scripts/qualify_win_either_half_pricing_source.py", "--help"],
                [sys.executable, "-m", "scripts.qualify_win_either_half_pricing_source", "--help"],
            )
            with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")):
                for command in commands:
                    result = subprocess.run(command, cwd=self.REPOSITORY_ROOT, capture_output=True, text=True, encoding="utf-8", shell=False, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_protocol_candidates_decision_schema_holdout_and_ignored_output(self):
        candidates = {item["provider_identifier"]: item for item in self.protocol["candidate_provider_templates"]}
        self.assertEqual(candidates["sportybet"]["provisional_status"], "PARTIALLY_QUALIFIED")
        self.assertEqual(
            candidates["sportybet"]["provisional_role_statuses"],
            {
                "execution_bookmaker_status": "PARTIALLY_QUALIFIED",
                "historical_status": "UNKNOWN",
                "live_pricing_status": "PARTIALLY_QUALIFIED",
                "prospective_replay_status": "UNKNOWN",
            },
        )
        self.assertEqual(candidates["sportmonks"]["provisional_status"], "UNKNOWN")
        self.assertEqual(candidates["the_odds_api"]["provisional_status"], "UNKNOWN")
        decision = self.protocol["decision_protocol"]
        self.assertIsNone(decision["seconds_before_kickoff"])
        self.assertEqual(decision, DEFAULT_DECISION_PROTOCOL.to_dict())
        self.assertEqual(self.protocol["holdout_governance"]["final_test_season"], "2025-26")
        self.assertEqual(CONSUMED_HOLDOUT_GOVERNANCE["status"], "ALREADY_CONSUMED_AUDIT_HOLDOUT")
        ignored = subprocess.run(
            ["git", "check-ignore", ".cache/athena-research/win-either-half/pricing-source-qualification-v1.json"],
            cwd=self.REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertIn("pricing-source-qualification-v1.json", ignored.stdout)

    def test_all_market_registrations_and_statuses_are_unchanged(self):
        self.assertEqual(set(MARKET_REGISTRY), set(MarketId))
        self.assertEqual(set(MODEL_STATUS_REGISTRY), set(MarketId))
        expected = {
            "MATCH_RESULT": "ACTIVE",
            "ASIAN_HANDICAP": "EXPERIMENTAL",
            "TOTAL_GOALS": "ACTIVE",
            "DRAW_OR_OVER_2_5": "EXPERIMENTAL",
            "AWAY_OR_OVER_2_5": "EXPERIMENTAL",
            "HOME_OR_OVER_2_5": "EXPERIMENTAL",
            "HOME_WIN_EITHER_HALF": "DISABLED",
            "AWAY_WIN_EITHER_HALF": "DISABLED",
            "DOUBLE_CHANCE": "ACTIVE",
            "BTTS": "EXPERIMENTAL",
            "DRAW_NO_BET": "DISABLED",
            "HOME_WIN_TO_NIL": "EXPERIMENTAL",
            "AWAY_WIN_TO_NIL": "EXPERIMENTAL",
            "MATCH_RESULT_1UP": "DISABLED",
            "MATCH_RESULT_2UP": "DISABLED",
        }
        self.assertEqual(
            {market.value: status.status.value for market, status in MODEL_STATUS_REGISTRY.items()},
            expected,
        )
        self.assertEqual(MODEL_STATUS_REGISTRY[MarketId.HOME_WIN_EITHER_HALF].status, ModelStatus.DISABLED)
        self.assertEqual(MODEL_STATUS_REGISTRY[MarketId.AWAY_WIN_EITHER_HALF].status, ModelStatus.DISABLED)
        self.assertEqual(len(MarketId), 15)

    def test_mandatory_gate_sets_cover_distinct_roles(self):
        self.assertIn(GateId.HISTORICAL_RETENTION, HISTORICAL_REQUIRED_GATES)
        self.assertNotIn(GateId.HISTORICAL_RETENTION, LIVE_REQUIRED_GATES)
        self.assertIn(GateId.DETERMINISTIC_BETSLIP, EXECUTION_REQUIRED_GATES)
        self.assertNotIn(GateId.DETERMINISTIC_BETSLIP, HISTORICAL_REQUIRED_GATES)
        self.assertIn(GateId.REPRODUCIBLE_EXPORT, PROSPECTIVE_REQUIRED_GATES)

    def test_direct_and_module_entrypoints_generate_and_check_real_temp_reports(self):
        commands = (
            [sys.executable, "scripts/qualify_win_either_half_pricing_source.py"],
            [sys.executable, "-m", "scripts.qualify_win_either_half_pricing_source"],
        )
        for index, command in enumerate(commands):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                evidence = root / "review.txt"
                evidence.write_text("review", encoding="utf-8")
                candidate = root / "candidate.json"
                candidate.write_text(
                    json.dumps(self._candidate(evidence), sort_keys=True),
                    encoding="utf-8",
                )
                output = root / f"report-{index}.json"
                common = [
                    "--input",
                    str(candidate),
                    "--evidence-root",
                    str(root),
                    "--protocol",
                    str(DEFAULT_PROTOCOL_PATH),
                ]
                generated = subprocess.run(
                    [*command, *common, "--output", str(output)],
                    cwd=self.REPOSITORY_ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    shell=False,
                    timeout=60,
                )
                self.assertEqual(generated.returncode, 0, generated.stderr)
                checked = subprocess.run(
                    [*command, *common, "--check", str(output)],
                    cwd=self.REPOSITORY_ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    shell=False,
                    timeout=60,
                )
                self.assertEqual(checked.returncode, 0, checked.stderr)


if __name__ == "__main__":
    unittest.main()
