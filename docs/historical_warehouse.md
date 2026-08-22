# Athena Historical Football Warehouse

## Purpose

Athena's historical warehouse is the durable evidence layer for past football matches. It is designed for model training, form calculations, market research, backtesting, competition-strength weighting, scorer/card analysis, manager effects and future feature engineering.

The warehouse is **not** one giant hand-maintained CSV. It is a normalized SQLite database with reproducible importers and CSV exports.

Generated data is local and git-ignored. The repository stores the schema, source registry and build code, not multi-gigabyte raw provider dumps.

## Competition hierarchy

The hierarchy is encoded in `domain/historical_competitions.py`.

Club priority begins with:

1. UEFA Champions League
2. UEFA Europa League
3. UEFA Conference League
4. Premier League
5. La Liga
6. Serie A
7. Bundesliga
8. Ligue 1
9. Big-five domestic cups
10. Eredivisie
11. Primeira Liga
12. Süper Lig
13. Belgian Pro League
14. Eliteserien
15. Danish Superliga
16. Allsvenskan
17. Swiss Super League
18. Super League Greece
19. EFL Championship
20. Saudi Pro League
21. MLS
22. Other approved European top flights

International competitions use a separate ranking, led by the FIFA World Cup, UEFA European Championship, Copa América and AFCON.

## Data model

### `warehouse_matches`

One canonical row per match. Important columns include:

- competition, season, stage and round
- date and kickoff
- home/away teams
- half-time score
- 90-minute full-time score
- extra-time score
- penalty shootout score
- venue, city, country and neutral-site flag
- referee
- home and away coach
- xG and possession when available
- shots, shots on target, corners and fouls
- yellow/red card totals
- `data_quality`

### `warehouse_events`

One row per known match event. Supports goals, cards, substitutions and StatsBomb event types. Event records can include player, assist, team, minute, stoppage time, period, card type, penalty/own-goal flags and xG.

### `warehouse_lineups`

Player appearance/lineup records with team, player, shirt number, position, starter flag and source-specific details.

### `warehouse_coaches`

Match-specific coaching records.

### `warehouse_officials`

Referees and other officials where sources provide them.

### `warehouse_match_sources`

Per-match provenance. This records which source supplied the match and whether that source has FT, HT, events, cards, lineups, coaches, officials and advanced statistics.

### `warehouse_field_provenance`

Per-field source ownership. A stronger source can enrich or correct a weaker source; a weaker source cannot silently overwrite stronger evidence.

### `warehouse_conflicts`

Disagreements are retained for audit instead of being discarded.

### `warehouse_match_flat`

A flat SQL view intended for model features and CSV export.

## Current source stack

| Source | Best use | Historical depth | Detail | Redistribution handling |
|---|---|---:|---|---|
| martj42 `international_results` | Senior international match backbone | 1872 onward | Results, scorers, shootouts | CC0 |
| Fjelstul World Cup Database | World Cup enrichment | 1930 onward | Goals, bookings, managers, players, substitutions, referees, venues | CC BY-SA 4.0 |
| Football-Data.co.uk | European league modelling/backtests | Primarily 1993/94 onward | HT/FT, cards, shots, corners, fouls, referees, odds columns | Keep raw cache local; follow source terms |
| OpenFootball | Public-domain league/cup/UEFA backfill | Varies by competition | Results, often HT; some seasons include scorers/venues | CC0 |
| StatsBomb Open Data | Deep event enrichment | Selected competitions/seasons | Event stream, lineups, xG, tactics and rich metadata | Attribution/source terms apply |

No honest public source contains every historical match in every requested competition with every scorer, card, coach, lineup and advanced statistic. Athena therefore treats missing values as missing rather than inventing them. Coverage improves source-by-source while the canonical match remains stable.

## Build commands

Initialize or inspect an empty warehouse:

```bash
python scripts/build_historical_warehouse.py --audit
```

Build all supported historical sources, including deep StatsBomb event and lineup data, then export CSVs:

```bash
python scripts/build_historical_warehouse.py --all --deep --export-csv data/history_exports
```

Build only the international backbone and rich World Cup layer:

```bash
python scripts/build_historical_warehouse.py --martj42 --worldcup --audit
```

Build the league backbone from Football-Data.co.uk:

```bash
python scripts/build_historical_warehouse.py --football-data --start-year 1993 --end-year 2026 --audit
```

Build public-domain European league/cup/UEFA backfill:

```bash
python scripts/build_historical_warehouse.py --openfootball --audit
```

Refresh downloaded files instead of using the local cache:

```bash
python scripts/build_historical_warehouse.py --all --deep --refresh --audit
```

## CSV exports

`--export-csv data/history_exports` writes:

- `matches.csv`
- `events.csv`
- `lineups.csv`
- `coaches.csv`
- `officials.csv`
- `sources.csv`
- `conflicts.csv`

CSV is an interchange/training format. SQLite remains the canonical warehouse because a single match can have many goals, bookings, substitutions, players and source records.

## Data quality policy

`data_quality` is recalculated after imports:

- `BASIC`: known FT result
- `STANDARD`: FT plus HT or event evidence
- `RICH`: FT + HT + events + both coaches + referee
- `PARTIAL`: less than a complete final score

Important rules:

1. Never fill unknown historical facts with guesses.
2. Preserve source URL/ID and retrieval time.
3. Prefer stronger event-specific sources over broad result-only sources.
4. Record contradictory values in `warehouse_conflicts`.
5. Keep 90-minute FT, extra-time and penalty scores separate.
6. Only derive HT from goalscorers when scorer coverage reconciles to the known total score.
7. Keep provider-specific columns in `extra_json` when they do not yet have a first-class schema field.

## Integration with existing Athena data

Athena already has `database/athena.db`, `historical_matches`, `half_time_observations` and a Football-Data importer. This warehouse is intentionally stored separately as `database/athena_history.db` so the high-volume evidence store does not destabilize the operational database.

Model/research services should read `warehouse_match_flat` or purpose-built feature queries from `athena_history.db`. A later integration can attach the database with SQLite `ATTACH DATABASE` or build a read-only repository/service over it.
