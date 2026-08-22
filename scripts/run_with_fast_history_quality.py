#!/usr/bin/env python3
"""Run a historical warehouse script with the million-row-safe quality refresh.

This is a narrow compatibility shim: target scripts keep their existing CLI and
logic, but any call to ``Warehouse.refresh_quality`` uses the set-based
implementation for the duration of that process.
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

    Warehouse.refresh_quality = refresh_quality_set_based  # type: ignore[method-assign]
    sys.argv = [str(target), *sys.argv[2:]]
    runpy.run_path(str(target), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
