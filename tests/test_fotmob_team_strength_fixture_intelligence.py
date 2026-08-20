from __future__ import annotations

import dataclasses
import datetime as dt
import ast
import inspect

import pytest

from domain.fotmob_team_strength_fixture_intelligence import (
    BaseStrengthComponent,
    BaseStrengthComponentId,
    EvidenceAnchor,
    FeatureBlocker,
    FeatureStatus,
    HistoricalPlayerAppearance,
    HistoricalTeamFixture,
    LineupState,
    PlayerRecordKind,
    PositionGroup,
    ReviewedPlayerRecord,
    SupportedContextRecord,
    TeamSide,
    TeamStrengthContextError,
    TeamStrengthFeatureId,
    build_team_strength_context_snapshot,
    canonical_team_strength_context_snapshot_bytes,
    sha256_team_strength_context_snapshot,
)

UTC = dt.timezone.utc
KICKOFF = dt.datetime(2026, 8, 22, 15, tzinfo=UTC)
AS_OF = KICKOFF - dt.timedelta(hours=2)


def anchor(seed: str, observed_at: dt.datetime | None = None) -> EvidenceAnchor:
    return EvidenceAnchor(f"fotmob://{seed}", observed_at or AS_OF - dt.timedelta(days=1), (seed[0] if seed else "a") * 64)


def player(team: str, pid: str, kind: PlayerRecordKind, *, state=LineupState.EXPECTED, group=PositionGroup.FWD, seed="a"):
    return ReviewedPlayerRecord(team, pid, kind, state, None if group is PositionGroup.UNKNOWN else group.value, group, "injury" if kind is PlayerRecordKind.UNAVAILABLE else None, anchor(seed))


def appearance(fid: str, days: int, team: str, pid: str, *, started=True, minutes=90, rating=7.0, seed="b"):
    venue = TeamSide.AWAY if team == "A" else TeamSide.HOME
    return HistoricalPlayerAppearance(fid, KICKOFF - dt.timedelta(days=days), True, team, pid, started, minutes, rating, venue, anchor(seed))


def fixture(fid: str, days: int, *, seed="c"):
    return HistoricalTeamFixture(fid, KICKOFF - dt.timedelta(days=days), True, ("H", "X"), anchor(seed))


def build(**overrides):
    values = dict(
        fixture_identifier="target",
        home_team_id="H",
        away_team_id="A",
        kickoff=KICKOFF,
        as_of=AS_OF,
        home_lineup_state=LineupState.EXPECTED,
        away_lineup_state=LineupState.EXPECTED,
        player_records=(player("H", "h1", PlayerRecordKind.STARTER), player("A", "a1", PlayerRecordKind.STARTER, seed="d")),
        historical_appearances=(appearance("p1", 4, "H", "h1"), appearance("p2", 5, "A", "a1", seed="e")),
        historical_fixtures=(HistoricalTeamFixture("p1", KICKOFF - dt.timedelta(days=4), True, ("H", "X"), anchor("c")), HistoricalTeamFixture("p2", KICKOFF - dt.timedelta(days=5), True, ("Y", "A"), anchor("f"))),
        home_availability_evidence=anchor("1"),
        away_availability_evidence=anchor("2"),
        home_schedule_history_evidence=anchor("3"),
        away_schedule_history_evidence=anchor("4"),
        home_player_history_evidence=anchor("5"),
        away_player_history_evidence=anchor("6"),
    )
    values.update(overrides)
    return build_team_strength_context_snapshot(**values)


def features(snapshot):
    return {item.feature_id.value: item for item in snapshot.features}


def test_strictly_prior_schedule_included_same_kickoff_and_future_excluded():
    rows = (
        fixture("prior", 3),
        HistoricalTeamFixture("same", KICKOFF, True, ("H", "Y"), anchor("d")),
        HistoricalTeamFixture("future", KICKOFF + dt.timedelta(days=1), True, ("H", "Z"), anchor("e")),
    )
    result = features(build(historical_fixtures=rows, historical_appearances=()))
    assert result["home_matches_previous_7_days"].value == 1.0
    assert result["home_rest_days"].value == 3.0


def test_same_and_future_appearances_cannot_change_target_features():
    prior = appearance("prior", 3, "H", "h1", rating=6.0)
    same = dataclasses.replace(prior, fixture_identifier="same", kickoff=KICKOFF, rating=10.0)
    future = dataclasses.replace(prior, fixture_identifier="future", kickoff=KICKOFF + dt.timedelta(days=1), rating=10.0)
    prior_fixture = HistoricalTeamFixture("prior", prior.kickoff, True, ("H", "X"), anchor("c"))
    result = features(build(historical_appearances=(prior, same, future), historical_fixtures=(prior_fixture,)))
    assert result["home_xi_recent_rating_mean"].value == 6.0
    assert result["home_xi_rating_observation_count"].value == 1.0


def test_post_kickoff_or_post_as_of_source_observation_rejected():
    bad = player("H", "h1", PlayerRecordKind.STARTER)
    bad = dataclasses.replace(bad, evidence=anchor("a", KICKOFF + dt.timedelta(seconds=1)))
    with pytest.raises(TeamStrengthContextError, match="post-as_of or post-kickoff"):
        build(player_records=(bad, player("A", "a1", PlayerRecordKind.STARTER, seed="d")))


def test_player_ids_anchor_identity_and_duplicate_or_conflicting_records_fail():
    regular = player("H", "42", PlayerRecordKind.STARTER)
    conflict = player("H", "42", PlayerRecordKind.UNAVAILABLE, seed="b")
    with pytest.raises(TeamStrengthContextError, match="duplicate/conflicting"):
        build(player_records=(regular, conflict, player("A", "a1", PlayerRecordKind.STARTER, seed="d")))


def test_expected_and_confirmed_lineup_states_remain_distinct():
    expected = build()
    confirmed_rows = tuple(dataclasses.replace(x, lineup_state=LineupState.CONFIRMED) for x in expected_players())
    confirmed = build(home_lineup_state=LineupState.CONFIRMED, away_lineup_state=LineupState.CONFIRMED, player_records=confirmed_rows)
    assert expected.home_lineup_state is LineupState.EXPECTED
    assert confirmed.home_lineup_state is LineupState.CONFIRMED
    assert canonical_team_strength_context_snapshot_bytes(expected) != canonical_team_strength_context_snapshot_bytes(confirmed)


def expected_players():
    return (player("H", "h1", PlayerRecordKind.STARTER), player("A", "a1", PlayerRecordKind.STARTER, seed="d"))


def test_missing_lineup_and_missing_availability_do_not_become_neutral_defaults():
    result = features(build(home_lineup_state=LineupState.NOT_AVAILABLE, player_records=(player("A", "a1", PlayerRecordKind.STARTER, seed="d"),), home_availability_evidence=None))
    assert result["home_xi_recent_rating_mean"].status is FeatureStatus.MISSING
    assert FeatureBlocker.MISSING_LINEUP in result["home_xi_recent_rating_mean"].blockers
    assert result["home_unavailable_player_count"].value is None
    assert result["home_unavailable_player_count"].blockers == (FeatureBlocker.MISSING_AVAILABILITY_EVIDENCE,)


def test_missing_rating_is_missing_not_zero_and_reliability_is_separate():
    rows = (appearance("p1", 4, "H", "h1", rating=None), appearance("p2", 5, "A", "a1", seed="e"))
    result = features(build(historical_appearances=rows))
    assert result["home_xi_recent_rating_mean"].status is FeatureStatus.MISSING
    assert result["home_xi_recent_rating_mean"].value is None
    assert result["home_xi_rating_observation_count"].value == 0.0


def test_regular_starter_and_fringe_unavailability_have_different_transparent_importance():
    current = (
        player("H", "regular", PlayerRecordKind.UNAVAILABLE),
        player("H", "fringe", PlayerRecordKind.UNAVAILABLE, seed="b"),
        player("A", "a1", PlayerRecordKind.STARTER, seed="d"),
    )
    history = tuple(appearance(f"r{i}", i + 2, "H", "regular", minutes=90, seed="c") for i in range(5)) + (appearance("r1", 3, "H", "fringe", started=False, minutes=5, seed="e"), appearance("away", 3, "A", "a1", seed="f"))
    historical_fixtures = tuple(HistoricalTeamFixture(f"r{i}", KICKOFF - dt.timedelta(days=i + 2), True, ("H", "X"), anchor("c")) for i in range(5)) + (HistoricalTeamFixture("away", KICKOFF - dt.timedelta(days=3), True, ("Y", "A"), anchor("f")),)
    result = features(build(player_records=current, historical_appearances=history, historical_fixtures=historical_fixtures))
    assert result["home_unavailable_prior_minutes_share_5"].value > 0.9
    assert result["home_unavailable_rating_observation_count"].value == 6.0
    snapshot = build(player_records=current, historical_appearances=history, historical_fixtures=historical_fixtures)
    components = {item.player_id: item for item in snapshot.player_components if item.team_id == "H"}
    assert components["regular"].starts_previous_5 == 5
    assert components["regular"].start_share_previous_5 == 1.0
    assert components["regular"].minutes_previous_5 == 450.0
    assert components["fringe"].starts_previous_5 == 0
    assert components["fringe"].start_share_previous_5 == 0.0
    assert components["fringe"].minutes_previous_5 == 5.0


def test_rating_reliability_position_groups_continuity_and_depth_are_explicit():
    current = (
        player("H", "gk", PlayerRecordKind.STARTER, group=PositionGroup.GK),
        player("H", "new", PlayerRecordKind.STARTER, group=PositionGroup.UNKNOWN, seed="b"),
        player("H", "bench", PlayerRecordKind.BENCH, group=PositionGroup.MID, seed="c"),
        player("A", "a1", PlayerRecordKind.STARTER, seed="d"),
    )
    history = (
        appearance("p1", 4, "H", "gk", rating=7.5),
        appearance("p1", 4, "H", "old", rating=6.5, seed="e"),
        appearance("p2", 8, "H", "bench", started=False, minutes=20, rating=6.8, seed="f"),
        appearance("p3", 5, "A", "a1", seed="a"),
    )
    historical_fixtures = (
        HistoricalTeamFixture("p1", KICKOFF - dt.timedelta(days=4), True, ("H", "X"), anchor("c")),
        HistoricalTeamFixture("p2", KICKOFF - dt.timedelta(days=8), True, ("H", "X"), anchor("d")),
        HistoricalTeamFixture("p3", KICKOFF - dt.timedelta(days=5), True, ("Y", "A"), anchor("e")),
    )
    result = features(build(player_records=current, historical_appearances=history, historical_fixtures=historical_fixtures))
    assert result["home_xi_gk_rating_mean"].value == 7.5
    assert result["home_xi_def_rating_mean"].status is FeatureStatus.MISSING
    assert result["home_replacement_count"].value == 1.0
    assert result["home_replacement_quality_evidence_gap_count"].value == 1.0
    assert result["home_available_bench_player_count"].value == 1.0
    assert result["home_bench_rating_coverage"].value == 1.0


def test_unknown_coarse_position_does_not_erase_exact_source_position():
    unknown = ReviewedPlayerRecord("H", "wide", PlayerRecordKind.STARTER, LineupState.EXPECTED, "WingBackVariant", PositionGroup.UNKNOWN, None, anchor("a"))
    result = build(player_records=(unknown, player("A", "a1", PlayerRecordKind.STARTER, seed="d")))
    assert result.home_lineup_state is LineupState.EXPECTED
    assert features(result)["home_xi_def_rating_mean"].status is FeatureStatus.MISSING


def test_base_strength_and_supported_context_are_separate_typed_namespaces():
    base = BaseStrengthComponent("H", BaseStrengthComponentId.ELO, 1540, anchor("a"))
    weather = SupportedContextRecord("weather_description", "rain", anchor("b"))
    result = build(base_components=(base,), supported_context=(weather,))
    assert features(result)["home_base_elo"].value == 1540.0
    assert result.supported_context[0].status == "SUPPORTED_CONTEXT_NOT_YET_MODEL_FEATURE"


def test_canonical_identity_and_evidence_mutation_fail_closed():
    result = build()
    payload = canonical_team_strength_context_snapshot_bytes(result)
    assert payload.endswith(b"\n")
    assert sha256_team_strength_context_snapshot(result) == sha256_team_strength_context_snapshot(result)
    with pytest.raises(TeamStrengthContextError):
        dataclasses.replace(result, source_evidence_sha256s=("b" * 64, "a" * 64))
    mutated_time = build()
    object.__setattr__(mutated_time.source_evidence[0], "observed_at", KICKOFF + dt.timedelta(seconds=1))
    with pytest.raises(TeamStrengthContextError, match="post-as_of or post-kickoff"):
        canonical_team_strength_context_snapshot_bytes(mutated_time)
    mutated_hash = build()
    object.__setattr__(mutated_hash.source_evidence[0], "evidence_sha256", "not-a-sha")
    with pytest.raises(TeamStrengthContextError, match="SHA-256"):
        canonical_team_strength_context_snapshot_bytes(mutated_hash)


def test_feature_namespace_is_exact_and_unverified_lineup_is_blocked():
    assert len(TeamStrengthFeatureId) == 66
    rows = tuple(dataclasses.replace(x, lineup_state=LineupState.UNVERIFIED_LINEUP_STATE) for x in expected_players())
    result = features(build(home_lineup_state=LineupState.UNVERIFIED_LINEUP_STATE, away_lineup_state=LineupState.UNVERIFIED_LINEUP_STATE, player_records=rows))
    assert result["home_xi_recent_rating_mean"].status is FeatureStatus.BLOCKED
    assert result["home_xi_recent_rating_mean"].blockers == (FeatureBlocker.UNVERIFIED_LINEUP_STATE,)


def test_incomplete_schedule_evidence_never_produces_zero_or_rest_defaults():
    result = features(build(home_schedule_history_evidence=None))
    assert result["home_rest_days"].status is FeatureStatus.MISSING
    assert result["home_rest_days"].value is None
    assert result["home_matches_previous_7_days"].status is FeatureStatus.MISSING
    assert result["home_matches_previous_7_days"].value is None


def test_incomplete_player_history_blocks_per_player_and_team_history_features():
    snapshot = build(home_player_history_evidence=None)
    home = next(item for item in snapshot.player_components if item.team_id == "H")
    assert home.status is FeatureStatus.MISSING
    assert home.starts_previous_5 is None
    assert features(snapshot)["home_xi_recent_rating_mean"].status is FeatureStatus.MISSING


def test_contradictory_availability_blocks_affected_features():
    conflicted = dataclasses.replace(player("H", "h1", PlayerRecordKind.STARTER), availability_conflicted=True)
    snapshot = build(player_records=(conflicted, player("A", "a1", PlayerRecordKind.STARTER, seed="d")))
    result = features(snapshot)
    assert result["home_unavailable_player_count"].status is FeatureStatus.BLOCKED
    assert result["home_xi_recent_rating_mean"].status is FeatureStatus.BLOCKED
    home = next(item for item in snapshot.player_components if item.team_id == "H")
    assert home.status is FeatureStatus.BLOCKED


def test_duplicate_historical_identities_fail_closed():
    row = appearance("p1", 4, "H", "h1")
    with pytest.raises(TeamStrengthContextError, match="historical player identity"):
        build(historical_appearances=(row, row))
    match = fixture("f1", 4)
    with pytest.raises(TeamStrengthContextError, match="historical fixture identity"):
        build(historical_fixtures=(match, match))


def test_array_order_is_not_identity_and_full_source_ancestry_is_preserved():
    first = build(player_records=expected_players())
    second = build(player_records=tuple(reversed(expected_players())))
    assert canonical_team_strength_context_snapshot_bytes(first) == canonical_team_strength_context_snapshot_bytes(second)
    assert first.source_evidence_sha256s == tuple(item.evidence_sha256 for item in first.source_evidence)


def test_builder_accepts_no_odds_or_probability_adjustment_and_safety_stays_closed():
    parameters = inspect.signature(build_team_strength_context_snapshot).parameters
    assert not ({"odds", "bookmaker_odds", "expected_goals", "probability", "coefficient"} & set(parameters))
    result = build()
    safety = dict(result.safety)
    assert safety["team_strength_feature_authorized"] is True
    assert all(value is False for key, value in safety.items() if key != "team_strength_feature_authorized")


def test_production_boundary_has_no_acquisition_probability_pricing_or_betting_imports():
    import domain.fotmob_team_strength_fixture_intelligence as production

    tree = ast.parse(inspect.getsource(production))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    forbidden = ("requests", "urllib", "httpx", "score_matrix", "probability", "pricing", "sportybet", "selection", "betting")
    assert not any(any(token in name.lower() for token in forbidden) for name in imported)
