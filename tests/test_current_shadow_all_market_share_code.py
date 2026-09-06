from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from domain import current_shadow_all_market_share_code as share
from domain._current_shadow_price_core import ShadowOpportunityEligibility, ShadowPriceDisposition
from domain.markets import MarketId, OutcomeId


NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


def _opportunity(
    token, confidence, market, outcome, ev, *, value_eligible=True, line=None,
):
    return SimpleNamespace(
        opportunity_id=token * 64,
        prediction_confidence=confidence,
        prediction_confidence_method="SCALAR_MODEL_PROBABILITY_V1",
        robust_net_expected_value=ev,
        robust_edge=ev / 2,
        value_first_eligibility=(
            ShadowOpportunityEligibility.ELIGIBLE
            if value_eligible
            else ShadowOpportunityEligibility.REJECTED
        ),
        price_result=SimpleNamespace(
            market_id=market,
            outcome_id=outcome,
            line=line,
            disposition=ShadowPriceDisposition.PRICED,
            quote_identity_sha256=token * 64,
            model_probability=confidence,
            settlement_state_probabilities=(),
        ),
    )


def _portfolio(opportunities):
    top = opportunities[0]
    leg = SimpleNamespace(
        fixture_identity="FOTMOB:1",
        provider_event_id="sr:match:1",
        home_team="Home",
        away_team="Away",
        competition="League",
        kickoff_utc=NOW + timedelta(hours=4),
        selected_opportunity_id=top.opportunity_id,
        decimal_odds=1.20,
    )
    source = SimpleNamespace(
        fixture_identity=leg.fixture_identity,
        router_decision=SimpleNamespace(
            opportunities=tuple(opportunities),
            router_policy_id="SHADOW_SOURCE_ALIGNED_SETTLEMENT_AWARE_ROUTER_V3",
        ),
    )
    return SimpleNamespace(
        selected_legs=(leg,),
        _router_inputs=(source,),
        requested_target_size=1,
    )


def _portfolio_many(opportunity_sets, *, target_size):
    legs = []
    sources = []
    for index, opportunities in enumerate(opportunity_sets, start=1):
        top = opportunities[0]
        leg = SimpleNamespace(
            fixture_identity=f"FOTMOB:{index}",
            provider_event_id=f"sr:match:{index}",
            home_team=f"Home {index}",
            away_team=f"Away {index}",
            competition=f"League {index}",
            kickoff_utc=NOW + timedelta(hours=4),
            selected_opportunity_id=top.opportunity_id,
            decimal_odds=1.20,
        )
        source = SimpleNamespace(
            fixture_identity=leg.fixture_identity,
            router_decision=SimpleNamespace(
                opportunities=tuple(opportunities),
                router_policy_id="SHADOW_SOURCE_ALIGNED_SETTLEMENT_AWARE_ROUTER_V3",
            ),
        )
        legs.append(leg)
        sources.append(source)
    return SimpleNamespace(
        selected_legs=tuple(legs),
        _router_inputs=tuple(sources),
        requested_target_size=target_size,
    )


def _install_live(monkeypatch, odds_by_market):
    monkeypatch.setattr(
        share.semantic_bridge,
        "_fetch_event",
        lambda _event: ({"bizCode": 10000}, b"{}", 200, "https://example.test/event"),
    )
    monkeypatch.setattr(share.semantic_bridge, "_event_with_markets", lambda *_args: {})

    def quote(_source, opportunity):
        market = opportunity.price_result.market_id.value
        return SimpleNamespace(
            provider_market_name=market,
            provider_outcome_name=opportunity.price_result.outcome_id.value,
            provider_specifier=None,
        )

    def resolve(*, intent, **_kwargs):
        market = intent["marketName"]
        return (
            {"eventId": intent["eventId"], "marketId": f"m-{market}", "outcomeId": f"o-{market}"},
            {
                "odds": str(odds_by_market[market]),
                "observed_market_name": market,
                "observed_outcome_name": intent["outcomeName"],
                "observed_specifier": None,
            },
        )

    monkeypatch.setattr(share, "_opportunity_quote", quote)
    monkeypatch.setattr(share.semantic_bridge, "resolve_intent", resolve)


def test_top_below_floor_reroutes_by_fresh_settlement_value(tmp_path, monkeypatch):
    top = _opportunity("a", 0.80, MarketId.MATCH_RESULT, OutcomeId.HOME, 0.50)
    next_best = _opportunity("b", 0.70, MarketId.BTTS, OutcomeId.YES, 0.10)
    lower_confidence_higher_value = _opportunity(
        "c", 0.60, MarketId.DOUBLE_CHANCE, OutcomeId.HOME_OR_DRAW, 0.10
    )
    _install_live(monkeypatch, {
        "MATCH_RESULT": 1.08,
        "BTTS": 1.60,
        "DOUBLE_CHANCE": 2.0,
    })
    selections, receipt, legs, events = share._fresh_resolve_portfolio(
        _portfolio((top, next_best, lower_confidence_higher_value)),
        output_dir=tmp_path,
        delay_seconds=0,
    )
    assert len(selections) == 1
    assert legs[0]["selected_opportunity_id"] == lower_confidence_higher_value.opportunity_id
    assert legs[0]["decimal_odds"] == "2.0"
    assert legs[0]["fresh_net_expected_value_diagnostic"] == 0.2
    assert events[0]["reason"] == "SOURCE_ALIGNED_FRESH_FALLBACK"
    top_audit = next(
        item for item in receipt["candidate_audits"][0]["candidates"]
        if item["opportunity_id"] == top.opportunity_id
    )
    assert top_audit["reason"] == "EXACT_CURRENT_ODDS_BELOW_1_09"


def test_top_price_change_above_floor_keeps_prediction_when_fresh_value_stays_highest(
    tmp_path, monkeypatch,
):
    top = _opportunity("a", 0.80, MarketId.MATCH_RESULT, OutcomeId.HOME, 0.20)
    backup = _opportunity("b", 0.70, MarketId.BTTS, OutcomeId.YES, 0.10)
    _install_live(monkeypatch, {"MATCH_RESULT": 1.50, "BTTS": 1.50})
    _selections, _receipt, legs, events = share._fresh_resolve_portfolio(
        _portfolio((top, backup)), output_dir=tmp_path, delay_seconds=0,
    )
    assert legs[0]["selected_opportunity_id"] == top.opportunity_id
    assert legs[0]["decimal_odds"] == "1.5"
    assert legs[0]["stale_portfolio_decimal_odds"] == 1.20
    assert legs[0]["fresh_net_expected_value_diagnostic"] == pytest.approx(0.20)
    assert events == ()


def test_no_positive_fresh_value_drops_fixture_and_records_honest_event(tmp_path, monkeypatch):
    top = _opportunity("a", 0.80, MarketId.MATCH_RESULT, OutcomeId.HOME, 1.0)
    backup = _opportunity("b", 0.70, MarketId.BTTS, OutcomeId.YES, 2.0)
    _install_live(monkeypatch, {"MATCH_RESULT": 1.08, "BTTS": 1.20})
    selections, receipt, legs, events = share._fresh_resolve_portfolio(
        _portfolio((top, backup)), output_dir=tmp_path, delay_seconds=0,
    )
    assert selections == ()
    assert legs == ()
    assert events[0]["to_opportunity_id"] is None
    assert events[0]["reason"] == "NO_CURRENT_PREDICTION_QUALIFIED_FALLBACK"
    backup_audit = next(
        item for item in receipt["candidate_audits"][0]["candidates"]
        if item["opportunity_id"] == backup.opportunity_id
    )
    assert backup_audit["reason"] == "FRESH_SETTLEMENT_AWARE_VALUE_NOT_POSITIVE"


def test_fresh_fallback_preserves_market_family_cap_and_source_aligned_order(
    tmp_path, monkeypatch,
):
    first = (
        _opportunity("a", 0.95, MarketId.MATCH_RESULT, OutcomeId.HOME, 0.20),
        _opportunity("b", 0.85, MarketId.BTTS, OutcomeId.YES, 0.10),
    )
    second = (
        _opportunity("c", 0.94, MarketId.DOUBLE_CHANCE, OutcomeId.HOME_OR_DRAW, 0.20),
        _opportunity("d", 0.84, MarketId.BTTS, OutcomeId.YES, 0.10),
    )
    third = (
        _opportunity("e", 0.93, MarketId.TOTAL_GOALS, OutcomeId.OVER, 0.20),
        _opportunity("f", 0.83, MarketId.BTTS, OutcomeId.YES, 0.20),
        _opportunity("g", 0.70, MarketId.HOME_WIN_TO_NIL, OutcomeId.YES, 0.10),
    )
    _install_live(monkeypatch, {
        "MATCH_RESULT": 1.08,
        "DOUBLE_CHANCE": 1.08,
        "TOTAL_GOALS": 1.08,
        "BTTS": 1.30,
        "HOME_WIN_TO_NIL": 1.60,
    })
    portfolio = _portfolio_many((first, second, third), target_size=4)
    selections, receipt, legs, events = share._fresh_resolve_portfolio(
        portfolio, output_dir=tmp_path, delay_seconds=0,
    )

    assert len(selections) == 3
    assert receipt["market_family_cap"] == 2
    assert receipt["fresh_market_family_counts"] == {"BTTS": 2, "WIN_TO_NIL": 1}
    assert [leg["market_family"] for leg in legs] == ["BTTS", "BTTS", "WIN_TO_NIL"]
    third_candidates = next(
        row["candidates"] for row in receipt["candidate_audits"]
        if row["fixture_identity"] == "FOTMOB:3"
    )
    assert any(
        item["opportunity_id"] == "f" * 64
        and item["reason"] == "CURRENT_MARKET_FAMILY_CAP:BTTS"
        for item in third_candidates
    )
    assert legs[2]["selected_opportunity_id"] == "g" * 64
    assert all(event["reason"] == "SOURCE_ALIGNED_FRESH_FALLBACK" for event in events)


def test_stale_value_gate_and_provider_only_total_line_cannot_reenter_fresh_selection(
    tmp_path, monkeypatch,
):
    stale_rejected = _opportunity(
        "a", 0.95, MarketId.MATCH_RESULT, OutcomeId.HOME, -0.10,
        value_eligible=False,
    )
    provider_only = _opportunity(
        "b", 0.90, MarketId.TOTAL_GOALS, OutcomeId.OVER, 0.20, line=0.5,
    )
    backup = _opportunity("c", 0.70, MarketId.BTTS, OutcomeId.YES, 0.10)
    _install_live(monkeypatch, {
        "MATCH_RESULT": 5.0,
        "TOTAL_GOALS": 5.0,
        "BTTS": 1.60,
    })
    selections, receipt, legs, _events = share._fresh_resolve_portfolio(
        _portfolio((stale_rejected, provider_only, backup)),
        output_dir=tmp_path,
        delay_seconds=0,
    )
    assert len(selections) == 1
    assert legs[0]["selected_opportunity_id"] == backup.opportunity_id
    audits = receipt["candidate_audits"][0]["candidates"]
    assert next(item for item in audits if item["opportunity_id"] == stale_rejected.opportunity_id)["reason"] == "SOURCE_ALIGNED_SETTLEMENT_VALUE_GATE_REJECTED"
    assert next(item for item in audits if item["opportunity_id"] == provider_only.opportunity_id)["reason"].startswith("SOURCE_MARKET_POLICY_REJECTED:")


def test_ambiguous_provider_semantics_fail_closed_without_nearby_substitution(tmp_path, monkeypatch):
    top = _opportunity("a", 0.80, MarketId.MATCH_RESULT, OutcomeId.HOME, 1.0)
    _install_live(monkeypatch, {"MATCH_RESULT": 1.20})

    def ambiguous(**_kwargs):
        raise share.semantic_bridge.SportyBetSemanticShareError("found 2")

    monkeypatch.setattr(share.semantic_bridge, "resolve_intent", ambiguous)
    selections, receipt, legs, events = share._fresh_resolve_portfolio(
        _portfolio((top,)), output_dir=tmp_path, delay_seconds=0,
    )
    assert selections == () and legs == ()
    assert "EXACT_PROVIDER_SEMANTICS_UNAVAILABLE" in receipt["candidate_audits"][0]["candidates"][0]["reason"]
    assert events[0]["to_opportunity_id"] is None


def test_direct_value_reasons_fail_closed_after_roundtrip_reprice():
    assert share._direct_value_reasons(({
        "fixture_identity": "FOTMOB:1",
        "fresh_net_expected_value_diagnostic": -0.001,
    },)) == ("FOTMOB:1:DIRECT_PROVIDER_SETTLEMENT_AWARE_VALUE_NOT_POSITIVE",)
    assert share._direct_value_reasons(({
        "fixture_identity": "FOTMOB:1",
        "fresh_net_expected_value_diagnostic": 0.001,
    },)) == ()


def test_roundtrip_requires_exact_fresh_odds_and_identity():
    leg = {
        "fixture_identity": "FOTMOB:1", "provider_event_id": "sr:match:1",
        "home_team": "Home", "away_team": "Away", "provider_market_id": "1",
        "provider_market_name": "1X2", "provider_specifier": None,
        "provider_outcome_id": "1", "provider_outcome_name": "Home",
        "decimal_odds": "1.11",
    }
    accepted = [{
        "eventId": "sr:match:1", "homeTeamName": "Home", "awayTeamName": "Away",
        "markets": [{"id": "1", "desc": "1X2", "specifier": None,
                     "outcomes": [{"id": "1", "desc": "Home", "odds": "1.11"}]}],
    }]
    receipt = {
        "create_unavailable_outcomes": 0, "load_unavailable_outcomes": 0,
        "selection_count": 1, "create_accepted_selection_count": 1,
        "load_accepted_selection_count": 1,
        "exact_roundtrip_selection_identity_verified": True,
        "create_accepted_outcomes": accepted, "load_accepted_outcomes": accepted,
        "sportybet_login_used": False, "sportybet_cookie_used": False,
        "sportybet_wallet_used": False, "stake_submitted": False, "wager_placed": False,
    }
    assert share._verify_roundtrip((leg,), receipt) == ()
    receipt["load_accepted_outcomes"] = [dict(accepted[0])]
    receipt["load_accepted_outcomes"][0] = {
        **accepted[0], "markets": [{**accepted[0]["markets"][0], "outcomes": [{"id": "1", "desc": "Home", "odds": "1.12"}]}],
    }
    assert "DIRECT_TRANSPORT_CREATE_RELOAD_CHANGED" in share._verify_roundtrip((leg,), receipt)
