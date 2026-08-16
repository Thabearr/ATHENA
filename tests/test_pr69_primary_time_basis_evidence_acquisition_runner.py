from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import domain.pr69_primary_time_basis_evidence_acquisition_protocol as pr124
import domain.pr69_primary_time_basis_evidence_acquisition_runner as contract
import scripts.run_pr69_primary_time_basis_evidence_acquisition as runner

UTC = datetime.timezone.utc
T0 = datetime.datetime(2026, 8, 16, 9, 0, tzinfo=UTC)


class MutableClock:
    def __init__(self, value: datetime.datetime = T0):
        self.value = value
        self.sleeps: list[float] = []

    def __call__(self) -> datetime.datetime:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += datetime.timedelta(seconds=seconds)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.advance(seconds)


def _tiny_plan(monkeypatch):
    actual = contract.campaign_slots()[0]
    plan = (
        contract.CampaignSlot(1, actual.target_id, actual.path, actual.content_type_prefix, "A"),
        contract.CampaignSlot(2, actual.target_id, actual.path, actual.content_type_prefix, "B"),
    )
    monkeypatch.setattr(contract, "campaign_slots", lambda: plan)
    return plan


def _manifest(slot: contract.CampaignSlot, attempt: int, started: datetime.datetime,
              observed: datetime.datetime, raw: bytes) -> dict:
    return {
        "schema_version": contract.SCHEMA_VERSION,
        "runner_id": contract.RUNNER_ID,
        "protocol_sha256": contract.PR124_PROTOCOL_SHA256,
        "target_id": slot.target_id,
        "slot": slot.slot,
        "attempt": attempt,
        "requested_url": slot.requested_url,
        "final_url": slot.requested_url,
        "request_method": "GET",
        "request_headers": [list(pair) for pair in contract.REQUEST_HEADERS],
        "redirect_chain": [],
        "request_started_at_utc": contract.serialize_utc(started),
        "response_completed_at_utc": contract.serialize_utc(observed),
        "observed_at_utc": contract.serialize_utc(observed),
        "http_status": 200,
        "tls_verified": True,
        "response_headers": [["content-type", slot.content_type_prefix + "; charset=utf-8"]],
        "raw_filename": contract.RAW_BODY_FILENAME,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_size": len(raw),
    }


class FakeFetcher:
    def __init__(self, clock: MutableClock, fail_calls: set[int] | None = None):
        self.clock = clock
        self.fail_calls = set(fail_calls or ())
        self.calls = 0
        self.starts: list[datetime.datetime] = []

    def __call__(self, *, slot, attempt, request_started_at, clock):
        self.calls += 1
        self.starts.append(request_started_at)
        self.clock.advance(0.25)
        if self.calls in self.fail_calls:
            raise runner.PrimaryEvidenceRequestError("NETWORK_FAILURE", "synthetic timeout")
        raw = f"evidence-{slot.target_id}-{slot.slot}-{attempt}".encode()
        manifest = _manifest(slot, attempt, request_started_at, self.clock(), raw)
        return runner.FetchResult(slot, attempt, raw, contract.validate_manifest(manifest, slot))


def test_runner_descriptor_is_result_free_and_exact() -> None:
    descriptor = dict(contract.runner_descriptor())
    assert descriptor["runner_state"] == "IMPLEMENTED_NOT_EXECUTED_PRIMARY_TIME_BASIS_EVIDENCE_NOT_CAPTURED"
    assert descriptor["pr124_protocol_sha256"] == pr124.PROTOCOL_SHA256
    assert descriptor["required_successful_capture_count"] == 8
    assert descriptor["network_acquisition_performed"] is False
    assert descriptor["pr69_source_local_time_basis_resolved"] is False
    assert descriptor["pr80_constructor_input_authorized"] is False
    assert descriptor["bet_authorized"] is False
    assert descriptor["next_required_boundary"] == "EXECUTE_REVIEWED_PR69_PRIMARY_TIME_BASIS_EVIDENCE_ACQUISITION_CAMPAIGN"


def test_campaign_plan_is_all_a_then_all_b_and_exact_targets() -> None:
    slots = contract.campaign_slots()
    assert len(slots) == 8
    assert [slot.slot for slot in slots] == ["A"] * 4 + ["B"] * 4
    assert [(slot.target_id, slot.path) for slot in slots[:4]] == [
        ("NOTES_TXT", "/notes.txt"),
        ("DATA_OVERVIEW", "/data.php"),
        ("HISTORICAL_DOWNLOAD_OVERVIEW", "/downloadm.php"),
        ("FIXTURES_OVERVIEW", "/matches.php"),
    ]


def test_upstream_protocol_mutation_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(pr124, "PROTOCOL_SIZE", pr124.PROTOCOL_SIZE + 1)
    with pytest.raises(contract.PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError, match="identity changed"):
        contract.runner_descriptor()


def test_manifest_rejects_redirect_tls_and_request_header_drift() -> None:
    slot = contract.campaign_slots()[0]
    raw = b"abc"
    base = _manifest(slot, 1, T0, T0 + datetime.timedelta(seconds=1), raw)
    for key, value in (
        ("final_url", "https://example.com/notes.txt"),
        ("tls_verified", False),
        ("request_headers", [["User-Agent", "browser"]]),
    ):
        candidate = dict(base)
        candidate[key] = value
        with pytest.raises(contract.PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError):
            contract.validate_manifest(candidate, slot)


def test_live_execution_requires_explicit_true(tmp_path: Path) -> None:
    with pytest.raises(runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError, match="exact True"):
        runner.execute_next_campaign_slot(execute_live_network=False, repository_root=tmp_path)


def test_one_slot_persists_raw_manifest_and_hash_chained_index(tmp_path: Path, monkeypatch) -> None:
    plan = _tiny_plan(monkeypatch)
    clock = MutableClock()
    fetcher = FakeFetcher(clock)
    progress = runner.execute_next_campaign_slot(
        execute_live_network=True, repository_root=tmp_path,
        fetcher=fetcher, clock=clock, sleeper=clock.sleep,
    )
    assert progress.completed_slots == 1
    assert progress.next_slot == plan[1]
    root = tmp_path / contract.CAPTURE_ROOT_RELATIVE
    capture = root / plan[0].target_id / "A"
    assert (capture / contract.RAW_BODY_FILENAME).read_bytes().startswith(b"evidence-")
    manifest_raw = (capture / contract.MANIFEST_FILENAME).read_bytes()
    assert manifest_raw.endswith(b"\n")
    manifest = json.loads(manifest_raw)
    assert hashlib.sha256((capture / contract.RAW_BODY_FILENAME).read_bytes()).hexdigest() == manifest["raw_sha256"]
    entries = runner.load_success_entries(repository_root=tmp_path)
    assert len(entries) == 1
    assert entries[0]["previous_entry_sha256"] == "0" * 64
    assert entries[0]["manifest_sha256"] == hashlib.sha256(manifest_raw).hexdigest()
    assert not (root / contract.RUNNER_LOCK_FILENAME).exists()


def test_retry_is_journaled_then_60_second_delay_succeeds(tmp_path: Path, monkeypatch) -> None:
    _tiny_plan(monkeypatch)
    clock = MutableClock()
    fetcher = FakeFetcher(clock, fail_calls={1})
    progress = runner.execute_next_campaign_slot(
        execute_live_network=True, repository_root=tmp_path,
        fetcher=fetcher, clock=clock, sleeper=clock.sleep,
    )
    assert progress.completed_slots == 1
    assert fetcher.calls == 2
    assert 60.0 in clock.sleeps
    failures = runner.load_failure_entries(repository_root=tmp_path)
    assert len(failures) == 1
    assert failures[0]["error_kind"] == "NETWORK_FAILURE"
    assert failures[0]["attempt"] == 1


def test_three_failed_attempts_use_frozen_delays_and_exhaust(tmp_path: Path, monkeypatch) -> None:
    _tiny_plan(monkeypatch)
    clock = MutableClock()
    fetcher = FakeFetcher(clock, fail_calls={1, 2, 3})
    with pytest.raises(runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError, match="ATTEMPTS_EXHAUSTED"):
        runner.execute_next_campaign_slot(
            execute_live_network=True, repository_root=tmp_path,
            fetcher=fetcher, clock=clock, sleeper=clock.sleep,
        )
    assert fetcher.calls == 3
    assert [value for value in clock.sleeps if value >= 60] == pytest.approx([60.0, 300.0])
    assert [entry["attempt"] for entry in runner.load_failure_entries(repository_root=tmp_path)] == [1, 2, 3]


def test_slot_b_waits_until_300_seconds_from_successful_a(tmp_path: Path, monkeypatch) -> None:
    _tiny_plan(monkeypatch)
    clock = MutableClock()
    fetcher = FakeFetcher(clock)
    runner.execute_next_campaign_slot(
        execute_live_network=True, repository_root=tmp_path,
        fetcher=fetcher, clock=clock, sleeper=clock.sleep,
    )
    runner.execute_next_campaign_slot(
        execute_live_network=True, repository_root=tmp_path,
        fetcher=fetcher, clock=clock, sleeper=clock.sleep,
    )
    entries = runner.load_success_entries(repository_root=tmp_path)
    a = contract.parse_utc(entries[0]["observed_at_utc"], "a")
    b = contract.parse_utc(entries[1]["observed_at_utc"], "b")
    assert (b - a).total_seconds() >= 300
    assert any(value >= 299 for value in clock.sleeps)


def test_expired_pair_window_blocks_before_second_network_call(tmp_path: Path, monkeypatch) -> None:
    _tiny_plan(monkeypatch)
    clock = MutableClock()
    fetcher = FakeFetcher(clock)
    runner.execute_next_campaign_slot(
        execute_live_network=True, repository_root=tmp_path,
        fetcher=fetcher, clock=clock, sleeper=clock.sleep,
    )
    assert fetcher.calls == 1
    clock.advance(3601)
    with pytest.raises(contract.PR69PrimaryTimeBasisEvidencePairWindowError, match="expired"):
        runner.execute_next_campaign_slot(
            execute_live_network=True, repository_root=tmp_path,
            fetcher=fetcher, clock=clock, sleeper=clock.sleep,
        )
    assert fetcher.calls == 1


def test_complete_unindexed_capture_is_recovered_without_duplicate_network(tmp_path: Path, monkeypatch) -> None:
    plan = _tiny_plan(monkeypatch)
    clock = MutableClock()
    raw = b"durable-before-index-crash"
    manifest = _manifest(plan[0], 1, clock(), clock(), raw)
    result = runner.FetchResult(plan[0], 1, raw, contract.validate_manifest(manifest, plan[0]))
    runner.write_capture(result, repository_root=tmp_path)

    def forbidden_fetch(**kwargs):
        raise AssertionError("network must not repeat a durable complete capture")

    progress = runner.execute_next_campaign_slot(
        execute_live_network=True, repository_root=tmp_path,
        fetcher=forbidden_fetch, clock=clock, sleeper=clock.sleep,
    )
    assert progress.completed_slots == 1
    assert progress.next_slot == plan[1]
    assert len(runner.load_success_entries(repository_root=tmp_path)) == 1


def test_partial_existing_slot_blocks_instead_of_overwriting_or_refetching(tmp_path: Path, monkeypatch) -> None:
    plan = _tiny_plan(monkeypatch)
    root = tmp_path / contract.CAPTURE_ROOT_RELATIVE / plan[0].target_id / "A"
    root.mkdir(parents=True)
    (root / contract.RAW_BODY_FILENAME).write_bytes(b"partial")
    calls = 0

    def forbidden_fetch(**kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError

    with pytest.raises(runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError):
        runner.execute_next_campaign_slot(
            execute_live_network=True, repository_root=tmp_path,
            fetcher=forbidden_fetch,
        )
    assert calls == 0
    assert (root / contract.RAW_BODY_FILENAME).read_bytes() == b"partial"


def test_symlink_component_is_rejected(tmp_path: Path) -> None:
    cache = tmp_path / ".cache"
    cache.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (cache / "athena-research").symlink_to(outside, target_is_directory=True)
    with pytest.raises(runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError, match="not a regular directory"):
        runner.load_success_entries(repository_root=tmp_path)


class FakeHTTPResponse:
    def __init__(self, body: bytes = b"Time = Time of match kick off\n", status: int = 200,
                 content_type: str = "text/plain; charset=utf-8", extra_headers=()):
        self.status = status
        self._body = body
        self._headers = [("Content-Type", content_type), ("Content-Length", str(len(body))), *extra_headers]

    def getheaders(self):
        return list(self._headers)

    def read(self, amount):
        return self._body


class FakeHTTPSConnection:
    instances: list["FakeHTTPSConnection"] = []
    response = FakeHTTPResponse()

    def __init__(self, host, port, timeout=None, context=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.requests = []
        self.headers = []
        self.closed = False
        type(self).instances.append(self)

    def putrequest(self, method, path, **kwargs):
        self.requests.append((method, path, kwargs))

    def putheader(self, name, value):
        self.headers.append((name, value))

    def endheaders(self):
        return None

    def getresponse(self):
        return type(self).response

    def close(self):
        self.closed = True


def test_transport_uses_exact_transparent_request_and_preserves_raw_bytes() -> None:
    FakeHTTPSConnection.instances.clear()
    FakeHTTPSConnection.response = FakeHTTPResponse()
    slot = contract.campaign_slots()[0]
    clock = MutableClock()
    started = clock()
    clock.advance(0.1)
    result = runner.fetch_primary_evidence(
        slot=slot, attempt=1, request_started_at=started, clock=clock,
        connection_factory=FakeHTTPSConnection,
    )
    connection = FakeHTTPSConnection.instances[-1]
    assert (connection.host, connection.port) == ("www.football-data.co.uk", 443)
    assert connection.requests == [("GET", "/notes.txt", {"skip_accept_encoding": True})]
    assert connection.headers == list(contract.REQUEST_HEADERS)
    assert connection.closed is True
    assert result.raw_body == b"Time = Time of match kick off\n"
    assert result.manifest["redirect_chain"] == []
    assert result.manifest["tls_verified"] is True
    assert result.manifest["raw_sha256"] == hashlib.sha256(result.raw_body).hexdigest()


def test_transport_refuses_redirect_compression_and_wrong_content_type() -> None:
    slot = contract.campaign_slots()[0]
    for response, kind in (
        (FakeHTTPResponse(status=302), "HTTP_STATUS"),
        (FakeHTTPResponse(extra_headers=(("Content-Encoding", "gzip"),)), "CONTENT_ENCODING"),
        (FakeHTTPResponse(content_type="text/html"), "CONTENT_TYPE"),
    ):
        FakeHTTPSConnection.response = response
        with pytest.raises(runner.PrimaryEvidenceRequestError) as exc:
            runner.fetch_primary_evidence(
                slot=slot, attempt=1, request_started_at=T0,
                clock=MutableClock(), connection_factory=FakeHTTPSConnection,
            )
        assert exc.value.kind == kind


def test_cli_without_execution_flag_is_network_inert(tmp_path: Path, monkeypatch, capsys) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("no network expected")

    monkeypatch.setattr(runner, "execute_campaign", forbidden)
    assert runner.main(["--repository-root", str(tmp_path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["execution_requested"] is False
    assert output["network_acquisition_performed"] is False
