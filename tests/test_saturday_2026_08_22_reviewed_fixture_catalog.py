from __future__ import annotations

import hashlib
from pathlib import Path

from domain.fixture_catalog import parse_utc_timestamp
from domain.fotmob_fixture_candidate_review import FixtureCandidateReviewDisposition
from scripts.manage_fotmob_reviewed_fixture_catalog import load_review_decision_ledger
from scripts.prepare_saturday_2026_08_22_reviewed_fixture_catalog import (
    ADMISSION_NOTES,
    ADMISSION_REVIEWED_AT,
    ADMISSION_REVIEWER_REFERENCE,
    CATALOG_AS_OF,
    EXPECTED_APPROVED_FIXTURE_COUNT,
    EXPECTED_CANDIDATE_BUNDLE_SHA256,
    EXPECTED_FIXTURE_REVIEW_LEDGER_SHA256,
    EXPECTED_MANIFEST_SHA256,
    EXPECTED_RAW_SHA256,
    EXPECTED_SOURCE_ARTIFACT_DIGEST,
    EXPECTED_SOURCE_ARTIFACT_ID,
    EXPECTED_SOURCE_CANDIDATE_COUNT,
    EXPECTED_SOURCE_HEAD_SHA,
    EXPECTED_SOURCE_RUN_ID,
    EXPECTED_UNREVIEWED_FIXTURE_COUNT,
)


LEDGER = Path("evidence/saturday_2026_08_22_fixture_identity_review_decisions.json")


def test_saturday_reviewed_catalog_pins_the_exact_pr199_source_boundary():
    assert EXPECTED_SOURCE_HEAD_SHA == "b879b2140d0bc3fb64fa8fec4c73c735240a3b41"
    assert EXPECTED_SOURCE_RUN_ID == 32455713912
    assert EXPECTED_SOURCE_ARTIFACT_ID == 9437181220
    assert EXPECTED_SOURCE_ARTIFACT_DIGEST == (
        "sha256:360aac588f049fe6b0437c43e060b317edd12aaf4672db93ebe2fca42de00589"
    )
    assert EXPECTED_RAW_SHA256 == (
        "a22e449fd7c59bee011e71230e345c733e1322311f6a9481812a23b4dcae2dc8"
    )
    assert EXPECTED_MANIFEST_SHA256 == (
        "64fb631d4889dbf360af4fb988656aba579b67ca5340578df1056dc5324dc09e"
    )
    assert EXPECTED_CANDIDATE_BUNDLE_SHA256 == (
        "53b48ae1beabc10b638ad20f21e4807f78f0a3879ff8a21fd19a2da538a1ba3d"
    )
    assert EXPECTED_SOURCE_CANDIDATE_COUNT == 670


def test_saturday_reviewed_catalog_consumes_exactly_the_50_pr201_identity_approvals():
    raw = LEDGER.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_FIXTURE_REVIEW_LEDGER_SHA256
    decisions, ledger_sha = load_review_decision_ledger(
        LEDGER,
        expected_candidate_bundle_sha256=EXPECTED_CANDIDATE_BUNDLE_SHA256,
    )
    assert ledger_sha == EXPECTED_FIXTURE_REVIEW_LEDGER_SHA256
    assert len(decisions) == EXPECTED_APPROVED_FIXTURE_COUNT == 50
    assert EXPECTED_UNREVIEWED_FIXTURE_COUNT == 620
    assert len({item.source_match_id for item in decisions}) == 50
    assert all(
        item.disposition is FixtureCandidateReviewDisposition.APPROVED
        for item in decisions
    )


def test_catalog_and_admission_review_timestamps_remain_canonical_and_prospective():
    catalog_as_of = parse_utc_timestamp(CATALOG_AS_OF, "catalog_as_of")
    admission_reviewed_at = parse_utc_timestamp(
        ADMISSION_REVIEWED_AT,
        "admission_reviewed_at",
    )
    earliest_saturday_kickoff = parse_utc_timestamp(
        "2026-08-22T11:00:00.000000Z",
        "earliest_saturday_kickoff",
    )
    assert catalog_as_of <= admission_reviewed_at < earliest_saturday_kickoff
    assert ADMISSION_REVIEWER_REFERENCE == "ATHENA_PR202_EXACT_50_CATALOG_ADMISSION_REVIEW"
    assert "candidate only" in ADMISSION_NOTES


def test_preparation_boundary_does_not_store_or_grant_downstream_authority():
    source = Path(
        "scripts/prepare_saturday_2026_08_22_reviewed_fixture_catalog.py"
    ).read_text(encoding="utf-8")
    assert '"catalog_admission_stored": False' in source
    assert '"fixture_intelligence_performed": False' in source
    assert '"model_probability_performed": False' in source
    assert '"sportybet_reconciliation_performed": False' in source
    assert '"fresh_price_performed": False' in source
    assert '"selection_performed": False' in source
    assert '"bet_decision_performed": False' in source
    assert "_store_from_decision_file" not in source
