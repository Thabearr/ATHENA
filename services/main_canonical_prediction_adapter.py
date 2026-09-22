"""One-way MAIN canonical RouterDecision -> legacy Prediction projection.

This module is a presentation compatibility boundary, not a decision engine.  It
resolves the source-controlled MAIN canonical core, verifies an exact supplied
RouterDecision, and projects only the verified Router outcome into the legacy
``Prediction`` presentation fields.  No model, pricing, routing, provider, or
legacy selector logic lives here.
"""
from __future__ import annotations

import math
from functools import lru_cache
from types import MappingProxyType
from typing import Any

from domain import canonical_core as _canonical_core
from domain import market_router as _canonical_router
from domain import markets as _markets
from domain import run_contracts as _run_contracts
from models.prediction import Prediction


POLICY_ID = "ATHENA_P3_1_MAIN_CANONICAL_PREDICTION_PRESENTATION_V1"
REGIME_ID = _canonical_core.CURRENT_SPORTYBET_PROVIDER
EXPECTED_ROUTER_COMPONENT_ID = "domain.market_router"
EXPECTED_ROUTER_CONTRACT_SHA256 = (
    "85b4b5c712154f7d4708eb53e9cadfcb7c65dc21bdb12cd94cf1b8cd48795e32"
)
EXPECTED_ROUTER_ARTIFACT_GIT_BLOB_SHA = "713ceef02b77a62d3c0b8ff1958e27dc438d42c3"
NO_RECOMMENDATION = "No Recommendation"
NO_ROUTER_REASON = "Canonical RouterDecision unavailable; recommendation withheld."

MAIN_AUTHORITY_MANIFEST = _run_contracts.AuthorityManifest(
    authority_profile="MAIN",
    mode="main_application",
    provider_acquisition=False,
    share_code_generation=False,
    login=False,
    cookies=False,
    wallet=False,
    staking=False,
    wager=False,
)

AUTHORITY = MappingProxyType(
    {
        "authority_profile": "MAIN",
        "canonical_core_resolution": True,
        "canonical_router_verification": True,
        "presentation_projection_only": True,
        "provider_acquisition": False,
        "share_code_generation": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "wager_placed": False,
    }
)


class MainCanonicalPredictionAdapterError(ValueError):
    """The MAIN canonical presentation boundary failed closed."""


def _require_exact_prediction(value: Any) -> Prediction:
    if type(value) is not Prediction:
        raise MainCanonicalPredictionAdapterError(
            "exact models.prediction.Prediction is required"
        )
    return value


@lru_cache(maxsize=1)
def resolve_main_canonical_core() -> _canonical_core.CanonicalCoreBindings:
    """Resolve the reviewed MAIN canonical core and exact Router owner."""

    try:
        bindings = _canonical_core.resolve_canonical_core(
            MAIN_AUTHORITY_MANIFEST,
            regime_id=REGIME_ID,
        )
        if bindings.authority_profile != "MAIN":
            raise MainCanonicalPredictionAdapterError(
                "MAIN canonical core profile drifted"
            )
        if bindings.share_code_generation is not False:
            raise MainCanonicalPredictionAdapterError(
                "MAIN presentation authority unexpectedly permits share-code generation"
            )
        record = bindings.record_for("market_router")
        if (
            record.responsibility_id != "market_router"
            or record.component_id != EXPECTED_ROUTER_COMPONENT_ID
            or record.contract_sha256 != EXPECTED_ROUTER_CONTRACT_SHA256
            or record.artifact_git_blob_sha != EXPECTED_ROUTER_ARTIFACT_GIT_BLOB_SHA
            or record.main_authority is not True
            or "MAIN" not in record.allowed_profiles
        ):
            raise MainCanonicalPredictionAdapterError(
                "MAIN canonical Router owner identity drifted"
            )
        return bindings
    except MainCanonicalPredictionAdapterError:
        raise
    except Exception as exc:
        raise MainCanonicalPredictionAdapterError(
            "MAIN canonical core resolution failed closed"
        ) from exc


def clear_main_canonical_core_cache() -> None:
    """Clear only the process-local proof cache; never mutates registry state."""

    resolve_main_canonical_core.cache_clear()


def _append_reason(prediction: Prediction, reason: str) -> None:
    if reason not in prediction.reasons:
        prediction.reasons.append(reason)


def _set_no_recommendation(prediction: Prediction, *, reasons: tuple[str, ...] = ()) -> Prediction:
    prediction.recommended_market = NO_RECOMMENDATION
    prediction.market_confidence = 0.0
    prediction.ranked_markets = []
    for reason in reasons:
        _append_reason(prediction, reason)
    return prediction


def _verify_router_decision(value: Any) -> _canonical_router.RouterDecision:
    if type(value) is not _canonical_router.RouterDecision:
        raise MainCanonicalPredictionAdapterError(
            "exact canonical domain.market_router.RouterDecision is required"
        )
    try:
        verified = _canonical_router.verify_router_decision(value)
    except Exception as exc:
        raise MainCanonicalPredictionAdapterError(
            "canonical RouterDecision verification failed closed"
        ) from exc
    if type(verified) is not _canonical_router.RouterDecision:
        raise MainCanonicalPredictionAdapterError(
            "canonical RouterDecision verification returned an unexpected type"
        )
    return verified


def project_canonical_router_decision(
    prediction: Prediction,
    router_decision: _canonical_router.RouterDecision | None = None,
) -> Prediction:
    """Project verified canonical Router authority into legacy presentation fields.

    The caller may supply no decision, in which case the legacy object remains
    available for descriptive analysis but recommendation authority is withheld.
    """

    prediction = _require_exact_prediction(prediction)
    resolve_main_canonical_core()

    if router_decision is None:
        return _set_no_recommendation(prediction, reasons=(NO_ROUTER_REASON,))

    decision = _verify_router_decision(router_decision)
    if decision.decision_status is _canonical_router.RouterDecisionStatus.NO_BET:
        return _set_no_recommendation(
            prediction,
            reasons=tuple(decision.decision_reasons),
        )
    if decision.decision_status is not _canonical_router.RouterDecisionStatus.SELECTED:
        raise MainCanonicalPredictionAdapterError(
            "canonical RouterDecision has an unsupported decision status"
        )

    selected = decision.selected_opportunity
    if selected is None:
        raise MainCanonicalPredictionAdapterError(
            "selected canonical RouterDecision has no selected opportunity"
        )
    confidence = selected.prediction_confidence
    if confidence is None or not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise MainCanonicalPredictionAdapterError(
            "selected canonical opportunity lacks a bounded prediction confidence"
        )
    try:
        selection = _markets.make_selection(
            selected.market_id,
            selected.outcome_id,
            line=selected.line,
        )
    except Exception as exc:
        raise MainCanonicalPredictionAdapterError(
            "canonical Router selection could not be projected to presentation"
        ) from exc

    presentation_confidence = round(confidence * 100.0, 1)
    prediction.recommended_market = selection.display_label
    prediction.market_confidence = presentation_confidence
    prediction.ranked_markets = [(selection.display_label, presentation_confidence)]
    return prediction


__all__ = [
    "AUTHORITY",
    "EXPECTED_ROUTER_ARTIFACT_GIT_BLOB_SHA",
    "EXPECTED_ROUTER_COMPONENT_ID",
    "EXPECTED_ROUTER_CONTRACT_SHA256",
    "MAIN_AUTHORITY_MANIFEST",
    "MainCanonicalPredictionAdapterError",
    "NO_RECOMMENDATION",
    "NO_ROUTER_REASON",
    "POLICY_ID",
    "REGIME_ID",
    "clear_main_canonical_core_cache",
    "project_canonical_router_decision",
    "resolve_main_canonical_core",
]
