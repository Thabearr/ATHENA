"""Research-only Elo-only xG fallback for Current Shadow current-as-of inference.

The reviewed UTC-native feature constructor intentionally keeps missing home form,
away form and fatigue missing.  Current Shadow must not impute those values or
silently broaden the frozen historical feature scope.  When the full five-feature
current-as-of model is therefore incomplete, this boundary may consume only the
two always-reviewed overall Elo features and the already-frozen
``FOTMOB_NATIVE_ELO_ONLY_NESTED_GLM`` coefficients from the reviewed validation
family.

This is a research/shadow fallback only.  It does not alter PR149 fresh-holdout
complete-case membership, mint a sealed prediction, approve a successor model,
or grant production/probability/pricing/selection/SportyBet/BET authority.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping

from domain import current_fotmob_utc_native_current_asof_xg as current_asof
from domain import fotmob_utc_native_expected_goals_fresh_holdout as fresh
from domain import (
    fotmob_utc_native_expected_goals_fresh_holdout_calibration_competition_protocol
    as pr148,
)
from domain import fotmob_utc_native_expected_goals_model_validation_result_review as review


SCHEMA_VERSION = 1
DATASET_NAME = "athena-current-fotmob-utc-native-current-asof-elo-only-xg-v1"
STATUS = "RESEARCH_ONLY_CURRENT_AS_OF_ELO_ONLY_XG"
COMPLETE = "CURRENT_AS_OF_RESEARCH_XG_ELO_ONLY_COMPLETE"
MODEL_ID = "FOTMOB_NATIVE_ELO_ONLY_NESTED_GLM"
REVIEW_BASIS = (
    "REVIEWED_UTC_NATIVE_VALIDATION_ELO_ONLY_NESTED_GLM_"
    "FROZEN_PR148_COEFFICIENTS_MISSING_FORM_FATIGUE_NOT_IMPUTED"
)

_AUTHORITY = MappingProxyType(
    {
        "production_model": False,
        "production_probability": False,
        "pricing": False,
        "selection": False,
        "sportybet_execution": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
    }
)
_ALLOWED_MISSING = frozenset({"home_form", "away_form", "fatigue"})


class CurrentAsOfEloOnlyXGError(ValueError):
    pass


def _error(message: str) -> CurrentAsOfEloOnlyXGError:
    return CurrentAsOfEloOnlyXGError(message)


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _sha(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise _error(f"{label} must be exact lowercase SHA-256")
    return value


def _finite(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise _error(f"{label} must be finite numeric")
    return float(value)


def _rate(predictors: tuple[float, ...], coefficients: tuple[float, ...], label: str) -> float:
    if len(predictors) != len(coefficients):
        raise _error(f"{label} predictor/coefficient dimension mismatch")
    eta = math.fsum(
        float(value) * float(coefficient)
        for value, coefficient in zip(predictors, coefficients)
    )
    if not math.isfinite(eta):
        raise _error(f"{label} linear predictor is non-finite")
    try:
        value = math.exp(eta)
    except OverflowError as exc:
        raise _error(f"{label} expected-goals rate overflowed") from exc
    if not math.isfinite(value) or value <= 0.0:
        raise _error(f"{label} expected-goals rate must be finite and positive")
    return value


def _elo_only_rates(features: Mapping[str, float]) -> dict[str, float]:
    if set(features) != {"home_elo", "away_elo"}:
        raise _error("Elo-only current-as-of fallback requires exactly two Elo features")
    home = _finite(features["home_elo"], "home_elo")
    away = _finite(features["away_elo"], "away_elo")
    predictors = (1.0, (home - 1500.0) / 400.0, (away - 1500.0) / 400.0)
    return {
        "elo_only_home": _rate(
            predictors,
            tuple(pr148.ELO_ONLY_HOME_COEFFICIENTS),
            "Elo-only home",
        ),
        "elo_only_away": _rate(
            predictors,
            tuple(pr148.ELO_ONLY_AWAY_COEFFICIENTS),
            "Elo-only away",
        ),
    }


def _verify_review_basis() -> None:
    reviewed = review.build_fotmob_utc_native_expected_goals_model_validation_result_review()
    if reviewed.get("review_state") != review.REVIEW_STATE:
        raise _error("reviewed UTC-native model-validation state changed")
    decision = reviewed.get("reviewed_decision")
    if (
        type(decision) is not dict
        or decision.get("positive_predictive_signal_retained_for_research") is not True
        or decision.get("native_refit_successor_candidate_approved") is not False
        or decision.get("automatic_model_approval") is not False
    ):
        raise _error("reviewed research-only model decision changed")
    protocol = pr148.build_fresh_holdout_home_calibration_competition_identity_protocol()
    frozen = protocol.get("frozen_model_rates")
    if (
        type(frozen) is not dict
        or frozen.get("elo_only_predictors")
        != ["INTERCEPT", "(HOME_ELO-1500)/400", "(AWAY_ELO-1500)/400"]
        or frozen.get("elo_only_home_coefficients") != list(pr148.ELO_ONLY_HOME_COEFFICIENTS)
        or frozen.get("elo_only_away_coefficients") != list(pr148.ELO_ONLY_AWAY_COEFFICIENTS)
        or frozen.get("fresh_labels_may_not_refit_any_coefficient") is not True
    ):
        raise _error("frozen reviewed Elo-only rate contract changed")
    semantics = protocol.get("feature_semantics")
    if (
        type(semantics) is not dict
        or semantics.get("missing_features_are_missing_not_imputed") is not True
        or semantics.get("historical_feature_scope_may_not_silently_expand_to_all_competitions")
        is not True
    ):
        raise _error("reviewed missing-feature semantics changed")


@dataclasses.dataclass(frozen=True)
class CurrentAsOfEloOnlyXGAssessment:
    schema_version: int
    dataset_name: str
    status: str
    completeness_status: str
    model_id: str
    review_basis: str
    source_assessment_sha256: str
    history_prefix_sha256: str
    feature_projection_sha256: str
    missing_full_model_feature_ids: tuple[str, ...]
    features: Mapping[str, float]
    rates: Mapping[str, float]
    authority: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or self.dataset_name != DATASET_NAME:
            raise _error("Elo-only assessment schema mismatch")
        if self.status != STATUS or self.completeness_status != COMPLETE:
            raise _error("Elo-only assessment status mismatch")
        if self.model_id != MODEL_ID or self.review_basis != REVIEW_BASIS:
            raise _error("Elo-only assessment model basis changed")
        for value, label in (
            (self.source_assessment_sha256, "source_assessment_sha256"),
            (self.history_prefix_sha256, "history_prefix_sha256"),
            (self.feature_projection_sha256, "feature_projection_sha256"),
        ):
            _sha(value, label)
        missing = self.missing_full_model_feature_ids
        if (
            type(missing) is not tuple
            or not missing
            or tuple(sorted(set(missing))) != missing
            or not set(missing).issubset(_ALLOWED_MISSING)
        ):
            raise _error("Elo-only fallback missing-feature proof changed")
        features = {key: _finite(value, key) for key, value in dict(self.features).items()}
        expected = _elo_only_rates(features)
        rates = dict(self.rates)
        if set(rates) != set(expected):
            raise _error("Elo-only rate vocabulary changed")
        for key, expected_value in expected.items():
            if type(rates[key]) is not float or rates[key] != expected_value:
                raise _error(f"{key} differs from frozen Elo-only transform")
        if dict(self.authority) != dict(_AUTHORITY):
            raise _error("Elo-only fallback authority changed")
        object.__setattr__(self, "features", MappingProxyType(features))
        object.__setattr__(self, "rates", MappingProxyType(rates))
        object.__setattr__(self, "authority", MappingProxyType(dict(_AUTHORITY)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "status": self.status,
            "completeness_status": self.completeness_status,
            "model_id": self.model_id,
            "review_basis": self.review_basis,
            "source_assessment_sha256": self.source_assessment_sha256,
            "history_prefix_sha256": self.history_prefix_sha256,
            "feature_projection_sha256": self.feature_projection_sha256,
            "missing_full_model_feature_ids": list(self.missing_full_model_feature_ids),
            "features": dict(self.features),
            "rates": dict(self.rates),
            "authority": dict(self.authority),
            "wager_placed": False,
        }


def build_current_asof_elo_only_xg_assessment(
    source_assessment: current_asof.CurrentAsOfXGAssessment,
) -> CurrentAsOfEloOnlyXGAssessment:
    """Project only source-derived Elo when the full current-as-of model is incomplete."""

    _verify_review_basis()
    if type(source_assessment) is not current_asof.CurrentAsOfXGAssessment:
        raise _error("source assessment must be exact CurrentAsOfXGAssessment")
    source = dataclasses.replace(source_assessment)
    if source.disposition is not current_asof.CurrentAsOfXGDisposition.MISSING_REVIEWED_FEATURES:
        raise _error("Elo-only fallback is only valid for missing full-model features")
    if source.rates:
        raise _error("missing full-model assessment unexpectedly carries rates")
    missing = tuple(source.missing_feature_ids)
    if not missing or not set(missing).issubset(_ALLOWED_MISSING):
        raise _error("full-model missing features escaped reviewed reduced-model scope")
    available = dict(source.features)
    if "home_elo" not in available or "away_elo" not in available:
        raise _error("reviewed overall Elo inputs are unavailable")
    features = {
        "home_elo": _finite(available["home_elo"], "home_elo"),
        "away_elo": _finite(available["away_elo"], "away_elo"),
    }
    rates = _elo_only_rates(features)
    source_sha = hashlib.sha256(_canonical(source.to_dict())).hexdigest()
    return CurrentAsOfEloOnlyXGAssessment(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        status=STATUS,
        completeness_status=COMPLETE,
        model_id=MODEL_ID,
        review_basis=REVIEW_BASIS,
        source_assessment_sha256=source_sha,
        history_prefix_sha256=source.history_prefix_sha256,
        feature_projection_sha256=source.feature_projection_sha256,
        missing_full_model_feature_ids=missing,
        features=features,
        rates=rates,
        authority=_AUTHORITY,
    )


def policy_summary() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "status": STATUS,
        "completeness_status": COMPLETE,
        "model_id": MODEL_ID,
        "review_basis": REVIEW_BASIS,
        "missing_feature_imputation": False,
        "historical_feature_scope_expansion": False,
        "fresh_holdout_mutation": False,
        "authority": dict(_AUTHORITY),
        "wager_placed": False,
    }


__all__ = [
    "COMPLETE",
    "CurrentAsOfEloOnlyXGAssessment",
    "CurrentAsOfEloOnlyXGError",
    "DATASET_NAME",
    "MODEL_ID",
    "REVIEW_BASIS",
    "SCHEMA_VERSION",
    "STATUS",
    "build_current_asof_elo_only_xg_assessment",
    "policy_summary",
]
