from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from domain import sportybet_fotmob_full_utc_reconciliation_receipt as receipt


class DummyResult:
    pass


def _bundle() -> receipt.FullUtcReconciliationSourceBundle:
    return receipt.FullUtcReconciliationSourceBundle(
        kickoff_promotion=object(),
        event_time_basis=object(),
        event_manifest=object(),
        event_inventory=object(),
        event_raw_html=b"<html>event</html>",
        terms_qualification=object(),
        terms_raw_html=b"<html>terms</html>",
        event_bridge=object(),
        sportradar_evidence=object(),
        sportradar_raw_response=b'{"sport_event":{}}',
        fotmob_admission_value=object(),
        fotmob_captures=((b"{}", object()),),
    )


def _install_reconciliation_stub(monkeypatch: pytest.MonkeyPatch, payload: bytes):
    result = DummyResult()
    calls = []

    def build(**kwargs):
        calls.append(kwargs)
        return result

    def canonical(value):
        assert value is result
        return payload

    monkeypatch.setattr(receipt.reconciliation, "build_full_utc_reconciliation", build)
    monkeypatch.setattr(receipt.reconciliation, "canonical_reconciliation_bytes", canonical)
    return result, calls


def test_store_executes_source_replay_and_publishes_exact_canonical_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b'{"disposition":"NO_EXACT_FULL_UTC_MATCH"}\n'
    result, calls = _install_reconciliation_stub(monkeypatch, payload)
    bundle = _bundle()

    directory, stored_result = receipt.store_reconciliation_receipt(
        source_bundle=bundle,
        repository_root=tmp_path,
    )

    assert stored_result is result
    assert directory.name == hashlib.sha256(payload).hexdigest()[:24]
    assert directory.parent == tmp_path / receipt.ALLOWED_OUTPUT_RELATIVE
    assert (directory / receipt.RECONCILIATION_FILENAME).read_bytes() == payload
    assert len(calls) == 2
    assert calls[0]["event_raw_html"] == bundle.event_raw_html
    assert calls[0]["terms_raw_html"] == bundle.terms_raw_html
    assert calls[0]["sportradar_raw_response"] == bundle.sportradar_raw_response
    assert calls[0]["fotmob_captures"] is bundle.fotmob_captures


def test_existing_identical_receipt_is_idempotent_only_after_source_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b'{"disposition":"AMBIGUOUS_EXACT_FULL_UTC_MATCH"}\n'
    result, calls = _install_reconciliation_stub(monkeypatch, payload)
    bundle = _bundle()

    first_dir, first_result = receipt.store_reconciliation_receipt(
        source_bundle=bundle,
        repository_root=tmp_path,
    )
    second_dir, second_result = receipt.store_reconciliation_receipt(
        source_bundle=bundle,
        repository_root=tmp_path,
    )

    assert first_dir == second_dir
    assert first_result is result
    assert second_result is result
    assert (first_dir / receipt.RECONCILIATION_FILENAME).read_bytes() == payload
    assert len(calls) == 4


def test_verify_replays_sources_and_rejects_tampered_stored_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b'{"disposition":"UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED"}\n'
    _install_reconciliation_stub(monkeypatch, payload)
    bundle = _bundle()
    directory, _ = receipt.store_reconciliation_receipt(
        source_bundle=bundle,
        repository_root=tmp_path,
    )
    (directory / receipt.RECONCILIATION_FILENAME).write_bytes(b"forged\n")

    with pytest.raises(
        receipt.SportyBetFotMobFullUtcReconciliationReceiptError,
        match="stale, tampered",
    ):
        receipt.verify_reconciliation_receipt_directory(
            directory,
            source_bundle=bundle,
            repository_root=tmp_path,
        )


def test_verify_rejects_unexpected_directory_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b'{"disposition":"NO_EXACT_FULL_UTC_MATCH"}\n'
    _install_reconciliation_stub(monkeypatch, payload)
    bundle = _bundle()
    directory, _ = receipt.store_reconciliation_receipt(
        source_bundle=bundle,
        repository_root=tmp_path,
    )
    (directory / "extra.txt").write_text("unexpected", encoding="utf-8")

    with pytest.raises(
        receipt.SportyBetFotMobFullUtcReconciliationReceiptError,
        match="contents mismatch",
    ):
        receipt.verify_reconciliation_receipt_directory(
            directory,
            source_bundle=bundle,
            repository_root=tmp_path,
        )


def test_wrong_output_root_fails_closed_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_reconciliation_stub(monkeypatch, b"{}\n")
    wrong = tmp_path / ".cache" / "athena-research" / "wrong-root"

    with pytest.raises(
        receipt.SportyBetFotMobFullUtcReconciliationReceiptError,
        match="reviewed exact reconciliation receipt root",
    ):
        receipt.store_reconciliation_receipt(
            source_bundle=_bundle(),
            repository_root=tmp_path,
            output_root=wrong,
        )
    assert not wrong.exists()


def test_source_reconciliation_failure_creates_no_receipt_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(**kwargs):
        raise receipt.reconciliation.SportyBetFotMobFullUtcReconciliationError(
            "source replay rejected"
        )

    monkeypatch.setattr(receipt.reconciliation, "build_full_utc_reconciliation", fail)

    with pytest.raises(
        receipt.SportyBetFotMobFullUtcReconciliationReceiptError,
        match="source replay rejected",
    ):
        receipt.store_reconciliation_receipt(
            source_bundle=_bundle(),
            repository_root=tmp_path,
        )
    assert not (tmp_path / receipt.ALLOWED_OUTPUT_RELATIVE).exists()
