"""Fail-closed audit for the offline P4.4J selected-source issuer seam fix."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from domain.ingest_contracts import canonical_json_bytes, strict_json_loads
from scripts import audit_p4_3_workflow_retirement_ledger as retirement
from scripts import audit_p4_4g_current_fotmob_canonical_only_workflow as p44g
from scripts import audit_p4_4h_current_shadow_canonical_run_migration_review as p44h
from scripts import audit_p4_4i_shadow_supervisor_failure_evidence as p44i
from scripts import audit_p4_workflow_evolution_ledger as evolution


BASE_MAIN = "301f5d13ca8f60392c52d8ff132e8740b9b979bb"
POLICY_ID = "ATHENA_P4_4J_SHADOW_SELECTED_SOURCE_ISSUER_NETWORK_CONTROL_V1"
RECEIPT_PATH = Path(
    "artifacts/architecture/p4_4j_shadow_selected_source_issuer_network_control_v1.json"
)
SOURCE_PATH = "scripts/execute_current_shadow_request.py"
SOURCE_BEFORE = {
    "git_blob_sha1": "e774407bdba1eac918c20a47cfa6027fdd94a456",
    "source_sha256": "56d7b934000a666f547681c4fa793c038cf46e0f1a3e476118e9d4617d756336",
}
SOURCE_AFTER = {
    "git_blob_sha1": "281ee558bba6f425113244e021e0ff0cd7e0e02e",
    "source_sha256": "1ea9b2a582eab774a14736e67a4dfdfdf199286cd0496bba99f3e1edec65f9f9",
}
P44I_AUDIT_PATH = "scripts/audit_p4_4i_shadow_supervisor_failure_evidence.py"
P44I_AUDIT_BEFORE = {
    "git_blob_sha1": "5c06e673319b7938c5a9703aa848d800738f3cb1",
    "source_sha256": "054e4fb958bfb494f32b61961807714e62771135719bd0806d24ccb58d7182ac",
}
P44I_AUDIT_AFTER = {
    "git_blob_sha1": "9ce5b5beb19ad80e7b3cd7b0a9a10feebb158954",
    "source_sha256": "44aa3ed9a362b6f2393e018810a6c17f0d7e1056ce43b3cbe5f9337af17d0b43",
}
P44I_TEST_PATH = "tests/test_p4_4i_shadow_supervisor_failure_evidence.py"
P44I_TEST_BEFORE = {
    "git_blob_sha1": "ae42fb13f50b1bb0d5fb6037272ead1655ab40c2",
    "source_sha256": "ca6da612307e8e864a8189a848695e8778627eaf1e8ffe45a667ff1442961b24",
}
P44I_TEST_AFTER = {
    "git_blob_sha1": "bc602fee306208bdc2753756f300a4d3c88226cb",
    "source_sha256": "9c42615073974b9e07a6331b108038a69ab54fc679a99ff70e9e2ff9167fe410",
}
WORKFLOW_TREE_SHA1 = "d58f71b9ac653c8762f1d9b18eede15755ee1a76"
WORKFLOW_COUNT = 38
EVOLUTION_SHA256 = "b9ee60aa5cfa63080159cae839ca82b5662fdfbfe70a91055392a1728ed05f7a"
EVOLUTION_TRANSITIONS = 6
RETIREMENT_SHA256 = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
RETIRED_COUNT = 3
P44H_RECEIPT_SHA256 = "0000a5978268909dd07330d59079bc4d7f8d32c0fee161653a4a19eea9b97c64"
P44I_RECEIPT_SHA256 = "d6f65a382c4ef23318a81261e48b8e717f768864a6e1e5baed61af3c11351a7c"
EXPECTED_CHANGED_PATHS = {
    str(RECEIPT_PATH).replace("\\", "/"),
    "docs/architecture/athena_run_workflow.md",
    "scripts/audit_p4_4i_shadow_supervisor_failure_evidence.py",
    "scripts/audit_p4_4j_shadow_selected_source_issuer_network_control.py",
    SOURCE_PATH,
    "tests/test_execute_current_shadow_request.py",
    "tests/test_p4_4i_shadow_supervisor_failure_evidence.py",
    "tests/test_p4_4j_shadow_selected_source_issuer_network_control.py",
}
# Offline P3.0 continuity tests may materialize these untracked local outputs.
# Preserve them as local evidence; they are not P4.4J inputs or PR changes.
LOCAL_PROTECTED_TEST_OUTPUT_PATHS = {
    "artifacts/p3-0-comparison-evidence/p3-0-e1-live-readiness.json",
    "p3-0-e1-live-readiness.json",
}
LOCAL_TEST_DIAGNOSTIC_PATHS = (
    p44i.LOCAL_TEST_DIAGNOSTIC_PATHS | LOCAL_PROTECTED_TEST_OUTPUT_PATHS
)


class P44JReviewError(AssertionError):
    """P4.4J receipt or current-source invariant did not match reviewed semantics."""


def _git(*args: str) -> bytes:
    result = subprocess.run(["git", *args], capture_output=True)
    if result.returncode:
        raise P44JReviewError(
            f"git {' '.join(args)} failed: {result.stderr.decode('utf-8', 'replace')}"
        )
    return result.stdout


def _canonical_sha(value: dict[str, Any]) -> str:
    body = {key: item for key, item in value.items() if key != "canonical_sha256"}
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def _identity(source: bytes) -> dict[str, str]:
    return evolution.source_identity(source)


def expected_receipt() -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository_base_main_sha": BASE_MAIN,
        "prior_architecture": {
            "workflow_tree_sha1": WORKFLOW_TREE_SHA1,
            "workflow_count": WORKFLOW_COUNT,
            "workflow_evolution_ledger_sha256": EVOLUTION_SHA256,
            "workflow_evolution_transition_count": EVOLUTION_TRANSITIONS,
            "p4_3_retirement_ledger_sha256": RETIREMENT_SHA256,
            "p4_3_retired_workflow_count": RETIRED_COUNT,
            "p4_4h_receipt_sha256": P44H_RECEIPT_SHA256,
            "p4_4i_receipt_sha256": P44I_RECEIPT_SHA256,
        },
        "prior_live_evidence": {
            "run_id": 36119049997,
            "run_url": "https://github.com/Thabearr/ATHENA/actions/runs/36119049997",
            "workflow_name": "ATHENA Canonical Run",
            "event": "workflow_dispatch",
            "attempt": 1,
            "exact_main_sha": BASE_MAIN,
            "dispatch_inputs": {
                "days": "2026-09-25",
                "target_legs": 20,
                "target_total_odds": "",
                "bookie": "sportybet",
                "profile": "shadow",
            },
            "request": {
                "sha256": "af5b8c5de987f4dacd286f734dd57be7f17b7d0091d743e373c63683cfa1e69e",
                "authority_profile": "SHADOW",
                "mode": "research_shadow",
                "date": "2026-09-25",
                "timezone": "Africa/Lagos",
                "target_legs": 20,
                "target_total_odds": None,
                "create_share_code": True,
                "place_wager": False,
            },
            "artifact_id": 10856121902,
            "artifact_name": "athena-run-36119049997",
            "artifact_zip_sha256": "d3cfc66ad2786304c2ca0c18f86d02c9a2597901a8d25c3ce5999fb0b30329a3",
            "canonical_run_receipt_sha256": "918678993d2f08df3779e3ebf103e7acfa1c3ff8bd118e9306f6c4c7382db8e9",
            "inner_current_shadow_receipt_sha256": "6e78b117cf95b5aee2ea121dd203d68d41c7c70a1c6899135cef308228c37c02",
            "stage_checkpoint_sha256": "f44ab77f5047c4b268454885462058763187016dc32de8f40c7a1a33ca5befe0",
            "workflow_request_resolution_sha256": "6d4d264fd348da44bbb2d7c01e9085fb6a31c9058bf514775428e94b699cd9e7",
            "restored_identity_state_sha256": "2f60f84df120f8bd908643c0f0b7319d9f5ffd576dc7b52caf5e738749125769",
            "github_workflow_conclusion": "success",
            "business_status": "SOURCE_INCOMPLETE",
            "selected_leg_count": 0,
            "shortfall": 20,
            "share_code_result": None,
            "wager_placed": False,
            "preserved_stage": "CURRENT_FOTMOB_SOURCE",
            "supervisor_returncode": 1,
            "failure_classification": "CURRENT_SHADOW_SUPERVISOR_NONZERO",
            "failure_boundary": "CURRENT_SHADOW_SUPERVISOR",
            "terminal_receipt_accepted": False,
            "provisional_marker_observed": True,
            "failure_text_classification": "SELECTED_SOURCE_ISSUER_REJECTED_EXECUTE_LIVE_NETWORK_KEYWORD",
            "exception_inferred": False,
            "owner_authorization_consumed": True,
            "dispatch_count": 1,
            "retry_count": 0,
            "no_retry_authorized": True,
            "live_successor_proof_complete": False,
            "live_successor_blocker_open": True,
        },
        "source_identity": {
            "path": SOURCE_PATH,
            "before": SOURCE_BEFORE,
            "after": SOURCE_AFTER,
        },
        "p4_4i_historical_audit_compatibility": {
            "reviewed_head": p44i.P44I_REVIEWED_HEAD,
            "immutable_receipt_unchanged": True,
            "historical_mode_skips_old_current_main_requirement": True,
            "explicit_live_mode_remains_strict": True,
            "source_identities": {
                P44I_AUDIT_PATH: {
                    "before": P44I_AUDIT_BEFORE,
                    "after": P44I_AUDIT_AFTER,
                },
                P44I_TEST_PATH: {
                    "before": P44I_TEST_BEFORE,
                    "after": P44I_TEST_AFTER,
                },
            },
        },
        "correction_scope": {
            "root_cause": "EXPLICIT_DATE_SELECTED_SOURCE_ISSUER_NETWORK_CONTROL_CALL_CONTRACT_MISMATCH",
            "selected_issuer_accepts_execute_live_network_keyword": True,
            "caller_network_control_value_preserved": True,
            "false_does_not_become_true": True,
            "default_network_control_remains_true": True,
            "selected_date_validation_order_and_horizon_unchanged": True,
            "exact_no_fixtures_skip_semantics_unchanged": True,
            "other_source_failures_propagate": True,
            "monkeypatch_restoration_unconditional": True,
            "football_source_admission_pricing_router_portfolio_delivery_semantics_changed": False,
            "timeout_changed": False,
            "workflow_yaml_changed": False,
            "workflow_evolution_transition_added": False,
            "caller_migration": False,
            "retirement": False,
            "new_authority": False,
            "provider_acquisition_during_pr": False,
            "provider_request_count_during_pr": 0,
            "workflow_dispatch_during_pr": False,
            "live_proof_during_pr": False,
            "live_retry_during_pr": False,
            "share_code_operation_during_pr": False,
            "login_during_pr": False,
            "cookies_during_pr": False,
            "wallet_during_pr": False,
            "staking_during_pr": False,
            "wager_during_pr": False,
            "wager_placed": False,
            "live_successor_proof_remains_open": True,
        },
        "review_governance": {
            "source_review_counter_while_unmerged": "2/5",
            "source_review_counter_if_merged": "3/5",
            "mandatory_source_reread_after_merge": False,
            "p4_4_overall_complete": False,
            "architecture_checkpoint_e_complete": False,
        },
    }
    value["canonical_sha256"] = _canonical_sha(value)
    return value


def _read_canonical(path: Path) -> dict[str, Any]:
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    value = strict_json_loads(raw)
    if type(value) is not dict or canonical_json_bytes(value) != raw:
        raise P44JReviewError(f"canonical JSON invalid: {path}")
    return value


def _validate_receipt(value: Any) -> dict[str, Any]:
    expected = expected_receipt()
    if type(value) is not dict or value != expected:
        raise P44JReviewError("P4.4J receipt differs from exact reviewed semantics")
    if value.get("canonical_sha256") != _canonical_sha(value):
        raise P44JReviewError("P4.4J receipt canonical self-hash is invalid")
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
            raise P44JReviewError("pull_request event is not bound to exact P4.4J base/head")
    else:
        remote_main = _git("rev-parse", "origin/main").decode().strip()
        if remote_main != BASE_MAIN:
            raise P44JReviewError(f"origin/main moved from exact P4.4J base: {remote_main}")
    try:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", BASE_MAIN, "HEAD"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        if not trusted_pr_event:
            raise P44JReviewError("exact P4.4J base is not in current history")
        try:
            _git("cat-file", "-e", f"{BASE_MAIN}^{{commit}}")
        except P44JReviewError:
            # Depth-1 synthetic PR checkout: trust only its exact base/head event binding.
            pass
        else:
            raise P44JReviewError("available P4.4J base object is not an ancestor of HEAD")
    return trusted_pr_event


def _verify_prior_receipts() -> None:
    p44h_receipt = p44h.audit(check_live=False)
    if p44h_receipt.get("canonical_sha256") != P44H_RECEIPT_SHA256:
        raise P44JReviewError("immutable P4.4H receipt drifted")
    p44i_receipt = p44i.audit(check_live=False)
    if p44i_receipt.get("canonical_sha256") != P44I_RECEIPT_SHA256:
        raise P44JReviewError("immutable P4.4I receipt drifted")
    p44g.audit(check_live=False)


def _verify_current_architecture() -> None:
    if _git("rev-parse", "HEAD:.github/workflows").decode().strip() != WORKFLOW_TREE_SHA1:
        raise P44JReviewError("workflow tree changed")
    paths = _git("ls-tree", "-r", "--name-only", "HEAD", ".github/workflows").decode().splitlines()
    if sum(path.endswith((".yml", ".yaml")) for path in paths) != WORKFLOW_COUNT:
        raise P44JReviewError("workflow count changed")

    ledger = evolution.validate_current_state()
    if (
        ledger.get("canonical_sha256") != EVOLUTION_SHA256
        or evolution.canonical_sha256(ledger) != EVOLUTION_SHA256
        or len(ledger.get("transitions", [])) != EVOLUTION_TRANSITIONS
    ):
        raise P44JReviewError("current P4 workflow-evolution state changed")
    retirement_state = retirement.validate_retirement_history()
    if (
        retirement_state.get("canonical_sha256") != RETIREMENT_SHA256
        or retirement_state.get("current_retired_workflow_count") != RETIRED_COUNT
    ):
        raise P44JReviewError("P4.3 retirement history changed")


def _verify_source_identity() -> None:
    before = _identity(_git("show", f"{BASE_MAIN}:{SOURCE_PATH}"))
    unstaged = subprocess.run(["git", "diff", "--quiet", "--", SOURCE_PATH], capture_output=True)
    if unstaged.returncode:
        raise P44JReviewError("P4.4J source has unstaged changes beyond the indexed reviewed bytes")
    after = _identity(_git("show", f":{SOURCE_PATH}"))
    if before != SOURCE_BEFORE:
        raise P44JReviewError("P4.4J source before identity differs from exact base")
    if after != SOURCE_AFTER:
        raise P44JReviewError("P4.4J source after identity differs from reviewed implementation")


def _verify_p4_4i_audit_compatibility_identities() -> None:
    for path, before_expected, after_expected in (
        (P44I_AUDIT_PATH, P44I_AUDIT_BEFORE, P44I_AUDIT_AFTER),
        (P44I_TEST_PATH, P44I_TEST_BEFORE, P44I_TEST_AFTER),
    ):
        before = _identity(_git("show", f"{BASE_MAIN}:{path}"))
        unstaged = subprocess.run(["git", "diff", "--quiet", "--", path], capture_output=True)
        if unstaged.returncode:
            raise P44JReviewError(f"P4.4I historical compatibility file is unstaged: {path}")
        after = _identity(_git("show", f":{path}"))
        if before != before_expected or after != after_expected:
            raise P44JReviewError(f"P4.4I historical compatibility source identity drift: {path}")


def _changed_paths() -> set[str]:
    paths = set(_git("diff", "--name-only", f"{BASE_MAIN}...HEAD").decode().splitlines())
    for line in _git("status", "--porcelain", "--untracked-files=all").decode().splitlines():
        if len(line) >= 4:
            path = line[3:]
            if path not in LOCAL_TEST_DIAGNOSTIC_PATHS:
                paths.add(path)
    return paths


def _verify_scope_and_workflow_immutability() -> None:
    if _changed_paths() != EXPECTED_CHANGED_PATHS:
        raise P44JReviewError("P4.4J changed paths differ from the exact reviewed scope")
    result = subprocess.run(
        ["git", "diff", "--quiet", BASE_MAIN, "--", ".github/workflows"],
        capture_output=True,
    )
    if result.returncode:
        raise P44JReviewError("workflow YAML differs from exact P4.4J base")
    for path in _changed_paths():
        if path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml")):
            raise P44JReviewError("P4.4J changed workflow YAML")


def audit(*, check_live: bool = True) -> dict[str, Any]:
    try:
        receipt = _validate_receipt(_read_canonical(RECEIPT_PATH))
        _verify_prior_receipts()
        if check_live:
            _verify_base()
            _verify_current_architecture()
            _verify_source_identity()
            _verify_p4_4i_audit_compatibility_identities()
            _verify_scope_and_workflow_immutability()
        return receipt
    except (OSError, ValueError, AssertionError, json.JSONDecodeError) as exc:
        if isinstance(exc, P44JReviewError):
            raise
        raise P44JReviewError(f"P4.4J audit failed: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.write:
            RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
            RECEIPT_PATH.write_bytes(canonical_json_bytes(expected_receipt()))
        receipt = audit(check_live=True)
        print(f"P4.4J selected-source network-control audit: PASS ({receipt['canonical_sha256']})")
        return 0
    except (P44JReviewError, OSError, ValueError) as exc:
        print(f"P4.4J audit: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
