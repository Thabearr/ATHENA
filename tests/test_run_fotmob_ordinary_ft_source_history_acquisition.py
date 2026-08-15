from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import domain.fotmob_ordinary_ft_source_history_acquisition_runner as runner_domain
import scripts.run_fotmob_ordinary_ft_source_history_acquisition as module
from domain.fotmob_ordinary_ft_source_history_acquisition_runner import (
    CampaignSlot,
    campaign_progress,
)


UTC = datetime.timezone.utc
T0 = datetime.datetime(2026, 8, 15, 10, 0, tzinfo=UTC)


class _MutableClock:
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


class _FakeTransport:
    def __init__(self, clock: _MutableClock, fail_calls: set[int] | None = None):
        self.clock = clock
        self.fail_calls = set(fail_calls or ())
        self.calls = 0
        self.fetch_args: list[dict[str, str]] = []
        self.responses: dict[Path, SimpleNamespace] = {}

    def fetch(self, **kwargs):
        self.calls += 1
        self.fetch_args.append(dict(kwargs))
        self.clock.advance(0.25)
        if self.calls in self.fail_calls:
            raise module.capture_runtime.FotMobDataMatchesNetworkError("synthetic timeout")
        return SimpleNamespace(
            network_acquisition_performed=True,
            observed_at=self.clock(),
        )

    def write(
        self,
        response,
        *,
        request_date,
        timezone,
        ccode3,
        repository_root,
    ):
        capture_id = f"{self.calls:024x}"
        capture = (
            Path(repository_root)
            / module.capture_runtime.ALLOWED_OUTPUT_RELATIVE
            / request_date
            / capture_id
        )
        capture.mkdir(parents=True, exist_ok=False)
        self.responses[capture] = response
        return capture, None

    def verify(self, *, capture_directory, request_date, repository_root):
        response = self.responses[Path(capture_directory)]
        return (
            SimpleNamespace(
                request_date=request_date,
                timezone="UTC",
                ccode3="NGA",
                observed_at=response.observed_at,
                raw_sha256=f"{self.calls % 10}" * 64,
                raw_size=100 + self.calls,
            ),
            f"{(self.calls + 1) % 10}" * 64,
        )


def _tiny_plan(monkeypatch):
    plan = (
        CampaignSlot(1, "20200801", "A"),
        CampaignSlot(2, "20200801", "B"),
    )
    monkeypatch.setattr(runner_domain, "campaign_slots", lambda: plan)
    return plan


def _campaign_root(tmp_path: Path) -> Path:
    return tmp_path / runner_domain.CAMPAIGN_ROOT_RELATIVE


def _inflight_path(tmp_path: Path) -> Path:
    return _campaign_root(tmp_path) / module.INFLIGHT_ATTEMPT_FILENAME


def test_live_execution_requires_explicit_true(tmp_path: Path) -> None:
    with pytest.raises(
        module.FotMobOrdinaryFtSourceHistoryAcquisitionLiveRunnerError,
        match="requires exact True",
    ):
        module.execute_next_campaign_slot(
            execute_live_network=False,
            repository_root=tmp_path,
        )


def test_one_slot_reuses_exact_utc_nga_transport_and_appends_success_index(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plan = _tiny_plan(monkeypatch)
    clock = _MutableClock()
    transport = _FakeTransport(clock)

    progress = module.execute_next_campaign_slot(
        execute_live_network=True,
        repository_root=tmp_path,
        fetcher=transport.fetch,
        writer=transport.write,
        verifier=transport.verify,
        clock=clock,
        sleeper=clock.sleep,
    )

    assert progress.completed_slots == 1
    assert progress.next_slot == plan[1]
    assert transport.fetch_args == [
        {"request_date": "20200801", "timezone": "UTC", "ccode3": "NGA"}
    ]

    root = _campaign_root(tmp_path)
    index = root / runner_domain.CAMPAIGN_INDEX_FILENAME
    failures = root / runner_domain.FAILURE_JOURNAL_FILENAME
    assert index.exists()
    assert index.read_bytes().count(b"\n") == 1
    assert not failures.exists()
    assert not (root / runner_domain.CAMPAIGN_LOCK_FILENAME).exists()
    assert not _inflight_path(tmp_path).exists()

    entries = module.load_campaign_entries(repository_root=tmp_path)
    assert len(entries) == 1
    assert entries[0]["event_type"] == "SLOT_SUCCEEDED"
    assert entries[0]["detail"]["capture_id"] == "000000000000000000000001"


def test_failed_attempt_is_durable_then_exact_60_second_retry_succeeds(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _tiny_plan(monkeypatch)
    clock = _MutableClock()
    transport = _FakeTransport(clock, fail_calls={1})

    progress = module.execute_next_campaign_slot(
        execute_live_network=True,
        repository_root=tmp_path,
        fetcher=transport.fetch,
        writer=transport.write,
        verifier=transport.verify,
        clock=clock,
        sleeper=clock.sleep,
    )

    assert progress.completed_slots == 1
    assert transport.calls == 2
    assert clock.sleeps == pytest.approx([60.0])
    entries = module.load_campaign_entries(repository_root=tmp_path)
    assert [entry["event_type"] for entry in entries] == [
        "ATTEMPT_FAILED",
        "SLOT_SUCCEEDED",
    ]
    assert entries[0]["attempt"] == 1
    assert entries[1]["attempt"] == 2
    assert entries[1]["previous_entry_sha256"] == entries[0]["entry_sha256"]
    assert not _inflight_path(tmp_path).exists()

    root = _campaign_root(tmp_path)
    assert (root / runner_domain.FAILURE_JOURNAL_FILENAME).exists()
    assert (root / runner_domain.CAMPAIGN_INDEX_FILENAME).exists()


def test_three_failed_attempts_use_60_then_300_and_block(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _tiny_plan(monkeypatch)
    clock = _MutableClock()
    transport = _FakeTransport(clock, fail_calls={1, 2, 3})

    with pytest.raises(
        module.FotMobOrdinaryFtSourceHistoryAcquisitionLiveRunnerError,
        match="ATTEMPTS_EXHAUSTED",
    ):
        module.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=transport.fetch,
            writer=transport.write,
            verifier=transport.verify,
            clock=clock,
            sleeper=clock.sleep,
        )

    assert transport.calls == 3
    assert clock.sleeps == pytest.approx([60.0, 300.0])
    entries = module.load_campaign_entries(repository_root=tmp_path)
    assert [entry["attempt"] for entry in entries] == [1, 2, 3]
    progress = campaign_progress(entries)
    assert progress.blocked is True
    assert progress.block_reason == "ATTEMPTS_EXHAUSTED"
    assert not _inflight_path(tmp_path).exists()


def test_slot_b_waits_for_frozen_300_second_pair_minimum(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plan = _tiny_plan(monkeypatch)
    clock = _MutableClock()
    transport = _FakeTransport(clock)

    first = module.execute_next_campaign_slot(
        execute_live_network=True,
        repository_root=tmp_path,
        fetcher=transport.fetch,
        writer=transport.write,
        verifier=transport.verify,
        clock=clock,
        sleeper=clock.sleep,
    )
    assert first.next_slot == plan[1]

    second = module.execute_next_campaign_slot(
        execute_live_network=True,
        repository_root=tmp_path,
        fetcher=transport.fetch,
        writer=transport.write,
        verifier=transport.verify,
        clock=clock,
        sleeper=clock.sleep,
    )
    assert second.complete is True
    assert clock.sleeps == pytest.approx([300.0])
    entries = module.load_campaign_entries(repository_root=tmp_path)
    from domain.fotmob_data_matches_capture import parse_utc_timestamp

    separation = (
        parse_utc_timestamp(entries[1]["detail"]["observed_at_utc"], "b")
        - parse_utc_timestamp(entries[0]["detail"]["observed_at_utc"], "a")
    ).total_seconds()
    assert separation >= 300


def test_expired_slot_b_window_is_journaled_and_no_network_request_occurs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plan = _tiny_plan(monkeypatch)
    clock = _MutableClock()
    transport = _FakeTransport(clock)

    first = module.execute_next_campaign_slot(
        execute_live_network=True,
        repository_root=tmp_path,
        fetcher=transport.fetch,
        writer=transport.write,
        verifier=transport.verify,
        clock=clock,
        sleeper=clock.sleep,
    )
    assert first.next_slot == plan[1]
    assert transport.calls == 1
    clock.advance(86401)

    with pytest.raises(
        module.FotMobOrdinaryFtSourceHistoryAcquisitionLiveRunnerError,
        match="pair window blocked",
    ):
        module.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=transport.fetch,
            writer=transport.write,
            verifier=transport.verify,
            clock=clock,
            sleeper=clock.sleep,
        )

    assert transport.calls == 1
    entries = module.load_campaign_entries(repository_root=tmp_path)
    assert entries[-1]["event_type"] == "SLOT_BLOCKED"
    assert entries[-1]["detail"]["error_kind"] == "PAIR_WINDOW_EXPIRED_BEFORE_REQUEST"
    assert campaign_progress(entries).blocked is True


def test_chunked_execution_stops_after_requested_new_successes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plan = _tiny_plan(monkeypatch)
    clock = _MutableClock()
    transport = _FakeTransport(clock)

    progress = module.execute_campaign(
        execute_live_network=True,
        repository_root=tmp_path,
        max_successful_slots=1,
        fetcher=transport.fetch,
        writer=transport.write,
        verifier=transport.verify,
        clock=clock,
        sleeper=clock.sleep,
    )
    assert progress.completed_slots == 1
    assert progress.next_slot == plan[1]
    assert transport.calls == 1


def test_crash_after_durable_capture_leaves_inflight_marker_and_blocks_duplicate_request(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _tiny_plan(monkeypatch)
    clock = _MutableClock()
    transport = _FakeTransport(clock)

    def crash_after_write(**kwargs):
        raise module.FotMobOrdinaryFtSourceHistoryAcquisitionLiveRunnerError(
            "synthetic crash after durable capture"
        )

    with pytest.raises(
        module.FotMobOrdinaryFtSourceHistoryAcquisitionLiveRunnerError,
        match="synthetic crash",
    ):
        module.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=transport.fetch,
            writer=transport.write,
            verifier=crash_after_write,
            clock=clock,
            sleeper=clock.sleep,
        )

    assert transport.calls == 1
    assert _inflight_path(tmp_path).exists()
    captures = list(
        (tmp_path / module.capture_runtime.ALLOWED_OUTPUT_RELATIVE / "20200801").iterdir()
    )
    assert len(captures) == 1
    assert module.load_campaign_entries(repository_root=tmp_path) == ()

    second_fetch_called = False

    def second_fetch(**kwargs):
        nonlocal second_fetch_called
        second_fetch_called = True
        raise AssertionError("unresolved in-flight attempt must block before fetch")

    with pytest.raises(
        module.FotMobOrdinaryFtSourceHistoryAcquisitionLiveRunnerError,
        match="UNRESOLVED_INFLIGHT_ATTEMPT_REQUIRES_RECONCILIATION",
    ):
        module.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=second_fetch,
            clock=clock,
            sleeper=clock.sleep,
        )
    assert second_fetch_called is False

    status = module.campaign_status(repository_root=tmp_path)
    assert status["blocked"] is True
    assert status["block_reason"] == "UNRESOLVED_INFLIGHT_ATTEMPT_REQUIRES_RECONCILIATION"
    assert status["inflight_attempt"]["request_date"] == "20200801"
    assert status["inflight_attempt"]["slot"] == "A"
    assert status["inflight_attempt"]["attempt"] == 1


def test_crash_after_outcome_append_is_auto_cleaned_without_repeating_completed_slot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plan = _tiny_plan(monkeypatch)
    clock = _MutableClock()
    transport = _FakeTransport(clock)
    original_remove = module._remove_inflight_intent

    def crash_before_marker_cleanup(root, expected):
        raise module.FotMobOrdinaryFtSourceHistoryAcquisitionLiveRunnerError(
            "synthetic crash after outcome append"
        )

    monkeypatch.setattr(module, "_remove_inflight_intent", crash_before_marker_cleanup)
    with pytest.raises(
        module.FotMobOrdinaryFtSourceHistoryAcquisitionLiveRunnerError,
        match="after outcome append",
    ):
        module.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=transport.fetch,
            writer=transport.write,
            verifier=transport.verify,
            clock=clock,
            sleeper=clock.sleep,
        )

    assert transport.calls == 1
    assert _inflight_path(tmp_path).exists()
    entries = module.load_campaign_entries(repository_root=tmp_path)
    assert len(entries) == 1
    assert entries[0]["event_type"] == "SLOT_SUCCEEDED"

    status = module.campaign_status(repository_root=tmp_path)
    assert status["block_reason"] == "RECORDED_OUTCOME_PENDING_SAFE_MARKER_CLEANUP"

    monkeypatch.setattr(module, "_remove_inflight_intent", original_remove)
    progress = module.execute_next_campaign_slot(
        execute_live_network=True,
        repository_root=tmp_path,
        fetcher=transport.fetch,
        writer=transport.write,
        verifier=transport.verify,
        clock=clock,
        sleeper=clock.sleep,
    )
    assert progress.complete is True
    assert transport.calls == 2
    assert transport.fetch_args[0]["request_date"] == plan[0].request_date
    assert transport.fetch_args[1]["request_date"] == plan[1].request_date
    assert not _inflight_path(tmp_path).exists()


def test_tampered_inflight_marker_fails_closed(tmp_path: Path, monkeypatch) -> None:
    _tiny_plan(monkeypatch)
    clock = _MutableClock()
    transport = _FakeTransport(clock)

    def crash(**kwargs):
        raise module.FotMobOrdinaryFtSourceHistoryAcquisitionLiveRunnerError("stop")

    with pytest.raises(module.FotMobOrdinaryFtSourceHistoryAcquisitionLiveRunnerError):
        module.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=transport.fetch,
            writer=transport.write,
            verifier=crash,
            clock=clock,
            sleeper=clock.sleep,
        )

    path = _inflight_path(tmp_path)
    marker = json.loads(path.read_text(encoding="utf-8"))
    marker["attempt"] = 2
    path.write_text(
        json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        module.FotMobOrdinaryFtSourceHistoryAcquisitionLiveRunnerError,
        match="SHA-256 mismatch",
    ):
        module.campaign_status(repository_root=tmp_path)


def test_existing_lock_refuses_concurrent_execution(tmp_path: Path, monkeypatch) -> None:
    _tiny_plan(monkeypatch)
    root = _campaign_root(tmp_path)
    root.mkdir(parents=True)
    (root / runner_domain.CAMPAIGN_LOCK_FILENAME).write_text("stale-or-live\n")

    called = False

    def fetch(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("must not run")

    with pytest.raises(
        module.FotMobOrdinaryFtSourceHistoryAcquisitionLiveRunnerError,
        match="campaign lock already exists",
    ):
        module.execute_next_campaign_slot(
            execute_live_network=True,
            repository_root=tmp_path,
            fetcher=fetch,
        )
    assert called is False


@pytest.mark.skipif(os.name == "nt", reason="symlink behavior requires POSIX test semantics")
def test_symlinked_campaign_root_fails_closed(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    cache = tmp_path / ".cache"
    cache.mkdir()
    research = cache / "athena-research"
    research.mkdir()
    target = research / "fotmob-ordinary-ft-source-history-campaign-v1"
    target.symlink_to(outside, target_is_directory=True)

    with pytest.raises(
        module.FotMobOrdinaryFtSourceHistoryAcquisitionLiveRunnerError,
        match="symlink",
    ):
        module.campaign_status(repository_root=tmp_path)


def test_status_is_network_free_on_empty_campaign(tmp_path: Path) -> None:
    status = module.campaign_status(repository_root=tmp_path)
    assert status["completed_slots"] == 0
    assert status["total_slots"] == 4410
    assert status["complete"] is False
    assert status["blocked"] is False
    assert status["inflight_attempt"] is None
    assert status["network_acquisition_performed_by_this_status_command"] is False
    assert status["historical_coverage_proven"] is False


def test_cli_requires_explicit_mode_and_rejects_chunking_status() -> None:
    parser = module.build_parser()
    with pytest.raises(SystemExit) as missing:
        parser.parse_args([])
    assert missing.value.code == 2

    with pytest.raises(SystemExit) as invalid:
        module.main(["--status", "--max-successful-slots", "1"])
    assert invalid.value.code == 2
