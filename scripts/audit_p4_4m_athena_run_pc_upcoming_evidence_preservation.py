"""Offline audit for P4.4M canonical Shadow evidence preservation."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import yaml

from domain import current_shadow_fixture_identity_compatibility as identity_compatibility
from domain import current_shadow_fixture_identity_v2 as identity_v2
from domain import current_shadow_sportybet_international_provider_family_bridge as bridge
from domain import current_shadow_sportybet_pc_upcoming_discovery as pc_upcoming
from domain import current_shadow_sportybet_pc_upcoming_reconciliation as runtime
from scripts import audit_p4_2_athena_run_workflow as p42
from scripts import audit_p4_workflow_evolution_ledger as evolution
from scripts import audit_p4_3_workflow_retirement_ledger as retirement


BASE_MAIN_SHA = "6fdd44a2ec6ed36d7a26c719d03cf4772aff3e80"
POLICY_ID = "ATHENA_P4_4M_CANONICAL_SHADOW_PC_UPCOMING_EVIDENCE_PRESERVATION_V1"
WORKFLOW_PATH = ".github/workflows/athena-run.yml"
FIXTURE_PATH = "tests/fixtures/architecture/revised_workflows/athena-run-pre-p4-4m-pc-upcoming-evidence-preservation.yml"
LEDGER_PATH = Path("artifacts/architecture/p4_workflow_evolution_ledger_v1.json")
PREVIOUS_SNAPSHOT_PATH = Path("artifacts/architecture/p4_workflow_evolution_snapshots/p4_4g_current_fotmob_canonical_only_workflow_v1.json")
SNAPSHOT_PATH = Path("artifacts/architecture/p4_workflow_evolution_snapshots/p4_4m_athena_run_pc_upcoming_evidence_preservation_v1.json")
RECEIPT_PATH = Path("artifacts/architecture/p4_4m_athena_run_pc_upcoming_evidence_preservation_v1.json")
PC_ROOT = ".cache/athena-research/current-shadow-sportybet-pc-upcoming-discovery"
PREVIOUS_ROOTS = (
    ".cache/athena-research/current-shadow-sportybet-catalog-fanout",
    ".cache/athena-research/current-shadow-sportybet-upcoming-discovery",
    ".cache/athena-research/sportybet-live-event-quote-evidence",
    ".cache/athena-research/fotmob-data-matches-captures",
)
AFTER_ROOTS = PREVIOUS_ROOTS[:2] + (PC_ROOT,) + PREVIOUS_ROOTS[2:]
TEAM_LABEL_FILES = (
    "domain/current_shadow_sportybet_team_label_compatibility.py",
    "docs/current_shadow_sportybet_reviewed_trailing_space_labels.md",
    "tests/test_current_shadow_fixture_identity_alias_wiring.py",
)


class P44MError(AssertionError):
    """Raised when the evidence-preservation-only contract drifts."""


def _canonical_sha256(value: dict[str, Any]) -> str:
    return evolution.canonical_sha256(value)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _git_bytes(revision: str, path: str) -> bytes:
    result = subprocess.run(["git", "show", f"{revision}:{path}"], capture_output=True)
    if result.returncode:
        raise P44MError(f"cannot read {revision}:{path} from Git")
    return result.stdout


def _workflow_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes().replace(b"\r\n", b"\n")
    except OSError as exc:
        raise P44MError(f"workflow bytes are unavailable: {path}") from exc


def _yaml(raw: bytes) -> dict[str, Any]:
    try:
        value = yaml.load(raw.decode("utf-8"), Loader=yaml.BaseLoader)
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise P44MError("workflow YAML could not be parsed") from exc
    if type(value) is not dict:
        raise P44MError("workflow YAML root must be a mapping")
    return value


def _preservation_step(workflow: dict[str, Any]) -> dict[str, Any]:
    found = []
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []):
            if step.get("id") == "preserve_shadow_evidence":
                found.append(step)
    if len(found) != 1:
        raise P44MError("expected exactly one canonical Shadow evidence-preservation step")
    return found[0]


def _identity(raw: bytes) -> dict[str, str]:
    return evolution.source_identity(raw)


def _receipt() -> dict[str, Any]:
    try:
        value = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise P44MError("P4.4M architecture receipt is unreadable") from exc
    if value.get("canonical_sha256") != _canonical_sha256(value):
        raise P44MError("P4.4M architecture receipt canonical SHA mismatch")
    return value


def check() -> dict[str, Any]:
    receipt = _receipt()
    if receipt.get("policy_id") != POLICY_ID or receipt.get("base_main_sha") != BASE_MAIN_SHA:
        raise P44MError("P4.4M policy or immutable base identity drifted")
    failed = receipt.get("failed_live_proof", {})
    if failed != {
        "run_id": 36229731847,
        "artifact_id": 10901662346,
        "artifact_zip_sha256": "c62c6e345fcf6329f00fa567b71dfbfe07df3d75797e3e74cad05c341b79286d",
        "classification": "POST_PR407_CANONICAL_SHADOW_SUCCESSOR_PROOF_INCOMPLETE:CURRENT_SHADOW_SUPERVISOR_NONZERO_PROVIDER_TEAM_LABEL_WHITESPACE_SHAPE_OUTSIDE_REVIEWED_EVIDENCE",
    }:
        raise P44MError("failed successor-proof evidence identity drifted")
    if receipt.get("failed_artifact_pc_upcoming_manifest_present") is not False or receipt.get("failed_artifact_pc_upcoming_raw_pages_present") is not False:
        raise P44MError("failed artifact evidence-preservation defect was misstated")
    if receipt.get("run_evidence_comment_id") != 5844630119 or receipt.get("offline_diagnosis_comment_id") != 5844716336:
        raise P44MError("failed-run issue evidence comments drifted")

    if pc_upcoming.EVIDENCE_ROOT.as_posix() != PC_ROOT:
        raise P44MError("active pcUpcoming evidence root drifted")
    if (
        pc_upcoming.POLICY_ID != "ATHENA_CURRENT_SHADOW_PC_UPCOMING_GLOBAL_FOOTBALL_SOURCE_V1"
        or pc_upcoming.PINNED_POLICY_SHA256 != "63799058bec00abefb8d9b2ec9ba6dcad0c6e4775a54f17b07c0018e543ec075"
        or pc_upcoming.calculate_policy_sha256() != pc_upcoming.PINNED_POLICY_SHA256
    ):
        raise P44MError("pcUpcoming source contract changed")
    if (
        runtime.POLICY_ID != "ATHENA_CURRENT_SHADOW_PC_UPCOMING_DISCOVERY_RECONCILIATION_V1"
        or runtime.PINNED_POLICY_SHA256 != "e44d8b3476118a094d3e59f885f7456c3aebc677c07d8eeefaa232df5bc6a43e"
        or runtime.calculate_policy_sha256() != runtime.PINNED_POLICY_SHA256
        or bridge.PINNED_POLICY_SHA256 != "7db676111a9be06f63fd207815837d53699d6bf1a98364fc2163046cd1c0a4bb"
        or bridge.calculate_policy_sha256() != bridge.PINNED_POLICY_SHA256
        or identity_v2.REGISTRY_SHA256 != "fc64fb0c2df3cee4f425158c48cfaada6757ba01e1759dd5b976ca899f85421e"
        or identity_v2.registry_sha256() != identity_v2.REGISTRY_SHA256
        or identity_compatibility.EXPECTED_POLICY_SHA256 != "dbef6539dd7c5d1c1589debe8daca9378ea2e0c0bb32acf3315a0d1a005c2b58"
        or identity_compatibility.calculate_policy_sha256() != identity_compatibility.EXPECTED_POLICY_SHA256
    ):
        raise P44MError("active runtime or identity contract changed")
    expected_contract_hashes = {
        "pc_upcoming_source": pc_upcoming.PINNED_POLICY_SHA256,
        "runtime_wrapper": runtime.PINNED_POLICY_SHA256,
        "international_bridge": bridge.PINNED_POLICY_SHA256,
        "v2_registry": identity_v2.REGISTRY_SHA256,
        "identity_compatibility": identity_compatibility.EXPECTED_POLICY_SHA256,
    }
    if receipt.get("runtime_contract_sha256") != {
        key: {"before": value, "after": value} for key, value in expected_contract_hashes.items()
    }:
        raise P44MError("runtime/source identity-contract hashes changed")

    before = _workflow_bytes(Path(FIXTURE_PATH))
    current = _workflow_bytes(Path(WORKFLOW_PATH))
    before_identity = _identity(before)
    after_identity = _identity(current)
    if receipt.get("workflow_before_identity") != before_identity or receipt.get("workflow_after_identity") != after_identity:
        raise P44MError("workflow before/after identity differs from the receipt")
    if subprocess.run(["git", "rev-parse", f"HEAD:{FIXTURE_PATH}"], capture_output=True, text=True).stdout.strip() != before_identity["git_blob_sha1"]:
        raise P44MError("immutable before fixture is not source-controlled at HEAD")
    if subprocess.run(["git", "rev-parse", f"HEAD:{WORKFLOW_PATH}"], capture_output=True, text=True).stdout.strip() != after_identity["git_blob_sha1"]:
        raise P44MError("current workflow identity differs from HEAD")

    before_step = _preservation_step(_yaml(before))
    current_yaml = _yaml(current)
    current_step = _preservation_step(current_yaml)
    before_run = before_step.get("run", "")
    current_run = current_step.get("run", "")
    root_line = f"  '{PC_ROOT}' \\\n"
    if PC_ROOT in before_run or current_run.count(PC_ROOT) != 1 or root_line not in current_run:
        raise P44MError("pcUpcoming source root must be absent before and added exactly once now")
    if current_run.replace(root_line, "", 1) != before_run:
        raise P44MError("workflow change exceeds the single pcUpcoming preservation-loop addition")
    for root in PREVIOUS_ROOTS:
        if before_run.count(root) != 1 or current_run.count(root) != 1:
            raise P44MError(f"existing preserved source root changed or disappeared: {root}")
    if "artifacts/athena-run-workflow/source-evidence" not in current_run:
        raise P44MError("source-evidence destination changed")
    if 'if [ -d "${source_dir}" ]; then' not in current_run or 'cp -a "${source_dir}" "${evidence_root}/"' not in current_run:
        raise P44MError("optional source-copy behavior changed")
    if "identity_path=\"${ATHENA_CURRENT_SHADOW_IDENTITY_STATE_PATH:-}\"" not in current_run:
        raise P44MError("identity-state preservation block disappeared")

    restored = copy.deepcopy(current_yaml)
    _preservation_step(restored)["run"] = before_run
    if restored != _yaml(before):
        raise P44MError("workflow triggers, inputs, permissions, concurrency, timeout, execution, or upload contract changed")
    upload = [
        step for job in current_yaml["jobs"].values() for step in job.get("steps", [])
        if step.get("id") == "upload_evidence"
    ]
    if len(upload) != 1:
        raise P44MError("canonical artifact upload step is missing or ambiguous")
    upload_with = upload[0].get("with", {})
    if (
        upload_with.get("name") != "athena-run-${{ github.run_id }}"
        or upload_with.get("retention-days") != "30"
        or upload_with.get("path") != "artifacts/athena-run-workflow\nartifacts/athena-runs"
    ):
        raise P44MError("canonical artifact name, roots, or retention changed")
    if receipt.get("pre_fix_preservation_list") != list(PREVIOUS_ROOTS) or receipt.get("post_fix_preservation_list") != list(AFTER_ROOTS):
        raise P44MError("receipt preservation-list lineage drifted")

    transition_id = "P44M_ATHENA_RUN_PC_UPCOMING_EVIDENCE_PRESERVATION_V1"
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    previous = json.loads(PREVIOUS_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    if previous.get("canonical_sha256") != "b9ee60aa5cfa63080159cae839ca82b5662fdfbfe70a91055392a1728ed05f7a":
        raise P44MError("immutable six-transition ledger snapshot changed")
    if ledger.get("transitions", [])[:6] != previous.get("transitions") or len(ledger.get("transitions", [])) != 7:
        raise P44MError("P4.4M must append exactly one transition after the immutable six-transition prefix")
    transition = ledger["transitions"][-1]
    if (
        transition.get("transition_id") != transition_id
        or transition.get("phase_id") != "P4.4M"
        or transition.get("workflow_path") != WORKFLOW_PATH
        or transition.get("operation") != "MAINTENANCE_REVISE"
        or transition.get("canonical_family") != "ATHENA_RUN"
        or transition.get("before") != before_identity
        or transition.get("after") != after_identity
        or transition.get("historical_before_fixture") != {"path": FIXTURE_PATH, **before_identity}
        or transition.get("maintenance_contract") != evolution.MAINTENANCE_CONTRACT
    ):
        raise P44MError("P4.4M evolution transition is not the exact reviewed maintenance revision")
    if (
        ledger.get("canonical_sha256") != _canonical_sha256(ledger)
        or snapshot != ledger
        or snapshot.get("canonical_sha256") != _canonical_sha256(snapshot)
        or receipt.get("workflow_evolution_ledger_sha256") != ledger.get("canonical_sha256")
    ):
        raise P44MError("ledger/snapshot/receipt canonical lineage is inconsistent")
    if transition.get("evidence_receipt_path") != RECEIPT_PATH.as_posix() or transition.get("checkpoint_snapshot_path") != SNAPSHOT_PATH.as_posix():
        raise P44MError("P4.4M transition receipt or snapshot path drifted")
    if receipt.get("reviewed_workflow_transition") != {k: v for k, v in transition.items() if k != "evidence_body_sha256"}:
        raise P44MError("architecture receipt does not bind the exact ledger transition")
    if evolution.receipt_evidence_body_sha256(receipt) != transition.get("evidence_body_sha256"):
        raise P44MError("architecture receipt evidence body hash mismatch")
    if ledger.get("current_live_workflow_count") != 38 or ledger.get("current_p4_3_retired_workflow_count") != 3:
        raise P44MError("workflow or retirement count changed")
    if ledger.get("current_workflow_tree_sha1") != receipt.get("workflow_tree_after_sha1"):
        raise P44MError("workflow tree identity differs from the receipt")

    for path, expected in receipt.get("team_label_file_sha256", {}).items():
        before_bytes = _git_bytes(BASE_MAIN_SHA, path).replace(b"\r\n", b"\n")
        after_bytes = _git_bytes("HEAD", path).replace(b"\r\n", b"\n")
        if _sha256(before_bytes) != expected["before"] or _sha256(after_bytes) != expected["after"] or expected["before"] != expected["after"]:
            raise P44MError(f"team-label source or test changed: {path}")

    if receipt.get("team_label_policy_changed") is not False or receipt.get("fixture_identity_policy_changed") is not False or receipt.get("pc_upcoming_source_policy_changed") is not False or receipt.get("runtime_wrapper_policy_changed") is not False:
        raise P44MError("P4.4M may not change team-label or runtime identity policies")
    if any(receipt.get(field) is not False for field in (
        "trigger_surface_changed", "permissions_changed", "concurrency_changed",
        "timeout_changed", "execution_command_changed", "provider_acquisition_authority_changed",
        "model_authority_changed", "pricing_authority_changed", "router_authority_changed",
        "portfolio_authority_changed", "share_code_authority_changed", "login_authority_changed",
        "cookies_authority_changed", "wallet_authority_changed", "staking_authority_changed",
        "bet_authority_changed", "wager_placed",
    )):
        raise P44MError("P4.4M receipt claims an unauthorized behavior or authority change")
    if receipt.get("provider_acquisition_during_implementation") != 0 or receipt.get("workflow_dispatches_during_implementation") != 0 or receipt.get("live_retries") != 0:
        raise P44MError("implementation must remain fully offline")
    if receipt.get("source_review_counter_while_unmerged") != "3/5" or receipt.get("source_review_counter_if_merged") != "4/5":
        raise P44MError("source-review counter lineage drifted")
    if receipt.get("p4_4_complete") is not False or receipt.get("architecture_checkpoint_e_complete") is not False or receipt.get("next_live_proof_authorized") is not False:
        raise P44MError("P4.4M receipt overclaims completion or live authority")

    current = evolution.validate_current_state()
    if current["canonical_sha256"] != ledger["canonical_sha256"]:
        raise P44MError("current workflow evolution validator returned a different ledger")
    retirement_state = retirement.validate_retirement_history()
    if retirement_state.get("current_retired_workflow_count") != 3:
        raise P44MError("P4.3 retirement count no longer equals three")
    return receipt


def main() -> int:
    receipt = check()
    print(receipt["canonical_sha256"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"P4_4M_PC_UPCOMING_EVIDENCE_PRESERVATION_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
