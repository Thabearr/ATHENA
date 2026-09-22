"""Deprecated compatibility shim; use domain._price_all_current_provider."""

DEPRECATED_COMPATIBILITY_SHIM = True
REPLACEMENT_MODULE = "domain._price_all_current_provider"

from domain._price_all_current_provider import *  # noqa: F401,F403
from domain._price_all_current_provider import __all__
