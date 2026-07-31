"""Leakage-safe pre-match features for Win Either Half research.

Features are computed from completed fixtures whose kickoff is strictly before
the target kickoff. Fixtures sharing a kickoff timestamp are evaluated against
the same prior state and are added to history only after the whole timestamp
group has been processed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Optional, Tuple


ROLLING_WINDOWS = (5, 10)
ROLLING_METRICS = (
    "observation_count",
    "goals_for_per_match",
    "goals_against_per_match",
    "first_half_goals_for_per_match",
    "first_half_goals_against_per_match",
    "first_half_win_rate",
    "second_half_win_rate",
    "win_either_half_yes_rate",
)


class FeatureBuildError(ValueError):
    """Raised when frozen label rows cannot safely produce features."""


class FeatureRole(str, Enum):
    IDENTIFIER = "IDENTIFIER"
    PRE_MATCH_FEATURE = "PRE_MATCH_FEATURE"
    TARGET_ONLY = "TARGET_ONLY"
    SPLIT_METADATA = "SPLIT_METADATA"


@dataclass(frozen=True)
class FeatureColumn:
    name: str
    role: FeatureRole
    description: str
    formula: str

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "formula": self.formula,
            "name": self.name,
            "role": self.role.value,
        }


@dataclass(frozen=True)
class HistoricalLabelMatch:
    fixture_identity: str
    kickoff_utc: datetime
    league: str
    season: str
    split: str
    home_team: str
    away_team: str
    full_time_home_goals: int
    full_time_away_goals: int
    half_time_home_goals: int
    half_time_away_goals: int
    home_win_first_half: int
    away_win_first_half: int
    home_win_second_half: int
    away_win_second_half: int
    home_win_either_half_yes: int
    away_win_either_half_yes: int
    both_teams_won_a_half: int

    def __post_init__(self) -> None:
        if not str(self.fixture_identity or "").strip():
            raise FeatureBuildError("fixture identity is required")
        if not str(self.home_team or "").strip() or not str(
            self.away_team or ""
        ).strip():
            raise FeatureBuildError("home and away team identity is required")
        kickoff = self.kickoff_utc
        if not isinstance(kickoff, datetime):
            raise FeatureBuildError("kickoff_utc must be a datetime")
        if kickoff.tzinfo is None:
            raise FeatureBuildError("kickoff_utc must be timezone-aware")
        object.__setattr__(
            self,
            "kickoff_utc",
            kickoff.astimezone(timezone.utc),
        )
        if self.split not in {"TRAIN", "VALIDATION", "TEST"}:
            raise FeatureBuildError(f"unsupported temporal split: {self.split}")
        score_fields = (
            self.full_time_home_goals,
            self.full_time_away_goals,
            self.half_time_home_goals,
            self.half_time_away_goals,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            for value in score_fields
        ):
            raise FeatureBuildError("FT and HT scores must be non-negative integers")
        if (
            self.half_time_home_goals > self.full_time_home_goals
            or self.half_time_away_goals > self.full_time_away_goals
        ):
            raise FeatureBuildError("HT scores cannot exceed FT scores")
        for field_name in (
            "home_win_first_half",
            "away_win_first_half",
            "home_win_second_half",
            "away_win_second_half",
            "home_win_either_half_yes",
            "away_win_either_half_yes",
            "both_teams_won_a_half",
        ):
            if getattr(self, field_name) not in (0, 1):
                raise FeatureBuildError(f"{field_name} must be 0 or 1")


@dataclass(frozen=True)
class PreMatchFeatureDataset:
    rows: Tuple[dict, ...]
    schema: Tuple[FeatureColumn, ...]


@dataclass(frozen=True)
class _TeamMatchEvidence:
    kickoff_utc: datetime
    split: str
    venue: str
    goals_for: int
    goals_against: int
    first_half_goals_for: int
    first_half_goals_against: int
    first_half_win: int
    second_half_win: int
    win_either_half_yes: int


_ALLOWED_HISTORY_SPLITS = {
    "TRAIN": frozenset(("TRAIN",)),
    "VALIDATION": frozenset(("TRAIN", "VALIDATION")),
    "TEST": frozenset(("TRAIN", "VALIDATION", "TEST")),
}


def _kickoff_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _history_for_target(
    history: list,
    target_split: str,
    *,
    venue: Optional[str] = None,
) -> list:
    allowed = _ALLOWED_HISTORY_SPLITS[target_split]
    return [
        item
        for item in history
        if item.split in allowed and (venue is None or item.venue == venue)
    ]


def _rolling_values(history: list, window: int) -> dict:
    values = history[-window:]
    count = len(values)
    if count == 0:
        return {
            "observation_count": 0,
            "goals_for_per_match": None,
            "goals_against_per_match": None,
            "first_half_goals_for_per_match": None,
            "first_half_goals_against_per_match": None,
            "first_half_win_rate": None,
            "second_half_win_rate": None,
            "win_either_half_yes_rate": None,
        }

    def mean(field_name: str) -> float:
        return sum(getattr(item, field_name) for item in values) / count

    return {
        "observation_count": count,
        "goals_for_per_match": mean("goals_for"),
        "goals_against_per_match": mean("goals_against"),
        "first_half_goals_for_per_match": mean("first_half_goals_for"),
        "first_half_goals_against_per_match": mean(
            "first_half_goals_against"
        ),
        "first_half_win_rate": mean("first_half_win"),
        "second_half_win_rate": mean("second_half_win"),
        "win_either_half_yes_rate": mean("win_either_half_yes"),
    }


def _add_team_features(
    row: dict,
    *,
    prefix: str,
    history: list,
    target_split: str,
    target_kickoff: datetime,
    relevant_venue: str,
) -> None:
    overall = _history_for_target(history, target_split)
    venue = _history_for_target(
        history,
        target_split,
        venue=relevant_venue,
    )
    row[f"{prefix}_prior_overall_matches"] = len(overall)
    row[f"{prefix}_prior_relevant_venue_matches"] = len(venue)
    row[f"{prefix}_no_prior_history"] = int(not overall)
    row[f"{prefix}_days_since_previous_missing"] = int(not overall)
    row[f"{prefix}_days_since_previous_fixture"] = (
        None
        if not overall
        else (target_kickoff - overall[-1].kickoff_utc).total_seconds()
        / 86400.0
    )
    for context_name, context_history in (
        ("overall", overall),
        (relevant_venue, venue),
    ):
        for window in ROLLING_WINDOWS:
            rolling = _rolling_values(context_history, window)
            for metric, value in rolling.items():
                row[
                    f"{prefix}_{context_name}_w{window}_{metric}"
                ] = value


def _append_completed_match(
    histories: dict,
    match: HistoricalLabelMatch,
) -> None:
    second_home = match.full_time_home_goals - match.half_time_home_goals
    second_away = match.full_time_away_goals - match.half_time_away_goals
    histories.setdefault(match.home_team, []).append(
        _TeamMatchEvidence(
            kickoff_utc=match.kickoff_utc,
            split=match.split,
            venue="home",
            goals_for=match.full_time_home_goals,
            goals_against=match.full_time_away_goals,
            first_half_goals_for=match.half_time_home_goals,
            first_half_goals_against=match.half_time_away_goals,
            first_half_win=int(
                match.half_time_home_goals > match.half_time_away_goals
            ),
            second_half_win=int(second_home > second_away),
            win_either_half_yes=match.home_win_either_half_yes,
        )
    )
    histories.setdefault(match.away_team, []).append(
        _TeamMatchEvidence(
            kickoff_utc=match.kickoff_utc,
            split=match.split,
            venue="away",
            goals_for=match.full_time_away_goals,
            goals_against=match.full_time_home_goals,
            first_half_goals_for=match.half_time_away_goals,
            first_half_goals_against=match.half_time_home_goals,
            first_half_win=int(
                match.half_time_away_goals > match.half_time_home_goals
            ),
            second_half_win=int(second_away > second_home),
            win_either_half_yes=match.away_win_either_half_yes,
        )
    )


def _schema() -> Tuple[FeatureColumn, ...]:
    columns = [
        FeatureColumn(
            "fixture_identity",
            FeatureRole.IDENTIFIER,
            "Canonical fixture identity.",
            "Copied from the frozen label row.",
        ),
        FeatureColumn(
            "kickoff_utc",
            FeatureRole.SPLIT_METADATA,
            "UTC target kickoff used for the strict temporal cutoff.",
            "Copied from the frozen label row and normalized to UTC.",
        ),
        FeatureColumn("league", FeatureRole.SPLIT_METADATA, "League code.", "Frozen label metadata."),
        FeatureColumn("season", FeatureRole.SPLIT_METADATA, "Football season.", "Frozen label metadata."),
        FeatureColumn("split", FeatureRole.SPLIT_METADATA, "Frozen temporal split.", "Frozen label metadata."),
        FeatureColumn("home_team", FeatureRole.IDENTIFIER, "Target home team.", "Frozen label identity."),
        FeatureColumn("away_team", FeatureRole.IDENTIFIER, "Target away team.", "Frozen label identity."),
    ]
    for prefix, venue in (
        ("home_team", "home"),
        ("away_team", "away"),
    ):
        columns.extend(
            (
                FeatureColumn(
                    f"{prefix}_prior_overall_matches",
                    FeatureRole.PRE_MATCH_FEATURE,
                    "Number of strictly earlier allowed-split team fixtures.",
                    "count(prior team fixtures with kickoff < target kickoff)",
                ),
                FeatureColumn(
                    f"{prefix}_prior_relevant_venue_matches",
                    FeatureRole.PRE_MATCH_FEATURE,
                    f"Number of strictly earlier team fixtures at {venue} venue.",
                    f"count(prior team fixtures at venue={venue})",
                ),
                FeatureColumn(
                    f"{prefix}_days_since_previous_fixture",
                    FeatureRole.PRE_MATCH_FEATURE,
                    "Elapsed days since the latest strictly earlier fixture; blank without history.",
                    "(target kickoff - latest prior kickoff) / 86400 seconds",
                ),
                FeatureColumn(
                    f"{prefix}_no_prior_history",
                    FeatureRole.PRE_MATCH_FEATURE,
                    "Explicit indicator that no allowed prior fixture exists.",
                    "1 when prior overall count is 0, otherwise 0",
                ),
                FeatureColumn(
                    f"{prefix}_days_since_previous_missing",
                    FeatureRole.PRE_MATCH_FEATURE,
                    "Explicit missingness indicator for days since previous fixture.",
                    "1 when days-since is unavailable, otherwise 0",
                ),
            )
        )
        for context in ("overall", venue):
            for window in ROLLING_WINDOWS:
                for metric in ROLLING_METRICS:
                    columns.append(
                        FeatureColumn(
                            f"{prefix}_{context}_w{window}_{metric}",
                            FeatureRole.PRE_MATCH_FEATURE,
                            f"{metric.replace('_', ' ')} over up to {window} prior {context} fixtures.",
                            (
                                "count(actual contributors)"
                                if metric == "observation_count"
                                else f"sum({metric.replace('_per_match', '').replace('_rate', '')}) / actual contributor count; blank when count=0"
                            ),
                        )
                    )
    for target in (
        "home_win_either_half_yes",
        "away_win_either_half_yes",
        "both_teams_won_a_half",
    ):
        columns.append(
            FeatureColumn(
                target,
                FeatureRole.TARGET_ONLY,
                "Frozen post-match research target; prohibited as a feature.",
                "Attached only after all pre-match features are calculated.",
            )
        )
    return tuple(columns)


FEATURE_SCHEMA = _schema()
FEATURE_COLUMNS = tuple(column.name for column in FEATURE_SCHEMA)


def build_pre_match_feature_dataset(
    matches: Iterable[HistoricalLabelMatch],
) -> PreMatchFeatureDataset:
    values = tuple(matches)
    fixture_ids = [match.fixture_identity for match in values]
    if len(set(fixture_ids)) != len(fixture_ids):
        raise FeatureBuildError("fixture identities must be unique")
    ordered = sorted(
        values,
        key=lambda item: (
            item.kickoff_utc,
            item.fixture_identity,
        ),
    )
    histories = {}
    rows = []
    index = 0
    while index < len(ordered):
        kickoff = ordered[index].kickoff_utc
        group = []
        while index < len(ordered) and ordered[index].kickoff_utc == kickoff:
            group.append(ordered[index])
            index += 1

        group_rows = []
        for match in group:
            row = {
                "fixture_identity": match.fixture_identity,
                "kickoff_utc": _kickoff_text(match.kickoff_utc),
                "league": match.league,
                "season": match.season,
                "split": match.split,
                "home_team": match.home_team,
                "away_team": match.away_team,
            }
            _add_team_features(
                row,
                prefix="home_team",
                history=histories.get(match.home_team, []),
                target_split=match.split,
                target_kickoff=match.kickoff_utc,
                relevant_venue="home",
            )
            _add_team_features(
                row,
                prefix="away_team",
                history=histories.get(match.away_team, []),
                target_split=match.split,
                target_kickoff=match.kickoff_utc,
                relevant_venue="away",
            )
            row.update(
                {
                    "home_win_either_half_yes": (
                        match.home_win_either_half_yes
                    ),
                    "away_win_either_half_yes": (
                        match.away_win_either_half_yes
                    ),
                    "both_teams_won_a_half": match.both_teams_won_a_half,
                }
            )
            group_rows.append(row)

        rows.extend(group_rows)
        for match in group:
            _append_completed_match(histories, match)

    return PreMatchFeatureDataset(rows=tuple(rows), schema=FEATURE_SCHEMA)


__all__ = [
    "FEATURE_COLUMNS",
    "FEATURE_SCHEMA",
    "FeatureBuildError",
    "FeatureColumn",
    "FeatureRole",
    "HistoricalLabelMatch",
    "PreMatchFeatureDataset",
    "ROLLING_METRICS",
    "ROLLING_WINDOWS",
    "build_pre_match_feature_dataset",
]
