import logging
from database.database import Database

logger = logging.getLogger("athena.team_form_service")

class TeamFormService:
    def __init__(self):
        self.db = Database()

    def get_recent_raw_form(self, team_id: int, limit: int = 5) -> str:
        """
        Queries fixtures and maps them to their respective match results 
        by joining text team identities against unique team IDs.
        """
        query = """
            SELECT t_home.team_id, t_away.team_id, r.home_score, r.away_score 
            FROM fixtures f
            JOIN results r ON f.fixture_id = r.fixture_id
            LEFT JOIN teams t_home ON f.home_team = t_home.name
            LEFT JOIN teams t_away ON f.away_team = t_away.name
            WHERE (t_home.team_id = ? OR t_away.team_id = ?) 
              AND (f.status = 'FT' OR r.finished = 1)
            ORDER BY f.match_date DESC LIMIT ?
        """
        form_chars = []
        try:
            with self.db.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (team_id, team_id, limit))
                matches = cursor.fetchall()
                
                for row in matches:
                    h_id, a_id, h_score, a_score = row
                    if h_score is None or a_score is None:
                        continue
                    if h_id == team_id:
                        if h_score > a_score: form_chars.append('W')
                        elif h_score == a_score: form_chars.append('D')
                        else: form_chars.append('L')
                    else:
                        if a_score > h_score: form_chars.append('W')
                        elif a_score == h_score: form_chars.append('D')
                        else: form_chars.append('L')
        except Exception as e:
            logger.error(f"Error compiling form sequence for team {team_id}: {e}")
            
        return "".join(form_chars[::-1]) # Chronological sequence layout
