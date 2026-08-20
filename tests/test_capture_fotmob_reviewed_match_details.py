from __future__ import annotations

import ast
import dataclasses
import datetime
import importlib.util
from pathlib import Path

import pytest

from domain.fotmob_reviewed_match_details_capture import (
    MANIFEST_FILENAME,
    MAX_RESPONSE_BYTES,
    RAW_FILENAME,
    CapturedFotMobReviewedMatchDetailsResponse,
    build_reviewed_match_details_raw_capture,
)
from domain.fotmob_reviewed_match_details_capture_artifact import (
    build_reviewed_match_details_capture_artifact,
)
from domain.fotmob_reviewed_match_details_probe import (
    ALLOWED_HOST,
    REQUEST_HEADERS,
    build_match_details_probe_plan,
    canonical_match_details_probe_plan_bytes,
)
from domain.reviewed_fixture_catalog_admission import REVIEWED_SOURCE_CAPABILITY
from domain.reviewed_fixture_intelligence_bootstrap_artifact import (
    canonical_verified_bootstrap_artifact_receipt_bytes,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY
from scripts.capture_fotmob_reviewed_match_details import (
    ALLOWED_OUTPUT_RELATIVE,
    REQUEST_TIMEOUT_SECONDS,
    FotMobReviewedMatchDetailsDurableCaptureError,
    _sync_directory,
    capture_fotmob_reviewed_match_details,
    validate_output_root,
    write_reviewed_match_details_capture_artifact,
)

UTC = datetime.timezone.utc
REQUEST_AT = datetime.datetime(2026, 8, 10, 6, 0, tzinfo=UTC)
SEND_AT = REQUEST_AT + datetime.timedelta(milliseconds=100)
OBSERVED_AT = REQUEST_AT + datetime.timedelta(seconds=1)
KICKOFF = datetime.datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def _upstream(tmp_path: Path):
    helper = Path(__file__).with_name(
        "test_reviewed_fixture_intelligence_bootstrap_artifact.py"
    )
    spec = importlib.util.spec_from_file_location("_athena_pr48_capture51_helper", helper)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PR #48 helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _, _, verified = module._verified(tmp_path)
    return verified, canonical_verified_bootstrap_artifact_receipt_bytes(verified)


def _artifact(tmp_path: Path, *, body=b"{not-json-but-preserved"):
    verified, receipt_bytes = _upstream(tmp_path)
    plan = build_match_details_probe_plan(
        verified,
        receipt_bytes,
        fixture_identifier="FOTMOB:1001",
        request_started_at=REQUEST_AT,
    )
    plan_bytes = canonical_match_details_probe_plan_bytes(plan)
    response = CapturedFotMobReviewedMatchDetailsResponse(
        status=200,
        content_type="application/json",
        content_length=len(body),
        body=body,
        observed_at=OBSERVED_AT,
        network_acquisition_performed=True,
    )
    capture = build_reviewed_match_details_raw_capture(
        plan=plan,
        plan_bytes=plan_bytes,
        response=response,
    )
    return build_reviewed_match_details_capture_artifact(capture)


class _Clock:
    def __init__(self, *values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


class _Response:
    def __init__(self, *, status=200, body=b"{not-json-but-preserved", headers=None):
        self.status = status
        self.body = body
        self.headers = headers or {
            "Content-Type": "application/json; charset=utf-8",
            "Content-Length": str(len(body)),
        }
        self.offset = 0
        self.read_calls = []

    def getheader(self, name):
        return self.headers.get(name)

    def read(self, amount):
        self.read_calls.append(amount)
        if self.offset >= len(self.body):
            return b""
        chunk = self.body[self.offset : self.offset + amount]
        self.offset += len(chunk)
        return chunk


class _Connection:
    def __init__(self, response):
        self.response = response
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
        return self.response

    def close(self):
        self.closed = True


def _factory(connection, calls):
    def build(host, port, *, timeout):
        calls.append((host, port, timeout))
        return connection

    return build


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    return root


def test_exact_live_capture_is_one_request_and_writes_exact_pr50_bytes(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path / "upstream")
    repo = _repo(tmp_path)
    body = b"{not-json-and-deliberately-unparsed"
    response = _Response(body=body)
    connection = _Connection(response)
    calls = []

    execution = capture_fotmob_reviewed_match_details(
        verified_bootstrap_artifact=verified,
        verification_receipt_bytes=receipt_bytes,
        fixture_identifier="FOTMOB:1001",
        execute_live_network=True,
        repository_root=repo,
        connection_factory=_factory(connection, calls),
        clock=_Clock(REQUEST_AT, SEND_AT, OBSERVED_AT),
    )

    assert calls == [(ALLOWED_HOST, 443, REQUEST_TIMEOUT_SECONDS)]
    assert connection.requests == [("GET", "/api/data/matchDetails?matchId=1001", True)]
    assert connection.headers == list(REQUEST_HEADERS)
    assert connection.endheaders_calls == 1
    assert connection.closed is True
    assert response.read_calls
    assert execution.capture_directory.parent == repo / ALLOWED_OUTPUT_RELATIVE
    assert (execution.capture_directory / RAW_FILENAME).read_bytes() == body
    assert (execution.capture_directory / MANIFEST_FILENAME).read_bytes() == (
        execution.artifact.manifest_bytes
    )
    assert execution.artifact.capture.raw_bytes == body
    assert execution.artifact.capture.manifest.network_acquisition_performed is True
    assert all(
        value is False
        for value in execution.artifact.capture.manifest.safety.values()
    )


def test_live_network_requires_exact_true_before_connection(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("network connection must not be created")

    for value in (False, None, 1, "true"):
        with pytest.raises(
            FotMobReviewedMatchDetailsDurableCaptureError,
            match="execute_live_network=True",
        ):
            capture_fotmob_reviewed_match_details(
                verified_bootstrap_artifact=verified,
                verification_receipt_bytes=receipt_bytes,
                fixture_identifier="FOTMOB:1001",
                execute_live_network=value,
                repository_root=_repo(tmp_path / str(value)),
                connection_factory=forbidden,
                clock=_Clock(REQUEST_AT),
            )


def test_redirect_or_non_json_response_is_not_captured(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path / "upstream")
    repo = _repo(tmp_path)
    redirect = _Connection(
        _Response(
            status=302,
            body=b"redirect",
            headers={"Content-Type": "text/html", "Content-Length": "8"},
        )
    )
    with pytest.raises(
        FotMobReviewedMatchDetailsDurableCaptureError,
        match="requires exact HTTP 200",
    ):
        capture_fotmob_reviewed_match_details(
            verified_bootstrap_artifact=verified,
            verification_receipt_bytes=receipt_bytes,
            fixture_identifier="FOTMOB:1001",
            execute_live_network=True,
            repository_root=repo,
            connection_factory=_factory(redirect, []),
            clock=_Clock(REQUEST_AT, SEND_AT),
        )
    assert redirect.endheaders_calls == 1
    assert not (repo / ALLOWED_OUTPUT_RELATIVE).exists()

    bad_media = _Connection(
        _Response(
            body=b"html",
            headers={"Content-Type": "text/html", "Content-Length": "4"},
        )
    )
    with pytest.raises(
        FotMobReviewedMatchDetailsDurableCaptureError,
        match="application/json",
    ):
        capture_fotmob_reviewed_match_details(
            verified_bootstrap_artifact=verified,
            verification_receipt_bytes=receipt_bytes,
            fixture_identifier="FOTMOB:1001",
            execute_live_network=True,
            repository_root=repo,
            connection_factory=_factory(bad_media, []),
            clock=_Clock(REQUEST_AT, SEND_AT),
        )
    assert not (repo / ALLOWED_OUTPUT_RELATIVE).exists()


def test_content_length_and_streamed_body_are_bounded_before_publication(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path / "upstream")
    repo = _repo(tmp_path)
    declared = _Connection(
        _Response(
            body=b"x",
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(MAX_RESPONSE_BYTES + 1),
            },
        )
    )
    with pytest.raises(FotMobReviewedMatchDetailsDurableCaptureError, match="8 MiB"):
        capture_fotmob_reviewed_match_details(
            verified_bootstrap_artifact=verified,
            verification_receipt_bytes=receipt_bytes,
            fixture_identifier="FOTMOB:1001",
            execute_live_network=True,
            repository_root=repo,
            connection_factory=_factory(declared, []),
            clock=_Clock(REQUEST_AT, SEND_AT),
        )
    assert declared.response.read_calls == []

    streamed = _Connection(
        _Response(
            body=b"x" * (MAX_RESPONSE_BYTES + 1),
            headers={"Content-Type": "application/json"},
        )
    )
    with pytest.raises(FotMobReviewedMatchDetailsDurableCaptureError, match="8 MiB"):
        capture_fotmob_reviewed_match_details(
            verified_bootstrap_artifact=verified,
            verification_receipt_bytes=receipt_bytes,
            fixture_identifier="FOTMOB:1001",
            execute_live_network=True,
            repository_root=repo,
            connection_factory=_factory(streamed, []),
            clock=_Clock(REQUEST_AT, SEND_AT),
        )
    assert not (repo / ALLOWED_OUTPUT_RELATIVE).exists()


def test_send_and_full_response_must_both_precede_kickoff(tmp_path: Path) -> None:
    verified, receipt_bytes = _upstream(tmp_path / "upstream")
    repo = _repo(tmp_path)
    connection = _Connection(_Response())
    with pytest.raises(
        FotMobReviewedMatchDetailsDurableCaptureError,
        match="request_send_at must be strictly before",
    ):
        capture_fotmob_reviewed_match_details(
            verified_bootstrap_artifact=verified,
            verification_receipt_bytes=receipt_bytes,
            fixture_identifier="FOTMOB:1001",
            execute_live_network=True,
            repository_root=repo,
            connection_factory=_factory(connection, []),
            clock=_Clock(REQUEST_AT, KICKOFF),
        )
    assert connection.endheaders_calls == 0

    connection = _Connection(_Response())
    with pytest.raises(
        FotMobReviewedMatchDetailsDurableCaptureError,
        match="observed_at must be strictly before",
    ):
        capture_fotmob_reviewed_match_details(
            verified_bootstrap_artifact=verified,
            verification_receipt_bytes=receipt_bytes,
            fixture_identifier="FOTMOB:1001",
            execute_live_network=True,
            repository_root=repo,
            connection_factory=_factory(connection, []),
            clock=_Clock(REQUEST_AT, SEND_AT, KICKOFF),
        )
    assert connection.endheaders_calls == 1
    assert not (repo / ALLOWED_OUTPUT_RELATIVE).exists()


def test_writer_is_exact_root_no_overwrite_and_revalidates_capability(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path / "upstream")
    repo = _repo(tmp_path)
    directory = write_reviewed_match_details_capture_artifact(
        artifact,
        repository_root=repo,
    )
    assert directory.exists()

    with pytest.raises(
        FotMobReviewedMatchDetailsDurableCaptureError,
        match="already exists",
    ):
        write_reviewed_match_details_capture_artifact(
            artifact,
            repository_root=repo,
        )
    assert (directory / RAW_FILENAME).read_bytes() == artifact.capture.raw_bytes
    assert (directory / MANIFEST_FILENAME).read_bytes() == artifact.manifest_bytes

    wrong = repo / ".cache" / "elsewhere"
    with pytest.raises(
        FotMobReviewedMatchDetailsDurableCaptureError,
        match="output root must be",
    ):
        validate_output_root(wrong, repository_root=repo)

    original = SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY]
    SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY] = dataclasses.replace(
        original,
        reliable_fixture_identity=CapabilityAvailability.UNKNOWN,
    )
    try:
        with pytest.raises(
            FotMobReviewedMatchDetailsDurableCaptureError,
            match="failed current exact revalidation",
        ):
            write_reviewed_match_details_capture_artifact(
                artifact,
                repository_root=_repo(tmp_path / "revoked"),
            )
    finally:
        SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY] = original


def test_partial_publication_rolls_back_only_owned_capture(tmp_path: Path, monkeypatch) -> None:
    artifact = _artifact(tmp_path / "upstream")
    repo = _repo(tmp_path)
    import scripts.capture_fotmob_reviewed_match_details as module

    original_atomic_write = module._atomic_write

    def fail_manifest(path, content, transaction):
        if path.name == MANIFEST_FILENAME:
            raise FotMobReviewedMatchDetailsDurableCaptureError("injected manifest failure")
        return original_atomic_write(path, content, transaction)

    monkeypatch.setattr(module, "_atomic_write", fail_manifest)
    with pytest.raises(
        FotMobReviewedMatchDetailsDurableCaptureError,
        match="injected manifest failure",
    ):
        module.write_reviewed_match_details_capture_artifact(
            artifact,
            repository_root=repo,
        )
    root = repo / ALLOWED_OUTPUT_RELATIVE
    assert root.exists()
    assert list(root.iterdir()) == []


def test_output_root_rejects_traversal_and_symlink(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    with pytest.raises(FotMobReviewedMatchDetailsDurableCaptureError, match="traversal"):
        validate_output_root(Path("../escape"), repository_root=repo)

    if not hasattr(Path, "symlink_to"):
        return
    cache = repo / ".cache"
    cache.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (cache / "athena-research").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(FotMobReviewedMatchDetailsDurableCaptureError, match="symlink"):
        validate_output_root(ALLOWED_OUTPUT_RELATIVE, repository_root=repo)


def test_directory_durability_fails_closed_on_unknown_platform(tmp_path: Path) -> None:
    with pytest.raises(FotMobReviewedMatchDetailsDurableCaptureError, match="unsupported"):
        _sync_directory(tmp_path, platform_name="mystery")


def test_workflow_imports_exclude_json_parsing_browser_bypass_and_downstream_semantics() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "capture_fotmob_reviewed_match_details.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    forbidden = {
        "json",
        "requests",
        "curl_cffi",
        "playwright",
        "workers.fotmob_bypass_client",
        "workers.fotmob_advanced_scraper",
        "domain.fixture_intelligence",
        "domain.fixture_model_features",
        "engine.prediction_engine",
    }
    assert not (imports & forbidden)
