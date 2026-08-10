from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from domain.fixture_intelligence import (
    FixtureIntelligenceFact,
    IntelligenceCategory,
    IntelligenceFactStatus,
    SourceRole,
    build_snapshot,
)
from domain.fixture_model_features import (
    ModelFeatureBlocker,
    ModelFeatureId,
    ModelFeatureStatus,
    build_model_feature_snapshot,
)
from domain.fotmob_reviewed_match_details_structure import JsonValueKind
from domain.fotmob_reviewed_match_details_unverified_candidates import (
    canonical_reviewed_match_details_unverified_candidate_bundle_bytes,
)
from domain.fotmob_reviewed_match_details_unverified_facts import (
    EVIDENCE_ROOT,
    FotMobReviewedMatchDetailsUnverifiedFactError,
    ReviewedMatchDetailsUnverifiedFactBundle,
    build_reviewed_match_details_unverified_fact_bundle,
    canonical_reviewed_match_details_unverified_fact_bundle_bytes,
    sha256_reviewed_match_details_unverified_fact_bundle,
)


def _pr55_helper():
    helper_path = Path(__file__).with_name(
        "test_fotmob_reviewed_match_details_unverified_candidates.py"
    )
    spec = importlib.util.spec_from_file_location("_athena_pr55_fact_helper", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PR #55 helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _approved(pointer: str, kind: JsonValueKind, category: IntelligenceCategory, field: str):
    helper = _pr55_helper()
    return helper._approved(pointer, kind, category, field)


def _candidate_chain(raw: bytes, decisions):
    helper = _pr55_helper()
    candidate_bundle, chain = helper._build(raw, tuple(decisions))
    candidate_bytes = canonical_reviewed_match_details_unverified_candidate_bundle_bytes(
        candidate_bundle
    )
    return candidate_bundle, candidate_bytes, chain


def _fact_bundle(raw: bytes, decisions):
    candidate_bundle, candidate_bytes, chain = _candidate_chain(raw, decisions)
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain
    fact_bundle = build_reviewed_match_details_unverified_fact_bundle(
        evidence=evidence,
        evidence_receipt_bytes=receipt,
        manifest_bytes=manifest,
        raw_bytes=raw,
        assessment=assessment,
        assessment_bytes=assessment_bytes,
        review=review,
        review_bytes=review_bytes,
        candidate_bundle=candidate_bundle,
        candidate_bundle_bytes=candidate_bytes,
    )
    return fact_bundle, candidate_bundle, candidate_bytes, chain


def test_exact_candidates_become_only_unverified_fixture_intelligence_facts() -> None:
    raw = b'{"alpha":{"label":"ok","value":100}}'
    decisions = (
        _approved(
            "/alpha/value",
            JsonValueKind.INTEGER,
            IntelligenceCategory.MATCH_CONTEXT,
            "synthetic_metric",
        ),
        _approved(
            "/alpha/label",
            JsonValueKind.STRING,
            IntelligenceCategory.FIXTURE_CONTEXT,
            "synthetic_label",
        ),
    )
    bundle, candidates, candidate_bytes, _ = _fact_bundle(raw, decisions)

    assert type(bundle) is ReviewedMatchDetailsUnverifiedFactBundle
    assert len(bundle.facts) == len(candidates.candidates) == 2
    assert all(type(item) is FixtureIntelligenceFact for item in bundle.facts)
    assert all(item.status is IntelligenceFactStatus.UNVERIFIED for item in bundle.facts)
    assert all(item.source_role is SourceRole.PRIMARY_FOOTBALL_CONTEXT for item in bundle.facts)
    assert all(item.source_provider == "fotmob_match_details_reviewed" for item in bundle.facts)
    assert all(item.observed_at == candidates.observed_at for item in bundle.facts)
    assert all(item.evidence_sha256 == candidates.raw_sha256 for item in bundle.facts)
    assert all(item.evidence_file_path == bundle.evidence_file_path for item in bundle.facts)
    assert all(item.notes is None for item in bundle.facts)
    assert bundle.candidate_bundle_size == len(candidate_bytes)
    assert all(value is False for value in bundle.safety.values())

    assert bundle.fixture_identifier == candidates.fixture_identifier
    assert bundle.source_match_id == candidates.source_match_id
    assert bundle.kickoff == candidates.kickoff
    assert bundle.observed_at == candidates.observed_at
    assert bundle.raw_sha256 == candidates.raw_sha256

    by_field = {item.field: item for item in bundle.facts}
    assert by_field["synthetic_metric"].value == 100
    assert by_field["synthetic_label"].value == "ok"

    canonical = canonical_reviewed_match_details_unverified_fact_bundle_bytes(bundle)
    assert canonical.endswith(b"\n")
    assert len(sha256_reviewed_match_details_unverified_fact_bundle(bundle)) == 64


def test_serialized_bundle_keeps_fixture_identity_at_bundle_level() -> None:
    raw = b'{"alpha":{"value":100}}'
    decision = _approved(
        "/alpha/value",
        JsonValueKind.INTEGER,
        IntelligenceCategory.MATCH_CONTEXT,
        "synthetic_metric",
    )
    bundle, candidates, _, _ = _fact_bundle(raw, (decision,))
    payload = bundle.to_dict()

    assert payload["fixture_identifier"] == candidates.fixture_identifier
    assert payload["source_match_id"] == candidates.source_match_id
    assert payload["kickoff"].endswith("Z")
    assert payload["observed_at"].endswith("Z")
    assert payload["raw_sha256"] == candidates.raw_sha256
    assert payload["candidate_bundle"]["fixture_identifier"] == payload["fixture_identifier"]
    assert payload["candidate_bundle"]["source_match_id"] == payload["source_match_id"]


def test_evidence_path_is_exact_pr50_durable_response_path() -> None:
    raw = b'{"alpha":{"value":100}}'
    decision = _approved(
        "/alpha/value",
        JsonValueKind.INTEGER,
        IntelligenceCategory.MATCH_CONTEXT,
        "synthetic_metric",
    )
    bundle, candidates, _, _ = _fact_bundle(raw, (decision,))
    timestamp = candidates.observed_at.strftime("%Y%m%dT%H%M%S%fZ")
    expected_identifier = (
        f"{candidates.source_match_id}--{timestamp}--{candidates.raw_sha256}"
    )
    assert bundle.evidence_file_path == (
        f"{EVIDENCE_ROOT}/{expected_identifier}/response.json"
    )
    assert bundle.facts[0].evidence_file_path == bundle.evidence_file_path


def test_pr55_candidate_bytes_and_full_semantic_rebuild_are_required() -> None:
    raw = b'{"alpha":{"value":100}}'
    decision = _approved(
        "/alpha/value",
        JsonValueKind.INTEGER,
        IntelligenceCategory.MATCH_CONTEXT,
        "synthetic_metric",
    )
    candidates, candidate_bytes, chain = _candidate_chain(raw, (decision,))
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain

    with pytest.raises(
        FotMobReviewedMatchDetailsUnverifiedFactError,
        match="exact canonical PR #55 bytes",
    ):
        build_reviewed_match_details_unverified_fact_bundle(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            candidate_bundle=candidates,
            candidate_bundle_bytes=candidate_bytes + b"\n",
        )

    object.__setattr__(candidates.candidates[0], "value", 101)
    with pytest.raises(
        FotMobReviewedMatchDetailsUnverifiedFactError,
        match="differs from exact semantic rebuild",
    ):
        build_reviewed_match_details_unverified_fact_bundle(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            candidate_bundle=candidates,
            candidate_bundle_bytes=canonical_reviewed_match_details_unverified_candidate_bundle_bytes(
                candidates
            ),
        )


def test_fact_status_value_or_evidence_path_mutation_fails_bundle_canonicalization() -> None:
    raw = b'{"alpha":{"value":100}}'
    decision = _approved(
        "/alpha/value",
        JsonValueKind.INTEGER,
        IntelligenceCategory.MATCH_CONTEXT,
        "synthetic_metric",
    )

    bundle, _, _, _ = _fact_bundle(raw, (decision,))
    object.__setattr__(bundle.facts[0], "status", IntelligenceFactStatus.SUPPORTED)
    with pytest.raises(
        FotMobReviewedMatchDetailsUnverifiedFactError,
        match="status-preserving",
    ):
        canonical_reviewed_match_details_unverified_fact_bundle_bytes(bundle)

    bundle, _, _, _ = _fact_bundle(raw, (decision,))
    object.__setattr__(bundle.facts[0], "value", 101)
    with pytest.raises(
        FotMobReviewedMatchDetailsUnverifiedFactError,
        match="status-preserving",
    ):
        canonical_reviewed_match_details_unverified_fact_bundle_bytes(bundle)

    bundle, _, _, _ = _fact_bundle(raw, (decision,))
    object.__setattr__(bundle.facts[0], "evidence_file_path", "forged/response.json")
    with pytest.raises(
        FotMobReviewedMatchDetailsUnverifiedFactError,
        match="status-preserving",
    ):
        canonical_reviewed_match_details_unverified_fact_bundle_bytes(bundle)


def test_fact_bundle_cannot_upgrade_safety() -> None:
    raw = b'{"alpha":{"value":100}}'
    decision = _approved(
        "/alpha/value",
        JsonValueKind.INTEGER,
        IntelligenceCategory.MATCH_CONTEXT,
        "synthetic_metric",
    )
    bundle, _, _, _ = _fact_bundle(raw, (decision,))
    unsafe = dict(bundle.safety)
    unsafe["supported_status_authorized"] = True
    object.__setattr__(bundle, "safety", unsafe)
    with pytest.raises(FotMobReviewedMatchDetailsUnverifiedFactError, match="safety"):
        canonical_reviewed_match_details_unverified_fact_bundle_bytes(bundle)


def test_pr31_blocks_model_feature_when_adapter_fact_is_unverified() -> None:
    raw = b'{"form":{"home":0.75}}'
    decision = _approved(
        "/form/home",
        JsonValueKind.NUMBER,
        IntelligenceCategory.FORM,
        "home_form",
    )
    bundle, _, _, chain = _fact_bundle(raw, (decision,))
    review = chain[-2]

    intelligence = build_snapshot(
        fixture_identifier=bundle.fixture_identifier,
        kickoff=bundle.kickoff,
        as_of=review.reviewed_at,
        raw_facts=list(bundle.facts),
    )
    features = build_model_feature_snapshot(intelligence)
    home_form = next(
        item for item in features.features if item.feature_id is ModelFeatureId.HOME_FORM
    )

    assert home_form.status is ModelFeatureStatus.BLOCKED
    assert home_form.value is None
    assert ModelFeatureBlocker.UNVERIFIED_EVIDENCE_PRESENT in home_form.blockers
    assert ModelFeatureBlocker.NO_SUPPORTED_EVIDENCE in home_form.blockers
    assert bundle.raw_sha256 in home_form.evidence_sha256s


def test_adapter_does_not_build_snapshot_or_supported_fact() -> None:
    raw = b'{"alpha":{"value":100}}'
    decision = _approved(
        "/alpha/value",
        JsonValueKind.INTEGER,
        IntelligenceCategory.MATCH_CONTEXT,
        "synthetic_metric",
    )
    bundle, _, _, _ = _fact_bundle(raw, (decision,))
    payload = bundle.to_dict()

    assert "category_coverage" not in payload
    assert "conflicted_fields" not in payload
    assert "unverified_fields" not in payload
    assert "as_of" not in payload
    assert all(item["status"] == "UNVERIFIED" for item in payload["facts"])
