from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
from pathlib import Path

import pytest

import domain.prospective_successor_feature_construction_candidate as candidate_module
from domain.fixture_model_features import ModelFeatureId
from domain.historical_model_feature_replay_candidate import (
    HistoricalReplaySourceInput,
    build_historical_model_feature_replay_corpus,
)
from domain.prospective_successor_feature_construction_candidate import (
    CONSTRUCTION_SPEC_SHA256,
    CONSTRUCTION_SPEC_SIZE,
    ConstructedFeatureStatus,
    ConstructedSuccessorFeature,
    ProspectiveMatchEvidence,
    ProspectiveSuccessorFeatureConstructionError,
    ProspectiveTargetFixture,
    build_prospective_successor_feature_construction_candidate,
    build_prospective_successor_feature_construction_specification,
    canonical_prospective_successor_feature_construction_candidate_bytes,
    canonical_prospective_successor_feature_construction_specification_bytes,
    revalidate_prospective_successor_feature_construction_candidate,
)


UTC = datetime.timezone.utc
HASH_SHARED = hashlib.sha256(b"shared-capture").hexdigest()


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utc(day: int, hour: int = 15) -> datetime.datetime:
    return datetime.datetime(2026, 8, day, hour, tzinfo=UTC)


def _local(day: int, hour: int = 15) -> datetime.datetime:
    return datetime.datetime(2026, 8, day, hour)


def _row(
    fixture: str,
    day: int,
    home: str,
    away: str,
    home_goals: int,
    away_goals: int,
    *,
    observed_day: int | None = None,
    observed_hour: int = 18,
    local_hour: int = 15,
    utc_day: int | None = None,
    utc_hour: int = 15,
    evidence_sha256: str | None = None,
) -> ProspectiveMatchEvidence:
    utc_day = day if utc_day is None else utc_day
    observed_day = utc_day if observed_day is None else observed_day
    return ProspectiveMatchEvidence(
        source_namespace="reviewed-source",
        fixture_identifier=fixture,
        source_local_kickoff=_local(day, local_hour),
        kickoff_utc=_utc(utc_day, utc_hour),
        home_team_identifier=home,
        away_team_identifier=away,
        home_goals=home_goals,
        away_goals=away_goals,
        observed_at=_utc(observed_day, observed_hour),
        evidence_sha256=evidence_sha256 or _hash(fixture),
        evidence_reference=f"capture/{fixture}.json",
    )


def _target(
    *,
    day: int = 14,
    home: str = "A",
    away: str = "B",
    as_of_hour: int = 12,
    utc_day: int | None = None,
) -> ProspectiveTargetFixture:
    utc_day = day if utc_day is None else utc_day
    return ProspectiveTargetFixture(
        source_namespace="reviewed-source",
        fixture_identifier="target",
        source_local_kickoff=_local(day),
        kickoff_utc=_utc(utc_day),
        home_team_identifier=home,
        away_team_identifier=away,
        as_of=_utc(day, as_of_hour),
        evidence_sha256=_hash("target"),
        evidence_reference="capture/target.json",
    )


def _feature_map(candidate):
    return {item.feature_id: item for item in candidate.features}


def test_specification_has_frozen_canonical_identity_and_all_safety_false():
    spec = build_prospective_successor_feature_construction_specification()
    exact = canonical_prospective_successor_feature_construction_specification_bytes(spec)
    assert len(exact) == CONSTRUCTION_SPEC_SIZE == 2330
    assert hashlib.sha256(exact).hexdigest() == CONSTRUCTION_SPEC_SHA256
    assert CONSTRUCTION_SPEC_SHA256 == "75fe157d1b767cf374e5c2a27cc3d96434aa12f2214fc37d7c91b1e7127eb4b7"
    assert spec.output_semantic_equivalence_authorized is False
    assert set(spec.safety.values()) == {False}


def test_specification_fails_closed_if_pr78_protocol_identity_drifts(monkeypatch):
    monkeypatch.setattr(
        candidate_module,
        "canonical_successor_live_input_semantic_qualification_protocol_bytes",
        lambda value: b"drift\n",
    )
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError, match="PR78 protocol identity changed"):
        build_prospective_successor_feature_construction_specification()


def test_specification_fails_closed_if_pr79_assessment_identity_drifts(monkeypatch):
    monkeypatch.setattr(
        candidate_module,
        "canonical_successor_live_input_semantic_qualification_execution_bytes",
        lambda value: b"drift\n",
    )
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError, match="PR79 assessment identity changed"):
        build_prospective_successor_feature_construction_specification()


def test_empty_history_uses_frozen_elo_initial_state_but_does_not_default_form_or_fatigue():
    candidate = build_prospective_successor_feature_construction_candidate(
        history=(), target=_target()
    )
    features = _feature_map(candidate)
    assert features["home_elo"].value == 1500
    assert features["away_elo"].value == 1500
    assert features["home_elo"].status is ConstructedFeatureStatus.CONSTRUCTED_FROM_FROZEN_INITIAL_STATE_ASSUMPTION
    assert features["away_elo"].status is ConstructedFeatureStatus.CONSTRUCTED_FROM_FROZEN_INITIAL_STATE_ASSUMPTION
    assert features["home_form"].status is ConstructedFeatureStatus.MISSING_PRIOR_HISTORY
    assert features["away_form"].status is ConstructedFeatureStatus.MISSING_PRIOR_HISTORY
    assert features["fatigue"].status is ConstructedFeatureStatus.MISSING_PRIOR_HISTORY
    assert candidate.all_five_values_available is False
    assert candidate.all_five_exact_semantic_equivalence is False
    assert set(candidate.safety.values()) == {False}


def test_form_is_exact_recent_five_pr78_formula():
    history = (
        _row("a1", 1, "A", "X1", 2, 0),
        _row("a2", 2, "X2", "A", 1, 1),
        _row("a3", 3, "A", "X3", 0, 1),
        _row("a4", 4, "X4", "A", 0, 2),
        _row("a5", 5, "A", "X5", 1, 1),
        _row("a6", 6, "A", "X6", 0, 3),
        _row("b1", 7, "B", "Y", 1, 0),
    )
    features = _feature_map(
        build_prospective_successor_feature_construction_candidate(
            history=history, target=_target()
        )
    )
    assert features["home_form"].value == round(0.10 + ((5 / 15) * 0.85), 3)
    assert features["home_form"].derivation_fixture_identifiers == (
        "a2", "a3", "a4", "a5", "a6"
    )


@pytest.mark.parametrize(
    ("home_day", "away_day", "expected"),
    [
        (10, 7, 0.30),
        (9, 8, 0.10),
        (7, 9, 0.0),
    ],
)
def test_fatigue_uses_exact_home_relative_rest_day_thresholds(home_day, away_day, expected):
    history = (
        _row("home-last", home_day, "A", "X", 1, 0),
        _row("away-last", away_day, "B", "Y", 0, 0),
    )
    features = _feature_map(
        build_prospective_successor_feature_construction_candidate(
            history=history, target=_target()
        )
    )
    assert features["fatigue"].value == expected
    assert features["fatigue"].status is ConstructedFeatureStatus.CONSTRUCTED_FROM_SUPPLIED_HISTORY


def test_first_elo_update_matches_frozen_plus50_and_unboosted_away_equations():
    history = (
        _row("a-win", 1, "A", "C", 1, 0),
        _row("b-draw", 2, "B", "D", 0, 0),
    )
    features = _feature_map(
        build_prospective_successor_feature_construction_candidate(
            history=history, target=_target()
        )
    )
    assert features["home_elo"].value == 1513
    assert features["away_elo"].value == 1497


def test_frozen_elo_k_boundaries_and_expected_score_orientation():
    assert candidate_module._k_factor(0) == 32
    assert candidate_module._k_factor(19) == 32
    assert candidate_module._k_factor(20) == 24
    assert candidate_module._k_factor(49) == 24
    assert candidate_module._k_factor(50) == 16
    assert candidate_module._expected_score(1500, 1500, home_boost=False) == 0.5
    assert candidate_module._expected_score(1500, 1500, home_boost=True) > 0.5


def test_duplicate_capture_hashes_are_valid_parallel_lineage_not_false_duplicates():
    history = (
        _row("f1", 1, "A", "C", 1, 0, evidence_sha256=HASH_SHARED),
        _row("f2", 2, "B", "D", 1, 0, evidence_sha256=HASH_SHARED),
    )
    candidate = build_prospective_successor_feature_construction_candidate(
        history=history, target=_target()
    )
    features = _feature_map(candidate)
    assert features["home_elo"].derivation_evidence_sha256s == (HASH_SHARED, HASH_SHARED)
    assert features["away_elo"].derivation_evidence_sha256s == (HASH_SHARED, HASH_SHARED)


def test_prior_result_not_observed_by_target_as_of_fails_closed_instead_of_disappearing():
    history = (
        _row(
            "late-result",
            13,
            "A",
            "C",
            1,
            0,
            observed_day=14,
            observed_hour=13,
        ),
    )
    with pytest.raises(
        ProspectiveSuccessorFeatureConstructionError,
        match="was not observed by target as_of",
    ):
        build_prospective_successor_feature_construction_candidate(
            history=history, target=_target(as_of_hour=12)
        )


def test_future_history_is_ignored_but_remains_counted_as_supplied():
    history = (
        _row("prior-a", 1, "A", "C", 1, 0),
        _row("prior-b", 2, "B", "D", 1, 0),
        _row("future", 15, "X", "Y", 2, 2, observed_day=15, observed_hour=18),
    )
    candidate = build_prospective_successor_feature_construction_candidate(
        history=history, target=_target()
    )
    assert candidate.supplied_history_count == 3
    assert candidate.eligible_history_count == 2


def test_input_order_does_not_change_canonical_candidate():
    rows = (
        _row("f1", 1, "A", "C", 1, 0),
        _row("f2", 2, "B", "D", 0, 0),
        _row("f3", 3, "A", "D", 0, 1),
    )
    target = _target()
    first = build_prospective_successor_feature_construction_candidate(
        history=rows, target=target
    )
    second = build_prospective_successor_feature_construction_candidate(
        history=tuple(reversed(rows)), target=target
    )
    assert (
        canonical_prospective_successor_feature_construction_candidate_bytes(first)
        == canonical_prospective_successor_feature_construction_candidate_bytes(second)
    )


def test_duplicate_fixture_identifier_fails_closed():
    history = (
        _row("same", 1, "A", "C", 1, 0),
        _row("same", 2, "B", "D", 0, 1),
    )
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError, match="duplicate source fixture"):
        build_prospective_successor_feature_construction_candidate(
            history=history, target=_target()
        )


def test_source_namespace_mismatch_fails_closed():
    row = dataclasses.replace(_row("f1", 1, "A", "C", 1, 0), source_namespace="other")
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError, match="source namespace mismatch"):
        build_prospective_successor_feature_construction_candidate(
            history=(row,), target=_target()
        )


def test_target_fixture_cannot_appear_in_history():
    row = dataclasses.replace(_row("f1", 1, "A", "C", 1, 0), fixture_identifier="target")
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError, match="target fixture cannot appear"):
        build_prospective_successor_feature_construction_candidate(
            history=(row,), target=_target()
        )


def test_local_and_utc_relative_order_disagreement_fails_closed():
    row = _row("f1", 13, "A", "C", 1, 0, utc_day=15)
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError, match="chronology disagree relative"):
        build_prospective_successor_feature_construction_candidate(
            history=(row,), target=_target()
        )


def test_local_and_utc_history_order_disagreement_fails_closed():
    first = _row("first", 1, "A", "C", 1, 0, utc_day=2)
    second = _row("second", 2, "B", "D", 1, 0, utc_day=1)
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError, match="eligible-history ordering disagree"):
        build_prospective_successor_feature_construction_candidate(
            history=(first, second), target=_target()
        )


def test_same_team_same_local_kickoff_fails_closed():
    first = _row("f1", 1, "A", "C", 1, 0)
    second = _row("f2", 1, "A", "D", 0, 1)
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError, match="multiple fixtures at one kickoff"):
        build_prospective_successor_feature_construction_candidate(
            history=(first, second), target=_target()
        )


def test_target_team_other_fixture_at_target_kickoff_fails_closed():
    row = _row("other", 14, "A", "C", 1, 0, observed_day=14, observed_hour=18)
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError, match="target team has another"):
        build_prospective_successor_feature_construction_candidate(
            history=(row,), target=_target()
        )


def test_bool_goal_and_non_utc_timestamp_are_rejected():
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError, match="goals"):
        dataclasses.replace(_row("f1", 1, "A", "C", 1, 0), home_goals=True)
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError, match="datetime.timezone.utc"):
        dataclasses.replace(
            _row("f1", 1, "A", "C", 1, 0),
            kickoff_utc=datetime.datetime(2026, 8, 1, 15),
        )


def test_constructed_feature_rejects_nonfinite_values_and_lineage_mismatch():
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError, match="finite"):
        ConstructedSuccessorFeature(
            feature_id="home_elo",
            status=ConstructedFeatureStatus.CONSTRUCTED_FROM_SUPPLIED_HISTORY,
            value=float("nan"),
            derivation_fixture_identifiers=("f1",),
            derivation_evidence_sha256s=(_hash("f1"),),
            construction_semantics="test",
        )
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError, match="cardinality"):
        ConstructedSuccessorFeature(
            feature_id="home_elo",
            status=ConstructedFeatureStatus.CONSTRUCTED_FROM_SUPPLIED_HISTORY,
            value=1500,
            derivation_fixture_identifiers=("f1",),
            derivation_evidence_sha256s=(),
            construction_semantics="test",
        )


def test_revalidator_rejects_mutated_history_target_candidate_and_bytes():
    history = (
        _row("f1", 1, "A", "C", 1, 0),
        _row("f2", 2, "B", "D", 1, 0),
    )
    target = _target()
    candidate = build_prospective_successor_feature_construction_candidate(
        history=history, target=target
    )
    exact = canonical_prospective_successor_feature_construction_candidate_bytes(candidate)

    assert (
        revalidate_prospective_successor_feature_construction_candidate(
            history=history,
            target=target,
            candidate=candidate,
            candidate_bytes=exact,
        )
        == candidate
    )

    changed_history = (
        dataclasses.replace(history[0], home_goals=0, away_goals=1),
        history[1],
    )
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError, match="differs"):
        revalidate_prospective_successor_feature_construction_candidate(
            history=changed_history,
            target=target,
            candidate=candidate,
            candidate_bytes=exact,
        )
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError, match="differs"):
        revalidate_prospective_successor_feature_construction_candidate(
            history=history,
            target=dataclasses.replace(target, as_of=_utc(14, 11)),
            candidate=candidate,
            candidate_bytes=exact,
        )
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError, match="differs"):
        revalidate_prospective_successor_feature_construction_candidate(
            history=history,
            target=target,
            candidate=candidate,
            candidate_bytes=exact + b" ",
        )


def test_candidate_cannot_promote_semantic_equivalence_or_safety():
    history = (
        _row("f1", 1, "A", "C", 1, 0),
        _row("f2", 2, "B", "D", 1, 0),
    )
    candidate = build_prospective_successor_feature_construction_candidate(
        history=history, target=_target()
    )
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError, match="cannot claim"):
        dataclasses.replace(candidate, all_five_exact_semantic_equivalence=True)

    safety = dict(candidate.safety)
    safety["successor_candidate_approved"] = True
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError, match="exact False"):
        dataclasses.replace(candidate, safety=safety)


def test_exact_math_matches_pr69_historical_replay_on_same_synthetic_history():
    raw = (
        "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR\n"
        "E0,01/08/2025,15:00,Alpha,Charlie,2,0,H,1,0,H\n"
        "E0,03/08/2025,15:00,Delta,Beta,1,1,D,0,0,D\n"
        "E0,05/08/2025,15:00,Alpha,Delta,0,1,A,0,0,D\n"
        "E0,08/08/2025,15:00,Beta,Charlie,3,0,H,1,0,H\n"
        "E0,14/08/2025,15:00,Alpha,Beta,1,0,H,0,0,D\n"
    ).encode("utf-8")
    corpus = build_historical_model_feature_replay_corpus(
        (HistoricalReplaySourceInput("2025-26", "E0", raw),)
    )
    historical_target = next(
        fixture
        for fixture in corpus.fixtures
        if fixture.home_team_name == "Alpha"
        and fixture.away_team_name == "Beta"
        and fixture.source_local_date == datetime.date(2025, 8, 14)
    )
    historical_values = {
        item.feature_id.value: item.value for item in historical_target.features
    }

    history = (
        ProspectiveMatchEvidence(
            "reviewed-source", "f1",
            datetime.datetime(2025, 8, 1, 15), datetime.datetime(2025, 8, 1, 15, tzinfo=UTC),
            "Alpha", "Charlie", 2, 0, datetime.datetime(2025, 8, 1, 18, tzinfo=UTC),
            _hash("f1"), "capture/f1",
        ),
        ProspectiveMatchEvidence(
            "reviewed-source", "f2",
            datetime.datetime(2025, 8, 3, 15), datetime.datetime(2025, 8, 3, 15, tzinfo=UTC),
            "Delta", "Beta", 1, 1, datetime.datetime(2025, 8, 3, 18, tzinfo=UTC),
            _hash("f2"), "capture/f2",
        ),
        ProspectiveMatchEvidence(
            "reviewed-source", "f3",
            datetime.datetime(2025, 8, 5, 15), datetime.datetime(2025, 8, 5, 15, tzinfo=UTC),
            "Alpha", "Delta", 0, 1, datetime.datetime(2025, 8, 5, 18, tzinfo=UTC),
            _hash("f3"), "capture/f3",
        ),
        ProspectiveMatchEvidence(
            "reviewed-source", "f4",
            datetime.datetime(2025, 8, 8, 15), datetime.datetime(2025, 8, 8, 15, tzinfo=UTC),
            "Beta", "Charlie", 3, 0, datetime.datetime(2025, 8, 8, 18, tzinfo=UTC),
            _hash("f4"), "capture/f4",
        ),
    )
    target = ProspectiveTargetFixture(
        "reviewed-source", "target",
        datetime.datetime(2025, 8, 14, 15), datetime.datetime(2025, 8, 14, 15, tzinfo=UTC),
        "Alpha", "Beta", datetime.datetime(2025, 8, 14, 12, tzinfo=UTC),
        _hash("target"), "capture/target",
    )
    prospective = _feature_map(
        build_prospective_successor_feature_construction_candidate(
            history=history, target=target
        )
    )
    for feature_id in (
        ModelFeatureId.HOME_ELO.value,
        ModelFeatureId.AWAY_ELO.value,
        ModelFeatureId.HOME_FORM.value,
        ModelFeatureId.AWAY_FORM.value,
        ModelFeatureId.FATIGUE.value,
    ):
        assert prospective[feature_id].value == historical_values[feature_id]


def test_module_does_not_import_runtime_acquisition_or_downstream_betting_layers():
    source = Path(candidate_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    assert imported_roots.isdisjoint(
        {
            "requests",
            "httpx",
            "aiohttp",
            "selenium",
            "playwright",
            "workers",
            "providers",
            "api",
            "services",
            "engine",
            "models",
        }
    )
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    assert all(
        token not in module_name
        for module_name in imported_modules
        for token in (
            "score_matrix",
            "probability",
            "pricing",
            "selection",
            "betting",
            "sportybet",
        )
    )
