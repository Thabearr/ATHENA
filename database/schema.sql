-- ==========================================
-- ATHENA Database Schema
-- Version: 0.4
-- ==========================================

-- =========================
-- Teams
-- =========================
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER UNIQUE,
    name TEXT NOT NULL,
    country TEXT,
    league TEXT,
    elo_rating INTEGER DEFAULT 1500,
    home_elo INTEGER DEFAULT 1500,
    away_elo INTEGER DEFAULT 1500,
    matches_processed INTEGER DEFAULT 0,
    last_update TEXT
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
    recommendation INTEGER,
    actual_result TEXT,  -- 'WIN', 'LOSS', 'VOID', or NULL
    edge REAL,
    is_value_bet INTEGER DEFAULT 0
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

    rank INTEGER DEFAULT 20,
    points INTEGER DEFAULT 0,

    form TEXT,

    played INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    draws INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,

    goals_for INTEGER DEFAULT 0,
    goals_against INTEGER DEFAULT 0,
    goal_difference INTEGER DEFAULT 0,

    clean_sheets INTEGER DEFAULT 0,
    failed_to_score INTEGER DEFAULT 0,

    home_played INTEGER DEFAULT 0,
    home_wins INTEGER DEFAULT 0,
    home_draws INTEGER DEFAULT 0,
    home_losses INTEGER DEFAULT 0,
    home_goals_for INTEGER DEFAULT 0,
    home_goals_against INTEGER DEFAULT 0,

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
-- Historical Matches (real finished results, used for form calculation)
-- =========================
CREATE TABLE IF NOT EXISTS historical_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER UNIQUE,
    home_id INTEGER,
    away_id INTEGER,
    home_goals INTEGER,
    away_goals INTEGER,
    match_date TEXT,
    home_pre_elo INTEGER,
    away_pre_elo INTEGER,
    home_xg REAL,
    away_xg REAL,
    home_possession INTEGER,
    away_possession INTEGER,
    league_code TEXT
);

-- =========================
-- Historical Match Conflicts
-- Additive evidence for immutable CSV rows that disagree with an existing
-- authoritative historical_matches row. Raw provider payloads are not stored.
-- =========================
CREATE TABLE IF NOT EXISTS historical_match_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    conflict_fingerprint TEXT NOT NULL,
    conflict_reason TEXT NOT NULL,
    incoming_home_id INTEGER,
    incoming_away_id INTEGER,
    incoming_home_goals INTEGER,
    incoming_away_goals INTEGER,
    incoming_match_date TEXT,
    incoming_season_label TEXT,
    resolved INTEGER NOT NULL DEFAULT 0,
    UNIQUE(fixture_id, source, conflict_fingerprint)
);

-- =========================
-- Half-Time Observations
-- Additive, source-specific evidence. Existing full-time scores remain
-- authoritative in historical_matches and are never replaced here.
-- =========================
CREATE TABLE IF NOT EXISTS half_time_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_identity TEXT NOT NULL,
    home_team TEXT,
    away_team TEXT,
    kickoff_time TEXT,
    full_time_home_goals INTEGER,
    full_time_away_goals INTEGER,
    half_time_home_goals INTEGER,
    half_time_away_goals INTEGER,
    source TEXT NOT NULL,
    observed_at TEXT,
    source_fixture_id TEXT,
    half_time_score_provenance TEXT NOT NULL DEFAULT 'MISSING',
    validation_status TEXT NOT NULL,
    rejection_reasons TEXT NOT NULL DEFAULT '[]',
    league TEXT,
    season TEXT,
    conflict_status INTEGER NOT NULL DEFAULT 0,
    conflict_fingerprint TEXT,
    conflict_reason TEXT,
    conflict_observed_at TEXT,
    UNIQUE(fixture_identity, source)
);

-- =========================
-- Managers & Derbies
-- =========================
CREATE TABLE IF NOT EXISTS derbies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_a_id INTEGER NOT NULL,
    team_b_id INTEGER NOT NULL,
    derby_name TEXT,
    intensity INTEGER DEFAULT 1, -- 1=Normal, 2=High, 3=Fierce
    UNIQUE(team_a_id, team_b_id)
);

CREATE TABLE IF NOT EXISTS manager_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL,
    manager_name TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT
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

CREATE INDEX IF NOT EXISTS idx_historical_matches_home
ON historical_matches(home_id);

CREATE INDEX IF NOT EXISTS idx_historical_matches_away
ON historical_matches(away_id);

CREATE INDEX IF NOT EXISTS idx_historical_match_conflicts_fixture
ON historical_match_conflicts(fixture_id);

CREATE INDEX IF NOT EXISTS idx_half_time_observations_fixture
ON half_time_observations(fixture_identity);

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

-- =========================
-- Backtest Runs
-- =========================
CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT,
    start_date TEXT,
    end_date TEXT,
    accas_generated INTEGER,
    accas_won INTEGER,
    accas_lost INTEGER,
    accas_void INTEGER,
    total_staked REAL,
    total_returned REAL,
    roi REAL,
    win_rate REAL,
    max_drawdown REAL
);

-- =========================
-- Acca History (for tracking backtests and live)
-- =========================
CREATE TABLE IF NOT EXISTS acca_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER, -- NULL for live, links to backtest_runs for backtests
    date_created TEXT,
    fold_size INTEGER,
    total_odds REAL,
    stake_size REAL,
    status TEXT, -- 'PENDING', 'WON', 'LOST'
    return_amount REAL
);
