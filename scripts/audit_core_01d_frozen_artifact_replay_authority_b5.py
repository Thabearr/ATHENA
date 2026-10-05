"""Authenticate the bounded B5 frozen-artifact replay authority review.

The audit uses committed source and read-only GitHub metadata captured in the
fixture.  It never downloads an Actions artifact, calls a provider, or runs a
historical workflow.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import yaml

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary

ROOT = Path(__file__).resolve().parents[1]
BASE_MAIN = "19a823d074798a9a897a61b881fed7579774cbba"
BASE_TREE = "4bf93aedfe39db987f57de3e75c97e7c84cec84b"
WORKFLOW_TREE = "9b08653f1a12bb1b3d964fbd910396ff955740da"
EVOLUTION_SHA = "73e1eb3fe6593558c821600dd0f103353d45c15a139ab470a996c7cbb35da531"
RETIREMENT_SHA = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
COMPLETION_V7_PATH = "tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v7.json"
COMPLETION_V7_SHA = "a047bcf6b5fadd2118f6c817b03a43312e0a9094a1269f4b6b22750c5e638512"
B4_PATH = "tests/fixtures/core_01d/core-01d-sportybet-current-trigger-authority-b4-v1.json"
B4_SHA = "9b630ef065318eb83333ce86ab7b121a790d44c8ce6ad5c0f4f5bac527905e3c"
A2_V6_PATH = "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v6.json"
A2_V6_SHA = "f0c9b4fa85ea352d58cb71bced56d985636433c00d461ab8586ecd59f13ccf94"
A2_V5_SHA = "8fbca3af87ecc7ac99da96252c3570e4ddef0d2e4071b180b2bc0299a10eeecd"
A2_V7_PATH = "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v7.json"
POST_443_TESTS = {
    "run_id": 37176160320, "workflow": "Tests", "event": "push", "branch": "main",
    "head_sha": BASE_MAIN, "status": "completed", "conclusion": "success",
    "syntax": "success", "shards_1_to_8": "success", "aggregate": "success",
}
SOURCE_INVENTORY_PATH = "tests/fixtures/core_01d/frozen-artifact-replay-authority-b5-source-inventory-v1.json"
RECEIPT_PATH = "tests/fixtures/core_01d/core-01d-frozen-artifact-replay-authority-b5-v1.json"
POLICY_ID = "ATHENA_CORE_01D_FROZEN_ARTIFACT_REPLAY_AUTHORITY_B5_V1"
INVENTORY_POLICY_ID = "ATHENA_CORE_01D_FROZEN_ARTIFACT_REPLAY_AUTHORITY_B5_SOURCE_INVENTORY_V1"
OBSERVED_AT = "2026-10-04T04:28:31Z"

TARGETS = (
    (".github/workflows/verify-fotmob-real-player-context-array-admission.yml", "pull_request"),
    (".github/workflows/verify-fotmob-real-player-context-team-strength-handoff.yml", "pull_request"),
    (".github/workflows/verify-fotmob-real-player-context-authoritative-bridge.yml", "pull_request"),
    (".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml", "push"),
)

# Exact base-source identities. Git blob SHA-1 authenticates repository bytes;
# source SHA-256 uses normalized LF bytes for portable review.
_PIN_TEXT = """
.github/workflows/verify-fotmob-real-player-context-array-admission.yml|6eb1709f9118c2a962513c02c3cad2595cc5eb45|cd610b438840f44906ac20beb455928d605c60e5671910e63d3f65094efc2b97
.github/workflows/verify-fotmob-real-player-context-team-strength-handoff.yml|90c18b78adf4bd05864d25293a863bddb09f8f2d|3c6123dd100b64a0613c6dbeee9a24b0d8caf5e2e6f8feb05f56a2ff3d075b1a
.github/workflows/verify-fotmob-real-player-context-authoritative-bridge.yml|2cecc6619b29da127826bbc96bc5c35f406f8753|f46fd382e371d6be0b2cdb3105d72708f86f128e4d6a9950c7358954d89c96a3
.github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml|363962cb45ba2e229a818727753867daa66d17e6|cbc046cfde9a8bd1372abfb420ada51796bb58ba069ab7bffca2076f182e3f49
scripts/verify_fotmob_real_player_context_admission.py|ab4c07146b06c520d26198130b42877b836d6049|8fb487e36d0486056a493f5f86fadf0514487727a36704ff3be15b7c825f684c
scripts/verify_fotmob_real_player_context_team_strength_handoff.py|d1e29240f84865de15ae251e65477f9e6541de85|fdf8e25a14ec402cf79d0c77b6af5aaffa5e8b90a07c00924468f13a432ca09e
scripts/verify_fotmob_real_player_context_authoritative_bridge.py|48e975ee05fbd2d8bc6e9d915f870d6055bb3075|cf5485a683029543e881733f4a0b8b23031c9dc02c0d64f2d889de2dccf5a725
scripts/prepare_saturday_2026_08_22_reviewed_fixture_catalog.py|00ee6a0cf5877de01ace2e3588a113156bccd296|38f57c1ed32165e9e344fc3578def95edff0ac51edf2c9cb5c696714d3b00304
scripts/replay_reviewed_fixture_catalog_admission.py|126bcb5b5956e3ff0e99922580319307e1f4b66f|ada2ca71aba29f616430e652dd4116645d5abde2057865b6e57024abb9f82115
scripts/manage_fotmob_reviewed_fixture_catalog.py|eb60ff6826319ca9df49088605827d85a20abcf4|1f6ef03a7aae5b2ae0db3a74c0921b5c232d2f282cc46b23cfb987d5692e727c
scripts/manage_fixture_catalog.py|8f21f26c92f4553f346ec89dd96efa19eb7684e1|f0da75f18308972e5cd5b3d7ed71347ffed93ef2916975dd5dc0ec6bc00383b3
scripts/build_fotmob_fixture_candidates.py|0bc65229e516e233eeba9d36869ab09f18944e94|fc1d515e7649e3f71cc467d738aeaa1381899ba88e889f3ec5a01fb1eab8641f
scripts/freeze_evidence_baseline.py|2d840d75a37bd10140e6529cd354d834a47a2b6e|6a3ec2523eb62e84d8fd4461b9ef76f38616637200026fddc9c342653cba0fce
domain/fotmob_real_player_context_array_admission.py|96df0545ce0367cfccf778c74c1d5e44533f20bd|5fa9f8f3615b520b1907b005f58a3c693bb7d849725cbe8ec63d3c44c365f03f
domain/fotmob_real_player_context_team_strength_handoff.py|9b47d709f39fdff93311d8e90e06949c042bd7fd|2445a4f2e2dc2e2188f357188cea6fd6e65bf54966b4ea3b44bde90e164eb66d
domain/fotmob_real_player_context_authoritative_bridge.py|c84194fd1e6ce3de696d0d40f67a5c43578c27e0|5fa056da099eefb130a40858b35807c5b8bfd62fc686d90f9520e2ad2de3af01
domain/fotmob_real_player_context_pr191_authoritative_adapter.py|dd2d70fa9a85cdaae31fc36aca84ddae7b320635|b94d528a4adf3cd58495462898ed752f790023c5dc3f2179c67d6d3f3c7e73b3
domain/fotmob_reviewed_team_strength_context_adapter.py|c653e29d8981783c2bc45a37cc384bf96016451e|19440fc7d66044451c57faeaab9eb87c735cc6a8435e4d6e652648cd0692961a
domain/fotmob_reviewed_match_details_persisted_evidence.py|919884028f0a557ac896062f876c226f65bb020f|1e45c5b4147eec0835dd57992b8d3de7acb676b7c22025a7d15bf2bbc86e0e34
domain/fotmob_reviewed_match_details_structure.py|602be01d842df9140bd8ff91fb974ccbf7a90f99|2151b97adcdb141cd358ef7a3b733fb8a13109118591428b5c84fad661df71db
domain/fotmob_reviewed_match_details_fact_status_materializer.py|bcfa424144249f9609d79b434b3eab4cc5da94e3|ca33c113d65a2b466d3821531b79889932f8c58357daa6c9fe163af0f12ad11a
domain/fotmob_reviewed_match_details_field_evidence_qualification.py|37cc92b4b80046fc2e25d89ac964a43d6e89d840|6328a77e6bf0071bb3623647f15b96b80313e59ba01f7e947fe8c8be87836f4d
domain/fotmob_reviewed_match_details_field_review.py|460df13dbbde7087181837a7c4bba3fc7d89343b|37c2fb9c7e161ddb91b75f58a6f5a58e49cb4b086f6c5ed8ceac7cad2527296a
domain/fotmob_reviewed_match_details_fixture_intelligence_snapshot.py|2d50d3e0338a771e95e1d37038f6f5f2914848f3|66de53c51f0aeb4919e4f203472e71d2b1cce405962438af6b61ea2cb62e0300
domain/fotmob_reviewed_match_details_model_feature_handoff.py|e7b9adccdde32555ff1f70f1dfa37409165255f8|102e2c8a08108c0013a1f0a923ef26f0475f473148deb039c4c1f8c99cca49e7
domain/fotmob_reviewed_match_details_snapshot_candidate_admission.py|8dff90f32809cd27d9dcfafab936be871b077b10|b78efe1537a4f6f4fad464bd871c23176914da655e91a39c445fbc8e18f95091
domain/fotmob_reviewed_match_details_snapshot_candidate_set.py|5b11ef8382f0b85c7724ae609f1ae79164468d21|b090049800e7e3d16e99ff1b322da109ce0f4243b485bde406e0dfca1b545536
domain/fotmob_reviewed_match_details_status_classification_policy.py|6a4d1d793f6a02a1066f4a4acdc26be2722d4855|9c86360b191eb57a9bbc1413d3d6272c65a8d7aa1739e679d0d6c04bfb129f9f
domain/fotmob_reviewed_match_details_status_evaluator.py|2894101591e3a391d15b18a3b21525a4dc8c08a3|11e9d467147c160548f1b2790792c7386f4a272158a33faccb2eeb4d0f3b5078
domain/fotmob_reviewed_match_details_unverified_candidates.py|e556b05c1270893b431cac561bf820319c2033f8|15c7dc0b390a4a8d9b5919fdbc07b3904b2eb7f361af102707f3b8fdeca284de
domain/fotmob_reviewed_match_details_unverified_facts.py|a3575598025b93d7b26e58945034580bd4bc65f0|dfdabb56c7d7e0157141effb75b152b3a1187a1136ab6ea1beb108fcce38c299
domain/fotmob_team_strength_fixture_intelligence.py|74e14830452c595db2818b1ab174ab86d1d9c9b8|a054afbdef99fc6c3ceffbce05379b6d7cbb1334227684df18822cc46e2249f0
domain/fixture_intelligence.py|2657a5701025647f616179103f7ba73deb542b2a|c95fbf403f58e953db650181a901d0d826f312dc1f9af0b4bdcb91a95bae2f2e
domain/fixture_model_features.py|e8d9ebf04676b54826b71752eae5aa5d23cb6caa|60ed622fce70389b6e7fcf31b6db89dcd3b9680bf39213e506389c76488a29b1
domain/reviewed_fixture_catalog_admission_source_replay.py|b2fd258fa89afc492da35cbbe242b15203040759|2061974642bc903482772303db49e589a991c58d8ffbd94d6a137f24f8582de5
domain/reviewed_fixture_catalog_admission.py|6a878b6900eacf7f3b59c55384e65fe833c9f59a|812d1b45c97a14f2825cf307dd60b223b4b4e1fc47ed83f1ac2fd86bbd4dc71e
domain/fotmob_fixture_catalog_handoff.py|79c82b81e14dc48c0b6972cc74d646e561bc53df|3c354f92160cbb315f9ef2a2dea8d667f547d2eb3b868f940494898dffc29a4d
domain/fixture_catalog.py|b3d4032d5c2bb6325f6b199cca9f827b5f1c2782|b078249db87f1a2250fd8b8c0beef0c78c852200fbcfe6cb174eca316195ace8
domain/fotmob_data_matches_capture.py|ca2149395de868104666620173b55a880b10c729|0b0ef80511fb58f18a6d872c01bb21a603fb8750795a60c6a67c3678d9b0dd37
domain/fotmob_fixture_candidate_review.py|b1e4b005276c60ab57a27d5b3919119e434cde00|c8fe89d3db612b347e9ea318f5e195abb518eddf27d0280a3f00ddbf78d0a492
domain/fotmob_fixture_candidates.py|a3434951e87cfbd90dd2c43cccd413e7edfb08e0|bc01f72471bc4166189b643331fbd99560aac23961b6e38b502a555a43a8f439
domain/fotmob_data_matches_probe.py|c39bdea2ef65b26c3212471f6996831c4c845826|fe33ec764d332a66d817fcf22834f4c7999d4ba7b0a323ac36d0652502c1c909
domain/sportybet_lite_source_capture.py|bfb8e79e04967f7aed08578bc63dc79f2511a503|36843c8a8d953ac47e27a96235b3f757141ca68c7420f05d336e8f8c63ca1994
domain/source_capabilities.py|37b919eb5efa0c931e1bf10d3f845865567ef0c4|ba25e1c1fbe30f5e6b8244318a824f3ac7ed9dbff6d3581ca159fb0649fdc411
evidence/saturday_2026_08_22_fixture_identity_review_decisions.json|59c8871c69adab45c8e98c30b51423672c6713bc|7555b821b126a9218f9c9ec94f812eba9ad4a20440bdcd43626dc5806d62b563
"""
SOURCE_PINS = {
    row.split("|", 1)[0]: (row.split("|", 2)[1], row.split("|", 2)[2])
    for row in _PIN_TEXT.strip().splitlines()
}

ZERO_ACTIONS = {
    "provider_calls": 0,
    "artifact_payload_downloads": 0,
    "workflow_dispatch": 0,
    "workflow_rerun": 0,
    "workflow_cancel": 0,
    "approval_comment_mutations": 0,
    "historical_pr_mutations": 0,
    "external_storage_writes": 0,
    "workflow_retirement_or_deletion": 0,
}

SOURCE_EDGES = [
    {"from": TARGETS[0][0], "to": "actions/github-script getArtifact + getWorkflowRun", "kind": "EXACT_GITHUB_METADATA_READ"},
    {"from": TARGETS[0][0], "to": "scripts/verify_fotmob_real_player_context_admission.py", "kind": "EXACT_ARTIFACT_OFFLINE_REPLAY"},
    {"from": TARGETS[1][0], "to": "scripts/verify_fotmob_real_player_context_team_strength_handoff.py", "kind": "EXACT_ARTIFACT_OFFLINE_REPLAY"},
    {"from": TARGETS[2][0], "to": "scripts/verify_fotmob_real_player_context_authoritative_bridge.py", "kind": "EXACT_ARTIFACT_OFFLINE_REPLAY"},
    {"from": "scripts/verify_fotmob_real_player_context_admission.py", "to": "domain.fotmob_real_player_context_array_admission", "kind": "PURE_SOURCE_BYTES_TO_ADMISSION"},
    {"from": "domain.fotmob_real_player_context_array_admission", "to": "domain.fotmob_reviewed_match_details_persisted_evidence + structure", "kind": "PURE_REVALIDATION"},
    {"from": "scripts/verify_fotmob_real_player_context_team_strength_handoff.py", "to": "domain.fotmob_real_player_context_team_strength_handoff", "kind": "PURE_SOURCE_BYTES_TO_CANDIDATE"},
    {"from": "domain.fotmob_real_player_context_team_strength_handoff", "to": "domain.fotmob_real_player_context_array_admission", "kind": "EXACT_PR193_REPLAY"},
    {"from": "scripts/verify_fotmob_real_player_context_authoritative_bridge.py", "to": "domain.fotmob_real_player_context_authoritative_bridge + PR191 adapter", "kind": "PURE_SOURCE_BYTES_TO_REVIEWED_WRAPPER"},
    {"from": "domain.fotmob_real_player_context_authoritative_bridge", "to": "domain.fotmob_real_player_context_array_admission + team_strength_handoff + reviewed-match-detail wrappers", "kind": "EXACT_FROZEN_LINEAGE_REPLAY"},
    {"from": TARGETS[0][0], "to": "actions/download-artifact + actions/upload-artifact", "kind": "EXACT_INPUT_READ_AND_RUN_SCOPED_PROOF_WRITE"},
    {"from": TARGETS[1][0], "to": "actions/download-artifact + actions/upload-artifact", "kind": "EXACT_INPUT_READ_AND_RUN_SCOPED_PROOF_WRITE"},
    {"from": TARGETS[2][0], "to": "actions/download-artifact + actions/upload-artifact", "kind": "EXACT_INPUT_READ_AND_RUN_SCOPED_PROOF_WRITE"},
    {"from": TARGETS[3][0], "to": "actions/github-script PR/commit/artifact/comment metadata reads", "kind": "GITHUB_CONTROL_PLANE_READ"},
    {"from": TARGETS[3][0], "to": "scripts/prepare_saturday_2026_08_22_reviewed_fixture_catalog.py", "kind": "FROZEN_ARTIFACT_OFFLINE_REPLAY_AND_LOCAL_CANDIDATE"},
    {"from": "scripts/prepare_saturday_2026_08_22_reviewed_fixture_catalog.py", "to": "scripts/manage_fotmob_reviewed_fixture_catalog.py + replay_reviewed_fixture_catalog_admission.py", "kind": "LOCAL_CATALOG_PREPARE"},
    {"from": "scripts/replay_reviewed_fixture_catalog_admission.py", "to": "domain.reviewed_fixture_catalog_admission_source_replay", "kind": "LOCAL_SOURCE_REPLAY_OR_STORE"},
    {"from": TARGETS[3][0], "to": "actions/download-artifact + actions/upload-artifact", "kind": "HISTORICAL_EXACT_INPUT_READ_AND_RUN_SCOPED_OUTPUT"},
]

PR_METADATA = {
    193: {"state": "closed", "merged": True, "merged_at": "2026-08-20T20:53:46Z", "closed_at": "2026-08-20T20:53:47Z", "base_ref": "main", "base_sha": "79c9e82c0d4604147bbef1704656ab4eec24fa35", "head_repo": "Thabearr/ATHENA", "head_ref": "evidence/fotmob-real-player-context-array-admission", "head_sha": "384d3791a819112d46fac4330c23493390be94b8", "merge_sha": "81094b8278ef5d6707d99b03de5ae38562cd1a63"},
    194: {"state": "closed", "merged": True, "merged_at": "2026-08-20T22:04:32Z", "closed_at": "2026-08-20T22:04:32Z", "base_ref": "main", "base_sha": "81094b8278ef5d6707d99b03de5ae38562cd1a63", "head_repo": "Thabearr/ATHENA", "head_ref": "model/fotmob-real-player-context-team-strength-handoff", "head_sha": "c1902a4497c9ffdb78be0f371cb43e6a9fc49624", "merge_sha": "adf267dbb00856275e9afd17c719c66448b9fe07"},
    197: {"state": "closed", "merged": True, "merged_at": "2026-08-21T05:18:56Z", "closed_at": "2026-08-21T05:18:56Z", "base_ref": "main", "base_sha": "e7d4df4f82aee875eda6e72b5c3925b24b05c49f", "head_repo": "Thabearr/ATHENA", "head_ref": "model/fotmob-real-player-context-authoritative-bridge", "head_sha": "bac9648b5717c5a743ddf47411df754f9650da36", "merge_sha": "a149d523ee4e8859bfead7b7a42bfcb002fc37a8"},
    202: {"state": "closed", "merged": True, "merged_at": "2026-08-21T09:24:09Z", "closed_at": "2026-08-21T09:24:09Z", "base_ref": "main", "base_sha": "08d54c11a4e5fb11ff7d7d886bda95c1efb01f05", "head_repo": "Thabearr/ATHENA", "head_ref": "evidence/saturday-2026-08-22-reviewed-fixture-catalog", "head_sha": "09b9a8f4afdc18d4165d531958f087130566ac20", "merge_sha": "1428802b0e9c00ff0ed6d1a6c3873a751c763416"},
}

PLAYER_SOURCE = {
    "artifact_id": 9422055017,
    "run_id": 32410775191,
    "run_name": "Execute FotMob Prospective Player-Context Campaign",
    "run_path": ".github/workflows/execute-fotmob-prospective-player-context-campaign.yml",
    "run_event": "pull_request",
    "run_status": "completed",
    "run_conclusion": "success",
    "run_created_at": "2026-08-20T19:49:44Z",
    "source_head_sha": "46f76e8033d3d498131c6f893111b437b6b459a9",
    "source_branch": "evidence/fotmob-prospective-player-context-campaign",
    "artifact_name": "fotmob-prospective-player-context-evidence",
    "artifact_size": 974969,
    "artifact_digest": "sha256:db5dc12b8863cbac15f210e018ddf0af9b9011a6ad8c3958a473a597254f44b5",
}
CATALOG_SOURCE = {
    "artifact_id": 9437181220,
    "run_id": 32455713912,
    "run_name": "Capture Saturday 2026-08-22 FotMob Fixture Universe",
    "run_path": ".github/workflows/capture-saturday-2026-08-22-fixture-universe.yml",
    "run_event": "pull_request",
    "run_status": "completed",
    "run_conclusion": "success",
    "run_created_at": "2026-08-21T06:45:49Z",
    "source_head_sha": "b879b2140d0bc3fb64fa8fec4c73c735240a3b41",
    "source_branch": "evidence/saturday-2026-08-22-fixture-universe-capture",
    "artifact_name": "saturday-2026-08-22-fixture-universe-evidence",
    "artifact_digest": "sha256:360aac588f049fe6b0437c43e060b317edd12aaf4672db93ebe2fca42de00589",
}


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AssertionError(reason)


def _git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(boundary.canonical(value)).hexdigest()


def _identity(path: str) -> dict[str, Any]:
    raw = (ROOT / path).read_bytes()
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    expected_blob, expected_sha = SOURCE_PINS[path]
    blob = _git("rev-parse", "HEAD:" + path).decode().strip()
    digest = hashlib.sha256(normalized).hexdigest()
    require(blob == expected_blob, f"B5 Git blob identity drift: {path}")
    require(digest == expected_sha, f"B5 normalized source identity drift: {path}")
    if path.startswith(".github/workflows/"):
        role = "target_workflow_source_and_trigger_contract"
    elif path.startswith("scripts/"):
        role = "bounded_replay_or_catalog_entrypoint"
    elif path.startswith("domain/"):
        role = "pure_replay_semantics_or_local_catalog_boundary"
    else:
        role = "exact_review_input_ledger"
    edges = [edge for edge in SOURCE_EDGES if edge["from"] == path or edge["to"].startswith(path)]
    return {"path": path, "git_blob_sha1": blob, "normalized_source_sha256": digest,
            "role": role, "discovery_edges": edges}


def _workflow(path: str) -> dict[str, Any]:
    value = yaml.load((ROOT / path).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    require(type(value) is dict, f"workflow YAML is not a mapping: {path}")
    return value


def _repository_caller_scan() -> dict[str, Any]:
    target_files = {Path(path).name for path, _ in TARGETS}
    patterns = ("gh workflow run", "createWorkflowDispatch", "actions.createWorkflowDispatch", "repository_dispatch")
    hits: list[dict[str, str]] = []
    for path in (p for p in _git("ls-files", "-z").decode().split("\0") if p):
        if not path.startswith((".github/workflows/", "scripts/", "domain/")):
            continue
        if path.startswith("scripts/audit_") or path in {p for p, _ in TARGETS}:
            continue
        try:
            text = (ROOT / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(term in text for term in patterns) and any(name in text for name in target_files):
            hits.append({"path": path, "classification": "POTENTIAL_STATIC_TARGET_CALL_REQUIRES_REVIEW"})
    return {
        "method": "TRACKED_WORKFLOW_SCRIPT_DOMAIN_SCAN_FOR_DISPATCH_AND_TARGET_NAMES",
        "candidate_hits": sorted(hits, key=lambda row: row["path"]),
        "result": "NO_CURRENT_REPOSITORY_CALLER_FOUND_SOURCE_SCAN" if not hits else "CALLER_CANDIDATE_FOUND",
        "external_manual_or_push_control_plane": "NOT_ERASED_BY_NO_REPOSITORY_CALLER_SCAN",
    }


def _workflow_contract(path: str) -> dict[str, Any]:
    value = _workflow(path)
    jobs = {}
    for name, job in value.get("jobs", {}).items():
        jobs[name] = {
            "if": job.get("if"),
            "permissions": job.get("permissions", {}),
            "steps": [{
                "name": step.get("name"), "if": step.get("if"), "uses": step.get("uses"),
                "run_sha256": hashlib.sha256(step.get("run", "").encode()).hexdigest()
                if step.get("run") is not None else None,
                "environment_names": sorted(step.get("env", {})),
                "persist_credentials": step.get("with", {}).get("persist-credentials"),
            } for step in job.get("steps", [])],
        }
    return {"workflow_permissions": value.get("permissions", {}), "triggers": value.get("on", {}),
            "concurrency": value.get("concurrency", {}), "jobs": jobs}


def _validate_source_semantics() -> None:
    require(len(TARGETS) == 4 and len(set(TARGETS)) == 4, "B5 must review exactly four unique surfaces")
    require(SOURCE_PINS and len(SOURCE_PINS) == len(set(SOURCE_PINS)), "invalid B5 source pin map")
    parent = boundary.read(COMPLETION_V7_PATH)
    require(parent.get("canonical_sha256") == COMPLETION_V7_SHA, "immutable Completion V7 identity drift")
    parent_keys = {(row["workflow_path"], row["trigger_kind"]) for row in parent["unreviewed_authority_surfaces"]}
    require(len(parent_keys) == 7 and set(TARGETS) <= parent_keys, "B5 target set is not inherited from Completion V7")
    require(_git("rev-parse", "HEAD:.github/workflows").decode().strip() == WORKFLOW_TREE,
            "B5 workflow subtree differs from handoff tree")
    evolution = boundary.read("artifacts/architecture/p4_workflow_evolution_ledger_v1.json")
    retirement = boundary.read("artifacts/architecture/p4_3_workflow_retirement_ledger_v1.json")
    require(evolution.get("canonical_sha256") == EVOLUTION_SHA and len(evolution.get("transitions", [])) == 14,
            "B5 workflow evolution ledger identity/transition count drift")
    require(retirement.get("canonical_sha256") == RETIREMENT_SHA and len(retirement.get("retirements", [])) == 3,
            "B5 retirement ledger identity/count drift")
    require(not _git("diff", "--name-only", "HEAD", "--", ".github/workflows").decode().strip(),
            "B5 contains a tracked workflow edit")
    untracked = set(_git("ls-files", "--others", "--exclude-standard").decode().splitlines())
    require(not any(path.startswith(".github/workflows/") for path in untracked), "B5 contains an untracked workflow edit")
    for path in SOURCE_PINS:
        _identity(path)

    array = _workflow(TARGETS[0][0])
    team = _workflow(TARGETS[1][0])
    bridge = _workflow(TARGETS[2][0])
    catalog = _workflow(TARGETS[3][0])
    require(set(array["on"]) == {"pull_request"} and array["on"]["pull_request"]["types"] == ["opened", "synchronize", "reopened", "edited"],
            "array-admission event surface drift")
    require(set(team["on"]) == {"pull_request"} and team["on"]["pull_request"]["types"] == ["opened", "synchronize", "reopened", "edited"],
            "team-strength event surface drift")
    require(set(bridge["on"]) == {"pull_request"} and bridge["on"]["pull_request"]["types"] == ["opened", "synchronize", "reopened", "edited"],
            "authoritative-bridge event surface drift")
    require(set(catalog["on"]) == {"pull_request", "push"} and catalog["on"]["push"]["branches"] == ["main"],
            "catalog push surface/sibling trigger drift")
    guards = [array["jobs"]["verify"]["if"], team["jobs"]["verify"]["if"], bridge["jobs"]["verify"]["if"]]
    expected_refs = ("evidence/fotmob-real-player-context-array-admission", "model/fotmob-real-player-context-team-strength-handoff", "model/fotmob-real-player-context-authoritative-bridge")
    for guard, ref in zip(guards, expected_refs, strict=True):
        require("github.event.pull_request.head.repo.full_name == github.repository" in guard and ref in guard,
                "player-context same-repository/exact-branch job guard drift")
    for path, workflow in ((TARGETS[0][0], array), (TARGETS[1][0], team), (TARGETS[2][0], bridge)):
        raw = (ROOT / path).read_text(encoding="utf-8")
        require(workflow.get("jobs", {}).get("verify", {}).get("permissions", {}).get("contents") == "read",
                "player-context job contents permission drift")
        require("permissions" not in workflow, "player-context workflow-level permission scope changed")
        require("secrets." not in raw and "persist-credentials: false" in raw,
                "player-context credential surface or checkout persistence changed")
        require("artifact-ids:" in raw and "actions/upload-artifact@" in raw,
                "player-context exact artifact read/proof write edge changed")
    for path, frozen_base in zip((TARGETS[0][0], TARGETS[1][0], TARGETS[2][0]),
                                 ("79c9e82c0d4604147bbef1704656ab4eec24fa35", "81094b8278ef5d6707d99b03de5ae38562cd1a63", "e7d4df4f82aee875eda6e72b5c3925b24b05c49f"), strict=True):
        raw = (ROOT / path).read_text(encoding="utf-8")
        require(f"pr.base.sha !== '{frozen_base}'" in raw, "player-context frozen base SHA guard drift")
        require("getArtifact" in raw and "getWorkflowRun" in raw, "player-context metadata guard order drift")
    require("team_strength_feature_authorized=false" in (ROOT / "scripts/verify_fotmob_real_player_context_team_strength_handoff.py").read_text(),
            "PR194 candidate-only authority assertion disappeared")
    bridge_script = (ROOT / "scripts/verify_fotmob_real_player_context_authoritative_bridge.py").read_text()
    require("team_strength_feature_authorized=true" in bridge_script and "probability_pricing_selection_bet_authorized=false" in bridge_script,
            "PR197 scoped feature authority assertion drift")
    require("Download exact successful PR192 evidence artifact" in array["jobs"]["verify"]["steps"][5]["name"],
            "array replay download position drift")
    require("github.event_name == 'push'" in catalog["jobs"]["admit-on-merged-main"]["if"], "catalog push job guard drift")
    catalog_raw = (ROOT / TARGETS[3][0]).read_text(encoding="utf-8")
    # This workflow has a separate pull_request job with its own checkout and
    # artifact download.  Bound ordering assertions to the reviewed push job so
    # the B1 sibling cannot satisfy or invalidate the push-surface proof.
    push_job = catalog_raw.split("  admit-on-merged-main:", 1)[1]
    ordered = ("pulls.get", "repos.getCommit", "actions.getArtifact", "actions/checkout@", "actions/download-artifact@",
               "Prepare exact merge-commit catalog admission decision", "Check exact-byte admission approval comment",
               "Upload merge-commit admission decision candidate before gate", "Require separate exact-byte admission review",
               "Store source-replayed exact catalog admission")
    offsets = [push_job.find(item) for item in ordered]
    require(all(offset >= 0 for offset in offsets) and offsets == sorted(offsets), "catalog exact guarded operation order drift")
    require("persist-credentials: false" in catalog_raw and "contents: read" in catalog_raw and "contents: write" not in catalog_raw,
            "catalog repository token/write boundary drift")
    require("fetch_workflow_run_artifacts" not in catalog_raw, "catalog source unexpectedly acquired artifact payload in workflow code")
    require(_repository_caller_scan()["result"] == "NO_CURRENT_REPOSITORY_CALLER_FOUND_SOURCE_SCAN",
            "B5 source caller scan found an unreviewed target caller")


def build_source_inventory() -> dict[str, Any]:
    _validate_source_semantics()
    contracts = {path: _workflow_contract(path) for path, _ in TARGETS}
    return boundary.seal({
        "schema_version": 1, "policy_id": INVENTORY_POLICY_ID, "repository": "Thabearr/ATHENA",
        "base_main_sha": BASE_MAIN, "base_tree_sha": BASE_TREE, "observed_at_utc": OBSERVED_AT,
        "target_keys": [[path, trigger] for path, trigger in TARGETS],
        "source_count": len(SOURCE_PINS), "sources": [_identity(path) for path in sorted(SOURCE_PINS)],
        "workflow_contracts": contracts, "source_edges": SOURCE_EDGES,
        "historical_control_prs": {str(number): value for number, value in PR_METADATA.items()},
        "frozen_player_source": PLAYER_SOURCE,
        "frozen_catalog_source": CATALOG_SOURCE,
        "read_only_observations": {
            "post_443_tests": {**POST_443_TESTS, "read_only": True,
                "endpoint": "/repos/Thabearr/ATHENA/actions/runs/37176160320", "observed_at_utc": OBSERVED_AT},
            "player_artifact_listing": {"run_id": 32410775191, "artifact_id": 9422055017,
                "state": "CURRENT_ACTIONS_ARTIFACT_LISTING_EMPTY", "total_count": 0, "read_only": True,
                "endpoint": "/repos/Thabearr/ATHENA/actions/runs/32410775191/artifacts", "observed_at_utc": OBSERVED_AT},
            "catalog_source_artifact_listing": {"run_id": 32455713912, "artifact_id": 9437181220,
                "state": "CURRENT_ACTIONS_ARTIFACT_LISTING_EMPTY", "total_count": 0, "read_only": True,
                "endpoint": "/repos/Thabearr/ATHENA/actions/runs/32455713912/artifacts", "observed_at_utc": OBSERVED_AT},
            "historical_branches": {"state": "NOT_FOUND_AT_READ_ONLY_REF_LOOKUP", "permanent_absence_proven": False,
                "refs": ["evidence/fotmob-real-player-context-array-admission", "model/fotmob-real-player-context-team-strength-handoff",
                         "model/fotmob-real-player-context-authoritative-bridge", "evidence/saturday-2026-08-22-reviewed-fixture-catalog"],
                "observed_at_utc": OBSERVED_AT},
            "catalog_current_main_push": {"run_id": 37176160133, "head_sha": BASE_MAIN, "event": "push",
                "status": "completed", "conclusion": "success", "job": "admit-on-merged-main",
                "steps": {"Bind this push to the exact PR202 merge commit": "success",
                          "Stop unrelated main pushes cleanly": "success",
                          "Check out exact PR202 merge commit": "skipped",
                          "Download exact PR199 source artifact for merged replay": "skipped",
                          "Prepare exact merge-commit catalog admission decision": "skipped",
                          "Store source-replayed exact catalog admission": "skipped",
                          "Upload exact admitted merge-commit proof": "skipped"}, "read_only": True,
                "endpoint": "/repos/Thabearr/ATHENA/actions/runs/37176160133", "observed_at_utc": OBSERVED_AT},
            "catalog_historical_exact_merge_push": {"run_id": 32467715248, "head_sha": PR_METADATA[202]["merge_sha"],
                "event": "push", "status": "completed", "conclusion": "failure", "run_attempt": 1,
                "steps": {"Bind this push to the exact PR202 merge commit": "success",
                          "Download exact PR199 source artifact for merged replay": "success",
                          "Prepare exact merge-commit catalog admission decision": "success",
                          "Check exact-byte admission approval comment": "success-with-no-matching-comment",
                          "Upload merge-commit admission decision candidate before gate": "success",
                          "Require separate exact-byte admission review": "failure",
                          "Store source-replayed exact catalog admission": "skipped",
                          "Upload exact admitted merge-commit proof": "skipped"}, "read_only": True,
                "endpoint": "/repos/Thabearr/ATHENA/actions/runs/32467715248", "observed_at_utc": OBSERVED_AT},
            "post_failure_approval_comment": {"issue": 202, "id": 5368504537, "author": "Thabearr",
                "created_at": "2026-08-21T10:11:28Z", "updated_at": "2026-08-21T10:11:28Z",
                "body": "ATHENA_CATALOG_ADMISSION_APPROVED_SHA256=952fd708031e880b3f7f1a38c09e38265035220c5be82711acbe26d1ba97ca87",
                "read_only": True, "endpoint": "/repos/Thabearr/ATHENA/issues/202/comments", "observed_at_utc": OBSERVED_AT},
            "later_exact_merge_workflow_runs": {"query": "gh run list --commit 1428802b0e9c00ff0ed6d1a6c3873a751c763416; filter exact workflow name/path",
                "matching_runs": [32467715248], "later_same_workflow_attempt_found": False,
                "interpretation": "NO_LATER_EXACT_MERGE_CATALOG_RUN_OBSERVED_AT_CAPTURE_TIME", "read_only": True,
                "observed_at_utc": OBSERVED_AT},
        },
        "repository_caller_scan": _repository_caller_scan(),
        "external_side_effect_entrypoints": {
            "player_context": {"new_provider_acquisition": "NONE", "historical_artifact_payload_read": "ACTIONS_DOWNLOAD_ARTIFACT_EXACT_ID"},
            "catalog": {"new_provider_acquisition": "NONE", "historical_artifact_payload_read": "ACTIONS_DOWNLOAD_ARTIFACT_EXACT_ID",
                "external_storage_write": "NONE", "github_branch_write": "NONE", "github_release_write": "NONE",
                "local_runner_write": ["reviewed catalog candidate", "source-replayed local admission only after exact approval"]},
        },
        "no_workflow_mutation": True, "no_live_execution": True,
        "source_scope": "EXACT_FOUR_B5_SURFACES_AND_DIRECT_REPLAY_CALLEES_ONLY",
    })


def _target_kind(path: str) -> str:
    if path.endswith("array-admission.yml"):
        return "PR193_EXACT_OBSERVATION_ARRAY_ADMISSION"
    if path.endswith("team-strength-handoff.yml"):
        return "PR194_TEAM_STRENGTH_CANDIDATE_HANDOFF"
    if path.endswith("authoritative-bridge.yml"):
        return "PR197_EXISTING_PR191_AUTHORITY_CONTEXT_BRIDGE"
    if path.endswith("reviewed-fixture-catalog.yml"):
        return "PR202_REVIEWED_FIXTURE_CATALOG_PUSH_ADMISSION"
    raise AssertionError(f"unknown B5 target {path}")


def _player_row(path: str, trigger: str, inventory: dict[str, Any]) -> dict[str, Any]:
    source = next(row for row in inventory["sources"] if row["path"] == path)
    pr_number = {TARGETS[0][0]: 193, TARGETS[1][0]: 194, TARGETS[2][0]: 197}[path]
    frozen_base = {193: PR_METADATA[193]["base_sha"], 194: PR_METADATA[194]["base_sha"], 197: PR_METADATA[197]["base_sha"]}[pr_number]
    branch = PR_METADATA[pr_number]["head_ref"]
    kind = _target_kind(path)
    feature = pr_number == 197
    scope = {
        193: "EXACT_OBSERVATION_ARRAY_SEMANTICS_ONLY",
        194: "EXACT_PR193_REPLAY_AND_TEAM_STRENGTH_CANDIDATE_MAPPING_ONLY",
        197: "EXACT_PR192_PR193_PR194_PR65_PR66_AND_PR191_WRAPPER_REPLAY",
    }[pr_number]
    return {
        "identity": {"workflow_path": path, "trigger_kind": trigger, "git_blob_sha1": source["git_blob_sha1"],
                     "normalized_source_sha256": source["normalized_source_sha256"]},
        "event_contract": {"event": "pull_request", "activity_types": ["opened", "synchronize", "reopened", "edited"],
            "workflow_path_filters": [], "job_guard": f"same-repository && head.ref == {branch!r}",
            "control_pr": pr_number, "frozen_base_sha": frozen_base,
            "artifact_id": PLAYER_SOURCE["artifact_id"], "source_run_id": PLAYER_SOURCE["run_id"],
            "source_head_sha": PLAYER_SOURCE["source_head_sha"], "source_artifact_digest": PLAYER_SOURCE["artifact_digest"],
            "guard_order": ["physical pull_request event", "same-repository/exact-head-branch job guard",
                "frozen pull_request.base.sha script guard", "getArtifact exact frozen id", "getWorkflowRun exact source run",
                "checkout PR head persist-credentials=false", "toolchain/dependencies", "download exact artifact payload",
                "offline replay", "upload run-scoped proof artifact", "step summary"]},
        "current_control_state": {"control_pr": PR_METADATA[pr_number],
            "historical_branch_state": "ABSENT_AT_READ_ONLY_REF_LOOKUP_NOT_PERMANENT_PROOF",
            "source_artifact_listing": "CURRENT_ACTIONS_ARTIFACT_LISTING_EMPTY_NOT_PROVEN_PERMANENT",
            "source_run_metadata": {key: PLAYER_SOURCE[key] for key in ("run_id", "run_name", "run_path", "run_event", "run_status", "run_conclusion", "source_head_sha", "source_branch")},
            "current_main_pr_event": "UNRELATED_PR_EVENT_MAY_START_RUN_BUT_EXACT_HEAD_BRANCH_JOB_GUARD_SKIPS",
            "recreated_branch_event": "JOB_GUARD_MAY_PASS_BUT_FROZEN_HISTORICAL_BASE_SHA_GUARD_FAILS_FOR_CURRENT_BASE",
            "historical_merged_pr_edited_event": "DECLARED_EDITED_ACTIVITY_IS_NOT_ASSUMED_IMPOSSIBLE; if historical payload matches the guard, artifact metadata is requested"},
        "permissions_and_credentials": {"workflow_permissions": {},
            "job_permissions": {"actions": "read", "contents": "read", "pull-requests": "read"},
            "job_token_use": ["actions/github-script metadata API", "actions/download-artifact exact id"],
            "explicit_secrets_bindings": [], "provider_or_user_credentials": "NONE_SOURCE_PATH",
            "checkout_persist_credentials": False, "package_toolchain_network": "BUILD_TOOLCHAIN_NETWORK_NOT_PROVIDER_ACQUISITION"},
        "dynamic_reachability": {"edges": [
            {"from": path, "to": "github.rest.actions.getArtifact(9422055017)", "kind": "ACTIONS_ARTIFACT_METADATA_READ"},
            {"from": path, "to": "github.rest.actions.getWorkflowRun(32410775191)", "kind": "ACTIONS_RUN_METADATA_READ"},
            {"from": path, "to": "actions/download-artifact exact id 9422055017", "kind": "HISTORICAL_PAYLOAD_READ_AFTER_METADATA_GUARDS"},
            {"from": path, "to": "actions/upload-artifact", "kind": "RUN_SCOPED_PROOF_WRITE"},
            {"from": path, "to": "GITHUB_STEP_SUMMARY", "kind": "RUN_SUMMARY_WRITE"},
        ], "artifact_payload_download_ordinal": 8, "first_high_risk_boundary": "exact artifact payload download after frozen PR/base/artifact/run metadata guards",
            "provider_network_edge": "NONE_REPLAY_CONSUMES_EXACT_LOCAL_ARTIFACT_BYTES_ONLY",
            "repository_branch_write": "NONE_CONTENTS_READ_ONLY_AND_CHECKOUT_CREDENTIALS_DISABLED",
            "external_storage_write": "NONE"},
        "historical_guarded_capability": {"pr_metadata_read": "NOT_USED_BY_RUNNER; EVENT_PAYLOAD_FIELDS_ONLY",
            "actions_artifact_metadata_read": "EXACT_ARTIFACT_ID_AND_PROVENANCE", "actions_run_metadata_read": "EXACT_SOURCE_RUN_ID",
            "artifact_payload_read": "EXACT_FROZEN_PR192_ARCHIVE", "provider_acquisition": "NONE",
            "offline_replay": scope, "semantic_admission": "EXACT_OBSERVATION_ARRAY_ONLY" if pr_number == 193 else "NONE_ADDED_BY_THIS_ROW",
            "team_strength_candidate_authority": "CANDIDATE_MAPPING_ONLY_FEATURE_AUTHORITY_FALSE" if pr_number == 194 else "NONE_ADDED_BY_THIS_ROW",
            "team_strength_feature_authority": "YES_ONLY_IN_EXISTING_PR191_WRAPPER_AT_EXACT_FRESHNESS_INSTANT" if feature else "FALSE",
            "probability_pricing_selection_bet": "FALSE", "actions_artifact_write": "RUN_SCOPED_PROOF_ARTIFACT",
            "step_summary_write": "GITHUB_STEP_SUMMARY", "repo_or_branch_write": "NONE", "release_write": "NONE",
            "external_storage_write": "NONE", "delivery_notification": "NONE", "wager": "NONE"},
        "current_observed_control_state_authority": {"declared_event_surface": "PHYSICALLY_REACHABLE_PULL_REQUEST_TYPES_OPENED_SYNCHRONIZE_REOPENED_EDITED",
            "unrelated_pr_path": "JOB_SKIPPED_BY_EXACT_BRANCH_GUARD", "recreated_branch_current_base_path": "BLOCKED_BY_FROZEN_BASE_SHA_BEFORE_ARTIFACT_METADATA",
            "historical_exact_identity_path": "BLOCKED_AT_CURRENT_ARTIFACT_METADATA_LOOKUP_BECAUSE_LISTING_EMPTY",
            "github_metadata_read": "POSSIBLE_BEFORE_CURRENT_ARTIFACT_ABSENCE_FAIL", "artifact_payload_read": "NOT_CURRENTLY_REACHED",
            "provider_acquisition": "NONE", "offline_replay": "NOT_CURRENTLY_REACHED", "actions_artifact_write": "NOT_CURRENTLY_REACHED",
            "team_strength_feature_authority": "FALSE_CURRENTLY_BLOCKED_BEFORE_REPLAY"},
        "residuals": {"historical_source_artifact_absence": "HISTORICAL_SOURCE_ARTIFACT_CURRENTLY_ABSENT_NOT_PROVEN_PERMANENT",
            "historical_branch_absence": "BRANCH_ABSENT_AT_OBSERVATION_NOT_PROVEN_PERMANENT",
            "historical_actions_rerun_residual": "HISTORICAL_ACTIONS_RERUN_RESIDUAL_NOT_PROVEN_ABSENT",
            "recreated_branch_or_ref_mutability": "NOT_PROVEN_IMPOSSIBLE", "artifact_availability_used_as_permanent_safety_claim": False},
        "review": {"status": "RESOLVED", "blocker": None, "historical_semantic_scope": kind},
    }


def _catalog_row(inventory: dict[str, Any]) -> dict[str, Any]:
    path, trigger = TARGETS[3]
    source = next(row for row in inventory["sources"] if row["path"] == path)
    contract = inventory["workflow_contracts"][path]
    return {
        "identity": {"workflow_path": path, "trigger_kind": trigger, "git_blob_sha1": source["git_blob_sha1"],
                     "normalized_source_sha256": source["normalized_source_sha256"]},
        "event_contract": {"event": "push", "branch_filter": ["main"], "path_filter": [],
            "job_guard": "github.event_name == 'push' && github.ref == 'refs/heads/main'",
            "historical_control_pr": 202, "historical_merge_sha": PR_METADATA[202]["merge_sha"],
            "source_artifact_id": CATALOG_SOURCE["artifact_id"], "source_run_id": CATALOG_SOURCE["run_id"],
            "source_head_sha": CATALOG_SOURCE["source_head_sha"], "source_digest": CATALOG_SOURCE["artifact_digest"],
            "guard_order": ["get PR #202 metadata", "require merged and merge_commit_sha == context.sha",
                "get exact commit metadata and check two-parent/head relation", "get source artifact metadata",
                "otherwise clean-stop on unrelated main push", "checkout exact merge commit with persist-credentials=false",
                "toolchain/dependencies", "download exact artifact payload", "prepare local catalog candidate",
                "read exact approval issue comment", "upload candidate Actions artifact", "fail if approval absent",
                "locally store source-replayed admission if approved", "upload admitted Actions proof if approved"]},
        "current_control_state": {"control_pr": PR_METADATA[202], "source_artifact_listing": "CURRENT_ACTIONS_ARTIFACT_LISTING_EMPTY_NOT_PROVEN_PERMANENT",
            "ordinary_main_push_run": inventory["read_only_observations"]["catalog_current_main_push"],
            "exact_merge_historical_run": inventory["read_only_observations"]["catalog_historical_exact_merge_push"],
            "post_failure_approval_comment": inventory["read_only_observations"]["post_failure_approval_comment"],
            "later_exact_merge_store_execution": "NOT_OBSERVED; exact-merge workflow query found only failed run 32467715248",
            "repush_mutability": "EXACT_HISTORICAL_MERGE_SHA_REPUSH_RESIDUAL_NOT_PROVEN_IMPOSSIBLE"},
        "permissions_and_credentials": {"workflow_permissions": contract["workflow_permissions"],
            "job_permissions": contract["jobs"]["admit-on-merged-main"]["permissions"],
            "github_token_capabilities": ["pull request metadata read", "commit metadata read", "Actions artifact metadata/read", "issue comment read"],
            "explicit_secrets_bindings": [], "checkout_persist_credentials": False,
            "contents_write_permission": False, "toolchain_network": "GITHUB_ACTIONS_AND_PACKAGE_TOOLCHAIN_NETWORK"},
        "dynamic_reachability": {"edges": [
            {"from": path, "to": "github.rest.pulls.get(202)", "kind": "PULL_REQUEST_METADATA_READ"},
            {"from": path, "to": "github.rest.repos.getCommit(context.sha)", "kind": "COMMIT_METADATA_READ_AFTER_EXACT_MERGE_MATCH"},
            {"from": path, "to": "github.rest.actions.getArtifact(9437181220)", "kind": "ACTIONS_ARTIFACT_METADATA_READ_AFTER_COMMIT_GUARDS"},
            {"from": path, "to": "actions/download-artifact exact id 9437181220", "kind": "HISTORICAL_PAYLOAD_READ_AFTER_METADATA_GUARDS"},
            {"from": path, "to": "issue #202 comments exact-byte SHA approval read", "kind": "ISSUE_COMMENT_READ"},
            {"from": path, "to": "actions/upload-artifact candidate and admitted proof", "kind": "RUN_SCOPED_ARTIFACT_WRITE"},
            {"from": path, "to": "scripts/replay_reviewed_fixture_catalog_admission.py store", "kind": "LOCAL_RUNNER_ADMISSION_STORE_ONLY_AFTER_APPROVAL"}],
            "ordinary_current_main_push_first_stop": "PR_METADATA_READ_THEN_SHA_MISMATCH_CLEAN_STOP",
            "conditional_exact_merge_first_high_risk_boundary": "source artifact metadata lookup after PR and commit guards",
            "github_branch_write": "NONE", "persistent_repository_or_database_write": "NONE",
            "local_runner_writes": ["catalog files", "candidate receipt", "source-replayed local admission only if exact approval gate passes"]},
        "historical_guarded_capability": {"pr_metadata_read": "PR202", "commit_metadata_read": "EXACT_MERGE_COMMIT_AND_TWO_PARENTS",
            "artifact_metadata_read": "EXACT_SOURCE_ARTIFACT_ID_AND_PROVENANCE", "artifact_payload_read": "EXACT_PR199_CAPTURE_ARCHIVE",
            "provider_acquisition": "NONE_REPLAYS_FROZEN_BYTES", "candidate_catalog_local_write": "YES_RUNNER_WORKSPACE",
            "approval_comment_read": "EXACT_CANDIDATE_SHA_AND_OWNER", "candidate_artifact_write": "RUN_SCOPED_ACTIONS_ARTIFACT_BEFORE_FINAL_APPROVAL_GATE",
            "admission_local_store": "CONDITIONAL_EXACT_SOURCE_REPLAY_AFTER_APPROVAL_ONLY",
            "admitted_artifact_write": "CONDITIONAL_RUN_SCOPED_ACTIONS_ARTIFACT_AFTER_LOCAL_STORE",
            "repo_branch_write": "NONE_READ_ONLY_REPOSITORY_PERMISSIONS_AND_CHECKOUT_CREDENTIALS_DISABLED",
            "persistent_canonical_database_write": "NONE_LOCAL_RUNNER_FILES_ONLY", "external_storage_write": "NONE",
            "release_write": "NONE", "fixture_intelligence_model_probability_sportybet_pricing_selection_bet": "FALSE"},
        "current_observed_control_state_authority": {"physical_push_event_surface": "LIVE_ON_MAIN_PUSHES",
            "ordinary_current_push": "PR_METADATA_READ_THEN_EXACT_MERGE_SHA_MISMATCH_AND_CLEAN_STOP",
            "current_run_37176160133": "CHECKOUT_ARTIFACT_DOWNLOAD_REPLAY_APPROVAL_STORE_AND_ADMITTED_UPLOAD_SKIPPED",
            "if_exact_merge_sha_reappears": "COMMIT_AND_SOURCE_ARTIFACT_METADATA_READS; CURRENT_EMPTY_SOURCE_ARTIFACT_LISTING_SHOULD_FAIL_BEFORE_PAYLOAD_DOWNLOAD",
            "approval_comment_exists": True, "approval_comment_is_current_source_artifact_recovery": False,
            "provider_acquisition": "NONE", "branch_or_persistent_db_write": "NONE", "candidate_artifact_write_on_current_run": "NOT_REACHED"},
        "residuals": {"source_artifact_absence": "CURRENTLY_EMPTY_NOT_PROVEN_PERMANENT",
            "exact_merge_sha_repush": "EXACT_HISTORICAL_MERGE_SHA_REPUSH_RESIDUAL_NOT_PROVEN_IMPOSSIBLE",
            "historical_actions_rerun": "HISTORICAL_ACTIONS_RERUN_RESIDUAL_NOT_PROVEN_ABSENT",
            "catalog_approval_comment": "COMMENT_READ_ONLY_APPROVAL_AFTER_ORIGINAL_FAILURE; no later target-workflow store run observed",
            "local_store_is_repo_write": False},
        "review": {"status": "RESOLVED", "blocker": None},
    }


def build_receipt() -> dict[str, Any]:
    inventory = build_source_inventory()
    rows = [_player_row(*target, inventory) for target in TARGETS[:3]] + [_catalog_row(inventory)]
    a2_chain = boundary.load_inventory_generations()
    generations = [generation for generation, _ in boundary.discover_inventory_generations()]
    require(generations[:8] == [1, 2, 3, 4, 5, 6, 7, 8] and len(generations) >= 8,
            "B5 requires the immutable contiguous A2 V1-V8 prefix")
    a2_v7 = a2_chain[6][1]
    a2_v8 = a2_chain[7][1]
    require(a2_v7["canonical_sha256"] == boundary.read(A2_V7_PATH)["canonical_sha256"]
            and a2_v7["predecessor_inventory"] == {
                "path": A2_V6_PATH, "canonical_sha256": A2_V6_SHA,
                "generation": 6, "rewritten": False},
            "A2 V7 does not bind the exact immutable V6 predecessor")
    require(a2_v8["predecessor_inventory"] == {
                "path": A2_V7_PATH, "canonical_sha256": a2_v7["canonical_sha256"],
                "generation": 7, "rewritten": False},
            "A2 V8 does not bind the exact immutable V7 predecessor")
    latest = boundary.authenticate_inventory()
    require(latest.get("generation", 0) >= 8,
            "current A2 source inventory must retain the reviewed V8 prefix")
    return boundary.seal({
        "schema_version": 1, "policy_id": POLICY_ID, "repository": "Thabearr/ATHENA", "master_issue": 337,
        "base_main_sha": BASE_MAIN, "base_tree_sha": BASE_TREE,
        "post_443_tests": POST_443_TESTS,
        "predecessor_completion_v7": {"path": COMPLETION_V7_PATH, "canonical_sha256": COMPLETION_V7_SHA, "rewritten": False},
        "predecessor_b4_review": {"path": B4_PATH, "canonical_sha256": B4_SHA, "rewritten": False},
        "a2_generation_6": {"path": A2_V6_PATH, "canonical_sha256": A2_V6_SHA, "generation": 6, "rewritten": False},
        "a2_generation_5_sha256": A2_V5_SHA,
        "a2_generation_7": {"path": A2_V7_PATH, "canonical_sha256": a2_v7["canonical_sha256"],
                             "generation": 7, "predecessor_generation": 6,
                             "predecessor_canonical_sha256": A2_V6_SHA, "rewritten": False},
        "source_inventory": {"path": SOURCE_INVENTORY_PATH, "canonical_sha256": inventory["canonical_sha256"]},
        "scope": {"inherited_unresolved_surface_count": 7, "target_surface_count": 4,
            "resolved_target_count": sum(row["review"]["status"] == "RESOLVED" for row in rows),
            "partial_target_count": sum(row["review"]["status"] != "RESOLVED" for row in rows),
            "global_unresolved_before": 7,
            "global_unresolved_after": 7 - sum(row["review"]["status"] == "RESOLVED" for row in rows),
            "target_keys": [[path, trigger] for path, trigger in TARGETS]},
        "review_rows": rows,
        "workflow_tree_sha1": WORKFLOW_TREE, "evolution_ledger_sha256": EVOLUTION_SHA, "transition_count": 14,
        "retirement_ledger_sha256": RETIREMENT_SHA, "retired_workflow_count": 3,
        "live_missing_artifact_relation_count": 0, "historical_missing_artifact_relation_count": 14,
        "retention_blockers_A_B_C_D": "CLOSED_WITH_HISTORICAL_LIMITATIONS_PRESERVED",
        "workflow_edit_count": 0, "trigger_edit_count": 0, "workflow_retirement_count": 0,
        "workflow_deletion_count": 0, "caller_migration_count": 0,
        "actions": ZERO_ACTIONS,
        "source_review_counter_while_open": "4/5", "source_review_counter_if_owner_merges": "5/5",
        "mandatory_governing_source_reread_after_b5_merge": True,
        "do_not_start_b6_before_reread": True,
        "criterion_11": False, "criterion_14": False,
        "checkpoint_e_status": "INCOMPLETE", "p4_4_status": "INCOMPLETE",
        "terminal": "CORE_01D_FROZEN_ARTIFACT_REPLAY_AUTHORITY_B5_REVIEW_READY_4_RESOLVED_DO_NOT_MERGE",
    })


def validate_source_inventory(value: dict[str, Any] | None = None) -> dict[str, Any]:
    value = boundary.read(SOURCE_INVENTORY_PATH) if value is None else value
    require((ROOT / SOURCE_INVENTORY_PATH).read_bytes() == boundary.canonical(value), "B5 source inventory is not canonical")
    expected = build_source_inventory()
    require(value == expected, "B5 source inventory differs from exact source/metadata evidence")
    require(value["target_keys"] == [[path, trigger] for path, trigger in TARGETS], "B5 source inventory scope drift")
    require(value["repository_caller_scan"]["result"] == "NO_CURRENT_REPOSITORY_CALLER_FOUND_SOURCE_SCAN",
            "B5 caller scan found an unreviewed source caller")
    return value


def validate_receipt(value: dict[str, Any] | None = None) -> dict[str, Any]:
    value = boundary.read(RECEIPT_PATH) if value is None else value
    require((ROOT / RECEIPT_PATH).read_bytes() == boundary.canonical(value), "B5 receipt is not canonical")
    inventory = validate_source_inventory()
    expected = build_receipt()
    require(value == expected, "B5 receipt differs from source, metadata, and Completion V7 derivation")
    keys = [(row["identity"]["workflow_path"], row["identity"]["trigger_kind"]) for row in value["review_rows"]]
    require(len(keys) == len(set(keys)) == 4 and set(keys) == set(TARGETS), "B5 receipt must contain exact four unique keys")
    require(all(row["review"]["status"] == "RESOLVED" for row in value["review_rows"]), "B5 row unresolved")
    require(value["scope"]["global_unresolved_after"] == 3, "B5 remaining count must derive to three")
    require(value["actions"] == ZERO_ACTIONS, "B5 performed or claimed a prohibited live action")
    require(value["criterion_11"] is False and value["criterion_14"] is False and
            value["checkpoint_e_status"] == value["p4_4_status"] == "INCOMPLETE", "B5 cannot complete Checkpoint E")
    require(value["source_inventory"]["canonical_sha256"] == inventory["canonical_sha256"], "B5 source inventory binding drift")
    return value


def audit() -> dict[str, Any]:
    a2_v8 = boundary.read(boundary.inventory_generation_path(8))
    require(a2_v8.get("generation") == 8, "immutable A2 generation V8 missing")
    require(a2_v8.get("predecessor_inventory", {}).get("path") == A2_V7_PATH
            and a2_v8.get("predecessor_inventory", {}).get("canonical_sha256") ==
            boundary.read(A2_V7_PATH)["canonical_sha256"],
            "A2 V8 predecessor must be exact V7")
    require(boundary.authenticate_inventory().get("generation", 0) >= 8,
            "current A2 inventory no longer extends immutable V8")
    from scripts import audit_core_01d_checkpoint_e_completion_v7 as completion_v7
    require(completion_v7.audit().get("result") == "PASS",
            "immutable Completion V7/B4 predecessor chain failed authentication")
    receipt = validate_receipt()
    return {"result": "PASS", "receipt_sha256": receipt["canonical_sha256"],
            "source_inventory_sha256": receipt["source_inventory"]["canonical_sha256"],
            "target_count": 4, "resolved_target_count": receipt["scope"]["resolved_target_count"],
            "partial_target_count": receipt["scope"]["partial_target_count"],
            "global_unresolved_before": 7, "global_unresolved_after": receipt["scope"]["global_unresolved_after"],
            "criterion_11": False, "criterion_14": False, "checkpoint_e": "INCOMPLETE", "p4_4": "INCOMPLETE",
            "mandatory_reread_after_merge": True, "do_not_start_b6_before_reread": True,
            "terminal": receipt["terminal"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-source-inventory", action="store_true")
    parser.add_argument("--write-receipt", action="store_true")
    args = parser.parse_args()
    if args.write_source_inventory:
        value = build_source_inventory()
        (ROOT / SOURCE_INVENTORY_PATH).write_bytes(boundary.canonical(value))
        print(value["canonical_sha256"])
    elif args.write_receipt:
        validate_source_inventory()
        value = build_receipt()
        (ROOT / RECEIPT_PATH).write_bytes(boundary.canonical(value))
        print(value["canonical_sha256"])
    else:
        print(json.dumps(audit(), sort_keys=True))


if __name__ == "__main__":
    main()
