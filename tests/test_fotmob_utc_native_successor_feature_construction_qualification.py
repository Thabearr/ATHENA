import json

import pytest

import domain.fotmob_utc_native_successor_feature_construction_qualification as q


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _row(
    fixture_id: str,
    kickoff_utc: str,
    home: str,
    away: str,
    home_goals: int,
    away_goals: int,
    evidence_sha256: str = SHA_A,
) -> dict:
    return {
        "source_namespace": q.SOURCE_NAMESPACE,
        "fixture_identifier": fixture_id,
        "source_local_kickoff": "2099-01-01T00:00:00",
        "kickoff_utc": kickoff_utc,
        "home_team_identifier": home,
        "away_team_identifier": away,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "observed_at": "2099-01-02T00:00:00Z",
        "evidence_sha256": evidence_sha256,
        "evidence_reference": f"synthetic:{fixture_id}",
    }


def _records(raw: bytes) -> list[dict]:
    return [json.loads(line) for line in raw.splitlines()]


def test_exact_pr134_protocol_and_pr119_executor_blobs_revalidate() -> None:
    q._verify_upstream()


def test_first_fixture_uses_explicit_missing_and_initial_state_semantics() -> None:
    raw, summary = q.construct_utc_native_feature_projection(
        [_row("1", "2026-01-01T12:00:00Z", "A", "B", 1, 0)]
    )
    record = _records(raw)[0]

    assert summary["record_count"] == 1
    assert record["kickoff_utc"] == "2026-01-01T12:00:00Z"
    assert record["home_form"] == {
        "status": "MISSING",
        "value": None,
    }
    assert record["away_form"] == {
        "status": "MISSING",
        "value": None,
    }
    assert record["home_elo"] == {
        "status": "CONSTRUCTED_FROM_FROZEN_INITIAL_STATE_ASSUMPTION",
        "value": 1500,
        "matches_before": 0,
        "rating_component": "OVERALL",
    }
    assert record["away_elo"]["value"] == 1500
    assert record["fatigue"] == {
        "status": "MISSING",
        "value": None,
        "home_rest_days": None,
        "away_rest_days": None,
        "rest_day_differential": None,
    }
    assert record["historical_live_data_freshness"] == {
        "status": "NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE",
        "value": None,
    }
    assert b"source_local_kickoff" not in raw


def test_summary_reports_protocol_availability_and_zero_conflicts() -> None:
    rows = [
        _row("1", "2026-01-01T12:00:00Z", "A", "B", 1, 0, SHA_A),
        _row("2", "2026-01-02T12:00:00Z", "A", "C", 0, 0, SHA_B),
    ]
    _, summary = q.construct_utc_native_feature_projection(rows)

    assert summary["record_count"] == 2
    assert summary["total_rows_seen"] == 2
    assert summary["feature_availability_counts"] == {
        "home_form": {
            "AVAILABLE": 1,
            "MISSING": 1,
            "BLOCKED": 0,
        },
        "away_form": {
            "AVAILABLE": 0,
            "MISSING": 2,
            "BLOCKED": 0,
        },
        "home_elo": {
            "AVAILABLE": 2,
            "MISSING": 0,
            "BLOCKED": 0,
        },
        "away_elo": {
            "AVAILABLE": 2,
            "MISSING": 0,
            "BLOCKED": 0,
        },
        "fatigue": {
            "AVAILABLE": 0,
            "MISSING": 2,
            "BLOCKED": 0,
        },
        "historical_live_data_freshness": {
            "AVAILABLE": 0,
            "MISSING": 0,
            "BLOCKED": 2,
        },
    }
    assert summary["feature_status_counts"][
        "historical_live_data_freshness:NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE"
    ] == 2
    assert summary["identity_or_lineage_conflict_count"] == 0
    assert summary["identity_or_lineage_conflicts"] == []


def test_strictly_prior_form_and_asymmetric_overall_elo_are_used() -> None:
    rows = [
        _row("1", "2026-01-01T12:00:00Z", "A", "B", 1, 0, SHA_A),
        _row("2", "2026-01-02T12:00:00Z", "A", "C", 0, 0, SHA_B),
    ]
    records = _records(q.construct_utc_native_feature_projection(rows)[0])
    second = records[1]

    assert second["home_form"] == {
        "status": "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY",
        "value": 0.95,
    }
    assert second["away_form"]["status"] == "MISSING"
    assert second["home_elo"] == {
        "status": "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY",
        "value": 1513,
        "matches_before": 1,
        "rating_component": "OVERALL",
    }
    assert second["away_elo"]["value"] == 1500
    assert second["fatigue"]["status"] == "MISSING"


def test_away_elo_update_uses_no_home_advantage_boost() -> None:
    rows = [
        _row("1", "2026-01-01T12:00:00Z", "A", "B", 1, 0, SHA_A),
        _row("2", "2026-01-02T12:00:00Z", "B", "C", 0, 0, SHA_B),
    ]
    second = _records(q.construct_utc_native_feature_projection(rows)[0])[1]

    assert second["home_team_identifier"] == "B"
    assert second["home_elo"] == {
        "status": "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY",
        "value": 1484,
        "matches_before": 1,
        "rating_component": "OVERALL",
    }


def test_fatigue_uses_integer_utc_days_and_home_minus_away_difference() -> None:
    rows = [
        _row("1", "2026-01-01T12:00:00Z", "A", "B", 1, 0, SHA_A),
        _row("2", "2026-01-02T12:00:00Z", "A", "C", 0, 0, SHA_B),
        _row("3", "2026-01-05T12:00:00Z", "A", "B", 0, 1, SHA_C),
    ]
    third = _records(q.construct_utc_native_feature_projection(rows)[0])[2]

    assert third["fatigue"] == {
        "status": "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY",
        "value": 0.10,
        "home_rest_days": 3,
        "away_rest_days": 4,
        "rest_day_differential": -1,
    }


def test_same_kickoff_groups_are_deterministic_and_batch_scoped() -> None:
    rows = [
        _row("20", "2026-01-01T12:00:00Z", "C", "D", 2, 0, SHA_B),
        _row("10", "2026-01-01T12:00:00Z", "A", "B", 1, 0, SHA_A),
        _row("30", "2026-01-02T12:00:00Z", "A", "C", 0, 0, SHA_C),
    ]
    raw_a, summary_a = q.construct_utc_native_feature_projection(rows)
    raw_b, summary_b = q.construct_utc_native_feature_projection(reversed(rows))

    assert raw_a == raw_b
    assert summary_a == summary_b
    assert summary_a["same_kickoff_group_count"] == 1
    records = _records(raw_a)
    assert [record["fixture_identifier"] for record in records] == ["10", "20", "30"]
    assert records[0]["home_elo"]["value"] == 1500
    assert records[1]["home_elo"]["value"] == 1500
    assert records[2]["home_form"]["value"] == 0.95
    assert records[2]["away_form"]["value"] == 0.95


def test_same_team_at_same_utc_kickoff_fails_closed() -> None:
    rows = [
        _row("1", "2026-01-01T12:00:00Z", "A", "B", 1, 0),
        _row("2", "2026-01-01T12:00:00Z", "A", "C", 0, 0),
    ]
    with pytest.raises(
        q.FotMobUTCNativeFeatureQualificationError,
        match="same source-scoped team appears twice at one UTC kickoff",
    ):
        q.construct_utc_native_feature_projection(rows)


def test_duplicate_fixture_identity_fails_closed() -> None:
    rows = [
        _row("1", "2026-01-01T12:00:00Z", "A", "B", 1, 0),
        _row("1", "2026-01-02T12:00:00Z", "C", "D", 0, 0),
    ]
    with pytest.raises(
        q.FotMobUTCNativeFeatureQualificationError,
        match="duplicate source fixture identity",
    ):
        q.construct_utc_native_feature_projection(rows)


def test_non_z_or_malformed_kickoff_is_rejected() -> None:
    row = _row("1", "2026-01-01T12:00:00Z", "A", "B", 1, 0)
    row["kickoff_utc"] = "2026-01-01T12:00:00"
    with pytest.raises(
        q.FotMobUTCNativeFeatureQualificationError,
        match="must be exact UTC Z text",
    ):
        q.construct_utc_native_feature_projection([row])


def test_projection_contains_no_source_local_or_numeric_freshness_surrogate() -> None:
    raw, summary = q.construct_utc_native_feature_projection(
        [_row("1", "2026-01-01T12:00:00Z", "A", "B", 1, 0)]
    )
    assert summary["unique_fixture_count"] == 1
    assert summary["unique_team_count"] == 2
    assert b"source_local" not in raw
    assert b"Europe/Oslo" not in raw
    record = _records(raw)[0]
    assert record["historical_live_data_freshness"]["value"] is None


def test_canonical_receipt_keeps_all_downstream_authority_false() -> None:
    receipt = {
        "schema_version": 1,
        "qualification_state": q.QUALIFICATION_STATE,
        "qualification_status": q.QUALIFICATION_STATUS,
        "next_required_boundary": q.NEXT_REQUIRED_BOUNDARY,
        "safety": {key: False for key in sorted(q.SAFETY_KEYS)},
    }
    first = q.canonical_qualification_receipt_bytes(receipt)
    second = q.canonical_qualification_receipt_bytes(dict(reversed(list(receipt.items()))))

    assert first == second
    assert json.loads(first)["safety"] == {
        key: False for key in sorted(q.SAFETY_KEYS)
    }
