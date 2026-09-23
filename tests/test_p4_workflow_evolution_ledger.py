"""Fail-closed, offline tests for post-P4.3 workflow evolution authority."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import audit_p4_workflow_evolution_ledger as audit
from scripts import audit_p4_3_workflow_retirement_ledger as retirement


NEW_PATH = ".github/workflows/athena-ingest.yml"
EVIDENCE_PATH = "artifacts/architecture/p4_4b_ingest_evidence_v1.json"
FIXTURE = "tests/fixtures/architecture/retired_workflows/athena-ingest.yml"
CHECKPOINT_PATH = "artifacts/architecture/p4_workflow_evolution_snapshots/p4_4b_1.json"
P44A_SNAPSHOT_PATH = Path("artifacts/architecture/p4_workflow_evolution_snapshots/p4_4a_workflow_evolution_ledger_v1.json")


def _baseline() -> tuple[dict, set[str]]:
    history = retirement.validate_retirement_history()
    matrix, _ = retirement.load_baseline()
    return audit.baseline_state(history), {row["workflow_path"] for row in matrix["workflow_rows"]}


def _transition(operation: str, *, path: str = NEW_PATH, before=None, after=None, identifier="P44B_1", fixture=None):
    transition = {
        "transition_id": identifier,
        "operation": operation,
        "workflow_path": path,
        "before": before,
        "after": after,
        "phase_id": "P4.4B",
        "canonical_family": "ATHENA_INGEST",
        "evidence_receipt_path": EVIDENCE_PATH,
        "checkpoint_snapshot_path": CHECKPOINT_PATH,
        "evidence_body_sha256": "",
    }
    if fixture is not None:
        transition["historical_fixture"] = fixture
    receipt = {
        "schema_version": 1,
        "policy_id": "SYNTHETIC_TEST_ONLY",
        "reviewed_workflow_transition": {key: value for key, value in transition.items() if key != "evidence_body_sha256"},
        "workflow_evolution_ledger_sha256": "a" * 64,
    }
    transition["evidence_body_sha256"] = audit.receipt_evidence_body_sha256(receipt)
    receipt["canonical_sha256"] = audit.canonical_sha256(receipt)
    return transition, receipt


def _evaluate(transitions, receipts):
    baseline, frozen = _baseline()
    matrix, _ = retirement.load_baseline()
    families = {row["workflow_path"]: row["successor_family"] for row in matrix["workflow_rows"]}
    fixtures = {}
    clean_transitions = copy.deepcopy(transitions)
    for transition in clean_transitions:
        raw = transition.pop("_test_fixture_bytes", None)
        fixture = transition.get("historical_before_fixture")
        if transition.get("operation") == "MAINTENANCE_REVISE" and raw is not None and isinstance(fixture, dict):
            fixtures[fixture.get("path")] = raw
    return audit.apply_transitions(
        baseline,
        clean_transitions,
        frozen_baseline_paths=frozen,
        evidence_receipts=receipts,
        baseline_families=families,
        historical_before_fixture_bytes=fixtures,
    )


def _maintenance_transition(
    path: str,
    *,
    before_raw: bytes,
    after_raw: bytes,
    identifier: str,
    fixture_path: str,
    evidence_path: str | None = None,
    checkpoint_path: str | None = None,
    family: str | None = None,
    contract: dict | None = None,
):
    matrix, _ = retirement.load_baseline()
    row = next((item for item in matrix["workflow_rows"] if item["workflow_path"] == path), None)
    selected_family = family if family is not None else row["successor_family"] if row else "ATHENA_INGEST"
    transition, receipt = _transition(
        "MAINTENANCE_REVISE",
        path=path,
        before=audit.source_identity(before_raw),
        after=audit.source_identity(after_raw),
        identifier=identifier,
    )
    transition["canonical_family"] = selected_family
    transition["phase_id"] = "P4.4A1"
    transition["historical_before_fixture"] = {
        "path": fixture_path,
        **audit.source_identity(before_raw),
    }
    transition["maintenance_contract"] = copy.deepcopy(
        audit.MAINTENANCE_CONTRACT if contract is None else contract
    )
    transition["_test_fixture_bytes"] = before_raw
    if evidence_path is not None:
        transition["evidence_receipt_path"] = evidence_path
    if checkpoint_path is not None:
        transition["checkpoint_snapshot_path"] = checkpoint_path
    _refresh_maintenance_receipt(transition, receipt)
    return transition, receipt


def _refresh_maintenance_receipt(transition, receipt):
    receipt["reviewed_workflow_transition"] = {
        key: value for key, value in transition.items()
        if key not in {"evidence_body_sha256", "_test_fixture_bytes"}
    }
    transition["evidence_body_sha256"] = audit.receipt_evidence_body_sha256(receipt)
    receipt["canonical_sha256"] = audit.canonical_sha256(receipt)


def _phase_checkpoint(transition, receipt):
    """Build a deterministic test-only prefix snapshot and its final receipt backlink."""
    snapshot = json.loads(P44A_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    snapshot["transitions"] = [transition]
    snapshot["current_live_workflow_count"] = 38 if transition["operation"] == "ADD" else 37
    snapshot["current_workflow_tree_sha1"] = "1" * 40
    snapshot["canonical_sha256"] = audit.canonical_sha256(snapshot)
    receipt["workflow_evolution_ledger_sha256"] = snapshot["canonical_sha256"]
    receipt["canonical_sha256"] = audit.canonical_sha256(receipt)
    return snapshot


def _synthetic_p43_retirement_extension():
    checkpoint = retirement._load_p43c_ledger_snapshot()
    current = copy.deepcopy(checkpoint)
    row = next(
        item for item in retirement.load_baseline()[0]["workflow_rows"]
        if item["workflow_path"] == ".github/workflows/athena-draft-ready-bridge.yml"
    )
    added = {
        "workflow_path": row["workflow_path"],
        "git_blob_sha1": row["git_blob_sha1"],
        "source_sha256": row["source_sha256"],
        "fixture_path": "tests/fixtures/architecture/retired_workflows/synthetic-p43-test.yml",
        "retirement_phase": "P4.3_TEST_ONLY",
        "retirement_receipt_path": "artifacts/architecture/p4_3_test_only_retirement.json",
        "successor_workflow_path": ".github/workflows/athena-run.yml",
    }
    current["retirements"] = sorted([*current["retirements"], added], key=lambda item: item["workflow_path"])
    current["retired_workflow_paths"] = sorted([*current["retired_workflow_paths"], row["workflow_path"]])
    current["current_retired_workflow_count"] = 4
    current["current_live_workflow_count"] = 36
    current["canonical_sha256"] = retirement.canonical_sha256(current)
    return checkpoint, current, added


def _synthetic_evolution_after_p43_extension(current_p43):
    evolution = json.loads(P44A_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    evolution["current_p4_3_retired_workflow_count"] = 4
    evolution["current_p4_3_retirement_ledger_sha256"] = current_p43["canonical_sha256"]
    evolution["current_p4_3_retirement_ledger_snapshot_path"] = "artifacts/architecture/p4_3_retirement_ledger_snapshots/p4_3d_synthetic_test.json"
    evolution["current_p4_3_retirement_ledger_snapshot_sha256"] = current_p43["canonical_sha256"]
    evolution["current_live_workflow_count"] = 36
    evolution["current_workflow_tree_sha1"] = "2" * 40
    evolution["canonical_sha256"] = audit.canonical_sha256(evolution)
    return evolution


def test_current_ledger_keeps_37_workflows_after_reviewed_maintenance() -> None:
    ledger = audit.validate_current_state()
    assert [item["transition_id"] for item in ledger["transitions"]] == [
        "P44A1_FH_VISIBILITY_BRIDGE_V1",
        "P44A1_FH_VISIBILITY_RELEASE_RECEIPTS_V1",
    ]
    assert ledger["current_live_workflow_count"] == 37
    assert ledger["current_workflow_tree_sha1"] == "a40328bdc4d73de7c2bc152b8fb810dcbb439f8c"
    assert ledger["canonical_sha256"] == audit.canonical_sha256(ledger)
    assert not Path(NEW_PATH).exists()
    assert retirement.validate_retirement_history()["canonical_sha256"] == audit.BASE_RETIREMENT_LEDGER_SHA256


def test_unreviewed_add_is_rejected_but_exact_reviewed_add_is_accepted() -> None:
    baseline, _ = _baseline()
    invented = dict(baseline)
    new_identity = audit.source_identity(b"name: synthetic ingest\n")
    invented[NEW_PATH] = new_identity
    with pytest.raises(audit.WorkflowEvolutionError, match="live workflow set"):
        audit.validate_current_state(workflow_paths=[*baseline, NEW_PATH])
    with pytest.raises(audit.WorkflowEvolutionError, match="live workflow set"):
        audit.validate_derived_tree(baseline, invented)
    add, receipt = _transition("ADD", after=new_identity)
    derived = _evaluate([add], {EVIDENCE_PATH: receipt})
    assert derived == invented
    audit.validate_derived_tree(derived, invented)
    assert len(derived) == 38


def test_add_identity_and_reviewed_receipt_are_required() -> None:
    identity = audit.source_identity(b"name: synthetic ingest\n")
    add, receipt = _transition("ADD", after=identity)
    with pytest.raises(audit.WorkflowEvolutionError, match="receipt is required"):
        _evaluate([add], {})
    bad = copy.deepcopy(add)
    bad["after"]["source_sha256"] = "b" * 64
    with pytest.raises(audit.WorkflowEvolutionError, match="exact operation"):
        _evaluate([bad], {EVIDENCE_PATH: receipt})
    with pytest.raises(audit.WorkflowEvolutionError, match="identity"):
        audit.validate_derived_tree({NEW_PATH: identity}, {NEW_PATH: audit.source_identity(b"drift")})
    missing_checkpoint = copy.deepcopy(add)
    missing_checkpoint.pop("checkpoint_snapshot_path")
    with pytest.raises(audit.WorkflowEvolutionError, match="schema/operation"):
        _evaluate([missing_checkpoint], {EVIDENCE_PATH: receipt})


def test_add_existing_baseline_or_duplicate_identifier_fails() -> None:
    baseline, _ = _baseline()
    old_path = ".github/workflows/athena-run.yml"
    add, receipt = _transition("ADD", path=old_path, after=baseline[old_path])
    with pytest.raises(audit.WorkflowEvolutionError, match="already existed or is frozen"):
        _evaluate([add], {EVIDENCE_PATH: receipt})
    first, receipt = _transition("ADD", after=audit.source_identity(b"one"))
    second, _ = _transition("ADD", after=audit.source_identity(b"two"))
    with pytest.raises(audit.WorkflowEvolutionError, match="duplicate"):
        _evaluate([first, second], {EVIDENCE_PATH: receipt})


def test_revise_chains_only_a_ledger_added_path() -> None:
    before = audit.source_identity(b"one")
    after = audit.source_identity(b"two")
    add, add_receipt = _transition("ADD", after=before)
    revise, revise_receipt = _transition("REVISE", before=before, after=after, identifier="P44B_2")
    revise["evidence_receipt_path"] = "artifacts/architecture/p4_4c_revision_evidence_v1.json"
    revise["checkpoint_snapshot_path"] = "artifacts/architecture/p4_workflow_evolution_snapshots/p4_4c_revision.json"
    revise_receipt["reviewed_workflow_transition"]["evidence_receipt_path"] = revise["evidence_receipt_path"]
    revise_receipt["reviewed_workflow_transition"]["checkpoint_snapshot_path"] = revise["checkpoint_snapshot_path"]
    revise["evidence_body_sha256"] = audit.receipt_evidence_body_sha256(revise_receipt)
    revise_receipt["canonical_sha256"] = audit.canonical_sha256(revise_receipt)
    receipts = {EVIDENCE_PATH: add_receipt, revise["evidence_receipt_path"]: revise_receipt}
    assert _evaluate([add, revise], receipts)[NEW_PATH] == after
    with pytest.raises(audit.WorkflowEvolutionError, match="live ledger-added"):
        _evaluate([revise, add], receipts)
    wrong = copy.deepcopy(revise)
    wrong["before"] = audit.source_identity(b"wrong")
    with pytest.raises(audit.WorkflowEvolutionError, match="exact operation"):
        _evaluate([add, wrong], receipts)
    with pytest.raises(audit.WorkflowEvolutionError, match="live ledger-added"):
        _evaluate([revise], receipts)


def test_frozen_survivor_cannot_be_revised_or_retired() -> None:
    baseline, _ = _baseline()
    path = ".github/workflows/athena-run.yml"
    revise, receipt = _transition("REVISE", path=path, before=baseline[path], after=audit.source_identity(b"changed"))
    with pytest.raises(audit.WorkflowEvolutionError, match="live ledger-added"):
        _evaluate([revise], {EVIDENCE_PATH: receipt})
    retire, receipt = _transition("RETIRE", path=path, before=baseline[path], fixture={"path": FIXTURE, **baseline[path]})
    with pytest.raises(audit.WorkflowEvolutionError, match="live ledger-added"):
        _evaluate([retire], {EVIDENCE_PATH: receipt})


def test_maintenance_revise_preserves_a_p43a_path_and_zero_count_delta() -> None:
    path = ".github/workflows/athena-run.yml"
    baseline, frozen = _baseline()
    before_raw = retirement.resolve_reviewed_workflow_source(path)
    after_raw = before_raw + b"\n# synthetic reviewed maintenance\n"
    transition, receipt = _maintenance_transition(
        path,
        before_raw=before_raw,
        after_raw=after_raw,
        identifier="P44A1_ATHENA_RUN_1",
        fixture_path="tests/fixtures/architecture/revised_workflows/athena-run-before-1.yml",
    )
    derived = _evaluate([transition], {EVIDENCE_PATH: receipt})
    assert derived[path] == audit.source_identity(after_raw)
    assert len(derived) == len(baseline) == 37
    assert set(derived) == set(baseline)
    assert path in frozen


def test_maintenance_revise_admission_is_limited_to_retained_p43a_paths() -> None:
    baseline, _ = _baseline()
    p43a_path = ".github/workflows/athena-run.yml"
    before_raw = retirement.resolve_reviewed_workflow_source(p43a_path)
    after_raw = before_raw + b"\n# reviewed maintenance\n"
    transition, receipt = _maintenance_transition(
        p43a_path,
        before_raw=before_raw,
        after_raw=after_raw,
        identifier="P44A1_REVISE_GUARDS",
        fixture_path="tests/fixtures/architecture/revised_workflows/athena-run-guard-before.yml",
    )
    ordinary, ordinary_receipt = _transition(
        "REVISE",
        path=p43a_path,
        before=baseline[p43a_path],
        after=audit.source_identity(after_raw),
        identifier="P44A1_ORDINARY_REVISE",
    )
    with pytest.raises(audit.WorkflowEvolutionError, match="live ledger-added"):
        _evaluate([ordinary], {EVIDENCE_PATH: ordinary_receipt})
    retire, retire_receipt = _transition(
        "RETIRE",
        path=p43a_path,
        before=baseline[p43a_path],
        fixture={"path": FIXTURE, **baseline[p43a_path]},
        identifier="P44A1_BASELINE_RETIRE",
    )
    with pytest.raises(audit.WorkflowEvolutionError, match="live ledger-added"):
        _evaluate([retire], {EVIDENCE_PATH: retire_receipt})
    add, add_receipt = _transition("ADD", path=p43a_path, after=baseline[p43a_path], identifier="P44A1_BASELINE_ADD")
    with pytest.raises(audit.WorkflowEvolutionError, match="already existed or is frozen"):
        _evaluate([add], {EVIDENCE_PATH: add_receipt})

    non_baseline, non_baseline_receipt = _maintenance_transition(
        NEW_PATH,
        before_raw=b"before\n",
        after_raw=b"after\n",
        identifier="P44A1_NON_BASELINE",
        fixture_path="tests/fixtures/architecture/revised_workflows/non-baseline.yml",
    )
    with pytest.raises(audit.WorkflowEvolutionError, match="not a P4.3A baseline"):
        _evaluate([non_baseline], {EVIDENCE_PATH: non_baseline_receipt})

    retired_path = ".github/workflows/current-sportybet-accumulator.yml"
    retired_row = next(r for r in retirement.load_baseline()[0]["workflow_rows"] if r["workflow_path"] == retired_path)
    retired, retired_receipt = _maintenance_transition(
        retired_path,
        before_raw=b"old retired workflow\n",
        after_raw=b"changed retired workflow\n",
        identifier="P44A1_RETIRED",
        fixture_path="tests/fixtures/architecture/revised_workflows/retired-target.yml",
    )
    with pytest.raises(audit.WorkflowEvolutionError, match="live retained P4.3A survivor"):
        _evaluate([retired], {EVIDENCE_PATH: retired_receipt})
    assert retired_row["git_blob_sha1"] != retired["before"]["git_blob_sha1"]


def test_maintenance_revise_requires_exact_before_after_and_fixture_identity() -> None:
    path = ".github/workflows/athena-run.yml"
    before_raw = retirement.resolve_reviewed_workflow_source(path)
    after_raw = before_raw + b"\n# new reviewed bytes\n"

    wrong_before, wrong_before_receipt = _maintenance_transition(
        path,
        before_raw=b"wrong before\n",
        after_raw=after_raw,
        identifier="P44A1_WRONG_BEFORE",
        fixture_path="tests/fixtures/architecture/revised_workflows/wrong-before.yml",
    )
    with pytest.raises(audit.WorkflowEvolutionError, match="before identity does not chain"):
        _evaluate([wrong_before], {EVIDENCE_PATH: wrong_before_receipt})

    unchanged, unchanged_receipt = _maintenance_transition(
        path,
        before_raw=before_raw,
        after_raw=before_raw,
        identifier="P44A1_UNCHANGED",
        fixture_path="tests/fixtures/architecture/revised_workflows/unchanged.yml",
    )
    with pytest.raises(audit.WorkflowEvolutionError, match="after identity did not change"):
        _evaluate([unchanged], {EVIDENCE_PATH: unchanged_receipt})

    no_fixture, no_fixture_receipt = _maintenance_transition(
        path,
        before_raw=before_raw,
        after_raw=after_raw,
        identifier="P44A1_NO_FIXTURE",
        fixture_path="tests/fixtures/architecture/revised_workflows/no-fixture.yml",
    )
    no_fixture.pop("historical_before_fixture")
    _refresh_maintenance_receipt(no_fixture, no_fixture_receipt)
    with pytest.raises(audit.WorkflowEvolutionError, match="schema/operation"):
        _evaluate([no_fixture], {EVIDENCE_PATH: no_fixture_receipt})

    no_contract, no_contract_receipt = _maintenance_transition(
        path,
        before_raw=before_raw,
        after_raw=after_raw,
        identifier="P44A1_NO_CONTRACT",
        fixture_path="tests/fixtures/architecture/revised_workflows/no-contract.yml",
    )
    no_contract.pop("maintenance_contract")
    _refresh_maintenance_receipt(no_contract, no_contract_receipt)
    with pytest.raises(audit.WorkflowEvolutionError, match="schema/operation"):
        _evaluate([no_contract], {EVIDENCE_PATH: no_contract_receipt})

    wrong_blob, wrong_blob_receipt = _maintenance_transition(
        path,
        before_raw=before_raw,
        after_raw=after_raw,
        identifier="P44A1_WRONG_FIXTURE_BLOB",
        fixture_path="tests/fixtures/architecture/revised_workflows/wrong-blob.yml",
    )
    wrong_blob["historical_before_fixture"]["git_blob_sha1"] = "0" * 40
    _refresh_maintenance_receipt(wrong_blob, wrong_blob_receipt)
    with pytest.raises(audit.WorkflowEvolutionError, match="fixture differs from before"):
        _evaluate([wrong_blob], {EVIDENCE_PATH: wrong_blob_receipt})

    wrong_sha, wrong_sha_receipt = _maintenance_transition(
        path,
        before_raw=before_raw,
        after_raw=after_raw,
        identifier="P44A1_WRONG_FIXTURE_SHA",
        fixture_path="tests/fixtures/architecture/revised_workflows/wrong-sha.yml",
    )
    wrong_sha["historical_before_fixture"]["source_sha256"] = "0" * 64
    _refresh_maintenance_receipt(wrong_sha, wrong_sha_receipt)
    with pytest.raises(audit.WorkflowEvolutionError, match="fixture differs from before"):
        _evaluate([wrong_sha], {EVIDENCE_PATH: wrong_sha_receipt})

    outside, outside_receipt = _maintenance_transition(
        path,
        before_raw=before_raw,
        after_raw=after_raw,
        identifier="P44A1_OUTSIDE_FIXTURE",
        fixture_path="tests/fixtures/architecture/retired_workflows/athena-run.yml",
    )
    _refresh_maintenance_receipt(outside, outside_receipt)
    with pytest.raises(audit.WorkflowEvolutionError, match="fixture path is invalid"):
        _evaluate([outside], {EVIDENCE_PATH: outside_receipt})

    bad_bytes, bad_bytes_receipt = _maintenance_transition(
        path,
        before_raw=before_raw,
        after_raw=after_raw,
        identifier="P44A1_FIXTURE_BYTES",
        fixture_path="tests/fixtures/architecture/revised_workflows/fixture-bytes.yml",
    )
    bad_bytes["_test_fixture_bytes"] = before_raw + b"drift"
    with pytest.raises(audit.WorkflowEvolutionError, match="fixture bytes drifted"):
        _evaluate([bad_bytes], {EVIDENCE_PATH: bad_bytes_receipt})


@pytest.mark.parametrize(
    ("contract_change", "message"),
    [
        ({"policy_id": "OTHER"}, "grants or misstates"),
        ({"baseline_origin": "P4_3D"}, "grants or misstates"),
        ({"permissions_changed": True}, "grants or misstates"),
        ({"provider_acquisition_authority_changed": True}, "grants or misstates"),
        ({"model_authority_changed": True}, "grants or misstates"),
        ({"pricing_authority_changed": True}, "grants or misstates"),
        ({"selection_authority_changed": True}, "grants or misstates"),
        ({"betting_authority_changed": True}, "grants or misstates"),
        ({"path_presence_changed": True}, "grants or misstates"),
        ({"retirement_authority_granted": True}, "grants or misstates"),
        ({"trigger_surface_changed": True}, "grants or misstates"),
        ({"concurrency_changed": True}, "grants or misstates"),
        ({"unexpected": False}, "exact v1 fields"),
    ],
)
def test_maintenance_contract_is_exact_and_authority_neutral(contract_change, message) -> None:
    path = ".github/workflows/athena-run.yml"
    before_raw = retirement.resolve_reviewed_workflow_source(path)
    after_raw = before_raw + b"\n# maintenance contract test\n"
    contract = copy.deepcopy(audit.MAINTENANCE_CONTRACT)
    contract.update(contract_change)
    transition, receipt = _maintenance_transition(
        path,
        before_raw=before_raw,
        after_raw=after_raw,
        identifier="P44A1_CONTRACT",
        fixture_path="tests/fixtures/architecture/revised_workflows/contract.yml",
        contract=contract,
    )
    with pytest.raises(audit.WorkflowEvolutionError, match=message):
        _evaluate([transition], {EVIDENCE_PATH: receipt})


def test_maintenance_revise_preserves_protected_research_family() -> None:
    path = ".github/workflows/fotmob-utc-native-xg-fresh-holdout-release-receipts.yml"
    before_raw = retirement.resolve_reviewed_workflow_source(path)
    after_raw = before_raw + b"\n# synthetic protected-maintenance test\n"
    transition, receipt = _maintenance_transition(
        path,
        before_raw=before_raw,
        after_raw=after_raw,
        identifier="P44A1_FH_RELEASE_RECEIPT",
        fixture_path="tests/fixtures/architecture/revised_workflows/fh-release-before.yml",
    )
    assert transition["canonical_family"] == "PROTECTED_RESEARCH"
    assert _evaluate([transition], {EVIDENCE_PATH: receipt})[path] == audit.source_identity(after_raw)

    wrong_family, wrong_family_receipt = _maintenance_transition(
        path,
        before_raw=before_raw,
        after_raw=after_raw,
        identifier="P44A1_FH_WRONG_FAMILY",
        fixture_path="tests/fixtures/architecture/revised_workflows/fh-release-wrong-family.yml",
        family="ATHENA_INGEST",
    )
    with pytest.raises(audit.WorkflowEvolutionError, match="family differs from P4.3A"):
        _evaluate([wrong_family], {EVIDENCE_PATH: wrong_family_receipt})


def test_chained_maintenance_revisions_require_exact_immediate_before_versions() -> None:
    path = ".github/workflows/athena-run.yml"
    before_a = retirement.resolve_reviewed_workflow_source(path)
    before_b = before_a + b"\n# revision B\n"
    after_c = before_b + b"# revision C\n"
    first, first_receipt = _maintenance_transition(
        path,
        before_raw=before_a,
        after_raw=before_b,
        identifier="P44A1_CHAIN_1",
        fixture_path="tests/fixtures/architecture/revised_workflows/athena-run-a.yml",
        evidence_path="artifacts/architecture/p4_4a1_chain_1.json",
        checkpoint_path="artifacts/architecture/p4_workflow_evolution_snapshots/p4_4a1_chain_1.json",
    )
    second, second_receipt = _maintenance_transition(
        path,
        before_raw=before_b,
        after_raw=after_c,
        identifier="P44A1_CHAIN_2",
        fixture_path="tests/fixtures/architecture/revised_workflows/athena-run-b.yml",
        evidence_path="artifacts/architecture/p4_4a1_chain_2.json",
        checkpoint_path="artifacts/architecture/p4_workflow_evolution_snapshots/p4_4a1_chain_2.json",
    )
    receipts = {
        first["evidence_receipt_path"]: first_receipt,
        second["evidence_receipt_path"]: second_receipt,
    }
    assert _evaluate([first, second], receipts)[path] == audit.source_identity(after_c)

    stale, stale_receipt = _maintenance_transition(
        path,
        before_raw=before_a,
        after_raw=after_c,
        identifier="P44A1_CHAIN_STALE",
        fixture_path="tests/fixtures/architecture/revised_workflows/athena-run-stale.yml",
        evidence_path="artifacts/architecture/p4_4a1_chain_stale.json",
        checkpoint_path="artifacts/architecture/p4_workflow_evolution_snapshots/p4_4a1_chain_stale.json",
    )
    with pytest.raises(audit.WorkflowEvolutionError, match="before identity does not chain"):
        _evaluate([first, stale], {**receipts, stale["evidence_receipt_path"]: stale_receipt})


def test_p43a_historical_resolver_uses_original_fixture_after_maintenance(monkeypatch) -> None:
    from scripts import audit_p4_3a_workflow_capability_census as p43a

    path = ".github/workflows/athena-run.yml"
    original = retirement.resolve_reviewed_workflow_source(path)
    revised = original + b"\n# synthetic maintenance revision\n"
    fixture_path = "tests/fixtures/architecture/revised_workflows/athena-run-original.yml"
    transition, _receipt = _maintenance_transition(
        path,
        before_raw=original,
        after_raw=revised,
        identifier="P44A1_HISTORICAL_RESOLVER",
        fixture_path=fixture_path,
    )
    transition.pop("_test_fixture_bytes")
    evolution = json.loads(P44A_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    evolution["transitions"] = [transition]

    # The source fixture, not an old commit object, is authoritative in a shallow checkout.
    monkeypatch.setattr(p43a, "_base_object_available", lambda: False)
    resolved = audit.resolve_p43a_historical_workflow_source(
        path,
        retirement_ledger=retirement.validate_retirement_history(),
        evolution_ledger=evolution,
        historical_fixture_bytes={fixture_path: original},
    )
    assert resolved == original
    assert audit.source_identity(resolved) == audit.source_identity(original)
    with pytest.raises(audit.WorkflowEvolutionError, match="historical fixture bytes differ"):
        audit.resolve_p43a_historical_workflow_source(
            path,
            retirement_ledger=retirement.validate_retirement_history(),
            evolution_ledger=evolution,
            historical_fixture_bytes={fixture_path: original + b"drift"},
        )


def test_maintenance_fixture_must_be_source_controlled_and_exact(monkeypatch) -> None:
    path = ".github/workflows/athena-run.yml"
    before_raw = retirement.resolve_reviewed_workflow_source(path)
    after_raw = before_raw + b"\n# source-controlled fixture test\n"
    transition, _receipt = _maintenance_transition(
        path,
        before_raw=before_raw,
        after_raw=after_raw,
        identifier="P44A1_TRACKED_FIXTURE",
        fixture_path="tests/fixtures/architecture/revised_workflows/source-controlled.yml",
    )
    fixture_path = transition["historical_before_fixture"]["path"]
    original_read_bytes = Path.read_bytes
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda self: before_raw if self.as_posix() == fixture_path else original_read_bytes(self),
    )
    monkeypatch.setattr(
        audit,
        "_git",
        lambda *args: transition["before"]["git_blob_sha1"].encode("ascii"),
    )
    loaded = audit._load_maintenance_before_fixtures([transition], require_source_controlled=True)
    assert loaded == {fixture_path: before_raw}

    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda self: before_raw + b"drift" if self.as_posix() == fixture_path else original_read_bytes(self),
    )
    with pytest.raises(audit.WorkflowEvolutionError, match="source identity mismatch"):
        audit._load_maintenance_before_fixtures([transition], require_source_controlled=True)

    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda self: before_raw if self.as_posix() == fixture_path else original_read_bytes(self),
    )
    monkeypatch.setattr(audit, "_git", lambda *args: b"0" * 40)
    with pytest.raises(audit.WorkflowEvolutionError, match="Git blob mismatch"):
        audit._load_maintenance_before_fixtures([transition], require_source_controlled=True)


def test_reviewed_current_identity_accepts_only_recorded_maintenance_bytes() -> None:
    path = ".github/workflows/athena-run.yml"
    before = retirement.resolve_reviewed_workflow_source(path)
    after = before + b"\n# revised current bytes\n"
    transition, receipt = _maintenance_transition(
        path,
        before_raw=before,
        after_raw=after,
        identifier="P44A1_CURRENT_IDENTITY",
        fixture_path="tests/fixtures/architecture/revised_workflows/athena-run-current.yml",
    )
    expected = _evaluate([transition], {EVIDENCE_PATH: receipt})
    observed = dict(expected)
    observed[path] = audit.source_identity(after)
    audit.validate_derived_tree(expected, observed)
    observed[path] = audit.source_identity(after + b"drift")
    with pytest.raises(audit.WorkflowEvolutionError, match="identity differs"):
        audit.validate_derived_tree(expected, observed)


def test_retire_added_path_requires_exact_fixture_and_before_identity() -> None:
    identity = audit.source_identity(b"one")
    add, add_receipt = _transition("ADD", after=identity)
    retire, retire_receipt = _transition("RETIRE", before=identity, identifier="P44B_2", fixture={"path": FIXTURE, **identity})
    retire["evidence_receipt_path"] = "artifacts/architecture/p4_4c_retirement_evidence_v1.json"
    retire["checkpoint_snapshot_path"] = "artifacts/architecture/p4_workflow_evolution_snapshots/p4_4c_retirement.json"
    retire_receipt["reviewed_workflow_transition"]["evidence_receipt_path"] = retire["evidence_receipt_path"]
    retire_receipt["reviewed_workflow_transition"]["checkpoint_snapshot_path"] = retire["checkpoint_snapshot_path"]
    retire["evidence_body_sha256"] = audit.receipt_evidence_body_sha256(retire_receipt)
    retire_receipt["canonical_sha256"] = audit.canonical_sha256(retire_receipt)
    receipts = {EVIDENCE_PATH: add_receipt, retire["evidence_receipt_path"]: retire_receipt}
    baseline, _ = _baseline()
    assert _evaluate([add, retire], receipts) == baseline
    drift = copy.deepcopy(retire)
    drift["historical_fixture"]["source_sha256"] = "0" * 64
    with pytest.raises(audit.WorkflowEvolutionError, match="exact operation"):
        _evaluate([add, drift], receipts)


def test_evidence_hash_excludes_only_backlink_and_self_hash() -> None:
    add, receipt = _transition("ADD", after=audit.source_identity(b"one"))
    digest = add["evidence_body_sha256"]
    altered = dict(receipt, workflow_evolution_ledger_sha256="b" * 64)
    altered["canonical_sha256"] = audit.canonical_sha256(altered)
    assert audit.receipt_evidence_body_sha256(altered) == digest
    altered["reviewed_workflow_transition"] = dict(altered["reviewed_workflow_transition"], phase_id="P4.4C")
    assert audit.receipt_evidence_body_sha256(altered) != digest


def test_unknown_or_missing_paths_fail_closed() -> None:
    baseline, _ = _baseline()
    missing = dict(baseline)
    missing.pop(".github/workflows/athena-run.yml")
    with pytest.raises(audit.WorkflowEvolutionError, match="live workflow set"):
        audit.validate_derived_tree(baseline, missing)
    extra = dict(baseline, **{NEW_PATH: audit.source_identity(b"one")})
    with pytest.raises(audit.WorkflowEvolutionError, match="live workflow set"):
        audit.validate_derived_tree(baseline, extra)


def test_baseline_and_ledger_have_frozen_evidence_identity() -> None:
    ledger = json.loads(audit.LEDGER_PATH.read_text(encoding="utf-8"))
    assert ledger["p4_3a_matrix_sha256"] == retirement.MATRIX_SHA256
    assert ledger["base_p4_3_retirement_checkpoint_sha256"] == audit.BASE_RETIREMENT_LEDGER_SHA256
    assert ledger["current_p4_3_retirement_ledger_sha256"] == audit.BASE_RETIREMENT_LEDGER_SHA256
    assert ledger["p4_3d_receipt_sha256"] == audit.P43D_RECEIPT_SHA256


def test_evolution_snapshot_extension_accepts_a_reviewed_p43_retirement() -> None:
    snapshot, current_p43, added_entry = _synthetic_p43_retirement_extension()
    expected = [*retirement._expected_entries(), added_entry]
    retirement.validate_reviewed_retirement_entries(snapshot, current_p43, expected_entries=expected)
    assert len(audit.baseline_state(current_p43)) == 36
    current_evolution = _synthetic_evolution_after_p43_extension(current_p43)
    audit.validate_evolution_snapshot_extension(
        json.loads(P44A_SNAPSHOT_PATH.read_text(encoding="utf-8")),
        current_evolution,
        snapshot_retirement_snapshot=snapshot,
        current_retirement_snapshot=current_p43,
        current_retirement=current_p43,
    )
    assert current_evolution["current_live_workflow_count"] == 36


def test_unreviewed_or_rewritten_p43_retirement_fails_closed() -> None:
    snapshot, current_p43, _added_entry = _synthetic_p43_retirement_extension()
    with pytest.raises(retirement.RetirementLedgerError, match="reviewed evidence"):
        retirement.validate_reviewed_retirement_entries(
            snapshot, current_p43, expected_entries=retirement._expected_entries()
        )
    changed = copy.deepcopy(current_p43)
    historical_path = snapshot["retired_workflow_paths"][0]
    changed_entry = next(entry for entry in changed["retirements"] if entry["workflow_path"] == historical_path)
    changed_entry["source_sha256"] = "0" * 64
    changed["canonical_sha256"] = retirement.canonical_sha256(changed)
    with pytest.raises(retirement.RetirementLedgerError):
        retirement.validate_historical_snapshot_extension(snapshot, changed)


def test_transition_receipts_must_bind_each_exact_phase_snapshot() -> None:
    before = audit.source_identity(b"first\n")
    add, receipt = _transition("ADD", after=before, identifier="P44B_PHASE_1")
    snapshot = _phase_checkpoint(add, receipt)
    assert receipt["workflow_evolution_ledger_sha256"] == snapshot["canonical_sha256"]

    after = audit.source_identity(b"second\n")
    revise, revise_receipt = _transition("REVISE", before=before, after=after, identifier="P44B_PHASE_2")
    revise["evidence_receipt_path"] = "artifacts/architecture/p4_4c_phase_2.json"
    revise["checkpoint_snapshot_path"] = "artifacts/architecture/p4_workflow_evolution_snapshots/p4_4b_phase_2.json"
    revise_receipt["reviewed_workflow_transition"]["evidence_receipt_path"] = revise["evidence_receipt_path"]
    revise_receipt["reviewed_workflow_transition"]["checkpoint_snapshot_path"] = revise["checkpoint_snapshot_path"]
    revise["evidence_body_sha256"] = audit.receipt_evidence_body_sha256(revise_receipt)
    revise_snapshot = copy.deepcopy(snapshot)
    revise_snapshot["transitions"] = [add, revise]
    revise_snapshot["current_live_workflow_count"] = 38
    revise_snapshot["current_workflow_tree_sha1"] = "3" * 40
    revise_snapshot["canonical_sha256"] = audit.canonical_sha256(revise_snapshot)
    revise_receipt["workflow_evolution_ledger_sha256"] = revise_snapshot["canonical_sha256"]
    revise_receipt["canonical_sha256"] = audit.canonical_sha256(revise_receipt)
    current = copy.deepcopy(revise_snapshot)
    receipts = {
        add["evidence_receipt_path"]: receipt,
        revise["evidence_receipt_path"]: revise_receipt,
    }
    snapshots = {
        add["checkpoint_snapshot_path"]: snapshot,
        revise["checkpoint_snapshot_path"]: revise_snapshot,
    }
    p43 = retirement._load_p43c_ledger_snapshot()
    audit.validate_transition_checkpoints(
        [add, revise], current,
        receipts=receipts,
        snapshots=snapshots,
        current_retirement=p43,
        current_retirement_snapshot=p43,
    )

    tampered = copy.deepcopy(receipts)
    tampered[add["evidence_receipt_path"]]["workflow_evolution_ledger_sha256"] = "f" * 64
    tampered[add["evidence_receipt_path"]]["canonical_sha256"] = audit.canonical_sha256(
        tampered[add["evidence_receipt_path"]]
    )
    with pytest.raises(audit.WorkflowEvolutionError, match="backlink differs"):
        audit.validate_transition_checkpoints(
            [add, revise], current,
            receipts=tampered,
            snapshots=snapshots,
            current_retirement=p43,
            current_retirement_snapshot=p43,
        )
    reordered = copy.deepcopy(current)
    reordered["transitions"] = [revise, add]
    reordered["canonical_sha256"] = audit.canonical_sha256(reordered)
    with pytest.raises(audit.WorkflowEvolutionError, match="rewrote or reordered"):
        audit.validate_evolution_snapshot_extension(
            snapshot,
            reordered,
            snapshot_retirement_snapshot=p43,
            current_retirement_snapshot=p43,
            current_retirement=p43,
        )


def test_evolution_snapshot_extension_rejects_transition_prefix_rewrite() -> None:
    before = audit.source_identity(b"first\n")
    add, receipt = _transition("ADD", after=before, identifier="P44B_PREFIX_1")
    snapshot = _phase_checkpoint(add, receipt)
    current = copy.deepcopy(snapshot)
    current["transitions"] = []
    current["current_live_workflow_count"] = 37
    current["current_workflow_tree_sha1"] = "4" * 40
    current["canonical_sha256"] = audit.canonical_sha256(current)
    p43 = retirement._load_p43c_ledger_snapshot()
    with pytest.raises(audit.WorkflowEvolutionError, match="rewrote or reordered"):
        audit.validate_evolution_snapshot_extension(
            snapshot,
            current,
            snapshot_retirement_snapshot=p43,
            current_retirement_snapshot=p43,
            current_retirement=p43,
        )
