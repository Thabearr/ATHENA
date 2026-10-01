"""Deterministic offline ownership evidence; no timezone/date migration."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import smtplib
import socket
import subprocess
import urllib.request
from zoneinfo import ZoneInfo

import pytest

from domain import current_shadow_fixture_date_request as legacy
from domain import execution_envelope as envelope
from domain.run_contracts import canonical_json_bytes
from scripts import audit_core_01_schedule_date_disposition as audit
from services import athena_run_service as service
from services.athena_run_request_parser import AthenaRunRequestParseError, parse_explicit_request
from services.athena_run_workflow_request import resolve_workflow_request

UTC = timezone.utc
NORMAL = datetime(2026, 9, 24, 9, tzinfo=UTC)
BOUNDARY = datetime(2026, 9, 24, 23, tzinfo=UTC)


def request(days="today", now=NORMAL, **overrides):
    return parse_explicit_request(days=days, target_legs=20, profile="shadow",
                                  create_share_code=False, now=now, **overrides)


@pytest.fixture(autouse=True)
def side_effect_sentinels(monkeypatch):
    counts = dict.fromkeys(("network", "provider_acquisition", "share_code", "delivery",
                           "email", "live_workflow_dispatch", "wager"), 0)

    def denied(key):
        def call(*args, **kwargs):
            counts[key] += 1
            raise AssertionError(f"CORE-01A prohibited operation: {key}")
        return call

    monkeypatch.setattr(socket.socket, "connect", denied("network"))
    monkeypatch.setattr(socket, "create_connection", denied("network"))
    monkeypatch.setattr(urllib.request, "urlopen", denied("network"))
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", denied("network"))
    monkeypatch.setattr(smtplib, "SMTP", denied("email"))
    monkeypatch.setattr(smtplib, "SMTP_SSL", denied("email"))
    monkeypatch.setattr(service, "_run_reviewed_shadow_worker", denied("provider_acquisition"))
    from domain import sportybet_share_code
    from scripts import send_current_shadow_email
    monkeypatch.setattr(sportybet_share_code, "create_verified_share_code", denied("share_code"))
    monkeypatch.setattr(sportybet_share_code, "create_verified_share_code_as_of", denied("delivery"))
    monkeypatch.setattr(send_current_shadow_email, "send_receipt_email", denied("email"))
    original_popen = subprocess.Popen

    def local_git_only(args, *positional, **kwargs):
        if not isinstance(args, (list, tuple)) or args[0] != "git" or kwargs.get("shell"):
            return denied("live_workflow_dispatch")(args)
        return original_popen(args, *positional, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", local_git_only)
    yield counts
    assert counts == dict.fromkeys(counts, 0)


@pytest.mark.parametrize("hour,minute,canonical_day,same", [
    (9, 0, date(2026, 9, 24), True),
    (22, 59, date(2026, 9, 24), True),
    (23, 0, date(2026, 9, 25), False),
])
def test_lagos_and_utc_today_boundary(hour, minute, canonical_day, same):
    now = datetime(2026, 9, 24, hour, minute, tzinfo=UTC)
    canonical = request(now=now)
    utc_today = legacy.validate_fixture_dates((now.strftime("%Y%m%d"),), current_utc=now)
    assert canonical.dates == (canonical_day,)
    assert utc_today == ("20260924",)
    assert (canonical.dates[0].strftime("%Y%m%d") == utc_today[0]) is same
    if not same:
        with pytest.raises(AthenaRunRequestParseError):
            request("2026-09-24", now=now)
        # Different meanings of "today" do not invalidate all exact requests:
        assert legacy.validate_fixture_dates(("20260925",), current_utc=now) == ("20260925",)


@pytest.mark.parametrize("count", range(1, 8))
def test_one_through_seven_selected_dates_sorted_and_exact(count):
    days = [date(2026, 9, 24) + timedelta(days=i) for i in range(count)]
    selected = request(",".join(day.isoformat() for day in reversed(days)))
    assert selected.dates == tuple(days)
    assert selected.target_legs == 20 and selected.target_total_odds is None
    assert legacy.validate_fixture_dates(tuple(day.strftime("%Y%m%d") for day in reversed(days)),
                                         current_utc=NORMAL) == tuple(day.strftime("%Y%m%d") for day in days)


def test_arbitrary_noncontiguous_selected_dates_and_independent_objective():
    selected = request("2026-09-30,today,2026-09-27", target_total_odds="12.5")
    assert selected.dates == (date(2026, 9, 24), date(2026, 9, 27), date(2026, 9, 30))
    assert selected.target_legs == 20 and str(selected.target_total_odds) == "12.5"


def test_seven_day_boundary_horizons_are_not_equal_or_shifted():
    canonical_days = tuple(date(2026, 9, 25) + timedelta(days=i) for i in range(7))
    legacy_days = tuple(date(2026, 9, 24) + timedelta(days=i) for i in range(7))
    assert request(",".join(day.isoformat() for day in canonical_days), now=BOUNDARY).dates == canonical_days
    assert legacy.validate_fixture_dates(tuple(day.strftime("%Y%m%d") for day in legacy_days),
                                         current_utc=BOUNDARY) == tuple(day.strftime("%Y%m%d") for day in legacy_days)
    assert canonical_days != legacy_days
    with pytest.raises(legacy.CurrentShadowFixtureDateRequestError):
        legacy.validate_fixture_dates(tuple(day.strftime("%Y%m%d") for day in canonical_days),
                                      current_utc=BOUNDARY)


@pytest.mark.parametrize("days", ["today,today", "today,2026-09-24", "tomorrow,friday",
    "2026-9-24", "2026-02-30", "2026-09-23", "2026-10-01", "",
    "today,tomorrow,saturday,sunday,monday,tuesday,wednesday,2026-09-30"])
def test_canonical_duplicate_collision_malformed_horizon_and_count_rejection(days):
    with pytest.raises(AthenaRunRequestParseError):
        request(days)


@pytest.mark.parametrize("days", [("2026-09-24",), ("20260931",), ("20260924", "20260924"),
    ("20260923",), ("20261001",), (), tuple(f"202609{i}" for i in range(24, 32))])
def test_legacy_exact_utc_format_duplicate_horizon_and_count_rejection(days):
    with pytest.raises(legacy.CurrentShadowFixtureDateRequestError):
        legacy.validate_fixture_dates(days, current_utc=NORMAL)


def test_accepted_request_survives_midnight_without_reresolving(tmp_path, monkeypatch):
    selected = request(now=datetime(2026, 9, 24, 22, 59, tzinfo=UTC))
    original = canonical_json_bytes(selected)
    seen = []

    def executor(actual, **kwargs):
        seen.append(actual)
        assert actual is selected
        assert canonical_json_bytes(actual) == original
        return service.ExecutorResult(status="OFFLINE_DATE_PRESERVATION", evidence={"offline": True})

    from services import athena_run_request_parser as parser
    monkeypatch.setattr(parser, "parse_explicit_request", lambda **kwargs: pytest.fail("date re-resolution"))
    engine = service.AthenaRunService(
        _test_executor_overrides={("SHADOW", "research_shadow", "sportybet"): executor},
        _commit_sha_provider=lambda: audit.BASE_MAIN, _clock=lambda: BOUNDARY + timedelta(hours=2))
    receipt = engine.run(selected, output_root=tmp_path)
    assert seen == [selected]
    assert receipt.request.dates == (date(2026, 9, 24),)
    assert canonical_json_bytes(selected) == original
    assert (tmp_path / selected.canonical_sha256 / "athena-run-request.json").read_bytes() == original


def test_envelope_binds_exact_dates_and_utc_z_timestamps():
    selected = request(now=BOUNDARY)
    lagos_clock = BOUNDARY.astimezone(ZoneInfo("Africa/Lagos"))
    bound = envelope.ExecutionEnvelope.from_request_bytes(
        request_bytes=canonical_json_bytes(selected),
        requested_operations=envelope.RequestedOperationIntent(True, False, False),
        authority_manifest=service.AthenaRunService.authority_manifest_for(selected),
        source_identity=envelope.SourceReleaseIdentity("GIT_COMMIT", audit.BASE_MAIN),
        date_resolution_policy_id=envelope.DATE_RESOLUTION_POLICY_ID,
        date_resolution_timezone_id=envelope.DATE_RESOLUTION_TIMEZONE_ID,
        clock_policy_id=envelope.PREVIEW_CLOCK_POLICY_ID, clock_observed_at=lagos_clock,
        issued_at=lagos_clock, expires_at=lagos_clock + timedelta(minutes=30))
    assert bound.resolved_request_dates == tuple(day.isoformat() for day in selected.dates)
    assert bound.request_bytes == canonical_json_bytes(selected)
    value = json.loads(bound.canonical_bytes)
    for field in ("clock_observed_at", "issued_at", "expires_at"):
        assert value[field].endswith("Z")


@pytest.mark.parametrize("days,now", [
    ("2026-10-01", BOUNDARY),
    (",".join((date(2026, 9, 25) + timedelta(days=i)).isoformat() for i in range(7)), BOUNDARY),
    ("today", datetime(2026, 9, 25, 0, 0, tzinfo=UTC)),
])
def test_unrepresentable_exact_bridge_precedes_provider_and_delivery(tmp_path, days, now,
                                                                  side_effect_sentinels):
    accepted_at = NORMAL if days == "today" else BOUNDARY
    selected = request(days, now=accepted_at)
    original = canonical_json_bytes(selected)
    engine = service.AthenaRunService(_commit_sha_provider=lambda: audit.BASE_MAIN, _clock=lambda: now)
    receipt = engine.run(selected, output_root=tmp_path)
    assert receipt.status == "SHADOW_DATE_POLICY_UNREPRESENTABLE"
    assert receipt.request == selected and canonical_json_bytes(selected) == original
    assert receipt.evidence["provider_acquisition"] is False
    assert receipt.evidence["request_dates_preserved"] == tuple(day.isoformat() for day in selected.dates)
    assert receipt.share_code_result is None and not receipt.selected_legs
    assert (tmp_path / selected.canonical_sha256 / "athena-run-request.json").read_bytes() == original
    assert side_effect_sentinels == dict.fromkeys(side_effect_sentinels, 0)


@pytest.fixture(scope="module")
def reviewed_sources():
    paths = [*audit.SOURCE_BLOBS, audit.CORE01B_BEFORE_FIXTURE]
    return {path: audit.read_tracked_head_blob(audit.ROOT, path) for path in paths}


def test_exact_receipt_audit_canonical_sha_and_predecessor_immutability():
    result = audit.audit()
    assert result["result"] == "PASS" and result["source_identity_count"] == 15
    assert result["canonical_sha256"] == "95468dea547844cea360944057b516056a9f0cd6d879e34fd1b108f6ed3951f0"


def test_schedule_semantics_compatibility_email_and_history(reviewed_sources):
    measured = audit.inspect_semantics(audit.inspect_sources(audit.ROOT)[1])
    selected = resolve_workflow_request(event_name="schedule", now=NORMAL)
    assert selected.authority_profile == "MAIN" and selected.mode == "main_application"
    assert selected.create_share_code is selected.place_wager is False
    assert measured["canonical_scheduled_request_sha256"] == selected.canonical_sha256
    for path in (audit.CANONICAL_WORKFLOW, audit.LEGACY_WORKFLOW):
        text = reviewed_sources[path][0].decode()
        assert 'cron: "0 9 * * *"' in text
        assert "backfill" not in text.lower() and "catch-up" not in text.lower()
        if path == audit.LEGACY_WORKFLOW:
            assert "current-shadow-all-market-request" in text
            assert "current-shadow-all-market.yml/runs?status=success" in text
        else:
            assert "scripts.restore_athena_artifact_roles --restore-inputs" in text
    text = reviewed_sources[audit.LEGACY_WORKFLOW][0].decode()
    assert "scope=(today|three-day)" in text and "dates=([0-9]{8}" in text
    assert text.index("scripts.execute_current_shadow_request") < text.index("scripts.send_current_shadow_email")
    assert "issue_comment:" not in reviewed_sources[audit.CANONICAL_WORKFLOW][0].decode()


def test_successor_and_governance_never_infer_live_proof():
    value = audit.parse_canonical((audit.ROOT / audit.ARTIFACT_PATH).read_bytes())
    proof = value["successor_proof"]
    assert proof["clean_successor_proof"] == "INCOMPLETE"
    assert proof["lg_a"] == "NOT_RUN_NOT_AUTHORIZED"
    assert proof["historical_run"] == 36345657852
    assert "AUTHORIZATION_NONCOMPLIANT" in proof["historical_classification"]
    for field in ("migration_allowed", "caller_migration_authorized", "schedule_migration_authorized",
                  "workflow_retirement_authorized", "offline_auth_or_port_replay_is_live_proof",
                  "github_success_is_business_success_proof"):
        assert proof[field] is False
    assert value["governance"]["source_review_counter_while_open"] == "1/5"
    assert value["schedule_disposition"]["missed_run_backfill"] == "FORBIDDEN"
    assert value["schedule_disposition"]["cron_parity_is_semantic_equivalence"] is False


def test_one_byte_receipt_mutation_fails_without_repair():
    raw = (audit.ROOT / audit.ARTIFACT_PATH).read_bytes()
    altered = raw.replace(b'"source_review_counter_at_start":1', b'"source_review_counter_at_start":2')
    assert len(altered) == len(raw) and altered != raw
    with pytest.raises(audit.DispositionError, match="self SHA"):
        audit.parse_canonical(altered)


@pytest.mark.parametrize("section,field,value", [
    ("successor_proof", "clean_successor_proof", "COMPLETE"),
    ("successor_proof", "lg_a", "PASS"),
    ("successor_proof", "historical_classification", "CLEAN_SUCCESSOR_PROOF"),
    ("schedule_disposition", "schedule_migration", "AUTHORIZED"),
    ("canonical_date_owner", "timezone", "UTC"),
    ("legacy_date_owner", "timezone", "Africa/Lagos"),
    ("successor_proof", "migration_allowed", 0),
])
def test_resigned_authority_or_date_mutation_still_fails(section, field, value,
                                                       monkeypatch, reviewed_sources):
    monkeypatch.setattr(audit, "read_tracked_head_blob", lambda root, path: reviewed_sources[path])
    receipt = json.loads((audit.ROOT / audit.ARTIFACT_PATH).read_bytes())
    receipt[section][field] = value
    receipt["canonical_sha256"] = audit.canonical_sha(receipt)
    with pytest.raises(audit.DispositionError, match="independently"):
        audit.audit(artifact_bytes=audit.canonical(receipt) + b"\n")


@pytest.mark.parametrize("path,before,after", [
    (audit.CANONICAL_WORKFLOW, b"0 9 * * *", b"0 10 * * *"),
    (audit.LEGACY_WORKFLOW, b"0 9 * * *", b"0 10 * * *"),
    ("services/athena_run_request_parser.py", b"Africa/Lagos", b"UTC"),
    ("domain/current_shadow_fixture_date_request.py", b"dt.timezone.utc", b"dt.timezone.other"),
    (audit.AUTH_PATH, b"NOT_RERUN_IN_A5", b"PASS"),
    (audit.P44H_PATH, b'"retirement_authorized":false', b'"retirement_authorized":true'),
    (audit.PORT_PATH, b"NATIVE_INSTALLED_RUNTIME_SLICE", b"CLEAN_LIVE_SUCCESSOR"),
])
def test_reviewed_source_or_historical_receipt_drift_fails(path, before, after,
                                                          monkeypatch, reviewed_sources):
    raw, identity = reviewed_sources[path]
    changed = raw.replace(before, after)
    assert changed != raw
    new_blob = hashlib.sha1(f"blob {len(changed)}\0".encode() + changed).hexdigest()
    altered = replace(identity, git_blob_sha1=new_blob,
                      git_blob_payload_sha256=hashlib.sha256(changed).hexdigest())
    monkeypatch.setattr(audit, "read_tracked_head_blob", lambda root, p:
                        (changed, altered) if p == path else reviewed_sources[p])
    with pytest.raises(audit.DispositionError, match="reviewed source drift"):
        audit.audit()
