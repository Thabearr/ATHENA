-- =========================
-- ATHENA Database Schema
-- Version: 0.1
-- =========================

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER UNIQUE,
    name TEXT NOT NULL,
    country TEXT,
    league TEXT
);

CREATE TABLE IF NOT EXISTS fixtures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER UNIQUE,
    league TEXT,
    season INTEGER,
    home_team TEXT,
    away_team TEXT,
    kickoff TEXT,
    status TEXT
);

CREATE TABLE IF NOT EXISTS odds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER,
    market TEXT,
    selection TEXT,
    price REAL
);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER,
    market TEXT,
    probability REAL,
    confidence REAL,
    reliability REAL,
    recommendation INTEGER
);

CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER,
    home_score INTEGER,
    away_score INTEGER,
    finished INTEGER
);

CREATE TABLE IF NOT EXISTS api_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT,
    response TEXT,
    created_at TEXT
); 
