from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
import importlib.util
import json
from functools import lru_cache
from pathlib import Path

import pytest

from domain.fixture_intelligence import (
    FixtureIntelligenceFact,
    IntelligenceCategory,
    IntelligenceFactStatus,
    build_snapshot,
)
from domain.fixture_model_features import (
    ModelFeatureBlocker,
    ModelFeatureId,
    ModelFeatureStatus,
    build_model_feature_snapshot,
)
from domain.fotmob_reviewed_match_details_fact_status_materializer import (
    DATASET_NAME,
    MATERIALIZATION_SCOPE,
    SCHEMA_VERSION,
    STATUS_MAPPING,
    FotMobReviewedMatchDetailsFactStatusMaterializationError,
    RecordedMatchDetailsFactStatusLineage,
    ReviewedMatchDetailsFactStatusMaterialization,
    canonical_reviewed_match_details_fact_status_materialization_bytes,
    materialize_reviewed_match_details_fact_statuses,
    revalidate_reviewed_match_details_fact_status_materialization,
    sha256_original_reviewed_match_details_fact,
    sha256_reviewed_match_details_fact_status_materialization,
)
from domain.fotmob_reviewed_match_details_field_evidence_qualification import (
    FieldEvidenceQualificationDisposition,
)
from domain.fotmob_reviewed_match_details_status_evaluator import (
    StatusEvaluationDisposition,
    canonical_reviewed_match_details_status_evaluation_bytes,
)
from domain.fotmob_reviewed_match_details_structure import JsonValueKind
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


UTC = datetime.timezone.utc


@lru_cache(maxsize=1)
def _pr61_helper():
    helper_path = Path(__file__).with_name(
        "test_fotmob_reviewed_match_details_status_evaluator.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_athena_pr61_materializer_helper",
        helper_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PR #61 helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_inputs(dispositions=None):
    return _pr61_helper()._build_inputs(dispositions)


def _custom_inputs(raw: bytes, approved):
    pr61 = _pr61_helper()
    pr60 = pr61._pr60_helper()
    (
        policy,
        policy_bytes,
        qualification,
        qualification_bytes,
        fact_bundle,
        fact_bytes,
        chain,
    ) = pr60._build_policy(raw, approved)
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


def _one_approved_inputs(raw: bytes = b'{"alpha":{"value":100}}'):
    pr60 = _pr61_helper()._pr60_helper()
    return _custom_inputs(raw, pr60._pr58_helper()._one_approved())


def _home_form_inputs(value: int):
    pr60 = _pr61_helper()._pr60_helper()
    pr58 = pr60._pr58_helper()
    approved = (
        pr58._approved(
            "/alpha/value",
            JsonValueKind.INTEGER,
            IntelligenceCategory.FORM,
            "home_form",
        ),
    )
    return _custom_inputs(
        json.dumps({"alpha": {"value": value}}, separators=(",", ":")).encode(),
        approved,
    )


def _evaluation(inputs, classified_at=None):
    at = inputs["policy"].policy_reviewed_at if classified_at is None else classified_at
    evaluation = _pr61_helper()._evaluate(inputs, at)
    evaluation_bytes = canonical_reviewed_match_details_status_evaluation_bytes(
        evaluation
    )
    return evaluation, evaluation_bytes


def _materialize_kwargs(inputs, evaluation, evaluation_bytes):
    return {
        "evidence": inputs["evidence"],
        "evidence_receipt_bytes": inputs["receipt"],
        "manifest_bytes": inputs["manifest"],
        "raw_bytes": inputs["raw"],
        "assessment": inputs["assessment"],
        "assessment_bytes": inputs["assessment_bytes"],
        "review": inputs["review"],
        "review_bytes": inputs["review_bytes"],
        "fact_bundle": inputs["fact_bundle"],
        "fact_bundle_bytes": inputs["fact_bytes"],
        "qualification": inputs["qualification"],
        "qualification_bytes": inputs["qualification_bytes"],
        "policy": inputs["policy"],
        "policy_bytes": inputs["policy_bytes"],
        "evaluation": evaluation,
        "evaluation_bytes": evaluation_bytes,
    }


def _materialize(inputs, classified_at=None):
    evaluation, evaluation_bytes = _evaluation(inputs, classified_at)
    artifact = materialize_reviewed_match_details_fact_statuses(
        **_materialize_kwargs(inputs, evaluation, evaluation_bytes)
    )
    artifact_bytes = canonical_reviewed_match_details_fact_status_materialization_bytes(
        artifact
    )
    return artifact, artifact_bytes, evaluation, evaluation_bytes


def _revalidate(inputs, artifact, artifact_bytes, evaluation, evaluation_bytes):
    return revalidate_reviewed_match_details_fact_status_materialization(
        **_materialize_kwargs(inputs, evaluation, evaluation_bytes),
        materialization=artifact,
        materialization_bytes=artifact_bytes,
    )


def _fact_by_field(artifact, field):
    return next(item for item in artifact.materialized_facts if item.field == field)


def _lineage_by_field(artifact, field):
    return next(item for item in artifact.lineage if item.field == field)


def test_contract_dataset_schema_scope_mapping_and_immutability() -> None:
    inputs = _one_approved_inputs()
    artifact, _, _, _ = _materialize(inputs)

    assert SCHEMA_VERSION == 1 and type(SCHEMA_VERSION) is int
    assert DATASET_NAME == (
        "athena-fotmob-reviewed-match-details-fact-status-materialization-v1"
    )
    assert MATERIALIZATION_SCOPE == "EXACT_EVALUATED_OBSERVATION_ONLY"
    assert STATUS_MAPPING == {
        StatusEvaluationDisposition.FRESH_QUALIFIED: IntelligenceFactStatus.SUPPORTED,
        StatusEvaluationDisposition.STALE_QUALIFIED: IntelligenceFactStatus.STALE,
        StatusEvaluationDisposition.BLOCKED_BY_QUALIFICATION: IntelligenceFactStatus.UNVERIFIED,
    }
    with pytest.raises(TypeError):
        STATUS_MAPPING[StatusEvaluationDisposition.FRESH_QUALIFIED] = (
            IntelligenceFactStatus.UNVERIFIED
        )
    with pytest.raises(dataclasses.FrozenInstanceError):
        artifact.dataset_name = "changed"
    with pytest.raises(dataclasses.FrozenInstanceError):
        artifact.lineage[0].resulting_status = IntelligenceFactStatus.STALE


def test_fresh_qualified_maps_to_supported_exactly() -> None:
    inputs = _one_approved_inputs()
    artifact, _, _, _ = _materialize(inputs)

    assert artifact.supported_count == 1
    assert artifact.stale_count == 0
    assert artifact.unverified_count == 0
    assert artifact.materialized_facts[0].status is IntelligenceFactStatus.SUPPORTED
    assert (
        artifact.lineage[0].evaluation_disposition
        is StatusEvaluationDisposition.FRESH_QUALIFIED
    )
    assert artifact.lineage[0].resulting_status is IntelligenceFactStatus.SUPPORTED


def test_stale_qualified_maps_to_stale_exactly() -> None:
    inputs = _one_approved_inputs()
    eligible = inputs["policy"].decisions[0]
    assert eligible.fresh_until is not None
    artifact, _, _, _ = _materialize(
        inputs,
        eligible.fresh_until + datetime.timedelta(microseconds=1),
    )

    assert artifact.supported_count == 0
    assert artifact.stale_count == 1
    assert artifact.unverified_count == 0
    assert artifact.materialized_facts[0].status is IntelligenceFactStatus.STALE
    assert (
        artifact.lineage[0].evaluation_disposition
        is StatusEvaluationDisposition.STALE_QUALIFIED
    )


def test_blocked_by_qualification_remains_unverified() -> None:
    inputs = _build_inputs(
        {"synthetic_label": FieldEvidenceQualificationDisposition.REJECTED}
    )
    artifact, _, _, _ = _materialize(inputs)

    blocked = _fact_by_field(artifact, "synthetic_label")
    fresh = _fact_by_field(artifact, "synthetic_metric")
    assert blocked.status is IntelligenceFactStatus.UNVERIFIED
    assert fresh.status is IntelligenceFactStatus.SUPPORTED
    assert artifact.supported_count == 1
    assert artifact.unverified_count == 1
    assert (
        _lineage_by_field(artifact, "synthetic_label").evaluation_disposition
        is StatusEvaluationDisposition.BLOCKED_BY_QUALIFICATION
    )


@pytest.mark.parametrize(
    "attribute",
    [
        "category",
        "field",
        "value",
        "source_provider",
        "source_role",
        "source_reference",
        "observed_at",
        "evidence_file_path",
        "evidence_sha256",
        "notes",
    ],
)
def test_original_fact_payload_is_unchanged_except_status(attribute) -> None:
    inputs = _one_approved_inputs()
    artifact, _, _, _ = _materialize(inputs)
    original = inputs["fact_bundle"].facts[0]
    materialized = artifact.materialized_facts[0]

    assert getattr(materialized, attribute) == getattr(original, attribute)
    assert original.status is IntelligenceFactStatus.UNVERIFIED
    assert materialized.status is IntelligenceFactStatus.SUPPORTED
    assert (
        artifact.lineage[0].original_fact_sha256
        == sha256_original_reviewed_match_details_fact(original)
    )


def test_exact_pr57_and_pr61_ancestry_is_anchored() -> None:
    inputs = _one_approved_inputs()
    artifact, _, evaluation, evaluation_bytes = _materialize(inputs)

    assert artifact.fixture_identifier == inputs["fact_bundle"].fixture_identifier
    assert artifact.source_match_id == inputs["fact_bundle"].source_match_id
    assert artifact.kickoff == evaluation.kickoff
    assert artifact.classified_at == evaluation.classified_at
    assert artifact.fact_bundle_size == len(inputs["fact_bytes"])
    assert artifact.fact_bundle_sha256 == hashlib.sha256(inputs["fact_bytes"]).hexdigest()
    assert artifact.evaluation_size == len(evaluation_bytes)
    assert artifact.evaluation_sha256 == hashlib.sha256(evaluation_bytes).hexdigest()


def test_wrong_fact_sha256_is_rejected_by_full_chain_replay() -> None:
    inputs = _one_approved_inputs()
    evaluation, _ = _evaluation(inputs)
    object.__setattr__(evaluation.decisions[0], "fact_sha256", "0" * 64)
    forged_bytes = canonical_reviewed_match_details_status_evaluation_bytes(evaluation)

    with pytest.raises(
        FotMobReviewedMatchDetailsFactStatusMaterializationError,
        match="full-chain revalidation",
    ):
        materialize_reviewed_match_details_fact_statuses(
            **_materialize_kwargs(inputs, evaluation, forged_bytes)
        )


@pytest.mark.parametrize(
    ("attribute", "replacement"),
    [
        ("category", IntelligenceCategory.FORM),
        ("field", "lookalike_field"),
        ("source_reference", None),
    ],
)
def test_decision_metadata_mismatch_is_rejected_even_with_valid_fact_hash(
    attribute,
    replacement,
) -> None:
    inputs = _one_approved_inputs()
    evaluation, _ = _evaluation(inputs)
    if attribute == "source_reference":
        replacement = (
            f"FOTMOB_MATCH_DETAILS:{evaluation.source_match_id}:/lookalike"
        )
    object.__setattr__(evaluation.decisions[0], attribute, replacement)
    forged_bytes = canonical_reviewed_match_details_status_evaluation_bytes(evaluation)

    with pytest.raises(
        FotMobReviewedMatchDetailsFactStatusMaterializationError,
        match="full-chain revalidation",
    ):
        materialize_reviewed_match_details_fact_statuses(
            **_materialize_kwargs(inputs, evaluation, forged_bytes)
        )


def test_hash_swapping_between_lookalike_facts_is_rejected() -> None:
    inputs = _build_inputs()
    evaluation, _ = _evaluation(inputs)
    first, second = evaluation.decisions
    first_hash, second_hash = first.fact_sha256, second.fact_sha256
    object.__setattr__(first, "fact_sha256", second_hash)
    object.__setattr__(second, "fact_sha256", first_hash)
    forged_bytes = canonical_reviewed_match_details_status_evaluation_bytes(evaluation)

    with pytest.raises(
        FotMobReviewedMatchDetailsFactStatusMaterializationError,
        match="full-chain revalidation",
    ):
        materialize_reviewed_match_details_fact_statuses(
            **_materialize_kwargs(inputs, evaluation, forged_bytes)
        )


@pytest.mark.parametrize(
    ("attribute", "replacement"),
    [
        ("status", IntelligenceFactStatus.STALE),
        ("value", 999),
        ("evidence_sha256", "0" * 64),
        ("source_reference", "FOTMOB_MATCH_DETAILS:123:/forged"),
        ("category", IntelligenceCategory.FORM),
        ("field", "forged_field"),
    ],
)
def test_forced_materialized_fact_mutation_fails_local_canonicalization(
    attribute,
    replacement,
) -> None:
    artifact, _, _, _ = _materialize(_one_approved_inputs())
    object.__setattr__(artifact.materialized_facts[0], attribute, replacement)

    with pytest.raises(
        FotMobReviewedMatchDetailsFactStatusMaterializationError,
        match="nested materialized fact|original PR #57|lineage",
    ):
        canonical_reviewed_match_details_fact_status_materialization_bytes(artifact)


def test_stale_cannot_be_turned_into_supported() -> None:
    inputs = _one_approved_inputs()
    deadline = inputs["policy"].decisions[0].fresh_until
    assert deadline is not None
    artifact, _, _, _ = _materialize(
        inputs,
        deadline + datetime.timedelta(microseconds=1),
    )
    object.__setattr__(artifact.materialized_facts[0], "status", IntelligenceFactStatus.SUPPORTED)
    object.__setattr__(artifact.lineage[0], "resulting_status", IntelligenceFactStatus.SUPPORTED)

    with pytest.raises(FotMobReviewedMatchDetailsFactStatusMaterializationError):
        canonical_reviewed_match_details_fact_status_materialization_bytes(artifact)


def test_blocked_cannot_be_turned_into_supported() -> None:
    inputs = _build_inputs(
        {"synthetic_label": FieldEvidenceQualificationDisposition.REJECTED}
    )
    artifact, _, _, _ = _materialize(inputs)
    index = next(
        i for i, item in enumerate(artifact.materialized_facts) if item.field == "synthetic_label"
    )
    object.__setattr__(artifact.materialized_facts[index], "status", IntelligenceFactStatus.SUPPORTED)
    object.__setattr__(artifact.lineage[index], "resulting_status", IntelligenceFactStatus.SUPPORTED)

    with pytest.raises(FotMobReviewedMatchDetailsFactStatusMaterializationError):
        canonical_reviewed_match_details_fact_status_materialization_bytes(artifact)


def test_conflicted_status_cannot_be_assigned_directly() -> None:
    artifact, _, _, _ = _materialize(_one_approved_inputs())
    object.__setattr__(artifact.materialized_facts[0], "status", IntelligenceFactStatus.CONFLICTED)
    object.__setattr__(artifact.lineage[0], "resulting_status", IntelligenceFactStatus.CONFLICTED)

    with pytest.raises(
        FotMobReviewedMatchDetailsFactStatusMaterializationError,
        match="CONFLICTED|mapping|nested lineage",
    ):
        canonical_reviewed_match_details_fact_status_materialization_bytes(artifact)


def test_coordinated_upstream_and_local_forgery_fails_pr52_to_pr62_replay() -> None:
    inputs = _one_approved_inputs()
    artifact, _, evaluation, evaluation_bytes = _materialize(inputs)

    forged_value = 999
    object.__setattr__(inputs["fact_bundle"].facts[0], "value", forged_value)
    object.__setattr__(artifact.materialized_facts[0], "value", forged_value)
    projected = dataclasses.replace(
        artifact.materialized_facts[0],
        status=IntelligenceFactStatus.UNVERIFIED,
    )
    forged_fact_sha = sha256_original_reviewed_match_details_fact(projected)
    object.__setattr__(artifact.lineage[0], "original_fact_sha256", forged_fact_sha)
    local_bytes = canonical_reviewed_match_details_fact_status_materialization_bytes(
        artifact
    )
    assert hashlib.sha256(local_bytes).hexdigest()

    with pytest.raises(
        FotMobReviewedMatchDetailsFactStatusMaterializationError,
        match="full-chain revalidation",
    ):
        _revalidate(
            inputs,
            artifact,
            local_bytes,
            evaluation,
            evaluation_bytes,
        )


def test_exact_revalidation_accepts_historical_canonical_bytes() -> None:
    inputs = _build_inputs(
        {"synthetic_label": FieldEvidenceQualificationDisposition.REJECTED}
    )
    artifact, artifact_bytes, evaluation, evaluation_bytes = _materialize(inputs)
    rebuilt = _revalidate(
        inputs,
        artifact,
        artifact_bytes,
        evaluation,
        evaluation_bytes,
    )

    assert rebuilt.to_dict() == artifact.to_dict()
    assert (
        canonical_reviewed_match_details_fact_status_materialization_bytes(rebuilt)
        == artifact_bytes
    )


@pytest.mark.parametrize("bad_bytes", [bytearray(b"x"), memoryview(b"x"), "bytes", None])
def test_materialization_bytes_must_be_exact_immutable_bytes(bad_bytes) -> None:
    inputs = _one_approved_inputs()
    artifact, _, evaluation, evaluation_bytes = _materialize(inputs)
    with pytest.raises(
        FotMobReviewedMatchDetailsFactStatusMaterializationError,
        match="exact immutable bytes",
    ):
        _revalidate(inputs, artifact, bad_bytes, evaluation, evaluation_bytes)


def test_noncanonical_or_wrong_materialization_bytes_are_rejected() -> None:
    inputs = _one_approved_inputs()
    artifact, artifact_bytes, evaluation, evaluation_bytes = _materialize(inputs)
    for bad in (artifact_bytes + b"\n", artifact_bytes[:-1], b"{}\n"):
        with pytest.raises(
            FotMobReviewedMatchDetailsFactStatusMaterializationError,
            match="not exact canonical",
        ):
            _revalidate(inputs, artifact, bad, evaluation, evaluation_bytes)


def test_canonical_bytes_and_hash_are_deterministic() -> None:
    artifact, artifact_bytes, _, _ = _materialize(_one_approved_inputs())
    assert artifact_bytes.endswith(b"\n") and not artifact_bytes.endswith(b"\n\n")
    assert artifact_bytes == (
        json.dumps(
            artifact.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    assert (
        sha256_reviewed_match_details_fact_status_materialization(artifact)
        == hashlib.sha256(artifact_bytes).hexdigest()
    )


def test_multiple_fresh_differing_values_are_preserved_and_pr31_blocks_conflict() -> None:
    first_inputs = _home_form_inputs(100)
    second_inputs = _home_form_inputs(200)
    first, _, first_evaluation, _ = _materialize(first_inputs)
    second, _, second_evaluation, _ = _materialize(second_inputs)

    facts = [first.materialized_facts[0], second.materialized_facts[0]]
    assert [item.value for item in facts] == [100, 200]
    assert all(item.status is IntelligenceFactStatus.SUPPORTED for item in facts)
    assert first.fixture_identifier == second.fixture_identifier
    assert first.kickoff == second.kickoff

    snapshot = build_snapshot(
        first.fixture_identifier,
        first.kickoff,
        max(first_evaluation.classified_at, second_evaluation.classified_at),
        facts,
    )
    assert (IntelligenceCategory.FORM.value, "home_form") in snapshot.conflicted_fields
    feature_snapshot = build_model_feature_snapshot(snapshot)
    home_form = next(
        item for item in feature_snapshot.features if item.feature_id is ModelFeatureId.HOME_FORM
    )
    assert home_form.status is ModelFeatureStatus.BLOCKED
    assert home_form.value is None
    assert home_form.blockers == (ModelFeatureBlocker.CONFLICTED_EVIDENCE,)


def test_artifact_creates_no_snapshot_or_model_output() -> None:
    artifact, artifact_bytes, _, _ = _materialize(_one_approved_inputs())
    payload = artifact.to_dict()
    text = artifact_bytes.decode("utf-8")
    assert type(artifact) is ReviewedMatchDetailsFactStatusMaterialization
    assert "snapshot" not in payload
    assert "model_features" not in payload
    assert "probability" not in payload
    assert "price" not in payload
    assert "bet" not in payload
    assert "FixtureIntelligenceSnapshot" not in text


def test_lineage_is_exact_and_no_winner_or_conflict_status_is_emitted() -> None:
    artifact, _, _, _ = _materialize(_build_inputs())
    assert all(type(item) is RecordedMatchDetailsFactStatusLineage for item in artifact.lineage)
    assert len(artifact.lineage) == len(artifact.materialized_facts) == 2
    assert all(item.resulting_status is IntelligenceFactStatus.SUPPORTED for item in artifact.lineage)
    assert all(item.status is not IntelligenceFactStatus.CONFLICTED for item in artifact.materialized_facts)
    assert "winner" not in artifact.to_dict()


def test_safety_is_detached_immutable_and_all_false() -> None:
    artifact, _, _, _ = _materialize(_one_approved_inputs())
    expected = {
        "network_acquisition_authorized",
        "fact_status_materialization_authorized",
        "source_wide_qualification_authorized",
        "source_identity_resolution_authorized",
        "conflict_resolution_authorized",
        "intelligence_snapshot_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
    assert set(artifact.safety) == expected
    assert all(type(value) is bool and value is False for value in artifact.safety.values())
    with pytest.raises(TypeError):
        artifact.safety["model_feature_authorized"] = True
    detached = artifact.to_dict()
    detached["safety"]["model_feature_authorized"] = True
    assert artifact.safety["model_feature_authorized"] is False


def test_fotmob_unofficial_source_capability_remains_unknown() -> None:
    capability = SOURCE_CAPABILITY_REGISTRY["fotmob_unofficial"]
    fields = (
        "full_time_score",
        "half_time_score",
        "event_timestamps",
        "reliable_fixture_identity",
        "historical_coverage",
        "freshness_metadata",
    )
    assert all(
        getattr(capability, field) is CapabilityAvailability.UNKNOWN
        for field in fields
    )


def test_production_module_has_no_network_filesystem_snapshot_model_or_downstream_imports() -> None:
    path = Path(__file__).resolve().parents[1] / "domain" / (
        "fotmob_reviewed_match_details_fact_status_materializer.py"
    )
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    forbidden = {
        "http.client",
        "urllib.request",
        "requests",
        "httpx",
        "aiohttp",
        "pathlib",
        "os",
        "domain.fixture_model_features",
        "intelligence.prediction_engine",
        "domain.fixture_catalog",
    }
    assert not imports & forbidden
    fixture_import = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "domain.fixture_intelligence"
    )
    imported_fixture_names = {alias.name for alias in fixture_import.names}
    assert "FixtureIntelligenceSnapshot" not in imported_fixture_names
    assert "build_snapshot" not in imported_fixture_names
    assert "build_snapshot(" not in source
    assert "build_model_feature_snapshot" not in source
    assert "compile_fixture_catalog" not in source
