"""Current completion overlays only proven Pass-A rows; V1 remains historical."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import json
import types
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
APP01B_ADDITIVE_PATHS={
 'docs/product/app_01b_preview_admission.md',
 'tests/fixtures/core_01d_schedule/append-only-projections/app_01b/pre-d1-execution-envelope.py.txt',
 'tests/fixtures/core_01d/pass1-v1-source/test-core-01-schedule-date-disposition.py.txt',
}
# D2 changes current API/application sources that already existed in the
# immutable Pass-A tree. Their exact current bytes are authenticated by the
# append-only A2 inventory; keep those additive D2 changes out of the V1 view.
APP01C_ADDITIVE_PATHS={
 'scripts/audit_core_01d_checkpoint_e_completion.py',
 'scripts/audit_checkpoint_e_workflows.py',
 'scripts/audit_core_01d_checkpoint_e_completion_v2.py',
 'scripts/audit_core_01d_authority_reachability_review_a.py',
 'api/app_factory.py',
 'api/schemas.py',
 'api/server.py',
 'api/v1/common.py',
 'api/v1/exports.py',
 'api/v1/fixtures.py',
 'api/v1/runs.py',
 'docs/product/app_01c_versioned_api.md',
 'run_desktop.py',
 'services/athena_capability_service.py',
 'services/athena_read_service.py',
 'tests/fixtures/core_01d/app_01c_historical/api_server.py.b64',
 'tests/fixtures/core_01d/app_01c_historical/checkpoint_e_completion.py.b64',
 'tests/fixtures/core_01d/app_01c_historical/run_desktop.py.txt',
 'tests/fixtures/core_01d/app_01c_historical/test_api_error_handling.py.txt',
 'tests/fixtures/core_01d/app_01c_historical/test_product_baseline_v1.py.txt',
 'tests/test_api_error_handling.py',
 'tests/test_app_01a_local_shell.py',
 'tests/test_app_01b_preview_admission.py',
 'tests/test_app_01c_versioned_read_api.py',
 'tests/test_core_01d_ci_offline_transport_inventory_evolution.py',
 'tests/test_core_01d_exact_pr_trigger_disposition_b1.py',
 'tests/test_core_01d_frozen_artifact_replay_authority_b5.py',
 'tests/test_core_01d_owner_one_shot_issue_comment_authority_b3.py',
 'tests/test_core_01d_port02c_trigger_authority_b6.py',
 'tests/test_product_baseline_v1.py',
}
# D2 predecessor tree blob identities for changed, pre-existing sources that
# are not already projected by the APP-01A historical runtime/source view.
# These are pinned to the exact D1 base main at the APP-01C handoff.
APP01C_PREDECESSOR_BLOBS={
 'scripts/audit_core_01d_checkpoint_e_completion.py':'bef5bd7bcb3c27fe27cb6efc80a7e7f67e7c7de9',
 'scripts/audit_checkpoint_e_workflows.py':'19ddce133ba37ef63931f658e267a562c0cb15d0',
 'scripts/audit_core_01d_checkpoint_e_completion_v2.py':'4fcd597964c8ccddeb0822e6c326f45712547e60',
 'scripts/audit_core_01d_authority_reachability_review_a.py':'036e483000ce07b2dab5fb7136e4992820026262',
 'api/app_factory.py':'715fdbc051962af2c8f51700b4b368af1ec88015',
 'api/schemas.py':'addb7c8d333c6c723192629d58738588953b55e9',
 'api/server.py':'1e8d3b8968a37eed78741e018fa4da057578223c',
 'run_desktop.py':'39c4cf8c780eb2831b637a69ff0648b6eb465874',
 'services/athena_capability_service.py':'25d4e8cf609effec84624219cebacb40a30437c2',
 'tests/test_api_error_handling.py':'a827e02b95779ca0478ffa74db34e41de1e04b42',
 'tests/test_app_01a_local_shell.py':'2176d1c0e6ceb1db1457f65a0f9325a39ea45aa9',
 'tests/test_app_01b_preview_admission.py':'7733431bb44801e46e6804144099e2779deba8ee',
 'tests/test_core_01d_ci_offline_transport_inventory_evolution.py':'85e9436f7c70c5e970764e5b4e554ca5f939f39d',
 'tests/test_core_01d_exact_pr_trigger_disposition_b1.py':'e49b70b8876f5826dddd46e7e822be7f594edb71',
 'tests/test_core_01d_frozen_artifact_replay_authority_b5.py':'ed3f8ae3a28dcf40d33bcff2121dd8f983206999',
 'tests/test_core_01d_owner_one_shot_issue_comment_authority_b3.py':'8ecc7eab8dc5514512a6c7a68e006556c928ad09',
 'tests/test_core_01d_port02c_trigger_authority_b6.py':'594a7b4f8c5a9d798d13af2f4c7e35635371bbb6',
 'tests/test_product_baseline_v1.py':'2d552f49cf84462bd1b32e86eea2a96ee0570b64',
}
INCIDENT_20261010_PREDECESSOR_BLOBS={
 'artifacts/product/data_01c_app_store_complete_v1.json':'6727c011ead7da533a8af00ef4c4b352ea35492b',
 'domain/current_shadow_sportybet_pc_upcoming_reconciliation.py':'1aa242e6db460c66b388b1acfd43859d382c82f9',
 'scripts/audit_p4_4q_pc_upcoming_simple_tournament_identity.py':'45b046ad0e6f44823561fe39ab43d03b80c2eab5',
 'scripts/audit_p4_4r_shadow_runtime_composition_stabilization.py':'ac9c320157b4230288203e67c3e31df9914ad5b8',
 'scripts/verify_p3_0_e1_live_readiness.py':'968781d51a3d2b2a7ebb6aa85d998ba888aa47dc',
 'tests/test_current_shadow_sportybet_pc_upcoming_reconciliation.py':'81d71a20f0dcca8204eeb7b8d8a9c6b268f09ef5',
 'tests/test_p3_0_e1_source_diagnostics_auditor.py':'ddf261c7bbda34331dc5590ba68fbbf4d6a3ee81',
 'tests/test_p4_4n_sportybet_team_label_shape_compatibility.py':'5bef37d4a8f25b9c693441c089ca723b7ee0bdd2',
 'tests/test_p4_4o_pc_upcoming_stable_epoch_recovery.py':'3e16c2df91f4fab539bca51b5bd9d077b15d1fec',
 'tests/test_p4_4o_pc_upcoming_stable_epoch_recovery_audit.py':'6725e92b83c55bc8d510f3177d0fc6f8e50df051',
 'tests/test_p4_4p_pc_upcoming_preparse_response_evidence.py':'1355855d4427d401307f9d02ff60e5439eb7424f',
 'tests/test_p4_4q_pc_upcoming_simple_tournament_identity.py':'7bb5659ee6020c0c9f36ff105297c5048c9f83d7',
}
INCIDENT_20261010_NEW_PATHS={
 'tests/fixtures/core_01d/inc_20261010/inc_20261010_pc_upcoming_bounded_epoch_stabilization_v1.json',
 'scripts/audit_inc_20261010_pc_upcoming_bounded_epoch_stabilization.py',
 'tests/test_inc_20261010_pc_upcoming_bounded_epoch_stabilization.py',
 'tests/fixtures/core_01d/inc_20261010/pc-upcoming-reconciliation-predecessor.py.txt',
 'tests/fixtures/core_01d/inc_20261010/verify-p3-live-readiness-predecessor.py.txt',
 'tests/fixtures/core_01d/inc_20261010/audit-p44q-simple-tournament-identity-predecessor.py.txt',
 'tests/fixtures/core_01d/inc_20261010/audit-p44r-runtime-composition-predecessor.py.txt',
 'tests/fixtures/core_01d/inc_20261010/test-current-shadow-pc-upcoming-reconciliation-predecessor.py.txt',
 'tests/fixtures/core_01d/inc_20261010/test-p3-e1-source-diagnostics-predecessor.py.txt',
 'tests/fixtures/core_01d/inc_20261010/test-p44n-team-label-shape-predecessor.py.txt',
 'tests/fixtures/core_01d/inc_20261010/test-p44o-stable-epoch-recovery-predecessor.py.txt',
 'tests/fixtures/core_01d/inc_20261010/test-p44o-stable-epoch-recovery-audit-predecessor.py.txt',
 'tests/fixtures/core_01d/inc_20261010/test-p44p-preparse-response-evidence-predecessor.py.txt',
 'tests/fixtures/core_01d/inc_20261010/test-p44q-simple-tournament-identity-predecessor.py.txt',
}
INCIDENT_20261010_CURRENT_PATHS=set(INCIDENT_20261010_PREDECESSOR_BLOBS)|INCIDENT_20261010_NEW_PATHS
RUN_01B_ADDITIVE_PATHS={
 'artifacts/product/run_01b_worker_lifecycle_v1.json',
 'docs/product/run_01b_worker_lifecycle.md',
 'tests/fixtures/core_01d/run_01a_historical/pr458/athena-job-service-predecessor.py.txt',
 'tests/fixtures/core_01d/run_01a_historical/pr458/run-repository-predecessor.py.txt',
}
RUN_02A_PRE_ADDITIVE_PATHS={
 'artifacts/product/run_02a_pre_durable_share_send_v1.json',
 'docs/product/run_02a_pre_durable_share_send.md',
 'scripts/audit_run_02a_pre_durable_share_send.py',
 'tests/fixtures/core_01d/run_01b_historical/source_bytes_v1.json',
 'tests/fixtures/core_01d/run_02a_pre_historical/worker-entry-predecessor.py.txt',
 'tests/fixtures/core_01d/run_02a_pre_historical/direct-share-predecessor.py.txt',
 'tests/fixtures/core_01d/run_02a_pre_historical/auth-worker-boundary-predecessor.py.txt',
 'tests/fixtures/core_01d/run_02a_pre_historical/run-repository-pr463-base.py.txt',
 'tests/fixtures/core_01d/run_02a_pre_historical/athena-job-service-pr463-base.py.txt',
 'tests/fixtures/core_01d/run_02a_pre_historical/worker-entry-pr463-base.py.txt',
 'tests/fixtures/core_01d/run_02a_pre_historical/test-worker-launcher-pr463-base.py.txt',
 'tests/fixtures/core_01d/run_02a_pre_historical/audit-run-01a-admission-pr463-base.py.txt',
 'tests/fixtures/core_01d/run_02a_pre_historical/auth-worker-boundary-pr463-base.py.txt',
 'tests/fixtures/core_01d/run_01a_historical/pr463/run-desktop-predecessor.py.txt',
 'tests/fixtures/core_01d/run_01a_historical/pr463/test-run-01a-durable-admission-predecessor.py.txt',
 'runtime/worker_startup_gate.py',
 'services/worker_process_control.py',
 'services/recovery_service.py',
 'tests/native/test_run_02a_process_tree.py',
 'tests/test_run_02a_recovery.py',
 'tests/test_run_02a_pre_durable_share_send.py',
 'tests/test_run_01b_worker_lifecycle.py',
}
RUN_02A_PRE_PREDECESSOR_BLOBS={
 'scripts/audit_auth_01_analysis_only_shadow_worker_boundary.py':'07ce59ed824d40ef1be12686537c4e355e565c30',
 'scripts/audit_lg_a_worker_launch_failure_remediation.py':'0e8a349d49ad2cb9a41a709ad134e48e6c766069',
 'runtime/worker_entry.py':'77d8888a4b007f9bb0967409a23e826f97338c90',
 'database/run_repository.py':'103bcbf4e06a90ef768a122408235b9d9267fe6b',
 'services/athena_job_service.py':'d0291cc9a25b1372d86464e2fb54ac97f1fc7f98',
 'tests/test_run_01a_durable_admission.py':'2a256f2a52761733280725f21b66e4b8a1bf2e24',
 'tests/test_worker_launcher.py':'973e00174e8967569e98fbf15bc58d2c13a3a20d',
 'scripts/audit_run_01a_durable_admission.py':'42d7550bec98ddc25b5999b20ed6195a442cd69f',
 'scripts/sportybet_direct_share_bridge.py':'681ce2a043a334dcb8523c81d092369d6540e6d5',
}
RUN_02A_PRE_PREDECESSOR_SOURCES={
 'tests/test_worker_launcher.py':(
  'tests/fixtures/core_01d/run_02a_pre_historical/test-worker-launcher-pr463-base.py.txt',
  '973e00174e8967569e98fbf15bc58d2c13a3a20d',
  'bbcaeef0bab1e60aa6a8e74ccdacedad87fe83295825041ce47a8a81c25802f4',
 ),
 'scripts/audit_run_01a_durable_admission.py':(
  'tests/fixtures/core_01d/run_02a_pre_historical/audit-run-01a-admission-pr463-base.py.txt',
  '42d7550bec98ddc25b5999b20ed6195a442cd69f',
  '90babe8cb97c9d16969fa00b721fad01a84e54aa838e38241663152def00fee8',
 ),
}
PR459_HISTORICAL_SOURCE_FORWARD_PATHS={
 'tests/fixtures/core_01d/pr459_live_trigger_incident/test-p4-3d-retirement-audit-extensibility-predecessor.py.txt',
 'docs/architecture/core_01d_pr459_live_trigger_incident.md',
 'tests/fixtures/core_01d/pr459_live_trigger_incident/create-direct-share-workflow-b4-predecessor.yml.txt',
 'tests/fixtures/core_01d/pr459_live_trigger_incident/p4-3-workflow-retirement-ledger-predecessor.py.txt',
 'tests/fixtures/core_01d/pr459_live_trigger_incident/run-02a-pre-base.py.txt',
 'tests/fixtures/core_01d/pr459_live_trigger_incident/prove-direct-share-workflow-b4-predecessor.yml.txt',
 'tests/fixtures/core_01d/pr459_live_trigger_incident_v1.json',
 'tests/fixtures/core_01d/pr459_live_trigger_incident/incident-audit-v208-predecessor.py.txt',
 'tests/fixtures/core_01d/run_01a_historical/pr461/audit-data-01b-durable-run-state-predecessor.py.txt',
 'tests/fixtures/core_01d/run_01a_historical/pr461/audit-data-01c-restore-portability-predecessor.py.txt',
 'tests/fixtures/core_01d/run_02a_pre_historical/app-store-complete-v154.py.txt',
 'tests/fixtures/core_01d/run_02a_pre_historical/b4-trigger-authority-predecessor.py.txt',
}

APP01C_NEW_PATHS={
 'api/v1/common.py','api/v1/exports.py','api/v1/fixtures.py','api/v1/runs.py',
 'docs/product/app_01c_versioned_api.md','services/athena_read_service.py',
 'tests/fixtures/core_01d/app_01c_historical/api_server.py.b64',
 'tests/fixtures/core_01d/app_01c_historical/checkpoint_e_completion.py.b64',
 'tests/fixtures/core_01d/app_01c_historical/run_desktop.py.txt',
 'tests/fixtures/core_01d/app_01c_historical/test_api_error_handling.py.txt',
 'tests/fixtures/core_01d/app_01c_historical/test_product_baseline_v1.py.txt',
 'tests/test_app_01c_versioned_read_api.py',
}
# Exact filtered scope digest after D2 added its authenticated APP01C paths.
# The origin/main and candidate projections both hash to this identity.
UNCHANGED_SCOPE_SHA='d7298582950c19d3be973d81871da276cccf6174b2aef726bd5dcb638f6a7cf3'
# Current additive authority-review documents are authenticated by their own
# pass auditors, completion overlays, and A2 generation chain. Keep only these
# exact additive paths out of the immutable Pass-A historical tree projection.
PASS_A_HISTORICAL_BLOBS={
 'tests/test_core_01d_workflow_consolidation.py':'65fd881b593f3e0537a7965ac97441d1dc1bc16b',
 'domain/execution_envelope.py':'8f0a84db708fef11fabb857b21b1322cb5b5a36e',
 'scripts/audit_core_01_schedule_date_disposition.py':'6f8d453cee00a13865c984b9a80880678b4fd84c',
 'tests/test_core_01_schedule_date_disposition.py':'f658773457d6a46bbd25f6b2a5636fff019b0043',
 # Preserve the exact P4.3 source reviewed before PR #461's narrow resolver
 # change. Current bytes remain authenticated by A2 and the focused audit.
 'scripts/audit_p4_3_workflow_retirement_ledger.py':'77927732b2abc2b13f20a4979ad7092307873900',
 # P4 evolution and retained-status source predecessors are projected from
 # the authenticated D5 source snapshot / A2 fixture below; do not replace
 # those earlier identities with their later main-base blobs.
 'tests/test_core_01d_historical_retention_acceptance.py':'9ac2d450e29c0faf5fd471f06f3f1ae0dfdaa51d',
 'tests/test_core_01d_canonical_drive_transfer_completed_history.py':'facfa6cd0932972d729215b8121942661a75cc54',
 'tests/test_p4_3d_retirement_audit_extensibility.py':'5e7de20231b2455f15fdc20c4fd21e1720714f64',
 # PR #461 adds these already-existing Pass-A workflow files to A2's current
 # source inventory. Preserve their exact pre-PR blobs in the immutable Pass-A
 # projection while A2 independently authenticates their current successors.
 '.github/workflows/create-saturday-2026-08-22-sportybet-direct-20-code.yml':'84fd86333c34e8b6e27afe7f9d6e0e1c4234e93c',
 '.github/workflows/prove-sportybet-direct-share-code.yml':'18e5656c232102df141aaa614aca3d5d7575ec5b',
}
B1_ADDITIVE_EVIDENCE_PATHS={
 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v3.json',
 'tests/fixtures/core_01d/exact-pr-trigger-disposition-b1-source-inventory-v1.json',
 'tests/fixtures/core_01d/core-01d-exact-pr-trigger-disposition-b1-v1.json',
 'tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v4.json',
 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v4.json',
 'tests/fixtures/core_01d/historical-warehouse-transfer-authority-b2-source-inventory-v1.json',
 'tests/fixtures/core_01d/core-01d-historical-warehouse-transfer-authority-b2-v1.json',
 'tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v5.json',
 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v5.json',
 'tests/fixtures/core_01d/owner-one-shot-issue-comment-authority-b3-source-inventory-v1.json',
 'tests/fixtures/core_01d/core-01d-owner-one-shot-issue-comment-authority-b3-v1.json',
 'tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v6.json',
 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v6.json',
 'tests/fixtures/core_01d/sportybet-current-trigger-authority-b4-source-inventory-v1.json',
 'tests/fixtures/core_01d/core-01d-sportybet-current-trigger-authority-b4-v1.json',
 'tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v7.json',
 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v7.json',
 'tests/fixtures/core_01d/frozen-artifact-replay-authority-b5-source-inventory-v1.json',
 'tests/fixtures/core_01d/core-01d-frozen-artifact-replay-authority-b5-v1.json',
 'tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v8.json',
 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v8.json',
 'tests/fixtures/core_01d/port02c-trigger-authority-b6-source-inventory-v1.json',
 'tests/fixtures/core_01d/core-01d-port02c-trigger-authority-b6-v1.json',
 'tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v9.json',
 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v9.json',
 'tests/fixtures/core_01d/win-either-half-trigger-authority-b7-source-inventory-v1.json',
 'tests/fixtures/core_01d/core-01d-win-either-half-trigger-authority-b7-v1.json',
 'tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v10.json',
}
# Existing offline P3 tests and the source-bound Tests shard selector publish
# these local products. This audit never consumes them as authority proof.
LOCAL_TEST_PRODUCTS={'.pytest-shard-files','p3-0-e1-live-readiness.json','artifacts/p3-0-comparison-evidence/p3-0-e1-live-readiness.json'}


def unchanged_inventory(raw):
 return b''.join(line for line in raw.splitlines(keepends=True) if line.split(b'\t',1)[1].strip().decode() not in ALLOWED_PASS_A_PATHS|APP01B_ADDITIVE_PATHS|APP01C_ADDITIVE_PATHS)

def a2_generation_additions(a2):
 latest=a2.authenticate_inventory()
 predecessor=a2.read_generation(a2.inventory_generation_path(2))
 predecessor_paths={row['path'] for row in predecessor['source_identities']}
 latest_paths={row['path'] for row in latest['source_identities']}
 return latest_paths-predecessor_paths

def app_successor_paths():
 from scripts import audit_app_01a_local_shell as app
 return app.authenticated_historical_paths()[0]

def current_successor_inventory_paths(a2):
 # V3 onward is an authenticated, contiguous additive evidence chain.
 return {path for generation,path in a2.discover_inventory_generations() if generation>=3}

def pass_a_preserved_a2_successor_paths(a2):
 # These workflow files were already present in the immutable Pass-A tree
 # before A2 began authenticating their current offline-only successors.
 paths=set(a2.A2_SUCCESSOR_WORKFLOWS)
 review.require(paths <= set(PASS_A_HISTORICAL_BLOBS),
                'A2 successor workflow is missing its immutable Pass-A blob pin')
 return paths

def pass_a_nonhistorical_a2_generation_paths(a2,generation_additions):
 # A2 successor workflows are additions to the A2 chain but not new Pass-A
 # paths: their predecessor bytes were already part of the immutable tree.
 return set(generation_additions)-pass_a_preserved_a2_successor_paths(a2)

def a2_historical_projection(raw):
 from scripts import audit_core_01d_ci_offline_transport_boundary as a2
 # Authenticate all current caller/guard source before using a historical view.
 latest=a2.authenticate_inventory()
 from scripts import audit_run_02a_pre_durable_share_send as run02a
 # Reuse the retained V154 predecessor seam for the exact E3-evolved E1
 # sources. It independently checks the fixture Git blob/LF hash, its
 # historical A2 identity, and the current source bytes against latest A2.
 for path in ('database/run_repository.py','services/athena_job_service.py'):
  predecessor=run02a.RUN_02A_CURRENT_SOURCE_PREDECESSORS.get(path)
  review.require(predecessor is not None
                 and predecessor[1]==RUN_02A_PRE_PREDECESSOR_BLOBS[path],
                 'E3 Pass-A predecessor differs from retained RUN-02A source seam: '+path)
  run02a.historical_prerequisite_source_bytes(path,latest=latest)
 from scripts import audit_run_01a_durable_admission as e1
 path='tests/test_run_01a_durable_admission.py'
 predecessor=e1._predecessor_bytes(path)
 predecessor_blob=hashlib.sha1(b'blob '+str(len(predecessor)).encode()+b'\0'+predecessor).hexdigest()
 review.require(predecessor_blob==RUN_02A_PRE_PREDECESSOR_BLOBS[path],
                'E3 Pass-A E1 test predecessor differs from its authenticated fixture')
 # tests/test_worker_launcher.py is an existing Pass-A path evolved by E3,
 # not a newly admitted test path. Preserve its exact V216/base bytes in the
 # historical tree while A2 independently authenticates the current source.
 path='tests/test_worker_launcher.py'
 fixture,blob,digest=RUN_02A_PRE_PREDECESSOR_SOURCES[path]
 review.require(RUN_02A_PRE_PREDECESSOR_BLOBS[path]==blob,
                'E3 Pass-A worker-launcher predecessor blob map disagrees')
 for logical in (path,fixture):
  candidate=ROOT/logical
  review.require(candidate.is_file() and not any(p.is_symlink() for p in (candidate,*candidate.parents)),
                 'E3 Pass-A worker-launcher predecessor requires regular source/fixture')
 current_sources={row['path']:row['lf_source_sha256'] for row in latest['source_identities']}
 current_bytes=a2.lf((ROOT/path).read_bytes())
 review.require(hashlib.sha256(current_bytes).hexdigest()==current_sources.get(path),
                'current E3 worker-launcher test differs from authenticated A2')
 retained=a2.read_generation(a2.inventory_generation_path(216))
 retained_sources={row['path']:row['lf_source_sha256'] for row in retained['source_identities']}
 predecessor_bytes=a2.lf((ROOT/fixture).read_bytes())
 predecessor_blob=hashlib.sha1(b'blob '+str(len(predecessor_bytes)).encode()+b'\0'+predecessor_bytes).hexdigest()
 review.require(hashlib.sha256(predecessor_bytes).hexdigest()==digest
                and predecessor_blob==blob and retained_sources.get(path)==digest,
                'E3 Pass-A worker-launcher predecessor differs from authenticated V216 fixture')
 # The E1 admission auditor itself was already in the Pass-A tree at the
 # current main base. Preserve that exact main blob in the historical view;
 # its current E3 successor remains independently authenticated by A2.
 path='scripts/audit_run_01a_durable_admission.py'
 fixture,blob,digest=RUN_02A_PRE_PREDECESSOR_SOURCES[path]
 for logical in (path,fixture):
  candidate=ROOT/logical
  review.require(candidate.is_file() and not any(p.is_symlink() for p in (candidate,*candidate.parents)),
                 'E3 Pass-A E1-auditor predecessor requires regular source/fixture')
 current_sources={row['path']:row['lf_source_sha256'] for row in latest['source_identities']}
 current_bytes=a2.lf((ROOT/path).read_bytes())
 review.require(hashlib.sha256(current_bytes).hexdigest()==current_sources.get(path),
                'current E3 E1 auditor differs from authenticated A2')
 predecessor_bytes=a2.lf((ROOT/fixture).read_bytes())
 predecessor_blob=hashlib.sha1(b'blob '+str(len(predecessor_bytes)).encode()+b'\0'+predecessor_bytes).hexdigest()
 review.require(hashlib.sha256(predecessor_bytes).hexdigest()==digest
                and predecessor_blob==blob
                and RUN_02A_PRE_PREDECESSOR_BLOBS[path]==blob,
                'E3 Pass-A E1-auditor predecessor differs from exact base fixture')
 v1.authenticate_fresh_holdout_20261015_evidence()
 from scripts import audit_core_01d_pr459_live_trigger_incident as incident
 incident.historical_incident_source()
 preserved_a2_successors=pass_a_preserved_a2_successor_paths(a2)
 from scripts import audit_app_01a_local_shell as app
 from scripts import audit_data_01c_restore_portability as d5
 review.require(not (set(PASS_A_HISTORICAL_BLOBS) & set(app.PATHS)),
                'Pass-A blob override must not supersede authenticated APP predecessor projection')
 d5_predecessor_paths=set(d5.snapshot()['sources'])|set(d5.HISTORICAL_A2_SOURCE_FIXTURES)
 review.require(not (set(PASS_A_HISTORICAL_BLOBS)&d5_predecessor_paths),
                'Pass-A blob override must not supersede authenticated D5/A2 predecessor projection')
 raw=app.historical_tree_projection(raw)
 # The immutable Pass-A projection predates the generic A2 inventory
 # generation chain. Exclude only Python sources first admitted after V2;
 # the latest generation authenticates their exact current bytes, while V2
 # remains the fixed comparison boundary for this historical projection.
 predecessor=a2.read_generation(a2.inventory_generation_path(2))
 predecessor_paths={row['path'] for row in predecessor['source_identities']}
 latest_paths={row['path'] for row in latest['source_identities']}
 generation_additions=pass_a_nonhistorical_a2_generation_paths(
  a2,latest_paths-predecessor_paths)
 # Authenticated A2 successor inventory documents are additive evidence, not
 # part of the immutable Pass-A historical tree. Discover their contiguous
 # chain from V3 onward after authenticate_inventory has verified it.
 successor_inventory_paths=current_successor_inventory_paths(a2)
 new_paths=(a2.A2_PATHS-preserved_a2_successors-ALLOWED_PASS_A_PATHS-set(a2.HISTORICAL_TEST_BLOBS))|generation_additions|successor_inventory_paths|B1_ADDITIVE_EVIDENCE_PATHS|APP01B_ADDITIVE_PATHS|APP01C_NEW_PATHS|INCIDENT_20261010_NEW_PATHS|RUN_01B_ADDITIVE_PATHS|RUN_02A_PRE_ADDITIVE_PATHS|PR459_HISTORICAL_SOURCE_FORWARD_PATHS|v1.FRESH_HOLDOUT_20261015_ADDITIVE_PATHS|v1.FRESH_HOLDOUT_20261014_ADDITIVE_PATHS
 for path in review.FRESH_HOLDOUT_20261014_PREDECESSOR_SOURCES:
  review.source_bytes(path)
 rows=[]
 for line in raw.splitlines(keepends=True):
  path=line.split(b'\t',1)[1].strip().decode()
  if path in new_paths:continue
  if path in v1.FRESH_HOLDOUT_20261014_PREDECESSOR_BLOBS:
   line=('100644 blob '+v1.FRESH_HOLDOUT_20261014_PREDECESSOR_BLOBS[path]+'\t'+path+'\n').encode()
  elif path in RUN_02A_PRE_PREDECESSOR_BLOBS:
   line=('100644 blob '+RUN_02A_PRE_PREDECESSOR_BLOBS[path]+'\t'+path+'\n').encode()
  elif path in INCIDENT_20261010_PREDECESSOR_BLOBS:
   line=('100644 blob '+INCIDENT_20261010_PREDECESSOR_BLOBS[path]+'\t'+path+'\n').encode()
  elif path in PASS_A_HISTORICAL_BLOBS:
   line=('100644 blob '+PASS_A_HISTORICAL_BLOBS[path]+'\t'+path+'\n').encode()
  elif path in a2.HISTORICAL_TEST_BLOBS:
   line=('100644 blob '+a2.HISTORICAL_TEST_BLOBS[path]+'\t'+path+'\n').encode()
  elif path in APP01C_PREDECESSOR_BLOBS and path not in app.PATHS:
   line=('100644 blob '+APP01C_PREDECESSOR_BLOBS[path]+'\t'+path+'\n').encode()
  rows.append(line)
 return b''.join(rows)

def authenticate_current_scope():
 from scripts import audit_core_01d_ci_offline_transport_boundary as a2
 generation_additions=a2_generation_additions(a2)
 successor_inventory_paths=current_successor_inventory_paths(a2)
 allowed=ALLOWED_PASS_A_PATHS|APP01B_ADDITIVE_PATHS|APP01C_ADDITIVE_PATHS|a2.A2_PATHS|B1_ADDITIVE_EVIDENCE_PATHS|generation_additions|successor_inventory_paths|app_successor_paths()|INCIDENT_20261010_CURRENT_PATHS|RUN_01B_ADDITIVE_PATHS|RUN_02A_PRE_ADDITIVE_PATHS|PR459_HISTORICAL_SOURCE_FORWARD_PATHS|set(RUN_02A_PRE_PREDECESSOR_BLOBS)|v1.FRESH_HOLDOUT_20261015_ADDITIVE_PATHS|v1.FRESH_HOLDOUT_20261014_ADDITIVE_PATHS|set(v1.FRESH_HOLDOUT_20261014_PREDECESSOR_BLOBS)
 git=review.retention.v4.v3._git
 review.require(review.sha256(unchanged_inventory(a2_historical_projection(git('ls-tree','-r','HEAD'))))==UNCHANGED_SCOPE_SHA,'Pass-A runtime/workflow/ledger/historical source change outside bounded evidence scope')
 review.require(set(git('diff','--name-only','HEAD').decode().splitlines())<=allowed,'unapproved dirty source in Pass A or its exact A2-generation/evidence seam')
 review.require(set(git('ls-files','--others','--exclude-standard').decode().splitlines())<=allowed|LOCAL_TEST_PRODUCTS,'unapproved untracked source in Pass A or its exact A2-generation/evidence seam')
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
   generation_additions=a2_generation_additions(a2)
   return b''.join(line for line in raw.splitlines(keepends=True) if line.strip().decode() not in NEW_PASS_A_PATHS|APP01B_ADDITIVE_PATHS|APP01C_ADDITIVE_PATHS|a2.A2_PATHS|B1_ADDITIVE_EVIDENCE_PATHS|generation_additions|app_successor_paths()|INCIDENT_20261010_CURRENT_PATHS|RUN_02A_PRE_ADDITIVE_PATHS|PR459_HISTORICAL_SOURCE_FORWARD_PATHS|set(RUN_02A_PRE_PREDECESSOR_BLOBS)|v1.FRESH_HOLDOUT_20261015_ADDITIVE_PATHS|v1.FRESH_HOLDOUT_20261014_ADDITIVE_PATHS|set(v1.FRESH_HOLDOUT_20261014_PREDECESSOR_BLOBS))
  return raw
 original_identity=module._source_identity
 def projected_identity(path,**kwargs):
  from scripts import audit_data_01c_restore_portability as portability
  if path==portability.WORKFLOW:
   portability.authenticate_workflow()
   return {'path':path,**portability.identity(portability.predecessor_source(path))}
  from scripts import audit_core_01d_sportybet_current_trigger_authority_b4 as b4
  if path in b4.B4_WORKFLOW_PREDECESSORS:
   return {'path':path,**portability.identity(b4._historical_b4_workflow_bytes(path))}
  return original_identity(path,**kwargs)
 module._git=projected
 module._source_identity=projected_identity
 try: yield
 finally:
  module._git=original
  module._source_identity=original_identity


def historical_v1_receipt():
 value=review.authenticate_json(review.COMPLETION_V1,review.COMPLETION_V1_SHA)
 source=review.source_bytes('scripts/audit_core_01d_checkpoint_e_completion.py')
 historical=types.ModuleType('_athena_checkpoint_e_completion_v1')
 historical.__file__=str(review.ROOT/review.HISTORICAL_CHECKPOINT_E_SOURCE)
 exec(compile(source,historical.__file__,'exec'),historical.__dict__)
 with historical_v1_git_view():
  expected=historical.build_receipt()
  historical.validate_receipt(value,expected)
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
