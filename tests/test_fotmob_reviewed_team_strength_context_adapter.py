from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib.util
import inspect
from pathlib import Path

import pytest

from domain.fixture_intelligence import IntelligenceCategory
from domain.fotmob_reviewed_match_details_model_feature_handoff import (
    canonical_reviewed_match_details_model_feature_handoff_bytes,
)
from domain.fotmob_reviewed_match_details_structure import JsonValueKind
from domain.fotmob_reviewed_match_details_array_records import (
    ArrayRecordSetScope,
    ArrayReviewQualification,
    ReviewedMatchDetailsArrayRecordsError,
    canonical_reviewed_match_details_array_records_bytes,
)
from domain.fotmob_reviewed_team_strength_context_adapter import (
    ReviewedFotMobTeamStrengthContext,
    ReviewedTeamStrengthContextAdapterError,
    build_reviewed_fotmob_team_strength_context,
    canonical_reviewed_fotmob_team_strength_context_bytes,
    revalidate_reviewed_fotmob_team_strength_context,
)
from domain.fotmob_team_strength_fixture_intelligence import (
    FeatureBlocker,
    FeatureStatus,
    PositionGroup,
    TeamSide,
    TeamStrengthContextError,
    build_team_strength_context_snapshot,
    canonical_team_strength_context_candidate_bytes,
)


def _helper():
    path = Path(__file__).with_name("test_fotmob_reviewed_match_details_array_records.py")
    spec = importlib.util.spec_from_file_location("_athena_array_adapter_helper", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load array helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pr66_helper():
    path = Path(__file__).with_name("test_fotmob_reviewed_match_details_model_feature_handoff.py")
    spec = importlib.util.spec_from_file_location("_athena_array_adapter_pr66_helper", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PR66 helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _reviewed_scalar_lineage(raw):
    pr66 = _pr66_helper()
    pr65 = pr66._pr65_helper()
    pr63 = pr65._pr64_helper()._pr63_helper()
    pr62 = pr63._pr62_helper()
    pr58 = pr62._pr61_helper()._pr60_helper()._pr58_helper()
    approved = (
        pr58._approved(
            "/alpha/value",
            JsonValueKind.INTEGER,
            IntelligenceCategory.FORM,
            "home_form",
        ),
    )
    inputs = pr62._custom_inputs(raw, approved)
    bundle = pr65._chain_bundle(pr63._chain(inputs))
    pr65_artifact, pr65_bytes, _ = pr65._build(bundle)
    handoff, handoff_bytes, _ = pr66._handoff((pr65_artifact, pr65_bytes, bundle))
    materialization_inputs, candidate_set, candidate_set_bytes, admission, admission_bytes = bundle
    return {
        "materialization_inputs": materialization_inputs,
        "candidate_set": candidate_set,
        "candidate_set_bytes": candidate_set_bytes,
        "admission": admission,
        "admission_bytes": admission_bytes,
        "pr65_artifact": pr65_artifact,
        "pr65_artifact_bytes": pr65_bytes,
        "pr66_handoff": handoff,
        "pr66_handoff_bytes": handoff_bytes,
    }


def build_context(**case_kwargs):
    raw = case_kwargs.pop("raw", None) or _helper()._raw()
    reviewed = _reviewed_scalar_lineage(raw)
    artifact, chain, raw = _helper().build_case(
        raw=raw,
        reviewed_at=reviewed["pr65_artifact"].classified_at,
        classified_at=reviewed["pr65_artifact"].classified_at,
        **case_kwargs,
    )
    artifact_bytes = canonical_reviewed_match_details_array_records_bytes(artifact)
    context = build_reviewed_fotmob_team_strength_context(
        evidence=chain[0], evidence_receipt_bytes=chain[1], manifest_bytes=chain[2],
        raw_bytes=raw, assessment=chain[3], assessment_bytes=chain[4],
        array_artifact=artifact, array_artifact_bytes=artifact_bytes,
        **reviewed,
    )
    return context, artifact, {"array": chain, "reviewed": reviewed}, raw, artifact_bytes


def _features(context):
    return {item.feature_id.value: item for item in context.candidate.features}


def test_full_array_replay_authorizes_wrapper_while_nested_pr190_safety_stays_false():
    context, artifact, lineage, _, _ = build_context()
    safety = dict(context.safety)
    assert safety["team_strength_feature_authorized"] is True
    assert all(not value for key, value in safety.items() if key != "team_strength_feature_authorized")
    assert all(value is False for _, value in context.candidate.safety)
    assert context.source_raw_sha256 == artifact.raw_sha256
    assert context.candidate.fixture_identifier == artifact.fixture_identifier
    assert context.home_team_id == "FOTMOB_TEAM:INTEGER:10"
    assert context.away_team_id == "FOTMOB_TEAM:INTEGER:20"
    assert context.source_pr65_artifact_sha256 == hashlib.sha256(
        lineage["reviewed"]["pr65_artifact_bytes"]
    ).hexdigest()
    assert context.source_pr66_handoff_sha256 == hashlib.sha256(
        lineage["reviewed"]["pr66_handoff_bytes"]
    ).hexdigest()
    assert canonical_reviewed_match_details_model_feature_handoff_bytes(
        lineage["reviewed"]["pr66_handoff"]
    ) == lineage["reviewed"]["pr66_handoff_bytes"]


def test_reviewed_current_lineup_availability_and_depth_can_be_available_without_history_defaults():
    context, _, _, _, _ = build_context()
    result = _features(context)
    assert result["home_unavailable_player_count"].status is FeatureStatus.AVAILABLE
    assert result["home_unavailable_player_count"].value == 0.0
    assert result["away_unavailable_player_count"].value == 1.0
    assert result["home_available_bench_player_count"].value == 1.0
    assert result["away_available_bench_player_count"].value == 1.0
    assert result["home_base_elo"].status is FeatureStatus.MISSING
    assert result["home_base_form"].status is FeatureStatus.AVAILABLE
    assert result["home_base_form"].value == 100.0
    assert result["home_xi_recent_rating_mean"].status is FeatureStatus.MISSING
    assert result["home_rest_days"].status is FeatureStatus.MISSING
    assert all(component.status is FeatureStatus.MISSING for component in context.candidate.player_components)


def test_reviewed_position_mapping_is_mechanical_and_unknown_stays_unknown():
    context, _, _, _, _ = build_context()
    positions = {item.player_id: item.position_group for item in context.candidate.player_components}
    assert positions["FOTMOB_PLAYER:INTEGER:101"] is PositionGroup.GK
    helper = _helper()
    unknown, _, _, _, _ = build_context(positions=())
    assert {item.position_group for item in unknown.candidate.player_components} == {PositionGroup.UNKNOWN}
    assert helper is not None


def test_stale_or_rejected_array_evidence_never_becomes_current_available_feature():
    helper = _helper()
    raw = helper._raw()
    chain = helper._pr53(raw)
    classified = chain[0].observed_at + helper.dt.timedelta(seconds=2)
    stale, _, _, _, _ = build_context(
        decisions=helper._decisions(chain[0], fresh_until=classified - helper.dt.timedelta(seconds=1))
    )
    assert _features(stale)["home_unavailable_player_count"].status is FeatureStatus.BLOCKED
    assert _features(stale)["home_available_bench_player_count"].status is FeatureStatus.BLOCKED
    rejected, _, _, _, _ = build_context(
        decisions=helper._decisions(chain[0], qualification=ArrayReviewQualification.REJECTED),
        positions=(),
    )
    assert _features(rejected)["home_unavailable_player_count"].status is FeatureStatus.MISSING
    assert _features(rejected)["home_available_bench_player_count"].status is FeatureStatus.BLOCKED


def test_incomplete_unavailable_array_does_not_turn_absence_into_zero():
    helper = _helper()
    raw = helper._raw()
    chain = helper._pr53(raw)
    context, _, _, _, _ = build_context(decisions=helper._decisions(chain[0], complete=False))
    home = _features(context)["home_unavailable_player_count"]
    assert home.status is FeatureStatus.MISSING
    assert home.value is None
    assert home.blockers == (FeatureBlocker.MISSING_AVAILABILITY_EVIDENCE,)


@pytest.mark.parametrize(
    "incomplete_scope",
    (ArrayRecordSetScope.STARTING_XI, ArrayRecordSetScope.BENCH),
)
def test_incomplete_starter_or_bench_sets_cannot_make_lineup_features_available(incomplete_scope):
    helper = _helper()
    raw = helper._raw()
    chain = helper._pr53(raw)
    decisions = tuple(
        dataclasses.replace(decision, completeness_attested=False)
        if decision.scope is incomplete_scope
        else decision
        for decision in helper._decisions(chain[0])
    )
    context, _, _, _, _ = build_context(decisions=decisions)
    result = _features(context)
    assert context.candidate.home_lineup_state.value == "UNVERIFIED_LINEUP_STATE"
    assert context.candidate.away_lineup_state.value == "UNVERIFIED_LINEUP_STATE"
    assert result["home_available_bench_player_count"].status is FeatureStatus.BLOCKED
    assert result["away_available_bench_player_count"].status is FeatureStatus.BLOCKED
    assert result["home_xi_recent_rating_mean"].status is FeatureStatus.BLOCKED
    assert result["away_xi_recent_rating_mean"].status is FeatureStatus.BLOCKED


def test_naked_candidate_and_caller_historical_rows_cannot_cross_authoritative_adapter():
    context, _, _, _, _ = build_context()
    with pytest.raises(TeamStrengthContextError):
        build_team_strength_context_snapshot(candidate=context.candidate)
    parameters = inspect.signature(build_reviewed_fotmob_team_strength_context).parameters
    assert "historical_appearances" not in parameters
    assert "historical_fixtures" not in parameters
    assert "base_components" not in parameters
    assert "candidate" not in parameters
    with pytest.raises(ReviewedTeamStrengthContextAdapterError, match="exact source replay"):
        ReviewedFotMobTeamStrengthContext()
    with pytest.raises(ReviewedTeamStrengthContextAdapterError, match="exact source replay"):
        dataclasses.replace(context)


def test_array_observation_must_be_inside_exact_admitted_pr65_pr66_lineage():
    _, artifact, lineage, raw, artifact_bytes = build_context()
    different = dict(_helper().RAW_OBJECT)
    different["alpha"] = {"value": 101}
    wrong_raw = _helper()._raw(different)
    wrong_reviewed = _reviewed_scalar_lineage(wrong_raw)
    with pytest.raises(ReviewedTeamStrengthContextAdapterError, match="absent from admitted PR65"):
        build_reviewed_fotmob_team_strength_context(
            evidence=lineage["array"][0],
            evidence_receipt_bytes=lineage["array"][1],
            manifest_bytes=lineage["array"][2],
            raw_bytes=raw,
            assessment=lineage["array"][3],
            assessment_bytes=lineage["array"][4],
            array_artifact=artifact,
            array_artifact_bytes=artifact_bytes,
            **wrong_reviewed,
        )


def test_full_revalidator_rejects_coordinated_nested_candidate_and_byte_forgery():
    context, artifact, lineage, raw, artifact_bytes = build_context()
    features = list(context.candidate.features)
    index = next(i for i, item in enumerate(features) if item.feature_id.value == "home_base_elo")
    features[index] = dataclasses.replace(features[index], blockers=(FeatureBlocker.INSUFFICIENT_PRIOR_HISTORY,))
    forged_candidate = dataclasses.replace(context.candidate, features=tuple(features))
    forged_candidate_bytes = canonical_team_strength_context_candidate_bytes(forged_candidate)
    object.__setattr__(context, "candidate", forged_candidate)
    object.__setattr__(context, "candidate_sha256", hashlib.sha256(forged_candidate_bytes).hexdigest())
    object.__setattr__(context, "candidate_size", len(forged_candidate_bytes))
    forged_bytes = canonical_reviewed_fotmob_team_strength_context_bytes(context)
    with pytest.raises(ReviewedTeamStrengthContextAdapterError, match="differs from full replay"):
        revalidate_reviewed_fotmob_team_strength_context(
            evidence=lineage["array"][0], evidence_receipt_bytes=lineage["array"][1],
            manifest_bytes=lineage["array"][2], raw_bytes=raw,
            assessment=lineage["array"][3], assessment_bytes=lineage["array"][4],
            array_artifact=artifact, array_artifact_bytes=artifact_bytes,
            context=context, context_bytes=forged_bytes,
            **lineage["reviewed"],
        )


def test_canonical_context_is_deterministic_and_full_revalidation_succeeds():
    context, artifact, lineage, raw, artifact_bytes = build_context()
    exact = canonical_reviewed_fotmob_team_strength_context_bytes(context)
    assert exact.endswith(b"\n")
    rebuilt = revalidate_reviewed_fotmob_team_strength_context(
        evidence=lineage["array"][0], evidence_receipt_bytes=lineage["array"][1],
        manifest_bytes=lineage["array"][2], raw_bytes=raw,
        assessment=lineage["array"][3], assessment_bytes=lineage["array"][4],
        array_artifact=artifact, array_artifact_bytes=artifact_bytes,
        context=context, context_bytes=exact,
        **lineage["reviewed"],
    )
    assert canonical_reviewed_fotmob_team_strength_context_bytes(rebuilt) == exact


def test_adapter_accepts_no_bookmaker_probability_or_adjustment_inputs_and_imports_no_legacy_bypass():
    parameters = inspect.signature(build_reviewed_fotmob_team_strength_context).parameters
    forbidden_parameters = {"odds", "bookmaker_odds", "expected_goals", "probability", "coefficient", "price"}
    assert not (forbidden_parameters & set(parameters))
    import domain.fotmob_reviewed_team_strength_context_adapter as production

    tree = ast.parse(inspect.getsource(production))
    imported = {
        alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names
    }
    forbidden = ("requests", "urllib", "httpx", "bypass", "advanced_scraper", "score_matrix", "probability", "pricing", "sportybet", "selection", "betting")
    assert not any(any(token in name.lower() for token in forbidden) for name in imported)
