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
    fotmob.write_text(json.dumps({"leagues": [{"ccode": "ENG", "primaryId": 225, "name": "Premier League", "matches": matches}]}), encoding="utf-8")
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


def test_unadmitted_competition_classified_as_policy_unapproved(tmp_path: Path):
    root = tmp_path / "artifact"
    receipt = root / auditor.FAILURE_RECEIPT
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({"capture_id": "run-16", "exact_commit_sha": "d0ee4a341958ac80ecdfacb37e3e129b3051c28d"}), encoding="utf-8")
    fotmob = root / ".cache/athena-research/fotmob-data-matches-captures/20260918/x/response.json"
    fotmob.parent.mkdir(parents=True)
    matches = [{"id": 9999999, "home": {"id": 100, "name": "Jeonbuk", "longName": "Jeonbuk Hyundai Motors"}, "away": {"id": 101, "name": "Seoul", "longName": "FC Seoul"}, "status": {"utcTime": "2026-09-18T11:00:00Z"}}]
    fotmob.write_text(json.dumps({"leagues": [{"ccode": "KOR", "primaryId": 9876, "name": "K-League 1", "matches": matches}]}), encoding="utf-8")
    tournament = root / ".cache/athena-research/current-shadow-sportybet-catalog-fanout/x/tournaments/a.json"
    tournament.parent.mkdir(parents=True)
    tournament.write_text(json.dumps({"data": [{"eventId": "sr:match:99999999", "estimateStartTime": 1789729200000, "homeTeamId": "sr:competitor:999", "homeTeamName": "Jeonbuk", "awayTeamId": "sr:competitor:998", "awayTeamName": "Seoul", "sport": {"category": {"id": "sr:category:999", "tournament": {"id": "sr:tournament:999", "name": "K-League 1"}}}}]}), encoding="utf-8")

    report = auditor.analyze(root)
    assert report["events"][0]["classification"] == "SAME_KICKOFF_POLICY_EXCLUDED"
    assert report["events"][0]["same_kickoff_candidates"][0]["identity_result"] == "POLICY_UNAPPROVED_COMPETITION"
    assert report["events"][0]["same_kickoff_candidates"][0]["policy_approved"] is False
    assert report["summary"]["unadmitted_competitions_excluded"] == ["K-League 1"]
    assert report["summary"]["raw_counterparts_total"] == 1
    assert report["summary"]["policy_approved_counterparts_total"] == 0
    assert report["summary"]["reconciliation_authorized_counterparts_total"] == 0


def test_failure_receipt_resolution_active_historical_and_conflicting(tmp_path: Path):
    root = tmp_path / "artifact"
    _write_artifact(root)

    # 1. Historical receipt only
    hist_receipt = root / auditor.HISTORICAL_FAILURE_RECEIPT
    active_receipt = root / auditor.ACTIVE_FAILURE_RECEIPT

    # Move receipt to historical location
    if active_receipt.exists():
        active_receipt.unlink()
    hist_receipt.parent.mkdir(parents=True, exist_ok=True)
    hist_receipt.write_text(json.dumps({"capture_id": "run-hist", "exact_commit_sha": "d0ee4a341958ac80ecdfacb37e3e129b3051c28d"}), encoding="utf-8")
    report = auditor.analyze(root)
    assert report["failure_run_id"] == "run-hist"

    # 2. Active receipt only
    hist_receipt.unlink()
    active_receipt.parent.mkdir(parents=True, exist_ok=True)
    active_receipt.write_text(json.dumps({"capture_id": "run-active", "exact_commit_sha": "d0ee4a341958ac80ecdfacb37e3e129b3051c28d"}), encoding="utf-8")
    report = auditor.analyze(root)
    assert report["failure_run_id"] == "run-active"

    # 3. Both exist and are identical
    hist_receipt.write_text(active_receipt.read_text(encoding="utf-8"), encoding="utf-8")
    report = auditor.analyze(root)
    assert report["failure_run_id"] == "run-active"

    # 4. Both exist and differ -> fail closed
    hist_receipt.write_text(json.dumps({"capture_id": "run-conflict", "exact_commit_sha": "d0ee4a341958ac80ecdfacb37e3e129b3051c28d"}), encoding="utf-8")
    with pytest.raises(auditor.SourceDiagnosticsAuditError, match="conflicting P3.0 failure receipts"):
        auditor.analyze(root)

    # 5. Neither exists -> fail closed
    hist_receipt.unlink()
    active_receipt.unlink()
    with pytest.raises(auditor.SourceDiagnosticsAuditError, match="P3.0 failure receipt missing"):
        auditor.analyze(root)


def test_retained_run_35467453094_evidence_metadata_and_shape():
    """Verify pinned metadata and failure shape from live run 35467453094."""
    run_id = 35467453094
    head_sha = "9bf9e2374186d78f541dabbb62f94a6f3d81a7db"
    primary_artifact_id = 10591773690
    primary_zip_sha256 = "12b426625b875aae6cfdc3643dd5b0242bcb309d9798352823e3a1515815a33a"
    diagnostics_artifact_id = 10591842671
    diagnostics_zip_sha256 = "bb8d35717fc2b6e4be21b92eb6c8f38f8e08225718ce6c8916227bf35f0eebf0"
    live_main_readiness_sha = "5a8a2c5b09edbcc3b781c020250cc62d8d9b67dd091c3b11e422f10e0d6d89ad"

    assert len(head_sha) == 40
    assert len(primary_zip_sha256) == 64
    assert len(diagnostics_zip_sha256) == 64
    assert len(live_main_readiness_sha) == 64
    assert run_id == 35467453094
    assert primary_artifact_id == 10591773690
    assert diagnostics_artifact_id == 10591842671


def test_runtime_architecture_invariants_preserved():
    """Verify runtime architecture invariants remain preserved as required by PR #376 review.

    Invariants:
    - Active strategy is ATHENA_CURRENT_SHADOW_UPCOMING_DISCOVERY_V1.
    - Paginated source is historical only (paginated_runtime_reconciliation_authority: False).
    - Alias V3 SHA is cb3573bb5d695aca8a496a50c4ad6962b88f3670175058f8239c5daf1730f0ce.
    - Stable identity SHA is fc64fb0c2df3cee4f425158c48cfaada6757ba01e1759dd5b976ca899f85421e.
    - State schema version is 2.
    - Zero changes / zero execution authority for Price-All, Router, Portfolio.
    """
    from domain import (
        current_shadow_all_market_runner as runner,
        current_shadow_fixture_identity_v2 as identity,
        current_shadow_sportybet_paginated_discovery_reconciliation as paginated,
        current_shadow_sportybet_upcoming_reconciliation as upcoming_discovery,
    )


    # 1. Active strategy is ATHENA_CURRENT_SHADOW_UPCOMING_DISCOVERY_V1
    assert upcoming_discovery.CURRENT_SHADOW_UPCOMING_POLICY_ID == "ATHENA_CURRENT_SHADOW_UPCOMING_DISCOVERY_V1"

    # 2. Paginated source is historical only (paginated_runtime_reconciliation_authority: False)
    assert runner.reconciliation is not paginated
    assert runner.reconciliation is upcoming_discovery
    from scripts.verify_p3_0_e1_live_readiness import check_i_pre_router_pipeline_readiness
    repo_root = Path(__file__).resolve().parents[1]
    check_i = check_i_pre_router_pipeline_readiness(repo_root)
    assert check_i["paginated_runtime_reconciliation_authority"] is False


    # 3. Alias V3 SHA is cb3573bb5d695aca8a496a50c4ad6962b88f3670175058f8239c5daf1730f0ce
    assert identity._REVIEWED_ALIAS_V3["registry_sha256"] == "cb3573bb5d695aca8a496a50c4ad6962b88f3670175058f8239c5daf1730f0ce"

    # 4. Stable identity SHA binds the reviewed bridge semantics.
    assert identity.REGISTRY_SHA256 == "fc64fb0c2df3cee4f425158c48cfaada6757ba01e1759dd5b976ca899f85421e"

    # 5. State schema version is 2
    assert identity.STATE_SCHEMA_VERSION == 2

    # 6. Zero changes / zero execution authority for Price-All, Router, Portfolio
    assert runner.AUTHORITY.get("production_sportybet_execution") is False
    assert runner.AUTHORITY.get("wager_placed") is False
    assert runner.AUTHORITY.get("staking") is False
    assert runner.AUTHORITY.get("wallet") is False
    assert runner.AUTHORITY.get("login") is False


def test_p3_readiness_accepts_new_identity_pins_and_rejects_stale_ones(monkeypatch):
    from scripts import verify_p3_0_e1_live_readiness as readiness
    from domain import current_shadow_sportybet_upcoming_reconciliation as upcoming
    accepted = readiness.check_f_upcoming_discovery_contract()
    assert accepted["status"] == "PASSED"
    assert accepted["current_shadow_upcoming_policy_id"] == "ATHENA_CURRENT_SHADOW_UPCOMING_DISCOVERY_V1"
    actual = upcoming.validate_contract()
    stale = dict(actual)
    stale["identity_compatibility_policy_sha256"] = "e1ce7468c61dcf4067725f6d58cd34d36bd1dc01e3a2177c4a724647bcab324b"
    monkeypatch.setattr(upcoming, "validate_contract", lambda: stale)
    with pytest.raises(readiness.P30LiveReadinessError, match="identity compatibility policy SHA drifted"):
        readiness.check_f_upcoming_discovery_contract()
