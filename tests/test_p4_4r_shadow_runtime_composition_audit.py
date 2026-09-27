from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import audit_p4_4r_shadow_runtime_composition_stabilization as audit


ROOT = Path(__file__).resolve().parents[1]


def _reseal(value: dict) -> dict:
    semantic = dict(value)
    semantic.pop("canonical_sha256", None)
    value["canonical_sha256"] = hashlib.sha256(audit._canonical(semantic)).hexdigest()
    return value


def test_runtime_binding_exposes_first_class_fresh_reprice_contract() -> None:
    from domain import current_shadow_runtime_bindings as bindings

    payload = bindings.policy_payload(composition=bindings.FRESH_REPRICE_COMPOSITION)
    contract = payload["fresh_reprice_contract"]
    assert payload["semantic_correctness_depends_on_monkeypatch_install_order"] is False
    assert contract["same_fixture_identity"] is True
    assert contract["same_provider_event_id"] is True
    assert contract["same_reconciliation_replay"] is True
    assert contract["fresh_observation_strictly_newer_than_reconciliation_and_prior_quote"] is True
    assert contract["evaluation_time_equals_fresh_observation"] is True
    assert contract["raw_manifest_inventory_and_registry_ancestry_replayed"] is True
    assert contract["legacy_mapping_and_bridge_identities"] is False
    assert contract["unknown_source_context_mode_fails_closed"] is True
    assert len(bindings.policy_sha256(composition=bindings.FRESH_REPRICE_COMPOSITION)) == 64


def test_p4_4r_receipt_rejects_reselfhashed_authority_or_evidence_overclaim() -> None:
    receipt = json.loads((ROOT / audit.RECEIPT_PATH).read_text(encoding="utf-8"))
    tampered = copy.deepcopy(receipt)
    tampered["evidence_classification"] = "FULL_BYTE_FOR_BYTE_LIVE_REPLAY"
    _reseal(tampered)
    with pytest.raises(audit.P44RError, match="evidence classification"):
        audit.verify_receipt(tampered)

    tampered = copy.deepcopy(receipt)
    tampered["offline_only_authority"]["workflow_dispatches_during_implementation"] = 1
    _reseal(tampered)
    with pytest.raises(audit.P44RError, match="authority/counter boundary"):
        audit.verify_receipt(tampered)


def test_p4_4r_fixture_hashes_fail_closed_on_raw_evidence_drift(tmp_path: Path) -> None:
    relative = "fresh/event.raw.json"
    destination = tmp_path / audit.FIXTURE_ROOT / relative
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"tampered exact provider bytes")
    expected_shas = dict(audit.FIXTURE_SHAS)
    for other, expected in audit.FIXTURE_SHAS.items():
        if other == relative:
            continue
        path = tmp_path / audit.FIXTURE_ROOT / other
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"placeholder")
        expected_shas[other] = hashlib.sha256(b"placeholder").hexdigest()
    with pytest.raises(audit.P44RError, match="fresh/event.raw.json"):
        audit._verify_fixture_files(tmp_path, expected_shas)


def test_p4_4r_runtime_source_has_no_fresh_semantic_patch_stack() -> None:
    audit._verify_runtime_composition(ROOT)
