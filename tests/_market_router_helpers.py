from __future__ import annotations

from datetime import timedelta
import hashlib

from domain._forward_calibration_fit import fit_forward_calibrator
from domain._forward_calibration_projection import (
    CalibrationPartition,
    CalibrationVectorRow,
    calibration_unit_specs,
)
from domain._price_all_contracts import CalibratedValueCandidate
from domain.fixture_intelligence import (
    FixtureIntelligenceFact,
    IntelligenceCategory,
    IntelligenceFactStatus,
    SourceRole,
    build_snapshot,
)
from domain.fixture_state_v2 import build_fixture_state_v2_snapshot
from domain.markets import MarketId, OutcomeId
from tests._price_all_helpers import EVENT, NOW, reviewed_quote_bundle

KICKOFF = NOW + timedelta(days=1)
AS_OF = NOW - timedelta(minutes=5)
OBSERVED = NOW - timedelta(minutes=10)

_CONTEXT_BINDINGS = (
    (IntelligenceCategory.FORM, "home_form", 0.72),
    (IntelligenceCategory.FORM, "away_form", 0.61),
    (IntelligenceCategory.PERFORMANCE, "home_elo", 1612),
    (IntelligenceCategory.PERFORMANCE, "away_elo", 1548),
    (IntelligenceCategory.SCHEDULE_LOAD, "fatigue", 0.23),
    (IntelligenceCategory.FIXTURE_CONTEXT, "live_data_freshness", 0.95),
)


def _fact(category, field, value, *, status=IntelligenceFactStatus.SUPPORTED, marker="a"):
    return FixtureIntelligenceFact(
        category=category,
        field=field,
        status=status,
        value=value,
        source_provider="ROUTER_TEST_SOURCE",
        source_role=SourceRole.VERIFIED_EXTERNAL,
        source_reference=f"router:test:{field}:{marker}",
        observed_at=OBSERVED,
        evidence_file_path=f"evidence/router/{marker}.json",
        evidence_sha256=(marker * 64)[:64],
        notes="Router test evidence.",
    )


def complete_fixture_state(*, fixture_id="fx", missing_field=None, blocked_field=None):
    facts = []
    for index, (category, field, value) in enumerate(_CONTEXT_BINDINGS):
        if field == missing_field:
            continue
        status = IntelligenceFactStatus.STALE if field == blocked_field else IntelligenceFactStatus.SUPPORTED
        facts.append(_fact(category, field, value, status=status, marker=str(index + 1)))
    intelligence = build_snapshot(fixture_id, KICKOFF, AS_OF, facts)
    return build_fixture_state_v2_snapshot(intelligence)


def _unit(market: MarketId, outcome: OutcomeId, line: float | None):
    if market is MarketId.TOTAL_GOALS:
        specs = calibration_unit_specs(total_goal_lines=(line,))
    elif market is MarketId.ASIAN_HANDICAP:
        home_line = line if outcome is OutcomeId.HOME else -line
        specs = calibration_unit_specs(asian_handicap_home_lines=(home_line,))
    else:
        specs = calibration_unit_specs()
    return next(item for item in specs if (
        item.market_id is market
        and item.line == line
        and (item.selection_outcome is None or item.selection_outcome is outcome)
    ))


def phase6_variant(
    market: MarketId = MarketId.MATCH_RESULT,
    outcome: OutcomeId = OutcomeId.HOME,
    line: float | None = None,
    probabilities: tuple[float, ...] = (0.60, 0.22, 0.18),
    *,
    fixture_id: str = "fx",
    event_id: str = EVENT,
    model_id: str = "POISSON_GLM_SCORE_V1",
):
    unit = _unit(market, outcome, line)
    fit = CalibrationVectorRow(
        match_key=f"fit:{model_id}", match_date="2024-01-02", competition_key="L1",
        season="2024", regime="MID_EVENT", model_id=model_id, fold_index=1,
        fit_end_date="2024-01-01", partition=CalibrationPartition.OOF_CALIBRATION_FIT,
        unit=unit, raw_probabilities=probabilities, observed_index=0,
    )
    source_sha = hashlib.sha256(model_id.encode()).hexdigest()
    artifact = fit_forward_calibrator(
        (fit,), model_id=model_id, source_training_view_sha256=source_sha,
    )
    target = CalibrationVectorRow(
        match_key=fixture_id, match_date="2026-08-27", competition_key="L1",
        season="2026", regime="MID_EVENT", model_id=model_id, fold_index=2,
        fit_end_date="2026-08-26", partition=CalibrationPartition.TERMINAL_HOLDOUT_EVALUATION,
        unit=unit, raw_probabilities=probabilities, observed_index=0,
    )
    return CalibratedValueCandidate.from_phase6_calibration(
        artifact,
        target,
        fixture_id=fixture_id,
        sportybet_event_id=event_id,
        outcome_id=outcome,
    )


def quote_bundle(tmp_path, market, rows, line=None, **kwargs):
    return reviewed_quote_bundle(tmp_path, market, tuple(rows), line, **kwargs)[-1]
