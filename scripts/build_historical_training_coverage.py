#!/usr/bin/env python3
"""Build the offline historical richness and canonical market-label corpus."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import date
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
from typing import Any, Iterable

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
    build_coverage_rows_from_bound_source,
    validate_contracts,
)

BATCH_SIZE = 500


def _protected_sqlite_paths(path: Path) -> frozenset[Path]:
    main = path.resolve()
    return frozenset(
        {main}
        | {
            Path(str(main) + suffix)
            for suffix in ("-wal", "-journal", "-shm")
        }
    )


def _assert_no_output_companions(output: Path) -> None:
    for suffix in ("-wal", "-journal", "-shm"):
        companion = Path(str(output) + suffix)
        if companion.exists():
            raise HistoricalTrainingCoverageError(
                f"unsafe output SQLite companion exists: {companion.name}"
            )


def _allocate_temporary(output: Path, protected: frozenset[Path]) -> Path:
    for _ in range(100):
        candidate = output.with_name(
            f".{output.name}.{secrets.token_hex(12)}.tmp"
        ).resolve()
        if candidate in protected or candidate.exists():
            continue
        descriptor = os.open(
            candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
        os.close(descriptor)
        return candidate
    raise HistoricalTrainingCoverageError(
        "unable to allocate safe exclusive temporary output"
    )


def _create_output(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
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
        CREATE INDEX idx_training_labels_family_status
          ON market_label_resolutions(market_family,status,match_key);
        CREATE INDEX idx_training_capabilities_status
          ON evidence_capability_resolutions(capability_id,status);
        """
    )
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


def _selected(
    row: Any,
    competition: str | None,
    start_date: str | None,
    end_date: str | None,
) -> bool:
    return (
        (competition is None or row["competition_key"] == competition)
        and (start_date is None or row["match_date"] >= start_date)
        and (end_date is None or row["match_date"] <= end_date)
    )


def _group_specs(connection: sqlite3.Connection) -> list[tuple[str, str, str, tuple[Any, ...]]]:
    specs: list[tuple[str, str, str, tuple[Any, ...]]] = [
        ("CORPUS", "ALL", "1=1", ()),
    ]
    for group_type, column in (
        ("SCOPE", "scope"),
        ("COMPETITION", "competition_key"),
        ("SEASON", "season"),
        ("DATA_QUALITY", "data_quality"),
    ):
        values = [
            row[0]
            for row in connection.execute(
                f"SELECT DISTINCT coalesce({column},'UNKNOWN') "
                f"FROM match_evidence_coverage ORDER BY 1"
            )
        ]
        for value in values:
            specs.append(
                (
                    group_type,
                    str(value),
                    f"coalesce(m.{column},'UNKNOWN')=?",
                    (value,),
                )
            )
    return specs


def _insert_status_triplet(
    connection: sqlite3.Connection,
    *,
    group_type: str,
    group_key: str,
    item_type: str,
    item_id: str,
    total: int,
    counts: dict[str, int],
) -> None:
    available = counts.get("AVAILABLE", 0)
    blocked = counts.get("BLOCKED", 0)
    coverage_rate = available / total
    blocked_rate = blocked / total
    for status in ("AVAILABLE", "MISSING", "BLOCKED"):
        connection.execute(
            "INSERT INTO coverage_summary VALUES(?,?,?,?,?,?,?,?,?)",
            (
                group_type,
                group_key,
                item_type,
                item_id,
                status,
                total,
                counts.get(status, 0),
                coverage_rate,
                blocked_rate,
            ),
        )


def _write_summary(connection: sqlite3.Connection) -> None:
    for group_type, group_key, predicate, parameters in _group_specs(connection):
        total = connection.execute(
            "SELECT count(*) FROM match_evidence_coverage m WHERE " + predicate,
            parameters,
        ).fetchone()[0]
        if not total:
            continue

        for item_type, table, id_column in (
            ("LABEL", "market_label_resolutions", "label_id"),
            ("CAPABILITY", "evidence_capability_resolutions", "capability_id"),
        ):
            grouped: dict[str, dict[str, int]] = {}
            for item_id, status, count in connection.execute(
                f"SELECT r.{id_column},r.status,count(*) FROM {table} r "
                "JOIN match_evidence_coverage m ON m.match_key=r.match_key "
                f"WHERE {predicate} GROUP BY r.{id_column},r.status "
                f"ORDER BY r.{id_column},r.status",
                parameters,
            ):
                grouped.setdefault(str(item_id), {})[str(status)] = int(count)
            for item_id, counts in grouped.items():
                _insert_status_triplet(
                    connection,
                    group_type=group_type,
                    group_key=group_key,
                    item_type=item_type,
                    item_id=item_id,
                    total=total,
                    counts=counts,
                )

        family_counts: dict[str, dict[str, int]] = {}
        for family, status, count in connection.execute(
            f"""
            WITH per_match AS (
              SELECT r.match_key,r.market_family,
                CASE WHEN sum(r.status='BLOCKED')>0 THEN 'BLOCKED'
                     WHEN sum(r.status='AVAILABLE')=count(*) THEN 'AVAILABLE'
                     ELSE 'MISSING' END AS family_status
              FROM market_label_resolutions r
              JOIN match_evidence_coverage m ON m.match_key=r.match_key
              WHERE r.market_family IS NOT NULL AND {predicate}
              GROUP BY r.match_key,r.market_family
            )
            SELECT market_family,family_status,count(*)
            FROM per_match
            GROUP BY market_family,family_status
            ORDER BY market_family,family_status
            """,
            parameters,
        ):
            family_counts.setdefault(str(family), {})[str(status)] = int(count)
        for family, counts in family_counts.items():
            _insert_status_triplet(
                connection,
                group_type=group_type,
                group_key=group_key,
                item_type="MARKET_FAMILY",
                item_id=family,
                total=total,
                counts=counts,
            )


def _write_result(
    destination: sqlite3.Connection,
    result: Any,
    label_families: dict[str, str | None],
) -> None:
    destination.execute(
        "INSERT INTO match_evidence_coverage VALUES(?,?,?,?,?,?,?,?)",
        (
            result.match_key,
            result.match_date,
            result.scope,
            result.competition_key,
            result.season,
            result.data_quality,
            result.canonical_sha256,
            result.canonical_bytes.decode("utf-8"),
        ),
    )
    for label_id, resolution in result.labels:
        value = resolution.value
        if hasattr(value, "value"):
            value = value.value
        destination.execute(
            "INSERT INTO market_label_resolutions VALUES(?,?,?,?,?,?,?)",
            (
                result.match_key,
                label_id,
                label_families[label_id],
                resolution.status.value,
                None
                if value is None
                else json.dumps(
                    value,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ),
                resolution.blocker,
                json.dumps(
                    list(resolution.evidence_identities), separators=(",", ":")
                ),
            ),
        )
    for capability_id, resolution in result.capabilities:
        destination.execute(
            "INSERT INTO evidence_capability_resolutions VALUES(?,?,?,?,?,?)",
            (
                result.match_key,
                capability_id,
                resolution.status.value,
                None
                if resolution.value is None
                else json.dumps(
                    resolution.value,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ),
                resolution.blocker,
                json.dumps(
                    list(resolution.evidence_identities), separators=(",", ":")
                ),
            ),
        )


def build_corpus(
    warehouse_path: Path,
    output_path: Path,
    *,
    asof_corpus: Path | None = None,
    tactical_corpus: Path | None = None,
    competition: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
    replace: bool = False,
) -> int:
    warehouse = Path(warehouse_path).resolve()
    output = Path(output_path).resolve()
    operational = (ROOT / "database" / "athena.db").resolve()
    protected = _protected_sqlite_paths(warehouse) | _protected_sqlite_paths(
        operational
    )
    optional_paths = [
        Path(value).resolve() for value in (asof_corpus, tactical_corpus) if value
    ]
    for path in optional_paths:
        protected |= _protected_sqlite_paths(path)
    if output in protected:
        raise HistoricalTrainingCoverageError(
            "output collides with a protected SQLite path"
        )
    _assert_no_output_companions(output)
    if output.exists() and not replace:
        raise HistoricalTrainingCoverageError(
            "output exists; pass --replace explicitly"
        )
    if limit is not None and limit < 1:
        raise HistoricalTrainingCoverageError("limit must be positive")
    for value in (start_date, end_date):
        if value is not None:
            try:
                parsed = date.fromisoformat(value)
            except (TypeError, ValueError) as exc:
                raise HistoricalTrainingCoverageError(
                    "date filters must be ISO YYYY-MM-DD"
                ) from exc
            if parsed.isoformat() != value:
                raise HistoricalTrainingCoverageError(
                    "date filters must be canonical ISO YYYY-MM-DD"
                )
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HistoricalTrainingCoverageError("start-date must not exceed end-date")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = _allocate_temporary(output, protected)
    temp_companions = [
        Path(str(temporary) + suffix) for suffix in ("-wal", "-journal", "-shm")
    ]
    registry_sha, market_sha, generation_sha = validate_contracts()
    count = 0
    try:
        with ExitStack() as stack:
            source = stack.enter_context(ReadOnlyHistoricalWarehouse(warehouse))
            asof = (
                stack.enter_context(
                    ReadOnlyOptionalJoinCorpus(
                        Path(asof_corpus), "ASOF", source.sha256
                    )
                )
                if asof_corpus
                else None
            )
            tactical = (
                stack.enter_context(
                    ReadOnlyOptionalJoinCorpus(
                        Path(tactical_corpus),
                        "TACTICAL",
                        source.sha256,
                        expected_asof_sha256=None if asof is None else asof.sha256,
                    )
                )
                if tactical_corpus
                else None
            )
            destination = _create_output(temporary)
            try:
                meta = {
                    "dataset": DATASET,
                    "schema_version": SCHEMA_VERSION,
                    "source_warehouse_sha256": source.sha256,
                    "source_warehouse_schema_version": source.schema_version,
                    "source_schema_sql_sha256": source.schema_sql_sha256,
                    "market_label_registry_version": MARKET_LABEL_REGISTRY_VERSION,
                    "market_label_registry_sha256": registry_sha,
                    "canonical_market_semantics_sha256": market_sha,
                    "generation_contract_version": LABEL_GENERATION_CONTRACT_VERSION,
                    "generation_contract_sha256": generation_sha,
                    "source_asof_corpus_sha256": None if asof is None else asof.sha256,
                    "source_tactical_corpus_sha256": (
                        None if tactical is None else tactical.sha256
                    ),
                    "authority_flags": dict(AUTHORITY_FLAGS),
                }
                destination.executemany(
                    "INSERT INTO corpus_meta VALUES(?,?)",
                    sorted(
                        (
                            key,
                            json.dumps(
                                value,
                                sort_keys=True,
                                separators=(",", ":"),
                                allow_nan=False,
                            ),
                        )
                        for key, value in meta.items()
                    ),
                )
                selected: Iterable[Any] = (
                    row
                    for row in source.stream_matches()
                    if _selected(row, competition, start_date, end_date)
                )
                if limit is not None:
                    import itertools

                    selected = itertools.islice(selected, limit)
                label_families = {
                    item.label_id: None if item.family is None else item.family.value
                    for item in MARKET_LABEL_REGISTRY
                }
                for batch in _chunks(selected):
                    results = build_coverage_rows_from_bound_source(
                        source,
                        batch,
                        asof_corpus=asof,
                        tactical_corpus=tactical,
                    )
                    if len(results) != len(batch):
                        raise HistoricalTrainingCoverageError(
                            "source-replayed batch cardinality mismatch"
                        )
                    for result in results:
                        _write_result(destination, result, label_families)
                        count += 1
                    destination.commit()
                _write_summary(destination)
                destination.commit()
                destination.close()
                destination = None

                source.assert_unchanged()
                if asof is not None:
                    asof.assert_unchanged()
                if tactical is not None:
                    tactical.assert_unchanged()
                _assert_no_output_companions(output)
                if any(path.exists() for path in temp_companions):
                    raise HistoricalTrainingCoverageError(
                        "temporary output retained an unsafe SQLite companion"
                    )
            finally:
                if destination is not None:
                    destination.close()
        os.replace(temporary, output)
        return count
    finally:
        if temporary.exists():
            temporary.unlink()
        for companion in temp_companions:
            if companion.exists():
                companion.unlink()


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
    print(
        build_corpus(
            args.db,
            args.output,
            asof_corpus=args.asof_corpus,
            tactical_corpus=args.tactical_corpus,
            competition=args.competition,
            start_date=args.start_date,
            end_date=args.end_date,
            limit=args.limit,
            replace=args.replace,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
