import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from domain.markets import MarketId, OutcomeId
from domain.model_status import MODEL_STATUS_REGISTRY, ModelStatus
from domain.win_either_half_pricing_evidence import (
    BOOKMAKER_FAIR_PROBABILITY_BANDS,
    CANONICAL_DECIMAL_PLACES,
    DEFAULT_MAX_QUOTE_AGE_SECONDS,
    DEVIG_METHOD,
    PERMITTED_MARKETS,
    PERMITTED_OUTCOMES,
    EvidenceReason,
    EvidenceStatus,
    KnownFixture,
    ProviderSelectionMapping,
    ResearchQuoteRecord,
    bookmaker_fair_probability_band,
    build_provider_mapping_registry,
    canonical_decimal_text,
    select_latest_eligible_snapshots,
    validate_complete_snapshot,
    validate_research_quote,
)
from scripts.export_win_either_half_pricing_evidence import (
    CALIBRATED_PREDICTION_COLUMNS,
    FROZEN_CALIBRATED_PREDICTIONS_IDENTITY,
    FROZEN_SELECTED_CALIBRATIONS,
    FROZEN_STAGE_4B_MANIFEST_LOGICAL_SHA256,
    PricingExportError,
    build_pricing_manifest,
    compare_pricing_manifests,
    evaluate_pricing_evidence,
    load_verified_calibrated_predictions,
    main,
    render_coverage,
    render_rejected_quotes,
    render_snapshots,
    render_valid_quotes,
    verify_stage_4b_manifest_contract,
    write_pricing_outputs,
)


class WinEitherHalfPricingEvidenceTests(unittest.TestCase):
    REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
    USE_DEFAULT_DECISION = object()

    def setUp(self):
        self.kickoff = datetime(2026, 5, 1, 15, 0, tzinfo=timezone.utc)
        self.decision = self.kickoff - timedelta(minutes=10)
        self.observed = self.decision - timedelta(minutes=5)
        self.fixture_id = "fixture-001"
        self.fixtures = {
            (self.fixture_id, market): KnownFixture(
                self.fixture_id,
                market,
                self.kickoff,
                "FINAL_TEST",
            )
            for market in PERMITTED_MARKETS
        }
        mappings = []
        for market in PERMITTED_MARKETS:
            for outcome in PERMITTED_OUTCOMES:
                mappings.append(
                    ProviderSelectionMapping.from_mapping(
                        {
                            "source": "book-a",
                            "provider_event_identifier": "event-1",
                            "provider_market_identifier": f"pm-{market.value}",
                            "provider_selection_identifier": f"ps-{outcome.value}",
                            "fixture_identifier": self.fixture_id,
                            "market_id": market.value,
                            "outcome_id": outcome.value,
                            "line": None,
                        }
                    )
                )
        self.mappings = build_provider_mapping_registry(mappings)

    def _quote(self, outcome=OutcomeId.YES, **changes):
        market = changes.pop("market_id", MarketId.HOME_WIN_EITHER_HALF)
        if isinstance(market, MarketId):
            market_value = market.value
            provider_market = f"pm-{market.value}"
        else:
            market_value = market
            provider_market = f"pm-{market}"
        outcome_value = outcome.value if isinstance(outcome, OutcomeId) else outcome
        value = {
            "schema_version": 1,
            "fixture_identifier": self.fixture_id,
            "market_id": market_value,
            "outcome_id": outcome_value,
            "line": None,
            "source": "book-a",
            "quote_snapshot_id": "snapshot-1",
            "observed_at": self.observed.isoformat(),
            "fixture_kickoff": self.kickoff.isoformat(),
            "decimal_odds": 1.8 if outcome_value == "YES" else 2.2,
            "is_genuine": True,
            "provider_event_identifier": "event-1",
            "provider_market_identifier": provider_market,
            "provider_selection_identifier": f"ps-{outcome_value}",
        }
        value.update(changes)
        return value

    def _validate(self, value, decision=USE_DEFAULT_DECISION):
        return validate_research_quote(
            value,
            fixture_catalog=self.fixtures,
            provider_mappings=self.mappings,
            decision_at=(
                self.decision
                if decision is self.USE_DEFAULT_DECISION
                else decision
            ),
        )

    def _record(self, outcome=OutcomeId.YES, **changes):
        result = self._validate(self._quote(outcome, **changes))
        self.assertEqual(result.status, EvidenceStatus.ACCEPTED, result.reasons)
        return result.record

    @staticmethod
    def _reasons(result):
        return {reason.value for reason in result.reasons}

    def test_permitted_market_outcome_and_line_contract_is_exact(self):
        self.assertEqual(
            PERMITTED_MARKETS,
            (
                MarketId.HOME_WIN_EITHER_HALF,
                MarketId.AWAY_WIN_EITHER_HALF,
            ),
        )
        self.assertEqual(PERMITTED_OUTCOMES, (OutcomeId.YES, OutcomeId.NO))
        for market in PERMITTED_MARKETS:
            for outcome in PERMITTED_OUTCOMES:
                with self.subTest(market=market, outcome=outcome):
                    self.assertEqual(
                        self._validate(self._quote(outcome, market_id=market)).status,
                        EvidenceStatus.ACCEPTED,
                    )
        self.assertIn(
            "INVALID_LINE", self._reasons(self._validate(self._quote(line=0.0)))
        )

    def test_unknown_market_outcome_and_fixture_fail_closed(self):
        unknown_market = self._validate(self._quote(market_id="HOME_TEAM_WIN_HALF"))
        self.assertIn("UNKNOWN_MARKET", self._reasons(unknown_market))
        unknown_outcome = self._validate(self._quote(outcome="HOME"))
        self.assertIn("UNKNOWN_OUTCOME", self._reasons(unknown_outcome))
        unknown_fixture = self._validate(
            self._quote(fixture_identifier="not-frozen")
        )
        self.assertIn("UNKNOWN_FIXTURE", self._reasons(unknown_fixture))

    def test_provider_mapping_is_exact_and_all_identifiers_are_required(self):
        mismatch = self._validate(
            self._quote(provider_selection_identifier="provider-other")
        )
        self.assertIn("PROVIDER_MAPPING_MISMATCH", self._reasons(mismatch))
        for name in (
            "provider_event_identifier",
            "provider_market_identifier",
            "provider_selection_identifier",
        ):
            with self.subTest(name=name):
                result = self._validate(self._quote(**{name: ""}))
                self.assertIn("MISSING_PROVIDER_IDENTIFIER", self._reasons(result))

    def test_missing_source_snapshot_and_genuine_requirement(self):
        self.assertIn(
            "MISSING_SOURCE",
            self._reasons(self._validate(self._quote(source=""))),
        )
        self.assertIn(
            "MISSING_SNAPSHOT_ID",
            self._reasons(self._validate(self._quote(quote_snapshot_id=""))),
        )
        self.assertIn(
            "NOT_GENUINE",
            self._reasons(self._validate(self._quote(is_genuine=False))),
        )

    def test_decimal_odds_validation(self):
        for value in (None, True, False, 1.0, 0, -2, float("nan"), float("inf"), "x"):
            with self.subTest(value=value):
                result = self._validate(self._quote(decimal_odds=value))
                self.assertIn("INVALID_ODDS", self._reasons(result))
        self.assertEqual(
            self._validate(self._quote(decimal_odds="1.0000001")).status,
            EvidenceStatus.ACCEPTED,
        )

    def test_all_as_of_timestamps_must_be_timezone_aware(self):
        fields = ("observed_at", "fixture_kickoff")
        for field in fields:
            with self.subTest(field=field):
                value = self._quote(**{field: "2026-05-01T14:00:00"})
                self.assertIn("NAIVE_TIMESTAMP", self._reasons(self._validate(value)))
        result = self._validate(self._quote(), decision="2026-05-01T14:45:00")
        self.assertIn("NAIVE_TIMESTAMP", self._reasons(result))
        missing = self._validate(self._quote(), decision=None)
        self.assertIn("MISSING_DECISION_AT", self._reasons(missing))

    def test_as_of_ordering_rejections_are_explicit(self):
        after_decision = self._validate(
            self._quote(observed_at=(self.decision + timedelta(seconds=1)).isoformat())
        )
        self.assertIn("OBSERVED_AFTER_DECISION", self._reasons(after_decision))
        after_kickoff = self._validate(
            self._quote(observed_at=(self.kickoff + timedelta(seconds=1)).isoformat()),
            decision=self.kickoff + timedelta(seconds=2),
        )
        self.assertIn("OBSERVED_AFTER_KICKOFF", self._reasons(after_kickoff))
        at_kickoff = self._validate(self._quote(), decision=self.kickoff)
        self.assertIn("DECISION_AT_OR_AFTER_KICKOFF", self._reasons(at_kickoff))

    def test_default_freshness_boundary_accepts_900_seconds_and_rejects_901(self):
        self.assertEqual(DEFAULT_MAX_QUOTE_AGE_SECONDS, 900)
        boundary = self._validate(
            self._quote(observed_at=(self.decision - timedelta(seconds=900)).isoformat())
        )
        self.assertEqual(boundary.status, EvidenceStatus.ACCEPTED)
        stale = self._validate(
            self._quote(observed_at=(self.decision - timedelta(seconds=901)).isoformat())
        )
        self.assertIn("STALE_AT_DECISION", self._reasons(stale))

    def test_complete_yes_no_snapshot_is_accepted_and_incomplete_is_unavailable(self):
        complete = validate_complete_snapshot(
            (self._record(OutcomeId.YES), self._record(OutcomeId.NO))
        )
        self.assertEqual(complete.status, EvidenceStatus.ACCEPTED)
        self.assertIsNotNone(complete.snapshot)
        incomplete = validate_complete_snapshot((self._record(OutcomeId.YES),))
        self.assertEqual(incomplete.status, EvidenceStatus.UNAVAILABLE)
        self.assertEqual(incomplete.reasons, (EvidenceReason.INCOMPLETE_MARKET,))

    def test_duplicate_yes_and_duplicate_no_fail_closed(self):
        for outcome in PERMITTED_OUTCOMES:
            with self.subTest(outcome=outcome):
                other = OutcomeId.NO if outcome is OutcomeId.YES else OutcomeId.YES
                result = validate_complete_snapshot(
                    (self._record(outcome), self._record(outcome), self._record(other))
                )
                self.assertEqual(result.status, EvidenceStatus.REJECTED)
                self.assertIn(EvidenceReason.DUPLICATE_OUTCOME, result.reasons)

    def test_mixed_source_snapshot_and_observed_time_fail_closed(self):
        yes = self._record(OutcomeId.YES)
        no = self._record(OutcomeId.NO)
        variants = (
            ("MIXED_SOURCE", {"source": "book-b"}),
            ("MIXED_SNAPSHOT", {"quote_snapshot_id": "snapshot-2"}),
            ("MIXED_OBSERVED_AT", {"observed_at": no.observed_at - timedelta(seconds=1)}),
        )
        for expected, changes in variants:
            with self.subTest(expected=expected):
                changed = ResearchQuoteRecord(**{**no.__dict__, **changes})
                result = validate_complete_snapshot((yes, changed))
                self.assertEqual(result.status, EvidenceStatus.REJECTED)
                self.assertIn(expected, self._reasons(result))

    def test_cross_bookmaker_and_cross_snapshot_rows_cannot_form_a_market(self):
        quote_rows = [self._quote(OutcomeId.YES), self._quote(OutcomeId.NO)]
        quote_rows[1]["source"] = "book-b"
        quote_rows[1]["provider_selection_identifier"] = "ps-NO-book-b"
        mapping = ProviderSelectionMapping.from_mapping(
            {
                "source": "book-b",
                "provider_event_identifier": "event-1",
                "provider_market_identifier": "pm-HOME_WIN_EITHER_HALF",
                "provider_selection_identifier": "ps-NO-book-b",
                "fixture_identifier": self.fixture_id,
                "market_id": "HOME_WIN_EITHER_HALF",
                "outcome_id": "NO",
                "line": None,
            }
        )
        mappings = dict(self.mappings)
        mappings[mapping.lookup_key] = mapping
        result = evaluate_pricing_evidence(
            quote_rows,
            fixture_catalog=self.fixtures,
            provider_mappings=mappings,
            decisions={self.fixture_id: self.decision},
        )
        self.assertEqual(result["coverage"]["snapshot_counts"]["ACCEPTED"], 0)
        self.assertEqual(result["coverage"]["snapshot_counts"]["UNAVAILABLE"], 2)

        quote_rows = [self._quote(OutcomeId.YES), self._quote(OutcomeId.NO)]
        quote_rows[1]["quote_snapshot_id"] = "snapshot-2"
        result = evaluate_pricing_evidence(
            quote_rows,
            fixture_catalog=self.fixtures,
            provider_mappings=self.mappings,
            decisions={self.fixture_id: self.decision},
        )
        self.assertEqual(result["coverage"]["snapshot_counts"]["ACCEPTED"], 0)
        self.assertEqual(result["coverage"]["snapshot_counts"]["UNAVAILABLE"], 2)

    def test_latest_snapshot_and_lexical_tie_break_are_deterministic(self):
        def snapshot(snapshot_id, observed):
            yes = ResearchQuoteRecord(
                **{
                    **self._record(OutcomeId.YES).__dict__,
                    "quote_snapshot_id": snapshot_id,
                    "observed_at": observed,
                }
            )
            no = ResearchQuoteRecord(
                **{
                    **self._record(OutcomeId.NO).__dict__,
                    "quote_snapshot_id": snapshot_id,
                    "observed_at": observed,
                }
            )
            return validate_complete_snapshot((yes, no))

        older = snapshot("z-older", self.observed - timedelta(seconds=1))
        same_a = snapshot("snapshot-a", self.observed)
        same_b = snapshot("snapshot-b", self.observed)
        selected = select_latest_eligible_snapshots((same_a, older, same_b))
        winner = [result.snapshot for result in selected if result.selected]
        self.assertEqual(len(winner), 1)
        self.assertEqual(winner[0].quote_snapshot_id, "snapshot-b")

    def test_multiplicative_devig_overround_and_probability_sum(self):
        result = validate_complete_snapshot(
            (self._record(OutcomeId.YES), self._record(OutcomeId.NO))
        )
        snapshot = result.snapshot
        self.assertEqual(snapshot.devig_method, DEVIG_METHOD)
        expected_yes_raw = 1 / 1.8
        expected_no_raw = 1 / 2.2
        self.assertEqual(
            snapshot.yes_raw_implied_probability,
            float(f"{expected_yes_raw:.12f}"),
        )
        self.assertEqual(
            snapshot.overround,
            float(f"{expected_yes_raw + expected_no_raw:.12f}"),
        )
        self.assertAlmostEqual(
            snapshot.yes_fair_probability + snapshot.no_fair_probability,
            1.0,
            places=12,
        )
        for value in snapshot.to_dict().values():
            if isinstance(value, float):
                self.assertTrue(value == value and abs(value) != float("inf"))
        self.assertTrue(0 <= snapshot.yes_fair_probability <= 1)
        self.assertTrue(0 <= snapshot.no_fair_probability <= 1)

        invalid_yes = ResearchQuoteRecord(
            **{
                **self._record(OutcomeId.YES).__dict__,
                "decimal_odds": Decimal("NaN"),
            }
        )
        non_finite = validate_complete_snapshot(
            (invalid_yes, self._record(OutcomeId.NO))
        )
        self.assertEqual(non_finite.status, EvidenceStatus.REJECTED)
        self.assertIn(EvidenceReason.NON_FINITE_RESULT, non_finite.reasons)

    def test_accepted_rejected_and_unavailable_counts_are_separate(self):
        complete = [self._quote(OutcomeId.YES), self._quote(OutcomeId.NO)]
        incomplete = self._quote(OutcomeId.YES, quote_snapshot_id="snapshot-2")
        rejected = self._quote(
            OutcomeId.NO,
            quote_snapshot_id="snapshot-3",
            decimal_odds=1.0,
        )
        result = evaluate_pricing_evidence(
            [*complete, incomplete, rejected],
            fixture_catalog=self.fixtures,
            provider_mappings=self.mappings,
            decisions={self.fixture_id: self.decision},
        )
        self.assertEqual(
            result["coverage"]["quote_counts"],
            {"ACCEPTED": 3, "REJECTED": 1, "UNAVAILABLE": 0},
        )
        self.assertEqual(
            result["coverage"]["snapshot_counts"],
            {"ACCEPTED": 1, "REJECTED": 0, "UNAVAILABLE": 1},
        )

    def test_canonical_serialization_and_bookmaker_fair_band_boundaries(self):
        self.assertEqual(CANONICAL_DECIMAL_PLACES, 12)
        self.assertEqual(canonical_decimal_text(Decimal("0.1234567890124")), "0.123456789012")
        expected = {
            0.0: "[0.0,0.2)",
            0.199999: "[0.0,0.2)",
            0.2: "[0.2,0.4)",
            0.4: "[0.4,0.6)",
            0.6: "[0.6,0.8)",
            0.8: "[0.8,1.0]",
            1.0: "[0.8,1.0]",
        }
        self.assertEqual(len(BOOKMAKER_FAIR_PROBABILITY_BANDS), 5)
        for value, band in expected.items():
            with self.subTest(value=value):
                self.assertEqual(bookmaker_fair_probability_band(value), band)

    def test_evaluation_roles_are_preserved_without_unlabelled_aggregation(self):
        result = evaluate_pricing_evidence(
            [self._quote(OutcomeId.YES), self._quote(OutcomeId.NO)],
            fixture_catalog=self.fixtures,
            provider_mappings=self.mappings,
            decisions={self.fixture_id: self.decision},
        )
        self.assertEqual(result["coverage"]["scope"], "ALL_ROLES_DESCRIPTIVE")
        self.assertEqual(
            set(result["coverage"]["by_evaluation_role"]),
            {"CALIBRATION_FIT_OOF", "VALIDATION_SELECTION", "FINAL_TEST"},
        )
        self.assertEqual(
            result["coverage"]["by_evaluation_role"]["FINAL_TEST"][
                "accepted_quotes"
            ],
            2,
        )

    def test_exact_stage_4b_ancestry_and_local_prediction_identity_are_frozen(self):
        path = self.REPOSITORY_ROOT / (
            "artifacts/research-manifests/win-either-half-calibration-v1.json"
        )
        manifest = json.loads(path.read_text(encoding="utf-8"))
        ancestry = verify_stage_4b_manifest_contract(manifest)
        self.assertEqual(
            ancestry["manifest_logical_sha256"],
            FROZEN_STAGE_4B_MANIFEST_LOGICAL_SHA256,
        )
        self.assertEqual(
            ancestry["calibrated_predictions"],
            FROZEN_CALIBRATED_PREDICTIONS_IDENTITY,
        )
        self.assertEqual(
            ancestry["selected_calibrations"], FROZEN_SELECTED_CALIBRATIONS
        )
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "predictions.csv"
            fake.write_text("not frozen\n", encoding="utf-8")
            with self.assertRaisesRegex(PricingExportError, "byte size differs"):
                load_verified_calibrated_predictions(fake, manifest)

    def test_small_prediction_fixture_loader_preserves_all_roles(self):
        rows = []
        roles = (
            ("CALIBRATION_FIT_OOF", "TRAIN", "2021-01-01T12:00:00Z"),
            ("VALIDATION_SELECTION", "VALIDATION", "2022-01-01T12:00:00Z"),
            ("FINAL_TEST", "TEST", "2023-01-01T12:00:00Z"),
        )
        for index, (role, split, kickoff) in enumerate(roles):
            for target, calibration in FROZEN_SELECTED_CALIBRATIONS.items():
                rows.append(
                    {
                        "fixture_identity": f"fixture-{index}",
                        "kickoff_utc": kickoff,
                        "league": "E0",
                        "season": "2025-26",
                        "split": split,
                        "prediction_role": role,
                        "target_name": target,
                        "target_value": "1",
                        "base_model_identifier": "logistic_l2_c0.1_v1",
                        "model_probability": "0.500000000000",
                        "calibration_identifier": calibration,
                        "calibrated_probability": "0.500000000000",
                    }
                )
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=CALIBRATED_PREDICTION_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        content = stream.getvalue().encode("utf-8")
        identity = {
            "byte_size": len(content),
            "rows": len(rows),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.csv"
            path.write_bytes(content)
            manifest = {"files": {"calibrated_predictions": identity}}
            catalog, actual = load_verified_calibrated_predictions(
                path,
                manifest,
                expected_identity=identity,
                require_frozen_identity=False,
            )
        self.assertEqual(len(catalog), 6)
        self.assertEqual(
            actual["evaluation_role_rows"],
            {
                "CALIBRATION_FIT_OOF": 2,
                "FINAL_TEST": 2,
                "VALIDATION_SELECTION": 2,
            },
        )

    def test_outputs_are_deterministic_lf_atomic_and_contain_no_decision_fields(self):
        evaluation = evaluate_pricing_evidence(
            [self._quote(OutcomeId.NO), self._quote(OutcomeId.YES)],
            fixture_catalog=self.fixtures,
            provider_mappings=self.mappings,
            decisions={self.fixture_id: self.decision},
        )
        valid, valid_rows = render_valid_quotes(evaluation["quote_results"])
        rejected, rejected_rows = render_rejected_quotes(evaluation["quote_results"])
        snapshots, snapshot_rows = render_snapshots(evaluation["snapshot_results"])
        coverage = render_coverage(evaluation["coverage"])
        self.assertNotIn(b"\r\n", valid + rejected + snapshots + coverage)
        header = snapshots.splitlines()[0].decode("utf-8").split(",")
        forbidden = {"edge", "edge_pp", "expected_value", "kelly", "bet"}
        self.assertFalse(forbidden.intersection(header))
        self.assertEqual((valid_rows, rejected_rows, snapshot_rows), (2, 0, 1))

        manifest_path_name = "win-either-half-pricing-v1.json"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {
                "valid_quotes_path": root / "valid.csv",
                "rejected_quotes_path": root / "rejected.csv",
                "snapshots_path": root / "snapshots.csv",
                "coverage_path": root / "coverage.json",
                "manifest_path": root / manifest_path_name,
            }
            write_pricing_outputs(
                **paths,
                valid_quote_bytes=valid,
                rejected_quote_bytes=rejected,
                snapshot_bytes=snapshots,
                coverage_bytes=coverage,
                manifest={"schema_version": 1},
            )
            self.assertTrue(all(path.exists() for path in paths.values()))
            with self.assertRaisesRegex(PricingExportError, "already exists"):
                write_pricing_outputs(
                    **paths,
                    valid_quote_bytes=valid,
                    rejected_quote_bytes=rejected,
                    snapshot_bytes=snapshots,
                    coverage_bytes=coverage,
                    manifest={"schema_version": 1},
                )

    def test_manifest_timestamp_is_non_semantic_and_contract_has_no_value_fields(self):
        stage_4b = json.loads(
            (
                self.REPOSITORY_ROOT
                / "artifacts/research-manifests/win-either-half-calibration-v1.json"
            ).read_text(encoding="utf-8")
        )
        empty = b""
        manifest = build_pricing_manifest(
            stage_4b_manifest=stage_4b,
            prediction_identity=FROZEN_CALIBRATED_PREDICTIONS_IDENTITY,
            quote_identity={"rows": 0, "byte_size": 0, "sha256": hashlib.sha256(empty).hexdigest()},
            mapping_identity={"rows": 0, "byte_size": 0, "sha256": hashlib.sha256(empty).hexdigest()},
            decision_identity={"rows": 0, "byte_size": 0, "sha256": hashlib.sha256(empty).hexdigest()},
            valid_quote_bytes=empty,
            valid_quote_rows=0,
            rejected_quote_bytes=empty,
            rejected_quote_rows=0,
            snapshot_bytes=empty,
            snapshot_rows=0,
            coverage_bytes=empty,
            coverage={"scope": "ALL_ROLES_DESCRIPTIVE"},
            generator_code_state={
                "evidence_git_head_sha": "1" * 40,
                "tracked_worktree_clean": True,
            },
            max_quote_age_seconds=900,
            generated_at_utc="2026-01-01T00:00:00Z",
        )
        changed = json.loads(json.dumps(manifest))
        changed["generated_at_utc"] = "2099-01-01T00:00:00Z"
        self.assertEqual(compare_pricing_manifests(manifest, changed), [])
        def all_keys(value):
            if isinstance(value, dict):
                for key, nested in value.items():
                    yield str(key).lower()
                    yield from all_keys(nested)
            elif isinstance(value, list):
                for nested in value:
                    yield from all_keys(nested)

        keys = set(all_keys(manifest))
        self.assertFalse(
            {"edge", "edge_pp", "kelly", "kelly_stake", "expected_value", "bet"}
            .intersection(keys)
        )
        self.assertFalse(manifest["market_safety"]["production_activation_authorized"])

    def test_dirty_worktree_fails_closed_before_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            quotes = root / "quotes.jsonl"
            mappings = root / "mappings.json"
            decisions = root / "decisions.json"
            quotes.write_text("", encoding="utf-8")
            mappings.write_text("[]", encoding="utf-8")
            decisions.write_text("[]", encoding="utf-8")
            manifest = self.REPOSITORY_ROOT / (
                "artifacts/research-manifests/win-either-half-calibration-v1.json"
            )
            with patch(
                "scripts.export_win_either_half_pricing_evidence.load_verified_calibrated_predictions",
                return_value=({}, {"rows": 36318}),
            ), patch(
                "scripts.export_win_either_half_pricing_evidence.get_code_state",
                return_value={
                    "evidence_git_head_sha": "1" * 40,
                    "tracked_worktree_clean": False,
                },
            ):
                result = main(
                    [
                        "--manifest-output",
                        str(root / "manifest.json"),
                        "--quotes",
                        str(quotes),
                        "--provider-mappings",
                        str(mappings),
                        "--decisions",
                        str(decisions),
                        "--calibration-manifest",
                        str(manifest),
                        "--calibrated-predictions",
                        str(root / "unused.csv"),
                    ]
                )
            self.assertEqual(result, 1)
            self.assertFalse((root / "manifest.json").exists())

    def test_direct_and_module_help_are_offline(self):
        commands = (
            [sys.executable, "scripts/export_win_either_half_pricing_evidence.py", "--help"],
            [sys.executable, "-m", "scripts.export_win_either_half_pricing_evidence", "--help"],
        )
        with patch.object(
            socket.socket,
            "connect",
            side_effect=AssertionError("network access is forbidden"),
        ):
            for command in commands:
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
                    self.assertIn("--max-quote-age-seconds", result.stdout)

    def test_row_outputs_remain_ignored_and_markets_disabled(self):
        tracked = set(
            subprocess.run(
                ["git", "ls-files"],
                cwd=self.REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                shell=False,
                check=True,
            ).stdout.splitlines()
        )
        for path in (
            ".cache/athena-research/win-either-half/pricing-valid-quotes-v1.csv",
            ".cache/athena-research/win-either-half/pricing-rejected-quotes-v1.csv",
            ".cache/athena-research/win-either-half/pricing-snapshots-v1.csv",
            ".cache/athena-research/win-either-half/pricing-coverage-v1.json",
            "artifacts/research-manifests/win-either-half-pricing-v1.json",
        ):
            self.assertNotIn(path, tracked)
        for market in PERMITTED_MARKETS:
            self.assertEqual(
                MODEL_STATUS_REGISTRY[market].status, ModelStatus.DISABLED
            )


if __name__ == "__main__":
    unittest.main()
