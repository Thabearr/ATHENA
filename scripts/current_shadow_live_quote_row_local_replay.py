"""Install Current Shadow-only row-local direct SportyBet quote replay.

The reviewed raw event response and manifest remain immutable and authoritative.
This worker-local hook changes only how the already-captured event-detail market
rows are parsed: one malformed market/outcome row is omitted instead of making
an otherwise-valid event unusable. The hook is installed only around Current
Shadow execution and restores the original reviewed parser afterward.
"""
from __future__ import annotations

from typing import Callable

from domain import sportybet_live_event_quote_evidence as live
from domain import current_shadow_sportybet_tolerant_live_inventory as tolerant


POLICY_ID = "ATHENA_CURRENT_SHADOW_ROW_LOCAL_DIRECT_QUOTE_WORKER_REPLAY_V1"


def install() -> Callable:
    original = live.build_live_event_quote_inventory
    live.build_live_event_quote_inventory = tolerant.build_shadow_live_event_quote_inventory
    return original


def restore(original: Callable) -> None:
    if not callable(original):
        raise TypeError("original live quote inventory builder must be callable")
    live.build_live_event_quote_inventory = original


__all__ = ["POLICY_ID", "install", "restore"]
