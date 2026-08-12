from __future__ import annotations

import dataclasses
import datetime
from pathlib import Path

import pytest

from tests.support.module_loader import load_test_module

from domain.fotmob_reviewed_match_details_field_evidence_qualification import (
    FieldEvidenceQualificationDisposition,
)
from domain.fotmob_reviewed_match_details_status_classification_policy import (
    StatusClassificationPolicyDisposition,
    canonical_reviewed_match_details_status_classification_policy_bytes,
)
from domain.fotmob_reviewed_match_details_status_classification_policy_semantics import (
    FRESHNESS_COMPARISON,
)
from domain.fotmob_reviewed_match_details_status_evaluator import (
    EVALUATION_SCOPE,
    FotMobReviewedMatchDetailsStatusEvaluationError,
    ReviewedMatchDetailsStatusEvaluation,
    StatusEvaluationDisposition,
    canonical_reviewed_match_details_status_evaluation_bytes,
    evaluate_reviewed_match_details_status_policy,
    revalidate_reviewed_match_details_status_evaluation,
    sha256_reviewed_match_details_status_evaluation,
)


UTC = datetime.timezone.utc


def _pr60_helper():
    return load_test_module("test_fotmob_reviewed_match_details_status_classification_policy")


def _build_inputs(dispositions=None):
    helper = _pr60_helper()
    pr58 = helper._pr58_helper()
    raw = b'{"alpha":{"label":"ok","value":100}}'
    (
        policy,
        policy_bytes,
        qualification,
        qualification_bytes,
        fact_bundle,
        fact_bytes,
        chain,
    ) = helper._build_policy(
        raw,
        pr58._two_approved(),
        dispositions,
    )
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain
    return {
        "raw": raw,
        "policy": policy,
        "policy_bytes": policy_bytes,
        "qualification": qualification,
        "qualification_bytes": qualification_bytes,
        "fact_bundle": fact_bundle,
        "fact_bytes": fact_bytes,
        "evidence": evidence,
        "receipt": receipt,
        "manifest": manifest,
        "assessment": assessment,
        "assessment_bytes": assessment_bytes,
        "review": review,
        "review_bytes": review_bytes,
    }


def _evaluate(inputs, classified_at):
    return evaluate_reviewed_match_details_status_policy(
        evidence=inputs["evidence"],
        evidence_receipt_bytes=inputs["receipt"],
        manifest_bytes=inputs["manifest"],
        raw_bytes=inputs["raw"],
        assessment=inputs["assessment"],
        assessment_bytes=inputs["assessment_bytes"],
        review=inputs["review"],
        review_bytes=inputs["review_bytes"],
        fact_bundle=inputs["fact_bundle"],
        fact_bundle_bytes=inputs["fact_bytes"],
        qualification=inputs["qualification"],
        qualification_bytes=inputs["qualification_bytes"],
        policy=inputs["policy"],
        policy_bytes=inputs["policy_bytes"],
        classified_at=classified_at,
    )


def _revalidate(inputs, evaluation, evaluation_bytes):
    return revalidate_reviewed_match_details_status_evaluation(
        evidence=inputs["evidence"],
        evidence_receipt_bytes=inputs["receipt"],
        manifest_bytes=inputs["manifest"],
        raw_bytes=inputs["raw"],
        assessment=inputs["assessment"],
        assessment_bytes=inputs["assessment_bytes"],
        review=inputs["review"],
        review_bytes=inputs["review_bytes"],
        fact_bundle=inputs["fact_bundle"],
        fact_bundle_bytes=inputs["fact_bytes"],
        qualification=inputs["qualification"],
        qualification_bytes=inputs["qualification_bytes"],
        policy=inputs["policy"],
        policy_bytes=inputs["policy_bytes"],
        evaluation=evaluation,
        evaluation_bytes=evaluation_bytes,
    )


def test_evaluator_emits_fresh_and_blocked_candidates_without_fact_status_promotion() -> None:
    inputs = _build_inputs(
        {"synthetic_label": FieldEvidenceQualificationDisposition.REJECTED}
    )
    policy = inputs["policy"]
    evaluation = _evaluate(inputs, policy.policy_reviewed_at)

    assert type(evaluation) is ReviewedMatchDetailsStatusEvaluation
    assert evaluation.evaluation_scope == EVALUATION_SCOPE == "EXACT_POLICY_OBSERVATION_ONLY"
    assert evaluation.freshness_comparison == FRESHNESS_COMPARISON
    assert evaluation.fixture_identifier == policy.fixture_identifier
    assert evaluation.source_match_id == policy.source_match_id
    assert evaluation.raw_sha256 == policy.raw_sha256
    assert evaluation.evidence_file_path == policy.evidence_file_path
    assert evaluation.policy_reviewed_at == policy.policy_reviewed_at
    assert evaluation.classified_at == policy.policy_reviewed_at
    assert evaluation.fresh_qualified_count == 1
    assert evaluation.stale_qualified_count == 0
    assert evaluation.blocked_count == 1
    assert all(value is False for value in evaluation.safety.values())

    fresh = next(
        item
        for item in evaluation.decisions
        if item.evaluation_disposition is StatusEvaluationDisposition.FRESH_QUALIFIED
    )
    blocked = next(
        item
        for item in evaluation.decisions
        if item.evaluation_disposition
        is StatusEvaluationDisposition.BLOCKED_BY_QUALIFICATION
    )
    assert fresh.qualification_disposition is FieldEvidenceQualificationDisposition.QUALIFIED
    assert (
        fresh.policy_disposition
        is StatusClassificationPolicyDisposition.ELIGIBLE_FOR_LATER_CLASSIFICATION
    )
    assert fresh.fresh_until is not None
    assert blocked.qualification_disposition is FieldEvidenceQualificationDisposition.REJECTED
    assert (
        blocked.policy_disposition
        is StatusClassificationPolicyDisposition.BLOCKED_BY_QUALIFICATION
    )
    assert blocked.fresh_until is None

    payload = evaluation.to_dict()
    assert "facts" not in payload
    assert "status" not in payload
    assert payload["safety"]["fact_status_mutation_authorized"] is False
    assert payload["safety"]["supported_fact_authorized"] is False
    assert payload["safety"]["stale_fact_authorized"] is False
    assert payload["safety"]["conflicted_fact_authorized"] is False


def test_exact_deadline_is_fresh_and_one_microsecond_later_is_stale() -> None:
    inputs = _build_inputs()
    policy = inputs["policy"]
    eligible = next(
        item
        for item in policy.decisions
        if item.disposition
        is StatusClassificationPolicyDisposition.ELIGIBLE_FOR_LATER_CLASSIFICATION
    )
    assert eligible.fresh_until is not None

    at_deadline = _evaluate(inputs, eligible.fresh_until)
    assert all(
        item.evaluation_disposition is StatusEvaluationDisposition.FRESH_QUALIFIED
        for item in at_deadline.decisions
    )

    after_deadline = _evaluate(
        inputs,
        eligible.fresh_until + datetime.timedelta(microseconds=1),
    )
    assert all(
        item.evaluation_disposition is StatusEvaluationDisposition.STALE_QUALIFIED
        for item in after_deadline.decisions
    )


def test_classification_before_policy_review_or_at_after_kickoff_fails_closed() -> None:
    inputs = _build_inputs()
    policy = inputs["policy"]

    invalid = (
        policy.policy_reviewed_at - datetime.timedelta(microseconds=1),
        policy.kickoff,
        policy.kickoff + datetime.timedelta(microseconds=1),
    )
    for classified_at in invalid:
        with pytest.raises(
            FotMobReviewedMatchDetailsStatusEvaluationError,
            match="classified_at",
        ):
            _evaluate(inputs, classified_at)


def test_classification_timestamp_requires_exact_datetime_timezone_utc() -> None:
    inputs = _build_inputs()
    policy = inputs["policy"]
    plus_one = datetime.timezone(datetime.timedelta(hours=1))

    with pytest.raises(
        FotMobReviewedMatchDetailsStatusEvaluationError,
        match="exact datetime.timezone.utc",
    ):
        _evaluate(
            inputs,
            policy.policy_reviewed_at.replace(tzinfo=plus_one),
        )


def test_policy_bytes_are_exact_immutable_and_full_chain_revalidated() -> None:
    inputs = _build_inputs()
    policy = inputs["policy"]

    with pytest.raises(
        FotMobReviewedMatchDetailsStatusEvaluationError,
        match="policy_bytes must be exact immutable bytes",
    ):
        evaluate_reviewed_match_details_status_policy(
            evidence=inputs["evidence"],
            evidence_receipt_bytes=inputs["receipt"],
            manifest_bytes=inputs["manifest"],
            raw_bytes=inputs["raw"],
            assessment=inputs["assessment"],
            assessment_bytes=inputs["assessment_bytes"],
            review=inputs["review"],
            review_bytes=inputs["review_bytes"],
            fact_bundle=inputs["fact_bundle"],
            fact_bundle_bytes=inputs["fact_bytes"],
            qualification=inputs["qualification"],
            qualification_bytes=inputs["qualification_bytes"],
            policy=policy,
            policy_bytes=bytearray(inputs["policy_bytes"]),
            classified_at=policy.policy_reviewed_at,
        )

    corrupted = inputs["policy_bytes"][:-1] + b"X"
    with pytest.raises(
        FotMobReviewedMatchDetailsStatusEvaluationError,
        match="PR #60 policy failed exact full-chain revalidation|policy_bytes differ",
    ):
        evaluate_reviewed_match_details_status_policy(
            evidence=inputs["evidence"],
            evidence_receipt_bytes=inputs["receipt"],
            manifest_bytes=inputs["manifest"],
            raw_bytes=inputs["raw"],
            assessment=inputs["assessment"],
            assessment_bytes=inputs["assessment_bytes"],
            review=inputs["review"],
            review_bytes=inputs["review_bytes"],
            fact_bundle=inputs["fact_bundle"],
            fact_bundle_bytes=inputs["fact_bytes"],
            qualification=inputs["qualification"],
            qualification_bytes=inputs["qualification_bytes"],
            policy=policy,
            policy_bytes=corrupted,
            classified_at=policy.policy_reviewed_at,
        )


def test_evaluation_canonical_bytes_hash_and_revalidation_are_deterministic() -> None:
    inputs = _build_inputs()
    evaluation = _evaluate(inputs, inputs["policy"].policy_reviewed_at)
    first = canonical_reviewed_match_details_status_evaluation_bytes(evaluation)
    second = canonical_reviewed_match_details_status_evaluation_bytes(
        dataclasses.replace(evaluation)
    )

    assert first == second
    assert sha256_reviewed_match_details_status_evaluation(evaluation) == __import__(
        "hashlib"
    ).sha256(first).hexdigest()
    rebuilt = _revalidate(inputs, evaluation, first)
    assert canonical_reviewed_match_details_status_evaluation_bytes(rebuilt) == first


def test_wrong_evaluation_bytes_fail_closed() -> None:
    inputs = _build_inputs()
    evaluation = _evaluate(inputs, inputs["policy"].policy_reviewed_at)
    exact = canonical_reviewed_match_details_status_evaluation_bytes(evaluation)

    with pytest.raises(
        FotMobReviewedMatchDetailsStatusEvaluationError,
        match="evaluation_bytes are not exact canonical PR #61 bytes",
    ):
        _revalidate(inputs, evaluation, exact[:-1] + b"X")

    with pytest.raises(
        FotMobReviewedMatchDetailsStatusEvaluationError,
        match="evaluation_bytes must be exact immutable bytes",
    ):
        _revalidate(inputs, evaluation, bytearray(exact))


def test_forced_nested_disposition_mutation_is_rejected_by_local_invariants() -> None:
    inputs = _build_inputs()
    evaluation = _evaluate(inputs, inputs["policy"].policy_reviewed_at)
    decision = evaluation.decisions[0]
    original = decision.evaluation_disposition
    replacement = (
        StatusEvaluationDisposition.STALE_QUALIFIED
        if original is StatusEvaluationDisposition.FRESH_QUALIFIED
        else StatusEvaluationDisposition.FRESH_QUALIFIED
    )
    object.__setattr__(decision, "evaluation_disposition", replacement)

    with pytest.raises(
        FotMobReviewedMatchDetailsStatusEvaluationError,
        match="nested evaluation decision|disagrees with exact PR #60 freshness semantics",
    ):
        canonical_reviewed_match_details_status_evaluation_bytes(evaluation)


def test_forced_blocked_decision_cannot_become_fresh_or_gain_deadline() -> None:
    inputs = _build_inputs(
        {"synthetic_label": FieldEvidenceQualificationDisposition.REJECTED}
    )
    evaluation = _evaluate(inputs, inputs["policy"].policy_reviewed_at)
    blocked = next(
        item
        for item in evaluation.decisions
        if item.evaluation_disposition
        is StatusEvaluationDisposition.BLOCKED_BY_QUALIFICATION
    )
    object.__setattr__(blocked, "evaluation_disposition", StatusEvaluationDisposition.FRESH_QUALIFIED)
    object.__setattr__(blocked, "fresh_until", evaluation.policy_reviewed_at)

    with pytest.raises(
        FotMobReviewedMatchDetailsStatusEvaluationError,
        match="nested evaluation decision|blocked policy decisions",
    ):
        canonical_reviewed_match_details_status_evaluation_bytes(evaluation)


def test_coordinated_policy_and_evaluation_fact_hash_forgery_fails_full_chain_replay() -> None:
    inputs = _build_inputs()
    evaluation = _evaluate(inputs, inputs["policy"].policy_reviewed_at)
    policy = inputs["policy"]
    forged_hash = "1" * 64

    policy_decision = policy.decisions[0]
    object.__setattr__(policy_decision, "fact_sha256", forged_hash)
    evaluation_decision = evaluation.decisions[0]
    object.__setattr__(evaluation_decision, "fact_sha256", forged_hash)

    forged_policy_bytes = canonical_reviewed_match_details_status_classification_policy_bytes(
        policy
    )
    forged_evaluation_bytes = canonical_reviewed_match_details_status_evaluation_bytes(
        evaluation
    )
    inputs["policy_bytes"] = forged_policy_bytes

    with pytest.raises(
        FotMobReviewedMatchDetailsStatusEvaluationError,
        match="PR #60 policy failed exact full-chain revalidation|PR #61 evaluation failed exact full-chain revalidation",
    ):
        _revalidate(inputs, evaluation, forged_evaluation_bytes)


def test_source_module_has_no_fact_status_snapshot_model_pricing_or_network_authority() -> None:
    module_path = (
        Path(__file__).parents[1]
        / "domain"
        / "fotmob_reviewed_match_details_status_evaluator.py"
    )
    source = module_path.read_text(encoding="utf-8")

    forbidden = (
        "FixtureIntelligenceFact",
        "IntelligenceFactStatus",
        "build_snapshot",
        "SOURCE_CAPABILITY_REGISTRY",
        "prediction_engine",
        "requests.",
        "httpx.",
        "aiohttp.",
        "socket.",
        "sportybet",
    )
    for token in forbidden:
        assert token not in source
