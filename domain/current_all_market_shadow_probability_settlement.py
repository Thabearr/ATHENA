"""Research-only all-market Shadow probability and settlement surface (PR C).

Two layers are intentionally separated:

* ``scan_fixture_all_markets`` is a deterministic mathematical composition helper.
* ``scan_current_fixture_all_markets`` is the current source-bound entrypoint.

Both layers remain research/shadow only. All authority flags remain false.
"""
from __future__ import annotations

import hashlib
from types import MappingProxyType
from typing import Mapping, Optional, Sequence

from domain import current_fotmob_latest_durable_fresh_history as latest_history
from domain.current_sportybet_semantic_registry import (
    CurrentSportyBetSemanticRegistry,
    ProviderSemanticStatus,
)
from domain.early_payout_lead_path_probabilities import project_early_payout_market
from domain.markets import MarketId
from domain.score_matrix import build_score_matrix
from domain.score_matrix_market_probabilities import (
    AnalyticalProjectionError,
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
from domain._all_market_shadow_current_binding import (
    _combine_line_projections,
    _finite_line_tuple,
    _provider_blocked,
    _provider_inputs,
    _research_xg_from_complete_current_history,
    _verified_provider_registry,
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
) -> CurrentAllMarketShadowFixtureScan:
    """Build the current source-bound 15-market research eligibility surface.

    The function never accepts raw current xG floats, caller-selected provider
    lines, or caller-authored WEH feature values.  Missing current provider
    proof remains an explicit provider blocker.  WEH remains
    SPECIALIST_FEATURES_MISSING until a later reviewed source-bound WEH
    feature handoff exists; raw ``weh_feature_row`` mappings cannot mint
    current readiness here.
    """

    registry = _verified_provider_registry(provider_semantic_registry)
    provider_statuses, total_lines, ah_lines = _provider_inputs(registry)
    research_xg, xg_block, missing_inputs, kickoff = (
        _research_xg_from_complete_current_history(
            complete_current_history,
            fixture_identity,
        )
    )
    # Current source-bound lane never accepts caller-minted WEH features.
    # Lower-level scan_fixture_all_markets may still accept reviewed-style
    # feature mappings for deterministic mathematical tests.
    scan = scan_fixture_all_markets(
        fixture_identity=fixture_identity,
        research_xg=research_xg,
        kickoff_utc_iso=kickoff,
        weh_feature_row=None,
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
