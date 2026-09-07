"""Worker-local Current Shadow fallback from incomplete full xG to reviewed Elo-only xG.

The base current-source binding remains unchanged.  This hook is installed only by
the user-facing Current Shadow request wrapper.  It first executes the existing
binding unchanged; only an OUTSIDE_REVIEWED_SEAL_WINDOW current-as-of fixture
whose full five-feature assessment is missing reviewed form/fatigue may use the
separate reviewed Elo-only research boundary.

No missing value is imputed and no historical feature scope is broadened.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from domain import _all_market_shadow_current_binding as binding
from domain import current_fotmob_utc_native_current_asof_elo_only as elo_only
from domain import current_fotmob_utc_native_current_asof_xg as current_asof
from domain import current_fotmob_utc_native_shadow_prediction as current_shadow
from domain._all_market_shadow_types import ResearchXGRates, ShadowDisposition


POLICY_ID = "ATHENA_CURRENT_SHADOW_CURRENT_AS_OF_ELO_ONLY_FALLBACK_V1"


@dataclass(frozen=True)
class FallbackHooks:
    original_research_xg: Any


def _with_fallback(
    original: Callable[..., Any],
    history: Any,
    fixture_identity: str,
    *,
    history_sha: str,
):
    result = original(history, fixture_identity, history_sha=history_sha)
    rates, blocker, missing, kickoff = result
    if rates is not None or blocker is not ShadowDisposition.MISSING_REQUIRED_INPUT:
        return result

    rows = [
        row
        for row in history.shadow_handoff.rows
        if row.fixture_identifier == fixture_identity
    ]
    if len(rows) != 1:
        return result
    row = rows[0]
    if row.disposition != current_shadow.OUTSIDE_REVIEWED_SEAL_WINDOW:
        return result

    try:
        ledger, _update_count = current_shadow._history_ledger(
            history.shadow_handoff.source_bundle
        )
        full = current_asof.build_current_asof_xg_assessment(
            history_ledger=ledger,
            selected_capture=row.fixture,
            fixture_review_policy_id=history.shadow_handoff.fixture_review_policy_id,
        )
    except Exception:
        return result
    if (
        full.disposition
        is not current_asof.CurrentAsOfXGDisposition.MISSING_REVIEWED_FEATURES
    ):
        return result

    reduced = elo_only.build_current_asof_elo_only_xg_assessment(full)
    reduced_rates = dict(reduced.rates)
    return (
        ResearchXGRates(
            calibrated_home=float(reduced_rates["elo_only_home"]),
            calibrated_away=float(reduced_rates["elo_only_away"]),
            feature_projection_identity=reduced.feature_projection_sha256,
            history_prefix_identity=reduced.history_prefix_sha256,
            source_fixture_identity=fixture_identity,
            completeness_status=elo_only.COMPLETE,
        ),
        None,
        (),
        kickoff,
    )


def install() -> FallbackHooks:
    original = binding._research_xg_from_validated_current_history

    def wrapped(history: Any, fixture_identity: str, *, history_sha: str):
        return _with_fallback(
            original,
            history,
            fixture_identity,
            history_sha=history_sha,
        )

    binding._research_xg_from_validated_current_history = wrapped
    return FallbackHooks(original_research_xg=original)


def restore(hooks: FallbackHooks) -> None:
    if type(hooks) is not FallbackHooks:
        raise ValueError("hooks must be exact FallbackHooks")
    binding._research_xg_from_validated_current_history = hooks.original_research_xg


def policy_summary() -> dict[str, Any]:
    payload = elo_only.policy_summary()
    return {
        "policy_id": POLICY_ID,
        "fallback": payload,
        "base_binding_runs_first": True,
        "only_outside_seal_window_missing_full_model": True,
        "wager_placed": False,
    }


__all__ = [
    "FallbackHooks",
    "POLICY_ID",
    "install",
    "policy_summary",
    "restore",
]
