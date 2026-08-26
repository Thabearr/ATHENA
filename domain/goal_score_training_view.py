"""Canonical three-corpus training-view bridge for Goal/Score Dynamics v2.

Historical As-Of and Tactical Identity provide pre-match model inputs. The #232
coverage corpus provides only safe regulation-score targets; post-match
richness/capability metadata is never a model feature.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import sqlite3
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np

from domain.goal_score_dynamics import (
    AUTHORITY_FLAGS,
    GOAL_SCORE_FEATURE_REGISTRY,
    GOAL_SCORE_FEATURE_REGISTRY_VERSION,
    GOAL_SCORE_SCHEMA_VERSION,
    FeatureStatus,
    GoalScoreError,
    TrainingRow,
    validate_evaluation_contract,
)
from domain._goal_score_training_sources import (
    ReadOnlyCorpus,
    _assert_no_active_companions,
    _extract_features,
    _extract_target,
    _parse_canonical_payload,
    _target_identity,
    _validate_cross_lineage,
    file_sha256,
)

TRAINING_VIEW_DATASET = "athena_goal_score_training_view"
TRAINING_VIEW_SCHEMA_VERSION = 1
TRAINING_VIEW_GENERATION_CONTRACT_VERSION = 1
SOURCE_COMPATIBILITY_POLICY_ID = "EXACT_THREE_CORPUS_SHA_AND_FROZEN_META_BINDING_V1"
TRAINING_ROW_ISSUANCE_POLICY_ID = "SOURCE_REPLAYED_CANONICAL_ROWS_ONLY_V1"
TARGET_JOIN_POLICY_ID = "EXACT_MATCH_KEY_DATE_COMPETITION_SCOPE_V1"
OUTPUT_POLICY_ID = "SEPARATE_EXCLUSIVE_TEMP_ATOMIC_REPLACE_V1"
COMPACT_STATUS_AVAILABLE = 0
COMPACT_STATUS_MISSING = 1
COMPACT_STATUS_BLOCKED = 2


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def training_view_contract_payload(
    evaluation_contract_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": TRAINING_VIEW_SCHEMA_VERSION,
        "goal_score_schema_version": GOAL_SCORE_SCHEMA_VERSION,
        "goal_score_feature_registry_version": GOAL_SCORE_FEATURE_REGISTRY_VERSION,
        "goal_score_evaluation_contract_sha256": evaluation_contract_sha256,
        "source_compatibility_policy_id": SOURCE_COMPATIBILITY_POLICY_ID,
        "training_row_issuance_policy_id": TRAINING_ROW_ISSUANCE_POLICY_ID,
        "target_join_policy_id": TARGET_JOIN_POLICY_ID,
        "output_policy_id": OUTPUT_POLICY_ID,
    }


def calculate_training_view_contract_sha256(
    evaluation_contract_sha256: str,
    version: int = TRAINING_VIEW_GENERATION_CONTRACT_VERSION,
) -> str:
    return hashlib.sha256(_canonical_bytes({
        "version": version,
        "semantics": training_view_contract_payload(
            evaluation_contract_sha256
        ),
    })).hexdigest()


EXPECTED_TRAINING_VIEW_GENERATION_CONTRACT_SHA256_BY_VERSION: Mapping[int, str] = MappingProxyType({
    1: "bac5380814de579dffe96d4e5daa39b0cf1e2d6144b59b5d89f2a81f7b27017b",
})


def validate_training_view_contract() -> tuple[str, str, str, str]:
    feature_sha, model_sha, evaluation_sha = validate_evaluation_contract()
    actual = calculate_training_view_contract_sha256(evaluation_sha)
    expected = EXPECTED_TRAINING_VIEW_GENERATION_CONTRACT_SHA256_BY_VERSION.get(
        TRAINING_VIEW_GENERATION_CONTRACT_VERSION
    )
    if expected is None or actual != expected:
        raise GoalScoreError(
            "Goal/Score training-view generation contract drift"
        )
    return feature_sha, model_sha, evaluation_sha, actual


def _create_output(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript("""
    PRAGMA journal_mode=DELETE;
    PRAGMA synchronous=FULL;
    CREATE TABLE corpus_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE training_population_summary(
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );
    CREATE TABLE training_rows(
      match_key TEXT PRIMARY KEY,
      match_date TEXT NOT NULL,
      scope TEXT NOT NULL,
      competition_key TEXT,
      season TEXT,
      home_goals INTEGER NOT NULL,
      away_goals INTEGER NOT NULL,
      canonical_sha256 TEXT NOT NULL,
      payload_json TEXT NOT NULL
    );
    CREATE INDEX idx_goal_score_training_date
      ON training_rows(match_date,match_key);
    """)
    return connection


def _protected(path: Path) -> set[Path]:
    resolved = path.resolve()
    return {
        resolved,
        *(Path(str(resolved) + suffix)
          for suffix in ("-wal", "-journal", "-shm")),
    }


def _assert_no_output_companions(output: Path) -> None:
    for suffix in ("-wal", "-journal", "-shm"):
        companion = Path(str(output) + suffix)
        if companion.exists():
            raise GoalScoreError(
                f"unsafe output SQLite companion exists: {companion.name}"
            )


def _temporary(output: Path, protected: set[Path]) -> Path:
    for _ in range(100):
        candidate = output.with_name(
            f".{output.name}.{secrets.token_hex(12)}.tmp"
        ).resolve()
        if candidate in protected or candidate.exists():
            continue
        descriptor = os.open(
            candidate,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        os.close(descriptor)
        return candidate
    raise GoalScoreError(
        "unable to allocate exclusive training-view temporary"
    )


def _row_payload(
    *,
    match_key: str,
    match_date: str,
    scope: str,
    competition_key: str | None,
    season: str | None,
    home_goals: int,
    away_goals: int,
    features: Mapping[str, tuple[FeatureStatus, float | None]],
    source_ids: Mapping[str, str],
    contract_ids: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "dataset": TRAINING_VIEW_DATASET,
        "schema_version": TRAINING_VIEW_SCHEMA_VERSION,
        "match_key": match_key,
        "match_date": match_date,
        "scope": scope,
        "competition_key": competition_key,
        "season": season,
        "target": {
            "home_goals": home_goals,
            "away_goals": away_goals,
        },
        "features": {
            key: {"status": status.value, "value": value}
            for key, (status, value) in sorted(features.items())
        },
        "source_identities": dict(sorted(source_ids.items())),
        "contract_identities": dict(sorted(contract_ids.items())),
        "authority_flags": dict(AUTHORITY_FLAGS),
    }


def _selection_where(
    *,
    competition: str | None,
    start_date: str | None,
    end_date: str | None,
    alias: str = "c",
) -> tuple[str, list[Any]]:
    conditions = ["1=1"]
    parameters: list[Any] = []
    if competition is not None:
        conditions.append(f"{alias}.competition_key=?")
        parameters.append(competition)
    if start_date is not None:
        conditions.append(f"{alias}.match_date>=?")
        parameters.append(start_date)
    if end_date is not None:
        conditions.append(f"{alias}.match_date<=?")
        parameters.append(end_date)
    return " AND ".join(conditions), parameters


def _score_ready_join_sql() -> str:
    """Return the label-local eligibility joins used by all training queries."""
    return """
    JOIN c.market_label_resolutions lhg
      ON lhg.match_key=c.match_key
     AND lhg.label_id='HOME_GOALS'
     AND lhg.status='AVAILABLE'
    JOIN c.market_label_resolutions lag
      ON lag.match_key=c.match_key
     AND lag.label_id='AWAY_GOALS'
     AND lag.status='AVAILABLE'
    """


def _population_counts(
    connection: sqlite3.Connection,
    where_sql: str,
    parameters: Sequence[Any],
) -> dict[str, int]:
    coverage_targets = int(connection.execute(
        "SELECT count(*) FROM c.match_evidence_coverage c WHERE " + where_sql,
        tuple(parameters),
    ).fetchone()[0])
    score_ready = int(connection.execute(
        "SELECT count(*) FROM c.match_evidence_coverage c "
        + _score_ready_join_sql()
        + " WHERE "
        + where_sql,
        tuple(parameters),
    ).fetchone()[0])
    three_corpus = int(connection.execute(
        "SELECT count(*) FROM c.match_evidence_coverage c "
        + _score_ready_join_sql()
        + " JOIN a.historical_asof_snapshots a ON a.match_key=c.match_key "
        + " JOIN t.tactical_identity_snapshots t ON t.match_key=c.match_key "
        + " WHERE "
        + where_sql,
        tuple(parameters),
    ).fetchone()[0])
    return {
        "coverage_target_count": coverage_targets,
        "score_target_available_count": score_ready,
        "three_corpus_join_count": three_corpus,
    }


def build_goal_score_training_view(
    asof_path: Path,
    tactical_path: Path,
    coverage_path: Path,
    output_path: Path,
    *,
    replace: bool = False,
    competition: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> int:
    output = Path(output_path).resolve()
    paths = [
        Path(path).resolve()
        for path in (asof_path, tactical_path, coverage_path)
    ]
    protected = set().union(*(_protected(path) for path in paths))
    operational = (
        Path(__file__).resolve().parents[1] / "database" / "athena.db"
    ).resolve()
    protected |= _protected(operational)
    if output in protected:
        raise GoalScoreError(
            "training-view output collides with protected SQLite source"
        )
    _assert_no_output_companions(output)
    if output.exists() and not replace:
        raise GoalScoreError(
            "training-view output exists; pass --replace"
        )
    if limit is not None and limit < 1:
        raise GoalScoreError("limit must be positive")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise GoalScoreError("start-date must not exceed end-date")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary(output, protected)
    feature_sha, model_sha, evaluation_sha, training_contract_sha = (
        validate_training_view_contract()
    )
    count = 0
    try:
        with (
            ReadOnlyCorpus(paths[0], "ASOF") as asof,
            ReadOnlyCorpus(paths[1], "TACTICAL") as tactical,
            ReadOnlyCorpus(paths[2], "COVERAGE") as coverage,
        ):
            warehouse_sha = _validate_cross_lineage(
                asof,
                tactical,
                coverage,
            )
            connection = sqlite3.connect(":memory:", uri=True)
            connection.row_factory = sqlite3.Row
            try:
                connection.execute(
                    "ATTACH DATABASE ? AS a",
                    (f"{asof.path.as_uri()}?mode=ro",),
                )
                connection.execute(
                    "ATTACH DATABASE ? AS t",
                    (f"{tactical.path.as_uri()}?mode=ro",),
                )
                connection.execute(
                    "ATTACH DATABASE ? AS c",
                    (f"{coverage.path.as_uri()}?mode=ro",),
                )
                where_sql, parameters = _selection_where(
                    competition=competition,
                    start_date=start_date,
                    end_date=end_date,
                )
                population = _population_counts(
                    connection,
                    where_sql,
                    parameters,
                )
                query = (
                    "SELECT c.match_key,c.match_date,c.scope,"
                    "c.competition_key,c.season,"
                    "c.canonical_sha256 coverage_sha,"
                    "c.payload_json coverage_payload,"
                    "a.canonical_sha256 asof_sha,"
                    "a.payload_json asof_payload,"
                    "t.canonical_sha256 tactical_sha,"
                    "t.payload_json tactical_payload "
                    "FROM c.match_evidence_coverage c "
                    + _score_ready_join_sql()
                    + " JOIN a.historical_asof_snapshots a "
                    "ON a.match_key=c.match_key "
                    "JOIN t.tactical_identity_snapshots t "
                    "ON t.match_key=c.match_key WHERE "
                    + where_sql
                    + " ORDER BY c.match_date,c.match_key"
                )
                query_parameters = list(parameters)
                if limit is not None:
                    query += " LIMIT ?"
                    query_parameters.append(limit)
                destination = _create_output(temporary)
                try:
                    metadata = {
                        "dataset": TRAINING_VIEW_DATASET,
                        "schema_version": TRAINING_VIEW_SCHEMA_VERSION,
                        "source_asof_corpus_sha256": asof.sha256,
                        "source_tactical_corpus_sha256": tactical.sha256,
                        "source_coverage_corpus_sha256": coverage.sha256,
                        "source_warehouse_sha256": warehouse_sha,
                        "goal_score_feature_registry_version": (
                            GOAL_SCORE_FEATURE_REGISTRY_VERSION
                        ),
                        "goal_score_feature_registry_sha256": feature_sha,
                        "goal_score_model_registry_sha256": model_sha,
                        "goal_score_evaluation_contract_sha256": evaluation_sha,
                        "training_view_generation_contract_version": (
                            TRAINING_VIEW_GENERATION_CONTRACT_VERSION
                        ),
                        "training_view_generation_contract_sha256": (
                            training_contract_sha
                        ),
                        "authority_flags": dict(AUTHORITY_FLAGS),
                    }
                    destination.executemany(
                        "INSERT INTO corpus_meta VALUES(?,?)",
                        [
                            (
                                key,
                                json.dumps(
                                    value,
                                    sort_keys=True,
                                    separators=(",", ":"),
                                    allow_nan=False,
                                ),
                            )
                            for key, value in sorted(metadata.items())
                        ],
                    )
                    source_ids = {
                        "asof_corpus_sha256": asof.sha256,
                        "tactical_corpus_sha256": tactical.sha256,
                        "coverage_corpus_sha256": coverage.sha256,
                        "warehouse_sha256": warehouse_sha,
                    }
                    contract_ids = {
                        "feature_registry_sha256": feature_sha,
                        "model_registry_sha256": model_sha,
                        "evaluation_contract_sha256": evaluation_sha,
                        "training_view_contract_sha256": training_contract_sha,
                    }
                    for row in connection.execute(
                        query,
                        tuple(query_parameters),
                    ):
                        asof_payload = _parse_canonical_payload(
                            row["asof_payload"],
                            row["asof_sha"],
                            "as-of",
                        )
                        tactical_payload = _parse_canonical_payload(
                            row["tactical_payload"],
                            row["tactical_sha"],
                            "Tactical",
                        )
                        coverage_payload = _parse_canonical_payload(
                            row["coverage_payload"],
                            row["coverage_sha"],
                            "coverage",
                        )
                        identities = (
                            _target_identity(asof_payload, "ASOF"),
                            _target_identity(tactical_payload, "TACTICAL"),
                            _target_identity(coverage_payload, "COVERAGE"),
                        )
                        if not identities[0] == identities[1] == identities[2]:
                            raise GoalScoreError(
                                "three-corpus target identity mismatch"
                            )
                        home_goals, away_goals = _extract_target(
                            coverage_payload
                        )
                        features = _extract_features(
                            asof_payload,
                            tactical_payload,
                        )
                        payload = _row_payload(
                            match_key=row["match_key"],
                            match_date=row["match_date"],
                            scope=row["scope"],
                            competition_key=row["competition_key"],
                            season=row["season"],
                            home_goals=home_goals,
                            away_goals=away_goals,
                            features=features,
                            source_ids={
                                **source_ids,
                                "asof_row_sha256": row["asof_sha"],
                                "tactical_row_sha256": row["tactical_sha"],
                                "coverage_row_sha256": row["coverage_sha"],
                            },
                            contract_ids=contract_ids,
                        )
                        raw = _canonical_bytes(payload)
                        canonical_sha = hashlib.sha256(raw).hexdigest()
                        destination.execute(
                            "INSERT INTO training_rows VALUES(?,?,?,?,?,?,?,?,?)",
                            (
                                row["match_key"],
                                row["match_date"],
                                row["scope"],
                                row["competition_key"],
                                row["season"],
                                home_goals,
                                away_goals,
                                canonical_sha,
                                raw.decode("utf-8"),
                            ),
                        )
                        count += 1
                        if count % 500 == 0:
                            destination.commit()
                    population.update({
                        "emitted_target_count": count,
                        "development_limit": (
                            -1 if limit is None else limit
                        ),
                    })
                    destination.executemany(
                        "INSERT INTO training_population_summary VALUES(?,?)",
                        [
                            (
                                key,
                                json.dumps(
                                    value,
                                    sort_keys=True,
                                    separators=(",", ":"),
                                ),
                            )
                            for key, value in sorted(population.items())
                        ],
                    )
                    destination.commit()
                finally:
                    destination.close()
            finally:
                connection.close()
            asof.assert_unchanged()
            tactical.assert_unchanged()
            coverage.assert_unchanged()
        for suffix in ("-wal", "-journal", "-shm"):
            if Path(str(temporary) + suffix).exists():
                raise GoalScoreError(
                    "temporary training-view SQLite companion remains"
                )
        _assert_no_output_companions(output)
        os.replace(temporary, output)
        return count
    finally:
        if temporary.exists():
            temporary.unlink()
        for suffix in ("-wal", "-journal", "-shm"):
            companion = Path(str(temporary) + suffix)
            if companion.exists():
                companion.unlink()


def _validated_training_connection(
    path: Path,
) -> tuple[sqlite3.Connection, dict[str, Any], Any, str]:
    feature_sha, model_sha, evaluation_sha, training_sha = (
        validate_training_view_contract()
    )
    source = Path(path).resolve()
    if not source.is_file():
        raise GoalScoreError(f"training view unavailable: {source}")
    _assert_no_active_companions(source)
    before = source.stat()
    source_sha = file_sha256(source)
    connection = sqlite3.connect(
        f"{source.as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        required = {
            "corpus_meta",
            "training_rows",
            "training_population_summary",
        }
        if not required.issubset(tables):
            raise GoalScoreError("training-view schema mismatch")
        metadata = {
            key: json.loads(value)
            for key, value in connection.execute(
                "SELECT key,value FROM corpus_meta"
            )
        }
        expected = {
            "dataset": TRAINING_VIEW_DATASET,
            "schema_version": TRAINING_VIEW_SCHEMA_VERSION,
            "goal_score_feature_registry_version": (
                GOAL_SCORE_FEATURE_REGISTRY_VERSION
            ),
            "goal_score_feature_registry_sha256": feature_sha,
            "goal_score_model_registry_sha256": model_sha,
            "goal_score_evaluation_contract_sha256": evaluation_sha,
            "training_view_generation_contract_version": (
                TRAINING_VIEW_GENERATION_CONTRACT_VERSION
            ),
            "training_view_generation_contract_sha256": training_sha,
        }
        if any(metadata.get(key) != value for key, value in expected.items()):
            raise GoalScoreError("training-view frozen identity mismatch")
        return connection, metadata, before, source_sha
    except Exception:
        connection.close()
        raise


def _assert_training_source_unchanged(
    source: Path,
    before: Any,
    source_sha: str,
) -> None:
    _assert_no_active_companions(source)
    after = source.stat()
    if (
        (after.st_size, after.st_mtime_ns)
        != (before.st_size, before.st_mtime_ns)
        or file_sha256(source) != source_sha
    ):
        raise GoalScoreError("training view changed during read")


def _decoded_training_payload(
    record: sqlite3.Row,
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    payload = _parse_canonical_payload(
        record["payload_json"],
        record["canonical_sha256"],
        "training-view",
    )
    if (
        payload.get("match_key") != record["match_key"]
        or payload.get("match_date") != record["match_date"]
    ):
        raise GoalScoreError("training-view row identity mismatch")
    target = payload.get("target")
    features = payload.get("features")
    if not isinstance(target, dict) or not isinstance(features, dict):
        raise GoalScoreError("training-view payload incomplete")
    registered = {item.feature_id for item in GOAL_SCORE_FEATURE_REGISTRY}
    if set(features) != registered:
        raise GoalScoreError(
            "training-view feature registry coverage mismatch"
        )
    return payload, target, features


def load_training_rows(path: Path) -> tuple[TrainingRow, ...]:
    source = Path(path).resolve()
    connection, _metadata, before, source_sha = (
        _validated_training_connection(source)
    )
    rows: list[TrainingRow] = []
    try:
        for record in connection.execute(
            "SELECT * FROM training_rows ORDER BY match_date,match_key"
        ):
            _payload, target, features = _decoded_training_payload(record)
            converted: dict[str, tuple[FeatureStatus, float | None]] = {}
            for key, item in features.items():
                if not isinstance(item, dict):
                    raise GoalScoreError(
                        "invalid training-view feature resolution"
                    )
                try:
                    status = FeatureStatus(str(item.get("status")))
                except ValueError as exc:
                    raise GoalScoreError(
                        "unknown training-view feature status"
                    ) from exc
                value = item.get("value")
                if status is FeatureStatus.AVAILABLE and (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                ):
                    raise GoalScoreError(
                        "invalid AVAILABLE training-view feature"
                    )
                converted[key] = (
                    status,
                    None
                    if status is not FeatureStatus.AVAILABLE
                    else float(value),
                )
            rows.append(TrainingRow(
                match_key=str(record["match_key"]),
                match_date=str(record["match_date"]),
                scope=str(record["scope"]),
                competition_key=record["competition_key"],
                season=record["season"],
                home_goals=int(target["home_goals"]),
                away_goals=int(target["away_goals"]),
                features=MappingProxyType(converted),
                canonical_sha256=str(record["canonical_sha256"]),
            ))
        _assert_training_source_unchanged(source, before, source_sha)
        return tuple(rows)
    finally:
        connection.close()


@dataclass(frozen=True)
class CompactTrainingData:
    """Single-parse numeric representation for corpus-scale evaluation."""

    feature_ids: tuple[str, ...]
    match_keys: np.ndarray
    match_dates: np.ndarray
    scopes: np.ndarray
    competition_keys: np.ndarray
    seasons: np.ndarray
    home_goals: np.ndarray
    away_goals: np.ndarray
    values: np.ndarray
    statuses: np.ndarray

    def __post_init__(self) -> None:
        rows = len(self.match_keys)
        if self.values.shape != (rows, len(self.feature_ids)):
            raise GoalScoreError("compact feature shape mismatch")
        if self.statuses.shape != self.values.shape:
            raise GoalScoreError("compact status shape mismatch")
        if self.values.dtype != np.float32:
            raise GoalScoreError("compact feature matrix must be float32")
        if self.statuses.dtype != np.uint8:
            raise GoalScoreError("compact status matrix must be uint8")

    def subset(self, indices: Sequence[int] | np.ndarray) -> "CompactTrainingData":
        index = np.asarray(indices, dtype=int)
        return CompactTrainingData(
            self.feature_ids,
            self.match_keys[index],
            self.match_dates[index],
            self.scopes[index],
            self.competition_keys[index],
            self.seasons[index],
            self.home_goals[index],
            self.away_goals[index],
            self.values[index],
            self.statuses[index],
        )

    def to_rows(
        self,
        indices: Sequence[int] | np.ndarray | None = None,
    ) -> tuple[TrainingRow, ...]:
        selected = (
            np.arange(len(self.match_keys), dtype=int)
            if indices is None
            else np.asarray(indices, dtype=int)
        )
        result: list[TrainingRow] = []
        for row_index in selected:
            features: dict[str, tuple[FeatureStatus, float | None]] = {}
            for feature_index, feature_id in enumerate(self.feature_ids):
                status_code = int(self.statuses[row_index, feature_index])
                status = (
                    FeatureStatus.AVAILABLE
                    if status_code == COMPACT_STATUS_AVAILABLE
                    else FeatureStatus.MISSING
                    if status_code == COMPACT_STATUS_MISSING
                    else FeatureStatus.BLOCKED
                    if status_code == COMPACT_STATUS_BLOCKED
                    else None
                )
                if status is None:
                    raise GoalScoreError("invalid compact feature status code")
                features[feature_id] = (
                    status,
                    float(self.values[row_index, feature_index])
                    if status is FeatureStatus.AVAILABLE
                    else None,
                )
            result.append(TrainingRow(
                match_key=str(self.match_keys[row_index]),
                match_date=str(self.match_dates[row_index]),
                scope=str(self.scopes[row_index]),
                competition_key=(
                    None
                    if self.competition_keys[row_index] is None
                    else str(self.competition_keys[row_index])
                ),
                season=(
                    None
                    if self.seasons[row_index] is None
                    else str(self.seasons[row_index])
                ),
                home_goals=int(self.home_goals[row_index]),
                away_goals=int(self.away_goals[row_index]),
                features=MappingProxyType(features),
            ))
        return tuple(result)


def load_compact_training_data(path: Path) -> CompactTrainingData:
    """Parse canonical rows once into bounded numeric arrays.

    The full nested feature dictionaries are not retained. Values use float32;
    source state is held separately as uint8 codes. This is the preferred
    full-corpus loading path for the challenger runner.
    """
    source = Path(path).resolve()
    connection, _metadata, before, source_sha = (
        _validated_training_connection(source)
    )
    feature_ids = tuple(
        item.feature_id for item in GOAL_SCORE_FEATURE_REGISTRY
    )
    row_count = int(connection.execute(
        "SELECT count(*) FROM training_rows"
    ).fetchone()[0])
    values = np.full(
        (row_count, len(feature_ids)),
        np.nan,
        dtype=np.float32,
    )
    statuses = np.empty(
        (row_count, len(feature_ids)),
        dtype=np.uint8,
    )
    match_keys = np.empty(row_count, dtype=object)
    match_dates = np.empty(row_count, dtype=object)
    scopes = np.empty(row_count, dtype=object)
    competition_keys = np.empty(row_count, dtype=object)
    seasons = np.empty(row_count, dtype=object)
    home_goals = np.empty(row_count, dtype=np.int16)
    away_goals = np.empty(row_count, dtype=np.int16)
    try:
        for row_index, record in enumerate(connection.execute(
            "SELECT * FROM training_rows ORDER BY match_date,match_key"
        )):
            _payload, target, features = _decoded_training_payload(record)
            match_keys[row_index] = record["match_key"]
            match_dates[row_index] = record["match_date"]
            scopes[row_index] = record["scope"]
            competition_keys[row_index] = record["competition_key"]
            seasons[row_index] = record["season"]
            for target_key, target_array in (
                ("home_goals", home_goals),
                ("away_goals", away_goals),
            ):
                target_value = target.get(target_key)
                if (
                    isinstance(target_value, bool)
                    or not isinstance(target_value, int)
                    or target_value < 0
                    or target_value > np.iinfo(np.int16).max
                ):
                    raise GoalScoreError(
                        "invalid compact regulation-score target"
                    )
                target_array[row_index] = target_value
            for feature_index, feature_id in enumerate(feature_ids):
                item = features[feature_id]
                if not isinstance(item, dict):
                    raise GoalScoreError(
                        "invalid training-view feature resolution"
                    )
                try:
                    status = FeatureStatus(str(item.get("status")))
                except ValueError as exc:
                    raise GoalScoreError(
                        "unknown training-view feature status"
                    ) from exc
                if status is FeatureStatus.AVAILABLE:
                    value = item.get("value")
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(float(value))
                    ):
                        raise GoalScoreError(
                            "invalid AVAILABLE training-view feature"
                        )
                    numeric = np.float32(value)
                    if not np.isfinite(numeric):
                        raise GoalScoreError(
                            "feature cannot be represented safely as float32"
                        )
                    values[row_index, feature_index] = numeric
                    statuses[row_index, feature_index] = COMPACT_STATUS_AVAILABLE
                elif status is FeatureStatus.MISSING:
                    statuses[row_index, feature_index] = COMPACT_STATUS_MISSING
                else:
                    statuses[row_index, feature_index] = COMPACT_STATUS_BLOCKED
        _assert_training_source_unchanged(source, before, source_sha)
        return CompactTrainingData(
            feature_ids,
            match_keys,
            match_dates,
            scopes,
            competition_keys,
            seasons,
            home_goals,
            away_goals,
            values,
            statuses,
        )
    finally:
        connection.close()


__all__ = [
    "COMPACT_STATUS_AVAILABLE",
    "COMPACT_STATUS_BLOCKED",
    "COMPACT_STATUS_MISSING",
    "CompactTrainingData",
    "EXPECTED_TRAINING_VIEW_GENERATION_CONTRACT_SHA256_BY_VERSION",
    "OUTPUT_POLICY_ID",
    "ReadOnlyCorpus",
    "SOURCE_COMPATIBILITY_POLICY_ID",
    "TARGET_JOIN_POLICY_ID",
    "TRAINING_ROW_ISSUANCE_POLICY_ID",
    "TRAINING_VIEW_DATASET",
    "TRAINING_VIEW_GENERATION_CONTRACT_VERSION",
    "TRAINING_VIEW_SCHEMA_VERSION",
    "build_goal_score_training_view",
    "calculate_training_view_contract_sha256",
    "file_sha256",
    "load_compact_training_data",
    "load_training_rows",
    "validate_training_view_contract",
]
