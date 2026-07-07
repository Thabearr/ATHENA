-- ==========================================
-- ATHENA Database Schema
-- Version: 0.2 (Production / Safe Migration)
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
-- Team Statistics (Sprint 2)
-- =========================
CREATE TABLE IF NOT EXISTS team_statistics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER,
    league_id INTEGER,
    season INTEGER,
    form TEXT,
    played INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    draws INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    goals_for INTEGER DEFAULT 0,
    goals_against INTEGER DEFAULT 0,
    -- Home Records (Crucial for Form Engine Advantage Metrics)
    home_played INTEGER DEFAULT 0,
    home_wins INTEGER DEFAULT 0,
    home_draws INTEGER DEFAULT 0,
    home_losses INTEGER DEFAULT 0,
    home_goals_for INTEGER DEFAULT 0,
    home_goals_against INTEGER DEFAULT 0,
    -- Away Records (Crucial for Form Engine Clash Metrics)
    away_played INTEGER DEFAULT 0,
    away_wins INTEGER DEFAULT 0,
    away_draws INTEGER DEFAULT 0,
    away_losses INTEGER DEFAULT 0,
    away_goals_for INTEGER DEFAULT 0,
    away_goals_against INTEGER DEFAULT 0,
    updated_at TEXT,
    UNIQUE(team_id, league_id, season)
);
