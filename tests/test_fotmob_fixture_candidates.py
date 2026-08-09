from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
import json
from pathlib import Path

import pytest

import domain.fotmob_fixture_candidates as candidate_module
import scripts.build_fotmob_fixture_candidates as candidate_cli
from domain.fotmob_data_matches_capture import (
    MAX_RESPONSE_BYTES,
    CapturedFotMobDataMatchesResponse,
    build_data_matches_capture_manifest,
    canonical_data_matches_capture_manifest_bytes,
    capture_identifier,
    sha256_data_matches_capture_manifest,
)
from domain.fotmob_data_matches_schema import (
    FotMobDataMatchesSchemaError,
    assess_fotmob_data_matches_schema,
    sha256_data_matches_schema_assessment,
)
from domain.fotmob_fixture_candidates import (
    DATASET_NAME,
    SCHEMA_VERSION,
    SOURCE_NAME,
    SUMMARY_DATASET_NAME,
    FixtureCandidateReviewStatus,
    FotMobFixtureCandidateBundle,
    FotMobFixtureCandidateError,
    build_fotmob_fixture_candidate_bundle,
    canonical_fotmob_fixture_candidate_bundle_bytes,
    fotmob_fixture_candidate_bundle_to_dict,
    sha256_fotmob_fixture_candidate_bundle,
)
from domain.source_capabilities import (
    SOURCE_CAPABILITY_REGISTRY,
    CapabilityAvailability,
)


UTC = datetime.timezone.utc
ZERO_SHA = "0" * 64


def _kickoff(date: str, hour: int = 12) -> str:
    return (
        f"{date[:4]}-{date[4:6]}-{date[6:]}T{hour:02d}:00:00.000Z"
    )


def _epoch_ms(value: str) -> int:
    parsed = datetime.datetime.fromisoformat(value[:-1] + "+00:00")
    epoch = datetime.datetime(1970, 1, 1, tzinfo=UTC)
    delta = parsed - epoch
    return delta.days * 86_400_000 + delta.seconds * 1000 + delta.microseconds // 1000


def _match(
    *,
    date: str = "20260815",
    match_id: int = 1001,
    league_id: int = 10,
    home_id: int = 101,
    home_name: str = "Home FC",
    home_long_name: str | None = None,
    away_id: int = 202,
    away_name: str = "Away FC",
    away_long_name: str | None = None,
    hour: int = 12,
    display_time: str | None = None,
) -> dict:
    utc_time = _kickoff(date, hour)
    return {
        "away": {
            "id": away_id,
            "score": 0,
            "name": away_name,
            "longName": away_name if away_long_name is None else away_long_name,
        },
        "eliminatedTeamId": None,
        "home": {
            "id": home_id,
            "score": 0,
            "name": home_name,
            "longName": home_name if home_long_name is None else home_long_name,
        },
        "id": match_id,
        "leagueId": league_id,
        "status": {
            "utcTime": utc_time,
            "halfs": {"firstHalfStarted": ""},
            "periodLength": 45,
            "started": False,
            "cancelled": False,
            "finished": False,
        },
        "statusId": 1,
        "time": display_time or f"{date[6:]}.{date[4:6]}.{date[:4]} 12:00",
        "timeTS": _epoch_ms(utc_time),
        "tournamentStage": "",
    }


def _payload(
    *,
    date: str = "20260815",
    matches: list[dict] | None = None,
    league_id: int = 10,
    primary_id: int = 10,
    league_name: str = "League Ω",
    ccode: str = "NGA",
) -> dict:
    return {
        "leagues": [
            {
                "ccode": ccode,
                "id": league_id,
                "internalRank": 1,
                "matches": [_match(date=date, league_id=league_id)] if matches is None else matches,
                "name": league_name,
                "primaryId": primary_id,
                "simpleLeague": False,
            }
        ],
        "date": date,
    }


def _raw(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _capture(
    payload: dict | None = None,
    *,
    date: str = "20260815",
    observed_second: int = 0,
) -> tuple[bytes, object]:
    raw = _raw(_payload(date=date) if payload is None else payload)
    response = CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=len(raw),
        body=raw,
        observed_at=datetime.datetime(2026, 8, 9, 8, 0, observed_second, tzinfo=UTC),
        network_acquisition_performed=True,
    )
    manifest = build_data_matches_capture_manifest(
        response,
        request_date=date,
        timezone="UTC",
        ccode3="NGA",
    )
    return raw, manifest


def _bundle(*captures):
    return build_fotmob_fixture_candidate_bundle(captures or (_capture(),))


def _write_capture(repository: Path, capture: tuple[bytes, object], name: str | None = None) -> Path:
    raw, manifest = capture
    capture_name = name or capture_identifier(
        request_date=manifest.request_date,
        timezone=manifest.timezone,
        ccode3=manifest.ccode3,
        observed_at=manifest.observed_at,
        raw_sha256=manifest.raw_sha256,
    )
    directory = (
        repository
        / candidate_cli.ALLOWED_ROOT_RELATIVE
        / manifest.request_date
        / capture_name
    )
    directory.mkdir(parents=True)
    (directory / "response.json").write_bytes(raw)
    (directory / "manifest.json").write_bytes(
        canonical_data_matches_capture_manifest_bytes(manifest)
    )
    return directory


def test_contract_dataset_schema_enum_and_immutability():
    bundle = _bundle()
    assert DATASET_NAME == "athena-fotmob-fixture-candidates-v1"
    assert SCHEMA_VERSION == 1 and type(SCHEMA_VERSION) is int
    assert list(FixtureCandidateReviewStatus) == [FixtureCandidateReviewStatus.UNREVIEWED]
    assert bundle.schema_version == 1
    assert bundle.dataset_name == DATASET_NAME
    assert dataclasses.fields(FotMobFixtureCandidateBundle)
    with pytest.raises(dataclasses.FrozenInstanceError):
        bundle.candidate_count = 2
    with pytest.raises(dataclasses.FrozenInstanceError):
        bundle.candidates[0].home_name = "changed"


@pytest.mark.parametrize(
    ("class_name", "expected_fields"),
    [
        (
            "FotMobFixtureCandidateSource",
            {
                "source_capture_dataset_name",
                "source_capture_schema_version",
                "source_capture_manifest_sha256",
                "source_raw_sha256",
                "source_raw_size",
                "source_observed_at",
                "request_date",
                "timezone",
                "ccode3",
                "schema_assessment_sha256",
                "candidate_count",
            },
        ),
        (
            "FotMobFixtureCandidate",
            {
                "review_status",
                "source",
                "source_match_id",
                "source_league_id",
                "source_competition_primary_id",
                "source_competition_name",
                "source_competition_ccode",
                "home_source_team_id",
                "home_name",
                "home_long_name",
                "away_source_team_id",
                "away_name",
                "away_long_name",
                "kickoff_utc",
                "source_capture_manifest_sha256",
                "source_raw_sha256",
                "source_request_date",
                "source_observed_at",
            },
        ),
        (
            "FotMobTeamIdentityVariant",
            {"name", "long_name", "source_capture_manifest_sha256s"},
        ),
        ("FotMobTeamIdentityConflict", {"source_team_id", "variants"}),
        (
            "FotMobCompetitionIdentityVariant",
            {"name", "ccode", "primary_id", "source_capture_manifest_sha256s"},
        ),
        ("FotMobCompetitionIdentityConflict", {"source_league_id", "variants"}),
        (
            "FotMobFixtureIdentityVariant",
            {
                "source_league_id",
                "home_source_team_id",
                "away_source_team_id",
                "kickoff_utc",
                "source_capture_manifest_sha256s",
            },
        ),
        ("FotMobFixtureIdentityConflict", {"source_match_id", "variants"}),
        (
            "FotMobFixtureCandidateBundle",
            {
                "schema_version",
                "dataset_name",
                "sources",
                "candidate_count",
                "candidates",
                "duplicate_source_match_id_count",
                "fixture_identity_conflict_count",
                "fixture_identity_conflicts",
                "team_identity_conflict_count",
                "team_identity_conflicts",
                "competition_identity_conflict_count",
                "competition_identity_conflicts",
                "safety",
            },
        ),
    ],
)
def test_public_dataclasses_have_exact_fields(class_name, expected_fields):
    cls = getattr(candidate_module, class_name)
    assert {field.name for field in dataclasses.fields(cls)} == expected_fields


@pytest.mark.parametrize(
    "field_name",
    [
        "review_status",
        "source",
        "source_match_id",
        "source_league_id",
        "source_competition_primary_id",
        "source_competition_name",
        "source_competition_ccode",
        "home_source_team_id",
        "home_name",
        "home_long_name",
        "away_source_team_id",
        "away_name",
        "away_long_name",
        "kickoff_utc",
        "source_capture_manifest_sha256",
        "source_raw_sha256",
        "source_request_date",
        "source_observed_at",
    ],
)
def test_every_candidate_contract_field_is_serialized(field_name):
    candidate = _bundle().candidates[0]
    assert field_name in candidate.to_dict()


@pytest.mark.parametrize(
    "field_name",
    [
        "source_capture_dataset_name",
        "source_capture_schema_version",
        "source_capture_manifest_sha256",
        "source_raw_sha256",
        "source_raw_size",
        "source_observed_at",
        "request_date",
        "timezone",
        "ccode3",
        "schema_assessment_sha256",
        "candidate_count",
    ],
)
def test_every_source_descriptor_field_is_serialized(field_name):
    source = _bundle().sources[0]
    assert field_name in source.to_dict()


@pytest.mark.parametrize(
    "field_name",
    [
        "schema_version",
        "dataset_name",
        "sources",
        "candidate_count",
        "candidates",
        "duplicate_source_match_id_count",
        "fixture_identity_conflict_count",
        "fixture_identity_conflicts",
        "team_identity_conflict_count",
        "team_identity_conflicts",
        "competition_identity_conflict_count",
        "competition_identity_conflicts",
        "safety",
    ],
)
def test_every_bundle_contract_field_is_serialized(field_name):
    assert field_name in _bundle().to_dict()


@pytest.mark.parametrize(
    "safety_key",
    [
        "network_acquisition_authorized",
        "raw_json_capture_authorized",
        "schema_assessment_authorized",
        "fixture_candidate_generation_authorized",
        "team_identity_resolution_authorized",
        "competition_identity_resolution_authorized",
        "fixture_identity_resolution_authorized",
        "source_qualified",
        "fixture_promotion_authorized",
        "intelligence_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    ],
)
def test_each_safety_authority_is_exact_false(safety_key):
    value = _bundle().safety[safety_key]
    assert value is False and type(value) is bool


def test_bool_schema_rejected():
    bundle = _bundle()
    with pytest.raises(FotMobFixtureCandidateError):
        dataclasses.replace(bundle, schema_version=True)


@pytest.mark.parametrize("invalid_status", ["UNREVIEWED", None, False])
def test_candidate_review_status_rejects_non_enum_values(invalid_status):
    candidate = _bundle().candidates[0]
    with pytest.raises(FotMobFixtureCandidateError):
        dataclasses.replace(candidate, review_status=invalid_status)


def test_safety_is_detached_immutable_and_all_false():
    bundle = _bundle()
    expected = {
        "network_acquisition_authorized",
        "raw_json_capture_authorized",
        "schema_assessment_authorized",
        "fixture_candidate_generation_authorized",
        "team_identity_resolution_authorized",
        "competition_identity_resolution_authorized",
        "fixture_identity_resolution_authorized",
        "source_qualified",
        "fixture_promotion_authorized",
        "intelligence_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
    assert set(bundle.safety) == expected
    assert all(value is False and type(value) is bool for value in bundle.safety.values())
    with pytest.raises(TypeError):
        bundle.safety["source_qualified"] = True
    serialized = bundle.to_dict()
    serialized["safety"]["source_qualified"] = True
    assert bundle.safety["source_qualified"] is False


def test_at_least_one_source_and_tuple_shape_required():
    for value in ([], (), b"raw", "capture"):
        with pytest.raises(FotMobFixtureCandidateError):
            build_fotmob_fixture_candidate_bundle(value)
    with pytest.raises(FotMobFixtureCandidateError):
        build_fotmob_fixture_candidate_bundle([(b"x",)])


def test_duplicate_manifest_input_rejected():
    capture = _capture()
    with pytest.raises(FotMobFixtureCandidateError, match="duplicate source manifest"):
        _bundle(capture, capture)


def test_raw_size_and_sha_mismatch_rejected():
    raw, manifest = _capture()
    with pytest.raises(FotMobFixtureCandidateError, match="size"):
        _bundle((raw + b" ", manifest))
    changed = b"x" + raw[1:]
    assert len(changed) == len(raw)
    with pytest.raises(FotMobFixtureCandidateError, match="SHA-256"):
        _bundle((changed, manifest))


def test_source_dataset_and_schema_are_pr38_v1():
    raw, manifest = _capture()
    object.__setattr__(manifest, "dataset_name", "foreign")
    with pytest.raises(FotMobFixtureCandidateError):
        _bundle((raw, manifest))
    raw, manifest = _capture()
    object.__setattr__(manifest, "schema_version", 2)
    with pytest.raises(FotMobFixtureCandidateError):
        _bundle((raw, manifest))


def test_pr39_assessment_runs_before_extraction(monkeypatch):
    called = []

    def fail_assessment(raw, manifest):
        called.append((raw, manifest))
        raise FotMobDataMatchesSchemaError("drift")

    def forbidden_parse(raw):
        raise AssertionError("extraction parse ran before assessment")

    monkeypatch.setattr(candidate_module, "assess_fotmob_data_matches_schema", fail_assessment)
    monkeypatch.setattr(candidate_module, "_strict_json", forbidden_parse)
    capture = _capture()
    with pytest.raises(FotMobFixtureCandidateError, match="assessment failed"):
        _bundle(capture)
    assert called == [capture]


def test_assessment_sha_and_source_ancestry_propagated_exactly():
    raw, manifest = _capture()
    assessment = assess_fotmob_data_matches_schema(raw, manifest)
    bundle = _bundle((raw, manifest))
    source = bundle.sources[0]
    assert source.schema_assessment_sha256 == sha256_data_matches_schema_assessment(assessment)
    assert source.source_capture_manifest_sha256 == sha256_data_matches_capture_manifest(manifest)
    assert source.source_raw_sha256 == manifest.raw_sha256
    assert source.source_raw_size == manifest.raw_size
    assert source.source_observed_at == manifest.observed_at
    assert (source.request_date, source.timezone, source.ccode3) == (
        manifest.request_date,
        manifest.timezone,
        manifest.ccode3,
    )


def test_exact_candidate_mapping_and_one_match_one_candidate():
    match = _match(
        match_id=987,
        league_id=42,
        home_id=394121,
        home_name="VfL Wolfsburg (W)",
        home_long_name="VfL Wolfsburg (W)",
        away_id=88,
        away_name="Åway—Club",
        away_long_name="Åway—Club Long",
        hour=17,
    )
    raw, manifest = _capture(
        _payload(
            matches=[match],
            league_id=42,
            primary_id=7,
            league_name="Premier League!",
            ccode="ENG",
        )
    )
    bundle = _bundle((raw, manifest))
    assert bundle.candidate_count == bundle.sources[0].candidate_count == 1
    item = bundle.candidates[0]
    assert item.review_status is FixtureCandidateReviewStatus.UNREVIEWED
    assert item.source == SOURCE_NAME == "FOTMOB"
    assert item.source_match_id == 987 and type(item.source_match_id) is int
    assert item.source_league_id == 42
    assert item.source_competition_primary_id == 7
    assert item.source_competition_name == "Premier League!"
    assert item.source_competition_ccode == "ENG"
    assert item.home_source_team_id == 394121
    assert item.home_name == item.home_long_name == "VfL Wolfsburg (W)"
    assert item.away_source_team_id == 88
    assert item.away_name == "Åway—Club"
    assert item.away_long_name == "Åway—Club Long"
    assert item.kickoff_utc == datetime.datetime(2026, 8, 15, 17, tzinfo=UTC)
    assert item.source_capture_manifest_sha256 == sha256_data_matches_capture_manifest(manifest)
    assert item.source_raw_sha256 == manifest.raw_sha256
    assert item.source_request_date == manifest.request_date
    assert item.source_observed_at == manifest.observed_at


@pytest.mark.parametrize(
    "value",
    [
        "VfL Wolfsburg (W)",
        "St. John’s / Club!",
        "ŽFK  日本",
        "  exact internal spacing  ",
        "mIxEd CaSe",
    ],
)
def test_source_strings_are_preserved_exactly(value):
    match = _match(home_name=value, home_long_name=value)
    raw, manifest = _capture(_payload(matches=[match], league_name=value, ccode="X-Y"))
    candidate = _bundle((raw, manifest)).candidates[0]
    assert candidate.home_name == value
    assert candidate.home_long_name == value
    assert candidate.source_competition_name == value
    assert candidate.source_competition_ccode == "X-Y"


@pytest.mark.parametrize(
    "forbidden",
    [
        "score",
        "statusId",
        "started",
        "cancelled",
        "finished",
        "reason",
        "aggregatedStr",
        "halfs",
        "firstHalfStarted",
        "time",
        "tournamentStage",
        "eliminatedTeamId",
        "fixture_identifier",
        "gender",
        "category",
        "canonical_team_id",
        "fixture_status",
        "full_time_score",
        "half_time_score",
    ],
)
def test_unreviewed_fields_are_not_mapped(forbidden):
    serialized = _bundle().candidates[0].to_dict()
    assert forbidden not in serialized
    assert forbidden not in {field.name for field in dataclasses.fields(type(_bundle().candidates[0]))}


def test_wolfsburg_source_id_conflict_preserves_both_variants():
    first = _capture(
        _payload(matches=[_match(home_id=394121, home_name="VfL Wolfsburg")]),
        observed_second=1,
    )
    second = _capture(
        _payload(
            date="20260822",
            matches=[
                _match(
                    date="20260822",
                    match_id=2002,
                    home_id=394121,
                    home_name="VfL Wolfsburg (W)",
                )
            ],
        ),
        date="20260822",
        observed_second=2,
    )
    bundle = _bundle(first, second)
    assert bundle.team_identity_conflict_count == 1
    conflict = bundle.team_identity_conflicts[0]
    assert conflict.source_team_id == 394121
    assert [(v.name, v.long_name) for v in conflict.variants] == [
        ("VfL Wolfsburg", "VfL Wolfsburg"),
        ("VfL Wolfsburg (W)", "VfL Wolfsburg (W)"),
    ]
    assert all(v.source_capture_manifest_sha256s for v in conflict.variants)
    assert len(bundle.candidates) == 2


@pytest.mark.parametrize("changed", ["name", "longName"])
def test_team_name_or_long_name_difference_creates_conflict(changed):
    first = _capture(observed_second=1)
    match = _match(date="20260822", match_id=2)
    match["home"][changed] = "Changed"
    second = _capture(_payload(date="20260822", matches=[match]), date="20260822", observed_second=2)
    assert _bundle(first, second).team_identity_conflict_count == 1


def test_identical_team_variant_is_not_conflict_and_retains_ancestry():
    first = _capture(observed_second=1)
    second = _capture(
        _payload(date="20260822", matches=[_match(date="20260822", match_id=2)]),
        date="20260822",
        observed_second=2,
    )
    bundle = _bundle(first, second)
    assert bundle.team_identity_conflict_count == 0
    assert bundle.candidate_count == 2


@pytest.mark.parametrize("changed", ["name", "ccode", "primaryId"])
def test_competition_identity_differences_create_conflict(changed):
    first = _capture(observed_second=1)
    kwargs = {"league_name": "League Ω", "ccode": "NGA", "primary_id": 10}
    mapping = {"name": "league_name", "ccode": "ccode", "primaryId": "primary_id"}
    kwargs[mapping[changed]] = "Changed" if changed != "primaryId" else 99
    second = _capture(
        _payload(date="20260822", matches=[_match(date="20260822", match_id=2)], **kwargs),
        date="20260822",
        observed_second=2,
    )
    bundle = _bundle(first, second)
    assert bundle.competition_identity_conflict_count == 1
    assert len(bundle.competition_identity_conflicts[0].variants) == 2


def _same_date_pair(*, change: str | None = None):
    first = _capture(observed_second=1)
    match = _match(display_time="15.08.2026 13:00")
    if change == "league":
        match["leagueId"] = 11
        second_payload = _payload(matches=[match], league_id=11)
    else:
        if change == "home":
            match["home"]["id"] = 999
        elif change == "away":
            match["away"]["id"] = 999
        elif change == "kickoff":
            match = _match(hour=13, display_time="15.08.2026 13:00")
        second_payload = _payload(matches=[match])
    return _capture(observed_second=1), _capture(second_payload, observed_second=2)


def test_unique_match_ids_have_no_duplicate_or_conflict():
    first = _capture(observed_second=1)
    second = _capture(
        _payload(date="20260822", matches=[_match(date="20260822", match_id=2)]),
        date="20260822",
        observed_second=2,
    )
    bundle = _bundle(first, second)
    assert bundle.duplicate_source_match_id_count == 0
    assert bundle.fixture_identity_conflict_count == 0


def test_repeated_identical_match_id_counts_duplicate_without_conflict():
    bundle = _bundle(*_same_date_pair())
    assert bundle.duplicate_source_match_id_count == 1
    assert bundle.fixture_identity_conflict_count == 0
    assert bundle.candidate_count == 2


@pytest.mark.parametrize("change", ["league", "home", "away", "kickoff"])
def test_repeated_match_identity_change_creates_conflict(change):
    bundle = _bundle(*_same_date_pair(change=change))
    assert bundle.duplicate_source_match_id_count == 1
    assert bundle.fixture_identity_conflict_count == 1
    assert len(bundle.fixture_identity_conflicts[0].variants) == 2
    assert bundle.candidate_count == 2


def test_counts_empty_matches_and_multi_capture_aggregation():
    empty = _capture(_payload(matches=[]), observed_second=1)
    nonempty = _capture(
        _payload(date="20260822", matches=[_match(date="20260822", match_id=2)]),
        date="20260822",
        observed_second=2,
    )
    bundle = _bundle(empty, nonempty)
    assert [source.candidate_count for source in bundle.sources] == [0, 1]
    assert bundle.candidate_count == 1
    assert sum(source.candidate_count for source in bundle.sources) == bundle.candidate_count


def test_reversed_input_order_is_canonically_identical():
    first = _capture(observed_second=1)
    second = _capture(
        _payload(date="20260822", matches=[_match(date="20260822", match_id=2)]),
        date="20260822",
        observed_second=2,
    )
    forward = _bundle(first, second)
    reverse = _bundle(second, first)
    assert forward.sources == reverse.sources
    assert forward.candidates == reverse.candidates
    assert forward.team_identity_conflicts == reverse.team_identity_conflicts
    assert forward.competition_identity_conflicts == reverse.competition_identity_conflicts
    assert forward.fixture_identity_conflicts == reverse.fixture_identity_conflicts
    assert canonical_fotmob_fixture_candidate_bundle_bytes(forward) == canonical_fotmob_fixture_candidate_bundle_bytes(reverse)
    assert sha256_fotmob_fixture_candidate_bundle(forward) == sha256_fotmob_fixture_candidate_bundle(reverse)


def test_canonical_serialization_and_hash_are_exact():
    bundle = _bundle()
    as_dict = fotmob_fixture_candidate_bundle_to_dict(bundle)
    canonical = canonical_fotmob_fixture_candidate_bundle_bytes(bundle)
    assert as_dict == bundle.to_dict()
    assert canonical.endswith(b"\n") and not canonical.endswith(b"\n\n")
    assert canonical == (
        json.dumps(as_dict, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    assert sha256_fotmob_fixture_candidate_bundle(bundle) == hashlib.sha256(canonical).hexdigest()
    assert len(as_dict["candidates"]) == 1
    assert "fixture_identifier" not in canonical.decode("utf-8")
    assert "PROMOTED" not in canonical.decode("utf-8")


def test_cli_parser_is_repeatable_capture_only():
    parser = candidate_cli.build_parser()
    destinations = {action.dest for action in parser._actions}
    assert destinations == {"help", "capture_directory"}
    args = parser.parse_args(["--capture-directory", "a", "--capture-directory", "b"])
    assert args.capture_directory == ["a", "b"]
    with pytest.raises(SystemExit):
        parser.parse_args([])
    assert SUMMARY_DATASET_NAME == "athena-fotmob-fixture-candidate-build-summary-v1"


def test_cli_verifies_first_rereads_bounded_and_prints_summary_only(tmp_path, capsys):
    capture = _capture()
    directory = _write_capture(tmp_path, capture)
    relative = directory.relative_to(tmp_path)
    before = {path: path.read_bytes() for path in directory.iterdir()}
    assert candidate_cli.main(["--capture-directory", str(relative)], repository_root=tmp_path) == 0
    output = json.loads(capsys.readouterr().out)
    assert set(output) == {
        "schema_version",
        "dataset_name",
        "source_capture_count",
        "source_request_dates",
        "candidate_count",
        "duplicate_source_match_id_count",
        "fixture_identity_conflict_count",
        "team_identity_conflict_count",
        "competition_identity_conflict_count",
        "bundle_sha256",
    }
    assert output["source_capture_count"] == 1
    assert output["source_request_dates"] == ["20260815"]
    assert output["candidate_count"] == 1
    text = json.dumps(output)
    assert "Home FC" not in text and "1001" not in text
    assert {path: path.read_bytes() for path in directory.iterdir()} == before


def test_cli_verifier_is_first_gate(tmp_path, monkeypatch):
    directory = _write_capture(tmp_path, _capture())
    calls = []

    def fail_verifier(*args, **kwargs):
        calls.append((args, kwargs))
        raise candidate_cli.FotMobDataMatchesCaptureError("bad provenance")

    def forbidden_read(path):
        raise AssertionError("raw read occurred before verifier")

    monkeypatch.setattr(candidate_cli, "verify_data_matches_capture_directory", fail_verifier)
    monkeypatch.setattr(candidate_cli, "_read_bounded_response", forbidden_read)
    with pytest.raises(SystemExit):
        candidate_cli.main(
            ["--capture-directory", str(directory.relative_to(tmp_path))],
            repository_root=tmp_path,
        )
    assert len(calls) == 1
    assert calls[0][1]["require_network_acquisition_performed"] is True


def test_cli_root_escape_rejected(tmp_path):
    outside = tmp_path.parent / "outside-capture"
    outside.mkdir(exist_ok=True)
    with pytest.raises(SystemExit):
        candidate_cli.main(["--capture-directory", str(outside)], repository_root=tmp_path)


def test_bounded_reader_rejects_oversized_apparent_file(tmp_path):
    path = tmp_path / "response.json"
    with path.open("wb") as handle:
        handle.seek(MAX_RESPONSE_BYTES)
        handle.write(b"x")
    with pytest.raises(FotMobFixtureCandidateError, match="8 MiB"):
        candidate_cli._read_bounded_response(path)


def test_production_has_no_unrestricted_read_bytes_or_network_imports():
    root = Path(__file__).resolve().parents[1]
    files = [
        root / "domain/fotmob_fixture_candidates.py",
        root / "scripts/build_fotmob_fixture_candidates.py",
    ]
    forbidden_imports = {
        "http.client",
        "urllib.request",
        "requests",
        "httpx",
        "aiohttp",
        "playwright",
        "selenium",
        "domain.fixture_catalog",
        "domain.fixture_intelligence",
        "domain.fixture_model_features",
        "intelligence.prediction_engine",
    }
    for path in files:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        assert not imports & forbidden_imports
        assert ".read_bytes(" not in source
    cli_source = files[1].read_text(encoding="utf-8")
    assert "execute-live-network" not in cli_source


@pytest.mark.parametrize(
    "forbidden_term",
    [
        "compile_fixture_catalog",
        "build_strict_catalog",
        "load_fixture_provenance_records",
        "fuzzy",
        "gender inference",
        "canonical team registry",
    ],
)
def test_forbidden_architecture_is_absent_from_production(forbidden_term):
    root = Path(__file__).resolve().parents[1]
    production = (
        (root / "domain/fotmob_fixture_candidates.py").read_text(encoding="utf-8")
        + (root / "scripts/build_fotmob_fixture_candidates.py").read_text(encoding="utf-8")
    ).lower()
    assert forbidden_term.lower() not in production


def test_source_capability_registry_remains_unknown():
    capability = SOURCE_CAPABILITY_REGISTRY["fotmob_unofficial"]
    fields = (
        "full_time_score",
        "half_time_score",
        "event_timestamps",
        "reliable_fixture_identity",
        "historical_coverage",
        "freshness_metadata",
    )
    assert all(
        getattr(capability, field) is CapabilityAvailability.UNKNOWN
        for field in fields
    )
