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
    parent = pass_a._parent_progress_receipt()['source_forward']
    performance = pass_a._root_performance_receipt()['source_forward']
    correction = pass_a._ci_assertion_successor_receipt()['source_forward']
    for path, row in value['source_forward'].items():
        current = pass_a.read_blob(path)
        assert row['after'] == parent[path]['before']
        assert pass_a.safe.identity(pass_a.read_blob(parent[path]['fixture'])) == row['after']
        if path in performance:
            assert performance[path]['before'] == parent[path]['after']
            assert performance[path]['after'] == pass_a.safe.identity(current)
        elif path in correction:
            assert correction[path]['before'] == parent[path]['after']
            assert correction[path]['after'] == pass_a.safe.identity(current)
        else:
            assert parent[path]['after'] == pass_a.safe.identity(current)
        assert retention.BOOTSTRAP_AFTER[path] == pass_a.safe.identity(current)
    # D5 authenticates the checked-out current tree; the V2 tree was already
    # projected above by the Tests successor and is not a D5 caller input.
    with pytest.raises(ValueError, match='unknown PORT-02C source-forward workflow tree'):
        d5.historical_workflow_tree(audit.V2_AFTER_TREE)
    assert d5.historical_workflow_tree(audit.AFTER_TREE) == d5.PREDECESSOR_TREE


def test_v3_diagnostic_upload_is_an_append_only_exact_v2_successor():
    value = audit._authenticate_v3()
    from scripts import audit_p4_workflow_evolution_ledger as p4
    from scripts import audit_phase_a_pass_a_tests_source_successor as pass_a

    assert value['authority_granted'] is False
    assert value['historical_bytes_changed'] is False
    assert value['required_contexts_changed'] is False
    assert value['source_authority_changed'] is False
    assert value['test_assignments_changed'] is False
    assert value['test_selection_changed'] is False
    assert value['artifact_action'] == {
        'name': audit.V3_ACTION_NAME,
        'uses': audit.V3_ACTION_REF,
        'if': 'always()',
        'path': '${{ runner.temp }}/athena-pytest-progress/*.jsonl',
        'if_no_files_found': 'ignore',
        'retention_days': 3,
        'name_template': 'pytest-progress-${{ github.run_id }}-${{ github.run_attempt }}-${{ matrix.shard }}',
    }
    current_workflow = audit.read_blob(audit.WORKFLOW)
    for expression in (b'${{ runner.temp }}', b'${{ github.run_id }}',
                       b'${{ github.run_attempt }}', b'${{ matrix.shard }}'):
        assert expression in current_workflow
    assert value['workflow_before'] == audit.V3_BEFORE
    assert value['workflow_after'] == audit.V3_AFTER
    assert value['prior_snapshot'] == {
        'path': audit.V3_PREDECESSOR_SNAPSHOT,
        'canonical_sha256': audit.V3_PREDECESSOR_SNAPSHOT_SHA256,
    }
    snapshot = json.loads(audit.read_blob(audit.V3_SNAPSHOT))
    predecessor = json.loads(audit.read_blob(audit.V3_PREDECESSOR_SNAPSHOT))
    assert snapshot['transitions'][:-1] == predecessor['transitions']
    assert p4.canonical_sha256(snapshot) == value['workflow_evolution_ledger_sha256']
    assert audit.project_tree(audit.V3_AFTER_TREE) == audit.BEFORE_TREE
    assert audit.project_b4_tree(audit.V3_AFTER_B4_TREE) == audit.BEFORE_B4_TREE
    assert audit.current_workflow_source() == audit.read_blob(audit.V3_FIXTURE)
    _prior, _v2, current = pass_a._ci_assertion_v3_chain()
    assert set(current['source_forward']) == pass_a.CI_ASSERTION_V3_PATHS
    assert current['source_forward'][audit.WORKFLOW]['after'] == audit.V3_AFTER


def test_v3_p4_current_to_historical_reader_route_has_scoped_cold_and_hit():
    from scripts import audit_phase_a_pass_a_tests_source_successor as pass_a

    with pass_a.source_derivation_scope() as owner:
        first = audit._authenticate_v3()
        cold_after_first = owner.metrics.get('pass_a_ci_assertion_v3_uncached', 0)
        hits_after_cold = owner.metrics.get('pass_a_ci_assertion_v3_hits', 0)
        second = audit._authenticate_v3()
        cold_after_repeat = owner.metrics.get('pass_a_ci_assertion_v3_uncached', 0)
        hits_after_repeat = owner.metrics.get('pass_a_ci_assertion_v3_hits', 0)

    assert first == second
    assert cold_after_first == 1
    assert cold_after_repeat == cold_after_first
    assert hits_after_repeat > hits_after_cold


def test_install_context_finishes_with_pass_a_v3_and_preserves_historical_fixtures():
    import copy
    from scripts import audit_phase_a_pc_upcoming_retention_successor as retention
    from scripts import audit_phase_a_pass_a_tests_source_successor as pass_a

    context = {
        'BOOTSTRAP_AFTER': dict(retention.BOOTSTRAP_AFTER),
        'HISTORICAL_PREDECESSORS': copy.deepcopy(retention.HISTORICAL_PREDECESSORS),
        'ADDED_METADATA': dict(retention.ADDED_METADATA),
        'BOOTSTRAP_METADATA': dict(retention.BOOTSTRAP_METADATA),
        'ADDED_PYTHON_PATHS': set(retention.ADDED_PYTHON_PATHS),
        'ADDED_PYTHON_IDENTITIES': dict(retention.ADDED_PYTHON_IDENTITIES),
    }
    historical_before = copy.deepcopy(context['HISTORICAL_PREDECESSORS'])
    checkpoint_path = 'scripts/audit_core_01d_checkpoint_e_completion_v2.py'
    checkpoint_descriptor = historical_before[checkpoint_path]

    audit.install_context(context)

    _prior, _v2, pass_a_v3 = pass_a._ci_assertion_v3_chain()
    for path, row in pass_a_v3['source_forward'].items():
        current = row.get('after') or pass_a.safe.identity(pass_a.read_blob(path))
        assert context['BOOTSTRAP_AFTER'][path] == current
        if path in historical_before:
            expected = dict(historical_before[path], after=current)
            assert context['HISTORICAL_PREDECESSORS'][path] == expected
        if path in context['ADDED_PYTHON_IDENTITIES']:
            assert context['ADDED_PYTHON_IDENTITIES'][path] == current

    final_checkpoint = context['HISTORICAL_PREDECESSORS'][checkpoint_path]
    assert final_checkpoint['fixture'] == checkpoint_descriptor['fixture']
    assert {key: value for key, value in final_checkpoint.items() if key != 'after'} == {
        key: value for key, value in checkpoint_descriptor.items() if key != 'after'}
    assert final_checkpoint['source_sha256'] == (
        'c376e7c55ad95d4e182b2e4c6626e0c1605bf7834e6b81abeae432e1d06212f1')
    assert final_checkpoint['after']['source_sha256'] == pass_a_v3['source_forward'][
        checkpoint_path]['after']['source_sha256']
    assert context['BOOTSTRAP_AFTER'][audit.WORKFLOW] == audit.V3_AFTER


@pytest.mark.parametrize(('field', 'wrong_value'), [
    ('path', '${ runner.temp }/athena-pytest-progress/*.jsonl'),
    ('name_template', 'pytest-progress-${ github.run_id }-${{ github.run_attempt }}-${{ matrix.shard }}'),
])
def test_v3_diagnostic_upload_rejects_wrong_github_expression(monkeypatch, field, wrong_value):
    original = audit.read_blob
    value = json.loads(original(audit.V3_RECEIPT))
    value['artifact_action'][field] = wrong_value
    value['canonical_sha256'] = ''
    value['canonical_sha256'] = audit.digest(value)
    monkeypatch.setattr(audit, 'V3_RECEIPT_SHA256', value['canonical_sha256'])
    altered = audit.canonical(value)
    monkeypatch.setattr(audit, 'read_blob',
                        lambda path: altered if path == audit.V3_RECEIPT else original(path))
    with pytest.raises(ValueError, match='Tests shard V3 receipt scope or authority drift'):
        audit._authenticate_v3()


@pytest.mark.parametrize('target', ['receipt_predecessor', 'snapshot_prefix', 'workflow_fixture'])
def test_v3_diagnostic_upload_rejects_wrong_predecessor_or_fixture(monkeypatch, target):
    selected = {
        'receipt_predecessor': audit.V3_RECEIPT,
        'snapshot_prefix': audit.V3_SNAPSHOT,
        'workflow_fixture': audit.V3_FIXTURE,
    }[target]
    original = audit.read_blob

    def changed(path):
        raw = original(path)
        if path != selected:
            return raw
        if target == 'receipt_predecessor':
            value = json.loads(raw)
            value['predecessor_inventory']['canonical_sha256'] = '0' * 64
            return audit.canonical(value)
        if target == 'snapshot_prefix':
            value = json.loads(raw)
            value['transitions'][0]['transition_id'] += '_FORGED'
            return audit.canonical(value)
        return raw + b'\n# altered predecessor fixture\n'

    monkeypatch.setattr(audit, 'read_blob', changed)
    with pytest.raises((ValueError, AssertionError)):
        audit._authenticate_v3()


@pytest.mark.parametrize('change', ['unknown_step', 'protected_permissions'])
def test_v3_diagnostic_upload_rejects_unreviewed_workflow_delta(monkeypatch, change):
    original = audit.read_blob

    def changed(path):
        raw = original(path)
        if path != audit.WORKFLOW:
            return raw
        if change == 'unknown_step':
            return raw + b'\n# unreviewed workflow delta\n'
        marker = b'  contents: read\n'
        assert raw.count(marker) == 1
        return raw.replace(marker, b'  contents: write\n', 1)

    monkeypatch.setattr(audit, 'read_blob', changed)
    with pytest.raises((ValueError, AssertionError)):
        audit.authenticate()


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
    after = audit.read_blob(audit.V3_FIXTURE)
    current = audit.read_blob(audit.WORKFLOW)
    assert before.replace(progress.PARENT_PROGRESS_COMMAND_BEFORE.encode(),
                          progress.PARENT_PROGRESS_COMMAND_AFTER.encode()) == after
    assert audit.identity(current) == audit.V3_AFTER
    assert value['test_assignments_changed'] is False
    assert value['required_contexts_changed'] is False
    assert value['child_environment_changed'] is False
    assert audit._authenticate_v2()['canonical_sha256'] == progress.TESTS_SHARD_V2_RECEIPT_SHA256
    assert audit.project_tree(audit.V2_AFTER_TREE) == audit.BEFORE_TREE
    for path, row in value['source_forward'].items():
        current = progress.read_blob(path)
        current = progress._ci_assertion_predecessor_source(path, current)
        current = progress._root_performance_predecessor_source(path, current)
        assert progress.safe.identity(current) == row['after']
        assert progress._parent_progress_predecessor_source(path, current) == progress.read_blob(row['fixture'])
    assert progress._parent_progress_predecessor_source('unknown/path', b'unchanged') == b'unchanged'


@pytest.mark.parametrize('target', ['receipt', 'fixture', 'current', 'predecessor',
                                    'pass_a_fixture', 'pass_a_current'])
def test_ci_assertion_successor_rejects_changed_source_evidence(monkeypatch, target):
    from scripts import audit_phase_a_pass_a_tests_source_successor as progress
    path = 'tests/test_tests_shard_balance_successor.py'
    receipt = progress._ci_assertion_successor_receipt()
    row = receipt['source_forward'][path]
    selected = {'receipt': progress.CI_ASSERTION_RECEIPT,
                'fixture': row['fixture'], 'current': path,
                'predecessor': progress.CI_ASSERTION_PREDECESSOR['path'],
                'pass_a_fixture': receipt['pass_a_predecessor']['fixture'],
                'pass_a_current': receipt['pass_a_predecessor']['path']}[target]
    original = progress.read_blob
    def changed(candidate):
        raw = original(candidate)
        if candidate != selected:
            return raw
        return raw[:-1] + (b'X' if raw[-1:] != b'X' else b'Y')
    with monkeypatch.context() as scoped:
        scoped.setattr(progress, 'read_blob', changed)
        with pytest.raises(ValueError, match='CI assertion'):
            progress._authenticate_ci_assertion_successor()
    assert progress._authenticate_ci_assertion_successor()['authority_granted'] is False


def test_ci_assertion_successor_rejects_fixture_git_mode_drift(monkeypatch):
    from scripts import audit_phase_a_pass_a_tests_source_successor as progress
    path = progress._ci_assertion_successor_receipt()['source_forward'][
        'tests/test_tests_shard_balance_successor.py']['fixture']
    original = progress.safe.subprocess.check_output
    def changed(command, *args, **kwargs):
        raw = original(command, *args, **kwargs)
        if command[:4] == ['git', 'ls-tree', '-z', 'HEAD'] and command[-1] == path:
            return raw.replace(b'100644 blob ', b'100755 blob ', 1)
        return raw
    monkeypatch.setattr(progress.safe.subprocess, 'check_output', changed)
    with pytest.raises(ValueError, match='Git tree mode drift'):
        progress._authenticate_ci_assertion_successor()


def test_parent_progress_rejects_wrong_projection_order():
    from scripts import audit_phase_a_pass_a_tests_source_successor as progress
    path = 'scripts/audit_tests_shard_balance_successor.py'
    current = progress.read_blob(path)
    previous = progress._root_performance_predecessor_source(path, current)
    with pytest.raises(ValueError, match='parent progress caller source identity drift'):
        progress._parent_progress_predecessor_source(path, current)
    with pytest.raises(ValueError, match='root performance caller source drift'):
        progress._root_performance_predecessor_source(path, previous)


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
    import hashlib
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
    runner_temp = tmp_path / 'runner-temp'
    runner_temp.mkdir()
    env['RUNNER_TEMP'] = str(runner_temp)
    command = [sys.executable, '-m', 'pytest', '-q', 'test_parent.py']
    plain = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
    baseline = (tmp_path / 'result.json').read_bytes()
    instrumented = subprocess.run(command[:3] + ['-p', 'scripts.audit_phase_a_pass_a_tests_source_successor'] + command[3:],
                                  cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
    assert (tmp_path / 'result.json').read_bytes() == baseline
    assert 'ATHENA_PYTEST_PROGRESS' not in plain.stdout + plain.stderr
    records = [json.loads(line.split('ATHENA_PYTEST_PROGRESS ', 1)[1])
               for line in instrumented.stdout.splitlines() if line.startswith('ATHENA_PYTEST_PROGRESS ')]
    assert [r['event'] for r in records] == [
        'session_start', 'collection_inventory', 'start', 'setup', 'call',
        'teardown', 'finish', 'session_finish']
    assert len({r['pid'] for r in records}) == 1
    assert [r['nodeid_display'] for r in records[2:7]] == ['test_parent.py::test_child_replay'] * 5
    expected_key = hashlib.sha256(
        'test_parent.py::test_child_replay'.encode('utf-8', errors='surrogatepass')
    ).hexdigest()
    assert records[1]['node_keys'] == [expected_key]
    assert {record['nodeid_key_sha256'] for record in records[2:7]} == {expected_key}
    assert all(record['nodeid_key_algorithm'] == 'sha256-utf8-surrogatepass-v1'
               for record in records[2:7])
    jsonl_files = list((runner_temp / 'athena-pytest-progress').glob('*.jsonl'))
    assert len(jsonl_files) == 1
    assert audit.ROOT.resolve() not in jsonl_files[0].resolve().parents
    durable = [json.loads(line) for line in jsonl_files[0].read_text().splitlines()]
    assert [record['event'] for record in durable] == [record['event'] for record in records]
    assert all('tested_checkout_sha' in record['source']
               and 'pr_head_sha' in record['source'] for record in durable)


def test_parent_progress_redacts_failure_and_keeps_test_and_crash_locations_separate():
    from types import SimpleNamespace
    from scripts import audit_phase_a_pass_a_tests_source_successor as progress

    root = audit.ROOT
    crash = SimpleNamespace(
        message='AssertionError: token=secret-value at https://example.invalid/private',
        path=root / 'tests' / 'test_sample.py', lineno=27)
    frame = SimpleNamespace(reprfileloc=SimpleNamespace(
        path=root / 'scripts' / 'audit_sample.py', lineno=19))
    report = SimpleNamespace(
        longrepr=SimpleNamespace(reprcrash=crash,
                                 reprtraceback=SimpleNamespace(reprentries=[frame])),
        location=('tests/test_sample.py', 4, 'test_sample'))
    fields = progress._ParentNodeProgress._failure_details(report)
    assert fields['failure_category'] == 'AssertionError'
    assert 'secret-value' not in fields['failure_explanation']
    assert 'example.invalid/private' not in fields['failure_explanation']
    assert fields['crash_file'] == 'tests/test_sample.py'
    assert fields['crash_line'] == 27
    assert fields['test_file'] == 'tests/test_sample.py'
    assert fields['test_line_zero_based'] == 4
    assert fields['trace_frames'] == [{'file': 'scripts/audit_sample.py', 'line': 19}]


def test_parent_progress_redacts_quoted_credentials_in_serialized_outputs():
    import hashlib
    import io
    import json
    import os
    from types import SimpleNamespace
    from scripts import audit_phase_a_pass_a_tests_source_successor as progress

    message = (
        'AssertionError: expected configuration to remain offline; '
        '{"token": "canary-token-123", \'password\': \'canary-password-456\', '
        '"nested": {"api_key": "canary-api-789"}, '
        '"escaped": "{\\"secret\\": \\"canary-secret-000\\"}"}'
    )
    crash = SimpleNamespace(message=message, path='tests/test_sample.py', lineno=27)
    report = SimpleNamespace(
        longrepr=SimpleNamespace(reprcrash=crash, reprtraceback=None),
        location=('tests/test_sample.py', 4, 'test_sample'),
    )

    class CaptureJSONL:
        def __init__(self):
            self.records = []
            self.closed = False
        def write(self, value):
            self.records.append(value)
        def flush(self):
            return None
        def close(self):
            self.closed = True

    reporter = object.__new__(progress._ParentNodeProgress)
    reporter.pid = os.getpid()
    reporter.stream = io.StringIO()
    reporter.jsonl = CaptureJSONL()
    reporter.jsonl_bytes = 0
    reporter.jsonl_limit = 8192
    reporter.run_identity = {'worker': 'parent'}
    reporter.source_identity = {'tested_checkout_sha': 'a' * 40}
    fields = reporter._failure_details(report)
    case_a = "tests/test_sample.py::test_sample[{'token': 'canary-node-321'}]"
    case_b = "tests/test_sample.py::test_sample[{'token': 'canary-node-654'}]"
    long_prefix = 'tests/test_sample.py::test_long_case[' + ('x' * 700)
    long_a, long_b = long_prefix + 'alpha]', long_prefix + 'beta]'
    nodeids = [case_a, case_b, long_a, long_b]
    expected_keys = [
        hashlib.sha256(nodeid.encode('utf-8', errors='surrogatepass')).hexdigest()
        for nodeid in nodeids
    ]
    reporter.pytest_collection_finish(SimpleNamespace(
        items=[SimpleNamespace(nodeid=nodeid) for nodeid in nodeids]))
    for event in ('start', 'setup', 'call', 'teardown', 'finish'):
        reporter._emit(event, case_a, **(fields if event == 'call' else {}))
    reporter._emit('call', case_b)
    reporter._emit('call', long_a)
    reporter._emit('call', long_b)
    header_cases = (
        ('Authorization: Basic YXRoZW5hOmNhbmFyeS1zZWNyZXQ=',
         ('YXRoZW5hOmNhbmFyeS1zZWNyZXQ=',)),
        ('Proxy-Authorization: Digest username="proxy-user-canary",\n'
         '  response="proxy-response-canary"',
         ('proxy-user-canary', 'proxy-response-canary')),
        ('Cookie: first=first-cookie-canary; session=second-cookie-canary',
         ('first-cookie-canary', 'second-cookie-canary')),
        ('Set-Cookie: session=set-cookie-canary; Path=/',
         ('set-cookie-canary',)),
    )
    for header, _canaries in header_cases:
        header_crash = SimpleNamespace(
            message='ValueError: request rejected; ' + header,
            path='tests/test_sample.py', lineno=27,
        )
        reporter.pytest_runtest_logreport(SimpleNamespace(
            when='call', outcome='failed', duration=0.1, failed=True,
            nodeid='tests/test_sample.py::test_header',
            longrepr=SimpleNamespace(reprcrash=header_crash),
        ))
    field_canaries = progress._ParentNodeProgress._redact_text(
        'token: "canary-token-plain" password = \'canary-password-plain\' '
        'api_key: \\"canary-api-plain\\"',
        512,
    )
    escaped_canary = progress._ParentNodeProgress._redact_text(
        r'token: \\"canary-escaped-222\\"', 512)

    stdout_jsonl = [
        line.split('ATHENA_PYTEST_PROGRESS ', 1)[1]
        for line in reporter.stream.getvalue().splitlines()
        if line.startswith('ATHENA_PYTEST_PROGRESS ')
    ]
    stdout_text = '\n'.join(stdout_jsonl)
    stdout_events = [json.loads(line) for line in stdout_jsonl]
    jsonl_text = ''.join(reporter.jsonl.records)
    jsonl_events = [json.loads(line) for line in reporter.jsonl.records]
    assert len(reporter.jsonl.records) == len(stdout_events)
    assert jsonl_events == stdout_events
    header_events = [event for event in stdout_events
                     if event['nodeid_display'] == 'tests/test_sample.py::test_header']
    assert len(header_events) == len(header_cases)
    for event, (_header, canaries) in zip(header_events, header_cases):
        assert event['failure_category'] == 'ValueError'
        assert event['failure_explanation'].startswith('ValueError: request rejected; ')
        assert event['failure_explanation'].endswith('<redacted>')
        for canary in canaries:
            assert canary not in stdout_text
            assert canary not in jsonl_text
    assert 'remain offline' in fields['failure_explanation']
    collection = [event for event in stdout_events if event['event'] == 'collection_inventory']
    assert len(collection) == 1
    assert collection[0]['collected_node_count'] == len(nodeids)
    assert collection[0]['node_keys'] == expected_keys
    assert collection[0]['node_key_algorithm'] == 'sha256-utf8-surrogatepass-v1'
    assert collection[0]['collected_node_keys_sha256'] == hashlib.sha256(
        '\n'.join(expected_keys).encode('ascii')).hexdigest()
    case_a_events = [event for event in stdout_events
                     if event.get('nodeid_key_sha256') == expected_keys[0]]
    assert [event['event'] for event in case_a_events] == [
        'start', 'setup', 'call', 'teardown', 'finish']
    assert {event['nodeid_key_sha256'] for event in case_a_events} == {expected_keys[0]}
    assert expected_keys[0] != expected_keys[1]
    assert expected_keys[2] != expected_keys[3]
    assert next(event['nodeid_display'] for event in stdout_events
                if event.get('nodeid_key_sha256') == expected_keys[0]) == next(
                    event['nodeid_display'] for event in stdout_events
                    if event.get('nodeid_key_sha256') == expected_keys[1])
    assert next(event['nodeid_display'] for event in stdout_events
                if event.get('nodeid_key_sha256') == expected_keys[2]) == next(
                    event['nodeid_display'] for event in stdout_events
                    if event.get('nodeid_key_sha256') == expected_keys[3])
    for canary in (
        'canary-token-123', 'canary-password-456', 'canary-api-789',
        'canary-secret-000', 'canary-node-321', 'canary-token-plain',
        'canary-password-plain', 'canary-api-plain', 'canary-escaped-222',
    ):
        assert canary not in stdout_text
        assert canary not in jsonl_text
        assert canary not in field_canaries
        assert canary not in escaped_canary
    assert 'canary-token-plain' not in field_canaries
    assert 'canary-password-plain' not in field_canaries
    assert 'canary-api-plain' not in field_canaries
    assert 'canary-escaped-222' not in escaped_canary


def test_parent_progress_jsonl_failure_keeps_stdout_fallback():
    import io
    import os
    from scripts import audit_phase_a_pass_a_tests_source_successor as progress

    class BrokenJSONL:
        def __init__(self):
            self.write_calls = 0
            self.closed = False
        def write(self, value):
            self.write_calls += 1
            raise OSError('diagnostic disk unavailable')
        def close(self):
            self.closed = True

    reporter = object.__new__(progress._ParentNodeProgress)
    reporter.pid = os.getpid()
    reporter.stream = io.StringIO()
    writer = BrokenJSONL()
    reporter.jsonl = writer
    reporter.jsonl_bytes = 0
    reporter.jsonl_limit = 8192
    reporter.run_identity = {'worker': 'parent'}
    reporter.source_identity = {'tested_checkout_sha': 'a' * 40}
    reporter._emit('finish', 'test_sample.py::test_case')
    assert 'ATHENA_PYTEST_PROGRESS ' in reporter.stream.getvalue()
    assert writer.write_calls == 1
    assert writer.closed
    assert reporter.jsonl is None


@pytest.mark.parametrize('runner_temp_kind', ['checkout', 'symlink-to-checkout'])
def test_parent_progress_rejects_checkout_destination_before_creation(
        monkeypatch, tmp_path, runner_temp_kind):
    import os
    from scripts import audit_phase_a_pass_a_tests_source_successor as progress

    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    if runner_temp_kind == 'checkout':
        runner_temp = checkout
    else:
        runner_temp = tmp_path / 'runner-temp-link'
        runner_temp.symlink_to(checkout, target_is_directory=True)
    report_dir = checkout / 'athena-pytest-progress'
    assert not report_dir.exists()

    monkeypatch.setattr(progress, 'ROOT', checkout)
    monkeypatch.setenv('RUNNER_TEMP', str(runner_temp))
    reporter = object.__new__(progress._ParentNodeProgress)
    reporter.run_identity = {'worker': 'parent'}
    reporter.jsonl = None
    reporter._open_jsonl(os)

    assert reporter.jsonl is None
    assert not report_dir.exists()
