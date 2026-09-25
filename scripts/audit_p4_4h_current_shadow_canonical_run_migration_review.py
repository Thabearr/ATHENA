"""Fail-closed, offline P4.4H Current Shadow to athena-run migration review."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from domain import current_shadow_fixture_date_request as legacy_dates
from domain.current_shadow_run_contract_adapter import adapt_current_shadow_request
from domain.ingest_contracts import canonical_json_bytes, strict_json_loads
from services.athena_run_request_parser import CLI_TIMEZONE_ID
from services.athena_run_workflow_request import resolve_workflow_request
from scripts import audit_p4_3_workflow_retirement_ledger as retirement
from scripts import audit_p4_4g_current_fotmob_canonical_only_workflow as p44g
from scripts import audit_p4_workflow_evolution_ledger as evolution

BASE_MAIN = "64eab40138790b9c7a294e25dc2ba9397e8a5ece"
POLICY_ID = "ATHENA_P4_4H_CURRENT_SHADOW_CANONICAL_RUN_MIGRATION_REVIEW_V1"
RECEIPT_PATH = Path("artifacts/architecture/p4_4h_current_shadow_canonical_run_migration_review_v1.json")
MATRIX_PATH = Path("artifacts/architecture/p4_3_workflow_capability_matrix_v1.json")
P44G_RECEIPT_PATH = Path("artifacts/architecture/p4_4g_current_fotmob_canonical_only_workflow_v1.json")
EVOLUTION_PATH = evolution.LEDGER_PATH
RETIREMENT_SHA256 = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
P44G_RECEIPT_SHA256 = "af0e87fc9fc925d1c30f5f2adee699be0724fa1b68842963f25c5a1f56fe12af"
EVOLUTION_SHA256 = "b9ee60aa5cfa63080159cae839ca82b5662fdfbfe70a91055392a1728ed05f7a"
MATRIX_SHA256 = "6b417a19557efdd39201e233fb866e4143b8102ba2879a4f1481e5241722dd8d"
WORKFLOW_TREE = "d58f71b9ac653c8762f1d9b18eede15755ee1a76"
WORKFLOW_COUNT = 38
RETIRED_COUNT = 3
CURRENT_SHADOW = ".github/workflows/current-shadow-all-market.yml"
ATHENA_RUN = ".github/workflows/athena-run.yml"
EXPECTED_IDENTITIES = {
    CURRENT_SHADOW: ("4321d70563e98acaf1663f5a7b28781908535328", "d63c108c672bb65bd5875074a933905446ca13a01bc6818ba9e10871972e1f01"),
    ATHENA_RUN: ("f4d4a23b3e21be18ea52314425169ff9862d27ef", "444de03c00aa8dc47b7b92a5bdfa333516ff22c055fa798cf706e372f6fb6430"),
    "services/athena_run_service.py": ("64d46481adf9a7e0fd65fcbe599868cb4a3a3d95", "0a87df8ef7274dcbff25088f36fcbaefe085394cc378eb8ec447a65d25f3bc98"),
    "services/athena_run_workflow_request.py": ("fef386a682a821bdd282552bc5d6d811c1be3514", "00117a236599d3f5b3f8f4d77fad53a29834c0e6ec33121341e0b645414fc047"),
    "services/athena_run_request_parser.py": ("27520e3224ec9be910218c3b0ee0c1686bb0a5e8", "5b2f5c83c19749bb1769026e3bb34d1cd5c2ab7f701cc446ef962d80a75c6772"),
    "domain/current_shadow_run_contract_adapter.py": ("886b1950e9c505621096641ce43740d627ed0526", "6026137dc9ce8a038a3ae74752968f0e1f89de66a7676bfbba972d3e2f5bd160"),
    "domain/current_shadow_fixture_date_request.py": ("9070298acd82ac40b9400b293a47f7a25b0d9cdc", "e6283d4f9544a20784e53a224c30375ea2934c26d6c4497b88bec10c44add9a7"),
    "scripts/execute_current_shadow_request.py": ("e774407bdba1eac918c20a47cfa6027fdd94a456", "56d7b934000a666f547681c4fa793c038cf46e0f1a3e476118e9d4617d756336"),
    "scripts/send_current_shadow_email.py": ("bc3b58e665258ca95d6dcd21d3cb7486fba17e51", "95326e2376f04def452dfa5f021c23a24f4cd9fcf743ea2e76a892d7940e13bb"),
    "domain/current_shadow_all_market_runner.py": ("34af555d6d6129ed766328b0c8f4c958beadd03e", "86859c57da2b62e3030edde862f97a86b18b39d7d6915f932ebf9729705b0760"),
    "scripts/execute_current_shadow_daily.py": ("a3991fcb843931b2f4f9fbd80aa086a9393799e4", "028d808275b0fc0b318f53409e1912968a3f4ca8930b5c5c27bde6c56cba1bb8"),
    "scripts/execute_current_shadow_all_market_fresh_reprice_bound.py": ("f3851254c3e2fd44dc6ddcf6ae86b0e3c333f9c2", "3123a3f3e344790e874df6e735f865ff373ff452f2b2f9cfc547d91a9e2b67b6"),
    ".github/workflows/p3-0-comparison-evidence-capture.yml": ("0d0d2285e7b17ca625288ec295884433e3c3cedd", "4001b4ee0f3624204d873d0556e4499219c850736ab447de5345b576f5efb902"),
    "tests/test_current_shadow_persisted_identity_ancestry.py": ("f4d9ad6451b02d778eb22cd6ce7ac54dc393518c", "632ae907dcef4a7f3fdb749d2a64c3db5760064e799fecb2978598b5fcb265f0"),
    "tests/test_current_shadow_history_github_persistent_cache.py": ("b347de5059c5b1ca71e28a2b1707636afe3f193c", "96d7939efd7c19c39b292520d6a73fde6187aaf5329ed30a8d619067fa55ec42"),
    "tests/test_p3_0_e1_owner_dispatch_bridge.py": ("7e1b9faf72e2e78bda61a7c2ae407c4640b09857", "1b926d50806513ccc84793e3c763714eeea0f5a7c08a0777b86d5663c285c73d"),
    "tests/test_current_shadow_daily_workflow.py": ("76e7b45d0aef95c9efb8522ffa19c2fa34dd8415", "dd0cea52f6e5333702f7b12902114b790c99c8e7128c2378865c0f78781ddaa0"),
    "tests/test_current_shadow_run_contract_adapter.py": ("20d3197ce0308c1581e346975baa8fdf82262dec", "cccec4c21ee3c0833849a3f0720387e9b737e7fd54d55b94b9ab48ec705981ae"),
}
FRESH_HOLDOUT_PATHS = (
    ".github/workflows/audit-fotmob-utc-native-xg-fresh-holdout-lineage.yml",
    ".github/workflows/bridge-fotmob-fresh-holdout-continuity-receipts.yml",
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout-release-receipts.yml",
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml",
    ".github/workflows/verify-fotmob-fresh-holdout-history-pagination.yml",
    ".github/workflows/watch-fotmob-fresh-holdout-scheduler-liveness.yml",
)
FRESH_HOLDOUT_IDENTITIES = {
    FRESH_HOLDOUT_PATHS[0]: ("0ba12d02fc2cd5f7a7d9fb1458eeec5cbe3bbd23", "13d8888ea802b2ef996b3e296a668f087a20a50fd0ee51ee8c5cbbc26673a274"),
    FRESH_HOLDOUT_PATHS[1]: ("74bfd162bd5fe67b79dd6c91550dbbb557b502e9", "6902f337ee1e33aaf9cd742cdd42796ef6f1a6e299097d4a204959b872b47ebd"),
    FRESH_HOLDOUT_PATHS[2]: ("3dbac1abd91462859089b94742412b4e75b0a997", "44ab05cd4034f4275fc8fc8d480ba0ff6b7fb725ed691ed7f0824a23b708922f"),
    FRESH_HOLDOUT_PATHS[3]: ("1efe1e34d4459b2aeea17d5da8ba77bd4e2442f2", "9ee4a81f508196716ccd4454b24644f8f5c9aece479103f4a17f8f9a13cfdbb9"),
    FRESH_HOLDOUT_PATHS[4]: ("c00eb7589ac7d5393b9cbd2368e0bd56520a961e", "003d93d934c8ac26ad9bcbd32dd27b54450048592ce1c3375db5512686b2cadd"),
    FRESH_HOLDOUT_PATHS[5]: ("f613211018417435cb4ad7a22529b1ff0a38d690", "2c77dfc4070bdf76a26b2209622f3ffc5fd82758f1203504729e9c90d375da21"),
}


class P44HReviewError(AssertionError):
    """P4.4H evidence or invariant did not match the reviewed source."""


def _git(*args: str) -> bytes:
    result = subprocess.run(["git", *args], capture_output=True)
    if result.returncode:
        raise P44HReviewError(f"git {' '.join(args)} failed: {result.stderr.decode('utf-8', 'replace')}")
    return result.stdout


def _identity(path: str, ref: str = "HEAD") -> dict[str, str]:
    return evolution.source_identity(_git("show", f"{ref}:{path}"))


def _canonical_sha(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes({k: v for k, v in value.items() if k != "canonical_sha256"})).hexdigest()


def _request_policy(scope: str, explicit: list[str] | None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "dataset_name": "athena-current-shadow-request-policy-v1",
        "fixture_dates": explicit,
        "fixture_scope": scope,
        "authority": {
            "production_model": False,
            "pricing": False,
            "selection": False,
            "sportybet_execution": False,
            "bet": False,
            "wager_placed": False,
        },
        "wager_placed": False,
    }


def _pair_case(name: str, dates: tuple[date, ...], *, scope: str = "today", target: int = 20, now: datetime | None = None, classification: str = "EXACTLY_REPRESENTABLE") -> dict[str, Any]:
    legacy = adapt_current_shadow_request(
        target_size=target,
        request_policy=_request_policy(scope, [d.strftime("%Y%m%d") for d in dates]),
    )
    canonical = resolve_workflow_request(
        event_name="workflow_dispatch",
        dispatch_inputs={
            "days": ",".join(d.strftime("%Y-%m-%d") for d in dates),
            "target_legs": str(target),
            "target_total_odds": "",
            "bookie": "sportybet",
            "profile": "shadow",
        },
        now=now or datetime(dates[0].year, dates[0].month, dates[0].day, 9, tzinfo=timezone.utc),
    )
    same = legacy.canonical_sha256 == canonical.canonical_sha256
    return {
        "case": name,
        "classification": classification if same else "UNREPRESENTABLE_WITH_CURRENT_CANONICAL_WORKFLOW_REQUEST_SURFACE",
        "dates": [d.strftime("%Y%m%d") for d in dates],
        "target_legs": target,
        "legacy_request_sha256": legacy.canonical_sha256,
        "canonical_request_sha256": canonical.canonical_sha256,
        "canonical_intent": {
            "authority_profile": canonical.authority_profile,
            "mode": canonical.mode,
            "target_legs": canonical.target_legs,
            "target_total_odds": None,
            "bookie": canonical.bookie,
            "create_share_code": canonical.create_share_code,
            "place_wager": canonical.place_wager,
        },
        "parity": same,
    }


def _request_parity() -> dict[str, Any]:
    from datetime import timedelta

    normal = datetime(2026, 9, 24, 9, tzinfo=timezone.utc)
    last_common = datetime(2026, 9, 24, 22, 59, tzinfo=timezone.utc)
    boundary = datetime(2026, 9, 24, 23, 0, tzinfo=timezone.utc)
    common_dates = (date(2026, 9, 24),)
    seven_dates = tuple(date(2026, 9, 24) + timedelta(days=i) for i in range(7))
    utc_today_at_boundary = date(2026, 9, 24)
    lagos_today_at_boundary = date(2026, 9, 25)
    cases = [
        _pair_case("workflow_dispatch_target_1", common_dates, target=1),
        _pair_case("workflow_dispatch_target_50", common_dates, target=50),
        _pair_case("workflow_dispatch_today_normal_0900z", common_dates),
        _pair_case("workflow_dispatch_today_2259z", common_dates, now=last_common),
        _pair_case("workflow_dispatch_three_day_scope_expanded_to_explicit_dates", common_dates + (date(2026, 9, 25), date(2026, 9, 26)), scope="three-day", classification="REPRESENTABLE_ONLY_WITH_EXPLICIT_DATE_PRESERVATION"),
        _pair_case("workflow_dispatch_explicit_seven_day_horizon", seven_dates, scope="today", now=last_common, classification="REPRESENTABLE_ONLY_WITH_EXPLICIT_DATE_PRESERVATION"),
    ]
    # These are source-level facts, not caller mappings: athena-run's schedule
    # currently resolves to MAIN, while Current Shadow schedule resolves SHADOW.
    legacy_schedule = adapt_current_shadow_request(
        target_size=20,
        request_policy=_request_policy("today", None),
        resolved_dates=(utc_today_at_boundary,),
    )
    canonical_schedule = resolve_workflow_request(event_name="schedule", now=normal)
    return {
        "legacy_target_bounds": {"minimum": 1, "maximum": 50, "invalid_values": [0, 51], "canonical_rejected": True},
        "invalid_request_cases": [
            {"case": "target_below_minimum_0", "classification": "INVALID_BY_EXISTING_LEGACY_POLICY"},
            {"case": "target_above_maximum_51", "classification": "INVALID_BY_EXISTING_LEGACY_POLICY"},
            {"case": "duplicate_explicit_date", "classification": "INVALID_BY_EXISTING_LEGACY_POLICY"},
            {"case": "malformed_explicit_date", "classification": "INVALID_BY_EXISTING_LEGACY_POLICY"},
            {"case": "more_than_seven_explicit_dates", "classification": "INVALID_BY_EXISTING_LEGACY_POLICY"},
            {"case": "date_before_utc_today_or_after_utc_plus_6", "classification": "INVALID_BY_EXISTING_LEGACY_POLICY"},
        ],
        "valid_request_pairs": cases,
        "schedule_mapping": {
            "legacy": {"time_utc": "09:00", "authority_profile": "SHADOW", "mode": "research_shadow", "target_legs": 20, "target_total_odds": None, "bookie": "sportybet", "create_share_code": True, "place_wager": False},
            "canonical_current": {"authority_profile": canonical_schedule.authority_profile, "mode": canonical_schedule.mode, "target_legs": canonical_schedule.target_legs, "target_total_odds": None, "bookie": canonical_schedule.bookie, "create_share_code": canonical_schedule.create_share_code, "place_wager": canonical_schedule.place_wager},
            "legacy_shadow_request_sha256": legacy_schedule.canonical_sha256,
            "classification": "UNREPRESENTABLE_WITH_CURRENT_CANONICAL_WORKFLOW_REQUEST_SURFACE",
            "reason": "athena-run schedule has no SHADOW profile input and resolves its reviewed default profile=main",
        },
        "timezone_edges": [
            {"instant_utc": "2026-09-24T09:00:00Z", "utc_date": "20260924", "lagos_date": "20260924", "classification": "EXACTLY_REPRESENTABLE"},
            {"instant_utc": "2026-09-24T22:59:00Z", "utc_date": "20260924", "lagos_date": "20260924", "classification": "EXACTLY_REPRESENTABLE"},
            {"instant_utc": "2026-09-24T23:00:00Z", "utc_date": "20260924", "lagos_date": "20260925", "classification": "UNREPRESENTABLE_WITH_CURRENT_CANONICAL_WORKFLOW_REQUEST_SURFACE"},
        ],
        "boundary_explicit_date": {
            "utc_legacy_date": "20260924",
            "legacy_policy_accepts": True,
            "canonical_lagos_today": "20260925",
            "canonical_explicit_utc_date_accepts": False,
            "classification": "UNREPRESENTABLE_WITH_CURRENT_CANONICAL_WORKFLOW_REQUEST_SURFACE",
            "date_shift_performed": False,
        },
        "seven_day_horizon": {
            "same_date_at_2026_09_24T22_59Z": True,
            "at_2026_09_24T23_00Z": False,
            "legacy_utc_window": ["20260924", "20260930"],
            "canonical_lagos_window": ["20260925", "20261001"],
            "classification": "UNREPRESENTABLE_WITH_CURRENT_CANONICAL_WORKFLOW_REQUEST_SURFACE",
        },
        "legacy_explicit_input_normalization": {
            "unsorted_unique_dates": "ACCEPTED_AND_SORTED_BY_EXISTING_LEGACY_POLICY",
            "unsorted_unique_dates_classification": "REPRESENTABLE_ONLY_WITH_EXPLICIT_DATE_PRESERVATION",
            "duplicates_malformed_more_than_seven_and_out_of_horizon": "REJECTED_BY_EXISTING_LEGACY_POLICY",
        },
        "issue_comment_grammar": {
            "scope": r"/athena-shadow target=([0-9]+) scope=(today|three-day)",
            "dates": r"/athena-shadow target=([0-9]+) dates=([0-9]{8}(?:,[0-9]{8}){0,6})",
            "scope_compatibility": "THIN_COMPATIBILITY_WRAPPER_RETAINED_PENDING_FUTURE_CALLER_REVIEW",
            "trigger_removed": False,
        },
        "cli_timezone": CLI_TIMEZONE_ID,
        "request_semantics_are_not_inferred_from_shared_supervisor": True,
    }


def _blockers() -> list[dict[str, Any]]:
    return [
        {"id": "SCHEDULED_SHADOW_OWNERSHIP", "legacy_owner": CURRENT_SHADOW, "canonical_candidate": ATHENA_RUN, "status": "OPEN_SCHEDULE_RESOLVES_MAIN_NOT_SHADOW", "migration_authorized": False, "retirement_authorized": False, "evidence": ["current-shadow schedule is 0 9 * * * and resolves target=20/today", "athena-run schedule is 0 9 * * * but resolver defaults profile=main"]},
        {"id": "NOTIFICATION_EMAIL", "legacy_owner": "scripts/send_current_shadow_email.py", "canonical_candidate": "post-core notification consumer", "status": "OPEN_SEPARABLE_POST_CORE_NOTIFICATION_NOT_MIGRATED", "migration_authorized": False, "retirement_authorized": False, "evidence": ["email step runs if: always() and reads durable Current Shadow receipt", "GMAIL_ADDRESS/GMAIL_APP_PASSWORD/RECIPIENT_EMAIL are scoped only to email step", "delivery receipt is separate; email delivery failure does not rewrite core Current Shadow receipt"], "future_requirement": "post-core consumer of durable canonical/compatibility evidence; failure must not rewrite core RunReceipt"},
        {"id": "PERSISTENT_IDENTITY_ANCESTRY", "legacy_owner": "current-shadow-all-market successful Actions run history + current-shadow-all-market-request artifact", "canonical_candidate": ATHENA_RUN, "status": "OPEN_HISTORICAL_ANCESTRY_CUTOVER_REQUIRED", "migration_authorized": False, "retirement_authorized": False, "evidence": ["both workflows query successful current-shadow-all-market.yml runs?status=success&per_page=5", "both download artifact current-shadow-all-market-request", "identity state file current-shadow-fixture-identity-v2-state.json"], "future_requirement": "preserve exact old run/artifact identities across cutover; do not fabricate or rewrite history"},
        {"id": "LIVE_CANONICAL_SHADOW_PROOF", "legacy_owner": CURRENT_SHADOW, "canonical_candidate": ATHENA_RUN, "status": "OPEN_NO_LIVE_PROOF_IN_OFFLINE_REVIEW", "migration_authorized": False, "retirement_authorized": False, "evidence": ["P4.4H uses deterministic pure request/service-injection tests only", "a live proof requires separate explicit owner authorization and bounded request budget"]},
        {"id": "ISSUE_COMMENT_COMPATIBILITY", "legacy_owner": "issue_comment /athena-shadow grammar", "canonical_candidate": ATHENA_RUN, "status": "OPEN_RETAIN_THIN_COMPATIBILITY_WRAPPER", "migration_authorized": False, "retirement_authorized": False, "evidence": ["reviewed exact two command regexes are recorded in request parity", "athena-run supports only schedule and workflow_dispatch events", "no trigger or grammar change in P4.4H"]},
    ]


def expected_receipt() -> dict[str, Any]:
    source_ids = {path: {"git_blob_sha1": blob, "source_sha256": sha} for path, (blob, sha) in EXPECTED_IDENTITIES.items()}
    fresh_ids = {path: {"git_blob_sha1": blob, "source_sha256": sha} for path, (blob, sha) in FRESH_HOLDOUT_IDENTITIES.items()}
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository_base_main_sha": BASE_MAIN,
        "source_identities": source_ids,
        "fresh_holdout_workflow_identities": fresh_ids,
        "p4_3a_matrix_sha256": MATRIX_SHA256,
        "frozen_p4_3a_current_shadow_baseline": {
            "workflow_path": CURRENT_SHADOW,
            "successor_family": "ATHENA_RUN",
            "retirement_blockers": [
                "scheduled SHADOW ownership not migrated",
                "notification/email capability not migrated",
                "persistent identity ancestry still consumes old workflow/artifact history",
                "live canonical SHADOW successor proof not established",
                "issue-comment compatibility still needs disposition",
            ],
            "retirement_eligible": False,
            "equivalence_claimed": False,
        },
        "p4_3_retirement_ledger_sha256": RETIREMENT_SHA256,
        "p4_4g_receipt_sha256": P44G_RECEIPT_SHA256,
        "p4_workflow_evolution_ledger_sha256": EVOLUTION_SHA256,
        "workflow_tree_sha1": WORKFLOW_TREE,
        "workflow_count": WORKFLOW_COUNT,
        "p4_3_retired_workflow_count": RETIRED_COUNT,
        "p4_4g_transition_prefix_count": 6,
        "legacy_capabilities": {
            "triggers": ["schedule:0 9 * * *", "workflow_dispatch", "issue_comment:created"],
            "workflow_dispatch": {"target_size": "1..50 exact integer", "fixture_scope": ["today", "three-day"], "fixture_dates": "explicit 1..7 UTC YYYYMMDD dates within current UTC through UTC+6 horizon"},
            "issue_comment_grammar": [r"/athena-shadow target=([0-9]+) scope=(today|three-day)", r"/athena-shadow target=([0-9]+) dates=([0-9]{8}(?:,[0-9]{8}){0,6})"],
            "core_execution": {"supervisor": "reviewed Current Shadow supervisor", "canonical_owner": "AthenaRunService._ShadowSupervisorExecutor", "request_path": "RunRequest -> AthenaRunService -> RunReceipt", "execution_parity_claimed_from_shared_supervisor_only": False},
            "restoration_and_ancestry": ["trusted-main durable-history prime", "PR119 bootstrap", "persistent fixture-identity state", "exact lineage-main binding"],
            "durable_evidence": {
                "legacy_artifact_name": "current-shadow-all-market-request",
                "canonical_artifact_name": "athena-run-${{ github.run_id }}",
                "identity_state_filename": "current-shadow-fixture-identity-v2-state.json",
                "legacy_layout": ["current-shadow-all-market-run-receipt.json", "current-shadow-all-market-stage.json", "current-shadow-all-market-progress.json", "source-evidence/", "identity-state/"],
                "canonical_layout": ["artifacts/athena-run-workflow/", "artifacts/athena-runs/<request-sha>/", "source-evidence/", "identity-state/"],
                "history_consumers": [
                    {"path": CURRENT_SHADOW, "query": "current-shadow-all-market.yml/runs?status=success&per_page=5", "run_filter": "no head_branch filter; skip GITHUB_RUN_ID", "artifact": "current-shadow-all-market-request", "selection": "first downloaded artifact containing current-shadow-fixture-identity-v2-state.json", "purpose": "restore current persistent fixture identity state"},
                    {"path": ATHENA_RUN, "query": "current-shadow-all-market.yml/runs?status=success&per_page=5", "run_filter": "no head_branch filter; skip GITHUB_RUN_ID", "artifact": "current-shadow-all-market-request", "selection": "first downloaded artifact containing current-shadow-fixture-identity-v2-state.json", "purpose": "restore current persistent fixture identity state"},
                    {"path": ".github/workflows/p3-0-comparison-evidence-capture.yml", "query": "current-shadow-all-market.yml/runs?status=success&per_page=10", "run_filter": "head_branch == main", "artifact": "current-shadow-all-market-request", "selection": "first downloaded artifact containing current-shadow-fixture-identity-v2-state.json", "purpose": "restore persistent identity state from trusted main run"},
                ],
                "dependent_tests": ["tests/test_current_shadow_persisted_identity_ancestry.py", "tests/test_current_shadow_history_github_persistent_cache.py", "tests/test_p3_0_e1_owner_dispatch_bridge.py"],
            },
            "notification": {"script": "scripts/send_current_shadow_email.py", "post_core": True, "step_if_always": True, "secrets_scoped_to_notification_step": True, "delivery_receipt_separate": True, "core_receipt_rewritten_by_email_failure": False},
            "permissions": {"workflow": {"contents": "read", "actions": "read"}, "no_p4_4h_permission_change": True},
        },
        "canonical_run_capabilities": {
            "triggers": ["schedule:0 9 * * *", "workflow_dispatch"],
            "schedule_default": {"profile": "main", "mode": "main_application", "target_legs": 20, "target_total_odds": None, "bookie": "sportybet", "create_share_code": False, "place_wager": False},
            "shadow_dispatch": {"profile": "shadow", "mode": "research_shadow", "target_legs": "1..50", "target_total_odds": None, "bookie": "sportybet", "create_share_code": True, "place_wager": False},
            "relative_date_timezone": CLI_TIMEZONE_ID,
            "uses_existing_reviewed_supervisor": True,
            "supervisor_owns_timeout_and_terminal_receipt": True,
            "service_adds_competing_supervisor_timeout": False,
            "identity_history_ancestry_cutover_complete": False,
        },
        "capability_assessments": [
            {"capability": "trigger_surface", "legacy_owner": CURRENT_SHADOW, "canonical_owner_or_candidate": ATHENA_RUN, "exact_evidence": ["legacy schedule 0 9 * * * + workflow_dispatch + issue_comment created", "canonical schedule 0 9 * * * + workflow_dispatch only"], "parity_status": "PARTIAL_ISSUE_COMMENT_WRAPPER_REMAINS", "blocker_status": "OPEN", "caller_migration_authorized": False, "workflow_retirement_authorized": False},
            {"capability": "request_surface", "legacy_owner": "scripts.execute_current_shadow_request.py + domain.current_shadow_fixture_date_request", "canonical_owner_or_candidate": "services.athena_run_workflow_request + services.athena_run_request_parser", "exact_evidence": ["target 1..50", "today/three-day scopes", "explicit 1..7 UTC YYYYMMDD within UTC through UTC+6", "canonical relative dates resolve Africa/Lagos"], "parity_status": "PARTIAL_EXPLICIT_DATE_MAPPING_WITH_UTC_LAGOS_BOUNDARY_BLOCKER", "blocker_status": "OPEN", "caller_migration_authorized": False, "workflow_retirement_authorized": False},
            {"capability": "core_execution", "legacy_owner": "scripts.execute_current_shadow_request.py", "canonical_owner_or_candidate": "AthenaRunService._ShadowSupervisorExecutor", "exact_evidence": ["source-controlled SHADOW/research_shadow/sportybet executor delegates to existing reviewed supervisor", "Current Shadow request/receipt adapter validates canonical identity", "supervisor owns timeout/final receipt"], "parity_status": "SAME_REVIEWED_EXECUTOR_OWNER_NO_FULL_WORKFLOW_EQUIVALENCE_CLAIM", "blocker_status": "LIVE_SUCCESSOR_PROOF_OPEN", "caller_migration_authorized": False, "workflow_retirement_authorized": False},
            {"capability": "restoration_and_ancestry", "legacy_owner": CURRENT_SHADOW, "canonical_owner_or_candidate": ATHENA_RUN, "exact_evidence": ["trusted-main durable-history prime", "PR119 bootstrap", "persistent fixture-identity state", "exact lineage-main binding"], "parity_status": "PARTIAL_OLD_ACTIONS_HISTORY_REMAINS_INPUT", "blocker_status": "OPEN_CUTOVER_CONTINUITY_REQUIRED", "caller_migration_authorized": False, "workflow_retirement_authorized": False},
            {"capability": "durable_evidence", "legacy_owner": "current-shadow-all-market-request artifact", "canonical_owner_or_candidate": "athena-run-${{ github.run_id }} artifact", "exact_evidence": ["athena-run and p3-0-comparison-evidence-capture query successful legacy workflow runs and download current-shadow-all-market-request", "legacy receipt/stage/progress/source-evidence layout differs from canonical run layout"], "parity_status": "NOT_BYTE_OR_HISTORY_EQUIVALENT", "blocker_status": "OPEN_PRESERVE_OLD_RUN_ARTIFACT_IDENTITIES", "caller_migration_authorized": False, "workflow_retirement_authorized": False},
            {"capability": "notification", "legacy_owner": "scripts/send_current_shadow_email.py", "canonical_owner_or_candidate": "separate post-core notification consumer", "exact_evidence": ["always() email step depends on durable legacy receipt", "secrets scoped to email step", "separate delivery receipt; mail failure does not rewrite core run receipt"], "parity_status": "SEPARABLE_BUT_NOT_MIGRATED", "blocker_status": "OPEN", "caller_migration_authorized": False, "workflow_retirement_authorized": False},
            {"capability": "issue_comment_compatibility", "legacy_owner": "issue_comment /athena-shadow grammar", "canonical_owner_or_candidate": "thin compatibility wrapper over canonical request service", "exact_evidence": ["two exact regex forms preserved in receipt", "athena-run event resolver rejects issue_comment"], "parity_status": "RETAIN_WRAPPER_CANDIDATE_NOT_MIGRATED", "blocker_status": "OPEN", "caller_migration_authorized": False, "workflow_retirement_authorized": False},
        ],
        "request_parity": _request_parity(),
        "blocker_review": _blockers(),
        "migration_dispositions": {
            "current_shadow_caller_migration_authorized": False,
            "current_shadow_workflow_retirement_authorized": False,
            "live_canonical_shadow_successor_proof_completed": False,
            "issue_comment_trigger_removed": False,
            "full_current_shadow_capability_equivalence_claimed": False,
            "provider_acquisition_authority_changed": False,
            "model_authority_changed": False,
            "pricing_authority_changed": False,
            "router_authority_changed": False,
            "portfolio_authority_changed": False,
            "selection_authority_changed": False,
            "share_code_authority_changed": False,
            "account_authority_changed": False,
            "login_authority_changed": False,
            "cookies_authority_changed": False,
            "wallet_authority_changed": False,
            "staking_authority_changed": False,
            "wager_authority_changed": False,
            "betting_authority_changed": False,
        },
        "review_execution": {
            "workflow_yaml_changed": False,
            "workflow_evolution_transition_added": False,
            "provider_acquisition_during_pr": False,
            "provider_request_count_during_pr": 0,
            "workflow_dispatch_during_pr": False,
            "current_shadow_live_run_performed": False,
            "fresh_holdout_run_performed": False,
            "p3_0_e1_run_performed": False,
            "share_code_created": False,
            "login_cookies_wallet_staking_wager_authority_added": False,
            "wager_placed": False,
            "p4_4_overall_complete": False,
            "architecture_checkpoint_e_complete": False,
            "source_review_counter_while_unmerged": "0/5",
            "source_review_counter_if_merged": "1/5",
            "mandatory_source_reread_after_merge": False,
        },
    }
    receipt["canonical_sha256"] = _canonical_sha(receipt)
    return receipt


def _read_canonical(path: Path) -> dict[str, Any]:
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    value = strict_json_loads(raw)
    if type(value) is not dict or canonical_json_bytes(value) != raw:
        raise P44HReviewError(f"canonical JSON invalid: {path}")
    return value


def _verify_base() -> bool:
    head = _git("rev-parse", "HEAD").decode().strip()
    trusted_pr_event = False
    if os.environ.get("GITHUB_EVENT_NAME") == "pull_request":
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        try:
            event = json.loads(Path(event_path).read_text(encoding="utf-8")) if event_path else {}
            pr = event.get("pull_request", {})
            event_head = pr.get("head", {}).get("sha", "")
            trusted_pr_event = (
                pr.get("base", {}).get("ref") == "main"
                and pr.get("base", {}).get("sha") == BASE_MAIN
                and re.fullmatch(r"[0-9a-f]{40}", str(event_head)) is not None
                and re.fullmatch(r"[0-9a-f]{40}", str(os.environ.get("GITHUB_SHA", ""))) is not None
                and head == os.environ.get("GITHUB_SHA")
            )
        except (OSError, json.JSONDecodeError):
            trusted_pr_event = False
        if not trusted_pr_event:
            raise P44HReviewError("pull_request event is not bound to exact P4.4H base/head")
    else:
        remote_main = _git("rev-parse", "origin/main").decode().strip()
        if remote_main != BASE_MAIN:
            raise P44HReviewError(f"origin/main moved from exact P4.4H base: {remote_main}")
    try:
        subprocess.run(["git", "merge-base", "--is-ancestor", BASE_MAIN, "HEAD"], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        if not trusted_pr_event:
            raise P44HReviewError("exact P4.4H base is not in current history")
    return trusted_pr_event


def _verify_base_source_identity(path: str, pair: tuple[str, str], *, trusted_pr_event: bool) -> None:
    """Bind a protected source to P4.4H base, tolerating only trusted shallow PR checkouts.

    GitHub's depth-1 synthetic pull-request checkout may omit the exact base commit
    object. In that case the event must bind the exact base SHA, and the checked-out
    source must independently retain the reviewed base identity. If the base commit
    is present, its tree is authoritative and is checked directly.
    """
    expected = {"git_blob_sha1": pair[0], "source_sha256": pair[1]}
    try:
        _git("cat-file", "-e", BASE_MAIN)
    except P44HReviewError:
        if not trusted_pr_event:
            raise P44HReviewError(f"exact P4.4H base object unavailable for {path}")
        if _identity(path) != expected:
            raise P44HReviewError(f"shallow P4.4H checkout source identity differs from reviewed base: {path}")
        return

    if evolution.source_identity(_git("show", f"{BASE_MAIN}:{path}")) != expected:
        raise P44HReviewError(f"authorized base source identity differs: {path}")


def audit(*, check_live: bool = True) -> dict[str, Any]:
    try:
        trusted_pr_event = _verify_base()
        expected = expected_receipt()
        receipt = _read_canonical(RECEIPT_PATH)
        if receipt != expected or receipt.get("canonical_sha256") != _canonical_sha(receipt):
            raise P44HReviewError("P4.4H receipt differs from exact reviewed semantics or self-hash")
        if check_live:
            matrix = _read_canonical(MATRIX_PATH)
            if matrix.get("canonical_sha256") != MATRIX_SHA256 or _canonical_sha(matrix) != MATRIX_SHA256:
                raise P44HReviewError("frozen P4.3A matrix identity/self-hash changed")
            frozen_row = next(
                (row for row in matrix.get("workflow_rows", []) if row.get("workflow_path") == CURRENT_SHADOW),
                None,
            )
            expected_baseline = expected["frozen_p4_3a_current_shadow_baseline"]
            if frozen_row is None or {
                "workflow_path": frozen_row.get("workflow_path"),
                "successor_family": frozen_row.get("successor_family"),
                "retirement_blockers": frozen_row.get("retirement_blockers"),
                "retirement_eligible": frozen_row.get("retirement_eligible"),
                "equivalence_claimed": frozen_row.get("capability_mapping", {}).get("equivalence_claimed"),
            } != expected_baseline:
                raise P44HReviewError("frozen P4.3A Current Shadow baseline row differs")
            p44g.audit(check_live=True)
            ledger = evolution.validate_current_state()
            if ledger.get("canonical_sha256") != EVOLUTION_SHA256 or len(ledger.get("transitions", [])) != 6:
                raise P44HReviewError("current evolution ledger identity/prefix changed")
            retirement_state = retirement.validate_retirement_history()
            if retirement_state.get("canonical_sha256") != RETIREMENT_SHA256 or retirement_state.get("current_retired_workflow_count") != RETIRED_COUNT:
                raise P44HReviewError("P4.3 retirement ledger changed")
            if _git("rev-parse", "HEAD:.github/workflows").decode().strip() != WORKFLOW_TREE:
                raise P44HReviewError("workflow tree changed during evidence-only P4.4H")
            count = sum(p.endswith((".yml", ".yaml")) for p in _git("ls-tree", "-r", "--name-only", "HEAD", ".github/workflows").decode().splitlines())
            if count != WORKFLOW_COUNT:
                raise P44HReviewError("workflow count changed")
            for path, pair in EXPECTED_IDENTITIES.items():
                if _identity(path) != {"git_blob_sha1": pair[0], "source_sha256": pair[1]}:
                    raise P44HReviewError(f"reviewed source identity drift: {path}")
            for path, pair in FRESH_HOLDOUT_IDENTITIES.items():
                if _identity(path) != {"git_blob_sha1": pair[0], "source_sha256": pair[1]}:
                    raise P44HReviewError(f"Fresh Holdout source identity drift: {path}")
            for path in (CURRENT_SHADOW, ATHENA_RUN):
                _verify_base_source_identity(path, EXPECTED_IDENTITIES[path], trusted_pr_event=trusted_pr_event)
        return receipt
    except (OSError, ValueError, AssertionError, json.JSONDecodeError) as exc:
        if isinstance(exc, P44HReviewError):
            raise
        raise P44HReviewError(f"P4.4H audit failed: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.write:
            value = expected_receipt()
            RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
            RECEIPT_PATH.write_bytes(canonical_json_bytes(value))
        audit(check_live=True)
        print(f"P4.4H offline Current Shadow migration review: PASS ({expected_receipt()['canonical_sha256']})")
        return 0
    except (P44HReviewError, OSError, ValueError) as exc:
        print(f"P4.4H audit: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
