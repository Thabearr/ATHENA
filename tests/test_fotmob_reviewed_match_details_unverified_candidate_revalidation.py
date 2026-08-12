from __future__ import annotations

import pytest

from tests.support.module_loader import load_test_module

from domain.fixture_intelligence import IntelligenceFactStatus
from domain.fotmob_reviewed_match_details_structure import JsonValueKind
from domain.fotmob_reviewed_match_details_unverified_candidates import (
    FotMobReviewedMatchDetailsUnverifiedCandidateError,
    canonical_reviewed_match_details_unverified_candidate_bundle_bytes,
)


def _helper_module():
    return load_test_module("test_fotmob_reviewed_match_details_unverified_candidates")


def _bundle():
    helper = _helper_module()
    raw = b'{"alpha":{"value":100}}'
    decision = helper._approved(
        "/alpha/value",
        JsonValueKind.INTEGER,
        helper.IntelligenceCategory.MATCH_CONTEXT,
        "synthetic_metric",
    )
    bundle, _ = helper._build(raw, (decision,))
    return bundle


def test_forced_nested_candidate_status_mutation_fails_canonicalization() -> None:
    bundle = _bundle()
    candidate = bundle.candidates[0]
    object.__setattr__(candidate, "status", IntelligenceFactStatus.SUPPORTED)

    with pytest.raises(
        FotMobReviewedMatchDetailsUnverifiedCandidateError,
        match="UNVERIFIED",
    ):
        canonical_reviewed_match_details_unverified_candidate_bundle_bytes(bundle)


def test_forced_nested_candidate_source_reference_mutation_fails_canonicalization() -> None:
    bundle = _bundle()
    candidate = bundle.candidates[0]
    object.__setattr__(candidate, "source_reference", "FORGED")

    with pytest.raises(
        FotMobReviewedMatchDetailsUnverifiedCandidateError,
        match="source_reference",
    ):
        canonical_reviewed_match_details_unverified_candidate_bundle_bytes(bundle)


def test_forced_nested_candidate_kind_mutation_fails_canonicalization() -> None:
    bundle = _bundle()
    candidate = bundle.candidates[0]
    object.__setattr__(candidate, "json_kind", JsonValueKind.STRING)

    with pytest.raises(
        FotMobReviewedMatchDetailsUnverifiedCandidateError,
        match="json_kind",
    ):
        canonical_reviewed_match_details_unverified_candidate_bundle_bytes(bundle)
