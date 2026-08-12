from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
import importlib.util
import inspect
import json
from functools import lru_cache
from pathlib import Path

import pytest

from domain.fixture_intelligence import (
    DATASET_NAME as FIXTURE_INTELLIGENCE_DATASET_NAME,
    SCHEMA_VERSION as FIXTURE_INTELLIGENCE_SCHEMA_VERSION,
    IntelligenceCategory,
    build_snapshot,
    canonical_snapshot_bytes,
)
from domain.fixture_model_features import (
    FixtureModelFeatureSnapshot,
    ModelFeatureBlocker,
    ModelFeatureId,
    ModelFeatureStatus,
    build_model_feature_snapshot,
    canonical_model_feature_snapshot_bytes,
)
from domain.fotmob_reviewed_match_details_fixture_intelligence_snapshot import (
    canonical_reviewed_match_details_fixture_intelligence_snapshot_bytes,
)
from domain.fotmob_reviewed_match_details_field_evidence_qualification import (
    FieldEvidenceQualificationDisposition,
)
from domain.fotmob_reviewed_match_details_model_feature_handoff import (
    DATASET_NAME,
    HANDOFF_SCOPE,
    SCHEMA_VERSION,
    FotMobReviewedMatchDetailsModelFeatureHandoffError,
    ReviewedMatchDetailsModelFeatureHandoff,
    build_reviewed_match_details_model_feature_handoff,
    canonical_reviewed_match_details_model_feature_handoff_bytes,
    revalidate_reviewed_match_details_model_feature_handoff,
    sha256_reviewed_match_details_model_feature_handoff,
)
from domain.fotmob_reviewed_match_details_structure import JsonValueKind
from domain.fotmob_reviewed_match_details_snapshot_candidate_set import (
    sha256_materialized_reviewed_match_details_fact,
)


UTC = datetime.timezone.utc


@lru_cache(maxsize=1)
def _pr65_helper():
    path = Path(__file__).with_name(
        "test_fotmob_reviewed_match_details_fixture_intelligence_snapshot.py"
    )
    spec = importlib.util.spec_from_file_location("_athena_pr66_pr65_helper", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PR #65 helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pr65_result(bundle=None):
    return _pr65_helper()._build(bundle)


def _handoff(pr65_result=None):
    if pr65_result is None:
        pr65_result = _pr65_result()
    artifact, artifact_bytes, bundle = pr65_result
    inputs, candidate, candidate_bytes, admission, admission_bytes = bundle
    handoff = build_reviewed_match_details_model_feature_handoff(
        materialization_inputs=inputs,
        candidate_set=candidate,
        candidate_set_bytes=candidate_bytes,
        admission=admission,
        admission_bytes=admission_bytes,
        artifact=artifact,
        artifact_bytes=artifact_bytes,
    )
    handoff_bytes = canonical_reviewed_match_details_model_feature_handoff_bytes(
        handoff
    )
    return handoff, handoff_bytes, pr65_result


def _revalidate(handoff, handoff_bytes, pr65_result):
    artifact, artifact_bytes, bundle = pr65_result
    inputs, candidate, candidate_bytes, admission, admission_bytes = bundle
    return revalidate_reviewed_match_details_model_feature_handoff(
        materialization_inputs=inputs,
        candidate_set=candidate,
        candidate_set_bytes=candidate_bytes,
        admission=admission,
        admission_bytes=admission_bytes,
        artifact=artifact,
        artifact_bytes=artifact_bytes,
        handoff=handoff,
        handoff_bytes=handoff_bytes,
    )


def _feature(handoff, feature_id):
    return next(
        item
        for item in handoff.model_feature_snapshot.features
        if item.feature_id is feature_id
    )


def _conflicted_pr65_result():
    pr65 = _pr65_helper()
    pr63 = pr65._pr64_helper()._pr63_helper()
    bundle = pr65._chain_bundle(
        pr63._one_approved_chain(10),
        pr63._one_approved_chain(20),
    )
    return _pr65_result(bundle)


def _stale_pr65_result():
    pr65 = _pr65_helper()
    pr63 = pr65._pr64_helper()._pr63_helper()
    pr62 = pr63._pr62_helper()
    inputs = pr62._home_form_inputs(100)
    fresh_until = inputs["policy"].decisions[0].fresh_until
    assert fresh_until is not None
    chain = pr63._chain(inputs, fresh_until + datetime.timedelta(microseconds=1))
    return _pr65_result(pr65._chain_bundle(chain))


def _rejected_home_form_inputs(value: int):
    pr63 = _pr65_helper()._pr64_helper()._pr63_helper()
    pr62 = pr63._pr62_helper()
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


def _unverified_pr65_result():
    pr65 = _pr65_helper()
    pr63 = pr65._pr64_helper()._pr63_helper()
    inputs = _rejected_home_form_inputs(100)
    chain = pr63._chain(inputs, inputs["policy"].policy_reviewed_at)
    return _pr65_result(pr65._chain_bundle(chain))


def test_exact_full_chain_produces_real_pr31_snapshot() -> None:
    handoff, _, pr65_result = _handoff()
    pr65 = pr65_result[0]

    assert type(handoff) is ReviewedMatchDetailsModelFeatureHandoff
    assert type(handoff.model_feature_snapshot) is FixtureModelFeatureSnapshot
    assert handoff.fixture_identifier == pr65.fixture_identifier
    assert handoff.source_match_id == pr65.source_match_id
    assert handoff.kickoff == pr65.kickoff
    assert handoff.as_of == pr65.classified_at == pr65.snapshot.as_of


def test_fresh_supported_home_form_is_exact_available_value() -> None:
    handoff, _, _ = _handoff()
    feature = _feature(handoff, ModelFeatureId.HOME_FORM)

    assert feature.status is ModelFeatureStatus.AVAILABLE
    assert feature.value == 100.0
    assert type(feature.value) is float
    assert feature.blockers == ()
    assert len(feature.evidence_sha256s) == 1


def test_absent_mapped_fields_remain_exact_missing() -> None:
    handoff, _, _ = _handoff()
    missing = tuple(
        item
        for item in handoff.model_feature_snapshot.features
        if item.feature_id is not ModelFeatureId.HOME_FORM
    )

    assert len(missing) == 5
    assert all(item.status is ModelFeatureStatus.MISSING for item in missing)
    assert all(item.value is None and not item.blockers for item in missing)
    assert all(not item.evidence_sha256s for item in missing)


def test_differing_supported_values_are_blocked_without_winner() -> None:
    handoff, _, _ = _handoff(_conflicted_pr65_result())
    feature = _feature(handoff, ModelFeatureId.HOME_FORM)

    assert feature.status is ModelFeatureStatus.BLOCKED
    assert feature.value is None
    assert feature.blockers == (ModelFeatureBlocker.CONFLICTED_EVIDENCE,)
    assert len(feature.evidence_sha256s) == 2
    assert "winner" not in handoff.to_dict()


def test_stale_only_preserves_exact_pr31_blocked_semantics() -> None:
    handoff, _, _ = _handoff(_stale_pr65_result())
    feature = _feature(handoff, ModelFeatureId.HOME_FORM)

    assert feature.status is ModelFeatureStatus.BLOCKED
    assert feature.value is None
    assert feature.blockers == (
        ModelFeatureBlocker.NO_SUPPORTED_EVIDENCE,
        ModelFeatureBlocker.STALE_EVIDENCE_PRESENT,
    )


def test_unverified_only_preserves_exact_pr31_blocked_semantics() -> None:
    handoff, _, _ = _handoff(_unverified_pr65_result())
    feature = _feature(handoff, ModelFeatureId.HOME_FORM)

    assert feature.status is ModelFeatureStatus.BLOCKED
    assert feature.value is None
    assert feature.blockers == (
        ModelFeatureBlocker.NO_SUPPORTED_EVIDENCE,
        ModelFeatureBlocker.UNVERIFIED_EVIDENCE_PRESENT,
    )


def test_incomplete_availability_is_accepted_without_model_ready_decision() -> None:
    handoff, _, _ = _handoff()
    payload = handoff.to_dict()

    assert any(
        item.status is ModelFeatureStatus.AVAILABLE
        for item in handoff.model_feature_snapshot.features
    )
    assert any(
        item.status is ModelFeatureStatus.MISSING
        for item in handoff.model_feature_snapshot.features
    )
    assert "model_ready" not in payload and "ready_for_model" not in payload


def test_exact_pr65_pr30_and_pr31_anchors() -> None:
    handoff, _, pr65_result = _handoff()
    pr65, pr65_bytes, _ = pr65_result
    intelligence_bytes = canonical_snapshot_bytes(pr65.snapshot)
    feature_bytes = canonical_model_feature_snapshot_bytes(
        handoff.model_feature_snapshot
    )

    assert handoff.source_pr65_artifact_sha256 == hashlib.sha256(pr65_bytes).hexdigest()
    assert handoff.source_pr65_artifact_size == len(pr65_bytes)
    assert handoff.source_fixture_intelligence_snapshot_sha256 == pr65.snapshot_sha256
    assert handoff.source_fixture_intelligence_snapshot_sha256 == hashlib.sha256(
        intelligence_bytes
    ).hexdigest()
    assert handoff.source_fixture_intelligence_snapshot_size == len(intelligence_bytes)
    assert handoff.model_feature_snapshot_sha256 == hashlib.sha256(feature_bytes).hexdigest()
    assert handoff.model_feature_snapshot_size == len(feature_bytes)


def test_pr31_source_identity_exactly_matches_rebuilt_pr65_snapshot() -> None:
    handoff, _, pr65_result = _handoff()
    pr65 = pr65_result[0]
    nested = handoff.model_feature_snapshot

    assert nested.fixture_identifier == pr65.fixture_identifier
    assert nested.kickoff == pr65.kickoff
    assert nested.as_of == pr65.classified_at == pr65.snapshot.as_of
    assert nested.source_snapshot_sha256 == pr65.snapshot_sha256
    assert nested.source_snapshot_dataset_name == pr65.snapshot.dataset_name
    assert nested.source_snapshot_dataset_name == FIXTURE_INTELLIGENCE_DATASET_NAME
    assert nested.source_snapshot_schema_version == pr65.snapshot.schema_version
    assert nested.source_snapshot_schema_version == FIXTURE_INTELLIGENCE_SCHEMA_VERSION


def test_contract_immutability_scope_and_detached_safety() -> None:
    handoff, _, _ = _handoff()

    assert SCHEMA_VERSION == 1 and type(SCHEMA_VERSION) is int
    assert DATASET_NAME == "athena-fotmob-reviewed-match-details-model-feature-handoff-v1"
    assert HANDOFF_SCOPE == "EXACT_REVALIDATED_PR65_SNAPSHOT_ONLY"
    assert handoff.safety == {key: False for key in handoff.safety}
    assert "model_feature_authorized" not in handoff.safety
    with pytest.raises(dataclasses.FrozenInstanceError):
        handoff.dataset_name = "forged"
    with pytest.raises(TypeError):
        handoff.safety["probability_inference_authorized"] = True
    assert handoff.model_feature_snapshot.safety == {
        key: False for key in handoff.model_feature_snapshot.safety
    }
    with pytest.raises(TypeError):
        handoff.model_feature_snapshot.safety["probability_inference_authorized"] = True


@pytest.mark.parametrize("bad", [b"{}\n", b"", bytearray(b"x"), memoryview(b"x"), "x"])
def test_wrong_or_mutable_pr65_artifact_bytes_are_rejected(bad) -> None:
    artifact, _, bundle = _pr65_result()
    inputs, candidate, candidate_bytes, admission, admission_bytes = bundle
    with pytest.raises(FotMobReviewedMatchDetailsModelFeatureHandoffError):
        build_reviewed_match_details_model_feature_handoff(
            materialization_inputs=inputs,
            candidate_set=candidate,
            candidate_set_bytes=candidate_bytes,
            admission=admission,
            admission_bytes=admission_bytes,
            artifact=artifact,
            artifact_bytes=bad,
        )


@pytest.mark.parametrize(
    "attribute,replacement",
    [
        ("source_pr65_artifact_sha256", "0" * 64),
        ("source_pr65_artifact_size", 1),
        ("source_fixture_intelligence_snapshot_sha256", "0" * 64),
        ("source_fixture_intelligence_snapshot_size", 1),
        ("model_feature_snapshot_sha256", "0" * 64),
        ("model_feature_snapshot_size", 1),
        ("fixture_identifier", "FOTMOB:9"),
        ("source_match_id", "9"),
        ("kickoff", datetime.datetime(2026, 1, 2, tzinfo=UTC)),
        ("as_of", datetime.datetime(2026, 1, 1, tzinfo=UTC)),
    ],
)
def test_forced_wrapper_anchor_or_identity_mutation_fails_full_replay(
    attribute,
    replacement,
) -> None:
    handoff, handoff_bytes, pr65_result = _handoff()
    object.__setattr__(handoff, attribute, replacement)
    with pytest.raises(FotMobReviewedMatchDetailsModelFeatureHandoffError):
        _revalidate(handoff, handoff_bytes, pr65_result)


@pytest.mark.parametrize(
    "target,attribute,replacement",
    [
        ("snapshot", "fixture_identifier", "FOTMOB:9"),
        ("snapshot", "as_of", datetime.datetime(2026, 1, 1, tzinfo=UTC)),
        ("snapshot", "source_snapshot_sha256", "0" * 64),
        ("feature", "status", ModelFeatureStatus.BLOCKED),
        ("feature", "value", 999.0),
        ("feature", "blockers", (ModelFeatureBlocker.CONFLICTED_EVIDENCE,)),
        ("feature", "evidence_sha256s", ("f" * 64,)),
        ("feature", "feature_id", ModelFeatureId.AWAY_FORM),
        ("feature", "source_category", IntelligenceCategory.PERFORMANCE),
        ("feature", "source_field", "away_form"),
    ],
)
def test_forced_nested_pr31_or_resolution_mutation_is_rejected(
    target,
    attribute,
    replacement,
) -> None:
    handoff, _, _ = _handoff()
    subject = (
        handoff.model_feature_snapshot
        if target == "snapshot"
        else _feature(handoff, ModelFeatureId.HOME_FORM)
    )
    object.__setattr__(subject, attribute, replacement)
    with pytest.raises(FotMobReviewedMatchDetailsModelFeatureHandoffError):
        canonical_reviewed_match_details_model_feature_handoff_bytes(handoff)


def test_coordinated_pr65_pr30_pr31_and_local_hash_forgery_fails_replay() -> None:
    handoff, handoff_bytes, pr65_result = _handoff()
    pr65, _, bundle = pr65_result
    forged_fact = dataclasses.replace(pr65.snapshot.facts[0], value=999)
    forged_snapshot = build_snapshot(
        pr65.fixture_identifier,
        pr65.kickoff,
        pr65.classified_at,
        (forged_fact,),
    )
    forged_snapshot_bytes = canonical_snapshot_bytes(forged_snapshot)
    forged_pr65 = dataclasses.replace(
        pr65,
        materialized_fact_sha256s=(
            sha256_materialized_reviewed_match_details_fact(forged_fact),
        ),
        snapshot=forged_snapshot,
        snapshot_sha256=hashlib.sha256(forged_snapshot_bytes).hexdigest(),
        snapshot_size=len(forged_snapshot_bytes),
    )
    forged_pr65_bytes = (
        canonical_reviewed_match_details_fixture_intelligence_snapshot_bytes(
            forged_pr65
        )
    )
    forged_features = build_model_feature_snapshot(forged_snapshot)
    forged_feature_bytes = canonical_model_feature_snapshot_bytes(forged_features)
    forged_handoff = dataclasses.replace(
        handoff,
        source_pr65_artifact_sha256=hashlib.sha256(forged_pr65_bytes).hexdigest(),
        source_pr65_artifact_size=len(forged_pr65_bytes),
        source_fixture_intelligence_snapshot_sha256=hashlib.sha256(
            forged_snapshot_bytes
        ).hexdigest(),
        source_fixture_intelligence_snapshot_size=len(forged_snapshot_bytes),
        model_feature_snapshot=forged_features,
        model_feature_snapshot_sha256=hashlib.sha256(forged_feature_bytes).hexdigest(),
        model_feature_snapshot_size=len(forged_feature_bytes),
    )
    forged_handoff_bytes = canonical_reviewed_match_details_model_feature_handoff_bytes(
        forged_handoff
    )
    with pytest.raises(FotMobReviewedMatchDetailsModelFeatureHandoffError):
        _revalidate(
            forged_handoff,
            forged_handoff_bytes,
            (forged_pr65, forged_pr65_bytes, bundle),
        )


@pytest.mark.parametrize("bad", [b"{}\n", b"", bytearray(b"x"), memoryview(b"x"), "x"])
def test_wrong_noncanonical_or_mutable_handoff_bytes_are_rejected(bad) -> None:
    handoff, _, pr65_result = _handoff()
    with pytest.raises(FotMobReviewedMatchDetailsModelFeatureHandoffError):
        _revalidate(handoff, bad, pr65_result)


def test_canonical_handoff_and_pr31_identity_are_deterministic() -> None:
    handoff, handoff_bytes, pr65_result = _handoff()
    rebuilt = _revalidate(handoff, handoff_bytes, pr65_result)

    assert handoff_bytes.endswith(b"\n") and not handoff_bytes.endswith(b"\n\n")
    assert canonical_reviewed_match_details_model_feature_handoff_bytes(rebuilt) == handoff_bytes
    assert sha256_reviewed_match_details_model_feature_handoff(handoff) == hashlib.sha256(
        handoff_bytes
    ).hexdigest()
    assert canonical_model_feature_snapshot_bytes(
        handoff.model_feature_snapshot
    ) == canonical_model_feature_snapshot_bytes(rebuilt.model_feature_snapshot)


def test_builder_has_no_feature_override_or_readiness_parameters() -> None:
    parameters = set(
        inspect.signature(build_reviewed_match_details_model_feature_handoff).parameters
    )
    assert not parameters & {
        "intelligence_snapshot",
        "model_feature_snapshot",
        "features",
        "feature_values",
        "selected_features",
        "blockers",
        "source_snapshot_sha256",
        "as_of",
        "model_ready",
        "ready_for_model",
    }


def test_production_ast_uses_only_pr65_replay_and_existing_pr31_boundary() -> None:
    path = (
        Path(__file__).parents[1]
        / "domain"
        / "fotmob_reviewed_match_details_model_feature_handoff.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []
    names: list[str] = []
    calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
            names.extend(item.name for item in node.names)
        elif isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)

    for required in (
        "revalidate_reviewed_match_details_fixture_intelligence_snapshot",
        "build_model_feature_snapshot",
        "canonical_model_feature_snapshot_bytes",
    ):
        assert required in names and required in calls
    forbidden_roots = {
        "http",
        "requests",
        "httpx",
        "aiohttp",
        "socket",
        "pathlib",
        "os",
    }
    assert not [item for item in imports if item.split(".")[0] in forbidden_roots]
    for forbidden in (
        "prediction_engine",
        "probability",
        "poisson",
        "calibration",
        "pricing",
        "sportybet",
        "selection",
        "betting",
    ):
        assert forbidden not in imports
        assert forbidden not in calls
