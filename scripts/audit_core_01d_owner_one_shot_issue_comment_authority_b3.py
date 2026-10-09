"""Authenticate the bounded B3 review of four owner one-shot comment lanes.

The receipt is source-bound and uses only checked-in GitHub metadata snapshots.
This module performs no network access and never comments, dispatches, reruns,
downloads artifacts, or calls a provider.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import yaml

from scripts.audit_data_01c_restore_portability import historical_workflow_tree

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_checkpoint_e_completion_v5 as completion_v5

ROOT = Path(__file__).resolve().parents[1]
BASE_MAIN = "f127b97408011339282302009e4187d2281b0c9a"
BASE_TREE = "15b74e717a7d368c18e304a41ea41c17ceb0932d"
WORKFLOW_TREE = "9b08653f1a12bb1b3d964fbd910396ff955740da"
EVOLUTION_SHA = "73e1eb3fe6593558c821600dd0f103353d45c15a139ab470a996c7cbb35da531"
RETIREMENT_SHA = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
COMPLETION_V5_SHA = "5655dca85b67ec1a3367a7c5bfa08dfebda0caccb4830e75b23f6cca4ff82d88"
B2_RECEIPT_SHA = "df16f3684c5facf04728e4a8cc19d507c4ff553431c46228565126d31116fd9b"
B2_SOURCE_SHA = "b160118a461b4194bc224f4ce0e4adda3fb03f90d7f9874d8d275e4befe51b4d"
A2_V4_SHA = "82c440deb06d760d13bf73d914c5ec9181e568ba388f844a3fc6fa49976ab50f"
A2_V3_SHA = "f7646fd5008d12cc7c5b0379455c384742b893a26cac00fa55df19f28c8a8017"
COMPLETION_V4_SHA = "adb23d8ca4802c95298ddf90b7c07e75d2a8179bebe0592db309140871e1490c"
B1_RECEIPT_SHA = "bf38f7ef6bc43efa96ff36152b71308fafe5b21d581fd7921fc6f1ba2b4b06cc"
SOURCE_INVENTORY_PATH = "tests/fixtures/core_01d/owner-one-shot-issue-comment-authority-b3-source-inventory-v1.json"
RECEIPT_PATH = "tests/fixtures/core_01d/core-01d-owner-one-shot-issue-comment-authority-b3-v1.json"
COMPLETION_V5_PATH = "tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v5.json"
POLICY_ID = "ATHENA_CORE_01D_OWNER_ONE_SHOT_ISSUE_COMMENT_AUTHORITY_B3_V1"
SOURCE_INVENTORY_POLICY_ID = "ATHENA_CORE_01D_OWNER_ONE_SHOT_ISSUE_COMMENT_AUTHORITY_B3_SOURCE_INVENTORY_V1"
OBSERVED_AT = "2026-10-03T23:19:54Z"
POST_441_TESTS = {
    "run_id": 37159760270,
    "workflow": "Tests",
    "event": "push",
    "branch": "main",
    "head_sha": BASE_MAIN,
    "status": "completed",
    "conclusion": "success",
    "syntax": "success",
    "shards": {str(i): "success" for i in range(1, 9)},
    "aggregate": "success",
    "read_only": True,
    "source_url": "https://api.github.com/repos/Thabearr/ATHENA/actions/runs/37159760270",
    "observed_at_utc": OBSERVED_AT,
}

# Exact normalized source identities at the B3 base. The four workflow pins
# bind the complete YAML guard/callee graph; the remaining pins bind the
# source-bound runner, protocol, and immediate capability helpers relied on.
SOURCE_PINS: dict[str, tuple[str, str]] = {
    ".github/workflows/execute-fotmob-ordinary-ft-source-history-campaign.yml": ("817d07546891a1b38d6282bc06dc88186b13ca8e", "d2a288153c5438c61248107f0b6cac8123d4ab22b4f3f3236048d7a0a4e2ca91"),
    ".github/workflows/execute-fotmob-utc-native-successor-feature-qualification-v2.yml": ("f543e6c907e3b0b098152040730423eccfa52aad", "482553d648b049db81ff30f6d757d92f76d80f17301826a0c6a1c9b181b8e2f1"),
    ".github/workflows/execute-fotmob-utc-native-expected-goals-model-validation.yml": ("52958ce34e07179226c6d14c86daf7b2d229459b", "d1fcc4453d84875bbbe73e95bb1a769d3e27bdc3fec0cb93662ca114c25d9bf6"),
    ".github/workflows/execute-pr69-primary-time-basis-evidence-campaign-v2.yml": ("4e580f5bfd86de4f1ce003d9c327662fc3cdc490", "d4beeef1624bc435666cb51e590891c7e735d6ad7bd10259933d02bf50b4d262"),
    "domain/fotmob_ordinary_ft_source_history_acquisition_runner.py": ("533b339bcb2d6721dae55c699327b53eabbffb09", "fbe3b410feed5ee7f1a1c45b59ed525cad0738b387a16270fb6203a68f9cd9a4"),
    "scripts/run_fotmob_ordinary_ft_source_history_acquisition.py": ("6f067b8f069a760248a3b0b624c88d4f91aaa7ef", "68707cee683a2194b933c6e2a10a3f1f80699b1ccf40204f299c1501a586e40d"),
    "domain/fotmob_ordinary_ft_source_history_acquisition_protocol.py": ("39541b351d2990f7ebb9572a8c9c674c85864284", "77c79e75fa33af3788134c4f976df74b9955c9c3c97e1ece01658da74df2bf4b"),
    "scripts/capture_fotmob_data_matches.py": ("10b8858ab62f2708bd564d578a627c43718e5a12", "7364da10ff20f48aee24808bde115a9dbcfca7dc58c93b571b9e87b13cccce4f"),
    "domain/fotmob_data_matches_capture.py": ("ca2149395de868104666620173b55a880b10c729", "0b0ef80511fb58f18a6d872c01bb21a603fb8750795a60c6a67c3678d9b0dd37"),
    "domain/fotmob_data_matches_probe.py": ("c39bdea2ef65b26c3212471f6996831c4c845826", "fe33ec764d332a66d817fcf22834f4c7999d4ba7b0a323ac36d0652502c1c909"),
    "domain/source_capabilities.py": ("37b919eb5efa0c931e1bf10d3f845865567ef0c4", "ba25e1c1fbe30f5e6b8244318a824f3ac7ed9dbff6d3581ca159fb0649fdc411"),
    "domain/fotmob_utc_native_successor_feature_construction_qualification.py": ("9c9e424791b65292f7bbe8849b3214c140834889", "c9f0396dcd68ad75414b16fe06f678410afc2194c1feabb46483d61519301542"),
    "scripts/qualify_fotmob_utc_native_successor_feature_construction.py": ("68503c85569f31532a1a810249073c36242055e0", "a891444047fc27f63cdf309086fd1a69acec819a1cb114f4ada0f2a37c699d76"),
    "domain/fotmob_utc_native_successor_feature_construction_protocol.py": ("57cc133a7fb9daa76c5d5d8e9156903e583c6575", "d00f773631111bc2e03a49d3e7ecbe2cbd7095f458fb986e3d5dde47e7e31e32"),
    "scripts/qualify_fotmob_historical_source_history_completeness_materialization.py": ("2409676b4993a25024e2e8554e84e3525e7c5e6e", "b076433d0a6bf56894971af7e781f8bad7703ca1999591525c53478b2aee42dd"),
    "domain/fotmob_historical_source_history_completeness_materialization_protocol.py": ("be7119f06804093959b6730c2fe8ac05ea4d2f05", "46ac7ae4add5d5055fb9e7f46367b39300bfac3e3a322ebba9b758c45e1a3999"),
    "domain/fotmob_historical_source_history_adapter_qualification.py": ("15070ac7a0f2447ebea05665368c59e62edce2c4", "fa3742ee890f042c101d4f693b31572e9755c68a99dc4a592b0d5acdba6d9fa7"),
    "domain/fotmob_historical_source_history_adapter_protocol.py": ("53682e3810bf3c06b1afc90b847361b6dcb3e04f", "d3c0a2f042b1b90a8066abed9f9493313131b5d354a0efdc77151d5b20114320"),
    "domain/fotmob_source_history_adapter_completeness_assessment.py": ("15a120272c08a495c4a12d7321f8b4ff7ec6b2ec", "32045548a1bf01e2af4727a3b00b80c50d9c0862805bd27defecd4153b24e7e2"),
    "domain/fotmob_source_history_elo_initialization_boundary_qualification.py": ("c6129520c99218c470d1ac6fe68d40cca5ae8475", "d06a868cfb41ad1242a68df9e9c194eaf1761e2edd3cf02ebf91ad23f5be448f"),
    "domain/fotmob_source_history_rearrangement_chronology_qualification.py": ("2028c7e4d847ba293bc88ffc718a406853f96d11", "310f3a811004cb7d50c1b8585e527da5dc62bc271d5e845742b2a97c670b5727"),
    "domain/fotmob_source_history_special_result_semantics_qualification.py": ("ed3f2053ab9732e1e34e2e54f6f1e3531d01a4ca", "d6b18b8df8d24210635e459e6f865087af59abf320f5f0b17e040a48a8f28058"),
    "domain/fotmob_ordinary_ft_finished_score_source_history_completeness_protocol.py": ("3dd38f5f61c20c10900fa0bee9a30a69a58a3006", "40c78401808a1a0cdc6205c34db718cf5a775186a778ff9cb446b0526ab613e1"),
    "domain/fotmob_historical_source_history_completeness_materialization_qualification.py": ("f0d17dbcd70fc8b5432b50061525224642541c05", "07ea03634fb85b8ef41e09e2e08d7d448184bae81aff50d0f50311a3a1b83407"),
    "domain/prospective_successor_feature_construction_candidate.py": ("9135f056d036fd0207a3daead2599ac2520274be", "8f16f790d66c4c26a5f0cd63260ec2f6c2bda26b6c267f1a378fa3be2cc76192"),
    "domain/prospective_successor_source_history_completeness_protocol.py": ("6d9fc8a32d99cd4013836b2378f85b7dfe971d84", "1a6a4b89169bfdced1f083a930c3d0565616ac40a82293645497b0b1bd3b2ee8"),
    "domain/successor_live_input_semantic_qualification_execution.py": ("7a88fab5b01f4c58f29950b480a59c212d3ae956", "a40df31f5a02d44d1b1bc61b187a5e346ea920e0fa9b329cdfc28bcd57bbae23"),
    "domain/successor_live_input_semantic_qualification_protocol.py": ("cbd409fe42ffa8a3571f604e0817c06671db2a25", "146abba5f4c3c9ae3344962c1bffcaa3116331db660747991d2623a45ee0400c"),
    "domain/fotmob_utc_native_expected_goals_model_validation.py": ("0421506b9e6e398c3469bb69196ef8fcad04f2a5", "68675e28101999ade924441caea07c34206b1386b80c5080d99e85c22794ce88"),
    "domain/fotmob_utc_native_expected_goals_model_validation_source_bound.py": ("89cbe2e948c4f69339c89df00db0282e14b955e8", "f78cf3e53f23db404a9b5780fad7075662359f222e8eeb0fc04f432def3ea2ab"),
    "scripts/validate_fotmob_utc_native_expected_goals_model.py": ("d3dddecbd66b79887aef547abcd048f40a57e2a8", "29d284d41c39813ceb466d283f7444a39cc0a81509f3ac9c36ef4ef9c249852c"),
    "domain/fotmob_utc_native_expected_goals_model_validation_protocol.py": ("1780330c4d0ab9140f0b2f6c776dfe79073ca7f8", "e76b594fea183468f1a28c468e1d4780ec986e7d4c9c6807726c42d4467a0a09"),
    "domain/historical_expected_goals_successor_robustness_evaluator.py": ("28e33a625c02c7f005232d6c5d05d6a0a52397b7", "09d4cc48f7d9fd84a53a6eb276c4e2754ff1fb0e8a5695c310410dd4297664ab"),
    "domain/historical_expected_goals_component_validation.py": ("cc75af78cb6af4e3b7ebed5c3569384f2f809bf5", "46deb7ee1d784cb0d76658b4e1e765c88c20657fd9871bce2a0717b15f8012c7"),
    "domain/historical_expected_goals_successor_candidate.py": ("d1d22f44436775a8fd7fa6d4970d8d230d59ebef", "7cd586f27c9767f51a152e59aab6ce39c7bffe88489a614ba1f1758a0afbfb06"),
    "domain/historical_expected_goals_successor_protocol.py": ("f0b3a070bcf235a097dd737d715f9d6162505509", "00bf9075efee9f780d6a683b72e59a199fb87dd18fcee84cc225e6f107a73c85"),
    "domain/historical_expected_goals_successor_robustness_protocol.py": ("b9efdb831363293826fc97b5145839232d7ac53d", "9b457ff444a4d91a7aaa1084bd3cc3a01da993337a160fa891f4afba3bd85054"),
    "domain/historical_model_feature_replay_candidate.py": ("b67a7e52954f47cc90c578ad193545c541984964", "98e9bf64f44ed8db8f8bd46ebc1c9052762910afcd1b1fdbd3881253e487abcb"),
    "domain/fixture_model_features.py": ("e8d9ebf04676b54826b71752eae5aa5d23cb6caa", "60ed622fce70389b6e7fcf31b6db89dcd3b9680bf39213e506389c76488a29b1"),
    "domain/fotmob_reviewed_match_details_expected_goals_transform_candidate.py": ("3cb4b98c2545e0fb351a2c4ab31dd37f5c518922", "d12523a2b647d29be8b5d451c98510d48b5c766fde4735ee15289767830d39d8"),
    "domain/pr69_primary_time_basis_evidence_acquisition_runner.py": ("04c30b177c2338848a448972cc0cfad0328e602c", "7e6f57a64ee344d66a3104e635a02dbab06c526d763da866d5bca7fe2a9caec8"),
    "scripts/run_pr69_primary_time_basis_evidence_acquisition.py": ("b44a010d0957ad8d76474aae2f090d52ae5b0e6e", "7b6b4ff5d03588d11c3ff681420263d80cd4c3b0ed414b402438fc935ce29313"),
    "domain/pr69_primary_time_basis_evidence_acquisition_protocol.py": ("df1a25227b8fee5fbbb21dce7f5f8be5d2464954", "bad012d860668d3781638b845196cf5ced44f8a6aedf05e354d757f0613ed594"),
    "domain/pr69_source_local_time_basis_resolution_qualification.py": ("b5b8037264b8c5f57b9728f902f20de75067da6b", "b0dcbd405f69aaa343cf4134d6db83c5b7448aed132bf6e62cb193bcc5cb588a"),
}

TARGETS = {
    ".github/workflows/execute-fotmob-ordinary-ft-source-history-campaign.yml#issue_comment": {
        "path": ".github/workflows/execute-fotmob-ordinary-ft-source-history-campaign.yml", "pr": 103,
        "command": "/athena-run-fotmob-history", "confirmation": "EXECUTE_4410_LIVE_CAPTURES",
        "marker_prefix": "<!-- ATHENA_FOTMOB_HISTORY_EXECUTION_ATTEMPT_V1 -->", "command_id": 5302462991,
        "marker_id": 5302463691, "result_id": 5303209973, "run_id": 31887523012,
        "run_head": "12a32de1cca8ffb657f67fa4a8d3106aec6ce31b", "historical_mode": "FOTMOB_LIVE_4410_CAPTURE",
    },
    ".github/workflows/execute-fotmob-utc-native-successor-feature-qualification-v2.yml#issue_comment": {
        "path": ".github/workflows/execute-fotmob-utc-native-successor-feature-qualification-v2.yml", "pr": 139,
        "command": "/athena-run-fotmob-utc-native-feature-qualification-v2",
        "confirmation": "EXECUTE_RECONCILED_21326_UTC_NATIVE_FEATURE_QUALIFICATION_V2",
        "marker_prefix": "<!-- ATHENA_FOTMOB_UTC_NATIVE_FEATURE_QUALIFICATION_ATTEMPT_V2 -->",
        "command_id": 5311311034, "marker_id": 5311311868, "result_id": 5311318782,
        "run_id": 31990121181, "run_head": "cd67be14f6a4f09484d18a57de360b8a5d4c51d7",
        "reconciliation_id": 5311071999, "historical_mode": "EXACT_ACTIONS_ARTIFACT_OFFLINE_FEATURE_QUALIFICATION",
    },
    ".github/workflows/execute-fotmob-utc-native-expected-goals-model-validation.yml#issue_comment": {
        "path": ".github/workflows/execute-fotmob-utc-native-expected-goals-model-validation.yml", "pr": 145,
        "command": "/athena-run-fotmob-utc-native-expected-goals-validation",
        "confirmation": "EXECUTE_REVIEWED_21129_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION",
        "marker_prefix": "<!-- ATHENA_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_ATTEMPT -->",
        "command_id": 5318114406, "marker_id": 5318115383, "result_id": 5318117332,
        "run_id": 32049714066, "run_head": "b8ddc00f7529c5533c9da2daad613d997498cbf2",
        "failed_run_id": 32046244761, "failed_command_id": 5317747534,
        "failed_reconciliation_id": 5317758294, "upstream_result_id": 5311318782,
        "historical_mode": "EXACT_ACTIONS_ARTIFACT_OFFLINE_RESEARCH_MODEL_VALIDATION_TRAINING",
    },
    ".github/workflows/execute-pr69-primary-time-basis-evidence-campaign-v2.yml#issue_comment": {
        "path": ".github/workflows/execute-pr69-primary-time-basis-evidence-campaign-v2.yml", "pr": 130,
        "command": "/athena-run-pr69-time-basis-evidence-v2",
        "confirmation": "EXECUTE_RECONCILED_8_PRIMARY_TIME_BASIS_CAPTURES_V2",
        "marker_prefix": "<!-- ATHENA_PR69_PRIMARY_TIME_BASIS_EVIDENCE_EXECUTION_ATTEMPT_V2 -->",
        "command_id": 5309821666, "marker_id": 5309822325, "result_id": 5309859464,
        "run_id": 31974333489, "run_head": "4a2ca10af4b14194253ba6fc84bca780e2b03d58",
        "prior_result_id": 5308433895, "prior_run_id": 31953949073, "prior_artifact_id": 9266604353,
        "fix_pr": 129, "fix_merge_sha": "94577458d4b8af59a4e986edb2e4df9c426e21be",
        "historical_mode": "FOOTBALL_DATA_LIVE_EIGHT_SLOT_EVIDENCE_CAMPAIGN",
    },
}

CALLEES_BY_PR = {
    103: (
        "domain/fotmob_ordinary_ft_source_history_acquisition_runner.py",
        "scripts/run_fotmob_ordinary_ft_source_history_acquisition.py",
        "domain/fotmob_ordinary_ft_source_history_acquisition_protocol.py",
        "scripts/capture_fotmob_data_matches.py",
        "domain/fotmob_data_matches_capture.py",
        "domain/fotmob_data_matches_probe.py",
        "domain/source_capabilities.py",
    ),
    139: (
        "domain/fotmob_utc_native_successor_feature_construction_qualification.py",
        "scripts/qualify_fotmob_utc_native_successor_feature_construction.py",
        "domain/fotmob_utc_native_successor_feature_construction_protocol.py",
        "scripts/qualify_fotmob_historical_source_history_completeness_materialization.py",
        "domain/fotmob_historical_source_history_completeness_materialization_protocol.py",
        "domain/fotmob_historical_source_history_adapter_qualification.py",
        "domain/fotmob_historical_source_history_adapter_protocol.py",
        "domain/fotmob_source_history_adapter_completeness_assessment.py",
        "domain/fotmob_source_history_elo_initialization_boundary_qualification.py",
        "domain/fotmob_source_history_rearrangement_chronology_qualification.py",
        "domain/fotmob_source_history_special_result_semantics_qualification.py",
        "domain/fotmob_ordinary_ft_finished_score_source_history_completeness_protocol.py",
        "domain/fotmob_historical_source_history_completeness_materialization_qualification.py",
        "domain/prospective_successor_feature_construction_candidate.py",
        "domain/prospective_successor_source_history_completeness_protocol.py",
        "domain/successor_live_input_semantic_qualification_execution.py",
        "domain/successor_live_input_semantic_qualification_protocol.py",
    ),
    145: (
        "domain/fotmob_utc_native_expected_goals_model_validation.py",
        "domain/fotmob_utc_native_expected_goals_model_validation_source_bound.py",
        "scripts/validate_fotmob_utc_native_expected_goals_model.py",
        "domain/fotmob_utc_native_expected_goals_model_validation_protocol.py",
        "domain/historical_expected_goals_successor_robustness_evaluator.py",
        "domain/historical_expected_goals_component_validation.py",
        "domain/historical_expected_goals_successor_candidate.py",
        "domain/historical_expected_goals_successor_protocol.py",
        "domain/historical_expected_goals_successor_robustness_protocol.py",
        "domain/historical_model_feature_replay_candidate.py",
        "domain/fixture_model_features.py",
        "domain/fotmob_reviewed_match_details_expected_goals_transform_candidate.py",
    ),
    130: (
        "domain/pr69_primary_time_basis_evidence_acquisition_runner.py",
        "scripts/run_pr69_primary_time_basis_evidence_acquisition.py",
        "domain/pr69_primary_time_basis_evidence_acquisition_protocol.py",
        "domain/pr69_source_local_time_basis_resolution_qualification.py",
    ),
}

# Exact read-only GitHub state collected 2026-10-03. Bodies are retained because
# these exact comments are workflow guard inputs, not because comments are
# immutable. The auditor rejects any change to the observed body/identity.
COMMENTS = {
    5302462991: ("Thabearr", "2026-08-15T13:33:20Z", "/athena-run-fotmob-history\nmain-sha: 12a32de1cca8ffb657f67fa4a8d3106aec6ce31b\nconfirm: EXECUTE_4410_LIVE_CAPTURES"),
    5302463691: ("github-actions[bot]", "2026-08-15T13:33:31Z", "<!-- ATHENA_FOTMOB_HISTORY_EXECUTION_ATTEMPT_V1 -->\nATHENA reviewed FotMob source-history campaign execution attempt started.\nrun-id: 31887523012\nmain-sha: 12a32de1cca8ffb657f67fa4a8d3106aec6ce31b\ncommand-comment-id: 5302462991\nstate: ATTEMPT_STARTED_NO_RESULT_YET\nAutomatic replay is forbidden if this run does not complete cleanly."),
    5303209973: ("github-actions[bot]", "2026-08-15T16:41:32Z", "<!-- ATHENA_FOTMOB_HISTORY_EXECUTION_RESULT_V1 -->\nATHENA reviewed FotMob source-history campaign execution result.\nrun-id: 31887523012\nmain-sha: 12a32de1cca8ffb657f67fa4a8d3106aec6ce31b\nrunner-exit-code: 0\nstatus-exit-code: 0\npackage-outcome: success\nartifact-upload-outcome: success\nverification-outcome: success\nstate: EXECUTION_COMPLETED_4410_SLOTS_EVIDENCE_ARTIFACT_PRESERVED\nartifact-name: fotmob-ordinary-ft-source-history-campaign-31887523012\nThis workflow does not itself claim historical completeness or downstream authority."),
    5311311034: ("Thabearr", "2026-08-17T03:07:26Z", "/athena-run-fotmob-utc-native-feature-qualification-v2\nmain-sha: cd67be14f6a4f09484d18a57de360b8a5d4c51d7\nconfirm: EXECUTE_RECONCILED_21326_UTC_NATIVE_FEATURE_QUALIFICATION_V2"),
    5311311868: ("github-actions[bot]", "2026-08-17T03:07:36Z", "<!-- ATHENA_FOTMOB_UTC_NATIVE_FEATURE_QUALIFICATION_ATTEMPT_V2 -->\nATHENA reconciled FotMob UTC-native feature qualification V2 attempt started.\nrun-id: 31990121181\nmain-sha: cd67be14f6a4f09484d18a57de360b8a5d4c51d7\ncommand-comment-id: 5311311034\nv1-reconciliation-comment-id: 5311071999\nstate: ATTEMPT_STARTED_NO_RESULT_YET\nAutomatic replay is forbidden if this V2 run does not complete cleanly."),
    5311318782: ("github-actions[bot]", "2026-08-17T03:08:54Z", "<!-- ATHENA_FOTMOB_UTC_NATIVE_FEATURE_QUALIFICATION_RESULT_V2 -->\nATHENA reconciled FotMob UTC-native feature qualification V2 execution result.\nrun-id: 31990121181\nmain-sha: cd67be14f6a4f09484d18a57de360b8a5d4c51d7\nrunner-exit-code: 0\nartifact-download-outcome: success\npackage-outcome: success\nartifact-upload-outcome: success\nverification-outcome: success\nstate: EXECUTION_COMPLETED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION_EVIDENCE_PRESERVED_V2\nartifact-name: fotmob-utc-native-feature-qualification-v2-31990121181\nFeature qualification evidence only. No model, pricing, selection, production, or BET authority is granted."),
    5311071999: ("Thabearr", "2026-08-17T02:24:55Z", "<!-- ATHENA_FOTMOB_UTC_NATIVE_FEATURE_QUALIFICATION_V1_RECONCILIATION -->\nATHENA UTC-native feature qualification V1 execution reconciliation.\nrun-id: 31987862156\nmain-sha: 2bd05e98cd74f9db6fa59472c05d5253f69d0f68\ncommand-comment-id: 5311067273\nfailure-stage: VALIDATE_ONE_SHOT_OWNER_COMMAND_AND_CURRENT_MAIN_MARKER_WRITE\nfailure: GitHub issue-comment creation returned 403 Resource not accessible by integration\nrunner-executed: false\nartifact-download-executed: false\nqualification-receipt-produced: false\nfeature-projection-produced: false\nfailure-evidence-artifact-id: 9274313978\nfailure-evidence-artifact-name: fotmob-utc-native-feature-qualification-31987862156\nfailure-evidence-artifact-sha256: 1a46808c8ee4d21ab67ec03b1fd6c0a80e79fadf04933092e7a106522e31c337\nfailure-evidence-artifact-size: 2388\nstate: V1_SPENT_GUARD_PERMISSION_FAILURE_NO_QUALIFICATION_EXECUTED_DO_NOT_REPLAY\nNo model, probability, pricing, selection, production, or BET authority is granted. A new reviewed V2 execution boundary is required before another attempt."),
    5318114406: ("Thabearr", "2026-08-17T17:18:05Z", "/athena-run-fotmob-utc-native-expected-goals-validation\nmain-sha: b8ddc00f7529c5533c9da2daad613d997498cbf2\nconfirm: EXECUTE_REVIEWED_21129_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION"),
    5318115383: ("github-actions[bot]", "2026-08-17T17:18:14Z", "<!-- ATHENA_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_ATTEMPT -->\nATHENA reviewed FotMob UTC-native expected-goals model-validation attempt started.\nrun-id: 32049714066\nmain-sha: b8ddc00f7529c5533c9da2daad613d997498cbf2\ncommand-comment-id: 5318114406\nupstream-v2-result-comment-id: 5311318782\nstate: ATTEMPT_STARTED_NO_RESULT_YET\nAutomatic replay is forbidden if this run does not complete cleanly."),
    5318117332: ("github-actions[bot]", "2026-08-17T17:18:31Z", "<!-- ATHENA_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_RESULT -->\nATHENA reviewed FotMob UTC-native expected-goals model-validation execution result.\nrun-id: 32049714066\nmain-sha: b8ddc00f7529c5533c9da2daad613d997498cbf2\nrunner-exit-code: 0\nartifact-download-outcome: success\npackage-outcome: success\nartifact-upload-outcome: success\nverification-outcome: success\nstate: EXECUTION_COMPLETED_REVIEWED_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_EVIDENCE_PRESERVED\nartifact-name: fotmob-utc-native-expected-goals-validation-32049714066\nResearch model-validation evidence only. Result review is required.\nNo ScoreMatrix, probability, pricing, selection, production, or BET authority is granted."),
    5317747534: ("Thabearr", "2026-08-17T16:34:38Z", "/athena-run-fotmob-utc-native-expected-goals-validation\nmain-sha: 21bff3fe96e8c9b250c9776240ba7bede9f74c89\nconfirm: EXECUTE_REVIEWED_21129_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION"),
    5317758294: ("Thabearr", "2026-08-17T16:35:48Z", "<!-- ATHENA_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_FAILED_PRE_ATTEMPT_RECONCILIATION -->\nATHENA UTC-native expected-goals validation execution command reached the control workflow but failed before the durable attempt marker could be created.\nrun-id: 32046244761\nmain-sha: 21bff3fe96e8c9b250c9776240ba7bede9f74c89\ncommand-comment-id: 5317747534\nattempt-marker-created: false\ncheckout-executed: false\nsource-artifact-download-executed: false\nvalidator-executed: false\nresearch-training-executed: false\nfailure-step: Validate one-shot owner command and current main\nfailure: GitHub API POST /issues/145/comments returned 403 Resource not accessible by integration because the closed-PR receipt path requires pull_requests=write.\nfailure-artifact-id: 9292984849\nfailure-artifact-name: fotmob-utc-native-expected-goals-validation-32046244761\nfailure-artifact-size-bytes: 2448\nfailure-artifact-sha256: 91965dee1fdb496e776a914de9a9e789a830141ea6b17276a7b1bade541835c1\nstate: FAILED_BEFORE_DURABLE_ATTEMPT_MARKER_NO_MODEL_VALIDATION_EXECUTED\nAutomatic replay of run 32046244761 is forbidden. A reviewed control-plane correction and a new explicit execution command are required before another attempt."),
    5309821666: ("Thabearr", "2026-08-16T21:43:19Z", "/athena-run-pr69-time-basis-evidence-v2\nmain-sha: 4a2ca10af4b14194253ba6fc84bca780e2b03d58\nconfirm: EXECUTE_RECONCILED_8_PRIMARY_TIME_BASIS_CAPTURES_V2"),
    5309822325: ("github-actions[bot]", "2026-08-16T21:43:28Z", "<!-- ATHENA_PR69_PRIMARY_TIME_BASIS_EVIDENCE_EXECUTION_ATTEMPT_V2 -->\nATHENA reconciled PR69 primary time-basis evidence campaign V2 attempt started.\nrun-id: 31974333489\nmain-sha: 4a2ca10af4b14194253ba6fc84bca780e2b03d58\ncommand-comment-id: 5309821666\nreconciled-from-run-id: 31953949073\nreconciled-artifact-id: 9266604353\nreconciled-artifact-digest: ce87f13cb72a917c0a01e4bbede87e4123d85861d5ee1cd98667bb802d380db7\nfix-pr: 129\nfix-merge-sha: 94577458d4b8af59a4e986edb2e4df9c426e21be\nstate: ATTEMPT_STARTED_NO_RESULT_YET\nAutomatic replay is forbidden if this V2 run does not complete cleanly."),
    5309859464: ("github-actions[bot]", "2026-08-16T21:53:11Z", "<!-- ATHENA_PR69_PRIMARY_TIME_BASIS_EVIDENCE_EXECUTION_RESULT_V2 -->\nATHENA reconciled PR69 primary time-basis evidence campaign V2 result.\nrun-id: 31974333489\nmain-sha: 4a2ca10af4b14194253ba6fc84bca780e2b03d58\nstate: PRIMARY_EVIDENCE_CAMPAIGN_V2_EXECUTED_AND_PRESERVED_PENDING_SEMANTIC_QUALIFICATION\ncampaign-exit-code: 0\npost-status-exit-code: 0\npackage-outcome: success\nassessment-outcome: success\nassessment-valid: true\nartifact-upload-outcome: success\nartifact-id: 9270750452\nartifact-digest: 186188a0cec4e3febc8971c0f69eb1feb7dec6d2f35052ce48d2913c37265a6c\nartifact-url: https://github.com/Thabearr/ATHENA/actions/runs/31974333489/artifacts/9270750452\nreconciled-from-run-id: 31953949073\nreconciled-artifact-id: 9266604353\nfix-pr: 129\nfix-merge-sha: 94577458d4b8af59a4e986edb2e4df9c426e21be\nsemantic-extraction: false\nhistorical-effective-scope-qualification: false\npr69-source-local-time-basis-resolution: false\npr80-constructor-input: false\nmodel/probability/pricing/selection/production/BET authority: false\nNo semantic conclusion is authorized by successful acquisition alone."),
    5308433895: ("github-actions[bot]", "2026-08-16T16:24:57Z", "<!-- ATHENA_PR69_PRIMARY_TIME_BASIS_EVIDENCE_EXECUTION_RESULT_V1 -->\nATHENA reviewed PR69 primary time-basis evidence campaign execution result.\nrun-id: 31953949073\nmain-sha: 0efe56f5003441b52e4ec3ba2723eb0d78a80422\nstate: EXECUTION_NOT_QUALIFIED_REVIEW_ARTIFACT_BEFORE_ANY_RETRY\ncampaign-exit-code: 1\npost-status-exit-code: 0\npackage-outcome: success\nartifact-upload-outcome: success\nartifact-id: 9266604353\nartifact-digest: ce87f13cb72a917c0a01e4bbede87e4123d85861d5ee1cd98667bb802d380db7\nartifact-url: https://github.com/Thabearr/ATHENA/actions/runs/31953949073/artifacts/9266604353\nsemantic-extraction: false\nhistorical-effective-scope-qualification: false\npr69-source-local-time-basis-resolution: false\npr80-constructor-input: false\nmodel/probability/pricing/selection/production/BET authority: false\nAutomatic replay is forbidden. Review the preserved artifact and reconcile this attempt before any retry."),
}

CONTROL_PRS = {
    103: {"title": "Add controlled execution lane for reviewed FotMob source-history campaign", "state": "closed", "merged": True, "merged_at": "2026-08-15T11:54:18Z", "closed_at": "2026-08-15T11:54:18Z", "base_branch": "main", "head_branch": "feature/fotmob-ordinary-ft-source-history-campaign-execution-lane", "head_sha": "9d60a5a74e6313f4f28841aeafb9174c732f4e73", "same_repository": True, "conversation_locked": False},
    128: {"title": "Add controlled PR69 primary evidence campaign execution lane", "state": "closed", "merged": True, "merged_at": "2026-08-16T14:37:12Z", "closed_at": "2026-08-16T14:37:12Z", "base_branch": "main", "head_branch": "feature/pr69-primary-evidence-campaign-execution-lane", "head_sha": "a365bd741972ebfc295ed851a891b7cd1f55322a", "same_repository": True},
    129: {"title": "[PR69] Bound primary evidence upstream verification overhead", "state": "closed", "merged": True, "merged_at": "2026-08-16T20:59:36Z", "closed_at": "2026-08-16T20:59:36Z", "base_branch": "main", "head_branch": "feature/pr69-primary-time-basis-verification-session", "head_sha": "cf4bb6a1008bb0b91d60c6b319a22eebdf902e53", "merge_sha": "94577458d4b8af59a4e986edb2e4df9c426e21be", "same_repository": True},
    138: {"title": "[FotMob][Research] Add one-shot UTC-native feature qualification execution boundary", "state": "closed", "merged": True, "merged_at": "2026-08-17T02:21:50Z", "closed_at": "2026-08-17T02:21:50Z", "base_branch": "main", "head_branch": "research/fotmob-utc-native-feature-qualification-execution", "head_sha": "a4e02da346f0c5ee81f849a91b942abd44857c87", "same_repository": True},
    139: {"title": "[FotMob][Research] Reconcile UTC-native feature qualification execution V2", "state": "closed", "merged": True, "merged_at": "2026-08-17T02:43:37Z", "closed_at": "2026-08-17T02:43:37Z", "base_branch": "main", "head_branch": "research/fotmob-utc-native-feature-qualification-execution-v2", "head_sha": "11f624caeb9a583b79c2835f53d807f98f4a127c", "same_repository": True, "conversation_locked": False},
    145: {"title": "[FotMob][Research] Control UTC-native expected-goals model validation execution", "state": "closed", "merged": True, "merged_at": "2026-08-17T16:20:29Z", "closed_at": "2026-08-17T16:20:29Z", "base_branch": "main", "head_branch": "research/fotmob-utc-native-expected-goals-model-validation-execution", "head_sha": "56416d73daa62850a409dc9a9f12dc01927abe77", "same_repository": True, "conversation_locked": False},
    130: {"title": "[PR69] Add reconciled primary evidence campaign V2 execution lane", "state": "closed", "merged": True, "merged_at": "2026-08-16T21:22:55Z", "closed_at": "2026-08-16T21:22:55Z", "base_branch": "main", "head_branch": "feature/pr69-primary-time-basis-reconciled-execution-v2", "head_sha": "ea1ac84517d39c5e9523123ba6159ee7afa23d46", "same_repository": True, "conversation_locked": False},
}

RUNS = {
    31887523012: {"workflow_path": ".github/workflows/execute-fotmob-ordinary-ft-source-history-campaign.yml", "event": "issue_comment", "head_sha": "12a32de1cca8ffb657f67fa4a8d3106aec6ce31b", "status": "completed", "conclusion": "success", "run_attempt": 1, "created_at": "2026-08-15T13:33:23Z"},
    31990121181: {"workflow_path": ".github/workflows/execute-fotmob-utc-native-successor-feature-qualification-v2.yml", "event": "issue_comment", "head_sha": "cd67be14f6a4f09484d18a57de360b8a5d4c51d7", "status": "completed", "conclusion": "success", "run_attempt": 1, "created_at": "2026-08-17T03:07:29Z"},
    32049714066: {"workflow_path": ".github/workflows/execute-fotmob-utc-native-expected-goals-model-validation.yml", "event": "issue_comment", "head_sha": "b8ddc00f7529c5533c9da2daad613d997498cbf2", "status": "completed", "conclusion": "success", "run_attempt": 1, "created_at": "2026-08-17T17:18:08Z"},
    32046244761: {"workflow_path": ".github/workflows/execute-fotmob-utc-native-expected-goals-model-validation.yml", "event": "issue_comment", "head_sha": "21bff3fe96e8c9b250c9776240ba7bede9f74c89", "status": "completed", "conclusion": "failure", "run_attempt": 1, "created_at": "2026-08-17T16:34:45Z"},
    31974333489: {"workflow_path": ".github/workflows/execute-pr69-primary-time-basis-evidence-campaign-v2.yml", "event": "issue_comment", "head_sha": "4a2ca10af4b14194253ba6fc84bca780e2b03d58", "status": "completed", "conclusion": "success", "run_attempt": 1, "created_at": "2026-08-16T21:43:22Z"},
    31953949073: {"workflow_path": ".github/workflows/execute-pr69-primary-time-basis-evidence-campaign.yml", "event": "issue_comment", "head_sha": "0efe56f5003441b52e4ec3ba2723eb0d78a80422", "status": "completed", "conclusion": "cancelled", "run_attempt": 1, "created_at": "2026-08-16T14:51:53Z"},
    31987862156: {"workflow_path": ".github/workflows/execute-fotmob-utc-native-successor-feature-qualification.yml", "event": "issue_comment", "head_sha": "2bd05e98cd74f9db6fa59472c05d5253f69d0f68", "status": "completed", "conclusion": "failure", "run_attempt": 1, "created_at": "2026-08-17T02:24:03Z"},
}

RECON_COMMENT_IDS = {
    139: [5311071999],
    145: [5311318782, 5317758294],
    130: [5308433895],
}

ZERO_ACTIONS = {
    "execution_command_comments": 0, "provider_or_public_source_calls": 0,
    "artifact_payload_downloads": 0, "workflow_dispatch": 0,
    "workflow_rerun": 0, "workflow_cancel": 0, "historical_comment_mutations": 0,
    "historical_pr_reopen_or_close": 0, "branch_writes": 0, "release_mutations": 0,
    "drive_or_external_storage_writes": 0, "email_or_smtp": 0,
    "share_code_or_login_or_cookie": 0, "wallet_or_stake_or_wager": 0,
    "retirement_or_deletion": 0,
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def verify_workflow_ledgers() -> None:
    workflow_tree = historical_workflow_tree(subprocess.check_output(["git", "rev-parse", "HEAD:.github/workflows"], cwd=ROOT).decode().strip())
    require(workflow_tree == WORKFLOW_TREE, "workflow tree identity drift")
    evolution = boundary.read("artifacts/architecture/p4_workflow_evolution_ledger_v1.json")
    require(evolution["canonical_sha256"] == EVOLUTION_SHA and len(evolution["transitions"]) == 14,
            "workflow evolution ledger identity/count drift")
    require(evolution["current_workflow_tree_sha1"] == WORKFLOW_TREE and evolution["current_live_workflow_count"] == 39,
            "workflow evolution current census drift")
    retirement = boundary.read("artifacts/architecture/p4_3_workflow_retirement_ledger_v1.json")
    require(retirement["canonical_sha256"] == RETIREMENT_SHA and retirement["current_retired_workflow_count"] == 3,
            "workflow retirement ledger identity/count drift")
    require(not subprocess.check_output(["git", "diff", "--name-only", "HEAD", "--", ".github/workflows"], cwd=ROOT).strip(),
            "B3 changed a workflow source")


def source_identity(path: str) -> dict[str, str]:
    raw = (ROOT / path).read_bytes()
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    expected_blob, expected_sha = SOURCE_PINS[path]
    git_blob = subprocess.check_output(
        ["git", "rev-parse", "HEAD:" + path], cwd=ROOT).decode().strip()
    require(git_blob == expected_blob, "B3 pinned Git blob identity drift: " + path)
    digest = hashlib.sha256(normalized).hexdigest()
    require(digest == expected_sha, "B3 pinned normalized source identity drift: " + path)
    return {"path": path, "git_blob_sha1": git_blob, "normalized_source_sha256": digest}


def authenticate_predecessor_chain() -> dict[str, object]:
    """Authenticate immutable predecessor documents without treating their old
    A2 V4 head as the current Python corpus after append-only V5 supersedes it.
    """
    completion = boundary.read(COMPLETION_V5_PATH)
    require(completion["canonical_sha256"] == COMPLETION_V5_SHA,
            "immutable Completion V5 identity drift")
    require(completion["scope"]["remaining_global_unreviewed_surface_count"] == 20
            and len(completion["unreviewed_authority_surfaces"]) == 20,
            "immutable Completion V5 unresolved surface census drift")
    require(completion["checkpoint_e_status"] == completion["p4_4_status"] == "INCOMPLETE",
            "immutable Completion V5 must remain incomplete")
    require(completion["checkpoint_criteria"]["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False
            and completion["checkpoint_criteria"]["no_unknown_current_artifact_or_notification_authority"] is False,
            "immutable Completion V5 global criteria drift")
    b2_receipt = boundary.read("tests/fixtures/core_01d/core-01d-historical-warehouse-transfer-authority-b2-v1.json")
    require(b2_receipt["canonical_sha256"] == B2_RECEIPT_SHA,
            "immutable B2 receipt identity drift")
    b2_inventory = boundary.read("tests/fixtures/core_01d/historical-warehouse-transfer-authority-b2-source-inventory-v1.json")
    require(b2_inventory["canonical_sha256"] == B2_SOURCE_SHA,
            "immutable B2 source inventory identity drift")
    completion_v4 = boundary.read("tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v4.json")
    require(completion_v4["canonical_sha256"] == COMPLETION_V4_SHA,
            "immutable Completion V4 identity drift")
    b1 = boundary.read("tests/fixtures/core_01d/core-01d-exact-pr-trigger-disposition-b1-v1.json")
    require(b1["canonical_sha256"] == B1_RECEIPT_SHA,
            "immutable B1 receipt identity drift")
    a2_v4 = boundary.read("tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v4.json")
    require(a2_v4["canonical_sha256"] == A2_V4_SHA,
            "immutable A2 generation V4 identity drift")
    require(completion["predecessor_completion_v4"]["canonical_sha256"] == COMPLETION_V4_SHA
            and completion["b2_review"]["canonical_sha256"] == B2_RECEIPT_SHA
            and completion["b2_source_inventory"]["canonical_sha256"] == B2_SOURCE_SHA,
            "Completion V5 predecessor bindings drift")
    return completion


def comment_snapshot(comment_id: int) -> dict[str, object]:
    author, timestamp, body = COMMENTS[comment_id]
    return {
        "comment_id": comment_id,
        "author_login": author,
        "created_at": timestamp,
        "updated_at": timestamp,
        "body": body,
        "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
        "current_presence": "PRESENT_READ_ONLY_OBSERVATION",
        "source_url": f"https://api.github.com/repos/Thabearr/ATHENA/issues/comments/{comment_id}",
        "read_only": True,
        "edit_or_deletion_impossible_proven": False,
    }


def workflow_value(path: str) -> dict[str, object]:
    value = yaml.load((ROOT / path).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    require(isinstance(value, dict), "workflow YAML root is not a mapping: " + path)
    return value


def step_contracts(job: dict[str, object]) -> list[dict[str, object]]:
    rows = []
    for index, step in enumerate(job.get("steps", []), 1):
        run = step.get("run")
        compact = " ".join(str(run).split()) if run is not None else ""
        rows.append({
            "ordinal": index,
            "name": step.get("name"),
            "uses": step.get("uses"),
            "if": step.get("if"),
            "shell": step.get("shell"),
            "run_sha256": hashlib.sha256(compact.encode()).hexdigest() if compact else None,
            "run_references": sorted(set(re.findall(
                r"(?:python(?:\s+-m)?|bash|sh)\s+(scripts/[A-Za-z0-9_./-]+\.py)", compact))),
            "with": step.get("with", {}),
            "env": step.get("env", {}),
        })
    return rows


def trigger_contract(target_key: str) -> dict[str, object]:
    target = TARGETS[target_key]
    control_pr = CONTROL_PRS[target["pr"]]
    require(control_pr["state"] == "closed" and control_pr["merged"] is True,
            "live control PR state does not satisfy the observed merged/closed source condition")
    require(control_pr.get("conversation_locked") is False,
            "live PR conversation lock state does not prove owner comments remain physically reachable")
    workflow = workflow_value(target["path"])
    events = workflow.get("on", {})
    require(isinstance(events, dict) and "issue_comment" in events, "issue_comment trigger missing")
    event = events["issue_comment"]
    require(event.get("types") == ["created"], "issue_comment type drift")
    job = workflow["jobs"]["execute"]
    all_triggers = workflow.get("on", {})
    guard = str(job.get("if", ""))
    for required in (
        "github.event.issue.pull_request",
        f"github.event.issue.number == {target['pr']}",
        "github.event.comment.user.login == 'Thabearr'",
        f"startsWith(github.event.comment.body, '{target['command']}')",
    ):
        require(required in guard, "one-shot event/job guard changed: " + required)
    raw = (ROOT / target["path"]).read_text(encoding="utf-8")
    require(target["marker_prefix"] in raw, "attempt marker prefix no longer occurs in source")
    require("lines.length !== 3" in raw and "/^main-sha: ([0-9a-f]{40})$/" in raw,
            "exact 3-line lowercase main SHA command contract drift")
    require(target["confirmation"] in raw, "confirmation token drift")
    require("${{ secrets." not in raw, "B3 source acquired a secrets.* binding")
    return {
        "event": "issue_comment", "types": event.get("types"),
        "declared_trigger_kinds_in_same_file": sorted(all_triggers),
        "job": "execute", "job_if": guard, "control_pr_number": target["pr"],
        "owner_login": "Thabearr", "command_prefix": target["command"],
        "exact_body_framing": "THREE_NONEMPTY_TRIMMED_LINES_COMMAND_MAIN_SHA_CONFIRM",
        "main_sha_rule": "EXACT_LOWERCASE_40_HEX_AND_EQUALS_CURRENT_DEFAULT_BRANCH_REF",
        "confirmation_token": target["confirmation"],
        "concurrency": workflow.get("concurrency", {}),
        "workflow_permissions": workflow.get("permissions", {}),
        "job_permissions": job.get("permissions", {}),
        "job_steps": step_contracts(job),
        "timeout_minutes": job.get("timeout-minutes"),
        "secret_bindings": sorted({line.strip() for line in raw.splitlines() if "${{ secrets." in line}),
        "explicit_github_token_expression_bindings": sorted({line.strip() for line in raw.splitlines() if "${{ github.token }}" in line}),
        "credential_surface": ("GITHUB_SCRIPT_TOKEN_SCOPED_BY_DECLARED_PERMISSIONS; NO secrets.* BINDINGS"
                               if "${{ github.token }}" not in raw else
                               "GITHUB_SCRIPT_TOKEN_SCOPED_BY_DECLARED_PERMISSIONS; GH_TOKEN_EXPLICIT_ON_EXACT_ARTIFACT_READ_STEP; NO secrets.* BINDINGS"),
        "trigger_surface_reachability": "PHYSICALLY_REACHABLE_OWNER_COMMENT_EVENT_ON_MERGED_PR",
        "live_control_pr_state": control_pr["state"],
        "live_control_pr_merged": control_pr["merged"],
        "live_control_pr_conversation_locked": control_pr["conversation_locked"],
    }


def source_order(path: str, markers: list[tuple[str, str]]) -> list[dict[str, object]]:
    raw = (ROOT / path).read_text(encoding="utf-8")
    offsets = []
    for label, token in markers:
        pos = raw.find(token)
        require(pos >= 0, "guard-order source token missing: " + label)
        offsets.append((pos, label, token))
    require([pos for pos, _, _ in offsets] == sorted(pos for pos, _, _ in offsets),
            "source-derived guard order drift")
    return [{"ordinal": i + 1, "operation": label, "line": raw.count("\n", 0, pos) + 1,
             "source_token": token} for i, (pos, label, token) in enumerate(offsets)]


GUARD_MARKERS = {
    103: [
        ("current control PR metadata read", "github.rest.pulls.get({"),
        ("current repository and default ref reads", "github.rest.git.getRef({"),
        ("existing marker comments read and checked", "const priorMarker = comments.find("),
        ("new attempt marker comment write", "const marker = await github.rest.issues.createComment({"),
        ("exact main checkout", "- name: Check out exact authorized main"),
        ("FotMob live acquisition boundary", "--execute-live-network"),
    ],
    139: [
        ("current control/repository/default-ref metadata reads", "github.rest.git.getRef({"),
        ("required V1 reconciliation comment read", "const reconciliation = v1Comments.find("),
        ("existing V2 marker comments read and checked", "const priorMarker = comments.find("),
        ("new attempt marker comment write", "const marker = await github.rest.issues.createComment({"),
        ("exact main checkout", "- name: Check out exact authorized main"),
        ("source artifact metadata read", "github.rest.actions.getArtifact({"),
        ("exact artifact payload download", "- name: Download and verify exact preserved artifact archive"),
        ("offline feature qualification", "python scripts/qualify_fotmob_utc_native_successor_feature_construction.py"),
    ],
    145: [
        ("current control/repository/default-ref metadata reads", "github.rest.git.getRef({"),
        ("successful upstream V2 result read", "const upstream = upstreamComments.find("),
        ("failed pre-attempt reconciliation read", "const reconciliation = comments.find("),
        ("existing expected-goals marker read and checked", "const priorMarker = comments.find("),
        ("new attempt marker comment write", "const marker = await github.rest.issues.createComment({"),
        ("exact main checkout", "- name: Check out exact authorized main"),
        ("historical source artifact metadata read", "github.rest.actions.getArtifact({"),
        ("exact source artifact payload download", "- name: Download and verify exact preserved V2 artifact archive"),
        ("research model-validation/training boundary", "python -m scripts.validate_fotmob_utc_native_expected_goals_model"),
    ],
    130: [
        ("control and exact fix PR metadata reads", "github.rest.pulls.get({"),
        ("prior V1 result comment read", "const priorResult = priorComments.find("),
        ("prior V1 Actions artifact metadata read before current marker", "github.rest.actions.getArtifact({"),
        ("current V2 marker comments read and checked", "const priorMarker = comments.find("),
        ("new attempt marker comment write", "const marker = await github.rest.issues.createComment({"),
        ("exact main checkout", "- name: Check out exact authorized main"),
        ("football-data.co.uk live acquisition boundary", "--execute-reviewed-protocol"),
    ],
}


def run_evidence(run_id: int) -> dict[str, object]:
    value = dict(RUNS[run_id])
    value.update({"run_id": run_id, "run_attempt": RUNS[run_id]["run_attempt"],
                  "source_url": f"https://api.github.com/repos/Thabearr/ATHENA/actions/runs/{run_id}",
                  "read_only": True, "payload_downloaded": False})
    return value


def build_source_inventory() -> dict[str, object]:
    boundary.authenticate_predecessors()
    verify_workflow_ledgers()
    authenticate_predecessor_chain()
    identities = [source_identity(path) for path in sorted(SOURCE_PINS)]
    target_rows = []
    for key, target in TARGETS.items():
        workflow_identity = next(row for row in identities if row["path"] == target["path"])
        target_rows.append({
            "surface_key": key,
            "source_identity": workflow_identity,
            "trigger_contract": trigger_contract(key),
            "guard_order": source_order(target["path"], GUARD_MARKERS[target["pr"]]),
            "relevant_callee_paths": list(CALLEES_BY_PR[target["pr"]]),
            "dynamic_call_edges": _dynamic_edges(target["pr"]),
            "out_of_scope_sibling_trigger_review": "NOT_RECLASSIFIED_BY_B3",
        })
    metadata = {
        "observed_at_utc": OBSERVED_AT,
        "read_only": True,
        "current_main_sha": BASE_MAIN,
        "control_pull_requests": {str(k): v for k, v in CONTROL_PRS.items()},
        "comments": [comment_snapshot(cid) for cid in sorted(COMMENTS)],
        "runs": [run_evidence(run_id) for run_id in sorted(RUNS)],
        "attempt_marker_prefix_searches": [
            {"control_pr_number": 103, "prefix": TARGETS[next(k for k in TARGETS if TARGETS[k]["pr"] == 103)]["marker_prefix"], "matching_comment_ids": [5302463691], "count": 1, "read_only": True},
            {"control_pr_number": 139, "prefix": TARGETS[next(k for k in TARGETS if TARGETS[k]["pr"] == 139)]["marker_prefix"], "matching_comment_ids": [5311311868], "count": 1, "read_only": True},
            {"control_pr_number": 145, "prefix": TARGETS[next(k for k in TARGETS if TARGETS[k]["pr"] == 145)]["marker_prefix"], "matching_comment_ids": [5318115383], "count": 1, "read_only": True},
            {"control_pr_number": 130, "prefix": TARGETS[next(k for k in TARGETS if TARGETS[k]["pr"] == 130)]["marker_prefix"], "matching_comment_ids": [5309822325], "count": 1, "read_only": True},
        ],
        "current_pr130_prior_artifact_metadata_observation": {
            "artifact_id": 9266604353,
            "metadata_get_state": "CURRENT_ACTIONS_ARTIFACT_METADATA_GET_404_NOT_FOUND",
            "run_id": 31953949073,
            "run_listing_total_count": 0,
            "source_endpoints": [
                "GET /repos/Thabearr/ATHENA/actions/artifacts/9266604353",
                "GET /repos/Thabearr/ATHENA/actions/runs/31953949073/artifacts",
            ],
            "read_only": True,
            "payload_downloaded": False,
            "used_as_primary_replay_guard": False,
        },
        "source_endpoints": [
            "GET /repos/Thabearr/ATHENA/pulls/{103,128,129,130,138,139,145}",
            "GET /repos/Thabearr/ATHENA/issues/comments/{comment_id}",
            "GET /repos/Thabearr/ATHENA/actions/runs/{run_id}",
        ],
        "no_comment_or_pr_mutation": True,
        "no_action_run_mutation": True,
        "no_artifact_payload_download": True,
    }
    return boundary.seal({
        "schema_version": 1,
        "policy_id": SOURCE_INVENTORY_POLICY_ID,
        "repository": "Thabearr/ATHENA",
        "master_issue": 337,
        "base_main_sha": BASE_MAIN,
        "base_tree_sha": BASE_TREE,
        "workflow_tree_sha1": WORKFLOW_TREE,
        "evolution_ledger_sha256": EVOLUTION_SHA,
        "evolution_transition_count": 14,
        "retirement_ledger_sha256": RETIREMENT_SHA,
        "retired_workflow_count": 3,
        "target_surface_count": len(TARGETS),
        "source_identities": identities,
        "target_surfaces": target_rows,
        "github_read_only_metadata": metadata,
        "post_441_tests": POST_441_TESTS,
        "no_workflow_mutation": True,
        "no_out_of_scope_surface_expansion": True,
    })


def _dynamic_edges(pr: int) -> list[dict[str, object]]:
    common = [
        {"edge": "issue_comment.created -> job execute", "classification": "OWNER_AND_CONTROL_PR_JOB_IF_GATED"},
        {"edge": "job -> actions/github-script", "classification": "READS_CONTROL_STATE_AND_ISSUE_COMMENTS_WRITES_ONE_SHOT_MARKER_AFTER_GUARDS"},
        {"edge": "job -> actions/checkout exact authorized main", "classification": "ONLY_AFTER_MARKER_WRITE"},
    ]
    specific = {
        103: [
            {"edge": "runner -> scripts.run_fotmob_ordinary_ft_source_history_acquisition", "classification": "LIVE_FOTMOB_4410_CAPTURE_BEHIND_MARKER"},
            {"edge": "capture helper -> FotMob data-matches HTTPS", "classification": "PUBLIC_PROVIDER_READ"},
            {"edge": "runner -> local research cache and run-scoped Actions artifact", "classification": "LOCAL_EVIDENCE_AND_ARTIFACT_WRITE"},
        ],
        139: [
            {"edge": "guard -> PR138 V1 reconciliation comment", "classification": "GITHUB_COMMENT_READ"},
            {"edge": "qualification -> exact PR119 artifact metadata and payload", "classification": "CROSS_RUN_ACTIONS_READ_AFTER_MARKER"},
            {"edge": "offline qualification -> run-scoped Actions artifact and result comment", "classification": "EVIDENCE_ARTIFACT_AND_GITHUB_COMMENT_WRITE"},
        ],
        145: [
            {"edge": "guard -> PR139 successful result and PR145 failed reconciliation comments", "classification": "GITHUB_COMMENT_READ"},
            {"edge": "validator -> exact source artifact metadata and payload", "classification": "CROSS_RUN_ACTIONS_READ_AFTER_MARKER"},
            {"edge": "source-bound validator -> research model validation/training", "classification": "RESEARCH_ONLY_AFTER_MARKER"},
            {"edge": "job -> run-scoped Actions artifact and result comment", "classification": "EVIDENCE_ARTIFACT_AND_GITHUB_COMMENT_WRITE"},
        ],
        130: [
            {"edge": "guard -> PR129 fix PR and PR128 prior result comment", "classification": "GITHUB_PR_AND_COMMENT_READ"},
            {"edge": "guard -> Actions getArtifact(9266604353)", "classification": "CROSS_RUN_ARTIFACT_METADATA_READ_BEFORE_MARKER"},
            {"edge": "campaign -> football-data.co.uk eight-slot capture", "classification": "PUBLIC_HISTORICAL_SOURCE_ACQUISITION_AFTER_MARKER"},
            {"edge": "campaign -> local evidence, run-scoped artifact and result comment", "classification": "EVIDENCE_AND_GITHUB_COMMENT_WRITE"},
        ],
    }
    return common + specific[pr]


def build_receipt() -> dict[str, object]:
    verify_workflow_ledgers()
    parent = authenticate_predecessor_chain()
    b2 = boundary.read("tests/fixtures/core_01d/core-01d-historical-warehouse-transfer-authority-b2-v1.json")
    require(b2.get("canonical_sha256") == B2_RECEIPT_SHA, "immutable B2 receipt identity drift")
    b2_inventory = boundary.read("tests/fixtures/core_01d/historical-warehouse-transfer-authority-b2-source-inventory-v1.json")
    require(b2_inventory.get("canonical_sha256") == B2_SOURCE_SHA, "immutable B2 source inventory identity drift")
    v4 = boundary.read("tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v4.json")
    require(v4.get("canonical_sha256") == COMPLETION_V4_SHA, "immutable Completion V4 identity drift")
    b1 = boundary.read("tests/fixtures/core_01d/core-01d-exact-pr-trigger-disposition-b1-v1.json")
    require(b1.get("canonical_sha256") == B1_RECEIPT_SHA, "immutable B1 receipt identity drift")
    require(boundary.read("tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v4.json").get("canonical_sha256") == A2_V4_SHA,
            "immutable A2 generation V4 identity drift")
    inventory = build_source_inventory()
    validate_source_inventory(inventory)
    inherited = parent["unreviewed_authority_surfaces"]
    inherited_keys = [(row["workflow_path"], row["trigger_kind"]) for row in inherited]
    require(len(inherited) == 20 and len(set(inherited_keys)) == 20, "Completion V5 unresolved census drift")
    target_keys = {(TARGETS[key]["path"], "issue_comment") for key in TARGETS}
    require(target_keys <= set(inherited_keys), "a B3 target is not inherited as unresolved")
    require(len(TARGETS) == 4 and len(target_keys) == 4, "B3 exact target set is not four unique surfaces")
    rows = [_review_row(key, target) for key, target in TARGETS.items()]
    require(all(row["review"]["status"] == "RESOLVED" for row in rows), "a B3 source/metadata row is partial")
    comments_by_id = {item["comment_id"]: item for item in inventory["github_read_only_metadata"]["comments"]}
    expected_snapshot_ids = set(COMMENTS)
    require(set(comments_by_id) == expected_snapshot_ids, "B3 GitHub metadata comment snapshot drift")
    return boundary.seal({
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository": "Thabearr/ATHENA",
        "master_issue": 337,
        "base_main_sha": BASE_MAIN,
        "base_tree_sha": BASE_TREE,
        "predecessors": {
            "completion_v5": {"path": COMPLETION_V5_PATH, "canonical_sha256": COMPLETION_V5_SHA, "rewritten": False},
            "b2_receipt": {"path": "tests/fixtures/core_01d/core-01d-historical-warehouse-transfer-authority-b2-v1.json", "canonical_sha256": B2_RECEIPT_SHA, "rewritten": False},
            "b2_source_inventory": {"path": "tests/fixtures/core_01d/historical-warehouse-transfer-authority-b2-source-inventory-v1.json", "canonical_sha256": B2_SOURCE_SHA, "rewritten": False},
            "completion_v4": {"path": "tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v4.json", "canonical_sha256": COMPLETION_V4_SHA, "rewritten": False},
            "b1_receipt": {"path": "tests/fixtures/core_01d/core-01d-exact-pr-trigger-disposition-b1-v1.json", "canonical_sha256": B1_RECEIPT_SHA, "rewritten": False},
            "a2_v4": {"path": "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v4.json", "canonical_sha256": A2_V4_SHA, "rewritten": False},
            "a2_v3_sha256": A2_V3_SHA,
        },
        "source_inventory": {"path": SOURCE_INVENTORY_PATH, "canonical_sha256": inventory["canonical_sha256"]},
        "post_441_tests": POST_441_TESTS,
        "target_surface_count": len(rows),
        "resolved_target_count": sum(row["review"]["status"] == "RESOLVED" for row in rows),
        "partial_target_count": sum(row["review"]["status"] != "RESOLVED" for row in rows),
        "global_unresolved_before": len(inherited),
        "global_unresolved_after": len(inherited) - sum(row["review"]["status"] == "RESOLVED" for row in rows),
        "workflow_tree_before_sha1": WORKFLOW_TREE,
        "workflow_tree_after_sha1": WORKFLOW_TREE,
        "evolution_ledger_before_sha256": EVOLUTION_SHA,
        "evolution_ledger_after_sha256": EVOLUTION_SHA,
        "evolution_transition_count_before": 14,
        "evolution_transition_count_after": 14,
        "retirement_ledger_sha256_before": RETIREMENT_SHA,
        "retirement_ledger_sha256_after": RETIREMENT_SHA,
        "retired_workflow_count": 3,
        "workflow_count": 39,
        "trigger_surface_count": 57,
        "review_rows": rows,
        "out_of_scope_surface_keys": [[row["workflow_path"], row["trigger_kind"]]
                                      for row in inherited if (row["workflow_path"], row["trigger_kind"]) not in target_keys],
        "actions": ZERO_ACTIONS,
        "workflow_edit_count": 0,
        "trigger_edit_count": 0,
        "workflow_retirement_count": 0,
        "workflow_deletion_count": 0,
        "caller_migration_count": 0,
        "criterion_11": False,
        "criterion_14": False,
        "checkpoint_e_status": "INCOMPLETE",
        "p4_4_status": "INCOMPLETE",
        "retention_blockers_A_B_C_D": "CLOSED_WITH_HISTORICAL_LIMITATIONS_PRESERVED",
        "historical_missing_artifact_relation_count": 14,
        "live_missing_artifact_relation_count": 0,
        "source_review_counter_while_open": "2/5",
        "source_review_counter_if_owner_merges": "3/5",
        "mandatory_governing_source_reread_after_b3_merge": False,
        "terminal": "CORE_01D_OWNER_ONE_SHOT_ISSUE_COMMENT_AUTHORITY_B3_REVIEW_READY_4_RESOLVED_DO_NOT_MERGE",
    })


def _review_row(key: str, target: dict[str, object]) -> dict[str, object]:
    identity = source_identity(target["path"])
    pr = CONTROL_PRS[target["pr"]]
    guard = source_order(target["path"], GUARD_MARKERS[target["pr"]])
    marker = comment_snapshot(target["marker_id"])
    command = comment_snapshot(target["command_id"])
    result = comment_snapshot(target["result_id"])
    require(command["author_login"] == "Thabearr", "historical command comment author drift")
    require(command["body"].splitlines() == [target["command"],
            "main-sha: " + target["run_head"], "confirm: " + target["confirmation"]],
            "exact historical owner command body drift")
    require(marker["author_login"] == "github-actions[bot]" and marker["body"].startswith(target["marker_prefix"] + "\n"),
            "historical attempt marker author/prefix drift")
    require(f"run-id: {target['run_id']}" in marker["body"]
            and f"main-sha: {target['run_head']}" in marker["body"]
            and f"command-comment-id: {target['command_id']}" in marker["body"],
            "historical marker run/main/command linkage drift")
    require(result["author_login"] == "github-actions[bot]"
            and f"run-id: {target['run_id']}" in result["body"]
            and f"main-sha: {target['run_head']}" in result["body"],
            "historical result comment run/main linkage drift")
    current_dims = {
        "github_pr_repository_default_ref_metadata_read": "CONTROL_AND_DEFAULT_BRANCH_READS_BEFORE_MARKER",
        "github_comment_read": "CONTROL_UPSTREAM_RECONCILIATION_AND_ATTEMPT_MARKER_READS_AS_DECLARED_BY_SOURCE",
        "github_comment_write": "NONE_BEFORE_PRESENT_MARKER_BLOCK",
        "github_api_write_other_than_comment": "NONE_SOURCE_HAS_NO_OTHER_GITHUB_MUTATION_CALL",
        "provider_acquisition": "NONE_BEFORE_EXISTING_MARKER_BLOCK" if target["pr"] != 130 else "NONE_BEFORE_MARKER; PUBLIC_SOURCE_ACQUISITION_AFTER_MARKER",
        "public_historical_source_acquisition": "NONE_BEFORE_EXISTING_MARKER_BLOCK" if target["pr"] != 130 else "NONE_BEFORE_MARKER; FOOTBALL_DATA_CAMPAIGN_AFTER_MARKER",
        "github_actions_artifact_metadata_read": "NONE_BEFORE_MARKER" if target["pr"] in (103, 139, 145) else "PRIOR_ARTIFACT_GET_BY_ID_9266604353_BEFORE_MARKER",
        "github_actions_artifact_payload_read": "NONE_BEFORE_EXISTING_MARKER_BLOCK",
        "model_or_research_execution": "NONE_BEFORE_EXISTING_MARKER_BLOCK",
        "local_research_evidence_write": "NONE_BEFORE_EXISTING_MARKER_BLOCK",
        "actions_artifact_write": "NONE_BEFORE_EXISTING_MARKER_BLOCK",
        "branch_or_repository_write": "NONE_BEFORE_EXISTING_MARKER_BLOCK; CHECKOUT_CREDENTIALS_DISABLED",
        "github_release_write": "NONE",
        "workflow_dispatch_authority": "NONE_NO_WORKFLOW_DISPATCH_TRIGGER_OR_API_CALL",
        "notification_authority": "NONE_BEFORE_PRESENT_MARKER_BLOCK",
        "persistent_canonical_database_write": "NONE",
        "external_storage_write": "NONE",
        "sportsbook_read": "NONE",
        "share_code": "NONE",
        "delivery": "NONE",
        "wager_stake_wallet": "NONE",
        "production_authority": "NONE",
    }
    if target["pr"] == 130:
        current_block = "PRE_MARKER_GITHUB_ACTIONS_ARTIFACT_METADATA_GET_CURRENTLY_RETURNS_404; IF_LOOKUP_GUARD_CONTINUES_PRESENT_MARKER_BLOCKS_BEFORE_CHECKOUT_AND_LIVE_SOURCE_ACQUISITION"
        first_current_boundary = "GitHub API metadata read for artifact 9266604353 occurs before the current attempt-marker list read"
        high_risk_boundary = "football-data.co.uk eight-slot public-source acquisition after the present attempt marker and exact-main checkout"
        historical = {
            "provider_acquisition": "NONE_FOTMOB",
            "public_historical_source_acquisition": "FOOTBALL_DATA_CO_UK_EIGHT_SLOT_LIVE_CAPTURE",
            "github_actions_artifact_metadata_read": "PRIOR_V1_ARTIFACT_METADATA_GET_BY_ID_9266604353",
            "github_actions_artifact_payload_read": "NONE_SOURCE_DOES_NOT_DOWNLOAD_PRIOR_V1_PAYLOAD",
            "model_or_research_execution": "PRIMARY_EVIDENCE_ACQUISITION_ONLY_NO_SEMANTIC_QUALIFICATION",
            "local_research_evidence_write": "EIGHT_SLOT_RUNNER_LOCAL_EVIDENCE",
            "actions_artifact_write": "RUN_SCOPED_PRIMARY_TIME_BASIS_EVIDENCE_ARTIFACT",
            "github_comment_write": "ONE_SHOT_ATTEMPT_AND_RESULT_COMMENTS",
            "persistent_canonical_database_write": "NONE",
            "external_storage_write": "NONE",
            "sportsbook_read": "NONE",
            "share_code": "NONE",
            "delivery": "NONE",
            "wager_stake_wallet": "NONE",
            "production_authority": "NONE_NO_SEMANTIC_OR_MODEL_AUTHORITY",
        }
    elif target["pr"] == 103:
        current_block = "EXISTING_MARKER_CHECK_BEFORE_MARKER_WRITE_CHECKOUT_AND_PROVIDER_NETWORK"
        first_current_boundary = "GitHub control PR, repository, default-ref and issue-comment metadata reads"
        high_risk_boundary = "FotMob data-matches acquisition behind exact one-shot marker write and exact main checkout"
        historical = {
            "provider_acquisition": "FOTMOB_DATA_MATCHES_LIVE_SOURCE_CAPTURE_4410_SLOTS",
            "public_historical_source_acquisition": "NONE_SEPARATE_PUBLIC_ARCHIVE_SOURCE",
            "github_actions_artifact_metadata_read": "NONE",
            "github_actions_artifact_payload_read": "NONE",
            "model_or_research_execution": "RESEARCH_SOURCE_HISTORY_CAPTURE_NO_MODEL_OR_SELECTION",
            "local_research_evidence_write": "FOTMOB_SOURCE_HISTORY_RESEARCH_CACHE",
            "actions_artifact_write": "RUN_SCOPED_CAPTURE_EVIDENCE_ARTIFACT",
            "github_comment_write": "ATTEMPT_MARKER_AND_RESULT_COMMENTS",
            "persistent_canonical_database_write": "NONE",
            "external_storage_write": "NONE",
            "sportsbook_read": "NONE",
            "share_code": "NONE",
            "delivery": "NONE",
            "wager_stake_wallet": "NONE",
            "production_authority": "NONE",
        }
    elif target["pr"] == 139:
        current_block = "EXISTING_MARKER_CHECK_BEFORE_CHECKOUT_ARTIFACT_METADATA_OR_PAYLOAD_READ"
        first_current_boundary = "GitHub control PR, repository, default-ref, PR138 reconciliation and current PR139 comment reads"
        high_risk_boundary = "PR119 artifact payload read and offline feature qualification after exact one-shot marker write and checkout"
        historical = {
            "provider_acquisition": "NONE_NO_PROVIDER_NETWORK",
            "public_historical_source_acquisition": "NONE",
            "github_actions_artifact_metadata_read": "EXACT_PR119_ARTIFACT_ID_9249856559_METADATA_READ",
            "github_actions_artifact_payload_read": "EXACT_PR119_ARTIFACT_PAYLOAD_READ",
            "model_or_research_execution": "OFFLINE_UTC_NATIVE_FEATURE_QUALIFICATION_ONLY",
            "local_research_evidence_write": "LOCAL_QUALIFICATION_EVIDENCE",
            "actions_artifact_write": "RUN_SCOPED_QUALIFICATION_EVIDENCE_ARTIFACT",
            "github_comment_write": "ATTEMPT_MARKER_AND_RESULT_COMMENTS",
            "persistent_canonical_database_write": "NONE",
            "external_storage_write": "NONE",
            "sportsbook_read": "NONE",
            "share_code": "NONE",
            "delivery": "NONE",
            "wager_stake_wallet": "NONE",
            "production_authority": "NONE_NO_MODEL_PRICING_SELECTION_OR_BET",
        }
    else:
        current_block = "EXISTING_MARKER_CHECK_BEFORE_CHECKOUT_ARTIFACT_METADATA_PAYLOAD_AND_MODEL_VALIDATION"
        first_current_boundary = "GitHub control PR, repository, default-ref, upstream result, reconciliation and current PR145 comment reads"
        high_risk_boundary = "historical source artifact payload read and research expected-goals validation/training after marker and checkout"
        historical = {
            "provider_acquisition": "NONE_NO_PROVIDER_NETWORK",
            "public_historical_source_acquisition": "NONE",
            "github_actions_artifact_metadata_read": "EXACT_SOURCE_ARTIFACT_ID_9275052993_METADATA_READ",
            "github_actions_artifact_payload_read": "EXACT_SOURCE_ARTIFACT_PAYLOAD_READ",
            "model_or_research_execution": "SOURCE_BOUND_RESEARCH_MODEL_VALIDATION_AND_TRAINING",
            "local_research_evidence_write": "LOCAL_MODEL_VALIDATION_EVIDENCE",
            "actions_artifact_write": "RUN_SCOPED_VALIDATION_EVIDENCE_ARTIFACT",
            "github_comment_write": "ATTEMPT_MARKER_AND_RESULT_COMMENTS",
            "persistent_canonical_database_write": "NONE",
            "external_storage_write": "NONE",
            "sportsbook_read": "NONE",
            "share_code": "NONE",
            "delivery": "NONE",
            "wager_stake_wallet": "NONE",
            "production_authority": "NONE_NO_MODEL_PROMOTION_PROBABILITY_PRICING_SELECTION_OR_BET",
        }
    historical.update({
        "github_pr_repository_default_ref_metadata_read": "CONTROL_PR_REPO_AND_CURRENT_DEFAULT_REF_READS",
        "github_comment_read": "CONTROL_COMMAND_AND_REQUIRED_RECONCILIATION_OR_ATTEMPT_MARKER_COMMENT_READS",
        "github_api_write_other_than_comment": "NONE_NO_PR_BRANCH_RELEASE_OR_REPOSITORY_MUTATION_CALL",
        "branch_or_repository_write": "NONE_CHECKOUT_PERSIST_CREDENTIALS_FALSE",
        "github_release_write": "NONE",
        "notification_authority": "GITHUB_ISSUE_COMMENT_STATUS_ONLY",
        "workflow_dispatch_authority": "NONE_NO_WORKFLOW_DISPATCH_TRIGGER_OR_API_CALL",
    })
    return {
        "surface_key": key,
        "identity": {"workflow_path": target["path"], "trigger_kind": "issue_comment", **identity},
        "event_contract": trigger_contract(key),
        "current_control_state": {
            "control_pr_number": target["pr"], "control_pr": pr,
            "control_pr_issue_state": "closed",
            "control_pr_conversation_locked": False,
            "command_comment": command, "attempt_marker_comment": marker, "result_comment": result,
            "required_lineage_comments": [comment_snapshot(cid) for cid in RECON_COMMENT_IDS.get(target["pr"], [])],
            "attempt_marker_prefix": target["marker_prefix"], "marker_currently_present": True,
            "marker_author": marker["author_login"], "historical_run_id": target["run_id"],
            "historical_run": run_evidence(target["run_id"]),
            "historical_run_main_sha": target["run_head"],
            "pre_marker_artifact_metadata_observation": (
                {"artifact_id": 9266604353,
                 "metadata_get_state": "CURRENT_ACTIONS_ARTIFACT_METADATA_GET_404_NOT_FOUND",
                 "run_id": 31953949073, "run_listing_total_count": 0,
                 "read_only": True, "payload_downloaded": False,
                 "used_as_primary_replay_guard": False}
                if target["pr"] == 130 else None),
            "control_comment_mutation_residual": "CONTROL_COMMENT_MUTATION_RESIDUAL_NOT_PROVEN_IMPOSSIBLE",
        },
        "guard_order": guard,
        "reachability": {
            "declared_event_surface_reachability": "PHYSICALLY_REACHABLE_OWNER_COMMENT_EVENT",
            "current_guarded_high_risk_execution_reachability": ("BLOCKED_BY_PRE_MARKER_ARTIFACT_METADATA_404_AND_PRESENT_MARKER_IF_METADATA_LOOKUP_PASSES"
                if target["pr"] == 130 else "BLOCKED_BY_PRESENT_DURABLE_ONE_SHOT_ATTEMPT_MARKER_IF_PRE_MARKER_GUARDS_PASS"),
            "current_guard_side_effects_before_replay_block": current_block,
            "current_execution_authority": current_dims,
            "first_current_external_boundary": first_current_boundary,
            "first_guarded_high_risk_boundary": high_risk_boundary,
            "historical_actions_rerun_residual": "HISTORICAL_ACTIONS_RERUN_RESIDUAL_NOT_PROVEN_ABSENT",
            "artifact_availability_used_as_primary_guard": False,
            "historical_artifact_availability_note": "NOT_USED_TO_ESTABLISH_CURRENT_ONE_SHOT_BLOCK; NO_ARTIFACT_PAYLOAD_DOWNLOADED",
            "sibling_trigger_state": "OTHER_TRIGGER_KINDS_REMAIN_OUT_OF_SCOPE_AND_UNCHANGED",
        },
        "historical_guarded_capability": historical,
        "current_observed_control_state_authority": current_dims,
        "dynamic_reachability": {
            "edges": _dynamic_edges(target["pr"]),
            "source_identity_chain": [source_identity(target["path"])] +
                                     [source_identity(path) for path in CALLEES_BY_PR[target["pr"]]],
            "marker_check_precedes_first_current_external_boundary": False,
            "marker_check_precedes_high_risk_execution_boundary": True,
            "PR130_artifact_metadata_read_precedes_marker_check": target["pr"] == 130,
        },
        "review": {"status": "RESOLVED", "disposition": "CURRENT_OWNER_COMMENT_SURFACE_REVIEWED_WITH_PRESENT_MARKER_BLOCK_AND_RESIDUALS_PRESERVED", "blocker": None},
    }


def validate_source_inventory(value: dict[str, object], expected: dict[str, object] | None = None,
                              raw: bytes | None = None) -> None:
    raw = (ROOT / SOURCE_INVENTORY_PATH).read_bytes() if raw is None else raw
    require(raw == boundary.canonical(value), "B3 source inventory is not canonical")
    require(value == (build_source_inventory() if expected is None else expected),
            "B3 source inventory differs from source/read-only metadata evidence")
    require(value.get("base_main_sha") == BASE_MAIN and value.get("base_tree_sha") == BASE_TREE,
            "B3 inventory base identity drift")
    require(value.get("target_surface_count") == 4 and len(value.get("target_surfaces", [])) == 4,
            "B3 inventory must bind exactly four target surfaces")
    require(value.get("no_out_of_scope_surface_expansion") is True, "B3 expanded beyond target scope")


def validate_receipt(value: dict[str, object], expected: dict[str, object] | None = None,
                     raw: bytes | None = None) -> None:
    raw = (ROOT / RECEIPT_PATH).read_bytes() if raw is None else raw
    require(raw == boundary.canonical(value), "B3 receipt is not canonical")
    require(value == (build_receipt() if expected is None else expected),
            "B3 receipt differs from authenticated predecessor/source/metadata overlay")
    require(value["target_surface_count"] == 4 and value["resolved_target_count"] == 4
            and value["partial_target_count"] == 0, "B3 target counts are not 4/4")
    require(value["global_unresolved_after"] == value["global_unresolved_before"] - value["resolved_target_count"] == 16,
            "B3 global unresolved count is not derived")
    require(value["checkpoint_e_status"] == value["p4_4_status"] == "INCOMPLETE"
            and value["criterion_11"] is False and value["criterion_14"] is False,
            "B3 cannot complete Checkpoint E/P4.4")
    require(all(row["review"]["status"] == "RESOLVED" for row in value["review_rows"]),
            "B3 includes an unproven current-state classification")
    for row in value["review_rows"]:
        require(row["reachability"]["declared_event_surface_reachability"] == "PHYSICALLY_REACHABLE_OWNER_COMMENT_EVENT",
                "merged PR was incorrectly used to call issue_comment unreachable")
        require(row["reachability"]["historical_actions_rerun_residual"] == "HISTORICAL_ACTIONS_RERUN_RESIDUAL_NOT_PROVEN_ABSENT",
                "historical rerun residual was omitted or overclaimed")
        require(row["current_control_state"]["control_comment_mutation_residual"] == "CONTROL_COMMENT_MUTATION_RESIDUAL_NOT_PROVEN_IMPOSSIBLE",
                "marker permanence overclaimed")
    pr130 = next(row for row in value["review_rows"] if row["identity"]["workflow_path"].endswith("pr69-primary-time-basis-evidence-campaign-v2.yml"))
    require(pr130["dynamic_reachability"]["PR130_artifact_metadata_read_precedes_marker_check"] is True,
            "PR130 artifact metadata read must remain before marker check")
    require(pr130["current_observed_control_state_authority"]["github_actions_artifact_metadata_read"] ==
            "PRIOR_ARTIFACT_GET_BY_ID_9266604353_BEFORE_MARKER", "PR130 pre-marker metadata read authority was erased")


def audit() -> dict[str, object]:
    inventory = boundary.read(SOURCE_INVENTORY_PATH)
    validate_source_inventory(inventory)
    receipt = boundary.read(RECEIPT_PATH)
    validate_receipt(receipt)
    return {
        "result": "PASS", "source_inventory_sha256": inventory["canonical_sha256"],
        "receipt_sha256": receipt["canonical_sha256"], "target_surface_count": 4,
        "resolved_target_count": receipt["resolved_target_count"],
        "global_unresolved_after": receipt["global_unresolved_after"],
        "checkpoint_e": receipt["checkpoint_e_status"], "p4_4": receipt["p4_4_status"],
        "terminal": receipt["terminal"],
    }


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
        value = build_receipt()
        (ROOT / RECEIPT_PATH).write_bytes(boundary.canonical(value))
        print(value["canonical_sha256"])
    else:
        print(json.dumps(audit(), sort_keys=True))


if __name__ == "__main__":
    main()
