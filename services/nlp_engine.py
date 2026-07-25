import os
import requests
from bs4 import BeautifulSoup
from textblob import TextBlob
from googlesearch import search
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

class NLPEngine:
    def __init__(self):
        self.google_api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
        self.google_cx = os.getenv("GOOGLE_SEARCH_CX")
        
        self.negative_keywords = ["injured", "injury", "out", "missing", "doubt", "ruled out", "suspended", "sidelined"]
        self.positive_keywords = ["boost", "return", "back", "recovered", "fit", "squad looks strong"]
        
        self.motivation_keywords = ["must win", "relegation battle", "title race", "derby", "revenge", "crucial", "cup final", "desperate"]
        self.fatigue_keywords = ["tired", "rested", "rotation", "heavy legs", "schedule", "congested", "focused on champions league", "rotated", "b team", "prioritize"]
        self.pressure_keywords = ["sack", "under pressure", "crisis", "must improve", "fans turning", "must deliver", "poor form", "managerial pressure"]
        
    def _search_google(self, query, num_results=3):
        """Search Google and return URLs."""
        urls = []
        if self.google_api_key and self.google_cx:
            # Use Google Custom Search API
            try:
                url = f"https://www.googleapis.com/customsearch/v1?key={self.google_api_key}&cx={self.google_cx}&q={query}&num={num_results}"
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    for item in data.get("items", []):
                        urls.append(item.get("link"))
                    return urls
                else:
                    logger.warning(f"Google API Error {response.status_code}: Falling back to scraper.")
            except Exception as e:
                logger.error(f"Google API exception: {e}")
                
        # Fallback to free scraper if no CX or API fails
        if not urls:
            try:
                for j in search(query, num_results=num_results, sleep_interval=2):
                    urls.append(j)
            except Exception as e:
                logger.error(f"Google scraper exception: {e}")
            
        return urls
        
    def _scrape_url(self, url):
        """Scrape text content from a URL."""
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                # Extract text from paragraphs
                paragraphs = soup.find_all('p')
                text = " ".join([p.get_text() for p in paragraphs])
                return text
        except Exception:
            pass
        return ""
        
    def analyze_fixture(self, home_team, away_team):
        """
        Analyze news for a fixture and return sentiment and risk metrics.
        """
        query = f"{home_team} vs {away_team} preview predictions team news football"
        logger.info(f"🔍 NLP Web Search: {query}")
        
        urls = self._search_google(query, num_results=2)
        
        combined_text = ""
        for url in urls:
            logger.debug(f"Scraping: {url}")
            combined_text += self._scrape_url(url) + " "
            
        if not combined_text.strip():
            return {
                "sentiment": 0.0, 
                "absence_risk": 0, 
                "nlp_edge": 0.0,
                "motivation_score": 0,
                "fatigue_score": 0,
                "pressure_score": 0
            }
            
        blob = TextBlob(combined_text)
        sentiment = blob.sentiment.polarity
        
        # Keyword matching
        text_lower = combined_text.lower()
        neg_count = sum(text_lower.count(kw) for kw in self.negative_keywords)
        pos_count = sum(text_lower.count(kw) for kw in self.positive_keywords)
        
        mot_count = sum(text_lower.count(kw) for kw in self.motivation_keywords)
        fat_count = sum(text_lower.count(kw) for kw in self.fatigue_keywords)
        press_count = sum(text_lower.count(kw) for kw in self.pressure_keywords)
        
        absence_risk = min(neg_count * 5, 30)  # Cap absence risk
        nlp_edge = (pos_count - neg_count) * 0.02
        
        motivation_score = mot_count * 3
        fatigue_score = fat_count * 4
        pressure_score = press_count * 3
        
        logger.info(
            f"📝 NLP Context -> Sent: {sentiment:.2f} | Abs: {absence_risk} | "
            f"Motiv: {motivation_score} | Fat: {fatigue_score} | Press: {pressure_score} | Edge: {nlp_edge:.2f}"
        )
        
        return {
            "sentiment": sentiment,
            "absence_risk": absence_risk,
            "nlp_edge": nlp_edge,
            "motivation_score": motivation_score,
            "fatigue_score": fatigue_score,
            "pressure_score": pressure_score
        }
