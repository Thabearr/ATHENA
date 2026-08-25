from __future__ import annotations

import dataclasses
import json
import socket
import sqlite3
from pathlib import Path

import pytest

import domain.historical_training_coverage as htc
from domain.historical_training_coverage import (
    EvidenceCapabilityId,
    HistoricalTrainingCoverageError,
    ResolutionStatus,
    SettlementState,
    build_historical_training_coverage_row,
    calculate_canonical_market_semantics_sha256,
    calculate_label_generation_contract_sha256,
    calculate_market_label_registry_sha256,
    settle_asian_handicap,
    settle_total_goals,
    validate_contracts,
)
from scripts.build_historical_training_coverage import build_corpus
from scripts.build_historical_asof_feature_corpus import build_corpus as build_asof_corpus
from scripts.build_tactical_identity_corpus import build_tactical_corpus
from scripts.build_historical_warehouse import Warehouse


def _warehouse(tmp_path: Path, rows: list[dict]) -> tuple[Path, list[str]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "history.db"
    warehouse = Warehouse(path)
    warehouse.initialize()
    keys = []
    for index, row in enumerate(rows):
        payload = {
            "competition_key": "eng_premier", "competition_name": "Premier League",
            "scope": "club", "season": "2025-26", "match_date": f"2025-01-{index + 1:02d}",
            "home_team": "Home", "away_team": "Away", **row,
        }
        keys.append(warehouse.upsert_match(payload, source_key="football_data_uk",
                                           source_match_id=f"m{index}"))
    warehouse.close()
    return path, keys


def _labels(row) -> dict:
    return dict(row.labels)


def _capabilities(row) -> dict:
    return dict(row.capabilities)


def _add_events(path: Path, key: str, events: list[dict], *, source="statsbomb_open") -> None:
    connection = sqlite3.connect(path)
    connection.execute("INSERT OR IGNORE INTO warehouse_match_sources(match_key,source_key,source_match_id,has_ft,has_events) VALUES(?,?,?,1,1)",
                       (key, source, "events"))
    for index, event in enumerate(events):
        values = {"event_key": f"{key}:{source}:{index}", "match_key": key, "source_key": source,
                  "event_type": "goal", "team": "Home", "minute": index + 1,
                  "stoppage_minute": 0, "second": 0, "period": "1",
                  "is_penalty": 0, "is_own_goal": 0, **event}
        details_json = values.pop("details_json", "{}")
        values["details_json"] = details_json
        connection.execute("""INSERT INTO warehouse_events(
            event_key,match_key,source_key,event_type,team,minute,stoppage_minute,second,
            period,is_penalty,is_own_goal,details_json) VALUES(
            :event_key,:match_key,:source_key,:event_type,:team,:minute,:stoppage_minute,:second,
            :period,:is_penalty,:is_own_goal,:details_json)""", values)
    connection.commit(); connection.close()


def test_independent_registry_market_and_generation_pins_fail_closed():
    registry, market, generation = validate_contracts()
    assert registry == "3eff35745371543bf6ff20c6c7e8550835382c04eba6583b8dbded932753e87b"
    assert market == "b6a1de9415e27d9ed0e7394012435a60ca733187d41c951fd53d4a035ae84f11"
    assert generation == "cf6434c6ad1a16e4ff8b6ca05a3a2c4d3b4d3d2c2fce60dd293640b40219b7ab"
    changed = list(htc.MARKET_LABEL_REGISTRY)
    changed[0] = dataclasses.replace(changed[0], derivation="semantic drift")
    assert calculate_market_label_registry_sha256(changed, 1) != registry
    with pytest.raises(HistoricalTrainingCoverageError, match="registry"):
        validate_contracts(registry_definitions=changed)
    assert calculate_label_generation_contract_sha256(registry_sha256=registry,
        market_sha256="0" * 64) != generation
    with pytest.raises(HistoricalTrainingCoverageError, match="unreviewed"):
        validate_contracts(registry_version=999)
    with pytest.raises(HistoricalTrainingCoverageError, match="unreviewed"):
        validate_contracts(generation_version=999)
    altered_markets = dict(htc.MARKET_REGISTRY)
    altered_markets[htc.MarketId.MATCH_RESULT] = dataclasses.replace(
        altered_markets[htc.MarketId.MATCH_RESULT], settlement_semantics="drift")
    assert calculate_canonical_market_semantics_sha256(altered_markets) != market
    with pytest.raises(HistoricalTrainingCoverageError, match="market semantics"):
        validate_contracts(market_registry=altered_markets)


def test_score_labels_are_exact_and_dnb_draw_is_push(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [{"home_score_ft": 2, "away_score_ft": 2}])
    row = build_historical_training_coverage_row(db, keys[0]); labels = _labels(row)
    assert labels["MATCH_RESULT"].value == "DRAW"
    assert labels["BTTS"].value == "YES"
    assert labels["DOUBLE_CHANCE_HOME_OR_DRAW"].value is True
    assert labels["DOUBLE_CHANCE_DRAW_OR_AWAY"].value is True
    assert labels["DOUBLE_CHANCE_HOME_OR_AWAY"].value is False
    assert labels["HOME_WIN_TO_NIL"].value == "NO"
    assert labels["DRAW_OR_OVER_2_5"].value == "YES"
    assert labels["HOME_DRAW_NO_BET"].value is SettlementState.PUSH
    assert labels["AWAY_DRAW_NO_BET"].value is SettlementState.PUSH
    assert labels["TOTAL_GOALS"].value == 4
    assert labels["GOAL_MARGIN"].value == 0
    assert all(definition.label_id not in {"TOTAL_OVER_2_5", "AH_HOME_MINUS_1"}
               for definition in htc.MARKET_LABEL_REGISTRY)


@pytest.mark.parametrize(("kernel", "args", "expected"), [
    (settle_asian_handicap, (0, "HOME", 0), SettlementState.PUSH),
    (settle_asian_handicap, (0, "HOME", .25), SettlementState.HALF_WIN),
    (settle_asian_handicap, (0, "HOME", -.25), SettlementState.HALF_LOSS),
    (settle_total_goals, (2, "OVER", 2), SettlementState.PUSH),
    (settle_total_goals, (2, "OVER", 2.25), SettlementState.HALF_LOSS),
    (settle_total_goals, (3, "UNDER", 2.75), SettlementState.HALF_LOSS),
])
def test_explicit_line_settlement_kernels(kernel, args, expected):
    assert kernel(*args) is expected


def test_missing_and_conflicted_ft_are_label_local(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        {"home_score_ft": None, "away_score_ft": None},
        {"home_score_ft": 1, "away_score_ft": 0, "referee": "Ref"},
    ])
    missing = build_historical_training_coverage_row(db, keys[0])
    assert _labels(missing)["MATCH_RESULT"].status is ResolutionStatus.MISSING
    connection = sqlite3.connect(db)
    connection.execute("INSERT INTO warehouse_conflicts(match_key,field_name,incoming_source,incoming_value) VALUES(?,?,?,?)",
                       (keys[1], "home_score_ft", "statsbomb_open", "2"))
    connection.commit(); connection.close()
    blocked = build_historical_training_coverage_row(db, keys[1])
    assert _labels(blocked)["MATCH_RESULT"].status is ResolutionStatus.BLOCKED
    connection = sqlite3.connect(db)
    connection.execute("UPDATE warehouse_conflicts SET resolved=1")
    connection.execute("INSERT INTO warehouse_conflicts(match_key,field_name,incoming_source,incoming_value) VALUES(?,?,?,?)",
                       (keys[1], "referee", "fjelstul_worldcup", "Other"))
    connection.commit(); connection.close()
    available = build_historical_training_coverage_row(db, keys[1])
    assert _labels(available)["MATCH_RESULT"].status is ResolutionStatus.AVAILABLE


def test_half_and_win_either_half_exact_or_missing_or_blocked(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        {"home_score_ft": 2, "away_score_ft": 1, "home_score_ht": 0, "away_score_ht": 1},
        {"home_score_ft": 1, "away_score_ft": 0},
        {"home_score_ft": 1, "away_score_ft": 0, "home_score_ht": 2, "away_score_ht": 0},
    ])
    exact = _labels(build_historical_training_coverage_row(db, keys[0]))
    assert exact["SECOND_HALF_HOME_GOALS"].value == 2
    assert exact["HOME_WIN_EITHER_HALF"].value == "YES"
    assert exact["AWAY_WIN_EITHER_HALF"].value == "YES"
    assert exact["BOTH_TEAMS_WON_A_HALF"].value is True
    assert _labels(build_historical_training_coverage_row(db, keys[1]))["HOME_WIN_EITHER_HALF"].status is ResolutionStatus.MISSING
    assert _labels(build_historical_training_coverage_row(db, keys[2]))["HOME_WIN_EITHER_HALF"].status is ResolutionStatus.BLOCKED


def test_complete_preferred_path_and_overlapping_early_payout(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [{"home_score_ft": 2, "away_score_ft": 2,
                                      "home_score_et": 3, "away_score_et": 2,
                                      "home_score_pen": 5, "away_score_pen": 4}])
    _add_events(db, keys[0], [
        {"team": "Home", "minute": 10}, {"team": "Home", "minute": 20},
        {"team": "Away", "minute": 30}, {"team": "Away", "minute": 40},
        {"team": "Home", "minute": 100, "period": "3"},
    ])
    labels = _labels(build_historical_training_coverage_row(db, keys[0]))
    assert labels["MATCH_RESULT_1UP_HOME"].value is True
    assert labels["MATCH_RESULT_1UP_AWAY"].value is False
    assert labels["MATCH_RESULT_1UP_DRAW"].value is True
    assert labels["MATCH_RESULT_2UP_HOME"].value is True
    assert labels["MATCH_RESULT_2UP_DRAW"].value is True
    assert labels["MATCH_RESULT"].value == "DRAW"


def test_extra_period_aggregate_capability_is_blocked_but_score_is_usable(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        {"home_score_ft": 1, "away_score_ft": 1, "home_score_et": 1, "away_score_et": 0,
         "home_xg": 2.0, "away_xg": 1.0, "home_shots": 10, "away_shots": 8},
        {"home_score_ft": 1, "away_score_ft": 0,
         "home_xg": 1.2, "away_xg": .4, "home_shots": 7, "away_shots": 5},
    ])
    extra = build_historical_training_coverage_row(db, keys[0])
    normal = build_historical_training_coverage_row(db, keys[1])
    assert _labels(extra)["MATCH_RESULT"].status is ResolutionStatus.AVAILABLE
    assert _capabilities(extra)["XG_PAIR"].status is ResolutionStatus.BLOCKED
    assert _capabilities(extra)["SHOTS_PAIR"].status is ResolutionStatus.BLOCKED
    assert _capabilities(normal)["XG_PAIR"].status is ResolutionStatus.AVAILABLE


def test_path_missing_mismatch_team_and_same_timestamp_block(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        {"home_score_ft": 1, "away_score_ft": 0},
        {"home_score_ft": 1, "away_score_ft": 1},
        {"home_score_ft": 1, "away_score_ft": 0},
    ])
    assert _labels(build_historical_training_coverage_row(db, keys[0]))["MATCH_RESULT_1UP_HOME"].status is ResolutionStatus.MISSING
    _add_events(db, keys[0], [])
    assert _labels(build_historical_training_coverage_row(db, keys[0]))["MATCH_RESULT_1UP_HOME"].status is ResolutionStatus.BLOCKED
    _add_events(db, keys[1], [{"team": "Home", "minute": 10}, {"team": "Unknown", "minute": 20}])
    assert _labels(build_historical_training_coverage_row(db, keys[1]))["MATCH_RESULT_1UP_HOME"].status is ResolutionStatus.BLOCKED
    _add_events(db, keys[2], [{"team": "Home", "minute": 10}, {"team": "Away", "minute": 10}])
    connection = sqlite3.connect(db); connection.execute(
        "UPDATE warehouse_matches SET away_score_ft=1 WHERE match_key=?", (keys[2],)); connection.commit(); connection.close()
    tied = _labels(build_historical_training_coverage_row(db, keys[2]))
    assert tied["MATCH_RESULT_1UP_HOME"].status is ResolutionStatus.BLOCKED
    assert tied["MATCH_RESULT_1UP_DRAW"].value is True


def test_preferred_events_prevent_raw_duplicate_counting(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [{"home_score_ft": 1, "away_score_ft": 0}])
    _add_events(db, keys[0], [{"team": "Home", "minute": 10}], source="statsbomb_open")
    _add_events(db, keys[0], [{"team": "Home", "minute": 10}], source="fjelstul_worldcup")
    row = build_historical_training_coverage_row(db, keys[0])
    assert _labels(row)["MATCH_RESULT_1UP_HOME"].value is True


def test_richness_capabilities_do_not_overclaim_prematch_or_path(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [{"home_score_ft": 1, "away_score_ft": 0,
        "home_score_ht": 0, "away_score_ht": 0, "referee": "Ref",
        "home_coach": "HC", "away_coach": "AC", "data_quality": "RICH"}])
    row = build_historical_training_coverage_row(db, keys[0]); caps = _capabilities(row)
    assert caps[EvidenceCapabilityId.XG_PAIR.value].status is ResolutionStatus.MISSING
    assert caps[EvidenceCapabilityId.COMPLETE_REGULATION_GOAL_PATH.value].status is ResolutionStatus.MISSING
    assert "PREMATCH_LINEUP" not in row.canonical_bytes.decode()
    assert "CURRENT_MANAGER" not in row.canonical_bytes.decode()
    assert all(value is False for _, value in row.authority_flags)


def test_builder_only_source_binding_and_determinism(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [{"home_score_ft": 1, "away_score_ft": 0}])
    first = build_historical_training_coverage_row(db, keys[0])
    second = build_historical_training_coverage_row(db, keys[0])
    assert first.canonical_bytes == second.canonical_bytes
    assert first.canonical_sha256 == second.canonical_sha256
    with pytest.raises(HistoricalTrainingCoverageError, match="source-builder"):
        htc.HistoricalTrainingCoverageRow()
    with pytest.raises(HistoricalTrainingCoverageError, match="source-builder"):
        dataclasses.replace(first, match_key="forged")


def test_direct_and_bulk_payloads_match_and_source_remains_read_only(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [{"home_score_ft": 1, "away_score_ft": 0,
                                     "home_score_ht": 1, "away_score_ht": 0}])
    before = db.read_bytes(); direct = build_historical_training_coverage_row(db, keys[0])
    output = tmp_path / "labels.db"
    assert build_corpus(db, output) == 1
    connection = sqlite3.connect(output)
    payload, sha = connection.execute("SELECT payload_json,canonical_sha256 FROM match_evidence_coverage").fetchone()
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    connection.close()
    assert payload.encode() == direct.canonical_bytes and sha == direct.canonical_sha256
    assert {"corpus_meta", "match_evidence_coverage", "market_label_resolutions", "coverage_summary"} <= tables
    assert db.read_bytes() == before


def test_output_collision_and_no_network(tmp_path: Path, monkeypatch):
    db, _ = _warehouse(tmp_path, [{"home_score_ft": 0, "away_score_ft": 0}])
    before = db.read_bytes()
    for output in (db, Path(str(db) + "-wal"), Path(str(db) + "-journal"), Path(str(db) + "-shm")):
        with pytest.raises(HistoricalTrainingCoverageError, match="collides"):
            build_corpus(db, output)
        assert db.read_bytes() == before
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("network")))
    assert build_corpus(db, tmp_path / "offline.db") == 1


def test_modified_source_bytes_change_ancestry(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [{"home_score_ft": 1, "away_score_ft": 0}])
    first = build_historical_training_coverage_row(db, keys[0])
    connection = sqlite3.connect(db)
    connection.execute("INSERT INTO warehouse_meta VALUES('coverage_test','changed')")
    connection.commit(); connection.close()
    second = build_historical_training_coverage_row(db, keys[0])
    assert first.source_warehouse_sha256 != second.source_warehouse_sha256
    assert first.canonical_sha256 != second.canonical_sha256


def test_capability_vector_has_every_required_dimension():
    assert {item.value for item in EvidenceCapabilityId} == {
        "REGULATION_FT", "HALF_TIME_SCORE", "PREFERRED_EVENT_EVIDENCE",
        "COMPLETE_REGULATION_GOAL_PATH", "XG_PAIR", "SHOTS_PAIR",
        "SHOTS_ON_TARGET_PAIR", "POSSESSION_PAIR", "CARD_TOTALS",
        "HOME_LINEUP_EVIDENCE", "AWAY_LINEUP_EVIDENCE", "HOME_COACH_EVIDENCE",
        "AWAY_COACH_EVIDENCE", "REFEREE_EVIDENCE", "ADVANCED_STATS_SOURCE_COVERAGE",
        "SOURCE_PROVENANCE", "CONFLICT_STATE", "HISTORICAL_ASOF_TARGET_JOIN",
        "TACTICAL_IDENTITY_TARGET_JOIN",
    }


def test_optional_phase2_phase3_exact_join_and_wrong_warehouse_rejected(tmp_path: Path):
    db, keys = _warehouse(tmp_path / "a", [{"home_score_ft": 1, "away_score_ft": 0}])
    asof = tmp_path / "asof.db"
    tactical = tmp_path / "tactical.db"
    assert build_asof_corpus(db, asof) == 1
    assert build_tactical_corpus(asof, db, tactical) == 1
    output = tmp_path / "joined.db"
    assert build_corpus(db, output, asof_corpus=asof, tactical_corpus=tactical) == 1
    connection = sqlite3.connect(output)
    payload = json.loads(connection.execute("SELECT payload_json FROM match_evidence_coverage").fetchone()[0])
    connection.close()
    assert payload["capabilities"]["HISTORICAL_ASOF_TARGET_JOIN"]["status"] == "AVAILABLE"
    assert payload["capabilities"]["TACTICAL_IDENTITY_TARGET_JOIN"]["status"] == "AVAILABLE"
    other, _ = _warehouse(tmp_path / "b", [{"home_score_ft": 1, "away_score_ft": 0}])
    connection = sqlite3.connect(other)
    connection.execute("INSERT INTO warehouse_meta VALUES('different_bytes','yes')")
    connection.commit(); connection.close()
    with pytest.raises(HistoricalTrainingCoverageError, match="ancestry"):
        build_corpus(other, tmp_path / "wrong.db", asof_corpus=asof)


def test_summary_preserves_quality_denominators_and_all_output_tables(tmp_path: Path):
    db, _ = _warehouse(tmp_path, [
        {"home_score_ft": None, "away_score_ft": None},
        {"home_score_ft": 1, "away_score_ft": 0},
        {"home_score_ft": 1, "away_score_ft": 1, "home_score_ht": 0, "away_score_ht": 0},
        {"home_score_ft": 2, "away_score_ft": 0, "home_score_ht": 1, "away_score_ht": 0},
    ])
    connection = sqlite3.connect(db)
    qualities = ("PARTIAL", "BASIC", "STANDARD", "RICH")
    keys = [row[0] for row in connection.execute("SELECT match_key FROM warehouse_matches ORDER BY match_date")]
    for key, quality in zip(keys, qualities):
        connection.execute("UPDATE warehouse_matches SET data_quality=? WHERE match_key=?", (quality, key))
    connection.commit(); connection.close()
    output = tmp_path / "summary.db"
    assert build_corpus(db, output) == 4
    connection = sqlite3.connect(output)
    assert dict(connection.execute("SELECT data_quality,count(*) FROM match_evidence_coverage GROUP BY data_quality")) == {
        "PARTIAL": 1, "BASIC": 1, "STANDARD": 1, "RICH": 1}
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"corpus_meta", "match_evidence_coverage", "evidence_capability_resolutions",
            "market_label_resolutions", "coverage_summary"} <= tables
    assert connection.execute("SELECT count(*) FROM coverage_summary WHERE group_type='DATA_QUALITY'").fetchone()[0] > 0
    assert connection.execute("SELECT count(*) FROM coverage_summary WHERE group_type='DATA_QUALITY' AND item_type='MARKET_FAMILY'").fetchone()[0] > 0
    rates = connection.execute("SELECT DISTINCT coverage_rate,blocked_rate FROM coverage_summary WHERE group_type='CORPUS' AND item_type='LABEL' AND item_id='MATCH_RESULT'").fetchall()
    assert len(rates) == 1
    connection.close()


def test_no_market_probability_price_or_authority_fields():
    payload = json.dumps([item.semantic_dict() for item in htc.MARKET_LABEL_REGISTRY])
    assert "probability" not in payload.lower()
    assert "price" not in payload.lower()
    assert all(not value for value in htc.AUTHORITY_FLAGS.values())
    from domain.sportybet_early_payout_settlement import (
        reviewed_sportybet_early_payout_settlement_receipt,
        sha256_sportybet_early_payout_settlement_receipt,
    )
    assert sha256_sportybet_early_payout_settlement_receipt(
        reviewed_sportybet_early_payout_settlement_receipt()
    ) == htc.EARLY_PAYOUT_SETTLEMENT_RECEIPT_SHA256


def test_present_malformed_scores_are_blocked_not_missing(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [{"home_score_ft": 1, "away_score_ft": 0,
                                      "home_score_ht": 0, "away_score_ht": 0}])
    connection = sqlite3.connect(db)
    connection.execute("UPDATE warehouse_matches SET home_score_ft=-1 WHERE match_key=?", (keys[0],))
    connection.commit(); connection.close()
    row = build_historical_training_coverage_row(db, keys[0])
    assert _capabilities(row)["REGULATION_FT"].status is ResolutionStatus.BLOCKED
    assert _labels(row)["MATCH_RESULT"].status is ResolutionStatus.BLOCKED

    connection = sqlite3.connect(db)
    connection.execute("UPDATE warehouse_matches SET home_score_ft=1,home_score_ht=-1 WHERE match_key=?", (keys[0],))
    connection.commit(); connection.close()
    row = build_historical_training_coverage_row(db, keys[0])
    assert _capabilities(row)["HALF_TIME_SCORE"].status is ResolutionStatus.BLOCKED
    assert _labels(row)["HOME_WIN_EITHER_HALF"].status is ResolutionStatus.BLOCKED


def test_statsbomb_own_goal_for_and_against_have_distinct_attribution(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        {"home_score_ft": 1, "away_score_ft": 0},
        {"home_score_ft": 0, "away_score_ft": 1},
    ])
    _add_events(db, keys[0], [{
        "team": "Home", "minute": 10, "second": 5, "is_own_goal": 1,
        "details_json": json.dumps({"type": "Own Goal For"}),
    }])
    _add_events(db, keys[1], [{
        "team": "Home", "minute": 10, "second": 5, "is_own_goal": 1,
        "details_json": json.dumps({"type": "Own Goal Against"}),
    }])
    own_for = _labels(build_historical_training_coverage_row(db, keys[0]))
    own_against = _labels(build_historical_training_coverage_row(db, keys[1]))
    assert own_for["MATCH_RESULT_1UP_HOME"].value is True
    assert own_against["MATCH_RESULT_1UP_AWAY"].value is True


def test_statsbomb_unproved_own_goal_semantics_block_path(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [{"home_score_ft": 0, "away_score_ft": 1}])
    _add_events(db, keys[0], [{
        "team": "Home", "minute": 10, "second": 5, "is_own_goal": 1,
        "details_json": "{}",
    }])
    row = build_historical_training_coverage_row(db, keys[0])
    assert _labels(row)["MATCH_RESULT_1UP_AWAY"].status is ResolutionStatus.BLOCKED


def test_normal_import_cannot_reach_injectable_coverage_assembler():
    import domain
    import importlib

    direct = importlib.import_module("domain._historical_training_coverage_impl")
    assert direct is htc
    assert domain._historical_training_coverage_impl is htc
    assert not hasattr(htc, "_assemble_coverage_row")
    assert not hasattr(htc, "preferred_events_for_match")
    assert not hasattr(htc, "evidence_counts_for_match")


def test_output_companion_blocks_replace(tmp_path: Path):
    db, _ = _warehouse(tmp_path, [{"home_score_ft": 0, "away_score_ft": 0}])
    output = tmp_path / "labels.db"
    output.write_bytes(b"old")
    companion = Path(str(output) + "-wal")
    companion.write_bytes(b"stale")
    with pytest.raises(HistoricalTrainingCoverageError, match="companion"):
        build_corpus(db, output, replace=True)
    assert output.read_bytes() == b"old"
    assert companion.read_bytes() == b"stale"


def test_optional_corpus_metadata_contract_drift_fails_closed(tmp_path: Path):
    db, _ = _warehouse(tmp_path, [{"home_score_ft": 1, "away_score_ft": 0}])
    asof = tmp_path / "asof.db"
    assert build_asof_corpus(db, asof) == 1
    connection = sqlite3.connect(asof)
    connection.execute("UPDATE corpus_meta SET value=? WHERE key='feature_registry_sha256'",
                       (json.dumps("0" * 64),))
    connection.commit(); connection.close()
    with pytest.raises(HistoricalTrainingCoverageError, match="contract"):
        build_corpus(db, tmp_path / "joined.db", asof_corpus=asof)


def test_tactical_corpus_must_bind_exact_supplied_asof_bytes(tmp_path: Path):
    db, _ = _warehouse(tmp_path, [{"home_score_ft": 1, "away_score_ft": 0}])
    asof = tmp_path / "asof.db"
    tactical = tmp_path / "tactical.db"
    assert build_asof_corpus(db, asof) == 1
    assert build_tactical_corpus(asof, db, tactical) == 1
    copied = tmp_path / "asof-copy.db"
    copied.write_bytes(asof.read_bytes())
    assert build_corpus(db, tmp_path / "ok.db", asof_corpus=copied,
                        tactical_corpus=tactical) == 1
    connection = sqlite3.connect(copied)
    connection.execute("INSERT INTO corpus_meta(key,value) VALUES('tamper', '1')")
    connection.commit(); connection.close()
    with pytest.raises(HistoricalTrainingCoverageError):
        build_corpus(db, tmp_path / "bad.db", asof_corpus=copied,
                     tactical_corpus=tactical)
