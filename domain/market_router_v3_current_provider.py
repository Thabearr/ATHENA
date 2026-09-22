"""Deprecated compatibility shim; use domain._market_router_current_provider."""

DEPRECATED_COMPATIBILITY_SHIM = True
REPLACEMENT_MODULE = "domain._market_router_current_provider"

from domain._market_router_current_provider import *  # noqa: F401,F403
from domain._market_router_current_provider import __all__
