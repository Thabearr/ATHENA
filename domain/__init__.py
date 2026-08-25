"""Domain models shared across ATHENA's prediction and export boundaries.

The historical as-of and historical-training-coverage implementations use
internal splits solely to keep their source-owned issuance facades small and
reviewable. Package initialization makes normal imports of each underscore
implementation resolve to its hardened facade, so a caller cannot bypass a
canonical evidence boundary by importing the implementation module directly.
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

_historical_training_coverage = importlib.import_module(
    ".historical_training_coverage", __name__
)
_training_coverage_post_hardening = importlib.import_module(
    "._historical_training_coverage_post_hardening", __name__
)
_training_coverage_post_hardening.install(_historical_training_coverage)
_historical_training_coverage_impl = _historical_training_coverage
sys.modules[
    f"{__name__}._historical_training_coverage_impl"
] = _historical_training_coverage
