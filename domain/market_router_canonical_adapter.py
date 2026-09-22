"""Deprecated compatibility shim; import the canonical API from domain.market_router."""

from domain.market_router import *  # noqa: F401,F403
from domain.market_router import __all__
from domain.market_router import (
    _prediction_identity_sha256,
    _rank_opportunities,
    _selection_rank_key,
)
