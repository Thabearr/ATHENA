"""Thin retained workflow syntax entry point; never dispatches or executes a run."""
from __future__ import annotations

import os
from datetime import datetime, timezone
import sys

from services.athena_shadow_issue_comment_compatibility import resolve_comment


def main() -> int:
    try:
        result = resolve_comment(os.environ.get("COMMENT_BODY", ""), now=datetime.now(timezone.utc))
    except ValueError:
        print("ATHENA request comment does not match reviewed grammar/date bounds", file=sys.stderr)
        return 2
    # Three validated lines consumed by the unchanged workflow handoff. No
    # canonical dispatch happens even when the evidence mapping is representable.
    print(result.target_legs)
    print(result.legacy_fixture_scope)
    print(result.legacy_fixture_dates)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
