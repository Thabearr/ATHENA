"""Offline proof that P4.4A adds workflow-evolution authority, not a workflow."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

from scripts import audit_p4_workflow_evolution_ledger as evolution
from scripts import audit_p4_3_workflow_retirement_ledger as retirement


POLICY_ID = "ATHENA_P4_4A_WORKFLOW_EVOLUTION_GUARD_V1"
RECEIPT_PATH = Path("artifacts/architecture/p4_4a_workflow_evolution_guard_v1.json")
CHECKPOINT_EVOLUTION_LEDGER_SHA256 = "b3bf449d0d7e04def85b9dbadd66a55c63acfd10348d8211f412da5c9a44b2cb"
FROZEN_SHA = {
    "p4_2_receipt_sha256": ("artifacts/architecture/p4_2_athena_run_workflow_v1.json", "fa575a5bb5f4611eb94564b92dea3e4230b8d429b1660dc3bde3d6c164b836f8"),
    "p4_3a_matrix_sha256": ("artifacts/architecture/p4_3_workflow_capability_matrix_v1.json", retirement.MATRIX_SHA256),
    "p4_3a_receipt_sha256": ("artifacts/architecture/p4_3a_workflow_capability_census_v1.json", retirement.P43A_RECEIPT_SHA256),
    "p4_3b_receipt_sha256": ("artifacts/architecture/p4_3b_current_sportybet_workflow_retirement_v1.json", retirement.P43B_RECEIPT_SHA256),
    "p4_3c_receipt_sha256": ("artifacts/architecture/p4_3c_spent_v1_evidence_workflow_retirement_v1.json", retirement.P43C_RECEIPT_SHA256),
    "p4_3d_receipt_sha256": ("artifacts/architecture/p4_3d_retirement_audit_extensibility_v1.json", evolution.P43D_RECEIPT_SHA256),
    "p4_3_retirement_ledger_sha256": (str(retirement.LEDGER_PATH).replace("\\", "/"), evolution.BASE_RETIREMENT_LEDGER_SHA256),
}


def verify_pure_transition_boundaries() -> None:
    """Exercise future authority with synthetic, in-memory evidence only."""
    history = retirement.validate_retirement_history()
    baseline = evolution.baseline_state(history)
    matrix, _ = retirement.load_baseline()
    frozen = {row["workflow_path"] for row in matrix["workflow_rows"]}
    path = ".github/workflows/athena-ingest.yml"
    before = evolution.source_identity(b"name: synthetic ingest v1\n")
    after = evolution.source_identity(b"name: synthetic ingest v2\n")
    evidence: dict[str, dict[str, Any]] = {}

    def transition(operation: str, identifier: str, old: Any, new: Any, fixture: dict[str, Any] | None = None) -> dict[str, Any]:
        receipt_path = f"artifacts/architecture/{identifier.lower()}_test_only.json"
        item: dict[str, Any] = {
            "transition_id": identifier,
            "operation": operation,
            "workflow_path": path,
            "before": old,
            "after": new,
            "phase_id": "P4.4B_TEST_ONLY",
            "canonical_family": "ATHENA_INGEST",
            "evidence_receipt_path": receipt_path,
            "evidence_body_sha256": "",
        }
        if fixture is not None:
            item["historical_fixture"] = fixture
        receipt: dict[str, Any] = {
            "policy_id": "SYNTHETIC_TEST_ONLY",
            "reviewed_workflow_transition": {key: value for key, value in item.items() if key != "evidence_body_sha256"},
            "workflow_evolution_ledger_sha256": "a" * 64,
        }
        item["evidence_body_sha256"] = evolution.receipt_evidence_body_sha256(receipt)
        receipt["canonical_sha256"] = evolution.canonical_sha256(receipt)
        evidence[receipt_path] = receipt
        return item

    add = transition("ADD", "P44A_SYNTHETIC_ADD", None, before)
    revise = transition("REVISE", "P44A_SYNTHETIC_REVISE", before, after)
    retire = transition("RETIRE", "P44A_SYNTHETIC_RETIRE", after, None, {
        "path": "tests/fixtures/architecture/retired_workflows/athena-ingest.yml", **after,
    })
    apply = lambda items: evolution.apply_transitions(baseline, items, frozen_baseline_paths=frozen, evidence_receipts=evidence)
    if apply([add])[path] != before or apply([add, revise])[path] != after or apply([add, revise, retire]) != baseline:
        raise AssertionError("synthetic reviewed ADD/REVISE/RETIRE did not preserve exact ancestry")
    for unreviewed in (
        [dict(add, workflow_path=".github/workflows/athena-run.yml")],
        [dict(revise, workflow_path=".github/workflows/athena-run.yml")],
        [dict(retire, workflow_path=".github/workflows/athena-run.yml")],
        [dict(add, after=copy.deepcopy(after))],
    ):
        try:
            apply(unreviewed)
        except evolution.WorkflowEvolutionError:
            pass
        else:
            raise AssertionError("unreviewed or frozen-baseline workflow transition was admitted")
    invented = dict(baseline, **{path: before})
    try:
        evolution.validate_derived_tree(baseline, invented)
    except evolution.WorkflowEvolutionError:
        pass
    else:
        raise AssertionError("unregistered athena-ingest.yml was admitted")


def expected_receipt() -> dict[str, Any]:
    history = retirement.validate_retirement_history()
    if history["current_retired_workflow_count"] != 3:
        raise AssertionError("P4.4A checkpoint retirement history changed")
    for key, (path, expected_sha) in FROZEN_SHA.items():
        content = json.loads(Path(path).read_text(encoding="utf-8"))
        if content.get("canonical_sha256") != expected_sha or retirement.canonical_sha256(content) != expected_sha:
            raise AssertionError(f"frozen architecture evidence changed: {path}")
    result: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository_base_main_sha": evolution.BASE_MAIN_SHA,
        "base_workflow_tree_sha1": evolution.BASE_WORKFLOW_TREE_SHA1,
        "workflow_evolution_ledger_path": evolution.LEDGER_PATH.as_posix(),
        "workflow_evolution_ledger_sha256": CHECKPOINT_EVOLUTION_LEDGER_SHA256,
        "workflow_evolution_transition_count": 0,
        "live_workflow_count_before": 37,
        "live_workflow_count_after": 37,
        "workflow_tree_before_sha1": evolution.BASE_WORKFLOW_TREE_SHA1,
        "workflow_tree_after_sha1": evolution.BASE_WORKFLOW_TREE_SHA1,
        "workflow_yaml_changed": False,
        "workflow_added": False,
        "workflow_revised": False,
        "workflow_deleted": False,
        "athena_ingest_workflow_created": False,
        "p4_4_ingest_live_acquisition_enabled": False,
        "p4_4_scheduled_acquisition_enabled": False,
        "provider_acquisition": False,
        "workflow_dispatch_triggered": False,
        "current_shadow_triggered": False,
        "fresh_holdout_triggered": False,
        "p3_0_e1_triggered": False,
        "real_share_code_operation": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "wager_placed": False,
        "model_formula_changed": False,
        "router_formula_changed": False,
        "portfolio_formula_changed": False,
        "provider_semantics_changed": False,
        "authority_semantics_changed": False,
        "p4_4a_exit_gate_satisfied": True,
        "p4_4_overall_complete": False,
        "architecture_checkpoint_e_fully_claimed": False,
        "source_review_counter_while_unmerged": "0/5",
        "source_review_counter_if_merged": "1/5",
    }
    result.update({key: expected_sha for key, (_, expected_sha) in FROZEN_SHA.items()})
    result["canonical_sha256"] = retirement.canonical_sha256(result)
    return result


def check() -> dict[str, Any]:
    verify_pure_transition_boundaries()
    ledger = evolution.validate_current_state()
    if not ledger["transitions"]:
        if ledger["canonical_sha256"] != CHECKPOINT_EVOLUTION_LEDGER_SHA256:
            raise AssertionError("zero-transition P4.4A evolution checkpoint changed")
        if Path(".github/workflows/athena-ingest.yml").exists():
            raise AssertionError("athena-ingest.yml must not exist without a reviewed ADD")
    expected = expected_receipt()
    committed = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    if committed != expected or retirement.canonical_sha256(committed) != committed.get("canonical_sha256"):
        raise AssertionError("P4.4A receipt differs from the reviewed zero-workflow-change proof")
    return committed


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.parse_args()
    print(check()["canonical_sha256"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"P4_4A_WORKFLOW_EVOLUTION_GUARD_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
