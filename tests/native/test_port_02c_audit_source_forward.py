"""Historical receipt immutability and exact current-source forward pins."""
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from scripts import audit_p4_workflow_evolution_ledger as evolution
from scripts import audit_p4_4s_canonical_adapter_bound_context_builder as p44s

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
