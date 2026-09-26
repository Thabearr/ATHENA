from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from domain import current_shadow_all_market_runner as runner
from domain import current_shadow_sportybet_pc_upcoming_reconciliation as runtime
from domain import current_shadow_sportybet_upcoming_reconciliation as historical
from scripts import audit_post_p4_4l_pc_upcoming_runtime_migration as audit


def _canonical_sha(payload: dict) -> str:
    semantic = dict(payload)
    semantic.pop("canonical_sha256", None)
    return hashlib.sha256(json.dumps(
        semantic, ensure_ascii=False, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ).encode()).hexdigest()


def test_current_owner_is_the_complete_pc_upcoming_wrapper_and_historical_wap_remains():
    assert runner.reconciliation is runtime
    assert runner.upcoming_discovery is runtime
    assert historical.CURRENT_SHADOW_UPCOMING_POLICY_ID == (
        "ATHENA_CURRENT_SHADOW_UPCOMING_DISCOVERY_V1"
    )
    assert historical.UPCOMING_PATH == "/api/ng/factsCenter/wapConfigurableUpcomingEvents"
    assert runtime.POLICY_ID == "ATHENA_CURRENT_SHADOW_PC_UPCOMING_DISCOVERY_RECONCILIATION_V1"
    assert runtime._policy_payload()["runtime_pagination"]["required"] is True
    assert runtime._policy_payload()["runtime_pagination"]["partial_capture_provider_absence_authority"] is False


def test_migration_audit_authenticates_current_and_historical_source_lineage():
    result = audit.audit(Path(__file__).resolve().parents[1])
    assert result["status"] == "PASSED"
    assert result["current_shadow_and_p3_shared_source"] is True
    assert result["old_wap_retained_historical"] is True
    assert result["pagination_complete_required"] is True
    assert result["provider_acquisition_used"] is False
    assert result["workflow_dispatch_used"] is False
    assert result["migration_receipt_sha256"] == "09bbbb0842b0f92c214d5e868ec3fe5e2d047f9de7b5c3e6d620bc147092f6f3"


def test_receipt_cannot_claim_partial_pagination_authority_even_with_rehashed_receipt():
    root = Path(__file__).resolve().parents[1]
    receipt = json.loads((root / audit.RECEIPT_PATH).read_text(encoding="utf-8"))
    receipt["runtime_wrapper"]["pagination_complete_required"] = False
    receipt["canonical_sha256"] = _canonical_sha(receipt)
    with pytest.raises(audit.PcUpcomingRuntimeMigrationAuditError, match="completeness contract drifted"):
        audit.validate_receipt(receipt)


def test_historical_source_audit_is_superseded_only_by_exact_migration_receipt():
    from scripts import audit_post_p4_4l_pc_upcoming_shared_football_source as source_audit
    from scripts import audit_post_p4_4l_international_provider_family_bridge as bridge_audit

    root = Path(__file__).resolve().parents[1]
    source_result = source_audit.audit(root)
    bridge_result = bridge_audit.audit(root)
    assert source_result["historical_candidate_receipt_unchanged"] is True
    assert source_result["runtime_owner_superseded_by_reviewed_migration"] is True
    assert bridge_result["runtime_migration_receipt_sha256"] == source_result["runtime_migration_receipt_sha256"]
