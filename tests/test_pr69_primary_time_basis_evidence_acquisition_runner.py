from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path

import pytest

import domain.pr69_primary_time_basis_evidence_acquisition_protocol as pr124
import domain.pr69_primary_time_basis_evidence_acquisition_runner as contract
import scripts.run_pr69_primary_time_basis_evidence_acquisition as runner

UTC = datetime.timezone.utc
T0 = datetime.datetime(2026, 8, 16, 9, 0, tzinfo=UTC)
_PRODUCTION_EXECUTE_NEXT_CAMPAIGN_SLOT = runner.execute_next_campaign_slot
_PRODUCTION_EXECUTE_CAMPAIGN = runner.execute_campaign


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


class SequenceClock:
    def __init__(self, *values: datetime.datetime):
        if not values:
            raise ValueError("at least one clock value is required")
        self.values = list(values)
        self.index = 0

    def __call__(self) -> datetime.datetime:
        if self.index < len(self.values):
            value = self.values[self.index]
            self.index += 1
            return value
        return self.values[-1]


def _tiny_plan(monkeypatch):
    actual = contract.campaign_slots()[0]
    plan = (
        contract.CampaignSlot(
            1, actual.target_id, actual.path, actual.content_type_prefix, "A"
        ),
        contract.CampaignSlot(
            2, actual.target_id, actual.path, actual.content_type_prefix, "B"
        ),
    )
    monkeypatch.setattr(contract, "campaign_slots", lambda: plan)
    return plan


def _two_target_a_plan(monkeypatch):
    actual = contract.campaign_slots()
    first = actual[0]
    second = actual[1]
    plan = (
        contract.CampaignSlot(
            1, first.target_id, first.path, first.content_type_prefix, "A"
        ),
        contract.CampaignSlot(
            2, second.target_id, second.path, second.content_type_prefix, "A"
        ),
    )
    monkeypatch.setattr(contract, "campaign_slots", lambda: plan)
    return plan


def _manifest(
    slot: contract.CampaignSlot,
    attempt: int,
    started: datetime.datetime,
    observed: datetime.datetime,
    raw: bytes,
) -> dict:
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
        "response_headers": [
            ["content-type", slot.content_type_prefix + "; charset=utf-8"]
        ],
        "raw_filename": contract.RAW_BODY_FILENAME,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_size": len(raw),
    }


class FakeFetcher:
    def __init__(
        self,
        clock: MutableClock,
        fail_calls: set[int] | None = None,
        response_seconds: float = 0.25,
    ) -> None:
        self.clock = clock
        self.fail_calls = set(fail_calls or ())
        self.response_seconds = response_seconds
        self.calls = 0
        self.starts: list[datetime.datetime] = []

    def __call__(self, *, slot, attempt, request_started_at, clock):
        self.calls += 1
        self.starts.append(request_started_at)
        self.clock.advance(self.response_seconds)
        if self.calls in self.fail_calls:
            raise runner.PrimaryEvidenceRequestError(
                "NETWORK_FAILURE", "synthetic timeout"
            )
        raw = f"evidence-{slot.target_id}-{slot.slot}-{attempt}".encode()
        manifest = _manifest(
            slot, attempt, request_started_at, self.clock(), raw
        )
        return runner.FetchResult(
            slot,
            attempt,
            raw,
            contract.validate_manifest(manifest, slot),
        )


@pytest.fixture(autouse=True)
def _install_private_synthetic_execution_seam(monkeypatch):
    """Keep synthetic fetchers out of the trusted public live-execution API.

    Existing state-machine tests use the private locked seam against tmp_path roots. Calls
    without a synthetic fetcher still exercise the production public wrapper. Any private
    synthetic call that accidentally reaches a real wait fails immediately instead of
    sleeping in hosted CI.
    """

    def execute_next_for_test(
        *,
        execute_live_network: bool,
        repository_root: Path | None = None,
        fetcher=runner.fetch_primary_evidence,
        clock=runner._clock,
        sleeper=None,
    ):
        if fetcher is runner.fetch_primary_evidence:
            return _PRODUCTION_EXECUTE_NEXT_CAMPAIGN_SLOT(
                execute_live_network=execute_live_network,
                repository_root=repository_root,
                clock=clock,
                sleeper=sleeper,
            )
        if execute_live_network is not True:
            return _PRODUCTION_EXECUTE_NEXT_CAMPAIGN_SLOT(
                execute_live_network=execute_live_network,
                repository_root=repository_root,
                clock=clock,
                sleeper=sleeper,
            )
        contract.runner_descriptor()
        repository = Path(repository_root or runner._repository_root()).resolve(strict=True)

        def forbidden_real_wait(seconds: float) -> None:
            raise AssertionError(
                f"synthetic runner test attempted a real wait of {seconds} seconds"
            )

        actual_sleeper = forbidden_real_wait if sleeper is None else sleeper
        with runner.campaign_lock(repository_root=repository) as root:
            return runner._execute_next_slot_locked(
                repository_root=repository,
                root=root,
                fetcher=fetcher,
                clock=clock,
                sleeper=actual_sleeper,
            )

    monkeypatch.setattr(runner, "execute_next_campaign_slot", execute_next_for_test)


def _capture_one_a(
    tmp_path: Path, monkeypatch, clock: MutableClock | None = None
):
    plan = _tiny_plan(monkeypatch)
    actual_clock = clock or MutableClock()
    fetcher = FakeFetcher(actual_clock)
    progress = runner.execute_next_campaign_slot(
        execute_live_network=True,
        repository_root=tmp_path,
        fetcher=fetcher,
        clock=actual_clock,
        sleeper=actual_clock.sleep,
    )
    return plan, actual_clock, fetcher, progress


def test_runner_descriptor_is_implemented_but_result_free() -> None:
    descriptor = dict(contract.runner_descriptor())
    assert descriptor["runner_state"] == (
        "IMPLEMENTED_NOT_EXECUTED_PRIMARY_TIME_BASIS_EVIDENCE_NOT_CAPTURED"
    )
    assert descriptor["campaign_runner_implemented"] is True
    assert descriptor["pr124_protocol_sha256"] == pr124.PROTOCOL_SHA256
    assert descriptor["required_successful_capture_count"] == 8
    assert descriptor["network_acquisition_performed"] is False
    assert descriptor["pr69_source_local_time_basis_resolved"] is False
    assert descriptor["pr80_constructor_input_authorized"] is False
    assert descriptor["bet_authorized"] is False
    assert descriptor["next_required_boundary"] == (
        "EXECUTE_REVIEWED_PR69_PRIMARY_TIME_BASIS_EVIDENCE_ACQUISITION_CAMPAIGN"
    )


def test_campaign_plan_is_exact_all_a_then_all_b() -> None:
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
    with pytest.raises(
        contract.PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError,
        match="identity changed",
    ):
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
        with pytest.raises(
            contract.PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError
        ):
            contract.validate_manifest(candidate, slot)


def test_split_stream_round_trip_preserves_global_hash_chain(monkeypatch) -> None:
    plan = _tiny_plan(monkeypatch)
    failure = contract.build_attempt_failed_entry(
        (),
        slot=plan[0],
        attempt=1,
        attempt_started_at=T0,
        recorded_at=T0 + datetime.timedelta(seconds=1),
        error_kind="NETWORK_FAILURE",
        error_message="timeout",
    )
    raw = b"ok"
    manifest = _manifest(
        plan[0], 2, T0 + datetime.timedelta(seconds=61),
        T0 + datetime.timedelta(seconds=62), raw,
    )
    success = contract.build_slot_succeeded_entry(
        (failure,),
        slot=plan[0],
        attempt=2,
        attempt_started_at=T0 + datetime.timedelta(seconds=61),
        recorded_at=T0 + datetime.timedelta(seconds=63),
        manifest_sha256=contract.manifest_sha256(manifest),
        raw_sha256=manifest["raw_sha256"],
        raw_size=len(raw),
        observed_at=T0 + datetime.timedelta(seconds=62),
    )
    entries = (failure, success)
    index, failures = contract.split_campaign_evidence_bytes(entries)
    assert contract.parse_campaign_evidence_bytes(index, failures) == entries


def test_global_evidence_rejects_torn_and_duplicate_json(monkeypatch) -> None:
    plan = _tiny_plan(monkeypatch)
    failure = contract.build_attempt_failed_entry(
        (),
        slot=plan[0],
        attempt=1,
        attempt_started_at=T0,
        recorded_at=T0,
        error_kind="NETWORK_FAILURE",
        error_message="timeout",
    )
    line = contract.canonical_campaign_entry_bytes(failure)
    with pytest.raises(
        contract.PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError,
        match="torn",
    ):
        contract.parse_campaign_evidence_bytes(b"", line[:-1])
    duplicate = line.replace(
        b'{"attempt":1,', b'{"attempt":1,"attempt":1,', 1
    )
    with pytest.raises(
        contract.PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError,
        match="duplicate",
    ):
        contract.parse_campaign_evidence_bytes(b"", duplicate)


def test_live_execution_requires_exact_true(tmp_path: Path) -> None:
    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="exact True",
    ):
        runner.execute_next_campaign_slot(
            execute_live_network=False, repository_root=tmp_path
        )


def test_public_live_execution_api_has_no_fetcher_injection(tmp_path: Path) -> None:
    calls = 0

    def synthetic_fetcher(**kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("synthetic transport must never run")

    with pytest.raises(TypeError):
        _PRODUCTION_EXECUTE_NEXT_CAMPAIGN_SLOT(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=synthetic_fetcher,
        )
    with pytest.raises(TypeError):
        _PRODUCTION_EXECUTE_CAMPAIGN(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=synthetic_fetcher,
        )
    assert calls == 0


def test_public_live_execution_rejects_clock_and_sleeper_injection(tmp_path: Path) -> None:
    clock = MutableClock()
    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="forbids clock or sleeper injection",
    ):
        _PRODUCTION_EXECUTE_NEXT_CAMPAIGN_SLOT(
            execute_live_network=True,
            repository_root=tmp_path,
            clock=clock,
        )
    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="forbids clock or sleeper injection",
    ):
        _PRODUCTION_EXECUTE_CAMPAIGN(
            execute_live_network=True,
            repository_root=tmp_path,
            sleeper=lambda seconds: None,
        )


def test_public_live_execution_rejects_repository_root_override(tmp_path: Path) -> None:
    trusted = runner._repository_root().resolve(strict=True)
    assert runner._trusted_repository_root(None) == trusted
    assert runner._trusted_repository_root(trusted) == trusted
    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="repository root override",
    ):
        _PRODUCTION_EXECUTE_NEXT_CAMPAIGN_SLOT(
            execute_live_network=True,
            repository_root=tmp_path,
        )
    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="repository root override",
    ):
        _PRODUCTION_EXECUTE_CAMPAIGN(
            execute_live_network=True,
            repository_root=tmp_path,
        )
    assert not (tmp_path / ".cache").exists()


def test_one_slot_persists_raw_manifest_and_global_index(
    tmp_path: Path, monkeypatch
) -> None:
    plan, _, _, progress = _capture_one_a(tmp_path, monkeypatch)
    assert progress.completed_slots == 1
    assert progress.next_slot == plan[1]
    root = tmp_path / contract.CAPTURE_ROOT_RELATIVE
    capture = root / plan[0].target_id / "A"
    raw = (capture / contract.RAW_BODY_FILENAME).read_bytes()
    manifest_raw = (capture / contract.MANIFEST_FILENAME).read_bytes()
    manifest = json.loads(manifest_raw)
    assert hashlib.sha256(raw).hexdigest() == manifest["raw_sha256"]
    entries = runner.load_campaign_entries(repository_root=tmp_path)
    assert [entry["event_type"] for entry in entries] == ["SLOT_SUCCEEDED"]
    assert entries[0]["previous_entry_sha256"] == contract.ZERO_SHA256
    assert entries[0]["detail"]["manifest_sha256"] == hashlib.sha256(
        manifest_raw
    ).hexdigest()
    assert not (root / runner.INFLIGHT_ATTEMPT_FILENAME).exists()
    assert not (root / contract.RUNNER_LOCK_FILENAME).exists()


def test_retry_is_durably_journaled_and_60_second_delay_applies(
    tmp_path: Path, monkeypatch
) -> None:
    _tiny_plan(monkeypatch)
    clock = MutableClock()
    fetcher = FakeFetcher(clock, fail_calls={1})
    progress = runner.execute_next_campaign_slot(
        execute_live_network=True,
        repository_root=tmp_path,
        fetcher=fetcher,
        clock=clock,
        sleeper=clock.sleep,
    )
    assert progress.completed_slots == 1
    assert fetcher.calls == 2
    assert any(value >= 59 for value in clock.sleeps)
    entries = runner.load_campaign_entries(repository_root=tmp_path)
    assert [entry["event_type"] for entry in entries] == [
        "ATTEMPT_FAILED", "SLOT_SUCCEEDED"
    ]
    assert entries[0]["attempt"] == 1
    assert entries[1]["attempt"] == 2
    assert entries[1]["previous_entry_sha256"] == entries[0]["entry_sha256"]


def test_retry_delay_survives_restart(tmp_path: Path, monkeypatch) -> None:
    _tiny_plan(monkeypatch)
    clock = MutableClock()
    fetcher = FakeFetcher(clock, fail_calls={1})

    class StopAfterFailure(RuntimeError):
        pass

    def stop_on_retry_wait(seconds: float) -> None:
        if seconds >= 59:
            raise StopAfterFailure
        clock.sleep(seconds)

    with pytest.raises(StopAfterFailure):
        runner.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=fetcher,
            clock=clock,
            sleeper=stop_on_retry_wait,
        )
    entries = runner.load_campaign_entries(repository_root=tmp_path)
    assert [entry["event_type"] for entry in entries] == ["ATTEMPT_FAILED"]
    assert not (
        tmp_path
        / contract.CAPTURE_ROOT_RELATIVE
        / runner.INFLIGHT_ATTEMPT_FILENAME
    ).exists()

    failure_recorded = contract.parse_utc(
        entries[-1]["recorded_at_utc"], "recorded_at_utc"
    )
    clock.value = failure_recorded + datetime.timedelta(seconds=30)
    restart_fetcher = FakeFetcher(clock)
    progress = runner.execute_next_campaign_slot(
        execute_live_network=True,
        repository_root=tmp_path,
        fetcher=restart_fetcher,
        clock=clock,
        sleeper=clock.sleep,
    )
    assert progress.completed_slots == 1
    assert restart_fetcher.calls == 1
    assert any(29 <= value <= 31 for value in clock.sleeps)


def test_three_failed_attempts_are_terminal_and_persisted(
    tmp_path: Path, monkeypatch
) -> None:
    _tiny_plan(monkeypatch)
    clock = MutableClock()
    fetcher = FakeFetcher(clock, fail_calls={1, 2, 3})
    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="ATTEMPTS_EXHAUSTED",
    ):
        runner.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=fetcher,
            clock=clock,
            sleeper=clock.sleep,
        )
    entries = runner.load_campaign_entries(repository_root=tmp_path)
    assert [entry["attempt"] for entry in entries] == [1, 2, 3]
    assert all(entry["event_type"] == "ATTEMPT_FAILED" for entry in entries)
    progress = contract.campaign_progress(entries)
    assert progress.blocked is True
    assert progress.block_reason == "ATTEMPTS_EXHAUSTED"
    calls = fetcher.calls
    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="blocked",
    ):
        runner.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=fetcher,
            clock=clock,
            sleeper=clock.sleep,
        )
    assert fetcher.calls == calls


def test_slot_b_waits_for_successful_a_observation(
    tmp_path: Path, monkeypatch
) -> None:
    _tiny_plan(monkeypatch)
    clock = MutableClock()
    fetcher = FakeFetcher(clock)
    runner.execute_next_campaign_slot(
        execute_live_network=True,
        repository_root=tmp_path,
        fetcher=fetcher,
        clock=clock,
        sleeper=clock.sleep,
    )
    runner.execute_next_campaign_slot(
        execute_live_network=True,
        repository_root=tmp_path,
        fetcher=fetcher,
        clock=clock,
        sleeper=clock.sleep,
    )
    entries = runner.load_campaign_entries(repository_root=tmp_path)
    successes = [entry for entry in entries if entry["event_type"] == "SLOT_SUCCEEDED"]
    a = contract.parse_utc(successes[0]["detail"]["observed_at_utc"], "a")
    b = contract.parse_utc(successes[1]["detail"]["observed_at_utc"], "b")
    assert (b - a).total_seconds() >= 300
    assert any(value >= 299 for value in clock.sleeps)


def test_expired_pair_window_is_durably_blocked_before_network(
    tmp_path: Path, monkeypatch
) -> None:
    _, clock, fetcher, _ = _capture_one_a(tmp_path, monkeypatch)
    assert fetcher.calls == 1
    clock.advance(3601)
    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="pair window blocked",
    ):
        runner.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=fetcher,
            clock=clock,
            sleeper=clock.sleep,
        )
    assert fetcher.calls == 1
    entries = runner.load_campaign_entries(repository_root=tmp_path)
    assert entries[-1]["event_type"] == "SLOT_BLOCKED"
    assert entries[-1]["detail"]["error_kind"] == (
        "PAIR_WINDOW_EXPIRED_BEFORE_REQUEST"
    )
    assert contract.campaign_progress(entries).blocked is True


def test_runner_clock_before_slot_a_fails_closed(tmp_path: Path, monkeypatch) -> None:
    _, clock, fetcher, _ = _capture_one_a(tmp_path, monkeypatch)
    successes = [
        entry
        for entry in runner.load_campaign_entries(repository_root=tmp_path)
        if entry["event_type"] == "SLOT_SUCCEEDED"
    ]
    a = contract.parse_utc(successes[0]["detail"]["observed_at_utc"], "a")
    clock.value = a - datetime.timedelta(seconds=1)
    calls = fetcher.calls
    with pytest.raises(
        contract.PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError,
        match="clock precedes",
    ):
        runner.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=fetcher,
            clock=clock,
            sleeper=clock.sleep,
        )
    assert fetcher.calls == calls


def test_clock_rollback_after_slow_success_blocks_next_target_before_network(
    tmp_path: Path, monkeypatch
) -> None:
    _two_target_a_plan(monkeypatch)
    clock = MutableClock()
    fetcher = FakeFetcher(clock, response_seconds=10.0)
    progress = runner.execute_next_campaign_slot(
        execute_live_network=True,
        repository_root=tmp_path,
        fetcher=fetcher,
        clock=clock,
        sleeper=clock.sleep,
    )
    assert progress.completed_slots == 1
    entries = runner.load_campaign_entries(repository_root=tmp_path)
    started = contract.parse_utc(
        entries[-1]["attempt_started_at_utc"], "attempt_started_at_utc"
    )
    recorded = contract.parse_utc(entries[-1]["recorded_at_utc"], "recorded_at_utc")
    assert (recorded - started).total_seconds() >= 10
    clock.value = started + datetime.timedelta(seconds=5)
    calls = fetcher.calls
    with pytest.raises(
        contract.PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError,
        match="latest durable campaign evidence",
    ):
        runner.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=fetcher,
            clock=clock,
            sleeper=clock.sleep,
        )
    assert fetcher.calls == calls


def test_clock_rollback_between_intent_and_request_blocks_before_network(
    tmp_path: Path, monkeypatch
) -> None:
    _tiny_plan(monkeypatch)
    clock = SequenceClock(T0, T0 - datetime.timedelta(seconds=1))
    calls = 0

    def forbidden_fetch(**kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("network must not run")

    with pytest.raises(
        contract.PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError,
        match="durable inflight intent",
    ):
        runner.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=forbidden_fetch,
            clock=clock,
        )
    assert calls == 0
    root = tmp_path / contract.CAPTURE_ROOT_RELATIVE
    assert not (root / runner.INFLIGHT_ATTEMPT_FILENAME).exists()
    assert runner.load_campaign_entries(repository_root=tmp_path) == ()


def test_pair_window_expiry_after_inflight_blocks_before_network(
    tmp_path: Path, monkeypatch
) -> None:
    _, _, _, _ = _capture_one_a(tmp_path, monkeypatch)
    entries = runner.load_campaign_entries(repository_root=tmp_path)
    a = contract.parse_utc(entries[-1]["detail"]["observed_at_utc"], "a")
    clock = SequenceClock(
        a + datetime.timedelta(seconds=300),
        a + datetime.timedelta(seconds=3601),
    )
    calls = 0

    def forbidden_fetch(**kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("network must not run")

    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="pair window blocked before request",
    ):
        runner.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=forbidden_fetch,
            clock=clock,
        )
    assert calls == 0
    entries = runner.load_campaign_entries(repository_root=tmp_path)
    assert entries[-1]["event_type"] == "SLOT_BLOCKED"
    assert entries[-1]["detail"]["error_kind"] == (
        "PAIR_WINDOW_EXPIRED_BEFORE_REQUEST"
    )
    root = tmp_path / contract.CAPTURE_ROOT_RELATIVE
    assert not (root / runner.INFLIGHT_ATTEMPT_FILENAME).exists()


def test_pending_inflight_attempt_blocks_automatic_retry(
    tmp_path: Path, monkeypatch
) -> None:
    plan = _tiny_plan(monkeypatch)
    root = runner._ensure_campaign_root(repository_root=tmp_path)
    entries = runner.load_campaign_entries(
        repository_root=tmp_path, create_root=True
    )
    runner._create_inflight(
        entries,
        slot=plan[0],
        attempt=1,
        intent_started_at=T0,
        root=root,
    )
    calls = 0

    def forbidden_fetch(**kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("network must not run")

    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="UNRESOLVED_INFLIGHT",
    ):
        runner.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=forbidden_fetch,
        )
    assert calls == 0


def test_complete_capture_with_pending_inflight_still_requires_reconciliation(
    tmp_path: Path, monkeypatch
) -> None:
    plan = _tiny_plan(monkeypatch)
    root = runner._ensure_campaign_root(repository_root=tmp_path)
    entries = runner.load_campaign_entries(
        repository_root=tmp_path, create_root=True
    )
    runner._create_inflight(
        entries,
        slot=plan[0],
        attempt=1,
        intent_started_at=T0,
        root=root,
    )
    raw = b"unindexed-but-complete"
    manifest = _manifest(plan[0], 1, T0, T0, raw)
    runner.write_capture(
        runner.FetchResult(
            plan[0], 1, raw, contract.validate_manifest(manifest, plan[0])
        ),
        repository_root=tmp_path,
    )
    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="UNRESOLVED_INFLIGHT",
    ):
        runner.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=lambda **kwargs: pytest.fail("network must not repeat"),
        )
    assert runner.load_campaign_entries(repository_root=tmp_path) == ()


def test_unindexed_capture_without_inflight_blocks_and_is_not_promoted(
    tmp_path: Path, monkeypatch
) -> None:
    plan = _tiny_plan(monkeypatch)
    raw = b"orphan-complete-capture"
    manifest = _manifest(plan[0], 1, T0, T0, raw)
    runner.write_capture(
        runner.FetchResult(
            plan[0], 1, raw, contract.validate_manifest(manifest, plan[0])
        ),
        repository_root=tmp_path,
    )
    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="UNINDEXED_CAPTURE",
    ):
        runner.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=lambda **kwargs: pytest.fail("network must not run"),
        )
    assert runner.load_campaign_entries(repository_root=tmp_path) == ()


def test_future_unindexed_capture_blocks_before_current_slot_network(
    tmp_path: Path, monkeypatch
) -> None:
    plan = _tiny_plan(monkeypatch)
    root = runner._ensure_campaign_root(repository_root=tmp_path)
    future = root / plan[1].target_id / plan[1].slot
    future.mkdir(parents=True)
    calls = 0

    def forbidden_fetch(**kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("network must not run")

    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="UNINDEXED_CAPTURE",
    ):
        runner.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=forbidden_fetch,
        )
    assert calls == 0


def test_unexpected_campaign_root_entry_blocks_before_network(
    tmp_path: Path, monkeypatch
) -> None:
    _tiny_plan(monkeypatch)
    root = runner._ensure_campaign_root(repository_root=tmp_path)
    (root / "rogue-evidence.bin").write_bytes(b"rogue")
    calls = 0

    def forbidden_fetch(**kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("network must not run")

    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="unexpected campaign root entry",
    ):
        runner.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=forbidden_fetch,
        )
    assert calls == 0


def test_recorded_outcome_allows_safe_stale_inflight_cleanup(
    tmp_path: Path, monkeypatch
) -> None:
    plan = _tiny_plan(monkeypatch)
    clock = MutableClock()
    root = runner._ensure_campaign_root(repository_root=tmp_path)
    entries = runner.load_campaign_entries(
        repository_root=tmp_path, create_root=True
    )
    intent = runner._create_inflight(
        entries,
        slot=plan[0],
        attempt=1,
        intent_started_at=clock(),
        root=root,
    )
    clock.advance(0.1)
    failure = contract.build_attempt_failed_entry(
        entries,
        slot=plan[0],
        attempt=1,
        attempt_started_at=clock(),
        recorded_at=clock(),
        error_kind="NETWORK_FAILURE",
        error_message="known failure",
    )
    runner._append_entry(entries, failure, repository_root=tmp_path)
    assert runner._load_inflight(root) == intent
    clock.advance(60)
    fetcher = FakeFetcher(clock)
    progress = runner.execute_next_campaign_slot(
        execute_live_network=True,
        repository_root=tmp_path,
        fetcher=fetcher,
        clock=clock,
        sleeper=clock.sleep,
    )
    assert progress.completed_slots == 1
    assert fetcher.calls == 1
    assert not (root / runner.INFLIGHT_ATTEMPT_FILENAME).exists()


def test_persistence_failure_after_request_leaves_inflight_and_prevents_retry(
    tmp_path: Path, monkeypatch
) -> None:
    _tiny_plan(monkeypatch)
    clock = MutableClock()
    fetcher = FakeFetcher(clock)

    def fail_write(*args, **kwargs):
        raise runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            "synthetic durability failure"
        )

    monkeypatch.setattr(runner, "write_capture", fail_write)
    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="durability failure",
    ):
        runner.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=fetcher,
            clock=clock,
            sleeper=clock.sleep,
        )
    assert fetcher.calls == 1
    root = tmp_path / contract.CAPTURE_ROOT_RELATIVE
    assert (root / runner.INFLIGHT_ATTEMPT_FILENAME).exists()
    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="UNRESOLVED_INFLIGHT",
    ):
        runner.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=lambda **kwargs: pytest.fail("duplicate network forbidden"),
            clock=clock,
            sleeper=clock.sleep,
        )


def test_write_capture_rejects_raw_manifest_mismatch_before_persistence(
    tmp_path: Path, monkeypatch
) -> None:
    plan = _tiny_plan(monkeypatch)
    raw = b"expected"
    manifest = _manifest(plan[0], 1, T0, T0, raw)
    result = runner.FetchResult(
        plan[0],
        1,
        b"different",
        contract.validate_manifest(manifest, plan[0]),
    )
    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="differs",
    ):
        runner.write_capture(result, repository_root=tmp_path)
    capture = (
        tmp_path
        / contract.CAPTURE_ROOT_RELATIVE
        / plan[0].target_id
        / plan[0].slot
    )
    assert not capture.exists()


def test_partial_existing_slot_blocks_without_overwrite(
    tmp_path: Path, monkeypatch
) -> None:
    plan = _tiny_plan(monkeypatch)
    root = (
        tmp_path
        / contract.CAPTURE_ROOT_RELATIVE
        / plan[0].target_id
        / plan[0].slot
    )
    root.mkdir(parents=True)
    raw_path = root / contract.RAW_BODY_FILENAME
    raw_path.write_bytes(b"partial")
    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="UNINDEXED_CAPTURE",
    ):
        runner.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=lambda **kwargs: pytest.fail("network must not run"),
        )
    assert raw_path.read_bytes() == b"partial"


def test_indexed_capture_with_extra_file_blocks_before_network(
    tmp_path: Path, monkeypatch
) -> None:
    plan, clock, fetcher, _ = _capture_one_a(tmp_path, monkeypatch)
    root = tmp_path / contract.CAPTURE_ROOT_RELATIVE
    capture = root / plan[0].target_id / plan[0].slot
    (capture / "unexpected.bin").write_bytes(b"unexpected")
    calls = fetcher.calls
    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="unexpected evidence files",
    ):
        runner.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=fetcher,
            clock=clock,
            sleeper=clock.sleep,
        )
    assert fetcher.calls == calls


def test_complete_campaign_status_blocks_post_completion_rogue_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    plan = _tiny_plan(monkeypatch)
    clock = MutableClock()
    fetcher = FakeFetcher(clock)
    runner.execute_next_campaign_slot(
        execute_live_network=True,
        repository_root=tmp_path,
        fetcher=fetcher,
        clock=clock,
        sleeper=clock.sleep,
    )
    progress = runner.execute_next_campaign_slot(
        execute_live_network=True,
        repository_root=tmp_path,
        fetcher=fetcher,
        clock=clock,
        sleeper=clock.sleep,
    )
    assert progress.complete is True
    root = tmp_path / contract.CAPTURE_ROOT_RELATIVE
    (root / "post-completion-orphan").write_bytes(b"orphan")
    status = runner.campaign_status(repository_root=tmp_path)
    assert status["complete"] is False
    assert status["blocked"] is True
    assert status["block_reason"] == "UNINDEXED_CAPTURE_REQUIRES_RECONCILIATION"
    assert len(plan) == 2


def test_symlink_component_is_rejected(tmp_path: Path) -> None:
    cache = tmp_path / ".cache"
    cache.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (cache / "athena-research").symlink_to(outside, target_is_directory=True)
    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="symlink",
    ):
        runner.load_campaign_entries(repository_root=tmp_path)


def test_hardlinked_journal_is_rejected(tmp_path: Path) -> None:
    if not hasattr(os, "link"):
        pytest.skip("hard links unavailable")
    root = runner._ensure_campaign_root(repository_root=tmp_path)
    index = root / contract.CAMPAIGN_INDEX_FILENAME
    index.write_bytes(b"")
    os.link(index, root / "second-link")
    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="single-link",
    ):
        runner.load_campaign_entries(repository_root=tmp_path)


class FakeHTTPResponse:
    def __init__(
        self,
        body: bytes = b"Time = Time of match kick off\n",
        status: int = 200,
        content_type: str = "text/plain; charset=utf-8",
        extra_headers=(),
    ):
        self.status = status
        self._body = body
        self._headers = [
            ("Content-Type", content_type),
            ("Content-Length", str(len(body))),
            *extra_headers,
        ]

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


def test_transport_uses_exact_transparent_request_and_raw_bytes() -> None:
    FakeHTTPSConnection.instances.clear()
    FakeHTTPSConnection.response = FakeHTTPResponse()
    slot = contract.campaign_slots()[0]
    clock = MutableClock()
    started = clock()
    clock.advance(0.1)
    result = runner.fetch_primary_evidence(
        slot=slot,
        attempt=1,
        request_started_at=started,
        clock=clock,
        connection_factory=FakeHTTPSConnection,
    )
    connection = FakeHTTPSConnection.instances[-1]
    assert (connection.host, connection.port) == (
        "www.football-data.co.uk", 443
    )
    assert connection.requests == [
        ("GET", "/notes.txt", {"skip_accept_encoding": True})
    ]
    assert connection.headers == list(contract.REQUEST_HEADERS)
    assert connection.closed is True
    assert result.raw_body == b"Time = Time of match kick off\n"
    assert result.manifest["redirect_chain"] == ()
    assert result.manifest["tls_verified"] is True
    assert result.manifest["raw_sha256"] == hashlib.sha256(
        result.raw_body
    ).hexdigest()


def test_transport_refuses_redirect_compression_wrong_content_type() -> None:
    slot = contract.campaign_slots()[0]
    cases = (
        (FakeHTTPResponse(status=302), "HTTP_STATUS"),
        (
            FakeHTTPResponse(extra_headers=(("Content-Encoding", "gzip"),)),
            "CONTENT_ENCODING",
        ),
        (FakeHTTPResponse(content_type="text/html"), "CONTENT_TYPE"),
    )
    for response, kind in cases:
        FakeHTTPSConnection.response = response
        with pytest.raises(runner.PrimaryEvidenceRequestError) as exc:
            runner.fetch_primary_evidence(
                slot=slot,
                attempt=1,
                request_started_at=T0,
                clock=MutableClock(),
                connection_factory=FakeHTTPSConnection,
            )
        assert exc.value.kind == kind


def test_status_mode_is_network_inert(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        runner,
        "execute_campaign",
        lambda **kwargs: pytest.fail("live executor must not run in status mode"),
    )
    assert runner.main([
        "--status", "--repository-root", str(tmp_path)
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["network_acquisition_performed_by_this_status_command"] is False
    assert output["completed_slots"] == 0
    assert output["pr69_source_local_time_basis_resolved"] is False
