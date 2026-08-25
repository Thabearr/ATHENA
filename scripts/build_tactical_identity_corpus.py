#!/usr/bin/env python3
"""Build a separate, offline Tactical Identity research corpus."""
from __future__ import annotations

import argparse
import json
import math
import os
import secrets
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.historical_asof_features import (  # noqa: E402
    ReadOnlyHistoricalWarehouse,
    TeamMatchProjection,
    _projection,
    historical_team_identity,
    qualifies_completed_prior_fixture,
)
from domain.tactical_identity import (  # noqa: E402
    COMPETITION_BASELINE_POLICY_ID,
    DESCRIPTOR_POLICY_ID,
    MANAGER_REGIME_POLICY_ID,
    OPPONENT_ADJUSTMENT_POLICY_ID,
    RECENCY_POLICY_ID,
    SHRINKAGE_POLICY_ID,
    TACTICAL_GENERATION_CONTRACT_VERSION,
    TACTICAL_IDENTITY_DATASET,
    TACTICAL_IDENTITY_REGISTRY_VERSION,
    TACTICAL_IDENTITY_SCHEMA_VERSION,
    TACTICAL_SOURCE_FEATURE_IDS,
    BaselineMoment,
    HistoricalFeatureId,
    ReadOnlyHistoricalAsOfCorpus,
    TacticalIdentityError,
    _assemble_tactical_identity_snapshot,
    _blocked,
    _feature_value,
    validate_tactical_generation_contract,
    validate_tactical_identity_registry,
)

DEFAULT_ASOF = ROOT / "data" / "history_features" / "athena_history_asof_features.db"
DEFAULT_WAREHOUSE = ROOT / "database" / "athena_history.db"
DEFAULT_OUTPUT = ROOT / "data" / "history_features" / "athena_tactical_identity.db"


@dataclass
class RollingTeamHistory:
    date_buckets: list[tuple[str, list[TeamMatchProjection]]] = field(default_factory=list)

    def add(self, match_date: str, projections: Iterable[TeamMatchProjection]) -> None:
        bucket = sorted(projections, key=lambda item: item.match_key)
        if not bucket:
            return
        self.date_buckets.append((match_date, bucket))
        # Preserve the complete LAST_20 boundary date, never split a date bucket.
        while len(self.date_buckets) > 1 and sum(
            len(group) for _, group in self.date_buckets[1:]
        ) >= 20:
            self.date_buckets.pop(0)

    def values(self) -> tuple[TeamMatchProjection, ...]:
        return tuple(item for _, bucket in self.date_buckets for item in bucket)


@dataclass
class RunningMoment:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def add(self, value: float) -> None:
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)

    def freeze(self) -> BaselineMoment:
        return BaselineMoment(
            self.count, self.mean if self.count else None,
            math.sqrt(self.m2 / self.count) if self.count else None,
        )


def _safe_paths(main: Path) -> frozenset[Path]:
    resolved = main.resolve()
    return frozenset({resolved} | {
        Path(str(resolved) + suffix) for suffix in ("-wal", "-journal", "-shm")
    })


def _temporary(output: Path, protected: frozenset[Path]) -> Path:
    for _ in range(100):
        candidate = output.with_name(f".{output.name}.{secrets.token_hex(12)}.tmp").resolve()
        if candidate in protected or candidate.exists():
            continue
        descriptor = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        return candidate
    raise TacticalIdentityError("cannot allocate safe Tactical Identity output")


def _create_output(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript("""
        PRAGMA journal_mode=DELETE;
        PRAGMA synchronous=FULL;
        CREATE TABLE corpus_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE tactical_identity_snapshots(
          match_key TEXT PRIMARY KEY,
          match_date TEXT NOT NULL,
          competition_key TEXT NOT NULL,
          canonical_sha256 TEXT NOT NULL,
          payload_json TEXT NOT NULL
        );
        CREATE INDEX idx_tactical_date ON tactical_identity_snapshots(match_date,match_key);
    """)
    return connection


def build_tactical_corpus(
    asof_corpus_path: Path, warehouse_path: Path, output_path: Path, *,
    competition: str | None = None, start_date: str | None = None,
    end_date: str | None = None, limit: int | None = None, replace: bool = False,
) -> int:
    asof_path, warehouse_path = Path(asof_corpus_path).resolve(), Path(warehouse_path).resolve()
    output = Path(output_path).resolve()
    operational = (ROOT / "database" / "athena.db").resolve()
    protected = (_safe_paths(asof_path) | _safe_paths(warehouse_path)
                 | _safe_paths(operational))
    if output in protected:
        raise TacticalIdentityError("output must be separate from all source/operational SQLite paths")
    if output.exists() and not replace:
        raise TacticalIdentityError(f"output already exists: {output}")
    if limit is not None and limit < 1:
        raise TacticalIdentityError("limit must be positive")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary(output, protected)
    registry_sha = validate_tactical_identity_registry()
    generation_sha = validate_tactical_generation_contract(tactical_registry_sha256=registry_sha)
    count = 0
    try:
        with ReadOnlyHistoricalAsOfCorpus(asof_path) as corpus, \
                ReadOnlyHistoricalWarehouse(warehouse_path) as source:
            if corpus.meta["source_warehouse_sha256"] != source.sha256:
                raise TacticalIdentityError("as-of corpus and warehouse SHA mismatch")
            target_keys = {row[0] for row in corpus.iter_targets()}
            histories: dict[tuple[str, str, str], RollingTeamHistory] = defaultdict(RollingTeamHistory)
            moments: dict[tuple[str, str], dict[HistoricalFeatureId, RunningMoment]] = defaultdict(
                lambda: {feature: RunningMoment() for feature in TACTICAL_SOURCE_FEATURE_IDS}
            )
            destination = _create_output(temporary)
            try:
                meta = {
                    "dataset": TACTICAL_IDENTITY_DATASET,
                    "schema_version": TACTICAL_IDENTITY_SCHEMA_VERSION,
                    "source_asof_corpus_sha256": corpus.sha256,
                    "source_warehouse_sha256": source.sha256,
                    "tactical_registry_version": TACTICAL_IDENTITY_REGISTRY_VERSION,
                    "tactical_registry_sha256": registry_sha,
                    "tactical_generation_contract_version": TACTICAL_GENERATION_CONTRACT_VERSION,
                    "tactical_generation_contract_sha256": generation_sha,
                    "recency_policy_id": RECENCY_POLICY_ID,
                    "competition_baseline_policy_id": COMPETITION_BASELINE_POLICY_ID,
                    "shrinkage_policy_id": SHRINKAGE_POLICY_ID,
                    "manager_regime_policy_id": MANAGER_REGIME_POLICY_ID,
                    "opponent_adjustment_policy_id": OPPONENT_ADJUSTMENT_POLICY_ID,
                }
                destination.executemany(
                    "INSERT INTO corpus_meta VALUES(?,?)",
                    sorted((key, json.dumps(value, separators=(",", ":")))
                           for key, value in meta.items()),
                )
                batch: list[Any] = []
                batch_date: str | None = None

                def process(rows: list[Any]) -> None:
                    nonlocal count
                    additions: dict[tuple[str, str, str], list[TeamMatchProjection]] = defaultdict(list)
                    baseline_additions: dict[tuple[str, str], list[TeamMatchProjection]] = defaultdict(list)
                    for row in rows:
                        selected = (row["match_key"] in target_keys
                                    and (competition is None or row["competition_key"] == competition)
                                    and (start_date is None or row["match_date"] >= start_date)
                                    and (end_date is None or row["match_date"] <= end_date)
                                    and (limit is None or count < limit))
                        home_identity = historical_team_identity(
                            row["scope"], row["competition_key"], row["home_team"])
                        away_identity = historical_team_identity(
                            row["scope"], row["competition_key"], row["away_team"])
                        if selected:
                            payload = corpus.snapshot_payload(row["match_key"])
                            baseline_key = (row["scope"], row["competition_key"])
                            snapshot = _assemble_tactical_identity_snapshot(
                                corpus=corpus, source=source, payload=payload, target=row,
                                home_history=histories[home_identity].values() if home_identity else (),
                                away_history=histories[away_identity].values() if away_identity else (),
                                baselines={feature: moment.freeze()
                                           for feature, moment in moments[baseline_key].items()},
                                registry_sha=registry_sha, generation_sha=generation_sha)
                            destination.execute(
                                "INSERT INTO tactical_identity_snapshots VALUES(?,?,?,?,?)",
                                (snapshot.target_match_key, snapshot.target_match_date,
                                 snapshot.target_competition_key, snapshot.canonical_sha256,
                                 snapshot.canonical_bytes.decode("utf-8")))
                            count += 1
                        if qualifies_completed_prior_fixture(row):
                            home = _projection(row, row["home_team"])
                            away = _projection(row, row["away_team"])
                            if home_identity:
                                additions[home_identity].append(home)
                            if away_identity:
                                additions[away_identity].append(away)
                            baseline_additions[(row["scope"], row["competition_key"])].extend((home, away))
                    # Date batch: no row on D affects any target or baseline on D.
                    for identity, projections in additions.items():
                        histories[identity].add(rows[0]["match_date"], projections)
                    for key, projections in baseline_additions.items():
                        for projection in projections:
                            for feature, moment in moments[key].items():
                                if not _blocked(projection, feature):
                                    value = _feature_value(projection, feature)
                                    if value is not None:
                                        moment.add(value)

                for row in source.stream_matches():
                    if batch_date is None:
                        batch_date = row["match_date"]
                    if row["match_date"] != batch_date:
                        process(batch); batch = []; batch_date = row["match_date"]
                    batch.append(row)
                if batch:
                    process(batch)
                destination.commit()
                source.assert_unchanged(); corpus.assert_unchanged()
            finally:
                destination.close()
        os.replace(temporary, output)
        return count
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asof-corpus", type=Path, default=DEFAULT_ASOF)
    parser.add_argument("--warehouse", type=Path, default=DEFAULT_WAREHOUSE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--competition")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    print(build_tactical_corpus(
        args.asof_corpus, args.warehouse, args.output,
        competition=args.competition, start_date=args.start_date,
        end_date=args.end_date, limit=args.limit, replace=args.replace))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
