"""Audit the supplementary CORE-01D retained-workflow status receipt offline.

This audit records explicit retention and missing-evidence disposition. It does
not grant deletion, migration, provider, replay, or completion authority and it
does not use volatile Actions-run state to classify retained capabilities.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
BASE_MAIN_SHA = "0e6d2c622ef7a12f82c4405d80906f49d97b523d"
BASE_TREE_SHA = "fed8664d63391aefdbd48197375e0ecf331b733c"
WORKFLOW_TREE_SHA1 = "9060b6fb263febc45332a7cf9c9da8448284b471"
POLICY_ID = "ATHENA_CORE_01D_RETAINED_WORKFLOW_STATUS_V1"
RECEIPT_PATH = "artifacts/architecture/core_01d_retained_workflow_status_v1.json"
MATRIX_V2_PATH = "artifacts/architecture/checkpoint_e_workflow_capability_matrix_v2.json"
CHECKPOINT_V2_PATH = "artifacts/architecture/checkpoint_e_workflow_consolidation_v2.json"
SCHEDULE_RECEIPT_PATH = "artifacts/architecture/core_01d_scheduled_shadow_ownership_v1.json"
EVOLUTION_PATH = "artifacts/architecture/p4_workflow_evolution_ledger_v1.json"

PREDECESSOR_V1_MATRIX_SHA256 = "9eb6e3fb35c7a58195a789aaf357fc35374b6f830f7da289ceeb3a84e403c815"
PREDECESSOR_V1_RECEIPT_SHA256 = "7a0d0f0bd3e448e9c9643954b20d4a8b7aab17b93cc28116ffab22452ba146ab"
PREDECESSOR_V2_MATRIX_SHA256 = "3c3cfec8b37e55161b24185941e72c3e096a00f38456a2c07a9072b62e31e5b7"
PREDECESSOR_V2_RECEIPT_SHA256 = "af167895b51d19271766fdab99e6da645da8f579dbc9159df100dcea41f5cc23"
SCHEDULE_OWNERSHIP_RECEIPT_SHA256 = "8e83fd5443149af74e14ceea44766809d1858ce856772a6500b8f55e073afde6"
EVOLUTION_LEDGER_SHA256 = "b582a5ba8a31ddfba94324f8869dd253460dcc01102ef356327a3337275b8335"

EXTERNAL_REPORTS = {
    "recovery_receipt_json": {
        "filename": "athena-checkpoint-e-artifact-retention-recovery-v1.json",
        "sha256": "0934cc3b511e8fee8e4fee24b0e89e0180f1869df0eec968f4718e67ba766e26",
    },
    "consumer_disposition_json": {
        "filename": "athena-checkpoint-e-artifact-consumer-disposition-review-v1.json",
        "sha256": "f07c92c6d7a51c2b3e49d991ec114f5e2b3b7c6a7ffd4856cec0f2e485371464",
    },
    "consumer_disposition_markdown": {
        "filename": "athena-checkpoint-e-artifact-consumer-disposition-review-v1.md",
        "sha256": "107175dcb8cd31b5969675598f2e4d7aaf71dece5135172d3542cb7d4214553c",
    },
}

ARTIFACT_IDS = (
    "9249856559", "9422055017", "9437181220", "9266604353",
    "9274313978", "9275052993", "9292984849", "9491418446",
)
EXPECTED_REFERENCE_LINE_COUNTS = {
    "9249856559": {"all": 42, "workflow": 3},
    "9422055017": {"all": 11, "workflow": 3},
    "9437181220": {"all": 17, "workflow": 11},
    "9266604353": {"all": 11, "workflow": 3},
    "9274313978": {"all": 9, "workflow": 2},
    "9275052993": {"all": 8, "workflow": 2},
    "9292984849": {"all": 4, "workflow": 1},
    "9491418446": {"all": 6, "workflow": 2},
}

NO_AUTHORITY = {
    "deletion_authorized": False,
    "retirement_authorized": False,
    "trigger_change_authorized": False,
    "caller_migration_authorized": False,
    "provider_reacquisition_authorized": False,
    "evidence_substitution_authorized": False,
    "synthetic_backfill_authorized": False,
    "replay_authorized": False,
}

BLOCKERS = [
    {
        "id": "PROTECTED_FRESH_HOLDOUT_PR119_EXACT_FALLBACK_NOT_DURABLY_RECOVERED",
        "artifact_ids": [9249856559],
        "reason": "Protected prospective fresh-holdout retains a conditional exact ZIP fallback behind a distinct PR119 projection.",
    },
    {
        "id": "OWNER_GATED_PR145_FEATURE_EVIDENCE_NOT_DURABLY_RECOVERED",
        "artifact_ids": [9275052993, 9292984849],
        "reason": "PR145 remains owner-gated; 9275052993 is a hard exact input and 9292984849 is preserved only as forensic pre-attempt history.",
    },
    {
        "id": "CANONICAL_HISTORY_TRANSFER_SOURCE_NOT_FULLY_DURABLE",
        "artifact_ids": [9491418446],
        "reason": "The exact archive is not recovered; transfer pieces 011-021 are missing and the reported pieces are not reverified.",
    },
    {
        "id": "HISTORICAL_REPLAY_ARCHIVES_UNAVAILABLE",
        "artifact_ids": [9422055017, 9437181220, 9266604353, 9274313978],
        "reason": "Exact historical archives remain unavailable for replay/audit. These are retention defects, not proof of current product-runtime blockage or retirement authority.",
    },
]


ARTIFACTS = [
    {
        "artifact_id": 9249856559,
        "run_id": 31887523012,
        "name": "fotmob-ordinary-ft-source-history-campaign-31887523012",
        "expected_size_bytes": 61886753,
        "expected_sha256": "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f",
        "source_head_sha": None,
        "recovery_state": "METADATA_ONLY_NO_BYTES",
        "dependency_types": ["CONDITIONAL_EXACT_FALLBACK", "HARD_EXACT_REPLAY_SOURCE"],
        "retained_status": "PROTECTED_RESEARCH_RETAIN_FAIL_CLOSED",
        "evidence_authority": "Protected research only; no production, pricing, selection, BET, or backfill authority.",
        "retained_reason": "Fresh-holdout remains prospective protected research and the spent PR139 V2 lineage remains historical evidence; neither can be retired based on artifact API unavailability.",
        "missing_evidence_effect": "Fresh-holdout validates the separate PR119 materialized projection first, then conditionally requires this exact ZIP if that projection is absent or mismatched. PR139 V2 requires the exact archive. Missing both bootstrap sources fails closed before collection.",
        "distinct_successor_evidence": {"asset": "athena-fresh-holdout-bootstrap-v1/pr119-materialized.ndjson", "size_bytes": 10545099, "row_count": 21326, "sha256": "e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2", "is_substitute": False},
        "owner_decision": "Recover only the exact original ZIP from an existing durable source. Preserve the projection and no-backfill contracts; no substitution or retirement.",
        "authorizations": NO_AUTHORITY,
    },
    {
        "artifact_id": 9422055017,
        "run_id": 32410775191,
        "name": "fotmob-prospective-player-context-evidence",
        "expected_size_bytes": 974969,
        "expected_sha256": "db5dc12b8863cbac15f210e018ddf0af9b9011a6ad8c3958a473a597254f44b5",
        "source_head_sha": "46f76e8033d3d498131c6f893111b437b6b459a9",
        "recovery_state": "METADATA_ONLY_NO_BYTES",
        "dependency_types": ["HARD_EXACT_REPLAY_SOURCE", "HARD_EXACT_VERIFICATION_SOURCE"],
        "retained_status": "CLOSED_HISTORICAL_PR_VERIFIER_RETAIN",
        "evidence_authority": "Exact-observation verification only; no source-wide, model, probability, pricing, selection, production, or BET authority.",
        "retained_reason": "PR193, PR194, and PR197 verifier histories are closed and source-bound; their merged code is not a replacement for the exact historical source archive.",
        "missing_evidence_effect": "Exact-source verification/replay is blocked. Derived PR193 real-array output (14,089 bytes; SHA-256 acf53d913ee3d7a6c4f357860aa2730b5122ad8a169f4a38bcc4ab882c6d4ad8) is not the raw source archive.",
        "producer_input_artifact_id": 9421984069,
        "owner_decision": "Preserve all three verifiers and recover the exact PR192 archive for historical replay. No replacement PR substitution or retirement.",
        "authorizations": NO_AUTHORITY,
    },
    {
        "artifact_id": 9437181220,
        "run_id": 32455713912,
        "name": None,
        "expected_size_bytes": None,
        "expected_sha256": "360aac588f049fe6b0437c43e060b317edd12aaf4672db93ebe2fca42de00589",
        "source_head_sha": "b879b2140d0bc3fb64fa8fec4c73c735240a3b41",
        "inner_raw_sha256": "a22e449fd7c59bee011e71230e345c733e1322311f6a9481812a23b4dcae2dc8",
        "manifest_sha256": "64fb631d4889dbf360af4fb988656aba579b67ca5340578df1056dc5324dc09e",
        "recovery_state": "METADATA_ONLY_NO_BYTES",
        "dependency_types": ["HARD_EXACT_REPLAY_SOURCE", "HARD_EXACT_VERIFICATION_SOURCE"],
        "retained_status": "HISTORICAL_GATE_FAILED_ADMISSION_UNPROVEN_RETAIN",
        "evidence_authority": "Saturday exact-source/catalog replay only; no automatic review, reacquisition, market, selection, or BET authority.",
        "retained_reason": "PR200/201/202 history and exact-source admission checks depend on this identity. The PR202 merge-push uploaded a candidate but failed the separate exact-byte approval gate; store/admitted proof was skipped.",
        "missing_evidence_effect": "Candidate bytes and a catalog admission receipt are absent. The later owner SHA comment 5368504537 followed merge-push run 32467715248 and is not admission proof; no rerun was observed.",
        "admission_lineage": {"candidate_pr_run_id": 32466721852, "merge_push_run_id": 32467715248, "owner_comment_id": 5368504537, "owner_sha_comment_after_run": True, "candidate_uploaded": True, "exact_byte_approval_gate_passed": False, "store_step_skipped": True, "admission_proven": False},
        "owner_decision": "Keep admission unclaimed; recover the exact source. Any continuation requires separate owner authorization. No retirement.",
        "authorizations": NO_AUTHORITY,
    },
    {
        "artifact_id": 9266604353,
        "run_id": 31953949073,
        "name": "pr69-primary-time-basis-evidence-campaign-31953949073",
        "expected_size_bytes": None,
        "expected_sha256": "ce87f13cb72a917c0a01e4bbede87e4123d85861d5ee1cd98667bb802d380db7",
        "source_head_sha": None,
        "recovery_state": "METADATA_ONLY_NO_BYTES",
        "dependency_types": ["SUCCESSOR_RECONCILIATION_METADATA_ONLY", "HISTORICAL_LINEAGE_ONLY"],
        "retained_status": "SPENT_HISTORICAL_ONE_SHOT_RETAIN",
        "evidence_authority": "Protected PR69 V1 acquisition evidence only; no semantic, model, pricing, selection, production, or BET authority.",
        "retained_reason": "V1 evidence and its separate V2 acquisition-only result must remain distinct. The exact PR130 V2 command is spent.",
        "missing_evidence_effect": "V2 checks prior result/artifact metadata but does not download this ZIP. V2 run 31974333489 did not establish semantic extraction, effective scope, or time basis.",
        "distinct_v2_acquisition_output": {"artifact_id": 9270750452, "sha256": "186188a0cec4e3febc8971c0f69eb1feb7dec6d2f35052ce48d2913c37265a6c", "is_v1_archive_or_semantic_qualification": False},
        "owner_decision": "Preserve V1/V2 separately and recover V1 bytes for history. No replay or semantic completion.",
        "authorizations": NO_AUTHORITY,
    },
    {
        "artifact_id": 9274313978,
        "run_id": 31987862156,
        "name": "fotmob-utc-native-feature-qualification-31987862156",
        "expected_size_bytes": 2388,
        "expected_sha256": "1a46808c8ee4d21ab67ec03b1fd6c0a80e79fadf04933092e7a106522e31c337",
        "source_head_sha": None,
        "recovery_state": "METADATA_ONLY_NO_BYTES",
        "dependency_types": ["SUCCESSOR_RECONCILIATION_METADATA_ONLY", "HISTORICAL_LINEAGE_ONLY"],
        "retained_status": "SPENT_HISTORICAL_ONE_SHOT_RETAIN",
        "evidence_authority": "V1 permission-failure evidence only; no qualification or model authority.",
        "retained_reason": "The failure record is required to preserve V1/V2 history and must not be rewritten as success.",
        "missing_evidence_effect": "PR139 V2 checks the V1 failure artifact ID/SHA/size as reconciliation-comment text; it does not download this ZIP. V1 failed before runner/source download.",
        "owner_decision": "Preserve failure/success distinction and recover the exact small V1 archive for audit. No replay or retirement.",
        "authorizations": NO_AUTHORITY,
    },
    {
        "artifact_id": 9275052993,
        "run_id": 31990121181,
        "name": "fotmob-utc-native-feature-qualification-v2-31990121181",
        "expected_size_bytes": 23349191,
        "expected_sha256": "f69ffad8f47faadb3ec743c96efa35fb6f4b43776a7650cf0414fb40455d29eb",
        "source_head_sha": "cd67be14f6a4f09484d18a57de360b8a5d4c51d7",
        "recovery_state": "METADATA_ONLY_NO_BYTES",
        "dependency_types": ["HARD_EXACT_OWNER_GATED_RESEARCH_INPUT"],
        "retained_status": "OWNER_GATED_RESEARCH_PENDING_EXACT_BYTES_RETAIN",
        "evidence_authority": "Research feature evidence only; no automatic model approval, production, pricing, selection, or BET authority.",
        "retained_reason": "PR145 remains a separate owner-gated research validator and its exact required input is unavailable.",
        "missing_evidence_effect": "PR145 validates exact artifact metadata and ZIP SHA/size before validator/training. Prior run 32046244761 failed before marker/download/training; no attempt marker was observed. No fallback exists.",
        "owner_decision": "Recover the exact archive before a separately owner-authorized command. No substitution or synthetic observations.",
        "authorizations": NO_AUTHORITY,
    },
    {
        "artifact_id": 9292984849,
        "run_id": 32046244761,
        "name": None,
        "expected_size_bytes": None,
        "expected_sha256": "91965dee1fdb496e776a914de9a9e789a830141ea6b17276a7b1bade541835c1",
        "source_head_sha": None,
        "recovery_state": "METADATA_ONLY_NO_BYTES",
        "dependency_types": ["FORENSIC_RECONCILIATION_METADATA_ONLY", "HISTORICAL_LINEAGE_ONLY"],
        "retained_status": "FORENSIC_PRE_ATTEMPT_HISTORY_RETAIN",
        "evidence_authority": "Forensic pre-attempt HTTP 403 evidence; validator and training did not execute.",
        "retained_reason": "PR145's reconciliation guard refers to this failure identity as text. It is distinct from, and not a payload input to, the validator.",
        "missing_evidence_effect": "Run 32046244761 failed before durable attempt marker, checkout, download, validator, or research training. Missing bytes impede forensic replay only.",
        "owner_decision": "Preserve the pre-attempt failure history; recover the exact archive if available. Do not call it success evidence, hard payload dependency, or retirement proof.",
        "authorizations": NO_AUTHORITY,
    },
    {
        "artifact_id": 9491418446,
        "run_id": 32628985683,
        "name": "athena-history-canonical.zip",
        "expected_size_bytes": 2149256220,
        "expected_sha256": "a783886d0906e357e26851fcb3eb182bb06bdcc184d21f2b6578bb3d1fa61511",
        "source_semantic_name": "athena-history-sqlite",
        "source_head_sha": None,
        "recovery_state": "PARTIAL_DURABLE_COPY_RECOVERED",
        "dependency_types": ["HARD_EXACT_TRANSFER_SOURCE"],
        "retained_status": "ADMINISTRATIVE_TRANSFER_PENDING_COMPLETE_ARCHIVE_RETAIN",
        "evidence_authority": "Warehouse archive transfer; actions:read and contents:write pointer-branch capability only, no provider authority.",
        "retained_reason": "The transfer workflow still has dispatch and path-filtered main-push consumers with fixed exact-archive validation.",
        "missing_evidence_effect": "Handoff reports pieces 000-010 and 022 of 23; pieces 011-021 are missing. Part hashes were not verified in this review. Exact reconstruction also requires concat/size/SHA, ZIP integrity, and athena_history.db membership.",
        "parts_found": ["000", "001", "002", "003", "004", "005", "006", "007", "008", "009", "010", "022"],
        "missing_parts": ["011", "012", "013", "014", "015", "016", "017", "018", "019", "020", "021"],
        "owner_decision": "Provide the complete exact archive or missing parts through an accessible durable path for offline verification. No dispatch or retirement.",
        "authorizations": NO_AUTHORITY,
    },
]


def _spec(*, artifact_id: int, path: str, event: str, qualifier: str,
          logical_id: str, status: str, lifecycle: str, dependency: str,
          reason: str, decision: str, guards: tuple[str, ...] = ()) -> dict:
    return {
        "artifact_id": artifact_id,
        "workflow_path": path,
        "event": event,
        "qualifier": qualifier,
        "logical_trigger_id": logical_id,
        "retained_status": status,
        "trigger_lifecycle": lifecycle,
        "dependency_type": dependency,
        "retained_reason": reason,
        "owner_decision": decision,
        "guard_tokens": list(guards),
    }


RELATION_SPECS = [
    _spec(
        artifact_id=9249856559,
        path=".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml",
        event="schedule", qualifier="cron 7 * * * *", logical_id="fresh-holdout:schedule:7",
        status="PROTECTED_RESEARCH_RETAIN_FAIL_CLOSED", lifecycle="LIVE_PROTECTED_RESEARCH",
        dependency="CONDITIONAL_EXACT_FALLBACK",
        reason="Protected prospective collection uses its exact PR119 projection first and this exact ZIP only as a conditional fallback.",
        decision="Preserve prospective-only/no-backfill guards; recover exact ZIP; no substitution or retirement.",
    ),
    _spec(
        artifact_id=9249856559,
        path=".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml",
        event="schedule", qualifier="cron 37 * * * *", logical_id="fresh-holdout:schedule:37",
        status="PROTECTED_RESEARCH_RETAIN_FAIL_CLOSED", lifecycle="LIVE_PROTECTED_RESEARCH",
        dependency="CONDITIONAL_EXACT_FALLBACK",
        reason="Protected prospective collection uses its exact PR119 projection first and this exact ZIP only as a conditional fallback.",
        decision="Preserve prospective-only/no-backfill guards; recover exact ZIP; no substitution or retirement.",
    ),
    _spec(
        artifact_id=9249856559,
        path=".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml",
        event="workflow_dispatch", qualifier="continuity inputs and exact prospective-only confirmation",
        logical_id="fresh-holdout:workflow_dispatch",
        status="PROTECTED_RESEARCH_RETAIN_FAIL_CLOSED", lifecycle="LIVE_PROTECTED_RESEARCH",
        dependency="CONDITIONAL_EXACT_FALLBACK",
        reason="Continuity dispatch remains prospective-only, bound to watchdog/slot/cron inputs, and uses the same exact bootstrap contract.",
        decision="Do not dispatch; preserve no-backfill guard and recover exact bytes.",
        guards=("continuity_source_watchdog_run_id", "continuity_target_slot",
                "continuity_target_cron", "PROSPECTIVE_ONLY_NO_BACKFILL_V1"),
    ),
    _spec(
        artifact_id=9249856559,
        path=".github/workflows/execute-fotmob-utc-native-successor-feature-qualification-v2.yml",
        event="issue_comment", qualifier="PR139 authorized exact V2 command",
        logical_id="pr139:issue_comment:v2", status="SPENT_HISTORICAL_ONE_SHOT_RETAIN",
        lifecycle="CLOSED_OR_SPENT", dependency="HARD_EXACT_REPLAY_SOURCE",
        reason="Merged PR139 V2 lineage is a spent one-shot research path with an exact original ZIP input.",
        decision="Preserve V1/V2 lineage; no replay; projection or V2 output is not a substitute.",
        guards=("github.event.issue.number == 139",
                "/athena-run-fotmob-utc-native-feature-qualification-v2",
                "const artifactId = 9249856559"),
    ),
    _spec(
        artifact_id=9422055017,
        path=".github/workflows/verify-fotmob-real-player-context-array-admission.yml",
        event="pull_request", qualifier="PR193 exact same-repository branch and frozen-base guard",
        logical_id="pr193:pull_request", status="CLOSED_HISTORICAL_PR_VERIFIER_RETAIN",
        lifecycle="CLOSED_HISTORICAL_PR", dependency="HARD_EXACT_VERIFICATION_SOURCE",
        reason="Merged PR193 verifier is bound to its exact branch/base and frozen source artifact.",
        decision="Preserve; recover exact archive only for historical replay.",
        guards=("evidence/fotmob-real-player-context-array-admission",
                "sourceArtifactId = 9422055017", "run.event !== 'pull_request'"),
    ),
    _spec(
        artifact_id=9422055017,
        path=".github/workflows/verify-fotmob-real-player-context-team-strength-handoff.yml",
        event="pull_request", qualifier="PR194 exact same-repository branch and frozen-base guard",
        logical_id="pr194:pull_request", status="CLOSED_HISTORICAL_PR_VERIFIER_RETAIN",
        lifecycle="CLOSED_HISTORICAL_PR", dependency="HARD_EXACT_VERIFICATION_SOURCE",
        reason="Merged PR194 verifier is bound to its exact branch/base and frozen source artifact.",
        decision="Preserve; recover exact archive only for historical replay.",
        guards=("model/fotmob-real-player-context-team-strength-handoff",
                "sourceArtifactId = 9422055017", "run.event !== 'pull_request'"),
    ),
    _spec(
        artifact_id=9422055017,
        path=".github/workflows/verify-fotmob-real-player-context-authoritative-bridge.yml",
        event="pull_request", qualifier="PR197 exact same-repository branch and frozen-base guard",
        logical_id="pr197:pull_request", status="CLOSED_HISTORICAL_PR_VERIFIER_RETAIN",
        lifecycle="CLOSED_HISTORICAL_PR", dependency="HARD_EXACT_VERIFICATION_SOURCE",
        reason="Merged PR197 verifier is bound to its exact branch/base and frozen source artifact.",
        decision="Preserve; recover exact archive only for historical replay.",
        guards=("model/fotmob-real-player-context-authoritative-bridge",
                "sourceArtifactId = 9422055017", "run.event !== 'pull_request'"),
    ),
    _spec(
        artifact_id=9437181220,
        path=".github/workflows/verify-saturday-competition-review-priority.yml",
        event="pull_request", qualifier="PR200 exact PR/ref guard", logical_id="pr200:pull_request",
        status="CLOSED_HISTORICAL_PR_VERIFIER_RETAIN", lifecycle="CLOSED_HISTORICAL_PR",
        dependency="HARD_EXACT_VERIFICATION_SOURCE",
        reason="Merged PR200 priority verifier pins the frozen exact Saturday source.",
        decision="Preserve; do not infer admission or authorize reacquisition.",
        guards=("github.event.pull_request.number == 200",
                "policy/competition-fixture-review-priority", "9437181220"),
    ),
    _spec(
        artifact_id=9437181220,
        path=".github/workflows/verify-saturday-2026-08-22-fixture-identity-review.yml",
        event="pull_request", qualifier="PR201 exact PR/ref guard", logical_id="pr201:pull_request",
        status="CLOSED_HISTORICAL_PR_VERIFIER_RETAIN", lifecycle="CLOSED_HISTORICAL_PR",
        dependency="HARD_EXACT_VERIFICATION_SOURCE",
        reason="Merged PR201 identity verifier pins the frozen exact Saturday source.",
        decision="Preserve; do not infer admission or authorize reacquisition.",
        guards=("github.event.pull_request.number == 201",
                "evidence/saturday-2026-08-22-fixture-identity-review", "9437181220"),
    ),
    _spec(
        artifact_id=9437181220,
        path=".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml",
        event="pull_request", qualifier="PR202 exact PR/ref candidate verifier",
        logical_id="pr202:pull_request", status="CLOSED_HISTORICAL_PR_VERIFIER_RETAIN",
        lifecycle="CLOSED_HISTORICAL_PR", dependency="HARD_EXACT_VERIFICATION_SOURCE",
        reason="Merged PR202 candidate verifier remains exact-source-bound; its PR event did not establish merged-main catalog admission.",
        decision="Keep admission unclaimed; no valid admission receipt or replacement source.",
        guards=("github.event.pull_request.number == 202",
                "evidence/saturday-2026-08-22-reviewed-fixture-catalog", "9437181220"),
    ),
    _spec(
        artifact_id=9437181220,
        path=".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml",
        event="push", qualifier="main merge-push exact PR202 admission path",
        logical_id="pr202:push:main-merge",
        status="HISTORICAL_GATE_FAILED_ADMISSION_UNPROVEN_RETAIN",
        lifecycle="HISTORICAL_GATE_FAILED", dependency="HARD_EXACT_VERIFICATION_SOURCE",
        reason="Historical merge-push prepared/uploaded a candidate but failed its exact-byte approval gate; the store/admission step was skipped.",
        decision="Do not treat candidate upload or later SHA comment as admission; no rerun or retirement.",
        guards=("github.event_name == 'push'", "github.ref == 'refs/heads/main'",
                "pull_number: 202", "artifact_id: 9437181220"),
    ),
    _spec(
        artifact_id=9266604353,
        path=".github/workflows/execute-pr69-primary-time-basis-evidence-campaign-v2.yml",
        event="issue_comment", qualifier="PR130 owner-gated one-shot V2 command",
        logical_id="pr130:issue_comment:v2", status="SPENT_HISTORICAL_ONE_SHOT_RETAIN",
        lifecycle="CLOSED_OR_SPENT", dependency="SUCCESSOR_RECONCILIATION_METADATA_ONLY",
        reason="Spent V2 owner command verifies V1 result/artifact metadata but does not download this ZIP; V2 acquisition did not establish semantics.",
        decision="Preserve V1/V2; recover V1 bytes; no replay or semantic completion.",
        guards=("github.event.issue.number == 130", "/athena-run-pr69-time-basis-evidence-v2",
                "priorArtifactId = 9266604353"),
    ),
    _spec(
        artifact_id=9274313978,
        path=".github/workflows/execute-fotmob-utc-native-successor-feature-qualification-v2.yml",
        event="issue_comment", qualifier="PR139 V2 failure-lineage reconciliation guard",
        logical_id="pr139:issue_comment:v2", status="SPENT_HISTORICAL_ONE_SHOT_RETAIN",
        lifecycle="CLOSED_OR_SPENT", dependency="SUCCESSOR_RECONCILIATION_METADATA_ONLY",
        reason="V2 checks the V1 permission-failure artifact identity as comment text; it does not fetch the V1 ZIP.",
        decision="Preserve failure/success distinction; recover exact V1 archive for audit; no replay.",
        guards=("github.event.issue.number == 139",
                "/athena-run-fotmob-utc-native-feature-qualification-v2",
                "failure-evidence-artifact-id: 9274313978"),
    ),
    _spec(
        artifact_id=9275052993,
        path=".github/workflows/execute-fotmob-utc-native-expected-goals-model-validation.yml",
        event="issue_comment", qualifier="PR145 owner-gated exact validation command",
        logical_id="pr145:issue_comment:validation",
        status="OWNER_GATED_RESEARCH_PENDING_EXACT_BYTES_RETAIN", lifecycle="LIVE_OWNER_GATED",
        dependency="HARD_EXACT_OWNER_GATED_RESEARCH_INPUT",
        reason="PR145 can reach the exact V2 research input only through owner-gated command and marker/reconciliation guards.",
        decision="Do not command; recover exact ZIP before any separately owner-authorized execution.",
        guards=("github.event.issue.number == 145",
                "/athena-run-fotmob-utc-native-expected-goals-validation",
                "const artifactId = 9275052993"),
    ),
    _spec(
        artifact_id=9292984849,
        path=".github/workflows/execute-fotmob-utc-native-expected-goals-model-validation.yml",
        event="issue_comment", qualifier="Same PR145 command; forensic reconciliation metadata check",
        logical_id="pr145:issue_comment:validation", status="FORENSIC_PRE_ATTEMPT_HISTORY_RETAIN",
        lifecycle="LIVE_OWNER_GATED_FORENSIC_GUARD",
        dependency="FORENSIC_RECONCILIATION_METADATA_ONLY",
        reason="PR145 checks this pre-attempt HTTP 403 identity in reconciliation text only; it is not a validator input.",
        decision="Preserve forensic failure; recover exact archive if available; not success evidence or retirement proof.",
        guards=("github.event.issue.number == 145", "failure-artifact-id: 9292984849",
                "validator-executed: false", "research-training-executed: false"),
    ),
    _spec(
        artifact_id=9491418446,
        path=".github/workflows/prepare-canonical-drive-transfer.yml",
        event="workflow_dispatch", qualifier="canonical transfer with pinned run/artifact defaults",
        logical_id="canonical-transfer:workflow_dispatch",
        status="ADMINISTRATIVE_TRANSFER_PENDING_COMPLETE_ARCHIVE_RETAIN",
        lifecycle="LIVE_ADMINISTRATIVE_TRANSFER", dependency="HARD_EXACT_TRANSFER_SOURCE",
        reason="Manual transfer requires the exact 2,149,256,220-byte archive and pinned SHA; overrides cannot change content identity.",
        decision="Do not dispatch; recover full exact archive or missing parts and verify offline.",
        guards=("workflow_dispatch", "default: \"9491418446\"",
                "EXPECTED_ARCHIVE_BYTES", "EXPECTED_ARCHIVE_SHA256"),
    ),
    _spec(
        artifact_id=9491418446,
        path=".github/workflows/prepare-canonical-drive-transfer.yml",
        event="push", qualifier="main workflow-file path filter",
        logical_id="canonical-transfer:push:main-workflow",
        status="ADMINISTRATIVE_TRANSFER_PENDING_COMPLETE_ARCHIVE_RETAIN",
        lifecycle="LIVE_ADMINISTRATIVE_TRANSFER", dependency="HARD_EXACT_TRANSFER_SOURCE",
        reason="Path-filtered main-push transfer requires the same exact archive and publishes a started pointer before download.",
        decision="Preserve transfer contract; do not trigger while bytes are incomplete or unverified.",
        guards=("push:", "branches: [main]",
                ".github/workflows/prepare-canonical-drive-transfer.yml", "9491418446"),
    ),
]


class RetainedWorkflowStatusError(AssertionError):
    """Raised when source, hashes, counts, or explicit retained status drift."""


def require(value: bool, message: str) -> None:
    if not value:
        raise RetainedWorkflowStatusError(message)


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def self_sha(value: dict) -> str:
    return sha256(canonical_bytes({key: item for key, item in value.items()
                                   if key != "canonical_sha256"}))


def seal(value: dict) -> dict:
    value["canonical_sha256"] = self_sha(value)
    return value


def _git(*args: str, check: bool = True) -> bytes:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    if check and result.returncode:
        raise RetainedWorkflowStatusError(
            f"git {' '.join(args)} failed: {result.stderr.decode('utf-8', 'replace')}"
        )
    return result.stdout


def _strict_json(raw: bytes, label: str) -> dict:
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RetainedWorkflowStatusError(f"duplicate JSON key in {label}: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RetainedWorkflowStatusError(f"invalid JSON in {label}: {exc}") from exc
    require(type(value) is dict, f"{label} must be a JSON object")
    return value


def _read_repo_json(path: str) -> dict:
    return _strict_json((ROOT / path).read_bytes(), path)


def _tree_entries(treeish: str) -> dict[str, str]:
    raw = _git("ls-tree", "-r", "-z", treeish, "--", ".github/workflows")
    entries = {}
    for row in raw.split(b"\0"):
        if not row:
            continue
        metadata, path = row.split(b"\t", 1)
        fields = metadata.decode("ascii").split()
        kind, oid = fields[1], fields[2]
        path_text = path.decode("utf-8")
        if kind == "blob" and path_text.endswith((".yml", ".yaml")):
            entries[path_text] = oid
    return entries


def _read_tree_blob(treeish: str, path: str) -> bytes:
    return _git("show", f"{treeish}:{path}")


def _worktree_blob(path: str) -> str:
    return subprocess.run(
        ["git", "hash-object", f"--path={path}", "--stdin"],
        cwd=ROOT, input=(ROOT / path).read_bytes(), capture_output=True,
        check=True,
    ).stdout.decode().strip()


def _workflow_inventory() -> tuple[list[dict], str]:
    base_entries = _tree_entries(BASE_MAIN_SHA)
    head_entries = _tree_entries("HEAD")
    require(len(base_entries) == 39, "pinned base workflow count is not 39")
    require(head_entries == base_entries, "current workflow path/blob inventory differs from exact base")
    current_worktree_paths = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / ".github" / "workflows").iterdir()
        if path.suffix in {".yml", ".yaml"}
    )
    require(current_worktree_paths == sorted(base_entries), "working-tree workflow inventory differs from base")
    rows = []
    for path in sorted(base_entries):
        expected = _read_tree_blob(BASE_MAIN_SHA, path)
        filtered_blob = _worktree_blob(path)
        require(filtered_blob == base_entries[path],
                f"working-tree workflow source differs from base after Git filters: {path}")
        rows.append({
            "path": path,
            "git_blob_sha1": base_entries[path],
            "source_sha256": sha256(expected),
        })
    base_tree = _git("rev-parse", f"{BASE_MAIN_SHA}:.github/workflows").decode().strip()
    head_tree = _git("rev-parse", "HEAD:.github/workflows").decode().strip()
    require(base_tree == head_tree == WORKFLOW_TREE_SHA1,
            "current .github/workflows tree differs from reviewed #431 workflow tree")
    return rows, sha256(canonical_bytes(rows))


def _source_matches(treeish: str) -> list[dict]:
    matches = []
    patterns = [part for artifact_id in ARTIFACT_IDS for part in ("-e", artifact_id)]
    result = subprocess.run(
        ["git", "grep", "-n", "-F", *patterns, treeish, "--"],
        cwd=ROOT, capture_output=True,
    )
    if result.returncode not in (0, 1):
        raise RetainedWorkflowStatusError(
            f"git grep failed for tracked artifact references: {result.stderr.decode('utf-8', 'replace')}"
        )
    for output_line in result.stdout.splitlines():
        revision, separator, remainder = output_line.partition(b":")
        require(bool(separator) and revision.decode() == treeish,
                "unexpected git grep revision prefix")
        path_raw, separator, tail = remainder.partition(b":")
        line_number, separator2, text = tail.partition(b":")
        require(bool(separator and separator2), "malformed git grep record")
        path = path_raw.decode("utf-8")
        try:
            number = int(line_number)
        except ValueError as exc:
            raise RetainedWorkflowStatusError("git grep returned invalid line number") from exc
        line_text = text.decode("utf-8", "replace").rstrip("\r")
        line_bytes = text.rstrip(b"\r")
        for artifact_id in ARTIFACT_IDS:
            if artifact_id.encode("ascii") in line_bytes:
                matches.append({
                    "artifact_id": int(artifact_id),
                    "path": path,
                    "line": number,
                    "line_sha256": sha256(line_text.encode("utf-8")),
                })
    return sorted(matches, key=lambda row: (row["artifact_id"], row["path"], row["line"]))


def _reference_inventory(workflow_rows: list[dict]) -> dict:
    # Use exact reviewed main for a non-self-referential inventory. Added receipt,
    # audit, test, and doc references in this PR cannot inflate the base counts.
    matches = _source_matches(BASE_MAIN_SHA)
    current_matches = _source_matches("HEAD")
    workflow_matches = [row for row in matches if row["path"].startswith(".github/workflows/")]
    current_workflow_matches = [row for row in current_matches if row["path"].startswith(".github/workflows/")]
    require(current_workflow_matches == workflow_matches,
            "current workflow artifact reference inventory differs from exact base")
    counts_by_id = {}
    workflow_counts_by_id = {}
    for artifact_id in ARTIFACT_IDS:
        counts_by_id[artifact_id] = sum(row["artifact_id"] == int(artifact_id) for row in matches)
        workflow_counts_by_id[artifact_id] = sum(row["artifact_id"] == int(artifact_id) for row in workflow_matches)
    require(counts_by_id == {key: value["all"] for key, value in EXPECTED_REFERENCE_LINE_COUNTS.items()} and
            workflow_counts_by_id == {key: value["workflow"] for key, value in EXPECTED_REFERENCE_LINE_COUNTS.items()},
            "per-artifact matching-line inventory differs from reviewed source counts")

    require(len(matches) == 108, f"base exact-ID matching line count drift: {len(matches)}")
    require(len(workflow_matches) == 27, f"base workflow matching line count drift: {len(workflow_matches)}")
    require(len(matches) - len(workflow_matches) == 81,
            "supporting non-workflow matching line count drift")
    paths = sorted({row["path"] for row in workflow_matches})
    edge_keys = sorted({(row["artifact_id"], row["path"]) for row in workflow_matches})
    require(len(paths) == 11, f"unique workflow path count drift: {len(paths)}")
    require(len(edge_keys) == 13, f"artifact/workflow edge count drift: {len(edge_keys)}")

    by_path = {row["path"]: row for row in workflow_rows}
    edge_rows = []
    for artifact_id, path in edge_keys:
        source_row = by_path[path]
        line_rows = [row for row in workflow_matches
                     if row["artifact_id"] == artifact_id and row["path"] == path]
        edge_rows.append({
            "artifact_id": artifact_id,
            "workflow_path": path,
            "git_blob_sha1": source_row["git_blob_sha1"],
            "source_sha256": source_row["source_sha256"],
            "matching_lines": [row["line"] for row in line_rows],
            "line_text_sha256": [row["line_sha256"] for row in line_rows],
        })
    return {
        "scan_tree_sha": BASE_MAIN_SHA,
        "scan_basis": "EXACT_BASE_TRACKED_SOURCE; current workflow tree and workflow references independently byte-equal the base",
        "matching_lines_by_artifact": counts_by_id,
        "workflow_matching_lines_by_artifact": workflow_counts_by_id,
        "all_repository_matching_line_count": len(matches),
        "workflow_matching_line_count": len(workflow_matches),
        "supporting_nonworkflow_matching_line_count": len(matches) - len(workflow_matches),
        "unique_workflow_path_count": len(paths),
        "artifact_workflow_edge_count": len(edge_keys),
        "reference_inventory_sha256": sha256(canonical_bytes(matches)),
        "workflow_reference_inventory_sha256": sha256(canonical_bytes(workflow_matches)),
        "workflow_reference_edges": edge_rows,
    }


def _load_predecessors() -> dict:
    matrix = _read_repo_json(MATRIX_V2_PATH)
    checkpoint = _read_repo_json(CHECKPOINT_V2_PATH)
    schedule = _read_repo_json(SCHEDULE_RECEIPT_PATH)
    ledger = _read_repo_json(EVOLUTION_PATH)
    for value, expected, label in (
        (matrix, PREDECESSOR_V2_MATRIX_SHA256, "V2 capability matrix"),
        (checkpoint, PREDECESSOR_V2_RECEIPT_SHA256, "V2 checkpoint receipt"),
        (schedule, SCHEDULE_OWNERSHIP_RECEIPT_SHA256, "schedule ownership receipt"),
        (ledger, EVOLUTION_LEDGER_SHA256, "workflow evolution ledger"),
    ):
        require(value.get("canonical_sha256") == expected == self_sha(value),
                f"{label} canonical identity drift")
    require(matrix.get("predecessor_matrix_sha256") == PREDECESSOR_V1_MATRIX_SHA256 and
            matrix.get("predecessor_receipt_sha256") == PREDECESSOR_V1_RECEIPT_SHA256,
            "V2 predecessor identities drift")
    require(checkpoint.get("workflow_matrix_sha256") == PREDECESSOR_V2_MATRIX_SHA256,
            "V2 checkpoint receipt/matrix binding drift")
    require(checkpoint.get("schedule_ownership_receipt_sha256") == SCHEDULE_OWNERSHIP_RECEIPT_SHA256,
            "V2 checkpoint receipt/schedule ownership binding drift")
    require(matrix.get("current_workflow_tree_sha1") == WORKFLOW_TREE_SHA1 and
            checkpoint.get("current_workflow_tree_sha1") == WORKFLOW_TREE_SHA1,
            "V2 workflow tree identity drift")
    require(matrix.get("workflow_count") == 39 and matrix.get("trigger_surface_count") == 57,
            "V2 39/57 census drift")
    require(len(ledger.get("transitions", [])) == 13 and
            ledger.get("current_workflow_tree_sha1") == WORKFLOW_TREE_SHA1,
            "workflow evolution ledger transition/tree drift")
    require(checkpoint.get("checkpoint_e_status") == "INCOMPLETE" and
            checkpoint.get("p4_4_status") == "INCOMPLETE",
            "historical Checkpoint E/P4.4 state drift")
    require(_worktree_blob(EVOLUTION_PATH) == _git("rev-parse", f"HEAD:{EVOLUTION_PATH}").decode().strip(),
            "workflow evolution ledger worktree source differs from HEAD")
    require(_worktree_blob(EVOLUTION_PATH) == _git("rev-parse", f"{BASE_MAIN_SHA}:{EVOLUTION_PATH}").decode().strip(),
            "workflow evolution ledger changed from exact base")
    return {"matrix": matrix, "checkpoint": checkpoint, "schedule": schedule, "ledger": ledger}


def _validate_relation_source(spec: dict, workflow_text: str) -> None:
    require(str(spec["artifact_id"]) in workflow_text,
            f"artifact ID missing from declared consumer: {spec['artifact_id']} {spec['workflow_path']}")
    document = yaml.load(workflow_text, Loader=yaml.BaseLoader)
    require(type(document) is dict and type(document.get("on")) is dict,
            f"workflow trigger document invalid: {spec['workflow_path']}")
    trigger = document["on"].get(spec["event"])
    require(trigger is not None, f"declared event missing: {spec['workflow_path']}#{spec['event']}")
    if spec["event"] == "schedule":
        cron = spec["qualifier"].removeprefix("cron ")
        crons = [item.get("cron") for item in trigger]
        require(cron in crons, f"schedule cron missing: {cron}")
    else:
        for token in spec["guard_tokens"]:
            require(token in workflow_text,
                    f"trigger guard drift in {spec['workflow_path']}: {token}")
    if spec["event"] == "push" and spec["artifact_id"] == 9491418446:
        require(trigger.get("branches") == ["main"] and
                trigger.get("paths") == [".github/workflows/prepare-canonical-drive-transfer.yml"],
                "canonical transfer push branch/path filter drift")
    if spec["event"] == "pull_request" and spec["artifact_id"] in {9437181220}:
        require(trigger.get("branches") == ["main"], "Saturday PR trigger branch drift")
    if spec["event"] == "pull_request" and spec["artifact_id"] == 9422055017:
        require(trigger.get("types") == ["opened", "synchronize", "reopened", "edited"],
                "player-context verifier pull_request type drift")


def _build_relations(workflow_rows: list[dict], reference_inventory: dict) -> list[dict]:
    by_path = {row["path"]: row for row in workflow_rows}
    source_text = {path: (ROOT / path).read_text(encoding="utf-8") for path in by_path}
    edge_lines = {
        (edge["artifact_id"], edge["workflow_path"]): edge["matching_lines"]
        for edge in reference_inventory["workflow_reference_edges"]
    }
    rows = []
    for spec in RELATION_SPECS:
        _validate_relation_source(spec, source_text[spec["workflow_path"]])
        key = (spec["artifact_id"], spec["workflow_path"])
        require(key in edge_lines, f"trigger relation has no exact source reference: {key}")
        row = {key: value for key, value in spec.items() if key != "guard_tokens"}
        row["artifact_reference_lines"] = edge_lines[key]
        row["workflow_source_sha256"] = by_path[spec["workflow_path"]]["source_sha256"]
        row["classification_basis"] = "STATIC_SOURCE_AND_REVIEWED_DISPOSITION; VOLATILE_ACTIONS_STATE_EXCLUDED"
        row["replay_authority_inferred"] = False
        row["authorizations"] = dict(NO_AUTHORITY)
        rows.append(row)
    ids = [row["logical_trigger_id"] + "|" + str(row["artifact_id"]) + "|" + row["workflow_path"] + "|" + row["event"] + "|" + row["qualifier"] for row in rows]
    require(len(ids) == len(set(ids)) == 17, "retained trigger relationship identity duplicate/count drift")
    logical = {row["logical_trigger_id"] for row in rows}
    live_logical = {row["logical_trigger_id"] for row in rows if row["trigger_lifecycle"].startswith("LIVE_")}
    historical_logical = {row["logical_trigger_id"] for row in rows if not row["trigger_lifecycle"].startswith("LIVE_")}
    live_rows = [row for row in rows if row["trigger_lifecycle"].startswith("LIVE_")]
    historical_rows = [row for row in rows if not row["trigger_lifecycle"].startswith("LIVE_")]
    require((len(logical), len(live_logical), len(historical_logical), len(live_rows), len(historical_rows)) == (15, 6, 9, 7, 10),
            "retained trigger live/history counts drift")
    return rows


def build_receipt() -> dict:
    require(_git("rev-parse", BASE_MAIN_SHA).decode().strip() == BASE_MAIN_SHA,
            "exact base main commit unavailable")
    require(_git("show", "-s", "--format=%T", BASE_MAIN_SHA).decode().strip() == BASE_TREE_SHA,
            "exact base main tree identity drift")
    workflows, workflow_inventory_sha = _workflow_inventory()
    references = _reference_inventory(workflows)
    _load_predecessors()
    relations = _build_relations(workflows, references)
    artifacts = json.loads(json.dumps(ARTIFACTS))
    require(len(artifacts) == 8 and len({row["artifact_id"] for row in artifacts}) == 8,
            "artifact disposition count/identity drift")
    require(sum(row["recovery_state"] == "PARTIAL_DURABLE_COPY_RECOVERED" for row in artifacts) == 1 and
            sum(row["recovery_state"] == "METADATA_ONLY_NO_BYTES" for row in artifacts) == 7,
            "artifact recovery state counts drift")
    require(artifacts[-1]["missing_parts"] == [f"{number:03d}" for number in range(11, 22)],
            "canonical transfer missing-piece inventory drift")

    receipt = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository": "Thabearr/ATHENA",
        "master_issue": 337,
        "exact_base_main_sha": BASE_MAIN_SHA,
        "exact_base_tree_sha": BASE_TREE_SHA,
        "source_review_counter_before_merge": "2/5",
        "source_review_counter_if_owner_merges": "3/5",
        "mandatory_source_reread_due": False,
        "predecessor_v1_matrix_sha256": PREDECESSOR_V1_MATRIX_SHA256,
        "predecessor_v1_receipt_sha256": PREDECESSOR_V1_RECEIPT_SHA256,
        "predecessor_v2_matrix_path": MATRIX_V2_PATH,
        "predecessor_v2_matrix_sha256": PREDECESSOR_V2_MATRIX_SHA256,
        "predecessor_v2_receipt_path": CHECKPOINT_V2_PATH,
        "predecessor_v2_receipt_sha256": PREDECESSOR_V2_RECEIPT_SHA256,
        "schedule_ownership_receipt_path": SCHEDULE_RECEIPT_PATH,
        "schedule_ownership_receipt_sha256": SCHEDULE_OWNERSHIP_RECEIPT_SHA256,
        "workflow_tree_sha1": WORKFLOW_TREE_SHA1,
        "workflow_tree_sha1_before": WORKFLOW_TREE_SHA1,
        "workflow_tree_sha1_after": WORKFLOW_TREE_SHA1,
        "evolution_ledger_path": EVOLUTION_PATH,
        "evolution_ledger_sha256": EVOLUTION_LEDGER_SHA256,
        "evolution_transition_count": 13,
        "workflow_count": 39,
        "trigger_surface_count": 57,
        "external_review_report_sha256": EXTERNAL_REPORTS,
        "missing_artifact_count": 8,
        "exact_archive_recovered_count": 0,
        "partial_durable_copy_count": 1,
        "artifact_workflow_edge_count": references["artifact_workflow_edge_count"],
        "reviewed_artifact_trigger_relationship_count": len(relations),
        "live_artifact_trigger_relationship_count": sum(row["trigger_lifecycle"].startswith("LIVE_") for row in relations),
        "historical_or_spent_artifact_trigger_relationship_count": sum(not row["trigger_lifecycle"].startswith("LIVE_") for row in relations),
        "unique_logical_trigger_path_count": len({row["logical_trigger_id"] for row in relations}),
        "live_logical_trigger_path_count": len({row["logical_trigger_id"] for row in relations if row["trigger_lifecycle"].startswith("LIVE_")}),
        "closed_or_spent_logical_trigger_path_count": len({row["logical_trigger_id"] for row in relations if not row["trigger_lifecycle"].startswith("LIVE_")}),
        "source_reference_inventory": references,
        "workflow_source_inventory_sha256": workflow_inventory_sha,
        "workflow_source_inventory": workflows,
        "retained_status_vocabulary": sorted({row["retained_status"] for row in relations}),
        "retained_status_rows": relations,
        "artifact_dispositions": artifacts,
        "blocker_family": "RETAINED_ACTIVE_EVIDENCE_DEPENDENCIES_AND_OWNER_DISPOSITIONS_UNRESOLVED",
        "exact_remaining_blocker_ids": BLOCKERS,
        "retirement_authorized": False,
        "workflow_source_changed": False,
        "workflow_deletion_count": 0,
        "trigger_change_count": 0,
        "caller_migration_count": 0,
        "consumer_contract_change_authorized": False,
        "consumer_contract_change_gate": "SEPARATE_OWNER_APPROVED_RETENTION_OR_DEPRECATION_DISPOSITION_REQUIRED_IF_EXACT_BYTES_CANNOT_BE_PRODUCED",
        "authorizations": dict(NO_AUTHORITY),
        "provider_action_count": 0,
        "workflow_dispatch_action_count": 0,
        "workflow_rerun_or_cancel_action_count": 0,
        "evidence_regeneration_count": 0,
        "share_code_action_count": 0,
        "email_action_count": 0,
        "login_cookie_wallet_stake_wager_action_count": 0,
        "protected_semantic_delta": dict.fromkeys((
            "model", "probability", "calibration", "xg", "elo", "price_all",
            "router", "portfolio", "provider", "selection", "betting",
        ), 0),
        "evidence_substitution_count": 0,
        "synthetic_backfill_count": 0,
        "volatile_runtime_observations_included": False,
        "volatile_run_state_used_for_static_classification": False,
        "p4_4_status": "INCOMPLETE",
        "checkpoint_e_status": "INCOMPLETE",
        "terminal": "CORE_01D_RETAINED_WORKFLOW_STATUS_REVIEW_READY_INCOMPLETE_DO_NOT_MERGE",
    }
    return seal(receipt)


def validate_receipt(value: dict, expected: dict | None = None) -> None:
    require(value.get("canonical_sha256") == self_sha(value), "retained-status receipt self-hash mismatch")
    expected = build_receipt() if expected is None else expected
    differing = sorted(key for key in set(value) | set(expected) if value.get(key) != expected.get(key))
    if differing:
        detail = ""
        if "retained_status_rows" in differing:
            for index, (actual, wanted) in enumerate(zip(value.get("retained_status_rows", []), expected.get("retained_status_rows", []))):
                if actual != wanted:
                    keys = sorted(key for key in set(actual) | set(wanted) if actual.get(key) != wanted.get(key))
                    detail = f" at relation {index}: {keys}; actual={actual!r}; expected={wanted!r}"
                    break
        raise RetainedWorkflowStatusError(
            "retained-status receipt differs from independently derived source: " + ", ".join(differing) + detail
        )
    require(value["checkpoint_e_status"] == value["p4_4_status"] == "INCOMPLETE",
            "retained status cannot imply Checkpoint E or P4.4 completion")
    require(all(row["authorizations"] == NO_AUTHORITY for row in value["retained_status_rows"]),
            "a retained trigger row grants forbidden authority")
    require(all(row["authorizations"] == NO_AUTHORITY for row in value["artifact_dispositions"]),
            "an artifact disposition grants forbidden authority")
    require(value["evolution_transition_count"] == 13 and value["workflow_source_changed"] is False,
            "workflow tree/evolution transition invariant drift")
    require(value["authorizations"] == NO_AUTHORITY and value["consumer_contract_change_authorized"] is False,
            "top-level receipt grants forbidden authority")


def audit() -> dict:
    expected = build_receipt()
    committed = _read_repo_json(RECEIPT_PATH)
    require((ROOT / RECEIPT_PATH).read_bytes() == canonical_bytes(committed),
            "retained-status receipt is not canonical JSON")
    validate_receipt(committed, expected)
    return {
        "result": "PASS",
        "terminal": committed["terminal"],
        "exact_head": _git("rev-parse", "HEAD").decode().strip(),
        "receipt_sha256": committed["canonical_sha256"],
        "workflow_tree_sha1": committed["workflow_tree_sha1"],
        "evolution_ledger_sha256": committed["evolution_ledger_sha256"],
        "evolution_transition_count": committed["evolution_transition_count"],
        "workflow_count": committed["workflow_count"],
        "trigger_surface_count": committed["trigger_surface_count"],
        "artifact_count": committed["missing_artifact_count"],
        "workflow_path_count": committed["source_reference_inventory"]["unique_workflow_path_count"],
        "artifact_workflow_edge_count": committed["artifact_workflow_edge_count"],
        "artifact_trigger_relationship_count": committed["reviewed_artifact_trigger_relationship_count"],
        "live_relation_count": committed["live_artifact_trigger_relationship_count"],
        "historical_relation_count": committed["historical_or_spent_artifact_trigger_relationship_count"],
        "p4_4": committed["p4_4_status"],
        "checkpoint_e": committed["checkpoint_e_status"],
        "blockers": [row["id"] for row in committed["exact_remaining_blocker_ids"]],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write the source-derived receipt")
    args = parser.parse_args(argv)
    try:
        expected = build_receipt()
        if args.write:
            (ROOT / RECEIPT_PATH).write_bytes(canonical_bytes(expected))
            result = {"result": "WROTE", "receipt_sha256": expected["canonical_sha256"],
                      "terminal": expected["terminal"]}
        else:
            committed = _read_repo_json(RECEIPT_PATH)
            require((ROOT / RECEIPT_PATH).read_bytes() == canonical_bytes(committed),
                    "retained-status receipt is not canonical JSON")
            validate_receipt(committed, expected)
            result = audit()
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, RetainedWorkflowStatusError, TypeError, ValueError, yaml.YAMLError) as exc:
        terminal = "CORE_01D_RETAINED_WORKFLOW_STATUS_REVIEW_BLOCKED_SOURCE_DRIFT_DO_NOT_MERGE"
        print(json.dumps({"result": "BLOCKED", "terminal": terminal, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
