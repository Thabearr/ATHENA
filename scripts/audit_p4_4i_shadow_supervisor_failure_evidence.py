"""Fail-closed evidence audit for P4.4I Current Shadow supervisor failures."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from domain.ingest_contracts import canonical_json_bytes, strict_json_loads
from scripts import audit_p4_3_workflow_retirement_ledger as retirement
from scripts import audit_p4_4g_current_fotmob_canonical_only_workflow as p44g
from scripts import audit_p4_4h_current_shadow_canonical_run_migration_review as p44h
from scripts import audit_p4_workflow_evolution_ledger as evolution

BASE_MAIN = "0066720de62611a3673468597335c3a2c55aacaf"
P44I_REVIEWED_HEAD = "9ff94e22a161373373900a3e7744311aaab29089"
POLICY_ID = "ATHENA_P4_4I_SHADOW_SUPERVISOR_FAILURE_EVIDENCE_V1"
RECEIPT_PATH = Path("artifacts/architecture/p4_4i_shadow_supervisor_failure_evidence_v1.json")
P44H_RECEIPT_SHA256 = "0000a5978268909dd07330d59079bc4d7f8d32c0fee161653a4a19eea9b97c64"
P44G_RECEIPT_SHA256 = "af0e87fc9fc925d1c30f5f2adee699be0724fa1b68842963f25c5a1f56fe12af"
EVOLUTION_SHA256 = "b9ee60aa5cfa63080159cae839ca82b5662fdfbfe70a91055392a1728ed05f7a"
RETIREMENT_SHA256 = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
WORKFLOW_TREE_SHA1 = "d58f71b9ac653c8762f1d9b18eede15755ee1a76"
WORKFLOW_COUNT = 38
RETIRED_COUNT = 3
SERVICE_PATH = "services/athena_run_service.py"
SERVICE_BEFORE = {
    "git_blob_sha1": "64d46481adf9a7e0fd65fcbe599868cb4a3a3d95",
    "source_sha256": "0a87df8ef7274dcbff25088f36fcbaefe085394cc378eb8ec447a65d25f3bc98",
}
SERVICE_AFTER = {
    "git_blob_sha1": "4797e59fa87bf44ef5ea525231e5f6f1ad302c28",
    "source_sha256": "f5f2d0bbe1c5855352361d2ecd14940225c66166898295b5cafe0edf6d8b6bce",
}
EXPECTED_CHANGED_PATHS = {
    "artifacts/architecture/p4_4i_shadow_supervisor_failure_evidence_v1.json",
    "docs/architecture/athena_run_workflow.md",
    "scripts/audit_p4_4i_shadow_supervisor_failure_evidence.py",
    "scripts/audit_p4_4h_current_shadow_canonical_run_migration_review.py",
    SERVICE_PATH,
    "tests/test_athena_run_service.py",
    "tests/test_p4_4h_current_shadow_canonical_run_migration_review.py",
    "tests/test_p4_4i_shadow_supervisor_failure_evidence.py",
}
# The existing offline Current Shadow history-verification tests may leave this
# explicitly non-authoritative diagnostic in the worktree. It is not source or
# phase evidence and must never be staged as part of P4.4I.
LOCAL_TEST_DIAGNOSTIC_PATHS = {
    "artifacts/current-shadow-all-market/current-shadow-history-artifact-verification-diagnostic.json"
}


class P44IReviewError(AssertionError):
    """P4.4I evidence or source invariant did not match reviewed semantics."""


def _git(*args: str) -> bytes:
    result = subprocess.run(["git", *args], capture_output=True)
    if result.returncode:
        raise P44IReviewError(
            f"git {' '.join(args)} failed: {result.stderr.decode('utf-8', 'replace')}"
        )
    return result.stdout


def _canonical_sha(value: dict[str, Any]) -> str:
    body = {key: item for key, item in value.items() if key != "canonical_sha256"}
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def _source_identity(path: str, ref: str = "HEAD") -> dict[str, str]:
    source = _git("show", f"{ref}:{path}")
    return evolution.source_identity(source)


def _worktree_source_identity(path: str) -> dict[str, str]:
    result = subprocess.run(["git", "diff", "--quiet", "--", path], capture_output=True)
    if result.returncode:
        raise P44IReviewError(f"unstaged {path} differs from the indexed canonical source")
    return evolution.source_identity(_git("show", f":{path}"))


def expected_receipt() -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository_base_main_sha": BASE_MAIN,
        "p4_4h_receipt_sha256": P44H_RECEIPT_SHA256,
        "p4_4g_receipt_sha256": P44G_RECEIPT_SHA256,
        "workflow_tree_sha1": WORKFLOW_TREE_SHA1,
        "workflow_count": WORKFLOW_COUNT,
        "workflow_evolution_ledger_sha256": EVOLUTION_SHA256,
        "workflow_evolution_transition_count": 6,
        "p4_3_retirement_ledger_sha256": RETIREMENT_SHA256,
        "p4_3_retired_workflow_count": RETIRED_COUNT,
        "supervisor_source_identity_before": SERVICE_BEFORE,
        "supervisor_source_identity_after": SERVICE_AFTER,
        "prior_live_evidence": {
            "run_id": 36111105935,
            "run_url": "https://github.com/Thabearr/ATHENA/actions/runs/36111105935",
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
            "canonical_request_sha256": "af5b8c5de987f4dacd286f734dd57be7f17b7d0091d743e373c63683cfa1e69e",
            "artifact_id": 10853141346,
            "artifact_name": "athena-run-36111105935",
            "artifact_zip_sha256": "2976c375787297c0759eb545e9d68706649d731b6b99fa26531f2baaab3b54d1",
            "canonical_run_receipt_sha256": "4b65f9b8e9e927e6261dac48ee71557ba7645e96eccff24682dcaa15f53dbec3",
            "inner_current_shadow_receipt_sha256": "63c9f0637ef5a1fa87545127577942902369e6b680eafdbcb3cd3ba965c21efe",
            "identity_state_sha256": "2f60f84df120f8bd908643c0f0b7319d9f5ffd576dc7b52caf5e738749125769",
            "workflow_request_resolution_sha256": "47aa53a842ae50d9ceb7c2141671b945558674a04a6274233304175babd3820d",
            "github_workflow_conclusion": "success",
            "business_status": "RESEARCH_NO_CODE_SOURCE_INCOMPLETE",
            "selected_leg_count": 0,
            "shortfall": 20,
            "share_code_result": None,
            "wager_placed": False,
            "provider_event_count": 0,
            "reconciled_fixture_count": 0,
            "priced_fixture_count": 0,
            "router_selected_count": 0,
            "supervisor_returncode": 1,
            "completed_current_shadow_stage": "CURRENT_FOTMOB_SOURCE",
            "inner_receipt_reasons": ["SOURCE_CHAIN_PENDING:STARTED"],
            "exact_child_exception": "UNKNOWN_NOT_DURABLY_PRESERVED",
            "source_exception_inferred": False,
            "live_successor_proof_complete": False,
            "live_successor_blocker_open": True,
            "owner_live_authorization_consumed": True,
            "dispatch_count": 1,
            "retry_count": 0,
            "no_retry_authorized": True,
            "login_used": False,
            "cookies_used": False,
            "wallet_accessed": False,
            "stake_submitted": False,
            "wager_placed": False,
        },
        "correction_scope": {
            "offline_evidence_integrity_only": True,
            "nonzero_supervisor_is_source_incomplete": True,
            "startup_provisional_marker_is_not_terminal": True,
            "bounded_stdout_stderr_tails_preserved": True,
            "validated_checkpoint_metadata_only": True,
            "child_exception_inferred": False,
            "provider_acquisition_during_pr": False,
            "provider_request_count_during_pr": 0,
            "workflow_dispatch_during_pr": False,
            "current_shadow_live_run_during_pr": False,
            "fresh_holdout_during_pr": False,
            "p3_0_e1_during_pr": False,
            "share_code_operation_during_pr": False,
            "login_during_pr": False,
            "cookies_during_pr": False,
            "wallet_during_pr": False,
            "staking_during_pr": False,
            "wager_during_pr": False,
            "workflow_yaml_changed": False,
            "caller_migration_authorized": False,
            "workflow_retirement_authorized": False,
            "new_authority_added": False,
            "live_successor_proof_completed": False,
            "retry_of_run_36111105935": False,
            "workflow_evolution_transition_added": False,
            "no_new_outer_timeout": True,
            "timeout_owner_unchanged": True,
        },
        "review_governance": {
            "source_review_counter_while_unmerged": "1/5",
            "source_review_counter_if_merged": "2/5",
            "mandatory_source_reread_after_merge": False,
            "p4_4_overall_complete": False,
            "architecture_checkpoint_e_complete": False,
        },
    }
    value["canonical_sha256"] = _canonical_sha(value)
    return value


def _read_canonical(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n")
    value = strict_json_loads(normalized)
    if type(value) is not dict or canonical_json_bytes(value) != normalized:
        raise P44IReviewError(f"canonical JSON invalid: {path}")
    return value


def _validate_receipt(value: Any) -> dict[str, Any]:
    expected = expected_receipt()
    if type(value) is not dict or value != expected:
        raise P44IReviewError("P4.4I receipt differs from exact reviewed semantics")
    if value.get("canonical_sha256") != _canonical_sha(value):
        raise P44IReviewError("P4.4I receipt canonical self-hash is invalid")
    return value


def _verify_base(*, allow_trusted_pr_event: bool = True) -> bool:
    head = _git("rev-parse", "HEAD").decode().strip()
    trusted_pr_event = False
    if allow_trusted_pr_event and os.environ.get("GITHUB_EVENT_NAME") == "pull_request":
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        try:
            event = json.loads(Path(event_path).read_text(encoding="utf-8")) if event_path else {}
            pr = event.get("pull_request", {})
            event_head = pr.get("head", {}).get("sha", "")
            trusted_pr_event = (
                pr.get("base", {}).get("ref") == "main"
                and pr.get("base", {}).get("sha") == BASE_MAIN
                and len(event_head) == 40
                and all(character in "0123456789abcdef" for character in event_head)
                and head == os.environ.get("GITHUB_SHA")
            )
        except (OSError, json.JSONDecodeError):
            trusted_pr_event = False
        if not trusted_pr_event:
            raise P44IReviewError("pull_request event is not bound to exact P4.4I base/head")
    else:
        remote_main = _git("rev-parse", "origin/main").decode().strip()
        if remote_main != BASE_MAIN:
            raise P44IReviewError(f"origin/main moved from exact P4.4I base: {remote_main}")
    try:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", BASE_MAIN, "HEAD"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        if not trusted_pr_event:
            raise P44IReviewError("exact P4.4I base is not in current history")
        try:
            _git("cat-file", "-e", BASE_MAIN)
        except P44IReviewError:
            # A depth-1 synthetic PR checkout is accepted only because the exact
            # GitHub event binds both the reviewed base and checked-out head.
            pass
        else:
            raise P44IReviewError("available P4.4I base object is not an ancestor of HEAD")
    return trusted_pr_event


def _verify_before_service_identity(*, trusted_pr_event: bool) -> None:
    try:
        before = _source_identity(SERVICE_PATH, BASE_MAIN)
    except P44IReviewError:
        if not trusted_pr_event:
            raise P44IReviewError("exact P4.4I base service object is unavailable")
        historical = p44h.expected_receipt()["source_identities"].get(SERVICE_PATH)
        if historical != SERVICE_BEFORE:
            raise P44IReviewError("P4.4H historical source identity does not bind P4.4I before bytes")
        return
    if before != SERVICE_BEFORE:
        raise P44IReviewError("P4.4I before-service identity differs from exact main")


def _historical_changed_paths() -> set[str] | None:
    """Return P4.4I's frozen diff when its original Git objects are available.

    Later shallow synthetic PR checkouts may omit the old P4.4I objects. Historical
    validation then relies on the exact immutable receipt and prior-phase identity
    binding; it must never substitute current HEAD for P4.4I's reviewed head.
    """
    for commit in (BASE_MAIN, P44I_REVIEWED_HEAD):
        try:
            _git("cat-file", "-e", f"{commit}^{{commit}}")
        except P44IReviewError:
            return None
    if _source_identity(SERVICE_PATH, BASE_MAIN) != SERVICE_BEFORE:
        raise P44IReviewError("P4.4I historical before-source identity drifted")
    if _source_identity(SERVICE_PATH, P44I_REVIEWED_HEAD) != SERVICE_AFTER:
        raise P44IReviewError("P4.4I historical after-source identity drifted")
    return set(
        _git("diff", "--name-only", f"{BASE_MAIN}...{P44I_REVIEWED_HEAD}")
        .decode()
        .splitlines()
    )


def audit(*, check_live: bool = True) -> dict[str, Any]:
    try:
        trusted_pr_event = _verify_base() if check_live else False
        value = _validate_receipt(_read_canonical(RECEIPT_PATH))

        historical_h = p44h.audit(check_live=False)
        if (
            historical_h != p44h.expected_receipt()
            or historical_h.get("canonical_sha256") != P44H_RECEIPT_SHA256
        ):
            raise P44IReviewError("immutable P4.4H receipt drifted")

        p44g.audit(check_live=check_live)
        if check_live:
            service_identity = _worktree_source_identity(SERVICE_PATH)
            if service_identity != SERVICE_AFTER:
                raise P44IReviewError("Current Shadow supervisor evidence implementation identity drifted")
            _verify_before_service_identity(trusted_pr_event=trusted_pr_event)

            if _git("rev-parse", "HEAD:.github/workflows").decode().strip() != WORKFLOW_TREE_SHA1:
                raise P44IReviewError("workflow tree changed during P4.4I evidence-only correction")
            workflow_paths = _git("ls-tree", "-r", "--name-only", "HEAD", ".github/workflows").decode().splitlines()
            if sum(path.endswith((".yml", ".yaml")) for path in workflow_paths) != WORKFLOW_COUNT:
                raise P44IReviewError("workflow count changed")

            ledger = _read_canonical(evolution.LEDGER_PATH)
            if (
                ledger.get("canonical_sha256") != EVOLUTION_SHA256
                or evolution.canonical_sha256(ledger) != EVOLUTION_SHA256
                or len(ledger.get("transitions", [])) != 6
            ):
                raise P44IReviewError("workflow evolution ledger changed")
            retirement_state = retirement.validate_retirement_history()
            if (
                retirement_state.get("canonical_sha256") != RETIREMENT_SHA256
                or retirement_state.get("current_retired_workflow_count") != RETIRED_COUNT
            ):
                raise P44IReviewError("P4.3 retirement history changed")

            try:
                changed_paths = set(
                    _git("diff", "--name-only", f"{BASE_MAIN}...HEAD").decode().splitlines()
                )
            except P44IReviewError:
                if not trusted_pr_event:
                    raise
            else:
                for line in _git("status", "--porcelain", "--untracked-files=all").decode().splitlines():
                    if len(line) >= 4:
                        path = line[3:]
                        if path not in LOCAL_TEST_DIAGNOSTIC_PATHS:
                            changed_paths.add(path)
                if changed_paths != EXPECTED_CHANGED_PATHS:
                    raise P44IReviewError(
                        "P4.4I changed-file scope differs from the reviewed evidence-only envelope"
                    )
        else:
            changed_paths = _historical_changed_paths()
            if changed_paths is not None and changed_paths != EXPECTED_CHANGED_PATHS:
                raise P44IReviewError(
                    "P4.4I historical changed-file scope differs from its reviewed head"
                )
        return value
    except (OSError, ValueError, AssertionError, json.JSONDecodeError) as exc:
        if isinstance(exc, P44IReviewError):
            raise
        raise P44IReviewError(f"P4.4I audit failed: {exc}") from exc


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
        print(f"P4.4I supervisor failure evidence audit: PASS ({receipt['canonical_sha256']})")
        return 0
    except (P44IReviewError, OSError, ValueError) as exc:
        print(f"P4.4I audit: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
