from __future__ import annotations

import ast
import datetime
import json
from pathlib import Path

import pytest

import domain.fotmob_ordinary_ft_source_history_acquisition_protocol as pr101
import domain.fotmob_ordinary_ft_source_history_acquisition_runner as module
from domain.fotmob_ordinary_ft_source_history_acquisition_runner import (
    NEXT_REQUIRED_BOUNDARY,
    PR101_PROTOCOL_SHA256,
    PR101_PROTOCOL_SIZE,
    REQUIRED_DATE_COUNT,
    REQUIRED_SUCCESSFUL_CAPTURE_COUNT,
    RUNNER_ID,
    RUNNER_STATE,
    CampaignSlot,
    FotMobOrdinaryFtSourceHistoryAcquisitionRunnerError,
    FotMobOrdinaryFtSourceHistoryPairWindowError,
    build_attempt_failed_entry,
    build_slot_blocked_entry,
    build_slot_succeeded_entry,
    campaign_dates,
    campaign_progress,
    campaign_slots,
    canonical_campaign_journal_entry_bytes,
    parse_campaign_evidence_bytes,
    runner_state,
    seconds_until_next_request_eligible,
    split_campaign_evidence_bytes,
)


UTC = datetime.timezone.utc
T0 = datetime.datetime(2026, 8, 15, 10, 0, tzinfo=UTC)
RAW_SHA = "1" * 64
MANIFEST_SHA = "2" * 64
CAPTURE_ID = "a" * 24


def _tiny_plan(monkeypatch) -> tuple[CampaignSlot, CampaignSlot]:
    plan = (
        CampaignSlot(1, "20200801", "A"),
        CampaignSlot(2, "20200801", "B"),
    )
    monkeypatch.setattr(module, "campaign_slots", lambda: plan)
    return plan


def _success(
    entries,
    *,
    slot,
    attempt=1,
    start=T0,
    observed=None,
    recorded=None,
    capture_id=CAPTURE_ID,
    raw_sha=RAW_SHA,
    manifest_sha=MANIFEST_SHA,
):
    observed = observed or (start + datetime.timedelta(seconds=1))
    recorded = recorded or (observed + datetime.timedelta(seconds=1))
    return build_slot_succeeded_entry(
        entries,
        slot=slot,
        attempt=attempt,
        attempt_started_at=start,
        recorded_at=recorded,
        capture_id=capture_id,
        raw_sha256=raw_sha,
        raw_size=123,
        manifest_sha256=manifest_sha,
        observed_at=observed,
    )


def test_runner_state_binds_exact_pr101_without_granting_authority() -> None:
    state = runner_state()
    assert state["runner_id"] == RUNNER_ID
    assert state["runner_state"] == RUNNER_STATE == (
        "IMPLEMENTED_NOT_EXECUTED_HISTORICAL_COVERAGE_UNPROVEN"
    )
    assert state["pr101_protocol_sha256"] == PR101_PROTOCOL_SHA256 == (
        "cfd8542df66c9e8fbe748f0559d67c336d41e441f3b4de8d6601ac1087cad3a6"
    )
    assert state["pr101_protocol_size"] == PR101_PROTOCOL_SIZE == 8511
    assert state["request_identity"] == {"timezone": "UTC", "ccode3": "NGA"}
    assert state["network_acquisition_performed"] is False
    assert state["history_rows_materialized"] == 0
    assert state["historical_coverage_proven"] is False
    assert set(state["downstream_authority"].values()) == {False}
    assert state["next_required_boundary"] == NEXT_REQUIRED_BOUNDARY


def test_frozen_plan_has_exact_2205_dates_and_all_a_then_all_b() -> None:
    dates = campaign_dates()
    slots = campaign_slots()
    assert len(dates) == REQUIRED_DATE_COUNT == 2205
    assert dates[0] == "20200801"
    assert dates[-1] == "20260814"
    assert len(slots) == REQUIRED_SUCCESSFUL_CAPTURE_COUNT == 4410
    assert slots[0] == CampaignSlot(1, "20200801", "A")
    assert slots[2204] == CampaignSlot(2205, "20260814", "A")
    assert slots[2205] == CampaignSlot(2206, "20200801", "B")
    assert slots[-1] == CampaignSlot(4410, "20260814", "B")
    assert tuple(slot.slot for slot in slots[:2205]) == ("A",) * 2205
    assert tuple(slot.slot for slot in slots[2205:]) == ("B",) * 2205


def test_success_index_and_failure_journal_round_trip_one_global_hash_chain(
    monkeypatch,
) -> None:
    plan = _tiny_plan(monkeypatch)
    failure = build_attempt_failed_entry(
        (),
        slot=plan[0],
        attempt=1,
        attempt_started_at=T0,
        recorded_at=T0 + datetime.timedelta(seconds=1),
        error_kind="ACQUISITION_ATTEMPT_FAILED",
        error_message="temporary failure",
    )
    success_a = _success(
        (failure,),
        slot=plan[0],
        attempt=2,
        start=T0 + datetime.timedelta(seconds=61),
        observed=T0 + datetime.timedelta(seconds=62),
        recorded=T0 + datetime.timedelta(seconds=63),
    )
    success_b = _success(
        (failure, success_a),
        slot=plan[1],
        start=T0 + datetime.timedelta(seconds=362),
        observed=T0 + datetime.timedelta(seconds=363),
        recorded=T0 + datetime.timedelta(seconds=364),
        capture_id="b" * 24,
        raw_sha="3" * 64,
        manifest_sha="4" * 64,
    )
    entries = (failure, success_a, success_b)

    index_bytes, failure_bytes = split_campaign_evidence_bytes(entries)
    assert index_bytes.count(b"\n") == 2
    assert failure_bytes.count(b"\n") == 1
    parsed = parse_campaign_evidence_bytes(index_bytes, failure_bytes)
    assert tuple(parsed) == entries
    assert parsed[0]["previous_entry_sha256"] == "0" * 64
    assert parsed[1]["previous_entry_sha256"] == parsed[0]["entry_sha256"]
    assert parsed[2]["previous_entry_sha256"] == parsed[1]["entry_sha256"]
    assert campaign_progress(parsed).complete is True


def test_attempts_are_contiguous_and_third_failure_blocks_resume(monkeypatch) -> None:
    plan = _tiny_plan(monkeypatch)
    entries = ()
    for attempt in range(1, 4):
        entry = build_attempt_failed_entry(
            entries,
            slot=plan[0],
            attempt=attempt,
            attempt_started_at=T0 + datetime.timedelta(seconds=attempt * 100),
            recorded_at=T0 + datetime.timedelta(seconds=attempt * 100 + 1),
            error_kind="ACQUISITION_ATTEMPT_FAILED",
            error_message=f"failure {attempt}",
        )
        entries = (*entries, entry)

    progress = campaign_progress(entries)
    assert progress.completed_slots == 0
    assert progress.blocked is True
    assert progress.block_reason == "ATTEMPTS_EXHAUSTED"
    assert progress.next_attempt is None

    with pytest.raises(FotMobOrdinaryFtSourceHistoryAcquisitionRunnerError):
        build_attempt_failed_entry(
            entries,
            slot=plan[0],
            attempt=3,
            attempt_started_at=T0,
            recorded_at=T0,
            error_kind="ACQUISITION_ATTEMPT_FAILED",
            error_message="duplicate third attempt",
        )


def test_resume_targets_exact_next_slot_and_attempt(monkeypatch) -> None:
    plan = _tiny_plan(monkeypatch)
    first_failure = build_attempt_failed_entry(
        (),
        slot=plan[0],
        attempt=1,
        attempt_started_at=T0,
        recorded_at=T0 + datetime.timedelta(seconds=1),
        error_kind="ACQUISITION_ATTEMPT_FAILED",
        error_message="retry me",
    )
    progress = campaign_progress((first_failure,))
    assert progress.next_slot == plan[0]
    assert progress.next_attempt == 2

    success = _success(
        (first_failure,),
        slot=plan[0],
        attempt=2,
        start=T0 + datetime.timedelta(seconds=61),
        observed=T0 + datetime.timedelta(seconds=62),
        recorded=T0 + datetime.timedelta(seconds=63),
    )
    progress = campaign_progress((first_failure, success))
    assert progress.next_slot == plan[1]
    assert progress.next_attempt == 1


def test_pair_window_waits_to_300_and_accepts_exact_boundaries(monkeypatch) -> None:
    plan = _tiny_plan(monkeypatch)
    success_a = _success(
        (),
        slot=plan[0],
        observed=T0 + datetime.timedelta(seconds=1),
        recorded=T0 + datetime.timedelta(seconds=2),
    )
    entries = (success_a,)

    now = T0 + datetime.timedelta(seconds=101)
    assert seconds_until_next_request_eligible(entries, now) == pytest.approx(200.0)

    success_b = _success(
        entries,
        slot=plan[1],
        start=T0 + datetime.timedelta(seconds=300),
        observed=T0 + datetime.timedelta(seconds=301),
        recorded=T0 + datetime.timedelta(seconds=302),
        capture_id="b" * 24,
        raw_sha="3" * 64,
        manifest_sha="4" * 64,
    )
    assert campaign_progress((*entries, success_b)).complete is True

    success_b_max = _success(
        entries,
        slot=plan[1],
        start=T0 + datetime.timedelta(seconds=86400),
        observed=T0 + datetime.timedelta(seconds=86401),
        recorded=T0 + datetime.timedelta(seconds=86402),
        capture_id="c" * 24,
        raw_sha="5" * 64,
        manifest_sha="6" * 64,
    )
    assert campaign_progress((*entries, success_b_max)).complete is True


def test_pair_window_rejects_too_early_and_too_late(monkeypatch) -> None:
    plan = _tiny_plan(monkeypatch)
    success_a = _success(
        (),
        slot=plan[0],
        observed=T0 + datetime.timedelta(seconds=1),
        recorded=T0 + datetime.timedelta(seconds=2),
    )
    entries = (success_a,)

    with pytest.raises(FotMobOrdinaryFtSourceHistoryPairWindowError, match="300-second"):
        _success(
            entries,
            slot=plan[1],
            start=T0 + datetime.timedelta(seconds=100),
            observed=T0 + datetime.timedelta(seconds=300),
            recorded=T0 + datetime.timedelta(seconds=301),
            capture_id="b" * 24,
            raw_sha="3" * 64,
            manifest_sha="4" * 64,
        )

    with pytest.raises(FotMobOrdinaryFtSourceHistoryPairWindowError, match="86400-second"):
        seconds_until_next_request_eligible(
            entries, T0 + datetime.timedelta(seconds=86402)
        )


def test_retry_delay_and_inter_request_spacing_are_resumable(monkeypatch) -> None:
    plan = _tiny_plan(monkeypatch)
    failure = build_attempt_failed_entry(
        (),
        slot=plan[0],
        attempt=1,
        attempt_started_at=T0,
        recorded_at=T0 + datetime.timedelta(seconds=0.25),
        error_kind="ACQUISITION_ATTEMPT_FAILED",
        error_message="network timeout",
    )
    assert seconds_until_next_request_eligible(
        (failure,), T0 + datetime.timedelta(seconds=0.25)
    ) == pytest.approx(60.0)
    assert seconds_until_next_request_eligible(
        (failure,), T0 + datetime.timedelta(seconds=60.25)
    ) == pytest.approx(0.0)


def test_explicit_block_entry_is_terminal(monkeypatch) -> None:
    plan = _tiny_plan(monkeypatch)
    blocked = build_slot_blocked_entry(
        (),
        slot=plan[0],
        recorded_at=T0,
        error_kind="PAIR_WINDOW_EXPIRED_BEFORE_REQUEST",
        error_message="cannot continue",
    )
    progress = campaign_progress((blocked,))
    assert progress.blocked is True
    assert progress.block_reason == "PAIR_WINDOW_EXPIRED_BEFORE_REQUEST"

    with pytest.raises(FotMobOrdinaryFtSourceHistoryAcquisitionRunnerError):
        _success((blocked,), slot=plan[0])


def test_noncanonical_torn_wrong_file_and_hash_tampering_fail_closed(monkeypatch) -> None:
    plan = _tiny_plan(monkeypatch)
    success = _success((), slot=plan[0])
    line = canonical_campaign_journal_entry_bytes(success)

    with pytest.raises(FotMobOrdinaryFtSourceHistoryAcquisitionRunnerError, match="torn trailing"):
        parse_campaign_evidence_bytes(line[:-1], b"")

    with pytest.raises(FotMobOrdinaryFtSourceHistoryAcquisitionRunnerError, match="wrong file"):
        parse_campaign_evidence_bytes(b"", line)

    parsed = json.loads(line)
    parsed["detail"]["raw_size"] = 999
    tampered = (json.dumps(parsed, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with pytest.raises(FotMobOrdinaryFtSourceHistoryAcquisitionRunnerError, match="SHA-256 mismatch"):
        parse_campaign_evidence_bytes(tampered, b"")

    pretty = json.dumps(json.loads(line), indent=2).encode() + b"\n"
    with pytest.raises(FotMobOrdinaryFtSourceHistoryAcquisitionRunnerError):
        parse_campaign_evidence_bytes(pretty, b"")


def test_protocol_drift_blocks_runner(monkeypatch) -> None:
    monkeypatch.setattr(pr101, "PROTOCOL_SHA256", "0" * 64)
    with pytest.raises(
        FotMobOrdinaryFtSourceHistoryAcquisitionRunnerError,
        match="PR101 acquisition protocol identity changed",
    ):
        runner_state()


def test_domain_runner_is_network_free_and_contains_no_downstream_imports() -> None:
    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
            imported_modules.add(node.module)

    assert imported_roots.isdisjoint(
        {
            "http", "requests", "httpx", "aiohttp", "socket", "subprocess",
            "playwright", "providers", "workers", "api", "services", "engine",
            "models", "database", "repositories", "scripts",
        }
    )
    assert all(
        token not in name
        for name in imported_modules
        for token in ("score_matrix", "probability", "pricing", "selection", "betting", "sportybet")
    )
