"""Exact historical reachability, with current source qualification retained."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import stat

import pytest

from scripts import audit_phase_a_pass_a_tests_source_successor as forward
from scripts import audit_tests_shard_balance_successor as shards


def test_pass_a_inventory_matches_frozen_source_and_edges():
    from scripts import audit_core_01d_authority_reachability_review_a as review
    frozen = review.authenticate_inventory()
    assert frozen['canonical_sha256'] == review.INVENTORY_SHA
    assert review.source_bytes(shards.WORKFLOW) == forward.read_blob(shards.FIXTURE)
    assert shards.identity(forward.read_blob(shards.WORKFLOW)) == shards.AFTER
    # Metadata/caller discovery still reads actual YAML: no projection needed.
    assert review.workflow_metadata(shards.WORKFLOW) == frozen['workflow_metadata'][shards.WORKFLOW]
    assert review.discover(shards.WORKFLOW) == frozen['static_discovery_edges'][shards.WORKFLOW]


def test_pass_a_source_successor_is_exact_and_does_not_map_unknown_paths():
    value = forward.authenticate_core()
    assert value['authority_granted'] is value['workflow_changed'] is False
    for path, row in forward.EDGES.items():
        assert forward.predecessor_source(path, forward.read_blob(path)) == forward.read_blob(row['fixture'])
    assert forward.predecessor_source('domain/unrelated.py', b'unrelated') == b'unrelated'


@pytest.mark.parametrize('which', ['current', 'predecessor', 'receipt'])
def test_pass_a_source_successor_rejects_changed_evidence(monkeypatch, which):
    row = forward.EDGES[forward.SOURCE]
    target = {'current': forward.SOURCE, 'predecessor': row['fixture'], 'receipt': forward.RECEIPT}[which]
    original = forward.read_blob
    monkeypatch.setattr(forward, 'read_blob', lambda p: original(p) + (b' ' if p == target else b''))
    with pytest.raises(ValueError, match='source|receipt|predecessor'):
        forward.authenticate_core()


@pytest.mark.parametrize('which', ['workflow', 'fixture', 'frozen'])
def test_pass_a_historical_workflow_rejects_tampered_bytes(monkeypatch, which):
    targets = {'workflow': shards.WORKFLOW, 'fixture': shards.FIXTURE,
               'frozen': 'tests/fixtures/core_01d/authority-reachability-pass-a-source-inventory-v1.json'}
    original = forward.read_blob
    monkeypatch.setattr(forward, 'read_blob', lambda p: original(p) + (b' ' if p == targets[which] else b''))
    with pytest.raises(ValueError, match='workflow|predecessor|inventory'):
        forward.historical_workflow_source()


@pytest.mark.parametrize('which', ['source', 'generation', 'missing'])
def test_pass_a_requires_current_a2_before_historical_substitution(monkeypatch, which):
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    value = deepcopy(a2.authenticate_inventory())
    if which == 'generation':
        value['generation'] = 357
    else:
        for row in value['source_identities']:
            if row['path'] == forward.SOURCE:
                row['lf_source_sha256'] = '0' * 64
        if which == 'missing':
            value['source_identities'] = [r for r in value['source_identities'] if r['path'] != forward.SOURCE]
    monkeypatch.setattr(a2, 'authenticate_inventory', lambda: value)
    with pytest.raises(ValueError, match='latest A2'):
        forward.historical_workflow_source()


def test_pass_a_has_no_caller_selected_tree_and_keeps_live_fence():
    from scripts import audit_core_01d_sportybet_current_trigger_authority_b4 as b4
    with pytest.raises(TypeError):
        forward.historical_workflow_source(shards.BEFORE_TREE)
    for stale in (shards.BEFORE_TREE, 'f' * 40):
        with pytest.raises(AssertionError, match='not for the checked-out tree'):
            b4.project_b4_workflow_tree(stale)


@pytest.mark.parametrize('kind', ['symlink', 'reparse', 'hardlink', 'ancestor'])
def test_pass_a_fixture_rejects_linked_evidence_before_read(monkeypatch, kind):
    target = forward.ROOT / forward.EDGES[forward.SOURCE]['fixture']
    affected = target.parent if kind == 'ancestor' else target
    original = Path.lstat
    def linked(candidate):
        status = original(candidate)
        if candidate == target and kind == 'ancestor':
            raise AssertionError('followed linked ancestor')
        if candidate != affected:
            return status
        return SimpleNamespace(st_mode=(stat.S_IFLNK | 0o777) if kind in {'symlink', 'ancestor'} else status.st_mode,
                               st_file_attributes=0x400 if kind == 'reparse' else 0,
                               st_nlink=2 if kind == 'hardlink' else 1)
    monkeypatch.setattr(Path, 'lstat', linked)
    with pytest.raises(ValueError, match='linked|nonregular'):
        forward.read_blob(forward.EDGES[forward.SOURCE]['fixture'])


@pytest.mark.parametrize('mode', ['100755', '120000', '160000'])
def test_pass_a_fixture_rejects_wrong_mode(monkeypatch, mode):
    safe = forward.safe
    fixture = forward.EDGES[forward.SOURCE]['fixture']
    forward.read_blob(fixture)  # Positive control and warm-cache mode check.
    original = safe.subprocess.check_output
    intercepted = []
    def changed(args, **kwargs):
        raw = original(args, **kwargs)
        if args[:2] == ['git', 'ls-tree'] and args[-2:] == ['--', fixture]:
            before, separator, rest = raw.partition(b' ')
            assert before == b'100644' and separator == b' '
            intercepted.append(True)
            return mode.encode() + separator + rest
        return raw
    monkeypatch.setattr(safe.subprocess, 'check_output', changed)
    with pytest.raises(ValueError, match='mode'):
        forward.read_blob(fixture)
    assert intercepted == [True]


def test_pass_a_rejects_changed_discovery_line_or_frozen_inventory(monkeypatch):
    from scripts import audit_core_01d_authority_reachability_review_a as review
    expected = review.read_json(review.INVENTORY_PATH)
    changed = deepcopy(expected)
    changed['static_discovery_edges'][shards.WORKFLOW][6]['line'] += 1
    monkeypatch.setattr(review, 'build_inventory', lambda: changed)
    with pytest.raises(AssertionError, match='discovered edges drifted'):
        review.authenticate_inventory()
    changed = deepcopy(expected)
    changed['canonical_sha256'] = '0' * 64
    original = review.read_json
    monkeypatch.setattr(review, 'read_json', lambda p: changed if p == review.INVENTORY_PATH else original(p))
    with pytest.raises(AssertionError, match='inventory seal drift'):
        review.authenticate_inventory()


@pytest.fixture
def blob_reuse_checkout(tmp_path, monkeypatch):
 import subprocess
 from scripts import audit_phase_a_b4_test_source_successor as safe
 def git(*args):
  return subprocess.check_output(['git', *args], cwd=tmp_path)
 git('init', '-q')
 git('config', 'user.name', 'Offline Fixture')
 git('config', 'user.email', 'offline@example.invalid')
 git('config', 'core.autocrlf', 'false')
 file = tmp_path / 'proof.txt'
 file.write_bytes(b'reviewed\n')
 git('add', 'proof.txt')
 git('commit', '-q', '-m', 'Deterministic offline source fixture')
 monkeypatch.setattr(safe, 'ROOT', tmp_path)
 safe._BLOB_PAYLOADS.clear()
 yield safe, file, git
 safe._BLOB_PAYLOADS.clear()


def test_blob_reuse_reads_current_worktree_after_warm_cache(blob_reuse_checkout):
 import os
 safe, file, _git = blob_reuse_checkout
 assert safe.read_blob('proof.txt') == safe.read_blob('proof.txt') == b'reviewed\n'
 state = file.stat()
 file.write_bytes(b'tampered\n')
 os.utime(file, ns=(state.st_atime_ns, state.st_mtime_ns))
 with pytest.raises(ValueError, match='filtered worktree identity drift'):
  safe.read_blob('proof.txt')


def test_blob_reuse_preserves_cold_reader_and_rejects_reader_replacement(blob_reuse_checkout, monkeypatch):
 from runtime import source_identity
 safe, _file, _git = blob_reuse_checkout
 original = source_identity.read_tracked_head_blob
 calls = []
 def counted(*args, **kwargs):
  calls.append(args)
  return original(*args, **kwargs)
 monkeypatch.setattr(source_identity, 'read_tracked_head_blob', counted)
 assert safe.read_blob('proof.txt') == safe.read_blob('proof.txt') == b'reviewed\n'
 assert len(calls) == 1
 def denied(*args, **kwargs):
  raise ValueError('replacement reader must run')
 monkeypatch.setattr(source_identity, 'read_tracked_head_blob', denied)
 with pytest.raises(ValueError, match='replacement reader must run'):
  safe.read_blob('proof.txt')


def test_blob_reuse_rechecks_git_mode(blob_reuse_checkout, monkeypatch):
 safe, _file, _git = blob_reuse_checkout
 safe.read_blob('proof.txt')
 original = safe.subprocess.check_output
 def executable(args, **kwargs):
  raw = original(args, **kwargs)
  return raw.replace(b'100644 blob ', b'100755 blob ') if args[:2] == ['git', 'ls-tree'] else raw
 monkeypatch.setattr(safe.subprocess, 'check_output', executable)
 with pytest.raises(ValueError, match='mode drift'):
  safe.read_blob('proof.txt')


def test_blob_reuse_preserves_crlf_and_observes_filter_change(blob_reuse_checkout):
 safe, file, git = blob_reuse_checkout
 assert safe.read_blob('proof.txt') == b'reviewed\n'
 git('config', 'core.autocrlf', 'true')
 file.write_bytes(b'reviewed\r\n')
 assert safe.read_blob('proof.txt') == b'reviewed\n'
 (file.parent / '.gitattributes').write_bytes(b'proof.txt -text\n')
 with pytest.raises(ValueError, match='filtered worktree identity drift'):
  safe.read_blob('proof.txt')


def test_blob_reuse_observes_new_head_and_rejects_corrupted_cache(blob_reuse_checkout):
 safe, file, git = blob_reuse_checkout
 assert safe.read_blob('proof.txt') == b'reviewed\n'
 file.write_bytes(b'successor\n')
 git('add', 'proof.txt')
 git('commit', '-q', '-m', 'Offline exact source successor')
 assert safe.read_blob('proof.txt') == b'successor\n'
 for key in list(safe._BLOB_PAYLOADS):
  safe._BLOB_PAYLOADS[key] = b'forged'
 with pytest.raises(ValueError, match='cached blob payload identity drift'):
  safe.read_blob('proof.txt')


@pytest.mark.parametrize('which', ['receipt', 'source', 'fixture', 'test', 'test_fixture', 'inventory'])
def test_blob_reuse_source_successor_rejects_changed_evidence(monkeypatch, which):
 value = forward._blob_reuse_receipt()
 source = 'scripts/audit_phase_a_b4_test_source_successor.py'
 test = 'tests/test_phase_a_pass_a_tests_source_successor.py'
 target = {'receipt': forward.BLOB_REUSE_RECEIPT, 'source': source,
           'fixture': value['source_forward'][source]['fixture'], 'test': test,
           'test_fixture': value['source_forward'][test]['fixture'],
           'inventory': value['predecessor_inventory']['path']}[which]
 original = forward.read_blob
 monkeypatch.setattr(forward, 'read_blob', lambda p: original(p) + (b' ' if p == target else b''))
 with pytest.raises(ValueError, match='blob reuse'):
  forward._blob_reuse_receipt()


@pytest.mark.parametrize('which', ['receipt', 'b4_current', 'b4_fixture', 'pass_a_current', 'pass_a_fixture', 'reader_current', 'reader_fixture', 'inventory'])
def test_git_mode_regression_successor_rejects_changed_evidence(monkeypatch, which):
 value = forward._git_mode_regression_receipt()
 b4 = 'tests/test_core_01d_sportybet_current_trigger_authority_b4.py'
 target = {'receipt': forward.GIT_MODE_REGRESSION_RECEIPT,
           'b4_current': b4, 'b4_fixture': value['source_forward'][b4]['fixture'],
           'pass_a_current': forward.TEST, 'pass_a_fixture': value['source_forward'][forward.TEST]['fixture'],
           'reader_current': 'scripts/audit_phase_a_b4_test_source_successor.py',
           'reader_fixture': value['source_forward']['scripts/audit_phase_a_b4_test_source_successor.py']['fixture'],
           'inventory': value['predecessor_inventory']['path']}[which]
 original = forward.read_blob
 monkeypatch.setattr(forward, 'read_blob', lambda p: original(p) + (b' ' if p == target else b''))
 with pytest.raises(ValueError, match='Git-mode regression'):
  forward._git_mode_regression_receipt()


@pytest.mark.parametrize('which', ['generation', 'missing', 'forged', 'predecessor'])
def test_git_mode_current_qualification_rejects_unqualified_a2(monkeypatch, which):
 from scripts import audit_core_01d_ci_offline_transport_boundary as a2
 safe = forward.safe
 latest = deepcopy(a2.authenticate_inventory())
 if which == 'generation':
  latest['generation'] = 371
 elif which == 'missing':
  latest['source_identities'] = [r for r in latest['source_identities'] if r['path'] != safe.SOURCE]
 else:
  for row in latest['source_identities']:
   if row['path'] == safe.SOURCE:
    row['lf_source_sha256'] = safe.AFTER['source_sha256'] if which == 'predecessor' else '0' * 64
 monkeypatch.setattr(a2, 'authenticate_inventory', lambda: latest)
 with pytest.raises(ValueError, match='current source is not authenticated by latest A2'):
  safe.authenticate()
