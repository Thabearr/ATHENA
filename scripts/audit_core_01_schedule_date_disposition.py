"""Offline, fail-closed CORE-01A disposition; never a migration/live authority."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain import current_shadow_fixture_date_request as legacy
from domain import execution_envelope as envelope
from domain.run_contracts import canonical_json_bytes
from runtime.source_identity import read_tracked_head_blob as read_current_head_blob
from services.athena_run_request_parser import CLI_TIMEZONE_ID, parse_explicit_request
from services.athena_run_workflow_request import resolve_workflow_request

BASE_MAIN = "1393cd6d246b01ba0784ed276b12e26a4e808c09"
PORT_HEAD = "979a93077be7846164a2c8600a2a5dca83eb5d12"
POLICY_ID = "ATHENA_CORE_01A_DATE_SCHEDULE_DISPOSITION_V1"
ARTIFACT_PATH = "artifacts/architecture/core_01_schedule_date_disposition_v1.json"
CANONICAL_WORKFLOW = ".github/workflows/athena-run.yml"
LEGACY_WORKFLOW = ".github/workflows/current-shadow-all-market.yml"
AUTH_PATH = "artifacts/architecture/auth_01_analysis_only_shadow_v1.json"
P44H_PATH = "artifacts/architecture/p4_4h_current_shadow_canonical_run_migration_review_v1.json"
PORT_PATH = "artifacts/architecture/port_02_native_runtime_v1.json"
CORE01B_WORKFLOW_AFTER_BLOB = "684122f69c29946a82c6fb1713db71bd8cf86afc"
CORE01B_WORKFLOW_AFTER_SHA256 = "1aa9f8f94deb80249dc079e828b719121e381f3a7e1289ee42ea797ff31afdac"
CORE01B_BEFORE_FIXTURE = "tests/fixtures/architecture/revised_workflows/athena-run-pre-core-01b-canonical-artifact-ancestry.yml"
CORE01C_WORKFLOW_AFTER_BLOB = "7ebeabcd0e4b0b388363760f6284afb63d97cad7"
CORE01C_WORKFLOW_AFTER_SHA256 = "fb54376740a7cff8e100a15c629cdbd9b1a34dc6fe8005362a8a2bbcee2faed2"
CORE01C_BEFORE_FIXTURE = "tests/fixtures/architecture/revised_workflows/current-shadow-all-market-pre-core-01c-compatibility-thin.yml"

# Exact reviewed main blobs, not repinned predecessor self-identities. Full
# payload verification and filtered worktree verification use PORT-01's helper.
SOURCE_BLOBS = {
    CANONICAL_WORKFLOW: "08a05d011d570695a2191153b5c55a4e536cbd04",
    LEGACY_WORKFLOW: "4321d70563e98acaf1663f5a7b28781908535328",
    AUTH_PATH: "2270ae97e1529e620ad9df4e77df9510b10a453a",
    P44H_PATH: "924febf73ab39a55433e69fd64cc203d493d68df",
    PORT_PATH: "d21ff8cef38d6a06045f200bcdef981fa5034118",
    "artifacts/architecture/p4_4r_shadow_runtime_composition_stabilization_v1.json": "0ed10b25f57a87037bf2d786a8f2ec77b0b2f55f",
    "artifacts/architecture/p4_4s_canonical_adapter_bound_context_builder_v1.json": "a8368721e2181e44a54bce25aae6171df11b6b40",
    "artifacts/product/product_baseline_v1.json": "a37c079b9175c1e24ac098b87fd6bc28e23e9527",
    "domain/current_shadow_fixture_date_request.py": "9070298acd82ac40b9400b293a47f7a25b0d9cdc",
    "domain/current_shadow_run_contract_adapter.py": "01a1e23982748797642fa8c1b9e8b6c1abd84895",
    "domain/execution_envelope.py": "8f0a84db708fef11fabb857b21b1322cb5b5a36e",
    "domain/run_contracts.py": "629bb37bb3674f07dbab8a7b5dcf61bfa186bd24",
    "services/athena_run_request_parser.py": "e3c5d143de3ed4e9e1977227c1191c2c14ab582b",
    "services/athena_run_service.py": "16d54ff599bffc70cdd66498a440647cf8e8b131",
    "services/athena_run_workflow_request.py": "7479f83bdc2d40fbe0310b16b69485f6928963bb",
}


class DispositionError(ValueError):
    pass


def read_tracked_head_blob(root, path):
    """This V1 checkpoint inspects authenticated historical source."""
    from scripts.core_01d_historical_source import historical_tracked
    return historical_tracked(root, path)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DispositionError(message)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def canonical_sha(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical({k: v for k, v in value.items()
                                     if k != "canonical_sha256"})).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        require(key not in value, f"duplicate JSON key: {key}")
        value[key] = item
    return value


def parse_canonical(raw: bytes) -> dict[str, Any]:
    value = json.loads(raw, object_pairs_hook=_unique_object)
    require(type(value) is dict, "receipt must be an object")
    require(raw == canonical(value) + b"\n", "receipt bytes are not canonical JSON")
    require(value.get("canonical_sha256") == canonical_sha(value), "receipt self SHA differs")
    return value


def inspect_sources(root: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    identities, payloads = {}, {}
    for path, blob in SOURCE_BLOBS.items():
        raw, identity = read_tracked_head_blob(root, path)
        if path in {"services/athena_run_service.py", "domain/current_shadow_run_contract_adapter.py"} and identity.git_blob_sha1 != blob:
            from scripts.audit_lg_a_worker_launch_failure_remediation import historical_source
            raw, identity = historical_source(path, root=root)
        if path == LEGACY_WORKFLOW and identity.git_blob_sha1 == CORE01C_WORKFLOW_AFTER_BLOB:
            require(identity.git_blob_payload_sha256 == CORE01C_WORKFLOW_AFTER_SHA256, "exact C3 successor SHA differs")
            from scripts.audit_core_01c_notification_comment_compatibility import verify_workflow_authority as verify_c3
            historical, historical_identity = read_tracked_head_blob(root, CORE01C_BEFORE_FIXTURE)
            require(historical_identity.git_blob_sha1 == blob, "C1/C3 historical before fixture differs")
            verify_c3(historical, raw)
            raw, identity = historical, historical_identity
        if path == CANONICAL_WORKFLOW and identity.git_blob_sha1 == CORE01B_WORKFLOW_AFTER_BLOB:
            require(identity.git_blob_payload_sha256 == CORE01B_WORKFLOW_AFTER_SHA256,
                    "exact C2 successor SHA differs")
            from scripts.audit_core_01b_canonical_artifact_ancestry import verify_workflow_authority
            historical, historical_identity = read_tracked_head_blob(root, CORE01B_BEFORE_FIXTURE)
            require(historical_identity.git_blob_sha1 == blob, "C1 historical before fixture differs")
            verify_workflow_authority(historical, raw)
            # C1 receipt and claims remain pinned to their checkpoint; only this
            # exact no-authority-delta C2 source is permitted for current HEAD.
            raw, identity = historical, historical_identity
        require(identity.git_blob_sha1 == blob, f"reviewed source drift: {path}")
        payloads[path] = raw
        identities[path] = {"git_blob_sha1": identity.git_blob_sha1,
                            "git_blob_payload_sha256": identity.git_blob_payload_sha256}
    return identities, payloads


def boundary_cases() -> list[dict[str, Any]]:
    cases = []
    for clock in ("09:00", "22:59", "23:00"):
        now = datetime.fromisoformat(f"2026-09-24T{clock}:00+00:00")
        request = parse_explicit_request(days="today", target_legs=20, profile="shadow",
                                         create_share_code=False, now=now)
        utc_text = now.astimezone(timezone.utc).strftime("%Y%m%d")
        utc_dates = legacy.validate_fixture_dates((utc_text,), current_utc=now)
        same = request.dates[0].strftime("%Y%m%d") == utc_dates[0]
        cases.append({"instant_utc": now.isoformat().replace("+00:00", "Z"),
                      "utc_date": now.date().isoformat(),
                      "lagos_date": request.dates[0].isoformat(),
                      "legacy_today": utc_dates[0],
                      "classification": "EXACTLY_REPRESENTABLE" if same else
                      "UNREPRESENTABLE_WITHOUT_DATE_SHIFT"})
    return cases


def inspect_date_validation() -> None:
    """Re-derive bounds, concrete sorting, format and collision rejection offline."""
    now = datetime(2026, 9, 24, 9, tzinfo=timezone.utc)

    def resolve(days: str):
        return parse_explicit_request(days=days, target_legs=20, profile="shadow",
                                      create_share_code=False, now=now)

    for count in range(1, 8):
        dates = tuple(now.date() + timedelta(days=i) for i in range(count))
        require(resolve(",".join(day.isoformat() for day in reversed(dates))).dates == dates,
                "canonical selected dates differ")
        utc_text = tuple(day.strftime("%Y%m%d") for day in dates)
        require(legacy.validate_fixture_dates(reversed(utc_text), current_utc=now) == utc_text,
                "legacy selected dates differ")
    for text in ("", "today,today", "today,2026-09-24", "2026-9-24", "2026-02-30",
                 "2026-09-23", "2026-10-01", ",".join(["today"] * 8)):
        try:
            resolve(text)
        except ValueError:
            continue
        raise DispositionError(f"canonical invalid date accepted: {text}")
    for dates in ((), ("2026-09-24",), ("20260931",), ("20260923",), ("20261001",),
                  ("20260924", "20260924"), tuple(f"202609{i}" for i in range(24, 32))):
        try:
            legacy.validate_fixture_dates(dates, current_utc=now)
        except legacy.CurrentShadowFixtureDateRequestError:
            continue
        raise DispositionError(f"legacy invalid date accepted: {dates}")


def inspect_semantics(payloads: dict[str, bytes]) -> dict[str, Any]:
    """Inspect reviewed bytes and exercise pure owners; never execute workflows."""
    text = {path: raw.decode("utf-8") for path, raw in payloads.items()}
    for path in (CANONICAL_WORKFLOW, LEGACY_WORKFLOW):
        require(text[path].count('cron: "0 9 * * *"') == 1, f"schedule differs: {path}")
        require("backfill" not in text[path].lower() and "catch-up" not in text[path].lower(),
                f"unexpected backfill: {path}")
        for ancestry in ("current-shadow-all-market.yml/runs?status=success&per_page=5",
                         "current-shadow-all-market-request",
                         "current-shadow-fixture-identity-v2-state.json"):
            require(ancestry in text[path], f"legacy ancestry absent: {path}: {ancestry}")
    require("issue_comment:" not in text[CANONICAL_WORKFLOW], "canonical comment trigger added")
    old = text[LEGACY_WORKFLOW]
    for token in ('target_size="20"', 'fixture_scope="today"', 'fixture_dates=""',
                  "issue_comment:", "scope=(today|three-day)", "dates=([0-9]{8}",
                  "Email durable Shadow result when configured", "if: always()",
                  "scripts.send_current_shadow_email", "current-shadow-email-delivery-receipt.json",
                  "scripts.execute_current_shadow_request"):
        require(token in old, f"legacy compatibility absent: {token}")
    require(CLI_TIMEZONE_ID == envelope.DATE_RESOLUTION_TIMEZONE_ID == "Africa/Lagos",
            "canonical timezone differs")
    require(envelope.DATE_RESOLUTION_POLICY_ID == "ATHENA_REQUEST_DATE_RESOLUTION_LAGOS_V1",
            "canonical date policy differs")
    require(legacy.MAX_SELECTED_DATES == 7 and legacy.MAX_FORWARD_DAYS == 6,
            "legacy horizon differs")
    inspect_date_validation()
    require("value.astimezone(dt.timezone.utc).date()" in
            text["domain/current_shadow_fixture_date_request.py"], "legacy UTC owner differs")
    service = text["services/athena_run_service.py"]
    bridge = service[service.index("class _ShadowSupervisorExecutor:"):]
    require(bridge.index('status="SHADOW_DATE_POLICY_UNREPRESENTABLE"') <
            bridge.index("completed = _run_reviewed_shadow_worker("), "bridge occurs after work")
    require("if representable != requested_text:" in bridge, "exact no-shift check absent")
    request = resolve_workflow_request(event_name="schedule",
                                       now=datetime(2026, 9, 24, 9, tzinfo=timezone.utc))
    require((request.authority_profile, request.mode, request.target_legs,
             request.target_total_odds, request.bookie, request.create_share_code,
             request.place_wager) ==
            ("MAIN", "main_application", 20, None, "sportybet", False, False),
            "canonical scheduled request differs")
    auth = json.loads(payloads[AUTH_PATH])
    require(auth["governance"]["clean_live_successor_proof"] == "NOT_RERUN_IN_A5" and
            auth["governance"]["clean_successor_proof"] == "INCOMPLETE", "AUTH live proof expanded")
    mismatch = auth["historical_authorization_mismatch"]
    require(mismatch["run_id"] == 36345657852 and
            mismatch["classification"] ==
            "POST_P4_4S_INTERNAL_SUCCESS_AUTHORIZATION_NONCOMPLIANT_SHARE_CODE_SIDE_EFFECT" and
            mismatch["owner_authorized_share_code_action"] is False,
            "historical authorization exception erased")
    p44h = json.loads(payloads[P44H_PATH])
    require(p44h["migration_dispositions"]["live_canonical_shadow_successor_proof_completed"]
            is False, "P4.4H live proof expanded")
    return {"canonical_scheduled_request": json.loads(canonical_json_bytes(request)),
            "canonical_scheduled_request_sha256": request.canonical_sha256}


def expected_receipt(root: Path = ROOT) -> dict[str, Any]:
    identities, payloads = inspect_sources(root)
    measured = inspect_semantics(payloads)
    auth = json.loads(payloads[AUTH_PATH])
    port = json.loads(payloads[PORT_PATH])
    cases = boundary_cases()
    require([case["classification"] for case in cases] ==
            ["EXACTLY_REPRESENTABLE", "EXACTLY_REPRESENTABLE",
             "UNREPRESENTABLE_WITHOUT_DATE_SHIFT"], "boundary behavior differs")
    receipt = {
        "schema_version": 1, "policy_id": POLICY_ID,
        "repository": {"name": "Thabearr/ATHENA", "base_main_sha": BASE_MAIN,
                       "port_02c_reviewed_head": PORT_HEAD, "port_02c_merge_commit": BASE_MAIN,
                       "port_02c_receipt_canonical_sha256": port["canonical_sha256"],
                       "postmerge_fixture_catalog": {"run_id": 36799780794,
                           "head_sha": BASE_MAIN, "status": "COMPLETED", "result": "SUCCESS"},
                       "postmerge_tests": {"run_id": 36799780766, "head_sha": BASE_MAIN,
                           "status": "COMPLETED", "result": "SUCCESS",
                           "successful_jobs": ["syntax", *[f"test shard {i} of 8" for i in range(1, 9)], "test"]}},
        "source_identities": identities,
        "governance": {"source_review_counter_at_start": 1,
                       "source_review_counter_while_open": "1/5",
                       "source_review_counter_if_merged": "2/5",
                       "mandatory_5_of_5_reread_due": False,
                       "block_b_to_c_bounded_refresh_completed": True,
                       "p4_4": "INCOMPLETE", "checkpoint_e": "INCOMPLETE",
                       "lg_a": "NOT_RUN_NOT_AUTHORIZED", "caller_migration": "NOT_AUTHORIZED",
                       "workflow_retirement": "NOT_AUTHORIZED"},
        "bounded_refresh": {"governing_product_sources": "OWNER_SUPPLIED_PDF_EXCERPTS_CORE_01A_C1_AND_BLUEPRINT_SEQUENCE_WORKFLOW_DATE_RECOVERY",
                            "original_product_pdfs_reread": False,
                            "current_issue_337_comment": 5922619630,
                            "postmerge_authority": "OWNER_HANDOFF_RECONCILED_WITH_LIVE_MAIN_PR_425_AND_POSTMERGE_CI",
                            "current_contract_paths": list(SOURCE_BLOBS),
                            "historical_receipts_modified": False},
        "successor_proof": {
            "disposition": "INCOMPLETE_CLEAN_LIVE_SUCCESSOR_PROOF_NOT_RERUN",
            "auth_01d_policy_id": auth["policy_id"],
            "auth_01d_canonical_sha256": auth["canonical_sha256"],
            "auth_01d_offline_analysis_only_proof": "PASS_PORTFOLIO_READY_NO_DELIVERY",
            "auth_01d_clean_live_successor_proof": "NOT_RERUN",
            "historical_run": 36345657852,
            "historical_classification": auth["historical_authorization_mismatch"]["classification"],
            "historical_internal_execution_evidence_useful": True,
            "clean_successor_proof": "INCOMPLETE", "lg_a": "NOT_RUN_NOT_AUTHORIZED",
            "migration_allowed": False, "caller_migration_authorized": False,
            "schedule_migration_authorized": False, "workflow_retirement_authorized": False,
            "offline_auth_or_port_replay_is_live_proof": False,
            "github_success_is_business_success_proof": False},
        "canonical_date_owner": {"module_function": "services.athena_run_request_parser.parse_explicit_request",
            "owner_chain": ["parse_explicit_request", "RunRequest concrete dates", "canonical request bytes", "ExecutionEnvelope date-resolution metadata"],
            "timezone": "Africa/Lagos", "policy_id": envelope.DATE_RESOLUTION_POLICY_ID,
            "selected_dates": "1..7", "horizon": "local today..today+6",
            "relative_tokens_resolved_once": True, "explicit_format": "YYYY-MM-DD",
            "sorted_deterministic_dates": True, "duplicate_resolutions_rejected": True,
            "accepted_dates_frozen_in_run_request": True, "utc_evidence_times_remain_utc_z": True,
            "target_legs_independent_of_target_total_odds": True},
        "legacy_date_owner": {"module": "domain.current_shadow_fixture_date_request",
            "policy_id": legacy.POLICY_ID, "timezone": "UTC", "explicit_format": "YYYYMMDD",
            "selected_dates": "1..7", "horizon": "UTC today..today+6",
            "scope_compatibility": ["today", "three-day"], "issue_comment_dates": "UTC YYYYMMDD",
            "malformed_duplicate_out_of_window_rejected": True},
        "representability": {"boundary_cases": cases, "date_shift_performed": False,
            "seven_day_boundary": {"instant_utc": "2026-09-24T23:00:00Z",
                "legacy_utc_horizon": ["20260924", "20260930"],
                "canonical_lagos_horizon": ["20260925", "20261001"],
                "classification": "UNREPRESENTABLE_WITHOUT_DATE_SHIFT"},
            "service_status": "SHADOW_DATE_POLICY_UNREPRESENTABLE",
            "service_rule": "EXACT_CANONICAL_DATES_MUST_FIT_EXISTING_UTC_WINDOW_BEFORE_WORKER_LAUNCH",
            "boundary_today_difference_does_not_reject_all_canonical_requests": True,
            "no_fallback_today_or_timezone_coercion": True},
        "schedule_disposition": {**measured,
            "canonical_cron": "0 9 * * *", "legacy_cron": "0 9 * * *",
            "canonical_schedule": "RETAIN_MAIN_NO_DELIVERY_0900Z_UNCHANGED",
            "legacy_shadow_schedule": "RETAIN_PENDING_CLEAN_SUCCESSOR_AND_OPERATIONAL_DISPOSITION",
            "legacy_request": {"profile": "SHADOW", "target": 20, "scope": "today",
                               "explicit_dates": [], "timezone": "UTC"},
            "both_schedule_surfaces_unchanged": True,
            "cron_parity_is_semantic_equivalence": False,
            "missed_run_backfill": "FORBIDDEN", "schedule_migration": "NOT_AUTHORIZED",
            "workflow_retirement": "NOT_AUTHORIZED", "r1_desktop_requires_unattended_scheduling": False,
            "retention_reasons": ["CLEAN_LIVE_SUCCESSOR_PROOF_MISSING", "AUTHORITY_PROFILE_DIFFERENCE",
                "DATE_POLICY_DIFFERENCE", "SEPARATE_LEGACY_NOTIFICATION_EMAIL",
                "LEGACY_IDENTITY_HISTORY_ANCESTRY", "ISSUE_COMMENT_COMPATIBILITY", "R1_NO_SCHEDULE_REQUIREMENT"]},
        "open_blockers": {"ISSUE_COMMENT_COMPATIBILITY": "RETAIN_BOTH_SCOPE_AND_EXPLICIT_DATE_GRAMMARS",
            "NOTIFICATION_EMAIL": "SEPARATE_POST_CORE_CONSUMER_NOT_MIGRATED_NOT_SENT",
            "PERSISTENT_IDENTITY_ANCESTRY": "RETAIN_LEGACY_SUCCESSFUL_RUN_HISTORY_AND_CURRENT_SHADOW_ALL_MARKET_REQUEST_ARTIFACT",
            "LIVE_CANONICAL_SHADOW_PROOF": "OPEN_LG_A_NOT_AUTHORIZED"},
        "safety": {"provider_acquisition": False, "delivery_share_code": False, "email": False,
            "login_cookies_wallet_stake_wager": False, "workflow_dispatch": False,
            "workflow_yaml_changed": False, "workflow_evolution_transition_added": False,
            "historical_receipts_changed": False,
            "side_effect_counts": {key: 0 for key in ("network", "provider_acquisition", "share_code",
                "delivery", "email", "live_workflow_dispatch", "login", "cookies", "wallet", "stake", "wager")}},
    }
    receipt["canonical_sha256"] = canonical_sha(receipt)
    return receipt


def receipt_bytes(root: Path = ROOT) -> bytes:
    """Historical receipt identity is its exact tracked blob, not checkout EOLs."""
    return read_tracked_head_blob(root, ARTIFACT_PATH)[0]


def audit(root: Path = ROOT, *, artifact_bytes: bytes | None = None) -> dict[str, Any]:
    expected = expected_receipt(root)
    raw = receipt_bytes(root) if artifact_bytes is None else artifact_bytes
    actual = parse_canonical(raw)
    # Byte equality also rejects Python's bool/int equality (false == 0).
    require(raw == canonical(expected) + b"\n",
            "receipt differs from independently reviewed source/disposition")
    return {"result": "PASS", "policy_id": POLICY_ID,
            "canonical_sha256": actual["canonical_sha256"],
            "source_identity_count": len(SOURCE_BLOBS), "live_authority": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-receipt", action="store_true")
    args = parser.parse_args()
    try:
        if args.print_receipt:
            print(canonical(expected_receipt()).decode("utf-8"))
        else:
            print(json.dumps(audit(), sort_keys=True))
    except (ValueError, OSError, KeyError) as exc:
        print(f"CORE-01A FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
