import ast
import dataclasses
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

import pytest

import domain.fotmob_capture as capture_domain
import scripts.capture_fotmob_matches as capture_script
from domain.fotmob_capture import (
    ALLOWED_HOST,
    ALLOWED_PATH,
    CANDIDATE_FILENAME,
    DATASET_NAME,
    MANIFEST_FILENAME,
    MAX_RESPONSE_BYTES,
    RESPONSE_FILENAME,
    SCHEMA_VERSION,
    SOURCE_PROVIDER,
    FotMobCaptureError,
    FotMobFixtureCandidate,
    FotMobFixtureRejection,
    FotMobFixtureRejectionReason,
    FotMobMatchesCaptureManifest,
    FotMobResource,
    FotMobReviewStatus,
    build_capture_manifest,
    build_source_reference,
    canonical_candidate_jsonl_bytes,
    canonical_manifest_bytes,
    manifest_from_mapping,
    parse_fotmob_matches_payload,
    request_target,
    sha256_bytes,
    strict_json_loads,
    validate_logical_evidence_path,
    validate_request_date,
    verify_capture_directory,
)
from scripts.capture_fotmob_matches import (
    ALLOWED_OUTPUT_RELATIVE,
    USER_AGENT,
    CapturedHttpResponse,
    FotMobNetworkError,
    fetch_matches_by_date,
    main,
    parse_content_length,
    validate_output_root,
    write_capture_directory,
)


UTC = dt.timezone.utc
OBSERVED = dt.datetime(2026, 8, 8, 12, 34, 56, 123456, tzinfo=UTC)
REQUEST_DATE = "20260808"


def match(
    match_id=1234567,
    *,
    home="Home FC",
    away="Away FC",
    kickoff="2026-08-08T18:00:00+00:00",
):
    return {
        "id": match_id,
        "home": {"name": home},
        "away": {"name": away},
        "status": {"utcTime": kickoff},
    }


def payload(*matches, league="Competition One", extra=None):
    value = {
        "leagues": [
            {
                "name": league,
                "matches": list(matches or (match(),)),
            }
        ]
    }
    if extra:
        value.update(extra)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def manifest(raw=None, **kwargs):
    values = {
        "request_date": REQUEST_DATE,
        "observed_at": OBSERVED,
        "http_status": 200,
        "content_type": "application/json; charset=utf-8",
        "evidence_file_path": RESPONSE_FILENAME,
        "network_acquisition_performed": False,
    }
    values.update(kwargs)
    return build_capture_manifest(raw or payload(), **values)


class FakeHttpResponse:
    def __init__(self, body=None, *, status=200, content_type="application/json", content_length=None):
        self.status = status
        self.body = payload() if body is None else body
        self.headers = {"Content-Type": content_type}
        if content_length is not None:
            self.headers["Content-Length"] = content_length
        self.read_calls = []

    def getheader(self, name):
        return self.headers.get(name)

    def read(self, amount):
        self.read_calls.append(amount)
        return self.body[:amount]


class FakeConnection:
    def __init__(self, response, calls, host, port, timeout):
        self.response = response
        self.calls = calls
        self.calls.append(("connect", host, port, timeout))

    def request(self, method, target, headers):
        self.calls.append(("request", method, target, dict(headers)))

    def getresponse(self):
        self.calls.append(("getresponse",))
        return self.response

    def close(self):
        self.calls.append(("close",))


def fake_factory(response):
    calls = []

    def factory(host, port, timeout):
        return FakeConnection(response, calls, host, port, timeout)

    return factory, calls


def repo_root(tmp_path):
    (tmp_path / ".cache" / "athena-research").mkdir(parents=True)
    return tmp_path


def offline_response(raw=None):
    return CapturedHttpResponse(
        status=200,
        content_type="application/json",
        body=raw or payload(),
        observed_at=OBSERVED,
        network_acquisition_performed=False,
    )


def network_response(raw=None):
    response = FakeHttpResponse(body=raw or payload())
    factory, _ = fake_factory(response)
    return fetch_matches_by_date(
        REQUEST_DATE,
        connection_factory=factory,
        clock=lambda: OBSERVED,
    )


def write_offline_capture(tmp_path, raw=None):
    repository = repo_root(tmp_path)
    capture_directory, built_manifest = write_capture_directory(
        offline_response(raw),
        request_date=REQUEST_DATE,
        output_root=ALLOWED_OUTPUT_RELATIVE,
        repository_root=repository,
    )
    return repository, capture_directory, built_manifest


def write_network_capture(tmp_path, raw=None):
    repository = repo_root(tmp_path)
    capture_directory, built_manifest = write_capture_directory(
        network_response(raw),
        request_date=REQUEST_DATE,
        output_root=ALLOWED_OUTPUT_RELATIVE,
        repository_root=repository,
    )
    return repository, capture_directory, built_manifest


# Exact identity and strict schema.
def test_exact_dataset_schema_source_and_resource():
    built = manifest()
    assert built.dataset_name == "athena-fotmob-matches-capture-v1"
    assert built.schema_version == 1 and type(built.schema_version) is int
    assert built.source_provider == "FOTMOB_UNOFFICIAL_PUBLIC_WEB"
    assert built.resource is FotMobResource.MATCHES_BY_DATE
    assert list(FotMobResource) == [FotMobResource.MATCHES_BY_DATE]
    assert list(FotMobReviewStatus) == [FotMobReviewStatus.UNREVIEWED]


@pytest.mark.parametrize("bad", [True, 1.0, "1", 0, 2])
def test_schema_version_requires_exact_integer_one(bad):
    with pytest.raises(FotMobCaptureError):
        dataclasses.replace(manifest(), schema_version=bad)


def test_manifest_and_candidate_have_exact_requested_fields():
    assert [field.name for field in dataclasses.fields(FotMobFixtureCandidate)] == [
        "fixture_identifier",
        "source_fixture_identifier",
        "home_team",
        "away_team",
        "competition",
        "kickoff",
        "source_reference",
        "observed_at",
        "evidence_file_path",
        "evidence_sha256",
        "review_status",
    ]
    assert [field.name for field in dataclasses.fields(FotMobFixtureRejection)] == [
        "league_index",
        "match_index",
        "reason",
    ]
    assert len(dataclasses.fields(FotMobMatchesCaptureManifest)) == 17


# Date and fixed request identity.
def test_valid_date_and_canonical_source_reference():
    assert validate_request_date(REQUEST_DATE) == REQUEST_DATE
    assert build_source_reference(REQUEST_DATE) == (
        "https://www.fotmob.com/api/matches?date=20260808"
    )
    assert request_target(REQUEST_DATE) == "/api/matches?date=20260808"


@pytest.mark.parametrize(
    "bad",
    [
        "2026-08-08",
        "2026088",
        "202608080",
        "20260230",
        " 20260808",
        "20260808 ",
        True,
        None,
        "20260808&x=1",
        "2026/0808",
        "20260808?x",
        "202608%38",
        "２０２６０８０８",
    ],
)
def test_invalid_dates_fail_closed(bad):
    with pytest.raises(FotMobCaptureError):
        validate_request_date(bad)


def test_transport_host_port_path_method_and_headers_are_fixed():
    response = FakeHttpResponse()
    factory, calls = fake_factory(response)
    captured = fetch_matches_by_date(
        REQUEST_DATE,
        connection_factory=factory,
        clock=lambda: OBSERVED,
    )
    assert calls[0] == ("connect", ALLOWED_HOST, 443, 30)
    assert calls[1] == (
        "request",
        "GET",
        f"{ALLOWED_PATH}?date={REQUEST_DATE}",
        {"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    assert captured.body == response.body
    assert captured.network_acquisition_performed is True
    assert calls[-1] == ("close",)


def test_arbitrary_host_and_path_are_not_transport_inputs():
    parameters = dataclasses.fields(CapturedHttpResponse)
    assert "host" not in {item.name for item in parameters}
    assert "path" not in {item.name for item in parameters}
    assert ALLOWED_HOST == "www.fotmob.com"
    assert ALLOWED_PATH == "/api/matches"


# Explicit live gate and check-mode isolation.
def test_cli_without_live_gate_performs_no_network(capsys):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("network called")

    with pytest.raises(SystemExit) as error:
        main(["--date", REQUEST_DATE], connection_factory=forbidden)
    assert error.value.code == 2
    assert calls == []
    assert "live network acquisition is disabled" in capsys.readouterr().err


def test_check_and_live_flags_are_mutually_exclusive(tmp_path):
    with pytest.raises(SystemExit) as error:
        main(
            [
                "--check-capture",
                str(tmp_path),
                "--execute-live-network",
            ]
        )
    assert error.value.code == 2


def test_check_mode_never_calls_network(tmp_path, capsys):
    repository, capture_directory, _ = write_network_capture(tmp_path)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("network called")

    assert main(
        ["--check-capture", str(capture_directory)],
        connection_factory=forbidden,
        repository_root=repository,
    ) == 0
    assert calls == []
    assert "UNREVIEWED" in capsys.readouterr().out


def test_manual_response_provenance_is_false_and_immutable():
    response = offline_response()
    assert response.network_acquisition_performed is False
    with pytest.raises(dataclasses.FrozenInstanceError):
        response.network_acquisition_performed = True


def test_writer_preserves_offline_provenance_in_manifest_bytes(tmp_path):
    _, capture_directory, built = write_offline_capture(tmp_path)
    assert built.safety["network_acquisition_performed"] is False
    serialized = canonical_manifest_bytes(built)
    assert b'"network_acquisition_performed": false' in serialized
    assert (capture_directory / MANIFEST_FILENAME).read_bytes() == serialized


def test_live_cli_rejects_receipt_without_network_provenance(
    tmp_path, monkeypatch, capsys
):
    repository = repo_root(tmp_path)
    monkeypatch.setattr(capture_script, "fetch_matches_by_date", lambda *a, **k: offline_response())
    with pytest.raises(SystemExit) as error:
        main(
            ["--date", REQUEST_DATE, "--execute-live-network"],
            repository_root=repository,
        )
    assert error.value.code == 1
    assert "requires validated network acquisition provenance" in capsys.readouterr().err
    assert not (repository / ALLOWED_OUTPUT_RELATIVE).exists()


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"status": True}, "status"),
        ({"status": 201}, "status"),
        ({"content_type": "text/html"}, "Content-Type"),
        ({"body": "not bytes"}, "body"),
        ({"body": b"x" * (MAX_RESPONSE_BYTES + 1)}, "16 MiB"),
        ({"observed_at": dt.datetime(2026, 8, 8, 12, 0)}, "timezone-aware"),
        ({"observed_at": None}, "datetime"),
        ({"network_acquisition_performed": 1}, "exact bool"),
    ],
)
def test_invalid_transport_receipt_is_rejected_before_filesystem_mutation(
    tmp_path, changes, message
):
    repository = repo_root(tmp_path)
    values = {
        "status": 200,
        "content_type": "application/json",
        "body": payload(),
        "observed_at": OBSERVED,
        "network_acquisition_performed": False,
    }
    values.update(changes)
    with pytest.raises(FotMobNetworkError, match=message):
        CapturedHttpResponse(**values)
    assert not (repository / ALLOWED_OUTPUT_RELATIVE).exists()
    assert list(repository.rglob("*.tmp")) == []


def test_writer_revalidates_forged_receipt_before_filesystem_mutation(tmp_path):
    repository = repo_root(tmp_path)
    response = offline_response()
    object.__setattr__(response, "status", 201)
    with pytest.raises(FotMobCaptureError, match="invalid transport receipt"):
        write_capture_directory(
            response,
            request_date=REQUEST_DATE,
            output_root=ALLOWED_OUTPUT_RELATIVE,
            repository_root=repository,
        )
    assert not (repository / ALLOWED_OUTPUT_RELATIVE).exists()
    assert list(repository.rglob("*.tmp")) == []


# HTTP response checks.
@pytest.mark.parametrize("status", [199, 201, 301, 403, 429, 500, True, None])
def test_non_200_status_is_rejected_without_body_dump(status):
    response = FakeHttpResponse(status=status)
    factory, _ = fake_factory(response)
    with pytest.raises(FotMobNetworkError, match="requires HTTP 200"):
        fetch_matches_by_date(REQUEST_DATE, connection_factory=factory, clock=lambda: OBSERVED)
    assert response.read_calls == []


@pytest.mark.parametrize(
    "content_type",
    ["application/json", "APPLICATION/JSON", "application/json; charset=utf-8"],
)
def test_json_content_types_are_accepted(content_type):
    response = FakeHttpResponse(content_type=content_type)
    factory, _ = fake_factory(response)
    result = fetch_matches_by_date(
        REQUEST_DATE, connection_factory=factory, clock=lambda: OBSERVED
    )
    assert result.content_type == content_type


@pytest.mark.parametrize("content_type", ["text/html", "text/plain", "", None])
def test_non_json_content_types_are_rejected(content_type):
    response = FakeHttpResponse(content_type=content_type)
    factory, _ = fake_factory(response)
    with pytest.raises(FotMobNetworkError, match="Content-Type"):
        fetch_matches_by_date(REQUEST_DATE, connection_factory=factory, clock=lambda: OBSERVED)
    assert response.read_calls == []


@pytest.mark.parametrize("value", ["abc", "1.0", "+1", " 1", "1 ", "-1", True, []])
def test_malformed_or_negative_content_length_is_rejected(value):
    with pytest.raises(FotMobNetworkError, match="Content-Length"):
        parse_content_length(value)


def test_content_length_above_limit_fails_before_body_read():
    response = FakeHttpResponse(content_length=str(MAX_RESPONSE_BYTES + 1))
    factory, _ = fake_factory(response)
    with pytest.raises(FotMobNetworkError, match="16 MiB"):
        fetch_matches_by_date(REQUEST_DATE, connection_factory=factory, clock=lambda: OBSERVED)
    assert response.read_calls == []


def test_actual_body_above_limit_is_rejected_even_without_content_length():
    response = FakeHttpResponse(body=b"x" * (MAX_RESPONSE_BYTES + 1))
    factory, _ = fake_factory(response)
    with pytest.raises(FotMobNetworkError, match="16 MiB"):
        fetch_matches_by_date(REQUEST_DATE, connection_factory=factory, clock=lambda: OBSERVED)
    assert response.read_calls == [MAX_RESPONSE_BYTES + 1]


def test_exact_16_mib_boundary_is_accepted():
    prefix = b'{"leagues":[]}'
    body = prefix + b" " * (MAX_RESPONSE_BYTES - len(prefix))
    response = FakeHttpResponse(body=body, content_length=str(MAX_RESPONSE_BYTES))
    factory, _ = fake_factory(response)
    result = fetch_matches_by_date(
        REQUEST_DATE, connection_factory=factory, clock=lambda: OBSERVED
    )
    built = build_capture_manifest(
        result.body,
        request_date=REQUEST_DATE,
        observed_at=result.observed_at,
        http_status=result.status,
        content_type=result.content_type,
        network_acquisition_performed=True,
    )
    assert built.payload_byte_size == MAX_RESPONSE_BYTES


def test_clock_runs_after_body_acquisition():
    response = FakeHttpResponse()
    factory, _ = fake_factory(response)

    def clock():
        assert response.read_calls == [MAX_RESPONSE_BYTES + 1]
        return OBSERVED

    result = fetch_matches_by_date(REQUEST_DATE, connection_factory=factory, clock=clock)
    assert result.observed_at == OBSERVED


def test_transport_does_not_retry_after_failure():
    calls = []

    def failing_factory(*args, **kwargs):
        calls.append((args, kwargs))
        raise OSError("offline")

    with pytest.raises(FotMobNetworkError, match="OSError"):
        fetch_matches_by_date(REQUEST_DATE, connection_factory=failing_factory)
    assert len(calls) == 1


# Strict JSON parsing.
@pytest.mark.parametrize(
    "raw",
    [
        b"\xff",
        b'{"leagues":[],"leagues":[]}',
        b'{"leagues":[],"x":NaN}',
        b'{"leagues":[],"x":Infinity}',
        b'{"leagues":[],"x":-Infinity}',
        b'{"leagues":',
    ],
)
def test_invalid_utf8_duplicate_keys_constants_and_malformed_json_are_rejected(raw):
    with pytest.raises(FotMobCaptureError):
        strict_json_loads(raw)


@pytest.mark.parametrize("raw", [b"[]", b'"object"', b"null", b"1"])
def test_top_level_must_be_object(raw):
    with pytest.raises(FotMobCaptureError, match="top-level"):
        parse_fotmob_matches_payload(raw, request_date=REQUEST_DATE, observed_at=OBSERVED)


def test_leagues_key_is_required_and_must_be_list():
    with pytest.raises(FotMobCaptureError, match="contain leagues"):
        parse_fotmob_matches_payload(b"{}", request_date=REQUEST_DATE, observed_at=OBSERVED)
    with pytest.raises(FotMobCaptureError, match="leagues must be a list"):
        parse_fotmob_matches_payload(
            b'{"leagues":{}}', request_date=REQUEST_DATE, observed_at=OBSERVED
        )


def test_additional_top_level_keys_are_allowed():
    candidates, rejections = parse_fotmob_matches_payload(
        payload(extra={"date": REQUEST_DATE, "newField": {"x": 1}}),
        request_date=REQUEST_DATE,
        observed_at=OBSERVED,
    )
    assert len(candidates) == 1 and rejections == ()


# Candidate extraction.
def test_valid_fixture_candidate_contract():
    raw = payload()
    candidates, rejections = parse_fotmob_matches_payload(
        raw, request_date=REQUEST_DATE, observed_at=OBSERVED
    )
    assert rejections == ()
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.fixture_identifier == "FOTMOB:1234567"
    assert candidate.source_fixture_identifier == "1234567"
    assert candidate.home_team == "Home FC"
    assert candidate.away_team == "Away FC"
    assert candidate.competition == "Competition One"
    assert candidate.source_reference == build_source_reference(REQUEST_DATE)
    assert candidate.review_status is FotMobReviewStatus.UNREVIEWED


@pytest.mark.parametrize("bad_id", [True, False, 0, -1, 1.0, "1", None])
def test_match_id_must_be_exact_positive_integer(bad_id):
    candidates, rejections = parse_fotmob_matches_payload(
        payload(match(bad_id)), request_date=REQUEST_DATE, observed_at=OBSERVED
    )
    assert candidates == ()
    assert rejections[0].reason is FotMobFixtureRejectionReason.INVALID_MATCH_ID


@pytest.mark.parametrize("bad_home", [None, "", " Home", "Home ", True, 3, "x" * 257])
def test_invalid_home_team_is_rejected(bad_home):
    candidates, rejections = parse_fotmob_matches_payload(
        payload(match(home=bad_home)), request_date=REQUEST_DATE, observed_at=OBSERVED
    )
    assert candidates == ()
    assert rejections[0].reason is FotMobFixtureRejectionReason.INVALID_HOME_TEAM


@pytest.mark.parametrize("bad_away", [None, "", " Away", "Away ", True, [], "x" * 257])
def test_invalid_away_team_is_rejected(bad_away):
    candidates, rejections = parse_fotmob_matches_payload(
        payload(match(away=bad_away)), request_date=REQUEST_DATE, observed_at=OBSERVED
    )
    assert candidates == ()
    assert rejections[0].reason is FotMobFixtureRejectionReason.INVALID_AWAY_TEAM


@pytest.mark.parametrize("bad_league", [None, "", " League", "League ", True, {}, "x" * 257])
def test_invalid_competition_is_rejected(bad_league):
    candidates, rejections = parse_fotmob_matches_payload(
        payload(league=bad_league), request_date=REQUEST_DATE, observed_at=OBSERVED
    )
    assert candidates == ()
    assert rejections[0].reason is FotMobFixtureRejectionReason.INVALID_COMPETITION


@pytest.mark.parametrize(
    "bad_kickoff",
    [None, "", "2026-08-08T18:00:00", "not-time", True, 1],
)
def test_invalid_kickoff_is_rejected_without_fallback(bad_kickoff):
    candidates, rejections = parse_fotmob_matches_payload(
        payload(match(kickoff=bad_kickoff)),
        request_date=REQUEST_DATE,
        observed_at=OBSERVED,
    )
    assert candidates == ()
    assert rejections[0].reason is FotMobFixtureRejectionReason.INVALID_KICKOFF


def test_kickoff_and_observed_at_normalize_to_utc():
    candidates, _ = parse_fotmob_matches_payload(
        payload(match(kickoff="2026-08-08T20:00:00+02:00")),
        request_date=REQUEST_DATE,
        observed_at=OBSERVED.astimezone(dt.timezone(dt.timedelta(hours=1))),
    )
    assert candidates[0].kickoff == dt.datetime(2026, 8, 8, 18, tzinfo=UTC)
    assert candidates[0].observed_at == OBSERVED
    assert candidates[0].kickoff.tzinfo is UTC


def test_invalid_entry_does_not_fabricate_or_remove_valid_candidate():
    raw = payload(match(1), match(2, home=None), match(3, home="Third", away="Fourth"))
    candidates, rejections = parse_fotmob_matches_payload(
        raw, request_date=REQUEST_DATE, observed_at=OBSERVED
    )
    assert [item.fixture_identifier for item in candidates] == ["FOTMOB:1", "FOTMOB:3"]
    assert len(rejections) == 1
    text = canonical_candidate_jsonl_bytes(candidates).decode("utf-8")
    assert "Unknown" not in text


def test_invalid_league_and_match_containers_have_deterministic_indexes():
    raw = json.dumps(
        {
            "leagues": [
                None,
                {"name": "League", "matches": {}},
                {"name": "League 2", "matches": [None]},
            ]
        }
    ).encode()
    candidates, rejections = parse_fotmob_matches_payload(
        raw, request_date=REQUEST_DATE, observed_at=OBSERVED
    )
    assert candidates == ()
    assert [(item.league_index, item.match_index, item.reason.value) for item in rejections] == [
        (0, 0, "INVALID_LEAGUE"),
        (1, 0, "INVALID_MATCH_CONTAINER"),
        (2, 0, "INVALID_MATCH_CONTAINER"),
    ]


def test_candidate_ordering_is_by_kickoff_then_fixture_identifier():
    raw = payload(
        match(20, home="B", away="C", kickoff="2026-08-08T19:00:00Z"),
        match(10, home="A", away="D", kickoff="2026-08-08T18:00:00Z"),
        match(5, home="E", away="F", kickoff="2026-08-08T19:00:00Z"),
    )
    candidates, _ = parse_fotmob_matches_payload(
        raw, request_date=REQUEST_DATE, observed_at=OBSERVED
    )
    assert [item.fixture_identifier for item in candidates] == [
        "FOTMOB:10",
        "FOTMOB:20",
        "FOTMOB:5",
    ]


def test_duplicate_match_id_is_rejected_deterministically():
    raw = payload(match(7), match(7, home="Other", away="Else"))
    candidates, rejections = parse_fotmob_matches_payload(
        raw, request_date=REQUEST_DATE, observed_at=OBSERVED
    )
    assert len(candidates) == 1
    assert rejections == (
        FotMobFixtureRejection(0, 1, FotMobFixtureRejectionReason.INVALID_MATCH_ID),
    )


def test_all_candidates_are_unreviewed():
    candidates, _ = parse_fotmob_matches_payload(
        payload(match(1), match(2, home="C", away="D")),
        request_date=REQUEST_DATE,
        observed_at=OBSERVED,
    )
    assert candidates
    assert all(item.review_status is FotMobReviewStatus.UNREVIEWED for item in candidates)


# Raw evidence and manifest integrity.
def test_evidence_hash_and_size_are_exact_raw_response_values():
    raw = b'{"leagues":[]}\n'
    built = manifest(raw)
    assert built.payload_byte_size == len(raw)
    assert built.payload_sha256 == hashlib.sha256(raw).hexdigest()
    assert all(item.evidence_sha256 == built.payload_sha256 for item in built.candidates)


def test_candidate_evidence_hash_equals_raw_hash():
    raw = payload()
    built = manifest(raw)
    assert built.candidates[0].evidence_sha256 == sha256_bytes(raw)


def test_manifest_counts_equal_immutable_tuples():
    built = manifest(payload(match(1), match(2, home=None)))
    assert isinstance(built.candidates, tuple)
    assert isinstance(built.rejections, tuple)
    assert built.candidate_fixture_count == len(built.candidates) == 1
    assert built.rejected_fixture_count == len(built.rejections) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("candidate_fixture_count", 2),
        ("rejected_fixture_count", 2),
        ("candidate_fixture_count", True),
        ("payload_byte_size", True),
        ("payload_byte_size", -1),
    ],
)
def test_forged_counts_and_integer_fields_are_rejected(field, value):
    with pytest.raises(FotMobCaptureError):
        dataclasses.replace(manifest(), **{field: value})


@pytest.mark.parametrize("bad_sha", ["short", "A" * 64, "g" * 64, None])
def test_malformed_or_uppercase_payload_sha_is_rejected(bad_sha):
    with pytest.raises(FotMobCaptureError):
        dataclasses.replace(manifest(), payload_sha256=bad_sha)


@pytest.mark.parametrize(
    "bad_path",
    [
        "/tmp/response.json",
        "C:/capture/response.json",
        "C:\\capture\\response.json",
        "\\capture\\response.json",
        "../response.json",
        "capture/../response.json",
        "//server/share/response.json",
        "\\\\server\\share\\response.json",
    ],
)
def test_logical_evidence_paths_reject_absolute_root_and_traversal(bad_path):
    with pytest.raises(FotMobCaptureError):
        validate_logical_evidence_path(bad_path)


def test_relative_logical_evidence_path_is_accepted():
    assert validate_logical_evidence_path("response.json") == "response.json"
    assert validate_logical_evidence_path("capture/response.json") == "capture/response.json"


# Safety.
def test_exact_safety_keys_and_live_network_state():
    offline = manifest(network_acquisition_performed=False)
    live = manifest(network_acquisition_performed=True)
    expected = {
        "network_acquisition_performed",
        "scraping_performed",
        "browser_automation_performed",
        "credential_use_performed",
        "pricing_acquisition_performed",
        "probability_inference_authorized",
        "market_activation_authorized",
        "selection_authorized",
        "production_approval_authorized",
        "bet_authorized",
    }
    assert set(live.safety) == expected
    assert offline.safety["network_acquisition_performed"] is False
    assert live.safety["network_acquisition_performed"] is True
    assert all(value is False for key, value in live.safety.items() if key != "network_acquisition_performed")


@pytest.mark.parametrize("bad_network", [0, 1, None, "true"])
def test_network_safety_flag_requires_exact_bool(bad_network):
    with pytest.raises(FotMobCaptureError):
        manifest(network_acquisition_performed=bad_network)


def test_non_network_safety_flags_must_be_false_and_keys_exact():
    built = manifest()
    enabled = dict(built.safety)
    enabled["pricing_acquisition_performed"] = True
    with pytest.raises(FotMobCaptureError):
        dataclasses.replace(built, safety=enabled)
    missing = dict(built.safety)
    missing.pop("bet_authorized")
    with pytest.raises(FotMobCaptureError):
        dataclasses.replace(built, safety=missing)


def test_caller_safety_mutation_cannot_change_manifest():
    built = manifest()
    caller = dict(built.safety)
    detached = dataclasses.replace(built, safety=caller)
    before = canonical_manifest_bytes(detached)
    caller["bet_authorized"] = True
    assert detached.safety["bet_authorized"] is False
    assert canonical_manifest_bytes(detached) == before
    with pytest.raises(TypeError):
        detached.safety["bet_authorized"] = True


# Canonical serialization.
def test_manifest_canonical_bytes_are_deterministic_pretty_utf8_lf():
    built = manifest()
    first = canonical_manifest_bytes(built)
    second = canonical_manifest_bytes(built)
    assert first == second
    assert first.endswith(b"\n")
    assert b"\r\n" not in first
    assert first == (
        json.dumps(
            built.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def test_candidate_jsonl_is_deterministic_under_candidate_ordering():
    raw = payload(
        match(2, home="C", away="D"),
        match(1, home="A", away="B"),
    )
    candidates, _ = parse_fotmob_matches_payload(
        raw, request_date=REQUEST_DATE, observed_at=OBSERVED
    )
    assert canonical_candidate_jsonl_bytes(candidates) == canonical_candidate_jsonl_bytes(
        tuple(reversed(candidates))
    )
    lines = canonical_candidate_jsonl_bytes(candidates).splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)["review_status"] == "UNREVIEWED" for line in lines)


def test_json_object_key_order_does_not_change_parsed_fixture_semantics():
    ordered = payload()
    reordered = b'{"leagues":[{"matches":[{"status":{"utcTime":"2026-08-08T18:00:00+00:00"},"away":{"name":"Away FC"},"home":{"name":"Home FC"},"id":1234567}],"name":"Competition One"}]}'
    first, _ = parse_fotmob_matches_payload(
        ordered, request_date=REQUEST_DATE, observed_at=OBSERVED
    )
    second, _ = parse_fotmob_matches_payload(
        reordered, request_date=REQUEST_DATE, observed_at=OBSERVED
    )
    first_dict = first[0].to_dict()
    second_dict = second[0].to_dict()
    first_dict.pop("evidence_sha256")
    second_dict.pop("evidence_sha256")
    assert first_dict == second_dict
    assert first[0].evidence_sha256 != second[0].evidence_sha256


def test_manifest_round_trip_is_exact():
    built = manifest()
    loaded = manifest_from_mapping(strict_json_loads(canonical_manifest_bytes(built)))
    assert loaded == built
    assert canonical_manifest_bytes(loaded) == canonical_manifest_bytes(built)


# Output containment, durability, and verification.
def test_output_root_must_be_exact_allowed_location(tmp_path):
    repository = repo_root(tmp_path)
    assert validate_output_root(ALLOWED_OUTPUT_RELATIVE, repository_root=repository) == (
        repository / ALLOWED_OUTPUT_RELATIVE
    )
    with pytest.raises(FotMobCaptureError, match="output root"):
        validate_output_root(Path("other"), repository_root=repository)
    with pytest.raises(FotMobCaptureError, match="output root"):
        validate_output_root(tmp_path / "outside", repository_root=repository)


def test_write_preserves_raw_bytes_and_creates_exact_three_files(tmp_path):
    raw = b'{"leagues":[]}\n  '
    _, capture_directory, built = write_offline_capture(tmp_path, raw)
    assert {item.name for item in capture_directory.iterdir()} == {
        RESPONSE_FILENAME,
        CANDIDATE_FILENAME,
        MANIFEST_FILENAME,
    }
    assert (capture_directory / RESPONSE_FILENAME).read_bytes() == raw
    assert sha256_bytes((capture_directory / RESPONSE_FILENAME).read_bytes()) == built.payload_sha256
    assert not any(".tmp" in item.name for item in capture_directory.iterdir())


def test_pre_existing_capture_directory_is_rejected_without_overwrite(tmp_path):
    repository, capture_directory, _ = write_offline_capture(tmp_path)
    raw_before = (capture_directory / RESPONSE_FILENAME).read_bytes()
    with pytest.raises(FotMobCaptureError, match="already exists"):
        write_capture_directory(
            offline_response(),
            request_date=REQUEST_DATE,
            output_root=ALLOWED_OUTPUT_RELATIVE,
            repository_root=repository,
        )
    assert (capture_directory / RESPONSE_FILENAME).read_bytes() == raw_before


def test_normal_handled_write_failure_cleans_only_owned_capture(tmp_path, monkeypatch):
    repository = repo_root(tmp_path)
    root = repository / ALLOWED_OUTPUT_RELATIVE
    root.mkdir(parents=True)
    unrelated = root / "unrelated.txt"
    unrelated.write_text("keep", encoding="utf-8")
    original = capture_script._atomic_write
    calls = []

    def fail_second(path, content):
        calls.append(path.name)
        if len(calls) == 2:
            raise FotMobCaptureError("injected")
        return original(path, content)

    monkeypatch.setattr(capture_script, "_atomic_write", fail_second)
    with pytest.raises(FotMobCaptureError, match="injected"):
        write_capture_directory(
            offline_response(),
            request_date=REQUEST_DATE,
            output_root=ALLOWED_OUTPUT_RELATIVE,
            repository_root=repository,
        )
    assert unrelated.read_text(encoding="utf-8") == "keep"
    date_dir = root / REQUEST_DATE
    assert not date_dir.exists() or list(date_dir.iterdir()) == []


def test_offline_verifier_accepts_exact_capture(tmp_path):
    _, capture_directory, built = write_offline_capture(tmp_path)
    verified = verify_capture_directory(
        capture_directory,
        require_network_acquisition_performed=False,
    )
    assert verified == built


def test_offline_capture_cannot_satisfy_required_network_provenance(tmp_path):
    _, capture_directory, built = write_offline_capture(tmp_path)
    assert built.safety["network_acquisition_performed"] is False
    with pytest.raises(FotMobCaptureError, match="network acquisition provenance"):
        verify_capture_directory(
            capture_directory,
            require_network_acquisition_performed=True,
        )


def test_verifier_detects_modified_raw_evidence(tmp_path):
    _, capture_directory, _ = write_offline_capture(tmp_path)
    with (capture_directory / RESPONSE_FILENAME).open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(FotMobCaptureError, match="byte size mismatch"):
        verify_capture_directory(capture_directory)


def test_verifier_detects_modified_candidate_jsonl(tmp_path):
    _, capture_directory, _ = write_offline_capture(tmp_path)
    (capture_directory / CANDIDATE_FILENAME).write_bytes(b"{}\n")
    with pytest.raises(FotMobCaptureError, match="candidate JSON Lines"):
        verify_capture_directory(capture_directory)


def test_verifier_detects_modified_manifest_field(tmp_path):
    _, capture_directory, _ = write_offline_capture(tmp_path)
    manifest_path = capture_directory / MANIFEST_FILENAME
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    value["payload_byte_size"] += 1
    manifest_path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(FotMobCaptureError, match="byte size mismatch"):
        verify_capture_directory(capture_directory)


def test_verifier_rejects_extra_or_missing_files(tmp_path):
    _, capture_directory, _ = write_offline_capture(tmp_path)
    (capture_directory / "extra.txt").write_text("x")
    with pytest.raises(FotMobCaptureError, match="exactly"):
        verify_capture_directory(capture_directory)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink unsupported")
def test_symlink_raw_evidence_is_rejected(tmp_path):
    _, capture_directory, _ = write_offline_capture(tmp_path)
    raw = capture_directory / RESPONSE_FILENAME
    target = capture_directory / "raw-target"
    raw.rename(target)
    try:
        os.symlink(target, raw)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(FotMobCaptureError, match="exactly|non-symlink"):
        verify_capture_directory(capture_directory)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink unsupported")
def test_symlink_capture_directory_is_rejected(tmp_path):
    _, capture_directory, _ = write_offline_capture(tmp_path)
    link = tmp_path / "capture-link"
    try:
        os.symlink(capture_directory, link, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(FotMobCaptureError, match="non-symlink"):
        verify_capture_directory(link)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink unsupported")
def test_symlink_output_root_is_rejected(tmp_path):
    repository = repo_root(tmp_path)
    expected = repository / ALLOWED_OUTPUT_RELATIVE
    target = tmp_path / "elsewhere"
    target.mkdir()
    try:
        os.symlink(target, expected, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(FotMobCaptureError, match="symlink"):
        validate_output_root(ALLOWED_OUTPUT_RELATIVE, repository_root=repository)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink unsupported")
def test_dangling_symlink_output_root_is_rejected(tmp_path):
    repository = repo_root(tmp_path)
    expected = repository / ALLOWED_OUTPUT_RELATIVE
    missing_target = tmp_path / "missing-target"
    try:
        os.symlink(missing_target, expected, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(FotMobCaptureError, match="symlink"):
        validate_output_root(ALLOWED_OUTPUT_RELATIVE, repository_root=repository)


def test_capture_directory_date_and_source_reference_must_reconcile(tmp_path):
    _, capture_directory, _ = write_offline_capture(tmp_path)
    renamed_parent = capture_directory.parent.parent / "20260809"
    capture_directory.parent.rename(renamed_parent)
    moved = renamed_parent / capture_directory.name
    with pytest.raises(FotMobCaptureError, match="date"):
        verify_capture_directory(moved)


# Domain constructor invariants and fail-closed boundaries.
@pytest.mark.parametrize("bad", [True, -1, 1.0, "0"])
def test_rejection_indexes_are_exact_nonnegative_integers(bad):
    with pytest.raises(FotMobCaptureError):
        FotMobFixtureRejection(
            league_index=bad,
            match_index=0,
            reason=FotMobFixtureRejectionReason.INVALID_LEAGUE,
        )


def test_candidate_requires_exact_unreviewed_status_and_identity():
    candidate = manifest().candidates[0]
    with pytest.raises(FotMobCaptureError):
        dataclasses.replace(candidate, review_status="UNREVIEWED")
    with pytest.raises(FotMobCaptureError):
        dataclasses.replace(candidate, fixture_identifier="LOCAL:1234567")
    with pytest.raises(FotMobCaptureError):
        dataclasses.replace(candidate, source_fixture_identifier="001234567")
    with pytest.raises(FotMobCaptureError):
        dataclasses.replace(
            candidate,
            source_fixture_identifier="001234567",
            fixture_identifier="FOTMOB:001234567",
        )


def test_raw_evidence_is_written_before_semantic_manifest_build(tmp_path, monkeypatch):
    repository = repo_root(tmp_path)
    original = capture_script.build_capture_manifest

    def assert_raw_exists(raw_payload, **kwargs):
        root = repository / ALLOWED_OUTPUT_RELATIVE / REQUEST_DATE
        capture_directories = list(root.iterdir())
        assert len(capture_directories) == 1
        raw_path = capture_directories[0] / RESPONSE_FILENAME
        assert raw_path.is_file()
        assert raw_path.read_bytes() == raw_payload
        return original(raw_payload, **kwargs)

    monkeypatch.setattr(capture_script, "build_capture_manifest", assert_raw_exists)
    write_capture_directory(
        offline_response(),
        request_date=REQUEST_DATE,
        output_root=ALLOWED_OUTPUT_RELATIVE,
        repository_root=repository,
    )


def test_atomic_write_order_places_manifest_last(tmp_path, monkeypatch):
    repository = repo_root(tmp_path)
    original = capture_script._atomic_write
    order = []

    def record(path, content):
        order.append(path.name)
        return original(path, content)

    monkeypatch.setattr(capture_script, "_atomic_write", record)
    write_capture_directory(
        offline_response(),
        request_date=REQUEST_DATE,
        output_root=ALLOWED_OUTPUT_RELATIVE,
        repository_root=repository,
    )
    assert order == [RESPONSE_FILENAME, CANDIDATE_FILENAME, MANIFEST_FILENAME]


@pytest.mark.parametrize(
    "filename",
    [RESPONSE_FILENAME, CANDIDATE_FILENAME, MANIFEST_FILENAME],
)
def test_file_fsync_precedes_rename_and_directory_sync(
    tmp_path, monkeypatch, filename
):
    events = []
    original_replace = os.replace

    monkeypatch.setattr(
        capture_script.os,
        "fsync",
        lambda descriptor: events.append(("file_fsync", descriptor)),
    )

    def replace(source, destination):
        events.append(("replace", Path(destination).name))
        return original_replace(source, destination)

    monkeypatch.setattr(capture_script.os, "replace", replace)
    monkeypatch.setattr(
        capture_script,
        "_sync_directory",
        lambda directory: events.append(("directory_sync", Path(directory))),
    )
    destination = tmp_path / filename
    capture_script._atomic_write(destination, b"evidence")
    assert events[0][0] == "file_fsync"
    assert events[1] == ("replace", filename)
    assert events[2] == ("directory_sync", tmp_path)
    assert destination.read_bytes() == b"evidence"


def test_new_directories_are_synced_after_parent_publication(tmp_path, monkeypatch):
    repository = repo_root(tmp_path)
    events = []
    original_mkdir = Path.mkdir
    original_sync = capture_script._sync_directory

    def mkdir(path, *args, **kwargs):
        events.append(("mkdir", Path(path)))
        return original_mkdir(path, *args, **kwargs)

    def sync(path, *args, **kwargs):
        events.append(("sync", Path(path)))
        return original_sync(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)
    monkeypatch.setattr(capture_script, "_sync_directory", sync)
    capture_directory, _ = write_capture_directory(
        offline_response(),
        request_date=REQUEST_DATE,
        output_root=ALLOWED_OUTPUT_RELATIVE,
        repository_root=repository,
    )
    root = repository / ALLOWED_OUTPUT_RELATIVE
    date_directory = root / REQUEST_DATE
    required_transitions = [
        [("mkdir", root), ("sync", root.parent), ("sync", root)],
        [("mkdir", date_directory), ("sync", root), ("sync", date_directory)],
        [
            ("mkdir", capture_directory),
            ("sync", date_directory),
            ("sync", capture_directory),
        ],
    ]
    for transition in required_transitions:
        start = events.index(transition[0])
        assert events[start : start + 3] == transition


def test_capture_directory_is_synced_after_every_final_replace(tmp_path, monkeypatch):
    repository = repo_root(tmp_path)
    events = []
    original_replace = os.replace
    original_sync = capture_script._sync_directory

    def replace(source, destination):
        events.append(("replace", Path(destination)))
        return original_replace(source, destination)

    def sync(path, *args, **kwargs):
        events.append(("sync", Path(path)))
        return original_sync(path, *args, **kwargs)

    monkeypatch.setattr(capture_script.os, "replace", replace)
    monkeypatch.setattr(capture_script, "_sync_directory", sync)
    capture_directory, _ = write_capture_directory(
        offline_response(),
        request_date=REQUEST_DATE,
        output_root=ALLOWED_OUTPUT_RELATIVE,
        repository_root=repository,
    )
    replacements = [event for event in events if event[0] == "replace"]
    assert [path.name for _, path in replacements] == [
        RESPONSE_FILENAME,
        CANDIDATE_FILENAME,
        MANIFEST_FILENAME,
    ]
    for replacement in replacements:
        index = events.index(replacement)
        assert events[index + 1] == ("sync", capture_directory)


def test_parent_sync_failure_fails_and_cleans_created_date(tmp_path, monkeypatch):
    repository = repo_root(tmp_path)
    root = repository / ALLOWED_OUTPUT_RELATIVE
    root.mkdir(parents=True)
    date_directory = root / REQUEST_DATE
    original_sync = capture_script._sync_directory
    failed = False

    def sync(path, *args, **kwargs):
        nonlocal failed
        if Path(path) == root and date_directory.exists() and not failed:
            failed = True
            raise FotMobCaptureError("injected parent sync failure")
        return original_sync(path, *args, **kwargs)

    monkeypatch.setattr(capture_script, "_sync_directory", sync)
    with pytest.raises(FotMobCaptureError, match="parent sync failure"):
        write_capture_directory(
            offline_response(),
            request_date=REQUEST_DATE,
            output_root=ALLOWED_OUTPUT_RELATIVE,
            repository_root=repository,
        )
    assert not date_directory.exists()


def test_final_directory_sync_failure_never_returns_success(tmp_path, monkeypatch):
    repository = repo_root(tmp_path)
    root = repository / ALLOWED_OUTPUT_RELATIVE
    original_sync = capture_script._sync_directory
    failed = False

    def sync(path, *args, **kwargs):
        nonlocal failed
        directory = Path(path)
        raw = directory / RESPONSE_FILENAME
        if directory.name.startswith("20260808T") and raw.exists() and not failed:
            failed = True
            raise FotMobCaptureError("injected final directory sync failure")
        return original_sync(path, *args, **kwargs)

    monkeypatch.setattr(capture_script, "_sync_directory", sync)
    with pytest.raises(FotMobCaptureError, match="final directory sync failure"):
        write_capture_directory(
            offline_response(),
            request_date=REQUEST_DATE,
            output_root=ALLOWED_OUTPUT_RELATIVE,
            repository_root=repository,
        )
    date_directory = root / REQUEST_DATE
    assert not date_directory.exists()


def test_existing_directory_hierarchy_still_writes_capture(tmp_path):
    repository = repo_root(tmp_path)
    root = repository / ALLOWED_OUTPUT_RELATIVE
    date_directory = root / REQUEST_DATE
    date_directory.mkdir(parents=True)
    capture_directory, _ = write_capture_directory(
        offline_response(),
        request_date=REQUEST_DATE,
        output_root=ALLOWED_OUTPUT_RELATIVE,
        repository_root=repository,
    )
    assert capture_directory.parent == date_directory
    assert (capture_directory / MANIFEST_FILENAME).is_file()


def test_windows_directory_sync_dispatches_and_fails_closed(tmp_path, monkeypatch):
    calls = []

    def fail(path):
        calls.append(Path(path))
        raise FotMobCaptureError("Windows directory sync unavailable")

    monkeypatch.setattr(capture_script, "_sync_windows_directory", fail)
    with pytest.raises(FotMobCaptureError, match="Windows directory sync unavailable"):
        capture_script._sync_directory(tmp_path, platform_name="nt")
    assert calls == [tmp_path]


@pytest.mark.parametrize(
    "failure_target",
    ["temporary", "response", "candidate", "capture_directory", "date_directory"],
)
def test_incomplete_cleanup_is_reported_with_exact_owned_path(
    tmp_path, monkeypatch, failure_target
):
    repository = repo_root(tmp_path)
    root = repository / ALLOWED_OUTPUT_RELATIVE
    root.mkdir(parents=True)
    unrelated = root / "unrelated.txt"
    unrelated.write_text("preserve", encoding="utf-8")
    sibling = root / "sibling-capture"
    sibling.mkdir()
    sibling_file = sibling / "foreign.txt"
    sibling_file.write_text("preserve", encoding="utf-8")

    original_atomic = capture_script._atomic_write
    atomic_calls = 0

    def fail_during_write(path, content):
        nonlocal atomic_calls
        atomic_calls += 1
        if failure_target == "temporary" and atomic_calls == 1:
            path.with_name(f".{path.name}.tmp").write_bytes(b"partial")
            raise FotMobCaptureError("injected write failure")
        if failure_target in {"response", "capture_directory", "date_directory"} and atomic_calls == 2:
            raise FotMobCaptureError("injected write failure")
        if failure_target == "candidate" and atomic_calls == 3:
            raise FotMobCaptureError("injected write failure")
        return original_atomic(path, content)

    original_unlink = Path.unlink
    original_rmdir = Path.rmdir
    failed_path = []

    def unlink(path, *args, **kwargs):
        should_fail = (
            (failure_target == "temporary" and path.name == f".{RESPONSE_FILENAME}.tmp")
            or (failure_target == "response" and path.name == RESPONSE_FILENAME)
            or (failure_target == "candidate" and path.name == CANDIDATE_FILENAME)
        )
        if should_fail:
            failed_path.append(Path(path))
            raise OSError(f"injected unlink failure for {path}")
        return original_unlink(path, *args, **kwargs)

    def rmdir(path, *args, **kwargs):
        should_fail = (
            failure_target == "capture_directory" and path.name.startswith("20260808T")
        ) or (failure_target == "date_directory" and path.name == REQUEST_DATE)
        if should_fail:
            failed_path.append(Path(path))
            raise OSError(f"injected rmdir failure for {path}")
        return original_rmdir(path, *args, **kwargs)

    monkeypatch.setattr(capture_script, "_atomic_write", fail_during_write)
    monkeypatch.setattr(Path, "unlink", unlink)
    monkeypatch.setattr(Path, "rmdir", rmdir)
    with pytest.raises(FotMobCaptureError, match="cleanup incomplete") as error:
        write_capture_directory(
            offline_response(),
            request_date=REQUEST_DATE,
            output_root=ALLOWED_OUTPUT_RELATIVE,
            repository_root=repository,
        )
    assert "injected write failure" in str(error.value)
    assert failed_path
    assert str(failed_path[0]) in str(error.value)
    assert unrelated.read_text(encoding="utf-8") == "preserve"
    assert sibling_file.read_text(encoding="utf-8") == "preserve"


def test_candidate_and_rejection_tuples_must_be_immutable_and_sorted():
    built = manifest(payload(match(2), match(1, home="A", away="B")))
    with pytest.raises(FotMobCaptureError):
        dataclasses.replace(built, candidates=list(built.candidates))
    with pytest.raises(FotMobCaptureError):
        dataclasses.replace(built, candidates=tuple(reversed(built.candidates)))
    rejected = manifest(payload(match(1, home=None), match(2, away=None)))
    with pytest.raises(FotMobCaptureError):
        dataclasses.replace(rejected, rejections=tuple(reversed(rejected.rejections)))


def test_manifest_candidate_anchor_mismatches_fail_closed():
    built = manifest()
    candidate = built.candidates[0]
    mutations = [
        dataclasses.replace(candidate, evidence_sha256="b" * 64),
        dataclasses.replace(candidate, evidence_file_path="other.json"),
        dataclasses.replace(candidate, observed_at=OBSERVED + dt.timedelta(seconds=1)),
        dataclasses.replace(candidate, source_reference=build_source_reference("20260809")),
    ]
    for changed in mutations:
        with pytest.raises(FotMobCaptureError):
            dataclasses.replace(built, candidates=(changed,))


def test_public_boundaries_wrap_routine_invalid_types():
    for value in (None, {}, [], object()):
        with pytest.raises(FotMobCaptureError):
            parse_fotmob_matches_payload(
                value, request_date=REQUEST_DATE, observed_at=OBSERVED
            )
        with pytest.raises(FotMobCaptureError):
            strict_json_loads(value)
    with pytest.raises(FotMobCaptureError):
        manifest_from_mapping(None)


# Scope and disconnection.
def test_capture_modules_do_not_import_legacy_or_downstream_integrations():
    forbidden = {
        "api.fotmob_provider",
        "workers.fotmob_loader",
        "workers.fotmob_advanced_scraper",
        "workers.fotmob_bypass_client",
        "domain.fixture_intelligence",
        "domain.fixture_model_features",
        "intelligence.prediction_engine",
        "intelligence.match_analyst",
        "subprocess",
        "requests",
        "playwright",
        "selenium",
        "curl_cffi",
    }
    imports = set()
    for module in (capture_domain, capture_script):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
    assert forbidden.isdisjoint(imports)


def test_capture_output_has_no_catalog_intelligence_model_pricing_or_betting_fields():
    output = manifest().to_dict()
    data_keys = set(output) - {"safety"}
    candidate_keys = set(output["candidates"][0])
    forbidden = {
        "reviewed_at",
        "probability",
        "odds",
        "expected_value",
        "kelly",
        "market_ranking",
        "accumulator",
        "stake",
        "bet",
    }
    assert forbidden.isdisjoint(data_keys)
    assert forbidden.isdisjoint(candidate_keys)
    assert output["safety"]["probability_inference_authorized"] is False
    assert output["safety"]["pricing_acquisition_performed"] is False
    assert output["safety"]["selection_authorized"] is False
    assert output["safety"]["bet_authorized"] is False


def test_raw_candidate_schema_cannot_be_catalog_review_input():
    row = manifest().candidates[0].to_dict()
    assert row["review_status"] == "UNREVIEWED"
    assert "reviewed_at" not in row
    assert row["fixture_identifier"].startswith("FOTMOB:")


def test_transport_uses_one_transparent_user_agent_without_credentials():
    response = FakeHttpResponse()
    factory, calls = fake_factory(response)
    fetch_matches_by_date(REQUEST_DATE, connection_factory=factory, clock=lambda: OBSERVED)
    headers = calls[1][3]
    assert headers == {"User-Agent": "ATHENA/1.0", "Accept": "application/json"}
    assert not any(
        key.lower() in {"authorization", "cookie", "referer", "proxy-authorization"}
        for key in headers
    )


def test_source_capability_registry_is_not_rewritten_by_capture_contract():
    from domain.source_capabilities import (
        CapabilityAvailability,
        SOURCE_CAPABILITY_REGISTRY,
    )

    fotmob = SOURCE_CAPABILITY_REGISTRY["fotmob_unofficial"]
    assert fotmob.full_time_score is CapabilityAvailability.UNKNOWN
    assert fotmob.half_time_score is CapabilityAvailability.UNKNOWN
    assert fotmob.reliable_fixture_identity is CapabilityAvailability.UNKNOWN
