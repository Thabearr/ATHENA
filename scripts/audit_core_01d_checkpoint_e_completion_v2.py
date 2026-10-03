"""Current completion overlays only proven Pass-A rows; V1 remains historical."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import json
from scripts import audit_core_01d_authority_reachability_review_a as review
from scripts import audit_core_01d_checkpoint_e_completion as v1

ROOT=review.ROOT
POLICY_ID='ATHENA_CORE_01D_CHECKPOINT_E_COMPLETION_V2'
RECEIPT_PATH='artifacts/architecture/core_01d_checkpoint_e_completion_v2.json'
REVIEW_SHA='9db3362af83eda04b6f005328b5d44f253fcd15ef5f39a62983cc6c3ff402521'
ALLOWED_PASS_A_PATHS={review.RECEIPT_PATH,RECEIPT_PATH,review.INVENTORY_PATH,
 'scripts/audit_core_01d_authority_reachability_review_a.py','scripts/audit_core_01d_checkpoint_e_completion_v2.py',
 'tests/test_core_01d_authority_reachability_review_a.py','tests/test_core_01d_checkpoint_e_completion_v2.py',
 'scripts/audit_checkpoint_e_workflows.py','docs/architecture/core_01d_checkpoint_e.md','tests/test_core_01d_checkpoint_e_completion.py','tests/test_core_01d_canonical_drive_transfer_completed_history.py'}
NEW_PASS_A_PATHS=ALLOWED_PASS_A_PATHS-{'scripts/audit_checkpoint_e_workflows.py','docs/architecture/core_01d_checkpoint_e.md','tests/test_core_01d_checkpoint_e_completion.py','tests/test_core_01d_canonical_drive_transfer_completed_history.py'}
UNCHANGED_SCOPE_SHA='5465e4dc03a46d4e64e81586720cebf9cb40d9dd53ce1fbe534fb825b5d9f32d'
# Existing offline P3 tests and the source-bound Tests shard selector publish
# these local products. This audit never consumes them as authority proof.
LOCAL_TEST_PRODUCTS={'.pytest-shard-files','p3-0-e1-live-readiness.json','artifacts/p3-0-comparison-evidence/p3-0-e1-live-readiness.json'}


def unchanged_inventory(raw):
 return b''.join(line for line in raw.splitlines(keepends=True) if line.split(b'\t',1)[1].strip().decode() not in ALLOWED_PASS_A_PATHS)

def a2_historical_projection(raw):
 from scripts import audit_core_01d_ci_offline_transport_boundary as a2
 # Authenticate all current caller/guard source before using a historical view.
 a2.authenticate_inventory()
 new_paths=a2.A2_PATHS-ALLOWED_PASS_A_PATHS-set(a2.HISTORICAL_TEST_BLOBS)
 rows=[]
 for line in raw.splitlines(keepends=True):
  path=line.split(b'\t',1)[1].strip().decode()
  if path in new_paths:continue
  if path in a2.HISTORICAL_TEST_BLOBS:
   line=('100644 blob '+a2.HISTORICAL_TEST_BLOBS[path]+'\t'+path+'\n').encode()
  rows.append(line)
 return b''.join(rows)

def authenticate_current_scope():
 from scripts import audit_core_01d_ci_offline_transport_boundary as a2
 git=review.retention.v4.v3._git
 review.require(review.sha256(unchanged_inventory(a2_historical_projection(git('ls-tree','-r','HEAD'))))==UNCHANGED_SCOPE_SHA,'Pass-A runtime/workflow/ledger/historical source change outside bounded evidence scope')
 review.require(set(git('diff','--name-only','HEAD').decode().splitlines())<=ALLOWED_PASS_A_PATHS|a2.A2_PATHS,'unapproved dirty source in Pass A')
 review.require(set(git('ls-files','--others','--exclude-standard').decode().splitlines())<=ALLOWED_PASS_A_PATHS|a2.A2_PATHS|LOCAL_TEST_PRODUCTS,'unapproved untracked source in Pass A')
 return True


@contextmanager
def historical_v1_git_view():
 """Remove only authenticated additive evidence from V1's historical inventory.

 V1's source, receipt, validator, criteria and strict inventory hash are unchanged.
 The original validator runs against the historical projection; no criterion or
 failure is overridden. All source outside this pass was authenticated first.
 This is deterministic in shallow CI and requires no network or ancestor fetch.
 """
 authenticate_current_scope()
 module=review.retention.v4.v3
 original=module._git
 def projected(*args):
  raw=original(*args)
  if args==('ls-tree','-r','HEAD'):
   raw=a2_historical_projection(raw)
   return b''.join(line for line in raw.splitlines(keepends=True) if line.split(b'\t',1)[1].strip().decode() not in NEW_PASS_A_PATHS)
  if args==('diff','--name-only','HEAD'):
   from scripts import audit_core_01d_ci_offline_transport_boundary as a2
   return b''.join(line for line in raw.splitlines(keepends=True) if line.strip().decode() not in NEW_PASS_A_PATHS|a2.A2_PATHS)
  return raw
 module._git=projected
 try: yield
 finally:
  module._git=original


def historical_v1_receipt():
 value=review.authenticate_json(review.COMPLETION_V1,review.COMPLETION_V1_SHA)
 with historical_v1_git_view():
  expected=v1.build_receipt()
  v1.validate_receipt(value,expected)
 return value


def build_receipt():
 # Rerun every original criterion against authenticated unchanged operational
 # sources. Apply only resolved row keys; partially reviewed keys remain exactly
 # inherited, together with all 32 entirely out-of-scope predecessor keys.
 review.authenticate_inventory()
 old=historical_v1_receipt()
 reviewed=review.read_json(review.RECEIPT_PATH)
 review.validate_receipt(reviewed)
 review.require(reviewed['canonical_sha256']==REVIEW_SHA,'Pass-A review identity drift')
 rows=reviewed['review_rows']
 resolved=[r for r in rows if r['resolved']]
 resolved_keys={(r['workflow_path'],r['trigger_kind']) for r in resolved}
 require=review.require
 require(resolved_keys<=review.KEYS,'out-of-scope authority overlay')
 remaining=[r for r in old['unreviewed_authority_surfaces'] if (r['workflow_path'],r['trigger_kind']) not in resolved_keys]
 remaining_keys={(r['workflow_path'],r['trigger_kind']) for r in remaining}
 require(not (remaining_keys & resolved_keys),'surface duplicated in resolved and inherited sets')
 require(len(remaining)==53-len(resolved_keys),'remaining count must be derived, not forced')
 out_of_scope=[r for r in remaining if (r['workflow_path'],r['trigger_kind']) not in review.KEYS]
 require(len(out_of_scope)==32,'out-of-scope predecessor rows changed')
 criteria=dict(old['checkpoint_criteria'])
 criteria[v1.CRITERIA[10]]=not remaining
 criteria[v1.CRITERIA[13]]=not remaining
 status,blockers=v1.status_from_criteria(criteria)
 require(status=='INCOMPLETE' and not criteria[v1.CRITERIA[10]] and not criteria[v1.CRITERIA[13]],'Pass A cannot close Checkpoint E')
 return review.seal({
  'schema_version':2,'policy_id':POLICY_ID,'repository':'Thabearr/ATHENA','master_issue':337,
  'base_main_sha':review.BASE_MAIN,'base_tree_sha':review.BASE_TREE,
  'predecessor_completion_v1':{'path':review.COMPLETION_V1,'canonical_sha256':review.COMPLETION_V1_SHA,'criteria_true_count':17,'unreviewed_surface_count':53,'checkpoint_e_status':'INCOMPLETE','rewritten':False},
  'matrix_v2':{'path':review.MATRIX_PATH,'canonical_sha256':review.MATRIX_SHA,'rewritten':False},
  'retained_v5':{'path':review.V5_PATH,'canonical_sha256':review.V5_SHA,'rewritten':False},
  'pass_a_review':{'path':review.RECEIPT_PATH,'canonical_sha256':REVIEW_SHA},
  'workflow_count':old['workflow_count'],'trigger_surface_count':old['trigger_surface_count'],
  'workflow_tree_before_sha1':old['workflow_tree_before_sha1'],'workflow_tree_after_sha1':old['workflow_tree_after_sha1'],
  'evolution_ledger_before_sha256':old['evolution_ledger_before_sha256'],'evolution_ledger_after_sha256':old['evolution_ledger_after_sha256'],'transition_count':old['transition_count'],
  'retirement_ledger_sha256':old['retirement_ledger_sha256'],'retired_workflow_count':old['retired_workflow_count'],
  'checkpoint_criteria':criteria,'checkpoint_e_status':status,'p4_4_status':status,'remaining_blocker_ids':blockers,
  'reviewed_pass_a_surface_count':21,'resolved_pass_a_surface_count':len(resolved),'unresolved_pass_a_surface_count':21-len(resolved),
  'reviewed_authority_rows':resolved,'unresolved_pass_a_rows':[r for r in rows if not r['resolved']],
  'unreviewed_authority_surfaces':remaining,'remaining_unreviewed_surface_count':len(remaining),'out_of_scope_unreviewed_surface_count':len(out_of_scope),
  'live_missing_artifact_relation_count':0,'historical_missing_artifact_relation_count':14,'retention_blockers_A_B_C_D':'CLOSED_WITH_HISTORICAL_LIMITATIONS_PRESERVED',
  'actions':review.retention.ZERO_ACTIONS,'protected_semantic_delta':review.retention.ZERO_DELTA,
  **review.retention.NO_AUTHORITY,
  'source_review_counter_while_open':'2/5','source_review_counter_if_owner_merges':'3/5','mandatory_source_reread_due':False,
  'terminal':reviewed['terminal'],
 })


def validate_receipt(value,expected=None):
 review.require(set(value['checkpoint_criteria'])==set(v1.CRITERIA),'19 criteria mandatory')
 status,blockers=v1.status_from_criteria(value['checkpoint_criteria'])
 review.require(status=='INCOMPLETE' and value['checkpoint_e_status']==value['p4_4_status']==status and value['remaining_blocker_ids']==blockers,'false completion or blocker removal')
 review.require(value==(build_receipt() if expected is None else expected),'completion V2 differs from independently authenticated review/source overlay')


def audit():
 value=review.read_json(RECEIPT_PATH);validate_receipt(value)
 return {'result':'PASS','receipt_sha256':value['canonical_sha256'],'checkpoint_e':value['checkpoint_e_status'],'p4_4':value['p4_4_status'],'remaining_blockers':value['remaining_blocker_ids'],'remaining_unreviewed_surface_count':value['remaining_unreviewed_surface_count'],'resolved_pass_a_surface_count':value['resolved_pass_a_surface_count'],'terminal':value['terminal']}

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--write',action='store_true');args=parser.parse_args()
 if args.write:
  value=build_receipt();(ROOT/RECEIPT_PATH).write_bytes(review.canonical_bytes(value));print(value['canonical_sha256'])
 else:print(json.dumps(audit(),sort_keys=True))
if __name__=='__main__':main()
