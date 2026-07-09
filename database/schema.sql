-- ==========================================
-- ATHENA Database Schema
-- Version: 0.3
-- ==========================================

-- =========================
-- Teams
-- =========================
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER UNIQUE,
    name TEXT NOT NULL,
    country TEXT,
    league TEXT
);

-- =========================
-- Fixtures
-- =========================
CREATE TABLE IF NOT EXISTS fixtures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER UNIQUE,
    league TEXT,
    season INTEGER,
    home_team TEXT,
    away_team TEXT,
    match_date TEXT,
    kickoff TEXT,
    venue TEXT,
    status TEXT
);

-- =========================
-- Odds
-- =========================
CREATE TABLE IF NOT EXISTS odds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER,
    market TEXT,
    selection TEXT,
    price REAL
);

-- =========================
-- Predictions
-- =========================
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER,
    market TEXT,
    probability REAL,
    confidence REAL,
    reliability REAL,
    recommendation INTEGER
);

-- =========================
-- Results
-- =========================
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER,
    home_score INTEGER,
    away_score INTEGER,
    finished INTEGER
);

-- =========================
-- API Cache
-- =========================
CREATE TABLE IF NOT EXISTS api_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT,
    response TEXT,
    created_at TEXT
);

-- =========================
-- Team Statistics
-- =========================
CREATE TABLE IF NOT EXISTS team_statistics (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    team_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    season INTEGER NOT NULL,

    -- League Information
    rank INTEGER DEFAULT 20,
    points INTEGER DEFAULT 0,

    -- Recent Form (WWDLW)
    form TEXT,

    -- Overall Record
    played INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    draws INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,

    -- Goals
    goals_for INTEGER DEFAULT 0,
    goals_against INTEGER DEFAULT 0,
    goal_difference INTEGER DEFAULT 0,

    -- Defensive Metrics
    clean_sheets INTEGER DEFAULT 0,
    failed_to_score INTEGER DEFAULT 0,

    -- =========================
    -- Home Record
    -- =========================
    home_played INTEGER DEFAULT 0,
    home_wins INTEGER DEFAULT 0,
    home_draws INTEGER DEFAULT 0,
    home_losses INTEGER DEFAULT 0,
    home_goals_for INTEGER DEFAULT 0,
    home_goals_against INTEGER DEFAULT 0,

    -- =========================
    -- Away Record
    -- =========================
    away_played INTEGER DEFAULT 0,
    away_wins INTEGER DEFAULT 0,
    away_draws INTEGER DEFAULT 0,
    away_losses INTEGER DEFAULT 0,
    away_goals_for INTEGER DEFAULT 0,
    away_goals_against INTEGER DEFAULT 0,

    updated_at TEXT,

    UNIQUE(team_id, league_id, season)
);

-- =========================
-- Recommended Indexes
-- =========================
CREATE INDEX IF NOT EXISTS idx_fixture_fixture_id
ON fixtures(fixture_id);

CREATE INDEX IF NOT EXISTS idx_results_fixture_id
ON results(fixture_id);

CREATE INDEX IF NOT EXISTS idx_predictions_fixture_id
ON predictions(fixture_id);

CREATE INDEX IF NOT EXISTS idx_team_statistics_lookup
ON team_statistics(team_id, league_id, season);
-- ==========================================
-- League Standings
-- ==========================================

CREATE TABLE IF NOT EXISTS standings (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    team_id INTEGER,

    league_id INTEGER,

    season INTEGER,

    position INTEGER,

    points INTEGER,

    played INTEGER,

    won INTEGER,

    drawn INTEGER,

    lost INTEGER,

    goal_difference INTEGER,

    UNIQUE(team_id, league_id, season)

);
