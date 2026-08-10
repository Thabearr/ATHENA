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
    DATASET_NAME,
    MAX_SAMPLE_BYTES,
    REQUEST_HEADERS,
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
SEND_AT = REQUEST_AT + datetime.timedelta(microseconds=500_000)
OBSERVED_AT = REQUEST_AT + datetime.timedelta(seconds=1)
KICKOFF = datetime.datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def _upstream(tmp_path: Path, *, verified_at=None):
    helper = Path(__file__).with_name(
        "test_reviewed_fixture_intelligence_bootstrap_artifact.py"
    )
    spec = importlib.util.spec_from_file_location("_athena_pr48_helper", helper)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PR #48 helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    kwargs = {} if verified_at is None else {"verified_at": verified_at}
    _, _, verified = module._verified(tmp_path, **kwargs)
    return verified, canonical_verified_bootstrap_artifact_receipt_bytes(verified)


class _Clock:
    def __init__(self, *values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


class _Response:
    def __init__(self, *, status=200, body=b'{"unreviewed":true}', headers=None, error=None):
        self.status = status
        self.body = body
        self.headers = headers or {
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        }
        self.error = error
        self.read_calls = []

    def getheader(self, name):
        return self.headers.get(name)

    def read(self, amount):
        self.read_calls.append(amount)
        if self.error is not None:
            raise self.error
        return self.body


class _Connection:
    def __init__(self, *, response=None, response_error=None):
        self.response = response
        self.response_error = response_error
        self.requests = []
        self.headers = []
        self.endheaders_calls = 0
        self.closed = False

    def putrequest(self, method, target, *, skip_accept_encoding):
        self.requests.append((method, target, skip_accept_encoding))

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


def _factory(connection, calls):
    def build(host, port, *, timeout):
        calls.append((host, port, timeout))
        return connection

    return build


def test_plan_is_self_validating_and_exactly_anchored_to_pr48(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)
    plan = build_match_details_probe_plan(
        verified,
        receipt_bytes,
        fixture_identifier="FOTMOB:1001",
        request_started_at=REQUEST_AT,
    )
    assert DATASET_NAME == "athena-fotmob-reviewed-match-details-probe-v1"
    assert source_match_id_from_fixture_identifier("FOTMOB:1001") == "1001"
    assert request_target("1001") == "/api/matchDetails?matchId=1001"
    assert plan.verified_bootstrap_artifact is not None
    assert plan.verification_receipt_bytes == receipt_bytes
    assert plan.fixture_identifier == "FOTMOB:1001"
    assert plan.source_match_id == "1001"
    assert plan.kickoff == KICKOFF
    assert plan.host == ALLOWED_HOST
    assert plan.request_headers == REQUEST_HEADERS
    assert plan.bootstrap_sha256 == verified.bootstrap_sha256
    assert plan.bootstrap_verification_receipt_sha256 == hashlib.sha256(
        receipt_bytes
    ).hexdigest()
    assert plan.x_mas_included is False
    assert plan.cookie_included is False
    assert plan.browser_impersonation is False

    with pytest.raises(FotMobReviewedMatchDetailsProbeError, match="bootstrap_sha256"):
        dataclasses.replace(plan, bootstrap_sha256="f" * 64)
    with pytest.raises(FotMobReviewedMatchDetailsProbeError, match="not an exact fixture"):
        dataclasses.replace(
            plan,
            fixture_identifier="FOTMOB:9999",
            source_match_id="9999",
        )


def test_wrong_receipt_fixture_or_noncanonical_id_fails_closed(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)
    with pytest.raises(FotMobReviewedMatchDetailsProbeError, match="exact canonical PR #48"):
        build_match_details_probe_plan(
            verified,
            receipt_bytes + b"\n",
            fixture_identifier="FOTMOB:1001",
            request_started_at=REQUEST_AT,
        )
    with pytest.raises(FotMobReviewedMatchDetailsProbeError, match="not an exact fixture"):
        build_match_details_probe_plan(
            verified,
            receipt_bytes,
            fixture_identifier="FOTMOB:9999",
            request_started_at=REQUEST_AT,
        )
    for value in ("FOTMOB:01001", "fotmob:1001", "FOTMOB:+1001", "FOTMOB:0"):
        with pytest.raises(FotMobReviewedMatchDetailsProbeError):
            source_match_id_from_fixture_identifier(value)
    for value in ("01001", "0", "+1001", 1001):
        with pytest.raises(FotMobReviewedMatchDetailsProbeError):
            request_target(value)


def test_current_timing_gate_is_after_pr48_and_strictly_pre_kickoff(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)
    with pytest.raises(FotMobReviewedMatchDetailsProbeError, match="must not predate PR #48"):
        build_match_details_probe_plan(
            verified,
            receipt_bytes,
            fixture_identifier="FOTMOB:1001",
            request_started_at=verified.verified_at - datetime.timedelta(microseconds=1),
        )
    with pytest.raises(FotMobReviewedMatchDetailsProbeError, match="strictly before fixture kickoff"):
        build_match_details_probe_plan(
            verified,
            receipt_bytes,
            fixture_identifier="FOTMOB:1001",
            request_started_at=KICKOFF,
        )
    historical, historical_bytes = _upstream(
        tmp_path / "historical",
        verified_at=KICKOFF + datetime.timedelta(seconds=1),
    )
    with pytest.raises(FotMobReviewedMatchDetailsProbeError, match="strictly before fixture kickoff"):
        build_match_details_probe_plan(
            historical,
            historical_bytes,
            fixture_identifier="FOTMOB:1001",
            request_started_at=historical.verified_at,
        )


def test_probe_requires_explicit_network_authorization_before_connection(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("connection must not be created")

    for value in (False, None, 1, "true"):
        with pytest.raises(FotMobReviewedMatchDetailsProbeError, match="execute_live_network=True"):
            probe_fotmob_reviewed_match_details(
                verified_bootstrap_artifact=verified,
                verification_receipt_bytes=receipt_bytes,
                fixture_identifier="FOTMOB:1001",
                execute_live_network=value,
                connection_factory=forbidden,
                clock=_Clock(REQUEST_AT),
            )


def test_one_transparent_request_returns_only_bounded_diagnostic_receipt(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)
    body = b'{"general":{"still_unreviewed":true}}'
    response = _Response(body=body)
    connection = _Connection(response=response)
    calls = []
    execution = probe_fotmob_reviewed_match_details(
        verified_bootstrap_artifact=verified,
        verification_receipt_bytes=receipt_bytes,
        fixture_identifier="FOTMOB:1001",
        execute_live_network=True,
        connection_factory=_factory(connection, calls),
        clock=_Clock(REQUEST_AT, SEND_AT, OBSERVED_AT),
    )
    assert calls == [(ALLOWED_HOST, 443, REQUEST_TIMEOUT_SECONDS)]
    assert connection.requests == [("GET", "/api/matchDetails?matchId=1001", True)]
    assert connection.headers == list(REQUEST_HEADERS)
    assert all(name.lower() not in {"cookie", "x-mas"} for name, _ in connection.headers)
    assert connection.endheaders_calls == 1
    assert response.read_calls == [MAX_SAMPLE_BYTES]
    assert connection.closed is True

    receipt = execution.receipt
    assert execution.operator_error is None
    assert receipt.transport_outcome is ProbeTransportOutcome.RESPONSE_RECEIVED
    assert receipt.status_code == 200
    assert receipt.sample_size == len(body)
    assert receipt.sample_sha256 == hashlib.sha256(body).hexdigest()
    assert all(value is False for value in receipt.safety.values())
    assert receipt.safety["response_body_parsing_authorized"] is False
    assert receipt.safety["source_qualification_authorized"] is False
    assert receipt.safety["intelligence_fact_authorized"] is False
    canonical = canonical_match_details_probe_receipt_bytes(receipt)
    assert canonical.endswith(b"\n")
    assert sha256_match_details_probe_receipt(receipt) == hashlib.sha256(canonical).hexdigest()


def test_final_pre_send_gate_blocks_kickoff_crossing_before_bytes_are_sent(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)
    connection = _Connection(response=_Response())
    with pytest.raises(FotMobReviewedMatchDetailsProbeError, match="request_send_at must be strictly before"):
        probe_fotmob_reviewed_match_details(
            verified_bootstrap_artifact=verified,
            verification_receipt_bytes=receipt_bytes,
            fixture_identifier="FOTMOB:1001",
            execute_live_network=True,
            connection_factory=_factory(connection, []),
            clock=_Clock(REQUEST_AT, KICKOFF),
        )
    assert connection.endheaders_calls == 0
    assert connection.closed is True


def test_redirect_is_recorded_not_followed_and_transport_errors_are_distinct(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)
    redirect = _Response(
        status=302,
        body=b"",
        headers={"Content-Length": "0", "Location": "https://example.invalid/no-follow"},
    )
    connection = _Connection(response=redirect)
    calls = []
    result = probe_fotmob_reviewed_match_details(
        verified_bootstrap_artifact=verified,
        verification_receipt_bytes=receipt_bytes,
        fixture_identifier="FOTMOB:1001",
        execute_live_network=True,
        connection_factory=_factory(connection, calls),
        clock=_Clock(REQUEST_AT, SEND_AT, OBSERVED_AT),
    )
    assert len(calls) == 1
    assert len(connection.requests) == 1
    assert connection.endheaders_calls == 1
    assert result.receipt.status_code == 302
    assert result.receipt.location == "https://example.invalid/no-follow"

    failed = _Connection(response_error=TimeoutError("offline"))
    result = probe_fotmob_reviewed_match_details(
        verified_bootstrap_artifact=verified,
        verification_receipt_bytes=receipt_bytes,
        fixture_identifier="FOTMOB:1001",
        execute_live_network=True,
        connection_factory=_factory(failed, []),
        clock=_Clock(REQUEST_AT, SEND_AT, OBSERVED_AT),
    )
    assert result.receipt.transport_outcome is ProbeTransportOutcome.TRANSPORT_ERROR
    assert result.receipt.status_code is None
    assert result.receipt.sample_size == 0
    assert result.operator_error == "transport error: TimeoutError"


def test_sampling_error_and_post_response_kickoff_crossing_fail_closed(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)
    response = _Response(error=OSError("read failed"))
    with pytest.raises(FotMobReviewedMatchDetailsProbeError, match="response sampling failed: OSError"):
        probe_fotmob_reviewed_match_details(
            verified_bootstrap_artifact=verified,
            verification_receipt_bytes=receipt_bytes,
            fixture_identifier="FOTMOB:1001",
            execute_live_network=True,
            connection_factory=_factory(_Connection(response=response), []),
            clock=_Clock(REQUEST_AT, SEND_AT),
        )

    connection = _Connection(response=_Response())
    with pytest.raises(FotMobReviewedMatchDetailsProbeError, match="observed_at must be strictly before"):
        probe_fotmob_reviewed_match_details(
            verified_bootstrap_artifact=verified,
            verification_receipt_bytes=receipt_bytes,
            fixture_identifier="FOTMOB:1001",
            execute_live_network=True,
            connection_factory=_factory(connection, []),
            clock=_Clock(REQUEST_AT, SEND_AT, KICKOFF),
        )
    assert connection.endheaders_calls == 1
    assert connection.closed is True


def test_capability_revocation_or_mutated_upstream_blocks_new_plan_and_reuse(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)
    plan = build_match_details_probe_plan(
        verified,
        receipt_bytes,
        fixture_identifier="FOTMOB:1001",
        request_started_at=REQUEST_AT,
    )
    historical_plan = plan.to_dict()
    original = SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY]
    SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY] = dataclasses.replace(
        original,
        reliable_fixture_identity=CapabilityAvailability.UNKNOWN,
    )
    try:
        assert plan.to_dict() == historical_plan
        with pytest.raises(FotMobReviewedMatchDetailsProbeError, match="failed current exact revalidation"):
            dataclasses.replace(plan)
        with pytest.raises(FotMobReviewedMatchDetailsProbeError, match="failed current exact revalidation"):
            build_match_details_probe_plan(
                verified,
                receipt_bytes,
                fixture_identifier="FOTMOB:1001",
                request_started_at=REQUEST_AT,
            )
    finally:
        SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY] = original

    fake = dataclasses.replace(verified.fixtures[0], fixture_identifier="FOTMOB:9999")
    object.__setattr__(verified, "fixtures", (fake,))
    assert plan.to_dict() == historical_plan
    with pytest.raises(FotMobReviewedMatchDetailsProbeError, match="failed current exact revalidation"):
        dataclasses.replace(plan)


def test_historical_receipt_bytes_are_detached_but_new_reconstruction_fails(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)
    connection = _Connection(response=_Response())
    receipt = probe_fotmob_reviewed_match_details(
        verified_bootstrap_artifact=verified,
        verification_receipt_bytes=receipt_bytes,
        fixture_identifier="FOTMOB:1001",
        execute_live_network=True,
        connection_factory=_factory(connection, []),
        clock=_Clock(REQUEST_AT, SEND_AT, OBSERVED_AT),
    ).receipt
    historical = canonical_match_details_probe_receipt_bytes(receipt)
    fake = dataclasses.replace(
        receipt.plan.verified_bootstrap_artifact.fixtures[0],
        fixture_identifier="FOTMOB:9999",
    )
    object.__setattr__(receipt.plan.verified_bootstrap_artifact, "fixtures", (fake,))
    assert canonical_match_details_probe_receipt_bytes(receipt) == historical
    with pytest.raises(FotMobReviewedMatchDetailsProbeError, match="probe plan failed exact current revalidation"):
        dataclasses.replace(receipt)


def test_plan_rejects_cookie_xmas_or_browser_impersonation_flags(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)
    plan = build_match_details_probe_plan(
        verified,
        receipt_bytes,
        fixture_identifier="FOTMOB:1001",
        request_started_at=REQUEST_AT,
    )
    for field in ("x_mas_included", "cookie_included", "browser_impersonation"):
        with pytest.raises(FotMobReviewedMatchDetailsProbeError, match="exact bool False"):
            dataclasses.replace(plan, **{field: True})


def test_production_imports_exclude_bypass_and_downstream_semantics() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = {
        "requests",
        "curl_cffi",
        "playwright",
        "workers.fotmob_bypass_client",
        "workers.fotmob_advanced_scraper",
        "domain.fixture_intelligence",
        "domain.fixture_model_features",
    }
    for relative in (
        "domain/fotmob_reviewed_match_details_probe.py",
        "scripts/probe_fotmob_reviewed_match_details.py",
    ):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        assert not (imports & forbidden)
