from __future__ import annotations

from collections import Counter
from pathlib import Path

from domain.fotmob_fixture_candidate_review import FixtureCandidateReviewDisposition
from scripts.manage_fotmob_reviewed_fixture_catalog import load_review_decision_ledger
from scripts.verify_saturday_2026_08_22_fixture_identity_review import (
    EXPECTED_APPROVED_COUNT,
    EXPECTED_CANDIDATE_BUNDLE_SHA256,
    EXPECTED_CANDIDATE_COUNT,
    EXPECTED_COMPETITION_COUNTS,
    EXPECTED_DECISION_LEDGER_SHA256,
    EXPECTED_MANIFEST_SHA256,
    EXPECTED_RAW_SHA256,
    EXPECTED_REVIEWER_REFERENCE,
    EXPECTED_UNREVIEWED_COUNT,
)


LEDGER = Path("evidence/saturday_2026_08_22_fixture_identity_review_decisions.json")


def test_explicit_review_ledger_is_exact_and_complete_for_the_50_fixture_pool():
    decisions, ledger_sha256 = load_review_decision_ledger(
        LEDGER,
        expected_candidate_bundle_sha256=EXPECTED_CANDIDATE_BUNDLE_SHA256,
    )

    assert ledger_sha256 == EXPECTED_DECISION_LEDGER_SHA256
    assert EXPECTED_CANDIDATE_COUNT == 670
    assert EXPECTED_APPROVED_COUNT == 50
    assert EXPECTED_UNREVIEWED_COUNT == 620
    assert len(decisions) == EXPECTED_APPROVED_COUNT
    assert len({item.source_match_id for item in decisions}) == EXPECTED_APPROVED_COUNT
    assert all(
        item.disposition is FixtureCandidateReviewDisposition.APPROVED
        for item in decisions
    )
    assert all(
        item.source_capture_manifest_sha256 == EXPECTED_MANIFEST_SHA256
        for item in decisions
    )
    assert all(
        item.reviewer_reference == EXPECTED_REVIEWER_REFERENCE
        for item in decisions
    )
    assert all(
        item.reviewed_at.isoformat().replace("+00:00", "Z")
        == "2026-08-21T07:26:00Z"
        for item in decisions
    )


def test_explicit_review_ledger_preserves_the_reviewed_competition_distribution():
    decisions, _ = load_review_decision_ledger(
        LEDGER,
        expected_candidate_bundle_sha256=EXPECTED_CANDIDATE_BUNDLE_SHA256,
    )
    expected_notes = {
        f"Saturday rank {rank} {competition}; identity only.": count
        for competition, rank, count in (
            ("Premier League", 1, 5),
            ("La Liga", 2, 3),
            ("Serie A", 3, 4),
            ("Ligue 1", 5, 5),
            ("Primeira Liga", 6, 3),
            ("Süper Lig", 7, 3),
            ("Eredivisie", 8, 4),
            ("DFB-Pokal", 9, 11),
            ("Belgian Pro League", 10, 3),
            ("Scottish Premiership", 11, 6),
            ("Greek Super League", 12, 3),
        )
    }
    assert Counter(item.notes for item in decisions) == expected_notes
    assert sum(EXPECTED_COMPETITION_COUNTS.values()) == EXPECTED_APPROVED_COUNT
    assert EXPECTED_COMPETITION_COUNTS == {
        "Belgian Pro League": 3,
        "DFB-Pokal": 11,
        "Eredivisie": 4,
        "Greek Super League": 3,
        "La Liga": 3,
        "Ligue 1": 5,
        "Premier League": 5,
        "Primeira Liga": 3,
        "Scottish Premiership": 6,
        "Serie A": 4,
        "Süper Lig": 3,
    }


def test_review_contract_remains_identity_only_and_pins_exact_pr199_bytes():
    assert EXPECTED_RAW_SHA256 == (
        "a22e449fd7c59bee011e71230e345c733e1322311f6a9481812a23b4dcae2dc8"
    )
    assert EXPECTED_MANIFEST_SHA256 == (
        "64fb631d4889dbf360af4fb988656aba579b67ca5340578df1056dc5324dc09e"
    )
    script = Path(
        "scripts/verify_saturday_2026_08_22_fixture_identity_review.py"
    ).read_text(encoding="utf-8")
    assert '"automatic_review_performed": False' in script
    assert '"fixture_catalog_admission_performed": False' in script
    assert '"fixture_intelligence_performed": False' in script
    assert '"model_probability_performed": False' in script
    assert '"sportybet_reconciliation_performed": False' in script
    assert '"fresh_price_performed": False' in script
    assert '"selection_performed": False' in script
    assert '"bet_decision_performed": False' in script
