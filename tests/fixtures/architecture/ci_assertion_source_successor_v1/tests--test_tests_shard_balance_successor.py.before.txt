"""Exactly-once partition and path-exact, fail-closed workflow evolution."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import pytest
import yaml

from scripts import audit_tests_shard_balance_successor as audit


def selection_code():
    workflow = yaml.safe_load((audit.ROOT / audit.WORKFLOW).read_text())
    step = next(s for s in workflow['jobs']['test_shard']['steps']
                if s['name'] == 'Select deterministic test-file shard')
    return step['run'].split("python - <<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]


def run_partition(monkeypatch, tmp_path, *, count=8):
    paths = sorted(p.relative_to(audit.ROOT).as_posix()
                   for p in (audit.ROOT / 'tests').rglob('test_*.py'))
    for path in paths:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
    code = selection_code()
    monkeypatch.chdir(tmp_path)
    selected = []
    for number in range(1, 9):
        monkeypatch.setenv('SHARD_NUMBER', str(number))
        monkeypatch.setenv('SHARD_COUNT', str(count))
        scope = {}
        exec(compile(code, '<exact-workflow-partition>', 'exec'), scope)
        current = (tmp_path / '.pytest-shard-files').read_text().splitlines()
        assert current == sorted(current)
        assert current
        selected.append(current)
    return paths, selected


def test_every_real_test_file_is_assigned_exactly_once(monkeypatch, tmp_path):
    paths, groups = run_partition(monkeypatch, tmp_path)
    assert Counter(p for group in groups for p in group) == Counter(paths)
    assert len(groups) == 8
    assert 'tests/test_core_01d_checkpoint_e_completion_v9.py' in groups[4]
    assert 'tests/test_core_01d_checkpoint_e_completion_v10.py' in groups[0]
    assert 'tests/test_lg_a_worker_launch_failure_remediation.py' in groups[1]
    # Evidence-based whole-file moves from exact-head run 40086219683.
    expected_shards = {
        'tests/test_core_01d_checkpoint_e_completion.py': 6,
        'tests/test_core_01d_checkpoint_e_completion_v2.py': 7,
        'tests/test_core_01d_retained_workflow_status.py': 3,
        'tests/test_core_01d_workflow_consolidation.py': 7,
        'tests/test_core_01d_checkpoint_e_completion_v10.py': 1,
    }
    for path, shard in expected_shards.items():
        assert path in groups[shard - 1]
    # Replay is deterministic; no probabilistic placement or cache state.
    _, repeated = run_partition(monkeypatch, tmp_path)
    assert groups == repeated


@pytest.mark.parametrize('count', [0, 7, 9])
def test_partition_rejects_changed_required_shard_count(monkeypatch, tmp_path, count):
    with pytest.raises(SystemExit, match='exactly eight'):
        run_partition(monkeypatch, tmp_path, count=count)


def test_partition_refuses_missing_heavy_file(monkeypatch, tmp_path):
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests/test_other.py').touch()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('SHARD_NUMBER', '1')
    monkeypatch.setenv('SHARD_COUNT', '8')
    # Read authoritative code through the absolute repository root.
    with pytest.raises(SystemExit, match='heavy test file is missing'):
        exec(compile(selection_code(), '<exact-workflow-partition>', 'exec'), {})


def test_exact_successor_and_original_p4_prefix():
    receipt = audit.authenticate()
    assert receipt['authority_granted'] is False
    assert receipt['required_contexts_changed'] is False
    assert audit.project_tree(audit.AFTER_TREE) == audit.BEFORE_TREE
    assert audit.project_b4_tree(audit.AFTER_B4_TREE) == audit.BEFORE_B4_TREE
    from scripts import audit_phase_a_pc_upcoming_retention_successor as retention
    assert retention.authenticate()['canonical_sha256'] == retention.RECEIPT_SHA256
    from scripts import audit_data_01c_restore_portability as d5
    assert d5.historical_workflow_tree(audit.AFTER_TREE) == d5.PREDECESSOR_TREE
    assert d5.historical_workflow_tree(audit.BEFORE_TREE) == d5.PREDECESSOR_TREE


def test_v2_rebalance_is_an_append_only_exact_v1_successor():
    audit.authenticate()
    value = audit._authenticate_v2()
    from scripts import audit_phase_a_pass_a_tests_source_successor as pass_a
    from scripts import audit_p4_workflow_evolution_ledger as p4
    from scripts import audit_phase_a_pc_upcoming_retention_successor as retention
    from scripts import audit_data_01c_restore_portability as d5

    assert value['canonical_sha256'] == pass_a.TESTS_SHARD_V2_RECEIPT_SHA256
    assert value['workflow_before'] == audit.V1_AFTER
    assert value['workflow_after'] == audit.V2_AFTER
    assert value['workflow_tree_before_sha1'] == audit.V1_AFTER_TREE
    assert value['workflow_tree_after_sha1'] == audit.V2_AFTER_TREE
    assert value['b4_projected_before_sha1'] == audit.V1_AFTER_B4_TREE
    assert value['b4_projected_after_sha1'] == audit.V2_AFTER_B4_TREE
    assert value['source_forward'].keys() == pass_a.TESTS_SHARD_V2_SOURCE_PATHS
    assert value['timing_evidence']['projected_completed_shard_max_seconds'] < 5 * 60 * 60
    assert value['timing_evidence']['projection_uncertainty'].startswith(
        'cancelled shards provide progress only')
    snapshot = audit.read_blob(audit.V2_SNAPSHOT)
    snapshot_value = json.loads(snapshot)
    prior = json.loads(audit.read_blob(audit.V1_SNAPSHOT))
    assert snapshot_value['transitions'][:-1] == prior['transitions']
    assert p4.canonical_sha256(snapshot_value) == snapshot_value['canonical_sha256']
    assert audit.project_tree(audit.V2_AFTER_TREE) == audit.BEFORE_TREE
    assert audit.project_b4_tree(audit.V2_AFTER_B4_TREE) == audit.BEFORE_B4_TREE
    assert retention.authenticate()['canonical_sha256'] == retention.RECEIPT_SHA256
    assert retention.authenticate_bootstrap_sources() is True
    for path, row in value['source_forward'].items():
        assert retention.BOOTSTRAP_AFTER[path] == pass_a._parent_progress_receipt()['source_forward'][path]['after']
    assert d5.historical_workflow_tree(audit.V2_AFTER_TREE) == d5.PREDECESSOR_TREE


@pytest.mark.parametrize('which', [
    'v2_receipt', 'v2_snapshot', 'current_workflow', 'workflow_fixture',
    'current_adapter', 'adapter_fixture', 'current_test', 'test_fixture',
])
def test_v2_rebalance_rejects_tampered_current_or_predecessor(monkeypatch, which):
    from scripts import audit_phase_a_pass_a_tests_source_successor as pass_a
    target = {
        'v2_receipt': (pass_a, audit.V2_RECEIPT),
        'v2_snapshot': (audit, audit.V2_SNAPSHOT),
        'current_workflow': (audit, audit.WORKFLOW),
        'workflow_fixture': (audit, audit.V2_FIXTURE),
        'current_adapter': (pass_a, 'scripts/audit_tests_shard_balance_successor.py'),
        'adapter_fixture': (pass_a, audit.V2_SOURCE_FIXTURE),
        'current_test': (pass_a, 'tests/test_tests_shard_balance_successor.py'),
        'test_fixture': (pass_a, audit.V2_TEST_FIXTURE),
    }[which]
    module, path = target
    original = module.read_blob
    monkeypatch.setattr(module, 'read_blob',
                        lambda candidate: original(candidate) + (b'\n' if candidate == path else b''))
    with pytest.raises((ValueError, AssertionError)):
        audit.authenticate()


@pytest.mark.parametrize('which', ['workflow', 'fixture', 'receipt', 'snapshot', 'source', 'source_fixture'])
def test_exact_evidence_tampering_rejected(monkeypatch, which):
    receipt = audit.receipt()
    source = 'scripts/audit_data_01c_restore_portability.py'
    path = {'workflow': audit.WORKFLOW, 'fixture': audit.FIXTURE,
            'receipt': audit.RECEIPT, 'snapshot': audit.SNAPSHOT,
            'source': source, 'source_fixture': receipt['source_forward'][source]['fixture']}[which]
    original = audit.read_blob
    monkeypatch.setattr(audit, 'read_blob', lambda p: original(p) + (b'\n' if p == path else b''))
    with pytest.raises(ValueError):
        audit.authenticate()


def test_unrelated_tree_and_workflow_change_rejected(monkeypatch):
    original = audit.tree_entries
    raw = original()
    # Mutate a neighboring workflow's blob without changing this approved path.
    lines = raw.splitlines()
    index = next(i for i, line in enumerate(lines) if line.endswith(b'\tathena-run.yml'))
    header, name = lines[index].split(b'\t')
    mode, kind, blob = header.split()
    lines[index] = mode + b' ' + kind + b' ' + b'0' * 40 + b'\t' + name
    monkeypatch.setattr(audit, 'tree_entries', lambda: b'\n'.join(lines) + b'\n')
    with pytest.raises(ValueError, match='tree'):
        audit.authenticate()


def test_forged_current_source_is_not_an_alternative_predecessor():
    path = 'scripts/audit_core_01d_retained_workflow_status_v3.py'
    with pytest.raises(ValueError, match='source'):
        audit.predecessor_source(path, audit.read_blob(path) + b'\n')


def test_historical_tests_identity_and_unknown_paths_remain_exact():
    from scripts import audit_core_01d_retained_workflow_status_v3 as v3
    row = v3._source_identity(audit.WORKFLOW)
    assert row['git_blob_sha1'] == audit.BEFORE['git_blob_sha1']
    assert row['source_sha256'] == audit.BEFORE['source_sha256']
    assert audit.predecessor_source('unrelated/path', b'unmodified') == b'unmodified'
    assert audit.project_tree('0' * 40) == '0' * 40
    assert audit.project_b4_tree('0' * 40) == '0' * 40


def test_historical_source_projection_is_exact_idempotent_and_keeps_unknown_rows():
    from scripts import audit_phase_a_pc_upcoming_retention_successor as retention
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    latest = a2.authenticate_inventory()
    raw = b'100644 blob ' + audit.AFTER['git_blob_sha1'].encode() + b'\t' + audit.WORKFLOW.encode() + b'\n'
    unknown = b'100644 blob ' + b'1' * 40 + b'\tunknown.py\n'
    result = retention.project_retention_inventory(raw + unknown, latest=latest)
    assert result == raw.replace(audit.AFTER['git_blob_sha1'].encode(), audit.BEFORE['git_blob_sha1'].encode()) + unknown
    assert retention.project_retention_inventory(result, latest=latest) == result


def test_parent_progress_preserves_partition_and_immutable_v2():
    from scripts import audit_phase_a_pass_a_tests_source_successor as progress
    value = progress.authenticate_parent_progress()
    before = audit.read_blob(progress.PARENT_PROGRESS_FIXTURE)
    after = audit.read_blob(audit.WORKFLOW)
    assert before.replace(progress.PARENT_PROGRESS_COMMAND_BEFORE.encode(),
                          progress.PARENT_PROGRESS_COMMAND_AFTER.encode()) == after
    assert value['test_assignments_changed'] is False
    assert value['required_contexts_changed'] is False
    assert value['child_environment_changed'] is False
    assert audit._authenticate_v2()['canonical_sha256'] == progress.TESTS_SHARD_V2_RECEIPT_SHA256
    assert audit.project_tree(audit.V2_AFTER_TREE) == audit.BEFORE_TREE
    for path, row in value['source_forward'].items():
        assert progress._parent_progress_predecessor_source(path, progress.read_blob(path)) == progress.read_blob(row['fixture'])
    assert progress._parent_progress_predecessor_source('unknown/path', b'unchanged') == b'unchanged'


@pytest.mark.parametrize('target', ['receipt', 'snapshot', 'workflow_fixture', 'source_fixture', 'source', 'a2_predecessor'])
def test_parent_progress_rejects_tampered_evidence(monkeypatch, target):
    from scripts import audit_phase_a_pass_a_tests_source_successor as progress
    row = progress._parent_progress_receipt()['source_forward']['scripts/audit_tests_shard_balance_successor.py']
    path = {'receipt': progress.PARENT_PROGRESS_RECEIPT,
            'snapshot': progress.PARENT_PROGRESS_SNAPSHOT,
            'workflow_fixture': progress.PARENT_PROGRESS_FIXTURE,
            'source_fixture': row['fixture'],
            'source': 'scripts/audit_tests_shard_balance_successor.py',
            'a2_predecessor': progress.PARENT_PROGRESS_A2['path']}[target]
    original = progress.read_blob
    monkeypatch.setattr(progress, 'read_blob', lambda p: original(p) + (b'\n' if p == path else b''))
    with pytest.raises((ValueError, AssertionError)):
        audit.authenticate()


def test_parent_progress_does_not_instrument_children_or_change_clean_replay(tmp_path):
    """CLI parent emits flushed nodes; child pytest and digest stdout stay exact."""
    import os
    import subprocess
    import sys

    child = tmp_path / 'child'
    child.mkdir()
    (child / 'test_clean.py').write_text('def test_clean():\n    assert True\n')
    # Mimic P4.4R's clean-process contract: stdout is a parseable single digest,
    # and a child invoking pytest without -p receives ordinary pytest behavior.
    (tmp_path / 'test_parent.py').write_text('''
import hashlib, json, os, subprocess, sys
from pathlib import Path

def test_child_replay():
    before = dict(os.environ)
    code = "from scripts import audit_phase_a_pass_a_tests_source_successor; import hashlib; print(hashlib.sha256(b'retained-clean-replay').hexdigest())"
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True)
    digest = result.stdout.strip()
    assert len(digest) == 64 and digest == hashlib.sha256(b'retained-clean-replay').hexdigest()
    nested = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'child/test_clean.py'], capture_output=True, text=True, check=True)
    assert '1 passed' in nested.stdout and 'ATHENA_PYTEST_PROGRESS' not in nested.stdout + nested.stderr
    assert dict(os.environ) == before
    Path('result.json').write_text(json.dumps({'digest': digest, 'environment': before}, sort_keys=True))
''')
    env = dict(os.environ)
    env['PYTHONPATH'] = str(audit.ROOT) + os.pathsep + env.get('PYTHONPATH', '')
    command = [sys.executable, '-m', 'pytest', '-q', 'test_parent.py']
    plain = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
    baseline = (tmp_path / 'result.json').read_bytes()
    instrumented = subprocess.run(command[:3] + ['-p', 'scripts.audit_phase_a_pass_a_tests_source_successor'] + command[3:],
                                  cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
    assert (tmp_path / 'result.json').read_bytes() == baseline
    assert 'ATHENA_PYTEST_PROGRESS' not in plain.stdout + plain.stderr
    records = [json.loads(line.split('ATHENA_PYTEST_PROGRESS ', 1)[1])
               for line in instrumented.stdout.splitlines() if line.startswith('ATHENA_PYTEST_PROGRESS ')]
    assert [r['event'] for r in records] == ['session_start', 'start', 'setup', 'call', 'teardown', 'finish']
    assert len({r['pid'] for r in records}) == 1
    assert [r['nodeid'] for r in records[1:]] == ['test_parent.py::test_child_replay'] * 5
