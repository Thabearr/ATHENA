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


def test_root_performance_json_snapshot_returns_fresh_values_and_observes_tamper(tmp_path, monkeypatch):
 import os
 from scripts import audit_core_01d_ci_offline_transport_boundary as a2
 value=a2.seal({'values':[1,True,1.0,None],'nested':{'source':'reviewed'}})
 raw=a2.canonical(value);target=tmp_path/'receipt.json';target.write_bytes(raw)
 monkeypatch.setattr(a2,'ROOT',tmp_path)
 first=a2.read('receipt.json');first['values'].append('poison')
 second=a2.read('receipt.json')
 assert second==value and second is not first
 assert [type(v) for v in second['values']]==[int,bool,float,type(None)]
 state=target.stat();target.write_bytes(raw.replace(b'reviewed',b'tampered'))
 os.utime(target,ns=(state.st_atime_ns,state.st_mtime_ns))
 with pytest.raises(AssertionError,match='self-hash mismatch'):
  a2.read('receipt.json')
 target.write_bytes(raw)
 assert a2.read('receipt.json')==value
 def denied(*args,**kwargs):raise AssertionError('replacement validator must run')
 monkeypatch.setattr(a2,'_authenticated_json_bytes',denied)
 with pytest.raises(AssertionError,match='replacement validator must run'):
  a2.read('receipt.json')


@pytest.mark.parametrize('fault',['gap','malformed_name','leading_zero','predecessor','schema','early','trailing'])
def test_root_performance_warm_chain_rejects_fresh_invalid_inputs(tmp_path,monkeypatch,fault):
 from scripts import audit_core_01d_ci_offline_transport_boundary as a2
 originals={i:(a2.ROOT/a2.inventory_generation_path(i)).read_bytes() for i in (1,2,3)}
 for i,raw in originals.items():
  p=tmp_path/a2.inventory_generation_path(i);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
 monkeypatch.setattr(a2,'ROOT',tmp_path)
 chain=a2.load_inventory_generations();assert len(chain)==3
 target=tmp_path/a2.inventory_generation_path(2)
 if fault=='gap':target.unlink()
 elif fault=='malformed_name':(target.parent/(a2.INVENTORY_PREFIX+'bad.json')).write_bytes(b'{}')
 elif fault=='leading_zero':(target.parent/(a2.INVENTORY_PREFIX+'v02.json')).write_bytes(originals[2])
 elif fault=='trailing':target.write_bytes(originals[2]+b' ')
 else:
  import json
  number=1 if fault=='early' else 2;target=tmp_path/a2.inventory_generation_path(number)
  value=json.loads(target.read_bytes())
  if fault=='predecessor':value['predecessor_inventory']['canonical_sha256']='0'*64
  elif fault=='schema':value['schema_version']=999
  else:value['base_main_sha']='0'*40
  target.write_bytes(a2.canonical(a2.seal(value)))
 with pytest.raises(AssertionError):a2.load_inventory_generations()


@pytest.mark.parametrize('bad',[b'',b'not-a-root-proof\n',b'../\n'+b'a'*40+b'\n',b'\n'+b'z'*40+b'\n',True])
def test_root_performance_combined_fence_rejects_bad_root_or_head(blob_reuse_checkout,monkeypatch,bad):
 from runtime import source_identity
 safe,_file,_git=blob_reuse_checkout
 assert safe.read_blob('proof.txt')==b'reviewed\n'
 original=source_identity._run_git
 def malformed(root,*args):
  if args==('rev-parse','--show-cdup','--verify','HEAD^{commit}'):return bad
  return original(root,*args)
 monkeypatch.setattr(source_identity,'_run_git',malformed)
 with pytest.raises(ValueError):safe.read_blob('proof.txt')


def test_root_performance_large_working_set_keeps_every_fresh_filter_check(blob_reuse_checkout,monkeypatch):
 from runtime import source_identity
 safe,file,git=blob_reuse_checkout
 names=[f'proof-{i:03}.txt' for i in range(96)]
 for i,name in enumerate(names):(file.parent/name).write_text(f'reviewed {i:03}\n')
 git('add','.');git('commit','-q','-m','Offline distinct immutable working set')
 original=source_identity.read_tracked_head_blob;full=[];filtered=[]
 def counted(*args,**kwargs):full.append(args);return original(*args,**kwargs)
 original_ascii=source_identity._ascii_git_output
 def hash_counted(root,*args):
  if args and args[0]=='hash-object':filtered.append(args)
  return original_ascii(root,*args)
 monkeypatch.setattr(source_identity,'read_tracked_head_blob',counted)
 monkeypatch.setattr(source_identity,'_ascii_git_output',hash_counted)
 for _ in range(2):
  for i,name in enumerate(names):assert safe.read_blob(name)==f'reviewed {i:03}\n'.encode()
 assert len(full)==96 and len(filtered)==192
 assert len(safe._BLOB_PAYLOADS)<=safe._BLOB_MAX_ITEMS
 assert sum(map(len,safe._BLOB_PAYLOADS.values()))<=safe._BLOB_MAX_BYTES


def test_root_performance_payload_cache_obeys_count_and_byte_budgets(blob_reuse_checkout,monkeypatch):
 safe,file,git=blob_reuse_checkout
 for i in range(5):(file.parent/f'item-{i}.txt').write_bytes(bytes([65+i])*8)
 (file.parent/'large.txt').write_bytes(b'X'*256)
 git('add','.');git('commit','-q','-m','Offline cache budget fixtures')
 monkeypatch.setattr(safe,'_BLOB_MAX_ITEMS',3);monkeypatch.setattr(safe,'_BLOB_MAX_BYTES',24)
 for i in range(5):
  safe.read_blob(f'item-{i}.txt')
  assert len(safe._BLOB_PAYLOADS)<=3 and sum(map(len,safe._BLOB_PAYLOADS.values()))<=24
 assert safe.read_blob('large.txt')==b'X'*256
 assert all(len(raw)<=24 for raw in safe._BLOB_PAYLOADS.values())


@pytest.mark.parametrize('which',['receipt','before','after','extra','predecessor'])
def test_root_performance_source_forward_rejects_tampering(monkeypatch,which):
 import json
 value=forward._root_performance_receipt()
 assert forward._root_performance_receipt()==value
 row=value['source_forward']['scripts/audit_phase_a_b4_test_source_successor.py']
 path={'receipt':forward.ROOT_PERFORMANCE_RECEIPT,'before':row['fixture'],
       'after':'scripts/audit_phase_a_b4_test_source_successor.py',
       'extra':forward.ROOT_PERFORMANCE_RECEIPT,'predecessor':forward.ROOT_PERFORMANCE_PREDECESSOR['path']}[which]
 original=forward.read_blob
 def altered(p):
  raw=original(p)
  if p!=path:return raw
  if which=='extra':
   changed=json.loads(raw);changed['extra_authority']=True
   changed['canonical_sha256']=forward.safe.canonical_digest(changed)
   return forward.safe.canonical(changed)
  return raw+b' '
 monkeypatch.setattr(forward,'read_blob',altered)
 with pytest.raises(ValueError):forward._authenticate_root_performance()


def test_root_performance_rechecks_scope_after_warm_immutable_parse(monkeypatch):
 assert forward._root_performance_receipt()['authority_granted'] is False
 altered=dict(forward.ROOT_PERFORMANCE_PREDECESSOR,generation=0)
 monkeypatch.setattr(forward,'ROOT_PERFORMANCE_PREDECESSOR',altered)
 with pytest.raises(ValueError,match='scope drift'):
  forward._root_performance_receipt()


def test_root_performance_scope_is_local_and_checks_current_bytes_at_return(blob_reuse_checkout):
 import os
 safe,file,_git=blob_reuse_checkout
 scope=forward._SourceReadScope(forward.read_blob)
 assert scope.read('proof.txt')==b'reviewed\n'
 state=file.stat();file.write_bytes(b'tampered\n');os.utime(file,ns=(state.st_atime_ns,state.st_mtime_ns))
 # This is an uncommitted input snapshot, never an authorization result.
 assert scope.read('proof.txt')==b'reviewed\n'
 with pytest.raises(ValueError,match='filtered worktree identity drift'):scope.verify()
 file.write_bytes(b'reviewed\n')
 fresh=forward._SourceReadScope(forward.read_blob)
 assert fresh.read('proof.txt')==b'reviewed\n';fresh.verify()


def test_root_performance_scope_preserves_filters_and_fences_head(blob_reuse_checkout):
 safe,file,git=blob_reuse_checkout
 scope=forward._SourceReadScope(forward.read_blob);scope.read('proof.txt')
 git('config','core.autocrlf','true');file.write_bytes(b'reviewed\r\n');scope.verify()
 (file.parent/'.gitattributes').write_bytes(b'proof.txt -text\n')
 with pytest.raises(ValueError,match='filtered worktree identity drift'):scope.verify()
 (file.parent/'.gitattributes').unlink()
 file.write_bytes(b'successor\n');git('add','proof.txt');git('commit','-q','-m','Offline scoped HEAD successor')
 with pytest.raises(ValueError,match='HEAD changed'):scope.verify()
 fresh=forward._SourceReadScope(forward.read_blob);assert fresh.read('proof.txt')==b'successor\n';fresh.verify()


@pytest.mark.parametrize('which',['public_reader','safe_reader','runtime_reader','root'])
def test_root_performance_scope_rejects_changed_reader_bindings(blob_reuse_checkout,monkeypatch,which):
 from runtime import source_identity
 safe,file,_git=blob_reuse_checkout
 scope=forward._SourceReadScope(forward.read_blob);scope.read('proof.txt')
 if which=='public_reader':monkeypatch.setattr(forward,'read_blob',lambda path:b'reviewed\n')
 elif which=='safe_reader':monkeypatch.setattr(safe,'read_blob',lambda path:b'reviewed\n')
 elif which=='runtime_reader':monkeypatch.setattr(source_identity,'read_tracked_head_blob',lambda *a,**kw:None)
 else:monkeypatch.setattr(safe,'ROOT',file.parent/'different')
 with pytest.raises(ValueError,match='reader changed'):scope.verify()


@pytest.mark.parametrize('which',['symlink','reparse','hardlink','executable_mode'])
def test_root_performance_scope_rejects_synthetic_link_and_mode_flags(blob_reuse_checkout,monkeypatch,which):
 import stat
 from pathlib import Path
 from types import SimpleNamespace
 safe,file,_git=blob_reuse_checkout
 scope=forward._SourceReadScope(forward.read_blob);scope.read('proof.txt')
 if which=='executable_mode':
  original=safe.subprocess.check_output
  def executable(args,**kwargs):
   value=original(args,**kwargs)
   return value.replace(b'100644 blob ',b'100755 blob ') if args[:2]==['git','ls-tree'] else value
  monkeypatch.setattr(safe.subprocess,'check_output',executable)
 else:
  original=Path.lstat
  def linked(path,*args,**kwargs):
   value=original(path,*args,**kwargs)
   if path!=file:return value
   return SimpleNamespace(st_mode=(stat.S_IFLNK|0o777) if which=='symlink' else value.st_mode,
                          st_file_attributes=0x400 if which=='reparse' else 0,
                          st_nlink=2 if which=='hardlink' else 1)
  monkeypatch.setattr(Path,'lstat',linked)
 with pytest.raises(ValueError,match='source'):scope.verify()
