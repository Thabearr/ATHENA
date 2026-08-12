from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
import importlib.util
import inspect
import math
from pathlib import Path

import pytest

from domain.fixture_model_features import (
    ModelFeatureBlocker,
    ModelFeatureId,
    ModelFeatureStatus,
    canonical_model_feature_snapshot_bytes,
)
from domain.fotmob_reviewed_match_details_expected_goals_transform_candidate import (
    CANDIDATE_SCOPE,
    DATASET_NAME,
    SCHEMA_VERSION,
    TRANSFORM_ID,
    ExpectedGoalsCandidateStatus,
    ExpectedGoalsFeatureAudit,
    FotMobReviewedMatchDetailsExpectedGoalsTransformCandidateError,
    LegacyExpectedGoalsTransformSpecification,
    build_reviewed_match_details_expected_goals_transform_candidate,
    canonical_legacy_expected_goals_transform_specification_bytes,
    canonical_reviewed_match_details_expected_goals_transform_candidate_bytes,
    legacy_expected_goals_transform_specification,
    revalidate_reviewed_match_details_expected_goals_transform_candidate,
    sha256_legacy_expected_goals_transform_specification,
    sha256_reviewed_match_details_expected_goals_transform_candidate,
)


def _pr67_helper():
    path = Path(__file__).with_name(
        "test_fotmob_reviewed_match_details_probability_model_readiness.py"
    )
    spec = importlib.util.spec_from_file_location("_athena_pr68_pr67_helper", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PR #67 helper")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def _chain_kwargs(pr65_result=None):
    helper = _pr67_helper()
    readiness, readiness_bytes, kwargs = helper._build(pr65_result)
    return {
        **kwargs,
        "readiness": readiness,
        "readiness_bytes": readiness_bytes,
    }


def _build(pr65_result=None):
    kwargs = _chain_kwargs(pr65_result)
    candidate = build_reviewed_match_details_expected_goals_transform_candidate(
        **kwargs
    )
    candidate_bytes = (
        canonical_reviewed_match_details_expected_goals_transform_candidate_bytes(
            candidate
        )
    )
    return candidate, candidate_bytes, kwargs


def _revalidate(candidate, candidate_bytes, kwargs):
    return revalidate_reviewed_match_details_expected_goals_transform_candidate(
        **kwargs,
        candidate=candidate,
        candidate_bytes=candidate_bytes,
    )


def _audit_values(
    *,
    home_form: float = 0.65,
    away_form: float = 0.55,
    home_elo: float = 1510.0,
    away_elo: float = 1490.0,
    fatigue: float = 0.2,
    freshness: float = 1.0,
):
    values = {
        ModelFeatureId.AWAY_ELO: away_elo,
        ModelFeatureId.AWAY_FORM: away_form,
        ModelFeatureId.FATIGUE: fatigue,
        ModelFeatureId.HOME_ELO: home_elo,
        ModelFeatureId.HOME_FORM: home_form,
        ModelFeatureId.LIVE_DATA_FRESHNESS: freshness,
    }
    return tuple(
        ExpectedGoalsFeatureAudit(
            feature_id=feature_id,
            status=ModelFeatureStatus.AVAILABLE,
            value=float(values[feature_id]),
            blockers=(),
            evidence_sha256s=(f"{index:064x}",),
        )
        for index, feature_id in enumerate(
            sorted(ModelFeatureId, key=lambda item: item.value), start=1
        )
    )


def _rates(audits):
    from domain.fotmob_reviewed_match_details_expected_goals_transform_candidate import (
        _rates_from_audits,
    )

    return _rates_from_audits(audits, legacy_expected_goals_transform_specification())


def test_exact_full_chain_builds_deterministic_blocked_candidate() -> None:
    candidate, candidate_bytes, kwargs = _build()
    rebuilt = _revalidate(candidate, candidate_bytes, kwargs)

    assert SCHEMA_VERSION == 1 and type(SCHEMA_VERSION) is int
    assert DATASET_NAME == (
        "athena-fotmob-reviewed-match-details-expected-goals-transform-candidate-v1"
    )
    assert CANDIDATE_SCOPE == "EXACT_REVALIDATED_PR67_FEATURE_STATE_RESEARCH_ONLY"
    assert candidate.status is ExpectedGoalsCandidateStatus.BLOCKED_FEATURE_INPUTS
    assert candidate.home_expected_goals_candidate is None
    assert candidate.away_expected_goals_candidate is None
    assert candidate_bytes.endswith(b"\n") and not candidate_bytes.endswith(b"\n\n")
    assert canonical_reviewed_match_details_expected_goals_transform_candidate_bytes(
        rebuilt
    ) == candidate_bytes
    assert sha256_reviewed_match_details_expected_goals_transform_candidate(
        candidate
    ) == hashlib.sha256(candidate_bytes).hexdigest()


def test_missing_and_blocked_pr31_features_remain_exact_blockers_without_defaults() -> None:
    candidate, _, _ = _build()

    assert candidate.blocking_feature_ids == (
        ModelFeatureId.AWAY_ELO,
        ModelFeatureId.AWAY_FORM,
        ModelFeatureId.FATIGUE,
        ModelFeatureId.HOME_ELO,
        ModelFeatureId.LIVE_DATA_FRESHNESS,
    )
    assert all(
        item.value is None
        for item in candidate.required_feature_audits
        if item.feature_id in candidate.blocking_feature_ids
    )
    assert candidate.home_expected_goals_candidate is None
    assert candidate.away_expected_goals_candidate is None

    blocked_candidate, _, _ = _build(_pr67_helper()._pr66_helper()._stale_pr65_result())
    home_form = next(
        item
        for item in blocked_candidate.required_feature_audits
        if item.feature_id is ModelFeatureId.HOME_FORM
    )
    assert home_form.status is ModelFeatureStatus.BLOCKED
    assert ModelFeatureBlocker.STALE_EVIDENCE_PRESENT in home_form.blockers
    assert ModelFeatureId.HOME_FORM in blocked_candidate.blocking_feature_ids
    assert blocked_candidate.home_expected_goals_candidate is None


def test_all_six_available_full_chain_produces_research_only_rates() -> None:
    pr65_result = _pr67_helper()._custom_full_available_pr66_result()
    candidate, _, kwargs = _build(pr65_result)

    assert candidate.status is ExpectedGoalsCandidateStatus.AVAILABLE_RESEARCH_CANDIDATE
    assert candidate.blocking_feature_ids == ()
    assert candidate.home_expected_goals_candidate == 1.45
    assert candidate.away_expected_goals_candidate == 1.25
    assert candidate.fixture_identifier == kwargs["readiness"].fixture_identifier
    assert candidate.source_pr31_snapshot_sha256 == kwargs[
        "readiness"
    ].source_model_feature_snapshot_sha256
    assert all(
        item.status is ModelFeatureStatus.AVAILABLE
        for item in candidate.required_feature_audits
    )


@pytest.mark.parametrize(
    "freshness,expected",
    (
        (0.049999, (1.65, 1.05)),
        (0.05, (1.75, 0.95)),
        (0.050001, (1.75, 0.95)),
    ),
)
def test_exact_legacy_freshness_switch_boundary(freshness, expected) -> None:
    audits = _audit_values(
        home_form=0.7,
        away_form=0.4,
        home_elo=1580.0,
        away_elo=1420.0,
        fatigue=0.0,
        freshness=freshness,
    )

    assert _rates(audits) == expected


def test_elo_center_divisor_and_raw_clamps_match_legacy_source() -> None:
    low = _rates(
        _audit_values(
            home_form=0.9,
            away_form=0.1,
            home_elo=700.0,
            away_elo=2300.0,
            fatigue=0.0,
            freshness=0.0,
        )
    )
    centered = _rates(
        _audit_values(
            home_elo=1500.0,
            away_elo=1500.0,
            fatigue=0.0,
            freshness=0.0,
        )
    )

    assert low == (0.65, 2.05)
    assert centered == (1.45, 1.25)


def test_fatigue_baselines_floor_and_rounding_order_match_legacy_source() -> None:
    assert _rates(_audit_values(fatigue=0.3334)) == (1.383, 1.317)
    assert _rates(
        _audit_values(
            home_form=0.1,
            away_form=0.9,
            fatigue=10.0,
            freshness=1.0,
        )
    ) == (0.05, 7.05)
    assert _rates(
        _audit_values(
            home_form=0.6504,
            away_form=0.55,
            fatigue=0.0,
            freshness=1.0,
        )
    )[0] == 1.55


def test_transform_specification_is_deterministic_and_research_only() -> None:
    specification = legacy_expected_goals_transform_specification()
    first = canonical_legacy_expected_goals_transform_specification_bytes(specification)
    second = canonical_legacy_expected_goals_transform_specification_bytes(
        legacy_expected_goals_transform_specification()
    )

    assert specification.transform_id == TRANSFORM_ID
    assert specification.candidate_only is True
    assert first == second
    assert first.endswith(b"\n") and not first.endswith(b"\n\n")
    assert sha256_legacy_expected_goals_transform_specification(
        specification
    ) == hashlib.sha256(first).hexdigest()
    with pytest.raises(FotMobReviewedMatchDetailsExpectedGoalsTransformCandidateError):
        dataclasses.replace(specification, minimum_rate=0.0)


@pytest.mark.parametrize(
    "attribute,replacement",
    (
        ("source_pr67_sha256", "0" * 64),
        ("source_pr67_size", 1),
        ("source_pr31_snapshot_sha256", "0" * 64),
        ("source_pr31_snapshot_size", 1),
        ("fixture_identifier", "FOTMOB:9"),
        ("source_match_id", "9"),
        ("kickoff", datetime.datetime(2026, 1, 2, tzinfo=datetime.timezone.utc)),
        ("as_of", datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)),
        ("home_expected_goals_candidate", 9.0),
        ("away_expected_goals_candidate", 9.0),
    ),
)
def test_forced_wrapper_or_candidate_rate_mutation_fails_full_replay(
    attribute, replacement
) -> None:
    candidate, candidate_bytes, kwargs = _build(
        _pr67_helper()._custom_full_available_pr66_result()
    )
    object.__setattr__(candidate, attribute, replacement)

    with pytest.raises(FotMobReviewedMatchDetailsExpectedGoalsTransformCandidateError):
        _revalidate(candidate, candidate_bytes, kwargs)


@pytest.mark.parametrize("bad", (b"", b"{}\n", bytearray(b"x"), memoryview(b"x"), "x"))
def test_noncanonical_or_mutable_candidate_bytes_are_rejected(bad) -> None:
    candidate, _, kwargs = _build()
    with pytest.raises(FotMobReviewedMatchDetailsExpectedGoalsTransformCandidateError):
        _revalidate(candidate, bad, kwargs)


def test_feature_audit_mutation_and_blocked_numbers_fail_closed() -> None:
    candidate, _, _ = _build()
    audit = candidate.required_feature_audits[0]
    object.__setattr__(audit, "value", 0.5)
    with pytest.raises(FotMobReviewedMatchDetailsExpectedGoalsTransformCandidateError):
        canonical_reviewed_match_details_expected_goals_transform_candidate_bytes(
            candidate
        )

    clean, _, _ = _build()
    object.__setattr__(clean, "home_expected_goals_candidate", 1.45)
    with pytest.raises(FotMobReviewedMatchDetailsExpectedGoalsTransformCandidateError):
        canonical_reviewed_match_details_expected_goals_transform_candidate_bytes(
            clean
        )


@pytest.mark.parametrize("value", (True, "0.5", math.nan, math.inf, -math.inf))
def test_invalid_numeric_feature_values_cannot_enter_candidate_computation(value) -> None:
    audit = _audit_values()[0]
    with pytest.raises(FotMobReviewedMatchDetailsExpectedGoalsTransformCandidateError):
        dataclasses.replace(audit, value=value)


def test_all_safety_is_false_and_no_approved_or_ready_status_exists() -> None:
    candidate, _, _ = _build()

    assert candidate.safety == {key: False for key in candidate.safety}
    assert not any(
        forbidden in item.value
        for item in ExpectedGoalsCandidateStatus
        for forbidden in ("APPROVED", "READY", "AUTHORIZED", "PRODUCTION")
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        candidate.dataset_name = "forged"
    with pytest.raises(TypeError):
        candidate.safety["score_matrix_authorized"] = True


def test_builder_exposes_no_values_coefficients_or_execution_overrides() -> None:
    parameters = set(
        inspect.signature(
            build_reviewed_match_details_expected_goals_transform_candidate
        ).parameters
    )
    assert not parameters & {
        "feature_snapshot",
        "feature_values",
        "home_form",
        "away_form",
        "home_elo",
        "away_elo",
        "fatigue",
        "freshness",
        "home_expected_goals",
        "away_expected_goals",
        "coefficients",
        "score_matrix",
        "probability",
    }


def test_production_ast_stops_before_score_matrix_and_execution() -> None:
    path = (
        Path(__file__).parents[1]
        / "domain"
        / "fotmob_reviewed_match_details_expected_goals_transform_candidate.py"
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
            calls.append(
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )

    assert "revalidate_reviewed_match_details_probability_model_readiness" in names
    forbidden = {
        "MatchAnalyst",
        "MLEngine",
        "ProbabilityEngine",
        "build_score_matrix",
        "joblib",
        "requests",
        "httpx",
        "aiohttp",
        "socket",
        "open",
        "write_text",
        "write_bytes",
    }
    assert not forbidden.intersection(imports + names + calls)
    assert not any(
        root in item.lower()
        for root in (
            "match_analyst",
            "ml_engine",
            "score_matrix",
            "prediction_engine",
            "probability_engine",
            "pricing",
            "sportybet",
            "selection",
            "betting",
        )
        for item in imports
    )


def test_frozen_specification_matches_current_legacy_source_branch_and_constants() -> None:
    source = (
        Path(__file__).parents[1] / "intelligence" / "match_analyst.py"
    ).read_text(encoding="utf-8")
    required_fragments = (
        "if avg_live_ratio < 0.05:",
        "0.50 + ((home_elo - 1500) / 800.0)",
        "0.50 + ((away_elo - 1500) / 800.0)",
        "max(0.1, min(0.9, home_raw))",
        "max(0.1, min(0.9, away_raw))",
        "1.45 + (home_raw - away_raw) - (fatigue_diff * 0.5)",
        "1.25 + (away_raw - home_raw) + (fatigue_diff * 0.5)",
        "max(0.05, round(base_home_lambda, 3))",
        "max(0.05, round(base_away_mu, 3))",
    )

    assert all(fragment in source for fragment in required_fragments)


def test_coordinated_upstream_and_candidate_forgery_fails_full_replay() -> None:
    candidate, _, kwargs = _build(_pr67_helper()._custom_full_available_pr66_result())
    home_audit = next(
        item
        for item in candidate.required_feature_audits
        if item.feature_id is ModelFeatureId.HOME_FORM
    )
    object.__setattr__(home_audit, "value", 0.7)
    forged_rates = _rates(candidate.required_feature_audits)
    object.__setattr__(candidate, "home_expected_goals_candidate", forged_rates[0])
    object.__setattr__(candidate, "away_expected_goals_candidate", forged_rates[1])
    forged_bytes = canonical_reviewed_match_details_expected_goals_transform_candidate_bytes(
        candidate
    )

    with pytest.raises(FotMobReviewedMatchDetailsExpectedGoalsTransformCandidateError):
        _revalidate(candidate, forged_bytes, kwargs)
