from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from domain import fotmob_data_matches_schema as schema_domain
from domain.fotmob_data_matches_capture import (
    DATASET_NAME as CAPTURE_DATASET_NAME,
    MAX_RESPONSE_BYTES,
    CapturedFotMobDataMatchesResponse,
    FotMobDataMatchesCaptureError,
    build_data_matches_capture_manifest,
    sha256_data_matches_capture_manifest,
)
from domain.fotmob_data_matches_schema import (
    DATASET_NAME,
    HALFS_KEYS,
    LEAGUE_ALLOWED_KEYS,
    LEAGUE_OPTIONAL_KEYS,
    LEAGUE_REQUIRED_KEYS,
    MATCH_KEYS,
    REASON_KEYS,
    SCHEMA_VERSION,
    STATUS_ALLOWED_KEYS,
    STATUS_OPTIONAL_KEYS,
    STATUS_REQUIRED_KEYS,
    TEAM_KEYS,
    FotMobDataMatchesSchemaError,
    StructuralCapability,
    assess_fotmob_data_matches_schema,
    canonical_data_matches_schema_assessment_bytes,
    data_matches_schema_assessment_to_dict,
    sha256_data_matches_schema_assessment,
)
from scripts import assess_fotmob_data_matches_schema as schema_script
from scripts.capture_fotmob_data_matches import write_data_matches_capture_directory


DATE = "20260815"
TIMEZONE = "UTC"
CCODE3 = "NGA"
OBSERVED = datetime.datetime(
    2026, 8, 9, 8, 58, 40, 355522, tzinfo=datetime.timezone.utc
)
KICKOFF = "2026-08-15T12:00:00.000Z"
KICKOFF_MS = 1786795200000
SAFETY_KEYS = {
    "network_acquisition_authorized",
    "raw_json_capture_authorized",
    "schema_assessment_authorized",
    "fixture_extraction_authorized",
    "fixture_candidate_generation_authorized",
    "source_qualified",
    "fixture_promotion_authorized",
    "intelligence_authorized",
    "model_feature_authorized",
    "probability_authorized",
    "pricing_authorized",
    "selection_authorized",
    "bet_authorized",
}


def team(identifier: int, name: str) -> dict[str, Any]:
    return {"id": identifier, "score": 0, "name": name, "longName": name}


def match(identifier: int = 1001) -> dict[str, Any]:
    return {
        "away": team(12, "Away"),
        "eliminatedTeamId": None,
        "home": team(11, "Home"),
        "id": identifier,
        "leagueId": 42,
        "status": {
            "utcTime": KICKOFF,
            "halfs": {"firstHalfStarted": ""},
            "periodLength": 45,
            "started": False,
            "cancelled": False,
            "finished": False,
        },
        "statusId": 1,
        "time": "15.08.2026 12:00",
        "timeTS": KICKOFF_MS,
        "tournamentStage": "",
    }


def league(matches: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "ccode": "ENG",
        "id": 42,
        "internalRank": 1,
        "matches": [match()] if matches is None else matches,
        "name": "Example competition",
        "primaryId": 42,
        "simpleLeague": False,
    }


def payload(leagues: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"leagues": [league()] if leagues is None else leagues, "date": DATE}


def raw_bytes(value: Any | None = None) -> bytes:
    return json.dumps(
        payload() if value is None else value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def source_manifest(raw: bytes, *, network: bool = False):
    response = CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=len(raw),
        body=raw,
        observed_at=OBSERVED,
        network_acquisition_performed=network,
    )
    return build_data_matches_capture_manifest(
        response,
        request_date=DATE,
        timezone=TIMEZONE,
        ccode3=CCODE3,
    )


def assess(value: Any | None = None):
    raw = raw_bytes(value)
    return assess_fotmob_data_matches_schema(raw, source_manifest(raw))


def test_exact_dataset_schema_enum_and_assessment_fields():
    result = assess()
    assert DATASET_NAME == "athena-fotmob-data-matches-schema-assessment-v1"
    assert SCHEMA_VERSION == 1 and type(result.schema_version) is int
    assert [item.value for item in StructuralCapability] == [
        "PRESENT_IN_CAPTURE",
        "ABSENT_IN_CAPTURE",
        "AMBIGUOUS",
    ]
    assert [field.name for field in dataclasses.fields(result)] == [
        "schema_version", "dataset_name", "source_capture_dataset_name",
        "source_capture_schema_version", "source_capture_manifest_sha256",
        "source_raw_sha256", "source_raw_size", "source_observed_at",
        "request_date", "timezone", "ccode3", "payload_date",
        "top_level_keys", "league_count", "match_count",
        "duplicate_match_id_count", "league_link_mismatch_count",
        "kickoff_timestamp_mismatch_count", "kickoff_request_date_mismatch_count",
        "league_key_union", "match_key_union", "match_key_intersection",
        "fixture_identity_candidate", "kickoff_candidate",
        "team_identity_candidate", "competition_identity_candidate",
        "status_candidate", "full_time_score_candidate",
        "half_time_score_candidate", "source_freshness_candidate", "safety",
    ]


@pytest.mark.parametrize("bad", [True, 1.0, "1", 0, 2])
def test_schema_requires_exact_integer_one(bad: Any):
    with pytest.raises(FotMobDataMatchesSchemaError):
        dataclasses.replace(assess(), schema_version=bad)


def test_assessment_and_safety_are_detached_immutable():
    result = assess()
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.match_count = 4  # type: ignore[misc]
    safety = dict(result.safety)
    copied = dataclasses.replace(result, safety=safety)
    safety["source_qualified"] = True
    assert copied.safety["source_qualified"] is False
    with pytest.raises(TypeError):
        copied.safety["source_qualified"] = True  # type: ignore[index]


@pytest.mark.parametrize("bad", [True, 0, 1, None, "false"])
def test_safety_values_must_be_exact_false(bad: Any):
    safety = dict(assess().safety)
    safety["source_qualified"] = bad
    with pytest.raises(FotMobDataMatchesSchemaError):
        dataclasses.replace(assess(), safety=safety)


def test_safety_key_set_is_exact():
    result = assess()
    assert set(result.safety) == SAFETY_KEYS
    assert all(type(value) is bool and value is False for value in result.safety.values())


def test_source_ancestry_is_exact_and_propagated():
    raw = raw_bytes()
    manifest = source_manifest(raw)
    result = assess_fotmob_data_matches_schema(raw, manifest)
    assert result.source_capture_dataset_name == CAPTURE_DATASET_NAME
    assert result.source_capture_schema_version == 1
    assert result.source_capture_manifest_sha256 == sha256_data_matches_capture_manifest(manifest)
    assert result.source_raw_sha256 == manifest.raw_sha256
    assert result.source_raw_size == len(raw)
    assert result.source_observed_at == manifest.observed_at
    assert (result.request_date, result.timezone, result.ccode3) == (DATE, TIMEZONE, CCODE3)


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("request_date", "20260230"),
        ("request_date", True),
        ("timezone", " UTC"),
        ("timezone", True),
        ("ccode3", "nga"),
        ("ccode3", True),
    ],
)
def test_assessment_request_identity_uses_pr38_validation(field: str, bad: Any):
    with pytest.raises(FotMobDataMatchesSchemaError, match="request identity"):
        dataclasses.replace(assess(), **{field: bad})


@pytest.mark.parametrize("bad", [None, object(), {}, b"manifest"])
def test_source_manifest_type_required(bad: Any):
    with pytest.raises(FotMobDataMatchesSchemaError, match="source_manifest"):
        assess_fotmob_data_matches_schema(raw_bytes(), bad)


def test_source_manifest_dataset_and_schema_are_anchored():
    raw = raw_bytes()
    manifest = source_manifest(raw)
    with pytest.raises(FotMobDataMatchesCaptureError):
        dataclasses.replace(manifest, dataset_name="other")
    with pytest.raises(FotMobDataMatchesCaptureError):
        dataclasses.replace(manifest, schema_version=2)


def test_raw_size_and_sha_mismatch_rejected():
    raw = raw_bytes()
    manifest = source_manifest(raw)
    with pytest.raises(FotMobDataMatchesSchemaError, match="size"):
        assess_fotmob_data_matches_schema(raw + b" ", manifest)
    changed = bytearray(raw)
    changed[-1] = 32
    with pytest.raises(FotMobDataMatchesSchemaError, match="SHA-256"):
        assess_fotmob_data_matches_schema(bytes(changed), manifest)


@pytest.mark.parametrize(
    "raw",
    [
        b"\xff",
        b"{",
        b'{"date":"20260815","date":"20260815","leagues":[]}',
        b'{"date":"20260815","leagues":[{"id":1,"id":1}]}',
        b'{"date":NaN,"leagues":[]}',
        b'{"date":Infinity,"leagues":[]}',
        b'{"date":-Infinity,"leagues":[]}',
        b"[]",
        b'"text"',
    ],
)
def test_strict_json_failures(raw: bytes):
    with pytest.raises(FotMobDataMatchesSchemaError):
        assess_fotmob_data_matches_schema(raw, source_manifest(raw))


def test_top_level_exact_contract_accepted():
    result = assess()
    assert result.top_level_keys == ("date", "leagues")
    assert result.payload_date == DATE


@pytest.mark.parametrize("mutation", ["missing-date", "missing-leagues", "extra", "date-type", "leagues-type", "date-mismatch"])
def test_top_level_drift_rejected(mutation: str):
    value = payload()
    if mutation == "missing-date": value.pop("date")
    elif mutation == "missing-leagues": value.pop("leagues")
    elif mutation == "extra": value["extra"] = None
    elif mutation == "date-type": value["date"] = 20260815
    elif mutation == "leagues-type": value["leagues"] = {}
    elif mutation == "date-mismatch": value["date"] = "20260816"
    with pytest.raises(FotMobDataMatchesSchemaError):
        assess(value)


def test_frozen_league_key_sets_are_exact():
    assert LEAGUE_REQUIRED_KEYS == {
        "ccode", "id", "internalRank", "matches", "name", "primaryId", "simpleLeague"
    }
    assert LEAGUE_OPTIONAL_KEYS == {
        "groupName", "isGroup", "localRank", "parentLeagueId", "parentLeagueName"
    }
    assert LEAGUE_ALLOWED_KEYS == LEAGUE_REQUIRED_KEYS | LEAGUE_OPTIONAL_KEYS


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("groupName", "Group A"),
        ("isGroup", True),
        ("localRank", 2),
        ("parentLeagueId", 7),
        ("parentLeagueName", "Parent"),
    ],
)
def test_each_frozen_optional_league_field_is_accepted(key: str, value: Any):
    item = league()
    item[key] = value
    result = assess(payload([item]))
    assert key in result.league_key_union


@pytest.mark.parametrize("key", sorted(LEAGUE_REQUIRED_KEYS))
def test_each_required_league_key_is_required(key: str):
    item = league()
    item.pop(key)
    with pytest.raises(FotMobDataMatchesSchemaError, match="required"):
        assess(payload([item]))


@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("ccode", 1), ("id", True), ("internalRank", 1.0), ("matches", {}),
        ("name", None), ("primaryId", "42"), ("simpleLeague", 0),
        ("groupName", None), ("isGroup", 1), ("localRank", True),
        ("parentLeagueId", None), ("parentLeagueName", 4),
    ],
)
def test_every_league_field_is_type_and_null_frozen(key: str, bad: Any):
    item = league()
    item[key] = bad
    with pytest.raises(FotMobDataMatchesSchemaError):
        assess(payload([item]))


def test_unknown_league_key_rejected_and_empty_matches_accepted():
    item = league([])
    empty = assess(payload([item]))
    assert empty.match_count == 0
    item["unknown"] = 1
    with pytest.raises(FotMobDataMatchesSchemaError, match="unreviewed"):
        assess(payload([item]))


def test_empty_league_list_is_structurally_accepted_without_hardcoded_count():
    result = assess(payload([]))
    assert result.league_count == 0
    assert result.match_count == 0
    assert result.league_key_union == ()
    assert result.fixture_identity_candidate is StructuralCapability.ABSENT_IN_CAPTURE


def test_match_key_freeze_and_exact_record_accepted():
    result = assess()
    expected = tuple(sorted(MATCH_KEYS))
    assert result.match_key_union == expected
    assert result.match_key_intersection == expected


@pytest.mark.parametrize("key", sorted(MATCH_KEYS))
def test_every_match_key_is_required(key: str):
    item = match()
    item.pop(key)
    with pytest.raises(FotMobDataMatchesSchemaError, match="required"):
        assess(payload([league([item])]))


def test_unknown_match_key_and_duplicate_id_fail_closed():
    item = match()
    item["unknown"] = None
    with pytest.raises(FotMobDataMatchesSchemaError, match="unreviewed"):
        assess(payload([league([item])]))
    with pytest.raises(FotMobDataMatchesSchemaError, match="duplicate"):
        assess(payload([league([match(1), match(1)])]))


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("id", True), ("leagueId", True), ("statusId", True), ("time", None),
        ("timeTS", True), ("tournamentStage", None), ("eliminatedTeamId", 1),
    ],
)
def test_match_field_domains_are_frozen(field: str, bad: Any):
    item = match()
    item[field] = bad
    with pytest.raises(FotMobDataMatchesSchemaError):
        assess(payload([league([item])]))


def test_league_linkage_mismatch_fails_closed():
    item = match()
    item["leagueId"] = 99
    with pytest.raises(FotMobDataMatchesSchemaError, match="containing league"):
        assess(payload([league([item])]))


@pytest.mark.parametrize("side", ["home", "away"])
def test_home_and_away_exact_team_schema(side: str):
    assert TEAM_KEYS == {"id", "score", "name", "longName"}
    item = match()
    item[side]["extra"] = 1
    with pytest.raises(FotMobDataMatchesSchemaError, match="unreviewed"):
        assess(payload([league([item])]))


@pytest.mark.parametrize("side", ["home", "away"])
@pytest.mark.parametrize("key", sorted(TEAM_KEYS))
def test_each_team_key_is_required(side: str, key: str):
    item = match()
    item[side].pop(key)
    with pytest.raises(FotMobDataMatchesSchemaError, match="required"):
        assess(payload([league([item])]))


@pytest.mark.parametrize(
    ("key", "bad"),
    [("id", True), ("score", True), ("name", None), ("longName", 1)],
)
def test_team_field_types_are_exact(key: str, bad: Any):
    item = match()
    item["home"][key] = bad
    with pytest.raises(FotMobDataMatchesSchemaError):
        assess(payload([league([item])]))


def test_score_need_not_be_zero_and_repeated_team_ids_are_allowed():
    first = match(1)
    second = match(2)
    first["home"]["score"] = 3
    second["home"]["id"] = first["home"]["id"]
    result = assess(payload([league([first, second])]))
    assert result.match_count == 2
    assert result.full_time_score_candidate is StructuralCapability.AMBIGUOUS


def test_kickoff_exact_utc_epoch_milliseconds_accepted():
    result = assess()
    assert result.kickoff_timestamp_mismatch_count == 0
    assert result.kickoff_request_date_mismatch_count == 0


@pytest.mark.parametrize(
    "bad",
    [
        "2026-08-15T12:00:00.000",
        "2026-08-15T13:00:00+01:00",
        "2026/08/15 12:00:00Z",
        "2026-08-15T12:00:00.000001Z",
        None,
    ],
)
def test_invalid_or_non_millisecond_utc_kickoff_rejected(bad: Any):
    item = match()
    item["status"]["utcTime"] = bad
    with pytest.raises(FotMobDataMatchesSchemaError):
        assess(payload([league([item])]))


def test_time_ts_mismatch_bool_and_request_date_mismatch_rejected():
    for changed in (KICKOFF_MS + 1, True):
        item = match()
        item["timeTS"] = changed
        with pytest.raises(FotMobDataMatchesSchemaError):
            assess(payload([league([item])]))
    item = match()
    item["status"]["utcTime"] = "2026-08-16T00:00:00.000Z"
    item["timeTS"] = 1786838400000
    with pytest.raises(FotMobDataMatchesSchemaError, match="request date"):
        assess(payload([league([item])]))


def test_display_time_adjacent_date_is_not_authoritative():
    item = match()
    item["time"] = "16.08.2026 01:00"
    assert assess(payload([league([item])])).match_count == 1


def test_frozen_status_and_halfs_key_sets_are_exact():
    assert STATUS_REQUIRED_KEYS == {
        "utcTime", "halfs", "periodLength", "started", "cancelled", "finished"
    }
    assert STATUS_OPTIONAL_KEYS == {"reason", "aggregatedStr"}
    assert STATUS_ALLOWED_KEYS == STATUS_REQUIRED_KEYS | STATUS_OPTIONAL_KEYS
    assert HALFS_KEYS == {"firstHalfStarted"}
    assert REASON_KEYS == {"short", "shortKey", "long", "longKey"}


@pytest.mark.parametrize("key", sorted(STATUS_REQUIRED_KEYS))
def test_every_required_status_key_is_required(key: str):
    item = match()
    item["status"].pop(key)
    with pytest.raises(FotMobDataMatchesSchemaError, match="required"):
        assess(payload([league([item])]))


@pytest.mark.parametrize("key", ["started", "cancelled", "finished"])
@pytest.mark.parametrize("bad", [0, 1, None, "false"])
def test_status_boolean_fields_are_exact(key: str, bad: Any):
    item = match()
    item["status"][key] = bad
    with pytest.raises(FotMobDataMatchesSchemaError):
        assess(payload([league([item])]))


def test_status_optional_domains_accepted_without_semantic_interpretation():
    item = match()
    item["status"]["aggregatedStr"] = "0 - 0"
    item["status"]["reason"] = {
        "short": "PPD", "shortKey": "postponed", "long": "Postponed",
        "longKey": "match_postponed",
    }
    result = assess(payload([league([item])]))
    assert result.status_candidate is StructuralCapability.PRESENT_IN_CAPTURE
    assert result.full_time_score_candidate is StructuralCapability.AMBIGUOUS


@pytest.mark.parametrize(
    ("key", "bad"),
    [("periodLength", True), ("aggregatedStr", None), ("reason", None), ("halfs", [])],
)
def test_status_field_type_null_domains_are_frozen(key: str, bad: Any):
    item = match()
    item["status"][key] = bad
    with pytest.raises(FotMobDataMatchesSchemaError):
        assess(payload([league([item])]))


def test_unknown_status_halfs_and_reason_keys_fail_closed():
    for container in ("status", "halfs", "reason"):
        item = match()
        if container == "status":
            item["status"]["newField"] = 1
        elif container == "halfs":
            item["status"]["halfs"]["halfTimeScore"] = "0-0"
        else:
            item["status"]["reason"] = {
                "short": "x", "shortKey": "x", "long": "x", "longKey": "x",
                "newField": "x",
            }
        with pytest.raises(FotMobDataMatchesSchemaError, match="unreviewed"):
            assess(payload([league([item])]))


@pytest.mark.parametrize("key", sorted(REASON_KEYS))
def test_each_reason_key_is_required_and_exact_string(key: str):
    base = {"short": "x", "shortKey": "x", "long": "x", "longKey": "x"}
    item = match()
    item["status"]["reason"] = {k: v for k, v in base.items() if k != key}
    with pytest.raises(FotMobDataMatchesSchemaError, match="required"):
        assess(payload([league([item])]))
    item["status"]["reason"] = dict(base, **{key: None})
    with pytest.raises(FotMobDataMatchesSchemaError, match="string"):
        assess(payload([league([item])]))


def test_first_half_started_is_exact_string_and_has_no_score_semantics():
    item = match()
    item["status"]["halfs"]["firstHalfStarted"] = None
    with pytest.raises(FotMobDataMatchesSchemaError):
        assess(payload([league([item])]))
    result = assess()
    assert result.half_time_score_candidate is StructuralCapability.ABSENT_IN_CAPTURE
    assert "half_time_score" not in result.to_dict()


def test_structural_capabilities_and_success_counts_are_exact():
    result = assess()
    assert result.league_count == 1 and result.match_count == 1
    assert result.duplicate_match_id_count == 0
    assert result.league_link_mismatch_count == 0
    assert result.kickoff_timestamp_mismatch_count == 0
    assert result.kickoff_request_date_mismatch_count == 0
    assert result.fixture_identity_candidate is StructuralCapability.PRESENT_IN_CAPTURE
    assert result.kickoff_candidate is StructuralCapability.PRESENT_IN_CAPTURE
    assert result.team_identity_candidate is StructuralCapability.PRESENT_IN_CAPTURE
    assert result.competition_identity_candidate is StructuralCapability.PRESENT_IN_CAPTURE
    assert result.status_candidate is StructuralCapability.PRESENT_IN_CAPTURE
    assert result.full_time_score_candidate is StructuralCapability.AMBIGUOUS
    assert result.half_time_score_candidate is StructuralCapability.ABSENT_IN_CAPTURE
    assert result.source_freshness_candidate is StructuralCapability.ABSENT_IN_CAPTURE


def test_counts_are_computed_not_hardcoded():
    value = payload([league([match(1), match(2)]), dict(league([]), id=43, primaryId=43)])
    value["leagues"][1]["matches"] = []
    result = assess(value)
    assert result.league_count == 2 and result.match_count == 2


def test_serialization_is_canonical_deterministic_and_hashed_exactly():
    result = assess()
    first = canonical_data_matches_schema_assessment_bytes(result)
    second = canonical_data_matches_schema_assessment_bytes(result)
    assert first == second and first.endswith(b"\n")
    assert json.loads(first) == data_matches_schema_assessment_to_dict(result)
    assert sha256_data_matches_schema_assessment(result) == hashlib.sha256(first).hexdigest()


def test_serialized_assessment_contains_no_fixture_values():
    serialized = canonical_data_matches_schema_assessment_bytes(assess()).decode("utf-8")
    for forbidden in (
        "Example competition", "Home", "Away", str(KICKOFF_MS), KICKOFF,
        '"id":1001', '"score":0',
    ):
        assert forbidden not in serialized


def _write_verified_capture(tmp_path: Path) -> tuple[Path, Path]:
    repository = tmp_path / "repository"
    repository.mkdir()
    raw = raw_bytes()
    response = CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json",
        content_length=len(raw),
        body=raw,
        observed_at=OBSERVED,
        network_acquisition_performed=True,
    )
    capture, _ = write_data_matches_capture_directory(
        response,
        request_date=DATE,
        timezone=TIMEZONE,
        ccode3=CCODE3,
        repository_root=repository,
    )
    return repository, capture


def test_cli_fixed_root_canonical_stdout_and_no_files_written(tmp_path, capsys):
    repository, capture = _write_verified_capture(tmp_path)
    before = sorted(path.relative_to(repository) for path in repository.rglob("*"))
    assert schema_script.main(
        ["--capture-directory", str(capture)], repository_root=repository
    ) == 0
    output = capsys.readouterr().out.encode("utf-8")
    assert output.endswith(b"\n")
    assert json.loads(output)["match_count"] == 1
    after = sorted(path.relative_to(repository) for path in repository.rglob("*"))
    assert after == before


def test_cli_parser_exposes_only_capture_directory():
    options = {
        option
        for action in schema_script.build_parser()._actions
        for option in action.option_strings
    }
    assert options == {"-h", "--help", "--capture-directory"}


def test_cli_root_escape_and_missing_capture_fail(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(FotMobDataMatchesSchemaError, match="outside"):
        schema_script._capture_path(outside, repository_root=repository)
    with pytest.raises(FotMobDataMatchesSchemaError):
        schema_script._capture_path(
            repository / schema_script.ALLOWED_ROOT_RELATIVE / "missing",
            repository_root=repository,
        )


def test_response_symlink_rejected_when_supported(tmp_path):
    source = tmp_path / "source.json"
    source.write_bytes(b"{}")
    link = tmp_path / "response.json"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(FotMobDataMatchesSchemaError, match="symlink"):
        schema_script._read_bounded_response(link)


def test_bounded_response_read_rejects_empty_and_obvious_oversize(tmp_path, monkeypatch):
    path = tmp_path / "response.json"
    path.write_bytes(b"")
    with pytest.raises(FotMobDataMatchesSchemaError, match="empty"):
        schema_script._read_bounded_response(path)
    path.write_bytes(b"x" * (MAX_RESPONSE_BYTES + 1))
    monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail("unbounded read"))
    with pytest.raises(FotMobDataMatchesSchemaError, match="8 MiB"):
        schema_script._read_bounded_response(path)


class _GrowthReader:
    def __init__(self, requested: list[int]) -> None:
        self.requested = requested

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, amount: int) -> bytes:
        self.requested.append(amount)
        return b"x" * amount


def test_stat_read_growth_is_bounded_at_maximum_plus_one(tmp_path, monkeypatch):
    path = tmp_path / "response.json"
    path.write_bytes(b"{}")
    requested: list[int] = []
    monkeypatch.setattr(Path, "open", lambda self, *a, **k: _GrowthReader(requested))
    monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail("unbounded read"))
    with pytest.raises(FotMobDataMatchesSchemaError, match="8 MiB"):
        schema_script._read_bounded_response(path)
    assert requested == [MAX_RESPONSE_BYTES + 1]


def test_verifier_runs_before_independent_assessment_read(tmp_path, monkeypatch):
    repository, capture = _write_verified_capture(tmp_path)
    events: list[str] = []
    original_verify = schema_script.verify_data_matches_capture_directory
    original_read = schema_script._read_bounded_response
    monkeypatch.setattr(
        schema_script,
        "verify_data_matches_capture_directory",
        lambda *a, **k: (events.append("verify"), original_verify(*a, **k))[1],
    )
    monkeypatch.setattr(
        schema_script,
        "_read_bounded_response",
        lambda *a, **k: (events.append("read"), original_read(*a, **k))[1],
    )
    schema_script._verified_raw(capture, repository / schema_script.ALLOWED_ROOT_RELATIVE)
    assert events == ["verify", "read"]


def test_source_capability_registry_remains_unknown():
    from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY

    source = SOURCE_CAPABILITY_REGISTRY["fotmob_unofficial"]
    assert all(
        value is CapabilityAvailability.UNKNOWN
        for value in (
            source.full_time_score, source.half_time_score, source.event_timestamps,
            source.reliable_fixture_identity, source.historical_coverage,
            source.freshness_metadata,
        )
    )


def test_production_modules_are_offline_and_have_no_downstream_imports():
    imports: set[str] = set()
    for module in (schema_domain, schema_script):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
    forbidden = {
        "http.client", "requests", "httpx", "aiohttp", "urllib.request",
        "curl_cffi", "playwright", "selenium", "domain.fixture_catalog",
        "domain.fixture_intelligence", "domain.fixture_model_features",
        "intelligence.prediction_engine", "intelligence.match_analyst",
    }
    assert imports.isdisjoint(forbidden)


def test_no_candidate_or_fixture_value_output_type_exists():
    assert not hasattr(schema_domain, "FotMobFixtureCandidate")
    assert not hasattr(schema_domain, "FixtureCatalog")
    keys = set(assess().to_dict())
    assert not {"fixtures", "matches", "match_ids", "teams", "kickoffs", "scores"} & keys
