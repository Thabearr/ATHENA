from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
import inspect
import json
from functools import lru_cache
from pathlib import Path

import pytest

from tests.support.module_loader import load_test_module

from domain.fixture_intelligence import (
    FixtureIntelligenceSnapshot,
    IntelligenceCategory,
    IntelligenceFactStatus,
    build_snapshot,
    canonical_snapshot_bytes,
)
from domain.fixture_model_features import (
    ModelFeatureBlocker,
    ModelFeatureId,
    ModelFeatureStatus,
    build_model_feature_snapshot,
)
from domain.fotmob_reviewed_match_details_fixture_intelligence_snapshot import (
    DATASET_NAME,
    SCHEMA_VERSION,
    FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError,
    ReviewedMatchDetailsFixtureIntelligenceSnapshot,
    build_reviewed_match_details_fixture_intelligence_snapshot,
    canonical_reviewed_match_details_fixture_intelligence_snapshot_bytes,
    revalidate_reviewed_match_details_fixture_intelligence_snapshot,
    sha256_reviewed_match_details_fixture_intelligence_snapshot,
)
from domain.fotmob_reviewed_match_details_snapshot_candidate_admission import (
    SnapshotCandidateAdmissionDisposition,
    SnapshotCandidateCompletenessAttestation,
)
from domain.fotmob_reviewed_match_details_field_evidence_qualification import (
    FieldEvidenceQualificationDisposition,
)
from domain.fotmob_reviewed_match_details_structure import JsonValueKind


UTC = datetime.timezone.utc


@lru_cache(maxsize=1)
def _pr64_helper():
    return load_test_module("test_fotmob_reviewed_match_details_snapshot_candidate_admission")


def _chain_bundle(*chains, disposition=SnapshotCandidateAdmissionDisposition.ADMITTED, reviewed_at=None):
    helper = _pr64_helper()
    candidate, candidate_bytes = helper._candidate(*chains)
    attestation = (
        SnapshotCandidateCompletenessAttestation.NO_KNOWN_OMITTED_REVIEWED_MATERIALIZATIONS
        if disposition is SnapshotCandidateAdmissionDisposition.ADMITTED
        else SnapshotCandidateCompletenessAttestation.NOT_ATTESTED
    )
    admission = helper._admit(
        inputs=tuple(chains),
        candidate=candidate,
        candidate_bytes=candidate_bytes,
        disposition=disposition,
        attestation=attestation,
        reviewed_at=candidate.classified_at if reviewed_at is None else reviewed_at,
    )
    admission_bytes = helper.canonical_reviewed_match_details_snapshot_candidate_admission_bytes(
        admission
    )
    return tuple(chains), candidate, candidate_bytes, admission, admission_bytes


def _one_bundle(*, disposition=SnapshotCandidateAdmissionDisposition.ADMITTED, reviewed_at=None):
    chain = _pr64_helper()._pr63_helper()._one_approved_chain()
    return _chain_bundle(chain, disposition=disposition, reviewed_at=reviewed_at)


def _build(bundle=None):
    if bundle is None:
        bundle = _one_bundle()
    inputs, candidate, candidate_bytes, admission, admission_bytes = bundle
    artifact = build_reviewed_match_details_fixture_intelligence_snapshot(
        materialization_inputs=inputs,
        candidate_set=candidate,
        candidate_set_bytes=candidate_bytes,
        admission=admission,
        admission_bytes=admission_bytes,
    )
    artifact_bytes = canonical_reviewed_match_details_fixture_intelligence_snapshot_bytes(
        artifact
    )
    return artifact, artifact_bytes, bundle


def _revalidate(artifact, artifact_bytes, bundle):
    inputs, candidate, candidate_bytes, admission, admission_bytes = bundle
    return revalidate_reviewed_match_details_fixture_intelligence_snapshot(
        materialization_inputs=inputs,
        candidate_set=candidate,
        candidate_set_bytes=candidate_bytes,
        admission=admission,
        admission_bytes=admission_bytes,
        artifact=artifact,
        artifact_bytes=artifact_bytes,
    )


def _feature(snapshot, feature_id):
    result = build_model_feature_snapshot(snapshot)
    return next(item for item in result.features if item.feature_id is feature_id)


def _rejected_home_form_inputs(value: int):
    pr62 = _pr64_helper()._pr63_helper()._pr62_helper()
    pr60 = pr62._pr61_helper()._pr60_helper()
    pr58 = pr60._pr58_helper()
    raw = json.dumps({"alpha": {"value": value}}, separators=(",", ":")).encode()
    approved = (
        pr58._approved(
            "/alpha/value",
            JsonValueKind.INTEGER,
            IntelligenceCategory.FORM,
            "home_form",
        ),
    )
    (
        policy,
        policy_bytes,
        qualification,
        qualification_bytes,
        fact_bundle,
        fact_bytes,
        chain,
    ) = pr60._build_policy(
        raw,
        approved,
        {"home_form": FieldEvidenceQualificationDisposition.REJECTED},
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


def test_exact_admitted_chain_creates_one_real_pr30_snapshot() -> None:
    artifact, _, bundle = _build()
    candidate = bundle[1]

    assert type(artifact.snapshot) is FixtureIntelligenceSnapshot
    assert artifact.fixture_identifier == candidate.fixture_identifier
    assert artifact.source_match_id == candidate.source_match_id
    assert artifact.kickoff == candidate.kickoff
    assert artifact.classified_at == candidate.classified_at
    assert artifact.snapshot.fixture_identifier == candidate.fixture_identifier
    assert artifact.snapshot.kickoff == candidate.kickoff
    assert artifact.snapshot.as_of == candidate.classified_at


def test_rejected_admission_fails_closed_without_fallback_snapshot() -> None:
    with pytest.raises(
        FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError,
        match="only an exact ADMITTED",
    ):
        _build(_one_bundle(disposition=SnapshotCandidateAdmissionDisposition.REJECTED))


def test_snapshot_as_of_is_classified_at_not_later_admission_review_time() -> None:
    preliminary = _one_bundle()
    candidate = preliminary[1]
    reviewed_at = candidate.classified_at + datetime.timedelta(seconds=1)
    artifact, _, _ = _build(_one_bundle(reviewed_at=reviewed_at))

    assert artifact.admission_reviewed_at == reviewed_at
    assert artifact.snapshot.as_of == candidate.classified_at
    assert artifact.snapshot.as_of != reviewed_at


def test_snapshot_contains_every_and_only_candidate_fact_without_reclassification() -> None:
    artifact, _, bundle = _build()
    candidate = bundle[1]

    assert artifact.fact_count == len(candidate.facts) == len(artifact.snapshot.facts)
    expected = build_snapshot(
        candidate.fixture_identifier,
        candidate.kickoff,
        candidate.classified_at,
        candidate.facts,
    )
    assert canonical_snapshot_bytes(expected) == canonical_snapshot_bytes(artifact.snapshot)
    assert sorted(fact.evidence_sha256 for fact in artifact.snapshot.facts) == sorted(
        fact.evidence_sha256 for fact in candidate.facts
    )
    assert sorted((fact.status for fact in artifact.snapshot.facts), key=lambda item: item.value) == sorted(
        (fact.status for fact in candidate.facts), key=lambda item: item.value
    )


def test_no_subset_selection_api_exists() -> None:
    parameters = set(inspect.signature(build_reviewed_match_details_fixture_intelligence_snapshot).parameters)
    assert not parameters & {
        "selected_facts", "included_fields", "exclude_stale", "exclude_unverified",
        "preferred_sources", "allowed_categories", "model_fields_only", "as_of",
    }


def test_differing_supported_values_survive_and_pr30_pr31_derive_conflict() -> None:
    helper = _pr64_helper()._pr63_helper()
    artifact, _, _ = _build(
        _chain_bundle(helper._one_approved_chain(10), helper._one_approved_chain(20))
    )

    facts = [fact for fact in artifact.snapshot.facts if fact.field == "home_form"]
    assert {fact.value for fact in facts} == {10, 20}
    assert all(fact.status is IntelligenceFactStatus.SUPPORTED for fact in facts)
    assert ("FORM", "home_form") in artifact.snapshot.conflicted_fields
    resolution = _feature(artifact.snapshot, ModelFeatureId.HOME_FORM)
    assert resolution.status is ModelFeatureStatus.BLOCKED
    assert resolution.blockers == (ModelFeatureBlocker.CONFLICTED_EVIDENCE,)


def test_one_fresh_supported_mapped_scalar_can_be_available_in_pr31_test_only() -> None:
    artifact, _, _ = _build()
    resolution = _feature(artifact.snapshot, ModelFeatureId.HOME_FORM)
    assert resolution.status is ModelFeatureStatus.AVAILABLE
    assert resolution.value == 100.0
    assert artifact.safety["model_feature_authorized"] is False


def test_stale_mapped_fact_remains_stale_and_pr31_blocks() -> None:
    helper = _pr64_helper()._pr63_helper()
    pr62 = helper._pr62_helper()
    inputs = pr62._home_form_inputs(100)
    fresh_until = inputs["policy"].decisions[0].fresh_until
    assert fresh_until is not None
    chain = helper._chain(inputs, fresh_until + datetime.timedelta(microseconds=1))
    artifact, _, _ = _build(_chain_bundle(chain))

    assert artifact.snapshot.facts[0].status is IntelligenceFactStatus.STALE
    resolution = _feature(artifact.snapshot, ModelFeatureId.HOME_FORM)
    assert resolution.status is ModelFeatureStatus.BLOCKED
    assert ModelFeatureBlocker.STALE_EVIDENCE_PRESENT in resolution.blockers


def test_unverified_mapped_fact_remains_unverified_and_pr31_blocks() -> None:
    helper = _pr64_helper()._pr63_helper()
    inputs = _rejected_home_form_inputs(100)
    chain = helper._chain(inputs, inputs["policy"].policy_reviewed_at)
    artifact, _, _ = _build(_chain_bundle(chain))

    assert artifact.snapshot.facts[0].status is IntelligenceFactStatus.UNVERIFIED
    assert artifact.snapshot.unverified_fields == (("FORM", "home_form"),)
    resolution = _feature(artifact.snapshot, ModelFeatureId.HOME_FORM)
    assert resolution.status is ModelFeatureStatus.BLOCKED
    assert ModelFeatureBlocker.UNVERIFIED_EVIDENCE_PRESENT in resolution.blockers


def test_incomplete_model_coverage_still_constructs_snapshot() -> None:
    artifact, _, _ = _build()
    result = build_model_feature_snapshot(artifact.snapshot)
    assert type(artifact.snapshot) is FixtureIntelligenceSnapshot
    assert any(item.status is ModelFeatureStatus.MISSING for item in result.features)


def test_contract_dataset_wrapper_immutability_and_downstream_safety() -> None:
    artifact, _, _ = _build()
    assert SCHEMA_VERSION == 1 and type(SCHEMA_VERSION) is int
    assert DATASET_NAME == "athena-fotmob-reviewed-match-details-fixture-intelligence-snapshot-v1"
    assert artifact.safety == {key: False for key in artifact.safety}
    assert "snapshot_creation_authorized" not in artifact.safety
    with pytest.raises(dataclasses.FrozenInstanceError):
        artifact.dataset_name = "forged"
    with pytest.raises(TypeError):
        artifact.safety["model_feature_authorized"] = True


def test_exact_candidate_admission_and_snapshot_byte_anchors() -> None:
    artifact, _, bundle = _build()
    candidate_bytes, admission_bytes = bundle[2], bundle[4]
    snapshot_bytes = canonical_snapshot_bytes(artifact.snapshot)

    assert artifact.candidate_set_sha256 == hashlib.sha256(candidate_bytes).hexdigest()
    assert artifact.candidate_set_size == len(candidate_bytes)
    assert artifact.admission_sha256 == hashlib.sha256(admission_bytes).hexdigest()
    assert artifact.admission_size == len(admission_bytes)
    assert artifact.snapshot_sha256 == hashlib.sha256(snapshot_bytes).hexdigest()
    assert artifact.snapshot_size == len(snapshot_bytes)


def test_wrong_candidate_or_admission_bytes_are_rejected() -> None:
    inputs, candidate, candidate_bytes, admission, admission_bytes = _one_bundle()
    for bad_candidate, bad_admission in (
        (b"{}\n", admission_bytes),
        (candidate_bytes, b"{}\n"),
    ):
        with pytest.raises(FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError):
            build_reviewed_match_details_fixture_intelligence_snapshot(
                materialization_inputs=inputs,
                candidate_set=candidate,
                candidate_set_bytes=bad_candidate,
                admission=admission,
                admission_bytes=bad_admission,
            )


@pytest.mark.parametrize(
    "attribute,replacement",
    [
        ("candidate_set_sha256", "0" * 64),
        ("candidate_set_size", 1),
        ("admission_sha256", "0" * 64),
        ("admission_size", 1),
        ("fixture_identifier", "FOTMOB:9"),
        ("source_match_id", "9"),
        ("kickoff", datetime.datetime(2026, 1, 2, tzinfo=UTC)),
        ("classified_at", datetime.datetime(2026, 1, 1, tzinfo=UTC)),
        ("materialization_sha256s", ("0" * 64,)),
        ("materialized_fact_sha256s", ("0" * 64,)),
        ("snapshot_sha256", "0" * 64),
        ("snapshot_size", 1),
    ],
)
def test_wrapper_anchor_or_identity_drift_fails_full_replay(attribute, replacement) -> None:
    artifact, artifact_bytes, bundle = _build()
    object.__setattr__(artifact, attribute, replacement)
    with pytest.raises(FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError):
        _revalidate(artifact, artifact_bytes, bundle)


@pytest.mark.parametrize(
    "target,attribute,replacement",
    [
        ("snapshot", "fixture_identifier", "FOTMOB:9"),
        ("snapshot", "as_of", datetime.datetime(2026, 1, 1, tzinfo=UTC)),
        ("fact", "value", 999),
        ("fact", "status", IntelligenceFactStatus.STALE),
        ("fact", "evidence_sha256", "f" * 64),
        ("snapshot", "conflicted_fields", (("FORM", "home_form"),)),
    ],
)
def test_forced_nested_snapshot_or_fact_mutation_is_rejected(target, attribute, replacement) -> None:
    artifact, _, _ = _build()
    subject = artifact.snapshot if target == "snapshot" else artifact.snapshot.facts[0]
    object.__setattr__(subject, attribute, replacement)
    with pytest.raises(FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError):
        canonical_reviewed_match_details_fixture_intelligence_snapshot_bytes(artifact)


def test_coordinated_candidate_snapshot_and_local_hash_forgery_fails_full_replay() -> None:
    artifact, artifact_bytes, bundle = _build()
    candidate = bundle[1]
    object.__setattr__(candidate.facts[0], "value", 999)
    object.__setattr__(artifact.snapshot.facts[0], "value", 999)
    object.__setattr__(artifact, "snapshot_sha256", "0" * 64)
    with pytest.raises(FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError):
        _revalidate(artifact, artifact_bytes, bundle)


@pytest.mark.parametrize("bad_bytes", [bytearray(b"x"), memoryview(b"x"), "x", b"{}\n"])
def test_wrong_noncanonical_or_mutable_artifact_bytes_are_rejected(bad_bytes) -> None:
    artifact, _, bundle = _build()
    with pytest.raises(FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError):
        _revalidate(artifact, bad_bytes, bundle)


def test_canonical_wrapper_and_existing_pr30_snapshot_bytes_are_deterministic() -> None:
    artifact, exact_bytes, bundle = _build()
    rebuilt = _revalidate(artifact, exact_bytes, bundle)

    assert canonical_reviewed_match_details_fixture_intelligence_snapshot_bytes(rebuilt) == exact_bytes
    assert exact_bytes.endswith(b"\n")
    assert sha256_reviewed_match_details_fixture_intelligence_snapshot(artifact) == hashlib.sha256(exact_bytes).hexdigest()
    assert canonical_snapshot_bytes(artifact.snapshot) == canonical_snapshot_bytes(rebuilt.snapshot)
    assert json.loads(exact_bytes.decode("utf-8"))["snapshot"]["as_of"].endswith("Z")


def test_production_ast_uses_pr30_snapshot_only_and_no_downstream_boundaries() -> None:
    path = Path(__file__).parents[1] / "domain" / "fotmob_reviewed_match_details_fixture_intelligence_snapshot.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports, names, calls = [], [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
            names.extend(item.name for item in node.names)
        elif isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name): calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute): calls.append(node.func.attr)
    assert "build_snapshot" in names and "build_snapshot" in calls
    assert "canonical_snapshot_bytes" in names and "canonical_snapshot_bytes" in calls
    assert "build_model_feature_snapshot" not in names and "build_model_feature_snapshot" not in calls
    assert "domain.fixture_model_features" not in imports
    assert not [item for item in imports if item.split(".")[0] in {"http", "requests", "httpx", "aiohttp", "socket", "pathlib", "os"}]
    for forbidden in ("prediction_engine", "pricing", "sportybet", "betting"):
        assert forbidden not in imports and forbidden not in names and forbidden not in calls
