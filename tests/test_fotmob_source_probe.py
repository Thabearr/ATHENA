from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from domain.fotmob_source_probe import (
    ALLOWED_HOST,
    DATASET_NAME,
    HTTPS_PORT,
    MAX_SAMPLE_BYTES,
    SCHEMA_VERSION,
    USER_AGENT,
    FotMobProbeRoute,
    FotMobSourceProbeError,
    FotMobSourceProbeReceipt,
    ProbeMediaExpectation,
    ProbeTransportOutcome,
    build_response_receipt,
    build_transport_error_receipt,
    canonical_source_probe_bytes,
    media_expectation_for_route,
    request_headers_for_route,
    request_target_for_route,
    sha256_source_probe_receipt,
    source_probe_receipt_to_dict,
    validate_probe_date,
)
from scripts import probe_fotmob_source as cli


DATE = "20260815"
OBSERVED = datetime.datetime(
    2026, 8, 15, 12, 34, 56, 123456, tzinfo=datetime.timezone.utc
)
SAFETY_KEYS = {
    "network_probe_authorized",
    "fixture_capture_authorized",
    "scraping_authorized",
    "browser_impersonation_authorized",
    "browser_automation_authorized",
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
        body: bytes = b'{"ok":true}',
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
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.closed = False

    def request(self, method: str, target: str, *, headers: dict[str, str]) -> None:
        self.requests.append((method, target, headers))

    def getresponse(self) -> FakeResponse:
        return self.response

    def close(self) -> None:
        self.closed = True


class ConnectionFactory:
    def __init__(self, response: FakeResponse | None = None, error: Exception | None = None):
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


def response_receipt(**changes: Any) -> FotMobSourceProbeReceipt:
    values = {
        "route": FotMobProbeRoute.MATCHES_API,
        "request_date": DATE,
        "status_code": 200,
        "content_type": "application/json; charset=utf-8",
        "content_length": 11,
        "location": None,
        "observed_at": OBSERVED,
        "sample": b'{"ok":true}',
    }
    values.update(changes)
    return build_response_receipt(**values)


def run_probe(
    route: FotMobProbeRoute = FotMobProbeRoute.MATCHES_API,
    *,
    response: FakeResponse | None = None,
) -> tuple[cli._ProbeExecution, ConnectionFactory]:
    factory = ConnectionFactory(response)
    result = cli.probe_fotmob_source(
        request_date=DATE,
        route=route,
        connection_factory=factory,
        clock=lambda: OBSERVED,
    )
    return result, factory


def test_contract_constants_are_exact():
    receipt = response_receipt()
    assert DATASET_NAME == "athena-fotmob-source-probe-v1"
    assert SCHEMA_VERSION == 1
    assert type(receipt.schema_version) is int
    assert receipt.dataset_name == DATASET_NAME
    assert ALLOWED_HOST == "www.fotmob.com"
    assert HTTPS_PORT == 443
    assert MAX_SAMPLE_BYTES == 4096


@pytest.mark.parametrize("value", [True, 1.0, "1", 0, 2])
def test_schema_version_requires_exact_integer_one(value: Any):
    with pytest.raises(FotMobSourceProbeError):
        dataclasses.replace(response_receipt(), schema_version=value)


def test_route_and_outcome_enums_are_exact():
    assert {item.value for item in FotMobProbeRoute} == {
        "matches_api",
        "date_web_page",
    }
    assert {item.value for item in ProbeTransportOutcome} == {
        "RESPONSE_RECEIVED",
        "TRANSPORT_ERROR",
    }
    assert {item.value for item in ProbeMediaExpectation} == {"JSON", "HTML"}


@pytest.mark.parametrize(
    ("route", "target", "expectation"),
    [
        (FotMobProbeRoute.MATCHES_API, "/api/matches?date=20260815", ProbeMediaExpectation.JSON),
        (FotMobProbeRoute.DATE_WEB_PAGE, "/?date=20260815", ProbeMediaExpectation.HTML),
    ],
)
def test_route_targets_and_media_expectations_are_fixed(route, target, expectation):
    assert request_target_for_route(route, DATE) == target
    assert media_expectation_for_route(route) is expectation


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
        "20260815?x=1",
        "2026/08/15",
        "202608%31",
        True,
        None,
    ],
)
def test_invalid_dates_fail_closed(value: Any):
    with pytest.raises(FotMobSourceProbeError):
        validate_probe_date(value)


def test_valid_date_round_trips():
    assert validate_probe_date(DATE) == DATE


@pytest.mark.parametrize(
    ("route", "expected"),
    [
        (
            FotMobProbeRoute.MATCHES_API,
            (("Accept", "application/json"), ("User-Agent", "ATHENA/1.0")),
        ),
        (
            FotMobProbeRoute.DATE_WEB_PAGE,
            (("Accept", "text/html,application/xhtml+xml"), ("User-Agent", "ATHENA/1.0")),
        ),
    ],
)
def test_request_profiles_are_exact_and_deterministic(route, expected):
    assert request_headers_for_route(route) == expected
    assert USER_AGENT == "ATHENA/1.0"


@pytest.mark.parametrize(
    "headers",
    [
        (("Accept", "application/json"), ("Referer", "https://www.fotmob.com/")),
        (("Accept", "application/json"), ("Cookie", "x=y")),
        (("Accept", "application/json"), ("Authorization", "Bearer secret")),
        (("Accept", "application/json"), ("User-Agent", "Mozilla/5.0")),
        (("Accept", "application/json"), ("User-Agent", "ATHENA/1.0"), ("X-Test", "1")),
    ],
)
def test_direct_receipt_rejects_nontransparent_headers(headers):
    with pytest.raises(FotMobSourceProbeError):
        dataclasses.replace(response_receipt(), request_headers=headers)


def test_request_header_tuple_is_immutable_and_detached():
    mutable = [list(item) for item in request_headers_for_route(FotMobProbeRoute.MATCHES_API)]
    receipt = response_receipt()
    mutable[0][1] = "text/plain"
    assert receipt.request_headers == request_headers_for_route(FotMobProbeRoute.MATCHES_API)
    with pytest.raises(TypeError):
        receipt.request_headers[0] = ("Accept", "text/plain")  # type: ignore[index]


@pytest.mark.parametrize("status", [200, 301, 302, 400, 401, 403, 404, 429, 500, 599])
def test_diagnostic_receipt_accepts_any_valid_http_status(status: int):
    assert response_receipt(status_code=status).status_code == status


@pytest.mark.parametrize("status", [True, 99, 600, 200.0, "200", None])
def test_invalid_status_fails_closed(status: Any):
    with pytest.raises(FotMobSourceProbeError):
        response_receipt(status_code=status)


@pytest.mark.parametrize("length", [-1, True, 1.0, "11", [], {}])
def test_invalid_content_length_fails_closed(length: Any):
    with pytest.raises(FotMobSourceProbeError):
        response_receipt(content_length=length)


def test_optional_location_is_preserved_but_does_not_change_route():
    receipt = response_receipt(status_code=302, location="https://example.invalid/elsewhere")
    assert receipt.location == "https://example.invalid/elsewhere"
    assert receipt.request_target == "/api/matches?date=20260815"


def test_transport_error_receipt_has_no_response_metadata():
    receipt = build_transport_error_receipt(
        route=FotMobProbeRoute.MATCHES_API,
        request_date=DATE,
        observed_at=OBSERVED,
    )
    assert receipt.transport_outcome is ProbeTransportOutcome.TRANSPORT_ERROR
    assert receipt.status_code is None
    assert receipt.content_type is None
    assert receipt.content_length is None
    assert receipt.location is None
    assert receipt.sample_size == 0
    assert receipt.sample_sha256 is None


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
        route=FotMobProbeRoute.MATCHES_API,
        request_date=DATE,
        observed_at=OBSERVED,
    )
    with pytest.raises(FotMobSourceProbeError):
        dataclasses.replace(receipt, **changes)


def test_response_received_requires_status_and_sample_sha():
    receipt = response_receipt()
    with pytest.raises(FotMobSourceProbeError):
        dataclasses.replace(receipt, status_code=None)
    with pytest.raises(FotMobSourceProbeError):
        dataclasses.replace(receipt, sample_sha256=None)


def test_normal_invalid_input_uses_contract_error():
    with pytest.raises(FotMobSourceProbeError):
        request_target_for_route("matches_api", DATE)
    with pytest.raises(FotMobSourceProbeError):
        build_response_receipt(
            route=FotMobProbeRoute.MATCHES_API,
            request_date=DATE,
            status_code=200,
            content_type=None,
            content_length=None,
            location=None,
            observed_at=OBSERVED,
            sample="not bytes",  # type: ignore[arg-type]
        )


def test_sampling_reads_exactly_at_most_4096_and_hashes_exact_bytes():
    body = bytes(range(256)) * 20
    response = FakeResponse(body=body)
    execution, factory = run_probe(response=response)
    sampled = body[:MAX_SAMPLE_BYTES]
    assert response.read_sizes == [MAX_SAMPLE_BYTES]
    assert execution.receipt.sample_size == MAX_SAMPLE_BYTES
    assert execution.receipt.sample_sha256 == hashlib.sha256(sampled).hexdigest()
    assert factory.connections[0].closed


def test_short_body_and_empty_body_have_exact_deterministic_fingerprints():
    short, _ = run_probe(response=FakeResponse(body=b"abc"))
    empty, _ = run_probe(response=FakeResponse(body=b""))
    assert short.receipt.sample_size == 3
    assert short.receipt.sample_sha256 == hashlib.sha256(b"abc").hexdigest()
    assert empty.receipt.sample_size == 0
    assert empty.receipt.sample_sha256 == hashlib.sha256(b"").hexdigest()


def test_body_never_appears_in_receipt_or_serialization():
    secret_body = b"unique-body-that-must-not-be-stored"
    execution, _ = run_probe(response=FakeResponse(body=secret_body))
    payload = execution.receipt.to_dict()
    assert "body" not in payload
    assert secret_body not in canonical_source_probe_bytes(execution.receipt)


def test_probe_performs_no_filesystem_write(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = list(tmp_path.rglob("*"))
    run_probe()
    assert list(tmp_path.rglob("*")) == before


def test_cli_without_explicit_gate_performs_zero_network(capsys):
    factory = ConnectionFactory()
    with pytest.raises(SystemExit) as exc:
        cli.main(
            ["--date", DATE, "--route", "matches_api"],
            connection_factory=factory,
            clock=lambda: OBSERVED,
        )
    assert exc.value.code == 2
    assert factory.calls == []
    assert "--execute-live-network" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("route", "target", "accept"),
    [
        ("matches_api", "/api/matches?date=20260815", "application/json"),
        ("date_web_page", "/?date=20260815", "text/html,application/xhtml+xml"),
    ],
)
def test_each_route_uses_exactly_one_fixed_https_request(route, target, accept):
    enum_route = FotMobProbeRoute(route)
    execution, factory = run_probe(enum_route)
    assert execution.receipt.transport_outcome is ProbeTransportOutcome.RESPONSE_RECEIVED
    assert factory.calls == [("www.fotmob.com", 443, cli.REQUEST_TIMEOUT_SECONDS)]
    assert factory.connections[0].requests == [
        ("GET", target, {"Accept": accept, "User-Agent": "ATHENA/1.0"})
    ]


@pytest.mark.parametrize("status", [301, 302, 403, 404, 429, 500])
def test_http_failure_or_redirect_is_recorded_without_retry_or_follow(status: int):
    response = FakeResponse(
        status=status,
        headers={
            "Content-Type": "text/html",
            "Location": "https://elsewhere.invalid/redirect",
        },
    )
    execution, factory = run_probe(response=response)
    assert execution.receipt.status_code == status
    assert execution.receipt.location == "https://elsewhere.invalid/redirect"
    assert len(factory.calls) == 1
    assert len(factory.connections[0].requests) == 1


def test_transport_failure_returns_bounded_receipt_and_never_retries():
    factory = ConnectionFactory(error=OSError("secret DNS internals and local path"))
    execution = cli.probe_fotmob_source(
        request_date=DATE,
        route=FotMobProbeRoute.MATCHES_API,
        connection_factory=factory,
        clock=lambda: OBSERVED,
    )
    assert len(factory.calls) == 1
    assert execution.receipt.transport_outcome is ProbeTransportOutcome.TRANSPORT_ERROR
    assert execution.operator_error == "transport error: OSError"
    serialized = canonical_source_probe_bytes(execution.receipt)
    assert b"secret" not in serialized
    assert b"DNS" not in serialized


def test_parser_exposes_no_arbitrary_url_header_or_proxy_option():
    actions = {option for action in cli.build_parser()._actions for option in action.option_strings}
    assert actions == {"-h", "--help", "--date", "--route", "--execute-live-network"}


def test_observed_at_is_timezone_aware_and_normalized_to_utc():
    offset = datetime.timezone(datetime.timedelta(hours=1))
    receipt = response_receipt(observed_at=OBSERVED.astimezone(offset))
    assert receipt.observed_at == OBSERVED
    assert receipt.observed_at.tzinfo is datetime.timezone.utc


@pytest.mark.parametrize("value", [datetime.datetime(2026, 8, 15), None, "2026-08-15T00:00:00Z"])
def test_invalid_observed_at_fails_closed(value: Any):
    with pytest.raises(FotMobSourceProbeError):
        response_receipt(observed_at=value)


def test_safety_keys_and_values_are_exact():
    receipt = response_receipt()
    assert set(receipt.safety) == SAFETY_KEYS
    assert all(type(value) is bool and value is False for value in receipt.safety.values())


@pytest.mark.parametrize("value", [0, None, True, "false"])
def test_invalid_safety_values_fail_closed(value: Any):
    safety = dict(response_receipt().safety)
    safety["network_probe_authorized"] = value
    with pytest.raises(FotMobSourceProbeError):
        dataclasses.replace(response_receipt(), safety=safety)


def test_safety_mapping_is_detached_and_immutable():
    original = dict(response_receipt().safety)
    receipt = dataclasses.replace(response_receipt(), safety=original)
    canonical = canonical_source_probe_bytes(receipt)
    original["network_probe_authorized"] = True
    assert receipt.safety["network_probe_authorized"] is False
    assert canonical_source_probe_bytes(receipt) == canonical
    with pytest.raises(TypeError):
        receipt.safety["network_probe_authorized"] = True  # type: ignore[index]


def test_serialization_helpers_are_exact_and_deterministic():
    receipt = response_receipt()
    payload = receipt.to_dict()
    assert source_probe_receipt_to_dict(receipt) == payload
    assert json.loads(json.dumps(payload)) == payload
    first = canonical_source_probe_bytes(receipt)
    second = canonical_source_probe_bytes(dataclasses.replace(receipt))
    assert first == second
    assert first.endswith(b"\n")
    assert sha256_source_probe_receipt(receipt) == hashlib.sha256(first).hexdigest()


def test_receipt_has_exact_field_contract():
    assert [field.name for field in dataclasses.fields(FotMobSourceProbeReceipt)] == [
        "schema_version",
        "dataset_name",
        "route",
        "request_date",
        "host",
        "request_target",
        "request_headers",
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


def test_source_capability_registry_remains_unknown():
    from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY

    fotmob = SOURCE_CAPABILITY_REGISTRY["fotmob_unofficial"]
    assert fotmob.full_time_score is CapabilityAvailability.UNKNOWN
    assert fotmob.half_time_score is CapabilityAvailability.UNKNOWN
    assert fotmob.event_timestamps is CapabilityAvailability.UNKNOWN
    assert fotmob.reliable_fixture_identity is CapabilityAvailability.UNKNOWN
    assert fotmob.historical_coverage is CapabilityAvailability.UNKNOWN
    assert fotmob.freshness_metadata is CapabilityAvailability.UNKNOWN


@pytest.mark.parametrize(
    "path",
    [Path("domain/fotmob_source_probe.py"), Path("scripts/probe_fotmob_source.py")],
)
def test_probe_modules_have_no_downstream_or_unsafe_imports(path: Path):
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
        "domain.fotmob_capture",
        "scripts.capture_fotmob_matches",
        "intelligence.prediction_engine",
        "intelligence.match_analyst",
        "subprocess",
        "requests",
        "playwright",
        "selenium",
    }
    assert imported.isdisjoint(forbidden)


def test_receipt_contract_contains_no_capture_probability_pricing_or_betting_fields():
    keys = set(response_receipt().to_dict())
    forbidden_fragments = (
        "body",
        "fixture",
        "probability",
        "odds",
        "price",
        "edge",
        "kelly",
        "selection",
        "stake",
        "bet",
    )
    assert not any(fragment in key.lower() for key in keys for fragment in forbidden_fragments)


def test_fixed_request_profile_contains_no_forbidden_header():
    for route in FotMobProbeRoute:
        headers = dict(request_headers_for_route(route))
        lowered = {key.lower() for key in headers}
        assert lowered == {"accept", "user-agent"}
        assert headers["User-Agent"] == "ATHENA/1.0"
