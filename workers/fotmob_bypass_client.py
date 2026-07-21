"""
FotMob Bypass Client - TLS Fingerprint Spoofing + Header Rotation
Queries FotMob's internal Next.js /api/data/* endpoints.
"""
import logging
import time
from typing import Optional, Dict, Any, List
from curl_cffi import requests as cffi_requests
from fake_useragent import UserAgent

logger = logging.getLogger("athena.fotmob_bypass")

# FotMob's new internal Next.js API base
FOTMOB_BASE = "https://www.fotmob.com"

# Endpoints discovered via JS bundle analysis
ENDPOINTS = {
    "matches":       "/api/data/matches",
    "match_details": "/api/data/matchDetails",
    "all_leagues":   "/api/data/allLeagues",
    "match_lineup":  "/api/data/match/lineup",
    "match_preview": "/api/data/match/preview",
    "match_shotmap": "/api/data/match/shotmap",
    "match_score":   "/api/data/match-score",
    "league_data":   "/api/data/leagueDataForMatch",
    "search":        "/api/data/search/suggest",
}


class FotmobBypassClient:
    """
    A resilient HTTP client that bypasses FotMob's Cloudflare + API protections.
    
    Uses curl_cffi to spoof Chrome's TLS fingerprint and fake_useragent
    for dynamic User-Agent rotation. All requests mimic a real browser session.
    """

    def __init__(self, proxies: Optional[Dict[str, str]] = None):
        self.proxies = proxies
        # Suppress fake_useragent fallback warnings by using a fixed fallback
        try:
            self.ua = UserAgent(
                os=['windows', 'macos'],
                browsers=['chrome', 'safari', 'edge'],
                fallback="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        except Exception:
            self.ua = None

        # curl_cffi session with Chrome 120 TLS fingerprint
        self.session = cffi_requests.Session(impersonate="chrome120")
        if self.proxies:
            self.session.proxies = self.proxies

    def _get_headers(self) -> Dict[str, str]:
        """Generate realistic browser headers with rotating User-Agent."""
        if self.ua:
            try:
                user_agent = self.ua.random
            except Exception:
                user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        else:
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

        return {
            "User-Agent": user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-GB,en;q=0.9",
            "Referer": f"{FOTMOB_BASE}/matches",
            "Origin": FOTMOB_BASE,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Cache-Control": "no-cache",
        }

    # ------------------------------------------------------------------ #
    #  PUBLIC API METHODS                                                  #
    # ------------------------------------------------------------------ #

    def fetch_matches_by_date(self, date_str: str) -> Optional[Dict[str, Any]]:
        """
        Fetch all matches for a given date.
        
        Args:
            date_str: Date in YYYYMMDD format (e.g. "20260721")
        
        Returns:
            Dict with keys: 'leagues' (list of league dicts with matches), 'date'
        """
        url = f"{FOTMOB_BASE}{ENDPOINTS['matches']}?date={date_str}"
        return self._execute_request(url)

    def fetch_matches_today(self) -> Optional[Dict[str, Any]]:
        """Fetch all of today's matches (no date param needed)."""
        url = f"{FOTMOB_BASE}{ENDPOINTS['matches']}"
        return self._execute_request(url)

    def fetch_match_details(self, match_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch deep match details (lineups, weather, stats, shotmap, etc).
        
        Returns dict with keys: general, header, content (lineup, weather, stats, etc)
        """
        url = f"{FOTMOB_BASE}{ENDPOINTS['match_details']}?matchId={match_id}"
        return self._execute_request(url)

    def fetch_all_leagues(self) -> Optional[Dict[str, Any]]:
        """
        Fetch the full FotMob league directory.
        
        Returns dict with keys: popular, international, countries
        """
        url = f"{FOTMOB_BASE}{ENDPOINTS['all_leagues']}"
        return self._execute_request(url)

    def fetch_match_lineup(self, match_id: int) -> Optional[Dict[str, Any]]:
        """Fetch lineup data for a specific match."""
        url = f"{FOTMOB_BASE}{ENDPOINTS['match_lineup']}?matchId={match_id}"
        return self._execute_request(url)

    def fetch_match_preview(self, match_id: int) -> Optional[Dict[str, Any]]:
        """Fetch match preview data."""
        url = f"{FOTMOB_BASE}{ENDPOINTS['match_preview']}?matchId={match_id}"
        return self._execute_request(url)

    # ------------------------------------------------------------------ #
    #  INTERNAL REQUEST ENGINE                                             #
    # ------------------------------------------------------------------ #

    def _execute_request(
        self, url: str, retries: int = 3, base_delay: float = 1.0
    ) -> Optional[Dict[str, Any]]:
        """
        Execute an HTTP GET with retry logic, header rotation, and exponential backoff.
        """
        for attempt in range(retries):
            headers = self._get_headers()
            try:
                response = self.session.get(url, headers=headers, timeout=15)

                if response.status_code == 200:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct.lower():
                        return response.json()
                    else:
                        logger.warning(
                            f"FotMob returned 200 but non-JSON content-type: {ct} for {url}"
                        )
                        return None

                elif response.status_code == 429:
                    # Rate limited — exponential backoff
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"FotMob rate-limited (429). Backing off {delay:.1f}s "
                        f"(attempt {attempt + 1}/{retries})"
                    )
                    time.sleep(delay)

                elif response.status_code in [403, 404]:
                    logger.warning(
                        f"FotMob {response.status_code} on attempt "
                        f"{attempt + 1}/{retries}. URL: {url}"
                    )
                else:
                    logger.error(
                        f"Unexpected status {response.status_code} for {url}"
                    )

            except Exception as e:
                logger.error(
                    f"Request error on attempt {attempt + 1}/{retries}: {e}"
                )
                time.sleep(base_delay)

        logger.error(f"Failed to fetch {url} after {retries} retries.")
        return None
