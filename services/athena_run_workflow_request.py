"""Pure GitHub-event to canonical ``RunRequest`` resolution for P4.2.

This module is deliberately a transport adapter only.  It delegates all date,
profile, objective, and request validation to the P4.1 parser and performs no
filesystem, network, provider, subprocess, or service work.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import re
from types import MappingProxyType

from domain.run_contracts import RunRequest
from services.athena_run_request_parser import parse_explicit_request


SCHEDULE_DAYS = "today"
SCHEDULE_TARGET_LEGS = 20
SCHEDULE_TARGET_TOTAL_ODDS = None
SCHEDULE_BOOKIE = "sportybet"
SCHEDULE_PROFILE = "main"

WORKFLOW_DISPATCH_DEFAULTS = MappingProxyType(
    {
        "days": "today",
        "target_legs": "20",
        "target_total_odds": "",
        "bookie": "sportybet",
        "profile": "main",
    }
)
WORKFLOW_INPUT_NAMES = tuple(sorted(WORKFLOW_DISPATCH_DEFAULTS))
_CANONICAL_TARGET_LEGS = re.compile(r"^(?:[1-9]|[1-4][0-9]|50)$", re.ASCII)


class AthenaRunWorkflowRequestError(ValueError):
    """Raised when an Actions event is not an exact canonical run request."""


def _validate_dispatch_inputs(dispatch_inputs: Mapping[str, str] | None) -> dict[str, str]:
    if not isinstance(dispatch_inputs, Mapping):
        raise AthenaRunWorkflowRequestError("workflow_dispatch inputs must be a mapping")
    if set(dispatch_inputs) != set(WORKFLOW_INPUT_NAMES):
        raise AthenaRunWorkflowRequestError("workflow_dispatch input names are incomplete or unsupported")
    values: dict[str, str] = {}
    for name in WORKFLOW_INPUT_NAMES:
        value = dispatch_inputs[name]
        if type(value) is not str:
            raise AthenaRunWorkflowRequestError(f"workflow_dispatch input {name} must be exact text")
        values[name] = value
    if _CANONICAL_TARGET_LEGS.fullmatch(values["target_legs"]) is None:
        raise AthenaRunWorkflowRequestError("target_legs must be canonical decimal text from 1 through 50")
    return values


def resolve_workflow_request(
    *,
    event_name: str,
    dispatch_inputs: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> RunRequest:
    """Resolve one supported GitHub event through the P4.1 parser exactly once."""

    if type(event_name) is not str:
        raise AthenaRunWorkflowRequestError("event_name must be exact text")
    if event_name == "schedule":
        if dispatch_inputs not in (None, {}):
            raise AthenaRunWorkflowRequestError("schedule events cannot supply dispatch inputs")
        days = SCHEDULE_DAYS
        target_legs = SCHEDULE_TARGET_LEGS
        target_total_odds = SCHEDULE_TARGET_TOTAL_ODDS
        bookie = SCHEDULE_BOOKIE
        profile = SCHEDULE_PROFILE
    elif event_name == "workflow_dispatch":
        values = _validate_dispatch_inputs(dispatch_inputs)
        days = values["days"]
        target_legs = int(values["target_legs"])
        target_total_odds = values["target_total_odds"] or None
        bookie = values["bookie"]
        profile = values["profile"]
    else:
        raise AthenaRunWorkflowRequestError("only schedule and workflow_dispatch events are supported")

    try:
        request = parse_explicit_request(
            days=days,
            target_legs=target_legs,
            target_total_odds=target_total_odds,
            bookie=bookie,
            profile=profile,
            now=now,
        )
    except (TypeError, ValueError) as exc:
        raise AthenaRunWorkflowRequestError(str(exc)) from exc
    if type(request) is not RunRequest:
        raise AthenaRunWorkflowRequestError("P4.1 parser did not return the exact RunRequest contract")
    return request


__all__ = [
    "AthenaRunWorkflowRequestError",
    "SCHEDULE_BOOKIE",
    "SCHEDULE_DAYS",
    "SCHEDULE_PROFILE",
    "SCHEDULE_TARGET_LEGS",
    "SCHEDULE_TARGET_TOTAL_ODDS",
    "WORKFLOW_DISPATCH_DEFAULTS",
    "WORKFLOW_INPUT_NAMES",
    "resolve_workflow_request",
]
