-- Teams
CREATE TABLE IF NOT EXISTS teams (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    team_id INTEGER UNIQUE,

    name TEXT NOT NULL,

    country TEXT,

    league TEXT
);

-- Fixtures
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

-- Odds
CREATE TABLE IF NOT EXISTS odds (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    fixture_id INTEGER,

    market TEXT,

    selection TEXT,

    price REAL
);

-- Predictions
CREATE TABLE IF NOT EXISTS predictions (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    fixture_id INTEGER,

    market TEXT,

    probability REAL,

    confidence REAL,

    reliability REAL,

    recommendation INTEGER
);

-- Results
CREATE TABLE IF NOT EXISTS results (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    fixture_id INTEGER,

    home_score INTEGER,

    away_score INTEGER,

    finished INTEGER
);
