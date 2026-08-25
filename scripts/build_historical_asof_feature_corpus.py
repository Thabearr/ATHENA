#!/usr/bin/env python3
"""Build the offline, leakage-safe historical as-of feature corpus."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.historical_asof_features import (  # noqa: E402
    HISTORICAL_ASOF_DATASET,
    HISTORICAL_ASOF_SCHEMA_VERSION,
    HISTORICAL_ADVANCED_PERIOD_SAFETY_POLICY_ID,
    HISTORICAL_COMPLETION_POLICY_ID,
    HISTORICAL_FEATURE_REGISTRY_VERSION,
    HISTORICAL_GENERATION_CONTRACT_VERSION,
    HISTORICAL_TEAM_IDENTITY_POLICY_ID,
    TEMPORAL_POLICY_ID,
    HistoricalAsOfError,
    ReadOnlyHistoricalWarehouse,
    TeamMatchProjection,
    _assemble_snapshot,
    _projection,
    _target,
    historical_team_identity,
    qualifies_completed_prior_fixture,
    validate_historical_feature_registry,
    validate_historical_generation_contract,
)

DEFAULT_DB = ROOT / "database" / "athena_history.db"
DEFAULT_OUTPUT = ROOT / "data" / "history_features" / "athena_history_asof_features.db"


@dataclass
class TeamRollingHistory:
    recent_date_buckets: list[tuple[str, list[TeamMatchProjection]]] = field(default_factory=list)
    schedule_date_buckets: list[tuple[str, list[TeamMatchProjection]]] = field(default_factory=list)
    current_season: str | None = None
    current_season_matches: list[TeamMatchProjection] = field(default_factory=list)
    closed_seasons: set[str] = field(default_factory=set)

    def history_for(self, season: str | None, target_date: str) -> tuple[TeamMatchProjection, ...]:
        if season is not None and season in self.closed_seasons:
            raise HistoricalAsOfError("historical target season reappeared after a later season")
        target = date.fromisoformat(target_date)
        while self.schedule_date_buckets and (
            target - date.fromisoformat(self.schedule_date_buckets[0][0])
        ).days > 28:
            self.schedule_date_buckets.pop(0)
        combined = {item.match_key: item for _, bucket in self.recent_date_buckets for item in bucket}
        combined.update({
            item.match_key: item
            for _, bucket in self.schedule_date_buckets
            for item in bucket
        })
        if season is not None and season == self.current_season:
            combined.update({item.match_key: item for item in self.current_season_matches})
        return tuple(sorted(combined.values(), key=lambda item: (item.match_date, item.match_key)))

    def add_date_bucket(self, match_date: str, items: Iterable[TeamMatchProjection]) -> None:
        bucket = sorted(items, key=lambda item: item.match_key)
        if not bucket:
            return
        self.recent_date_buckets.append((match_date, bucket))
        self.schedule_date_buckets.append((match_date, bucket))
        incoming = date.fromisoformat(match_date)
        while self.schedule_date_buckets and (
            incoming - date.fromisoformat(self.schedule_date_buckets[0][0])
        ).days > 28:
            self.schedule_date_buckets.pop(0)
        while len(self.recent_date_buckets) > 1 and sum(
            len(group) for _, group in self.recent_date_buckets[1:]
        ) >= 20:
            self.recent_date_buckets.pop(0)
        seasons = {
            item.season
            for item in bucket
            if isinstance(item.season, str) and item.season and item.season == item.season.strip()
        }
        if len(seasons) > 1:
            raise HistoricalAsOfError("ambiguous same-date season transition in rolling history")
        if seasons:
            season = next(iter(seasons))
            if season != self.current_season:
                if season in self.closed_seasons:
                    raise HistoricalAsOfError("historical season reappeared after a later season")
                if self.current_season is not None:
                    self.closed_seasons.add(self.current_season)
                self.current_season = season
                self.current_season_matches = []
            self.current_season_matches.extend(item for item in bucket if item.season == season)


def _selected(row: Any, competition: str | None, start_date: str | None, end_date: str | None) -> bool:
    return (
        (competition is None or row["competition_key"] == competition)
        and (start_date is None or row["match_date"] >= start_date)
        and (end_date is None or row["match_date"] <= end_date)
    )


def _create_output(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        PRAGMA journal_mode=DELETE;
        PRAGMA synchronous=FULL;
        CREATE TABLE corpus_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE historical_asof_snapshots(
          match_key TEXT PRIMARY KEY,
          match_date TEXT NOT NULL,
          competition_key TEXT,
          canonical_sha256 TEXT NOT NULL,
          payload_json TEXT NOT NULL
        );
        CREATE INDEX idx_history_asof_date ON historical_asof_snapshots(match_date,match_key);
        """
    )
    return connection


def _protected_sqlite_paths(main_path: Path) -> frozenset[Path]:
    return frozenset(
        {main_path.resolve()}
        | {Path(str(main_path.resolve()) + suffix) for suffix in ("-wal", "-journal", "-shm")}
    )


def _new_safe_temporary(output: Path, protected: frozenset[Path]) -> Path:
    for _ in range(100):
        candidate = output.with_name(f".{output.name}.{secrets.token_hex(12)}.tmp").resolve()
        if candidate in protected or candidate.exists():
            continue
        descriptor = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        return candidate
    raise HistoricalAsOfError("unable to allocate a collision-safe output temporary file")


def build_corpus(
    warehouse_path: Path,
    output_path: Path,
    *,
    competition: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
    replace: bool = False,
) -> int:
    source_path = Path(warehouse_path).resolve()
    output = Path(output_path).resolve()
    operational = (ROOT / "database" / "athena.db").resolve()
    protected = _protected_sqlite_paths(source_path) | _protected_sqlite_paths(operational)
    legacy_temporary = output.with_name(output.name + ".tmp").resolve()
    if output in protected or legacy_temporary == source_path:
        raise HistoricalAsOfError("output must be separate from historical and operational databases")
    if limit is not None and limit < 1:
        raise HistoricalAsOfError("limit must be positive")
    for value in (start_date, end_date):
        if value is not None:
            date.fromisoformat(value)
    if output.exists() and not replace:
        raise HistoricalAsOfError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = _new_safe_temporary(output, protected)
    registry_sha = validate_historical_feature_registry()
    generation_contract_sha = validate_historical_generation_contract()
    count = 0
    try:
        with ReadOnlyHistoricalWarehouse(source_path) as source:
            destination = _create_output(temporary)
            histories: dict[tuple[str, str, str], TeamRollingHistory] = defaultdict(TeamRollingHistory)
            try:
                meta = {
                    "dataset": HISTORICAL_ASOF_DATASET,
                    "feature_registry_sha256": registry_sha,
                    "feature_registry_version": HISTORICAL_FEATURE_REGISTRY_VERSION,
                    "generation_schema_version": HISTORICAL_ASOF_SCHEMA_VERSION,
                    "generation_contract_version": HISTORICAL_GENERATION_CONTRACT_VERSION,
                    "generation_contract_sha256": generation_contract_sha,
                    "historical_completion_policy_id": HISTORICAL_COMPLETION_POLICY_ID,
                    "historical_advanced_period_safety_policy_id": (
                        HISTORICAL_ADVANCED_PERIOD_SAFETY_POLICY_ID
                    ),
                    "historical_team_identity_policy_id": HISTORICAL_TEAM_IDENTITY_POLICY_ID,
                    "source_schema_sql_sha256": source.schema_sql_sha256,
                    "source_warehouse_schema_version": source.schema_version,
                    "source_warehouse_sha256": source.sha256,
                    "temporal_policy_id": TEMPORAL_POLICY_ID,
                }
                destination.executemany(
                    "INSERT INTO corpus_meta(key,value) VALUES(?,?)",
                    sorted((key, json.dumps(value, separators=(",", ":"))) for key, value in meta.items()),
                )
                date_batch: list[Any] = []
                current_date: str | None = None

                def process_batch(rows: list[Any]) -> None:
                    nonlocal count
                    additions: dict[tuple[str, str, str], list[TeamMatchProjection]] = defaultdict(list)
                    for row in rows:
                        home_identity = historical_team_identity(
                            row["scope"], row["competition_key"], row["home_team"]
                        )
                        away_identity = historical_team_identity(
                            row["scope"], row["competition_key"], row["away_team"]
                        )
                        if _selected(row, competition, start_date, end_date) and (limit is None or count < limit):
                            snapshot = _assemble_snapshot(
                                _target(row),
                                histories[home_identity].history_for(row["season"], row["match_date"])
                                if home_identity is not None else (),
                                histories[away_identity].history_for(row["season"], row["match_date"])
                                if away_identity is not None else (),
                                source,
                                registry_sha,
                                generation_contract_sha,
                            )
                            destination.execute(
                                "INSERT INTO historical_asof_snapshots VALUES(?,?,?,?,?)",
                                (row["match_key"], row["match_date"], row["competition_key"],
                                 snapshot.canonical_sha256, snapshot.canonical_bytes.decode("utf-8")),
                            )
                            count += 1
                            if count % 500 == 0:
                                destination.commit()
                        if qualifies_completed_prior_fixture(row):
                            home_projection = _projection(
                                row, row["home_team"]
                            )
                            away_projection = _projection(
                                row, row["away_team"]
                            )
                            if home_identity is not None:
                                additions[home_identity].append(home_projection)
                            if away_identity is not None:
                                additions[away_identity].append(away_projection)
                    for identity, projections in additions.items():
                        histories[identity].add_date_bucket(rows[0]["match_date"], projections)

                for row in source.stream_matches():
                    date.fromisoformat(row["match_date"])
                    if current_date is None:
                        current_date = row["match_date"]
                    if row["match_date"] != current_date:
                        process_batch(date_batch)
                        if limit is not None and count >= limit:
                            date_batch = []
                            break
                        date_batch = []
                        current_date = row["match_date"]
                    date_batch.append(row)
                if date_batch:
                    process_batch(date_batch)
                destination.commit()
                source.assert_unchanged()
            finally:
                destination.close()
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, output)
        return count
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--competition")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--replace", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    count = build_corpus(
        args.db, args.output, competition=args.competition, start_date=args.start_date,
        end_date=args.end_date, limit=args.limit, replace=args.replace,
    )
    print(json.dumps({"output": str(args.output.resolve()), "snapshots": count}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
