import logging
import math
import hashlib
import sqlite3
import os
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from domain.evidence import (
    DataQualitySummary,
    EvidenceItem,
    EvidenceStatus,
    FixtureEvidenceReport,
    MarketEvaluation,
    evidence_items_by_field,
)
from domain.markets import (
    MARKET_REGISTRY,
    DecisionStatus,
    MarketId,
    MarketRegistryError,
    resolve_legacy_selection,
)
from domain.model_status import (
    MODEL_STATUS_REGISTRY,
    ModelStatus,
    get_model_status,
)
from domain.pricing import (
    DEFAULT_MAX_QUOTE_AGE_SECONDS,
    parse_bookmaker_quotes,
    price_selection,
)
from domain.score_matrix import build_score_matrix
from intelligence.ml_engine import MLEngine

logger = logging.getLogger("athena.match_analyst")


# Global baseline probabilities for each market type.
# These represent the "average" probability across all football matches.
# Edge = fixture_prob - baseline gives VALUE ABOVE MARKET AVERAGE.
MARKET_BASELINES = {

    "DC_1X": 0.72,
    "DC_X2": 0.62,
    "DC_12": 0.74,
    "OVER_05": 0.92,
    "OVER_15": 0.78,
    "OVER_25": 0.52,
    "UNDER_25": 0.48,
    "UNDER_35": 0.72,
    "UNDER_45": 0.86,
    "UNDER_55": 0.95,
    "AH_HOME_PLUS_15": 0.82,
    "AH_AWAY_PLUS_15": 0.82,
    "AH_HOME_PLUS_25": 0.92,
    "AH_AWAY_PLUS_25": 0.92,
    "HOME_OR_OVER_25": 0.68,
    "AWAY_OR_OVER_25": 0.58,
    "DRAW_OR_OVER_25": 0.65,
    "GG_YES": 0.48,
    "GG_NO": 0.52,
    "DNB_HOME": 0.44,
    "DNB_AWAY": 0.36,
    "WIN_EITHER_HALF_HOME_YES": 0.52,
    "WIN_EITHER_HALF_AWAY_YES": 0.42,
    "HOME_WIN_TO_NIL_YES": 0.22,
    "HOME_WIN_TO_NIL_NO": 0.78,
    "AWAY_WIN_TO_NIL_YES": 0.16,
    "AWAY_WIN_TO_NIL_NO": 0.84,
    "1X2_2UP_HOME": 0.44,
    "1X2_2UP_AWAY": 0.36,
    "1X2_1UP_HOME": 0.44,
    "1X2_1UP_AWAY": 0.36,
}

# Load dynamic weights from evolution engine if available
_WEIGHTS_PATH = os.path.join("config", "model_weights.json")
try:
    if os.path.exists(_WEIGHTS_PATH):
        with open(_WEIGHTS_PATH, "r") as f:
            _dynamic_weights = json.load(f)
            if "MARKET_BASELINES" in _dynamic_weights:
                MARKET_BASELINES.update(_dynamic_weights["MARKET_BASELINES"])
except Exception as e:
    logger.warning(f"Failed to load dynamic weights: {e}")

# Market category grouping — used by AccaFilter to enforce diversity caps
MARKET_CATEGORIES = {
    "DC_1X": "DOUBLE_CHANCE",
    "DC_X2": "DOUBLE_CHANCE",
    "DC_12": "DOUBLE_CHANCE",
    "OVER_05": "OVER_UNDER",
    "OVER_15": "OVER_UNDER",
    "OVER_25": "OVER_UNDER",
    "UNDER_25": "OVER_UNDER",
    "UNDER_35": "OVER_UNDER",
    "UNDER_45": "OVER_UNDER",
    "UNDER_55": "OVER_UNDER",
    "AH_HOME_PLUS_15": "ASIAN_HANDICAP",
    "AH_AWAY_PLUS_15": "ASIAN_HANDICAP",
    "AH_HOME_PLUS_25": "ASIAN_HANDICAP",
    "AH_AWAY_PLUS_25": "ASIAN_HANDICAP",
    "HOME_OR_OVER_25": "COMBO",
    "AWAY_OR_OVER_25": "COMBO",
    "DRAW_OR_OVER_25": "COMBO",
    "GG_YES": "BTTS",
    "GG_NO": "BTTS",
    "DNB_HOME": "DRAW_NO_BET",
    "DNB_AWAY": "DRAW_NO_BET",
    "WIN_EITHER_HALF_HOME_YES": "WIN_EITHER_HALF",
    "WIN_EITHER_HALF_AWAY_YES": "WIN_EITHER_HALF",
    "HOME_WIN_TO_NIL_YES": "WIN_TO_NIL",
    "HOME_WIN_TO_NIL_NO": "WIN_TO_NIL",
    "AWAY_WIN_TO_NIL_YES": "WIN_TO_NIL",
    "AWAY_WIN_TO_NIL_NO": "WIN_TO_NIL",
    "1X2_2UP_HOME": "EARLY_PAYOUT",
    "1X2_2UP_AWAY": "EARLY_PAYOUT",
    "1X2_1UP_HOME": "EARLY_PAYOUT",
    "1X2_1UP_AWAY": "EARLY_PAYOUT",

}


MARKET_PROBABILITY_METHODS = {
    "DC_1X": "normalized_score_matrix_result_sum",
    "DC_X2": "normalized_score_matrix_result_sum",
    "DC_12": "normalized_score_matrix_result_sum",
    "OVER_15": "normalized_score_matrix_total_goals",
    "OVER_25": "normalized_score_matrix_total_goals",
    "UNDER_25": "normalized_score_matrix_total_goals",
    "UNDER_35": "normalized_score_matrix_total_goals",
    "GG_YES": "normalized_score_matrix_btts",
    "GG_NO": "normalized_score_matrix_btts",
    "DNB_HOME": "full_time_home_win_probability_proxy",
    "DNB_AWAY": "full_time_away_win_probability_proxy",
    "HOME_OR_OVER_25": "normalized_score_matrix_union_probability",
    "AWAY_OR_OVER_25": "normalized_score_matrix_union_probability",
    "DRAW_OR_OVER_25": "normalized_score_matrix_union_probability",
    "HOME_WIN_TO_NIL_NO": "normalized_score_matrix_win_to_nil_complement",
    "AWAY_WIN_TO_NIL_NO": "normalized_score_matrix_win_to_nil_complement",
    "AH_HOME_PLUS_15": "normalized_score_matrix_handicap_cover",
    "AH_AWAY_PLUS_15": "normalized_score_matrix_handicap_cover",
    "AH_HOME_PLUS_25": "normalized_score_matrix_handicap_cover",
    "AH_AWAY_PLUS_25": "normalized_score_matrix_handicap_cover",
}


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _valid_bookmaker_odds(value: Any) -> bool:
    return _is_number(value) and float(value) > 1.0


def build_market_evaluations(
    market_probabilities: Mapping[str, float],
    viable_markets: Sequence[dict],
    evidence_items: Sequence[EvidenceItem],
    *,
    selected_verdict: Optional[str] = None,
    min_probability: float = 0.55,
) -> list:
    """Build an auditable evaluation list without changing model decisions."""
    evidence_by_field = evidence_items_by_field(evidence_items)
    viable_by_verdict = {
        candidate["verdict"]: candidate for candidate in viable_markets
    }
    reported_markets = set()
    evaluations = []

    for verdict, raw_probability in market_probabilities.items():
        try:
            selection = resolve_legacy_selection(verdict)
        except MarketRegistryError:
            continue

        model_definition = get_model_status(selection.market_id)
        reported_markets.add(selection.market_id)
        probability = (
            float(raw_probability)
            if _is_number(raw_probability)
            else None
        )
        candidate = viable_by_verdict.get(verdict)
        canonical_odds = candidate.get("bookmaker_odds") if candidate else None

        missing_inputs = []
        for required_input in model_definition.probability_inputs:
            evidence = evidence_by_field.get(required_input)
            if (
                evidence is None
                or evidence.status != EvidenceStatus.AVAILABLE
            ):
                missing_inputs.append(required_input)
        if canonical_odds is None:
            missing_inputs.append("bookmaker_odds")

        selected = bool(
            selected_verdict == verdict
            and model_definition.selectable
            and candidate is not None
        )
        rejection_reasons = []
        if not model_definition.selectable:
            rejection_reasons.append(model_definition.reason)
            selected = False
        elif probability is None:
            rejection_reasons.append(
                "No probability was produced for this market outcome."
            )
        elif candidate is None:
            if verdict not in MARKET_PROBABILITY_METHODS:
                rejection_reasons.append(
                    "Probability is reportable, but this outcome is not "
                    "enabled in the current selection candidate set."
                )
            elif probability < min_probability:
                rejection_reasons.append(
                    "Probability did not clear the minimum analytical "
                    f"threshold of {min_probability:.2f}."
                )
            else:
                rejection_reasons.append(
                    "Market did not clear the positive global-baseline "
                    "delta threshold."
                )
        elif not selected:
            if selected_verdict:
                rejection_reasons.append(
                    "A higher-ranked eligible market was selected."
                )
            else:
                rejection_reasons.append(
                    "No market was selected for this fixture."
                )

        edge_value = candidate.get("edge_pp") if candidate else None
        kelly_value = candidate.get("kelly_stake_pct") if candidate else None

        evaluations.append(
            MarketEvaluation(
                market_id=selection.market_id,
                outcome_id=selection.outcome_id,
                line=selection.line,
                model_status=model_definition.status,
                probability=probability,
                probability_method=(
                    candidate.get("probability_method")
                    if candidate
                    else MARKET_PROBABILITY_METHODS.get(verdict)
                    or model_definition.probability_method
                ),
                probability_inputs=model_definition.probability_inputs,
                pricing_inputs=model_definition.pricing_inputs,
                missing_inputs=missing_inputs,
                rejection_reasons=rejection_reasons,
                selected=selected,
                bookmaker_odds=canonical_odds,
                edge_pp=edge_value,
                kelly_stake_pct=kelly_value,
                model_fair_odds=(
                    1.0 / probability
                    if probability and probability > 0
                    else None
                ),
            )
        )

    for market_id, model_definition in MODEL_STATUS_REGISTRY.items():
        if market_id in reported_markets:
            continue
        evaluations.append(
            MarketEvaluation(
                market_id=market_id,
                outcome_id=MARKET_REGISTRY[
                    market_id
                ].supported_outcomes[0],
                line=None,
                model_status=model_definition.status,
                probability=None,
                probability_method=model_definition.probability_method,
                probability_inputs=model_definition.probability_inputs,
                pricing_inputs=model_definition.pricing_inputs,
                missing_inputs=[
                    field
                    for field in (
                        model_definition.probability_inputs
                        + model_definition.pricing_inputs
                    )
                    if (
                        evidence_by_field.get(field) is None
                        or evidence_by_field[field].status
                        != EvidenceStatus.AVAILABLE
                    )
                ],
                rejection_reasons=[
                    model_definition.reason
                    if model_definition.status
                    in {ModelStatus.DISABLED, ModelStatus.UNSUPPORTED}
                    else "No probability was produced for this market."
                ],
                selected=False,
                bookmaker_odds=None,
                edge_pp=None,
                kelly_stake_pct=None,
                model_fair_odds=None,
            )
        )

    evaluations.sort(
        key=lambda evaluation: (
            evaluation.market_id.value,
            evaluation.outcome_id.value,
            evaluation.line is None,
            evaluation.line or 0.0,
        )
    )
    return evaluations


def build_fixture_evidence_report(
    fixture_context: Mapping[str, Any],
    evidence_items: Sequence[EvidenceItem],
    market_evaluations: Sequence[MarketEvaluation],
    final_decision: DecisionStatus,
    decision_reasons: Sequence[str],
    score_matrix_audit: Optional[Mapping[str, Any]] = None,
) -> dict:
    """Serialize one deterministic evidence report with an actual generation time."""
    report = FixtureEvidenceReport(
        fixture_id=fixture_context.get("fixture_id"),
        home_team=str(fixture_context.get("home_team") or "Home"),
        away_team=str(fixture_context.get("away_team") or "Away"),
        match_date=fixture_context.get("match_date"),
        generated_at=datetime.now(timezone.utc).isoformat(),
        evidence_items=evidence_items,
        data_quality=DataQualitySummary.from_items(evidence_items),
        market_evaluations=market_evaluations,
        final_decision=final_decision,
        decision_reasons=decision_reasons,
        score_matrix_audit=score_matrix_audit,
    )
    return report.to_dict()


def build_viable_market_candidates(
    market_probabilities: dict,
    archetype_boosts: dict,
    min_probability: float = 0.55,
) -> list:
    """Build candidates without inventing edge or a fallback selection.

    The returned delta is explicitly a comparison with a global historical
    baseline. It is not bookmaker-implied edge and must not be represented as
    such. Bookmaker value calculation remains a separate stabilization task.
    """
    candidates = []
    for verdict, probability in market_probabilities.items():
        if probability < min_probability:
            continue
        try:
            selection = resolve_legacy_selection(verdict)
            model_definition = get_model_status(selection.market_id)
        except MarketRegistryError:
            continue
        if not model_definition.selectable:
            continue
        probability_method = MARKET_PROBABILITY_METHODS.get(verdict)
        if not probability_method:
            continue

        baseline = MARKET_BASELINES.get(verdict, 0.50)
        baseline_delta = round(probability - baseline, 4)
        ranking_boost = round(archetype_boosts.get(verdict, 0.0), 4)
        ranking_score = round(baseline_delta + ranking_boost, 4)
        if ranking_score <= 0:
            continue

        candidates.append({
            "verdict": verdict,
            "prob": float(probability),
            # Compatibility field: this is not genuine bookmaker edge.
            "edge": baseline_delta,
            "edge_above_baseline": baseline_delta,
            "edge_method": "global_baseline_delta",
            "ranking_boost": ranking_boost,
            "ranking_score": ranking_score,
            "is_bookmaker_edge": False,
            "edge_is_bookmaker_value": False,
            "probability_method": probability_method,
            "category": MARKET_CATEGORIES.get(verdict, "OTHER"),
            "market_id": selection.market_id.value,
            "outcome_id": selection.outcome_id.value,
            "line": selection.line,
            "display_label": selection.display_label,
            "model_fair_odds": 1.0 / probability,
            "bookmaker_odds": None,
            "edge_pp": None,
            "kelly_stake_pct": None,
            "bookmaker_quote": None,
        })

    candidates.sort(
        key=lambda candidate: candidate["ranking_score"],
        reverse=True,
    )
    return candidates


class MatchAnalyst:
    def __init__(self, form_engine, motivation_engine, weather_engine, fatigue_engine,
                 injury_engine, referee_engine, risk_engine):
        self.form_eng = form_engine
        self.motivation_engine = motivation_engine
        self.weather_engine = weather_engine
        self.fatigue_eng = fatigue_engine
        self.injury_eng = injury_engine
        self.ref_eng = referee_engine
        self.risk_eng = risk_engine
        
        self.ml_eng = MLEngine()

    def _calculate_poisson_probability(self, actual_goals: int, expected_goals: float) -> float:
        if expected_goals <= 0:
            return 1.0 if actual_goals == 0 else 0.0
        return math.exp(-expected_goals) * (expected_goals ** actual_goals) / math.factorial(actual_goals)



    def _assess_upset_risk(self, prob_home_win: float, prob_away_win: float,
                            fatigue_diff: float, referee_signal: dict,
                            avg_live_ratio: float, is_backtest: bool = False) -> dict:
        favorite_prob = max(prob_home_win, prob_away_win)

        risk = 0.0
        if favorite_prob < 0.55:
            risk += 35
        elif favorite_prob < 0.65:
            risk += 20
        else:
            risk += 8

        if fatigue_diff >= 0.30:
            risk += 25
        elif fatigue_diff >= 0.10:
            risk += 10

        if referee_signal.get("has_data") and referee_signal.get("high_volatility"):
            risk += 20

        if not is_backtest:
            if avg_live_ratio < 0.20:
                risk += 30
            elif avg_live_ratio < 0.60:
                risk += 15

        risk = min(risk, 100)
        upset_alert = risk >= 55

        return {
            "risk_score": round(risk, 1),
            "upset_alert": upset_alert,
            "stale_data": avg_live_ratio < 0.60 and not is_backtest,
        }

    def compile_master_fixture_prediction(
        self,
        fixture_context: dict,
        *,
        quote_current_time: Optional[datetime] = None,
        max_quote_age_seconds: int = DEFAULT_MAX_QUOTE_AGE_SECONDS,
    ) -> dict:
        home_team = fixture_context.get('home_team') or 'Home'
        away_team = fixture_context.get('away_team') or 'Away'
        home_id = (
            fixture_context.get('home_id')
            if fixture_context.get('home_id') is not None
            else 1
        )
        away_id = (
            fixture_context.get('away_id')
            if fixture_context.get('away_id') is not None
            else 2
        )
        match_date = fixture_context.get('match_date')
        fixture_id = (
            fixture_context.get('fixture_id')
            if fixture_context.get('fixture_id') is not None
            else 0
        )
        is_knockout = bool(fixture_context.get('is_knockout', False))
        is_backtest = bool(fixture_context.get('is_backtest', False))

        form_service = getattr(self.form_eng, 'form_svc', None) or getattr(self.form_eng, 'form_service', None)
        home_form_value = (
            form_service.get_recent_form_score(home_id, match_date)
            if form_service
            else None
        )
        away_form_value = (
            form_service.get_recent_form_score(away_id, match_date)
            if form_service
            else None
        )
        home_form_defaulted = not _is_number(home_form_value)
        away_form_defaulted = not _is_number(away_form_value)
        home_raw = (
            float(home_form_value) if not home_form_defaulted else 0.50
        )
        away_raw = (
            float(away_form_value) if not away_form_defaulted else 0.50
        )

        home_freshness = (
            form_service.get_data_freshness(home_id, match_date)
            if form_service
            else None
        )
        away_freshness = (
            form_service.get_data_freshness(away_id, match_date)
            if form_service
            else None
        )
        home_live_ratio = (
            home_freshness.get("live_ratio")
            if isinstance(home_freshness, dict)
            else None
        )
        away_live_ratio = (
            away_freshness.get("live_ratio")
            if isinstance(away_freshness, dict)
            else None
        )
        freshness_defaulted = not (
            _is_number(home_live_ratio) and _is_number(away_live_ratio)
        )
        if freshness_defaulted:
            home_live_ratio = (
                float(home_live_ratio)
                if _is_number(home_live_ratio)
                else 0.0
            )
            away_live_ratio = (
                float(away_live_ratio)
                if _is_number(away_live_ratio)
                else 0.0
            )
        avg_live_ratio = (
            float(home_live_ratio) + float(away_live_ratio)
        ) / 2

        home_last_date = form_service.get_last_match_date(home_id, match_date) if form_service else None
        away_last_date = form_service.get_last_match_date(away_id, match_date) if form_service else None

        fatigue = self.fatigue_eng.analyze_fixture_fatigue_clash(
            home_id, away_id, match_date, home_last_date, away_last_date
        )
        fatigue_value = (
            fatigue.get("fatigue_differential")
            if isinstance(fatigue, dict)
            else None
        )
        fatigue_defaulted = not _is_number(fatigue_value)
        fatigue_diff = (
            float(fatigue_value) if not fatigue_defaulted else 0.0
        )

        referee_signal = self.ref_eng.check_referee_anomaly(fixture_id)
        if not isinstance(referee_signal, dict):
            referee_signal = {}

        # Use ELO ratings instead of form data if available
        home_elo_context = fixture_context.get('home_pre_elo')
        away_elo_context = fixture_context.get('away_pre_elo')
        home_elo_available = _is_number(home_elo_context)
        away_elo_available = _is_number(away_elo_context)
        home_elo = (
            float(home_elo_context) if home_elo_available else 1500
        )
        away_elo = (
            float(away_elo_context) if away_elo_available else 1500
        )
        home_elo_source = "fixture_context"
        away_elo_source = "fixture_context"
        
        if not home_elo_available or not away_elo_available:
            db_path = "database/athena.db"
            if os.path.exists(db_path):
                try:
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT elo_rating FROM teams WHERE team_id = ? OR name = ?", (home_id, home_team))
                    h_row = cursor.fetchone()
                    if h_row and _is_number(h_row[0]):
                        home_elo = float(h_row[0])
                        home_elo_available = True
                        home_elo_source = "athena_database"
                    
                    cursor.execute("SELECT elo_rating FROM teams WHERE team_id = ? OR name = ?", (away_id, away_team))
                    a_row = cursor.fetchone()
                    if a_row and _is_number(a_row[0]):
                        away_elo = float(a_row[0])
                        away_elo_available = True
                        away_elo_source = "athena_database"
                    conn.close()
                except Exception as e:
                    logger.error(f"Failed to fetch ELO: {e}")

        if avg_live_ratio < 0.05:
            # Normalize ELO to a roughly 0.2 to 0.8 scale, where 1500 is 0.50
            # A 200 point ELO diff is very large.
            home_raw = 0.50 + ((home_elo - 1500) / 800.0)
            away_raw = 0.50 + ((away_elo - 1500) / 800.0)
            
            # Ensure boundaries
            home_raw = max(0.1, min(0.9, home_raw))
            away_raw = max(0.1, min(0.9, away_raw))

        base_home_lambda = 1.45 + (home_raw - away_raw) - (fatigue_diff * 0.5)
        base_away_mu = 1.25 + (away_raw - home_raw) + (fatigue_diff * 0.5)

        lambda_val = max(0.05, round(base_home_lambda, 3))
        mu_val = max(0.05, round(base_away_mu, 3))

        score_distribution = build_score_matrix(lambda_val, mu_val)
        score_matrix_audit = score_distribution.audit_dict()
        prob_home_win = score_distribution.home_win
        prob_away_win = score_distribution.away_win
        prob_draw = score_distribution.draw
        prob_under_35 = score_distribution.under(3.5)
        prob_over_25 = score_distribution.over(2.5)
        prob_gg = score_distribution.btts_yes
        prob_home_win_to_nil = score_distribution.home_win_to_nil
        prob_away_win_to_nil = score_distribution.away_win_to_nil

        # --- ML ENGINE INTEGRATION ---
        # ML output remains a separately evidenced ranking/risk signal. It must
        # not mutate probabilities derived from the normalized score matrix.
        ml_preds = self.ml_eng.predict(home_id, away_id, home_elo, away_elo, match_date=match_date)
        if ml_preds:
            ml_xg = ml_preds["expected_total_goals"]
            ranking_expected_goals = (
                (lambda_val + mu_val + ml_xg) / 2
            )
        else:
            ranking_expected_goals = lambda_val + mu_val

        prob_over_15 = score_distribution.over(1.5)

        stale_data = avg_live_ratio < 0.60 and not is_backtest

        bookmaker_odds_context = fixture_context.get("bookmaker_odds")
        bookmaker_quotes = parse_bookmaker_quotes(
            bookmaker_odds_context,
            current_time=quote_current_time,
            max_quote_age_seconds=max_quote_age_seconds,
        )
        bookmaker_odds_available = bool(bookmaker_quotes)
        freshness_status = EvidenceStatus.AVAILABLE
        freshness_notes = None
        if freshness_defaulted:
            freshness_status = EvidenceStatus.DEFAULTED
            freshness_notes = (
                "Missing live-data freshness was replaced by a 0.0 ratio."
            )
        elif stale_data:
            freshness_status = EvidenceStatus.STALE
            freshness_notes = (
                "Average live-data ratio is below the 0.60 freshness threshold."
            )

        evidence_items = []

        def record_evidence(
            source,
            field,
            value,
            status,
            notes=None,
            observed_at=None,
        ):
            evidence_items.append(
                EvidenceItem(
                    source=source,
                    field=field,
                    value=value,
                    status=status,
                    observed_at=observed_at,
                    notes=notes,
                )
            )

        available = EvidenceStatus.AVAILABLE
        defaulted = EvidenceStatus.DEFAULTED
        missing = EvidenceStatus.MISSING
        input_specs = (
            (
                "fixture_id",
                fixture_id,
                available
                if fixture_context.get("fixture_id") is not None
                else defaulted,
                "Missing fixture identity was replaced by 0.",
            ),
            (
                "home_team",
                home_team,
                available if fixture_context.get("home_team") else defaulted,
                "Missing home team was replaced by 'Home'.",
            ),
            (
                "away_team",
                away_team,
                available if fixture_context.get("away_team") else defaulted,
                "Missing away team was replaced by 'Away'.",
            ),
            (
                "home_id",
                home_id,
                available
                if fixture_context.get("home_id") is not None
                else defaulted,
                "Missing home team ID was replaced by 1.",
            ),
            (
                "away_id",
                away_id,
                available
                if fixture_context.get("away_id") is not None
                else defaulted,
                "Missing away team ID was replaced by 2.",
            ),
            (
                "match_date",
                match_date,
                available if match_date else missing,
                "Match date was not provided.",
            ),
            (
                "fixture_data_source",
                fixture_context.get("data_source"),
                available if fixture_context.get("data_source") else missing,
                "Fixture data source was not identified.",
            ),
            (
                "is_knockout",
                is_knockout,
                available
                if fixture_context.get("is_knockout") is not None
                else defaulted,
                "Missing knockout flag was replaced by False.",
            ),
            (
                "is_backtest",
                is_backtest,
                available
                if fixture_context.get("is_backtest") is not None
                else defaulted,
                "Missing backtest flag was replaced by False.",
            ),
        )
        for field, value, status, fallback_note in input_specs:
            record_evidence(
                "fixture_context",
                field,
                value,
                status,
                fallback_note if status != available else None,
            )

        for field, value, was_defaulted, observed_at in (
            (
                "home_form",
                home_form_value,
                home_form_defaulted,
                home_last_date,
            ),
            (
                "away_form",
                away_form_value,
                away_form_defaulted,
                away_last_date,
            ),
        ):
            record_evidence(
                "team_form_service",
                field,
                0.50 if was_defaulted else float(value),
                defaulted if was_defaulted else available,
                (
                    f"Missing {field.replace('_', ' ')} was replaced by 0.50."
                    if was_defaulted
                    else None
                ),
                str(observed_at) if observed_at is not None else None,
            )

        for field, value, source, is_available in (
            ("home_elo", home_elo, home_elo_source, home_elo_available),
            ("away_elo", away_elo, away_elo_source, away_elo_available),
        ):
            record_evidence(
                source,
                field,
                value,
                available if is_available else defaulted,
                (
                    None
                    if is_available
                    else f"Missing {field.replace('_', ' ')} was replaced by 1500."
                ),
            )

        record_evidence(
            "team_form_service",
            "live_data_freshness",
            round(avg_live_ratio, 4),
            freshness_status,
            freshness_notes,
        )
        record_evidence(
            "fatigue_engine",
            "fatigue",
            fatigue_diff,
            defaulted if fatigue_defaulted else available,
            (
                "Missing fatigue differential was replaced by 0.0."
                if fatigue_defaulted
                else None
            ),
        )
        referee_available = bool(referee_signal.get("has_data"))
        record_evidence(
            "referee_engine",
            "referee_data",
            referee_signal if referee_available else None,
            available if referee_available else missing,
            None if referee_available else "No referee evidence was available.",
        )
        record_evidence(
            "ml_engine",
            "ml_predictions",
            True if ml_preds else None,
            available if ml_preds else missing,
            None if ml_preds else "No ML prediction was available.",
        )
        record_evidence(
            "fixture_context",
            "bookmaker_odds",
            [quote.to_dict() for quote in bookmaker_quotes]
            if bookmaker_odds_available else None,
            available if bookmaker_odds_available else missing,
            (
                None
                if bookmaker_odds_available
                else "No validated current bookmaker odds were provided."
            ),
        )
        record_evidence(
            "normalized_score_matrix",
            "score_matrix",
            score_matrix_audit,
            available,
            "Independent-Poisson matrix normalized after adaptive tail truncation.",
        )
        
        # Default heuristic risk
        risk_assessment = self._assess_upset_risk(prob_home_win, prob_away_win, fatigue_diff, referee_signal, avg_live_ratio, is_backtest)
        risk_score = risk_assessment["risk_score"]
        upset_alert = risk_assessment["upset_alert"]
        
        # Override with Confidence Meta-Model if available
        if ml_preds and ml_preds.get("reliability_score") is not None:
            reliability = ml_preds["reliability_score"]
            risk_score = (1.0 - reliability) * 100
            upset_alert = reliability < 0.50 # Adjusted ML confidence threshold to align with 50% base rate

        # --- COMPREHENSIVE MARKET PROBABILITY CALCULATIONS ---
        prob_over_05 = score_distribution.over(0.5)
        prob_under_25 = score_distribution.under(2.5)
        prob_under_45 = score_distribution.under(4.5)
        prob_under_55 = score_distribution.under(5.5)

        prob_home_plus_1_5 = score_distribution.asian_handicap_cover(
            "HOME",
            1.5,
        )
        prob_away_plus_1_5 = score_distribution.asian_handicap_cover(
            "AWAY",
            1.5,
        )
        prob_home_plus_2_5 = score_distribution.asian_handicap_cover(
            "HOME",
            2.5,
        )
        prob_away_plus_2_5 = score_distribution.asian_handicap_cover(
            "AWAY",
            2.5,
        )

        prob_draw_or_over_25 = score_distribution.result_or_over("DRAW")
        prob_home_or_over_25 = score_distribution.result_or_over("HOME")
        prob_away_or_over_25 = score_distribution.result_or_over("AWAY")

        prob_1x = score_distribution.double_chance_home_or_draw
        prob_x2 = score_distribution.double_chance_draw_or_away
        prob_12 = score_distribution.double_chance_home_or_away

        # --- BUILD CANDIDATES WITH A GLOBAL-BASELINE DELTA ---
        # Each market is only included if its fixture probability exceeds
        # the global baseline, AND the probability meets a minimum threshold.
        # This delta is not bookmaker-implied edge or evidence of betting value.
        
        all_market_probs = {
            "DC_1X": prob_1x,
            "DC_X2": prob_x2,
            "DC_12": prob_12,
            "OVER_15": prob_over_15,
            "OVER_25": prob_over_25,
            "UNDER_25": prob_under_25,
            "UNDER_35": prob_under_35,
            "GG_YES": prob_gg,
            "GG_NO": score_distribution.btts_no,
            "DNB_HOME": prob_home_win,
            "DNB_AWAY": prob_away_win,
            # Win-either-half is intentionally disabled until ATHENA has a
            # valid half-by-half score model. Full-time win probability * 1.35
            # is not a defensible probability calculation.
            "HOME_OR_OVER_25": prob_home_or_over_25,
            "AWAY_OR_OVER_25": prob_away_or_over_25,
            "DRAW_OR_OVER_25": prob_draw_or_over_25,
            "HOME_WIN_TO_NIL_NO": score_distribution.sum_where(
                lambda home, away: not (home > 0 and away == 0)
            ),
            "AWAY_WIN_TO_NIL_NO": score_distribution.sum_where(
                lambda home, away: not (away > 0 and home == 0)
            ),
            "AH_HOME_PLUS_15": prob_home_plus_1_5,
            "AH_AWAY_PLUS_15": prob_away_plus_1_5,
            "AH_HOME_PLUS_25": prob_home_plus_2_5,
            "AH_AWAY_PLUS_25": prob_away_plus_2_5,
        }

        evaluation_market_probs = {
            "HOME_WIN": prob_home_win,
            "DRAW": prob_draw,
            "AWAY_WIN": prob_away_win,
            "OVER_05": prob_over_05,
            **all_market_probs,
            "UNDER_45": prob_under_45,
            "UNDER_55": prob_under_55,
            "HOME_WIN_TO_NIL_YES": prob_home_win_to_nil,
            "AWAY_WIN_TO_NIL_YES": prob_away_win_to_nil,
        }

        # Early-payout markets are intentionally not modeled here. Reusing the
        # full-time win probability ignores the bookmaker's lead-path and
        # settlement rules, so those selections remain unavailable for now.

        # --- ARCHETYPE ENGINE ---
        # Classify the match state and boost specific variance-reducing markets
        total_xg = ranking_expected_goals
        elo_diff = abs(home_elo - away_elo)
        
        archetype_boosts = {}
        
        # 1. High Event / Chaos
        if total_xg > 2.8 and 50 < elo_diff < 350:
            archetype_boosts["AWAY_OR_OVER_25"] = 0.15
            archetype_boosts["HOME_OR_OVER_25"] = 0.15
            archetype_boosts["GG_YES"] = 0.10
            archetype_boosts["OVER_25"] = 0.15
            
        # 2. Low Event / Tactical Stalemate
        if total_xg < 2.2:
            archetype_boosts["UNDER_25"] = 0.25
            archetype_boosts["UNDER_35"] = 0.15
            archetype_boosts["DNB_HOME"] = 0.18
            archetype_boosts["DNB_AWAY"] = 0.18
            
        # 3. Smart Upset Pivoting ("The Milan Scenario")
        # If ATHENA detects an upset trap against a heavy favorite, brilliantly pivot to the underdog.
        if upset_alert:
            if prob_home_win > prob_away_win:
                # Home is heavily favored but vulnerable! Pivot to Away underdog options.
                archetype_boosts["DC_X2"] = 0.25
                archetype_boosts["DNB_AWAY"] = 0.20
                archetype_boosts["AH_AWAY_PLUS_15"] = 0.25
                archetype_boosts["AH_AWAY_PLUS_25"] = 0.15
            else:
                # Away is heavily favored but vulnerable! Pivot to Home underdog options.
                archetype_boosts["DC_1X"] = 0.25
                archetype_boosts["DNB_HOME"] = 0.20
                archetype_boosts["AH_HOME_PLUS_15"] = 0.25
                archetype_boosts["AH_HOME_PLUS_25"] = 0.15

        # Minimum probability threshold per fixture to be considered viable
        MIN_PROB = 0.55

        viable_markets = build_viable_market_candidates(
            all_market_probs,
            archetype_boosts,
            min_probability=MIN_PROB,
        )
        selected_verdict = viable_markets[0]["verdict"] if viable_markets else None

        # Candidates are sorted by baseline delta, which is not bookmaker value.

        if not viable_markets:
            market_evaluations = build_market_evaluations(
                evaluation_market_probs,
                viable_markets,
                evidence_items,
                selected_verdict=None,
                min_probability=MIN_PROB,
            )
            no_bet_reasons = [
                "No market cleared the minimum probability and "
                "positive baseline-delta thresholds."
            ]
            return {
                "decision_status": DecisionStatus.NO_BET.value,
                "recommended_analytical_verdict": None,
                "edge_differential": None,
                "edge_is_bookmaker_value": False,
                "accumulator_eligible_selection": None,
                "upset_alert": upset_alert,
                "risk_score": risk_score,
                "stale_data": stale_data,
                "viable_markets": [],
                "reasoning_verdicts": [],
                "no_bet_reasons": no_bet_reasons,
                "evidence_report": build_fixture_evidence_report(
                    fixture_context,
                    evidence_items,
                    market_evaluations,
                    DecisionStatus.NO_BET,
                    no_bet_reasons,
                    score_matrix_audit=score_matrix_audit,
                ),
            }
            
        # Model F: Confidence Meta-Model Hard Filter
        # If the ML Meta-Model flags this as an Upset Risk (Reliability < 50%),
        # we set upset_alert to True. AccaFilter may reject the fixture in strict
        # mode; no market is created when the validated candidate list is empty.

        best_market = viable_markets[0]
        best_selection = resolve_legacy_selection(best_market["verdict"])
        pricing, pricing_reason = price_selection(
            best_selection,
            best_market["prob"],
            bookmaker_quotes,
        )
        if pricing is not None:
            best_market.update({
                "bookmaker_odds": round(
                    pricing.bookmaker_quote.bookmaker_odds, 4
                ),
                "bookmaker_quote": pricing.bookmaker_quote.to_dict(),
                "bookmaker_probability": round(
                    pricing.bookmaker_probability, 4
                ),
                "edge_pp": round(pricing.edge_pp, 4),
                "kelly_stake_pct": round(pricing.kelly_stake_pct, 4),
                "edge_method": pricing.method,
                "is_bookmaker_edge": True,
                "edge_is_bookmaker_value": True,
            })

        pricing_checks_pass = (
            pricing is not None
            and pricing.edge_pp >= 2.0
            and risk_score <= 85
            and avg_live_ratio >= 0.40
        )
        if pricing is None:
            decision_status = DecisionStatus.ANALYTICAL_CANDIDATE
        elif pricing_checks_pass:
            decision_status = DecisionStatus.BET
        else:
            decision_status = DecisionStatus.NO_BET

        decision_reasons = [
            f"{best_market['verdict']} ranked first among markets that "
            "cleared the analytical selection thresholds."
        ]
        if pricing is None:
            decision_reasons.append(pricing_reason)
        elif pricing.edge_pp < 2.0:
            decision_reasons.append(
                "The de-vigged bookmaker edge did not clear the 2.0pp "
                "eligibility threshold."
            )
        if risk_score > 85:
            decision_reasons.append(
                "The fixture failed the configured maximum risk score of 85."
            )
        if avg_live_ratio < 0.40:
            decision_reasons.append(
                "The fixture failed the configured minimum data freshness of 0.40."
            )

        market_evaluations = build_market_evaluations(
            evaluation_market_probs,
            viable_markets,
            evidence_items,
            selected_verdict=selected_verdict,
            min_probability=MIN_PROB,
        )
        no_bet_reasons = (
            decision_reasons if decision_status == DecisionStatus.NO_BET else []
        )
        accumulator_eligible_selection = (
            dict(best_market)
            if decision_status == DecisionStatus.BET
            else None
        )
        edge_is_bookmaker_value = pricing is not None

        return {
            "decision_status": decision_status.value,
            "recommended_analytical_verdict": best_market["verdict"],
            "edge_differential": best_market["edge"],
            "edge_is_bookmaker_value": edge_is_bookmaker_value,
            "bookmaker_odds": best_market["bookmaker_odds"],
            "bookmaker_probability": best_market.get(
                "bookmaker_probability"
            ),
            "edge_pp": best_market["edge_pp"],
            "kelly_stake_pct": best_market["kelly_stake_pct"],
            "upset_alert": upset_alert,
            "risk_score": risk_score,
            "stale_data": stale_data,
            "viable_markets": viable_markets,
            "accumulator_eligible_selection": (
                accumulator_eligible_selection
            ),
            "reasoning_verdicts": [{
                "label": best_market["display_label"],
                "market_id": best_market["market_id"],
                "outcome_id": best_market["outcome_id"],
                "line": best_market["line"],
                "status": decision_status.value,
                "model_probability": best_market["prob"],
                "model_fair_odds": best_market["model_fair_odds"],
                "bookmaker_odds": best_market["bookmaker_odds"],
                "bookmaker_probability": best_market.get(
                    "bookmaker_probability"
                ),
                "edge_pp": best_market["edge_pp"],
                "kelly_stake_pct": best_market["kelly_stake_pct"],
                "reason": decision_reasons[-1],
            }],
            "no_bet_reasons": no_bet_reasons,
            "evidence_report": build_fixture_evidence_report(
                fixture_context,
                evidence_items,
                market_evaluations,
                decision_status,
                decision_reasons,
                score_matrix_audit=score_matrix_audit,
            ),
        }
