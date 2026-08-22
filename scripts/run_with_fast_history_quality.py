#!/usr/bin/env python3
"""Run a historical warehouse script with million-row-safe helpers.

This is a narrow compatibility shim: target scripts keep their existing CLI and
logic, but quality refresh becomes set-based and immutable source priorities are
memoized for the lifetime of the import process. Import failures still propagate
unchanged through ``runpy``.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_historical_warehouse import Warehouse  # noqa: E402
from scripts.historical_quality import refresh_quality_set_based  # noqa: E402


def install_fast_warehouse_helpers() -> None:
    """Install process-local read optimizations without changing merge rules."""
    Warehouse.refresh_quality = refresh_quality_set_based  # type: ignore[method-assign]

    original_priority = Warehouse.priority
    priority_cache: dict[tuple[int, str], int] = {}

    def cached_priority(warehouse: Warehouse, source: str) -> int:
        key = (id(warehouse), source)
        if key not in priority_cache:
            priority_cache[key] = original_priority(warehouse, source)
        return priority_cache[key]

    Warehouse.priority = cached_priority  # type: ignore[method-assign]


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("usage: run_with_fast_history_quality.py <script> [args ...]")

    target = Path(sys.argv[1])
    if not target.is_absolute():
        target = ROOT / target
    target = target.resolve()
    scripts_root = (ROOT / "scripts").resolve()
    if scripts_root not in target.parents or target.suffix != ".py" or not target.is_file():
        raise SystemExit(f"target must be an existing Python script under {scripts_root}")
    if target == Path(__file__).resolve():
        raise SystemExit("runner cannot invoke itself")

    install_fast_warehouse_helpers()
    sys.argv = [str(target), *sys.argv[2:]]
    runpy.run_path(str(target), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
