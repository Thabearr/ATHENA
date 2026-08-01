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
    validate_protocol_contract,
    validate_evidence_files,
    write_report,
)


class WinEitherHalfPricingSourceQualificationTests(unittest.TestCase):
    REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
    CHECKED_AT = "2026-08-01T12:00:00Z"

    def setUp(self):
        self.checked_at = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        protocol_bytes = DEFAULT_PROTOCOL_PATH.read_bytes()
        self.protocol_value = json.loads(protocol_bytes.decode("utf-8"))
        self.protocol = validate_protocol_contract(self.protocol_value, protocol_bytes)
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
            "provider_market_identifier": f"provider-{market.value}",
            "provider_market_name": "Provider localized market name",
            "provider_description": "Reviewed provider settlement documentation",
            "subject": expected["subject"],
            "yes_settlement": expected["yes_settlement"],
            "no_settlement": expected["no_settlement"],
            "line": None,
            "provider_yes_selection_identifier": f"{market.value}-yes",
            "provider_yes_selection_label": "Yes",
            "provider_no_selection_identifier": f"{market.value}-no",
            "provider_no_selection_label": "No",
            "yes_canonical_outcome_id": "YES",
            "no_canonical_outcome_id": "NO",
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
                "evidence_reference": "review.txt",
                "checked_at": self.CHECKED_AT,
                "markets": [
                    self._semantics(MarketId.HOME_WIN_EITHER_HALF),
                    self._semantics(MarketId.AWAY_WIN_EITHER_HALF),
                ]
            },
            "outcome_evidence": {
                "canonical_outcome_ids": ["YES", "NO"],
                "provider_yes_selection_identifier": "provider-yes",
                "provider_yes_selection_label": "Yes",
                "provider_no_selection_identifier": "provider-no",
                "provider_no_selection_label": "No",
                "evidence_reference": "review.txt",
                "checked_at": self.CHECKED_AT,
            },
            "quote_field_evidence": {
                "raw_decimal_odds_capability": True,
                "bookmaker_identifier": "book-1",
                "bookmaker_name_or_source": "Bookmaker One",
                "provider_event_identifier": "event-1",
                "provider_market_identifier": "market-1",
                "provider_yes_selection_identifier": "yes-1",
                "provider_no_selection_identifier": "no-1",
                "fixture_reference": "fixture-1",
                "evidence_reference": "review.txt",
                "checked_at": self.CHECKED_AT,
            },
            "timestamp_evidence": {
                "timestamp_source": "PROVIDER_QUOTE_OR_UPDATE",
                "sample_timestamp": self.CHECKED_AT,
                "download_time_distinct": True,
                "quote_ordering_reproducible": True,
                "evidence_reference": "review.txt",
                "checked_at": self.CHECKED_AT,
            },
            "snapshot_evidence": {
                "provider_identifier": "provider-1",
                "fixture_identifier": "fixture-1",
                "market_id": MarketId.HOME_WIN_EITHER_HALF.value,
                "bookmaker_identifier": "book-1",
                "yes_observed_at": self.CHECKED_AT,
                "no_observed_at": self.CHECKED_AT,
                "native_snapshot_id": "snapshot-1",
                "evidence_reference": "review.txt",
                "checked_at": self.CHECKED_AT,
            },
            "historical_retention_evidence": {
                "retained_settled_history": True,
                "historical_observed_at": True,
                "bookmaker_identity": True,
                "exact_market_and_selections": True,
                "quote_change_ordering": True,
                "archived_or_exportable_snapshots": True,
                "frozen_period_coverage": {
                    "CALIBRATION_FIT_OOF": 21270,
                    "VALIDATION_SELECTION": 6952,
                    "FINAL_TEST": 8096,
                    "total": 36318,
                },
                "evidence_reference": "review.txt",
                "checked_at": self.CHECKED_AT,
            },
            "live_pricing_evidence": {
                "current_exact_market_availability": True,
                "complete_yes_no_snapshots": True,
                "latest_eligible_snapshot_selection": True,
                "provider_mapping_reproducible": True,
                "timezone_aware_quote_updates": True,
                "maximum_quote_age_seconds": 900,
                "excludes_post_decision": True,
                "excludes_post_kickoff": True,
                "evidence_reference": "review.txt",
                "checked_at": self.CHECKED_AT,
            },
            "fixture_mapping_evidence": {
                "examples": [
                    {
                        "provider": self._fixture_mapping("provider-event-1"),
                        "canonical": self._fixture_mapping("athena-fixture-1"),
                        "fuzzy_only": False,
                    }
                ],
                "aggregate_results": {
                    "EXACT": 1,
                    "CONFLICT": 0,
                    "AMBIGUOUS": 0,
                    "UNAVAILABLE": 0,
                },
                "independent_fuzzy_name_qualification": False,
                "evidence_reference": "review.txt",
                "checked_at": self.CHECKED_AT,
            },
            "export_reproducibility_evidence": {
                "reproducible_export": True,
                "stable_fixture_market_identifiers": True,
                "deterministic_ordering": True,
                "evidence_reference": "review.txt",
                "checked_at": self.CHECKED_AT,
            },
            "licensing_and_retention_evidence": {
                "research_retention_permission": True,
                "retained_research_use_permitted": True,
                "evidence_reference": "review.txt",
                "checked_at": self.CHECKED_AT,
            },
            "execution_workflow_evidence": {
                "exact_fixture_market_outcome_selection": True,
                "deterministic_betslip_construction": True,
                "validated_price_matching": True,
                "changed_odds_detection": True,
                "suspended_selection_detection": True,
                "missing_market_detection": True,
                "explicit_user_confirmation": True,
                "permitted_automation": True,
                "evidence_reference": "review.txt",
                "checked_at": self.CHECKED_AT,
            },
            "booking_code_evidence": {
                "capability_status": "UNAVAILABLE",
                "evidence_reference": "review.txt",
                "checked_at": self.CHECKED_AT,
            },
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

    def _fixture_mapping(self, event_identifier):
        return {
            "provider_event_identifier": event_identifier,
            "competition_identifier": "E0",
            "season_identifier": "2025-26",
            "kickoff": "2026-08-10T15:00:00Z",
            "home_participant_identifier": "home-1",
            "home_participant_name": "Home",
            "away_participant_identifier": "away-1",
            "away_participant_name": "Away",
            "neutral_venue": False,
            "fixture_status": "SCHEDULED",
        }

    def _qualify(self, candidate, root):
        return qualify_candidate(
            candidate,
            evidence_root=root,
            protocol=self.protocol,
            code_state={
                "evidence_git_head_sha": "1" * 40,
                "tracked_worktree_clean": True,
            },
            input_identity={"byte_size": 1, "sha256": "a" * 64},
        )

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
        for settlement in substitutions:
            with self.subTest(settlement=settlement):
                result = validate_market_semantics(
                    self._semantics(
                        MarketId.HOME_WIN_EITHER_HALF,
                        yes_settlement=settlement,
                    )
                )
                self.assertEqual(result.status, GateStatus.FAIL)
                self.assertEqual(result.reason, "MARKET_SEMANTICS_MISMATCH")
        missing = self._semantics(MarketId.HOME_WIN_EITHER_HALF)
        missing.pop("provider_description")
        self.assertEqual(validate_market_semantics(missing).status, GateStatus.UNKNOWN)
        localized = validate_market_semantics(
            self._semantics(
                MarketId.HOME_WIN_EITHER_HALF,
                provider_market_name="Equipo local gana cualquiera de las mitades",
            )
        )
        self.assertEqual(localized.status, GateStatus.PASS)

    def test_exact_outcomes_and_quote_evidence_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("review", encoding="utf-8")
            cases = []
            candidate = self._candidate(evidence)
            candidate["outcome_evidence"]["canonical_outcome_ids"] = ["YES", "HOME"]
            cases.append((candidate, GateId.EXACT_YES_NO_STRUCTURE))
            candidate = self._candidate(evidence)
            candidate["quote_field_evidence"]["raw_decimal_odds_capability"] = False
            cases.append((candidate, GateId.RAW_DECIMAL_ODDS))
            candidate = self._candidate(evidence)
            candidate["quote_field_evidence"]["bookmaker_identifier"] = True
            cases.append((candidate, GateId.BOOKMAKER_PROVENANCE))
            candidate = self._candidate(evidence)
            candidate["timestamp_evidence"]["timestamp_source"] = "DOWNLOAD_TIME"
            cases.append((candidate, GateId.QUOTE_OBSERVED_AT))
            candidate = self._candidate(evidence)
            candidate["snapshot_evidence"]["no_observed_at"] = "2026-08-01T12:00:01Z"
            cases.append((candidate, GateId.SAME_BOOKMAKER_SNAPSHOT))
            for candidate, gate in cases:
                with self.subTest(gate=gate):
                    report = qualify_candidate(
                        candidate,
                        evidence_root=root,
                        protocol=self.protocol,
                        code_state={"evidence_git_head_sha": "1" * 40, "tracked_worktree_clean": True},
                        input_identity={"byte_size": 1, "sha256": "a" * 64},
                    )
                    self.assertEqual(
                        report["gate_results"][gate.value]["effective"]["status"],
                        "FAIL",
                    )

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
            for gate_result in first["gate_results"].values():
                self.assertEqual(
                    set(gate_result), {"declared", "derived", "effective"}
                )
            protocol_bytes = DEFAULT_PROTOCOL_PATH.read_bytes()
            self.assertEqual(first["protocol"]["byte_size"], len(protocol_bytes))
            self.assertEqual(
                first["protocol"]["sha256"], hashlib.sha256(protocol_bytes).hexdigest()
            )
            self.assertEqual(
                first["decision_protocol"], self.protocol_value["decision_protocol"]
            )
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
        candidates = {item["provider_identifier"]: item for item in self.protocol_value["candidate_provider_templates"]}
        self.assertEqual(candidates["sportybet"]["provisional_status"], "UNKNOWN")
        self.assertEqual(
            candidates["sportybet"]["provisional_role_statuses"],
            {
                "execution_bookmaker_status": "UNKNOWN",
                "historical_status": "UNKNOWN",
                "live_pricing_status": "UNKNOWN",
                "prospective_replay_status": "UNKNOWN",
            },
        )
        self.assertEqual(candidates["sportmonks"]["provisional_status"], "UNKNOWN")
        self.assertEqual(candidates["the_odds_api"]["provisional_status"], "UNKNOWN")
        decision = self.protocol_value["decision_protocol"]
        self.assertIsNone(decision["seconds_before_kickoff"])
        self.assertEqual(decision, DEFAULT_DECISION_PROTOCOL.to_dict())
        self.assertEqual(self.protocol_value["holdout_governance"]["final_test_season"], "2025-26")
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

    def test_self_declared_pass_is_downgraded_when_structured_sections_are_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("generic review", encoding="utf-8")
            candidate = self._candidate(evidence)
            for section in (
                "market_semantics_evidence",
                "outcome_evidence",
                "quote_field_evidence",
                "timestamp_evidence",
                "snapshot_evidence",
                "historical_retention_evidence",
                "live_pricing_evidence",
                "fixture_mapping_evidence",
                "export_reproducibility_evidence",
                "licensing_and_retention_evidence",
                "execution_workflow_evidence",
            ):
                candidate[section] = {}
            report = self._qualify(candidate, root)
            for role_status in report["qualification"].values():
                self.assertNotIn(role_status, {
                    "QUALIFIED_FOR_HISTORICAL_RESEARCH",
                    "QUALIFIED_FOR_LIVE_PRICING",
                    "QUALIFIED_AS_EXECUTION_BOOKMAKER",
                    "QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY",
                })
            semantics = report["gate_results"][GateId.EXACT_MARKET_SEMANTICS.value]
            self.assertEqual(semantics["declared"]["status"], "PASS")
            self.assertEqual(semantics["derived"]["status"], "UNKNOWN")
            self.assertEqual(semantics["effective"]["status"], "UNKNOWN")

    def test_full_candidate_preserves_unknown_and_conflict_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("review", encoding="utf-8")
            valid = self._qualify(self._candidate(evidence), root)
            self.assertEqual(
                valid["gate_results"][GateId.EXACT_MARKET_SEMANTICS.value]["effective"]["status"],
                "PASS",
            )
            missing_candidate = self._candidate(evidence)
            missing_candidate["market_semantics_evidence"]["markets"][0].pop(
                "provider_description"
            )
            missing = self._qualify(missing_candidate, root)
            self.assertEqual(
                missing["gate_results"][GateId.EXACT_MARKET_SEMANTICS.value]["effective"]["status"],
                "UNKNOWN",
            )
            conflict_candidate = self._candidate(evidence)
            conflict_candidate["market_semantics_evidence"]["markets"][0][
                "yes_settlement"
            ] = "home team wins the first half"
            conflict = self._qualify(conflict_candidate, root)
            self.assertEqual(
                conflict["gate_results"][GateId.EXACT_MARKET_SEMANTICS.value]["effective"]["status"],
                "FAIL",
            )

    def test_boolean_provider_identifiers_snapshot_and_fixture_mapping_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("review", encoding="utf-8")
            candidate = self._candidate(evidence)
            candidate["quote_field_evidence"]["provider_event_identifier"] = True
            report = self._qualify(candidate, root)
            self.assertEqual(
                report["gate_results"][GateId.REPRODUCIBLE_PROVIDER_MAPPING.value]["derived"]["status"],
                "FAIL",
            )
            candidate = self._candidate(evidence)
            candidate["snapshot_evidence"]["no_observed_at"] = "2026-08-01T12:00:01Z"
            report = self._qualify(candidate, root)
            self.assertEqual(
                report["gate_results"][GateId.SAME_BOOKMAKER_SNAPSHOT.value]["derived"]["reason"],
                "MIXED_OBSERVED_AT",
            )
            candidate = self._candidate(evidence)
            candidate["fixture_mapping_evidence"]["examples"][0]["provider"][
                "home_participant_identifier"
            ] = "away-1"
            candidate["fixture_mapping_evidence"]["examples"][0]["provider"][
                "away_participant_identifier"
            ] = "home-1"
            candidate["fixture_mapping_evidence"]["aggregate_results"] = {
                "EXACT": 0,
                "CONFLICT": 1,
                "AMBIGUOUS": 0,
                "UNAVAILABLE": 0,
            }
            report = self._qualify(candidate, root)
            self.assertEqual(
                report["gate_results"][GateId.FIXTURE_MAPPING.value]["derived"]["status"],
                "FAIL",
            )

    def test_exact_frozen_coverage_live_freshness_and_retention_permission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("review", encoding="utf-8")
            candidate = self._candidate(evidence)
            candidate["historical_retention_evidence"]["frozen_period_coverage"][
                "FINAL_TEST"
            ] = 8095
            report = self._qualify(candidate, root)
            self.assertEqual(
                report["gate_results"][GateId.FROZEN_PERIOD_COVERAGE.value]["effective"]["status"],
                "FAIL",
            )
            candidate = self._candidate(evidence)
            candidate["live_pricing_evidence"]["maximum_quote_age_seconds"] = 901
            report = self._qualify(candidate, root)
            self.assertEqual(
                report["gate_results"][GateId.FRESHNESS_ENFORCEABLE.value]["effective"]["status"],
                "FAIL",
            )
            candidate = self._candidate(evidence)
            candidate["licensing_and_retention_evidence"] = {}
            report = self._qualify(candidate, root)
            self.assertNotEqual(
                report["qualification"]["historical_status"],
                "QUALIFIED_FOR_HISTORICAL_RESEARCH",
            )
            self.assertNotEqual(
                report["qualification"]["prospective_replay_status"],
                "QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY",
            )

    def test_not_applicable_never_satisfies_mandatory_gates(self):
        all_not_applicable = {
            gate: self._gate(GateStatus.NOT_APPLICABLE) for gate in GateId
        }
        for role in SourceRole:
            with self.subTest(role=role):
                self.assertEqual(
                    qualify_mandatory_gates(role, all_not_applicable),
                    QualificationStatus.DISQUALIFIED,
                )
        self.assertEqual(
            qualify_prospective_replay(all_not_applicable),
            QualificationStatus.DISQUALIFIED,
        )
        for role, gate in (
            (SourceRole.HISTORICAL_RESEARCH_SOURCE, GateId.EXACT_MARKET_SEMANTICS),
            (SourceRole.HISTORICAL_RESEARCH_SOURCE, GateId.FIXTURE_MAPPING),
            (SourceRole.HISTORICAL_RESEARCH_SOURCE, GateId.HISTORICAL_RETENTION),
            (SourceRole.LIVE_PRICING_SOURCE, GateId.QUOTE_OBSERVED_AT),
        ):
            gates = self._gates()
            gates[gate] = self._gate(GateStatus.NOT_APPLICABLE)
            self.assertEqual(
                qualify_mandatory_gates(role, gates), QualificationStatus.DISQUALIFIED
            )

    def test_execution_can_qualify_without_booking_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("review", encoding="utf-8")
            report = self._qualify(self._candidate(evidence), root)
            self.assertEqual(
                report["qualification"]["execution_bookmaker_status"],
                "QUALIFIED_AS_EXECUTION_BOOKMAKER",
            )
            self.assertEqual(
                report["gate_results"][GateId.BOOKING_CODE_SUPPORT.value]["effective"]["status"],
                "NOT_APPLICABLE",
            )

    def test_protocol_identity_and_contract_mutations_fail_closed(self):
        protocol_bytes = DEFAULT_PROTOCOL_PATH.read_bytes()
        validated = validate_protocol_contract(
            json.loads(protocol_bytes.decode("utf-8")), protocol_bytes
        )
        self.assertEqual(validated.byte_size, len(protocol_bytes))
        self.assertEqual(validated.sha256, hashlib.sha256(protocol_bytes).hexdigest())
        mutations = {
            "mandatory_gates": lambda value: value["role_mandatory_gates"]["LIVE_PRICING_SOURCE"].pop(),
            "qualification_statuses": lambda value: value["qualification_statuses"].pop(),
            "market_semantics": lambda value: value["market_scope"]["HOME_WIN_EITHER_HALF"].__setitem__("subject", "AWAY_TEAM"),
            "fixture_tolerance": lambda value: value["fixture_mapping"].__setitem__("kickoff_tolerance_seconds", 301),
            "snapshot_contract": lambda value: value["snapshot_contract"].__setitem__("same_observed_at", False),
            "maximum_quote_age": lambda value: value["decision_protocol"].__setitem__("maximum_quote_age_seconds", 901),
            "decision_protocol": lambda value: value["decision_protocol"].__setitem__("timezone", "LOCAL"),
            "frozen_denominator": lambda value: value["frozen_fixture_market_denominator"].__setitem__("total", 36317),
            "holdout_governance": lambda value: value["holdout_governance"].__setitem__("status", "PRISTINE"),
            "no_production": lambda value: value.__setitem__("no_production_approval", False),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                changed = json.loads(json.dumps(self.protocol_value))
                mutate(changed)
                changed_bytes = _canonical_json_bytes(changed)
                with self.assertRaises(QualificationExportError):
                    validate_protocol_contract(changed, changed_bytes)

    def test_modified_protocol_fails_before_report_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("review", encoding="utf-8")
            candidate_path = root / "candidate.json"
            candidate_path.write_text(
                json.dumps(self._candidate(evidence), sort_keys=True),
                encoding="utf-8",
            )
            changed = json.loads(json.dumps(self.protocol_value))
            changed["decision_protocol"]["maximum_quote_age_seconds"] = 901
            protocol_path = root / "modified-protocol.json"
            protocol_path.write_text(
                json.dumps(changed, sort_keys=True), encoding="utf-8"
            )
            output = root / "report.json"
            with patch(
                "scripts.qualify_win_either_half_pricing_source.get_code_state",
                side_effect=AssertionError("code state must not be inspected"),
            ):
                self.assertEqual(
                    main(
                        [
                            "--input",
                            str(candidate_path),
                            "--evidence-root",
                            str(root),
                            "--protocol",
                            str(protocol_path),
                            "--output",
                            str(output),
                        ]
                    ),
                    1,
                )
            self.assertFalse(output.exists())

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
