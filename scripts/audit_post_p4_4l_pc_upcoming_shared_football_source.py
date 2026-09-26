"""Offline audit for the evidence-only pcUpcomingEvents source contract."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from domain import current_shadow_sportybet_pc_upcoming_discovery as pc

RECEIPT_PATH = Path("artifacts/architecture/post_p4_4l_pc_upcoming_shared_football_source_v1.json")
EXPECTED_PAGE_ANCHORS = (
    {
        "page_num": 1,
        "request_target": "/api/ng/factsCenter/pcUpcomingEvents?sportId=sr%3Asport%3A1&marketId=1&pageSize=100&pageNum=1&todayGames=false&timeline=48&_t=1790371922118",
        "http_status": 200,
        "response_completed_utc": "2026-09-25T21:32:56.419Z",
        "raw_bytes": 206280,
        "raw_sha256": "4db55291edf5f1cee3c2348aad4dd1ba5e59c6448d785a8154e70b37539e7367",
        "bizCode": 10000,
        "totalNum": 1148,
        "tournament_count": 15,
        "event_count": 100,
    },
    {
        "page_num": 2,
        "request_target": "/api/ng/factsCenter/pcUpcomingEvents?sportId=sr%3Asport%3A1&marketId=1&pageSize=100&pageNum=2&todayGames=false&timeline=48&_t=1790371985712",
        "http_status": 200,
        "response_completed_utc": "2026-09-25T21:33:48.923Z",
        "raw_bytes": 200718,
        "raw_sha256": "8cf628647aaff4c9711545361a7b7c48773052b88b2122bfc7af8d009a9dcd6a",
        "bizCode": 10000,
        "totalNum": 1148,
        "tournament_count": 15,
        "event_count": 100,
    },
    {
        "page_num": 3,
        "request_target": "/api/ng/factsCenter/pcUpcomingEvents?sportId=sr%3Asport%3A1&marketId=1&pageSize=100&pageNum=3&todayGames=false&timeline=48&_t=1790372038297",
        "http_status": 200,
        "response_completed_utc": "2026-09-25T21:34:38.553Z",
        "raw_bytes": 200230,
        "raw_sha256": "7426e8b3813461b9de625d9d796f542d9ca06bc5220f4079b9a41b949df8a88b",
        "bizCode": 10000,
        "totalNum": 1148,
        "tournament_count": 14,
        "event_count": 100,
    },
)
EXPECTED_FAMILIES = (
    ("CLUB", "sr:category:26", "USA", "sr:tournament:242", "MLS", 14),
    ("INTERNATIONAL", "sr:category:4", "International", "sr:tournament:23755", "UEFA Nations League", 18),
    ("INTERNATIONAL", "sr:category:4", "International", "sr:tournament:1848", "Africa Cup of Nations Qualification", 2),
    ("INTERNATIONAL", "sr:category:4", "International", "sr:tournament:851", "Int. Friendly Games", 7),
    ("INTERNATIONAL", "sr:category:4", "International", "sr:tournament:27420", "CONCACAF Nations League", 9),
)


class PcUpcomingSourceAuditError(ValueError):
    """Raised when the source receipt or runtime boundaries drift."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PcUpcomingSourceAuditError(message)


def validate_receipt(receipt: Any) -> str:
    _require(type(receipt) is dict, "architecture receipt must be an object")
    embedded = receipt.get("canonical_sha256")
    _require(type(embedded) is str and len(embedded) == 64, "receipt canonical SHA is missing")
    semantic = dict(receipt)
    semantic.pop("canonical_sha256", None)
    actual = hashlib.sha256(_canonical(semantic)).hexdigest()
    _require(actual == embedded, "architecture receipt canonical SHA mismatch")
    _require(receipt.get("schema_version") == 1, "receipt schema version drifted")
    _require(receipt.get("policy_id") == pc.POLICY_ID, "receipt policy ID drifted")
    _require(receipt.get("policy_sha256") == pc.PINNED_POLICY_SHA256 == pc.calculate_policy_sha256(), "receipt policy SHA drifted")
    _require(receipt.get("repository") == "Thabearr/ATHENA", "receipt repository identity drifted")
    _require(receipt.get("base_main_sha") == pc.P4_4_BASE_MAIN, "receipt base main drifted")
    _require(receipt.get("issue_337_diagnostic_evidence_comment_id") == pc.DIAGNOSTIC_ISSUE_COMMENT_ID, "receipt diagnostic evidence comment drifted")

    source = receipt.get("source_contract")
    _require(type(source) is dict, "source contract evidence missing")
    _require(source.get("endpoint_path") == pc.SOURCE_PATH, "candidate endpoint path drifted")
    _require(source.get("endpoint_path") not in source.get("not_endpoint_path", []), "candidate endpoint aliases another source")
    _require(set(source.get("not_endpoint_path", [])) == {"/api/ng/factsCenter/pc/upcomingEvents", "/api/ng/factsCenter/wapConfigurableUpcomingEvents"}, "endpoint distinction drifted")
    _require(source.get("runtime_owner_status") == "EVIDENCE_QUALIFIED_CANDIDATE_NOT_RUNTIME_OWNER", "candidate was promoted")
    _require(source.get("origin") == pc.ORIGIN and source.get("source_method") == pc.SOURCE_METHOD, "candidate provider source identity drifted")
    _require(source.get("request_headers") == dict(pc.REQUEST_HEADERS) and source.get("anonymous_no_cookie_or_authorization") is True, "anonymous request headers or safety drifted")
    _require(source.get("coverage_horizon_hours") == pc.TIMELINE_HOURS and source.get("market_filter") == 1, "source query scope drifted")
    _require(source.get("fixed_query") == {
        "sportId": pc.FOOTBALL_SPORT_ID,
        "marketId": 1,
        "pageSize": pc.PAGE_SIZE,
        "pageNum": "1-through-20-positive-integer",
        "todayGames": False,
        "timeline": pc.TIMELINE_HOURS,
        "_t": "response-scoped-positive-epoch-millisecond-request-nonce",
    }, "fixed query semantics drifted")

    pages = receipt.get("diagnostic_pages")
    _require(type(pages) is list and tuple(pages) == EXPECTED_PAGE_ANCHORS, "diagnostic raw page identities/hashes drifted")
    diagnostic = receipt.get("diagnostic_capture_assessment")
    _require(type(diagnostic) is dict, "diagnostic assessment missing")
    _require(diagnostic.get("captured_event_count") == 300 and diagnostic.get("unique_event_count_across_pages") == 300, "captured page event counts drifted")
    _require(diagnostic.get("provider_totalNum") == 1148, "provider totalNum drifted")
    _require(diagnostic.get("match_status_absent_rows") == 20 and diagnostic.get("match_status_absent_rows_by_page") == {"1": 1, "2": 17, "3": 2}, "observed missing matchStatus rows drifted")
    _require(diagnostic.get("missing_match_status_treatment") == "PRESERVED_NULL_NOT_INFERRED_AND_NOT_PREMATCH_BOOKABLE", "missing matchStatus handling is not fail-closed")
    _require(diagnostic.get("pagination_complete") is False and diagnostic.get("pagination_exhausted_in_diagnostic") is False, "diagnostic falsely claims complete pagination")
    _require(diagnostic.get("global_page_integrity") == "PASS", "global page integrity evidence missing")
    _require(diagnostic.get("page_1_contains_club_and_international") is True, "shared page-1 coverage evidence missing")
    deviation = diagnostic.get("protocol_deviation")
    _require(type(deviation) is dict and deviation.get("pages_2_and_3_unnecessary_under_original_stop_rule") is True and deviation.get("maximum_request_count_exceeded") is False and deviation.get("retry_count") == 0, "diagnostic protocol deviation not truthfully bound")

    families = receipt.get("observed_provider_families")
    _require(type(families) is list, "provider family observations missing")
    observed_keys = tuple((row.get("scope_observed"), row.get("category_id"), row.get("category_name"), row.get("tournament_id"), row.get("tournament_name"), row.get("page_1_event_count", row.get("page_1_future_prematch_event_count"))) for row in families[:5])
    _require(observed_keys == EXPECTED_FAMILIES, "observed club/international provider identities drifted")
    _require(len(families) == 6 and families[5].get("tournament_id") == "sr:tournament:622" and families[5].get("athena_source_family_mapping_added") is False, "Gulf Cup observation must not become a source mapping")
    _require(all(row.get("athena_source_family_mapping_added") is False for row in families), "receipt grants an unreviewed source/provider mapping")

    detail = receipt.get("direct_event_confirmation")
    _require(type(detail) is dict, "direct event evidence missing")
    expected_detail = {
        "event_id": "sr:match:73220868",
        "request_target": "/api/ng/factsCenter/event?productId=3&eventId=sr%3Amatch%3A73220868",
        "http_status": 200,
        "response_completed_utc": "2026-09-25T21:36:26.617Z",
        "raw_bytes": 188113,
        "raw_sha256": "cfbe9cd146a61c6c66975bfdf311d489b1ecebe54f27a9b4f3b663f03c35fc8e",
        "bizCode": 10000,
        "confirmation_result": "PASS",
        "home_team_id": "sr:competitor:21808",
        "home_team_name": "Barbados",
        "away_team_id": "sr:competitor:21820",
        "away_team_name": "Saint Lucia",
        "estimate_start_time_utc": "2026-09-26T00:00:00Z",
        "match_status": "Not start",
        "booking_status": "Booked",
        "category_id": "sr:category:4",
        "category_name": "International",
        "tournament_id": "sr:tournament:27420",
        "tournament_name": "CONCACAF Nations League",
        "market_count": 195,
    }
    _require(detail == expected_detail, "direct event confirmation identity/hash drifted")

    accounting = receipt.get("diagnostic_authorization")
    _require(type(accounting) is dict and accounting.get("authorization_consumed") is True and accounting.get("request_count") == accounting.get("maximum_requests") == 4 and accounting.get("retry_count") == 0, "diagnostic request authorization accounting drifted")
    governance = receipt.get("runtime_and_governance")
    _require(type(governance) is dict, "runtime/governance evidence missing")
    exact_false = (
        "current_shadow_runtime_owner_changed", "p3_runtime_owner_changed", "paginated_runtime_reconciliation_authority",
        "catalog_fanout_runtime_authority", "international_provider_family_mapping_added", "provider_acquisition_during_implementation",
        "provider_absence_authority",
        "workflow_dispatch_during_implementation", "model_authority", "pricing_authority", "router_authority", "portfolio_authority",
        "share_code_authority", "login", "cookies", "wallet", "staking", "bet", "wager_placed", "next_live_proof_authorized",
    )
    _require(governance.get("old_current_shadow_runtime_owner") == "ATHENA_CURRENT_SHADOW_UPCOMING_DISCOVERY_V1", "old Current Shadow source identity changed")
    _require(all(governance.get(key) is False for key in exact_false), "runtime or downstream authority was broadened")
    _require(governance.get("provider_request_count_during_implementation") == 0 and governance.get("workflow_dispatch_count_during_implementation") == 0, "implementation performed provider/workflow actions")
    _require(governance.get("source_review_counter_while_unmerged") == "0/5" and governance.get("source_review_counter_if_merged") == "1/5", "source review counter drifted")
    _require(governance.get("p4_4_complete") is False and governance.get("architecture_checkpoint_e_complete") is False, "phase completion was overclaimed")
    return embedded


def audit(repository_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(repository_root) if repository_root is not None else Path(__file__).resolve().parents[1]
    receipt_path = root / RECEIPT_PATH
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PcUpcomingSourceAuditError("architecture receipt is unavailable or malformed") from exc
    receipt_sha = validate_receipt(receipt)

    # The old receipt above remains the immutable candidate-not-runtime record.
    # Current ownership may change only through the separately pinned migration
    # receipt and audit, never by relaxing this source receipt's checks.
    from scripts import audit_post_p4_4l_pc_upcoming_runtime_migration as migration
    supersession = migration.audit(root)
    _require(supersession.get("status") == "PASSED", "reviewed runtime supersession is not authenticated")
    return {
        "status": "PASSED",
        "policy_id": pc.POLICY_ID,
        "policy_sha256": pc.calculate_policy_sha256(),
        "receipt_canonical_sha256": receipt_sha,
        "historical_candidate_receipt_unchanged": True,
        "runtime_owner_superseded_by_reviewed_migration": True,
        "paginated_runtime_authority_false": True,
        "fanout_runtime_authority_false": True,
        "fanout_global_echo_rejected": True,
        "runtime_migration_receipt_sha256": supersession["migration_receipt_sha256"],
        "network_used": False,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True))
