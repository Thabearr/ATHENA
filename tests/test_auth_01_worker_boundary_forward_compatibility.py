from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import audit_auth_01_analysis_only_shadow as historical_audit
from scripts import audit_auth_01_analysis_only_shadow_worker_boundary as audit


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_ARTIFACT_SHA256 = "7b09adb4882d49749c33efecbce0b1c8985a2d3bdec52417f7b02f8f335f4a86"
HISTORICAL_REPLAY_SHA256 = "3b792193ef813f4aab79d7c3f9d48550270f3ae008265cc9ceb9c3d629e974f5"
FALSE_REQUEST_SHA256 = "2206abcefa58a28b3ec162b8a735e20ee2b18203b832837c8da9cf2735a5b276"
TRUE_REQUEST_SHA256 = "0142610f7c9fd1eec15b00da8ca13ecf4d2efc107b6b6d60e6e32e0841aaf3c4"


@pytest.fixture(scope="module")
def proof() -> dict:
    return audit.check_artifact()


def _forward_artifact() -> dict:
    return audit._read_json(ROOT / audit.ARTIFACT_PATH)


def test_forward_artifact_has_exact_canonical_self_hash(proof):
    artifact = _forward_artifact()
    unsigned = dict(artifact)
    claimed = unsigned.pop("canonical_sha256")
    assert claimed == hashlib.sha256(audit._canonical(unsigned)).hexdigest()
    assert artifact["policy_id"] == "ATHENA_AUTH_01_ANALYSIS_ONLY_SHADOW_WORKER_BOUNDARY_V1"
    assert proof["result"] == "PASS"


def test_historical_auth_01d_artifact_and_replay_identity_remain_immutable(proof):
    historical = historical_audit._validate_historical_artifact(ROOT)
    assert historical["canonical_sha256"] == HISTORICAL_ARTIFACT_SHA256
    assert historical["offline_replay"]["deterministic_output_sha256"] == HISTORICAL_REPLAY_SHA256
    assert proof["historical_predecessor_integrity"] == "PASS"
    assert proof["historical_replay_sha256"] == HISTORICAL_REPLAY_SHA256
    assert proof["historical_full_receipt_sha_compared"] is False


def test_false_and_true_request_v1_identities_are_unchanged(proof):
    artifact = _forward_artifact()
    request = artifact["current_request_contract"]
    assert request["false_request_sha256"] == FALSE_REQUEST_SHA256
    assert request["true_compatibility_request_sha256"] == TRUE_REQUEST_SHA256
    assert proof["worker_command"]["request_artifact_id"] == FALSE_REQUEST_SHA256


def test_worker_command_worker_entry_and_receipt_bind_current_head(proof):
    assert proof["current_head_sha"] != historical_audit.BASE_MAIN_SHA
    assert proof["worker_command"]["release_identity_kind"] == "DEVELOPMENT_CHECKOUT"
    assert proof["worker_command"]["release_identity_id"] == proof["current_head_sha"]
    assert proof["worker_entry_release_identity_id"] == proof["current_head_sha"]
    assert proof["run_receipt_exact_commit_sha"] == proof["current_head_sha"]


def test_worker_command_binds_request_and_explicitly_has_no_envelope(proof):
    command = proof["worker_command"]
    assert command["operation"] == "CURRENT_SHADOW_REQUEST"
    assert command["mode"] == "research_shadow"
    assert command["request_artifact_id"] == FALSE_REQUEST_SHA256
    assert command["envelope_artifact_id"] is None
    assert command["request_artifact_id"] != historical_audit.BASE_MAIN_SHA


def test_worker_boundary_does_not_enable_arbitrary_dispatch(proof):
    artifact = _forward_artifact()["current_worker_boundary"]
    assert artifact["arbitrary_module"] is False
    assert artifact["arbitrary_function"] is False
    assert artifact["arbitrary_argv"] is False
    assert artifact["arbitrary_environment"] is False
    assert artifact["arbitrary_cwd"] is False
    assert artifact["shell"] is False
    assert proof["worker_command"]["operation"] == "CURRENT_SHADOW_REQUEST"


def test_final_worker_delivery_argument_is_exact_false_and_real_parser_accepts_it(proof):
    assert proof["worker_final_delivery_argument"] == ["--create-share-code", "false"]
    assert proof["worker_parser_create_share_code"] is False
    assert _forward_artifact()["current_worker_boundary"]["delivery_argument"] == [
        "--create-share-code",
        "false",
    ]


def test_request_policy_and_inner_receipt_preserve_no_delivery(proof):
    assert proof["worker_request_policy_create_share_code"] is False
    assert proof["worker_inner_receipt_create_share_code"] is False
    projection = _forward_artifact()["semantic_continuity"]["projection"]
    assert projection["request_policy_delivery_intent"] is False
    assert projection["inner_delivery_intent"] is False


def test_forward_evidence_contains_no_share_or_wager_result(proof):
    assert proof["worker_share_receipt_present"] is False
    assert proof["worker_share_code_present"] is False
    assert proof["worker_share_url_present"] is False
    assert proof["worker_wager_placed"] is False
    projection = _forward_artifact()["semantic_continuity"]["projection"]
    assert projection["share_receipt_present"] is False
    assert projection["share_code_present"] is False
    assert projection["share_url_present"] is False
    assert projection["wager_placed"] is False


def test_forward_replay_side_effect_sentinels_are_zero(proof):
    assert proof["provider_network_calls"] == 0
    assert proof["share_transport_calls"] == 0
    assert proof["account_wager_calls"] == 0
    assert all(value == 0 for value in _forward_artifact()["network_sentinels"].values())
    assert all(value == 0 for value in _forward_artifact()["side_effects"].values())


def test_semantic_continuity_is_deterministic_without_historical_receipt_comparison(proof):
    artifact = _forward_artifact()
    projection = artifact["semantic_continuity"]["projection"]
    expected = hashlib.sha256(audit._canonical(projection)).hexdigest()
    assert artifact["semantic_continuity"]["semantic_continuity_sha256"] == expected
    assert proof["semantic_continuity_sha256"] == expected
    assert proof["clean_process_count"] == 2
    assert proof["forward_reverse_semantic_bytes_equal"] is True
    assert proof["forward_reverse_full_replay_bytes_equal"] is True
    assert artifact["semantic_continuity"]["historical_full_run_receipt_sha_compared"] is False
    assert proof["current_run_receipt_sha256"] not in json.dumps(artifact, sort_keys=True)
