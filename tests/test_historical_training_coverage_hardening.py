from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

import domain.historical_training_coverage as htc
from domain.historical_asof_features import ReadOnlyHistoricalWarehouse
from scripts.build_historical_asof_feature_corpus import build_corpus as build_asof_corpus
from scripts.build_historical_warehouse import Warehouse


def _warehouse(tmp_path: Path) -> tuple[Path, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "history.db"
    warehouse = Warehouse(path)
    warehouse.initialize()
    key = warehouse.upsert_match(
        {
            "competition_key": "eng_premier",
            "competition_name": "Premier League",
            "scope": "club",
            "season": "2025-26",
            "match_date": "2025-01-02",
            "home_team": "Home",
            "away_team": "Away",
            "home_score_ft": 1,
            "away_score_ft": 0,
        },
        source_key="football_data_uk",
        source_match_id="m1",
    )
    warehouse.close()
    return path, key


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_fake_source_object_cannot_enter_canonical_builder():
    class FakeSource:
        def _require_bound_row(self, _row):
            return None

    with pytest.raises(
        htc.HistoricalTrainingCoverageError,
        match="canonical read-only warehouse",
    ):
        htc.build_coverage_rows_from_bound_source(FakeSource(), ())


def test_optional_corpus_object_mutation_loses_issuance(tmp_path: Path):
    warehouse_path, key = _warehouse(tmp_path)
    asof_path = tmp_path / "asof.db"
    assert build_asof_corpus(warehouse_path, asof_path) == 1
    with ReadOnlyHistoricalWarehouse(warehouse_path) as source:
        row = source.target_match(key)
        corpus = htc.ReadOnlyOptionalJoinCorpus(
            asof_path, "ASOF", source.sha256
        )
        try:
            corpus.sha256 = "0" * 64
            with pytest.raises(
                htc.HistoricalTrainingCoverageError,
                match="changed after canonical issuance",
            ):
                htc.build_coverage_rows_from_bound_source(
                    source, (row,), asof_corpus=corpus
                )
        finally:
            corpus.close()


def test_optional_row_must_match_exact_bound_warehouse_target(tmp_path: Path):
    warehouse_path, _ = _warehouse(tmp_path)
    asof_path = tmp_path / "asof.db"
    assert build_asof_corpus(warehouse_path, asof_path) == 1
    connection = sqlite3.connect(asof_path)
    match_key, payload_json = connection.execute(
        "SELECT match_key,payload_json FROM historical_asof_snapshots"
    ).fetchone()
    payload = json.loads(payload_json)
    payload["target"]["home_team"] = "Forged Home"
    canonical = _canonical_bytes(payload)
    connection.execute(
        "UPDATE historical_asof_snapshots SET payload_json=?,canonical_sha256=? "
        "WHERE match_key=?",
        (canonical.decode("utf-8"), hashlib.sha256(canonical).hexdigest(), match_key),
    )
    connection.commit()
    connection.close()
    with pytest.raises(
        htc.HistoricalTrainingCoverageError,
        match="target does not match bound warehouse",
    ):
        from scripts.build_historical_training_coverage import build_corpus

        build_corpus(
            warehouse_path,
            tmp_path / "coverage.db",
            asof_corpus=asof_path,
        )


def test_regulation_path_identity_excludes_et_event_ids(tmp_path: Path):
    warehouse_path, key = _warehouse(tmp_path)
    connection = sqlite3.connect(warehouse_path)
    connection.execute(
        "INSERT OR REPLACE INTO warehouse_match_sources"
        "(match_key,source_key,source_match_id,has_ft,has_events) "
        "VALUES(?,?,?,1,1)",
        (key, "statsbomb_open", "events"),
    )
    events = (
        ("reg-goal", "Home", 10, 5, "1"),
        ("et-goal", "Away", 100, 3, "3"),
    )
    for event_key, team, minute, second, period in events:
        connection.execute(
            """INSERT INTO warehouse_events(
                event_key,match_key,source_key,event_type,team,minute,
                stoppage_minute,second,period,is_penalty,is_own_goal,details_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                event_key,
                key,
                "statsbomb_open",
                "goal",
                team,
                minute,
                0,
                second,
                period,
                0,
                0,
                json.dumps({"type": "Shot"}),
            ),
        )
    connection.commit()
    connection.close()

    row = htc.build_historical_training_coverage_row(warehouse_path, key)
    capability = dict(row.capabilities)["COMPLETE_REGULATION_GOAL_PATH"]
    assert capability.status is htc.ResolutionStatus.AVAILABLE
    assert "PREFERRED_EVENT:reg-goal" in capability.evidence_identities
    assert "PREFERRED_EVENT:et-goal" not in capability.evidence_identities
    for label_id in (
        "MATCH_RESULT_1UP_HOME",
        "MATCH_RESULT_1UP_AWAY",
        "MATCH_RESULT_2UP_HOME",
        "MATCH_RESULT_2UP_AWAY",
    ):
        label = dict(row.labels)[label_id]
        assert "PREFERRED_EVENT:et-goal" not in label.evidence_identities
