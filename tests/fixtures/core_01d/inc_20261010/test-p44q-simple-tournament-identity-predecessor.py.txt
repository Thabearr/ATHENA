"""Acceptance regressions and provenance tests for P4.4Q simple-tournament provider identity admission."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import copy
from pathlib import Path

import pytest

from domain import current_shadow_sportybet_pc_upcoming_discovery as source
from domain import current_shadow_sportybet_pc_upcoming_reconciliation as runtime
from domain import current_shadow_sportybet_international_provider_family_bridge as bridge
from domain import current_shadow_fixture_identity_v2 as identity_v2
from domain import current_shadow_fixture_identity_compatibility as identity_compatibility
from scripts import audit_p4_4q_pc_upcoming_simple_tournament_identity as audit

OBSERVED = datetime(2026, 9, 25, 21, 32, 56, 419000, tzinfo=timezone.utc)
OBSERVED_MS = int(OBSERVED.timestamp() * 1000)


def _synthetic_event_row(
    index: int,
    *,
    event_id: str | None = None,
    home_name: str | None = None,
    nested_sport: dict | None = None,
) -> dict:
    kickoff_ms = int(datetime(2026, 9, 26, 0, 0, tzinfo=timezone.utc).timestamp() * 1000) + index
    row: dict = {
        "eventId": event_id or f"sr:match:{7000000 + index}",
        "homeTeamId": f"sr:competitor:{8000000 + index * 2}",
        "homeTeamName": home_name or f"Home Team {index}",
        "awayTeamId": f"sr:competitor:{8000001 + index * 2}",
        "awayTeamName": f"Away Team {index}",
        "estimateStartTime": kickoff_ms,
        "status": 0,
        "matchStatus": "Not start",
        "bookingStatus": "Booked",
    }
    if nested_sport is not None:
        row["sport"] = nested_sport
    return row


def _page_bytes(
    total: int,
    tournaments: list[dict],
) -> bytes:
    payload = {
        "bizCode": 10000,
        "data": {
            "totalNum": total,
            "tournaments": tournaments,
        },
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _page(page_num: int, raw: bytes) -> source.PcUpcomingPageEvidence:
    observed = OBSERVED.replace(microsecond=419000 + page_num)
    nonce = int(observed.timestamp() * 1000) - 500
    return source.parse_page(raw, page_num=page_num, request_nonce_ms=nonce, observed_at=observed)


# ======================================================================
# Case A: nested exact namespace agreement passes
# ======================================================================
def test_case_a_nested_exact_namespace_agreement_passes() -> None:
    nested_sport = {
        "id": "sr:sport:1",
        "category": {
            "id": "sr:category:131",
            "name": "Wales",
            "tournament": {
                "id": "sr:simple_tournament:11141",
                "name": "Premier League, Women",
            },
        },
    }
    event_row = _synthetic_event_row(1, nested_sport=nested_sport)
    tournament_row = {
        "id": "sr:simple_tournament:11141",
        "name": "Premier League, Women",
        "categoryId": "sr:category:131",
        "categoryName": "Wales",
        "events": [event_row],
    }
    raw = _page_bytes(1, [tournament_row])
    page = _page(1, raw)
    assert page.total_num == 1
    assert page.event_count == 1
    event = page.events[0]
    assert event.tournament_id == "sr:simple_tournament:11141"
    assert event.tournament_name == "Premier League, Women"
    assert event.category_id == "sr:category:131"
    assert event.category_name == "Wales"


# ======================================================================
# Case B: same numeric tail but namespace mismatch fails
# outer: sr:simple_tournament:11141, nested: sr:tournament:11141
# ======================================================================
def test_case_b_same_numeric_tail_namespace_mismatch_fails() -> None:
    nested_sport = {
        "id": "sr:sport:1",
        "category": {
            "id": "sr:category:131",
            "name": "Wales",
            "tournament": {
                "id": "sr:tournament:11141",
                "name": "Premier League, Women",
            },
        },
    }
    event_row = _synthetic_event_row(1, nested_sport=nested_sport)
    tournament_row = {
        "id": "sr:simple_tournament:11141",
        "name": "Premier League, Women",
        "categoryId": "sr:category:131",
        "categoryName": "Wales",
        "events": [event_row],
    }
    raw = _page_bytes(1, [tournament_row])
    with pytest.raises(source.PcUpcomingDiscoveryError, match="event tournament ancestry conflicts with wrapper"):
        _page(1, raw)


# ======================================================================
# Case C: reverse namespace mismatch fails
# outer: sr:tournament:11141, nested: sr:simple_tournament:11141
# ======================================================================
def test_case_c_reverse_namespace_mismatch_fails() -> None:
    nested_sport = {
        "id": "sr:sport:1",
        "category": {
            "id": "sr:category:131",
            "name": "Wales",
            "tournament": {
                "id": "sr:simple_tournament:11141",
                "name": "Premier League, Women",
            },
        },
    }
    event_row = _synthetic_event_row(1, nested_sport=nested_sport)
    tournament_row = {
        "id": "sr:tournament:11141",
        "name": "Premier League, Women",
        "categoryId": "sr:category:131",
        "categoryName": "Wales",
        "events": [event_row],
    }
    raw = _page_bytes(1, [tournament_row])
    with pytest.raises(source.PcUpcomingDiscoveryError, match="event tournament ancestry conflicts with wrapper"):
        _page(1, raw)


# ======================================================================
# Case D: deterministic source policy payload binds ALL four provider ID regex objects
# ======================================================================
def test_case_d_deterministic_source_policy_payload_binds_all_four_provider_id_regexes() -> None:
    payload = source.policy_payload()
    assert "provider_native_id_grammar" in payload
    grammar = payload["provider_native_id_grammar"]

    assert grammar["event"] == source._EVENT_ID_RE.pattern
    assert grammar["competitor"] == source._COMPETITOR_ID_RE.pattern
    assert grammar["category"] == source._CATEGORY_ID_RE.pattern
    assert grammar["tournament"] == source._TOURNAMENT_ID_RE.pattern

    assert grammar["event"] == "^sr:match:([1-9][0-9]*)$"
    assert grammar["competitor"] == "^sr:competitor:([1-9][0-9]*)$"
    assert grammar["category"] == "^sr:category:([1-9][0-9]*)$"
    assert grammar["tournament"] == "^sr:(?:tournament|simple_tournament):([1-9][0-9]*)$"

    assert grammar["exact_string_only"] is True
    assert grammar["normalization"] == "NONE"
    assert grammar["coercion"] is False
    assert grammar["tournament_namespace_rewrite"] is False


# ======================================================================
# Case E: stable-total synthetic multi-page capture containing simple_tournament completes
# ======================================================================
def test_case_e_stable_total_synthetic_multipage_capture_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path.resolve()
    root.mkdir(parents=True, exist_ok=True)

    # 2 pages: page 1 has 100 events, page 2 has 50 events. Total = 150.
    total = 150
    p1_events = [_synthetic_event_row(i) for i in range(1, 101)]
    p2_events = [_synthetic_event_row(i) for i in range(101, 151)]

    p1_tournament = {
        "id": "sr:simple_tournament:11141",
        "name": "Premier League, Women",
        "categoryId": "sr:category:131",
        "categoryName": "Wales",
        "events": p1_events,
    }
    p2_tournament = {
        "id": "sr:simple_tournament:11141",
        "name": "Premier League, Women",
        "categoryId": "sr:category:131",
        "categoryName": "Wales",
        "events": p2_events,
    }

    raw_p1 = _page_bytes(total, [p1_tournament])
    raw_p2 = _page_bytes(total, [p2_tournament])
    raw_pages = [raw_p1, raw_p2]

    def fetch(page_num: int, nonce: int):
        return raw_pages[page_num - 1], datetime.now(timezone.utc)

    monkeypatch.setattr(source, "_fetch_page", fetch)

    evidence_path, manifest = runtime.capture_current_pc_upcoming_discovery(
        repository_root=root,
        execute_live_network=True,
    )
    assert manifest.pagination_complete is True
    assert manifest.captured_event_count == total
    assert manifest.provider_total_num == total
    assert manifest.captured_page_count == 2
    assert tuple(page.page_num for page in manifest.pages) == (1, 2)

    all_events = manifest.events
    assert len(all_events) == 150
    for event in all_events:
        assert event.tournament_id == "sr:simple_tournament:11141"
        assert event.tournament_name == "Premier League, Women"

    projection_bytes = source.provider_identity_projection_bytes(manifest)
    assert b"sr:simple_tournament:11141" in projection_bytes


# ======================================================================
# Case F: no bridge mapping for 11141
# ======================================================================
def test_case_f_no_bridge_mapping_for_simple_tournament_11141() -> None:
    mapping = bridge.mapping_for_exact_pair(
        source_ccode="INT",
        source_primary_id=11141,
        provider_category_id="sr:category:131",
        provider_category_name="Wales",
        provider_tournament_id="sr:simple_tournament:11141",
        provider_tournament_name="Premier League, Women",
    )
    assert mapping is None
    assert bridge.provider_pair_is_reviewed_international_family(
        "sr:category:131", "sr:simple_tournament:11141"
    ) is False
    assert bridge.classify_source_provider_family(
        source_ccode="INT",
        source_primary_id=11141,
        provider_category_id="sr:category:131",
        provider_category_name="Wales",
        provider_tournament_id="sr:simple_tournament:11141",
        provider_tournament_name="Premier League, Women",
    ) is bridge.InternationalProviderFamilyClassification.NOT_APPLICABLE


# ======================================================================
# Case G: P4.4P negative evidence preservation remains valid
# ======================================================================
@pytest.mark.parametrize(
    "invalid_tournament_id",
    [
        "not-provider-native",
        "sr:competition:11141",
        "sr:simple_tournament:0",
    ],
)
def test_case_g_negative_evidence_preservation_rejects_invalid_namespace(
    invalid_tournament_id: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path.resolve()
    root.mkdir(parents=True, exist_ok=True)

    event_row = _synthetic_event_row(1)
    tournament_row = {
        "id": invalid_tournament_id,
        "name": "Invalid League",
        "categoryId": "sr:category:131",
        "categoryName": "Wales",
        "events": [event_row],
    }
    raw = _page_bytes(1, [tournament_row])
    raw_hash = hashlib.sha256(raw).hexdigest()

    def fetch(page_num: int, nonce: int):
        return raw, datetime.now(timezone.utc)

    monkeypatch.setattr(source, "_fetch_page", fetch)

    with pytest.raises(runtime.PcUpcomingRuntimeReconciliationError, match="PC_UPCOMING_RUNTIME_SOURCE_INCOMPLETE"):
        runtime.capture_current_pc_upcoming_discovery(
            repository_root=root,
            execute_live_network=True,
        )

    evidence_root = root / source.EVIDENCE_ROOT
    attempt = evidence_root / runtime.RUNTIME_ATTEMPTS_DIRECTORY / "attempt-001"
    journal = json.loads((attempt / runtime.RAW_RESPONSE_JOURNAL_FILENAME).read_text(encoding="utf-8"))
    rows = journal["responses"]
    assert len(rows) == 1
    page1 = attempt / rows[0]["raw_relative_path"]
    assert page1.exists(), "raw response bytes must be persisted before parse failure"
    assert page1.read_bytes() == raw
    assert hashlib.sha256(page1.read_bytes()).hexdigest() == rows[0]["raw_sha256"] == raw_hash

    parse_failure_path = attempt / runtime.PARSE_FAILURE_FILENAME
    assert parse_failure_path.exists(), "parse-failure receipt must be generated"
    parse_failure_doc = json.loads(parse_failure_path.read_text(encoding="utf-8"))
    assert parse_failure_doc["raw_sha256"] == raw_hash
    assert parse_failure_doc["page_num"] == 1
    assert parse_failure_doc["attempt_index"] == 1
    assert parse_failure_doc["semantic_acceptance"] is False
    assert parse_failure_doc["provider_absence_authority"] is False
    assert parse_failure_doc["reconciliation_authority"] is False

    assert not (attempt / "manifest.json").exists(), "no attempt manifest may be written after parse failure"
    assert not (evidence_root / "manifest.json").exists(), "no accepted manifest may be written after parse failure"

    stabilization_path = evidence_root / runtime.STABILIZATION_RECEIPT_FILENAME
    assert stabilization_path.exists()
    stabilization_doc = json.loads(stabilization_path.read_text(encoding="utf-8"))
    assert stabilization_doc["attempt_count"] == 1, "non-totalNum parse failure must not start epoch 2"
    assert not (evidence_root / runtime.RUNTIME_ATTEMPTS_DIRECTORY / "attempt-002").exists()

    for auth_key, auth_val in runtime.AUTHORITY.items():
        if auth_key in {"model", "pricing", "router", "portfolio", "login", "cookies", "wallet", "staking", "bet", "wager_placed"}:
            assert auth_val is False, f"authority {auth_key} must be False"


# ======================================================================
# Blocker B Specific Acceptance Tests (Items 1-7)
# ======================================================================

def test_acceptance_item_1_reconstructed_observed_wrapper_identity_is_accepted() -> None:
    """Synthetic offline reconstruction accepts the exact observed wrapper/category/tournament identity.

    This is not byte-for-byte replay of the preserved live page-7 response.
    """
    tournament_row = {
        "id": "sr:simple_tournament:11141",
        "name": "Premier League, Women",
        "categoryId": "sr:category:131",
        "categoryName": "Wales",
        "events": [
            _synthetic_event_row(
                1,
                nested_sport={
                    "id": "sr:sport:1",
                    "category": {
                        "id": "sr:category:131",
                        "name": "Wales",
                        "tournament": {
                            "id": "sr:simple_tournament:11141",
                            "name": "Premier League, Women",
                        },
                    },
                },
            )
        ],
    }
    raw = _page_bytes(1, [tournament_row])
    page = _page(7, raw)
    assert page.page_num == 7
    assert len(page.events) == 1
    assert page.events[0].tournament_id == "sr:simple_tournament:11141"


@pytest.mark.parametrize(
    "valid_id",
    [
        "sr:simple_tournament:1",
        "sr:simple_tournament:11141",
        "sr:simple_tournament:999999999",
    ],
)
def test_acceptance_item_2_simple_tournament_valid_variants(valid_id: str) -> None:
    """Item 2: Valid simple tournament IDs admitted."""
    tournament_row = {
        "id": valid_id,
        "name": "Valid Tournament",
        "categoryId": "sr:category:1",
        "categoryName": "Category",
        "events": [
            _synthetic_event_row(
                1,
                nested_sport={
                    "id": "sr:sport:1",
                    "category": {
                        "id": "sr:category:1",
                        "name": "Category",
                        "tournament": {
                            "id": valid_id,
                            "name": "Valid Tournament",
                        },
                    },
                },
            )
        ],
    }
    raw = _page_bytes(1, [tournament_row])
    page = _page(1, raw)
    assert page.events[0].tournament_id == valid_id


@pytest.mark.parametrize(
    "invalid_id",
    [
        "sr:simple_tournament:0",
        "sr:simple_tournament:01",
        "sr:simple_tournament:abc",
        "sr:simple_tournament:",
        "simple_tournament:1",
        "sr:tournament:0",
        "sr:simple-tournament:1",
        "sr:simple_tournament: 1",
        "sr:simple_tournament:1 ",
        "sr:simple_tournament:1\n",
    ],
)
def test_acceptance_item_3_simple_tournament_invalid_variants_rejected(invalid_id: str) -> None:
    """Item 3: Invalid simple tournament variants rejected."""
    tournament_row = {
        "id": invalid_id,
        "name": "Invalid Tournament",
        "categoryId": "sr:category:1",
        "categoryName": "Category",
        "events": [
            _synthetic_event_row(
                1,
                nested_sport={
                    "id": "sr:sport:1",
                    "category": {
                        "id": "sr:category:1",
                        "name": "Category",
                        "tournament": {
                            "id": invalid_id,
                            "name": "Invalid Tournament",
                        },
                    },
                },
            )
        ],
    }
    raw = _page_bytes(1, [tournament_row])
    with pytest.raises(source.PcUpcomingDiscoveryError):
        _page(1, raw)


def test_acceptance_item_4_raw_preserved_without_rewrite_or_trim() -> None:
    """Item 4: Raw provider-native string is preserved without namespace rewrite or trim."""
    raw_tid = "sr:simple_tournament:11141"
    tournament_row = {
        "id": raw_tid,
        "name": "Premier League, Women",
        "categoryId": "sr:category:131",
        "categoryName": "Wales",
        "events": [
            _synthetic_event_row(
                1,
                nested_sport={
                    "id": "sr:sport:1",
                    "category": {
                        "id": "sr:category:131",
                        "name": "Wales",
                        "tournament": {
                            "id": raw_tid,
                            "name": "Premier League, Women",
                        },
                    },
                },
            )
        ],
    }
    raw = _page_bytes(1, [tournament_row])
    page = _page(1, raw)
    event = page.events[0]
    assert event.tournament_id == "sr:simple_tournament:11141"
    assert "sr:tournament" not in event.tournament_id
    assert event.tournament_id == raw_tid


def test_acceptance_item_5_no_simple_tournament_competition_mappings_in_v2() -> None:
    """Item 5: domain/current_shadow_fixture_identity_v2.py does not contain any simple-tournament competition mappings."""
    v2_content = Path("domain/current_shadow_fixture_identity_v2.py").read_text(encoding="utf-8")
    assert "sr:simple_tournament" not in v2_content
    assert bridge.provider_pair_is_reviewed_international_family("sr:category:131", "sr:simple_tournament:11141") is False


def test_acceptance_item_6_fixture_reconciliation_unmapped_behavior() -> None:
    """Item 6: Simple tournament with no competition mapping reconciles as unmapped without synthetic mapping or silent drop."""
    # When no mapping exists in bridge, classify returns NOT_APPLICABLE and mapping is None
    mapping = bridge.mapping_for_exact_pair(
        source_ccode="INT",
        source_primary_id=11141,
        provider_category_id="sr:category:131",
        provider_category_name="Wales",
        provider_tournament_id="sr:simple_tournament:11141",
        provider_tournament_name="Premier League, Women",
    )
    assert mapping is None
    # No fallback or synthetic mapping is generated
    assert bridge.provider_pair_is_reviewed_international_family("sr:category:131", "sr:simple_tournament:11141") is False


def test_acceptance_item_7_recovery_and_negative_evidence_interaction() -> None:
    """Item 7: P4.4O stable-epoch recovery and P4.4P pre-parse response evidence remain active."""
    # Source policy retains strict capture stabilization policy
    runtime_payload = runtime._policy_payload()
    stabilization = runtime_payload["capture_stabilization"]
    assert stabilization["recovery_semantics"] == "FRESH_CAPTURE_EPOCH_AFTER_EXACT_CROSS_PAGE_TOTALNUM_DRIFT"
    assert stabilization["max_capture_epochs"] == 2
    assert stabilization["no_third_capture_epoch"] is True
    assert stabilization["no_per_page_http_retry"] is True

    preparse = runtime_payload["preparse_response_evidence"]
    assert preparse["every_successful_runtime_http_response_persisted_before_semantic_parse"] is True
    assert preparse["raw_response_bytes_written_exclusively"] is True
    assert preparse["parse_failure_receipt_binds_exact_raw_response_sha"] is True
    assert preparse["parse_failure_semantic_acceptance"] is False
    assert "source_v1_acceptance_unchanged" not in preparse
    assert preparse["source_acceptance_semantics_owned_by_bound_source_policy"] is True
    assert preparse["preparse_evidence_mechanics_unchanged"] is True


# ======================================================================
# Additional acceptance: Pinned policy hashes and receipts are validated
# ======================================================================
def test_all_pinned_policy_hashes_and_receipts_are_validated() -> None:
    source_payload = source.policy_payload()
    assert source.calculate_policy_sha256() == source.PINNED_POLICY_SHA256 == "306e9b37bb749032cae48be100ae7b49f1221fcf3392373a2e2407a8b3c339f5"

    runtime_payload = runtime._policy_payload()
    assert runtime.calculate_policy_sha256() == runtime.PINNED_POLICY_SHA256 == "3cf597440422433e7c7e2246d33de4ece22e55395218f8bc2eb8950a361dd68a"

    assert bridge.calculate_policy_sha256() == bridge.PINNED_POLICY_SHA256 == "c3f05e5ea6ce08c392ec13d1b39d40dd8dd177e5a73f3660605c359705719858"
    assert identity_v2.REGISTRY_SHA256 == identity_v2.registry_sha256() == "149b7b61213e33ee85f030d3e567966e5f79df6bea4e138d54d638c76d5e8156"
    assert identity_v2.SEED_REGISTRY_SHA256 == identity_v2.seed_registry_sha256() == "7fe662fc91a80daabf1e774ddd5c8ecdb5215eaf63adb03822b3fb05f872df79"
    assert identity_compatibility.calculate_policy_sha256() == identity_compatibility.EXPECTED_POLICY_SHA256 == "e8587d1e99cb7aa6214f65b515ca59f1456443a554a762ba27be204506da7569"

    audit_result = audit.audit()
    assert audit_result["status"] == "PASSED"
    assert audit_result["receipt_sha256"] == "24ac836152c945754620bdd15f9c9436cc686e550b65127c88895902ddaebebe"


def test_provenance_audit_rejects_resealed_tampered_source_ancestry_link() -> None:
    root = Path(".")
    source_receipt = audit._read_json(root, audit.SOURCE_RECEIPT_PATH)
    bridge_receipt = audit._read_json(root, audit.BRIDGE_RECEIPT_PATH)
    historical_source_receipt = audit._read_json(root, audit.HISTORICAL_SOURCE_RECEIPT_PATH)
    audit._verify_source_ancestry(source_receipt, bridge_receipt, historical_source_receipt)

    tampered_bridge = copy.deepcopy(bridge_receipt)
    tampered_bridge["provider_source_authority"]["supersession_receipt_sha256"] = "0" * 64
    semantic = dict(tampered_bridge)
    semantic.pop("canonical_sha256")
    tampered_bridge["canonical_sha256"] = hashlib.sha256(audit._canonical(semantic)).hexdigest()

    with pytest.raises(audit.P44QError, match="bridge provider-source authority receipt ancestry drifted"):
        audit._verify_source_ancestry(source_receipt, tampered_bridge, historical_source_receipt)

