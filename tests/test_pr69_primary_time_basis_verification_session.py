from __future__ import annotations

import datetime
import hashlib
from pathlib import Path

import pytest

import domain.pr69_primary_time_basis_evidence_acquisition_protocol as pr124
import domain.pr69_primary_time_basis_evidence_acquisition_runner as contract
import scripts.run_pr69_primary_time_basis_evidence_acquisition as runner

UTC = datetime.timezone.utc
T0 = datetime.datetime(2026, 8, 16, 9, 0, tzinfo=UTC)


def _count_deep_revalidations(monkeypatch: pytest.MonkeyPatch):
    original = pr124.build_pr69_primary_time_basis_evidence_acquisition_protocol
    calls = 0

    def counted():
        nonlocal calls
        calls += 1
        return original()

    monkeypatch.setattr(
        pr124,
        "build_pr69_primary_time_basis_evidence_acquisition_protocol",
        counted,
    )

    def current() -> int:
        return calls

    return current


def test_bounded_session_reuses_only_deep_upstream_revalidation(monkeypatch) -> None:
    calls = _count_deep_revalidations(monkeypatch)

    with contract.upstream_verification_session():
        contract.runner_descriptor()
        contract.campaign_slots()
        contract.campaign_progress(())
        assert calls() == 1

    contract.runner_descriptor()
    assert calls() == 2


def test_bounded_session_still_fails_closed_on_direct_pr124_identity_mutation(
    monkeypatch,
) -> None:
    with contract.upstream_verification_session():
        monkeypatch.setattr(pr124, "PROTOCOL_SIZE", pr124.PROTOCOL_SIZE + 1)
        with pytest.raises(
            contract.PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError,
            match="identity changed",
        ):
            contract.runner_descriptor()


def test_status_uses_one_deep_revalidation(monkeypatch, tmp_path: Path) -> None:
    calls = _count_deep_revalidations(monkeypatch)

    status = runner.campaign_status(repository_root=tmp_path)

    assert status["completed_slots"] == 0
    assert status["complete"] is False
    assert calls() == 1


def test_reviewed_transport_refreshes_before_and_after_request(
    monkeypatch, tmp_path: Path
) -> None:
    slot = contract.campaign_slots()[0]
    raw = b"reviewed-evidence"
    refresh_calls = 0

    def counted_refresh() -> None:
        nonlocal refresh_calls
        refresh_calls += 1

    def reviewed_fetcher(*, slot, attempt, request_started_at, clock):
        observed = clock().astimezone(UTC)
        manifest = {
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
            "request_started_at_utc": contract.serialize_utc(request_started_at),
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
        return runner.FetchResult(
            slot=slot,
            attempt=attempt,
            raw_body=raw,
            manifest=contract.validate_manifest(manifest, slot),
        )

    monkeypatch.setattr(contract, "refresh_upstream_verification_session", counted_refresh)
    monkeypatch.setattr(runner, "fetch_primary_evidence", reviewed_fetcher)
    root = runner._ensure_campaign_root(repository_root=tmp_path)

    with contract.upstream_verification_session():
        progress = runner._execute_next_slot_locked(
            repository_root=tmp_path,
            root=root,
            fetcher=runner.fetch_primary_evidence,
            clock=lambda: T0,
            sleeper=lambda _seconds: None,
        )

    assert progress.completed_slots == 1
    assert progress.next_slot is not None
    assert progress.next_slot.ordinal == 2
    assert refresh_calls == 2
