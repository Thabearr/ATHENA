from __future__ import annotations

from copy import deepcopy

import pytest

from domain import current_all_market_shadow_probability_settlement as prc
from domain.current_shadow_market_probability_adapter import (
    market_probability_bundle_from_current_shadow_fixture_scan,
)
from domain.market_probabilities import (
    MarketProbabilityBundle,
    MarketProbabilityError,
    ProbabilityAvailability,
    canonical_json_bytes,
)
from domain.markets import MarketId, OutcomeId


FIXTURE = "FOTMOB:P12:1001"
A = "a" * 64
B = "b" * 64
SUPPORTED = "SUPPORTED"
BLOCKED = "CURRENT_PROVIDER_UNAVAILABLE/UNPROVEN"


def _xg() -> prc.ResearchXGRates:
    return prc.ResearchXGRates(
        calibrated_home=1.72,
        calibrated_away=0.91,
        sealed_prediction_sha256=A,
        history_prefix_identity=B,
        source_fixture_identity=FIXTURE,
    )


def _scan(provider_status: str | None = None):
    provider = (
        None
        if provider_status is None
        else {market: provider_status for market in MarketId}
    )
    return prc.scan_fixture_all_markets(
        fixture_identity=FIXTURE,
        research_xg=_xg(),
        kickoff_utc_iso="2026-09-12T15:00:00Z",
        total_goals_lines=(0.5, 1.5, 2.5, 3.5, 4.5),
        asian_handicap_home_lines=(-0.75, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75),
        provider_semantic_by_market=provider,
    )


def _bundle(provider_status: str | None = None) -> MarketProbabilityBundle:
    return market_probability_bundle_from_current_shadow_fixture_scan(
        _scan(provider_status)
    )


def test_bundle_round_trip_is_byte_canonical_and_immutable() -> None:
    bundle = _bundle()
    raw = canonical_json_bytes(bundle)
    rebuilt = MarketProbabilityBundle.from_canonical_bytes(raw)
    assert canonical_json_bytes(rebuilt) == raw
    assert rebuilt.canonical_sha256 == bundle.canonical_sha256
    with pytest.raises(TypeError):
        bundle.model_evidence["mutate"] = True  # type: ignore[index]


def test_bundle_has_exact_market_coverage_and_score_grid_identity() -> None:
    bundle = _bundle()
    assert tuple(row.market_id for row in bundle.markets) == tuple(MarketId)
    assert bundle.score_grid is not None
    assert len(bundle.score_grid.sha256) == 64
    assert bundle.score_grid.identity_method == "normalized_score_matrix_content_sha256"
    assert all(value is False for value in bundle.authority.values())


def test_provider_pricing_and_selected_market_fields_are_absent() -> None:
    raw = canonical_json_bytes(_bundle())
    for forbidden in (
        b"decimal_odds",
        b"odds_raw",
        b"quote_identity_sha256",
        b"recommended_market",
        b"selected_market",
        b"provider_event_id",
        b"provider_market_id",
    ):
        assert forbidden not in raw


def test_provider_semantic_overlay_does_not_change_football_probability_bundle() -> None:
    supported = _bundle(SUPPORTED)
    blocked = _bundle(BLOCKED)
    assert canonical_json_bytes(supported) == canonical_json_bytes(blocked)


def test_total_goals_are_partitioned_and_monotone_across_lines() -> None:
    row = _bundle().market(MarketId.TOTAL_GOALS)
    assert row.availability is ProbabilityAvailability.AVAILABLE
    by_line: dict[float, dict[OutcomeId, float]] = {}
    for event in row.event_probabilities:
        assert event.line is not None
        by_line.setdefault(event.line, {})[event.outcome_id] = event.probability
    lines = sorted(by_line)
    overs = [by_line[line][OutcomeId.OVER] for line in lines]
    unders = [by_line[line][OutcomeId.UNDER] for line in lines]
    assert all(left >= right for left, right in zip(overs, overs[1:]))
    assert all(left <= right for left, right in zip(unders, unders[1:]))
    assert all(
        abs(by_line[line][OutcomeId.OVER] + by_line[line][OutcomeId.UNDER] - 1.0) < 1e-12
        for line in lines
    )


def test_non_monotone_total_goals_fail_closed() -> None:
    payload = _bundle().to_dict()
    row = next(item for item in payload["markets"] if item["market_id"] == "TOTAL_GOALS")
    lines = sorted({item["line"] for item in row["event_probabilities"]})
    first, second = lines[:2]
    for item in row["event_probabilities"]:
        if item["line"] == first and item["outcome_id"] == "OVER":
            item["probability"] = 0.2
        elif item["line"] == first and item["outcome_id"] == "UNDER":
            item["probability"] = 0.8
        elif item["line"] == second and item["outcome_id"] == "OVER":
            item["probability"] = 0.3
        elif item["line"] == second and item["outcome_id"] == "UNDER":
            item["probability"] = 0.7
    with pytest.raises(MarketProbabilityError, match="monotone"):
        MarketProbabilityBundle.from_dict(payload)


def test_invalid_partition_probability_mass_fails_closed() -> None:
    payload = _bundle().to_dict()
    row = next(item for item in payload["markets"] if item["market_id"] == "MATCH_RESULT")
    row["event_probabilities"][0]["probability"] = 0.9
    row["event_probabilities"][1]["probability"] = 0.9
    row["event_probabilities"][2]["probability"] = 0.1
    with pytest.raises(MarketProbabilityError, match="partition"):
        MarketProbabilityBundle.from_dict(payload)


def test_invalid_settlement_probability_mass_fails_closed() -> None:
    payload = _bundle().to_dict()
    row = next(item for item in payload["markets"] if item["market_id"] == "DRAW_NO_BET")
    settlement = row["settlement_distributions"][0]
    settlement.update(
        full_win=0.7,
        half_win=0.0,
        push=0.2,
        half_loss=0.0,
        full_loss=0.2,
    )
    with pytest.raises(MarketProbabilityError, match="mass"):
        MarketProbabilityBundle.from_dict(payload)


def test_pricing_or_selection_evidence_cannot_be_smuggled_into_bundle() -> None:
    payload = _bundle().to_dict()
    payload["model_evidence"]["provider_odds"] = 1.8
    with pytest.raises(MarketProbabilityError, match="boundary"):
        MarketProbabilityBundle.from_dict(payload)

    payload = _bundle().to_dict()
    specialist = payload["specialist_outputs"][0]
    specialist["evidence"]["quote_identity_sha256"] = "c" * 64
    with pytest.raises(MarketProbabilityError, match="boundary"):
        MarketProbabilityBundle.from_dict(payload)

    payload = _bundle().to_dict()
    payload["model_evidence"]["recommended_market"] = "MATCH_RESULT"
    with pytest.raises(MarketProbabilityError, match="boundary"):
        MarketProbabilityBundle.from_dict(payload)


def test_extra_or_ambiguous_contract_fields_fail_closed() -> None:
    payload = _bundle().to_dict()
    payload["selected_market"] = "MATCH_RESULT"
    with pytest.raises(MarketProbabilityError, match="fields drifted"):
        MarketProbabilityBundle.from_dict(payload)

    raw = canonical_json_bytes(_bundle())
    noncanonical = raw[:-1] + b"  \n"
    with pytest.raises(MarketProbabilityError, match="not canonical"):
        MarketProbabilityBundle.from_canonical_bytes(noncanonical)


def test_duplicate_json_keys_and_nonfinite_constants_fail_closed() -> None:
    raw = canonical_json_bytes(_bundle())
    duplicated = raw.replace(
        b'"schema_version":1',
        b'"schema_version":1,"schema_version":1',
        1,
    )
    with pytest.raises(MarketProbabilityError, match="duplicate JSON key"):
        MarketProbabilityBundle.from_canonical_bytes(duplicated)

    nonfinite = raw.replace(b'"calibrated_home":1.72', b'"calibrated_home":NaN', 1)
    with pytest.raises(MarketProbabilityError, match="non-finite JSON constant"):
        MarketProbabilityBundle.from_canonical_bytes(nonfinite)


def test_specialist_score_grid_evidence_is_bound_to_bundle_identity() -> None:
    payload = deepcopy(_bundle().to_dict())
    early = next(
        item
        for item in payload["specialist_outputs"]
        if item["market_id"] == "MATCH_RESULT_1UP"
    )
    early["evidence"]["score_matrix_sha256"] = "f" * 64
    with pytest.raises(MarketProbabilityError, match="score-grid identity"):
        MarketProbabilityBundle.from_dict(payload)


def test_available_specialist_market_requires_explicit_specialist_output() -> None:
    payload = _bundle().to_dict()
    payload["specialist_outputs"] = [
        item
        for item in payload["specialist_outputs"]
        if item["market_id"] != "MATCH_RESULT_1UP"
    ]
    with pytest.raises(MarketProbabilityError, match="requires explicit specialist output"):
        MarketProbabilityBundle.from_dict(payload)


def test_available_score_grid_market_requires_exact_score_grid_identity() -> None:
    payload = _bundle().to_dict()
    payload["score_grid"] = None
    with pytest.raises(MarketProbabilityError, match="requires score-grid identity"):
        MarketProbabilityBundle.from_dict(payload)


def test_no_reviewed_xg_produces_truthful_blocked_bundle_without_score_grid() -> None:
    scan = prc.scan_fixture_all_markets(
        fixture_identity=FIXTURE,
        research_xg=None,
        kickoff_utc_iso="2026-09-12T15:00:00Z",
        total_goals_lines=(1.5, 2.5),
        asian_handicap_home_lines=(-0.5, 0.0, 0.5),
        provider_semantic_by_market=None,
    )
    bundle = market_probability_bundle_from_current_shadow_fixture_scan(scan)
    assert bundle.score_grid is None
    assert bundle.specialist_outputs == ()
    assert all(
        row.availability is ProbabilityAvailability.BLOCKED
        for row in bundle.markets
    )
    assert all(not row.event_probabilities for row in bundle.markets)
    assert all(not row.settlement_distributions for row in bundle.markets)
