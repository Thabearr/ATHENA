# Athena Historical Football Warehouse

## Purpose

Athena's historical warehouse is the durable evidence layer for past football matches. It is designed for model training, form calculations, market research, backtesting, competition-strength weighting, scorer/card analysis, manager effects and future feature engineering.

The canonical store is a normalized SQLite database at `database/athena_history.db`. CSV files are exports for analysis/training, not the source of truth. Generated databases, source caches and CSV exports are git-ignored; Git stores only the reproducible schema/import/build code.

The operational `database/athena.db` remains separate. Historical ingestion must not destabilize Athena's live prediction/backtest state.

## Competition hierarchy

The historical hierarchy is encoded in `domain/historical_competitions.py`. Club and senior international football use separate rank spaces; a high hierarchy rank controls review/coverage priority, not automatic betting authority.

### Club hierarchy

The current historical order is:

1. UEFA Champions League, Europa League and Conference League.
2. Premier League, La Liga, Serie A, Bundesliga and Ligue 1.
3. Big Five domestic cups: FA Cup, EFL Cup, Copa del Rey, Coppa Italia, DFB-Pokal and Coupe de France.
4. Eredivisie, Primeira Liga, Süper Lig and Belgian Pro League.
5. Scottish Premiership, Eliteserien, Danish Superliga, Allsvenskan, Swiss Super League and Super League Greece.
6. EFL Championship.
7. Major League Soccer.
8. Saudi Pro League.
9. Other European top flights, followed by other retained global top flights as catch-all evidence buckets.

The named historical registry is also tested against Athena's live source-qualified competition-review registry so a competition already prioritized by live accumulator review cannot silently disappear from history coverage.

### International hierarchy

International priority starts with the FIFA World Cup, UEFA European Championship, Copa América and AFCON, followed by AFC Asian Cup and CONCACAF Gold Cup, World Cup qualification, continental qualification, Nations League competitions, friendlies and other senior internationals.

## Data model

### `warehouse_matches`

One canonical row per match, including competition/season/stage, date/kickoff, teams, HT/90-minute FT/ET/penalty scores, venue/location, referee, coaches, xG, possession, shots, shots on target, corners, fouls and card totals when available.

Canonical match keys use conservative cross-source team normalization. Mechanical variants such as `AFC Bournemouth` vs `Bournemouth AFC`, `FC Fulham` vs `Fulham FC`, punctuation and accent differences resolve to the same match identity without fuzzy matching.

### `warehouse_events`

One row per source event/evidence item. Goal and card incidents use canonical `event_type='goal'` and `event_type='card'` labels across providers. Provider-specific raw types remain available in event details. Player, assist, team, minute, stoppage time, period, card type, penalty/own-goal flags and xG are retained where available.

Some sources provide aggregate player match totals rather than exact incident minutes. Those rows are marked with an aggregate subtype instead of inventing a timestamp.

### Other linked tables

- `warehouse_lineups`: player appearances/lineups.
- `warehouse_coaches`: match-specific coaching records.
- `warehouse_officials`: referees and other officials.
- `warehouse_penalty_shootouts`: shootout evidence.
- `warehouse_match_sources`: source-level coverage flags and source IDs/URLs.
- `warehouse_field_provenance`: source ownership for individual canonical fields.
- `warehouse_conflicts`: contradictory source values retained for audit.
- `warehouse_match_flat`: flat view for model features and CSV export.

Coach/referee canonical fields obey the same source-priority rules as other match fields; linked source rows never get to bypass provenance precedence.

## Source stack

| Source | Best use | Historical depth | Detail | Handling |
|---|---|---:|---|---|
| StatsBomb Open Data | Deep event enrichment | Selected competitions/seasons | Events, lineups, shot xG, tactics and rich metadata | Strongest supported event source; attribution/source terms apply |
| Fjelstul World Cup Database | World Cup enrichment | 1930 onward | Goals, bookings, managers, players, substitutions, referees, venues | CC BY-SA 4.0 |
| martj42 `international_results` | Senior internationals | 1872 onward | Results, scorers, shootouts | CC0 |
| Global Football Data Lake | Current cross-league layer | Modern seasons | Fixtures, HT, stats, referees, coaches, formations, player appearances/goals/cards | CC BY 4.0; imported before lower-priority history |
| Football-Data.co.uk | European league modelling/backtests | Primarily 1993/94 onward | HT/FT, cards, shots, corners, fouls, referee and odds fields where available | Keep raw cache local; follow source terms |
| schochastics goal-time files | Scorer/minute enrichment | Varies by competition | Scorer identities and goal times | Conservative exact normalized fixture attachment |
| OpenFootball | League/cup/UEFA/international backfill | Varies | Results, often HT; structured football.txt files | CC0 |
| schochastics `football-data` | Broad result backbone | 1888-2023 | 1.2M+ top-flight/international results | ODC-By; lowest-priority result backbone |

No single public source contains every historical match in every requested competition with every scorer, card, coach, lineup and advanced statistic. Athena therefore leaves unavailable historical fields as `NULL` instead of inventing them. Richer sources augment or replace weaker evidence field-by-field, and disagreements are retained in `warehouse_conflicts`.

## Source-priority and import order

Import order matters for efficiency, but canonical field ownership is still enforced by explicit source priority.

The modern Global Football Data Lake is imported first. It establishes current fixtures and richer modern fields before the 1.2M-match schochastics backbone runs. The backbone is deliberately lower priority and fills historical gaps instead of overwriting richer modern evidence.

StatsBomb and Fjelstul sit above broad result providers for fields they actually supply. Missing evidence never receives a synthetic replacement merely because a stronger source lacks coverage.

## Score-period semantics

For Athena, `home_score_ft` / `away_score_ft` mean the **90-minute regulation score**, not the score after extra time. `home_score_et` / `away_score_et` mean the score after extra time, and `*_score_pen` stores the shootout score.

Some historical sources publish a final score that includes extra time. `scripts/normalize_historical_score_periods.py` uses complete goal-event ledgers and shootout evidence to separate regulation from extra time. If the regulation score cannot be reconstructed confidently, Athena leaves FT missing rather than training on an incorrectly labelled ET result.

## Reproducible full build

The GitHub Actions workflow is the preferred full build because it applies the exact source order, quality refresh, freshness gate and integrity checks used for release artifacts.

For a local equivalent, run the current-data layer first, then the backbone and enrichments:

```bash
python scripts/run_with_fast_history_quality.py scripts/import_current_soccer_datalake.py --deep-players
python scripts/import_global_football_backbone.py
python scripts/run_with_fast_history_quality.py scripts/build_historical_warehouse.py --martj42 --worldcup --football-data --start-year 1993 --end-year 2026 --audit
python scripts/run_with_fast_history_quality.py scripts/import_openfootball_history.py
python scripts/run_with_fast_history_quality.py scripts/enrich_schochastics_goal_events.py
python scripts/run_with_fast_history_quality.py scripts/enrich_statsbomb_history.py
python scripts/normalize_historical_score_periods.py
python scripts/run_with_fast_history_quality.py scripts/build_historical_warehouse.py --export-csv data/history_exports --audit
python scripts/audit_historical_hierarchy_coverage.py --strict --recent-since 2024-01-01 --output data/history_exports/hierarchy_coverage.json
python scripts/audit_historical_data_integrity.py --strict --output data/history_exports/data_integrity.json
```

The OpenFootball importer explicitly handles European season rollover: for a `2025-26` season, July-December dates are in 2025 and January-June dates are in 2026. MLS, Eliteserien and Allsvenskan are treated as calendar-year leagues where the source requires it.

## GitHub Actions build

`.github/workflows/build-historical-warehouse.yml` runs on relevant pull requests/pushes and can also be dispatched manually. It:

1. runs historical warehouse unit/integrity tests;
2. imports the current hierarchy fixture/stat/coach/player layer;
3. imports the 1.2M-match global historical backbone;
4. imports senior internationals, World Cup enrichment and Football-Data league history;
5. imports OpenFootball league/cup/UEFA/international history;
6. enriches scorer and goal-minute history;
7. enriches supported StatsBomb matches with canonical events/lineups/xG;
8. normalizes regulation, extra-time and shootout score semantics;
9. exports CSV tables and the final audit;
10. fails if any named hierarchy competition has no history or no match on/after `2024-01-01`;
11. fails on logical duplicate hierarchy fixtures or noncanonical goal/card incident types;
12. runs SQLite integrity checking and packages the artifacts;
13. uploads `athena-history-sqlite` and `athena-history-csv` artifacts.

The current-data and source-priority upsert paths batch SQLite commits. The broad backbone already uses batched inserts. This keeps the full reproducible build practical without weakening final integrity checks.

## CSV exports

`--export-csv data/history_exports` creates:

- `matches.csv`
- `events.csv`
- `lineups.csv`
- `coaches.csv`
- `officials.csv`
- `sources.csv`
- `conflicts.csv`
- `hierarchy_coverage.json` after the strict coverage audit
- `data_integrity.json` after the strict cross-source integrity audit

SQLite remains canonical because one match can have many goals, bookings, substitutions, players and source records.

## Data quality policy

`data_quality` is recalculated after imports with a set-based refresh for large builds:

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
7. Use conservative normalized identity matching; never use fuzzy fixture guessing in the historical truth layer.
8. Keep provider-specific fields in `extra_json`/event details until they deserve first-class schema columns.
9. Fail release builds when named hierarchy coverage is stale or logical duplicate fixtures remain.

## Integration with existing Athena

Athena's operational `database/athena.db` remains unchanged. Services can query `warehouse_match_flat` directly, attach `database/athena_history.db` to the operational SQLite connection, or consume the exported CSV tables. Historical hierarchy metadata is evidence/review context; it does not make a fixture or market betting-eligible by itself.
