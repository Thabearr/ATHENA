from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from domain import current_shadow_sportybet_pc_upcoming_discovery as source
from domain import current_shadow_sportybet_pc_upcoming_reconciliation as runtime
from domain import current_shadow_fixture_identity_compatibility as identity_compatibility
from scripts import audit_p4_4p_pc_upcoming_preparse_response_evidence as audit


def _raw_page(page_num: int, *, total: int, count: int = 100, invalid_id: bool = False) -> bytes:
    first_event = (page_num - 1) * 100 + 1
    events = []
    for number in range(first_event, first_event + count):
        events.append({
            "eventId": f"sr:match:{80000000 + number}",
            "homeTeamId": f"sr:competitor:{90000000 + number * 2}",
            "homeTeamName": f"Home {number}",
            "awayTeamId": f"sr:competitor:{90000001 + number * 2}",
            "awayTeamName": f"Away {number}",
            "estimateStartTime": 1_798_000_000_000 + number * 1000,
            "status": 0,
            "matchStatus": "Not start",
            "bookingStatus": "Booked",
        })
    payload = {
        "bizCode": 10000,
        "data": {
            "totalNum": total,
            "tournaments": [{
                "id": "not-provider-native" if invalid_id else "sr:tournament:242",
                "name": "Synthetic League",
                "categoryId": "sr:category:26",
                "categoryName": "Synthetic Country",
                "events": events,
            }],
        },
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _capture_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, list[bytes]]:
    root = tmp_path.resolve()
    root.mkdir(parents=True, exist_ok=True)
    raw_pages = [_raw_page(i, total=757, invalid_id=(i == 7)) for i in range(1, 8)]

    def fetch(page_num: int, nonce: int):
        return raw_pages[page_num - 1], datetime.now(timezone.utc)

    monkeypatch.setattr(source, "_fetch_page", fetch)
    with pytest.raises(runtime.PcUpcomingRuntimeReconciliationError, match="PC_UPCOMING_RUNTIME_SOURCE_INCOMPLETE"):
        runtime.capture_current_pc_upcoming_discovery(
            repository_root=root,
            execute_live_network=True,
        )
    return root / source.EVIDENCE_ROOT, raw_pages


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _rewrite_sealed(path: Path, value: dict) -> None:
    semantic = dict(value)
    semantic.pop("canonical_sha256", None)
    path.write_bytes(runtime._canonical(runtime._seal_document(semantic)) + b"\n")


def test_runtime_contract_binds_evidence_first_semantics_and_immutable_source_v1() -> None:
    identities = runtime.validate_contract()
    assert runtime.POLICY_ID == "ATHENA_CURRENT_SHADOW_PC_UPCOMING_DISCOVERY_RECONCILIATION_V1"
    assert runtime.calculate_policy_sha256() == runtime.PINNED_POLICY_SHA256 == (
        "a5c42439e894d33950b5cba608dcd5a031896e7a8e75c6bf613b2314497b1c24"
    )
    assert identities["preparse_response_evidence"]["every_successful_runtime_http_response_persisted_before_semantic_parse"] is True
    assert identities["preparse_response_evidence"]["parse_failure_semantic_acceptance"] is False
    assert source.POLICY_ID == "ATHENA_CURRENT_SHADOW_PC_UPCOMING_GLOBAL_FOOTBALL_SOURCE_V1"
    assert source.calculate_policy_sha256() == source.PINNED_POLICY_SHA256 == (
        "63799058bec00abefb8d9b2ec9ba6dcad0c6e4775a54f17b07c0018e543ec075"
    )


def test_six_valid_then_invalid_seventh_response_is_saved_before_parse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[str, int]] = []
    identity_calls: list[str] = []
    raw_pages = [_raw_page(i, total=757, invalid_id=(i == 7)) for i in range(1, 8)]

    def fetch(page_num: int, nonce: int):
        events.append(("transport-return", page_num))
        return raw_pages[page_num - 1], datetime.now(timezone.utc)

    original_write_raw = runtime._write_raw_response_exclusive
    original_write_journal = runtime._write_raw_response_observations
    original_parse = source.parse_page
    original_failure = runtime._persist_parse_failure

    def write_raw(path: Path, raw: bytes) -> None:
        original_write_raw(path, raw)
        events.append(("raw-fsynced", int(path.name[5:8])))

    def write_journal(attempt_root: Path, attempt_index: int, rows):
        result = original_write_journal(attempt_root, attempt_index, rows)
        events.append(("journal-committed", int(rows[-1]["page_num"])))
        return result

    def parse(raw: bytes, **kwargs):
        events.append(("parse-start", kwargs["page_num"]))
        return original_parse(raw, **kwargs)

    def persist_failure(**kwargs):
        result = original_failure(**kwargs)
        events.append(("parse-failure-committed", kwargs["response"]["page_num"]))
        return result

    monkeypatch.setattr(source, "_fetch_page", fetch)
    monkeypatch.setattr(runtime, "_write_raw_response_exclusive", write_raw)
    monkeypatch.setattr(runtime, "_write_raw_response_observations", write_journal)
    monkeypatch.setattr(source, "parse_page", parse)
    monkeypatch.setattr(runtime, "_persist_parse_failure", persist_failure)
    monkeypatch.setattr(identity_compatibility, "begin_identity_scope", lambda *_args, **_kwargs: identity_calls.append("identity"))

    root = tmp_path.resolve()
    with pytest.raises(runtime.PcUpcomingRuntimeReconciliationError, match="PC_UPCOMING_RUNTIME_SOURCE_INCOMPLETE:PcUpcomingDiscoveryError:tournament.id is not an exact provider-native ID"):
        runtime.capture_current_pc_upcoming_discovery(repository_root=root, execute_live_network=True)

    evidence_root = root / source.EVIDENCE_ROOT
    attempt = evidence_root / runtime.RUNTIME_ATTEMPTS_DIRECTORY / "attempt-001"
    journal = _read(attempt / runtime.RAW_RESPONSE_JOURNAL_FILENAME)
    attempt_receipt = _read(attempt / "attempt-receipt.json")
    failure = _read(attempt / runtime.PARSE_FAILURE_FILENAME)
    rows = journal["responses"]
    assert len(rows) == 7
    assert len(_read(attempt / "page-observations.json")["pages"]) == 6
    assert attempt_receipt["successful_page_response_count"] == 7
    assert attempt_receipt["parsed_page_count"] == 6
    assert attempt_receipt["status"] == "FAILED_SOURCE_OR_EVIDENCE_ERROR"
    assert attempt_receipt["accepted_by_runtime"] is False
    assert failure["page_num"] == 7
    assert failure["exception_type"] == "PcUpcomingDiscoveryError"
    assert failure["exception_message"] == "tournament.id is not an exact provider-native ID"
    assert failure["semantic_acceptance"] is False
    assert failure["provider_absence_authority"] is False
    assert failure["reconciliation_authority"] is False
    assert failure["fresh_epoch_authorized"] is False
    page7 = attempt / rows[6]["raw_relative_path"]
    assert page7.read_bytes() == raw_pages[6]
    assert hashlib.sha256(page7.read_bytes()).hexdigest() == failure["raw_sha256"] == rows[6]["raw_sha256"]
    assert not (attempt / "manifest.json").exists()
    assert not (evidence_root / "manifest.json").exists()
    assert not hasattr(runtime, "captured_event_count")
    assert identity_calls == []
    assert not (evidence_root / runtime.RUNTIME_ATTEMPTS_DIRECTORY / "attempt-002").exists()
    assert events.index(("raw-fsynced", 7)) < events.index(("journal-committed", 7)) < events.index(("parse-start", 7)) < events.index(("parse-failure-committed", 7))
    stabilization = _read(evidence_root / runtime.STABILIZATION_RECEIPT_FILENAME)
    assert stabilization["attempt_count"] == 1
    assert stabilization["final_state"] == "FAILED_SOURCE_OR_EVIDENCE_ERROR"
    replay = runtime.verify_runtime_capture_stabilization(repository_root=root)
    assert replay["accepted_attempt_index"] is None
    assert replay["provider_absence_from_failed_attempt"] is False


def test_preparse_evidence_write_failure_prevents_semantic_parse_and_epoch_two(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    parsed: list[int] = []
    fetches: list[int] = []
    monkeypatch.setattr(source, "_fetch_page", lambda page_num, nonce: (
        fetches.append(page_num) or _raw_page(page_num, total=1, count=1), datetime.now(timezone.utc)
    ))
    monkeypatch.setattr(runtime, "_write_raw_response_exclusive", lambda *_args: (_ for _ in ()).throw(
        runtime.PcUpcomingRuntimeReconciliationError("forced pre-parse evidence persistence failure")
    ))
    original_parse = source.parse_page
    monkeypatch.setattr(source, "parse_page", lambda raw, **kwargs: (parsed.append(kwargs["page_num"]), original_parse(raw, **kwargs))[1])

    with pytest.raises(runtime.PcUpcomingRuntimeReconciliationError, match="forced pre-parse evidence persistence failure"):
        runtime.capture_current_pc_upcoming_discovery(repository_root=tmp_path.resolve(), execute_live_network=True)
    assert fetches == [1]
    assert parsed == []
    evidence_root = tmp_path / source.EVIDENCE_ROOT
    stabilization = _read(evidence_root / runtime.STABILIZATION_RECEIPT_FILENAME)
    assert stabilization["attempt_count"] == 1
    assert stabilization["final_state"] == "FAILED_SOURCE_OR_EVIDENCE_ERROR"
    assert not (evidence_root / "manifest.json").exists()
    assert not (evidence_root / runtime.RUNTIME_ATTEMPTS_DIRECTORY / "attempt-002").exists()


def test_accepted_epoch_records_every_response_without_changing_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw_pages = [_raw_page(1, total=101), _raw_page(2, total=101, count=1)]
    fetches: list[int] = []

    def fetch(page_num: int, nonce: int):
        fetches.append(page_num)
        return raw_pages[page_num - 1], datetime.now(timezone.utc)

    monkeypatch.setattr(source, "_fetch_page", fetch)
    root, manifest = runtime.capture_current_pc_upcoming_discovery(
        repository_root=tmp_path.resolve(), execute_live_network=True
    )
    attempt = root / runtime.RUNTIME_ATTEMPTS_DIRECTORY / "attempt-001"
    journal = _read(attempt / runtime.RAW_RESPONSE_JOURNAL_FILENAME)
    parsed = _read(attempt / "page-observations.json")["pages"]
    assert fetches == [1, 2]
    assert len(journal["responses"]) == len(parsed) == manifest.captured_page_count == 2
    assert all(row["semantic_parse_attempted"] is True and row["semantic_parse_succeeded"] is True for row in journal["responses"])
    assert not (attempt / runtime.PARSE_FAILURE_FILENAME).exists()
    assert not (root / runtime.PARSE_FAILURE_FILENAME).exists()
    assert runtime.verify_current_pc_upcoming_discovery(repository_root=tmp_path).to_dict() == manifest.to_dict()
    assert runtime.verify_runtime_capture_stabilization(repository_root=tmp_path)["accepted_attempt_index"] == 1


def test_public_source_v1_still_rejects_invalid_provider_native_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = _raw_page(1, total=1, count=1, invalid_id=True)
    monkeypatch.setattr(source, "_fetch_page", lambda *_args: (raw, datetime.now(timezone.utc)))
    with pytest.raises(source.PcUpcomingDiscoveryError, match="tournament.id is not an exact provider-native ID"):
        source.capture_current_pc_upcoming_discovery(repository_root=tmp_path.resolve(), execute_live_network=True)
    assert not (tmp_path / source.EVIDENCE_ROOT / "manifest.json").exists()
    assert not (tmp_path / source.EVIDENCE_ROOT / "pages" / "page-001.raw.json").exists()


@pytest.mark.parametrize("tamper", [
    "raw_bytes", "raw_sha", "request_nonce", "request_target", "observed_at", "page_num",
    "exception_message", "failure_raw_sha", "semantic_acceptance", "authority",
    "remove_raw", "orphan_raw", "journal_count",
])
def test_offline_replay_rejects_preparse_evidence_tampering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper: str) -> None:
    evidence_root, _raw_pages = _capture_failure(tmp_path, monkeypatch)
    attempt = evidence_root / runtime.RUNTIME_ATTEMPTS_DIRECTORY / "attempt-001"
    journal_path = attempt / runtime.RAW_RESPONSE_JOURNAL_FILENAME
    journal = _read(journal_path)
    row = journal["responses"][-1]
    failure_path = attempt / runtime.PARSE_FAILURE_FILENAME
    failure = _read(failure_path)
    if tamper == "raw_bytes":
        raw_path = attempt / row["raw_relative_path"]
        raw_path.write_bytes(raw_path.read_bytes() + b" ")
    elif tamper == "raw_sha":
        row["raw_sha256"] = "0" * 64
        _rewrite_sealed(journal_path, journal)
    elif tamper == "request_nonce":
        row["request_nonce"] += 1
        _rewrite_sealed(journal_path, journal)
    elif tamper == "request_target":
        row["request_target"] += "&pageNum=1"
        _rewrite_sealed(journal_path, journal)
    elif tamper == "observed_at":
        row["observed_at"] = "2020-01-01T00:00:00Z"
        _rewrite_sealed(journal_path, journal)
    elif tamper == "page_num":
        row["page_num"] = 8
        _rewrite_sealed(journal_path, journal)
    elif tamper == "exception_message":
        failure["exception_message"] = "different failure"
        _rewrite_sealed(failure_path, failure)
    elif tamper == "failure_raw_sha":
        failure["raw_sha256"] = "0" * 64
        _rewrite_sealed(failure_path, failure)
    elif tamper == "semantic_acceptance":
        failure["semantic_acceptance"] = True
        _rewrite_sealed(failure_path, failure)
    elif tamper == "authority":
        failure["provider_absence_authority"] = True
        failure["reconciliation_authority"] = True
        _rewrite_sealed(failure_path, failure)
    elif tamper == "remove_raw":
        (attempt / row["raw_relative_path"]).unlink()
    elif tamper == "orphan_raw":
        (attempt / runtime.RAW_RESPONSE_DIRECTORY / "page-999.raw.json").write_bytes(b"orphan")
    elif tamper == "journal_count":
        journal["responses"].pop()
        _rewrite_sealed(journal_path, journal)
    with pytest.raises(runtime.PcUpcomingRuntimeReconciliationError):
        runtime.verify_runtime_capture_stabilization(repository_root=tmp_path)


def test_p4_4p_architecture_audit_pins_current_runtime_and_historical_p4_4o() -> None:
    result = audit.audit(Path.cwd())
    assert result["status"] == "PASSED"
    assert result["receipt_sha256"] == "d7d8c9733b41b0146e73940769f66c6103c48c87bed054ecbbadb512aae1ffae"
    assert result["runtime_policy_sha256"] == runtime.PINNED_POLICY_SHA256
    assert result["provider_acquisition_during_implementation"] is False
    assert audit.audit_historical(Path.cwd())["failed_proof_exact_offending_value_known"] is False


def test_p4_4p_receipt_hash_rejects_mutation(tmp_path: Path) -> None:
    receipt = _read(Path.cwd() / audit.RECEIPT_PATH)
    receipt["failed_proof_exact_offending_value_known"] = True
    target = tmp_path / audit.RECEIPT_PATH
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(audit.P44PError, match="canonical SHA mismatch"):
        audit._verify_receipt(tmp_path)
