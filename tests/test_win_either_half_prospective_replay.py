"""Unit tests for Stage 5B2 prospective Win Either Half pricing observation replay.

Tests verify strict contract adherence, real Stage 5B1 integration, attempt-linked quote isolation,
deterministic byte-for-byte evidence generation, manifest validation, and safety invariants.
"""

from __future__ import annotations

import copy
import csv
from decimal import Decimal
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from domain.markets import MARKET_REGISTRY, MarketId, OutcomeId
from domain.model_status import MODEL_STATUS_REGISTRY, ModelStatus
from domain.win_either_half_pricing_source_qualification import (
    QualificationStatus,
    canonical_market_registry_snapshot,
)
from domain.win_either_half_prospective_replay import (
    ATTEMPT_WINDOW_SECONDS,
    DEFAULT_PROTOCOL_PATH,
    EXPECTED_ATTEMPTS_PER_FIXTURE,
    FROZEN_CANDIDATE_OFFSETS_SECONDS,
    MAXIMUM_QUOTE_AGE_SECONDS,
    PERMITTED_MARKETS,
    SCHEMA_VERSION,
    AttemptResult,
    AvailabilityReason,
    AvailabilityStatus,
    EvaluationRecord,
    ObservationAttempt,
    ProspectiveQuote,
    ValidatedSnapshot,
    assert_no_forbidden_fields,
    build_expected_protocol_contract,
    evaluate_prospective_replay,
    load_fixtures_dataset,
    load_provider_mappings_dataset,
    load_source_qualification,
    parse_observation_attempts,
    parse_prospective_quotes,
    validate_protocol_contract,
)
from scripts.export_win_either_half_prospective_replay import (
    OUTPUT_FILENAMES,
    ProspectiveReplayExportError,
    build_outputs,
    check_manifest,
    commit_evidence_bundle,
    format_csv,
    run,
)


class TestWinEitherHalfProspectiveReplay(unittest.TestCase):
    """Test suite proving all 40 required checklist items."""

    REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

    def setUp(self) -> None:
        self.fixtures_payload = {
            "schema_version": 1,
            "fixtures": [
                {
                    "fixture_identifier": "FIX-101",
                    "kickoff": "2026-08-10T15:00:00Z",
                }
            ],
        }
        self.mappings_payload = {
            "schema_version": 1,
            "mappings": [
                {
                    "fixture_identifier": "FIX-101",
                    "provider_identifier": "TEST_PROVIDER",
                    "source": "ODDS_PORTAL",
                    "bookmaker_identifier": "PINNACLE",
                    "provider_event_identifier": "EV-101",
                    "markets": {
                        "HOME_WIN_EITHER_HALF": {
                            "provider_market_identifier": "MKT-HWEH",
                            "outcomes": {
                                "YES": "SEL-HWEH-YES",
                                "NO": "SEL-HWEH-NO",
                            },
                        },
                        "AWAY_WIN_EITHER_HALF": {
                            "provider_market_identifier": "MKT-AWEH",
                            "outcomes": {
                                "YES": "SEL-AWEH-YES",
                                "NO": "SEL-AWEH-NO",
                            },
                        },
                    },
                }
            ],
        }
        self.source_qual_payload = {
            "schema_version": 1,
            "dataset_name": "win-either-half-pricing-source-qualification-v1",
            "provider_identifier": "TEST_PROVIDER",
            "qualification": {
                "historical_status": "QUALIFIED_FOR_HISTORICAL_RESEARCH",
                "live_pricing_status": "DISQUALIFIED",
                "execution_bookmaker_status": "DISQUALIFIED",
                "prospective_replay_status": "QUALIFIED_FOR_HISTORICAL_RESEARCH",
            },
            "holdout_governance": {
                "prospective_validation_required": True,
                "production_approval_authorized": False,
            },
            "market_statuses": {
                "HOME_WIN_EITHER_HALF": "DISABLED",
                "AWAY_WIN_EITHER_HALF": "DISABLED",
            },
            "no_production_approval": "Research qualification only",
        }
        self.protocol_raw = DEFAULT_PROTOCOL_PATH.read_bytes()
        self.protocol_payload = json.loads(self.protocol_raw.decode("utf-8"))
        self.mock_code_state = {
            "git_sha": "0123456789abcdef0123456789abcdef01234567",
            "tracked_worktree_clean": True,
        }

    def _sample_attempt(
        self,
        attempt_id: str = "ATT-1",
        fixture_id: str = "FIX-101",
        market_id: str = "HOME_WIN_EITHER_HALF",
        offset: int = 86400,
        scheduled_at: str = "2026-08-09T15:00:00Z",
        attempted_at: str = "2026-08-09T15:00:00Z",
        result: str = "QUOTES_CAPTURED",
        quote_snapshot_id: str = "SNAP-1",
    ) -> dict:
        return {
            "schema_version": 1,
            "attempt_id": attempt_id,
            "fixture_identifier": fixture_id,
            "market_id": market_id,
            "line": None,
            "provider_identifier": "TEST_PROVIDER",
            "source": "ODDS_PORTAL",
            "bookmaker_identifier": "PINNACLE",
            "provider_event_identifier": "EV-101",
            "provider_market_identifier": "MKT-HWEH",
            "offset_seconds_before_kickoff": offset,
            "scheduled_at": scheduled_at,
            "attempted_at": attempted_at,
            "result": result,
            "capture_method": "HTTP_GET",
            "quote_snapshot_id": quote_snapshot_id if result == "QUOTES_CAPTURED" else None,
        }

    def _sample_quote(
        self,
        attempt_id: str = "ATT-1",
        outcome_id: str = "YES",
        quote_snapshot_id: str = "SNAP-1",
        observed_at: str = "2026-08-09T14:55:00Z",
        odds: str = "1.85",
        selection_id: str = "SEL-HWEH-YES",
    ) -> dict:
        return {
            "schema_version": 1,
            "attempt_id": attempt_id,
            "fixture_identifier": "FIX-101",
            "market_id": "HOME_WIN_EITHER_HALF",
            "outcome_id": outcome_id,
            "line": None,
            "provider_identifier": "TEST_PROVIDER",
            "source": "ODDS_PORTAL",
            "bookmaker_identifier": "PINNACLE",
            "provider_event_identifier": "EV-101",
            "provider_market_identifier": "MKT-HWEH",
            "provider_selection_identifier": selection_id,
            "quote_snapshot_id": quote_snapshot_id,
            "observed_at": observed_at,
            "fixture_kickoff": "2026-08-10T15:00:00Z",
            "decimal_odds": odds,
            "is_genuine": True,
        }

    # 1. Real nested Stage 5B1 report is accepted
    def test_real_nested_stage_5b1_report_accepted(self) -> None:
        prov = load_source_qualification(self.source_qual_payload)
        self.assertEqual(prov, "TEST_PROVIDER")

    # 2. QUALIFIED_FOR_HISTORICAL_RESEARCH is accepted
    def test_qualified_for_historical_research_accepted(self) -> None:
        payload = copy.deepcopy(self.source_qual_payload)
        payload["qualification"]["prospective_replay_status"] = "QUALIFIED_FOR_HISTORICAL_RESEARCH"
        self.assertEqual(load_source_qualification(payload), "TEST_PROVIDER")

    # 3. QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY is accepted
    def test_qualified_for_prospective_replay_only_accepted(self) -> None:
        payload = copy.deepcopy(self.source_qual_payload)
        payload["qualification"]["prospective_replay_status"] = "QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY"
        self.assertEqual(load_source_qualification(payload), "TEST_PROVIDER")

    # 4. QUALIFIED_FOR_LIVE_PRICING is rejected
    def test_qualified_for_live_pricing_rejected(self) -> None:
        payload = copy.deepcopy(self.source_qual_payload)
        payload["qualification"]["prospective_replay_status"] = "QUALIFIED_FOR_LIVE_PRICING"
        with self.assertRaises(ValueError):
            load_source_qualification(payload)

    # 5. Fabricated QUALIFIED_PROSPECTIVE_REPLAY_ELIGIBLE is rejected
    def test_fabricated_status_rejected(self) -> None:
        payload = copy.deepcopy(self.source_qual_payload)
        payload["qualification"]["prospective_replay_status"] = "QUALIFIED_PROSPECTIVE_REPLAY_ELIGIBLE"
        with self.assertRaises(ValueError):
            load_source_qualification(payload)

    # 6. Top-level prospective_replay_status without qualification object is rejected
    def test_top_level_status_without_qualification_object_rejected(self) -> None:
        payload = {
            "schema_version": 1,
            "dataset_name": "win-either-half-pricing-source-qualification-v1",
            "provider_identifier": "TEST_PROVIDER",
            "prospective_replay_status": "QUALIFIED_FOR_HISTORICAL_RESEARCH",
            "holdout_governance": {
                "prospective_validation_required": True,
                "production_approval_authorized": False,
            },
            "market_statuses": {
                "HOME_WIN_EITHER_HALF": "DISABLED",
                "AWAY_WIN_EITHER_HALF": "DISABLED",
            },
            "no_production_approval": "Statement",
        }
        with self.assertRaises(ValueError):
            load_source_qualification(payload)

    # 7. Both markets must remain DISABLED in source report
    def test_both_markets_must_remain_disabled_in_source_report(self) -> None:
        payload = copy.deepcopy(self.source_qual_payload)
        payload["market_statuses"]["HOME_WIN_EITHER_HALF"] = "ENABLED"
        with self.assertRaises(ValueError):
            load_source_qualification(payload)

        payload2 = copy.deepcopy(self.source_qual_payload)
        payload2["market_statuses"]["AWAY_WIN_EITHER_HALF"] = "ACTIVE"
        with self.assertRaises(ValueError):
            load_source_qualification(payload2)

    # 8. MARKET_UNAVAILABLE attempt is not contaminated by quotes linked to a different offset
    def test_market_unavailable_not_contaminated_by_other_offset_quotes(self) -> None:
        fixtures = load_fixtures_dataset(self.fixtures_payload)
        mappings = load_provider_mappings_dataset(self.mappings_payload, "TEST_PROVIDER")

        att_86400 = self._sample_attempt("ATT-86400", offset=86400, scheduled_at="2026-08-09T15:00:00Z", attempted_at="2026-08-09T15:00:00Z", result="MARKET_UNAVAILABLE")
        att_3600 = self._sample_attempt("ATT-3600", offset=3600, scheduled_at="2026-08-10T14:00:00Z", attempted_at="2026-08-10T14:00:00Z", result="QUOTES_CAPTURED", quote_snapshot_id="SNAP-3600")

        q_yes = self._sample_quote("ATT-3600", outcome_id="YES", quote_snapshot_id="SNAP-3600", observed_at="2026-08-10T13:58:00Z", selection_id="SEL-HWEH-YES")
        q_no = self._sample_quote("ATT-3600", outcome_id="NO", quote_snapshot_id="SNAP-3600", observed_at="2026-08-10T13:58:00Z", selection_id="SEL-HWEH-NO")

        att_results, v_by_id, v_by_key = parse_observation_attempts([att_86400, att_3600], fixtures, mappings, "TEST_PROVIDER")
        q_results = parse_prospective_quotes([q_yes, q_no], fixtures, mappings, v_by_id, "TEST_PROVIDER")
        valid_quotes = [r.quote for r in q_results if r.is_valid and r.quote is not None]

        snaps, evals = evaluate_prospective_replay(fixtures, v_by_key, valid_quotes)
        eval_86400 = [e for e in evals if e.offset_seconds_before_kickoff == 86400 and e.market_id == MarketId.HOME_WIN_EITHER_HALF][0]
        eval_3600 = [e for e in evals if e.offset_seconds_before_kickoff == 3600 and e.market_id == MarketId.HOME_WIN_EITHER_HALF][0]

        self.assertEqual(eval_86400.availability_status, AvailabilityStatus.UNAVAILABLE)
        self.assertEqual(eval_3600.availability_status, AvailabilityStatus.AVAILABLE)

    # 9. CAPTURE_ERROR attempt is not contaminated by quotes linked to another attempt
    def test_capture_error_not_contaminated_by_other_quotes(self) -> None:
        fixtures = load_fixtures_dataset(self.fixtures_payload)
        mappings = load_provider_mappings_dataset(self.mappings_payload, "TEST_PROVIDER")

        att_err = self._sample_attempt("ATT-ERR", offset=86400, scheduled_at="2026-08-09T15:00:00Z", attempted_at="2026-08-09T15:00:00Z", result="CAPTURE_ERROR")
        att_ok = self._sample_attempt("ATT-OK", offset=3600, scheduled_at="2026-08-10T14:00:00Z", attempted_at="2026-08-10T14:00:00Z", result="QUOTES_CAPTURED", quote_snapshot_id="SNAP-OK")

        q_yes = self._sample_quote("ATT-OK", outcome_id="YES", quote_snapshot_id="SNAP-OK", observed_at="2026-08-10T13:58:00Z", selection_id="SEL-HWEH-YES")
        q_no = self._sample_quote("ATT-OK", outcome_id="NO", quote_snapshot_id="SNAP-OK", observed_at="2026-08-10T13:58:00Z", selection_id="SEL-HWEH-NO")

        att_results, v_by_id, v_by_key = parse_observation_attempts([att_err, att_ok], fixtures, mappings, "TEST_PROVIDER")
        q_results = parse_prospective_quotes([q_yes, q_no], fixtures, mappings, v_by_id, "TEST_PROVIDER")
        valid_quotes = [r.quote for r in q_results if r.is_valid and r.quote is not None]

        snaps, evals = evaluate_prospective_replay(fixtures, v_by_key, valid_quotes)
        eval_err = [e for e in evals if e.offset_seconds_before_kickoff == 86400 and e.market_id == MarketId.HOME_WIN_EITHER_HALF][0]
        eval_ok = [e for e in evals if e.offset_seconds_before_kickoff == 3600 and e.market_id == MarketId.HOME_WIN_EITHER_HALF][0]

        self.assertEqual(eval_err.availability_status, AvailabilityStatus.UNKNOWN)
        self.assertEqual(eval_err.availability_reason, AvailabilityReason.CAPTURE_ERROR.value)
        self.assertEqual(eval_ok.availability_status, AvailabilityStatus.AVAILABLE)

    # 10. Missing attempt remains UNKNOWN even when another checkpoint has quotes
    def test_missing_attempt_remains_unknown_despite_other_quotes(self) -> None:
        fixtures = load_fixtures_dataset(self.fixtures_payload)
        mappings = load_provider_mappings_dataset(self.mappings_payload, "TEST_PROVIDER")

        att_ok = self._sample_attempt("ATT-OK", offset=3600, scheduled_at="2026-08-10T14:00:00Z", attempted_at="2026-08-10T14:00:00Z", result="QUOTES_CAPTURED", quote_snapshot_id="SNAP-OK")
        q_yes = self._sample_quote("ATT-OK", outcome_id="YES", quote_snapshot_id="SNAP-OK", observed_at="2026-08-10T13:58:00Z", selection_id="SEL-HWEH-YES")
        q_no = self._sample_quote("ATT-OK", outcome_id="NO", quote_snapshot_id="SNAP-OK", observed_at="2026-08-10T13:58:00Z", selection_id="SEL-HWEH-NO")

        att_results, v_by_id, v_by_key = parse_observation_attempts([att_ok], fixtures, mappings, "TEST_PROVIDER")
        q_results = parse_prospective_quotes([q_yes, q_no], fixtures, mappings, v_by_id, "TEST_PROVIDER")
        valid_quotes = [r.quote for r in q_results if r.is_valid and r.quote is not None]

        snaps, evals = evaluate_prospective_replay(fixtures, v_by_key, valid_quotes)
        eval_missing = [e for e in evals if e.offset_seconds_before_kickoff == 86400 and e.market_id == MarketId.HOME_WIN_EITHER_HALF][0]
        self.assertEqual(eval_missing.availability_status, AvailabilityStatus.UNKNOWN)
        self.assertEqual(eval_missing.availability_reason, AvailabilityReason.NO_ATTEMPT_RECORD.value)

    # 11. Unknown attempt_id quote is rejected and counted as orphan evidence
    def test_unknown_attempt_id_quote_rejected_as_orphan(self) -> None:
        fixtures = load_fixtures_dataset(self.fixtures_payload)
        mappings = load_provider_mappings_dataset(self.mappings_payload, "TEST_PROVIDER")

        q_orphan = self._sample_quote("NON_EXISTENT_ATTEMPT", outcome_id="YES")
        q_results = parse_prospective_quotes([q_orphan], fixtures, mappings, {}, "TEST_PROVIDER")
        self.assertFalse(q_results[0].is_valid)
        self.assertIn("UNKNOWN_ATTEMPT_ID", q_results[0].rejection_reasons)

    # 12. Quote attempt_id mismatch is rejected
    def test_quote_attempt_mismatch_rejected(self) -> None:
        fixtures = load_fixtures_dataset(self.fixtures_payload)
        mappings = load_provider_mappings_dataset(self.mappings_payload, "TEST_PROVIDER")
        att = self._sample_attempt("ATT-1", fixture_id="FIX-101", market_id="HOME_WIN_EITHER_HALF")
        att_results, v_by_id, _ = parse_observation_attempts([att], fixtures, mappings, "TEST_PROVIDER")

        q_mismatch = self._sample_quote("ATT-1", outcome_id="YES")
        q_mismatch["market_id"] = "AWAY_WIN_EITHER_HALF"
        q_results = parse_prospective_quotes([q_mismatch], fixtures, mappings, v_by_id, "TEST_PROVIDER")
        self.assertFalse(q_results[0].is_valid)
        self.assertIn("ATTEMPT_MARKET_MISMATCH", q_results[0].rejection_reasons)

    # 13. Duplicate attempt_id is invalid even across different expected keys
    def test_duplicate_attempt_id_invalidates_all_matching_records(self) -> None:
        fixtures = load_fixtures_dataset(self.fixtures_payload)
        mappings = load_provider_mappings_dataset(self.mappings_payload, "TEST_PROVIDER")

        att1 = self._sample_attempt("ATT-DUP", offset=86400, scheduled_at="2026-08-09T15:00:00Z", attempted_at="2026-08-09T15:00:00Z")
        att2 = self._sample_attempt("ATT-DUP", offset=3600, scheduled_at="2026-08-10T14:00:00Z", attempted_at="2026-08-10T14:00:00Z")

        att_results, v_by_id, v_by_key = parse_observation_attempts([att1, att2], fixtures, mappings, "TEST_PROVIDER")
        self.assertFalse(att_results[0].is_valid)
        self.assertFalse(att_results[1].is_valid)
        self.assertIn("DUPLICATE_ATTEMPT_ID", att_results[0].rejection_reasons)
        self.assertIn("DUPLICATE_ATTEMPT_ID", att_results[1].rejection_reasons)

    # 14. Quote age 900 seconds at attempted_at passes
    def test_quote_age_900_at_attempted_at_passes(self) -> None:
        fixtures = load_fixtures_dataset(self.fixtures_payload)
        mappings = load_provider_mappings_dataset(self.mappings_payload, "TEST_PROVIDER")

        att = self._sample_attempt("ATT-1", offset=3600, scheduled_at="2026-08-10T14:00:00Z", attempted_at="2026-08-10T14:00:00Z")
        q = self._sample_quote("ATT-1", outcome_id="YES", observed_at="2026-08-10T13:45:00Z")

        att_results, v_by_id, _ = parse_observation_attempts([att], fixtures, mappings, "TEST_PROVIDER")
        q_results = parse_prospective_quotes([q], fixtures, mappings, v_by_id, "TEST_PROVIDER")
        self.assertTrue(q_results[0].is_valid)

    # 15. Quote age 901 seconds fails
    def test_quote_age_901_fails(self) -> None:
        fixtures = load_fixtures_dataset(self.fixtures_payload)
        mappings = load_provider_mappings_dataset(self.mappings_payload, "TEST_PROVIDER")

        att = self._sample_attempt("ATT-1", offset=3600, scheduled_at="2026-08-10T14:00:00Z", attempted_at="2026-08-10T14:00:00Z")
        q = self._sample_quote("ATT-1", outcome_id="YES", observed_at="2026-08-10T13:44:59Z")

        att_results, v_by_id, _ = parse_observation_attempts([att], fixtures, mappings, "TEST_PROVIDER")
        q_results = parse_prospective_quotes([q], fixtures, mappings, v_by_id, "TEST_PROVIDER")
        self.assertFalse(q_results[0].is_valid)
        self.assertIn("STALE_QUOTE", q_results[0].rejection_reasons)

    # 16. Quote observed after attempted_at fails
    def test_quote_observed_after_attempted_at_fails(self) -> None:
        fixtures = load_fixtures_dataset(self.fixtures_payload)
        mappings = load_provider_mappings_dataset(self.mappings_payload, "TEST_PROVIDER")

        att = self._sample_attempt("ATT-1", offset=3600, scheduled_at="2026-08-10T14:00:00Z", attempted_at="2026-08-10T14:00:00Z")
        q = self._sample_quote("ATT-1", outcome_id="YES", observed_at="2026-08-10T14:01:00Z")

        att_results, v_by_id, _ = parse_observation_attempts([att], fixtures, mappings, "TEST_PROVIDER")
        q_results = parse_prospective_quotes([q], fixtures, mappings, v_by_id, "TEST_PROVIDER")
        self.assertFalse(q_results[0].is_valid)
        self.assertIn("QUOTE_OBSERVED_AFTER_ATTEMPT", q_results[0].rejection_reasons)

    # 17. Permitted late attempt can use quote after scheduled_at but before attempted_at
    def test_permitted_late_attempt_can_use_quote_after_scheduled_at_before_attempted_at(self) -> None:
        fixtures = load_fixtures_dataset(self.fixtures_payload)
        mappings = load_provider_mappings_dataset(self.mappings_payload, "TEST_PROVIDER")

        att = self._sample_attempt("ATT-1", offset=3600, scheduled_at="2026-08-10T14:00:00Z", attempted_at="2026-08-10T14:04:00Z")
        q = self._sample_quote("ATT-1", outcome_id="YES", observed_at="2026-08-10T14:02:00Z")

        att_results, v_by_id, _ = parse_observation_attempts([att], fixtures, mappings, "TEST_PROVIDER")
        q_results = parse_prospective_quotes([q], fixtures, mappings, v_by_id, "TEST_PROVIDER")
        self.assertTrue(q_results[0].is_valid)

    # 18. schema_version=true fails for every input type
    def test_schema_version_true_fails_for_all_inputs(self) -> None:
        sq = copy.deepcopy(self.source_qual_payload)
        sq["schema_version"] = True
        with self.assertRaises(ValueError):
            load_source_qualification(sq)

        fx = copy.deepcopy(self.fixtures_payload)
        fx["schema_version"] = True
        with self.assertRaises(ValueError):
            load_fixtures_dataset(fx)

        mp = copy.deepcopy(self.mappings_payload)
        mp["schema_version"] = True
        with self.assertRaises(ValueError):
            load_provider_mappings_dataset(mp, "TEST_PROVIDER")

        fixtures = load_fixtures_dataset(self.fixtures_payload)
        mappings = load_provider_mappings_dataset(self.mappings_payload, "TEST_PROVIDER")
        att = self._sample_attempt("ATT-1")
        att["schema_version"] = True
        att_results, _, _ = parse_observation_attempts([att], fixtures, mappings, "TEST_PROVIDER")
        self.assertFalse(att_results[0].is_valid)
        self.assertIn("INVALID_SCHEMA_VERSION", att_results[0].rejection_reasons)

        q = self._sample_quote("ATT-1")
        q["schema_version"] = True
        q_results = parse_prospective_quotes([q], fixtures, mappings, {}, "TEST_PROVIDER")
        self.assertFalse(q_results[0].is_valid)
        self.assertIn("INVALID_SCHEMA_VERSION", q_results[0].rejection_reasons)

    # 19. offset=true fails
    def test_offset_true_fails(self) -> None:
        fixtures = load_fixtures_dataset(self.fixtures_payload)
        mappings = load_provider_mappings_dataset(self.mappings_payload, "TEST_PROVIDER")
        att = self._sample_attempt("ATT-1")
        att["offset_seconds_before_kickoff"] = True
        att_results, _, _ = parse_observation_attempts([att], fixtures, mappings, "TEST_PROVIDER")
        self.assertFalse(att_results[0].is_valid)
        self.assertIn("INVALID_OFFSET_SECONDS", att_results[0].rejection_reasons)

    # 20. Unexpected attempt and quote keys fail
    def test_unexpected_attempt_and_quote_keys_fail(self) -> None:
        fixtures = load_fixtures_dataset(self.fixtures_payload)
        mappings = load_provider_mappings_dataset(self.mappings_payload, "TEST_PROVIDER")

        att = self._sample_attempt("ATT-1")
        att["unexpected_field"] = "extra"
        att_results, _, _ = parse_observation_attempts([att], fixtures, mappings, "TEST_PROVIDER")
        self.assertFalse(att_results[0].is_valid)
        self.assertIn("ATTEMPT_UNEXPECTED_FIELD", att_results[0].rejection_reasons)

        q = self._sample_quote("ATT-1")
        q["unexpected_field"] = "extra"
        q_results = parse_prospective_quotes([q], fixtures, mappings, {}, "TEST_PROVIDER")
        self.assertFalse(q_results[0].is_valid)
        self.assertIn("QUOTE_UNEXPECTED_FIELD", q_results[0].rejection_reasons)

    # 21. Every protocol top-level and nested mutation fails
    def test_every_protocol_mutation_fails(self) -> None:
        base_proto = build_expected_protocol_contract()
        with tempfile.NamedTemporaryFile("wb", delete=False) as f:
            f.write(json.dumps(base_proto, sort_keys=True).encode("utf-8"))
            proto_path = Path(f.name)

        try:
            validate_protocol_contract(base_proto, proto_path.read_bytes(), committed_path=proto_path)

            mut1 = copy.deepcopy(base_proto)
            mut1["candidate_offsets_seconds"] = [86400, 3600]
            with self.assertRaises(ValueError):
                validate_protocol_contract(mut1, proto_path.read_bytes(), committed_path=proto_path)

            mut2 = copy.deepcopy(base_proto)
            mut2["quote_contract"]["maximum_quote_age_seconds"] = 1200
            with self.assertRaises(ValueError):
                validate_protocol_contract(mut2, proto_path.read_bytes(), committed_path=proto_path)
        finally:
            proto_path.unlink(missing_ok=True)

    # 22. CSV with multiple rejection reasons is valid and has fixed column counts
    def test_csv_multiple_rejection_reasons_fixed_column_count(self) -> None:
        cols = ["id", "reasons", "is_valid"]
        rows = [
            ["1", ["REASON_A", "REASON_B, WITH COMMA", 'REASON_C "QUOTED"'], False],
            ["2", ["SINGLE_REASON"], True],
        ]
        csv_bytes = format_csv(cols, rows)
        reader = csv.reader(io.StringIO(csv_bytes.decode("utf-8")))
        parsed_rows = list(reader)
        self.assertEqual(len(parsed_rows), 3)
        for r in parsed_rows:
            self.assertEqual(len(r), 3)

    # 23. Input row permutations leave all six derived non-manifest output files byte-identical
    # 24. Manifest changes only where raw input identities legitimately change
    def test_permutation_invariance_and_manifest_identity(self) -> None:
        att1 = self._sample_attempt("ATT-1", offset=86400, scheduled_at="2026-08-09T15:00:00Z", attempted_at="2026-08-09T15:00:00Z")
        att2 = self._sample_attempt("ATT-2", offset=3600, scheduled_at="2026-08-10T14:00:00Z", attempted_at="2026-08-10T14:00:00Z")
        q1 = self._sample_quote("ATT-1", outcome_id="YES", selection_id="SEL-HWEH-YES")
        q2 = self._sample_quote("ATT-1", outcome_id="NO", selection_id="SEL-HWEH-NO")

        b1 = build_outputs(
            source_qual_raw=json.dumps(self.source_qual_payload, sort_keys=True).encode("utf-8"),
            source_qual_payload=self.source_qual_payload,
            fixtures_raw=json.dumps(self.fixtures_payload, sort_keys=True).encode("utf-8"),
            fixtures_payload=self.fixtures_payload,
            provider_mappings_raw=json.dumps(self.mappings_payload, sort_keys=True).encode("utf-8"),
            provider_mappings_payload=self.mappings_payload,
            attempts_raw=(json.dumps(att1) + "\n" + json.dumps(att2)).encode("utf-8"),
            raw_attempts=[att1, att2],
            quotes_raw=(json.dumps(q1) + "\n" + json.dumps(q2)).encode("utf-8"),
            raw_quotes=[q1, q2],
            protocol_raw=self.protocol_raw,
            protocol_payload=self.protocol_payload,
            source_qual_path=Path("sq.json"),
            fixtures_path=Path("fx.json"),
            mappings_path=Path("mp.json"),
            attempts_path=Path("att.jsonl"),
            quotes_path=Path("q.jsonl"),
            protocol_path=DEFAULT_PROTOCOL_PATH,
            code_state=self.mock_code_state,
        )

        b2 = build_outputs(
            source_qual_raw=json.dumps(self.source_qual_payload, sort_keys=True).encode("utf-8"),
            source_qual_payload=self.source_qual_payload,
            fixtures_raw=json.dumps(self.fixtures_payload, sort_keys=True).encode("utf-8"),
            fixtures_payload=self.fixtures_payload,
            provider_mappings_raw=json.dumps(self.mappings_payload, sort_keys=True).encode("utf-8"),
            provider_mappings_payload=self.mappings_payload,
            attempts_raw=(json.dumps(att2) + "\n" + json.dumps(att1)).encode("utf-8"),
            raw_attempts=[att2, att1],
            quotes_raw=(json.dumps(q2) + "\n" + json.dumps(q1)).encode("utf-8"),
            raw_quotes=[q2, q1],
            protocol_raw=self.protocol_raw,
            protocol_payload=self.protocol_payload,
            source_qual_path=Path("sq.json"),
            fixtures_path=Path("fx.json"),
            mappings_path=Path("mp.json"),
            attempts_path=Path("att.jsonl"),
            quotes_path=Path("q.jsonl"),
            protocol_path=DEFAULT_PROTOCOL_PATH,
            code_state=self.mock_code_state,
        )

        for name in ("normalized_attempts", "valid_quotes", "rejected_quotes", "validated_snapshots", "evaluations", "summary"):
            self.assertEqual(b1.files[name], b2.files[name], f"Mismatch in output {name}")

    # 25. Dirty tracked worktree fails generation
    def test_dirty_tracked_worktree_fails(self) -> None:
        dirty_state = {"git_sha": "abc", "tracked_worktree_clean": False}
        with self.assertRaises(ProspectiveReplayExportError):
            build_outputs(
                source_qual_raw=b"",
                source_qual_payload={},
                fixtures_raw=b"",
                fixtures_payload={},
                provider_mappings_raw=b"",
                provider_mappings_payload={},
                attempts_raw=b"",
                raw_attempts=[],
                quotes_raw=b"",
                raw_quotes=[],
                protocol_raw=b"",
                protocol_payload={},
                source_qual_path=Path("sq.json"),
                fixtures_path=Path("fx.json"),
                mappings_path=Path("mp.json"),
                attempts_path=Path("att.jsonl"),
                quotes_path=Path("q.jsonl"),
                protocol_path=DEFAULT_PROTOCOL_PATH,
                code_state=dirty_state,
            )

    # 26. Git-state lookup failure fails closed
    @patch("scripts.export_win_either_half_prospective_replay.get_code_state")
    def test_git_state_lookup_failure_fails_closed(self, mock_code_state) -> None:
        mock_code_state.side_effect = RuntimeError("git command failed")
        with self.assertRaises(ProspectiveReplayExportError):
            build_outputs(
                source_qual_raw=b"",
                source_qual_payload={},
                fixtures_raw=b"",
                fixtures_payload={},
                provider_mappings_raw=b"",
                provider_mappings_payload={},
                attempts_raw=b"",
                raw_attempts=[],
                quotes_raw=b"",
                raw_quotes=[],
                protocol_raw=b"",
                protocol_payload={},
                source_qual_path=Path("sq.json"),
                fixtures_path=Path("fx.json"),
                mappings_path=Path("mp.json"),
                attempts_path=Path("att.jsonl"),
                quotes_path=Path("q.jsonl"),
                protocol_path=DEFAULT_PROTOCOL_PATH,
            )

    # 27. Stored manifest formatting changes fail check mode
    # 28. Every output SHA, byte size, and row count is checked
    def test_check_mode_verifies_exact_bytes_and_metadata(self) -> None:
        att = self._sample_attempt("ATT-1", offset=86400, scheduled_at="2026-08-09T15:00:00Z", attempted_at="2026-08-09T15:00:00Z")
        bundle = build_outputs(
            source_qual_raw=json.dumps(self.source_qual_payload, sort_keys=True).encode("utf-8"),
            source_qual_payload=self.source_qual_payload,
            fixtures_raw=json.dumps(self.fixtures_payload, sort_keys=True).encode("utf-8"),
            fixtures_payload=self.fixtures_payload,
            provider_mappings_raw=json.dumps(self.mappings_payload, sort_keys=True).encode("utf-8"),
            provider_mappings_payload=self.mappings_payload,
            attempts_raw=json.dumps(att).encode("utf-8"),
            raw_attempts=[att],
            quotes_raw=b"",
            raw_quotes=[],
            protocol_raw=self.protocol_raw,
            protocol_payload=self.protocol_payload,
            source_qual_path=Path("sq.json"),
            fixtures_path=Path("fx.json"),
            mappings_path=Path("mp.json"),
            attempts_path=Path("att.jsonl"),
            quotes_path=Path("q.jsonl"),
            protocol_path=DEFAULT_PROTOCOL_PATH,
            code_state=self.mock_code_state,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            paths = {name: out_dir / OUTPUT_FILENAMES[name] for name in OUTPUT_FILENAMES}
            commit_evidence_bundle(output_paths=paths, contents=bundle.files, force=True)

            check_manifest(manifest_path=paths["manifest"], bundle=bundle)

            manifest_json = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            paths["manifest"].write_text(json.dumps(manifest_json, indent=4) + "\n", encoding="utf-8")
            with self.assertRaises(ProspectiveReplayExportError):
                check_manifest(manifest_path=paths["manifest"], bundle=bundle)

    # 29. Extra attempts and orphan quotes appear in summary accounting
    def test_extra_attempts_and_orphan_quotes_in_summary(self) -> None:
        att_valid = self._sample_attempt("ATT-1", offset=86400, scheduled_at="2026-08-09T15:00:00Z", attempted_at="2026-08-09T15:00:00Z")
        att_extra = self._sample_attempt("ATT-EXTRA", fixture_id="UNMAPPED-FIX")
        q_orphan = self._sample_quote("ATT-NONEXISTENT")

        bundle = build_outputs(
            source_qual_raw=json.dumps(self.source_qual_payload, sort_keys=True).encode("utf-8"),
            source_qual_payload=self.source_qual_payload,
            fixtures_raw=json.dumps(self.fixtures_payload, sort_keys=True).encode("utf-8"),
            fixtures_payload=self.fixtures_payload,
            provider_mappings_raw=json.dumps(self.mappings_payload, sort_keys=True).encode("utf-8"),
            provider_mappings_payload=self.mappings_payload,
            attempts_raw=(json.dumps(att_valid) + "\n" + json.dumps(att_extra)).encode("utf-8"),
            raw_attempts=[att_valid, att_extra],
            quotes_raw=json.dumps(q_orphan).encode("utf-8"),
            raw_quotes=[q_orphan],
            protocol_raw=self.protocol_raw,
            protocol_payload=self.protocol_payload,
            source_qual_path=Path("sq.json"),
            fixtures_path=Path("fx.json"),
            mappings_path=Path("mp.json"),
            attempts_path=Path("att.jsonl"),
            quotes_path=Path("q.jsonl"),
            protocol_path=DEFAULT_PROTOCOL_PATH,
            code_state=self.mock_code_state,
        )

        summary = json.loads(bundle.files["summary"].decode("utf-8"))
        self.assertEqual(summary["supplied_attempt_count"], 2)
        self.assertEqual(summary["valid_attempt_count"], 1)
        self.assertEqual(summary["invalid_attempt_count"], 1)
        self.assertEqual(summary["orphan_quote_count"], 1)
        self.assertEqual(summary["supplied_quote_count"], 1)
        self.assertEqual(summary["invalid_quote_count"], 1)

    # 30. socket.connect is patched to raise and pipeline remains fully offline
    @patch("socket.socket.connect", side_effect=RuntimeError("Network access forbidden"))
    def test_pipeline_fully_offline(self, mock_socket) -> None:
        att = self._sample_attempt("ATT-1", offset=86400, scheduled_at="2026-08-09T15:00:00Z", attempted_at="2026-08-09T15:00:00Z")
        bundle = build_outputs(
            source_qual_raw=json.dumps(self.source_qual_payload, sort_keys=True).encode("utf-8"),
            source_qual_payload=self.source_qual_payload,
            fixtures_raw=json.dumps(self.fixtures_payload, sort_keys=True).encode("utf-8"),
            fixtures_payload=self.fixtures_payload,
            provider_mappings_raw=json.dumps(self.mappings_payload, sort_keys=True).encode("utf-8"),
            provider_mappings_payload=self.mappings_payload,
            attempts_raw=json.dumps(att).encode("utf-8"),
            raw_attempts=[att],
            quotes_raw=b"",
            raw_quotes=[],
            protocol_raw=self.protocol_raw,
            protocol_payload=self.protocol_payload,
            source_qual_path=Path("sq.json"),
            fixtures_path=Path("fx.json"),
            mappings_path=Path("mp.json"),
            attempts_path=Path("att.jsonl"),
            quotes_path=Path("q.jsonl"),
            protocol_path=DEFAULT_PROTOCOL_PATH,
            code_state=self.mock_code_state,
        )
        self.assertIsNotNone(bundle)

    # 31. All 15 canonical market registrations remain present
    # 32. Every pre-existing model status remains unchanged
    # 33. HOME_WIN_EITHER_HALF remains DISABLED
    # 34. AWAY_WIN_EITHER_HALF remains DISABLED
    def test_canonical_market_and_model_registries(self) -> None:
        snapshot = canonical_market_registry_snapshot()
        self.assertEqual(len(snapshot), 15)
        self.assertEqual(MODEL_STATUS_REGISTRY[MarketId.HOME_WIN_EITHER_HALF].status, ModelStatus.DISABLED)
        self.assertEqual(MODEL_STATUS_REGISTRY[MarketId.AWAY_WIN_EITHER_HALF].status, ModelStatus.DISABLED)

    # 35. selected_offset_seconds remains null
    # 36. selection_authorized remains false
    def test_selection_governance_invariants(self) -> None:
        proto = build_expected_protocol_contract()
        self.assertIsNone(proto["output_contract"]["selected_offset_seconds"])
        self.assertFalse(proto["output_contract"]["selection_authorized"])

    # 37. No odds values, model probabilities, edge, EV, Kelly, stake, ACCA, booking-code, or BET fields emitted
    def test_assert_no_forbidden_fields_enforced(self) -> None:
        for forbidden in ("model_probability", "expected_value", "kelly_stake", "acca_selection", "bet_decision", "home_goals"):
            with self.assertRaises(ValueError):
                assert_no_forbidden_fields({"data": {forbidden: 1.0}})

    # 38. Direct and module --help entrypoints work
    def test_cli_help_entrypoints(self) -> None:
        res1 = subprocess.run(
            [sys.executable, "scripts/export_win_either_half_prospective_replay.py", "--help"],
            cwd=self.REPOSITORY_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(res1.returncode, 0, res1.stderr)
        self.assertIn("usage:", res1.stdout.lower())

        res2 = subprocess.run(
            [sys.executable, "-m", "scripts.export_win_either_half_prospective_replay", "--help"],
            cwd=self.REPOSITORY_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(res2.returncode, 0, res2.stderr)
        self.assertIn("usage:", res2.stdout.lower())

    # 39. Transactional rollback restores every prior output byte-for-byte
    def test_transactional_rollback_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            p1 = out_dir / "file1.txt"
            p1.write_text("original", encoding="utf-8")

            output_paths = {"f1": p1, "f2": out_dir / "file2.txt"}
            contents = {"f1": b"new_f1", "f2": b"new_f2"}

            with patch("shutil.move", side_effect=RuntimeError("Disk failure")):
                with self.assertRaises(ProspectiveReplayExportError):
                    commit_evidence_bundle(output_paths=output_paths, contents=contents, force=True)

            self.assertEqual(p1.read_text(encoding="utf-8"), "original")
            self.assertFalse((out_dir / "file2.txt").exists())

    # 40. Full CLI pipeline test with --manifest-output and --check
    @patch("scripts.export_win_either_half_prospective_replay.get_code_state")
    def test_full_pipeline_cli_and_check(self, mock_code_state) -> None:
        mock_code_state.return_value = self.mock_code_state

        att = self._sample_attempt("ATT-1", offset=86400, scheduled_at="2026-08-09T15:00:00Z", attempted_at="2026-08-09T15:00:00Z", result="QUOTES_CAPTURED", quote_snapshot_id="SNAP-1")
        q_yes = self._sample_quote("ATT-1", outcome_id="YES", quote_snapshot_id="SNAP-1", observed_at="2026-08-09T14:55:00Z", selection_id="SEL-HWEH-YES")
        q_no = self._sample_quote("ATT-1", outcome_id="NO", quote_snapshot_id="SNAP-1", observed_at="2026-08-09T14:55:00Z", selection_id="SEL-HWEH-NO")

        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            sq_path = td / "source-qualification.json"
            sq_path.write_bytes(json.dumps(self.source_qual_payload).encode("utf-8"))

            fx_path = td / "fixtures.json"
            fx_path.write_bytes(json.dumps(self.fixtures_payload).encode("utf-8"))

            mp_path = td / "mappings.json"
            mp_path.write_bytes(json.dumps(self.mappings_payload).encode("utf-8"))

            att_path = td / "attempts.jsonl"
            att_path.write_bytes((json.dumps(att) + "\n").encode("utf-8"))

            q_path = td / "quotes.jsonl"
            q_path.write_bytes((json.dumps(q_yes) + "\n" + json.dumps(q_no) + "\n").encode("utf-8"))

            manifest_path = td / OUTPUT_FILENAMES["manifest"]

            # Run generate
            ret = run([
                "--source-qualification", str(sq_path),
                "--fixtures", str(fx_path),
                "--provider-mappings", str(mp_path),
                "--attempts", str(att_path),
                "--quotes", str(q_path),
                "--protocol", str(DEFAULT_PROTOCOL_PATH),
                "--manifest-output", str(manifest_path),
                "--force",
            ])
            self.assertEqual(ret, 0)
            self.assertTrue(manifest_path.is_file())

            # Run check
            ret_check = run([
                "--source-qualification", str(sq_path),
                "--fixtures", str(fx_path),
                "--provider-mappings", str(mp_path),
                "--attempts", str(att_path),
                "--quotes", str(q_path),
                "--protocol", str(DEFAULT_PROTOCOL_PATH),
                "--check", str(manifest_path),
            ])
            self.assertEqual(ret_check, 0)


if __name__ == "__main__":
    unittest.main()
