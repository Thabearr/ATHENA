import logging
from database.database import get_db_connection

logger = logging.getLogger("athena.team_form_service")

class TeamFormService:
    def __init__(self):
        pass

    def get_recent_raw_form(self, team_id: int, limit: int = 5) -> str:
        query = """
            SELECT home_team_id, away_team_id, home_score, away_score 
            FROM fixtures 
            WHERE (home_team_id = ? OR away_team_id = ?) AND status = 'FT'
            ORDER BY match_date DESC LIMIT ?
        """
        form_chars = []
        try:
            with get_db_connection() as conn:
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
            
        return "".join(form_chars[::-1])
