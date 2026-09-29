from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import re
import socket
import urllib.request

import pytest

from domain import current_shadow_run_contract_adapter as adapter
from domain import run_contracts
from scripts import audit_auth_01_analysis_only_shadow as audit


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ARTIFACT_SHA256 = "7b09adb4882d49749c33efecbce0b1c8985a2d3bdec52417f7b02f8f335f4a86"
EXPECTED_FALSE_REQUEST_SHA256 = "2206abcefa58a28b3ec162b8a735e20ee2b18203b832837c8da9cf2735a5b276"
EXPECTED_TRUE_REQUEST_SHA256 = "0142610f7c9fd1eec15b00da8ca13ecf4d2efc107b6b6d60e6e32e0841aaf3c4"


def _artifact() -> dict:
    return audit._read_json(ROOT / audit.ARTIFACT_PATH)


def _assert_no_share_values(value, path="$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            normalized = key.lower()
            if any(token in normalized for token in ("share_code", "share_url", "sharecode", "shareurl")):
                assert (
                    item is None
                    or type(item) is bool
                    or (normalized.endswith("_calls") and type(item) is int and item == 0)
                ), child_path
            _assert_no_share_values(item, child_path)
    elif type(value) is list:
        for index, item in enumerate(value):
            _assert_no_share_values(item, f"{path}[{index}]")
    elif type(value) is str:
        assert not re.search(r"https?://|sportybet\.com", value, re.IGNORECASE), path


def _policy(create_share_code: bool | None) -> dict:
    authority = {
        "research_shadow_request": True,
        "production_model": False,
        "pricing": False,
        "selection": False,
        "sportybet_execution": False,
        "bet": False,
        "wager_placed": False,
    }
    policy = {
        "schema_version": 1,
        "dataset_name": adapter.CURRENT_REQUEST_DATASET,
        "fixture_scope": "today",
        "fixture_dates": ["20260927"],
        "authority": authority,
        "wager_placed": False,
    }
    if create_share_code is not None:
        policy["create_share_code"] = create_share_code
        authority["research_anonymous_share_code_generation"] = create_share_code
        authority["provider_create_reload_verification"] = create_share_code
    return policy


def test_a5_artifact_is_canonical_and_freezes_the_reviewed_boundary():
    artifact = _artifact()
    claimed = artifact["canonical_sha256"]
    unsigned = dict(artifact)
    unsigned.pop("canonical_sha256")

    assert claimed == EXPECTED_ARTIFACT_SHA256
    assert hashlib.sha256(audit._canonical(unsigned)).hexdigest() == claimed
    assert artifact["schema_version"] == 1
    assert artifact["policy_id"] == audit.POLICY_ID == "ATHENA_AUTH_01_ANALYSIS_ONLY_SHADOW_V1"
    assert artifact["implementation_base_main_sha"] == audit.BASE_MAIN_SHA
    assert artifact["current_no_delivery_contract"]["create_share_code"] is False
    assert artifact["current_no_delivery_contract"]["share_code_generation_capability"] is False
    assert artifact["current_no_delivery_contract"]["provider_acquisition_capability"] is True
    assert artifact["current_no_delivery_contract"]["shortfall"] == 19
    assert artifact["offline_replay"]["clean_process_count"] == 2
    assert artifact["offline_replay"]["import_orders"] == ["forward", "reverse"]
    assert artifact["offline_replay"]["canonical_output_bytes_identical"] is True
    assert artifact["governance"]["P4_4"] == "INCOMPLETE"
    assert artifact["governance"]["architecture_checkpoint_E"] == "INCOMPLETE"
    assert artifact["governance"]["clean_successor_proof"] == "INCOMPLETE"
    assert artifact["governance"]["live_proof"] == "NOT_AUTHORIZED"
    assert artifact["governance"]["caller_migration"] == "NOT_AUTHORIZED"
    assert artifact["governance"]["workflow_retirement"] == "NOT_AUTHORIZED"
    assert artifact["historical_authorization_mismatch"]["classification"] == (
        "POST_P4_4S_INTERNAL_SUCCESS_AUTHORIZATION_NONCOMPLIANT_SHARE_CODE_SIDE_EFFECT"
    )
    assert artifact["historical_authorization_mismatch"]["raw_share_code_copied"] is False
    assert artifact["historical_authorization_mismatch"]["raw_share_url_copied"] is False
    assert all(value == 0 for value in artifact["safety"].values() if type(value) is int)
    _assert_no_share_values(artifact)


def test_adapter_preserves_exact_v1_bytes_for_both_delivery_intents():
    dates = (date(2026, 9, 27),)
    hashes = {}
    for intent in (False, True):
        request = adapter.adapt_current_shadow_request(
            target_size=20,
            request_policy=_policy(intent),
            resolved_dates=dates,
            expected_create_share_code=intent,
        )
        raw = run_contracts.canonical_json_bytes(request)
        assert run_contracts.RunRequest.from_json_bytes(raw) == request
        assert hashlib.sha256(raw).hexdigest() == request.canonical_sha256
        hashes[intent] = request.canonical_sha256

    assert hashes[False] == EXPECTED_FALSE_REQUEST_SHA256
    assert hashes[True] == EXPECTED_TRUE_REQUEST_SHA256
    assert hashes[False] != hashes[True]
    with pytest.raises(adapter.CurrentShadowRunContractAdapterError, match="requires explicit policy"):
        adapter.adapt_current_shadow_request(
            target_size=20,
            request_policy=_policy(None),
            resolved_dates=dates,
            expected_create_share_code=False,
        )


def test_frozen_base_and_p44_receipt_identities_are_unchanged():
    assert audit._git_blob(audit.BASELINE_JSON) == audit.BASELINE_JSON_BLOB
    assert audit._git_blob(audit.BASELINE_MARKDOWN) == audit.BASELINE_MARKDOWN_BLOB
    for path, expected in (
        (audit.P44R_RECEIPT_PATH, audit.P44R_RECEIPT_SHA256),
        (audit.P44S_RECEIPT_PATH, audit.P44S_RECEIPT_SHA256),
    ):
        receipt = audit._read_json(ROOT / path)
        claimed = receipt.get("canonical_sha256")
        unsigned = dict(receipt)
        unsigned.pop("canonical_sha256", None)
        assert claimed == expected
        assert hashlib.sha256(audit._canonical(unsigned)).hexdigest() == expected


def test_offline_audit_recomputes_two_process_proof_with_network_sentinels(monkeypatch):
    attempts: list[str] = []

    def deny(name: str):
        def blocked(*_args, **_kwargs):
            attempts.append(name)
            raise AssertionError(f"unexpected network attempt in offline A5 audit: {name}")

        return blocked

    monkeypatch.setattr(socket.socket, "connect", deny("socket.connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", deny("socket.connect_ex"))
    monkeypatch.setattr(socket, "create_connection", deny("socket.create_connection"))
    monkeypatch.setattr(urllib.request, "urlopen", deny("urllib.urlopen"))

    result = audit.check_artifact()

    assert result["result"] == "PASS"
    assert result["policy_id"] == audit.POLICY_ID
    assert result["artifact_canonical_sha256"] == EXPECTED_ARTIFACT_SHA256
    assert result["clean_process_count"] == 2
    assert result["P4_4R_P4_4S"]["P4_4R"]["result"] == "PASS"
    assert result["P4_4R_P4_4S"]["P4_4S"]["result"] == "PASS"
    assert attempts == []
