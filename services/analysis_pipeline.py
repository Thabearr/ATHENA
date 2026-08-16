import logging
import re
from datetime import datetime, timedelta
from domain.markets import DecisionStatus
from database.database import Database
from intelligence.match_analyst import MatchAnalyst
from services.team_form_service import TeamFormService

logger = logging.getLogger("athena.analysis_pipeline")

# Assume a match lasts at most this long (kickoff to full time + stoppage).
# Anything older than this is treated as over, regardless of what the
# 'status' column says — this protects against fixtures getting stuck
# forever if a data source's date-range window moves past them before
# their status ever gets updated to finished.
MAX_MATCH_DURATION_HOURS = 3

LEGACY_RUNTIME_AUTHORIZATION_STATE = (
    "ANALYSIS_ONLY_REVIEWED_SUCCESSOR_RUNTIME_NOT_AUTHORIZED"
)
LEGACY_RUNTIME_BET_BLOCK_REASON = (
    "The legacy heuristic MatchAnalyst path is analysis-only. Reviewed "
    "successor model, source, pricing, selection, and BET authorization has "
    "not been granted to this runtime path."
)


def apply_runtime_authorization(analysis: dict) -> dict:
    """Fail closed when the legacy analyzer attempts to emit an executable BET.

    The legacy analyzer remains useful for diagnostics while the reviewed
    successor pipeline is being completed, but it must not outrun the reviewed
    model/source/pricing authorization chain. Analytical evidence is preserved;
    only execution authority is removed.
    """
    safe = dict(analysis or {})
    if safe.get("decision_status") != DecisionStatus.BET.value:
        return safe

    safe["analytical_decision_status"] = DecisionStatus.BET.value
    safe["decision_status"] = DecisionStatus.ANALYTICAL_CANDIDATE.value
    safe["accumulator_eligible_selection"] = None
    safe["runtime_authorization_state"] = LEGACY_RUNTIME_AUTHORIZATION_STATE
    safe["runtime_authorization_reasons"] = [LEGACY_RUNTIME_BET_BLOCK_REASON]

    reasons = list(safe.get("no_bet_reasons") or [])
    if LEGACY_RUNTIME_BET_BLOCK_REASON not in reasons:
        reasons.append(LEGACY_RUNTIME_BET_BLOCK_REASON)
    safe["no_bet_reasons"] = reasons

    verdicts = []
    for verdict in safe.get("reasoning_verdicts") or []:
        if isinstance(verdict, dict):
            item = dict(verdict)
            if item.get("status") == DecisionStatus.BET.value:
                item["status"] = DecisionStatus.ANALYTICAL_CANDIDATE.value
            verdicts.append(item)
        else:
            verdicts.append(verdict)
    if "reasoning_verdicts" in safe:
        safe["reasoning_verdicts"] = verdicts

    report = safe.get("evidence_report")
    if isinstance(report, dict):
        report = dict(report)
        report["analytical_decision_before_runtime_gate"] = report.get(
            "final_decision"
        )
        report["final_decision"] = DecisionStatus.ANALYTICAL_CANDIDATE.value
        report_reasons = list(report.get("decision_reasons") or [])
        if LEGACY_RUNTIME_BET_BLOCK_REASON not in report_reasons:
            report_reasons.append(LEGACY_RUNTIME_BET_BLOCK_REASON)
        report["decision_reasons"] = report_reasons
        report["runtime_authorization_state"] = (
            LEGACY_RUNTIME_AUTHORIZATION_STATE
        )
        safe["evidence_report"] = report

    return safe


class AnalysisPipeline:
    def __init__(self, match_analyst: MatchAnalyst, form_service: TeamFormService):
        self.db = Database()
        self.analyst = match_analyst
        self.form_svc = form_service

    def _resolve_team_id(self, team_name: str) -> int:
        try:
            query = "SELECT team_id FROM teams WHERE name = ? LIMIT 1"
            with self.db.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (team_name,))
                row = cursor.fetchone()
                return row[0] if row else abs(hash(team_name)) % 1000
        except Exception:
            return abs(hash(team_name)) % 1000

    def _parse_match_date(self, date_string: str):
        if not date_string:
            return None
        try:
            cleaned = date_string.strip()
            if 'T' in cleaned:
                if '+' in cleaned:
                    cleaned = cleaned.split('+')[0]
                if cleaned.endswith('Z'):
                    cleaned = cleaned[:-1]
                if '.' in cleaned:
                    cleaned = cleaned.split('.')[0]
                return datetime.strptime(cleaned, "%Y-%m-%dT%H:%M:%S")
            else:
                return datetime.strptime(cleaned.split()[0], "%Y-%m-%d")
        except Exception:
            return None

    def fetch_upcoming_fixtures(self, limit: int = 200) -> list:
        query = """
            SELECT fixture_id, league, season, home_team, away_team, match_date, data_source
            FROM fixtures
            WHERE status NOT IN ('FT', 'AET', 'PEN')
            ORDER BY match_date ASC LIMIT ?
        """
        results = []
        try:
            with self.db.connect() as conn:
                conn.row_factory = lambda cursor, row: dict(
                    (cursor.description[i][0], value) for i, value in enumerate(row)
                )
                cursor = conn.cursor()
                cursor.execute(query, (limit,))
                results = cursor.fetchall()
        except Exception as e:
            logger.error(f"Failed to fetch upcoming fixtures from DB: {e}")

        # Local safety net: drop anything whose kickoff has clearly already
        # passed, even if its stored 'status' never got updated by a loader.
        now = datetime.utcnow()
        still_upcoming = []
        for fix in results:
            match_dt = self._parse_match_date(fix.get("match_date"))
            if match_dt is None:
                still_upcoming.append(fix)  # can't parse it — don't silently drop, just pass through
                continue
            if match_dt + timedelta(hours=MAX_MATCH_DURATION_HOURS) > now:
                still_upcoming.append(fix)

        dropped = len(results) - len(still_upcoming)
        if dropped:
            logger.info(f"Filtered out {dropped} fixture(s) whose kickoff has already passed.")

        if not still_upcoming:
            logger.warning(
                "No real fixtures found in the database. Not fabricating "
                "placeholder matches — run the fixture loader first."
            )

        return still_upcoming

    def run_pipeline_snapshot(self, execution_limit: int = 150, override_fixtures: list = None) -> list:
        if override_fixtures is not None:
            upcoming = override_fixtures
        else:
            upcoming = self.fetch_upcoming_fixtures(limit=execution_limit)

        analyzed_batch = []
        youth_pattern = re.compile(r'\b[uU]\d{2}\b')
        womens_blacklist = [" W ", "Women", "Womens", "Femenino", "Frauen", " Féminines", "Fem."]

        for fix in upcoming:
            home_team = str(fix.get('home_team') or 'Unknown Home')
            away_team = str(fix.get('away_team') or 'Unknown Away')
            league_name = str(fix.get('league') or '').lower()

            if any(b.lower() in home_team.lower() or b.lower() in away_team.lower() for b in womens_blacklist):
                continue
            if youth_pattern.search(home_team) or youth_pattern.search(away_team):
                continue

            context_payload = {
                "fixture_id": fix.get("fixture_id", 0),
                "home_team": home_team,
                "away_team": away_team,
                "home_id": self._resolve_team_id(home_team),
                "away_id": self._resolve_team_id(away_team),
                "match_date": fix.get("match_date", ""),
                "data_source": fix.get("data_source"),
                "is_knockout": any(k in league_name for k in ["cup", "champions league", "playoff", "knockout", "qualif", "conference"]),
            }

            if fix.get("bookmaker_odds") is not None:
                context_payload["bookmaker_odds"] = fix["bookmaker_odds"]

            if "home_pre_elo" in fix and fix["home_pre_elo"] is not None:
                context_payload["home_pre_elo"] = fix["home_pre_elo"]
                context_payload["away_pre_elo"] = fix["away_pre_elo"]

            try:
                analysis = apply_runtime_authorization(
                    self.analyst.compile_master_fixture_prediction(
                        context_payload
                    )
                )
                analyzed_batch.append({
                    "fixture_id": fix.get("fixture_id", 0),
                    "fixture": f"{home_team} vs {away_team}",
                    "home_team": home_team,
                    "away_team": away_team,
                    "league": fix.get("league", "Unknown"),
                    "match_date": fix.get("match_date", ""),
                    "decision_status": analysis.get(
                        "decision_status",
                        DecisionStatus.NO_BET.value,
                    ),
                    "analytical_decision_status": analysis.get(
                        "analytical_decision_status"
                    ),
                    "runtime_authorization_state": analysis.get(
                        "runtime_authorization_state"
                    ),
                    "runtime_authorization_reasons": analysis.get(
                        "runtime_authorization_reasons", []
                    ),
                    "upset_alert": analysis.get("upset_alert", False),
                    "risk_score": analysis.get("risk_score", 0.0),
                    "stale_data": analysis.get("stale_data", False),
                    "edge": analysis.get("edge_differential"),
                    "edge_is_bookmaker_value": analysis.get(
                        "edge_is_bookmaker_value",
                        False,
                    ),
                    "bookmaker_odds": analysis.get("bookmaker_odds"),
                    "bookmaker_probability": analysis.get(
                        "bookmaker_probability"
                    ),
                    "edge_pp": analysis.get("edge_pp"),
                    "kelly_stake_pct": analysis.get(
                        "kelly_stake_pct"
                    ),
                    "verdict": analysis.get("recommended_analytical_verdict"),
                    "viable_markets": analysis.get("viable_markets", []),
                    "accumulator_eligible_selection": analysis.get(
                        "accumulator_eligible_selection"
                    ),
                    "no_bet_reasons": analysis.get("no_bet_reasons", []),
                    "evidence_report": analysis.get("evidence_report"),
                    "source": fix.get("data_source", "unknown"),
                })
            except Exception as e:
                logger.error(f"Error compiling prediction for {home_team} vs {away_team}: {e}")
                continue

        return analyzed_batch
