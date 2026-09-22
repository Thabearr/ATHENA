"""Deprecated compatibility shim for the former Portfolio provider module.

Import ``domain._portfolio_optimizer_current_provider`` in new code.  This
module remains only to preserve the exact historical public API during
migration.
"""
from __future__ import annotations

from domain import _portfolio_optimizer_current_provider as _replacement


DEPRECATED_COMPATIBILITY_SHIM = True
REPLACEMENT_MODULE = "domain._portfolio_optimizer_current_provider"

__all__ = list(_replacement.__all__)

for _name in __all__:
    globals()[_name] = getattr(_replacement, _name)
