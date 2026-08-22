# Athena Historical Football Warehouse

## Purpose

Athena's historical warehouse is the durable evidence layer for past football matches. It is designed for model training, form calculations, market research, backtesting, competition-strength weighting, scorer/card analysis, manager effects and future feature engineering.

The canonical store is a normalized SQLite database at `database/athena_history.db`. CSV files are exports for analysis/training, not the source of truth. Generated databases, source caches and CSV exports are git-ignored; Git stores only the reproducible schema/import/build code.

## Competition hierarchy

The hierarchy is encoded in `domain/historical_competitions.py` and is independent for club and international football.

Club priority starts with UEFA Champions League, Europa League and Conference League, then the Premier League, La Liga, Serie A, Bundesliga and Ligue 1, followed by the Big Five domestic cups, Eredivisie, Primeira Liga, Süper Lig, Belgian Pro League, Eliteserien, Danish Superliga, Allsvenskan, Swiss Super League, Super League Greece, EFL Championship, Saudi Pro League, MLS and other approved European top flights.

International priority starts with the FIFA World Cup, UEFA European Championship, Copa América and AFCON, then Asian Cup, Gold Cup, qualifiers, Nations League, friendlies and other senior internationals.

## Data model

### `warehouse_matches`

One canonical row per match, including competition/season/stage, date/kickoff, teams, HT/90-minute FT/ET/penalty scores, venue/location, referee, coaches, xG, possession, shots, shots on target, corners, fouls and card totals when available.

### `warehouse_events`

One row per known event. Supports goals, cards, substitutions and richer StatsBomb event types with player, assist, team, minute, stoppage time, period, card type, penalty/own-goal flags and xG.

### Other linked tables

- `warehouse_lineups`: player appearances/lineups.
- `warehouse_coaches`: match-specific coaching records.
- `warehouse_officials`: referees and other officials.
- `warehouse_penalty_shootouts`: shootout evidence.
- `warehouse_match_sources`: source-level coverage flags and source IDs/URLs.
- `warehouse_field_provenance`: source ownership for individual canonical fields.
- `warehouse_conflicts`: contradictory source values retained for audit.
- `warehouse_match_flat`: flat view for model features and CSV export.

## Source stack

| Source | Best use | Historical depth | Detail | Handling |
|---|---|---:|---|---|
| schochastics `football-data` | Broad result backbone | 1888-2023 | 1.2M+ top-flight/international results | ODC-By; batched local import |
| martj42 `international_results` | Senior internationals | 1872 onward | Results, scorers, shootouts | CC0 |
| Fjelstul World Cup Database | World Cup enrichment | 1930 onward | Goals, bookings, managers, players, substitutions, referees, venues | CC BY-SA 4.0 |
| Football-Data.co.uk | European league modelling/backtests | Primarily 1993/94 onward | HT/FT, cards, shots, corners, fouls, referee and odds fields where available | Keep raw cache local; follow source terms |
| OpenFootball | League/cup/UEFA backfill | Varies | Results, often HT; public-domain structured football.txt files | CC0 |
| StatsBomb Open Data | Deep event enrichment | Selected competitions/seasons | Events, lineups, xG, tactics and rich metadata | Attribution/source terms apply |

No single public source contains every historical match in every requested competition with every scorer, card, coach, lineup and advanced statistic. Athena therefore leaves unavailable historical fields as `NULL` instead of inventing them. Richer sources augment or replace weaker evidence field-by-field, and disagreements are retained in `warehouse_conflicts`.

## Recommended full build

Run the broad backbone first, then richer sources in increasing detail:

```bash
python scripts/import_global_football_backbone.py
python scripts/build_historical_warehouse.py --martj42 --worldcup --football-data --start-year 1993 --end-year 2026 --audit
python scripts/import_openfootball_history.py
python scripts/enrich_statsbomb_history.py
python scripts/build_historical_warehouse.py --export-csv data/history_exports --audit
```

The separate OpenFootball importer is the recommended path because it explicitly handles European season rollover: for a `2025-26` season, July-December dates are in 2025 and January-June dates are in 2026. MLS, Eliteserien and Allsvenskan are treated as calendar-year leagues in the global backbone.

## GitHub Actions build

The workflow `.github/workflows/build-historical-warehouse.yml` provides a manual reproducible build. It:

1. runs the historical warehouse tests;
2. imports the 1.2M-match global backbone;
3. imports internationals, World Cup enrichment and Football-Data league history;
4. imports OpenFootball league/cup/UEFA history;
5. optionally enriches supported matches with StatsBomb events/lineups;
6. exports CSV tables;
7. runs `PRAGMA integrity_check`;
8. uploads `athena-history-sqlite` and `athena-history-csv` artifacts.

## CSV exports

`--export-csv data/history_exports` creates:

- `matches.csv`
- `events.csv`
- `lineups.csv`
- `coaches.csv`
- `officials.csv`
- `sources.csv`
- `conflicts.csv`

SQLite remains canonical because one match can have many goals, bookings, substitutions, players and source records.

## Data quality policy

`data_quality` is recalculated after imports:

- `BASIC`: known 90-minute FT result.
- `STANDARD`: FT plus HT or event evidence.
- `RICH`: FT + HT + events + both coaches + referee.
- `PARTIAL`: less than a complete regulation-time result.

Rules:

1. Never fill unknown historical facts with guesses.
2. Preserve source IDs/URLs and retrieval provenance.
3. Prefer stronger event-specific sources over broad result-only sources.
4. Record contradictory values instead of silently discarding them.
5. Keep 90-minute FT, extra-time and penalty scores separate.
6. Only derive HT from goalscorers when scorer coverage reconciles to the known total score.
7. Keep provider-specific fields in `extra_json` until they deserve first-class schema columns.

## Integration with existing Athena

Athena's operational `database/athena.db` remains unchanged. The high-volume evidence warehouse is stored separately as `database/athena_history.db` so historical ingestion cannot destabilize live prediction/backtest state. Services can query `warehouse_match_flat` directly or attach the history DB to the operational SQLite connection later.
