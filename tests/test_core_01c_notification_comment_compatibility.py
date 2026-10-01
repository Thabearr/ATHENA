from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import urllib.request

import pytest

from domain.run_contracts import canonical_json_bytes, RunRequest
from services import athena_shadow_issue_comment_compatibility as comment
from services.athena_run_request_parser import parse_explicit_request
from scripts import audit_core_01c_notification_comment_compatibility as audit
from scripts import resolve_athena_shadow_issue_comment as cli
from scripts import send_current_shadow_email as mail

NOW = datetime(2026, 9, 24, 9, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def deny_real_actions(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("C3 real side effect forbidden")
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", deny)
    monkeypatch.setattr(mail.smtplib, "SMTP", deny)
    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", deny)
    from services import athena_run_service
    from domain import sportybet_share_code
    monkeypatch.setattr(athena_run_service.AthenaRunService, "run", deny)
    monkeypatch.setattr(athena_run_service, "_run_reviewed_shadow_worker", deny)
    monkeypatch.setattr(sportybet_share_code, "create_verified_share_code", deny)
    monkeypatch.setattr(sportybet_share_code, "create_verified_share_code_as_of", deny)
    original = subprocess.Popen
    def git_only(args, *positional, **kwargs):
        if not isinstance(args, (tuple, list)) or args[0] != "git" or kwargs.get("shell"):
            return deny()
        return original(args, *positional, **kwargs)
    monkeypatch.setattr(subprocess, "Popen", git_only)


@pytest.mark.parametrize("clock", ["09:00", "22:59"])
@pytest.mark.parametrize("command,count", [
    ("/athena-shadow target=1 scope=today", 1), ("/athena-shadow target=50 scope=three-day", 3),
    ("/athena-shadow target=20 dates=20260924", 1),
    ("/athena-shadow target=20 dates=20260924,20260925,20260926,20260927,20260928,20260929,20260930", 7),
])
def test_exact_grammar_byte_digest_and_intent_parity(command, count, clock):
    now = datetime.fromisoformat(f"2026-09-24T{clock}:00+00:00")
    result = comment.resolve_comment(command, now=now)
    days = ",".join(datetime.strptime(day, "%Y%m%d").date().isoformat() for day in result.legacy_utc_resolved_dates)
    request = parse_explicit_request(days=days, target_legs=result.target_legs, bookie="sportybet",
                                     profile="shadow", create_share_code=True, target_total_odds=None, now=now)
    assert result.original_command == command and len(result.legacy_utc_resolved_dates) == count
    assert result.compatibility_status == comment.REPRESENTABLE
    assert result.canonical_request_bytes == canonical_json_bytes(request)
    assert result.canonical_request_sha256 == request.canonical_sha256
    decoded = RunRequest.from_json_bytes(result.canonical_request_bytes)
    assert decoded.authority_profile == "SHADOW" and decoded.create_share_code is True
    assert decoded.place_wager is False and decoded.target_total_odds is None
    assert result.dispatch_authority is False
    with pytest.raises(AttributeError):
        result.target_legs = 10


@pytest.mark.parametrize("command", [
    "/athena-shadow target=0 scope=today", "/athena-shadow target=51 scope=today",
    " /athena-shadow target=20 scope=today", "/athena-shadow target=20 scope=today ",
    "/athena-shadow target=20 scope=today\n", "/athena-shadow target=20  scope=today",
    "/ATHENA-shadow target=20 scope=today", "/athena-shadow target=20 scope=TODAY",
    "/athena-shadow target=20 scope=tomorrow", "/athena target=20 scope=today",
    "/athena-shadow target=20 dates=2026-09-24", "/athena-shadow target=20 dates=20260924,20260924",
    "/athena-shadow target=20 dates=20260931", "/athena-shadow target=20 dates=20260923",
    "/athena-shadow target=20 dates=20261001", "/athena-shadow target=20 dates=20260924,",
    "/athena-shadow target=20 dates=20260924,20260925,20260926,20260927,20260928,20260929,20260930,20261001",
    "/athena-shadow target=20 scope=today dates=20260924", "/athena-shadow scope=today target=20",
])
def test_malformed_unknown_or_invalid_comment_fails_closed(command):
    with pytest.raises(ValueError):
        comment.resolve_comment(command, now=NOW)


@pytest.mark.parametrize("command,dates", [
    ("/athena-shadow target=20 scope=today", ("20260924",)),
    ("/athena-shadow target=20 scope=three-day", ("20260924", "20260925", "20260926")),
    ("/athena-shadow target=20 dates=20260924", ("20260924",)),
])
def test_2300_unrepresentable_never_shifted(command, dates):
    result = comment.resolve_comment(command, now=NOW.replace(hour=23))
    assert result.legacy_utc_resolved_dates == dates
    assert result.compatibility_status == comment.UNREPRESENTABLE
    assert result.canonical_request_bytes is None and result.canonical_request_sha256 is None


def test_2300_explicit_future_dates_are_still_exactly_representable():
    result = comment.resolve_comment("/athena-shadow target=20 dates=20260926,20260925", now=NOW.replace(hour=23))
    request = parse_explicit_request(days="2026-09-25,2026-09-26", target_legs=20, bookie="sportybet",
                                     profile="shadow", create_share_code=True, target_total_odds=None, now=NOW.replace(hour=23))
    assert result.canonical_request_bytes == canonical_json_bytes(request)
    assert result.legacy_utc_resolved_dates == ("20260925", "20260926")
    assert result.legacy_fixture_dates == "20260926,20260925"  # original legacy handoff unchanged


def test_naive_clock_and_nontext_fail_closed():
    with pytest.raises(ValueError):
        comment.resolve_comment("/athena-shadow target=20 scope=today", now=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError):
        comment.resolve_comment(None, now=NOW)


def test_thin_cli_only_emits_legacy_handoff(monkeypatch, capsys):
    class Clock:
        @staticmethod
        def now(tz): return NOW.replace(hour=23)
    monkeypatch.setattr(cli, "datetime", Clock)
    monkeypatch.setenv("COMMENT_BODY", "/athena-shadow target=20 scope=three-day")
    assert cli.main() == 0
    assert capsys.readouterr().out == "20\nthree-day\n\n"
    monkeypatch.setenv("COMMENT_BODY", "/athena-shadow target=0 scope=today")
    assert cli.main() == 2
    assert "grammar/date bounds" in capsys.readouterr().err


def source_receipt(tmp_path):
    safety = dict.fromkeys(("sportybet_login_used", "sportybet_cookie_used", "sportybet_wallet_used",
                            "stake_submitted", "wager_placed"), False)
    nested = {"status": "RESEARCH_SHADOW_CODE_VERIFIED", "code_verified": True,
              "exact_create_reload_equality": True, "shareCode": "SYNTHETIC_CODE",
              "shareURL": "https://example.invalid/SYNTHETIC_CODE", **safety}
    fixture = {"dataset_name": mail.EXPECTED_DATASET, "status": nested["status"],
               "shareCode": nested["shareCode"], "shareURL": nested["shareURL"],
               "share_code_receipt": nested, **safety}
    path = tmp_path / "business.json"
    path.write_bytes(json.dumps(fixture, sort_keys=True).encode())
    return path


@pytest.mark.parametrize("mode", ["unconfigured", "delivered", "connect", "starttls", "login", "send_message"])
def test_mocked_notification_never_mutates_business_or_reruns_core(tmp_path, monkeypatch, mode):
    path = source_receipt(tmp_path)
    before = path.read_bytes()
    sha = hashlib.sha256(before).hexdigest()
    calls = []
    for key, value in zip(audit.SECRET_NAMES, ("fake@example.invalid", "NOT_A_REAL_CREDENTIAL", "fake@example.invalid")):
        monkeypatch.setenv(key, "" if mode == "unconfigured" else value)
    class SMTP:
        def __init__(self, *args, **kwargs): self.stage("connect")
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def stage(self, stage):
            calls.append(stage)
            if mode == stage: raise OSError("NOT_A_REAL_CREDENTIAL must never be recorded")
        def starttls(self): self.stage("starttls")
        def login(self, *args): self.stage("login")
        def send_message(self, message): self.stage("send_message")
    monkeypatch.setattr(mail.smtplib, "SMTP", SMTP)
    delivery = tmp_path / "delivery.json"
    result = mail.send_receipt_email(receipt_path=path, delivery_receipt_path=delivery)
    expected = mail.EMAIL_SKIPPED_UNCONFIGURED if mode == "unconfigured" else mail.EMAIL_DELIVERED if mode == "delivered" else mail.EMAIL_FAILED
    assert result["status"] == expected
    assert result["source_receipt_sha256"] == sha == hashlib.sha256(path.read_bytes()).hexdigest()
    assert before == path.read_bytes()
    assert result["smtp_successful_send"] == (mode == "delivered")
    assert result["secrets_recorded"] is False and result["wager_placed"] is False
    assert "NOT_A_REAL_CREDENTIAL" not in delivery.read_text()
    if mode == "unconfigured": assert not calls


def test_failed_notification_cli_zero_and_warning(tmp_path, monkeypatch, capsys):
    path = source_receipt(tmp_path)
    before = path.read_bytes()
    for key in audit.SECRET_NAMES: monkeypatch.setenv(key, "SYNTHETIC_NOT_A_SECRET")
    def smtp(*args, **kwargs): raise mail.smtplib.SMTPException("synthetic transport failure")
    monkeypatch.setattr(mail.smtplib, "SMTP", smtp)
    assert mail.main(["--receipt", str(path)]) == 0
    captured = capsys.readouterr()
    assert "EMAIL_FAILED" in captured.out and "WARNING" in captured.err
    assert path.read_bytes() == before


@pytest.mark.parametrize("change", ["json", "dataset", "unsafe", "integer_false", "unverified_code", "nested_mismatch", "nested_unsafe", "missing"])
def test_integrity_security_failures_remain_fatal_without_smtp(tmp_path, change):
    path = source_receipt(tmp_path)
    value = json.loads(path.read_bytes())
    if change == "json": path.write_bytes(b"INVALID_JSON")
    elif change == "missing": path.unlink()
    else:
        if change == "dataset": value["dataset_name"] = "OTHER"
        elif change == "unsafe": value["wager_placed"] = True
        elif change == "integer_false": value["stake_submitted"] = 0
        elif change == "unverified_code": value["status"] = "RESEARCH_NO_CODE_NO_BET"
        elif change == "nested_mismatch": value["share_code_receipt"]["shareCode"] = "MISMATCH"
        else: value["share_code_receipt"]["sportybet_login_used"] = True
        path.write_bytes(json.dumps(value).encode())
    with pytest.raises(mail.CurrentShadowEmailError): mail.main(["--receipt", str(path)])


def test_delivery_cannot_overwrite_business_receipt(tmp_path):
    path = source_receipt(tmp_path)
    before = path.read_bytes()
    with pytest.raises(mail.CurrentShadowEmailError, match="alias"):
        mail.send_receipt_email(receipt_path=path, delivery_receipt_path=path)
    assert path.read_bytes() == before


def test_unexpected_programming_failure_is_not_hidden(tmp_path, monkeypatch):
    for key in audit.SECRET_NAMES: monkeypatch.setenv(key, "SYNTHETIC_NOT_A_SECRET")
    def smtp(*args, **kwargs): raise RuntimeError("not ordinary SMTP transport")
    monkeypatch.setattr(mail.smtplib, "SMTP", smtp)
    with pytest.raises(RuntimeError): mail.send_receipt_email(receipt_path=source_receipt(tmp_path))


def test_authority_diff_and_exact_guard():
    before, after = audit.tracked(audit.BEFORE_FIXTURE), audit.tracked(audit.WORKFLOW)
    audit.verify_workflow_authority(before, after)
    for old, new in ((b"== 276", b"== 277"), (b"github.repository_owner", b"'someone'"),
                     (b'cron: "0 9 * * *"', b'cron: "0 10 * * *"'),
                     (b"scripts.execute_current_shadow_request", b"scripts.other_execution")):
        with pytest.raises(ValueError, match="authority drift"):
            audit.verify_workflow_authority(before, after.replace(old, new))


def test_rederived_receipt_exact_eleven_transition_prefix_and_history():
    result = audit.audit()
    assert result["result"] == "PASS" and result["transition_count"] == 11
    predecessor = json.loads(audit.tracked(audit.PREDECESSOR_PATH))
    ledger = audit.evolution.validate_current_state()
    assert ledger["transitions"][:10] == predecessor["transitions"]
    assert ledger["transitions"][10]["transition_id"] == audit.TRANSITION_ID
    assert ledger["current_live_workflow_count"] == 39 and ledger["current_p4_3_retired_workflow_count"] == 3
    assert all(value == 0 for value in result["real_side_effect_counts"].values())


def test_historical_integrity_does_not_require_ancestor_objects(monkeypatch):
    original = audit.subprocess.check_output
    def head_only(args, *positional, **kwargs):
        if any(audit.BASE_MAIN in str(arg) for arg in args):
            pytest.fail("C3 audit attempted an unavailable ancestor object")
        return original(args, *positional, **kwargs)
    monkeypatch.setattr(audit.subprocess, "check_output", head_only)
    assert audit.audit()["result"] == "PASS"
