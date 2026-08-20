from typing import List, Dict, Any

from domain.accumulator_priority import prioritize_accumulator_candidates
from domain.markets import DecisionStatus
from intelligence.correlation_analyzer import CorrelationAnalyzer
from intelligence.match_analyst import MARKET_CATEGORIES
from services.nlp_engine import NLPEngine
from loguru import logger


class AccaFilter:
    """Leg filtering with deterministic league/fixture priority ordering.

    Eligibility is decided before priority.  Priority never rescues a fixture
    that failed the decision, pricing, freshness, risk, correlation, or market
    gates.  Once a fixture is eligible, ATHENA uses strict league exhaustion:
    every eligible fixture in the highest-ranked league is considered before the
    next league.  Unclassified leagues are considered only after the configured
    hierarchy has been exhausted.
    """

    def __init__(self):
        self.correlation_analyzer = CorrelationAnalyzer()
        self.nlp_engine = NLPEngine()

    def filter_and_rank_legs(
        self,
        analyzed_matches: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Disqualify invalid legs, then apply the default priority policy.

        This preserves the existing eligibility checks.  Ranking no longer uses
        a fuzzy league substring tier or a hidden weighted score.  Instead it is
        the transparent policy in ``domain.accumulator_priority``:

        league rank -> estimated leg probability -> risk -> freshness ->
        validated bookmaker edge -> kickoff -> stable fixture identity.
        """

        valid_legs = []

        for match in analyzed_matches:
            if match.get("decision_status") != DecisionStatus.BET.value:
                continue
            if not match.get("accumulator_eligible_selection"):
                continue

            # Existing baseline-delta eligibility gate.  This field is not
            # treated as bookmaker value by the priority policy.
            edge = match.get("edge")
            if not isinstance(edge, (int, float)) or isinstance(edge, bool) or edge < 0.05:
                continue

            # Existing hard risk gate.
            risk_score = match.get("risk_score", 0.0)
            if (
                not isinstance(risk_score, (int, float))
                or isinstance(risk_score, bool)
                or risk_score > 85
            ):
                continue

            # Existing evidence-freshness gate.
            freshness = match.get("freshness", 1.0)
            if (
                not isinstance(freshness, (int, float))
                or isinstance(freshness, bool)
                or freshness < 0.40
            ):
                continue

            valid_legs.append(match)

        # Explicitly allow fallback leagues, but rank 999 means they are only
        # reached after every configured priority league has been exhausted.
        ordered, exclusions = prioritize_accumulator_candidates(
            valid_legs,
            allow_unprioritized=True,
        )
        for exclusion in exclusions:
            logger.warning(
                "Accumulator priority excluded fixture %s (%s): %s",
                exclusion.fixture_id,
                exclusion.league,
                exclusion.reason,
            )
        return list(ordered)

    def build_filtered_acca(
        self,
        ranked_legs: List[Dict[str, Any]],
        target_size: int = 5,
        single_league: bool = False,
    ) -> List[Dict[str, Any]]:
        """Build the final acca while preserving strict league exhaustion.

        ``ranked_legs`` already carries the league hierarchy and fixture priority
        order.  This method walks that order once, applying team duplication,
        late-context, market-category and correlation checks.  There is no
        arbitrary per-league cap: a lower-priority league can enter only after
        every earlier candidate has either been accepted or rejected by a real
        gate.
        """

        final_acca = []
        team_set = set()

        correlation_threshold = 0.85 if single_league else 0.65

        for leg in ranked_legs:
            if len(final_acca) >= target_size:
                break

            home_team = leg.get("home_team")
            away_team = leg.get("away_team")
            priced_market = leg.get("accumulator_eligible_selection")

            # Only the exact selection that passed bookmaker pricing may enter
            # the accumulator. Analytical alternatives remain audit-only.
            if not isinstance(priced_market, dict):
                continue

            # Same team in multiple legs — always block.
            if home_team in team_set or away_team in team_set:
                continue

            # Preserve the legacy late-context check.  It may reject a fixture,
            # but it cannot promote a lower-priority fixture ahead of an
            # unexamined higher-priority candidate.
            try:
                nlp_data = self.nlp_engine.analyze_fixture(home_team, away_team)

                if nlp_data.get("absence_risk", 0) >= 20:
                    logger.warning(
                        "NLP fatal risk: %s vs %s flagged for heavy absences; skipping fixture.",
                        home_team,
                        away_team,
                    )
                    continue

                fatigue = nlp_data.get("fatigue_score", 0)
                pressure = nlp_data.get("pressure_score", 0)
                if fatigue > 10:
                    leg["risk_score"] = leg.get("risk_score", 0) + fatigue
                    logger.warning(
                        "NLP fatigue flagged for %s vs %s (+%s risk)",
                        home_team,
                        away_team,
                        fatigue,
                    )
                if pressure > 10:
                    leg["risk_score"] = leg.get("risk_score", 0) + (pressure / 2)

                motivation = nlp_data.get("motivation_score", 0)
                if motivation > 5:
                    leg["risk_score"] = max(
                        0,
                        leg.get("risk_score", 0) - (motivation / 2),
                    )
            except Exception as exc:
                logger.error(
                    "NLP Engine failed for %s vs %s: %s",
                    home_team,
                    away_team,
                    exc,
                )

            # Validate the one priced selection. Diversity may reject it, but
            # must never substitute a different unpriced market.
            leg_accepted = False
            for market_option in (priced_market,):
                verdict = market_option["verdict"]
                cat = market_option.get(
                    "category",
                    MARKET_CATEGORIES.get(verdict, "OTHER"),
                )
                market_delta = market_option.get("edge")
                if not isinstance(market_delta, (int, float)) or isinstance(
                    market_delta,
                    bool,
                ):
                    continue

                if self.correlation_analyzer.is_category_full(
                    verdict,
                    final_acca,
                ):
                    continue

                test_leg = leg.copy()
                test_leg["verdict"] = verdict
                test_leg["market"] = verdict
                test_leg["market_id"] = market_option.get("market_id")
                test_leg["outcome_id"] = market_option.get("outcome_id")
                test_leg["line"] = market_option.get("line")
                test_leg["display_label"] = market_option.get("display_label")
                test_leg["edge"] = market_delta
                test_leg["edge_is_bookmaker_value"] = market_option.get(
                    "edge_is_bookmaker_value",
                    False,
                )
                test_leg["edge_method"] = market_option.get("edge_method")
                test_leg["estimated_probability"] = market_option.get("prob")
                test_leg["probability_method"] = market_option.get(
                    "probability_method"
                )
                test_leg["bookmaker_odds"] = market_option.get("bookmaker_odds")
                test_leg["bookmaker_quote"] = market_option.get("bookmaker_quote")
                test_leg["edge_pp"] = market_option.get("edge_pp")
                test_leg["kelly_stake_pct"] = market_option.get("kelly_stake_pct")
                test_leg["market_category"] = cat

                correlation = self.correlation_analyzer.check_leg_correlation(
                    test_leg,
                    final_acca,
                    skip_league=single_league,
                )

                if correlation <= correlation_threshold:
                    final_acca.append(test_leg)
                    team_set.add(home_team)
                    team_set.add(away_team)
                    leg_accepted = True
                    break

            if not leg_accepted:
                continue

        return final_acca
