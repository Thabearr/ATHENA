"""Scoped P3.0-E1 reuse of the reviewed Current Shadow request reconciliation boundary.

The P3.0 paired collector intentionally calls the Current Shadow source/Price-All/
Router boundary directly so it can stop before Portfolio and delivery. The supported
Current Shadow request wrapper installs two reconciliation-only compatibility hooks
before that same boundary: the evidence-bound run-199 fixture matcher and the
row-local tolerant live-inventory reader. Reuse those exact hooks here rather than
reimplementing them or silently running a narrower reconciliation policy.

This module grants no model, pricing, Router, Portfolio, delivery, login, wallet,
staking, BET, or wager authority. Every hook is restored unconditionally.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from scripts import execute_current_shadow_request as current_request


@contextmanager
def scoped_current_request_reconciliation_compatibility() -> Iterator[None]:
    """Install exactly the supported request reconciliation hooks for one scope."""

    proxy, previous = current_request._install_reconciliation_compatibility()
    try:
        yield
    finally:
        current_request._restore_reconciliation_compatibility(proxy, previous)


__all__ = ["scoped_current_request_reconciliation_compatibility"]
