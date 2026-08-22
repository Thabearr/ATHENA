"""Set-based historical warehouse quality classification.

The original ``Warehouse.refresh_quality`` predates the 1.2M-match backbone and
performs one event lookup per match. This implementation preserves the same
classification rules while doing the work in one indexed SQLite UPDATE.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.build_historical_warehouse import Warehouse


def refresh_quality_set_based(warehouse: "Warehouse") -> None:
    """Recompute ``data_quality`` for the whole warehouse without N+1 queries."""
    warehouse.conn.execute(
        """
        UPDATE warehouse_matches AS m
        SET data_quality = CASE
            WHEN m.home_score_ft IS NOT NULL
             AND m.away_score_ft IS NOT NULL
             AND m.home_score_ht IS NOT NULL
             AND m.away_score_ht IS NOT NULL
             AND m.referee IS NOT NULL
             AND TRIM(m.referee) <> ''
             AND m.home_coach IS NOT NULL
             AND TRIM(m.home_coach) <> ''
             AND m.away_coach IS NOT NULL
             AND TRIM(m.away_coach) <> ''
             AND EXISTS (
                 SELECT 1
                 FROM warehouse_events AS e
                 WHERE e.match_key = m.match_key
             )
            THEN 'RICH'

            WHEN m.home_score_ft IS NOT NULL
             AND m.away_score_ft IS NOT NULL
             AND (
                 (m.home_score_ht IS NOT NULL AND m.away_score_ht IS NOT NULL)
                 OR EXISTS (
                     SELECT 1
                     FROM warehouse_events AS e
                     WHERE e.match_key = m.match_key
                 )
             )
            THEN 'STANDARD'

            WHEN m.home_score_ft IS NOT NULL
             AND m.away_score_ft IS NOT NULL
            THEN 'BASIC'

            ELSE 'PARTIAL'
        END
        """
    )
    warehouse.conn.commit()
