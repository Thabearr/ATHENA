#!/usr/bin/env python3
"""
Quick test script to validate FotMob scraper and data pipeline.
"""

import asyncio
import logging
from datetime import datetime

from workers.fotmob_advanced_scraper import FotMobAdvancedScraper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_fotmob():
    """Test FotMob scraper data extraction."""
    print("\n" + "="*70)
    print("      🧪 TESTING FOTMOB ADVANCED SCRAPER 🧪")
    print("="*70 + "\n")
    
    scraper = FotMobAdvancedScraper()
    
    # Fetch 3 days of matches
    print("📥 Fetching FotMob fixtures for next 3 days...\n")
    matches = await scraper.fetch_upcoming_matches(days_ahead=3)
    
    if not matches:
        print("❌ No matches fetched! This is the problem.\n")
        print("Diagnostics:")
        print("  - Check if fotmob package is installed: pip install fotmob")
        print("  - Check if FotMob endpoints are accessible")
        print("  - Check internet connection")
        return
    
    print(f"✅ Successfully fetched {len(matches)} matches!\n")
    
    # Display first 5 matches
    print("📊 Sample Matches (First 5):\n")
    for i, match in enumerate(matches[:5], 1):
        print(f"{i}. {match['home_team']} vs {match['away_team']}")
        print(f"   League: {match.get('league', '?')}")
        print(f"   Date: {match.get('match_date', '?')}")
        print(f"   Status: {match.get('status', '?')}")
        print(f"   Injuries (Home): {len(match.get('home_injuries', []))} players")
        print(f"   Injuries (Away): {len(match.get('away_injuries', []))} players")
        print(f"   Weather: {match.get('weather', {}).get('condition', '?')} ({match.get('weather', {}).get('temperature', '?')}°)")
        print(f"   Referee: {match.get('referee', '?')}")
        print()
    
    # Try syncing to DB
    print("💾 Attempting to sync to database...\n")
    sync_result = scraper.sync_to_db(matches)
    
    if sync_result:
        print("✅ Successfully synced all matches to database!\n")
    else:
        print("❌ Failed to sync to database\n")
    
    print("="*70 + "\n")


if __name__ == "__main__":
    asyncio.run(test_fotmob())
