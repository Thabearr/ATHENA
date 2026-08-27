"""
Enhanced Accumulator Engine - Fullproof Selection Strategy
Balances edge confidence with practical betting constraints.
"""

import logging
import math
from datetime import datetime, timezone
from typing import List, Dict

from domain.markets import (
    DecisionStatus,
    MarketId,
    MarketRegistryError,
    make_selection,
    resolve_legacy_selection,
    serialize_leg,
    serialize_selection,
)
from domain.model_status import MODEL_STATUS_REGISTRY
from domain.pricing import (
    DEFAULT_MAX_QUOTE_AGE_SECONDS,
    parse_bookmaker_quotes,
    quote_matches_selection,
)

logger = logging.getLogger("athena.accumulator")


class AccumulatorEngine:
    """
    Generates bulletproof accas by prioritizing:
    1. Strong Poisson probability (>70%)
    2. Solid edge (>0.08 for safety, >0.10 ideal)
    3. Market reliability (proven markets only)
    4. Risk-adjusted selection (allows some upset alerts if edge is exceptional)
    """

    def __init__(
        self,
        min_edge: float = 0.05,
        *,
        max_quote_age_seconds: int = DEFAULT_MAX_QUOTE_AGE_SECONDS,
        current_time_provider=None,
    ):
        self.min_edge = min_edge
        self.max_quote_age_seconds = max_quote_age_seconds
        self.current_time_provider = (
            current_time_provider
            or (lambda: datetime.now(timezone.utc))
        )
        self.market_reliability = {
            "TO_QUALIFY_HOME": 0.95,
            "TO_QUALIFY_AWAY": 0.95,
            "1X2_2UP_HOME": 0.90,
            "1X2_2UP_AWAY": 0.90,
            "1X2_1UP_HOME": 0.85,
            "1X2_1UP_AWAY": 0.85,
            "DNB_HOME": 0.80,
            "DNB_AWAY": 0.80,
            "DC_1X": 0.75,
            "DC_X2": 0.75,
            "DC_12": 0.75,
            "HOME_OR_OVER_25": 0.70,
            "AWAY_OR_OVER_25": 0.70,
            "HOME_WIN_TO_NIL_NO": 0.65,
            "AWAY_WIN_TO_NIL_NO": 0.65,
            "ASIAN_HANDICAP_HOME_PLUS_1_5": 0.60,
            "ASIAN_HANDICAP_AWAY_PLUS_1_5": 0.60,
            "WIN_EITHER_HALF_HOME_YES": 0.55,
            "WIN_EITHER_HALF_AWAY_YES": 0.55,
            "GG_YES": 0.50,
            "GG_NO": 0.50,
            "OVER_15": 0.45,
            "UNDER_35": 0.45,
        }

    def map_verdict_to_market_string(
        self,
        verdict: str,
        home_team: str,
        away_team: str,
    ) -> tuple:
        """Map a registered legacy verdict to its display tuple.

        Unknown verdicts fail loudly instead of silently becoming a Double
        Chance Home-or-Draw selection.
        """
        selection = serialize_selection(resolve_legacy_selection(verdict))
        return (
            selection["market_display_name"],
            selection["outcome_display_name"],
        )

    @staticmethod
    def _capability_rejection_reason(
        canonical_selection,
        prepared_fixture: dict,
    ):
        """Return why a canonical selection cannot enter an accumulator."""
        model_status = MODEL_STATUS_REGISTRY[canonical_selection.market_id]
        if not model_status.selectable:
            return (
                f"{prepared_fixture['market_display_name']} has no explicit "
                "selection authority for accumulator use: "
                f"{model_status.reason}"
            )

        if canonical_selection.market_id == MarketId.ASIAN_HANDICAP:
            line = canonical_selection.line
            if line is None or abs(line) % 1.0 != 0.5:
                return (
                    "Asian Handicap accumulator legs support only exact "
                    "half-goal lines; integer and quarter-goal lines are "
                    "unsupported."
                )

        return None

    def _score_fixture(self, fixture: dict) -> float:
        """Score a fixture for legacy acca inclusion fallback.

        The reviewed league/fixture priority planner supersedes this score when
        candidates carry ``priority_policy_version``.  This method remains only
        for callers that have not yet crossed the new priority boundary.
        """
        verdict = fixture.get("verdict", "DC_1X")
        raw_edge = fixture.get("edge")
        edge = (
            float(raw_edge)
            if isinstance(raw_edge, (int, float))
            and not isinstance(raw_edge, bool)
            and math.isfinite(float(raw_edge))
            else 0.0
        )
        risk_score = fixture.get("risk_score", 100)
        upset_alert = fixture.get("upset_alert", False)

        market_score = self.market_reliability.get(verdict, 40) * 100
        edge_score = min(edge * 500, 100)
        risk_penalty = (risk_score / 100) * 30
        upset_penalty = 15 if upset_alert else 0

        total_score = (
            (market_score * 0.60)
            + (edge_score * 0.30)
            - risk_penalty
            - upset_penalty
        )
        return max(total_score, 0)

    def _is_acca_eligible(self, fixture: dict, strict: bool = False) -> bool:
        """Determine if a fixture is eligible under the legacy risk rules."""
        raw_edge = fixture.get("edge")
        edge = (
            float(raw_edge)
            if isinstance(raw_edge, (int, float))
            and not isinstance(raw_edge, bool)
            and math.isfinite(float(raw_edge))
            else 0.0
        )
        upset_alert = fixture.get("upset_alert", False)
        risk_score = fixture.get("risk_score", 100)
        verdict = fixture.get("verdict", "")

        if edge < self.min_edge:
            return False

        hedged_safety_markets = {
            "DC_1X",
            "DC_X2",
            "DC_12",
            "DNB_HOME",
            "DNB_AWAY",
            "OVER_15",
            "UNDER_35",
            "OVER_05",
            "UNDER_45",
            "UNDER_55",
            "AH_HOME_PLUS_15",
            "AH_AWAY_PLUS_15",
            "AH_HOME_PLUS_25",
            "AH_AWAY_PLUS_25",
            "HOME_OR_OVER_25",
            "AWAY_OR_OVER_25",
            "DRAW_OR_OVER_25",
            "TO_QUALIFY_HOME",
            "TO_QUALIFY_AWAY",
            "WIN_EITHER_HALF_HOME_YES",
            "WIN_EITHER_HALF_AWAY_YES",
        }

        if strict and upset_alert and verdict not in hedged_safety_markets:
            return False
        if risk_score > 85:
            return False
        return True

    def generate_accumulator(
        self,
        analyzed_fixtures: list,
        fold_size: int,
        strict: bool = False,
    ) -> dict:
        """Generate an accumulator from pre-filtered fixtures.

        If every candidate carries ATHENA priority metadata, the incoming order
        is the consideration order.  ATHENA walks that entire ordered reserve
        until the requested fold is filled or the pool is exhausted, so one
        rejected higher-priority fixture does not cause an avoidable shortfall.

        Callers without priority metadata retain the historical score fallback.
        """
        requested_fold_size = fold_size
        eligible = list(analyzed_fixtures)

        if len(eligible) < fold_size:
            if len(eligible) == 0:
                return {
                    "decision_status": DecisionStatus.NO_BET.value,
                    "no_bet_reasons": [
                        "No fixture had a validated market selection."
                    ],
                    "fold_size": 0,
                    "requested_fold_size": requested_fold_size,
                    "total_estimated_odds": 0.0,
                    "legs": [],
                    "evidence_reports": [],
                    "eligible_count": 0,
                    "available_count": len(analyzed_fixtures),
                }
            fold_size = len(eligible)

        priority_ordered = bool(eligible) and all(
            isinstance(fix, dict) and fix.get("priority_policy_version")
            for fix in eligible
        )
        if priority_ordered:
            candidate_fixtures = eligible
        else:
            scored = [(fix, self._score_fixture(fix)) for fix in eligible]
            scored.sort(key=lambda item: item[1], reverse=True)
            candidate_fixtures = [fix for fix, _ in scored[:fold_size]]

        legs = []
        rejected_reasons = []
        attempted_fixtures = []
        compounded_odds = 1.0

        for fix in candidate_fixtures:
            if len(legs) >= fold_size:
                break
            attempted_fixtures.append(fix)
            verdict = fix.get("verdict")
            try:
                prepared_fixture = serialize_leg(fix)
                canonical_selection = make_selection(
                    prepared_fixture["market_id"],
                    prepared_fixture["outcome_id"],
                    line=prepared_fixture["line"],
                    display_label=prepared_fixture["display_label"],
                    selection_display_name=prepared_fixture[
                        "outcome_display_name"
                    ],
                )
            except MarketRegistryError as exc:
                reason = (
                    f"{fix.get('fixture', 'Unknown fixture')}: unsupported "
                    f"selection identifier or invalid canonical identity "
                    f"({exc})."
                )
                logger.warning(reason)
                rejected_reasons.append(reason)
                continue

            capability_rejection = self._capability_rejection_reason(
                canonical_selection,
                prepared_fixture,
            )
            if capability_rejection:
                reason = (
                    f"{fix.get('fixture', 'Unknown fixture')}: "
                    f"{capability_rejection}"
                )
                logger.warning(reason)
                rejected_reasons.append(reason)
                continue

            bookmaker_odds = fix.get("bookmaker_odds")
            raw_quote = fix.get("bookmaker_quote")
            try:
                validated_quotes = parse_bookmaker_quotes(
                    [raw_quote] if isinstance(raw_quote, dict) else [],
                    current_time=self.current_time_provider(),
                    max_quote_age_seconds=self.max_quote_age_seconds,
                )
                exact_quote = validated_quotes[0] if validated_quotes else None
            except (MarketRegistryError, TypeError, ValueError):
                exact_quote = None

            if (
                not isinstance(bookmaker_odds, (int, float))
                or isinstance(bookmaker_odds, bool)
                or bookmaker_odds <= 1.0
                or exact_quote is None
                or not exact_quote.is_genuine
                or not exact_quote.is_current
                or not quote_matches_selection(exact_quote, canonical_selection)
                or abs(exact_quote.bookmaker_odds - float(bookmaker_odds)) > 1e-9
                or fix.get("edge_is_bookmaker_value") is not True
                or not isinstance(fix.get("edge_pp"), (int, float))
                or not isinstance(fix.get("kelly_stake_pct"), (int, float))
            ):
                reason = (
                    f"{fix.get('fixture', 'Unknown fixture')}: no validated "
                    "current bookmaker odds matching the exact market, "
                    "outcome, and line were provided."
                )
                logger.warning(reason)
                rejected_reasons.append(reason)
                continue

            leg_odds = round(float(bookmaker_odds), 4)
            compounded_odds *= leg_odds

            legs.append(
                {
                    "fixture_id": fix.get("fixture_id"),
                    "fixture": fix["fixture"],
                    "home_team": fix.get("home_team"),
                    "away_team": fix.get("away_team"),
                    "league": fix.get("league"),
                    "match_date": fix.get("match_date"),
                    "verdict": verdict,
                    "market_id": prepared_fixture["market_id"],
                    "outcome_id": prepared_fixture["outcome_id"],
                    "line": prepared_fixture["line"],
                    "display_label": prepared_fixture["display_label"],
                    "market_family": prepared_fixture["market_family"],
                    "market_display_name": prepared_fixture[
                        "market_display_name"
                    ],
                    "outcome_display_name": prepared_fixture[
                        "outcome_display_name"
                    ],
                    "settlement_semantics": prepared_fixture[
                        "settlement_semantics"
                    ],
                    "market": prepared_fixture["market_display_name"],
                    "selection": prepared_fixture["outcome_display_name"],
                    "edge": round(fix["edge"], 3),
                    "edge_is_bookmaker_value": fix.get(
                        "edge_is_bookmaker_value",
                        False,
                    ),
                    "edge_method": fix.get("edge_method"),
                    "edge_pp": round(float(fix["edge_pp"]), 4),
                    "kelly_stake_pct": round(
                        float(fix["kelly_stake_pct"]),
                        4,
                    ),
                    "estimated_probability": fix.get("estimated_probability"),
                    "probability_method": fix.get("probability_method"),
                    "evidence_report": fix.get("evidence_report"),
                    "risk_score": round(fix["risk_score"], 1),
                    "odds": leg_odds,
                    "odds_source": "bookmaker",
                    "priority_policy_version": fix.get(
                        "priority_policy_version"
                    ),
                    "league_priority_policy_version": fix.get(
                        "league_priority_policy_version"
                    ),
                    "league_priority_tier": fix.get("league_priority_tier"),
                    "league_priority_rank": fix.get("league_priority_rank"),
                    "league_priority_name": fix.get("league_priority_name"),
                    "fixture_priority_probability": fix.get(
                        "fixture_priority_probability"
                    ),
                    "fixture_priority_risk_score": fix.get(
                        "fixture_priority_risk_score"
                    ),
                    "fixture_priority_freshness": fix.get(
                        "fixture_priority_freshness"
                    ),
                    "fixture_priority_edge_pp": fix.get(
                        "fixture_priority_edge_pp"
                    ),
                }
            )

        if not legs:
            return {
                "decision_status": DecisionStatus.NO_BET.value,
                "no_bet_reasons": rejected_reasons
                or ["No fixture had a validated market selection."],
                "fold_size": 0,
                "requested_fold_size": requested_fold_size,
                "total_estimated_odds": 0.0,
                "legs": [],
                "evidence_reports": [
                    fix["evidence_report"]
                    for fix in attempted_fixtures
                    if fix.get("evidence_report")
                ],
                "eligible_count": len(eligible),
                "available_count": len(analyzed_fixtures),
            }

        return {
            "decision_status": DecisionStatus.BET.value,
            "no_bet_reasons": [],
            "fold_size": len(legs),
            "requested_fold_size": requested_fold_size,
            "total_estimated_odds": round(compounded_odds, 2),
            "legs": legs,
            "eligible_count": len(eligible),
            "available_count": len(analyzed_fixtures),
            "priority_policy_version": (
                candidate_fixtures[0].get("priority_policy_version")
                if priority_ordered and candidate_fixtures
                else None
            ),
        }
