from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from domain.fotmob_reviewed_match_details_field_evidence_qualification import (
    FotMobReviewedMatchDetailsFieldEvidenceQualificationError,
    build_reviewed_match_details_field_evidence_qualification,
    canonical_reviewed_match_details_field_evidence_qualification_bytes,
)


def _helper():
    helper_path = Path(__file__).with_name(
        "test_fotmob_reviewed_match_details_field_evidence_qualification.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_athena_pr58_mutation_helper",
        helper_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PR #58 helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_forced_nested_recorded_decision_mutation_fails_local_canonicalization() -> None:
    helper = _helper()
    raw = b'{"alpha":{"value":100}}'

    qualification, _, _, _, _ = helper._build_qualification(
        raw,
        helper._one_approved(),
    )
    object.__setattr__(qualification.decisions[0], "rationale", "   ")
    with pytest.raises(
        FotMobReviewedMatchDetailsFieldEvidenceQualificationError,
        match="nested recorded decision",
    ):
        canonical_reviewed_match_details_field_evidence_qualification_bytes(
            qualification
        )

    qualification, _, _, _, _ = helper._build_qualification(
        raw,
        helper._one_approved(),
    )
    object.__setattr__(qualification.decisions[0], "fact_sha256", "not-a-sha")
    with pytest.raises(
        FotMobReviewedMatchDetailsFieldEvidenceQualificationError,
        match="nested recorded decision",
    ):
        canonical_reviewed_match_details_field_evidence_qualification_bytes(
            qualification
        )


def test_forced_input_review_decision_mutation_fails_before_recording() -> None:
    helper = _helper()
    raw = b'{"alpha":{"value":100}}'
    fact_bundle, fact_bytes, chain = helper._fact_chain(
        raw,
        helper._one_approved(),
    )
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain
    decisions = helper._review_decisions(fact_bundle)
    object.__setattr__(decisions[0], "rationale", "   ")

    with pytest.raises(
        FotMobReviewedMatchDetailsFieldEvidenceQualificationError,
        match="review decision failed invariant revalidation",
    ):
        build_reviewed_match_details_field_evidence_qualification(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            fact_bundle=fact_bundle,
            fact_bundle_bytes=fact_bytes,
            decisions=decisions,
            reviewed_at=helper._qualification_reviewed_at(fact_bundle, review),
            reviewer_reference="ATHENA-PR58-MUTATION-TEST",
        )
