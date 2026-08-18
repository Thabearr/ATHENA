from __future__ import annotations

from pathlib import Path

import pytest

from domain import sportybet_fotmob_full_utc_reconciliation_receipt as receipt


class DummyResult:
    pass


def _bundle(**changes) -> receipt.FullUtcReconciliationSourceBundle:
    values = dict(
        kickoff_promotion=object(),
        event_time_basis=object(),
        event_manifest=object(),
        event_inventory=object(),
        event_raw_html=b"event",
        terms_qualification=object(),
        terms_raw_html=b"terms",
        event_bridge=object(),
        sportradar_evidence=object(),
        sportradar_raw_response=b"sportradar",
        fotmob_admission_value=object(),
        fotmob_captures=((b"fotmob", object()),),
    )
    values.update(changes)
    return receipt.FullUtcReconciliationSourceBundle(**values)


def _mutable_stub(monkeypatch: pytest.MonkeyPatch, state: dict[str, bytes]):
    result = DummyResult()

    def build(**kwargs):
        return result

    def canonical(value):
        assert value is result
        return state["payload"]

    monkeypatch.setattr(receipt.reconciliation, "build_full_utc_reconciliation", build)
    monkeypatch.setattr(receipt.reconciliation, "canonical_reconciliation_bytes", canonical)
    return result


def test_source_bundle_rejects_non_exact_raw_bytes_and_capture_container() -> None:
    with pytest.raises(receipt.SportyBetFotMobFullUtcReconciliationReceiptError):
        _bundle(event_raw_html=bytearray(b"event"))
    with pytest.raises(receipt.SportyBetFotMobFullUtcReconciliationReceiptError):
        _bundle(terms_raw_html="terms")
    with pytest.raises(receipt.SportyBetFotMobFullUtcReconciliationReceiptError):
        _bundle(sportradar_raw_response=memoryview(b"x"))
    with pytest.raises(receipt.SportyBetFotMobFullUtcReconciliationReceiptError):
        _bundle(fotmob_captures=[])
    with pytest.raises(receipt.SportyBetFotMobFullUtcReconciliationReceiptError):
        _bundle(fotmob_captures=())


def test_receipt_hash_helpers_require_bounded_nonempty_exact_bytes() -> None:
    for invalid in (
        b"",
        "{}",
        bytearray(b"{}"),
        b"x" * (receipt.MAX_RECEIPT_BYTES + 1),
    ):
        with pytest.raises(receipt.SportyBetFotMobFullUtcReconciliationReceiptError):
            receipt.receipt_sha256_from_bytes(invalid)


def test_source_drift_cannot_reuse_prior_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {"payload": b'{"source":"first"}\n'}
    _mutable_stub(monkeypatch, state)
    bundle = _bundle()
    directory, _ = receipt.store_reconciliation_receipt(
        source_bundle=bundle,
        repository_root=tmp_path,
    )

    state["payload"] = b'{"source":"second"}\n'
    with pytest.raises(
        receipt.SportyBetFotMobFullUtcReconciliationReceiptError,
        match="directory identity",
    ):
        receipt.verify_reconciliation_receipt_directory(
            directory,
            source_bundle=bundle,
            repository_root=tmp_path,
        )


def test_identifier_collision_never_overwrites_existing_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {"payload": b'{"source":"first"}\n'}
    _mutable_stub(monkeypatch, state)
    bundle = _bundle()
    monkeypatch.setattr(
        receipt,
        "receipt_identifier_from_bytes",
        lambda payload: "0" * 24,
    )

    directory, _ = receipt.store_reconciliation_receipt(
        source_bundle=bundle,
        repository_root=tmp_path,
    )
    original = (directory / receipt.RECONCILIATION_FILENAME).read_bytes()
    state["payload"] = b'{"source":"different"}\n'

    with pytest.raises(
        receipt.SportyBetFotMobFullUtcReconciliationReceiptError,
        match="stale, tampered",
    ):
        receipt.store_reconciliation_receipt(
            source_bundle=bundle,
            repository_root=tmp_path,
        )
    assert (directory / receipt.RECONCILIATION_FILENAME).read_bytes() == original


def test_partial_write_failure_is_cleaned_before_error_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {"payload": b'{"source":"clean-me"}\n'}
    _mutable_stub(monkeypatch, state)
    bundle = _bundle()
    expected_id = receipt.receipt_identifier_from_bytes(state["payload"])

    def partial_then_fail(path: Path, payload: bytes) -> None:
        path.write_bytes(payload[:3])
        raise receipt.SportyBetFotMobFullUtcReconciliationReceiptError(
            "injected write failure"
        )

    monkeypatch.setattr(receipt, "_write_exclusive", partial_then_fail)

    with pytest.raises(
        receipt.SportyBetFotMobFullUtcReconciliationReceiptError,
        match="injected write failure",
    ):
        receipt.store_reconciliation_receipt(
            source_bundle=bundle,
            repository_root=tmp_path,
        )
    assert not (tmp_path / receipt.ALLOWED_OUTPUT_RELATIVE / expected_id).exists()


def test_cleanup_failure_is_not_suppressed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {"payload": b'{"source":"cleanup-fail"}\n'}
    _mutable_stub(monkeypatch, state)

    def fail_write(path: Path, payload: bytes) -> None:
        raise receipt.SportyBetFotMobFullUtcReconciliationReceiptError(
            "write failure"
        )

    def fail_cleanup(directory: Path, root: Path) -> None:
        raise receipt.SportyBetFotMobFullUtcReconciliationReceiptError(
            "cleanup failure"
        )

    monkeypatch.setattr(receipt, "_write_exclusive", fail_write)
    monkeypatch.setattr(receipt, "_cleanup_partial_directory", fail_cleanup)

    with pytest.raises(
        receipt.SportyBetFotMobFullUtcReconciliationReceiptError,
        match="partial cleanup also failed",
    ):
        receipt.store_reconciliation_receipt(
            source_bundle=_bundle(),
            repository_root=tmp_path,
        )


def test_concurrent_directory_creation_is_never_cleaned_as_our_partial_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {"payload": b'{"source":"concurrent"}\n'}
    _mutable_stub(monkeypatch, state)
    bundle = _bundle()
    root = tmp_path / receipt.ALLOWED_OUTPUT_RELATIVE
    root.mkdir(parents=True)
    expected_id = receipt.receipt_identifier_from_bytes(state["payload"])
    target = root / expected_id
    original_mkdir = Path.mkdir

    def concurrent_mkdir(self: Path, *args, **kwargs) -> None:
        if self == target:
            original_mkdir(self)
            (self / "foreign.txt").write_text("owned by concurrent writer", encoding="utf-8")
            raise FileExistsError("simulated concurrent creator won the race")
        original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", concurrent_mkdir)

    with pytest.raises(
        receipt.SportyBetFotMobFullUtcReconciliationReceiptError,
        match="could not durably publish",
    ):
        receipt.store_reconciliation_receipt(
            source_bundle=bundle,
            repository_root=tmp_path,
        )

    assert target.is_dir()
    assert (target / "foreign.txt").read_text(encoding="utf-8") == "owned by concurrent writer"


def test_receipt_directory_traversal_and_outside_paths_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {"payload": b'{"source":"paths"}\n'}
    _mutable_stub(monkeypatch, state)
    bundle = _bundle()
    directory, _ = receipt.store_reconciliation_receipt(
        source_bundle=bundle,
        repository_root=tmp_path,
    )

    with pytest.raises(receipt.SportyBetFotMobFullUtcReconciliationReceiptError):
        receipt.verify_reconciliation_receipt_directory(
            Path("..") / directory.name,
            source_bundle=bundle,
            repository_root=tmp_path,
        )

    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(receipt.SportyBetFotMobFullUtcReconciliationReceiptError):
        receipt.verify_reconciliation_receipt_directory(
            outside,
            source_bundle=bundle,
            repository_root=tmp_path,
        )


def test_verifier_has_no_storage_only_call_path(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        receipt.verify_reconciliation_receipt_directory(
            tmp_path,
            repository_root=tmp_path,
        )
