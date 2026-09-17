"""Scoped P3.0-E1 reuse of the supported Current Shadow pre-Router runtime semantics.

The P3.0 paired collector intentionally calls the Current Shadow source/Price-All/
Router boundary directly so it can stop before Portfolio and delivery.  That direct
call must nevertheless execute under the same semantic compatibility layers as the
supported ``scripts.execute_current_shadow_request`` path.

The supported request is layered as follows before the common Router acquisition
boundary is reached:

* request wrapper: run-199 reconciliation compatibility and tolerant live inventory;
* request wrapper: reviewed current-as-of Elo-only xG fallback;
* daily worker: Current Shadow fixture-identity recovery V3;
* daily worker: row-local direct-quote replay;
* daily worker: all-market worker marker while the common runner executes.

P3.0-E1 previously reused only the first bullet.  That made the paired capture a
narrower application path than the supported Current Shadow request and caused
``NO_EXACT_REVIEWED_FOTMOB_MATCH`` even though the supported daily worker had an
additional reviewed identity-recovery boundary.

This scope delegates to the existing reviewed installers; it defines no aliases,
matching tolerance, model formula, price rule, Router rule, Portfolio behavior,
delivery behavior, authentication, account state, staking, BET, or wager authority.
Every installed hook and environment marker is restored unconditionally in exact
LIFO order.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from typing import Iterator

from scripts import execute_current_shadow_all_market as all_market_cli
from scripts import execute_current_shadow_daily as current_daily
from scripts import execute_current_shadow_request as current_request


@contextmanager
def scoped_current_request_pre_router_compatibility() -> Iterator[None]:
    """Mirror the supported request/daily semantic stack through Router only."""

    proxy = None
    previous_proxy = None
    xg_hooks = None
    identity_hooks = None
    quote_hook = None
    prior_all_market_worker = os.environ.get(all_market_cli.WORKER_ENV)
    try:
        proxy, previous_proxy = current_request._install_reconciliation_compatibility()
        xg_hooks = current_request.xg_fallback.install()
        os.environ[all_market_cli.WORKER_ENV] = "1"
        identity_hooks = current_daily.identity_recovery.install(
            current_daily.runner.reconciliation
        )
        quote_hook = current_daily.quote_replay.install()
        yield
    finally:
        try:
            if quote_hook is not None:
                current_daily.quote_replay.restore(quote_hook)
        finally:
            try:
                if identity_hooks is not None:
                    current_daily.identity_recovery.restore(
                        current_daily.runner.reconciliation,
                        identity_hooks,
                    )
            finally:
                try:
                    if prior_all_market_worker is None:
                        os.environ.pop(all_market_cli.WORKER_ENV, None)
                    else:
                        os.environ[all_market_cli.WORKER_ENV] = prior_all_market_worker
                finally:
                    try:
                        if xg_hooks is not None:
                            current_request.xg_fallback.restore(xg_hooks)
                    finally:
                        if proxy is not None and previous_proxy is not None:
                            current_request._restore_reconciliation_compatibility(
                                proxy,
                                previous_proxy,
                            )


# Compatibility name retained for focused callers/tests from PR #369.  It now
# intentionally means the complete supported pre-Router semantic scope rather
# than only the outer request reconciliation hooks.
scoped_current_request_reconciliation_compatibility = (
    scoped_current_request_pre_router_compatibility
)


__all__ = [
    "scoped_current_request_pre_router_compatibility",
    "scoped_current_request_reconciliation_compatibility",
]
