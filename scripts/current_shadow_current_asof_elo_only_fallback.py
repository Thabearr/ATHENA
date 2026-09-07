"""Worker-local Current Shadow fallback from incomplete full xG to reviewed Elo-only xG.

The base current-source binding remains unchanged. This hook is installed only by
the user-facing Current Shadow request wrapper. It first executes the existing
binding unchanged; when the base binding reports missing required inputs, the
wrapper may replay the separate current-as-of assessment for exact reviewed
Current Shadow row dispositions that can legitimately need that replay.

The frozen PR149 seal-window disposition is not runtime model-readiness authority.
Both OUTSIDE_REVIEWED_SEAL_WINDOW and MISSING_REVIEWED_FEATURES rows must pass the
same current-as-of assessment. Elo-only recovery is then allowed only when that
assessment proves the full five-feature model is incomplete solely because the
reviewed form/fatigue features are missing while both reviewed overall Elo inputs
remain available.

No missing value is imputed and no historical feature scope is broadened.
The worker also retains bounded, non-authoritative per-fixture diagnostics so a
live Current Shadow receipt can distinguish missing-Elo, missing-form/fatigue,
and other fail-closed model-readiness states without changing model behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable

from domain import _all_market_shadow_current_binding as binding
from domain import current_fotmob_utc_native_current_asof_elo_only as elo_only
from domain import current_fotmob_utc_native_current_asof_xg as current_asof
from domain import current_fotmob_utc_native_shadow_prediction as current_shadow
from domain._all_market_shadow_types import ResearchXGRates, ShadowDisposition


POLICY_ID = "ATHENA_CURRENT_SHADOW_CURRENT_AS_OF_ELO_ONLY_FALLBACK_V2"
DIAGNOSTIC_SCHEMA_VERSION = 2
DIAGNOSTIC_DATASET_NAME = "athena-current-shadow-current-asof-xg-diagnostic-v2"
_FALLBACK_ROW_DISPOSITIONS = frozenset(
    {
        current_shadow.MISSING_REVIEWED_FEATURES,
        current_shadow.OUTSIDE_REVIEWED_SEAL_WINDOW,
    }
)

_DIAGNOSTIC_AUTHORITY = MappingProxyType(
    {
        "research_shadow_diagnostic": True,
        "production_model": False,
        "production_probability": False,
        "pricing": False,
        "selection": False,
        "sportybet_execution": False,
        "bet": False,
        "wager_placed": False,
    }
)
_DIAGNOSTIC_ROWS: dict[str, dict[str, Any]] = {}


@dataclass(frozen=True)
class FallbackHooks:
    original_research_xg: Any


def _enum_text(value: Any) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw)


def _missing_ids(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list, set, frozenset)):
        return ()
    return tuple(sorted({item for item in value if type(item) is str and item}))


def _record(
    fixture_identity: str,
    *,
    state: str,
    history_sha: str,
    blocker: Any,
    missing: Any,
    row_disposition: Any = None,
    full: Any = None,
    error_code: str | None = None,
    error_type: str | None = None,
) -> None:
    if type(fixture_identity) is not str or not fixture_identity:
        return
    row: dict[str, Any] = {
        "fixture_identity": fixture_identity,
        "state": state,
        "history_sha256": history_sha,
        "base_blocker": _enum_text(blocker),
        "base_missing_feature_ids": list(_missing_ids(missing)),
        "row_disposition": _enum_text(row_disposition),
        "full_assessment_disposition": None,
        "full_missing_feature_ids": [],
        "full_available_feature_ids": [],
        "error_code": error_code,
        "error_type": error_type,
        "fallback_applied": state == "ELO_ONLY_APPLIED",
        "wager_placed": False,
    }
    if full is not None:
        row["full_assessment_disposition"] = _enum_text(
            getattr(full, "disposition", None)
        )
        row["full_missing_feature_ids"] = list(
            _missing_ids(getattr(full, "missing_feature_ids", ()))
        )
        features = getattr(full, "features", {})
        if hasattr(features, "keys"):
            row["full_available_feature_ids"] = sorted(
                key for key in features.keys() if type(key) is str
            )
    _DIAGNOSTIC_ROWS[fixture_identity] = row


def _current_asof_error_code(exc: BaseException) -> str:
    if str(exc) == "reviewed Elo unexpectedly became missing":
        return "REVIEWED_ELO_UNAVAILABLE"
    return "CURRENT_ASOF_REVIEWED_ASSESSMENT_REJECTED"


def _elo_only_error_code(exc: BaseException) -> str:
    if str(exc) == "reviewed overall Elo inputs are unavailable":
        return "REVIEWED_ELO_UNAVAILABLE"
    return "ELO_ONLY_REVIEWED_ASSESSMENT_REJECTED"


def _with_fallback(
    original: Callable[..., Any],
    history: Any,
    fixture_identity: str,
    *,
    history_sha: str,
):
    result = original(history, fixture_identity, history_sha=history_sha)
    rates, blocker, missing, kickoff = result
    if rates is not None:
        _record(
            fixture_identity,
            state="BASE_MODEL_READY",
            history_sha=history_sha,
            blocker=blocker,
            missing=missing,
        )
        return result
    if blocker is not ShadowDisposition.MISSING_REQUIRED_INPUT:
        _record(
            fixture_identity,
            state="BASE_BLOCKER_NOT_FALLBACK_ELIGIBLE",
            history_sha=history_sha,
            blocker=blocker,
            missing=missing,
        )
        return result

    rows = [
        row
        for row in history.shadow_handoff.rows
        if row.fixture_identifier == fixture_identity
    ]
    if len(rows) != 1:
        _record(
            fixture_identity,
            state="CURRENT_HISTORY_ROW_NOT_UNIQUE",
            history_sha=history_sha,
            blocker=blocker,
            missing=missing,
        )
        return result
    row = rows[0]
    if row.disposition not in _FALLBACK_ROW_DISPOSITIONS:
        _record(
            fixture_identity,
            state="ROW_DISPOSITION_NOT_FALLBACK_ELIGIBLE",
            history_sha=history_sha,
            blocker=blocker,
            missing=missing,
            row_disposition=row.disposition,
        )
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
    except current_asof.CurrentAsOfXGError as exc:
        _record(
            fixture_identity,
            state="CURRENT_ASOF_ASSESSMENT_ERROR",
            history_sha=history_sha,
            blocker=blocker,
            missing=missing,
            row_disposition=row.disposition,
            error_code=_current_asof_error_code(exc),
            error_type=type(exc).__name__,
        )
        return result
    except Exception as exc:
        _record(
            fixture_identity,
            state="CURRENT_ASOF_INPUT_REPLAY_ERROR",
            history_sha=history_sha,
            blocker=blocker,
            missing=missing,
            row_disposition=row.disposition,
            error_code="CURRENT_ASOF_INPUT_REPLAY_FAILED",
            error_type=type(exc).__name__,
        )
        return result
    if (
        full.disposition
        is not current_asof.CurrentAsOfXGDisposition.MISSING_REVIEWED_FEATURES
    ):
        _record(
            fixture_identity,
            state="FULL_CURRENT_ASOF_NOT_FALLBACK_ELIGIBLE",
            history_sha=history_sha,
            blocker=blocker,
            missing=missing,
            row_disposition=row.disposition,
            full=full,
        )
        return result

    try:
        reduced = elo_only.build_current_asof_elo_only_xg_assessment(full)
    except elo_only.CurrentAsOfEloOnlyXGError as exc:
        _record(
            fixture_identity,
            state="ELO_ONLY_ASSESSMENT_ERROR",
            history_sha=history_sha,
            blocker=blocker,
            missing=missing,
            row_disposition=row.disposition,
            full=full,
            error_code=_elo_only_error_code(exc),
            error_type=type(exc).__name__,
        )
        return result
    except Exception as exc:
        _record(
            fixture_identity,
            state="ELO_ONLY_INPUT_REPLAY_ERROR",
            history_sha=history_sha,
            blocker=blocker,
            missing=missing,
            row_disposition=row.disposition,
            full=full,
            error_code="ELO_ONLY_INPUT_REPLAY_FAILED",
            error_type=type(exc).__name__,
        )
        return result

    _record(
        fixture_identity,
        state="ELO_ONLY_APPLIED",
        history_sha=history_sha,
        blocker=blocker,
        missing=missing,
        row_disposition=row.disposition,
        full=full,
    )
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
    _DIAGNOSTIC_ROWS.clear()

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


def diagnostic_summary() -> dict[str, Any]:
    rows = [dict(_DIAGNOSTIC_ROWS[key]) for key in sorted(_DIAGNOSTIC_ROWS)]
    state_counts: dict[str, int] = {}
    for row in rows:
        state = row["state"]
        state_counts[state] = state_counts.get(state, 0) + 1
    return {
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "dataset_name": DIAGNOSTIC_DATASET_NAME,
        "fallback_policy_id": POLICY_ID,
        "fixture_count": len(rows),
        "state_counts": {key: state_counts[key] for key in sorted(state_counts)},
        "fixtures": rows,
        "authority": dict(_DIAGNOSTIC_AUTHORITY),
        "wager_placed": False,
    }


def policy_summary() -> dict[str, Any]:
    payload = elo_only.policy_summary()
    return {
        "policy_id": POLICY_ID,
        "fallback": payload,
        "base_binding_runs_first": True,
        "fallback_row_dispositions": sorted(_FALLBACK_ROW_DISPOSITIONS),
        "current_asof_assessment_required": True,
        "seal_window_is_not_runtime_model_readiness_authority": True,
        "diagnostic_dataset_name": DIAGNOSTIC_DATASET_NAME,
        "diagnostic_non_authoritative": True,
        "wager_placed": False,
    }


__all__ = [
    "DIAGNOSTIC_DATASET_NAME",
    "FallbackHooks",
    "POLICY_ID",
    "diagnostic_summary",
    "install",
    "policy_summary",
    "restore",
]
