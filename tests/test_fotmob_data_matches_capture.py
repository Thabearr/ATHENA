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

from domain import fotmob_data_matches_capture as capture_domain
from domain import fotmob_data_matches_probe as probe_domain
from domain.fotmob_data_matches_capture import (
    ALLOWED_HOST,
    DATASET_NAME,
    HTTPS_PORT,
    MANIFEST_FILENAME,
    MAX_MANIFEST_BYTES,
    MAX_RESPONSE_BYTES,
    RAW_FILENAME,
    REQUEST_HEADERS,
    SCHEMA_VERSION,
    CapturedFotMobDataMatchesResponse,
    FotMobDataMatchesCaptureError,
    FotMobDataMatchesCaptureManifest,
    build_data_matches_capture_manifest,
    canonical_data_matches_capture_manifest_bytes,
    capture_identifier,
    data_matches_capture_manifest_to_dict,
    manifest_from_mapping,
    sha256_bytes,
    sha256_data_matches_capture_manifest,
    strict_manifest_json_loads,
    validate_json_content_type,
    verify_data_matches_capture_directory,
)
from scripts import capture_fotmob_data_matches as capture_script
from scripts.capture_fotmob_data_matches import (
    ALLOWED_OUTPUT_RELATIVE,
    FotMobDataMatchesNetworkError,
    fetch_fotmob_data_matches,
    validate_output_root,
    write_data_matches_capture_directory,
)


DATE = "20260815"
TIMEZONE = "UTC"
CCODE3 = "NGA"
TARGET = "/api/data/matches?date=20260815&timezone=UTC&ccode3=NGA"
OBSERVED = datetime.datetime(
    2026, 8, 15, 12, 34, 56, 123456, tzinfo=datetime.timezone.utc
)
RAW = b"\xff\xfe{opaque raw transport bytes}\r\n"
SAFETY_KEYS = {
    "network_acquisition_authorized",
    "application_signature_reproduction_authorized",
    "cookie_use_authorized",
    "browser_impersonation_authorized",
    "raw_json_capture_authorized",
    "fixture_parsing_authorized",
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
        content_type: Any = "application/json; charset=utf-8",
        content_length: Any = ...,
        location: Any = None,
    ) -> None:
        self.status = status
        self.body = body
        length = (
            str(len(body))
            if content_length is ... and isinstance(body, bytes)
            else None if content_length is ... else content_length
        )
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": length,
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
    content_type: str = "application/json; charset=utf-8",
    content_length: int | None | object = ...,
) -> CapturedFotMobDataMatchesResponse:
    length = len(body) if content_length is ... else content_length
    return CapturedFotMobDataMatchesResponse(
        status=200,
        content_type=content_type,
        content_length=length,  # type: ignore[arg-type]
        body=body,
        observed_at=OBSERVED,
        network_acquisition_performed=network,
    )


def manifest(**changes: Any) -> FotMobDataMatchesCaptureManifest:
    built = build_data_matches_capture_manifest(
        offline_response(),
        request_date=DATE,
        timezone=TIMEZONE,
        ccode3=CCODE3,
    )
    return dataclasses.replace(built, **changes) if changes else built


def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    return root


def write_offline(
    tmp_path: Path,
    *,
    network: bool = False,
    body: bytes = RAW,
) -> tuple[Path, Path, FotMobDataMatchesCaptureManifest]:
    repo = repository(tmp_path)
    directory, built = write_data_matches_capture_directory(
        offline_response(body, network=network),
        request_date=DATE,
        timezone=TIMEZONE,
        ccode3=CCODE3,
        repository_root=repo,
    )
    return repo, directory, built


def test_exact_contract_constants_and_manifest_fields():
    built = manifest()
    assert DATASET_NAME == "athena-fotmob-data-matches-capture-v1"
    assert SCHEMA_VERSION == 1
    assert type(built.schema_version) is int
    assert RAW_FILENAME == "response.json"
    assert MANIFEST_FILENAME == "manifest.json"
    assert MAX_RESPONSE_BYTES == 8 * 1024 * 1024
    assert MAX_MANIFEST_BYTES == 64 * 1024
    assert [field.name for field in dataclasses.fields(built)] == [
        "schema_version", "dataset_name", "request_date", "timezone", "ccode3",
        "host", "request_target", "request_headers", "x_mas_included", "status",
        "content_type", "content_length", "observed_at",
        "network_acquisition_performed", "raw_file_name", "raw_sha256", "raw_size",
        "safety",
    ]


@pytest.mark.parametrize("bad", [True, 1.0, "1", 0, 2])
def test_schema_requires_exact_integer_one(bad: Any):
    with pytest.raises(FotMobDataMatchesCaptureError):
        dataclasses.replace(manifest(), schema_version=bad)


def test_manifest_is_frozen_and_safety_detached_immutable():
    original = dict(manifest().safety)
    built = dataclasses.replace(manifest(), safety=original)
    with pytest.raises(dataclasses.FrozenInstanceError):
        built.status = 404  # type: ignore[misc]
    original["source_qualified"] = True
    assert built.safety["source_qualified"] is False
    with pytest.raises(TypeError):
        built.safety["source_qualified"] = True  # type: ignore[index]


@pytest.mark.parametrize("bad", [0, 1, None, True, "false"])
def test_safety_values_require_exact_false(bad: Any):
    safety = dict(manifest().safety)
    safety["source_qualified"] = bad
    with pytest.raises(FotMobDataMatchesCaptureError):
        dataclasses.replace(manifest(), safety=safety)


def test_safety_keys_are_exact_and_all_false():
    assert set(manifest().safety) == SAFETY_KEYS
    assert all(type(value) is bool and value is False for value in manifest().safety.values())


@pytest.mark.parametrize("bad", [True, 0, 1, None, "false"])
def test_x_mas_must_be_exact_false(bad: Any):
    with pytest.raises(FotMobDataMatchesCaptureError):
        dataclasses.replace(manifest(), x_mas_included=bad)


def test_request_contract_is_anchored_exactly_to_probe():
    built = manifest()
    assert ALLOWED_HOST == probe_domain.ALLOWED_HOST == "www.fotmob.com"
    assert HTTPS_PORT == probe_domain.HTTPS_PORT == 443
    assert REQUEST_HEADERS is probe_domain.REQUEST_HEADERS
    assert built.request_target == probe_domain.request_target(DATE, TIMEZONE, CCODE3)
    assert built.request_headers == probe_domain.REQUEST_HEADERS
    assert built.request_target == TARGET
    assert "includeNextDayLateNight" not in built.request_target


@pytest.mark.parametrize(
    "bad",
    ["2026-08-15", "2026081", "20260230", " 20260815", True, None],
)
def test_date_validation_matches_probe_fail_closed(bad: Any):
    with pytest.raises(FotMobDataMatchesCaptureError):
        build_data_matches_capture_manifest(
            offline_response(), request_date=bad, timezone=TIMEZONE, ccode3=CCODE3
        )


@pytest.mark.parametrize(
    "bad",
    ["", " UTC", "UTC ", "Africa//Lagos", "UTC&x", "UTC%x", "A" * 65, True, None],
)
def test_timezone_validation_matches_probe_fail_closed(bad: Any):
    with pytest.raises(FotMobDataMatchesCaptureError):
        build_data_matches_capture_manifest(
            offline_response(), request_date=DATE, timezone=bad, ccode3=CCODE3
        )


@pytest.mark.parametrize("bad", ["nga", "NG", "NGAA", "N1A", True, None])
def test_ccode3_validation_matches_probe_fail_closed(bad: Any):
    with pytest.raises(FotMobDataMatchesCaptureError):
        build_data_matches_capture_manifest(
            offline_response(), request_date=DATE, timezone=TIMEZONE, ccode3=bad
        )


def test_transport_uses_exact_one_low_level_request():
    factory = FakeFactory()
    response = fetch_fotmob_data_matches(
        request_date=DATE,
        timezone=TIMEZONE,
        ccode3=CCODE3,
        connection_factory=factory,
        clock=lambda: OBSERVED,
    )
    assert response.network_acquisition_performed is True
    assert factory.calls == [(ALLOWED_HOST, HTTPS_PORT, capture_script.REQUEST_TIMEOUT_SECONDS)]
    connection = factory.connections[0]
    assert connection.request_lines == [("GET", TARGET, False, True)]
    assert connection.headers == list(REQUEST_HEADERS)
    assert connection.endheaders_calls == 1
    assert connection.getresponse_calls == 1
    assert connection.closed


def test_real_stdlib_wire_serialization_is_exact():
    connections: list[RecordingHTTPSConnection] = []

    def factory(host: str, port: int, *, timeout: int) -> RecordingHTTPSConnection:
        connection = RecordingHTTPSConnection(host, port, timeout=timeout)
        connections.append(connection)
        return connection

    fetch_fotmob_data_matches(
        request_date=DATE,
        timezone=TIMEZONE,
        ccode3=CCODE3,
        connection_factory=factory,
        clock=lambda: OBSERVED,
    )
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
        b"accept-encoding:", b"x-mas:", b"referer:", b"cookie:",
        b"authorization:", b"accept-language:", b"origin:", b"connection:",
        b"sec-fetch-", b"sec-ch-ua", b"fotmob-client:", b"x-requested-with:",
        b"mozilla/",
    ):
        assert forbidden not in lowered
    assert serialized.count(b"GET ") == 1


@pytest.mark.parametrize("status", [201, 301, 401, 403, 404, 500, True])
def test_non_200_or_bool_status_fails_without_retry(status: Any):
    factory = FakeFactory(FakeHttpResponse(status=status))
    with pytest.raises(FotMobDataMatchesNetworkError):
        fetch_fotmob_data_matches(
            request_date=DATE, timezone=TIMEZONE, ccode3=CCODE3,
            connection_factory=factory, clock=lambda: OBSERVED,
        )
    assert len(factory.calls) == 1
    assert factory.connections[0].getresponse_calls == 1


def test_redirect_location_is_not_followed():
    factory = FakeFactory(FakeHttpResponse(status=301, location="https://example.invalid"))
    with pytest.raises(FotMobDataMatchesNetworkError):
        fetch_fotmob_data_matches(
            request_date=DATE, timezone=TIMEZONE, ccode3=CCODE3,
            connection_factory=factory, clock=lambda: OBSERVED,
        )
    assert len(factory.calls) == 1


@pytest.mark.parametrize(
    "value",
    ["application/json", "application/json;charset=utf-8", "APPLICATION/JSON; charset=utf-8"],
)
def test_json_content_types_are_accepted(value: str):
    assert validate_json_content_type(value) == value


@pytest.mark.parametrize(
    "value", ["text/html", "text/plain", "", " application/json", "application/json;", None]
)
def test_non_json_or_malformed_content_types_rejected(value: Any):
    with pytest.raises(FotMobDataMatchesCaptureError):
        validate_json_content_type(value)


@pytest.mark.parametrize("body", ["json", bytearray(b"json"), None, [], {}])
def test_non_bytes_body_rejected(body: Any):
    with pytest.raises(FotMobDataMatchesCaptureError):
        dataclasses.replace(offline_response(), body=body)


def test_empty_and_oversized_body_rejected():
    with pytest.raises(FotMobDataMatchesCaptureError, match="empty"):
        offline_response(b"")
    with pytest.raises(FotMobDataMatchesCaptureError, match="8 MiB"):
        offline_response(b"x" * (MAX_RESPONSE_BYTES + 1))


def test_oversized_content_length_fails_before_body_read():
    response = FakeHttpResponse(content_length=str(MAX_RESPONSE_BYTES + 1))
    with pytest.raises(FotMobDataMatchesNetworkError, match="8 MiB"):
        fetch_fotmob_data_matches(
            request_date=DATE, timezone=TIMEZONE, ccode3=CCODE3,
            connection_factory=FakeFactory(response), clock=lambda: OBSERVED,
        )
    assert response.read_calls == []


def test_actual_body_over_limit_is_rejected_incrementally():
    response = FakeHttpResponse(
        body=b"x" * (MAX_RESPONSE_BYTES + 1), content_length=None
    )
    with pytest.raises(FotMobDataMatchesNetworkError, match="8 MiB"):
        fetch_fotmob_data_matches(
            request_date=DATE, timezone=TIMEZONE, ccode3=CCODE3,
            connection_factory=FakeFactory(response), clock=lambda: OBSERVED,
        )
    assert sum(response.read_calls) <= MAX_RESPONSE_BYTES + 1


def test_content_length_mismatch_rejected_and_absence_accepted():
    mismatch = FakeHttpResponse(body=b"abc", content_length="2")
    with pytest.raises(FotMobDataMatchesNetworkError, match="does not match"):
        fetch_fotmob_data_matches(
            request_date=DATE, timezone=TIMEZONE, ccode3=CCODE3,
            connection_factory=FakeFactory(mismatch), clock=lambda: OBSERVED,
        )
    response = fetch_fotmob_data_matches(
        request_date=DATE, timezone=TIMEZONE, ccode3=CCODE3,
        connection_factory=FakeFactory(FakeHttpResponse(body=b"abc", content_length=None)),
        clock=lambda: OBSERVED,
    )
    assert response.content_length is None and response.body == b"abc"


def test_non_utf8_bytes_are_preserved_without_json_parsing(monkeypatch):
    marker = b"\xff\x00not-json-at-all"
    monkeypatch.setattr(
        capture_script.json,
        "loads",
        lambda *_a, **_k: pytest.fail("response body must not be parsed"),
    )
    response = fetch_fotmob_data_matches(
        request_date=DATE, timezone=TIMEZONE, ccode3=CCODE3,
        connection_factory=FakeFactory(FakeHttpResponse(body=marker)),
        clock=lambda: OBSERVED,
    )
    assert response.body == marker


def test_response_validation_provenance_and_time_are_exact():
    offset = datetime.timezone(datetime.timedelta(hours=1))
    response = dataclasses.replace(
        offline_response(), observed_at=OBSERVED.astimezone(offset)
    )
    assert response.observed_at == OBSERVED
    assert response.observed_at.tzinfo is datetime.timezone.utc
    for bad in (0, 1, None, "false"):
        with pytest.raises(FotMobDataMatchesCaptureError):
            dataclasses.replace(response, network_acquisition_performed=bad)


def test_writer_propagates_offline_provenance_and_verifier_policy(tmp_path):
    repo, directory, built = write_offline(tmp_path, network=False)
    assert built.network_acquisition_performed is False
    with pytest.raises(FotMobDataMatchesCaptureError, match="provenance"):
        verify_data_matches_capture_directory(
            directory, allowed_root=repo / ALLOWED_OUTPUT_RELATIVE,
            require_network_acquisition_performed=True,
        )
    assert verify_data_matches_capture_directory(
        directory, allowed_root=repo / ALLOWED_OUTPUT_RELATIVE,
        require_network_acquisition_performed=False,
    ) == built


def test_manifest_canonical_bytes_and_hash_are_exact():
    built = manifest()
    payload = built.to_dict()
    assert data_matches_capture_manifest_to_dict(built) == payload
    raw = canonical_data_matches_capture_manifest_bytes(built)
    assert raw.endswith(b"\n")
    assert json.loads(raw) == payload
    assert sha256_data_matches_capture_manifest(built) == hashlib.sha256(raw).hexdigest()
    assert RAW not in raw


@pytest.mark.parametrize("bad", ["A" * 64, "0" * 63, "g" * 64, None])
def test_manifest_sha_requires_lowercase_exact(bad: Any):
    with pytest.raises(FotMobDataMatchesCaptureError):
        dataclasses.replace(manifest(), raw_sha256=bad)


def test_capture_identifier_is_deterministic_and_uses_all_identity_members():
    built = manifest()
    base = capture_identifier(
        request_date=DATE, timezone=TIMEZONE, ccode3=CCODE3,
        observed_at=OBSERVED, raw_sha256=built.raw_sha256,
    )
    assert len(base) == 24 and base.isascii() and base.isalnum() and base.islower()
    assert base == capture_identifier(
        request_date=DATE, timezone=TIMEZONE, ccode3=CCODE3,
        observed_at=OBSERVED, raw_sha256=built.raw_sha256,
    )
    assert base != capture_identifier(
        request_date=DATE, timezone="Africa/Lagos", ccode3=CCODE3,
        observed_at=OBSERVED, raw_sha256=built.raw_sha256,
    )


@pytest.mark.parametrize(
    "raw", [b'{"a":1,"a":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}', b"[1]", b"bad", b"\xff"]
)
def test_strict_manifest_loading_rejects_invalid_json_and_topology(raw: bytes):
    if raw == b"[1]":
        with pytest.raises(FotMobDataMatchesCaptureError, match="keys"):
            manifest_from_mapping(strict_manifest_json_loads(raw))
    else:
        with pytest.raises(FotMobDataMatchesCaptureError):
            strict_manifest_json_loads(raw)


def test_manifest_mapping_rejects_missing_extra_and_wrong_header_shapes():
    payload = manifest().to_dict()
    for mutation in ("missing", "extra", "headers"):
        changed = json.loads(json.dumps(payload))
        if mutation == "missing":
            changed.pop("status")
        elif mutation == "extra":
            changed["extra"] = False
        else:
            changed["request_headers"] = {"Accept": "application/json"}
        with pytest.raises(FotMobDataMatchesCaptureError):
            manifest_from_mapping(changed)


@pytest.mark.parametrize(
    "supplied", [Path("outside"), Path("..") / "escape", Path("C:/outside"), Path("/")]
)
def test_output_root_rejects_aliases_and_escape(tmp_path, supplied: Path):
    with pytest.raises(FotMobDataMatchesCaptureError):
        validate_output_root(supplied, repository_root=repository(tmp_path))


def test_write_preserves_exact_bytes_and_creates_only_two_files(tmp_path):
    repo, directory, built = write_offline(tmp_path)
    assert {item.name for item in directory.iterdir()} == {RAW_FILENAME, MANIFEST_FILENAME}
    assert (directory / RAW_FILENAME).read_bytes() == RAW
    assert (directory / MANIFEST_FILENAME).read_bytes() == canonical_data_matches_capture_manifest_bytes(built)
    with pytest.raises(FotMobDataMatchesCaptureError, match="already exists"):
        write_data_matches_capture_directory(
            offline_response(), request_date=DATE, timezone=TIMEZONE,
            ccode3=CCODE3, repository_root=repo,
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
    with pytest.raises(FotMobDataMatchesCaptureError, match="concurrently"):
        write_data_matches_capture_directory(
            offline_response(), request_date=DATE, timezone=TIMEZONE,
            ccode3=CCODE3, repository_root=repo,
        )
    assert sentinel.read_bytes() == b"race-winner"


def test_capture_directory_race_preserves_foreign_final(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    root = repo / ALLOWED_OUTPUT_RELATIVE
    date_directory = root / DATE
    date_directory.mkdir(parents=True)
    built = manifest()
    capture_dir = date_directory / capture_identifier(
        request_date=DATE, timezone=TIMEZONE, ccode3=CCODE3,
        observed_at=OBSERVED, raw_sha256=built.raw_sha256,
    )
    foreign = capture_dir / RAW_FILENAME
    original = Path.mkdir
    raced = False

    def mkdir(path, *args, **kwargs):
        nonlocal raced
        if Path(path) == capture_dir and not raced:
            raced = True
            original(path)
            foreign.write_bytes(b"foreign")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)
    with pytest.raises(FotMobDataMatchesCaptureError, match="already exists"):
        write_data_matches_capture_directory(
            offline_response(), request_date=DATE, timezone=TIMEZONE,
            ccode3=CCODE3, repository_root=repo,
        )
    assert foreign.read_bytes() == b"foreign"


@pytest.mark.parametrize(
    "name", [f".{RAW_FILENAME}.tmp", RAW_FILENAME, f".{MANIFEST_FILENAME}.tmp", MANIFEST_FILENAME]
)
def test_preexisting_temp_or_final_is_preserved(tmp_path, monkeypatch, name: str):
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
    with pytest.raises(FotMobDataMatchesCaptureError, match="cleanup incomplete"):
        write_data_matches_capture_directory(
            offline_response(), request_date=DATE, timezone=TIMEZONE,
            ccode3=CCODE3, repository_root=repo,
        )
    assert foreign is not None and foreign.read_bytes() == b"foreign-deterministic"


@pytest.mark.parametrize("filename", [RAW_FILENAME, MANIFEST_FILENAME])
def test_publication_race_never_overwrites_foreign_final(tmp_path, monkeypatch, filename):
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
    with pytest.raises(FotMobDataMatchesCaptureError, match="cleanup incomplete"):
        write_data_matches_capture_directory(
            offline_response(), request_date=DATE, timezone=TIMEZONE,
            ccode3=CCODE3, repository_root=repo,
        )
    assert raced is not None and raced.read_bytes() == b"foreign-race-winner"


def test_final_ownership_is_recorded_only_after_successful_link(tmp_path, monkeypatch):
    temporary = tmp_path / f".{RAW_FILENAME}.tmp"
    final = tmp_path / RAW_FILENAME
    temporary.write_bytes(b"owned")
    transaction = capture_script._CaptureTransactionState(
        date_directory=tmp_path, capture_directory=tmp_path,
        capture_directory_owned=True, owned_temp_files={temporary},
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


def test_file_fsync_link_and_directory_sync_order(tmp_path, monkeypatch):
    events = []
    original_link = os.link
    original_unlink = Path.unlink
    monkeypatch.setattr(capture_script.os, "fsync", lambda fd: events.append("file-fsync"))
    monkeypatch.setattr(capture_script.os, "link", lambda source, final: (events.append("link"), original_link(source, final))[1])
    monkeypatch.setattr(Path, "unlink", lambda path, *a, **k: (events.append("unlink"), original_unlink(path, *a, **k))[1])
    monkeypatch.setattr(capture_script, "_sync_directory", lambda path: events.append("dir-fsync"))
    transaction = capture_script._CaptureTransactionState(
        date_directory=tmp_path, capture_directory=tmp_path, capture_directory_owned=True
    )
    capture_script._atomic_write(tmp_path / RAW_FILENAME, b"raw", transaction)
    assert events == ["file-fsync", "link", "dir-fsync", "unlink", "dir-fsync"]


def test_directory_sync_failure_fails_closed_and_owned_rollback_cleans(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    original = capture_script._sync_directory
    failed = False

    def sync(path, *args, **kwargs):
        nonlocal failed
        directory = Path(path)
        if (directory / RAW_FILENAME).exists() and not failed:
            failed = True
            raise FotMobDataMatchesCaptureError("injected sync failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(capture_script, "_sync_directory", sync)
    with pytest.raises(FotMobDataMatchesCaptureError, match="sync failure"):
        write_data_matches_capture_directory(
            offline_response(), request_date=DATE, timezone=TIMEZONE,
            ccode3=CCODE3, repository_root=repo,
        )
    assert not (repo / ALLOWED_OUTPUT_RELATIVE / DATE).exists()


def test_foreign_file_arrival_is_preserved_and_cleanup_failure_reported(tmp_path, monkeypatch):
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
            raise FotMobDataMatchesCaptureError("later failure")
        return result

    monkeypatch.setattr(capture_script, "_atomic_write", inject)
    with pytest.raises(FotMobDataMatchesCaptureError, match="cleanup incomplete") as error:
        write_data_matches_capture_directory(
            offline_response(), request_date=DATE, timezone=TIMEZONE,
            ccode3=CCODE3, repository_root=repo,
        )
    assert foreign is not None and foreign.read_bytes() == b"preserve"
    assert str(foreign.parent) in str(error.value)
    assert not (foreign.parent / RAW_FILENAME).exists()


def test_cleanup_failure_surfaces_exact_owned_path(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    original_atomic = capture_script._atomic_write
    original_unlink = Path.unlink
    owned_raw: Path | None = None
    calls = 0

    def later_failure(path, content, transaction):
        nonlocal owned_raw, calls
        calls += 1
        result = original_atomic(path, content, transaction)
        if calls == 1:
            owned_raw = path
        if calls == 2:
            raise FotMobDataMatchesCaptureError("manifest failure")
        return result

    def unlink(path, *args, **kwargs):
        if owned_raw is not None and Path(path) == owned_raw:
            raise OSError("injected unlink failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(capture_script, "_atomic_write", later_failure)
    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(FotMobDataMatchesCaptureError, match="cleanup incomplete") as error:
        write_data_matches_capture_directory(
            offline_response(), request_date=DATE, timezone=TIMEZONE,
            ccode3=CCODE3, repository_root=repo,
        )
    assert owned_raw is not None and str(owned_raw) in str(error.value)


def test_verifier_accepts_exact_capture_and_rejects_missing_extra(tmp_path):
    repo, directory, built = write_offline(tmp_path)
    root = repo / ALLOWED_OUTPUT_RELATIVE
    assert verify_data_matches_capture_directory(
        directory, allowed_root=root, require_network_acquisition_performed=False
    ) == built
    extra = directory / "extra.txt"
    extra.write_bytes(b"x")
    with pytest.raises(FotMobDataMatchesCaptureError, match="exactly"):
        verify_data_matches_capture_directory(
            directory, allowed_root=root, require_network_acquisition_performed=False
        )
    extra.unlink()
    (directory / RAW_FILENAME).unlink()
    with pytest.raises(FotMobDataMatchesCaptureError, match="exactly"):
        verify_data_matches_capture_directory(
            directory, allowed_root=root, require_network_acquisition_performed=False
        )


def test_production_capture_root_is_git_ignored():
    repository_root = Path(__file__).resolve().parents[1]
    assert ALLOWED_OUTPUT_RELATIVE == Path(
        ".cache/athena-research/fotmob-data-matches-captures"
    )
    for filename in (RAW_FILENAME, MANIFEST_FILENAME):
        candidate = ALLOWED_OUTPUT_RELATIVE / DATE / "example" / filename
        checked = subprocess.run(
            ["git", "check-ignore", "-q", candidate.as_posix()],
            cwd=repository_root, check=False, capture_output=True,
        )
        assert checked.returncode == 0


def test_verifier_rejects_oversized_and_empty_raw_without_unbounded_read(tmp_path, monkeypatch):
    repo, directory, _ = write_offline(tmp_path)
    raw_path = directory / RAW_FILENAME
    raw_path.write_bytes(b"x" * (MAX_RESPONSE_BYTES + 1))
    monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail("unbounded read"))
    with pytest.raises(FotMobDataMatchesCaptureError, match="verification limit"):
        verify_data_matches_capture_directory(
            directory, allowed_root=repo / ALLOWED_OUTPUT_RELATIVE,
            require_network_acquisition_performed=False,
        )
    raw_path.write_bytes(b"")
    with pytest.raises(FotMobDataMatchesCaptureError, match="empty"):
        verify_data_matches_capture_directory(
            directory, allowed_root=repo / ALLOWED_OUTPUT_RELATIVE,
            require_network_acquisition_performed=False,
        )


class _RecordingBoundedReader:
    def __init__(self, content: bytes, requested: list[int]) -> None:
        self.content = content
        self.requested = requested

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, amount: int) -> bytes:
        self.requested.append(amount)
        return self.content[:amount]


@pytest.mark.parametrize(
    ("filename", "maximum"),
    [(RAW_FILENAME, MAX_RESPONSE_BYTES), (MANIFEST_FILENAME, MAX_MANIFEST_BYTES)],
)
def test_verifier_stat_read_growth_is_bounded_at_maximum_plus_one(
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
    monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail("unbounded read"))
    with pytest.raises(FotMobDataMatchesCaptureError, match="verification limit"):
        verify_data_matches_capture_directory(
            directory, allowed_root=repo / ALLOWED_OUTPUT_RELATIVE,
            require_network_acquisition_performed=False,
        )
    assert requested == [maximum + 1]


def test_manifest_verification_rejects_exact_invalid_and_oversized_bounded(tmp_path, monkeypatch):
    repo, directory, _ = write_offline(tmp_path)
    path = directory / MANIFEST_FILENAME
    path.write_bytes(b" " * MAX_MANIFEST_BYTES)
    monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail("unbounded read"))
    with pytest.raises(FotMobDataMatchesCaptureError, match="strict UTF-8 JSON"):
        verify_data_matches_capture_directory(
            directory, allowed_root=repo / ALLOWED_OUTPUT_RELATIVE,
            require_network_acquisition_performed=False,
        )
    path.write_bytes(b"x" * (MAX_MANIFEST_BYTES + 1))
    with pytest.raises(FotMobDataMatchesCaptureError, match="verification limit"):
        verify_data_matches_capture_directory(
            directory, allowed_root=repo / ALLOWED_OUTPUT_RELATIVE,
            require_network_acquisition_performed=False,
        )


@pytest.mark.parametrize(
    "mutation", ["raw", "size", "target", "headers", "xmas", "safety", "date"]
)
def test_verifier_detects_raw_and_manifest_drift(tmp_path, mutation):
    repo, directory, _ = write_offline(tmp_path)
    root = repo / ALLOWED_OUTPUT_RELATIVE
    raw_path = directory / RAW_FILENAME
    manifest_path = directory / MANIFEST_FILENAME
    if mutation == "raw":
        raw_path.write_bytes(raw_path.read_bytes() + b"x")
    else:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if mutation == "size": payload["raw_size"] += 1
        elif mutation == "target": payload["request_target"] = "/api/data/matches?bad=1"
        elif mutation == "headers": payload["request_headers"][0][1] = "text/plain"
        elif mutation == "xmas": payload["x_mas_included"] = True
        elif mutation == "safety": payload["safety"]["source_qualified"] = True
        elif mutation == "date": payload["request_date"] = "20260816"
        manifest_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(FotMobDataMatchesCaptureError):
        verify_data_matches_capture_directory(
            directory, allowed_root=root, require_network_acquisition_performed=False
        )


def test_symlink_capture_or_raw_is_rejected_when_supported(tmp_path):
    repo, directory, _ = write_offline(tmp_path)
    root = repo / ALLOWED_OUTPUT_RELATIVE
    link = directory.parent / "linked"
    try:
        link.symlink_to(directory, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(FotMobDataMatchesCaptureError, match="symlink"):
        verify_data_matches_capture_directory(
            link, allowed_root=root, require_network_acquisition_performed=False
        )


def test_cli_without_gate_performs_zero_connection(capsys):
    factory = FakeFactory()
    with pytest.raises(SystemExit) as error:
        capture_script.main(
            ["--date", DATE, "--timezone", TIMEZONE, "--ccode3", CCODE3],
            connection_factory=factory, clock=lambda: OBSERVED,
        )
    assert error.value.code == 2
    assert factory.calls == []
    assert "--execute-live-network" in capsys.readouterr().err


def test_cli_success_issues_one_request_and_never_prints_body(tmp_path, capsys):
    repo = repository(tmp_path)
    marker = b"secret-response-marker"
    factory = FakeFactory(FakeHttpResponse(body=marker))
    assert capture_script.main(
        ["--date", DATE, "--timezone", TIMEZONE, "--ccode3", CCODE3,
         "--execute-live-network"],
        connection_factory=factory, clock=lambda: OBSERVED, repository_root=repo,
    ) == 0
    output = capsys.readouterr().out
    assert len(factory.calls) == 1
    assert marker.decode() not in output
    assert "raw_sha256" in output and "manifest_sha256" in output


def test_cli_parser_exposes_only_fixed_inputs_and_gate():
    options = {
        option
        for action in capture_script.build_parser()._actions
        for option in action.option_strings
    }
    assert options == {
        "-h", "--help", "--date", "--timezone", "--ccode3",
        "--execute-live-network",
    }


def test_source_capability_remains_unknown():
    from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY

    fotmob = SOURCE_CAPABILITY_REGISTRY["fotmob_unofficial"]
    assert all(
        value is CapabilityAvailability.UNKNOWN
        for value in (
            fotmob.full_time_score, fotmob.half_time_score, fotmob.event_timestamps,
            fotmob.reliable_fixture_identity, fotmob.historical_coverage,
            fotmob.freshness_metadata,
        )
    )


def test_new_modules_have_no_unsafe_downstream_or_fixture_parser_imports():
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
        "intelligence.match_analyst", "requests", "httpx", "aiohttp",
        "curl_cffi", "playwright", "selenium", "base64", "subprocess",
    }
    assert imports.isdisjoint(forbidden)


def test_no_x_mas_signature_or_embedded_signing_material_exists():
    production = (
        Path(capture_domain.__file__).read_text(encoding="utf-8")
        + Path(capture_script.__file__).read_text(encoding="utf-8")
    ).lower()
    assert "hashlib.md5" not in production
    assert "b64encode" not in production
    assert "306d430a56a4e621a6fde71ec0d0f433af0c14a2" not in production
    assert "fotmob-client" not in production


def test_manifest_has_no_response_or_fixture_model_pricing_betting_fields():
    keys = {key.lower() for key in manifest().to_dict()}
    forbidden = {
        "body", "response", "sample", "leagues", "matches", "fixture",
        "candidate", "team", "competition", "kickoff", "probability", "odds",
        "price", "kelly", "selection", "stake", "bet",
    }
    assert keys.isdisjoint(forbidden)
    assert not hasattr(capture_domain, "FotMobFixtureCandidate")
