#!/usr/bin/env python3
"""
Seed the derbies table with known major European derbies.
These are used by CorrelationAnalyzer to detect high-volatility matchups.
"""
import sqlite3

DB_PATH = "database/athena.db"

# (team_a_name, team_b_name, derby_name, intensity)
# intensity: 1=Normal, 2=High, 3=Fierce
DERBIES = [
    # England
    ("Liverpool FC", "Manchester United FC", "North-West Derby", 3),
    ("Arsenal FC", "Tottenham Hotspur FC", "North London Derby", 3),
    ("Manchester United FC", "Manchester City FC", "Manchester Derby", 3),
    ("Liverpool FC", "Everton FC", "Merseyside Derby", 3),
    ("Chelsea FC", "Arsenal FC", "London Derby", 2),
    ("Chelsea FC", "Tottenham Hotspur FC", "London Derby", 2),
    ("West Ham United FC", "Tottenham Hotspur FC", "London Derby", 2),
    ("Crystal Palace FC", "Brighton & Hove Albion FC", "M23 Derby", 2),
    ("Newcastle United FC", "Sunderland AFC", "Tyne-Wear Derby", 3),
    ("Aston Villa FC", "Birmingham City FC", "Second City Derby", 3),
    ("Wolverhampton Wanderers FC", "West Bromwich Albion FC", "Black Country Derby", 2),
    ("Leeds United FC", "Manchester United FC", "Roses Derby", 2),
    # Spain
    ("Real Madrid CF", "FC Barcelona", "El Clasico", 3),
    ("Real Madrid CF", "Atletico Madrid", "Derbi Madrileno", 3),
    ("FC Barcelona", "RCD Espanyol", "Derbi Barceloni", 2),
    ("Sevilla FC", "Real Betis", "Seville Derby", 3),
    ("Athletic Club", "Real Sociedad", "Basque Derby", 3),
    # Italy
    ("AC Milan", "Inter Milan", "Derby della Madonnina", 3),
    ("AS Roma", "SS Lazio", "Derby della Capitale", 3),
    ("Juventus FC", "Torino FC", "Derby della Mole", 3),
    ("Napoli", "AS Roma", "Derby del Sole", 2),
    ("Genoa CFC", "UC Sampdoria", "Derby della Lanterna", 3),
    # Germany
    ("Borussia Dortmund", "FC Schalke 04", "Revierderby", 3),
    ("Bayern Munich", "Borussia Dortmund", "Der Klassiker", 2),
    ("FC Bayern München", "Borussia Dortmund", "Der Klassiker", 2),
    ("Hamburger SV", "SV Werder Bremen", "Nordderby", 2),
    ("1. FC Köln", "Borussia Mönchengladbach", "Rhine Derby", 2),
    # France
    ("Olympique de Marseille", "Paris Saint-Germain FC", "Le Classique", 3),
    ("Olympique Lyonnais", "AS Saint-Étienne", "Derby Rhone-Alpes", 3),
    # Netherlands
    ("AFC Ajax", "Feyenoord Rotterdam", "De Klassieker", 3),
    ("AFC Ajax", "PSV Eindhoven", "De Topper", 2),
    ("Feyenoord Rotterdam", "Sparta Rotterdam", "Stadsderby", 2),
    # Portugal
    ("SL Benfica", "Sporting CP", "Derby de Lisboa", 3),
    ("SL Benfica", "FC Porto", "O Classico", 3),
    ("FC Porto", "Sporting CP", "Derby Invicto", 2),
    # Scotland
    ("Celtic FC", "Rangers FC", "Old Firm", 3),
    # Turkey
    ("Galatasaray SK", "Fenerbahce SK", "Intercontinental Derby", 3),
    ("Galatasaray SK", "Besiktas JK", "Istanbul Derby", 3),
    ("Fenerbahce SK", "Besiktas JK", "Istanbul Derby", 3),
    # Belgium
    ("RSC Anderlecht", "Standard Liege", "Classic Derby", 2),
    ("Club Brugge KV", "RSC Anderlecht", "Topper", 2),
    # Greece
    ("Olympiacos FC", "Panathinaikos FC", "Derby of the eternal enemies", 3),
    # Austria
    ("SK Rapid Wien", "FK Austria Wien", "Wiener Derby", 3),
]


def seed_derbies():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    inserted = 0
    skipped = 0

    for team_a_name, team_b_name, derby_name, intensity in DERBIES:
        # Look up team_ids by name (fuzzy - we check both exact and partial)
        cursor.execute("SELECT team_id FROM teams WHERE name = ?", (team_a_name,))
        row_a = cursor.fetchone()
        cursor.execute("SELECT team_id FROM teams WHERE name = ?", (team_b_name,))
        row_b = cursor.fetchone()

        if not row_a or not row_b:
            skipped += 1
            continue

        team_a_id = row_a[0]
        team_b_id = row_b[0]

        # Ensure consistent ordering (smaller id first)
        if team_a_id > team_b_id:
            team_a_id, team_b_id = team_b_id, team_a_id

        try:
            cursor.execute(
                "INSERT OR IGNORE INTO derbies (team_a_id, team_b_id, derby_name, intensity) VALUES (?, ?, ?, ?)",
                (team_a_id, team_b_id, derby_name, intensity),
            )
            if cursor.rowcount > 0:
                inserted += 1
                print(f"  + {derby_name}: {team_a_name} vs {team_b_name}")
        except Exception as e:
            print(f"  ! Error inserting {derby_name}: {e}")

    conn.commit()
    conn.close()
    print(f"\nDerbies seeded: {inserted} inserted, {skipped} skipped (teams not in DB)")


if __name__ == "__main__":
    seed_derbies()
