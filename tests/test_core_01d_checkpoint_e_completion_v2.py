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

def test_current_master_authenticates_v3_and_preserves_historical_v2(receipt):
 from scripts import audit_checkpoint_e_workflows as master
 from scripts import audit_core_01d_checkpoint_e_completion_v3 as a2
 value=master.audit()
 assert value['current_completion_receipt_sha256']==a2.audit()['receipt_sha256']
 assert value['historical_completion_v2_receipt_sha256']==receipt['canonical_sha256']
 assert value['historical_completion_v1_receipt_sha256']==review.COMPLETION_V1_SHA
 assert value['remaining_unreviewed_surface_count']==32
 assert value['checkpoint_e']==value['p4_4']=='INCOMPLETE'
 assert receipt['remaining_blocker_ids']==value['blockers']

def test_unapproved_runtime_change_cannot_hide_in_historical_projection(monkeypatch):
 original=review.retention.v4.v3._git
 def changed(*args):
  raw=original(*args)
  if args==('ls-tree','-r','HEAD'):return raw+b'100644 blob 0000000000000000000000000000000000000000\tdomain/unapproved-runtime.py\n'
  return raw
 monkeypatch.setattr(review.retention.v4.v3,'_git',changed)
 with pytest.raises(AssertionError,match='outside bounded evidence scope'):current.historical_v1_receipt()

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
