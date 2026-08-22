#!/usr/bin/env python3
"""Run a historical warehouse script with million-row-safe helpers.

This is a narrow compatibility shim: target scripts keep their existing CLI and
merge rules, while quality refresh becomes set-based, immutable source
priorities are memoized, and existing-match provenance is loaded once per
upsert instead of once per populated field. Import failures still propagate
unchanged through ``runpy``.
"""
from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_historical_warehouse import (  # noqa: E402
    MATCH_FIELDS,
    Warehouse,
    match_key,
    now,
)
from scripts.historical_quality import refresh_quality_set_based  # noqa: E402


def fast_upsert_match(
    warehouse: Warehouse,
    row: dict[str, Any],
    *,
    source: str | None = None,
    source_id: str | None = None,
    source_url: str | None = None,
    coverage: dict[str, int] | None = None,
    source_key: str | None = None,
    source_match_id: str | None = None,
) -> str:
    """Equivalent source-priority upsert with fewer SQLite round trips."""
    source = source or source_key
    source_id = source_id or source_match_id
    if not source:
        raise ValueError("source/source_key is required")

    key = warehouse.source_match(source, source_id) or match_key(row)
    incoming_priority = warehouse.priority(source)
    existing = warehouse.conn.execute(
        "SELECT * FROM warehouse_matches WHERE match_key=?", (key,)
    ).fetchone()

    if not existing:
        values = {field: row.get(field) for field in MATCH_FIELDS}
        values["extra_json"] = values.get("extra_json") or "{}"
        cols = ["match_key", *MATCH_FIELDS]
        warehouse.conn.execute(
            f"INSERT INTO warehouse_matches({','.join(cols)}) VALUES({','.join('?' for _ in cols)})",
            [key, *[values[col] for col in MATCH_FIELDS]],
        )
        provenance_rows = [
            (key, field, source, incoming_priority)
            for field, value in values.items()
            if value not in (None, "")
        ]
        if provenance_rows:
            warehouse.conn.executemany(
                """INSERT OR REPLACE INTO warehouse_field_provenance
                   (match_key,field_name,source_key,source_priority) VALUES(?,?,?,?)""",
                provenance_rows,
            )
    else:
        provenance = {
            item["field_name"]: item
            for item in warehouse.conn.execute(
                """SELECT field_name,source_key,source_priority
                   FROM warehouse_field_provenance WHERE match_key=?""",
                (key,),
            )
        }
        updates: dict[str, Any] = {}
        provenance_rows: list[tuple[str, str, str, int]] = []
        for field in MATCH_FIELDS:
            incoming = row.get(field)
            if incoming in (None, ""):
                continue
            current = existing[field]
            prov = provenance.get(field)
            current_priority = int(prov["source_priority"]) if prov else 999
            old_source = prov["source_key"] if prov else None

            if current in (None, "") or incoming_priority < current_priority:
                if current not in (None, "") and str(current) != str(incoming):
                    warehouse._conflict(  # noqa: SLF001 - exact Warehouse merge semantics
                        key, field, current, incoming, old_source, source
                    )
                updates[field] = incoming
                provenance_rows.append((key, field, source, incoming_priority))
            elif str(current) != str(incoming):
                warehouse._conflict(  # noqa: SLF001 - exact Warehouse merge semantics
                    key, field, current, incoming, old_source, source
                )

        if updates:
            fields = list(updates)
            assignments = ",".join(f"{field}=?" for field in fields)
            warehouse.conn.execute(
                f"UPDATE warehouse_matches SET {assignments},updated_at=? WHERE match_key=?",
                [*[updates[field] for field in fields], now(), key],
            )
            warehouse.conn.executemany(
                """INSERT OR REPLACE INTO warehouse_field_provenance
                   (match_key,field_name,source_key,source_priority) VALUES(?,?,?,?)""",
                provenance_rows,
            )

    cov = {name: int(value) for name, value in (coverage or {}).items()}
    warehouse.conn.execute(
        """INSERT OR IGNORE INTO warehouse_match_sources(
               match_key,source_key,source_match_id,source_url,
               has_ft,has_ht,has_events,has_cards,has_lineups,has_coaches,
               has_officials,has_advanced_stats
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            key,
            source,
            source_id,
            source_url,
            cov.get("has_ft", 0),
            cov.get("has_ht", 0),
            cov.get("has_events", 0),
            cov.get("has_cards", 0),
            cov.get("has_lineups", 0),
            cov.get("has_coaches", 0),
            cov.get("has_officials", 0),
            cov.get("has_advanced_stats", 0),
        ),
    )
    warehouse._record_match_write()  # noqa: SLF001 - preserve batching behavior
    return key


def install_fast_warehouse_helpers() -> None:
    """Install process-local read/write optimizations without changing rules."""
    Warehouse.refresh_quality = refresh_quality_set_based  # type: ignore[method-assign]

    original_priority = Warehouse.priority

    def cached_priority(warehouse: Warehouse, source: str) -> int:
        cache = getattr(warehouse, "_source_priority_cache", None)
        if cache is None:
            cache = {}
            setattr(warehouse, "_source_priority_cache", cache)
        if source not in cache:
            cache[source] = original_priority(warehouse, source)
        return int(cache[source])

    Warehouse.priority = cached_priority  # type: ignore[method-assign]
    Warehouse.upsert_match = fast_upsert_match  # type: ignore[method-assign]


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
