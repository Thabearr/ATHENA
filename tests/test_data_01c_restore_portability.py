"""Bounded qualification source evolution; synthetic receipt negatives only."""
from copy import deepcopy
import hashlib
import json

import pytest
import yaml

from scripts import audit_data_01c_restore_portability as audit
from scripts import qualify_data_01c_restore_portability as qualifier
from scripts import audit_p4_workflow_evolution_ledger as evolution


def test_exact_workflow_delta_preserves_all_existing_authority_and_cases():
    before = yaml.load(audit.predecessor_source(audit.WORKFLOW), Loader=yaml.BaseLoader)
    after = yaml.load(audit.expected_workflow(), Loader=yaml.BaseLoader)
    added = after['jobs']['native-slice']['steps'].pop(-3)
    assert added['name'] == 'D5 native restore portability (offline, four cases)'
    assert added['run'].strip() == 'python scripts/qualify_data_01c_restore_portability.py --runner-temp "${{ runner.temp }}"'
    upload = after['jobs']['native-slice']['steps'][-1]['with']
    upload['path'] = upload['path'].replace(audit.UPLOAD.strip() + '\n', '')
    assert after == before
    assert audit.authenticate_workflow() == audit.successor_context()


@pytest.mark.parametrize('mutation', [
    'contents: read', 'windows-latest', 'ubuntu-24.04', 'cancel-in-progress: true',
    'python scripts/build_dev_bundle.py', 'name: CASE 1', 'name: CASE 2',
    'name: CASE 3', 'name: CASE 4', 'name: CASE 5', 'retention-days: 14',
    'workflow_dispatch:', 'branches:', 'name: Upload qualification evidence',
])
def test_workflow_mutation_cannot_unlock_successor(monkeypatch, mutation):
    from pathlib import Path
    original = Path.read_bytes
    changed = audit.expected_workflow().replace(mutation.encode(), b'UNAPPROVED', 1)
    assert changed != audit.expected_workflow()
    monkeypatch.setattr(Path, 'read_bytes', lambda path: changed if path == audit.ROOT / audit.WORKFLOW else original(path))
    with pytest.raises(ValueError, match='exact D5'):
        audit.authenticate_workflow()


def test_nodeids_and_crash_parametrizations_are_exact():
    import ast
    tree = ast.parse((audit.ROOT / qualifier.TEST_FILE).read_text())
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert all(node.rsplit('::', 1)[-1] in functions for node in qualifier.NODEIDS)
    switch = functions['test_native_same_volume_switch_recovers_each_crash_marker']
    decorators = [node for node in switch.decorator_list if isinstance(node, ast.Call)]
    values = [ast.literal_eval(node.args[1]) for node in decorators if len(node.args) == 2]
    assert values == [qualifier.PHASES]
    source = (audit.ROOT / 'scripts/qualify_data_01c_restore_portability.py').read_text()
    assert '*NODEIDS' in source and '"--basetemp="' in source
    assert 'pytest", "tests/native"' not in source


def test_historical_projection_rejects_forged_listed_source_metadata():
    path = audit.WORKFLOW
    forged = b"100644 blob " + b"0" * 40 + b"\t" + path.encode() + b"\n"
    with pytest.raises(ValueError, match='source inventory identity'):
        audit.project_historical_inventory(forged)


def test_authenticated_historical_projection_is_idempotent():
    path = audit.WORKFLOW
    blob = audit.identity(audit.expected_workflow())["git_blob_sha1"]
    raw = b"100644 blob " + blob.encode() + b"\t" + path.encode() + b"\n"
    projected = audit.project_historical_inventory(raw)
    assert projected != raw
    assert audit.project_historical_inventory(projected) == projected


def synthetic_receipt(host='Windows'):
    return {'schema_version': 1, 'policy_id': qualifier.POLICY,
            'host_os': host, 'host_os_version': 'Windows synthetic' if host == 'Windows' else 'Ubuntu 24.04 synthetic',
            'filesystem_type': 'NTFS' if host == 'Windows' else 'ext4',
            'filesystem_observation': 'WIN32_GET_VOLUME_PATH_NAME_AND_GET_VOLUME_INFORMATION' if host == 'Windows' else 'FINDMNT_TARGET_TEST_BASETEMP',
            'python_version': '3.12.0', 'final_pr_head': 'a' * 40, 'checkout_sha': 'b' * 40,
            'event_name': 'pull_request', 'run_id': 1, 'run_attempt': 1,
            'pytest_nodeids': qualifier.NODEIDS, 'passed_nodeids': qualifier.CASES,
            'crash_phases': qualifier.PHASES, 'pytest_exit_code': 0,
            'cross_process_lock_tested': True, 'same_volume_switch_tested': True,
            'network_calls': 0, 'provider_calls': 0, 'delivery_calls': 0, 'wager_actions': 0}


def seal(value):
    value = deepcopy(value)
    value.pop('canonical_sha256', None)
    value['canonical_sha256'] = hashlib.sha256(qualifier.canonical(value)).hexdigest()
    return value


@pytest.mark.parametrize('host', ['Windows', 'Linux'])
@pytest.mark.parametrize('mutation', ['filesystem', 'observation', 'os', 'nodeid', 'phase', 'head', 'result', 'manual', 'side_effect'])
def test_platform_evidence_fails_closed(host, mutation):
    value = synthetic_receipt(host)
    if mutation == 'filesystem': value['filesystem_type'] = 'overlay'
    elif mutation == 'observation': value.pop('filesystem_observation')
    elif mutation == 'os': value['host_os'] = 'Darwin'
    elif mutation == 'nodeid': value['passed_nodeids'] = []
    elif mutation == 'phase': value['crash_phases'] = []
    elif mutation == 'head': value['final_pr_head'] = 'c' * 40
    elif mutation == 'result': value['pytest_exit_code'] = 1
    elif mutation == 'manual': value['event_name'] = 'workflow_dispatch'
    else: value['network_calls'] = 1
    with pytest.raises(ValueError):
        qualifier.validate_receipt(seal(value), 'a' * 40)


@pytest.mark.parametrize('path', list(audit.FROZEN_EVIDENCE))
def test_frozen_add_checkpoint_and_ledger_tampering_rejected(monkeypatch, path):
    from pathlib import Path
    original = Path.read_bytes
    monkeypatch.setattr(Path, 'read_bytes', lambda value: original(value) + b'\n' if value == audit.ROOT / path else original(value))
    with pytest.raises(ValueError, match='historical evidence drift'):
        audit.authenticate_workflow()


@pytest.mark.parametrize('mutation', ['tree', 'ledger', 'before', 'after'])
def test_second_successor_retains_exact_predecessor_and_rejects_future(mutation):
    path = evolution.PORT02C_REPLAY_WORKFLOW_PATH
    after, tree = audit.successor_context()
    derived = {path: dict(evolution.PORT02C_REPLAY_WORKFLOW_BEFORE)}
    observed = {path: dict(after)}
    for name, (before, current) in evolution.CORE01D_PR119_CONTROL_WORKFLOW_FORWARD.items():
        derived[name] = dict(before)
        observed[name] = dict(current)
    ledger = evolution.CORE01D_PR119_LEDGER_SHA256
    assert evolution._port02c_current_source_forward(derived, observed, head_tree=tree, ledger_sha=ledger)[path] == after
    if mutation == 'tree': tree = '0' * 40
    elif mutation == 'ledger': ledger = '0' * 64
    elif mutation == 'before': derived[path]['source_sha256'] = '0' * 64
    else: observed[path]['source_sha256'] = '0' * 64
    with pytest.raises(evolution.WorkflowEvolutionError):
        evolution._port02c_current_source_forward(derived, observed, head_tree=tree, ledger_sha=ledger)
