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
    path = "scripts/audit_p4_workflow_evolution_ledger.py"
    blob = audit.identity((audit.ROOT / path).read_bytes().replace(b"\r\n", b"\n"))["git_blob_sha1"]
    raw = b"100644 blob " + blob.encode() + b"\t" + path.encode() + b"\n"
    projected = audit.project_historical_inventory(raw)
    assert projected != raw
    assert audit.project_historical_inventory(projected) == projected


def test_checkpoint_e_projection_keeps_only_exact_v74_predecessor_paths():
    from scripts import audit_core_01d_checkpoint_e_completion as checkpoint
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    from scripts import audit_core_01d_historical_retention_acceptance as retention
    from scripts import audit_data_01c_app_store_complete as app_store

    historical = audit.historical_d4_sources()
    v74 = a2.read_generation(a2.inventory_generation_path(74))
    v74_paths = {row["path"] for row in v74["source_identities"]}
    assert set(historical) == set(audit.D4_BASE_SOURCE_PATHS)
    assert set(app_store.SUCCESSOR_SOURCE_PATHS) & v74_paths == set(historical)
    raw_sources = []
    expected_sources = []
    for path in audit.D4_BASE_SOURCE_PATHS:
        row = historical[path]
        current = audit.identity((audit.ROOT / path).read_bytes().replace(b"\r\n", b"\n"))
        raw_sources.append(b"100644 blob " + current["git_blob_sha1"].encode() + b"\t" + path.encode() + b"\n")
        expected_sources.append(b"100644 blob " + row["git_blob_sha1"].encode() + b"\t" + path.encode() + b"\n")
    assert audit.project_historical_inventory(b"".join(raw_sources)) == b"".join(expected_sources)

    raw = retention.v4.v3._git("ls-tree", "-r", "HEAD")
    assert checkpoint.validate_bounded_inventory(raw) is None


def test_v74_predecessor_source_fixture_rejects_tampering():
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2

    raw = (audit.ROOT / audit.D4_BASE_SOURCE_FIXTURE).read_bytes()
    value = json.loads(raw)
    value["sources"][audit.D4_BASE_SOURCE_PATHS[0]]["git_blob_sha1"] = "0" * 40
    with pytest.raises(ValueError, match="fixture digest drift"):
        audit.parse_historical_d4_sources(qualifier.canonical(value),
                                          a2.read_generation(a2.inventory_generation_path(74)))


def test_a2_historical_source_forward_uses_only_v1_pinned_bytes(tmp_path, monkeypatch):
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    for source, fixture in audit.HISTORICAL_A2_SOURCE_FIXTURES.items():
        raw = (audit.ROOT / fixture).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() == a2.pinned_historical_identity(source)
        assert audit.historical_a2_source_blob_identity(source) == audit.identity(raw)["git_blob_sha1"]

    source = "tests/test_p4_4a_workflow_evolution_guard.py"
    historical_blob = audit.historical_a2_source_blob_identity(source)
    current_blob = audit.identity((audit.ROOT / source).read_bytes().replace(b"\r\n", b"\n"))["git_blob_sha1"]
    raw_current = b"100644 blob " + current_blob.encode() + b"\t" + source.encode() + b"\n"
    projected = audit.project_historical_inventory(raw_current)
    assert projected == b"100644 blob " + historical_blob.encode() + b"\t" + source.encode() + b"\n"

    from scripts import audit_data_01c_app_store_complete as store
    existing_p4_sources = {
        "scripts/audit_p4_workflow_evolution_ledger.py",
        "tests/native/test_port_02c_audit_source_forward.py",
        source,
    }
    assert existing_p4_sources <= set(store.SOURCE_PATHS)
    assert not existing_p4_sources & store.SUCCESSOR_SOURCE_PATHS

    source, fixture = next(iter(audit.HISTORICAL_A2_SOURCE_FIXTURES.items()))
    forged_root = tmp_path / "forged"
    forged_path = forged_root / fixture
    forged_path.parent.mkdir(parents=True)
    forged_path.write_bytes(b"# substituted historical source\n")
    monkeypatch.setattr(audit, "ROOT", forged_root)
    with pytest.raises(ValueError, match="pinned A2 historical source fixture identity mismatch"):
        audit.historical_a2_source_blob_identity(source)


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
