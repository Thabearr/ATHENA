from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from pathlib import Path

import pytest

import domain.fotmob_data_matches_capture as capture_contract
import domain.fotmob_data_matches_eliminated_team_id_value_domain_extension as pr89
import domain.fotmob_fresh_holdout_capture_qualification_adapter as adapter
import domain.fotmob_fresh_holdout_ordinary_ft_settlement_schema_adapter as settlement_adapter
import scripts.run_fotmob_utc_native_xg_fresh_holdout_tick as tick_cli


UTC = dt.timezone.utc
REQUEST_DATE = "20260910"
KICKOFF = "2026-09-10T18:00:00.000Z"
KICKOFF_MS = 1_789_063_200_000
OBSERVED = dt.datetime(2026, 9, 10, 1, 46, 15, tzinfo=UTC)
PREVIOUS_KICKOFF = "2026-09-09T23:30:00.000Z"
PREVIOUS_KICKOFF_MS = 1_788_996_600_000


class _Absent:
    pass


ABSENT = _Absent()


def _raw(value: dict) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _manifest(raw: bytes):
    response = capture_contract.CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=len(raw),
        body=raw,
        observed_at=OBSERVED,
        network_acquisition_performed=True,
    )
    return capture_contract.build_data_matches_capture_manifest(
        response,
        request_date=REQUEST_DATE,
        timezone="UTC",
        ccode3="NGA",
    )


def _payload(*, home_shortname="H", away_shortname="A") -> dict:
    home = {
        "id": 11,
        "longName": "Home Long",
        "name": "Home",
        "penScore": 0,
        "redCards": 1,
        "score": 2,
    }
    away = {
        "id": 12,
        "longName": "Away Long",
        "name": "Away",
        "penScore": 0,
        "redCards": 0,
        "score": 1,
    }
    if home_shortname is not ABSENT:
        home["shortName"] = home_shortname
    if away_shortname is not ABSENT:
        away["shortName"] = away_shortname
    return {
        "date": REQUEST_DATE,
        "leagues": [
            {
                "ccode": "ENG",
                "id": 42,
                "internalRank": 1,
                "matches": [
                    {
                        "away": away,
                        "eliminatedTeamId": 11,
                        "home": home,
                        "id": 1001,
                        "leagueId": 42,
                        "status": {
                            "awarded": False,
                            "cancelled": False,
                            "finished": True,
                            "halfs": {
                                "firstHalfStarted": "10.09.2026 18:00:00",
                                "secondHalfStarted": "10.09.2026 19:00:00",
                                "firstExtraHalfStarted": "10.09.2026 19:50:00",
                                "secondExtraHalfStarted": "10.09.2026 20:05:00",
                            },
                            "liveTime": {
                                "addedTime": 0,
                                "basePeriod": 90,
                                "long": "",
                                "longKey": "",
                                "maxTime": 90,
                                "short": "",
                                "shortKey": "",
                            },
                            "numberOfAwayRedCards": 0,
                            "numberOfHomeRedCards": 1,
                            "ongoing": False,
                            "periodLength": 45,
                            "reason": {
                                "long": "Full-Time",
                                "longKey": "finished",
                                "short": "FT",
                                "shortKey": "fulltime_short",
                            },
                            "scoreStr": "2 - 1",
                            "started": True,
                            "utcTime": KICKOFF,
                        },
                        "statusId": 6,
                        "time": "10.09.2026 18:00",
                        "timeTS": KICKOFF_MS,
                        "tournamentStage": "",
                    }
                ],
                "name": "Example competition",
                "primaryId": 42,
                "simpleLeague": False,
            }
        ],
    }


def _without_extra_halfs(payload: dict) -> dict:
    value = copy.deepcopy(payload)
    halfs = value["leagues"][0]["matches"][0]["status"]["halfs"]
    halfs.pop("firstExtraHalfStarted", None)
    halfs.pop("secondExtraHalfStarted", None)
    return value


def _with_previous_day_spillover(payload: dict) -> dict:
    value = copy.deepcopy(payload)
    spillover = copy.deepcopy(value["leagues"][0]["matches"][0])
    spillover["id"] = 1002
    spillover["status"]["utcTime"] = PREVIOUS_KICKOFF
    spillover["timeTS"] = PREVIOUS_KICKOFF_MS
    spillover["time"] = "10.09.2026 01:30"
    spillover["status"]["finished"] = False
    spillover["status"]["ongoing"] = True
    spillover["statusId"] = 2
    value["leagues"][0]["matches"].append(spillover)
    return value


def _identity(rows) -> list[tuple]:
    return [
        (
            row.fixture_id,
            row.provider_primary_id,
            row.wrapper_id,
            row.home_team_id,
            row.away_team_id,
            row.kickoff_utc,
            row.capture_observed_at,
        )
        for row in rows
    ]


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def test_frozen_structural_chain_rejects_unprojected_team_shortname() -> None:
    payload = _without_extra_halfs(_payload())
    raw = _raw(payload)
    manifest = _manifest(raw)

    with pytest.raises(pr89.FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError):
        pr89.assess_fotmob_data_matches_eliminated_team_id_value_domain(raw, manifest)

    rows = adapter.qualify_capture_fixtures(raw, manifest)
    assert [row.fixture_id for row in rows] == [1001]


@pytest.mark.parametrize(
    ("home_shortname", "away_shortname"),
    [
        ("H", ABSENT),
        (ABSENT, "A"),
        ("H", "A"),
        (ABSENT, ABSENT),
        ("", ""),
    ],
)
def test_team_shortname_is_optional_exact_opaque_string_only(
    home_shortname,
    away_shortname,
) -> None:
    raw = _raw(
        _payload(
            home_shortname=home_shortname,
            away_shortname=away_shortname,
        )
    )
    rows = adapter.qualify_capture_fixtures(raw, _manifest(raw))
    assert [row.fixture_id for row in rows] == [1001]


@pytest.mark.parametrize("bad", [None, True, 1, 1.25, [], {}])
@pytest.mark.parametrize("side", ["home", "away"])
def test_team_shortname_rejects_null_coercion_and_non_string_types(
    side: str,
    bad,
) -> None:
    payload = _payload()
    payload["leagues"][0]["matches"][0][side]["shortName"] = bad
    raw = _raw(payload)
    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match=rf"{side}\.shortName must be an exact string",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw))


def test_projection_is_deep_copy_and_removes_only_approved_team_shortname() -> None:
    payload = _payload()
    payload["leagues"][0]["matches"][0]["home"]["futureSibling"] = "still-present"

    projected = adapter._remove_reviewed_team_short_names(payload)
    original_match = payload["leagues"][0]["matches"][0]
    projected_match = projected["leagues"][0]["matches"][0]

    assert original_match["home"]["shortName"] == "H"
    assert original_match["away"]["shortName"] == "A"
    assert "shortName" not in projected_match["home"]
    assert "shortName" not in projected_match["away"]
    assert projected_match["home"]["futureSibling"] == "still-present"

    raw = _raw(payload)
    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="structural chain failed",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw))


@pytest.mark.parametrize("location", ["match", "league", "status", "halfs"])
def test_shortname_outside_home_away_team_objects_remains_fail_closed(
    location: str,
) -> None:
    payload = _payload()
    league = payload["leagues"][0]
    match = league["matches"][0]
    if location == "match":
        match["shortName"] = "opaque"
    elif location == "league":
        league["shortName"] = "opaque"
    elif location == "status":
        match["status"]["shortName"] = "opaque"
    else:
        match["status"]["halfs"]["shortName"] = "opaque"

    raw = _raw(payload)
    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="structural chain failed",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw))


def test_shortname_text_has_no_provider_identity_authority_and_source_lineage_stays_original() -> None:
    raw_a = _raw(_payload(home_shortname="HOME-A", away_shortname="AWAY-A"))
    raw_b = _raw(
        _payload(
            home_shortname="completely different",
            away_shortname="values",
        )
    )
    manifest_a = _manifest(raw_a)
    manifest_b = _manifest(raw_b)

    rows_a = adapter.qualify_capture_fixtures(raw_a, manifest_a)
    rows_b = adapter.qualify_capture_fixtures(raw_b, manifest_b)

    assert _identity(rows_a) == _identity(rows_b)
    assert manifest_a.raw_sha256 != manifest_b.raw_sha256
    assert rows_a[0].capture_raw_sha256 == manifest_a.raw_sha256
    assert rows_b[0].capture_raw_sha256 == manifest_b.raw_sha256
    assert rows_a[0].capture_manifest_sha256 == (
        capture_contract.sha256_data_matches_capture_manifest(manifest_a)
    )
    assert rows_b[0].capture_manifest_sha256 == (
        capture_contract.sha256_data_matches_capture_manifest(manifest_b)
    )


def test_shortname_composes_with_terminal_extra_half_and_previous_day_spillover_compatibility() -> None:
    raw = _raw(_with_previous_day_spillover(_payload()))
    rows = adapter.qualify_capture_fixtures(raw, _manifest(raw))
    assert [row.fixture_id for row in rows] == [1001]


def test_settlement_structural_projection_composes_with_shortname_without_semantic_promotion() -> None:
    raw = _raw(_payload())
    assessment = settlement_adapter.assess_eliminated_team_id_value_domain_for_settlement(
        raw,
        _manifest(raw),
    )
    assert (
        assessment.status
        is pr89.EliminatedTeamIdValueDomainStatus.QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN
    )
    assert assessment.status_reason_semantics_qualified is False
    assert assessment.final_result_semantics_qualified is False


def test_receipt_binds_exact_sep10_failure_evidence_and_grants_no_authority() -> None:
    receipt = adapter.adapter_receipt()
    assert receipt["adapter_id"] == "FOTMOB_FRESH_HOLDOUT_REVIEWED_SCHEMA_ADAPTER_V3"
    assert receipt["reviewed_team_shortname_key"] == "shortName"
    assert receipt["reviewed_team_shortname_rule"] == (
        "OPTIONAL_MATCH_TEAM_SHORTNAME_EXACT_STRING_NULL_FORBIDDEN_OPAQUE_"
        "VALIDATION_PROJECTION_ONLY"
    )
    assert receipt["team_shortname_source_workflow_run_id"] == 34426288968
    assert receipt["team_shortname_source_actions_artifact_id"] == 10132954816
    assert receipt["team_shortname_source_actions_artifact_name"] == (
        "failure-20260910T013700Z-run-34426288968.tar.gz"
    )
    assert receipt["team_shortname_source_actions_artifact_sha256"] == (
        "ad44afa394d5fc9be03132af069acf018566cc8eebcee932d518f9fb15b4ab7e"
    )
    assert receipt["team_shortname_source_capture_lineages"] == [
        {
            "request_date": "20260909",
            "observed_at": "2026-09-10T01:46:14.724321Z",
            "manifest_sha256": "308898f47d5a6f8e292d247ff661c4b3e71ebb4b0349b13435a59b6ac91c6cf4",
            "raw_sha256": "6884f67152db749c9f69dc74119d6bed475971d3cb9d27ceb65d1e4ee5d69ccb",
        },
        {
            "request_date": "20260910",
            "observed_at": "2026-09-10T01:46:15.042980Z",
            "manifest_sha256": "0aa3be5dc0f8fe3c8922d40d3a2a277ce3df377bc4fc6fdd1c1b34c2f2af710a",
            "raw_sha256": "3492eab523b2a9e330f7fadb61b25ad21595242f86d6b1173fa2a3547fe2ca1f",
        },
        {
            "request_date": "20260911",
            "observed_at": "2026-09-10T01:46:15.396251Z",
            "manifest_sha256": "82149cd522c5146d9158382caa8edb03b8dac3a966d3df799cae3833292a0cf4",
            "raw_sha256": "1e2029c8e6878e6ec40b414d046ef3e817c69e4f64659363ce5b8de8e6d9a51a",
        },
    ]
    assert receipt["team_shortname_projection_is_validation_only"] is True
    assert receipt["team_shortname_has_no_identity_or_football_semantics"] is True
    assert receipt["compatibility_projection_is_not_source_evidence"] is True
    assert receipt["network_acquisition_performed"] is False
    assert all(value is False for value in receipt["safety"].values())


def test_active_blob_pin_cascade_is_exact_and_activation_runner_pin_is_unchanged() -> None:
    capture_blob = _git_blob_sha(Path(adapter.__file__))
    settlement_blob = _git_blob_sha(Path(settlement_adapter.__file__))

    assert settlement_adapter.LIVE_CAPTURE_ADAPTER_BLOB_SHA == capture_blob
    assert tick_cli.LIVE_CAPTURE_IDENTITY_ADAPTER_BLOB_SHA == capture_blob
    assert tick_cli.SETTLEMENT_SCHEMA_ADAPTER_BLOB_SHA == settlement_blob
    assert tick_cli.ACTIVATION_RUNNER_BLOB_SHA == (
        "901ab137d6601a3485eac30da7e6bad7eeefa397"
    )
