from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import audit_post_p4_4l_international_provider_family_bridge as audit


ROOT = Path(__file__).resolve().parents[1]


def _load_receipt():
    return json.loads((ROOT / audit.RECEIPT_PATH).read_text(encoding="utf-8"))


def _rehash(receipt):
    semantic = dict(receipt)
    semantic.pop("canonical_sha256", None)
    raw = json.dumps(semantic, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    receipt["canonical_sha256"] = hashlib.sha256(raw).hexdigest()


def test_bridge_architecture_receipt_and_runtime_isolation_audit_pass():
    receipt = _load_receipt()
    assert audit.validate_receipt(receipt) == receipt["canonical_sha256"]
    audit.validate_runtime_isolation()


def test_audit_rejects_receipt_mapping_expansion_even_with_recomputed_receipt_hash():
    receipt = copy.deepcopy(_load_receipt())
    receipt["reviewed_mappings"].append(copy.deepcopy(receipt["reviewed_mappings"][0]))
    _rehash(receipt)
    with pytest.raises(audit.InternationalProviderFamilyBridgeAuditError):
        audit.validate_receipt(receipt)


def test_audit_rejects_youth_or_provider_only_identity_promotion():
    receipt = copy.deepcopy(_load_receipt())
    receipt["unmapped_source_identities"][0]["state"] = "MAPPED"
    _rehash(receipt)
    with pytest.raises(audit.InternationalProviderFamilyBridgeAuditError):
        audit.validate_receipt(receipt)

    receipt = copy.deepcopy(_load_receipt())
    receipt["provider_only_unmapped_observation"]["source_mapping_added"] = True
    _rehash(receipt)
    with pytest.raises(audit.InternationalProviderFamilyBridgeAuditError):
        audit.validate_receipt(receipt)


def test_audit_rejects_runtime_authority_or_owner_drift():
    receipt = copy.deepcopy(_load_receipt())
    receipt["authority"]["current_shadow_runtime_discovery"] = True
    _rehash(receipt)
    with pytest.raises(audit.InternationalProviderFamilyBridgeAuditError):
        audit.validate_receipt(receipt)

    receipt = copy.deepcopy(_load_receipt())
    receipt["continuity"]["p3_runtime_changed"] = True
    _rehash(receipt)
    with pytest.raises(audit.InternationalProviderFamilyBridgeAuditError):
        audit.validate_receipt(receipt)


def test_audit_rejects_policy_and_receipt_identity_drift():
    receipt = copy.deepcopy(_load_receipt())
    receipt["bridge_policy_sha256"] = "0" * 64
    _rehash(receipt)
    with pytest.raises(audit.InternationalProviderFamilyBridgeAuditError):
        audit.validate_receipt(receipt)
