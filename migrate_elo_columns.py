"""Add ELO columns to teams table and run ELO backfill."""
import sqlite3

DB_PATH = "database/athena.db"

conn = sqlite3.connect(DB_PATH)

# Add missing ELO columns
migrations = [
    ("teams", "elo_rating", "INTEGER DEFAULT 1500"),
    ("teams", "home_elo", "INTEGER DEFAULT 1500"),
    ("teams", "away_elo", "INTEGER DEFAULT 1500"),
    ("teams", "matches_processed", "INTEGER DEFAULT 0"),
    ("teams", "last_update", "TEXT"),
]

for table, col, col_type in migrations:
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        print(f"  Added {table}.{col}")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e):
            print(f"  {table}.{col} already exists")
        else:
            raise

conn.commit()
print("\nSchema migration complete.")

# Verify
for r in conn.execute("PRAGMA table_info(teams)").fetchall():
    print(f"  {r}")

conn.close()
