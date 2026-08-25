#!/usr/bin/env python3
"""Build the offline historical richness and canonical market-label corpus."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.historical_asof_features import ReadOnlyHistoricalWarehouse
from domain.historical_training_coverage import (
    AUTHORITY_FLAGS,
    DATASET,
    LABEL_GENERATION_CONTRACT_VERSION,
    MARKET_LABEL_REGISTRY,
    MARKET_LABEL_REGISTRY_VERSION,
    SCHEMA_VERSION,
    HistoricalTrainingCoverageError,
    ReadOnlyOptionalJoinCorpus,
    build_coverage_row_from_bound_source,
    validate_contracts,
)

BATCH_SIZE = 500


def _protected_sqlite_paths(path: Path) -> frozenset[Path]:
    main = path.resolve()
    return frozenset({main} | {Path(str(main) + suffix) for suffix in ("-wal", "-journal", "-shm")})


def _allocate_temporary(output: Path, protected: frozenset[Path]) -> Path:
    for _ in range(100):
        candidate = output.with_name(f".{output.name}.{secrets.token_hex(12)}.tmp").resolve()
        if candidate in protected or candidate.exists():
            continue
        descriptor = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        return candidate
    raise HistoricalTrainingCoverageError("unable to allocate safe exclusive temporary output")


def _create_output(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript("""
        PRAGMA journal_mode=DELETE;
        PRAGMA synchronous=FULL;
        CREATE TABLE corpus_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE match_evidence_coverage(
          match_key TEXT PRIMARY KEY,
          match_date TEXT NOT NULL,
          scope TEXT NOT NULL,
          competition_key TEXT,
          season TEXT,
          data_quality TEXT NOT NULL,
          canonical_sha256 TEXT NOT NULL,
          payload_json TEXT NOT NULL
        );
        CREATE TABLE market_label_resolutions(
          match_key TEXT NOT NULL,
          label_id TEXT NOT NULL,
          market_family TEXT,
          status TEXT NOT NULL,
          value_json TEXT,
          blocker TEXT,
          evidence_json TEXT NOT NULL,
          PRIMARY KEY(match_key,label_id)
        );
        CREATE TABLE evidence_capability_resolutions(
          match_key TEXT NOT NULL,
          capability_id TEXT NOT NULL,
          status TEXT NOT NULL,
          value_json TEXT,
          blocker TEXT,
          evidence_json TEXT NOT NULL,
          PRIMARY KEY(match_key,capability_id)
        );
        CREATE TABLE coverage_summary(
          group_type TEXT NOT NULL,
          group_key TEXT NOT NULL,
          item_type TEXT NOT NULL,
          item_id TEXT NOT NULL,
          status TEXT NOT NULL,
          target_count INTEGER NOT NULL,
          status_count INTEGER NOT NULL,
          coverage_rate REAL NOT NULL,
          blocked_rate REAL NOT NULL,
          PRIMARY KEY(group_type,group_key,item_type,item_id,status)
        );
        CREATE INDEX idx_training_coverage_context
          ON match_evidence_coverage(scope,competition_key,season,data_quality);
        CREATE INDEX idx_training_labels_status
          ON market_label_resolutions(label_id,status);
    """)
    return connection


def _chunks(values: Iterable[Any], size: int = BATCH_SIZE) -> Iterable[list[Any]]:
    batch: list[Any] = []
    for value in values:
        batch.append(value)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def _batch_material(source: ReadOnlyHistoricalWarehouse, rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, list[Mapping[str, Any]]], dict[str, dict[str, int]]]:
    keys = [str(row["match_key"]) for row in rows]
    placeholders = ",".join("?" for _ in keys)
    events: dict[str, list[Mapping[str, Any]]] = {key: [] for key in keys}
    for event in source.connection.execute(
        f"SELECT * FROM warehouse_events_preferred WHERE match_key IN ({placeholders}) "
        "ORDER BY match_key,event_type,source_key,minute,stoppage_minute,second", keys):
        events[event["match_key"]].append(dict(event))
    counts: dict[str, dict[str, int]] = {key: {} for key in keys}
    queries = {
        "home_lineups": "SELECT l.match_key,count(*) n FROM warehouse_lineups l JOIN warehouse_matches m ON m.match_key=l.match_key WHERE l.match_key IN ({}) AND l.team=m.home_team GROUP BY l.match_key",
        "away_lineups": "SELECT l.match_key,count(*) n FROM warehouse_lineups l JOIN warehouse_matches m ON m.match_key=l.match_key WHERE l.match_key IN ({}) AND l.team=m.away_team GROUP BY l.match_key",
        "home_coaches": "SELECT c.match_key,count(*) n FROM warehouse_coaches c JOIN warehouse_matches m ON m.match_key=c.match_key WHERE c.match_key IN ({}) AND c.team=m.home_team GROUP BY c.match_key",
        "away_coaches": "SELECT c.match_key,count(*) n FROM warehouse_coaches c JOIN warehouse_matches m ON m.match_key=c.match_key WHERE c.match_key IN ({}) AND c.team=m.away_team GROUP BY c.match_key",
        "referees": "SELECT match_key,count(*) n FROM warehouse_officials WHERE match_key IN ({}) AND role='referee' GROUP BY match_key",
        "advanced_sources": "SELECT match_key,count(*) n FROM warehouse_match_sources WHERE match_key IN ({}) AND has_advanced_stats=1 GROUP BY match_key",
        "provenance": "SELECT match_key,count(*) n FROM warehouse_field_provenance WHERE match_key IN ({}) GROUP BY match_key",
        "approved_event_sources": "SELECT match_key,count(*) n FROM warehouse_match_sources WHERE match_key IN ({}) AND has_events=1 AND source_key IN ('statsbomb_open','fjelstul_worldcup') GROUP BY match_key",
    }
    for name, template in queries.items():
        for item in source.connection.execute(template.format(placeholders), keys):
            counts[item["match_key"]][name] = int(item["n"])
    return events, counts


def _selected(row: Mapping[str, Any], competition: str | None, start_date: str | None,
              end_date: str | None) -> bool:
    return ((competition is None or row["competition_key"] == competition)
            and (start_date is None or row["match_date"] >= start_date)
            and (end_date is None or row["match_date"] <= end_date))


def _write_summary(connection: sqlite3.Connection) -> None:
    # Every target remains in every denominator.  Summaries cover the whole
    # corpus plus each scope, competition, season, and warehouse quality group.
    groups = (
        ("CORPUS", "ALL", "1=1", ()),
    )
    for group_type, group_key, predicate, parameters in groups:
        total = connection.execute(
            f"SELECT count(*) FROM match_evidence_coverage WHERE {predicate}", parameters).fetchone()[0]
        if not total:
            continue
        for item_type, rows in (
            ("LABEL", connection.execute("SELECT label_id,status,count(*) n FROM market_label_resolutions GROUP BY label_id,status")),
            ("CAPABILITY", connection.execute("SELECT capability_id,status,count(*) n FROM evidence_capability_resolutions GROUP BY capability_id,status")),
        ):
            grouped: dict[str, dict[str, int]] = {}
            for row in rows:
                grouped.setdefault(row[0], {})[row[1]] = int(row[2])
            for item_id, statuses in sorted(grouped.items()):
                blocked = statuses.get("BLOCKED", 0) / total
                for status in ("AVAILABLE", "MISSING", "BLOCKED"):
                    count = statuses.get(status, 0)
                    connection.execute("INSERT INTO coverage_summary VALUES(?,?,?,?,?,?,?,?,?)",
                        (group_type, group_key, item_type, item_id, status, total, count,
                         count / total if status == "AVAILABLE" else 0.0, blocked))
        family_rows = connection.execute("""
            WITH per_match AS (
              SELECT match_key,market_family,
                CASE WHEN sum(status='BLOCKED')>0 THEN 'BLOCKED'
                     WHEN sum(status='AVAILABLE')=count(*) THEN 'AVAILABLE'
                     ELSE 'MISSING' END status
              FROM market_label_resolutions WHERE market_family IS NOT NULL
              GROUP BY match_key,market_family
            )
            SELECT market_family,status,count(*) FROM per_match GROUP BY market_family,status
        """)
        family_counts: dict[str, dict[str, int]] = {}
        for family, status, value in family_rows:
            family_counts.setdefault(family, {})[status] = int(value)
        for family, statuses in sorted(family_counts.items()):
            blocked = statuses.get("BLOCKED", 0) / total
            for status in ("AVAILABLE", "MISSING", "BLOCKED"):
                value = statuses.get(status, 0)
                connection.execute("INSERT INTO coverage_summary VALUES(?,?,?,?,?,?,?,?,?)",
                    (group_type, group_key, "MARKET_FAMILY", family, status, total, value,
                     value / total if status == "AVAILABLE" else 0.0, blocked))
    # Deterministic SQL group coverage for all requested descriptive dimensions.
    for group_type, column in (("SCOPE", "scope"), ("COMPETITION", "competition_key"),
                               ("SEASON", "season"), ("DATA_QUALITY", "data_quality")):
        for group_key, total in connection.execute(
            f"SELECT coalesce({column},'UNKNOWN'),count(*) FROM match_evidence_coverage GROUP BY {column}"):
            for item_type, table, id_column in (
                ("LABEL", "market_label_resolutions", "label_id"),
                ("CAPABILITY", "evidence_capability_resolutions", "capability_id"),
            ):
                for item_id, status, count in connection.execute(
                    f"SELECT r.{id_column},r.status,count(*) FROM {table} r "
                    f"JOIN match_evidence_coverage m ON m.match_key=r.match_key "
                    f"WHERE coalesce(m.{column},'UNKNOWN')=? GROUP BY r.{id_column},r.status", (group_key,)):
                    blocked_count = connection.execute(
                        f"SELECT count(*) FROM {table} r JOIN match_evidence_coverage m ON m.match_key=r.match_key "
                        f"WHERE coalesce(m.{column},'UNKNOWN')=? AND r.{id_column}=? AND r.status='BLOCKED'",
                        (group_key, item_id)).fetchone()[0]
                    connection.execute("INSERT INTO coverage_summary VALUES(?,?,?,?,?,?,?,?,?)",
                        (group_type, group_key, item_type, item_id, status, total, count,
                         count / total if status == "AVAILABLE" else 0.0, blocked_count / total))


def build_corpus(warehouse_path: Path, output_path: Path, *, asof_corpus: Path | None = None,
                 tactical_corpus: Path | None = None, competition: str | None = None,
                 start_date: str | None = None, end_date: str | None = None,
                 limit: int | None = None, replace: bool = False) -> int:
    warehouse = Path(warehouse_path).resolve()
    output = Path(output_path).resolve()
    operational = (ROOT / "database" / "athena.db").resolve()
    protected = _protected_sqlite_paths(warehouse) | _protected_sqlite_paths(operational)
    optional_paths = [Path(value).resolve() for value in (asof_corpus, tactical_corpus) if value]
    for path in optional_paths:
        protected |= _protected_sqlite_paths(path)
    if output in protected:
        raise HistoricalTrainingCoverageError("output collides with a protected SQLite path")
    if output.exists() and not replace:
        raise HistoricalTrainingCoverageError("output exists; pass --replace explicitly")
    if limit is not None and limit < 1:
        raise HistoricalTrainingCoverageError("limit must be positive")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = _allocate_temporary(output, protected)
    registry_sha, market_sha, generation_sha = validate_contracts()
    count = 0
    try:
        with ExitStack() as stack:
            source = stack.enter_context(ReadOnlyHistoricalWarehouse(warehouse))
            asof = stack.enter_context(ReadOnlyOptionalJoinCorpus(asof_corpus, "ASOF", source.sha256)) if asof_corpus else None
            tactical = stack.enter_context(ReadOnlyOptionalJoinCorpus(tactical_corpus, "TACTICAL", source.sha256)) if tactical_corpus else None
            destination = _create_output(temporary)
            try:
                meta = {
                    "dataset": DATASET, "schema_version": SCHEMA_VERSION,
                    "source_warehouse_sha256": source.sha256,
                    "source_warehouse_schema_version": source.schema_version,
                    "source_schema_sql_sha256": source.schema_sql_sha256,
                    "market_label_registry_version": MARKET_LABEL_REGISTRY_VERSION,
                    "market_label_registry_sha256": registry_sha,
                    "canonical_market_semantics_sha256": market_sha,
                    "generation_contract_version": LABEL_GENERATION_CONTRACT_VERSION,
                    "generation_contract_sha256": generation_sha,
                    "source_asof_corpus_sha256": None if asof is None else asof.sha256,
                    "source_tactical_corpus_sha256": None if tactical is None else tactical.sha256,
                    "authority_flags": dict(AUTHORITY_FLAGS),
                }
                destination.executemany("INSERT INTO corpus_meta VALUES(?,?)", sorted(
                    (key, json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))
                    for key, value in meta.items()))
                selected = (row for row in source.stream_matches()
                            if _selected(row, competition, start_date, end_date))
                if limit is not None:
                    import itertools
                    selected = itertools.islice(selected, limit)
                for batch in _chunks(selected):
                    for row in batch:
                        key = row["match_key"]
                        result = build_coverage_row_from_bound_source(
                            source, row, asof_corpus=asof, tactical_corpus=tactical)
                        payload = result.canonical_bytes.decode("utf-8")
                        destination.execute("INSERT INTO match_evidence_coverage VALUES(?,?,?,?,?,?,?,?)",
                            (result.match_key, result.match_date, result.scope, result.competition_key,
                             result.season, result.data_quality, result.canonical_sha256, payload))
                        label_families = {item.label_id: None if item.family is None else item.family.value
                                          for item in MARKET_LABEL_REGISTRY}
                        for label_id, resolution in result.labels:
                            destination.execute("INSERT INTO market_label_resolutions VALUES(?,?,?,?,?,?,?)",
                                (result.match_key, label_id, label_families[label_id], resolution.status.value,
                                 None if resolution.value is None else json.dumps(
                                     resolution.value.value if hasattr(resolution.value, "value") else resolution.value,
                                     sort_keys=True, separators=(",", ":"), allow_nan=False),
                                 resolution.blocker, json.dumps(list(resolution.evidence_identities), separators=(",", ":"))))
                        for capability_id, resolution in result.capabilities:
                            destination.execute("INSERT INTO evidence_capability_resolutions VALUES(?,?,?,?,?,?)",
                                (result.match_key, capability_id, resolution.status.value,
                                 None if resolution.value is None else json.dumps(resolution.value,
                                     sort_keys=True, separators=(",", ":"), allow_nan=False),
                                 resolution.blocker, json.dumps(list(resolution.evidence_identities), separators=(",", ":"))))
                        count += 1
                    destination.commit()
                _write_summary(destination)
                destination.commit()
                destination.execute("PRAGMA wal_checkpoint(FULL)")
                destination.close()
                source.assert_unchanged()
                if asof: asof.assert_unchanged()
                if tactical: tactical.assert_unchanged()
            except Exception:
                destination.close()
                raise
        os.replace(temporary, output)
        return count
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--asof-corpus", type=Path)
    parser.add_argument("--tactical-corpus", type=Path)
    parser.add_argument("--competition")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    print(build_corpus(args.db, args.output, asof_corpus=args.asof_corpus,
                       tactical_corpus=args.tactical_corpus, competition=args.competition,
                       start_date=args.start_date, end_date=args.end_date,
                       limit=args.limit, replace=args.replace))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
