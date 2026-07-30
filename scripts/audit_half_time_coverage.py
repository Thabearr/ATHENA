#!/usr/bin/env python3
"""Read-only half-time data coverage and research-readiness audit."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from domain.half_time_data import (  # noqa: E402
    HalfTimeObservation,
    ReadinessThresholds,
    ScoreProvenance,
    audit_half_time_coverage,
)


def _parse_datetime(value) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _stored_value(row, column_name: str, default=None):
    return row[column_name] if column_name in row.keys() else default


def _stored_conflict_status(row) -> bool:
    value = _stored_value(row, "conflict_status", 0)
    return str(value).strip().lower() in {"1", "true"}


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> set:
    return {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})")
    }


def _coalesce_expression(expressions: list, fallback: str = "NULL") -> str:
    if not expressions:
        return fallback
    if len(expressions) == 1:
        return expressions[0]
    return f"COALESCE({', '.join(expressions)})"


def _load_historical_rows(connection: sqlite3.Connection) -> list:
    if not _table_exists(connection, "historical_matches"):
        return []

    historical_columns = _table_columns(connection, "historical_matches")
    has_teams = _table_exists(connection, "teams")
    has_fixtures = _table_exists(connection, "fixtures")

    joins = []
    if has_teams:
        joins.extend(
            (
                "LEFT JOIN teams home ON home.team_id = hm.home_id",
                "LEFT JOIN teams away ON away.team_id = hm.away_id",
            )
        )
    if has_fixtures:
        joins.append(
            "LEFT JOIN fixtures f ON f.fixture_id = hm.fixture_id"
        )

    home_team_fields = []
    away_team_fields = []
    league_fields = []
    season_fields = []
    if has_teams:
        home_team_fields.append("home.name")
        away_team_fields.append("away.name")
    if has_fixtures:
        home_team_fields.append("f.home_team")
        away_team_fields.append("f.away_team")
        league_fields.append("f.league")
        season_fields.append("CAST(f.season AS TEXT)")
    if "league" in historical_columns:
        league_fields.insert(0, "hm.league")
    if "season_label" in historical_columns:
        season_fields.insert(0, "hm.season_label")

    source_expression = (
        "COALESCE(hm.data_source, 'legacy_untagged')"
        if "data_source" in historical_columns
        else "'legacy_untagged'"
    )
    query = f"""
        SELECT
            CAST(hm.fixture_id AS TEXT) AS fixture_identity,
            {_coalesce_expression(home_team_fields, "''")} AS home_team,
            {_coalesce_expression(away_team_fields, "''")} AS away_team,
            hm.match_date AS kickoff_time,
            hm.home_goals AS full_time_home_goals,
            hm.away_goals AS full_time_away_goals,
            {source_expression} AS source,
            'historical_matches' AS authoritative_store,
            {_coalesce_expression(league_fields)} AS league,
            {_coalesce_expression(season_fields)} AS season
        FROM historical_matches hm
        {' '.join(joins)}
        ORDER BY CAST(hm.fixture_id AS TEXT)
    """
    return list(connection.execute(query))


def _load_finished_result_rows(
    connection: sqlite3.Connection,
) -> list:
    if not (
        _table_exists(connection, "results")
        and _table_exists(connection, "fixtures")
    ):
        return []

    fixture_columns = _table_columns(connection, "fixtures")
    source_expression = (
        "COALESCE(f.data_source, 'legacy_untagged')"
        if "data_source" in fixture_columns
        else "'legacy_untagged'"
    )
    season_fields = []
    if "season_label" in fixture_columns:
        season_fields.append("f.season_label")
    if "season" in fixture_columns:
        season_fields.append("CAST(f.season AS TEXT)")
    kickoff_fields = []
    if "kickoff" in fixture_columns:
        kickoff_fields.append("f.kickoff")
    if "match_date" in fixture_columns:
        kickoff_fields.append("f.match_date")

    query = f"""
        SELECT
            CAST(f.fixture_id AS TEXT) AS fixture_identity,
            COALESCE(f.home_team, '') AS home_team,
            COALESCE(f.away_team, '') AS away_team,
            {_coalesce_expression(kickoff_fields)} AS kickoff_time,
            r.home_score AS full_time_home_goals,
            r.away_score AS full_time_away_goals,
            {source_expression} AS source,
            'results' AS authoritative_store,
            f.league AS league,
            {_coalesce_expression(season_fields)} AS season,
            r.id AS result_row_id
        FROM results r
        INNER JOIN fixtures f ON f.fixture_id = r.fixture_id
        WHERE r.finished = 1
        ORDER BY CAST(f.fixture_id AS TEXT), r.id DESC
    """
    return list(connection.execute(query))


def _load_stored_observations(
    connection: sqlite3.Connection,
) -> dict:
    if not _table_exists(connection, "half_time_observations"):
        return {}

    observations_by_fixture = {}
    rows = connection.execute(
        """
        SELECT *
        FROM half_time_observations
        ORDER BY fixture_identity, source
        """
    )
    for row in rows:
        observations_by_fixture.setdefault(
            str(row["fixture_identity"]),
            [],
        ).append(row)
    return observations_by_fixture


def _load_historical_conflicts(
    connection: sqlite3.Connection,
) -> dict:
    if not _table_exists(connection, "historical_match_conflicts"):
        return {}

    conflicts_by_fixture = {}
    rows = connection.execute(
        """
        SELECT
            fixture_id,
            conflict_fingerprint,
            conflict_reason
        FROM historical_match_conflicts
        WHERE resolved = 0
        ORDER BY CAST(fixture_id AS TEXT), conflict_fingerprint
        """
    )
    for row in rows:
        conflicts_by_fixture.setdefault(
            str(row["fixture_id"]),
            [],
        ).append(row)
    return conflicts_by_fixture


def _combined_conflict_metadata(
    stored,
    historical_conflicts,
) -> tuple:
    reasons = []
    fingerprints = []
    conflict_observed_at = None

    if stored is not None and _stored_conflict_status(stored):
        stored_reason = _stored_value(stored, "conflict_reason")
        if stored_reason:
            reasons.append(str(stored_reason))
        stored_fingerprint = _stored_value(
            stored,
            "conflict_fingerprint",
        )
        if stored_fingerprint:
            fingerprints.append(str(stored_fingerprint))
        conflict_observed_at = _parse_datetime(
            _stored_value(stored, "conflict_observed_at")
        )

    for conflict in historical_conflicts:
        reason = conflict["conflict_reason"]
        fingerprint = conflict["conflict_fingerprint"]
        if reason:
            reasons.append(str(reason))
        if fingerprint:
            fingerprints.append(str(fingerprint))

    if not reasons and not fingerprints:
        return False, None, None, conflict_observed_at

    return (
        True,
        ",".join(sorted(set(fingerprints)))[:512] or None,
        "; ".join(sorted(set(reasons)))[:512]
        or "unresolved historical full-time conflict",
        conflict_observed_at,
    )


def _select_authoritative_fixtures(
    historical_rows: Iterable[sqlite3.Row],
    result_rows: Iterable[sqlite3.Row],
) -> dict:
    """Apply full-time precedence: historical_matches, then latest result row."""
    selected = {}
    for row in historical_rows:
        selected.setdefault(str(row["fixture_identity"] or ""), row)
    for row in result_rows:
        selected.setdefault(str(row["fixture_identity"] or ""), row)
    return selected


def _observation_from_authoritative_fixture(
    authoritative,
    stored=None,
    historical_conflicts=(),
) -> HalfTimeObservation:
    (
        conflict_status,
        conflict_fingerprint,
        conflict_reason,
        conflict_observed_at,
    ) = _combined_conflict_metadata(stored, historical_conflicts)
    if stored is None:
        return HalfTimeObservation(
            fixture_identity=str(
                authoritative["fixture_identity"] or ""
            ),
            home_team=authoritative["home_team"] or "",
            away_team=authoritative["away_team"] or "",
            kickoff_time=_parse_datetime(authoritative["kickoff_time"]),
            full_time_home_goals=authoritative[
                "full_time_home_goals"
            ],
            full_time_away_goals=authoritative[
                "full_time_away_goals"
            ],
            half_time_home_goals=None,
            half_time_away_goals=None,
            source=authoritative["source"] or "legacy_untagged",
            observed_at=None,
            source_fixture_id=None,
            authoritative_full_time_source=authoritative[
                "authoritative_store"
            ],
            half_time_score_provenance=ScoreProvenance.MISSING,
            league=authoritative["league"],
            season=authoritative["season"],
            conflict_status=conflict_status,
            conflict_fingerprint=conflict_fingerprint,
            conflict_reason=conflict_reason,
            conflict_observed_at=conflict_observed_at,
        )

    return HalfTimeObservation(
        fixture_identity=str(authoritative["fixture_identity"] or ""),
        home_team=(
            authoritative["home_team"] or stored["home_team"] or ""
        ),
        away_team=(
            authoritative["away_team"] or stored["away_team"] or ""
        ),
        kickoff_time=_parse_datetime(
            authoritative["kickoff_time"] or stored["kickoff_time"]
        ),
        full_time_home_goals=authoritative["full_time_home_goals"],
        full_time_away_goals=authoritative["full_time_away_goals"],
        half_time_home_goals=stored["half_time_home_goals"],
        half_time_away_goals=stored["half_time_away_goals"],
        source=stored["source"],
        observed_at=_parse_datetime(stored["observed_at"]),
        source_fixture_id=stored["source_fixture_id"],
        stored_full_time_home_goals=stored["full_time_home_goals"],
        stored_full_time_away_goals=stored["full_time_away_goals"],
        authoritative_full_time_source=authoritative[
            "authoritative_store"
        ],
        half_time_score_provenance=stored[
            "half_time_score_provenance"
        ],
        league=stored["league"] or authoritative["league"],
        season=stored["season"] or authoritative["season"],
        conflict_status=conflict_status,
        conflict_fingerprint=conflict_fingerprint,
        conflict_reason=conflict_reason,
        conflict_observed_at=conflict_observed_at,
    )


def _observation_from_unmatched_storage(stored) -> HalfTimeObservation:
    return HalfTimeObservation(
        fixture_identity=str(stored["fixture_identity"] or ""),
        home_team=stored["home_team"] or "",
        away_team=stored["away_team"] or "",
        kickoff_time=_parse_datetime(stored["kickoff_time"]),
        full_time_home_goals=stored["full_time_home_goals"],
        full_time_away_goals=stored["full_time_away_goals"],
        half_time_home_goals=stored["half_time_home_goals"],
        half_time_away_goals=stored["half_time_away_goals"],
        source=stored["source"],
        observed_at=_parse_datetime(stored["observed_at"]),
        source_fixture_id=stored["source_fixture_id"],
        stored_full_time_home_goals=stored["full_time_home_goals"],
        stored_full_time_away_goals=stored["full_time_away_goals"],
        authoritative_full_time_source=None,
        half_time_score_provenance=stored[
            "half_time_score_provenance"
        ],
        league=stored["league"],
        season=stored["season"],
        conflict_status=_stored_conflict_status(stored),
        conflict_fingerprint=_stored_value(
            stored,
            "conflict_fingerprint",
        ),
        conflict_reason=_stored_value(stored, "conflict_reason"),
        conflict_observed_at=_parse_datetime(
            _stored_value(stored, "conflict_observed_at")
        ),
    )


def load_observations_from_database(
    database_path: str,
) -> tuple:
    """Load the complete fixture universe through a read-only connection.

    Full-time precedence is deterministic: ``historical_matches`` wins when
    present, otherwise the highest-id finished ``results`` row joined to
    ``fixtures`` is authoritative. Observation-only fixtures are then added.
    """
    resolved_path = Path(database_path).resolve()
    if not resolved_path.is_file():
        raise FileNotFoundError(f"Database does not exist: {resolved_path}")

    database_uri = f"{resolved_path.as_uri()}?mode=ro"
    connection = sqlite3.connect(database_uri, uri=True)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        historical_rows = _load_historical_rows(connection)
        result_rows = _load_finished_result_rows(connection)
        stored_by_fixture = _load_stored_observations(connection)
        historical_conflicts_by_fixture = _load_historical_conflicts(
            connection
        )
    finally:
        connection.close()

    authoritative_by_fixture = _select_authoritative_fixtures(
        historical_rows,
        result_rows,
    )
    fixture_identities = sorted(
        set(authoritative_by_fixture) | set(stored_by_fixture)
    )
    observations = []
    for fixture_identity in fixture_identities:
        authoritative = authoritative_by_fixture.get(fixture_identity)
        stored_rows = stored_by_fixture.get(fixture_identity, ())
        historical_conflicts = historical_conflicts_by_fixture.get(
            fixture_identity,
            (),
        )
        if authoritative is not None and not stored_rows:
            observations.append(
                _observation_from_authoritative_fixture(
                    authoritative,
                    historical_conflicts=historical_conflicts,
                )
            )
            continue

        for stored in stored_rows:
            if authoritative is not None:
                observation = _observation_from_authoritative_fixture(
                    authoritative,
                    stored,
                    historical_conflicts,
                )
            else:
                observation = _observation_from_unmatched_storage(stored)
            observations.append(
                observation
            )

    return tuple(observations)


def render_human_readable(report: dict) -> str:
    lines = [
        "ATHENA half-time coverage audit",
        (
            "Historical fixtures inspected: "
            f"{report['total_historical_fixtures_inspected']}"
        ),
        (
            "Valid half-time scores: "
            f"{report['fixtures_with_valid_half_time_scores']}"
        ),
        (
            "Missing half-time scores: "
            f"{report['fixtures_missing_half_time_scores']}"
        ),
        f"Invalid fixture observations: {report['invalid_observations']}",
        (
            "Source observations: "
            f"{report['total_source_observations']}"
        ),
        (
            "Invalid source observations: "
            f"{report['invalid_source_observations']}"
        ),
        (
            "Conflicting fixtures: "
            + (
                ", ".join(report["conflicting_fixtures"])
                if report["conflicting_fixtures"]
                else "None"
            )
        ),
        f"Coverage: {report['coverage_percentage']:.2f}%",
        f"Readiness: {report['readiness']}",
        "Readiness reasons:",
    ]
    reasons = report["readiness_reasons"] or ["None"]
    lines.extend(f"  - {reason}" for reason in reasons)

    for heading, field_name in (
        ("Coverage by league", "coverage_by_league"),
        ("Coverage by season", "coverage_by_season"),
        ("Source breakdown", "source_breakdown"),
    ):
        lines.append(f"{heading}:")
        values = report[field_name]
        if not values:
            lines.append("  - None")
        for key, bucket in values.items():
            lines.append(
                f"  - {key}: {bucket['valid']}/{bucket['total']} valid "
                f"({bucket['coverage_percentage']:.2f}%), "
                f"{bucket['missing']} missing, {bucket['invalid']} invalid"
            )

    lines.extend(
        (
            "Earliest valid observation: "
            + str(report["earliest_valid_observation"]),
            "Latest valid observation: "
            + str(report["latest_valid_observation"]),
        )
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    defaults = ReadinessThresholds()
    parser = argparse.ArgumentParser(
        description="Audit stored half-time coverage without modifying data."
    )
    parser.add_argument(
        "--database",
        default="database/athena.db",
        help="Path to the SQLite database.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )
    parser.add_argument(
        "--minimum-valid-observations",
        type=int,
        default=defaults.minimum_valid_observations,
    )
    parser.add_argument(
        "--minimum-overall-coverage",
        type=float,
        default=defaults.minimum_overall_coverage,
    )
    parser.add_argument(
        "--minimum-league-coverage",
        type=float,
        default=defaults.minimum_league_coverage,
    )
    parser.add_argument(
        "--maximum-invalid-record-percentage",
        type=float,
        default=defaults.maximum_invalid_record_percentage,
    )
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    thresholds = ReadinessThresholds(
        minimum_valid_observations=args.minimum_valid_observations,
        minimum_overall_coverage=args.minimum_overall_coverage,
        minimum_league_coverage=args.minimum_league_coverage,
        maximum_invalid_record_percentage=(
            args.maximum_invalid_record_percentage
        ),
    )
    observations = load_observations_from_database(args.database)
    report = audit_half_time_coverage(
        observations,
        thresholds=thresholds,
    ).to_dict()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_human_readable(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
