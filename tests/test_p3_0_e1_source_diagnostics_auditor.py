from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
import zipfile

import pytest

from scripts import analyze_p3_0_e1_source_diagnostics as auditor


def _write_artifact(root: Path, *, duplicate: bool = False, unrelated: bool = False) -> Path:
    receipt = root / auditor.FAILURE_RECEIPT
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({"capture_id": "run-16", "exact_commit_sha": "d0ee4a341958ac80ecdfacb37e3e129b3051c28d"}), encoding="utf-8")
    fotmob = root / ".cache/athena-research/fotmob-data-matches-captures/20260918/x/response.json"
    fotmob.parent.mkdir(parents=True)
    home, away = ("Example", "Other") if unrelated else ("Okzhetpes Kokshetau", "Zhenis")
    matches = [{"id": 5204254, "home": {"id": 2128, "name": home, "longName": home}, "away": {"id": 1614087, "name": away, "longName": away}, "status": {"utcTime": "2026-09-18T11:00:00Z"}}]
    if duplicate:
        matches.append({"id": 5204255, "home": {"id": 2129, "name": "Okzhetpes Kokshetau", "longName": "Okzhetpes Kokshetau"}, "away": {"id": 1614088, "name": "Zhenis", "longName": "Zhenis"}, "status": {"utcTime": "2026-09-18T11:00:00Z"}})
    fotmob.write_text(json.dumps({"leagues": [{"ccode": "KAZ", "primaryId": 225, "name": "Premier League", "matches": matches}]}), encoding="utf-8")
    tournament = root / ".cache/athena-research/current-shadow-sportybet-catalog-fanout/x/tournaments/a.json"
    tournament.parent.mkdir(parents=True)
    tournament.write_text(json.dumps({"data": [{"eventId": "sr:match:69343126", "estimateStartTime": 1789729200000, "homeTeamId": "sr:competitor:5359", "homeTeamName": "FC Okzhetpes", "awayTeamId": "sr:competitor:5363", "awayTeamName": "FC Zhenis", "sport": {"category": {"id": "sr:category:278", "tournament": {"id": "sr:tournament:682", "name": "Premier League"}}}}]}), encoding="utf-8")
    return root


def _zip_tree(source: Path, destination: Path) -> Path:
    with zipfile.ZipFile(destination, "w") as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source).as_posix())
    return destination


def test_audit_is_deterministic_and_exposes_explicit_alias_without_authority(tmp_path: Path):
    root = _write_artifact(tmp_path / "artifact")
    first = auditor.analyze(root)
    second = auditor.analyze(root)
    assert auditor._canonical(first) == auditor._canonical(second)
    assert first["events"][0]["classification"] == "EXPLICIT_ALIAS_COMPATIBLE"
    assert first["events"][0]["same_kickoff_candidates"][0]["fotmob_fixture_id"] == 5204254
    assert first["authority"]["fixture_reconciliation"] is False
    assert first["authority"]["network"] is False


def test_unsupported_same_kickoff_fixture_remains_unsupported(tmp_path: Path):
    report = auditor.analyze(_write_artifact(tmp_path / "artifact", unrelated=True))
    assert report["events"][0]["classification"] == "SAME_KICKOFF_UNSUPPORTED"


def test_ambiguous_same_kickoff_identity_remains_ambiguous(tmp_path: Path):
    report = auditor.analyze(_write_artifact(tmp_path / "artifact", duplicate=True))
    assert report["events"][0]["classification"] == "AMBIGUOUS"


def test_zip_digest_and_malformed_zip_fail_closed(tmp_path: Path):
    archive = _zip_tree(_write_artifact(tmp_path / "artifact"), tmp_path / "artifact.zip")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert auditor.analyze(archive, expected_zip_sha256=digest)["artifact_sha256"] == digest
    with pytest.raises(auditor.SourceDiagnosticsAuditError, match="SHA-256 mismatch"):
        auditor.analyze(archive, expected_zip_sha256="0" * 64)
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"not a zip")
    with pytest.raises(auditor.SourceDiagnosticsAuditError, match="malformed"):
        auditor.analyze(broken)


def test_audit_never_invokes_network(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: pytest.fail("network invoked"))
    assert auditor.analyze(_write_artifact(tmp_path / "artifact"))["provider_event_count"] == 1
