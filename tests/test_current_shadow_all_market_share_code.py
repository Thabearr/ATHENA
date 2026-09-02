from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from domain import current_shadow_all_market_share_code as share
from domain._current_shadow_price_core import ShadowPriceDisposition
from domain.markets import MarketId, OutcomeId


NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


def _opportunity(token, confidence, market, outcome, ev):
    return SimpleNamespace(
        opportunity_id=token * 64,
        prediction_confidence=confidence,
        prediction_confidence_method="SCALAR_MODEL_PROBABILITY_V1",
        robust_net_expected_value=ev,
        robust_edge=ev / 2,
        price_result=SimpleNamespace(
            market_id=market,
            outcome_id=outcome,
            line=None,
            disposition=ShadowPriceDisposition.PRICED,
            quote_identity_sha256=token * 64,
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
            router_policy_id="SHADOW_PREDICTION_FIRST_ROUTER_V2",
        ),
    )
    return SimpleNamespace(
        selected_legs=(leg,),
        _router_inputs=(source,),
        requested_target_size=1,
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


def test_top_below_floor_reroutes_by_confidence_not_value(tmp_path, monkeypatch):
    top = _opportunity("a", 0.80, MarketId.MATCH_RESULT, OutcomeId.HOME, 0.50)
    next_best = _opportunity("b", 0.70, MarketId.BTTS, OutcomeId.YES, -0.50)
    lower = _opportunity("c", 0.60, MarketId.DOUBLE_CHANCE, OutcomeId.HOME_OR_DRAW, 9.0)
    _install_live(monkeypatch, {
        "MATCH_RESULT": 1.08,
        "BTTS": 1.15,
        "DOUBLE_CHANCE": 5.0,
    })
    selections, receipt, legs, events = share._fresh_resolve_portfolio(
        _portfolio((top, next_best, lower)), output_dir=tmp_path, delay_seconds=0,
    )
    assert len(selections) == 1
    assert legs[0]["selected_opportunity_id"] == next_best.opportunity_id
    assert legs[0]["decimal_odds"] == "1.15"
    assert events[0]["reason"] == "PREDICTION_FIRST_FRESH_FALLBACK"
    assert receipt["candidate_audits"][0]["candidates"][0]["reason"] == "EXACT_CURRENT_ODDS_BELOW_1_09"


def test_top_price_change_above_floor_keeps_prediction_and_fresh_odds(tmp_path, monkeypatch):
    top = _opportunity("a", 0.80, MarketId.MATCH_RESULT, OutcomeId.HOME, -0.50)
    backup = _opportunity("b", 0.70, MarketId.BTTS, OutcomeId.YES, 5.0)
    _install_live(monkeypatch, {"MATCH_RESULT": 1.11, "BTTS": 3.0})
    _selections, _receipt, legs, events = share._fresh_resolve_portfolio(
        _portfolio((top, backup)), output_dir=tmp_path, delay_seconds=0,
    )
    assert legs[0]["selected_opportunity_id"] == top.opportunity_id
    assert legs[0]["decimal_odds"] == "1.11"
    assert legs[0]["stale_portfolio_decimal_odds"] == 1.20
    assert events == ()


def test_no_fallback_drops_fixture_and_records_honest_event(tmp_path, monkeypatch):
    top = _opportunity("a", 0.80, MarketId.MATCH_RESULT, OutcomeId.HOME, 1.0)
    backup = _opportunity("b", 0.70, MarketId.BTTS, OutcomeId.YES, 2.0)
    _install_live(monkeypatch, {"MATCH_RESULT": 1.08, "BTTS": 1.01})
    selections, _receipt, legs, events = share._fresh_resolve_portfolio(
        _portfolio((top, backup)), output_dir=tmp_path, delay_seconds=0,
    )
    assert selections == ()
    assert legs == ()
    assert events[0]["to_opportunity_id"] is None
    assert events[0]["reason"] == "NO_CURRENT_PREDICTION_QUALIFIED_FALLBACK"


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
