from __future__ import annotations

import ast
import dataclasses
import datetime
import json
from functools import lru_cache
from pathlib import Path

import pytest

from tests.support.module_loader import load_test_module

from domain.fixture_intelligence import (
    FixtureIntelligenceSnapshot,
    IntelligenceFactStatus,
    build_snapshot,
)
from domain.fixture_model_features import FixtureModelFeatureError, build_model_feature_snapshot
from domain.fotmob_reviewed_match_details_snapshot_candidate_set import (
    CANDIDATE_SCOPE,
    DATASET_NAME,
    SCHEMA_VERSION,
    FotMobReviewedMatchDetailsSnapshotCandidateSetError,
    RecordedMatchDetailsSnapshotCandidateSetMember,
    ReviewedMatchDetailsMaterializationChainInput,
    ReviewedMatchDetailsSnapshotCandidateSet,
    build_reviewed_match_details_snapshot_candidate_set,
    canonical_reviewed_match_details_snapshot_candidate_set_bytes,
    revalidate_reviewed_match_details_snapshot_candidate_set,
    sha256_materialized_reviewed_match_details_fact,
    sha256_reviewed_match_details_snapshot_candidate_set,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


UTC = datetime.timezone.utc


@lru_cache(maxsize=1)
def _pr62_helper():
    return load_test_module("test_fotmob_reviewed_match_details_fact_status_materializer")


def _chain(inputs, classified_at=None) -> ReviewedMatchDetailsMaterializationChainInput:
    pr62 = _pr62_helper()
    artifact, artifact_bytes, evaluation, evaluation_bytes = pr62._materialize(
        inputs, classified_at
    )
    kwargs = pr62._materialize_kwargs(inputs, evaluation, evaluation_bytes)
    return ReviewedMatchDetailsMaterializationChainInput(
        evidence=kwargs["evidence"],
        evidence_receipt_bytes=kwargs["evidence_receipt_bytes"],
        manifest_bytes=kwargs["manifest_bytes"],
        raw_bytes=kwargs["raw_bytes"],
        assessment=kwargs["assessment"],
        assessment_bytes=kwargs["assessment_bytes"],
        review=kwargs["review"],
        review_bytes=kwargs["review_bytes"],
        fact_bundle=kwargs["fact_bundle"],
        fact_bundle_bytes=kwargs["fact_bundle_bytes"],
        qualification=kwargs["qualification"],
        qualification_bytes=kwargs["qualification_bytes"],
        policy=kwargs["policy"],
        policy_bytes=kwargs["policy_bytes"],
        evaluation=evaluation,
        evaluation_bytes=evaluation_bytes,
        materialization=artifact,
        materialization_bytes=artifact_bytes,
    )


def _one_approved_chain(value: int = 100, classified_at=None):
    return _chain(_pr62_helper()._home_form_inputs(value), classified_at)


def _blocked_chain():
    pr62 = _pr62_helper()
    disposition = pr62.FieldEvidenceQualificationDisposition.REJECTED
    return _chain(pr62._build_inputs({"synthetic_label": disposition}))


def _candidate(*chains):
    return build_reviewed_match_details_snapshot_candidate_set(
        materialization_inputs=tuple(chains)
    )


def _canonical_candidate(*chains):
    candidate = _candidate(*chains)
    return candidate, canonical_reviewed_match_details_snapshot_candidate_set_bytes(candidate)


def test_contract_dataset_scope_immutable_and_detached_safety() -> None:
    candidate, _ = _canonical_candidate(_one_approved_chain())

    assert SCHEMA_VERSION == 1 and type(SCHEMA_VERSION) is int
    assert DATASET_NAME == (
        "athena-fotmob-reviewed-match-details-snapshot-candidate-set-v1"
    )
    assert CANDIDATE_SCOPE == "EXPLICIT_REVALIDATED_MATERIALIZATION_SET_ONLY"
    assert candidate.member_count == 1
    assert candidate.safety == {key: False for key in candidate.safety}
    with pytest.raises(dataclasses.FrozenInstanceError):
        candidate.fixture_identifier = "FOTMOB:9"
    with pytest.raises(TypeError):
        candidate.safety["model_feature_authorized"] = True


def test_one_exact_pr62_materialization_is_accepted_and_anchored() -> None:
    chain = _one_approved_chain()
    candidate, exact_bytes = _canonical_candidate(chain)

    assert candidate.member_count == 1
    member = candidate.members[0]
    assert member.materialization_sha256 == __import__("hashlib").sha256(
        chain.materialization_bytes
    ).hexdigest()
    assert member.materialization_size == len(chain.materialization_bytes)
    assert member.fact_bundle_sha256 == chain.materialization.fact_bundle_sha256
    assert member.evaluation_sha256 == chain.materialization.evaluation_sha256
    assert len(candidate.facts) == len(chain.materialization.materialized_facts)
    assert exact_bytes.endswith(b"\n")


def test_two_same_moment_materializations_are_losslessly_combined_deterministically() -> None:
    first = _one_approved_chain(100)
    second = _one_approved_chain(200)
    forward, forward_bytes = _canonical_candidate(first, second)
    reverse, reverse_bytes = _canonical_candidate(second, first)

    assert forward.member_count == 2
    assert len(forward.facts) == 2
    assert forward_bytes == reverse_bytes
    assert sha256_reviewed_match_details_snapshot_candidate_set(forward) == (
        sha256_reviewed_match_details_snapshot_candidate_set(reverse)
    )
    assert {fact.value for fact in forward.facts} == {100, 200}
    assert all(fact.status is IntelligenceFactStatus.SUPPORTED for fact in forward.facts)


def test_equal_semantic_values_from_distinct_materializations_are_not_collapsed() -> None:
    pr62 = _pr62_helper()
    pr60 = pr62._pr61_helper()._pr60_helper()
    pr58 = pr60._pr58_helper()
    approved = (
        pr58._approved(
            "/alpha/value",
            pr62.JsonValueKind.INTEGER,
            __import__("domain.fixture_intelligence", fromlist=["IntelligenceCategory"]).IntelligenceCategory.FORM,
            "home_form",
        ),
    )
    compact = _chain(pr62._custom_inputs(b'{"alpha":{"value":100}}', approved))
    spaced = _chain(pr62._custom_inputs(b'{ "alpha": {"value": 100}}', approved))
    candidate, _ = _canonical_candidate(compact, spaced)

    assert candidate.member_count == 2
    assert len(candidate.facts) == 2
    assert [fact.value for fact in candidate.facts] == [100, 100]
    assert candidate.members[0].materialization_sha256 != candidate.members[1].materialization_sha256


def test_duplicate_exact_materialization_sha_is_rejected() -> None:
    chain = _one_approved_chain()
    with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateSetError, match="duplicate"):
        _candidate(chain, chain)


def test_mixed_classification_times_are_rejected_without_reselection() -> None:
    inputs = _pr62_helper()._home_form_inputs(100)
    first = _chain(inputs)
    later = _chain(
        inputs,
        inputs["policy"].policy_reviewed_at + datetime.timedelta(seconds=1),
    )
    assert first.materialization.classified_at != later.materialization.classified_at
    with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateSetError, match="classified_at"):
        _candidate(first, later)


@pytest.mark.parametrize("attribute, value", [("fixture_identifier", "FOTMOB:9"), ("source_match_id", "9")])
def test_local_candidate_rejects_member_fixture_or_source_match_mismatch(attribute, value) -> None:
    candidate, _ = _canonical_candidate(_one_approved_chain())
    member = candidate.members[0]
    if attribute == "fixture_identifier":
        altered = dataclasses.replace(member, fixture_identifier=value, source_match_id="9")
    else:
        altered = dataclasses.replace(member, fixture_identifier="FOTMOB:9", source_match_id=value)
    with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateSetError):
        dataclasses.replace(candidate, members=(altered,))


def test_local_candidate_rejects_member_kickoff_mismatch() -> None:
    candidate, _ = _canonical_candidate(_one_approved_chain())
    changed = dataclasses.replace(
        candidate.members[0], kickoff=candidate.kickoff + datetime.timedelta(seconds=1)
    )
    with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateSetError, match="share exact"):
        dataclasses.replace(candidate, members=(changed,))


def test_differing_supported_values_are_preserved_without_winner_or_conflict_status() -> None:
    candidate, _ = _canonical_candidate(_one_approved_chain(11), _one_approved_chain(22))

    assert [fact.value for fact in candidate.facts] != [candidate.facts[0].value]
    assert {fact.value for fact in candidate.facts} == {11, 22}
    assert all(fact.status is IntelligenceFactStatus.SUPPORTED for fact in candidate.facts)
    assert all(lineage.status is IntelligenceFactStatus.SUPPORTED for lineage in candidate.fact_lineage)
    assert all(fact.status is not IntelligenceFactStatus.CONFLICTED for fact in candidate.facts)
    assert not hasattr(candidate, "conflicted_fields")
    assert not hasattr(candidate, "winner")


def test_stale_and_blocked_statuses_remain_exact_without_reevaluation() -> None:
    pr62 = _pr62_helper()
    stale_inputs = pr62._one_approved_inputs()
    fresh_until = stale_inputs["policy"].decisions[0].fresh_until
    assert fresh_until is not None
    stale = _chain(stale_inputs, fresh_until + datetime.timedelta(microseconds=1))
    stale_candidate, _ = _canonical_candidate(stale)
    assert stale_candidate.facts[0].status is IntelligenceFactStatus.STALE

    blocked_candidate, _ = _canonical_candidate(_blocked_chain())
    statuses = {fact.field: fact.status for fact in blocked_candidate.facts}
    assert statuses["synthetic_label"] is IntelligenceFactStatus.UNVERIFIED


@pytest.mark.parametrize(
    "attribute, replacement",
    [
        ("value", 999),
        ("status", IntelligenceFactStatus.STALE),
        ("evidence_sha256", "f" * 64),
        ("source_reference", "FOTMOB_MATCH_DETAILS:1:/forged"),
        ("category", __import__("domain.fixture_intelligence", fromlist=["IntelligenceCategory"]).IntelligenceCategory.PERFORMANCE),
        ("field", "forged_field"),
    ],
)
def test_forced_nested_fact_mutation_is_rejected(attribute, replacement) -> None:
    candidate, _ = _canonical_candidate(_one_approved_chain())
    object.__setattr__(candidate.facts[0], attribute, replacement)
    with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateSetError):
        canonical_reviewed_match_details_snapshot_candidate_set_bytes(candidate)


def test_forced_member_anchor_mutation_is_rejected() -> None:
    chain = _one_approved_chain()
    candidate, candidate_bytes = _canonical_candidate(chain)
    object.__setattr__(candidate.members[0], "evaluation_sha256", "0" * 64)
    with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateSetError):
        revalidate_reviewed_match_details_snapshot_candidate_set(
            materialization_inputs=(chain,),
            candidate_set=candidate,
            candidate_set_bytes=candidate_bytes,
        )


def test_direct_conflicted_assignment_is_rejected() -> None:
    candidate, _ = _canonical_candidate(_one_approved_chain())
    object.__setattr__(candidate.facts[0], "status", IntelligenceFactStatus.CONFLICTED)
    with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateSetError):
        canonical_reviewed_match_details_snapshot_candidate_set_bytes(candidate)


def test_coordinated_upstream_and_candidate_forgery_fails_full_pr52_to_pr63_replay() -> None:
    chain = _one_approved_chain()
    candidate, candidate_bytes = _canonical_candidate(chain)
    object.__setattr__(chain.materialization.materialized_facts[0], "value", 999)
    object.__setattr__(candidate.facts[0], "value", 999)
    with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateSetError):
        revalidate_reviewed_match_details_snapshot_candidate_set(
            materialization_inputs=(chain,),
            candidate_set=candidate,
            candidate_set_bytes=candidate_bytes,
        )


@pytest.mark.parametrize("bad_bytes", [bytearray(b"x"), memoryview(b"x"), "x"])
def test_nonimmutable_candidate_bytes_are_rejected(bad_bytes) -> None:
    candidate, _ = _canonical_candidate(_one_approved_chain())
    with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateSetError):
        revalidate_reviewed_match_details_snapshot_candidate_set(
            materialization_inputs=(_one_approved_chain(),),
            candidate_set=candidate,
            candidate_set_bytes=bad_bytes,
        )


def test_wrong_or_noncanonical_candidate_bytes_are_rejected() -> None:
    chain = _one_approved_chain()
    candidate, exact_bytes = _canonical_candidate(chain)
    for bad_bytes in (b"{}\n", exact_bytes + b"\n"):
        with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateSetError):
            revalidate_reviewed_match_details_snapshot_candidate_set(
                materialization_inputs=(chain,),
                candidate_set=candidate,
                candidate_set_bytes=bad_bytes,
            )


def test_full_revalidation_rebuilds_historical_exact_bytes() -> None:
    chain = _one_approved_chain()
    candidate, exact_bytes = _canonical_candidate(chain)
    rebuilt = revalidate_reviewed_match_details_snapshot_candidate_set(
        materialization_inputs=(chain,),
        candidate_set=candidate,
        candidate_set_bytes=exact_bytes,
    )
    assert canonical_reviewed_match_details_snapshot_candidate_set_bytes(rebuilt) == exact_bytes


def test_fact_lineage_and_hashes_bind_every_flattened_exact_fact() -> None:
    candidate, _ = _canonical_candidate(_one_approved_chain(100), _one_approved_chain(200))
    assert len(candidate.facts) == len(candidate.fact_lineage)
    for fact, lineage in zip(candidate.facts, candidate.fact_lineage):
        assert lineage.materialized_fact_sha256 == sha256_materialized_reviewed_match_details_fact(fact)
        assert lineage.status is fact.status
        assert lineage.category is fact.category
        assert lineage.field == fact.field
        assert lineage.source_reference == fact.source_reference


def test_candidate_set_is_not_pr30_snapshot_and_cannot_enter_pr31_directly() -> None:
    candidate, _ = _canonical_candidate(_one_approved_chain())
    assert not isinstance(candidate, FixtureIntelligenceSnapshot)
    with pytest.raises(FixtureModelFeatureError):
        build_model_feature_snapshot(candidate)


def test_pr30_conflict_remains_a_later_snapshot_decision_not_pr63_behavior() -> None:
    candidate, _ = _canonical_candidate(_one_approved_chain(10), _one_approved_chain(20))
    later_snapshot = build_snapshot(
        candidate.fixture_identifier,
        candidate.kickoff,
        candidate.classified_at,
        list(candidate.facts),
    )
    assert ("FORM", "home_form") in later_snapshot.conflicted_fields
    assert not hasattr(candidate, "conflicted_fields")


def test_canonical_bytes_are_deterministic_json_safe_and_have_no_snapshot_claim() -> None:
    candidate, first = _canonical_candidate(_one_approved_chain())
    second = canonical_reviewed_match_details_snapshot_candidate_set_bytes(candidate)
    decoded = json.loads(first.decode("utf-8"))
    assert first == second
    assert first.endswith(b"\n")
    assert "FixtureIntelligenceSnapshot" not in first.decode("utf-8")
    assert decoded["candidate_scope"] == CANDIDATE_SCOPE
    assert sha256_reviewed_match_details_snapshot_candidate_set(candidate) == __import__("hashlib").sha256(first).hexdigest()


def test_input_requires_nonempty_exact_immutable_tuple() -> None:
    chain = _one_approved_chain()
    for bad in ((), [chain], (object(),)):
        with pytest.raises(FotMobReviewedMatchDetailsSnapshotCandidateSetError):
            build_reviewed_match_details_snapshot_candidate_set(materialization_inputs=bad)


def test_fotmob_source_capability_remains_unknown() -> None:
    capability = SOURCE_CAPABILITY_REGISTRY["fotmob_unofficial"]
    assert all(
        getattr(capability, field) is CapabilityAvailability.UNKNOWN
        for field in (
            "full_time_score",
            "half_time_score",
            "event_timestamps",
            "reliable_fixture_identity",
            "historical_coverage",
            "freshness_metadata",
        )
    )


def test_production_module_does_not_cross_snapshot_model_network_or_downstream_boundaries() -> None:
    source = Path(__file__).parents[1] / "domain" / "fotmob_reviewed_match_details_snapshot_candidate_set.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = []
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node, ast.Name):
            names.append(node.id)
    forbidden_import_roots = {"http", "requests", "httpx", "aiohttp", "socket", "pathlib", "os"}
    assert not [name for name in imports if name.split(".")[0] in forbidden_import_roots]
    assert "domain.fixture_model_features" not in imports
    assert "FixtureIntelligenceSnapshot" not in names
    assert "build_snapshot" not in names
    assert "build_model_feature_snapshot" not in names
    for forbidden in ("compile_fixture_catalog", "prediction_engine", "pricing", "bet"):
        assert forbidden not in names
