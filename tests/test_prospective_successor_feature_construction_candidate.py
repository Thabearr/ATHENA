from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
from pathlib import Path

import pytest

from domain.fixture_model_features import ModelFeatureId
from domain.historical_model_feature_replay_candidate import (
    HistoricalReplaySourceInput,
    build_historical_model_feature_replay_corpus,
)
from domain.prospective_successor_feature_construction_candidate import (
    CONSTRUCTION_SCOPE,
    CONSTRUCTION_SPEC_SHA256,
    CONSTRUCTION_SPEC_SIZE,
    CONSTRUCTION_STATE,
    DATASET_NAME,
    NEXT_REQUIRED_BOUNDARY,
    PR79_MAIN_SHA,
    ConstructedFeatureStatus,
    ProspectiveMatchEvidence,
    ProspectiveSuccessorFeatureConstructionError,
    ProspectiveTargetFixture,
    build_prospective_successor_feature_construction_candidate,
    build_prospective_successor_feature_construction_specification,
    canonical_prospective_successor_feature_construction_candidate_bytes,
    canonical_prospective_successor_feature_construction_specification_bytes,
    revalidate_prospective_successor_feature_construction_candidate,
    sha256_prospective_successor_feature_construction_specification,
)

UTC = datetime.timezone.utc


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _dt(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value)


def _utc(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value).replace(tzinfo=UTC)


def _row(
    fixture_id: str,
    kickoff: str,
    home: str,
    away: str,
    home_goals: int,
    away_goals: int,
    *,
    source_namespace: str = "synthetic",
    observed_at: datetime.datetime | None = None,
    kickoff_utc: datetime.datetime | None = None,
) -> ProspectiveMatchEvidence:
    local = _dt(kickoff)
    utc_kickoff = kickoff_utc or local.replace(tzinfo=UTC)
    return ProspectiveMatchEvidence(
        source_namespace=source_namespace,
        fixture_identifier=fixture_id,
        source_local_kickoff=local,
        kickoff_utc=utc_kickoff,
        home_team_identifier=home,
        away_team_identifier=away,
        home_goals=home_goals,
        away_goals=away_goals,
        observed_at=observed_at or (utc_kickoff + datetime.timedelta(hours=3)),
        evidence_sha256=_sha(f"evidence:{fixture_id}"),
        evidence_reference=f"synthetic:{fixture_id}",
    )


def _target() -> ProspectiveTargetFixture:
    return ProspectiveTargetFixture(
        source_namespace="synthetic",
        fixture_identifier="TARGET",
        source_local_kickoff=_dt("2026-08-10T20:00:00"),
        kickoff_utc=_utc("2026-08-10T20:00:00"),
        home_team_identifier="H",
        away_team_identifier="A",
        as_of=_utc("2026-08-10T18:00:00"),
        evidence_sha256=_sha("target"),
        evidence_reference="synthetic:target",
    )


def _history() -> tuple[ProspectiveMatchEvidence, ...]:
    return (
        _row("F1", "2026-07-01T20:00:00", "X", "H", 0, 1),
        _row("F2", "2026-07-05T20:00:00", "A", "Y", 2, 0),
        _row("F3", "2026-07-10T20:00:00", "H", "Z", 1, 1),
        _row("F4", "2026-07-12T20:00:00", "Q", "A", 1, 0),
        _row("F5", "2026-07-20T20:00:00", "H", "A", 2, 1),
        _row("F6", "2026-07-25T20:00:00", "H", "W", 0, 1),
        _row("F7", "2026-07-28T20:00:00", "A", "V", 1, 1),
        _row("F8", "2026-08-01T20:00:00", "H", "T", 3, 0),
        _row("F9", "2026-08-03T20:00:00", "U", "A", 0, 2),
    )


def _candidate(history=None):
    return build_prospective_successor_feature_construction_candidate(
        history=_history() if history is None else history,
        target=_target(),
    )


def _features(candidate):
    return {item.feature_id: item for item in candidate.features}


def _result(home_goals: int, away_goals: int) -> str:
    return "H" if home_goals > away_goals else "A" if home_goals < away_goals else "D"


def _pr69_csv_bytes() -> bytes:
    rows = ["Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR"]
    for item in _history():
        rows.append(
            ",".join(
                (
                    "E0",
                    item.source_local_kickoff.strftime("%d/%m/%Y"),
                    item.source_local_kickoff.strftime("%H:%M"),
                    item.home_team_identifier,
                    item.away_team_identifier,
                    str(item.home_goals),
                    str(item.away_goals),
                    _result(item.home_goals, item.away_goals),
                    "0",
                    "0",
                    "D",
                )
            )
        )
    target = _target()
    rows.append(
        ",".join(
            (
                "E0",
                target.source_local_kickoff.strftime("%d/%m/%Y"),
                target.source_local_kickoff.strftime("%H:%M"),
                target.home_team_identifier,
                target.away_team_identifier,
                "0",
                "0",
                "D",
                "0",
                "0",
                "D",
            )
        )
    )
    return ("\n".join(rows) + "\n").encode("utf-8")


def test_frozen_spec_identity_and_all_false_safety() -> None:
    spec = build_prospective_successor_feature_construction_specification()
    exact = canonical_prospective_successor_feature_construction_specification_bytes(spec)
    assert spec.dataset_name == DATASET_NAME
    assert spec.construction_scope == CONSTRUCTION_SCOPE
    assert spec.repository_main_sha == PR79_MAIN_SHA
    assert sha256_prospective_successor_feature_construction_specification(spec) == CONSTRUCTION_SPEC_SHA256
    assert hashlib.sha256(exact).hexdigest() == CONSTRUCTION_SPEC_SHA256
    assert len(exact) == CONSTRUCTION_SPEC_SIZE == 2118
    assert spec.output_semantic_equivalence_authorized is False
    assert spec.next_required_boundary == NEXT_REQUIRED_BOUNDARY
    assert spec.safety == {key: False for key in spec.safety}
    with pytest.raises(TypeError):
        spec.safety["successor_live_inputs_qualified"] = True


def test_exact_synthetic_values_and_lineage() -> None:
    candidate = _candidate()
    feature = _features(candidate)
    assert candidate.construction_state == CONSTRUCTION_STATE
    assert candidate.supplied_history_count == candidate.eligible_history_count == 9
    assert candidate.all_five_constructed_from_supplied_history is True
    assert candidate.all_five_exact_semantic_equivalence is False
    assert {key: feature[key].value for key in feature} == {
        "home_elo": 1517,
        "away_elo": 1495,
        "home_form": 0.667,
        "away_form": 0.497,
        "fatigue": 0.0,
    }
    assert feature["home_form"].direct_fixture_identifiers == ("F1", "F3", "F5", "F6", "F8")
    assert feature["away_form"].direct_fixture_identifiers == ("F2", "F4", "F5", "F7", "F9")
    assert feature["fatigue"].direct_fixture_identifiers == ("F8", "F9")
    assert feature["home_elo"].direct_evidence_sha256s == (candidate.history_prefix_sha256,)
    assert feature["away_elo"].direct_evidence_sha256s == (candidate.history_prefix_sha256,)


def test_math_matches_pr69_on_identical_sequence() -> None:
    candidate = _candidate()
    feature = _features(candidate)
    corpus = build_historical_model_feature_replay_corpus(
        (
            HistoricalReplaySourceInput(
                season="2026-27",
                acquisition_league="E0",
                raw_bytes=_pr69_csv_bytes(),
            ),
        )
    )
    target = next(
        item
        for item in corpus.fixtures
        if item.home_team_name == "H"
        and item.away_team_name == "A"
        and item.source_local_kickoff == _dt("2026-08-10T20:00:00")
    )
    replay = {item.feature_id: item for item in target.features}
    assert feature["home_elo"].value == replay[ModelFeatureId.HOME_ELO].value
    assert feature["away_elo"].value == replay[ModelFeatureId.AWAY_ELO].value
    assert feature["home_form"].value == replay[ModelFeatureId.HOME_FORM].value
    assert feature["away_form"].value == replay[ModelFeatureId.AWAY_FORM].value
    assert feature["fatigue"].value == replay[ModelFeatureId.FATIGUE].value


def test_input_order_is_canonical() -> None:
    forward = _candidate(_history())
    reverse = _candidate(tuple(reversed(_history())))
    assert canonical_prospective_successor_feature_construction_candidate_bytes(forward) == canonical_prospective_successor_feature_construction_candidate_bytes(reverse)


def test_result_observed_after_as_of_is_excluded() -> None:
    baseline = _candidate()
    late = _row(
        "LATE",
        "2026-08-05T20:00:00",
        "H",
        "R",
        5,
        0,
        observed_at=_utc("2026-08-11T00:00:00"),
    )
    candidate = _candidate((*_history(), late))
    assert candidate.supplied_history_count == 10
    assert candidate.eligible_history_count == 9
    assert candidate.history_prefix_sha256 == baseline.history_prefix_sha256
    assert candidate.features == baseline.features


def test_empty_history_never_defaults_form_or_fatigue() -> None:
    candidate = _candidate(())
    feature = _features(candidate)
    assert feature["home_elo"].value == feature["away_elo"].value == 1500
    for feature_id in ("home_form", "away_form", "fatigue"):
        item = feature[feature_id]
        assert item.status is ConstructedFeatureStatus.MISSING_PRIOR_HISTORY
        assert item.value is None
        assert item.direct_fixture_identifiers == item.direct_evidence_sha256s == ()
    assert candidate.all_five_constructed_from_supplied_history is False
    assert candidate.all_five_exact_semantic_equivalence is False


@pytest.mark.parametrize(
    "history",
    (
        lambda: (
            _row("DUP", "2026-07-01T20:00:00", "H", "X", 1, 0),
            _row("DUP", "2026-07-02T20:00:00", "H", "Y", 1, 0),
        ),
        lambda: (_row("F1", "2026-07-01T20:00:00", "H", "X", 1, 0, source_namespace="other"),),
        lambda: (_row("TARGET", "2026-07-01T20:00:00", "H", "X", 1, 0),),
        lambda: (
            _row("A1", "2026-07-01T20:00:00", "H", "X", 1, 0),
            _row("A2", "2026-07-01T20:00:00", "H", "Y", 2, 0),
        ),
    ),
)
def test_identity_and_same_team_same_kickoff_ambiguities_fail_closed(history) -> None:
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError):
        _candidate(history())


def test_local_utc_chronology_disagreement_fails_closed() -> None:
    inconsistent = _row(
        "BADTIME",
        "2026-08-09T20:00:00",
        "H",
        "X",
        1,
        0,
        kickoff_utc=_utc("2026-08-11T20:00:00"),
        observed_at=_utc("2026-08-11T23:00:00"),
    )
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError, match="source-local and UTC chronology disagree"):
        _candidate((inconsistent,))


def test_target_and_result_chronology_are_fail_closed() -> None:
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError):
        dataclasses.replace(_target(), as_of=_utc("2026-08-10T20:00:00"))
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError):
        _row(
            "EARLY",
            "2026-07-01T20:00:00",
            "H",
            "X",
            1,
            0,
            observed_at=_utc("2026-07-01T20:00:00"),
        )


def test_candidate_revalidation_mutation_and_wrong_bytes_fail_closed() -> None:
    candidate = _candidate()
    exact = canonical_prospective_successor_feature_construction_candidate_bytes(candidate)
    assert revalidate_prospective_successor_feature_construction_candidate(
        history=_history(), target=_target(), candidate=candidate, candidate_bytes=exact
    ) == candidate
    object.__setattr__(candidate, "all_five_exact_semantic_equivalence", True)
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError):
        canonical_prospective_successor_feature_construction_candidate_bytes(candidate)
    clean = _candidate()
    with pytest.raises(ProspectiveSuccessorFeatureConstructionError):
        revalidate_prospective_successor_feature_construction_candidate(
            history=_history(), target=_target(), candidate=clean, candidate_bytes=b"{}\n"
        )
    with pytest.raises(TypeError):
        clean.safety["expected_goals_production_authorized"] = True


def _call_root(node: ast.AST) -> str | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def test_no_runtime_network_filesystem_or_downstream_engine_dependencies() -> None:
    source = Path("domain/prospective_successor_feature_construction_candidate.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
    forbidden_roots = {
        "api",
        "workers",
        "providers",
        "repositories",
        "services",
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "pathlib",
        "sqlite3",
        "database",
        "engine",
        "models",
    }
    assert not any(name.split(".", 1)[0] in forbidden_roots for name in imports)
    call_roots = {
        root
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for root in (_call_root(node.func),)
        if root is not None
    }
    assert "open" not in call_roots
