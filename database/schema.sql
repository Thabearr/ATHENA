-- ==========================================
-- ATHENA Database Schema
-- Version: 0.2
-- ==========================================

DROP TABLE IF EXISTS teams;
DROP TABLE IF EXISTS fixtures;
DROP TABLE IF EXISTS odds;
DROP TABLE IF EXISTS predictions;
DROP TABLE IF EXISTS results;
DROP TABLE IF EXISTS api_cache;

-- =========================
-- Teams
-- =========================

CREATE TABLE teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER UNIQUE,
    name TEXT NOT NULL,
    country TEXT,
    league TEXT
);

-- =========================
-- Fixtures
-- =========================

CREATE TABLE fixtures (
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

CREATE TABLE odds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    fixture_id INTEGER,

    market TEXT,
    selection TEXT,
    price REAL
);

-- =========================
-- Predictions
-- =========================

CREATE TABLE predictions (
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

CREATE TABLE results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    fixture_id INTEGER,

    home_score INTEGER,
    away_score INTEGER,

    finished INTEGER
);

-- =========================
-- API Cache
-- =========================

CREATE TABLE api_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    endpoint TEXT,
    response TEXT,

    created_at TEXT
);

CREATE TABLE IF NOT EXISTS team_statistics (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    team_id INTEGER,

    league_id INTEGER,

    season INTEGER,

    form TEXT,

    played INTEGER,

    wins INTEGER,

    draws INTEGER,

    losses INTEGER,

    goals_for INTEGER,

    goals_against INTEGER,

    updated_at TEXT
);
