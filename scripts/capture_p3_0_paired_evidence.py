#!/usr/bin/env python3
"""Explicit prospective paired capture for ATHENA P3.0-E1."""
from scripts._p3_0_paired_capture_part2 import *  # noqa: F401,F403
from scripts import p3_0_current_request_reconciliation_compat as _request_reconciliation


_unscoped_main = main


def main(argv=None):
    """Run the paired collector under the full supported Current Shadow pre-Router scope."""

    with _request_reconciliation.scoped_current_request_pre_router_compatibility():
        return _unscoped_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
