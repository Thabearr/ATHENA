from domain import current_shadow_all_market_portfolio as portfolio
from domain import current_shadow_all_market_router as router
from domain._current_shadow_price_core import (
    AUTHORITY_FLAGS,
    MINIMUM_SELECTABLE_OVER_TOTAL_GOALS_LINE,
    ROUTER_POLICY_ID,
)


def test_current_shadow_source_aligned_v3_policy_contract_is_explicit():
    assert ROUTER_POLICY_ID == "SHADOW_SOURCE_ALIGNED_SETTLEMENT_AWARE_ROUTER_V3"
    assert router.ROUTER_POLICY_ID == ROUTER_POLICY_ID
    assert (
        portfolio.PORTFOLIO_POLICY_ID
        == "SHADOW_SOURCE_ALIGNED_SETTLEMENT_AWARE_PORTFOLIO_V3"
    )
    assert (
        portfolio.JOINT_SELECTION_POLICY_ID
        == "SETTLEMENT_AWARE_EV_THEN_CONFIDENCE_THEN_CANONICAL_IDENTITY_WITH_HARD_CAPS_V3"
    )
    assert MINIMUM_SELECTABLE_OVER_TOTAL_GOALS_LINE == 1.5
    assert AUTHORITY_FLAGS["wager_placed"] is False
