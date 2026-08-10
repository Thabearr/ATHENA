from __future__ import annotations

import datetime
import hashlib
import importlib.util
from pathlib import Path

import pytest

from domain.fixture_intelligence import IntelligenceFactStatus
from domain.fotmob_reviewed_match_details_fact_qualification_policy import (
    MAX_CAPTURE_AGE_SECONDS,
    FactQualificationDisposition,
    FotMobReviewedMatchDetailsFactQualificationPolicyError,
    MatchDetailsFactQualificationDecision,
    ReviewedMatchDetailsFactQualificationPolicy,
    build_reviewed_match_details_fact_qualification_policy,
    canonical_reviewed_match_details_fact_qualification_policy_bytes,
    revalidate_reviewed_match_details_fact_qualification_policy,
    sha256_reviewed_match_details_fact_qualification_policy,
)
from domain.fotmob_reviewed_match_details_structure import JsonValueKind
from domain.fotmob_reviewed_match_details_unverified_candidates import (
    canonical_reviewed_match_details_unverified_candidate_bundle_bytes,
)
from domain.fotmob_reviewed_match_details_unverified_facts import (
    canonical_reviewed_match_details_unverified_fact_bundle_bytes,
)
from domain.source_capabilities import SOURCE_CAPABILITY_REGISTRY


def _pr57_helper():
    helper_path = Path(__file__).with_name(
        "test_fotmob_reviewed_match_details_unverified_facts.py"
    )
    spec = importlib.util.spec_from_file_location("_athena_pr57_policy_helper", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PR #57 helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _semantic_decisions():
    helper = _pr57_helper()
    return (
        helper._approved(
            "/form/home",
            JsonValueKind.NUMBER,
            helper.IntelligenceCategory.FORM,
            "home_form",
        ),
        helper._approved(
            "/context/label",
            JsonValueKind.STRING,
            helper.IntelligenceCategory.MATCH_CONTEXT,
            "context_label",
        ),
    )


def _eligible(candidate, *, age: int = 3600, corroboration: bool = False):
    return MatchDetailsFactQualificationDecision(
        category=candidate.category,
        field=candidate.field,
        json_pointer=candidate.json_pointer,
        expected_kind=candidate.json_kind,
        disposition=FactQualificationDisposition.ELIGIBLE,
        max_capture_age_seconds=age,
        requires_independent_corroboration=corroboration,
        notes="reviewed eligibility only",
    )


def _rejected(candidate):
    return MatchDetailsFactQualificationDecision(
        category=candidate.category,
        field=candidate.field,
        json_pointer=candidate.json_pointer,
        expected_kind=candidate.json_kind,
        disposition=FactQualificationDisposition.REJECTED,
        max_capture_age_seconds=None,
        requires_independent_corroboration=False,
        notes="not eligible for later classification",
    )


def _chain():
    helper = _pr57_helper()
    raw = b'{"form":{"home":0.75},"context":{"label":"cup"}}'
    fact_bundle, _, _, chain = helper._fact_bundle(raw, _semantic_decisions())
    fact_bundle_bytes = canonical_reviewed_match_details_unverified_fact_bundle_bytes(
        fact_bundle
    )
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain
    return {
        "raw": raw,
        "fact_bundle": fact_bundle,
        "fact_bundle_bytes": fact_bundle_bytes,
        "evidence": evidence,
        "receipt": receipt,
        "manifest": manifest,
        "assessment": assessment,
        "assessment_bytes": assessment_bytes,
        "review": review,
        "review_bytes": review_bytes,
    }


def _build_policy(*, decisions=None, reviewed_at=None):
    chain = _chain()
    candidates = chain["fact_bundle"].candidate_bundle.candidates
    if decisions is None:
        decisions = (_eligible(candidates[0], age=1800), _rejected(candidates[1]))
    if reviewed_at is None:
        reviewed_at = chain["fact_bundle"].observed_at + datetime.timedelta(seconds=1)
    policy = build_reviewed_match_details_fact_qualification_policy(
        evidence=chain["evidence"],
        evidence_receipt_bytes=chain["receipt"],
        manifest_bytes=chain["manifest"],
        raw_bytes=chain["raw"],
        assessment=chain["assessment"],
        assessment_bytes=chain["assessment_bytes"],
        review=chain["review"],
        review_bytes=chain["review_bytes"],
        fact_bundle=chain["fact_bundle"],
        fact_bundle_bytes=chain["fact_bundle_bytes"],
        decisions=tuple(decisions),
        reviewed_at=reviewed_at,
        reviewer_reference="ATHENA-PR58-TEST",
    )
    return policy, chain


def test_policy_covers_every_exact_pr57_fact_without_changing_status() -> None:
    registry_before = dict(SOURCE_CAPABILITY_REGISTRY)
    policy, chain = _build_policy()

    assert type(policy) is ReviewedMatchDetailsFactQualificationPolicy
    assert policy.fixture_identifier == chain["fact_bundle"].fixture_identifier
    assert policy.source_match_id == chain["fact_bundle"].source_match_id
    assert policy.kickoff == chain["fact_bundle"].kickoff
    assert policy.observed_at == chain["fact_bundle"].observed_at
    assert policy.raw_sha256 == chain["fact_bundle"].raw_sha256
    assert len(policy.decisions) == len(chain["fact_bundle"].facts) == 2
    assert all(
        fact.status is IntelligenceFactStatus.UNVERIFIED
        for fact in policy.fact_bundle.facts
    )
    assert all(value is False for value in policy.safety.values())
    assert SOURCE_CAPABILITY_REGISTRY == registry_before
    assert "fotmob_match_details_reviewed" not in SOURCE_CAPABILITY_REGISTRY

    payload = policy.to_dict()
    assert payload["fact_bundle"]["facts"][0]["status"] == "UNVERIFIED"
    assert payload["safety"]["source_qualification_satisfied"] is False
    assert payload["safety"]["supported_status_authorized"] is False
    assert payload["safety"]["status_classification_authorized"] is False


def test_policy_requires_every_and_only_exact_candidate_target() -> None:
    chain = _chain()
    candidates = chain["fact_bundle"].candidate_bundle.candidates

    with pytest.raises(
        FotMobReviewedMatchDetailsFactQualificationPolicyError,
        match="every and only",
    ):
        _build_policy(decisions=(_eligible(candidates[0]),))

    fake = MatchDetailsFactQualificationDecision(
        category=candidates[1].category,
        field=candidates[1].field,
        json_pointer="/context/other",
        expected_kind=candidates[1].json_kind,
        disposition=FactQualificationDisposition.REJECTED,
        max_capture_age_seconds=None,
        requires_independent_corroboration=False,
        notes="fake target",
    )
    with pytest.raises(
        FotMobReviewedMatchDetailsFactQualificationPolicyError,
        match="every and only",
    ):
        _build_policy(decisions=(_eligible(candidates[0]), fake))


def test_policy_expected_kind_must_match_exact_pr55_candidate_kind() -> None:
    chain = _chain()
    candidates = chain["fact_bundle"].candidate_bundle.candidates
    wrong = MatchDetailsFactQualificationDecision(
        category=candidates[0].category,
        field=candidates[0].field,
        json_pointer=candidates[0].json_pointer,
        expected_kind=JsonValueKind.STRING,
        disposition=FactQualificationDisposition.ELIGIBLE,
        max_capture_age_seconds=3600,
        requires_independent_corroboration=False,
        notes="wrong kind",
    )
    with pytest.raises(
        FotMobReviewedMatchDetailsFactQualificationPolicyError,
        match="expected_kind",
    ):
        _build_policy(decisions=(wrong, _rejected(candidates[1])))


def test_eligible_policy_requires_bounded_capture_age_and_exact_corroboration_bool() -> None:
    chain = _chain()
    candidate = chain["fact_bundle"].candidate_bundle.candidates[0]

    for invalid_age in (0, -1, MAX_CAPTURE_AGE_SECONDS + 1, True):
        with pytest.raises(
            FotMobReviewedMatchDetailsFactQualificationPolicyError,
            match="max_capture_age_seconds",
        ):
            MatchDetailsFactQualificationDecision(
                category=candidate.category,
                field=candidate.field,
                json_pointer=candidate.json_pointer,
                expected_kind=candidate.json_kind,
                disposition=FactQualificationDisposition.ELIGIBLE,
                max_capture_age_seconds=invalid_age,
                requires_independent_corroboration=False,
                notes="bad age",
            )

    with pytest.raises(
        FotMobReviewedMatchDetailsFactQualificationPolicyError,
        match="exact bool",
    ):
        MatchDetailsFactQualificationDecision(
            category=candidate.category,
            field=candidate.field,
            json_pointer=candidate.json_pointer,
            expected_kind=candidate.json_kind,
            disposition=FactQualificationDisposition.ELIGIBLE,
            max_capture_age_seconds=3600,
            requires_independent_corroboration=1,
            notes="bad corroboration type",
        )


def test_rejected_policy_cannot_carry_freshness_or_corroboration_requirements() -> None:
    chain = _chain()
    candidate = chain["fact_bundle"].candidate_bundle.candidates[0]

    with pytest.raises(
        FotMobReviewedMatchDetailsFactQualificationPolicyError,
        match="must not carry max_capture_age_seconds",
    ):
        MatchDetailsFactQualificationDecision(
            category=candidate.category,
            field=candidate.field,
            json_pointer=candidate.json_pointer,
            expected_kind=candidate.json_kind,
            disposition=FactQualificationDisposition.REJECTED,
            max_capture_age_seconds=60,
            requires_independent_corroboration=False,
            notes="bad rejected policy",
        )

    with pytest.raises(
        FotMobReviewedMatchDetailsFactQualificationPolicyError,
        match="cannot request corroboration",
    ):
        MatchDetailsFactQualificationDecision(
            category=candidate.category,
            field=candidate.field,
            json_pointer=candidate.json_pointer,
            expected_kind=candidate.json_kind,
            disposition=FactQualificationDisposition.REJECTED,
            max_capture_age_seconds=None,
            requires_independent_corroboration=True,
            notes="bad rejected policy",
        )


def test_policy_review_must_be_prospective_and_not_predate_observation() -> None:
    chain = _chain()

    with pytest.raises(
        FotMobReviewedMatchDetailsFactQualificationPolicyError,
        match="must not predate",
    ):
        _build_policy(
            reviewed_at=chain["fact_bundle"].observed_at - datetime.timedelta(microseconds=1)
        )

    with pytest.raises(
        FotMobReviewedMatchDetailsFactQualificationPolicyError,
        match="strictly before fixture kickoff",
    ):
        _build_policy(reviewed_at=chain["fact_bundle"].kickoff)


def test_full_chain_revalidation_rejects_coordinated_candidate_and_fact_forgery() -> None:
    chain = _chain()
    fact_bundle = chain["fact_bundle"]
    candidate = fact_bundle.candidate_bundle.candidates[0]
    matching_fact = next(
        fact
        for fact in fact_bundle.facts
        if fact.category is candidate.category and fact.field == candidate.field
    )

    object.__setattr__(candidate, "value", 0.99)
    object.__setattr__(matching_fact, "value", 0.99)
    candidate_bytes = canonical_reviewed_match_details_unverified_candidate_bundle_bytes(
        fact_bundle.candidate_bundle
    )
    object.__setattr__(fact_bundle, "candidate_bundle_size", len(candidate_bytes))
    object.__setattr__(
        fact_bundle,
        "candidate_bundle_sha256",
        hashlib.sha256(candidate_bytes).hexdigest(),
    )
    forged_fact_bytes = canonical_reviewed_match_details_unverified_fact_bundle_bytes(
        fact_bundle
    )

    decisions = tuple(
        _eligible(item) for item in fact_bundle.candidate_bundle.candidates
    )
    with pytest.raises(
        FotMobReviewedMatchDetailsFactQualificationPolicyError,
        match="PR #57 fact bundle failed exact full-chain revalidation",
    ):
        build_reviewed_match_details_fact_qualification_policy(
            evidence=chain["evidence"],
            evidence_receipt_bytes=chain["receipt"],
            manifest_bytes=chain["manifest"],
            raw_bytes=chain["raw"],
            assessment=chain["assessment"],
            assessment_bytes=chain["assessment_bytes"],
            review=chain["review"],
            review_bytes=chain["review_bytes"],
            fact_bundle=fact_bundle,
            fact_bundle_bytes=forged_fact_bytes,
            decisions=decisions,
            reviewed_at=fact_bundle.observed_at + datetime.timedelta(seconds=1),
            reviewer_reference="ATHENA-PR58-FORGERY",
        )


def test_policy_canonicalization_is_deterministic_and_revalidatable() -> None:
    policy, chain = _build_policy()
    canonical = canonical_reviewed_match_details_fact_qualification_policy_bytes(policy)
    assert canonical.endswith(b"\n")
    assert len(sha256_reviewed_match_details_fact_qualification_policy(policy)) == 64

    rebuilt = revalidate_reviewed_match_details_fact_qualification_policy(
        evidence=chain["evidence"],
        evidence_receipt_bytes=chain["receipt"],
        manifest_bytes=chain["manifest"],
        raw_bytes=chain["raw"],
        assessment=chain["assessment"],
        assessment_bytes=chain["assessment_bytes"],
        review=chain["review"],
        review_bytes=chain["review_bytes"],
        fact_bundle=chain["fact_bundle"],
        fact_bundle_bytes=chain["fact_bundle_bytes"],
        policy=policy,
        policy_bytes=canonical,
    )
    assert canonical_reviewed_match_details_fact_qualification_policy_bytes(rebuilt) == canonical

    with pytest.raises(
        FotMobReviewedMatchDetailsFactQualificationPolicyError,
        match="exact canonical qualification policy bytes",
    ):
        revalidate_reviewed_match_details_fact_qualification_policy(
            evidence=chain["evidence"],
            evidence_receipt_bytes=chain["receipt"],
            manifest_bytes=chain["manifest"],
            raw_bytes=chain["raw"],
            assessment=chain["assessment"],
            assessment_bytes=chain["assessment_bytes"],
            review=chain["review"],
            review_bytes=chain["review_bytes"],
            fact_bundle=chain["fact_bundle"],
            fact_bundle_bytes=chain["fact_bundle_bytes"],
            policy=policy,
            policy_bytes=canonical + b"\n",
        )


def test_policy_safety_cannot_be_upgraded() -> None:
    policy, _ = _build_policy()
    unsafe = dict(policy.safety)
    unsafe["supported_status_authorized"] = True
    object.__setattr__(policy, "safety", unsafe)
    with pytest.raises(
        FotMobReviewedMatchDetailsFactQualificationPolicyError,
        match="safety",
    ):
        canonical_reviewed_match_details_fact_qualification_policy_bytes(policy)
