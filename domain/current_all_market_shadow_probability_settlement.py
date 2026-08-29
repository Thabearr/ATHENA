"""Research-only all-market Shadow probability and settlement surface (PR C).

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


_PROVIDER_BLOCKED_VALUES = frozenset(
    {
        "CURRENT_PROVIDER_UNAVAILABLE",
        "CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN",
        "CURRENT_PROVIDER_UNPROVEN",
        "PROVIDER_UNPROVEN",
    }
)
_SUPPORTED_PROVIDER_STATUSES = frozenset(
    {
        ProviderSemanticStatus.SUPPORTED,
        ProviderSemanticStatus.SUPPORTED_WITH_EXACT_LINE_POLICY,
    }
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


def _provider_blocked(value: Optional[str]) -> bool:
    return value in _PROVIDER_BLOCKED_VALUES


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
        latest_history.canonical_current_fotmob_latest_durable_fresh_history_handoff_bytes(
            history
        )
    except Exception as exc:
        raise AllMarketShadowError(
            "complete current PR151 history failed exact replay"
        ) from exc
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
    history_sha = latest_history.sha256_current_fotmob_latest_durable_fresh_history_handoff(
        history
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


def scan_fixture_all_markets(
    *,
    fixture_identity: str,
    research_xg: Optional[ResearchXGRates],
    kickoff_utc_iso: Optional[str] = None,
    weh_feature_row: Optional[Mapping[str, object]] = None,
    total_goals_line: float = DEFAULT_TOTAL_GOALS_LINE,
    total_goals_lines: Optional[Sequence[float]] = None,
    asian_handicap_home_lines: Sequence[float] = DEFAULT_AH_HOME_LINES,
    provider_semantic_by_market: Optional[Mapping[MarketId, str]] = None,
) -> CurrentAllMarketShadowFixtureScan:
    """Compose one deterministic 15-market mathematical Shadow surface.

    This lower-level helper does not claim that caller-supplied ``research_xg`` or
    provider-status strings are current source evidence.  Use
    :func:`scan_current_fixture_all_markets` for the current source-bound lane.
    """

    if type(fixture_identity) is not str or not fixture_identity.strip():
        raise AllMarketShadowError("fixture_identity must be non-empty")

    assessments: dict[MarketId, ShadowMarketAssessment] = {}
    matrix_audit = None

    if research_xg is None:
        for market_id in MarketId:
            if market_id in {
                MarketId.HOME_WIN_EITHER_HALF,
                MarketId.AWAY_WIN_EITHER_HALF,
            }:
                continue
            assessments[market_id] = _blocked_assessment(
                market_id,
                ShadowDisposition.NO_REVIEWED_XG,
                missing_inputs=("calibrated_home", "calibrated_away"),
                blocker_reason="No reviewed research/shadow xG rates supplied",
                provider_semantic_status=_provider_status(
                    provider_semantic_by_market, market_id
                ),
            )
    else:
        score_matrix = build_score_matrix(
            research_xg.calibrated_home,
            research_xg.calibrated_away,
        )
        matrix_audit = score_matrix.audit_dict()

        for market_id in (
            MarketId.MATCH_RESULT,
            MarketId.DRAW_OR_OVER_2_5,
            MarketId.AWAY_OR_OVER_2_5,
            MarketId.HOME_OR_OVER_2_5,
            MarketId.DOUBLE_CHANCE,
            MarketId.BTTS,
            MarketId.DRAW_NO_BET,
            MarketId.HOME_WIN_TO_NIL,
            MarketId.AWAY_WIN_TO_NIL,
        ):
            projection = project_score_matrix_market(score_matrix, market_id)
            provider = _provider_status(provider_semantic_by_market, market_id)
            disposition = (
                ShadowDisposition.ANALYTICAL_READY_PROVIDER_BLOCKED
                if _provider_blocked(provider)
                else ShadowDisposition.ANALYTICAL_READY
            )
            assessments[market_id] = _from_score_matrix_projection(
                projection,
                disposition=disposition,
                score_matrix_audit=matrix_audit,
                provider_semantic_status=provider,
            )

        tg_values = (
            _finite_line_tuple(total_goals_lines, "total_goals_lines")
            if total_goals_lines is not None
            else _finite_line_tuple((total_goals_line,), "total_goals_lines")
        )
        tg_provider = _provider_status(provider_semantic_by_market, MarketId.TOTAL_GOALS)
        if not tg_values:
            assessments[MarketId.TOTAL_GOALS] = _blocked_assessment(
                MarketId.TOTAL_GOALS,
                (
                    ShadowDisposition.PROVIDER_UNPROVEN
                    if _provider_blocked(tg_provider)
                    else ShadowDisposition.UNSUPPORTED_EXACT_LINE
                ),
                blocker_reason=(
                    "No current complete analytically eligible Total Goals line"
                    if _provider_blocked(tg_provider)
                    else "No Total Goals line supplied"
                ),
                provider_semantic_status=tg_provider,
            )
        else:
            try:
                tg_projections = tuple(
                    project_score_matrix_market(
                        score_matrix, MarketId.TOTAL_GOALS, line=line
                    )
                    for line in tg_values
                )
            except AnalyticalProjectionError as exc:
                assessments[MarketId.TOTAL_GOALS] = _blocked_assessment(
                    MarketId.TOTAL_GOALS,
                    ShadowDisposition.UNSUPPORTED_EXACT_LINE,
                    blocker_reason=str(exc),
                    provider_semantic_status=tg_provider,
                )
            else:
                assessments[MarketId.TOTAL_GOALS] = _combine_line_projections(
                    tg_projections,
                    disposition=(
                        ShadowDisposition.ANALYTICAL_READY_PROVIDER_BLOCKED
                        if _provider_blocked(tg_provider)
                        else ShadowDisposition.ANALYTICAL_READY
                    ),
                    score_matrix_audit=matrix_audit,
                    provider_semantic_status=tg_provider,
                )

        ah_values = _finite_line_tuple(
            asian_handicap_home_lines, "asian_handicap_home_lines"
        )
        ah_provider = _provider_status(
            provider_semantic_by_market, MarketId.ASIAN_HANDICAP
        )
        if not ah_values:
            assessments[MarketId.ASIAN_HANDICAP] = _blocked_assessment(
                MarketId.ASIAN_HANDICAP,
                (
                    ShadowDisposition.PROVIDER_UNPROVEN
                    if _provider_blocked(ah_provider)
                    else ShadowDisposition.UNSUPPORTED_EXACT_LINE
                ),
                blocker_reason=(
                    "No current complete analytically eligible Asian Handicap line"
                    if _provider_blocked(ah_provider)
                    else "No Asian Handicap home lines supplied"
                ),
                provider_semantic_status=ah_provider,
            )
        else:
            try:
                ah_projections = tuple(
                    project_score_matrix_market(
                        score_matrix, MarketId.ASIAN_HANDICAP, line=line
                    )
                    for line in ah_values
                )
            except AnalyticalProjectionError as exc:
                assessments[MarketId.ASIAN_HANDICAP] = _blocked_assessment(
                    MarketId.ASIAN_HANDICAP,
                    ShadowDisposition.UNSUPPORTED_EXACT_LINE,
                    blocker_reason=str(exc),
                    provider_semantic_status=ah_provider,
                )
            else:
                assessments[MarketId.ASIAN_HANDICAP] = _combine_line_projections(
                    ah_projections,
                    disposition=(
                        ShadowDisposition.ANALYTICAL_READY_PROVIDER_BLOCKED
                        if _provider_blocked(ah_provider)
                        else ShadowDisposition.ANALYTICAL_READY
                    ),
                    score_matrix_audit=matrix_audit,
                    provider_semantic_status=ah_provider,
                )

        for market_id in (MarketId.MATCH_RESULT_1UP, MarketId.MATCH_RESULT_2UP):
            early = project_early_payout_market(score_matrix, market_id)
            provider = _provider_status(provider_semantic_by_market, market_id)
            assessments[market_id] = _from_early_payout(
                early,
                disposition=(
                    ShadowDisposition.ANALYTICAL_READY_PROVIDER_BLOCKED
                    if _provider_blocked(provider)
                    else ShadowDisposition.ANALYTICAL_READY
                ),
                score_matrix_audit=matrix_audit,
                provider_semantic_status=provider,
            )

    for market_id in (MarketId.HOME_WIN_EITHER_HALF, MarketId.AWAY_WIN_EITHER_HALF):
        provider = _provider_status(provider_semantic_by_market, market_id)
        if weh_feature_row is None:
            assessments[market_id] = _blocked_assessment(
                market_id,
                ShadowDisposition.SPECIALIST_FEATURES_MISSING,
                missing_inputs=PRE_MATCH_FEATURE_NAMES,
                blocker_reason="Specialized WEH 74-feature vector not supplied",
                provider_semantic_status=provider,
            )
            continue
        try:
            supplied = set(weh_feature_row)
            expected = set(PRE_MATCH_FEATURE_NAMES)
            if supplied != expected:
                missing = tuple(sorted(expected - supplied))
                assessments[market_id] = _blocked_assessment(
                    market_id,
                    ShadowDisposition.SPECIALIST_FEATURES_MISSING,
                    missing_inputs=missing,
                    blocker_reason=f"WEH feature namespace incomplete: missing={missing}",
                    provider_semantic_status=provider,
                )
                continue
            prediction = predict_win_either_half(weh_feature_row)
            assessments[market_id] = _from_weh(
                prediction,
                market_id,
                disposition=(
                    ShadowDisposition.ANALYTICAL_READY_PROVIDER_BLOCKED
                    if _provider_blocked(provider)
                    else ShadowDisposition.ANALYTICAL_READY
                ),
                provider_semantic_status=provider,
            )
        except WinEitherHalfInferenceError as exc:
            assessments[market_id] = _blocked_assessment(
                market_id,
                ShadowDisposition.SPECIALIST_FEATURES_MISSING,
                missing_inputs=(),
                blocker_reason=str(exc),
                provider_semantic_status=provider,
            )

    ordered = tuple(assessments[market_id] for market_id in MarketId)
    return CurrentAllMarketShadowFixtureScan(
        fixture_identity=fixture_identity,
        kickoff_utc_iso=kickoff_utc_iso,
        research_xg=research_xg,
        score_matrix_audit=MappingProxyType(matrix_audit) if matrix_audit else None,
        market_assessments=ordered,
        authority=_authority_map(),
    )


def scan_current_fixture_all_markets(
    *,
    complete_current_history: latest_history.CurrentLatestDurableFreshHistoryHandoff,
    fixture_identity: str,
    provider_semantic_registry: Optional[CurrentSportyBetSemanticRegistry] = None,
    weh_feature_row: Optional[Mapping[str, object]] = None,
) -> CurrentAllMarketShadowFixtureScan:
    """Build the current source-bound 15-market research eligibility surface.

    The function never accepts raw current xG floats or caller-selected provider
    lines.  Missing current provider proof remains an explicit provider blocker.
    """

    registry = _verified_provider_registry(provider_semantic_registry)
    provider_statuses, total_lines, ah_lines = _provider_inputs(registry)
    research_xg, xg_block, missing_inputs, kickoff = (
        _research_xg_from_complete_current_history(
            complete_current_history,
            fixture_identity,
        )
    )
    scan = scan_fixture_all_markets(
        fixture_identity=fixture_identity,
        research_xg=research_xg,
        kickoff_utc_iso=kickoff,
        weh_feature_row=weh_feature_row,
        total_goals_lines=total_lines,
        asian_handicap_home_lines=ah_lines,
        provider_semantic_by_market=provider_statuses,
    )
    if xg_block is None:
        return scan

    revised: list[ShadowMarketAssessment] = []
    for assessment in scan.market_assessments:
        if assessment.market_id in {
            MarketId.HOME_WIN_EITHER_HALF,
            MarketId.AWAY_WIN_EITHER_HALF,
        }:
            revised.append(assessment)
            continue
        reason = (
            "Current source-bound xG inputs are incomplete"
            if xg_block is ShadowDisposition.MISSING_REQUIRED_INPUT
            else "Fixture is outside the reviewed current xG seal window"
        )
        revised.append(
            _blocked_assessment(
                assessment.market_id,
                xg_block,
                missing_inputs=missing_inputs,
                blocker_reason=reason,
                provider_semantic_status=assessment.provider_semantic_status,
            )
        )
    return CurrentAllMarketShadowFixtureScan(
        fixture_identity=scan.fixture_identity,
        kickoff_utc_iso=scan.kickoff_utc_iso,
        research_xg=None,
        score_matrix_audit=None,
        market_assessments=tuple(revised),
        authority=_authority_map(),
    )


def build_current_all_market_shadow_scan(
    fixtures: Sequence[CurrentAllMarketShadowFixtureScan],
) -> CurrentAllMarketShadowScan:
    """Assemble one or more fixture scans into a deterministic handoff."""

    return CurrentAllMarketShadowScan(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        fixtures=tuple(fixtures),
        authority=_authority_map(),
    )


def canonical_current_all_market_shadow_scan_bytes(
    scan: CurrentAllMarketShadowScan,
) -> bytes:
    if type(scan) is not CurrentAllMarketShadowScan:
        raise AllMarketShadowError("value must be exact CurrentAllMarketShadowScan")
    rebuilt = CurrentAllMarketShadowScan(
        schema_version=scan.schema_version,
        dataset_name=scan.dataset_name,
        fixtures=tuple(scan.fixtures),
        authority=dict(scan.authority),
    )
    return _canonical_json_bytes(rebuilt.to_dict())


def sha256_current_all_market_shadow_scan(scan: CurrentAllMarketShadowScan) -> str:
    return hashlib.sha256(canonical_current_all_market_shadow_scan_bytes(scan)).hexdigest()


__all__ = [
    "DEFAULT_AH_HOME_LINES",
    "DEFAULT_TOTAL_GOALS_LINE",
    "DATASET_NAME",
    "SCHEMA_VERSION",
    "AllMarketShadowError",
    "CurrentAllMarketShadowFixtureScan",
    "CurrentAllMarketShadowScan",
    "ResearchXGRates",
    "ShadowDisposition",
    "ShadowMarketAssessment",
    "build_current_all_market_shadow_scan",
    "canonical_current_all_market_shadow_scan_bytes",
    "scan_current_fixture_all_markets",
    "scan_fixture_all_markets",
    "sha256_current_all_market_shadow_scan",
]
