from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
import http.client
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from domain import fotmob_page_capture as capture_domain
from domain.fotmob_page_capture import (
    ALLOWED_HOST,
    DATASET_NAME,
    HTTPS_PORT,
    MANIFEST_FILENAME,
    MAX_MANIFEST_BYTES,
    MAX_RESPONSE_BYTES,
    RAW_FILENAME,
    REQUEST_HEADERS,
    SCHEMA_VERSION,
    CapturedFotMobPageResponse,
    FotMobPageCaptureError,
    FotMobPageCaptureManifest,
    build_page_capture_manifest,
    canonical_page_capture_manifest_bytes,
    capture_identifier,
    manifest_from_mapping,
    page_capture_manifest_to_dict,
    request_target,
    sha256_bytes,
    sha256_page_capture_manifest,
    validate_html_content_type,
    validate_request_date,
    verify_page_capture_directory,
)
from scripts import capture_fotmob_date_page as capture_script
from scripts.capture_fotmob_date_page import (
    ALLOWED_OUTPUT_RELATIVE,
    FotMobPageNetworkError,
    fetch_fotmob_date_page,
    validate_output_root,
    write_page_capture_directory,
)


DATE = "20260815"
OBSERVED = datetime.datetime(
    2026, 8, 15, 12, 34, 56, 123456, tzinfo=datetime.timezone.utc
)
RAW = b"<!doctype html>\r\n<html>\xffopaque</html>\n"
SAFETY_KEYS = {
    "network_acquisition_authorized",
    "html_capture_authorized",
    "html_parsing_authorized",
    "fixture_extraction_authorized",
    "source_qualified",
    "fixture_promotion_authorized",
    "intelligence_authorized",
    "model_feature_authorized",
    "probability_authorized",
    "pricing_authorized",
    "selection_authorized",
    "bet_authorized",
}


class FakeHttpResponse:
    def __init__(
        self,
        *,
        status: Any = 200,
        body: Any = RAW,
        content_type: Any = "text/html; charset=utf-8",
        content_length: Any = None,
        location: Any = None,
    ) -> None:
        self.status = status
        self.body = body
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": (
                str(len(body)) if content_length is None and isinstance(body, bytes)
                else content_length
            ),
            "Location": location,
        }
        self.offset = 0
        self.read_calls: list[int] = []

    def getheader(self, name: str) -> Any:
        return self.headers.get(name)

    def read(self, amount: int) -> Any:
        self.read_calls.append(amount)
        if not isinstance(self.body, bytes):
            return self.body
        chunk = self.body[self.offset : self.offset + amount]
        self.offset += len(chunk)
        return chunk


class FakeConnection:
    def __init__(self, response: FakeHttpResponse) -> None:
        self.response = response
        self.request_lines: list[tuple[str, str, bool, bool]] = []
        self.headers: list[tuple[str, str]] = []
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
        self.headers.append((name, value))

    def endheaders(self) -> None:
        self.endheaders_calls += 1

    def getresponse(self) -> FakeHttpResponse:
        self.getresponse_calls += 1
        return self.response

    def close(self) -> None:
        self.closed = True


class FakeFactory:
    def __init__(
        self,
        response: FakeHttpResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response or FakeHttpResponse()
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

    def sendall(self, content: bytes) -> None:
        self.sent.extend(content)

    def close(self) -> None:
        pass


class RecordingHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, *, timeout: int) -> None:
        super().__init__(host, port, timeout=timeout)
        self.recording_socket = RecordingSocket()
        self.response = FakeHttpResponse()

    def connect(self) -> None:
        self.sock = self.recording_socket  # type: ignore[assignment]

    def getresponse(self) -> FakeHttpResponse:
        return self.response


def offline_response(
    body: bytes = RAW,
    *,
    network: bool = False,
    content_type: str = "text/html; charset=utf-8",
    content_length: int | None | object = ...,
) -> CapturedFotMobPageResponse:
    length = len(body) if content_length is ... else content_length
    return CapturedFotMobPageResponse(
        status=200,
        content_type=content_type,
        content_length=length,  # type: ignore[arg-type]
        body=body,
        observed_at=OBSERVED,
        network_acquisition_performed=network,
    )


def manifest(**changes: Any) -> FotMobPageCaptureManifest:
    built = build_page_capture_manifest(offline_response(), request_date=DATE)
    return dataclasses.replace(built, **changes) if changes else built


def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    return root


def write_offline(tmp_path: Path, *, network: bool = False, body: bytes = RAW):
    repo = repository(tmp_path)
    capture, built = write_page_capture_directory(
        offline_response(body, network=network),
        request_date=DATE,
        repository_root=repo,
    )
    return repo, capture, built


def test_exact_dataset_schema_host_target_headers_and_fields():
    built = manifest()
    assert DATASET_NAME == "athena-fotmob-date-page-capture-v1"
    assert SCHEMA_VERSION == 1
    assert type(built.schema_version) is int
    assert ALLOWED_HOST == "www.fotmob.com"
    assert HTTPS_PORT == 443
    assert request_target(DATE) == "/?date=20260815"
    assert REQUEST_HEADERS == (
        ("Accept", "text/html,application/xhtml+xml"),
        ("User-Agent", "ATHENA/1.0"),
    )
    assert [field.name for field in dataclasses.fields(FotMobPageCaptureManifest)] == [
        "schema_version", "dataset_name", "request_date", "host",
        "request_target", "request_headers", "status", "content_type",
        "content_length", "observed_at", "network_acquisition_performed",
        "raw_file_name", "raw_sha256", "raw_size", "safety",
    ]


@pytest.mark.parametrize("bad", [True, 1.0, "1", 0, 2])
def test_schema_requires_exact_integer_one(bad: Any):
    with pytest.raises(FotMobPageCaptureError):
        dataclasses.replace(manifest(), schema_version=bad)


@pytest.mark.parametrize(
    "bad",
    [
        "2026-08-15", "2026081", "202608150", "20260230", " 20260815",
        "20260815 ", "20260815&x=1", "20260815?x=1", "2026/08/15",
        "202608%31", True, None,
    ],
)
def test_invalid_dates_fail_closed(bad: Any):
    with pytest.raises(FotMobPageCaptureError):
        validate_request_date(bad)


def test_manifest_is_frozen_and_safety_is_detached_immutable():
    original = dict(manifest().safety)
    built = dataclasses.replace(manifest(), safety=original)
    original["source_qualified"] = True
    assert built.safety["source_qualified"] is False
    with pytest.raises(dataclasses.FrozenInstanceError):
        built.raw_size = 1  # type: ignore[misc]
    with pytest.raises(TypeError):
        built.safety["source_qualified"] = True  # type: ignore[index]


@pytest.mark.parametrize("bad", [0, None, True, "false"])
def test_safety_requires_exact_false_values(bad: Any):
    safety = dict(manifest().safety)
    safety["source_qualified"] = bad
    with pytest.raises(FotMobPageCaptureError):
        dataclasses.replace(manifest(), safety=safety)


def test_safety_has_exact_keys_and_all_false():
    assert set(manifest().safety) == SAFETY_KEYS
    assert all(type(value) is bool and value is False for value in manifest().safety.values())


def test_transport_uses_exact_one_low_level_request():
    factory = FakeFactory()
    fetched = fetch_fotmob_date_page(DATE, connection_factory=factory, clock=lambda: OBSERVED)
    assert fetched.network_acquisition_performed is True
    assert factory.calls == [("www.fotmob.com", 443, capture_script.REQUEST_TIMEOUT_SECONDS)]
    connection = factory.connections[0]
    assert connection.request_lines == [("GET", "/?date=20260815", False, True)]
    assert connection.headers == list(REQUEST_HEADERS)
    assert connection.endheaders_calls == 1
    assert connection.getresponse_calls == 1
    assert connection.closed


def test_real_stdlib_wire_serialization_is_exact():
    connections: list[RecordingHTTPSConnection] = []

    def factory(host: str, port: int, *, timeout: int):
        connection = RecordingHTTPSConnection(host, port, timeout=timeout)
        connections.append(connection)
        return connection

    fetch_fotmob_date_page(DATE, connection_factory=factory, clock=lambda: OBSERVED)
    assert len(connections) == 1
    wire = bytes(connections[0].recording_socket.sent)
    assert wire.split(b"\r\n") == [
        b"GET /?date=20260815 HTTP/1.1",
        b"Host: www.fotmob.com",
        b"Accept: text/html,application/xhtml+xml",
        b"User-Agent: ATHENA/1.0",
        b"",
        b"",
    ]
    lowered = wire.lower()
    for forbidden in (
        b"accept-encoding:", b"referer:", b"cookie:", b"authorization:",
        b"accept-language:", b"connection:", b"sec-fetch-", b"sec-ch-ua",
        b"mozilla/", b"x-",
    ):
        assert forbidden not in lowered
    assert wire.count(b"GET ") == 1


@pytest.mark.parametrize("status", [301, 403, 404, True])
def test_non_200_and_bool_status_fail_without_retry(status: Any):
    factory = FakeFactory(FakeHttpResponse(status=status))
    with pytest.raises(FotMobPageNetworkError):
        fetch_fotmob_date_page(DATE, connection_factory=factory, clock=lambda: OBSERVED)
    assert len(factory.calls) == 1
    assert len(factory.connections[0].request_lines) == 1
    assert factory.connections[0].response.read_calls == []


def test_redirect_location_is_not_followed():
    response = FakeHttpResponse(status=301, location="https://example.invalid")
    factory = FakeFactory(response)
    with pytest.raises(FotMobPageNetworkError):
        fetch_fotmob_date_page(DATE, connection_factory=factory, clock=lambda: OBSERVED)
    assert len(factory.calls) == 1


@pytest.mark.parametrize(
    "content_type",
    ["text/html", "TEXT/HTML", "text/html;charset=utf-8", "text/html; charset=utf-8"],
)
def test_html_content_types_are_accepted(content_type: str):
    assert validate_html_content_type(content_type) == content_type


@pytest.mark.parametrize(
    "content_type",
    [None, "", " text/html", "application/json", "text/plain", "text/html;"],
)
def test_non_html_or_malformed_content_types_are_rejected(content_type: Any):
    with pytest.raises(FotMobPageCaptureError):
        validate_html_content_type(content_type)


@pytest.mark.parametrize("body", ["html", bytearray(b"html"), None, [], {}])
def test_non_bytes_body_is_rejected(body: Any):
    with pytest.raises((FotMobPageCaptureError, FotMobPageNetworkError)):
        CapturedFotMobPageResponse(200, "text/html", None, body, OBSERVED, False)


def test_empty_and_oversized_bodies_are_rejected():
    with pytest.raises(FotMobPageCaptureError, match="empty"):
        offline_response(b"")
    with pytest.raises(FotMobPageCaptureError, match="8 MiB"):
        offline_response(b"x" * (MAX_RESPONSE_BYTES + 1), content_length=None)


def test_oversized_content_length_fails_before_body_consumption():
    response = FakeHttpResponse(content_length=str(MAX_RESPONSE_BYTES + 1))
    factory = FakeFactory(response)
    with pytest.raises(FotMobPageNetworkError, match="8 MiB"):
        fetch_fotmob_date_page(DATE, connection_factory=factory, clock=lambda: OBSERVED)
    assert response.read_calls == []


def test_incremental_limit_rejects_actual_body_over_8_mib():
    response = FakeHttpResponse(body=b"x" * (MAX_RESPONSE_BYTES + 1), content_length=None)
    response.headers["Content-Length"] = None
    with pytest.raises(FotMobPageNetworkError, match="8 MiB"):
        fetch_fotmob_date_page(
            DATE,
            connection_factory=FakeFactory(response),
            clock=lambda: OBSERVED,
        )
    assert len(response.read_calls) > 1
    assert max(response.read_calls) <= capture_script.READ_CHUNK_BYTES


def test_exact_8_mib_boundary_is_accepted_incrementally():
    body = b"x" * MAX_RESPONSE_BYTES
    response = FakeHttpResponse(body=body)
    fetched = fetch_fotmob_date_page(
        DATE, connection_factory=FakeFactory(response), clock=lambda: OBSERVED
    )
    assert fetched.body == body
    assert response.read_calls[-1] == 1


def test_raw_non_utf8_and_line_endings_are_preserved_exactly(tmp_path):
    raw = b"\xff\x00<html>\r\n  exact \n</html>"
    repo, directory, built = write_offline(tmp_path, body=raw)
    assert (directory / RAW_FILENAME).read_bytes() == raw
    assert built.raw_size == len(raw)
    assert built.raw_sha256 == hashlib.sha256(raw).hexdigest()
    assert repo.exists()


def test_response_validation_and_provenance_are_exact():
    offline = offline_response(network=False)
    assert offline.network_acquisition_performed is False
    with pytest.raises(FotMobPageCaptureError):
        dataclasses.replace(offline, network_acquisition_performed=1)
    with pytest.raises(FotMobPageCaptureError):
        dataclasses.replace(offline, observed_at=datetime.datetime(2026, 8, 15))
    offset = datetime.timezone(datetime.timedelta(hours=1))
    shifted = dataclasses.replace(offline, observed_at=OBSERVED.astimezone(offset))
    assert shifted.observed_at == OBSERVED


def test_writer_propagates_false_provenance_and_verifier_policy(tmp_path):
    repo, directory, built = write_offline(tmp_path, network=False)
    assert built.network_acquisition_performed is False
    data = json.loads((directory / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert data["network_acquisition_performed"] is False
    with pytest.raises(FotMobPageCaptureError, match="provenance"):
        verify_page_capture_directory(
            directory,
            allowed_root=repo / ALLOWED_OUTPUT_RELATIVE,
            require_network_acquisition_performed=True,
        )
    checked = verify_page_capture_directory(
        directory,
        allowed_root=repo / ALLOWED_OUTPUT_RELATIVE,
        require_network_acquisition_performed=False,
    )
    assert checked == built


def test_live_fetch_provenance_is_true_and_writer_preserves_true(tmp_path):
    fetched = fetch_fotmob_date_page(
        DATE, connection_factory=FakeFactory(), clock=lambda: OBSERVED
    )
    repo = repository(tmp_path)
    directory, built = write_page_capture_directory(
        fetched, request_date=DATE, repository_root=repo
    )
    assert built.network_acquisition_performed is True
    assert verify_page_capture_directory(
        directory,
        allowed_root=repo / ALLOWED_OUTPUT_RELATIVE,
        require_network_acquisition_performed=True,
    ) == built


def test_manifest_canonical_serialization_and_hash_are_exact():
    built = manifest()
    assert page_capture_manifest_to_dict(built) == built.to_dict()
    raw = canonical_page_capture_manifest_bytes(built)
    assert raw.endswith(b"\n")
    assert raw == canonical_page_capture_manifest_bytes(dataclasses.replace(built))
    assert sha256_page_capture_manifest(built) == hashlib.sha256(raw).hexdigest()
    assert json.loads(raw) == built.to_dict()
    assert RAW not in raw


@pytest.mark.parametrize("bad", [True, 1.0, "1", -1])
def test_manifest_integer_fields_are_strict(bad: Any):
    with pytest.raises(FotMobPageCaptureError):
        dataclasses.replace(manifest(), raw_size=bad)


@pytest.mark.parametrize("bad", ["A" * 64, "0" * 63, "g" * 64, None])
def test_manifest_sha_is_lowercase_exact(bad: Any):
    with pytest.raises(FotMobPageCaptureError):
        dataclasses.replace(manifest(), raw_sha256=bad)


def test_capture_identifier_is_deterministic_and_safe():
    built = manifest()
    first = capture_identifier(
        request_date=DATE, observed_at=OBSERVED, raw_sha256=built.raw_sha256
    )
    second = capture_identifier(
        request_date=DATE, observed_at=OBSERVED, raw_sha256=built.raw_sha256
    )
    assert first == second
    assert len(first) == 24
    assert all(character in "0123456789abcdef" for character in first)


@pytest.mark.parametrize(
    "supplied",
    [Path("outside"), Path("..") / "escape", Path("C:/outside"), Path("/")],
)
def test_output_root_rejects_aliases_and_escape(tmp_path, supplied: Path):
    repo = repository(tmp_path)
    with pytest.raises(FotMobPageCaptureError):
        validate_output_root(supplied, repository_root=repo)


def test_write_creates_exact_two_files_and_rejects_existing_capture(tmp_path):
    repo, directory, built = write_offline(tmp_path)
    assert {item.name for item in directory.iterdir()} == {RAW_FILENAME, MANIFEST_FILENAME}
    assert (directory / RAW_FILENAME).read_bytes() == RAW
    assert (directory / MANIFEST_FILENAME).read_bytes() == canonical_page_capture_manifest_bytes(built)
    with pytest.raises(FotMobPageCaptureError, match="already exists"):
        write_page_capture_directory(
            offline_response(), request_date=DATE, repository_root=repo
        )


def test_date_directory_race_preserves_foreign_sentinel(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    root = repo / ALLOWED_OUTPUT_RELATIVE
    root.mkdir(parents=True)
    date_directory = root / DATE
    sentinel = date_directory / "foreign.txt"
    original = Path.mkdir
    raced = False

    def mkdir(path, *args, **kwargs):
        nonlocal raced
        if Path(path) == date_directory and not raced:
            raced = True
            original(path)
            sentinel.write_bytes(b"race-winner")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)
    with pytest.raises(FotMobPageCaptureError, match="concurrently"):
        write_page_capture_directory(
            offline_response(), request_date=DATE, repository_root=repo
        )
    assert sentinel.read_bytes() == b"race-winner"


def test_capture_directory_race_preserves_foreign_files(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    root = repo / ALLOWED_OUTPUT_RELATIVE
    date_directory = root / DATE
    date_directory.mkdir(parents=True)
    built = manifest()
    identifier = capture_identifier(
        request_date=DATE, observed_at=OBSERVED, raw_sha256=built.raw_sha256
    )
    capture_directory = date_directory / identifier
    foreign = capture_directory / RAW_FILENAME
    original = Path.mkdir
    raced = False

    def mkdir(path, *args, **kwargs):
        nonlocal raced
        if Path(path) == capture_directory and not raced:
            raced = True
            original(path)
            foreign.write_bytes(b"foreign-page")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)
    with pytest.raises(FotMobPageCaptureError, match="already exists"):
        write_page_capture_directory(
            offline_response(), request_date=DATE, repository_root=repo
        )
    assert foreign.read_bytes() == b"foreign-page"


@pytest.mark.parametrize("name", [f".{RAW_FILENAME}.tmp", RAW_FILENAME, f".{MANIFEST_FILENAME}.tmp", MANIFEST_FILENAME])
def test_preexisting_temp_or_final_is_never_deleted(tmp_path, monkeypatch, name):
    repo = repository(tmp_path)
    original_atomic = capture_script._atomic_write
    foreign: Path | None = None

    def inject(path, content, transaction):
        nonlocal foreign
        if foreign is None:
            foreign = path.parent / name
            foreign.write_bytes(b"foreign-deterministic")
        return original_atomic(path, content, transaction)

    monkeypatch.setattr(capture_script, "_atomic_write", inject)
    with pytest.raises(FotMobPageCaptureError, match="cleanup incomplete"):
        write_page_capture_directory(
            offline_response(), request_date=DATE, repository_root=repo
        )
    assert foreign is not None
    assert foreign.read_bytes() == b"foreign-deterministic"


@pytest.mark.parametrize("filename", [RAW_FILENAME, MANIFEST_FILENAME])
def test_publication_race_cannot_overwrite_foreign_final(tmp_path, monkeypatch, filename):
    repo = repository(tmp_path)
    original_link = os.link
    raced: Path | None = None

    def race(source, destination):
        nonlocal raced
        final = Path(destination)
        if final.name == filename and raced is None:
            raced = final
            final.write_bytes(b"foreign-race-winner")
        return original_link(source, destination)

    monkeypatch.setattr(capture_script.os, "link", race)
    with pytest.raises(FotMobPageCaptureError, match="cleanup incomplete"):
        write_page_capture_directory(
            offline_response(), request_date=DATE, repository_root=repo
        )
    assert raced is not None
    assert raced.read_bytes() == b"foreign-race-winner"


def test_publication_ownership_changes_only_after_link(tmp_path, monkeypatch):
    temporary = tmp_path / ".page.html.tmp"
    final = tmp_path / RAW_FILENAME
    temporary.write_bytes(b"owned")
    transaction = capture_script._CaptureTransactionState(
        date_directory=tmp_path,
        capture_directory=tmp_path,
        capture_directory_owned=True,
        owned_temp_files={temporary},
    )
    original = os.link
    observed = []

    def link(source, destination):
        observed.append((final in transaction.owned_final_files, temporary in transaction.owned_temp_files))
        return original(source, destination)

    monkeypatch.setattr(capture_script.os, "link", link)
    capture_script._publish_no_overwrite(temporary, final, transaction)
    assert observed == [(False, True)]
    assert final in transaction.owned_final_files
    assert temporary not in transaction.owned_temp_files


def test_hard_link_unavailable_fails_without_overwrite(tmp_path, monkeypatch):
    temporary = tmp_path / ".page.html.tmp"
    final = tmp_path / RAW_FILENAME
    temporary.write_bytes(b"owned")
    transaction = capture_script._CaptureTransactionState(
        date_directory=tmp_path,
        capture_directory=tmp_path,
        capture_directory_owned=True,
        owned_temp_files={temporary},
    )
    monkeypatch.setattr(capture_script.os, "link", lambda *_: (_ for _ in ()).throw(OSError("unsupported")))
    with pytest.raises(FotMobPageCaptureError, match="unavailable"):
        capture_script._publish_no_overwrite(temporary, final, transaction)
    assert not final.exists()


def test_file_and_directory_sync_order(tmp_path, monkeypatch):
    events = []
    original_link = os.link
    original_unlink = Path.unlink
    monkeypatch.setattr(capture_script.os, "fsync", lambda fd: events.append(("file", fd)))
    monkeypatch.setattr(capture_script.os, "link", lambda source, final: (events.append(("link", Path(final).name)), original_link(source, final))[1])
    monkeypatch.setattr(Path, "unlink", lambda path, *a, **k: (events.append(("unlink", Path(path).name)), original_unlink(path, *a, **k))[1])
    monkeypatch.setattr(capture_script, "_sync_directory", lambda path: events.append(("directory", Path(path))))
    transaction = capture_script._CaptureTransactionState(
        date_directory=tmp_path, capture_directory=tmp_path, capture_directory_owned=True
    )
    capture_script._atomic_write(tmp_path / RAW_FILENAME, b"raw", transaction)
    assert [event[0] for event in events] == ["file", "link", "directory", "unlink", "directory"]


def test_new_directory_entries_are_synchronized_after_creation(tmp_path, monkeypatch):
    repo = repository(tmp_path)
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
    capture_directory, _ = write_page_capture_directory(
        offline_response(), request_date=DATE, repository_root=repo
    )
    root = repo / ALLOWED_OUTPUT_RELATIVE
    date_directory = root / DATE
    for transition in (
        [("mkdir", root), ("sync", root.parent), ("sync", root)],
        [("mkdir", date_directory), ("sync", root), ("sync", date_directory)],
        [("mkdir", capture_directory), ("sync", date_directory), ("sync", capture_directory)],
    ):
        start = events.index(transition[0])
        assert events[start : start + 3] == transition


def test_sync_failure_fails_closed_and_owned_rollback_cleans(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    original = capture_script._sync_directory
    failed = False

    def sync(path, *args, **kwargs):
        nonlocal failed
        directory = Path(path)
        if (directory / RAW_FILENAME).exists() and not failed:
            failed = True
            raise FotMobPageCaptureError("injected sync failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(capture_script, "_sync_directory", sync)
    with pytest.raises(FotMobPageCaptureError, match="sync failure"):
        write_page_capture_directory(
            offline_response(), request_date=DATE, repository_root=repo
        )
    capture_root = repo / ALLOWED_OUTPUT_RELATIVE / DATE
    assert not capture_root.exists()


def test_foreign_arrival_survives_and_cleanup_failure_is_reported(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    original = capture_script._atomic_write
    foreign: Path | None = None
    calls = 0

    def inject(path, content, transaction):
        nonlocal foreign, calls
        calls += 1
        result = original(path, content, transaction)
        if calls == 1:
            foreign = path.parent / "foreign.txt"
            foreign.write_bytes(b"preserve")
            raise FotMobPageCaptureError("later failure")
        return result

    monkeypatch.setattr(capture_script, "_atomic_write", inject)
    with pytest.raises(FotMobPageCaptureError, match="cleanup incomplete") as error:
        write_page_capture_directory(
            offline_response(), request_date=DATE, repository_root=repo
        )
    assert foreign is not None and foreign.read_bytes() == b"preserve"
    assert str(foreign.parent) in str(error.value)
    assert not (foreign.parent / RAW_FILENAME).exists()


def test_cleanup_unlink_failure_surfaces_owned_path(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    original_atomic = capture_script._atomic_write
    original_unlink = Path.unlink
    calls = 0
    owned_raw: Path | None = None

    def later_failure(path, content, transaction):
        nonlocal calls, owned_raw
        calls += 1
        result = original_atomic(path, content, transaction)
        if calls == 1:
            owned_raw = path
        if calls == 2:
            raise FotMobPageCaptureError("manifest failure")
        return result

    def unlink(path, *args, **kwargs):
        if owned_raw is not None and Path(path) == owned_raw:
            raise OSError("injected unlink failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(capture_script, "_atomic_write", later_failure)
    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(FotMobPageCaptureError, match="cleanup incomplete") as error:
        write_page_capture_directory(
            offline_response(), request_date=DATE, repository_root=repo
        )
    assert owned_raw is not None and str(owned_raw) in str(error.value)


def test_verifier_accepts_exact_capture_and_rejects_missing_extra(tmp_path):
    repo, directory, built = write_offline(tmp_path)
    root = repo / ALLOWED_OUTPUT_RELATIVE
    assert verify_page_capture_directory(
        directory, allowed_root=root, require_network_acquisition_performed=False
    ) == built
    extra = directory / "extra.txt"
    extra.write_bytes(b"x")
    with pytest.raises(FotMobPageCaptureError, match="exactly"):
        verify_page_capture_directory(
            directory, allowed_root=root, require_network_acquisition_performed=False
        )
    extra.unlink()
    (directory / RAW_FILENAME).unlink()
    with pytest.raises(FotMobPageCaptureError, match="exactly"):
        verify_page_capture_directory(
            directory, allowed_root=root, require_network_acquisition_performed=False
        )


def test_production_capture_root_is_git_ignored_and_old_root_is_not_canonical():
    repository_root = Path(__file__).resolve().parents[1]
    assert ALLOWED_OUTPUT_RELATIVE == Path(
        ".cache/athena-research/fotmob-date-page-captures"
    )
    for filename in (RAW_FILENAME, MANIFEST_FILENAME):
        candidate = ALLOWED_OUTPUT_RELATIVE / "example" / filename
        checked = subprocess.run(
            ["git", "check-ignore", "-q", candidate.as_posix()],
            cwd=repository_root,
            check=False,
            capture_output=True,
        )
        assert checked.returncode == 0
    old_candidate = Path(
        "artifacts/source-captures/fotmob-date-page/example/page.html"
    )
    assert old_candidate.parts[:4] != ALLOWED_OUTPUT_RELATIVE.parts[:4]
    checked_old = subprocess.run(
        ["git", "check-ignore", "-q", old_candidate.as_posix()],
        cwd=repository_root,
        check=False,
        capture_output=True,
    )
    assert checked_old.returncode == 1


def test_verifier_accepts_raw_page_at_exact_limit(tmp_path):
    body = b"x" * MAX_RESPONSE_BYTES
    repo, directory, built = write_offline(tmp_path, body=body)
    assert verify_page_capture_directory(
        directory,
        allowed_root=repo / ALLOWED_OUTPUT_RELATIVE,
        require_network_acquisition_performed=False,
    ) == built


def test_verifier_rejects_oversized_and_empty_raw_without_read_bytes(
    tmp_path, monkeypatch
):
    repo, directory, _ = write_offline(tmp_path)
    raw_path = directory / RAW_FILENAME
    raw_path.write_bytes(b"x" * (MAX_RESPONSE_BYTES + 1))
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda self: pytest.fail("unbounded Path.read_bytes must not be used"),
    )
    with pytest.raises(FotMobPageCaptureError, match="verification limit"):
        verify_page_capture_directory(
            directory,
            allowed_root=repo / ALLOWED_OUTPUT_RELATIVE,
            require_network_acquisition_performed=False,
        )

    raw_path.write_bytes(b"")
    with pytest.raises(FotMobPageCaptureError, match="must not be empty"):
        verify_page_capture_directory(
            directory,
            allowed_root=repo / ALLOWED_OUTPUT_RELATIVE,
            require_network_acquisition_performed=False,
        )


class _RecordingBoundedReader:
    def __init__(self, content: bytes, requested: list[int]) -> None:
        self._content = content
        self._requested = requested

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, amount: int) -> bytes:
        self._requested.append(amount)
        return self._content[:amount]


@pytest.mark.parametrize(
    ("filename", "maximum"),
    [
        (RAW_FILENAME, MAX_RESPONSE_BYTES),
        (MANIFEST_FILENAME, MAX_MANIFEST_BYTES),
    ],
)
def test_verifier_detects_stat_read_growth_with_maximum_plus_one_read(
    tmp_path, monkeypatch, filename, maximum
):
    repo, directory, _ = write_offline(tmp_path)
    target = directory / filename
    original_open = Path.open
    requested: list[int] = []

    def raced_open(path, *args, **kwargs):
        if path == target and args and args[0] == "rb":
            return _RecordingBoundedReader(b"x" * (maximum + 1), requested)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", raced_open)
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda self: pytest.fail("unbounded Path.read_bytes must not be used"),
    )
    with pytest.raises(FotMobPageCaptureError, match="verification limit"):
        verify_page_capture_directory(
            directory,
            allowed_root=repo / ALLOWED_OUTPUT_RELATIVE,
            require_network_acquisition_performed=False,
        )
    assert requested == [maximum + 1]


def test_manifest_verification_is_bounded_at_exact_and_oversized_limits(
    tmp_path, monkeypatch
):
    repo, directory, _ = write_offline(tmp_path)
    manifest_path = directory / MANIFEST_FILENAME
    manifest_path.write_bytes(b" " * MAX_MANIFEST_BYTES)
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda self: pytest.fail("unbounded Path.read_bytes must not be used"),
    )
    with pytest.raises(FotMobPageCaptureError, match="strict UTF-8 JSON"):
        verify_page_capture_directory(
            directory,
            allowed_root=repo / ALLOWED_OUTPUT_RELATIVE,
            require_network_acquisition_performed=False,
        )

    manifest_path.write_bytes(b"x" * (MAX_MANIFEST_BYTES + 1))
    with pytest.raises(FotMobPageCaptureError, match="verification limit"):
        verify_page_capture_directory(
            directory,
            allowed_root=repo / ALLOWED_OUTPUT_RELATIVE,
            require_network_acquisition_performed=False,
        )


@pytest.mark.parametrize("mutation", ["raw", "size", "date", "target", "headers", "safety"])
def test_verifier_detects_manifest_and_raw_drift(tmp_path, mutation):
    repo, directory, _ = write_offline(tmp_path)
    root = repo / ALLOWED_OUTPUT_RELATIVE
    raw_path = directory / RAW_FILENAME
    manifest_path = directory / MANIFEST_FILENAME
    if mutation == "raw":
        raw_path.write_bytes(raw_path.read_bytes() + b"x")
    else:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if mutation == "size": payload["raw_size"] += 1
        elif mutation == "date": payload["request_date"] = "20260816"
        elif mutation == "target": payload["request_target"] = "/?date=20260816"
        elif mutation == "headers": payload["request_headers"][0][1] = "text/plain"
        elif mutation == "safety": payload["safety"]["source_qualified"] = True
        manifest_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(FotMobPageCaptureError):
        verify_page_capture_directory(
            directory, allowed_root=root, require_network_acquisition_performed=False
        )


def test_verifier_rejects_outside_root(tmp_path):
    repo, directory, _ = write_offline(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(FotMobPageCaptureError, match="outside"):
        verify_page_capture_directory(directory, allowed_root=other)


def test_symlink_capture_or_raw_is_rejected_when_supported(tmp_path):
    repo, directory, _ = write_offline(tmp_path)
    root = repo / ALLOWED_OUTPUT_RELATIVE
    link = directory.parent / "linked"
    try:
        link.symlink_to(directory, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(FotMobPageCaptureError, match="symlink"):
        verify_page_capture_directory(link, allowed_root=root, require_network_acquisition_performed=False)


def test_symlink_output_root_is_rejected_when_supported(tmp_path):
    repo = repository(tmp_path)
    expected = repo / ALLOWED_OUTPUT_RELATIVE
    real = tmp_path / "foreign-root"
    real.mkdir()
    expected.parent.mkdir(parents=True)
    try:
        expected.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(FotMobPageCaptureError, match="symlink"):
        validate_output_root(ALLOWED_OUTPUT_RELATIVE, repository_root=repo)


def test_manifest_round_trip_is_exact():
    built = manifest()
    parsed = manifest_from_mapping(json.loads(canonical_page_capture_manifest_bytes(built)))
    assert parsed == built


def test_cli_without_gate_performs_zero_connection(capsys):
    factory = FakeFactory()
    with pytest.raises(SystemExit) as error:
        capture_script.main(
            ["--date", DATE],
            connection_factory=factory,
            clock=lambda: OBSERVED,
        )
    assert error.value.code == 2
    assert factory.calls == []
    assert "--execute-live-network" in capsys.readouterr().err


def test_cli_success_one_request_and_output_has_no_html(tmp_path, capsys):
    repo = repository(tmp_path)
    factory = FakeFactory()
    assert capture_script.main(
        ["--date", DATE, "--execute-live-network"],
        connection_factory=factory,
        clock=lambda: OBSERVED,
        repository_root=repo,
    ) == 0
    output = capsys.readouterr().out
    assert len(factory.calls) == 1
    assert "<!doctype" not in output
    assert "raw_sha256" in output


def test_parser_has_no_arbitrary_url_header_proxy_or_user_agent():
    options = {
        option
        for action in capture_script.build_parser()._actions
        for option in action.option_strings
    }
    assert options == {
        "-h", "--help", "--date", "--output-root",
        "--execute-live-network", "--check-capture",
    }


def test_source_capability_remains_unknown():
    from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY

    fotmob = SOURCE_CAPABILITY_REGISTRY["fotmob_unofficial"]
    assert fotmob.full_time_score is CapabilityAvailability.UNKNOWN
    assert fotmob.half_time_score is CapabilityAvailability.UNKNOWN
    assert fotmob.event_timestamps is CapabilityAvailability.UNKNOWN
    assert fotmob.reliable_fixture_identity is CapabilityAvailability.UNKNOWN
    assert fotmob.historical_coverage is CapabilityAvailability.UNKNOWN
    assert fotmob.freshness_metadata is CapabilityAvailability.UNKNOWN


def test_new_modules_have_no_unsafe_downstream_or_parsing_imports():
    imports = set()
    for module in (capture_domain, capture_script):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
    forbidden = {
        "domain.fixture_catalog", "domain.fixture_intelligence",
        "domain.fixture_model_features", "intelligence.prediction_engine",
        "intelligence.match_analyst", "bs4", "BeautifulSoup", "lxml",
        "html.parser", "requests", "httpx", "curl_cffi", "playwright",
        "selenium", "fake_useragent", "subprocess",
    }
    assert imports.isdisjoint(forbidden)


def test_manifest_contains_no_raw_html_parsed_fixture_model_pricing_or_bet_fields():
    payload = manifest().to_dict()
    keys = {key.lower() for key in payload}
    forbidden = {
        "html", "body", "dom", "fixture", "candidate", "team", "match_id",
        "probability", "odds", "price", "expected_value", "kelly", "selection",
        "stake", "bet",
    }
    assert keys.isdisjoint(forbidden)
    assert payload["safety"]["html_parsing_authorized"] is False
    assert payload["safety"]["fixture_extraction_authorized"] is False
    assert payload["safety"]["source_qualified"] is False
