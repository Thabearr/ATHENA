from __future__ import annotations

import ast
import dataclasses
import datetime
import inspect
import json
from functools import lru_cache
from pathlib import Path

import pytest

from tests.support.module_loader import load_test_module

from domain.fixture_intelligence import FixtureIntelligenceSnapshot
from domain.fixture_model_features import FixtureModelFeatureError, build_model_feature_snapshot
from domain.fotmob_reviewed_match_details_snapshot_candidate_admission import (
    ADMISSION_SCOPE,
    DATASET_NAME,
    SCHEMA_VERSION,
    FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError,
    ReviewedMatchDetailsSnapshotCandidateAdmission,
    SnapshotCandidateAdmissionDisposition,
    SnapshotCandidateCompletenessAttestation,
    admit_reviewed_match_details_snapshot_candidate_set,
    canonical_reviewed_match_details_snapshot_candidate_admission_bytes,
    revalidate_reviewed_match_details_snapshot_candidate_admission,
    sha256_reviewed_match_details_snapshot_candidate_admission,
)


UTC = datetime.timezone.utc


@lru_cache(maxsize=1)
def _pr63_helper():
    return load_test_module("test_fotmob_reviewed_match_details_snapshot_candidate_set")


def _candidate(*chains):
    helper = _pr63_helper()
    candidate = helper._candidate(*chains)
    return candidate, helper.canonical_reviewed_match_details_snapshot_candidate_set_bytes(candidate)


def _one_candidate():
    helper = _pr63_helper()
    chain = helper._one_approved_chain()
    candidate, candidate_bytes = _candidate(chain)
    return (chain,), candidate, candidate_bytes


def _admit(
    *,
    inputs=None,
    candidate=None,
    candidate_bytes=None,
    disposition=SnapshotCandidateAdmissionDisposition.ADMITTED,
    attestation=SnapshotCandidateCompletenessAttestation.NO_KNOWN_OMITTED_REVIEWED_MATERIALIZATIONS,
    reviewed_at=None,
    reviewer_reference="review: PR64 synthetic admission",
    rationale="Reviewed the whole exact candidate set without subset selection.",
):
    if inputs is None:
        inputs, candidate, candidate_bytes = _one_candidate()
    return admit_reviewed_match_details_snapshot_candidate_set(
        materialization_inputs=inputs,
        candidate_set=candidate,
        candidate_set_bytes=candidate_bytes,
        disposition=disposition,
        completeness_attestation=attestation,
        reviewed_at=candidate.classified_at if reviewed_at is None else reviewed_at,
        reviewer_reference=reviewer_reference,
        rationale=rationale,
    )


def _canonical_admission(**kwargs):
    admission = _admit(**kwargs)
    return admission, canonical_reviewed_match_details_snapshot_candidate_admission_bytes(admission)


def test_admitted_exact_candidate_requires_exact_positive_attestation() -> None:
    admission, _ = _canonical_admission()
    assert admission.decision.disposition is SnapshotCandidateAdmissionDisposition.ADMITTED
    assert admission.decision.completeness_attestation is (
        SnapshotCandidateCompletenessAttestation.NO_KNOWN_OMITTED_REVIEWED_MATERIALIZATIONS
    )
    assert len(admission.admitted_candidate_set_identities) == 1
    identity = admission.admitted_candidate_set_identities[0]
    assert identity.candidate_set_sha256 == admission.decision.candidate_set_sha256
    assert identity.materialization_sha256s == admission.decision.materialization_sha256s
    assert identity.materialized_fact_sha256s == admission.decision.materialized_fact_sha256s


def test_rejected_exact_candidate_exposes_zero_admitted_identities() -> None:
    admission, _ = _canonical_admission(
        disposition=SnapshotCandidateAdmissionDisposition.REJECTED,
        attestation=SnapshotCandidateCompletenessAttestation.NOT_ATTESTED,
    )
    assert admission.decision.disposition is SnapshotCandidateAdmissionDisposition.REJECTED
    assert admission.admitted_candidate_set_identities == ()


@pytest.mark.parametrize(
    "disposition, attestation",
    [
        (SnapshotCandidateAdmissionDisposition.ADMITTED, SnapshotCandidateCompletenessAttestation.NOT_ATTESTED),
        (SnapshotCandidateAdmissionDisposition.REJECTED, SnapshotCandidateCompletenessAttestation.NO_KNOWN_OMITTED_REVIEWED_MATERIALIZATIONS),
        (SnapshotCandidateAdmissionDisposition.ADMITTED, "GLOBALLY_COMPLETE"),
    ],
)
def test_disposition_requires_its_exact_narrow_attestation(disposition, attestation) -> None:
    with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError):
        _admit(disposition=disposition, attestation=attestation)


def test_contract_scope_immutability_and_safety() -> None:
    admission, _ = _canonical_admission()
    assert SCHEMA_VERSION == 1 and type(SCHEMA_VERSION) is int
    assert DATASET_NAME == "athena-fotmob-reviewed-match-details-snapshot-candidate-admission-v1"
    assert ADMISSION_SCOPE == "EXACT_FIXTURE_CLASSIFICATION_MOMENT_CANDIDATE_SET_ONLY"
    assert admission.safety == {key: False for key in admission.safety}
    with pytest.raises(dataclasses.FrozenInstanceError):
        admission.dataset_name = "forged"
    with pytest.raises(TypeError):
        admission.safety["snapshot_creation_authorized"] = True


@pytest.mark.parametrize(
    "attribute, replacement",
    [
        ("candidate_set_sha256", "0" * 64),
        ("candidate_set_size", 1),
        ("fixture_identifier", "FOTMOB:9"),
        ("source_match_id", "9"),
        ("kickoff", datetime.datetime(2026, 1, 2, tzinfo=UTC)),
        ("classified_at", datetime.datetime(2026, 1, 1, tzinfo=UTC)),
        ("member_count", 99),
        ("fact_count", 99),
    ],
)
def test_decision_anchor_drift_is_rejected(attribute, replacement) -> None:
    admission, _ = _canonical_admission()
    object.__setattr__(admission.decision, attribute, replacement)
    with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError):
        canonical_reviewed_match_details_snapshot_candidate_admission_bytes(admission)


def test_member_and_fact_identity_drift_is_rejected() -> None:
    admission, _ = _canonical_admission()
    object.__setattr__(admission.decision, "materialization_sha256s", ("0" * 64,))
    with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError):
        canonical_reviewed_match_details_snapshot_candidate_admission_bytes(admission)

    admission, _ = _canonical_admission()
    object.__setattr__(admission.decision, "materialized_fact_sha256s", ("0" * 64,))
    with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError):
        canonical_reviewed_match_details_snapshot_candidate_admission_bytes(admission)


def test_review_time_chronology_and_exact_utc_are_fail_closed() -> None:
    inputs, candidate, candidate_bytes = _one_candidate()
    for reviewed_at in (
        candidate.classified_at - datetime.timedelta(microseconds=1),
        candidate.kickoff,
        candidate.classified_at.astimezone(datetime.timezone(datetime.timedelta(hours=1))),
    ):
        with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError):
            _admit(inputs=inputs, candidate=candidate, candidate_bytes=candidate_bytes, reviewed_at=reviewed_at)


@pytest.mark.parametrize("reviewer_reference, rationale", [("", "reason"), ("review", ""), (" review ", "reason"), ("review", " reason ")])
def test_reviewer_reference_and_rationale_are_required_exact_text(reviewer_reference, rationale) -> None:
    with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError):
        _admit(reviewer_reference=reviewer_reference, rationale=rationale)


def test_conflicting_stale_unverified_and_incomplete_coverage_can_still_be_admitted() -> None:
    helper = _pr63_helper()
    conflicting = _candidate(helper._one_approved_chain(10), helper._one_approved_chain(20))
    admission = _admit(inputs=(helper._one_approved_chain(10), helper._one_approved_chain(20)), candidate=conflicting[0], candidate_bytes=conflicting[1])
    assert len(admission.admitted_candidate_set_identities) == 1

    pr62 = helper._pr62_helper()
    stale_inputs = pr62._one_approved_inputs()
    fresh_until = stale_inputs["policy"].decisions[0].fresh_until
    assert fresh_until is not None
    stale_chain = helper._chain(stale_inputs, fresh_until + datetime.timedelta(microseconds=1))
    stale_candidate = _candidate(stale_chain)
    assert _admit(inputs=(stale_chain,), candidate=stale_candidate[0], candidate_bytes=stale_candidate[1]).decision.disposition is SnapshotCandidateAdmissionDisposition.ADMITTED

    blocked = helper._blocked_chain()
    blocked_candidate = _candidate(blocked)
    assert _admit(inputs=(blocked,), candidate=blocked_candidate[0], candidate_bytes=blocked_candidate[1]).decision.disposition is SnapshotCandidateAdmissionDisposition.ADMITTED


def test_admission_never_selects_member_or_fact_subset() -> None:
    signature = inspect.signature(admit_reviewed_match_details_snapshot_candidate_set)
    assert not ({"selected_facts", "accepted_members", "excluded_members", "preferred_sources"} & set(signature.parameters))
    admission, _ = _canonical_admission()
    assert admission.decision.fact_count == len(admission.decision.materialized_fact_sha256s)
    assert admission.decision.member_count == len(admission.decision.materialization_sha256s)


@pytest.mark.parametrize("attribute, replacement", [
    ("disposition", SnapshotCandidateAdmissionDisposition.REJECTED),
    ("completeness_attestation", SnapshotCandidateCompletenessAttestation.NOT_ATTESTED),
    ("reviewed_at", datetime.datetime(2026, 1, 1, tzinfo=UTC)),
    ("rationale", "forged rationale"),
])
def test_forced_decision_mutation_is_rejected_by_full_replay(attribute, replacement) -> None:
    inputs, candidate, candidate_bytes = _one_candidate()
    admission, admission_bytes = _canonical_admission(inputs=inputs, candidate=candidate, candidate_bytes=candidate_bytes)
    object.__setattr__(admission.decision, attribute, replacement)
    with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError):
        revalidate_reviewed_match_details_snapshot_candidate_admission(
            materialization_inputs=inputs, candidate_set=candidate, candidate_set_bytes=candidate_bytes,
            admission=admission, admission_bytes=admission_bytes,
        )


def test_forced_admitted_identity_mutation_and_coordinated_candidate_forgery_fail_replay() -> None:
    inputs, candidate, candidate_bytes = _one_candidate()
    admission, admission_bytes = _canonical_admission(inputs=inputs, candidate=candidate, candidate_bytes=candidate_bytes)
    object.__setattr__(admission.admitted_candidate_set_identities[0], "candidate_set_sha256", "0" * 64)
    with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError):
        canonical_reviewed_match_details_snapshot_candidate_admission_bytes(admission)

    admission, admission_bytes = _canonical_admission(inputs=inputs, candidate=candidate, candidate_bytes=candidate_bytes)
    object.__setattr__(candidate.facts[0], "value", 999)
    with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError):
        revalidate_reviewed_match_details_snapshot_candidate_admission(
            materialization_inputs=inputs, candidate_set=candidate, candidate_set_bytes=candidate_bytes,
            admission=admission, admission_bytes=admission_bytes,
        )


@pytest.mark.parametrize("bad_bytes", [bytearray(b"x"), memoryview(b"x"), "x", b"{}\n"])
def test_wrong_noncanonical_or_mutable_admission_bytes_are_rejected(bad_bytes) -> None:
    inputs, candidate, candidate_bytes = _one_candidate()
    admission, _ = _canonical_admission(inputs=inputs, candidate=candidate, candidate_bytes=candidate_bytes)
    with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError):
        revalidate_reviewed_match_details_snapshot_candidate_admission(
            materialization_inputs=inputs, candidate_set=candidate, candidate_set_bytes=candidate_bytes,
            admission=admission, admission_bytes=bad_bytes,
        )


def test_canonical_sha_and_exact_full_revalidation_are_deterministic() -> None:
    inputs, candidate, candidate_bytes = _one_candidate()
    admission, exact_bytes = _canonical_admission(inputs=inputs, candidate=candidate, candidate_bytes=candidate_bytes)
    rebuilt = revalidate_reviewed_match_details_snapshot_candidate_admission(
        materialization_inputs=inputs, candidate_set=candidate, candidate_set_bytes=candidate_bytes,
        admission=admission, admission_bytes=exact_bytes,
    )
    assert canonical_reviewed_match_details_snapshot_candidate_admission_bytes(rebuilt) == exact_bytes
    assert sha256_reviewed_match_details_snapshot_candidate_admission(admission) == __import__("hashlib").sha256(exact_bytes).hexdigest()
    assert json.loads(exact_bytes.decode("utf-8"))["admission_scope"] == ADMISSION_SCOPE


def test_admission_is_not_snapshot_and_cannot_enter_pr31_directly() -> None:
    admission, _ = _canonical_admission()
    assert not isinstance(admission, FixtureIntelligenceSnapshot)
    with pytest.raises(FixtureModelFeatureError):
        build_model_feature_snapshot(admission)


def test_production_ast_has_no_snapshot_model_network_filesystem_or_downstream_boundary() -> None:
    path = Path(__file__).parents[1] / "domain" / "fotmob_reviewed_match_details_snapshot_candidate_admission.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports, names, calls = [], [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import): imports.extend(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom): imports.append(node.module or "")
        elif isinstance(node, ast.Name): names.append(node.id)
        elif isinstance(node, ast.Call):
            calls.append(node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else "")
    assert not [item for item in imports if item.split(".")[0] in {"http", "requests", "httpx", "aiohttp", "socket", "pathlib", "os"}]
    forbidden = {"FixtureIntelligenceSnapshot", "build_snapshot", "build_model_feature_snapshot", "compile_fixture_catalog"}
    assert not (set(names) & forbidden)
    assert not (set(calls) & forbidden)
