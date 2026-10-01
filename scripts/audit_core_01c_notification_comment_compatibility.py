"""Offline C3 syntax/notification parity and append-only maintenance evidence."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

import yaml

from domain.run_contracts import canonical_json_bytes
from runtime.source_identity import read_tracked_head_blob
from services import athena_shadow_issue_comment_compatibility as comment
from services.athena_run_request_parser import parse_explicit_request
from scripts import audit_p4_workflow_evolution_ledger as evolution
from scripts import send_current_shadow_email as mail

ROOT = Path(__file__).resolve().parents[1]
BASE_MAIN = "f507842cb0fb523f08f28862d1e54b9e470edb82"
POLICY_ID = "ATHENA_CORE_01C_NOTIFICATION_COMMENT_COMPATIBILITY_V1"
WORKFLOW = ".github/workflows/current-shadow-all-market.yml"
BEFORE_FIXTURE = "tests/fixtures/architecture/revised_workflows/current-shadow-all-market-pre-core-01c-compatibility-thin.yml"
BEFORE_IDENTITY = {"git_blob_sha1": "4321d70563e98acaf1663f5a7b28781908535328",
                   "source_sha256": "d63c108c672bb65bd5875074a933905446ca13a01bc6818ba9e10871972e1f01"}
RECEIPT_PATH = "artifacts/architecture/core_01c_notification_comment_compatibility_v1.json"
SNAPSHOT_PATH = "artifacts/architecture/p4_workflow_evolution_snapshots/core_01c_current_shadow_compatibility_thin_v1.json"
PREDECESSOR_PATH = "artifacts/architecture/p4_workflow_evolution_snapshots/core_01b_athena_run_canonical_artifact_ancestry_v1.json"
PREDECESSOR_SHA = "15115996d087e6a4786065f4cbe676ff6cd8317d36dc3302e1dd1ba64d335901"
C2_RECEIPT_PATH = "artifacts/architecture/core_01b_canonical_artifact_ancestry_v1.json"
C2_RECEIPT_SHA = "194109e678c7a5f92c16a58db003ecd31fc04863cc8612b499da066caa3d3473"
TRANSITION_ID = "CORE01C_CURRENT_SHADOW_COMPATIBILITY_THIN_V1"
SECRET_NAMES = ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "RECIPIENT_EMAIL")
SOURCE_PATHS = (WORKFLOW, "services/athena_shadow_issue_comment_compatibility.py",
                "scripts/resolve_athena_shadow_issue_comment.py", "scripts/send_current_shadow_email.py")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return evolution.canonical_json_bytes(value)


def tracked(path):
    return read_tracked_head_blob(ROOT, path)[0]


def verify_workflow_authority(before: bytes, after: bytes) -> None:
    old = yaml.load(before, Loader=yaml.BaseLoader)
    new = yaml.load(after, Loader=yaml.BaseLoader)
    expected = copy.deepcopy(old)
    steps = expected["jobs"]["current-shadow-all-market"]["steps"]
    resolve = next(row for row in steps if row["name"] == "Resolve daily/on-demand request")
    run = resolve["run"]
    start = run.index('      parsed="$(python - <<\'PY\'')
    end = run.index(')" || {', start) + len(')"')
    resolve["run"] = run[:start] + '      parsed="$(python -m scripts.resolve_athena_shadow_issue_comment)"' + run[end:]
    require(new == expected, "CORE-01C workflow authority drift beyond exact comment parser delegation")
    require(comment.SCOPE_GRAMMAR == r"/athena-shadow target=([0-9]+) scope=(today|three-day)" and
            comment.EXPLICIT_DATES_GRAMMAR == r"/athena-shadow target=([0-9]+) dates=([0-9]{8}(?:,[0-9]{8}){0,6})",
            "comment grammar drift")
    for grammar in (comment.SCOPE_GRAMMAR, comment.EXPLICIT_DATES_GRAMMAR):
        require(grammar in before.decode() and grammar not in after.decode(), "grammar parser owner not moved")
    actual_steps = new["jobs"]["current-shadow-all-market"]["steps"]
    names = [row["name"] for row in actual_steps]
    require(names.index("Execute current research Shadow request") < names.index("Preserve exact current source evidence") <
            names.index("Email durable Shadow result when configured") < names.index("Upload durable research receipt"),
            "notification is not post-core/preservation")
    for row in actual_steps:
        found = set(row.get("env", {})) & set(SECRET_NAMES)
        require(found == (set(SECRET_NAMES) if row["name"] == "Email durable Shadow result when configured" else set()),
                "notification secret scope drift")
    canonical_workflow = yaml.load(tracked(".github/workflows/athena-run.yml"), Loader=yaml.BaseLoader)
    require("issue_comment" not in canonical_workflow["on"], "canonical issue-comment migration forbidden")


def comment_evidence():
    rows = []
    for clock in ("09:00", "22:59", "23:00"):
        now = datetime.fromisoformat(f"2026-09-24T{clock}:00+00:00")
        commands = ("/athena-shadow target=20 scope=today", "/athena-shadow target=20 scope=three-day",
                    "/athena-shadow target=20 dates=20260924", "/athena-shadow target=20 dates=20260925,20260926")
        for command in commands:
            result = comment.resolve_comment(command, now=now)
            expected_status = comment.UNREPRESENTABLE if clock == "23:00" and "20260925,20260926" not in command else comment.REPRESENTABLE
            require(result.compatibility_status == expected_status and result.dispatch_authority is False,
                    "boundary compatibility status/authority differs")
            iso = ",".join(datetime.strptime(day, "%Y%m%d").date().isoformat() for day in result.legacy_utc_resolved_dates)
            if expected_status == comment.REPRESENTABLE:
                request = parse_explicit_request(days=iso, target_legs=20, bookie="sportybet", profile="shadow",
                                                 create_share_code=True, target_total_odds=None, now=now)
                require(result.canonical_request_bytes == canonical_json_bytes(request) and
                        result.canonical_request_sha256 == request.canonical_sha256 and
                        not request.place_wager and request.create_share_code, "canonical request parity differs")
            else:
                require(result.canonical_request_bytes is None and result.canonical_request_sha256 is None,
                        "unrepresentable intent coerced")
                require(result.legacy_utc_resolved_dates[0] == "20260924", "legacy UTC date shifted")
            rows.append({"clock_utc": now.isoformat(), "command": command, "legacy_dates": list(result.legacy_utc_resolved_dates),
                         "status": result.compatibility_status, "request_sha256": result.canonical_request_sha256,
                         "exact_byte_parity": expected_status == comment.REPRESENTABLE, "date_shift": False})
    return rows


def notification_evidence():
    """Exercise actual mail owner with fake config/SMTP, never real transport."""
    fixture = {"dataset_name": mail.EXPECTED_DATASET, "status": "RESEARCH_NO_CODE_NO_BET",
               "shareCode": None, "shareURL": None, "share_code_receipt": None,
               **dict.fromkeys(("sportybet_login_used", "sportybet_cookie_used", "sportybet_wallet_used",
                                "stake_submitted", "wager_placed"), False)}
    raw = canonical(fixture)
    sha = hashlib.sha256(raw).hexdigest()
    rows = []
    with tempfile.TemporaryDirectory(prefix="athena-c3-mail-offline-") as directory:
        source, delivery = Path(directory) / "business.json", Path(directory) / "delivery.json"
        source.write_bytes(raw)
        for mode in ("unconfigured", "delivered", "connect", "starttls", "login", "send_message"):
            calls = []
            class SMTP:
                def __init__(self, host, port, timeout):
                    require((host, port, timeout) == ("smtp.gmail.com", 587, 30), "SMTP endpoint drift")
                    calls.append("connect")
                    if mode == "connect":
                        raise OSError("SYNTHETIC_FAILURE_NO_SECRET_VALUES")
                def __enter__(self): return self
                def __exit__(self, *args): return False
                def stage(self, stage):
                    calls.append(stage)
                    if mode == stage:
                        raise mail.smtplib.SMTPException("SYNTHETIC_FAILURE_NO_SECRET_VALUES")
                def starttls(self): self.stage("starttls")
                def login(self, *args): self.stage("login")
                def send_message(self, message): self.stage("send_message")
            config = dict(zip(SECRET_NAMES, ("", "", "") if mode == "unconfigured" else
                              ("synthetic@example.invalid", "SYNTHETIC_NOT_A_CREDENTIAL", "synthetic@example.invalid")))
            with patch.dict(mail.os.environ, config), patch.object(mail.smtplib, "SMTP", SMTP):
                result = mail.send_receipt_email(receipt_path=source, delivery_receipt_path=delivery)
            status = mail.EMAIL_SKIPPED_UNCONFIGURED if mode == "unconfigured" else mail.EMAIL_DELIVERED if mode == "delivered" else mail.EMAIL_FAILED
            require(result["status"] == status and result["source_receipt_sha256"] == sha and
                    source.read_bytes() == raw and result["secrets_recorded"] is False and result["wager_placed"] is False and
                    result["smtp_successful_send"] == (mode == "delivered"), "notification mutated business result")
            require(mode != "unconfigured" or not calls, "unconfigured SMTP constructed")
            require("SYNTHETIC_NOT_A_CREDENTIAL" not in delivery.read_text(), "secret recorded")
            rows.append({"case": mode, "status": status, "source_before_sha256": sha, "source_after_sha256": sha,
                         "source_receipt_sha256": result["source_receipt_sha256"], "smtp_successful_send": result["smtp_successful_send"],
                         "failure_type": result["failure_type"], "secrets_recorded": False, "wager_placed": False})
        source.write_bytes(b"INVALID_JSON")
        try:
            mail.send_receipt_email(receipt_path=source, delivery_receipt_path=delivery)
        except mail.CurrentShadowEmailError:
            pass
        else:
            raise ValueError("invalid source receipt did not fail closed")
    return rows


def expected_evidence():
    before, after = tracked(BEFORE_FIXTURE), tracked(WORKFLOW)
    require(evolution.source_identity(before) == BEFORE_IDENTITY, "exact historical before fixture differs")
    verify_workflow_authority(before, after)
    predecessor = json.loads(tracked(PREDECESSOR_PATH))
    require(predecessor["canonical_sha256"] == PREDECESSOR_SHA == evolution.canonical_sha256(predecessor) and
            len(predecessor["transitions"]) == 10 and predecessor["transitions"][9]["transition_id"] ==
            "CORE01B_ATHENA_RUN_CANONICAL_ARTIFACT_ANCESTRY_V1", "C2 predecessor differs")
    c2 = json.loads(tracked(C2_RECEIPT_PATH))
    require(c2["canonical_sha256"] == C2_RECEIPT_SHA == evolution.canonical_sha256(c2), "C2 receipt differs")
    transition = {"transition_id": TRANSITION_ID, "phase_id": "CORE-01C", "operation": "MAINTENANCE_REVISE",
                  "workflow_path": WORKFLOW, "canonical_family": "ATHENA_RUN", "before": BEFORE_IDENTITY,
                  "after": evolution.source_identity(after), "historical_before_fixture": {"path": BEFORE_FIXTURE, **BEFORE_IDENTITY},
                  "maintenance_contract": evolution.MAINTENANCE_CONTRACT, "evidence_receipt_path": RECEIPT_PATH,
                  "checkpoint_snapshot_path": SNAPSHOT_PATH}
    receipt = {"schema_version": 1, "policy_id": POLICY_ID, "repository": "Thabearr/ATHENA", "base_main_sha": BASE_MAIN,
               "core_01b_reviewed_head": "bc0c1a173a37cf363b80c2cc239cce60a0dcb5ce", "core_01b_merge_commit": BASE_MAIN,
               "core_01b_receipt_sha256": C2_RECEIPT_SHA,
               "postmerge_fixture_catalog": {"run_id": 36829944259, "head_sha": BASE_MAIN, "result": "SUCCESS"},
               "postmerge_tests": {"run_id": 36829944279, "head_sha": BASE_MAIN, "result": "SUCCESS_SYNTAX_SHARDS_1_8_AGGREGATE"},
               "governance": {"source_review_counter_while_open": "3/5", "source_review_counter_if_merged": "4/5",
                   "mandatory_reread_due": False, "p4_4": "INCOMPLETE", "checkpoint_e": "INCOMPLETE",
                   "clean_successor_proof": "INCOMPLETE_NOT_RERUN", "lg_a": "NOT_RUN_NOT_AUTHORIZED",
                   "caller_migration": "NOT_AUTHORIZED", "schedule_migration": "NOT_AUTHORIZED", "retirement": "NOT_AUTHORIZED"},
               "issue_comment": {"policy_id": comment.POLICY_ID, "status": comment.DISPOSITION,
                   "grammars": [comment.SCOPE_GRAMMAR, comment.EXPLICIT_DATES_GRAMMAR], "issue_number": 276,
                   "commenter": "github.repository_owner", "admission_prefix": "/athena-shadow ",
                   "parser_owner": SOURCE_PATHS[1], "cli": SOURCE_PATHS[2], "dispatch_authority": False,
                   "create_share_code_compatibility_intent": True, "place_wager": False, "date_shift": False,
                   "canonical_equivalence": comment_evidence()},
               "notification": {"status": "EXPLICIT_RETAINED_SECONDARY_NON_AUTHORITATIVE",
                   "secret_names": list(SECRET_NAMES), "secret_scope": "EMAIL_STEP_ONLY", "recipient_source": "RECIPIENT_EMAIL_ONLY",
                   "smtp": "smtp.gmail.com:587", "source_receipt": "artifacts/current-shadow-all-market/current-shadow-all-market-run-receipt.json",
                   "delivery_receipt": "artifacts/current-shadow-all-market/current-shadow-email-delivery-receipt.json",
                   "transport_failure": "EMAIL_FAILED_WARNING_EXIT_ZERO", "integrity_security_failure": "FAIL_CLOSED",
                   "desktop_email": "NOT_ENABLED_PENDING_RECIPIENT_CONSENT_TRANSPORT_LIFECYCLE_REVIEW",
                   "mocked_matrix": notification_evidence(), "business_receipt_mutation": False, "core_rerun": False},
               "source_identities": {path: evolution.source_identity(tracked(path)) for path in SOURCE_PATHS},
               "workflow_before_identity": BEFORE_IDENTITY, "workflow_after_identity": evolution.source_identity(after),
               "reviewed_workflow_transition": transition, "workflow_evolution_checkpoint_path": SNAPSHOT_PATH,
               "predecessor_checkpoint_sha256": PREDECESSOR_SHA, "predecessor_transition_count": 10,
               "transition_position": 11, "current_live_workflow_count": 39, "current_p4_3_retired_workflow_count": 3,
               "workflow_authority_delta": 0, "historical_receipts_changed": False, "current_shadow": "ACTIVE",
               "remaining_blockers": ["SCHEDULED_SHADOW_OWNERSHIP", "LIVE_CANONICAL_SHADOW_PROOF"],
               "safety_counts": dict.fromkeys(("network", "provider", "share_code", "delivery", "email", "live_dispatch",
                                               "login", "cookies", "wallet", "stake", "wager"), 0)}
    transition["evidence_body_sha256"] = evolution.receipt_evidence_body_sha256(receipt)
    receipt["reviewed_workflow_transition"] = {k: v for k, v in transition.items() if k != "evidence_body_sha256"}
    ledger = copy.deepcopy(predecessor)
    ledger["transitions"].append(transition)
    ledger["current_workflow_tree_sha1"] = subprocess.check_output(["git", "rev-parse", "HEAD:.github/workflows"], text=True).strip()
    ledger["canonical_sha256"] = evolution.canonical_sha256(ledger)
    receipt["workflow_evolution_ledger_sha256"] = ledger["canonical_sha256"]
    receipt["canonical_sha256"] = evolution.canonical_sha256(receipt)
    return receipt, ledger


def audit():
    receipt, checkpoint = expected_evidence()
    require(json.loads(tracked(RECEIPT_PATH)) == receipt, "C3 receipt differs from rederived evidence")
    ledger = evolution.validate_current_state()
    require(json.loads(tracked(SNAPSHOT_PATH)) == ledger == checkpoint, "C3 checkpoint differs")
    evolution.validate_evolution_snapshot_extension(json.loads(tracked(PREDECESSOR_PATH)), ledger)
    return {"result": "PASS", "policy_id": POLICY_ID, "receipt_sha256": receipt["canonical_sha256"],
            "ledger_sha256": ledger["canonical_sha256"], "transition_count": 11, "live_count": 39, "retired_count": 3,
            "real_side_effect_counts": receipt["safety_counts"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        receipt, ledger = expected_evidence()
        for path, value in ((RECEIPT_PATH, receipt), (SNAPSHOT_PATH, ledger), (evolution.LEDGER_PATH.as_posix(), ledger)):
            (ROOT / path).write_bytes(canonical(value))
        print(json.dumps({"receipt_sha": receipt["canonical_sha256"], "ledger_sha": ledger["canonical_sha256"]}))
    else:
        print(json.dumps(audit(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
