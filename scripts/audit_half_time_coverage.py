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
            {_coalesce_expression(league_fields)} AS league,
            {_coalesce_expression(season_fields)} AS season
        FROM historical_matches hm
        {' '.join(joins)}
        ORDER BY CAST(hm.fixture_id AS TEXT)
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


def load_observations_from_database(
    database_path: str,
) -> tuple:
    """Load observations through a SQLite read-only connection."""
    resolved_path = Path(database_path).resolve()
    if not resolved_path.is_file():
        raise FileNotFoundError(f"Database does not exist: {resolved_path}")

    database_uri = f"{resolved_path.as_uri()}?mode=ro"
    connection = sqlite3.connect(database_uri, uri=True)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        historical_rows = _load_historical_rows(connection)
        stored_by_fixture = _load_stored_observations(connection)
    finally:
        connection.close()

    observations = []
    for historical in historical_rows:
        fixture_identity = historical["fixture_identity"]
        stored_rows = stored_by_fixture.get(fixture_identity, ())
        if not stored_rows:
            observations.append(
                HalfTimeObservation(
                    fixture_identity=fixture_identity,
                    home_team=historical["home_team"] or "",
                    away_team=historical["away_team"] or "",
                    kickoff_time=_parse_datetime(
                        historical["kickoff_time"]
                    ),
                    full_time_home_goals=historical[
                        "full_time_home_goals"
                    ],
                    full_time_away_goals=historical[
                        "full_time_away_goals"
                    ],
                    half_time_home_goals=None,
                    half_time_away_goals=None,
                    source=historical["source"] or "legacy_untagged",
                    observed_at=None,
                    source_fixture_id=None,
                    half_time_score_provenance=ScoreProvenance.MISSING,
                    league=historical["league"],
                    season=historical["season"],
                )
            )
            continue

        for stored in stored_rows:
            observations.append(
                HalfTimeObservation(
                    fixture_identity=fixture_identity,
                    home_team=(
                        stored["home_team"]
                        or historical["home_team"]
                        or ""
                    ),
                    away_team=(
                        stored["away_team"]
                        or historical["away_team"]
                        or ""
                    ),
                    kickoff_time=_parse_datetime(
                        stored["kickoff_time"]
                        or historical["kickoff_time"]
                    ),
                    full_time_home_goals=(
                        stored["full_time_home_goals"]
                        if stored["full_time_home_goals"] is not None
                        else historical["full_time_home_goals"]
                    ),
                    full_time_away_goals=(
                        stored["full_time_away_goals"]
                        if stored["full_time_away_goals"] is not None
                        else historical["full_time_away_goals"]
                    ),
                    half_time_home_goals=stored[
                        "half_time_home_goals"
                    ],
                    half_time_away_goals=stored[
                        "half_time_away_goals"
                    ],
                    source=stored["source"],
                    observed_at=_parse_datetime(stored["observed_at"]),
                    source_fixture_id=stored["source_fixture_id"],
                    half_time_score_provenance=stored[
                        "half_time_score_provenance"
                    ],
                    league=stored["league"] or historical["league"],
                    season=stored["season"] or historical["season"],
                )
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
        f"Invalid observations: {report['invalid_observations']}",
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
