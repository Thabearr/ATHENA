"""Current-source binding helpers for PR C all-market Shadow surface.

Two layers are intentionally separated:

* ``scan_fixture_all_markets`` is a deterministic mathematical composition helper.
  It accepts already-reviewed research xG rates and never claims that those inputs
  are the complete current source state.
* ``scan_current_fixture_all_markets`` is the current source-bound entrypoint.  It
  revalidates the exact complete PR151 durable-history handoff, derives xG only
  from one sealed current shadow row, revalidates the typed PR-B SportyBet
  semantic registry, and derives exact current line families from its observations.

Both layers remain research/shadow only.  Production, pricing, selection, staking,
SportyBet execution, and BET authority remain false.
"""
from __future__ import annotations

import dataclasses
import hashlib
import math
from types import MappingProxyType
from typing import Mapping, Optional, Sequence

from domain import current_fotmob_latest_durable_fresh_history as latest_history
from domain import current_fotmob_utc_native_shadow_prediction as current_shadow
from domain import fotmob_utc_native_expected_goals_fresh_holdout as fresh_xg
from domain.current_sportybet_semantic_registry import (
    CurrentSportyBetSemanticRegistry,
    EvidenceFreshnessState,
    ProviderCoverageRecord,
    ProviderSemanticStatus,
)
from domain.early_payout_lead_path_probabilities import project_early_payout_market
from domain.markets import MARKET_REGISTRY, MarketId
from domain.score_matrix import build_score_matrix
from domain.score_matrix_market_probabilities import (
    AnalyticalProjectionError,
    ScoreMatrixMarketProjection,
    project_score_matrix_market,
)
from domain.win_either_half_features import PRE_MATCH_FEATURE_NAMES
from domain.win_either_half_inference import (
    WinEitherHalfInferenceError,
    predict_win_either_half,
)
from domain._all_market_shadow_types import (
    DEFAULT_AH_HOME_LINES,
    DEFAULT_TOTAL_GOALS_LINE,
    DATASET_NAME,
    SCHEMA_VERSION,
    AllMarketShadowError,
    CurrentAllMarketShadowFixtureScan,
    CurrentAllMarketShadowScan,
    ResearchXGRates,
    ShadowDisposition,
    ShadowMarketAssessment,
    _authority_map,
    _canonical_json_bytes,
)
from domain._all_market_shadow_helpers import (
    _blocked_assessment,
    _from_early_payout,
    _from_score_matrix_projection,
    _from_weh,
    _provider_status,
)

# Provider axis is bound to the typed PR-B enum. Never hand-maintain alternate
# spellings of the unavailable/unproven status — the real value is
# ProviderSemanticStatus.CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN.value
# ("CURRENT_PROVIDER_UNAVAILABLE/UNPROVEN").
_SUPPORTED_PROVIDER_STATUSES = frozenset(
    {
        ProviderSemanticStatus.SUPPORTED,
        ProviderSemanticStatus.SUPPORTED_WITH_EXACT_LINE_POLICY,
    }
)
_PROVIDER_BLOCKED_STATUSES = frozenset(
    {
        ProviderSemanticStatus.CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN,
    }
)
_PROVIDER_BLOCKED_VALUES = frozenset(
    status.value for status in _PROVIDER_BLOCKED_STATUSES
)
_RATE_KEYS = frozenset(
    {
        "native_home",
        "native_away",
        "elo_only_home",
        "elo_only_away",
        "calibrated_home",
        "calibrated_away",
    }
)


def _provider_blocked(value: object) -> bool:
    """Return True when an explicit provider status must keep the provider axis blocked.

    ``None`` means the caller did not supply a provider overlay for this market
    (mathematical helper with no registry). That is not a grant of support and
    not an explicit block — disposition stays ANALYTICAL_READY on the math axis.

    Supported enum values / their exact ``.value`` strings grant provider readiness.
    The explicit PR-B unavailable/unproven status blocks. Any other explicit
    value (unknown string, forged token, wrong spelling) fails closed.
    """

    if value is None:
        return False
    if isinstance(value, ProviderSemanticStatus):
        return value not in _SUPPORTED_PROVIDER_STATUSES
    if type(value) is not str:
        return True
    if value in {status.value for status in _SUPPORTED_PROVIDER_STATUSES}:
        return False
    # Explicit unproven/unavailable and every unknown/forged token stay blocked.
    return True


def _finite_line_tuple(values: Sequence[float], label: str) -> tuple[float, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise AllMarketShadowError(f"{label} must be a numeric sequence")
    result: list[float] = []
    for item in values:
        if (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
        ):
            raise AllMarketShadowError(f"{label} contains non-finite numeric line")
        value = float(item)
        value = 0.0 if value == 0.0 else value
        if value not in result:
            result.append(value)
    return tuple(result)


def _combine_line_projections(
    projections: Sequence[ScoreMatrixMarketProjection],
    *,
    disposition: ShadowDisposition,
    score_matrix_audit: Mapping[str, object],
    provider_semantic_status: Optional[str],
) -> ShadowMarketAssessment:
    """Flatten exact line projections into one canonical MarketId row.

    ``AnalyticalEventProbability.line`` preserves each Total-Goals line.  Asian
    Handicap settlement objects preserve HOME line and opposite AWAY line, so PR D
    can group every exact line without inventing a second canonical MarketId.
    """

    rows = tuple(projections)
    if not rows:
        raise AllMarketShadowError("at least one exact line projection is required")
    first = _from_score_matrix_projection(
        rows[0],
        disposition=disposition,
        score_matrix_audit=score_matrix_audit,
        provider_semantic_status=provider_semantic_status,
    )
    if any(item.market_id is not first.market_id for item in rows):
        raise AllMarketShadowError("line projections escaped one canonical market")
    return ShadowMarketAssessment(
        market_id=first.market_id,
        market_family=first.market_family,
        disposition=first.disposition,
        probability_method=first.probability_method,
        probability_input_namespace=first.probability_input_namespace,
        analytical_capability=first.analytical_capability,
        settlement_capability=first.settlement_capability,
        event_probabilities=tuple(
            event for projection in rows for event in projection.event_probabilities
        ),
        settlement_distributions=tuple(
            settlement
            for projection in rows
            for settlement in projection.settlement_distributions
        ),
        required_inputs=first.required_inputs,
        missing_inputs=(),
        blocker_reason=None,
        provider_semantic_status=provider_semantic_status,
        pricing_authority=first.pricing_authority,
        selection_authority=first.selection_authority,
        score_matrix_audit=first.score_matrix_audit,
    )


def _verified_provider_registry(
    value: Optional[CurrentSportyBetSemanticRegistry],
) -> Optional[CurrentSportyBetSemanticRegistry]:
    if value is None:
        return None
    if type(value) is not CurrentSportyBetSemanticRegistry:
        raise AllMarketShadowError(
            "provider_semantic_registry must be exact CurrentSportyBetSemanticRegistry"
        )
    try:
        checked = dataclasses.replace(value)
        # Canonical serialization re-runs the registry's exact contract validation.
        _ = checked.canonical_bytes
    except Exception as exc:
        raise AllMarketShadowError(
            "current SportyBet semantic registry failed exact revalidation"
        ) from exc
    if any(checked.authority.values()):
        raise AllMarketShadowError(
            "provider semantic registry unexpectedly acquired downstream authority"
        )
    return checked


def _coverage_by_market(
    registry: CurrentSportyBetSemanticRegistry,
) -> dict[MarketId, ProviderCoverageRecord]:
    rows = {item.market_id: item for item in registry.coverage}
    if set(rows) != set(MarketId):
        raise AllMarketShadowError("provider semantic registry coverage is incomplete")
    return rows


def _current_complete_provider_lines(
    coverage: ProviderCoverageRecord,
) -> tuple[float, ...]:
    """Return only complete, current, bookable, analytically eligible exact lines."""

    if coverage.market_id not in {MarketId.TOTAL_GOALS, MarketId.ASIAN_HANDICAP}:
        raise AllMarketShadowError("current line extraction is only valid for line markets")
    if coverage.provider_status not in _SUPPORTED_PROVIDER_STATUSES:
        return ()
    groups: dict[
        tuple[str, str, Optional[str], str],
        list[object],
    ] = {}
    for observation in coverage.observations:
        if (
            observation.bookable is not True
            or observation.evidence_freshness is not EvidenceFreshnessState.CURRENT
            or observation.line_analytically_eligible is not True
            or observation.line is None
        ):
            continue
        key = (
            observation.provider_event_id,
            observation.provider_market_id,
            observation.provider_specifier,
            observation.line,
        )
        groups.setdefault(key, []).append(observation)

    expected_outcomes = set(MARKET_REGISTRY[coverage.market_id].supported_outcomes)
    lines: list[float] = []
    for group in groups.values():
        if {item.canonical_outcome_id for item in group} != expected_outcomes:
            continue
        raw_line = group[0].line
        if raw_line is None:
            continue
        try:
            line = float(raw_line)
        except (TypeError, ValueError, OverflowError) as exc:
            raise AllMarketShadowError("reviewed provider line is not numeric") from exc
        if not math.isfinite(line):
            raise AllMarketShadowError("reviewed provider line is non-finite")
        line = 0.0 if line == 0.0 else line
        if line not in lines:
            lines.append(line)
    return tuple(sorted(lines))


def _provider_inputs(
    registry: Optional[CurrentSportyBetSemanticRegistry],
) -> tuple[Mapping[MarketId, str], tuple[float, ...], tuple[float, ...]]:
    """Project the typed PR-B registry into the narrow PR-C semantic axis."""

    if registry is None:
        status = ProviderSemanticStatus.CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN.value
        return (
            MappingProxyType({market_id: status for market_id in MarketId}),
            (),
            (),
        )
    rows = _coverage_by_market(registry)
    statuses = MappingProxyType(
        {market_id: rows[market_id].provider_status.value for market_id in MarketId}
    )
    return (
        statuses,
        _current_complete_provider_lines(rows[MarketId.TOTAL_GOALS]),
        _current_complete_provider_lines(rows[MarketId.ASIAN_HANDICAP]),
    )


def _research_xg_from_validated_current_history(
    history: latest_history.CurrentLatestDurableFreshHistoryHandoff,
    fixture_identity: str,
    *,
    history_sha: str,
) -> tuple[
    Optional[ResearchXGRates],
    Optional[ShadowDisposition],
    tuple[str, ...],
    str,
]:
    """Extract one exact sealed xG pair from an already validated PR151 handoff.

    This helper is private so public current-source callers cannot bypass the
    reviewed replay boundary. PR-F may reuse it only for an exact history object
    issued by the reviewed history builder in the same worker process.
    """

    if type(history) is not latest_history.CurrentLatestDurableFreshHistoryHandoff:
        raise AllMarketShadowError(
            "validated current history must be exact CurrentLatestDurableFreshHistoryHandoff"
        )
    if (
        type(history_sha) is not str
        or len(history_sha) != 64
        or any(character not in "0123456789abcdef" for character in history_sha)
    ):
        raise AllMarketShadowError("validated current history SHA identity is invalid")
    if (
        history.latest_applicable_success_selection_proven is not True
        or history.current_fresh_history_prefix_complete is not True
    ):
        raise AllMarketShadowError("current fresh-history completeness is not proven")
    if any(history.authority.values()):
        raise AllMarketShadowError(
            "complete current history unexpectedly acquired downstream authority"
        )

    rows = [
        row
        for row in history.shadow_handoff.rows
        if row.fixture_identifier == fixture_identity
    ]
    if len(rows) != 1:
        raise AllMarketShadowError(
            "complete current shadow replay does not contain exactly one fixture row"
        )
    row = rows[0]
    kickoff = row.kickoff_utc.isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )

    if row.disposition == current_shadow.MISSING_REVIEWED_FEATURES:
        return (
            None,
            ShadowDisposition.MISSING_REQUIRED_INPUT,
            tuple(row.missing_feature_ids),
            kickoff,
        )
    if row.disposition == current_shadow.OUTSIDE_REVIEWED_SEAL_WINDOW:
        return None, ShadowDisposition.OUTSIDE_REVIEWED_XG_WINDOW, (), kickoff
    if (
        row.disposition != current_shadow.SEALED_COMPLETE_CASE
        or row.sealed_prediction is None
        or row.sealed_prediction_sha256 is None
    ):
        raise AllMarketShadowError("current shadow row escaped reviewed disposition contract")

    prediction = dataclasses.replace(row.sealed_prediction)
    sealed_sha = fresh_xg.sha256_sealed_fresh_prediction(prediction)
    if sealed_sha != row.sealed_prediction_sha256:
        raise AllMarketShadowError("sealed current xG prediction identity changed")
    rates = dict(prediction.rates)
    if set(rates) != _RATE_KEYS:
        raise AllMarketShadowError("sealed current xG rate vocabulary drifted")
    home = rates["calibrated_home"]
    away = rates["calibrated_away"]
    if (
        isinstance(home, bool)
        or isinstance(away, bool)
        or not isinstance(home, (int, float))
        or not isinstance(away, (int, float))
        or not math.isfinite(float(home))
        or not math.isfinite(float(away))
        or float(home) < 0.0
        or float(away) < 0.0
    ):
        raise AllMarketShadowError("sealed calibrated xG rates are invalid")
    return (
        ResearchXGRates(
            calibrated_home=float(home),
            calibrated_away=float(away),
            sealed_prediction_sha256=sealed_sha,
            history_prefix_identity=history_sha,
            source_fixture_identity=fixture_identity,
            completeness_status="SEALED_COMPLETE_CURRENT_HISTORY",
        ),
        None,
        (),
        kickoff,
    )


def _research_xg_from_complete_current_history(
    complete_current_history: latest_history.CurrentLatestDurableFreshHistoryHandoff,
    fixture_identity: str,
) -> tuple[
    Optional[ResearchXGRates],
    Optional[ShadowDisposition],
    tuple[str, ...],
    str,
]:
    """Replay complete current history and extract one exact current sealed xG pair."""

    if type(complete_current_history) is not latest_history.CurrentLatestDurableFreshHistoryHandoff:
        raise AllMarketShadowError(
            "complete_current_history must be exact CurrentLatestDurableFreshHistoryHandoff"
        )
    try:
        history = dataclasses.replace(complete_current_history)
        canonical = latest_history._canonical(history.to_dict())
    except Exception as exc:
        raise AllMarketShadowError(
            "complete current PR151 history failed exact replay"
        ) from exc
    history_sha = hashlib.sha256(canonical).hexdigest()
    return _research_xg_from_validated_current_history(
        history,
        fixture_identity,
        history_sha=history_sha,
    )
