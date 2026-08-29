"""Research-only all-market Shadow probability and settlement surface (PR C).

Composes reviewed ScoreMatrix, DNB/AH settlement, WEH specialist, and 1UP/2UP
lead-path into one deterministic 15-market research-only Shadow surface.
All production / pricing / selection / BET authority remains false.
"""
from __future__ import annotations

import hashlib

from types import MappingProxyType
from typing import Mapping, Optional, Sequence

from domain.early_payout_lead_path_probabilities import project_early_payout_market
from domain.markets import MarketId
from domain.score_matrix import build_score_matrix
from domain.score_matrix_market_probabilities import project_score_matrix_market
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


def scan_fixture_all_markets(
    *,
    fixture_identity: str,
    research_xg: Optional[ResearchXGRates],
    kickoff_utc_iso: Optional[str] = None,
    weh_feature_row: Optional[Mapping[str, object]] = None,
    total_goals_line: float = DEFAULT_TOTAL_GOALS_LINE,
    asian_handicap_home_lines: Sequence[float] = DEFAULT_AH_HOME_LINES,
    provider_semantic_by_market: Optional[Mapping[MarketId, str]] = None,
) -> CurrentAllMarketShadowFixtureScan:
    """Build the exact 15-market research Shadow surface for one fixture."""
    if type(fixture_identity) is not str or not fixture_identity.strip():
        raise AllMarketShadowError("fixture_identity must be non-empty")

    assessments: dict[MarketId, ShadowMarketAssessment] = {}
    score_matrix = None
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
                if provider
                and provider
                in {
                    "CURRENT_PROVIDER_UNAVAILABLE",
                    "CURRENT_PROVIDER_UNPROVEN",
                    "PROVIDER_UNPROVEN",
                }
                else ShadowDisposition.ANALYTICAL_READY
            )
            assessments[market_id] = _from_score_matrix_projection(
                projection,
                disposition=disposition,
                score_matrix_audit=matrix_audit,
                provider_semantic_status=provider,
            )

        try:
            tg_projection = project_score_matrix_market(
                score_matrix, MarketId.TOTAL_GOALS, line=total_goals_line
            )
            provider = _provider_status(provider_semantic_by_market, MarketId.TOTAL_GOALS)
            assessments[MarketId.TOTAL_GOALS] = _from_score_matrix_projection(
                tg_projection,
                disposition=ShadowDisposition.ANALYTICAL_READY,
                score_matrix_audit=matrix_audit,
                provider_semantic_status=provider,
            )
        except Exception as exc:
            assessments[MarketId.TOTAL_GOALS] = _blocked_assessment(
                MarketId.TOTAL_GOALS,
                ShadowDisposition.UNSUPPORTED_EXACT_LINE,
                missing_inputs=(),
                blocker_reason=str(exc),
                provider_semantic_status=_provider_status(
                    provider_semantic_by_market, MarketId.TOTAL_GOALS
                ),
            )

        ah_lines = tuple(float(line) for line in asian_handicap_home_lines)
        if not ah_lines:
            assessments[MarketId.ASIAN_HANDICAP] = _blocked_assessment(
                MarketId.ASIAN_HANDICAP,
                ShadowDisposition.UNSUPPORTED_EXACT_LINE,
                blocker_reason="No Asian Handicap home lines supplied",
                provider_semantic_status=_provider_status(
                    provider_semantic_by_market, MarketId.ASIAN_HANDICAP
                ),
            )
        else:
            try:
                preferred = -0.5 if -0.5 in ah_lines else ah_lines[0]
                ah_projection = project_score_matrix_market(
                    score_matrix, MarketId.ASIAN_HANDICAP, line=preferred
                )
                provider = _provider_status(
                    provider_semantic_by_market, MarketId.ASIAN_HANDICAP
                )
                if provider in {
                    "CURRENT_PROVIDER_UNAVAILABLE",
                    "CURRENT_PROVIDER_UNPROVEN",
                    "PROVIDER_UNPROVEN",
                }:
                    disposition = ShadowDisposition.ANALYTICAL_READY_PROVIDER_BLOCKED
                else:
                    disposition = ShadowDisposition.ANALYTICAL_READY
                assessments[MarketId.ASIAN_HANDICAP] = _from_score_matrix_projection(
                    ah_projection,
                    disposition=disposition,
                    score_matrix_audit=matrix_audit,
                    provider_semantic_status=provider or "CURRENT_PROVIDER_UNPROVEN",
                )
            except Exception as exc:
                assessments[MarketId.ASIAN_HANDICAP] = _blocked_assessment(
                    MarketId.ASIAN_HANDICAP,
                    ShadowDisposition.UNSUPPORTED_EXACT_LINE,
                    blocker_reason=str(exc),
                    provider_semantic_status=_provider_status(
                        provider_semantic_by_market, MarketId.ASIAN_HANDICAP
                    ),
                )

        for market_id in (MarketId.MATCH_RESULT_1UP, MarketId.MATCH_RESULT_2UP):
            early = project_early_payout_market(score_matrix, market_id)
            assessments[market_id] = _from_early_payout(
                early,
                disposition=ShadowDisposition.ANALYTICAL_READY,
                score_matrix_audit=matrix_audit,
                provider_semantic_status=_provider_status(
                    provider_semantic_by_market, market_id
                ),
            )

    for market_id in (MarketId.HOME_WIN_EITHER_HALF, MarketId.AWAY_WIN_EITHER_HALF):
        if weh_feature_row is None:
            assessments[market_id] = _blocked_assessment(
                market_id,
                ShadowDisposition.SPECIALIST_FEATURES_MISSING,
                missing_inputs=PRE_MATCH_FEATURE_NAMES,
                blocker_reason="Specialized WEH 74-feature vector not supplied",
                provider_semantic_status=_provider_status(
                    provider_semantic_by_market, market_id
                ),
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
                    provider_semantic_status=_provider_status(
                        provider_semantic_by_market, market_id
                    ),
                )
                continue
            prediction = predict_win_either_half(weh_feature_row)
            assessments[market_id] = _from_weh(
                prediction,
                market_id,
                disposition=ShadowDisposition.ANALYTICAL_READY,
                provider_semantic_status=_provider_status(
                    provider_semantic_by_market, market_id
                ),
            )
        except WinEitherHalfInferenceError as exc:
            assessments[market_id] = _blocked_assessment(
                market_id,
                ShadowDisposition.SPECIALIST_FEATURES_MISSING,
                missing_inputs=(),
                blocker_reason=str(exc),
                provider_semantic_status=_provider_status(
                    provider_semantic_by_market, market_id
                ),
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
    "scan_fixture_all_markets",
    "sha256_current_all_market_shadow_scan",
]
