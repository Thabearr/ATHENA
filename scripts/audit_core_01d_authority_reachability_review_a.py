"""Offline, source-bound Pass-A authority review; capability is not permission."""
from __future__ import annotations
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import yaml
from services import athena_artifact_role_resolver as roles
from scripts import audit_core_01d_historical_retention_acceptance as retention

ROOT = Path(__file__).resolve().parents[1]
BASE_MAIN = '11d4ee1cb52ba3f766698e2ed335e57d0547a475'
BASE_TREE = '96629b79a6ffaa13ab497fae58a9411cec4bc846'
POLICY_ID = 'ATHENA_CORE_01D_AUTHORITY_REACHABILITY_REVIEW_A_V1'
RECEIPT_PATH = 'artifacts/architecture/core_01d_authority_reachability_review_a_v1.json'
INVENTORY_PATH = 'tests/fixtures/core_01d/authority-reachability-pass-a-source-inventory-v1.json'
INVENTORY_SHA = 'f3cdbec57c380f7a77ce97e4bfab627241cc8b73d0817ec2abfa2f27cf2e209f'
COMPLETION_V1 = 'artifacts/architecture/core_01d_checkpoint_e_completion_v1.json'
COMPLETION_V1_SHA = 'aa65bef7841b7dd8a45ffddc65c25c06c14319d1711bc52ef62fcc50059b1731'
MATRIX_PATH = 'artifacts/architecture/checkpoint_e_workflow_capability_matrix_v2.json'
MATRIX_SHA = '3c3cfec8b37e55161b24185941e72c3e096a00f38456a2c07a9072b62e31e5b7'
V5_PATH = 'artifacts/architecture/core_01d_retained_workflow_status_v5.json'
V5_SHA = 'c90d71a04f54c29ed094b262f0aef6cad9067316c6d548227f1c4c289a4abebf'
SCOPE = {
 'athena-draft-ready-bridge': ['issue_comment'], 'athena-patch-bridge': ['issue_comment'],
 'athena-ingest': ['schedule', 'workflow_dispatch'], 'tests': ['pull_request', 'push'],
 'current-shadow-history-cache-prime': ['issue_comment', 'workflow_dispatch'],
 'current-shadow-sportybet-source-diagnostic': ['issue_comment'],
 'audit-fotmob-utc-native-xg-fresh-holdout-lineage': ['issue_comment'],
 'bridge-fotmob-fresh-holdout-continuity-receipts': ['issue_comment', 'workflow_run'],
 'fotmob-utc-native-xg-fresh-holdout-release-receipts': ['workflow_run'],
 'fotmob-utc-native-xg-fresh-holdout': ['schedule', 'workflow_dispatch'],
 'watch-fotmob-fresh-holdout-scheduler-liveness': ['issue_comment', 'schedule'],
 'verify-fotmob-fresh-holdout-history-pagination': ['pull_request'],
 'issue-current-fotmob-reviewed-source': ['workflow_dispatch'],
 'p3-0-comparison-evidence-capture': ['workflow_dispatch'],
 'p3-0-e1-owner-dispatch-bridge': ['issue_comment'],
}
def workflow_path(name): return '.github/workflows/' + name + '.yml'
KEYS = {(workflow_path(name), trigger) for name, triggers in SCOPE.items() for trigger in triggers}
FAMILY_SOURCES = {
 'athena-draft-ready-bridge': [],
 'athena-patch-bridge': ['tests/conftest.py', 'requirements.txt'],
 'athena-ingest': ['scripts/resolve_athena_ingest_workflow_request.py', 'scripts/execute_athena_ingest_workflow.py', 'services/athena_ingest_service.py', 'domain/ingest_contracts.py', 'scripts/capture_fotmob_data_matches.py', 'domain/fotmob_data_matches_capture.py', 'domain/fotmob_data_matches_probe.py', 'tests/test_athena_ingest_workflow.py', 'tests/test_athena_ingest_service.py'],
 'tests': ['tests/conftest.py', 'requirements.txt', 'tests/test_athena_ingest_workflow.py', 'tests/test_fotmob_utc_native_expected_goals_fresh_holdout_activation_runner.py', 'tests/test_current_shadow_sportybet_source_diagnostic.py'],
 'current-shadow-history-cache-prime': ['scripts/restore_current_shadow_history_prime_artifact.py', 'scripts/prime_current_shadow_history_github_cache.py', 'scripts/current_shadow_history_github_persistent_cache.py', 'scripts/current_shadow_history_github_prefetch.py', 'domain/current_fotmob_latest_durable_fresh_history.py', 'scripts/audit_fotmob_fresh_holdout_actions_lineage.py', 'scripts/audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection.py'],
 'current-shadow-sportybet-source-diagnostic': ['scripts/capture_current_shadow_sportybet_source_diagnostic.py', 'domain/current_shadow_sportybet_catalog_fanout_reconciliation.py', 'domain/_current_shadow_sportybet_catalog_fanout_reconciliation_candidate_local.py', 'domain/_current_shadow_sportybet_catalog_fanout_reconciliation_base.py'],
 'audit-fotmob-utc-native-xg-fresh-holdout-lineage': ['scripts/audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection.py', 'scripts/audit_fotmob_fresh_holdout_actions_lineage_pr175_projection.py', 'scripts/audit_fotmob_fresh_holdout_actions_lineage.py', 'domain/fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery.py', 'scripts/mirror_fotmob_fresh_holdout_release_receipt.py'],
 'bridge-fotmob-fresh-holdout-continuity-receipts': ['domain/fotmob_fresh_holdout_bridge_noop.py', 'domain/fotmob_fresh_holdout_continuity.py', 'scripts/bind_fotmob_fresh_holdout_continuity_dispatch.py', 'scripts/run_fotmob_fresh_holdout_release_receipt_mirror.py', 'scripts/mirror_fotmob_fresh_holdout_release_receipt.py', 'domain/fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery.py'],
 'fotmob-utc-native-xg-fresh-holdout-release-receipts': ['scripts/run_fotmob_fresh_holdout_release_receipt_mirror.py', 'scripts/mirror_fotmob_fresh_holdout_release_receipt.py', 'domain/fotmob_fresh_holdout_continuity.py', 'domain/fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery.py'],
 'fotmob-utc-native-xg-fresh-holdout': ['scripts/restore_fotmob_pr119_bootstrap_release.py', 'scripts/run_fotmob_utc_native_xg_fresh_holdout_tick.py', 'domain/fotmob_utc_native_expected_goals_fresh_holdout_activation_runner.py', 'domain/fotmob_utc_native_expected_goals_fresh_holdout_collection_control.py', 'domain/fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery.py', 'domain/fotmob_fresh_holdout_continuity.py', 'domain/fotmob_fresh_holdout_capture_qualification_adapter.py', 'domain/fotmob_fresh_holdout_ordinary_ft_settlement_schema_adapter.py', 'scripts/capture_fotmob_data_matches.py'],
 'watch-fotmob-fresh-holdout-scheduler-liveness': ['scripts/check_fotmob_fresh_holdout_scheduler_liveness.py', 'domain/fotmob_fresh_holdout_continuity.py'],
 'verify-fotmob-fresh-holdout-history-pagination': [],
 'issue-current-fotmob-reviewed-source': ['scripts/issue_current_fotmob_reviewed_source_via_ingest.py', 'services/current_fotmob_ingest_issuer.py', 'services/athena_ingest_service.py', 'services/current_fotmob_ingest_compatibility.py', 'domain/ingest_contracts.py', 'scripts/capture_fotmob_data_matches.py'],
 'p3-0-comparison-evidence-capture': ['scripts/restore_current_shadow_history_prime_artifact.py', 'scripts/verify_p3_0_e1_live_readiness.py', 'scripts/capture_p3_0_paired_evidence_hosted.py', 'scripts/capture_p3_0_paired_evidence.py', 'scripts/_p3_0_paired_capture_part1.py', 'scripts/_p3_0_paired_capture_part2.py', 'scripts/p3_0_current_request_reconciliation_compat.py', 'scripts/p3_0_duplicate_event_conflict_diagnostic.py', 'scripts/current_shadow_history_artifact_verification_reuse.py', 'scripts/current_shadow_history_builder_audit_reuse.py', 'scripts/current_shadow_history_semantic_replay_reuse.py', 'scripts/current_shadow_history_github_persistent_cache.py', 'scripts/execute_current_shadow_all_market.py', 'scripts/execute_current_shadow_all_market_summary_reuse.py', 'domain/current_shadow_all_market_runner.py', 'domain/current_shadow_canonical_core_adapter.py', 'domain/current_shadow_fixture_date_request.py', 'domain/current_shadow_sportybet_pc_upcoming_reconciliation.py', 'scripts/issue_current_fotmob_reviewed_source.py', 'domain/_current_shadow_quote_binding.py'],
 'p3-0-e1-owner-dispatch-bridge': [],
}
PREDECESSORS = {
 COMPLETION_V1: COMPLETION_V1_SHA, MATRIX_PATH: MATRIX_SHA, V5_PATH: V5_SHA,
 retention.RECEIPT_PATH: '2b1957c6ef92066832434528d3c9cb13a317d9daebc441b08f939a7ea5c9189c',
}
ANCHORS = ['artifacts/architecture/core_01d_athena_run_scheduled_shadow_cutover_v1.json', 'artifacts/architecture/core_01b_canonical_artifact_ancestry_v1.json', 'artifacts/architecture/core_01c_notification_comment_compatibility_v1.json', 'artifacts/architecture/p4_workflow_evolution_ledger_v1.json', 'artifacts/architecture/p4_3_workflow_retirement_ledger_v1.json', '.github/workflows/athena-run.yml', '.github/workflows/current-shadow-all-market.yml', 'scripts/audit_core_01d_checkpoint_e_completion.py']
# A lexical signal is a discovery obligation, never an authority conclusion.
SIGNALS = re.compile(r'uses:|python\s|\b(?:bash|sh)\s+[^|]|subprocess\.|gh\s+(?:api|workflow|run|release)|github\.(?:rest|graphql)|createWorkflowDispatch|repository_dispatch|workflow_(?:dispatch|run)|actions/(?:download|upload)-artifact|git push|SMTP|sendmail|requests\.|httpx\.|urllib\.|urlopen|curl\s|https?://|_network_get|acquisition_callable\(|capture_one\(|connection_factory\(|putrequest\(|share_module\.|wallet|stake|wager', re.I)
FORBIDDEN = ('UNKNOWN', 'UNREVIEWED', 'TBD', 'ASSUMED')
AUTHORITY_FIELDS = ('provider_acquisition_authority', 'sportsbook_read_authority', 'share_code_authority', 'wager_authority', 'delivery_authority', 'notification_authority', 'artifact_read_authority', 'artifact_write_authority', 'release_read_authority', 'release_write_authority', 'issue_comment_write_authority', 'pull_request_mutation_authority', 'branch_write_authority', 'workflow_dispatch_authority', 'database_or_canonical_store_write_authority', 'external_storage_write_authority')
REQUIRED_FIELDS = ('workflow_path', 'trigger_kind', 'workflow_source_sha256', 'workflow_git_blob_sha1', 'supported_status', 'retained_reason', 'authority_profile', *AUTHORITY_FIELDS, 'credential_surface', 'network_authority_summary', 'dynamic_reachability_review_state', 'dynamic_reachability_edges', 'fail_closed_guards', 'source_evidence', 'historical_or_current_lifecycle')
sha256 = lambda raw: hashlib.sha256(raw).hexdigest()
seal, canonical_bytes = retention.seal, retention.canonical_bytes
require = retention.require

def identity(path):
 raw = (ROOT / path).read_bytes()
 return {'path': path, 'git_blob_sha1': hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(), 'normalized_source_sha256': sha256(raw.replace(b'\r\n', b'\n'))}

def read_json(path): return roles.strict_json((ROOT / path).read_bytes())
def authenticate_json(path, expected):
 value = read_json(path)
 require(value.get('canonical_sha256') == expected == sha256(canonical_bytes({k:v for k,v in value.items() if k!='canonical_sha256'})), 'immutable predecessor identity drift: '+path)
 return value

def discover(path):
 text = (ROOT/path).read_text(); edges=[]; step='source'; function='module'
 ranges=[]
 if path.endswith('.py'):
  ranges=[(n.lineno,n.end_lineno,n.name) for n in ast.walk(ast.parse(text)) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
 for line,content in enumerate(text.splitlines(),1):
  if '- name:' in content: step=content.split('- name:',1)[1].strip()
  owners=[(end-start,name) for start,end,name in ranges if start<=line<=end]
  function=min(owners)[1] if owners else 'module'
  if SIGNALS.search(content):
   edges.append({'id':path+':'+str(line), 'path':path,'line':line,'step':step if path.endswith('.yml') else function,
                 'line_sha256':sha256(content.encode()), 'discovery_kind':'LEXICAL_SIGNAL_REQUIRES_PATH_REVIEW'})
 if path.endswith('.py'):
  for node in ast.walk(ast.parse(text)):
   if isinstance(node,ast.Import): modules=[alias.name for alias in node.names]
   elif isinstance(node,ast.ImportFrom): modules=[node.module] if node.module else []
   else: continue
   for module in modules:
    if module.split('.')[0] in ('domain','scripts','services','providers'):
     edges.append({'id':path+':'+str(node.lineno)+':import:'+module,'path':path,'line':node.lineno,'step':'repository import binding','line_sha256':sha256(text.splitlines()[node.lineno-1].encode()),'discovery_kind':'REPOSITORY_CALLEE_BINDING','callee_module':module})
 return edges

def workflow_metadata(path):
 doc=yaml.load((ROOT/path).read_text(),Loader=yaml.BaseLoader)
 return {'name':doc['name'], 'trigger_filters':doc['on'], 'permissions':doc.get('permissions',{}),
         'job_permissions':{k:v.get('permissions',{}) for k,v in doc['jobs'].items()},
         'job_guards':{k:v.get('if','SUCCESS_DEFAULT') for k,v in doc['jobs'].items()},
         'step_guards':{k:[{'name':s.get('name',s.get('uses','step')), 'if':s.get('if','SUCCESS_DEFAULT')} for s in v.get('steps',[])] for k,v in doc['jobs'].items()},
         'concurrency':doc.get('concurrency',{}),
         'environment_variable_names':sorted({key for job in doc['jobs'].values() for step in job.get('steps',[]) for key in step.get('env',{})}),
         'token_bindings':sorted({value for job in doc['jobs'].values() for step in job.get('steps',[]) for key,value in step.get('env',{}).items() if key in ('GH_TOKEN','GITHUB_TOKEN')}),
         'dynamic_workflow_literals':[{'line':i,'literal':match.group(0)} for i,line in enumerate((ROOT/path).read_text().splitlines(),1) for match in re.finditer(r'[a-z][a-z0-9-]+\.yml|workflow_id[\"\']?\s*[:=]\s*[0-9]+',line)]}

def build_inventory():
 paths=sorted({workflow_path(n) for n in SCOPE}|{p for ps in FAMILY_SOURCES.values() for p in ps}|set(PREDECESSORS)|set(ANCHORS))
 # Read all current YAMLs only to bound repository callers; no out-of-scope row is classified.
 callers=[]
 for path in sorted((ROOT/'.github/workflows').glob('*.yml')):
  doc=yaml.load(path.read_text(),Loader=yaml.BaseLoader)
  for target in SCOPE:
   name=workflow_metadata(workflow_path(target))['name']
   if name in doc.get('on',{}).get('workflow_run',{}).get('workflows',[]):
    callers.append({'caller_path':path.relative_to(ROOT).as_posix(),'target_path':workflow_path(target),'kind':'WORKFLOW_RUN_NAME_FILTER','caller_identity':identity(path.relative_to(ROOT).as_posix())})
   for line,content in enumerate(path.read_text().splitlines(),1):
    if re.search(r'gh\s+workflow\s+run\s+'+re.escape(target+'.yml'),content):
     callers.append({'caller_path':path.relative_to(ROOT).as_posix(),'target_path':workflow_path(target),'kind':'FIXED_ACTIONS_DISPATCH','line':line,'caller_identity':identity(path.relative_to(ROOT).as_posix())})
  for target in SCOPE:
   pattern=r'[\"\']gh[\"\']\s*,\s*[\"\']workflow[\"\']\s*,\s*[\"\']run[\"\']\s*,\s*[\"\']'+re.escape(target+'.yml')
   for match in re.finditer(pattern,path.read_text()):
    callers.append({'caller_path':path.relative_to(ROOT).as_posix(),'target_path':workflow_path(target),'kind':'FIXED_ACTIONS_DISPATCH','line':path.read_text()[:match.start()].count('\n')+1,'caller_identity':identity(path.relative_to(ROOT).as_posix())})
 return seal({'schema_version':1,'policy_id':'ATHENA_CORE_01D_AUTHORITY_REACHABILITY_PASS_A_SOURCE_INVENTORY_V1',
  'base_main_sha':BASE_MAIN,'base_tree_sha':BASE_TREE,'sources':[identity(p) for p in paths],
  'workflow_metadata':{workflow_path(n):workflow_metadata(workflow_path(n)) for n in SCOPE},
  'family_semantic_sources':FAMILY_SOURCES,'static_discovery_edges':{p:discover(p) for p in paths if p.endswith(('.py','.yml'))},
  'repository_callers':callers,'external_side_effect_boundaries':{
   'fotmob':'scripts/capture_fotmob_data_matches.py:fetch_fotmob_data_matches',
   'sportybet_diagnostic':'domain/_current_shadow_sportybet_catalog_fanout_reconciliation_base.py:_network_get',
   'research_capture':'domain/current_shadow_all_market_runner.py:_acquire_router_inputs',
   'github_release_receipt':'scripts/run_fotmob_fresh_holdout_release_receipt_mirror.py:upload_receipt',
   'branch_push':'athena-patch-bridge.yml:commit/Commit and push exact reviewed patch',
   'dynamic_pytest':'tests/test_*.py selected from checkout; global transport absence is not established'},
  'out_of_scope_trigger_classification_count':0,'read_only':True})

def authenticate_inventory():
 value=read_json(INVENTORY_PATH)
 require(value['canonical_sha256']==INVENTORY_SHA,'Pass-A inventory seal drift')
 require(value==build_inventory(),'source identities, guards, permissions, callers or discovered edges drifted')
 return value

def authenticate_scope():
 old=authenticate_json(COMPLETION_V1,COMPLETION_V1_SHA)
 authenticate_json(MATRIX_PATH,MATRIX_SHA); authenticate_json(V5_PATH,V5_SHA)
 require(len(old['unreviewed_authority_surfaces'])==53 and sum(old['checkpoint_criteria'].values())==17,'predecessor criteria drift')
 for path,trigger in KEYS:
  rows=[r for r in old['unreviewed_authority_surfaces'] if (r['workflow_path'],r['trigger_kind'])==(path,trigger)]
  require(len(rows)==1 and rows[0]['current_source_sha256']==identity(path)['normalized_source_sha256'],'Pass-A scope/source drift: '+path+':'+trigger)
 return old

# Conclusions below name guarded effects, not imported capabilities. The pinned
# inventory binds the complete YAML and the specific semantic callees relied on.
CONTRACTS = {
 'athena-draft-ready-bridge': ('GITHUB_PR_CONTROL_PLANE', {'pull_request_mutation_authority':'OPEN_DRAFT_TO_READY_EXACT_HEAD_ONLY'}, 'Owner Thabearr; exact /athena-ready head=<40 lowercase SHA>; same repository; main base; open draft; exact head before and after GraphQL mark-ready. No branch update or dispatch.'),
 'athena-patch-bridge': ('GITHUB_PATCH_CONTROL_PLANE', {'branch_write_authority':'VALIDATED_SAME_REPOSITORY_DRAFT_PR_HEAD_ONLY','artifact_write_authority':'TRANSIENT_VALIDATION_ARTIFACT','artifact_read_authority':'SAME_RUN_VALIDATED_PATCH_HASH_ONLY'}, 'Owner /athena-apply; same-repository open draft; two exact merge parents; patch SHA and head; 60KB limit; bounded path allowlist excludes .github; structural plus all synthetic pytest shards and syntax; exact head/base recheck; non-force PR-head push; post-push merge-tree verification. Pytest transport proof remains partial.'),
 'athena-ingest': ('CANONICAL_INGEST_MAIN', {'provider_acquisition_authority':'FOTMOB_READ_ONLY_CAPTURE','artifact_write_authority':'RUN_SCOPED_EVIDENCE_WRITE','database_or_canonical_store_write_authority':'CANONICAL_UPDATE_ARTIFACT_ONLY_NO_DATABASE_COMMIT','delivery_authority':'ARTIFACT_ONLY'}, 'Exact refs/heads/main and checkout SHA; persisted canonical request; explicit --execute-live-network; FotMob UTC/NGA 1..7 dates; bounded HTTP GET/size/time; exclusive capture persistence; canonical update JSON, replay manifest and receipt only; failed producer remains failure after artifact preservation.'),
 'tests': ('CI_VALIDATION_ONLY', {}, 'PR base main or push main; contents read; checkout, pip dependencies, compileall, deterministic all-test sharding. No live flags or production secrets are passed. Shared conftest does not globally deny transport; sampled monkeypatch tests do not prove every dynamically selected test is offline.'),
 'current-shadow-history-cache-prime': ('RESEARCH_SHADOW_SUPPORT', {'artifact_read_authority':'CROSS_RUN_TRUSTED_MAIN_VERIFIED_TRANSPORT_READ','artifact_write_authority':'HISTORY_CACHE_WRITE','release_read_authority':'DURABLE_HISTORY_TRANSPORT_READ','database_or_canonical_store_write_authority':'WORKER_LOCAL_TRANSPORT_CACHE_ONLY','delivery_authority':'ARTIFACT_ONLY'}, 'Issue #276 exact owner command, or GitHub-authorized manual dispatch (no extra YAML owner/main admission guard). Prior successful main run identity and cache hashes verified; GH_TOKEN required; immutable GitHub history transport/cache only, not provider acquisition or evidence admission.'),
 'current-shadow-sportybet-source-diagnostic': ('RESEARCH_SHADOW_SUPPORT', {'sportsbook_read_authority':'ANONYMOUS_CATALOG_TOURNAMENT_GET_DIAGNOSTICS_ONLY','artifact_write_authority':'RUN_SCOPED_EVIDENCE_WRITE','delivery_authority':'ARTIFACT_ONLY'}, 'Issue #276 owner exact command; fresh output directory; anonymous GET catalogue/tournament targets through fanout._network_get alias to base GET transport; bounded response parsing/exclusive evidence writes; no reconciliation, share-code, account or wager route invoked.'),
 'audit-fotmob-utc-native-xg-fresh-holdout-lineage': ('PROTECTED_RESEARCH_CONTROL_PLANE', {'artifact_read_authority':'CROSS_RUN_EXACT_LINEAGE_READ','artifact_write_authority':'PROTECTED_RESEARCH_RECEIPT_WRITE','release_read_authority':'EXACT_LINEAGE_EVIDENCE_READ','issue_comment_write_authority':'STATUS_ONLY_CONTROL_ISSUE_172_OR_LEGACY_PR_170','notification_authority':'ISSUE_COMMENT_STATUS_ONLY','delivery_authority':'ARTIFACT_ONLY'}, 'Exact owner three-line audit command and main SHA; merged/closed PR170 or open owner/title-bound issue172; reviewed dependency blobs; GitHub read-only metadata/binary lineage audit; successful or authorized failure status comment only. No provider collection, backfill or production authority.'),
 'bridge-fotmob-fresh-holdout-continuity-receipts': ('PROTECTED_RESEARCH_CONTROL_PLANE', {'artifact_read_authority':'CROSS_RUN_EXACT_CONTINUITY_EVIDENCE_READ','release_read_authority':'EXACT_ARCHIVE_AND_RECEIPT_READ','release_write_authority':'EXACT_RECEIPT_IN_EXISTING_EVIDENCE_RELEASE_ONLY','delivery_authority':'GITHUB_RELEASE_EVIDENCE_ONLY'}, 'Natural successful main scheduled watchdog ID345006851/path/name/head bound, or issue172 owner exact durability-only command with numeric run ID; checked-out reviewed blobs; source must be completed reviewed continuity dispatch. Proven no-dispatch/superseded preacquisition dispositions are no-ops. Verified existing bytes/receipt only; no collection dispatch.'),
 'fotmob-utc-native-xg-fresh-holdout-release-receipts': ('PROTECTED_RESEARCH_CONTROL_PLANE', {'artifact_read_authority':'CROSS_RUN_EXACT_COLLECTION_EVIDENCE_READ','release_read_authority':'EXACT_ARCHIVE_AND_RECEIPT_READ','release_write_authority':'EXACT_RECEIPT_IN_EXISTING_EVIDENCE_RELEASE_ONLY','delivery_authority':'GITHUB_RELEASE_EVIDENCE_ONLY'}, 'workflow_run primary collection name; successful schedule/continuity dispatch; transport validates exact collection workflow ID/path/branch/source and reviewed implementation blobs. Exact artifact ZIP digest and archive identity required, or independently proven no-acquisition no-op; release visibility verification; never substitute metadata for bytes.'),
 'fotmob-utc-native-xg-fresh-holdout': ('PROTECTED_RESEARCH', {'provider_acquisition_authority':'PROTECTED_FRESH_HOLDOUT_COLLECTION','artifact_read_authority':'CROSS_RUN_EXACT_DURABLE_LINEAGE_READ','artifact_write_authority':'PROTECTED_RESEARCH_RECEIPT_WRITE','release_read_authority':'EXACT_PR119_BOOTSTRAP_AND_DURABLE_LINEAGE_READ','release_write_authority':'PROSPECTIVE_RESEARCH_ARCHIVE_RELEASE_WRITE','database_or_canonical_store_write_authority':'PROTECTED_RESEARCH_STATE_ONLY','delivery_authority':'GITHUB_RELEASE_EVIDENCE_ONLY'}, 'Natural :07/:37 UTC schedule, or exact prospective-only continuity token/watchdog/main/jobs/window provenance; resolve lineage lattice and duplicates before acquisition. Fixed PR119 release projection hash e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2; reviewed tick adapters; --execute-live-network; no backfill, production xG, Price-all, Router, Portfolio, share-code or wager. Publish cumulative success/failure archive with exact release identity/size; failure never becomes success.'),
 'watch-fotmob-fresh-holdout-scheduler-liveness': ('PROTECTED_RESEARCH_CONTROL_PLANE', {'artifact_read_authority':'ACTIONS_CONTROL_METADATA_ONLY','issue_comment_write_authority':'STATUS_ONLY_CONTROL_ISSUE_172','notification_authority':'ISSUE_COMMENT_STATUS_ONLY'}, 'Exact :03/:33 cron or owner issue172 two-line control-only command; main equality and reviewed blobs; bounded scheduler decision may enable disabled or disable/enable stale primary registration. Schedule alone plans future continuity, rechecks main/source/window and absence of natural delivery before fixed-target dispatch. Does not call FotMob itself.'),
 'verify-fotmob-fresh-holdout-history-pagination': ('CI_VALIDATION_ONLY', {'artifact_read_authority':'ACTIONS_RUN_HISTORY_METADATA_ONLY'}, 'PR main and three explicit path filters; actions/contents read; inline gh GET pagination through full history; malformed/no pre-campaign completed boundary fails; logs only, no checkout/provider or write transport.'),
 'issue-current-fotmob-reviewed-source': ('RESEARCH_EVIDENCE_CAPTURE', {'provider_acquisition_authority':'REVIEWED_FOTMOB_SOURCE_CAPTURE','artifact_write_authority':'RUN_SCOPED_EVIDENCE_WRITE','database_or_canonical_store_write_authority':'CANONICAL_UPDATE_ARTIFACT_AND_REVIEW_PROJECTION_ONLY','delivery_authority':'ARTIFACT_ONLY'}, 'Dispatch date/timezone/ccode3; only UTC/NGA accepted; explicit live flag; refs/heads/main and checkout SHA enforced by issuer/service; one-date bounded FotMob GET, canonical artifact update then frozen review projection; failure persists and never falls back. No additional owner guard or downstream dispatch in YAML.'),
 'p3-0-comparison-evidence-capture': ('RESEARCH_EVIDENCE_CAPTURE', {'provider_acquisition_authority':'REVIEWED_FOTMOB_SOURCE_CAPTURE','sportsbook_read_authority':'ANONYMOUS_CURRENT_EVENT_DISCOVERY_AND_QUOTE_READ','artifact_read_authority':'CROSS_RUN_TRUSTED_MAIN_HISTORY_AND_IDENTITY_READ','artifact_write_authority':'RUN_SCOPED_EVIDENCE_WRITE','release_read_authority':'FIXED_PR119_BOOTSTRAP_READ','database_or_canonical_store_write_authority':'WORKER_LOCAL_EVIDENCE_AND_IDENTITY_ONLY','delivery_authority':'ARTIFACT_ONLY'}, 'Dispatch 1..7 prospective dates today..today+6 and cap1..50; exact checkout SHA, main lineage read (not a YAML owner/main-ref admission guard); trusted history restore and fixed PR119 projection hash. Hosted cache hooks restored in LIFO order; collector _collect_sources calls reviewed _acquire_router_inputs with P3_E1_PRE_ROUTER_CAPTURE and live acquisition, stops at research Price-All/Router. No Portfolio/share-code/account/wager/delivery invocation; bounded timeout and explicit failure evidence.'),
 'p3-0-e1-owner-dispatch-bridge': ('PROTECTED_RESEARCH_CONTROL_PLANE', {'workflow_dispatch_authority':'FIXED_P3_CAPTURE_MAIN_PROSPECTIVE_INPUTS_ONLY','artifact_read_authority':'ACTIONS_CAPTURE_RUN_METADATA_ONLY'}, 'Issue337 owner exact /athena-run-p3-e1; one unique owner authorization comment; exact current main before dispatch; prospective seven dates/cap50 fixed by code; no active capture, 90min cooldown, max8 starts/24h, exhausted bounded pagination. Dispatch exactly p3-0-comparison-evidence-capture.yml on main. Callee provider authority is not transferred to bridge.'),
}


def edge_classification(name, trigger, edge):
 text=(ROOT/edge['path']).read_text().splitlines()[edge['line']-1].strip()
 if edge['discovery_kind']=='REPOSITORY_CALLEE_BINDING': return 'CALLEE_IMPORT_CAPABILITY_ONLY_NOT_AUTHORITY_OR_EXECUTION'
 if text.startswith('#') or re.search(r'[\"\'](?:wager_placed|wallet|staking|share_code_generation)[\"\']\s*:\s*False',text): return 'SOURCE_GUARD_OR_DECLARATIVE_DENIAL_NOT_SIDE_EFFECT'
 if edge['step'] in ('upload_receipt','reviewed_upload'): return 'EXACT_VERIFIED_EXISTING_RELEASE_RECEIPT_WRITE'
 if edge['step'] in ('_gh_json','_gh_download','_reviewed_gh_download','_gh_release_metadata','_gh_download_asset'): return 'GITHUB_READ_ONLY_METADATA_OR_BINARY_TRANSPORT'
 if edge['step']=='_network_get': return 'ANONYMOUS_SPORTYBET_HTTP_GET_BOUNDARY'
 # Context follows the full pinned source, not the existence of a grep hit.
 if name=='watch-fotmob-fresh-holdout-scheduler-liveness' and trigger=='issue_comment' and edge['path']==workflow_path(name) and edge['line']>=199:
  return 'NOT_REACHABLE_COMMENT_TRIGGER_SCHEDULE_ONLY_GUARD'
 if 'git push' in text: return 'GUARDED_NONFORCE_DRAFT_PR_HEAD_WRITE'
 if 'markPullRequestReadyForReview' in text or 'github.graphql' in text: return 'GUARDED_EXACT_HEAD_PR_READY_MUTATION'
 if 'issues.createComment' in text: return 'GUARDED_CONTROL_STATUS_COMMENT'
 if 'gh workflow run' in text or '"gh", "workflow", "run"' in text: return 'GUARDED_FIXED_TARGET_ACTIONS_DISPATCH_NO_PROVIDER_CALL'
 if '/disable' in text or '/enable' in text: return 'GUARDED_SCHEDULER_REGISTRATION_WRITE'
 if 'upload-artifact' in text: return 'EVIDENCE_OR_TRANSIENT_ARTIFACT_WRITE_NOT_USER_DELIVERY'
 if 'download-artifact' in text or 'gh run download' in text: return 'GUARDED_ARTIFACT_TRANSPORT_READ'
 if 'gh release upload' in text or 'gh release create' in text: return 'GUARDED_RESEARCH_EVIDENCE_RELEASE_WRITE'
 if 'pytest' in text: return 'DYNAMIC_TEST_TRANSPORT_PROOF_GAP'
 if edge['path'] in ('tests/conftest.py','requirements.txt') or edge['path'].startswith('tests/'): return 'LOCAL_TEST_OR_DEPENDENCY_PROOF_NOT_GLOBAL_NETWORK_DENIAL'
 if 'putrequest(' in text or '_network_get(' in text or 'connection_factory(' in text or 'capture_one(' in text or 'acquisition_callable(' in text: return 'NAMED_CALLEE_TRANSPORT_BOUNDARY_SCOPE_IN_CONTRACT'
 if 'share_module.' in text: return 'OUTSIDE_P3_PRE_ROUTER_ENTRYPOINT_NO_SHARE_CODE_DELEGATION'
 return 'SOURCE_BOUND_CALLEE_OR_LOCAL_GUARD_CONSULT_FAMILY_CONTRACT'

COMMENT_GRAMMARS = {
 'athena-draft-ready-bridge': r'/athena-ready head=([0-9a-f]{40})',
 'athena-patch-bridge': '/athena-apply\nbase-sha: <exact PR head>\npatch-sha256: <exact digest>\n```diff\n<1..60000 bytes bounded patch>\n```',
 'current-shadow-history-cache-prime': '/athena-shadow-history-cache-prime',
 'current-shadow-sportybet-source-diagnostic': '/athena-shadow-source-diagnostic',
 'audit-fotmob-utc-native-xg-fresh-holdout-lineage': r'/athena-audit-fresh-holdout-lineage\nmain-sha: ([0-9a-f]{40})\nconfirm: READ_ONLY_ACTIONS_LINEAGE_AUDIT',
 'bridge-fotmob-fresh-holdout-continuity-receipts': r'/athena-mirror-fresh-holdout-continuity-receipt\nrun-id: ([1-9][0-9]*)\nconfirm: DURABILITY_ONLY_NO_ACQUISITION_V1',
 'watch-fotmob-fresh-holdout-scheduler-liveness': '/athena-repair-fresh-holdout-scheduler\nconfirm: CONTROL_PLANE_ONLY_NO_ACQUISITION',
 'p3-0-e1-owner-dispatch-bridge': '/athena-run-p3-e1',
}


def build_receipt():
 old=authenticate_scope(); inventory=authenticate_inventory(); matrix=read_json(MATRIX_PATH)
 base_rows={(r['workflow_path'],s['trigger_kind']):s for r in matrix['workflow_rows'] for s in r['trigger_surfaces']}
 identities={s['path']:s for s in inventory['sources']}; rows=[]
 for name,triggers in SCOPE.items():
  path=workflow_path(name); profile, grants, contract=CONTRACTS[name]
  sources=[path,*FAMILY_SOURCES[name]]
  for trigger in triggers:
   predecessor=base_rows[path,trigger]; auth=dict.fromkeys(AUTHORITY_FIELDS,'NONE'); auth['notification_authority']='GITHUB_CHECK_OR_LOG_ONLY'; auth.update(grants)
   if name=='watch-fotmob-fresh-holdout-scheduler-liveness' and trigger=='schedule': auth['workflow_dispatch_authority']='FIXED_FUTURE_FRESH_HOLDOUT_CONTINUITY_ONLY'
   partial=name in {'tests','athena-patch-bridge'}
   gaps=['provider_acquisition_authority','sportsbook_read_authority','share_code_authority','wager_authority','delivery_authority','notification_authority','external_storage_write_authority','network_authority_summary','dynamic_reachability_review_state'] if partial else []
   if partial:
    for field in gaps:
     if field in auth: auth[field]='EVIDENCE_GAP_DYNAMIC_TEST_TRANSPORT'
   edges=[{**e,'final_classification':edge_classification(name,trigger,e)} for p in sources for e in inventory['static_discovery_edges'].get(p,[])]
   inbound=[c for c in inventory['repository_callers'] if c['target_path']==path]
   outbound=[c for c in inventory['repository_callers'] if c['caller_path']==path]
   if name=='watch-fotmob-fresh-holdout-scheduler-liveness' and trigger=='issue_comment': outbound=[c for c in outbound if c['kind']!='FIXED_ACTIONS_DISPATCH']
   rows.append({
    'workflow_path':path,'trigger_kind':trigger,'workflow_source_sha256':identities[path]['normalized_source_sha256'],'workflow_git_blob_sha1':identities[path]['git_blob_sha1'],
    'supported_status':predecessor['supported_status'],'retained_reason':predecessor['retained_reason'],
    'authority_profile':profile,**auth,
    'credential_surface':{'github':inventory['workflow_metadata'][path]['permissions'],'jobs':inventory['workflow_metadata'][path]['job_permissions'],'production_secret_inputs':'NONE_DECLARED','token_bindings':inventory['workflow_metadata'][path]['token_bindings'],'environment_variable_names':inventory['workflow_metadata'][path]['environment_variable_names'],'artifact_service_token':'ACTION_MANAGED_IF_UPLOAD_PRESENT'},
    'network_authority_summary':'EVIDENCE_GAP_DYNAMIC_TEST_TRANSPORT' if partial else contract,
    'dynamic_reachability_review_state':'PARTIAL_DYNAMIC_TEST_TRANSPORT_BOUNDARY' if partial else 'SOURCE_BOUND_GUARDED_PATH_REVIEW_COMPLETE',
    'dynamic_reachability_edges':edges,'fail_closed_guards':{'contract':contract,'job_guards':inventory['workflow_metadata'][path]['job_guards'],'step_guards':inventory['workflow_metadata'][path]['step_guards']},
    'source_evidence':[identities[p] for p in sources],
    'historical_or_current_lifecycle':'CURRENT_PROTECTED_OR_CONTROL_PLANE_ROOT',
    'trigger_filters':inventory['workflow_metadata'][path]['trigger_filters'][trigger],
    'trigger_specific_contract':'SCHEDULE_ONE_UTC_TODAY_DATE' if name=='athena-ingest' and trigger=='schedule' else 'MANUAL_STRICTLY_INCREASING_1_TO_7_DATES' if name=='athena-ingest' else 'SCHEDULE_ONLY_PROSPECTIVE_DISPATCH' if name.startswith('watch-') and trigger=='schedule' else 'OWNER_COMMENT_REGISTRATION_REPAIR_NO_DISPATCH' if name.startswith('watch-') else 'EXACT_SOURCE_TRIGGER_FILTER_AND_GUARDS',
    'research_computation_authority':'PRICE_ALL_ROUTER_EVIDENCE_ONLY_NO_PORTFOLIO' if name=='p3-0-comparison-evidence-capture' else 'NONE_GRANTED_BY_THIS_TRIGGER',
    'command_grammar':COMMENT_GRAMMARS[name] if trigger=='issue_comment' else 'NOT_A_COMMENT_TRIGGER',
    'dispatch_input_contract':inventory['workflow_metadata'][path]['trigger_filters'][trigger] if trigger=='workflow_dispatch' else 'NOT_A_MANUAL_DISPATCH_TRIGGER',
    'workflow_run_upstream_binding':inventory['workflow_metadata'][path]['trigger_filters'][trigger] if trigger=='workflow_run' else 'NOT_A_WORKFLOW_RUN_TRIGGER',
    'dynamic_workflow_literals':inventory['workflow_metadata'][path]['dynamic_workflow_literals'],
    'inbound_dynamic_callers':inbound,'outbound_dynamic_targets':outbound,'static_repository_callers':inbound,'dynamic_repository_callers':'FIXED_SOURCE_TARGETS_PLUS_AUTHENTICATED_EXTERNAL_GITHUB_EVENT_CALLERS',
    'external_api_mutations':{k:v for k,v in auth.items() if k in ('release_write_authority','issue_comment_write_authority','pull_request_mutation_authority','branch_write_authority','workflow_dispatch_authority','external_storage_write_authority')},
    'workflow_control_authority':'GUARDED_PRIMARY_ENABLE_DISABLE_REGISTRATION' if name.startswith('watch-') else 'CI_CONCURRENCY_CANCEL_OLDER_SAME_GROUP' if name=='tests' else 'NONE',
    'evidence_publication_is_user_facing_delivery':False,'callee_provider_authority_transferred_to_bridge':False,
    'protected_research_production_model_backfill_price_router_portfolio_authority':'NONE' if 'holdout' in name else 'NOT_GRANTED_BY_THIS_REVIEW',
    'resolved':not partial,'unresolved_fields':gaps,
    'evidence_gap':'No global fail-closed network-denial fixture; all tests/test_*.py are dynamically selected; sampled monkeypatches cannot prove absence of every provider, sportsbook, SMTP or account transport. No live action observed or asserted.' if partial else None,
    'safest_next_action':'Separate source-only CI transport/caller review or independently approved global offline-boundary mission; do not execute live workflows or change runtime here.' if partial else None,
   })
 resolved=sum(r['resolved'] for r in rows)
 return seal({'schema_version':1,'policy_id':POLICY_ID,'repository':'Thabearr/ATHENA','master_issue':337,
  'base_main_sha':BASE_MAIN,'base_tree_sha':BASE_TREE,'workflow_tree_sha1':retention.v4.v3.WORKFLOW_TREE_SHA1,
  'evolution_ledger_sha256':retention.v4.v3.EVOLUTION_LEDGER_SHA256,'transition_count':14,'retirement_ledger_sha256':retention.v4.v3.P43_LEDGER_SHA256,'retired_workflow_count':3,
  'post_merge_ci_gate':{'run_id':37051054827,'head_sha':BASE_MAIN,'event':'push','conclusion':'success','syntax_and_shards_1_to_8_and_aggregate':'SUCCESS','observation':'READ_ONLY_GITHUB_METADATA_BEFORE_BRANCH_CREATION_NO_RERUN'},
  'predecessors':PREDECESSORS,'source_inventory':{'path':INVENTORY_PATH,'canonical_sha256':INVENTORY_SHA},
  'review_rows':rows,'scoped_workflow_count':15,'reviewed_surface_count':len(rows),'resolved_surface_count':resolved,'unresolved_surface_count':len(rows)-resolved,
  'global_unreviewed_surface_count_before':len(old['unreviewed_authority_surfaces']),'remaining_global_unreviewed_surface_count':len(old['unreviewed_authority_surfaces'])-resolved,
  'checkpoint_e_status':'INCOMPLETE','p4_4_status':'INCOMPLETE','review_grants_new_execution_authority':False,
  'actions':retention.ZERO_ACTIONS,'protected_semantic_delta':retention.ZERO_DELTA,
  'action_scope':'Operational effects; excludes authorized implementation branch/PR and final #337 evidence administration',
  'source_review_counter_while_open':'2/5','source_review_counter_if_owner_merges':'3/5','mandatory_source_reread_due':False,
  'terminal':'CORE_01D_AUTHORITY_REACHABILITY_PASS_A_REVIEW_READY_PARTIAL_DO_NOT_MERGE' if resolved!=21 else 'CORE_01D_AUTHORITY_REACHABILITY_PASS_A_REVIEW_READY_21_OF_53_SURFACES_REVIEWED_DO_NOT_MERGE'})

def strings(value):
 if isinstance(value,str): yield value
 elif isinstance(value,dict):
  for key,item in value.items(): yield from strings(key); yield from strings(item)
 elif isinstance(value,list):
  for item in value: yield from strings(item)

def validate_receipt(value, expected=None):
 rows=value['review_rows']; keys=[(r['workflow_path'],r['trigger_kind']) for r in rows]
 require(len(keys)==21 and len(set(keys))==21 and set(keys)==KEYS,'exact 21 Pass-A surface keys required')
 for row in rows:
  require(set(REQUIRED_FIELDS)<=set(row),'required authority dimension missing')
  if row['resolved']:
   require(not any(word in text.upper() for text in strings(row) for word in FORBIDDEN),'resolved row contains placeholder authority')
   require(not row['unresolved_fields'] and not any('EVIDENCE_GAP' in str(row[k]) for k in AUTHORITY_FIELDS),'unproved dimension marked resolved')
 require(value==(build_receipt() if expected is None else expected),'review differs from source-bound authority/edge truth')

def audit():
 value=read_json(RECEIPT_PATH);validate_receipt(value)
 return {k:value[k] for k in ('resolved_surface_count','unresolved_surface_count','remaining_global_unreviewed_surface_count','terminal')}|{'result':'PASS','receipt_sha256':value['canonical_sha256']}

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--write',action='store_true');parser.add_argument('--write-inventory',action='store_true');args=parser.parse_args()
 if args.write_inventory:
  value=build_inventory();(ROOT/INVENTORY_PATH).write_bytes(canonical_bytes(value));print(value['canonical_sha256'])
 elif args.write:
  value=build_receipt();(ROOT/RECEIPT_PATH).write_bytes(canonical_bytes(value));print(value['canonical_sha256'])
 else: print(json.dumps(audit(),sort_keys=True))
if __name__=='__main__':main()
