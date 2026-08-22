PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS warehouse_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS warehouse_sources (
    source_key TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    homepage TEXT,
    license_name TEXT,
    attribution TEXT,
    redistributable INTEGER NOT NULL DEFAULT 0,
    source_priority INTEGER NOT NULL DEFAULT 100,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS warehouse_competitions (
    competition_key TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    scope TEXT NOT NULL CHECK(scope IN ('club','international')),
    country TEXT,
    confederation TEXT,
    competition_type TEXT NOT NULL,
    hierarchy_rank INTEGER NOT NULL,
    hierarchy_tier TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    aliases_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS warehouse_team_aliases (
    competition_key TEXT NOT NULL,
    source_key TEXT NOT NULL,
    alias TEXT NOT NULL,
    alias_norm TEXT NOT NULL,
    canonical_team TEXT NOT NULL,
    source_team_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (competition_key, source_key, alias_norm),
    FOREIGN KEY (competition_key) REFERENCES warehouse_competitions(competition_key),
    FOREIGN KEY (source_key) REFERENCES warehouse_sources(source_key)
);

CREATE TABLE IF NOT EXISTS warehouse_matches (
    match_key TEXT PRIMARY KEY,
    competition_key TEXT,
    competition_name TEXT NOT NULL,
    scope TEXT NOT NULL CHECK(scope IN ('club','international')),
    season TEXT,
    stage TEXT,
    round_name TEXT,
    match_date TEXT NOT NULL,
    kickoff_time TEXT,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    home_score_ft INTEGER,
    away_score_ft INTEGER,
    home_score_ht INTEGER,
    away_score_ht INTEGER,
    home_score_et INTEGER,
    away_score_et INTEGER,
    home_score_pen INTEGER,
    away_score_pen INTEGER,
    result TEXT,
    venue TEXT,
    city TEXT,
    country TEXT,
    neutral INTEGER,
    attendance INTEGER,
    referee TEXT,
    home_coach TEXT,
    away_coach TEXT,
    home_xg REAL,
    away_xg REAL,
    home_possession REAL,
    away_possession REAL,
    home_shots INTEGER,
    away_shots INTEGER,
    home_shots_on_target INTEGER,
    away_shots_on_target INTEGER,
    home_corners INTEGER,
    away_corners INTEGER,
    home_fouls INTEGER,
    away_fouls INTEGER,
    home_yellows INTEGER,
    away_yellows INTEGER,
    home_reds INTEGER,
    away_reds INTEGER,
    extra_json TEXT NOT NULL DEFAULT '{}',
    data_quality TEXT NOT NULL DEFAULT 'PARTIAL',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (competition_key) REFERENCES warehouse_competitions(competition_key)
);

CREATE TABLE IF NOT EXISTS warehouse_field_provenance (
    match_key TEXT NOT NULL,
    field_name TEXT NOT NULL,
    source_key TEXT NOT NULL,
    source_priority INTEGER NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (match_key, field_name),
    FOREIGN KEY (match_key) REFERENCES warehouse_matches(match_key) ON DELETE CASCADE,
    FOREIGN KEY (source_key) REFERENCES warehouse_sources(source_key)
);

CREATE TABLE IF NOT EXISTS warehouse_match_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_key TEXT NOT NULL,
    source_key TEXT NOT NULL,
    source_match_id TEXT,
    source_url TEXT,
    retrieved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    payload_sha256 TEXT,
    has_ft INTEGER NOT NULL DEFAULT 0,
    has_ht INTEGER NOT NULL DEFAULT 0,
    has_events INTEGER NOT NULL DEFAULT 0,
    has_cards INTEGER NOT NULL DEFAULT 0,
    has_lineups INTEGER NOT NULL DEFAULT 0,
    has_coaches INTEGER NOT NULL DEFAULT 0,
    has_officials INTEGER NOT NULL DEFAULT 0,
    has_advanced_stats INTEGER NOT NULL DEFAULT 0,
    UNIQUE(match_key, source_key, source_match_id),
    FOREIGN KEY (match_key) REFERENCES warehouse_matches(match_key) ON DELETE CASCADE,
    FOREIGN KEY (source_key) REFERENCES warehouse_sources(source_key)
);

CREATE TABLE IF NOT EXISTS warehouse_events (
    event_key TEXT PRIMARY KEY,
    match_key TEXT NOT NULL,
    source_key TEXT NOT NULL,
    source_event_id TEXT,
    event_type TEXT NOT NULL,
    event_subtype TEXT,
    team TEXT,
    player TEXT,
    assist TEXT,
    minute INTEGER,
    stoppage_minute INTEGER,
    second INTEGER,
    period TEXT,
    outcome TEXT,
    card_type TEXT,
    is_penalty INTEGER NOT NULL DEFAULT 0,
    is_own_goal INTEGER NOT NULL DEFAULT 0,
    xg REAL,
    details_json TEXT NOT NULL DEFAULT '{}',
    source_url TEXT,
    FOREIGN KEY (match_key) REFERENCES warehouse_matches(match_key) ON DELETE CASCADE,
    FOREIGN KEY (source_key) REFERENCES warehouse_sources(source_key)
);

CREATE TABLE IF NOT EXISTS warehouse_lineups (
    lineup_key TEXT PRIMARY KEY,
    match_key TEXT NOT NULL,
    source_key TEXT NOT NULL,
    team TEXT NOT NULL,
    player TEXT NOT NULL,
    player_id TEXT,
    shirt_number INTEGER,
    position TEXT,
    starter INTEGER,
    captain INTEGER,
    minutes_played INTEGER,
    details_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (match_key) REFERENCES warehouse_matches(match_key) ON DELETE CASCADE,
    FOREIGN KEY (source_key) REFERENCES warehouse_sources(source_key)
);

CREATE TABLE IF NOT EXISTS warehouse_coaches (
    coach_key TEXT PRIMARY KEY,
    match_key TEXT NOT NULL,
    source_key TEXT NOT NULL,
    team TEXT NOT NULL,
    coach_name TEXT NOT NULL,
    coach_id TEXT,
    role TEXT NOT NULL DEFAULT 'head_coach',
    nationality TEXT,
    FOREIGN KEY (match_key) REFERENCES warehouse_matches(match_key) ON DELETE CASCADE,
    FOREIGN KEY (source_key) REFERENCES warehouse_sources(source_key)
);

CREATE TABLE IF NOT EXISTS warehouse_officials (
    official_key TEXT PRIMARY KEY,
    match_key TEXT NOT NULL,
    source_key TEXT NOT NULL,
    official_name TEXT NOT NULL,
    official_id TEXT,
    role TEXT NOT NULL DEFAULT 'referee',
    nationality TEXT,
    FOREIGN KEY (match_key) REFERENCES warehouse_matches(match_key) ON DELETE CASCADE,
    FOREIGN KEY (source_key) REFERENCES warehouse_sources(source_key)
);

CREATE TABLE IF NOT EXISTS warehouse_penalty_shootouts (
    shootout_key TEXT PRIMARY KEY,
    match_key TEXT NOT NULL,
    source_key TEXT NOT NULL,
    sequence_number INTEGER,
    team TEXT,
    player TEXT,
    outcome TEXT,
    first_shooter TEXT,
    winner TEXT,
    details_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (match_key) REFERENCES warehouse_matches(match_key) ON DELETE CASCADE,
    FOREIGN KEY (source_key) REFERENCES warehouse_sources(source_key)
);

CREATE TABLE IF NOT EXISTS warehouse_import_runs (
    run_id TEXT PRIMARY KEY,
    source_key TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    files_seen INTEGER NOT NULL DEFAULT 0,
    rows_seen INTEGER NOT NULL DEFAULT 0,
    matches_inserted INTEGER NOT NULL DEFAULT 0,
    matches_updated INTEGER NOT NULL DEFAULT 0,
    events_inserted INTEGER NOT NULL DEFAULT 0,
    lineups_inserted INTEGER NOT NULL DEFAULT 0,
    warnings INTEGER NOT NULL DEFAULT 0,
    details_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (source_key) REFERENCES warehouse_sources(source_key)
);

CREATE TABLE IF NOT EXISTS warehouse_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_key TEXT NOT NULL,
    field_name TEXT NOT NULL,
    existing_value TEXT,
    incoming_value TEXT,
    existing_source TEXT,
    incoming_source TEXT NOT NULL,
    observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved INTEGER NOT NULL DEFAULT 0,
    UNIQUE(match_key, field_name, incoming_source, incoming_value)
);

CREATE INDEX IF NOT EXISTS idx_wh_matches_date ON warehouse_matches(match_date);
CREATE INDEX IF NOT EXISTS idx_wh_matches_competition ON warehouse_matches(competition_key, season, match_date);
CREATE INDEX IF NOT EXISTS idx_wh_matches_teams ON warehouse_matches(home_team, away_team, match_date);
CREATE INDEX IF NOT EXISTS idx_wh_team_aliases_lookup ON warehouse_team_aliases(competition_key, source_key, alias_norm);
CREATE INDEX IF NOT EXISTS idx_wh_events_match ON warehouse_events(match_key, minute);
CREATE INDEX IF NOT EXISTS idx_wh_events_player ON warehouse_events(player, event_type);
CREATE INDEX IF NOT EXISTS idx_wh_sources_match ON warehouse_match_sources(match_key);
CREATE INDEX IF NOT EXISTS idx_wh_lineups_match ON warehouse_lineups(match_key, team);
CREATE INDEX IF NOT EXISTS idx_wh_coaches_match ON warehouse_coaches(match_key, team);
CREATE INDEX IF NOT EXISTS idx_wh_officials_match ON warehouse_officials(match_key);

CREATE VIEW IF NOT EXISTS warehouse_match_flat AS
SELECT
    m.match_key,
    c.hierarchy_rank,
    c.hierarchy_tier,
    m.scope,
    m.competition_key,
    m.competition_name,
    m.season,
    m.stage,
    m.round_name,
    m.match_date,
    m.kickoff_time,
    m.home_team,
    m.away_team,
    m.home_score_ht,
    m.away_score_ht,
    m.home_score_ft,
    m.away_score_ft,
    m.home_score_et,
    m.away_score_et,
    m.home_score_pen,
    m.away_score_pen,
    m.result,
    m.venue,
    m.city,
    m.country,
    m.neutral,
    m.attendance,
    m.referee,
    m.home_coach,
    m.away_coach,
    m.home_xg,
    m.away_xg,
    m.home_possession,
    m.away_possession,
    m.home_shots,
    m.away_shots,
    m.home_shots_on_target,
    m.away_shots_on_target,
    m.home_corners,
    m.away_corners,
    m.home_fouls,
    m.away_fouls,
    m.home_yellows,
    m.away_yellows,
    m.home_reds,
    m.away_reds,
    m.data_quality
FROM warehouse_matches m
LEFT JOIN warehouse_competitions c ON c.competition_key = m.competition_key;

-- Raw warehouse_events deliberately keeps every source's evidence. This view is
-- the safe aggregation/model-facing surface: for each match + event type, only
-- the strongest available source contributes incidents. Complementary event
-- types from weaker sources are still retained when no stronger source provides
-- that same event type.
CREATE VIEW IF NOT EXISTS warehouse_events_preferred AS
SELECT e.*
FROM warehouse_events e
JOIN warehouse_sources s ON s.source_key = e.source_key
WHERE NOT EXISTS (
    SELECT 1
    FROM warehouse_events e2
    JOIN warehouse_sources s2 ON s2.source_key = e2.source_key
    WHERE e2.match_key = e.match_key
      AND e2.event_type = e.event_type
      AND (
          s2.source_priority < s.source_priority
          OR (s2.source_priority = s.source_priority AND e2.source_key < e.source_key)
      )
);