"""Historical V1 preserved; partial overlays never manufacture completion."""
from copy import deepcopy
import pytest
from scripts import audit_core_01d_checkpoint_e_completion_v2 as current
from scripts import audit_core_01d_authority_reachability_review_a as review

@pytest.fixture(scope='module')
def receipt():return current.build_receipt()

def test_v1_and_all_nineteen_criteria_are_independently_authenticated(receipt):
 old=current.historical_v1_receipt()
 assert old['canonical_sha256']==review.COMPLETION_V1_SHA
 assert old['checkpoint_e_status']==old['p4_4_status']=='INCOMPLETE'
 assert len(receipt['checkpoint_criteria'])==19 and sum(receipt['checkpoint_criteria'].values())==17
 assert receipt['checkpoint_criteria']==old['checkpoint_criteria']
 assert receipt['checkpoint_e_status']==receipt['p4_4_status']=='INCOMPLETE'
 assert receipt['resolved_pass_a_surface_count']==18 and receipt['unresolved_pass_a_surface_count']==3
 assert receipt['remaining_unreviewed_surface_count']==35
 assert receipt['out_of_scope_unreviewed_surface_count']==32

def test_inherited_rows_are_exact_and_no_resolved_key_is_duplicated(receipt):
 old=review.read_json(review.COMPLETION_V1)
 resolved={(r['workflow_path'],r['trigger_kind']) for r in receipt['reviewed_authority_rows']}
 remaining=receipt['unreviewed_authority_surfaces']
 assert remaining==[r for r in old['unreviewed_authority_surfaces'] if (r['workflow_path'],r['trigger_kind']) not in resolved]
 assert not resolved & {(r['workflow_path'],r['trigger_kind']) for r in remaining}
 assert {k for k in resolved if k not in review.KEYS}==set()

@pytest.mark.parametrize('mutation',['complete','no_unknown','drop_out_of_scope','add_review','duplicate','true_11','true_14','tree','ledger','transition15','retire','semantic','side_effect'])
def test_resealed_completion_or_scope_falsehoods_fail(receipt,mutation):
 value=deepcopy(receipt)
 if mutation=='complete':value.update(checkpoint_e_status='COMPLETE',p4_4_status='COMPLETE',remaining_blocker_ids=[])
 elif mutation=='no_unknown':value.update(unreviewed_authority_surfaces=[],remaining_unreviewed_surface_count=0)
 elif mutation=='drop_out_of_scope':value['unreviewed_authority_surfaces'].pop()
 elif mutation=='add_review':value['reviewed_authority_rows'][0]['workflow_path']=review.workflow_path('athena-run')
 elif mutation=='duplicate':value['unreviewed_authority_surfaces'].append(deepcopy(value['reviewed_authority_rows'][0]))
 elif mutation in ('true_11','true_14'):value['checkpoint_criteria'][current.v1.CRITERIA[10 if mutation=='true_11' else 13]]=True
 elif mutation=='tree':value['workflow_tree_after_sha1']='0'*40
 elif mutation=='ledger':value['evolution_ledger_after_sha256']='0'*64
 elif mutation=='transition15':value['transition_count']=15
 elif mutation=='retire':value['retirement_authorized']=True
 elif mutation=='semantic':value['protected_semantic_delta']['model']=1
 else:value['actions']['workflow_dispatch']=1
 review.seal(value)
 with pytest.raises(AssertionError):current.validate_receipt(value,receipt)

def test_current_master_authenticates_v10_and_preserves_historical_v2(receipt):
 from scripts import audit_checkpoint_e_workflows as master
 from scripts import audit_core_01d_checkpoint_e_completion_v10 as current_v10
 value=master.audit()
 assert value['current_completion_receipt_sha256']==current_v10.audit()['receipt_sha256']
 assert value['historical_completion_v2_receipt_sha256']==receipt['canonical_sha256']
 assert value['historical_completion_v1_receipt_sha256']==review.COMPLETION_V1_SHA
 assert value['remaining_unreviewed_surface_count']==0
 assert value['checkpoint_e']==value['p4_4']=='COMPLETE'
 assert value['blockers']==[]
 assert receipt['remaining_blocker_ids']

def test_unapproved_runtime_change_cannot_hide_in_historical_projection(monkeypatch):
 original=review.retention.v4.v3._git
 def changed(*args):
  raw=original(*args)
  if args==('ls-tree','-r','HEAD'):return raw+b'100644 blob 0000000000000000000000000000000000000000\tdomain/unapproved-runtime.py\n'
  return raw
 monkeypatch.setattr(review.retention.v4.v3,'_git',changed)
 with pytest.raises(AssertionError,match='outside bounded evidence scope'):current.historical_v1_receipt()

def test_e3_pass_audit_predecessors_are_exact_and_fixture_tamper_fails_closed(monkeypatch):
 from pathlib import Path
 from scripts import audit_core_01d_ci_offline_transport_boundary as a2
 latest=a2.authenticate_inventory()
 expected={path:identity[1] for path,identity in current.PASS_A_E3_COMPAT_SOURCE_PREDECESSORS.items()}
 assert current.authenticate_pass_a_e3_compat_predecessors(a2,latest)==expected
 path,identity=next(iter(current.PASS_A_E3_COMPAT_SOURCE_PREDECESSORS.items()))
 target=(current.ROOT/identity[0]).resolve()
 original=Path.read_bytes
 def altered(candidate):
  raw=original(candidate)
  return raw+b'# altered historical predecessor\\n' if candidate.resolve()==target else raw
 monkeypatch.setattr(Path,'read_bytes',altered)
 with pytest.raises(AssertionError,match='Pass-A E3 audit predecessor differs'):
  current.authenticate_pass_a_e3_compat_predecessors(a2,latest)

def test_v1_pass4_raw_tree_fixture_is_exact_historical_git_tree():
 import hashlib
 from scripts import audit_core_01d_ci_offline_transport_boundary as a2
 raw=current.authenticated_v1_original_raw_tree(a2)
 assert len(raw)==current.V1_ORIGINAL_RAW_TREE_SIZE
 assert hashlib.sha256(raw).hexdigest()==current.V1_ORIGINAL_RAW_TREE_SHA256
 if a2.historical_objects_available(current.V1_ORIGINAL_RAW_TREE_COMMIT):
  assert raw==a2.git('ls-tree','-r',current.V1_ORIGINAL_RAW_TREE_COMMIT)

def test_v1_pass4_raw_tree_fixture_rejects_byte_mode_path_and_symlink_tampering(
 monkeypatch,tmp_path,
):
 from pathlib import Path
 from scripts import audit_core_01d_ci_offline_transport_boundary as a2
 target=(current.ROOT/current.V1_ORIGINAL_RAW_TREE_PATH).resolve()
 original=Path.read_bytes
 def altered(candidate):
  raw=original(candidate)
  return raw+b'100644 blob 0000000000000000000000000000000000000000\\tforged.py\\n' if candidate.resolve()==target else raw
 monkeypatch.setattr(Path,'read_bytes',altered)
 with pytest.raises(AssertionError,match='raw-tree snapshot bytes drift'):
  current.authenticated_v1_original_raw_tree(a2)
 monkeypatch.setattr(Path,'read_bytes',original)

 original_git=a2.git
 def wrong_mode(*args,**kwargs):
  if args==('ls-tree','-z','HEAD','--',current.V1_ORIGINAL_RAW_TREE_PATH):
   return ('120000 blob '+current.V1_ORIGINAL_RAW_TREE_BLOB+'\t'+current.V1_ORIGINAL_RAW_TREE_PATH+'\0').encode()
  return original_git(*args,**kwargs)
 monkeypatch.setattr(a2,'git',wrong_mode)
 with pytest.raises(AssertionError,match='mode or HEAD blob drift'):
  current.authenticated_v1_original_raw_tree(a2)
 monkeypatch.setattr(a2,'git',original_git)

 monkeypatch.setattr(current,'V1_ORIGINAL_RAW_TREE_PATH','tests/fixtures/forged-tree.txt')
 with pytest.raises(AssertionError,match='regular tracked fixture'):
  current.authenticated_v1_original_raw_tree(a2)

 monkeypatch.setattr(current,'V1_ORIGINAL_RAW_TREE_PATH',
                     'tests/fixtures/core_01d/pass_a_v1_original_raw_tree/linked-tree.txt')
 link_root=tmp_path/'linked-tree'
 link=(link_root/current.V1_ORIGINAL_RAW_TREE_PATH)
 link.parent.mkdir(parents=True)
 link.symlink_to(target)
 monkeypatch.setattr(current,'ROOT',link_root)
 with pytest.raises(AssertionError,match='regular tracked fixture'):
  current.authenticated_v1_original_raw_tree(a2)

def test_local_test_products_are_not_authority_evidence(monkeypatch):
 assert current.LOCAL_TEST_PRODUCTS=={'.pytest-shard-files','p3-0-e1-live-readiness.json','artifacts/p3-0-comparison-evidence/p3-0-e1-live-readiness.json'}
 assert 'Path(".pytest-shard-files").write_text(' in (review.ROOT/'.github/workflows/tests.yml').read_text()
 original=review.retention.v4.v3._git
 def products(*args):
  if args==('ls-files','--others','--exclude-standard'):
   return ('\n'.join(sorted(current.LOCAL_TEST_PRODUCTS))+'\n').encode()
  return original(*args)
 monkeypatch.setattr(review.retention.v4.v3,'_git',products)
 assert current.authenticate_current_scope()
 assert not current.LOCAL_TEST_PRODUCTS & current.ALLOWED_PASS_A_PATHS
 def extra(*args):
  if args==('ls-files','--others','--exclude-standard'):return b'domain/unapproved-source.py\n'
  return original(*args)
 monkeypatch.setattr(review.retention.v4.v3,'_git',extra)
 with pytest.raises(AssertionError,match='unapproved untracked source'):current.authenticate_current_scope()


def test_checkpoint_e_uses_only_the_authenticated_historical_tests_workflow():
 from scripts import audit_checkpoint_e_workflows as checkpoint
 from scripts import audit_phase_a_pass_a_tests_source_successor as tests_source
 from scripts import audit_tests_shard_balance_successor as shards

 base, predecessors = checkpoint.base_input(include_scan_source_predecessors=True)
 history = checkpoint.history_input()
 predecessor = tests_source.historical_workflow_source()
 assert predecessor == shards.read_blob(shards.FIXTURE)
 assert shards.identity(predecessor) == shards.BEFORE
 assert predecessors[shards.WORKFLOW] == predecessor
 expected = checkpoint.build_matrix(base, history, predecessors)
 assert expected == checkpoint.strict(checkpoint.read(checkpoint.MATRIX_PATH))

 tampered = dict(predecessors)
 tampered[shards.WORKFLOW] = predecessor + b"\n"
 with pytest.raises(ValueError, match="predecessor|immutable source inventory"):
  checkpoint.build_matrix(base, history, tampered)
 unapproved = dict(predecessors)
 unapproved["tests/unrelated.py"] = b"unapproved"
 with pytest.raises(ValueError, match="unapproved source predecessor"):
  checkpoint.build_matrix(base, history, unapproved)


def test_a2_depth_one_tests_text_is_the_exact_v1_predecessor(monkeypatch):
 from scripts import audit_core_01d_ci_offline_transport_boundary as a2
 from scripts import audit_tests_shard_balance_successor as shards

 expected = shards.read_blob(shards.FIXTURE)
 assert shards.identity(expected) == shards.BEFORE
 assert a2.pinned_historical_text(shards.WORKFLOW).encode("utf-8") == expected
 original = shards.read_blob
 monkeypatch.setattr(
  shards, "read_blob",
  lambda path: original(path) + b"\n" if path == shards.FIXTURE else original(path),
 )
 with pytest.raises(ValueError, match="predecessor|identity|drift"):
  a2.pinned_historical_text(shards.WORKFLOW)


def test_b1_generation_assertion_uses_only_the_authenticated_historical_source(monkeypatch):
 from scripts import audit_phase_a_pass_a_tests_source_successor as pass_a

 current = pass_a.read_blob(pass_a.B1_SOURCE)
 historical = pass_a.read_blob(pass_a.B1_FIXTURE)
 row = pass_a._integrated_lineage_receipt()['source_forward'][pass_a.B1_SOURCE]
 assert row['before'] == pass_a.B1_V2_AFTER
 assert pass_a.safe.identity(pass_a.read_blob(row['fixture'])) == pass_a.B1_V2_AFTER
 assert pass_a.safe.identity(current) == row['after']
 assert pass_a.safe.identity(historical) == pass_a.B1_BEFORE
 assert pass_a.predecessor_source(pass_a.B1_SOURCE, current) == historical
 assert pass_a.predecessor_source("tests/unrelated.py", b"unrelated") == b"unrelated"

 with pytest.raises(ValueError, match="integrated lineage caller source drift"):
  pass_a.predecessor_source(pass_a.B1_SOURCE, current + b"\n")

 original = pass_a.read_blob
 monkeypatch.setattr(
  pass_a, "read_blob",
  lambda path: original(path) + b"\n" if path == pass_a.B1_FIXTURE else original(path),
 )
 with pytest.raises(ValueError, match="identity drift|exact reviewed patch"):
  pass_a.predecessor_source(pass_a.B1_SOURCE, current)


def test_a2_historical_text_source_forward_is_exact_and_path_limited(monkeypatch):
 from scripts import audit_phase_a_pass_a_tests_source_successor as pass_a

 row = pass_a._a2_text_receipt()["source_forward"][pass_a.A2_TEXT_SOURCE]
 current = pass_a.read_blob(pass_a.A2_TEXT_SOURCE)
 historical = pass_a.read_blob(row["fixture"])
 assert pass_a._a2_text_predecessor_source(pass_a.A2_TEXT_SOURCE, current) == historical
 assert pass_a._a2_text_predecessor_source("scripts/unrelated.py", b"current") == b"current"

 with pytest.raises(ValueError, match="identity drift"):
  pass_a._a2_text_predecessor_source(pass_a.A2_TEXT_SOURCE, current + b"\n")

 original = pass_a.read_blob
 monkeypatch.setattr(
  pass_a, "read_blob",
  lambda path: original(path) + b"\n" if path == row["fixture"] else original(path),
 )
 with pytest.raises(ValueError, match="identity drift"):
  pass_a._a2_text_predecessor_source(pass_a.A2_TEXT_SOURCE, current)


def test_pytest_configuration_restoration_keeps_both_published_identities():
 from scripts import audit_phase_a_pass_a_tests_source_successor as forward
 value = forward._pytest_restoration_receipt()
 row = value['source_forward']['pytest.ini']
 original = forward._positive_fixture_receipt()['source_forward']['pytest.ini']
 assert row['before'] == original['after']
 assert row['after'] == original['before']
 assert forward.read_blob('pytest.ini') == forward.read_blob(original['fixture'])
 assert forward._pytest_restoration_predecessor('unrelated', b'current') == b'current'


@pytest.mark.parametrize('which', ['receipt', 'current', 'fixture', 'inventory',
                                   'census_current', 'census_fixture', 'checkpoint_current', 'checkpoint_fixture'])
def test_pytest_restoration_rejects_changed_evidence(monkeypatch, which):
 from scripts import audit_phase_a_pass_a_tests_source_successor as forward
 value = forward._pytest_restoration_receipt()
 row = value['source_forward']['pytest.ini']
 target = {'receipt': forward.PYTEST_RESTORATION_RECEIPT,
           'current': 'pytest.ini', 'fixture': row['fixture'],
           'inventory': value['predecessor_inventory']['path'],
           'census_current': forward.CENSUS_TEST,
           'census_fixture': value['source_forward'][forward.CENSUS_TEST]['fixture'],
           'checkpoint_current': 'scripts/audit_checkpoint_e_workflows.py',
           'checkpoint_fixture': value['source_forward']['scripts/audit_checkpoint_e_workflows.py']['fixture']}[which]
 original = forward.read_blob
 monkeypatch.setattr(forward, 'read_blob', lambda p: original(p) + (b' ' if p == target else b''))
 with pytest.raises(ValueError, match='restoration'):
  forward._pytest_restoration_receipt()


def test_census_historical_scan_authenticates_current_then_exact_frozen_source(monkeypatch):
 import json
 from scripts import audit_phase_a_pass_a_tests_source_successor as forward
 row = forward._pytest_restoration_receipt()['source_forward'][forward.CENSUS_TEST]
 before = forward.historical_census_test_source()
 frozen = json.loads(forward.read_blob('tests/fixtures/core_01d/exact-main-source-inventory.json'))
 assert frozen['files'][forward.CENSUS_TEST] == {'mode': '100644', 'git_blob_sha1': row['before']['git_blob_sha1']}
 assert forward.safe.identity(before) == row['before']
 assert forward.safe.identity(forward.read_blob(forward.CENSUS_TEST)) == row['after']
 original = forward.read_blob
 monkeypatch.setattr(forward, 'read_blob', lambda p: original(p) + (b' ' if p == forward.CENSUS_TEST else b''))
 with pytest.raises(ValueError, match='restoration source identity drift'):
  forward.historical_census_test_source()


@pytest.mark.parametrize('which', ['missing', 'forged', 'stale'])
def test_census_historical_scan_rejects_unqualified_current_a2(monkeypatch, which):
 from scripts import audit_phase_a_pass_a_tests_source_successor as forward
 from scripts import audit_core_01d_ci_offline_transport_boundary as a2
 latest = deepcopy(a2.authenticate_inventory())
 if which == 'stale':
  latest['generation'] = 369
 elif which == 'missing':
  latest['source_identities'] = [r for r in latest['source_identities'] if r['path'] != forward.CENSUS_TEST]
 else:
  for row in latest['source_identities']:
   if row['path'] == forward.CENSUS_TEST:
    row['lf_source_sha256'] = '0' * 64
 monkeypatch.setattr(a2, 'authenticate_inventory', lambda: latest)
 with pytest.raises(ValueError, match='requires current A2 source identity'):
  forward.historical_census_test_source()
