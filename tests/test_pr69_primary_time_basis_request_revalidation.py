from __future__ import annotations

import datetime
import hashlib
from pathlib import Path

import pytest

import domain.pr69_primary_time_basis_evidence_acquisition_runner as contract
import scripts.run_pr69_primary_time_basis_evidence_acquisition as runner

UTC = datetime.timezone.utc
T0 = datetime.datetime(2026, 8, 16, 9, 0, tzinfo=UTC)


class MutableClock:
    def __init__(self, value: datetime.datetime = T0) -> None:
        self.value = value
        self.sleeps: list[float] = []

    def __call__(self) -> datetime.datetime:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += datetime.timedelta(seconds=seconds)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.advance(seconds)


def _tiny_pair_plan(monkeypatch) -> tuple[contract.CampaignSlot, ...]:
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
    def __init__(self, clock: MutableClock) -> None:
        self.clock = clock
        self.calls = 0

    def __call__(self, *, slot, attempt, request_started_at, clock):
        self.calls += 1
        self.clock.advance(0.25)
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


def test_clock_rollback_after_inflight_persistence_blocks_before_network(
    tmp_path: Path, monkeypatch
) -> None:
    _tiny_pair_plan(monkeypatch)
    clock = MutableClock()
    root = runner._ensure_campaign_root(repository_root=tmp_path)
    original_create = runner._create_inflight

    def create_then_rollback(*args, **kwargs):
        intent = original_create(*args, **kwargs)
        clock.value = kwargs["intent_started_at"] - datetime.timedelta(seconds=1)
        return intent

    monkeypatch.setattr(runner, "_create_inflight", create_then_rollback)
    calls = 0

    def forbidden_fetch(**kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("network must not run after clock rollback")

    with pytest.raises(
        contract.PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError,
        match="inflight intent timestamp",
    ):
        runner._execute_next_slot_locked(
            repository_root=tmp_path,
            root=root,
            fetcher=forbidden_fetch,
            clock=clock,
            sleeper=clock.sleep,
        )

    assert calls == 0
    assert not (root / runner.INFLIGHT_ATTEMPT_FILENAME).exists()
    assert runner.load_campaign_entries(repository_root=tmp_path) == ()


def test_pair_window_expiry_during_inflight_persistence_blocks_before_network(
    tmp_path: Path, monkeypatch
) -> None:
    plan = _tiny_pair_plan(monkeypatch)
    clock = MutableClock()
    root = runner._ensure_campaign_root(repository_root=tmp_path)
    fetcher = FakeFetcher(clock)

    first = runner._execute_next_slot_locked(
        repository_root=tmp_path,
        root=root,
        fetcher=fetcher,
        clock=clock,
        sleeper=clock.sleep,
    )
    assert first.completed_slots == 1
    entries = runner.load_campaign_entries(repository_root=tmp_path)
    observed_a = contract.parse_utc(
        entries[-1]["detail"]["observed_at_utc"], "observed_at_utc"
    )
    clock.value = observed_a + datetime.timedelta(
        seconds=contract.MINIMUM_PAIR_SEPARATION_SECONDS
    )

    original_create = runner._create_inflight

    def create_then_expire(*args, **kwargs):
        intent = original_create(*args, **kwargs)
        clock.value = observed_a + datetime.timedelta(
            seconds=contract.MAXIMUM_PAIR_SEPARATION_SECONDS + 1
        )
        return intent

    monkeypatch.setattr(runner, "_create_inflight", create_then_expire)
    calls = 0

    def forbidden_fetch(**kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("network must not run after pair-window expiry")

    with pytest.raises(
        runner.PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        match="pair window blocked before request",
    ):
        runner._execute_next_slot_locked(
            repository_root=tmp_path,
            root=root,
            fetcher=forbidden_fetch,
            clock=clock,
            sleeper=clock.sleep,
        )

    assert calls == 0
    entries = runner.load_campaign_entries(repository_root=tmp_path)
    assert entries[-1]["event_type"] == "SLOT_BLOCKED"
    assert entries[-1]["target_id"] == plan[1].target_id
    assert entries[-1]["slot"] == "B"
    assert entries[-1]["detail"]["error_kind"] == (
        "PAIR_WINDOW_EXPIRED_BEFORE_REQUEST"
    )
    assert contract.campaign_progress(entries).blocked is True
    assert not (root / runner.INFLIGHT_ATTEMPT_FILENAME).exists()
