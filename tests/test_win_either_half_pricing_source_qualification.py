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

    GATE_CAPABILITY = {
        GateId.EXACT_MARKET_SEMANTICS: "MARKET_SEMANTICS",
        GateId.EXACT_YES_NO_STRUCTURE: "OUTCOME_STRUCTURE",
        GateId.RAW_DECIMAL_ODDS: "QUOTE_SCHEMA",
        GateId.BOOKMAKER_PROVENANCE: "QUOTE_SCHEMA",
        GateId.QUOTE_OBSERVED_AT: "TIMESTAMP",
        GateId.SAME_BOOKMAKER_SNAPSHOT: "SNAPSHOT",
        GateId.FIXTURE_MAPPING: "FIXTURE_MAPPING",
        GateId.REPRODUCIBLE_EXPORT: "REPRODUCIBLE_EXPORT",
        GateId.HISTORICAL_RETENTION: "HISTORICAL_RETENTION",
        GateId.FROZEN_PERIOD_COVERAGE: "FROZEN_COVERAGE",
        GateId.RESEARCH_RETENTION_PERMISSION: "RESEARCH_PERMISSION",
        GateId.CURRENT_MARKET_AVAILABILITY: "LIVE_AVAILABILITY",
        GateId.FRESHNESS_ENFORCEABLE: "LIVE_AVAILABILITY",
        GateId.REPRODUCIBLE_PROVIDER_MAPPING: "QUOTE_SCHEMA",
        GateId.PERMITTED_AUTOMATION: "EXECUTION_SAFETY",
        GateId.EXACT_EXECUTION_SELECTION: "EXECUTION_SELECTION",
        GateId.DETERMINISTIC_BETSLIP: "EXECUTION_SAFETY",
        GateId.VALIDATED_QUOTE_PRICE_MATCH: "EXECUTION_SAFETY",
        GateId.CHANGED_ODDS_DETECTION: "EXECUTION_SAFETY",
        GateId.SUSPENDED_SELECTION_DETECTION: "EXECUTION_SAFETY",
        GateId.MISSING_MARKET_DETECTION: "EXECUTION_SAFETY",
        GateId.EXPLICIT_USER_CONFIRMATION: "EXECUTION_SAFETY",
        GateId.BOOKING_CODE_SUPPORT: "BOOKING_CODE",
    }
    MARKET_SPECIFIC_CAPABILITIES = {
        "MARKET_SEMANTICS",
        "OUTCOME_STRUCTURE",
        "QUOTE_SCHEMA",
        "SNAPSHOT",
        "HISTORICAL_RETENTION",
        "FROZEN_COVERAGE",
        "LIVE_AVAILABILITY",
        "EXECUTION_SELECTION",
    }

    def _claim_id(self, capability):
        return f"claim-{capability.lower().replace('_', '-')}"

    def _gate(
        self,
        status=GateStatus.PASS,
        reason="reviewed evidence",
        gate=GateId.EXACT_MARKET_SEMANTICS,
    ):
        return GateEvidence(
            status,
            reason,
            (self._claim_id(self.GATE_CAPABILITY[gate]),),
            self.checked_at,
        )

    def _gates(self, default=GateStatus.PASS):
        return {gate: self._gate(default, gate=gate) for gate in GateId}

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
            "claim_ids": [self._claim_id("MARKET_SEMANTICS")],
            "checked_at": self.CHECKED_AT,
        }
        row.update(changes)
        return row

    def _candidate(self, evidence_file):
        gate_evidence = {
            gate.value: self._gate(
                GateStatus.NOT_APPLICABLE
                if gate is GateId.BOOKING_CODE_SUPPORT
                else GateStatus.PASS,
                gate=gate,
            ).to_dict()
            for gate in GateId
        }
        content = evidence_file.read_bytes()
        semantics = {
            market: self._semantics(market) for market in PERMITTED_MARKETS
        }
        quote_mappings = []
        snapshot_samples = []
        historical_markets = []
        live_markets = []
        for market in PERMITTED_MARKETS:
            semantic = semantics[market]
            quote_mappings.append(
                {
                    "market_id": market.value,
                    "provider_market_identifier": semantic["provider_market_identifier"],
                    "provider_market_name": semantic["provider_market_name"],
                    "provider_yes_selection_identifier": semantic["provider_yes_selection_identifier"],
                    "provider_yes_selection_label": semantic["provider_yes_selection_label"],
                    "provider_no_selection_identifier": semantic["provider_no_selection_identifier"],
                    "provider_no_selection_label": semantic["provider_no_selection_label"],
                    "bookmaker_identifier": "book-1",
                    "bookmaker_name_or_source": "Bookmaker One",
                    "provider_event_identifier": f"event-{market.value}",
                    "fixture_reference": f"fixture-{market.value}",
                    "raw_decimal_odds_capability": True,
                    "claim_ids": [self._claim_id("QUOTE_SCHEMA")],
                    "checked_at": self.CHECKED_AT,
                }
            )
            snapshot_samples.append(
                {
                    "market_id": market.value,
                    "provider_identifier": "reviewed-provider",
                    "provider_event_identifier": f"event-{market.value}",
                    "fixture_reference": f"fixture-{market.value}",
                    "provider_market_identifier": semantic["provider_market_identifier"],
                    "bookmaker_identifier": "book-1",
                    "provider_yes_selection_identifier": semantic["provider_yes_selection_identifier"],
                    "provider_no_selection_identifier": semantic["provider_no_selection_identifier"],
                    "outcome_identifiers": ["YES", "NO"],
                    "yes_observed_at": self.CHECKED_AT,
                    "no_observed_at": self.CHECKED_AT,
                    "native_snapshot_id": f"snapshot-{market.value}",
                    "claim_ids": [self._claim_id("SNAPSHOT")],
                    "checked_at": self.CHECKED_AT,
                }
            )
            historical_markets.append(
                {
                    "market_id": market.value,
                    "retained_settled_history": True,
                    "historical_observed_at": True,
                    "bookmaker_identity": True,
                    "exact_market_and_selections": True,
                    "quote_change_ordering": True,
                    "archived_or_exportable_snapshots": True,
                    "frozen_period_coverage": {
                        "CALIBRATION_FIT_OOF": 10635,
                        "VALIDATION_SELECTION": 3476,
                        "FINAL_TEST": 4048,
                        "total": 18159,
                    },
                    "retention_claim_ids": [self._claim_id("HISTORICAL_RETENTION")],
                    "coverage_claim_ids": [self._claim_id("FROZEN_COVERAGE")],
                    "claim_ids": [
                        self._claim_id("HISTORICAL_RETENTION"),
                        self._claim_id("FROZEN_COVERAGE"),
                    ],
                    "checked_at": self.CHECKED_AT,
                }
            )
            live_markets.append(
                {
                    "market_id": market.value,
                    "current_exact_market_availability": True,
                    "complete_yes_no_snapshots": True,
                    "latest_eligible_snapshot_selection": True,
                    "provider_mapping_reproducible": True,
                    "timezone_aware_quote_updates": True,
                    "maximum_quote_age_seconds": 900,
                    "excludes_post_decision": True,
                    "excludes_post_kickoff": True,
                    "claim_ids": [self._claim_id("LIVE_AVAILABILITY")],
                    "checked_at": self.CHECKED_AT,
                }
            )
        evidence_claims = [
            {
                "claim_id": self._claim_id(capability),
                "provider_identifier": "reviewed-provider",
                "evidence_file_path": evidence_file.name,
                "document_title": f"Reviewed {capability} artifact",
                "source_reference": f"section:{capability.lower()}",
                "capability_identifier": capability,
                "canonical_market_ids": (
                    [market.value for market in PERMITTED_MARKETS]
                    if capability in self.MARKET_SPECIFIC_CAPABILITIES
                    else []
                ),
                "capability_statement": f"Reviewed evidence for {capability}",
                "retrieval_timestamp": self.CHECKED_AT,
                "reviewer_checked_at": self.CHECKED_AT,
                "reviewer_conclusion": "PASS",
            }
            for capability in sorted(set(self.GATE_CAPABILITY.values()))
        ]
        return {
            "schema_version": 1,
            "provider_identifier": "reviewed-provider",
            "provider_name": "Reviewed Provider",
            "candidate_roles": [role.value for role in SourceRole],
            "evidence_checked_at": self.CHECKED_AT,
            "market_semantics_evidence": {
                "claim_ids": [self._claim_id("MARKET_SEMANTICS")],
                "checked_at": self.CHECKED_AT,
                "markets": [semantics[market] for market in PERMITTED_MARKETS],
            },
            "outcome_evidence": {
                "canonical_outcome_ids": ["YES", "NO"],
                "claim_ids": [self._claim_id("OUTCOME_STRUCTURE")],
                "checked_at": self.CHECKED_AT,
            },
            "quote_field_evidence": {
                "mappings": quote_mappings,
                "shared_provider_market_identifier_proven_for_both_subjects": False,
                "claim_ids": [self._claim_id("QUOTE_SCHEMA")],
                "checked_at": self.CHECKED_AT,
            },
            "timestamp_evidence": {
                "timestamp_source": "PROVIDER_QUOTE_OR_UPDATE",
                "sample_timestamp": self.CHECKED_AT,
                "download_time_distinct": True,
                "quote_ordering_reproducible": True,
                "claim_ids": [self._claim_id("TIMESTAMP")],
                "checked_at": self.CHECKED_AT,
            },
            "snapshot_evidence": {
                "samples": snapshot_samples,
                "claim_ids": [self._claim_id("SNAPSHOT")],
                "checked_at": self.CHECKED_AT,
            },
            "historical_retention_evidence": {
                "markets": historical_markets,
                "combined_frozen_period_coverage": {
                    "CALIBRATION_FIT_OOF": 21270,
                    "VALIDATION_SELECTION": 6952,
                    "FINAL_TEST": 8096,
                    "total": 36318,
                },
                "coverage_claim_ids": [self._claim_id("FROZEN_COVERAGE")],
                "claim_ids": [
                    self._claim_id("HISTORICAL_RETENTION"),
                    self._claim_id("FROZEN_COVERAGE"),
                ],
                "checked_at": self.CHECKED_AT,
            },
            "live_pricing_evidence": {
                "markets": live_markets,
                "claim_ids": [self._claim_id("LIVE_AVAILABILITY")],
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
                "claim_ids": [self._claim_id("FIXTURE_MAPPING")],
                "checked_at": self.CHECKED_AT,
            },
            "export_reproducibility_evidence": {
                "reproducible_export": True,
                "stable_fixture_market_identifiers": True,
                "deterministic_ordering": True,
                "claim_ids": [self._claim_id("REPRODUCIBLE_EXPORT")],
                "checked_at": self.CHECKED_AT,
            },
            "licensing_and_retention_evidence": {
                "research_retention_permission": True,
                "retained_research_use_permitted": True,
                "claim_ids": [self._claim_id("RESEARCH_PERMISSION")],
                "checked_at": self.CHECKED_AT,
            },
            "execution_workflow_evidence": {
                "exact_fixture_market_outcome_selection": True,
                "exact_selection_claim_ids": [
                    self._claim_id("EXECUTION_SELECTION")
                ],
                "deterministic_betslip_construction": True,
                "validated_price_matching": True,
                "changed_odds_detection": True,
                "suspended_selection_detection": True,
                "missing_market_detection": True,
                "explicit_user_confirmation": True,
                "permitted_automation": True,
                "claim_ids": [self._claim_id("EXECUTION_SAFETY")],
                "checked_at": self.CHECKED_AT,
            },
            "booking_code_evidence": {
                "capability_status": "UNAVAILABLE",
                "claim_ids": [self._claim_id("BOOKING_CODE")],
                "checked_at": self.CHECKED_AT,
            },
            "gate_evidence": gate_evidence,
            "evidence_claims": evidence_claims,
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
            candidate["quote_field_evidence"]["mappings"][0][
                "raw_decimal_odds_capability"
            ] = False
            cases.append((candidate, GateId.RAW_DECIMAL_ODDS))
            candidate = self._candidate(evidence)
            candidate["quote_field_evidence"]["mappings"][0][
                "bookmaker_identifier"
            ] = True
            cases.append((candidate, GateId.BOOKMAKER_PROVENANCE))
            candidate = self._candidate(evidence)
            candidate["timestamp_evidence"]["timestamp_source"] = "DOWNLOAD_TIME"
            cases.append((candidate, GateId.QUOTE_OBSERVED_AT))
            candidate = self._candidate(evidence)
            candidate["snapshot_evidence"]["samples"][0][
                "no_observed_at"
            ] = "2026-08-01T12:00:01Z"
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
            "DRAW_NO_BET": "EXPERIMENTAL",
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
            candidate["quote_field_evidence"]["mappings"][0][
                "provider_event_identifier"
            ] = True
            report = self._qualify(candidate, root)
            self.assertEqual(
                report["gate_results"][GateId.REPRODUCIBLE_PROVIDER_MAPPING.value]["derived"]["status"],
                "FAIL",
            )
            candidate = self._candidate(evidence)
            candidate["snapshot_evidence"]["samples"][0][
                "no_observed_at"
            ] = "2026-08-01T12:00:01Z"
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
            candidate["historical_retention_evidence"]["markets"][0][
                "frozen_period_coverage"
            ]["FINAL_TEST"] = 4047
            report = self._qualify(candidate, root)
            self.assertEqual(
                report["gate_results"][GateId.FROZEN_PERIOD_COVERAGE.value]["effective"]["status"],
                "FAIL",
            )
            candidate = self._candidate(evidence)
            candidate["live_pricing_evidence"]["markets"][0][
                "maximum_quote_age_seconds"
            ] = 901
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

    def test_both_market_quote_mappings_and_snapshots_are_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("review", encoding="utf-8")
            cases = (
                ("quote_field_evidence", "mappings", 0, GateId.RAW_DECIMAL_ODDS),
                ("quote_field_evidence", "mappings", 1, GateId.RAW_DECIMAL_ODDS),
                ("snapshot_evidence", "samples", 0, GateId.SAME_BOOKMAKER_SNAPSHOT),
                ("snapshot_evidence", "samples", 1, GateId.SAME_BOOKMAKER_SNAPSHOT),
            )
            for section, rows, retained_index, gate in cases:
                with self.subTest(section=section, retained_index=retained_index):
                    candidate = self._candidate(evidence)
                    candidate[section][rows] = [candidate[section][rows][retained_index]]
                    report = self._qualify(candidate, root)
                    self.assertNotEqual(
                        report["qualification"]["live_pricing_status"],
                        "QUALIFIED_FOR_LIVE_PRICING",
                    )
                    self.assertNotEqual(
                        report["gate_results"][gate.value]["effective"]["status"],
                        "PASS",
                    )

    def test_market_mapping_duplicates_and_semantic_selection_mismatch_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("review", encoding="utf-8")
            duplicate = self._candidate(evidence)
            duplicate["quote_field_evidence"]["mappings"][1]["market_id"] = (
                duplicate["quote_field_evidence"]["mappings"][0]["market_id"]
            )
            duplicate_report = self._qualify(duplicate, root)
            self.assertEqual(
                duplicate_report["gate_results"][GateId.RAW_DECIMAL_ODDS.value][
                    "effective"
                ]["status"],
                "FAIL",
            )

            mismatch = self._candidate(evidence)
            mismatch["quote_field_evidence"]["mappings"][1][
                "provider_yes_selection_identifier"
            ] = mismatch["quote_field_evidence"]["mappings"][0][
                "provider_yes_selection_identifier"
            ]
            mismatch_report = self._qualify(mismatch, root)
            self.assertEqual(
                mismatch_report["gate_results"][GateId.REPRODUCIBLE_PROVIDER_MAPPING.value][
                    "effective"
                ]["status"],
                "FAIL",
            )

    def test_per_market_historical_coverage_and_combined_reconciliation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("review", encoding="utf-8")
            report = self._qualify(self._candidate(evidence), root)
            self.assertEqual(
                report["gate_results"][GateId.FROZEN_PERIOD_COVERAGE.value][
                    "effective"
                ]["status"],
                "PASS",
            )
            for market in PERMITTED_MARKETS:
                self.assertEqual(
                    report["market_qualification"][market.value]["historical_status"],
                    "PASS",
                )
                self.assertEqual(
                    report["market_qualification"][market.value][
                        "historical_frozen_period_coverage"
                    ],
                    {
                        "CALIBRATION_FIT_OOF": 10635,
                        "VALIDATION_SELECTION": 3476,
                        "FINAL_TEST": 4048,
                        "total": 18159,
                    },
                )

            market_drift = self._candidate(evidence)
            market_drift["historical_retention_evidence"]["markets"][0][
                "frozen_period_coverage"
            ]["total"] = 18158
            self.assertEqual(
                self._qualify(market_drift, root)["gate_results"][
                    GateId.FROZEN_PERIOD_COVERAGE.value
                ]["effective"]["status"],
                "FAIL",
            )
            combined_drift = self._candidate(evidence)
            combined_drift["historical_retention_evidence"][
                "combined_frozen_period_coverage"
            ]["total"] = 36317
            self.assertEqual(
                self._qualify(combined_drift, root)["gate_results"][
                    GateId.FROZEN_PERIOD_COVERAGE.value
                ]["effective"]["status"],
                "FAIL",
            )

    def test_live_capability_is_required_for_each_market(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("review", encoding="utf-8")
            candidate = self._candidate(evidence)
            candidate["live_pricing_evidence"]["markets"].pop()
            report = self._qualify(candidate, root)
            self.assertNotEqual(
                report["qualification"]["live_pricing_status"],
                "QUALIFIED_FOR_LIVE_PRICING",
            )
            self.assertEqual(
                sum(
                    result["live_status"] == "PASS"
                    for result in report["market_qualification"].values()
                ),
                1,
            )

    def test_typed_claims_are_authoritative_and_capability_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("generic text", encoding="utf-8")

            no_claims = self._candidate(evidence)
            no_claims["evidence_claims"] = []
            no_claim_report = self._qualify(no_claims, root)
            self.assertTrue(
                all(
                    not status.startswith("QUALIFIED")
                    for status in no_claim_report["qualification"].values()
                )
            )

            complete = self._qualify(self._candidate(evidence), root)
            self.assertEqual(
                complete["qualification"]["historical_status"],
                "QUALIFIED_FOR_HISTORICAL_RESEARCH",
            )

            unrelated = self._candidate(evidence)
            market_claim = next(
                claim
                for claim in unrelated["evidence_claims"]
                if claim["claim_id"] == self._claim_id("MARKET_SEMANTICS")
            )
            market_claim["capability_identifier"] = "BOOKING_CODE"
            self.assertEqual(
                self._qualify(unrelated, root)["gate_results"][
                    GateId.EXACT_MARKET_SEMANTICS.value
                ]["effective"]["status"],
                "FAIL",
            )

            unknown = self._candidate(evidence)
            unknown["evidence_claims"] = [
                claim
                for claim in unknown["evidence_claims"]
                if claim["claim_id"] != self._claim_id("MARKET_SEMANTICS")
            ]
            self.assertEqual(
                self._qualify(unknown, root)["gate_results"][
                    GateId.EXACT_MARKET_SEMANTICS.value
                ]["effective"]["status"],
                "UNKNOWN",
            )

            contradictory = self._candidate(evidence)
            next(
                claim
                for claim in contradictory["evidence_claims"]
                if claim["claim_id"] == self._claim_id("MARKET_SEMANTICS")
            )["reviewer_conclusion"] = "FAIL"
            self.assertEqual(
                self._qualify(contradictory, root)["gate_results"][
                    GateId.EXACT_MARKET_SEMANTICS.value
                ]["effective"]["status"],
                "FAIL",
            )

    def test_claim_registry_identity_provider_and_timestamps_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("review", encoding="utf-8")
            duplicate = self._candidate(evidence)
            duplicate["evidence_claims"].append(dict(duplicate["evidence_claims"][0]))
            with self.assertRaisesRegex(
                QualificationExportError, "claim IDs must be unique"
            ):
                self._qualify(duplicate, root)

            wrong_provider = self._candidate(evidence)
            wrong_provider["evidence_claims"][0]["provider_identifier"] = "other"
            with self.assertRaisesRegex(
                QualificationExportError, "provider does not match"
            ):
                self._qualify(wrong_provider, root)

            naive = self._candidate(evidence)
            naive["evidence_claims"][0]["retrieval_timestamp"] = "2026-08-01T12:00:00"
            with self.assertRaisesRegex(QualificationExportError, "timezone-aware"):
                self._qualify(naive, root)

    def test_failure_precedence_and_optional_booking_consistency(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("review", encoding="utf-8")

            reviewer_fail_unknown = self._candidate(evidence)
            reviewer_fail_unknown["gate_evidence"][GateId.EXACT_MARKET_SEMANTICS.value][
                "status"
            ] = "FAIL"
            reviewer_fail_unknown["market_semantics_evidence"]["markets"][0].pop(
                "provider_description"
            )
            self.assertEqual(
                self._qualify(reviewer_fail_unknown, root)["gate_results"][
                    GateId.EXACT_MARKET_SEMANTICS.value
                ]["effective"]["status"],
                "FAIL",
            )

            reviewer_fail_pass = self._candidate(evidence)
            reviewer_fail_pass["gate_evidence"][GateId.EXACT_MARKET_SEMANTICS.value][
                "status"
            ] = "FAIL"
            self.assertEqual(
                self._qualify(reviewer_fail_pass, root)["gate_results"][
                    GateId.EXACT_MARKET_SEMANTICS.value
                ]["effective"]["status"],
                "FAIL",
            )

            reviewer_unknown_structured_fail = self._candidate(evidence)
            reviewer_unknown_structured_fail["gate_evidence"][
                GateId.EXACT_MARKET_SEMANTICS.value
            ]["status"] = "UNKNOWN"
            reviewer_unknown_structured_fail["market_semantics_evidence"]["markets"][0][
                "yes_settlement"
            ] = "home team wins first half only"
            self.assertEqual(
                self._qualify(reviewer_unknown_structured_fail, root)["gate_results"][
                    GateId.EXACT_MARKET_SEMANTICS.value
                ]["effective"]["status"],
                "FAIL",
            )

            booking_fail = self._candidate(evidence)
            booking_fail["booking_code_evidence"]["capability_status"] = "CONFLICT"
            self.assertEqual(
                self._qualify(booking_fail, root)["gate_results"][
                    GateId.BOOKING_CODE_SUPPORT.value
                ]["effective"]["status"],
                "FAIL",
            )

            booking_pass = self._candidate(evidence)
            booking_pass["booking_code_evidence"]["capability_status"] = "AVAILABLE"
            self.assertEqual(
                self._qualify(booking_pass, root)["gate_results"][
                    GateId.BOOKING_CODE_SUPPORT.value
                ]["effective"]["status"],
                "FAIL",
            )

            booking_unavailable = self._qualify(self._candidate(evidence), root)
            self.assertEqual(
                booking_unavailable["gate_results"][GateId.BOOKING_CODE_SUPPORT.value][
                    "effective"
                ]["status"],
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
            "per_market_denominator": lambda value: value[
                "frozen_fixture_market_denominator_by_market"
            ]["HOME_WIN_EITHER_HALF"].__setitem__("total", 18158),
            "market_specific_contract": lambda value: value[
                "market_specific_evidence_contract"
            ].__setitem__("snapshot_samples_per_market", 0),
            "evidence_claim_contract": lambda value: value[
                "evidence_claim_contract"
            ]["gate_capability_allowlist"]["exact_market_semantics"].append(
                "BOOKING_CODE"
            ),
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

    def test_snapshot_samples_reconcile_to_exact_quote_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("review", encoding="utf-8")
            cases = {
                "provider_event_identifier": "other-event",
                "fixture_reference": "other-fixture",
                "provider_market_identifier": "other-market",
                "bookmaker_identifier": "other-book",
                "provider_yes_selection_identifier": "other-yes",
                "provider_no_selection_identifier": "other-no",
            }
            for field, replacement in cases.items():
                with self.subTest(field=field):
                    candidate = self._candidate(evidence)
                    candidate["snapshot_evidence"]["samples"][0][field] = replacement
                    report = self._qualify(candidate, root)
                    self.assertEqual(
                        report["gate_results"][
                            GateId.SAME_BOOKMAKER_SNAPSHOT.value
                        ]["effective"]["status"],
                        "FAIL",
                    )

            borrowed = self._candidate(evidence)
            home = borrowed["snapshot_evidence"]["samples"][0]
            away = borrowed["snapshot_evidence"]["samples"][1]
            for field in (
                "provider_event_identifier",
                "fixture_reference",
                "provider_market_identifier",
                "provider_yes_selection_identifier",
                "provider_no_selection_identifier",
            ):
                away[field] = home[field]
            self.assertEqual(
                self._qualify(borrowed, root)["gate_results"][
                    GateId.SAME_BOOKMAKER_SNAPSHOT.value
                ]["effective"]["status"],
                "FAIL",
            )

    def test_claim_market_scope_is_explicit_and_role_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("review", encoding="utf-8")

            home_only = self._candidate(evidence)
            next(
                claim
                for claim in home_only["evidence_claims"]
                if claim["claim_id"] == self._claim_id("MARKET_SEMANTICS")
            )["canonical_market_ids"] = [
                MarketId.HOME_WIN_EITHER_HALF.value
            ]
            report = self._qualify(home_only, root)
            self.assertEqual(
                report["gate_results"][
                    GateId.EXACT_MARKET_SEMANTICS.value
                ]["effective"]["status"],
                "FAIL",
            )
            self.assertEqual(
                report["market_qualification"][
                    MarketId.AWAY_WIN_EITHER_HALF.value
                ]["semantics_status"],
                "FAIL",
            )

            for scope in (
                [],
                ["MATCH_RESULT"],
                [
                    MarketId.HOME_WIN_EITHER_HALF.value,
                    MarketId.HOME_WIN_EITHER_HALF.value,
                ],
            ):
                candidate = self._candidate(evidence)
                next(
                    claim
                    for claim in candidate["evidence_claims"]
                    if claim["claim_id"] == self._claim_id("MARKET_SEMANTICS")
                )["canonical_market_ids"] = scope
                with self.subTest(scope=scope), self.assertRaises(
                    QualificationExportError
                ):
                    self._qualify(candidate, root)

            global_scoped = self._candidate(evidence)
            next(
                claim
                for claim in global_scoped["evidence_claims"]
                if claim["claim_id"] == self._claim_id("RESEARCH_PERMISSION")
            )["canonical_market_ids"] = [
                MarketId.HOME_WIN_EITHER_HALF.value
            ]
            self.assertEqual(
                self._qualify(global_scoped, root)["gate_results"][
                    GateId.RESEARCH_RETENTION_PERMISSION.value
                ]["effective"]["status"],
                "FAIL",
            )

            execution_home_only = self._candidate(evidence)
            next(
                claim
                for claim in execution_home_only["evidence_claims"]
                if claim["claim_id"] == self._claim_id("EXECUTION_SELECTION")
            )["canonical_market_ids"] = [
                MarketId.HOME_WIN_EITHER_HALF.value
            ]
            execution_report = self._qualify(execution_home_only, root)
            self.assertNotEqual(
                execution_report["qualification"]["execution_bookmaker_status"],
                "QUALIFIED_AS_EXECUTION_BOOKMAKER",
            )

    def test_claim_aggregation_is_order_independent_and_fail_dominant(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("review", encoding="utf-8")

            def add_claim(candidate, claim_id, conclusion):
                template = next(
                    claim
                    for claim in candidate["evidence_claims"]
                    if claim["claim_id"] == self._claim_id("MARKET_SEMANTICS")
                )
                row = dict(template)
                row["claim_id"] = claim_id
                row["reviewer_conclusion"] = conclusion
                candidate["evidence_claims"].append(row)

            statuses = []
            for order in (
                ["missing-claim", "claim-market-semantics-fail"],
                ["claim-market-semantics-fail", "missing-claim"],
            ):
                candidate = self._candidate(evidence)
                add_claim(candidate, "claim-market-semantics-fail", "FAIL")
                candidate["market_semantics_evidence"]["claim_ids"] = order
                statuses.append(
                    self._qualify(candidate, root)["gate_results"][
                        GateId.EXACT_MARKET_SEMANTICS.value
                    ]["effective"]["status"]
                )
            self.assertEqual(statuses, ["FAIL", "FAIL"])

            unknown_and_fail = self._candidate(evidence)
            add_claim(
                unknown_and_fail,
                "claim-market-semantics-unknown",
                "UNKNOWN",
            )
            add_claim(
                unknown_and_fail,
                "claim-market-semantics-fail",
                "FAIL",
            )
            unknown_and_fail["market_semantics_evidence"]["claim_ids"] = [
                "claim-market-semantics-unknown",
                "claim-market-semantics-fail",
            ]
            self.assertEqual(
                self._qualify(unknown_and_fail, root)["gate_results"][
                    GateId.EXACT_MARKET_SEMANTICS.value
                ]["effective"]["status"],
                "FAIL",
            )

            pass_missing = self._candidate(evidence)
            pass_missing["market_semantics_evidence"]["claim_ids"] = [
                self._claim_id("MARKET_SEMANTICS"),
                "missing-claim",
            ]
            self.assertEqual(
                self._qualify(pass_missing, root)["gate_results"][
                    GateId.EXACT_MARKET_SEMANTICS.value
                ]["effective"]["status"],
                "UNKNOWN",
            )

    def test_claim_timestamp_ordering_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "review.txt"
            evidence.write_text("review", encoding="utf-8")

            retrieval_after_review = self._candidate(evidence)
            retrieval_after_review["evidence_claims"][0][
                "retrieval_timestamp"
            ] = "2026-08-01T12:00:01Z"
            with self.assertRaisesRegex(
                QualificationExportError, "retrieval_timestamp"
            ):
                self._qualify(retrieval_after_review, root)

            review_after_candidate = self._candidate(evidence)
            review_after_candidate["evidence_claims"][0][
                "reviewer_checked_at"
            ] = "2026-08-01T12:00:01Z"
            with self.assertRaisesRegex(
                QualificationExportError,
                "candidate evidence_checked_at",
            ):
                self._qualify(review_after_candidate, root)


if __name__ == "__main__":
    unittest.main()
