"""Historical receipt immutability and exact current-source forward pins."""
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from scripts import audit_p4_workflow_evolution_ledger as evolution
from scripts import audit_p4_4s_canonical_adapter_bound_context_builder as p44s
from scripts import audit_port_01_source_identity_parity as port01

ROOT = Path(__file__).resolve().parents[2]


def test_adapter_successor_exact_not_historical_rewrite():
    source = (ROOT / "domain/current_shadow_canonical_core_adapter.py").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(source).hexdigest() == p44s.PORT02C_ADAPTER_SUCCESSOR_SHA256
    assert p44s.ADAPTER_AFTER_SHA256 == "bf1a9acff635a378f81bafa73f8274a4b9806e34d8d7c3ca13bad1729e205ce2"
    assert p44s.audit(ROOT)["current_source_forward_classification"] == "PORT02C_EXPLICIT_VERIFIED_RELEASE_RESOURCE_RESOLUTION_ONLY"


@pytest.mark.parametrize("mutation", ["tree", "ledger", "before", "after"])
def test_workflow_forward_rejects_arbitrary_future_source(mutation):
    path = evolution.PORT02C_REPLAY_WORKFLOW_PATH
    derived = {path: deepcopy(evolution.PORT02C_REPLAY_WORKFLOW_BEFORE)}
    observed = {path: deepcopy(evolution.PORT02C_REPLAY_WORKFLOW_AFTER)}
    tree = evolution.PORT02C_REPLAY_WORKFLOW_TREE_SHA1
    ledger = "d1c8d79ac48bf0521a609e29991014513bd2f7afed2389c5e3a9d6ec8bfba8a2"
    assert evolution._port02c_current_source_forward(derived, observed, head_tree=tree, ledger_sha=ledger)[path] == observed[path]
    if mutation == "tree": tree = "0" * 40
    elif mutation == "ledger": ledger = "0" * 64
    elif mutation == "before": derived[path]["source_sha256"] = "0" * 64
    else: observed[path]["source_sha256"] = "0" * 64
    with pytest.raises(evolution.WorkflowEvolutionError):
        evolution._port02c_current_source_forward(derived, observed, head_tree=tree, ledger_sha=ledger)


def test_attributes_current_forward_keeps_historical_anchor_exact():
    historical = next(a for a in port01.EXPECTED_ANCHORS if a["anchor_id"] == "GIT_ATTRIBUTES")
    assert historical["git_blob_sha1"] == "39ccd8d38ce17c105a906e2f1416f68e64fcc862"
    assert port01.current_anchor_identity(historical)["git_blob_sha1"] == "58e4728b1f6189b5e7aaa277611359ec51f22a91"
    with pytest.raises(port01.PortabilityAuditError):
        port01.current_anchor_identity({**historical, "git_blob_sha1": "0" * 40})


def test_d5_second_successor_does_not_replace_original_identity():
    from scripts import audit_data_01c_restore_portability as d5
    assert evolution.source_identity(d5.predecessor_source(d5.WORKFLOW)) == evolution.PORT02C_REPLAY_WORKFLOW_AFTER
    after, tree = d5.successor_context()
    assert after != evolution.PORT02C_REPLAY_WORKFLOW_AFTER
    assert tree != evolution.CORE01D_PR119_WORKFLOW_TREE_SHA1
    assert evolution.PORT02C_REPLAY_WORKFLOW_BEFORE["git_blob_sha1"] == "cb7374cbf4d1d35a39964d123e75367996983d6c"
    with pytest.raises(evolution.WorkflowEvolutionError):
        evolution._port02c_current_source_forward({d5.WORKFLOW: after}, {d5.WORKFLOW: after},
            head_tree=tree, ledger_sha=evolution.CORE01D_PR119_LEDGER_SHA256)
