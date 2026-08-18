from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from domain import reviewed_fixture_catalog_admission as fotmob_admission
from domain import sportybet_fotmob_full_utc_reconciliation as reconciliation
from scripts import execute_source_replayed_sportybet_fotmob_reconciliation as executor


def test_repository_root_requires_existing_directory(tmp_path: Path) -> None:
    assert executor._repository_root(tmp_path) == tmp_path.resolve()
    with pytest.raises(executor.SourceReplayedSportyBetFotMobExecutionError):
        executor._repository_root(tmp_path / "missing")


def test_path_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(
        executor.SourceReplayedSportyBetFotMobExecutionError,
        match="traversal",
    ):
        executor._path("../escape", repository=tmp_path, label="source")


def test_same_bytes_hash_requires_exact_manifest_identity() -> None:
    raw = b"evidence"
    executor._same_bytes_hash(
        raw,
        hashlib.sha256(raw).hexdigest(),
        len(raw),
        "source",
    )
    with pytest.raises(
        executor.SourceReplayedSportyBetFotMobExecutionError,
        match="do not match",
    ):
        executor._same_bytes_hash(raw, "0" * 64, len(raw), "source")
    with pytest.raises(
        executor.SourceReplayedSportyBetFotMobExecutionError,
        match="do not match",
    ):
        executor._same_bytes_hash(raw, hashlib.sha256(raw).hexdigest(), len(raw) + 1, "source")


def test_fotmob_capture_loader_requires_nonempty_sequence(tmp_path: Path) -> None:
    with pytest.raises(
        executor.SourceReplayedSportyBetFotMobExecutionError,
        match="at least one",
    ):
        executor._load_fotmob_capture_pairs((), repository=tmp_path)


def test_fotmob_capture_loader_rejects_duplicate_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = tmp_path / "capture"
    capture.mkdir()
    monkeypatch.setattr(
        executor,
        "verify_data_matches_capture_directory",
        lambda *args, **kwargs: SimpleNamespace(
            raw_sha256=hashlib.sha256(b"raw").hexdigest(),
            raw_size=3,
        ),
    )
    monkeypatch.setattr(executor, "_read_regular", lambda *args, **kwargs: b"raw")
    monkeypatch.setattr(
        executor,
        "canonical_data_matches_capture_manifest_bytes",
        lambda value: b"manifest\n",
    )
    with pytest.raises(
        executor.SourceReplayedSportyBetFotMobExecutionError,
        match="duplicate",
    ):
        executor._load_fotmob_capture_pairs((capture, capture), repository=tmp_path)


def _patch_source_chain(
    monkeypatch: pytest.MonkeyPatch,
    *,
    disposition: fotmob_admission.ReviewedFixtureCatalogAdmissionDisposition,
):
    event_manifest = object()
    event_inventory = object()
    event_raw = b"event"
    terms_qualification = object()
    terms_raw = b"terms"
    time_basis = object()
    event_bridge = object()
    sportradar_evidence = object()
    sportradar_raw = b"sportradar"
    promotion = object()
    admission = SimpleNamespace(decision=SimpleNamespace(disposition=disposition))
    captures = ((b"fotmob", object()),)

    monkeypatch.setattr(
        executor,
        "_load_sportybet_event_sources",
        lambda *args, **kwargs: (event_manifest, event_inventory, event_raw),
    )
    monkeypatch.setattr(
        executor,
        "_load_terms_sources",
        lambda *args, **kwargs: (terms_qualification, terms_raw),
    )
    monkeypatch.setattr(
        executor.event_time_basis,
        "build_event_local_time_basis",
        lambda **kwargs: time_basis,
    )
    monkeypatch.setattr(
        executor.event_identity,
        "build_sportradar_event_identity_bridge",
        lambda **kwargs: event_bridge,
    )
    monkeypatch.setattr(
        executor,
        "_load_sportradar_sources",
        lambda *args, **kwargs: (sportradar_evidence, sportradar_raw),
    )
    monkeypatch.setattr(
        executor.kickoff_promotion,
        "build_kickoff_identity_promotion",
        lambda **kwargs: promotion,
    )
    monkeypatch.setattr(
        executor,
        "revalidate_stored_admission_from_sources",
        lambda *args, **kwargs: admission,
    )
    monkeypatch.setattr(
        executor,
        "_load_fotmob_capture_pairs",
        lambda *args, **kwargs: captures,
    )
    return SimpleNamespace(
        event_manifest=event_manifest,
        event_inventory=event_inventory,
        event_raw=event_raw,
        terms_qualification=terms_qualification,
        terms_raw=terms_raw,
        time_basis=time_basis,
        event_bridge=event_bridge,
        sportradar_evidence=sportradar_evidence,
        sportradar_raw=sportradar_raw,
        promotion=promotion,
        admission=admission,
        captures=captures,
    )


def _build_kwargs(tmp_path: Path) -> dict[str, object]:
    return {
        "event_evidence_directory": "event-evidence",
        "terms_evidence_directory": "terms-evidence",
        "sportradar_evidence_directory": "sportradar-evidence",
        "fotmob_capture_directories": ("capture-one",),
        "fixture_review_decision_ledger": "review-ledger.json",
        "check_catalog": "catalog.json",
        "check_manifest": "catalog-manifest.json",
        "fotmob_admission_directory": "admission",
        "repository_root": tmp_path,
    }


def test_build_source_bundle_rebuilds_complete_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _patch_source_chain(
        monkeypatch,
        disposition=fotmob_admission.ReviewedFixtureCatalogAdmissionDisposition.ADMITTED,
    )
    bundle = executor.build_source_bundle(**_build_kwargs(tmp_path))
    assert bundle.kickoff_promotion is values.promotion
    assert bundle.event_time_basis is values.time_basis
    assert bundle.event_manifest is values.event_manifest
    assert bundle.event_inventory is values.event_inventory
    assert bundle.event_raw_html == values.event_raw
    assert bundle.terms_qualification is values.terms_qualification
    assert bundle.terms_raw_html == values.terms_raw
    assert bundle.event_bridge is values.event_bridge
    assert bundle.sportradar_evidence is values.sportradar_evidence
    assert bundle.sportradar_raw_response == values.sportradar_raw
    assert bundle.fotmob_admission_value is values.admission
    assert bundle.fotmob_captures == values.captures


def test_build_source_bundle_rejects_replayed_non_admitted_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_source_chain(
        monkeypatch,
        disposition=fotmob_admission.ReviewedFixtureCatalogAdmissionDisposition.REJECTED,
    )
    with pytest.raises(
        executor.SourceReplayedSportyBetFotMobExecutionError,
        match="ADMITTED",
    ):
        executor.build_source_bundle(**_build_kwargs(tmp_path))


def test_execute_stores_and_source_verifies_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = object()
    receipt_directory = tmp_path / ".cache" / "receipt"
    receipt_directory.mkdir(parents=True)
    matched = SimpleNamespace(to_dict=lambda: {"source_fixture_identifier": "123"})
    result = SimpleNamespace(
        disposition=reconciliation.FullUtcReconciliationDisposition.UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED,
        exact_match_count=1,
        fixture_reconciliation_authorized=True,
        matched_fixture=matched,
    )
    monkeypatch.setattr(executor, "build_source_bundle", lambda **kwargs: bundle)
    monkeypatch.setattr(
        executor.receipt,
        "store_reconciliation_receipt",
        lambda **kwargs: (receipt_directory, result),
    )
    monkeypatch.setattr(
        executor.receipt,
        "verify_reconciliation_receipt_directory",
        lambda *args, **kwargs: result,
    )
    monkeypatch.setattr(
        executor.reconciliation,
        "canonical_reconciliation_bytes",
        lambda value: b"canonical-result\n",
    )
    summary = executor.execute_source_replayed_reconciliation(**_build_kwargs(tmp_path))
    assert summary["status"] == executor.EXECUTION_STATUS
    assert summary["disposition"] == "UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED"
    assert summary["exact_match_count"] == 1
    assert summary["fixture_reconciliation_authorized"] is True
    assert summary["matched_fixture"] == {"source_fixture_identifier": "123"}
    assert summary["receipt_sha256"] == hashlib.sha256(b"canonical-result\n").hexdigest()
    assert summary["athena_network_acquisition_performed"] is False
    for key in (
        "bookmaker_equivalence_authorized",
        "canonical_market_mapping_authorized",
        "fresh_price_authorized",
        "pricing_authorized",
        "model_integration_authorized",
        "selection_authorized",
        "slip_construction_authorized",
        "booking_code_authorized",
        "sportybet_execution_authorized",
        "bet_authorized",
    ):
        assert summary[key] is False


def test_execute_rejects_post_store_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = object()
    receipt_directory = tmp_path / "receipt"
    receipt_directory.mkdir()
    stored = object()
    verified = object()
    monkeypatch.setattr(executor, "build_source_bundle", lambda **kwargs: bundle)
    monkeypatch.setattr(
        executor.receipt,
        "store_reconciliation_receipt",
        lambda **kwargs: (receipt_directory, stored),
    )
    monkeypatch.setattr(
        executor.receipt,
        "verify_reconciliation_receipt_directory",
        lambda *args, **kwargs: verified,
    )
    monkeypatch.setattr(
        executor.reconciliation,
        "canonical_reconciliation_bytes",
        lambda value: b"stored\n" if value is stored else b"verified\n",
    )
    with pytest.raises(
        executor.SourceReplayedSportyBetFotMobExecutionError,
        match="post-store",
    ):
        executor.execute_source_replayed_reconciliation(**_build_kwargs(tmp_path))


def test_main_returns_two_on_fail_closed_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(**kwargs):
        raise executor.SourceReplayedSportyBetFotMobExecutionError("blocked")

    monkeypatch.setattr(executor, "execute_source_replayed_reconciliation", fail)
    code = executor.main(
        [
            "--event-evidence-directory", "event",
            "--terms-evidence-directory", "terms",
            "--sportradar-evidence-directory", "sportradar",
            "--fotmob-capture-directory", "capture",
            "--fixture-review-decision-ledger", "ledger",
            "--check-catalog", "catalog",
            "--check-manifest", "manifest",
            "--fotmob-admission-directory", "admission",
        ]
    )
    assert code == 2
    assert "ERROR: blocked" in capsys.readouterr().err


def test_main_emits_canonical_json_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    expected = {"status": "ok", "bet_authorized": False}
    monkeypatch.setattr(
        executor,
        "execute_source_replayed_reconciliation",
        lambda **kwargs: expected,
    )
    code = executor.main(
        [
            "--event-evidence-directory", "event",
            "--terms-evidence-directory", "terms",
            "--sportradar-evidence-directory", "sportradar",
            "--fotmob-capture-directory", "capture",
            "--fixture-review-decision-ledger", "ledger",
            "--check-catalog", "catalog",
            "--check-manifest", "manifest",
            "--fotmob-admission-directory", "admission",
        ]
    )
    assert code == 0
    assert capsys.readouterr().out == json.dumps(
        expected,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"
