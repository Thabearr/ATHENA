from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from domain.markets import MarketId, OutcomeId
from domain.model_status import MODEL_STATUS_REGISTRY, ModelStatus
from domain.win_either_half_prospective_replay import (
    PERMITTED_MARKETS,
    ProspectiveFixture,
    ProspectiveReplayError,
    ReplayReason,
    ReplayStatus,
    aggregate_replay,
    evaluate_replay_row,
    load_fixture_catalog,
    load_provider_mappings,
    parse_quotes,
    reject_forbidden_fields,
    run_prospective_replay,
    validate_candidate_offsets,
    validate_source_qualification_report,
)
from scripts.export_win_either_half_prospective_replay import (
    DEFAULT_PROTOCOL_PATH,
    InputFile,
    ProspectiveReplayExportError,
    _canonical_json_bytes,
    build_outputs,
    main,
    validate_protocol_contract,
)


class WinEitherHalfProspectiveReplayTests(unittest.TestCase):
    REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
    KICKOFF = datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)

    def setUp(self):
        protocol_bytes = DEFAULT_PROTOCOL_PATH.read_bytes()
        self.protocol_value = json.loads(protocol_bytes.decode("utf-8"))
        self.protocol = validate_protocol_contract(
            self.protocol_value, protocol_bytes
        )

    def _source_report(self, status="QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY"):
        return {
            "schema_version": 1,
            "dataset_name": "win-either-half-pricing-source-qualification-v1",
            "provider_identifier": "reviewed-provider",
            "qualification": {"prospective_replay_status": status},
            "holdout_governance": {"prospective_validation_required": True},
            "market_statuses": {
                MarketId.HOME_WIN_EITHER_HALF.value: "DISABLED",
                MarketId.AWAY_WIN_EITHER_HALF.value: "DISABLED",
            },
            "no_production_approval": "qualification only",
        }

    def _fixtures(self):
        return {
            "schema_version": 1,
            "dataset_name": "win-either-half-prospective-fixtures-v1",
            "provider_identifier": "reviewed-provider",
            "expected_sources": ["sportybet"],
            "fixtures": [
                {
                    "fixture_identifier": "fixture-1",
                    "provider_event_identifier": "event-1",
                    "kickoff_utc": "2026-08-10T15:00:00Z",
                    "market_ids": [
                        MarketId.HOME_WIN_EITHER_HALF.value,
                        MarketId.AWAY_WIN_EITHER_HALF.value,
                    ],
                }
            ],
        }

    def _mappings(self):
        rows = []
        for market in PERMITTED_MARKETS:
            provider_market = f"provider-{market.value}"
            for outcome in (OutcomeId.YES, OutcomeId.NO):
                rows.append(
                    {
                        "source": "sportybet",
                        "provider_event_identifier": "event-1",
                        "provider_market_identifier": provider_market,
                        "provider_selection_identifier": (
                            f"{provider_market}-{outcome.value.lower()}"
                        ),
                        "fixture_identifier": "fixture-1",
                        "market_id": market.value,
                        "outcome_id": outcome.value,
                        "line": None,
                    }
                )
        return rows

    def _quote(
        self,
        market,
        outcome,
        *,
        observed_at="2026-08-10T14:40:00Z",
        snapshot="snapshot-1",
        odds="2.00",
    ):
        provider_market = f"provider-{market.value}"
        return {
            "schema_version": 1,
            "fixture_identifier": "fixture-1",
            "market_id": market.value,
            "outcome_id": outcome.value,
            "line": None,
            "source": "sportybet",
            "quote_snapshot_id": snapshot,
            "observed_at": observed_at,
            "fixture_kickoff": "2026-08-10T15:00:00Z",
            "decimal_odds": odds,
            "is_genuine": True,
            "provider_event_identifier": "event-1",
            "provider_market_identifier": provider_market,
            "provider_selection_identifier": (
                f"{provider_market}-{outcome.value.lower()}"
            ),
        }

    def _complete_quotes(self, **changes):
        rows = []
        for market in PERMITTED_MARKETS:
            for outcome in (OutcomeId.YES, OutcomeId.NO):
                rows.append(self._quote(market, outcome, **changes))
        return rows

    def _loaded(self):
        fixtures, sources = load_fixture_catalog(
            self._fixtures(), provider_identifier="reviewed-provider"
        )
        lookup, canonical = load_provider_mappings(
            self._mappings(), fixtures=fixtures, expected_sources=sources
        )
        return fixtures, sources, lookup, canonical

    def test_source_qualification_must_explicitly_allow_prospective_replay(self):
        accepted = validate_source_qualification_report(self._source_report())
        self.assertEqual(accepted["provider_identifier"], "reviewed-provider")
        for status in ("UNKNOWN", "PARTIALLY_QUALIFIED", "DISQUALIFIED"):
            with self.subTest(status=status), self.assertRaises(
                ProspectiveReplayError
            ):
                validate_source_qualification_report(self._source_report(status))

    def test_protocol_is_exact_unselected_and_fails_closed_on_drift(self):
        protocol_bytes = DEFAULT_PROTOCOL_PATH.read_bytes()
        result = validate_protocol_contract(
            json.loads(protocol_bytes.decode("utf-8")), protocol_bytes
        )
        self.assertEqual(result.sha256, hashlib.sha256(protocol_bytes).hexdigest())
        self.assertEqual(result.value["selection_policy"]["selection_status"], "UNSELECTED")
        changed = json.loads(protocol_bytes.decode("utf-8"))
        changed["maximum_quote_age_seconds"] = 901
        with self.assertRaises(ProspectiveReplayExportError):
            validate_protocol_contract(changed, _canonical_json_bytes(changed))

    def test_candidate_offsets_are_unique_positive_and_bounded(self):
        self.assertEqual(validate_candidate_offsets([900, 3600]), (3600, 900))
        for values in ([0], [-1], [True], [900, 900], [604801]):
            with self.subTest(values=values), self.assertRaises(
                ProspectiveReplayError
            ):
                validate_candidate_offsets(values)

    def test_outcomes_models_value_and_betting_fields_are_forbidden(self):
        for field in (
            "result",
            "home_goals",
            "model_probability",
            "edge",
            "expected_value",
            "kelly",
            "stake",
            "bet_decision",
        ):
            with self.subTest(field=field), self.assertRaises(
                ProspectiveReplayError
            ):
                reject_forbidden_fields({"nested": {field: 1}})

    def test_fixture_catalog_requires_both_exact_markets_and_aware_kickoff(self):
        fixtures, sources = load_fixture_catalog(
            self._fixtures(), provider_identifier="reviewed-provider"
        )
        self.assertEqual(tuple(fixtures), ("fixture-1",))
        self.assertEqual(sources, ("sportybet",))
        missing_market = self._fixtures()
        missing_market["fixtures"][0]["market_ids"].pop()
        with self.assertRaises(ProspectiveReplayError):
            load_fixture_catalog(
                missing_market, provider_identifier="reviewed-provider"
            )
        naive = self._fixtures()
        naive["fixtures"][0]["kickoff_utc"] = "2026-08-10T15:00:00"
        with self.assertRaisesRegex(ProspectiveReplayError, "timezone-aware"):
            load_fixture_catalog(naive, provider_identifier="reviewed-provider")

    def test_provider_mappings_require_exact_complete_four_way_coverage(self):
        fixtures, sources = load_fixture_catalog(
            self._fixtures(), provider_identifier="reviewed-provider"
        )
        lookup, canonical = load_provider_mappings(
            self._mappings(), fixtures=fixtures, expected_sources=sources
        )
        self.assertEqual(len(lookup), 4)
        self.assertEqual(len(canonical), 4)
        incomplete = self._mappings()[:-1]
        with self.assertRaisesRegex(ProspectiveReplayError, "cover every"):
            load_provider_mappings(
                incomplete, fixtures=fixtures, expected_sources=sources
            )
        duplicate = self._mappings() + [dict(self._mappings()[0])]
        with self.assertRaisesRegex(ProspectiveReplayError, "unique"):
            load_provider_mappings(
                duplicate, fixtures=fixtures, expected_sources=sources
            )

    def test_quote_validation_is_exact_and_fail_closed(self):
        fixtures, _, lookup, _ = self._loaded()
        valid = parse_quotes(
            self._complete_quotes(), fixtures=fixtures, mapping_lookup=lookup
        )
        self.assertTrue(all(result.accepted for result in valid))
        cases = []
        row = self._quote(PERMITTED_MARKETS[0], OutcomeId.YES)
        row["is_genuine"] = False
        cases.append(row)
        row = self._quote(PERMITTED_MARKETS[0], OutcomeId.YES)
        row["decimal_odds"] = "NaN"
        cases.append(row)
        row = self._quote(PERMITTED_MARKETS[0], OutcomeId.YES)
        row["observed_at"] = "2026-08-10T14:40:00"
        cases.append(row)
        row = self._quote(PERMITTED_MARKETS[0], OutcomeId.YES)
        row["provider_selection_identifier"] = "wrong"
        cases.append(row)
        for index, changed in enumerate(cases):
            with self.subTest(index=index):
                result = parse_quotes(
                    [changed], fixtures=fixtures, mapping_lookup=lookup
                )[0]
                self.assertFalse(result.accepted)
                self.assertTrue(result.reasons)

    def test_900_second_freshness_boundary_accepts_and_901_rejects(self):
        fixture = ProspectiveFixture(
            "fixture-1", "event-1", self.KICKOFF, PERMITTED_MARKETS
        )
        fixtures, _, lookup, _ = self._loaded()
        market = PERMITTED_MARKETS[0]
        decision = self.KICKOFF - timedelta(seconds=900)
        quotes_900 = [
            self._quote(
                market,
                outcome,
                observed_at=(decision - timedelta(seconds=900)).isoformat(),
            )
            for outcome in (OutcomeId.YES, OutcomeId.NO)
        ]
        parsed_900 = parse_quotes(
            quotes_900, fixtures=fixtures, mapping_lookup=lookup
        )
        row_900 = evaluate_replay_row(
            fixture=fixture,
            market_id=market,
            source="sportybet",
            candidate_offset_seconds=900,
            raw_quote_count=2,
            valid_quotes=[result.record for result in parsed_900 if result.record],
        )
        self.assertEqual(row_900.availability_status, ReplayStatus.AVAILABLE)
        quotes_901 = [
            self._quote(
                market,
                outcome,
                observed_at=(decision - timedelta(seconds=901)).isoformat(),
            )
            for outcome in (OutcomeId.YES, OutcomeId.NO)
        ]
        parsed_901 = parse_quotes(
            quotes_901, fixtures=fixtures, mapping_lookup=lookup
        )
        row_901 = evaluate_replay_row(
            fixture=fixture,
            market_id=market,
            source="sportybet",
            candidate_offset_seconds=900,
            raw_quote_count=2,
            valid_quotes=[result.record for result in parsed_901 if result.record],
        )
        self.assertEqual(
            row_901.availability_reason,
            ReplayReason.NO_FRESH_QUOTES_AT_DECISION,
        )

    def test_incomplete_snapshot_is_unavailable_and_snapshots_never_mix(self):
        fixtures, _, lookup, _ = self._loaded()
        market = PERMITTED_MARKETS[0]
        one_outcome = [self._quote(market, OutcomeId.YES)]
        parsed = parse_quotes(one_outcome, fixtures=fixtures, mapping_lookup=lookup)
        row = evaluate_replay_row(
            fixture=fixtures["fixture-1"],
            market_id=market,
            source="sportybet",
            candidate_offset_seconds=900,
            raw_quote_count=1,
            valid_quotes=[result.record for result in parsed if result.record],
        )
        self.assertEqual(row.availability_reason, ReplayReason.NO_COMPLETE_SNAPSHOT)
        mixed = [
            self._quote(market, OutcomeId.YES, snapshot="a"),
            self._quote(market, OutcomeId.NO, snapshot="b"),
        ]
        parsed_mixed = parse_quotes(
            mixed, fixtures=fixtures, mapping_lookup=lookup
        )
        mixed_row = evaluate_replay_row(
            fixture=fixtures["fixture-1"],
            market_id=market,
            source="sportybet",
            candidate_offset_seconds=900,
            raw_quote_count=2,
            valid_quotes=[
                result.record for result in parsed_mixed if result.record
            ],
        )
        self.assertEqual(
            mixed_row.availability_reason, ReplayReason.NO_COMPLETE_SNAPSHOT
        )

    def test_latest_snapshot_and_lexical_tie_break_are_deterministic(self):
        fixtures, _, lookup, _ = self._loaded()
        market = PERMITTED_MARKETS[0]
        rows = []
        for snapshot in ("snapshot-a", "snapshot-b"):
            for outcome in (OutcomeId.YES, OutcomeId.NO):
                rows.append(self._quote(market, outcome, snapshot=snapshot))
        parsed = parse_quotes(rows, fixtures=fixtures, mapping_lookup=lookup)
        replay = evaluate_replay_row(
            fixture=fixtures["fixture-1"],
            market_id=market,
            source="sportybet",
            candidate_offset_seconds=900,
            raw_quote_count=4,
            valid_quotes=[result.record for result in parsed if result.record],
        )
        self.assertEqual(replay.selected_snapshot_id, "snapshot-b")

    def test_full_denominator_and_both_market_aggregate_reconcile(self):
        fixtures, sources, lookup, _ = self._loaded()
        quote_rows = self._complete_quotes()
        results = parse_quotes(
            quote_rows, fixtures=fixtures, mapping_lookup=lookup
        )
        replay = run_prospective_replay(
            fixtures=fixtures,
            expected_sources=sources,
            offsets=(3600, 900),
            raw_quote_rows=quote_rows,
            quote_results=results,
        )
        self.assertEqual(len(replay), 4)
        summary = aggregate_replay(
            replay, minimum_fixtures_for_interpretation=100
        )
        by_offset = {
            row["candidate_offset_seconds"]: row
            for row in summary["offsets"]
        }
        self.assertEqual(by_offset[900]["both_markets_available_same_source"], 1)
        self.assertEqual(by_offset[3600]["both_markets_available_same_source"], 0)
        self.assertEqual(summary["selection_status"], "UNSELECTED")

    def test_outputs_are_deterministic_lf_and_exclude_odds_models_value_and_bets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_bytes = _canonical_json_bytes(self._source_report())
            fixtures_bytes = _canonical_json_bytes(self._fixtures())
            mappings_bytes = _canonical_json_bytes(self._mappings())
            quotes = self._complete_quotes()
            quote_bytes = b"".join(
                _canonical_json_bytes(row, pretty=False) + b"\n" for row in quotes
            )
            kwargs = dict(
                protocol=self.protocol,
                source_qualification=self._source_report(),
                source_qualification_file=InputFile(root / "source.json", source_bytes),
                fixtures_value=self._fixtures(),
                fixtures_file=InputFile(root / "fixtures.json", fixtures_bytes),
                mappings_value=self._mappings(),
                mappings_file=InputFile(root / "mappings.json", mappings_bytes),
                quote_rows=quotes,
                quotes_file=InputFile(root / "quotes.jsonl", quote_bytes),
                code_state={
                    "evidence_git_head_sha": "1" * 40,
                    "tracked_worktree_clean": True,
                },
            )
            first = build_outputs(**kwargs)
            second = build_outputs(**kwargs)
            self.assertEqual(first[:3], second[:3])
            row_bytes, rejected_bytes, summary_bytes, summary = first
            self.assertNotIn(b"\r\n", row_bytes)
            self.assertNotIn(b"\r\n", rejected_bytes)
            combined = (row_bytes + rejected_bytes + summary_bytes).lower()
            for forbidden in (
                b"decimal_odds",
                b"model_probability",
                b"expected_value",
                b"kelly",
                b"bet_decision",
            ):
                self.assertNotIn(forbidden, combined)
            self.assertEqual(summary["expected_row_denominator"], 16)
            self.assertEqual(summary["aggregate"]["selection_status"], "UNSELECTED")

    def test_cli_generation_and_check_are_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.json"
            fixtures = root / "fixtures.json"
            mappings = root / "mappings.json"
            quotes = root / "quotes.jsonl"
            source.write_text(json.dumps(self._source_report()), encoding="utf-8")
            fixtures.write_text(json.dumps(self._fixtures()), encoding="utf-8")
            mappings.write_text(json.dumps(self._mappings()), encoding="utf-8")
            quotes.write_text(
                "\n".join(json.dumps(row) for row in self._complete_quotes()) + "\n",
                encoding="utf-8",
            )
            rows = root / "rows.csv"
            rejected = root / "rejected.csv"
            summary = root / "summary.json"
            common = [
                "--source-qualification",
                str(source),
                "--fixtures",
                str(fixtures),
                "--provider-mappings",
                str(mappings),
                "--quotes",
                str(quotes),
                "--rows-output",
                str(rows),
                "--rejected-output",
                str(rejected),
                "--summary-output",
                str(summary),
            ]
            with patch(
                "scripts.export_win_either_half_prospective_replay.get_code_state",
                return_value={
                    "evidence_git_head_sha": "1" * 40,
                    "tracked_worktree_clean": True,
                },
            ):
                self.assertEqual(main(common), 0)
                self.assertEqual(
                    main(
                        [
                            "--source-qualification",
                            str(source),
                            "--fixtures",
                            str(fixtures),
                            "--provider-mappings",
                            str(mappings),
                            "--quotes",
                            str(quotes),
                            "--check-rows",
                            str(rows),
                            "--check-rejected",
                            str(rejected),
                            "--check-summary",
                            str(summary),
                        ]
                    ),
                    0,
                )

    def test_help_entrypoints_are_offline_and_markets_remain_disabled(self):
        commands = (
            [sys.executable, "scripts/export_win_either_half_prospective_replay.py", "--help"],
            [sys.executable, "-m", "scripts.export_win_either_half_prospective_replay", "--help"],
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
        for market in PERMITTED_MARKETS:
            self.assertEqual(
                MODEL_STATUS_REGISTRY[market].status, ModelStatus.DISABLED
            )
        ignored = subprocess.run(
            [
                "git",
                "check-ignore",
                ".cache/athena-research/win-either-half/prospective-replay-summary-v1.json",
            ],
            cwd=self.REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            shell=False,
        )
        # The uploaded source archive may not contain .git metadata; the rule is
        # still present in .gitignore and is verified on the actual branch by CI.
        if ignored.returncode == 0:
            self.assertIn("prospective-replay-summary-v1.json", ignored.stdout)
        else:
            self.assertIn(".cache/athena-research/", (self.REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
