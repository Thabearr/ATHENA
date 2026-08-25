"""Domain models shared across ATHENA's prediction and export boundaries.

The historical as-of implementation has an internal split solely to keep its
source-owned issuance facade small and reviewable.  Load that facade while the
package initializes, then make both the implementation module import name and
the package attribute resolve to the same hardened module object.  Normal Python
imports therefore cannot bypass the canonical issuance boundary by importing
the underscore implementation first or through ``from domain import ...``.
"""
from __future__ import annotations

import importlib
import sys

_historical_asof_features = importlib.import_module(
    ".historical_asof_features", __name__
)
_historical_asof_features_impl = _historical_asof_features
sys.modules[
    f"{__name__}._historical_asof_features_impl"
] = _historical_asof_features
