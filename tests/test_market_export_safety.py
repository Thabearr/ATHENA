import unittest
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient

from api.export import router as export_router
from domain.markets import (
    MARKET_REGISTRY,
    MarketId,
    OutcomeId,
    UnknownMarketError,
    InvalidSelectionError,
    resolve_legacy_selection,
    serialize_selection,
    validate_selection,
)
from domain.model_status import MODEL_STATUS_REGISTRY, ModelStatus
from intelligence.accumulator import AccumulatorEngine
from intelligence.match_analyst import build_viable_market_candidates
from workers.bookie_automator import BookieAutomator


app = FastAPI()
app.include_router(export_router)


class CanonicalMarketRegistryTests(unittest.TestCase):
    def test_registry_contains_the_declared_market_scope(self):
        declared_scope = {
            MarketId.ASIAN_HANDICAP,
            MarketId.TOTAL_GOALS,
            MarketId.DRAW_OR_OVER_2_5,
            MarketId.AWAY_OR_OVER_2_5,
            MarketId.HOME_OR_OVER_2_5,
            MarketId.HOME_WIN_EITHER_HALF,
            MarketId.AWAY_WIN_EITHER_HALF,
            MarketId.DOUBLE_CHANCE,
            MarketId.BTTS,
            MarketId.DRAW_NO_BET,
            MarketId.HOME_WIN_TO_NIL,
            MarketId.AWAY_WIN_TO_NIL,
            MarketId.MATCH_RESULT_1UP,
            MarketId.MATCH_RESULT_2UP,
        }

        self.assertTrue(declared_scope.issubset(MARKET_REGISTRY))
        for market_id in declared_scope:
            with self.subTest(market_id=market_id):
                definition = MARKET_REGISTRY[market_id]
                self.assertTrue(definition.display_name)
                self.assertTrue(definition.settlement_semantics)
                self.assertTrue(definition.supported_outcomes)

    def test_win_either_half_aliases_resolve_to_one_selection(self):
        canonical = resolve_legacy_selection("WIN_EITHER_HALF_HOME_YES")

        for alias in ("HOME_WIN_EITHER_HALF", "HOME_TEAM_WIN_HALF"):
            self.assertEqual(resolve_legacy_selection(alias), canonical)

        self.assertEqual(canonical.market_id, MarketId.HOME_WIN_EITHER_HALF)
        self.assertEqual(canonical.outcome_id, OutcomeId.YES)

    def test_line_markets_require_a_line(self):
        with self.assertRaises(InvalidSelectionError):
            validate_selection(
                MarketId.ASIAN_HANDICAP,
                OutcomeId.AWAY,
                line=None,
            )

    def test_market_specific_outcomes_are_enforced(self):
        with self.assertRaises(InvalidSelectionError):
            validate_selection(MarketId.DRAW_NO_BET, OutcomeId.DRAW)

        market_id, outcome_id, line = validate_selection(
            MarketId.MATCH_RESULT_1UP,
            OutcomeId.DRAW,
        )
        self.assertEqual(market_id, MarketId.MATCH_RESULT_1UP)
        self.assertEqual(outcome_id, OutcomeId.DRAW)
        self.assertIsNone(line)

    def test_unknown_markets_fail_loudly(self):
        with self.assertRaises(UnknownMarketError):
            validate_selection("NOT_A_REAL_MARKET", OutcomeId.YES)

    def test_serialization_includes_auditable_market_metadata(self):
        selection = resolve_legacy_selection("UNDER_35")
        payload = serialize_selection(selection)

        self.assertEqual(payload["market_id"], MarketId.TOTAL_GOALS.value)
        self.assertEqual(payload["outcome_id"], OutcomeId.UNDER.value)
        self.assertEqual(payload["line"], 3.5)
        self.assertEqual(payload["display_label"], "Under 3.5")
        self.assertTrue(payload["settlement_semantics"])

    def test_disabled_selection_can_still_be_serialized_for_audit(self):
        payload = serialize_selection(
            resolve_legacy_selection("WIN_EITHER_HALF_HOME_YES")
        )

        self.assertEqual(
            payload["market_id"],
            MarketId.HOME_WIN_EITHER_HALF.value,
        )
        self.assertEqual(payload["outcome_id"], OutcomeId.YES.value)


class ExportSelectionPreservationTests(unittest.TestCase):
    QUOTE_NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    EXPECTED_SELECTIONS = {
        "fixture-home": {
            "fixture": "Alpha FC vs Beta FC",
            "market_id": MarketId.MATCH_RESULT.value,
            "outcome_id": OutcomeId.HOME.value,
            "line": None,
            "display_label": "Home Win",
        },
        "fixture-away": {
            "fixture": "Gamma FC vs Delta FC",
            "market_id": MarketId.MATCH_RESULT.value,
            "outcome_id": OutcomeId.AWAY.value,
            "line": None,
            "display_label": "Away Win",
        },
        "fixture-btts": {
            "fixture": "Epsilon FC vs Zeta FC",
            "market_id": MarketId.BTTS.value,
            "outcome_id": OutcomeId.YES.value,
            "line": None,
            "display_label": "BTTS Yes",
        },
        "fixture-under": {
            "fixture": "Eta FC vs Theta FC",
            "market_id": MarketId.TOTAL_GOALS.value,
            "outcome_id": OutcomeId.UNDER.value,
            "line": 3.5,
            "display_label": "Under 3.5",
        },
        "fixture-x2": {
            "fixture": "Iota FC vs Kappa FC",
            "market_id": MarketId.DOUBLE_CHANCE.value,
            "outcome_id": OutcomeId.DRAW_OR_AWAY.value,
            "line": None,
            "display_label": "Double Chance X2",
        },
        "fixture-ah": {
            "fixture": "Lambda FC vs Mu FC",
            "market_id": MarketId.ASIAN_HANDICAP.value,
            "outcome_id": OutcomeId.AWAY.value,
            "line": 1.5,
            "display_label": "Away +1.5",
        },
        "fixture-combo": {
            "fixture": "Nu FC vs Xi FC",
            "market_id": MarketId.HOME_OR_OVER_2_5.value,
            "outcome_id": OutcomeId.YES.value,
            "line": None,
            "display_label": "Home Team or Over 2.5 Yes",
        },
        "fixture-nil": {
            "fixture": "Omicron FC vs Pi FC",
            "market_id": MarketId.HOME_WIN_TO_NIL.value,
            "outcome_id": OutcomeId.NO.value,
            "line": None,
            "display_label": "Home Team to Win to Nil No",
        },
    }

    def _analyzed_fixtures(self):
        verdicts = [
            ("fixture-home", "Alpha FC", "Beta FC", "HOME_WIN"),
            ("fixture-away", "Gamma FC", "Delta FC", "AWAY_WIN"),
            ("fixture-btts", "Epsilon FC", "Zeta FC", "GG_YES"),
            ("fixture-under", "Eta FC", "Theta FC", "UNDER_35"),
            ("fixture-x2", "Iota FC", "Kappa FC", "DC_X2"),
            ("fixture-ah", "Lambda FC", "Mu FC", "AH_AWAY_PLUS_15"),
            ("fixture-combo", "Nu FC", "Xi FC", "HOME_OR_OVER_25"),
            ("fixture-nil", "Omicron FC", "Pi FC", "HOME_WIN_TO_NIL_NO"),
        ]
        return [
            {
                "fixture_id": fixture_id,
                **self.EXPECTED_SELECTIONS[fixture_id],
                "home_team": home_team,
                "away_team": away_team,
                "verdict": verdict,
                "edge": 0.10,
                "risk_score": 10.0,
                "bookmaker_odds": 2.0,
                "bookmaker_quote": {
                    "market_id": self.EXPECTED_SELECTIONS[
                        fixture_id
                    ]["market_id"],
                    "outcome_id": self.EXPECTED_SELECTIONS[
                        fixture_id
                    ]["outcome_id"],
                    "line": self.EXPECTED_SELECTIONS[fixture_id]["line"],
                    "bookmaker_odds": 2.0,
                    "source": "test_bookmaker",
                    "quote_snapshot_id": f"snapshot-{fixture_id}",
                    "observed_at": (
                        self.QUOTE_NOW - timedelta(minutes=1)
                    ).isoformat(),
                    "is_genuine": True,
                    "is_current": True,
                },
                "edge_is_bookmaker_value": True,
                "edge_pp": 5.0,
                "kelly_stake_pct": 1.0,
            }
            for fixture_id, home_team, away_team, verdict in verdicts
        ]

    def assert_selection_identity(self, legs):
        self.assertEqual(len(legs), len(self.EXPECTED_SELECTIONS))
        legs_by_fixture = {leg["fixture_id"]: leg for leg in legs}

        for fixture_id, expected in self.EXPECTED_SELECTIONS.items():
            with self.subTest(fixture_id=fixture_id):
                self.assertIn(fixture_id, legs_by_fixture)
                leg = legs_by_fixture[fixture_id]
                for field_name, expected_value in expected.items():
                    self.assertEqual(leg[field_name], expected_value)

    def test_mixed_slip_survives_json_api_and_export_preparation(self):
        accumulator = AccumulatorEngine(
            current_time_provider=lambda: self.QUOTE_NOW,
        ).generate_accumulator(
            self._analyzed_fixtures(),
            fold_size=8,
        )
        self.assertEqual(accumulator["decision_status"], "NO_BET")
        self.assertEqual(accumulator["legs"], [])

        # Existing canonical legs remain serializable for audit/export tests;
        # the accumulator did not authorize or create them.
        frontend_payload = jsonable_encoder({
            "decision_status": "NO_BET",
            "legs": self._analyzed_fixtures(),
        })
        self.assert_selection_identity(frontend_payload["legs"])

        response = TestClient(app).post(
            "/api/export",
            json={"bookmaker": "sportybet", "acca_data": frontend_payload},
        )

        self.assertEqual(response.status_code, 200)
        exported = response.json()
        self.assertEqual(exported["integration_status"], "integration_unavailable")
        self.assertIsNone(exported["bookmaker_code"])
        self.assertFalse(exported["bookmaker_code_is_genuine"])
        self.assertTrue(exported["slip_reference"].startswith("ATHENA-"))
        self.assertNotIn("code", exported)
        self.assert_selection_identity(exported["legs"])

        serialized_response = response.text
        self.assertNotIn("SB-", serialized_response)
        self.assertNotIn("shareBet", serialized_response)
        self.assertNotIn("stake.com", serialized_response)

    def test_fake_booking_code_entrypoint_is_disabled(self):
        self.assertFalse(hasattr(BookieAutomator(), "generate_booking_code"))

    def test_export_rejects_legs_without_canonical_or_registered_identity(self):
        response = TestClient(app).post(
            "/api/export",
            json={
                "bookmaker": "sportybet",
                "acca_data": {
                    "legs": [
                        {
                            "fixture": "Tau FC vs Upsilon FC",
                            "market": "1X2",
                            "selection": "Home",
                        }
                    ]
                },
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("canonical market_id/outcome_id", response.json()["detail"])

    def test_export_rejects_conflicting_canonical_and_legacy_identity(self):
        response = TestClient(app).post(
            "/api/export",
            json={
                "bookmaker": "sportybet",
                "acca_data": {
                    "legs": [
                        {
                            "fixture_id": "conflicting-selection",
                            "fixture": "Tau FC vs Upsilon FC",
                            "market_id": MarketId.MATCH_RESULT.value,
                            "outcome_id": OutcomeId.HOME.value,
                            "line": None,
                            "display_label": "Home Win",
                            "verdict": "AWAY_WIN",
                        }
                    ]
                },
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "conflicts with legacy verdict",
            response.json()["detail"],
        )


class AccumulatorCapabilityGateTests(unittest.TestCase):
    CURRENT_TIME = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)

    def _priced_fixture(
        self,
        market_id,
        outcome_id,
        *,
        line=None,
        fixture_id="capability-fixture",
    ):
        return {
            "fixture_id": fixture_id,
            "fixture": "Alpha FC vs Beta FC",
            "home_team": "Alpha FC",
            "away_team": "Beta FC",
            "market_id": market_id.value,
            "outcome_id": outcome_id.value,
            "line": line,
            "edge": 0.10,
            "risk_score": 10.0,
            "bookmaker_odds": 2.0,
            "bookmaker_quote": {
                "market_id": market_id.value,
                "outcome_id": outcome_id.value,
                "line": line,
                "bookmaker_odds": 2.0,
                "source": "test_bookmaker",
                "quote_snapshot_id": f"snapshot-{fixture_id}",
                "observed_at": (
                    self.CURRENT_TIME - timedelta(minutes=1)
                ).isoformat(),
                "is_genuine": True,
                "is_current": True,
            },
            "edge_is_bookmaker_value": True,
            "edge_pp": 10.0,
            "kelly_stake_pct": 1.0,
        }

    def _generate(self, fixture):
        return AccumulatorEngine(
            current_time_provider=lambda: self.CURRENT_TIME,
        ).generate_accumulator([fixture], fold_size=1)

    def test_every_market_without_selection_authority_is_rejected(self):
        disabled_selections = (
            (
                MarketId.HOME_WIN_EITHER_HALF,
                OutcomeId.YES,
                "home-either-half",
            ),
            (
                MarketId.AWAY_WIN_EITHER_HALF,
                OutcomeId.YES,
                "away-either-half",
            ),
            (MarketId.MATCH_RESULT_1UP, OutcomeId.HOME, "one-up"),
            (MarketId.MATCH_RESULT_2UP, OutcomeId.AWAY, "two-up"),
        )
        self.assertTrue(
            all(
                not MODEL_STATUS_REGISTRY[market_id].selectable
                for market_id, _, _ in disabled_selections
            )
        )

        for market_id, outcome_id, fixture_id in disabled_selections:
            with self.subTest(
                market_id=market_id,
                outcome_id=outcome_id,
            ):
                result = self._generate(
                    self._priced_fixture(
                        market_id,
                        outcome_id,
                        fixture_id=fixture_id,
                    )
                )

                self.assertEqual(result["decision_status"], "NO_BET")
                self.assertEqual(result["legs"], [])
                self.assertIn(
                    "no explicit selection authority",
                    result["no_bet_reasons"][0],
                )

        analytically_available = self._generate(
            self._priced_fixture(
                MarketId.MATCH_RESULT,
                OutcomeId.HOME,
                fixture_id="analytical-match-result",
            )
        )
        self.assertEqual(analytically_available["decision_status"], "NO_BET")
        self.assertEqual(analytically_available["legs"], [])
        self.assertIn(
            "no explicit selection authority",
            analytically_available["no_bet_reasons"][0],
        )

    def test_integer_and_quarter_handicap_lines_are_rejected(self):
        for line in (-2.0, -1.0, 0.0, 1.0, 2.0, -0.75, -0.25, 0.25, 0.75):
            with self.subTest(line=line):
                result = self._generate(
                    self._priced_fixture(
                        MarketId.ASIAN_HANDICAP,
                        OutcomeId.AWAY,
                        line=line,
                        fixture_id=f"unsupported-ah-{line}",
                    )
                )

                self.assertEqual(result["decision_status"], "NO_BET")
                self.assertEqual(result["legs"], [])
                self.assertIn("no explicit selection authority", result["no_bet_reasons"][0])

    def test_supported_half_goal_handicaps_are_analytical_only(self):
        for index, line in enumerate(
            (-2.5, -1.5, -0.5, 0.5, 1.5, 2.5)
        ):
            outcome_id = (
                OutcomeId.HOME if index % 2 == 0 else OutcomeId.AWAY
            )
            with self.subTest(line=line, outcome_id=outcome_id):
                result = self._generate(
                    self._priced_fixture(
                        MarketId.ASIAN_HANDICAP,
                        outcome_id,
                        line=line,
                        fixture_id=f"supported-ah-{index}",
                    )
                )

                self.assertEqual(result["decision_status"], "NO_BET")
                self.assertEqual(result["legs"], [])
                self.assertIn(
                    "no explicit selection authority",
                    result["no_bet_reasons"][0],
                )


class NoBetFallbackTests(unittest.TestCase):
    def test_baseline_delta_is_not_floored_or_given_a_fallback(self):
        no_candidates = build_viable_market_candidates(
            {"DC_1X": 0.70},
            {},
        )
        self.assertEqual(no_candidates, [])

        candidates = build_viable_market_candidates(
            {"DC_1X": 0.73},
            {},
        )
        self.assertEqual(candidates, [])

    def test_empty_accumulator_is_an_explicit_no_bet(self):
        result = AccumulatorEngine().generate_accumulator([], fold_size=5)

        self.assertEqual(result["decision_status"], "NO_BET")
        self.assertEqual(result["legs"], [])
        self.assertTrue(result["no_bet_reasons"])

    def test_unknown_selection_does_not_become_double_chance(self):
        result = AccumulatorEngine().generate_accumulator(
            [
                {
                    "fixture_id": "unknown-market",
                    "fixture": "Rho FC vs Sigma FC",
                    "home_team": "Rho FC",
                    "away_team": "Sigma FC",
                    "verdict": "UNREGISTERED_MARKET_SELECTION",
                    "edge": 0.10,
                    "risk_score": 10.0,
                }
            ],
            fold_size=1,
        )

        self.assertEqual(result["decision_status"], "NO_BET")
        self.assertEqual(result["legs"], [])
        self.assertIn(
            "unsupported selection identifier",
            result["no_bet_reasons"][0],
        )

    def test_missing_bookmaker_odds_cannot_bypass_selection_authority(self):
        result = AccumulatorEngine().generate_accumulator(
            [
                {
                    "fixture_id": "missing-odds",
                    "fixture": "Phi FC vs Chi FC",
                    "home_team": "Phi FC",
                    "away_team": "Chi FC",
                    "verdict": "DC_1X",
                    "edge": 0.10,
                    "risk_score": 10.0,
                }
            ],
            fold_size=1,
        )

        self.assertEqual(result["decision_status"], "NO_BET")
        self.assertEqual(result["legs"], [])
        self.assertIn(
            "no explicit selection authority",
            result["no_bet_reasons"][0],
        )

if __name__ == "__main__":
    unittest.main()
