import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app, _fixtures_cache


class ApiFixtureCacheTests(unittest.TestCase):
    def setUp(self):
        _fixtures_cache.clear()

    def test_fixtures_and_leagues_reuse_cached_scrape(self):
        with patch("api.server.FotMobAdvancedScraper") as mock_scraper_cls:
            mock_scraper = mock_scraper_cls.return_value
            mock_scraper.fetch_upcoming_matches.return_value = [
                {"league": "Premier League", "match_date": "2026-07-25T15:00:00Z"},
                {"league": "LaLiga", "match_date": "2026-07-25T18:00:00Z"},
            ]
            client = TestClient(app)

            fixtures_response = client.get("/api/fixtures?days=3")
            leagues_response = client.get("/api/leagues?days=3")

            self.assertEqual(fixtures_response.status_code, 200)
            self.assertEqual(leagues_response.status_code, 200)
            self.assertEqual(mock_scraper.fetch_upcoming_matches.call_count, 1)
            self.assertEqual(leagues_response.json()["leagues"], ["LaLiga", "Premier League"])


if __name__ == "__main__":
    unittest.main()
