from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from domain import sportybet_official_time_semantics as semantics


UTC = dt.timezone.utc
OBSERVED = dt.datetime(2026, 8, 18, 16, 0, tzinfo=UTC)
IMPORTED = dt.datetime(2026, 8, 18, 16, 1, tzinfo=UTC)


def _html(*statements: str) -> bytes:
    body = "".join(f"<p>{statement}</p>" for statement in statements)
    return f"<!doctype html><html><body>{body}</body></html>".encode("utf-8")


def _store(
    tmp_path: Path,
    raw: bytes,
) -> tuple[Path, semantics.SportyBetOfficialTimeSemanticsQualification]:
    return semantics.store_official_time_semantics_evidence(
        raw,
        source_url=semantics.SOURCE_URL,
        observed_at_user_attested=OBSERVED,
        imported_at_utc=IMPORTED,
        attestation=semantics.ATTESTATION,
        repository_root=tmp_path,
    )


def test_conflicting_global_zone_statements_fail_closed() -> None:
    conflicting = (
        "All times stated on the Website and/or referred to by SportyBet staff "
        "relate to UTC unless stated otherwise."
    )
    with pytest.raises(
        semantics.SportyBetOfficialTimeSemanticsError,
        match="conflicting or not exact GMT",
    ):
        semantics.build_qualification(
            _html(semantics.EXPECTED_STATEMENT, conflicting),
            source_url=semantics.SOURCE_URL,
            observed_at_user_attested=OBSERVED,
            imported_at_utc=IMPORTED,
            attestation=semantics.ATTESTATION,
        )


def test_second_file_write_failure_removes_partial_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_write = semantics._write_exclusive
    call_count = 0

    def injected_write(path: Path, content: bytes) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise semantics.SportyBetOfficialTimeSemanticsError(
                "injected second-write failure"
            )
        real_write(path, content)

    monkeypatch.setattr(semantics, "_write_exclusive", injected_write)
    with pytest.raises(
        semantics.SportyBetOfficialTimeSemanticsError,
        match="injected second-write failure",
    ):
        _store(tmp_path, _html(semantics.EXPECTED_STATEMENT))

    root = tmp_path / semantics.ALLOWED_OUTPUT_RELATIVE
    assert root.is_dir()
    assert list(root.iterdir()) == []


def test_verification_failure_after_two_writes_removes_partial_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_verify = semantics.verify_evidence_directory
    verification_calls = 0

    def injected_verify(
        evidence_directory: object,
        *,
        allowed_root: Path,
    ) -> semantics.SportyBetOfficialTimeSemanticsQualification:
        nonlocal verification_calls
        verification_calls += 1
        if verification_calls == 1:
            raise semantics.SportyBetOfficialTimeSemanticsError(
                "injected verification failure"
            )
        return real_verify(evidence_directory, allowed_root=allowed_root)

    monkeypatch.setattr(semantics, "verify_evidence_directory", injected_verify)
    with pytest.raises(
        semantics.SportyBetOfficialTimeSemanticsError,
        match="injected verification failure",
    ):
        _store(tmp_path, _html(semantics.EXPECTED_STATEMENT))

    root = tmp_path / semantics.ALLOWED_OUTPUT_RELATIVE
    assert root.is_dir()
    assert list(root.iterdir()) == []


def test_cleanup_failure_is_never_silently_suppressed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_write(path: Path, content: bytes) -> None:
        del path, content
        raise semantics.SportyBetOfficialTimeSemanticsError("injected write failure")

    def fail_cleanup(directory: Path, root: Path) -> None:
        del directory, root
        raise semantics.SportyBetOfficialTimeSemanticsError(
            "injected cleanup failure"
        )

    monkeypatch.setattr(semantics, "_write_exclusive", fail_write)
    monkeypatch.setattr(semantics, "_cleanup_partial_directory", fail_cleanup)
    with pytest.raises(
        semantics.SportyBetOfficialTimeSemanticsError,
        match="write failed and cleanup also failed",
    ):
        _store(tmp_path, _html(semantics.EXPECTED_STATEMENT))


def test_extra_directory_entry_blocks_replay_without_deleting_evidence(
    tmp_path: Path,
) -> None:
    directory, _ = _store(tmp_path, _html(semantics.EXPECTED_STATEMENT))
    extra = directory / "unexpected.txt"
    extra.write_text("unexpected", encoding="utf-8")

    with pytest.raises(
        semantics.SportyBetOfficialTimeSemanticsError,
        match="contents mismatch",
    ):
        semantics.verify_evidence_directory(
            directory,
            allowed_root=tmp_path / semantics.ALLOWED_OUTPUT_RELATIVE,
        )

    assert extra.read_text(encoding="utf-8") == "unexpected"


def test_existing_complete_evidence_is_reverified_before_idempotent_return(
    tmp_path: Path,
) -> None:
    raw = _html(semantics.EXPECTED_STATEMENT)
    directory, _ = _store(tmp_path, raw)
    qualification_path = directory / semantics.QUALIFICATION_FILENAME
    qualification_path.write_bytes(qualification_path.read_bytes() + b" ")

    with pytest.raises(semantics.SportyBetOfficialTimeSemanticsError):
        _store(tmp_path, raw)


def test_protocol_forbids_retroactive_or_perpetual_semantics_promotion() -> None:
    protocol_path = Path(
        "artifacts/research-protocols/sportybet-official-time-semantics-v1.json"
    )
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    assert protocol["temporal_scope"] == (
        "OBSERVED_PROVIDER_PAGE_ONLY_NO_RETROACTIVE_OR_PERPETUAL_CLAIM"
    )
    assert protocol[
        "event_application_requires_temporally_compatible_terms_evidence"
    ] is True
    assert protocol["specific_event_time_basis_authorized"] is False
