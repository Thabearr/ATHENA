from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
import importlib.util
from pathlib import Path

import pytest

from domain.fotmob_reviewed_match_details_probe import (
    ALLOWED_HOST,
    ALLOWED_PATH,
    DATASET_NAME,
    MAX_SAMPLE_BYTES,
    REQUEST_HEADERS,
    SCHEMA_VERSION,
    FotMobMatchDetailsProbePlan,
    FotMobReviewedMatchDetailsProbeError,
    ProbeTransportOutcome,
    build_match_details_probe_plan,
    canonical_match_details_probe_receipt_bytes,
    request_target,
    sha256_match_details_probe_receipt,
    source_match_id_from_fixture_identifier,
)
from domain.reviewed_fixture_catalog_admission import REVIEWED_SOURCE_CAPABILITY
from domain.reviewed_fixture_intelligence_bootstrap_artifact import (
    canonical_verified_bootstrap_artifact_receipt_bytes,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY
from scripts.probe_fotmob_reviewed_match_details import (
    REQUEST_TIMEOUT_SECONDS,
    probe_fotmob_reviewed_match_details,
)

UTC = datetime.timezone.utc
REQUEST_AT = datetime.datetime(2026, 8, 10, 6, 0, tzinfo=UTC)
OBSERVED_AT = datetime.datetime(2026, 8, 10, 6, 0, 1, tzinfo=UTC)
KICKOFF = datetime.datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def _upstream(tmp_path: Path, *, verified_at=None):
    helper_path = Path(__file__).with_name(
        "test_reviewed_fixture_intelligence_bootstrap_artifact.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_athena_pr48_probe_test_helper",
        helper_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PR #48 test helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    kwargs = {}
    if verified_at is not None:
        kwargs["verified_at"] = verified_at
    _, _, verified = module._verified(tmp_path, **kwargs)
    receipt_bytes = canonical_verified_bootstrap_artifact_receipt_bytes(verified)
    return verified, receipt_bytes


class _Clock:
    def __init__(self, *values: datetime.datetime):
        self._values = iter(values)

    def __call__(self):
        return next(self._values)


class _FakeResponse:
    def __init__(
        self,
        *,
        status=200,
        body=b'{"unreviewed":"sample"}',
        headers=None,
        read_error=None,
    ):
        self.status = status
        self.body = body
        self.headers = headers or {
            "Content-Type": "application/json; charset=utf-8",
            "Content-Length": str(len(body)),
        }
        self.read_error = read_error
        self.read_calls = []

    def getheader(self, name):
        return self.headers.get(name)

    def read(self, amount):
        self.read_calls.append(amount)
        if self.read_error is not None:
            raise self.read_error
        return self.body


class _FakeConnection:
    def __init__(self, response=None, response_error=None):
        self.response = response
        self.response_error = response_error
        self.putrequests = []
        self.headers = []
        self.endheaders_calls = 0
        self.closed = False

    def putrequest(self, method, target, *, skip_accept_encoding):
        self.putrequests.append((method, target, skip_accept_encoding))

    def putheader(self, name, value):
        self.headers.append((name, value))

    def endheaders(self):
        self.endheaders_calls += 1

    def getresponse(self):
        if self.response_error is not None:
            raise self.response_error
        return self.response

    def close(self):
        self.closed = True


def _factory_for(connection: _FakeConnection, calls: list[tuple]):
    def factory(host, port, *, timeout):
        calls.append((host, port, timeout))
        return connection

    return factory


def test_request_contract_is_exact_and_source_scoped(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)
    plan = build_match_details_probe_plan(
        verified,
        receipt_bytes,
        fixture_identifier="FOTMOB:1001",
        request_started_at=REQUEST_AT,
    )

    assert SCHEMA_VERSION == 1
    assert DATASET_NAME == "athena-fotmob-reviewed-match-details-probe-v1"
    assert ALLOWED_PATH == "/api/matchDetails"
    assert source_match_id_from_fixture_identifier("FOTMOB:1001") == "1001"
    assert request_target("1001") == "/api/matchDetails?matchId=1001"
    assert plan.fixture_identifier == "FOTMOB:1001"
    assert plan.source_match_id == "1001"
    assert plan.kickoff == KICKOFF
    assert plan.request_started_at == REQUEST_AT
    assert plan.host == ALLOWED_HOST
    assert plan.request_headers == REQUEST_HEADERS
    assert plan.x_mas_included is False
    assert plan.cookie_included is False
    assert plan.browser_impersonation is False
    assert plan.bootstrap_sha256 == verified.bootstrap_sha256
    assert plan.bootstrap_verification_receipt_sha256 == hashlib.sha256(
        receipt_bytes
    ).hexdigest()


def test_exact_pr48_receipt_bytes_and_exact_fixture_are_required(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)

    with pytest.raises(
        FotMobReviewedMatchDetailsProbeError,
        match="exact canonical PR #48 receipt",
    ):
        build_match_details_probe_plan(
            verified,
            receipt_bytes + b"\n",
            fixture_identifier="FOTMOB:1001",
            request_started_at=REQUEST_AT,
        )

    with pytest.raises(
        FotMobReviewedMatchDetailsProbeError,
        match="not an exact fixture",
    ):
        build_match_details_probe_plan(
            verified,
            receipt_bytes,
            fixture_identifier="FOTMOB:9999",
            request_started_at=REQUEST_AT,
        )


@pytest.mark.parametrize(
    "value",
    ["FOTMOB:01001", "fotmob:1001", "FOTMOB:+1001", "FOTMOB:0", 1001, None],
)
def test_noncanonical_fixture_identifiers_are_rejected(value) -> None:
    with pytest.raises(FotMobReviewedMatchDetailsProbeError):
        source_match_id_from_fixture_identifier(value)


@pytest.mark.parametrize("value", ["01001", "0", "+1001", 1001, None, ""])
def test_noncanonical_source_match_ids_are_rejected(value) -> None:
    with pytest.raises(FotMobReviewedMatchDetailsProbeError):
        request_target(value)


def test_probe_requires_explicit_exact_live_network_authorization(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)

    def forbidden_factory(*args, **kwargs):
        raise AssertionError("network factory must not be called")

    for value in (False, None, 1, "true"):
        with pytest.raises(
            FotMobReviewedMatchDetailsProbeError,
            match="execute_live_network=True",
        ):
            probe_fotmob_reviewed_match_details(
                verified_bootstrap_artifact=verified,
                verification_receipt_bytes=receipt_bytes,
                fixture_identifier="FOTMOB:1001",
                execute_live_network=value,
                connection_factory=forbidden_factory,
                clock=_Clock(REQUEST_AT),
            )


def test_successful_probe_makes_one_transparent_bounded_request(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)
    body = b'{"general":{"unreviewed":true}}'
    response = _FakeResponse(body=body)
    connection = _FakeConnection(response=response)
    calls = []

    execution = probe_fotmob_reviewed_match_details(
        verified_bootstrap_artifact=verified,
        verification_receipt_bytes=receipt_bytes,
        fixture_identifier="FOTMOB:1001",
        execute_live_network=True,
        connection_factory=_factory_for(connection, calls),
        clock=_Clock(REQUEST_AT, OBSERVED_AT),
    )

    assert calls == [(ALLOWED_HOST, 443, REQUEST_TIMEOUT_SECONDS)]
    assert connection.putrequests == [
        ("GET", "/api/matchDetails?matchId=1001", True)
    ]
    assert connection.headers == list(REQUEST_HEADERS)
    assert all(name.lower() not in {"cookie", "x-mas"} for name, _ in connection.headers)
    assert connection.endheaders_calls == 1
    assert response.read_calls == [MAX_SAMPLE_BYTES]
    assert connection.closed is True

    receipt = execution.receipt
    assert execution.operator_error is None
    assert receipt.transport_outcome is ProbeTransportOutcome.RESPONSE_RECEIVED
    assert receipt.status_code == 200
    assert receipt.content_type == "application/json; charset=utf-8"
    assert receipt.content_length == len(body)
    assert receipt.sample_size == len(body)
    assert receipt.sample_sha256 == hashlib.sha256(body).hexdigest()
    assert receipt.observed_at == OBSERVED_AT
    assert all(value is False for value in receipt.safety.values())
    assert receipt.safety["response_body_parsing_authorized"] is False
    assert receipt.safety["football_semantics_authorized"] is False
    assert receipt.safety["intelligence_fact_authorized"] is False

    canonical = canonical_match_details_probe_receipt_bytes(receipt)
    assert canonical.endswith(b"\n")
    assert canonical == canonical_match_details_probe_receipt_bytes(receipt)
    assert sha256_match_details_probe_receipt(receipt) == hashlib.sha256(
        canonical
    ).hexdigest()


def test_redirect_is_recorded_but_never_followed(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)
    response = _FakeResponse(
        status=302,
        body=b"",
        headers={
            "Content-Type": "text/html",
            "Content-Length": "0",
            "Location": "https://example.invalid/not-followed",
        },
    )
    connection = _FakeConnection(response=response)
    calls = []

    execution = probe_fotmob_reviewed_match_details(
        verified_bootstrap_artifact=verified,
        verification_receipt_bytes=receipt_bytes,
        fixture_identifier="FOTMOB:1001",
        execute_live_network=True,
        connection_factory=_factory_for(connection, calls),
        clock=_Clock(REQUEST_AT, OBSERVED_AT),
    )

    assert len(calls) == 1
    assert len(connection.putrequests) == 1
    assert execution.receipt.status_code == 302
    assert execution.receipt.location == "https://example.invalid/not-followed"


def test_transport_error_before_response_is_a_metadata_only_receipt(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)
    connection = _FakeConnection(response_error=TimeoutError("offline"))
    calls = []

    execution = probe_fotmob_reviewed_match_details(
        verified_bootstrap_artifact=verified,
        verification_receipt_bytes=receipt_bytes,
        fixture_identifier="FOTMOB:1001",
        execute_live_network=True,
        connection_factory=_factory_for(connection, calls),
        clock=_Clock(REQUEST_AT, OBSERVED_AT),
    )

    assert execution.receipt.transport_outcome is ProbeTransportOutcome.TRANSPORT_ERROR
    assert execution.receipt.status_code is None
    assert execution.receipt.sample_size == 0
    assert execution.receipt.sample_sha256 is None
    assert execution.operator_error == "transport error: TimeoutError"
    assert connection.closed is True


def test_response_sampling_error_is_not_downgraded_to_transport_error(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)
    response = _FakeResponse(read_error=OSError("read failed"))
    connection = _FakeConnection(response=response)

    with pytest.raises(
        FotMobReviewedMatchDetailsProbeError,
        match="response sampling failed: OSError",
    ):
        probe_fotmob_reviewed_match_details(
            verified_bootstrap_artifact=verified,
            verification_receipt_bytes=receipt_bytes,
            fixture_identifier="FOTMOB:1001",
            execute_live_network=True,
            connection_factory=_factory_for(connection, []),
            clock=_Clock(REQUEST_AT),
        )


def test_request_must_be_after_pr48_verification_and_strictly_before_kickoff(
    tmp_path: Path,
) -> None:
    verified, receipt_bytes = _upstream(tmp_path)

    with pytest.raises(
        FotMobReviewedMatchDetailsProbeError,
        match="must not predate PR #48 verification",
    ):
        build_match_details_probe_plan(
            verified,
            receipt_bytes,
            fixture_identifier="FOTMOB:1001",
            request_started_at=verified.verified_at - datetime.timedelta(microseconds=1),
        )

    with pytest.raises(
        FotMobReviewedMatchDetailsProbeError,
        match="strictly before fixture kickoff",
    ):
        build_match_details_probe_plan(
            verified,
            receipt_bytes,
            fixture_identifier="FOTMOB:1001",
            request_started_at=KICKOFF,
        )


def test_historical_pr48_receipt_verified_after_kickoff_cannot_drive_probe(
    tmp_path: Path,
) -> None:
    verified, receipt_bytes = _upstream(
        tmp_path,
        verified_at=KICKOFF + datetime.timedelta(seconds=1),
    )
    with pytest.raises(
        FotMobReviewedMatchDetailsProbeError,
        match="strictly before fixture kickoff",
    ):
        build_match_details_probe_plan(
            verified,
            receipt_bytes,
            fixture_identifier="FOTMOB:1001",
            request_started_at=verified.verified_at,
        )


def test_response_observation_at_kickoff_fails_closed_after_one_request(
    tmp_path: Path,
) -> None:
    verified, receipt_bytes = _upstream(tmp_path)
    connection = _FakeConnection(response=_FakeResponse())
    calls = []

    with pytest.raises(
        FotMobReviewedMatchDetailsProbeError,
        match="observed_at must be strictly before fixture kickoff",
    ):
        probe_fotmob_reviewed_match_details(
            verified_bootstrap_artifact=verified,
            verification_receipt_bytes=receipt_bytes,
            fixture_identifier="FOTMOB:1001",
            execute_live_network=True,
            connection_factory=_factory_for(connection, calls),
            clock=_Clock(REQUEST_AT, KICKOFF),
        )
    assert len(calls) == 1
    assert len(connection.putrequests) == 1
    assert connection.closed is True


def test_capability_revocation_blocks_new_probe_plan_but_not_historical_pr48_bytes(
    tmp_path: Path,
) -> None:
    verified, receipt_bytes = _upstream(tmp_path)
    historical = canonical_verified_bootstrap_artifact_receipt_bytes(verified)
    original = SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY]
    SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY] = dataclasses.replace(
        original,
        reliable_fixture_identity=CapabilityAvailability.UNKNOWN,
    )
    try:
        assert canonical_verified_bootstrap_artifact_receipt_bytes(verified) == historical
        with pytest.raises(
            FotMobReviewedMatchDetailsProbeError,
            match="failed current exact revalidation",
        ):
            build_match_details_probe_plan(
                verified,
                receipt_bytes,
                fixture_identifier="FOTMOB:1001",
                request_started_at=REQUEST_AT,
            )
    finally:
        SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY] = original


def test_mutated_pr48_fixture_set_is_rejected_before_network(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)
    fake = dataclasses.replace(
        verified.fixtures[0],
        fixture_identifier="FOTMOB:9999",
    )
    object.__setattr__(verified, "fixtures", (fake,))

    with pytest.raises(
        FotMobReviewedMatchDetailsProbeError,
        match="failed current exact revalidation",
    ):
        build_match_details_probe_plan(
            verified,
            receipt_bytes,
            fixture_identifier="FOTMOB:9999",
            request_started_at=REQUEST_AT,
        )


def test_invalid_content_length_fails_closed(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)
    response = _FakeResponse(headers={"Content-Length": "12.5"})
    connection = _FakeConnection(response=response)

    with pytest.raises(
        FotMobReviewedMatchDetailsProbeError,
        match="Content-Length",
    ):
        probe_fotmob_reviewed_match_details(
            verified_bootstrap_artifact=verified,
            verification_receipt_bytes=receipt_bytes,
            fixture_identifier="FOTMOB:1001",
            execute_live_network=True,
            connection_factory=_factory_for(connection, []),
            clock=_Clock(REQUEST_AT),
        )


def test_plan_rejects_browser_or_cookie_style_profiles(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)
    plan = build_match_details_probe_plan(
        verified,
        receipt_bytes,
        fixture_identifier="FOTMOB:1001",
        request_started_at=REQUEST_AT,
    )
    for changed in (
        dataclasses.replace(plan, x_mas_included=True),
        dataclasses.replace(plan, cookie_included=True),
        dataclasses.replace(plan, browser_impersonation=True),
    ):
        # dataclasses.replace validates during construction, so reaching this line
        # would itself indicate a fail-open regression.
        assert changed is None


def test_production_scope_has_no_bypass_or_downstream_semantic_imports() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = (
        root / "domain" / "fotmob_reviewed_match_details_probe.py",
        root / "scripts" / "probe_fotmob_reviewed_match_details.py",
    )
    forbidden = {
        "requests",
        "curl_cffi",
        "playwright",
        "workers.fotmob_bypass_client",
        "workers.fotmob_advanced_scraper",
        "domain.fixture_intelligence",
        "domain.fixture_model_features",
    }
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        assert not (imports & forbidden)
