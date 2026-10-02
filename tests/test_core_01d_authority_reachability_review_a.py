"""Bounded surface set, truthful partial proof and source-backed authority."""
from copy import deepcopy
import socket
import smtplib
import pytest
from scripts import audit_core_01d_authority_reachability_review_a as review

@pytest.fixture(scope='module')
def receipt():return review.build_receipt()

@pytest.mark.parametrize('mutation',['20','22','wrong_path','wrong_trigger','duplicate','out_of_scope'])
def test_exact_scope_rejects_resealed_mutations(receipt,mutation):
 value=deepcopy(receipt)
 if mutation=='20':value['review_rows'].pop()
 elif mutation in ('22','duplicate'):value['review_rows'].append(deepcopy(value['review_rows'][0]))
 elif mutation=='wrong_path':value['review_rows'][0]['workflow_path']='.github/workflows/no-such-workflow.yml'
 elif mutation=='wrong_trigger':value['review_rows'][0]['trigger_kind']='push'
 else:value['review_rows'][0]['workflow_path']='.github/workflows/athena-run.yml'
 review.seal(value)
 with pytest.raises(AssertionError):review.validate_receipt(value,receipt)

def test_scope_sources_and_partial_counts_are_derived(receipt):
 assert {(r['workflow_path'],r['trigger_kind']) for r in receipt['review_rows']}==review.KEYS
 assert len({r['workflow_path'] for r in receipt['review_rows']})==15
 assert receipt['reviewed_surface_count']==21
 assert receipt['resolved_surface_count']==18 and receipt['unresolved_surface_count']==3
 assert receipt['remaining_global_unreviewed_surface_count']==35
 gaps={(r['workflow_path'],r['trigger_kind']) for r in receipt['review_rows'] if not r['resolved']}
 assert gaps=={(review.workflow_path('tests'),'push'),(review.workflow_path('tests'),'pull_request'),(review.workflow_path('athena-patch-bridge'),'issue_comment')}
 for row in receipt['review_rows']:
  assert set(review.REQUIRED_FIELDS)<=set(row)
  if row['resolved']:
   assert not any(word in text.upper() for text in review.strings(row) for word in review.FORBIDDEN)
  else:
   assert row['unresolved_fields'] and row['evidence_gap'] and row['safest_next_action']
   assert row['provider_acquisition_authority']=='EVIDENCE_GAP_DYNAMIC_TEST_TRANSPORT'

def row(value,name,trigger=None):return next(r for r in value['review_rows'] if r['workflow_path']==review.workflow_path(name) and (trigger is None or r['trigger_kind']==trigger))

@pytest.mark.parametrize('name,field,forged',[
 ('athena-draft-ready-bridge','provider_acquisition_authority','FOTMOB_READ_ONLY_CAPTURE'),
 ('athena-draft-ready-bridge','wager_authority','PLACE_BET'),
 ('athena-draft-ready-bridge','branch_write_authority','UNBOUNDED_WRITE'),
 ('athena-patch-bridge','provider_acquisition_authority','FOTMOB_READ_ONLY_CAPTURE'),
 ('athena-patch-bridge','wager_authority','PLACE_BET'),
 ('athena-patch-bridge','branch_write_authority','ANY_BRANCH_OR_WORKFLOW'),
 ('tests','provider_acquisition_authority','FOTMOB_READ_ONLY_CAPTURE'),
 ('tests','wager_authority','PLACE_BET'),
 ('tests','pull_request_mutation_authority','WRITE_ANY_PR'),
 ('athena-ingest','provider_acquisition_authority','NONE'),
 ('athena-ingest','sportsbook_read_authority','SPORTSBOOK_WRITE'),
 ('athena-ingest','share_code_authority','CREATE'),
 ('athena-ingest','wager_authority','PLACE_BET'),
 ('fotmob-utc-native-xg-fresh-holdout','share_code_authority','CREATE'),
 ('fotmob-utc-native-xg-fresh-holdout','wager_authority','PLACE_BET'),
 ('fotmob-utc-native-xg-fresh-holdout','protected_research_production_model_backfill_price_router_portfolio_authority','PRODUCTION_MODEL_BACKFILL_PRICE_ALL_ROUTER_PORTFOLIO'),
 ('p3-0-e1-owner-dispatch-bridge','provider_acquisition_authority','REVIEWED_FOTMOB_SOURCE_CAPTURE'),
 ('current-shadow-history-cache-prime','provider_acquisition_authority','REVIEWED_FOTMOB_SOURCE_CAPTURE'),
 ('athena-ingest','delivery_authority','USER_FACING_DELIVERY_FROM_UPLOAD'),
])
def test_high_risk_authority_claims_are_rejected(receipt,name,field,forged):
 value=deepcopy(receipt);row(value,name)[field]=forged;review.seal(value)
 with pytest.raises(AssertionError):review.validate_receipt(value,receipt)

@pytest.mark.parametrize('word',review.FORBIDDEN)
def test_resolved_row_recursively_rejects_placeholders(receipt,word):
 value=deepcopy(receipt);row(value,'athena-ingest')['dynamic_reachability_edges'][0]['nested']={'claim':word};review.seal(value)
 with pytest.raises(AssertionError):review.validate_receipt(value,receipt)

@pytest.mark.parametrize('name,needle',[
 ('athena-ingest','python -m'),('p3-0-e1-owner-dispatch-bridge','gh workflow run'),
 ('bridge-fotmob-fresh-holdout-continuity-receipts','workflow_run'),
 ('athena-patch-bridge','git push'),('athena-patch-bridge','download-artifact'),
 ('fotmob-utc-native-xg-fresh-holdout','gh release upload'),
 ('athena-ingest','upload-artifact'),
])
def test_removing_a_discovered_dynamic_or_side_effect_edge_fails(receipt,name,needle):
 value=deepcopy(receipt);r=row(value,name)
 edges=r['dynamic_reachability_edges']
 matches=[e for e in edges if needle in (review.ROOT/e['path']).read_text().splitlines()[e['line']-1]]
 assert matches,needle
 edges.remove(matches[0]);review.seal(value)
 with pytest.raises(AssertionError):review.validate_receipt(value,receipt)

@pytest.mark.parametrize('field',['artifact_read_authority','artifact_write_authority','notification_authority','dynamic_reachability_review_state'])
def test_required_explicit_dimensions_cannot_disappear(receipt,field):
 value=deepcopy(receipt);row(value,'athena-ingest').pop(field);review.seal(value)
 with pytest.raises(AssertionError):review.validate_receipt(value,receipt)

def test_comment_watchdog_has_no_dispatch_but_schedule_does(receipt):
 comment=row(receipt,'watch-fotmob-fresh-holdout-scheduler-liveness','issue_comment')
 scheduled=row(receipt,'watch-fotmob-fresh-holdout-scheduler-liveness','schedule')
 assert comment['workflow_dispatch_authority']=='NONE'
 assert scheduled['workflow_dispatch_authority']=='FIXED_FUTURE_FRESH_HOLDOUT_CONTINUITY_ONLY'
 assert comment['provider_acquisition_authority']==scheduled['provider_acquisition_authority']=='NONE'
 assert scheduled['outbound_dynamic_targets'][0]['target_path']==review.workflow_path('fotmob-utc-native-xg-fresh-holdout')
 assert not comment['outbound_dynamic_targets']

def test_ingest_is_update_artifact_not_database_commit(receipt):
 for r in receipt['review_rows']:
  if r['workflow_path']==review.workflow_path('athena-ingest'):
   assert r['provider_acquisition_authority']=='FOTMOB_READ_ONLY_CAPTURE'
   assert r['database_or_canonical_store_write_authority']=='CANONICAL_UPDATE_ARTIFACT_ONLY_NO_DATABASE_COMMIT'
   assert r['delivery_authority']=='ARTIFACT_ONLY'
   assert r['evidence_publication_is_user_facing_delivery'] is False

def test_partial_cannot_be_sealed_as_complete_review(receipt):
 value=deepcopy(receipt);r=row(value,'tests');r.update(resolved=True,unresolved_fields=[]);review.seal(value)
 with pytest.raises(AssertionError):review.validate_receipt(value,receipt)

def test_offline_audit_never_invokes_transport(monkeypatch):
 def deny(*args,**kwargs):raise AssertionError('live transport forbidden')
 monkeypatch.setattr(socket,'create_connection',deny);monkeypatch.setattr(smtplib,'SMTP',deny)
 assert review.audit()['result']=='PASS'

def test_inventory_authenticates_every_source_and_discovery_edge():
 inv=review.authenticate_inventory()
 assert len(inv['workflow_metadata'])==15
 assert inv['out_of_scope_trigger_classification_count']==0
 assert all(s['git_blob_sha1'] and s['normalized_source_sha256'] for s in inv['sources'])
 assert all(inv['static_discovery_edges'][review.workflow_path(n)] for n in review.SCOPE)
