from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
import http.client
import json
from pathlib import Path
from typing import Any

import pytest

from domain.fotmob_data_matches_probe import (
    ALLOWED_HOST,
    ALLOWED_PATH,
    DATASET_NAME,
    HTTPS_PORT,
    MAX_SAMPLE_BYTES,
    MEDIA_EXPECTATION,
    REQUEST_HEADERS,
    SCHEMA_VERSION,
    USER_AGENT,
    FotMobDataMatchesProbeError,
    FotMobDataMatchesProbeReceipt,
    ProbeTransportOutcome,
    build_response_receipt,
    build_transport_error_receipt,
    canonical_data_matches_probe_receipt_bytes,
    data_matches_probe_receipt_to_dict,
    ordered_query_parameters,
    request_headers,
    request_target,
    serialize_query,
    sha256_data_matches_probe_receipt,
    validate_ccode3,
    validate_request_date,
    validate_timezone,
)
from scripts import probe_fotmob_data_matches as cli


DATE = "20260815"
TIMEZONE = "UTC"
CCODE3 = "NGA"
TARGET = "/api/data/matches?date=20260815&timezone=UTC&ccode3=NGA"
OBSERVED = datetime.datetime(
    2026, 8, 15, 12, 34, 56, 123456, tzinfo=datetime.timezone.utc
)
SAFETY_KEYS = {
    "network_acquisition_authorized",
    "application_signature_reproduction_authorized",
    "cookie_use_authorized",
    "browser_impersonation_authorized",
    "fixture_capture_authorized",
    "fixture_parsing_authorized",
    "source_qualified",
    "fixture_promotion_authorized",
    "intelligence_authorized",
    "model_feature_authorized",
    "probability_authorized",
    "pricing_authorized",
    "selection_authorized",
    "bet_authorized",
}


class FakeResponse:
    def __init__(
        self,
        *,
        status: Any = 200,
        body: bytes = b'{"diagnostic":true}',
        headers: dict[str, Any] | None = None,
    ) -> None:
        self.status = status
        self.body = body
        self.headers = headers or {"Content-Type": "application/json"}
        self.read_sizes: list[int] = []

    def getheader(self, name: str) -> Any:
        return self.headers.get(name)

    def read(self, amount: int) -> bytes:
        self.read_sizes.append(amount)
        return self.body[:amount]


class FakeConnection:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.request_lines: list[tuple[str, str, bool, bool]] = []
        self.emitted_headers: list[tuple[str, str]] = []
        self.endheaders_calls = 0
        self.getresponse_calls = 0
        self.closed = False

    def putrequest(
        self,
        method: str,
        target: str,
        *,
        skip_host: bool = False,
        skip_accept_encoding: bool = False,
    ) -> None:
        self.request_lines.append((method, target, skip_host, skip_accept_encoding))

    def putheader(self, name: str, value: str) -> None:
        self.emitted_headers.append((name, value))

    def endheaders(self) -> None:
        self.endheaders_calls += 1

    def getresponse(self) -> FakeResponse:
        self.getresponse_calls += 1
        return self.response

    def close(self) -> None:
        self.closed = True


class ConnectionFactory:
    def __init__(
        self,
        response: FakeResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response or FakeResponse()
        self.error = error
        self.calls: list[tuple[str, int, int]] = []
        self.connections: list[FakeConnection] = []

    def __call__(self, host: str, port: int, *, timeout: int) -> FakeConnection:
        self.calls.append((host, port, timeout))
        if self.error is not None:
            raise self.error
        connection = FakeConnection(self.response)
        self.connections.append(connection)
        return connection


class RecordingSocket:
    def __init__(self) -> None:
        self.sent = bytearray()
        self.closed = False

    def sendall(self, content: bytes) -> None:
        self.sent.extend(content)

    def close(self) -> None:
        self.closed = True


class RecordingHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        host: str,
        port: int,
        *,
        timeout: int,
        response: FakeResponse,
    ) -> None:
        super().__init__(host, port, timeout=timeout)
        self.recording_socket = RecordingSocket()
        self.response = response

    def connect(self) -> None:
        self.sock = self.recording_socket  # type: ignore[assignment]

    def getresponse(self) -> FakeResponse:
        return self.response


def response_receipt(**changes: Any) -> FotMobDataMatchesProbeReceipt:
    values = {
        "request_date": DATE,
        "timezone": TIMEZONE,
        "ccode3": CCODE3,
        "status_code": 200,
        "content_type": "application/json; charset=utf-8",
        "content_length": 19,
        "location": None,
        "observed_at": OBSERVED,
        "sample": b'{"diagnostic":true}',
    }
    values.update(changes)
    return build_response_receipt(**values)


def run_probe(
    *,
    response: FakeResponse | None = None,
) -> tuple[cli._ProbeExecution, ConnectionFactory]:
    factory = ConnectionFactory(response)
    execution = cli.probe_fotmob_data_matches(
        request_date=DATE,
        timezone=TIMEZONE,
        ccode3=CCODE3,
        connection_factory=factory,
        clock=lambda: OBSERVED,
    )
    return execution, factory


def test_contract_constants_are_exact():
    receipt = response_receipt()
    assert DATASET_NAME == "athena-fotmob-data-matches-probe-v1"
    assert SCHEMA_VERSION == 1
    assert type(receipt.schema_version) is int
    assert ALLOWED_HOST == "www.fotmob.com"
    assert HTTPS_PORT == 443
    assert ALLOWED_PATH == "/api/data/matches"
    assert MAX_SAMPLE_BYTES == 4096
    assert MEDIA_EXPECTATION == "application/json"


@pytest.mark.parametrize("value", [True, 1.0, "1", 0, 2])
def test_schema_version_requires_exact_integer_one(value: Any):
    with pytest.raises(FotMobDataMatchesProbeError):
        dataclasses.replace(response_receipt(), schema_version=value)


def test_receipt_is_frozen_and_has_exact_fields():
    receipt = response_receipt()
    with pytest.raises(dataclasses.FrozenInstanceError):
        receipt.status_code = 404  # type: ignore[misc]
    assert [field.name for field in dataclasses.fields(receipt)] == [
        "schema_version",
        "dataset_name",
        "request_date",
        "timezone",
        "ccode3",
        "host",
        "request_target",
        "request_headers",
        "x_mas_included",
        "media_expectation",
        "transport_outcome",
        "status_code",
        "content_type",
        "content_length",
        "location",
        "observed_at",
        "sample_size",
        "sample_sha256",
        "safety",
    ]


def test_x_mas_included_is_exact_false():
    assert response_receipt().x_mas_included is False
    for value in (True, 0, 1, None, "false"):
        with pytest.raises(FotMobDataMatchesProbeError):
            dataclasses.replace(response_receipt(), x_mas_included=value)


def test_valid_date_round_trips():
    assert validate_request_date(DATE) == DATE


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-15",
        "2026081",
        "202608150",
        "20260230",
        " 20260815",
        "20260815 ",
        "20260815&x=1",
        True,
        None,
    ],
)
def test_invalid_dates_fail_closed(value: Any):
    with pytest.raises(FotMobDataMatchesProbeError):
        validate_request_date(value)


@pytest.mark.parametrize(
    "value",
    ["UTC", "Africa/Lagos", "America/New_York", "Etc/GMT+1", "A.B-C_D+E/F"],
)
def test_valid_timezones_are_accepted(value: str):
    assert validate_timezone(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        " UTC",
        "UTC ",
        "Africa//Lagos",
        "/UTC",
        "UTC/",
        "Africa Lagos",
        "UTC\n",
        "UTC?x",
        "UTC&x",
        "UTC=x",
        "UTC#x",
        "UTC%x",
        "A" * 65,
        None,
        True,
        1,
    ],
)
def test_invalid_timezones_fail_closed(value: Any):
    with pytest.raises(FotMobDataMatchesProbeError):
        validate_timezone(value)


def test_valid_ccode3_is_accepted():
    assert validate_ccode3("NGA") == "NGA"


@pytest.mark.parametrize(
    "value",
    ["nga", "NG", "NGAA", "N1A", "NGA_1", " NGA", True, None, 123],
)
def test_invalid_ccode3_fails_closed(value: Any):
    with pytest.raises(FotMobDataMatchesProbeError):
        validate_ccode3(value)


def test_ordered_query_parameters_are_exact():
    assert ordered_query_parameters(DATE, TIMEZONE, CCODE3) == (
        ("date", "20260815"),
        ("timezone", "UTC"),
        ("ccode3", "NGA"),
    )


def test_exact_utc_query_and_target():
    assert serialize_query(DATE, TIMEZONE, CCODE3) == (
        "date=20260815&timezone=UTC&ccode3=NGA"
    )
    assert request_target(DATE, TIMEZONE, CCODE3) == TARGET


@pytest.mark.parametrize(
    ("timezone", "encoded"),
    [
        ("America/New_York", "America%2FNew_York"),
        ("Etc/GMT+1", "Etc%2FGMT%2B1"),
    ],
)
def test_query_uses_urlsearchparams_compatible_encoding(timezone: str, encoded: str):
    assert serialize_query(DATE, timezone, CCODE3) == (
        f"date=20260815&timezone={encoded}&ccode3=NGA"
    )


def test_query_has_no_late_night_or_extra_parameters():
    target = request_target(DATE, TIMEZONE, CCODE3)
    assert target.count("&") == 2
    assert "includeNextDayLateNight" not in target
    assert target.startswith("/api/data/matches?")
    assert "/api/matches" not in target


def test_request_headers_are_exact_and_immutable():
    assert REQUEST_HEADERS == (
        ("Accept", "application/json"),
        ("User-Agent", "ATHENA/1.0"),
    )
    assert request_headers() is REQUEST_HEADERS
    assert USER_AGENT == "ATHENA/1.0"
    with pytest.raises(TypeError):
        REQUEST_HEADERS[0] = ("Accept", "text/plain")  # type: ignore[index]


@pytest.mark.parametrize(
    "headers",
    [
        (("Accept", "application/json"), ("x-mas", "forbidden")),
        (("Accept", "application/json"), ("Referer", "https://www.fotmob.com/")),
        (("Accept", "application/json"), ("Cookie", "a=b")),
        (("Accept", "application/json"), ("Authorization", "secret")),
        (("Accept", "application/json"), ("User-Agent", "Mozilla/5.0")),
        REQUEST_HEADERS + (("X-Test", "1"),),
    ],
)
def test_direct_receipt_rejects_unapproved_headers(headers):
    with pytest.raises(FotMobDataMatchesProbeError):
        dataclasses.replace(response_receipt(), request_headers=headers)


def test_probe_uses_exactly_one_fixed_request():
    execution, factory = run_probe()
    assert execution.receipt.transport_outcome is ProbeTransportOutcome.RESPONSE_RECEIVED
    assert factory.calls == [("www.fotmob.com", 443, cli.REQUEST_TIMEOUT_SECONDS)]
    connection = factory.connections[0]
    assert connection.request_lines == [("GET", TARGET, False, True)]
    assert connection.emitted_headers == list(REQUEST_HEADERS)
    assert connection.endheaders_calls == 1
    assert connection.getresponse_calls == 1
    assert connection.closed


def test_real_stdlib_wire_profile_is_exact():
    connections: list[RecordingHTTPSConnection] = []

    def factory(host: str, port: int, *, timeout: int) -> RecordingHTTPSConnection:
        connection = RecordingHTTPSConnection(
            host,
            port,
            timeout=timeout,
            response=FakeResponse(),
        )
        connections.append(connection)
        return connection

    cli.probe_fotmob_data_matches(
        request_date=DATE,
        timezone=TIMEZONE,
        ccode3=CCODE3,
        connection_factory=factory,
        clock=lambda: OBSERVED,
    )
    assert len(connections) == 1
    serialized = bytes(connections[0].recording_socket.sent)
    assert serialized.split(b"\r\n") == [
        f"GET {TARGET} HTTP/1.1".encode("ascii"),
        b"Host: www.fotmob.com",
        b"Accept: application/json",
        b"User-Agent: ATHENA/1.0",
        b"",
        b"",
    ]
    lowered = serialized.lower()
    for forbidden in (
        b"accept-encoding:",
        b"x-mas:",
        b"referer:",
        b"cookie:",
        b"authorization:",
        b"accept-language:",
        b"connection:",
        b"origin:",
        b"sec-fetch-",
        b"sec-ch-ua",
        b"fotmob-client:",
        b"x-requested-with:",
        b"mozilla/",
    ):
        assert forbidden not in lowered
    assert serialized.count(b"GET ") == 1


def test_cli_without_explicit_gate_performs_zero_network(capsys):
    factory = ConnectionFactory()
    with pytest.raises(SystemExit) as exc:
        cli.main(
            ["--date", DATE, "--timezone", TIMEZONE, "--ccode3", CCODE3],
            connection_factory=factory,
            clock=lambda: OBSERVED,
        )
    assert exc.value.code == 2
    assert factory.calls == []
    assert "--execute-live-network" in capsys.readouterr().err


def test_cli_parser_exposes_only_fixed_inputs_and_gate():
    actions = {
        option
        for action in cli.build_parser()._actions
        for option in action.option_strings
    }
    assert actions == {
        "-h",
        "--help",
        "--date",
        "--timezone",
        "--ccode3",
        "--execute-live-network",
    }


@pytest.mark.parametrize("status", [200, 401, 403, 404, 500, 599])
def test_diagnostic_response_statuses_are_valid(status: int):
    response = FakeResponse(status=status)
    execution, factory = run_probe(response=response)
    assert execution.receipt.status_code == status
    assert len(factory.calls) == 1
    assert factory.connections[0].getresponse_calls == 1


@pytest.mark.parametrize("status", [True, 99, 600, 200.0, "200", None])
def test_invalid_status_fails_closed(status: Any):
    with pytest.raises(FotMobDataMatchesProbeError):
        response_receipt(status_code=status)


def test_redirect_is_recorded_and_not_followed():
    response = FakeResponse(
        status=302,
        headers={
            "Content-Type": "text/html",
            "Location": "https://elsewhere.invalid/blocked",
        },
    )
    execution, factory = run_probe(response=response)
    assert execution.receipt.status_code == 302
    assert execution.receipt.location == "https://elsewhere.invalid/blocked"
    assert len(factory.calls) == 1
    assert factory.connections[0].getresponse_calls == 1


@pytest.mark.parametrize("value", [-1, True, 1.0, "12", [], {}])
def test_invalid_receipt_content_length_fails_closed(value: Any):
    with pytest.raises(FotMobDataMatchesProbeError):
        response_receipt(content_length=value)


@pytest.mark.parametrize("value", ["-1", "+1", " 1", "1 ", "1.0", True])
def test_invalid_wire_content_length_fails_closed(value: Any):
    response = FakeResponse(headers={"Content-Length": value})
    with pytest.raises(FotMobDataMatchesProbeError):
        run_probe(response=response)


def test_sample_is_capped_at_4096_and_hashes_exact_bytes():
    body = bytes(range(256)) * 20
    response = FakeResponse(body=body)
    execution, _ = run_probe(response=response)
    sample = body[:MAX_SAMPLE_BYTES]
    assert response.read_sizes == [MAX_SAMPLE_BYTES]
    assert execution.receipt.sample_size == MAX_SAMPLE_BYTES
    assert execution.receipt.sample_sha256 == hashlib.sha256(sample).hexdigest()


def test_short_and_empty_samples_have_exact_hashes():
    short, _ = run_probe(response=FakeResponse(body=b"abc"))
    empty, _ = run_probe(response=FakeResponse(body=b""))
    assert short.receipt.sample_size == 3
    assert short.receipt.sample_sha256 == hashlib.sha256(b"abc").hexdigest()
    assert empty.receipt.sample_size == 0
    assert empty.receipt.sample_sha256 == hashlib.sha256(b"").hexdigest()


def test_non_utf8_body_is_never_decoded_or_parsed():
    body = b"\xff\xfe\x00not-json"
    execution, _ = run_probe(response=FakeResponse(body=body))
    assert execution.receipt.sample_sha256 == hashlib.sha256(body).hexdigest()
    assert "body" not in execution.receipt.to_dict()


def test_body_is_not_printed_or_persisted(tmp_path: Path, monkeypatch, capfd):
    marker = b"unique-secret-response-marker"
    monkeypatch.chdir(tmp_path)
    factory = ConnectionFactory(FakeResponse(body=marker))
    before = list(tmp_path.rglob("*"))
    result = cli.main(
        [
            "--date",
            DATE,
            "--timezone",
            TIMEZONE,
            "--ccode3",
            CCODE3,
            "--execute-live-network",
        ],
        connection_factory=factory,
        clock=lambda: OBSERVED,
    )
    captured = capfd.readouterr()
    assert result == 0
    assert marker.decode("ascii") not in captured.out
    assert list(tmp_path.rglob("*")) == before


def test_transport_error_receipt_has_no_response_metadata_and_no_retry():
    factory = ConnectionFactory(error=OSError("secret DNS and local path"))
    execution = cli.probe_fotmob_data_matches(
        request_date=DATE,
        timezone=TIMEZONE,
        ccode3=CCODE3,
        connection_factory=factory,
        clock=lambda: OBSERVED,
    )
    assert len(factory.calls) == 1
    receipt = execution.receipt
    assert receipt.transport_outcome is ProbeTransportOutcome.TRANSPORT_ERROR
    assert receipt.status_code is None
    assert receipt.content_type is None
    assert receipt.content_length is None
    assert receipt.location is None
    assert receipt.sample_size == 0
    assert receipt.sample_sha256 is None
    assert execution.operator_error == "transport error: OSError"
    assert b"secret" not in canonical_data_matches_probe_receipt_bytes(receipt)


@pytest.mark.parametrize(
    "changes",
    [
        {"status_code": 200},
        {"content_type": "application/json"},
        {"content_length": 0},
        {"location": "https://example.invalid"},
        {"sample_size": 1},
        {"sample_sha256": "0" * 64},
    ],
)
def test_transport_error_cannot_claim_response_fields(changes: dict[str, Any]):
    receipt = build_transport_error_receipt(
        request_date=DATE,
        timezone=TIMEZONE,
        ccode3=CCODE3,
        observed_at=OBSERVED,
    )
    with pytest.raises(FotMobDataMatchesProbeError):
        dataclasses.replace(receipt, **changes)


def test_observed_at_is_timezone_aware_and_normalized():
    offset = datetime.timezone(datetime.timedelta(hours=1))
    receipt = response_receipt(observed_at=OBSERVED.astimezone(offset))
    assert receipt.observed_at == OBSERVED
    assert receipt.observed_at.tzinfo is datetime.timezone.utc


@pytest.mark.parametrize("value", [datetime.datetime(2026, 8, 15), None, "timestamp"])
def test_invalid_observed_at_fails_closed(value: Any):
    with pytest.raises(FotMobDataMatchesProbeError):
        response_receipt(observed_at=value)


def test_safety_contract_is_exact_detached_and_immutable():
    original = dict(response_receipt().safety)
    receipt = dataclasses.replace(response_receipt(), safety=original)
    canonical = canonical_data_matches_probe_receipt_bytes(receipt)
    assert set(receipt.safety) == SAFETY_KEYS
    assert all(type(value) is bool and value is False for value in receipt.safety.values())
    original["network_acquisition_authorized"] = True
    assert receipt.safety["network_acquisition_authorized"] is False
    assert canonical_data_matches_probe_receipt_bytes(receipt) == canonical
    with pytest.raises(TypeError):
        receipt.safety["network_acquisition_authorized"] = True  # type: ignore[index]


@pytest.mark.parametrize("value", [0, None, True, "false"])
def test_invalid_safety_values_fail_closed(value: Any):
    safety = dict(response_receipt().safety)
    safety["network_acquisition_authorized"] = value
    with pytest.raises(FotMobDataMatchesProbeError):
        dataclasses.replace(response_receipt(), safety=safety)


def test_serialization_helpers_are_exact_and_deterministic():
    receipt = response_receipt()
    payload = receipt.to_dict()
    assert data_matches_probe_receipt_to_dict(receipt) == payload
    assert json.loads(json.dumps(payload)) == payload
    first = canonical_data_matches_probe_receipt_bytes(receipt)
    second = canonical_data_matches_probe_receipt_bytes(dataclasses.replace(receipt))
    assert first == second
    assert first.endswith(b"\n")
    assert sha256_data_matches_probe_receipt(receipt) == hashlib.sha256(first).hexdigest()
    assert b'{"diagnostic":true}' not in first


def test_source_capability_registry_remains_unknown():
    from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY

    fotmob = SOURCE_CAPABILITY_REGISTRY["fotmob_unofficial"]
    assert all(
        value is CapabilityAvailability.UNKNOWN
        for value in (
            fotmob.full_time_score,
            fotmob.half_time_score,
            fotmob.event_timestamps,
            fotmob.reliable_fixture_identity,
            fotmob.historical_coverage,
            fotmob.freshness_metadata,
        )
    )


@pytest.mark.parametrize(
    "path",
    [
        Path("domain/fotmob_data_matches_probe.py"),
        Path("scripts/probe_fotmob_data_matches.py"),
    ],
)
def test_production_modules_have_no_downstream_or_unsafe_imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden = {
        "domain.fixture_catalog",
        "domain.fixture_intelligence",
        "domain.fixture_model_features",
        "intelligence.prediction_engine",
        "intelligence.match_analyst",
        "requests",
        "httpx",
        "aiohttp",
        "curl_cffi",
        "playwright",
        "selenium",
        "base64",
        "subprocess",
    }
    assert imported.isdisjoint(forbidden)


def test_no_signature_generation_or_embedded_signing_material_exists():
    production = (
        Path("domain/fotmob_data_matches_probe.py").read_text(encoding="utf-8")
        + Path("scripts/probe_fotmob_data_matches.py").read_text(encoding="utf-8")
    )
    lowered = production.lower()
    assert "hashlib.md5" not in lowered
    assert "b64encode" not in lowered
    assert "306d430a56a4e621a6fde71ec0d0f433af0c14a2" not in lowered
    assert "fotmob-client" not in lowered


def test_receipt_contains_no_fixture_probability_pricing_or_betting_fields():
    keys = set(response_receipt().to_dict())
    forbidden = ("body", "leagues", "matches", "probability", "odds", "price", "kelly", "stake")
    assert not any(fragment in key.lower() for key in keys for fragment in forbidden)
