"""Freeze the non-network collection control for the reviewed fresh xG holdout.

This boundary resolves the exact PR #149 merge timestamp into the prospective
holdout start and freezes the operational request cadence/evidence-retention
requirements that a later activation runner must obey. Importing or executing
this module performs no network access and does not start the holdout campaign.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import hashlib
import types
from collections.abc import Mapping
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
CAPTURE_MINUTES_UTC = (0, 30)
REQUEST_TIMEZONE = "UTC"
REQUEST_CCODE3 = "NGA"
REQUEST_DATE_OFFSETS_DAYS = (0, 1)
REQUESTS_PER_ACTIVE_TICK = len(REQUEST_DATE_OFFSETS_DAYS)

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


class FreshHoldoutCollectionControlError(ValueError):
    """Raised when the pre-activation collection control cannot fail closed."""


class ControlPhase(str, enum.Enum):
    PRE_START = "PRE_START"
    PREDICTION_AND_SETTLEMENT_COLLECTION = "PREDICTION_AND_SETTLEMENT_COLLECTION"
    SETTLEMENT_TAIL_ONLY = "SETTLEMENT_TAIL_ONLY"
    COLLECTION_COMPLETE = "COLLECTION_COMPLETE"


def _error(message: str) -> FreshHoldoutCollectionControlError:
    return FreshHoldoutCollectionControlError(message)


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


def settlement_tail_end_utc() -> dt.datetime:
    return _parse_utc(SETTLEMENT_TAIL_END_UTC_TEXT, "settlement tail end")


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
        raise _error("scheduled tick must be an exact UTC :00 or :30 boundary")
    return tick


def control_phase(value: dt.datetime) -> ControlPhase:
    current = _utc(value, "control time")
    start = holdout_start_utc()
    hard = hard_close_utc()
    tail = settlement_tail_end_utc()
    if current < start:
        return ControlPhase.PRE_START
    if current < hard:
        return ControlPhase.PREDICTION_AND_SETTLEMENT_COLLECTION
    if current < tail:
        return ControlPhase.SETTLEMENT_TAIL_ONLY
    return ControlPhase.COLLECTION_COMPLETE


def request_dates_for_tick(scheduled_tick: dt.datetime) -> tuple[str, ...]:
    """Return exact FotMob UTC request dates for one scheduled active tick."""
    tick = _scheduled_tick(scheduled_tick)
    phase = control_phase(tick)
    if phase in {ControlPhase.PRE_START, ControlPhase.COLLECTION_COMPLETE}:
        return ()
    if phase is ControlPhase.SETTLEMENT_TAIL_ONLY:
        offsets = (0,)
    else:
        offsets = REQUEST_DATE_OFFSETS_DAYS
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
    prediction_sealing_authorized: bool
    network_acquisition_authorized: bool

    def __post_init__(self) -> None:
        tick = _scheduled_tick(self.scheduled_for_utc)
        object.__setattr__(self, "scheduled_for_utc", tick)
        if not isinstance(self.phase, ControlPhase):
            raise _error("tick phase is invalid")
        expected_phase = control_phase(tick)
        if self.phase is not expected_phase:
            raise _error("tick phase does not match scheduled time")
        expected_dates = request_dates_for_tick(tick)
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
            "prediction_sealing_authorized": self.prediction_sealing_authorized,
            "network_acquisition_authorized": self.network_acquisition_authorized,
        }


def build_collection_tick_plan(scheduled_tick: dt.datetime) -> CollectionTickPlan:
    verify_reviewed_implementation()
    tick = _scheduled_tick(scheduled_tick)
    phase = control_phase(tick)
    return CollectionTickPlan(
        scheduled_for_utc=tick,
        phase=phase,
        request_dates=request_dates_for_tick(tick),
        timezone=REQUEST_TIMEZONE,
        ccode3=REQUEST_CCODE3,
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
            "settlement_tail_end_utc": SETTLEMENT_TAIL_END_UTC_TEXT,
            "prediction_membership_close_selected_by_count_only_rules": True,
            "settlement_after_selected_close_preserves_preclose_kickoff_membership": True,
        },
        "capture_control": {
            "cadence_minutes": CAPTURE_INTERVAL_MINUTES,
            "utc_minutes": list(CAPTURE_MINUTES_UTC),
            "request_timezone": REQUEST_TIMEZONE,
            "request_ccode3": REQUEST_CCODE3,
            "active_request_date_offsets_days": list(REQUEST_DATE_OFFSETS_DAYS),
            "active_requests_per_tick": REQUESTS_PER_ACTIVE_TICK,
            "settlement_tail_request_date_offsets_days": [0],
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
    "CAPTURE_INTERVAL_MINUTES",
    "CAPTURE_MINUTES_UTC",
    "CONTROL_ID",
    "CONTROL_STATE",
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
    "SETTLEMENT_TAIL_END_UTC_TEXT",
    "build_collection_tick_plan",
    "collection_control_receipt",
    "control_phase",
    "hard_close_utc",
    "holdout_start_utc",
    "minimum_gate_utc",
    "pr149_merge_utc",
    "request_dates_for_tick",
    "settlement_tail_end_utc",
    "verify_reviewed_implementation",
]
