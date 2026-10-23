"""Exactly-once partition and path-exact, fail-closed workflow evolution."""
from __future__ import annotations

from collections import Counter
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
    assert 'tests/test_core_01d_checkpoint_e_completion_v10.py' in groups[5]
    assert 'tests/test_lg_a_worker_launch_failure_remediation.py' in groups[1]
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
