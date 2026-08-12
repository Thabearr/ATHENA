from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from tests.support.module_loader import load_test_module

from domain.fixture_intelligence import IntelligenceFactStatus
from domain.fotmob_reviewed_match_details_field_evidence_qualification import (
    FieldEvidenceQualificationDisposition,
)
from domain.fotmob_reviewed_match_details_status_classification_policy import (
    CONFLICT_POLICY,
    POLICY_SCOPE,
    FotMobReviewedMatchDetailsStatusClassificationPolicyError,
    MatchDetailsFreshnessPolicyRule,
    ReviewedMatchDetailsStatusClassificationPolicy,
    StatusClassificationPolicyDisposition,
    build_reviewed_match_details_status_classification_policy,
    canonical_reviewed_match_details_status_classification_policy_bytes,
    revalidate_reviewed_match_details_status_classification_policy,
    sha256_reviewed_match_details_status_classification_policy,
)


def _pr58_helper():
    return load_test_module("test_fotmob_reviewed_match_details_field_evidence_qualification")


def _policy_reviewed_at(qualification) -> datetime.datetime:
    return qualification.reviewed_at + (
        (qualification.kickoff - qualification.reviewed_at) / 3
    )


def _fresh_until(qualification) -> datetime.datetime:
    return qualification.reviewed_at + (
        2 * (qualification.kickoff - qualification.reviewed_at) / 3
    )


def _freshness_rules(qualification):
    rules = []
    for decision in qualification.decisions:
        if decision.disposition is FieldEvidenceQualificationDisposition.QUALIFIED:
            rules.append(
                MatchDetailsFreshnessPolicyRule(
                    category=decision.category,
                    field=decision.field,
                    source_reference=decision.source_reference,
                    fresh_until=_fresh_until(qualification),
                    rationale=f"Explicit freshness policy for {decision.field}.",
                )
            )
    return tuple(sorted(rules, key=lambda item: item.key))


def _build_policy(raw: bytes, approved_decisions, dispositions=None):
    helper = _pr58_helper()
    qualification, qualification_bytes, fact_bundle, fact_bytes, chain = (
        helper._build_qualification(raw, approved_decisions, dispositions)
    )
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain
    policy = build_reviewed_match_details_status_classification_policy(
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
        qualification=qualification,
        qualification_bytes=qualification_bytes,
        freshness_rules=_freshness_rules(qualification),
        policy_reviewed_at=_policy_reviewed_at(qualification),
        reviewer_reference="ATHENA-PR60-TEST",
    )
    policy_bytes = canonical_reviewed_match_details_status_classification_policy_bytes(
        policy
    )
    return (
        policy,
        policy_bytes,
        qualification,
        qualification_bytes,
        fact_bundle,
        fact_bytes,
        chain,
    )


def test_policy_records_qualified_freshness_and_blocks_rejected_without_status_change() -> None:
    helper = _pr58_helper()
    raw = b'{"alpha":{"label":"ok","value":100}}'
    policy, _, qualification, _, fact_bundle, _, _ = _build_policy(
        raw,
        helper._two_approved(),
        {"synthetic_label": FieldEvidenceQualificationDisposition.REJECTED},
    )

    assert type(policy) is ReviewedMatchDetailsStatusClassificationPolicy
    assert policy.policy_scope == POLICY_SCOPE == "EXACT_OBSERVATION_ONLY"
    assert policy.conflict_policy == CONFLICT_POLICY == "PRESERVE_DIFFERING_QUALIFIED_VALUES"
    assert policy.eligible_count == 1
    assert policy.blocked_count == 1
    assert len(policy.decisions) == len(qualification.decisions) == 2
    assert policy.fixture_identifier == qualification.fixture_identifier
    assert policy.source_match_id == qualification.source_match_id
    assert policy.raw_sha256 == qualification.raw_sha256
    assert policy.evidence_file_path == qualification.evidence_file_path
    assert policy.qualification_reviewed_at == qualification.reviewed_at
    assert policy.qualification_reviewed_at <= policy.policy_reviewed_at < policy.kickoff
    assert all(fact.status is IntelligenceFactStatus.UNVERIFIED for fact in fact_bundle.facts)
    assert all(value is False for value in policy.safety.values())

    eligible = next(
        item
        for item in policy.decisions
        if item.disposition
        is StatusClassificationPolicyDisposition.ELIGIBLE_FOR_LATER_CLASSIFICATION
    )
    blocked = next(
        item
        for item in policy.decisions
        if item.disposition
        is StatusClassificationPolicyDisposition.BLOCKED_BY_QUALIFICATION
    )
    assert eligible.qualification_disposition is FieldEvidenceQualificationDisposition.QUALIFIED
    assert eligible.fresh_until is not None
    assert policy.observed_at <= eligible.fresh_until < policy.kickoff
    assert blocked.qualification_disposition is FieldEvidenceQualificationDisposition.REJECTED
    assert blocked.fresh_until is None

    payload = policy.to_dict()
    assert "facts" not in payload
    assert "status" not in payload
    assert payload["safety"]["status_promotion_authorized"] is False
    assert payload["safety"]["conflict_resolution_authorized"] is False


def test_freshness_rules_cover_every_and_only_qualified_fact() -> None:
    helper = _pr58_helper()
    raw = b'{"alpha":{"label":"ok","value":100}}'
    qualification, qualification_bytes, fact_bundle, fact_bytes, chain = (
        helper._build_qualification(
            raw,
            helper._two_approved(),
            {"synthetic_label": FieldEvidenceQualificationDisposition.REJECTED},
        )
    )
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain
    rules = _freshness_rules(qualification)
    assert len(rules) == 1

    with pytest.raises(
        FotMobReviewedMatchDetailsStatusClassificationPolicyError,
        match="every and only PR #58 QUALIFIED fact",
    ):
        build_reviewed_match_details_status_classification_policy(
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
            qualification=qualification,
            qualification_bytes=qualification_bytes,
            freshness_rules=(),
            policy_reviewed_at=_policy_reviewed_at(qualification),
            reviewer_reference="ATHENA-PR60-TEST",
        )

    rejected = next(
        item
        for item in qualification.decisions
        if item.disposition is FieldEvidenceQualificationDisposition.REJECTED
    )
    extra = MatchDetailsFreshnessPolicyRule(
        category=rejected.category,
        field=rejected.field,
        source_reference=rejected.source_reference,
        fresh_until=_fresh_until(qualification),
        rationale="A rejected observation must not receive a freshness rule.",
    )
    supplied = tuple(sorted(rules + (extra,), key=lambda item: item.key))
    with pytest.raises(
        FotMobReviewedMatchDetailsStatusClassificationPolicyError,
        match="every and only PR #58 QUALIFIED fact",
    ):
        build_reviewed_match_details_status_classification_policy(
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
            qualification=qualification,
            qualification_bytes=qualification_bytes,
            freshness_rules=supplied,
            policy_reviewed_at=_policy_reviewed_at(qualification),
            reviewer_reference="ATHENA-PR60-TEST",
        )


def test_all_rejected_qualification_requires_no_freshness_rule() -> None:
    helper = _pr58_helper()
    raw = b'{"alpha":{"value":100}}'
    policy, _, qualification, _, _, _, _ = _build_policy(
        raw,
        helper._one_approved(),
        {"synthetic_metric": FieldEvidenceQualificationDisposition.REJECTED},
    )
    assert all(
        item.disposition is FieldEvidenceQualificationDisposition.REJECTED
        for item in qualification.decisions
    )
    assert policy.eligible_count == 0
    assert policy.blocked_count == 1
    assert policy.decisions[0].fresh_until is None


def test_freshness_rules_must_be_sorted_unique_and_exact_types() -> None:
    helper = _pr58_helper()
    raw = b'{"alpha":{"label":"ok","value":100}}'
    qualification, qualification_bytes, fact_bundle, fact_bytes, chain = (
        helper._build_qualification(raw, helper._two_approved())
    )
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain
    rules = _freshness_rules(qualification)
    assert len(rules) == 2

    with pytest.raises(
        FotMobReviewedMatchDetailsStatusClassificationPolicyError,
        match="deterministically sorted",
    ):
        build_reviewed_match_details_status_classification_policy(
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
            qualification=qualification,
            qualification_bytes=qualification_bytes,
            freshness_rules=tuple(reversed(rules)),
            policy_reviewed_at=_policy_reviewed_at(qualification),
            reviewer_reference="ATHENA-PR60-TEST",
        )

    with pytest.raises(
        FotMobReviewedMatchDetailsStatusClassificationPolicyError,
        match="unique exact facts",
    ):
        build_reviewed_match_details_status_classification_policy(
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
            qualification=qualification,
            qualification_bytes=qualification_bytes,
            freshness_rules=tuple(sorted((rules[0], rules[0]), key=lambda item: item.key)),
            policy_reviewed_at=_policy_reviewed_at(qualification),
            reviewer_reference="ATHENA-PR60-TEST",
        )

    with pytest.raises(
        FotMobReviewedMatchDetailsStatusClassificationPolicyError,
        match="exact immutable tuple",
    ):
        build_reviewed_match_details_status_classification_policy(
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
            qualification=qualification,
            qualification_bytes=qualification_bytes,
            freshness_rules=list(rules),
            policy_reviewed_at=_policy_reviewed_at(qualification),
            reviewer_reference="ATHENA-PR60-TEST",
        )


def test_fresh_until_is_explicit_utc_and_strictly_pre_kickoff() -> None:
    helper = _pr58_helper()
    raw = b'{"alpha":{"value":100}}'
    qualification, qualification_bytes, fact_bundle, fact_bytes, chain = (
        helper._build_qualification(raw, helper._one_approved())
    )
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain
    decision = qualification.decisions[0]

    for invalid in (
        qualification.observed_at - datetime.timedelta(microseconds=1),
        qualification.kickoff,
        qualification.kickoff + datetime.timedelta(microseconds=1),
    ):
        rule = MatchDetailsFreshnessPolicyRule(
            category=decision.category,
            field=decision.field,
            source_reference=decision.source_reference,
            fresh_until=invalid,
            rationale="Explicit invalid-boundary test.",
        )
        with pytest.raises(
            FotMobReviewedMatchDetailsStatusClassificationPolicyError,
            match="fresh_until",
        ):
            build_reviewed_match_details_status_classification_policy(
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
                qualification=qualification,
                qualification_bytes=qualification_bytes,
                freshness_rules=(rule,),
                policy_reviewed_at=_policy_reviewed_at(qualification),
                reviewer_reference="ATHENA-PR60-TEST",
            )

    with pytest.raises(
        FotMobReviewedMatchDetailsStatusClassificationPolicyError,
        match="exact datetime.timezone.utc",
    ):
        MatchDetailsFreshnessPolicyRule(
            category=decision.category,
            field=decision.field,
            source_reference=decision.source_reference,
            fresh_until=_fresh_until(qualification).replace(tzinfo=datetime.timezone(datetime.timedelta(hours=1))),
            rationale="Wrong timezone object.",
        )


def test_policy_review_chronology_is_prospective() -> None:
    helper = _pr58_helper()
    raw = b'{"alpha":{"value":100}}'
    qualification, qualification_bytes, fact_bundle, fact_bytes, chain = (
        helper._build_qualification(raw, helper._one_approved())
    )
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain
    rules = _freshness_rules(qualification)

    for invalid in (
        qualification.reviewed_at - datetime.timedelta(microseconds=1),
        qualification.kickoff,
        qualification.kickoff + datetime.timedelta(microseconds=1),
    ):
        with pytest.raises(
            FotMobReviewedMatchDetailsStatusClassificationPolicyError,
            match="policy_reviewed_at",
        ):
            build_reviewed_match_details_status_classification_policy(
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
                qualification=qualification,
                qualification_bytes=qualification_bytes,
                freshness_rules=rules,
                policy_reviewed_at=invalid,
                reviewer_reference="ATHENA-PR60-TEST",
            )


def test_builder_requires_exact_pr58_bytes_and_full_chain_revalidation() -> None:
    helper = _pr58_helper()
    raw = b'{"alpha":{"value":100}}'
    qualification, qualification_bytes, fact_bundle, fact_bytes, chain = (
        helper._build_qualification(raw, helper._one_approved())
    )
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain

    with pytest.raises(
        FotMobReviewedMatchDetailsStatusClassificationPolicyError,
        match="full-chain revalidation",
    ):
        build_reviewed_match_details_status_classification_policy(
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
            qualification=qualification,
            qualification_bytes=qualification_bytes + b"\n",
            freshness_rules=_freshness_rules(qualification),
            policy_reviewed_at=_policy_reviewed_at(qualification),
            reviewer_reference="ATHENA-PR60-TEST",
        )


def test_policy_revalidation_requires_exact_presented_bytes() -> None:
    helper = _pr58_helper()
    raw = b'{"alpha":{"value":100}}'
    policy, policy_bytes, qualification, qualification_bytes, fact_bundle, fact_bytes, chain = (
        _build_policy(raw, helper._one_approved())
    )
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain

    rebuilt = revalidate_reviewed_match_details_status_classification_policy(
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
        qualification=qualification,
        qualification_bytes=qualification_bytes,
        policy=policy,
        policy_bytes=policy_bytes,
    )
    assert rebuilt.to_dict() == policy.to_dict()

    with pytest.raises(
        FotMobReviewedMatchDetailsStatusClassificationPolicyError,
        match="exact canonical PR #60 bytes",
    ):
        revalidate_reviewed_match_details_status_classification_policy(
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
            qualification=qualification,
            qualification_bytes=qualification_bytes,
            policy=policy,
            policy_bytes=policy_bytes + b"\n",
        )


def test_full_chain_revalidation_rejects_mutated_recorded_fact_hash() -> None:
    helper = _pr58_helper()
    raw = b'{"alpha":{"value":100}}'
    policy, _, qualification, qualification_bytes, fact_bundle, fact_bytes, chain = (
        _build_policy(raw, helper._one_approved())
    )
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain

    object.__setattr__(policy.decisions[0], "fact_sha256", "0" * 64)
    forged_bytes = canonical_reviewed_match_details_status_classification_policy_bytes(
        policy
    )
    with pytest.raises(
        FotMobReviewedMatchDetailsStatusClassificationPolicyError,
        match="full-chain",
    ):
        revalidate_reviewed_match_details_status_classification_policy(
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
            qualification=qualification,
            qualification_bytes=qualification_bytes,
            policy=policy,
            policy_bytes=forged_bytes,
        )


def test_nested_policy_mutation_conflict_policy_and_safety_fail_closed() -> None:
    helper = _pr58_helper()
    raw = b'{"alpha":{"value":100}}'

    policy, _, _, _, _, _, _ = _build_policy(raw, helper._one_approved())
    object.__setattr__(policy.decisions[0], "rationale", "   ")
    with pytest.raises(
        FotMobReviewedMatchDetailsStatusClassificationPolicyError,
        match="nested policy decision",
    ):
        canonical_reviewed_match_details_status_classification_policy_bytes(policy)

    policy, _, _, _, _, _, _ = _build_policy(raw, helper._one_approved())
    object.__setattr__(policy, "conflict_policy", "LATEST_WINS")
    with pytest.raises(
        FotMobReviewedMatchDetailsStatusClassificationPolicyError,
        match="preserve differing qualified values",
    ):
        canonical_reviewed_match_details_status_classification_policy_bytes(policy)

    policy, _, _, _, _, _, _ = _build_policy(raw, helper._one_approved())
    unsafe = dict(policy.safety)
    unsafe["supported_status_authorized"] = True
    object.__setattr__(policy, "safety", unsafe)
    with pytest.raises(
        FotMobReviewedMatchDetailsStatusClassificationPolicyError,
        match="safety",
    ):
        canonical_reviewed_match_details_status_classification_policy_bytes(policy)


def test_canonical_bytes_are_deterministic() -> None:
    helper = _pr58_helper()
    raw = b'{"alpha":{"value":100}}'
    policy, policy_bytes, _, _, _, _, _ = _build_policy(raw, helper._one_approved())

    assert policy_bytes.endswith(b"\n")
    assert canonical_reviewed_match_details_status_classification_policy_bytes(
        policy
    ) == policy_bytes
    assert len(sha256_reviewed_match_details_status_classification_policy(policy)) == 64


def test_module_has_no_fact_promotion_snapshot_registry_or_network_side_effects() -> None:
    module_path = (
        Path(__file__).parents[1]
        / "domain"
        / "fotmob_reviewed_match_details_status_classification_policy.py"
    )
    source = module_path.read_text(encoding="utf-8")

    forbidden = (
        "FixtureIntelligenceFact",
        "IntelligenceFactStatus",
        "domain.source_capabilities",
        "SOURCE_CAPABILITY_REGISTRY",
        "build_snapshot",
        "build_model_feature_snapshot",
        "requests.",
        "httpx.",
        "aiohttp.",
        "urllib.request",
        "socket.",
    )
    for token in forbidden:
        assert token not in source
