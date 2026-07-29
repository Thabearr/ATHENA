"""Idempotent persistence for validated half-time source evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum

from domain.half_time_data import HalfTimeObservation


class ObservationWriteResult(str, Enum):
    INSERTED = "INSERTED"
    UPDATED = "UPDATED"
    UNCHANGED = "UNCHANGED"
    CONFLICT = "CONFLICT"


_BASE_COLUMNS = (
    "fixture_identity",
    "home_team",
    "away_team",
    "kickoff_time",
    "full_time_home_goals",
    "full_time_away_goals",
    "half_time_home_goals",
    "half_time_away_goals",
    "source",
    "observed_at",
    "source_fixture_id",
    "half_time_score_provenance",
    "validation_status",
    "rejection_reasons",
    "league",
    "season",
)

_CONFLICT_COLUMNS = (
    "conflict_status",
    "conflict_fingerprint",
    "conflict_reason",
    "conflict_observed_at",
)

_COLUMNS = _BASE_COLUMNS + _CONFLICT_COLUMNS
_MATERIAL_COLUMNS = tuple(
    column for column in _BASE_COLUMNS if column != "observed_at"
)


def _serialize_datetime(
    value,
    *,
    require_timezone: bool,
):
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError("observation timestamps must be datetime values")
    if require_timezone and (
        value.tzinfo is None or value.utcoffset() is None
    ):
        raise ValueError("observed_at must be timezone-aware")
    return value.isoformat()


def _parse_aware_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _serialize_score(value):
    if isinstance(value, bool):
        return json.dumps(value)
    if isinstance(value, (dict, list)):
        return json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    return value


class HalfTimeObservationStore:
    """Write only half_time_observations using the caller's transaction."""

    @staticmethod
    def _payload(observation: HalfTimeObservation) -> dict:
        if not isinstance(observation, HalfTimeObservation):
            raise TypeError("observation must be a HalfTimeObservation")
        return {
            "fixture_identity": observation.fixture_identity,
            "home_team": observation.home_team,
            "away_team": observation.away_team,
            "kickoff_time": _serialize_datetime(
                observation.kickoff_time,
                require_timezone=False,
            ),
            "full_time_home_goals": _serialize_score(
                observation.full_time_home_goals
            ),
            "full_time_away_goals": _serialize_score(
                observation.full_time_away_goals
            ),
            "half_time_home_goals": _serialize_score(
                observation.half_time_home_goals
            ),
            "half_time_away_goals": _serialize_score(
                observation.half_time_away_goals
            ),
            "source": observation.source,
            "observed_at": _serialize_datetime(
                observation.observed_at,
                require_timezone=True,
            ),
            "source_fixture_id": observation.source_fixture_id,
            "half_time_score_provenance": (
                observation.half_time_score_provenance.value
            ),
            "validation_status": observation.validation_status.value,
            "rejection_reasons": json.dumps(
                list(observation.rejection_reasons),
                ensure_ascii=True,
                separators=(",", ":"),
            ),
            "league": observation.league,
            "season": observation.season,
            "conflict_status": int(observation.conflict_status),
            "conflict_fingerprint": observation.conflict_fingerprint,
            "conflict_reason": observation.conflict_reason,
            "conflict_observed_at": _serialize_datetime(
                observation.conflict_observed_at,
                require_timezone=True,
            ),
        }

    @staticmethod
    def _conflict_metadata(incoming: dict) -> dict:
        material_payload = {
            column: incoming[column]
            for column in _MATERIAL_COLUMNS
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                material_payload,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        reason = (
            "Materially different source observation received at the same "
            "or unknown provider version; fingerprint="
            f"{fingerprint[:16]}."
        )[:240]
        return {
            "conflict_status": 1,
            "conflict_fingerprint": fingerprint,
            "conflict_reason": reason,
            "conflict_observed_at": incoming["observed_at"],
        }

    @staticmethod
    def _write_result(
        existing: dict,
        incoming: dict,
    ) -> ObservationWriteResult:
        existing_time = _parse_aware_datetime(existing["observed_at"])
        incoming_time = _parse_aware_datetime(incoming["observed_at"])
        materially_different = any(
            existing[column] != incoming[column]
            for column in _MATERIAL_COLUMNS
        )

        if incoming_time is not None:
            if existing_time is None:
                return ObservationWriteResult.UPDATED
            if incoming_time > existing_time:
                return ObservationWriteResult.UPDATED
            if incoming_time < existing_time:
                return ObservationWriteResult.UNCHANGED
            return (
                ObservationWriteResult.CONFLICT
                if materially_different
                else ObservationWriteResult.UNCHANGED
            )

        return (
            ObservationWriteResult.CONFLICT
            if materially_different
            else ObservationWriteResult.UNCHANGED
        )

    def upsert(
        self,
        cursor,
        observation: HalfTimeObservation,
    ) -> ObservationWriteResult:
        """Insert or conservatively replace one fixture/source observation."""
        incoming = self._payload(observation)
        cursor.execute(
            f"""
            SELECT {", ".join(_COLUMNS)}
            FROM half_time_observations
            WHERE fixture_identity = ? AND source = ?
            """,
            (
                incoming["fixture_identity"],
                incoming["source"],
            ),
        )
        existing_row = cursor.fetchone()
        existing = (
            dict(zip(_COLUMNS, existing_row))
            if existing_row is not None
            else None
        )

        if existing == incoming:
            return ObservationWriteResult.UNCHANGED
        if existing is not None:
            write_result = self._write_result(existing, incoming)
            if write_result == ObservationWriteResult.CONFLICT:
                conflict_metadata = self._conflict_metadata(incoming)
                if any(
                    existing[column] != conflict_metadata[column]
                    for column in _CONFLICT_COLUMNS
                ):
                    cursor.execute(
                        """
                        UPDATE half_time_observations
                        SET conflict_status = ?,
                            conflict_fingerprint = ?,
                            conflict_reason = ?,
                            conflict_observed_at = ?
                        WHERE fixture_identity = ? AND source = ?
                        """,
                        (
                            conflict_metadata["conflict_status"],
                            conflict_metadata["conflict_fingerprint"],
                            conflict_metadata["conflict_reason"],
                            conflict_metadata["conflict_observed_at"],
                            incoming["fixture_identity"],
                            incoming["source"],
                        ),
                    )
                return ObservationWriteResult.CONFLICT
            if write_result != ObservationWriteResult.UPDATED:
                return write_result
            if (
                existing["conflict_status"]
                and incoming["validation_status"] != "VALID"
            ):
                for column in _CONFLICT_COLUMNS:
                    incoming[column] = existing[column]

        placeholders = ", ".join("?" for _ in _COLUMNS)
        updates = ", ".join(
            f"{column}=excluded.{column}"
            for column in _COLUMNS
            if column not in {"fixture_identity", "source"}
        )
        cursor.execute(
            f"""
            INSERT INTO half_time_observations ({", ".join(_COLUMNS)})
            VALUES ({placeholders})
            ON CONFLICT(fixture_identity, source) DO UPDATE SET
                {updates}
            """,
            tuple(incoming[column] for column in _COLUMNS),
        )
        return (
            ObservationWriteResult.INSERTED
            if existing is None
            else ObservationWriteResult.UPDATED
        )


__all__ = [
    "HalfTimeObservationStore",
    "ObservationWriteResult",
]
