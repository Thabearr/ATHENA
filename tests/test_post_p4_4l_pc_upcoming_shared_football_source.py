from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import audit_post_p4_4l_pc_upcoming_shared_football_source as audit


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / audit.RECEIPT_PATH


def _receipt() -> dict:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def _rehash(value: dict) -> dict:
    payload = dict(value)
    payload.pop("canonical_sha256", None)
    canonical = json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    value["canonical_sha256"] = hashlib.sha256(canonical).hexdigest()
    return value


def test_source_contract_audit_passes_offline() -> None:
    result = audit.audit(ROOT)
    assert result["status"] == "PASSED"
    assert result["network_used"] is False
    assert result["runtime_owner_unchanged"] is True
    assert result["p3_runtime_owner_unchanged"] is True
    assert result["paginated_runtime_authority_false"] is True
    assert result["fanout_runtime_authority_false"] is True
    assert result["fanout_global_echo_rejected"] is True


def test_audit_rejects_receipt_claiming_diagnostic_pagination_complete() -> None:
    value = _rehash(copy.deepcopy(_receipt()))
    value["diagnostic_capture_assessment"]["pagination_complete"] = True
    value = _rehash(value)
    with pytest.raises(audit.PcUpcomingSourceAuditError, match="pagination"):
        audit.validate_receipt(value)


def test_audit_rejects_runtime_promotion_or_p3_promotion() -> None:
    value = copy.deepcopy(_receipt())
    value["runtime_and_governance"]["current_shadow_runtime_owner_changed"] = True
    with pytest.raises(audit.PcUpcomingSourceAuditError, match="authority"):
        audit.validate_receipt(_rehash(value))
    value = copy.deepcopy(_receipt())
    value["runtime_and_governance"]["p3_runtime_owner_changed"] = True
    with pytest.raises(audit.PcUpcomingSourceAuditError, match="authority"):
        audit.validate_receipt(_rehash(value))


def test_audit_rejects_diagnostic_hash_or_unreviewed_provider_mapping_drift() -> None:
    value = copy.deepcopy(_receipt())
    value["diagnostic_pages"][0]["raw_sha256"] = "0" * 64
    with pytest.raises(audit.PcUpcomingSourceAuditError, match="raw page"):
        audit.validate_receipt(_rehash(value))
    value = copy.deepcopy(_receipt())
    value["observed_provider_families"][5]["athena_source_family_mapping_added"] = True
    with pytest.raises(audit.PcUpcomingSourceAuditError, match="Gulf Cup"):
        audit.validate_receipt(_rehash(value))


def test_source_policy_has_no_runtime_or_downstream_authority() -> None:
    from domain import current_shadow_sportybet_pc_upcoming_discovery as pc

    assert pc.AUTHORITY["provider_discovery_evidence"] is True
    for key in set(pc.AUTHORITY) - {"provider_discovery_evidence"}:
        assert pc.AUTHORITY[key] is False
