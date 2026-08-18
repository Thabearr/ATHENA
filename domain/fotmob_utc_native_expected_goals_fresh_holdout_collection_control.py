"""Freeze the non-network collection control for the reviewed fresh xG holdout.

This boundary resolves the exact PR #149 merge timestamp into the prospective
holdout start and freezes the operational request cadence, count-only close-state
requirements, and evidence-retention obligations that a later activation runner
must obey. Importing or executing this module performs no network access and does
not start the holdout campaign.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import hashlib
import json
import types
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import domain.fotmob_data_matches_ordinary_ft_finished_score_adapter as score_adapter
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh


SCHEMA_VERSION = 1
CONTROL_ID = "FOTMOB_UTC_NATIVE_XG_FRESH_HOLDOUT_COLLECTION_CONTROL_V1"
CONTROL_STATE = (
    "REVIEWED_FRESH_HOLDOUT_COLLECTION_CONTROL_FROZEN_NOT_ACTIVATED_"
    "NO_NETWORK_ACQUISITION"
)
NEXT_REQUIRED_BOUNDARY = (
    "ACTIVATE_REVIEWED_FRESH_HOLDOUT_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_"
    "COLLECTION_RUNNER"
)

PR149_MERGE_SHA = "9ba66cff0677b5952c6c931ddf3cefb7c9565187"
PR149_MERGE_UTC_TEXT = "2026-08-18T04:18:35Z"
PR149_IMPLEMENTATION_BLOB_SHA = "5dabab12d5205d384fd3904cda0e68661ef90791"
HOLDOUT_START_UTC_TEXT = "2026-08-19T00:00:00Z"
MINIMUM_GATE_UTC_TEXT = "2026-09-16T00:00:00Z"
HARD_CLOSE_UTC_TEXT = "2026-11-17T00:00:00Z"
SETTLEMENT_TAIL_END_UTC_TEXT = "2026-11-18T00:00:00Z"

CAPTURE_INTERVAL_MINUTES = 30
CAPTURE_MINUTES_UTC = (7, 37)
REQUEST_TIMEZONE = "UTC"
REQUEST_CCODE3 = "NGA"
ACTIVE_REQUEST_DATE_OFFSETS_DAYS = (-1, 0, 1)
SETTLEMENT_REQUEST_DATE_OFFSETS_DAYS = (-1, 0)
REQUESTS_PER_ACTIVE_TICK = len(ACTIVE_REQUEST_DATE_OFFSETS_DAYS)
REQUESTS_PER_SETTLEMENT_TICK = len(SETTLEMENT_REQUEST_DATE_OFFSETS_DAYS)

CONTROL_ROOT_RELATIVE = (
    ".cache/athena-research/fotmob-utc-native-xg-fresh-holdout"
)
CAPTURE_INDEX_FILENAME = "capture-index.ndjson"
PREDICTION_JOURNAL_FILENAME = "prediction-journal.ndjson"
POST_SEAL_IDENTITY_JOURNAL_FILENAME = "post-seal-identity-journal.ndjson"
SETTLEMENT_JOURNAL_FILENAME = "settlement-journal.ndjson"
CONTROL_JOURNAL_FILENAME = "control-journal.ndjson"
CHECKPOINT_FILENAME = "checkpoint.json"

SAFETY_KEYS = tuple(sorted(fresh.SAFETY_KEYS))
_CLOSE_STATE_TOKEN = object()
_CLOSE_DECISIONS = frozenset(
    {
        fresh.HoldoutBoundaryDecision.CLOSE_COUNT_ONLY_COVERAGE_QUALIFIED.value,
        fresh.HoldoutBoundaryDecision.CLOSE_INSUFFICIENT_COVERAGE_NO_SUCCESSOR_DECISION.value,
    }
)
_OPEN_DECISION = fresh.HoldoutBoundaryDecision.OPEN_WAITING_FOR_COUNT_ONLY_COVERAGE.value


class FreshHoldoutCollectionControlError(ValueError):
    """Raised when the pre-activation collection control cannot fail closed."""


class ControlPhase(str, enum.Enum):
    PRE_START = "PRE_START"
    PREDICTION_AND_SETTLEMENT_COLLECTION = "PREDICTION_AND_SETTLEMENT_COLLECTION"
    SETTLEMENT_TAIL_ONLY = "SETTLEMENT_TAIL_ONLY"
    COLLECTION_COMPLETE = "COLLECTION_COMPLETE"


def _error(message: str) -> FreshHoldoutCollectionControlError:
    return FreshHoldoutCollectionControlError(message)


def _canonical(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("control evidence serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _sha256(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise _error(f"{label} must be exactly 64 lowercase hexadecimal characters")
    return value


def _utc(value: Any, label: str) -> dt.datetime:
    if type(value) is not dt.datetime or value.tzinfo is None or value.utcoffset() is None:
        raise _error(f"{label} must be a timezone-aware datetime")
    try:
        return value.astimezone(dt.timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error(f"{label} is invalid") from exc


def _parse_utc(value: Any, label: str) -> dt.datetime:
    if type(value) is not str or not value.endswith("Z") or value != value.strip():
        raise _error(f"{label} must be exact UTC Z text")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise _error(f"{label} is malformed") from exc
    return _utc(parsed, label)


def _utc_text(value: dt.datetime) -> str:
    return _utc(value, "timestamp").isoformat(timespec="seconds").replace("+00:00", "Z")


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in SAFETY_KEYS})


def pr149_merge_utc() -> dt.datetime:
    return _parse_utc(PR149_MERGE_UTC_TEXT, "PR149 merge timestamp")


def holdout_start_utc() -> dt.datetime:
    return _parse_utc(HOLDOUT_START_UTC_TEXT, "holdout start")


def minimum_gate_utc() -> dt.datetime:
    return _parse_utc(MINIMUM_GATE_UTC_TEXT, "minimum gate")


def hard_close_utc() -> dt.datetime:
    return _parse_utc(HARD_CLOSE_UTC_TEXT, "hard close")


def settlement_tail_end_utc(
    close_state: "CloseControlState | None" = None,
) -> dt.datetime:
    """Return the close-specific tail end, or the latest possible hard-close tail."""
    if close_state is None:
        return _parse_utc(SETTLEMENT_TAIL_END_UTC_TEXT, "latest settlement tail end")
    state = _checked_close_state(close_state)
    if state.selected_close_utc is None:
        raise _error("open close-control state has no settlement tail")
    return state.selected_close_utc + dt.timedelta(days=1)


def verify_reviewed_implementation() -> None:
    """Re-prove the exact merged PR149 implementation before activation planning."""
    if _git_blob_sha(Path(fresh.__file__)) != PR149_IMPLEMENTATION_BLOB_SHA:
        raise _error("PR149 fresh-holdout implementation blob changed")
    receipt = fresh.implementation_receipt()
    if receipt["implementation_state"] != fresh.IMPLEMENTATION_STATE:
        raise _error("PR149 implementation state changed")
    if receipt["fresh_holdout_started"] is not False:
        raise _error("PR149 unexpectedly reports fresh holdout already started")
    if receipt["network_acquisition_performed"] is not False:
        raise _error("PR149 unexpectedly reports network acquisition")
    if receipt["next_required_boundary"] != (
        "INSTALL_REVIEWED_FRESH_HOLDOUT_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_"
        "COLLECTION_CONTROL"
    ):
        raise _error("PR149 next boundary changed")
    if any(receipt["safety"].values()):
        raise _error("PR149 downstream authority changed")

    resolved = fresh.resolve_holdout_start(pr149_merge_utc())
    if resolved != holdout_start_utc():
        raise _error("resolved fresh holdout start changed")
    if fresh.minimum_gate_boundary(resolved) != minimum_gate_utc():
        raise _error("minimum gate boundary changed")
    if fresh.hard_close_boundary(resolved) != hard_close_utc():
        raise _error("hard close boundary changed")
    if hard_close_utc() + dt.timedelta(days=1) != settlement_tail_end_utc():
        raise _error("latest settlement tail boundary changed")

    minimum_repeat = score_adapter.MINIMUM_REPEAT_SEPARATION_SECONDS
    if type(minimum_repeat) is not int or minimum_repeat < 1:
        raise _error("ordinary-FT repeat separation contract changed")
    if CAPTURE_INTERVAL_MINUTES * 60 < minimum_repeat:
        raise _error("capture cadence is shorter than reviewed repeat separation")


def _scheduled_tick(value: dt.datetime) -> dt.datetime:
    tick = _utc(value, "scheduled tick")
    if (
        tick.second != 0
        or tick.microsecond != 0
        or tick.minute not in CAPTURE_MINUTES_UTC
    ):
        raise _error("scheduled tick must be an exact UTC :07 or :37 boundary")
    return tick


@dataclasses.dataclass(frozen=True)
class CloseControlState:
    """Result-free close-state receipt created only by PR149's count-only evaluator."""

    evaluated_boundary_utc: dt.datetime
    decision: str
    selected_close_utc: dt.datetime | None
    coverage_sha256: str
    _token: object = dataclasses.field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _CLOSE_STATE_TOKEN:
            raise _error("close-control state must come from reviewed count-only evaluation")
        evaluated = _utc(self.evaluated_boundary_utc, "evaluated close boundary")
        if evaluated.time() != dt.time.min:
            raise _error("evaluated close boundary must be an exact UTC midnight")
        if not (minimum_gate_utc() <= evaluated <= hard_close_utc()):
            raise _error("evaluated close boundary escaped the frozen 28/90-day window")
        object.__setattr__(self, "evaluated_boundary_utc", evaluated)
        if type(self.decision) is not str or self.decision not in (_OPEN_DECISION, *_CLOSE_DECISIONS):
            raise _error("close-control decision escaped reviewed vocabulary")
        selected = self.selected_close_utc
        if self.decision in _CLOSE_DECISIONS:
            if selected is None or _utc(selected, "selected close") != evaluated:
                raise _error("closed state must select its evaluated boundary exactly")
            object.__setattr__(self, "selected_close_utc", evaluated)
        elif selected is not None:
            raise _error("open state cannot carry a selected close boundary")
        object.__setattr__(
            self,
            "coverage_sha256",
            _sha256(self.coverage_sha256, "coverage_sha256"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluated_boundary_utc": _utc_text(self.evaluated_boundary_utc),
            "decision": self.decision,
            "selected_close_utc": (
                None if self.selected_close_utc is None else _utc_text(self.selected_close_utc)
            ),
            "coverage_sha256": self.coverage_sha256,
        }


def _checked_close_state(value: Any) -> CloseControlState:
    if type(value) is not CloseControlState or value._token is not _CLOSE_STATE_TOKEN:
        raise _error("close_state must be exact reviewed CloseControlState")
    return dataclasses.replace(value)


def evaluate_close_control_state(
    predictions: Sequence[fresh.SealedFreshPrediction],
    *,
    boundary: dt.datetime,
) -> CloseControlState:
    """Evaluate one UTC close boundary using PR149's count-only state machine only."""
    verify_reviewed_implementation()
    current = _utc(boundary, "close evaluation boundary")
    if current.time() != dt.time.min:
        raise _error("close evaluation boundary must be an exact UTC midnight")
    if not (minimum_gate_utc() <= current <= hard_close_utc()):
        raise _error("close evaluation boundary escaped the frozen 28/90-day window")
    try:
        result = fresh.evaluate_holdout_boundary(
            predictions,
            holdout_start=holdout_start_utc(),
            boundary=current,
        )
    except Exception as exc:
        raise _error("reviewed PR149 count-only close evaluation failed") from exc
    decision = result.get("decision")
    if decision not in (_OPEN_DECISION, *_CLOSE_DECISIONS):
        raise _error("PR149 returned unexpected close decision")
    if result.get("outcome_or_performance_input_used") is not False:
        raise _error("PR149 close evaluation unexpectedly used outcome/performance input")
    coverage = result.get("coverage")
    if type(coverage) is not dict:
        raise _error("PR149 close evaluation omitted coverage receipt")
    return CloseControlState(
        evaluated_boundary_utc=current,
        decision=decision,
        selected_close_utc=current if decision in _CLOSE_DECISIONS else None,
        coverage_sha256=hashlib.sha256(_canonical(coverage)).hexdigest(),
        _token=_CLOSE_STATE_TOKEN,
    )


def required_close_evaluation_boundary(value: dt.datetime) -> dt.datetime | None:
    """Return the latest UTC midnight whose count-only close state must be known."""
    current = _utc(value, "control time")
    minimum = minimum_gate_utc()
    if current < minimum:
        return None
    hard = hard_close_utc()
    if current >= hard:
        return hard
    return dt.datetime.combine(current.date(), dt.time.min, tzinfo=dt.timezone.utc)


def _validated_close_state_for_time(
    value: dt.datetime,
    close_state: CloseControlState | None,
) -> CloseControlState | None:
    current = _utc(value, "control time")
    required = required_close_evaluation_boundary(current)
    if required is None:
        if close_state is not None:
            raise _error("close_state is forbidden before the minimum gate boundary")
        return None
    if close_state is None:
        raise _error("current count-only close state is required at/after the minimum gate")
    state = _checked_close_state(close_state)
    if state.evaluated_boundary_utc > current:
        raise _error("close_state was evaluated in the future")
    if state.selected_close_utc is not None:
        if state.selected_close_utc > current:
            raise _error("selected close boundary is in the future")
        return state
    if state.evaluated_boundary_utc != required:
        raise _error("open close_state is stale for the latest required UTC boundary")
    return state


def control_phase(
    value: dt.datetime,
    *,
    close_state: CloseControlState | None = None,
) -> ControlPhase:
    current = _utc(value, "control time")
    start = holdout_start_utc()
    if current < start:
        if close_state is not None:
            raise _error("close_state is forbidden before holdout start")
        return ControlPhase.PRE_START
    state = _validated_close_state_for_time(current, close_state)
    selected_close = None if state is None else state.selected_close_utc
    if selected_close is None:
        return ControlPhase.PREDICTION_AND_SETTLEMENT_COLLECTION
    if current < selected_close + dt.timedelta(days=1):
        return ControlPhase.SETTLEMENT_TAIL_ONLY
    return ControlPhase.COLLECTION_COMPLETE


def request_dates_for_tick(
    scheduled_tick: dt.datetime,
    *,
    close_state: CloseControlState | None = None,
) -> tuple[str, ...]:
    """Return exact FotMob UTC request dates for one scheduled control tick."""
    tick = _scheduled_tick(scheduled_tick)
    phase = control_phase(tick, close_state=close_state)
    if phase in {ControlPhase.PRE_START, ControlPhase.COLLECTION_COMPLETE}:
        return ()
    offsets = (
        SETTLEMENT_REQUEST_DATE_OFFSETS_DAYS
        if phase is ControlPhase.SETTLEMENT_TAIL_ONLY
        else ACTIVE_REQUEST_DATE_OFFSETS_DAYS
    )
    return tuple(
        (tick.date() + dt.timedelta(days=offset)).strftime("%Y%m%d")
        for offset in offsets
    )


@dataclasses.dataclass(frozen=True)
class CollectionTickPlan:
    scheduled_for_utc: dt.datetime
    phase: ControlPhase
    request_dates: tuple[str, ...]
    timezone: str
    ccode3: str
    close_state: CloseControlState | None
    prediction_sealing_authorized: bool
    network_acquisition_authorized: bool

    def __post_init__(self) -> None:
        tick = _scheduled_tick(self.scheduled_for_utc)
        object.__setattr__(self, "scheduled_for_utc", tick)
        state = _validated_close_state_for_time(tick, self.close_state)
        if state is not None:
            object.__setattr__(self, "close_state", state)
        if not isinstance(self.phase, ControlPhase):
            raise _error("tick phase is invalid")
        expected_phase = control_phase(tick, close_state=state)
        if self.phase is not expected_phase:
            raise _error("tick phase does not match scheduled time and close state")
        expected_dates = request_dates_for_tick(tick, close_state=state)
        if type(self.request_dates) is not tuple or self.request_dates != expected_dates:
            raise _error("tick request-date plan changed")
        if self.timezone != REQUEST_TIMEZONE or self.ccode3 != REQUEST_CCODE3:
            raise _error("tick request identity changed")
        expected_prediction = self.phase is ControlPhase.PREDICTION_AND_SETTLEMENT_COLLECTION
        if self.prediction_sealing_authorized is not expected_prediction:
            raise _error("prediction-sealing phase authorization changed")
        if self.network_acquisition_authorized is not False:
            raise _error("control contract itself may not authorize network acquisition")

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheduled_for_utc": _utc_text(self.scheduled_for_utc),
            "phase": self.phase.value,
            "request_dates": list(self.request_dates),
            "timezone": self.timezone,
            "ccode3": self.ccode3,
            "close_state": None if self.close_state is None else self.close_state.to_dict(),
            "prediction_sealing_authorized": self.prediction_sealing_authorized,
            "network_acquisition_authorized": self.network_acquisition_authorized,
        }


def build_collection_tick_plan(
    scheduled_tick: dt.datetime,
    *,
    close_state: CloseControlState | None = None,
) -> CollectionTickPlan:
    verify_reviewed_implementation()
    tick = _scheduled_tick(scheduled_tick)
    state = _validated_close_state_for_time(tick, close_state)
    phase = control_phase(tick, close_state=state)
    return CollectionTickPlan(
        scheduled_for_utc=tick,
        phase=phase,
        request_dates=request_dates_for_tick(tick, close_state=state),
        timezone=REQUEST_TIMEZONE,
        ccode3=REQUEST_CCODE3,
        close_state=state,
        prediction_sealing_authorized=(
            phase is ControlPhase.PREDICTION_AND_SETTLEMENT_COLLECTION
        ),
        network_acquisition_authorized=False,
    )


def collection_control_receipt() -> dict[str, Any]:
    """Describe the frozen activation envelope without performing acquisition."""
    verify_reviewed_implementation()
    return {
        "schema_version": SCHEMA_VERSION,
        "control_id": CONTROL_ID,
        "control_state": CONTROL_STATE,
        "reviewed_implementation": {
            "merge_sha": PR149_MERGE_SHA,
            "merge_timestamp_utc": PR149_MERGE_UTC_TEXT,
            "implementation_blob_sha": PR149_IMPLEMENTATION_BLOB_SHA,
        },
        "fresh_holdout": {
            "start_utc": HOLDOUT_START_UTC_TEXT,
            "minimum_gate_utc": MINIMUM_GATE_UTC_TEXT,
            "hard_close_utc": HARD_CLOSE_UTC_TEXT,
            "latest_settlement_tail_end_utc": SETTLEMENT_TAIL_END_UTC_TEXT,
            "settlement_tail_duration_hours": 24,
            "prediction_membership_close_selected_by_count_only_rules": True,
            "settlement_after_selected_close_preserves_preclose_kickoff_membership": True,
        },
        "close_control": {
            "evaluation_starts_at_minimum_gate": True,
            "evaluation_boundary": "LATEST_REQUIRED_UTC_MIDNIGHT",
            "reviewed_evaluator": "PR149_EVALUATE_HOLDOUT_BOUNDARY",
            "outcome_or_performance_inputs_accepted": False,
            "open_state_must_be_current_through_latest_required_boundary": True,
            "selected_close_immediately_disables_prediction_sealing": True,
            "selected_close_is_irreversible": True,
            "tail_end_rule": "SELECTED_CLOSE_UTC_PLUS_24_HOURS",
            "hard_close_fallback_required": True,
        },
        "capture_control": {
            "cadence_minutes": CAPTURE_INTERVAL_MINUTES,
            "utc_minutes": list(CAPTURE_MINUTES_UTC),
            "nominal_schedule_avoids_start_of_hour": True,
            "actual_capture_observed_at_authoritative": True,
            "nominal_schedule_time_is_observation_time": False,
            "request_timezone": REQUEST_TIMEZONE,
            "request_ccode3": REQUEST_CCODE3,
            "active_request_date_offsets_days": list(ACTIVE_REQUEST_DATE_OFFSETS_DAYS),
            "active_requests_per_tick": REQUESTS_PER_ACTIVE_TICK,
            "settlement_tail_request_date_offsets_days": list(
                SETTLEMENT_REQUEST_DATE_OFFSETS_DAYS
            ),
            "settlement_requests_per_tick": REQUESTS_PER_SETTLEMENT_TICK,
            "fresh_capture_scope_limited_to_legacy_primary_ids": False,
            "all_structurally_qualified_provider_primary_ids_retained": True,
            "history_state_mutation_limited_to_frozen_legacy_primary_ids": True,
        },
        "durable_evidence": {
            "root_relative": CONTROL_ROOT_RELATIVE,
            "capture_index": CAPTURE_INDEX_FILENAME,
            "prediction_journal": PREDICTION_JOURNAL_FILENAME,
            "post_seal_identity_journal": POST_SEAL_IDENTITY_JOURNAL_FILENAME,
            "settlement_journal": SETTLEMENT_JOURNAL_FILENAME,
            "control_journal": CONTROL_JOURNAL_FILENAME,
            "checkpoint": CHECKPOINT_FILENAME,
            "append_only_journals_required": True,
            "prediction_seal_must_be_durable_before_kickoff": True,
            "every_qualified_post_seal_identity_observation_must_be_retained": True,
            "known_change_then_reversion_remains_excluding": True,
            "cross_run_state_restore_required": True,
            "close_state_revalidation_from_prediction_journal_required": True,
            "scheduler_gap_must_be_journaled_not_backfilled": True,
            "missed_capture_opportunity_may_not_be_retrofilled": True,
            "public_repo_schedule_auto_disable_is_coverage_risk_not_backfill_authority": True,
            "exact_bootstrap_projection_required_before_prediction_sealing": True,
        },
        "activation": {
            "workflow_or_scheduler_installed": False,
            "network_acquisition_performed": False,
            "fresh_holdout_collection_started": False,
            "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        },
        "safety": dict(_safety()),
    }


__all__ = [
    "ACTIVE_REQUEST_DATE_OFFSETS_DAYS",
    "CAPTURE_INTERVAL_MINUTES",
    "CAPTURE_MINUTES_UTC",
    "CONTROL_ID",
    "CONTROL_STATE",
    "CloseControlState",
    "CollectionTickPlan",
    "ControlPhase",
    "FreshHoldoutCollectionControlError",
    "HARD_CLOSE_UTC_TEXT",
    "HOLDOUT_START_UTC_TEXT",
    "MINIMUM_GATE_UTC_TEXT",
    "NEXT_REQUIRED_BOUNDARY",
    "PR149_MERGE_SHA",
    "PR149_MERGE_UTC_TEXT",
    "REQUEST_CCODE3",
    "REQUEST_TIMEZONE",
    "SETTLEMENT_REQUEST_DATE_OFFSETS_DAYS",
    "SETTLEMENT_TAIL_END_UTC_TEXT",
    "build_collection_tick_plan",
    "collection_control_receipt",
    "control_phase",
    "evaluate_close_control_state",
    "hard_close_utc",
    "holdout_start_utc",
    "minimum_gate_utc",
    "pr149_merge_utc",
    "request_dates_for_tick",
    "required_close_evaluation_boundary",
    "settlement_tail_end_utc",
    "verify_reviewed_implementation",
]
