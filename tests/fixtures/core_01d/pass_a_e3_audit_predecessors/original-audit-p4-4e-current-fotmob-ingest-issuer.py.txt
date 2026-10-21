"""Offline source/evidence audit for the P4.4E canonical current-FotMob issuer."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from domain.ingest_contracts import canonical_json_bytes, strict_json_loads
from scripts import audit_p4_3_workflow_retirement_ledger as retirement
from scripts import audit_p4_4d_current_fotmob_ingest_compatibility as p44d
from scripts import audit_p4_workflow_evolution_ledger as evolution


BASE_MAIN = "08110c4b415e6c944146efa02225b136af845d67"
P44D_RECEIPT_SHA256 = "4f24db8a93068688192203aab5a4f1e9e0600cd684ee23f53e06a027e9f953e0"
WORKFLOW_TREE_SHA1 = "02e62ab141627885652c304f83dda4274d7245a9"
EVOLUTION_SHA256 = "12abbe541ed807cf96238972f3120ffe9df8130b1dee452740917ea0995d75f7"
P43_RETIREMENT_SHA256 = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
INGEST_PATH = ".github/workflows/athena-ingest.yml"
LEGACY_PATH = ".github/workflows/issue-current-fotmob-reviewed-source.yml"
RECEIPT_PATH = Path("artifacts/architecture/p4_4e_current_fotmob_ingest_issuer_v1.json")
ISSUER_PATH = "services/current_fotmob_ingest_issuer.py"
ISSUER_MODULE = "services.current_fotmob_ingest_issuer"
ISSUER_ENTRYPOINT = "issue_current_reviewed_fotmob_via_canonical_ingest"
EXPECTED_IDENTITIES = {
    INGEST_PATH: {
        "git_blob_sha1": "1c3abb610477862663ccb1b077ff4413be819eda",
        "source_sha256": "9e5137b85a28f8552c4a6bc834c7657a2c690b4203382aa914d5f6854667d8d1",
    },
    LEGACY_PATH: {
        "git_blob_sha1": "11bef2434088de1f8ac96e27e58b5ea07f1f06f4",
        "source_sha256": "8efb3b19d5fa580bca5a995ef9d9fbde84a62c153daea78a579c344f706df157",
    },
    "domain/ingest_contracts.py": {
        "git_blob_sha1": "77f71e1570d7f0b6aed7641b45074ef462997d7d",
        "source_sha256": "e00f6e5c9d1670abae57bed097d89a01f78fcf059fa17a95caec238c4f6fc5fb",
    },
    "services/athena_ingest_service.py": {
        "git_blob_sha1": "08a177bea47b52bed0890d0f43e0f25c5fa14246",
        "source_sha256": "4fe52bb56047b6adfacdee71673d41412669ecf2c61eace636a29b2d567bac5a",
    },
    "scripts/execute_athena_ingest_workflow.py": {
        "git_blob_sha1": "92cf2aab50e8520f3a931f30211510a88c82985e",
        "source_sha256": "1d6e13ae3a823c4a8eac36e3ddf18bc868bcc906a2c289bc1793d7ffa33b6547",
    },
    "scripts/resolve_athena_ingest_workflow_request.py": {
        "git_blob_sha1": "18262b9b8b751e5c4629c5c064ab6dab9666fdca",
        "source_sha256": "8fbb831edd1adcec2594d74f69bbf306d94e3d6dd34f3c6ea1968bc5fcf3eeea",
    },
    "scripts/issue_current_fotmob_reviewed_source.py": {
        "git_blob_sha1": "b50689971ee20cb6800145317a0e9fcb3486f40f",
        "source_sha256": "449e83af1a8e25bf5b054b88682b8559363196ca2d6e1dad87c742949b8d0484",
    },
    "services/current_fotmob_ingest_compatibility.py": {
        "git_blob_sha1": "a1fecd955c7b9e4966dc7248cbae0851414371c5",
        "source_sha256": "04a36fe3d51d9609aa215d3623e0e260a665e817c4b1830a080ed8fc67cb7934",
    },
}
FALSE_AUTHORITY_FIELDS = (
    "fixture_selection_authority", "fixture_intelligence_fact_authority",
    "fixture_intelligence_snapshot_authority",
    "model_feature_authority", "probability_authority", "pricing_authority",
    "routing_authority", "portfolio_authority", "share_code_authority",
    "account_authority", "login_authority", "cookies_authority", "wallet_authority",
    "staking_authority", "wager_authority", "backfill_authority",
)
POLICY_ID = "ATHENA_P4_4E_CURRENT_FOTMOB_INGEST_ISSUER_V1"


class P44EIngestIssuerAuditError(AssertionError):
    """P4.4E authority or historical source identity differs from review."""


def _git(*args: str) -> bytes:
    completed = subprocess.run(["git", *args], capture_output=True)
    if completed.returncode:
        raise P44EIngestIssuerAuditError(
            f"git {' '.join(args)} failed: {completed.stderr.decode('utf-8', 'replace')}"
        )
    return completed.stdout


def _canonical_sha(value: dict[str, Any]) -> str:
    unsigned = {key: item for key, item in value.items() if key != "canonical_sha256"}
    return hashlib.sha256(retirement.canonical_json_bytes(unsigned)).hexdigest()


def expected_receipt() -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository_base_main_sha": BASE_MAIN,
        "p4_4d_receipt_sha256": P44D_RECEIPT_SHA256,
        "workflow_tree_sha1_before": WORKFLOW_TREE_SHA1,
        "workflow_tree_sha1_after": WORKFLOW_TREE_SHA1,
        "workflow_count_before": 38,
        "workflow_count_after": 38,
        "workflow_evolution_ledger_sha256": EVOLUTION_SHA256,
        "workflow_evolution_transition_count_before": 4,
        "workflow_evolution_transition_count_after": 4,
        "p4_3_retirement_ledger_sha256": P43_RETIREMENT_SHA256,
        "canonical_ingest_workflow_identity": EXPECTED_IDENTITIES[INGEST_PATH],
        "legacy_current_reviewed_workflow_identity": EXPECTED_IDENTITIES[LEGACY_PATH],
        "compatibility_scope": {
            "provider": "fotmob", "date_count": 1, "timezone": "UTC", "ccode3": "NGA",
        },
        "canonical_artifact_root": "artifacts/athena-ingest-workflow",
        "issuer_date_count_exact": 1,
        "successful_path_canonical_provider_request_count": 1,
        "provider_request_count_by_adapter": 0,
        "acquisition_retry_count": 0,
        "published_artifact_overwrite_allowed": False,
        "source_bytes_copied_by_adapter": False,
        "source_bytes_rewritten_by_adapter": False,
        "pr243_policy_bounds_overridable": False,
        "new_seam_has_cli": False,
        "new_seam_workflow_caller_count": 0,
        "exact_main_lineage_required": True,
        "shared_canonical_ingest_service_used": True,
        "p4_4d_compatibility_adapter_used": True,
        "direct_provider_transport_duplicated_by_issuer": False,
        "workflow_yaml_modified": False,
        "canonical_ingest_request_schema_modified": False,
        "canonical_ingest_runtime_modified": False,
        "legacy_issuer_modified": False,
        "live_caller_migrated": False,
        "live_legacy_workflow_activated_on_new_seam": False,
        "no_supported_live_caller_references_new_issuer": True,
        "new_issuer_live_caller_count": 0,
        "provider_acquisition_during_pr": False,
        "provider_request_count_during_pr": 0,
        "workflow_dispatch_during_pr": False,
        "workflow_activation_during_pr": False,
        "legacy_workflow_retirement_authorized": False,
        "new_provider_family_authorized": False,
        "non_ingest_authority_expansion": False,
        "full_legacy_workflow_equivalence_claimed": False,
        "noncanonical_timezone_or_ccode3_supported": False,
        "fixture_selection_authority": False,
        "fixture_intelligence_fact_authority": False,
        "fixture_intelligence_snapshot_authority": False,
        "model_feature_authority": False,
        "probability_authority": False,
        "pricing_authority": False,
        "routing_authority": False,
        "portfolio_authority": False,
        "share_code_authority": False,
        "account_authority": False,
        "login_authority": False,
        "cookies_authority": False,
        "wallet_authority": False,
        "staking_authority": False,
        "wager_authority": False,
        "backfill_authority": False,
        "p4_4_overall_complete": False,
        "architecture_checkpoint_e_complete": False,
        "source_review_counter_while_unmerged": "1/5",
        "source_review_counter_if_merged": "2/5",
    }
    value["canonical_sha256"] = _canonical_sha(value)
    return value


def validate_receipt(value: Any, *, check_live: bool = True) -> dict[str, Any]:
    expected = expected_receipt()
    if type(value) is not dict or set(value) != set(expected):
        raise P44EIngestIssuerAuditError("P4.4E receipt fields differ from exact schema")
    if value != expected:
        raise P44EIngestIssuerAuditError("P4.4E receipt differs from reviewed semantics")
    if value["canonical_sha256"] != _canonical_sha(value):
        raise P44EIngestIssuerAuditError("P4.4E receipt self-hash mismatch")
    if check_live:
        _validate_live_state()
    return value


def _source_identity(path: str) -> dict[str, str]:
    raw = _git("show", f"HEAD:{path}")
    return {
        "git_blob_sha1": hashlib.sha1(
            b"blob " + str(len(raw)).encode("ascii") + bytes([0]) + raw
        ).hexdigest(),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
    }


def _require_exact_base_ancestry() -> None:
    merge_base = subprocess.run(
        ["git", "merge-base", "HEAD", BASE_MAIN], capture_output=True
    )
    if merge_base.returncode == 0:
        based_on_exact_main = merge_base.stdout.decode("ascii").strip() == BASE_MAIN
    else:
        # Hosted PR checkouts may contain only the synthetic merge commit. Its
        # parent or the trusted pull_request event must bind this P4.4E base,
        # not the older P4.4D branch base.
        parents = _git("show", "-s", "--format=%P", "HEAD").decode("ascii").split()
        based_on_exact_main = BASE_MAIN in parents
        if not based_on_exact_main:
            event_path = os.environ.get("GITHUB_EVENT_PATH")
            if os.environ.get("GITHUB_EVENT_NAME") == "pull_request" and event_path:
                try:
                    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
                    pull_request = event.get("pull_request")
                    base = pull_request.get("base") if isinstance(pull_request, dict) else None
                    head = pull_request.get("head") if isinstance(pull_request, dict) else None
                    base_sha = base.get("sha") if isinstance(base, dict) else None
                    base_ref = base.get("ref") if isinstance(base, dict) else None
                    head_sha = head.get("sha") if isinstance(head, dict) else None
                    current_sha = _git("rev-parse", "HEAD").decode("ascii").strip()
                    github_sha = os.environ.get("GITHUB_SHA")
                    based_on_exact_main = (
                        base_sha == BASE_MAIN
                        and base_ref == "main"
                        and isinstance(head_sha, str)
                        and len(head_sha) == 40
                        and all(char in "0123456789abcdef" for char in head_sha)
                        and current_sha in {head_sha, github_sha}
                    )
                except (OSError, json.JSONDecodeError, P44EIngestIssuerAuditError):
                    based_on_exact_main = False
    if not based_on_exact_main:
        raise P44EIngestIssuerAuditError("P4.4E branch is not based on exact reviewed main")


def _workflow_count_at_head() -> int:
    paths = _git("ls-tree", "-r", "--name-only", "HEAD", ".github/workflows").decode(
        "utf-8"
    ).splitlines()
    return sum(path.endswith((".yml", ".yaml")) for path in paths)


def _ensure_no_live_caller() -> None:
    needles = (ISSUER_MODULE, ISSUER_ENTRYPOINT)
    excluded = {ISSUER_PATH, "scripts/audit_p4_4e_current_fotmob_ingest_issuer.py"}
    try:
        paths = _git("ls-files", "-z", "--", "*.py", "*.yml", "*.yaml").decode("utf-8").split("\0")
    except UnicodeError as exc:
        raise P44EIngestIssuerAuditError("tracked production source list is malformed") from exc
    for relative in paths:
        if not relative or relative.startswith("tests/") or relative in excluded:
            continue
        path = Path(relative)
        if any(part in {".venv", "venv", "site-packages", "__pycache__"} for part in path.parts):
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise P44EIngestIssuerAuditError(
                f"production source could not be inspected: {relative}"
            ) from exc
        if any(needle in source for needle in needles):
            raise P44EIngestIssuerAuditError(
                f"P4.4E issuer has an active workflow/caller reference: {relative}"
            )


def _validate_issuer_composition() -> None:
    try:
        tree = ast.parse(Path(ISSUER_PATH).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeError) as exc:
        raise P44EIngestIssuerAuditError("P4.4E issuer module cannot be parsed") from exc
    imported: set[str] = set()
    called: set[str] = set()
    referenced: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.update(alias.name for alias in node.names)
            referenced.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
            referenced.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called.add(node.func.id)
    forbidden = {"fetch_fotmob_data_matches", "write_data_matches_capture_directory"}
    if referenced & forbidden or called & forbidden:
        raise P44EIngestIssuerAuditError("P4.4E duplicates provider transport ownership")
    reviewed_calls = {
        "execute_ingest_request",
        "project_current_reviewed_fotmob_source_from_ingest_artifact",
    }
    if not reviewed_calls <= imported or not reviewed_calls <= called:
        raise P44EIngestIssuerAuditError("P4.4E does not compose the reviewed ingest/projection services")


def _validate_live_state() -> None:
    try:
        _require_exact_base_ancestry()
        p44d.audit(check_live=False)
    except (AssertionError, OSError, ValueError) as exc:
        raise P44EIngestIssuerAuditError(
            f"P4.4D historical boundary or exact base ancestry failed: {exc}"
        ) from exc

    if _git("rev-parse", "HEAD:.github/workflows").decode("ascii").strip() != WORKFLOW_TREE_SHA1:
        raise P44EIngestIssuerAuditError("protected workflow tree changed")
    if _workflow_count_at_head() != 38:
        raise P44EIngestIssuerAuditError("workflow count differs from P4.4D")
    ledger = json.loads(_git("show", f"HEAD:{evolution.LEDGER_PATH.as_posix()}"))
    if (
        ledger.get("canonical_sha256") != EVOLUTION_SHA256
        or evolution.canonical_sha256(ledger) != EVOLUTION_SHA256
        or len(ledger.get("transitions", [])) != 4
    ):
        raise P44EIngestIssuerAuditError("workflow evolution history changed")
    retirement_ledger = retirement.validate_retirement_history()
    if (
        retirement_ledger.get("canonical_sha256") != P43_RETIREMENT_SHA256
        or retirement_ledger.get("current_retired_workflow_count") != 3
    ):
        raise P44EIngestIssuerAuditError("P4.3 retirement history changed")

    for path, identity in EXPECTED_IDENTITIES.items():
        if _source_identity(path) != identity:
            raise P44EIngestIssuerAuditError(f"protected source identity changed: {path}")
        if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", path]).returncode != 0:
            raise P44EIngestIssuerAuditError(f"protected source has an unstaged change: {path}")
        if subprocess.run(["git", "diff", "--cached", "--quiet", "HEAD", "--", path]).returncode != 0:
            raise P44EIngestIssuerAuditError(f"protected source has a staged change: {path}")
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", ".github/workflows"]).returncode != 0:
        raise P44EIngestIssuerAuditError("workflow YAML has an unstaged change")
    if subprocess.run(["git", "diff", "--cached", "--quiet", "HEAD", "--", ".github/workflows"]).returncode != 0:
        raise P44EIngestIssuerAuditError("workflow YAML has a staged change")
    _validate_issuer_composition()
    _ensure_no_live_caller()


def audit(path: Path = RECEIPT_PATH, *, check_live: bool = True) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = strict_json_loads(raw)
        if canonical_json_bytes(value) != raw:
            raise P44EIngestIssuerAuditError("P4.4E architecture receipt is not canonical JSON")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        if isinstance(exc, P44EIngestIssuerAuditError):
            raise
        raise P44EIngestIssuerAuditError("P4.4E architecture receipt cannot be loaded") from exc
    return validate_receipt(value, check_live=check_live)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        audit()
        print("P4.4E canonical current-FotMob issuer audit: PASS")
        return 0
    except (P44EIngestIssuerAuditError, AssertionError, OSError, ValueError) as exc:
        print(f"P4.4E canonical current-FotMob issuer audit: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
